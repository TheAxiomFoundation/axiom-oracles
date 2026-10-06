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
the policy right.

**Which entries blame PolicyEngine.** Attribution is computed from the
committed data. It does not come from entry names: for example,
`nd-open-rows-axiom-pe-divergent` annotates TAXSIM rows, so it is not
attributed. Only `upstream_engine_gap` entries can be attributed, in one of
four ways:

- The rows the entry annotates in the committed dashboard report compare
  Axiom with PolicyEngine. A row that compares two oracles (PolicyEngine vs
  TAXSIM, Tax-Calculator vs PolicyEngine) has no Axiom leg, so it does not
  say which side is wrong and attributes nothing on its own.
- The entry annotates no rows, and PolicyEngine is the report's only
  counterpart.
- The entry annotates no rows, the report has several oracles, and the
  entry's `kind` is a PolicyEngine-leg kind.
- The entry links a PolicyEngine issue or pull request, whatever its rows
  say.

A known cause (`dashboard/public/data/known_causes.json`) falls under the
same rule when two things hold:

- Its `fix_owner` names `policyengine` as one of its hyphenated parts, or its
  `issue_url` links PolicyEngine.
- It explains a live bucket: the dashboard's `causeFor()` picks it for some
  (concept, kind) bucket of mismatch rows in a committed report. When a
  report publishes only a sample of its rows, a nonzero per-concept count
  also keeps the cause live.

A cause whose mismatch cleared attributes nothing. Of two causes for one
bucket, only the one the dashboard shows attributes.
An explicit `engines` mapping must be nonempty; omit it for a generic cause.
Suite, concept and kind identifiers used for attribution must be nonempty
strings without `::` or `|`, so dashboard buckets and ratchet identities
cannot alias one another. Unknown string kinds remain attributed when the
dashboard selects the cause; only actual eligibility row kinds allow judgment
assertions instead of numeric assertions.

Every such entry must carry:

- a PolicyEngine **issue** URL, in `linked_issue` or `evidence.upstream_url`
  (`issue_url` for a known cause). A pull request attributes the entry but
  does not count as the issue; cite the issue it closes. Comment anchors,
  query strings and a lowercase org are accepted.
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

A companion must be about the disputed concept.

- When the concept is a RuleSpec output (its module's companion test asserts
  it on its canonical repository's main or at the pinned commit), the concept
  itself must be among `legal_ids`, and `--resolve` refuses a companion that
  leaves it out. An older pin cannot hide a concept now encoded on main.
- A comparison-surface concept (such as `us:tax/federal-income-tax#eitc`) has
  no module of its own. For those, every legal id and test must at least be
  in the concept's country (`us` → `rulespec-us` or `rulespec-us-*`).

**The ratchet.** `scripts/pe_axiom_standard.py --check` enforces all of this
in CI against `conformance/pe-axiom-standard.yaml`. That file is generated;
do not hand-edit it. The entries that predated the standard are grandfathered
there, each with its computed status. `open_max` counts attributions without
a companion (declared debt plus grandfathered).

The check compares the file with every committed version of itself, the way
`scripts/closure_universe.py` derives its pending floor, so neither a pull
request nor a direct push can loosen it by editing the file:

- The grandfathered list may only shrink, and a grandfathered entry's status
  may only rise.
- The `debt_raises` log only grows. No committed record may be removed or
  edited.
- `open_max` may not exceed any committed version's `open_max` plus the
  increments (`to - from`) of the raise records added since that version.
  Only a deliberate raise lifts the ceiling:
  `uv run scripts/pe_axiom_standard.py --raise-ceiling "<reason>"` appends a
  dated record (`from`, `to`, `reason`) and raises by exactly `to - from`.

Because each version is charged only for the raises it has not seen,
parallel branches merge. After a merge or a revert, re-pin with
`uv run scripts/pe_axiom_standard.py`, adding `--raise-ceiling` when the open
count rose. The re-pin starts from what history enforces, not from the
working file alone:

- it restores every committed raise record
- it drops grandfathered rows any version closed
- it lowers `open_max` to the committed ceiling

`--resolve` checks each declared Axiom side against GitHub (the RuleSpec test
files can come from local clones instead):

- **PolicyEngine citations** must resolve to issue payloads with the cited
  repository and number. A PR returned by GitHub's issues endpoint does not
  qualify. Both open and closed issues qualify; absent or unverifiable reads
  fail closed.
- **Companion tests:**
  - The literal repository-relative `.test.yaml` path exists as a regular
    Git file at the pinned commit, and that commit is on main. URL queries,
    percent escapes, Windows separators, empty/dot path components and
    symlinks cannot stand in for that file. Case and Unicode are matched
    exactly; the raw fetch encodes the literal path.
  - The case asserts each legal id.
  - A case named like the disputed case asserts the Axiom value from the
    comparison. Amounts require numeric assertions within an absolute
    0.005; eligibility outputs also compare judgments as holds/not_holds
    or 0/1. A one-row tables case compares by its row. Unreadable or
    conflicting values for a known disputed case fail.
    Actual matched row kinds determine amount versus eligibility validation,
    including rows in the exact bucket selected for a known cause. An optional
    disposition `kind` filter cannot change that type. Conflicting row types
    fail; without row evidence, assertions must be numeric.
  - The case is still on main and asserts the same values there, because
    RuleSpec CI runs main.
- **Encoding debt** must be an open issue, not a pull request, in a
  TheAxiomFoundation `rulespec-*` repository. A closed debt issue means the
  encoding landed: replace the debt with `axiom_companion`, or reopen it.

Transient GitHub failures are retried and reported as "re-run", never as
"not found".

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
