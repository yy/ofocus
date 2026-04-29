"""Unit tests for CLI — no OmniFocus needed."""

import subprocess
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

from ofocus import __version__
from ofocus.cli import cli
from ofocus.commands.project import _build_project_show_response
from ofocus.commands.task import _build_task_update_success_code
from ofocus.helpers import (
    annotate_types,
    build_folder_or_project_lookup_script,
    build_fuzzy_lookup_script,
    build_item_result_stringify,
    build_js_json_stringify,
    build_task_action_success_code,
    build_task_field_assignments,
    build_task_lookup_script,
    build_task_result_stringify,
    check_ambiguous,
    collect_first_available,
    count_tasks,
    echo_action_result,
    echo_json,
    echo_task_list,
    filter_available,
    filter_tasks,
    filter_tree,
    format_task_line,
    handle_group_json_option,
    js_escape,
    jxa_local_date_constructor,
    load_task_list,
    load_unique_task_list,
    mark_availability,
    print_tree,
    require_cli_result,
    run_jxa_or_exit,
    set_subcommand_defaults,
    validate_date,
    validate_task_id,
)
from ofocus.jxa import (
    JS_ACTION_TASK_HELPERS,
    JS_INBOX,
    JS_PROJECT_STATUS_HELPERS,
    JS_PROJECTS,
    JS_SERIALIZE_FOLDER_CONTENTS,
    JS_SHOW_PROJECT,
    JS_STATS,
    JS_TASKS,
    JS_TOP_LEVEL,
    run_jxa,
)
from ofocus.models import Task
from ofocus.omni import OmniError

# Patch target for jxa.run_jxa as used by each command module
_PATCH_JXA = "ofocus.jxa.run_jxa"


def test_js_escape_basic():
    assert js_escape("hello") == "hello"


def test_js_escape_double_quotes():
    assert js_escape('say "hi"') == 'say \\"hi\\"'


def test_js_escape_single_quotes():
    assert js_escape("it's") == "it\\'s"


def test_js_escape_backslash():
    assert js_escape("a\\b") == "a\\\\b"


def test_js_escape_newline():
    assert js_escape("line1\nline2") == "line1\\nline2"


def test_js_escape_backtick():
    assert js_escape("use `code`") == "use \\`code\\`"


def test_js_escape_dollar():
    assert js_escape("cost $5") == "cost \\$5"


def test_js_escape_template_literal_injection():
    assert js_escape("${alert(1)}") == "\\${alert(1)}"


def test_js_escape_carriage_return():
    assert js_escape("a\rb") == "a\\rb"


def test_js_escape_null_byte():
    assert js_escape("a\0b") == "a\\0b"


def test_js_escape_line_separator():
    assert js_escape("a\u2028b") == "a\\u2028b"


def test_js_escape_paragraph_separator():
    assert js_escape("a\u2029b") == "a\\u2029b"


def test_js_escape_combined():
    result = js_escape("a\\b\"c'd`e$f\ng")
    assert result == "a\\\\b\\\"c\\'d\\`e\\$f\\ng"


def test_build_fuzzy_lookup_script_reuses_fuzzy_match_and_customizes_not_found():
    script = build_fuzzy_lookup_script(
        'Personal "Projects"',
        "doc.flattenedProjects",
        """\
JSON.stringify({id: item.id(), name: item.name()});
""",
        item_var="item",
        not_found_error='Project not found: "Personal"',
    )

    assert "function fuzzyMatch(collection, query)" in script
    assert 'fuzzyMatch(doc.flattenedProjects, "Personal \\"Projects\\"")' in script
    assert 'JSON.stringify({error: "Project not found: \\"Personal\\""})' in script
    assert "var item = lookup.match;" in script


def test_build_fuzzy_lookup_script_reuses_shared_scaffold_and_prefix():
    script = build_fuzzy_lookup_script(
        "Personal",
        "doc.flattenedProjects",
        "JSON.stringify({id: item.id(), name: item.name()});",
        script_prefix="// prefix\n",
        not_found_error="Project not found",
    )

    assert script.startswith("// prefix\n")
    assert script.count('var app = Application("OmniFocus");') == 1
    assert script.count("var doc = app.defaultDocument;") == 1
    assert "else {\n    var item = lookup.match;" in script


def test_build_fuzzy_lookup_script_special_cases_empty_string_name_matching():
    script = build_fuzzy_lookup_script(
        "",
        "doc.flattenedFolders",
        "JSON.stringify({id: item.id(), name: item.name()});",
        not_found_error="Folder not found",
    )

    assert 'if (query === "") {' in script
    assert 'if (items[i].name() === "") emptyNames.push(items[i]);' in script
    assert "emptyNames.length === 1" in script
    assert script.index('if (query === "") {') < script.index("// ID prefix")


def test_build_folder_or_project_lookup_script_reuses_shared_snippets():
    script = build_folder_or_project_lookup_script('Research "Alpha"')

    assert script.count("function fuzzyMatch(collection, query)") == 1
    assert script.count("function serializeFolderContents(folder)") == 1
    assert 'var query = "Research \\"Alpha\\"";' in script
    assert "var folderLookup = fuzzyMatch(doc.flattenedFolders, query);" in script
    assert "var projLookup = fuzzyMatch(doc.flattenedProjects, query);" in script
    assert 'result = {error: "Folder not found"};' in script


def test_build_js_json_stringify_formats_compact_object_literal():
    assert (
        build_js_json_stringify(
            [("id", "task.id()"), ("name", "task.name()"), ("completed", "true")]
        )
        == "JSON.stringify({id: task.id(), name: task.name(), completed: true});"
    )


def test_build_item_result_stringify_uses_id_name_pair_by_default():
    assert build_item_result_stringify() == (
        "JSON.stringify({id: item.id(), name: item.name()});"
    )


def test_build_task_result_stringify_includes_standard_task_fields():
    assert build_task_result_stringify(
        [("flagged", "task.flagged()"), ("project", "proj ? proj.name() : null")]
    ) == (
        "JSON.stringify({id: task.id(), name: task.name(), flagged: task.flagged(), "
        "project: proj ? proj.name() : null});"
    )


def test_build_task_action_success_code_appends_standard_result_payload():
    assert build_task_action_success_code(
        "app.markComplete(task);",
        result_fields=[("completed", "true")],
    ) == "\n".join(
        [
            "app.markComplete(task);",
            "JSON.stringify({id: task.id(), name: task.name(), completed: true});",
        ]
    )


def test_build_task_update_success_code_without_project_keeps_update_then_result():
    success_code = _build_task_update_success_code(
        ['task.name = "Renamed";', "task.flagged = true;"],
        project=None,
    )

    assert success_code == "\n".join(
        [
            'task.name = "Renamed";',
            "task.flagged = true;",
            "var proj = task.containingProject();",
            (
                "JSON.stringify({id: task.id(), name: task.name(), "
                "flagged: task.flagged(), project: proj ? proj.name() : null});"
            ),
        ]
    )


def test_build_task_update_success_code_with_project_moves_before_updates():
    success_code = _build_task_update_success_code(
        ['task.name = "Renamed";'],
        project='Paper "Draft"',
    )

    assert 'fuzzyMatch(doc.flattenedProjects, "Paper \\"Draft\\"")' in success_code
    assert 'JSON.stringify({error: "Project not found"});' in success_code
    assert 'error: "ambiguous_project", matches: projLookup.matches' in success_code
    assert "app.evaluateJavascript(moveScript);" in success_code
    move_index = success_code.index("app.evaluateJavascript(moveScript);")
    update_index = success_code.index('    task.name = "Renamed";')
    assert move_index < update_index
    assert "project: proj ? proj.name() : null" in success_code


