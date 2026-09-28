"""Invariants of the PolicyEngine -> Axiom standard gate, for every input.

Property-based companions to tests/test_pe_axiom_standard.py, which holds the
example and end-to-end (Git history, CLI) tests. Each test states one
invariant the gate's ratchet relies on:

I1  Bootstrap soundness: the ratchet derived from any record set with no
    prior ratchet passes check_records and check_history.
I2  Round trip: serialize_ratchet -> yaml.safe_load -> Ratchet.from_document
    is the identity on derived documents.
I3  Re-pin is idempotent.
I4  Re-pin never loosens: open_max, the grandfathered keys and debt_raises
    never grow, and when the current ratchet passes, the re-pinned one
    passes check_records and check_history against it.
I5  Improvement is monotone: a passing gate keeps passing when a record
    gains a PolicyEngine issue or a stronger Axiom side, or disappears.
I6  Differential: the grandfathered entries check_records reports as
    regressed are exactly those check_history reports as lowered in the
    re-pinned file (the two monotonic checkers agree).
I7  Replay: any sequence of re-pins and deliberate raises, each taken only
    when the gate allows it, passes check_history against every earlier
    committed version.
I8  A raise binds: an accepted document's open_max never exceeds the
    committed ceiling or its latest raise's ``to``, and an appended raise's
    ``from`` never exceeds the committed ceiling it replaces.
I9  Accounting: companion + debt + missing = attributed; open = debt + missing.
I10 Attribution is order-independent, and only upstream_engine_gap entries
    attribute.
I11 Companion pointers round-trip through str and parse.
"""

from __future__ import annotations

import copy

import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.comparison.pe_axiom_standard import (
    UPSTREAM_ENGINE_GAP,
    CompanionPointer,
    Ratchet,
    RatchetDocumentError,
    Record,
    attribute_disposition,
    check_history,
    check_records,
    derive_ratchet,
    serialize_ratchet,
    summarize,
    validate_axiom_side_fields,
)

PROPERTY_SETTINGS = settings(max_examples=300, deadline=None, derandomize=True)

CONCEPTS = (
    "us:policies/income_tax/example_pipeline#federal_example",
    "us-ca:policies/ftb/example#state_example",
)
SOURCES = (
    "dispositions/us-a-grid.yaml",
    "dispositions/us-b-grid.yaml",
    "dashboard/public/data/known_causes.json",
)
PE_ISSUE = "https://github.com/PolicyEngine/policyengine-us/issues/1"
DEBT_ISSUE = "https://github.com/TheAxiomFoundation/rulespec-us/issues/2"
COMPANION = {
    "legal_ids": [CONCEPTS[0]],
    "tests": [
        "rulespec-us@" + "a" * 40
        + ":us/policies/income_tax/example_pipeline.test.yaml#case-1"
    ],
}
AXIOM_SIDES = ("missing", "debt", "companion")
TODAY = "2026-09-27"


def _record(source: str, record_id: str, concept: str, pe: bool, axiom: str) -> Record:
    entry: dict = {}
    if axiom == "debt":
        entry["axiom_encoding_debt"] = DEBT_ISSUE
    elif axiom == "companion":
        entry["axiom_companion"] = copy.deepcopy(COMPANION)
    return Record(
        source=source,
        id=record_id,
        suite="suite",
        concept=concept,
        basis="rows",
        pe_issue=PE_ISSUE if pe else None,
        entry=entry,
    )


def _records(ids: st.SearchStrategy[str]) -> st.SearchStrategy[list[Record]]:
    spec = st.tuples(
        st.sampled_from(SOURCES),
        ids,
        st.sampled_from(CONCEPTS),
        st.booleans(),
        st.sampled_from(AXIOM_SIDES),
    )
    # Unique by (source, id) so a label names exactly one record.
    return st.lists(spec, max_size=12, unique_by=lambda s: (s[0], s[1])).map(
        lambda specs: [_record(*s) for s in specs]
    )


# Any text, including YAML-significant and non-ASCII characters, for the
# round-trip property; a small id space elsewhere so that successive record
# sets overlap (records persist, improve, regress, appear and disappear).
any_records = _records(st.text(min_size=1, max_size=8))
overlapping_records = _records(st.sampled_from("abcdef"))


