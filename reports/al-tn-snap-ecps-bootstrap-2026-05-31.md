# AL/TN SNAP ECPS Bootstrap - 2026-05-31

## Scope

This adds first-pass composed SNAP programs for Alabama and Tennessee and runs
full Enhanced CPS state slices against PolicyEngine. No Python overrides were
added to align amounts.

## Compose and Compile

Both AL and TN now exist as `axiom-programs` specs in the same layout as the
other state SNAP programs:

- `axiom-programs/us-al/snap/fy-2026.yaml`
- `axiom-programs/us-tn/snap/fy-2026.yaml`

The dashboard comparison configs now declare both the source compose spec and
the compiled artifact target. `scripts/run_comparison.py` composes and compiles
the program before running the comparison, so dashboard regeneration no longer
depends on a hidden manual `/tmp` setup step. The equivalent commands are:

```bash
/Users/pavelmakarchuk/axiom-compose/.venv/bin/axiom-compose \
  /Users/pavelmakarchuk/axiom-programs/us-al/snap/fy-2026.yaml \
  --rulespec-root /Users/pavelmakarchuk/rulespec-us \
  --rulespec-root /Users/pavelmakarchuk/rulespec-us-al \
  -o /tmp/al-snap-composed.yaml

AXIOM_RULESPEC_REPO_ROOTS=/Users/pavelmakarchuk \
  /Users/pavelmakarchuk/axiom-rules-engine/target/release/axiom-rules-engine \
  compile --program /tmp/al-snap-composed.yaml \
  --output /tmp/al-snap-compiled.json

/Users/pavelmakarchuk/axiom-compose/.venv/bin/axiom-compose \
  /Users/pavelmakarchuk/axiom-programs/us-tn/snap/fy-2026.yaml \
  --rulespec-root /Users/pavelmakarchuk/rulespec-us \
  --rulespec-root /Users/pavelmakarchuk/rulespec-us-tn \
  -o /tmp/tn-snap-composed.yaml

AXIOM_RULESPEC_REPO_ROOTS=/Users/pavelmakarchuk \
  /Users/pavelmakarchuk/axiom-rules-engine/target/release/axiom-rules-engine \
  compile --program /tmp/tn-snap-composed.yaml \
  --output /tmp/tn-snap-compiled.json
```

Last verified on 2026-05-31:

- AL compiled successfully with 245 derived outputs.
- TN compiled successfully with 515 derived outputs.

## Alabama

- Program: `axiom-programs/us-al/snap/fy-2026.yaml`
- RuleSpec roots: `rulespec-us`, `rulespec-us-al`
- Composed artifact: `/tmp/al-snap-composed.yaml`
- Compiled artifact: `/tmp/al-snap-compiled.json`
- Derived outputs: 245
- ECPS cases: 704
- Comparisons: 1,408
- Matches: 1,367
- Mismatch entries: 41
- Weighted match rate: 95.401081%
- Benefit: 667 / 704 matched
- Eligibility: 700 / 704 matched

AL mismatch buckets:

| Bucket | Count |
| --- | ---: |
| Benefit amount mismatches | 37 |
| Eligibility mismatches | 4 |
| Eligibility left-only | 3 |
| Eligibility right-only | 1 |
| Benefit mismatches paired with eligibility mismatch | 4 |
| Benefit-only mismatches | 33 |
| Axiom benefit greater than PE | 30 |
| PE benefit greater than Axiom | 7 |

Current AL drivers:

- The first-pass program composes a broad AL Food Assistance policy scope, but
  `snap_benefit` still uses the federal benefit chain plus generic ECPS income
  and shelter projection.
- The dominant benefit residual direction is now traced to TANF. PolicyEngine
  computes Alabama TANF and includes it in SNAP unearned income; Axiom does not
  yet compute or inject Alabama TANF into the composed SNAP income path.
- Of the 37 AL benefit residuals, 30 have Axiom greater than PolicyEngine. Of
  those 30, 21 have positive PE Alabama TANF. None of the seven PE-greater-than-
  Axiom benefit residuals had positive PE TANF in the diagnostic run.
- Examples:
  - `ecps-51206` / county `01011`: Axiom `$785` vs PE `$749.27`; PE
    `al_tanf` and `snap_unearned_income` are both `$4,128/year`.
  - `ecps-51544` / county `01117`: Axiom `$62` and eligible vs PE `$0` and
    ineligible; PE `al_tanf` is `$3,648/year`.
  - `ecps-52446` / county `01087`: Axiom `$403` and eligible vs PE `$0` and
    ineligible; PE `al_tanf` is about `$5,284.59/year`.
- The PE-greater-than-Axiom cases include minimum-benefit/eligibility edges. For
  example, `ecps-51307` / county `01121` is Axiom `$0` and ineligible while PE
  is eligible with `$23.97/month`.
- No AL-specific standard utility allowance amount table is wired yet. AL POE
  903 encodes SUA/BUA/telephone eligibility mechanics, but the local RuleSpec
  surface does not yet contain an executable FY 2026 utility amount table. This
  is a real coverage gap, but it is not the observed driver in this run: PE
  applied zero `snap_utility_allowance` in all 37 AL benefit-mismatch cases
  while 33 of those cases had positive housing costs.
