"""Click CLI for OmniFocus."""

import json
import re
import subprocess
import sys
from datetime import date
from typing import Any

import click

from ofocus.models import Project, Tag, Task
from ofocus.omni import OmniError

# ── JS snippets ──────────────────────────────────────────────────────────


JS_LOCAL_DATE_HELPERS = """\
function toLocalDateString(d) {
    if (!d) return null;
    var year = d.getFullYear();
    var month = String(d.getMonth() + 1).padStart(2, "0");
    var day = String(d.getDate()).padStart(2, "0");
    return year + "-" + month + "-" + day;
}
"""


JS_INBOX = """\
""" + JS_LOCAL_DATE_HELPERS + """\
var doc = Application("OmniFocus").defaultDocument;
var tasks = doc.inboxTasks().map(function(t) {
    var tags = t.tags().map(function(tg) { return tg.name(); });
    return {
        id: t.id(),
        name: t.name(),
        flagged: t.flagged(),
        completed: t.completed(),
        dueDate: toLocalDateString(t.dueDate()),
        note: t.note(),
        tags: tags
    };
});
JSON.stringify(tasks);
"""

JS_TASKS = """\
""" + JS_LOCAL_DATE_HELPERS + """\
var doc = Application("OmniFocus").defaultDocument;
var tasks = doc.flattenedTasks().filter(function(t) {
    return !t.completed() && !t.dropped();
}).map(function(t) {
    var tags = t.tags().map(function(tg) { return tg.name(); });
    var proj = t.containingProject();
    return {
        id: t.id(),
        name: t.name(),
        flagged: t.flagged(),
        completed: false,
        dueDate: toLocalDateString(t.dueDate()),
        note: t.note(),
        project: proj ? proj.name() : null,
        tags: tags
    };
});
JSON.stringify(tasks);
"""

JS_PROJECTS = """\
var doc = Application("OmniFocus").defaultDocument;
var projects = doc.flattenedProjects().map(function(p) {
    var s;
    try { s = p.status(); } catch(e) { s = "active"; }
    var f = p.folder();
    return {
        id: p.id(),
        name: p.name(),
        status: s,
        taskCount: p.flattenedTasks().length,
        folder: f ? f.name() : null,
        note: p.note()
    };
});
JSON.stringify(projects);
"""

JS_TAGS = """\
var doc = Application("OmniFocus").defaultDocument;
var tags = doc.flattenedTags().map(function(t) {
    return { id: t.id(), name: t.name() };
});
JSON.stringify(tags);
"""

JS_FOLDERS = """\
var doc = Application("OmniFocus").defaultDocument;
var folders = doc.flattenedFolders().map(function(f) {
    return {
        id: f.id(),
        name: f.name(),
        projectCount: f.projects().length
    };
});
JSON.stringify(folders);
"""


def _handle_error(e: OmniError):
    click.echo(f"Error: {e}", err=True)
    sys.exit(1)


# ── CLI ──────────────────────────────────────────────────────────────────


@click.group()
@click.version_option(version="0.1.1", prog_name="ofocus")
def cli():
    """OmniFocus CLI via OmniAutomation."""


# ── Inbox ────────────────────────────────────────────────────────────────


@cli.group(invoke_without_command=True)
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
@click.pass_context
def inbox(ctx, as_json):
    """List or manage inbox tasks."""
    if ctx.invoked_subcommand is not None:
        return
    try:
        raw = _run_jxa(JS_INBOX)
    except OmniError as e:
        _handle_error(e)
    tasks = [Task.from_dict(d) for d in (raw or [])]
    if as_json:
        click.echo(json.dumps([t.to_dict() for t in tasks], indent=2))
    else:
        click.echo(f"{len(tasks)} inbox tasks:")
        for t in tasks:
            click.echo(f"  {t.id[:8]}  {t.to_line()}")


@inbox.command("add")
@click.argument("name")
@click.option("--note", default=None, help="Task note")
@click.option("--due", default=None, help="Due date (YYYY-MM-DD)")
@click.option("--flag", is_flag=True, help="Flag the task")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def inbox_add(name, note, due, flag, as_json):
    """Add a task to the inbox."""
    script = f"""\
var app = Application("OmniFocus");
var doc = app.defaultDocument;
var task = app.InboxTask({{name: "{_js_escape(name)}"}});
doc.inboxTasks.push(task);
"""
    if note:
        script += f'task.note = "{_js_escape(note)}";\n'
    if flag:
        script += "task.flagged = true;\n"
    if due:
        script += f"task.dueDate = {_jxa_local_date_constructor(due)};\n"
    script += "JSON.stringify({id: task.id(), name: task.name()});"

    try:
        result = _run_jxa(script)
    except OmniError as e:
        _handle_error(e)
    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(f"Added: {result.get('name', name)} ({result.get('id', '?')[:8]})")


