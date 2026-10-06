# Measured B gap audit

This audit reads the fresh **bounded** B run in `targeted-B/`; it does not extend
those measurements to the full schedule. The source-join reproduction passed:

```sh
/Users/maxghenis/TheAxiomFoundation/axiom-oracles/.venv/bin/python yale-full-run/audit_measured_gaps.py
```

Observed output: `verification=PASS`, six sample engine records retained, five
source joins, eleven Yale files hash-verified against the committed preview
receipt, two additional files equal to their pinned Git blobs, and corpus SHA-256
`0f3ed7ef2efb64383825db65e615959200770e8511c8d4834b16e02892cb9ec8` matched.
The script independently verifies each consumed raw shard against its census
hash. Evidence is in `measured-gap-evidence.json` and the earlier
`measured-gap-yale-source-joins.json`.

`R:` paths below refer to `B/rulespec-us/`; `O:` to `B/oracles/`; `Y:` to the local
Yale checkout `/Users/maxghenis/TheAxiomFoundation/_tariff-yale`, verified at
commit `c4307e514196618afcbf88cf7fd33746417eeabf`, tree
`d3107eae32ae7ac366b319abd4ab7b13c78d5c3c`. Corpus references mean the ruling's
exact notes JSONL at corpus commit `5cf7556ad3d68aa0596d58f7ac60942bb5db3120`.

## Counts read from the verified bounded census

| Current class / unclassified slot | Units | Representative fresh B value versus Yale |
|---|---:|---|
| `cafta-52i-deferred` | 5 | `6203331040`, CR, 2026-08-01: note 52 `0.125 / 0` |
| `section232-annex-brazil` | 33 | `8467895030`, BR, 2026-07-30: Brazil `0.25 / 0` |
| `section232-annex-forced-labor` | 35 | Same entry: note 52 `0.125 / 0` |
| `section232-heading-brazil` | 2 | `8414308030`, BR, 2026-07-23: Brazil `0.25 / 0` |
| `section232-heading-forced-labor` | 8 | `8407344400`, RU, 2026-07-30: note 52 `0.125 / 0` |
| **Axiom-attributed-open total** | **83** | Current ledger attribution; no new class invented |
| Unexplained Brazil component | 6 | `9403999020`, BR, 2026-07-22: `0 / 0.25` |
| Unexplained note-52 component | 80 | `9403999020`, MX, 2026-07-24: `0 / 0.10` |
| Totals containing an unexplained component | 82 | Same HTS10 |
| **Unexplained total** | **168** | 86 components + 82 totals |

The 198 bounded `9403999020` records all carry Axiom Section 232 `0.5` versus
Yale `0`; the current classifier assigns that slot `vintage-revision-232`.
The raw-record audit independently counts six Brazil mismatches, eighty note-52
mismatches and eighty-two cases containing either. These are endpoint comparison
units, not unique product lines, transactions or full-schedule estimates.

## Exact `9403999020` mechanism and the unresolved source judgment

The code/data difference is now established, rather than inferred from a class
name:

1. Axiom's generated Note-16 steel table contains exact atom `9403999020: 1`
   (`R:us/policies/usitc/us-tariff-incidence/generated/note16-232-steel.yaml:3449`),
   citing Note 16(c)(vii), page 241 (`:3382–3388`). Its version date is August 3
   (`:3396–3398`). The helper unions versions without dates (`R:tools/b16_entry_flags.py:34–45`),
   makes the steel flag true (`:134–143`) and therefore makes both Brazil/note-52
   scope flags false (`:187–192`). Fresh engine records confirm those exact flags.
2. Yale lists this exact HTS10 as Annex 2, aluminum, effective April 6, 2026
   (`Y:resources/s232_annex_products.csv:748`). Its earlier derivative list also
   includes the exact code for aluminum and steel (`Y:resources/s232_derivative_products.csv:622–623`),
   so this is not simply absence from Yale's derivative data.
