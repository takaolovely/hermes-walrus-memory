"""Tool schemas: what the model reads when deciding to call or skip a tool.

These strings are prompt text, not documentation. Each description states when
to call the tool, what it returns, and what it explicitly does not do, because
the model chooses tools from this text alone. Every property names its format so
an id, a topic key and free text cannot be confused for one another.
"""

from __future__ import annotations

MEMORY_OBSERVE_SCHEMA = {
    "name": "memory_observe",
    "description": (
        "Record one fact worth remembering about the user, their preferences, their environment "
        "or a project. Call this when you learn something durable, not for passing conversation. "
        "Observations are append-only and never edited, so record what you actually learned even "
        "if you suspect it may change: when the user corrects you later, call memory_correct and "
        "both versions stay readable. Returns {id, ref, sync}; keep the id for corrections."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "fact": {
                "type": "string",
                "description": "The fact itself, one complete sentence in plain language, e.g. 'The user deploys on Vercel.'",
            },
            "topic": {
                "type": "string",
                "description": (
                    "Short lowercase grouping key, no spaces, e.g. 'deployment' or 'user.timezone'. "
                    "Reuse the same key for related facts so corrections and conflicts group correctly. "
                    "Defaults to the first word of the fact when omitted."
                ),
            },
            "source": {
                "type": "string",
                "description": "Where the fact came from: 'user', 'tool', 'document', or 'inference'. Defaults to 'agent'.",
            },
        },
        "required": ["fact"],
    },
}

MEMORY_CORRECT_SCHEMA = {
    "name": "memory_correct",
    "description": (
        "Correct a fact that is now wrong, or refine it. Call this instead of calling "
        "memory_observe again with a changed value: the original observation stays in the ledger, "
        "and the correction is appended beside it, so what was believed before is never lost. "
        "After two corrections on the same fact a rule is derived automatically. Returns "
        "{target, previous, ref, rule}."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "fact_id": {
                "type": "string",
                "description": "The 'id' value returned by memory_observe or memory_recall_cited. It is an id, not a topic name.",
            },
            "correction": {
                "type": "string",
                "description": "The corrected fact, one complete sentence. Write it as the full true statement, not a diff.",
            },
            "reason": {
                "type": "string",
                "description": "Why the earlier fact was wrong, in a few words, e.g. 'user migrated to Fly.io'. Shown in the timeline.",
            },
            "rule": {
                "type": "string",
                "description": (
                    "Optional general rule learned from this correction, e.g. 'always confirm the "
                    "timezone before scheduling'. Omit it unless the user states a preference worth "
                    "applying elsewhere."
                ),
            },
        },
        "required": ["fact_id", "correction"],
    },
}

MEMORY_RECALL_CITED_SCHEMA = {
    "name": "memory_recall_cited",
    "description": (
        "Search memory before answering a question that depends on what you already know about "
        "this user or project. Returns each fact with its current text and a citation chain such "
        "as 'rule#04 <- fix#03 <- fix#02 <- obs#01'. Quote that chain when a remembered fact "
        "changed your answer, so the user can audit where it came from. An empty results list "
        "means nothing is stored on that topic: say so instead of guessing."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Plain words describing what you are looking for, e.g. 'deployment platform'. Not an id.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum facts to return, 1 to 20. Defaults to 5.",
            },
        },
        "required": ["query"],
    },
}

MEMORY_PROVENANCE_DIFF_SCHEMA = {
    "name": "memory_provenance_diff",
    "description": (
        "Show how a belief changed over time: what was observed at which timestamp, each "
        "correction with its reason, and any rule derived from them. Use this when the user asks "
        "'why did you think that', 'when did that change', or to explain a citation chain. Pass "
        "either fact_id or topic, not both."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "fact_id": {
                "type": "string",
                "description": "One fact id from memory_observe or memory_recall_cited.",
            },
            "topic": {
                "type": "string",
                "description": "A topic key to show every fact filed under it, e.g. 'deployment'.",
            },
        },
        "required": [],
    },
}

WALRUS_SYNC_SCHEMA = {
    "name": "walrus_sync",
    "description": (
        "Move memory between this machine and Walrus Mainnet. 'push' uploads lines still marked "
        "pending, which is what to run after a network outage; 'pull' merges lines that exist on "
        "Walrus but not locally, which is how a second device catches up. Requires "
        "WALRUS_DELEGATE_KEY and WALRUS_ACCOUNT_ID; without them it reports that the local ledger "
        "is still working and nothing is lost. Reading sealed blobs also needs a SEAL session, "
        "and pull reports a degraded result when one is missing."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["push", "pull"],
                "description": "Direction: 'push' sends local pending lines to Walrus, 'pull' brings remote lines down.",
            },
        },
        "required": ["action"],
    },
}

WALRUS_VERIFY_SCHEMA = {
    "name": "walrus_verify",
    "description": (
        "Check that memory has not been tampered with. Walks the local SHA-256 hash chain and "
        "reports the first broken line if one was edited, deleted or reordered. With Walrus "
        "configured it also checks which local lines are present on chain. Reports "
        "verified_on_walrus: false separately from walrus_reachable: false, because a relay that "
        "cannot decrypt sealed blobs is not the same as memory that is missing."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

MEMORY_IMPORT_SCHEMA = {
    "name": "memory_import",
    "description": (
        "Mirror the entries of the built-in Hermes MEMORY.md into this ledger, so existing memory "
        "gains provenance and citations without being retyped. The source file is opened read-only "
        "and never modified. Safe to rerun: entries already in the ledger are reported as "
        "skipped_existing, so nothing is duplicated. Use dry_run first to preview."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the memory file. Omit to use HERMES_MEMORY_MD or ~/.hermes/MEMORY.md.",
            },
            "topic_prefix": {
                "type": "string",
                "description": "Prefix added to every imported topic so mirrored facts group together. Defaults to 'memory_md'.",
            },
            "dry_run": {
                "type": "boolean",
                "description": "When true, report what would be imported and write nothing. Defaults to false.",
            },
        },
        "required": [],
    },
}

ALL_SCHEMAS = [
    MEMORY_OBSERVE_SCHEMA,
    MEMORY_CORRECT_SCHEMA,
    MEMORY_RECALL_CITED_SCHEMA,
    MEMORY_PROVENANCE_DIFF_SCHEMA,
    WALRUS_SYNC_SCHEMA,
    WALRUS_VERIFY_SCHEMA,
    MEMORY_IMPORT_SCHEMA,
]
