// Semantics of the SOUTHMOD model-findings helpers, run by
// tests/test_southmod_issues.py::test_dashboard_findings_helpers_agree_with_python
// over the published bundle. The pytest side
// passes SOUTHMOD_FINDINGS_EXPECTED: the dashboard registry (parsed from
// suites.js) and the per-region entry counts Python reads from the packaged
// ledgers, so the JS grouping is checked against an independent count.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  axiomGapLabel,
  CLASSIFICATION_LABELS,
  classificationLabel,
  codeLabel,
  findingAnchor,
  findingText,
  foldGroups,
  groupFindings,
  scopeFindings,
  STATUS_LABELS,
  STATUS_TONES,
  statusLabel,
} from "../src/utils/southmodFindings.mjs";

const expected = JSON.parse(process.env.SOUTHMOD_FINDINGS_EXPECTED);
const models = expected.models;
const bundle = JSON.parse(
  readFileSync(new URL("../public/data/southmod-issues.json", import.meta.url)),
);

// Grouping: one group per registry model, in registry order, counts equal to
// Python's.
const groups = groupFindings(bundle, models);
assert.deepEqual(
  groups.map((g) => g.region),
  Object.keys(models),
);
for (const g of groups) {
  assert.equal(g.model, models[g.region].model);
  assert.equal(g.country, models[g.region].country);
  assert.equal(g.entries.length, expected.counts[g.region] ?? 0, g.region);
  assert.equal(g.ledger === null, expected.counts[g.region] === undefined);
  if (g.ledger === null) assert.ok(g.note, `${g.region} needs a note`);
}
const all = groups.flatMap((g) => g.entries);
assert.equal(new Set(all.map((e) => e.id)).size, all.length);

// Every entry renders prose, a label for its classification and status, and
// a unique anchor; no label falls back to raw words for a published code.
for (const e of all) {
  assert.ok(findingText(e).length > 0, e.id);
  assert.ok(e.classification in CLASSIFICATION_LABELS, e.classification);
  if (e.status != null) {
    assert.ok(e.status in STATUS_LABELS, e.status);
    assert.ok(e.status in STATUS_TONES, e.status);
  }
  assert.equal(findingAnchor(e.id), `finding-${e.id}`);
}
assert.equal(new Set(all.map((e) => findingAnchor(e.id))).size, all.length);
assert.equal(codeLabel({}, "some_new_code"), "some new code");
assert.equal(codeLabel({}, null), null);
assert.equal(classificationLabel("convention_difference"), "convention difference");
assert.equal(statusLabel(undefined), null);
assert.equal(axiomGapLabel(false), "not an Axiom gap");
assert.equal(axiomGapLabel(true), "counts as an Axiom gap");
assert.equal(axiomGapLabel(null), "Axiom gap unadjudicated");
assert.equal(axiomGapLabel(undefined), "Axiom gap unadjudicated");
assert.equal(findingText({ observed: "o" }), "o");
assert.equal(findingText({ summary: "s", observed: "o" }), "s");

// A model the bundle omits still gets a group, with no ledger.
const missing = groupFindings({ models: [] }, models);
assert.ok(missing.every((g) => g.ledger === null && g.entries.length === 0));
assert.deepEqual(groupFindings(null, models).length, Object.keys(models).length);

// Scoping, exhaustively: every region (and none) x every program filter that
// keeps a single suite, plus keep-nothing and keep-everything.
const suites = [...new Set(all.flatMap((e) => e.affected_comparisons || []))];
const filters = [
  null,
  () => false,
  () => true,
  ...suites.map((s) => Object.assign((suite) => suite === s, { only: s })),
];
// Python's independent per-suite counts cover exactly the suites cited.
assert.deepEqual([...suites].sort(), Object.keys(expected.suite_counts).sort());
let cases = 0;
for (const region of [null, ...Object.keys(models)]) {
  const regional = groups.filter((g) => !region || g.region === region);
  const regionalTotal = regional.reduce((n, g) => n + g.entries.length, 0);
  for (const keepSuite of filters) {
    const scope = scopeFindings(groups, { region, keepSuite });
    cases += 1;
    // Region narrowing and the region total.
    assert.ok(scope.groups.every((g) => !region || g.region === region));
    assert.equal(scope.total, regionalTotal);
    // inScope is exactly the entries shown, never more than the total.
    const shownEntries = scope.groups.flatMap((g) => g.entries);
    assert.equal(scope.inScope, shownEntries.length);
    assert.ok(scope.inScope <= scope.total);
    for (const g of scope.groups) {
      assert.equal(g.total, regional.find((r) => r.region === g.region).entries.length);
    }
    if (!keepSuite) {
      // No program filter: every group in the region stays, untouched.
      assert.deepEqual(
        scope.groups.map((g) => g.region),
        regional.map((g) => g.region),
      );
      assert.equal(scope.inScope, regionalTotal);
    } else {
      // A filter keeps exactly the entries touching an accepted suite and
      // drops groups it leaves empty.
      const want = regional
        .flatMap((g) => g.entries)
        .filter((e) => (e.affected_comparisons || []).some(keepSuite));
      assert.deepEqual(shownEntries, want);
      assert.ok(scope.groups.every((g) => g.entries.length > 0));
    }
    // Differential: a single-suite filter keeps exactly the entries Python
    // counted as naming that suite, in this region.
    if (keepSuite?.only) {
      const byRegion = expected.suite_counts[keepSuite.only];
      const want = region
        ? byRegion[region] ?? 0
        : Object.values(byRegion).reduce((n, c) => n + c, 0);
      assert.equal(scope.inScope, want, `${region} ${keepSuite.only}`);
    }
    // Folding never loses or splits a group, and shows at least one.
    const fold = foldGroups(scope.groups, 10, null);
    assert.deepEqual([...fold.shown, ...fold.rest], scope.groups);
    if (scope.groups.length) assert.ok(fold.shown.length >= 1);
    const shownLines = fold.shown.reduce((n, g) => n + g.entries.length, 0);
    if (fold.rest.length) {
      assert.ok(shownLines >= 10);
      const lastless = shownLines - fold.shown.at(-1).entries.length;
      assert.ok(lastless < 10 || fold.shown.length === 1);
    }
  }
}
assert.equal(cases, (1 + Object.keys(models).length) * filters.length);

// A pinned (deep-linked) entry in the folded tail is reported as such.
const fold = foldGroups(groups, 1, null);
if (fold.rest.length) {
  const tailId = fold.rest.flatMap((g) => g.entries)[0]?.id;
  if (tailId) assert.equal(foldGroups(groups, 1, tailId).pinnedInRest, true);
  const headId = fold.shown[0].entries[0]?.id;
  if (headId) assert.equal(foldGroups(groups, 1, headId).pinnedInRest, false);
}

console.log(`SOUTHMOD FINDINGS SEMANTICS: true (${cases} scope cases)`);
