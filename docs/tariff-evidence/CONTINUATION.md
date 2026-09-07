# Live-source continuation

The clean milestone `a7d2bf13af1b64fa20695e7347e933c76f5efe2c` remains on
`sprint/tariff-evidence-20260907`, with its Git/replay bundles unchanged. Work
continues on `sprint/tariff-evidence-continuation-20260907`, integrated with live
origin/main `ef012e83cd2e8b9b7afd4829841d9e29bc173d42`.

## Live source authenticity

[The live-source receipt](../../reference/us-tariff-schedule/boundary-evidence/live-sources/receipt.json)
contains actual HTTPS retrieval metadata and SHA-256 bindings for the official
USITC Rev15 Chapter99 PDF, GeneralNote11 PDF and GPO FederalRegister action
2026-15181. Chapter99 exactly matches the frozen original. These are archived
primary snapshots, not claims that Rev15 is the latest law. Raw source bodies
are committed; cookies/local connection metadata are omitted from HTTP records.

The original Chapter99 ingest's Ed25519 signature now verifies through the
pinned canonical axiom-corpus verifier, using the actual public trust root from
the authenticated repository Actions variable. Its applied PDF and provisions
hashes match. The previous receipt's not-performed signature label is historical;
this separate receipt supplies the newly performed verification. GeneralNote11
and the FederalRegister action are direct-source captures, not new signed ingests.
No GPO PDF signature verification or new signature creation is claimed.

## Two new scopes and a real counterexample

[The note52 receipt](../../reference/us-tariff-schedule/boundary-evidence/note52-transit-usmca.json)
adds source evidence for `entry_is_entered_free_of_duty_under_usmca` and
`entry_loaded_and_in_transit_before_july_24_2026`. It executes the pinned real
Axiom engine on 230 synthetic cases/690 outputs in the witness and generated
chapter95. Countries are Canada, Mexico, Argentina, UnitedKingdom and a United
States negative control. Both Boolean inputs vary jointly. Other exception
facts are explicitly false; the generated nonexempt product membership is
stipulated true and is outside this batch's claim.

All200noon controls match, as do10probes exactly at the cutoff. **Twenty probes
before the cutoff do not match.** Heading9903.05.85 and the FederalRegister
notice use July28,2026 at00:01eastern, but the program stops the safe harbor
at the Day boundary. A stipulated qualifying shipment entered at00:00:00 or
00:00:59 still qualifies under the source. Both programs return false and
charge0.1 for covered origins. The UnitedStates control remains zero-duty but
also loses the source-qualified predicate. The complete requests, responses,
traces and expected-versus-actual counterexamples are retained.

The receipt therefore states `all_cases_match=false`. Full admission of the
transit scope is blocked on a timestamp precision contract and a supervised
encoder repair. No hand-written RuleSpec fix was made. USMCA remains a
stipulated fact: GeneralNote11(b) and applicable entry requirements must be
established separately; origin alone does not determine qualification.

## HTS identity and lookup contracts

[The identity receipt](../../reference/us-tariff-schedule/boundary-evidence/hts-identity.json)
adds the three named line flags and `hts_line`. New live USITC Chapters 72, 76
and 22 PDFs support seven legal/statistical lines, including negative neighbors.
The actual pinned adapter accepts dotted, digit-only, spaced and hyphenated
codes. All 28 canonical witness calls match its identity flags; nine raw alias
calls differ because the witness compares dotted Text literally. The receipt
retains both results and requires normalization at the direct witness boundary.

Generated-table lookups take an **Integer legal rate-row key**. Aluminum
7601.10.60.40 uses 7601106000; beer suffixes 30/60/90 use 2203000000. All seven
rate/disposition lookups match the visually checked official pages. Beer keeps
its specific Column 2 disposition (13.2 cents/liter); no ad-valorem equivalent
is inferred. This batch executes 63 real cases / 189 outputs plus 28 adapter
calls. It establishes a bounded input contract, not actual classification.

The note 52 request now supplies the correct integer `hts_line` instead of an
unused dotted Text value. Its 230 cases / 690 outputs and 20 known time-precision
counterexamples are unchanged. All frozen original proofs remain untouched.

## China action adapter counterexamples

[The note 31 receipt](../../reference/us-tariff-schedule/boundary-evidence/china-action.json)
adds `entry_is_china_301_2024_action` and `entry_is_china_301_solar`. The live
USITC snapshot and newly downloaded GPO notice 2024-21217 establish positive
classifications at 7601.10.30 and 8541.42.00, with respective additional rates
of 25% and 50% for China. The PDF pages and their rate columns were visually
checked; the original notice's extraction warnings are preserved.

The real pinned adapter (`tools/b16_entry_flags.py:385–386`) returns false for
both inputs. In 36 real runtime cases, the direct witness and generated programs
with explicitly declared source membership match. Four generated-program cases
using actual adapter facts return zero for China instead of the source rates.
Hong Kong and France controls remain zero. These are preserved counterexamples,
not repairs or invented proof of complete note 31 coverage. The broad 2024-action
scope also needs a heading-specific contract; other note 31 rate families must
not be collapsed into this 25% Boolean component.

Both scopes remain blocked pending complete source-grounded adapter membership,
exclusion/precedence validation and the authorized encoding workflow. All code
under the pinned RuleSpec repository remains untouched.

Current source coverage is **14 of the original 21 repaired scopes**. Eleven
have no legal counterexample within their documented bounded contracts; three
have explicit blockers. Seven remain outside the captured batches. All 58
actual-entry groundings remain uncaptured; admitted/grounded scopes remain zero.
See the [updated frontier](../../reference/us-tariff-schedule/boundary-evidence/frontier-inventory.json).

## Reproduction and current-base hold

```sh
python scripts/us_tariff_live_source_evidence.py --check
python scripts/build_us_tariff_note52_boundary_evidence.py --check
python scripts/build_us_tariff_identity_evidence.py --check
python scripts/build_us_tariff_china_action_evidence.py --check
python -m pytest -q tests/test_us_tariff_live_source_evidence.py \
  tests/test_us_tariff_note52_boundary_evidence.py \
  tests/test_us_tariff_identity_evidence.py \
  tests/test_us_tariff_china_action_evidence.py
```

24 targeted tests pass across the source and continuation batches. Real replay --check reproduces the exact receipt,
including its20known counterexamples. The input cache is the same immutable
RuleSpec commit and pinned executable used by the preserved milestone.

Current main changed `axiom_oracles/comparison/comparator.py` and `report.py`.
The preserved causal-proof gate deliberately expires on such source changes.
The canonical merged certificate therefore records conformant=false while
exercised/executable remain true and closed/certified remain false.
[Exact old/current bindings](continuation-integration-hold.json) document why.
The original milestone's qualified conformance and all four proof bytes remain
preserved. We did not repin old measurements to new code or rescan216millionrows.
Review must decide how to admit the historical generation under the new base.

Root can arrange the required bounded Fable review. No limited-account retries,
resets, overflow, new paid compute, publication, merge or activation occurred.
