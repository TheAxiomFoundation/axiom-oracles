"""fiit-ecps EITC attribution: the committed evidence and the tooling behind it."""

from __future__ import annotations

import importlib.util
import itertools
import json
import math
import re
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


def _edit_first_disposition(root: Path, edit) -> str:
    path = root / builder.DISPOSITIONS
    document = yaml.safe_load(path.read_text())
    edit(document["entries"][0])
    path.write_text(yaml.safe_dump(document, sort_keys=False))
    return document["entries"][0]["id"]


@pytest.mark.parametrize(
    ("edit", "expected"),
    [
        # The selection lists still match the evidence; production loses the
        # rows to the filter, the binding or the missing binding (sol review
        # of #635, finding 2).
        (lambda entry: entry.update(kind="error"), "the merge gives 7627 of its rows to None"),
        (
            lambda entry: entry.update(concept="us:tax/federal-income-tax#ctc"),
            "the merge gives 7627 of its rows to None",
        ),
        (
            lambda entry: entry["selector_binding"].update(rows_sha256="0" * 64),
            "the merge reports binding_violated_entries",
        ),
        (lambda entry: entry.pop("selector_binding"), "selector_binding is not its rows' binding"),
        (lambda entry: entry["evidence"].pop("mechanism"), "evidence needs a non-empty `mechanism`"),
    ],
)
def test_audit_follows_what_the_production_merge_does(repo_copy, edit, expected):
    entry_id = _edit_first_disposition(repo_copy, edit)
    problems = builder.check(repo_copy)
    assert any(expected in problem for problem in problems), (entry_id, problems)


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


@pytest.mark.parametrize(
    "edit",
    [
        lambda data: data.pop("run"),
        lambda data: data.update(rows=[]),
        lambda data: next(iter(data["rows"].values())).pop("axiom"),
    ],
)
def test_audit_reports_a_malformed_evidence_file_instead_of_raising(repo_copy, edit):
    _edit_json(repo_copy / builder.EVIDENCE, edit)
    problems = builder.check(repo_copy)
    assert problems and all(isinstance(problem, str) for problem in problems)


def test_audit_reports_a_malformed_binding_instead_of_raising(repo_copy):
    _edit_first_disposition(
        repo_copy, lambda entry: entry.update(selector_binding="not-a-binding")
    )
    problems = builder.check(repo_copy)
    assert problems and all(isinstance(problem, str) for problem in problems)


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


# --- fail closed on incomplete downstream evidence ------------------------


@pytest.fixture
def build_payloads():
    """Reconstruct the stage fields used by the builder from its committed run."""
    evidence = json.loads((ROOT / builder.EVIDENCE).read_text())
    _, full = builder.bound_full_report(ROOT)
    rows = evidence["rows"]
    stages = {
        stage: {
            "attribution": {
                key: {"mechanism": record[stage]}
                for key, record in rows.items()
                if stage in record
            }
        }
        for stage in ("stage1", "stage2", "stage3")
    }
    stages["stage1"].update(
        baseline_reproduces_full_run=True,
        baseline_value_drift=[],
        explain_sample_tax_units=1500,
        explain_sample_matches_full_run=True,
    )
    stages["stage2"].update(
        decomposition=evidence["age_units"] | evidence["investment_units"],
        explained_units={
            "age": list(evidence["age_units"]),
            "age+investment": [],
            "investment": list(evidence["investment_units"]),
        },
        base_reproduces_stage1_all_mechanisms=True,
        variants={"se_loss+seca": {"rows": {}}},
    )
    stages["stage3"].update(
        switch_model_exact=True,
        bridge_aggregate_variant_leaves_stage1_investment_rows=True,
        policyengine_aggregate_variant_clears_all=True,
    )
    return {"full": full, "evidence": evidence, **stages}


def _build(payloads):
    return builder.build_evidence(
        payloads["full"],
        payloads["stage1"],
        payloads["stage2"],
        payloads["stage3"],
        raw_report=payloads["evidence"]["run"]["report"],
        raw_sha256=payloads["evidence"]["run"]["report_sha256"],
    )


def _downstream_key(rows, stage1):
    # The old audit already caught a dividend row defaulting to PE investment.
    # Exercise the PE investment rows that its permissive fallback accepted.
    return next(
        key for key, record in rows.items()
        if record.get("stage1") == stage1
        and (stage1 != "investment" or record["entry"] == "pe_investment")
    )


def test_valid_stage_payloads_rebuild_committed_artifacts_byte_for_byte(build_payloads):
    evidence, assignment = _build(build_payloads)
    assert json.dumps(evidence, indent=1, sort_keys=True) + "\n" == (
        ROOT / builder.EVIDENCE
    ).read_text()
    # The build intentionally precedes stamping. Remove only the existing
    # binding stanzas, leaving all other bytes (including comments) intact.
    unbound = re.sub(
        r"^  selector_binding:\n(?:    .*\n)*",
        "",
        (ROOT / builder.DISPOSITIONS).read_text(),
        flags=re.M,
    )
    assert builder.build_dispositions(evidence, assignment) == unbound


