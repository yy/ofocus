"""Shared CLI helpers: validators, formatters, tree utilities."""

import json
import re
import sys
from datetime import date
from textwrap import indent
from typing import Any

import click

from ofocus.models import Task
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


def build_task_field_assignments(
    *,
    target: str = "task",
    name: str | None = None,
    due: str | None = None,
    flag: bool | None = None,
    note: str | None = None,
) -> list[str]:
    """Build JXA assignment statements for common task fields."""
    assignments = []
    if name is not None:
        assignments.append(f'{target}.name = "{js_escape(name)}";')
    if due is not None:
        assignments.append(
            f"{target}.dueDate = {jxa_local_date_constructor(due)};"
        )
    if flag is not None:
        assignments.append(f"{target}.flagged = {'true' if flag else 'false'};")
    if note is not None:
        assignments.append(f'{target}.note = "{js_escape(note)}";')
    return assignments


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


def load_task_list(script: str) -> list[Task]:
    """Run a task-list JXA script and parse the results into Task objects."""
    raw = run_jxa_or_exit(script)
    return [Task.from_dict(d) for d in (raw or [])]


def load_unique_task_list(*scripts: str) -> list[Task]:
    """Load tasks from multiple scripts, keeping only the first item per ID."""
    seen: set[str] = set()
    tasks = []
    for script in scripts:
        for task in load_task_list(script):
            if task.id in seen:
                continue
            seen.add(task.id)
            tasks.append(task)
    return tasks


def echo_task_list(tasks: list[Task], label: str, as_json: bool) -> None:
    """Render a task collection using the CLI's standard text or JSON format."""
    if as_json:
        click.echo(json.dumps([task.to_dict() for task in tasks], indent=2))
        return

    click.echo(f"{len(tasks)} {label}:")
    for task in tasks:
        click.echo(f"  {task.id[:8]}  {task.to_line()}")


def set_subcommand_defaults(
    ctx: click.Context, subcommand: str, **defaults: Any
) -> None:
    """Merge non-empty defaults into Click's default_map for a subcommand."""
    filtered_defaults = {
        key: value
        for key, value in defaults.items()
        if value is not None and value is not False
    }
    if not filtered_defaults:
        return

    ctx.default_map = ctx.default_map or {}
    ctx.default_map.setdefault(subcommand, {}).update(filtered_defaults)


def echo_action_result(
    result: dict[str, Any],
    action: str,
    *,
    as_json: bool,
    fallback_name: str | None = None,
    include_id: bool = False,
) -> None:
    """Render a single-item command result using the standard text/JSON formats."""
    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    name = result.get("name", fallback_name or "?")
    if include_id:
        click.echo(f"{action}: {name} ({result.get('id', '?')[:8]})")
        return

    click.echo(f"{action}: {name}")


def build_task_lookup_script(
    task_id: str,
    success_code: str,
    *,
    script_prefix: str = "",
) -> str:
    """Build a JXA script that resolves a task by exact ID or unique prefix."""
    from ofocus import jxa

    return (
        script_prefix
        + jxa.JS_FIND_TASK_BY_ID
        + f"""\
var app = Application("OmniFocus");
var doc = app.defaultDocument;
var query = "{js_escape(task_id)}";
var lookup = findTaskById(doc, query);
if (lookup.error) {{
    JSON.stringify(lookup);
}} else {{
    var task = lookup.match;
{indent(success_code.rstrip(), "    ")}
}}
"""
    )


def build_fuzzy_lookup_script(
    query: str,
    collection_expr: str,
    success_code: str,
    *,
    item_var: str = "item",
    not_found_error: str,
    script_prefix: str = "",
) -> str:
    """Build a JXA script that fuzzy-matches an item and runs success code."""
    from ofocus import jxa

    return (
        script_prefix
        + jxa.JS_FUZZY_MATCH
        + f"""\
var app = Application("OmniFocus");
var doc = app.defaultDocument;
var lookup = fuzzyMatch({collection_expr}, "{js_escape(query)}");
if (lookup.error === "not_found") {{
    JSON.stringify({{error: "{js_escape(not_found_error)}"}});
}} else if (lookup.error) {{
    JSON.stringify(lookup);
}} else {{
    var {item_var} = lookup.match;
{indent(success_code.rstrip(), "    ")}
}}
"""
    )


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


def run_task_lookup_or_exit(
    task_id: str,
    success_code: str,
    *,
    script_prefix: str = "",
    aliases: dict[str, str] | None = None,
) -> dict:
    """Run a task lookup script and exit cleanly on ambiguous or error results."""
    result = run_jxa_or_exit(
        build_task_lookup_script(
            task_id,
            success_code,
            script_prefix=script_prefix,
        )
    )
    check_ambiguous(result, "tasks", aliases=aliases)
    check_result_error(result)
    return result or {}


def open_omnifocus_item(item_id: str) -> None:
    """Open an OmniFocus item by ID via the app URL scheme."""
    import subprocess

    try:
        subprocess.run(["open", f"omnifocus:///task/{item_id}"], check=True)
    except subprocess.CalledProcessError as e:
        click.echo(f"Error: failed to open OmniFocus URL: {e}", err=True)
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


def collect_first_available(
    children: list[dict], parent_sequential: bool = False
) -> list[dict]:
    """Collect first available leaf tasks, respecting sequential parents."""
    results = []
    for node in children:
        if not node.get("_available"):
            continue
        kids = node.get("children", [])
        if kids:
            results.extend(
                collect_first_available(
                    kids, parent_sequential=node.get("sequential", False)
                )
            )
        else:
            results.append(node)
        if parent_sequential and results:
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


def count_tasks(children: list[dict]) -> tuple[int, int]:
    """Count (remaining, total) leaf tasks in the tree."""
    remaining = 0
    total = 0
    for node in children:
        kids = node.get("children", [])
        if kids:
            r, t = count_tasks(kids)
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