def test_build_task_lookup_script_uses_global_scalar_prefix_scan():
    script = build_task_lookup_script(
        "abc12345",
        """\
JSON.stringify({id: task.id(), name: task.name()});
""",
    )

    assert "function serializeTaskMatches(ids, names)" in script
    assert "var ids = doc.flattenedTasks.id();" in script
    assert "var names = doc.flattenedTasks.name();" in script
    assert "var inbox = doc.inboxTasks();" not in script
    assert "doc.flattenedTasks.whose({id: prefixIds[0]})();" in script


def test_build_task_lookup_script_reuses_shared_scaffold_and_prefix():
    script = build_task_lookup_script(
        "abc12345",
        "JSON.stringify({id: task.id(), name: task.name()});",
        script_prefix="// prefix\n",
    )

    assert script.startswith("// prefix\n")
    assert script.count('var app = Application("OmniFocus");') == 1
    assert script.count("var doc = app.defaultDocument;") == 1
    assert "if (lookup.error) {\n    JSON.stringify(lookup);\n}\nelse {" in script


# ── validate_date ──────────────────────────────────────────────────────


def test_validate_date_valid():
    assert validate_date("2026-03-08") == "2026-03-08"


def test_validate_date_rejects_injection():
    with pytest.raises(SystemExit):
        validate_date('"); doShellScript("evil"); //')


def test_validate_date_rejects_partial():
    with pytest.raises(SystemExit):
        validate_date("2026-3-8")


def test_validate_date_rejects_garbage():
    with pytest.raises(SystemExit):
        validate_date("not-a-date")


def test_validate_date_rejects_impossible_date():
    with pytest.raises(SystemExit):
        validate_date("2026-02-31")


def test_jxa_local_date_constructor_uses_local_components():
    assert jxa_local_date_constructor("2026-03-15") == "new Date(2026, 2, 15)"


def test_build_task_field_assignments_formats_common_mutations():
    assert build_task_field_assignments(
        name='Review "draft"',
        due="2026-03-15",
        flag=False,
        note="Line 1\nLine 2",
    ) == [
        'task.name = "Review \\"draft\\"";',
        "task.dueDate = new Date(2026, 2, 15);",
        "task.flagged = false;",
        'task.note = "Line 1\\nLine 2";',
    ]


# ── validate_task_id ───────────────────────────────────────────────────


def test_validate_task_id_valid():
    assert validate_task_id("j7cpqVlu") == "j7cpqVlu"


def test_validate_task_id_with_hyphens():
    assert validate_task_id("abc-123_XY") == "abc-123_XY"


def test_validate_task_id_rejects_quotes():
    with pytest.raises(SystemExit):
        validate_task_id('abc"def')


def test_validate_task_id_rejects_spaces():
    with pytest.raises(SystemExit):
        validate_task_id("abc def")


def test_validate_task_id_rejects_injection():
    with pytest.raises(SystemExit):
        validate_task_id('"}); doShellScript("evil")')


def test_cli_version_matches_package_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_js_tasks_uses_scalar_field_arrays_for_speed():
    assert "doc.flattenedTasks.id()" in JS_TASKS
    assert "doc.flattenedTasks.containingProject.name()" in JS_TASKS
    assert "doc.flattenedTasks.containingProject.id()" in JS_TASKS
    assert "doc.flattenedTasks.tasks()" in JS_TASKS
    assert "doc.flattenedTasks.tags.name()" in JS_TASKS
    assert "doc.flattenedTasks().filter" not in JS_TASKS


def test_action_task_helper_includes_top_level_project_actions():
    assert "t.containingProject()" in JS_ACTION_TASK_HELPERS
    assert "t.tasks().length === 0" in JS_ACTION_TASK_HELPERS
    assert "t.project()" not in JS_ACTION_TASK_HELPERS
    assert "t.parentTask()" not in JS_ACTION_TASK_HELPERS


def test_js_tasks_filters_project_actions_and_excludes_task_groups():
    assert "!projectNames[i]" in JS_TASKS
    assert "ids[i] === projectIds[i]" in JS_TASKS
    assert "isActiveProjectStatus(projectStatuses[i])" in JS_TASKS
    assert "childTasks[i].length !== 0" in JS_TASKS
    assert "completed[i]" in JS_TASKS
    assert "dropped[i]" in JS_TASKS


def test_js_tasks_excludes_inactive_project_statuses():
    assert "doc.flattenedTasks.containingProject.status()" in JS_TASKS
    assert "!isActiveProjectStatus(projectStatuses[i])" in JS_TASKS
    assert "function getProjectStatus(project)" in JS_PROJECT_STATUS_HELPERS
    assert 'return status === "active" || status === "active status";' in (
        JS_PROJECT_STATUS_HELPERS
    )


def test_project_scripts_reuse_shared_status_lookup_helper():
    assert "status: getProjectStatus(project)" in JS_PROJECTS
    assert "status: getProjectStatus(proj)" in JS_SHOW_PROJECT
    assert "try { s = project.status(); }" not in JS_PROJECTS
    assert "try { s = proj.status(); }" not in JS_SHOW_PROJECT


def test_js_projects_precomputes_task_counts_from_scalar_arrays():
    assert "function countProjectTasksById()" in JS_PROJECTS
    assert "doc.flattenedTasks.id()" in JS_PROJECTS
    assert "doc.flattenedTasks.containingProject.id()" in JS_PROJECTS
    assert "taskCount: taskCounts[id] || 0" in JS_PROJECTS
    assert "project.flattenedTasks().filter" not in JS_PROJECTS
    assert "return serializeProjectSummary(p);" not in JS_PROJECTS


def test_js_due_dates_use_local_date_strings():
    assert "toLocalDateString" in JS_INBOX
    assert "toLocalDateString" in JS_TASKS
    assert "toISOString" not in JS_INBOX
    assert "toISOString" not in JS_TASKS


def test_folder_contents_script_reuses_project_summary_helpers():
    assert "function serializeFolderSummary(folder)" in JS_SERIALIZE_FOLDER_CONTENTS
    assert "function serializeProjectSummary(project)" in JS_SERIALIZE_FOLDER_CONTENTS
    assert "children.push(serializeFolderSummary(subfolders[i]));" in (
        JS_SERIALIZE_FOLDER_CONTENTS
    )
    assert "children.push(serializeProjectSummary(projects[i]));" in (
        JS_SERIALIZE_FOLDER_CONTENTS
    )


def test_top_level_script_reuses_project_summary_helpers():
    assert "function serializeFolderSummary(folder)" in JS_TOP_LEVEL
    assert "function serializeProjectSummary(project)" in JS_TOP_LEVEL
    assert "result.push(serializeFolderSummary(folders[i]));" in JS_TOP_LEVEL
    assert "result.push(serializeProjectSummary(topProjects[i]));" in JS_TOP_LEVEL


def test_stats_excludes_dropped_from_active_and_overdue(monkeypatch):
    scripts = []

    def fake_run_jxa(script):
        scripts.append(script)
        return {
            "inbox": 0,
            "active": 0,
            "projects": 0,
            "tags": 0,
            "flagged": 0,
            "overdue": 0,
        }

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["stats", "--json"])

    assert result.exit_code == 0
    assert len(scripts) == 1
    assert "doc.flattenedTasks.id()" in scripts[0]
    assert "doc.flattenedTasks.completed()" in scripts[0]
    assert "doc.flattenedTasks.containingProject.name()" in scripts[0]
    assert "doc.flattenedTasks.containingProject.id()" in scripts[0]
    assert "doc.flattenedTasks.containingProject.status()" in scripts[0]
    assert "doc.flattenedTasks.tasks()" in scripts[0]
    assert "childTasks[i].length === 0" in scripts[0]
    assert "ids[i] === projectIds[i]" in scripts[0]
    assert "!isActiveProjectStatus(projectStatuses[i])" in scripts[0]
    assert "completed[i] ||" in scripts[0]
    assert "dropped[i]" in scripts[0]
    assert "doc.flattenedTasks().filter" not in scripts[0]


