# Current-code Yale tariff campaign checkpoint

**B does not meet the requested zero-unexplained, zero-open condition in the completed fresh cohort.** Across the same 118,194 fresh comparisons, B reduces mismatches from 6,164 to 3,662 and unexplained units from 3,394 to 168, but has 83 Axiom-attributed-open components. These are **partial-schedule measurements**, not a full-schedule result or an official v2 classification/report. No v2 report or replacement certificate has been produced at this checkpoint. Separately, B completed full Chapters 29 and 79: **11,779,722 comparisons, zero unexplained and zero Axiom-open** under the current diagnostic classifier. The other 98 full chapters remain incomplete or unstarted.

This report uses current axiom-oracles origin/main `16fe458fc46512b15c4580cb9f25596bd7cb6984`, baseline A `96d5e7c1e6309dc205b7320bbddaae8dd5d410df`, and candidate B `c62645022a8b2fcb5f9e6afdc2def2c8d68c2baf`. Both RuleSpec checkouts, all generated artifacts, and new caches are inside this workspace. The engine is `/Users/maxghenis/TheAxiomFoundation/_tariff-parity/axiom-rules-engine/target/release/axiom-rules-engine`, SHA-256 `674ca6e70afdccb59c3d6847933bc24b4590105e49db54790f2dcd0bdbbe32d7`. The previous lane's report and required organization rules were read before work.

## Primary result: fresh A versus fresh B, partial schedule

The completed cohort is all 8,100 Chapter 79 endpoint cases plus disjoint bounded probes: CH62 640, CH84 800, CH29 800, and CH94 198. The latter chapter is restricted to `9403999020`. Both variants freshly evaluated all 10,538 cases, representing 141 origins. This deliberately selected cohort is not representative and its counts must not be extrapolated. The helpers use current campaign comparison functions and selectors; they do not bypass the official classifier to manufacture a receipt. Their diagnostic output explicitly records that global preview-population validation was not performed.

| Metric | A: baseline | B: candidate |
|---|---:|---:|
| Endpoint cases | 10,538 | 10,538 |
| Comparisons | 118,194 | 118,194 |
| Matches | 112,030 | 114,532 |
| Mismatches | 6,164 | 3,662 |
| Unexplained `brazil_section_301` components | 426 | 6 |
| Unexplained `forced_labor_section_301` components | 1,382 | 80 |
| Unexplained `total` units | 1,586 | 82 |
| All unexplained units | 3,394 | 168 |
| Axiom-attributed-open components | 0 | 83 |
| Engine errors | 0 | 0 |
| Would this measured cohort meet zero unexplained and zero open? | **No** | **No** |
| Official full-schedule would-be-conformant result | **Not produced** | **Not produced** |

A's zero open count does not mean its encoding is complete: current selectors leave the hardcoded-false Brazil/note-52 behavior unexplained. `__unexplained_component__` and `__unexplained_total__` are diagnostic census buckets, not invented ledger dispositions. All other class/slot counts are retained in [fresh-combined-census.json](fresh-combined-census.json).

| Existing Axiom-open class | Slot | A | B |
|---|---|---:|---:|
| `cafta-52i-deferred` | `forced_labor_section_301` | 0 | 5 |
| `section232-annex-brazil` | `brazil_section_301` | 0 | 33 |
| `section232-annex-forced-labor` | `forced_labor_section_301` | 0 | 35 |
| `section232-heading-brazil` | `brazil_section_301` | 0 | 2 |
| `section232-heading-forced-labor` | `forced_labor_section_301` | 0 | 8 |

The combined verification returned `PASS: artifact/shard hashes, disjoint cohorts, equal A/B identities, census and paired conservation`. Fresh A CH79's compressed bytes independently match the historical shard SHA-256 `03624b9ab3ee7539ae7ef0333725e1a1e79211dbee08d035e07786ab44ee3e62`; fresh B's hash is `d0dbcb414a8314765aa75ad1d24f216d464614a5972fbdd49c8baf597a0f5704`. The combined case-ID hash is `214b89cb39265424b60117eeb2e17d054d81c4da8155345815197bbde9222fdd`. See [FRESH_RESULT.md](FRESH_RESULT.md) and [TARGETED_RESULT.md](TARGETED_RESULT.md).

## Additional completed fresh B coverage

Full B Chapter 29 finished just before its 30-minute timeout. It is separate from the matched fresh A/B cohort above: there is no complete fresh A Chapter 29, and the 800 CH29 probes above overlap this full chapter. Do not add these tables together.

