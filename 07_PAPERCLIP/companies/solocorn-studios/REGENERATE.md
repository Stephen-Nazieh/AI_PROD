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
