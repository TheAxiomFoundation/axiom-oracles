# C1 build journal

All probabilities below were recorded before the corresponding gate command.
Wall-clock values are measured by the stage receipts.

## 2026-08-17 — amended cap execution

- A2' adjudication receipt: cap raised to 12,000,000 evaluated interval cells; the 6,713,128-cell quotient and 3,200,176-cell fixed-regime guard are both required, totaling 9,913,304 cells. No Yale re-extraction is authorized because the committed receipt keys remain valid.
- R1/R2/R3 authorized extractor rerun — P(pass) = 0.98, conditional on exact reproduction of 68,417,040 / 6,713,128 / 3,200,176 / 480,580 and immediate stop on any difference.
- R1/R2/R3 authorized extractor rerun — PASS. The single invocation reproduced all four binding counts exactly, retained the guard, and emitted the five required artifacts. Evaluated interval cells: 9,913,304 under the 12,000,000 cap. Wall-clock: 669.29s. Engine processes started: 0. Receipts: `reference/us-tariff-schedule/{provenance,integrity-receipt,quotient-receipt,full-exposure}.json`, `selected-intervals.csv.gz`, and `trajectory-class-map.csv.gz`.
- A1 — P(pass) = 0.98. Pending receipt: fresh validation of `conformance/executable/us-tariff-witness.json`, including absolute-path compilation of the 100 generated chapters plus the five-line witness and exact witness replay. Engine-process ceiling: 3.
- A1 first invocation — FAIL before engine start: the ad-hoc `.venv` lacks PyYAML (`ModuleNotFoundError: yaml`). Wall-clock: 0.07s. Engine processes started: 0.
- A1 retry — P(pass) = 0.98 using the repository's locked `uv run` environment.
- A1 locked-environment retry — FAIL before engine start: sandbox policy denied access to uv's default cache. Wall-clock: 0.04s. Engine processes started: 0.
- A1 cache-relocated retry — P(pass) = 0.95 with `UV_CACHE_DIR` confined to writable temporary storage; lockfile unchanged.
- A1 cache-relocated retry — FAIL before engine start: the writable cache lacks a locked wheel and network is disabled. Wall-clock: 0.16s. Engine processes started: 0.
- A1 installed-environment retry — P(pass) = 0.98 using the readable sibling `axiom-oracles/.venv` interpreter with the same project dependencies already installed.
- A1 installed-environment retry — PASS. Receipt: `conformance/executable/us-tariff-witness.json`; 101/101 programs compiled, pinned engine hash matched, and 10/10 witness values reproduced by exact JSON numeric equality with `executable=true`. Wall-clock: 12.03s. Maximum concurrent engine processes: 1.
- A2 — P(pass) = 0.90. Pending receipt: a content-addressed cache for all 709,659 selected line-country pairs, using the pinned `b16_entry_flags.py` and the generated statistical-member to rate-bearing-line routing.
- A2 first feed attempt — FAIL before engine start: it passed the Yale 10-digit statistical member as `hts_line`; the generated schedule parameters require the rate-bearing ancestor key. The attempted benchmark hard-failed all 5,000 cases on the first member (`0101210010`), so its timing projection and output were rejected. Engine processes started sequentially: 1; maximum concurrent: 1.
- A2 routing retry — P(pass) = 0.95, with `hts_line` derived only from the pinned generated chapter parameter tables and the Yale member retained separately as `hts_number`.
- A2 routing retry — STOP before engine execution: the selected Yale universe contains members under non-ad-valorem rate lines for which the generated bulk program intentionally has disposition keys but no General-rate parameter. First deterministic counterexample: Yale member `0102294024`; generated rate-bearing/disposition key `0102294000` (`specific`). The required MFN and statutory-total queries would therefore hard-fail, and the C1 contract forbids dispositioning engine errors. No valid first shard exists, so no greater-than-six-hour projection can be computed. C1/C2, D1, X1, W1, N1, and S1 were not run.
- A2 Amendment A7 — P(pass) = 0.97. The disposition pre-pass reads all 100 generated General/column-2 Text tables before shard planning, receipts every one of the 20,508 selected HTS members, and conserves all 9,913,304 evaluated cells. It routes 8,762,852 cells to full comparison and 1,150,452 to components-only (`11.6051318511%`). The latter receive `known_not_comparable` base/total reasons; no engine error is reclassified. Formula inspection of 900 component rules proves seven authority components are base-independent. IEEPA and forced-labor section 301 genuinely reference `mfn_ad_valorem_rate`, so their 2,300,904 component slots are separately structurally excluded on these cells. Wall-clock: 60.018s. Engine processes: 0. Receipts: `reference/us-tariff-schedule/disposition-routing{.csv.gz,-receipt.json}`.
- A2 Amendment A7 — PASS. Focused fail-closed suite: 5 passed, including the required N1 mutant that routes a `specific` line to full comparison and must fail before shard planning.
- C1 execution projection — CHECKPOINT. Even before two-endpoint replay, the safe A7 plan contains 104,444,536 comparison slots (96,391,372 on full cells plus 8,053,164 independent-component slots). This is 16.9 times B1.6 G5's 6,179,232-comparison campaign, which the binding design records as an hours-scale run. The projected C1 engine stage therefore exceeds six hours by a wide margin. Per the checkpoint instruction, no engine shard was started; C1/C2, D1, X1, W1, downstream N1, and S1 remain pending after this committed A2 checkpoint. Maximum concurrent engine processes: 0.
- C1 authorized first evaluation shard — P(pass) = 0.90. The deterministic first nonempty chapter shard will compile from the pinned RuleSpec checkout, feed only the A7-routed `hts_line` plus the pinned `b16_entry_flags.py` outputs and declared neutral facts, query only its permitted surface, fail closed on any engine error, and measure engine wall-clock separately from Python-side comparison. The measured shard will replace the pre-run analogy with a 16-hour total projection before further shards are launched. Engine-process ceiling: 3.
- C1 authorized first evaluation shard — FAIL CLOSED. The chapter-01 invocation attempted 5,001 deterministic endpoint cases and produced 5,001 engine errors before any value result because the feed passed `entry_is_line_c`, which is emitted by the pinned `b16_entry_flags.py` but is not a legal input slot in the generated chapter composition. First error: `dataset input us:policies/cbp/us-tariff-schedule/generated/ch01/ch01#input.entry_is_line_c must use an absolute legal RuleSpec reference that resolves to an input slot, derived rule, or parameter in the compiled program`. Engine wall-clock including compile: 0.879s; invocation wall-clock including Python planning: 9.311s. Maximum concurrent engine processes: 1. Receipt: `reference/us-tariff-schedule/first-shard-failure-receipt.json`. Per the standing zero-unexplained bar, an engine error after A7 routing is unexplained and the campaign stops: no valid evaluation shard, revised projection, Python-side comparison, C2, D1, X1, W1, remaining N1, or S1 was produced.
- A2 declared-input amendment — P(pass) = 0.99. The harness introspects each compiled generated composition, asserts full supplied-versus-declared closure before execution, and permits only the coordinator-confirmed retired exemplar flags to be projected away.
- A2 declared-input amendment — PASS. All 100 compiled compositions drop exactly `entry_is_line_c` and `entry_is_line_e`; no chapter has another dropped tool feed flag or a declared-but-unfed tool flag. The receipt records that the engine's strict absent input raises `MissingInput`, while `input_or_else` substitutes a compiled default; campaign policy therefore stops in the harness before either behavior can hide an unfed declared case input. Required N1 mutants for an undeclared feed field and a declared-but-unfed field both fail closed. Wall-clock: 7.673s. Engine processes: 100 sequential compile invocations; maximum concurrent: 1. Receipt: `reference/us-tariff-schedule/declared-input-contract-receipt.json`.
- C1 corrected first-shard projection — P(pass) = 0.95. PASS. The declared-input filter was applied to 5,001 deterministic chapter-01 full-comparison endpoint cases. Two independent pinned-engine replays completed 5,001/5,001 results with zero errors and identical canonical result SHA-256 `aa977aab3e8818582171d2442678c5279ff8b742d480d68211893c5a6c58a04c`; wall-clock 4.123s and 5.651s. The conservative two-endpoint upper bound of 19,826,608 cases, divided across at most three workers using the slower replay, projects 2.0743 engine-hours, below the binding 16-hour ceiling. Receipt: `reference/us-tariff-schedule/evaluation-projection-receipt.json`.

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
