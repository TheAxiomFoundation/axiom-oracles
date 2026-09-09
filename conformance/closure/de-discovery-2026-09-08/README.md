# Kindergeld class discovery seeds

This snapshot contains 209 candidate entries: 16 BMF letters, 2 BZSt
instructions, 168 court candidates, and 23 bilateral or association instruments.
Of these, 204 remain pending citation seeds. Four corpus-receipted entries are
bearing dependencies (two parentage decisions, C-328/20 and the 2025 country-group
letter); the 2013 transfer letter is non-bearing for this Kindergeld surface.
The three courts’ BStBl II publication remains
unverified and discovery-class membership is explicitly provisional. A court citation entry is not necessarily a
unique case: spelling variants and duplicate legal identities still require
reconciliation. These counts do not establish complete enumeration.

The DA-KG text was extracted with `pdftotext -layout` from the exact PDF
already receipted as `de-subject-003` in `de-instrument-graph.json` (PDF SHA
`33e1a8c4f6bd65034febc9d0c45850e64e982f665f519f08eaeceb80ac02dedd`).
Whitespace-normalized citation excerpts identify each seed. The retained
DVKA official bilateral index identifies the 22 linked instruments; DA-KG
also explicitly identifies Association Council Decision 3/80.

The full official BMF positive register dated 14 March 2025 is retained as
`bmf-positive-list-2025.pdf`, with its extracted text and both SHA-256 values
bound in the discovery snapshot. Visually checked page 56 adds the letters of
8 February 2016, 28 June 2013, 17 January 2014 and 18 December 2023. The 2013 letter’s operative text is now receipted and dispositioned below;
the other three still require operative-text/applicability review; this register does not
establish exhaustive BMF discovery.

`snapshot.json` binds the retained discovery source files by SHA-256 and
contains a canonical-JSON receipt over all fields except `receipt_sha256`
(UTF-8, sorted keys, compact separators, no ASCII escaping). The ledger
producer verifies every source hash and every whitespace-normalized
excerpt, rejects duplicates and missing snapshots, and adds pending rows.
Discovery-source hashes are deliberately not operative-body hashes.

## Current source and encoding pins

The consumer binds corpus release `de-rulespec-2026-09-09-kindergeld-bmf-context`
from merge `6caa12dbaeb916f3f1c66c8e2f821c45b63c9ce5`, content SHA-256
`a5518aeeae74d85fb8627dd7006edeb55c3fcb9741a928f1b46c156c737d255e`.
Its 8,206 rows in 24 scopes preserve the preceding frontier, civil and parentage
captures. Publication 34293466751 and mirror 34293798326 succeeded; the
signature verifies and the anonymous mirror is byte-identical. The retained
BT-Drs.20/12778 excerpt retains PDF pages 1 and 64 and is expressly a draft
explanatory memorandum, not enacted law. Its combined-allowance explanation
remains bearing until implemented in the §32/§66 rules. The bounded
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

The preceding signed BGB1591 workflow used encoder merge `c39348f1241516d33127a887f470266608c6aefa`
(PR #1593), pinned by dedicated RuleSpec PR #51. The newline-preservation fix
passed independent agent review, 14,050 CI tests (80 skipped), lint and platform
builds. Encoder #1588 previously restored bounded explicit German dependency
recognition and structured amendment context, also following independent
review and green CI. These reviews are not human certification approval.

## Remaining frontier

The regenerated ledger has 5 pending spine rows out of 18 and 210 pending
instruments out of 681. Dependency closure remains false: eight law-derived
inputs and 124 bearing instruments remain open, with no unclassified inputs.
The eight birth-record and date inputs are committed world facts; engine-supplied query
boundaries are not external inputs. The additional KindRG evidence candidate
remains pending until its precise legal disposition is established.

The 209 discovery candidates are incomplete seeds: exhaust official BMF/BZSt
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

Calendar arithmetic is now available through engine PR #171, merged at
`f6b0d15246a7db1403836628576f11e0d334348c`, and dedicated RuleSpec pin PR #56
(merge `5460b74316deedbc50f48397b6586ad62bc71a06`). Calendar-month/year shifts
have tested month-end, leap-year, overflow and relation behavior. This does not
supply the legal inclusion/expiry semantics of BGB §§187–188 or resolve AO9's
non-temporary-stay and short-interruption judgments. The required encoder
builtin update merged in axiom-encode#1595 at
`002dc41952c925c6451d485c6d8c6381a1a811ad`. RuleSpec pin PR #57 passed
repository validation and merged at `c81939be1366649168284703ca8b542ec6045694`,
binding that encoder and the new corpus release.

Protected §32 allowance generation 34285315505 produced zero signatures.
Amounts compiled and passed numeric grounding, but the candidate's deferrals
claimed missing runtime relationship support and failed the completeness gate.
A missing legal definition is not proof that relations cannot be represented.
No rejected §32 candidate is declared encoded. Fresh §78 retry 34285955474 was
blocked before generation by the existing three-failed-attempt limit. The
repository-wide override has not been enabled while concurrent US work runs.

BGB187 run 34289192829 produced signed PR #58, but review found an unsupported
1998 boundary copied from the maternity example. PR #58 was closed unmerged. Supervised corrected run 34290391532 produced
PR #59, which passed repository CI and merged at
`8dd7d2e040ba99b84e9f92d8d63434c9ce46726b`. Its 2025 observation start is
explicitly not a statutory commencement. Three date inputs drive the first
included day; applicable-regime selection, deadline ends and full legal ages
still require encoding. The consumer now declares this signed prerequisite.

Encoder PR #1597 adds an expiring numeric retry limit for one exact citation.
Independent review and full CI passed; it merged at
`bf676a948578b2a5c2aeb43df6f63ed2107ca417`. Dedicated pin PR #60 passed
CI and merged at `46d9c0559b90443662c564f0731fba9243c52ab7`. Retry
34293870108 passed its exact-citation numeric attempt guard; the temporary
entry was then removed. The global limit remains three and the global override
remains false. The protected generation is running; no §78 output is yet declared.

Regeneration (supply the pinned corpus and RuleSpec checkouts as needed):

```
python scripts/de_closure.py
python scripts/de_closure_ledger.py --generate --artifact de/kindergeld
python scripts/de_certificate_census.py
python scripts/certify.py
```
