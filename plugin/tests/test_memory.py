"""Memory semantics: corrections never overwrite, citations are built from real
line refs, and the projection is recomputed from the file every time."""

from __future__ import annotations

import json

from plugin import ledger, memory as memory_mod, store


def build_memory(records):
    return memory_mod.Memory(records)


def test_observation_then_correction_keeps_both(ledger_path):
    s = store.LedgerStore()
    s.append_fields(ledger.KIND_OBS, {"id": "obs-1", "topic": "tz", "text": "Jakarta", "at": "2026-01-01T00:00:00+00:00"})
    s.append_fields(
        ledger.KIND_FIX,
        {"id": "fix-1", "target": "obs-1", "topic": "tz", "text": "Palembang", "previous": "Jakarta", "at": "2026-01-02T00:00:00+00:00"},
    )
    mem = build_memory(s.read_records())
    fact = mem.get("obs-1")
    assert fact.original_text == "Jakarta"
    assert fact.active_text == "Palembang"
    assert fact.corrected is True
    assert [r.text for r in s.read_records()] == ["Jakarta", "Palembang"]


def test_citation_order_is_rule_fix_obs(ledger_path):
    s = store.LedgerStore()
    s.append_fields(ledger.KIND_OBS, {"id": "obs-1", "topic": "tz", "text": "Jakarta"})
    s.append_fields(ledger.KIND_FIX, {"id": "fix-1", "target": "obs-1", "text": "Palembang"})
    s.append_fields(ledger.KIND_RULE, {"id": "rule-1", "target": "obs-1", "text": "always confirm tz"})
    fact = build_memory(s.read_records()).get("obs-1")
    assert fact.citation() == "rule#03 <- fix#02 <- obs#01"


def test_orphan_fix_is_ignored_not_crashing(ledger_path):
    s = store.LedgerStore()
    s.append_fields(ledger.KIND_FIX, {"id": "fix-1", "target": "missing", "text": "x"})
    mem = build_memory(s.read_records())
    assert mem.facts() == []


def test_search_ranks_topic_matches(ledger_path):
    s = store.LedgerStore()
    s.append_fields(ledger.KIND_OBS, {"id": "obs-1", "topic": "deployment", "text": "user deploys on Vercel"})
    s.append_fields(ledger.KIND_OBS, {"id": "obs-2", "topic": "food", "text": "user likes coffee"})
    mem = build_memory(s.read_records())
    hits = mem.search("deployment")
    assert hits[0].id == "obs-1"
    assert all(h.id != "obs-2" for h in hits)


def test_search_empty_query_returns_facts(ledger_path):
    s = store.LedgerStore()
    s.append_fields(ledger.KIND_OBS, {"id": "obs-1", "topic": "a", "text": "x"})
    assert len(build_memory(s.read_records()).search("")) == 1


def test_conflicts_detected_for_same_topic(ledger_path):
    s = store.LedgerStore()
    s.append_fields(ledger.KIND_OBS, {"id": "obs-1", "topic": "editor", "text": "uses vim"})
    s.append_fields(ledger.KIND_OBS, {"id": "obs-2", "topic": "editor", "text": "uses VS Code"})
    conflicts = build_memory(s.read_records()).conflicts()
    assert len(conflicts) == 1
    assert conflicts[0]["topic"] == "editor"
    assert len(conflicts[0]["variants"]) == 2


def test_no_conflict_when_correction_reconciles(ledger_path):
    s = store.LedgerStore()
    s.append_fields(ledger.KIND_OBS, {"id": "obs-1", "topic": "editor", "text": "uses vim"})
    s.append_fields(ledger.KIND_OBS, {"id": "obs-2", "topic": "editor", "text": "uses VS Code"})
    s.append_fields(ledger.KIND_FIX, {"id": "fix-1", "target": "obs-2", "text": "uses vim"})
    conflicts = build_memory(s.read_records()).conflicts()
    assert conflicts == []


def test_timeline_is_chronological(ledger_path):
    s = store.LedgerStore()
    s.append_fields(ledger.KIND_OBS, {"id": "obs-1", "topic": "t", "text": "first", "at": "2026-03-01T00:00:00+00:00"})
    s.append_fields(
        ledger.KIND_FIX,
        {"id": "fix-1", "target": "obs-1", "text": "second", "reason": "wrong", "at": "2026-03-05T00:00:00+00:00"},
    )
    events = build_memory(s.read_records()).timeline("obs-1")
    assert [e["event"] for e in events] == ["observed", "corrected"]
    assert events[0]["at"] < events[1]["at"]
    assert events[1]["reason"] == "wrong"


def test_timeline_unknown_fact_is_empty(ledger_path):
    s = store.LedgerStore()
    assert build_memory(s.read_records()).timeline("nope") == []


def test_needs_rule_threshold():
    assert memory_mod.needs_rule([]) is False
    rec = ledger.build(ledger.KIND_FIX, "00000000", 1, {"id": "f"})
    assert memory_mod.needs_rule([rec]) is False
    assert memory_mod.needs_rule([rec, rec]) is True


def test_stable_topic_key_is_normalised():
    assert memory_mod.stable_topic_key("User  Timezone") == memory_mod.stable_topic_key("user timezone")
    assert len(memory_mod.stable_topic_key("anything")) == 8


def test_dedupe_keeps_first():
    a = ledger.build(ledger.KIND_OBS, "00000000", 1, {"id": "o1", "text": "a"})
    b = ledger.build(ledger.KIND_OBS, a.hash, 2, {"id": "o1", "text": "b"})
    c = ledger.build(ledger.KIND_OBS, "00000000", 3, {"id": "o2", "text": "c"})
    out = memory_mod.dedupe([a, b, c])
    assert [r.text for r in out] == ["a", "c"]


def test_as_dict_shape(ledger_path):
    s = store.LedgerStore()
    s.append_fields(ledger.KIND_OBS, {"id": "obs-1", "topic": "t", "text": "x", "at": "2026-01-01T00:00:00+00:00"})
    payload = build_memory(s.read_records()).get("obs-1").as_dict()
    assert set(payload) >= {"id", "topic", "text", "citation", "line_hash", "observed_at"}
    json.dumps(payload)  # must be JSON serialisable
