"""fiit-ecps EITC attribution: the committed evidence and the tooling behind it."""

from __future__ import annotations

import importlib.util
import itertools
import json
import math
import shutil
import sys
from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings, strategies as st

import axiom_oracles.bridges.tax_populace as tp

ROOT = Path(__file__).resolve().parents[1]
ATTRIBUTION = ROOT / "scripts" / "fiit_ecps_eitc_attribution"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


builder = _load(
    "build_fiit_ecps_eitc_dispositions", ROOT / "scripts" / "build_fiit_ecps_eitc_dispositions.py"
)
minimal_sets = _load("minimal_sets", ATTRIBUTION / "minimal_sets.py")
stage3 = _load("counterfactuals_stage3", ATTRIBUTION / "counterfactuals_stage3.py")


# --- the committed evidence ------------------------------------------------


def test_committed_evidence_dispositions_and_report_agree():
    assert builder.check(ROOT) == []


@pytest.fixture
def repo_copy(tmp_path):
    """The four files the audit reads, copied so a test can break one."""
    _, full = builder.bound_full_report(ROOT)
    copy = json.loads((ROOT / builder.DASHBOARD).read_text())
    source = copy["summary"]["dispositioned"]["source_report"]["path"]
    for relative in (builder.DASHBOARD, builder.EVIDENCE, builder.DISPOSITIONS, source):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    assert builder.check(tmp_path) == []
    return tmp_path


def _edit_json(path: Path, edit) -> None:
    data = json.loads(path.read_text())
    edit(data)
    path.write_text(json.dumps(data))


def _first(rows: dict, entry: str) -> str:
    return next(key for key, record in sorted(rows.items()) if record["entry"] == entry)


def test_audit_catches_a_case_moved_between_dispositions(repo_copy):
    path = repo_copy / builder.DISPOSITIONS
    document = yaml.safe_load(path.read_text())
    partnership, age = document["entries"][1], document["entries"][4]
    moved = partnership["case_selector"]["case_ids_by_output"]["eitc_earned_income"].pop()
    age["case_selector"]["case_ids_by_output"].setdefault("eitc_earned_income", []).append(moved)
    path.write_text(yaml.safe_dump(document, sort_keys=False))

    problems = builder.check(repo_copy)

    assert f"{partnership['id']}: selects other rows than its evidence" in problems
    assert f"{age['id']}: selects other rows than its evidence" in problems


def test_audit_catches_an_entry_its_stages_do_not_give(repo_copy):
    evidence = json.loads((repo_copy / builder.EVIDENCE).read_text())
    key = _first(evidence["rows"], "partnership")

    def relabel(data):
        data["rows"][key]["entry"] = "age"

    _edit_json(repo_copy / builder.EVIDENCE, relabel)
    problems = builder.check(repo_copy)
    assert f"{key}: entry 'age', stages give 'partnership'" in problems
    assert f"{builder.EVIDENCE}: entry counts are not its rows'" in problems


def test_audit_catches_evidence_values_that_are_not_the_reports(repo_copy):
    evidence = json.loads((repo_copy / builder.EVIDENCE).read_text())
    key = _first(evidence["rows"], "ctc")

    def nudge(data):
        data["rows"][key]["diff"] += 0.01

    _edit_json(repo_copy / builder.EVIDENCE, nudge)
    assert f"{key}: evidence values differ from the bound report's" in builder.check(repo_copy)


def test_audit_catches_a_row_missing_from_the_evidence(repo_copy):
    evidence = json.loads((repo_copy / builder.EVIDENCE).read_text())
    key = _first(evidence["rows"], "se_projection")
    _edit_json(repo_copy / builder.EVIDENCE, lambda data: data["rows"].pop(key))
    assert f"{key}: only in the bound report" in builder.check(repo_copy)


def test_audit_refuses_a_report_that_is_not_the_bound_bytes(repo_copy):
    copy = json.loads((repo_copy / builder.DASHBOARD).read_text())
    source = repo_copy / copy["summary"]["dispositioned"]["source_report"]["path"]
    source.write_text(source.read_text() + "\n")
    [problem] = builder.check(repo_copy)
    assert problem.startswith("bound FULL report:")
    assert "digest" in problem


