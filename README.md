# Dark Agent PandaStack sandbox

Secure, approval-gated `web_search` execution plane for Dark Agent.

## PandaStack settings

- Base directory: `./`
- Dockerfile path: `./Dockerfile`
- Health check path: `/healthz`
- Container port: `8080` (the Docker command also accepts PandaStack's `PORT` override)
- Keep one replica/worker while replay protection uses local SQLite.

## Secrets

Add these in PandaStack's **Secrets** section, not regular Environment Variables:

- `FIRECRAWL_API_KEY`
- `TOOL_SANDBOX_TOKEN` (must be the same value used by Dark Agent and at least 32 characters)

Optional regular environment variable:

```text
SANDBOX_REPLAY_DB_PATH=/tmp/dark-agent-replays.sqlite3
```

After deployment, this URL must return JSON immediately:

```text
https://dark-agent.pandastack.app/healthz
```

Then configure Dark Agent:

```text
TOOL_SANDBOX_URL=https://dark-agent.pandastack.app/v1/execute
DARK_AGENT_ENABLE_WEB_SEARCH=true
DARK_AGENT_ENABLE_WEB_SCRAPE=false
```
