// Mirror ops launch-readiness/certified-nodes.yaml — the single source of
// truth for what is certified — into the API's ledger artifact
// (axiom-certified-ledger/1). The app and demos mirror the ledger; the
// ledger mirrors the ops file; there is no other curation path.
//
// Usage:
//   node scripts/mirror-certified-nodes.mjs \
//     [--source ~/ops/launch-readiness/certified-nodes.yaml] \
//     [--out data/certified-nodes.json]
//
// The ops schema (axiom.certified_nodes.v1) lists entries with `node`,
// `mode` (attested|computed — the same claim vocabulary the ledger uses),
// per-entry evidence pins, and the five checked criteria. Each mirrored
// ledger entry's evidence_sha256 is the sha of the canonical ops entry, so
// tampering with either side is visible.

import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { load } from "js-yaml";

function arg(name, fallback) {
  const index = process.argv.indexOf(`--${name}`);
  return index >= 0 && process.argv[index + 1]
    ? process.argv[index + 1]
    : fallback;
}

const sourcePath = arg(
  "source",
  `${process.env.HOME}/ops/launch-readiness/certified-nodes.yaml`
);
const outPath = arg("out", "data/certified-nodes.json");

const doc = load(readFileSync(sourcePath, "utf8"));
if (!doc || doc.schema !== "axiom.certified_nodes.v1") {
  console.error(
    `Refusing: ${sourcePath} is not schema axiom.certified_nodes.v1`
  );
  process.exit(1);
}
const nodes = Array.isArray(doc.nodes) ? doc.nodes : [];

const entries = nodes.map((node, index) => {
  if (typeof node?.node !== "string" || !node.node.includes("#")) {
    console.error(`Refusing: nodes[${index}].node is not a node legal id`);
    process.exit(1);
  }
  if (node.mode !== "attested" && node.mode !== "computed") {
    console.error(`Refusing: nodes[${index}].mode must be attested|computed`);
    process.exit(1);
  }
  const canonical = JSON.stringify(node, Object.keys(node).sort());
  return {
    legal_id: node.node,
    certificate_id: `ops-${node.mode}-${createHash("sha256").update(canonical).digest("hex").slice(0, 12)}`,
    claim: node.mode,
    evidence_sha256: createHash("sha256").update(canonical).digest("hex")
  };
});

// Vintage comes from the entries' pins when present; the empty file (the
// honest launch state) mirrors to the empty bootstrap ledger.
const firstPinned = nodes.find((node) => node?.pinned)?.pinned ?? {};
const ledger = {
  format: "axiom-certified-ledger/1",
  ledger_id: `ops-certified-nodes@${doc.as_of ?? "unknown"}`,
  issued_at: new Date().toISOString(),
  fixture: false,
  vintage: {
    encoding_release: String(firstPinned.rulespec_us ?? "unreleased"),
    engine_release: String(firstPinned.engine ?? "unreleased"),
    corpus_release: String(firstPinned.corpus ?? "unreleased")
  },
  entries: entries.sort((a, b) => a.legal_id.localeCompare(b.legal_id))
};

writeFileSync(outPath, `${JSON.stringify(ledger, null, 2)}\n`);
console.log(
  `Mirrored ${entries.length} certified node${entries.length === 1 ? "" : "s"} from ${sourcePath} → ${outPath}`
);
