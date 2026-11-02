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
  displayEngines,
  euromodPlatformModel,
  otherOracle,
  runAnchor,
  southmodAcknowledgement,
  southmodModel,
  suiteRegion,
  ukmodAcknowledgement,
} from "../src/utils/suites.js";
import { ORACLE_IDENTITY, attributedOracles } from "../src/utils/oracleIdentity.js";
import { crossCheckCount, groupByOracle, verificationReports } from "../src/utils/roster.js";
import { engineLabel, mismatchKindLabel } from "../src/utils/format.js";

assert.ok(globalThis.Bun?.YAML, "run with bun: the configs are parsed with Bun.YAML");

const PLATFORM_MODELS = ["euromod", "ukmod", "southmod"];
const JRC_REGIONS = new Set(["be", "dk", "de"]);

// Oracles a committed report reaches the roster with but that have no
// identity card yet. Shrink-only: the test fails if one gains an identity
// (delete it here) or a new oracle arrives without one (give it an entry in
// src/utils/oracleIdentity.js).
const KNOWN_UNIDENTIFIED = new Set(["treasury-incomeexplorer"]);

// A model root given as a bare environment variable names no model, so each
// one is mapped here, citing where its release is pinned.
const ENV_MODEL_ROOTS = {
  // The JRC's EUROMOD J2.0+: scripts/de_unified_comparison.py ORACLE_PINS.
  $EUROMOD_MODEL_ROOT_DE: "euromod",
};

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
  if (/^\$[A-Z0-9_]+$/.test(root)) {
    assert.ok(root in ENV_MODEL_ROOTS, `model root ${root} is a bare variable: map it in ENV_MODEL_ROOTS`);
    return ENV_MODEL_ROOTS[root];
  }
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
    params,
    suite: params.suite,
    root: params.euromod_model_root,
    family: modelFamily(params.euromod_model_root),
  });
}
const configBySuite = new Map(configs.map((c) => [c.suite, c]));
assert.equal(configBySuite.size, configs.length, "one model-root config per suite");
assert.match(
  readFileSync("../scripts/de_unified_comparison.py", "utf8"),
  /"euromod":\s*\{\s*"release":\s*"J2\.0\+"/,
  "DE's EUROMOD pin moved off J2.0+: recheck ENV_MODEL_ROOTS",
);

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
// that model, so no attribution rests on the suite slug alone. (EUROMOD
// reports from the BE suite runner have no model-root config; they are
// credited to EUROMOD by region.)
for (const report of axiomPairs) {
  const oracle = otherOracle(report);
  if (oracle !== "ukmod" && oracle !== "southmod") continue;
  const config = configBySuite.get(report.suite);
  assert.ok(config, `${report.file} is credited to ${oracle} but no config names its model root`);
  assert.equal(config.family, oracle, report.file);
}
for (const report of axiomPairs.filter((r) => otherOracle(r) === "euromod")) {
  assert.ok(JRC_REGIONS.has(suiteRegion(report.suite)), `${report.file} credited to EUROMOD`);
}

// ── The UKMOD release the acknowledgement names is the one that ran ─────
const ukmodConfigs = configs.filter((c) => c.family === "ukmod");
const ukmodReports = axiomPairs.filter((r) => otherOracle(r) === "ukmod");
for (const config of ukmodConfigs) {
  assert.ok(
    config.root.endsWith(`/UKMOD_PUBLIC_${UKMOD_RELEASE}`),
    `${config.name} runs ${config.root}, not UKMOD_PUBLIC_${UKMOD_RELEASE}: update UKMOD_RELEASE`,
  );
}
for (const report of ukmodReports) {
  const recorded = report.provenance?.oracle?.euromod_release;
  if (recorded != null) assert.equal(recorded, UKMOD_RELEASE, report.file);
}

// ── The acknowledgement carries every part UKMOD's terms ask for ────────
const ack = ukmodAcknowledgement();
for (const required of [
  `The results presented here are based on UKMOD version ${UKMOD_RELEASE}.`,
  "UKMOD is maintained, developed and managed by the Centre for Microsimulation and Policy Analysis (CeMPA) at the University of Essex.",
  "The process of extending and updating UKMOD was financially supported by the Nuffield Foundation (2018-2021) and the abrdn Financial Fairness Trust (2023-2024).",
  "The results and their interpretation are the Axiom Foundation's sole responsibility.",
  "Richiardi M, Collado D, Popova D (2021). UKMOD – A new tax-benefit model for the four nations of the UK. International Journal of Microsimulation, 14(1): 92-101. DOI: 10.34196/IJM.00231.",
  "Changes: ",
]) {
  assert.ok(ack.includes(required), `UKMOD acknowledgement lost: ${required}`);
}

// Every override a UKMOD run applies is indicated, as the licence asks:
// take-up rates set to 1 under one phrase, anything else by name.
const constants = [];
const switches = [];
for (const config of ukmodConfigs) {
  for (const pair of String(config.params.euromod_constant_overrides || "").split(",")) {
    if (!pair.trim()) continue;
    const [name, value] = pair.split("=");
    constants.push({ source: config.name, name: name.trim(), value: Number(value) });
  }
  for (const [name, enabled] of config.params.euromod_policy_switch_overrides || []) {
    switches.push({ source: config.name, name, enabled });
  }
}
for (const report of ukmodReports) {
  for (const c of report.cases || []) {
    for (const entry of c.metadata?.euromod_constant_overrides || []) {
      constants.push({ source: report.file, name: entry[0], value: Number(entry.at(-1)) });
    }
    for (const [name, enabled] of c.metadata?.euromod_policy_switch_overrides || []) {
      switches.push({ source: report.file, name, enabled });
    }
  }
}
assert.ok(constants.length > 0 && switches.length > 0, "found no UKMOD overrides to check");
for (const { source, name, value } of constants) {
  if (/TU/.test(name) && value === 1) {
    assert.ok(ack.includes("set take-up rates to 1"), `${source}: take-up rate ${name}`);
  } else {
    assert.ok(ack.includes(`(${name}) to ${value}`), `${source}: ${name}=${value} is not indicated`);
  }
}
for (const { source, name, enabled } of switches) {
  assert.equal(enabled, false, `${source}: ${name} switched on`);
  assert.ok(ack.includes("switch off UKMOD's take-up policies") && ack.includes(name), `${source}: ${name}`);
}

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
    // Displayed engine names agree with the oracle on both sides.
    assert.deepEqual(displayEngines(right), { left: "axiom", right: oracle });
    assert.deepEqual(displayEngines(left), { left: oracle, right: "axiom" });
    assert.equal(runAnchor(right), `run-${suite || "report"}-vs-${oracle}`);
    // Without Axiom on a side there is no oracle to credit, but the
    // displayed names still name the model.
    const pair = { suite, engines: { left: engine, right: "gettsim" } };
    assert.equal(otherOracle(pair), null);
    assert.equal(displayEngines(pair).left, oracle);
    cases += 1;
  }
}
assert.equal(otherOracle({ suite: "uk-x", engines: undefined }), null);
assert.equal(otherOracle(null), null);

