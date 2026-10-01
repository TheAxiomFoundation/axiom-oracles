# TAXSIM disposition migration audit

Baseline: `origin/main` resolved to `69d6e1b121b76b1406dfd8c73a5d45cc12d932cc`. Its unmodified `axiom_oracles/comparison/dispositions.py` bytes hash to `bc1548e356c4aefd0588bc8aa841a95eba407eb0fd82f0e02c66b3cbb8152969`.

The inherited work was **partial** on requirement 6: it migrated all 75 entries and hard-coded three expected digests in `tests/test_dispositions_hardened.py`, but did not supply an independently reconstructed origin/main baseline or cover the slim national report, other TAXSIM reports, and case chunks. The completed proof below reconstructs the old merge from old code **and** old data, removes stored row annotations before merging, and compares complete assignment digests.

## Reproduction and scope

The audit ran `uv run python scripts/prove_disposition_migration.py`. The script uses the following procedure:

1. Resolve `git rev-parse origin/main`; enumerate paths with `git ls-tree -r --name-only <resolved commit>`. Inspect every tracked report JSON under `reports/` and `dashboard/public/data/`, requiring `suite` and `summary` and TAXSIM in the report engine keys or values. This detects both two-engine comparison reports and the older Axiom/PolicyEngine/TAXSIM grid schema. The scan found 45 reports.
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

All three migrated suite reports, including the full FIIT source, record `provenance.oracle.name: taxsim` and PolicyEngine package versions, but **none records any C1 TAXSIM binary SHA, `engine_identity.taxsim.binaries`, or `provenance.oracle.policyengine_taxsim` version**. The origin/main dependency pin and mechanism prose mention 2.30.0; they do not prove which package generated a historical report. The migration therefore uses the explicit additive `oracle_binding: {identity_unrecorded: true}` on all 75 entries, with no invented historical package version. A future recorded version or binary expires these bindings. Historical reports lacking identity cannot detect an unrecorded repin; the exact population bindings still detect changed selected rows. PR1 must record identity on regenerated reports.

The original schema ID stays `axiom_oracles.dispositions.v1`; the additions preserve existing non-TAXSIM ledgers. The 75 migrated entries comprise 71 `case_selector` entries carrying count/value population hashes and four `case_id` entries carrying both exact side values. Current attribution counts are 29 taxsim, 10 axiom, 17 convention, 11 input, and 8 two_sided.

Twenty-three entries carry 25 row-arithmetic checks, all inspecting an actual side value or signed difference. None uses a tautology such as `left - right - difference = 0`. The checks cover zero-output classes, fixed/list-valued deduction fingerprints, flat Colorado offsets, and fixed composite deltas. The remaining entries retain citations where the historical mechanism needs household facts or intermediate outputs that mismatch rows do not store. Constant arithmetic is retained as historical explanatory context, never as the sole TAXSIM reconciliation. This audit validates stored arithmetic and attribution against inherited descriptions; it does not rerun engines or establish tax law from engine outputs.

## Attribution review

Each row records the reviewed migration choice and its YAML entry line. Unmarked entries follow the explicit side, input limitation, or convention described in their inherited mechanism. The review notes below identify every judgment or uncertainty found in this audit; the original mechanism/evidence text and disposition kinds are preserved.