def _parse(document: dict) -> Ratchet:
    return Ratchet.from_document(yaml.safe_load(serialize_ratchet(document)))


def _open(records: list[Record]) -> int:
    return sum(1 for r in records if r.open)


def _only_the_ceiling(problems: list[str]) -> bool:
    return bool(problems) and all(p.startswith("RATCHET regressed") for p in problems)


@st.composite
def committed_ratchets(draw) -> tuple[list[Record], Ratchet]:
    """A ratchet the script could have committed, and the records it saw."""

    records = draw(overlapping_records)
    ratchet = _parse(derive_ratchet(records, None))
    for later in draw(st.lists(overlapping_records, max_size=3)):
        problems = check_records(later, ratchet)
        if not problems:
            ratchet = _parse(derive_ratchet(later, ratchet))
        elif _only_the_ceiling(problems):
            ratchet = _parse(
                derive_ratchet(later, ratchet, raise_reason="r", today=TODAY)
            )
    return records, ratchet


# --------------------------------------------------------------------------
# I1-I4: bootstrap, round trip, idempotence, never loosens
# --------------------------------------------------------------------------


@PROPERTY_SETTINGS
@given(records=any_records)
def test_bootstrap_passes_the_records_it_was_derived_from(records) -> None:
    ratchet = _parse(derive_ratchet(records, None))
    assert check_records(records, ratchet) == []
    assert check_history(ratchet, [("self", ratchet)]) == []
    assert ratchet.open_max == _open(records)
    assert set(ratchet.grandfathered) == {r.key for r in records if not r.compliant}


@PROPERTY_SETTINGS
@given(records=any_records, current=committed_ratchets())
def test_serialization_round_trips(records, current) -> None:
    for document in (
        derive_ratchet(records, None),
        derive_ratchet(records, current[1]),
        derive_ratchet(records, current[1], raise_reason="a: b # c", today=TODAY),
    ):
        assert _parse(document) == Ratchet.from_document(document)


@PROPERTY_SETTINGS
@given(records=overlapping_records, current=committed_ratchets())
def test_repin_is_idempotent(records, current) -> None:
    once = derive_ratchet(records, current[1])
    assert derive_ratchet(records, _parse(once)) == once


@PROPERTY_SETTINGS
@given(records=overlapping_records, current=committed_ratchets())
def test_repin_never_loosens(records, current) -> None:
    committed = current[1]
    repinned = _parse(derive_ratchet(records, committed))
    assert repinned.open_max <= committed.open_max
    assert set(repinned.grandfathered) <= set(committed.grandfathered)
    assert repinned.debt_raises == committed.debt_raises
    if check_records(records, committed) == []:
        assert check_records(records, repinned) == []
        assert check_history(repinned, [("committed", committed)]) == []


# --------------------------------------------------------------------------
# I5-I7: monotone improvement, differential, replay
# --------------------------------------------------------------------------


@PROPERTY_SETTINGS
@given(
    records=overlapping_records,
    current=committed_ratchets(),
    moves=st.lists(st.sampled_from(("keep", "issue", "side", "drop")), max_size=12),
)
def test_improvement_never_fails_a_passing_gate(records, current, moves) -> None:
    committed = current[1]
    if check_records(records, committed):
        return
    improved: list[Record] = []
    for index, record in enumerate(records):
        move = moves[index] if index < len(moves) else "keep"
        if move == "drop":
            continue
        pe = record.pe_issue is not None or move == "issue"
        rank = AXIOM_SIDES.index(record.axiom_status)
        axiom = AXIOM_SIDES[min(rank + 1, 2)] if move == "side" else record.axiom_status
        improved.append(_record(record.source, record.id, record.concept, pe, axiom))
    assert check_records(improved, committed) == []


@PROPERTY_SETTINGS
@given(records=overlapping_records, current=committed_ratchets())
def test_regression_checks_agree(records, current) -> None:
    committed = current[1]
    live_problems = check_records(records, committed)
    history_problems = check_history(
        _parse(derive_ratchet(records, committed)), [("committed", committed)]
    )
    labels = {(r.source, r.id) for r in records}
    regressed = {
        label
        for label in labels
        if any(
            p.startswith(f"{label[0]} [{label[1]}]: grandfathered entry regressed")
            for p in live_problems
        )
    }
    lowered = {
        label
        for label in labels
        if any(
            p.startswith(f"grandfathered status of {label[0]} [{label[1]}] fell below")
            for p in history_problems
        )
    }
    assert regressed == lowered


