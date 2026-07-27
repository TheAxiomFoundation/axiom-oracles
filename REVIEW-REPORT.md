VERDICT: REQUEST-CHANGES

# Final scoped confirmation: axiom-oracles PR #407

- Target: `41512b26598858d47a306fe71f0df4e7360d9d41`
- Parent: `6fca6d194cb0e3a85e62884f683eb27e2def5dac`
- Original branch base: `105b7133f735a6dc7bd1026b4df4ce119db65469`
- Local merged `origin/main`: `9b889a27432e84804938bd3b374b4f5f7466792e`
- Review date: 2026-07-27
- Scope: only the corrected round-3/4 ledger text, its one-commit delta,
  requested read-only checks, and PR #407 body claims

The exact delta and every executable check pass, and PR #407's body is accurate.
Approval is blocked only because the newly added round-3 ledger paragraph
contains one false attribution and one causal statement that the required
history and committed ledgers do not verify.

## Blocking ledger findings

### 1. `PROGRESS.md` did not name `72718c96` as final

The new text says:

```text
this ledger described it as untracked while naming
`72718c96` as final
```

At round-3 target `1fe6bbba`, `PROGRESS.md` does call
`REPAIR-ROUND2-REPORT.md` intentionally untracked (lines 576-579), but it
contains no occurrence of `72718c96`. The final/current references to that SHA
are in `REPAIR-ROUND2-REPORT.md` itself:

```text
git grep -n 72718c96 1fe6bbba -- \
  PROGRESS.md REPAIR-ROUND2-REPORT.md

1fe6bbba:REPAIR-ROUND2-REPORT.md:8:...
1fe6bbba:REPAIR-ROUND2-REPORT.md:31:...
1fe6bbba:REPAIR-ROUND2-REPORT.md:266:...
```

Thus the sentence conflates two artifacts: the campaign ledger described the
report as untracked; the repair report, not the ledger, named `72718c96`
final/current. Round 3 also recorded that the campaign ledger omitted the
overview regeneration and stale-worker-report removal.

### 2. “by an over-broad `git add`” is unverifiable

History proves that `1fe6bbba` added `REPAIR-ROUND2-REPORT.md`:

```text
A  REPAIR-ROUND2-REPORT.md
D  WORKER-REPORT.md
M  dashboard/public/data/overview.json
```

Neither branch history, commit metadata, nor the committed round-3/4 ledgers
or reports records the staging command that caused the addition. Calling it an
“over-broad `git add`” may be an inference, but it is not a verified fact under
the requested evidence set.

An accurate replacement would say that the report was committed despite both
it and the campaign ledger describing it as untracked; that the repair report
itself named `72718c96` final/current; and that the campaign ledger omitted the
final overview and worker-report cleanup. Commit `6fca6d19` then performed the
required report removal and ledger correction.

This review does not re-raise round 4's two-path observation. Deleting the
stray repair report was the required round-3 fix, exactly as directed.

## Passing Git and ledger evidence

- `41512b26^` is exactly `6fca6d19`.
- `git rev-list --count 6fca6d19..41512b26` returns `1`.
- `git diff-tree --no-commit-id --name-status -r 41512b26` returns only
  `M PROGRESS.md`.
- The commit is docs-only: 20 insertions and 1 deletion in `PROGRESS.md`.
- Round-3 review commit `800e4b63` and round-4 review commit `9ed26ef7` exist
  at the named committed ledgers.
- All other new historical claims are corroborated: both review outcomes,
  round-3's required report removal and ledger correction, round-4's passing
  path/whitespace/overview/chain results, the external report location, and
  the final-confirmation next state.
- The external
  `snapclean-repair2-REPORT.md` is byte-identical to
  `1fe6bbba:REPAIR-ROUND2-REPORT.md`, SHA-256
  `f461bb409cb65fffd1e8f91d3fbad76e467fefe399b0f2dd7b37d9a81f48e7c2`.

## Requested checks

