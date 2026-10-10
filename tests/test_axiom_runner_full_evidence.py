"""Full-evidence mode and batch failure isolation in the Axiom runner.

The fixture program has the shape of 26 USC 21: a credit that reads its
creditable expenses only when the claim is allowed, and creditable expenses
whose requirements input is read only on that branch. Before the fix, full
evidence force-queried the untaken branch (a missing input for every unit
whose claim was disallowed), and any one case's engine error failed every
case in its batch. A Case-surface Axiom-vs-PolicyEngine tax run therefore
errored on every tax unit while the same concepts computed against TAXSIM,
whose full-population run is too large to switch full evidence on.

Invariants (property-tested over random batches below):

- Evidence invariance: switching full evidence on never changes any
  compared value or any error.
- Batch independence: a case's result does not depend on its batch-mates
  or the batch size.
- Error attribution: exactly the cases whose taken branch lacks an input
  error, and their messages carry no ``case-<i>::`` batch namespace.
- No forcing: every query asks only for the compared outputs; evidence
  intermediates are exactly the rules the engine evaluated.
- Bounded isolation: a batch with k case-attributed failures costs at most
  2k + 1 engine runs; an error naming no case fails its batch in one run.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner
from axiom_oracles.core.case import Case


PROPERTY_SETTINGS = settings(max_examples=200, deadline=None, derandomize=True)
OUTPUT = "credit"
ABSENT = "absent"

PROGRAM = """\
format: rulespec/v1
module:
  kind: composition
  summary: Guarded-branch fixture for full-evidence runner tests.
rules:
  - name: claim_allowed
    kind: derived
    entity: TaxUnit
    dtype: Judgment
    period: Year
    versions:
      - effective_from: '2026-01-01'
        formula: claim_requirements_met
  - name: creditable_expenses
    kind: derived
    entity: TaxUnit
    dtype: Money
    period: Year
    unit: USD
    versions:
      - effective_from: '2026-01-01'
        formula: |-
          if expense_requirements_satisfied:
              expenses_paid
          else:
              0
  - name: credit
    kind: derived
    entity: TaxUnit
    dtype: Money
    period: Year
    unit: USD
    versions:
      - effective_from: '2026-01-01'
        formula: |-
          if claim_allowed:
              creditable_expenses * 0.2
          else:
              0
"""


@pytest.fixture(autouse=True)
def _isolated_rulespec_roots(monkeypatch, tmp_path):
    monkeypatch.setenv("AXIOM_RULESPEC_ROOT", str(tmp_path / "no-roots"))


def _case(case_id: str, claim: bool, satisfied: bool | str, expenses: int) -> Case:
    inputs: dict[str, object] = {
        "claim_requirements_met": claim,
        "expenses_paid": expenses,
    }
    if satisfied != ABSENT:
        inputs["expense_requirements_satisfied"] = satisfied
    return Case(
        case_id=case_id,
        period="2026",
        metadata={
            "axiom_input_records": [
                {
                    "name": name,
                    "entity": "TaxUnit",
                    "entity_id": "tax_unit",
                    "value": value,
                }
                for name, value in inputs.items()
            ]
        },
    )


def _expected(claim: bool, satisfied: bool | str, expenses: int):
    """Oracle: (credit, evaluated intermediates) or None when the case errors."""

    if not claim:
        return 0.0, {"claim_allowed": False}
    if satisfied == ABSENT:
        return None
    creditable = expenses if satisfied else 0
    return creditable * 0.2, {"claim_allowed": True, "creditable_expenses": creditable}


def _scalar(value):
    if isinstance(value, bool):
        return {"kind": "judgment", "outcome": "holds" if value else "not_holds"}
    return {"kind": "scalar", "value": {"kind": "decimal", "value": str(value)}}


class _GuardedEngine:
    """``run-compiled`` for PROGRAM: queries run in order, each derived rule
    is evaluated lazily and cached per entity, the trace lists what was
    evaluated for the query's entity, and the first error exits non-zero."""

    def __init__(self, *, global_error: str | None = None) -> None:
        self.requests: list[dict] = []
        self.global_error = global_error

    def __call__(self, args, **kwargs):
        request = json.loads(kwargs["input"])
        self.requests.append(request)
        if self.global_error is not None:
            return subprocess.CompletedProcess(
                args, 1, stdout="", stderr=self.global_error
            )
        inputs = {
            (record["entity_id"], record["name"]): record["value"]["value"]
            for record in request["dataset"]["inputs"]
        }
        results = []
        for query in request["queries"]:
            entity_id = query["entity_id"]
            cache: dict[str, object] = {}

            def read(name: str, entity_id: str = entity_id):
                if (entity_id, name) not in inputs:
                    raise LookupError(
                        f"missing input `{name}` for entity `{entity_id}` "
                        "over 2026-01-01..2026-12-31"
                    )
                return inputs[(entity_id, name)]

            def evaluate(name: str, cache: dict = cache, read=read):
                if name not in cache:
                    if name == "claim_allowed":
                        cache[name] = bool(read("claim_requirements_met"))
                    elif name == "creditable_expenses":
                        cache[name] = (
                            read("expenses_paid")
                            if read("expense_requirements_satisfied")
                            else 0
                        )
                    elif name == "credit":
                        cache[name] = (
                            evaluate("creditable_expenses") * 0.2
                            if evaluate("claim_allowed")
                            else 0.0
                        )
                    else:
                        raise LookupError(f"unknown derived output `{name}`")
                return cache[name]

            try:
                outputs = {name: _scalar(evaluate(name)) for name in query["outputs"]}
            except LookupError as error:
                return subprocess.CompletedProcess(
                    args, 1, stdout="", stderr=str(error)
                )
            results.append(
                {
                    "entity_id": entity_id,
                    "outputs": outputs,
                    "trace": {name: _scalar(value) for name, value in cache.items()},
                }
            )
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=json.dumps(
                {"metadata": {"actual_mode": "explain"}, "results": results}
            ),
            stderr="",
        )


