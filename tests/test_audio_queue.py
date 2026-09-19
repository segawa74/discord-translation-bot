import asyncio
from unittest.mock import MagicMock, patch

import pytest

from src.audio_queue import AudioQueueManager


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

    class MockCommunicate:
        def __init__(self, text, voice):
            self.text = text
            self.voice = voice

        async def save(self, filename):
            generated_files.append(filename)

    with (
        patch("src.audio_queue.edge_tts.Communicate", MockCommunicate),
        patch("src.audio_queue.discord.FFmpegPCMAudio") as mock_ffmpeg,
        patch("os.path.exists", return_value=True),
        patch("os.remove"),
    ):
        mock_ffmpeg.return_value = MagicMock()

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
        patch("os.path.exists", return_value=True),
        patch("os.remove"),
    ):
        mock_ffmpeg.return_value = MagicMock()

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
    mock_voice_client.play.side_effect = [Exception("Playback error"), None]
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
        patch("os.path.exists", return_value=True),
        patch("os.remove"),
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
