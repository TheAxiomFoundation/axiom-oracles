# PR #1311 preview-conformance report

Date: 2026-08-26  
Lane: preview conformance, note-50/52 classes  
Question: whether rulespec-us #1311 closes the 1,592,236 axiom-attributed-open units in certificates/us-tariff-duty.json before the official toolchain rebind

## Executive result

No. At the pinned #1311 head, the preview closes 1,443,846 of the 1,592,236 original units (90.680402%) and leaves 148,390 original units open.

| Original certificate class | Baseline units | Closed by #1311 | Residual | Closure |
|---|---:|---:|---:|---:|
| fed-false-family-forced-labor | 1,499,038 | 1,359,384 | 139,654 | 90.683759% |
| fed-false-family-brazil | 93,198 | 84,462 | 8,736 | 90.626408% |
| **Total** | **1,592,236** | **1,443,846** | **148,390** | **90.680402%** |

The 148,390 residual units are 74,195 component-interval cells: 69,827 forced-labor and 4,368 Brazil. They are not the deferred Note 52(i) CAFTA population. CAFTA is a separate, newly exposed population that matched Yale before the new flags were bound.

The same rebind exposes 246,940 new Yale/Axiom disagreements. Of those, 17,404 are the exact deferred Note 52(i) CAFTA population and 229,536 are non-CAFTA. Therefore the post-rebind target-slot mismatch count predicted by this preview is:

    148,390 old residual + 246,940 new disagreements = 395,330

The receipt fields named verdict: PASS mean that execution, hashes, joins, and conservation checks passed. They do not mean that the rules conform to the Yale target.

## Why the original classes do not close

The entire 148,390-unit old residual has an exact causal split.

| Cause | Forced units | Brazil units | Total |
|---|---:|---:|---:|
| Yale aircraft-use utilization proxy | 71,168 | 3,654 | 74,822 |
| Yale pharmaceutical-use utilization proxy | 68,418 | 5,082 | 73,500 |
| Yale MFN input-vintage/parser difference | 68 | 0 | 68 |
| **Total** | **139,654** | **8,736** | **148,390** |

For all 74,822 aircraft units, Yale's expected component is exactly 10% of the Axiom non-exempt component rate, reflecting Yale's configured 90% exempt-share approximation. For all 73,500 pharmaceutical units, Yale expects exactly 50% of the Axiom rate. The #1311 list-membership flags are true on these entries, while the C6 panel component applies the full non-exempt rate; conditional/end-use treatment belongs to entry-level wiring. This is a model/output-contract disagreement, not a missed note-50/52 list entry.

The remaining 68 forced-labor units are 17 HTS10-origin cells repeated at four probes. They are confined to four chapter-87 lines:

- 8712005000
- 8714915000
- 8714921000
- 8714949000

Forty-four are 10% cap cases and 24 are 12.5% cap cases. In the affected Yale target vintages, raw General-rate strings carry trailing HTML underline tags and Yale's parser yields a zero statutory base. The C6 input preserves General rates of 3.7%, 6%, 5%, or 10%, so the cap formula produces smaller additional-duty gaps. This is an oracle input-vintage/parser difference, not a #1311 flag, cap, or effective-date error.

The deterministic old-residual audit, including every rate pair, origin/tier/chapter/date distribution, all 17 parser cells, source-list parity, and representative case IDs, is:

    reference/us-tariff-schedule/preview-1311/old-residual-taxonomy-receipt.json
    SHA-256 b4f9d26d5a800cf1b0e6e50c6b3935ee18b24ca55bbcc5eecf9e10ab8f829bea

Its reproducer is:

    reference/us-tariff-schedule/preview-1311/old_residual_taxonomy.py
    SHA-256 ff5cc00b453547534beaa48f62ef0046c04249a947bff4e92921832465faddf7

