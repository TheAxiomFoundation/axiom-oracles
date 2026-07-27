# PROGRESS — WIC concept citation honesty

## State

- Branch: `z1-wic-citation`, based on `origin/main` at `98dfa9e`.
- Task: determine whether `us:statutes/42/1786#wic_eligible` is used as a
  resolvable citation key or only as a concept identifier, then apply the honest
  corpus-aware fix.
- Verification discipline: audit every statute/regulation concept ID, prove zero
  numeric changes byte-for-byte, and run the test suite exactly once.
- Test suite: not run.

## Done

- Confirmed the starting worktree was clean and matched `origin/main`.
- Created the requested branch.

## Next

1. Review issue #401 and PR #406 precedent.
2. Trace consumers of concept IDs and citation addressing.
3. Resolve every statute/regulation ID against the citation corpus.
4. Implement the WIC relabel if it is label-only.
5. Compare numeric artifacts byte-for-byte, then run the test suite once.
6. Write `OUTPUT.md`, push, and open a draft PR referencing #401.
