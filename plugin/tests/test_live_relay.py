"""Behaviour against a live relay that rejects the credentials.

These tests only run when WALRUS_LIVE=1 and real credentials are present. It is
a state-machine check, not a happy-path demo: an auth failure must leave the
local ledger intact, the tool must still report success, and every line must be
marked pending so walrus_sync can chase it later.
"""

from __future__ import annotations

import json
import os

import pytest

from plugin import ledger, tools, walrus

pytestmark = pytest.mark.skipif(
    os.environ.get("WALRUS_LIVE") != "1",
    reason="set WALRUS_LIVE=1 with credentials to run the live relay tests",
)


def _load(raw: str) -> dict:
    return json.loads(raw)


def test_rejected_credentials_do_not_lose_or_block_writes(monkeypatch, ledger_path):
    """A relay that rejects the credentials must cost nothing but a pending mark.

    Credentials come from the environment so no key material lives in the repo.
    Set WALRUS_LIVE=1 plus WALRUS_DELEGATE_KEY / WALRUS_ACCOUNT_ID to run it.
    """
    if not os.environ.get("WALRUS_DELEGATE_KEY") or not os.environ.get("WALRUS_ACCOUNT_ID"):
        pytest.skip("WALRUS_DELEGATE_KEY and WALRUS_ACCOUNT_ID required for the live test")
    monkeypatch.setenv("WALRUS_HTTP_TIMEOUT", "20")

    obs = _load(tools.memory_observe(fact="Auth failure should not cost a line.", topic="auth"))
    assert obs["ok"] is True
    assert obs["sync"] == "pending"
    assert "401" in obs["note"]
    # The message must name the fix, not just the status code.
    assert "not registered" in obs["note"] or "delegate" in obs["note"]

    fix = _load(tools.memory_correct(fact_id=obs["id"], correction="Auth failure costs nothing."))
    assert fix["ok"] is True

    verify = _load(tools.walrus_verify())
    assert verify["chain_ok"] is True
    assert verify["lines"] == 2
    assert verify["pending"] == 2
    assert verify["synced"] == 0

    chain = ledger.verify_chain(open(ledger_path, encoding="utf-8").read().splitlines())
    assert chain.ok is True


def test_auth_error_message_is_actionable(monkeypatch):
    err = walrus.WalrusError("http 401: ")
    text = walrus.explain(err)
    assert "not registered" in text
    assert "account id" in text.lower()

    assert "rate limiting" in walrus.explain(walrus.WalrusError("http 429: slow down"))
    assert walrus.explain(walrus.WalrusError("network: timed out")) == "network: timed out"
