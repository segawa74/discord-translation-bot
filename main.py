import asyncio
import logging
import signal

from src.bot import TranslationBot
from src.config import get_discord_token, get_shutdown_timeout

logger = logging.getLogger(__name__)


async def run_bot(shutdown_timeout: float | None = None):
    token = get_discord_token()
    if shutdown_timeout is None:
        shutdown_timeout = get_shutdown_timeout()
    bot = TranslationBot(token)

    loop = asyncio.get_running_loop()
    stop_requested = asyncio.Event()
    for shutdown_signal in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(shutdown_signal, stop_requested.set)
        except NotImplementedError:
            # Some event loops (notably the Windows default loop) do not support
            # asyncio signal handlers. KeyboardInterrupt still unwinds this task.
            break

    runner = asyncio.create_task(bot.client.start(token))
    stop_waiter = asyncio.create_task(stop_requested.wait())
    try:
        done, _ = await asyncio.wait(
            (runner, stop_waiter),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if runner in done:
            await runner
    finally:
        deadline = loop.time() + shutdown_timeout
        shutdown_task = bot.begin_shutdown(deadline)
        if not runner.done():
            runner.cancel()
        stop_waiter.cancel()

        tasks = {runner, stop_waiter, shutdown_task}
        _, pending = await asyncio.wait(tasks, timeout=max(0.0, deadline - loop.time()))
        for task in pending:
            task.cancel()
        if pending:
            _, pending = await asyncio.wait(
                pending, timeout=max(0.0, deadline - loop.time())
            )

        for task in pending:
            logger.error(
                "Task %s remained active at the application shutdown deadline",
                task.get_name(),
            )

        if runner.done() and not runner.cancelled():
            exception = runner.exception()
            if exception is not None:
                logger.error(
                    "Discord client task failed",
                    exc_info=(type(exception), exception, exception.__traceback__),
                )

        if shutdown_task.done() and not shutdown_task.cancelled():
            exception = shutdown_task.exception()
            if exception is not None:
                logger.error(
                    "Bot shutdown task failed",
                    exc_info=(type(exception), exception, exception.__traceback__),
                )


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Shutdown requested")


if __name__ == "__main__":
    main()
