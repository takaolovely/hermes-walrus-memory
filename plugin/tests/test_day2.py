"""Day 2 specs: rule supersession, MEMORY.md import, namespace isolation."""

from __future__ import annotations

import json
import os

from plugin import ledger, memory as memory_mod, tools, walrus


def _load(raw: str) -> dict:
    return json.loads(raw)


# -- 1. a rule never freezes the fact --------------------------------------


def test_third_correction_still_moves_active_text(populated):
    """Two corrections derive a rule. A third must still change what is believed."""
    fact_id = populated["fact_id"]
    path = populated["ledger_path"]

    before = _load(tools.memory_recall_cited(query="Palembang", ledger_path=path))
    assert "WIB" in before["results"][0]["text"]

    tools.memory_correct(
        fact_id=fact_id,
        correction="The user is in Palembang but travels to Jakarta monthly.",
        reason="schedule confirmed",
        ledger_path=path,
    )

    after = _load(tools.memory_recall_cited(query="Palembang", ledger_path=path))
    hit = [r for r in after["results"] if r["id"] == fact_id][0]
    assert "travels to Jakarta monthly" in hit["text"]
    assert hit["text"] != before["results"][0]["text"]


def test_third_correction_supersedes_old_rule(populated):
    """The stale rule must not keep quoting text the user has since changed."""
    fact_id = populated["fact_id"]
    path = populated["ledger_path"]

    out = _load(
        tools.memory_correct(
            fact_id=fact_id,
            correction="The user is in Palembang, WIB, and deletes nothing.",
            reason="third correction",
            ledger_path=path,
        )
    )
    assert out["rule"] is not None, "a new rule should be derived for the changed fact"

    records = ledger.verify_chain(
        open(path, encoding="utf-8").read().splitlines()
    ).records
    rules = [r for r in records if r.kind == ledger.KIND_RULE]
    assert len(rules) == 2, "old rule kept, new rule appended"
    assert rules[1].fields.get("supersedes") == rules[0].ref
    assert "deletes nothing" in rules[1].fields["text"]

    mem = memory_mod.Memory(records)
    fact = mem.get(fact_id)
    assert fact.rule is rules[1], "projection points at the newest rule"
    assert "deletes nothing" in fact.active_text


def test_explicit_rule_on_later_correction_replaces_derived_one(populated):
    fact_id = populated["fact_id"]
    path = populated["ledger_path"]

    out = _load(
        tools.memory_correct(
            fact_id=fact_id,
            correction="The user is in Palembang, WIB, UTC+7 always.",
            rule="Always store timezone with the city.",
            ledger_path=path,
        )
    )
    assert out["rule"] is not None
    rules = ledger.verify_chain(open(path, encoding="utf-8").read().splitlines()).records
    latest = [r for r in rules if r.kind == ledger.KIND_RULE][-1]
    assert latest.fields["text"] == "Always store timezone with the city."


def test_first_two_corrections_do_not_derived_duplicate_rule(populated):
    path = populated["ledger_path"]
    records = ledger.verify_chain(open(path, encoding="utf-8").read().splitlines()).records
    rules = [r for r in records if r.kind == ledger.KIND_RULE]
    assert len(rules) == 1


# -- 2. memory_import ------------------------------------------------------


MEMORY_MD = """# memory

Entry one about the deployment target. It has two sentences.

§

Entry two about the user's editor of choice.

§

Entry three about coffee.
"""


def test_import_writes_obs_lines(tmp_path, ledger_path):
    src = tmp_path / "MEMORY.md"
    src.write_text(MEMORY_MD, encoding="utf-8")

    out = _load(tools.memory_import(path=str(src), ledger_path=ledger_path))
    assert out["ok"] is True
    assert out["imported"] == 3
    assert out["skipped_existing"] == 0

    mem = memory_mod.Memory(
        ledger.verify_chain(open(ledger_path, encoding="utf-8").read().splitlines()).records
    )
    facts = mem.facts()
    assert len(facts) == 3
    assert all(f.ob.fields["source"] == "memory_md" for f in facts)
    assert all(f.topic.startswith("memory_md:") for f in facts)
    # Wrapped lines are joined back into one ledger line.
    assert facts[0].original_text.startswith("Entry one about the deployment")


def test_import_is_idempotent(tmp_path, ledger_path):
    src = tmp_path / "MEMORY.md"
    src.write_text(MEMORY_MD, encoding="utf-8")

    first = _load(tools.memory_import(path=str(src), ledger_path=ledger_path))
    second = _load(tools.memory_import(path=str(src), ledger_path=ledger_path))

    assert first["imported"] == 3
    assert second["imported"] == 0
    assert second["skipped_existing"] == 3
    lines = [l for l in open(ledger_path, encoding="utf-8").read().splitlines() if l.strip()]
    assert len(lines) == 3, "no duplicate obs lines"


