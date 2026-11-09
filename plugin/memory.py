"""Memory semantics: append-only observations, corrections that never overwrite,
and rules derived from repeated corrections.

The projection is computed fresh from the lines every time, never cached, so the
answer to "what does Hermes believe right now" and "what did it believe before"
come from the same source of truth.
"""

from __future__ import annotations

import base64
import hashlib
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from . import ledger

TOPIC_FIELD = "topic"


def _norm(topic: str) -> str:
    return " ".join(str(topic or "").lower().split())


@dataclass
class Fact:
    """One observation plus everything that happened to it."""

    ob: ledger.Record
    fixes: List[ledger.Record] = field(default_factory=list)
    rule: Optional[ledger.Record] = None

    @property
    def id(self) -> str:
        return self.ob.id

    @property
    def topic(self) -> str:
        return self.ob.fields.get(TOPIC_FIELD, "")

    @property
    def active_text(self) -> str:
        """Latest correction wins for what is believed now, but nothing is lost."""
        if self.fixes:
            return self.fixes[-1].fields.get("text", self.ob.text)
        return self.ob.text

    @property
    def original_text(self) -> str:
        return self.ob.text

    @property
    def corrected(self) -> bool:
        return bool(self.fixes)

    def citation(self) -> str:
        """rule#04 <- fix#02 <- obs#01, most recent first, only what exists."""
        chain = []
        if self.rule is not None:
            chain.append(self.rule.ref)
        for fix in reversed(self.fixes):
            chain.append(fix.ref)
        chain.append(self.ob.ref)
        return " <- ".join(chain)

    def as_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "topic": self.topic,
            "text": self.active_text,
            "original_text": self.original_text,
            "corrected": self.corrected,
            "citation": self.citation(),
            "observed_at": self.ob.ts,
            "last_change_at": (self.fixes[-1].ts if self.fixes else self.ob.ts),
            "line_hash": self.ob.hash,
        }


class Memory:
    """Read model over a list of ledger records."""

    def __init__(self, records: Sequence[ledger.Record]):
        self.records: List[ledger.Record] = list(records)
        self._facts: Dict[str, Fact] = {}
        self._by_topic: Dict[str, List[str]] = {}
        self._build()

    def _build(self) -> None:
        for record in self.records:
            if record.kind == ledger.KIND_OBS:
                fact = Fact(ob=record)
                self._facts[record.id] = fact
                self._by_topic.setdefault(_norm(fact.topic), []).append(record.id)
        for record in self.records:
            if record.kind == ledger.KIND_FIX:
                target = record.fields.get("target", "")
                fact = self._facts.get(target)
                if fact is not None:
                    fact.fixes.append(record)
            elif record.kind == ledger.KIND_RULE:
                target = record.fields.get("target", "")
                fact = self._facts.get(target)
                if fact is not None:
                    fact.rule = record

    # -- lookups -----------------------------------------------------------
    def facts(self) -> List[Fact]:
        return list(self._facts.values())

    def get(self, fact_id: str) -> Optional[Fact]:
        return self._facts.get(fact_id)

    def by_topic(self, topic: str) -> List[Fact]:
        return [self._facts[i] for i in self._by_topic.get(_norm(topic), []) if i in self._facts]

    def search(self, query: str, limit: int = 8) -> List[Fact]:
        """Token overlap score, no embeddings, no network. Ties break by recency.

        A fact must match on a real word: "user" in both a deployment fact and a
        coffee fact says nothing, so a single-token overlap only counts when the
        token is rare enough to discriminate.
        """
        tokens = [t for t in _normalise_words(query).split() if len(t) > 1]
        if not tokens:
            return self.facts()[:limit]

        # Document frequency over the corpus, so stopword-ish tokens stop scoring.
        docs = [_normalise_words(f"{f.topic} {f.active_text} {f.original_text}") for f in self._facts.values()]
        total = max(1, len(docs))

        def idf(token: str) -> float:
            df = sum(1 for doc in docs if token in doc)
            if df == 0:
                return 0.0
            return math.log(1 + total / df)

        scored: List[Tuple[float, str, Fact]] = []
        for fact, haystack in zip(self._facts.values(), docs):
            hits = sum(idf(token) for token in tokens if token in haystack)
            if hits <= 0:
                continue
            score = hits / sum(idf(token) for token in tokens)
            if _norm(fact.topic) and _norm(fact.topic) in _normalise_words(query):
                score += 0.5
            if fact.corrected:
                score += 0.1
            scored.append((score, fact.ob.ts, fact))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [fact for _, _, fact in scored[:limit]]

    # -- hygiene -----------------------------------------------------------
    def conflicts(self) -> List[Dict[str, object]]:
        """Same topic, different active text, still live. These are the ones a
        human should resolve with a rule before the agent acts on either."""
        out: List[Dict[str, object]] = []
        for topic, ids in self._by_topic.items():
            if len(ids) < 2:
                continue
            variants: Dict[str, List[Fact]] = {}
            for fact_id in ids:
                fact = self._facts[fact_id]
                key = _norm(fact.active_text)
                variants.setdefault(key, []).append(fact)
            if len(variants) < 2:
                continue
            out.append(
                {
                    "topic": self._facts[ids[0]].topic,
                    "variants": [
                        {
                            "text": group[0].active_text,
                            "citations": [f.citation() for f in group],
                            "ids": [f.id for f in group],
                        }
                        for group in variants.values()
                    ],
                }
            )
        return out

    def timeline(self, fact_id: str) -> List[Dict[str, object]]:
        fact = self._facts.get(fact_id)
        if fact is None:
            return []
        events: List[Dict[str, object]] = [
            {
                "at": fact.ob.ts,
                "event": "observed",
                "ref": fact.ob.ref,
                "text": fact.ob.text,
                "hash": fact.ob.hash,
            }
        ]
        for fix in fact.fixes:
            events.append(
                {
                    "at": fix.ts,
                    "event": "corrected",
                    "ref": fix.ref,
                    "text": fix.fields.get("text", ""),
                    "previous": fix.fields.get("previous", ""),
                    "reason": fix.fields.get("reason", ""),
                    "hash": fix.hash,
                }
            )
        if fact.rule is not None:
            events.append(
                {
                    "at": fact.rule.ts,
                    "event": "rule",
                    "ref": fact.rule.ref,
                    "text": fact.rule.fields.get("text", ""),
                    "hash": fact.rule.hash,
                }
            )
        events.sort(key=lambda item: str(item["at"]))
        return events


# -- helpers ---------------------------------------------------------------

_PUNCT = ".,;:!?\"'()[]{}<>/\\|`~@#$%^&*+=_"


def _normalise_words(text: str) -> str:
    out = []
    for char in str(text or "").lower():
        out.append(" " if char in _PUNCT else char)
    return " ".join("".join(out).split())


def needs_rule(fixes: Sequence[ledger.Record], threshold: int = 2) -> bool:
    return len(fixes) >= threshold


def stable_topic_key(topic: str) -> str:
    """Short deterministic key so the same topic across devices shares an id."""
    digest = hashlib.sha256(_norm(topic).encode("utf-8")).digest()
    return base64.b32encode(digest).decode("ascii").lower()[:8]


def dedupe(records: Sequence[ledger.Record]) -> List[ledger.Record]:
    """Drop records whose (kind, id) already appeared, keeping the first."""
    seen = set()
    out: List[ledger.Record] = []
    for record in records:
        key = (record.kind, record.id)
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out
