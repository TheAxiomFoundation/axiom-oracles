# Mismatch dispositions

Raw match rates misrepresent parity when the remaining mismatches are fully
explained — the Belgium lane showed 59/88 (67%) raw while every residual was
either an arithmetically reconciled convention difference or a filed upstream
engine issue. This directory gives those classifications a first-class,
schema-validated home instead of scattering them across notes and comments.

One file per comparison suite: `dispositions/<suite>.yaml`, where `<suite>`
matches the `suite` field of the comparison report. Schema
`axiom_oracles.dispositions.v1` is defined and enforced by
`axiom_oracles/comparison/dispositions.py`; CI validates every file via
`scripts/apply_dispositions.py --check`.

## Entry shape

```yaml
schema: axiom_oracles.dispositions.v1
suite: be-worker-ssc
updated: "2026-07-05"
entries:
  - id: work-bonus-january-2025-timing
    concept: be:regulations/...#belgium_worker_work_bonus_..._total_reduction
    case_id: be-worker-ssc-30k        # or case_selector: {case_ids: [...]} /
                                      #    {case_id_prefix: "..."}
    kind: amount_difference           # optional mismatch-kind filter
    disposition: upstream_engine_gap
    evidence:
      mechanism: >-
        What causes the residual, in one paragraph.
      arithmetic:                     # each item must reconcile numerically
        - expression: "3398.52 - 3386.87"
          equals: 11.65
      upstream_url: https://github.com/ec-jrc/...
      sources:
        - axiom_oracles/data/euromod_issues.json#<entry-id>
    linked_issue: https://github.com/ec-jrc/...
    expires_on_source_change: true
    pinned:                           # optional, single-case entries only
      left: 3398.52
      right: 3386.87
```

## Disposition kinds

| Kind | Meaning | Counts as explained |
| --- | --- | --- |
| `explained_residual` | The residual reconciles arithmetically to a documented convention or mechanism | yes |
| `upstream_engine_gap` | The counterpart engine diverges from the upstream source; filed or cited upstream | yes |
| `bridge_artifact` | The comparison harness fed the engines different inputs; not an engine or encoding defect | yes |
| `axiom_encoding_gap` | The Axiom encoding is missing or wrong; classified, but never counted as explained | no |
| `unexplained` | Explicitly recorded open investigation | no |

## Rules

- **Evidence is mandatory.** Every entry needs `evidence.mechanism` plus
  arithmetic that reconciles or an upstream citation (`evidence.upstream_url`,
  `linked_issue`, or `evidence.sources`). A disposition without evidence is
  invalid — classifications must reconcile numerically, not assert.
- **Arithmetic is checked.** `expression` supports numbers, `+ - * /`, and
  parentheses; it must equal `equals` within `tolerance` (default 0.005).
- **Citations cannot dangle.** Non-URL `sources` are repo-relative paths
  (optionally with an `#anchor`) and must exist.
- **Dispositions expire with their sources.** With
  `expires_on_source_change: true`, a pinned entry stops applying when the
  live mismatch values move away from `pinned`, and an entry whose mismatch
  disappears is reported as expired rather than silently relabeling a new
  residual. Non-expiring entries that match nothing are flagged as orphaned —
  delete them when their mismatch clears.

## PolicyEngine attributions carry their Axiom side

Standard (2026-09-24): a PolicyEngine policy bug is not done until Axiom has
the policy right. An `upstream_engine_gap` entry blames PolicyEngine when
the rows it annotates in the committed dashboard report have PolicyEngine as
the counterpart engine. An entry that annotates no rows is also attributed
when the report's only counterpart is PolicyEngine, or when its `kind` is a
PolicyEngine-leg kind in a multi-oracle report. An entry is also
attributed, whatever its rows say, when it links a PolicyEngine issue or pull
request. Attribution is computed from the data. It does not come from entry
names: `nd-open-rows-axiom-pe-divergent` annotates TAXSIM rows, so it is not
attributed. Known causes (`dashboard/public/data/known_causes.json`) whose
`fix_owner` starts with `policyengine`, or whose `issue_url` is a PolicyEngine
issue, fall under the same rule.

Every such entry must carry:

- the PolicyEngine issue URL in `linked_issue` or `evidence.upstream_url`
  (`issue_url` for a known cause), and
- exactly one of:

```yaml
    axiom_companion:                  # (i) Axiom asserted correct, pinned by a test
      legal_ids:
        - us:policies/income_tax/salt_deduction_pipeline#federal_salt_deduction
      tests:
        - rulespec-us@<40-hex sha on main>:us/policies/income_tax/salt_deduction_pipeline.test.yaml#salt-low-agi-engine-cap
    # or
    axiom_encoding_debt: https://github.com/TheAxiomFoundation/rulespec-us/issues/<n>   # (ii) owed
```

`scripts/pe_axiom_standard.py --check` enforces this in CI against
`conformance/pe-axiom-standard.yaml`, which is generated and must not be
hand-edited. The entries that predated the standard are grandfathered there,
each with its computed status. `open_max` counts attributions without a
companion (declared debt plus grandfathered). The check compares the file
with every committed version of itself, the way
`scripts/closure_universe.py` derives its pending floor, so a pull request or
a direct push cannot loosen it by editing the file:

- the grandfathered list may only shrink, and a grandfathered entry's status
  may only rise;
- `open_max` may only fall. A deliberate raise is
  `uv run scripts/pe_axiom_standard.py --raise-ceiling "<reason>"`, which
  appends a dated `debt_raises` record (`from`, `to`, `reason`). That list is
  append-only. The record binds the raise: `open_max` may not exceed the
  latest `to`, and `from` may not exceed the committed ceiling it replaces,
  so the record states the whole increase.

`--resolve` checks each companion pointer against the RuleSpec repository:

- the file exists at the pinned commit
- the commit is on main
- the case asserts each legal id
- a case named like the disputed case asserts the Axiom value from the
  comparison

`--suggest --rulespec-checkout rulespec-us=<clone>` lists open attributions
whose disputed case already exists as a companion case.

## Where the numbers land

`apply_dispositions` joins these files into the comparison report (bumping it
to `axiom.comparison_report.v2.1`, additively): matching mismatch rows gain a
`disposition` annotation and `summary.dispositioned` carries
`raw_match_rate`, `explained_rate` (matches plus explained residuals,
upstream gaps, and bridge artifacts over total), and `unexplained_count`.
`scripts/run_comparison.py` merges automatically when writing dashboard
reports; `scripts/apply_dispositions.py` refreshes the checked-in dashboard
JSON for suites (such as the EUROMOD ones) that are generated outside CI.