| Complete fresh B chapter | Cases | Comparisons | Matches | Mismatches | Unexplained | Axiom-open |
|---|---:|---:|---:|---:|---:|---:|
| 29 | 991,575 | 11,689,650 | 11,493,380 | 196,270 | 0 | 0 |
| 79 | 8,100 | 90,072 | 89,028 | 1,044 | 0 | 0 |
| **Total** | **999,675** | **11,779,722** | **11,582,408** | **197,314** | **0** | **0** |

Both complete B chapters meet the numerical zero-unexplained/zero-open condition, with zero engine errors. Global coverage and preview-population guards remain unperformed, so this is not official conformance. Full CH29's remaining Brazil/note-52 component mismatches are all positive: 4,218 Brazil and 54,496 note 52, classified by existing pharmaceutical methodology/reference-behavior selectors. There are no new unexplained or Axiom-open classes in that chapter. See [CH29_RESULT.md](CH29_RESULT.md), [B-fresh-ch29-census.json](B-fresh-ch29-census.json), and `B-fresh-ch29-census-chapters/ch29.json` for every class and slot.

A separately labeled historical-A/fresh-B CH29 pairing verifies the same 991,575 cases: 104,030 mismatches become matches and 2,066 matches become mismatches (82 Brazil, 1,000 note 52, 984 totals). The new components use `yale-zero-pharma-brazil` / `yale-zero-pharma-forced-labor`; none is unexplained or Axiom-open. This pairing is excluded from the fresh A/B table because the baseline shard was not accepted by current cache keys. See [paired-ch29-historical-A-fresh-B.json](paired-ch29-historical-A-fresh-B.json).

## Does B close the Brazil and note 52 gaps?

B closes **all 1,286 unexplained units in complete CH79** in the fresh A/B comparison. Full fresh B CH29 also has zero unexplained units, versus 217,228 in the separately labeled historical A CH29 replay. B does not close the gaps in the matched fresh cohort that includes other-chapter probes. A's helper hardcodes both flags false (`A/rulespec-us/tools/b16_entry_flags.py:107–108`). B derives them from exemption tables and steel/aluminum membership (`B/rulespec-us/tools/b16_entry_flags.py:115–126,134–144,187–192`); existing chapter compositions consume them (`tools/generate_schedule_compositions.py:115–120`). The chapter compositions themselves are unchanged between A and B.

Fresh CH79 examples from [fresh-ch79-paired.json](fresh-ch79-paired.json):

| HTS10 / origin / date | Slot | A | B | Yale |
|---|---|---:|---:|---:|
| `7903906000` / BR / 2026-07-22 | Brazil | 0 | 0.25 | 0.25 |
| `7903906000` / CA / 2026-07-24 | Note 52 | 0 | 0.10 | 0.10 |
| Same CA entry | Total | 0.03 | 0.13 | 0.13 |

These are observed Axiom encoding gaps repaired by B on those entries. The remaining `9403999020` differences have a separately verified input-treatment mechanism described below; their legal resolution remains open.

## What new differences does B introduce?

The fresh paired comparison records 2,660 mismatches becoming matches and **158 matches becoming mismatches**, a net reduction of 2,502. New mismatches occur in the bounded probes and all have positive candidate deltas.

| Transition | Brazil | Note 52 | Total | All |
|---|---:|---:|---:|---:|
| Mismatch → match | 329 | 1,154 | 1,177 | 2,660 |
| Match → mismatch | 61 | 70 | 27 | 158 |
| Retained mismatch, changed actual | 91 | 148 | 387 | 626 |

Examples: `2933492600`/BR/2026-08-01 changes Brazil `0 → 0.25` and note 52 `0 → 0.125`, both against Yale zero; `6203331040`/CR/2026-08-01 changes note 52 `0 → 0.125` against zero; `8407344400`/RU/2026-07-30 does the same. These are numerical changes, not by themselves findings that every new Axiom value is legally wrong. The #510 ruling fixes statutory non-exempt semantics and requires positive statutory exclusions to take precedence over Yale methodology labels (`B/oracles/reference/us-tariff-schedule/output-semantics-ruling.md:5–20`). GN6/pharmaceutical utilization proxies and bounded exact-atom reference defects require their existing source-backed dispositions; actual sector exclusions remain Axiom-open.

