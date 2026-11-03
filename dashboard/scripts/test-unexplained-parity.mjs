// Canonical assessments and existing publication views, without package-wide
// module-mode changes. The pytest wrapper compares these with Python results.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../src/utils/unexplained.js", import.meta.url), "utf8");
const { assessUnexplained, publishedUnexplained } = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
);
let input = "";
for await (const chunk of process.stdin) input += chunk;
const cases = JSON.parse(input, (_key, value) => {
  if (value && typeof value === "object" && Object.keys(value).length === 1 &&
      Object.hasOwn(value, "$nonfinite")) {
    return { nan: NaN, inf: Infinity, "-inf": -Infinity }[value.$nonfinite];
  }
  return value;
});
const actual = cases.map(({ report, options = {}, expected, name }) => {
  let result;
  try {
    result = {
      assessment: assessUnexplained(report, options),
      dashboard: publishedUnexplained(report, options),
      scoreboard: publishedUnexplained(report, { ...options, view: "scoreboard" }),
    };
  } catch (error) {
    result = { error: error.message };
  }
  if (expected !== undefined) assert.deepEqual(result, expected, name);
  return result;
});
console.log(JSON.stringify(actual));
console.error(`UNEXPLAINED PARITY: ${cases.length} complete assessments agree`);
