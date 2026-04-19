# Spec: Template CLI — user-facing docs companion

## Summary

This is the end-user companion to the simplified technical specs:

- [`spec-from-template.md`](spec-from-template.md)
- [`spec-template-fragments.md`](spec-template-fragments.md)
- [`spec-taskpaper-import.md`](spec-taskpaper-import.md)

It describes the workflow rather than the implementation details.

At implementation time, the "Workflows" section here should be merged into
`USAGE.md` and mirrored in `src/ofocus/USAGE.md`.

## Where templates live

Templates live in a separate Git repository, typically:

```text
~/path/to/your/templates/
```

`ofocus` points to the local checkout of that repo using either:

- `OFOCUS_TEMPLATES_DIR`, or
- `~/.config/ofocus/config.toml`

Example config:

```toml
[templates]
dir = "~/path/to/your/templates"
```

The active templates are the top-level `*.taskpaper` files in that repo. This
means you keep managing them the same way you do now: edit them in Git, commit
them in Git, and let `ofocus` read the working tree.

## Quick start: trip template

```bash
ofocus project from-template trip \
    --var destination="Example City" \
    --var start_date=2026-04-20 \
    --folder Personal
```

Produces:

```text
Created project from template: trip
  name:      Trip to Example City
  folder:    Personal
  variables: 2
```

The important simplification is that any `Destination TODO`, `Packing TODO`, or other
high-level checklist block is authored directly in `trip.taskpaper`. `ofocus`
does not try to turn those sections on or off.

## Workflows

### 1. Browse the template repo

```bash
ofocus template ls
```

Example:

```text
conference
course
grant
trip
writing
```

### 2. Inspect a template before using it

```bash
ofocus template show travel
```

This prints:

- the resolved path;
- the discovered variables;
- the raw TaskPaper body.

Useful when checking whether a template already contains a `Destination TODO` or
similar checklist group.

### 3. Dry-run before importing

```bash
ofocus project from-template trip \
    --var destination="Example City" \
    --var start_date=2026-04-20 \
    --dry-run
```

This prints the substituted TaskPaper and does not touch OmniFocus.

### 4. Save the substituted TaskPaper to a file

```bash
ofocus project from-template trip \
    --var destination="Example City" \
    --var start_date=2026-04-20 \
    --out /tmp/example-trip.taskpaper
```

This is useful if you want to inspect or archive the exact TaskPaper that would
be imported.

### 5. Copy the substituted TaskPaper to the clipboard

```bash
ofocus project from-template trip \
    --var destination="Example City" \
    --var start_date=2026-04-20 \
    --copy
```

This reproduces the lightweight paste-into-OmniFocus workflow: `ofocus`
prepares the final TaskPaper, puts it on the clipboard, and leaves the actual
paste/import step to you.

### 6. Validate the template repo

```bash
ofocus template validate
```

This is a lightweight repo check. It verifies that:

- the active `.taskpaper` files are readable;
- placeholders are well-formed;
- there are no duplicate template names.

It does **not** lint every OmniFocus TaskPaper feature.

### 7. Edit the template directly in Git

Example change inside `trip.taskpaper`:

```taskpaper
- Destination TODO @parallel(true) @autodone(true)
    - Local transit researched
    - Lodging details confirmed
```

Then:

```bash
cd ~/path/to/your/templates
git add trip.taskpaper
git commit
```

That is the intended content-management model: templates stay as ordinary files
in your repo, not inside `ofocus`.

## Claude Code usage

The CLI is designed so Claude Code can map a natural-language request onto:

- a template name;
- a set of `--var` values;
- an optional `--folder`;
- an optional output mode such as `--dry-run` or `--copy`.

Example:

> User: "Make a trip project for Example City starting April 20"
>
> Claude:
> ```bash
> ofocus project from-template trip \
>     --var destination="Example City" \
>     --var start_date=2026-04-20
> ```

Claude is only an input method. The template repo and the CLI remain the source
of truth.

## Tips

- Prefer simple variable names unless you already have templates that use spaces
  such as `{project name}`. Both are supported.
- Keep the templates repo version-controlled separately from `ofocus`.
- Put inactive or historical templates in `archive/` so `template ls` stays
  focused.
- Use `--dry-run` when you want to inspect the exact substituted TaskPaper, and
  `--copy` when you want the old paste-into-OmniFocus flow.
