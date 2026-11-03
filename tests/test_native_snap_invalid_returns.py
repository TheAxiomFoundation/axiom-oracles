"""Only finite returned SNAP values enter comparison counts or matches (#604).

The native SNAP producer used to pass every PolicyEngine return through
``native()``, which turned NaN and infinities into zero, and the CSV adapter
read a blank or unparseable cell as 0 or False. An invalid return then
arrived as a match with error-free execution evidence. These tests follow
the native FIIT fix in #368: invalid returns stay visible as diagnostic
mismatches with an engine error, never as a comparison or a match.
"""

from __future__ import annotations

import ast
import csv
import importlib.util
import io
import json
import math
import subprocess
import shutil
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pytest
from hypothesis import example, given, settings, strategies as st

from axiom_oracles.bridges import snap_populace
from axiom_oracles.bridges.snap_populace import (
    COMPARED_AXIOM_OUTPUT,
    JURISDICTION_CONFIGS,
    PE_COMPARED_OUTPUT,
    ProjectedCase,
)
from axiom_oracles.conformance.attestation import attest

ROOT = Path(__file__).parents[1]
CONFIG = JURISDICTION_CONFIGS["us-co"]
INVALID = [
    pytest.param(None, id="missing"),
    pytest.param(math.nan, id="nan"),
    pytest.param(math.inf, id="infinity"),
    pytest.param(-math.inf, id="negative-infinity"),
]
AMOUNT = "us:statutes/7/2014/u#snap_benefit"
ELIGIBILITY = "us:statutes/7/2014/o#snap_eligible"


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@lru_cache
def runner():
    return _load("snap_604_runner", "scripts/run_comparison.py")


@lru_cache
def merger():
    return _load("snap_604_merge", "scripts/merge_shard_reports.py")


def pe_outputs(amount=100.0, eligible=True) -> dict:
    return {
        PE_COMPARED_OUTPUT: amount,
        "is_snap_eligible": eligible,
        "snap_gross_income": 0,
        "snap_net_income": 0,
        "snap_excess_shelter_expense_deduction": 0,
        "snap_standard_deduction": 0,
        "snap_earned_income_deduction": 0,
        "snap_dependent_care_deduction": 0,
        "snap_child_support_deduction": 0,
        "snap_child_support_gross_income_deduction": 0,
        "snap_excess_medical_expense_deduction": 0,
        "snap_max_allotment": 100,
        "snap_utility_allowance": 0,
        "housing_cost": 0,
        "has_usda_elderly_disabled": False,
        "meets_snap_categorical_eligibility": False,
        "snap_utility_allowance_type": "",
    }


def axiom_outputs(amount=100.0, eligible="holds") -> dict:
    outputs = {}
    for label, output_id in CONFIG.output_id_by_label.items():
        if label == "snap_eligible":
            outputs[output_id] = {"kind": "judgment", "outcome": eligible}
        elif label == COMPARED_AXIOM_OUTPUT:
            outputs[output_id] = {"value": {"kind": "decimal", "value": amount}}
        else:
            outputs[output_id] = {"value": {"kind": "decimal", "value": 0}}
    return {"outputs": outputs}


def produce(pairs):
    """Run the native producer on (pe_amount, pe_eligible, ax_amount, ax_eligible)."""
    cases, results = [], []
    for index, (pe_amount, pe_eligible, ax_amount, ax_eligible) in enumerate(pairs):
        cases.append(
            ProjectedCase(
                spm_unit_id=index + 1,
                household_id=index + 1,
                inputs={},
                member_inputs=[],
                pe_outputs=pe_outputs(pe_amount, pe_eligible),
            )
        )
        results.append(axiom_outputs(ax_amount, ax_eligible))
    return snap_populace.compare(cases, results, 1.5, config=CONFIG)


def through_csv(rows) -> list[dict]:
    """Serialize with the producer's CSV writer and read back as the runner does."""
    buffer = io.StringIO()
    snap_populace.write_csv_handle(buffer, rows)
    buffer.seek(0)
    return list(csv.DictReader(buffer))


def publish(rows) -> dict:
    report = runner()._adapt_snap_ecps_csv_to_v2(
        through_csv(rows), {"parameters": {"jurisdiction": "us-co"}}
    )
    # The published report must be portable through strict JSON.
    return json.loads(json.dumps(report, allow_nan=False))


def aggregate(report, concept):
    return next(row for row in report["aggregates"] if row["concept"] == concept)


# ── producer ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("invalid", INVALID)
@pytest.mark.parametrize("side", ["policyengine", "axiom"])
def test_producer_keeps_invalid_amount_and_records_engine_error(invalid, side):
    row = produce(
        [
            (
                invalid if side == "policyengine" else 100.0,
                True,
                invalid if side == "axiom" else 100.0,
                "holds",
            )
        ]
    )[0]
    assert row["amount_compared"] is False
    assert row["amount_match"] is False and row["match"] is False
    assert row["difference"] is None and row["absolute_difference"] is None
    assert row["errors"] == [
        {
            "engine": side,
            "output": "pe_snap" if side == "policyengine" else "axiom_snap_allotment",
            "error": "missing_or_nonfinite_output",
        }
    ]
    returned = row["pe_snap" if side == "policyengine" else "axiom_snap_allotment"]
    if invalid is None:
        assert returned is None
    else:
        assert returned is invalid or (math.isnan(returned) and math.isnan(invalid))
    assert row["eligibility_compared"] is True


