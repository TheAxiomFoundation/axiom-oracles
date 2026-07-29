VERDICT: REQUEST-CHANGES

# Blind review — `data/month-fix-regen`

Target `f0a6598e1337310fdf2f663af91b7ab81f773491` is not ready to merge.
The regenerated data itself is strong: all three required independent replays
match the committed artifacts, the 19-suite scope is complete, disposition
facts check out, month semantics are honest, and the derived chain is green.
Two reviewability/containment defects require correction, including one direct
violation of the requested append-only ledger rule.

## Frozen scope

- Target branch: local `data/month-fix-regen`.
- Immutable target: `f0a6598e1337310fdf2f663af91b7ab81f773491`.
- Declared and verified comparison base:
  `819f370bf0346e4a6a8dfb1c8c4f0d873d6d0340`.
- Merge-base of target and declared base: the declared base exactly.
- Disposable review worktree:
  `.git/review-worktrees/month-fix-regen-f0a6598e-blind`.
- Local review branch: `review/month-fix-regen-f0a6598e-blind`.
- No target-branch, remote, or GitHub write was made.

## Findings

### 1. Blocking — `PROGRESS.md` was replaced, not appended

The target violates the explicit containment requirement that `PROGRESS.md`
be appended rather than rewritten.

- Base `PROGRESS.md`: 57,579 bytes and 951 lines.
- Target `PROGRESS.md`: 14,644 bytes and 245 lines.
- Base-to-target numstat: `245 insertions, 951 deletions`.
- The first branch commit, `6d73f431`, alone records `28 insertions,
  951 deletions`.
- The deleted file is the existing US–PolicyEngine reconciliation ledger
  beginning `PROGRESS — us-pe reconciliation`, not disposable boilerplate.

Required fix: restore the base ledger byte-for-byte, append the month
regeneration ledger after it, and regenerate the branch commits without
deleting or editing the pre-existing history.

### 2. Material — California's `188/22/131` evidence claim is not anchored to the literal merged #423 set

The final California classifications are factually sound, but the branch's
accounting and validation machinery are not self-contained:

- The actual merged base at `819f370b` contains 345 issue-#362/#423 evidence
  identities.
- The claimed `188 vanished + 22 drifted + 131 retained = 341` uses
  `/private/tmp/month-fix-regen-ca423.yaml`, SHA-256
  `da5bf292288a2a33c9d8ca88619a264f7a537f92bcd282ce1c3266a39acfb26b`.
- That 341-row source comes from repaired commit `b09a8319`, which is not an
  ancestor of the target.
- The four merged-base-only identities are the benefit and eligibility rows
  for `ecps-59082` and `ecps-62506`. All four genuinely vanish, so the literal
  merged-base accounting is:

  ```text
  192 vanished + 22 materially drifted + 131 retained = 345
  ```

- The exact reconciler is only the temporary file
  `/private/tmp/month-fix-regen-audit-bin-220a71f1/reconcile_ca.py`; its input
  receipt and exact drift-row output are also untracked.
- The target's tracked `scripts/build_ca_snap_362_dispositions.py` still
  expects 345 rows and cannot validate the refreshed artifacts. Running its
  documented `--check` mode with the saved trace fails at
  `_compact_value(..., "o", ...)` with `KeyError: 'o'` because the compact
  artifact schema changed.
- Historical hardened builder `b09a8319` does validate the repaired 341-row
  source and receipt, but it validates the old source only; it does not perform
  the target's current `188/22/131` reconciliation.

Required fix: commit a compact, schema-compatible reconciliation receipt or
checker that starts from the literal merged 345-row base, records the exact
192/22/131 partition, and correct the ledger/report wording. The four extra
rows do not change the final dispositions, but their provenance cannot remain
implicit in `/private/tmp`.

## Regeneration integrity

I replayed California SNAP, Kansas TANF, and SSI using the committed
compose/compile/compare/disposition machinery. The runtime independently
reported:

```text
policyengine==4.18.9
policyengine-us==1.767.3
policyengine-core==3.30.3
```

