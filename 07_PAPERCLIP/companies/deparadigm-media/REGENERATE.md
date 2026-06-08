# Regenerating agents/ and skills/

This package intentionally does **not** keep `agents/` and `skills/` on disk.
They are byte-identical copies of the canonical `library/` and are gitignored
to avoid a ~4.3MB duplicate in version control.

Before running `npx paperclipai company import`, regenerate them:

```bash
python3 07_PAPERCLIP/scripts/sync_company.py --company solocorn-studios --all
```

This copies `library/agents/` → `agents/` and `library/skills/` → `skills/`.
The unique, version-controlled parts of this package are `COMPANY.md`,
`.paperclip.yaml`, `teams/`, and `projects/`.

## ⚠️ `company import` is not idempotent

Each `npx paperclipai company import` creates a **new** company rather than
updating the existing one, so repeated imports pile up duplicate "Solocorn
Studios" companies. The bridge targets the original (`PAPERCLIP_COMPANY_ID`),
so duplicates are dead weight. Prefer editing in the Paperclip UI/API; reserve
`import` for first-time setup. Delete stale duplicates with
`DELETE /api/companies/<id>` — note Paperclip's delete returns HTTP 500 for any
company that has run history (cost_events FK bug); those need their cost_events
cleared in the embedded Postgres first. See AGENTS.md "Re-import Company Package".
