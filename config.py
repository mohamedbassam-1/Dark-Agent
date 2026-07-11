from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as error:
        raise RuntimeError(f"{name} must be an integer") from error
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    sandbox_token: str
    firecrawl_api_key: str
    replay_db_path: Path
    signature_max_age_seconds: int = 60
    request_limit_bytes: int = 8_192
    provider_response_limit_bytes: int = 512_000
    rate_limit_per_minute: int = 30

    @classmethod
    def from_env(cls) -> "Settings":
        token = _required("TOOL_SANDBOX_TOKEN")
        if not 32 <= len(token) <= 4_096:
            raise RuntimeError("TOOL_SANDBOX_TOKEN must contain 32 to 4096 characters")
        search_key = _required("FIRECRAWL_API_KEY")
        if len(search_key) > 4_096:
            raise RuntimeError("FIRECRAWL_API_KEY is too long")
        return cls(
            sandbox_token=token,
            firecrawl_api_key=search_key,
            replay_db_path=Path(os.environ.get("SANDBOX_REPLAY_DB_PATH", "/tmp/dark-agent-replays.sqlite3")),
            signature_max_age_seconds=_bounded_int("SIGNATURE_MAX_AGE_SECONDS", 60, 15, 300),
            request_limit_bytes=_bounded_int("SANDBOX_REQUEST_LIMIT_BYTES", 8_192, 1_024, 65_536),
            provider_response_limit_bytes=_bounded_int("PROVIDER_RESPONSE_LIMIT_BYTES", 512_000, 32_768, 2_000_000),
            rate_limit_per_minute=_bounded_int("SANDBOX_RATE_LIMIT_PER_MINUTE", 30, 1, 300),
        )
