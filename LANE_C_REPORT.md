# Lane C report — axiom-oracles / rulespec-be#118

## Summary

Implementation, live verification, and canonical repository checks are
complete. The `be-marital-quotient` suite now feeds the repaired
rulespec-be#118 couple program at its real grain: two related `Person` records
under a queried `TaxUnit`, with spouse roles and record-targeted EUROMOD
bridges. The composition artifact schema is now v2 and records that structure
generically for any suite.

Local implementation commit: `5e9c91768` (`BE: feed marital quotient Person
records`; body references rulespec-be#118 and #93/#106). Nothing was pushed.

## Exact diff surface

- `axiom_oracles/suites/be_worker.py`: replaces the two Article-89 flat
  professional-income boundaries with eight Person input records; adds the two
  spouse-to-tax-unit relation tuples; preserves all 13 TaxUnit joint/local
  facts, including every Article 126 false branch and both local rates; adds
  the imported Article 134 selector as false; and makes `yem` / `yemeq_s`
  target spouse A's gross / work-bonus reference records.
- `axiom_oracles/conformance/compositions.py`: generic serialization and
  parsing of value-free record targets, normalized relation tuples, flat or
  record-target bridge targets, and bridge transforms; schema v2.
- `conformance/compositions/be.yaml`: regenerated, never hand-edited.
- `axiom_oracles/grids/extract.py` and `tests/test_case_grids.py`: classify
  `axiom_relations` alongside record inputs as engine-projection metadata, so
  the oracle-neutral grid does not leak RuleSpec relation wiring.
- `tests/test_case_schema.py` and `tests/test_conformance.py`: exact Belgian
  structural/bridge assertions, DK record precedent, transformed bridge
  preservation, serialization round-trip, and repaired archaeology boundary.
- `scripts/generate_conformance_compositions.py`, `conformance/README.md`,
  `comparisons/be-marital-quotient.yaml`, and `docs/be-coverage-matrix.md`:
  generated-contract, comparison, and coverage documentation updated for the
  repaired program and canonical-refresh sequencing.

## Regenerated composition delta

`scripts/generate_conformance_compositions.py be` wrote 23 suite rows and its
own `be --check` passes. The marital-quotient row changes from two flat
Article-89 spouse boundaries and a flat `yem` bridge to:

- 17 unique supplied boundaries: 13 TaxUnit boundaries plus four Person-local
  boundary names;
- eight value-free Person record targets (`head` and `spouse` × gross,
  work-bonus reference, `is_spouse_a`, `is_spouse_b`);
- two ordered relation tuples (`head -> taxunit`, `spouse -> taxunit`);
- record-target bridge specs for `yem` (head gross) and `yemeq_s` (head
  work-bonus reference).

The generic fix also makes four pre-existing transformed BE bridges truthful:
birth leave and maternity leave retain `divide_by: 312`, Flemish job bonus
retains `divide_by: 12`, and unemployment retains `divide_by: 312`, instead of
the v1 generator incorrectly serializing mapping keys as boundary names.
Regenerating `conformance/be.yaml` and the scoreboard produced no content drift.
The first grid check exposed that the generic extractor omitted
`axiom_relations` from its existing projection-metadata exclusion set. After
fixing that omission and regenerating, every jurisdiction grid is byte-identical
to its committed oracle-neutral skeleton; there is intentionally no grid-file
delta.

## Live suite result and provenance

The full EUROMOD + Axiom supervised worktree comparison ran successfully in
the sandbox: 3/3 within the unchanged EUR 15 tolerance, zero mismatches, zero
engine errors.

| Case | EUROMOD | Axiom | absolute delta | bridged head gross | bridged head reference |
| --- | ---: | ---: | ---: | ---: | ---: |
| `be-marital-quotient-30k` | -808.575343646797 | -813.306092125515 | 4.730748478718 | 31650.67178502879 | 27285.06188364551 |
| `be-marital-quotient-45k` | 3484.260716878077 | 3484.259384864826 | 0.001332013251 | 47476.00767754318 | 40927.59282546826 |
| `be-marital-quotient-60k` | 7548.604137323547 | 7548.602448856045 | 0.001688467501 | 63301.34357005758 | 54570.12376729102 |

Provenance:

- rulespec-be worktree commit:
  `a0fe1c1ce8e6ff1b196f87c6480f039254cbea10` (rulespec-be#118);
- rules engine source commit:
  `c6cc389a8f5e7238019e4fa06849325fad9acd46`;
- engine binary SHA-256:
  `9452599c5ef641a30ded4ab65ced19cdfc054a667582b62ad33577a8ad787a1f`;
- x64 EUROMOD Python: EUROMOD 0.2.18, pandas 3.0.3, coreclr via
  `/Users/maxghenis/.dotnet-x64`;
- model/system/dataset/template: `EUROMOD_RELEASES_J2.0+`, `BE_2025`,
  `BE_2024_c1_2015_03_e2`, `BE_training_data`;
- raw report: `/private/tmp/be-marital-quotient-rulespec-be118.json`.

The sandbox cannot create the requested sibling
`_cape-prep/oracles-be118-roots` directory. An equivalent isolated roots
directory, `/private/tmp/oracles-be118-roots.pzaffd`, contained a `rulespec-be`
symlink to the exact requested worktree. This suite carries no policy-switch or
constant override, and the EUROMOD leg did not hit the Lane A overlay failure.

## Disposition-retirement decision

Retain `dispositions/be-marital-quotient.yaml` in this PR. The supervised
worktree run proves all three entries will become retirable, but the current
committed publication still carries the three pinned 0/3 mismatch rows. Its
re-emitted provenance has a null RuleSpec SHA, so it cannot prove freshness and
should not be silently replaced by a feature-worktree run. The dispositions
README requires entries to be deleted when their mismatch clears; the merge
machinery reports expiring entries as expired after the committed mismatch
disappears. Removing the ledger against today's committed report would instead
leave three unexplained rows, violating the suite's `unexplained_max: 0`
ratchet. Repository precedent (commit `d34aa6fa`) removes a ledger together
with a refreshed zero-mismatch report whose provenance pins the repaired
RuleSpec on merged main. No test pins a hard-coded marital-quotient disposition
count.

Therefore retirement is a follow-up affected rerun after rulespec-be#118 is on
the default branch: replace the canonical/dashboard report, delete the YAML
ledger, and remove its served mirror
`dashboard/public/data/dispositions/be-marital-quotient.json` in the same
artifact refresh.

## Verification

- Live comparison: 3 comparisons, 3 matches, 0 mismatches, 0 errors.
- Final focused pytest (`test_conformance`, `test_case_schema`, `test_case_grids`,
  Axiom adapter/tax projection, dispositions, unexplained ratchet): 350 passed,
  3 skipped.
- A pre-final-review full pytest run: 2,779 passed, 70 skipped, 12 failed.
  Eleven failures are
  `tests/test_commit_refreshed_report.py` cloning the untouched mainline
  `dispositions/us-tariff-schedule.yaml`, whose `match` keys the current
  validator rejects; one is `test_dashboard_loader.py` attempting an offline
  `npx esbuild` download (`ENOTFOUND`). Neither failure group overlaps this
  diff. The direct `apply_dispositions.py --check` failure has the same tariff
  cause.
- Ruff: full repository passes.
- Passing canonical gates: NZ IncomeExplorer, chunk indexes, exercise census,
  certificates, SNAP case/disposition artifacts, extracted grids, boundary
  cases, affected map, vacuous gate, dashboard overview, all enforceable
  conformance universes, closure universe, compositions, scoreboard,
  conformance ratchet, unexplained ratchet, and burn-down.
- `validate_bridge_manifests.py --strict` also reports unrelated default-branch
  DK manifest/registry drift (unknown 2023/couple suite names and stale DK input
  catalogs); the modified BE suite has no bridge-manifest finding.
- `git diff --check` passes. No tolerances changed.

## Merge sequencing recommendation

Merge this harness PR immediately before or atomically with rulespec-be#118.
The old flat suite cannot satisfy the repaired program, while this record-based
suite is intentionally coupled to its Person/relation interface. Once #118 is
visible to default-branch runners, trigger the canonical affected rerun and
retire the now-expired dispositions in that artifact-only follow-up.

## Open questions

- The sandbox cannot write the requested parent path
  `/Users/maxghenis/TheAxiomFoundation/_cape-prep/LANE_C_REPORT.md`; this
  worktree-side copy is maintained incrementally as the recoverable handoff.
- Whether the integration owner prefers an explicit cross-repository merge
  queue/hold between this PR and rulespec-be#118; there is no compatibility
  window where either half can safely run alone against the other repository's
  old main.

LANE C DONE
