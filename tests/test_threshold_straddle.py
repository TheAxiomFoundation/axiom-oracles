"""Load-bearing invariants for exact interpretation and threshold evidence.

* Every recorded NZ requested output equals the interpreter's typed value;
  any byte-binding or output disagreement invalidates the whole verdict.
* Only executed paths observe sites. Static extraction includes dormant
  reachable paths, so no observation cannot be mistaken for completion.
* Below/at/above form a disjoint, exhaustive partition of live observations;
  equality alone never straddles. Counts and verdicts are permutation invariant.
* Adding a valid evaluation cannot un-straddle an existing site.
* Missing inputs, unknown IR, and unsupported semantics never become zero.
* Parameter-only source roots have zero sites only when each selected rule's
  every version is a numeric literal. The caller must validate its signature.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
from decimal import Decimal, localcontext
from pathlib import Path

import pytest
from hypothesis import given, strategies as st

from scripts.threshold_straddle import (
    InterpretationError,
    Interpreter,
    _decimal,
    _literal,
    compute_threshold_straddle,
    parameter_only_straddle,
)

ROOT = Path(__file__).resolve().parents[1]
PROGRAM = (
    ROOT / "conformance/executable/nz-treasury-incomeexplorer/compiled-program.json"
)
TRACES = ROOT / "comparisons/nz-treasury-incomeexplorer/evaluation-traces.json"
PERIOD = {"start": "2026-04-01", "end": "2027-03-31", "period_kind": "tax_year"}


def literal(value):
    kind = (
        "bool"
        if isinstance(value, bool)
        else "integer"
        if isinstance(value, int)
        else "decimal"
    )
    return {"kind": "literal", "value": {"kind": kind, "value": value}}


INPUT = {"kind": "input", "name": "income"}
PARAM = {"kind": "parameter_lookup", "parameter": "threshold", "index": literal(0)}
MIN = {"kind": "min", "items": [INPUT, PARAM]}


def artifact(expr=MIN):
    return {
        "artifact_format_version": 1,
        "program": {
            "parameters": [
                {
                    "name": "threshold",
                    "versions": [
                        {
                            "effective_from": "2025-01-01",
                            "values": {"0": literal(10)["value"]},
                        },
                    ],
                }
            ],
            "derived": [
                {
                    "name": "root",
                    "id": "test:module#root",
                    "expr": expr,
                    "semantics": "scalar",
                    "dtype": "decimal",
                }
            ],
        },
        "metadata": {
            "input_catalog": [
                {"slot": "income", "request_names": ["test:module#input.income"]}
            ]
        },
    }


def trace(program, observations, outputs=None):
    raw = json.dumps(program).encode()
    if outputs is None:
        outputs = [min(value, 10) for value in observations]
    evaluations = []
    for i, (value, expected) in enumerate(zip(observations, outputs, strict=True)):
        query = {
            "entity_id": "person",
            "period": PERIOD,
            "outputs": ["test:module#root"],
        }
        response = (
            {"kind": "judgment", "outcome": "holds" if expected else "not_holds"}
            if isinstance(expected, bool)
            else {"kind": "scalar", "value": literal(expected)["value"]}
        )
        evaluations.append(
            {
                "evaluation_id": str(i),
                "view": "test",
                "requested_output_roots": query["outputs"],
                "request": {
                    "queries": [query],
                    "dataset": {
                        "inputs": [
                            {
                                "entity_id": "person",
                                "name": "test:module#input.income",
                                "interval": {
                                    "start": PERIOD["start"],
                                    "end": PERIOD["end"],
                                },
                                "value": literal(value)["value"],
                            }
                        ],
                        "relations": [],
                    },
                },
                "response": {
                    "entity_id": "person",
                    "period": PERIOD,
                    "outputs": {"test:module#root": response},
                },
            }
        )
    return raw, {
        "compiled_program": {"artifact_sha256": hashlib.sha256(raw).hexdigest()},
        "evaluations": evaluations,
    }


def assess(program, observations, outputs=None):
    return compute_threshold_straddle(*trace(program, observations, outputs))


def test_differential_every_recorded_nz_engine_output():
    traces = json.loads(TRACES.read_text())
    block = compute_threshold_straddle(PROGRAM.read_bytes(), traces)
    check = block["self_check"]
    assert check == {
        "evaluations": 883,
        "outputs_checked": 2459,
        "outputs_matched": 2459,
        "complete": True,
        "failures": [],
    }
    assert sum(len(e["response"]["outputs"]) for e in traces["evaluations"]) == 2459
    assert not block["defects"]


def test_income_tax_has_no_evidence_above_180000():
    block = compute_threshold_straddle(
        PROGRAM.read_bytes(), json.loads(TRACES.read_text()), view="nz/income-tax"
    )
    sites = [
        s
        for s in block["unstraddled"]
        if s.get("parameter") == "individual_income_tax_bracket_thresholds"
        and s["index"] == 4
    ]
    assert block["self_check"]["complete"]
    assert not block["complete"]
    assert len(sites) == 2
    direct = next(s for s in sites if s["threshold"] == "180000")
    assert direct["max_observed"] == "78214.285714285714285714285714"
    assert direct["below"] == 91 and direct["above"] == 0


@pytest.mark.parametrize(
    ("expr", "value", "expected"),
    [
        (literal(3), 0, 3),
        (literal("1.25"), 0, "1.25"),
        (INPUT, 7, 7),
        (PARAM, 7, 10),
        ({"kind": "add", "items": [INPUT, literal(2), literal(3)]}, 7, 12),
        ({"kind": "sub", "left": INPUT, "right": literal(2)}, 7, 5),
        ({"kind": "mul", "left": INPUT, "right": literal(2)}, 7, 14),
        (
            {"kind": "div", "left": INPUT, "right": literal(3)},
            1,
            "0.3333333333333333333333333333",
        ),
        (MIN, 7, 7),
        ({"kind": "max", "items": [INPUT, PARAM, literal(-1)]}, 7, 10),
        ({"kind": "floor", "value": INPUT}, "-1.25", -2),
        (
            {
                "kind": "if",
                "condition": {
                    "kind": "comparison",
                    "op": "lt",
                    "left": INPUT,
                    "right": PARAM,
                },
                "then_expr": literal(1),
                "else_expr": literal(2),
            },
            7,
            1,
        ),
        (
            {
                "kind": "comparison",
                "op": "eq",
                "left": literal(True),
                "right": literal(True),
            },
            7,
            True,
        ),
        (
            {
                "kind": "not",
                "item": {
                    "kind": "comparison",
                    "op": "ne",
                    "left": INPUT,
                    "right": PARAM,
                },
            },
            10,
            True,
        ),
    ],
)
def test_supported_node_semantics(expr, value, expected):
    block = assess(artifact(expr), [value], [expected])
    assert block["self_check"]["complete"], block


def test_derived_values_and_parameter_version_selection_by_period_start():
    program = artifact({"kind": "derived", "name": "other"})
    program["program"]["derived"].append({"name": "other", "expr": PARAM})
    program["program"]["parameters"][0]["versions"].append(
        {"effective_from": "2026-06-01", "values": {"0": literal(20)["value"]}}
    )
    block = assess(program, [0], [10])
    assert block["self_check"]["complete"]


@pytest.mark.parametrize("kind,first", [("and", False), ("or", True)])
def test_short_circuit_preserves_static_unobserved_site(kind, first):
    comparison = {"kind": "comparison", "op": "gt", "left": INPUT, "right": PARAM}
    fixed = {
        "kind": "comparison",
        "op": "eq",
        "left": literal(first),
        "right": literal(True),
    }
    expr = {"kind": kind, "items": [fixed, comparison]}
    block = assess(artifact(expr), [1, 11], [first, first])
    assert block["self_check"]["complete"]
    assert len(block["sites"]) == 1
    assert block["sites"][0]["live_observations"] == 0
    assert not block["complete"]


def test_if_only_selected_branch_observes_sites():
    expr = {
        "kind": "if",
        "condition": {
            "kind": "comparison",
            "op": "lt",
            "left": INPUT,
            "right": literal(0),
        },
        "then_expr": MIN,
        "else_expr": literal(0),
    }
    block = assess(artifact(expr), [-1, 11], [-1, 0])
    assert block["self_check"]["complete"]
    assert block["sites"][0]["below"] == 1
    assert block["sites"][0]["above"] == 0


def test_nary_min_checks_every_eligible_pair_and_all_operands_live():
    expr = {
        "kind": "min",
        "items": [INPUT, PARAM, {"kind": "add", "items": [INPUT, literal(1)]}],
    }
    block = assess(artifact(expr), [1, 10, 11], [1, 10, 10])
    assert len(block["sites"]) == 2
    assert all(s["live_observations"] == 3 and s["straddled"] for s in block["sites"])


def test_difference_of_identical_operands_has_no_input_dependency():
    base = {"kind": "add", "items": [INPUT, PARAM]}
    expr = {
        "kind": "min",
        "items": [base, base],
    }
    block = assess(artifact(expr), [1], [11])
    assert block["self_check"]["complete"] and block["complete"]
    assert block["sites"] == []


def test_finite_precision_prevents_unsound_algebraic_cancellation():
    program = artifact(
        {"kind": "min", "items": [{"kind": "add", "items": [INPUT, PARAM]}, INPUT]}
    )
    program["program"]["parameters"][0]["versions"][0]["values"]["0"] = literal("0.1")[
        "value"
    ]
    maximum = "79228162514264337593543950335"
    block = assess(program, ["0", maximum], ["0", maximum])
    assert block["self_check"]["complete"]
    assert len(block["sites"]) == 1
    # At zero, x+p > x. At the maximum coefficient the addition rounds to x.
    assert block["sites"][0]["above"] == block["sites"][0]["at"] == 1


def test_equality_is_at_never_straddled_and_eq_ne_are_not_sites():
    block = assess(artifact(), [10, 10])
    assert block["sites"][0]["at"] == 2
    assert block["sites"][0]["below"] == block["sites"][0]["above"] == 0
    assert not block["complete"]
    for op, expected in [("eq", True), ("ne", False)]:
        expr = {"kind": "comparison", "op": op, "left": INPUT, "right": PARAM}
        assert assess(artifact(expr), [10], [expected])["sites"] == []


def test_synthetic_above_top_threshold_straddles():
    program = artifact()
    program["program"]["parameters"][0]["versions"][0]["values"]["0"] = literal(180000)[
        "value"
    ]
    assert not assess(program, [78214], [78214])["complete"]
    block = assess(program, [78214, 180001], [78214, 180000])
    assert block["complete"]
    assert block["sites"][0]["below"] == block["sites"][0]["above"] == 1


@pytest.mark.parametrize(
    "mutation",
    [
        "bytes",
        "output",
        "unknown",
        "missing",
        "alias",
        "unrequested",
        "entity",
        "period",
        "rounding",
    ],
)
def test_mutants_fail_closed(mutation):
    program = artifact()
    if mutation == "unknown":
        program["program"]["derived"][0]["expr"] = {
            "kind": "if",
            "condition": {
                "kind": "comparison",
                "op": "eq",
                "left": literal(True),
                "right": literal(True),
            },
            "then_expr": MIN,
            "else_expr": {"kind": "future_node"},
        }
    if mutation == "rounding":
        program["program"]["derived"][0]["rounding"] = {"mode": "half_up"}
    raw, traces = trace(program, [1, 11])
    if mutation == "bytes":
        raw += b" "
    if mutation == "output":
        traces["evaluations"][0]["response"]["outputs"]["test:module#root"]["value"][
            "value"
        ] = 999
    if mutation == "missing":
        traces["evaluations"][0]["request"]["dataset"]["inputs"] = []
    if mutation == "alias":
        traces["evaluations"][0]["request"]["dataset"]["inputs"][0]["name"] = "income"
    if mutation == "entity":
        traces["evaluations"][0]["response"]["entity_id"] = "other"
    if mutation == "period":
        traces["evaluations"][0]["response"]["period"] = {
            **PERIOD,
            "start": "2025-04-01",
        }
    kwargs = {"roots": ["unrequested"]} if mutation == "unrequested" else {}
    block = compute_threshold_straddle(raw, traces, **kwargs)
    assert not block["complete"]
    assert block["defects"] or block["self_check"]["failures"]


def test_input_intervals_select_latest_covering_whole_period():
    raw, traces = trace(artifact(), [1], [8])
    rows = traces["evaluations"][0]["request"]["dataset"]["inputs"]
    rows[0]["interval"]["start"] = "2020-01-01"
    rows.extend(
        [
            {
                **copy.deepcopy(rows[0]),
                "interval": {"start": "2025-01-01", "end": "2027-12-31"},
                "value": literal(8)["value"],
            },
            {
                **copy.deepcopy(rows[0]),
                "interval": {"start": "2026-06-01", "end": "2027-12-31"},
                "value": literal(9)["value"],
            },
        ]
    )
    assert compute_threshold_straddle(raw, traces)["self_check"]["complete"]


@given(st.lists(st.integers(min_value=-100, max_value=100), min_size=1, max_size=25))
def test_side_partition_and_permutation_invariance(values):
    forward = assess(artifact(), values)
    backward = assess(artifact(), list(reversed(values)))
    assert forward["sites"] == backward["sites"]
    assert forward["complete"] == backward["complete"]
    site = forward["sites"][0]
    assert (
        site["below"] + site["at"] + site["above"]
        == site["live_observations"]
        == len(values)
    )
    assert site["below"] == sum(v < 10 for v in values)
    assert site["at"] == values.count(10)
    assert site["above"] == sum(v > 10 for v in values)


@given(
    st.lists(st.integers(-100, 100), min_size=1, max_size=25), st.integers(-100, 100)
)
def test_adding_evaluation_cannot_unstraddle(values, extra):
    before = assess(artifact(), values)
    after = assess(artifact(), [*values, extra])
    assert not before["complete"] or after["complete"]
    assert not before["sites"][0]["straddled"] or after["sites"][0]["straddled"]


@given(st.integers(min_value=-(10**20), max_value=10**20), st.integers(1, 28))
def test_decimal_fitting_is_context_independent_and_representable(coefficient, scale):
    exact = Decimal(f"{coefficient}e-{scale}")
    with localcontext() as context:
        context.prec = 6
        fitted = _decimal(exact)
    assert fitted == exact
    assert -fitted.as_tuple().exponent <= 28


def test_missing_input_and_division_by_zero_are_errors():
    program = artifact({"kind": "div", "left": INPUT, "right": literal(0)})
    raw, traces = trace(program, [1])
    interpreter = Interpreter(json.loads(raw))
    evaluation = traces["evaluations"][0]
    interpreter.prepare(evaluation["request"], evaluation["request"]["queries"][0])
    with pytest.raises(InterpretationError, match="division by zero"):
        interpreter.evaluate("test:module#root")


def test_decimal_string_midpoints_round_away_while_arithmetic_rounds_even():
    midpoint = "1.00000000000000000000000000005"
    expected = Decimal("1.0000000000000000000000000001")
    assert (
        _literal({"kind": "decimal", "value": midpoint}, round_input=True) == expected
    )
    assert (
        _literal({"kind": "decimal", "value": "-" + midpoint}, round_input=True)
        == expected.copy_negate()
    )
    assert _decimal(Decimal(midpoint)) == Decimal(1)
    assert _literal({"kind": "decimal", "value": 42}) == Decimal(42)
    with pytest.raises(InterpretationError, match="syntax"):
        _literal({"kind": "decimal", "value": "1e2"}, round_input=True)


def test_duplicate_source_yaml_keys_are_not_a_zero_site_proof():
    raw = b"rules:\n- name: amount\n  kind: derived\n  kind: parameter\n  versions:\n  - formula: '255'\n"
    block = parameter_only_straddle(raw, roots=["de:test#amount"], module_id="de:test")
    assert block["mode"] == "unavailable" and "duplicate" in block["reason"]


def test_actual_de_parameter_root_proves_zero_sites():
    document = json.loads(
        (ROOT / "conformance/executable/de-kindergeld-signed-rulespec.json").read_text()
    )
    raw = base64.b64decode(document["module"]["bytes_base64"])
    block = parameter_only_straddle(
        raw,
        roots=["de:statutes/estg/66#monthly_kindergeld_per_child"],
        module_id="de:statutes/estg/66",
    )
    assert block["mode"] == "computed" and block["complete"]
    assert block["sites"] == []
    assert block["module_sha256"] == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize(
    "formula", ["1 + 2", True, ".nan", "1e2", "-1", ".5", "1.", "+1", "other_parameter"]
)
def test_de_nonliteral_formula_is_unavailable(formula):
    import yaml

    raw = yaml.safe_dump(
        {
            "rules": [
                {
                    "name": "amount",
                    "kind": "parameter",
                    "versions": [{"formula": formula}],
                }
            ]
        }
    ).encode()
    assert (
        parameter_only_straddle(raw, roots=["de:test#amount"], module_id="de:test")[
            "mode"
        ]
        == "unavailable"
    )


@pytest.mark.parametrize(
    "roots,kind",
    [
        (["de:test#missing"], "parameter"),
        (["de:test#amount"] * 2, "parameter"),
        (["de:test#amount"], "derived"),
        ([], "parameter"),
    ],
)
def test_de_root_contract_fails_closed(roots, kind):
    raw = f"rules:\n- name: amount\n  kind: {kind}\n  versions:\n  - formula: '255'\n".encode()
    assert (
        parameter_only_straddle(raw, roots=roots, module_id="de:test")["mode"]
        == "unavailable"
    )


def test_census_route_without_suites_is_not_exercised():
    """An empty exercise conjunction must not read as exercised."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_straddle_certify", Path(__file__).resolve().parents[1] / "scripts" / "certify.py"
    )
    certify = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(certify)
    rows, complete = certify._exercise_block([], {"suites": {}}, [])
    assert rows == {}
    assert complete is False

