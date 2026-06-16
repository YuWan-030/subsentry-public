from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from backend.app.core.config import Settings


class UnsafeUrlError(ValueError):
    pass


def _is_blocked_ip(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return True
    return any(
        (
            ip.is_loopback,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_private,
            ip.is_reserved,
            ip.is_unspecified,
        )
    )


def validate_outbound_url(settings: Settings, url: str, *, label: str = "URL") -> str:
    clean_url = (url or "").strip()
    parsed = urlparse(clean_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UnsafeUrlError(f"{label} must be a valid http(s) URL")
    if parsed.username or parsed.password:
        raise UnsafeUrlError(f"{label} must not include credentials")
    if settings.allow_private_targets:
        return clean_url

    try:
        resolved = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"{label} host cannot be resolved") from exc

    for item in resolved:
        ip_text = item[4][0]
        if _is_blocked_ip(ip_text):
            raise UnsafeUrlError(f"{label} points to a private or reserved address")
    return clean_url