def test_import_survives_reformatting_without_duplicating(tmp_path, ledger_path):
    src = tmp_path / "MEMORY.md"
    src.write_text(MEMORY_MD, encoding="utf-8")
    tools.memory_import(path=str(src), ledger_path=ledger_path)

    # Same words, different wrapping and punctuation spacing.
    src.write_text(MEMORY_MD.replace("Entry two about", "Entry  two about"), encoding="utf-8")
    out = _load(tools.memory_import(path=str(src), ledger_path=ledger_path))
    assert out["imported"] == 0


def test_import_dry_run_writes_nothing(tmp_path, ledger_path):
    src = tmp_path / "MEMORY.md"
    src.write_text(MEMORY_MD, encoding="utf-8")
    out = _load(tools.memory_import(path=str(src), ledger_path=ledger_path, dry_run=True))
    assert out["imported"] == 3
    assert not os.path.exists(ledger_path)


def test_import_source_is_read_only(tmp_path, ledger_path):
    src = tmp_path / "MEMORY.md"
    src.write_text(MEMORY_MD, encoding="utf-8")
    before = src.read_text(encoding="utf-8")
    stat_before = src.stat()

    tools.memory_import(path=str(src), ledger_path=ledger_path)

    assert src.read_text(encoding="utf-8") == before
    assert src.stat().st_size == stat_before.st_size
    assert not os.access(str(src) + ".tmp", os.F_OK)


def test_import_missing_file_returns_error(tmp_path, ledger_path):
    out = _load(tools.memory_import(path=str(tmp_path / "nope.md"), ledger_path=ledger_path))
    assert out["ok"] is False
    assert out["imported"] == 0


def test_import_skips_markdown_headings(tmp_path, ledger_path):
    src = tmp_path / "MEMORY.md"
    src.write_text("# Heading only\n\n§\n\nReal entry here.\n", encoding="utf-8")
    out = _load(tools.memory_import(path=str(src), ledger_path=ledger_path))
    assert out["imported"] == 1


# -- 3. namespace isolation ------------------------------------------------


def test_default_namespace_is_plugin_own(monkeypatch):
    monkeypatch.delenv("WALRUS_NAMESPACE", raising=False)
    assert walrus.namespace() == "hermes-walrus-memory"


def test_custom_namespace_is_honoured(monkeypatch):
    monkeypatch.setenv("WALRUS_NAMESPACE", "hermes-demo-v1")
    assert walrus.namespace() == "hermes-demo-v1"


def test_recallspend_namespaces_are_refused(monkeypatch):
    """Writing into a live app's ledger would corrupt it. Never allowed."""
    for foreign in ("recallspend-ledger", "recallspend-rules", "RecallSpend-Ledger"):
        monkeypatch.setenv("WALRUS_NAMESPACE", foreign)
        assert walrus.namespace() == "hermes-walrus-memory"


def test_client_uses_resolved_namespace(monkeypatch):
    monkeypatch.setenv("WALRUS_DELEGATE_KEY", "dummy-key")
    monkeypatch.setenv("WALRUS_ACCOUNT_ID", "0xdummy")
    monkeypatch.setenv("WALRUS_NAMESPACE", "hermes-demo-v1")
    assert walrus.WalrusClient().namespace == "hermes-demo-v1"

    monkeypatch.setenv("WALRUS_NAMESPACE", "recallspend-ledger")
    assert walrus.WalrusClient().namespace == "hermes-walrus-memory"


def test_verify_reports_namespace(ledger_path):
    tools.memory_observe(fact="namespace should be visible", ledger_path=ledger_path)
    out = _load(tools.walrus_verify(ledger_path=ledger_path))
    assert out["namespace"] == "hermes-walrus-memory"


# -- 4. offline safety while credentials are present ----------------------


def test_write_survives_unreachable_relay(monkeypatch, ledger_path):
    """Credentials set, relay dead: the line still lands locally as pending."""
    monkeypatch.setenv("WALRUS_DELEGATE_KEY", "dummy-key")
    monkeypatch.setenv("WALRUS_ACCOUNT_ID", "0xdummy")
    monkeypatch.setenv("MEMWAL_SERVER_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("WALRUS_HTTP_TIMEOUT", "0.2")

    out = _load(tools.memory_observe(fact="offline write test", topic="offline", ledger_path=ledger_path))
    assert out["ok"] is True
    assert out["sync"] == "pending"

    verify = _load(tools.walrus_verify(ledger_path=ledger_path))
    assert verify["chain_ok"] is True
    assert verify["pending"] == 1
