# Preview-1311 output-semantics disposition ruling report

Date: 2026-08-26  
Requested output: `/Users/maxghenis/PolicyEngine/_tariff-p5/burndown/dispositions-ruling-report.md`  
Branch: `codex/dispositions-output-semantics`  
Head: `0af3535515193846a865d4d059e2e7d91aa866a3`  
Baseline: `f5743d4a6`  
Push status: not pushed

## Outcome

This branch executes Max's 2026-08-26 ruling: the certificate certifies the
statutory non-exempt component semantics. Yale utilization proxies, scope
masks, parser artifacts, and other modeled constructs are classified only as
bounded, receipted reference behavior or defects; Axiom does not reproduce
those constructs.

Twenty exact per-slot selectors classify all 395,330 preview mismatch units.
Every selector binds an exact slot, a generated exact HTS10 line set, and a
delta sign or finite delta set. The preview dry-run found zero overlaps and
zero unexplained units at both row and campaign-signature levels. The CAFTA and
Section-232 populations remain `axiom-attributed-open`; classification does
not make the certificate conformant.

The ruling and legal/source receipt are committed in
`reference/us-tariff-schedule/output-semantics-ruling.md`. The generated exact
population receipt is
`reference/us-tariff-schedule/preview-disposition-line-sets.json`.

## Per-class selectors, receipts, and attribution

“Line set” below means the class-specific, hashed exact HTS10 set named by the
selector in the generated receipt. It is the required non-slot bound; the
delta constraint is an additional bound.

| Logical class and selector census | Selector bound | Units | Attribution / disposition | Receipt or authority |
|---|---|---:|---|---|
| Aircraft utilization proxy: `aircraft-utilization-proxy-brazil` 3,654; `aircraft-utilization-proxy-forced-labor` 71,168 | Exact slot + corresponding line set + positive delta | 74,822 | `reference-behavior` / `explained_residual` | Old receipt proves `expected = 0.10 * actual` per unit. Yale `c4307e51`, `config/policy_params.yaml:865-866,922-932`, sets 90%; `src/pipeline/06_calculate_rates.R:997-1007,1103-1108` applies `rate * (1 - share)`. |
| Pharma utilization proxy: `pharma-utilization-proxy-brazil` 5,082; `pharma-utilization-proxy-forced-labor-035` 988; `pharma-utilization-proxy-forced-labor-non035` 67,430 | Exact slot + corresponding line set + receipt-listed finite delta set | 73,500 | `reference-behavior` / `explained_residual` | Old receipt proves `expected = 0.50 * actual` per unit. The same Yale files/lines configure and apply 50%. |
| Yale parser zero statutory base: `yale-parser-zero-statutory-base` | Forced-labor slot + four-line set + negative delta | 68 | `reference-defect` / `upstream_engine_gap` | Yale Rev-11/12 contain four trailing-tag rate strings rejected by its parser; C6 preserves the rates. |
| New Yale-zero aircraft conditional: `yale-zero-aircraft-brazil` 414; `yale-zero-aircraft-forced-labor` 40,392 | Exact slot + corresponding line set + positive delta | 40,806 | `reference-behavior` / `explained_residual` | New-mismatch receipt plus Yale utilization/scope behavior; separate because these do not satisfy the old 10% equation. |
| New Yale-zero pharma conditional: `yale-zero-pharma-brazil` 84; `yale-zero-pharma-forced-labor` 1,058 | Exact slot + corresponding line set + finite delta set | 1,142 | `reference-behavior` / `explained_residual` | New-mismatch receipt plus Yale utilization/scope behavior; separate because these do not satisfy the old 50% equation. |
| CAFTA Note 52(i): `cafta-52i-deferred` | Forced-labor slot + line set + positive delta | 17,404 | `axiom-attributed-open` / `axiom_encoding_gap` | Rev-15 Note 52(i), C6/#1311 deferred-output note, and missing GN-29(d)(v) plus DR-CAFTA claim/eligibility facts. |
| Section-232 exposed/unconsumed: `section232-exposed-brazil` 8,826; `section232-exposed-forced-labor` 110,856 | Exact slot + corresponding line set + positive delta | 119,682 | `axiom-attributed-open` / `axiom_encoding_gap` | Notes 50(a)(vi)/52(f). Fix: consume `entry_is_section_232_covered` in both panel components. |
| Section-232 annex membership: `section232-annex-brazil` 2,346; `section232-annex-forced-labor` 31,488 | Exact slot + corresponding line set + positive delta | 33,834 | `axiom-attributed-open` / `axiom_encoding_gap` | Same authority. Fix: ground the full enumerated per-article program surface beyond the current aluminum/steel helper, then consume it. |
| Section-232 heading programs: `section232-heading-brazil` 2,334; `section232-heading-forced-labor` 30,104 | Exact slot + corresponding line set + positive delta | 32,438 | `axiom-attributed-open` / `axiom_encoding_gap` | Same authority. Fix: expose/consume the programs in Notes 50(a)(vi)(2)-(8) and 52(f)(2)-(8). |
| Conditional Chapter 98: `chapter98-brazil` 6; `chapter98-forced-labor` 1,508 | Exact slot + corresponding line set + positive delta | 1,514 | `reference-behavior` / `explained_residual` | Notes 50(a)(i)/52(a) require a proper claim and CBP agreement. Yale statically zeros secondary codes; the panel has neutral non-exempt facts. |
| Yale HTS8-over-HTS10 broadening: `yale-hts8-broadening-brazil` | Brazil slot + exact 20-child line set + positive delta | 120 | `reference-defect` / `upstream_engine_gap` | Note 50(a)(ii) enumerates exact HTS10 children; Yale applies HTS8 prefix membership. This class takes precedence over its 24-unit Section-232 overlap. |
| **Total** | **20 selectors** | **395,330** |  |  |

