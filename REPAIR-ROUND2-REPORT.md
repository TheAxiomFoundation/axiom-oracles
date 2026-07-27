# SNAP residual cleanup — repair round 2

Defensive correctness and completeness audit, 2026-07-27.

## Result

- Final tracked HEAD:
  `72718c962ce06385be4858b770af6d55b43bc3fa`.
- Branch: `fed-parity/snap-residual-cleanup`.
- Starting target: `6846f433dbf126249997c92cea7a3ac3c153fe13`.
- Merged local `origin/main`:
  `9b889a27432e84804938bd3b374b4f5f7466792e`.
- No push, pull request, issue mutation, or other remote/GitHub write was
  performed.
- This report is intentionally untracked.

The five suites now genuinely resolve and run PolicyEngine 4.18.9,
PolicyEngine-US 1.767.3, and PolicyEngine-Core 3.30.3. Their canonical
reports and served case-explorer indexes record those imported runtime
versions. All fresh evidence, dispositions, served annotations, and generated
chain outputs reconcile.

## Version-labeled before/after

The baseline is exactly the five reports committed on local
`origin/main@9b889a27`, not the previous branch report.

| Snapshot | Honest engine label |
| --- | --- |
| Baseline: `origin/main@9b889a27` | Reports declare PolicyEngine 4.18.9 and PolicyEngine-US 1.752.2. Core is not recorded in those reports; the committed resolver default is Core 3.28.0. |
| Current: `72718c96` | Imported runtime recorded by every report: PolicyEngine 4.18.9 / PolicyEngine-US 1.767.3 / PolicyEngine-Core 3.30.3. |

Counts are `unexplained mismatch rows / unique households with at least one
unexplained mismatch`.

| State | Baseline raw | Baseline unexplained | Current raw | Current unexplained |
| --- | ---: | ---: | ---: | ---: |
| AL | 53 | 43 / 38 | 53 | 23 / 21 |
| MA | 255 | 49 / 47 | 255 | 83 / 55 |
| NC | 99 | 88 / 82 | 99 | 71 / 68 |
| SC | 180 | 54 / 49 | 181 | 106 / 61 |
| TN | 68 | 68 / 59 | 68 | 41 / 34 |
| **Total** | **655** | **302 / 275** | **656** | **324 / 239** |

MA and SC honestly increase because the specified 69 categorical households,
138 rows, remain unexplained. SC also has one genuinely new raw row on the
corrected generation.

## Exact oracle and generation inputs

Each of the five comparison configs explicitly pins:

- Python 3.13;
- PolicyEngine 4.18.9;
- PolicyEngine-US 1.767.3;
- PolicyEngine-Core 3.30.3.

The isolated runner now obtains report engine versions from the distributions
actually imported in its comparison subprocess. Publication fails if those
versions differ from the resolved pins. The sanity path uses the same
suite-specific pins.

All five full-population suites were regenerated with no retry:

| Suite | Cases | Comparisons | Raw mismatches |
| --- | ---: | ---: | ---: |
| `al-snap-ecps` | 1,444 | 2,888 | 53 |
| `ma-snap-ecps` | 1,632 | 3,264 | 255 |
| `nc-snap-ecps` | 1,854 | 3,708 | 99 |
| `sc-snap-ecps` | 1,283 | 2,566 | 181 |
| `tn-snap-ecps` | 1,427 | 2,854 | 68 |
| **Total** | **7,640** | **15,280** | **656** |

Clean dependency snapshots used by the sandbox execution:

- Axiom rules engine:
  `48797e101c093bb388be718c6f5d8fc9d9f94a7d`;
- RuleSpec-US:
  `ca2d424fcb85ce8c3a8f4706113331710f114460`;
- axiom-compose:
  `331b6aab62cde94a3583a5b1310b530d7b140089`;
- pinned Populace SHA-256:
  `16be6338f9d0b3c339883dae59949e995663b64cf145de6728b3dd0f916c5d5f`.

## Fresh per-case dispositions

Counts are `households / mismatch rows`.

