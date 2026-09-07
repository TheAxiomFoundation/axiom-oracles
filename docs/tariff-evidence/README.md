# Tariff evidence closure, September 7, 2026

The bounded sprint adds source evidence for six of the 21 previously missing
scope descriptions and exercises their complete Boolean input space through
real Axiom software. It does not change the RuleSpec program or certify any
actual import entry. **All 58 groundings remain uncaptured; closed and certified
remain false.**

The unfinished frontier rebuild had already named all 58 inputs. Thus the old
21/58 gap was an interface-description gap, not 21 newly missing source files.
[Frontier inventory](../../reference/us-tariff-schedule/boundary-evidence/frontier-inventory.json)
records all 58 inputs and identifies the 21 repaired descriptions.

## Selected batch and result

The six inputs concern donation, informational materials, accompanied baggage,
a proper Chapter 98 claim, CBP agreement and the 9802 carve-out. They were
constant in the 19-million-case campaign. Exercising them therefore adds
behavioral evidence that the campaign could not provide. The exact program
has two relevant surfaces: the witness and generated chapter 72.

The [source and runtime receipt](../../reference/us-tariff-schedule/boundary-evidence/note2-exceptions.json)
contains 384 synthetic cases, all 64 combinations for China, Hong Kong and a
France negative control in both compositions. All 768 output values match the
source-derived test expectations. Twenty-eight component-rate cases are
positive. Queries use an exact one-day interval, February 16, 2026.

