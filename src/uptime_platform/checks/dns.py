import time

import dns.asyncresolver
import dns.exception

from uptime_platform.checks.entities import CheckResult
from uptime_platform.checks.failures import failure_kind
from uptime_platform.monitors.entities import DnsRecordType


class DnsChecker:
    def __init__(
        self,
        host: str,
        record_type: DnsRecordType,
    ) -> None:
        self._host = host
        self._record_type = record_type

    async def check(
        self,
        timeout_seconds: int,
    ) -> CheckResult:
        started_at = time.perf_counter()

        try:
            answer = await dns.asyncresolver.resolve(
                self._host,
                self._record_type.value,
                lifetime=timeout_seconds,
            )

            response_time_ms = (time.perf_counter() - started_at) * 1000

            return CheckResult(
                success=True,
                response_time_ms=response_time_ms,
                status_code=None,
                error=None,
                details={
                    "record_type": self._record_type.value,
                    "records": [record.to_text() for record in answer],
                },
            )

        except (
            dns.exception.DNSException,
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
