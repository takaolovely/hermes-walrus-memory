"""Store: durable append, position bookkeeping, unchanged live MEMORY.md."""

from __future__ import annotations

from pathlib import Path

from plugin import ledger, store


def test_path_precedence(monkeypatch, tmp_path):
    monkeypatch.setenv("WALRUS_LEDGER_PATH", str(tmp_path / "a.log"))
    assert store.resolve_path().name == "a.log"

    monkeypatch.delenv("WALRUS_LEDGER_PATH")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    assert store.resolve_path() == tmp_path / "home" / store.DEFAULT_FILENAME

    explicit = tmp_path / "explicit.log"
    assert store.resolve_path(str(explicit)) == explicit


def test_append_creates_file_and_positions(ledger_path):
    s = store.LedgerStore(ledger_path)
    assert s.read_lines() == []
    seq, prev = s.next_position()
    assert (seq, prev) == (1, "00000000")

    s.append_fields(ledger.KIND_OBS, {"id": "o1", "text": "first"})
    seq, prev = s.next_position()
    assert seq == 2
    assert prev != "00000000"

    s.append_fields(ledger.KIND_OBS, {"id": "o2", "text": "second"})
    assert len(s.read_lines()) == 2
    assert Path(ledger_path).exists()


def test_writes_are_durable(ledger_path):
    s = store.LedgerStore(ledger_path)
    s.append_fields(ledger.KIND_OBS, {"id": "o1", "text": "x"})
    # Re-open with a fresh object: the data is on disk, not in memory.
    assert len(store.LedgerStore(ledger_path).read_lines()) == 1


def test_verify_on_empty_ledger(ledger_path):
    result = store.LedgerStore(ledger_path).verify()
    assert result.ok is True
    assert result.lines == 0


def test_rewrite_is_atomic_and_preserves_order(ledger_path):
    s = store.LedgerStore(ledger_path)
    s.append_fields(ledger.KIND_OBS, {"id": "o1", "text": "a"})
    s.append_fields(ledger.KIND_OBS, {"id": "o2", "text": "b"})
    records = s.read_records()
    records[0].sync = "synced"
    records[0].walrus = "digest1"
    s.rewrite(records)

    reread = store.LedgerStore(ledger_path).read_records()
    assert [r.id for r in reread] == ["o1", "o2"]
    assert reread[0].sync == "synced"
    assert reread[0].walrus == "digest1"


def test_no_tmp_file_left_behind(ledger_path):
    s = store.LedgerStore(ledger_path)
    s.append_fields(ledger.KIND_OBS, {"id": "o1", "text": "a"})
    s.rewrite(s.read_records())
    leftovers = list(Path(ledger_path).parent.glob("*.tmp"))
    assert leftovers == []


def test_ledger_does_not_touch_memory_md(ledger_path, isolated_home):
    s = store.LedgerStore(ledger_path)
    for i in range(5):
        s.append_fields(ledger.KIND_OBS, {"id": f"o{i}", "text": f"line {i}"})
    assert isolated_home["memory_md"].read_text(encoding="utf-8") == "# memory\n\n- existing fact\n"
