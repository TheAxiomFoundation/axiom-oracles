VERDICT: REQUEST-CHANGES

# Blind review: `fed-parity/snap-residual-cleanup`

- Target: `6846f433dbf126249997c92cea7a3ac3c153fe13`
- Compared with local `origin/main`:
  `9b889a27432e84804938bd3b374b4f5f7466792e`
- Merge base: `105b7133f735a6dc7bd1026b4df4ce119db65469`
- Review date: 2026-07-27

The canonical five reports and disposition YAMLs contain mostly sound
case-level work, and the requested live TANF sample passed. The branch is not
approvable because browser-facing case artifacts silently retain the
classifications this branch claims to remove, the declared engine provenance
is false and not reproducible from the committed configs, and the exact head
conflicts with current `origin/main`.

## Blocking findings

### 1. Served case-explorer data silently contradicts the reports

None of
`dashboard/public/data/cases/{al,ma,nc,sc,tn}-snap-ecps/` changed from the
merge base. Those compact chunks are not inert: `dashboard/src/utils/caseData.js`
loads them, and `dashboard/src/components/Households.jsx` uses mismatch field
`e` to label and filter explained versus unexplained cases.

Independent reconciliation against the five current canonical reports found:

| State | Canonical rows | Served rows | Wrong annotations | Missing current row | Obsolete served row |
| --- | ---: | ---: | ---: | --- | --- |
| AL | 53 | 53 | 21 | `ecps-37103` benefit | `ecps-37416` benefit |
| MA | 255 | 255 | 74 | `ecps-2303` benefit | `ecps-2930` benefit |
| NC | 99 | 99 | 28 | — | — |
| SC | 181 | 180 | 116 | `ecps-29277` benefit | — |
| TN | 68 | 68 | 27 | — | — |
| **Total** | **656** | **655** | **266** | **3** | **2** |

All 138 returned categorical rows still carry
`e: "axiom_encoding_gap"` in the served chunks: 54 MA rows and 84 SC rows.
Most new #9157/#397 annotations are absent. AL `ecps-36459` retains the wrong
encoding-gap class, and new SC `ecps-29277` is absent entirely.

Thus the claims that these rows are “physically unannotated” and that no silent
classification remains are false for the dashboard users who consume these
artifacts. The existing seven `--check` gates do not detect this split-brain
state.

### 2. Engine provenance is false and not reproducible from committed machinery

The five configs correctly retain `sample_size: 0` and `period: 2026-01`.
However:

- Every committed report records PolicyEngine-US `1.767.3` with
  PolicyEngine Core **`3.28.0`**, not the claimed `3.30.3`.
- `WORKER-REPORT.md` and all 95 TANF evidence entries also say Core `3.28.0`.
- The preserved 121-case artifact records `4.18.9 / 1.767.3 / 3.28.0` and has
  SHA-256
  `084db4c17c97c3ab6ed057186b5c6df969737944013069361125499674497f66`.
- None of the five committed comparison configs declares
  `policyengine_version`, `policyengine_us_version`, or
  `policyengine_core_version`.
- Consequently, committed `_resolve_pe_oracle_pins` selects the repository
  defaults `policyengine==4.18.9`, `policyengine-us==1.752.2`, and
  `policyengine-core==3.28.0` for every suite. It does not select the
  `1.767.3` version stamped into the reports.
- The dependency paths in the configs are mutable `$HOME` checkouts. The
  clean worker snapshots and temporary `uv` shim are not committed inputs.

Preparation for an end-to-end AL rerun was attempted from a detached target
worktree. Invoking the committed runner's exact `uv` subprocess shape failed
before comparison because the sandbox denied cache initialization at
`/Users/maxghenis/.cache/uv/sdists-v9/.git`. A writable, offline
copy-on-write cache attempt was stopped after two minutes and was still
incomplete. Even with that runtime repaired, the committed config would run
US `1.752.2`, so it would not test the declared report stack. No honest byte
comparison was produced. The prompt-authorized fallback was completed: all
seven generated-chain `--check` gates passed.

