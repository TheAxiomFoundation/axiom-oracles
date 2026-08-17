# C1 build journal

All probabilities below were recorded before the corresponding gate command.
Wall-clock values are measured by the stage receipts.

## 2026-08-16 — extraction preflight

- D0 — P(pass) = 1.00. Receipt: `ops/C1-DESIGN.md` plus the coordinator's binding GO in the build instruction. Verdict: PASS.
- R1 — P(pass) = 0.80. Pending receipt: `reference/us-tariff-schedule/provenance.json`.
- R2 — P(pass) = 0.75. Pending receipt: `reference/us-tariff-schedule/integrity-receipt.json`.
- R3 — P(pass) = 0.85. Pending receipt: `reference/us-tariff-schedule/quotient-receipt.json`.

### First extraction attempt

- R1 — FAIL before receipt generation: `vector memory exhausted` caused by a full-table copy in the new extractor. Wall-clock: 218.83s. No quotient or engine run occurred.
- R1 retry — P(pass) = 0.85. The retry converts the loaded object by reference and validates columns independently.
- R2 retry — P(pass) = 0.80.
- R3 retry — P(pass) = 0.85.

### Second extraction attempt

- R1 — PASS through schema, rate, key, interval, and trajectory construction in-memory; final provenance not emitted because R2 stopped the run.
- R2 — FAIL: numeric-versus-character Census code join reported unbridged countries. Wall-clock: 508.47s. No quotient or engine run occurred.
- R1 second retry — P(pass) = 0.92.
- R2 second retry — P(pass) = 0.95 after explicit character normalization on both join keys.
- R3 second retry — P(pass) = 0.85.

### Third extraction attempt

- R1 — PASS through 68,417,040 filtered interval cells and 4,921,920 line-country trajectories.
- R2 — FAIL at bridge join after 466.79s; no quotient or engine run occurred. The next retry moves the set-difference check before hashing/join and prints any exact missing code.
- R1 third retry — P(pass) = 0.95.
- R2 third retry — P(pass) = 0.90.
- R3 third retry — P(pass) = 0.85.

### Fourth extraction attempt

- R1 — PASS through the same measured spine and trajectory counts.
- R2 — FAIL after 466.37s: pre-join set closure passed, but `data.table::merge` produced missing ISO values. No quotient or engine run occurred.
- R1 fourth retry — P(pass) = 0.97.
- R2 fourth retry — P(pass) = 0.98 using direct `match()` after the passing set-closure assertion.
- R3 fourth retry — P(pass) = 0.85.

### Fifth extraction attempt

- R1 — PASS through the same measured spine and trajectory counts.
- R2 — FAIL after 499.18s: inherited bridge row 7920 (Namibia) has a blank ISO-2. No quotient or engine run occurred.
- R1 fifth retry — P(pass) = 0.98.
- R2 fifth retry — P(pass) = 0.99 with published, hashed `7920 -> NA` ISO 3166-1 addition; the existing witness bridge is unchanged.
- R3 fifth retry — P(pass) = 0.85.

### Sixth extraction attempt

- R1 — PASS through the same measured spine and trajectory counts.
- R2 — FAIL after 454.72s because `fread` parsed the valid literal ISO code `NA` as a missing token. No quotient or engine run occurred.
- R1 sixth retry — P(pass) = 0.98.
- R2 sixth retry — P(pass) = 0.995 with empty-string-only NA parsing on both bridge inputs.
- R3 sixth retry — P(pass) = 0.85.

### Seventh extraction attempt

- R1 — PASS through 68,417,040 interval cells, 20,508 lines, 240 countries, and 14 revisions.
- R2 — PASS at 465.10s, including the published Namibia bridge addition.
- R3 — STOP receipt emitted at 551.46s: representative-only quotient 6,713,128 > 5,000,000. A lexical-hash warning made the first guard count invalid, but cannot reverse the stop.
- R3 receipt-correction retry — P(pass) = 0.97. Purpose is only to measure the A1 guard addition correctly; no engine run is authorized.

### Final extraction verdict

- R1 — PASS. Receipt: `reference/us-tariff-schedule/stop-provenance.json`. Full universe: 68,417,040 interval cells, 20,508 lines, 240 countries, 14 revisions.
- R2 — PASS. Receipt: `reference/us-tariff-schedule/stop-provenance.json`; bridge closed with the hashed 7920/Namibia addition.
- R3 — STOP / cap gate did not pass. Receipt: `reference/us-tariff-schedule/quotient-receipt.json`. The lossless EXPECTED-side trajectory quotient is 6,713,128 interval cells. The A1 exhaustive-behavior guard adds 3,200,176 cells (229,079 pairs), producing 9,913,304 candidate cells. The guard is dropped per A1, but the base quotient remains 1,713,128 above the 5,000,000 cap. Final measurement wall-clock: 594.53s.
- A1, A2, C1, C2, D1, X1, W1, N1, S1 — NOT RUN because A2 mandates STOP before any engine run when R3 exceeds the cap. Engine processes started: 0.