The runner's `provenance.generated_at` is inherently wall-clock-dependent.
For the literal byte comparison, I first asserted that every other provenance
field matched, then reused only the committed timestamp and serialized through
the committed dashboard pipeline. No calculated value, disposition, stack
field, case ordering, or other provenance field was normalized.

| Replay | Cases | Raw mismatches | Candidate and committed SHA-256 | Result |
| --- | ---: | ---: | --- | --- |
| `ca-snap-ecps` | 7,101 | 529 | `d5b95f7c8f9e9a66f5146dcf82bcfe719c6433cb150217a181f4db959fe3911d` | byte parity |
| `ks-tanf-ecps` | 861 | 218 | `1132d023920d768577617e074b914cd17c89a057dd7fd893c5052454b4a33532` | byte parity |
| `ssi-ecps` | 75,112 | 2,990 | `0eb73772a9220a0cd0aaeb1ec174a43fab61bf33289f56c600202a1f7128399b` | byte parity |

California completed all 72 comparison batches with cyclic garbage collection
kept enabled and did not reproduce the worker's earlier batch-68 memory kill.
Replay receipts are under `/private/tmp/month-fix-review-replays/<suite>/`.

All 19 primary reports, case indexes, and relevant overview entries record the
same declared stack. No suite-config tolerance field changed. Normalized
concept tolerance metadata is identical at base and target for all 19 reports;
the nine TANF/SSI concept mappings remain absolute `$25` with no relative
tolerance.

## Affected-set completeness

The exact 194 changed-path inventory classifies as:

| Class | Paths |
| --- | ---: |
| Primary reports for the requested suites | 19 |
| Case artifacts spanning exactly those 19 suites | 108 |
| Comparison configs | 14 |
| Source disposition YAML | 14 |
| Served disposition JSON | 14 |
| TANF/SSI program specs | 9 |
| Permitted shared regenerated artifacts and row notes | 15 |
| `PROGRESS.md` | 1 |
| Unclassified / foreign | 0 |

Additional containment checks:

- The primary-report suite set and case-tree suite set are exactly the
  requested ten SNAP, eight TANF, and SSI suites.
- California TANF, Colorado TANF, and Medicaid MAGI report/config/case/
  disposition paths are byte-unchanged.
- Their excluded concept-mapping blocks hash identically at base and target.
- PolicyEngine-US 1.767.3 source confirms `ca_tanf` and `co_tanf` are numeric
  `YEAR` variables and `is_medicaid_eligible` is a boolean `YEAR` variable.
- UKMOD configs, reports, cases, dispositions, and conformance definitions are
  unchanged. The only UK/UK-PE paths are allowed shared dated history
  snapshots; excluding the date, each payload equals its July 28 predecessor.
- All 197 unaffected dashboard reports and 196 unaffected freshness entries
  are semantically identical.
- Non-US-PE scoreboard jurisdictions are unchanged.
- No new host/worktree absolute path is embedded in changed configs or data.
- `git diff --check` passes and no file mode changed.

The only affected-set failure is the destructive `PROGRESS.md` replacement
described above.

## California disposition audit

### Vanished rows

Against the repaired 341-row source, all 188 claimed vanished identities are
absent from the new mismatch report. Their 126 unique households remain in the
compact artifacts, each with 100% match rate and no mismatch for the old
case/concept identity.

This deterministic 12-row sample exceeds the requested minimum:

| Old disposition identity | Old left | Old right | Current result |
| --- | ---: | ---: | --- |
| `ca-362-self-employment-tanf-ecps-61018-benefit` | 785 | 251.27410888671875 | match |
| `ca-362-self-employment-forward-ecps-57615-benefit` | 61 | 0 | match |
| `ca-362-self-employment-tanf-ecps-58835-benefit` | 930 | 402.9453531901042 | match |
| `ca-362-self-employment-forward-ecps-60334-benefit` | 298 | 0 | match |
| `ca-362-period-self-employment-tanf-ecps-59593-eligibility` | true | false | match |
| `ca-362-period-ecps-57472-benefit` | 773 | 782.8538411458334 | match |
| `ca-362-period-ecps-59371-benefit` | 404 | 411.0453287760417 | match |
| `ca-362-period-ecps-60702-benefit` | 717 | 727.1131998697916 | match |
| `ca-362-period-ecps-57158-benefit` | 342 | 350.0795084635417 | match |
| `ca-362-self-employment-forward-ecps-59768-benefit` | 298 | 0 | match |
| `ca-362-self-employment-ecps-61485-benefit` | 238 | 54.79497273763021 | match |
| `ca-362-self-employment-forward-ecps-59283-eligibility` | true | false | match |

