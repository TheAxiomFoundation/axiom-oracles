# Output-semantics ruling and legal receipt

## Human-maintainer decision

Max ruled on 2026-08-26 that the certificate certifies the statutory
non-exempt component semantics. Reference-modeled behavior—including Yale's
utilization proxies, scope masks, and parser artifacts—must be classified only
as bounded, receipted reference-behavior disposition classes. The certificate
does not reproduce Yale's modeled construct.

This ruling controls `campaign-dispositions.yaml`. An
`axiom-attributed-open` class continues to count against certificate
conformance until its statutory behavior is encoded.

## Source pins

- Rev-15 note corpus: Axiom corpus commit
  `5cf7556ad3d68aa0596d58f7ac60942bb5db3120`,
  `data/corpus/provisions/us/statute/2026-08-04-usitc-hts-2026-rev15-notes.jsonl`,
  blob `9a1a6fd3c65407d19b011eb8d433b7ca65bfec63`, SHA-256
  `0f3ed7ef2efb64383825db65e615959200770e8511c8d4834b16e02892cb9ec8`.
- Yale mirror: commit `c4307e514196618afcbf88cf7fd33746417eeabf`,
  tree `d3107eae32ae7ac366b319abd4ab7b13c78d5c3c`.
- C6 RuleSpec surface: commit
  `3357f7dc710d18861b1fefdff115e2434e67b988`, tree
  `c3d530c72344310aa2fdfcebe5aec286b1ad4869`.

## Section 232 interplay: positive statutory authority

Rev-15 Note 50(a)(vi), corpus physical JSONL line 563,
`us/statute/hts/chapter-99/page-553`, says:

> As provided in heading 9903.05.07, the additional duty imposed by heading 9903.05.01 shall not apply to: (1) articles of aluminum, of steel or of copper, nor to derivative aluminum or steel articles provided for in headings 9903.82.02 and 9903.82.04–9903.82.26;

The same subdivision continues with passenger vehicles and light trucks,
their parts, wood products, medium- and heavy-duty vehicles and parts,
semiconductors, and patented pharmaceutical articles, each by enumerated
Chapter-99 heading.

Rev-15 Note 52(f), physical line 576,
`us/statute/hts/chapter-99/page-566`, says:

> As provided in heading 9903.05.90, the additional duties imposed by headings 9903.05.20–9903.05.84 shall not apply to: (1) articles of aluminum, of steel or of copper, nor to derivative aluminum or steel articles provided for in headings 9903.82.02 and 9903.82.04–9903.82.26;

It repeats the same enumerated program families. The notes do not use the
phrase “section 232”; the express Chapter-99 heading enumeration supplies the
authority. Yale's implementation is at
`src/pipeline/06_calculate_rates.R:901-921`, applied to forced-labor at
`:969-976` and Brazil at `:1077-1094`.

Therefore all 185,954 preview scope-mask units are Axiom-attributed and open:

- 119,682 exposed-but-unconsumed units: consume
  `entry_is_section_232_covered` in both panel components.
- 33,834 annex-membership units: broaden the grounded per-article fact beyond
  the direct aluminum/steel surface, then consume it.
- 32,438 heading-program units: expose and consume membership in the programs
  enumerated by Notes 50(a)(vi)(2)-(8) and 52(f)(2)-(8).

The C6 helper's current direct fact is aluminum-or-steel only
(`tools/b16_entry_flags.py:119-130`). The Brazil and forced-labor panel
components cite the exclusions but do not consume that fact
(`us/policies/cbp/us-tariff-duty/composition.yaml:3435-3478` and following).

For contrast, the bounded body of Rev-15 Note 20 contains no exclusion by the
Note-50/52 Chapter-99 families. Its line 270/page-260 stacking text says that
covered products “shall continue to be subject to antidumping, countervailing,
or other duties, fees, exactions and charges ... as well as” the Section-301
duty. A Section-232 mask for a Note-20 family would therefore be unsupported
reference behavior. None of the preview's 185,954 units is a Note-20 unit.

## Reference-behavior and reference-defect receipts

