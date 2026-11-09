# Demo script: hermes-walrus-memory

Target 78 seconds. Hard ceiling 90. Screen recording of a real terminal plus VO.
Every number below comes from a run of this repo, not from a mockup.

Read the VO slightly faster than feels natural. Silence is what makes these feel
slow, not words.

---

## Scene 1 — The problem (0:00 to 0:09, 9s)

**On screen:** a plain `MEMORY.md` being edited. One line is selected, deleted,
one word typed over it.

```
The user ships on Vercel.   <- selected and deleted
The user ships on Fly.io.   <- typed in its place
```

**VO:** "Most agent memory is a document. When you correct the agent, the old
belief is deleted. Hermes cannot tell you what it thought before, or why it
changed."

---

## Scene 2 — Ledger instead of document (0:09 to 0:22, 13s)

**On screen:** terminal. The lines appear as they are written.

```
$ hermes
> Remember that I ship on Vercel.

memory_observe  -> obs#01  "The user ships on Vercel."

> Actually it moved to Fly.io, Vercel is static only.

memory_correct  -> fix#02  "The user ships on Fly.io, Vercel for static."
                   previous kept: "The user ships on Vercel."
```

**VO:** "Walrus Memory stores memory as an append-only ledger. A correction is a
new line, not an overwrite. The original stays readable forever."

---

## Scene 3 — Provenance and citation (0:22 to 0:38, 16s)

**On screen:** ask a question, recall returns the citation chain.

```
> Where do I deploy?

memory_recall_cited  -> "Fly.io, Vercel for static"
                         rule#04 <- fix#03 <- fix#02 <- obs#01

> Why did you think Vercel before?

memory_provenance_diff -> Believed at 2026-11-09 15:34: Observed, Vercel.
                          Corrected: moved to Fly.io, because user migrated.
```

**VO:** "Ask again and every answer carries the exact line it came from. Ask why
it changed and you get a timeline. After two corrections, a rule is derived and
cites the corrections that produced it."

---

## Scene 4 — Tamper-evident (0:38 to 0:50, 12s)

**On screen:** edit one character in the ledger with sed, then verify.

```
$ sed -i 's/Fly.io/Railway/' ~/.hermes/walrus-memory.log
$ hermes
> Verify my memory.

walrus_verify -> chain_ok: false
                 broken_at: 2
                 hash mismatch at fix#02
```

Then restore the file, verify again: `chain_ok: true, lines: 6`.

**VO:** "Every line carries a SHA-256 hash chained to the one before it. Change a
single character and verify names the exact line that broke. No key, no server,
no setup."

---

## Scene 5 — Walrus Mainnet (0:50 to 1:08, 18s)

**On screen:** export credentials, write, then verify against chain.

```
$ export WALRUS_DELEGATE_KEY=... WALRUS_ACCOUNT_ID=0x21c2...
> Remember that I moved to Palembang.

memory_observe -> obs#07  sync=synced  job 77fa9773

> Verify against Walrus.

walrus_verify -> chain_ok: true
                 walrus_reachable: true
                 verified_on_walrus: true
                 walrus_lines: 7
```

Cut to the relay response showing the encryption:

```
POST /api/recall  without x-seal-session
-> {"results": [], "dropped_count": 7, "degraded": true}
```

**VO:** "Point it at Walrus Mainnet and the same lines go on chain, encrypted with
Mysten SEAL before upload. Without a session key the relay can prove the memory
exists but cannot read a word of it. Privacy is the default, not a setting."

---

## Scene 6 — Close (1:08 to 1:18, 10s)

**On screen:** the repo URL, the seven tool names, and the test result.

```
github.com/takaolovely/hermes-walrus-memory

7 tools   memory_observe  memory_correct  memory_recall_cited
          memory_provenance_diff  memory_import  walrus_sync  walrus_verify

93 tests passing      works with zero configuration
```

**VO:** "Seven tools, ninety-three tests, no keys required. Install it, and your
agent stops forgetting what it used to believe."

---

## Timing budget

```
scene 1   0:00 - 0:09    9s   problem
scene 2   0:09 - 0:22   13s   ledger
scene 3   0:22 - 0:38   16s   citation and provenance
scene 4   0:38 - 0:50   12s   tamper evidence
scene 5   0:50 - 1:08   18s   Walrus Mainnet and SEAL
scene 6   1:08 - 1:18   10s   close
                        ---
                        78s   with 12s of headroom under the 90s ceiling
```

## Recording notes

- Terminal font 16pt minimum, dark theme, no custom prompt, no username in the
  prompt line. Run everything from `/tmp/demo` so a home directory never shows.
- Do not show the real delegate key. Export it from a file and say "credentials
  loaded", or type it masked.
- Cut, do not speed up. A sped-up terminal reads as dishonest.
- The `sed` in scene 4 is on a copy of the ledger, restored right after. Say so
  in the caption so nobody thinks data loss is part of the demo.
- Capture at 60 fps, export 1920x1080. Keep the voice track at about -16 LUFS.

## What not to show

- `pysui`, `sui-sdk`, or any Python Sui client. There is none, and implying
  otherwise misrepresents the dependency footprint.
- The RecallSpend namespace or account. The demo uses its own account.
- Any claim that recall matches synonyms. It is token overlap, stated in the
  README, and the demo should not contradict it.
