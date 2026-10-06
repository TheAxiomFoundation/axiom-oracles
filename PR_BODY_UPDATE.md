## Why

The SNAP QC suites never execute in CI. `comparisons.yml` and `affected-rerun.yml` send them to runners that have no engine binary and no QC public-use file. On those runners `scripts/run_comparison.py` re-emits the committed dashboard report (`provenance.reemitted_report: true`), and the leg passes.

That is how California's replay went unnoticed after it stopped compiling. rulespec-us#1176 (2026-07-30) added an import the CA FY2024 overlay didn't rewrite. The engine then rejected the chain with `duplicate derived rule snap_net_income_limit_100_percent_fpl_48_states_dc`.

#548 fixed the overlay and refreshed the six dashboards from local runs. This PR is the CI side: a lane that actually runs the suites and fails when one breaks.

## What

**`.github/workflows/snap-qc-replay.yml`** runs Mondays at 07:17 UTC and on demand. Dispatch takes optional `suites` and `rulespec_us_ref` inputs.

- **prepare**
  - Resolves one rulespec-us commit (`main` unless dispatched otherwise).
  - Reads `axiom_artifact_rules_engine_ref` from rulespec-us `.axiom/workflow-toolchain.toml`. That is currently ffd8213, the pin `program-artifacts.yml` also builds.
  - Builds the engine with `cargo build --release --locked --bin axiom-rules-engine`. The binary is cached as `axiom-rules-engine-release-<ImageOS>-<ref>` and rebuilt on a cache miss.
  - Fetches the PUF pinned in `SNAP_QC_PINS`, using the loader's browser headers. The zip is cached under a key derived from the pin's URL and sha256, and it is re-verified against the pin before every extraction.
  - Selects the suites.
- **replay** (matrix, `fail-fast: false`)
  - Checks out rulespec-us at the resolved SHA into a directory named `rulespec-us`. The overlay stages the tree under that basename. The pinned engine serves `us:` imports only from a root named `rulespec-us` (or `rulespec-us-<suffix>`), so under any other name the staged copy cannot supply its own imports.
  - Runs `run_comparison.py <suite> --summary --require-live`.
  - Runs `snap_qc_replay.py check`, even if the replay step failed.
  - Uploads the report and the replay log.
- **live-tests** runs two tests that skip everywhere else, and fails if either skips:
  - `test_live_fy2024_row_counts`, which needs the PUF;
  - `test_live_engine_reproduces_worked_example`, which needs the engine and rulespec-us.

Every job selects `ubuntu-24.04` rather than `ubuntu-latest`, so a cached engine binary is never restored on a different Ubuntu release. Nothing is committed; the point is a failing check.

**`run_comparison.py --require-live`** exits nonzero when a runner marks its output as a re-emission. It exits before `run_comparison.py` publishes a report or dashboard copy. A generator that wrote its own files before failing is not rolled back. The runners that mark a re-emission are snap-qc, euromod, gettsim, and us-tariff; the UK case-grid fallbacks do not mark one, so the flag does not catch them (see "Not in this PR").

**`scripts/snap_qc_replay.py`**

