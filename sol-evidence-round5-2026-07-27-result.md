# Round-5 semantic evidence reconciliation — result

## Outcome

PASS. The round-4 Required closure and the two explicitly promoted PARTIAL
items are implemented on branch `evidence-validator`. No changes were pushed.

The implementation is limited to semantic report/chunk reconciliation,
reference-leg gating, the two migrated Colorado evidence corpora, the latent QC
mismatch signal, skipped inline-v1 preservation, derived-mode precedence, and
strict disposition-document authorization.

## Required closure

1. Reference conformance now requires valid, bound evidence with
   `reconciliation == "full"`. Reality legs may still use honest cardinality
   evidence. The former positive reference-cardinality mutant now proves
   rejection, while a reality-cardinality control remains clean.
2. Full reconciliation now constructs canonical per-case verdicts and checks:
   concepts, outcome placement under the report's amount/eligibility tolerance
   semantics, per-concept aggregate counts, the exact report mismatch key set,
   report/chunk left and right values under the report tolerances, unique and
   non-overlapping concepts, and bidirectional compact disposition markers.
   Report disposition counts are also reconciled with mismatch markers.
3. Both suites touched by migration commit `a753d092` now use one auditable
   regeneration path. It replays authoritative compact rows from immutable
   pre-migration commit
   `6c4f17bfe6dc8224ee8251401fe0247b1117a25b`, projects current report
   dispositions bidirectionally, validates the complete staged projection, and
   rebuilds exact v1 indexes. Results:

   - `co-snap-ecps`: `bound/full`, 1,072 cases.
   - `co-snap-qc`: `bound/cardinality`, 856 cases; regeneration was
     byte-identical.
   - `ecps-spm-50970`: both report and compact row now say
     `explained_residual`; the report headline has zero unexplained mismatches.
   - `dashboard/src/components/Households.jsx` reads `m.e` for both unexplained
     counting and the explained/unexplained row label, so the explorer now
     agrees with the report.

4. `compact_case` now converts a QC producer row with `matched: false` and no
   comparator mismatch list into an explicit compact mismatch. The dashboard
   can no longer label that future row “engines agree.”
5. The mutant suite now includes the required negative cases: same-ID foreign
   values, report/chunk disposition drift in both directions, duplicate and
   overlapping concepts, rejected reference-cardinality evidence,
   later-malformed chunks, skip-with-inline-v1, and QC mismatch compaction.
6. A registry-provided `mode` can no longer overwrite the derived emitted
   certificate mode. A file authorizes disposition accounting only when it
   parses as a valid, nonempty dispositions document for the accepted suite.

## Certificate honesty

The regenerated `certificates/us-co-snap.json` reports:

- `conformant: true`;
- reference `co-snap-ecps`: `bound/full`, clean, 2,144 comparisons, 2,143
  matches, one explained mismatch, zero unexplained;
- reality `co-snap-qc`: `bound/cardinality`, clean, 856 matches and zero
  mismatches;
- overall certificate state: `unavailable`, unchanged in meaning, because the
  existing exercise-census completeness blocker remains.

Thus `conformant` remains true only after the regenerated ECPS evidence passes
the new semantic reconciliation; no gate or data was tuned around a failure.

## Verification

All named gates and directly affected checks passed:

- `scripts/regenerate_migrated_compact_rows.py --check`: ECPS
  `bound/full` (1,072); QC `bound/cardinality` (856).
- `scripts/generate_chunk_indexes.py --check`: both migrated indexes current.
- `scripts/apply_dispositions.py --check`: 76 files validated; committed
  dashboard data consistent.
- `scripts/exercise_census.py --check`: up to date.
- `scripts/certify.py --check`: up to date.
- `scripts/validate_bridge_manifests.py`: 0 errors, four pre-existing
  conservative audit-debt findings.
- Full certification mutant suite: 54 passed.
- Regeneration and comparison tests: 41 passed.
- Bot no-op test
  `test_no_changes_second_run_is_a_noop`: 1 passed.
- Ruff on every touched Python file: passed.
- `git diff --check`: passed.
- Independent final scope/correctness review: no actionable findings.

## Commits

- `dc4e5069` — start and commit round-5 progress tracking.
- `53e670cc` — require semantic reconciliation for reference evidence.
- `52712c96` — regenerate compact evidence and preserve mismatch signals.
- `887b55e4` — refresh semantic evidence certification.

## Constraints and residual risk

- The initial worktree was clean and matched cached
  `origin/evidence-validator`. A live fetch of `origin/main` was blocked by
  DNS; cached `origin/main` was
  `abe2520193439467d5fd1ada46476fc7f05d0611`.
- The regeneration audit deliberately depends on historical Git object
  `6c4f17b…`; a shallow clone without that object cannot run the audit until
  the object is fetched.
- Reports do not retain a per-case mirror of matched values. Matched rows can
  therefore be proven to the report's available semantic detail—concept,
  tolerance outcome, and aggregate counts—while mismatch rows additionally
  reconcile exact report keys, values, and dispositions.
- Copying this report to the requested ops output path was attempted and
  denied by the read-only sandbox (`Operation not permitted`). This committed
  in-repository file is the authorized fallback.
