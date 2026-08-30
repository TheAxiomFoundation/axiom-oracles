# Retired Belgium oracle evidence

These files are historical evidence from Belgium comparisons that targeted
RuleSpec modules retired at the documentary-concept boundary. The comparison
reports, generated dispositions, and case chunks remain byte-for-byte copies of
their former current locations. The issue archive is a structured extraction of
the corresponding retired-only issue-ledger entries. None are dashboard inputs,
current comparison reports, active dispositions, or executable case fixtures.
Current-data loaders intentionally scan only the parent
`dashboard/public/data` directories and must not recurse here.

The archived Article 51 report is included because that run imported the
retired worker oracle pipeline. The `be-article-51-forfait` suite itself remains
active on the legacy documentary `article_51_forfaits` output, pending a fresh
run after the signed canonical page-121/page-122 migration lands.

The archive contains 37 files: this README, 21 former comparison reports, 10
generated disposition results, four case artifacts, and one structured retired
issue extraction. The expanded hard cut added the former worker-SSC, pensioner
contribution, gross property-tax, birth-allowance, child-benefit base, Brussels
social-supplement, Brussels same-age-household, and Wallonia social-supplement
reports. Their 12 generated report/disposition artifacts were moved here
without changing their bytes.

The retired RuleSpec module prefixes are:

- `be:policies/euromod_benefit_income_list`
- `be:policies/euromod_disposable_income_list`
- `be:policies/euromod_tax_income_list`
- `be:regulations/unemployment/pilot_oracle_pipeline`
- `be:statutes/family_benefits/regional_routing`
- `be:statutes/gift_tax/regional_routing`
- `be:statutes/inheritance_tax/regional_routing`
- `be:statutes/education/study_allowance_routing`
- `be:statutes/income_tax/individual/pilot_worker_oracle_pipeline`
- `be:statutes/income_tax/individual/couple_pit_oracle_pipeline`
- `be:statutes/income_tax/individual/pensioner_pit_oracle_pipeline`
- `be:statutes/income_tax/individual/self_employed_oracle_pipeline`
- `be:statutes/property_tax/gross_withholding_and_supplied_centimes`
- `be:statutes/property_tax/regional_routing`
- `be:statutes/vehicle_tax/regional_routing`

Preserve the archived JSON bytes. A future documentary replacement must publish
a new current report from a real Axiom run; it must not rewrite these records.
