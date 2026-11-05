# TAXSIM disposition migration audit

Baseline: `358f433b9b5511e097f0375cec7e33c815b36a3e`, this change's merge base with `main`. Its unmodified `axiom_oracles/comparison/dispositions.py` bytes hash to `ba8b75b0200fd57282934cb3e91caab71a71fc3f74f95a0e34b3f7bd1aac8100`. The proof loads that module inside the `axiom_oracles.comparison` package, because it imports `pe_axiom_standard` relatively, and first checks that this checkout's `pe_axiom_standard.py` and `conformance/unexplained.py` are byte-identical to the baseline's.

The inherited work was **partial** on the independent-baseline requirement: it migrated all 75 entries and hard-coded three expected digests in `tests/test_dispositions_hardened.py`, but did not supply an independently reconstructed origin/main baseline or cover the slim national report, other TAXSIM reports, and case chunks. The completed proof below reconstructs the old merge from old code **and** old data, removes stored row annotations before merging, and compares complete assignment digests.

## Reproduction and scope

The audit ran `uv run python scripts/prove_disposition_migration.py --write 358f433b9b5511e097f0375cec7e33c815b36a3e`. The script uses the following procedure:

1. Resolve the baseline ref with `git rev-parse`; enumerate paths with `git ls-tree -r --name-only <resolved commit>`. Inspect every tracked report JSON under `reports/` and `dashboard/public/data/`, requiring `suite` and `summary` and TAXSIM in the report engine keys or values. This detects both two-engine comparison reports and the older Axiom/PolicyEngine/TAXSIM grid schema. The scan found 45 reports.
2. Extract the original merge module, all 45 report files, and each applicable original disposition YAML with `git show <resolved commit>:<path>` into a fresh temporary directory. Load the original module with `importlib.util.spec_from_file_location`; no checkout, worktree creation, history rewrite, external engine run, or modified baseline implementation is involved. Original `load_dispositions` validates the original YAML. Its optional source-existence checks use the repository; they validate only that the pre-existing citation paths exist.
3. For each full report, remove each stored `disposition` annotation, then call the original `apply_dispositions` with the original YAML (or `None` for reports without a ledger). Separately remove annotations from the working-tree report and merge current validated YAML with the current module. Compute each side with its own `assignment_digest` implementation. Assert equal digests.
4. The national FIIT dashboard report retains only 1,000 of 26,229 mismatch rows. Verify the `source_report` file SHA, freshly merge the complete source on each side, verify the embedded full `assignment_sha256`, and reconstruct/check every retained row annotation against the fresh full merge. Population bindings must never be rederived from the 1,000-row sample. Compute its retained-row digest separately from the complete-population digest.
5. Compare all six TAXSIM case chunk files and their two indexes byte-for-byte against origin/main, then record their SHA-256 values. These compact case records store disposition kinds but omit entry IDs, so they cannot supply a complete `assignment_digest`. The supporting member-decomposition JSON is a receipt (`axiom_oracles.member_decomposition_receipt.v1`), not a comparison report; it is untouched.

Result: **45/45 report assignment digests equal; 8/8 case artifacts byte-identical**. All 45 report files themselves are also byte-identical to origin/main. The machine-readable proof records independent before/after fields and report-file hashes in [taxsim-disposition-migration-baseline.json](taxsim-disposition-migration-baseline.json). `tests/test_dispositions_migration.py` checks current fresh merges against that frozen baseline, rejects a lost or changed assignment, checks the slim/full source binding, and checks the case artifacts.

## Report assignment digests

Paths below are relative to `dashboard/public/data/` unless they start with `reports/`. Each SHA in the final column is the exact **before = after** assignment digest. The JSON companion stores both fields explicitly.

