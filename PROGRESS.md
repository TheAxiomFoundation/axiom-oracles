# PROGRESS — WIC concept citation honesty

## State

- Branch: `z1-wic-citation`, based on `origin/main` at `98dfa9e`.
- Decision: relabel the public concept to `us:programs/wic#eligible`. Keep
  execution addressing separate by targeting the real RuleSpec output
  `us:policies/usda/wic/eligibility_pipeline#wic_eligible`, merged on
  `rulespec-us` `origin/main` and grounded in 7 CFR 246.7(c)-(e).
- Verification discipline: audit every statute/regulation concept ID, prove zero
  numeric changes byte-for-byte, and run the test suite exactly once.
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

## Next

1. Implement the WIC label/address split and migrate its dashboard metadata.
2. Add a focused regression test for the public ID and Axiom target.
3. Prove the implementation is exactly the declared byte transformation and
   that every comparison/conformance numeric artifact is byte-identical.
4. Run the full pytest suite once; do not run or regenerate comparison suites.
5. Write `OUTPUT.md`, push, and open a draft PR referencing #401.
