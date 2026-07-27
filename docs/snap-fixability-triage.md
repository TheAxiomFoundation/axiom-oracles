# SNAP Fixability Triage

Current as of 2026-06-02, based on the committed full ECPS dashboard reports.
This is a work queue, not an attempt to force Axiom to match PolicyEngine.
TANF, TAFDC, and Families First residuals stay visible until those cash
assistance programs or source-backed case inputs are available.

## Summary

| State | Current result | Fixability | Next action |
| --- | ---: | --- | --- |
| CA | 0 benefit, 0 eligibility mismatches | Stable | Leave as regression guard. |
| NY | 0 benefit, 0 eligibility mismatches | Stable | Leave as regression guard. |
| CO | 0 benefit, 0 eligibility mismatches on encoder-backed run | Stable comparison; generic wrapper not yet dashboard path | Keep dashboard on encoder-backed run until the generic ECPS projection compares the same SNAP/SPM units and is clean. |
| NC | 40 benefit, 12 eligibility mismatches | Documented; no safe output patch | The 200% categorical path is wired as encoded: 100% FPL base times NC's 2.00 multiplier. Keep the FPG-basis residuals visible unless the source/encoder changes the controlling table. |
| SC | 61 benefit, 35 eligibility mismatches | Documented source/model divergence | Do not wire PE's broader categorical or SCCAP-style treatment until SC source facts are available. Current SC source has FIIRS at 130% FPL and SCCAP-Y needs living-arrangement/purchase-prepare facts ECPS does not expose. |
| AL | 24 benefit, 4 eligibility mismatches | Mostly documented; one categorical source question remains | Keep the weighted PE-only elderly/disabled minimum-benefit edge visible until a source-backed categorical approval path exists. Zero-weight Axiom-only edges are PE-counted unearned income gaps. |
| TN | 31 benefit, 5 eligibility mismatches | Blocked on Families First / unearned income coverage | Document and leave Families First/TANF-like income residuals visible. Current traced eligibility edges are income-input differences, not an extra state gate to wire. |
| MA | 65 benefit, 42 eligibility mismatches | Mostly blocked on TAFDC and missing categorical service facts | Do not synthesize categorical service or TAFDC facts from PE outputs. Add source-backed facts or the cash-assistance program first. |

## State Details

### NC

Current full ECPS alignment:

- Benefit: 1,326 / 1,366 matched; 40 mismatches.
- Eligibility: 1,354 / 1,366 matched; 12 PE-only eligibility mismatches.

Current non-TANF gaps:

- The 12 PE-only eligibility residuals are at the NC 200% categorical income
  edge; 11 have household weight 0. The one weighted case, `ecps-39817`, has
  Axiom gross income of $7,256.55/month against an encoded threshold of
  $3,596 * 2 = $7,192/month. PolicyEngine reports annual gross income
  $87,078.53 and FPG ratio 1.963, so PE accepts. The NC source says "200%
  maximum allowable gross income limit"; the wrapper aliases the base limit to
  the FY2026 monthly SNAP 100% FPL table and the encoded NC rule applies the
  2.00 multiplier. This is source-backed as currently encoded; changing it to
  PE's annual-FPG treatment would require an encoder/source decision, not a
  dashboard patch.
- Non-TANF benefit residuals are mostly small monthly-versus-annual
  periodization and deduction differences. Traced weighted cases
  `ecps-39711`, `ecps-40009`, and `ecps-39762` have zero PE utility allowance
  and zero Axiom utility allowance; the differences land in earned-income,
  standard, shelter, and net-income rounding after period conversion.
- Keep the shelter projection fix as-is. The case `RENT_PAID` fact now feeds
  both Axiom shelter costs and PE SNAP `housing_cost`.

Not fixable without new coverage:

- The two benefit residuals over $100 are TANF-on-SSI cases where PE adds
  `nc_tanf` / `tanf` to SNAP unearned income and Axiom has no source-backed
  TANF fact to project.
- Additional positive benefit residuals such as `ecps-40245` and `ecps-38982`
  have the same shape at smaller dollar amounts: PE counts more annual unearned
  cash income than Axiom can source from current NC ECPS inputs.

### SC

Current full ECPS alignment:

- Benefit: 697 / 758 matched; 61 mismatches.
- Eligibility: 723 / 758 matched; 29 PE-only and 6 Axiom-only eligibility
  mismatches.

Needs source review before code changes:

- The weighted PE-only minimum-benefit cases pass PE under a broader
  elderly/disabled categorical or SCCAP-style treatment than the encoded SC
  source currently supports. In traced cases such as `ecps-41409`,
  `ecps-40398`, and `ecps-40588`, Axiom computes a $24 minimum monthly
  allotment but returns `snap_eligible=false` because `snap_income_eligible`
  is false and no categorical flag is present.
- Tracing `household_has_snap_participation_basis_from_income_or_categorical_benefits`
  exposes missing source inputs, including a substantial-liquid-resources fact.
  This is not currently safe to paper over with a neutral default because it is
  part of the source's categorical/resource eligibility surface.
- The encoded SC source points to Family Independence Information and Referral
  Services with income at or below 130% FPL. Wiring PE's broader categorical
  path would be synthetic unless source review establishes it.
