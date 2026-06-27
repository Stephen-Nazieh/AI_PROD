# Secrets & hygiene

All secrets live in **git-ignored** files — never in tracked code:
- `content_engine/config/credentials.json` — TikTok/YouTube posting creds (template: `credentials.example.json`)
- `.docker/.env` — `OPENCLAW_GATEWAY_TOKEN`, `OPENCLAW_TOKEN`, `PAPERCLIP_DB_*`

Tracked files reference these by env var (e.g. `${OPENCLAW_GATEWAY_TOKEN}` in `docker-compose.yml`,
`os.environ.get("OPENCLAW_TOKEN", "")` in the runtime agents).

## OpenClaw token rotation (done)
The gateway token was previously hardcoded (the old hardcoded value) across 7 tracked files in
this **public** repo. It's been **rotated** — the new value is in `.docker/.env` only — and scrubbed
from all tracked files. ⚠️ The old value still exists in **git history**, so treat it as burned
(rotation makes it useless). If you ever need to purge history too, use `git filter-repo`; otherwise
rotation is sufficient. To run OpenClaw, export the token from `.docker/.env`.

## Quick audit
```sh
# nothing secret should print:
git grep -nE "solocorn_secure_token|sk-[A-Za-z0-9]{20}|AKIA[0-9A-Z]{16}" -- . ':!*.example.*'
```