3. The current producer's dated annex join returns `annex_2`, with no heading
   program hit, for both July-22 and July-24 probes. Yale config labels Annex 2
   removed from scope and sets its rate to zero (`Y:config/policy_params.yaml:332–334`).
   The adapter maps tier to that flat rate (`Y:src/model/authority_adapter.R:833–838`);
   the calculator applies it (`Y:src/pipeline/06_calculate_rates.R:2615–2618`) and
   updates the statutory-232 field (`:2812–2814`).
4. Yale's shared Note-50/52 scope mask includes only positive statutory-232,
   Annex 1a/1b/1c/3, or heading-program coverage (`:910–921`); Annex 2 is absent.
   Brazil uses this mask at `:1077–1094`, note 52 at `:969–976`. Thus its Annex-2
   treatment permits those charges while Axiom's static steel flag suppresses
   them. This reproduces the direction of the observed component differences.

The current ledger expressly calls the Section-232 slot's vintage difference
`input-comparability` (`O:reference/us-tariff-schedule/campaign-dispositions.yaml:483–492`).
That supports describing the *mechanism* behind the associated Brazil/note-52
residuals as a provisional input-comparability/vintage difference. It **does not
classify those residuals**: that selector is limited to `slot: section_232`,
and current positive statutory-exclusion classes do not match their negative
deltas. They remain unexplained in the reported counts.

The exact corpus read also rules out a simple claim that this steel atom belongs
only to headings outside the exclusions. Physical JSONL line 246 / page 236 says
Note 16's subdivision-(c) lists are governed by headings 9903.82.02–9903.82.26.
Physical line 251 / page 241 contains the `9403.99.9020` continuation of
16(c)(vii); the same page explicitly maps that subdivision to, for example,
UK heading 9903.82.05. These are within the heading family cited by the
Note-50/52 ruling.

However, line 246 / page 236 also conditions the specified 9903.82 headings on
at least 15% applicable-metal weight for articles outside chapters 72/73/74/76.
The helper's static membership Boolean does not encode that condition, heading
selection, or legal-date transitions. The bounded campaign supplies no measured
metal-weight fact that resolves it. Source membership alone therefore does not
prove that each sampled entry qualifies for the exemption.

**Next required join before a fix:** reconcile the dated statutory instruments
behind Yale's April-6 Annex-2 removal and Axiom's August-3 codified Note-16 list;
derive the actual applicable 9903.82 heading for the campaign date and supplied
article/origin/metal-content facts, then apply Notes 50/52's enumerated exclusion.
This audit proves the two implementations' mechanism, not which dated legal
treatment is correct. The smallest valid repair is that grounded applicability
derivation and consumption, or a bounded receipted input-comparability disposition
only after the missing join supports it. Do not copy `Yale statutory_rate_232 > 0`
into Axiom, delete the corpus atom, or add a selector merely to clear the count.

## Causes of the measured open classes

**Derivative aluminum annex: 68 open units.** The fresh `8467895030` record has
both Axiom metal flags false, both charge scope flags true, and Yale statutory
232 `0.25`. The pinned Yale source join returns Annex 1b; its eight-digit prefix
is at `Y:resources/s232_annex_products.csv:343`, with the older derivative entry
at `Y:resources/s232_derivative_products.csv:385`.

The primary corpus is more specific than that reference join: physical JSONL
line 248 / page 238, Note 16(c)(vi), names `8467.89.50` among derivative aluminum
articles. Axiom's generator has steel productions for 16(c)(iii)/(iv)/(vii)/(x)/(xi)
and aluminum productions for old Note 19(b)/(j), but none for 16(c)(vi)/(ix)
(`R:tools/generate_incidence_tables.py:78–84`). This explains the missing
aluminum applicability on the sample. Note 19(k), physical line 266 / page 256,
also names it but is outside the generator's 19(j) production.

