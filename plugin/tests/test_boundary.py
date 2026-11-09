"""The tool boundary must never leak an exception into the agent loop."""

from __future__ import annotations

import json

import pytest

from plugin import tools, walrus


def _load(raw: str) -> dict:
    return json.loads(raw)


def test_guard_returns_error_json_instead_of_raising():
    def boom(**kwargs):
        raise RuntimeError("internal explosion")

    out = _load(tools._guard("memory_observe", boom, {}))
    assert out["ok"] is False
    assert "RuntimeError" in out["error"]
    assert "internal explosion" in out["error"]


def test_guard_maps_bad_arguments():
    def strict(only_this):
        return "ok"

    out = _load(tools._guard("memory_observe", strict, {"wrong": 1}))
    assert out["ok"] is False
    assert "rejected its arguments" in out["error"]


def test_guard_maps_filesystem_errors():
    def disk(path):
        raise OSError(28, "No space left on device")

    out = _load(tools._guard("memory_observe", disk, {"path": "/x"}))
    assert out["ok"] is False
    assert "could not reach the ledger" in out["error"]


def test_guard_passes_through_success():
    def fine(value):
        return json.dumps({"ok": True, "value": value})

    out = _load(tools._guard("x", fine, {"value": 7}))
    assert out == {"ok": True, "value": 7}


def test_registered_handlers_are_guarded():
    """A broken ledger path must produce an error result, not a traceback."""

    class Ctx:
        def __init__(self):
            self.tools = {}

        def register_tool(self, name, toolset, schema, handler, **kw):
            self.tools[name] = handler

    from plugin import register

    ctx = Ctx()
    register(ctx)

    # /dev/null/subdir cannot be created, so the store raises on write.
    for name, args in (
        ("memory_observe", {"fact": "x", "ledger_path": "/dev/null/nope/x.log"}),
        ("memory_recall_cited", {"query": "x", "ledger_path": "/dev/null/nope/x.log"}),
        ("walrus_verify", {"ledger_path": "/dev/null/nope/x.log"}),
    ):
        raw = ctx.tools[name](args)
        assert isinstance(raw, str), f"{name} did not return a string"
        payload = _load(raw)
        assert "ok" in payload


def test_bridge_failure_never_raises(monkeypatch):
    """A bridge command that explodes must degrade, not propagate."""
    import subprocess

    monkeypatch.setenv("WALRUS_SEAL_BRIDGE", "some-bridge")
    walrus.seal_session_reset()

    def exploding(*a, **kw):
        raise subprocess.SubprocessError("bridge died")

    monkeypatch.setattr(subprocess, "run", exploding)
    assert walrus.seal_session("0xabc", "ns") == ""


def test_timeout_defaults_are_tight():
    assert walrus.DEFAULT_TIMEOUT <= 8.0
    assert walrus.DEFAULT_SEAL_TIMEOUT <= 8.0
