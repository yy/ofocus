"""Task subcommand group."""

import json
import sys

import click

from ofocus import jxa
from ofocus.helpers import (
    check_ambiguous,
    check_result_error,
    handle_error,
    js_escape,
    jxa_local_date_constructor,
    validate_date,
    validate_task_id,
)
from ofocus.models import Task
from ofocus.omni import OmniError


@click.group(invoke_without_command=True)
@click.pass_context
def task(ctx):
    """Manage tasks."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(ls)


@task.command("ls")
@click.option("--project", default=None, help="Filter by project name")
@click.option("--tag", default=None, help="Filter by tag name")
@click.option("--flagged", is_flag=True, help="Flagged only")
@click.option("--due-before", default=None, help="Tasks due before date (YYYY-MM-DD)")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def ls(project, tag, flagged, due_before, as_json):
    """List active tasks."""
    try:
        raw = jxa.run_jxa(jxa.JS_TASKS)
    except OmniError as e:
        handle_error(e)
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
        due_before = validate_date(due_before)
        task_list = [
            t for t in task_list if t.due_date and t.due_date[:10] <= due_before
        ]
    if as_json:
        click.echo(json.dumps([t.to_dict() for t in task_list], indent=2))
    else:
        click.echo(f"{len(task_list)} tasks:")
        for t in task_list:
            click.echo(f"  {t.id[:8]}  {t.to_line()}")


@task.command()
@click.argument("task_id")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def complete(task_id, as_json):
    """Mark a task as complete."""
    validate_task_id(task_id)
    script = f"""\
var app = Application("OmniFocus");
var doc = app.defaultDocument;
var query = "{js_escape(task_id)}";
var all = doc.flattenedTasks();
var matches = all.filter(function(t) {{
    return t.id() === query;
}});
if (matches.length === 0) {{
    matches = all.filter(function(t) {{
        return t.id().indexOf(query) === 0;
    }});
}}
if (matches.length === 0) {{
    JSON.stringify({{error: "Task not found"}});
}} else if (matches.length > 1) {{
    JSON.stringify({{
        error: "ambiguous",
        matches: matches.map(function(t) {{
            return {{id: t.id(), name: t.name()}};
        }})
    }});
}} else {{
    var task = matches[0];
    app.markComplete(task);
    JSON.stringify({{id: task.id(), name: task.name(), completed: true}});
}}
"""
    try:
        result = jxa.run_jxa(script)
    except OmniError as e:
        handle_error(e)
    check_ambiguous(result, "tasks")
    check_result_error(result)
    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(f"Completed: {result.get('name', task_id)}")


@task.command()
@click.argument("task_id")
@click.option("--name", default=None, help="New name")
@click.option("--due", default=None, help="New due date (YYYY-MM-DD)")
@click.option("--flag/--no-flag", default=None, help="Set/unset flag")
@click.option("--note", default=None, help="Set note")
@click.option("--project", default=None, help="Move to project (by project ID)")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def update(task_id, name, due, flag, note, project, as_json):
    """Update a task."""
    validate_task_id(task_id)
    updates = []
    script_prefix = ""
    if name is not None:
        updates.append(f'task.name = "{js_escape(name)}";')
    if due is not None:
        updates.append(f"task.dueDate = {jxa_local_date_constructor(due)};")
    if flag is not None:
        updates.append(f"task.flagged = {'true' if flag else 'false'};")
    if note is not None:
        updates.append(f'task.note = "{js_escape(note)}";')
    if project is not None:
        validate_task_id(project)
        script_prefix = jxa.JS_FUZZY_MATCH
    if not updates and project is None:
        click.echo("No updates specified.", err=True)
        sys.exit(1)
    update_code = "\n    ".join(updates)
    if project is not None:
        apply_updates = f"    {update_code}\n" if update_code else ""
        success_code = f"""\
var projLookup = fuzzyMatch(doc.flattenedProjects(), "{js_escape(project)}");
    if (projLookup.error === "not_found") {{
        JSON.stringify({{error: "Project not found"}});
    }} else if (projLookup.error === "ambiguous") {{
        JSON.stringify({{error: "ambiguous_project", matches: projLookup.matches}});
    }} else {{
        projLookup.match.tasks.push(task);
{apply_updates}    var proj = task.containingProject();
        JSON.stringify({{
            id: task.id(),
            name: task.name(),
            flagged: task.flagged(),
            project: proj ? proj.name() : null
        }});
    }}"""
    else:
        success_code = f"""\
{update_code}
    var proj = task.containingProject();
    JSON.stringify({{
        id: task.id(),
        name: task.name(),
        flagged: task.flagged(),
        project: proj ? proj.name() : null
    }});"""
    script = f"""\
{script_prefix}\
var app = Application("OmniFocus");
var doc = app.defaultDocument;
var query = "{js_escape(task_id)}";
var all = doc.flattenedTasks();
var matches = all.filter(function(t) {{
    return t.id() === query;
}});
if (matches.length === 0) {{
    matches = all.filter(function(t) {{
        return t.id().indexOf(query) === 0;
    }});
}}
if (matches.length === 0) {{
    JSON.stringify({{error: "Task not found"}});
}} else if (matches.length > 1) {{
    JSON.stringify({{
        error: "ambiguous",
        matches: matches.map(function(t) {{
            return {{id: t.id(), name: t.name()}};
        }})
    }});
}} else {{
    var task = matches[0];
    {success_code}
}}
"""
    try:
        result = jxa.run_jxa(script)
    except OmniError as e:
        handle_error(e)
    check_ambiguous(result, "tasks")
    if result and result.get("error") == "ambiguous_project":
        check_ambiguous(
            {"error": "ambiguous", "matches": result["matches"]}, "projects"
        )
    check_result_error(result)
    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(f"Updated: {result.get('name', task_id)}")


@task.command()
@click.argument("task_id")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def drop(task_id, as_json):
    """Drop (mark as dropped) a task."""
    validate_task_id(task_id)
    script = f"""\
