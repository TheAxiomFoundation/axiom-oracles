"""The fixture-case engine evaluator behind the SNAP boundary and federal grids.

These pin the properties the grids rely on (#675): every published value is
the engine's, every recorded fixture output is checked against it, a
disagreement fails instead of publishing either value, every engine call is
receipted and journaled, and fixture shapes the evaluator does not understand
fail closed.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from axiom_oracles import rulespec_fixture_engine as fe
from axiom_oracles.engine_identity import ENGINE_RECEIPT_OUTPUT_ENV

MODULE = "us:regulations/test/abawd"
AGE = f"{MODULE}#input.member_age"
EXCEPTION = f"{MODULE}#exception_applies"
COUNT = f"{MODULE}#child_count"
AMOUNT = f"{MODULE}#amount"
RELATION = f"{MODULE}#relation.child_of_household"

PROGRAM = {
    "relations": [{"name": RELATION, "arity": 2}],
    "derived": [
        {"id": EXCEPTION, "entity": "Person", "expr": {"kind": "input"}},
        {
            "id": COUNT,
            "entity": "Person",
            "expr": {
                "kind": "count_related",
                "relation": RELATION,
                "current_slot": 1,
                "related_slot": 0,
            },
        },
        {"id": AMOUNT, "entity": "Person", "expr": {"kind": "input"}},
    ],
}
RULES = {
    EXCEPTION: {"ge": [AGE, 65]},
    COUNT: {"count": RELATION},
    AMOUNT: {"copy": AGE},
}


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "rulespec-us"
    module = root / "us" / "regulations" / "test" / "abawd.yaml"
    module.parent.mkdir(parents=True)
    module.write_text("format: rulespec/v1\n")
    return root


def _record(name: str, age: int, verdict: str, *, children: int = 0) -> dict:
    return {
        "name": name,
        "period": "2026-07",
        "input": {
            AGE: age,
            RELATION: [
                {f"{MODULE}#input.child_age": 10 + index} for index in range(children)
            ],
        },
        "output": {EXCEPTION: verdict},
    }


def _evaluate(binary, root, records, outputs=(EXCEPTION,)):
    return fe.evaluate_fixture_cases(
        binary,
        MODULE,
        [root],
        {record["name"]: record for record in records},
        lambda _case_id, _record: list(outputs),
    )


def test_values_are_the_engines_and_the_request_is_the_fixtures(
    fake_rules_engine, tmp_path
):
    binary = fake_rules_engine(PROGRAM, RULES)
    root = _root(tmp_path)
    record = _record("age_66", 66, "holds", children=2)
    record["output"][COUNT] = "2"

    values = _evaluate(binary, root, [record])

    # The recorded COUNT output is evaluated and checked too, though the
    # caller asked only for the exception verdict.
    assert values == {"age_66": {EXCEPTION: "holds", COUNT: Decimal("2")}}
    [request] = fake_rules_engine.requests()
    query = request["queries"][0]
    assert query["outputs"] == [EXCEPTION, COUNT]
    assert query["period"] == {
        "period_kind": "month",
        "start": "2026-07-01",
        "end": "2026-07-31",
    }
    flat = [item for item in request["dataset"]["inputs"] if item["name"] == AGE]
    assert flat == [
        {
            "name": AGE,
            "entity": "Person",
            "entity_id": query["entity_id"],
            "interval": {"start": "2026-07-01", "end": "2026-07-31"},
            "value": {"kind": "integer", "value": 66},
        }
    ]
    relations = request["dataset"]["relations"]
    assert len(relations) == 2
    # current_slot 1: the queried entity sits in slot 1, the child in slot 0.
    assert all(item["tuple"][1] == query["entity_id"] for item in relations)
    children = {item["tuple"][0] for item in relations}
    child_inputs = [
        item for item in request["dataset"]["inputs"] if item["name"] != AGE
    ]
    assert {item["entity_id"] for item in child_inputs} == children
    assert {item["entity"] for item in child_inputs} == {"Child"}


def test_a_fixture_that_disagrees_with_the_engine_fails(fake_rules_engine, tmp_path):
    binary = fake_rules_engine(PROGRAM, RULES)
    root = _root(tmp_path)
    # The fixture says age 64 is excepted; the engine says it is not.
    with pytest.raises(fe.FixtureDisagreement, match="age_64.*fixture 'holds'"):
        _evaluate(binary, root, [_record("age_64", 64, "holds")])


def test_a_numeric_disagreement_fails(fake_rules_engine, tmp_path):
    binary = fake_rules_engine(PROGRAM, RULES)
    root = _root(tmp_path)
    record = _record("age_40", 40, "not_holds")
    record["output"][AMOUNT] = "41"
    with pytest.raises(fe.FixtureDisagreement, match=r"fixture '41', engine Decimal\('40'\)"):
        _evaluate(binary, root, [record], outputs=(EXCEPTION, AMOUNT))


@settings(
    max_examples=25,
    deadline=None,
    database=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(age=st.integers(min_value=0, max_value=120), recorded=st.booleans())
def test_engine_verdict_is_published_only_when_the_fixture_agrees(
    fake_rules_engine, tmp_path_factory, age, recorded
):
    """For any case, the result is the engine's verdict or a failure.

    The engine's verdict is age >= 65. When the fixture records the same
    verdict the engine's is returned; otherwise the run fails, so neither the
    fixture's nor the engine's value is published.
    """
    binary = fake_rules_engine(PROGRAM, RULES)
    root = _root(tmp_path_factory.mktemp("case"))
    engine_holds = age >= 65
    record = _record("case", age, "holds" if recorded else "not_holds")
    if recorded == engine_holds:
        values = _evaluate(binary, root, [record])
        assert values["case"][EXCEPTION] == ("holds" if engine_holds else "not_holds")
    else:
        with pytest.raises(fe.FixtureDisagreement):
            _evaluate(binary, root, [record])


def test_every_engine_call_is_receipted_and_journaled(
    fake_rules_engine, tmp_path, monkeypatch
):
    binary = fake_rules_engine(PROGRAM, RULES)
    root = _root(tmp_path)
    journal = tmp_path / "journal.json"
    monkeypatch.setenv(ENGINE_RECEIPT_OUTPUT_ENV, str(journal))

    _evaluate(binary, root, [_record("age_66", 66, "holds")])

    recorded = json.loads(journal.read_text())
    assert recorded["commit"] == "a" * 40
    assert recorded["binary_sha256"] == fake_rules_engine.digest


def test_a_changed_executable_is_refused(fake_rules_engine, tmp_path):
    binary = fake_rules_engine(PROGRAM, RULES)
    root = _root(tmp_path)
    with fe.tempfile.TemporaryDirectory() as scratch:
        compiled = fe.compile_module(binary, MODULE, [root], Path(scratch))
        binary.write_text(binary.read_text() + "\n# rebuilt\n")
        with pytest.raises(fe.EngineIdentityError):
            fe.evaluate_case(compiled, _record("age_66", 66, "holds"), [EXCEPTION])


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda r: r.update(tables={"Person": [{}]}), "table rows"),
        (lambda r: r["input"].update(member_age=3), "not an absolute input"),
        (lambda r: r["input"].update({AGE: {"nested": 1}}), "nested mapping"),
        (
            lambda r: r["input"].update({f"{MODULE}#relation.unknown_of_x": []}),
            "declares no relation",
        ),
    ],
)
def test_unsupported_fixture_shapes_fail_closed(
    fake_rules_engine, tmp_path, mutate, message
):
    binary = fake_rules_engine(PROGRAM, RULES)
    root = _root(tmp_path)
    record = _record("age_66", 66, "holds")
    mutate(record)
    with pytest.raises(fe.FixtureEngineError, match=message):
        _evaluate(binary, root, [record])


def test_an_output_the_program_does_not_define_fails(fake_rules_engine, tmp_path):
    binary = fake_rules_engine(PROGRAM, RULES)
    root = _root(tmp_path)
    with pytest.raises(fe.FixtureEngineError, match="does not define"):
        _evaluate(
            binary,
            root,
            [_record("age_66", 66, "holds")],
            outputs=(EXCEPTION, f"{MODULE}#missing"),
        )


@pytest.mark.parametrize(
    "output",
    (f"{MODULE}#removed", f"{MODULE}#household_total"),
    ids=("no_rule", "another_entity"),
)
def test_a_recorded_output_the_engine_did_not_evaluate_fails(
    fake_rules_engine, tmp_path, output
):
    program = {
        **PROGRAM,
        "derived": [
            *PROGRAM["derived"],
            {
                "id": f"{MODULE}#household_total",
                "entity": "Household",
                "expr": {"kind": "input"},
            },
        ],
    }
    binary = fake_rules_engine(program, RULES)
    root = _root(tmp_path)
    record = _record("age_66", 66, "holds")
    record["output"][output] = "999"
    with pytest.raises(fe.FixtureDisagreement, match="evaluated no such output"):
        _evaluate(binary, root, [record])


_RECORDED_OUTPUTS = st.sampled_from((EXCEPTION, COUNT, AMOUNT))


@settings(max_examples=200, deadline=None)
@given(
    recorded=st.dictionaries(
        _RECORDED_OUTPUTS, st.sampled_from(("holds", "not_holds", 1, "2.5"))
    ),
    returned=st.dictionaries(
        _RECORDED_OUTPUTS,
        st.sampled_from(("holds", "not_holds", Decimal(1), Decimal("2.5"))),
    ),
)
def test_agreement_holds_only_when_the_engine_returned_every_recorded_value(
    recorded, returned
):
    agrees = all(
        output in returned and fe.expected_value(raw) == returned[output]
        for output, raw in recorded.items()
    )
    if agrees:
        fe.require_agreement("case", returned, recorded)
    else:
        with pytest.raises(fe.FixtureDisagreement):
            fe.require_agreement("case", returned, recorded)


def test_a_relation_the_program_never_reads_fails_closed(tmp_path):
    program = {
        "relations": [{"name": RELATION, "arity": 2}],
        "derived": [{"id": EXCEPTION, "entity": "Person", "expr": {"kind": "input"}}],
    }
    artifact = tmp_path / "artifact.json"
    artifact.write_text(json.dumps({"program": program}))
    with pytest.raises(fe.FixtureEngineError, match="never reads relation"):
        fe.build_request(_record("c", 30, "not_holds", children=1), artifact, [EXCEPTION])


def test_relation_read_from_slot_zero_reverses_the_tuple(tmp_path):
    program = {
        "relations": [{"name": RELATION, "arity": 2}],
        "derived": [
            {
                "id": COUNT,
                "entity": "Person",
                "expr": {"kind": "count_related", "relation": RELATION, "current_slot": 0},
            }
        ],
    }
    artifact = tmp_path / "artifact.json"
    artifact.write_text(json.dumps({"program": program}))
    request = fe.build_request(_record("c", 30, "not_holds", children=1), artifact, [COUNT])
    [relation] = request["dataset"]["relations"]
    assert relation["tuple"][0] == request["queries"][0]["entity_id"]
