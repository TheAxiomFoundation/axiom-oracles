// Decoding of per-case zero-output masks, run by
// tests/test_emit_case_artifacts.py::test_dashboard_decodes_the_python_zero_output_masks.
// The pytest side passes ZERO_OUTPUTS_FIXTURE: rows and output_slots written by
// scripts/emit_case_artifacts.py plus, per row, the zero-valued names Python
// started from, so the JS decoder is checked against the Python encoder.

import assert from "node:assert/strict";

import { zeroOutputNames } from "../src/utils/zeroOutputs.mjs";

const fixture = JSON.parse(process.env.ZERO_OUTPUTS_FIXTURE);
for (const { row, zero } of fixture.cases) {
  assert.deepEqual(zeroOutputNames(row, fixture.output_slots), zero);
}

// A chunk written before per-case masks: every slot the case does not list.
assert.deepEqual(
  zeroOutputNames({ o: [{ n: "b", v: 2 }], o0: 2 }, ["a", "b", "c"]),
  ["a", "c"],
);
// With a mask, an unevaluated slot is never reported as zero.
assert.deepEqual(
  zeroOutputNames({ o: [{ n: "b", v: 2 }], o0: 1, oz: "8" }, ["a", "b", "c"]),
  ["a"],
);
assert.deepEqual(zeroOutputNames({ o: [] }, null), []);

console.log("ZERO OUTPUT MASKS: true");