### 3. The exact head conflicts with current `origin/main`

The branch is eight commits ahead and two commits behind its merge base.
`git merge-tree` reports one conflict:
`dashboard/public/data/freshness.json`, where both sides changed the
document-level `generated_at` field. The branch must incorporate current main
and regenerate freshness before it is PR-ready.

### 4. Two honesty claims are inaccurate

The minimum-benefit result is correctly zero, but the worker report calls its
six-row near-minimum table exhaustive. There are seven shared-eligibility rows
with one side at `$24` or `$23.973597`; it omits MA `ecps-2303`
(`$24` versus `$100.1699930826823`, eligibility true/true). The omitted case
still fails the exact `$24` versus `$23.84/$23.973597` criterion, so the zero
disposition count remains correct.

All 119 current disposition entries have a `linked_issue`, and there are no
duplicate case/concept selectors or cases assigned to multiple classes.
However, 14 retained BBCE entries (AL 3, MA 4, NC 3, SC 4) lack an
`evidence.sources` list; eight of those entries were modified on this branch.
Their common link, RuleSpec-US #1098, is explicitly a California/CalFresh
issue and does not track the asserted AL/MA/NC/SC mechanisms. The unqualified
“linked issue + source” claim is therefore not met.

## Independent TANF counterfactual replay

Ten exact Populace households were reconstructed and run through live,
separate baseline and state-component-plus-aggregate-`tanf=0` simulations.
Runtime: Python 3.13.9, PolicyEngine 4.18.9, PolicyEngine-US 1.767.3,
PolicyEngine Core 3.30.3, `spm-calculator` 0.3.1. Pinned Populace SHA-256:
`16be6338f9d0b3c339883dae59949e995663b64cf145de6728b3dd0f916c5d5f`.

| State / case | Axiom | Baseline PE | TANF/mo | Zero-TANF PE | Abs. delta | Eligible before/after | Result |
| --- | ---: | ---: | ---: | ---: | ---: | :---: | :---: |
| AL `ecps-36567` | 785 | 749.274170 | 344.000000 | 789.399170 | 4.399170 | T/T | PASS |
| AL `ecps-36718` | 785 | 756.474202 | 268.246114 | 789.399170 | 4.399170 | T/T | PASS |
| MA `ecps-2004` | 693 | 384.624105 | 698.784587 | 699.024170 | 6.024170 | T/T | PASS |
| MA `ecps-2012` | 785 | 715.524170 | 984.333252 | 789.399170 | 4.399170 | T/T | PASS |
| NC `ecps-27158` | 1183 | 1168.779460 | 310.333618 | 1189.629395 | 6.629395 | T/T | PASS |
| NC `ecps-28066` | 944 | 934.545492 | 55.560689 | 951.045492 | **7.045492** | T/T | **FAIL** |
| SC `ecps-28685` | 546 | 504.734782 | 358.618896 | 549.059814 | 3.059814 | T/T | PASS |
| SC `ecps-28729` | 546 | 504.434814 | 358.230754 | 549.059814 | 3.059814 | T/T | PASS |
| TN `ecps-35254` | 667 | 564.645345 | 362.034749 | 673.545369 | 6.545369 | T/T | PASS |
| TN `ecps-36247` | 938 | 772.245280 | 438.000000 | 945.195394 | **7.195394** | T/T | **FAIL** |

For every row, the state component equaled aggregate TANF and both became zero
after neutralization. All ten baselines matched the committed report values
bit-for-bit. The two sampled failures remain unannotated in both aggregate and
case mismatch records. Core 3.30.3 produced the same numeric results as the
preserved Core 3.28.0 evidence for all ten rows.

Replay output:
`/tmp/tanf_review_subset_core3303.json`, SHA-256
`3ee4052975145fdfae4118f85659738ede38e256bba09f5e28e707eb283cc5ad`.

