# Spec: `ofocus project from-template` and `ofocus template`

## Summary

`ofocus project from-template <template>` creates an OmniFocus project from a
single TaskPaper template stored in a separate Git-managed template repository.

The new design is intentionally simple:

- one `.taskpaper` file per template;
- no base/fragment composition;
- no axis flags like `--dest` or `--purpose`;
- no custom TaskPaper parser in `ofocus`;
- variable substitution only, followed by OmniFocus's native TaskPaper import.

This keeps the CLI close to an existing Git-based template workflow while
moving the workflow into `ofocus`.

## Command interface

### Create a project from a template

```bash
ofocus project from-template <template>
    [--var key=value]... [--var key=value]...
    [--folder NAME]
    [--dry-run | --out FILE | --copy]
    [--json]
```

| Arg / flag        | Required | Default       | Description                                                                 |
|-------------------|----------|---------------|-----------------------------------------------------------------------------|
| `<template>`      | yes      | —             | Template name or relative path, resolved inside the templates repo.         |
| `--var key=value` | no       | —             | Variable substitution. Repeatable. Split on the first `=` only.            |
| `--folder`        | no       | doc root      | Target OmniFocus folder name or ID; fuzzy-matched using existing helpers.  |
| `--dry-run`       | no       | false         | Print substituted TaskPaper to stdout; do not touch OmniFocus.             |
| `--out FILE`      | no       | —             | Write substituted TaskPaper to `FILE`; do not touch OmniFocus.             |
| `--copy`          | no       | false         | Copy substituted TaskPaper to the clipboard; do not touch OmniFocus.       |
| `--json`          | no       | false         | Emit machine-readable success or validation output.                         |

`--dry-run`, `--out`, and `--copy` are mutually exclusive.

### Inspect templates

```bash
ofocus template ls [--json]
ofocus template show <template> [--json]
ofocus template validate [--json]
```

- `template ls` lists active templates discovered in the configured templates
  repo. No OmniFocus call.
- `template show` prints the resolved file path, discovered variables, and raw
  body of a template. No OmniFocus call.
- `template validate` performs lightweight file-level checks on the entire
  template repo. No OmniFocus call.

## Behavior

### Resolution pipeline

Given:

```bash
ofocus project from-template trip \
    --var destination="Example City" \
    --var start_date=2026-04-20 \
    --folder Personal
```

the command does the following:

1. **Locate the templates repo** (see [Config](#config)).
2. **Resolve the template** to a `.taskpaper` file in that repo.
3. **Read the file as UTF-8**.
4. **Discover placeholders** using the template-variable rules in
   [`spec-template-fragments.md`](spec-template-fragments.md).
5. **Apply substitutions** from `--var`.
6. **Fail if any placeholders remain unresolved**, listing all missing variable
   names.
7. **Short-circuit if requested**:
   - `--dry-run` prints the substituted TaskPaper to stdout.
   - `--out FILE` writes the substituted TaskPaper to disk.
   - `--copy` copies the substituted TaskPaper to the system clipboard.
8. **Otherwise import the resulting TaskPaper** into OmniFocus using the native
   TaskPaper import path described in
   [`spec-taskpaper-import.md`](spec-taskpaper-import.md).

There is no intermediate composition step.

### Success output

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

`name` is derived from the substituted first non-blank line of the TaskPaper
text. v1 does not require `ofocus` to return the imported OmniFocus project ID.

## Data model

### Config

`~/.config/ofocus/config.toml`:

```toml
[templates]
dir = "~/path/to/your/templates"
```

Resolution order:

1. `OFOCUS_TEMPLATES_DIR` env var, if set.
2. `[templates] dir` in `~/.config/ofocus/config.toml`, if present.
3. Default `~/path/to/your/templates`, if it exists.
4. Otherwise error:
   `No templates dir found. Set OFOCUS_TEMPLATES_DIR or configure ~/.config/ofocus/config.toml.`

The configured directory is the **working tree root of the Git repo that stores
your templates**. `ofocus` does not clone, fetch, or manage Git itself; it only
reads the local checkout.

### Exit codes

| Code | Meaning                                                                          |
|------|----------------------------------------------------------------------------------|
| 0    | Success                                                                          |
| 1    | Generic OmniFocus / bridge error                                                 |
| 2    | Usage error                                                                      |
| 3    | Template resolution or substitution error                                        |
| 4    | Validation error                                                                 |

## Implementation notes

New code lives in:

- `src/ofocus/commands/template.py` — new Click group for `template ls`,
  `template show`, `template validate`.
- `src/ofocus/commands/project.py` — add `project from-template`.
- `src/ofocus/templates.py` — repository discovery, template resolution,
  placeholder detection, substitution, and validation helpers.

Reuse existing helpers where possible:

- `build_fuzzy_lookup_script` for `--folder`;
- `check_ambiguous` and `check_result_error` for folder lookup failures;
- `run_jxa_or_exit` for the native import bridge call.

No new parsing dependency is required. Config loading uses stdlib `tomllib`.

## Edge cases

- **Unknown template.**
  `Template not found: travel. Available: conference, course, grant, ...`
  Exit 3.
- **Bad `--var` value.**
  `Invalid --var: expected key=value`
  Exit 2.
- **Duplicate `--var` keys.**
  Last value wins.
- **Missing variables.**
  ```
  Missing required variables: destination, start_date
    destination: pass --var "destination=..."
    start_date: pass --var "start_date=..."
  ```
  Exit 3.
- **Empty substituted template.**
  `Template is empty after substitution.`
  Exit 3.
- **Folder ambiguous.**
  Reuse the existing ambiguous-folder error flow.
- **Folder not found.**
  Reuse the existing fuzzy-match not-found error flow.
- **Template path escapes the repo root** via `..` or symlink tricks.
  Reject with `Template path escapes templates dir.` Exit 3.
- **More than one of `--dry-run`, `--out`, `--copy`.**
  Usage error. Exit 2.

## Not in scope (v1)

- Fragment composition.
- Axis-specific flags such as `--dest`, `--purpose`, `--companions`.
- Shared snippets, anchors, or template inheritance.
- Automatic prompting for missing variables.
- Managing the Git repo itself from `ofocus`.
- Updating an existing OmniFocus project from a template.
