"""Ledger line codec and SHA-256 hash chain for hermes-walrus-memory.

Every memory record is one pipe-delimited line:

    kind|prev=<8hex>|hash=<8hex>|seq=<n>|ts=<iso>|id=<id>|...fields...
    sync=pending|walrus=<digest or empty>

Design rules that matter:

1. Lines are append-only. A correction never rewrites the line it corrects, it
   is a new ``fix|`` line that points at the ``obs|`` id.
2. ``hash`` is SHA-256 over the canonical payload (kind + all fields in
   insertion order) plus ``prev``. Tampering with any earlier line breaks every
   later hash, which is what ``walrus_verify`` walks.
3. ``sync=`` and ``walrus=`` are transport metadata. They live in the line but
   are excluded from the hash payload, because the Walrus blob digest is only
   known after the line is written to the relay and a re-hash after a sync must
   not invalidate the chain.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

KIND_OBS = "obs"
KIND_FIX = "fix"
KIND_RULE = "rule"
KINDS = (KIND_OBS, KIND_FIX, KIND_RULE)

# Fields that are transport metadata, never part of the hash payload.
META_FIELDS = ("sync", "walrus")

_FIELD_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
_SAFE_RE = re.compile(r"[|\n\r\t]")


def clean(value: Any, max_len: int = 200) -> str:
    """Make a value safe for a single pipe-delimited line."""
    s = str("" if value is None else value)
    s = _SAFE_RE.sub(" ", s)
    s = " ".join(s.split())
    return s[:max_len]


def short_hash(text: str) -> str:
    """First 8 hex chars of SHA-256, the width used by the chain."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Record:
    """One ledger line, parsed."""

    kind: str
    seq: int
    prev: str
    hash: str
    fields: Dict[str, str] = field(default_factory=dict)
    sync: str = "local"
    walrus: str = ""

    # -- ids and text ------------------------------------------------------
    @property
    def id(self) -> str:
        return self.fields.get("id", "")

    @property
    def text(self) -> str:
        return self.fields.get("text", "")

    @property
    def ts(self) -> str:
        return self.fields.get("at", "")

    @property
    def ref(self) -> str:
        """Citation handle, e.g. rule#04."""
        return f"{self.kind}#{self.seq:02d}"

    # -- hashing -----------------------------------------------------------
    def payload(self) -> str:
        """Canonical string the hash covers. Excludes transport metadata."""
        parts = [self.kind, f"prev={self.prev}", f"seq={self.seq}"]
        for key, value in self.fields.items():
            if key in META_FIELDS:
                continue
            parts.append(f"{key}={value}")
        return "|".join(parts)

    def compute_hash(self) -> str:
        return short_hash(self.payload())

    def is_intact(self) -> bool:
        return self.compute_hash() == self.hash

    # -- serialisation -----------------------------------------------------
    def encode(self) -> str:
        parts = [self.kind, f"prev={self.prev}", f"hash={self.hash}", f"seq={self.seq}"]
        for key, value in self.fields.items():
            parts.append(f"{key}={value}")
        parts.append(f"sync={self.sync}")
        if self.walrus:
            parts.append(f"walrus={self.walrus}")
        return "|".join(parts)


def decode(line: str) -> Optional[Record]:
    """Parse one line. Returns None for blank or malformed lines."""
    raw = (line or "").strip()
    if not raw:
        return None
    parts = raw.split("|")
    kind = parts[0]
    if kind not in KINDS:
        return None
    record = Record(kind=kind, seq=0, prev="", hash="")
    for part in parts[1:]:
        m = _FIELD_RE.match(part)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        if key == "prev":
            record.prev = value
        elif key == "hash":
            record.hash = value
        elif key == "seq":
            try:
                record.seq = int(value)
            except ValueError:
                return None
        elif key == "sync":
            record.sync = value or "local"
        elif key == "walrus":
            record.walrus = value
        else:
            record.fields[key] = value
    if not record.hash:
        return None
    return record


def build(
    kind: str,
    prev: str,
    seq: int,
    fields: Dict[str, Any],
    sync: str = "local",
    walrus: str = "",
) -> Record:
    """Create a hashed record ready to append."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind: {kind}")
    clean_fields = {k: clean(v) for k, v in fields.items() if k not in META_FIELDS}
    record = Record(kind=kind, seq=seq, prev=prev, hash="", fields=clean_fields, sync=sync, walrus=walrus)
    record.hash = record.compute_hash()
    return record


@dataclass
class VerifyResult:
    ok: bool
    lines: int
    broken_at: Optional[int] = None
    reason: str = ""
    records: List[Record] = field(default_factory=list)


def verify_chain(lines: List[str]) -> VerifyResult:
    """Walk the chain: every hash must match, every prev must match the last hash."""
    records: List[Record] = []
    prev_hash = "00000000"
    for index, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        record = decode(line)
        if record is None:
            return VerifyResult(False, len(records), index, "malformed line", records)
        if record.seq != index:
            return VerifyResult(False, len(records), index, f"seq gap: expected {index}, got {record.seq}", records)
        if record.prev != prev_hash:
            return VerifyResult(False, len(records), index, f"prev mismatch at {record.ref}", records)
        if not record.is_intact():
            return VerifyResult(False, len(records), index, f"hash mismatch at {record.ref}", records)
        records.append(record)
        prev_hash = record.hash
    return VerifyResult(True, len(records), None, "", records)
