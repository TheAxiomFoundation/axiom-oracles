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

## Current source and encoding pins

The consumer binds corpus release `de-rulespec-2026-09-08-kindergeld-context`
from merge `069407610ff961a075665d08c96ad08f54a9767b`, content SHA-256
`32f506ac4cee0b0e98aab5834b4ab0f98ea82f918890ddd2394c10a31286773c`.
Its 8,176 rows in 20 scopes preserve the preceding frontier, civil and parentage
captures. Publication 34266745140 and mirror 34267191780 succeeded; the
signature verifies and the anonymous mirror is byte-identical. The bounded
KindRG extract retains original PDF pages 1 and 26; the full act remains
separately captured. Supplemental entries 001–006 and 011–017 bind 32 corpus
rows through `supplemental-corpus-bindings.json` without changing their legal
dispositions merely because their sources became receipted.

RuleSpec merge `0201d1f7225f2be5cbd61add704f8f0fa7ea3b76` includes signed
BGB §1591 module PR #54. Protected generation 34276007507 produced its
signature; repository validation 34276471091 passed before merge. Both proof
atoms carry exact corpus excerpts, including the 1 July 1998 commencement.
Five observable identifiers/date inputs establish birth-based maternity from
an identified complete record at the query day. Four cases exercise seven
row expectations, including child/person pair separation and birth timing.
Missing record evidence is an evaluation error, not a negative legal judgment.
This prerequisite does not close the unimplemented §32/§63 composition.
Earlier candidates #46, #48, #52 and #53 were closed without merging.

The signed workflow uses encoder merge `c39348f1241516d33127a887f470266608c6aefa`
(PR #1593), pinned by dedicated RuleSpec PR #51. The newline-preservation fix
passed independent agent review, 14,050 CI tests (80 skipped), lint and platform
builds. Encoder #1588 previously restored bounded explicit German dependency
recognition and structured amendment context, also following independent
review and green CI. These reviews are not human certification approval.

## Remaining frontier

The regenerated ledger has 5 pending spine rows out of 18 and 207 pending
instruments out of 671. Dependency closure remains false: eight law-derived
inputs and 119 bearing instruments remain open, with no unclassified inputs.
The five birth-record inputs are committed world facts; engine-supplied query
boundaries are not external inputs. The additional KindRG evidence candidate
remains pending until its precise legal disposition is established.

The 201 discovery candidates are incomplete seeds: exhaust official BMF/BZSt
registers, verify case identities and BStBl II publication, reconcile duplicate
identities, capture operative texts, and encode every bearing rule. All four
class rows remain pending. No complete discovery or certified claim is made.

Prior §64, AO §§8–9 and §78 generation attempts produced no accepted modules.
They exposed unresolved household-priority composition, observable residence
judgments, exact calendar-duration arithmetic and transition-payment rules.
Rejected artifacts were not manually applied. The synthetic cases under
`runtime-probe/` establish runtime behavior only; they are not legal encodings
or closure premises. Fixed-day approximations cannot replace statutory
calendar months or years.

Regeneration (supply the pinned corpus and RuleSpec checkouts as needed):

```
python scripts/de_closure.py
python scripts/de_closure_ledger.py --generate --artifact de/kindergeld
python scripts/de_certificate_census.py
python scripts/certify.py
```