| Evidence class | AL | MA | NC | SC | TN | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Lone minor, PolicyEngine-US #9157 | 4 / 8 | 1 / 2 | 3 / 6 | 2 / 4 | 2 / 4 | **12 / 24** |
| Zero-TANF bridge, axiom-oracles #397 | 14 / 14 | 18 / 18 | 11 / 11 | 29 / 29 | 23 / 23 | **95 / 95** |
| Minimum benefit, #9158 + #399 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | **0 / 0** |
| Categorical honest pool, no disposition | 0 / 0 | 27 / 54 | 0 / 0 | 42 / 84 | 0 / 0 | **69 / 138** |

Across all retained annotations, including pre-existing non-target mechanisms,
the aggregate served classes are:

| Disposition class | Rows | Unique households |
| --- | ---: | ---: |
| `upstream_engine_gap` | 24 | 12 |
| `bridge_artifact` | 95 | 95 |
| `axiom_encoding_gap` | 213 | 125 |
| **All annotated** | **332** | — |

The 69-household categorical pool is not included in those annotated totals.
All 138 rows are physically unannotated in both canonical reports and served
case chunks.

### Lone-minor signature

The regenerated reports contain exactly the same 12 one-person minor
households with Axiom false/zero and PolicyEngine true/positive. An explicit
Core 3.30.3 replay reproduced the mechanism:

- imputed K-12 status excludes the minor's wages and returns eligible with a
  positive benefit;
- setting K-12 explicitly false counts the wages and returns ineligible/zero;
- age 18 does not receive the exclusion.

No vanished mismatch retains a #9157 disposition.

### TANF counterfactual

Every fresh benefit-only candidate was screened, rather than carrying forward
the old selector set.

| State | Benefit-only candidates | Endogenous TANF | Pass | Fail |
| --- | ---: | ---: | ---: | ---: |
| AL | 33 | 16 | 14 | 2 |
| MA | 44 | 23 | 18 | 5 |
| NC | 72 | 13 | 11 | 2 |
| SC | 44 | 38 | 29 | 9 |
| TN | 47 | 31 | 23 | 8 |
| **Total** | **240** | **121** | **95** | **26** |

For all 121 endogenous-TANF candidates:

- the fresh baseline matched its new report value exactly;
- baseline and counterfactual SNAP eligibility were true;
- the state TANF component equaled aggregate TANF;
- both component and aggregate TANF were zero after neutralization.

Only the tolerance predicate split the set: 95 passed and 26 failed. All 26
failures remain unexplained. The authoritative artifact is
`/tmp/snap_tanf_counterfactual_all_states_17673_core3303.json`, SHA-256
`0251315e09222289f11e21efc89c5421b84459acaa23bcd1f615828dadcb0b00`.
Its pass IDs and every per-case numeric field exactly matched the committed
YAML; the 95 evidence blocks now truthfully say Core 3.30.3.

### Minimum-benefit screen

The complete shared-eligibility near-minimum set has seven rows:

| State/case | Axiom | PolicyEngine | Qualification |
| --- | ---: | ---: | --- |
| MA `ecps-2070` | 24.00 | 44.294978 | No |
| MA `ecps-2303` | 24.00 | 100.169993 | No |
| NC `ecps-27289` | 24.00 | 63.494980 | No |
| NC `ecps-27513` | 76.00 | 23.973597 | No |
| NC `ecps-27882` | 24.00 | 6.093599 | No |
| NC `ecps-28338` | 151.00 | 23.973597 | No |
| SC `ecps-28997` | 45.00 | 23.973597 | No; TANF counterfactual also failed |

None is the required Axiom $24 versus PolicyEngine $23.84/$23.973597 pair.
The #9158/#399 disposition count is therefore zero. The previously omitted
MA `ecps-2303` is now included.

## Served case-explorer data

Before repair, the targeted checker independently reproduced the review:

- 266 wrong annotations;
- 3 missing current rows;
- 2 obsolete served rows;
- 15 stale mismatch-value rows;
- stale engine metadata;
- all 138 returned categorical rows silently classified.

After regeneration:

