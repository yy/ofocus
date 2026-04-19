# Spec: Template Library Format and Variable Substitution

## Summary

Despite the old filename, this spec no longer describes fragments. The fragment
design is dropped.

The v1 template library is a directory of plain `.taskpaper` files stored in a
separate Git repository. Each file is a complete template. `ofocus` performs
only two template-specific operations:

1. discover available template files;
2. substitute `{variables}` in the file text.

Everything else about structure, dates, tags, repetition, and project layout is
left to OmniFocus's native TaskPaper importer.

## Directory layout

Recommended layout:

```text
<templates_dir>/
├── trip.taskpaper
├── conference.taskpaper
├── course.taskpaper
├── launch.taskpaper
├── event.taskpaper
├── renewal.taskpaper
├── application.taskpaper
├── writing.taskpaper
├── mentoring.taskpaper
├── media.taskpaper
├── archive/
│   ├── old_trip.taskpaper
│   └── ...
├── README.md
└── tests/ or scripts/ (optional)
```

Rules:

- The configured `templates_dir` is the root of your Git-managed template repo.
- Active templates are top-level `*.taskpaper` files in that root.
- `archive/` is ignored by `template ls` and `template validate`.
- Non-template files such as `README.md`, tests, or helper scripts may live in
  the repo but are ignored by discovery.

This layout matches a simple Git-managed template repository.

## Template file format

A template is a plain UTF-8 TaskPaper file. There is no YAML frontmatter.

Example:

```taskpaper
Trip to {destination} @parallel(false) @autodone(false)
    - Before departure @due({start_date} -50d) @autodone(true)
        - Check travel documents
    - Destination TODO @parallel(true) @autodone(true)
        - Local transit researched
        - Lodging details confirmed
    - Return TODO @parallel(true) @autodone(true)
        - Return travel confirmed
        - Post-trip admin reviewed
```

The important point is that **place-specific or scenario-specific checklist
blocks live directly in the template itself**. `ofocus` does not select them or
compose them. If a template contains a `Destination TODO` section, that section is
imported exactly as written, and you manage it manually in OmniFocus.

## Variable syntax

Placeholders use curly braces:

```text
{destination}
{start_date}
{project_name}
{due_date}
```

### Rules

- A placeholder is any `{...}` span whose content:
  - is non-empty;
  - does not contain `{`, `}`, or a newline.
- Variable names are matched **literally**.
- Variable names may contain spaces.
- Repeated placeholders are allowed.
- Placeholder discovery preserves first-seen order for human-facing output.
- Literal braces are not supported in v1.

Suggested regex:

```text
\{([^{}\n]+)\}
```

Examples:

- `Trip to {destination}` → variable name `destination`
- `Project: {project_name}:` → variable name `project_name`

## Substitution model

Substitution is pure text replacement on the full file contents.

Given:

```text
Trip to {destination}
- Leave on {start_date}
```

and:

```text
destination=Example City
start_date=2026-04-20
```

the result is:

```text
Trip to Example City
- Leave on 2026-04-20
```

### Rules

- Replacement is exact by variable name.
- `--var` parsing splits on the first `=` only.
- If a key appears multiple times on the command line, the last value wins.
- Missing variables are an error.
- There is no default value mechanism.
- There is no expression language.
- `ofocus` does not interpret dates, tags, or TaskPaper parameters during
  substitution.

## Discovery and naming

For v1, template names come from filename stems:

- `trip.taskpaper` → `trip`
- `writing.taskpaper` → `writing`

`template ls` lists those stems in sorted order.

`project from-template <template>` resolves in this order:

1. exact stem match among active top-level templates;
2. exact relative path inside `templates_dir`, with or without `.taskpaper`.

Resolution must reject paths that escape `templates_dir`.

## Validation rules

Validation is deliberately lightweight.

### Per-file checks

For each active top-level `*.taskpaper` file:

- file is readable;
- file is valid UTF-8 text;
- file is non-empty after trimming trailing whitespace-only lines;
- every placeholder matches the placeholder syntax above;
- there are no unmatched `{` or `}` characters.

### Repo-level checks

- no duplicate template stems among active templates;
- ignored directories such as `archive/` do not affect validation.

### What validation does **not** do

`template validate` does not:

- parse TaskPaper structure;
- inspect OmniFocus-specific parameters such as `@due(...)` or `@repeat-rule`;
- verify that the template imports successfully into OmniFocus;
- verify that a "Destination TODO" section is conditionally relevant.

That is an intentional design limit. The template repo remains mostly plain text
content, not a custom schema.

## Output

Human mode:

```text
Validating /path/to/templates...
  conference.taskpaper              OK
  course.taskpaper                  OK
  trip.taskpaper                    OK
Summary: 3 files, 0 errors
```

`--json`:

```json
{
  "ok": true,
  "errors": [],
  "stats": {
    "files": 3,
    "errors": 0
  }
}
```

## Implementation notes

- All helpers can live in a single `src/ofocus/templates.py` module.
- Placeholder extraction and substitution are pure functions and should be
  unit-tested without OmniFocus.
- No YAML or TaskPaper parsing dependency is needed.
- Tests should use fixture files with realistic TaskPaper content, including
  placeholders with spaces.