def _artifact(tmp_path: Path) -> Path:
    path = tmp_path / "program.compiled.json"
    path.write_text(
        json.dumps(
            {
                "program": {
                    "derived": [
                        {"name": "claim_allowed", "entity": "TaxUnit"},
                        {"name": "creditable_expenses", "entity": "TaxUnit"},
                        {"name": "credit", "entity": "TaxUnit"},
                    ]
                }
            }
        )
    )
    return path


def _runner(artifact: Path, engine, *, full_evidence: bool, batch_size: int = 5_000):
    return AxiomRulesRunner(
        compiled_artifact_path=artifact,
        binary_path=artifact.parent / "axiom-rules-engine",
        record_all_outputs=full_evidence,
        batch_size=batch_size,
        subprocess_run=engine,
    )


CASE_SPECS = st.lists(
    st.tuples(
        st.booleans(),
        st.sampled_from([True, False, ABSENT]),
        st.integers(min_value=0, max_value=20_000),
    ),
    min_size=1,
    max_size=24,
)


@PROPERTY_SETTINGS
@given(specs=CASE_SPECS, batch_size=st.integers(min_value=1, max_value=30))
def test_full_evidence_and_isolation_invariants(tmp_path_factory, specs, batch_size):
    artifact = _artifact(tmp_path_factory.mktemp("artifact"))
    cases = [_case(f"case-{i}", *spec) for i, spec in enumerate(specs)]

    by_mode = {}
    for full_evidence in (False, True):
        engine = _GuardedEngine()
        results = _runner(
            artifact, engine, full_evidence=full_evidence, batch_size=batch_size
        ).run_cases(cases, [OUTPUT])
        by_mode[full_evidence] = results

        # No forcing: every query names only the compared output.
        assert all(
            query["outputs"] == [OUTPUT]
            for request in engine.requests
            for query in request["queries"]
        )
        # Bounded isolation, per batch chunk: <= 2k + 1 runs.
        failing = sum(_expected(*spec) is None for spec in specs)
        chunks = -(-len(cases) // batch_size)
        assert len(engine.requests) <= 2 * failing + chunks

        for spec, result in zip(specs, results, strict=True):
            expected = _expected(*spec)
            if expected is None:
                assert result.values == {}
                assert len(result.errors) == 1
                assert (
                    "missing input `expense_requirements_satisfied`" in result.errors[0]
                )
                assert "case-" not in result.errors[0]
                continue
            credit, intermediates = expected
            assert result.errors == ()
            assert result.values[OUTPUT] == pytest.approx(credit)
            if full_evidence:
                # Evidence is exactly what the engine evaluated.
                assert set(result.values) == {OUTPUT, *intermediates}
                for name, value in intermediates.items():
                    assert result.values[name] == value
            else:
                assert set(result.values) == {OUTPUT}

    # Evidence invariance: compared values and errors do not move.
    for without, with_evidence in zip(by_mode[False], by_mode[True], strict=True):
        assert with_evidence.errors == without.errors
        assert with_evidence.values.get(OUTPUT) == without.values.get(OUTPUT)

    # Batch independence: each case matches its own single-case run.
    for case, batched in zip(cases, by_mode[True], strict=True):
        [alone] = _runner(artifact, _GuardedEngine(), full_evidence=True).run_cases(
            [case], [OUTPUT]
        )
        assert alone.values == batched.values
        assert alone.errors == batched.errors


def test_untaken_branch_input_no_longer_fails_the_batch(tmp_path):
    """The co-state-income-tax-ecps regression: a disallowed claim's missing
    expense-requirements input is never read, with or without evidence."""

    artifact = _artifact(tmp_path)
    cases = [
        _case("claims", True, True, 1_000),
        _case("disallowed", False, ABSENT, 500),
    ]
    engine = _GuardedEngine()
    claims, disallowed = _runner(artifact, engine, full_evidence=True).run_cases(
        cases, [OUTPUT]
    )

    assert len(engine.requests) == 1
    assert claims.errors == disallowed.errors == ()
    assert claims.values == {
        OUTPUT: 200.0,
        "claim_allowed": True,
        "creditable_expenses": 1_000.0,
    }
    assert disallowed.values == {OUTPUT: 0.0, "claim_allowed": False}


def test_case_specific_error_stays_on_its_case(tmp_path):
    artifact = _artifact(tmp_path)
    cases = [_case(f"unit-{i}", True, True, 100 * i) for i in range(7)]
    cases[4] = _case("unit-4", True, ABSENT, 400)
    engine = _GuardedEngine()

    results = _runner(artifact, engine, full_evidence=False).run_cases(cases, [OUTPUT])

    assert [bool(result.errors) for result in results] == [
        False,
        False,
        False,
        False,
        True,
        False,
        False,
    ]
    assert results[4].errors == (
        "missing input `expense_requirements_satisfied` for entity `tax_unit` "
        "over 2026-01-01..2026-12-31",
    )
    assert [result.values.get(OUTPUT) for result in results] == [
        pytest.approx(20.0 * i) if i != 4 else None for i in range(7)
    ]
    # One failed run attributes unit-4, then the two halves succeed.
    assert len(engine.requests) == 3


def test_error_naming_no_case_fails_the_batch_in_one_run(tmp_path):
    artifact = _artifact(tmp_path)
    cases = [_case(f"unit-{i}", True, True, 100) for i in range(50)]
    error = (
        "dataset input `expenses_paid` must use an absolute legal RuleSpec reference"
    )
    engine = _GuardedEngine(global_error=error)

    results = _runner(artifact, engine, full_evidence=True).run_cases(cases, [OUTPUT])

    assert len(engine.requests) == 1
    assert all(result.errors == (error,) for result in results)


ENGINE_BINARY = os.environ.get("AXIOM_RULES_ENGINE_BINARY")


@pytest.mark.skipif(
    not (ENGINE_BINARY and Path(ENGINE_BINARY).is_file()),
    reason="AXIOM_RULES_ENGINE_BINARY not set to a built axiom-rules-engine",
)
def test_real_engine_matches_the_fake(tmp_path):
    """Differential check: the real engine's explain trace and error text
    behave as _GuardedEngine models them (verified on 0c39023e)."""

    program = tmp_path / "program.yaml"
    program.write_text(PROGRAM)
    artifact = tmp_path / "program.compiled.json"
    subprocess.run(
        [
            ENGINE_BINARY,
            "compile",
            "--program",
            str(program),
            "--output",
            str(artifact),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    specs = [
        (True, True, 1_000),
        (False, ABSENT, 500),
        (True, ABSENT, 700),
        (True, False, 900),
        (False, True, 300),
    ]
    cases = [_case(f"unit-{i}", *spec) for i, spec in enumerate(specs)]
    for full_evidence in (False, True):
        real = AxiomRulesRunner(
            compiled_artifact_path=artifact,
            binary_path=ENGINE_BINARY,
            record_all_outputs=full_evidence,
        ).run_cases(cases, [OUTPUT])
        fake_dir = tmp_path / f"fake-{full_evidence}"
        fake_dir.mkdir()
        fake = _runner(
            _artifact(fake_dir),
            _GuardedEngine(),
            full_evidence=full_evidence,
        ).run_cases(cases, [OUTPUT])
        for real_result, fake_result in zip(real, fake, strict=True):
            assert real_result.errors == fake_result.errors
            assert set(real_result.values) == set(fake_result.values)
            for name, value in fake_result.values.items():
                assert real_result.values[name] == pytest.approx(value)
