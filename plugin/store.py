"""Local append-only store with write-ahead durability.

The ledger file is the source of truth in zero-config mode. Writes are
synchronous and fsync'd before any network attempt, so a Walrus relay timeout
can never cost a memory line.
"""

from __future__ import annotations

try:  # POSIX file locking. Absent on Windows, where _lock is a no-op.
    import fcntl
except ImportError:  # pragma: no cover - Windows only
    fcntl = None  # type: ignore[assignment]
import os
from pathlib import Path
from typing import List, Optional

from . import ledger

DEFAULT_FILENAME = "walrus-memory.log"
ENV_LEDGER_PATH = "WALRUS_LEDGER_PATH"
PLUGIN_DATA_DIR = "plugin-data"
PLUGIN_SLUG = "hermes-walrus-memory"


def hermes_home() -> Path:
    """Hermes home directory, preferring the loader's own resolver.

    ``hermes_cli.config.get_hermes_home`` is the authoritative answer inside a
    running Hermes. Imported lazily so this plugin still loads in a bare
    interpreter (tests, the load_check script) without hermes-agent installed.
    """
    try:
        from hermes_cli.config import get_hermes_home  # type: ignore[import-not-found]

        return Path(get_hermes_home()).expanduser()
    except Exception:  # noqa: BLE001 - any failure falls back to the env var
        return Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes")).expanduser()


def ledger_root() -> Path:
    """The only directory a ledger may live in."""
    return (hermes_home() / PLUGIN_DATA_DIR / PLUGIN_SLUG).resolve()


def resolve_path(explicit: Optional[str] = None) -> Path:
    """Ledger location, confined to Hermes home.

    Precedence: explicit arg, ``WALRUS_LEDGER_PATH``, then the plugin data dir.
    Every candidate is resolved and rejected unless it sits inside
    ``<hermes_home>/plugin-data/hermes-walrus-memory/``. Without this check a
    caller could point the ledger at any file on disk and the append would
    write through it.
    """
    root = ledger_root()
    candidate = explicit or os.environ.get(ENV_LEDGER_PATH)
    target = Path(candidate).expanduser().resolve() if candidate else (root / DEFAULT_FILENAME)
    try:
        target.relative_to(root)
    except ValueError:
        raise ValueError(
            f"ledger path must stay inside {root}; refusing to touch {target}"
        ) from None
    return target


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
            if fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                fh.write(line)
                fh.flush()
                os.fsync(fh.fileno())
            finally:
                if fcntl is not None:
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
