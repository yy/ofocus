"""Task subcommand group."""

import json
import sys
from textwrap import indent

import click

from ofocus import jxa
from ofocus.helpers import (
    echo_task_list,
    js_escape,
    jxa_local_date_constructor,
    load_task_list,
    load_unique_task_list,
    open_omnifocus_task,
    run_task_lookup_or_exit,
    validate_date,
    validate_task_id,
)


@click.group(invoke_without_command=True)
@click.option(
    "--project",
    "project_filter",
    default=None,
    help="Filter by project name",
)
@click.option("--tag", default=None, help="Filter by tag name")
@click.option("--flagged", is_flag=True, help="Flagged only")
@click.option("--due-before", default=None, help="Tasks due before date (YYYY-MM-DD)")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
@click.pass_context
def task(ctx, project_filter, tag, flagged, due_before, as_json):
    """Manage tasks."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(
            ls,
            project=project_filter,
            tag=tag,
            flagged=flagged,
            due_before=due_before,
            as_json=as_json,
        )
    elif ctx.invoked_subcommand == "ls":
        ctx.default_map = ctx.default_map or {}
        ls_defaults = ctx.default_map.setdefault("ls", {})
        if project_filter is not None:
            ls_defaults["project"] = project_filter
        if tag is not None:
            ls_defaults["tag"] = tag
        if flagged:
            ls_defaults["flagged"] = flagged
        if due_before is not None:
            ls_defaults["due_before"] = due_before
        if as_json:
            ls_defaults["as_json"] = as_json


@task.command("ls")
@click.option("--project", default=None, help="Filter by project name")
@click.option("--tag", default=None, help="Filter by tag name")
@click.option("--flagged", is_flag=True, help="Flagged only")
@click.option("--due-before", default=None, help="Tasks due before date (YYYY-MM-DD)")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def ls(project, tag, flagged, due_before, as_json):
    """List active tasks."""
    task_list = load_task_list(jxa.JS_TASKS)
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
    echo_task_list(task_list, "tasks", as_json)


@task.command()
@click.argument("task_id")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def complete(task_id, as_json):
    """Mark a task as complete."""
    validate_task_id(task_id)
    result = run_task_lookup_or_exit(
        task_id,
        """\
app.markComplete(task);
JSON.stringify({id: task.id(), name: task.name(), completed: true});
""",
    )
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
@click.option("--project", default=None, help="Move to project (by name or ID)")
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
        script_prefix = jxa.JS_FUZZY_MATCH
    if not updates and project is None:
        click.echo("No updates specified.", err=True)
        sys.exit(1)
    update_code = "\n".join(updates)
    if project is not None:
        apply_updates = f"{indent(update_code, '    ')}\n" if update_code else ""
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
    result = run_task_lookup_or_exit(
        task_id,
        success_code,
        script_prefix=script_prefix,
        aliases={"ambiguous_project": "projects"},
    )
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
    result = run_task_lookup_or_exit(
        task_id,
        """\
app.markDropped(task);
JSON.stringify({id: task.id(), name: task.name(), dropped: true});
""",
    )
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
    result = run_task_lookup_or_exit(
        task_id,
        """\
var name = task.name();
var id = task.id();
app.delete(task);
JSON.stringify({id: id, name: name, deleted: true});
""",
    )
    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(f"Deleted: {result.get('name', task_id)}")


@task.command("open")
@click.argument("task_id")
def open_task(task_id):
    """Open a task in OmniFocus."""
    validate_task_id(task_id)
    result = run_task_lookup_or_exit(
        task_id,
        """\
JSON.stringify({id: task.id(), name: task.name()});
""",
    )
    open_omnifocus_task(result["id"])
    click.echo(f"Opened: {result['name']}")


@task.command()
@click.argument("query")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def search(query, as_json):
    """Search tasks by name (includes inbox and active tasks)."""
    task_list = load_unique_task_list(jxa.JS_TASKS, jxa.JS_INBOX)
    q = query.lower()
    matches = [
        t for t in task_list if q in t.name.lower() or (t.note and q in t.note.lower())
    ]
    echo_task_list(matches, "matches", as_json)
