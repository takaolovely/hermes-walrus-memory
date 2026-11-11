"""The six tools. Each returns a JSON string, like every Hermes tool handler.

Handlers never raise on network trouble: a Walrus timeout becomes a
``sync=pending`` line and a note in the result, because a memory tool that
crashes when a relay is slow is a memory tool nobody leaves installed.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import ledger, memory as memory_mod, store, walrus

NAMESPACE = "hermes-walrus-memory"  # default; see walrus.namespace() for the resolved one


# -- shared plumbing -------------------------------------------------------


def _store(path: Optional[str] = None) -> store.LedgerStore:
    """Open the ledger. No tool handler may choose the path.

    ``path`` exists only so tests and the load_check script can point at a
    scratch file. Handlers call this with no argument, so the location always
    comes from config (``WALRUS_LEDGER_PATH``) and is confined by
    ``store.resolve_path`` to the plugin data directory.
    """
    return store.LedgerStore(path)


def _client() -> Optional[walrus.WalrusClient]:
    if not walrus.is_configured():
        return None
    return walrus.WalrusClient()


def _ns() -> str:
    """Resolved namespace, re-read every call so a demo can switch it live."""
    return walrus.namespace()


def _ok(**payload: Any) -> str:
    payload.setdefault("ok", True)
    return json.dumps(payload, ensure_ascii=False)


def _err(message: str, **payload: Any) -> str:
    payload.setdefault("ok", False)
    payload.setdefault("error", message)
    return json.dumps(payload, ensure_ascii=False)


def _guard(name: str, fn, args: Dict[str, Any]) -> str:
    """Last line of defence around a tool handler.

    A memory tool must never raise into the agent loop: an exception here would
    surface as a broken tool call in the middle of a conversation. Network and
    filesystem failures are already handled closer to the source, so anything
    reaching this wrapper is a bug, and the honest response is an error result
    that names it rather than a traceback.
    """
    try:
        return fn(**args)
    except (TypeError, KeyError, ValueError) as exc:
        return _err(f"{name} rejected its arguments: {exc}")
    except OSError as exc:
        return _err(f"{name} could not reach the ledger: {exc}")
    except Exception as exc:  # noqa: BLE001 - a tool boundary must not leak
        return _err(f"{name} failed unexpectedly: {type(exc).__name__}: {exc}")


def _write(store_obj: store.LedgerStore, kind: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    """Write-ahead: local first, then a best-effort Walrus append.

    The line is on disk and fsynced before the relay is contacted, so a slow or
    broken relay costs nothing: the line is marked ``sync=pending`` and
    ``walrus_sync`` catches up later.
    """
    seq, _ = store_obj.next_position()
    idempotency = f"{_ns()}:{kind}:{fields.get('id', '')}:{seq}"
    client = _client()
    state, extra = "local", ""
    if client is not None:
        # Commit the line as pending *before* the network call, so the pending
        # state is what a crash mid-request leaves behind, not a lost memory.
        provisional = store_obj.append_fields(kind, fields, sync="pending")
        state, extra = walrus.try_append(client, provisional, idempotency)
        if state == "synced":
            records = store_obj.read_records()
            for record in records:
                if record.seq == provisional.seq:
                    record.sync = "synced"
                    record.walrus = extra
                    break
            store_obj.rewrite(records)
    else:
        store_obj.append_fields(kind, fields, sync="local")
    return {"seq": seq, "sync": state, "note": extra}


# -- 1. observe ------------------------------------------------------------


def memory_observe(fact: str, topic: str = "", source: str = "") -> str:
    text = ledger.clean(fact, 400)
    if not text:
        return _err("fact is empty")
    topic = ledger.clean(topic, 80) or ledger.clean(text.split(" ")[0], 40)
    store_obj = _store()
    fact_id = f"obs-{memory_mod.stable_topic_key(topic)}-{uuid.uuid4().hex[:4]}"
    fields = {
        "id": fact_id,
        "topic": topic,
        "text": text,
        "source": ledger.clean(source, 60) or "agent",
        "at": ledger.utc_now(),
    }
    written = _write(store_obj, ledger.KIND_OBS, fields)
    return _ok(
        id=fact_id,
        topic=topic,
        text=text,
        ref=f"obs#{written['seq']:02d}",
        sync=written["sync"],
        ledger=str(store_obj.path),
        note=written["note"] or None,
    )


# -- 2. correct ------------------------------------------------------------


def _derived_rule_text(fact: memory_mod.Fact) -> str:
    """The rule a fact would derive right now. Comparing against this is what
    tells a stale rule apart from one already quoting the current belief."""
    return ledger.clean(
        f"{fact.active_text} (derived from {len(fact.fixes)} corrections)", 240
    )


def memory_correct(
    fact_id: str,
    correction: str,
    reason: str = "",
    rule: str = "",
) -> str:
    text = ledger.clean(correction, 400)
    if not text:
        return _err("correction is empty")
    store_obj = _store()
    mem = memory_mod.Memory(store_obj.read_records())
    fact = mem.get(fact_id)
    if fact is None:
        return _err(f"unknown fact id: {fact_id}")

    previous = fact.active_text
    fix_fields = {
        "id": f"fix-{len(fact.fixes) + 1:02d}-{fact_id}",
        "target": fact_id,
        "topic": fact.topic,
        "text": text,
        "previous": previous,
        "reason": ledger.clean(reason, 160),
        "at": ledger.utc_now(),
    }
    written = _write(store_obj, ledger.KIND_FIX, fix_fields)

    # Re-read: the fix line above is already on disk, so the projection now
    # reflects it. A rule never freezes the fact: if the user corrects again,
    # active_text still follows the newest fix and a fresh rule supersedes the
    # old one. An explicit ``rule`` is always honoured, a derived rule only
    # fires when there is none yet.
    mem_now = memory_mod.Memory(store_obj.read_records())
    fact_now = mem_now.get(fact_id)
    rule_ref = None
    rule_text = ledger.clean(rule, 240)
    if fact_now is not None and fact_now.fixes:
        supersedes = fact_now.rule
        # A derived rule exists only to state what is currently believed, so it
        # must be re-derived whenever the newest correction changed that. An
        # explicit rule always wins; a derived one is only skipped when the
        # existing rule already quotes the current text word for word.
        stale = supersedes is None or supersedes.fields.get("text", "") != _derived_rule_text(fact_now)
        if rule_text or (memory_mod.needs_rule(fact_now.fixes) and stale):
            rule_fields = {
                "id": f"rule-{fact_id}-{len(fact_now.fixes):02d}",
                "target": fact_id,
                "topic": fact_now.topic,
                "text": rule_text or _derived_rule_text(fact_now),
                "at": ledger.utc_now(),
            }
            if supersedes is not None:
                rule_fields["supersedes"] = supersedes.ref
            written_rule = _write(store_obj, ledger.KIND_RULE, rule_fields)
            rule_ref = f"rule#{written_rule['seq']:02d}"

    return _ok(
        target=fact_id,
        correction=text,
        previous=previous,
        ref=f"fix#{written['seq']:02d}",
        rule=rule_ref,
        sync=written["sync"],
        preserved_observation=True,
    )


# -- 3. recall with citations ---------------------------------------------


def memory_recall_cited(query: str, limit: int = 5) -> str:
    store_obj = _store()
    mem = memory_mod.Memory(store_obj.read_records())
    if not mem.facts():
        return _ok(query=query, results=[], note="ledger is empty")
    hits = mem.search(query, limit=max(1, min(int(limit or 5), 20)))
    return _ok(
        query=query,
        results=[hit.as_dict() for hit in hits],
        citation_format="rule#NN <- fix#NN <- obs#NN",
    )


# -- 4. provenance diff ----------------------------------------------------


def memory_provenance_diff(fact_id: str = "", topic: str = "") -> str:
    store_obj = _store()
    mem = memory_mod.Memory(store_obj.read_records())

    if fact_id:
        events = mem.timeline(fact_id)
        if not events:
            return _err(f"unknown fact id: {fact_id}")
        narrative = []
        for event in events:
            if event["event"] == "observed":
                narrative.append(f"Believed at {event['at']}: {event['text']}  [{event['ref']}]")
            elif event["event"] == "corrected":
                narrative.append(
                    f"Corrected at {event['at']} to: {event['text']}  [{event['ref']}]"
                    + (f" because {event['reason']}" if event.get("reason") else "")
                )
            else:
                narrative.append(f"Rule at {event['at']}: {event['text']}  [{event['ref']}]")
        return _ok(fact_id=fact_id, events=events, narrative=narrative)

    if topic:
        facts = mem.by_topic(topic)
        if not facts:
            return _err(f"no facts for topic: {topic}")
        return _ok(
            topic=topic,
            facts=[
                {"id": f.id, "citation": f.citation(), "events": mem.timeline(f.id)}
                for f in facts
            ],
        )
    return _err("pass fact_id or topic")


# -- 7. import from the built-in MEMORY.md --------------------------------


MEMORY_MD_ENV = "HERMES_MEMORY_MD"
DEFAULT_MEMORY_MD = "MEMORY.md"
MEMORIES_DIR = "memories"


def memories_root() -> Path:
    """The only directory ``memory_import`` may read from."""
    return (store.hermes_home() / MEMORIES_DIR).resolve()


def _memory_md_path() -> Path:
    """Resolve the memory file, confined to the profile's memories folder.

    The model cannot steer this. Earlier the handler took a ``path`` argument
    and mirrored whatever file it named to the relay, which is both an
    arbitrary-file-read and a data-exfiltration path. Now the location is
    config only, and ``HERMES_MEMORY_MD`` is itself rejected unless it resolves
    inside ``<hermes_home>/memories/``.
    """
    root = memories_root()
    env = os.environ.get(MEMORY_MD_ENV)
    target = Path(env).expanduser().resolve() if env else (root / DEFAULT_MEMORY_MD)
    try:
        target.relative_to(root)
    except ValueError:
        raise ValueError(
            f"memory file must stay inside {root}; refusing to read {target}"
        ) from None
    return target


_ENTRY_SPLIT = re.compile(r"\n\s*§\s*\n")


def parse_memory_md(text: str) -> List[Dict[str, str]]:
    """Split MEMORY.md into entries without interpreting their content.

    Hermes separates memories with a lone section sign on its own line. Long
    entries wrap across lines, so paragraphs are joined back into one line and
    the first sentence becomes a usable topic.
    """
    entries: List[Dict[str, str]] = []
    for block in _ENTRY_SPLIT.split(text):
        # Drop markdown headings line by line. Testing the whole block would
        # throw away a real entry that merely follows a heading without a
        # separator, which is how the first entry of MEMORY.md looks.
        kept = [line.strip() for line in block.splitlines() if line.strip() and not line.strip().startswith("#")]
        # Collapse wrapping: one entry is one ledger line.
        flat = " ".join(kept)
        if not flat:
            continue
        topic = flat.split(".")[0][:60]
        if len(topic) < 3:
            topic = " ".join(flat.split(" ")[:6])[:60]
        entries.append({"topic": topic, "text": flat})
    return entries


def memory_import(
    topic_prefix: str = "memory_md",
    dry_run: bool = False,
) -> str:
    """Mirror built-in MEMORY.md entries into the ledger as obs lines.

    The source is always ``<hermes_home>/memories/MEMORY.md``. There is no
    path argument on purpose: this handler mirrors what it reads to the relay
    when credentials are set, so a caller-chosen path would be an
    arbitrary-file-read with an exfiltration route attached.

    Read-only on the source file, idempotent on the ledger: rerunning it on an
    unchanged MEMORY.md imports nothing. Facts are compared on normalised text,
    so a re-formatted-but-identical entry is still a skip.
    """
    source = _memory_md_path()
    if not source.exists():
        return _err(f"memory file not found: {source}", imported=0, skipped_existing=0)

    try:
        with source.open("r", encoding="utf-8") as fh:
            raw = fh.read()
    except OSError as exc:
        return _err(f"cannot read {source}: {exc}", imported=0, skipped_existing=0)

    entries = parse_memory_md(raw)
    store_obj = _store()
    mem = memory_mod.Memory(store_obj.read_records())
    existing = {_entry_key(f.original_text) for f in mem.facts()}

    imported: List[Dict[str, str]] = []
    skipped = 0
    for entry in entries:
        key = _entry_key(entry["text"])
        if key in existing:
            skipped += 1
            continue
        existing.add(key)
        if dry_run:
            imported.append({"topic": entry["topic"], "text": entry["text"][:120], "ref": "dry-run"})
            continue
        # The topic is kept short and prefixed so imported facts stay grouped
        # and can be told apart from agent-observed ones.
        observe_payload = json.loads(
            memory_observe(
                fact=entry["text"],
                topic=f"{topic_prefix}:{entry['topic']}"[:80],
                source="memory_md",
            )
        )
        if not observe_payload.get("ok"):
            continue
        imported.append(
            {
                "topic": observe_payload["topic"],
                "text": entry["text"][:120],
                "ref": observe_payload["ref"],
            }
        )

    return _ok(
        source=str(source),
        dry_run=dry_run,
        imported=len(imported),
        skipped_existing=skipped,
        total_entries=len(entries),
        items=imported[:20],
    )


def _entry_key(text: str) -> str:
    """Compare on words only: whitespace and punctuation churn must not
    produce a duplicate observation."""
    return " ".join(memory_mod._normalise_words(text).split())[:400]


# -- 5. sync ---------------------------------------------------------------


def walrus_sync(action: str = "push") -> str:
    """push pending local lines to Walrus, or pull the Walrus snapshot into the
    local ledger. Pull never duplicates a record that is already local."""
    store_obj = _store()
    client = _client()
    if client is None:
        return _err(
            "Walrus is not configured. Set WALRUS_DELEGATE_KEY and WALRUS_ACCOUNT_ID "
            "to enable syncing. The local ledger keeps working without them.",
            mode="local",
        )

    if action == "push":
        records = store_obj.read_records()
        pending = [r for r in records if r.sync != "synced"]
        if not pending:
            return _ok(action="push", pushed=0, pending=0, note="nothing pending")
        pushed = 0
        failed = []
        for record in pending:
            key = f"{_ns()}:{record.kind}:{record.id}:{record.seq}"
            state, extra = walrus.try_append(client, record, key)
            if state == "synced":
                record.sync = "synced"
                record.walrus = extra
                pushed += 1
            else:
                failed.append({"ref": record.ref, "error": extra})
        store_obj.rewrite(records)
        return _ok(
            action="push",
            pushed=pushed,
            pending=len(failed),
            failures=failed[:10],
        )

    if action == "pull":
        try:
            remote_lines = client.snapshot()
        except walrus.WalrusDegraded as exc:
            # The index found records but their blobs are sealed. Pull is not
            # disabled and nothing is lost: it reports exactly that state so the
            # operator can supply a SEAL session and try again.
            found = exc.dropped
            return _ok(
                action="pull",
                degraded=True,
                encrypted_blobs_found=found,
                pulled=0,
                message=(
                    f"Found {found} encrypted memory record(s) on Walrus Mainnet, but plaintext "
                    "decryption requires an active Mysten SEAL session. Set WALRUS_SEAL_SESSION "
                    "or configure WALRUS_SEAL_BRIDGE and run pull again."
                ),
            )
        except walrus.WalrusError as exc:
            return _err(f"pull failed: {exc}")
        remote: List[ledger.Record] = []
        for line in remote_lines:
            record = ledger.decode(line)
            if record is not None:
                remote.append(record)
        local = store_obj.read_records()
        merged = memory_mod.dedupe(remote + local)
        merged.sort(key=lambda r: (r.fields.get("at", ""), r.seq))
        # Re-seal pulled records onto this device's chain so verification is
        # local. A pulled line came FROM Walrus, so it is marked synced rather
        # than pending: calling it pending would invite walrus_sync to upload a
        # duplicate under a re-sealed hash.
        resealed: List[ledger.Record] = []
        prev = "00000000"
        for index, record in enumerate(merged, start=1):
            rebuilt = ledger.build(
                record.kind,
                prev,
                index,
                dict(record.fields),
                sync="synced",
                walrus=record.walrus or record.hash,
            )
            resealed.append(rebuilt)
            prev = rebuilt.hash
        store_obj.rewrite(resealed)
        return _ok(
            action="pull",
            pulled=len(remote),
            merged=len(resealed),
            note="local ledger re-sealed so the hash chain verifies on this device",
        )

    return _err(f"unknown action: {action} (use push or pull)")


# -- 6. verify -------------------------------------------------------------


def walrus_verify() -> str:
    store_obj = _store()
    result = store_obj.verify()
    configured = walrus.is_configured()
    mode = "walrus" if configured else "local"
    payload = {
        "mode": mode,
        "namespace": walrus.namespace(),
        "integrity": "local tamper-evident hash chain" if not configured else "on-chain verifiable Walrus memory",
        "chain_ok": result.ok,
        "lines": result.lines,
        "broken_at": result.broken_at,
        "reason": result.reason or None,
        "head": result.records[-1].hash if result.records else "00000000",
        "ledger": str(store_obj.path),
        "synced": sum(1 for r in result.records if r.sync == "synced"),
        "pending": sum(1 for r in result.records if r.sync == "pending"),
    }
    if not configured:
        payload["note"] = "Set WALRUS_DELEGATE_KEY and WALRUS_ACCOUNT_ID to also compare against Walrus Mainnet."
        return _ok(**payload)

    client = _client()
    try:
        remote_lines = client.snapshot()
    except walrus.WalrusDegraded as exc:
        # The relay saw the lines but could not decrypt the blobs. Saying
        # "not on Walrus" here would be a lie: the write succeeded.
        payload["walrus_reachable"] = True
        payload["verified_on_walrus"] = False
        payload["walrus_error"] = str(exc)[:240]
        payload["note"] = (
            "Local chain verified and every synced line was accepted by the relay, "
            "but blobs could not be read back without a SEAL session. This is a "
            "read-path limitation, not a write failure."
        )
        return _ok(**payload)
    except walrus.WalrusError as exc:
        payload["walrus_reachable"] = False
        payload["verified_on_walrus"] = False
        payload["walrus_error"] = walrus.explain(exc)[:240]
        payload["note"] = "Local chain verified; Walrus comparison skipped because the relay did not answer."
        return _ok(**payload)

    # Compare on (kind, id), not on the encoded line. Pull re-seals lines onto
    # this device's chain, so the hash differs from the Walrus copy even when
    # the content is identical. Identity is what "is it on Walrus" means.
    local_ids = {(r.kind, r.id) for r in result.records}
    remote_ids = set()
    for line in remote_lines:
        parsed = ledger.decode(line)
        if parsed is not None:
            remote_ids.add((parsed.kind, parsed.id))
    missing_remote = len([key for key in local_ids if key not in remote_ids])
    payload.update(
        {
            "walrus_reachable": True,
            "verified_on_walrus": missing_remote == 0,
            "walrus_lines": len(remote_lines),
            "not_on_walrus": missing_remote,
            "match": missing_remote == 0,
        }
    )
    return _ok(**payload)
