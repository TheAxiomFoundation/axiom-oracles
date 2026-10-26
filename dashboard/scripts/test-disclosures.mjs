// Disclosure invariants: identity copy preserves the PR's relationship and
// scope disclosures, and each relationship claim has dated, short evidence.
// Run with `bun test ./scripts/test-disclosures.mjs` from dashboard/.
// DISCLOSURE_TEST_REF checks a committed snapshot without changing the tree.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync, readdirSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { test } from "bun:test";

const ref = process.env.DISCLOSURE_TEST_REF;
const root = new URL("../../", import.meta.url);
function source(path) {
  return ref
    ? execFileSync("git", ["show", `${ref}:${path}`], { cwd: root, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] })
    : readFileSync(new URL(path, root), "utf8");
}
let identities;
if (ref) {
  // Before main extracted the module, this data lived in OraclesV2.jsx.
  let copy;
  try {
    copy = source("dashboard/src/utils/oracleIdentity.js");
  } catch {
    copy = source("dashboard/src/components/OraclesV2.jsx");
  }
  const block = copy.match(/(?:export )?const ORACLE_IDENTITY = (\{[\s\S]*?\n\});/);
  assert.ok(block, `ORACLE_IDENTITY missing at ${ref}`);
  // The newer module has acknowledgements and a release interpolation.
  // These do not affect the three disclosure strings checked here.
  identities = runInNewContext(`(${block[1]})`, {
    UKMOD_RELEASE: "unused in disclosure checks",
    ukmodAcknowledgement: () => "",
    southmodAcknowledgement: () => "",
  });
} else {
  ({ ORACLE_IDENTITY: identities } = await import("../src/utils/oracleIdentity.js"));
}

test("PolicyEngine and TAXSIM cards retain the approved relationship disclosures", () => {
  assert.equal(
    identities.policyengine.what,
    "Open-source tax–benefit microsimulation of US and UK law. Max Ghenis is CEO of both Axiom and PolicyEngine, which he co-founded, and PSL Foundation fiscally sponsors both organizations.",
  );
  assert.equal(
    identities.taxsim.what,
    "TAXSIM-35 — the National Bureau of Economic Research's federal and state income-tax calculator, the reference model of empirical tax research. PolicyEngine is building TAXSIM's successor with its author's cooperation, and Axiom's runs use the TAXSIM executable that PolicyEngine packages (policyengine-taxsim).",
  );
});

test("SNAP-QC card discloses its eligibility limitation", () => {
  assert.ok(identities["snap-qc"].what.endsWith(
    "The file keeps only eligible households and the replay takes income and several deductions as given, so it checks benefit arithmetic and leaves eligibility untested.",
  ));
});

test("dashboard source contains neither banned independence claim", () => {
  const paths = ref
    ? execFileSync("git", ["ls-tree", "-r", "--name-only", ref, "--", "dashboard/src"], { cwd: root, encoding: "utf8" }).trim().split("\n")
    : readdirSync(new URL("dashboard/src/", root), { recursive: true }).map((path) => `dashboard/src/${path}`);
  for (const path of paths.filter((path) => /\.(?:jsx?|json|css)$/.test(path))) {
    assert.doesNotMatch(source(path), /independent engines|never grades its own work/i, path);
  }
});

function evidence() {
  return JSON.parse(source("dashboard/src/data/disclosure-evidence.json"));
}
const publicSources = {
  "policyengine-leadership": {
    url: "https://axiom.org/team",
    quote: "co-founder and CEO of PolicyEngine",
  },
  "policyengine-fiscal-sponsorship": {
    url: "https://policyengine.org/us/donate",
    quote: "our fiscal sponsor, the PSL Foundation",
  },
  "taxsim-successor": {
    url: "https://taxsim.nber.org/",
    quote: "A successor to Taxsim is being built by PolicyEngine with my cooperation",
  },
};

test("each disclosed relationship has a dated source URL and a quote of at most 20 words", () => {
  const records = evidence().disclosures;
  assert.deepEqual(records.map((entry) => entry.claim_id).sort(), [
    "axiom-fiscal-sponsorship", "axiom-leadership", "policyengine-fiscal-sponsorship",
    "policyengine-leadership", "taxsim-executable", "taxsim-successor",
  ]);
  for (const entry of records) {
    assert.ok(entry.claim.length > 0, entry.claim_id);
    assert.match(entry.source_url, /^https:\/\//, entry.claim_id);
    assert.equal(entry.retrieved_on, "2026-10-06", entry.claim_id);
    assert.ok(entry.retrieved_by.length > 0 && entry.retrieval_note.length > 0, entry.claim_id);
    assert.ok(entry.quote.trim().split(/\s+/).length <= 20, `${entry.claim_id}: quote exceeds 20 words`);
  }
});

test("public quotes preserve reviewer provenance and precise claim coverage", () => {
  const records = new Map(evidence().disclosures.map((entry) => [entry.claim_id, entry]));
  for (const [id, expected] of Object.entries(publicSources)) {
    const entry = records.get(id);
    assert.equal(entry.source_url, expected.url, id);
    assert.equal(entry.quote, expected.quote, id);
    assert.equal(entry.retrieval_note, "retrieved 2026-10-06 by the Axiom eng hub's reviewer", id);
  }
  for (const id of ["axiom-leadership", "axiom-fiscal-sponsorship"]) {
    const entry = records.get(id);
    assert.equal(entry.source_kind, "approved PR declaration", id);
    assert.ok(entry.limitation.includes("independent"), `${id}: distinguish the PR declaration from independent evidence`);
    assert.ok(!entry.retrieval_note.includes("reviewer"), `${id}: do not attribute a local excerpt to the reviewer`);
  }
});

test("executable packaging evidence quotes the committed TAXSIM pin documentation", () => {
  const entry = evidence().disclosures.find((record) => record.claim_id === "taxsim-executable");
  assert.equal(entry.source_path, "axiom_oracles/adapters/taxsim/pins.py");
  assert.ok(source(entry.source_path).includes(entry.quote), "packaging quote differs from local committed source");
  assert.ok(entry.source_url.includes("/axiom_oracles/adapters/taxsim/pins.py"));
});
