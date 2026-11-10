# hermes-walrus-memory

Append-only memory for Hermes Agent where corrections never overwrite what the
agent used to believe. Every fact carries a citation to the exact ledger line it
came from, and with Walrus credentials the same lines are stored on Walrus
Mainnet.

Built for the Hermes Agent Plugin Hackathon.

## The problem it solves

Most agent memory is a document that gets rewritten. When you correct the agent,
the old belief disappears, so it can never tell you what it thought before, why
it changed, or which correction taught it a rule. You get a snapshot with no
history.

This plugin stores memory as a ledger:

```
obs#01  The user ships on Vercel.
fix#02  The user ships on Fly.io and Vercel.       reason: user corrected the platform
fix#03  The user ships on Fly.io first, static on Vercel.
rule#04 Fly.io first, Vercel for static.           derived from 2 corrections
```

Ask it again later and it answers with `rule#04 <- fix#03 <- fix#02 <- obs#01`.
The original line is still there, unchanged and still readable.

## Two modes, one ledger

| | Zero config | With Walrus |
|---|---|---|
| Setup | none, install and go | `WALRUS_DELEGATE_KEY` + `WALRUS_ACCOUNT_ID` |
| Storage | `~/.hermes/walrus-memory.log` | local file plus Walrus Mainnet |
| Integrity | local tamper-evident SHA-256 hash chain | hash chain plus on-chain snapshot comparison |
| If the network is down | not a factor | line written locally, marked `sync=pending`, `walrus_sync` catches up later |
| Cross-device | no | `walrus_sync` push and pull |

Nothing in the zero-config mode needs a key, a node, or a network call. That is
deliberate: a memory tool that errors on install because an environment variable
is missing is a memory tool nobody keeps.

The integration is never on the critical path. A write is `fsync`ed to the local
ledger first, then the relay is contacted. If the relay is slow, down, or
returns garbage, the line stays on disk with `sync=pending` and the tool still
reports success. Nothing in the agent loop ever fails because Walrus did.

## The seven tools

| Tool | What it does |
|---|---|
| `memory_observe` | record a fact as an `obs` line |
| `memory_correct` | append a `fix` line, keep the original, derive a `rule` after two corrections |
| `memory_recall_cited` | search and return each fact with its citation chain |
| `memory_provenance_diff` | timeline: what was believed at which timestamp, and why it changed |
| `memory_import` | mirror built-in `MEMORY.md` entries in as observations, idempotent |
| `walrus_sync` | push pending lines to Walrus, or pull the snapshot and merge without duplicates |
| `walrus_verify` | walk the hash chain, and compare against Walrus when configured |

### A rule never freezes the fact

A derived `rule` states what is currently believed, so it is re-derived when a
later correction changes that belief. The old rule is kept for history and the
new one records `supersedes=rule#NN`. Recall always returns the newest text:

```
fix#02  Palembang.
rule#03 Palembang. (derived from 2 corrections)
fix#04  Palembang, WIB, and deletes nothing.
rule#05 Palembang, WIB, and deletes nothing. (derived from 3 corrections)  supersedes=rule#03
```

### Importing existing memory

`memory_import` reads `~/.hermes/MEMORY.md` in read-only mode, splits it on the
section separator, and writes each entry as an `obs` line tagged
`source=memory_md`. Running it twice on an unchanged file imports nothing and
reports `skipped_existing`. Comparison is on normalised words, so re-wrapping a
line does not create a duplicate.

## Install

```bash
hermes plugins install https://github.com/takaolovely/hermes-walrus-memory
hermes tools enable walrus_memory
```

Then ask the agent to remember something, correct it, and ask again.

That is the whole setup for the default mode. There is nothing to `pip install`:
the ledger, the hash chain and all seven tools run on the Python standard library
alone. `cryptography` is imported lazily and only when Walrus credentials are
present, so Mode 2 needs `pip install cryptography` while Mode 1 does not.

## How integrity works

Each line carries `prev=<8hex>` and `hash=<8hex>`, where the hash covers the
line's own fields plus the previous line's hash. Editing, deleting or reordering
any line breaks every hash after it, and `walrus_verify` reports the first broken
position:

```
{"chain_ok": true, "lines": 4, "head": "9f3c21ab", "pending": 0}
```

Transport metadata (`sync=`, `walrus=`) sits in the line but is excluded from the
hash payload, so syncing a line to Walrus never invalidates a chain that was
already verified.

## How Walrus sync works

The relayer does not accept a bearer token. Each request is signed with the
Ed25519 key in `WALRUS_DELEGATE_KEY` over

```
{timestamp}.{method}.{path}.{sha256(body)}.{nonce}.{account_id}
```

and sent back in `x-signature`, `x-public-key`, `x-timestamp`, `x-nonce`,
`x-account-id`. Writes go to `POST /api/remember`, which returns `202` with a job
id; the relayer uploads to Walrus asynchronously, so a job id means "accepted",
not "on chain yet". Reading goes through `POST /api/recall`, a similarity search
scoped to the namespace.

