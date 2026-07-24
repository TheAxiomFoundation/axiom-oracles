# Nonstatutory amount exclusions — final report

- Status: complete
- Branch: `fed-parity/federal-grid-suites`
- Starting commit: `249adb5ebd01bcb6a44a4f53b8b99bd196745c1b`
- Verified implementation commit:
  `9e1a4c81031bd50d9b65dfceeb2e3dd275d0aa65`

## Schema and generator

`oracle_models_nonstatutory_amount` was already present in both
`EXCLUSION_REASONS` and the `ExclusionReason` `Literal`, introduced earlier for
three UKMOD rows. This work reused that closed-enum value and completed its
contract:

- Updated the schema definition for administrative/service-value imputations.
- Added the requested definition to the conformance README exclusion table.
- Made a note mandatory for this reason. The validation error requires the note
  to name the imputation mechanism and, where applicable, the separately
  compared eligibility surface.
- Added a direct allowed-reason test, missing-note test, unknown-reason negative
  test, and committed-US-row test.
- Added a direct generator regression test proving that fresh oracle facts
  replace generated fields while preserving an authored nonstatutory reason and
  note.

The generic preservation path is
`generate_conformance_universe.py` → `raw_to_universe_policy`: regenerated
`output_vars`, policy type, and internal variables come from the oracle, while
committed `in_scope`, `exclusion_reason`, `suite`, `note`, and comparability are
copied without a reason-specific filter.

A real regeneration against the installed PolicyEngine-US 1.767.3 tree passed:

```text
conformance[us-pe] OK: 148 policies (127 in scope, 21 excluded) match policyengine-us_1.767.3/us
```

A semantic comparison with the starting YAML found changes to exactly the seven
approved rows. The additional line churn in `conformance/us-pe.yaml` is the real
generator's deterministic serialization.

## Seven row notes

All seven rows now have `in_scope: false`,
`exclusion_reason: oracle_models_nonstatutory_amount`, no suite, their original
observable output variable, and these formula-grounded notes:

- `wic`: PolicyEngine-US 1.767.3 imputes this monthly Person value from the
  average food-package parameter
  `gov.usda.wic.value[wic_food_package_str]`, adjusted with
  `gov.usda.wic.cvb.current`,
  `gov.usda.wic.cvb.included_in_value`, and
  `gov.usda.wic.cvb.replaces_included_value`, then gates it on
  `is_wic_eligible` and `would_claim_wic` (subject to
  `gov.usda.wic.abolish_wic`). This is a package-value imputation, not a
  statutory amount formula; `is_wic_eligible` is compared separately
  (rulespec-us PR #1010).

- `free_school_meals`: PolicyEngine-US 1.767.3 imputes this annual SPM-unit
  value from the `FREE` branch of `school_meal_tier`: the NSLP-plus-SBP
  reimbursement differential over the paid tier from
  `gov.usda.school_meals.amount.nslp[state_group_str][tier]` and
  `gov.usda.school_meals.amount.sbp[state_group_str][tier]`, multiplied by
  `gov.usda.school_meals.school_days` and the SPM-unit count of
  `is_in_k12_school`. This is a reimbursement-rate service-value imputation,
  not a statutory amount formula; the `school_meal_tier` eligibility
  classification is compared separately.

- `reduced_price_school_meals`: PolicyEngine-US 1.767.3 imputes this annual
  SPM-unit value from the `REDUCED` branch of `school_meal_tier`: the
  NSLP-plus-SBP reimbursement differential over the paid tier from
  `gov.usda.school_meals.amount.nslp[state_group_str][tier]` and
  `gov.usda.school_meals.amount.sbp[state_group_str][tier]`, multiplied by
  `gov.usda.school_meals.school_days` and the SPM-unit count of
  `is_in_k12_school`. This is a reimbursement-rate service-value imputation,
  not a statutory amount formula; the `school_meal_tier` eligibility
  classification is compared separately.

- `chip`: PolicyEngine-US 1.767.3 imputes this annual Person value as state
  separate-CHIP spending divided by enrollment, using
  `calibration.gov.hhs.cms.chip.spending.separate_chip.total[state_code]` and
  `calibration.gov.hhs.cms.chip.enrollment.separate_chip[state_code]`, then
  gates it on `chip_enrolled` (eligibility plus take-up). This is a per-capita
  expenditure imputation, not a statutory amount formula; `is_chip_eligible`
  is compared separately.

- `head_start`: PolicyEngine-US 1.767.3 imputes this annual Person value as
  state Head Start spending per funded slot:
  `gov.hhs.head_start.spending[state_code_str]` divided by
  `gov.hhs.head_start.enrollment[state_code_str]` (zero for nonpositive
  enrollment), multiplied by `takes_up_head_start_if_eligible`. This is an
  administrative slot-cost imputation, not a statutory amount formula;
  `is_head_start_eligible` is compared separately (rulespec-us PR #1010).

- `early_head_start`: PolicyEngine-US 1.767.3 imputes this annual Person value
  as state Early Head Start spending per funded slot:
  `gov.hhs.head_start.early_head_start.spending[state_code_str]` divided by
  `gov.hhs.head_start.early_head_start.enrollment[state_code_str]` (zero for
  nonpositive enrollment), multiplied by
  `takes_up_early_head_start_if_eligible`. This is an administrative slot-cost
  imputation, not a statutory amount formula;
  `is_early_head_start_eligible` is compared separately (rulespec-us PR #1010).

- `commodity_supplemental_food_program`: PolicyEngine-US 1.767.3 imputes this
  annual Person value directly from `gov.usda.csfp.amount`, an administrative
  cost-per-participant parameter derived from program cost divided by
  participation, and gates it on
  `commodity_supplemental_food_program_eligible`. This is a
  food-package/caseload service-value imputation, not a statutory amount
  formula; `commodity_supplemental_food_program_eligible` is compared
  separately (rulespec-us PR #1008).

The source inspection used a warm uv-managed Python 3.13 environment containing
PolicyEngine-US 1.767.3 and PolicyEngine Core 3.30.3. It inspected the installed
variable classes directly, including the transitive school-meal subsidy and
CHIP per-capita formulas.

## Held rows

The existing regression guard passed with all three requested credit rows still
in scope, uncovered, and without an exclusion reason:

- 25D: `residential_clean_energy_credit`
- 30D: `new_clean_vehicle_credit`
- 25E: `used_clean_vehicle_credit`

## Disposition evidence

The two disposition classes remain `upstream_engine_gap`. Only their
`evidence.sources` lists changed:

- `us-qbid-grid` now includes
  https://github.com/PolicyEngine/policyengine-us/issues/9150.
- `us-savers-credit-grid` now includes
  https://github.com/PolicyEngine/policyengine-us/issues/9151.

All pinned values, mechanisms, source-change expiry flags, and classes are
unchanged.

## Final conformance

| Metric | Before | After |
| --- | ---: | ---: |
| Policies in scope | 134 | 127 |
| Covered | 35 | 35 |
| Covered percent | 26.1194% | 27.5591% |
| Excluded | 14 | 21 |
| Uncovered | 99 | 92 |
| `oracle_models_nonstatutory_amount` exclusions | 0 | 7 |
| Unexplained | 0 | 0 |
| Axiom-attributed open | 0 | 0 |

The host was on July 23 in America/New_York but had crossed midnight UTC.
Accordingly, the pre-change us-pe `2026-07-23` history point remains 35/134 and
the new 35/127 result is recorded in the required `2026-07-24` UTC snapshots.
All four jurisdictions received a real July 24 snapshot, and the burndown was
regenerated to 37 total points.

## Ratchet behavior

The ratchet handles the denominator decrease as designed:

1. Before re-pinning, `conformance_ratchet.py --check` passed with the live
   35/127 scoreboard against the committed 35/134 ratchet. Regression checks
   examine covered, unexplained, and Axiom-attributed-open; they do not reject a
   changed informational denominator.
2. The default writer computes `covered_min = max(existing, live)`, so the
   coverage floor stayed 35.
3. It computes both ceilings with `min(existing, live)`, so
   `unexplained_max` and `axiom_attributed_open_max` stayed 0.
4. It records the live denominator directly, so `policies_in_scope` changed
   from 134 to 127.
5. The post-write ratchet check passed.

Final us-pe ratchet:

```yaml
covered_min: 35
unexplained_max: 0
axiom_attributed_open_max: 0
policies_in_scope: 127
```

## Regeneration and gates

Real write-mode regeneration completed for dispositions, the affected map,
vacuous/freshness data, scoreboard and all detail mirrors, the UTC snapshot,
ratchet, and burndown. The affected map and freshness artifacts were already
byte-current; the scope-derived files changed.

All final checks passed:

- Comparison registry listing: 136 entries.
- Rule verification: 20,154 rules; 99.6% grounded; 98.4% manifest-backed;
  17/111 executable surfaces.
- State-tax Populace contract: 43 jurisdictions, 28 ready, 15 blocked, 162
  explicit inputs, 2 explicit relations.
- Dispositions: 77 files validated and consistent with dashboard data. The
  checker emitted only its two pre-existing expired-entry notes.
- Grids and boundary suggestions: current.
- Affected map: 157 suites and 171 suite-repository edges.
- Vacuous gate: 137 oracle-backed configs; 184 suites; 17 executable surfaces;
  56 suites awaiting provenance.
- Universe checks: UK and BE matched their installed exact releases. The normal
  all-check cleanly skipped mismatched local UK-PE and US-PE checkouts; the
  separate exact installed PolicyEngine-US 1.767.3 check passed at 148 policies,
  127 in scope, and 21 excluded.
- Conformance compositions: 23 covered BE suites current.
- Scoreboard: 4 jurisdictions, 3 conformant.
- Ratchet: no invariant regressed.
- Burndown: 4 series, 37 points.
- Ruff: `All checks passed!`
- Full pytest: 1,693 passed, 33 skipped, 0 failed, 0 warnings in 251.91 seconds.
- Offline build: freshly produced
  `dist/axiom_oracles-0.2.1.tar.gz` and
  `dist/axiom_oracles-0.2.1-py3-none-any.whl`. Because the sandbox's writable
  isolated uv cache did not contain Hatchling and the populated global cache
  was read-only, the successful final build used uv `--no-build-isolation` with
  the cached Hatchling backend on `PYTHONPATH`.
- `git diff --check`: clean.

## Commits

- `b1cb92e6cb7661fd616da5137121c1673c4d5f9a` — start and commit progress.
- `b2630ab6ad47b728ba04205c15af724a01a65758` — enforce and document the
  nonstatutory note contract; add focused schema/generator tests.
- `49e4d94907ad87369ba1ce4d854684a9f09911dd` — apply the seven exclusions and
  exact formula-grounded notes.
- `e29b7832323f1b67ec32dbfb1443d84deaea0992` — append upstream issue evidence.
- `31d6ad5777022141ae434610a3e65b6501ea6270` — regenerate live conformance
  scope, detail, ratchet, and burndown artifacts.
- `9e1a4c81031bd50d9b65dfceeb2e3dd275d0aa65` — record the correct 2026-07-24
  UTC snapshots and preserve the prior July 23 history point.
- `251befada9ca1e2bd8a24d5efc98efc3958e1377` — write the final report,
  completion marker, and completed progress state.

No pushes, pull requests, or GitHub writes were made.