@pytest.mark.parametrize("invalid", [None, math.nan, "maybe"])
@pytest.mark.parametrize("side", ["policyengine", "axiom"])
def test_producer_keeps_invalid_eligibility_out_of_comparison(invalid, side):
    row = produce(
        [
            (
                100.0,
                invalid if side == "policyengine" else True,
                100.0,
                invalid if side == "axiom" else "holds",
            )
        ]
    )[0]
    assert row["eligibility_compared"] is False
    assert row["amount_compared"] is True and row["amount_match"] is True
    assert [error["engine"] for error in row["errors"]] == [side]


@pytest.mark.parametrize(
    "pe_eligible,ax_eligible", [(False, "not_holds"), (True, "holds")]
)
def test_producer_controls_keep_genuine_zero_and_false(pe_eligible, ax_eligible):
    row = produce([(0.0, pe_eligible, 0, ax_eligible)])[0]
    assert row["amount_compared"] is row["eligibility_compared"] is True
    assert row["match"] is True and row["errors"] == []
    assert row["pe_snap"] == row["axiom_snap_allotment"] == 0


def test_producer_summary_prints_with_invalid_rows(capsys):
    rows = produce([(None, True, 100.0, "holds"), (90.0, True, 100.0, "holds")])
    snap_populace.print_summary(rows, 1.5, 5)
    out = capsys.readouterr().out
    assert "Uncompared rows (invalid returns): 1" in out
    assert "Max absolute difference: $10.00" in out


# ── adapter, serialization, attestation ───────────────────────────────────
def assert_one_failed_amount_pair(report, *, engine):
    summary = report["summary"]
    # Two SNAP units: one clean pair per concept, one failed amount pair.
    assert summary["comparison_count"] == 3
    assert summary["match_count"] == 3
    assert summary["mismatch_count"] == summary["uncompared_mismatches"] == 1
    assert summary["weighted"]["mismatch_weight"] == 0
    assert summary["error_count"] == 1
    assert summary["errors_by_engine"] == {engine: 1}
    output = "pe_snap" if engine == "policyengine" else "axiom_snap_allotment"
    assert report["errors"] == [
        {
            "engine": engine,
            "case_id": "ecps-spm-2",
            "concept": AMOUNT,
            "output": output,
            "error": "missing_or_nonfinite_output",
        }
    ]
    amount = aggregate(report, AMOUNT)
    assert amount["comparison_count"] == amount["match_count"] == 1
    assert amount["mismatch_count"] == amount["uncompared_mismatches"] == 1
    assert amount["mismatch_weight"] == 0
    [mismatch] = report["mismatches"]
    assert mismatch["uncompared"] is True and mismatch["difference"] is None
    case = next(case for case in report["cases"] if case["case_id"] == "ecps-spm-2")
    side = "right_errors" if engine == "policyengine" else "left_errors"
    assert case[side] == report["errors"]
    evidence = attest(report, oracle="policyengine")
    assert any("engine error" in problem for problem in evidence.problems)
    assert not evidence.eligible


@pytest.mark.parametrize("invalid", INVALID)
@pytest.mark.parametrize("side", ["policyengine", "axiom"])
def test_invalid_amount_is_not_a_match_after_csv_and_adapter(invalid, side):
    rows = produce(
        [
            (100.0, True, 100.0, "holds"),
            (
                invalid if side == "policyengine" else 0.0,
                True,
                invalid if side == "axiom" else 0.0,
                "holds",
            ),
        ]
    )
    assert_one_failed_amount_pair(publish(rows), engine=side)


@pytest.mark.parametrize("cell", ["", "nan", "NaN", "inf", "-inf", "None", "n/a"])
@pytest.mark.parametrize("column", ["pe_snap", "axiom_snap_allotment"])
def test_adapter_rejects_invalid_cells_from_any_producer(cell, column):
    # The axiom-encode producer writes the same CSV without the new ledger
    # columns, so the adapter must detect invalid cells by itself.
    rows = through_csv(
        produce([(100.0, True, 100.0, "holds"), (0.0, True, 0.0, "holds")])
    )
    for row in rows:
        for key in ("errors", "amount_compared", "eligibility_compared"):
            row.pop(key)
    rows[1][column] = cell
    rows[1]["match"] = "True"
    report = runner()._adapt_snap_ecps_csv_to_v2(
        rows, {"parameters": {"jurisdiction": "us-co"}}
    )
    report = json.loads(json.dumps(report, allow_nan=False))
    engine = "policyengine" if column == "pe_snap" else "axiom"
    assert_one_failed_amount_pair(report, engine=engine)


@pytest.mark.parametrize("cell", ["", "None", "nan", "maybe"])
@pytest.mark.parametrize("column", ["pe_snap_eligible", "axiom_snap_eligible"])
def test_adapter_never_reads_a_missing_verdict_as_false(cell, column):
    rows = through_csv(
        produce([(100.0, False, 100.0, "not_holds"), (0.0, False, 0.0, "not_holds")])
    )
    rows[1][column] = cell
    report = runner()._adapt_snap_ecps_csv_to_v2(
        rows, {"parameters": {"jurisdiction": "us-co"}}
    )
    eligibility = aggregate(report, ELIGIBILITY)
    assert eligibility["comparison_count"] == eligibility["match_count"] == 1
    assert eligibility["uncompared_mismatches"] == 1
    assert report["summary"]["error_count"] == 1
    assert not attest(report, oracle="policyengine").eligible


def test_adapter_controls_keep_genuine_zero_and_false_matches():
    rows = produce([(0.0, False, 0.0, "not_holds"), (0.0, True, 0.0, "holds")])
    report = publish(rows)
    summary = report["summary"]
    assert summary["comparison_count"] == summary["match_count"] == 4
    assert summary["mismatch_count"] == summary["error_count"] == 0
    assert summary["uncompared_mismatches"] == 0
    assert report["errors"] == []
    assert attest(report, oracle="policyengine").error_count == 0


