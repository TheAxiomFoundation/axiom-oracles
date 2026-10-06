# B full-schedule continuation checkpoint

**Incomplete: coverage remains CH29 and CH79 (2/100 chapters). No new chapter was evaluated.** The requested `nice -n 10` wrapper emitted `setpriority: Operation not permitted`; an independent preflight observed niceness **0**, required **10**, and exited **2**. The long three-worker evaluation was not started while the question about relaxing that constraint was pending. This is a runtime priority blocker, not a wall-clock timeout or a completed full-schedule run.

The exact starting B state was copied from the previous lane and verified. Preparation receipts, keys and compressed shard bodies were retained; only the two manifest cache-path strings were relocated into this workspace. The original manifest SHA-256 is `11a722f898e8fd3ce23a33f175acdf4ad2bf9e66e178f8d6e2c960f783cbad42`. The current manifest SHA-256 is `b1bd7699a3a35cfd63b14b3d4b6ff511dc0565fed90d14dc73f3e9c881f28193`. The unchanged campaign accepted both chapters with `evaluate --chapters 29,79 --workers 3 --resume`, exit 0:

```text
29: resume skip cases=991575 errors=0
79: resume skip cases=8100 errors=0
```

## Measured totals

**Full-schedule comparisons, matches, mismatches, unexplained and open totals are unmeasured.** Official `compare` was not run because coverage is incomplete. Official `classify` was not attempted, as instructed. The current-selector diagnostic census was rerun over both complete chapters, then its own verified resume was run successfully. No selector or RuleSpec semantics changed.

| Complete chapter | Cases | Comparisons | Matches | Mismatches | Unexplained | Axiom-open |
|---|---:|---:|---:|---:|---:|---:|
| 29 | 991,575 | 11,689,650 | 11,493,380 | 196,270 | 0 | 0 |
| 79 | 8,100 | 90,072 | 89,028 | 1,044 | 0 | 0 |
| **Completed coverage** | **999,675** | **11,779,722** | **11,582,408** | **197,314** | **0** | **0** |

Both chapters have zero engine errors. These are completed-chapter diagnostic totals, not global guarded classification or conformance. Every observed class/slot/chapter, including explained mismatches, is retained in [B-completed-gap-inventory.json](B-completed-gap-inventory.json) and its chapter directory. Zero-unexplained/zero-open closure differs from numerical agreement: current dispositions preserve some source-backed reference/methodology differences.

## Known gap inventory, prior bounded probes only

The source audit independently reclassified the previous lane's four bounded B shards with the unchanged current selectors. It reproduced **168 unexplained units and 83 Axiom-open components** across 2,438 prior cases. These selected probes are not additional complete chapters and must not be added to the completed-chapter totals; their CH29 rows overlap full CH29. **The complete remaining-gap inventory cannot be produced without the 98 remaining chapters.**

Ranked by comparison units, the independently reproduced partial inventory is:

| Chapter | Current class/bucket | Slot | Unexplained | Axiom-open |
|---|---|---|---:|---:|
| 94 | `__unexplained_total__` | total | 82 | 0 |
| 94 | `__unexplained_component__` | forced_labor_section_301 | 80 | 0 |
| 84 | section232-annex-forced-labor | forced_labor_section_301 | 0 | 35 |
| 84 | section232-annex-brazil | brazil_section_301 | 0 | 33 |
| 84 | section232-heading-forced-labor | forced_labor_section_301 | 0 | 8 |
| 94 | `__unexplained_component__` | brazil_section_301 | 6 | 0 |
| 62 | cafta-52i-deferred | forced_labor_section_301 | 0 | 5 |
| 84 | section232-heading-brazil | brazil_section_301 | 0 | 2 |
| **Total, bounded probes** | | | **168** | **83** |

`__unexplained_*` are diagnostic buckets, not new selectors. Totals are comparison units derived from component differences, not additional independent defects. The grouped causes rank as applicability/vintage 168, annex coverage 68, sector headings 10 and CAFTA 5.

