VERDICT: APPROVE

# Re-review — `data/month-fix-regen` repair round

Reviewed target
`58c6075f05e2e6509d1b79f8493afa72441df604` resolves both mechanical
findings from the prior review. No blocking or material repair defect remains.
This review was limited to the claimed repairs and their containment; the
previously approved data-integrity work was not reopened.

## Frozen scope

- Reviewed head: `58c6075f05e2e6509d1b79f8493afa72441df604`.
- Repair start / previously verified artifact state:
  `f0a6598e1337310fdf2f663af91b7ab81f773491`.
- Literal merge base:
  `819f370bf0346e4a6a8dfb1c8c4f0d873d6d0340`.
- Literal PR #423 merge:
  `1b57affd55eeaf765ac33c18645df2253a51d3d8`.
- Disposable worktree:
  `/Users/maxghenis/TheAxiomFoundation/axiom-oracles/_worktrees/month-fix-regen`.
- No remote or GitHub write was performed.

## Repair 1 — append-preserved progress ledger

Direct byte comparison passed:

| Evidence | Result |
| --- | --- |
| Merge-base prefix size | 57,579 bytes / 951 lines |
| Merge-base prefix SHA-256 | `c453af85c7e77b13a2ea18fcfd884f149d4783c4edf712354a85485d67b8379a` |
| `cmp` of merge-base file and reviewed-head prefix | exit 0 |
| Base-to-reviewed-head numstat | 391 insertions / 0 deletions |

The separator-delimited historical month-regeneration ledger embedded after
that prefix is also byte-identical to `f0a6598e:PROGRESS.md`: 14,644 bytes,
245 lines, SHA-256
`0e2cabe4771cd9cb75547f6908d83d79dbb9d269aac46bc3e3892f8ce5d95851`.

The remaining appended repair entries are a faithful record of the four repair
commits and repeated verification: their cited refs, changed paths, counts,
checker receipts, test totals, protected hashes, and sandbox disclosure all
reconcile. The ledger repair therefore satisfies exact prefix preservation and
append containment.

## Repair 2 — literal California disposition accounting

The disposition file at PR #423 merge `1b57affd` and merge base `819f370b` is
byte-identical, with SHA-256
`18cfbe28f951261142bfa3c52d0c88f6d0a3d53b77b597fcd807b4d2e9a23086`.
It contains 349 total entries, of which exactly 345 are `ca-362-*` rows.

I independently parsed that YAML and joined it to the reviewed source report,
current source dispositions, and compact case tree without importing the new
reconciler. The result is:

| Literal-base disposition | Rows |
| --- | ---: |
| Vanished from the current mismatch identity set | 192 |
| Current mismatch, but dropped from current dispositions | 22 |
| Kept with exact current source/report identity | 131 |
| Total | 345 |

The 131 kept rows independently divide into 115 materially moved pins and 16
unchanged pins. All kept source pins equal their current report pins.

The pinned saved requested-month trace has SHA-256
`c46af9b87c8f5ad01f1909bc45e80e00b4c4a50e5b802ea4ccbe194b5954b568`.
An independent trace-to-report join confirmed all 22 current-but-dropped pins
moved materially; none is disposition-covered or silently annotated. The full
drift-row receipt digest is
`fa54f6fdf05592da62c3c03b74264a4dfb7d9828e4f33ea169e75fc033ad3a51`.

### Vanished sample

The following 12 literal-base rows are absent from the 529-row current report
identity set and from current `ca-362` source entries. Each household exists in
the compact tree at a 100% match rate with zero mismatch rows for the old
concept.

| Literal-base row | Old pin |
| --- | --- |
| `ca-362-self-employment-forward-ecps-59082-benefit` | `148 / 0` |
| `ca-362-self-employment-forward-ecps-59082-eligibility` | `true / false` |
| `ca-362-self-employment-forward-ecps-62506-benefit` | `454 / 0` |
| `ca-362-self-employment-forward-ecps-62506-eligibility` | `true / false` |
| `ca-362-disability-shelter-cap-ecps-61953-benefit` | `392 / 215.68473307291666` |
| `ca-362-period-ecps-57158-benefit` | `342 / 350.0795084635417` |
| `ca-362-period-ecps-57289-benefit` | `718 / 727.5545247395834` |
| `ca-362-period-ecps-57404-benefit` | `481 / 489.3452962239583` |
| `ca-362-period-ecps-57472-benefit` | `773 / 782.8538411458334` |
| `ca-362-period-ecps-57737-benefit` | `227 / 234.2703653971354` |
| `ca-362-period-ecps-57783-benefit` | `1007 / 1016.3794759114584` |
| `ca-362-period-ecps-58054-benefit` | `417 / 425.9882405598958` |

This sample includes all four literal-merged-only identities for `ecps-59082`
and `ecps-62506`.

### Kept sample

For all six sampled rows, current source identity and pin equal the current
report, the report carries the expected disposition ID, and the compact tree
contains exactly one matching concept payload.

| Row | Literal-base pin | Current pin | Class |
| --- | --- | --- | --- |
| `ca-362-disability-shelter-cap-ecps-56995-benefit` | `298 / 205.91998291015625` | `298 / 202.60000610351562` | moved |
| `ca-362-disability-shelter-cap-ecps-58732-benefit` | `293 / 197.8203328450521` | `293 / 190.5999755859375` | moved |
| `ca-362-disability-shelter-cap-ecps-61918-benefit` | `383 / 142.97412109375` | `383 / 137` | moved |
| `ca-362-pe-student-earnings-ecps-57065-eligibility` | `false / true` | `false / true` | unchanged |
| `ca-362-pe-student-earnings-ecps-57392-eligibility` | `false / true` | `false / true` | unchanged |
| `ca-362-pe-student-earnings-ecps-58015-eligibility` | `false / true` | `false / true` | unchanged |

