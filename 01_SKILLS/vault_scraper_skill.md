---
agent_id: local_vault_scraper
type: engineering_devops
model_target: qwen3-coder-32b-mlx
---

# Local Vault Scraper Skill

Extract and clean markdown content from raw source materials and process them into the `02_CURRICULUM/compiled_wiki/` local vault. This skill replaces external web-fetching tools with direct file-system operations and local oMLX-powered content cleaning.

## Core Directive

Process raw text documents, transcripts, and ingest queues from `02_CURRICULUM/raw_sources/` into clean, structured wiki nodes inside `02_CURRICULUM/compiled_wiki/`.

## Workflow

1. **Scan raw sources**: List all files in `02_CURRICULUM/raw_sources/youtube_ingest/` and `02_CURRICULUM/raw_sources/web_ingest/`.
2. **Read content**: Load each raw file as plain text or markdown.
3. **Clean via oMLX**: Dispatch the raw content to the local oMLX server for cleaning:
   - Strip verbal filler words and navigation clutter
   - Fix incorrect programming syntax
   - Format math symbols using clean markdown notation
   - Structure into logical sections with headings
4. **Deduplicate**: Check the compiled wiki index for existing nodes on the same topic.
5. **Write node**: Save the cleaned content as a new `.md` file in `02_CURRICULUM/compiled_wiki/`.
6. **Link graph**: Inject wikilink tags (`[[Related Node]]`) to connect with existing nodes.

## oMLX Cleaning Prompt Template

When dispatching raw content to `http://127.0.0.1:8000/v1/chat/completions`, use this system instruction:

```
You are a document cleaning engine. Your job is to:
1. Remove all filler words (um, uh, like, you know, basically)
2. Fix any broken code syntax
3. Convert math expressions to LaTeX markdown ($...$ or $$...$$)
4. Structure the output with clear headings
5. Preserve all factual claims and technical details exactly
6. Do NOT add opinions or commentary not present in the source
```

## Output Format

Each cleaned node must include:
- YAML frontmatter with `title`, `date`, `tags`, and `source`
- Clean markdown body with proper heading hierarchy
- Wikilink cross-references to related compiled nodes
- A `## Sources` section at the bottom citing the original raw file

## File Naming Convention

```
{topic-slug}_{source-type}_{date}.md
```

Examples:
- `linear_regression_youtube_2024-01-15.md`
- `gcp_serverless_web_2024-01-16.md`

## Safety Rules

- Never overwrite an existing compiled node without creating a `.backup` copy first.
- If conflicting information is detected, prepend `**[CONTEXT ALERT: CONTRADICTION DETECTED]**` to the node.
- If a raw source has no processable content (empty, corrupted, or non-text), move it to `02_CURRICULUM/raw_sources/_rejected/` and log the reason.
