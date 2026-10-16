import asyncio
import logging
import tempfile
import threading
from pathlib import Path

import discord
import edge_tts

logger = logging.getLogger(__name__)


class _TemporaryAudioSource(discord.AudioSource):
    """Let discord.py's audio player own source and file cleanup."""

    def __init__(
        self, source: discord.AudioSource, path: Path, loop: asyncio.AbstractEventLoop
    ):
        self._source = source
        self._path = path
        self._loop = loop
        self.cleanup_complete: asyncio.Future[None] = loop.create_future()
        self._cleanup_lock = threading.Lock()
        self._cleanup_started = False

    def read(self) -> bytes:
        return self._source.read()

    def is_opus(self) -> bool:
        return self._source.is_opus()

    def cleanup(self) -> None:
        with self._cleanup_lock:
            if self._cleanup_started:
                return
            self._cleanup_started = True

        try:
            self._source.cleanup()
        except Exception:
            logger.exception("Failed to clean up audio source")
        else:
            try:
                self._path.unlink(missing_ok=True)
            except OSError:
                logger.exception("Failed to remove temporary audio file")
        finally:
            try:
                self._loop.call_soon_threadsafe(self._mark_cleanup_complete)
            except RuntimeError:
                # The process event loop may already be closing after the task deadline.
                logger.warning(
                    "Audio source cleanup completed after the event loop closed"
                )

    def _mark_cleanup_complete(self) -> None:
        if not self.cleanup_complete.done():
            self.cleanup_complete.set_result(None)


