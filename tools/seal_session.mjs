// Sidecar that mints an x-seal-session header for the Python plugin.
//
// SEAL sessions require an on-chain read of the SealConfig and threshold
// encryption of the session key, which is why this shells out to the official
// SDK instead of reimplementing it. Nothing here is a plugin dependency: if
// Node or the SDK is missing, the caller reports a degraded read path.
//
// usage: node seal_session.mjs <accountId> <namespace> <query>
// env:   WALRUS_DELEGATE_KEY   required
//        WALRUS_SEAL_SDK_ROOT  directory whose node_modules has the SDK
//                              (default: resolve upward from this file)
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import path from "node:path";

const [, , accountId, namespace, query = "obs"] = process.argv;
if (!accountId || !namespace) {
  console.log(JSON.stringify({ ok: false, error: "usage: seal_session.mjs <accountId> <namespace> [query]" }));
  process.exit(2);
}

const key = process.env.WALRUS_DELEGATE_KEY;
if (!key) {
  console.log(JSON.stringify({ ok: false, error: "WALRUS_DELEGATE_KEY missing" }));
  process.exit(2);
}

// Resolve the SDK from an explicit root when given, otherwise normally. ESM
// ignores NODE_PATH, so createRequire is the only way to honour a root.
const root = process.env.WALRUS_SEAL_SDK_ROOT;
let MemWal;
try {
  if (root) {
    const requireFromRoot = createRequire(path.join(path.resolve(root), "package.json"));
    const entry = requireFromRoot.resolve("@mysten-incubation/memwal");
    MemWal = (await import(pathToFileURL(entry).href)).MemWal;
  } else {
    MemWal = (await import("@mysten-incubation/memwal")).MemWal;
  }
} catch (e) {
  console.log(
    JSON.stringify({
      ok: false,
      error: `cannot load @mysten-incubation/memwal (set WALRUS_SEAL_SDK_ROOT): ${String(e?.message ?? e).slice(0, 200)}`,
    })
  );
  process.exit(3);
}

try {
  const client = MemWal.create({
    key,
    accountId,
    serverUrl: process.env.MEMWAL_SERVER_URL || "https://relayer.memory.walrus.xyz",
    namespace,
  });
  const session = await client.buildSealSession();
  console.log(JSON.stringify({ ok: true, session }));
} catch (e) {
  console.log(JSON.stringify({ ok: false, error: String(e?.message ?? e).slice(0, 300) }));
  process.exit(1);
}
