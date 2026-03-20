# Spec: `ofocus show` command

## Summary

Add `ofocus show <project>` to display a project's tasks as a tree, preserving OmniFocus's nested task group (action group) hierarchy. This gives a quick structural overview of a project and makes it easy to pick the next task to work on.

## Motivation

`ofocus tasks --project X` returns a flat list with no hierarchy. OmniFocus projects can contain nested action groups (task groups containing subtasks), and that structure is lost. A tree view makes it immediately clear what's a group vs. a leaf task, what's done, and what's next.

## Command interface

```
ofocus show <project_name_or_id> [--all] [--json]
```

**Arguments:**
- `project_name_or_id` — project name (substring match, case-insensitive) or full project ID

**Options:**
- `--all` — include completed/dropped tasks (default: only remaining tasks)
- `--json` — output the tree as nested JSON instead of ASCII art

## Tree output format

```
My Project  (3/7 remaining)
├── Buy supplies  ⚑
├── Phase 1
│   ├── Draft outline
│   ├── Write intro  (due 2026-03-25)
│   └── Review  #waiting
└── Phase 2
    ├── ✓ Set up repo
    └── Final check
```

**Decorators** (appended to task name):
- `⚑` — flagged
- `(due YYYY-MM-DD)` — has a due date
- `#tag1 #tag2` — tags
- `✓` prefix — completed (only shown with `--all`)
- `✗` prefix — dropped (only shown with `--all`)

**Header line:** `Project Name  (N/M remaining)` where N = remaining tasks, M = total tasks (leaf tasks only, not counting groups themselves).

## JSON output (`--json`)

```json
{
  "id": "abc123",
  "name": "My Project",
  "status": "active",
  "note": "...",
  "remaining": 3,
  "total": 7,
  "children": [
    {
      "id": "def456",
      "name": "Buy supplies",
      "type": "task",
      "flagged": true,
      "completed": false,
      "dropped": false,
      "dueDate": null,
      "note": null,
      "tags": [],
      "children": []
    },
    {
      "id": "ghi789",
      "name": "Phase 1",
      "type": "group",
      "flagged": false,
      "completed": false,
      "dropped": false,
      "dueDate": null,
      "note": null,
      "tags": [],
      "children": [
        { "...": "nested tasks" }
      ]
    }
  ]
}
```

The `type` field is `"task"` for leaf tasks and `"group"` for action groups (tasks that contain children).

## Project lookup

1. Try exact ID match first (`flattenedProjects.whose({id: value})`)
2. Fall back to case-insensitive substring match on project name
3. If multiple projects match by name, list them and exit with an error asking the user to be more specific

## JXA implementation notes

The key challenge is extracting the hierarchy. OmniFocus's JXA API provides:
- `project.tasks()` — top-level children of the project
- `task.tasks()` — children of a task (action group)
- `task.tasks().length > 0` — distinguishes groups from leaf tasks

Use a recursive function in JXA to walk the tree:

```javascript
function serializeTask(t) {
    var children = t.tasks();
    return {
        id: t.id(),
        name: t.name(),
        flagged: t.flagged(),
        completed: t.completed(),
        dropped: t.dropped(),
        dueDate: toLocalDateString(t.dueDate()),
        note: t.note(),
        tags: t.tags().map(function(tg) { return tg.name(); }),
        children: children.map(serializeTask)
    };
}
```

Call `project.tasks().map(serializeTask)` to get the full tree. The `--all` filtering (hiding completed/dropped) happens Python-side after receiving the full tree, so the JXA script stays simple.

## Python-side rendering

A recursive function renders the tree with box-drawing characters:

```python
def _render_tree(children, prefix="", is_last_list=None):
    for i, child in enumerate(children):
        is_last = (i == len(children) - 1)
        connector = "└── " if is_last else "├── "
        # ... render name with decorators
        # recurse into child["children"] with updated prefix
```

## Changes required

| File | Change |
|------|--------|
| `cli.py` | Add `show` command, JXA script with recursive tree extraction, tree renderer |
| `models.py` | No changes needed (tree nodes stay as dicts, not new dataclasses) |

## Edge cases

- **Empty project** — print header with `(0/0 remaining)`, no tree
- **Deeply nested groups** — OmniFocus allows arbitrary nesting; the recursive approach handles this naturally
- **Project not found** — error message and exit code 1
- **Ambiguous name match** — list matching projects with IDs so user can pick
