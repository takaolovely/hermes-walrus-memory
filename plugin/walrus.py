"""Walrus Memory sync layer: graceful by construction.

Two modes share one interface:

* ``local``   - no credentials. Every method degrades to a no-op that reports
                ``configured: false`` plus a reason. Nothing raises.
* ``walrus``  - WALRUS_DELEGATE_KEY and WALRUS_ACCOUNT_ID are set and the
                memwal HTTP relay answers. Errors at any point are caught and
                reported as pending lines for ``walrus_sync`` to chase later.

The relay protocol mirrors the one proven in RecallSpend (src/lib/memory.ts):
append with an idempotency key, recall by namespace, and a 409 when the same
key is reused with different text.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

DEFAULT_RELAY = "https://relayer.memory.walrus.xyz"
ENV_KEY = "WALRUS_DELEGATE_KEY"
ENV_ACCOUNT = "WALRUS_ACCOUNT_ID"
ENV_RELAY = "MEMWAL_SERVER_URL"
ENV_TIMEOUT = "WALRUS_HTTP_TIMEOUT"
ENV_NAMESPACE = "WALRUS_NAMESPACE"
ENV_SEAL = "WALRUS_SEAL_SESSION"
ENV_SEAL_BRIDGE = "WALRUS_SEAL_BRIDGE"
DEFAULT_TIMEOUT = 6.0
DEFAULT_SEAL_TIMEOUT = 8.0
SEAL_TTL_SECONDS = 270.0  # SEAL issues 5 minute sessions; refresh before they lapse

DEFAULT_NAMESPACE = "hermes-walrus-memory"

# Namespaces owned by other applications. A memory plugin that appends into
# somebody else's ledger corrupts their data, so these are refused outright
# instead of trusted to configuration.
FOREIGN_NAMESPACES = ("recallspend-ledger", "recallspend-rules")


def namespace() -> str:
    """Namespace for this plugin. Never a foreign one.

    Overriding it is supported (e.g. ``hermes-demo-v1`` for a recording
    session), but a name owned by another app falls back to the default with a
    note rather than writing into their ledger.
    """
    requested = (os.environ.get(ENV_NAMESPACE) or "").strip() or DEFAULT_NAMESPACE
    if requested.lower() in FOREIGN_NAMESPACES:
        return DEFAULT_NAMESPACE
    return requested


@dataclass
class SyncStatus:
    configured: bool
    mode: str
    reason: str = ""


def credentials() -> tuple[Optional[str], Optional[str]]:
    return os.environ.get(ENV_KEY), os.environ.get(ENV_ACCOUNT)


def is_configured() -> bool:
    """Instant check. Never touches the network: this is what a tool's
    availability check is allowed to call."""
    key, account = credentials()
    return bool(key and account)


def status() -> SyncStatus:
    if is_configured():
        return SyncStatus(True, "walrus", f"credentials present, namespace {namespace()}")
    missing = []
    if not os.environ.get(ENV_KEY):
        missing.append(ENV_KEY)
    if not os.environ.get(ENV_ACCOUNT):
        missing.append(ENV_ACCOUNT)
    return SyncStatus(False, "local", "not configured: missing " + ", ".join(missing))


class WalrusClient:
    """Relay client for Walrus Memory.

    The relayer does not take a bearer token. Every request is signed:

        message = f"{ts}.{method}.{path}.{sha256(body)}.{nonce}.{account_id}"

    signed with the Ed25519 key in WALRUS_DELEGATE_KEY and sent back in the
    x-signature / x-public-key / x-timestamp / x-nonce / x-account-id headers.
    This mirrors @mysten-incubation/memwal so the plugin speaks the same
    protocol as the SDK instead of a guessed REST shape.

    Every network call is timeout-bounded and raises only ``WalrusError``,
    which callers convert into a pending line.
    """

    def __init__(self, namespace: str = "", timeout: Optional[float] = None):
        self.namespace = namespace or globals()["namespace"]()
        self.timeout = float(os.environ.get(ENV_TIMEOUT, DEFAULT_TIMEOUT)) if timeout is None else timeout
        self.server = os.environ.get(ENV_RELAY, DEFAULT_RELAY).rstrip("/")

    # -- signing -----------------------------------------------------------
    def _private_key(self):
        key, account = credentials()
        if not key or not account:
            raise WalrusError("credentials missing")
        raw = key[2:] if key[:2].lower() == "0x" else key
        try:
            seed = bytes.fromhex(raw)
        except ValueError as exc:
            raise WalrusError(f"WALRUS_DELEGATE_KEY is not hex: {exc}") from exc
        if len(seed) != 32:
            raise WalrusError(f"WALRUS_DELEGATE_KEY must be a 32 byte Ed25519 seed, got {len(seed)} bytes")
        return seed

    def _signed_headers(self, method: str, path: str, body_str: str) -> Dict[str, str]:
        # Imported here so a Hermes install without the `cryptography` package
        # still loads the plugin and works in zero-config mode. Only the Walrus
        # network layer needs Ed25519, and it says so plainly when it cannot.
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        except ImportError as exc:
            raise WalrusError(
                "the 'cryptography' package is required to sign Walrus requests "
                "(pip install cryptography). The local ledger works without it."
            ) from exc
        import time
        import uuid as _uuid

        _, account = credentials()
        seed = self._private_key()
        private = Ed25519PrivateKey.from_private_bytes(seed)
        public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        timestamp = str(int(time.time()))
        nonce = str(_uuid.uuid4())
        digest = hashlib.sha256(body_str.encode("utf-8")).hexdigest()
        message = f"{timestamp}.{method}.{path}.{digest}.{nonce}.{account}"
        signature = private.sign(message.encode("utf-8"))
        return {
            "x-public-key": public.hex(),
            "x-signature": signature.hex(),
            "x-timestamp": timestamp,
            "x-nonce": nonce,
            "x-account-id": account or "",
        }

    def _request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        body_str = "" if method == "GET" else json.dumps(payload or {})
        headers = {
            "content-type": "application/json",
            **self._signed_headers(method, path, body_str),
        }
        # Only recall needs to decrypt a blob, so the session is attached there.
        # Sending it on writes would hand the relayer a key it never uses.
        if method == "POST" and path == "/api/recall":
            _, account = credentials()
            session = seal_session(account or "", self.namespace, str((payload or {}).get("query", "obs")))
            if session:
                headers["x-seal-session"] = session
        req = urllib.request.Request(
            f"{self.server}{path}",
            data=None if method == "GET" else body_str.encode("utf-8"),
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300] if exc.fp else ""
            # The relayer explains auth failures in x-auth-error and a machine
            # code in the body. Without both, a 401 looks identical whether the
            # key is wrong, the clock is drifting, or the account was never
            # registered, so the operator cannot tell what to fix.
            if exc.headers:
                auth_hint = exc.headers.get("x-auth-error", "")
                code = exc.headers.get("x-server-code", "") or exc.headers.get("x-error-code", "")
                parts = [p for p in (auth_hint, code) if p]
                if parts:
                    detail = (f"{detail} [{' '.join(parts)}]").strip()
            raise WalrusError(f"http {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise WalrusError(f"network: {exc}") from exc
        if not raw.strip():
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise WalrusError(f"bad json: {raw[:120]}") from exc

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", path, payload)

    # -- operations --------------------------------------------------------
    def append(self, idempotency_key: str, text: str) -> str:
        """Submit one line. Returns the job id the relayer accepted.

        The relayer answers 202 with a job id and uploads to Walrus in the
        background, so a job id means "accepted and paid for", not "on chain
        yet". ``job_status`` follows it to a terminal state.
        """
        data = self._post(
            "/api/remember",
            {"text": text, "namespace": self.namespace, "idempotency_key": idempotency_key},
        )
        job = data.get("job_id") or data.get("jobId") or ""
        digest = data.get("blob_id") or data.get("digest") or ""
        if digest:
            return str(digest)
        if not job:
            raise WalrusError(f"relay accepted no job: {json.dumps(data)[:120]}")
        return str(job)

    def job_status(self, job_id: str) -> str:
        """Terminal state of a remember job: done, failed, or still running."""
        data = self._request("GET", f"/api/remember/{job_id}")
        return str(data.get("status", "unknown"))

    def snapshot(self, limit: int = 5000) -> List[str]:
        """Every line stored in the namespace, as far as recall can see.

        The relayer rejects an empty query, so a neutral bait word is used:
        recall is a similarity search, and every ledger line contains the kind
        prefix, which is enough to walk the namespace.

        Recall returns ``dropped_count`` with ``degraded: true`` when it matched
        lines but could not download or decrypt their blobs. That is a very
        different condition from "nothing is stored", so it raises
        ``WalrusDegraded`` instead of quietly returning an empty list.
        """
        out: List[str] = []
        seen = set()
        dropped = 0
        degraded = False
        for bait in ("obs", "fix", "rule"):
            data = self._post(
                "/api/recall",
                {"query": bait, "limit": limit, "namespace": self.namespace},
            )
            dropped += int(data.get("dropped_count") or 0)
            degraded = degraded or bool(data.get("degraded"))
            rows = data.get("results") or data.get("rows") or data.get("lines") or []
            for row in rows:
                text = ""
                if isinstance(row, str):
                    text = row
                elif isinstance(row, dict):
                    candidate = row.get("text") or row.get("line") or row.get("content")
                    if isinstance(candidate, str):
                        text = candidate
                if text and text not in seen:
                    seen.add(text)
                    out.append(text)
        if degraded or dropped:
            raise WalrusDegraded(
                f"relay matched {dropped} line(s) but could not read them back "
                f"(degraded={str(degraded).lower()}). Blobs need a SEAL session "
                f"to decrypt; the write path is unaffected.",
                dropped=dropped,
            )
        return out


class WalrusError(RuntimeError):
    pass


class WalrusDegraded(WalrusError):
    """Recall matched lines but could not read them back.

    Distinct from "nothing stored": the write succeeded and the index knows
    about the line, but the blob needs a SEAL session to decrypt.
    """

    def __init__(self, message: str, dropped: int = 0):
        super().__init__(message)
        self.dropped = int(dropped)


# -- SEAL session ----------------------------------------------------------
#
# Walrus Memory encrypts every blob with Mysten SEAL before uploading it. The
# relayer can find a matching line but cannot return its plaintext without an
# ``x-seal-session`` credential, so recall comes back degraded with a
# dropped_count until one is supplied.
#
# A session is not a signature over a fixed string: SessionKey.create performs
# an on-chain read of the SealConfig and its key servers, then threshold
# encrypts the session key. Reimplementing that in Python would mean dragging a
# Sui client into a plugin whose only dependency should be an HTTP stack, so the
# session comes from one of two places instead:
#
#   WALRUS_SEAL_SESSION  a literal session string, supplied by the operator
#   WALRUS_SEAL_BRIDGE   a command that prints {"ok": true, "session": "..."}
#
# tools/seal_session.mjs is that command for machines with Node and
# @mysten-incubation/memwal installed. Without either, sync stays degraded and
# says so rather than pretending the memory is not there.

_seal_cache: Dict[str, Any] = {"value": "", "expires": 0.0}


def seal_bridge_command() -> Optional[List[str]]:
    """The configured bridge command, split into argv."""
    raw = (os.environ.get(ENV_SEAL_BRIDGE) or "").strip()
    if not raw:
        return None
    import shlex

    return shlex.split(raw)


def seal_bridge_available() -> bool:
    """True when a session could plausibly be produced right now.

    Cheap on purpose: this never runs the bridge, it only checks for a literal
    session or a configured command, so an availability probe stays instant.
    """
    if (os.environ.get(ENV_SEAL) or "").strip():
        return True
    return seal_bridge_command() is not None


def seal_session(account_id: str, namespace: str, query: str = "obs") -> str:
    """Best current SEAL session string, or "" when none can be obtained.

    Cached for the life of a SEAL session. Never raises: a bridge that is
    missing, slow, or broken degrades the read path instead of failing a tool.
    """
    literal = (os.environ.get(ENV_SEAL) or "").strip()
    if literal:
        return literal

    now = time.time()
    if _seal_cache["value"] and now < float(_seal_cache["expires"]):
        return str(_seal_cache["value"])

    argv = seal_bridge_command()
    if not argv:
        return ""

    try:
        proc = subprocess.run(
            argv + [account_id, namespace, query],
            capture_output=True,
            text=True,
            # Bounded like every other call: a bridge that hangs must cost a
            # degraded read, never a stuck tool call.
            timeout=float(os.environ.get("WALRUS_SEAL_BRIDGE_TIMEOUT", str(DEFAULT_SEAL_TIMEOUT))),
            env={**os.environ},
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return ""
    except Exception:  # noqa: BLE001 - a bridge must never break the tool
        return ""

    for line in reversed((proc.stdout or "").strip().splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if data.get("ok") and data.get("session"):
            _seal_cache["value"] = str(data["session"])
            _seal_cache["expires"] = time.time() + SEAL_TTL_SECONDS
            return str(data["session"])
    return ""


def seal_session_reset() -> None:
    """Drop the cached session. Used by tests and after an auth change."""
    _seal_cache["value"] = ""
    _seal_cache["expires"] = 0.0


# What each auth failure actually means for the operator. A bare 401 sends
# people to check the wrong thing, so the message names the fix.
_AUTH_HELP = {
    401: (
        "credentials rejected. The key is not registered as a delegate on this "
        "account. A wallet address is not a MemWal account id."
    ),
    403: "this delegate key is not allowed to write to that namespace.",
    404: "endpoint not found. Check MEMWAL_SERVER_URL.",
    429: "relay is rate limiting. Lines stay pending and walrus_sync retries.",
}


def explain(exc: "WalrusError") -> str:
    """Turn a relay error into something actionable."""
    text = str(exc)
    for code, help_text in _AUTH_HELP.items():
        if f"http {code}" in text:
            return f"{text} - {help_text}"
    return text


def try_append(client: Optional[WalrusClient], record, idempotency_key: str) -> tuple[str, str]:
    """Best-effort append of one record.

    Returns ``(sync_state, walrus_digest)``. Never raises: a failure becomes
    ``("pending", "")`` so the caller keeps the local line and moves on.
    """
    if client is None:
        return "local", ""
    try:
        digest = client.append(idempotency_key, record.encode())
        return "synced", digest
    except WalrusError as exc:
        return "pending", explain(exc)[:240]