var app = Application("OmniFocus");
var doc = app.defaultDocument;
var query = "{js_escape(task_id)}";
var all = doc.flattenedTasks();
var matches = all.filter(function(t) {{
    return t.id() === query;
}});
if (matches.length === 0) {{
    matches = all.filter(function(t) {{
        return t.id().indexOf(query) === 0;
    }});
}}
if (matches.length === 0) {{
    JSON.stringify({{error: "Task not found"}});
}} else if (matches.length > 1) {{
    JSON.stringify({{
        error: "ambiguous",
        matches: matches.map(function(t) {{
            return {{id: t.id(), name: t.name()}};
        }})
    }});
}} else {{
    var task = matches[0];
    app.markDropped(task);
    JSON.stringify({{id: task.id(), name: task.name(), dropped: true}});
}}
"""
    try:
        result = jxa.run_jxa(script)
    except OmniError as e:
        handle_error(e)
    check_ambiguous(result, "tasks")
    check_result_error(result)
    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(f"Dropped: {result.get('name', task_id)}")


@task.command()
@click.argument("task_id")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def delete(task_id, as_json):
    """Delete a task permanently."""
    validate_task_id(task_id)
    script = f"""\
var app = Application("OmniFocus");
var doc = app.defaultDocument;
var query = "{js_escape(task_id)}";
var all = doc.flattenedTasks();
var matches = all.filter(function(t) {{
    return t.id() === query;
}});
if (matches.length === 0) {{
    matches = all.filter(function(t) {{
        return t.id().indexOf(query) === 0;
    }});
}}
if (matches.length === 0) {{
    JSON.stringify({{error: "Task not found"}});
}} else if (matches.length > 1) {{
    JSON.stringify({{
        error: "ambiguous",
        matches: matches.map(function(t) {{
            return {{id: t.id(), name: t.name()}};
        }})
    }});
}} else {{
    var task = matches[0];
    var name = task.name();
    var id = task.id();
    app.delete(task);
    JSON.stringify({{id: id, name: name, deleted: true}});
}}
"""
    try:
        result = jxa.run_jxa(script)
    except OmniError as e:
        handle_error(e)
    check_ambiguous(result, "tasks")
    check_result_error(result)
    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(f"Deleted: {result.get('name', task_id)}")


@task.command("open")
@click.argument("task_id")
def open_task(task_id):
    """Open a task in OmniFocus."""
    validate_task_id(task_id)
    script = f"""\
var app = Application("OmniFocus");
var doc = app.defaultDocument;
var query = "{js_escape(task_id)}";
var all = doc.flattenedTasks();
var matches = all.filter(function(t) {{ return t.id() === query; }});
if (matches.length === 0) {{
    matches = all.filter(function(t) {{ return t.id().indexOf(query) === 0; }});
}}
if (matches.length === 0) {{
    JSON.stringify({{error: "Task not found"}});
}} else if (matches.length > 1) {{
    JSON.stringify({{
        error: "ambiguous",
        matches: matches.map(function(t) {{ return {{id: t.id(), name: t.name()}}; }})
    }});
}} else {{
    JSON.stringify({{id: matches[0].id(), name: matches[0].name()}});
}}
"""
    try:
        result = jxa.run_jxa(script)
    except OmniError as e:
        handle_error(e)
    check_ambiguous(result, "tasks")
    check_result_error(result)
    import subprocess

    try:
        subprocess.run(["open", f"omnifocus:///task/{result['id']}"], check=True)
    except subprocess.CalledProcessError as e:
        click.echo(f"Error: failed to open OmniFocus URL: {e}", err=True)
        sys.exit(1)
    click.echo(f"Opened: {result['name']}")


@task.command()
@click.argument("query")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def search(query, as_json):
    """Search tasks by name (includes inbox and active tasks)."""
    try:
        raw_tasks = jxa.run_jxa(jxa.JS_TASKS)
        raw_inbox = jxa.run_jxa(jxa.JS_INBOX)
    except OmniError as e:
        handle_error(e)
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