# ── Tasks ────────────────────────────────────────────────────────────────


@cli.command()
@click.option("--project", default=None, help="Filter by project name")
@click.option("--tag", default=None, help="Filter by tag name")
@click.option("--flagged", is_flag=True, help="Flagged only")
@click.option("--due-before", default=None, help="Tasks due before date (YYYY-MM-DD)")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def tasks(project, tag, flagged, due_before, as_json):
    """List active tasks."""
    try:
        raw = _run_jxa(JS_TASKS)
    except OmniError as e:
        _handle_error(e)
    task_list = [Task.from_dict(d) for d in (raw or [])]
    if project:
        task_list = [
            t for t in task_list if t.project and project.lower() in t.project.lower()
        ]
    if tag:
        task_list = [
            t for t in task_list if any(tag.lower() in tg.lower() for tg in t.tags)
        ]
    if flagged:
        task_list = [t for t in task_list if t.flagged]
    if due_before:
        due_before = _validate_date(due_before)
        task_list = [
            t for t in task_list if t.due_date and t.due_date[:10] <= due_before
        ]
    if as_json:
        click.echo(json.dumps([t.to_dict() for t in task_list], indent=2))
    else:
        click.echo(f"{len(task_list)} tasks:")
        for t in task_list:
            click.echo(f"  {t.id[:8]}  {t.to_line()}")


# ── Complete ─────────────────────────────────────────────────────────────


@cli.command()
@click.argument("task_id")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def complete(task_id, as_json):
    """Mark a task as complete."""
    _validate_task_id(task_id)
    script = f"""\
var app = Application("OmniFocus");
var doc = app.defaultDocument;
var matches = doc.flattenedTasks.whose({{id: "{_js_escape(task_id)}"}})();
if (matches.length === 0) {{
    JSON.stringify({{error: "Task not found"}});
}} else {{
    var task = matches[0];
    task.completed = true;
    JSON.stringify({{id: task.id(), name: task.name(), completed: true}});
}}
"""
    try:
        result = _run_jxa(script)
    except OmniError as e:
        _handle_error(e)
    if result and result.get("error"):
        click.echo(f"Error: {result['error']}", err=True)
        sys.exit(1)
    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(f"Completed: {result.get('name', task_id)}")


# ── Update ───────────────────────────────────────────────────────────────


@cli.command()
@click.argument("task_id")
@click.option("--name", default=None, help="New name")
@click.option("--due", default=None, help="New due date (YYYY-MM-DD)")
@click.option("--flag/--no-flag", default=None, help="Set/unset flag")
@click.option("--note", default=None, help="Set note")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def update(task_id, name, due, flag, note, as_json):
    """Update a task."""
    _validate_task_id(task_id)
    updates = []
    if name is not None:
        updates.append(f'task.name = "{_js_escape(name)}";')
    if due is not None:
        updates.append(f"task.dueDate = {_jxa_local_date_constructor(due)};")
    if flag is not None:
        updates.append(f"task.flagged = {'true' if flag else 'false'};")
    if note is not None:
        updates.append(f'task.note = "{_js_escape(note)}";')
    if not updates:
        click.echo("No updates specified.", err=True)
        sys.exit(1)
    update_code = "\n".join(updates)
    script = f"""\
var app = Application("OmniFocus");
var doc = app.defaultDocument;
var matches = doc.flattenedTasks.whose({{id: "{_js_escape(task_id)}"}})();
if (matches.length === 0) {{
    JSON.stringify({{error: "Task not found"}});
}} else {{
    var task = matches[0];
    {update_code}
    JSON.stringify({{id: task.id(), name: task.name(), flagged: task.flagged()}});
}}
"""
    try:
        result = _run_jxa(script)
    except OmniError as e:
        _handle_error(e)
    if result and result.get("error"):
        click.echo(f"Error: {result['error']}", err=True)
        sys.exit(1)
    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(f"Updated: {result.get('name', task_id)}")


# ── Drop ─────────────────────────────────────────────────────────────────


