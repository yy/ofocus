# Spec: Native TaskPaper Import Pipeline

## Summary

The final stage of `ofocus project from-template` does **not** parse TaskPaper
into a custom Python tree. Instead, it hands the substituted TaskPaper text to
OmniFocus's native TaskPaper import support.

This is the core simplification of the revised design:

- `ofocus` owns template discovery, variable substitution, and folder lookup.
- OmniFocus owns TaskPaper parsing and project creation.

That keeps `ofocus` aligned with a long-standing Git-managed template workflow
and avoids reimplementing TaskPaper semantics.

## Why native import

Using OmniFocus's importer has three advantages:

1. Existing templates already target OmniFocus-flavored TaskPaper.
2. Relative dates such as `@due({start_date} -50d)` remain the app's
   responsibility.
3. Parameters such as `@parallel`, `@autodone`, `@repeat-method`, and
   `@repeat-rule` do not need bespoke handling in `ofocus`.

The design intentionally delegates those semantics to OmniFocus instead of
creating a second parser with subtly different behavior.

## Import flow

Input:

- substituted TaskPaper text;
- optional target folder.

Steps:

1. Read the substituted first non-blank line and use it as the display name in
   CLI output.
2. Resolve `--folder`, if provided, using the existing fuzzy folder lookup.
3. If `--copy` is set, copy the substituted TaskPaper text to the system
   clipboard and stop.
4. Otherwise invoke OmniFocus's native TaskPaper import command through the
   bridge.
5. Report success or surface the import error.

If `--folder` is omitted, import into the document root.
If `--copy` is used, `--folder` is ignored because no import occurs.

## Template expectations

v1 assumes templates are already valid OmniFocus TaskPaper text.

That means:

- indentation and structure should be authored exactly as you want OmniFocus to
  create them;
- date expressions such as `@due(2026-04-20 -50d)` are passed through
  untouched;
- checklist blocks such as `Destination TODO` or `Packing TODO` are included exactly
  as written;
- unsupported or malformed TaskPaper is an import-time error from OmniFocus,
  not something `ofocus` tries to normalize.

## Bridge contract

`ofocus` should provide a dedicated helper in `src/ofocus/jxa.py` for native
TaskPaper import.

Responsibilities of that helper:

- accept the substituted TaskPaper text;
- optionally accept a resolved folder object or folder ID;
- pass the text to OmniFocus's import mechanism;
- return a JSON result or a structured error.

The exact bridge implementation may use the native scripting command exposed by
OmniFocus's scripting dictionary. The important spec requirement is the
behavioral contract: **native TaskPaper import, not custom parsing**.

## Success output

Human mode:

```text
Created project from template: trip
  name:      Trip to Example City
  folder:    Personal
  variables: 2
```

`--json`:

```json
{
  "template": "trip",
  "name": "Trip to Example City",
  "folder": "Personal",
  "variables": {
    "destination": "Example City",
    "start_date": "2026-04-20"
  }
}
```

v1 does not require an OmniFocus item ID in the result.

## Error handling

| Situation                                  | Behavior                                                                    |
|--------------------------------------------|-----------------------------------------------------------------------------|
| Unresolved placeholders remain             | Exit 3 before calling OmniFocus.                                            |
| Template file unreadable                   | Exit 3.                                                                     |
| Template text empty after substitution     | Exit 3.                                                                     |
| Clipboard copy fails                       | Surface the clipboard error; exit 1.                                        |
| Folder lookup ambiguous                    | Reuse existing ambiguous-folder error flow; exit 1.                         |
| Folder not found                           | Reuse existing not-found error flow; exit 1.                                |
| OmniFocus rejects the TaskPaper import     | Surface the bridge error; exit 1.                                           |
| OmniFocus not running                      | Reuse existing `OmniError` handling; exit 1.                                |

## Testing strategy

### Unit tests

No OmniFocus required:

- variable extraction preserves placeholder names with spaces;
- substitution replaces repeated variables correctly;
- missing-variable errors list all missing names;
- template resolution honors the configured repo root and rejects path escape;
- clipboard export copies the substituted TaskPaper text;
- `template validate` ignores `archive/`.

### Integration tests

Optional and skipped by default:

- import a small fixture template into a throwaway folder in OmniFocus;
- assert success is reported;
- manually or programmatically clean up after the test.

The goal of integration tests is to verify the bridge path, not to duplicate
OmniFocus's TaskPaper parser in Python assertions.

## Not in scope (v1)

- Custom TaskPaper parsing in `ofocus`.
- Mapping individual `@attrs` in Python.
- Rewriting, normalizing, or linting OmniFocus TaskPaper semantics.
- Partial rollback if OmniFocus creates some items and then errors.
