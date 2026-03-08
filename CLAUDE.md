# ofocus — Python CLI for OmniFocus

## What this is

A Python CLI that reads and writes to OmniFocus via JXA (JavaScript for Automation) through `osascript`. All OmniFocus interaction goes through a single bridge function `_run_jxa()` in `cli.py`.

## Architecture

```
src/ofocus/
├── __init__.py
├── cli.py          # Click CLI + JXA scripts + bridge function
├── models.py       # Task, Project, Tag, Folder dataclasses
└── omni.py         # OmniError exception class (run_omnijs is unused, kept for future OmniAutomation use)
```

### How the OmniFocus bridge works

`_run_jxa(script)` runs JavaScript via `osascript -l JavaScript`. Scripts use JXA's `Application("OmniFocus")` API to access the OmniFocus database. Every script ends with `JSON.stringify(...)` and the output is parsed as JSON.

Key JXA patterns:
- `app.defaultDocument` → the OmniFocus document
- `doc.inboxTasks()` → inbox items
- `doc.flattenedTasks()` → all tasks (flat, ignoring hierarchy)
- `doc.flattenedProjects()` → all projects
- `doc.flattenedTasks.whose({id: "..."})()` → find by ID
- `app.InboxTask({name: "..."})` → create inbox task
- `app.Project({name: "..."})` → create project
- `task.completed = true` → complete a task (JXA property assignment)
- `task.dropped = true` → drop a task

### `omni.py` — OmniAutomation bridge (currently unused)

Contains `run_omnijs()` which wraps JS in `Application("OmniFocus").evaluateJavascript(...)`. This runs code in OmniAutomation context (different API from JXA — uses `document.inbox` instead of `app.defaultDocument.inboxTasks()`). Currently unused because JXA works fine, but kept for potential cross-platform OmniAutomation use later.

### `models.py`

Simple dataclasses: `Task`, `Project`, `Tag`, `Folder`. Each has:
- `from_dict(d)` — parse from JXA JSON output
- `to_line()` — human-readable single-line format
- `to_dict()` — serialize back to JSON-compatible dict

Field name mapping: JXA returns `camelCase` (e.g. `dueDate`, `taskCount`), Python uses `snake_case`.

### `cli.py`

Click-based CLI. All commands support `--json` for machine-readable output.

**Commands:**
- `ofocus inbox` — list inbox tasks
- `ofocus inbox add "name" [--note --due --flag]` — add to inbox
- `ofocus tasks [--project --tag --flagged --due-before]` — list active tasks
- `ofocus complete <id>` — mark complete
- `ofocus update <id> [--name --due --flag/--no-flag --note]` — update task
- `ofocus drop <id>` — drop task
- `ofocus delete <id>` — permanently delete
- `ofocus projects [--folder]` — list projects
- `ofocus project-create "name" [--folder]` — create project
- `ofocus tags` — list tags
- `ofocus search "query"` — search tasks by name/note
- `ofocus stats` — quick counts
- `ofocus dump` — full JSON dump

## Development

```bash
uv sync                    # Install deps
uv run pytest              # Run tests (models only, no OmniFocus needed)
uv run ofocus --help       # CLI help
uv run ofocus stats        # Quick smoke test (needs OmniFocus running)
```

## Dependencies

- `click` — CLI framework
- `subprocess` + `json` (stdlib) — JXA bridge
- Dev: `ruff`, `pytest`, `pytest-cov`

## Task IDs

OmniFocus task IDs are opaque strings like `j7cpqVlu`. The CLI shows the first 8 chars in human output. For `complete`, `update`, `drop`, `delete` commands, pass the **full ID** (get it from `--json` output).

## Future work (not implemented)

- `ofocus clean` — deduplicate, flag stale
- Batch operations
- Publish to PyPI
- Template support
- Perspectives, forecast, focus
