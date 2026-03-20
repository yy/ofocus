# Spec: `ofocus project show`

## Summary

`ofocus project show <project>` displays a project's tasks as a tree, preserving OmniFocus action-group hierarchy.

## Command interface

```bash
ofocus project show <project_name_or_id> [--all] [--available] [--first] [--json]
```

## Behavior

- Lookup uses fuzzy matching in this order: exact ID, ID prefix, case-insensitive name substring.
- Ambiguous matches return a disambiguation error with IDs and names.
- Default output excludes completed and dropped tasks.
- `--all` includes completed and dropped tasks.
- `--available` keeps only actionable tasks.
- `--first` prints only the first available task(s).
- `--json` returns nested JSON with `remaining`, `total`, and node `type` annotations.

## Data model

- Tree nodes include: `id`, `name`, `flagged`, `completed`, `dropped`, `dueDate`, `deferDate`, `note`, `tags`, `sequential`, `children`.
- `type` is added on JSON output:
  - `"group"` for nodes with children
  - `"task"` for leaf nodes

## Implementation notes

- JXA snippets and reusable functions live in `src/ofocus/jxa.py`.
- CLI command wiring lives in `src/ofocus/commands/project.py`.
- Tree filtering/counting/formatting helpers live in `src/ofocus/helpers.py`.

## Edge cases

- Empty project: prints `(0/0 remaining)`.
- Fully completed groups: hidden in default mode.
- Ambiguous lookup: exits with an error and candidate IDs.
