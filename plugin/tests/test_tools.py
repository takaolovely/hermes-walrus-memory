"""The six tool handlers: zero-config behaviour, graceful network failure, and
the guarantee that nothing ever raises into the agent loop."""

from __future__ import annotations

import json

import pytest

from plugin import ledger, tools, walrus


def call(fn, **kwargs):
    raw = fn(**kwargs)
    assert isinstance(raw, str)
    return json.loads(raw)


# -- zero config -----------------------------------------------------------


def test_observe_without_credentials(ledger_path):
    out = call(tools.memory_observe, fact="The user prefers dark mode.", topic="ui")
    assert out["ok"] is True
    assert out["sync"] == "local"
    assert out["ref"] == "obs#01"
    assert ledger_path


def test_observe_rejects_empty(ledger_path):
    out = call(tools.memory_observe, fact="   ")
    assert out["ok"] is False
    assert "empty" in out["error"]


def test_observe_sanitises_pipes(ledger_path):
    out = call(tools.memory_observe, fact="a|b\nc", topic="t")
    assert out["ok"] and "|" not in out["text"]


def test_correct_preserves_original(populated):
    out = call(
        tools.memory_provenance_diff,
        fact_id=populated["fact_id"],
    )
    events = out["events"]
    assert events[0]["event"] == "observed"
    assert events[0]["text"] == "The user is in Jakarta."
    assert [e["event"] for e in events].count("corrected") == 2


def test_correct_derives_rule_after_two_fixes(populated):
    out = call(
        tools.memory_recall_cited,
        query="timezone",
    )
    top = out["results"][0]
    assert top["text"] == "The user is in Palembang, WIB (UTC+7)."
    assert top["citation"].startswith("rule#")
    assert "obs#01" in top["citation"]


def test_correct_unknown_id_errors_cleanly(ledger_path):
    out = call(tools.memory_correct, fact_id="nope", correction="x")
    assert out["ok"] is False
    assert "unknown fact" in out["error"]


def test_correct_with_explicit_rule(ledger_path):
    obs = call(tools.memory_observe, fact="deadline is Friday", topic="deadline")
    out = call(
        tools.memory_correct,
        fact_id=obs["id"],
        correction="deadline is Saturday",
        rule="always confirm the deadline in writing",
    )
    assert out["rule"].startswith("rule#")
    assert out["preserved_observation"] is True


def test_recall_on_empty_ledger(ledger_path):
    out = call(tools.memory_recall_cited, query="anything")
    assert out["ok"] is True
    assert out["results"] == []


def test_recall_limit_is_clamped(ledger_path):
    for i in range(12):
        call(tools.memory_observe, fact=f"fact number {i}", topic="bulk")
    out = call(tools.memory_recall_cited, query="fact", limit=99)
    assert len(out["results"]) <= 20


def test_provenance_requires_argument(ledger_path):
    out = call(tools.memory_provenance_diff)
    assert out["ok"] is False


def test_provenance_by_topic(populated):
    out = call(
        tools.memory_provenance_diff,
        topic="user.timezone",
    )
    assert out["ok"] is True
    assert len(out["facts"]) == 1


# -- verify ----------------------------------------------------------------


def test_verify_zero_config_reports_local_mode(populated):
    out = call(tools.walrus_verify)
    assert out["ok"] is True
    assert out["mode"] == "local"
    assert out["chain_ok"] is True
    assert "hash chain" in out["integrity"]
    assert out["lines"] == 4  # obs + fix + fix + derived rule


def test_verify_detects_tampering(populated):
    path = populated["ledger_path"]
    with open(path, "r+", encoding="utf-8") as fh:
        content = fh.read()
        fh.seek(0)
        fh.write(content.replace("Jakarta", "JakartaX", 1))
        fh.truncate()
    out = call(tools.walrus_verify)
    assert out["chain_ok"] is False
    assert out["broken_at"] == 1


# -- graceful network failure ---------------------------------------------


class BoomClient(walrus.WalrusClient):
    def append(self, idempotency_key, text):
        raise walrus.WalrusError("network: timed out")


class FakeClient(walrus.WalrusClient):
    def __init__(self):
        super().__init__("test")
        self.sent = []

    def append(self, idempotency_key, text):
        self.sent.append(text)
        return f"digest{len(self.sent)}"

    def snapshot(self):
        return list(self.sent)


def test_observe_survives_relay_timeout(monkeypatch, ledger_path):
    monkeypatch.setenv("WALRUS_DELEGATE_KEY", "k")
    monkeypatch.setenv("WALRUS_ACCOUNT_ID", "a")
    monkeypatch.setattr(tools, "_client", lambda: BoomClient("test"))

    out = call(tools.memory_observe, fact="written anyway", topic="t")
    assert out["ok"] is True, "a relay timeout must never fail the tool"
    assert out["sync"] == "pending"
    assert "timed out" in (out["note"] or "")

    verify = call(tools.walrus_verify)
    assert verify["chain_ok"] is True
    assert verify["pending"] == 1


def test_failed_write_is_never_lost(monkeypatch, ledger_path):
    monkeypatch.setenv("WALRUS_DELEGATE_KEY", "k")
    monkeypatch.setenv("WALRUS_ACCOUNT_ID", "a")
    monkeypatch.setattr(tools, "_client", lambda: BoomClient("test"))
    call(tools.memory_observe, fact="durable despite failure", topic="t")

    from plugin import store
    records = store.LedgerStore().read_records()
    assert [r.text for r in records] == ["durable despite failure"]


