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

### Selectors

Exactly one per entry, always scoped by `concept` (and the optional `kind`):

| Selector | Selects |
| --- | --- |
| `case_id` | one mismatch row |
| `case_selector` | `{case_ids: [...]}` and/or `{case_id_prefix: "..."}` |
| `signatures` | rows whose signature is listed: a stamped `signature` field, else the SHA-256 of the row identity `{concept, kind, delta, facts, error_signature}` (case id and absolute values excluded) |
| `match` | a structured selector over row fields (below) |

`match` bounds (all present bounds must hold):

```yaml
match:
  kind: amount_difference            # or a list
  facts: {state: [GA, MD], year: 2024, mstat: 2}   # row["facts"], scalar or list
  delta: {sign: pos, min: 30, max: 31, abs_min: 1, abs_max: 50,
          values: [30.8], tolerance: 0.005}        # signed left - right
  left: {min: 0, max: 100000, values: [...], tolerance: 0.005}
  right: {values: [0]}
  error_signature: SIGFPE            # engine_error rows: row["error"]["signature"]
  error_engine: taxsim               # engine_error rows: row["error"]["engine"]
```

An empty `match`, a `match` bounded only by `kind`, and vacuous bounds
(`delta: {}`, a lone `tolerance`) are invalid: no entry may claim a whole
concept. Rows gain `facts` when their population sets
`case.metadata["selector_facts"]` (copied verbatim onto each mismatch row);
rows without a bounded field never match it.

### Bindings

- `selector_binding` (on `case_selector`, `signatures`, `match` entries):
  `{units, rows_sha256}` — row count plus a digest over each selected row's
  identity and exact `left`/`right`/`difference` — or, for `signatures` entries,
  `{units, signature_population_sha256}` — a digest over the selected rows'
  `(signature, multiplicity)` pairs. Any drift expires the entry.
- `oracle_binding`: the oracle identity the classification was made
  against — `taxsim_binary_sha256: [<64-hex>, ...]`,
  `policyengine_taxsim: "<version>"`, and/or `identity_unrecorded: true`.
  The report's most specific recorded identity governs: recorded TAXSIM
  binaries (`provenance.oracle.taxsim_binaries[*].sha256`, else
  `engine_identity.taxsim.binaries[*].sha256`) must be a subset of the
  bound digests (per-row digests are used when every selected row records
  one — engine-error rows do; value rows do not, so a report that ran two
  binaries needs both listed); else a recorded
  `provenance.oracle.policyengine_taxsim` must equal the bound version;
  else only `identity_unrecorded: true` matches. Re-pinning TAXSIM
  therefore expires every classification made against the old binary.
- `identity_unrecorded: true` is an explicit legacy exception, not a verified
  oracle identity. The three migrated TAXSIM reports record neither C1 binary
  digests nor the package version. Their entries bind the exact observed row
  populations without inventing a historical version; they expire when a
  refreshed report records an identity. An unrecorded binary change with
  identical rows cannot be detected. New reports should always record C1
  identity and use a binary binding.
- `uv run scripts/bind_dispositions.py <suite>` computes all bindings (and
  `pinned` values for `case_id` entries) from the suite's committed FULL
  report and stamps them textually; `--check` reports drift without
  writing. Run it only after re-verifying the classifications.

### Attribution

`attribution` names who owns the residual: one of the engine names on the
suite's two sides (`runner.parameters.left`/`right` in
`comparisons/<suite>.yaml`; the engine adapter names when the suite
declares none) or `convention`, `input`, `two_sided`. Unknown values are
invalid. For the PE-vs-TAXSIM emulator lane the vocabulary is
`taxsim | policyengine | convention | input | two_sided`.

### Row arithmetic

`evidence.row_arithmetic` items `{expression, equals, tolerance}` reference
row variables — `left`, `right`, `difference`, `facts.<name>` — and are
checked on every selected row at merge time (`equals` may be a list: the row
passes if it equals any). One failing row expires the entry
(`row_arithmetic_failed`) and fails `apply_dispositions.py --check`.
Expressions stay restricted: numbers, `+ - * /`, parentheses, and those
names (dotted fact names are lookups, not attribute access); no calls.

### TAXSIM lanes

A suite with `taxsim` on either side is a TAXSIM lane. Every entry there
must carry `attribution` and `oracle_binding`; every multi-row selector a
`selector_binding`; every `case_id` entry `pinned` `left` and `right`; and
`row_arithmetic` or an upstream citation — constant-only `arithmetic` does
not count as reconciliation there. At merge time a row selected by two
entries is a conservation error (elsewhere the first entry still wins), and
an entry without `oracle_binding` expires. Suites whose sides are both
external engines must attribute every `upstream_engine_gap` entry.