All Git hygiene checks exit 0:

```text
git diff --check
git diff --check origin/main..41512b26
git diff --check 6fca6d19..41512b26
```

Neither `REPAIR-ROUND2-REPORT.md` nor `WORKER-REPORT.md` appears in
`origin/main..41512b26` or in the target tree.

All thirteen generated-chain commands exit 0:

| Check | Result |
| --- | --- |
| dispositions | 83 files consistent |
| served cases | 5 suites / 656 rows / 332 annotated / 0 silent |
| served explanations | 5 suites / 119 entries / exact YAML parity |
| grids | up to date |
| boundary suggestions | up to date |
| affected map | 163 suites / 172 edges |
| vacuous/freshness | 136 configs / 213 suites / 24 surfaces |
| dashboard overview | 214 reports bundled |
| conformance universes | exit 0 |
| conformance compositions | 23 BE covered suites |
| scoreboard, snapshot `2026-07-27` | 4 jurisdictions / 3 conformant |
| ratchet | 4 jurisdictions / no regression |
| burn-down | 4 series / 49 points |

The universe check verified UK and BE. US-PE and UK-PE took their documented
clean no-op because the available local checkouts do not match the committed
pins. The battery completed in 9.55 seconds and left the worktree clean.
Review-ledger commits change only appended Markdown; all executable and data
inputs used by the battery are byte-identical to target `41512b26`.

## PR #407 body audit

The read-only GitHub result reports PR head
`41512b26598858d47a306fe71f0df4e7360d9d41`. Every requested claim matches:

| State | Before rows / households | After rows / households |
| --- | ---: | ---: |
| AL | 43 / 38 | 23 / 21 |
| MA | 49 / 47 | 83 / 55 |
| NC | 88 / 82 | 71 / 68 |
| SC | 54 / 49 | 106 / 61 |
| TN | 68 / 59 | 41 / 34 |
| **Total** | **302 / 275** | **324 / 239** |

- All five configs and reports record PolicyEngine 4.18.9,
  PolicyEngine-US 1.767.3, and PolicyEngine Core 3.30.3.
- The lone-minor class is exactly 12 households / 24 rows, all linked to
  PolicyEngine/policyengine-us#9157.
- The TANF class has exactly 121 endogenous candidates: 95 pass selectors and
  26 failures. All 26 failures remain unannotated, and the 95 applied rows link
  to TheAxiomFoundation/axiom-oracles#397.
- The complete minimum-benefit screen contains seven rows, including MA
  `ecps-2303`; none qualifies, and no #9158/#399 disposition exists.
- Exactly 69 MA/SC households / 138 rows moved from prior BBCE dispositions to
  `disposition: null`. All remain physically unannotated in canonical and
  served data, and axiom-oracles#403 tracks that exact set.
- Served artifacts contain 656 rows, 332 annotations, 119 disposition entries,
  and zero silent classifications.
- The `us-pe:snap` registration is unchanged except for its residual-count and
  pinned-runtime note.
- Issues PolicyEngine/policyengine-us#9157 and #9158 and
  TheAxiomFoundation/axiom-oracles#397, #399, and #403 all exist, remain open,
  and describe the mechanisms claimed in the PR body.

There is no PR-body finding.

## Review disclosures

- No remote or GitHub write was made. GitHub access was read-only.
- Review writes are confined to the disposable review branch and committed
  ledger under
  `.git/review-worktrees/snap-residual-cleanup-41512b26`.
- No usable GitNexus graph tool is connected. The scoped increment changes
  only Markdown, so exact Git objects, prior committed ledgers, and generator
  checks cover its relevant risk; settled SNAP implementation work was not
  re-reviewed.

## Required change

Correct the round-3 paragraph so it assigns the `72718c96` final/current claim
to the repair report, not `PROGRESS.md`, and remove or qualify the unverified
“over-broad `git add`” cause. No change is requested to the report deletion,
generated artifacts, dispositions, checks, or PR body.
