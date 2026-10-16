import asyncio
import signal

import pytest

import main


@pytest.mark.asyncio
async def test_sigterm_cancels_client_start_and_runs_shutdown(monkeypatch):
    loop = asyncio.get_running_loop()
    handlers = {}
    client_started = asyncio.Event()
    client_cancelled = asyncio.Event()
    shutdown_started = asyncio.Event()

    class FakeClient:
        async def start(self, token):
            client_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                client_cancelled.set()
                raise

    class FakeBot:
        def __init__(self, token):
            self.client = FakeClient()

        def begin_shutdown(self, deadline):
            shutdown_started.set()
            task = loop.create_future()
            task.set_result(None)
            return task

    monkeypatch.setattr(main, "get_discord_token", lambda: "test-token")
    monkeypatch.setattr(main, "TranslationBot", FakeBot)
    monkeypatch.setattr(
        loop,
        "add_signal_handler",
        lambda handled_signal, callback: handlers.__setitem__(handled_signal, callback),
    )

    runner = asyncio.create_task(main.run_bot(shutdown_timeout=2))
    await client_started.wait()
    handlers[signal.SIGTERM]()
    await runner

    assert client_cancelled.is_set()
    assert shutdown_started.is_set()