def test_stats_overdue_uses_local_calendar_dates(monkeypatch):
    scripts = []

    def fake_run_jxa(script):
        scripts.append(script)
        return {
            "inbox": 0,
            "active": 0,
            "projects": 0,
            "tags": 0,
            "flagged": 0,
            "overdue": 0,
        }

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["stats", "--json"])

    assert result.exit_code == 0
    assert len(scripts) == 1
    assert "toLocalDateString" in scripts[0]
    assert "var today = toLocalDateString(new Date());" in scripts[0]
    assert "toLocalDateString(d) < today" in scripts[0]
    assert "d && d < new Date()" not in scripts[0]


def test_stats_filters_completed_and_dropped_inbox_tasks(monkeypatch):
    scripts = []

    def fake_run_jxa(script):
        scripts.append(script)
        return {
            "inbox": 0,
            "active": 0,
            "projects": 0,
            "tags": 0,
            "flagged": 0,
            "overdue": 0,
        }

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["stats", "--json"])

    assert result.exit_code == 0
    assert len(scripts) == 1
    assert "doc.inboxTasks().filter(function(t) {" in scripts[0]
    assert "return !t.completed() && !t.dropped();" in scripts[0]
    assert "inbox: doc.inboxTasks().length" not in scripts[0]


def test_stats_uses_shared_jxa_constant(monkeypatch):
    scripts = []

    def fake_run_jxa(script):
        scripts.append(script)
        return {
            "inbox": 0,
            "active": 0,
            "projects": 0,
            "tags": 0,
            "flagged": 0,
            "overdue": 0,
        }

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["stats", "--json"])

    assert result.exit_code == 0
    assert scripts == [JS_STATS]


def test_run_jxa_timeout_raises_omnierror(monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout", 0))

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(OmniError, match="timed out"):
        run_jxa("JSON.stringify({ok: true});")


def test_run_jxa_empty_output_raises_omnierror(monkeypatch):
    class Result:
        stdout = ""

    def fake_run(*_args, **_kwargs):
        return Result()

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(OmniError, match="empty output"):
        run_jxa("JSON.stringify({ok: true});")


def test_run_jxa_activates_omnifocus_before_script(monkeypatch):
    scripts = []

    class Result:
        stdout = '{"ok": true}'

    def fake_run(args, **_kwargs):
        scripts.append(args[-1])
        return Result()

    monkeypatch.setattr("subprocess.run", fake_run)

    result = run_jxa("JSON.stringify({ok: true});")

    assert result == {"ok": True}
    assert len(scripts) == 1
    assert 'var __ofocusApp = Application("OmniFocus");' in scripts[0]
    assert "__ofocusApp.activate();" in scripts[0]
    assert "delay(0.2);" in scripts[0]
    assert scripts[0].endswith("JSON.stringify({ok: true});")


def test_run_jxa_or_exit_exits_cleanly_on_omnierror(monkeypatch, capsys):
    def fake_run_jxa(_script):
        raise OmniError("boom")

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)

    with pytest.raises(SystemExit):
        run_jxa_or_exit("JSON.stringify({ok: true});")

    assert "Error: boom" in capsys.readouterr().err


def test_load_task_list_parses_results(monkeypatch):
    def fake_run_jxa(_script):
        return [{"id": "abc123", "name": "Read paper", "tags": ["urgent"]}]

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)

    tasks = load_task_list("tasks script")

    assert len(tasks) == 1
    assert tasks[0].id == "abc123"
    assert tasks[0].name == "Read paper"
    assert tasks[0].tags == ["urgent"]


def test_load_unique_task_list_dedupes_by_id(monkeypatch):
    def fake_run_jxa(script):
        if script == "tasks script":
            return [
                {"id": "a1", "name": "Read paper"},
                {"id": "a2", "name": "Email advisor"},
            ]
        if script == "inbox script":
            return [
                {"id": "a1", "name": "Read paper"},
                {"id": "a3", "name": "Buy milk"},
            ]
        raise AssertionError(f"Unexpected script: {script}")

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)

    tasks = load_unique_task_list("tasks script", "inbox script")

    assert [task.id for task in tasks] == ["a1", "a2", "a3"]


def test_echo_task_list_renders_text(capsys):
    tasks = [
        Task(id="abc12345", name="Read paper", flagged=True),
        Task(id="def67890", name="Email advisor"),
    ]

    echo_task_list(tasks, "tasks", as_json=False)

    assert capsys.readouterr().out == (
        "2 tasks:\n  abc12345  * Read paper\n  def67890  Email advisor\n"
    )


def test_echo_json_uses_cli_standard_indentation(capsys):
    echo_json({"id": "abc12345", "items": [{"name": "Read paper"}]})

    assert capsys.readouterr().out == (
        "{\n"
        '  "id": "abc12345",\n'
        '  "items": [\n'
        "    {\n"
        '      "name": "Read paper"\n'
        "    }\n"
        "  ]\n"
        "}\n"
    )


def test_filter_tasks_combines_task_ls_filters():
    tasks = [
        Task(
            id="a1",
            name="Match",
            project="Work",
            tags=["Urgent"],
            flagged=True,
            due_date="2026-03-10",
        ),
        Task(
            id="a2",
            name="Too late",
            project="Work",
            tags=["Urgent"],
            flagged=True,
            due_date="2026-03-11",
        ),
        Task(
            id="a3",
            name="Wrong tag",
            project="Work",
            tags=["Later"],
            flagged=True,
            due_date="2026-03-10",
        ),
        Task(
            id="a4",
            name="Unflagged",
            project="Work",
            tags=["Urgent"],
            flagged=False,
            due_date="2026-03-10",
        ),
    ]

    filtered = filter_tasks(
        tasks,
        project="wor",
        tag="urgent",
        flagged=True,
        due_before="2026-03-10",
    )

    assert [task.id for task in filtered] == ["a1"]


def test_filter_tasks_keeps_empty_string_project_lookup_explicit():
    tasks = [
        Task(id="a1", name="Empty project task", project=""),
        Task(id="a2", name="Missing project task", project=None),
        Task(id="a3", name="Work task", project="Work"),
    ]

    filtered = filter_tasks(tasks, project="")

    assert [task.id for task in filtered] == ["a1"]


def test_set_subcommand_defaults_merges_only_explicit_values():
    ctx = SimpleNamespace(default_map={"ls": {"tag": "research"}})

    set_subcommand_defaults(
        ctx,
        "ls",
        project="Work",
        tag=None,
        flagged=False,
        as_json=True,
    )

    assert ctx.default_map == {
        "ls": {"tag": "research", "project": "Work", "as_json": True}
    }


def test_handle_group_json_option_forwards_supported_subcommand():
    ctx = SimpleNamespace(
        invoked_subcommand="show",
        command_path="ofocus project",
        default_map=None,
    )

    forwarded = handle_group_json_option(
        ctx,
        as_json=True,
        supported_subcommands=("show",),
    )

    assert forwarded is True
    assert ctx.default_map == {"show": {"as_json": True}}


def test_handle_group_json_option_rejects_unsupported_subcommand():
    ctx = SimpleNamespace(
        invoked_subcommand="open",
        command_path="ofocus task",
        default_map=None,
    )

    with pytest.raises(
        click.UsageError,
        match="`--json` is not supported by `ofocus task open`\\.",
    ):
        handle_group_json_option(
            ctx,
            as_json=True,
            unsupported_subcommands=("open",),
        )


def test_echo_action_result_renders_short_id_when_requested(capsys):
    echo_action_result(
        {"id": "abc12345xyz", "name": "Read paper"},
        "Added",
        as_json=False,
        include_id=True,
    )

    assert capsys.readouterr().out == "Added: Read paper (abc12345)\n"


