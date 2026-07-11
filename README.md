# Dark Agent isolated tool sandbox

This standalone Python service is the untrusted execution plane for Dark Agent. It currently allowlists only `web_search`. It never receives the OpenAI key, database credentials, mission history, or browser cookies.

## Security boundary

- Verifies the bearer credential and the exact HMAC-SHA256 contract used by `lib/tools/sandbox.ts`.
- Accepts requests only within a 60-second clock window and atomically rejects reused execution IDs.
- Validates a strict protocol, UUID, tool allowlist, input schema, body size, output size, and rate window.
- Calls only the fixed Brave Search HTTPS host, disables environment proxies and redirects, and fails closed if DNS resolves to any non-public address.
- Runs as a non-root user with one worker so the local SQLite replay ledger remains authoritative.
- Returns bounded result fields. Dark Agent still treats every returned character as untrusted and runs its deterministic sanitizer before storage.

## Run locally

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
uvicorn app.main:app --host 127.0.0.1 --port 8080 --no-access-log
```

Run those commands from `sandbox_service`. Copy `.env.example` to your secret manager; do not commit the real values.

## Deploy

Build `sandbox_service/Dockerfile` as a separate private container. Configure:

- `TOOL_SANDBOX_TOKEN`: the same high-entropy secret configured in the Dark Agent control plane.
- `BRAVE_SEARCH_API_KEY`: a server-only Brave Search API credential.
- `SANDBOX_REPLAY_DB_PATH`: a writable ephemeral path; keep exactly one application worker.

Expose only HTTPS port 443 through the hosting proxy and configure outbound egress to allow only DNS plus `api.search.brave.com:443`. Do not expose container port 8080 directly. Set Dark Agent's `TOOL_SANDBOX_URL` to:

```text
https://YOUR-SANDBOX-HOST/v1/execute
```

Keep `DARK_AGENT_ENABLE_WEB_SEARCH=true`. Set `DARK_AGENT_ENABLE_WEB_SCRAPE=false` until the separate page-reader implementation is shipped.

The container installs the exact dependency versions in `requirements.lock`; update and retest that lock deliberately rather than resolving new package versions during deployment.

The unauthenticated `GET /healthz` endpoint returns only protocol and allowlist status. API documentation endpoints and access logs are disabled.
