# Knowledge Base — deparadigm-media/daily-curiosities-3

Isolated knowledge base for this project/business unit. Managed via
`01_SKILLS/knowledge_base.py`.

## Layout
- `sources/` — inbox; drop raw files (notes, transcripts, syllabi) here
- `notes/` — curated KB documents (markdown; the searchable content)
- `.kb/index.json` — machine manifest of documents

## Manage
```bash
python3 01_SKILLS/knowledge_base.py add    deparadigm-media daily-curiosities-3 path/to/file.md
python3 01_SKILLS/knowledge_base.py ingest deparadigm-media daily-curiosities-3   # process sources/
python3 01_SKILLS/knowledge_base.py search deparadigm-media daily-curiosities-3 "query"
python3 01_SKILLS/knowledge_base.py list   deparadigm-media daily-curiosities-3
```