Conservation:

- Old: `74,822 + 73,500 + 68 = 148,390`.
- New: `40,806 + 1,142 + 17,404 + 119,682 + 33,834 + 32,438 + 1,514 + 120 = 246,940`.
- Total: `148,390 + 246,940 = 395,330`.
- Slots: Brazil `22,866` + forced labor `372,464` = `395,330`.

The 41,948 new Yale-zero aircraft/pharma units are explicit classes rather
than being folded into the old proxy classes; folding would falsely assert
the exact 10%/50% equations and break conservation.

## Section-232 legal derivation

The actual source is the Rev-15 corpus at Axiom corpus commit
`5cf7556ad3d68aa0596d58f7ac60942bb5db3120`,
`data/corpus/provisions/us/statute/2026-08-04-usitc-hts-2026-rev15-notes.jsonl`,
blob `9a1a6fd3c65407d19b011eb8d433b7ca65bfec63`, SHA-256
`0f3ed7ef2efb64383825db65e615959200770e8511c8d4834b16e02892cb9ec8`.

Rev-15 Note 50(a)(vi), physical line 563/page 553, states verbatim:

> As provided in heading 9903.05.07, the additional duty imposed by heading 9903.05.01 shall not apply to: (1) articles of aluminum, of steel or of copper, nor to derivative aluminum or steel articles provided for in headings 9903.82.02 and 9903.82.04–9903.82.26;

The subdivision continues with enumerated headings for vehicles/light trucks,
their parts, wood, medium/heavy vehicles and parts, semiconductors, and
patented pharmaceuticals.

Rev-15 Note 52(f), physical line 576/page 566, states verbatim:

> As provided in heading 9903.05.90, the additional duties imposed by headings 9903.05.20–9903.05.84 shall not apply to: (1) articles of aluminum, of steel or of copper, nor to derivative aluminum or steel articles provided for in headings 9903.82.02 and 9903.82.04–9903.82.26;

