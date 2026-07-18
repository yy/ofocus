"""Shared helpers for running AppleScript JavaScript bridges."""

import json
import subprocess
from typing import Any


class OmniError(Exception):
    """Error from OmniFocus bridge execution."""


class OmniTimeoutError(OmniError):
    """The osascript bridge exceeded its timeout."""


def _unwrap_json_string(value: Any) -> Any:
    """Parse a JSON string payload if it itself contains serialized JSON."""
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _parse_json_output(
    stdout: str,
    *,
    error_prefix: str,
    unwrap_nested_json_string: bool = False,
) -> Any:
    """Parse bridge output as JSON, optionally unwrapping quoted JSON strings."""
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        raise OmniError(f"Failed to parse {error_prefix} output: {stdout!r}")
    if unwrap_nested_json_string:
        return _unwrap_json_string(parsed)
    return parsed


def _subprocess_output_text(value: str | None) -> str:
    """Return subprocess output as text even when CalledProcessError stores None."""
    return value or ""


def run_osascript_json(
    script: str,
    *,
    timeout_seconds: int,
    error_prefix: str,
    allow_empty_output: bool = False,
    unwrap_nested_json_string: bool = False,
) -> Any | None:
    """Run JavaScript via osascript and return parsed JSON."""
    try:
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", script],
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as e:
        raise OmniTimeoutError(
            f"{error_prefix} error: command timed out after {timeout_seconds} seconds"
        ) from e
    except subprocess.CalledProcessError as e:
        detail = _subprocess_output_text(e.stderr).strip() or _subprocess_output_text(
            e.stdout
        ).strip()
        raise OmniError(f"{error_prefix} error: {detail}") from e

    stdout = result.stdout.strip()
    if not stdout:
        if allow_empty_output:
            return None
        raise OmniError(f"{error_prefix} error: empty output from osascript")

    return _parse_json_output(
        stdout,
        error_prefix=error_prefix,
        unwrap_nested_json_string=unwrap_nested_json_string,
    )