@PROPERTY_SETTINGS
@given(
    states=st.lists(overlapping_records, min_size=1, max_size=6),
    raise_when_allowed=st.lists(st.booleans(), min_size=6, max_size=6),
)
def test_replayed_repins_and_raises_pass_history(states, raise_when_allowed) -> None:
    current = _parse(derive_ratchet(states[0], None))
    versions = [("v0", current)]
    for step, records in enumerate(states[1:], start=1):
        problems = check_records(records, current)
        if not problems:
            document = derive_ratchet(records, current)
        elif _only_the_ceiling(problems) and raise_when_allowed[step - 1]:
            document = derive_ratchet(records, current, raise_reason="r", today=TODAY)
        else:
            continue  # the gate refuses this change; nothing is committed
        following = _parse(document)
        assert check_records(records, following) == []
        assert check_history(following, versions) == []
        versions.append((f"v{step}", following))
        current = following


# --------------------------------------------------------------------------
# I8: a raise record binds the ceiling it authorizes
# --------------------------------------------------------------------------


def _near(anchor: int) -> st.SearchStrategy[int]:
    """Anywhere in range, or within a few of a boundary that matters."""

    return st.one_of(
        st.integers(0, 200), st.integers(max(0, anchor - 3), anchor + 3)
    )


@PROPERTY_SETTINGS
@given(current=committed_ratchets(), data=st.data())
def test_an_accepted_document_is_bound_by_its_raise(current, data) -> None:
    committed = current[1]
    append_raise = data.draw(st.booleans(), label="append_raise")
    raise_from = data.draw(_near(committed.open_max), label="raise_from")
    raise_to = data.draw(_near(raise_from), label="raise_to")
    open_max = data.draw(
        _near(raise_to if append_raise else committed.open_max), label="open_max"
    )
    document = derive_ratchet([], committed)
    document["grandfathered"] = []
    document["open_max"] = open_max
    raises = [dict(item) for item in committed.debt_raises]
    if append_raise:
        raises.append(
            {"date": TODAY, "from": raise_from, "to": raise_to, "reason": "hand edit"}
        )
    if raises:
        document["debt_raises"] = raises
    try:
        edited = Ratchet.from_document(document)
    except RatchetDocumentError:
        return  # refused as malformed
    if check_history(edited, [("committed", committed)]):
        return  # refused as a loosening
    if append_raise:
        assert raise_from <= committed.open_max
        assert open_max <= raise_to
    else:
        assert open_max <= committed.open_max


# --------------------------------------------------------------------------
# I9: accounting identities
# --------------------------------------------------------------------------


@PROPERTY_SETTINGS
@given(records=any_records)
def test_summary_accounts_for_every_attribution(records) -> None:
    summary = summarize(records)
    assert (
        summary["axiom_companion"]
        + summary["axiom_encoding_debt"]
        + summary["axiom_side_missing"]
        == summary["pe_attributed"]
        == len(records)
    )
    assert summary["open"] == summary["axiom_encoding_debt"] + summary["axiom_side_missing"]
    assert summary["pe_issue_linked"] <= summary["pe_attributed"]


# --------------------------------------------------------------------------
# I10: attribution
# --------------------------------------------------------------------------

ENGINES = ("axiom", "policyengine-us", "policyengine_uk", "taxsim", "euromod")
ENTRY_IDS = ("gap-1", "gap-2")

