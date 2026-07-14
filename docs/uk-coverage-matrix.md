# UK coverage matrix — PolicyEngine-UK vs rulespec-uk vs axiom-oracles

Authoritative per-program coverage of the PolicyEngine-UK **simulated** policy
surface against the `rulespec-uk` **encoded** surface and the `axiom-oracles`
cross-engine **comparison** suites. This gates the UK encoding wave: a row's
status tells a worker whether the instrument is unencoded, encoded-but-not-yet
oracle-compared, or already live-compared to PolicyEngine.

This is the PolicyEngine-oracle analogue of `docs/be-coverage-matrix.md` (the
EUROMOD Belgium scoper).

## Provenance (facts from code/config, not memory)

- **PolicyEngine-UK facts** are read from the installed model at
  `/Users/maxghenis/PolicyEngine/policyengine-uk` (HEAD `45eb181c`), by grepping
  `policyengine_uk/variables/**/*.py` for `def formula` / `adds = [...]`, reading
  formula bodies, and querying the live `Microsimulation` tax-benefit system.
  The repo's self-reported `programs.yaml` registry was **not** used as ground
  truth (it drifts from code — e.g. it lists JSA/ESA as `complete` when the code
  comments say they are reported-ceiling models).
- **Fiscal aggregates** are computed from `Microsimulation()` on
  `enhanced_frs_2023_24` at 2026 (`.venv` at
  `~/PolicyEngine/policyengine-uk/.venv`). GBP figures below are program-level
  sums; recipient counts are weighted counts of nonzero records.
- **rulespec-uk** inventory is from `main` HEAD `91cecab2` (163 rule files, 162
  test companions; the one file without a test is `uksi/2013/376/23.yaml`, a
  structural `rules: []` stub). Output-concept classification is from
  `axiom_oracles.bridges.coverage.build_policyengine_coverage_report()`.
- **axiom-oracles** suites are `comparisons/uk-*.yaml` (HEAD `5025e92`);
  per-concept run status is read from
  `dashboard/public/data/axiom-policyengine-uk-{tax-benefits,universal-credit}-efrs.json`.

## Denominators

- **PolicyEngine-UK** simulates from `enhanced_frs_2023_24`. Its variable tree
  distinguishes four kinds, not two:
  1. **SIMULATED (rules)** — a `def formula` computes entitlement/liability from
     parameters and circumstances (income tax, NI 1/2/4, UC, Pension Credit,
     Housing Benefit, Child Benefit entitlement, WTC/CTC/IS entitlement,
     Tax-Free Childcare, Winter Fuel, Scottish payments, LBTT/LTT/SDLT, VAT,
     fuel duty, CGT).
  2. **SIMULATED (rate-from-input-category)** — a `def formula` applies a
     parameterised rate table, but the award *category/eligibility* is a frozen
     FRS input (`pip_dl_category`, `aa_category`, `dla_sc_category`, …). PIP,
     DLA, Attendance Allowance. Responds to *rate* reforms, **not** to
     *eligibility-rule* reforms.
  3. **PASSTHROUGH / reported-ceiling** — a `def formula` (or one-item `adds`)
     that reads a `*_reported` FRS amount and applies only a capital/tariff
     screen or a flat multiply, never computing the maximum from statute
     (`jsa_income`, `esa_income`, `sda`, `ssmg`, `maternity_allowance`,
     `incapacity_benefit`, `iidb`, `afcs`, `council_tax_benefit`,
     `state_pension` — pro-rated from `state_pension_reported`).
  4. **INPUT** — no formula; value straight from microdata (`council_tax`,
     `council_tax_band`, all `*_category` disability drivers, NHS/transport
     usage series).
- **Take-up modelling** happens in the *data pipeline* (`policyengine-uk-data`),
  not the formula layer: every `would_claim_*` gate is a stochastic draw baked
  into the dataset (defaults `True` in a standalone calculator). ~14 genuine
  program gates: UC, Pension Credit, Housing Benefit, WTC, CTC, IS, Child
  Benefit, Tax-Free Childcare, Scottish Child Payment, plus DfE grants. **No
  disability/carer benefit has a take-up gate.**
