"""Local append-only store with write-ahead durability.

The ledger file is the source of truth in zero-config mode. Writes are
synchronous and fsync'd before any network attempt, so a Walrus relay timeout
can never cost a memory line.
"""

from __future__ import annotations

import fcntl
import os
from pathlib import Path
from typing import List, Optional

from . import ledger

DEFAULT_FILENAME = "walrus-memory.log"
ENV_LEDGER_PATH = "WALRUS_LEDGER_PATH"


def resolve_path(explicit: Optional[str] = None) -> Path:
    """Ledger location, in precedence order: explicit arg, env var, HERMES_HOME."""
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get(ENV_LEDGER_PATH)
    if env:
        return Path(env).expanduser()
    home = os.environ.get("HERMES_HOME") or str(Path.home() / ".hermes")
    return Path(home).expanduser() / DEFAULT_FILENAME


class LedgerStore:
    """Append-only file with an exclusive lock during writes."""

    def __init__(self, path: Optional[str] = None):
        self.path = resolve_path(path)

    # -- reading -----------------------------------------------------------
    def read_lines(self) -> List[str]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as fh:
            return [line.rstrip("\n") for line in fh if line.strip()]

    def read_records(self) -> List[ledger.Record]:
        out: List[ledger.Record] = []
        for line in self.read_lines():
            record = ledger.decode(line)
            if record is not None:
                out.append(record)
        return out

    # -- writing -----------------------------------------------------------
    def append(self, record: ledger.Record) -> ledger.Record:
        """Durably append one record and return it."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = record.encode() + "\n"
        with self.path.open("a+", encoding="utf-8") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                fh.write(line)
                fh.flush()
                os.fsync(fh.fileno())
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        return record

    def next_position(self) -> tuple[int, str]:
        """Return (seq, prev_hash) for the next line."""
        records = self.read_records()
        if not records:
            return 1, "00000000"
        last = records[-1]
        return last.seq + 1, last.hash

    def append_fields(self, kind: str, fields: dict, sync: str = "local", walrus: str = "") -> ledger.Record:
        seq, prev = self.next_position()
        record = ledger.build(kind, prev, seq, fields, sync=sync, walrus=walrus)
        return self.append(record)

    # -- maintenance -------------------------------------------------------
    def rewrite(self, records: List[ledger.Record]) -> None:
        """Replace the file atomically. Only used by sync and import."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for record in records:
                fh.write(record.encode() + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)

    def verify(self) -> ledger.VerifyResult:
        return ledger.verify_chain(self.read_lines())
