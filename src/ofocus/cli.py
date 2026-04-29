"""Click CLI for OmniFocus."""

import click

from ofocus import __version__, jxa
from ofocus.commands.inbox import inbox
from ofocus.commands.project import project
from ofocus.commands.tag import tag
from ofocus.commands.task import task
from ofocus.helpers import echo_json, run_jxa_or_exit

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
    result = run_jxa_or_exit(jxa.JS_STATS)
    if as_json:
        echo_json(result)
    else:
        click.echo(f"Inbox:    {result['inbox']}")
        click.echo(f"Active:   {result['active']}")
        click.echo(f"Flagged:  {result['flagged']}")
        click.echo(f"Overdue:  {result['overdue']}")
        click.echo(f"Projects: {result['projects']}")
        click.echo(f"Tags:     {result['tags']}")


# ── Dump ─────────────────────────────────────────────────────────────────


@cli.command()
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def dump(as_json):
    """Full JSON dump of all active tasks, projects, tags."""
    del as_json  # `dump` is always JSON, but accept the flag for CLI consistency.
    tasks_raw = run_jxa_or_exit(jxa.JS_TASKS)
    projects_raw = run_jxa_or_exit(jxa.JS_PROJECTS)
    tags_raw = run_jxa_or_exit(jxa.JS_TAGS)
    inbox_raw = run_jxa_or_exit(jxa.JS_INBOX)
    folders_raw = run_jxa_or_exit(jxa.JS_FOLDERS)
    result = {
        "inbox": inbox_raw or [],
        "tasks": tasks_raw or [],
        "projects": projects_raw or [],
        "tags": tags_raw or [],
        "folders": folders_raw or [],
    }
    echo_json(result)


# ── Usage ────────────────────────────────────────────────────────────────


@cli.command()
def usage():
    """Print CLI reference for humans and AI agents."""
    from importlib.resources import files

    text = files("ofocus").joinpath("USAGE.md").read_text()
    click.echo(text)
