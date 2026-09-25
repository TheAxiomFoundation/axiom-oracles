// The pytest wrapper supplies all committed reports and synthetic mutants on
// stdin. Import the browser implementation directly: no bundler/dependencies.
import assert from "node:assert/strict";
import { assessUnexplained } from "../src/utils/unexplained.js";

let input = "";
for await (const chunk of process.stdin) input += chunk;
const cases = JSON.parse(input, (_key, value) => {
  if (value && typeof value === "object" &&
      Object.keys(value).length === 1 && Object.hasOwn(value, "$nonfinite")) {
    return { nan: NaN, inf: Infinity, "-inf": -Infinity }[value.$nonfinite];
  }
  return value;
});
for (const { name, report, options, expected } of cases) {
  assert.deepEqual(assessUnexplained(report, options), expected, name);
}
console.log(`UNEXPLAINED PARITY: ${cases.length} complete assessments agree`);
