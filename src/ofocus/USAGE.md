# ofocus CLI Reference

OmniFocus CLI for macOS. All commands support `--json` for structured output. Requires OmniFocus running.

## Commands

### Read

```bash
ofocus inbox                              # List inbox tasks
ofocus tasks                              # List active tasks
ofocus tasks --project "Work"             # Filter by project
ofocus tasks --tag "errand"               # Filter by tag
ofocus tasks --flagged                    # Flagged only
ofocus tasks --due-before 2026-03-10      # Due before date
ofocus search "quarterly"                 # Search name/note (inbox + active)
ofocus projects                           # List projects
ofocus projects --folder "Work"           # Filter by folder
ofocus tags                               # List tags
ofocus stats                              # Counts: inbox, active, flagged, overdue
ofocus dump                               # Full JSON export
```

### Write

```bash
ofocus inbox add "Task name"                        # Add to inbox
ofocus inbox add "Task" --note "Details" --flag      # With note and flag
ofocus inbox add "Task" --due 2026-03-15             # With due date (YYYY-MM-DD)
ofocus project-create "Project name"                 # Create project
ofocus project-create "Name" --folder "Work"         # In a folder
ofocus complete <id>                                 # Mark complete
ofocus update <id> --name "New name"                 # Rename
ofocus update <id> --due 2026-03-20 --flag           # Set due date and flag
ofocus update <id> --no-flag                         # Remove flag
ofocus update <id> --note "Updated note"             # Set note
ofocus update <id> --project <project_id>            # Move to project
ofocus drop <id>                                     # Drop (soft delete)
ofocus delete <id>                                   # Permanent delete
```

## Task IDs

Human output shows 8-char truncated IDs. Use `--json` to get full IDs:

```bash
ofocus inbox --json | jq -r '.[].id'
```

## JSON output schema

### Task

```json
{"id": "j7cpqVlu3kR", "name": "Buy milk", "flagged": false, "completed": false, "dueDate": "2026-03-15T00:00:00.000Z", "note": "", "project": "Errands", "tags": ["shopping"]}
```

Fields: `id`, `name`, `flagged` (bool), `completed` (bool), `dueDate` (ISO 8601 or null), `note` (string), `project` (string or null, absent for inbox), `tags` (string array).

### Project

```json
{"id": "p1abc", "name": "Work", "status": "active", "taskCount": 5, "folder": "Main", "note": ""}
```

### Stats

```json
{"inbox": 3, "active": 42, "projects": 8, "tags": 12, "flagged": 5, "overdue": 2}
```

## Common agent workflows

```bash
# Morning review: what needs attention?
ofocus stats --json
ofocus tasks --flagged --json
ofocus tasks --due-before $(date +%Y-%m-%d) --json

# Capture a task from agent context
ofocus inbox add "Review PR #42 — blocking release" --flag --due 2026-03-09 --json

# Complete a task by ID
ofocus complete j7cpqVlu3kR --json

# Find tasks related to a topic
ofocus search "deploy" --json

# Snapshot for context
ofocus dump > /tmp/omnifocus.json
```
