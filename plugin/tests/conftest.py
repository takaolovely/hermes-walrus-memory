"""Shared fixtures. Every test runs against a temporary ledger path and a
temporary HERMES_HOME, so the live ~/.hermes/MEMORY.md is never touched.

The ledger and memory paths live inside that temporary home on purpose: the
plugin now refuses to read or write outside <hermes_home>/plugin-data/ and
<hermes_home>/memories/, so a fixture pointing anywhere else would be testing
a code path that no longer exists.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_DIR.parent))

from plugin import ledger, memory as memory_mod, store, tools, walrus  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Point every path at tmp_path and strip Walrus credentials."""
    home = tmp_path / "hermes-home"
    home.mkdir(parents=True, exist_ok=True)

    # The confined locations the plugin resolves to by default.
    ledger_dir = home / "plugin-data" / "hermes-walrus-memory"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    memories_dir = home / "memories"
    memories_dir.mkdir(parents=True, exist_ok=True)

    memory_file = memories_dir / "MEMORY.md"
    memory_file.write_text("# memory\n\n- existing fact\n", encoding="utf-8")

    ledger_file = ledger_dir / "walrus-memory.log"

    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("WALRUS_LEDGER_PATH", str(ledger_file))
    monkeypatch.delenv("HERMES_MEMORY_MD", raising=False)
    for key in (
        "WALRUS_DELEGATE_KEY",
        "WALRUS_ACCOUNT_ID",
        "MEMWAL_SERVER_URL",
        "WALRUS_HTTP_TIMEOUT",
        "WALRUS_NAMESPACE",
    ):
        monkeypatch.delenv(key, raising=False)

    yield {"home": home, "ledger": ledger_file, "memory_md": memory_file}

    # The live memory file must be byte-identical after every test.
    assert memory_file.read_text(encoding="utf-8") == "# memory\n\n- existing fact\n"


@pytest.fixture
def ledger_path(isolated_home):
    return str(isolated_home["ledger"])


@pytest.fixture
def import_source(isolated_home, monkeypatch):
    """A separate MEMORY.md inside memories/, for the import tests.

    It lives in the same confined directory the resolver allows, so the tests
    exercise the real confinement path instead of bypassing it. Keeping it
    separate from the autouse fixture's file means the "live MEMORY.md is never
    modified" assertion stays meaningful while import tests rewrite their own
    source.
    """
    src = isolated_home["home"] / "memories" / "IMPORT_SOURCE.md"
    monkeypatch.setenv("HERMES_MEMORY_MD", str(src))
    return src


@pytest.fixture
def populated(ledger_path):
    """One observation corrected twice, which derives a rule."""
    first = tools.memory_observe(fact="The user is in Jakarta.", topic="user.timezone")
    fact_id = json.loads(first)["id"]
    tools.memory_correct(
        fact_id=fact_id,
        correction="The user is in Palembang.",
        reason="user corrected the city",
    )
    tools.memory_correct(
        fact_id=fact_id,
        correction="The user is in Palembang, WIB (UTC+7).",
        reason="timezone confirmed",
    )
    return {"fact_id": fact_id, "ledger_path": ledger_path}
