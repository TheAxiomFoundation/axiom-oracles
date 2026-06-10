# Oracle Comparison Difference Overview — June 10, 2026

One-page map of every suite in the dashboard, where the differences lie, and
what causes them. The per-bucket detail lives in
`dashboard/public/data/known_causes.json`, which the dashboard renders inline
next to each disagreement count.

## Clean suites (zero mismatches)

| Suite | Scope | Compared values |
| --- | --- | ---: |
| ca-snap-ecps | California SNAP, 4,465 SPM units | 8,930 |
| ny-snap-ecps | New York SNAP, 2,306 SPM units | 4,612 |
| co-snap-ecps | Colorado SNAP, 730 SPM units | 1,460 |
| uk-universal-credit-efrs | UK Universal Credit, 177,608 people | 750,298 |
| co-health-thresholds | CO Medicaid/CHIP/BHP threshold parameters | 8 |
| co-tanf-coverage | Colorado Works TANF (coverage-only, no comparable PE output) | 0 |

## Suites with differences

| Suite | Mismatches / compared | Dominant cause | Owner |
| --- | ---: | --- | --- |
| nyc-income-tax-ecps-diagnostic | 81,197 / 275,830 | NYC school-tax second-band rounding convention | source-vs-PE convention |
| fiit-ecps | 172 / 299,993 | Joint-return SE-tax entity shape (EITC only) | rulespec-us |
| ma-snap-ecps | 107 / 1,792 | PE-imputed MA TAFDC + categorical/BBCE input gaps | rulespec-us-ma |
| sc-snap-ecps | 96 / 1,516 | PE-imputed SC TANF + minimum-benefit categorical gates | rulespec-us-sc |
| nc-snap-ecps | 52 / 2,732 | Small residuals; large ones are TANF-on-SSI; FPL table convention | rulespec-us-nc |
| uk-tax-benefits-efrs | 43 / 3,451,998 | Student-loan balance cap not yet encoded | rulespec-uk |
| tn-snap-ecps | 36 / 1,704 | PE-imputed TN Families First | rulespec-us-tn |
| al-snap-ecps | 28 / 1,408 | PE-imputed AL TANF + small edges | rulespec-us-al |
| nyc-synthetic (Axiom vs PE) | 12 / 5,691 | Legacy bridge taxable-income residuals, superseded by fiit-ecps | investigation |
| nyc-synthetic (PE vs TAXSIM) | 7 / 70 | NBER TAXSIM CTC/ODC/ACTC modeling gaps | upstream TAXSIM |
| co-state-income-tax-ecps | 6 / 926 | All six residuals are zero-weight rows; weighted match is 100% | investigation |
| nyc-income-tax-gap | 3 / 11 | Same school-tax rounding convention, synthetic check | source-vs-PE convention |

## The four recurring causes

Almost every difference above falls into one of four classes:

1. **PE-imputed state TANF in SNAP unearned income** (MA, AL, TN, SC, NC).
   PolicyEngine computes the state TANF/cash-assistance program and counts it
   in SNAP unearned income; Axiom projects only observed ECPS income facts and
   has no TANF fact to inject. This is the dominant benefit-amount driver in
   every SNAP state with residuals, and it also produces the
   Axiom-eligible/PE-ineligible edges where imputed TANF pushes PE just over
   the net-income limit. Fix path: compute or project state TANF into the
   composed SNAP income surface.

2. **Categorical/BBCE input coverage** (MA, SC). The categorical-eligibility
   rules are encoded and composed, but the TANF-service, authorization, and
   categorical income-standard facts they need are missing or source-unresolved
   in the ECPS projection, so Axiom denies where PE pays (often at the federal
   minimum benefit). In SC, PE additionally appears to apply a broader
   gross-FPG categorical path than the source's 130%-FPL FIIRS-tied standard.

3. **Source-rounding/table conventions** (NYC school tax, NC 200% limit).
   Axiom follows the literal source (rounded IT-201 second-band base amounts;
   FY 2026 monthly 100% FPL table × 2.00), PE derives values (unrounded
   carry-ins; annual FPG ratios). Differences are small ($0.06–$0.48 per NYC
   case) but affect many rows in the full diagnostic. These need a convention
   decision, not a bug fix.

4. **Entity-shape and formula-scope gaps awaiting re-encode** (federal EITC,
   UK student loans). Federal: 26 USC 1402(a)/(b), 164(f), and 32(c)(2) are
   still tax-unit-scoped where the statute speaks per individual, changing the
   OASDI cap interaction on joint returns — all 172 federal residuals. UK: the
   student-loan repayment rule lacks the outstanding-balance cap PE applies —
   all 43 UK residuals. Both stay visible deliberately rather than being
   aligned synthetically to PE output.

Remaining one-offs: six zero-weight CO tax units pending a component trace,
a handful of environment-sensitive minimum-benefit edges in AL (pinned vs
local PE runner disagree), and the legacy nyc-synthetic Axiom-vs-PE report
whose four taxable-income residuals predate the current fiit-ecps pipeline and
should be refreshed or retired.

## Hygiene applied to the explanation registry (this date)

- Removed five dead "Resolved in current run" entries (CA ×3, NY ×2) — those
  suites now have zero mismatches, so the entries never rendered.
- Added missing explanations for both nyc-synthetic reports (PE-vs-TAXSIM
  liability and CTC buckets; Axiom-vs-PE taxable-income chain), with an
  `engines` discriminator in `known_causes.json` and the dashboard lookup,
  since both reports share the `nyc-synthetic` suite slug.
- Rewrote every remaining entry cause-first with current run numbers; the
  registry now has exactly one entry per live mismatch bucket (verified
  against the dashboard data files) and no stale entries.