Nearly all old residuals are positive-rate overshoots relative to Yale: 148,322 overshoot, 56 forced-labor units undershoot, and 12 forced-labor units remain at zero. All 8,736 Brazil residual units evaluate at 25%, while Yale expects 12.5% or 2.5%.

## Deferred Note 52(i) CAFTA residual

The exact panel exercise is **17,404 endpoint component units / 8,702 component-interval cells**. It covers:

- 1,633 of Yale's 1,737 conditional HTS8 entries;
- 3,909 HTS10 codes;
- 4,351 HTS10-origin pairs;
- four probes, with 4,351 units at each of 2026-07-24, 2026-07-30, 2026-07-31, and 2026-08-01.

| Origin | Units |
|---|---:|
| Costa Rica (CR) | 1,260 |
| Dominican Republic (DO) | 128 |
| Guatemala (GT) | 108 |
| Honduras (HN) | 120 |
| Nicaragua (NI) | 15,636 |
| El Salvador (SV) | 152 |
| **Total** | **17,404** |

The realized Axiom-minus-Yale deltas are 12.5 percentage points on 17,024 units and 10 percentage points on 380 units.

The exact chapter distribution is:

| Chapter | Units | Chapter | Units | Chapter | Units |
|---|---:|---|---:|---|---:|
| 42 | 356 | 50 | 16 | 51 | 328 |
| 52 | 2,220 | 53 | 276 | 54 | 1,136 |
| 55 | 1,796 | 56 | 356 | 57 | 344 |
| 58 | 464 | 59 | 336 | 60 | 492 |
| 61 | 3,028 | 62 | 4,756 | 63 | 1,000 |
| 65 | 156 | 70 | 252 | 94 | 92 |

This count is an exact join to Yale's condition=fta HTS8 list, not a six-country heuristic. The broader country heuristic finds 30,880 units and would overcount by 13,476.

### Is General Note 29 needed?

Yes, but it is not sufficient by itself.

The successor release us-rulespec-2026-08-09-cutover-surface-union has the Rev-15 note-50/52 citations (815 inventory items) but no General Note 29 inventory items. The #1311 generator explicitly defers Note 52(i): the rule is limited to a textile or apparel good as defined by GN 29(d)(v) that is entered duty-free under DR-CAFTA. GN 29 ingest is therefore necessary to ground the product definition.

Reaching zero also requires an entry-level fact that the import actually claims/qualifies for DR-CAFTA duty-free treatment. Yale uses an HS2-by-country preference-utilization proxy; country plus HTS membership alone is not proof that each entry is eligible. Thus:

- GN 29 ingest is required to encode the legal product scope.
- A DR-CAFTA duty-free claim/eligibility input and entry-level wiring are also required.
- Those changes can address only the 17,404 CAFTA units; they cannot clear the 148,390 old residual or the 229,536 new non-CAFTA disagreements.

## New non-CAFTA disagreements

The 229,536 new non-CAFTA units are 114,768 exact component-interval cells. The source-backed and selected-input-backed taxonomy conserves every unit:

| Exclusive category | Units | Distinct cells | Interpretation |
|---|---:|---:|---|
| Brazil aircraft | 414 | 207 | Yale utilization proxy versus full listed rate |
| Brazil pharma | 84 | 42 | Yale utilization proxy versus full listed rate |
| Forced-labor aircraft | 40,392 | 20,196 | Yale utilization proxy versus full listed rate |
| Forced-labor pharma | 1,058 | 529 | Yale utilization proxy versus full listed rate |
| Section 232 scope mask | 185,954 | 92,977 | Yale fully masks Section 232-scope articles; listed flag still charges |
| Chapter 98 handling | 1,514 | 757 | Entry/context handling absent from the panel component |
| Yale HTS8 statistical broadening | 120 | 60 | Yale HTS8 list covers neighboring HTS10 statistical lines |
| Encoded-full exemption failure | 0 | 0 | No failure of an encoded unconditional full exemption |
| **Total** | **229,536** | **114,768** | |

