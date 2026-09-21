import asyncio
import ssl
import time
from datetime import UTC, datetime, timedelta

from uptime_platform.checks.entities import CheckResult
from uptime_platform.checks.failures import failure_kind


class TlsChecker:
    def __init__(
        self,
        host: str,
        port: int,
        expiry_threshold_days: int,
    ) -> None:
        self._host = host
        self._port = port
        self._expiry_threshold_days = expiry_threshold_days

    async def check(
        self,
        timeout_seconds: int,
    ) -> CheckResult:
        started_at = time.perf_counter()

        writer: asyncio.StreamWriter | None = None

        try:
            ssl_context = ssl.create_default_context()

            async with asyncio.timeout(
                timeout_seconds,
            ):
                _, writer = await asyncio.open_connection(
                    host=self._host,
                    port=self._port,
                    ssl=ssl_context,
                    server_hostname=self._host,
                )

            response_time_ms = (time.perf_counter() - started_at) * 1000

            ssl_object = writer.get_extra_info("ssl_object")

            if ssl_object is None:
                raise RuntimeError("TLS connection has no SSL object")

            certificate = ssl_object.getpeercert()

            expires_raw = certificate.get("notAfter")

            if not isinstance(
                expires_raw,
                str,
            ):
                raise TypeError("TLS certificate expiration date is missing")
            expires_at = datetime.fromtimestamp(
                ssl.cert_time_to_seconds(expires_raw),
                tz=UTC,
            )

            now = datetime.now(UTC)
            remaining = expires_at - now

            days_until_expiry = max(
                0,
                int(remaining.total_seconds() // 86400),
            )

            details = {
                "expires_at": expires_at.isoformat(),
                "days_until_expiry": days_until_expiry,
            }

            if remaining <= timedelta(days=self._expiry_threshold_days):
                return CheckResult(
                    success=False,
                    response_time_ms=response_time_ms,
                    status_code=None,
                    error=(f"TLS certificate expires in {days_until_expiry} days"),
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
            TimeoutError,
            OSError,
            ssl.SSLError,
            RuntimeError,
            ValueError,
            TypeError,
        ) as exc:
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