def test_builder_and_audit_refuse_the_reviewers_corrupted_labels(build_payloads, repo_copy):
    rows = build_payloads["evidence"]["rows"]
    se = _downstream_key(rows, "residual")
    investment = _downstream_key(rows, "investment")
    build_payloads["stage2"]["attribution"][se]["mechanism"] = "residual"
    build_payloads["stage3"]["attribution"][investment]["mechanism"] = "residual"
    build_payloads["stage2"]["variants"]["se_loss+seca"]["rows"][se] = {}
    build_payloads["stage3"]["policyengine_aggregate_variant_clears_all"] = False

    with pytest.raises(ValueError):
        _build(build_payloads)

    evidence = build_payloads["evidence"]
    evidence["rows"][se]["stage2"] = "residual"
    evidence["rows"][investment]["stage3"] = "residual"
    evidence["checks"]["stage2_all_mechanisms_rows_left"] = 1
    evidence["checks"]["stage3_policyengine_aggregate_clears_all"] = False
    (repo_copy / builder.EVIDENCE).write_text(json.dumps(evidence))
    assert builder.check(repo_copy)
    with pytest.raises(ValueError):
        builder.build_dispositions(
            evidence, {key: record["entry"] for key, record in evidence["rows"].items()}
        )


@pytest.mark.parametrize("stage1,stage", [("residual", "stage2"), ("investment", "stage3")])
@pytest.mark.parametrize(
    "label", ["residual", None, "", "unknown", "ambiguous:", "ambiguous:div_aggregate|unknown"]
)
def test_builder_refuses_uncleared_or_unsupported_downstream_labels(
    build_payloads, stage1, stage, label
):
    key = _downstream_key(build_payloads["evidence"]["rows"], stage1)
    build_payloads[stage]["attribution"][key]["mechanism"] = label
    with pytest.raises(ValueError):
        _build(build_payloads)


@pytest.mark.parametrize("stage1,stage", [("residual", "stage2"), ("investment", "stage3")])
@pytest.mark.parametrize("label", ["residual", None, "", "unknown"])
def test_audit_refuses_uncleared_or_unsupported_downstream_labels(
    repo_copy, stage1, stage, label
):
    evidence = json.loads((repo_copy / builder.EVIDENCE).read_text())
    key = _downstream_key(evidence["rows"], stage1)
    evidence["rows"][key][stage] = label
    (repo_copy / builder.EVIDENCE).write_text(json.dumps(evidence))
    assert any(key in problem for problem in builder.check(repo_copy))
    with pytest.raises(ValueError):
        builder.build_dispositions(
            evidence, {key: record["entry"] for key, record in evidence["rows"].items()}
        )


@pytest.mark.parametrize("stage1", ["investment", "age+investment"])
def test_builder_and_audit_refuse_a_missing_stage3_label(build_payloads, repo_copy, stage1):
    key = _downstream_key(build_payloads["evidence"]["rows"], stage1)
    build_payloads["stage3"]["attribution"].pop(key)
    with pytest.raises(ValueError):
        _build(build_payloads)

    def remove_label(evidence):
        evidence["rows"][key].pop("stage3")

    _edit_json(repo_copy / builder.EVIDENCE, remove_label)
    assert any(key in problem for problem in builder.check(repo_copy))


@pytest.mark.parametrize(
    "stage,field,value",
    [
        ("stage1", "baseline_reproduces_full_run", False),
        ("stage1", "baseline_value_drift", ["tax_unit_1|eitc"]),
        ("stage1", "explain_sample_matches_full_run", False),
        ("stage2", "base_reproduces_stage1_all_mechanisms", False),
        ("stage3", "switch_model_exact", False),
        ("stage3", "bridge_aggregate_variant_leaves_stage1_investment_rows", False),
        ("stage3", "policyengine_aggregate_variant_clears_all", False),
    ],
)
def test_builder_refuses_failed_recorded_baseline_or_model_checks(
    build_payloads, stage, field, value
):
    build_payloads[stage][field] = value
    with pytest.raises(ValueError):
        _build(build_payloads)


@pytest.mark.parametrize(
    "field,value",
    [
        ("stage1_baseline_reproduces_full_run", False),
        ("stage1_baseline_value_drift_rows", 1),
        ("explain_mode_sample_matches_fast_full_run", False),
        ("stage2_base_reproduces_stage1", False),
        ("stage2_all_mechanisms_rows_left", 1),
        ("stage3_switch_model_reproduces_both_aggregates", False),
        ("stage3_policyengine_aggregate_clears_all", False),
        ("bridge_aggregate_variant_leaves_stage1_investment_rows", False),
    ],
)
def test_audit_and_disposition_builder_refuse_failed_recorded_checks(repo_copy, field, value):
    evidence = json.loads((repo_copy / builder.EVIDENCE).read_text())
    evidence["checks"][field] = value
    (repo_copy / builder.EVIDENCE).write_text(json.dumps(evidence))
    assert any(field in problem for problem in builder.check(repo_copy))
    with pytest.raises(ValueError):
        builder.build_dispositions(
            evidence, {key: record["entry"] for key, record in evidence["rows"].items()}
        )


