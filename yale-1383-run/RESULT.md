# Yale #1383 measurement: stopped at baseline reproduction

The baseline report does not reproduce with the observed local `origin/main`
(`c52688619542c5e4a581c84d83283a0b0a5bf1b7`). The campaign's `report` command
exited 1 with `ValueError: classification receipt schema is stale`. Following
the requested stop condition, no candidate evaluation was run. Candidate
conformance, mismatch totals, new classes, and remaining encoding gaps are
unmeasured; this run does not establish 100% conformance.

| Metric | Main committed certificate/detail | Candidate c62645022 |
|---|---:|---|
| Comparisons | 216,111,132 | Not measured |
| Matches | 206,607,439 | Not measured |
| Mismatches | 9,503,693 | Not measured |
| Unexplained | 0 | Not measured |
| fed-false-family-brazil | 93,198 | Not measured |
| fed-false-family-forced-labor | 1,499,038 | Not measured |
| axiom-attributed-open units | 1,592,236 | Not measured |
| Certificate conformant | false | Undetermined |

These main figures were read from committed artifacts, not reproduced by a
fresh full-schedule evaluation. The detail report's separate S1 `conformant`
field is true; the program certificate's conformant premise is false.

## Observed baseline failure

- `scripts/us_tariff_schedule_campaign.py:1549–1553` requires classification
  schema `axiom_oracles.us_tariff_schedule.classification.v2`.
- `reference/us-tariff-schedule/classification-receipt.json:294` commits v1.
  Its lines 4–5 still census both `fed-false-family-*` classes.
- The current `reference/us-tariff-schedule/campaign-dispositions.yaml` has
  neither of those selectors. Commit
  `6ce2e674306d02506a5e1dbce21754a220290cbd` introduced the v2 guard and removed
  the selectors; its changed-file list includes neither the classification
  receipt nor the detail report. Subsequent guards at campaign lines
  1563–1581 reject unknown class IDs and stale preview populations as well.

The unchanged comparator and selectors were replayed over the hash-verified
committed Chapter 79 shard (8,100 cases). This was a read-only diagnostic of
existing engine results, not a fresh engine evaluation:

| CH79 observation | Units |
|---|---:|
| Comparisons | 90,072 |
| Matches | 87,762 |
| Mismatches | 2,310 |
| Brazil component mismatches | 36 |
| Note 52 component mismatches | 620 |
| Direct units unclassified by current ledger | 656 |
| Total units made unexplained by those components | 630 |
| Unexplained, including totals | 1,286 |
| Engine errors recorded in cached shard | 0 |

The partial helper reports zero units assigned to current open classes because
the old classes are absent. That is not closure: 1,286 units are unexplained.
These units are not candidate regressions.

Observed sample component values from that committed shard:

| HTS10 | Origin | Date | Component | Axiom | Yale |
|---|---|---|---|---:|---:|
| 7903906000 | BR | 2026-07-22 | Brazil Section 301 | 0 | 0.25 |
| 7903906000 | CA | 2026-07-24 | Note 52 | 0 | 0.10 |

At baseline rulespec `96d5e7c1e6309dc205b7320bbddaae8dd5d410df`,
`tools/b16_entry_flags.py:107–108` supplies both membership flags as false.
At candidate `c62645022a8b2fcb5f9e6afdc2def2c8d68c2baf`, lines 187–191 derive
them from unconditional exclusions and Section 232 coverage. Those source
observations do not quantify candidate agreement. The receipt's 93,192 and
5,034 diagnostics were not substituted for measurements.

## Checks and elapsed time

| Command/check | Observed output | Elapsed seconds |
|---|---|---:|
| `shasum -a 256` on located engine | Required hash matched | Not timed |
| `prepass`, baseline rulespec | Exit 0; routing SHA matches committed | 445.191 |
| `input-contract`, initial directory layout | Exit 1 on first CH01 compile | 123.346 |
| Direct CH01 compile, original layout | Unresolved canonical `us:` import; exit 1 | 1.127 |
| Direct CH01 compile after adding `rulespec-us` symlink | Exit 0 | 7.107 |
| CH79 cached diagnostic census | Counts above; shard hash matched | 161.864 |
| `report` on committed comparison/classification receipts | Stale schema; exit 1 | 2.192 |

Timings overlap and must not be added as wall time. Timed root stage commands
ran from 2026-09-23 16:35:58 UTC through 16:43:23 UTC. Repository discovery,
checkout, and documentation time are not included.

The engine was located at
`/Users/maxghenis/TheAxiomFoundation/_tariff-parity/axiom-rules-engine/target/release/axiom-rules-engine`.
Its SHA-256 is
`674ca6e70afdccb59c3d6847933bc24b4590105e49db54790f2dcd0bdbbe32d7`.
The source checkout reports `ffd8213271947b0189a9dd61a055c1e0e78908a0`.
Hash verification establishes the required binary identity.

Fresh prepass routing SHA-256:
`7236c015bee357f33063a3ab7917c1b4ad42390d97ad2ecda26fad9bb21232b3`.
Its receipt differs from committed only in `stage_wall_clock_seconds`:
440.833 versus 60.018. The logging wrapper's duration includes process startup.