def test_finite_disagreement_keeps_its_comparison_and_weight():
    report = publish(produce([(100.0, True, 50.0, "holds")]))
    amount = aggregate(report, AMOUNT)
    assert amount["comparison_count"] == amount["mismatch_count"] == 1
    assert amount["mismatch_weight"] == 1 and amount["uncompared_mismatches"] == 0
    assert report["summary"]["error_count"] == 0


def test_shard_merge_carries_the_error_ledger():
    rows = produce([(100.0, True, 100.0, "holds"), (None, True, 0.0, "holds")])
    report = publish(rows)
    merged = merger().merge([deepcopy(report), deepcopy(report)])
    summary = merged["summary"]
    assert summary["comparison_count"] == summary["match_count"] == 6
    assert summary["mismatch_count"] == summary["uncompared_mismatches"] == 2
    assert summary["error_count"] == len(merged["errors"]) == 2
    assert summary["errors_by_engine"] == {"policyengine": 2}
    amount = aggregate(merged, AMOUNT)
    assert amount["uncompared_mismatches"] == amount["mismatch_count"] == 2
    assert amount["mismatch_weight"] == 0
    assert not attest(merged, oracle="policyengine").eligible


_values = st.one_of(
    st.none(),
    st.sampled_from([math.nan, math.inf, -math.inf]),
    st.floats(min_value=-1e6, max_value=1e6, allow_nan=False),
)
_verdicts = st.sampled_from([True, False, None, math.nan])


@settings(max_examples=60, deadline=None, database=None, derandomize=True)
@example(pairs=[(None, True, 0.0, True)])
@example(pairs=[(0.0, False, 0.0, False)])
@given(
    pairs=st.lists(
        st.tuples(_values, _verdicts, _values, _verdicts), min_size=1, max_size=6
    )
)
def test_only_valid_pairs_enter_snap_denominators(pairs):
    rows = produce(
        [
            (
                pe,
                pe_el,
                ax,
                {True: "holds", False: "not_holds"}.get(ax_el, ax_el)
                if not isinstance(ax_el, float)
                else ax_el,
            )
            for pe, pe_el, ax, ax_el in pairs
        ]
    )
    report = publish(rows)

    def finite(value):
        return isinstance(value, float) and math.isfinite(value)

    valid_amount = [(pe, ax) for pe, _, ax, _ in pairs if finite(pe) and finite(ax)]
    valid_elig = [
        (p, a) for _, p, _, a in pairs if isinstance(p, bool) and isinstance(a, bool)
    ]
    invalid_pairs = (len(pairs) - len(valid_amount)) + (len(pairs) - len(valid_elig))
    amount_matches = sum(abs(ax - pe) <= 1.5 for pe, ax in valid_amount)
    elig_matches = sum(p == a for p, a in valid_elig)
    summary = report["summary"]
    assert summary["comparison_count"] == len(valid_amount) + len(valid_elig)
    assert summary["match_count"] == amount_matches + elig_matches
    assert summary["uncompared_mismatches"] == invalid_pairs
    assert summary["weighted"]["mismatch_weight"] == (
        summary["comparison_count"] - summary["match_count"]
    )
    assert attest(report, oracle="policyengine").error_count >= invalid_pairs
    if invalid_pairs:
        assert not attest(report, oracle="policyengine").eligible


# ── loader: invalid support values never become zero inputs ─────────────────
def load_stub(
    monkeypatch,
    variable,
    value,
    *,
    config=CONFIG,
    positive_snap_only=False,
    utility_projection="raw",
    overrides=None,
):
    np = pytest.importorskip("numpy")
    state = config.jurisdiction.rsplit("-", 1)[-1].upper()
    arrays = {
        "spm_unit_id": [1],
        "person_spm_unit_id": [1],
        "person_household_id": [1],
        "household_id": [1],
        "state_code_str": [state],
        "snap_unit_size": [1],
        "spm_unit_size": [1],
        PE_COMPARED_OUTPUT: [10.0],
        "snap_utility_allowance_type": ["SUA"],
        "snap_utility_region_str": [""],
        **(overrides or {}),
    }

    def calculate(name, period=None):
        if name == variable:
            return np.array([value], dtype=object)
        return np.array(arrays.get(name, [0.0]))

    sim = SimpleNamespace(calculate=calculate)
    monkeypatch.setitem(
        __import__("sys").modules,
        "policyengine_us",
        SimpleNamespace(Microsimulation=lambda **_kwargs: sim),
    )
    monkeypatch.setattr(
        snap_populace, "load_populace_dataset", lambda *_a, **_k: object()
    )
    monkeypatch.setattr(snap_populace, "legalize_inputs", lambda inputs, _index: inputs)
    return snap_populace.load_policyengine_cases(
        config=config,
        base_inputs={},
        period=snap_populace.month_period(2026, 1),
        state=state,
        sample_size=None,
        positive_snap_only=positive_snap_only,
        utility_projection=utility_projection,
        populace_year=2024,
    )


@pytest.mark.parametrize("invalid", INVALID)
@pytest.mark.parametrize(
    "variable", sorted(snap_populace.POLICYENGINE_INPUT_SUPPORT_VARIABLES)
)
def test_loader_rejects_invalid_support_values_before_projection(
    monkeypatch, invalid, variable
):
    with pytest.raises(
        ValueError, match=f"spm_unit_1 {variable}: missing or nonfinite"
    ):
        load_stub(monkeypatch, variable, invalid)


@pytest.mark.parametrize("invalid", INVALID)
def test_loader_preserves_invalid_compared_return(monkeypatch, invalid):
    [case] = load_stub(monkeypatch, "is_snap_eligible", invalid)
    returned = case.pe_outputs["is_snap_eligible"]
    assert (
        returned is None
        if invalid is None
        else (returned == invalid or (math.isnan(returned) and math.isnan(invalid)))
    )