| Report | Stored mismatch rows | Before = after assignment SHA-256 |
| --- | ---: | --- |
| `axiom-policyengine-taxsim-az-income-tax-liability.json` | 6 | `ce5f27bb0cc9c96f56d89d7795966904fdf097fdf2299f25a399d62c7424d8c1` |
| `axiom-policyengine-taxsim-ca-income-tax-liability.json` | 2 | `e282bab62ac1cc65aecbc71833dcd84012d39fc4b1c3a535b4d63017d7a1d842` |
| `axiom-policyengine-taxsim-co-income-tax-liability.json` | 6 | `7bb724f12638007fd87972491e30319fee1260ff50a66d02d0c07e9849fbdc34` |
| `axiom-policyengine-taxsim-dc-income-tax-liability.json` | 6 | `50b49cfb75f2360779b9f6b4ab3e9e9eabe48286b53e1c0d14692280e1ef9d26` |
| `axiom-policyengine-taxsim-ga-income-tax-liability.json` | 6 | `d50479b46428a5fb81e7b933645dd6029fa5e678cdca22bf954332b37beca024` |
| `axiom-policyengine-taxsim-hi-income-tax-liability.json` | 6 | `c193bd929bc82fc567e985aea6b9648deadc908b98a3c49c839e306d55acd523` |
| `axiom-policyengine-taxsim-ia-income-tax-liability.json` | 6 | `1012d359405e079879626fd286d1a7263efd41bd2a56350752bb6e864c1a3f03` |
| `axiom-policyengine-taxsim-id-income-tax-liability.json` | 6 | `6f846c4e5fa1ebd5c9ef860de8ed0d2fd2a44a1970fd669f3f816d26fc46c396` |
| `axiom-policyengine-taxsim-il-income-tax-liability.json` | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| `axiom-policyengine-taxsim-in-income-tax-liability.json` | 6 | `582b1f8e19cf3e42c1b8d2c3f6069f8cfc291dd2e96fbf9bf43b65bc76f482e9` |
| `axiom-policyengine-taxsim-ks-income-tax-liability.json` | 6 | `7a49e5f7cce6b2180f5ff3a696d5218975a8e9f9ccb4b7c6bc5fe92b26d59902` |
| `axiom-policyengine-taxsim-ky-income-tax-liability.json` | 6 | `e3e1b47c76e24b6a8a9f44981c4d5cb60a0fa29d65b4046ec19b942e660f6584` |
| `axiom-policyengine-taxsim-la-income-tax-liability.json` | 6 | `bd30e5d45eb3bac557792ef5bd9d5c09a17b996c5f48d5da4221cb5d99be738a` |
| `axiom-policyengine-taxsim-ma-income-tax-liability.json` | 6 | `f9e16337986d4a172e627c50c0b5b611d6812e90179ad93bd2487b472c2a3117` |
| `axiom-policyengine-taxsim-md-income-tax-liability.json` | 6 | `4cee0f5d6d495caeb27d55ac682b2667b09113f03820c701b9f142c6c0e24ee2` |
| `axiom-policyengine-taxsim-me-income-tax-liability.json` | 6 | `d95a70c264294840134a94873656ef8ca83d2d5f2d6e44af084bdfecc2e624f2` |
| `axiom-policyengine-taxsim-mi-income-tax-liability.json` | 6 | `c4feec2fa4da198428c4b65a38c7527db68838f19ed11aef40ede124f7ec8c91` |
| `axiom-policyengine-taxsim-mn-income-tax-liability.json` | 6 | `a63673f09f6327c0a3dfcd68139f5b95a3f33fa596827dbd61614de126745ef6` |
| `axiom-policyengine-taxsim-mo-income-tax-liability.json` | 6 | `a2efda708e746c393b3f39c860b4333ac942b9a63c7beefcdde3faefbe72b876` |
| `axiom-policyengine-taxsim-ms-income-tax-liability.json` | 6 | `e8f95d1118799e5800a04a311d86cab5becccf73f5a8e2088c21abcf18b39942` |
| `axiom-policyengine-taxsim-mt-income-tax-liability.json` | 6 | `ba9fcf2d93ac912dc8136f955f8d759aaf6df3cfc86f42b31a9d1a6132001571` |
| `axiom-policyengine-taxsim-nc-income-tax-liability.json` | 6 | `f9c9a099df7ae360782e558f2c61af9c6eccab90bf908785b710cc3e3c20aa2c` |
| `axiom-policyengine-taxsim-nd-income-tax-liability.json` | 6 | `87649b2414d0f6a77054c3d7f2c941a46f3cd552cc9ef9383f9d9e928d13f70e` |
| `axiom-policyengine-taxsim-ne-income-tax-liability.json` | 6 | `77549bd7f59e976be3159d1ce9f44c0c77a07a474eb45c179e814a48ddb8600d` |
| `axiom-policyengine-taxsim-nj-income-tax-liability.json` | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| `axiom-policyengine-taxsim-nm-income-tax-liability.json` | 6 | `12d7d5a26efdb6cbf4b1da480e2c64832c1c27c5c297aa7bb4bae063341fdae1` |
| `axiom-policyengine-taxsim-ny-income-tax-liability.json` | 6 | `3ccf8b2ae4484a45d34815082023bce219cef52d1db9cf4c039271b0f380581c` |
| `axiom-policyengine-taxsim-oh-income-tax-liability.json` | 6 | `f9c334c3d8cceffd45acae6ef8e28465736ba3d032a81a5fe208a924fc2d1818` |
| `axiom-policyengine-taxsim-ok-income-tax-liability.json` | 6 | `f39f3f5f8f938da0558b30b8c075cad60fd8f30f2afa65781a2688f6e00a0dad` |
| `axiom-policyengine-taxsim-or-income-tax-liability.json` | 12 | `b0b4215dd365a9e2add788e7a0a1e272e2ff4235bafbf0af12d2d296fe4e394b` |
| `axiom-policyengine-taxsim-pa-income-tax-liability.json` | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| `axiom-policyengine-taxsim-ri-income-tax-liability.json` | 12 | `b195eb8d56a66b26bf72b81d4cec80ecbcb887d14e709f78aa2d0b316415e3ad` |
| `axiom-policyengine-taxsim-sc-income-tax-liability.json` | 6 | `26536a4f4b3dc293a65a24abc3534e80a0666eb8ecadf483a80da2818042c1e2` |
| `axiom-policyengine-taxsim-ut-income-tax-liability.json` | 6 | `6a2e49e923218701e9a4ef0211c04d81720d7e10ce3e66bb0777c71386a1f87c` |
| `axiom-policyengine-taxsim-va-income-tax-liability.json` | 6 | `b5b4d810499e00d974c90aa564a211dfa07183b2322c9e67a2c34d5e8642ee5e` |
| `axiom-policyengine-taxsim-vt-income-tax-liability.json` | 6 | `1fbe4ef5acecb4b6b8178531dc413e8791e79e5166173a2a59c6fac23248745e` |
| `axiom-policyengine-taxsim-wa-income-tax-liability.json` | 6 | `2c9141d4acc6dc6b26faac3a9c56ea40de6e05232f2da85e2c3ed2e721660615` |
| `axiom-policyengine-taxsim-wi-income-tax-liability.json` | 10 | `bf00db6bb42182b5e08947e14cba9248ce85c3905483a5ec0a111dc046f759fc` |
| `axiom-policyengine-taxsim-wv-income-tax-liability.json` | 6 | `29cb93a077c8216239ffd9b81cedf685fd27f4f476be5f611bbef7eca9a805ca` |
| `axiom-taxsim-co-state-income-tax-ecps.json` | 530 | `0cc14e9c2027b1f9397174836cfeab1157ab93a986866b7c9f5150008684069f` |
| `axiom-taxsim-co-tax-intersection-ecps.json` | 2117 | `ecfa30855fc9130c7ae192b0d7b5cbaf43231d4b2d3437b665e08d78ff87e47c` |
| `axiom-taxsim-fiit-ecps.json` | 1000 | `6f9a3b8b88c919451f1165b54ddd817d85ad4c940fa8f9f8afffb88a39f8ed22` |
| `policyengine-taxsim.json` | 7 | `b6c6557481bc5c7e70a9566ca3d13958b6f3ac81661f5057dcffae51f85e9578` |
| `reports/axiom-policyengine-taxsim-ut-income-tax-liability-all-2026-07-27.json` | 6 | `6a2e49e923218701e9a4ef0211c04d81720d7e10ce3e66bb0777c71386a1f87c` |
| `reports/axiom-taxsim-fiit-ecps-verify-2026-08-28.json` | 26229 | `2a144e710e3875c3e247abea5861c5c5eca3b6a9b3d81054e5b19a8ac80299dc` |

