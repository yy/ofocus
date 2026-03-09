"""Unit tests for CLI helpers — no OmniFocus needed."""

import subprocess

import pytest
from click.testing import CliRunner

from ofocus.cli import (
    JS_INBOX,
    JS_TASKS,
    _js_escape,
    _jxa_local_date_constructor,
    _run_jxa,
    _validate_date,
    _validate_task_id,
    cli,
)
from ofocus.omni import OmniError


def test_js_escape_basic():
    assert _js_escape("hello") == "hello"


def test_js_escape_double_quotes():
    assert _js_escape('say "hi"') == 'say \\"hi\\"'


def test_js_escape_single_quotes():
    assert _js_escape("it's") == "it\\'s"


def test_js_escape_backslash():
    assert _js_escape("a\\b") == "a\\\\b"


def test_js_escape_newline():
    assert _js_escape("line1\nline2") == "line1\\nline2"


def test_js_escape_backtick():
    assert _js_escape("use `code`") == "use \\`code\\`"


def test_js_escape_dollar():
    assert _js_escape("cost $5") == "cost \\$5"


def test_js_escape_template_literal_injection():
    assert _js_escape("${alert(1)}") == "\\${alert(1)}"


def test_js_escape_carriage_return():
    assert _js_escape("a\rb") == "a\\rb"


def test_js_escape_null_byte():
    assert _js_escape("a\0b") == "a\\0b"


def test_js_escape_line_separator():
    assert _js_escape("a\u2028b") == "a\\u2028b"


def test_js_escape_paragraph_separator():
    assert _js_escape("a\u2029b") == "a\\u2029b"


def test_js_escape_combined():
    result = _js_escape("a\\b\"c'd`e$f\ng")
    assert result == "a\\\\b\\\"c\\'d\\`e\\$f\\ng"


# ── _validate_date ──────────────────────────────────────────────────────


def test_validate_date_valid():
    assert _validate_date("2026-03-08") == "2026-03-08"


def test_validate_date_rejects_injection():
    with pytest.raises(SystemExit):
        _validate_date('"); doShellScript("evil"); //')


def test_validate_date_rejects_partial():
    with pytest.raises(SystemExit):
        _validate_date("2026-3-8")


def test_validate_date_rejects_garbage():
    with pytest.raises(SystemExit):
        _validate_date("not-a-date")


def test_validate_date_rejects_impossible_date():
    with pytest.raises(SystemExit):
        _validate_date("2026-02-31")


def test_jxa_local_date_constructor_uses_local_components():
    assert _jxa_local_date_constructor("2026-03-15") == "new Date(2026, 2, 15)"


# ── _validate_task_id ───────────────────────────────────────────────────


def test_validate_task_id_valid():
    assert _validate_task_id("j7cpqVlu") == "j7cpqVlu"


def test_validate_task_id_with_hyphens():
    assert _validate_task_id("abc-123_XY") == "abc-123_XY"


def test_validate_task_id_rejects_quotes():
    with pytest.raises(SystemExit):
        _validate_task_id('abc"def')


def test_validate_task_id_rejects_spaces():
    with pytest.raises(SystemExit):
        _validate_task_id("abc def")


def test_validate_task_id_rejects_injection():
    with pytest.raises(SystemExit):
        _validate_task_id('"}); doShellScript("evil")')


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

    monkeypatch.setattr("ofocus.cli._run_jxa", fake_run_jxa)
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
        _run_jxa("JSON.stringify({ok: true});")


def test_inbox_add_due_uses_local_date_constructor(monkeypatch):
    scripts = []

    def fake_run_jxa(script):
        scripts.append(script)
        return {"id": "abc12345", "name": "Read paper"}

    monkeypatch.setattr("ofocus.cli._run_jxa", fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["inbox", "add", "Read paper", "--due", "2026-03-15"])

    assert result.exit_code == 0
    assert len(scripts) == 1
    assert 'task.dueDate = new Date(2026, 2, 15);' in scripts[0]
    assert 'new Date("2026-03-15")' not in scripts[0]


def test_update_due_uses_local_date_constructor(monkeypatch):
    scripts = []

    def fake_run_jxa(script):
        scripts.append(script)
        return {"id": "abc12345", "name": "Read paper", "flagged": False}

    monkeypatch.setattr("ofocus.cli._run_jxa", fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["update", "abc12345", "--due", "2026-03-15"])

    assert result.exit_code == 0
    assert len(scripts) == 1
    assert 'task.dueDate = new Date(2026, 2, 15);' in scripts[0]
    assert 'new Date("2026-03-15")' not in scripts[0]


def test_tasks_due_before_uses_local_dates_in_json(monkeypatch):
    def fake_run_jxa(_script):
        return [
            {"id": "a1", "name": "Today", "dueDate": "2026-03-10"},
            {"id": "a2", "name": "Tomorrow", "dueDate": "2026-03-11"},
        ]

    monkeypatch.setattr("ofocus.cli._run_jxa", fake_run_jxa)
    runner = CliRunner()
    result = runner.invoke(cli, ["tasks", "--due-before", "2026-03-10", "--json"])

    assert result.exit_code == 0
    assert result.output.strip() == (
        '[\n'
        '  {\n'
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