No fresh baseline chapter evaluation, full baseline, projection, candidate
evaluation, full compare/classify, or test suite was run. The default C1 cache
was only read. A fresh `AXIOM_TARIFF_C1_CACHE` path was supplied; no cache
seeding was performed.

## Exact commands and checkout constraints

The assigned checkout was detached at `ef7e11f5f4e2ff841f2797685ba2807c6090563f`
and lacked the campaign. This command failed before modifying the checkout:

```sh
/usr/bin/git -c core.fsmonitor=false switch -c subfleet/yale-parity-1383-measure origin/main
# fatal: Unable to create '.../.git/worktrees/20260923-093102-yale-parity-1383-measure/index.lock': Operation not permitted
```

All new writes stayed inside the assigned workspace. Local shared bare clones
and worktrees were created there:

```sh
/usr/bin/git clone --shared --bare /Users/maxghenis/TheAxiomFoundation/axiom-oracles yale-1383-run/oracles.git
/usr/bin/git --git-dir=yale-1383-run/oracles.git worktree add -b measure/yale-1383 main-checkout c52688619542c5e4a581c84d83283a0b0a5bf1b7
/usr/bin/git clone --shared --bare /Users/maxghenis/TheAxiomFoundation/rulespec-us yale-1383-run/rulespec.git
/usr/bin/git --git-dir=yale-1383-run/rulespec.git worktree add --detach rulespec-baseline 96d5e7c1e6309dc205b7320bbddaae8dd5d410df
/usr/bin/git --git-dir=yale-1383-run/rulespec.git worktree add --detach rulespec-candidate c62645022a8b2fcb5f9e6afdc2def2c8d68c2baf
ln -s rulespec-baseline rulespec-us
```

Both rulespec commits were already present; no fetch was necessary. The
resolver recognizes `rulespec-us` and `rulespec-us-*` directory names
(`axiom-rules-engine/src/rulespec.rs:963–973,1005–1019`). The symlink resolved
the initial compile setup error without changing RuleSpec content.

The following shell variables express the exact paths captured in `logs/*.json`:

```sh
RUN=/Users/maxghenis/.subfleet/worktrees/20260923-093102-yale-parity-1383-measure
PY=/Users/maxghenis/TheAxiomFoundation/axiom-oracles/.venv/bin/python
ENGINE=/Users/maxghenis/TheAxiomFoundation/_tariff-parity/axiom-rules-engine/target/release/axiom-rules-engine
export AXIOM_TARIFF_C1_CACHE="$RUN/yale-1383-run/baseline-cache"
export RULESPEC_US_CHECKOUT="$RUN/rulespec-baseline"
cd "$RUN/main-checkout"
"$PY" scripts/us_tariff_schedule_campaign.py prepass --rulespec-root ../rulespec-baseline --engine-binary "$ENGINE"
"$PY" scripts/us_tariff_schedule_campaign.py input-contract --rulespec-root ../rulespec-baseline --engine-binary "$ENGINE"
AXIOM_RULESPEC_REPO_ROOTS="$RUN" "$ENGINE" compile --program "$RUN/rulespec-baseline/us/policies/cbp/us-tariff-schedule/generated/ch01/ch01.yaml" --output "$RUN/yale-1383-run/baseline-ch01-compile.json"
"$PY" scripts/us_tariff_schedule_campaign.py report
# Exit 1: ValueError: classification receipt schema is stale
cd "$RUN"
python3 yale-1383-run/chapter_census.py --oracles-root main-checkout --rulespec-root rulespec-baseline --manifest yale-1383-run/committed-main/reference/us-tariff-schedule/eval/MANIFEST.json --chapter 79 --output yale-1383-run/committed-ch79-census.json
```

The initial failed `input-contract` preceded the symlink fix. No rerun of that
100-chapter stage occurred after discovering the independent report blocker.
Each root stage's exact argv, working directory, environment overrides,
stdout, stderr, exit status, and timestamps are recorded in `logs/`.

`axiom-locate release us-rulespec-2026-08-23-canada-338-suspension-union`
returned no results. Candidate source resolution was not exercised because
the baseline stop condition fired. No corpus pin or source was changed.

## Retained artifacts

The requested external `_briefs/.../yale-1383-run/` directory is outside the
sandbox's writable roots. Artifacts are retained instead at
`/Users/maxghenis/.subfleet/worktrees/20260923-093102-yale-parity-1383-measure/yale-1383-run/`:

- `RESULT.md`, `measurement.json`, `preflight.json`, `ARTIFACTS.json`
- `run_logged.py`, `chapter_census.py`
- `logs/`: timed command receipts and stdout/stderr
- `baseline-prepass-receipt.json`, `baseline-prepass-check.json`
- `committed-ch79-census.json`, `committed-ch79-target-samples.json`
- `campaign-baseline-audit.md`, `baseline-report-stage.log`
- `committed-main/`: original certificate, detail, manifest, and stage receipts
- `baseline-ch01-compile.json`: successful diagnostic compilation artifact

The original assigned checkout was preserved. Generated stage changes in the
isolated main checkout were archived and restored; no campaign, ledger,
certificate, or RuleSpec source was edited. No push, PR, comment, merge, or
OpenAI API call occurred.