| Ledger and entry line | Entry | Attribution | Review note |
| --- | --- | --- | --- |
| `co-state-income-tax-taxsim.yaml:5` | `taxsim-co-flat-30-8-filing-status-offset` | `taxsim` | Follows the inherited mechanism. |
| `co-state-income-tax-taxsim.yaml:174` | `taxsim-co-flat-20-7-filing-status-offset` | `taxsim` | Follows the inherited mechanism. |
| `co-state-income-tax-taxsim.yaml:245` | `taxsim-co-refundable-credit-vintage` | `taxsim` | Follows the inherited mechanism. |
| `co-state-income-tax-taxsim.yaml:648` | `co-state-open-rows-axiom-pe-divergent` | `taxsim` | TAXSIM attribution uses an accepted Axiom reference after PE projection dispositions, plus credit/convention decomposition; not independent statutory verification. |
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
| `co-tax-intersection-taxsim.yaml:3614` | `co-intersection-state-open-rows-axiom-pe-divergent` | `taxsim` | Same accepted-reference judgment as co-state-open-rows-axiom-pe-divergent, explicitly qualified in inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:3699` | `taxsim-2026-amt-parameter-vintage` | `taxsim` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:3781` | `taxsim-qbid-wage-limit-and-floor-vintage-taxable-income` | `taxsim` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:3837` | `taxsim-2026-capgains-bracket-set-vintage` | `taxsim` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:3950` | `se-loss-461l-cap-vintage-two-sided` | `two_sided` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:3995` | `taxsim-qbid-seca-member-composite-taxable-income` | `two_sided` | Retain two_sided for TAXSIM QBID/ALD behavior plus deliberate Axiom/PE bridge OASDI-base convention. |
| `co-tax-intersection-taxsim.yaml:4093` | `taxsim-input-gssi-earners-scope-taxable-income` | `input` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:4150` | `se-loss-461l-cap-vintage-two-sided-extension` | `two_sided` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:4213` | `taxsim-blindness-63f-and-qbid-composite-taxable-income` | `input` | Retain input for blindness-led composite, although it also contains the documented rental/QBID convention. |
| `co-tax-intersection-taxsim.yaml:4253` | `taxsim-auto-hoh-and-qbid-composite-taxable-income` | `convention` | Retain convention for auto-HoH-led composite, although it also names a TAXSIM QBID floor machinery gap. |
| `co-tax-intersection-taxsim.yaml:4293` | `taxsim-auto-itemized-salt-contents-taxable-income` | `convention` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:4330` | `amt-partiii-routing-vs-taxsim-amt-vintage` | `two_sided` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:4400` | `taxsim-2026-credit-machinery-liability-composite-eitc-refundable-ctc` | `taxsim` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:4461` | `taxsim-2026-ctc-machinery-absent-extension` | `taxsim` | Follows the inherited mechanism. |
| `co-tax-intersection-taxsim.yaml:4502` | `axiom-eitc-phaseout-income-se-loss-not-netted` | `axiom` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:5` | `taxsim-2026-eitc-child-machinery-absent` | `taxsim` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:4120` | `taxsim-input-lacks-blindness-column-63f-increments` | `input` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:6200` | `axiom-uncapped-oasdi-flat-765-wage-only` | `axiom` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:17378` | `axiom-uncapped-oasdi-flat-765-with-uncapped-seca` | `axiom` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:18258` | `taxsim-2026-eitc-childless-schedule-applied-to-units-with-children` | `taxsim` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:19669` | `axiom-seca-medicare-rate-only` | `axiom` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:25947` | `axiom-seca-medicare-rate-only-1402b2-gate` | `two_sided` | Changed axiom to two_sided: parent Axiom Medicare-only omission and TAXSIM below-threshold inclusion both appear in the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:26194` | `taxsim-auto-itemized-standard-deduction-zeroed` | `convention` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:26476` | `taxsim-auto-hoh-standard-deduction` | `convention` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:26546` | `taxsim-childless-eitc-parameter-vintage` | `taxsim` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:26622` | `taxsim-input-format-lacks-alaska-pfd-eitc` | `input` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:26671` | `taxsim-binary-2025-parameter-fallback` | `taxsim` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:26711` | `ecps-projection-dependent-se-income-fica` | `input` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:26754` | `axiom-seca-medicare-rate-only-r2-leftovers` | `axiom` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:26794` | `taxsim-binary-2025-parameter-fallback-r2-standard-deduction` | `taxsim` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:26827` | `taxsim-auto-itemized-standard-deduction-zeroed-r2` | `convention` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:26857` | `taxsim-childless-eitc-parameter-vintage-r2` | `taxsim` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:26884` | `taxsim-2026-eitc-investment-limit-vintage` | `taxsim` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:26913` | `taxsim-childless-schedule-and-axiom-earned-netting-composite-eitc` | `two_sided` | Follows the inherited mechanism. |
| `fiit-taxsim-ecps.yaml:26975` | `axiom-eitc-earned-income-se-loss-not-netted` | `axiom` | Follows the inherited mechanism. |

The three SECA-chain pending-triage mechanisms are pre-existing attribution limitations, not new independent causal proofs. The two previously open Colorado classes also explicitly rely on an accepted reference after bridge dispositions. Those classifications remain review questions for the ledger owner; changing their row assignments is outside this compatibility migration.

## Non-TAXSIM worker SSC change

The sole diff in `dashboard/public/data/axiom-euromod-be-worker-ssc.json` is the new metadata mapping `expired_reasons: {dataset-uprating-bridge-artifact-resolved: no_live_rows}`. A structural comparison against origin/main is exactly equal after removing that mapping. Origin/main already listed this ID in `expired_entries`; its unchanged `dispositions/be-worker-ssc.yaml` mechanism says the historical bridge artifact was resolved and its gross contribution now matches. No row assignment, count, rate, value, source, or expiry status changes. The generated metadata is therefore intentional and does not reclassify the non-TAXSIM suite.

Rerun `uv run python scripts/prove_disposition_migration.py` and `uv run pytest -q tests/test_dispositions_migration.py` to reproduce the proof.