The Section 232 split is 172,448 forced-labor units and 13,506 Brazil units. Its exclusive subcauses are:

| Section 232 subcause | Forced | Brazil | Total |
|---|---:|---:|---:|
| Engine metal fact exposed but unconsumed | 110,856 | 8,826 | 119,682 |
| Unflagged in-scope annex membership | 31,488 | 2,346 | 33,834 |
| Unflagged heading-program source membership | 30,104 | 2,334 | 32,438 |
| **Total** | **172,448** | **13,506** | **185,954** |

The first 119,682 are a direct target-output wiring disagreement: the engine already exposes entry_is_section_232_covered=true, but the compared panel component does not consume it. Matching Yale on the other 66,272 needs a broader fact surface for annex and heading-program membership. The heading-program population is exactly split in the audit among auto parts, auto vehicles, medium/heavy-duty vehicles and parts, wood, and their overlaps.

The Chapter 98 split is 1,508 forced-labor and 6 Brazil. The 120-unit Yale statistical-broadening population is Brazil-only and has precedence over the Section 232 categorization; 24 of those units also have a positive Section 232 rate.

An interval/rate falsification found no timing explanation: Brazil has the same 2,272 effective cells in all three July interval vintages, forced labor has the same 43,489 in both effective vintages, and there are zero set additions/removals, actual-rate changes, or cause changes. No audited row belongs to Yale's July-31 patented-pharma source population. The smaller forced-labor deltas in capped countries are expected net-MFN formulas, not a cause of these new mismatches.

The deterministic join scanned all 9,913,304 selected rows and joined all 89,346 unmapped interval keys uniquely, with zero missing or duplicate joins. Its detailed source memberships, overlap rules, exact distributions, representative cells, timing checks, and hashes are in:

    reference/us-tariff-schedule/preview-1311/unmapped-cause-audit-receipt.json
    SHA-256 4572f1a121848337bcd0ea797c09e771fc55a3e0efaeb79c195979ddb5a5e29e

Its reproducer is:

    reference/us-tariff-schedule/preview-1311/unmapped_cause_audit.py
    SHA-256 a6a5a0f960c63ef96ea6a85bf9dc912991566e9ed1c8a93772ee5349a7cec166

Two consecutive executions reproduced the receipt byte-for-byte. Its payload digest, excluding its self-hash field, is cd3577aef8ba83ca563a7b192ac0c4022583eb57c619327a37801a3a23c0d54a.

The five Yale HTS8 versus exact HTS10 broadening differences are:

| Yale HTS8 | Exact legal HTS10 |
|---|---|
| 04090000 | 0409000005 |
| 44079902 | 4407990295 |
| 84224091 | 8422409181 |
| 85051100 | 8505110070 |
| 85371091 | 8537109170 |

These are real disagreements against the certificate's Yale target, but they are not all evidence that the legal note tables are wrong. The C6 source describes forced_labor_section_301_component_rate as an explicitly non-exempt panel projection and directs transaction-dependent exceptions to forced_labor_section_301_entry_component_rate. Yale's rate_s301fl instead embeds utilization proxies, a Section 232 scope mask, USMCA machinery, Chapter 98/context rules, and patented-pharma treatment. The official rebind must decide which output semantics the certificate is meant to certify.

### Exact cell list

Every new row is listed in:

    /Users/maxghenis/TheAxiomFoundation/axiom-oracles-cert/reference/us-tariff-schedule/preview-1311/new-mismatch-cells.jsonl.gz

SHA-256:

    7e26a7e746abd4d033b8dcc6b7d95efcece45b1405ac84238011500c84bbe029

It contains exactly 246,940 JSONL rows, including the 17,404 CAFTA rows. Each row carries case_id, probe, slot, interval, revision, HTS line, HTS10, origin, expected, actual, delta, flags, exact CAFTA marker, primary taxonomy, and detail labels.

