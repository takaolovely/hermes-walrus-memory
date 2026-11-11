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

    # Undeclared keys must be dropped at the registration boundary, so a model
    # cannot steer a handler at a path of its choosing. The call still succeeds
    # (or fails for its own reasons) but never reaches the filesystem via
    # ledger_path.
    for name, args in (
        ("memory_observe", {"fact": "x", "ledger_path": "/dev/null/nope/x.log"}),
        ("memory_recall_cited", {"query": "x", "ledger_path": "/dev/null/nope/x.log"}),
        ("walrus_verify", {"ledger_path": "/dev/null/nope/x.log"}),
    ):
        raw = ctx.tools[name](args)
        assert isinstance(raw, str), f"{name} did not return a string"
        payload = _load(raw)
        assert "ok" in payload


def test_undeclared_keys_never_reach_handler():
    """The wrapper strips every key the schema does not declare."""
    seen = []

    def spy(**kwargs):
        seen.append(kwargs)
        return "{}"

    class Ctx:
        def __init__(self):
            self.tools = {}

        def register_tool(self, name, toolset, schema, handler, **kw):
            self.tools[name] = handler

    from plugin import _TOOLS, register

    orig = list(_TOOLS)
    try:
        import plugin as pkg

        pkg._TOOLS = (("memory_observe", orig[0][1], spy, "x"),)
        ctx = Ctx()
        register(ctx)
    finally:
        import plugin as pkg

        pkg._TOOLS = tuple(orig)

    ctx.tools["memory_observe"](
        {"fact": "hello", "topic": "t", "ledger_path": "/etc/passwd", "path": "/etc/shadow"}
    )
    assert seen == [{"fact": "hello", "topic": "t"}]


def test_import_schema_has_no_path():
    """memory_import must not accept a caller-chosen source path."""
    from plugin.schemas import MEMORY_IMPORT_SCHEMA

    props = MEMORY_IMPORT_SCHEMA["parameters"]["properties"]
    assert "path" not in props
    assert set(props) == {"topic_prefix", "dry_run"}


def test_schemas_declare_no_ledger_path():
    """No tool may expose ledger_path to the model."""
    from plugin.schemas import ALL_SCHEMAS

    for schema in ALL_SCHEMAS:
        props = schema.get("parameters", {}).get("properties", {})
        assert "ledger_path" not in props, f"{schema['name']} exposes ledger_path"


def test_bridge_env_is_minimal(monkeypatch):
    """The SEAL bridge child gets an allowlist, never the inherited environment."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp-should-not-leak")
    monkeypatch.setenv("WALRUS_DELEGATE_KEY", "delegate-key")
    monkeypatch.setenv("WALRUS_ACCOUNT_ID", "account-id")

    env = walrus.bridge_env()

    assert "OPENAI_API_KEY" not in env
    assert "GITHUB_TOKEN" not in env
    assert "WALRUS_ACCOUNT_ID" not in env, "bridge does not need the account id in env"
    assert env.get("WALRUS_DELEGATE_KEY") == "delegate-key"
    assert set(env).issubset(set(walrus.BRIDGE_ENV_ALLOWLIST))


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
