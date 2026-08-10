# Closure universes

Closure is the completeness analogue of the conformance harness. Conformance asks
whether an encoding agrees with an oracle; closure asks whether every provision
under a declared source root is accounted for as `encoded`, `excluded` for a
reviewable reason, or honestly `pending`.

The initial certificate scope is `us-co/snap`, over three pinned roots:

| Universe | Pinned denominator | Exact RuleSpec module prefix |
| --- | --- | --- |
| `state-10-ccr-2506-1` | `co-provisions.jsonl` | `us-co/regulations/10-ccr-2506-1/` |
| `us-7-cfr-273` | `cfr-273.jsonl` | `us/regulations/7-cfr/273/` |
| `us-7-usc-51` | `usc-51.jsonl` | `us/statutes/7/` |

Every JSONL row is in the denominator, including document, part, subpart, and
title nodes. This literal all-provision rule avoids silently changing the
denominator by filtering source kinds.

## Generate and check

```console
uv run scripts/closure_universe.py --generate
uv run scripts/closure_universe.py --check
```

`--generate` verifies the hashes in `data/provenance.yaml`, joins every citation
to the pinned RuleSpec tree, preserves valid human review decisions, and writes
the three universes plus `summary.json`. `--check` performs the same derivation
without writing and fails on invalid decisions, source drift, stale generated
facts or summary counts, missing referenced modules, or a pending-count
regression.

The v1 encoding join is deliberately mechanical and exact. It maps a corpus
citation path to one candidate RuleSpec `.yaml` path and tests exact membership
in `data/rulespec-us-files.txt`. It does not search snapshot filenames or treat
a descendant module as proof that its parent provision is fully encoded. For
example, `us/regulation/7/273/2` maps to
`us/regulations/7-cfr/273/2.yaml`; the presence of `2/j.yaml` does not close the
whole section.

## Human-reviewed fields

`citation`, `heading`, the source/RuleSpec provenance, and the default
file-join status are generated facts. Reviewers may replace a row with:

- `status: excluded`, plus a non-empty `reason` and content-grounded `basis`; or
- `status: encoded` with a corrected non-empty `encoded_by` list whose module
  paths exist in the pinned RuleSpec tree.

An optional `note` is preserved. Allowed exclusion reasons are:

- `container_heading`
- `procedural_no_point_in_time_effect`
- `reserved`
- `no_household_computation`
- `operationalized_by:<module path>`

The last form names the existing RuleSpec module that fully realizes the
provision. Partial coverage remains `pending`.

An `encoded_by` list equal to the mechanical citation-path candidate is a
generated fact, not a review override. That distinction lets a new RuleSpec pin
demote the row back to `pending` if the module disappears. A corrected list
points somewhere else in the pinned tree and survives regeneration.

## Pending ratchet

Each universe records `ratchet.pending_max` against its generated provenance
header. Its content-pin fingerprint and ceiling are duplicated in `summary.json`;
the two prior copies must agree before regeneration can write either one. The
gate also derives an immutable floor from every committed ancestor universe
with the same content pins; coordinated edits to both current copies therefore
cannot raise the floor. CI checks out full Git history for this comparison, and
the gate rejects shallow repository checkouts. With unchanged source and
RuleSpec content pins, regeneration may only lower the ceiling. Changing either
pin starts a new baseline because the denominator or encoding inventory may
have changed. `summary.json` reports the live counts; `closed` is true only when
every root has zero pending rows.

This file-path join is evidence of repository coverage, not proof that every
legal subrule is faithfully implemented. A later node/citation join can replace
the v1 shim without changing the universe or ratchet discipline.

## Known pinned-data shape defects

- The chapter 51 projection has no `heading` field on 287 subsection/paragraph
  rows. The universe keeps the required field as an empty string rather than
  inventing a heading.
- The Colorado projection flattens every section directly under the document
  node. In the source PDF, `4.802.6` contains `4.802.61`–`.63` and `4.900`
  contains `4.901`–`.905`; both are bodyless container headings. A heuristic
  requiring child citations to begin with the parent plus a dot incorrectly
  reports them as childless. The exact closure join does not use that heuristic.
- The pinned RuleSpec inventory contains three default-Git C-quoted paths for
  `1437c–1` rather than literal Unicode paths. They are outside these three
  roots and do not affect the counts. A future universe covering that root
  should pin a NUL-delimited/unquoted inventory.