### Utilization proxies

Yale configures a 90% aircraft share and 50% pharmaceutical share for the
forced-labor action at `config/policy_params.yaml:865-866`. For Brazil, it
describes the shares as “flat placeholders, not measured utilization” at
`:922-928` and sets 90%/50% at `:930-932`. The calculator multiplies the
statutory component by `1 - share` at
`src/pipeline/06_calculate_rates.R:997-1007` and `:1103-1108`.

The old-residual receipt proves 74,822 aircraft units satisfy exactly
`expected = 0.10 * actual`, and 73,500 pharmaceutical units satisfy exactly
`expected = 0.50 * actual`. Those are reference-behavior classes. The 41,948
new Yale-zero aircraft/pharmaceutical units do not satisfy those equations and
are kept in separate reference-behavior classes.

### Yale parser zero

At Yale commit `c4307e51`, both `data/hts_archives/hts_2026_rev_11.json.gz`
and `hts_2026_rev_12.json.gz` contain these physical-line pairs:

- `425559/425564`: `8712.00.50.00`, `3.7% <u></u>`;
- `425800/425805`: `8714.91.50.00`, `6% <u></u>`;
- `425847/425852`: `8714.92.10.00`, `5% <u></u>`;
- `426186/426191`: `8714.94.90.00`, `10% <u></u>`.

`src/core/helpers.R:80-94` accepts a simple percentage only when the entire
string matches `^[0-9.]+%$`; `src/model/rate_schema.R:102-117` coalesces the
resulting missing base to zero. C6 preserves the four statutory rates as
0.037, 0.06, 0.05, and 0.10 at
`us/policies/usitc/us-tariff-duty/lines/generated/ch87.yaml:1490,1497,1499,1508`.
The exact 68-unit population is a reference defect.

### Chapter 98

Note 50(a)(i), corpus line 550/page-540, conditions relief on goods “for which
entry is properly claimed under a provision of chapter 98” and on CBP agreeing
that the entry is appropriate, subject to the listed 9802 exceptions. Note
52(a), line 563/page-553, repeats those conditions. Yale instead statically
zeros listed secondary codes at
`src/pipeline/06_calculate_rates.R:2961-2988`. The panel certificate supplies
neutral non-exempt claim facts, so the 1,514-unit Yale zero is bounded
reference behavior, not an Axiom omission.

### HTS8 broadening

Yale stores the five eight-digit parents at
`resources/s301_brazil_exempt_products.csv:52,616,797,827,840` and applies
prefix membership in `src/pipeline/06_calculate_rates.R:1070,1092`. Note
50(a)(ii), corpus lines 553-555/pages 543-545, enumerates only these children:
`0409000005`, `4407990295`, `8422409181`, `8505110070`, and `8537109170`.
The 120 neighboring-child units have no note-text authority and are a reference
defect. The taxonomy gives this cause precedence over its 24-unit overlap with
the Section-232 population.

## CAFTA 52(i): deferred encoding, still open

Rev-15 Note 52(i), corpus line 576/page-566, says:

> As provided in heading 9903.05.95, the additional duties imposed by headings 9903.05.33, 9903.05.34, 9903.05.37, 9903.05.40, 9903.05.42 and 9903.05.58 shall not apply to a textile or apparel good as defined in subdivision (d)(v) of general note 29 of the HTSUS which is the product of Costa Rica, the Dominican Republic, El Salvador, Guatemala, Honduras or Nicaragua, entered free of duty under the Dominican Republic-Central America-United States Free Trade Agreement, including any treatment set forth in subchapter XXII of chapter 98 of the HTSUS.

The C6/#1311 commit message (`3357f7dc`) explicitly records: “note 52(i)
CAFTA remains a deferred output pending GN 29 ingest.” Encoding also requires
an entry-level DR-CAFTA duty-free claim/eligibility fact; origin and product
membership alone do not prove the statutory condition. The exact 17,404 units
are consequently `axiom-attributed-open` and must continue to count against
conformance until GN-29 scope and the claim fact are encoded and wired.