## Grounded causes and repair order

**B has observed remaining gaps and does not establish 100% closure.** Full-schedule status is unmeasured. No encoding-only sequence guaranteed to yield 100% numerical agreement is supported by these observations. The grounded next steps, ordered by the known partial gap counts, are below. They were not executed; atomic changes must use the supervised encoder required by the org rules.

1. **Resolve dated applicability for `9403999020` (168 units).** BR / 2026-07-22 / Brazil: Axiom `0`, Yale `0.25`; MX / 2026-07-24 / note 52: Axiom `0`, Yale `0.10`. `B/rulespec-us/tools/b16_entry_flags.py:34` unions versioned members without dates; `:134`, `:142`, `:187` use the static steel flag to exclude both charges. The exact steel atom is at `B/rulespec-us/us/policies/usitc/us-tariff-incidence/generated/note16-232-steel.yaml:3449`, in the August-3 version at `:3396`. The pinned corpus JSONL at commit `5cf7556ad3d68aa0596d58f7ac60942bb5db3120`, `data/corpus/provisions/us/statute/2026-08-04-usitc-hts-2026-rev15-notes.jsonl:246` and `:251`, supplies the heading/metal-content condition and exact atom. The smallest grounded action is to reconcile the dated instruments and required metal/origin facts, then encode the applicable heading and exclusions. Deleting the atom or copying Yale's mask is not justified by this audit.
2. **Encode omitted derivative-aluminum applicability (68 units).** `8467895030` / BR / 2026-07-30: Brazil `0.25 / 0`, note 52 `0.125 / 0` (Axiom / Yale). `B/rulespec-us/tools/generate_incidence_tables.py:78` omits the relevant derivative-aluminum limbs; the pinned corpus above at `:248` names `8467.89.50` under Note 16(c)(vi). Encode the missing statutory heading, date, origin and metal-content conditions, then consume the Note-50/52 exclusion. This cause is proved for the sample, not automatically for every possible annex unit.
3. **Consume statutory sector-heading coverage (10 units).** `8414308030` / BR / 2026-07-23 / Brazil: `0.25 / 0`; `8407344400` / RU / 2026-07-30 / note 52: `0.125 / 0`. `B/rulespec-us/tools/b16_entry_flags.py:165` expressly leaves these sector limbs unconsumed; generated `us/policies/cbp/us-tariff-schedule/generated/ch84/ch84.yaml:3041` and `:3198` consume the resulting generic flags. Derive source-backed per-article heading coverage with its entry conditions and use it in both exclusions.
4. **Encode CAFTA scope and actual qualifying claim (5 units).** `6203331040` / CR / 2026-08-01 / note 52: `0.125 / 0`. `B/rulespec-us/us/policies/usitc/us-tariff-duty/overlays/section-301/forced-labor-costa-rica-9903-05-33.yaml:36` names the unconsumed heading input; `tools/generate_incidence_tables.py:286` documents missing GN29 scope/claim treatment. Encode the scope-and-duty-free-claim conjunction, after reconciling the neutral campaign inputs with Yale's preference treatment. Origin/product membership alone does not establish a qualifying claim or prove this repair will produce Yale zero.

[gap-cause-audit.md](gap-cause-audit.md) contains the exact pinned corpus citations, independently verified Yale joins, active generated-program citations, sample cells and further source-visible gaps that have not been assigned new measured units. Its evidence confirms six samples, five joins, thirteen Yale source files, the corpus hash and eleven audited B source files.

## Historical A transitions

The hash-only audit verified all **100 historical A shard bodies**, totaling 722,142,701 compressed bytes, but **0/100 historical keys match the current retained A receipt**. No original historical full-schedule population is eligible under the requested current-key restriction. These shards were not rekeyed or paired again.