@cli.command()
@click.argument("task_id")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def drop(task_id, as_json):
    """Drop (mark as dropped) a task."""
    _validate_task_id(task_id)
    script = f"""\
var app = Application("OmniFocus");
var doc = app.defaultDocument;
var matches = doc.flattenedTasks.whose({{id: "{_js_escape(task_id)}"}})();
if (matches.length === 0) {{
    JSON.stringify({{error: "Task not found"}});
}} else {{
    var task = matches[0];
    task.dropped = true;
    JSON.stringify({{id: task.id(), name: task.name(), dropped: true}});
}}
"""
    try:
        result = _run_jxa(script)
    except OmniError as e:
        _handle_error(e)
    if result and result.get("error"):
        click.echo(f"Error: {result['error']}", err=True)
        sys.exit(1)
    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(f"Dropped: {result.get('name', task_id)}")


# ── Delete ───────────────────────────────────────────────────────────────


@cli.command()
@click.argument("task_id")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def delete(task_id, as_json):
    """Delete a task permanently."""
    _validate_task_id(task_id)
    script = f"""\
var app = Application("OmniFocus");
var doc = app.defaultDocument;
var matches = doc.flattenedTasks.whose({{id: "{_js_escape(task_id)}"}})();
if (matches.length === 0) {{
    JSON.stringify({{error: "Task not found"}});
}} else {{
    var task = matches[0];
    var name = task.name();
    var id = task.id();
    app.delete(task);
    JSON.stringify({{id: id, name: name, deleted: true}});
}}
"""
    try:
        result = _run_jxa(script)
    except OmniError as e:
        _handle_error(e)
    if result and result.get("error"):
        click.echo(f"Error: {result['error']}", err=True)
        sys.exit(1)
    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(f"Deleted: {result.get('name', task_id)}")


# ── Projects ─────────────────────────────────────────────────────────────


@cli.command()
@click.option("--folder", default=None, help="Filter by folder name")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def projects(folder, as_json):
    """List projects."""
    try:
        raw = _run_jxa(JS_PROJECTS)
    except OmniError as e:
        _handle_error(e)
    proj_list = [Project.from_dict(d) for d in (raw or [])]
    if folder:
        proj_list = [
            p for p in proj_list if p.folder and folder.lower() in p.folder.lower()
        ]
    if as_json:
        click.echo(json.dumps([p.to_dict() for p in proj_list], indent=2))
    else:
        click.echo(f"{len(proj_list)} projects:")
        for p in proj_list:
            click.echo(f"  {p.id[:8]}  {p.to_line()}")


# ── Project Create ───────────────────────────────────────────────────────


@cli.command("project-create")
@click.argument("name")
@click.option("--folder", default=None, help="Parent folder name")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def project_create(name, folder, as_json):
    """Create a new project."""
    if folder:
        script = f"""\
var app = Application("OmniFocus");
var doc = app.defaultDocument;
var folders = doc.flattenedFolders.whose({{name: "{_js_escape(folder)}"}})();
if (folders.length === 0) {{
    JSON.stringify({{error: "Folder not found: {_js_escape(folder)}"}});
}} else {{
    var proj = app.Project({{name: "{_js_escape(name)}"}});
    folders[0].projects.push(proj);
    JSON.stringify({{id: proj.id(), name: proj.name(), folder: folders[0].name()}});
}}
"""
    else:
        script = f"""\
var app = Application("OmniFocus");
var doc = app.defaultDocument;
var proj = app.Project({{name: "{_js_escape(name)}"}});
doc.projects.push(proj);
JSON.stringify({{id: proj.id(), name: proj.name()}});
"""
    try:
        result = _run_jxa(script)
    except OmniError as e:
        _handle_error(e)
    if result and result.get("error"):
        click.echo(f"Error: {result['error']}", err=True)
        sys.exit(1)
    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(
            f"Created project: {result.get('name', name)} ({result.get('id', '?')[:8]})"
        )


# ── Tags ─────────────────────────────────────────────────────────────────


@cli.command()
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def tags(as_json):
    """List all tags."""
    try:
        raw = _run_jxa(JS_TAGS)
    except OmniError as e:
        _handle_error(e)
    tag_list = [Tag.from_dict(d) for d in (raw or [])]
    if as_json:
        click.echo(
            json.dumps([{"id": t.id, "name": t.name} for t in tag_list], indent=2)
        )
    else:
        click.echo(f"{len(tag_list)} tags:")
        for t in tag_list:
            click.echo(f"  {t.id[:8]}  {t.name}")


# ── Search ───────────────────────────────────────────────────────────────


