"""Tag subcommand group."""

import json

import click

from ofocus import jxa
from ofocus.helpers import run_jxa_or_exit
from ofocus.models import Tag


@click.group(invoke_without_command=True)
@click.pass_context
def tag(ctx):
    """Manage tags."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(ls)


@tag.command("ls")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def ls(as_json):
    """List all tags."""
    raw = run_jxa_or_exit(jxa.JS_TAGS)
    tag_list = [Tag.from_dict(d) for d in (raw or [])]
    if as_json:
        click.echo(
            json.dumps([{"id": t.id, "name": t.name} for t in tag_list], indent=2)
        )
    else:
        click.echo(f"{len(tag_list)} tags:")
        for t in tag_list:
            click.echo(f"  {t.id[:8]}  {t.name}")
