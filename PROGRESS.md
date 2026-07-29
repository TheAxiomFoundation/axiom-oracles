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
- Verdict: `APPROVE`.

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
- RuleSpec source is pinned read-only at
  `fed-parity/ca-bbce@8d1f31d50cfa094db9206172ee56c6fb68665e7c`
  (local and origin refs agree), based on `af6c57d6`. Its worktree has only an
  unrelated untracked `WORKER-REPORT.md`, which was excluded and untouched.
- Mechanical public-surface comparison passes exactly: the new MCE module has
  14 public rules plus one excluded `data_relation`; the FY-2026 module adds
  three public rules. The 17 expected legal IDs equal the 17 PR mapping
  additions, with empty missing and phantom sets.
- Companion YAML evidence matches the claimed boundaries: the MCE rate is
  encoded as `2.00` and asserted as `2.0`; the student output and its source
  rule are Person/Month and exercised at `2026-01`; MCE conferral requires a
  PUB 275 trigger, gross screen, household bars, and an eligible member but no
  net/asset test; separate cases exercise resource and net waivers and both
  MCE and traditional-CE zero-benefit denials.
- Comparable-row audit passes against the exact cached PolicyEngine US 1.767.3
  wheel and commit `49d19b239a593dbac8920ac6fd80cfe33372343a`.
  Runtime resolves `gov.hhs.tanf.non_cash.income_limit.gross`, reports metadata
  unit `/1`, period `year`, state breakdown, and returns CA `2` on both
  2015-10-01 and 2026-01-01. The parameter YAML has exactly one CA history
  entry (`2015-10-01: 2`), so there is no later CA change at the pin.
- The comparable record exactly follows the Pell `max_pell_limits` keyed-rate
  shape: `parameter_value`, parameter path, `parameter_key`, year period, and
  rate comparison. RuleSpec's `2.00`, companion `2.0`, inclusive 200% pass,
  and 201% fail cases establish the same boundary.
- Companion CLI execution was unavailable: one local encoder environment lacks
  `receipt`, while another rejects the nested RuleSpec worktree as a
  noncanonical root. The source and companion assertions were inspected and
  parsed directly; the PE runtime check executed successfully.
- Adversarial audit of all 16 `not_comparable` rows passes at PE-US 1.767.3.
  Runtime confirms every named candidate exists with the expected grain:
  `is_snap_ineligible_student` is Person/year; immigration is Person/month;
  TANF non-cash gross/net/asset/status and SNAP work/status/allotment candidates
  are SPMUnit/month.
- Every variable in PE's seven-file SNAP student subtree is year-defined; no
  month-scoped student judgment exists. RuleSpec's student exclusion and its
  imported source are Person/Month, so the recorded period boundary is real.
- PE's TANF non-cash status formula is exactly gross AND net AND asset. The
  gross candidate is a ratio pass/fail predicate, asset is a test outcome
  under CA's infinite limit, and net actively applies in CA for both household
  categories. None represents the legal Money ceiling, PUB-275-gated status,
  resource waiver, or net-test waiver.
- Work and immigration candidates are partial and/or opposite-polarity;
  PE's aggregate eligibility and unit-size formulas omit the RuleSpec
  same-person five-gate composite. The ordinary registry runner executes only
  direct variables, so it has no generic negation transform that would make
  those negative legal judgments exact.
- Commit-qualified PE source/class inventory and concept searches found no
  one-to-one SNAP surface for the drug-felony overlay, full household bar,
  cash-out SSI or institution exclusions, composite member inclusion, MCE
  conferral, waiver facts, or categorical zero-benefit denial. The PE
  zero-allotment path can remain eligible for households of three or more,
  confirming that its downstream status/allotment outputs are not the denial
  judgment.
- Rechecked GitHub read-only metadata immediately before verdict: the live PR
  still has base `f8ea6027`, head `b8fc73f0`, one commit, and one changed file;
  local and origin-tracking head refs still match.
- Wrote and committed the self-contained final evidence report at
  `REVIEW-REPORT.md` (`29ba017c`).

## Next

None. Review complete; issue the recorded verdict without writing to the PR,
remotes, or GitHub.