@pytest.mark.parametrize(
    ("concept", "difference", "entry"),
    [
        (builder.TAX_BEFORE_CREDITS, -5.83, "tax_before_credits"),
        (builder.CAPITAL_GAIN, 3.25, "capital_gain"),
        (builder.CTC, 50.0, "ctc"),
    ],
)
def test_non_eitc_rows_need_their_signature(concept, difference, entry):
    row = {"case_id": "ecps-tax_unit_1", "output": "x", "concept": concept}
    assert builder.entry_of({**row, "difference": difference}, None, None) == entry
    with pytest.raises(ValueError, match="breaks"):
        builder.entry_of(
            {**row, "difference": difference + math.copysign(0.02, difference)}, None, None
        )


def test_eitc_rows_need_an_attribution():
    row = {"case_id": "ecps-tax_unit_1", "output": "x", "concept": builder.EITC}
    with pytest.raises(ValueError, match="without a stage-1 attribution"):
        builder.entry_of(row, None, None)
    with pytest.raises(ValueError, match="no entry"):
        builder.entry_of(row, "ambiguous:age|investment", None)
    assert builder.entry_of(row, "investment", "div_aggregate") == "dividend_aggregate"
    assert builder.entry_of(row, "investment", "cg_distributions") == "pe_investment"
    assert builder.entry_of(row, "age+investment", "farm_rent") == "age"


# --- minimal clearing sets ------------------------------------------------


MECHANISMS = ("a", "b", "c", "d")


def _reference_minimal(key, variants) -> set[frozenset[str]]:
    """Brute force: S clears the key and no nonempty proper subset of S does."""
    def clears(mechanisms):
        return key not in variants[mechanisms]

    found = set()
    for mechanisms in variants:
        if not mechanisms or not clears(mechanisms):
            continue
        subsets = (
            frozenset(subset)
            for size in range(1, len(mechanisms))
            for subset in itertools.combinations(sorted(mechanisms), size)
        )
        if not any(clears(subset) for subset in subsets):
            found.add(mechanisms)
    return found


@st.composite
def _stage(draw):
    names = MECHANISMS[: draw(st.integers(min_value=1, max_value=len(MECHANISMS)))]
    keys = [f"k{index}" for index in range(draw(st.integers(min_value=1, max_value=6)))]
    variants = {}
    for size in range(len(names) + 1):
        for combo in itertools.combinations(names, size):
            variants[frozenset(combo)] = frozenset(
                draw(st.sets(st.sampled_from(keys))) if combo else keys
            )
    return keys, variants, draw(st.randoms())


def _name(mechanisms):
    return "+".join(m for m in MECHANISMS if m in mechanisms)


@settings(max_examples=300)
@given(_stage())
def test_attribution_is_the_brute_force_minimal_sets(stage):
    keys, variants, rng = stage
    attribution = minimal_sets.attribute(keys, variants, _name)
    shuffled = list(variants.items())
    rng.shuffle(shuffled)
    assert minimal_sets.attribute(keys, dict(shuffled), _name) == attribution
    for key in keys:
        reference = _reference_minimal(key, variants)
        mechanism = attribution[key]["mechanism"]
        if not reference:
            assert mechanism == minimal_sets.RESIDUAL
        elif len(reference) == 1:
            [only] = reference
            assert mechanism == _name(only)
            assert key not in variants[only]
        else:
            assert mechanism == minimal_sets.AMBIGUOUS_PREFIX + "|".join(
                sorted(_name(m) for m in reference)
            )
        assert attribution[key]["clearing_variants"] == sorted(
            _name(m) for m, rows in variants.items() if m and key not in rows
        )


def test_the_base_never_clears():
    variants = {frozenset(): frozenset(), frozenset({"a"}): frozenset({"k"})}
    assert minimal_sets.attribute(["k"], variants, _name)["k"]["mechanism"] == "residual"


# --- stage 3 -------------------------------------------------------------


def test_stage3_base_check_allows_only_counterfactual_only_extras():
    target = {"tax_unit_1|eitc", "tax_unit_2|eitc"}
    full_run = {key: {} for key in target} | {"tax_unit_3|eitc": {}}
    # 2026-10-14: four eitc_eligible rows the full run does not have.
    ok, extra = stage3.base_check(target | {"tax_unit_27227|eitc_eligible"}, target, full_run)
    assert ok and extra == ["tax_unit_27227|eitc_eligible"]
    assert stage3.base_check(target, target, full_run) == (True, [])
    # A full-run row the base leaves belongs to another stage-1 mechanism.
    assert not stage3.base_check(target | {"tax_unit_3|eitc"}, target, full_run)[0]
    # The base must leave every target row.
    assert not stage3.base_check({"tax_unit_1|eitc"}, target, full_run)[0]


