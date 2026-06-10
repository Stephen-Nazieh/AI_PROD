# Knowledge Base — deparadigm-media/sarcastic-explainers

Isolated knowledge base for this project/business unit. Managed via
`01_SKILLS/knowledge_base.py`.

## Layout
- `sources/` — inbox; drop raw files (notes, transcripts, syllabi) here
- `notes/` — curated KB documents (markdown; the searchable content)
- `.kb/index.json` — machine manifest of documents

## Manage
```bash
python3 01_SKILLS/knowledge_base.py add    deparadigm-media sarcastic-explainers path/to/file.md
python3 01_SKILLS/knowledge_base.py ingest deparadigm-media sarcastic-explainers   # process sources/
python3 01_SKILLS/knowledge_base.py search deparadigm-media sarcastic-explainers "query"
python3 01_SKILLS/knowledge_base.py list   deparadigm-media sarcastic-explainers
```
