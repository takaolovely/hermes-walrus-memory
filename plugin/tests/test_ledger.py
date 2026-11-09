"""Hash chain: integrity, tamper detection, and the metadata-not-hashed rule."""

from __future__ import annotations

import pytest

from plugin import ledger


def make(kind, prev, seq, fields):
    return ledger.build(kind, prev, seq, fields)


def test_clean_strips_pipe_and_newlines():
    assert ledger.clean("a|b\nc\td") == "a b c d"
    assert "|" not in ledger.clean("x|y")
    assert len(ledger.clean("a" * 100, 10)) == 10


def test_chain_builds_and_verifies():
    first = make(ledger.KIND_OBS, "00000000", 1, {"id": "o1", "topic": "t", "text": "hello"})
    second = make(ledger.KIND_OBS, first.hash, 2, {"id": "o2", "topic": "t", "text": "world"})
    lines = [first.encode(), second.encode()]
    result = ledger.verify_chain(lines)
    assert result.ok is True
    assert result.lines == 2
    assert result.records[1].prev == first.hash


def test_hash_is_deterministic():
    a = make(ledger.KIND_OBS, "00000000", 1, {"id": "o1", "text": "same"})
    b = make(ledger.KIND_OBS, "00000000", 1, {"id": "o1", "text": "same"})
    assert a.hash == b.hash
    assert len(a.hash) == 8


def test_edited_line_breaks_chain():
    first = make(ledger.KIND_OBS, "00000000", 1, {"id": "o1", "text": "hello"})
    second = make(ledger.KIND_OBS, first.hash, 2, {"id": "o2", "text": "world"})
    tampered = first.encode().replace("text=hello", "text=hacked")
    result = ledger.verify_chain([tampered, second.encode()])
    assert result.ok is False
    assert result.broken_at == 1
    assert "hash mismatch" in result.reason


def test_deleted_line_breaks_chain():
    first = make(ledger.KIND_OBS, "00000000", 1, {"id": "o1", "text": "a"})
    second = make(ledger.KIND_OBS, first.hash, 2, {"id": "o2", "text": "b"})
    third = make(ledger.KIND_OBS, second.hash, 3, {"id": "o3", "text": "c"})
    result = ledger.verify_chain([first.encode(), third.encode()])
    assert result.ok is False
    assert result.broken_at == 2
    assert "seq gap" in result.reason


def test_reordered_lines_break_chain():
    first = make(ledger.KIND_OBS, "00000000", 1, {"id": "o1", "text": "a"})
    second = make(ledger.KIND_OBS, first.hash, 2, {"id": "o2", "text": "b"})
    result = ledger.verify_chain([second.encode(), first.encode()])
    assert result.ok is False


def test_transport_metadata_is_not_hashed():
    """Syncing a line to Walrus must not invalidate the chain."""
    record = make(ledger.KIND_OBS, "00000000", 1, {"id": "o1", "text": "hello"})
    before = record.hash
    record.sync = "synced"
    record.walrus = "abc123digest"
    assert record.is_intact() is True
    assert ledger.verify_chain([record.encode()]).ok is True

    reopened = ledger.decode(record.encode())
    assert reopened.sync == "synced"
    assert reopened.walrus == "abc123digest"
    assert reopened.hash == before


def test_metadata_inside_fields_is_stripped_at_build():
    record = make(ledger.KIND_OBS, "00000000", 1, {"id": "o1", "text": "x", "sync": "evil", "walrus": "evil"})
    assert "sync" not in record.fields
    assert "walrus" not in record.fields


def test_decode_rejects_garbage():
    assert ledger.decode("") is None
    assert ledger.decode("nonsense|a=b") is None
    assert ledger.decode("obs|text=x") is None  # no hash


def test_decode_roundtrip_preserves_fields():
    record = make(ledger.KIND_FIX, "abcd1234", 7, {"id": "f1", "target": "o1", "text": "corrected"})
    back = ledger.decode(record.encode())
    assert back.kind == ledger.KIND_FIX
    assert back.seq == 7
    assert back.prev == "abcd1234"
    assert back.fields["target"] == "o1"
    assert back.ref == "fix#07"


def test_build_rejects_unknown_kind():
    with pytest.raises(ValueError):
        make("bogus", "00000000", 1, {"id": "x"})


def test_ref_width_is_stable():
    record = make(ledger.KIND_RULE, "00000000", 4, {"id": "r1"})
    assert record.ref == "rule#04"
