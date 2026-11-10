# hermes-walrus-memory

Append-only memory for Hermes Agent where corrections never overwrite what the agent used to believe. Every fact carries a citation to the exact ledger line it came from, and with Walrus credentials the same lines are stored on Walrus Mainnet.

Built for the Hermes Agent Plugin Hackathon.

## When you need this (and when you don't)

This plugin is not a drop-in replacement for everyday scratchpad memory. `~/.hermes/MEMORY.md` already handles casual notes well. Build or install this when you need:

- **Debugging agent belief drift.** Trace why Hermes believes a specific rule, which past correction taught it that rule, and what it believed beforehand: `rule#04 <- fix#03 <- fix#02 <- obs#01`.
- **Auditable decision and config trails.** Keep a tamper-evident SHA-256 hash-chained log of project rules, infrastructure changes, or operational constraints where silent overwrites are unacceptable.
- **Encrypted cross-machine portability.** Sync durable project facts across a VPS and a local machine through Walrus Mainnet without exposing plaintext to a third-party cloud database. Blobs are sealed by default with Mysten SEAL.

If you only use Hermes for conversation, you do not need this. That is a fair reason to skip it.

## Quick start (zero config, 0 Python dependencies)

```bash
hermes plugins install https://github.com/takaolovely/hermes-walrus-memory
hermes tools enable walrus_memory
```

That is the whole setup. No API key, no `pip install`, no network call. The ledger, the hash chain and all seven tools run on the Python standard library alone. `cryptography` is imported lazily and only when Walrus credentials are present, so Mode 1 needs nothing and Mode 2 needs one package.

**Observe.** Tell Hermes "Remember that we deploy our API on Vercel" and it records `obs#01`.

**Correct.** Tell Hermes "Correction: we moved the API to Fly.io, only static stays on Vercel" and it appends `fix#02` without deleting `obs#01`. After repeated corrections it derives a rule that cites the corrections behind it.

**Recall with citations.** Ask "Where do we deploy, and what did you think before?" and it returns the active rule plus the full lineage:

```
rule#04 <- fix#03 <- fix#02 <- obs#01
```

## Demo (67 seconds)

<!-- Replace the link below with the X post after upload. -->
Watch the walkthrough: **X post link goes here after upload**

The demo covers the full lifecycle: how a standard `MEMORY.md` overwrites erase history, how hermes-walrus-memory appends `obs` then `fix` then `rule` lines with exact citations, how `walrus_verify` catches a manual `sed -i` disk tamper at the exact broken line (`fix#02`), and how Walrus Mainnet with Mysten SEAL enforces privacy by default: `degraded: true` without a SEAL session versus `dropped: 0` with an active one.

A local copy lives at [`docs/demo.mp4`](docs/demo.mp4), and the Remotion source that renders it is in [`docs/demo/`](docs/demo/).

## What makes it verifiable

Each line carries `prev=<8hex>` and `hash=<8hex>`, where the hash covers the line's own fields plus the previous line's hash. Editing, deleting or reordering any line breaks every hash after it, so `walrus_verify` reports the first broken position instead of a vague failure:

```
{"chain_ok": true, "lines": 4, "head": "9f3c21ab", "pending": 0}
```

Transport metadata (`sync=`, `walrus=`) sits in the line but is excluded from the hash payload, so syncing a line to Walrus never invalidates a chain that was already verified.

## Privacy by default

With credentials set, every line is encrypted with Mysten SEAL before it leaves the machine. The relay indexes the memory so it can be found again, but it cannot return plaintext without an active seal session:

```
POST /api/recall  without x-seal-session
{"degraded": true, "encrypted_blobs_found": 21, "pulled": 0}

POST /api/recall  with x-seal-session
{"degraded": false, "pulled": 6, "dropped": 0}
```

A third party can prove the memory exists and is intact without reading a word of it. That is the default state, not an option you have to remember to switch on.

## The seven tools

```
memory_observe          append a durable fact as a new line
memory_correct          append a correction, keep the original
memory_recall_cited     recall a fact with its citation chain
memory_provenance_diff   timeline of what changed and why
memory_import           mirror an existing MEMORY.md, read-only
walrus_sync             push and pull against Walrus Mainnet
walrus_verify           check the chain, and check it against Walrus
```

Every tool is wrapped at the boundary, so a bad argument or an unreachable relay returns an informative message instead of a traceback in your agent loop.

## Tests

```bash
python3 tools/load_check.py            # no install needed, runs the seven tools
pip install -r requirements-dev.txt
python -m pytest plugin/tests -q       # 93 passed, 2 skipped
```

The two skipped tests need live Walrus credentials and are gated behind `WALRUS_LIVE=1`. Admission checks pass 15/15 with `hermes plugins validate`, including a capability probe that compares declared tools against what `register()` actually registers.

## Known limitations

- Reading sealed blobs back needs a Mysten SEAL session. Without one, `pull` and `verify` report a degraded result instead of failing; the local ledger and the write path are unaffected.
- Pull re-seals merged lines onto the puller's own chain, so two devices that wrote independently produce different hashes for the same line. Dedupe and verification compare on line identity, not hash.
- Recall is token overlap with inverse document frequency, not embeddings. It cannot match synonyms.
- This plugin does not register as `memory.provider`. It adds provenance alongside the built-in `MEMORY.md` rather than replacing it.
- The ledger grows. There is no automatic compaction yet, so old lines stay until you remove them.

## More detail

- [`docs/TECHNICAL.md`](docs/TECHNICAL.md) covers the ledger format, the Ed25519 relay protocol, the three-tier SEAL resolver, namespace safety and file paths.
- [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) is the verified demo script, with every command and output taken from a real run.

## License

MIT. See [`LICENSE`](LICENSE).
