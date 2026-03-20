# ofocus — Python CLI for OmniFocus

## What this is

A Python CLI that reads and writes to OmniFocus via JXA (JavaScript for Automation) through `osascript`. All OmniFocus interaction goes through `run_jxa()` in `jxa.py`.

## Architecture

```
src/ofocus/
├── __init__.py
├── cli.py              # Root Click group + top-level commands (stats, dump, usage)
├── jxa.py              # JXA bridge (run_jxa) + all JS_* snippet constants
├── helpers.py          # Validators, formatters, tree utilities
├── commands/
│   ├── inbox.py        # inbox group: list, add
│   ├── task.py         # task group: ls, complete, update, drop, delete, search
│   ├── project.py      # project group: ls, show, create
│   └── tag.py          # tag group: ls
├── models.py           # Task, Project, Tag, Folder dataclasses
└── omni.py             # OmniError exception class
```

### How the OmniFocus bridge works

`run_jxa(script)` runs JavaScript via `osascript -l JavaScript`. Scripts use JXA's `Application("OmniFocus")` API to access the OmniFocus database. Every script ends with `JSON.stringify(...)` and the output is parsed as JSON.

Key JXA patterns:
- `app.defaultDocument` → the OmniFocus document
- `doc.inboxTasks()` → inbox items
- `doc.flattenedTasks()` → all tasks (flat, ignoring hierarchy)
- `doc.flattenedProjects()` → all projects
- `doc.flattenedTasks.whose({id: "..."})()` → find by ID
- `app.InboxTask({name: "..."})` → create inbox task
- `app.Project({name: "..."})` → create project
- `app.markComplete(task)` → complete a task (NOT `task.completed = true`, which throws access error)
- `app.markDropped(task)` → drop a task (NOT `task.dropped = true`)
- `project.tasks()` → top-level children (for tree hierarchy)
- `task.tasks()` → subtasks of an action group
- `task.sequential()` → whether children must be done in order

### Shared JXA helpers

- `JS_FUZZY_MATCH` — reusable `fuzzyMatch(items, query)` function: exact ID → ID prefix → name substring
- `JS_SERIALIZE_FOLDER_CONTENTS` — reusable `serializeFolderContents(folder)` for listing subfolders + projects
- `JS_LOCAL_DATE_HELPERS` — `toLocalDateString()` for date formatting

### `models.py`

Simple dataclasses: `Task`, `Project`, `Tag`, `Folder`. Each has:
- `from_dict(d)` — parse from JXA JSON output
- `to_line()` — human-readable single-line format
- `to_dict()` — serialize back to JSON-compatible dict

Field name mapping: JXA returns `camelCase` (e.g. `dueDate`, `taskCount`), Python uses `snake_case`.

### Commands (gh-style subcommands)

```
ofocus project ls [folder]                     # Browse folders/projects (tree)
ofocus project show <project> [--available --first --all]  # Project task tree
ofocus project create "name" [--folder]        # Create project
ofocus task ls [--project --tag --flagged --due-before]    # List active tasks
ofocus task complete <id>                      # Mark complete
ofocus task update <id> [--name --due --flag --note --project]  # Update task
ofocus task drop <id>                          # Drop task
ofocus task delete <id>                        # Permanently delete
ofocus task search "query"                     # Search by name/note
ofocus inbox                                   # List inbox tasks
ofocus inbox add "name" [--note --due --flag]  # Add to inbox
ofocus tag ls                                  # List tags
ofocus stats                                   # Quick counts
ofocus dump                                    # Full JSON dump
ofocus usage                                   # CLI reference
```

Bare `ofocus task` defaults to `ofocus task ls`. Bare `ofocus project` defaults to `ofocus project ls`.

## Development

```bash
uv sync                    # Install deps
uv run pytest              # Run tests (no OmniFocus needed)
uv run ofocus --help       # CLI help
uv run ofocus stats        # Quick smoke test (needs OmniFocus running)
```

## Dependencies

- `click` — CLI framework
- `subprocess` + `json` (stdlib) — JXA bridge
- Dev: `ruff`, `pytest`, `pytest-cov`

## Task IDs

OmniFocus task IDs are opaque strings like `j7cpqVlu3kR`. The CLI shows the first 8 chars in human output. ID prefixes work in task/project commands — you can pass the truncated 8-char ID directly.

## Future work (not implemented)

- `ofocus clean` — deduplicate, flag stale
- Batch operations
- Template support
- Perspectives, forecast, focus
