# PROGRESS — WIC concept citation honesty

## State

- Branch: `z1-wic-citation`, based on `origin/main` at `98dfa9e`.
- Decision: relabel the public concept to `us:programs/wic#eligible`. Keep
  execution addressing separate by targeting the real RuleSpec output
  `us:policies/usda/wic/eligibility_pipeline#wic_eligible`, merged on
  `rulespec-us` `origin/main` and grounded in 7 CFR 246.7(c)-(e).
- Verification discipline: audit every statute/regulation concept ID, prove zero
  numeric changes byte-for-byte, and run the test suite exactly once.
- Implementation: committed as `579228c0`.
- Test suite: frozen after one collected full run: 2,096 passed, 59 skipped,
  6 failed. The five bridge failures read a detached, stale sibling
  `rulespec-us` checkout; the dashboard-loader failure is blocked DNS for an
  uninstalled `esbuild`. No failure concerns WIC or a changed file.
- Publication: final report in preparation; branch not yet pushed.

## Done

- Confirmed the starting worktree was clean and matched `origin/main`.
- Created the requested branch.
- Reviewed issue #401 and PR #406. `ProgramMapping.standard` is the public
  comparison/report label; `targets.axiom` is the Axiom result address.
- Traced the WIC consumers:
  - `Concepts.WIC_ELIGIBLE` has no direct call sites;
  - PolicyEngine remains addressed as `is_wic_eligible`;
  - ACCESS NYC remains addressed as `S2R022`;
  - no tracked comparison report contains the WIC concept ID;
  - `dashboard/public/data/programs.json` is the sole tracked derived consumer.
- Confirmed that 42 USC 1786 remains absent from the current axiom-corpus
  inventory, while the WIC composition target exists in current RuleSpec.
- Completed the scoped citation-path sweep. After overlaying the SNAP relabels
  owned by open PR #406, the only unresolved scoped concepts are the two
  26 USC 3111(a)/(b) leaf IDs (their parent section resolves). The broader
  known remainder is the three Massachusetts 106 CMR block paths, outside these
  two scoped files. Both groups are handled in other lanes.
- Built a repo-local GitNexus graph and reviewed the affected mapping,
  comparison, runner, and report flows. The graph reports broad critical reach
  for changing `ProgramMapping` itself; this task changes one data row only, so
  the contained risk is label selection plus three engine target lookups.
- Relabeled `Concepts.WIC_ELIGIBLE` and the mapping key to
  `us:programs/wic#eligible`.
- Repointed `targets.axiom` to the exact current RuleSpec composition output;
  PolicyEngine and ACCESS NYC targets are byte-identical to the baseline.
- Migrated the WIC row in `dashboard/public/data/programs.json`. An isolated
  run of `sync_programs.py` against the sole `rulespec-us` WIC module reproduced
  the committed row exactly: encoded, with one federal coverage path.
- Added a focused regression test pinning the public label and all three engine
  addresses. Targeted result: 1 passed, 46 deselected.
- Completed two independent no-number checks:
  - exact declared transforms of the three production files reproduced every
    working-tree byte (sha256 `728d74d…`, `7b143530…`, `d7ba510c…`);
  - all non-WIC dashboard rows and all non-address WIC fields are equal.
- Confirmed byte-for-byte that no comparison report, case chunk, disposition,
  or conformance artifact differs from the pre-implementation commit.
- Confirmed the dashboard overview remains current (215 reports); it does not
  inventory `programs.json`.
- Committed the implementation as `579228c0`.
- Attempted the PR #406 `uv run` launcher. It exited before collection because
  the sandbox cannot write the uv cache; zero tests ran in that attempt.
- Ran the full suite exactly once with the existing environment:
  `.venv/bin/python -m pytest tests/ -q`.
  Frozen result: 2,096 passed, 59 skipped, 6 failed in 647.36 seconds.
- Diagnosed the frozen failures without rerunning:
  - five bridge contracts selected the sibling `rulespec-us` checkout at
    detached `c3e1c3ad`, behind its `origin/main` `ecb057ef`; all five relevant
    RuleSpec/fixture paths changed between those commits;
  - the dashboard loader invoked `npx esbuild`, but no local esbuild executable
    exists and registry DNS is unavailable;
  - none of the five failing test files, their mapping registries, or the
    dashboard loader changed on this branch.
- Preserved the legacy import-planner caveat: default CLI composition still
  derives imports from canonical labels rather than `targets.axiom`. WIC was
  already unrunnable through that path because no `42/1786` RuleSpec module
  exists; the mapped runner output address is now correct. A generic planner
  refactor is outside this citation-label task.

## Next

1. Commit the frozen verification record and `OUTPUT.md`.
2. Push the branch.
3. Open a draft PR referencing #401.
4. Record the publication URL in both progress files and push that final commit.
