import asyncio
import signal

import pytest

from uptime_platform.notifications import main as entrypoint

pytestmark = pytest.mark.anyio


async def test_sigterm_cancels_worker_and_waits_for_cleanup(monkeypatch):
    monkeypatch.setenv("METRICS_PORT", "0")
    handlers = {}
    removed = []
    started = asyncio.Event()
    cleaned = asyncio.Event()
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(
        loop,
        "add_signal_handler",
        lambda sig, callback: handlers.update({sig: callback}),
    )
    monkeypatch.setattr(loop, "remove_signal_handler", lambda sig: removed.append(sig))

    class StubNotificationWorker:
        def __init__(self, **kwargs):
            pass

        async def run_forever(self):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

    monkeypatch.setattr(entrypoint, "NotificationWorker", StubNotificationWorker)
    async with asyncio.timeout(2):
        task = asyncio.create_task(entrypoint.main())
        await started.wait()
        handlers[signal.SIGTERM]()
        handlers[signal.SIGTERM]()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert cleaned.is_set()
    assert removed == [signal.SIGTERM]
