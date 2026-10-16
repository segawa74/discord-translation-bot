import asyncio
import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from src.audio_queue import AudioQueueManager
from src.bot import TranslationBot


def complete_audio_source(source, *, after=None):
    if after is not None:
        after(None)
    source.cleanup()


class BlockingAudioSource(discord.AudioSource):
    def __init__(self, path, started, release, cleanup_calls, errors):
        self.path = Path(path)
        self.started = started
        self.release = release
        self.cleanup_calls = cleanup_calls
        self.errors = errors

    def read(self):
        try:
            assert self.path.exists()
            self.started.set()
            if not self.release.wait(timeout=5):
                raise AssertionError("test did not release fake audio thread")
            assert self.path.exists(), "file removed while fake player was reading"
        except Exception as error:
            self.errors.append(error)
        return b""

    def is_opus(self):
        return False

    def cleanup(self):
        self.cleanup_calls.append(self.path)


def start_blocking_audio_thread(source, *, after=None):
    def play_on_thread():
        try:
            source.read()
            if after is not None:
                after(None)
        except Exception as error:
            if after is not None:
                after(error)
        finally:
            source.cleanup()

    thread = threading.Thread(target=play_on_thread, daemon=True)
    thread.start()
    return thread


@pytest.mark.asyncio
async def test_audio_queue_guild_isolation():
    manager = AudioQueueManager()
    q1 = manager.get_queue(1)
    q2 = manager.get_queue(2)
    assert q1 is not q2
    assert manager.get_queue(1) is q1


@pytest.mark.asyncio
async def test_audio_queue_sequential_processing_and_unique_files():
    manager = AudioQueueManager()

    guild = MagicMock()
    guild.id = 100
    mock_voice_client = MagicMock()
    mock_voice_client.is_connected.return_value = True
    mock_voice_client.is_playing.return_value = False
    guild.voice_client = mock_voice_client

    text_channel = MagicMock()

    generated_files = []
    processed_messages = []

    class MockCommunicate:
        def __init__(self, text, voice):
            self.text = text
            self.voice = voice

        async def save(self, filename):
            generated_files.append(filename)
            processed_messages.append(self.text)

    with (
        patch("src.audio_queue.edge_tts.Communicate", MockCommunicate),
        patch("src.audio_queue.discord.FFmpegPCMAudio") as mock_ffmpeg,
    ):
        mock_ffmpeg.return_value = MagicMock()
        mock_voice_client.play.side_effect = complete_audio_source

        await manager.add_item(guild, text_channel, "First message", "ja-JP")
        await manager.add_item(guild, text_channel, "Second message", "ja-JP")

        worker_task = manager.workers[guild.id]
        queue = manager.get_queue(guild.id)
        await asyncio.wait_for(queue.join(), timeout=2.0)

        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

    assert len(generated_files) == 2
    assert generated_files[0] != generated_files[1]
    assert "100" in generated_files[0]
    assert "100" in generated_files[1]
    assert processed_messages == ["First message", "Second message"]


@pytest.mark.asyncio
async def test_audio_queue_tts_error_recovery():
    manager = AudioQueueManager()

    guild = MagicMock()
    guild.id = 200
    mock_voice_client = MagicMock()
    mock_voice_client.is_connected.return_value = True
    mock_voice_client.is_playing.return_value = False
    guild.voice_client = mock_voice_client

    text_channel = MagicMock()

    call_count = 0

    class MockCommunicate:
        def __init__(self, text, voice):
            self.text = text

        async def save(self, filename):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("TTS failure")

    with (
        patch("src.audio_queue.edge_tts.Communicate", MockCommunicate),
        patch("src.audio_queue.discord.FFmpegPCMAudio") as mock_ffmpeg,
    ):
        mock_ffmpeg.return_value = MagicMock()
        mock_voice_client.play.side_effect = complete_audio_source

        await manager.add_item(guild, text_channel, "Failing message", "ja-JP")
        await manager.add_item(guild, text_channel, "Succeeding message", "ja-JP")

        queue = manager.get_queue(guild.id)
        await asyncio.wait_for(queue.join(), timeout=2.0)

        worker_task = manager.workers[guild.id]
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

    assert call_count == 2