It repeats the same eight program families. Although the text does not say
“section 232,” `shall not apply` plus the enumerated Chapter-99 headings is
positive statutory authority. Thus all 119,682 + 33,834 + 32,438 = 185,954
scope-mask units are Axiom-attributed and open.

For contrast, Rev-15 Note 20, physical line 270/page 260, says verbatim:

> Products of China that are provided for in heading 9903.88.01 and classified in one of the subheadings enumerated in U.S. note 20(b) to subchapter III shall continue to be subject to antidumping, countervailing, or other duties, fees, exactions and charges that apply to such products, as well as to the additional 25 percent ad valorem rate of duty imposed by heading 9903.88.01.

The bounded Note-20 body has no Note-50/52 program exclusion. A 232 mask for a
Note-20 family would lack authority; none of the 185,954 units is Note 20.

The 1,514 Chapter-98 units differ: Notes 50(a)(i)/52(a) condition relief on a
proper claim and CBP agreement, which Yale's static code zero lacks. The 120
broadening units also differ: the legal text identifies exact HTS10 children,
while Yale broadens from HTS8; all 120 take broadening precedence, including
the 24-unit 232 overlap.

## Detailed reference receipts

Yale pin: commit `c4307e514196618afcbf88cf7fd33746417eeabf`, tree
`d3107eae32ae7ac366b319abd4ab7b13c78d5c3c`.

Parser receipt in both Yale `hts_2026_rev_11.json.gz` and
`hts_2026_rev_12.json.gz`:

| HTS10 | Physical lines | Yale string | C6 rate | Units |
|---|---:|---|---:|---:|
| `8712005000` | 425559/425564 | `3.7% <u></u>` | 0.037 | 20 |
| `8714915000` | 425800/425805 | `6% <u></u>` | 0.06 | 20 |
| `8714921000` | 425847/425852 | `5% <u></u>` | 0.05 | 8 |
| `8714949000` | 426186/426191 | `10% <u></u>` | 0.10 | 20 |

Yale `src/core/helpers.R:80-94` requires a whole-string simple percentage and
`src/model/rate_schema.R:102-117` coalesces the missing base to zero. C6 rates
are at `us/policies/usitc/us-tariff-duty/lines/generated/ch87.yaml:1490,1497,1499,1508`.

HTS8 broadening receipt (`resources/s301_brazil_exempt_products.csv`):

| Yale line / HTS8 | Statutory HTS10 | Neighbor units |
|---|---|---:|
| 52 / `04090000` | `0409000005` | 30 |
| 616 / `44079902` | `4407990295` | 18 |
| 797 / `84224091` | `8422409181` | 24 |
| 827 / `85051100` | `8505110070` | 24 |
| 840 / `85371091` | `8537109170` | 24 |
| **Total** |  | **120** |

Yale applies prefix membership at
`src/pipeline/06_calculate_rates.R:1070,1092`; Note 50(a)(ii), corpus lines
553-555/pages 543-545, supplies exact-child authority.

CAFTA remains open. Note 52(i), physical line 576/page 566, says verbatim:

> As provided in heading 9903.05.95, the additional duties imposed by headings 9903.05.33, 9903.05.34, 9903.05.37, 9903.05.40, 9903.05.42 and 9903.05.58 shall not apply to a textile or apparel good as defined in subdivision (d)(v) of general note 29 of the HTSUS which is the product of Costa Rica, the Dominican Republic, El Salvador, Guatemala, Honduras or Nicaragua, entered free of duty under the Dominican Republic-Central America-United States Free Trade Agreement, including any treatment set forth in subchapter XXII of chapter 98 of the HTSUS.

C6 commit `3357f7dc710d18861b1fefdff115e2434e67b988` records:
“note 52(i) CAFTA remains a deferred output pending GN 29 ingest.” GN-29(d)(v)
and an actual DR-CAFTA duty-free claim/eligibility fact remain prerequisites.