The FIIT dashboard embeds full-population assignment SHA-256 `2a144e710e3875c3e247abea5861c5c5eca3b6a9b3d81054e5b19a8ac80299dc`; its retained-row digest is `6f9a3b8b88c919451f1165b54ddd817d85ad4c940fa8f9f8afffb88a39f8ed22`. These represent different populations and both are unchanged.

## Case artifacts

| Path under dashboard/public/data/cases/ | Unchanged file SHA-256 |
| --- | --- |
| `co-state-income-tax-taxsim/chunk-0.json` | `f5f7c9a15a6c2726cde2abc1a716a4f23f9b98fa3c3242e5dec5678d38c5a91c` |
| `co-state-income-tax-taxsim/chunk-1.json` | `d2b7e69dc7ac6641721b11c2849473e1a161aef8f95b4cc891aa2455dda45287` |
| `co-state-income-tax-taxsim/chunk-2.json` | `52630500dd4bd57dfc7f1b39a75bdcd51b2e4caddde51571fc9f0e76e841e9b3` |
| `co-state-income-tax-taxsim/index.json` | `e0973ac10ede0f53e490dca11a917e27bd104cfef279e55a6d018edc2dbf1e3b` |
| `co-tax-intersection-taxsim/chunk-0.json` | `a03e8296e8a0e1bd3b8d7e520a83e89c5f8a335d0f204296240471498584811d` |
| `co-tax-intersection-taxsim/chunk-1.json` | `f5aa74018aea8bfb8166b155ff27755f399cee792c8f8e9873d9fde02776f869` |
| `co-tax-intersection-taxsim/chunk-2.json` | `027e1cf30ad9f7302affa79dece66211daa6fd241baf0ecf2ccfbea1e3eb2f04` |
| `co-tax-intersection-taxsim/index.json` | `3486acc2514c7c0d232ca46946be387a67f1c833c4914b9cf5a8d3a75606f1de` |

