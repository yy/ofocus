"""Click CLI for OmniFocus."""

import json
import re
import subprocess
import sys
from datetime import date
from typing import Any

import click

from ofocus import __version__
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

# Reusable JXA function: fuzzy-match an item from a list by ID or name.
# Returns {match: item} on unique match, {error: "ambiguous", matches: [...]}
# on multiple, or {error: "not_found"} on none.
JS_FUZZY_MATCH = """\
function fuzzyMatch(items, query) {
    var i;
    // Exact ID
    for (i = 0; i < items.length; i++) {
        if (items[i].id() === query) return {match: items[i]};
    }
    // ID prefix
    var prefixes = [];
    for (i = 0; i < items.length; i++) {
        if (items[i].id().indexOf(query) === 0) prefixes.push(items[i]);
    }
    if (prefixes.length === 1) return {match: prefixes[0]};
    if (prefixes.length > 1) return {
        error: "ambiguous",
        matches: prefixes.map(function(x) { return {id: x.id(), name: x.name()}; })
    };
    // Name substring (case-insensitive)
    var lq = query.toLowerCase();
    var names = [];
    for (i = 0; i < items.length; i++) {
        if (items[i].name().toLowerCase().indexOf(lq) !== -1) names.push(items[i]);
    }
    if (names.length === 1) return {match: names[0]};
    if (names.length > 1) return {
        error: "ambiguous",
        matches: names.map(function(x) { return {id: x.id(), name: x.name()}; })
    };
    return {error: "not_found"};
}
"""


JS_INBOX = (
    """\
"""
    + JS_LOCAL_DATE_HELPERS
    + """\
var doc = Application("OmniFocus").defaultDocument;
var tasks = doc.inboxTasks().filter(function(t) {
    return !t.completed() && !t.dropped();
}).map(function(t) {
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
)

JS_TASKS = (
    """\
"""
    + JS_LOCAL_DATE_HELPERS
    + """\
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
)

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

JS_SHOW_PROJECT = (
    """\
"""
    + JS_LOCAL_DATE_HELPERS
    + JS_FUZZY_MATCH
    + """\
var app = Application("OmniFocus");
var doc = app.defaultDocument;

function serializeTask(t) {
    var children = t.tasks();
    return {
        id: t.id(),
        name: t.name(),
        flagged: t.flagged(),
        completed: t.completed(),
        dropped: t.dropped(),
        dueDate: toLocalDateString(t.dueDate()),
        deferDate: toLocalDateString(t.deferDate()),
        note: t.note(),
        tags: t.tags().map(function(tg) { return tg.name(); }),
        sequential: children.length > 0 ? t.sequential() : false,
        children: children.map(serializeTask)
    };
}

var lookup = fuzzyMatch(doc.flattenedProjects(), "__QUERY__");
var result;
if (lookup.error === "not_found") {
    result = {error: "Project not found"};
} else if (lookup.error) {
    result = lookup;
} else {
    var proj = lookup.match;
    var s;
    try { s = proj.status(); } catch(e) { s = "active"; }
    result = {
        id: proj.id(),
        name: proj.name(),
        status: s,
        note: proj.note(),
        sequential: proj.sequential(),
        children: proj.tasks().map(serializeTask)
    };
}
JSON.stringify(result);
"""
)

# Reusable JXA: serialize a folder's subfolders and projects into a list.
JS_SERIALIZE_FOLDER_CONTENTS = """\
function serializeFolderContents(folder) {
    var children = [];
    var subfolders = folder.folders();
    for (var i = 0; i < subfolders.length; i++) {
        var sf = subfolders[i];
        var projects = sf.projects();
        var activeCount = 0;
        for (var j = 0; j < projects.length; j++) {
            var s;
            try { s = projects[j].status(); } catch(e) { s = "active"; }
            if (s === "active" || s === "active status") activeCount++;
        }
        children.push({
            type: "folder",
            id: sf.id(),
            name: sf.name(),
            projectCount: projects.length,
            activeCount: activeCount
        });
    }
    var projects = folder.projects();
    for (var i = 0; i < projects.length; i++) {
        var p = projects[i];
        var s;
        try { s = p.status(); } catch(e) { s = "active"; }
        var remaining = p.flattenedTasks().filter(function(t) {
            return !t.completed() && !t.dropped();
        }).length;
        children.push({
            type: "project",
            id: p.id(),
            name: p.name(),
            status: s,
            taskCount: remaining
        });
    }
    return children;
}
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

JS_TOP_LEVEL = """\
var doc = Application("OmniFocus").defaultDocument;
var result = [];

// Top-level folders
var folders = doc.folders();
for (var i = 0; i < folders.length; i++) {
    var f = folders[i];
    var projects = f.projects();
    var activeCount = 0;
    for (var j = 0; j < projects.length; j++) {
        var s;
        try { s = projects[j].status(); } catch(e) { s = "active"; }
        if (s === "active" || s === "active status") activeCount++;
    }
    result.push({
        type: "folder",
        id: f.id(),
        name: f.name(),
        projectCount: projects.length,
        activeCount: activeCount
    });
}

