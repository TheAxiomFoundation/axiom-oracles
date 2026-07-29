# PROGRESS — blind review of axiom-oracles PR #424

## State

- Review worktree: `.git/review-worktrees/pr424-b8fc73f-blind`
- Local review branch: `review/pr424-b8fc73f-blind`
- GitHub PR: `TheAxiomFoundation/axiom-oracles#424`
- Verified PR base: `main` at `f8ea6027984b9da73c6f4b58d15a20b450181ac4`
- Verified PR head branch: `fed-parity/ca-bbce-mappings`
- Verified immutable PR head: `b8fc73f06b48dffce269573af35653386dd84f81`
- Rules: read-only toward the PR branch, remotes, and GitHub; all review
  artifacts and commits stay on the local `review/...` branch.
- Output: `REVIEW-REPORT.md`
- Verdict: pending evidence.

## Done

- Read the `gitnexus-pr-review` workflow.
- Queried GitHub read-only metadata and matched the GitHub head SHA to both the
  local head branch and the origin-tracking ref.
- Created this disposable review worktree directly from the immutable PR head.
- Independently re-queried GitHub metadata and diff on 2026-07-28: PR #424 is
  open, has base `f8ea6027984b9da73c6f4b58d15a20b450181ac4`, head
  `b8fc73f06b48dffce269573af35653386dd84f81`, one commit, one changed file,
  and the fetched patch matches the local target ref.
- GitNexus change/impact/context tools are not exposed in this session. The
  patch is registry YAML with no changed code symbols, so blast radius will be
  checked through the registry parser, exact-set tests, and direct consumers.
- Containment is exact: `f8ea6027..b8fc73f0` changes only
  `axiom_oracles/bridges/mappings/us.yaml` (130 insertions), and
  `git diff --check` passes.
- Parsed all 11 mapping YAML files and loaded the packaged registry: 4,742 raw
  rows, 4,741 legal IDs plus one prefix fallback, zero duplicate legal IDs.
  The reviewed set resolves to 17 exact records: one `parameter_value` and 16
  `not_comparable` records, with P4 on every non-comparable record.
- Focused registry/coverage tests pass: 402 passed.
- Full registry battery
  (`tests/bridges tests/test_federal_tax_liability_generator.py`) on the PR
  file produced 5 failed, 1,268 passed, 33 skipped. Replacing only `us.yaml`
  with the base blob produced the identical five CA/IL/NY/OH failures and the
  same pass/skip counts. The PR file was restored with
  `git show HEAD:axiom_oracles/bridges/mappings/us.yaml > ...`; its blob hash
  again matches HEAD and the worktree is clean.
- Sandbox note: the first `uv run` attempt could not write its default
  `~/.cache/uv`; a second offline attempt could not download PyYAML. Tests ran
  successfully through an existing local project virtual environment.

## Next

1. Audit the comparable mapping against PolicyEngine US 1.767.3 and house style.
2. Adversarially audit all 16 `not_comparable` rows and named candidates.
3. Cross-check exactly 17 legal IDs against the two RuleSpec public surfaces.
4. Write and commit `REVIEW-REPORT.md`, update this ledger, and issue a verdict.
