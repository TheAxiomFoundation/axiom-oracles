# SNAP State Encoding Inventory

Current as of 2026-06-02. This is an implementation inventory, not a claim that
all listed rules are fully comparable to PolicyEngine.

## Dashboard / Program Coverage

| State | Status | Notes |
| --- | --- | --- |
| CA | Dashboard SNAP clean | Direct encoder comparison path; 0 current mismatches. |
| NY | Dashboard SNAP clean | Direct encoder comparison path; 0 current mismatches. |
| CO | Dashboard SNAP clean | Existing composed SNAP program; good candidate for broader axiom-programs consolidation. |
| NC | Dashboard-composed SNAP | Local composed spec under `comparisons/programs`; not yet merged into `axiom-programs`. Remaining non-TANF issue is annual-FPG vs FY2026 monthly SNAP table treatment. |
| SC | Dashboard-composed SNAP | Local composed spec under `comparisons/programs`; not yet merged into `axiom-programs`. Remaining residuals include PE categorical treatment and TANF income. |
| AL | Merged axiom-programs SNAP | Current residuals are 21 PE TANF-in-SNAP-income cases, 1 PE-only income/categorical case, 1 Axiom-only threshold/disqualification case, and 1 PE-greater amount edge. |
| TN | Merged axiom-programs SNAP | Current residuals are 30 PE Families First/TANF-in-SNAP-income cases and 1 PE-greater amount edge; five eligibility residuals also include PE Families First/TANF. |
| MA | Merged axiom-programs SNAP | HCSUA and categorical/standard income rollup are wired; remaining gaps are TAFDC/TANF and missing categorical service/source facts in ECPS. |

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

1. Promote NC and SC local dashboard-composed specs into `axiom-programs` once
   the current comparison shape is accepted.
2. For CO, either add the existing composed SNAP program to `axiom-programs` or
   document why it should stay dashboard-local.
3. For FL, build a first-pass composed SNAP program from the existing categorical
   and food-assistance corpus, then run full ECPS before attempting fixes.
4. For AZ, use the encoded utility/deduction surfaces to improve shelter-cost
   modeling only after a state amount source is available.
5. Continue avoiding TANF/Families First/TAFDC synthetic projection. Those gaps
   should remain visible until the relevant cash-assistance programs are modeled
   or an explicit source-backed input is available.
