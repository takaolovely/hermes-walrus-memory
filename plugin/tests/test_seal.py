"""SEAL session resolution and pull semantics.

Walrus Memory encrypts every blob with Mysten SEAL, so recall needs an
x-seal-session credential to return plaintext. These tests pin the three-tier
resolution (literal env, bridge command, degraded) and the promise that a pulled
line is not marked pending.
"""

from __future__ import annotations

import json
import os

import pytest

from plugin import ledger, memory as memory_mod, store, tools, walrus


def _load(raw: str) -> dict:
    return json.loads(raw)


@pytest.fixture(autouse=True)
def _clear_seal_cache():
    walrus.seal_session_reset()
    yield
    walrus.seal_session_reset()


# -- resolution order ------------------------------------------------------


def test_no_session_configured_means_no_bridge(monkeypatch):
    monkeypatch.delenv("WALRUS_SEAL_SESSION", raising=False)
    monkeypatch.delenv("WALRUS_SEAL_BRIDGE", raising=False)
    assert walrus.seal_bridge_available() is False
    assert walrus.seal_session("0xabc", "ns") == ""


def test_literal_session_wins(monkeypatch):
    monkeypatch.setenv("WALRUS_SEAL_SESSION", "literal-session-token")
    monkeypatch.setenv("WALRUS_SEAL_BRIDGE", "/bin/false")
    assert walrus.seal_bridge_available() is True
    assert walrus.seal_session("0xabc", "ns") == "literal-session-token"


def test_bridge_output_is_parsed_and_cached(monkeypatch, tmp_path):
    script = tmp_path / "bridge.sh"
    calls = tmp_path / "calls.txt"
    script.write_text(
        f'#!/bin/sh\necho "$@" >> {calls}\necho \'{{"ok": true, "session": "from-bridge"}}\'\n',
        encoding="utf-8",
    )
    script.chmod(0o755)
    monkeypatch.setenv("WALRUS_SEAL_BRIDGE", str(script))

    assert walrus.seal_session("0xabc", "my-ns", "obs") == "from-bridge"
    # Cached: the second call must not run the bridge again.
    assert walrus.seal_session("0xabc", "my-ns", "fix") == "from-bridge"
    args = calls.read_text(encoding="utf-8").strip().splitlines()
    assert len(args) == 1
    assert "0xabc my-ns obs" in args[0]


def test_broken_bridge_degrades_instead_of_raising(monkeypatch, tmp_path):
    script = tmp_path / "boom.sh"
    script.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setenv("WALRUS_SEAL_BRIDGE", str(script))
    assert walrus.seal_session("0xabc", "ns") == ""


def test_missing_bridge_binary_degrades(monkeypatch):
    monkeypatch.setenv("WALRUS_SEAL_BRIDGE", "/nonexistent/binary/never")
    assert walrus.seal_session("0xabc", "ns") == ""


def test_bridge_garbage_output_degrades(monkeypatch, tmp_path):
    script = tmp_path / "junk.sh"
    script.write_text("#!/bin/sh\necho 'not json'\necho '{\"ok\": false}'\n", encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setenv("WALRUS_SEAL_BRIDGE", str(script))
    assert walrus.seal_session("0xabc", "ns") == ""


# -- recall carries the session -------------------------------------------


def test_seal_header_only_attached_to_recall(monkeypatch):
    monkeypatch.setenv("WALRUS_SEAL_SESSION", "session-xyz")
    monkeypatch.setenv("WALRUS_DELEGATE_KEY", "00" * 32)
    monkeypatch.setenv("WALRUS_ACCOUNT_ID", "0xdeadbeef")

    client = walrus.WalrusClient(namespace="ns")
    recall_headers = client._signed_headers("POST", "/api/recall", "{}")
    assert "x-seal-session" not in recall_headers, "signing does not add it"

    # The header is added in _request, so assert through the payload path.
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["headers"] = dict(req.headers)

        class Resp:
            def read(self):
                return b'{"results": [], "total": 0}'

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    client._post("/api/recall", {"query": "obs", "namespace": "ns"})
    header_names = {k.lower() for k in captured["headers"]}
    assert "x-seal-session" in header_names

    captured.clear()
    client._post("/api/remember", {"text": "hello", "namespace": "ns", "idempotency_key": "k"})
    header_names = {k.lower() for k in captured["headers"]}
    assert "x-seal-session" not in header_names, "writes must not ship the decrypt credential"


# -- pull semantics -------------------------------------------------------


def _seed_remote(tmp_path, records):
    """Write records to a fake remote snapshot the client will return."""
    return [r.encode() for r in records]


def test_pulled_lines_are_marked_synced_not_pending(monkeypatch, ledger_path, tmp_path):
    monkeypatch.setenv("WALRUS_DELEGATE_KEY", "dummy")
    monkeypatch.setenv("WALRUS_ACCOUNT_ID", "0xdummy")

    remote = [
        ledger.build(ledger.KIND_OBS, "00000000", 1, {"id": "obs-remote-1", "topic": "remote", "text": "from walrus", "at": "2026-11-01T00:00:00+00:00"}),
        ledger.build(ledger.KIND_FIX, "abc12345", 2, {"id": "fix-01-obs-remote-1", "target": "obs-remote-1", "topic": "remote", "text": "corrected", "at": "2026-11-01T00:01:00+00:00"}),
    ]
    monkeypatch.setattr(walrus.WalrusClient, "snapshot", lambda self, limit=5000: _seed_remote(tmp_path, remote))

    out = _load(tools.walrus_sync(action="pull"))
    assert out["ok"] is True
    assert out["pulled"] == 2

    records = store.LedgerStore().read_records()
    assert all(r.sync == "synced" for r in records), "pulled lines came from Walrus"
    assert ledger.verify_chain([r.encode() for r in records]).ok is True


def test_verify_matches_on_identity_not_resealed_hash(monkeypatch, ledger_path, tmp_path):
    """Pull re-seals lines locally, so the hash differs from the Walrus copy.
    Verify must not call those lines missing."""
    monkeypatch.setenv("WALRUS_DELEGATE_KEY", "dummy")
    monkeypatch.setenv("WALRUS_ACCOUNT_ID", "0xdummy")

    remote = [
        ledger.build(ledger.KIND_OBS, "00000000", 1, {"id": "obs-x", "topic": "t", "text": "remote only", "at": "2026-11-01T00:00:00+00:00"}),
    ]
    remote_lines = _seed_remote(tmp_path, remote)
    monkeypatch.setattr(walrus.WalrusClient, "snapshot", lambda self, limit=5000: remote_lines)

    tools.walrus_sync(action="pull")
    out = _load(tools.walrus_verify())

    assert out["walrus_reachable"] is True
    assert out["verified_on_walrus"] is True
    assert out["not_on_walrus"] == 0
    assert out["match"] is True


def test_pull_degrades_with_structured_payload(monkeypatch, ledger_path):
    monkeypatch.setenv("WALRUS_DELEGATE_KEY", "dummy")
    monkeypatch.setenv("WALRUS_ACCOUNT_ID", "0xdummy")

    def sealed(self, limit=5000):
        raise walrus.WalrusDegraded("relay matched 4 line(s)", dropped=4)

    monkeypatch.setattr(walrus.WalrusClient, "snapshot", sealed)

    out = _load(tools.walrus_sync(action="pull"))
    assert out["ok"] is True, "pull is not disabled, it reports its state"
    assert out["degraded"] is True
    assert out["encrypted_blobs_found"] == 4
    assert out["pulled"] == 0
    assert "SEAL" in out["message"]
