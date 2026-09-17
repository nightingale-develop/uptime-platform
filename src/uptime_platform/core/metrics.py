import asyncio
import os
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    start_http_server,
)

from uptime_platform.monitors.entities import MonitorType

type MetricsRole = Literal["api", "scheduler", "worker"]


@dataclass
class CheckObservation:
    success: bool = False


class Metrics:
    def __init__(self, role: MetricsRole) -> None:
        self.registry = CollectorRegistry()
        if role in {"api", "scheduler"}:
            self.checks = Counter(
                "uptime_checks_total",
                "Executed check attempts.",
                ["monitor_type", "outcome"],
                registry=self.registry,
            )
            self.check_duration = Histogram(
                "uptime_check_duration_seconds",
                "Wall time spent executing checks.",
                ["monitor_type"],
                registry=self.registry,
                buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
            )
            for monitor_type in MonitorType:
                self.check_duration.labels(monitor_type.value)
                for outcome in ("success", "failure"):
                    self.checks.labels(monitor_type.value, outcome)
        if role == "scheduler":
            self.scheduler_success = Gauge(
                "uptime_scheduler_last_success_timestamp_seconds",
                "Unix timestamp of the last fully successful scheduler cycle.",
                registry=self.registry,
            )
        if role == "worker":
            self.deliveries = Counter(
                "uptime_notification_deliveries_total",
                "Notification send attempts.",
                ["outcome"],
                registry=self.registry,
            )
            for outcome in ("success", "failure"):
                self.deliveries.labels(outcome)

    @contextmanager
    def check(self, monitor_type: str) -> Iterator[CheckObservation]:
        observation = CheckObservation()
        started = time.perf_counter()
        try:
            yield observation
        finally:
            self.checks.labels(
                monitor_type, "success" if observation.success else "failure"
            ).inc()
            self.check_duration.labels(monitor_type).observe(
                time.perf_counter() - started
            )


@lru_cache
def get_metrics(role: MetricsRole) -> Metrics:
    return Metrics(role)


@asynccontextmanager
async def export_metrics(metrics: Metrics, default_port: int) -> AsyncIterator[None]:
    server, thread = start_http_server(
        int(os.environ.get("METRICS_PORT", default_port)),
        addr=os.environ.get("METRICS_HOST", "127.0.0.1"),
        registry=metrics.registry,
    )
    try:
        yield
    finally:
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        await asyncio.to_thread(thread.join)
