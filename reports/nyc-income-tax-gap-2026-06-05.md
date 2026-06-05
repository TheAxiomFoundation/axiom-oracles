# NYC Income Tax Comparison Status

Date: 2026-06-05

## Status

NYC income tax is partially source-backed in Axiom, but it is not yet a full
`nyc_income_tax` alignment surface.

What is now encoded and valid:

- `rulespec-us-ny/statutes/NYC/11-1701.yaml`
  - source-backed NYC base resident income-tax rate tables;
  - encoder-applied with signed manifest;
  - live validation passes.
- `rulespec-us-ny/statutes/NYC/11-1704/1.yaml`
  - source-backed 14% additional tax on section 11-1701 tax for years before
    2027;
  - encoder-applied with signed manifest;
  - live validation passes.
- `rulespec-us-ny/statutes/NYC/11-1706.yaml`
  - source-backed city pass-through entity tax credit and overpayment treatment;
  - encoder-applied with signed manifest;
  - live validation and companion tests pass.
- `rulespec-us-ny/policies/tax/it-201-instructions/nyc-school-tax-credit-rate-reduction.yaml`
  - source-backed NYC school tax credit rate-reduction amount from IT-201-I
    page 21;
  - encoder-applied with signed manifest after overlay validation;
  - live validation and companion tests pass.
- `rulespec-us-ny/policies/tax/it-216-instructions/nyc-child-dependent-care-credit.yaml`
  - source-backed NYC child and dependent care credit worksheet slice from
    IT-216-I page 6;
  - encoder-applied with signed manifest after no-apply generation and
    resolver-correct overlay test validation;
  - live compile, validation, and companion tests pass.

What is still not full liability:

- NY taxable income / NY state income-tax base is not encoded through to
  `ny_taxable_income`;
- NYC nonrefundable credits are not encoded through final liability;
- NYC refundable credits are not encoded through final liability;
- the final resident/status selector is still deferred in the source artifact.
The encoded `11-1706` pass-through entity tax credit is not one of the ordinary
NYC credits currently driving PolicyEngine `nyc_income_tax` residuals.
The encoded school-tax rate-reduction and CDCC page-6 components are ordinary
NYC credit components, but they are not yet wired into final NYC liability.

New corpus source coverage added:

- `us-ny/form/tax/it-201-instructions`
- `us-ny/form/tax/it-215-instructions`
- `us-ny/form/tax/it-216-instructions`

The run snapshots three official New York State Department of Taxation and
Finance PDFs into `axiom-corpus` as
`2026-06-05-ny-tax-current-forms`, with 54 provision records and complete
coverage. These are source inputs for NYC household credit, school tax credit,
EITC, and CDCC work. The CDCC page-6 component and school-tax rate-reduction
component are now RuleSpec encodings; the rest remain source inputs only.

## PolicyEngine Surface

PolicyEngine's `nyc_income_tax`:

- gates on `in_nyc`;
- derives `nyc_taxable_income` from `ny_taxable_income`;
- applies the NYC filing-status rate table through
  `nyc_income_tax_before_credits`;
- subtracts nonrefundable credits, currently household credit and
  unincorporated-business credit;
- subtracts refundable credits, currently CDCC, EITC, and school-tax credit.

So the honest full comparison target is still bigger than the two encoded NYC
rate provisions.

## Diagnostic Comparison

I ran a diagnostic rate-table comparison over 40 NYC synthetic cases:

- PE was run case-by-case because the local PE batch runner currently loses the
  NYC county-derived `in_nyc` flag for this pinned PE build.
- PE supplied `nyc_taxable_income`.
- Axiom used that value only as `city_taxable_income` to test the encoded NYC
  rate schedule and additional-tax provisions.
- Axiom did not use PE's `nyc_income_tax` as an input.

Results:

- 40 cases tested.
- 33 cases had nonzero PE `nyc_income_tax_before_credits`.
- Max absolute Axiom-vs-PE difference: `$0.57`.
- Mean absolute difference: `$0.18`.
- All differences are under `$1`.

This is a diagnostic only. It proves the encoded 11-1701 + 11-1704.1 rate path
is structurally aligned with PE when both engines use the same city taxable
income. It does not prove full NYC income-tax liability alignment.

## Difference Driver

The sub-dollar differences are not a structural tax mismatch.

Axiom follows the NYC Admin Code rate table exactly as encoded by the source:
the higher brackets use statutory base-tax constants such as `$1,591` for
single/other residents over `$50,000`, then apply the encoded 14% additional
tax from section 11-1704.1.