## Identity and evidence findings

All three migrated suite reports, including the full FIIT source, record `provenance.oracle.name: taxsim` and PolicyEngine package versions, but **none records any TAXSIM binary SHA-256, `engine_identity.taxsim.binaries`, or `provenance.oracle.policyengine_taxsim` version**. The origin/main dependency pin and mechanism prose mention 2.30.0; they do not prove which package generated a historical report. The migration therefore uses the explicit additive `oracle_binding: {identity_unrecorded: true}` on all 75 entries, with no invented historical package version. A future recorded version or binary expires these bindings. Historical reports lacking identity cannot detect an unrecorded repin; the exact population bindings still detect changed selected rows. A regenerated report must record the TAXSIM binary that produced it (`engine_identity.taxsim`, which the runner now writes).

The original schema ID stays `axiom_oracles.dispositions.v1`; the additions preserve existing non-TAXSIM ledgers. The 75 migrated entries comprise 71 `case_selector` entries carrying count/value population hashes and four `case_id` entries carrying both exact side values. Current entry-level attribution counts are 31 taxsim, 10 axiom, 18 convention, 10 input, 6 two_sided; three entries also carry per-case exceptions (`attribution_by_case`).

Twenty-three entries carry 25 row-arithmetic checks, all inspecting an actual side value or signed difference. None uses a tautology such as `left - right - difference = 0`. The checks cover zero-output classes, fixed/list-valued deduction fingerprints, flat Colorado offsets, and fixed composite deltas. The remaining entries retain citations where the historical mechanism needs household facts or intermediate outputs that mismatch rows do not store. Constant arithmetic is retained as historical explanatory context, never as the sole TAXSIM reconciliation. This audit validates stored arithmetic and attribution against inherited descriptions; it does not rerun engines or establish tax law from engine outputs.

## Attribution review

origin/main carries no `attribution` on any of the 75 entries, so every value below is new in this change. Each row records the reviewed choice and its YAML entry line. The leading-ingredient rule applies throughout: a composite takes the attribution of its largest member. Unmarked entries follow the explicit side, input limitation, or convention described in their inherited mechanism. The review notes below identify every judgment or uncertainty found in this audit; the original mechanism/evidence text and disposition kinds are preserved.

