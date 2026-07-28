VERDICT: APPROVE

# Round-2 adversarial review — `triage/ca-snap-441`

Reviewed exact target head
`9de6c1cbf1f5849ce1348d8ef715e6dcf74f4533` in the detached disposable
worktree `.git/review-worktrees/ca-snap-441-9de6c1cb-round2`. The merge base
remains `86be77210aa03da867a6103558cb57fe51a2ba55`. No target-branch, remote,
GitHub, or PR state was changed.

All four round-1 blockers are closed.

## Replay digest

The published replay block was run verbatim, including its exact worktree,
cached runtime overlay, base ref, output path, shell SHA-256 gate, and builder
`--check`.

- Traced: 361 households / 441 rows.
- Trace SHA-256:
  `c46af9b87c8f5ad01f1909bc45e80e00b4c4a50e5b802ea4ccbe194b5954b568`.
- Builder: 341 evidence-pinned issue-362 rows / 100 remaining unexplained.
- Diagnostic split: three genuine PE-US 1.767.3 closures / 74 persistent
  Axiom-higher mismatches.
- Exit status: zero; the literal hash test and `--check` both passed.

A second independent trace from the detached review worktree reproduced the
same bytes and hash, using PolicyEngine 4.18.9, PolicyEngine-US 1.767.3,
PolicyEngine Core 3.30.3, and the pinned Populace artifact.

## Live counterfactual digest

Reviewer seed: `20260728` via Python 3.13 `random.Random`, distinct from round
1's `362441`.

The two removed cases correctly remain unexplained:

| Case | Exhaustive live result |
| --- | --- |
| `ecps-59082` | Annual and January zero-SE, zero-TANF, and joint probes all remain false / $0 versus Axiom true / $148. |
| `ecps-62506` | Best annual result is $345.120321 and best January result is $337.899963 versus Axiom $454; zero-TANF remains false / $0. |

Both cases have zero YAML entries, four canonical rows with null dispositions,
four served rows without annotations, and zero served-disposition entries.

Five sampled re-documented cases independently prove every mechanism named in
their new annotations:

| Case | Mechanisms | Closing intervention | Live PE vs Axiom | Result |
| --- | --- | --- | ---: | :---: |
| `ecps-57511` | SE + induced TANF | annual zero-SE + TANF | $1,189.629395 vs $1,183 | pass |
| `ecps-58210` | January + SE + induced TANF | January zero-SE + TANF | $1,355.599976 vs $1,355 | pass |
| `ecps-58771` | SE + induced TANF | annual zero-SE + TANF | $549.059814 vs $546 | pass |
| `ecps-59120` | January + SE + induced TANF | January zero-SE + TANF | $946.900024 vs $946 | pass |
| `ecps-60323` | January + SE | January zero-SE | $979.900024 vs $979 | pass |

All self-employment and TANF source alignments are within $0.10. The three
sampled period cases fail the corresponding annual intervention before the
January intervention closes, and zeroing self-employment induces the stated
TANF before the joint intervention in every sampled induced-TANF case.

Five additional bridge cases were randomly selected from 216 eligible current
bridge cases after excluding all 28 round-1 samples and the 16 challenged
cases:

| Case | Mechanism | Live PE vs Axiom | Delta | Result |
| --- | --- | ---: | ---: | :---: |
| `ecps-57788` | SE | $590.649129 vs $584 | +$6.649129 | pass |
| `ecps-59827` | TANF | $186.584778 vs $182 | +$4.584778 | pass |
| `ecps-60519` | January | $470 vs $469 | +$1 | pass |
| `ecps-60935` | TANF | $416.384806 vs $412 | +$4.384806 | pass |
| `ecps-61816` | TANF | $314.684733 vs $310 | +$4.684733 | pass |

Requested sample result: 2/2 removals confirmed, 5/5 re-documented mechanisms
confirmed, and 5/5 new bridge cases passed.

## Drift-note spot checks

Seeded persistent rows `ecps-60310`, `ecps-58756`, and `ecps-58656` remain
plain unexplained on every surface. Direct-January PE-US 1.767.3 is,
respectively, $636.099976 versus Axiom $1,183, $414.099976 versus $762, and
$403.299988 versus $636; eligibility matches and every miss remains above $7.

Closure spot-check `ecps-59207` is accurately recorded: stamped PE is
$853.653890, direct-January PE-US 1.767.3 is $843.50, and Axiom is $843. The
row remains intentionally unannotated. The exhaustive trace independently
reproduces the exact three-closure / 74-persistent split.

## Conservation and served parity

- Original residual set: 321 bridge + 20 upstream + 100 unexplained = 441.
- Full CA mismatch set: 243 BBCE + 321 bridge + 20 upstream + 100 unexplained
  = 684.
- All sets are pairwise disjoint and exhaustive; no issue-362 annotation lies
  outside the original 441 rows.
- Raw mismatch identities and values are unchanged from the pinned base.
- The four BBCE selectors, 243 expansions, and annotation objects are
  unchanged from round 1.
- Explorer: 7,101 unique cases, 684 exact mismatches, 584 annotated, 100
  unexplained, zero missing/obsolete/value-drifted/annotation-drifted rows,
  and zero silent classifications.
- `index.json` and `chunk-14.json` are byte-identical to round 1; chunks 0–13
  differ only in mismatch annotations.

## Checks and containment

All 13 published generated-data `--check` commands exited zero:
dispositions, CA cases, CA served dispositions, grids, boundary suggestions,
affected map, vacuous gate, overview, universes, compositions, scoreboard,
ratchet, and burn-down. The disclosed US-PE and UK-PE universe version no-ops
also exited zero. Focused replay/disposition/case-emitter tests report
`39 passed`; Ruff, compilation, and both repair/full-branch whitespace checks
pass.

The full branch contains exactly 32 changed paths: 17 CA artifacts, seven
shared regenerated conformance artifacts, seven directly supporting
implementation/test files, and `PROGRESS.md`. No unrelated suite report or
disposition changed.

## Non-blocking scope note

The shared disposition join still retains eight pre-existing, non-CA row
annotations when an entry ID remains but its selector no longer selects that
row. Summary counts correctly treat those rows as unexplained, so the visual
annotation and summary can disagree. The four affected GA/MD/ND/RI reports and
this behavior are byte/behavior unchanged from the merge base and round-1
target; current CA has no such row and reconciles exactly. Correcting those
unrelated report and case surfaces is outside the explicit CA containment and
should be tracked separately.

GitNexus reported the disposable worktree unindexed, so repository-native diff,
source, test, and generated-chain inspection supplied the code-path review.