// Top-level projects (not in any folder)
var topProjects = doc.projects();
for (var i = 0; i < topProjects.length; i++) {
    var p = topProjects[i];
    var s;
    try { s = p.status(); } catch(e) { s = "active"; }
    var remaining = p.flattenedTasks().filter(function(t) {
        return !t.completed() && !t.dropped();
    }).length;
    result.push({
        type: "project",
        id: p.id(),
        name: p.name(),
        status: s,
        taskCount: remaining
    });
}

JSON.stringify(result);
"""


def _handle_error(e: OmniError):
    click.echo(f"Error: {e}", err=True)
    sys.exit(1)


def _check_ambiguous(result: dict | None, item_type: str = "items") -> None:
    """If result is an ambiguous-match error, print matches and exit."""
    if not result:
        return
    if result.get("error") == "ambiguous":
        click.echo(f"Multiple {item_type} match. Be more specific:", err=True)
        for m in result["matches"]:
            click.echo(f"  {m['id'][:8]}  {m['name']}", err=True)
        sys.exit(1)


# ── CLI ──────────────────────────────────────────────────────────────────


@click.group()
@click.version_option(version=__version__, prog_name="ofocus")
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
    app.markComplete(task);
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
@click.option("--project", default=None, help="Move to project (by project ID)")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def update(task_id, name, due, flag, note, project, as_json):
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
    if project is not None:
        _validate_task_id(project)  # same safe-char validation
        updates.append(f"""\
var projMatches = doc.flattenedProjects.whose({{id: "{_js_escape(project)}"}})();
if (projMatches.length === 0) {{ throw new Error("Project not found"); }}
projMatches[0].tasks.push(task);""")
    if not updates:
        click.echo("No updates specified.", err=True)
        sys.exit(1)
    update_code = "\n    ".join(updates)
    script = f"""\
