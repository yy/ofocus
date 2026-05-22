"""Inbox subcommand group."""

import click

from ofocus import jxa
from ofocus.helpers import (
    build_omnifocus_doc_script,
    build_task_field_assignments,
    build_task_result_stringify,
    echo_action_result,
    echo_task_list,
    handle_group_json_option,
    js_escape,
    load_task_list,
    run_jxa_or_exit,
)


def _build_inbox_add_script(
    name: str,
    *,
    note: str | None = None,
    due: str | None = None,
    flag: bool = False,
) -> str:
    """Build the JXA script for adding a task to the inbox."""
    assignments = build_task_field_assignments(
        note=note if note else None,
        due=due,
        flag=True if flag else None,
    )
    assignment_block = "\n".join(assignments)

    script = build_omnifocus_doc_script(
        f"""\
var task = app.InboxTask({{name: "{js_escape(name)}"}});
doc.inboxTasks.push(task);
"""
    )
    if assignment_block:
        script += assignment_block + "\n"
    script += build_task_result_stringify()
    return script


@click.group(invoke_without_command=True)
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
@click.pass_context
def inbox(ctx, as_json):
    """List or manage inbox tasks."""
    if handle_group_json_option(
        ctx,
        as_json=as_json,
        supported_subcommands=("add",),
    ):
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
    script = _build_inbox_add_script(name, note=note, due=due, flag=flag)
    result = run_jxa_or_exit(script)
    echo_action_result(
        result,
        "Added",
        as_json=as_json,
        fallback_name=name,
        include_id=True,
    )
