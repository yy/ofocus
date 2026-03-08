"""OmniAutomation bridge — run JavaScript inside OmniFocus via osascript."""

import json
import subprocess


class OmniError(Exception):
    """Error from OmniAutomation execution."""


def run_omnijs(script: str) -> any:
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
        )
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
