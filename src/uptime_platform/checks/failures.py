import socket
import ssl

import dns.exception
import dns.resolver
import httpx2


def failure_kind(error: BaseException) -> str:
    chain: list[BaseException] = []
    current: BaseException | None = error
    while current is not None and len(chain) < 10:
        chain.append(current)
        current = current.__cause__ or current.__context__
    for exception in chain:
        if isinstance(exception, ssl.SSLCertVerificationError):
            return "tls_certificate"
        if isinstance(exception, ssl.SSLError):
            return "tls"
        if isinstance(exception, (socket.gaierror, dns.resolver.NXDOMAIN)):
            return "dns"
    for exception in chain:
        if isinstance(
            exception, (TimeoutError, httpx2.TimeoutException, dns.exception.Timeout)
        ):
            return "timeout"
        if isinstance(exception, dns.exception.DNSException):
            return "dns"
        if isinstance(exception, ConnectionRefusedError):
            return "connection_refused"
        if isinstance(exception, httpx2.TooManyRedirects):
            return "redirects"
        if isinstance(exception, httpx2.ProtocolError):
            return "protocol"
        if isinstance(exception, (ConnectionError, httpx2.NetworkError)):
            return "connection"
    return "unknown"
