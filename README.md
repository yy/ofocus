# ofocus

A command-line interface for [OmniFocus](https://www.omnigroup.com/omnifocus) on macOS. Read and write tasks, projects, and tags directly from your terminal — or let AI agents (Claude Code, MCP servers, etc.) work with OmniFocus.

ofocus talks to OmniFocus through JXA (JavaScript for Automation) via `osascript` — no plugins, no server, no API keys. If OmniFocus is running, ofocus works.

## Install

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```bash
# From source
git clone https://github.com/yy/ofocus.git
cd ofocus
uv sync

# Run directly
uv run ofocus --help
```

## Quick start

```bash
# What's on my plate?
ofocus stats

# Check the inbox
ofocus inbox

# Add something to the inbox
ofocus inbox add "Buy coffee beans" --flag
ofocus inbox add "Read paper" --due 2026-03-15 --note "The one from Alice"

# Browse projects and folders
ofocus project ls
ofocus project ls "Research"
ofocus project show "Paper writing"
ofocus project show "Paper writing" --first    # First available task

# Find tasks across inbox and projects
ofocus task search "quarterly"

# List active tasks, optionally filtered
ofocus task ls
ofocus task ls --project "Work" --flagged
ofocus task ls --tag "errand" --due-before 2026-03-10

# Mark done, update, or drop
ofocus task complete j7cpqVlu
ofocus task update j7cpqVlu --name "Buy good coffee beans" --flag
ofocus task drop j7cpqVlu

# Create a project
ofocus project create "Q2 Planning" --folder "Work"
```

## Commands

| Command | Description |
|---|---|
| `ofocus inbox` | List inbox tasks |
| `ofocus inbox add "name"` | Add task to inbox (`--note`, `--due`, `--flag`) |
| `ofocus task ls` | List active tasks (`--project`, `--tag`, `--flagged`, `--due-before`) |
| `ofocus task search "query"` | Search by name/note across inbox and active tasks |
| `ofocus task complete <id>` | Mark a task complete |
| `ofocus task update <id>` | Update a task (`--name`, `--due`, `--flag`/`--no-flag`, `--note`, `--project`) |
| `ofocus task drop <id>` | Drop a task |
| `ofocus task delete <id>` | Permanently delete a task |
| `ofocus project ls [folder]` | Browse folders and projects (drill into subfolders) |
| `ofocus project show <project>` | Show project tasks as a tree (`--available`, `--first`, `--all`) |
| `ofocus project create "name"` | Create a project (`--folder`) |
| `ofocus tag ls` | List all tags |
| `ofocus stats` | Quick counts (inbox, active, flagged, overdue) |
| `ofocus dump` | Full JSON dump of everything |

Most data commands support `--json` for machine-readable output. Bare `ofocus task` and `ofocus project` default to their `ls` subcommand.

## JSON mode

Commands that return task/project/tag/stat data accept `--json` to output structured JSON instead of human-readable text. This makes ofocus composable with other tools:

```bash
# Pipe flagged tasks to jq
ofocus task ls --flagged --json | jq '.[].name'

# Get task IDs for scripting
ofocus inbox --json | jq -r '.[].id'

# Full database export
ofocus dump > omnifocus-backup.json
```

## Task IDs

Human output shows truncated 8-character IDs for readability. These work as prefixes in task/project commands:

```bash
$ ofocus inbox
  j7cpqVlu  Buy coffee beans

$ ofocus task complete j7cpqVlu
Completed: Buy coffee beans
```

## Use with Claude Code and AI agents

The `--json` flag on every command makes ofocus a natural tool for Claude Code, MCP servers, and other AI agents that need to read or manage OmniFocus tasks programmatically. Agents can list tasks, create new ones, mark them complete, and search — all through structured JSON over stdin/stdout.

```bash
# An agent can check what's overdue
ofocus task ls --due-before 2026-03-08 --json

# Browse project structure
ofocus project show "Paper writing" --first --json

# Add a task from an agent workflow
ofocus inbox add "Follow up on PR review" --due 2026-03-10 --json

# Dump everything for context
ofocus dump
```

## How it works

ofocus constructs JXA scripts and runs them via `osascript -l JavaScript`. Each command builds a small JavaScript snippet that talks to `Application("OmniFocus")`, executes it as a subprocess, and parses the JSON output. No AppleScript, no Shortcuts, no network calls.

## Requirements

- macOS (uses `osascript`)
- OmniFocus 3 or 4
- Python 3.13+

## Development

```bash
uv sync                        # Install deps
uv run pytest                  # Run tests
uv run ruff check src/ tests/  # Lint
uv run ofocus stats            # Smoke test (needs OmniFocus running)
```

## License

MIT