The original [USITC Rev-15 Chapter 99 PDF](https://hts.usitc.gov/reststop/file?release=2026HTSRev15&filename=Chapter%2099)
is pinned to SHA-256 `92822e8f38873a7275c4cf9bd5341f96f5834dbea964623e7a7aa7b2cd02f225`.
PDF page 176 (printed 99-III-4) contains notes 2(t) and 2(u); PDF page 598
(printed 99-III-426) contains headings 9903.01.21 and .22. Both pages were
visually checked against the original PDF. Full corpus records, raw-record
hashes, JSONL line numbers, source URLs and the ingest-manifest binding appear
in the receipt. This uses an existing archived primary source; the failed
live fetch is not represented as a new download or a current-law verification.

The original ingest signature is retained, and the two applied-file hashes
match. Independent signature verification against the trusted public key
remains outstanding. Naming that signature is not claiming its verification.

The donation input must stipulate the complete condition, including the
presidential-determination caveats. A Chapter 98 claim alone or CBP agreement
alone does not qualify. Their conjunction qualifies only outside the four
9802 provisions; an independent donation/information/baggage exception can
still qualify. This receipt tests the exception judgment and component rate,
not the reduced monetary basis for 9802 entries, total duty, or real-entry
eligibility. The reciprocal-annex treatment of the witness line is an existing
program assumption outside this batch's source claim.

## Reproduce the bounded result

Use an existing Python environment with this repository's dependencies. No
package download, paid compute, encoder invocation or huge scan is necessary.

```sh
python scripts/build_us_tariff_boundary_evidence.py --check \
  --corpus-root /path/to/axiom-corpus \
  --rulespec-root /path/to/rulespec-us \
  --engine /path/to/pinned/axiom-rules-engine
python -m pytest -q tests/test_us_tariff_boundary_evidence.py \
  tests/test_us_tariff_reproducibility_audit.py
```

The corpus must contain Git commit `cc18c703741425a3ebf994a2975cae158bd305d1`;
RuleSpec must contain `4f591c4267063094cc6da9d590872ea982940b81`. The real engine
must hash to `674ca6e70afdccb59c3d6847933bc24b4590105e49db54790f2dcd0bdbbe32d7`.
The producer exports immutable Git objects and copies the verified executable
to an isolated temporary directory before compiling/running it. It replays
every case and requires byte-identical output under `--check`.

## Existing proofs and downstream receipts

The CAFTA 17,404-unit, steel 114-unit, residual 5,733-unit and selector
216,111,132-comparison-unit proofs retain their original bytes and qualified
conclusions. No full scan ran during this sprint.

The [file-binding inventory](../../reference/us-tariff-schedule/boundary-evidence/reproducibility-inventory.json)
examines 202 unique path/digest pairs: 189 small files hash-match, 12 large
artifacts are present but deliberately not rehashed, and one relative
historical artifact is missing. Existence/size checks do not renew its previous
content verification. The audit hashes files at most 20 MB and never
uncompresses campaign data. Use:

```sh
python scripts/audit_us_tariff_reproducibility.py \
  --rulespec-root /path/to/rulespec-us --yale-root /path/to/tariff-rate-tracker \
  --historical-source /path/to/target-mismatch-cells.jsonl.gz \
  --output /path/to/reproducibility-inventory.json
```

The missing 10,088,070-byte file is
`reference/us-tariff-schedule/preview-1311/target-mismatch-cells.jsonl.gz`.
Its exact SHA-256 is
`d5b53173afe489686aff86a4d1d776bf821cb97945e9ebacd5ba6bc912a8b705`.
An exact copy was recovered from `axiom-oracles-cert` and saved durably at
`/Users/maxghenis/capacity-sprint-20260907/tariff/historical/target-mismatch-cells.jsonl.gz`.
Restore that file at the relative path before a future *full* reproduction;
restoration is not a reason to rerun the 216-million-row scan now. Other large
inputs remain tied to local absolute cache paths. Shipping a portable full
campaign bundle is still outstanding.

The closure producer now writes compiler JSON to a normal temporary file,
fixing its `/dev/stdout` sandbox failure. The 164-test preserved-rebuild battery
passes, including recompilation of the witness and all 100 generated chapters
from immutable Git objects, reproducing the exact 58-input union. Separately,
the existing executable receipt reproduces all ten recorded witness values and
101 program compilations byte-for-byte. The new six-input receipt supplements
those existing receipts and does not relabel campaign-constant inputs as varied.

## Downstream metadata repair

The canonical certificate producer initially rejected the saved conformant
claim: all 39 proof-hash scalars in the disposition ledger were stale after the
prior rebuild. The first failure was the steel-scope Brazil causal binding.
The [metadata rebind receipt](../../reference/us-tariff-schedule/publication-metadata-rebind.json)
now links immutable copies of the original audited ledger, classification,
report and exercise receipt to the completed, preserved proof generation.

The deterministic producer changes exactly 39 ledger hash scalars and three
classification input hashes, adds an explicit original-audit annotation, and
updates the corresponding report and two exercise-receipt hash fields. It
preserves every comparison, signature assignment, population accumulator,
class count and sidecar binding. It scans **zero comparison rows**. It does
not represent the old sidecar as a fresh audit of new metadata. The mandatory
publication gate reproduces this exact transformation from hash-pinned inputs;
changing measured results or replacing the baseline makes it fail.

```sh
python scripts/rebind_us_tariff_publication.py --check
python -m pytest -q tests/test_us_tariff_publication_rebind.py \
  tests/test_us_tariff_publication.py tests/test_build_us_tariff_exercise_receipt.py
```

All 151 targeted tests pass. The canonical tariff certificate and its census
row have been regenerated: conformant, exercised and executable are true;
closed and certified remain false. This repairs reproducibility of an existing
qualified comparison verdict; it supplies no new legal-completeness claim.

## Fifteen repaired scopes outside this batch

| Inputs | Remaining evidence and implementation requirement |
| --- | --- |
| `entry_is_line_a`, `entry_is_line_b`, `entry_is_line_d`, `hts_line` | Bind exact HTS statistical/legal-line identities and adapter normalization to source rows; test positive and neighboring identifiers. Actual classification remains external. |
| `entry_is_china_301_2024_action`, `entry_is_china_301_solar` | Capture the complete note-31 membership source and exclusions and derive membership through supervised encoding; current flags remain declared and campaign-constant. |
| `entry_is_china_301_list123`, `entry_is_china_301_list4a` | Ingest original 2018/2019 action and exclusion instruments and reconcile dated list membership. |
| `entry_is_entered_free_of_duty_under_usmca` | Source General Note 11/related claims and establish actual transaction qualification; a source page cannot certify a claim. |
| `entry_is_section_232_aluminum`, `entry_is_section_232_steel` | Complete dated proclamation/annex membership and transaction qualifiers. Preserve the existing bounded input-comparability proofs. |
| `entry_is_section_122_exempt` | Bind complete note 2(aa) exclusion coverage and its transaction conditions; distinguish membership from real-entry qualification. |
| `entry_is_section_201_cspv` | Bind the expired note-18 safeguard's product and date surface; retain the expiration boundary. |
| `entry_loaded_and_in_transit_before_july_24_2026` | Capture the note-52 safe-harbor wording and carrier/loading/entry evidence with July 24/28 boundaries. |
| `resolved_non_ad_valorem_column2_rate` | Preserve specific/compound/conditional rates, quantities and customs value. Do not replace with an inferred flat rate. |

The 13 partial/pending source families, subordinate-instrument census and typed
law-derived dependencies also remain open in the existing closure certificate.
A source-linked synthetic receipt cannot close these separate obligations.

## Integration and release hold

Branch: `sprint/tariff-evidence-20260907`. It preserves the exact unfinished
rebuild from `83908413e68f551f83c61fbbd891409a567bf5ee` in an isolated worktree.
GitHub fetch failed with `Could not resolve host: github.com`; the cached main
ref is not represented as a verified live base. Neither original checkout was
edited. Before integration, fetch and safely reconcile current main, regenerate
the tariff certificate with its canonical producer, and rerun changed gates.

Final Fable review and the existing release conditions remain mandatory.
Launch runbook Gates 2–3 remain Max's: prebriefs/contact, followed by an explicit
go for the nav switch and publication. This sprint grants none of those actions.