def test_check_ambiguous_accepts_alias_errors(capsys):
    with pytest.raises(SystemExit):
        check_ambiguous(
            {
                "error": "ambiguous_project",
                "matches": [
                    {"id": "p1234567", "name": "Project A"},
                    {"id": "p7654321", "name": "Project B"},
                ],
            },
            aliases={"ambiguous_project": "projects"},
        )

    assert "Multiple projects match" in capsys.readouterr().err


def test_require_cli_result_allows_expected_sentinel_error():
    assert require_cli_result(
        {"error": "is_project", "id": "proj1"},
        item_type="folders",
        allowed_errors=("is_project",),
    ) == {"error": "is_project", "id": "proj1"}


def test_require_cli_result_exits_on_unexpected_error(capsys):
    with pytest.raises(SystemExit):
        require_cli_result(
            {"error": "Folder not found"},
            item_type="folders",
            allowed_errors=("is_project",),
        )

    assert "Folder not found" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("argv", "fake_result"),
    [
        (
            ["task", "complete", "abc12345"],
            {"id": "abc12345XYZ", "name": "Read paper", "completed": True},
        ),
        (
            ["task", "update", "abc12345", "--name", "Renamed"],
            {"id": "abc12345XYZ", "name": "Renamed", "flagged": False, "project": None},
        ),
        (
            ["task", "drop", "abc12345"],
            {"id": "abc12345XYZ", "name": "Read paper", "dropped": True},
        ),
        (
            ["task", "delete", "abc12345"],
            {"id": "abc12345XYZ", "name": "Read paper", "deleted": True},
        ),
    ],
)
def test_task_mutation_commands_support_prefix_lookup(monkeypatch, argv, fake_result):
    scripts = []

    def fake_run_jxa(script):
        scripts.append(script)
        return fake_result

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, argv)

    assert result.exit_code == 0
    assert len(scripts) == 1
    assert "indexOf(query) === 0" in scripts[0]
    assert "doc.flattenedTasks.id()" in scripts[0]
    assert "doc.inboxTasks()" not in scripts[0]


def test_task_complete_honors_group_level_json_shorthand(monkeypatch):
    def fake_run_jxa(_script):
        return {"id": "abc12345XYZ", "name": "Read paper", "completed": True}

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "--json", "complete", "abc12345"])

    assert result.exit_code == 0
    assert result.output.strip() == (
        '{\n  "id": "abc12345XYZ",\n  "name": "Read paper",\n  "completed": true\n}'
    )


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (
            ["task", "--json", "open", "abc12345"],
            "`--json` is not supported by `ofocus task open`.",
        ),
        (
            ["project", "--json", "open", "proj12345"],
            "`--json` is not supported by `ofocus project open`.",
        ),
    ],
)
def test_group_level_json_rejects_open_subcommands(monkeypatch, argv, message):
    monkeypatch.setattr(_PATCH_JXA, lambda _script: {"id": "abc12345XYZ", "name": "X"})
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: None)
    runner = CliRunner()
    result = runner.invoke(cli, argv)

    assert result.exit_code == 2
    assert message in result.output


def test_task_rejects_ls_only_filters_before_non_ls_subcommands():
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "--project", "Work", "complete", "abc12345"])

    assert result.exit_code == 2
    assert "--project can only be used with `ofocus task ls`" in result.output


@pytest.mark.parametrize(
    "argv",
    [
        ["task", "complete", "abc12345"],
        ["task", "update", "abc12345", "--name", "X"],
        ["task", "drop", "abc12345"],
        ["task", "delete", "abc12345"],
    ],
)
def test_task_mutation_commands_fail_cleanly_on_ambiguous_prefix(monkeypatch, argv):
    def fake_run_jxa(_script):
        return {
            "error": "ambiguous",
            "matches": [
                {"id": "abc12345XYZ", "name": "Task A"},
                {"id": "abc12345ZZZ", "name": "Task B"},
            ],
        }

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, argv)

    assert result.exit_code == 1
    assert "Multiple tasks match" in result.output


@pytest.mark.parametrize(
    "argv",
    [
        ["task", "open", "abc12345"],
        ["project", "open", "proj1234"],
    ],
)
def test_open_commands_fail_when_open_url_fails(monkeypatch, argv):
    def fake_run_jxa(_script):
        return {"id": "abc12345XYZ", "name": "Read paper"}

    def fake_run(cmd, check=False, **_kwargs):
        if check:
            raise subprocess.CalledProcessError(returncode=1, cmd=cmd)
        return subprocess.CompletedProcess(cmd, 1)

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    monkeypatch.setattr("subprocess.run", fake_run)
    runner = CliRunner()
    result = runner.invoke(cli, argv)

    assert result.exit_code == 1
    assert "failed to open OmniFocus URL" in result.output
    assert "Opened:" not in result.output


def test_project_open_uses_shared_fuzzy_lookup_script(monkeypatch):
    scripts = []

    def fake_run_jxa(script):
        scripts.append(script)
        return {"id": "proj12345XYZ", "name": "Paper writing"}

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: None)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "open", "Paper"])

    assert result.exit_code == 0
    assert len(scripts) == 1
    assert "function fuzzyMatch(collection, query)" in scripts[0]
    assert 'fuzzyMatch(doc.flattenedProjects, "Paper")' in scripts[0]
    assert 'JSON.stringify({error: "Project not found"});' in scripts[0]
    assert "var item = lookup.match;" in scripts[0]
    assert "JSON.stringify({id: item.id(), name: item.name()});" in scripts[0]


@pytest.mark.parametrize(
    ("argv", "expected_url"),
    [
        (["task", "open", "abc12345"], "omnifocus:///task/abc12345XYZ"),
        (["project", "open", "proj1234"], "omnifocus:///project/proj12345XYZ"),
    ],
)
def test_open_commands_use_type_specific_omnifocus_urls(
    monkeypatch, argv, expected_url
):
    open_calls = []

    def fake_run_jxa(_script):
        if argv[0] == "task":
            return {"id": "abc12345XYZ", "name": "Read paper"}
        return {"id": "proj12345XYZ", "name": "Paper writing"}

    def fake_run(cmd, check=False, **_kwargs):
        open_calls.append((cmd, check))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    monkeypatch.setattr("subprocess.run", fake_run)
    runner = CliRunner()
    result = runner.invoke(cli, argv)

    assert result.exit_code == 0
    assert open_calls == [(["open", expected_url], True)]
    assert "Opened:" in result.output


def test_project_show_honors_group_level_json_shorthand(monkeypatch):
    def fake_run_jxa(_script):
        return {
            "id": "proj12345XYZ",
            "name": "Paper writing",
            "status": "active",
            "note": "",
            "children": [],
        }

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "--json", "show", "Paper"])

    assert result.exit_code == 0
    assert result.output.strip() == (
        "{\n"
        '  "id": "proj12345XYZ",\n'
        '  "name": "Paper writing",\n'
        '  "status": "active",\n'
        '  "note": "",\n'
        '  "children": [],\n'
        '  "remaining": 0,\n'
        '  "total": 0\n'
        "}"
    )


def test_inbox_add_due_uses_local_date_constructor(monkeypatch):
    scripts = []

    def fake_run_jxa(script):
        scripts.append(script)
        return {"id": "abc12345", "name": "Read paper"}

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["inbox", "add", "Read paper", "--due", "2026-03-15"])

    assert result.exit_code == 0
    assert len(scripts) == 1
    assert "task.dueDate = new Date(2026, 2, 15);" in scripts[0]
    assert 'new Date("2026-03-15")' not in scripts[0]


def test_inbox_add_due_rejects_empty_string(monkeypatch):
    def fail_run_jxa(_script):
        raise AssertionError("inbox add should reject an empty due date before JXA")

    monkeypatch.setattr(_PATCH_JXA, fail_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["inbox", "add", "Read paper", "--due", ""])

    assert result.exit_code == 1
    assert "Error: date must be YYYY-MM-DD format" in result.output


