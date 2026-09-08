# Kindergeld class discovery seeds

This snapshot adds 201 pending candidate entries to the closure frontier:
11 BMF letters, 2 BZSt instructions, 165 court citations, and 23 bilateral
or association instruments. A court citation entry is not necessarily a
unique case: spelling variants and duplicate legal identities still require
reconciliation. These counts do not establish complete enumeration.

The DA-KG text was extracted with `pdftotext -layout` from the exact PDF
already receipted as `de-subject-003` in `de-instrument-graph.json` (PDF SHA
`33e1a8c4f6bd65034febc9d0c45850e64e982f665f519f08eaeceb80ac02dedd`).
Whitespace-normalized citation excerpts identify each seed. The retained
DVKA official bilateral index identifies the 22 linked instruments; DA-KG
also explicitly identifies Association Council Decision 3/80.

`snapshot.json` binds the retained discovery source files by SHA-256 and
contains a canonical-JSON receipt over all fields except `receipt_sha256`
(UTF-8, sorted keys, compact separators, no ASCII escaping). The ledger
producer verifies every source hash and every whitespace-normalized
excerpt, rejects duplicates and missing snapshots, and adds pending rows.
Discovery-source hashes are deliberately not operative-body hashes.

The corpus capture tranche in axiom-corpus PR #647 contains the 23 agreement
texts, but ingest signatures and release publication are pending. Its local
availability does not authorize an `encoded` or text-bound legal disposition.
The consumer retains its published corpus and RuleSpec pins until a new
signed release and signed modules exist.

Remaining work: exhaust the official BMF/BZSt registers; verify individual
case identities and BStBl II publication against official records; reconcile
duplicate identities; capture operative texts; disposition each member and
encode every bearing rule. The four class rows remain pending. No complete
discovery or certified claim is made.

Regeneration (with the corpus and RuleSpec checkouts supplied as needed):

```
python scripts/de_closure_ledger.py --generate --artifact de/kindergeld
python scripts/de_certificate_census.py
python scripts/certify.py
```

## V 23.1 reconciliation still requiring an implementation

The receipted DA-KG section says, “Das festgesetzte Kindergeld ist ungerundet
auszuzahlen.” That addresses payment of an amount already fixed. The signed
§66 module's `kindergeld_before_whole_euro_rounding` instead feeds the
§66(3) child-allowance-increase calculation. The statutory proof for rounding
says “Das Kindergeld ist dabei auf volle Euro kaufmännisch zu runden.”

These are different stages. The integration must constrain whole-euro
rounding to that statutory increase calculation and pass an issued fixing's
amount through payment without a second rounding step. In particular, the
EU differential output must not acquire whole-euro rounding merely by being
routed through a generic payment rule. The existing fixed €255/€259 cases
alone cannot demonstrate this distinction, because rounding already-integral
amounts is numerically inert. The V23.1 row stays bearing and open until the
assessment/payment boundary and any fractional amount cases are implemented
and verified from the applicable sources. No disposition is changed here.
