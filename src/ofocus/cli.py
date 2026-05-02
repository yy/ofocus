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


_DUMP_SCRIPT_SEQUENCE = (
    ("tasks", jxa.JS_TASKS),
    ("projects", jxa.JS_PROJECTS),
    ("tags", jxa.JS_TAGS),
    ("inbox", jxa.JS_INBOX),
    ("folders", jxa.JS_FOLDERS),
)
_DUMP_OUTPUT_ORDER = ("inbox", "tasks", "projects", "tags", "folders")


def _load_dump_payload() -> dict[str, list]:
    """Load all dump sections while preserving the CLI's JSON output order."""
    loaded = {
        section: run_jxa_or_exit(script) or []
        for section, script in _DUMP_SCRIPT_SEQUENCE
    }
    return {section: loaded[section] for section in _DUMP_OUTPUT_ORDER}


@cli.command()
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def dump(as_json):
    """Full JSON dump of all active tasks, projects, tags."""
    del as_json  # `dump` is always JSON, but accept the flag for CLI consistency.
    echo_json(_load_dump_payload())


# ── Usage ────────────────────────────────────────────────────────────────


@cli.command()
def usage():
    """Print CLI reference for humans and AI agents."""
    from importlib.resources import files

    text = files("ofocus").joinpath("USAGE.md").read_text()
    click.echo(text)
