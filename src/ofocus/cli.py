"""Click CLI for OmniFocus."""

import json

import click

from ofocus import __version__, jxa
from ofocus.commands.inbox import inbox
from ofocus.commands.project import project
from ofocus.commands.tag import tag
from ofocus.commands.task import task
from ofocus.helpers import handle_error
from ofocus.omni import OmniError

# ── CLI ──────────────────────────────────────────────────────────────────


@click.group()
@click.version_option(version=__version__, prog_name="ofocus")
def cli():
    """OmniFocus CLI."""


cli.add_command(inbox)
cli.add_command(task)
cli.add_command(project)
cli.add_command(tag)


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
        result = jxa.run_jxa(script)
    except OmniError as e:
        handle_error(e)
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
        tasks_raw = jxa.run_jxa(jxa.JS_TASKS)
        projects_raw = jxa.run_jxa(jxa.JS_PROJECTS)
        tags_raw = jxa.run_jxa(jxa.JS_TAGS)
        inbox_raw = jxa.run_jxa(jxa.JS_INBOX)
        folders_raw = jxa.run_jxa(jxa.JS_FOLDERS)
    except OmniError as e:
        handle_error(e)
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
