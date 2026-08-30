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
suite: be-employer-ssc
updated: "2026-07-05"
entries:
  - id: stale-company-closing-fund-rates
    concept: be:regulations/...#belgium_employer_social_security_ordinary_worker_contribution
    case_id: be-employer-ssc-30k      # or case_selector: {case_ids: [...]} /
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

## Where the numbers land

`apply_dispositions` joins these files into the comparison report (bumping it
to `axiom.comparison_report.v2.1`, additively): matching mismatch rows gain a
`disposition` annotation and `summary.dispositioned` carries
`raw_match_rate`, `explained_rate` (matches plus explained residuals,
upstream gaps, and bridge artifacts over total), and `unexplained_count`.
`scripts/run_comparison.py` merges automatically when writing dashboard
reports; `scripts/apply_dispositions.py` refreshes the checked-in dashboard
JSON for suites (such as the EUROMOD ones) that are generated outside CI.
