# PROGRESS — WIC concept citation honesty

## State

- Branch: `z1-wic-citation`, based on `origin/main` at `98dfa9e`.
- Decision: relabel the public concept to `us:programs/wic#eligible`. Keep
  execution addressing separate by targeting the real RuleSpec output
  `us:policies/usda/wic/eligibility_pipeline#wic_eligible`, merged on
  `rulespec-us` `origin/main` and grounded in 7 CFR 246.7(c)-(e).
- Verification discipline: audit every statute/regulation concept ID, prove zero
  numeric changes byte-for-byte, and run the test suite exactly once.
- Implementation: applied and locally verified; not yet committed.
- Test suite: not run.

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

## Next

1. Commit the verified implementation.
2. Run the full pytest suite once; do not run or regenerate comparison suites.
3. Record the frozen result and write `OUTPUT.md`.
4. Push and open a draft PR referencing #401.
