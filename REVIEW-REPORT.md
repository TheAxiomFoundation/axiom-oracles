VERDICT: REQUEST-CHANGES

# Round-3 confirmation: `fed-parity/snap-residual-cleanup`

- Target: `1fe6bbba90dbf320ed154d77eff7b22ead26731a`
- Round-2 head: `72718c962ce06385be4858b770af6d55b43bc3fa`
- Local `origin/main`: `9b889a27432e84804938bd3b374b4f5f7466792e`
- Review date: 2026-07-27
- Scope: only the two round-2 blockers, target-delta containment, whitespace,
  and the generated-chain `--check` battery

The served overview repair is correct, `WORKER-REPORT.md` is absent from the
net PR, whitespace is clean, and all 13 generated-chain checks pass. Approval
is blocked because the cleanup commit also tracks the formerly untracked
`REPAIR-ROUND2-REPORT.md`, contrary to the requested two-change delta, while
both that report and the retained campaign ledger say the report is
intentionally untracked and still describe `72718c96` as final/current.

## Blocking findings

### 1. The one-commit delta contains an unexpected tracked report

Ancestry itself is correct:

```text
1fe6bbba^ = 72718c962ce06385be4858b770af6d55b43bc3fa
git rev-list --count 72718c96..1fe6bbba = 1
```

The exact delta is:

```text
A  REPAIR-ROUND2-REPORT.md
D  WORKER-REPORT.md
M  dashboard/public/data/overview.json
```

That is 267 insertions and 312 deletions. The 266-line added repair report is
not a rename even with a 20% similarity threshold. Therefore the delta is not
limited to overview regeneration plus removal of the stale report.

The newly tracked file also contradicts its tracked state:

- lines 7-8 call `72718c96` the “Final tracked HEAD”;
- line 15 says, “This report is intentionally untracked”;
- line 31 calls `72718c96` the current result.

### 2. The retained campaign ledger was not made accurate for the cleanup

`PROGRESS.md` remains in the net PR and is byte-identical at `72718c96` and
`1fe6bbba` (blob
`381194bf1ac84803a063dc066c532047e5978c53`). Its substantive round-2 repair
facts are correct: 656 rows; unexplained counts `23/83/71/106/41`; and
PolicyEngine-US 1.767.3 / Core 3.30.3.

Its final state is not accurate after `1fe6bbba`:

- lines 462-465 require an untracked final report;
- lines 576-579 say `REPAIR-ROUND2-REPORT.md` is intentionally untracked;
- it does not record the final overview regeneration or stale
  `WORKER-REPORT.md` removal.

The earlier round-1 section is clearly historical, but it also retains
“Current committed” pre-repair counts and Core 3.28.0 wording. The appended
round-2 section supplies the corrected data; the blocking contradiction is
the report's tracked/untracked state and missing final cleanup entry.

## Passing evidence

### Served overview

`python3 scripts/generate_dashboard_overview.py --check` exits 0:

```text
overview OK: 214 reports bundled
```

Semantic comparison of the overview at `72718c96` and `1fe6bbba` finds 214
reports before and after, no additions/removals, and exactly five changed
report objects and source-size entries:

| State | Embedded rows | Unexplained | PE-US | Core |
| --- | ---: | ---: | --- | --- |
| AL | 53 | 23 | 1.767.3 | 3.30.3 |
| MA | 255 | 83 | 1.767.3 | 3.30.3 |
| NC | 99 | 71 | 1.767.3 | 3.30.3 |
| SC | 181 | 106 | 1.767.3 | 3.30.3 |
| TN | 68 | 41 | 1.767.3 | 3.30.3 |
| **Total** | **656** | **324** | — | — |

Each embedded mismatch-array length equals its summary mismatch count. The
five canonical reports also record PE-US 1.767.3 and Core 3.30.3 under
`provenance.oracle`.

### Net PR report state and whitespace

`WORKER-REPORT.md` is absent from both `origin/main` and `1fe6bbba`;
`git diff --name-only origin/main..1fe6bbba -- WORKER-REPORT.md` is empty.

Both checks exit 0 with no output:

```text
git diff --check origin/main..1fe6bbba
git diff --check 72718c96..1fe6bbba
```

### Complete generated-chain battery

All 13 checks exit 0. The existing repository virtual environment was used
directly because the disposable worktree has no separate `.venv`.

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
pins. The full battery completed in 8.63 seconds and left the review worktree
clean.

## Required changes

1. Remove `REPAIR-ROUND2-REPORT.md` from the tracked PR delta, preserving it as
   an output outside the branch if desired.
2. Update the tracked `PROGRESS.md` campaign ledger to record the overview
   regeneration and stale-report removal and to describe the final report's
   tracked/untracked state accurately.
3. Rerun the overview, diff, and 13 generated-chain checks.

No change is requested to the regenerated overview payload itself.

## Review disclosures

- No remote or GitHub write was made.
- GitNexus reported that the repository was not indexed. A local,
  no-embeddings analysis parsed the repository but could not write
  `~/.gitnexus/registry.json` under the sandbox. Its transient untracked cache
  was moved out of the disposable review worktree. Because the target commit
  changes only generated JSON and Markdown, exact Git and generator evidence
  covers the relevant blast radius.
- Round-2 served-case parity, counterfactuals, #9157 reproduction, qualifier
  screening, freshness semantics, chain details beyond `--check`, and
  containment were not redone.