class AudioQueueManager:
    def __init__(self):
        self.queues: dict[int, asyncio.Queue] = {}
        self.workers: dict[int, asyncio.Task] = {}
        self._accepting = True
        self._worker_deadlines: dict[int, float] = {}
        self._shutdown_drain_task: asyncio.Task | None = None

    def get_queue(self, guild_id: int) -> asyncio.Queue:
        if guild_id not in self.queues:
            self.queues[guild_id] = asyncio.Queue()
        return self.queues[guild_id]

    def ensure_worker(self, guild: discord.Guild, text_channel: discord.TextChannel):
        if not self._accepting:
            return
        if guild.id not in self.workers or self.workers[guild.id].done():
            self.workers[guild.id] = asyncio.create_task(
                self._audio_worker(guild, text_channel)
            )

    async def add_item(
        self,
        guild: discord.Guild,
        text_channel: discord.TextChannel,
        text: str,
        voice_name: str,
    ) -> bool:
        if not self._accepting:
            return False

        queue = self.get_queue(guild.id)
        # The queue is unbounded, so put_nowait keeps admission atomic with the
        # shutdown gate: no other coroutine can start shutdown between this check
        # and worker creation.
        queue.put_nowait((text, voice_name))
        self.ensure_worker(guild, text_channel)
        return True

    async def _audio_worker(
        self, guild: discord.Guild, text_channel: discord.TextChannel
    ):
        queue = self.get_queue(guild.id)
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=300.0)
                except TimeoutError:
                    break
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Audio worker failed for guild %s", guild.id)
                    await asyncio.sleep(1.0)
                    continue

                try:
                    await self._process_item(guild, item)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Audio processing failed for guild %s", guild.id)
                finally:
                    queue.task_done()
        finally:
            if self.workers.get(guild.id) is asyncio.current_task():
                self.workers.pop(guild.id, None)
                self._worker_deadlines.pop(guild.id, None)

    async def _process_item(self, guild: discord.Guild, item):
        audio_path = None
        audio_source = None
        playback_started = False
        try:
            text, voice_name = item
            voice_client = guild.voice_client
            if not voice_client or not voice_client.is_connected():
                return

            with tempfile.NamedTemporaryFile(
                prefix=f"tts_{guild.id}_",
                suffix=".mp3",
                dir=tempfile.gettempdir(),
                delete=False,
            ) as audio_file:
                audio_path = Path(audio_file.name)

            communicate = edge_tts.Communicate(text, voice_name)
            await communicate.save(str(audio_path))

            while True:
                voice_client = guild.voice_client
                if not voice_client or not voice_client.is_connected():
                    return
                if not voice_client.is_playing():
                    break
                await asyncio.sleep(0.3)

            loop = asyncio.get_running_loop()
            ffmpeg_source = discord.FFmpegPCMAudio(str(audio_path))
            audio_source = _TemporaryAudioSource(ffmpeg_source, audio_path, loop)

            def after_playback(error: Exception | None) -> None:
                if error is not None:
                    logger.error(
                        "Discord audio playback failed for guild %s",
                        guild.id,
                        exc_info=(type(error), error, error.__traceback__),
                    )

            voice_client.play(audio_source, after=after_playback)
            playback_started = True

            try:
                await asyncio.shield(audio_source.cleanup_complete)
            except asyncio.CancelledError:
                try:
                    voice_client.stop()
                except Exception:
                    logger.exception("Failed to stop audio for guild %s", guild.id)
                await self._wait_for_source_cleanup(audio_source, guild.id)
                raise
        finally:
            if audio_source is None and audio_path is not None:
                try:
                    audio_path.unlink(missing_ok=True)
                except OSError:
                    logger.exception("Failed to remove temporary audio file")
            elif audio_source is not None and not playback_started:
                # A source exists but VoiceClient.play() did not take ownership.
                self._start_source_cleanup(audio_source, guild.id)
                await self._wait_for_source_cleanup(audio_source, guild.id)

    def _start_source_cleanup(
        self, audio_source: _TemporaryAudioSource, guild_id: int
    ) -> None:
        cleanup_thread = threading.Thread(
            target=audio_source.cleanup,
            name=f"audio-cleanup-{guild_id}",
            daemon=True,
        )
        cleanup_thread.start()

    async def _wait_for_source_cleanup(
        self, audio_source: _TemporaryAudioSource, guild_id: int
    ) -> bool:
        loop = asyncio.get_running_loop()
        deadline = self._worker_deadlines.get(guild_id)
        if deadline is None:
            deadline = loop.time() + 5.0
        completed, _ = await asyncio.wait(
            {audio_source.cleanup_complete},
            timeout=max(0.0, deadline - loop.time()),
        )
        if not completed:
            logger.error(
                "Audio source cleanup did not complete before deadline for guild %s; "
                "temporary file is retained until source cleanup",
                guild_id,
            )
        return audio_source.cleanup_complete.done()

    def stop_accepting(self) -> None:
        self._accepting = False

    def begin_shutdown(self, deadline: float) -> list[asyncio.Task]:
        self.stop_accepting()
        worker_tasks = list(self.workers.values())
        for guild_id, worker in self.workers.items():
            self._worker_deadlines[guild_id] = deadline
            if not worker.done():
                worker.cancel()
        if self._shutdown_drain_task is None or self._shutdown_drain_task.done():
            self._shutdown_drain_task = asyncio.create_task(
                self._drain_pending_queues(deadline)
            )
        return [*worker_tasks, self._shutdown_drain_task]

    async def _drain_pending_queues(self, deadline: float) -> None:
        for guild_id, queue in list(self.queues.items()):
            await self._drain_queue_until(queue, deadline, guild_id)

    async def _drain_queue_until(
        self, queue: asyncio.Queue, deadline: float, guild_id: int
    ) -> None:
        loop = asyncio.get_running_loop()
        while not queue.empty():
            if loop.time() >= deadline:
                logger.error(
                    "Shutdown deadline reached with %s queued audio items in guild %s",
                    queue.qsize(),
                    guild_id,
                )
                return
            for _ in range(128):
                if queue.empty():
                    break
                queue.get_nowait()
                queue.task_done()

            if queue.empty():
                break
            if loop.time() >= deadline:
                logger.error(
                    "Shutdown deadline reached with %s queued audio items in guild %s",
                    queue.qsize(),
                    guild_id,
                )
                return
            await asyncio.sleep(0)

    async def shutdown(self, deadline: float | None = None) -> list[asyncio.Task]:
        loop = asyncio.get_running_loop()
        if deadline is None:
            deadline = loop.time() + 20.0

        remaining = max(0.0, deadline - loop.time())
        final_reserve = min(1.0, remaining / 4)
        worker_reserve = min(1.0, max(0.0, (remaining - final_reserve) / 2))
        worker_deadline = max(loop.time(), deadline - final_reserve - worker_reserve)
        worker_tasks = self.begin_shutdown(worker_deadline)
        if worker_tasks:
            _, pending = await asyncio.wait(
                worker_tasks, timeout=max(0.0, worker_deadline - loop.time())
            )
        else:
            pending = set()

        for task in pending:
            logger.warning(
                "Audio shutdown task %s exceeded the work deadline; cancelling",
                task.get_name(),
            )
            task.cancel()

        if pending:
            _, pending = await asyncio.wait(
                pending, timeout=max(0.0, deadline - loop.time())
            )

        for task in pending:
            logger.error(
                "Audio shutdown task %s did not stop before shutdown deadline",
                task.get_name(),
            )

        await self.finish_shutdown(deadline)
        return list(pending)

    async def finish_shutdown(self, deadline: float) -> None:
        """Release queue references after workers have stopped or been drained."""
        await self._drain_pending_queues(deadline)

        for guild_id, worker in list(self.workers.items()):
            if worker.done():
                self.workers.pop(guild_id, None)
                self._worker_deadlines.pop(guild_id, None)

        drain_finished = (
            self._shutdown_drain_task is None or self._shutdown_drain_task.done()
        )
        if (
            not self.workers
            and drain_finished
            and all(queue.empty() for queue in self.queues.values())
        ):
            self.queues.clear()

    async def cleanup_guild(self, guild_id: int):
        loop = asyncio.get_running_loop()
        worker = self.workers.get(guild_id)
        deadline = loop.time() + 5.0
        worker_deadline = deadline - 1.0
        if worker is not None:
            self._worker_deadlines[guild_id] = worker_deadline
            if not worker.done():
                worker.cancel()
            _, pending = await asyncio.wait(
                {worker}, timeout=max(0.0, worker_deadline - loop.time())
            )
            if pending:
                logger.warning("Audio worker cleanup slow for guild %s", guild_id)
                worker.cancel()
                _, pending = await asyncio.wait(
                    pending, timeout=max(0.0, deadline - loop.time())
                )
            if pending:
                logger.error(
                    "Audio worker did not stop before cleanup deadline for guild %s",
                    guild_id,
                )

        queue = self.queues.get(guild_id)
        if queue is not None:
            await self._drain_queue_until(queue, deadline, guild_id)
            if queue.empty():
                self.queues.pop(guild_id, None)
        if worker is None or worker.done():
            self.workers.pop(guild_id, None)
            self._worker_deadlines.pop(guild_id, None)
