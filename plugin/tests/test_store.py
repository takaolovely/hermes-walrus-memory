"""Store: durable append, position bookkeeping, unchanged live MEMORY.md."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugin import ledger, store


def test_path_precedence(monkeypatch, tmp_path):
    """Every candidate must land inside the confined plugin data directory."""
    home = tmp_path / "home"
    root = home / "plugin-data" / "hermes-walrus-memory"
    monkeypatch.setenv("HERMES_HOME", str(home))

    monkeypatch.setenv("WALRUS_LEDGER_PATH", str(root / "a.log"))
    assert store.resolve_path().name == "a.log"

    monkeypatch.delenv("WALRUS_LEDGER_PATH")
    assert store.resolve_path() == root / store.DEFAULT_FILENAME

    explicit = root / "explicit.log"
    assert store.resolve_path(str(explicit)) == explicit


def test_path_outside_hermes_home_is_refused(monkeypatch, tmp_path):
    """A path outside the plugin data dir must raise, not write.

    This is the regression test for the review finding: a model-supplied path
    used to reach any file on disk, so an append would write through it.
    """
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HERMES_HOME", str(home))

    outside = tmp_path / "somewhere-else.log"
    with pytest.raises(ValueError):
        store.resolve_path(str(outside))
    with pytest.raises(ValueError):
        store.LedgerStore(str(outside))

    monkeypatch.setenv("WALRUS_LEDGER_PATH", str(outside))
    with pytest.raises(ValueError):
        store.resolve_path()


def test_traversal_out_of_data_dir_is_refused(monkeypatch, tmp_path):
    """../../ escapes must be rejected after resolution, not lexically."""
    home = tmp_path / "home"
    root = home / "plugin-data" / "hermes-walrus-memory"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HERMES_HOME", str(home))

    sneaky = str(root / ".." / ".." / ".." / "escaped.log")
    with pytest.raises(ValueError):
        store.resolve_path(sneaky)


def test_append_creates_file_and_positions(ledger_path):
    s = store.LedgerStore()
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
    s = store.LedgerStore()
    s.append_fields(ledger.KIND_OBS, {"id": "o1", "text": "x"})
    # Re-open with a fresh object: the data is on disk, not in memory.
    assert len(store.LedgerStore().read_lines()) == 1


def test_verify_on_empty_ledger(ledger_path):
    result = store.LedgerStore().verify()
    assert result.ok is True
    assert result.lines == 0


def test_rewrite_is_atomic_and_preserves_order(ledger_path):
    s = store.LedgerStore()
    s.append_fields(ledger.KIND_OBS, {"id": "o1", "text": "a"})
    s.append_fields(ledger.KIND_OBS, {"id": "o2", "text": "b"})
    records = s.read_records()
    records[0].sync = "synced"
    records[0].walrus = "digest1"
    s.rewrite(records)

    reread = store.LedgerStore().read_records()
    assert [r.id for r in reread] == ["o1", "o2"]
    assert reread[0].sync == "synced"
    assert reread[0].walrus == "digest1"


def test_no_tmp_file_left_behind(ledger_path):
    s = store.LedgerStore()
    s.append_fields(ledger.KIND_OBS, {"id": "o1", "text": "a"})
    s.rewrite(s.read_records())
    leftovers = list(Path(ledger_path).parent.glob("*.tmp"))
    assert leftovers == []


def test_ledger_does_not_touch_memory_md(ledger_path, isolated_home):
    s = store.LedgerStore()
    for i in range(5):
        s.append_fields(ledger.KIND_OBS, {"id": f"o{i}", "text": f"line {i}"})
    assert isolated_home["memory_md"].read_text(encoding="utf-8") == "# memory\n\n- existing fact\n"
