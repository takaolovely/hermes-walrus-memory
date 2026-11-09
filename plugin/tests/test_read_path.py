"""Read-path truthfulness: degraded is not the same as missing."""

from __future__ import annotations

import json

import pytest

from plugin import tools, walrus


def _load(raw: str) -> dict:
    return json.loads(raw)


def test_degraded_recall_is_not_reported_as_missing(monkeypatch, ledger_path):
    """The relay matched lines but could not decrypt them. Verify must say so
    instead of claiming the lines are absent from Walrus."""
    monkeypatch.setenv("WALRUS_DELEGATE_KEY", "dummy-key")
    monkeypatch.setenv("WALRUS_ACCOUNT_ID", "0xdummy")

    def fake_snapshot(self, limit=5000):
        raise walrus.WalrusDegraded("relay matched 4 line(s) but could not read them back")

    monkeypatch.setattr(walrus.WalrusClient, "snapshot", fake_snapshot)

    tools.memory_observe(fact="degraded read test", topic="degraded", ledger_path=ledger_path)
    out = _load(tools.walrus_verify(ledger_path=ledger_path))

    assert out["ok"] is True
    assert out["chain_ok"] is True
    assert out["walrus_reachable"] is True, "the relay did answer"
    assert out["verified_on_walrus"] is False
    assert "not_on_walrus" not in out, "must not claim lines are missing"
    assert "SEAL" in out["note"]


def test_snapshot_raises_degraded_instead_of_empty(monkeypatch):
    """An empty list and 'could not decrypt' are different facts."""
    client = walrus.WalrusClient(namespace="test")
    monkeypatch.setattr(
        client,
        "_post",
        lambda path, payload: {"results": [], "total": 0, "dropped_count": 3, "degraded": True},
    )
    with pytest.raises(walrus.WalrusDegraded) as exc:
        client.snapshot()
    # Three bait queries, three dropped lines each.
    assert "9 line(s)" in str(exc.value)
    assert "degraded=true" in str(exc.value)


def test_snapshot_returns_lines_when_healthy(monkeypatch):
    client = walrus.WalrusClient(namespace="test")
    monkeypatch.setattr(
        client,
        "_post",
        lambda path, payload: {
            "results": [{"text": "obs|seq=1|text=hello"}, {"text": "fix|seq=2|text=hi"}],
            "total": 2,
            "degraded": False,
        },
    )
    lines = client.snapshot()
    assert lines == ["obs|seq=1|text=hello", "fix|seq=2|text=hi"]