This mirrors `@mysten-incubation/memwal`, the SDK used in production by
RecallSpend, so the plugin speaks the real protocol instead of a guessed REST
shape.

## Privacy by default: memory is sealed

Every blob is encrypted with **Mysten SEAL** before it reaches Walrus. The relay
indexes the vector so it can find a match, but it cannot return the plaintext
without an `x-seal-session` credential. Ask for memory without one and the relay
answers honestly:

```json
{"results": [], "total": 0, "dropped_count": 4, "degraded": true}
```

Four records exist. None are readable. A third party with the relay and the
network can prove a memory is there without being able to read a word of it.
That is the default state, not a configuration option.

The plugin reports this instead of pretending the memory is absent:

```json
{
  "ok": true,
  "degraded": true,
  "encrypted_blobs_found": 4,
  "pulled": 0,
  "message": "Found 4 encrypted memory record(s) on Walrus Mainnet, but plaintext decryption requires an active Mysten SEAL session."
}
```

A SEAL session cannot be derived from the delegate key: `SessionKey.create`
performs an on-chain read of the SealConfig and threshold-encrypts the session
key, which is the whole point of the scheme. Reimplementing it in Python would
drag a Sui client into a plugin that should only need an HTTP stack, so the
plugin resolves a session in three tiers and never makes it a hard dependency:

| Tier | Setup | Result |
|---|---|---|
| 1 | `WALRUS_SEAL_SESSION=<session string>` | used as-is |
| 2 | `WALRUS_SEAL_BRIDGE=<command>` | the command prints `{"ok": true, "session": "..."}`; cached for the SEAL TTL |
| 3 | neither | read path degrades with the message above, write path untouched |

`tools/seal_session.mjs` is the tier 2 command for machines that have Node and
the SDK installed:

```bash
export WALRUS_SEAL_BRIDGE="node $PWD/tools/seal_session.mjs"
export WALRUS_SEAL_SDK_ROOT=/path/to/dir-with-node_modules   # optional
```

Measured on this project: 0.65 s for a fresh session, 0.0001 s cached.

## Namespace safety

`WALRUS_NAMESPACE` defaults to `hermes-walrus-memory`. The plugin refuses to
write into a namespace owned by another application:

```python
FOREIGN_NAMESPACES = ("recallspend-ledger", "recallspend-rules")
```

Setting one of those falls back to the plugin's own namespace. A memory plugin
that appends into somebody else's ledger corrupts their data, so this is a hard
guard rather than configuration advice.

## Files and paths

| Path | Purpose |
|---|---|
| `~/.hermes/walrus-memory.log` | the ledger, append-only |
| `WALRUS_LEDGER_PATH` | override the ledger path (used by the test suite) |
| `WALRUS_NAMESPACE` | relay namespace, default `hermes-walrus-memory` |
| `MEMWAL_SERVER_URL` | relay override, defaults to `https://relayer.memory.walrus.xyz` |
| `WALRUS_HTTP_TIMEOUT` | per-request timeout in seconds, default 6 |
| `WALRUS_SEAL_SESSION` | literal SEAL session for reading sealed blobs |
| `WALRUS_SEAL_BRIDGE` | command that mints a SEAL session, see above |
| `WALRUS_SEAL_SDK_ROOT` | directory whose `node_modules` holds `@mysten-incubation/memwal` |
| `HERMES_MEMORY_MD` | override the `MEMORY.md` path used by `memory_import` |

`~/.hermes/MEMORY.md` is never modified. This plugin runs alongside the built-in
memory, it does not replace it: `memory.provider` is left untouched, so
installing or removing the plugin never changes how Hermes already remembers.

## Tests

The plugin itself has no third-party dependency, so `load_check.py` runs on a
bare Python install:

```bash
python tools/load_check.py            # registers the plugin and drives every tool
```

The suite needs pytest. One install covers both, and the `cryptography` package
is only used by the Walrus network layer:

```bash
pip install -r requirements-dev.txt
python -m pytest plugin/tests -q      # 93 tests, all offline
```

Live relay tests are skipped unless credentials are present:

```bash
WALRUS_LIVE=1 WALRUS_DELEGATE_KEY=... WALRUS_ACCOUNT_ID=... \
  python -m pytest plugin/tests/test_live_relay.py -q
```

Every test writes to a temporary directory through `tmp_path` and
`WALRUS_LEDGER_PATH`. The suite asserts the live `MEMORY.md` is byte-identical
after each test, and that `memory_import` leaves its source file untouched.

## Known limitations

1. Pull re-seals the merged ledger onto this device's chain. Two devices that
   both wrote before syncing will produce different hashes for the same line,
   because the chain is per-device. The line text and ids still dedupe, and
   `walrus_verify` compares on `(kind, id)` for exactly this reason.
2. Recall is token overlap with inverse document frequency, not embeddings.
   It does not call a model, so it cannot match synonyms.
3. Reading sealed blobs needs a SEAL session. Without one the read path
   degrades and says so. The write path never depends on it.
4. Credentials are read from the environment. There is no OAuth flow yet.

## License

MIT