- **rulespec-uk** has **827 classified outputs**: **151 comparable**, **669
  known_not_comparable**, **7 unmapped** (the 7 are the just-landed
  savings/dividend pipeline + Data Protection Act outputs at HEAD `91cecab2`).
  The Kingston-upon-Thames sub-repo contributes 30 (all not_comparable local-CTR
  outputs). `not_comparable` is dominated by per-rate/per-band statutory helpers
  PE aggregates away (tax: 28; Regulation 100 Class-4-annual-maximum step/case
  intermediates) and program-wrapper boundary outputs that duplicate
  already-mapped parameter branches (UC: 12).
- **axiom-oracles** live-compares to PolicyEngine-UK through **two** suites
  (`uk-tax-benefits-efrs`, `uk-universal-credit-efrs`) on the same
  `enhanced_frs_2023_24` population at 2026, PE-UK `2.88.56` / core `3.26.11`.
  The six `uk-*-ukmod` suites target **UKMOD/EUROMOD, not PolicyEngine** —
  excluded from this matrix except as noted. The `uk-pe` **conformance
  universe** (`conformance/uk-pe.yaml`, #188) pins PolicyEngine-UK **2.89.2**;
  where a program's PE behaviour differs between the running-suite pin
  (2.88.56) and the universe pin (2.89.2) — notably Council Tax Reduction,
  present only from ≥2.89.2 — the row cites the 2.89.2 behaviour.

## Status legend

- **compared** — a final/aggregate PE-UK output is live-compared to the rulespec
  output in a running EFRS suite (in a dashboard JSON).
- **compared (rates/params)** — only the underlying rate *parameters* (or a
  tariff-income helper), not the final computed output, are compared.
- **encoded, not compared** — rulespec output exists and is `comparable`, but no
  running suite exercises it yet (often a deliberately-excluded "final wrapper"
  awaiting projection facts).
- **partial** — some sub-surface encoded/compared, large parts not.
- **NOT ENCODED** — no rulespec-uk output for the instrument.

## Matrix — one row per PolicyEngine-UK simulated program/surface

Ordered by 2026 fiscal weight (GBP bn, EFRS). `sim` = PE-UK simulation kind
(codes above). Suite cells cite the running EFRS suite; "—" = not in a running
PE suite.

| # | PE-UK program / surface | GBP bn (recip M) | sim | main PE-UK output var(s) | rulespec-uk status | suite (running today?) | gap → UK legal source family |
|---|---|---|---|---|---|---|---|
| 1 | **VAT** | 437 (32.1) | 1 | `vat` | partial — VAT Act 1994 ss.2/24/25/26 shell (rate + output/input/net) ENCODED; no rates/exemptions/threshold; firm-entity outputs `not_comparable` | — (no PE VAT oracle surface) | broaden → VATA 1994 Sch.7A–9 (reduced/zero/exempt), reg. thresholds |
| 2 | **Income tax (final)** | 314 (42.9) | 1 | `income_tax` | ENCODED end-to-end — ITA 2007 ss.6–35 + FA 2021/2023/2026; pilot pipelines to `uk_pit_/uk_svdv_income_tax_liability` | **compared** — `uk-tax-benefits-efrs` (`income_tax_liability`→`income_tax`, +`total_income`, `adjusted_net_income`, `personal_allowance`, all §10/§11D/§13 bands) | — (broaden: **Scottish/Welsh rates** — PE branches `earned_income_tax` via `pays_scottish_income_tax`, Axiom compares UK-branch only) |
| 3 | **National Insurance (incl. employer)** | 211 (33.0) | 1 | `total_national_insurance`; employee `national_insurance` £55bn | Class 1/2/4 ENCODED — SSCBA 1992 ss.1/8/15 + uksi/2001/1004 reg.10/100; 3 NIC pilot pipelines (employee, employer secondary, self-employed). **Class 3 NOT ENCODED** | **compared** — `uk-tax-benefits-efrs` (`national_insurance`, `ni_class_1_employee(_primary/_additional)`, `ni_class_4(_main/_maximum)`) | — (encode Class 3 voluntary → SSCBA 1992 s.13–14; broaden employer/secondary threshold provenance) |
| 4 | **State Pension** | 129 (11.9) | 3 | `state_pension` = `basic_state_pension`+`new_state_pension`+`additional_state_pension` | ENCODED (rates) — Pensions Act 2014 + Up-rating Order 2026 arts.4/6; `state-pension.yaml` → `state_pension_weekly_amount` | **encoded, not compared** — `state-pension-final` bridge surface **removed** (rulespec-uk 60501ec re-grounded `state-pension.yaml` to accrual basis); `additional_state_pension`+`state_pension` are `direct_variable`-mapped | build final suite; PE pro-rates a *reported* amount so structural (accrual-rule) reforms won't flow → Pensions Act 2014; SSCBA 1992 Pt II |
| 5 | **Universal Credit (final)** | 84 (6.4) | 1 | `universal_credit` (after `would_claim_uc` + benefit cap) | ENCODED deeply — WRA 2012 ss.1–27/40 + UC Regs 2013 (regs 22/24/26/27/29/34/36, Sch.4/5/10) + composed `uc_pilot_award_amount` pipeline (49 rules) | **compared** — `uk-universal-credit-efrs` runs 13 surfaces at 100% match: final award (`derived_expression`→`universal_credit`) + all elements as parameter rows + `uc_assessable_capital`/`uc_childcare_work_condition`/`uc_tariff_income`. The `universal-credit-final` (`would_claim`-inclusive) bridge surface was removed (rulespec retired in 829ab1a) | — (broaden: reg.90 MIF thresholds; sanction *amounts*; reconcile the two UC compose specs — `programs/uk/universal-credit/fy-2026-27.yaml` vs `universal_credit_composed_award_pipeline.yaml`) |
| 6 | **Council tax (gross)** | 62 (31.2) | 4 (INPUT) | `council_tax` (reported liability) | NOT ENCODED (the tax itself; no bands/valuation) | — | encode base liability → LGFA 1992 Pt I; band ratios |
| 7 | **Business rates** | 32 (26.0) | 1 | `business_rates` | NOT ENCODED | — | encode → LGFA 1988 Pt III; multiplier + reliefs |
| 8 | **PIP** | 29 (3.7) | 2 | `pip` = `pip_dl`+`pip_m` (category is frozen FRS input) | ENCODED (entitlement + rates) — WRA 2012 ss.77–79 + uksi/2013/377 reg.24 → `personal_independence_payment_weekly_amount` | **encoded, not compared** — `pip`/`pip_dl`/`pip_m`/`receives_enhanced_pip_dl` all `direct_variable`; **no PIP surface in either running suite** | build PIP suite (8 comparable outputs waiting) → WRA 2012 ss.77–79; uksi/2013/377 |
| 9 | **Capital gains tax** | 25 (1.3) | 1 | `capital_gains_tax` | NOT ENCODED | — | encode → TCGA 1992; FA rate schedule |
| 10 | **Fuel duty** | 24 (19.5) | 1 | `fuel_duty` | NOT ENCODED | — | encode → HODA 1979 rates |
| 11 | **Child Benefit** | 17 (8.4) | 1 | `child_benefit` (gross); `child_benefit_less_tax_charge` net £15bn | ENCODED (entitlement+rates) — SSCBA 1992 s.141 + uksi/2006/965 reg.2 (wrapper retired, atomic content survives) | **compared (rate+entitlement)** — `uk-tax-benefits-efrs` compares `child_benefit_respective_amount`+`child_benefit_entitlement` (weekly, pre-take-up). **Final `child_benefit` bridge surface removed** (`child-benefit-final`; rulespec retired in 829ab1a) | build final suite; **encode HITBC** (`CB_HITC`, £2.3bn, NOT ENCODED) → ITEPA/ITA HICBC (FA 2012 Sch.1) |
| 12 | **Housing Benefit** | 14 (1.5) | 1 | `housing_benefit` (after `would_claim_housing_benefit`) | **partial** — only capital tariff-income encoded (uksi/2006/213 reg.52 + 2006/214 reg.29); no applicable amount / max rent / taper / final award (wrapper retired) | **compared (tariff only)** — `uk-tax-benefits-efrs` compares `housing_benefit_tariff_income`; the applicable-amount + entitlement surfaces project PE's `housing_benefit_applicable_income` directly, so the earnings-disregard step is out of scope (#159/#165: PE stacks the base disregard on top of the £37.10 worker disregard — an unintended over-disregard vs SI 2006/213 Sch 4, ~63.5k benunits / ~£32M/yr on eFRS, filed PolicyEngine/policyengine-uk#1794). The `housing-benefit-final` bridge surface was removed (rulespec retired in 829ab1a) | encode applicable amount + LHA/max-rent + taper → HB Regs 2006 (uksi/2006/213 & /214), full |
| 13 | **Stamp Duty Land Tax** | 11 (0.5) | 1 | `stamp_duty_land_tax` | NOT ENCODED | — | encode → FA 2003 Pt 4 |
| 14 | **Attendance Allowance** | 9 (1.7) | 2 | `attendance_allowance` (category frozen FRS input) | **partial (rates)** — only 2026 rates (Up-rating Order Sch.1); no eligibility/final formula | **compared (rates)** — 2 AA rate params `parameter_value`; no final AA variable compared | encode eligibility + final → SSCBA 1992 s.64–67; build AA suite |
| 15 | **Student loan repayments** | 9 (5.9) | 1 | `student_loan_repayments` / `student_loan_repayment` | ENCODED end-to-end — plan thresholds+rates (GOV.UK-sourced) + outstanding-balance cap → `student_loan_repayments` | **compared** — `uk-tax-benefits-efrs` (`student_loan_repayment(_rate)`, `student_loan_repayments`) — **100% match** (the 43 near-end-of-loan mismatches resolved once the EFRS bridge fed `student_loan_balance` into the balance cap; rulespec-uk#77 + oracles#147) | — (upstream-source-checked against SI 2009/470) |
| 16 | **DLA** | 6 (1.0) | 2 | `dla` = `dla_sc`+`dla_m` (category frozen FRS input) | ENCODED (child DLA + rates) — GOV.UK + Up-rating Order art.14 → `disability_living_allowance_annual_amount` | **compared** — `uk-tax-benefits-efrs` (`disability-living-allowance-final`: `dla`/`dla_sc`/`dla_m` + care/mobility components) — 68 mismatches (weekly-rate edge cases) | — (distinguish adult legacy DLA; resolve mismatches) |
| 17 | **ESA (contributory)** | 6 (0.7) | 3 | `esa_contrib` (reported passthrough) | NOT ENCODED (contrib ESA) | — | (low priority; passthrough) → WRA 2007 Pt 1 |
| 18 | **Pension Credit** | 5 (1.3) | 1 | `pension_credit` = Guarantee + Savings (after `would_claim_pc`) | ENCODED (Guarantee close to end-to-end) — SPCA 2002 ss.1–3 + uksi/2002/1792 reg.6/15/Sch.IIA; **Savings Credit mechanics encoded (s.3) but not wired to final** | **compared (components)** — `uk-tax-benefits-efrs` compares `guarantee_credit`, `savings_credit`, `standard_minimum_guarantee`, severe-disab/carer/child additions, `pension_credit_deemed_income`, `is_SP_age`/`state_pension_age`. **Final `pension_credit` bridge surface removed** (`pension-credit-final`; rulespec re-grounded in 60501ec) | build final suite; wire Savings Credit → SPCA 2002 s.3; uksi/2002/1792 |
| 19 | **Carer's Allowance** | 5 (1.1) | 1 (hybrid) | `carers_allowance` (care-hours test OR reported fallback; zeroed in Scotland ≥2025) | ENCODED end-to-end — Up-rating Order Sch.1 + `carers-allowance.yaml` → `carers_allowance_annual_amount` | **compared** — `uk-tax-benefits-efrs` (`carers-allowance-final`) — **152 mismatches** (largest concept; Scotland/CSP-cutover + hours-vs-reported edge cases) | — (resolve mismatches: Scotland CSP replacement timing, hours threshold) |
| 20 | **Council Tax Benefit (legacy)** | 4 (4.6) | 3 (INPUT) | `council_tax_benefit` (abolished pre-2013 scheme, reported passthrough) | — (legacy scheme not the target) | — | see CTR row #29 |
| 21 | **Marriage allowance** | 3 (2.7) | 1 | `marriage_allowance` | NOT ENCODED | — | encode → ITA 2007 ss.55A–55E (transferable allowance) |
| 22 | **HITBC** | 2 (1.4) | 1 | `CB_HITC` | NOT ENCODED | — | encode → HICBC (FA 2012 Sch.1; ITEPA) — pairs with Child Benefit final |
| 23 | **ESA (income-related)** | 2 (0.2) | 3 | `esa_income` (reported-ceiling + tariff screen only) | **partial** — only capital tariff-income (uksi/2008/794 reg.118); no eligibility/components/final | **compared (tariff only)** — `esa_income`+`esa_income_tariff_income` `direct_variable`; the `esa-income-final` bridge surface was removed (rulespec retired in 829ab1a) | encode WRAG/support components + means test → ESA Regs 2008 |
| 24 | **Winter Fuel Allowance** | 2 (7.1) | 1 | `winter_fuel_allowance` (means-test toggle models 2024 PC-only restriction; zeroed in Scotland) | **partial (rates)** — 6 branch amounts (uksi/2025/969 reg.3); no eligibility gateway/final | **compared (rates)** — 3 WFA params `parameter_value`; 4 branch amounts `not_comparable`; no final WFA compared | encode eligibility + final → uksi/2000/729 & 2025/969; build WFA suite (Scotland PAWHP separate) |
| 25 | **AFCS / IIDB / incapacity** | 1–2 (0.1–0.2) | 3/4 | `afcs`, `iidb`, `incapacity_benefit` (pure reported passthroughs) | NOT ENCODED | — | (low priority; passthrough data) |
| 26 | **Scottish Child Payment** | 0.5 (0.4) | 1 | `scottish_child_payment` (after `would_claim_scp`) | ENCODED end-to-end — ssi/2020/351 reg.18/20 → `scottish_child_payment_annual_amount` | **compared** — `uk-tax-benefits-efrs` (`scottish-child-payment-final`) — 0 mismatches | — |
| 27 | **Tax-Free Childcare** | 0.4 (0.6) | 1 | `tax_free_childcare` (after `would_claim_tfc`) | **partial** — top-up rate + element + income ceiling (Childcare Payments Act 2014 ss.1/21 + uksi/2015/448 reg.15); no final cap/payment formula | **compared (params)** — 2 TFC params `parameter_value`; rate framing mismatch (`not_comparable`: statute 25% vs PE 20%) | encode final top-up + annual cap → Childcare Payments Act 2014; build TFC suite |
| 28 | **Carer Support Payment (Scotland)** | 0.4 (0.1) | 1 (hybrid) | `carer_support_payment` (Scotland CA replacement, ≥2025) | ENCODED end-to-end — ssi/2023/302 reg.5/16 → `carer_support_payment_annual_amount` | **compared** — `uk-tax-benefits-efrs` (`carer-support-payment-final`) — 12 mismatches | — (resolve mismatches) |
| 29 | **Council Tax Reduction (current)** | n/a (input-tested) | 1 (rules) | `council_tax_reduction` (household; = `council_tax_benefit` over benunit heads) — **now present in PE-UK ≥2.89.2** (#1769 national core + #1771 Kingston, both MERGED) | ENCODED — England pension-age (`council-tax-reduction.yaml`, SI 2012/2885 Sch.1) + Kingston working-age local scheme (`kingston…council-tax-reduction`, 19 rules) | **encoded, not compared** — `council_tax_reduction` is `direct_variable`-mapped (bridges/mappings/uk.yaml) to the now-present PE variable; no EFRS CTR surface in a running suite yet. Commensurable: PE's England-pensioner path (`england.council_tax_reduction.pensioners`: max_support 1, capital_limit £16,000, withdrawal 0.20) matches SI 2012/2885 penny-for-penny on a synthetic pension-age grid (verified, PE-UK 2.89.2). `council_tax` is a supplied input on **both** sides (PE `council_tax_reduction_maximum_eligible_liability` = `council_tax`; rulespec `council_tax_liability_for_year` input) | build EFRS `council-tax-reduction` surface projecting PE's applicable-amount/applicable-income/non-dep/`council_tax`/`savings` into the rulespec supplied inputs (the `uk_pension_credit` bridge pattern) → LGFA 1992 s.13A + Sch.1A; SI 2012/2885; council CTR schemes |
| 30 | **JSA (income) / IS / WTC / CTC** | 0.0 (migrated) | 1/3 | `jsa_income`, `income_support`, `working_tax_credit`, `child_tax_credit` | IS/JSA: only capital-tariff (uksi/1987/1967 reg.53; 1996/207 reg.116). WTC/CTC: only element rate tables (uksi/2002/2005 Sch.2; 2002/2007 reg.7; 2024/247) — no taper/final | **compared (tariff/rates only)** — `income_support_tariff_income`, `jsa_income_tariff_income` `direct_variable`; WTC/CTC element params `parameter_value` (incl. a documented £1,015-vs-£1,010.22 PE bug) | low fiscal priority (all £0 in 2026, UC migration); encode taper if needed → JSA Regs 1996 / IS Regs 1987 / WTC & CTC Regs 2002 |
| 31 | **LBTT (Scotland) / LTT (Wales)** | 0.2 / 0.1 | 1 | `land_and_buildings_transaction_tax`, `land_transaction_tax` | NOT ENCODED | — | encode → LTT(S)A 2013 / LTTA(W) 2017 |
| 32 | **SDA** | 0.05 (0.01) | 3 | `sda` (reported passthrough × max rate) | **partial (rate)** — basic+age rates (Up-rating Order Sch.1); wrapper retired | **compared (rate)** — `sda` `direct_variable` (single rate) + `not_comparable` age-band rows; the `severe-disablement-allowance-final` bridge surface was removed (rulespec retired in 829ab1a) | (closed legacy benefit; low priority) → SSCBA 1992 s.68 |
| 33 | **SSMG** | 0.01 (0.02) | 3 | `ssmg` (reported passthrough × rate) | **partial (rate)** — £500 amount only (uksi/2005/3061 reg.5) | **compared (rate)** — `gov.dwp.ssmg.rate` `parameter_value` | encode eligibility + final → uksi/2005/3061 |
| 34 | **TV Licence** | (cost) | 1 | `tv_licence`, `free_tv_licence_value` | **partial (fee only)** — £180 colour fee (uksi/2004/692 Sch.1); no over-75/concession | **compared (fee)** — `gov.dcms.bbc.tv_licence.colour` `parameter_value` | encode free-licence rules → uksi/2004/692 |

**PE-UK simulated but NOT tax/benefit policy** (data passthrough, excluded from
oracle scope): NHS in-kind spending (`nhs_spending` + visit/cost series, DHSC —
no formulas), rail/bus subsidy (DfT — only `rail_subsidy_spending` has a
formula), `domestic_rates` (NI). A fiscal analyst cannot simulate NHS/transport
policy reforms through these — they are imputation inputs.

**PE-UK NOT MODELLED at all** (no variable): Best Start Grant, Cold Weather
Payment, Funeral Expenses Payment, Statutory Sick/Maternity/Paternity Pay,
Bereavement Support Payment, Widowed Parent's Allowance, Discretionary Housing
Payments, Budgeting Loans, Blind Person's Allowance.

## rulespec-uk encoded with NO PolicyEngine-UK oracle counterpart

Real encoded surfaces that are non-fiscal or have no PE-UK simulation, so they
cannot be PE-compared: **Companies Act 2006 s.382** (small-company test),
**Data Protection Act 2018 s.157** (UK GDPR fine maxima), and **National Minimum
/ Living Wage** rate (uksi/2015/621) — belong in unit tests, not the PE matrix.

## Sanity-check vs the live dashboard

Two PE suites publish. `uk-tax-benefits-efrs`: **177,608 cases, 3,506,191
comparisons, 232 mismatches (99.9934% match)** across 51 concepts; mismatches
concentrate in Carer's Allowance (152), DLA (68), Carer Support Payment (12)
(the 43 student-loan mismatches resolved once the EFRS bridge fed
`student_loan_balance` into the balance cap; rulespec-uk#77 + oracles#147).
`uk-universal-credit-efrs`: **177,608 cases, 750,298
comparisons, 0 mismatches (100%)** across 26 concepts. Cross-referencing the 151
`comparable` rulespec outputs against the 77 running concept ids: **48 comparable
outputs are live-compared today**; **103 are encoded-and-comparable but not yet
in any running suite** (dominated by the 7 excluded "final wrapper" surfaces plus
PIP/state-pension/WFA/AA/TFC/CTC families). Nothing already-compared is marked
missing above.

The six `uk-*-ukmod` suites (+4 more found: dividend/savings/mixed income-tax,
UC) target **UKMOD/EUROMOD**, not PolicyEngine — synthetic 5-point grids, out of
scope here. `comparisons/parameter-oracles.yaml` has **zero UK entries**.

## Wave plan — gap workers grouped (PE var names + legal source families)

Ordered by 2026 fiscal/population weight. "Encode+compare" = write rulespec +
build/enable an EFRS suite; "compare-only" = rulespec exists, just build the
suite; "PE-blocked" = PolicyEngine-UK must add the variable first.

1. **Re-encode the 7 retired final wrappers, then rebuild their suites**
   (encode+compare — rulespec-uk retired the five wrapper .yamls in 829ab1a and
   re-grounded `state-pension`/`pension-credit` in 60501ec, so the matching
   `efrs_uk.py` surfaces were removed as dead code): `universal-credit-final`,
   `pension-credit-final`, `child-benefit-final`, `state-pension-final`,
   `housing-benefit-final`, `esa-income-final`,
   `severe-disablement-allowance-final`. PE vars: `universal_credit`,
   `pension_credit`, `child_benefit`, `state_pension`, `housing_benefit`,
   `esa_income`, `sda`. Still the biggest transfers, but blocked on upstream
   re-encoding (composed pipelines cover pre-take-up mechanics; the
   take-up/reported-ceiling wrappers need a deliberate re-encode), not on
   projection facts.

2. **PIP suite** (compare-only; £29bn, 3.7M) — 8 comparable outputs
   (`pip`/`pip_dl`/`pip_m`/`receives_enhanced_pip_dl`) waiting, zero suite. →
   WRA 2012 ss.77–79; uksi/2013/377. (Note PE treats award category as frozen
   input — rate reforms only.)

3. **HITBC + Child Benefit final together** (encode+compare; `CB_HITC` £2.3bn) —
   HITBC is NOT ENCODED; encode it to pair with the Child Benefit final wrapper.
   → FA 2012 Sch.1 (HICBC); SSCBA 1992 s.141.

4. **Housing Benefit full entitlement** (encode+compare; £14bn) — only tariff
   income encoded; encode applicable amount + LHA/max-rent + taper + final.
   `housing_benefit`. → HB Regs 2006 (uksi/2006/213 & /214), full.

5. **Scottish income tax branch** (encode+compare) — PE branches
   `earned_income_tax` to Scottish rates via `pays_scottish_income_tax`; Axiom
   compares UK-branch only. Encode Scottish (+Welsh) rate tables and add the
   Scottish comparison branch. → Scotland Act 2016; Welsh Rates (Wales Act 2014).

6. **Council Tax Reduction** (**unblocked** — build EFRS surface) — rulespec has
   CTR (England pension-age SI 2012/2885 + Kingston working-age); PE-UK gained a
   `council_tax_reduction` variable in **≥2.89.2** (#1769 national core + #1771
   Kingston, both MERGED), so the earlier PE-side block is resolved. The
   `england.council_tax_reduction.pensioners` path is parameter-identical to
   SI 2012/2885 (max_support 1, capital_limit £16,000, withdrawal 0.20) and
   matches the rulespec England pension-age award penny-for-penny on a synthetic
   grid (verified, PE-UK 2.89.2); it does **not** inherit the #1794 Housing
   Benefit earnings-disregard defect (CTR's `council_tax_reduction_applicable_income`
   applies no earnings disregard and never calls
   `housing_benefit_applicable_income_disregard`). Remaining work is the EFRS
   `council-tax-reduction` surface (bridging PE's applicable-amount/-income,
   non-dep deductions, `council_tax`, and `savings` into the rulespec supplied
   inputs) → LGFA 1992 s.13A + Sch.1A; SI 2012/2885.

7. **Attendance Allowance + Winter Fuel + Tax-Free Childcare finals**
   (encode+compare) — each has rate params compared but no eligibility/final
   formula encoded. `attendance_allowance`, `winter_fuel_allowance`,
   `tax_free_childcare`. → SSCBA 1992 s.64–67 (AA); uksi/2025/969 (WFA);
   Childcare Payments Act 2014 (TFC). WFA-Scotland (PAWHP) separate.

8. **Base indirect/property taxes** (encode+compare; large but static bases) —
   NOT ENCODED: VAT rate/exemption schedule (£437bn shell only), council tax
   base (£62bn), business rates (£32bn), CGT (£25bn), fuel duty (£24bn), SDLT
   (£11bn), LBTT/LTT. `vat`, `council_tax`, `business_rates`, `capital_gains_tax`,
   `fuel_duty`, `stamp_duty_land_tax`, `land_and_buildings_transaction_tax`,
   `land_transaction_tax`. → VATA 1994; LGFA 1992/1988; TCGA 1992; HODA 1979;
   FA 2003; LTT(S)A 2013 / LTTA(W) 2017.

9. **NI Class 3 + Marriage Allowance** (encode+compare; smaller) — both NOT
   ENCODED. `marriage_allowance` (£3bn). → SSCBA 1992 s.13–14; ITA 2007
   ss.55A–55E.

10. **Legacy benefit tapers (low priority — £0 in 2026 under UC migration)** —
    IS/JSA/ESA/WTC/CTC final entitlement (only tariff/rates encoded). Fix the
    documented WTC 30-hour element PE bug (£1,015 vs £1,010.22) in passing. →
    IS Regs 1987 / JSA Regs 1996 / ESA Regs 2008 / WTC & CTC Regs 2002.

## Council Tax Reduction — per-council reference (entitledto oracle)

Row 29 records CTR against the two *engine* oracles (PolicyEngine-UK, UKMOD),
both of which are **national** on the working-age side: PolicyEngine models the
three national schemes (England pension-age, Scotland, Wales) plus five named
English councils (Merton, Kingston upon Thames, Newham, Westminster, Oxford);
UKMOD models the country grain only. For every *other* English billing
authority's working-age scheme neither reproduces the local rules — PolicyEngine
falls back to the survey-reported benefit (`council_tax_benefit_reported`, i.e.
`0` on a constructed household). There are ~300 English billing authorities, so
this is a large blind spot the engine oracles structurally cannot close.

The `entitledto` recorded-fixture oracle
(`axiom_oracles/adapters/entitledto/`, suite `uk-ctr`, comparison
`uk-council-tax-reduction-entitledto`) closes it: entitledto models every
council's CTR scheme, so it is the most complete per-council reference (entitledto
publishes estimates, not authoritative awards). It is a *recorded*
oracle — entitledto's legal notices bar automated collection, so a human
captures each case once on the public calculator (`fixtures/uk_ctr/
CAPTURE-PROTOCOL.md`) and the runner replays the recorded response with
provenance; CI never probes it.

The eight-case grid demonstrates the gap at one income point: an identical single
private-renter earning £11,000 returns, on PolicyEngine-UK 2.89.2, **£0** in
Scotland (national scheme, tapered out because PolicyEngine counts the UC award
itself as CTR applicable income — applicable income £15,510 vs a £4,969 applicable
amount), **£1,181** in Kingston upon Thames (a supported local scheme), and **£0**
in Manchester (an unsupported council → reported fallback). entitledto returns the true award for
all three. How these slot into the coverage classifier: today a per-council CTR
output is `known_not_comparable`/`unmapped` against the PolicyEngine registry
(`bridges/mappings/uk.yaml`, axiom-oracles#78 / #278) because no PolicyEngine
variable models that council; once its entitledto fixtures are captured, the
council's CTR award becomes `comparable` against the entitledto oracle — a
per-council comparability the PolicyEngine-only classifier cannot express.
