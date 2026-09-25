// The pytest wrapper supplies every committed dashboard JSON document (plus
// synthetic grid-shaped and duplicate-suite reports), the typed diagnostic
// suites, and the Python unexplained ratchet's per-suite counts. The
// dashboard's gated per-suite counts must equal them exactly.
import assert from "node:assert/strict";
import { gatedUnexplainedBySuite } from "../src/utils/unexplained.js";

let input = "";
for await (const chunk of process.stdin) input += chunk;
const { documents, known_causes, diagnostics, expected } = JSON.parse(input);
const diagnostic = new Set(diagnostics);
const actual = gatedUnexplainedBySuite(documents, {
  known_causes,
  isDiagnostic: (suite) => diagnostic.has(suite),
});
assert.deepEqual(actual, expected);
const total = Object.values(actual).reduce((sum, count) => sum + count, 0);
console.log(`UNEXPLAINED GATE PARITY: ${Object.keys(actual).length} suites, total ${total}`);
