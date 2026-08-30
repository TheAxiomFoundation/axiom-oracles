# Belgium coverage matrix — documentary concepts only

This page summarizes the active EUROMOD Belgium `BE_2025` comparison surface.
The machine-readable source of truth is
`axiom_oracles/data/euromod_be_coverage.json`, mirrored byte-for-byte to
`dashboard/public/data/euromod-be-coverage.json`.

The boundary is strict: RuleSpec exports only concepts stated in public policy
documents. EUROMOD remains an executable comparison oracle, not a source of
Belgian legal concepts. Aggregation, routing, behavioral assumptions, and
comparator-shaped pipeline outputs belong in the oracle or application layer.

## Denominator and current claim

The pinned `BE_2025` XML contains 43 policy nodes, 1,171 functions, and 8,211
parameters. The inventory does not report a RuleSpec coverage percentage until
every policy/function is classified as encoded, externally composed,
oracle-tested, or a gap.

The current top-level dashboard contains 13 Belgium reports covering 45
comparisons. Of those, 30 are exact raw matches; schema-validated dispositions
explain the remaining 15, leaving zero unexplained comparisons. Historical
reports are excluded from these totals.

## Current documentary comparison suites

| Surface | Current suites | Scope note |
|---|---|---|
| Employer social security | `be-employer-ssc` | Source-backed ordinary employer contribution; the employee suite is retired pending a direct-only rerun |
| Self-employed and special contributions | `be-self-employed-ssc`, `be-special-social-security-contribution` | Source-backed contribution rules; known EUROMOD residuals stay dispositioned |
| Flemish programs | `be-flemish-social-protection-premium`, `be-flemish-jobbonus` | Documentary regional outputs |
| Property and capital tax | `be-cadastral-income-indexation`, `be-capital-income-tax` | Direct legal tax concepts; no current gross property-tax aggregate |
| Regional and municipal PIT components | `be-regional-pit-surcharge`, `be-local-municipal-pit` | Component outputs stated in the relevant law |
| Social assistance | `be-social-assistance`, `be-elderly-income-support` | Social-integration income and GRAPA/IGO |
| Leave compensation | `be-maternity-leave`, `be-birth-leave` | Direct indemnity and compensation outputs |

Each current report carries its own engine, model, RuleSpec, and data provenance.
The coverage inventory records the residual status for each EUROMOD variable;
this table does not replace those pins.

## Article 51 transition

The Python case suite for the Article 51 employee professional-expense forfait
remains available because it now queries the direct documentary
`article_51_forfaits` output and bridges only EUROMOD's exposed
`il_netYem` base into that module's documentary input.

It is not currently published or counted as conformance evidence. Its previous
report imported a retired worker pipeline and is archived as historical evidence.
A new current report must wait for the signed canonical page-121/page-122
migration, then rerun real Axiom and EUROMOD against the receipted target.

## External composition and routing

These EUROMOD outputs are not atomic RuleSpec concepts:

| EUROMOD output | Active status | Correct layer |
|---|---|---|
| `tin_s` | no direct mapping | Compose documentary PIT components in conformance or an application |
| `bun_s` | no direct mapping | Compare against a documentary unemployment composition outside RuleSpec |
| `bed_s` | no direct mapping | Select and aggregate the applicable Community documentary output outside RuleSpec |
| `tsceerd_s` | no direct mapping | Annualize documentary monthly work-bonus outputs outside RuleSpec |
| `tprhm_s` | no direct mapping | Select the regional property-tax rule and apply local centimes outside RuleSpec |
| `bchba_s` | no direct mapping | Select the documentary regional birth-allowance output outside RuleSpec |
| `bch_s` | no direct mapping | Compose regional, annual, supplement, and household child-benefit outputs outside RuleSpec |
| `ils_tax` | no direct mapping | EUROMOD tax income-list aggregate in the oracle layer |
| `ils_ben` | no direct mapping | EUROMOD benefit income-list aggregate in the oracle layer |
| `ils_dispy` | no direct mapping | EUROMOD disposable-income aggregate in the oracle layer |

The source-backed employee, pensioner, family-benefit, and regional property-tax
components remain available. They are not current comparison evidence until a
fresh suite targets a surviving documentary output directly.

## Historical evidence

Retired comparison reports, their generated dispositions, and their case chunks
are preserved byte-for-byte under
`dashboard/public/data/historical/retired-documentary-boundary/`. The
37-file archive contains 21 former reports, 10 generated disposition results,
four case artifacts, one structured retired-issue extraction, and its README. The
historical directory is intentionally outside the dashboard manifest,
conformance scoreboard, exercise census, freshness registry, and current
disposition rollup. Its README lists the retired module prefixes and the archive
contract.

## Updating this matrix

1. Change the active suite/config surface only after the RuleSpec target has an
   official encoder receipt.
2. Run the real Axiom runtime; never substitute a parallel calculation.
3. Regenerate grids, affected mappings, dispositions, dashboard overview,
   conformance compositions/scoreboard, exercise census, and freshness.
4. Update `euromod_be_coverage.json` and its dashboard mirror together.
5. Keep retired evidence historical; publish a new report rather than rewriting
   old results.