def test_inbox_add_honors_group_level_json_shorthand(monkeypatch):
    def fake_run_jxa(_script):
        return {"id": "abc12345", "name": "Read paper"}

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["inbox", "--json", "add", "Read paper"])

    assert result.exit_code == 0
    assert result.output.strip() == (
        '{\n  "id": "abc12345",\n  "name": "Read paper"\n}'
    )


def test_inbox_lists_tasks(monkeypatch):
    def fake_run_jxa(_script):
        return [
            {
                "id": "abc12345xyz",
                "name": "Read paper",
                "flagged": True,
                "completed": False,
                "dueDate": None,
                "note": None,
                "tags": ["research"],
            }
        ]

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["inbox"])

    assert result.exit_code == 0
    assert result.output == "1 inbox tasks:\n  abc12345  * Read paper #research\n"


def test_update_due_uses_local_date_constructor(monkeypatch):
    scripts = []

    def fake_run_jxa(script):
        scripts.append(script)
        return {"id": "abc12345", "name": "Read paper", "flagged": False}

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "update", "abc12345", "--due", "2026-03-15"])

    assert result.exit_code == 0
    assert len(scripts) == 1
    assert "task.dueDate = new Date(2026, 2, 15);" in scripts[0]
    assert 'new Date("2026-03-15")' not in scripts[0]


def test_update_project_uses_prefix_lookup(monkeypatch):
    scripts = []

    def fake_run_jxa(script):
        scripts.append(script)
        return {"id": "abc12345", "name": "Read paper", "flagged": False}

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "update", "abc12345", "--project", "proj1234"])

    assert result.exit_code == 0
    assert len(scripts) == 1
    assert 'fuzzyMatch(doc.flattenedProjects, "proj1234")' in scripts[0]


def test_update_project_accepts_project_name_lookup(monkeypatch):
    scripts = []

    def fake_run_jxa(script):
        scripts.append(script)
        return {
            "id": "abc12345",
            "name": "Read paper",
            "flagged": False,
            "project": "Paper writing",
        }

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["task", "update", "abc12345", "--project", "Paper writing"]
    )

    assert result.exit_code == 0
    assert len(scripts) == 1
    assert 'fuzzyMatch(doc.flattenedProjects, "Paper writing")' in scripts[0]
    assert "Updated: Read paper" in result.output


def test_update_project_reports_ambiguous_project_matches(monkeypatch):
    def fake_run_jxa(_script):
        return {
            "error": "ambiguous_project",
            "matches": [
                {"id": "proj1234aaa", "name": "Project A"},
                {"id": "proj1234bbb", "name": "Project B"},
            ],
        }

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "update", "abc12345", "--project", "proj1234"])

    assert result.exit_code == 1
    assert "Multiple projects match" in result.output


def test_tasks_due_before_uses_local_dates_in_json(monkeypatch):
    def fake_run_jxa(_script):
        return [
            {"id": "a1", "name": "Today", "dueDate": "2026-03-10"},
            {"id": "a2", "name": "Tomorrow", "dueDate": "2026-03-11"},
        ]

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "ls", "--due-before", "2026-03-10", "--json"])

    assert result.exit_code == 0
    assert result.output.strip() == (
        "[\n"
        "  {\n"
        '    "id": "a1",\n'
        '    "name": "Today",\n'
        '    "flagged": false,\n'
        '    "completed": false,\n'
        '    "dueDate": "2026-03-10",\n'
        '    "note": null,\n'
        '    "project": null,\n'
        '    "tags": []\n'
        "  }\n"
        "]"
    )


def test_tasks_due_before_rejects_empty_string(monkeypatch):
    def fake_run_jxa(_script):
        return [{"id": "a1", "name": "Today", "dueDate": "2026-03-10"}]

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "ls", "--due-before", "", "--json"])

    assert result.exit_code == 1
    assert "Error: date must be YYYY-MM-DD format" in result.output


def test_task_ls_empty_string_project_filter_is_not_treated_as_no_filter(monkeypatch):
    def fake_run_jxa(_script):
        return [
            {"id": "a1", "name": "Empty project task", "project": ""},
            {"id": "a2", "name": "Work task", "project": "Work"},
        ]

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "ls", "--project", "", "--json"])

    assert result.exit_code == 0
    assert result.output.strip() == (
        "[\n"
        "  {\n"
        '    "id": "a1",\n'
        '    "name": "Empty project task",\n'
        '    "flagged": false,\n'
        '    "completed": false,\n'
        '    "dueDate": null,\n'
        '    "note": null,\n'
        '    "project": "",\n'
        '    "tags": []\n'
        "  }\n"
        "]"
    )


def test_task_search_dedupes_inbox_and_active_results(monkeypatch):
    def fake_run_jxa(script):
        if script == JS_TASKS:
            return [
                {
                    "id": "abc12345xyz",
                    "name": "Read paper",
                    "flagged": False,
                    "completed": False,
                    "dueDate": None,
                    "note": "Review methods",
                    "project": "Research",
                    "tags": [],
                }
            ]
        if script == JS_INBOX:
            return [
                {
                    "id": "abc12345xyz",
                    "name": "Read paper",
                    "flagged": False,
                    "completed": False,
                    "dueDate": None,
                    "note": "Review methods",
                    "tags": [],
                }
            ]
        raise AssertionError(f"Unexpected script: {script}")

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "search", "read"])

    assert result.exit_code == 0
    assert result.output == "1 matches:\n  abc12345  Read paper [Research]\n"


def test_dump_accepts_json_flag(monkeypatch):
    responses = {
        JS_TASKS: [{"id": "t1", "name": "Task"}],
        "projects": [{"id": "p1", "name": "Project"}],
        "tags": [{"id": "g1", "name": "Tag"}],
        JS_INBOX: [{"id": "i1", "name": "Inbox"}],
        "folders": [{"id": "f1", "name": "Folder"}],
    }
    scripts = []

    def fake_run_jxa(script):
        scripts.append(script)
        if script == JS_TASKS:
            return responses[JS_TASKS]
        if script == JS_INBOX:
            return responses[JS_INBOX]
        if "flattenedProjects" in script:
            return responses["projects"]
        if "flattenedTags" in script:
            return responses["tags"]
        if "flattenedFolders" in script:
            return responses["folders"]
        raise AssertionError(f"Unexpected script: {script}")

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["dump", "--json"])

    assert result.exit_code == 0
    assert len(scripts) == 5
    assert result.output.strip() == (
        "{\n"
        '  "inbox": [\n'
        "    {\n"
        '      "id": "i1",\n'
        '      "name": "Inbox"\n'
        "    }\n"
        "  ],\n"
        '  "tasks": [\n'
        "    {\n"
        '      "id": "t1",\n'
        '      "name": "Task"\n'
        "    }\n"
        "  ],\n"
        '  "projects": [\n'
        "    {\n"
        '      "id": "p1",\n'
        '      "name": "Project"\n'
        "    }\n"
        "  ],\n"
        '  "tags": [\n'
        "    {\n"
        '      "id": "g1",\n'
        '      "name": "Tag"\n'
        "    }\n"
        "  ],\n"
        '  "folders": [\n'
        "    {\n"
        '      "id": "f1",\n'
        '      "name": "Folder"\n'
        "    }\n"
        "  ]\n"
        "}"
    )


# ── Tree helpers ───────────────────────────────────────────────────────

