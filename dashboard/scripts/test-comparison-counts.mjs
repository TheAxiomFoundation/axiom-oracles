// Run from dashboard/: bun test ./scripts/test-comparison-counts.mjs
// A read-only historical check: COMPARISON_TEST_REF=879bce60 bun test ...
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { test } from "bun:test";

import { groupByOracle, reportHouseholds, verificationReports } from "../src/utils/roster.js";
import { suiteMeta } from "../src/utils/suites.js";

const revision = process.env.COMPARISON_TEST_REF;
function source(path) {
  return revision
    ? execFileSync("git", ["show", `${revision}:dashboard/${path}`], {
        encoding: "utf8",
        maxBuffer: 32 * 1024 * 1024,
      })
    : readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
}

const page = source("src/components/OraclesV2.jsx");

test("the hero calls its mixed report-case total comparison cases", () => {
  assert.ok(
    /<em>\{compactCount\(totals\.households\)\}<\/em> comparison cases checked/.test(page),
    "the hero must label its mixed case total 'comparison cases checked'",
  );
});

test("oracle and program summaries use the same case unit", () => {
  assert.ok(/<Stat value=\{oracle\.households\.toLocaleString\(\)\} label="comparison cases"/.test(page), "oracle cards must label the same mixed count 'comparison cases'");
  assert.ok(/<span className="v2-prog-unit"> comparison cases<\/span>/.test(page), "program rows must label the same mixed count 'comparison cases'");
  assert.ok(!/individual checks across these households|\$\{p\.households\.toLocaleString\(\)\} households/.test(page), "case-count tooltips must use the same unit");
});

test("the hero total derives from case counts once per verification report", () => {
  const { reports } = JSON.parse(source("public/data/overview.json"));
  const verification = verificationReports(reports, new Set());
  // Independently derive the report total from the stored case counts,
  // rather than concept-level aggregates or distinct household IDs.
  const count = (r) => Number.isFinite(r.case_count) ? r.case_count : (r.cases || []).length;
  const sum = (rows) => rows.reduce((n, r) => n + count(r), 0);
  const parameters = verification.filter((r) => suiteMeta(r.suite).kind === "parameter");
  const federal = verification.filter((r) => ["fiit-ecps", "fiit-taxsim-ecps"].includes(r.suite));
  const remaining = verification.filter((r) => !parameters.includes(r) && !federal.includes(r));

  assert.equal(sum(parameters), 325);
  assert.equal(federal.length, 2);
  assert.deepEqual(federal.map(count), [87_519, 87_519]);
  assert.equal(sum(federal), 175_038);
  assert.equal(sum(verification), sum(parameters) + sum(federal) + sum(remaining));
  assert.equal(
    groupByOracle(verification).reduce((n, oracle) => n + oracle.households, 0),
    sum(verification),
  );
  for (const report of verification) assert.equal(reportHouseholds(report), count(report));
  if (revision === "879bce60" || revision === "879bce60c9684c63470727f36dc2abf62711f1da") {
    assert.equal(sum(verification), 992_281);
  }
  console.log(`CASE COUNT DERIVATION: ${sum(parameters)} parameter + ${sum(federal)} federal tax-unit + ${sum(remaining)} other comparison cases = ${sum(verification)} (${verification.length} reports)`);
});