### Checker change and coverage

The checker change does not weaken validation:

- `scripts/reconcile_ca_snap_423_dispositions.py` is tracked and read-only.
  It resolves the explicit `--base-ref` to a commit, requires the literal blob
  hash and 345-row identity digest, and validates the complete partition and
  movement identity digests.
- It validates the current 529 canonical mismatches, 288 expanded
  annotations, all 7,101 exact `id/r/h/m` compact cases, source/served
  disposition parity, current runtime provenance, kept pins, and the complete
  requested-month drift receipt.
- `scripts/build_ca_snap_362_dispositions.py` now requires `--base-ref`.
  Current `--check` dispatches to the new reconciler. Historical trace mode
  remains operational against hash-pinned legacy report, compact, trace, and
  expected-YAML blobs instead of incorrectly reading the retired schema from
  current files.
- The 21 dedicated builder/reconciler tests cover unsafe or missing refs,
  literal-byte drift, equal-count identity swaps, retired compact schema,
  silent annotations, missing merged-only rows, self-consistent kept-pin
  tampering, drift-pin tampering, and invalid dispatch modes.

Both tracked entry points exited 0 and emitted identical deterministic receipt
SHA-256
`2e08a890b301a6fab087fe91b89cdc4f51274365ccd51840728873968b357b54`.
The real historical saved-trace check also passed: 345 rows validated and 96
historical rows remained unexplained.

## Protected artifacts and containment

All 39 tracked paths containing `ca-snap-ecps`, `ks-tanf-ecps`, or `ssi-ecps`
are byte-identical between repair start `f0a6598e` and reviewed head
`58c6075f0`, except the two explicitly permitted California accounting-note
copies.

| Primary report | Bytes | Total mismatches | SHA-256 |
| --- | ---: | ---: | --- |
| CA SNAP | 875,499 | 529 | `d5b95f7c8f9e9a66f5146dcf82bcfe719c6433cb150217a181f4db959fe3911d` |
| KS TANF | 1,157,490 | 218 | `1132d023920d768577617e074b914cd17c89a057dd7fd893c5052454b4a33532` |
| SSI | 1,981,263 | 2,990 | `0eb73772a9220a0cd0aaeb1ec174a43fab61bf33289f56c600202a1f7128399b` |

Their case-tree Git object IDs are likewise unchanged:
`83f07db650885a0acd98ffec6c6855b48f515547`,
`dd8310123d7d386d777867410ab0caa59679161f`, and
`2eceabc8ef2f91dc591c39ae60eb5fd50c7d5aaf`.

The complete repair diff is seven paths:

- modified `PROGRESS.md`;
- modified the historical CA builder;
- added the tracked CA reconciler;
- added its two focused test modules; and
- modified the source and served copies of the CA provenance/accounting note.

No comparison config, primary report, case tree, conformance file, or other
suite artifact changed. The claim that there are no new tracked files beyond
the reconciler/accounting work is accurate in intent but imprecise literally:
the two explicitly requested focused test modules are also newly tracked, while
the accounting documents are modified rather than added. This is expected
review support, not a containment defect.

## Validation

The full requested battery passed 7/7:

| Check | Result |
| --- | --- |
| `apply_dispositions.py --check` | 82 files validated |
| `extract_grids.py --check` | grids up to date |
| `generate_affected_map.py --check` | 172 suites / 184 edges |
| `check_vacuous_gate.py --check` | 136 oracle-backed configs |
| `conformance_scoreboard.py --check` | 4 jurisdictions / 3 conformant |
| `conformance_ratchet.py --check` | no invariant regressed |
| `conformance_burndown.py --check` | 4 series / 57 points |

The focused command over builder dispatch, reconciler, dispositions, served
dispositions, and case artifacts passed `50 passed in 3.43s`. Pre/post status
was identical, `git diff --check` passed, and no tracked or cached suite
artifact changed.

## SSI truncation note

The worker's report-only note is correct:

- Merge-base `819f370b` and current local `origin/main` at `f8ea6027` both
  explicitly store/show 1,000 of 3,067 SSI mismatches in
  `dashboard_truncation`.
- The reviewed report explicitly stores/shows 1,000 of 2,990 while preserving
  the 2,990 headline count.
- The SSI compact index declares `partial: "mismatch-only"`; its six chunks
  independently close to 2,990 unique rows and 2,990 mismatch payloads.
- The real read-only checker exits 1:
  `canonical mismatch list is incomplete (1000/2990); compact parity is
  uncheckable`.
- The generator, checker, and focused fail-closed test are unchanged from local
  main.

The truncation is pre-existing, explicit, and genuinely fail-closed rather
than a silent undercount.

## Sandbox and environment disclosure

The GitNexus review workflow could create a partial local worktree index but
the sandbox denied registration at
`/Users/maxghenis/.gitnexus/registry.json` with `EPERM`. The partial generated
index was removed, leaving no tracked or untracked residue; direct diff,
caller, checker, and test inspection supplied the review evidence instead.
No validation command required network access, and no other sandbox permission
failure occurred.

Recommendation: approve the repair round.