The PR receipt's **5,034** is a different population: a historical Brazil *input-scope* diagnostic, expressly not a campaign rerun (`B/rulespec-us/.axiom/encoding-receipts/2026-09-20-note50-note52-incidence-lane.json:494–566`). It divides into 120 exact-ten-digit siblings, 144 GN6 conditional-list candidates, 84 pharmaceutical candidates, and 4,686 unattributed candidates. Current authority precedence leaves only 96 of those historical 120 siblings as reference defects; 24 have positive statutory exclusion authority (`B/oracles/reference/us-tariff-schedule/campaign-dispositions.yaml:377–390`). The receipt withdraws its earlier causal account for the 4,686 and all quantified note-52 causal attributions; its 133,444 note-52 figure is an unattributed upper bound. Neither 5,034 nor 133,444 is a freshly measured mismatch count here. No full-schedule conclusion about those populations has been established.

## What stands between B and 100%?

The following **measured blockers** remain. Counts are comparison units, not unique products or transactions. Proposed repairs below were **not executed**; no RuleSpec or selector semantics were changed. Source paths beginning `R:` are under `B/rulespec-us/`, and `O:` under `B/oracles/`. Detailed verified source joins, exact corpus excerpts and limitations are in [measured-gap-audit.md](measured-gap-audit.md) and [measured-gap-evidence.json](measured-gap-evidence.json).

| Measured gap | Observed sample and concrete cause | Smallest grounded next action, not executed |
|---|---|---|
| **68 open annex units:** Brazil 33, note 52 35 | `8467895030`/BR/2026-07-30: B Brazil `0.25`, note 52 `0.125`, Yale both zero. Axiom's metal flags are false. The pinned corpus Note 16(c)(vi), page 238, names `8467.89.50`; `R:tools/generate_incidence_tables.py:78–84` omits derivative-aluminum 16(c)(vi)/(ix), using old Note 19(b)/(j) instead. The verified Yale join yields Annex 1b, statutory 232 `0.25`. Existing ledger annex classes remain Axiom-attributed (`O:.../campaign-dispositions.yaml:245–288`). | Supervised encoding of omitted derivative-aluminum applicability, including statutory heading, date, origin and metal-content conditions; consume the applicable Note-50/52 exclusion. Do not substitute Yale's nonzero rate for statutory coverage. |
| **10 open heading units:** Brazil 2, note 52 8 | `8414308030`/BR/2026-07-23: Brazil `0.25 / 0`; `8407344400`/RU/2026-07-30: note 52 `0.125 / 0`. Verified Yale joins put both in vehicle/MHD parts, with statutory 232 `0.237625`. `R:tools/b16_entry_flags.py:164–176` expressly leaves those heading limbs unconsumed. Ledger `:333–376`, ruling `:35–76` retain Axiom attribution. | Derive per-article statutory heading coverage and its entry conditions from the proper source, then wire both exclusions. A heading program can apply independently of a metal annex's treatment. |
| **5 open CAFTA units** | `6203331040`/CR/2026-08-01: note 52 `0.125 / 0`. `R:us/policies/usitc/us-tariff-duty/overlays/section-301/forced-labor-costa-rica-9903-05-33.yaml:36` names an unconsumed `article_described_in_heading_9903_05_95`; `R:tools/generate_incidence_tables.py:286–305` records missing GN29 scope/claim. Ruling `:145–158` keeps the gap open. Yale's source marks the relevant prefix `fta`, and its config uses a utilization proxy. | Encode GN29 scope and actual duty-free claim/eligibility, then consume Note 52(i). First resolve the Yale preference/share-to-statutory-column join for these neutral inputs; origin/product membership alone does not prove a claim, and an encoding change alone is not yet proven to yield Yale zero. |
| **168 unexplained units on `9403999020`: Brazil 6, note 52 80, totals 82** | BR/2026-07-22 Brazil `0 / 0.25`; MX/2026-07-24 note 52 `0 / 0.10`. All 198 bounded records also have Axiom 232 `0.5 / 0`. Exact steel atom at `R:us/policies/usitc/us-tariff-incidence/generated/note16-232-steel.yaml:3449`, sourced to 16(c)(vii), August-3 version `:3382–3398`; helper unions versions without dates (`:34–45`) and suppresses both charges through static steel membership (`:134–143,187–192`). Yale instead joins this exact code to April-6 Annex 2, zeroes its 232 rate, and excludes Annex 2 from its shared Note-50/52 exclusion mask. | Reconcile the dated legal instruments behind April-6 removal and August-3 codified membership, deriving applicable 9903.82 heading and metal-weight/origin facts at each campaign date. Only then repair the applicability encoding or establish a bounded, receipted input-comparability disposition. No selector is justified merely by the desired count. |

