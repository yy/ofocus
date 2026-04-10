"""Legacy OmniAutomation compatibility bridge and shared OmniFocus errors."""

from typing import Any

from ofocus.bridge import OmniError, run_osascript_json

__all__ = ["OmniError", "run_omnijs"]

OMNIJS_TIMEOUT_SECONDS = 15


def run_omnijs(script: str) -> Any:
    """Run OmniAutomation JS inside OmniFocus, return parsed JSON.

    The script should end with a JSON.stringify(...) expression.
    """
    # Escape backticks in the script for the template literal
    escaped = script.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
    wrapper = f'Application("OmniFocus").evaluateJavascript(`{escaped}`)'
    return run_osascript_json(
        wrapper,
        timeout_seconds=OMNIJS_TIMEOUT_SECONDS,
        error_prefix="OmniAutomation",
        allow_empty_output=True,
        unwrap_nested_json_string=True,
    )