@pytest.mark.parametrize("value", [0, 0.0, False])
def test_loader_keeps_finite_zero_and_false(monkeypatch, value):
    [case] = load_stub(monkeypatch, "snap_assets", value)
    assert case.pe_outputs["snap_assets"] == value


# Functions whose ``values`` is not the PolicyEngine mapping: a numpy array,
# or (_diagnostic_sum) its own varargs of diagnostic amounts.
_NOT_THE_POLICYENGINE_MAPPING = frozenset(
    {"array", "any_by_id", "all_by_id", "build_household_value_map", "_diagnostic_sum"}
)
# The two reviewed statements that read the mapping with keys the scan cannot
# resolve, as (function, exact statement source). Any other statement that
# reads it that way fails the guard until someone reviews it.
_REVIEWED_DYNAMIC_STATEMENTS = frozenset(
    {
        # The support loop reads exactly the names it validates.
        (
            "load_policyengine_cases",
            "for name in support_names:\n"
            "    require_support_value(values[name][idx], name, spm_id)",
        ),
        # pe_outputs copies every returned value for compare(); not inputs.
        (
            "load_policyengine_cases",
            "pe_outputs = {name: returned_value(values[name][idx]) for name in values}",
        ),
    }
)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _string_items(node: ast.AST) -> set[str] | None:
    if isinstance(node, ast.Tuple | ast.List | ast.Set) and all(
        isinstance(item, ast.Constant) and isinstance(item.value, str)
        for item in node.elts
    ):
        return {item.value for item in node.elts}
    return None


def _support_reads(source: str) -> tuple[set[str], list[str]]:
    """Every key read from the PolicyEngine ``values`` mapping, by AST.

    An allowlist: every load of the name ``values`` (outside the functions
    where it names a numpy array) is accepted only when it is
    - subscripted with a key that resolves to a literal, or to a loop
      variable over a literal tuple, list or set;
    - the receiver of ``.get`` with such a key;
    - passed to a function in this module whose matching parameter is named
      ``values``, or the sole argument of ``set()``;
    - read inside one of the two reviewed statements, keyed to their exact
      source.

    Every other use (an unresolved key, any other method or attribute, an
    alias, unpacking, an operator, a conditional, a container, a call to
    anything else) is reported as a problem.
    """
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    reads: set[str] = set()
    problems: list[str] = []

    for name, function in functions.items():
        if name in _NOT_THE_POLICYENGINE_MAPPING:
            continue
        parents: dict[ast.AST, ast.AST] = {}
        for node in ast.walk(function):
            for child in ast.iter_child_nodes(node):
                parents[child] = node

        def ancestors(node: ast.AST):
            while node in parents:
                node = parents[node]
                yield node

        def reviewed(node: ast.AST) -> bool:
            return any(
                isinstance(ancestor, ast.stmt)
                and (name, ast.unparse(ancestor)) in _REVIEWED_DYNAMIC_STATEMENTS
                for ancestor in ancestors(node)
            )

        def resolve(key: ast.AST, at: ast.AST) -> set[str] | None:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                return {key.value}
            if not isinstance(key, ast.Name):
                return None
            for node in ancestors(at):
                if isinstance(node, ast.For):
                    loops = [node]
                elif isinstance(node, _COMPREHENSIONS):
                    loops = node.generators
                else:
                    continue
                for loop in loops:
                    if isinstance(loop.target, ast.Name) and loop.target.id == key.id:
                        return _string_items(loop.iter)
            return None

        def accept_read(keys: set[str] | None, node: ast.AST, where: str) -> None:
            if keys is not None:
                reads.update(keys)
            elif not reviewed(node):
                problems.append(f"{where} unresolved read {ast.unparse(node)}")

        for node in ast.walk(function):
            if not (
                isinstance(node, ast.Name)
                and node.id == "values"
                and isinstance(node.ctx, ast.Load)
            ):
                continue
            parent = parents.get(node)
            where = f"{name}:{node.lineno}"
            if isinstance(parent, ast.Subscript) and parent.value is node:
                accept_read(resolve(parent.slice, parent), parent, where)
            elif isinstance(parent, ast.Attribute) and parent.value is node:
                call = parents.get(parent)
                if (
                    parent.attr == "get"
                    and isinstance(call, ast.Call)
                    and call.func is parent
                    and call.args
                ):
                    accept_read(resolve(call.args[0], call), call, where)
                else:
                    problems.append(f"{where} unreviewed use values.{parent.attr}")
            elif isinstance(parent, ast.Call) and node in parent.args:
                callee = parent.func.id if isinstance(parent.func, ast.Name) else None
                position = parent.args.index(node)
                target = functions.get(callee)
                params = [a.arg for a in target.args.args] if target else []
                if callee == "set" and parent.args == [node] and not parent.keywords:
                    continue
                if position < len(params) and params[position] == "values":
                    continue
                problems.append(f"{where} values handed to {ast.unparse(parent.func)}")
            elif isinstance(parent, ast.keyword) and parent.value is node:
                call = parents.get(parent)
                callee = call.func.id if isinstance(call.func, ast.Name) else None
                target = functions.get(callee)
                params = [a.arg for a in target.args.args] if target else []
                if parent.arg == "values" and "values" in params:
                    continue
                problems.append(f"{where} values handed to {ast.unparse(call.func)}")
            elif isinstance(parent, ast.comprehension) and parent.iter is node:
                if not reviewed(parent):
                    problems.append(f"{where} unreviewed loop over values")
            else:
                problems.append(f"{where} unreviewed use {ast.unparse(parent)}")
    return reads, problems


