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
| NC | 40 benefit, 12 eligibility mismatches | Mostly documented; one source/encoder question remains | Review NC's 200% categorical income source alias before changing threshold math. Keep cash-assistance income residuals visible until WFFA/TANF coverage exists. |
| SC | 61 benefit, 35 eligibility mismatches | Needs source review | Do not wire PE's broader categorical treatment until the SC source establishes it. Current source evidence points to a 130% Family Independence service path, not broad BBCE. |
| AL | 24 benefit, 4 eligibility mismatches | Mostly blocked on TANF / targeted gates | Document and leave TANF residuals visible. Investigate the remaining PE-only income/categorical case and Axiom-only disqualification/threshold cases separately. |
| TN | 31 benefit, 5 eligibility mismatches | Mostly blocked on Families First / targeted gates | Document and leave Families First residuals visible. Review uncovered eligibility-looking gates before adding any to `snap_eligible`. |
| MA | 65 benefit, 42 eligibility mismatches | Mostly blocked on TAFDC and missing categorical service facts | Do not synthesize categorical service or TAFDC facts from PE outputs. Add source-backed facts or the cash-assistance program first. |

## State Details

### NC

Current full ECPS alignment:

- Benefit: 1,326 / 1,366 matched; 40 mismatches.
- Eligibility: 1,354 / 1,366 matched; 12 PE-only eligibility mismatches.

Current non-TANF gaps:

- The 12 PE-only eligibility residuals are at the NC 200% categorical income
  edge. Traced cases such as `ecps-39817` and `ecps-128370` show PE accepting
  the household through gross-FPG/categorical treatment while Axiom rejects on
  the composed NC income gate. The NC source says "200% maximum allowable gross
  income limit"; the wrapper currently aliases the base limit to the FY2026
  monthly SNAP income table. A source/encoder review is needed before changing
  this to PE's annual-FPG treatment.
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

- The weighted PE-only minimum-benefit cases appear to pass PE under a broader
  categorical treatment than the encoded SC source currently supports.
- The encoded SC source points to Family Independence Information and Referral
  Services with income at or below 130% FPL. Wiring a broader gross-FPG
  categorical path would be synthetic unless source review establishes it.

Not fixable without new coverage:

- Large traced amount residuals are TANF income, not utility allowance. PE adds
  `sc_tanf` / `tanf`; traced high-dollar cases have PE utility allowance and
  excess shelter deduction at zero.

### AL

Current full ECPS alignment:

- Benefit: 680 / 704 matched; 24 mismatches.
- Eligibility: 700 / 704 matched; 3 Axiom-only and 1 PE-only eligibility
  mismatches.

Fixable only after targeted review:

- The PE-only case is an income/categorical edge.
- The Axiom-only cases need a disqualification or state eligibility-gate trace
  before any additional gate is wired.

Not fixable without new coverage:

- Most amount residuals are PE TANF-in-SNAP-income cases.
- The state utility amount table remains a real modeling gap, but current AL
  traces do not show it as the observed driver.

### TN

Current full ECPS alignment:

- Benefit: 821 / 852 matched; 31 mismatches.
- Eligibility: 847 / 852 matched; 5 Axiom-only eligibility mismatches.

Fixable only after targeted review:

- Compose reports eligibility-looking rules outside `snap_eligible`, but those
  should not be added mechanically. Each gate needs a source-backed trace.

Not fixable without new coverage:

- The dominant residual is PE Families First / TANF income in SNAP unearned
  income. Axiom should not project that synthetically.

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

- `us:statutes/7/2014/u#snap_benefit`
- `us:statutes/7/2014/o#snap_eligible`

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
