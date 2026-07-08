# US coverage wave 1 — federal lane — progress

Branch: `us-federal-repealed-exclusions`. Goal: close uncovered FEDERAL rows in the
`us-pe` conformance universe (the 30 federal/national rows that are not `*_income_tax`
and not state-TANF). Validation year 2026; oracle `policyengine-us` (universe label
1.767.3, fiit-ecps population pin 1.729.0).

Federal covered at start = the 12 fiit-ecps rows + ssi + snap + medicaid-magi-co.
30 federal/national rows were in-scope uncovered.

## Scoreboard
- Start: us-pe in_scope 140, covered 27 (19.29%), excluded 8.
- After this branch: **in_scope 137, covered 27 (19.71%), excluded 11**
  (`oracle_models_repealed_law: 3` added). Blocking list 113 → 110.

## Closed this branch — EXCLUDE (3, evidence-backed `oracle_models_repealed_law`)
PolicyEngine-US runs each formula (`switch=on`) but a lapsed parameter gates it to $0
for every 2026 synthetic case — no current-law surface for Axiom to compare. Probe:
`scripts/probe_us_repealed_federal.py` (PE-US 1.767.3, all_zero=True).
- **acp** — Affordable Connectivity Program (47 USC 1752; IIJA 2021 §60502); new
  enrollments stopped 2024-02-07, last partial benefit May 2024. `gov.fcc.acp.amount`=0
  at 2026; acp=$0 even with `is_acp_eligible` forced + broadband_cost 2400.
- **ebb** — Emergency Broadband Benefit (CAA 2021; 47 USC 1752 note); transitioned to
  ACP 2021-12-31. `gov.fcc.ebb.amount`=0 at 2026; ebb=$0 under maximal activation.
- **recovery_rebate_credit** — IRC 6428/6428A/6428B economic impact payments, 2020-2021
  tax years only. `rrc_cares`+`rrc_caa`+`rrc_arpa` each $0 at 2026.

## Remaining 27 federal rows — honest disposition (ENCODE-THEN-COVER worklist)
Mechanics checked, not pattern-matched. rulespec-us `programs/us/fiit/fy-2026.yaml`
explicitly states taxable-income assembly (IRC 61-63) is **not yet encoded** (taxable
income is a runtime input) and its outputs are `acknowledged_incomplete`. The
fiit-ecps `#nonrefundable_credits` concept matches PE only as an **aggregate**; the
individual credits below are not independently encoded/surfaced. So none of these are
"already covered" — all need encode work before a suite. Probe values are 2026 PE-US.

Federal income-tax assembly (IRC 61-63 not encoded):
- taxable_income, itemized_taxable_income_deductions, salt_deduction (IRC 164),
  qualified_business_income_deduction (IRC 199A) — probe live (QBI 13.5k, SALT 31.5k).

Individual nonrefundable credits (roll into fiit aggregate, not surfaced/encoded):
- savers_credit (25B), lifetime_learning_credit (25A(c)), elderly_disabled_credit (22),
  foreign_tax_credit (27/901). Each needs an activating input + per-credit encode.

Surtaxes (outside fiit scope 1(j)/24/26/32/55; payroll only OASDI+Medicare, not these):
- self_employment_tax (1401/1402, probe 33.6k), additional_medicare_tax (3101(b)(2),
  probe 7.2k), net_investment_income_tax (1411, probe 26.6k) — clean statutory
  arithmetic; strong per-case-grid candidates once encoded.

AMT — `alternative_minimum_tax` IS a fiit output but `acknowledged_incomplete`
(statutes/26/55 + rev-proc-2025-32). Needs completion + an AMT-triggering grid
(post-TCJA AMT rarely binds for wage earners; $0 across a plain wage sweep).

Energy/vehicle credits (IRA, not encoded): energy_efficient_home_improvement_credit
(25C), residential_clean_energy_credit (25D), new_clean_vehicle_credit (30D),
used_clean_vehicle_credit (25E), high_efficiency_electric_home_rebate (IRA §50122;
live in 2026, `elements` non-empty — NOT a repealed-law exclusion),
residential_efficiency_electrification_rebate (IRA §50121; input-carried retrofit
expenditures).

ACA PTC — `aca_ptc` (IRC 36B). rev-proc-2025-25 applicable-percentage table is encoded
(`us/policies/irs/rev-proc-2025-25/aca-ptc.yaml`), but the full 36B surface (SLCSP
benchmark, contribution) is not. xref-heavy → defer per encode#1058; corpus#108 pattern.

Health/benefit surfaces (not encoded in rulespec-us; real live surfaces — probe non-$0
where household activates): chip, commodity_supplemental_food_program (1.2k),
wic, head_start, early_head_start, free_school_meals (3.4k), reduced_price_school_meals,
spm_unit_capped_housing_subsidy (Section 8 HAP — computed, needs FMR/takeup inputs).

## Notes
- This branch also refreshes two pre-existing STALE generated artifacts that block CI
  independent of federal work: `conformance/detail/uk-pe.json` (a uk-pe report gained a
  `dispositioned` block; detail was never regenerated — deterministic, content-based)
  and `conformance_burndown.json` (missing all 2026-07-08 points that committed history
  snapshots already carry). Both are deterministic regenerations, no semantic decisions.
- Verified locally (Python 3.14, uv.lock): ruff, run_comparison --list,
  check_rule_verification, apply_dispositions/extract_grids/affected_map/vacuous-gate/
  universe --check, scoreboard/ratchet/burndown --check, pytest (1253 passed/12 skipped),
  uv build — all pass.