def _bridge_source() -> str:
    return (ROOT / "axiom_oracles/bridges/snap_populace.py").read_text()


_EXEMPT_READS = {"snap_utility_allowance_type", "is_snap_eligible"}


def test_every_support_variable_read_for_inputs_is_validated():
    # Guard drift: every PolicyEngine value the projections read is validated
    # support, except is_snap_eligible (support only under the eligibility
    # bridge, tested below) and the enum snap_utility_allowance_type (refused
    # when unrecognized, tested below). The scan is an allowlist.
    reads, problems = _support_reads(_bridge_source())
    assert problems == []
    assert {"water_expense", "is_snap_eligible", "snap_assets"} <= reads
    unlisted = (
        reads - _EXEMPT_READS - snap_populace.POLICYENGINE_INPUT_SUPPORT_VARIABLES
    )
    assert not unlisted, unlisted


_US_CA_ANCHOR = (
    '    if config.jurisdiction == "us-ca":\n'
    "        return {\n"
    '            "snap_gross_monthly_earned_income"'
)
_LOADER_ANCHOR = "    household_input_ref_by_name = legal_input_index(base_inputs)\n"
_NEW = '"snap_new_unlisted_input"'
# Each shape routes an unlisted PolicyEngine variable (or every variable)
# toward an input; the guard must reject each, as an unlisted read or as a
# use it cannot vouch for.
_UNLISTED_READS = {
    "literal": (_US_CA_ANCHOR, f"    _x = values[{_NEW}][idx]\n"),
    "get-literal": (_US_CA_ANCHOR, f"    _x = values.get({_NEW})\n"),
    "get-unresolved": (_US_CA_ANCHOR, f"    _k = {_NEW}\n    _x = values.get(_k)\n"),
    "name-key": (_US_CA_ANCHOR, f"    _k = {_NEW}\n    _x = values[_k][idx]\n"),
    "list-loop": (
        _US_CA_ANCHOR,
        f"    for _name in [{_NEW}]:\n        _x = values[_name][idx]\n",
    ),
    "items": (
        _US_CA_ANCHOR,
        "    for _k, _v in values.items():\n        _x = _v[idx]\n",
    ),
    "keys": (_US_CA_ANCHOR, "    _x = [values[k] for k in values.keys()]\n"),
    "walrus-alias": (_US_CA_ANCHOR, f"    _x = (pe := values)[{_NEW}][idx]\n"),
    "module-constant": (_US_CA_ANCHOR, "    _x = values[PE_COMPARED_OUTPUT][idx]\n"),
    "dict-unpack": (_US_CA_ANCHOR, f"    _m = {{**values}}\n    _x = _m[{_NEW}]\n"),
    "tuple-alias": (_US_CA_ANCHOR, f"    _m, _n = values, None\n    _x = _m[{_NEW}]\n"),
    "conditional": (
        _US_CA_ANCHOR,
        f"    _x = (values if idx else values)[{_NEW}][idx]\n",
    ),
    "operator": (_US_CA_ANCHOR, f"    _x = (values | {{}})[{_NEW}][idx]\n"),
    "starred": (_US_CA_ANCHOR, "    _x = list(*[values])\n"),
    "len": (_US_CA_ANCHOR, "    _x = len(values)\n"),
    # Iterating the keys alone reads nothing, but no reviewed statement
    # vouches for the loop, so it fails closed too.
    "key-loop": (_US_CA_ANCHOR, "    _x = [name for name in values]\n"),
    "unreviewed-loop-in-loader": (
        _LOADER_ANCHOR,
        "    _all = {name: money(values[name][idx]) for name in values}\n",
    ),
}


def _guard_rejects(source: str) -> bool:
    reads, problems = _support_reads(source)
    unlisted = (
        reads - _EXEMPT_READS - snap_populace.POLICYENGINE_INPUT_SUPPORT_VARIABLES
    )
    return bool(problems or unlisted)


@pytest.mark.parametrize("shape", sorted(_UNLISTED_READS))
def test_drift_guard_catches_every_read_shape(shape):
    source = _bridge_source()
    anchor, injected = _UNLISTED_READS[shape]
    assert source.count(anchor) == 1
    assert not _guard_rejects(source)
    assert _guard_rejects(source.replace(anchor, injected + anchor)), shape


def test_drift_guard_exemptions_are_keyed_to_their_exact_statements():
    # Editing either reviewed statement (here: projecting every value
    # through money() instead of copying it) voids its exemption.
    source = _bridge_source()
    old = "pe_outputs = {name: returned_value(values[name][idx]) for name in values}"
    assert source.count(old) == 1
    edited = source.replace(old, old.replace("returned_value", "money"))
    assert _guard_rejects(edited)


# ── generic US variable comparison (us_populace) ─────────────────────────────
def us_compare(pe_value, axiom_value):
    from axiom_oracles.bridges import us_populace
    from axiom_oracles.bridges.registry import PolicyEngineMapping

    mapping = PolicyEngineMapping(
        legal_id="us-ca:regulations/cdss/eas/49/49-055#ca_capi",
        country="us",
        mapping_type="direct_variable",
        policyengine_variable="ca_capi",
    )
    cases = [
        us_populace.USVariableCase(
            variable="ca_capi",
            person_id=person,
            spm_unit_id=person,
            state="CA",
            inputs={},
            pe_outputs={"ca_capi": value},
        )
        for person, value in ((1, 600.0), (2, pe_value))
    ]
    outputs = [
        {"outputs": {mapping.legal_id: {"value": {"value": value}}}}
        for value in (600.0, axiom_value)
    ]
    return us_populace.compare_outputs(
        variables=("ca_capi",),
        cases_by_variable={"ca_capi": cases},
        mappings_by_variable={"ca_capi": (mapping,)},
        axiom_outputs_by_variable={"ca_capi": outputs},
        skipped_reasons={},
        tolerance=0.01,
        relative_tolerance=1e-9,
    )