PolicyEngine stores a combined marginal-rate table: each rate is multiplied by
114%, and the bracket carry-in amount is computed from the marginal rates and
thresholds. That avoids the statute's rounded base-tax constants.

Example from the diagnostic:

- Case: single adult, city taxable income `$52,000`.
- Axiom: `$1,891.26`.
- PolicyEngine: `$1,890.69`.
- Difference: `$0.57`.

The source of that `$0.57` is the statutory rounded base amount versus PE's
pure marginal-rate carry-in calculation.

## School Tax Credit Rate-Reduction Component Check

I also ran the newly encoded NYC school-tax credit rate-reduction component
against PolicyEngine's
`nyc_school_tax_credit_rate_reduction_amount` component on synthetic 2025
tax-unit cases. This is still a component diagnostic, not final
`nyc_income_tax`.

Inputs were shared source-level facts:

- `nyc_taxable_income`;
- filing-status table selection;
- NYC residence gate on the PolicyEngine side.

Results:

| Case | Axiom | PolicyEngine | Difference | Driver |
| --- | ---: | ---: | ---: | --- |
| Single, `$20,000` NYC taxable income | `$39.24` | `$38.76` | `$0.48` | Axiom uses source table base `$21`; PE computes marginal carry-in `$20.52`. |
| Joint, `$20,000` NYC taxable income | `$34.20` | `$34.20` | `$0.00` | Both are in the first band: `0.171%` of taxable income. |
| Head of household, `$20,000` NYC taxable income | `$37.768` | `$37.392` | `$0.376` | Axiom uses source table base `$25`; PE computes marginal carry-in `$24.624`. |
| Separate, `$20,000` NYC taxable income | `$39.24` | `$38.76` | `$0.48` | Same table as single. |
| Surviving spouse, `$20,000` NYC taxable income | `$34.20` | `$34.20` | `$0.00` | Same table as joint. |
| Joint, `$500,001` NYC taxable income | `$0.00` | `$0.00` | `$0.00` | Both apply the `$500,000` eligibility limit. |

This confirms the same source-vs-PE convention seen in the NYC rate-table
diagnostic: the Axiom encoding follows the form's rounded base amounts, while
PolicyEngine stores a marginal-rate table and derives the bracket carry-in
from rates and thresholds. I did not change Axiom to match PE's carry-in
convention because the rounded base amounts are explicit in the source form.

## Dashboard Component Comparison

I generated the dashboard report at
`dashboard/public/data/axiom-policyengine-nyc-income-tax-components.json`.
This is not a full Enhanced CPS run. It is an 11-case synthetic component
check because the current Axiom NYC stack does not yet derive the upstream
ECPS facts needed for final NYC liability: `ny_taxable_income`, the full NYC
credit stack, and final `nyc_income_tax`.

Results:

- 11 component comparisons.
- 8 matches.
- 3 mismatches.
- 0 engine errors.

Breakdown:

- NYC school tax credit rate-reduction amount: 3/6 matched.
- NYC child and dependent care credit, full-year slice: 5/5 matched.

All three mismatches are in the school-tax second band and have the same driver
as the rate-table diagnostic: Axiom follows the source-stated rounded base
amounts, while PolicyEngine derives the bracket carry-in from marginal rates
and thresholds. The dashboard report marks this as a source-vs-PE convention,
not a final-liability defect.

## Full NYC ECPS Diagnostic

I also ran a full NYC Enhanced CPS diagnostic over the NYC ECPS city dataset:

- dataset: `hf://policyengine/policyengine-us-data/cities/NYC.h5`;
- population: 137,915 NYC tax units;
- compared values: 275,830 component outputs;
- dashboard report:
  `dashboard/public/data/axiom-policyengine-nyc-income-tax-components-ecps.json`.

This is not an independent final-liability comparison. It uses PE/ECPS
upstream tax-unit projections, including `nyc_taxable_income` and `ny_cdcc`, as
Axiom inputs because those upstream NY/NYC facts are not yet encoded through
final `nyc_income_tax`.

Results:

- Overall: 194,633/275,830 matched, 81,197 mismatches.
- NYC school tax credit rate-reduction amount: 56,718/137,915 matched.
- NYC child and dependent care credit, full-year slice: 137,915/137,915
  matched.
- Stored mismatch examples: 1,000; aggregate counts use the full run.

All full-ECPS diagnostic mismatches are in the school-tax rate-reduction
component. The stored examples show the same small rounded-base convention
seen in the synthetic checks, usually about `$0.064`, `$0.376`, or `$0.48` per
affected tax unit. This confirms the drift is broad but not structural: Axiom
uses the source-stated rounded base amounts, while PolicyEngine derives
bracket carry-ins from marginal rates and thresholds.

