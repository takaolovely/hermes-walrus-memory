"""Shared fixtures. Every test runs against a temporary ledger path and a
temporary HERMES_HOME, so the live ~/.hermes/MEMORY.md is never touched.
"""

from __future__ import annotations

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
    memory_file = home / "MEMORY.md"
    memory_file.write_text("# memory\n\n- existing fact\n", encoding="utf-8")

    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("WALRUS_LEDGER_PATH", str(tmp_path / "walrus-memory.log"))
    for key in (
        "WALRUS_DELEGATE_KEY",
        "WALRUS_ACCOUNT_ID",
        "MEMWAL_SERVER_URL",
        "WALRUS_HTTP_TIMEOUT",
        "WALRUS_NAMESPACE",
    ):
        monkeypatch.delenv(key, raising=False)

    yield {"home": home, "ledger": Path(os.environ["WALRUS_LEDGER_PATH"]), "memory_md": memory_file}

    # The live memory file must be byte-identical after every test.
    assert memory_file.read_text(encoding="utf-8") == "# memory\n\n- existing fact\n"


@pytest.fixture
def ledger_path(isolated_home):
    return str(isolated_home["ledger"])


@pytest.fixture
def populated(ledger_path):
    """One observation corrected twice, which derives a rule."""
    first = tools.memory_observe(
        fact="The user is in Jakarta.", topic="user.timezone", ledger_path=ledger_path
    )
    import json

    fact_id = json.loads(first)["id"]
    tools.memory_correct(
        fact_id=fact_id,
        correction="The user is in Palembang.",
        reason="user corrected the city",
        ledger_path=ledger_path,
    )
    tools.memory_correct(
        fact_id=fact_id,
        correction="The user is in Palembang, WIB (UTC+7).",
        reason="timezone confirmed",
        ledger_path=ledger_path,
    )
    return {"fact_id": fact_id, "ledger_path": ledger_path}
