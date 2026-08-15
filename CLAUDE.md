# ofocus — Python CLI for OmniFocus via JXA (`osascript`)

- Command reference: `USAGE.md` (or `uv run ofocus usage`). Architecture,
  bridge layering, JXA patterns: `docs/architecture.md`. Feature specs:
  `docs/spec-*.md`.
- Tests need no OmniFocus: `uv run pytest`. Live smoke test (OmniFocus
  running): `uv run ofocus stats`.

## Traps

- Complete/drop via `app.markComplete(task)` / `app.markDropped(task)` —
  setting `task.completed`/`task.dropped` directly throws an access error.
- `fuzzyMatch(collection, query)` takes a JXA specifier, not a resolved array;
  it tries server-side `.whose({id})` before any linear scan.
- Two copies of USAGE.md: repo root and `src/ofocus/USAGE.md` (packaged,
  served by `ofocus usage`). Keep them in sync — they have drifted before.
- `omni.py` is a legacy OmniAutomation bridge; `OmniError` actually lives in
  `bridge.py`.
- ID prefixes (the 8 chars shown in output) are accepted wherever a
  task/project argument is.
