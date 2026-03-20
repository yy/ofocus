# ofocus CLI Reference

OmniFocus CLI for macOS. Most data commands support `--json` for structured output. Requires OmniFocus running.

## Commands

### Read

```bash
ofocus inbox                                    # List inbox tasks
ofocus task ls                                  # List active tasks
ofocus task ls --project "Work"                 # Filter by project
ofocus task ls --tag "errand"                   # Filter by tag
ofocus task ls --flagged                        # Flagged only
ofocus task ls --due-before 2026-03-10          # Due before date
ofocus task search "quarterly"                  # Search name/note
ofocus project ls                               # Folder/project tree
ofocus project ls "Research"                    # Drill into folder
ofocus project show "Work"                      # Project task tree
ofocus project show "Work" --available          # Only actionable tasks
ofocus project show "Work" --first              # First available task(s)
ofocus project show "Work" --all                # Include completed/dropped
ofocus tag ls                                   # List tags
ofocus stats                                    # Counts: inbox, active, flagged, overdue
ofocus dump                                     # Full JSON export
```

### Write

```bash
ofocus inbox add "Task name"                    # Add to inbox
ofocus inbox add "Task" --note "Details" --flag # With note and flag
ofocus inbox add "Task" --due 2026-03-15        # With due date (YYYY-MM-DD)
ofocus project create "Project name"            # Create project
ofocus project create "Name" --folder "Work"    # In a folder
ofocus task complete <id>                       # Mark complete
ofocus task update <id> --name "New name"       # Rename
ofocus task update <id> --due 2026-03-20 --flag # Set due date and flag
ofocus task update <id> --no-flag               # Remove flag
ofocus task update <id> --note "Updated note"   # Set note
ofocus task update <id> --project <project_id>  # Move to project
ofocus task drop <id>                           # Drop (soft delete)
ofocus task delete <id>                         # Permanent delete
```

## Task IDs

Human output shows 8-char truncated IDs. These work as prefixes in task/project commands:

```bash
ofocus inbox --json | jq -r '.[].id'           # Get full IDs
ofocus task complete j7cpqVlu                   # Prefix works too
```

## JSON output schema

### Task

```json
{"id": "j7cpqVlu3kR", "name": "Buy milk", "flagged": false, "completed": false, "dueDate": "2026-03-15", "note": "", "project": "Errands", "tags": ["shopping"]}
```

Fields: `id`, `name`, `flagged` (bool), `completed` (bool), `dueDate` (YYYY-MM-DD or null), `note` (string), `project` (string or null, absent for inbox), `tags` (string array).

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
ofocus task ls --flagged --json
ofocus task ls --due-before $(date +%Y-%m-%d) --json

# Browse and drill into projects
ofocus project ls
ofocus project ls "Research"
ofocus project show "Paper writing" --first --json

# Capture a task from agent context
ofocus inbox add "Review PR #42 - blocking release" --flag --due 2026-03-09 --json

# Complete a task by ID
ofocus task complete j7cpqVlu3kR --json

# Find tasks related to a topic
ofocus task search "deploy" --json

# Snapshot for context
ofocus dump > /tmp/omnifocus.json
```
