# B gap cause audit

The independently rechecked **prior partial probes** retain **168 unexplained comparison units and 83 Axiom-attributed-open components**. These counts describe 2,438 previously evaluated cases in CH29, CH62, CH84 and CH94; this audit does not add campaign coverage or estimate full-schedule populations. The run's new full-chapter census must supply the final ranking.

The measured mechanisms support specific encoding work, but do not establish an encoding-only sequence guaranteed to produce 100% numerical agreement. The `9403999020` legal-date/metal-content question and the CAFTA claim/input question remain unresolved. The maintained ruling also deliberately preserves source-backed reference differences under statutory non-exempt semantics (`B/oracles/reference/us-tariff-schedule/output-semantics-ruling.md:5`, `:12`, `:94`). Numerical agreement and zero-unexplained/zero-open closure are different measures.

## Sources and reproduction

The organization rules and the previous lane's `RESULT.md`, `measured-gap-audit.md`, and `source-audit.md` were read first. Audited B is `c62645022a8b2fcb5f9e6afdc2def2c8d68c2baf`. Source files and partial shards were read from the previous workspace, without writing there:

`/Users/maxghenis/.subfleet/worktrees/20260923-140123-yale-campaign-full-v2/yale-full-run/`

Below, `R:` means `B/rulespec-us/`, `O:` means `B/oracles/`, and `Y:` means `/Users/maxghenis/TheAxiomFoundation/_tariff-yale/`. After the local B copy appeared, a separate SHA-256 check verified every individually audited B source against the current copy; see [gap-cause-current-copy-verification.json](gap-cause-current-copy-verification.json). [gap-cause-audit-evidence.json](gap-cause-audit-evidence.json) records their individual hashes, exact sample engine records, prior shard hashes, and reproduced current-selector censuses. `C:` means the pinned corpus file `data/corpus/provisions/us/statute/2026-08-04-usitc-hts-2026-rev15-notes.jsonl` at commit `5cf7556ad3d68aa0596d58f7ac60942bb5db3120`; numbers following `C:` are physical JSONL lines, not printed page numbers.

The verifier reused the prior source-join implementation, redirecting its sole output into this workspace, then independently replayed all four prior bounded shards through the current `compare_record`, `mismatch_signature`, `mismatch_unit`, and `matching_class_id` functions. It compared each reproduced summary, class count, class/slot count, attribution count, and slot count against the existing census. The run verified six exact sample records, five Yale source joins, eleven Yale file hashes, two additional files against pinned Git blobs, and the corpus SHA-256 `0f3ed7ef2efb64383825db65e615959200770e8511c8d4834b16e02892cb9ec8`. Yale's bound commit is `c4307e514196618afcbf88cf7fd33746417eeabf`, tree `d3107eae32ae7ac366b319abd4ab7b13c78d5c3c`.

Reproduction command, invoked with the requested lower-priority wrapper:

```sh
nice -n 10 /Users/maxghenis/TheAxiomFoundation/axiom-oracles/.venv/bin/python \
  yale-b-full/audit_known_gap_sources.py \
  --prior-run /Users/maxghenis/.subfleet/worktrees/20260923-140123-yale-campaign-full-v2/yale-full-run \
  --output yale-b-full/gap-cause-audit-evidence.json
```

The command exited 0 and all verification checks passed. Output is retained in `gap-cause-audit-verification.stdout` and `.stderr`. The wrapper emitted `nice: setpriority: Operation not permitted`, so this audit cannot claim the lower priority was applied. No engine evaluation, official `classify`, network/API access, RuleSpec/selector change, or Git mutation was performed by this audit. A process-list diagnostic was denied by the sandbox (`ps: operation not permitted`) and supplied no process information.

## Ranked known gaps: prior partial probes only

Slots abbreviated below are `br` = `brazil_section_301`, `52` = `forced_labor_section_301`. Rates are proportions, so `0.125` is 12.5%.