CH79 alone has an accepted fresh A reproduction whose compressed bytes equal historical CH79. Its prior pairing was rebound to the verified current campaign/key/body hashes: **0 matches became mismatches**, and 1,266 mismatches became matches across 90,072 comparisons. This is the limited historical-output-equivalent result, not a full-schedule historical count. The old CH29 diagnostic's 2,066 regressions remain excluded because its A key is stale. See [historical-eligibility.md](historical-eligibility.md) and its JSON evidence.

## Commands and verification observed

| Work | Outcome |
|---|---|
| Exact setup/receipt/key/body verification | Exit 0, PASS; no receipt recreated |
| Official CH29/79 resume check under requested wrapper, 3 workers | Exit 0; both skipped; nice emitted permission error |
| Actual priority preflight | Exit 2; niceness 0, required 10 |
| Completed-chapter current-selector census | Exit 0, 150.722 s; all conservation checks pass |
| Diagnostic resume verification | Exit 0, 10.603 s; CH29/79 both `resumed: true` |
| Helper static checks | Conservation on known censuses; corrupt total rejected; compilation/help pass |
| Continuation shell syntax and campaign argument review | PASS |
| Historical hash/key eligibility audit | Exit 0, 17.056 s; all assertions pass |
| Prior bounded source/census audit | Exit 0; 168 unexplained and 83 open reproduced |
| Remaining-chapter evaluation / official compare / official classify | Not run |

The actual timed commands and output are in `logs/`; setup/copy recovery is in [SETUP_COMMANDS.md](SETUP_COMMANDS.md). No campaign or RuleSpec source changes, encoding repairs, network/API calls, push, PR, comment or merge ran.

## Continuation and artifacts

Completed: **29, 79**. Remaining: **01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 78, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99a, 99b, 99c**. No partial shard was promoted, and no engine evaluation writer remains from this lane.

From an environment where the requested niceness can be applied:

```sh
sh /Users/maxghenis/.subfleet/worktrees/20260923-222653-yale-campaign-b-full/yale-b-full/resume_pipeline.sh
```

This checks niceness, runs all remaining `evaluate --resume` work with three workers, then official `compare` and the current-selector diagnostic helper. Exact expanded commands and clean interruption/resume instructions are in [CONTINUATION.md](CONTINUATION.md). Preparation receipts must remain unchanged. The pending priority question is the reason the long evaluation did not begin here.

Artifacts retained in this workspace:

- `B/oracles`, `B/rulespec-us`, `B/cache`: source state, retained preparation artifacts and two completed compressed shards.
- [CHECKPOINT.json](CHECKPOINT.json), [setup-verification.json](setup-verification.json), and `prior-checkpoint/B-MANIFEST.json`: exact coverage, continuation and hash evidence.
- [B-completed-gap-inventory.json](B-completed-gap-inventory.json), `.md` and `B-completed-gap-inventory-chapters/`: all observed completed-chapter class/slot populations and samples.
- [gap-cause-audit.md](gap-cause-audit.md), `gap-cause-audit-evidence.json`, `gap-cause-current-copy-verification.json`, and audit script/output: source-grounded known partial gaps.
- [historical-eligibility.md](historical-eligibility.md), its JSON and audit script: historical/current key eligibility and limited CH79 pairing evidence.
- `helpers/`, `resume_pipeline.sh`, `check_priority.py`, `run_logged.py`, `logs/`, and `prior-checkpoint/`: reproducible tooling, exact commands and retained prior evidence.
- [ARTIFACTS.json](ARTIFACTS.json): bounded artifact paths, sizes and SHA-256 hashes. `git-history.txt` and `changes.bundle` package local commits separately.

The outer checkout's shared Git metadata is outside the writable workspace; its branch creation failed. Coherent steps are instead committed on **`subfleet/yale-campaign-b-full` in `B/oracles`**, preserving the previous lane's history. Small run artifacts are mirrored under `B/oracles/measurement/yale-campaign-b-full/` for review; cache bodies remain identified by hash in this workspace.
