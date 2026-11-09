"""hermes-walrus-memory - append-only memory with temporal provenance.

Corrections are appended, never written over, so Hermes can always say what it
believed before you corrected it, plus the exact line it learned the rule from.

Zero config: works as a local tamper-evident hash chain.
With WALRUS_DELEGATE_KEY + WALRUS_ACCOUNT_ID: every line also lands on Walrus.
"""

from __future__ import annotations

from . import tools
from .schemas import (
    MEMORY_CORRECT_SCHEMA,
    MEMORY_IMPORT_SCHEMA,
    MEMORY_OBSERVE_SCHEMA,
    MEMORY_PROVENANCE_DIFF_SCHEMA,
    MEMORY_RECALL_CITED_SCHEMA,
    WALRUS_SYNC_SCHEMA,
    WALRUS_VERIFY_SCHEMA,
)

__version__ = "0.2.0"

_TOOLS = (
    ("memory_observe", MEMORY_OBSERVE_SCHEMA, tools.memory_observe, "🧠"),
    ("memory_correct", MEMORY_CORRECT_SCHEMA, tools.memory_correct, "✏️"),
    ("memory_recall_cited", MEMORY_RECALL_CITED_SCHEMA, tools.memory_recall_cited, "🔎"),
    ("memory_provenance_diff", MEMORY_PROVENANCE_DIFF_SCHEMA, tools.memory_provenance_diff, "🕓"),
    ("walrus_sync", WALRUS_SYNC_SCHEMA, tools.walrus_sync, "🔁"),
    ("walrus_verify", WALRUS_VERIFY_SCHEMA, tools.walrus_verify, "✅"),
    ("memory_import", MEMORY_IMPORT_SCHEMA, tools.memory_import, "📥"),
)


def register(ctx) -> None:
    """Register the memory tools. Called once by the Hermes plugin loader.

    This plugin deliberately does not touch ``memory.provider``. It runs
    alongside the built-in MEMORY.md, adding a provenance layer on top, so
    installing or removing it never changes how Hermes already remembers.

    Every handler is wrapped in ``tools._guard``. A memory tool that raises into
    the agent loop breaks the conversation it was supposed to help, so failures
    come back as an ``ok: false`` result naming what went wrong.
    """
    for name, schema, handler, emoji in _TOOLS:
        ctx.register_tool(
            name=name,
            toolset="walrus_memory",
            schema=schema,
            handler=lambda args, _n=name, _h=handler, **kw: tools._guard(
                _n, _h, {k: v for k, v in (args or {}).items()}
            ),
            emoji=emoji,
        )
