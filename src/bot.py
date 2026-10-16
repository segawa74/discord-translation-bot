import asyncio
import logging

import discord

from src.audio_queue import AudioQueueManager
from src.config import LANG_SETTINGS, get_shutdown_timeout
from src.translator import Translator

logger = logging.getLogger(__name__)
SHUTDOWN_FINALIZATION_RESERVE_SECONDS = 1.0


class TranslationBot:
    def __init__(self, token: str):
        self.token = token
        intents = discord.Intents.default()
        intents.message_content = True
        self.client = discord.Client(intents=intents)

        self.translator = Translator()
        self.audio_manager = AudioQueueManager()

        self.guild_settings: dict[int, dict] = {}
        self._shutdown_started = False
        self._shutdown_task: asyncio.Task | None = None
        self._shutdown_deadline: float | None = None
        self._worker_tasks: list[asyncio.Task] = []
        self._active_message_tasks: set[asyncio.Task] = set()
        self._message_tasks_at_shutdown: tuple[asyncio.Task, ...] = ()
        self._worker_deadline: float | None = None
        self._work_deadline: float | None = None

        self._register_events()

    def _register_events(self):
        @self.client.event
        async def on_ready():
            logger.info("Logged in as %s", self.client.user)

        @self.client.event
        async def on_message(message: discord.Message):
            await self._handle_message(message)

    async def _handle_message(self, message: discord.Message):
        if self._shutdown_started or message.author.bot or not message.guild:
            return

        task = asyncio.current_task()
        if task is not None:
            self._active_message_tasks.add(task)
        try:
            await self._process_message(message)
        finally:
            if task is not None:
                self._active_message_tasks.discard(task)

    async def _process_message(self, message: discord.Message):
        if message.content == "!join":
            if message.author.voice:
                try:
                    voice_client = message.guild.voice_client
                    if voice_client and voice_client.is_connected():
                        await voice_client.move_to(message.author.voice.channel)
                    else:
                        await message.author.voice.channel.connect()

                    if self._shutdown_started:
                        voice_client = message.guild.voice_client
                        if voice_client:
                            await voice_client.disconnect(force=True)
                        return

                    self.guild_settings[message.guild.id] = {
                        "channel_id": message.channel.id,
                        "lang": "ja",
                    }
                    await message.channel.send(
                        "Connected! Default: **Japanese**. "
                        "Use `!en`, `!ko`, `!ja` to switch."
                    )
                except Exception:
                    logger.exception("Failed to join voice channel")
                    await message.channel.send(
                        "Failed to connect to Voice Channel. Check bot permissions "
                        "and application logs."
                    )
            else:
                await message.channel.send("Join VC first!")
            return

        if message.content == "!bye":
            if message.guild.voice_client:
                try:
                    await message.guild.voice_client.disconnect()
                except Exception:
                    logger.exception("Failed to disconnect voice client")

            if message.guild.id in self.guild_settings:
                del self.guild_settings[message.guild.id]
            await self.audio_manager.cleanup_guild(message.guild.id)
            await message.channel.send("Disconnected.")
            return

        cmd = message.content.replace("!", "")
        if message.content.startswith("!") and cmd in LANG_SETTINGS:
            if message.guild.id in self.guild_settings:
                self.guild_settings[message.guild.id]["lang"] = cmd
                lang_name = LANG_SETTINGS[cmd]["name"]
                await message.channel.send(f"Language switched to **{lang_name}**.")
            else:
                await message.channel.send("Not connected. Use `!join` first.")
            return

        if message.guild.voice_client and message.guild.voice_client.is_connected():
            if not message.content or message.content.startswith("!"):
                return

            settings = self.guild_settings.get(message.guild.id)
            if not settings:
                return

            if message.channel.id != settings["channel_id"]:
                return

            logger.info("Received message in guild %s", message.guild.id)

            current_lang = settings["lang"]
            voice = LANG_SETTINGS[current_lang]["voice"]

            translated = await self.translator.translate(message.content, current_lang)
            if self._shutdown_started or not translated:
                return

            logger.info("Translated message for language %s", current_lang)
            try:
                await message.channel.send(f"> {translated}")
            except Exception:
                logger.exception("Failed to send translated message")

            if self._shutdown_started:
                return

            await self.audio_manager.add_item(
                message.guild, message.channel, translated, voice
            )

    def begin_shutdown(self, deadline: float) -> asyncio.Task:
        """Close admission synchronously and return the shared shutdown task."""
        if self._shutdown_task is not None:
            return self._shutdown_task

        loop = asyncio.get_running_loop()
        self._shutdown_started = True
        self._shutdown_deadline = deadline
        remaining = max(0.0, deadline - loop.time())
        final_reserve = min(SHUTDOWN_FINALIZATION_RESERVE_SECONDS, remaining / 4)
        worker_reserve = min(1.0, max(0.0, (remaining - final_reserve) / 2))
        self._worker_deadline = max(
            loop.time(), deadline - final_reserve - worker_reserve
        )
        self._work_deadline = max(loop.time(), deadline - final_reserve)

        active_tasks = tuple(
            task
            for task in self._active_message_tasks
            if task is not asyncio.current_task() and not task.done()
        )
        self._message_tasks_at_shutdown = active_tasks
        for task in active_tasks:
            task.cancel()

        self.audio_manager.stop_accepting()
        self._worker_tasks = self.audio_manager.begin_shutdown(self._worker_deadline)
        self._shutdown_task = asyncio.create_task(self._finish_shutdown())
        return self._shutdown_task

    async def shutdown(self, deadline: float | None = None):
        if deadline is None:
            deadline = asyncio.get_running_loop().time() + get_shutdown_timeout()
        task = self.begin_shutdown(deadline)
        await asyncio.shield(task)

    async def _finish_shutdown(self):
        loop = asyncio.get_running_loop()
        close_task = asyncio.create_task(self.client.close())
        pending_tasks = set(self._worker_tasks)
        pending_tasks.update(self._message_tasks_at_shutdown)
        pending_tasks.add(close_task)

        done, pending = await asyncio.wait(
            pending_tasks,
            timeout=max(0.0, self._work_deadline - loop.time()),
        )
        for task in pending:
            logger.warning(
                "Shutdown task %s exceeded the work deadline; cancelling",
                task.get_name(),
            )
            task.cancel()

        if pending:
            finished, pending = await asyncio.wait(
                pending,
                timeout=max(0.0, self._shutdown_deadline - loop.time()),
            )
            done.update(finished)

        for task in pending:
            logger.error(
                "Shutdown task %s did not finish before the shutdown deadline",
                task.get_name(),
            )

        for task in done:
            if task.cancelled():
                continue
            exception = task.exception()
            if exception is not None:
                logger.error(
                    "Shutdown task %s failed",
                    task.get_name(),
                    exc_info=(type(exception), exception, exception.__traceback__),
                )

        await self.audio_manager.finish_shutdown(self._shutdown_deadline)