| Rank | Family | Chapter | Current class and slot | Unexplained | Axiom-open |
|---:|---|---:|---|---:|---:|
| 1 | `9403999020` applicability difference | 94 | `__unexplained_total__` / total | 82 | 0 |
| 1 | Same | 94 | `__unexplained_component__` / 52 | 80 | 0 |
| 1 | Same | 94 | `__unexplained_component__` / br | 6 | 0 |
| 2 | Missing derivative-aluminum applicability | 84 | `section232-annex-forced-labor` / 52 | 0 | 35 |
| 2 | Same | 84 | `section232-annex-brazil` / br | 0 | 33 |
| 3 | Unconsumed sector-heading applicability | 84 | `section232-heading-forced-labor` / 52 | 0 | 8 |
| 3 | Same | 84 | `section232-heading-brazil` / br | 0 | 2 |
| 4 | CAFTA Note 52(i) | 62 | `cafta-52i-deferred` / 52 | 0 | 5 |
| | **Prior bounded total** | | | **168** | **83** |

CH29's 800 bounded cases contain zero unexplained/open units. CH62 has 640 cases, CH84 800, and CH94 198. These are not full chapters. The 82 unexplained totals are additional comparison units derived from the 86 unexplained components; they are not 82 additional causal defects. `__unexplained_*` are diagnostic buckets, not new ledger dispositions.

| Family | HTS10 | Origin | Date | Slot | Axiom B | Yale |
|---|---|---|---|---|---:|---:|
| Applicability difference | `9403999020` | BR | 2026-07-22 | br | 0 | 0.25 |
| Applicability difference | `9403999020` | MX | 2026-07-24 | 52 | 0 | 0.10 |
| Derivative aluminum | `8467895030` | BR | 2026-07-30 | br | 0.25 | 0 |
| Derivative aluminum | `8467895030` | BR | 2026-07-30 | 52 | 0.125 | 0 |
| Sector heading | `8414308030` | BR | 2026-07-23 | br | 0.25 | 0 |
| Sector heading | `8407344400` | RU | 2026-07-30 | 52 | 0.125 | 0 |
| CAFTA | `6203331040` | CR | 2026-08-01 | 52 | 0.125 | 0 |

## Concrete causes and smallest grounded fixes

**`9403999020`: 168 prior unexplained units.** The exact atom is present at `R:us/policies/usitc/us-tariff-incidence/generated/note16-232-steel.yaml:3449`; its Note 16(c)(vii) source is at `:3382` and August-3 version at `:3396`. `R:tools/b16_entry_flags.py:34` unions every version's values without consulting dates. The resulting steel Boolean (`:134`) contributes to Section-232 coverage (`:142`), which suppresses both overlay scope flags (`:187`). All 198 prior sample records have Axiom Section 232 `0.5`, Yale `0`.

Yale's exact code is Annex 2 effective April 6 (`Y:resources/s232_annex_products.csv:748`); its configured Annex-2 rate is zero (`Y:config/policy_params.yaml:332`). The adapter maps that tier to the rate (`Y:src/model/authority_adapter.R:833`), and the calculator applies it and updates the statutory field (`Y:src/pipeline/06_calculate_rates.R:2615`, `:2812`). Its shared Notes-50/52 mask omits Annex 2 (`:910`), explaining the opposite overlay direction. This is a verified implementation mechanism, not a legal determination that the Yale treatment is correct.

The corpus actually contains `9403.99.9020` under 16(c)(vii) (`C:251`, printed page 241). The governing Note 16(c) heading family and the 15%-metal-weight condition for articles outside chapters 72/73/74/76 are at `C:246`, page 236. Thus deletion of the atom, treating every union member as covered on every date, or blindly copying Yale's rate mask would each skip a material condition. The smallest grounded next action is to reconcile the dated instruments behind the April-6 removal and August-3 codified list, derive the applicable 9903.82 heading from date/origin/article/metal-content facts, then consume Notes 50/52's precise exclusion. If the panel lacks the required facts, a bounded input-comparability treatment requires independent evidence. The existing `vintage-revision-232` selector applies only to `section_232` (`O:reference/us-tariff-schedule/campaign-dispositions.yaml:483`); it does not classify these negative Brazil/note-52 residuals.

