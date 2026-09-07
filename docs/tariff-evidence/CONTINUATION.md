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

Current source coverage is **8 of the original21repaired scopes**, of which
7have no counterexample in their bounded batches and1has this precision blocker.
13remain outside the captured batches. All58actual-entry groundings remain
uncaptured; fully admitted/grounded scopes remain zero. See the
[updated frontier](../../reference/us-tariff-schedule/boundary-evidence/frontier-inventory.json).

## Reproduction and current-base hold

```sh
python scripts/us_tariff_live_source_evidence.py --check
python scripts/build_us_tariff_note52_boundary_evidence.py --check
python -m pytest -q tests/test_us_tariff_live_source_evidence.py \
  tests/test_us_tariff_note52_boundary_evidence.py
```

15targeted tests pass. Real replay --check reproduces the exact receipt,
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