_AMOUNT = st.one_of(
    st.just(0.0),
    st.floats(min_value=-50_000, max_value=50_000, allow_nan=False).map(
        lambda value: round(value, 2)
    ),
)
_COLUMNS = (
    *tp.EITC_INTEREST_AND_DIVIDEND_COLUMNS,
    *tp.EITC_PASSIVE_INCOME_COLUMNS,
    "short_term_capital_gains",
    "non_sch_d_capital_gains",
    "long_term_capital_gains",
)


@st.composite
def _unit(draw):
    roles = draw(st.sampled_from(((True, False), (True, True))))
    dependents = draw(st.integers(min_value=0, max_value=2))
    persons = []
    for index, (head, spouse) in enumerate(
        [(True, False)] + ([(False, True)] if roles[1] else []) + [(False, False)] * dependents
    ):
        person = {
            "person_id": index,
            "age": 40 if head or spouse else 12,
            "is_tax_unit_head": head,
            "is_tax_unit_spouse": spouse,
        }
        for column in _COLUMNS:
            if draw(st.booleans()):
                person[column] = draw(_AMOUNT)
        persons.append(person)
    pe_people = {p["person_id"]: {"dividend_income": draw(_AMOUNT)} for p in persons}
    return persons, pe_people


def _close(left, right):
    return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-6)


@settings(max_examples=300)
@given(_unit())
def test_stage3_switch_model_without_switches_is_the_bridge(unit):
    """The check stage 3 runs on real units, over generated ones."""
    persons, pe_people = unit
    bridge = tp.project_eitc_relevant_investment_income(
        row=None, persons=tp.tax_unit_filers(persons)
    )
    assert _close(stage3.aggregate(persons, pe_people, frozenset()), bridge)


@settings(max_examples=200)
@given(_unit(), st.sets(st.sampled_from(stage3.SWITCHES)))
def test_stage3_switches_are_the_data_edits_they_name(unit, flags):
    persons, pe_people = unit
    flags = frozenset(flags)

    def edited(column):
        return [{**p, column: 0.0} for p in persons]

    # Leaving out a column is zeroing it.
    if "farm_rent" not in flags:
        assert _close(
            stage3.aggregate(persons, pe_people, flags | {"farm_rent"}),
            stage3.aggregate(edited("farm_rent_income"), pe_people, flags),
        )
    if "cg_distributions" not in flags:
        assert _close(
            stage3.aggregate(persons, pe_people, flags | {"cg_distributions"}),
            stage3.aggregate(edited("non_sch_d_capital_gains"), pe_people, flags),
        )
    # The stored aggregate replaces the components, person by person.
    if "div_aggregate" not in flags:
        stored = [
            {
                **p,
                "qualified_dividend_income": pe_people[p["person_id"]]["dividend_income"],
                "non_qualified_dividend_income": 0.0,
            }
            for p in persons
        ]
        assert _close(
            stage3.aggregate(persons, pe_people, flags | {"div_aggregate"}),
            stage3.aggregate(stored, pe_people, flags),
        )
    # Counting dependents is filing every member's amounts together: the
    # baskets are summed over people before any floor, so one head holding
    # the unit's totals is the same aggregate.
    if "dependents" not in flags:
        merged = {"person_id": 0, "age": 40, "is_tax_unit_head": True,
                  "is_tax_unit_spouse": False}
        for column in _COLUMNS:
            merged[column] = sum(p.get(column, 0.0) for p in persons)
        merged_pe = {0: {"dividend_income": sum(v["dividend_income"] for v in pe_people.values())}}
        assert _close(
            stage3.aggregate(persons, pe_people, flags | {"dependents"}),
            stage3.aggregate([merged], merged_pe, flags),
        )
    # Unflooring the passive basket can only lower the aggregate.
    if "rental_unfloor" not in flags:
        floored = stage3.aggregate(persons, pe_people, flags)
        unfloored = stage3.aggregate(persons, pe_people, flags | {"rental_unfloor"})
        assert unfloored <= floored + 1e-6
