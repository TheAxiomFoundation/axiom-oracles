VERDICT: pending targeted test completion
HEAD: 8eca4516450f2a4bbeceb9f4298360f8b9e83bc8

## Blockers

None found in the code, restoration, or merge audits. Targeted pytest run is still in progress.

## Majors

None found.

## Minors

- Documentation still describes pre-merge behavior. `comparisons/README.md:62` says UK grid fallbacks lack the marker, although #549 now marks them. Its lines 258–260, `docs/snap-qc-oracle-playbook.md:464`, `.github/workflows/snap-qc-replay.yml:5`, and `scripts/snap_qc_replay.py:4` still describe the ordinary weekly/affected workflows dispatching SNAP QC. Update these passages to say that those workflows skip the seven manual suites, the dedicated live workflow executes them, and UK fallbacks receive the shared protection. The PR body's UK-interplay paragraph is also outdated. These are documentation defects, not observed execution defects.

## Tests run

All local commands use the workspace `.venv`, with `UV_CACHE_DIR` and `TMPDIR` beneath `.review-tmp`. The initial plain `uv sync --extra dev` failed because its default cache is outside the writable sandbox; retrying with the workspace cache passed.

- `uv sync --extra dev` with workspace cache → passed.
- `uv run pytest -q tests/test_affected_map.py tests/test_run_comparison.py tests/test_guard_reemitted_reports.py tests/test_commit_refreshed_report.py tests/test_provenance.py tests/test_snap_qc_replay.py` → pending; log `.review-tmp/targeted-resumed.txt`. The new `test_reemission_never_replaces_a_real_report` has passed, including its real local push and checks of the pushed tip; the older integration scenarios are still running.
- Additional UK integration probes: `.venv/bin/python -m pytest -q .review-tmp/provenance-audit/test_uk_interplay.py --basetemp=.review-tmp/provenance-audit/pytest-temp` → 20 passed. All ten actual UK grid configurations preserve real dashboard bytes on forced generator failure; their output is marked and has a null rulespec SHA. `--require-live` refuses before report publication.
- `.venv/bin/python .review-tmp/provenance-audit/check_map_interplay.py` → passed. Checks all seven SNAP suites, both pinned suites, 37 UK fresh/stale pairs, and unchanged non-SNAP map entries.
- `uv run python scripts/<name>.py --check` → all eleven passed: `generate_affected_map`, `check_vacuous_gate`, `generate_dashboard_overview`, `exercise_census`, `conformance_scoreboard`, `conformance_burndown`, `apply_dispositions`, `generate_chunk_indexes`, `unexplained_ratchet`, `conformance_ratchet`, `closure_universe`.
- `uv run python scripts/certify.py --check --program <program>` → all three passed: `dk/boerne-og-ungeydelse`, `us-co/snap`, `us/tariff-duty`.
- `bash -n scripts/commit_refreshed_report.sh` and `git diff --check` → passed.
- `gh pr checks 552 -R TheAxiomFoundation/axiom-oracles` → `test` and `gettsim-live` both pass on the reviewed head (run 36343427826).

Gate logs and timings are in `.review-tmp/gates-resumed/`. The disposition check's expired `be-worker-ssc` advisory is non-failing. The scoped certificate checks needed no DE download; the pinned aarch64 host archive is already available locally.

## Merge-from-base check

Reviewed the full net diff against merge base `fc3ce90de39d702b5ec3981a4e170d03a488b6eb`. No repository-local AGENTS.md or CLAUDE.md is present; applicable ancestor instructions were read. PR body, comments, and current checks were read without GitHub mutations.

- `658845978`: all 24 PR-only files retained; all 58 main-only changes retained. The twelve overlaps resolve exactly as documented: six real reports from the PR, six derived files from main, subsequently regenerated in `ff78a90c8`.
- `9b439203e`: 32 PR-only and 14 main-only files retained; all four overlaps equal independently reconstructed clean three-way merges.
- `8eca45164`: 30 PR-only files retained; all six #569 overlaps equal independently reconstructed clean three-way merges.
- Normalized added/deleted lines for all 24 non-data net patches match the earlier reviewed `b0b561ac` patches exactly. No dropped or reverted fixes found.

#569's declared-root discovery remains restricted to `axiom-oracles-compare`; SNAP QC still records the bridge's actual checkout. Its explicit re-emission marker remains independent of root/pin metadata and always nulls report SHAs. Pinned suites compare against their pin, not moving HEAD. Generated map changes are exactly the seven SNAP QC rows, each with only rulespec-us and `name: null`. UK fallback behavior composes with both dashboard and commit-time guards; `--require-live` remains before publication.

## Judgment flags

No new published finding or computed number is introduced. NY/CA/AZ/GA/MD blobs exactly equal `ff551a95b`; TX exactly equals `a1a22f1fe`. All report fields outside provenance are unchanged from base. TX correctly restores its July run and May oracle pin.

Recursive JSON audits constrain derived differences to the seven SNAP freshness entries plus the generation timestamp, six overview provenance/source-hash entries, six census report hashes, and the three census-pinning certificate hashes. All changed hashes match their actual source bytes.

No money, legal, people, release, or outside-send decision is implicated. The operational merge procedure remains necessary: the workflow is currently `disabled_manually` and both queued/in-progress run lists are empty. After merging, re-enable it and verify the next sweep preserves the six report blobs. No merge, push, comment, approval, or change request was sent to GitHub.

## Summary

Source and data audits found no blocker or major. Only documentation drift remains; targeted pytest completion is outstanding. This review adds only this report and local review evidence, preserving the reviewed product files.

The requested commit was attempted but blocked by the sandbox: Git cannot create `/Users/maxghenis/TheAxiomFoundation/axiom-oracles/.git/worktrees/20260927-151124-nr-or552-rev2/index.lock` outside the writable workspace. No commit was created; the report remains in the assigned workspace.