- `suites` chooses what runs.
  - `REQUIRED_SUITES` (CO, NY, CA, AZ, GA, MD) run unless a dispatch narrows the selection. If a selected required suite's composition has moved, its leg fails instead of leaving the matrix.
  - `PENDING_SUITES` holds TX. Its composition is absent from rulespec-us main (rulespec-us#888; PR #891 is open and conflicting). TX joins automatically, with a warning annotation, once the composition exists.
  - A test fails CI if a registered `snap-qc-compare` suite appears in neither list.
- `fetch-puf` wraps the new `populations/snap_qc.fetch_pinned_puf`.
- `check` fails the leg unless all of these hold:
  - the report was not re-emitted;
  - the replay log records `Wrote: <this report>` and no failure, which proves the logged run produced it;
  - it has at least one case, and every case was compared;
  - benefit mismatches, error cases, and error rows are all zero;
  - the report lists every stage concept the suite's replay compares, the benefit included, and repeats none. The expected ids come from the bridge's new `stage_concepts(jurisdiction)`, which uses the same overlay-rewritten output-id map as the replay and needs no engine, checkout, or QC file. A report with an empty or partial `concepts` list therefore fails; before this, one with 856 cases, 0 mismatches, and empty `concepts`/`aggregates` passed;
  - every stage concept was compared on every case, with no divergence and no missing side (a stage can diverge while the benefit matches, and `summary.mismatch_count` counts only benefit mismatches);
  - it records the resolved rulespec-us SHA and the provisioned engine binary.

  The failure annotation names the suite and each failed check. It then shows the first benefit-mismatch cases or the replay's exception. The report has no per-case rows for a stage-only divergence, so that failure shows only as counts.

**Docs**: playbook §10 and a pointer in `comparisons/README.md`.

## Verification

**GitHub runners.** The trials ran on a throwaway branch (`ci/snap-qc-live-replay-trial`) that adds only a 3-line `push` trigger. They predate this revision (the UK split and the `check` hardening).

- [35809329469](https://github.com/TheAxiomFoundation/axiom-oracles/actions/runs/35809329469) ran fe869127b, the PR head after the rebase onto #548. **Every job passed.** `prepare` downloaded and verified the August PUF and restored the cached engine. Both live tests passed, and all six legs passed `check`: CO 856, NY 847, CA 883, AZ 922, GA 945, and MD 722 cases.
- Before #548 merged, [35803990816](https://github.com/TheAxiomFoundation/axiom-oracles/actions/runs/35803990816) and [35805686741](https://github.com/TheAxiomFoundation/axiom-oracles/actions/runs/35805686741) passed prepare, the live tests, and five legs.
  - The CA leg failed on the real regression, with the annotation *SNAP QC replay failed: ca-snap-qc* carrying the duplicate-derived-rule error.
  - snapqcdata.net served the pinned zip to a GitHub IP.
  - The engine built in about 20–30 s.
  - Run 35803990816 carried the runner notice that `ubuntu-latest` moves to Ubuntu 26 from 2026-10-19, which is why the image is pinned.

**Local rehearsal**, also before this revision, ran the same step sequence against rulespec-us main `f43dec52`, engine ffd8213, and the August PUF (zip sha256 `b8b29b85…`):

| suite | result |
| --- | --- |
| co-snap-qc | PASS: 856/856 benefit-exact, every stage exact |
| ny-snap-qc | PASS: 847/847 |
| ca-snap-qc | PASS: 883/883 |
| az-snap-qc | PASS: 922/922 |
| ga-snap-qc | PASS: 945/945 |
| md-snap-qc | PASS: 722/722 |
| live tests | 2 ran, 0 skipped |

**Negative paths**, exercised locally or in tests:

- `--require-live` with no data refuses and publishes no report.
- A re-emitted report fails `check`.
- A report left over from an earlier run fails `check`.
- A tampered report fails with the case named. This covers a benefit mismatch, a stage-only divergence, a missing side, and count drift.
- A report with no stage concepts fails `check`, as does one listing only some of them. The partial-list test is exhaustive over all 64 subsets of Colorado's six stages, and only the full set passes. A repeated concept id also fails, so a clean duplicate row cannot shadow a divergent one.
- A corrupted cached zip is discarded and re-downloaded.
- The validation pin af6e4ea, run locally, rejects the chain (`declares removed plural corpus_citation_paths`), which confirms the artifact pin is the right one.

**Review.** Two independent GPT-6 Astra reviews:

- The first found no false-green or silent no-op path in the workflow. It flagged the UK fallback gap. The fix for that is now split out; see "Not in this PR".
- The second audited every mechanism claim in the docs, comments, commits, and this description. Its corrections are applied.

Two further independent reviews of fee2fc5c found two problems, and this revision addresses both:
- The UK grid re-emit marking churns the affected-rerun lane, so it is split out.
- `check` passed a report whose `concepts` and `aggregates` were empty. It now fails.

**This revision, checked locally:**

- **The stricter `check` passes the reports real replays committed.** The seven committed SNAP QC dashboard reports came from real replays; six of them were later re-emitted by the affected rerun. Each lists exactly the concept ids `stage_concepts` computes. `check_report` finds nothing wrong with any of them except the re-emission flag on those six. CO's report is not a re-emission, so it passes with no failures. A differential test pins the concept ids, though not the pass result, for every registered suite. No live run has used the new check yet.
- **The UK split keeps the affected-rerun lane as it is on main.** The simulation made each generator fail, with a `uv` stub exiting 1 and again with no `uv`. That matches the lane itself: in affected-rerun run 36166565194, the uk-vat generator raised `FileNotFoundError: 'axiom-rules'`, and the leg reused the committed report and passed. The simulation then ran `run_comparison.py` for all 10 UK grid suites against a fresh rulespec-uk clone at main `94fa5875` and ran `select_affected_suites.py` with that HEAD unchanged.
  - At fee2fc5c, all 10 suites were re-selected with "rulespec-uk: report ran against unknown SHA".
  - At this head, none were: the reports record `94fa5875` and no re-emission, the same as main.

`ruff check` is clean. New tests:

- `tests/test_snap_qc_replay.py` (43 cases);
- 2 `--require-live` cases in `tests/test_run_comparison.py`;
- 4 `fetch_pinned_puf` cases in `tests/test_snap_qc_population.py`;
- 7 `stage_concepts` cases in `tests/test_snap_qc_compare.py`, one per QC jurisdiction.

Together with the rest of those four files: 207 passed, 2 skipped (the two live tests).

## After merge

The weekly run should pass all six suites and the live tests against current main.

## Not in this PR

- **UK grid re-emit marking.** This is split out of the PR. The affected-rerun legs have no `axiom-rules` engine, so the UK grid generators fail there and reuse the committed report. If that fallback were marked as a re-emit, the report would record a null rulespec-uk SHA. `select_affected_suites.py` would then re-select the 10 UK grid suites on every sweep, and the bot would commit a `generated_at`-only refresh each time, the same churn us-tariff shows. The marking belongs with the `ci: manual` routing for those suites in #555 (d301). Until then, `--require-live` does not catch a UK grid fallback, and nothing in this PR runs a UK grid with it.
- **SNAP QC re-emissions on the affected rerun.** The affected rerun overwrites these real reports with re-emissions on every sweep. Within hours of #548 it had re-emitted over NY, CA, AZ, and MD on main (`reemitted_report: true`, run kind `affected-rerun`), even though rulespec-us main had not moved from `f43dec52`.

  The cause:
  - `comparisons/affected_map.json` maps each snap-qc suite to `rulespec-us` plus a per-state `rulespec-us-<st>` repo.
  - The replay reads the state layers from the monorepo's `us-<st>/` directories, so a report records only the rulespec-us SHA.
  - `select_affected_suites.py` therefore selects every suite with "rulespec-us-<st>: report ran against unknown SHA".
  - The leg's runner has no engine or PUF, so it re-emits.

  In run 35786994281, the MD and GA legs were cancelled after about 90 minutes of push retries.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

