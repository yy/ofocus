"""Project subcommand group."""

import json
import sys
from datetime import date

import click

from ofocus import jxa
from ofocus.helpers import (
    annotate_types,
    build_folder_or_project_lookup_script,
    build_fuzzy_lookup_script,
    build_item_result_stringify,
    check_ambiguous,
    check_result_error,
    count_tasks,
    echo_action_result,
    format_task_line,
    handle_group_json_option,
    js_escape,
    open_omnifocus_item,
    prepare_project_children,
    print_ls_items,
    print_tree,
    run_jxa_or_exit,
    strip_internal_fields,
)


@click.group(invoke_without_command=True)
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
@click.pass_context
def project(ctx, as_json):
    """Manage projects."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(ls, folder=None, as_json=as_json)
        return

    handle_group_json_option(
        ctx,
        as_json=as_json,
        supported_subcommands=("ls", "show", "create"),
        unsupported_subcommands=("open",),
    )


@project.command("ls")
@click.argument("folder", default=None, required=False)
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def ls(folder, as_json):
    """List folders and projects. Optionally drill into a folder by name or ID."""
    if folder:
        script = build_folder_or_project_lookup_script(folder)
        result = run_jxa_or_exit(script)
        check_ambiguous(
            result,
            "folders",
            aliases={"ambiguous_project": "projects"},
        )
        if result and result.get("error") == "is_project":
            # Redirect to show command
            ctx = click.get_current_context()
            ctx.invoke(
                show,
                project=result["id"],
                show_all=False,
                available=False,
                first_available=False,
                as_json=as_json,
            )
            return
        check_result_error(result)
        if as_json:
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo(f"{result['folder']}/")
            print_ls_items(result.get("children", []))
    else:
        raw = run_jxa_or_exit(jxa.JS_TOP_LEVEL)
        if as_json:
            click.echo(json.dumps(raw, indent=2))
        else:
            print_ls_items(raw or [])


@project.command()
@click.argument("project")
@click.option("--all", "show_all", is_flag=True, help="Include completed/dropped tasks")
@click.option(
    "--available", is_flag=True, help="Only show available (actionable) tasks"
)
@click.option(
    "--first",
    "first_available",
    is_flag=True,
    help="Show only the first available task(s)",
)
@click.option("--json", "as_json", is_flag=True, help="Output nested JSON")
def show(project, show_all, available, first_available, as_json):
    """Show a project's tasks as a tree."""
    script = jxa.JS_SHOW_PROJECT.replace("__QUERY__", js_escape(project))
    result = run_jxa_or_exit(script)
    if not result:
        click.echo("Error: no result from OmniFocus", err=True)
        sys.exit(1)
    check_ambiguous(result, "projects")
    check_result_error(result)

    children = prepare_project_children(
        result["children"],
        parent_sequential=result.get("sequential", False),
        show_all=show_all,
        available_only=available,
        first_available_only=first_available,
        today=date.today().isoformat(),
    )

    if first_available:
        if not as_json:
            if not children:
                click.echo(f"{result['name']}  — no available tasks")
            else:
                click.echo(f"{result['name']}  — first available:")
                for task_node in children:
                    line = format_task_line(task_node)
                    click.echo(f"  {task_node['id'][:8]}  {line}")
            return

    if as_json:
        response = dict(result)
        response["children"] = children
        remaining, total = count_tasks(children)
        response["remaining"] = remaining
        response["total"] = total
        strip_internal_fields(response["children"])
        annotate_types(response["children"])
        click.echo(json.dumps(response, indent=2))
    else:
        remaining, total = count_tasks(children)
        click.echo(f"{result['name']}  ({remaining}/{total} remaining)")
        print_tree(children)


@project.command("open")
@click.argument("project")
def open_project(project):
    """Open a project in OmniFocus."""
    script = build_fuzzy_lookup_script(
        project,
        "doc.flattenedProjects",
        build_item_result_stringify(),
        item_var="item",
        not_found_error="Project not found",
    )
    result = run_jxa_or_exit(script)
    check_ambiguous(result, "projects")
    check_result_error(result)
    open_omnifocus_item(result["id"], item_type="project")
    echo_action_result(result, "Opened", as_json=False, fallback_name=project)


@project.command()
@click.argument("name")
@click.option("--folder", default=None, help="Parent folder (name or ID)")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def create(name, folder, as_json):
    """Create a new project."""
    if folder:
        folder_result = build_item_result_stringify(
            [("folder", "item.name()")],
            target="proj",
        )
        script = build_fuzzy_lookup_script(
            folder,
            "doc.flattenedFolders",
            f"""\
var proj = app.Project({{name: "{js_escape(name)}"}});
item.projects.push(proj);
{folder_result}
""",
            item_var="item",
            not_found_error=f"Folder not found: {folder}",
        )
    else:
        project_result = build_item_result_stringify(target="proj")
        script = f"""\
var app = Application("OmniFocus");
var doc = app.defaultDocument;
var proj = app.Project({{name: "{js_escape(name)}"}});
doc.projects.push(proj);
{project_result}
"""
    result = run_jxa_or_exit(script)
    check_ambiguous(result, "folders")
    check_result_error(result)
    echo_action_result(
        result,
        "Created project",
        as_json=as_json,
        fallback_name=name,
        include_id=True,
    )
