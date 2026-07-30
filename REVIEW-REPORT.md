VERDICT: APPROVE

# PR #432 repair re-review

Target:

- Repository: `TheAxiomFoundation/axiom-oracles`
- Accepted repair start: `eee181a30885626b1c85c4273badb732d7840ba3`
- Reviewed repair head: `f268e26cb907be0e5df63e255a3e8bc084e7e31d`
- Base: `e1374eb30c582639f8f71f9bf9c22ba93b6e36f4`
- Review worktree:
  `.git/review-worktrees/pr432-f268e26cb-repair-rereview`

This pass was limited to the two requested repairs, preservation of the
accepted evidence, exact-stack replay, generated checks, and containment. The
predecessor's validated causal and authority evidence was treated as accepted
and was not reopened.

No blocking repair or containment finding remains.

## 1. PUB 275 binding is fully reverted

The bridge binds neither `household_was_issued_pub_275` nor
`household_has_online_access_to_pub_275`.

- Exact-name search across bridge code, population code, mapping data, the CA
  comparison config/fixtures, and tests finds the names only in the negative
  regression test. There is no positive, constant, composite, or alias
  binding.
- The current population-mapping blob is byte-identical to the pre-binding
  blob at `09b143aa`; its SHA-256 is
  `a0ce5e36593d483e4ceb4ce0cf16ccb2c16b256c8f141459d4d03a5a1ea73ebf`.
- Against the freshly compiled program, both leaves remain Judgment inputs,
  both report `mapped=False`, and both project through the generic unmapped
  fallback as false.
- The focused population loader suite passes: 14 tests.

The current artifact taxonomy independently recomputes to:

| Component | Rows |
| --- | ---: |
| Raw mismatches | 529 |
| Encoding-attributed | 0 |
| Bridge-attributed | 268 |
| Upstream-attributed | 20 |
| Unexplained | 241 |

Closure is exact: `0 + 268 + 20 + 241 = 529`.

The rejected exposure was removed, not relabeled:

- Base / rejected / current identity counts are `529 / 1,058 / 529`.
- The rejected state introduced 735 identities not present at base.
- Zero of those 735 identities survives in the current report.
- The current 529-identity set exactly equals the base identity set.
- The ten exposure-only selectors that expanded to 735 rows are absent.
- Canonical and compact served artifacts each contain the same 529 identities,
  with zero missing, extra, or silent classifications.

The honest 157-row PUB 275 residual remains visible as bridge attribution:
79 eligibility rows and 78 benefit rows. The identities are exactly the former
encoding set; only the mechanism changed from `axiom_encoding_gap` to
`bridge_artifact`.

## 2. Six stale served rows are repaired and pinned

At immutable snapshot commit
`c1084c2339ccc4bc41776f71b059fbabe8732916`, the six served rows are:

- four net-test rows linked to
  `https://github.com/PolicyEngine/policyengine-us/issues/9175`;
- two ACIN rows linked to
  `https://github.com/PolicyEngine/policyengine-us/issues/9176`;
- zero rows retaining the superseded net/gross source-blob links.

The snapshot byte pins reproduce exactly:

| Snapshot blob | SHA-256 |
| --- | --- |
| Source dispositions | `c68761bf21c80df448ecd36545175d2e7dd97ffc790abf6e36b921b6c4054a99` |
| Canonical report | `d2e095a5ab737f12c50c64b82d90f87377790b646382390cc0f1ab5286c26073` |
| Served dispositions | `443a8fde62070325c73c4c0e96f07eb92e978c91bf32d96cd3c9384fef2ba546` |

Independent compaction of the snapshot YAML gives exact parsed equality with
the 141-entry served snapshot. The live source and served artifacts correctly
contain none of the six retired selectors because the reverted bridge no
longer materializes those rows; the corrected links are preserved only in the
explicitly rejected, hash-pinned historical snapshot.

All three previously failing entry points now pass:

```text
scripts/emit_disposition_artifacts.py --check ca-snap-ecps
scripts/reconcile_ca_snap_423_dispositions.py \
  --base-ref 819f370bf0346e4a6a8dfb1c8c4f0d873d6d0340 --check
scripts/build_ca_snap_362_dispositions.py --check \
  --base-ref 819f370bf0346e4a6a8dfb1c8c4f0d873d6d0340
```

The live emitter reports 133 entries with exact YAML parity.

## 3. Assertions and tolerances were not weakened

- The served emitter and dependent #362 builder scripts are byte-identical
  between `eee181a` and `f268e26cb`.
- All 13 predecessor #423 test functions remain; one snapshot-byte-tamper test
  was added, for 14 total.
- `_require(...)` invocations increased from 114 to 123.
- No skip or xfail was introduced and no prior test name was removed.
- The compact-artifact, silent-annotation, equal-count partition swap,
  reclassified-selector swap, kept-pin, active-drift, retired-drift, and
  snapshot-byte tamper protections remain exercised.
- All 323 mismatch identities common to rejected and current reports retain
  identical absolute and relative tolerance fields.
- Benefit tolerance remains 7, eligibility tolerance remains 0, both relative
  tolerances remain 0, and `MOVEMENT_THRESHOLD` remains `0.005`.

The generated US-PE unexplained ratchet ceiling transparently returns from 195
to 244 because 195 depended on the rejected universal-issuance premise. That
is the required honest ledger restoration, not a comparison-tolerance or
artifact-assertion relaxation.

## 4. Required historical evidence is preserved honestly

Both #423 eras are internally exact:

| Era | Vanished | Current but dropped | Reclassified | Kept | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Honest live state | 192 | 22 | 0 | 131 | 345 |
| Rejected PUB 275 snapshot | 156 | 17 | 41 | 131 | 345 |

The complete 22-row requested-month drift receipt:

- appears in both eras;
- serializes to 9,033 bytes in each;
- is byte-for-byte identical between them;
- has SHA-256
  `fa54f6fdf05592da62c3c03b74264a4dfb7d9828e4f33ea169e75fc033ad3a51`.

The rejected snapshot separately retains the 41-row replacement receipt
`e70a713f5610eb393432df046fc8386c43cde3255769f9547ce939674b46373e`
and its `20 paired eligibility / 20 paired benefit / 1 benefit-only` split.

Both PolicyEngine issue links remain in the canonical US-PE ledger. Its
framing is accurate after the revert: the issues are independently verified
on the pinned stack, but the corrected bridge cannot currently expose them
because the household MCE gate is unobserved. In particular, it does not imply
that #9175's 723-row net-test class was measured in the current run.

## 5. Fresh exact-stack replay matches the committed state

I independently re-composed, compiled, and replayed the full CA suite from
clean inputs:

- RuleSpec-US:
  `edc62ea566a617cf5b9c3b620f712b73c6767c94`
- Compatible rules engine:
  `e19f1b7573c74512f20a6b71a0c55dbbf333d41b`
- PolicyEngine: 4.18.9
- PolicyEngine-US: 1.767.3
- PolicyEngine Core: 3.30.3
- Plotly: 5.24.1
- Certified Populace artifact SHA-256:
  `16be6338f9d0b3c339883dae59949e995663b64cf145de6728b3dd0f916c5d5f`

Fresh input hashes exactly match the accepted inputs:

- composed:
  `03166c96d74382dae2fef348ee6ab8c05ea92e5b855555db0ba60b473700910d`
- compiled:
  `c1d2c5bdac8d03e137d569d50791654981a219699557018ccd151273b8a0bb23`

Replay result:

- 7,101 cases;
- 14,202 comparisons;
- 13,673 matches;
- 529 mismatches;
- zero execution errors;
- raw report SHA-256
  `fe63c28f0e3ead5c8cedc169d4c81c874911e82e533901b6ed54623d735f2bc7`.

Applying the current dispositions and production slimming transform to that
fresh raw report reproduces exactly:

- all 529 canonical mismatch rows;
- all 404 served mismatching-case payloads;
- both aggregates;
- both concepts;
- the complete dispositioned summary.

The only pre-stamp differences are the expected separately generated engine
and provenance stamps; the committed stamps name the exact RuleSpec, engine,
and package versions used above.

## 6. Validation battery

All 15 read-only generated checks pass:

1. disposition join;
2. focused CA case artifacts;
3. focused CA served dispositions;
4. grids;
5. boundary cases;
6. affected map;
7. vacuous/freshness gate;
8. dashboard overview;
9. conformance universes;
10. conformance compositions;
11. scoreboard;
12. ratchet;
13. burn-down;
14. #423 reconciliation;
15. dependent #362 dispatch.

The conformance-universe check verified UK and BE. US-PE and UK-PE were
explicit clean no-ops because the available general checkouts are newer than
their registry pins; the CA run itself used the exact required stack above.

Additional validation:

- focused repair tests: 40 passed;
- repository-wide Ruff 0.15.0 lint: passed;
- `git diff --check`: passed.

Full pytest result:

```text
2 failed, 2320 passed, 70 skipped, 104 warnings in 267.11s
```

No repair-specific test failed. The two failures are unchanged and unrelated:

1. `tests/test_dashboard_loader.py::test_loader_equivalence` cannot resolve
   `registry.npmjs.org` for sandboxed `npx esbuild` (`ENOTFOUND`);
2. the unchanged federal-grid pin test compares commit labels
   `345c2203...` and `ae64af27...` for the already accepted equivalent tree.

Both failed test files and both implicated comparison configs are byte-
unchanged from base.

## 7. Containment and append-only ledger

Repair range `eee181a..f268e26cb`:

- eight commits;
- exactly 31 whitelisted paths;
- 31 ordinary modifications, all mode `100644`;
- no add, delete, rename, or mode change;
- no comparison config, fixture, concept mapping, runner, corpus, or unrelated
  suite change.

The 31 paths comprise only the progress ledger, population mapping and focused
contract test, CA canonical/source/served/compact artifacts, permitted US-PE
ledger and generated rollups, and the #423 reconciler/tests. The full
base-to-head range is likewise 31 mode-stable paths.

Every repair commit includes one committed `State / Done / Next` append.
Across all eight repair transitions:

- the parent `PROGRESS.md` blob is an exact byte prefix of the child;
- 362 lines / 18,177 bytes were appended;
- zero ledger byte was removed.

All reviewer ledger transitions are exact byte-prefix appends as well.

The author branch remained at
`f268e26cb907be0e5df63e255a3e8bc084e7e31d`. Review commits exist only on the
local `review/pr432-f268e26cb-repair-rereview` branch. No PR-branch, remote,
GitHub, issue, comment, or review write occurred.

## Tooling and sandbox disclosures

- GitNexus query tools were not exposed by tool discovery. The repair delta,
  callers, assertions, and containment were therefore audited directly from
  Git history, source, generated guards, and executable receipts.
- The worktree has no local virtual environment. Read-only repository checks
  used the parent environment; the model replay overlaid the cached exact
  PolicyEngine-US/Core/Plotly packages and reverified their versions and import
  paths before execution.
- The parent environment does not contain a `ruff` executable; the available
  system Ruff 0.15.0 binary passed repository-wide lint.
- Restricted npm resolution caused the disclosed dashboard-loader failure.
- The general US/UK conformance checkouts do not match the registry pins, so
  those universe subchecks explicitly no-op rather than claim verification.

None of these limitations blocked the exact CA replay, the full requested
`--check` chain, repair-specific tests, receipt verification, or containment
audit.
