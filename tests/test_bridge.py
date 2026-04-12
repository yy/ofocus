"""Unit tests for the shared osascript JSON bridge."""

import subprocess

import pytest

from ofocus.bridge import OmniError, run_osascript_json


def test_run_osascript_json_unwraps_nested_json_string(monkeypatch):
    class Result:
        stdout = '"{\\"ok\\": true, \\"items\\": [1, 2]}"'

    def fake_run(*_args, **_kwargs):
        return Result()

    monkeypatch.setattr("subprocess.run", fake_run)

    assert run_osascript_json(
        "JSON.stringify({ok: true});",
        timeout_seconds=5,
        error_prefix="Bridge",
        unwrap_nested_json_string=True,
    ) == {"ok": True, "items": [1, 2]}


def test_run_osascript_json_leaves_plain_strings_alone(monkeypatch):
    class Result:
        stdout = '"hello"'

    def fake_run(*_args, **_kwargs):
        return Result()

    monkeypatch.setattr("subprocess.run", fake_run)

    assert run_osascript_json(
        "JSON.stringify('hello');",
        timeout_seconds=5,
        error_prefix="Bridge",
        unwrap_nested_json_string=True,
    ) == "hello"


def test_run_osascript_json_raises_on_invalid_json(monkeypatch):
    class Result:
        stdout = "not-json"

    def fake_run(*_args, **_kwargs):
        return Result()

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(OmniError, match="Failed to parse Bridge output"):
        run_osascript_json(
            "JSON.stringify({ok: true});",
            timeout_seconds=5,
            error_prefix="Bridge",
        )


def test_run_osascript_json_keeps_object_payloads_when_unwrap_is_enabled(monkeypatch):
    class Result:
        stdout = '{"ok": true}'

    def fake_run(*_args, **_kwargs):
        return Result()

    monkeypatch.setattr("subprocess.run", fake_run)

    assert run_osascript_json(
        "JSON.stringify({ok: true});",
        timeout_seconds=5,
        error_prefix="Bridge",
        unwrap_nested_json_string=True,
    ) == {"ok": True}


def test_run_osascript_json_allows_empty_output_when_requested(monkeypatch):
    class Result:
        stdout = ""

    def fake_run(*_args, **_kwargs):
        return Result()

    monkeypatch.setattr("subprocess.run", fake_run)

    assert (
        run_osascript_json(
            "JSON.stringify({ok: true});",
            timeout_seconds=5,
            error_prefix="Bridge",
            allow_empty_output=True,
        )
        is None
    )


def test_run_osascript_json_wraps_timeout_errors(monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=args[0],
            timeout=kwargs.get("timeout", 0),
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(OmniError, match="timed out after 5 seconds"):
        run_osascript_json(
            "JSON.stringify({ok: true});",
            timeout_seconds=5,
            error_prefix="Bridge",
        )


def test_run_osascript_json_wraps_called_process_errors(monkeypatch):
    def fake_run(*_args, **_kwargs):
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=["osascript"],
            stderr="execution error",
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(OmniError, match="Bridge error: execution error"):
        run_osascript_json(
            "JSON.stringify({ok: true});",
            timeout_seconds=5,
            error_prefix="Bridge",
        )
