// Default publication semantics are deliberately preserved; opt-in canonical
// semantics are validated separately. No package-wide module-mode change.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../src/utils/unexplained.js", import.meta.url), "utf8");
const { gatedUnexplainedBySuite } = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
);
let input = "";
for await (const chunk of process.stdin) input += chunk;
const { documents, known_causes, diagnostics, expected } = JSON.parse(input);
const diagnostic = new Set(diagnostics);
const actual = gatedUnexplainedBySuite(documents, {
  known_causes,
  isDiagnostic: suite => diagnostic.has(suite),
});
assert.deepEqual(actual, expected);
const total = Object.values(actual).reduce((sum, count) => sum + count, 0);
console.log(`UNEXPLAINED GATE PARITY: ${Object.keys(actual).length} suites, total ${total}`);