- SCCAP-Y is encoded, but it requires facts such as SSI-applicant status,
  living alone or purchasing/preparing separately, and shelter-low/high
  classification. ECPS does not expose enough source facts to project that path
  honestly for the full comparison.

Not fixable without new coverage:

- Large traced amount residuals are TANF income, not utility allowance. PE adds
  `sc_tanf` / `tanf`; traced high-dollar cases have PE utility allowance and
  excess shelter deduction at zero.
- Zero-weight Axiom-only eligibility examples such as `ecps-40402`,
  `ecps-40659`, and `ecps-129579` are income-input differences. Corrected
  pinned traces for `ecps-40402` and `ecps-40659` show PE adding SC TANF to
  SNAP unearned income and denying, while Axiom passes standard income on the
  current ECPS projection because no source-backed TANF fact is projected.

### AL

Current full ECPS alignment:

- Benefit: 680 / 704 matched; 24 mismatches.
- Eligibility: 700 / 704 matched; 3 Axiom-only and 1 PE-only eligibility
  mismatches.

Current non-TANF gaps:

- The weighted PE-only case `ecps-51400` is an elderly/disabled
  minimum-benefit edge. PE approves with a $23.97 normal allotment despite net
  income above 100% FPG. Axiom computes a $24 monthly allotment but returns
  `snap_eligible=false` because the income gate fails and categorical
  participation-basis inputs are not source-backed.
- The zero-weight Axiom-only cases `ecps-51544`, `ecps-51708`, and
  `ecps-52446` have split drivers. Corrected pinned traces show `ecps-51544`
  and `ecps-52446` are TANF income interactions: PE includes Alabama TANF in
  SNAP unearned income while Axiom does not project TANF. `ecps-51708` is not
  TANF-driven; PE reports TANF and utility allowance at zero and net income
  around 41.3% FPG, so it remains a zero-weight PE disqualification or
  categorical-source edge.

Not fixable without new coverage:

- Most amount residuals are PE TANF-in-SNAP-income cases.
- The state utility amount table remains a real modeling gap, but current AL
  traces do not show it as the observed driver.

### TN

Current full ECPS alignment:

- Benefit: 821 / 852 matched; 31 mismatches.
- Eligibility: 847 / 852 matched; 5 Axiom-only eligibility mismatches.

Current non-TANF gaps:

- Traced Axiom-only eligibility residuals, including weighted case
  `ecps-49447`, pass Axiom's standard income gates because Axiom sees lower
  unearned income. Corrected pinned traces show PE Families First/TANF in all
  five eligibility residuals; PE pushes net income above roughly 103.6%-108.2%
  FPG and denies. `ecps-49447` is the only weighted eligibility residual.
- Compose still reports eligibility-looking rules outside `snap_eligible`, but
  the current traced residuals do not justify adding those gates mechanically.
  The observed driver is income-input coverage.

Not fixable without new coverage:

- The dominant residual is PE Families First / TANF income in SNAP unearned
  income. Axiom should not project that synthetically.
- The utility amount table is encoded in an unsafe mixed block and still needs
  an encoder split, but current traced TN residuals have PE utility allowance
  at zero.
- The one PE-greater-than-Axiom amount edge, `ecps-50388`, is not Families
  First-driven: corrected pinned trace has PE `tn_ff` and `tanf` at $0, utility
  allowance at $0, gross income around 154.6% FPG, and net income around 53.3%
  FPG.

### MA

Current full ECPS alignment:

- Benefit: 831 / 896 matched; 65 mismatches.
- Eligibility: 854 / 896 matched; 39 PE-only and 3 Axiom-only eligibility
  mismatches.

Fixable only after new facts or program coverage:

- HCSUA and categorical/standard income rollups are wired.
- Remaining PE-only cases need source-backed MA assistance/service facts in the
  ECPS projection or the relevant TAFDC/TANF program modeled.

## CO Wrapper Status

The CO encoder-backed dashboard comparison is clean. The generic
`axiom-programs/us-co/snap/fy-2026.yaml` wrapper now compiles and has a
source-backed generic adapter path for:

- `us:programs/snap#benefit`
- `us:programs/snap#eligible`

What changed:

- Compiled-artifact output aliasing maps the local dashboard output
  `snap_eligible` to the unique qualified CO legal output ID.
- Generic ECPS input projection now supplies CO's basic/expanded categorical
  inputs as the same non-categorical baseline used by the CO source fixture and
  legacy CO adapter, because ECPS does not expose those service facts.
- Generic input dtype inference now treats `if` conditions as judgments,
  preserves numeric dtype for `then`/`else` branches, and treats division
  operands as numeric.
- Optional branch denominators that ECPS does not measure directly use neutral
  nonzero defaults, including self-employment period months and related
  proration/count/rate inputs.

Smoke status: generic CO SNAP passed a 1,000-record prefilter smoke run
(10 CO households, 20 comparisons, 0 mismatches). A full generic run now
executes without engine errors after dtype/denominator projection fixes, but it
is not clean: 694 CO households, 1,388 comparisons, 276 mismatches. The
encoder-backed dashboard path projects 730 CO ECPS SNAP/SPM units and remains
clean, so the dashboard should not switch until the generic projection compares
the same benefit units and closes the remaining policy/input gaps.