def test_sync_push_retries_pending(monkeypatch, ledger_path):
    monkeypatch.setenv("WALRUS_DELEGATE_KEY", "k")
    monkeypatch.setenv("WALRUS_ACCOUNT_ID", "a")
    monkeypatch.setattr(tools, "_client", lambda: BoomClient("test"))
    call(tools.memory_observe, fact="stuck line", topic="t")

    fake = FakeClient()
    monkeypatch.setattr(tools, "_client", lambda: fake)
    out = call(tools.walrus_sync, action="push")
    assert out["ok"] is True
    assert out["pushed"] == 1
    assert out["pending"] == 0

    verify = call(tools.walrus_verify)
    assert verify["chain_ok"] is True
    assert verify["pending"] == 0


def test_sync_without_credentials_is_explicit(ledger_path):
    out = call(tools.walrus_sync, action="push")
    assert out["ok"] is False
    assert out["mode"] == "local"
    assert "WALRUS_DELEGATE_KEY" in out["error"]


def test_sync_pull_merges_without_duplicates(monkeypatch, ledger_path):
    monkeypatch.setenv("WALRUS_DELEGATE_KEY", "k")
    monkeypatch.setenv("WALRUS_ACCOUNT_ID", "a")

    # Device A writes two lines and syncs them.
    fake = FakeClient()
    monkeypatch.setattr(tools, "_client", lambda: fake)
    call(tools.memory_observe, fact="device A fact", topic="a")
    call(tools.memory_observe, fact="second fact", topic="a")
    call(tools.walrus_sync, action="push")

    # Device B pulls the same snapshot twice: no duplicates either time.
    # The pull writes into the confined ledger path, so both reads land there.
    out1 = call(tools.walrus_sync, action="pull")
    out2 = call(tools.walrus_sync, action="pull")
    assert out1["ok"] and out2["ok"]
    from plugin import store
    assert len(store.LedgerStore().read_records()) == 2
    assert call(tools.walrus_verify)["chain_ok"] is True


def test_sync_pull_failure_is_reported_not_raised(monkeypatch, ledger_path):
    monkeypatch.setenv("WALRUS_DELEGATE_KEY", "k")
    monkeypatch.setenv("WALRUS_ACCOUNT_ID", "a")

    class BadSnapshot(walrus.WalrusClient):
        def snapshot(self):
            raise walrus.WalrusError("network: down")

    monkeypatch.setattr(tools, "_client", lambda: BadSnapshot("test"))
    out = call(tools.walrus_sync, action="pull")
    assert out["ok"] is False
    assert "pull failed" in out["error"]


def test_sync_unknown_action(monkeypatch, ledger_path):
    monkeypatch.setattr(tools, "_client", lambda: FakeClient())
    out = call(tools.walrus_sync, action="sideways")
    assert out["ok"] is False


def test_verify_reports_unreachable_walrus(monkeypatch, ledger_path):
    monkeypatch.setenv("WALRUS_DELEGATE_KEY", "k")
    monkeypatch.setenv("WALRUS_ACCOUNT_ID", "a")

    class Down(walrus.WalrusClient):
        def snapshot(self):
            raise walrus.WalrusError("network: down")

    monkeypatch.setattr(tools, "_client", lambda: Down("test"))
    out = call(tools.walrus_verify)
    assert out["chain_ok"] is True
    assert out["walrus_reachable"] is False
    assert "skipped" in out["note"]


def test_availability_check_never_uses_network(monkeypatch):
    """is_configured() is what the tool's check_fn calls; it must be pure."""
    monkeypatch.delenv("WALRUS_DELEGATE_KEY", raising=False)
    monkeypatch.delenv("WALRUS_ACCOUNT_ID", raising=False)
    assert walrus.is_configured() is False

    monkeypatch.setenv("WALRUS_DELEGATE_KEY", "k")
    monkeypatch.setenv("WALRUS_ACCOUNT_ID", "a")
    assert walrus.is_configured() is True

    status = walrus.status()
    assert status.mode == "walrus"


# -- rule derivation -------------------------------------------------------


def test_third_correction_replaces_the_stale_rule(ledger_path):
    """A rule states what is believed now. Leaving a stale one next to a newer
    correction would make recall quote text the user already changed."""
    obs = call(tools.memory_observe, fact="uses vim", topic="editor")
    fid = obs["id"]
    call(tools.memory_correct, fact_id=fid, correction="uses emacs")
    call(tools.memory_correct, fact_id=fid, correction="uses helix")
    call(tools.memory_correct, fact_id=fid, correction="uses neovim")

    from plugin import store

    records = store.LedgerStore().read_records()
    kinds = [r.kind for r in records]
    assert kinds.count("rule") == 2, "old rule kept for history, new rule supersedes it"
    assert kinds.count("fix") == 3
    assert kinds[0] == "obs"

    rules = [r for r in records if r.kind == "rule"]
    assert rules[1].fields.get("supersedes") == rules[0].ref
    assert "neovim" in rules[1].fields["text"]
    assert "helix" not in rules[1].fields["text"]


def test_rule_cites_the_latest_correction(populated):
    out = call(tools.memory_recall_cited, query="Palembang")
    citation = out["results"][0]["citation"]
    assert citation.startswith("rule#")
    assert "fix#03" in citation
    assert citation.endswith("obs#01")
