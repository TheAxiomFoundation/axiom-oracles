# Canada executable oracle coverage

`scripts/run_canada_official_comparison.py inventory` emits only reproducible
numeric comparison engines. An official webpage, formula publication,
unavailable calculator, or discovery tool is not an oracle merely because it
comes from a government source.

| Oracle | Comparison role | Mode | Status |
| --- | --- | --- | --- |
| CRA Child and family benefits calculator | Numeric | Live HTTP session | Implemented for the federal CCB, child disability benefit, and Groceries and Essentials Benefit outputs currently encoded in RuleSpec Canada. |
| CRA Payroll Deductions Online Calculator (PDOC) | Numeric | Live public JSON API | Implemented for Ontario regular salary with default TD1 claims and zero year-to-date balances. The comparison uses source-shaped per-pay CPP, EI, and combined income-tax outputs. |
| Statistics Canada SPSD/M | Broad numeric model | Licensed local model | Implemented for the full-database 2025 federal schedule-tax comparison. The v34.0 adapter and reproducible aggregate report are registered; execution requires a local licensed installation, and no Package data is redistributed. |

## Excluded official surfaces

These surfaces are not emitted by the machine-readable oracle inventory and
must not supply comparison results:

| Surface | Why it is excluded |
| --- | --- |
| CRA GST/HST calculator | Its official rate-table adapter is reproducible, but no corpus-backed RuleSpec target or registered comparison suite exists yet. |
| Revenu Quebec WebRAS | The live interface is Cloudflare-gated. TP-1015.F-V formulas are source material, not an independent executable oracle. |
| ESDC Canadian EI Benefits Estimator | The public calculation route currently fails upstream. |
| ESDC Canadian Retirement Income Calculator | It is not automated and depends on personal contribution history and session-specific assumptions. |
| ESDC Canada Disability Benefit amount guidance | It is an official parameter/formula source, not an independent calculator. |
| Government of Canada Benefits Finder | It discovers candidate programs but does not calculate statutory entitlement amounts. |

No guessed, synthetic, or formula-fallback output may be promoted into the
oracle registry. Official source material can support corpus encoding and
RuleSpec proofs, but oracle results must come from an independently executable,
auditable comparison surface.

Oracle results are comparison evidence only. They are not copied into RuleSpec
parameters, formulas, or companion-test expectations. RuleSpec changes are
generated from corpus sources and installed through signed `axiom-encode
encode --apply` runs.

The SPSD/M lane's committed report contains aggregates and the required
Statistics Canada attribution, while the licensed synthetic database and
per-household extracts remain local. See `docs/spsdm-reproduction.md` for the
executable runbook.
