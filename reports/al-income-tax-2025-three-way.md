# Alabama TY2025 three-way lane

1,155 eCPS households, taxsimid 88052–89206. Final liability: `siitax`.

| PE versus TAXSIM absolute gap | Households |
|---|---:|
| abs(PE-TAXSIM) <= 1 | 681 |
| 1 < abs(PE-TAXSIM) <= 15 | 76 |
| abs(PE-TAXSIM) > 15 | 398 |

Tolerance is $1 absolute, relative zero; $1–$15 is a diagnostic band.

Axiom federal feeds are one implementation, not independent votes.

- pe_federal: **pending_module** — Alabama TY2025 composed module is absent; encoding awaits source signing (decision d270; pending narrow union axiom-corpus#746). (`us-al/policies/income_tax/2025_resident_liability.yaml`).
- taxsim_federal: **pending_module** — Alabama TY2025 composed module is absent; encoding awaits source signing (decision d270; pending narrow union axiom-corpus#746). (`us-al/policies/income_tax/2025_resident_liability.yaml`).

Component attribution is observational, not legal adjudication. Multiple component differences may coexist.

| Band | First observed difference (households) |
|---|---|
| within_1 | no_component_gap_over_1: 454, agi: 123, deductions: 52, taxable_income: 28, exemptions: 24 |
| over_1_through_15 | exemptions: 34, taxable_income: 29, deductions: 13 |
| over_15 | taxable_income: 231, agi: 76, exemptions: 64, deductions: 27 |

TAXSIM `max(v34,v35)` is an `observed_behavior_fit`; its unallocated taxable-income reduction is not an identified federal deduction. Zero taxable income censors decomposition.

PE component replay differs from saved release amounts by at most $4 AGI, $8 taxable income and $0.50 liability; both representations are retained.

Federal crosswalks preserve unavailable Form 1040 line 22 and other unreported worksheet amounts. `fiitax` is never substituted for line 22.

With these saved references, module availability enables compilation, but both feeds also need verified line 22, refundable AOTC, refundable adoption and Schedule 3 line 13a amounts before evaluation. A refreshed manifest may supply these as named form-line columns plus `<field>_status=verified_form_line` in each engine release.

Per-household component table: [al-income-tax-2025-three-way-components.csv](al-income-tax-2025-three-way-components.csv). Full provenance and crosswalks are in the JSON report.

Ground-truth fixtures are documentary evidence and are not Python tax-law expectations. The signed corpus release is `us-rulespec-2026-09-14-wave4-r2-union`; narrow union axiom-corpus#746 and signing decision d270 remain pending.