def test_builder_checks_original_rows_clear_but_allows_counterfactual_only_extras(build_payloads):
    final_rows = build_payloads["stage2"]["variants"]["se_loss+seca"]["rows"]
    extra = "tax_unit_999999999|eitc_earned_income"
    assert extra not in build_payloads["evidence"]["rows"]
    final_rows[extra] = {"axiom": 10.0, "policyengine": 0.0, "diff": 10.0}
    build_payloads["stage3"]["base_counterfactual_only_rows"] = [extra]
    evidence, assignment = _build(build_payloads)
    assert evidence["checks"]["stage2_all_mechanisms_rows_left"] == 0
    assert extra not in evidence["rows"] and extra not in assignment
    builder.build_dispositions(evidence, assignment)

    original = _downstream_key(evidence["rows"], "residual")
    final_rows[original] = final_rows[extra]
    with pytest.raises(ValueError):
        _build(build_payloads)


@pytest.mark.parametrize(
    "stage1,stage2_label,stage3_label,entry",
    [
        ("residual", "se_loss", None, "se_projection"),
        ("residual", "seca", None, "se_projection"),
        ("residual", "se_loss+seca", None, "se_projection"),
        ("residual", "ambiguous:se_loss|seca", None, "se_projection"),
        ("investment", None, "div_aggregate", "dividend_aggregate"),
        ("investment", None, "ambiguous:cg_distributions|div_aggregate", "pe_investment"),
        (
            "investment",
            None,
            "ambiguous:cg_distributions+farm_rent|div_aggregate+cg_distributions",
            "pe_investment",
        ),
        ("age+investment", None, "ambiguous:div_aggregate|farm_rent", "age"),
    ],
)
def test_supported_clearing_attributions_include_ambiguous_labels(
    stage1, stage2_label, stage3_label, entry
):
    row = {"case_id": "ecps-tax_unit_1", "output": "eitc", "concept": builder.EITC}
    assert builder.entry_of(row, stage1, stage3_label, stage2=stage2_label) == entry


def test_builder_refuses_honestly_unresolved_output_of_real_stage2_main(
    tmp_path, monkeypatch, build_payloads
):
    stage2_main = _load(
        "counterfactuals_stage2_unresolved_test", ATTRIBUTION / "counterfactuals_stage2.py"
    )
    key = "tax_unit_1|eitc_earned_income"
    values = {"axiom": 10.0, "policyengine": 0.0, "diff": 10.0}
    stage1_payload = {
        **build_payloads["stage1"],
        "attribution": {key: {"mechanism": "residual"}},
        "variants": {"age+partnership+investment": {"rows": {key: values}}},
    }
    stage1_path, output_path = tmp_path / "stage1.json", tmp_path / "stage2.json"
    stage1_path.write_text(json.dumps(stage1_payload))
    monkeypatch.setattr(stage2_main, "load_with_decomposition", lambda ids: ({}, {}))
    monkeypatch.setattr(stage2_main.cf, "subset_pe_data", lambda data, ids: data)
    monkeypatch.setattr(stage2_main, "decompose", lambda *args: {})
    monkeypatch.setattr(stage2_main, "version", lambda name: "fixture")
    # Every real stage-2 variant keeps the original mismatch. Its baseline is
    # faithful, so stage 2 legitimately exits zero and records an unresolved row.
    monkeypatch.setattr(
        stage2_main,
        "run",
        lambda *args, **kwargs: ({("tax_unit_1", "eitc_earned_income"): values}, 1),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stage2", "--stage1", str(stage1_path),
            "--rulespec-root", str(tmp_path / "rulespec"),
            "--engine", str(tmp_path / "engine"), "--out", str(output_path),
        ],
    )
    assert stage2_main.main() == 0
    unresolved = json.loads(output_path.read_text())
    assert unresolved["base_reproduces_stage1_all_mechanisms"] is True
    assert unresolved["attribution"][key]["mechanism"] == "residual"
    assert key in unresolved["variants"]["se_loss+seca"]["rows"]

    build_payloads["stage1"] = stage1_payload
    build_payloads["stage2"] = unresolved
    build_payloads["stage3"]["attribution"] = {}
    build_payloads["full"] = {
        "mismatches": [{
            "case_id": "ecps-tax_unit_1",
            "output": "eitc_earned_income",
            "concept": builder.EITC,
            "left": 10.0,
            "right": 0.0,
            "difference": 10.0,
        }],
        "summary": {"mismatch_count": 1},
        "provenance": build_payloads["full"]["provenance"],
    }
    with pytest.raises(ValueError):
        _build(build_payloads)


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
