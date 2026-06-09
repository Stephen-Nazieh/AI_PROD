# Knowledge Base — deparadigm-media/book-review

Isolated knowledge base for this project/business unit. Managed via
`01_SKILLS/knowledge_base.py`.

## Layout
- `sources/` — inbox; drop raw files (notes, transcripts, syllabi) here
- `notes/` — curated KB documents (markdown; the searchable content)
- `.kb/index.json` — machine manifest of documents

## Manage
```bash
python3 01_SKILLS/knowledge_base.py add    deparadigm-media book-review path/to/file.md
python3 01_SKILLS/knowledge_base.py ingest deparadigm-media book-review   # process sources/
python3 01_SKILLS/knowledge_base.py search deparadigm-media book-review "query"
python3 01_SKILLS/knowledge_base.py list   deparadigm-media book-review
```
