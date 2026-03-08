"""OmniAutomation bridge — run JavaScript inside OmniFocus via osascript."""

import json
import subprocess
from typing import Any

OMNIJS_TIMEOUT_SECONDS = 15


class OmniError(Exception):
    """Error from OmniAutomation execution."""


def run_omnijs(script: str) -> Any:
    """Run OmniAutomation JS inside OmniFocus, return parsed JSON.

    The script should end with a JSON.stringify(...) expression.
    """
    # Escape backticks in the script for the template literal
    escaped = script.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
    wrapper = f'Application("OmniFocus").evaluateJavascript(`{escaped}`)'
    try:
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", wrapper],
            capture_output=True,
            text=True,
            check=True,
            timeout=OMNIJS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as e:
        raise OmniError(
            "OmniAutomation error: command timed out after "
            f"{OMNIJS_TIMEOUT_SECONDS} seconds"
        ) from e
    except subprocess.CalledProcessError as e:
        raise OmniError(
            f"OmniAutomation error: {e.stderr.strip() or e.stdout.strip()}"
        ) from e

    stdout = result.stdout.strip()
    if not stdout:
        return None

    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        # osascript may wrap output in quotes; try unwrapping
        if stdout.startswith('"') and stdout.endswith('"'):
            try:
                inner = json.loads(stdout)
                return json.loads(inner)
            except (json.JSONDecodeError, TypeError):
                pass
        raise OmniError(f"Failed to parse OmniAutomation output: {stdout!r}")
