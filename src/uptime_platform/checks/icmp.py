import time

from icmplib import async_ping
from icmplib.exceptions import ICMPLibError

from uptime_platform.checks.entities import CheckResult
from uptime_platform.checks.failures import failure_kind


class IcmpChecker:
    def __init__(
        self,
        host: str,
    ) -> None:
        self._host = host

    async def check(
        self,
        timeout_seconds: int,
    ) -> CheckResult:
        started_at = time.perf_counter()

        try:
            result = await async_ping(
                self._host,
                count=1,
                timeout=timeout_seconds,
                privileged=True,
            )

            response_time_ms = (time.perf_counter() - started_at) * 1000

            details = {
                "address": result.address,
                "packets_sent": result.packets_sent,
                "packets_received": result.packets_received,
                "packet_loss": result.packet_loss,
                "avg_rtt_ms": result.avg_rtt,
            }

            if not result.is_alive:
                return CheckResult(
                    success=False,
                    response_time_ms=response_time_ms,
                    status_code=None,
                    error="No ICMP reply received",
                    details=details,
                )

            return CheckResult(
                success=True,
                response_time_ms=response_time_ms,
                status_code=None,
                error=None,
                details=details,
            )

        except (
            ICMPLibError,
            OSError,
        ) as exc:
            response_time_ms = (time.perf_counter() - started_at) * 1000

            return CheckResult(
                success=False,
                response_time_ms=response_time_ms,
                status_code=None,
                error=str(exc),
                details={"failure_kind": failure_kind(exc)},
            )
