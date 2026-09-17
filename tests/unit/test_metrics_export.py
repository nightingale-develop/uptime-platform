import asyncio
import subprocess
import sys

import pytest
from prometheus_client.parser import text_string_to_metric_families

from uptime_platform.core.metrics import Metrics, export_metrics


@pytest.mark.parametrize("error", [None, RuntimeError, asyncio.CancelledError])
def test_check_duration_uses_seconds_and_counts_interrupted_attempts(
    monkeypatch, error
):
    from uptime_platform.core import metrics as module

    clock = iter((10.0, 10.25))
    monkeypatch.setattr(module.time, "perf_counter", lambda: next(clock))
    metrics = Metrics("api")

    def execute():
        with metrics.check("http") as observation:
            if error is not None:
                raise error()
            observation.success = True

    if error is None:
        execute()
    else:
        with pytest.raises(error):
            execute()
    assert (
        metrics.registry.get_sample_value(
            "uptime_check_duration_seconds_sum", {"monitor_type": "http"}
        )
        == 0.25
    )
    assert (
        metrics.registry.get_sample_value(
            "uptime_checks_total",
            {
                "monitor_type": "http",
                "outcome": "success" if error is None else "failure",
            },
        )
        == 1
    )


def test_three_processes_export_independent_registries():
    script = """
import sys
from prometheus_client import generate_latest
from uptime_platform.core.metrics import Metrics
metrics = Metrics(sys.argv[1])
if sys.argv[1] == 'worker':
    metrics.deliveries.labels('success').inc(3)
else:
    with metrics.check('http') as observation:
        observation.success = True
print(generate_latest(metrics.registry).decode())
"""
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", script, role],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for role in ("api", "scheduler", "worker")
    ]
    try:
        outputs = []
        for process in processes:
            output, error = process.communicate(timeout=15)
            assert process.returncode == 0, error
            outputs.append(output)
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait()
    values = [
        {
            (s.name, tuple(sorted(s.labels.items()))): s.value
            for f in text_string_to_metric_families(output)
            for s in f.samples
        }
        for output in outputs
    ]
    check = ("uptime_checks_total", (("monitor_type", "http"), ("outcome", "success")))
    assert values[0][check] + values[1][check] == 2
    assert check not in values[2]
    assert (
        values[2][("uptime_notification_deliveries_total", (("outcome", "success"),))]
        == 3
    )


@pytest.mark.anyio
async def test_exporter_closes_listener_and_thread_on_cancellation(monkeypatch):
    from prometheus_client import start_http_server

    from uptime_platform.core import metrics as module

    servers = []

    def start(*args, **kwargs):
        result = start_http_server(*args, **kwargs)
        servers.append(result)
        return result

    monkeypatch.setenv("METRICS_PORT", "0")
    monkeypatch.setattr(module, "start_http_server", start)
    started = asyncio.Event()

    async def run():
        async with export_metrics(Metrics("scheduler"), 9001):
            started.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(run())
    try:
        async with asyncio.timeout(5):
            await started.wait()
            port = servers[0][0].server_port
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"GET /metrics HTTP/1.0\r\n\r\n")
            await writer.drain()
            response = await reader.read()
            writer.close()
            await writer.wait_closed()
            assert b"200 OK" in response
            assert b"uptime_scheduler_last_success_timestamp_seconds" in response
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert not servers[0][1].is_alive()
    assert servers[0][0].socket.fileno() == -1