@pytest.mark.parametrize("invalid", INVALID)
@pytest.mark.parametrize("side", ["policyengine", "axiom"])
def test_us_variable_comparison_keeps_invalid_returns_out_of_counts(invalid, side):
    report = us_compare(
        invalid if side == "policyengine" else 0.0,
        invalid if side == "axiom" else 0.0,
    )
    raw = json.loads(json.dumps(report.to_json(), allow_nan=False))
    assert raw["compared_values"] == 1
    assert raw["mismatch_count"] == raw["uncompared_mismatches"] == 1
    assert raw["errors"] == [
        {
            "engine": side,
            "case_id": "person_2",
            "variable": "ca_capi",
            "output": "us-ca:regulations/cdss/eas/49/49-055#ca_capi",
            "error": "missing_or_nonfinite_output",
        }
    ]
    [summary] = raw["output_summary"]
    assert (
        summary["compared"]
        == summary["mismatches"]
        == summary["uncompared_mismatches"]
        == 1
    )
    assert raw["mismatches"][0]["reason"] == "invalid_output"


@pytest.mark.parametrize("value", [0, 0.0, False])
def test_us_variable_comparison_keeps_genuine_zero(value):
    raw = us_compare(value, 0.0).to_json()
    assert raw["compared_values"] == 2
    assert raw["mismatch_count"] == raw["uncompared_mismatches"] == 0
    assert raw["errors"] == []


# ── review follow-ups: checks the first round left untested ───────────────────
def test_adapter_honours_a_ledger_only_verdict():
    # "yes" is a verdict for the adapter's CSV parser but not for the
    # producer, which records an Axiom error. Only the ledger carries that.
    rows = produce([(100.0, True, 100.0, "yes"), (100.0, True, 100.0, "holds")])
    assert rows[0]["eligibility_compared"] is False
    report = publish(rows)
    eligibility = aggregate(report, ELIGIBILITY)
    assert eligibility["comparison_count"] == eligibility["match_count"] == 1
    assert eligibility["uncompared_mismatches"] == 1
    assert report["errors"] == [
        {
            "engine": "axiom",
            "case_id": "ecps-spm-1",
            "concept": ELIGIBILITY,
            "output": "axiom_snap_eligible",
            "error": "missing_or_nonfinite_output",
        }
    ]


def test_adapter_honours_amount_compared_false_with_parseable_cells():
    rows = through_csv(
        produce([(100.0, True, 100.0, "holds"), (0.0, True, 0.0, "holds")])
    )
    rows[1]["amount_compared"] = "False"
    rows[1]["errors"] = "[]"
    report = runner()._adapt_snap_ecps_csv_to_v2(
        rows, {"parameters": {"jurisdiction": "us-co"}}
    )
    amount = aggregate(report, AMOUNT)
    assert amount["comparison_count"] == amount["match_count"] == 1
    assert amount["uncompared_mismatches"] == 1
    assert report["summary"]["error_count"] == 1


@pytest.mark.parametrize("cell", ["not json", "{}", '"x"', "[", "42"])
def test_adapter_refuses_an_unreadable_error_ledger(cell):
    rows = through_csv(produce([(100.0, True, 100.0, "holds")]))
    rows[0]["errors"] = cell
    with pytest.raises(ValueError, match="SNAP error ledger"):
        runner()._adapt_snap_ecps_csv_to_v2(
            rows, {"parameters": {"jurisdiction": "us-co"}}
        )


@pytest.mark.parametrize("invalid", INVALID)
def test_eligibility_bridge_refuses_invalid_is_snap_eligible(monkeypatch, invalid):
    # us-az projects is_snap_eligible as the input na_budgetary_unit_is_eligible,
    # where a NaN would become bool(nan) == True.
    config = JURISDICTION_CONFIGS["us-az"]
    assert config.eligibility_oracle_bridge
    with pytest.raises(ValueError, match="spm_unit_1 is_snap_eligible: missing"):
        load_stub(monkeypatch, "is_snap_eligible", invalid, config=config)


def test_eligibility_bridge_keeps_a_valid_verdict(monkeypatch):
    config = JURISDICTION_CONFIGS["us-az"]
    [case] = load_stub(monkeypatch, "is_snap_eligible", True, config=config)
    assert case.pe_outputs["is_snap_eligible"] is True


@pytest.mark.parametrize("invalid", INVALID)
def test_positive_snap_only_keeps_an_invalid_allotment_for_the_ledger(
    monkeypatch, invalid
):
    # A NaN allotment fails `> 0`; it must reach compare() as an engine error,
    # not drop out of the population unseen.
    [case] = load_stub(
        monkeypatch, PE_COMPARED_OUTPUT, invalid, positive_snap_only=True
    )
    row = produce_case(case)
    assert row["amount_compared"] is False
    assert {
        "engine": "policyengine",
        "output": "pe_snap",
        "error": "missing_or_nonfinite_output",
    } in row["errors"]


@pytest.mark.parametrize("value", [0.0, -5.0])
def test_positive_snap_only_still_drops_a_finite_non_positive_allotment(
    monkeypatch, value
):
    assert (
        load_stub(monkeypatch, PE_COMPARED_OUTPUT, value, positive_snap_only=True) == []
    )