var app = Application("OmniFocus");
var doc = app.defaultDocument;
var matches = doc.flattenedTasks.whose({{id: "{_js_escape(task_id)}"}})();
if (matches.length === 0) {{
    JSON.stringify({{error: "Task not found"}});
}} else {{
    var task = matches[0];
    {update_code}
    var proj = task.containingProject();
    JSON.stringify({{
        id: task.id(),
        name: task.name(),
        flagged: task.flagged(),
        project: proj ? proj.name() : null
    }});
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
    app.markDropped(task);
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


@cli.command("ls")
@click.argument("folder", default=None, required=False)
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def ls(folder, as_json):
    """List folders and projects. Optionally drill into a folder by name or ID."""
    if folder:
        script = (
            JS_FUZZY_MATCH
            + f"""\
var doc = Application("OmniFocus").defaultDocument;
var query = "{_js_escape(folder)}";

{JS_SERIALIZE_FOLDER_CONTENTS}

var folderLookup = fuzzyMatch(doc.flattenedFolders(), query);
var result;

if (folderLookup.match) {{
    result = {{folder: folderLookup.match.name(), children: serializeFolderContents(folderLookup.match)}};
}} else if (folderLookup.error === "ambiguous") {{
    result = folderLookup;
}} else {{
    // No folder found — try matching a project
    var projLookup = fuzzyMatch(doc.flattenedProjects(), query);
    if (projLookup.match) {{
        result = {{error: "is_project", id: projLookup.match.id(), name: projLookup.match.name()}};
    }} else if (projLookup.error === "ambiguous") {{
        result = {{error: "ambiguous_project", matches: projLookup.matches}};
    }} else {{
        result = {{error: "Not found"}};
    }}
}}

JSON.stringify(result);
"""
        )
        try:
            result = _run_jxa(script)
        except OmniError as e:
            _handle_error(e)
        _check_ambiguous(result, "folders")
        # Project fallback also returns ambiguous via "ambiguous_project" key
        if result and result.get("error") == "ambiguous_project":
            _check_ambiguous(
                {"error": "ambiguous", "matches": result["matches"]}, "projects"
            )
        if result and result.get("error") == "is_project":
            # Redirect to show command
            ctx = click.get_current_context()
            ctx.invoke(
                show,
                project=result["id"],
                show_all=False,
                available=False,
                first_available=False,
                as_json=as_json,
            )
            return
        if result and result.get("error"):
            click.echo(f"Error: {result['error']}", err=True)
            sys.exit(1)
        if as_json:
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo(f"{result['folder']}/")
            _print_ls_items(result.get("children", []))
    else:
        try:
            raw = _run_jxa(JS_TOP_LEVEL)
        except OmniError as e:
            _handle_error(e)
        if as_json:
            click.echo(json.dumps(raw, indent=2))
        else:
            _print_ls_items(raw or [])


@cli.command()
@click.argument("project")
@click.option("--all", "show_all", is_flag=True, help="Include completed/dropped tasks")
@click.option(
    "--available", is_flag=True, help="Only show available (actionable) tasks"
)
@click.option(
    "--first",
    "first_available",
    is_flag=True,
    help="Show only the first available task(s)",
)
@click.option("--json", "as_json", is_flag=True, help="Output nested JSON")
def show(project, show_all, available, first_available, as_json):
    """Show a project's tasks as a tree."""
    script = JS_SHOW_PROJECT.replace("__QUERY__", _js_escape(project))
    try:
        result = _run_jxa(script)
    except OmniError as e:
        _handle_error(e)
    if not result:
        click.echo("Error: no result from OmniFocus", err=True)
        sys.exit(1)
    _check_ambiguous(result, "projects")
    if result.get("error"):
        click.echo(f"Error: {result['error']}", err=True)
        sys.exit(1)

    if not show_all:
        result["children"] = _filter_tree(result["children"])

    if available or first_available:
        today = date.today().isoformat()
        _mark_availability(result["children"], result.get("sequential", False), today)
        if first_available:
            first_tasks = _collect_first_available(result["children"])
            if as_json:
                click.echo(json.dumps(first_tasks, indent=2))
            else:
                if not first_tasks:
                    click.echo(f"{result['name']}  — no available tasks")
                else:
                    click.echo(f"{result['name']}  — first available:")
                    for t in first_tasks:
                        click.echo(f"  {t['id'][:8]}  {_format_task_line(t)}")
            return
        result["children"] = _filter_available(result["children"])

    if as_json:
        remaining, total = _count_tasks(result["children"], count_all=True)
        result["remaining"] = remaining
        result["total"] = total
        _annotate_types(result["children"])
        click.echo(json.dumps(result, indent=2))
    else:
        remaining, total = _count_tasks(result["children"], count_all=True)
        click.echo(f"{result['name']}  ({remaining}/{total} remaining)")
        _print_tree(result["children"])


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
@click.option("--folder", default=None, help="Parent folder (name or ID)")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def project_create(name, folder, as_json):
    """Create a new project."""
    if folder:
        script = (
            JS_FUZZY_MATCH
            + f"""\
var app = Application("OmniFocus");
var doc = app.defaultDocument;
var lookup = fuzzyMatch(doc.flattenedFolders(), "{_js_escape(folder)}");
if (lookup.error === "not_found") {{
    JSON.stringify({{error: "Folder not found: {_js_escape(folder)}"}});
}} else if (lookup.error) {{
    JSON.stringify(lookup);
}} else {{
    var proj = app.Project({{name: "{_js_escape(name)}"}});
    lookup.match.projects.push(proj);
    JSON.stringify({{
        id: proj.id(),
        name: proj.name(),
        folder: lookup.match.name()
    }});
}}
"""
        )
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
    _check_ambiguous(result, "folders")
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
JXA_TIMEOUT_SECONDS = 30


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


def _print_ls_items(items: list[dict]):
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


def _mark_availability(children: list[dict], parent_sequential: bool, today: str):
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
            _mark_availability(kids, node.get("sequential", False), today)
            # A group is available if any child is available
            node["_available"] = node["_available"] and any(
                c.get("_available") for c in kids
            )

        if not node.get("completed") and not node.get("dropped"):
            found_first = True


def _filter_available(children: list[dict]) -> list[dict]:
    """Keep only available nodes."""
    filtered = []
    for node in children:
        if not node.get("_available"):
            continue
        node = dict(node)
        node["children"] = _filter_available(node.get("children", []))
        filtered.append(node)
    return filtered


def _collect_first_available(children: list[dict]) -> list[dict]:
    """Collect leaf tasks that are the first available action(s)."""
    results = []
    for node in children:
        if not node.get("_available"):
            continue
        kids = node.get("children", [])
        if kids:
            results.extend(_collect_first_available(kids))
        else:
            results.append(node)
        if results:
            break
    return results


def _filter_tree(children: list[dict]) -> list[dict]:
    """Remove completed/dropped tasks, keeping groups that have remaining children."""
    filtered = []
    for node in children:
        if node.get("completed") or node.get("dropped"):
            continue
        original_children = node.get("children", [])
        node = dict(node)
        node["children"] = _filter_tree(original_children)
        if original_children and not node["children"]:
            continue
        filtered.append(node)
    return filtered


def _count_tasks(children: list[dict], count_all: bool = False) -> tuple[int, int]:
    """Count (remaining, total) leaf tasks in the tree."""
    remaining = 0
    total = 0
    for node in children:
        kids = node.get("children", [])
        if kids:
            r, t = _count_tasks(kids, count_all=True)
            remaining += r
            total += t
        else:
            total += 1
            if not node.get("completed") and not node.get("dropped"):
                remaining += 1
    return remaining, total


def _annotate_types(children: list[dict]):
    """Add 'type' field to each node for JSON output."""
    for node in children:
        kids = node.get("children", [])
        node["type"] = "group" if kids else "task"
        _annotate_types(kids)


def _format_task_line(node: dict) -> str:
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


def _print_tree(children: list[dict], prefix: str = ""):
    """Print tree with box-drawing characters."""
    for i, node in enumerate(children):
        is_last = i == len(children) - 1
        connector = "└── " if is_last else "├── "
        click.echo(f"{prefix}{connector}{_format_task_line(node)}")
        kids = node.get("children", [])
        if kids:
            extension = "    " if is_last else "│   "
            _print_tree(kids, prefix + extension)


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
