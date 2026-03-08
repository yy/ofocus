"""Unit tests for CLI helpers — no OmniFocus needed."""

import pytest

from ofocus.cli import _js_escape, _validate_date, _validate_task_id


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
