"""Shared CLI helpers: validators, formatters, tree utilities."""

import re
import sys
from datetime import date
from typing import Any

import click

from ofocus.omni import OmniError

# ── Validators ──────────────────────────────────────────────────────────

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TASK_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def validate_date(value: str) -> str:
    """Validate and return a YYYY-MM-DD date string."""
    if not _DATE_RE.match(value):
        click.echo("Error: date must be YYYY-MM-DD format", err=True)
        sys.exit(1)
    try:
        date.fromisoformat(value)
    except ValueError:
        click.echo("Error: date must be a real calendar date", err=True)
        sys.exit(1)
    return value


def validate_task_id(value: str) -> str:
    """Validate that a task ID contains only safe characters."""
    if not _TASK_ID_RE.match(value):
        click.echo("Error: invalid task ID format", err=True)
        sys.exit(1)
    return value


def js_escape(s: str) -> str:
    """Escape a string for embedding in JavaScript."""
    return (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("'", "\\'")
        .replace("`", "\\`")
        .replace("$", "\\$")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\0", "\\0")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def jxa_local_date_constructor(value: str) -> str:
    """Return a JXA Date constructor that preserves the local calendar date."""
    parsed = date.fromisoformat(validate_date(value))
    return f"new Date({parsed.year}, {parsed.month - 1}, {parsed.day})"


# ── Error handling ──────────────────────────────────────────────────────


def handle_error(e: OmniError):
    click.echo(f"Error: {e}", err=True)
    sys.exit(1)


def run_jxa_or_exit(script: str) -> Any | None:
    """Run JXA and exit cleanly with a CLI error if OmniFocus fails."""
    from ofocus import jxa

    try:
        return jxa.run_jxa(script)
    except OmniError as e:
        handle_error(e)


def check_ambiguous(
    result: dict | None,
    item_type: str = "items",
    aliases: dict[str, str] | None = None,
) -> None:
    """If result is an ambiguous-match error, print matches and exit."""
    if not result:
        return
    error = result.get("error")
    if error == "ambiguous":
        matched_item_type = item_type
    elif aliases and error in aliases:
        matched_item_type = aliases[error]
    else:
        return

    click.echo(f"Multiple {matched_item_type} match. Be more specific:", err=True)
    for m in result["matches"]:
        click.echo(f"  {m['id'][:8]}  {m['name']}", err=True)
    sys.exit(1)


def check_result_error(result: dict | None) -> None:
    """If result contains a generic error, print it and exit."""
    if result and result.get("error"):
        click.echo(f"Error: {result['error']}", err=True)
        sys.exit(1)


# ── Display helpers ─────────────────────────────────────────────────────


def print_ls_items(items: list[dict]):
    """Print folder/project items from ls command."""
    for item in items:
        if item["type"] == "folder":
            active = item["activeCount"]
            total = item["projectCount"]
            click.echo(
                "  "
                f"{item['id'][:8]}  {item['name']}/  "
                f"({active}/{total} projects active)"
            )
        else:
            status = (
                f" ({item['status']})"
                if item["status"] not in ("active", "active status")
                else ""
            )
            click.echo(
                "  "
                f"{item['id'][:8]}  {item['name']}  "
                f"({item['taskCount']} tasks){status}"
            )


# ── Tree helpers ────────────────────────────────────────────────────────


def mark_availability(children: list[dict], parent_sequential: bool, today: str):
    """Mark each node with '_available' based on sequential ordering and defer dates."""
    found_first = False
    for node in children:
        # Completed/dropped tasks are never available
        if node.get("completed") or node.get("dropped"):
            node["_available"] = False
            continue
        # Deferred if defer date is in the future
        deferred = bool(node.get("deferDate") and node["deferDate"] > today)
        # In sequential parent, only the first remaining child is available
        blocked_by_sequence = parent_sequential and found_first
        node["_available"] = not deferred and not blocked_by_sequence

        kids = node.get("children", [])
        if kids:
            mark_availability(kids, node.get("sequential", False), today)
            # A group is available if any child is available
            node["_available"] = node["_available"] and any(
                c.get("_available") for c in kids
            )

        if not node.get("completed") and not node.get("dropped"):
            found_first = True


def filter_available(children: list[dict]) -> list[dict]:
    """Keep only available nodes."""
    filtered = []
    for node in children:
        if not node.get("_available"):
            continue
        node = dict(node)
        node["children"] = filter_available(node.get("children", []))
        filtered.append(node)
    return filtered


def collect_first_available(children: list[dict]) -> list[dict]:
    """Collect leaf tasks that are the first available action(s)."""
    results = []
    for node in children:
        if not node.get("_available"):
            continue
        kids = node.get("children", [])
        if kids:
            results.extend(collect_first_available(kids))
        else:
            results.append(node)
        if results:
            break
    return results


def filter_tree(children: list[dict]) -> list[dict]:
    """Remove completed/dropped tasks, keeping groups that have remaining children."""
    filtered = []
    for node in children:
        if node.get("completed") or node.get("dropped"):
            continue
        original_children = node.get("children", [])
        node = dict(node)
        node["children"] = filter_tree(original_children)
        if original_children and not node["children"]:
            continue
        filtered.append(node)
    return filtered


def count_tasks(children: list[dict], count_all: bool = False) -> tuple[int, int]:
    """Count (remaining, total) leaf tasks in the tree."""
    remaining = 0
    total = 0
    for node in children:
        kids = node.get("children", [])
        if kids:
            r, t = count_tasks(kids, count_all=True)
            remaining += r
            total += t
        else:
            total += 1
            if not node.get("completed") and not node.get("dropped"):
                remaining += 1
    return remaining, total


def annotate_types(children: list[dict]):
    """Add 'type' field to each node for JSON output."""
    for node in children:
        kids = node.get("children", [])
        node["type"] = "group" if kids else "task"
        annotate_types(kids)


def strip_internal_fields(children: list[dict]):
    """Remove internal helper fields from tree nodes before JSON output."""
    for node in children:
        node.pop("_available", None)
        strip_internal_fields(node.get("children", []))


def format_task_line(node: dict) -> str:
    """Format a single task node with decorators."""
    parts = []
    if node.get("completed"):
        parts.append("✓")
    elif node.get("dropped"):
        parts.append("✗")
    parts.append(node["name"])
    if node.get("flagged"):
        parts.append("⚑")
    if node.get("dueDate"):
        parts.append(f"(due {node['dueDate']})")
    tags = node.get("tags", [])
    if tags:
        parts.append(" ".join(f"#{t}" for t in tags))
    return " ".join(parts)


def print_tree(children: list[dict], prefix: str = ""):
    """Print tree with box-drawing characters."""
    for i, node in enumerate(children):
        is_last = i == len(children) - 1
        connector = "└── " if is_last else "├── "
        click.echo(f"{prefix}{connector}{format_task_line(node)}")
        kids = node.get("children", [])
        if kids:
            extension = "    " if is_last else "│   "
            print_tree(kids, prefix + extension)
