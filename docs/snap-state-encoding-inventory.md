# SNAP State Encoding Inventory

Current as of 2026-06-02. This is an implementation inventory, not a claim that
all listed rules are fully comparable to PolicyEngine.

## Dashboard / Program Coverage

| State | Status | Notes |
| --- | --- | --- |
| CA | Dashboard SNAP clean | Direct encoder comparison path; 0 current mismatches. |
| NY | Dashboard SNAP clean | Direct encoder comparison path; 0 current mismatches. |
| CO | Dashboard SNAP clean | Direct encoder comparison path is clean. The `rulespec-us/us-co/programs/snap/fy-2026.yaml` wrapper compiles and the generic adapter now runs without engine errors, but the full generic household-level run is not clean (694 CO households, 1,388 comparisons, 276 mismatches). The dashboard remains on the encoder-backed SPM/SNAP-unit projection, which is clean over 730 units. |
| NC | Canonical SNAP program | Composed spec now lives under `rulespec-us/us-nc/programs/snap/fy-2026.yaml`. Remaining non-TANF issue is annual-FPG vs FY2026 monthly SNAP table treatment. |
| SC | Canonical SNAP program | Composed spec now lives under `rulespec-us/us-sc/programs/snap/fy-2026.yaml`. Remaining residuals include PE categorical treatment and TANF income. |
| AL | Canonical SNAP program | Current residuals are 21 PE TANF-in-SNAP-income cases, 1 PE-only income/categorical case, 1 Axiom-only threshold/disqualification case, and 1 PE-greater amount edge. |
| TN | Canonical SNAP program | Current residuals are 30 PE Families First/TANF-in-SNAP-income cases and 1 PE-greater amount edge; five eligibility residuals also include PE Families First/TANF. |
| MA | Canonical SNAP program | HCSUA and categorical/standard income rollup are wired; remaining gaps are TAFDC/TANF and missing categorical service/source facts in ECPS. |

## Other Local State RuleSpec Repos

| State | Local SNAP signal | Readiness |
| --- | --- | --- |
| AZ | SNAP deduction and utility eligibility surfaces, including utility allowance eligibility and dependent-care deductions. | Useful for targeted shelter/utility work; not a full SNAP program yet. |
| FL | Substantial human-services corpus with food assistance / TCA technical pages, including categorical eligibility. | Promising next first-pass composition candidate, but needs program assembly and source-input alias review. |
| ID | Mostly definitions and administrative food stamp material. | Low immediate comparison value. |
| NH | Administrative SNAP notice delivery rule. | Low immediate comparison value. |
| OK | No usable local SNAP YAML found. | Not ready. |
| DE | No usable local SNAP YAML found. | Not ready. |

## Next Practical Moves

1. For CO, add source-backed mappings from the generic composed program outputs
   to the federal SNAP dashboard concept IDs before switching the dashboard off
   the current clean encoder-backed comparison path.
2. For FL, build a first-pass composed SNAP program from the existing categorical
   and food-assistance corpus, then run full ECPS before attempting fixes.
3. For AZ, use the encoded utility/deduction surfaces to improve shelter-cost
   modeling only after a state amount source is available.
4. Continue avoiding TANF/Families First/TAFDC synthetic projection. Those gaps
   should remain visible until the relevant cash-assistance programs are modeled
   or an explicit source-backed input is available.
