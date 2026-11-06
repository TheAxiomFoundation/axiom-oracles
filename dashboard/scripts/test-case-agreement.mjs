import assert from "node:assert/strict";

import { caseAgreement, triangulate } from "../src/utils/caseAgreement.mjs";

assert.equal(caseAgreement(100), true);
assert.equal(caseAgreement(99.9999995), false);
assert.equal(caseAgreement(null), null);
assert.equal(caseAgreement(Number.NaN), null);

const runs = [
  { suite: "a", oracle: "policyengine" },
  { suite: "b", oracle: "taxsim" },
];
const measured = (a, b) => ({
  a: { cases: [{ id: "case", r: a }] },
  b: { cases: [{ id: "case", r: b }] },
});
const buckets = (result) => Object.fromEntries(result.buckets);

// A case no run measured never reads as disagreeing with every oracle.
const unmeasured = triangulate(runs, measured(null, null));
assert.equal(unmeasured.joined, 0);
assert.deepEqual(buckets(unmeasured), {});

// A case one run didn't measure leaves the join, whatever the other run says.
const partial = triangulate(runs, measured(0, null));
assert.equal(partial.joined, 0);
assert.deepEqual(buckets(partial), {});

assert.deepEqual(buckets(triangulate(runs, measured(0, 0))), { none: ["case"] });
assert.deepEqual(buckets(triangulate(runs, measured(100, 0))), { policyengine: ["case"] });
assert.deepEqual(buckets(triangulate(runs, measured(0, 100))), { taxsim: ["case"] });
assert.deepEqual(buckets(triangulate(runs, measured(100, 100))), {
  "policyengine+taxsim": ["case"],
});

console.log("CASE AGREEMENT SEMANTICS: true");