This supports the committed 95-pass/26-fail disposition logic and confirms
that the sampled failures were honestly left unexplained.

## Claims that did pass

- Lone-minor evidence is exact: AL 4, MA 1, NC 3, SC 2, TN 2 households,
  totaling 12 households and 24 benefit/eligibility rows. Each is a
  one-person minor household with Axiom false/zero and PE true/positive.
  Eleven use the `$217,027.52` clone income; AL `ecps-37651` is the disclosed
  `$21,866.20` exception and still exceeds Axiom's one-person income limit.
  PolicyEngine-US #9157 and the cached 1.767.3 formula corroborate the missing
  parental-control predicate.
- Canonical TANF selectors exactly equal the preserved 95-pass set. All 26
  preserved failures are absent from the class.
- The exact minimum-benefit qualifying criterion yields zero cases.
- In the five canonical reports and YAMLs, the categorical rollback is exact:
  MA 27 households/54 rows and SC 42/84. The state changes reconcile to
  `+34` MA and `+52` SC, including newly generated and bridge-classified
  `ecps-29277`.
- The worker's before/after totals match the canonical data:
  655 to 656 raw rows, and 302 rows/275 households to
  324 rows/239 households unexplained.
- The PR-style three-dot diff contains exactly 16 paths: the two Markdown
  artifacts, five reports, five disposition files, the US-PE row, two US-PE
  detail mirrors, and freshness. No scripts, CI files, other conformance rows,
  suites, or state sources changed. No generation path was added to CI.
- `us-pe:snap` still has `in_scope: true` and suite `ca-snap-ecps`. Only its
  note changed. Its `23/83/71/106/41` state counts match the five canonical
  reports, and generated coverage fields are unchanged.

## Chain validation

All requested read-only checks exited zero:

| Check | Result |
| --- | --- |
| `apply_dispositions.py --check` | 83 files; consistent |
| `extract_grids.py --check` | up to date |
| `generate_affected_map.py --check` | 162 suites / 171 edges |
| `check_vacuous_gate.py --check` | 136 configs / 212 suites / 23 surfaces |
| `conformance_scoreboard.py --snapshot --date 2026-07-27 --check` | 4 jurisdictions / 3 conformant; zero snapshot updates |
| `conformance_ratchet.py --check` | 4 jurisdictions; no regression |
| `conformance_burndown.py --check` | 4 series / 49 points |

These checks establish parity for the artifacts they cover, but they do not
validate the stale compact case-explorer artifacts.

## Required changes

1. Incorporate current `origin/main`, resolve the freshness conflict, and
   regenerate the derived chain.
2. Commit the intended per-suite PolicyEngine pins, including the declared
   Core version, then regenerate all five reports from clean, immutable
   dependency snapshots. Demonstrate one end-to-end deterministic comparison.
3. Regenerate all five compact case-explorer directories from the new full
   reports. Add a check that compares their row identities and `e` annotations
   with the canonical reports.
4. Correct the minimum-benefit audit table to include `ecps-2303`.
5. Add relevant state-specific tracking issues and explicit source lists for
   the 14 retained BBCE entries, or narrow/remove those dispositions.

## Tooling and sandbox disclosures

- No remote or GitHub write was made. GitHub issue bodies were read through a
  read-only connector after direct web/`gh` access failed.
- The local GitNexus CLI reported this repository unindexed, and no connector
  graph-query tools were available. No code symbols changed, so the review
  used direct config, execution-path, and artifact tracing.
- The full-suite `uv` run failed because the sandbox denied its home-cache
  initialization. The offline cache-copy workaround was incomplete and was
  abandoned; the partially copied temporary cache could not be deleted because
  the command policy rejected recursive removal. The detached auxiliary
  worktree was removed successfully.
- The ten-case live replay succeeded without sandbox errors and left the
  committed review worktree clean.