For `9403999020`, the measured mechanism is exact: Yale `resources/s232_annex_products.csv:748`, `config/policy_params.yaml:332–334`, `src/model/authority_adapter.R:833–838`, and `src/pipeline/06_calculate_rates.R:910–921,2615–2618,2812–2814` establish its Annex-2 zero and exclusion-mask behavior. Axiom uses the static steel atom. The current ledger calls its **232 slot** `vintage-revision-232`, attribution `input-comparability` (`O:.../campaign-dispositions.yaml:483–492`). This supports a **provisional input-comparability/vintage characterization of the associated mechanism**, not a legal judgment or classification of the negative Brazil/note-52 residuals. That selector only covers `section_232`; the 168 units remain unexplained.

The exact corpus also prevents a simplistic repair: Note 16(c) is mapped to headings 9903.82.02–9903.82.26, within the ruling's exclusion family; page 241 contains the exact `9403.99.9020` atom. Page 236 also conditions the relevant headings on at least 15% applicable-metal weight for articles outside chapters 72/73/74/76. The static Boolean does not resolve that condition, the applicable heading or date transitions, and the campaign supplies no measured metal-weight fact establishing it. Do not delete the atom, copy Yale's rate mask, or infer statutory truth from table membership alone.

The full remaining-gap inventory is **unknown until full evaluation and guarded classification finish**. The source audit additionally identifies unconsumed Note-52(j) country lists, prose-qualified exemptions treated as unconditional, Note-52(k) non-ad-valorem equivalent-rate branches, and transaction/9802 duty-base conditions. These are source-visible gaps, **not measured additional certificate counts**. Their causes and proposed minimal repairs are listed in [source-audit.md](source-audit.md).

## Historical baseline replay: completed, not accepted as a current-cache evaluation

All 100 default-cache shard bodies passed their committed hashes (722,142,701 bytes). Nevertheless, **0/100 keys match current main's committed input-contract receipt**. Substituting the pre-#510 receipt in a diagnostic key calculation matches 100/100; that historical receipt was not installed and no old shard was rekeyed. Current key material includes the entire input-contract receipt, including measured duration (`scripts/us_tariff_schedule_campaign.py:733,2143`), and `evaluate --resume` requires the computed key plus hash (`:827`). Thus historical bodies cannot be claimed as accepted current-code engine evaluation.

The unchanged current comparator/selectors did complete a separately labeled replay of four verified historical baseline chapters. This is evidence about those old engine outputs, and is excluded from the primary fresh table:

| Historical A chapter | Cases | Comparisons | Matches | Mismatches | Unexplained |
|---|---:|---:|---:|---:|---:|
| 79 | 8,100 | 90,072 | 87,762 | 2,310 | 1,286 |
| 62 | 1,403,865 | 15,624,738 | 15,268,118 | 356,620 | 246,696 |
| 84 | 1,821,240 | 21,849,858 | 19,943,125 | 1,906,733 | 262,984 |
| 29 | 991,575 | 11,689,650 | 11,391,416 | 298,234 | 217,228 |
| **Total** | **4,224,780** | **49,254,318** | **46,690,421** | **2,563,897** | **728,194** |

That replay has 20,822 unexplained Brazil components, 350,376 note-52 components, and 356,996 totals; zero engine errors and zero classified Axiom-open components. It did not perform the official preview-population guard. Its logged command completed at `2026-09-23T19:52:52.057864+00:00` in 1,057.868 seconds. Evidence: [A-historical-priority-census.json](A-historical-priority-census.json), its four chapter artifacts, and [cache-audit.md](cache-audit.md).

## What honest regeneration of main's v2 artifacts requires

Running current `report` against the committed v1 receipt was observed to fail, exit 1: **`ValueError: classification receipt schema is stale`**. Changing the schema string is insufficient. `classify` binds the actual comparison hash and selector signature populations (`scripts/us_tariff_schedule_campaign.py:1843–1893,1962–1981`); `report` revalidates that handoff (`:2007`).