SAMPLE_TREE = [
    {
        "id": "t1",
        "name": "Buy supplies",
        "flagged": True,
        "completed": False,
        "dropped": False,
        "dueDate": None,
        "note": "",
        "tags": [],
        "children": [],
    },
    {
        "id": "g1",
        "name": "Phase 1",
        "flagged": False,
        "completed": False,
        "dropped": False,
        "dueDate": None,
        "note": "",
        "tags": [],
        "children": [
            {
                "id": "t2",
                "name": "Draft outline",
                "flagged": False,
                "completed": False,
                "dropped": False,
                "dueDate": None,
                "note": "",
                "tags": [],
                "children": [],
            },
            {
                "id": "t3",
                "name": "Review",
                "flagged": False,
                "completed": True,
                "dropped": False,
                "dueDate": "2026-03-25",
                "note": "",
                "tags": ["waiting"],
                "children": [],
            },
        ],
    },
    {
        "id": "t4",
        "name": "Dropped task",
        "flagged": False,
        "completed": False,
        "dropped": True,
        "dueDate": None,
        "note": "",
        "tags": [],
        "children": [],
    },
]


def test_filter_tree_removes_completed_and_dropped():
    filtered = filter_tree(SAMPLE_TREE)
    names = [n["name"] for n in filtered]
    assert "Dropped task" not in names
    phase1 = [n for n in filtered if n["name"] == "Phase 1"][0]
    child_names = [c["name"] for c in phase1["children"]]
    assert "Draft outline" in child_names
    assert "Review" not in child_names


def test_filter_tree_preserves_all_when_nothing_completed():
    tree = [
        {"id": "a", "name": "A", "completed": False, "dropped": False, "children": []},
    ]
    assert len(filter_tree(tree)) == 1


def test_count_tasks_leaf_only():
    remaining, total = count_tasks(SAMPLE_TREE)
    assert total == 4
    assert remaining == 2


def test_count_tasks_after_filter():
    filtered = filter_tree(SAMPLE_TREE)
    remaining, total = count_tasks(filtered)
    assert total == 2
    assert remaining == 2


def test_annotate_types():
    tree = [
        {"name": "leaf", "children": []},
        {"name": "group", "children": [{"name": "child", "children": []}]},
    ]
    annotate_types(tree)
    assert tree[0]["type"] == "task"
    assert tree[1]["type"] == "group"
    assert tree[1]["children"][0]["type"] == "task"


def test_format_task_line_plain():
    node = {
        "name": "Do thing",
        "flagged": False,
        "completed": False,
        "dropped": False,
        "dueDate": None,
        "tags": [],
    }
    assert format_task_line(node) == "Do thing"


def test_format_task_line_all_decorators():
    node = {
        "name": "Important",
        "flagged": True,
        "completed": False,
        "dropped": False,
        "dueDate": "2026-04-01",
        "tags": ["work", "urgent"],
    }
    line = format_task_line(node)
    assert "Important" in line
    assert "⚑" in line
    assert "(due 2026-04-01)" in line
    assert "#work" in line
    assert "#urgent" in line


def test_format_task_line_completed():
    node = {
        "name": "Done",
        "flagged": False,
        "completed": True,
        "dropped": False,
        "dueDate": None,
        "tags": [],
    }
    assert format_task_line(node).startswith("✓")


def test_format_task_line_dropped():
    node = {
        "name": "Nope",
        "flagged": False,
        "completed": False,
        "dropped": True,
        "dueDate": None,
        "tags": [],
    }
    assert format_task_line(node).startswith("✗")


def test_print_tree_output(capsys):
    tree = [
        {
            "name": "A",
            "flagged": False,
            "completed": False,
            "dropped": False,
            "dueDate": None,
            "tags": [],
            "children": [],
        },
        {
            "name": "B",
            "flagged": False,
            "completed": False,
            "dropped": False,
            "dueDate": None,
            "tags": [],
            "children": [
                {
                    "name": "B1",
                    "flagged": False,
                    "completed": False,
                    "dropped": False,
                    "dueDate": None,
                    "tags": [],
                    "children": [],
                },
            ],
        },
    ]
    print_tree(tree)
    output = capsys.readouterr().out
    assert "├── A" in output
    assert "└── B" in output
    assert "    └── B1" in output


# ── project show command ──────────────────────────────────────────────


def test_show_renders_tree(monkeypatch):
    def fake_run_jxa(_script):
        return {
            "id": "proj1",
            "name": "My Project",
            "status": "active",
            "note": "",
            "children": [
                {
                    "id": "t1",
                    "name": "Task A",
                    "flagged": True,
                    "completed": False,
                    "dropped": False,
                    "dueDate": None,
                    "note": "",
                    "tags": [],
                    "children": [],
                },
                {
                    "id": "t2",
                    "name": "Task B",
                    "flagged": False,
                    "completed": False,
                    "dropped": False,
                    "dueDate": "2026-04-01",
                    "note": "",
                    "tags": [],
                    "children": [],
                },
            ],
        }

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "show", "proj1"])
    assert result.exit_code == 0
    assert "My Project  (2/2 remaining)" in result.output
    assert "Task A" in result.output
    assert "⚑" in result.output
    assert "(due 2026-04-01)" in result.output


def test_show_filters_completed_by_default(monkeypatch):
    def fake_run_jxa(_script):
        return {
            "id": "proj1",
            "name": "P",
            "status": "active",
            "note": "",
            "children": [
                {
                    "id": "t1",
                    "name": "Done",
                    "flagged": False,
                    "completed": True,
                    "dropped": False,
                    "dueDate": None,
                    "note": "",
                    "tags": [],
                    "children": [],
                },
                {
                    "id": "t2",
                    "name": "Active",
                    "flagged": False,
                    "completed": False,
                    "dropped": False,
                    "dueDate": None,
                    "note": "",
                    "tags": [],
                    "children": [],
                },
            ],
        }

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "show", "proj1"])
    assert result.exit_code == 0
    assert "Done" not in result.output
    assert "Active" in result.output


def test_show_filters_empty_groups_after_removing_completed_children(monkeypatch):
    def fake_run_jxa(_script):
        return {
            "id": "proj1",
            "name": "P",
            "status": "active",
            "note": "",
            "children": [
                {
                    "id": "g1",
                    "name": "Phase 1",
                    "flagged": False,
                    "completed": False,
                    "dropped": False,
                    "dueDate": None,
                    "note": "",
                    "tags": [],
                    "children": [
                        {
                            "id": "t1",
                            "name": "Done",
                            "flagged": False,
                            "completed": True,
                            "dropped": False,
                            "dueDate": None,
                            "note": "",
                            "tags": [],
                            "children": [],
                        },
                    ],
                },
            ],
        }

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "show", "proj1"])
    assert result.exit_code == 0
    assert "P  (0/0 remaining)" in result.output
    assert "Phase 1" not in result.output


def test_show_all_includes_completed(monkeypatch):
    def fake_run_jxa(_script):
        return {
            "id": "proj1",
            "name": "P",
            "status": "active",
            "note": "",
            "children": [
                {
                    "id": "t1",
                    "name": "Done",
                    "flagged": False,
                    "completed": True,
                    "dropped": False,
                    "dueDate": None,
                    "note": "",
                    "tags": [],
                    "children": [],
                },
            ],
        }

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "show", "proj1", "--all"])
    assert result.exit_code == 0
    assert "✓ Done" in result.output


def test_show_json_output(monkeypatch):
    def fake_run_jxa(_script):
        return {
            "id": "proj1",
            "name": "P",
            "status": "active",
            "note": "",
            "children": [
                {
                    "id": "t1",
                    "name": "Leaf",
                    "flagged": False,
                    "completed": False,
                    "dropped": False,
                    "dueDate": None,
                    "note": "",
                    "tags": [],
                    "children": [],
                },
            ],
        }

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "show", "proj1", "--json"])
    assert result.exit_code == 0
    import json

    data = json.loads(result.output)
    assert data["remaining"] == 1
    assert data["total"] == 1
    assert data["children"][0]["type"] == "task"


