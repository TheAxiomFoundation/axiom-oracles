// Run from dashboard/: bun test ./scripts/test-uncompared-rollups.mjs
// UNCOMPARED_TEST_REF reproduces the finding using a committed reader.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { test } from "bun:test";
import * as suites from "../src/utils/suites.js";
import * as format from "../src/utils/format.js";
import { countUnexplained } from "../src/utils/programs.js";
import { reportHouseholds } from "../src/utils/roster.js";
import legacyRendering from "./fixtures/uncompared-rollups-legacy.json";

const root = new URL("../../", import.meta.url);
function source(ref) {
  const path = "dashboard/src/components/OraclesV2.jsx";
  return ref
    ? execFileSync("git", ["show", `${ref}:${path}`], { cwd: root, encoding: "utf8" })
    : readFileSync(new URL(path, root), "utf8");
}
const page = source(process.env.UNCOMPARED_TEST_REF);
const deps = { ...suites, countUnexplained, reportHouseholds };

// Execute each component's actual accumulation body with its real readers.
function programRollup(page, marker, reports) {
  const begin = page.indexOf("    const byProgram = new Map();", page.indexOf(marker));
  const end = page.indexOf("    return [...byProgram.values()]", begin);
  assert.ok(begin >= 0 && end > begin);
  return new Function(...Object.keys(deps), "regionScoped", "model", "knownCauses", "data",
    page.slice(begin, end) + "return [...byProgram.values()];")(
    ...Object.values(deps), { reports }, { verification: reports }, [], { knownCauses: [] },
  );
}

function report(uncompared, mismatches = 0, total = 1) {
  return {
    suite: "al-snap-ecps", engines: { left: "axiom", right: "policyengine" },
    case_count: total + uncompared,
    aggregates: [{ concept: "benefit", comparison_count: total,
      mismatch_count: mismatches + uncompared, uncompared_mismatches: uncompared }],
  };
}

for (const marker of ["const programRows = useMemo(", "const allPrograms = useMemo("]) {
  test(`${marker} sums engine errors separately from compared checks`, () => {
    const reports = [report(1), report(2, 1, 3)];
    const [row] = programRollup(page, marker, reports);
    assert.equal(row.total, 4);
    assert.equal(row.mismatches, 1);
    assert.equal(row.uncompared, 3);
    const [baseline] = programRollup(page, marker, [report(0), report(0, 1, 3)]);
    assert.equal((row.total - row.mismatches) / row.total,
      (baseline.total - baseline.mismatches) / baseline.total);
  });
}

function renderRow(page, p) {
  const begin = page.indexOf("function ProgRow(");
  const end = page.indexOf("\nconst programKeyOf", begin);
  const jsx = page.slice(begin, end);
  const compiled = new Bun.Transpiler({ loader: "jsx", tsconfig: {
    compilerOptions: { jsx: "react" },
  } }).transformSync(jsx);
  const ProgRow = new Function("React", "REGION_LABELS", ...Object.keys(format),
    compiled + "; return ProgRow;")(React, { us: "US" }, ...Object.values(format));
  return renderToStaticMarkup(React.createElement(ProgRow, { p, onOpenProgram() {} }));
}
const row = { key: "snap__AL", label: "Alabama SNAP", region: "us", households: 2,
  total: 1, mismatches: 0, rate: 100 };

test("a partly errored program renders agreement alongside its engine errors", () => {
  const html = renderRow(page, { ...row, uncompared: 1 });
  assert.ok(html.includes("100%"));
  assert.match(html, />1<\/span><span[^>]*>not compared \(engine errors\)<\/span>/);
});

test("programs without uncompared pairs retain the reviewed rendering exactly", () => {
  // Captured from 32e7a4cdee2d89999a3ec8cc648f3fa5868a45a7. Keep CI's
  // shallow checkout independent of historical Git objects.
  for (const { props, html } of legacyRendering) {
    assert.equal(renderRow(page, props), html);
    assert.equal(renderRow(page, { ...props, uncompared: 0 }), html);
  }
});