School-tax diagnostic breakdown:

| Filing-status group | Band | Tax units | Matches | Mismatches |
| --- | ---: | ---: | ---: | ---: |
| Head of household | Zero/negative | 2,535 | 2,535 | 0 |
| Head of household | First band | 2,120 | 2,120 | 0 |
| Head of household | Second band | 6,953 | 0 | 6,953 |
| Head of household | Over limit | 200 | 200 | 0 |
| Joint/surviving spouse | Zero/negative | 8,818 | 8,818 | 0 |
| Joint/surviving spouse | First band | 3,470 | 3,470 | 0 |
| Joint/surviving spouse | Second band | 31,178 | 0 | 31,178 |
| Joint/surviving spouse | Over limit | 7,228 | 7,228 | 0 |
| Single/separate | Zero/negative | 21,350 | 21,350 | 0 |
| Single/separate | First band | 8,795 | 8,795 | 0 |
| Single/separate | Second band | 43,066 | 0 | 43,066 |
| Single/separate | Over limit | 2,202 | 2,202 | 0 |

The second-band mismatch count is exactly `6,953 + 31,178 + 43,066 =
81,197`, matching the full school-tax mismatch count. The base-amount
differences are:

- joint/surviving spouse: source `$37` vs PE carry-in `$36.936`, difference
  `$0.064`;
- head of household: source `$25` vs PE carry-in `$24.624`, difference
  `$0.376`;
- single/separate: source `$21` vs PE carry-in `$20.52`, difference `$0.48`.

PolicyEngine's own baseline tests acknowledge this convention by using a `$1`
absolute error margin on second-band school-tax cases because the printed
instruction amounts are rounded. With a `$1` convention tolerance, the encoded
school-tax component would effectively align over the full NYC ECPS diagnostic
population. I did not change the Axiom encoding to PE's carry-in convention,
because the source form explicitly states the rounded base amounts.

## Remaining Work

Next source-backed work, without PE-derived overrides:

1. Re-encode the NY taxable-income base, starting with `TAX/612` and the
   related NY Tax Law sections needed to expose `ny_taxable_income`.
2. Encode the remaining NYC credit stack from source-backed law and forms:
   household credit, unincorporated-business credit, EITC, and the remaining
   school-tax credit pieces. CDCC page 6 is landed, but final liability still
   needs composition and any upstream NY state CDCC inputs it references.
3. Add a final NYC composition only after the upstream legal inputs are
   source-backed.
4. Promote the dashboard from "current gap / diagnostic" to an alignment card
   only after full liability can run without using PE's own taxable-income or
   final-tax outputs as Axiom inputs.

Attempted ordinary-credit encoder steps:

- A rerun for
  `us-ny/form/tax/it-216-instructions/page-6` with logical source id
  `us-ny/form/tax/it-216-instructions/nyc-child-dependent-care-credit`
  produced a compile-clean, zero-ungrounded artifact. Its standalone generated
  test run failed only because the temporary output root was not named
  `rulespec-us-ny`, so legal IDs could not resolve. In a resolver-correct
  disposable overlay, the companion tests passed: 4 cases, 0 failures. I then
  installed it through the signed encoder apply helper. Live compile,
  validation, and companion tests pass.
- A retry no-apply encoder run for
  `us-ny/form/tax/it-215-instructions/page-3` with logical source id
  `us-ny/form/tax/it-215-instructions/nyc-earned-income-credit` compiled but
  failed CI and remained unapplyable. Metrics: compile=yes, ci=no, grounded=12,
  ungrounded=21, embedded_source=yes, generalist_review=7.5/10. The ungrounded
  values are still the flattened Worksheet C table thresholds and bounds,
  including `5000`, `7500`, `15000`, `17500`, `20000`, `22500`, `40000`, and
  `42500`. Nothing was applied.
- A no-apply encoder run for
  `us-ny/form/tax/it-201-instructions/page-21` with logical source id
  `us-ny/form/tax/it-201-instructions/nyc-school-tax-credit-rate-reduction`
  compiled and had no ungrounded values. Standalone validation could not resolve
  generated tests outside the policy repo, so I validated it through the
  encoder's policy-overlay path and then applied the already generated artifact
  through the signed encoder apply helper. Live validation passes.

Net: source coverage for ordinary NYC credits is now available, and the NYC
school-tax rate-reduction and CDCC page-6 components are landed. EITC is still
blocked by encoder/table-grounding issues. The next sustainable fix is
encoder/tooling work for form-backed policy targets and extracted table
grounding, not manual edits to match PolicyEngine.