def produce_case(case):
    case = ProjectedCase(
        spm_unit_id=case.spm_unit_id,
        household_id=case.household_id,
        inputs={},
        member_inputs=[],
        pe_outputs={
            **pe_outputs(),
            PE_COMPARED_OUTPUT: case.pe_outputs[PE_COMPARED_OUTPUT],
        },
    )
    [row] = snap_populace.compare([case], [axiom_outputs()], 1.5, config=CONFIG)
    return row


@pytest.mark.parametrize("utility_type", ["", "XYZ", "sua", "nan"])
def test_unrecognized_utility_allowance_type_is_refused(monkeypatch, utility_type):
    with pytest.raises(ValueError, match="snap_utility_allowance_type"):
        load_stub(
            monkeypatch,
            "snap_utility_allowance_type",
            utility_type,
            utility_projection="policyengine-type",
        )


@pytest.mark.parametrize("utility_type", ["SUA", "LUA", "IUA", "NONE"])
def test_recognized_utility_allowance_types_project(monkeypatch, utility_type):
    [case] = load_stub(
        monkeypatch,
        "snap_utility_allowance_type",
        utility_type,
        utility_projection="policyengine-type",
    )
    assert case.pe_outputs["snap_utility_allowance_type"] == utility_type


def test_person_support_check_refuses_misaligned_person_arrays(monkeypatch):
    # zip(..., strict=True): a person array shorter than person_spm_unit_id
    # must fail, not silently skip the trailing persons' checks.
    with pytest.raises(ValueError):
        load_stub(
            monkeypatch,
            "ssi",
            0.0,
            overrides={"person_spm_unit_id": [1, 1], "person_household_id": [1, 1]},
        )


@pytest.mark.parametrize("pe_value", [math.nan, None, 0.0, 600.0])
@pytest.mark.parametrize("path", ["missing_axiom_row", "missing_axiom_output"])
def test_us_variable_missing_axiom_return_is_an_uncompared_error(path, pe_value):
    # A missing Axiom row or output is an invalid return: an engine error and
    # an uncompared diagnostic mismatch, with no 0.0 stand-in on either side.
    from axiom_oracles.bridges import us_populace
    from axiom_oracles.bridges.registry import PolicyEngineMapping

    mapping = PolicyEngineMapping(
        legal_id="us-ca:regulations/cdss/eas/49/49-055#ca_capi",
        country="us",
        mapping_type="direct_variable",
        policyengine_variable="ca_capi",
    )
    cases = [
        us_populace.USVariableCase(
            variable="ca_capi",
            person_id=person,
            spm_unit_id=person,
            state="CA",
            inputs={},
            pe_outputs={"ca_capi": value},
        )
        for person, value in ((1, 600.0), (2, pe_value))
    ]
    outputs = [{"outputs": {mapping.legal_id: {"value": {"value": 600.0}}}}]
    if path == "missing_axiom_output":
        outputs.append({"outputs": {}})
    raw = us_populace.compare_outputs(
        variables=("ca_capi",),
        cases_by_variable={"ca_capi": cases},
        mappings_by_variable={"ca_capi": (mapping,)},
        axiom_outputs_by_variable={"ca_capi": outputs},
        skipped_reasons={},
        tolerance=0.01,
        relative_tolerance=1e-9,
    ).to_json()
    raw = json.loads(json.dumps(raw, allow_nan=False))
    assert raw["compared_values"] == 1
    assert raw["mismatch_count"] == raw["uncompared_mismatches"] == 1
    [summary] = raw["output_summary"]
    assert summary["compared"] == summary["mismatches"] == 1
    assert summary["uncompared_mismatches"] == 1
    engines = ["axiom"] + (
        ["policyengine"] if pe_value is None or math.isnan(pe_value) else []
    )
    assert [error["engine"] for error in raw["errors"]] == engines
    assert {error["case_id"] for error in raw["errors"]} == {"person_2"}
    [row] = raw["mismatches"]
    assert row["reason"] == path
    assert row["axiom"] is None and row["diff"] is None
    assert row["policyengine"] == (
        None if pe_value is None or math.isnan(pe_value) else pe_value
    )


