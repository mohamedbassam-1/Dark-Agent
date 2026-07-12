from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from .security import resolve_public_addresses


FIRECRAWL_SEARCH_HOST = "api.firecrawl.dev"
FIRECRAWL_SEARCH_URL = f"https://{FIRECRAWL_SEARCH_HOST}/v2/search"


class SearchProviderError(Exception):
    pass


async def search_web(
    *,
    query: str,
    max_results: int,
    api_key: str,
    response_limit_bytes: int,
) -> dict[str, Any]:
    try:
        await asyncio.to_thread(resolve_public_addresses, FIRECRAWL_SEARCH_HOST)
    except Exception as error:
        raise SearchProviderError(
            f"firecrawl_dns_failed: {type(error).__name__}: {error}"
        ) from error

    timeout = httpx.Timeout(connect=3.0, read=12.0, write=3.0, pool=3.0)
    limits = httpx.Limits(max_connections=5, max_keepalive_connections=2)
    raw = bytearray()

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            limits=limits,
            follow_redirects=False,
            trust_env=False,
            headers={"Accept": "application/json", "User-Agent": "Dark-Agent-Sandbox/1.0"},
        ) as client:
            async with client.stream(
                "POST",
                FIRECRAWL_SEARCH_URL,
                json={
                    "query": query,
                    "limit": max_results,
                    "timeout": 10_000,
                    "ignoreInvalidURLs": True,
                },
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            ) as response:
                if response.is_redirect:
                    raise SearchProviderError(
                        f"firecrawl_redirect_rejected: HTTP {response.status_code}"
                    )
                if response.status_code == 429:
                    raise SearchProviderError("firecrawl_rate_limited: HTTP 429")
                if response.status_code != 200:
                    raise SearchProviderError(
                        f"firecrawl_rejected_request: HTTP {response.status_code}"
                    )
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) > response_limit_bytes:
                        raise SearchProviderError(
                            "firecrawl_response_exceeded_byte_limit"
                        )
    except httpx.TimeoutException as error:
        raise SearchProviderError(
            f"firecrawl_timeout: {type(error).__name__}: {error}"
        ) from error
    except httpx.RequestError as error:
        raise SearchProviderError(
            f"firecrawl_transport_failed: {type(error).__name__}: {error}"
        ) from error

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise SearchProviderError("search provider returned invalid JSON") from error
    results = _firecrawl_web_results(payload)
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


def _firecrawl_web_results(payload: object) -> list[object]:
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise SearchProviderError("search provider reported a failed request")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise SearchProviderError("search provider response is missing data")
    results = data.get("web")
    if not isinstance(results, list):
        raise SearchProviderError("search provider response is missing web results")
    return results


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
