// Oracle attribution: every report is credited to the model that actually
// ran it. EUROMOD-platform models (the JRC's EUROMOD, CeMPA's UKMOD,
// UNU-WIDER's SOUTHMOD) all report engine id "euromod"; the dashboard tells
// them apart by suite region, and this test holds that mapping to what each
// comparison config ran (its euromod_model_root). Run from dashboard/ with
// bun, after `bun install` (Bun.YAML parses the configs; the disposition
// tag check imports a component):
//   bun scripts/test-oracle-attribution.mjs
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";

import {
  SOUTHMOD_MODELS,
  UKMOD_RELEASE,
  euromodPlatformModel,
  otherOracle,
  runAnchor,
  suiteRegion,
  ukmodAcknowledgement,
} from "../src/utils/suites.js";
import { ORACLE_IDENTITY } from "../src/utils/oracleIdentity.js";
import { engineLabel } from "../src/utils/format.js";

assert.ok(globalThis.Bun?.YAML, "run with bun: the configs are parsed with Bun.YAML");

const PLATFORM_MODELS = ["euromod", "ukmod", "southmod"];

// Oracles a committed report reaches the roster with but that have no
// identity card yet. Shrink-only: the test fails if one gains an identity
// (delete it here) or a new oracle arrives without one (give it an entry in
// src/utils/oracleIdentity.js).
const KNOWN_UNIDENTIFIED = new Set(["treasury-incomeexplorer"]);

// ── Committed data ──────────────────────────────────────────────────────
const manifest = JSON.parse(readFileSync("public/data/manifest.json", "utf8"));
const reports = manifest.reports.map((file) => ({
  file,
  ...JSON.parse(readFileSync(`public/data/${file}`, "utf8")),
}));
const axiomPairs = reports.filter(
  (r) => r.engines?.left === "axiom" || r.engines?.right === "axiom",
);

/** The model a EUROMOD-platform model root names. */
function modelFamily(root) {
  if (root.includes("SOUTHMOD")) return "southmod";
  if (root.includes("UKMOD")) return "ukmod";
  if (root.includes("EUROMOD")) return "euromod";
  throw new Error(`unclassified EUROMOD-platform model root ${root}: name its model in modelFamily`);
}

const configs = [];
for (const name of readdirSync("../comparisons").sort()) {
  if (!name.endsWith(".yaml")) continue;
  const config = Bun.YAML.parse(readFileSync(`../comparisons/${name}`, "utf8"));
  const params = config?.runner?.parameters || {};
  if (!params.euromod_model_root) continue;
  configs.push({
    name,
    suite: params.suite,
    root: params.euromod_model_root,
    family: modelFamily(params.euromod_model_root),
  });
}
const configBySuite = new Map(configs.map((c) => [c.suite, c]));
assert.equal(configBySuite.size, configs.length, "one model-root config per suite");

// ── Differential: dashboard attribution vs the model each config ran ────
const checked = Object.fromEntries(PLATFORM_MODELS.map((m) => [m, 0]));
for (const config of configs) {
  assert.equal(
    euromodPlatformModel(config.suite),
    config.family,
    `${config.name} runs ${config.root}; the dashboard would credit ${euromodPlatformModel(config.suite)}`,
  );
  for (const report of axiomPairs.filter((r) => r.suite === config.suite)) {
    assert.equal(otherOracle(report), config.family, `${report.file} vs ${config.name}`);
    checked[config.family] += 1;
  }
}
for (const model of PLATFORM_MODELS) {
  assert.ok(checked[model] > 0, `no committed ${model} report was checked against its config`);
}

// Every report credited to UKMOD or SOUTHMOD is pinned by a config naming
// that model, so no attribution rests on the suite slug alone.
for (const report of axiomPairs) {
  const oracle = otherOracle(report);
  if (oracle !== "ukmod" && oracle !== "southmod") continue;
  const config = configBySuite.get(report.suite);
  assert.ok(config, `${report.file} is credited to ${oracle} but no config names its model root`);
  assert.equal(config.family, oracle, report.file);
}

// ── The UKMOD release the acknowledgement names is the one that ran ─────
for (const config of configs.filter((c) => c.family === "ukmod")) {
  assert.ok(
    config.root.endsWith(`/UKMOD_PUBLIC_${UKMOD_RELEASE}`),
    `${config.name} runs ${config.root}, not UKMOD_PUBLIC_${UKMOD_RELEASE}: update UKMOD_RELEASE`,
  );
}
for (const report of axiomPairs.filter((r) => otherOracle(r) === "ukmod")) {
  const recorded = report.provenance?.oracle?.euromod_release;
  if (recorded != null) assert.equal(recorded, UKMOD_RELEASE, report.file);
}
assert.ok(ukmodAcknowledgement().includes(`based on UKMOD version ${UKMOD_RELEASE}.`));
assert.ok(
  ukmodAcknowledgement().includes(
    "UKMOD is maintained, developed and managed by the Centre for Microsimulation and Policy Analysis at the Institute for Social and Economic Research (ISER), University of Essex.",
  ),
);

