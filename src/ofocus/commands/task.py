"""Task subcommand group."""

import sys
from textwrap import indent

import click

from ofocus import jxa
from ofocus.helpers import (
    build_js_json_stringify,
    build_task_action_success_code,
    build_task_field_assignments,
    build_task_result_stringify,
    echo_action_result,
    echo_task_list,
    js_escape,
    load_task_list,
    load_unique_task_list,
    open_omnifocus_item,
    run_task_lookup_or_exit,
    set_subcommand_defaults,
    validate_date,
    validate_task_id,
)


def _run_task_action(
    task_id: str,
    success_code: str,
    *,
    script_prefix: str = "",
    aliases: dict[str, str] | None = None,
) -> dict:
    """Resolve a task ID/prefix and run an action script against the match."""
    validate_task_id(task_id)
    return run_task_lookup_or_exit(
        task_id,
        success_code,
        script_prefix=script_prefix,
        aliases=aliases,
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
        return

    if ctx.invoked_subcommand == "ls":
        set_subcommand_defaults(
            ctx,
            "ls",
            project=project_filter,
            tag=tag,
            flagged=flagged,
            due_before=due_before,
            as_json=as_json,
        )
        return

    misused_filters = []
    if project_filter is not None:
        misused_filters.append("--project")
    if tag is not None:
        misused_filters.append("--tag")
    if flagged:
        misused_filters.append("--flagged")
    if due_before is not None:
        misused_filters.append("--due-before")
    if misused_filters:
        options = ", ".join(misused_filters)
        raise click.UsageError(
            f"{options} can only be used with `ofocus task ls` or bare `ofocus task`."
        )

    if as_json and ctx.invoked_subcommand == "open":
        raise click.UsageError("`--json` is not supported by `ofocus task open`.")

    if as_json and ctx.invoked_subcommand in {
        "complete",
        "update",
        "drop",
        "delete",
        "search",
    }:
        set_subcommand_defaults(ctx, ctx.invoked_subcommand, as_json=True)


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
    result = _run_task_action(
        task_id,
        build_task_action_success_code(
            "app.markComplete(task);",
            result_fields=[("completed", "true")],
        ),
    )
    echo_action_result(result, "Completed", as_json=as_json, fallback_name=task_id)


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
    updates = build_task_field_assignments(
        name=name,
        due=due,
        flag=flag,
        note=note,
    )
    script_prefix = ""
    if project is not None:
        script_prefix = jxa.JS_FUZZY_MATCH
    if not updates and project is None:
        click.echo("No updates specified.", err=True)
        sys.exit(1)
    update_code = "\n".join(updates)
    task_result = build_task_result_stringify(
        [
            ("flagged", "task.flagged()"),
            ("project", "proj ? proj.name() : null"),
        ]
    )
    if project is not None:
        apply_updates = f"{indent(update_code, '    ')}\n" if update_code else ""
        success_code = f"""\
var projLookup = fuzzyMatch(doc.flattenedProjects, "{js_escape(project)}");
if (projLookup.error === "not_found") {{
    JSON.stringify({{error: "Project not found"}});
}} else if (projLookup.error === "ambiguous") {{
    JSON.stringify({{error: "ambiguous_project", matches: projLookup.matches}});
}} else {{
    var moveScript = '(() => {{ const t = Task.byIdentifier("' + task.id()
        + '"); const p = Project.byIdentifier("' + projLookup.match.id()
        + '"); moveTasks([t], p); }})()';
    app.evaluateJavascript(moveScript);
{apply_updates}    var proj = task.containingProject();
    {task_result}
}}"""
    else:
        success_code = f"""\
{update_code}
var proj = task.containingProject();
{task_result}"""
    result = _run_task_action(
        task_id,
        success_code,
        script_prefix=script_prefix,
        aliases={"ambiguous_project": "projects"},
    )
    echo_action_result(result, "Updated", as_json=as_json, fallback_name=task_id)


@task.command()
@click.argument("task_id")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def drop(task_id, as_json):
    """Drop (mark as dropped) a task."""
    result = _run_task_action(
        task_id,
        build_task_action_success_code(
            "app.markDropped(task);",
            result_fields=[("dropped", "true")],
        ),
    )
    echo_action_result(result, "Dropped", as_json=as_json, fallback_name=task_id)


@task.command()
@click.argument("task_id")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def delete(task_id, as_json):
    """Delete a task permanently."""
    result = _run_task_action(
        task_id,
        "\n".join(
            [
                "var name = task.name();",
                "var id = task.id();",
                "app.delete(task);",
                build_js_json_stringify(
                    [("id", "id"), ("name", "name"), ("deleted", "true")]
                ),
            ]
        ),
    )
    echo_action_result(result, "Deleted", as_json=as_json, fallback_name=task_id)


@task.command("open")
@click.argument("task_id")
def open_task(task_id):
    """Open a task in OmniFocus."""
    result = _run_task_action(
        task_id,
        build_task_result_stringify(),
    )
    open_omnifocus_item(result["id"])
    echo_action_result(result, "Opened", as_json=False, fallback_name=task_id)


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
