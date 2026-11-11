"""Load the plugin the way Hermes does and drive every tool through the
registered handlers. Run with:  python tools/load_check.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class FakeCtx:
    """Mirrors hermes_cli.plugins.PluginContext.register_tool's contract."""

    def __init__(self):
        self.tools = {}

    def register_tool(self, name, toolset, schema, handler, **kwargs):
        self.tools[name] = {"toolset": toolset, "schema": schema, "handler": handler, **kwargs}


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="walrus-load-")
    os.environ["HERMES_HOME"] = tmp
    # The ledger may only live inside <HERMES_HOME>/plugin-data/<plugin>/, so
    # point the env var there instead of straight at the temp dir root.
    ledger_dir = os.path.join(tmp, "plugin-data", "hermes-walrus-memory")
    os.makedirs(ledger_dir, exist_ok=True)
    os.environ["WALRUS_LEDGER_PATH"] = os.path.join(ledger_dir, "walrus-memory.log")
    os.environ.pop("WALRUS_DELEGATE_KEY", None)
    os.environ.pop("WALRUS_ACCOUNT_ID", None)
    os.environ.pop("WALRUS_NAMESPACE", None)

    import plugin

    ctx = FakeCtx()
    plugin.register(ctx)

    expected = {
        "memory_observe",
        "memory_correct",
        "memory_recall_cited",
        "memory_provenance_diff",
        "memory_import",
        "walrus_sync",
        "walrus_verify",
    }
    assert set(ctx.tools) == expected, f"registered {set(ctx.tools)}"
    for name, spec in ctx.tools.items():
        assert spec["toolset"] == "walrus_memory"
        assert spec["schema"]["name"] == name
        assert callable(spec["handler"])
    print(f"registered {len(ctx.tools)} tools: {', '.join(sorted(ctx.tools))}")

    def run(name, args):
        raw = ctx.tools[name]["handler"](args)
        assert isinstance(raw, str), f"{name} returned {type(raw)}"
        return json.loads(raw)

    obs = run("memory_observe", {"fact": "The user ships on Vercel.", "topic": "deploy"})
    print("observe   ->", obs["ref"], "sync=" + obs["sync"])

    fix = run("memory_correct", {
        "fact_id": obs["id"],
        "correction": "The user ships on Fly.io and Vercel.",
        "reason": "user corrected the platform",
    })
    print("correct   ->", fix["ref"], "previous kept:", fix["previous"])

    run("memory_correct", {
        "fact_id": obs["id"],
        "correction": "The user ships on Fly.io first, Vercel for static.",
        "reason": "refined",
    })

    recall = run("memory_recall_cited", {"query": "deploy platform"})
    print("recall    ->", recall["results"][0]["citation"])
    print("            ", recall["results"][0]["text"])

    diff = run("memory_provenance_diff", {"fact_id": obs["id"]})
    for line in diff["narrative"]:
        print("timeline  ->", line)

    # memory_import reads <hermes_home>/memories/MEMORY.md and nothing else.
    memories_dir = Path(tmp) / "memories"
    memories_dir.mkdir(parents=True, exist_ok=True)
    memory_md = memories_dir / "MEMORY.md"
    memory_md.write_text(
        "VPS runs Ubuntu with UFW enabled.\n\n\u00a7\n\nUser prefers direct answers.\n",
        encoding="utf-8",
    )
    before = memory_md.read_bytes()
    imp = run("memory_import", {})
    print("import    -> imported =", imp["imported"], "skipped =", imp["skipped_existing"])
    again = run("memory_import", {})
    print("import x2 -> imported =", again["imported"], "skipped =", again["skipped_existing"])
    assert memory_md.read_bytes() == before, "import must not modify MEMORY.md"

    sync = run("walrus_sync", {"action": "push"})
    print("sync      -> ok =", sync["ok"], "|", str(sync.get("error", ""))[:60])

    verify = run("walrus_verify", {})
    print("verify    -> chain_ok =", verify["chain_ok"], "lines =", verify["lines"], "mode =", verify["mode"])

    assert fix["previous"] == "The user ships on Vercel."
    assert recall["results"][0]["citation"].startswith("rule#")
    assert verify["chain_ok"] is True
    assert imp["imported"] == 2 and again["imported"] == 0
    assert sync["ok"] is False and sync["mode"] == "local"
    print("\nALL SEVEN TOOLS OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
