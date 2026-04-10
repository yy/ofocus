"""Shared helpers for running AppleScript JavaScript bridges."""

import json
import subprocess
from typing import Any


class OmniError(Exception):
    """Error from OmniFocus bridge execution."""


def _parse_json_output(
    stdout: str,
    *,
    error_prefix: str,
    unwrap_nested_json_string: bool = False,
) -> Any:
    """Parse bridge output as JSON, optionally unwrapping quoted JSON strings."""
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        if (
            unwrap_nested_json_string
            and stdout.startswith('"')
            and stdout.endswith('"')
        ):
            try:
                inner = json.loads(stdout)
                return json.loads(inner)
            except (json.JSONDecodeError, TypeError):
                pass
        raise OmniError(f"Failed to parse {error_prefix} output: {stdout!r}")


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
        raise OmniError(
            f"{error_prefix} error: command timed out after {timeout_seconds} seconds"
        ) from e
    except subprocess.CalledProcessError as e:
        detail = e.stderr.strip() or e.stdout.strip()
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
