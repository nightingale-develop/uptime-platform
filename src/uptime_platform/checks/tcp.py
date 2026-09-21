import asyncio
import time

from uptime_platform.checks.entities import CheckResult
from uptime_platform.checks.failures import failure_kind


class TcpChecker:
    def __init__(
        self,
        host: str,
        port: int,
    ) -> None:
        self._host = host
        self._port = port

    async def check(
        self,
        timeout_seconds: int,
    ) -> CheckResult:
        started_at = time.perf_counter()

        writer: asyncio.StreamWriter | None = None

        try:
            async with asyncio.timeout(
                timeout_seconds,
            ):
                _, writer = await asyncio.open_connection(
                    host=self._host,
                    port=self._port,
                )

            response_time_ms = (time.perf_counter() - started_at) * 1000

            return CheckResult(
                success=True,
                response_time_ms=response_time_ms,
                status_code=None,
                error=None,
            )

        except (TimeoutError, OSError) as exc:
            response_time_ms = (time.perf_counter() - started_at) * 1000

            return CheckResult(
                success=False,
                response_time_ms=response_time_ms,
                status_code=None,
                error=str(exc),
                details={"failure_kind": failure_kind(exc)},
            )

        finally:
            if writer is not None:
                writer.close()

                try:
                    await writer.wait_closed()
                except OSError:
                    pass