The compact distinct-cell grouping is embedded at classification.surprises.exact_cells in:

    /Users/maxghenis/TheAxiomFoundation/axiom-oracles-cert/reference/us-tariff-schedule/preview-1311/mismatch-taxonomy-receipt.json

SHA-256:

    3d1a7543d738d6e396e111ff909c245f082146aeeeeef27d57a5da38f30e25de

That array lists all 114,768 non-CAFTA cells with their exact HTS10, origin, revision, interval, probes, case IDs, expected/actual/delta, and category. The row-level file is the practical inspection artifact; the receipt is intentionally about 92 MiB because it embeds the complete grouped list.

Example extraction:

    gzip -cd reference/us-tariff-schedule/preview-1311/new-mismatch-cells.jsonl.gz |
      jq -c 'select(.cafta_52i_exact == false)'

## Scope and execution

The classify ledger was read before evaluation. The two original classes share a 92-chapter footprint:

    01-26, 28-30, 32-73, 75-76, 78-96

The original forced-labor class covers 749,519 interval rows, 13,699 HTS10 codes, 86 origins, and 1,499,038 endpoint units. Brazil covers 46,599 interval rows, 15,547 HTS10 codes, origin BR, and 93,198 endpoint units. Their 1,592,236 component units occupy 1,538,428 distinct endpoint cases because 53,808 cases exercise both target slots.

A flags-only census found newly exposed Yale-zero cells in chapters 74 and 98, so the faithful affected partition is 94 chapters. Chapters 27, 31, 97, 99a, 99b, and 99c were omitted. The evaluation therefore did not blindly rerun the stock full compare:

- 9,913,304 selected interval rows were censused.
- 19,085,544 endpoint records were evaluated.
- All 94 shard hashes validate.
- Engine errors: 0.
- Aggregate shard process time: 23,650.117 seconds (6.569 hours).
- The prior full-run manifest had 19,118,619 endpoints, so the partition avoided 33,075 endpoints.
- The microbenchmark projection was 0.751 wall-clock hours at three workers; the conservative historical 94-shard sum was 10.243 sequential hours, or 3.414 ideal wall-clock hours at three workers.

The evaluation used at most three concurrent engine processes. nice -n 10 was present on the compute commands, but the sandbox denied setpriority with Operation not permitted; execution continued at default priority. This is recorded in the logs.

The generated C6 incidence modules describe the codified state effective 2026-08-03 and explicitly say they are not a historical-vintage panel. The requested preview uses the date-free b16_entry_flags membership extractor to inject those grounded memberships into the certificate's 2026-07-22 through 2026-08-01 panel. This is therefore the requested rebind counterfactual, not a claim that the Rev-15 note text was historically in force on every panel probe.

## Preview compatibility projection

The stock campaign input-contract gate fails closed against C6 because tools/b16_entry_flags.py emits two compatibility aliases not declared as campaign inputs:

- entry_is_brazil_301
- entry_is_forced_labor_301

The declared inputs are entry_is_brazil_301_listed and entry_is_forced_labor_301_listed. The lane-local driver projected away exactly the two undeclared aliases at runtime. It made no campaign, rulespec, toolchain, workflow, or waiver edit.

This compatibility projection is suitable only for the pre-rebind preview. The official post-rebind run should use the stock campaign and a legitimately reconciled input contract; it should not silently reuse the lane projection.

## Conservation checks

All of the following identities and integrity gates pass:

    1,443,846 closed + 148,390 old residual = 1,592,236 original
    148,390 old residual + 246,940 new = 395,330 current mismatches
    22,866 Brazil mismatches + 372,464 forced mismatches = 395,330
    148,390 ignored-old taxonomy rows + 246,940 classified-new rows = 395,330
    17,404 CAFTA + 229,536 non-CAFTA new = 246,940
    41,948 aircraft/pharma + 185,954 Section 232 + 1,514 chapter 98
      + 120 HTS8 broadening = 229,536 non-CAFTA new