The required continuation is full `evaluate → compare → classify → report`, with retained valid prepass, input-contract and projection receipts. Comparison requires the entire declared chapter set (`:903–907`). Then regenerate/recheck the independent certificate evidence and run `scripts/certify.py --program us/tariff-duty` and `--check`. The campaign's `computed_conformant` is only S1, zero unexplained plus zero engine errors (`:1992–1993`); the certificate separately requires zero Axiom-open units and no report defects (`scripts/certify.py:489–540`). Final certification also requires exercised, closed and executable premises (`:2617–2629`). An honest v2 artifact can report failure; honest regeneration does not imply 100%.

Specific source-backed blockers and assets:

1. **Fresh engine coverage:** finish all 100 chapters with current receipt keys and hashes. Preserve current receipts while resuming: rerunning `input-contract` changes its duration hash and invalidates every key. Old and new entries must not be mixed; the comparator rejects duplicate chapters. The committed manifests were archived before initializing fresh manifests.
2. **Bound preview populations:** `scripts/build_us_tariff_preview_disposition_receipt.py:60–119,747–769` pins historical compressed inputs and selector counts; its CLI has no current-comparison input (`:496–505`). Campaign code also binds producer/source hashes and exact signatures (`:55–71,1040–1085,1222–1250`). A source-grounded producer/contract update is required for changed populations, not manual count substitution. The expected raw `preview-1311/unmapped-cause-audit-receipt.json` was absent locally (`FileNotFoundError` observed). The bounded source audit used the committed preview source identities, not fabricated missing populations.
3. **Pinned extraction assets:** selected intervals, quotient, full exposure, trajectory map, integrity and provenance come from `Rscript scripts/extract_us_tariff_schedule.R <oracles-root> <yale-root>` (`:4–20,46–106`), upstream of the Python stages. This run reused committed pinned artifacts; no new R extraction ran. A regenerated extraction must reproduce the bound Yale timeseries, origin and source inputs.
4. **Separate certificate producers:** executable reproduction is explicitly pinned to A and rejects other refs (`scripts/tariff_executable_reproduction.py:49,394–398`); it retains `executable=false` for incomplete promised-output coverage (`:93–115,635–648`). Closure is separately pinned (`scripts/us_tariff_closure.py:44–66,1560–1564`). B needs a reviewed rebind of those actual producer contracts and an aligned program set, plus current exercise evidence. `witness-replay` is an independent panel replay and does not regenerate that executable receipt. Exact source-derived commands are in [source-audit.md](source-audit.md).
5. **Source provenance:** B's August-23 Canada-338 union corpus pin is metadata, not verified by the engine compile path. Observed 100/100 compile success in each input-contract stage establishes local module/import compilation only. Engine source loads local YAML and checks source SHA shape (`src/compile.rs:170–182,750–757`; `src/rulespec.rs:206–248,760–802`), without consuming `.axiom/toolchain.toml` or resolving a remote corpus release. No claim that the release was located or hash-verified follows from those passes.

No semantic repair, selector addition, preview producer revision, closure/executable regeneration, certificate generation, push, PR, comment, merge, or OpenAI API call was performed in this checkpoint work.

## Completed stages, tests and runtime

The fresh projection estimated **9.6467 hours for A and 10.5476 for B** with three workers, before full comparison and classification. Both passed the script's 16-hour ceiling. The priority B attempt used a 45-minute evaluation window; CH29 ran alongside it with an isolated manifest so concurrent writers could not overwrite each other's checkpoint. Its evaluator and cache-key logic are unchanged.

The logged stage times below overlap; summing them is not overall wall time. The first stage started at `2026-09-23T19:25:50.485694+00:00`. The last engine-evaluation wrapper ended at `2026-09-23T20:19:33.555583+00:00`; the elapsed logged measurement window to that point was **3223.070 seconds (53 minutes 43.070 seconds)**. Diagnostic pairing, checkpoint checks, documentation and packaging continued afterward; all per-command intervals are in the logs.

