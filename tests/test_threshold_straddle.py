"""Load-bearing invariants for exact interpretation and threshold evidence.

* Every requested output checked for a view must reproduce its recorded typed
  value; byte-binding or checked-output disagreement invalidates that verdict.
* Only executed paths observe sites. Static extraction includes dormant
  reachable paths, so no observation cannot be mistaken for completion.
* Min/max below/at/above partition live observations; equality alone never
  straddles. Comparisons partition false/true outcomes into below/above, with
  equality assigned by the operator. Counts are permutation invariant.
* For fixed artifact/root scope, adding a valid evaluation cannot remove
  observed straddling. New period-specific sites or stale exemptions can still
  make the overall verdict incomplete.
* Missing inputs, unknown IR, and unsupported semantics cannot establish a
  zero-site proof.
* Parameter-only source roots have zero sites only within the accepted source
  shape, with a dated numeric literal in every selected version. The caller
  must validate the signature.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
from decimal import Decimal, localcontext
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from scripts.threshold_straddle import (
    InterpretationError,
    Interpreter,
    _decimal,
    _literal,
    compute_threshold_straddle,
    apply_threshold_exemptions,
    _REPLAY_CACHE,
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
    assert len(sites) == 1
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


def test_parameter_on_input_side_is_not_a_threshold():
    program = artifact(
        {"kind": "min", "items": [{"kind": "add", "items": [INPUT, PARAM]}, INPUT]}
    )
    program["program"]["parameters"][0]["versions"][0]["values"]["0"] = literal("0.1")[
        "value"
    ]
    maximum = "79228162514264337593543950335"
    block = assess(program, ["0", maximum], ["0", maximum])
    assert block["self_check"]["complete"]
    assert block["sites"] == []
    # Neither side is a parameter-only threshold, irrespective of rounding.


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


@settings(deadline=None)
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


@settings(deadline=None)
@given(
    st.lists(st.integers(-100, 100), min_size=1, max_size=25), st.integers(-100, 100)
)
def test_adding_evaluation_cannot_unstraddle(values, extra):
    before = assess(artifact(), values)
    after = assess(artifact(), [*values, extra])
    assert not before["complete"] or after["complete"]
    assert not before["sites"][0]["straddled"] or after["sites"][0]["straddled"]


@settings(deadline=None)
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
        "_straddle_certify",
        Path(__file__).resolve().parents[1] / "scripts" / "certify.py",
    )
    certify = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(certify)
    rows, complete = certify._exercise_block([], {"suites": {}}, [])
    assert rows == {}
    assert complete is False


@pytest.mark.parametrize("op", ["lt", "lte", "gt", "gte"])
@pytest.mark.parametrize("reverse", [False, True])
@settings(deadline=None)
@given(st.lists(st.integers(8, 12), min_size=1, max_size=15))
def test_comparison_outcomes_partition_equality_and_permute(op, reverse, values):
    def outcome(value):
        left, right = (10, value) if reverse else (value, 10)
        return {
            "lt": left < right,
            "lte": left <= right,
            "gt": left > right,
            "gte": left >= right,
        }[op]

    expr = {
        "kind": "comparison",
        "op": op,
        "left": PARAM if reverse else INPUT,
        "right": INPUT if reverse else PARAM,
    }
    outputs = [outcome(value) for value in values]
    block = assess(artifact(expr), values, outputs)
    site = block["sites"][0]
    assert site["above"] == sum(outputs)
    assert site["below"] == len(outputs) - sum(outputs)
    assert site["at"] == 0
    assert site["below"] + site["above"] == site["live_observations"] == len(values)
    assert site["straddled"] == (any(outputs) and not all(outputs))
    for label, expected in (("below", False), ("above", True)):
        nearest = site[f"nearest_{label}"]
        if nearest is not None:
            assert outcome(Decimal(nearest)) is expected
        else:
            assert not any(value is expected for value in outputs)

    assert (
        block["sites"] == assess(artifact(expr), values[::-1], outputs[::-1])["sites"]
    )
    extended = assess(artifact(expr), [*values, 10], [*outputs, outcome(10)])
    assert not block["complete"] or extended["complete"]


def test_input_versus_its_floor_is_not_a_parameter_threshold():
    amount = {"kind": "add", "items": [INPUT, PARAM]}
    expr = {
        "kind": "comparison",
        "op": "gt",
        "left": amount,
        "right": {"kind": "floor", "value": amount},
    }
    block = assess(artifact(expr), [0, "0.5"], [False, True])
    assert block["self_check"]["complete"] and block["complete"]
    assert block["sites"] == []


@pytest.mark.parametrize("kind", ["parameter", "derived"])
@settings(deadline=None)
@given(st.lists(st.integers(1, 100), min_size=2, max_size=10))
def test_equal_effective_dates_select_last_version(kind, values):
    program = artifact(PARAM)
    if kind == "parameter":
        program["program"]["parameters"][0]["versions"] = [
            {"effective_from": "2025-01-01", "values": {"0": literal(value)["value"]}}
            for value in values
        ]
    else:
        program["program"]["derived"][0]["versions"] = [
            {"effective_from": "2025-01-01", "expr": literal(value)} for value in values
        ]
    assert assess(program, [0], [values[-1]])["self_check"]["complete"]


@pytest.mark.parametrize(
    "ident", ["test:module#root", "root", "test:module#X/versions/0"]
)
def test_duplicate_or_invalid_derived_ids_fail_closed(ident):
    program = artifact()
    program["program"]["derived"].append({"name": "other", "id": ident, "expr": MIN})
    block = assess(program, [1, 11])
    assert not block["complete"]
    assert any("derived id" in reason for reason in block["defects"])


@pytest.mark.parametrize(
    "scope,key,value",
    [
        ("rule", "values", {0: 1}),
        ("rule", "formula", "income"),
        ("rule", "entity", "Person"),
        ("rule", "indexed_by", "rank"),
        ("rule", "id", "other"),
        ("rule", "future_key", True),
        ("version", "values", {0: 1}),
        ("version", "effective_to", "2026-01-01"),
        ("version", "future_key", True),
    ],
)
def test_parameter_only_proof_rejects_unaccepted_keys(scope, key, value):
    import yaml

    rule = {
        "name": "amount",
        "kind": "parameter",
        "versions": [{"effective_from": "2025-01-01", "formula": "255"}],
    }
    (rule if scope == "rule" else rule["versions"][0])[key] = value
    block = parameter_only_straddle(
        yaml.safe_dump({"rules": [rule]}).encode(),
        roots=["de:test#amount"],
        module_id="de:test",
    )
    assert block["mode"] == "unavailable"


def test_parameter_only_version_requires_effective_date():
    raw = (
        b"rules:\n- name: amount\n  kind: parameter\n  versions:\n  - formula: '255'\n"
    )
    assert not parameter_only_straddle(
        raw, roots=["de:test#amount"], module_id="de:test"
    )["complete"]


def exemption_ledger(block, **changes):
    entry = {
        "program": "test",
        "view": "test",
        "site_id": block["sites"][0]["id"],
        "side": "above",
        "reason": "Fixture's permitted input domain ends at ten.",
        "citation": "Fixture input-domain specification.",
    }
    entry.update(changes)
    return json.dumps({"schema_version": 1, "exemptions": [entry]}).encode()


def test_exemptions_are_decisions_not_observations():
    block = assess(artifact(), [1, 10])
    result = apply_threshold_exemptions({"test": block}, exemption_ledger(block))[
        "test"
    ]
    assert result["complete"]
    assert result["sites"][0]["above"] == 0
    assert not result["sites"][0]["straddled"]
    assert result["sites"][0]["exempted_sides"] == ["above"]
    assert len(result["unstraddled"]) == len(result["exemptions"]) == 1
    assert "exemptions" not in block


@pytest.mark.parametrize(
    "changes",
    [
        {"view": "missing"},
        {"program": "missing"},
        {"site_id": "missing"},
        {"side": "below"},
        {"side": "at"},
        {"reason": " "},
        {"citation": ""},
        {"reason": 1},
        {"unknown": "x"},
    ],
)
def test_invalid_or_stale_exemptions_fail_closed(changes):
    block = assess(artifact(), [1, 10])
    result = apply_threshold_exemptions(
        {"test": block}, exemption_ledger(block, **changes)
    )["test"]
    assert not result["complete"] and result["defects"]


def test_exemption_becomes_stale_when_missing_side_is_observed():
    block = assess(artifact(), [1, 10])
    after = assess(artifact(), [1, 10, 11])
    result = apply_threshold_exemptions({"test": after}, exemption_ledger(block))[
        "test"
    ]
    assert not result["complete"] and "stale" in result["defects"][0]


def test_replay_cache_shares_views_and_revalidates_bytes_and_traces(monkeypatch):
    _REPLAY_CACHE.clear()
    raw, traces = trace(artifact(), [1, 11])
    traces["evaluations"][1]["view"] = "other"
    calls = 0
    original = Interpreter.evaluate

    def counted(self, root):
        nonlocal calls
        calls += 1
        return original(self, root)

    monkeypatch.setattr(Interpreter, "evaluate", counted)
    first = compute_threshold_straddle(raw, traces, view="test")
    second = compute_threshold_straddle(raw, traces, view="other")
    combined = compute_threshold_straddle(raw, traces)
    assert calls == 2
    assert first["sites"][0]["below"] == second["sites"][0]["above"] == 1
    assert not first["complete"] and not second["complete"] and combined["complete"]
    combined["sites"][0]["below"] = 999
    assert compute_threshold_straddle(raw, traces)["sites"][0]["below"] == 1
    assert calls == 2
    assert not compute_threshold_straddle(raw + b" ", traces)["complete"]
    changed = copy.deepcopy(traces)
    changed["evaluations"][0]["response"]["outputs"]["test:module#root"]["value"][
        "value"
    ] = 999
    assert not compute_threshold_straddle(raw, changed)["complete"]
    assert calls == 4
    assert compute_threshold_straddle(raw, traces)["complete"]
    assert calls == 4


@pytest.mark.parametrize(
    "mutation",
    ["duplicate", "bool_version", "missing_entries", "extra_field", "entries_mapping"],
)
def test_exemption_ledger_shape_is_strict(mutation):
    block = assess(artifact(), [1, 10])
    ledger = json.loads(exemption_ledger(block))
    if mutation == "duplicate":
        ledger["exemptions"] *= 2
    elif mutation == "bool_version":
        ledger["schema_version"] = True
    elif mutation == "missing_entries":
        del ledger["exemptions"]
    elif mutation == "extra_field":
        ledger["extra"] = []
    else:
        ledger["exemptions"] = {}
    result = apply_threshold_exemptions({"test": block}, json.dumps(ledger).encode())[
        "test"
    ]
    assert not result["complete"] and result["defects"]


def test_committed_exemptions_reference_missing_sides_without_changing_counts():
    traces = json.loads(TRACES.read_text())
    blocks = {
        view: compute_threshold_straddle(PROGRAM.read_bytes(), traces, view=view)
        for view in sorted({row["view"] for row in traces["evaluations"]})
    }
    applied = apply_threshold_exemptions(
        blocks, (ROOT / "conformance/threshold-straddle-exemptions.yaml").read_bytes()
    )
    assert sum(len(block["exemptions"]) for block in applied.values()) == 1
    for view, block in applied.items():
        assert not block["defects"]
        before = {site["id"]: site for site in blocks[view]["sites"]}
        for site in block["sites"]:
            for field in ("below", "at", "above", "live_observations", "straddled"):
                assert site[field] == before[site["id"]][field]
    ietc = applied["nz/independent-earner-tax-credit"]
    assert not ietc["complete"]
    assert ietc["unstraddled"][0]["exempted_sides"] == ["above"]
    assert ietc["unstraddled"][0]["below"] == 0


def test_removing_exemption_revalidates_original_unobserved_side():
    block = assess(artifact(), [1, 10])
    first = apply_threshold_exemptions({"test": block}, exemption_ledger(block))
    assert first["test"]["complete"]
    second = apply_threshold_exemptions(first, b'{"schema_version":1,"exemptions":[]}')[
        "test"
    ]
    assert not second["complete"]
    assert second["exemptions"] == []
    assert "exempted_sides" not in second["sites"][0]


def test_replay_cache_bytes_rechecks_trace_mutation(monkeypatch):
    _REPLAY_CACHE.clear()
    raw, traces = trace(artifact(), [1, 11])
    encoded = json.dumps(traces).encode()
    first = compute_threshold_straddle(raw, encoded)
    assert first["complete"]

    def forbidden(*args):
        raise AssertionError("unchanged trace bytes must reuse replay")

    monkeypatch.setattr(Interpreter, "evaluate", forbidden)
    assert compute_threshold_straddle(raw, encoded, view="test")["complete"]
    assert not compute_threshold_straddle(raw, encoded[:-1])["complete"]


def test_mutating_dictionary_cannot_change_cached_trace_bytes():
    _REPLAY_CACHE.clear()
    raw, traces = trace(artifact(), [1, 11])
    encoded = json.dumps(traces, sort_keys=True, separators=(",", ":")).encode()
    assert compute_threshold_straddle(raw, traces)["complete"]
    traces["evaluations"].clear()
    assert compute_threshold_straddle(raw, encoded)["complete"]
    assert not compute_threshold_straddle(raw, traces)["complete"]


@pytest.mark.parametrize("raw", [b"rules: [", b"rules:\n  bad: @broken"])
def test_malformed_yaml_becomes_unavailable_or_ledger_defect(raw):
    proof = parameter_only_straddle(raw, roots=["de:test#amount"], module_id="de:test")
    assert proof["mode"] == "unavailable" and not proof["complete"]
    block = assess(artifact(), [1, 11])
    invalid = apply_threshold_exemptions({"test": block}, raw)["test"]
    assert invalid["defects"] and not invalid["complete"]


@pytest.mark.parametrize(
    "extra",
    [
        {
            "source_relation": {
                "type": "sets",
                "target": "de:test#amount",
                "value": "de:test#other",
            }
        },
        {"data_relation": {"arity": 1}},
        {"future_key": True},
    ],
)
def test_unselected_rules_cannot_carry_global_semantic_fields(extra):
    import yaml

    document = {
        "rules": [
            {
                "name": "amount",
                "kind": "parameter",
                "versions": [{"effective_from": "2025-01-01", "formula": "255"}],
            },
            {
                "name": "other",
                "kind": "derived",
                "versions": [{"effective_from": "2025-01-01", "formula": "1"}],
                **extra,
            },
        ]
    }
    proof = parameter_only_straddle(
        yaml.safe_dump(document).encode(), roots=["de:test#amount"], module_id="de:test"
    )
    assert proof["mode"] == "unavailable" and not proof["complete"]
