"""Tag subcommand group."""

import click

from ofocus import jxa
from ofocus.helpers import (
    echo_item_list,
    handle_group_json_option,
    run_jxa_or_exit,
)
from ofocus.models import Tag


@click.group(invoke_without_command=True)
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
@click.pass_context
def tag(ctx, as_json):
    """Manage tags."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(ls, as_json=as_json)
        return

    handle_group_json_option(
        ctx,
        as_json=as_json,
        supported_subcommands=("ls",),
    )


@tag.command("ls")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def ls(as_json):
    """List all tags."""
    raw = run_jxa_or_exit(jxa.JS_TAGS)
    tag_list = [Tag.from_dict(d) for d in (raw or [])]
    echo_item_list(tag_list, "tags", as_json)
