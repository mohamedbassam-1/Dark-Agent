from __future__ import annotations

import asyncio
import json
import os
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from .config import Settings
from .replay import ReplayLedger
from .search import SearchProviderError, search_web
from .security import AuthenticationError, verify_signed_request


DIAGNOSTIC_BUILD = "pandastack-env-v2"


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: StrictStr = Field(min_length=2, max_length=500)
    maxResults: StrictInt = Field(default=3, ge=1, le=10)


class ExecutionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: StrictStr
    executionId: StrictStr
    toolId: StrictStr
    input: dict[str, object]


@dataclass(slots=True)
class RateWindow:
    maximum: int
    events: deque[float]
    lock: asyncio.Lock

    async def accept(self) -> bool:
        async with self.lock:
            now = time.monotonic()
            while self.events and self.events[0] <= now - 60:
                self.events.popleft()
            if len(self.events) >= self.maximum:
                return False
            self.events.append(now)
            return True


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.settings = None
        application.state.replays = None
        application.state.rate_window = None
        application.state.configuration_status = "invalid"
        application.state.configuration_checks = _configuration_checks()
        try:
            active = configured or Settings.from_env()
            application.state.settings = active
            application.state.replays = ReplayLedger(active.replay_db_path)
            application.state.rate_window = RateWindow(active.rate_limit_per_minute, deque(), asyncio.Lock())
            application.state.configuration_status = "ready"
            application.state.configuration_checks["replayDatabase"] = "ready"
            print("[dark-agent-sandbox] startup ready", flush=True)
        except Exception as error:
            if application.state.configuration_checks["replayDatabase"] == "not_checked":
                prerequisites_ready = (
                    application.state.configuration_checks["toolSandboxToken"] == "valid"
                    and application.state.configuration_checks["firecrawlApiKey"] == "present"
                )
                application.state.configuration_checks["replayDatabase"] = "error" if prerequisites_ready else "skipped"
            print(
                f"[dark-agent-sandbox] startup locked: {type(error).__name__}",
                flush=True,
            )
        yield

    app = FastAPI(
        title="Dark Agent Tool Sandbox",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/")
    @app.get("/healthz")
    async def healthz():
        return {
            "status": "ok",
            "protocol": "dark-agent-tool-v1",
            "build": DIAGNOSTIC_BUILD,
            "configuration": app.state.configuration_status,
            "checks": app.state.configuration_checks,
            "tools": ["web_search"],
        }

    @app.post("/v1/execute")
    async def execute(
        request: Request,
        authorization: str | None = Header(default=None),
        x_dark_agent_timestamp: str | None = Header(default=None),
        x_dark_agent_execution: str | None = Header(default=None),
        x_dark_agent_tool: str | None = Header(default=None),
        x_dark_agent_signature: str | None = Header(default=None),
    ):
        settings: Settings | None = request.app.state.settings
        if settings is None:
            return _error(503, "sandbox configuration is unavailable")
        content_length = request.headers.get("content-length")
        if content_length and (not content_length.isdigit() or int(content_length) > settings.request_limit_bytes):
            return _error(413, "request exceeds the sandbox byte limit")
        raw_body = await _read_bounded_body(request, settings.request_limit_bytes)
        if raw_body is None:
            return _error(413, "request exceeds the sandbox byte limit")
        try:
            decoded = json.loads(raw_body)
            envelope = ExecutionEnvelope.model_validate(decoded)
            UUID(envelope.executionId)
        except (json.JSONDecodeError, ValueError):
            return _error(400, "invalid execution envelope")
        try:
            verify_signed_request(
                token=settings.sandbox_token,
                authorization=authorization,
                timestamp=x_dark_agent_timestamp,
                execution_id=x_dark_agent_execution,
                tool_id=x_dark_agent_tool,
                signature=x_dark_agent_signature,
                raw_body=raw_body,
                body_execution_id=envelope.executionId,
                body_tool_id=envelope.toolId,
                max_age_seconds=settings.signature_max_age_seconds,
            )
        except AuthenticationError:
            return _error(401, "request authentication failed")
        if envelope.version != "dark-agent-tool-v1" or envelope.toolId != "web_search":
            return _error(400, "tool or protocol is not allowlisted")
        if not await request.app.state.rate_window.accept():
            return _error(429, "sandbox rate limit reached")
        if not request.app.state.replays.claim(envelope.executionId):
            return _error(409, "execution id has already been used")
        try:
            search_input = SearchInput.model_validate(envelope.input)
            result = await search_web(
                query=search_input.query,
                max_results=search_input.maxResults,
                api_key=settings.firecrawl_api_key,
                response_limit_bytes=settings.provider_response_limit_bytes,
            )
        except ValueError:
            return _error(400, "tool input failed validation")
        except (SearchProviderError, RuntimeError):
            return _error(502, "search provider failed safely")
        return {
            "version": "dark-agent-tool-result-v1",
            "executionId": envelope.executionId,
            "toolId": envelope.toolId,
            "result": result,
        }

    return app


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": message})


def _configuration_checks() -> dict[str, str]:
    token = os.environ.get("TOOL_SANDBOX_TOKEN", "").strip()
    firecrawl_key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
    if not token:
        token_status = "missing"
    elif len(token) < 32:
        token_status = "too_short"
    elif len(token) > 4_096:
        token_status = "too_long"
    else:
        token_status = "valid"
    return {
        "toolSandboxToken": token_status,
        "firecrawlApiKey": "present" if firecrawl_key else "missing",
        "replayDatabase": "not_checked",
    }


async def _read_bounded_body(request: Request, maximum: int) -> bytes | None:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > maximum:
            return None
    return bytes(body)


app = create_app()
