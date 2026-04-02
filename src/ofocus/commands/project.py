"""Project subcommand group."""

import json
import sys
from datetime import date

import click

from ofocus import jxa
from ofocus.helpers import (
    annotate_types,
    check_ambiguous,
    check_result_error,
    collect_first_available,
    count_tasks,
    filter_available,
    filter_tree,
    format_task_line,
    js_escape,
    mark_availability,
    open_omnifocus_task,
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
    elif ctx.invoked_subcommand == "ls" and as_json:
        ctx.default_map = ctx.default_map or {}
        ctx.default_map.setdefault("ls", {})["as_json"] = as_json


@project.command("ls")
@click.argument("folder", default=None, required=False)
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def ls(folder, as_json):
    """List folders and projects. Optionally drill into a folder by name or ID."""
    if folder:
        script = (
            jxa.JS_FUZZY_MATCH
            + f"""\
var doc = Application("OmniFocus").defaultDocument;
var query = "{js_escape(folder)}";

{jxa.JS_SERIALIZE_FOLDER_CONTENTS}

var folderLookup = fuzzyMatch(doc.flattenedFolders(), query);
var result;

if (folderLookup.match) {{
    result = {{
        folder: folderLookup.match.name(),
        children: serializeFolderContents(folderLookup.match)
    }};
}} else if (folderLookup.error === "ambiguous") {{
    result = folderLookup;
}} else {{
    // No folder found — try matching a project
    var projLookup = fuzzyMatch(doc.flattenedProjects(), query);
    if (projLookup.match) {{
        result = {{
            error: "is_project",
            id: projLookup.match.id(),
            name: projLookup.match.name()
        }};
    }} else if (projLookup.error === "ambiguous") {{
        result = {{error: "ambiguous_project", matches: projLookup.matches}};
    }} else {{
        result = {{error: "Folder not found"}};
    }}
}}

JSON.stringify(result);
"""
        )
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

    if not show_all:
        result["children"] = filter_tree(result["children"])

    if available or first_available:
        today = date.today().isoformat()
        mark_availability(result["children"], result.get("sequential", False), today)
        if first_available:
            first_tasks = collect_first_available(result["children"])
            if as_json:
                strip_internal_fields(first_tasks)
                click.echo(json.dumps(first_tasks, indent=2))
            else:
                if not first_tasks:
                    click.echo(f"{result['name']}  — no available tasks")
                else:
                    click.echo(f"{result['name']}  — first available:")
                    for t in first_tasks:
                        click.echo(f"  {t['id'][:8]}  {format_task_line(t)}")
            return
        result["children"] = filter_available(result["children"])

    if as_json:
        remaining, total = count_tasks(result["children"])
        result["remaining"] = remaining
        result["total"] = total
        strip_internal_fields(result["children"])
        annotate_types(result["children"])
        click.echo(json.dumps(result, indent=2))
    else:
        remaining, total = count_tasks(result["children"])
        click.echo(f"{result['name']}  ({remaining}/{total} remaining)")
        print_tree(result["children"])


@project.command("open")
@click.argument("project")
def open_project(project):
    """Open a project in OmniFocus."""
    script = (
        jxa.JS_FUZZY_MATCH
        + f"""\
var doc = Application("OmniFocus").defaultDocument;
var lookup = fuzzyMatch(doc.flattenedProjects(), "{js_escape(project)}");
if (lookup.error === "not_found") {{
    JSON.stringify({{error: "Project not found"}});
}} else if (lookup.error) {{
    JSON.stringify(lookup);
}} else {{
    JSON.stringify({{id: lookup.match.id(), name: lookup.match.name()}});
}}
"""
    )
    result = run_jxa_or_exit(script)
    check_ambiguous(result, "projects")
    check_result_error(result)
    open_omnifocus_task(result["id"])
    click.echo(f"Opened: {result['name']}")


@project.command()
@click.argument("name")
@click.option("--folder", default=None, help="Parent folder (name or ID)")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def create(name, folder, as_json):
    """Create a new project."""
    if folder:
        script = (
            jxa.JS_FUZZY_MATCH
            + f"""\
var app = Application("OmniFocus");
var doc = app.defaultDocument;
var lookup = fuzzyMatch(doc.flattenedFolders(), "{js_escape(folder)}");
if (lookup.error === "not_found") {{
    JSON.stringify({{error: "Folder not found: {js_escape(folder)}"}});
}} else if (lookup.error) {{
    JSON.stringify(lookup);
}} else {{
    var proj = app.Project({{name: "{js_escape(name)}"}});
    lookup.match.projects.push(proj);
    JSON.stringify({{
        id: proj.id(),
        name: proj.name(),
        folder: lookup.match.name()
    }});
}}
"""
        )
    else:
        script = f"""\
var app = Application("OmniFocus");
var doc = app.defaultDocument;
var proj = app.Project({{name: "{js_escape(name)}"}});
doc.projects.push(proj);
JSON.stringify({{id: proj.id(), name: proj.name()}});
"""
    result = run_jxa_or_exit(script)
    check_ambiguous(result, "folders")
    check_result_error(result)
    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(
            f"Created project: {result.get('name', name)} ({result.get('id', '?')[:8]})"
        )
