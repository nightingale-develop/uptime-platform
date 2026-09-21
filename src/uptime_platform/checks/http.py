import time

import httpx2

from uptime_platform.checks.entities import CheckResult
from uptime_platform.checks.failures import failure_kind
from uptime_platform.monitors.entities import HttpMethod


class HttpChecker:
    def __init__(
        self,
        url: str,
        method: HttpMethod = HttpMethod.GET,
        expected_status_codes: tuple[int, ...] | None = None,
        body_contains: str | None = None,
        follow_redirects: bool = False,
        verify_tls: bool = True,
    ) -> None:
        self._url = url
        self._method = method
        self._expected_status_codes = expected_status_codes
        self._body_contains = body_contains
        self._follow_redirects = follow_redirects
        self._verify_tls = verify_tls

    async def check(
        self,
        timeout_seconds: int,
    ) -> CheckResult:
        started_at = time.perf_counter()

        try:
            async with httpx2.AsyncClient(
                follow_redirects=self._follow_redirects,
                verify=self._verify_tls,
            ) as client:
                response = await client.request(
                    method=self._method.value,
                    url=self._url,
                    timeout=timeout_seconds,
                )

            response_time_ms = (time.perf_counter() - started_at) * 1000

            if self._expected_status_codes is None:
                status_success = response.is_success
            else:
                status_success = response.status_code in self._expected_status_codes

            if not status_success:
                return CheckResult(
                    success=False,
                    response_time_ms=response_time_ms,
                    status_code=response.status_code,
                    error=(f"Unexpected HTTP status code: {response.status_code}"),
                )

            if (
                self._body_contains is not None
                and self._body_contains not in response.text
            ):
                return CheckResult(
                    success=False,
                    response_time_ms=response_time_ms,
                    status_code=response.status_code,
                    error=("Expected text was not found in response body"),
                )

            return CheckResult(
                success=True,
                response_time_ms=response_time_ms,
                status_code=response.status_code,
                error=None,
            )

        except httpx2.HTTPError as exc:
            response_time_ms = (time.perf_counter() - started_at) * 1000

            return CheckResult(
                success=False,
                response_time_ms=response_time_ms,
                status_code=None,
                error=str(exc),
                details={"failure_kind": failure_kind(exc)},
            )