### Engine-error rows

When either engine reports errors for a case, every compared output of the
case is a mismatch row of kind `engine_error` (never a match) carrying
`row["error"] = {engine, side, signature, messages[, binary_sha256,
returncode][, other_side]}`; `taxsim-crash:<signature>` messages yield their
signature (e.g. `SIGFPE`, `rc=139`), other errors `unclassified`. The report
summary gains `engine_error_count` when any exist. Dispositions select them
with `kind: engine_error` plus `match.error_signature`. If both engines fail,
error selectors inspect both sides; combined engine and signature bounds must
hold on the same side.

## Disposition kinds

| Kind | Meaning | Counts as explained |
| --- | --- | --- |
| `explained_residual` | The residual reconciles arithmetically to a documented convention or mechanism | yes |
| `upstream_engine_gap` | The counterpart engine diverges from the upstream source; filed or cited upstream | yes |
| `bridge_artifact` | The comparison harness fed the engines different inputs; not an engine or encoding defect | yes |
| `axiom_encoding_gap` | The Axiom encoding is missing or wrong; retained as a separate count | yes |
| `unexplained` | Explicitly recorded open investigation | no |

## Rules

- **Evidence is mandatory.** Every entry needs `evidence.mechanism` plus
  arithmetic that reconciles (constant `arithmetic` or per-row
  `row_arithmetic`; TAXSIM lanes accept only the latter) or an upstream
  citation (`evidence.upstream_url`, `linked_issue`, or `evidence.sources`).
  A disposition without evidence is invalid — classifications must reconcile
  numerically, not assert.
- **Arithmetic is checked.** `expression` supports numbers, `+ - * /`, and
  parentheses; it must equal `equals` within `tolerance` (default 0.005).
- **Citations cannot dangle.** Non-URL `sources` are repo-relative paths
  (optionally with an `#anchor`) and must exist.
- **Dispositions expire with their sources.** With
  `expires_on_source_change: true`, a pinned entry stops applying when the
  live mismatch values move away from `pinned`, and an entry whose mismatch
  disappears is reported as expired rather than silently relabeling a new
  residual. Non-expiring entries that match nothing are flagged as orphaned —
  delete them when their mismatch clears. An entry whose `selector_binding`,
  `oracle_binding`, or `row_arithmetic` no longer holds expires regardless;
  `summary.dispositioned.expired_reasons` records why (`no_live_rows`,
  `pinned_values_changed`, `selector_binding_violated`,
  `oracle_binding_missing`, `oracle_identity_changed`,
  `oracle_identity_unrecorded`, `oracle_identity_malformed`,
  `row_arithmetic_failed`).

## Where the numbers land

`apply_dispositions` joins these files into the comparison report (bumping it
to `axiom.comparison_report.v2.1`, additively): matching mismatch rows gain a
`disposition` annotation and `summary.dispositioned` carries
`raw_match_rate`, `explained_rate` (matches plus explained residuals,
upstream gaps, and bridge artifacts over total), and `unexplained_count`.
`scripts/run_comparison.py` merges automatically when writing dashboard
reports; `scripts/apply_dispositions.py` refreshes the checked-in dashboard
JSON for suites (such as the EUROMOD ones) that are generated outside CI.

## Merge invariants

- Each mismatch row receives at most one disposition. Overlapping selectors
  are errors in TAXSIM lanes; other suites retain the first applicable entry.
- For a complete report, the four classified counts plus `unexplained_count`
  equal `mismatch_count`, and matches plus mismatches equal comparisons.
  Explicit `unexplained` annotations are included in `unexplained_count`.
- `explained_rate >= raw_match_rate`, and both are bounded by 0 and 100 for
  a consistent report. All four classified kinds, including
  `axiom_encoding_gap`, count toward the existing explained-rate calculation.
- `assignment_digest` is independent of row order and, for disjoint selectors,
  entry order. It retains multiplicity and each row's case, concept, entry id,
  and disposition kind.
- An entry whose population binding, oracle identity, or row arithmetic
  fails assigns zero rows. Reapplying the merge clears stale annotations;
  unchanged valid inputs produce the same assignments without mutating them.

The migration proof and its legacy-identity limitations are recorded in
[`docs/taxsim-disposition-migration-audit.md`](../docs/taxsim-disposition-migration-audit.md).
