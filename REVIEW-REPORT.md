VERDICT: APPROVE

PR #416 head `bd9085e3e7186733eea96d9bf225adab4482dc90` fixes the
single round-1 blocker without regressing the requested healthy paths or period
semantics. No new blocking finding was found in this scoped confirmation.

## Forced-unavailable confirmation

The probe used PolicyEngine 4.18.9, PolicyEngine-US 1.767.3, and
PolicyEngine-Core 3.30.3. It forced both native and source definition-period
discovery to return no period while leaving real PolicyEngine calculations
available, then invoked `PolicyEngineRunner.run_cases()` separately for each
variable.

- `al_tanf`, requested at `2026-01`, raised `RuntimeError` and returned no
  result. Its message names both `'al_tanf'` and `'2026-01'` and says the annual
  output-dataset value will not be served in its place.
- `ssi`, requested at `2026-01`, independently raised `RuntimeError` and
  returned no result. Its message names both `'ssi'` and `'2026-01'` and gives
  the same fail-closed explanation.

The old silent results (`3648.0` and `11928.0`) are no longer reachable under
this fault injection.

## Healthy-path regression

The same exact runtime produced:

| Variable | Requested period | Result |
| --- | --- | ---: |
| `snap_min_allotment` | `2026-01` | `23.84000015258789` |
| `snap_min_allotment` | `2026-10` | `24.3743953704834` |
| `al_tanf` | `2026-01` | `304.0` |
| `ssi` | `2026-01` | `994.0` |

These exactly match round 1's healthy-path values, including the SNAP October
COLA transition.

## Period and type invariants

- Numeric `YEAR` variable `income_tax` remained `3820.0` for both a plain
  `2026` request and a `2026-01` request.
- Boolean `is_snap_eligible` remained the boolean `True` for `2026-01`.
- During a real plain-year runner request,
  `_policyengine_definition_period` was replaced with an assertion-raising
  mock and was called zero times. The boolean path likewise made zero calls.

The new unknown-period guard is therefore after the existing plain-year and
boolean early return and does not alter either behavior.

## Exact delta and blast radius

`bd9085e3` is one non-merge commit whose sole parent is `d78d46e2`. The range
contains exactly 44 insertions, no deletions, and only these two modified files:

- `axiom_oracles/adapters/policyengine/runner.py`: six insertions
- `tests/test_policyengine_requested_month.py`: 38 insertions

The runner change is one generic guard that raises when a numeric month
request's definition period is unknown; its diagnostic includes the variable
and requested period. `git diff --check` passes.

The local GitNexus graph review rated the change low risk. The changed helper
has two direct production callers (`run_case` and `_run_case_batch_once`), five
upstream symbols, one affected process, and no signature change or unupdated
direct caller.

## Gates

- Exact-runtime targeted tests:
  `15 passed, 104 warnings`.
- Full repository pytest:
  `2253 passed, 62 skipped, 6 failed, 104 warnings in 324.96s`.
- Ruff 0.15.12:
  `All checks passed!`.

The full-suite failure set is exactly the six failures already reproduced on
clean main in round 1; there is no new failure:

1. `tests/bridges/test_ca_2026_bhst_oracle.py::test_california_bhst_exact_mappings_match_rulespec_output_set`
2. `tests/bridges/test_il_2026_pilot_income_tax_oracle.py::test_il_2026_exact_mappings_match_rulespec_output_set`
3. `tests/bridges/test_il_2026_pilot_income_tax_oracle.py::test_il_2026_positive_recapture_branch_is_fixture_covered`
4. `tests/bridges/test_ny_2026_main_income_tax_oracle.py::test_ny_2026_exact_mappings_match_rulespec_output_set`
5. `tests/bridges/test_oh_2026_income_tax_oracle.py::test_oh_2026_exact_mappings_match_the_rulespec_output_set`
6. `tests/test_dashboard_loader.py::test_loader_equivalence`

The first five are the known external RuleSpec mapping/fixture drift. The
dashboard-loader failure is the known sandboxed `npx esbuild` DNS lookup.

## Review discipline

The review ran in
`.git/review-worktrees/pr416-bd9085e3-confirm` on throwaway branch
`review/pr416-bd9085e3-confirm`. The local GitNexus index generated for the
review was removed afterward. No PR branch, remote, or GitHub state was
modified, and no remote/GitHub write was attempted.
