import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from src.audio_queue import AudioQueueManager
from src.bot import TranslationBot


def make_bot():
    bot = TranslationBot.__new__(TranslationBot)
    bot.client = MagicMock()
    bot.client.close = AsyncMock()
    bot.audio_manager = AudioQueueManager()
    bot.guild_settings = {}
    bot._shutdown_started = False
    bot._shutdown_task = None
    bot._shutdown_deadline = None
    bot._worker_tasks = []
    bot._active_message_tasks = set()
    bot._message_tasks_at_shutdown = ()
    bot._worker_deadline = None
    bot._work_deadline = None
    return bot


@pytest.mark.asyncio
async def test_shutdown_is_idempotent_and_closes_client_once():
    bot = make_bot()
    deadline = asyncio.get_running_loop().time() + 2

    first_task = bot.begin_shutdown(deadline)
    second_task = bot.begin_shutdown(deadline)
    await bot.shutdown(deadline)

    assert second_task is first_task
    assert bot.audio_manager._accepting is False
    bot.client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_close_timeout_cancels_client_close():
    bot = make_bot()
    close_started = asyncio.Event()
    close_cancelled = asyncio.Event()
    never_release = asyncio.Event()

    async def hanging_close():
        close_started.set()
        try:
            await never_release.wait()
        except asyncio.CancelledError:
            close_cancelled.set()
            raise

    bot.client.close = AsyncMock(side_effect=hanging_close)
    deadline = asyncio.get_running_loop().time() + 0.2

    await bot.shutdown(deadline)

    assert close_started.is_set()
    assert close_cancelled.is_set()


@pytest.mark.asyncio
async def test_shutdown_logs_client_close_failure_without_escaping():
    bot = make_bot()
    bot.client.close = AsyncMock(side_effect=RuntimeError("close failure"))

    await bot.shutdown(asyncio.get_running_loop().time() + 2)

    bot.client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_discord_client_close_continues_after_voice_disconnect_error():
    bot = make_bot()
    client = discord.Client(intents=discord.Intents.none())
    bot.client = client
    fake_voice_client = MagicMock()
    fake_voice_client.disconnect = AsyncMock(side_effect=RuntimeError("disconnect"))
    client._connection._add_voice_client(998, fake_voice_client)

    await bot.shutdown(asyncio.get_running_loop().time() + 2)

    fake_voice_client.disconnect.assert_awaited_once_with(force=True)
    assert client.is_closed()


@pytest.mark.asyncio
async def test_real_client_close_voice_disconnect_is_bounded_by_shutdown_deadline():
    bot = make_bot()
    client = discord.Client(intents=discord.Intents.none())
    bot.client = client
    disconnect_started = asyncio.Event()
    disconnect_cancelled = asyncio.Event()
    never_release = asyncio.Event()

    async def hanging_disconnect(*, force=False):
        disconnect_started.set()
        try:
            await never_release.wait()
        except asyncio.CancelledError:
            disconnect_cancelled.set()
            raise

    fake_voice_client = MagicMock()
    fake_voice_client.disconnect = AsyncMock(side_effect=hanging_disconnect)
    # Inject a fake voice protocol into the installed discord.py ConnectionState;
    # Client.close() then follows its real voice-disconnect path without a Gateway.
    client._connection._add_voice_client(999, fake_voice_client)
    deadline = asyncio.get_running_loop().time() + 0.2

    await bot.shutdown(deadline)

    assert disconnect_started.is_set()
    assert disconnect_cancelled.is_set()
    assert client.is_closed()


@pytest.mark.asyncio
async def test_message_resuming_after_shutdown_does_not_enqueue_audio():
    bot = make_bot()
    translation_started = asyncio.Event()

    class LateTranslator:
        async def translate(self, text, target_lang_code):
            translation_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                return "late translation"

    bot.translator = LateTranslator()
    add_item = AsyncMock(wraps=bot.audio_manager.add_item)
    bot.audio_manager.add_item = add_item

    guild = SimpleNamespace(
        id=900,
        name="test-guild",
        voice_client=SimpleNamespace(is_connected=lambda: True),
    )
    channel = SimpleNamespace(id=901, send=AsyncMock())
    message = SimpleNamespace(
        author=SimpleNamespace(bot=False),
        guild=guild,
        channel=channel,
        content="hello",
    )
    bot.guild_settings[guild.id] = {"channel_id": channel.id, "lang": "ja"}

    message_task = asyncio.create_task(bot._handle_message(message))
    await translation_started.wait()

    await bot.shutdown(asyncio.get_running_loop().time() + 2)
    await message_task

    add_item.assert_not_awaited()
    assert bot.audio_manager.workers == {}
    assert bot.audio_manager.queues == {}


@pytest.mark.asyncio
async def test_new_message_is_ignored_after_shutdown_gate_closes():
    bot = make_bot()
    bot.translator = MagicMock()
    bot.translator.translate = AsyncMock()
    message = SimpleNamespace(
        author=SimpleNamespace(bot=False),
        guild=SimpleNamespace(id=1),
        channel=SimpleNamespace(id=2),
        content="hello",
    )

    bot.begin_shutdown(asyncio.get_running_loop().time() + 2)
    await bot._handle_message(message)

    bot.translator.translate.assert_not_awaited()
    await bot.shutdown()