| Command/stage | A wrapper seconds | B wrapper seconds | Observed result |
|---|---:|---:|---|
| `prepass` | 452.701 | 491.184 | Both exit 0; 9,913,304 selected cells; identical verified routing hash |
| `input-contract` | 82.470 | 84.407 | Both exit 0; 100 chapter modules compile |
| `projection` | 80.325 | 88.112 | Both exit 0 |
| Fresh complete CH79 `evaluate` | 156.408 | Included in 2,701.981 s priority wrapper | A exit 0; both completed shards, zero errors; shard times A 153.706 s, B 303.372 s |
| Fresh complete CH29, isolated manifest | — | 1,782.190 | Exit 0; 991,575 cases, zero errors; shard time 1,730.683 s |
| Fresh CH29 diagnostic census | — | 94.800 | Exit 0; zero unexplained/open |
| Historical-A/fresh-B CH29 pair | — | 122.089 | Exit 0; equal case identities and slot populations |
| CH79 `evaluate --resume` check | 7.489 | 7.414 | Both exit 0: `79: resume skip cases=8100 errors=0` |
| Fresh CH79 diagnostic census | 18.260 | 12.269 | Both exit 0 |
| Bounded selection | — | 162.797 | Exit 0; 2,438 cases selected |
| Bounded fresh evaluation | 35.685 | 40.587 | Both exit 0; four chapters each, zero engine errors |
| Bounded A/B pair | — | 0.810 | Exit 0; exact case/expected/query-plan identity checks pass |
| Fresh combined census | — | 13.359 | Exit 0; hash, identity and conservation checks pass; helper time 7.107 s |
| Historical A four-chapter replay | 1,057.868 | — | Exit 0; diagnostic counts above |
| `compare` on partial manifests | 0.357 | 0.360 | Both exit 1: `evaluation manifest is incomplete` |
| `report` against existing v1 | 0.534 | 0.220 | Both exit 1: `classification receipt schema is stale` |
| Campaign tests | — | 8.477 | `51 passed, 1 skipped in 6.14s` |
| B entry-flag helper tests | — | 37.784 | `19 passed in 36.07s` |

The source-join audit returned `verification=PASS`: six fresh sample records, five joins, eleven Yale files verified against the committed preview identities, two additional files equal to pinned Git blobs, consumed shards hash-verified, and the ruling's corpus notes SHA-256 matched. Yale commit is `c4307e514196618afcbf88cf7fd33746417eeabf`, tree `d3107eae32ae7ac366b319abd4ab7b13c78d5c3c`. No new engine evaluation ran for that audit.

## Final checkpoint status

| Work | Final observed outcome | Started UTC | Finished UTC | Wrapper seconds |
|---|---|---|---|---:|
| Standard B `evaluate --chapters 62,84,79 --workers 2 --resume` | Timeout, exit 124 / child -15; CH79 complete; no completed CH62/84 shard | 19:34:31.504528 | 20:19:33.555583 | 2,701.981 |
| B CH29 via isolated manifest and unmodified evaluator | Exit 0; complete hash-verified shard, 991,575 cases | 19:46:51.179152 | 20:16:33.437643 | 1,782.190 |
| A `classify` against committed historical full comparison | Timeout, exit 124 / child -15; no new v2 receipt, empty stdout/stderr | 19:37:24.305607 | 20:17:24.822528 | 2,400.445 |

After the primary writer stopped, `merge_isolated_checkpoint.py` recomputed both current B keys, verified both shard hashes and unique chapters, and merged CH29 into the primary B manifest (exit 0, 0.360 s). The unchanged campaign then accepted both with `evaluate --chapters 29,79 --workers 1 --resume` (exit 0, 0.374 s):

```text
29: resume skip cases=991575 errors=0
79: resume skip cases=8100 errors=0
```

Final official coverage is A **1/100** chapters and B **2/100** chapters; the additional bounded probes are separately labeled diagnostics. No partial chapter output was promoted to a completed shard. The final B manifest SHA-256 is `11a722f898e8fd3ce23a33f175acdf4ad2bf9e66e178f8d6e2c960f783cbad42`. The earlier CH79-only B manifest is retained as `B/ch79-checkpoint-MANIFEST.json` so earlier diagnostic manifest hashes remain auditable.

At 20:10:32 UTC official `compare` was run for both variants: exit 1, `ValueError: evaluation manifest is incomplete`. After the final merge B `compare` was run again at 20:20:04 UTC with the same error (exit 1, 0.207 s). Direct `report` against the existing v1 receipt failed for both variants with `ValueError: classification receipt schema is stale`. The historical A `classify` timeout did not reach a recorded preview-guard error; the producer-rebinding requirement above is a source finding, not a fabricated runtime failure. No new v2 classification/report was produced. Full schedule counts and official conformance remain unmeasured.

## Exact commands and continuation

Every logged command retains exact argument vectors, working directory, explicit environment overrides, timestamps, return code and output in `logs/<label>.json`, `.stdout`, and `.stderr`. Initial clone/worktree commands and observed setup results are in [SETUP_COMMANDS.md](SETUP_COMMANDS.md). The blocks below reproduce commands already run; the later continuation block is explicitly unexecuted.