## Preview provenance

| Input | SHA-256 |
|---|---|
| `old-residual-taxonomy-receipt.json` | `b4f9d26d5a800cf1b0e6e50c6b3935ee18b24ca55bbcc5eecf9e10ab8f829bea` |
| `unmapped-cause-audit-receipt.json` | `4572f1a121848337bcd0ea797c09e771fc55a3e0efaeb79c195979ddb5a5e29e` |
| `mismatch-taxonomy-receipt.json` | `3d1a7543d738d6e396e111ff909c245f082146aeeeeef27d57a5da38f30e25de` |
| `new-mismatch-cells.jsonl.gz` | `7e26a7e746abd4d033b8dcc6b7d95efcece45b1405ac84238011500c84bbe029` |
| `target-mismatch-cells.jsonl.gz` | `d5b53173afe489686aff86a4d1d776bf821cb97945e9ebacd5ba6bc912a8b705` |

Generated receipt SHA-256:
`df5f3e13487de1d0fc2c3dd413cee5efc32f21fc3d6706f41de1a2157ccecd95`;
payload SHA-256:
`ec38c7d2a65d2218fc39c431349518b24dcde5923eee60359e36d0b45c270bf3`.
The inherited preview directory remains untracked and unchanged.

## Input contract

The b16 mismatch is resolved campaign-locally. Campaign consumption
canonicalizes and equality-checks:

- `entry_is_brazil_301` → `entry_is_brazil_301_listed`;
- `entry_is_forced_labor_301` → `entry_is_forced_labor_301_listed`.

The canonical field must exist and equal its alias; the alias is then removed
before contract comparison/case construction at every helper-consumption site.
No RuleSpec or external runtime projection is needed. The official C6 contract
stage passed all 100 compositions; only declared surplus `entry_is_line_c` and
`entry_is_line_e` were dropped. The receipt is
`reference/us-tariff-schedule/declared-input-contract-receipt.json`.

## Closure producer

The scoping-memo gate was contained: the historical U.S. producer path had
been displaced by the Danish implementation. The branch restores it as
`scripts/us_tariff_closure.py`, leaves `scripts/closure_ledger.py` intact for
Denmark, and points U.S. certification to the campaign-specific producer.

It pins corpus `bef19f24206a9de4ef29d9ba2b5924f3cc6a00c6`, RuleSpec
`96d5e7c1e6309dc205b7320bbddaae8dd5d410df`, 29,845 schedule rows, 805
Chapter-99 pages, and 380 modules. Full re-derivation, `--check`, and certificate
verification pass. Closure correctly remains `closed: false`; substantive
pending/partial families, including non-metal 232 annexes, are not waived.

## Validation

- Generated receipt `--check`: PASS; 20 selectors, 395,330 units, no overlap
  or residue.
- Preview classifier integration: 197,665 signatures, zero mixed signatures,
  exact census. The fixed legacy key had mixed 168 units/33 signatures because
  it omitted HTS10 and ISO2.
- C6 input contract: PASS, 100 compositions.
- U.S. closure `--check`: PASS; `closed: false` preserved.
- Certificate `--check`: PASS.
- Affected pytest suite: 235 passed in 82.57 seconds.
- `git diff --check`: PASS.
- Scope audit: no RuleSpec, toolchain, workflow, or waiver edits.

## Open items

1. Encode GN-29(d)(v) and the DR-CAFTA claim fact; 17,404 CAFTA units remain
   Axiom-attributed and nonconformant.
2. Implement the three 232 fixes; annex and program facts must be broadened
   and grounded, not merely relabeled.
3. Run the official post-rebind campaign and regenerate comparison,
   classification, and report artifacts. This dry-run is exact against the
   supplied preview, not a substitute for the official run.
4. Open the PR and obtain dual-agree review. Do not push from this lane.
