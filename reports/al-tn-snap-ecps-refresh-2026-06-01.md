# AL/TN SNAP ECPS Refresh - 2026-06-01

## Scope

This refresh reran the composed Alabama and Tennessee SNAP programs after the
`rulespec-us-al` manual batch and the `axiom-encode` Alabama oracle coverage
classification were merged. The comparison path composes from
`axiom-programs`, compiles with `axiom-rules-engine`, and compares Axiom to
PolicyEngine on the state-filtered Enhanced CPS population.

No Python overrides were added to force alignment.

## Commands

```bash
uv run python scripts/run_comparison.py al-snap-ecps --summary
uv run python scripts/run_comparison.py tn-snap-ecps --summary
```

Both commands regenerate the dashboard report JSON in
`dashboard/public/data/`.

## Alabama

- Cases: 704
- Comparisons: 1,408
- Mismatch entries: 36
- SNAP benefit: 672 / 704 matched
- SNAP eligibility: 700 / 704 matched
- Benefit residuals: 32
- Eligibility residuals: 4
- Eligibility left-only: 3
- Eligibility right-only: 1
- Benefit residual direction: 30 Axiom > PolicyEngine, 2 PolicyEngine > Axiom

Current driver breakdown:

- 22 of 32 AL benefit residuals have positive PolicyEngine `al_tanf`.
- All 22 TANF-positive residuals are in the Axiom > PolicyEngine direction.
- PolicyEngine `snap_utility_allowance` is zero in all 32 AL benefit residuals.
- PolicyEngine `housing_cost` is positive in 30 of 32 AL benefit residuals.
- The remaining PE > Axiom cases are `ecps-51400` (Axiom ineligible/$0 vs PE
  eligible/$23.97) and `ecps-51859` (Axiom $828 vs PE $835.78, just over the
  $7 tolerance).

Interpretation:

The dominant AL benefit gap is still TANF income composition: PolicyEngine
computes Alabama TANF and includes it in SNAP unearned income; Axiom currently
does not compute or inject Alabama TANF into the SNAP income path. AL utility
amount wiring remains a real coverage gap, but it is not the observed current
driver in this ECPS run because PolicyEngine applies zero utility allowance in
all current AL benefit residuals.

## Tennessee

- Cases: 852
- Comparisons: 1,704
- Mismatch entries: 45
- SNAP benefit: 813 / 852 matched
- SNAP eligibility: 846 / 852 matched
- Benefit residuals: 39
- Eligibility residuals: 6
- Eligibility left-only: 6
- Eligibility right-only: 0
- Benefit residual direction: 39 Axiom > PolicyEngine, 0 PolicyEngine > Axiom

Current driver breakdown:

- 30 of 39 TN benefit residuals have positive PolicyEngine `tn_ff`.
- All 30 Families First/TANF-positive residuals are in the Axiom > PolicyEngine
  direction.
- PolicyEngine `snap_utility_allowance` is zero in all 39 TN benefit residuals.
- PolicyEngine `housing_cost` is positive in 36 of 39 TN benefit residuals.
- Six benefit residuals are paired with Axiom-eligible / PolicyEngine-ineligible
  eligibility mismatches.

Interpretation:

The dominant TN benefit gap is Families First/TANF income composition:
PolicyEngine computes Tennessee Families First and includes it in SNAP unearned
income; Axiom currently does not compute or inject Families First into the SNAP
income path. TN utility amount data exists in RuleSpec, but it is in a mixed
block with older income/allotment surfaces, so it should be split or re-encoded
through the encoder before being scoped into the composed program. It is not the
observed current driver in this ECPS run because PolicyEngine applies zero
utility allowance in all current TN benefit residuals.

## Next Work

1. Add TANF/Families First as real Axiom program surfaces, then wire payable
   cash assistance into SNAP unearned income through program composition.
2. Trace AL and TN Axiom-left-only eligibility cases before adding any uncovered
   eligibility-looking rules to `snap_eligible`.
3. Re-encode or split the TN utility table surface so utility amounts can be
   composed without importing stale SNAP income/allotment values.
4. Source and encode the AL FY 2026 utility amount table if an official source
   is available.
