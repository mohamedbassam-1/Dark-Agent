from __future__ import annotations

import hashlib
import hmac
import ipaddress
import re
import socket
from datetime import datetime, timezone


HEX_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class AuthenticationError(Exception):
    pass


def verify_signed_request(
    *,
    token: str,
    authorization: str | None,
    timestamp: str | None,
    execution_id: str | None,
    tool_id: str | None,
    signature: str | None,
    raw_body: bytes,
    body_execution_id: str,
    body_tool_id: str,
    max_age_seconds: int,
    now: datetime | None = None,
) -> None:
    expected_authorization = f"Bearer {token}"
    if authorization is None or not hmac.compare_digest(authorization, expected_authorization):
        raise AuthenticationError("invalid credential")
    if not timestamp or not execution_id or not tool_id or not signature:
        raise AuthenticationError("missing authentication metadata")
    if execution_id != body_execution_id or tool_id != body_tool_id:
        raise AuthenticationError("header and body binding mismatch")
    if not HEX_SHA256.fullmatch(signature):
        raise AuthenticationError("invalid signature encoding")

    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise AuthenticationError("invalid timestamp") from error
    if parsed.tzinfo is None:
        raise AuthenticationError("timestamp must include a timezone")
    current = now or datetime.now(timezone.utc)
    if abs((current - parsed.astimezone(timezone.utc)).total_seconds()) > max_age_seconds:
        raise AuthenticationError("stale request")

    signed = timestamp.encode() + b"." + execution_id.encode() + b"." + raw_body
    expected_signature = hmac.new(token.encode(), signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise AuthenticationError("invalid signature")


def resolve_public_addresses(hostname: str) -> tuple[str, ...]:
    """Fail closed unless every resolved address is globally routable."""
    try:
        records = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise RuntimeError("search provider DNS resolution failed") from error
    addresses = tuple(sorted({record[4][0] for record in records}))
    if not addresses:
        raise RuntimeError("search provider returned no addresses")
    for address in addresses:
        parsed = ipaddress.ip_address(address)
        if not parsed.is_global:
            raise RuntimeError("search provider resolved to a non-public address")
    return addresses