Both gzip sidecars pass gzip integrity checks. Their line counts are exactly 395,330 and 246,940. All 94 evaluation shard hashes pass. The taxonomy payload digest independently recomputes to:

    39b8c56a6fbdd7f852cf8d64bd31b7b521ecd5e4c93ee529e5b933a26d1b30e5

The committed selector currently classifies only 68 current units as fed-false-family-forced-labor; 395,262 current units become __unexplained__. That selector result should not be confused with the exact source/input taxonomy above.

## Immutable inputs and pins

| Input | Pin / SHA-256 |
|---|---|
| Cert baseline commit | 903f5b8fba7ae80dcc7d3a5ba00c66ae3fa31da7 |
| Cert baseline tree | 8a67489af6822515a5003ab2bda01777207ca813 |
| Certificate | 211588976fe5e416b982430ec40632731ae063fda4dfb96103e2fb67f509656f |
| Selected intervals | 94af0a2b36c7cde0840220810791672ae494da38f288fd1cb3de1a122eb91826 |
| Routing | 7236c015bee357f33063a3ab7917c1b4ad42390d97ad2ecda26fad9bb21232b3 |
| Disposition ledger | d24e578836db1f5c5e076af600a049140ed499567c8c8d6823074184a706db53 |
| Baseline eval manifest | 5123e201a32c3965d82440c515525c854e9113d7efc84e820bbe878617a83a39 |
| Baseline classification | 8890874d6162ae5acd17c300aa7567101aa77cd151687fa86b67036607748e2f |
| Campaign source | 8358f3e8994547b1a7a16a1818705cd72b75ea321a50c8f9db83e3fb01828150 |
| C6 rulespec commit | 3357f7dc710d18861b1fefdff115e2434e67b988 |
| C6 rulespec tree | c3d530c72344310aa2fdfcebe5aec286b1ad4869 |
| C6 note50 tree | f313eb5be207bb8d561ecb3d6e39ed083fc420c0 |
| C6 note52 tree | edfc26f36d4c83a57a6006f1cd3b1058184bba8a |
| C6 entry flag tool | 8032dde5fe4a9bc14448cc84e338181a69b912e37b74331d89e9d5f9ef746c8a |
| C6 table generator | ffb99f2901c6fc0bf96c30c81e972b6d507e5fd5c0e8d89c34a91dd67c41dd84 |
| Pinned engine commit | ffd8213271947b0189a9dd61a055c1e0e78908a0 |
| Pinned engine tree | 86e78cc74fffe774fe0ba010c0a951ca1dfcc000 |
| Pinned engine binary | 674ca6e70afdccb59c3d6847933bc24b4590105e49db54790f2dcd0bdbbe32d7 |
| Yale commit | c4307e514196618afcbf88cf7fd33746417eeabf |
| Yale tree | d3107eae32ae7ac366b319abd4ab7b13c78d5c3c |
| Yale CAFTA list | a38f8e42e9615b58dc09fd8a661b4a0fdb9d12e2121342a657fae69450215280 |
| Successor corpus selector | e8a66545095eff763e7e1dab473c9848e62a0407b83421bb0e879009e78a7fd9 |
| Successor signed release content | 9591ed6ade8f264f34a79e89b99ae05ac04b19cb1bf6b69480108bdfee1eb435 |

Both /Users/maxghenis/TheAxiomFoundation/_b1wt/rulespec-us/.worktrees/rulespec-us-c6 and /Users/maxghenis/PolicyEngine/_tariff-p5/b1/c6-roots/rulespec-us were clean and equal at the C6 commit/tree. The canonical clone already had the requested commit, so no synchronization mutation was needed. The engine symlink resolved to /Users/maxghenis/TheAxiomFoundation/axiom-rules-engine-pinned/target/release/axiom-rules-engine. The sibling rulespec-us-338 worktree was not touched.