def test_build_project_show_response_keeps_source_tree_unmodified():
    result = {"id": "proj1", "name": "P"}
    children = [
        {
            "id": "t1",
            "name": "First",
            "flagged": False,
            "completed": False,
            "dropped": False,
            "dueDate": None,
            "note": "",
            "tags": [],
            "_available": True,
            "children": [],
        }
    ]

    response = _build_project_show_response(result, children)

    assert response["remaining"] == 1
    assert response["total"] == 1
    assert response["children"][0]["type"] == "task"
    assert "_available" not in response["children"][0]
    assert "_available" in children[0]
    assert "type" not in children[0]


def test_show_ambiguous_project(monkeypatch):
    def fake_run_jxa(_script):
        return {
            "error": "ambiguous",
            "matches": [
                {"id": "p1", "name": "Proj A"},
                {"id": "p2", "name": "Proj B"},
            ],
        }

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "show", "Proj"])
    assert result.exit_code == 1
    assert "Multiple projects match" in result.output


def test_show_project_not_found(monkeypatch):
    def fake_run_jxa(_script):
        return {"error": "Project not found"}

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "show", "nonexistent"])
    assert result.exit_code == 1
    assert "Project not found" in result.output


# ── project ls command ────────────────────────────────────────────────


def test_ls_top_level(monkeypatch):
    def fake_run_jxa(_script):
        return [
            {
                "type": "folder",
                "id": "f1",
                "name": "Research",
                "projectCount": 5,
                "activeCount": 3,
            },
            {
                "type": "project",
                "id": "p1",
                "name": "Misc",
                "status": "active",
                "taskCount": 10,
            },
        ]

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "ls"])
    assert result.exit_code == 0
    assert "Research/" in result.output
    assert "3/5 projects active" in result.output
    assert "Misc" in result.output
    assert "10 tasks" in result.output


def test_task_group_forwards_ls_options(monkeypatch):
    def fake_run_jxa(_script):
        return [
            {
                "id": "a1",
                "name": "Flagged task",
                "flagged": True,
                "completed": False,
                "dueDate": None,
                "note": None,
                "project": "Work",
                "tags": [],
            },
            {
                "id": "a2",
                "name": "Plain task",
                "flagged": False,
                "completed": False,
                "dueDate": None,
                "note": None,
                "project": "Work",
                "tags": [],
            },
        ]

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "--flagged", "--json"])

    assert result.exit_code == 0
    assert result.output.strip() == (
        "[\n"
        "  {\n"
        '    "id": "a1",\n'
        '    "name": "Flagged task",\n'
        '    "flagged": true,\n'
        '    "completed": false,\n'
        '    "dueDate": null,\n'
        '    "note": null,\n'
        '    "project": "Work",\n'
        '    "tags": []\n'
        "  }\n"
        "]"
    )


def test_project_group_forwards_json_option(monkeypatch):
    def fake_run_jxa(_script):
        return [
            {
                "type": "project",
                "id": "p1",
                "name": "Misc",
                "status": "active",
                "taskCount": 10,
            },
        ]

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "--json"])

    assert result.exit_code == 0
    assert result.output.strip() == (
        "[\n"
        "  {\n"
        '    "type": "project",\n'
        '    "id": "p1",\n'
        '    "name": "Misc",\n'
        '    "status": "active",\n'
        '    "taskCount": 10\n'
        "  }\n"
        "]"
    )


def test_tag_group_forwards_json_option(monkeypatch):
    def fake_run_jxa(_script):
        return [
            {
                "id": "t1",
                "name": "urgent",
            },
        ]

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["tag", "--json"])

    assert result.exit_code == 0
    assert result.output.strip() == (
        '[\n  {\n    "id": "t1",\n    "name": "urgent"\n  }\n]'
    )


def test_task_group_forwards_options_to_explicit_ls_subcommand(monkeypatch):
    def fake_run_jxa(_script):
        return [
            {
                "id": "a1",
                "name": "Flagged task",
                "flagged": True,
                "completed": False,
                "dueDate": None,
                "note": None,
                "project": "Work",
                "tags": [],
            },
            {
                "id": "a2",
                "name": "Plain task",
                "flagged": False,
                "completed": False,
                "dueDate": None,
                "note": None,
                "project": "Work",
                "tags": [],
            },
        ]

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "--flagged", "ls", "--json"])

    assert result.exit_code == 0
    assert result.output.strip() == (
        "[\n"
        "  {\n"
        '    "id": "a1",\n'
        '    "name": "Flagged task",\n'
        '    "flagged": true,\n'
        '    "completed": false,\n'
        '    "dueDate": null,\n'
        '    "note": null,\n'
        '    "project": "Work",\n'
        '    "tags": []\n'
        "  }\n"
        "]"
    )


def test_project_group_forwards_json_to_explicit_ls_subcommand(monkeypatch):
    def fake_run_jxa(_script):
        return [
            {
                "type": "project",
                "id": "p1",
                "name": "Misc",
                "status": "active",
                "taskCount": 10,
            },
        ]

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "--json", "ls"])

    assert result.exit_code == 0
    assert result.output.strip() == (
        "[\n"
        "  {\n"
        '    "type": "project",\n'
        '    "id": "p1",\n'
        '    "name": "Misc",\n'
        '    "status": "active",\n'
        '    "taskCount": 10\n'
        "  }\n"
        "]"
    )


def test_tag_group_forwards_json_to_explicit_ls_subcommand(monkeypatch):
    def fake_run_jxa(_script):
        return [
            {
                "id": "t1",
                "name": "urgent",
            },
        ]

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["tag", "--json", "ls"])

    assert result.exit_code == 0
    assert result.output.strip() == (
        '[\n  {\n    "id": "t1",\n    "name": "urgent"\n  }\n]'
    )


def test_ls_drill_into_folder(monkeypatch):
    def fake_run_jxa(_script):
        return {
            "folder": "Research",
            "children": [
                {
                    "type": "folder",
                    "id": "sf1",
                    "name": "Subfolder",
                    "projectCount": 2,
                    "activeCount": 2,
                },
                {
                    "type": "project",
                    "id": "p1",
                    "name": "Paper writing",
                    "status": "active",
                    "taskCount": 5,
                },
            ],
        }

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "ls", "Research"])
    assert result.exit_code == 0
    assert "Research/" in result.output
    assert "Subfolder/" in result.output
    assert "Paper writing" in result.output


def test_ls_empty_string_folder_uses_lookup_path(monkeypatch):
    scripts = []

    def fake_run_jxa(script):
        scripts.append(script)
        return {"folder": "", "children": []}

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "ls", ""])

    assert result.exit_code == 0
    assert len(scripts) == 1
    assert 'var query = "";' in scripts[0]
    assert "doc.flattenedFolders" in scripts[0]
    assert "doc.flattenedProjects" in scripts[0]
    assert result.output == "/\n"


def test_ls_folder_not_found(monkeypatch):
    def fake_run_jxa(_script):
        return {"error": "Folder not found"}

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "ls", "nonexistent"])
    assert result.exit_code == 1
    assert "Folder not found" in result.output


def test_project_ls_script_uses_folder_not_found_error(monkeypatch):
    scripts = []

    def fake_run_jxa(script):
        scripts.append(script)
        return {"error": "Folder not found"}

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "ls", "nonexistent"])

    assert result.exit_code == 1
    assert len(scripts) == 1
    assert 'result = {error: "Folder not found"};' in scripts[0]


def test_ls_ambiguous_folder(monkeypatch):
    def fake_run_jxa(_script):
        return {
            "error": "ambiguous",
            "matches": [
                {"id": "f1", "name": "Research A"},
                {"id": "f2", "name": "Research B"},
            ],
        }

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "ls", "Research"])
    assert result.exit_code == 1
    assert "Multiple folders match" in result.output


def test_ls_ambiguous_project_fallback(monkeypatch):
    def fake_run_jxa(_script):
        return {
            "error": "ambiguous_project",
            "matches": [
                {"id": "p1", "name": "Project A"},
                {"id": "p2", "name": "Project B"},
            ],
        }

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "ls", "proj"])
    assert result.exit_code == 1
    assert "Multiple projects match" in result.output


