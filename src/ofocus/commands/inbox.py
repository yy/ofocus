"""Inbox subcommand group."""

import click

from ofocus import jxa
from ofocus.helpers import (
    build_js_json_stringify,
    build_task_field_assignments,
    echo_action_result,
    echo_task_list,
    js_escape,
    load_task_list,
    run_jxa_or_exit,
    set_subcommand_defaults,
)


@click.group(invoke_without_command=True)
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
@click.pass_context
def inbox(ctx, as_json):
    """List or manage inbox tasks."""
    if ctx.invoked_subcommand == "add" and as_json:
        set_subcommand_defaults(ctx, "add", as_json=as_json)
        return

    if ctx.invoked_subcommand is not None:
        return
    tasks = load_task_list(jxa.JS_INBOX)
    echo_task_list(tasks, "inbox tasks", as_json)


@inbox.command("add")
@click.argument("name")
@click.option("--note", default=None, help="Task note")
@click.option("--due", default=None, help="Due date (YYYY-MM-DD)")
@click.option("--flag", is_flag=True, help="Flag the task")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def inbox_add(name, note, due, flag, as_json):
    """Add a task to the inbox."""
    assignments = build_task_field_assignments(
        note=note if note else None,
        due=due if due else None,
        flag=True if flag else None,
    )
    assignment_block = "\n".join(assignments)

    script = f"""\
var app = Application("OmniFocus");
var doc = app.defaultDocument;
var task = app.InboxTask({{name: "{js_escape(name)}"}});
doc.inboxTasks.push(task);
"""
    if assignment_block:
        script += assignment_block + "\n"
    script += build_js_json_stringify([("id", "task.id()"), ("name", "task.name()")])

    result = run_jxa_or_exit(script)
    echo_action_result(
        result,
        "Added",
        as_json=as_json,
        fallback_name=name,
        include_id=True,
    )
