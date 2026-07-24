# Canada PolicyEngine coverage boundary

Authoritative snapshot of the PolicyEngine Canada comparison boundary for the
current `rulespec-ca` source-law surface. This matrix records why Canada outputs
remain on source-grounded oracle lanes until PolicyEngine exposes matching
current-law calculation boundaries.

## Provenance

- `rulespec-ca` snapshot: `8d8d2d8`
- `PolicyEngine/policyengine-canada` snapshot: `78aef804`
- Coverage classifier: `build_policyengine_coverage_report()`
- Mapping registry: `axiom_oracles/bridges/mappings/ca.yaml`

## Current denominator

The coverage classifier returns:

- **3,914 total Canada RuleSpec outputs**
- **0 PolicyEngine-comparable outputs**
- **3,914 known-not-comparable outputs**
- **0 untested comparable outputs**

The broad `ca:` `not_comparable` registry entry is intentional. No current
PolicyEngine Canada variable has yet passed the required legal-boundary,
parameter-vintage, entity, period, unit, and numerical-parity checks for these
RuleSpec outputs.

## Why candidate mappings were rejected

### Current benefits use stale PolicyEngine parameters

The 2026 RuleSpec CCB, Child Disability Benefit, Ontario Sales Tax Credit, and
Nova Scotia Affordable Living Tax Credit calculations use current official
amounts and thresholds. The corresponding PolicyEngine parameter files stop in
older benefit years. Matching variable names therefore do not establish
current-law parity.

Their output contracts also differ. RuleSpec represents the CRA July-to-June
benefit year and applies the calculation to a tax `Family`; the candidate
PolicyEngine variables use calendar-year periods and a co-resident `Household`.
Updating parameters alone would not resolve those period and entity boundaries.

Representative examples:

- RuleSpec CCB base amounts are `$8,157` and `$6,883`; PolicyEngine still uses
  `$6,997` and `$5,903`.
- RuleSpec Child Disability Benefit base is `$3,480`; PolicyEngine still uses
  `$2,985`.
- RuleSpec Ontario Sales Tax Credit amount is `$378`; PolicyEngine still uses
  `$345`.

### Adjusted family net income differs at the zero boundary

The relevant RuleSpec CCB, linked-credit, and CWB outputs floor adjusted family
net income at zero. PolicyEngine's `adjusted_family_net_income` variable does
not. Negative-income cases therefore diverge even before benefit parameters are
applied.

### Quebec tax and work-premium boundaries differ

PolicyEngine's Quebec tax rates stop in 2023, and `qc_taxable_income` is a
passthrough from `total_individual_pre_tax_income`. It cannot be compared
exactly with the 2025 TP-1 taxable-income schedule.

The Quebec work-premium variables also use older parameters and different
calculation structures. RuleSpec models the Schedule P line sequence, including
work-income phase-in, caps, spouse allocation, and a monthly supplement.
PolicyEngine exposes annual aggregate formulas at different boundaries.

### Payroll-contribution outputs are absent

PolicyEngine Canada does not currently expose standalone person-level annual
employee liabilities for CPP, QPP, EI, and QPIP. RuleSpec payroll outputs must
remain on official-source validation until those engine surfaces exist and pass
parity tests.

## Existing suites are not this comparison surface

- `ca-income-tax-liability` is an older pilot over legacy `us-ca:` identifiers
  and publishes explained residuals rather than exact `ca:` source-law parity.
- `ca-tanf-ecps`, `ca-snap-ecps`, and `ca-capi-limits` are California or legacy
  `us-ca:` suites, not Canada-country legal IDs.
- The SPSD/M adapter work is a separate Canada oracle lane. It does not make
  stale PolicyEngine variables exact matches for current RuleSpec outputs.

## PolicyEngine Canada upstream issue inventory

Existing upstream issues already cover part of the stale-engine work:

- [#506](https://github.com/PolicyEngine/policyengine-canada/issues/506)
  tracks the federal 2025 tax schedule.
- [#507](https://github.com/PolicyEngine/policyengine-canada/issues/507),
  [#508](https://github.com/PolicyEngine/policyengine-canada/issues/508), and
  [#509](https://github.com/PolicyEngine/policyengine-canada/issues/509) cover
  Alberta, British Columbia, and Quebec 2025 parameters.
- [#5](https://github.com/PolicyEngine/policyengine-canada/issues/5) and
  [#25](https://github.com/PolicyEngine/policyengine-canada/issues/25) cover
  federal taxable income and deductions.
- [#152](https://github.com/PolicyEngine/policyengine-canada/issues/152),
  [#403](https://github.com/PolicyEngine/policyengine-canada/issues/403), and
  [#527](https://github.com/PolicyEngine/policyengine-canada/issues/527) cover
  CPP, Employment Insurance benefits, and QPP respectively. Issue #403 does not
  cover employee EI premium liability; that output is tracked in #556 below.

The Axiom coverage audit added five focused issues:

1. [#553](https://github.com/PolicyEngine/policyengine-canada/issues/553)
   updates Ontario PIT parameters through the current comparison vintages.
2. [#554](https://github.com/PolicyEngine/policyengine-canada/issues/554)
   models the 2025 Canada Workers Benefit secondary-earner exemption.
3. [#555](https://github.com/PolicyEngine/policyengine-canada/issues/555)
   replaces provincial taxable-income passthroughs with legal calculations.
4. [#556](https://github.com/PolicyEngine/policyengine-canada/issues/556)
   exposes standalone annual employee CPP/QPP/EI/QPIP liabilities.
5. [#557](https://github.com/PolicyEngine/policyengine-canada/issues/557)
   updates current CRA family-benefit parameters and resolves the July-to-June
   benefit-year and tax-family entity boundaries.

## Axiom-side lane split

Canada validation should use:

- official CRA, Revenu Quebec, and other primary-source examples and invariants
  for encoded RuleSpec modules;
- the registered SPSD/M v34.0 full-database federal schedule-tax suite, with
  its documented concept and residual boundary, plus future SPSD/M suites only
  after the same boundary review;
- PolicyEngine only after a candidate output passes exact boundary, vintage,
  entity, period, unit, and numerical-parity review.

Mappings belong in the registry and parity belongs in oracle suites. Neither
RuleSpec formulas nor oracle adapters should hard-code values merely to imitate
an unavailable or stale PolicyEngine result.
