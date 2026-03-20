"""Inbox subcommand group."""

import json

import click

from ofocus import jxa
from ofocus.helpers import handle_error, js_escape, jxa_local_date_constructor
from ofocus.models import Task
from ofocus.omni import OmniError


@click.group(invoke_without_command=True)
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
@click.pass_context
def inbox(ctx, as_json):
    """List or manage inbox tasks."""
    if ctx.invoked_subcommand is not None:
        return
    try:
        raw = jxa.run_jxa(jxa.JS_INBOX)
    except OmniError as e:
        handle_error(e)
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
var task = app.InboxTask({{name: "{js_escape(name)}"}});
doc.inboxTasks.push(task);
"""
    if note:
        script += f'task.note = "{js_escape(note)}";\n'
    if flag:
        script += "task.flagged = true;\n"
    if due:
        script += f"task.dueDate = {jxa_local_date_constructor(due)};\n"
    script += "JSON.stringify({id: task.id(), name: task.name()});"

    try:
        result = jxa.run_jxa(script)
    except OmniError as e:
        handle_error(e)
    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(f"Added: {result.get('name', name)} ({result.get('id', '?')[:8]})")