Smallest source-grounded repair: have the supervised encoder derive the omitted
Note-16 derivative-aluminum applicability, including its applicable heading,
date/origin and metal-content conditions, then consume that fact in the two
charge exclusions. The ruling and existing `section232-annex-*` classes retain
these as Axiom-attributed-open (`O:.../campaign-dispositions.yaml:245–288`);
the missing coverage cannot be closed by reference labeling.

**Heading-program coverage: 10 open units.** The verified source join puts
`8414308030` in both auto-parts and MHD-parts lists, at
`Y:resources/s232_auto_parts.txt:32` and `Y:resources/s232_mhd_parts.txt:38`.
It puts `8407344400` in auto-parts and MHD-parts; the MHD prefix is at
`Y:resources/s232_mhd_parts.txt:28`. Their fresh Yale statutory-232 values are
`0.237625`, while Axiom's metal flags are false. The helper explicitly leaves
the vehicle/MHD heading limbs unconsumed (`R:tools/b16_entry_flags.py:164–176`).
Smallest repair: derive and consume the actual statutory per-article heading
coverage for these programs, preserving any entry conditions. The heading
program may remain applicable even if a metal annex says Annex 2; Yale explicitly
preserves independent heading rates (`Y:.../06_calculate_rates.R:2594–2618`).
The ruling's positive statutory authority takes precedence over aircraft or
other reference labels (`O:.../output-semantics-ruling.md:12–20,35–76`). The
existing `section232-heading-*` selectors remain open (`O:.../campaign-dispositions.yaml:333–376`).

**CAFTA Note 52(i): 5 open units.** `6203331040`/Costa Rica has B note-52 scope
true and rate `0.125`, versus Yale zero. Yale's pinned country-exemption source
contains `62033310` with condition `fta` for the six CAFTA origins
(`Y:resources/s301fl_final_country_exemptions.csv:1371`); its config identifies
this as claim-conditional and proxied by utilization (`Y:config/policy_params.yaml:853–856`).
The Axiom Costa Rica overlay names an unconsumed
`article_described_in_heading_9903_05_95` input
(`R:us/policies/usitc/us-tariff-duty/overlays/section-301/forced-labor-costa-rica-9903-05-33.yaml:36`),
while the composition lacks GN29(d)(v) scope and a CAFTA duty-free claim
(`R:tools/generate_incidence_tables.py:286–305`).

Smallest repair: encode GN29 scope and the actual duty-free claim/eligibility
condition and wire Note 52(i). The current ruling explicitly keeps these open
until both are encoded (`O:.../output-semantics-ruling.md:145–158`). The observed
zero is not proof that the neutral campaign input satisfies the statutory claim;
the exact Yale preference/share-to-statutory-column path was not replayed in
this bounded source audit. Resolve that input/source join before assuming an
encoding change alone will make the two samples equal. Do not set claim facts
true merely from origin and product membership.

## Checks and limits

The evidence script read existing fresh records; it ran no new engine cases and
changed no RuleSpec or selector. The current producer's `verify_yale_sources`
checked commit/tree and the eleven file hashes recorded in the committed
preview receipt. The additional country-exemption CSV and authority adapter
were compared byte-for-byte with the same pinned Git commit. The corpus notes
were read by `git show` and hash-verified against the ruling.

An initial attempt to read
`B/oracles/reference/us-tariff-schedule/preview-1311/unmapped-cause-audit-receipt.json`
failed with `FileNotFoundError`; that raw preview input is absent in this
workspace. The successful bounded join instead adapted the **already committed**
`preview-disposition-line-sets.json.yale_sources` identities to the same verifier's
input shape. It did not fabricate missing preview populations or regenerate the
full historical receipt. This absence is also relevant to reproducing the full
preview producer.

No new classification was introduced. The observed unexplained count remains
168 and the observed Axiom-attributed-open count remains 83 in these bounded
samples. Corpus applicability and dated legal reconciliation must precede any
semantic repair or disposition change.