**Derivative aluminum: 68 prior open units.** `8467895030` has both Axiom metal flags false and both overlay scope flags true. Yale's verified join returns Annex 1b and statutory Section 232 `0.25`. Corpus Note 16(c)(vi) explicitly names `8467.89.50` (`C:248`, page 238); Note 19(k) also names it (`C:266`, page 256). Yet the production list covers steel under 16(c)(iii)/(iv)/(vii)/(x)/(xi), and aluminum under old 19(b)/(j), omitting 16(c)(vi)/(ix) and 19(k) (`R:tools/generate_incidence_tables.py:78`). The helper's two aluminum groups use only those existing tables (`R:tools/b16_entry_flags.py:101`, `:133`).

The smallest repair is supervised encoding of the omitted derivative-aluminum applicability, including heading, effective dates, origin and metal-content conditions, followed by consumption of the applicable exclusions. Notes 50(a)(vi) and 52(f) supply the exclusion authority (`C:563`, page 553; `C:576`, page 566). Both annex classes remain Axiom-attributed-open (`O:reference/us-tariff-schedule/campaign-dispositions.yaml:245`, `:267`). This specific missing-aluminum cause is demonstrated for the sample; it should not be assigned automatically to every full-schedule annex unit, which may involve other metal/copper families.

**Sector-heading applicability: 10 prior open units.** `R:tools/b16_entry_flags.py:165` explicitly omits copper, vehicle, vehicle-part, wood, MHD, semiconductor and patented-pharmaceutical limbs because no consumed membership table derives them. The helper's overall coverage is only aluminum-or-steel (`:142`). The actual generated CH84 program consumes the resulting Brazil and note-52 flags at `R:us/policies/cbp/us-tariff-schedule/generated/ch84/ch84.yaml:3041`, `:3198`; these are the running schedule formulas, rather than the older witness formulas in the base composition. The generator wiring is `R:tools/generate_schedule_compositions.py:115`.

The pinned joins place both sample HTS10s in vehicle/MHD parts; `8414308030` is at `Y:resources/s232_auto_parts.txt:32` and `Y:resources/s232_mhd_parts.txt:38`, while `8407344400`'s MHD prefix is at `Y:resources/s232_mhd_parts.txt:28`. Both sampled Yale Section-232 values are `0.237625`. The smallest repair is grounded per-article coverage for the expressly enumerated sector headings, retaining all entry/date/origin conditions, then consuming it in both exclusions. A metal-annex outcome does not by itself resolve independent sector-heading treatment. The corpus authority is `C:563`/`:576`; current heading classes remain open at `O:reference/us-tariff-schedule/campaign-dispositions.yaml:333`, `:355`.

**CAFTA: 5 prior open units.** The country overlay negates `article_described_in_heading_9903_05_95` (`R:us/policies/usitc/us-tariff-duty/overlays/section-301/forced-labor-costa-rica-9903-05-33.yaml:36`), but the incidence generator documents that neither the GN29(d)(v) scope nor the CAFTA duty-free claim is implemented/consumed (`R:tools/generate_incidence_tables.py:286`). CH62's actual formula consumes only the generic flag and country rate/floor gates (`R:us/policies/cbp/us-tariff-schedule/generated/ch62/ch62.yaml:3198`). Note 52(i) expressly requires both textile/apparel scope and an entry free of duty under DR-CAFTA (`C:576`).

The smallest repair is to encode GN29 scope and the actual qualifying entry claim/eligibility, and wire that conjunction into Note 52(i). Yale's source labels prefix `62033310` as `fta` (`Y:resources/s301fl_final_country_exemptions.csv:1371`) and its config identifies claim-conditional exemptions modeled with utilization (`Y:config/policy_params.yaml:853`). The exact preference/share-to-statutory-column path was not replayed by this audit. Origin and product membership cannot establish the required claim, and no claim should be turned on solely to match Yale. The maintainer ruling and current selector retain the open attribution (`O:reference/us-tariff-schedule/output-semantics-ruling.md:147`; `O:reference/us-tariff-schedule/campaign-dispositions.yaml:55`).