// ── Invariants of otherOracle, exhaustive over suites × engines × sides ─
// The domain is finite where it matters (which engine, which region), so
// every committed suite and engine is enumerated, plus synthetic slugs for
// each region prefix and a seeded sample of arbitrary slugs.
let seed = 0x5eed;
function rand() {
  seed ^= seed << 13;
  seed ^= seed >>> 17;
  seed ^= seed << 5;
  return (seed >>> 0) / 2 ** 32;
}
const ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789-";
const arbitrarySlugs = Array.from({ length: 500 }, () =>
  Array.from({ length: 1 + Math.floor(rand() * 24) }, () =>
    ALPHABET[Math.floor(rand() * ALPHABET.length)],
  ).join(""),
);
const prefixes = ["us", "uk", "be", "de", "dk", "ca", "nz", "xx", ...Object.keys(SOUTHMOD_MODELS)];
const suites = new Set([
  ...reports.map((r) => r.suite),
  ...configs.map((c) => c.suite),
  ...prefixes.flatMap((p) => [`${p}-dispy`, `${p}-worker-pit`, `${p}-x-ukmod`]),
  ...arbitrarySlugs,
  "",
]);
const engines = new Set([
  ...reports.flatMap((r) => [r.engines?.left, r.engines?.right]).filter(Boolean),
  "euromod",
  "a-future-engine",
]);
engines.delete("axiom");

let cases = 0;
for (const suite of suites) {
  const region = suiteRegion(suite);
  const expectedPlatform = SOUTHMOD_MODELS[region]
    ? "southmod"
    : region === "uk"
      ? "ukmod"
      : "euromod";
  for (const engine of engines) {
    const right = { suite, engines: { left: "axiom", right: engine } };
    const left = { suite, engines: { left: engine, right: "axiom" } };
    const oracle = otherOracle(right);
    // Side symmetry and determinism.
    assert.equal(otherOracle(left), oracle, `side symmetry: ${suite} ${engine}`);
    assert.equal(otherOracle(right), oracle, `determinism: ${suite} ${engine}`);
    if (engine === "euromod") {
      // Region alone decides the platform model; UK and SOUTHMOD countries
      // are never credited to the JRC's EUROMOD.
      assert.equal(oracle, expectedPlatform, `${suite} (region ${region})`);
      assert.ok(PLATFORM_MODELS.includes(oracle));
    } else {
      // Only the EUROMOD platform is refined; every other engine passes through.
      assert.equal(oracle, engine, `passthrough: ${suite} ${engine}`);
    }
    assert.equal(runAnchor(right), `run-${suite || "report"}-vs-${oracle}`);
    // Without Axiom on a side there is no oracle to credit.
    assert.equal(otherOracle({ suite, engines: { left: engine, right: "gettsim" } }), null);
    cases += 1;
  }
}
assert.equal(otherOracle({ suite: "uk-x", engines: undefined }), null);
assert.equal(otherOracle(null), null);

// ── Every oracle a committed report reaches has an identity card ────────
const reached = new Set(axiomPairs.map(otherOracle));
for (const id of reached) {
  if (KNOWN_UNIDENTIFIED.has(id)) {
    assert.ok(!ORACLE_IDENTITY[id], `${id} now has an identity: drop it from KNOWN_UNIDENTIFIED`);
    continue;
  }
  const identity = ORACLE_IDENTITY[id];
  assert.ok(identity, `oracle ${id} reaches the roster with no ORACLE_IDENTITY entry`);
  assert.ok(identity.org && identity.what && identity.url, `incomplete identity for ${id}`);
}
for (const id of KNOWN_UNIDENTIFIED) {
  assert.ok(reached.has(id), `${id} no longer reaches the roster: drop it from KNOWN_UNIDENTIFIED`);
}
for (const id of PLATFORM_MODELS) {
  assert.ok(reached.has(id), `no committed report is credited to ${id}`);
  assert.notEqual(engineLabel(id), id, `engineLabel has no name for ${id}`);
}
assert.equal(ORACLE_IDENTITY.ukmod.org, "University of Essex (CeMPA)");
assert.equal(ORACLE_IDENTITY.ukmod.acknowledgement, ukmodAcknowledgement());
assert.equal(
  ORACLE_IDENTITY.ukmod.licence.url,
  "https://creativecommons.org/licenses/by-nc-nd/4.0/",
);
assert.equal(ORACLE_IDENTITY.euromod.org, "European Commission JRC");

// Every committed run keeps a distinct anchor.
const anchors = new Map();
for (const report of reports) {
  const anchor = runAnchor(report);
  assert.ok(!anchors.has(anchor), `${report.file} and ${anchors.get(anchor)} share ${anchor}`);
  anchors.set(anchor, report.file);
}

// ── Disposition tags name the model, not the platform ───────────────────
const { dispositionTag } = await import("../src/components/DispositionNote.jsx");
const tagFor = (suite) =>
  dispositionTag("upstream_engine_gap", {
    suite,
    region: suiteRegion(suite),
    oracle: otherOracle({ suite, engines: { left: "euromod", right: "axiom" } }),
  });
assert.equal(tagFor("uk-universal-credit"), "UKMOD gap");
assert.equal(tagFor("gh-income-tax-rate-schedule"), "GHAMOD gap");
assert.equal(tagFor("be-worker-pit"), "EUROMOD gap");

const counts = PLATFORM_MODELS.map((m) => `${m} ${checked[m]}`).join(", ");
console.log(
  `ORACLE ATTRIBUTION: true (${configs.length} model-root configs; reports checked: ${counts}; ${cases} suite × engine cases)`,
);
