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

## Surcharge activation and expired safeguard

[The temporal receipt](../../reference/us-tariff-schedule/boundary-evidence/temporal-boundaries.json)
adds `entry_is_section_122_exempt` and `entry_is_section_201_cspv`. Two new live
GPO PDFs, 2026-03824 and 2022-02906, bind the surcharge's activation and the
solar safeguard's last staged period. Full source PDFs, sanitized HTTP metadata,
visually checked pages and source hashes are retained.

The real engine executes 43 cases / 43 outputs. Forty-one match; two generated
section 122 cases charge 10% at February 24 00:00:00 and 00:00:59 Eastern,
before the proclamation's 00:01 activation. The Day precision contract therefore
also blocks this scope. Noon exemption and expiry controls match. The precise
end boundary remains unresolved: the proclamation says through July 24 00:01,
while the Rev15 compiler note says close of July 23. No end-minute judgment is
invented. The full exemption flag remains an external determination.

All 20 post-expiry solar runtime cases return zero, including the adapter's
positive CSPV-cell classification. This validates the expired behavior only:
the composition begins February 15, after the safeguard's February 6 end date.
Active-period rates, quotas and complete CSPV classification are unvalidated.
The older 5 GW quota is not represented as the final 12.5 GW quota in Rev15.

## China list incidence and duplicate beer charge

[The list receipt](../../reference/us-tariff-schedule/boundary-evidence/china-lists.json)
adds the aggregate list 1/2/3 flag (tested on list 3 members) and list 4A flag.
The authenticated source pages bind ferroalloy and beer to heading 9903.88.03
at 25%, and the sports-ball line to 9903.88.15 at 7.5%. Exclusion qualification
is stipulated absent; complete list 1/2 and exclusion coverage is unvalidated.

The real adapter classifies all nine source/three-origin cases correctly. In
18 real runtime cases, the generated chapter 22 China beer case charges 50%
because it adds both `entry_is_china_301_list123` and `entry_is_line_d` terms.
The witness charges the source's single 25%. Seventeen other cases match.
The complete overlap counterexample is preserved; the aggregate list scope
stays blocked pending an authorized composition repair and review.

## Non-flat Column 2 blocker

[The Column 2 receipt](../../reference/us-tariff-schedule/boundary-evidence/column2-resolution.json)
adds the source-bound external-resolution contract. A new live General Note 3
PDF confirms all four Column 2 origins. The real engine makes 41 diagnostic
calls: 29 outputs match the contract/disposition checks, and 12 calls exit with
an explicit missing `resolved_non_ad_valorem_column2_rate` error. Missing input
is never replaced with zero. The supplied numeric sentinels only test the
receiver; **zero legal resolved rates are validated**.

The sampled archival chapter 99 rows explicitly expired before 2012 or at the
end of 2020. Their 2026 calls are interface diagnostics, not current-entry duty
calculations. Admission needs an appropriate vintage, the underlying duty for
“No change,” actual quantities/units/customs value, and a real resolver receipt.
The complete native errors and requests are retained; this scope stops at the
precise external-resolution/vintage blocker.

Current source coverage is **19 of the original 21 repaired scopes**: 12 with
no legal counterexample under their bounded contracts, five with counterexamples,
one post-expiry-only scope and one diagnostic-contract-only scope. Aluminum and
steel remain outside the captured batches. All 58 actual-entry groundings remain
uncaptured; admitted/grounded scopes remain zero. See the
[updated frontier](../../reference/us-tariff-schedule/boundary-evidence/frontier-inventory.json).

## Reproduction and current-base hold

```sh
python scripts/us_tariff_live_source_evidence.py --check
python scripts/build_us_tariff_note52_boundary_evidence.py --check
python scripts/build_us_tariff_identity_evidence.py --check
python scripts/build_us_tariff_china_action_evidence.py --check
python scripts/build_us_tariff_temporal_evidence.py --check
python scripts/build_us_tariff_china_list_evidence.py --check
python scripts/build_us_tariff_column2_evidence.py --check
python -m pytest -q tests/test_us_tariff_live_source_evidence.py \
  tests/test_us_tariff_note52_boundary_evidence.py \
  tests/test_us_tariff_identity_evidence.py \
  tests/test_us_tariff_china_action_evidence.py \
  tests/test_us_tariff_temporal_evidence.py \
  tests/test_us_tariff_china_list_evidence.py \
  tests/test_us_tariff_column2_evidence.py
```

33 targeted tests pass across the source and continuation batches. Real replay --check reproduces the exact receipt,
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