@cli.command()
@click.argument("query")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def search(query, as_json):
    """Search tasks by name (includes inbox and active tasks)."""
    try:
        raw_tasks = _run_jxa(JS_TASKS)
        raw_inbox = _run_jxa(JS_INBOX)
    except OmniError as e:
        _handle_error(e)
    seen = set()
    task_list = []
    for d in (raw_tasks or []) + (raw_inbox or []):
        if d["id"] not in seen:
            seen.add(d["id"])
            task_list.append(Task.from_dict(d))
    q = query.lower()
    matches = [
        t for t in task_list if q in t.name.lower() or (t.note and q in t.note.lower())
    ]
    if as_json:
        click.echo(json.dumps([t.to_dict() for t in matches], indent=2))
    else:
        click.echo(f"{len(matches)} matches:")
        for t in matches:
            click.echo(f"  {t.id[:8]}  {t.to_line()}")


# ── Stats ────────────────────────────────────────────────────────────────


@cli.command()
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def stats(as_json):
    """Show quick counts."""
    script = """\
var app = Application("OmniFocus");
var doc = app.defaultDocument;
var inbox = doc.inboxTasks().length;
var active = doc.flattenedTasks().filter(function(t) {
    return !t.completed() && !t.dropped();
}).length;
var projects = doc.flattenedProjects().length;
var tags = doc.flattenedTags().length;
var flagged = doc.flattenedTasks().filter(function(t) {
    return t.flagged() && !t.completed() && !t.dropped();
}).length;
var overdue = doc.flattenedTasks().filter(function(t) {
    if (t.completed() || t.dropped()) return false;
    var d = t.dueDate();
    return d && d < new Date();
}).length;
JSON.stringify({
    inbox: inbox,
    active: active,
    projects: projects,
    tags: tags,
    flagged: flagged,
    overdue: overdue
});
"""
    try:
        result = _run_jxa(script)
    except OmniError as e:
        _handle_error(e)
    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(f"Inbox:    {result['inbox']}")
        click.echo(f"Active:   {result['active']}")
        click.echo(f"Flagged:  {result['flagged']}")
        click.echo(f"Overdue:  {result['overdue']}")
        click.echo(f"Projects: {result['projects']}")
        click.echo(f"Tags:     {result['tags']}")


# ── Dump ─────────────────────────────────────────────────────────────────


@cli.command()
def dump():
    """Full JSON dump of all active tasks, projects, tags."""
    try:
        tasks_raw = _run_jxa(JS_TASKS)
        projects_raw = _run_jxa(JS_PROJECTS)
        tags_raw = _run_jxa(JS_TAGS)
        inbox_raw = _run_jxa(JS_INBOX)
        folders_raw = _run_jxa(JS_FOLDERS)
    except OmniError as e:
        _handle_error(e)
    result = {
        "inbox": inbox_raw or [],
        "tasks": tasks_raw or [],
        "projects": projects_raw or [],
        "tags": tags_raw or [],
        "folders": folders_raw or [],
    }
    click.echo(json.dumps(result, indent=2))


# ── Usage ────────────────────────────────────────────────────────────────


@cli.command()
def usage():
    """Print CLI reference for humans and AI agents."""
    from importlib.resources import files

    text = files("ofocus").joinpath("USAGE.md").read_text()
    click.echo(text)


# ── Helpers ──────────────────────────────────────────────────────────────

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TASK_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
JXA_TIMEOUT_SECONDS = 15


def _validate_date(value: str) -> str:
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


def _validate_task_id(value: str) -> str:
    """Validate that a task ID contains only safe characters."""
    if not _TASK_ID_RE.match(value):
        click.echo("Error: invalid task ID format", err=True)
        sys.exit(1)
    return value


def _js_escape(s: str) -> str:
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


def _jxa_local_date_constructor(value: str) -> str:
    """Return a JXA Date constructor that preserves the local calendar date."""
    parsed = date.fromisoformat(_validate_date(value))
    return f"new Date({parsed.year}, {parsed.month - 1}, {parsed.day})"


def _run_jxa(script: str) -> Any | None:
    """Run a JXA (not OmniAutomation) script and parse JSON result."""
    try:
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", script],
            capture_output=True,
            text=True,
            check=True,
            timeout=JXA_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as e:
        raise OmniError(
            f"JXA error: command timed out after {JXA_TIMEOUT_SECONDS} seconds"
        ) from e
    except subprocess.CalledProcessError as e:
        raise OmniError(f"JXA error: {e.stderr.strip() or e.stdout.strip()}") from e

    stdout = result.stdout.strip()
    if not stdout:
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        raise OmniError(f"Failed to parse JXA output: {stdout!r}")