def test_a_case_with_nothing_compared_is_unmeasured():
    # Both the amount pair and the eligibility pair failed, so the case was
    # never measured: its rate is None, not 0.0 (measured disagreement).
    rows = produce(
        [(math.nan, math.nan, 100.0, "holds"), (100.0, True, 100.0, "holds")]
    )
    report = publish(rows)
    summary = report["summary"]
    assert summary["comparison_count"] == summary["match_count"] == 2
    assert summary["uncompared_mismatches"] == 2
    rates = {case["case_id"]: case["match_rate"] for case in report["cases"]}
    assert rates == {"ecps-spm-1": None, "ecps-spm-2": 100.0}

    # The served case row carries the same None, and the dashboard's
    # tri-state contract reads it as unmeasured (null), not as disagreement.
    emitter = _load("snap_604_emit_cases", "scripts/emit_case_artifacts.py")
    served = [emitter.compact_case(case, {})["r"] for case in report["cases"]]
    assert served == [None, 100.0]
    bun = shutil.which("bun")
    if bun is None:
        pytest.skip("dashboard helpers require Bun")
    script = (
        'import { caseAgreement } from "./dashboard/src/utils/caseAgreement.mjs";'
        "const rates = JSON.parse(await Bun.stdin.text());"
        "console.log(JSON.stringify(rates.map(caseAgreement)));"
    )
    result = subprocess.run(
        [bun, "-e", script],
        cwd=ROOT,
        input=json.dumps(served),
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == [None, True]


@pytest.mark.parametrize("garbage", ["abc", "", "1,0", "NaN!"])
def test_unparseable_axiom_decimal_is_an_axiom_error_not_a_crash(garbage):
    [row] = produce([(100.0, True, garbage, "holds")])
    assert row["amount_compared"] is False and row["match"] is False
    assert row["errors"] == [
        {
            "engine": "axiom",
            "output": "axiom_snap_allotment",
            "error": "missing_or_nonfinite_output",
        }
    ]
    amount = aggregate(publish([row]), AMOUNT)
    assert amount["comparison_count"] == 0 and amount["uncompared_mismatches"] == 1


# BUA and TUA are not PolicyEngine-US values; accept them only where a branch
# projects them by name (us-ny both, us-az TUA). Elsewhere they would project
# as "no utility" silently, so they are refused.
@pytest.mark.parametrize(
    "jurisdiction,utility_type",
    [("us-ny", "BUA"), ("us-ny", "TUA"), ("us-az", "TUA")],
)
def test_bua_tua_project_only_where_a_branch_names_them(jurisdiction, utility_type):
    projected = snap_populace.project_utility_allowance_type(
        JURISDICTION_CONFIGS[jurisdiction], utility_type, "NY_NAS"
    )
    assert any(value is True for value in projected.values())


@pytest.mark.parametrize(
    "jurisdiction,utility_type",
    [
        ("us-az", "BUA"),
        ("us-co", "BUA"),
        ("us-co", "TUA"),
        ("us-ca", "BUA"),
        ("us-ca", "TUA"),
    ],
)
def test_bua_tua_are_refused_where_no_branch_names_them(jurisdiction, utility_type):
    with pytest.raises(ValueError, match="snap_utility_allowance_type"):
        snap_populace.project_utility_allowance_type(
            JURISDICTION_CONFIGS[jurisdiction], utility_type, ""
        )


@pytest.mark.parametrize("utility_type", ["BUA", "TUA"])
def test_loader_refuses_bua_tua_in_the_generic_branch(monkeypatch, utility_type):
    # co, or and ut, the suites on this producer, take the generic branch.
    with pytest.raises(ValueError, match="snap_utility_allowance_type"):
        load_stub(
            monkeypatch,
            "snap_utility_allowance_type",
            utility_type,
            utility_projection="policyengine-type",
        )


def _served_case(pair):
    from axiom_oracles import evidence

    report = publish(produce([pair]))
    [case] = report["cases"]
    emitter = _load("snap_604_emit_cases", "scripts/emit_case_artifacts.py")
    served = emitter.compact_case(case, {})
    defects: list[str] = []
    evidence._validate_compact_case(served, "cases[0]", defects, "us-co-snap-ecps")
    return case, served, defects


def test_served_rate_leaves_an_uncompared_pair_out_and_flags_it():
    # Amount uncompared (PolicyEngine NaN) beside a matched eligibility pair:
    # the one compared pair agrees, so the served rate is 100.0, and the
    # uncompared row stays visible with "u": true.
    case, served, defects = _served_case((math.nan, True, 100.0, "holds"))
    assert case["match_rate"] == 100.0
    assert served["r"] == 100.0
    [row] = served["m"]
    assert row["u"] is True and row["c"] == AMOUNT
    assert defects == []


def test_served_rate_still_counts_a_real_disagreement():
    case, served, defects = _served_case((100.0, True, 50.0, "holds"))
    assert case["match_rate"] == served["r"] == 50.0
    [row] = served["m"]
    assert "u" not in row
    assert defects == []


@pytest.mark.parametrize("rate", [50.0, 0.0])
def test_validator_refuses_a_rate_that_counts_an_uncompared_row(rate):
    from axiom_oracles import evidence

    _, served, _ = _served_case((math.nan, True, 100.0, "holds"))
    served["r"] = rate
    defects: list[str] = []
    evidence._validate_compact_case(served, "cases[0]", defects, "us-co-snap-ecps")
    assert any("match rate" in defect for defect in defects), defects


def test_validator_refuses_a_non_true_uncompared_flag():
    from axiom_oracles import evidence

    _, served, _ = _served_case((math.nan, True, 100.0, "holds"))
    served["m"][0]["u"] = "yes"
    defects: list[str] = []
    evidence._validate_compact_case(served, "cases[0]", defects, "us-co-snap-ecps")
    assert any(".u must be true" in defect for defect in defects), defects


@pytest.mark.parametrize(
    "pe_amount,ax_amount,kind",
    [
        (math.nan, 100.0, "missing_right"),
        (None, 100.0, "missing_right"),
        (100.0, math.inf, "missing_left"),
        (100.0, None, "missing_left"),
        (math.nan, None, "missing_both"),
    ],
)
def test_uncompared_amount_with_a_missing_side_uses_the_missing_kind(
    pe_amount, ax_amount, kind
):
    # A missing side is labelled as such (as the generic Comparator does), so
    # a case_id-only amount_difference disposition cannot "explain" it.
    report = publish(produce([(pe_amount, True, ax_amount, "holds")]))
    [row] = [m for m in report["mismatches"] if m["concept"] == AMOUNT]
    assert row["uncompared"] is True and row["kind"] == kind
    assert {"value": kind, "count": 1} in report["summary"]["mismatches_by_kind"]


def test_ledger_only_amount_failure_keeps_amount_difference():
    # Both values present but the producer marked the pair uncompared.
    rows = through_csv(produce([(100.0, True, 100.0, "holds")]))
    rows[0]["amount_compared"] = "False"
    rows[0]["errors"] = "[]"
    report = runner()._adapt_snap_ecps_csv_to_v2(
        rows, {"parameters": {"jurisdiction": "us-co"}}
    )
    [row] = [m for m in report["mismatches"] if m["concept"] == AMOUNT]
    assert row["uncompared"] is True and row["kind"] == "amount_difference"
    assert row["left"] == row["right"] == 100.0