// ── Mismatch labels name the model, not the platform ────────────────────
const NAMED_KINDS = ["eligibility_left_only", "eligibility_right_only", "missing_left", "missing_right"];
for (const report of axiomPairs) {
  const oracle = otherOracle(report);
  if (!PLATFORM_MODELS.includes(oracle)) continue;
  for (const kind of NAMED_KINDS) {
    const label = mismatchKindLabel(kind, displayEngines(report));
    if (oracle === "euromod") {
      assert.match(label, /EUROMOD|Axiom/, `${report.file} ${kind}`);
    } else {
      assert.doesNotMatch(label, /EUROMOD/, `${report.file} ${kind}: ${label}`);
    }
  }
  const sideKind = report.engines.left === "axiom" ? "missing_right" : "missing_left";
  assert.equal(
    mismatchKindLabel(sideKind, displayEngines(report)),
    `${engineLabel(oracle)} returned no value`,
    report.file,
  );
}

// ── The roster the overview renders ─────────────────────────────────────
const none = new Set();
const verification = verificationReports(reports, none);
const roster = new Map(groupByOracle(verification).map((o) => [o.id, o]));
assert.equal(
  [...roster.values()].reduce((n, o) => n + o.reports.length, 0),
  verification.length,
);
for (const [id, entry] of roster) {
  for (const report of entry.reports) assert.equal(otherOracle(report), id, report.file);
}
const ukFiles = verification
  .filter((r) => r.file.startsWith("axiom-euromod-uk-"))
  .map((r) => r.file)
  .sort();
assert.equal(ukFiles.length, ukmodConfigs.length, "one committed UKMOD report per UKMOD config");
assert.deepEqual(roster.get("ukmod").reports.map((r) => r.file).sort(), ukFiles);
assert.deepEqual([...roster.get("ukmod").regions], ["uk"]);
for (const region of roster.get("euromod").regions) {
  assert.ok(JRC_REGIONS.has(region), `EUROMOD card shows region ${region}`);
}
for (const region of roster.get("southmod").regions) {
  assert.ok(SOUTHMOD_MODELS[region], `SOUTHMOD card shows region ${region}`);
}

// Hiding an oracle hides its model only, on both the roster and the
// oracle-vs-oracle count (DE's EUROMOD-vs-GETTSIM runs are the JRC's).
const hideJrc = verificationReports(reports, new Set(["euromod"]));
assert.equal(hideJrc.filter((r) => otherOracle(r) === "ukmod").length, ukFiles.length);
assert.ok(!hideJrc.some((r) => otherOracle(r) === "euromod"));
const allCrossChecks = crossCheckCount(reports, none);
assert.ok(allCrossChecks > 0);
assert.equal(crossCheckCount(reports, new Set(["ukmod", "southmod"])), allCrossChecks);
assert.ok(crossCheckCount(reports, new Set(["euromod"])) < allCrossChecks);
// No committed cross-check runs UKMOD yet, so pin one: it hides with UKMOD.
const ukCrossCheck = [{ suite: "uk-benefit-cap", engines: { left: "euromod", right: "policyengine" } }];
assert.equal(crossCheckCount(ukCrossCheck, new Set(["ukmod"])), 0);
assert.equal(crossCheckCount(ukCrossCheck, new Set(["euromod"])), 1);

