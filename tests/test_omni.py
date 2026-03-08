"""Unit tests for OmniAutomation bridge helpers."""

import subprocess

import pytest

from ofocus.omni import OmniError, run_omnijs


def test_run_omnijs_timeout_raises_omnierror(monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout", 0))

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(OmniError, match="timed out"):
        run_omnijs("JSON.stringify({ok: true});")
