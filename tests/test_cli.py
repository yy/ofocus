"""Unit tests for CLI — no OmniFocus needed."""

import subprocess

import pytest
from click.testing import CliRunner

from ofocus import __version__
from ofocus.cli import cli
from ofocus.helpers import (
    annotate_types,
    collect_first_available,
    count_tasks,
    filter_available,
    filter_tree,
    format_task_line,
    js_escape,
    jxa_local_date_constructor,
    mark_availability,
    print_tree,
    validate_date,
    validate_task_id,
)
from ofocus.jxa import JS_INBOX, JS_TASKS, run_jxa
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


def test_js_tasks_excludes_dropped():
    assert "!t.dropped()" in JS_TASKS


def test_js_due_dates_use_local_date_strings():
    assert "toLocalDateString" in JS_INBOX
    assert "toLocalDateString" in JS_TASKS
    assert "toISOString" not in JS_INBOX
    assert "toISOString" not in JS_TASKS


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
    assert "!t.dropped()" in scripts[0]
    assert "t.completed() || t.dropped()" in scripts[0]


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
    remaining, total = count_tasks(SAMPLE_TREE, count_all=True)
    assert total == 4
    assert remaining == 2


def test_count_tasks_after_filter():
    filtered = filter_tree(SAMPLE_TREE)
    remaining, total = count_tasks(filtered, count_all=True)
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
    assert len(first) == 1
    assert first[0]["name"] == "A"


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
    assert len(first) == 1
    assert first[0]["name"] == "G1"


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