## Additional source-visible gaps, not measured units here

| Gap | Direct source | Smallest grounded repair |
|---|---|---|
| Note 52(j) country article lists | `R:tools/generate_incidence_tables.py:291` through `:305` identifies thirteen unconsumed country limbs and their overlay inputs. | Encode the thirteen applicable country/article predicates with dates and consume them; use current fresh rows to determine which signatures they explain. |
| Conditional religious-use/sowing articles treated as unconditional | B includes the entire a(iii)/c memberships in unconditional groups (`R:tools/b16_entry_flags.py:116`, `:122`); the generator discloses three Brazil and seven note-52 qualified occurrences (`R:tools/generate_incidence_tables.py:216`, `:325`). | Add and consume the actual use facts. Preserve exact HTS atom widths; do not replace the statutory condition with a broad prefix exemption. |
| Note 52(k) non-ad-valorem equivalents | Missing equivalent-rate branches are documented at `R:tools/generate_incidence_tables.py:306`. Running CH84 floor comparisons subtract only `mfn_ad_valorem_rate` (`R:us/policies/cbp/us-tariff-schedule/generated/ch84/ch84.yaml:3200`, `:3205`). | Derive the prescribed duty/customs-value equivalent, including Korea's properly claimed Special-column branch, from supported quantity/value/claim inputs. |
| Brazil transaction relief and Notes 50/52 reduced 9802 duty bases | `R:tools/generate_incidence_tables.py:161` through `:208` and `:263` through `:276` document unconsumed/missing exceptions and reduced bases. The active schedule consumes the panel-rate formulas (`R:tools/generate_schedule_compositions.py:115`). | Encode and route the qualifying entry facts and reduced duty base into the entry-level outputs. Do not assume neutral panel facts qualify for entry relief. |

These rows are implementation findings, not additional counted blockers, and cannot be added to the table above. The prior receipt's 5,034 Brazil input-scope cases and 133,444 note-52 upper bound are also not fresh mismatch counts.

## Audit of the current diagnostic census

The existing `measure_shards.py` imports the campaign code rather than reproducing its comparison or selector predicates. Its per-chapter hash and case-count checks protect each consumed shard. It classifies each distinct component signature with `matching_class_id`, whose current implementation rejects overlapping selectors (`O:scripts/us_tariff_schedule_campaign.py:1832`). Signatures include HTS10, ISO2, flags, origin regime and revision/interval (`:931`), so memoizing their classes within a chapter preserves the selector identity.

The helper counts an unmatched component as unexplained. A mismatching total is unexplained if any contributing mismatching component is unexplained; otherwise the total is derived from its component classes. This agrees with official aggregation (`:1865`, `:1900`). Axiom-open counts are the components assigned an existing `axiom-attributed-open` entry, not a second allocation of the derived totals. Engine errors become unexplained units. Conservation requires total mismatches to equal summed class/bucket units.

The helper calls `validate_dispositions(entries, {})`, validating the current structured selector schema, but it does not bind a full comparison receipt or enforce the preview-population contract. Official `classify` does both (`:1845`, `:1884`, `:1892`), so its output remains a diagnostic census even with all chapters present. Full coverage and current cache-key acceptance must be established separately by official `evaluate --resume`; this audit does not infer them from a hash-valid historical shard. No selectors were added or widened.

The repair order supported by this prior sample is: resolve the `9403999020` applicability inputs/instruments; encode omitted derivative-aluminum coverage; encode the other applicable sector headings; encode CAFTA scope and actual qualifying claim. Fresh full-schedule units should determine final prioritization. All atomic RuleSpec work must use the supervised encoder as required by the organization rules. No encoding repair was executed in this audit.