The four literal-merged-base-only rows for `ecps-59082` and `ecps-62506`
also have 100% current match rates and no mismatches.

### Materially drifted rows

All 22 drifted rows:

- remain current mismatches;
- are absent from final source and served dispositions;
- are absent from every expanded selector;
- have `disposition: null` in the committed report.

Their old evidence is therefore not silently carried. Exact old → current
left/right evidence:

```text
56991   1183 / 818.199951171875       -> 1141 / 818.199951171875
57027   1571 / 942.5                  -> 1363 / 942.5
57313   623 / 623.5999755859375       -> 631 / 623.5999755859375
57453   225 / 298                     -> 239 / 298
57529   994 / 561.699951171875        -> 703 / 561.699951171875
57845   1183 / 688.9000244140625      -> 957 / 688.9000244140625
57891   994 / 557.7999877929688       -> 878 / 557.7999877929688
58088   687 / 548.199951171875        -> 634 / 548.199951171875
58987   179 / 78.99998474121094       -> 78 / 23.84000015258789
59016   298 / 88.29998779296875       -> 0 / 88.29998779296875
59103   154 / 23.84000015258789       -> 0 / 23.84000015258789
59173   421 / 277.79998779296875      -> 0 / 277.79998779296875
60319   298 / 94.29998779296875       -> 0 / 94.29998779296875
60409   1196 / 716                    -> 1018 / 716
60756   603 / 289.3999938964844       -> 504 / 289.3999938964844
60777   785 / 387.79998779296875      -> 679 / 387.79998779296875
60816   361 / 283.89996337890625      -> 361 / 0
60859   994 / 286.89996337890625      -> 0 / 286.89996337890625
60978   329 / 113.0999755859375       -> 307 / 113.0999755859375
61251   994 / 557.5                   -> 884 / 557.5
61495   785 / 434.8999938964844       -> 586 / 434.8999938964844
62327   239 / 23.84000015258789       -> 246 / 23.84000015258789
```

### Retained rows

All 131 retained rows have exact current pins and exact report disposition IDs.
The movement split independently reconciles to 115 materially moved and 16
unchanged rows. All 111 retained bridge entries' numeric evidence closes
within the unchanged `$7` suite tolerance.

Six sampled benefit rows:

| Class / case | Current Axiom / PE | Evidence counterfactual / Axiom | Delta |
| --- | --- | --- | ---: |
| period-TANF `57232` | `917 / 535` | `917.7999877929688 / 917` | 0.79998779296875 |
| period-TANF `57252` | `758 / 485.199951171875` | `758.5 / 758` | 0.5 |
| self-employment+TANF `57797` | `994 / 551.199951171875` | `994 / 994` | 0 |
| self-employment+TANF `58394` | `546 / 297` | `546 / 546` | 0 |
| TANF `56996` | `546 / 179.0999755859375` | `546 / 546` | 0 |
| TANF `57016` | `994 / 687.4000244140625` | `994 / 994` | 0 |

The maximum delta across the 104 direct requested-month counterfactual rows is
`$1.50`, safely within `$7`.

### January minimum-benefit class

Independent base/current identity comparison:

