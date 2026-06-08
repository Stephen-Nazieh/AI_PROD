---
name: Local Vault Manager Skill
description: engineering_devops
metadata:
  paperclip:
    tags:
    - engineering_devops
    source_file: 01_SKILLS/obsidian_vault_manager.md
    format_detected: yaml_frontmatter
    original_agent_id: local_vault_manager
    model_target: qwen3-coder-32b-mlx
---

# Local Vault Manager Skill

Direct file-system operations for managing the `02_CURRICULUM/compiled_wiki/` local vault. This skill replaces the Obsidian CLI with Python-native file operations, enabling full vault automation without requiring a running Obsidian instance.

## Core Directive

Read, create, search, and manage notes, properties, tags, and tasks within the local compiled wiki using direct filesystem access and the `skills.py` bridge utility.

## Vault Operations

### Read a Note

```python
from skills import read_note

content = read_note("Linear Regression Fundamentals")
# Returns full markdown content as string
```

### Create a Note

```python
from skills import create_note

create_note(
    name="New Concept Node",
    content="# New Concept\n\nDetailed explanation here.",
    frontmatter={
        "title": "New Concept Node",
        "tags": ["statistics", "active"],
        "date": "2024-01-15"
    }
)
```

### Append to a Note

```python
from skills import append_to_note

append_to_note(
    name="Existing Note",
    content="\n\n## New Section\nAdditional content here."
)
```

### Search Vault Content

```python
from skills import search_vault

results = search_vault(query="linear regression", limit=10)
# Returns list of matching file paths with snippet previews
```

### Set Property on a Note

```python
from skills import set_property

set_property(
    file_name="My Note",
    property_name="status",
    property_value="done"
)
```

### List Tags

```python
from skills import list_tags

tags = list_tags(sort_by="count")
# Returns dict of tag -> occurrence count across the vault
```

### Get Backlinks

```python
from skills import get_backlinks

links = get_backlinks("Target Note")
# Returns list of note names that wikilink to the target
```

## Daily Notes

The vault supports a daily notes pattern:

```python
from skills import daily_note_path, read_note

# Read today's daily note (auto-created if missing)
today_path = daily_note_path()
content = read_note(today_path)

# Append a task to today's note
from skills import append_to_note
append_to_note(today_path, "\n- [ ] New task for today")
```

## Task Queries

Search for tasks across the vault:

```python
from skills import query_tasks

# All incomplete tasks
todos = query_tasks(status="todo")

# Tasks in a specific note
tasks = query_tasks(file_name="Project Alpha")
```

## File Targeting

All operations use vault-relative paths from `02_CURRICULUM/compiled_wiki/`:

- `name="My Note"` resolves to `02_CURRICULUM/compiled_wiki/My Note.md`
- `path="folder/note.md"` resolves to `02_CURRICULUM/compiled_wiki/folder/note.md`
- If a file does not exist, create operations will build the necessary directory structure

## Batch Operations

For bulk vault transformations:

```python
from skills import batch_transform

# Example: add a tag to all notes matching a query
batch_transform(
    query="tag:#statistics",
    transform=lambda content, fm: (content, {**fm, "tags": fm.get("tags", []) + ["reviewed"]})
)
```