rows = st.fixed_dictionaries(
    {
        "case_id": st.sampled_from(("c1", "c2", "c3")),
        "concept": st.sampled_from(CONCEPTS),
        "disposition": st.one_of(
            st.none(), st.fixed_dictionaries({"id": st.sampled_from(ENTRY_IDS)})
        ),
        "left": st.integers(0, 9),
        "right": st.integers(0, 9),
    },
    optional={
        "left_engine": st.sampled_from(ENGINES),
        "right_engine": st.sampled_from(ENGINES),
    },
)
reports = st.lists(
    st.fixed_dictionaries(
        {
            "engines": st.one_of(
                st.fixed_dictionaries(
                    {"left": st.sampled_from(ENGINES), "right": st.sampled_from(ENGINES)}
                ),
                st.dictionaries(st.sampled_from(ENGINES), st.just("1.0"), max_size=3),
            ),
            "mismatches": st.lists(rows, max_size=5),
        }
    ),
    max_size=3,
)
entries = st.fixed_dictionaries(
    {
        "id": st.sampled_from(ENTRY_IDS),
        "concept": st.sampled_from(CONCEPTS),
        "disposition": st.sampled_from(
            (UPSTREAM_ENGINE_GAP, "explained_residual", "bridge_artifact")
        ),
        "kind": st.sampled_from(("amount_difference", "policyengine_amount_difference")),
    },
    optional={"linked_issue": st.sampled_from((PE_ISSUE, DEBT_ISSUE))},
)


def _reversed(report_list: list[dict]) -> list[dict]:
    return [
        dict(report, mismatches=list(reversed(report["mismatches"])))
        for report in reversed(report_list)
    ]


@PROPERTY_SETTINGS
@given(entry=entries, report_list=reports)
def test_attribution_is_order_independent(entry, report_list) -> None:
    basis, case_ids, values = attribute_disposition(entry, report_list)
    basis2, case_ids2, values2 = attribute_disposition(entry, _reversed(report_list))
    assert basis == basis2
    assert set(case_ids) == set(case_ids2)
    assert {k: sorted(v, key=repr) for k, v in values.items()} == {
        k: sorted(v, key=repr) for k, v in values2.items()
    }


@PROPERTY_SETTINGS
@given(entry=entries, report_list=reports)
def test_only_engine_gaps_attribute_and_a_pe_link_always_does(entry, report_list) -> None:
    basis, _, _ = attribute_disposition(entry, report_list)
    if entry["disposition"] != UPSTREAM_ENGINE_GAP:
        assert basis is None
    elif entry.get("linked_issue") == PE_ISSUE:
        assert basis is not None


# --------------------------------------------------------------------------
# I11: companion pointers
# --------------------------------------------------------------------------

segments = st.from_regex(r"[A-Za-z0-9_-]{1,8}", fullmatch=True)
pointers = st.builds(
    CompanionPointer,
    repo=st.from_regex(r"rulespec-[a-z0-9-]{1,10}", fullmatch=True),
    sha=st.from_regex(r"[0-9a-f]{40}", fullmatch=True),
    path=st.lists(segments, min_size=1, max_size=4).map(
        lambda parts: "/".join(parts) + ".test.yaml"
    ),
    case=st.from_regex(r"\S(?:.*\S)?", fullmatch=True),
)
legal_ids = st.builds(
    lambda jurisdiction, path, output: f"{jurisdiction}:{path}#{output}",
    st.from_regex(r"[a-z]{2}(?:-[a-z]{2})?", fullmatch=True),
    st.lists(segments, min_size=1, max_size=3).map("/".join),
    st.from_regex(r"[a-z_]{1,12}", fullmatch=True),
)


@PROPERTY_SETTINGS
@given(pointer=pointers, ids=st.lists(legal_ids, min_size=1, max_size=3))
def test_companion_pointers_round_trip_and_validate(pointer, ids) -> None:
    assert CompanionPointer.parse(str(pointer)) == pointer
    entry = {"axiom_companion": {"legal_ids": ids, "tests": [str(pointer)]}}
    assert validate_axiom_side_fields(entry, "entry") == []
    assert validate_axiom_side_fields(
        entry, "entry", disposition_kind=UPSTREAM_ENGINE_GAP
    ) == []


@PROPERTY_SETTINGS
@given(pointer=pointers, cut=st.integers(0, 3))
def test_pointers_that_escape_the_repository_are_rejected(pointer, cut) -> None:
    parts = pointer.path.split("/")
    parts.insert(min(cut, len(parts) - 1), "..")
    escaped = f"{pointer.repo}@{pointer.sha}:{'/'.join(parts)}#{pointer.case}"
    assert CompanionPointer.parse(escaped) is None
    rooted = f"{pointer.repo}@{pointer.sha}:/{pointer.path}#{pointer.case}"
    assert CompanionPointer.parse(rooted) is None