@pytest.mark.asyncio
async def test_audio_queue_playback_error_recovery():
    manager = AudioQueueManager()

    guild = MagicMock()
    guild.id = 300
    mock_voice_client = MagicMock()
    mock_voice_client.is_connected.return_value = True
    mock_voice_client.is_playing.return_value = False
    play_count = 0

    def fail_first_play(source, *, after=None):
        nonlocal play_count
        play_count += 1
        if play_count == 1:
            raise RuntimeError("Playback error")
        complete_audio_source(source, after=after)

    mock_voice_client.play.side_effect = fail_first_play
    guild.voice_client = mock_voice_client

    text_channel = MagicMock()

    class MockCommunicate:
        def __init__(self, text, voice):
            pass

        async def save(self, filename):
            pass

    with (
        patch("src.audio_queue.edge_tts.Communicate", MockCommunicate),
        patch("src.audio_queue.discord.FFmpegPCMAudio") as mock_ffmpeg,
    ):
        mock_ffmpeg.return_value = MagicMock()

        await manager.add_item(guild, text_channel, "First playback error", "ja-JP")
        await manager.add_item(guild, text_channel, "Second playback success", "ja-JP")

        queue = manager.get_queue(guild.id)
        await asyncio.wait_for(queue.join(), timeout=2.0)

        worker_task = manager.workers[guild.id]
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

    assert mock_voice_client.play.call_count == 2


@pytest.mark.asyncio
async def test_audio_queue_removes_temp_file_when_tts_fails(tmp_path):
    manager = AudioQueueManager()
    guild = MagicMock()
    guild.id = 400
    guild.voice_client.is_connected.return_value = True

    def fail_tts(text, voice):
        class Communicate:
            async def save(self, filename):
                raise RuntimeError("TTS failure")

        return Communicate()

    with (
        patch("src.audio_queue.tempfile.gettempdir", return_value=tmp_path),
        patch("src.audio_queue.edge_tts.Communicate", side_effect=fail_tts),
    ):
        await manager.add_item(guild, MagicMock(), "hello", "voice")
        await asyncio.wait_for(manager.get_queue(guild.id).join(), timeout=2)
        await manager.shutdown()

    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_audio_queue_removes_temp_file_when_ffmpeg_fails(tmp_path):
    manager = AudioQueueManager()
    guild = MagicMock()
    guild.id = 401
    guild.voice_client.is_connected.return_value = True
    guild.voice_client.is_playing.return_value = False
    saved_paths = []

    def fake_tts(text, voice):
        class Communicate:
            async def save(self, filename):
                path = Path(filename)
                path.write_bytes(b"audio")
                saved_paths.append(path)

        return Communicate()

    with (
        patch("src.audio_queue.tempfile.gettempdir", return_value=tmp_path),
        patch("src.audio_queue.edge_tts.Communicate", side_effect=fake_tts),
        patch("src.audio_queue.discord.FFmpegPCMAudio", side_effect=RuntimeError),
    ):
        await manager.add_item(guild, MagicMock(), "hello", "voice")
        await asyncio.wait_for(manager.get_queue(guild.id).join(), timeout=2)
        await manager.shutdown()

    assert saved_paths
    assert all(not path.exists() for path in saved_paths)


@pytest.mark.asyncio
async def test_audio_file_is_removed_after_player_thread_finishes(tmp_path):
    manager = AudioQueueManager()
    guild = MagicMock()
    guild.id = 402
    voice_client = guild.voice_client
    voice_client.is_connected.return_value = True
    voice_client.is_playing.return_value = False
    player_started = threading.Event()
    allow_player_to_finish = threading.Event()
    cleanup_calls = []
    thread_errors = []
    audio_sources = []
    player_threads = []
    audio_paths = []

    def fake_tts(text, voice):
        class Communicate:
            async def save(self, filename):
                path = Path(filename)
                path.write_bytes(b"audio")

        return Communicate()

    def fake_ffmpeg(filename):
        audio_path = Path(filename)
        audio_paths.append(audio_path)
        source = BlockingAudioSource(
            audio_path,
            player_started,
            allow_player_to_finish,
            cleanup_calls,
            thread_errors,
        )
        audio_sources.append(source)
        return source

    def fake_play(source, *, after=None):
        player_threads.append(start_blocking_audio_thread(source, after=after))

    with (
        patch("src.audio_queue.tempfile.gettempdir", return_value=tmp_path),
        patch("src.audio_queue.edge_tts.Communicate", side_effect=fake_tts),
        patch("src.audio_queue.discord.FFmpegPCMAudio", side_effect=fake_ffmpeg),
    ):
        voice_client.play.side_effect = fake_play
        await manager.add_item(guild, MagicMock(), "hello", "voice")
        await asyncio.wait_for(asyncio.to_thread(player_started.wait, 2), timeout=3)
        assert audio_paths[0].exists()

        allow_player_to_finish.set()
        await asyncio.wait_for(manager.get_queue(guild.id).join(), timeout=3)
        await asyncio.to_thread(player_threads[0].join, 2)
        await manager.shutdown()

    assert not audio_paths[0].exists()
    assert cleanup_calls == [audio_paths[0]]
    assert thread_errors == []