- 7,640 cases are served across 17 chunks;
- all 656 mismatch identities and values equal the canonical reports;
- 332 annotations equal the canonical disposition classes;
- all five engine blocks record 4.18.9 / 1.767.3 / 3.30.3;
- wrong, missing, obsolete, and silent-classification counts are all zero.

The five previously missing served disposition-explanation files are also
present and exactly match 119 YAML entries. CI now runs both exact checks
immediately after canonical disposition validation.

## Merge and generated chain

Local `origin/main` was merged in commit `6143141f`. Its sole conflict,
`dashboard/public/data/freshness.json`, was resolved by running the generator,
not by selecting either side. Freshness was regenerated again after the five
new reports and now contains 213 suites and 24 executable surfaces.

The complete write chain ran in the required order, followed by the same chain
in read-only parity mode:

| Chain member | Final check |
| --- | --- |
| `apply_dispositions.py --check` | 83 files; committed dashboard data consistent |
| `extract_grids.py --check` | Up to date |
| `generate_affected_map.py --check` | 163 suites / 172 suite-repository edges |
| `check_vacuous_gate.py --check` | 136 oracle-backed configs / 213 suites / 24 executable surfaces |
| `conformance_scoreboard.py --snapshot --date 2026-07-27 --check` | 4 jurisdictions / 3 conformant |
| `conformance_ratchet.py --check` | 4 jurisdictions / no invariant regression |
| `conformance_burndown.py --check` | 4 series / 49 points |
| targeted case-artifact check | 656 rows / 332 annotated / 0 silent |
| targeted disposition-artifact check | 5 suites / 119 entries / exact YAML parity |

The `us-pe:snap` note now explicitly ties its unchanged
`23/83/71/106/41` counts to the corrected runtime.

## Validation

- Task-scoped suite: 364 passed, 3 skipped.
- Earlier runner/provenance subset: 87 passed.
- Ruff: all seven Python files changed from `origin/main` pass.
- `git diff --check`: pass.

A broad repository run was intentionally stopped in its slow integration tail
after 6m27s and 62 percent: 1,282 passed, 26 skipped, and one failure. The
failure is
`test_oh_2026_exact_mappings_match_the_rulespec_output_set`, unchanged from
`origin/main`; both available RuleSpec-US checkouts lack four Ohio source-hold
outputs expected by that test. A focused rerun produced 1 failure / 3 passes.
No SNAP-scoped test failed.

## Sandbox and scope disclosures

- Normal `uv` environment construction attempted writes under the read-only
  home cache. The suites therefore used the reviewer's cached-wheel recipe
  through a temporary, fail-closed `uv`-compatible shim. It accepted only
  Python 3.13 plus the exact 4.18.9 / 1.767.3 / 3.30.3 pins, verified the
  imported distributions, and used no network fallback.
- PolicyEngine 4.18.9 warns that its bundled manifest names US 1.752.2.
  The approved local certification override permitted the explicitly pinned
  1.767.3 data/model combination; the committed runtime-attestation gate
  independently rejects any imported-version mismatch.
- The reusable venv did not contain the `ruff` Python module; the installed
  `/opt/homebrew/bin/ruff` executable ran successfully.
- One initial test command named files that do not exist and exited before
  collection. It was corrected; the real targeted runs above pass.
- The broad test run and its unrelated Ohio failure are disclosed above; no
  result was represented as a full-suite pass.
- Existing non-target BBCE dispositions were not recharacterized as one of
  the three freshly verified mechanisms. This report makes no blanket claim
  that every retained non-target BBCE entry has a state-specific tracking
  issue or source list.
- No remote write was made.

## Repair commits

- `9962210c` — start committed round-2 audit progress.
- `6143141f` — merge local `origin/main` and regenerate conflict output.
- `ff8fe787` — pin the exact SNAP oracle stack.
- `31862ca3` — attest imported runtime versions and fail closed.
- `99b2e322` — add semantic served-case parity checks.
- `343b4bb9` — regenerate all five reports and fresh disposition evidence.
- `ddef4c3a` — regenerate served case/explanation data and add CI gates.
- `2c6ce814` — regenerate freshness and the conformance chain.
- `faf7fbc5` — record final validation.
- `72718c96` — mark the committed progress ledger complete.