// ── Every oracle on the roster has an identity card ─────────────────────
for (const id of roster.keys()) {
  if (KNOWN_UNIDENTIFIED.has(id)) {
    assert.ok(!ORACLE_IDENTITY[id], `${id} now has an identity: drop it from KNOWN_UNIDENTIFIED`);
    continue;
  }
  const identity = ORACLE_IDENTITY[id];
  assert.ok(identity, `oracle ${id} reaches the roster with no ORACLE_IDENTITY entry`);
  assert.ok(identity.org && identity.what && identity.url, `incomplete identity for ${id}`);
}
for (const id of KNOWN_UNIDENTIFIED) {
  assert.ok(roster.has(id), `${id} no longer reaches the roster: drop it from KNOWN_UNIDENTIFIED`);
}
for (const id of PLATFORM_MODELS) assert.ok(roster.has(id), `no ${id} card on the roster`);
assert.deepEqual(PLATFORM_MODELS.map(engineLabel), ["EUROMOD", "UKMOD", "SOUTHMOD"]);
assert.equal(ORACLE_IDENTITY.euromod.org, "European Commission JRC");
assert.equal(ORACLE_IDENTITY.ukmod.org, "University of Essex (CeMPA)");
assert.equal(ORACLE_IDENTITY.ukmod.url, "https://www.microsimulation.ac.uk/ukmod/");
assert.ok(ORACLE_IDENTITY.ukmod.what.includes(`(${UKMOD_RELEASE})`));
assert.equal(ORACLE_IDENTITY.ukmod.acknowledgement, ack);
assert.deepEqual(ORACLE_IDENTITY.ukmod.licence, {
  name: "CC BY-NC-ND 4.0",
  url: "https://creativecommons.org/licenses/by-nc-nd/4.0/",
});
assert.equal(ORACLE_IDENTITY.southmod.org, "UNU-WIDER");
assert.equal(ORACLE_IDENTITY.southmod.acknowledgement, southmodAcknowledgement());
for (const id of ["ukmod", "southmod"]) {
  const { org, what, url } = ORACLE_IDENTITY[id];
  assert.doesNotMatch(`${org} ${what} ${url}`, /European Commission|EU's official|jrc\.ec\.europa\.eu/, id);
}
// The footer links every licensed model on the roster to its record.
assert.deepEqual(attributedOracles([...roster.keys()]).sort(), ["southmod", "ukmod"]);

// Every committed run keeps a distinct anchor.
const anchors = new Map();
for (const report of reports) {
  const anchor = runAnchor(report);
  assert.ok(!anchors.has(anchor), `${report.file} and ${anchors.get(anchor)} share ${anchor}`);
  anchors.set(anchor, report.file);
}

// ── The pages route through the helpers tested above ────────────────────
// The checks above exercise the helpers; these pin that the components
// still call them, since a revert to raw engine ids would pass the build.
const WIRING = {
  "src/components/OraclesV2.jsx": [
    "verificationReports(data.reports, HIDDEN_ORACLES)",
    "crossCheckCount(data.reports, HIDDEN_ORACLES)",
    "groupByOracle(verification)",
    "engines: displayEngines(report)",
    "attributedOracles(oracles.map((o) => o.id))",
    "{ORACLE_IDENTITY[routeOracle.id].acknowledgement}",
    "href={ORACLE_IDENTITY[routeOracle.id].licence.url}",
  ],
  "src/components/ProgramPage.jsx": ["oracle: otherOracle(report)", "engines: displayEngines(report)"],
  "src/components/Households.jsx": ["oracle: otherOracle(r)"],
};
for (const [file, needles] of Object.entries(WIRING)) {
  const source = readFileSync(file, "utf8");
  for (const needle of needles) assert.ok(source.includes(needle), `${file} no longer has ${needle}`);
  assert.doesNotMatch(source, /engines: report\.engines/, `${file} passes raw engine ids to labels`);
}

// ── Disposition tags name the model, for every model-root config ────────
const { dispositionTag } = await import("../src/components/DispositionNote.jsx");
for (const config of configs) {
  const oracle = euromodPlatformModel(config.suite);
  const expected = oracle === "southmod" ? southmodModel(config.suite) : engineLabel(oracle);
  assert.ok(expected && expected !== oracle, `no display name for ${config.suite}`);
  const tag = dispositionTag("upstream_engine_gap", {
    suite: config.suite,
    region: suiteRegion(config.suite),
    oracle,
  });
  assert.equal(tag, `${expected} gap`, `${config.name} disposition tag`);
}

const counts = PLATFORM_MODELS.map((m) => `${m} ${checked[m]}`).join(", ");
console.log(
  `ORACLE ATTRIBUTION: true (${configs.length} model-root configs; reports checked: ${counts}; ` +
    `${constants.length + switches.length} UKMOD overrides indicated; ${cases} suite × engine cases)`,
);
