# PR #422 blind-review progress

## State

- Review status: in progress.
- Verdict: pending evidence.
- Source PR: `TheAxiomFoundation/axiom-oracles#422`.
- Verified live head branch: `fed-parity/atomic0-mappings`.
- Immutable source head: `f9fd1de2001247100b7d68db9ba59a23383fda05`.
- PR base snapshot: `8b876f6fdea5551fb00d8a98ae33e22707e17c68`.
- Review ledger/worktree: `.git/review-worktrees/pr422-f9fd1de2-blind`.
- Review branch: `review/pr422-f9fd1de2-blind` (local only).
- Final output file: `REVIEW-REPORT.md`.
- Source containment so far: one file, 17 insertions, no whitespace errors.

## Done

- Read the GitNexus PR-review workflow.
- Verified live PR metadata and diff through the read-only GitHub connector.
- Confirmed the local source branch and cached remote-tracking ref both resolve
  to the live PR head.
- Independently reverified on resume that GitHub still reports open PR #422 at
  head `f9fd1de2001247100b7d68db9ba59a23383fda05`, branch
  `fed-parity/atomic0-mappings`, base `8b876f6fdea5551fb00d8a98ae33e22707e17c68`,
  with one commit, one changed file, and 17 insertions.
- Confirmed GitHub reports one commit, one changed file, and 17 insertions.
- Created this disposable review worktree at the immutable source head.
- Confirmed source head `f9fd1de2` has the PR base snapshot `8b876f6f` as its
  sole parent.
- Confirmed the immutable source diff changes only
  `axiom_oracles/bridges/mappings/us.yaml`; `git diff --check` is clean.
- A prior attempt recorded a temporary GitNexus index/impact query. The resumed
  reviewer did not rely on that result: `npx --no-install gitnexus status`
  found no local CLI and its fallback could not reach the sandbox-blocked npm
  registry. Manual registry-consumer and focused executable coverage checks
  therefore supply the review evidence.
- Recorded the rulespec-us review target at
  `3f933cd935e68cb1cdd50a254ab449aeabe2d468` on
  `fed-parity/atomic-63c6-67h`; its existing untracked `WORKER-REPORT.md` is
  user state and will not be modified.
- Recorded the RuleSpec toolchain corpus pin
  `10142cb0f07403c2de4599c76bec01e96640fda9`.
- Independently audited section 63(c)(6) against the exact cached
  `policyengine-us` 1.767.3 wheel and `policyengine-core` 3.30.3. The only
  nearby federal surface, formula-less TaxUnit boolean/year input
  `separate_filer_itemizes`, is consumed by `basic_standard_deduction` to
  model branch (A); filing status has no alien category, the two nonresident
  alien flags are section-25A-credit-specific, no short-period/accounting-
  period surface exists, and the entity registry has no estate, trust, common
  trust fund, or partnership taxpayer entity. Estate/partnership name hits are
  estate-tax or income amounts, not taxpayer-type judgments. Therefore no
  genuine combined or per-branch B-D counterpart exists and
  `not_comparable` is the correct classification.
- Verified the retained corpus object at the exact pin: provision rows 31-35
  contain the parent and unique A-D children for married-separate/either-
  spouse-itemizes, nonresident alien, section 443(a)(1) short return caused by
  an accounting-period change, and estate or trust/common trust
  fund/partnership. The PR rationale's taxonomy is substantively accurate;
  “short-year” and “estate/trust” are only shorthand for the fuller C/D text.
- Independently audited section 67(h) against the exact PolicyEngine wheel.
  `gov.irs.deductions.itemized.misc.applies` exists with metadata unit `bool`
  and period `year`, has Python-boolean values `true` from 2013 and `false`
  from 2018 with no later override, and evaluates `False` at both ends of
  2026 under PolicyEngine Core 3.30.3. Its TaxUnit/year consumer gates the
  complete PE-modeled miscellaneous-deduction aggregate, rather than one
  expense source or only the two-percent floor.
- Confirmed the current-law intent from PolicyEngine history: OBBBA commit
  `bf338c0dcd509833c518b8ae7a87ff68064d6ece`, an ancestor of the 1.767.3
  release commit, deliberately removed the former `2026-01-01: true`
  reactivation. The parameter metadata still links the former section 67(g)
  anchor; that stale upstream anchor is non-blocking because the leaf's broad
  gate, value history, and current-law update match the retained section
  67(h) judgment.
- Verified the RuleSpec section 67(h) atom is TaxUnit/Judgment/Year, formula
  `false` from 2018, with a 2026 companion expecting `not_holds`. The exact
  retained corpus provision says no miscellaneous itemized deduction is
  allowed after 2017.
- Checked mapping house style and the loaded registry object. All 888
  repository `parameter_value` mappings omit `entity`; the new entry's
  `period: year`, `comparison: boolean`, omitted entity/unit, and comparable
  parameter target are appropriate for a global bool/year leaf feeding a
  TaxUnit/year rule. Full registry validation returns zero issues.

## Next

1. Run the changed-file coverage gate against the specified RuleSpec worktree.
2. Verify YAML, duplicate IDs, diff containment, and the clean-main failure
   baseline without using the shared stash.
3. Write and commit `REVIEW-REPORT.md`, update this ledger, and report the
   verdict without writing to the PR branch, remotes, or GitHub.
