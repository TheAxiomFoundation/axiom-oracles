import assert from "node:assert/strict";

import { caseAgreement } from "../src/utils/caseAgreement.mjs";

assert.equal(caseAgreement(100), true);
assert.equal(caseAgreement(99.9999995), false);
assert.equal(caseAgreement(null), null);
assert.equal(caseAgreement(Number.NaN), null);

console.log("CASE AGREEMENT SEMANTICS: true");