| Ledger and entry line | Entry | Attribution | Review note |
| --- | --- | --- | --- |
| `co-state-income-tax-taxsim.yaml:5` | `taxsim-co-flat-30-8-filing-status-offset` | `taxsim` | Follows the inherited mechanism. |
| `co-state-income-tax-taxsim.yaml:174` | `taxsim-co-flat-20-7-filing-status-offset` | `taxsim` | Follows the inherited mechanism. |
| `co-state-income-tax-taxsim.yaml:245` | `taxsim-co-refundable-credit-vintage` | `taxsim` | Follows the inherited mechanism. |
| `co-state-income-tax-taxsim.yaml:648` | `co-state-open-rows-axiom-pe-divergent` | `taxsim`; `convention` for 136208 and 59285 | Five rows decompose to the TAXSIM-attributed EITC-coupling and credit-vintage classes. Rows 136208 (auto head-of-household standard deduction) and 59285 (automatic itemization) decompose to ingredients the ledger attributes to `convention`, recorded in `attribution_by_case`. The Axiom reference rests on the PE-divergence dispositions, not statute. See [Evidence for the contested calls](#evidence-for-the-contested-calls). |
| `co-tax-intersection-taxsim.yaml:5` | `taxsim-2026-ctc-child-credit-machinery-absent` | `taxsim` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:249` | `taxsim-2026-eitc-with-children-absent` | `taxsim` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:326` | `taxsim-input-lacks-blindness-column-63f-increments` | `input` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:391` | `axiom-3101-oasdi-contribution-base-cap-missing` | `axiom` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:625` | `axiom-seca-chain-drift-pending-triage` | `axiom` | Inherited provisional Axiom attribution: mechanism explicitly says no single-rate reconciliation and pending triage. Attribution is not newly proven. |
| `co-tax-intersection-taxsim.yaml:751` | `liability-composite-of-member-classes-and-niit-addmed-scope` | `two_sided` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:1192` | `taxsim-blindness-63f-extension-taxable_income` | `input` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:1253` | `taxsim-blindness-63f-extension-tax_before_credits` | `input` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:1305` | `taxsim-blindness-63f-extension-liability` | `input` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:1355` | `capgains-worksheet-bucket-routing-tbc` | `convention` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:1426` | `taxsim-qbid-rental-convention-taxable-income` | `convention` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:1604` | `taxsim-co-flat-30-8-filing-status-offset-intersection` | `taxsim` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:1773` | `taxsim-co-flat-20-7-filing-status-offset-intersection` | `taxsim` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:1844` | `taxsim-co-refundable-credit-vintage` | `taxsim` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:2139` | `taxsim-2026-eitc-childless-schedule-applied` | `taxsim` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:2190` | `taxsim-2026-ctc-machinery-absent-refundable-arm` | `taxsim` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:2236` | `capgains-worksheet-bucket-routing-tbc-postdividendfix` | `convention` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:2440` | `taxsim-fiitax-surtax-scope-liability` | `convention` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:2495` | `taxsim-co-refundable-credit-vintage-intersection-echo` | `taxsim` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:2563` | `taxsim-2026-credit-machinery-liability-refundable-arm-zero-tbc` | `taxsim` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:2606` | `taxsim-2026-ctc-machinery-liability-nonrefundable-multiples` | `taxsim` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:2635` | `taxsim-qbid-rental-convention-tbc-bracket-chain` | `convention` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:2683` | `taxsim-blindness-63f-taxable-income-zero-floor` | `input` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:2712` | `taxsim-blindness-63f-plus-qbid-floor-taxable-income` | `input` | Retain input for blindness-led composite, although it also contains the documented rental/QBID convention. |
| `co-tax-intersection-taxsim.yaml:2740` | `axiom-seca-chain-drift-taxable-income-propagation` | `axiom` | Inherited provisional Axiom parent attribution; propagation also includes a blindness input ingredient on one row. |
| `co-tax-intersection-taxsim.yaml:2771` | `axiom-seca-chain-drift-tbc-bracket-propagation` | `axiom` | Inherited provisional Axiom parent attribution, propagated through a bracket rate. |
| `co-tax-intersection-taxsim.yaml:2810` | `taxsim-auto-hoh-standard-deduction` | `convention` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:2854` | `taxsim-auto-hoh-tax-before-credits` | `convention` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:2903` | `taxsim-auto-hoh-liability` | `convention` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:2948` | `taxsim-auto-itemized-state-tax-tax-before-credits` | `convention` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:2987` | `taxsim-auto-itemized-state-tax-liability` | `convention` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:3026` | `taxsim-auto-itemized-state-tax-standard-deduction` | `convention` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:3061` | `taxsim-qbid-rental-convention-tax-before-credits` | `convention` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:3201` | `taxsim-2026-capgains-zero-threshold-vintage` | `taxsim` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:3267` | `liability-composite-of-member-classes-and-niit-scope-r2` | `two_sided` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:3486` | `taxsim-co-credit-stack-vintage-intersection-lane` | `taxsim` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:3614` | `co-intersection-state-open-rows-axiom-pe-divergent` | `taxsim`; `convention` for 136208 and 59285 | Same split as co-state-open-rows-axiom-pe-divergent. |
| `co-tax-intersection-taxsim.yaml:3707` | `taxsim-2026-amt-parameter-vintage` | `taxsim` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:3789` | `taxsim-qbid-wage-limit-and-floor-vintage-taxable-income` | `taxsim` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:3845` | `taxsim-2026-capgains-bracket-set-vintage` | `taxsim` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:3958` | `se-loss-461l-cap-vintage-two-sided` | `two_sided` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:4003` | `taxsim-qbid-seca-member-composite-taxable-income` | `taxsim`; `convention` for 7 rows | Per-row leading member from the decomposition receipt: 18 rows lead with a TAXSIM QBID member, 7 with a bridge convention. See [Evidence for the contested calls](#evidence-for-the-contested-calls). |
| `co-tax-intersection-taxsim.yaml:4115` | `taxsim-input-gssi-earners-scope-taxable-income` | `input` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:4172` | `se-loss-461l-cap-vintage-two-sided-extension` | `two_sided` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:4235` | `taxsim-blindness-63f-and-qbid-composite-taxable-income` | `convention` | Led by the QBID rental convention (6,731.31) over the 63(f) blindness increment (1,650.00). |
| `co-tax-intersection-taxsim.yaml:4275` | `taxsim-auto-hoh-and-qbid-composite-taxable-income` | `convention` | Retain convention for auto-HoH-led composite, although it also names a TAXSIM QBID floor machinery gap. |
| `co-tax-intersection-taxsim.yaml:4315` | `taxsim-auto-itemized-salt-contents-taxable-income` | `convention` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:4352` | `amt-partiii-routing-vs-taxsim-amt-vintage` | `two_sided` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:4422` | `taxsim-2026-credit-machinery-liability-composite-eitc-refundable-ctc` | `taxsim` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:4483` | `taxsim-2026-ctc-machinery-absent-extension` | `taxsim` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:4524` | `axiom-eitc-phaseout-income-se-loss-not-netted` | `axiom` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:5` | `taxsim-2026-eitc-child-machinery-absent` | `taxsim` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:4120` | `taxsim-input-lacks-blindness-column-63f-increments` | `input` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:6200` | `axiom-uncapped-oasdi-flat-765-wage-only` | `axiom` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:17378` | `axiom-uncapped-oasdi-flat-765-with-uncapped-seca` | `axiom` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:18258` | `taxsim-2026-eitc-childless-schedule-applied-to-units-with-children` | `taxsim` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:19669` | `axiom-seca-medicare-rate-only` | `axiom` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:25947` | `axiom-seca-medicare-rate-only-1402b2-gate` | `taxsim` (provisional) | The mechanism (the binary includes SE below the 1402(b)(2) threshold) explains 169 of 217 rows. 48 rows and the `axiom_encoding_gap` kind are open questions for the lane owner. See [Evidence for the contested calls](#evidence-for-the-contested-calls). |
| `fiit-taxsim-ecps.yaml:26202` | `taxsim-auto-itemized-standard-deduction-zeroed` | `convention` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:26484` | `taxsim-auto-hoh-standard-deduction` | `convention` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:26554` | `taxsim-childless-eitc-parameter-vintage` | `taxsim` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:26630` | `taxsim-input-format-lacks-alaska-pfd-eitc` | `input` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:26679` | `taxsim-binary-2025-parameter-fallback` | `taxsim` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:26719` | `ecps-projection-dependent-se-income-fica` | `input` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:26762` | `axiom-seca-medicare-rate-only-r2-leftovers` | `axiom` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:26802` | `taxsim-binary-2025-parameter-fallback-r2-standard-deduction` | `taxsim` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:26835` | `taxsim-auto-itemized-standard-deduction-zeroed-r2` | `convention` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:26865` | `taxsim-childless-eitc-parameter-vintage-r2` | `taxsim` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:26892` | `taxsim-2026-eitc-investment-limit-vintage` | `taxsim` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:26921` | `taxsim-childless-schedule-and-axiom-earned-netting-composite-eitc` | `two_sided` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:26983` | `axiom-eitc-earned-income-se-loss-not-netted` | `axiom` | Follows the inherited mechanism. |

The three SECA-chain pending-triage mechanisms are pre-existing attribution limitations, not new independent causal proofs. The two previously open Colorado classes also explicitly rely on an accepted reference after bridge dispositions, and the 1402(b)(2) gate entry is provisional (above). Those classifications remain review questions for the ledger owner; changing their row assignments is outside this compatibility migration.

## Evidence for the contested calls

`tests/test_dispositions_attribution_evidence.py` re-derives three of the calls below from a committed file: the blindness-and-QBID composite and the QBID/SECA composite from the member-decomposition receipt, and the 1402(b)(2) gate from the full FIIT report. No committed file decomposes the open-rows residuals, so its fourth test checks only that the YAML names the two exceptions and that the mechanism text names both cases.

### `taxsim-blindness-63f-and-qbid-composite-taxable-income`: `convention`

The entry's own arithmetic is 6,731.31 (TAXSIM QBID 0 against Axiom's 0.2 x 33,656.56 on the rental QBI base, the dispositioned rental-in-QBI convention) + 1,650.00 (the 63(f) blindness increment TAXSIM's input cannot carry) = 8,381.31. The convention member leads, so the composite is `convention`. By the same rule `taxsim-blindness-63f-plus-qbid-floor-taxable-income` (2,050 + 400) stays `input` and `taxsim-auto-hoh-and-qbid-composite-taxable-income` (8,050 - 474.66) stays `convention`.

### `co-state-open-rows-axiom-pe-divergent` and `co-intersection-state-open-rows-axiom-pe-divergent`: `taxsim`, with two `convention` rows

The mechanism decomposes each row as siitax = staxbc - sctc - sptcr - 0.5 x v25. Per the mechanism, rows 135552, 135799, 135880, 136404 and 58696 decompose to the Colorado EITC coupling of the 2026 childless federal schedule and the CO child-credit and family-affordability vintage. That decomposition rests on TAXSIM values from a rerun no committed file holds. The ledger attributes both classes to `taxsim` (`taxsim-2026-eitc-childless-schedule-applied`, `taxsim-co-refundable-credit-vintage`). Row 136208 (state residual 503.90 in both reports) is led by TAXSIM's auto head-of-household standard deduction. The ledger's `taxsim-auto-hoh-and-qbid-composite-taxable-income` splits the same unit's federal taxable-income residual, 7,575.34, into that member (+8,050.00) and TAXSIM's missing QBID floor (-474.66). The leading member is taken as the state row's attribution; no committed file decomposes the 503.90 itself. The mechanism's "10,317.46 - 37.82" is TAXSIM's own state value from a rerun that no committed file holds, not a decomposition of the residual. Row 59285 (state residual -786.80 in the state report and -727.09 in the intersection report) is called for TAXSIM's automatic itemization of its own state tax from the mechanism alone: nothing committed reconciles either residual to it. The ledger attributes both ingredients to `convention` (`taxsim-auto-hoh-*`, `taxsim-auto-itemized-state-tax-*`), so `attribution_by_case` records them. These two rows are the least evidenced calls here, and they are open for the lane owner. The entries are not split: a split would change the entry id on two annotated rows of each committed report, and so those reports' bytes, which the published-report gates hold fixed. The Axiom value is the reference only because the Axiom-vs-PE divergence on these units is dispositioned as `bridge_artifact`; it was not verified independently against statute.

### `taxsim-qbid-seca-member-composite-taxable-income`: `taxsim`, with seven `convention` rows

Each row's residual is the sum of a QBID member and an SE-ALD member in `reports/axiom-taxsim-co-tax-intersection-ecps-member-decomposition-2026-08-31.json`. The leading member decides the row:

- A positive QBID member is TAXSIM's QBID exceeding Axiom's: TAXSIM applies no 199A(b)(3) phase-in (`taxsim`).
- A negative member under $400 is Axiom's statutory $400 minimum, which TAXSIM lacks (`taxsim`).
- A larger negative member can come only from the QBI-base difference, the rental-in-QBI bridge convention (`convention`, as `taxsim-qbid-rental-convention-taxable-income`).
- The -93.00 SE-ALD member is the bridge's PolicyEngine-matching OASDI base (186,000 against 184,500), a bridge convention (`convention`).

| Unit | Residual | QBID member | SE-ALD member | Leading member | Attribution |
| ---: | ---: | ---: | ---: | --- | --- |
| 135586 | -1,271.63 | -1,271.62 |  | QBID: QBI-base difference (rental-in-QBI convention) | `convention` |
| 58620 | 1,314.68 | 1,286.11 | 28.58 | QBID: TAXSIM lacks the 199A(b)(3) phase-in | `taxsim` |
| 58643 | -2,479.65 | -2,480.11 | 0.46 | QBID: QBI-base difference (rental-in-QBI convention) | `convention` |
| 58645 | -2,867.54 | -2,867.54 |  | QBID: QBI-base difference (rental-in-QBI convention) | `convention` |
| 58942 | 1,711.24 | 1,804.25 | -93.00 | QBID: TAXSIM lacks the 199A(b)(3) phase-in | `taxsim` |
| 59264 | -4,819.53 | -4,819.53 |  | QBID: QBI-base difference (rental-in-QBI convention) | `convention` |
| 136114 | -1,298.78 | -1,298.78 |  | QBID: QBI-base difference (rental-in-QBI convention) | `convention` |
| 136327 | -180.73 | -180.73 |  | QBID: TAXSIM lacks the $400 minimum | `taxsim` |
| 136399 | -74.40 | 18.60 | -93.00 | SE-ALD: bridge OASDI base (-93.00) | `convention` |
| 136429 | -1,371.54 | -1,371.53 |  | QBID: QBI-base difference (rental-in-QBI convention) | `convention` |
| 154724 | 139,270.87 | 134,531.46 | 4,739.42 | QBID: TAXSIM lacks the 199A(b)(3) phase-in | `taxsim` |
| 155406 | 2,248.63 | 2,167.83 | 80.79 | QBID: TAXSIM lacks the 199A(b)(3) phase-in | `taxsim` |
| 156147 | 45,137.07 | 45,230.07 | -93.00 | QBID: TAXSIM lacks the 199A(b)(3) phase-in | `taxsim` |
| 156467 | 28.51 | 26.69 | 1.82 | QBID: TAXSIM lacks the 199A(b)(3) phase-in | `taxsim` |
| 156651 | 54,781.87 | 54,266.59 | 515.28 | QBID: TAXSIM lacks the 199A(b)(3) phase-in | `taxsim` |
| 157013 | 95,158.92 | 94,225.25 | 933.66 | QBID: TAXSIM lacks the 199A(b)(3) phase-in | `taxsim` |
| 157251 | 98.85 | 80.47 | 18.38 | QBID: TAXSIM lacks the 199A(b)(3) phase-in | `taxsim` |
| 157317 | 288,676.39 | 283,076.17 | 5,600.22 | QBID: TAXSIM lacks the 199A(b)(3) phase-in | `taxsim` |
| 157868 | 41,546.31 | 41,639.32 | -93.00 | QBID: TAXSIM lacks the 199A(b)(3) phase-in | `taxsim` |
| 161870 | 73,939.11 | 71,269.82 | 2,669.29 | QBID: TAXSIM lacks the 199A(b)(3) phase-in | `taxsim` |
| 161979 | 44,397.67 | 42,788.74 | 1,608.92 | QBID: TAXSIM lacks the 199A(b)(3) phase-in | `taxsim` |
| 163020 | 37,893.91 | 36,515.96 | 1,377.94 | QBID: TAXSIM lacks the 199A(b)(3) phase-in | `taxsim` |
| 164227 | 34.92 | 32.42 | 2.49 | QBID: TAXSIM lacks the 199A(b)(3) phase-in | `taxsim` |
| 164548 | 159,377.94 | 157,227.99 | 2,149.95 | QBID: TAXSIM lacks the 199A(b)(3) phase-in | `taxsim` |
| 164633 | 4,193,224.92 | 4,107,604.76 | 85,620.15 | QBID: TAXSIM lacks the 199A(b)(3) phase-in | `taxsim` |

### `axiom-seca-medicare-rate-only-1402b2-gate`: `taxsim`, provisional

The mechanism says the binary's SECA base includes net earnings below the 1402(b)(2) $400 threshold, which the Axiom side excludes. That can make TAXSIM higher by at most 0.153 x 400 = 61.20. In the full report (`reports/axiom-taxsim-fiit-ecps-verify-2026-08-28.json`), 169 of the 217 selected rows fit (difference in [-61.20, 0)). The mechanism does not explain the other 48: 47 rows where Axiom is higher (240.99 to 3,227,627.85) and ecps-tax-unit-1907 (-367.37). The report stores no inputs, so they could not be decomposed here. `taxsim` attributes what the mechanism shows. The 48 rows, and a kind (`axiom_encoding_gap`) that a mechanism describing Axiom as correct does not support, are open for the lane owner. The entry's `notes` say so. Changing the kind would change the committed reports' counts, so it is left as it was.

## Non-TAXSIM worker SSC change

`dashboard/public/data/axiom-euromod-be-worker-ssc.json` is byte-identical to origin/main. It is the one non-TAXSIM report with an expired entry (`dataset-uprating-bridge-artifact-resolved`, already listed in origin/main's `expired_entries`). Outside TAXSIM lanes the merge writes `expired_reasons` only when a reason is new to this schema, and this entry's reason is the older `no_live_rows`, so a fresh merge of the report adds no reasons block. The proof checks both the bytes and that fresh merge.

Rerun `uv run python scripts/prove_disposition_migration.py` (it checks against the recorded baseline, and exits 1 if this checkout no longer reproduces it) and `uv run pytest -q tests/test_dispositions_migration.py` to reproduce the proof.
