# Canada official oracle coverage

This inventory distinguishes executable numeric oracles from official source and
discovery surfaces. `scripts/run_canada_official_comparison.py inventory` emits
the machine-readable registry.

| Oracle | Comparison role | Mode | Status |
| --- | --- | --- | --- |
| CRA Child and family benefits calculator | Numeric | Live HTTP session | Implemented for the federal CCB, child disability benefit, and Groceries and Essentials Benefit outputs currently encoded in RuleSpec Canada. |
| CRA Payroll Deductions Online Calculator (PDOC) | Numeric | Live public JSON API | Implemented for Ontario regular salary with default TD1 claims and zero year-to-date balances. The comparison uses source-shaped per-pay CPP, EI, and combined income-tax outputs. |
| CRA GST/HST calculator | Numeric parameter arithmetic | Live official page bundle | The official page rate table and before-tax arithmetic adapter are implemented. RuleSpec comparison remains pending a corpus-backed GST/HST target. |
| Revenu Quebec WebRAS | Numeric | Official formula fallback | The live UI is Cloudflare-gated. Use the official TP-1015.F-V payroll formulas as the reproducible source surface; no live automated claim is made. |
| ESDC Canadian EI Benefits Estimator | Numeric | Temporarily unavailable | The public calculation route currently fails upstream. Preserve the registry entry and do not synthesize expected values. |
| ESDC Canadian Retirement Income Calculator | Projection | Session-bound web service | Not yet automated. Results require CPP/OAS history and projection assumptions in an ASP.NET session. |
| ESDC Canada Disability Benefit amount guidance | Parameter/formula | Official parameter page | Suitable for parameter and formula parity, but it is not an independent executable calculator. |
| Government of Canada Benefits Finder | Coverage discovery | Discovery only | Suitable for finding candidate programs, not for validating statutory amounts. |
| Statistics Canada SPSD/M | Broad numeric model | Licensed local model | Pending Statistics Canada delivery and local license setup. No redistribution or remote execution is assumed. |

Official calculator results are comparison evidence only. They are not copied
into RuleSpec parameters, formulas, or companion-test expectations. RuleSpec
changes are generated from corpus sources and installed through signed
`axiom-encode encode --apply` runs.