def test_ls_shows_inactive_project_status(monkeypatch):
    def fake_run_jxa(_script):
        return [
            {
                "type": "project",
                "id": "p1",
                "name": "Old",
                "status": "on hold",
                "taskCount": 0,
            },
        ]

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "ls"])
    assert result.exit_code == 0
    assert "(on hold)" in result.output


# ── project create command ────────────────────────────────────────────


def test_project_create_ambiguous_folder(monkeypatch):
    def fake_run_jxa(_script):
        return {
            "error": "ambiguous",
            "matches": [
                {"id": "f1", "name": "Work"},
                {"id": "f2", "name": "Work"},
            ],
        }

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["project", "create", "Test Project", "--folder", "Work"]
    )
    assert result.exit_code == 1
    assert "Multiple folders match" in result.output


def test_project_create_folder_uses_shared_fuzzy_lookup_script(monkeypatch):
    scripts = []

    def fake_run_jxa(script):
        scripts.append(script)
        return {"id": "p1", "name": "Test Project", "folder": "Work"}

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["project", "create", "Test Project", "--folder", "Work"]
    )

    assert result.exit_code == 0
    assert len(scripts) == 1
    assert "function fuzzyMatch(collection, query)" in scripts[0]
    assert 'fuzzyMatch(doc.flattenedFolders, "Work")' in scripts[0]
    assert 'JSON.stringify({error: "Folder not found: Work"});' in scripts[0]
    assert "var item = lookup.match;" in scripts[0]
    assert 'var proj = app.Project({name: "Test Project"});' in scripts[0]
    assert "item.projects.push(proj);" in scripts[0]


def test_project_create_empty_string_folder_uses_folder_lookup(monkeypatch):
    scripts = []

    def fake_run_jxa(script):
        scripts.append(script)
        return {"id": "p1", "name": "Test Project", "folder": ""}

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["project", "create", "Test Project", "--folder", "", "--json"]
    )

    assert result.exit_code == 0
    assert len(scripts) == 1
    assert 'fuzzyMatch(doc.flattenedFolders, "")' in scripts[0]
    assert "item.projects.push(proj);" in scripts[0]
    assert 'JSON.stringify({error: "Folder not found: "});' in scripts[0]


# ── Availability helpers ──────────────────────────────────────────────


def _make_task(
    name, completed=False, dropped=False, defer=None, sequential=False, children=None
):
    return {
        "id": name.lower().replace(" ", "_"),
        "name": name,
        "flagged": False,
        "completed": completed,
        "dropped": dropped,
        "dueDate": None,
        "deferDate": defer,
        "note": "",
        "tags": [],
        "sequential": sequential,
        "children": children or [],
    }


def test_mark_availability_sequential_parent():
    children = [
        _make_task("A"),
        _make_task("B"),
        _make_task("C"),
    ]
    mark_availability(children, parent_sequential=True, today="2026-03-20")
    assert children[0]["_available"] is True
    assert children[1]["_available"] is False
    assert children[2]["_available"] is False


def test_mark_availability_parallel_parent():
    children = [
        _make_task("A"),
        _make_task("B"),
    ]
    mark_availability(children, parent_sequential=False, today="2026-03-20")
    assert children[0]["_available"] is True
    assert children[1]["_available"] is True


def test_mark_availability_skips_completed_in_sequential():
    children = [
        _make_task("Done", completed=True),
        _make_task("Next"),
        _make_task("Later"),
    ]
    mark_availability(children, parent_sequential=True, today="2026-03-20")
    assert children[0]["_available"] is False  # completed
    assert children[1]["_available"] is True  # first remaining
    assert children[2]["_available"] is False  # blocked


def test_mark_availability_deferred():
    children = [
        _make_task("Future", defer="2026-12-01"),
        _make_task("Now"),
    ]
    mark_availability(children, parent_sequential=False, today="2026-03-20")
    assert children[0]["_available"] is False  # deferred
    assert children[1]["_available"] is True


def test_mark_availability_past_defer_is_available():
    children = [
        _make_task("Past defer", defer="2026-01-01"),
    ]
    mark_availability(children, parent_sequential=False, today="2026-03-20")
    assert children[0]["_available"] is True


def test_filter_available():
    children = [
        _make_task("A"),
        _make_task("B"),
    ]
    mark_availability(children, parent_sequential=True, today="2026-03-20")
    filtered = filter_available(children)
    assert len(filtered) == 1
    assert filtered[0]["name"] == "A"


def test_collect_first_available_parallel():
    children = [
        _make_task("A"),
        _make_task("B"),
    ]
    mark_availability(children, parent_sequential=False, today="2026-03-20")
    first = collect_first_available(children)
    assert [task["name"] for task in first] == ["A", "B"]


def test_collect_first_available_nested_sequential():
    children = [
        _make_task(
            "Group",
            sequential=True,
            children=[
                _make_task("G1"),
                _make_task("G2"),
            ],
        ),
        _make_task("Standalone"),
    ]
    mark_availability(children, parent_sequential=False, today="2026-03-20")
    first = collect_first_available(children)
    assert [task["name"] for task in first] == ["G1", "Standalone"]


def test_show_available_flag(monkeypatch):
    def fake_run_jxa(_script):
        return {
            "id": "proj1",
            "name": "Seq Project",
            "status": "active",
            "note": "",
            "sequential": True,
            "children": [
                _make_task("First"),
                _make_task("Second"),
                _make_task("Third"),
            ],
        }

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "show", "proj1", "--available"])
    assert result.exit_code == 0
    assert "First" in result.output
    assert "Second" not in result.output


def test_show_available_json_omits_internal_availability_field(monkeypatch):
    def fake_run_jxa(_script):
        return {
            "id": "proj1",
            "name": "Seq Project",
            "status": "active",
            "note": "",
            "sequential": True,
            "children": [
                _make_task("First"),
                _make_task("Second"),
            ],
        }

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "show", "proj1", "--available", "--json"])

    assert result.exit_code == 0
    import json

    data = json.loads(result.output)
    assert data["children"][0]["name"] == "First"
    assert "_available" not in data["children"][0]


def test_show_first_json_omits_internal_availability_field(monkeypatch):
    def fake_run_jxa(_script):
        return {
            "id": "proj1",
            "name": "Seq Project",
            "status": "active",
            "note": "",
            "sequential": True,
            "children": [
                _make_task("First"),
                _make_task("Second"),
            ],
        }

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "show", "proj1", "--first", "--json"])

    assert result.exit_code == 0
    import json

    data = json.loads(result.output)
    assert data["name"] == "Seq Project"
    assert data["remaining"] == 1
    assert data["total"] == 1
    assert data["children"][0]["name"] == "First"
    assert "_available" not in data["children"][0]
    assert data["children"][0]["type"] == "task"


def test_show_first_flag(monkeypatch):
    def fake_run_jxa(_script):
        return {
            "id": "proj1",
            "name": "Seq Project",
            "status": "active",
            "note": "",
            "sequential": True,
            "children": [
                _make_task("First"),
                _make_task("Second"),
            ],
        }

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "show", "proj1", "--first"])
    assert result.exit_code == 0
    assert "first available" in result.output
    assert "First" in result.output
    assert "Second" not in result.output


def test_show_first_flag_lists_all_parallel_first_available_tasks(monkeypatch):
    def fake_run_jxa(_script):
        return {
            "id": "proj1",
            "name": "Parallel Project",
            "status": "active",
            "note": "",
            "sequential": False,
            "children": [
                _make_task("First"),
                _make_task("Second"),
            ],
        }

    monkeypatch.setattr(_PATCH_JXA, fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "show", "proj1", "--first"])

    assert result.exit_code == 0
    assert "first available" in result.output
    assert "First" in result.output
    assert "Second" in result.output