## Preview artifact receipts

All paths below are under:

    /Users/maxghenis/TheAxiomFoundation/axiom-oracles-cert/reference/us-tariff-schedule/preview-1311

| Artifact | SHA-256 |
|---|---|
| declared-input-contract-full.json | 16a216bc48803e89e0ad9452f2bdc1c4fc78a06c4eaa4a958b39958c84fe0f85 |
| declared-input-contract-partition.json | 699b00217825e68cd9ee9e9b881d810ba4bb9cd087aee6351293f46c7122126f |
| input-contract-execution-receipt.json | f54cf918a098768f3b69c8d08d3ea1dde41844f59babbb0055f56e87228e406b |
| provenance-receipt.json | 4a2b408a4abec3fa173dc18571b9668f04199148645a7a4c6d7a46755e3e34d2 |
| evaluation-projection-receipt.json | 6c6487f9474453b8e8975939ba70ef3e5e204d5bfb415e1cc6f541745e867637 |
| static-footprint-census-receipt.json | ec97976d84b49ebc9220cc53d8f72449be2f02e3a4d63979370ff39a987ecc0a |
| eval/MANIFEST.json | 74fc9e5085ac379054e456eb457cdc51032d9cb68542497c080c5fc9c5907b1a |
| shard-verification.log | fad800f2fd830b37815d0e00d29cefbb409c51a4bba77c12b3d43dbf18ace6df |
| target-comparison-classification-receipt.json | 845c4ad0516c03ef4cfb5224f5c5f67f812d42a084db9de52633ca050205f9c7 |
| target-mismatch-cells.jsonl.gz | d5b53173afe489686aff86a4d1d776bf821cb97945e9ebacd5ba6bc912a8b705 |
| mismatch-taxonomy-receipt.json | 3d1a7543d738d6e396e111ff909c245f082146aeeeeef27d57a5da38f30e25de |
| new-mismatch-cells.jsonl.gz | 7e26a7e746abd4d033b8dcc6b7d95efcece45b1405ac84238011500c84bbe029 |
| old-residual-taxonomy-receipt.json | b4f9d26d5a800cf1b0e6e50c6b3935ee18b24ca55bbcc5eecf9e10ab8f829bea |
| unmapped-cause-audit-receipt.json | 4572f1a121848337bcd0ea797c09e771fc55a3e0efaeb79c195979ddb5a5e29e |
| preview_driver.py | c8b757d1447ce6abd21edf217490247b69649a861d23bddabde03bc2849e77dd |
| mismatch_taxonomy.py | efcf9b115fa156d572d56f23566ead852bceef48c32fb5f3680a4619753a0177 |
| old_residual_taxonomy.py | ff5cc00b453547534beaa48f62ef0046c04249a947bff4e92921832465faddf7 |
| unmapped_cause_audit.py | a6a5a0f960c63ef96ea6a85bf9dc912991566e9ed1c8a93772ee5349a7cec166 |
| evaluation.log | cc59bb6bbca4abc37663ad3e70a4a2263e7797576a639f79f69738ad4cfba291 |
| target-compare.log | 2b3710f6335dedae92c542c6e24c79fbb4686b7995119a772c985bcb1238f1b7 |
| mismatch-taxonomy.log | 9c29ea916de85288e1656544b74e74b3d1ca80598e99f075611f9af1ee6e600a |

The lane artifacts are deliberately uncommitted. PROGRESS.md is the only lane bookkeeping surface committed in the cert worktree.

## Exact commands

Working directory:

    cd /Users/maxghenis/TheAxiomFoundation/axiom-oracles-cert