@pytest.mark.asyncio
async def test_bot_shutdown_keeps_file_until_player_thread_cleanup(tmp_path):
    manager = AudioQueueManager()
    bot = TranslationBot.__new__(TranslationBot)
    bot.client = MagicMock()
    bot.client.close = AsyncMock()
    bot.audio_manager = manager
    bot._shutdown_started = False
    bot._shutdown_task = None
    bot._shutdown_deadline = None
    bot._worker_tasks = []
    bot._active_message_tasks = set()
    bot._message_tasks_at_shutdown = ()
    bot._worker_deadline = None
    bot._work_deadline = None
    guild = MagicMock()
    guild.id = 404
    voice_client = guild.voice_client
    voice_client.is_connected.return_value = True
    voice_client.is_playing.return_value = False
    player_started = threading.Event()
    allow_player_to_finish = threading.Event()
    stop_requested = asyncio.Event()
    cleanup_calls = []
    thread_errors = []
    audio_paths = []
    player_threads = []

    def fake_tts(text, voice):
        class Communicate:
            async def save(self, filename):
                Path(filename).write_bytes(b"audio")

        return Communicate()

    def fake_ffmpeg(filename):
        audio_path = Path(filename)
        audio_paths.append(audio_path)
        return BlockingAudioSource(
            audio_path,
            player_started,
            allow_player_to_finish,
            cleanup_calls,
            thread_errors,
        )

    def fake_play(source, *, after=None):
        player_threads.append(start_blocking_audio_thread(source, after=after))

    voice_client.play.side_effect = fake_play
    voice_client.stop.side_effect = stop_requested.set

    with (
        patch("src.audio_queue.tempfile.gettempdir", return_value=tmp_path),
        patch("src.audio_queue.edge_tts.Communicate", side_effect=fake_tts),
        patch("src.audio_queue.discord.FFmpegPCMAudio", side_effect=fake_ffmpeg),
    ):
        await manager.add_item(guild, MagicMock(), "hello", "voice")
        await asyncio.wait_for(asyncio.to_thread(player_started.wait, 2), timeout=3)
        assert audio_paths[0].exists()

        shutdown_task = asyncio.create_task(
            bot.shutdown(deadline=asyncio.get_running_loop().time() + 3)
        )
        await asyncio.wait_for(stop_requested.wait(), timeout=2)
        assert audio_paths[0].exists()
        assert cleanup_calls == []

        allow_player_to_finish.set()
        await asyncio.wait_for(shutdown_task, timeout=3)
        await asyncio.to_thread(player_threads[0].join, 2)

    assert not audio_paths[0].exists()
    assert cleanup_calls == [audio_paths[0]]
    assert thread_errors == []
    assert manager.workers == {}
    bot.client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_cancels_all_guild_workers_before_waiting():
    manager = AudioQueueManager()
    release_workers = asyncio.Event()
    cancellation_events = asyncio.Queue()
    guild_ids = (501, 502, 503)

    async def slow_worker(guild_id):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancellation_events.put_nowait(guild_id)
            await release_workers.wait()
            raise

    for guild_id in guild_ids:
        manager.queues[guild_id] = asyncio.Queue()
        manager.workers[guild_id] = asyncio.create_task(slow_worker(guild_id))

    shutdown_task = asyncio.create_task(
        manager.shutdown(deadline=asyncio.get_running_loop().time() + 2)
    )
    cancelled_ids = await asyncio.wait_for(
        asyncio.gather(*(cancellation_events.get() for _ in guild_ids)), timeout=1
    )
    assert set(cancelled_ids) == set(guild_ids)

    release_workers.set()
    await asyncio.wait_for(shutdown_task, timeout=2)

    assert manager.workers == {}
    assert manager.queues == {}


@pytest.mark.asyncio
async def test_audio_queue_rejects_items_after_shutdown_starts():
    manager = AudioQueueManager()
    guild = MagicMock()
    guild.id = 505

    workers = manager.begin_shutdown(asyncio.get_running_loop().time() + 2)
    accepted = await manager.add_item(guild, MagicMock(), "late", "voice")
    await asyncio.gather(*workers, return_exceptions=True)
    await manager.finish_shutdown(asyncio.get_running_loop().time() + 2)

    assert accepted is False
    assert manager.workers == {}
    assert manager.queues == {}


@pytest.mark.asyncio
async def test_audio_queue_shutdown_awaits_worker_cancellation():
    manager = AudioQueueManager()
    guild = MagicMock()
    guild.id = 403

    await manager.add_item(guild, MagicMock(), "hello", "voice")
    worker = manager.workers[guild.id]
    queue = manager.get_queue(guild.id)

    await manager.shutdown()
    await asyncio.wait_for(queue.join(), timeout=1)

    assert worker.cancelled()
    assert manager.workers == {}
    assert manager.queues == {}