- Compose reports eligibility-looking AL rules outside `snap_eligible`, including
  `household_meets_snap_income_eligibility_standards`,
  `person_eligible_under_abawd_provision`, and `person_is_eligible_alien`.
  These should be traced before being wired into the gate.

## Tennessee

- Program: `axiom-programs/us-tn/snap/fy-2026.yaml`
- RuleSpec roots: `rulespec-us`, `rulespec-us-tn`
- Composed artifact: `/tmp/tn-snap-composed.yaml`
- Compiled artifact: `/tmp/tn-snap-compiled.json`
- Derived outputs: 515
- ECPS cases: 852
- Comparisons: 1,704
- Matches: 1,650
- Mismatch entries: 54
- Weighted match rate: 93.690369%
- Benefit: 804 / 852 matched
- Eligibility: 846 / 852 matched

TN mismatch buckets:

| Bucket | Count |
| --- | ---: |
| Benefit amount mismatches | 48 |
| Eligibility mismatches | 6 |
| Eligibility left-only | 6 |
| Eligibility right-only | 0 |
| Benefit mismatches paired with eligibility mismatch | 5 |
| Benefit-only mismatches | 43 |
| Axiom benefit greater than PE | 38 |
| PE benefit greater than Axiom | 10 |

Current TN drivers:

- The first-pass TN program composes a large DHS SNAP policy scope. One narrower
  duplicate page, `policies/dhs/snap/24-08/page-2`, was excluded because it
  exports `excluded_household_member`, which collides with the broader
  `policies/dhs/snap/24-07/page-3` export.
- The dominant benefit residual direction is now traced to Tennessee Families
  First/TANF. PolicyEngine computes `tn_ff`/`tanf` and includes it in SNAP
  unearned income; Axiom does not yet compute or inject Families First into the
  composed SNAP income path.
- Of the 48 TN benefit residuals, 38 have Axiom greater than PolicyEngine. Of
  those 38, 30 have positive PE Families First/TANF. None of the ten
  PE-greater-than-Axiom benefit residuals had positive PE TANF in the diagnostic
  run.
- Examples:
  - `ecps-49363` / county `47157`: Axiom `$909` vs PE `$733.70`; PE `tn_ff`
    and `snap_unearned_income` are both `$5,652/year`.
  - `ecps-49447` / county `47093`: Axiom `$308` and eligible vs PE `$0` and
    ineligible; PE `tn_ff` is `$5,652/year`.
  - `ecps-49860` / county `47047`: Axiom `$61` and eligible vs PE `$0` and
    ineligible; PE `tn_ff` is `$4,116/year`.
- The PE-greater-than-Axiom cases include minimum-benefit/eligibility edges. For
  example, `ecps-49546` and `ecps-49795` in county `47037` are Axiom `$0` while
  PE is eligible with `$23.97/month`.
- TN-specific utility amount data is present in RuleSpec but not safely scoped.
  `rulespec-us-tn/regulations/1240-01/04/27/block-1.yaml` exports
  `snap_standard_utility_allowance`, `snap_basic_utility_allowance`,
  `snap_telephone_standard`, and `snap_homeless_shelter_standard`. The same
  block also exports older SNAP income standards, max allotment, standard
  deduction, and shelter cap values with broad effective dates, so the current
  TN program deliberately does not include it wholesale. The sustainable fix is
  to re-encode or split the utility amount surface through the encoder, then
  compose only the utility allowances into shelter costs. This is a real
  coverage gap, but it is not the observed driver in this run: PE applied zero
  `snap_utility_allowance` in all 48 TN benefit-mismatch cases while 44 of those
  cases had positive housing costs.
- Compose reports eligibility-looking TN rules outside `snap_eligible`, including
  `income_eligibility_standards_met`,
  `ineligible_household_member_due_to_enumeration`,
  `individual_transitional_snap_eligible`, and `bua_eligible`.

## Source Notes

- USDA FNS explains that SNAP utility allowances are used in total shelter
  costs and may be used in place of actual utility costs; FNS also notes that
  Tennessee SUAs vary by household size.
- Tennessee's public SNAP eligibility page describes the shelter/utility
  deduction as part of SNAP deductions.
- PolicyEngine has executable AL TANF variables (`al_tanf`) and TN Families
  First variables (`tn_ff`). The current Axiom SNAP composed programs do not yet
  include those cash-assistance programs as income inputs to SNAP.

## Next Work

1. Add TANF/Families First as real program surfaces, then wire their payable
   cash assistance into SNAP unearned income. This should be encoded/programmed
   as policy, not injected as an oracle override.
2. Re-encode or split TN `regulations/1240-01/04/27/block-1` so the utility
   amount tables can be scoped without also importing stale income/allotment
   values.
3. Source and encode the AL FY 2026 utility amount table if an official amount
   source can be located.
4. Resolve TN's duplicate `excluded_household_member` RuleSpec surface through
   encoder/concept consolidation before adding the narrower SSN page back to
   program scope.
5. Only wire uncovered eligibility-looking rules into `snap_eligible` after
   per-case tracing confirms they are top-level gates rather than administrative
   verification, expedited-service, or alternative eligibility concepts.
