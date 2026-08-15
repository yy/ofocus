# Architecture notes

Extracted from CLAUDE.md; verified against the code 2026-08-03.

## Module map

```
src/ofocus/
├── cli.py              # Root Click group + top-level commands (stats, dump, usage)
├── bridge.py           # Shared osascript runner (run_osascript_json) + OmniError
├── jxa.py              # JXA bridge (run_jxa) + all JS_* snippet constants
├── omni.py             # Legacy OmniAutomation bridge (run_omnijs); re-exports OmniError
├── helpers.py          # Validators, formatters, tree utilities, run_jxa_or_exit
├── models.py           # Task, Project, Tag, Folder dataclasses
├── USAGE.md            # Packaged copy of the CLI reference (served by `ofocus usage`)
└── commands/
    ├── inbox.py        # inbox group: list, add
    ├── task.py         # task group: ls, complete, update, drop, delete, open, search
    ├── project.py      # project group: ls, show, open, create
    └── tag.py          # tag group: ls
```

Bare `ofocus task` / `ofocus project` / `ofocus inbox` / `ofocus tag` default to
their list subcommand (`invoke_without_command=True`).

## How the OmniFocus bridge works

`run_jxa(script)` (jxa.py) runs JavaScript via `osascript -l JavaScript`.
Scripts use JXA's `Application("OmniFocus")` API. Every script ends with
`JSON.stringify(...)`; `bridge.run_osascript_json` parses the output as JSON.
`omni.run_omnijs` is a legacy OmniAutomation path kept for compatibility.

Key JXA patterns:

- `app.defaultDocument` → the OmniFocus document
- `doc.inboxTasks()` → inbox items
- `doc.flattenedTasks()` → all tasks (flat, ignoring hierarchy)
- `doc.flattenedProjects()` → all projects
- `doc.flattenedTasks.whose({id: "..."})()` → find by ID
- `app.InboxTask({name: "..."})` → create inbox task
- `app.Project({name: "..."})` → create project
- `project.tasks()` → top-level children (for tree hierarchy)
- `task.tasks()` → subtasks of an action group
- `task.sequential()` → whether children must be done in order

## Shared JXA helpers (jxa.py)

- `JS_FUZZY_MATCH` — `fuzzyMatch(collection, query)`: `collection` is a JXA
  specifier (not pre-resolved). Tries `.whose({id})` first, then linear scan:
  exact ID → ID prefix → case-insensitive name substring. Returns
  `{match}`, `{error: "ambiguous", matches}`, or `{error: "not_found"}`.
- `JS_SERIALIZE_FOLDER_CONTENTS` — `serializeFolderContents(folder)` for
  listing subfolders + projects
- `JS_LOCAL_DATE_HELPERS` — `toLocalDateString()` for date formatting

## models.py

Dataclasses `Task`, `Project`, `Tag`, `Folder`, each with `from_dict(d)`
(parse JXA JSON), `to_line()` (one-line human format), `to_dict()`.
JXA returns `camelCase` (`dueDate`, `taskCount`); Python uses `snake_case`.

## Task IDs

OmniFocus IDs are opaque strings like `j7cpqVlu3kR`. Human output shows the
first 8 chars (`helpers.py`); ID prefixes are accepted anywhere a task/project
argument is (via fuzzyMatch).

## Future work (not implemented)

Specs live in `docs/spec-*.md` (templates, taskpaper import, show command).
Also on the list: `ofocus clean` (dedupe, flag stale), batch operations,
perspectives/forecast/focus.
