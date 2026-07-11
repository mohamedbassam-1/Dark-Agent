from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from .security import resolve_public_addresses


BRAVE_SEARCH_HOST = "api.search.brave.com"
BRAVE_SEARCH_URL = f"https://{BRAVE_SEARCH_HOST}/res/v1/web/search"


class SearchProviderError(Exception):
    pass


async def search_web(
    *,
    query: str,
    max_results: int,
    api_key: str,
    response_limit_bytes: int,
) -> dict[str, Any]:
    await asyncio.to_thread(resolve_public_addresses, BRAVE_SEARCH_HOST)
    timeout = httpx.Timeout(connect=3.0, read=8.0, write=3.0, pool=3.0)
    limits = httpx.Limits(max_connections=5, max_keepalive_connections=2)
    async with httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        follow_redirects=False,
        trust_env=False,
        headers={"Accept": "application/json", "User-Agent": "Dark-Agent-Sandbox/1.0"},
    ) as client:
        async with client.stream(
            "GET",
            BRAVE_SEARCH_URL,
            params={"q": query, "count": max_results, "safesearch": "strict", "text_decorations": "false"},
            headers={"X-Subscription-Token": api_key},
        ) as response:
            if response.is_redirect:
                raise SearchProviderError("search provider redirect rejected")
            if response.status_code == 429:
                raise SearchProviderError("search provider rate limit reached")
            if response.status_code != 200:
                raise SearchProviderError("search provider rejected the request")
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                raw.extend(chunk)
                if len(raw) > response_limit_bytes:
                    raise SearchProviderError("search provider response exceeded the byte limit")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise SearchProviderError("search provider returned invalid JSON") from error
    results = payload.get("web", {}).get("results", []) if isinstance(payload, dict) else []
    bounded_results = []
    for item in results[:max_results]:
        if not isinstance(item, dict):
            continue
        bounded_results.append(
            {
                "title": _text(item.get("title"), 300),
                "url": _public_result_url(item.get("url")),
                "description": _text(item.get("description"), 1_200),
            }
        )
    return {"query": query, "resultCount": len(bounded_results), "results": bounded_results}


def _text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(character for character in value if character >= " " or character in "\n\t")[:limit]


def _public_result_url(value: object) -> str:
    if not isinstance(value, str) or len(value) > 2_048:
        return ""
    try:
        parsed = httpx.URL(value)
    except Exception:
        return ""
    if parsed.scheme not in ("http", "https") or not parsed.host or parsed.userinfo:
        return ""
    return str(parsed)