Gates and census:

    .venv/bin/python reference/us-tariff-schedule/preview-1311/preview_driver.py input-contract > reference/us-tariff-schedule/preview-1311/input-contract.log 2>&1
    .venv/bin/python reference/us-tariff-schedule/preview-1311/preview_driver.py projection > reference/us-tariff-schedule/preview-1311/projection.log 2>&1
    nice -n 10 .venv/bin/python reference/us-tariff-schedule/preview-1311/preview_driver.py static-footprint >> reference/us-tariff-schedule/preview-1311/static-footprint.log 2>&1

Affected-partition evaluation and target comparison:

    nice -n 10 .venv/bin/python reference/us-tariff-schedule/preview-1311/preview_driver.py evaluate --workers 3 >> reference/us-tariff-schedule/preview-1311/evaluation.log 2>&1
    nice -n 10 .venv/bin/python reference/us-tariff-schedule/preview-1311/preview_driver.py target-compare-classify >> reference/us-tariff-schedule/preview-1311/target-compare.log 2>&1
    nice -n 10 .venv/bin/python reference/us-tariff-schedule/preview-1311/mismatch_taxonomy.py >> reference/us-tariff-schedule/preview-1311/mismatch-taxonomy.log 2>&1

Old-residual causal audit:

    .venv/bin/python reference/us-tariff-schedule/preview-1311/old_residual_taxonomy.py \
      --mismatch-cells reference/us-tariff-schedule/preview-1311/target-mismatch-cells.jsonl.gz \
      --selected-intervals reference/us-tariff-schedule/selected-intervals.csv.gz \
      --classification-receipt reference/us-tariff-schedule/preview-1311/target-comparison-classification-receipt.json \
      --yale-root /Users/maxghenis/TheAxiomFoundation/_tariff-yale \
      --rulespec-root /Users/maxghenis/PolicyEngine/_tariff-p5/b1/c6-roots/rulespec-us \
      --output reference/us-tariff-schedule/preview-1311/old-residual-taxonomy-receipt.json

Previously unmapped new-disagreement audit:

    .venv/bin/python reference/us-tariff-schedule/preview-1311/unmapped_cause_audit.py

Shard byte verification:

    jq -r '.shards[] | "\(.sha256)  \(.path)"' reference/us-tariff-schedule/preview-1311/eval/MANIFEST.json |
      shasum -a 256 -c - > reference/us-tariff-schedule/preview-1311/shard-verification.log 2>&1

The evaluate command was resumed after an interrupted lane process. Forty-eight shards validated from the current input-derived cache keys, and the remaining shards were computed. The final manifest was then fully rehashed; no shard is accepted solely because a path exists.

## Official post-rebind check

The official run should be stock, full-surface, and independent of this preview projection:

1. Pin the merged rulespec, official corpus selector containing Rev-15 notes plus GN 29 when available, and pinned engine; record commits, trees, binary hash, and clean statuses.
2. Run stock prepass, input-contract, and projection. Reconcile the two compatibility aliases through the official contract rather than projecting them away.
3. Run stock evaluate with at most three workers and resume/cache validation.
4. Run stock compare, classify, witness-replay, and report across every chapter and every certificate slot.
5. Check the exact identities in this report:
   - old classes: 1,443,846 predicted closed and 148,390 predicted residual;
   - CAFTA: 17,404 predicted new residual;
   - new non-CAFTA: 229,536 predicted disagreements;
   - total target-slot mismatches: 395,330.
6. Investigate any deviation at the exact case/probe rows in the two gzip sidecars.
7. Require no regression outside the two target slots before changing certificate disposition.

## Bottom line

Merging #1311 and rebinding the current toolchain is predicted to produce **partial closure, not closure**: 1,443,846 old units close and 148,390 remain. It also turns on 246,940 previously matching Yale-zero units. The exact Note 52(i) CAFTA residual is 17,404 units, and GN 29 ingest plus an entry-level DR-CAFTA claim/eligibility fact are required to drive that population to zero. The 229,536 non-CAFTA new disagreements are fully enumerated and are dominated by the Section 232 scope-mask/output-semantics gap.