| Suite | Old `23.973597208658855` | New `23.84000015258789` | Other January | Match |
| --- | ---: | ---: | ---: | ---: |
| AL | 1 | 1 | 0 | 0 |
| AZ | 78 | 78 | 0 | 0 |
| CA | 45 | 42 | 0 | 3 |
| FL | 272 | 270 | 0 | 2 |
| GA | 76 | 76 | 0 | 0 |
| MA | 78 | 78 | 0 | 0 |
| NC | 2 | 2 | 0 | 0 |
| NY | 19 | 8 | 3 | 8 |
| SC | 64 | 64 | 0 | 0 |
| TN | 0 | 0 | 0 | 0 |
| **Total** | **635** | **619** | **3** | **13** |

Movement samples include AL `ecps-37190`, AZ `ecps-51667`, CA `ecps-57178`,
FL `ecps-31327`, GA `ecps-29773`, MA `ecps-1984`, NC `ecps-27513`, NY
`ecps-4723`, and SC `ecps-28671`; each moves exactly between the two stated
values.

The 13 matching identities are CA `59086`, `61031`, `62057`; FL `31350`,
`32233`; and NY `4721`, `5097`, `5539`, `5872`, `5923`, `6817`, `6871`,
`6879`. Every current case has 100% match rate and no mismatch.

## Comparison-period semantics

All eight TANF suites and SSI retain `period: 2026-01` from base to target.
All selected Axiom outputs are explicitly monthly:

- AL, DE, GA, MN, NY, and WA select their monthly benefit outputs.
- AZ's monthly wrapper divides its annual leaf by 12.
- Kansas adds `ks_tanf_monthly_maximum_benefit`.
- SSI's household monthly wrapper divides `ssi_annual_benefit` by 12.

The corresponding nine PolicyEngine-US 1.767.3 variables all report
`definition_period=month`. Their mappings and reports retain the unchanged
`$25` tolerance.

### Kansas TANF

Kansas moves from 6 to 218 raw mismatches with zero unexplained. This is
evidence-backed, not tolerance-driven:

- Final selectors cover exactly all 218 mismatch identities.
- 212 rows belong to Douglas (`20045`, 32), Harvey (`20079`, 9), or Johnson
  (`20091`, 171) counties.
- PolicyEngine's actual county grouping selects group IV for those rows while
  the Axiom bridge intentionally fixes group I. Every one of the 212 rows is
  exactly `$43` lower on Axiom, exceeding the unchanged `$25` tolerance.
- The remaining six are the six prior SSI assistance-unit identities, now
  pinned at monthly values: two `309/241`, one `224/0`, two `454/403`, and one
  `515/471`. Every delta also exceeds `$25`.

### Alabama TANF

Alabama honestly moves from `0 / 0` to `3 raw / 3 unexplained`.
`dispositions_file` is null and every row is unclassified:

```text
ecps-37103  18 / 53.390533   difference -35.390533
ecps-37187  250 / 279.929443 difference -29.929443
ecps-37415  305 / 334.262756 difference -29.262756
```

All three exceed the unchanged `$25` tolerance.

## Chain parity and reconciliation

The complete required check battery exited zero:

```text
scripts/apply_dispositions.py --check
  Validated 82 dispositions files
  Dispositions are consistent with the committed dashboard data

scripts/extract_grids.py --check
  Grids up to date.

scripts/generate_affected_map.py --check
  affected_map OK: 172 suites, 184 suite-repo edges

scripts/check_vacuous_gate.py --check
  vacuous-gate OK: 136 configs oracle-backed; 215 suites,
  34 executable surfaces, 68 suite(s) awaiting provenance

scripts/conformance_scoreboard.py --check
  conformance scoreboard OK: 4 jurisdiction(s), 3 conformant

scripts/conformance_ratchet.py --check
  conformance ratchet OK: 4 jurisdiction(s), no invariant regressed

scripts/conformance_burndown.py --check
  conformance burn-down OK: 4 series, 57 point(s)
```

The dispositions check printed four unrelated pre-existing informational
expired-entry notes for BE worker SSC, two Colorado tax-intersection entries,
and the NYC diagnostic; it still exited zero and none belongs to this branch.

History has no native `--check` flag. I rebuilt each snapshot document in
memory through `conformance_scoreboard._snapshot_document`, serialized it with
the committed serializer, and byte-compared:

```text
be     exact: 23/23 covered, unexplained 0, axiom 0
uk     exact: 21/21 covered, unexplained 0, axiom 0
uk-pe  exact: 23/23 covered, unexplained 0, axiom 0
us-pe  exact: 34/127 covered, unexplained 244, axiom 157
```

Every requested suite decomposes exactly:

| Suite | Raw | Encoding | Bridge | Upstream | Unexplained |
| --- | ---: | ---: | ---: | ---: | ---: |
| `al-snap-ecps` | 56 | 8 | 0 | 8 | 40 |
| `az-snap-ecps` | 597 | 597 | 0 | 0 | 0 |
| `ca-snap-ecps` | 529 | 157 | 111 | 20 | 241 |
| `fl-snap-ecps` | 774 | 0 | 0 | 0 | 774 |
| `ga-snap-ecps` | 245 | 170 | 0 | 0 | 75 |
| `ma-snap-ecps` | 263 | 152 | 17 | 2 | 92 |
| `nc-snap-ecps` | 76 | 10 | 11 | 6 | 49 |
| `ny-snap-ecps` | 245 | 5 | 0 | 0 | 240 |
| `sc-snap-ecps` | 185 | 42 | 29 | 4 | 110 |
| `tn-snap-ecps` | 70 | 0 | 23 | 4 | 43 |
| `al-tanf-ecps` | 3 | 0 | 0 | 0 | 3 |
| `az-tanf-ecps` | 0 | 0 | 0 | 0 | 0 |
| `de-tanf-ecps` | 0 | 0 | 0 | 0 | 0 |
| `ga-tanf-ecps` | 1 | 0 | 1 | 0 | 0 |
| `ks-tanf-ecps` | 218 | 0 | 218 | 0 | 0 |
| `mn-tanf-ecps` | 0 | 0 | 0 | 0 | 0 |
| `ny-tanf-ecps` | 36 | 0 | 36 | 0 | 0 |
| `wa-tanf-ecps` | 0 | 0 | 0 | 0 | 0 |
| `ssi-ecps` | 2,990 | 0 | 2,990 | 0 | 0 |

California therefore reconciles exactly as requested:

```text
529 raw = 157 encoding + 111 bridge + 20 upstream + 241 unexplained
```

The US-PE headline also reconciles: unexplained 244 is California SNAP 241
plus Alabama TANF 3; Axiom-attributed open 157 is California encoding 157.

## Execution disclosures

- GitNexus graph tools were not exposed in this session. This is an
  artifact/program-YAML branch with no changed code symbols, so direct
  path accounting, consumer checks, data replays, and derived-chain checks
  supplied the impact evidence.
- The ordinary project virtual environment contains PolicyEngine-US 1.752.2
  and core 3.28.0. Replays used the existing read-only cached 1.767.3/3.30.3
  overlay with PolicyEngine 4.18.9 from that environment; runtime metadata and
  every generated engine block independently confirmed the exact declared
  stack. No network access was used.
- The sandbox rejected one attempt to place the replay helper directly under
  `/private/tmp` through the patch interface. I instead added and committed the
  review-only helper on the disposable review branch; no target file or
  external checkout was changed.
- The first root-level history parity command referenced a nonexistent
  `scripts.conformance_history` module and failed immediately. The corrected
  command used the actual `scripts.conformance_scoreboard` generator and
  byte-matched all four snapshots.
- The target California builder's `KeyError: 'o'` is a real schema
  incompatibility, not a sandbox failure.
- All substantive audit lanes ended with clean worktrees and no sandbox
  denial. No remote or GitHub action was attempted.

## Recommendation

Request changes at `f0a6598e`:

1. Restore the deleted 951-line base ledger and append the month-regeneration
   progress.
2. Commit a current-schema California reconciliation receipt/checker anchored
   to all 345 literal merged-base rows.
3. Correct the disposition accounting to distinguish the repaired 341-row
   source (`188/22/131`) from the actual merged-base set (`192/22/131`).

After those corrections, rerun the lightweight chain checks. The data
regenerations themselves do not need to be repeated unless the fixes alter
their committed artifacts.
