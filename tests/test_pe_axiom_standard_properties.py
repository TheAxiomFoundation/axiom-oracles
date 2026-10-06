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
I8  A raise binds: an accepted document's open_max never exceeds a committed
    version's open_max plus the increments (to - from) of the raise records
    it adds, and it keeps every committed raise record.
I9  Accounting: companion + debt + missing = attributed; open = debt + missing.
I10 Attribution is order-independent, and only upstream_engine_gap entries
    attribute.
I11 Companion pointers round-trip through str and parse.
I12 Merge: two branches that each moved only as the gate allowed can always
    be merged. Re-pinning either side's ratchet file (plus a raise when the
    merged open count rose) passes check_history against every version on
    both branches, unless the merged data itself regresses an entry.
"""

from __future__ import annotations

import copy

import yaml
from hypothesis import example, given, settings
from hypothesis import strategies as st

from axiom_oracles.comparison.pe_axiom_standard import (
    UPSTREAM_ENGINE_GAP,
    effective_ratchet,
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


NEW_IDS = "ghij"
MOVES = ("keep", "keep", "keep", "issue", "side", "drop", "regress")


@st.composite
def evolved(draw, records: list[Record]) -> list[Record]:
    """The next data state: existing records persist, improve, regress or go,
    and new attributions appear (mostly with declared debt, which needs a
    raise, so raises are common rather than rare)."""

    out: list[Record] = []
    for record in records:
        move = draw(st.sampled_from(MOVES))
        if move == "drop":
            continue
        pe = record.pe_issue is not None
        rank = AXIOM_SIDES.index(record.axiom_status)
        if move == "issue":
            pe = True
        elif move == "side":
            rank = min(rank + 1, 2)
        elif move == "regress":
            pe, rank = (False, rank) if pe else (pe, max(rank - 1, 0))
        out.append(_record(record.source, record.id, record.concept, pe, AXIOM_SIDES[rank]))
    taken = {(r.source, r.id) for r in out}
    for new_id in draw(st.lists(st.sampled_from(NEW_IDS), max_size=2, unique=True)):
        source = draw(st.sampled_from(SOURCES))
        if (source, new_id) in taken:
            continue
        side = draw(st.sampled_from(("debt", "debt", "companion", "missing")))
        out.append(_record(source, new_id, CONCEPTS[0], True, side))
        taken.add((source, new_id))
    return out


def _commit(
    records: list[Record],
    current: Ratchet,
    *,
    raise_allowed: bool,
    versions=(),
    reason: str = "r",
):
    """What a contributor can commit: a re-pin, or a raise when only the
    ceiling blocks. ``None`` when the gate refuses the data change."""

    effective = effective_ratchet(current, versions)
    problems = check_records(records, effective)
    if not problems:
        return _parse(derive_ratchet(records, effective))
    if raise_allowed and _only_the_ceiling(problems):
        return _parse(
            derive_ratchet(records, effective, raise_reason=reason, today=TODAY)
        )
    return None


@st.composite
def branch(draw, records: list[Record], ratchet: Ratchet, name: str, steps: int = 3):
    """A line of commits from (records, ratchet) that the gate allowed."""

    versions: list[tuple[str, Ratchet]] = []
    for step in range(draw(st.integers(0, steps))):
        candidate = draw(evolved(records))
        following = _commit(
            candidate, ratchet, raise_allowed=draw(st.booleans()), reason=f"{name}{step}"
        )
        if following is None:
            continue  # refused; the data change is not committed
        records, ratchet = candidate, following
        versions.append((f"{name}{step}", ratchet))
    return records, ratchet, versions


@st.composite
def committed_ratchets(draw) -> tuple[list[Record], Ratchet]:
    """A ratchet the script could have committed, and the records it saw."""

    records = draw(overlapping_records)
    ratchet = _parse(derive_ratchet(records, None))
    records, ratchet, _ = draw(branch(records, ratchet, "c"))
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
@example(
    records=[_record(SOURCES[0], "NEL\u0085id", CONCEPTS[0], False, "missing")],
    current=([], _parse(derive_ratchet([], None))),
)
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
@given(start=overlapping_records, data=st.data())
def test_replayed_repins_and_raises_pass_history(start, data) -> None:
    current = _parse(derive_ratchet(start, None))
    records, versions = start, [("v0", current)]
    for step in range(1, 7):
        candidate = data.draw(evolved(records), label=f"state{step}")
        following = _commit(candidate, current, raise_allowed=data.draw(st.booleans()))
        if following is None:
            continue  # the gate refuses this change; nothing is committed
        assert check_records(candidate, following) == []
        assert check_history(following, versions) == []
        records, current = candidate, following
        versions.append((f"v{step}", following))


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
    increment = raise_to - raise_from if append_raise else 0
    assert open_max <= committed.open_max + increment


# --------------------------------------------------------------------------
# I12: parallel branches always merge
# --------------------------------------------------------------------------


@PROPERTY_SETTINGS
@example(current_pe=False, historical_pe=True)
@given(current_pe=st.booleans(), historical_pe=st.booleans())
def test_merged_grandfather_status_keeps_highest_pe_issue(
    current_pe, historical_pe
) -> None:
    """A merge preserves every recorded PE-issue improvement."""

    missing = _record(SOURCES[0], "a", CONCEPTS[0], False, "missing")
    current = _parse(
        derive_ratchet(
            [_record(SOURCES[0], "a", CONCEPTS[0], current_pe, "missing")], None
        )
    )
    historical = _parse(
        derive_ratchet(
            [_record(SOURCES[0], "a", CONCEPTS[0], historical_pe, "missing")], None
        )
    )
    merged = effective_ratchet(current, [("other-branch", historical)])
    assert merged.grandfathered[missing.key]["pe_issue"] == (
        "present" if current_pe or historical_pe else "missing"
    )
    problems = check_records([missing], merged)
    assert any("grandfathered entry regressed" in p for p in problems) == (
        current_pe or historical_pe
    )


@PROPERTY_SETTINGS
@given(start=overlapping_records, data=st.data())
def test_parallel_branches_always_merge(start, data) -> None:
    base = _parse(derive_ratchet(start, None))
    base_records, base, trunk = data.draw(branch(start, base, "m"), label="trunk")
    history = [("m", base)] + trunk
    a_records, a, a_versions = data.draw(branch(base_records, base, "a"), label="a")
    b_records, b, b_versions = data.draw(branch(base_records, base, "b"), label="b")
    versions = history + a_versions + b_versions
    # The merged data: one side's records plus the other side's new ones, or a
    # further evolution of that.
    keys = {(r.source, r.id) for r in a_records}
    merged_records = a_records + [r for r in b_records if (r.source, r.id) not in keys]
    merged_records = data.draw(st.sampled_from([merged_records, b_records, a_records]))
    # The merge takes one side's ratchet file as-is and re-pins it.
    side = data.draw(st.sampled_from([a, b]), label="file taken")
    merged = _commit(merged_records, side, raise_allowed=True, versions=versions)
    if merged is None:
        # Refused only for a genuine violation in the merged data: a new
        # attribution without its Axiom side, or a regressed grandfathered
        # entry, judged against what history allows.
        problems = check_records(merged_records, effective_ratchet(side, versions))
        assert problems and not _only_the_ceiling(problems)
        return
    assert check_records(merged_records, merged) == []
    assert check_history(merged, versions) == []


@PROPERTY_SETTINGS
@given(start=overlapping_records, data=st.data())
def test_parallel_raises_merge(start, data) -> None:
    # Each branch adds its own new debt-backed attribution and raises for it,
    # possibly after other gate-allowed commits; the merge keeps both.
    base = _parse(derive_ratchet(start, None))
    versions = [("m", base)]
    tips = []
    for name, new_id in (("a", "g"), ("b", "h")):
        records, ratchet, line = data.draw(branch(start, base, name, steps=2), label=name)
        records = [r for r in records if r.id not in "gh"] + [
            _record(SOURCES[0], new_id, CONCEPTS[0], True, "debt")
        ]
        raised = _commit(records, ratchet, raise_allowed=True, reason=f"{name} raise")
        if raised is None:
            return  # this branch's data is refused for another reason
        versions += line + [(f"{name}-raise", raised)]
        tips.append((records, raised))
    (a_records, a), (b_records, b) = tips
    merged_records = a_records + [r for r in b_records if r.id == "h"]
    side = data.draw(st.sampled_from([a, b]), label="file taken")
    merged = _commit(merged_records, side, raise_allowed=True, versions=versions)
    if merged is None:
        problems = check_records(merged_records, effective_ratchet(side, versions))
        assert problems and not _only_the_ceiling(problems)
        return
    # check_history also proves every raise record either branch committed
    # survived the merge (the log only grows).
    assert check_records(merged_records, merged) == []
    assert check_history(merged, versions) == []


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