```sh
RUN=/Users/maxghenis/.subfleet/worktrees/20260923-140123-yale-campaign-full-v2/yale-full-run
PY=/Users/maxghenis/TheAxiomFoundation/axiom-oracles/.venv/bin/python
ENGINE=/Users/maxghenis/TheAxiomFoundation/_tariff-parity/axiom-rules-engine/target/release/axiom-rules-engine

# Preparation commands already run for each VARIANT, B and A.
# Do not rerun these over retained receipts merely to resume the checkpoint.
VARIANT=B
cd "$RUN/$VARIANT/oracles"
export AXIOM_TARIFF_C1_CACHE="$RUN/$VARIANT/cache"
export RULESPEC_US_CHECKOUT="$RUN/$VARIANT/rulespec-us"
"$PY" scripts/us_tariff_schedule_campaign.py prepass --rulespec-root ../rulespec-us --engine-binary "$ENGINE"
"$PY" scripts/us_tariff_schedule_campaign.py input-contract --rulespec-root ../rulespec-us --engine-binary "$ENGINE"
"$PY" scripts/us_tariff_schedule_campaign.py projection --rulespec-root ../rulespec-us --engine-binary "$ENGINE"

# B priority command ran under a 2,700-second timeout; only CH79 completed in this wrapper.
"$PY" scripts/us_tariff_schedule_campaign.py evaluate --rulespec-root ../rulespec-us --engine-binary "$ENGINE" --chapters 62,84,79 --workers 2 --resume

# A commands actually run with A's environment and working directory.
VARIANT=A
cd "$RUN/$VARIANT/oracles"
export AXIOM_TARIFF_C1_CACHE="$RUN/$VARIANT/cache"
export RULESPEC_US_CHECKOUT="$RUN/$VARIANT/rulespec-us"
"$PY" scripts/us_tariff_schedule_campaign.py evaluate --rulespec-root ../rulespec-us --engine-binary "$ENGINE" --chapters 79 --workers 1 --resume
"$PY" scripts/us_tariff_schedule_campaign.py classify
"$PY" scripts/us_tariff_schedule_campaign.py report

# Tests actually run in B/oracles and B/rulespec-us, respectively.
cd "$RUN/B/oracles"
AXIOM_TARIFF_C1_CACHE="$RUN/B/test-cache" RULESPEC_US_CHECKOUT="$RUN/B/rulespec-us" "$PY" -m pytest -q tests/test_us_tariff_schedule_campaign.py
cd "$RUN/B/rulespec-us"
"$PY" -m pytest -q tools/test_b16_entry_flags.py

# Diagnostics actually run from the assigned workspace.
cd "$RUN/.."
python3 yale-full-run/measure_shards.py --oracles-root yale-full-run/A/oracles --rulespec-root yale-full-run/A/rulespec-us --manifest yale-full-run/A/committed/MANIFEST.json --chapters 79,62,84,29 --output yale-full-run/A-historical-priority-census.json
"$PY" yale-full-run/run_targeted_probe.py select --oracles-root yale-full-run/B/oracles --output yale-full-run/targeted-selection.json
TMPDIR="$RUN/probe-tmp" "$PY" yale-full-run/run_targeted_probe.py evaluate --oracles-root "$RUN/B/oracles" --rulespec-root "$RUN/B/rulespec-us" --engine-binary "$ENGINE" --selection yale-full-run/targeted-selection.json --output-dir yale-full-run/targeted-B
TMPDIR="$RUN/probe-tmp" "$PY" yale-full-run/run_targeted_probe.py evaluate --oracles-root "$RUN/A/oracles" --rulespec-root "$RUN/A/rulespec-us" --engine-binary "$ENGINE" --selection yale-full-run/targeted-selection.json --output-dir yale-full-run/targeted-A
"$PY" yale-full-run/pair_targeted_probe.py --oracles-root yale-full-run/B/oracles --baseline-manifest yale-full-run/targeted-A/diagnostic-MANIFEST.json --candidate-manifest yale-full-run/targeted-B/diagnostic-MANIFEST.json --output yale-full-run/targeted-A-B-paired.json
"$PY" yale-full-run/combine_fresh.py --run-root yale-full-run --output yale-full-run/fresh-combined-census.json
"$PY" yale-full-run/audit_measured_gaps.py
```

The isolated CH29 command actually started, with B's cache and RuleSpec environment overrides, was:

```sh
cd "$RUN/.."
AXIOM_TARIFF_C1_CACHE="$RUN/B/cache" RULESPEC_US_CHECKOUT="$RUN/B/rulespec-us" "$PY" yale-full-run/evaluate_isolated_shard.py --oracles-root yale-full-run/B/oracles --rulespec-root yale-full-run/B/rulespec-us --engine-binary "$ENGINE" --manifest yale-full-run/B/ch29-isolated-MANIFEST.json --chapter 29
```

**Proposed continuation, not executed by this report:** all evaluation writers have stopped and the completed CH29 checkpoint is merged. Use the retained receipts and [resume_pipeline.sh](resume_pipeline.sh). It prioritizes 62/84/29, evaluates remaining chapters with three workers, then runs the unchanged `compare`, `classify`, and `report` sequentially. It stops on any failure, including historical preview guards. It does not invent dispositions or run the independent witness/certificate producers.

```sh
sh "$RUN/resume_pipeline.sh" B
sh "$RUN/resume_pipeline.sh" A
```

After valid full comparison/classification/report artifacts and any necessary source-grounded producer rebinding, the further **unexecuted** certificate commands are:

```sh
cd "$RUN/B/oracles"
export AXIOM_TARIFF_C1_CACHE="$RUN/B/cache"
export RULESPEC_US_CHECKOUT="$RUN/B/rulespec-us"
"$PY" scripts/us_tariff_schedule_campaign.py witness-replay
"$PY" scripts/certify.py --program us/tariff-duty
"$PY" scripts/certify.py --program us/tariff-duty --check
```

## Artifacts and local changes

- [CH29_RESULT.md](CH29_RESULT.md), `B-fresh-ch29-census.json`, its chapter directory, and `paired-ch29-historical-A-fresh-B.json`: the additional full B chapter and explicitly historical baseline pairing.
- [FRESH_RESULT.md](FRESH_RESULT.md), [fresh-combined-census.json](fresh-combined-census.json), and [fresh-ch79-paired.json](fresh-ch79-paired.json): primary fresh A/B result and verified provenance.
- [TARGETED_RESULT.md](TARGETED_RESULT.md), [targeted-selection.json](targeted-selection.json), `targeted-A/`, `targeted-B/`, and [targeted-A-B-paired.json](targeted-A-B-paired.json): selected cases, fresh compressed result shards, per-chapter class/slot censuses, samples and transitions.
- `A/`, `B/`: local checkouts, archived committed artifacts, fresh stage receipts/manifests and workspace caches. `A-fresh-ch79-census.json`, `B-ch79-census.json`, and their chapter directories retain current fresh CH79 diagnostics.
- [A-historical-priority-census.json](A-historical-priority-census.json) and its chapter directory: explicitly historical four-chapter replay, separate from current accepted cache evaluation.
- [cache-audit.md](cache-audit.md), `baseline-cache-key-audit.json`, `baseline-historical-cache-audit.json`, `chapter-exposure-ranking.json`, `prepass-verification.json`, and `A-ch79-cache-reproduction.json`: cache and setup evidence.
- [source-audit.md](source-audit.md), [measured-gap-audit.md](measured-gap-audit.md), [measured-gap-evidence.json](measured-gap-evidence.json), and `measured-gap-yale-source-joins.json`: grounded causes, legal/source limits and producer requirements.
- `logs/`: exact commands and observed output. Helpers: `run_logged.py`, `measure_shards.py`, `pair_shards.py`, `run_targeted_probe.py`, `pair_targeted_probe.py`, `combine_fresh.py`, `evaluate_isolated_shard.py`, `merge_isolated_checkpoint.py`, `audit_measured_gaps.py`, `build_inventory.py`, and [resume_pipeline.sh](resume_pipeline.sh).

Campaign, selector and RuleSpec source were not edited. Existing changes and the default cache were preserved. The outer branch creation command failed with exit 128 because shared Git metadata could not create `index.lock` (`Operation not permitted`), recorded in [setup.json](setup.json). Work was committed in coherent steps in the writable local `B/oracles` checkout on `subfleet/yale-campaign-full-v2`. Exact local commit IDs are recorded in `git-history.txt`; `changes.bundle` contains this branch's commits relative to origin/main. The final inventory, [ARTIFACTS.json](ARTIFACTS.json), records retained artifact paths, sizes and SHA-256 hashes. Large workspace cache bodies remain outside the Git bundle and are identified by manifest/hash. No remote mutation ran.
