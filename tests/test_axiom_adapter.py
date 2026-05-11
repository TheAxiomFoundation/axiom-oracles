import json
import subprocess
from pathlib import Path

from axiom_oracles.adapters.axiom import AxiomRulesRunner
from axiom_oracles.cli import _build_runner
from axiom_oracles.comparison.mappings import comparable_mappings
from axiom_oracles.core.case import Case, Concepts


def test_axiom_runner_executes_rulespec_program_with_case_inputs(tmp_path: Path) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args[1] == "compile":
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        request = json.loads(kwargs["input"])
        assert request["queries"][0]["outputs"] == [
            "us:statutes/26/6401#income_tax"
        ]
        assert request["queries"][0]["period"]["period_kind"] == "tax_year"
        assert request["dataset"]["inputs"] == [
            {
                "name": "us:statutes/26/6401#input.income_tax_before_refundable_credits",
                "entity": "TaxUnit",
                "entity_id": "tax_unit",
                "interval": {"start": "2026-01-01", "end": "2026-12-31"},
                "value": {"kind": "integer", "value": 1000},
            },
            {
                "name": "us:statutes/26/6401#input.eitc",
                "entity": "TaxUnit",
                "entity_id": "tax_unit",
                "interval": {"start": "2026-01-01", "end": "2026-12-31"},
                "value": {"kind": "integer", "value": 250},
            },
        ]
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=json.dumps(
                {
                    "metadata": {
                        "requested_mode": "explain",
                        "actual_mode": "explain",
                    },
                    "results": [
                        {
                            "entity_id": "tax_unit",
                            "period": request["queries"][0]["period"],
                            "outputs": {
                                "us:statutes/26/6401#income_tax": {
                                    "kind": "scalar",
                                    "name": "income_tax",
                                    "id": "us:statutes/26/6401#income_tax",
                                    "dtype": "decimal",
                                    "unit": "USD",
                                    "value": {
                                        "kind": "decimal",
                                        "value": "750",
                                    },
                                }
                            },
                        }
                    ],
                }
            ),
            stderr="",
        )

    runner = AxiomRulesRunner(
        program_path=tmp_path / "program.yaml",
        binary_path=tmp_path / "axiom-rules",
        subprocess_run=fake_run,
    )
    case = Case(
        case_id="case-1",
        period="2026",
        metadata={
            "axiom_inputs": {
                "us:statutes/26/6401#input.income_tax_before_refundable_credits": 1000
            }
        },
        facts={"us:statutes/26/6401#input.eitc": 250},
    )

    [result] = runner.run_cases([case], [Concepts.FEDERAL_INCOME_TAX])

    assert calls[0][0][1] == "compile"
    assert calls[1][0][1] == "run-compiled"
    assert result.errors == ()
    assert result.values == {"us:statutes/26/6401#income_tax": 750.0}


def test_axiom_runner_accepts_explicit_input_records(tmp_path: Path) -> None:
    def fake_run(args, **kwargs):
        if args[1] == "compile":
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        request = json.loads(kwargs["input"])
        assert request["dataset"]["inputs"] == [
            {
                "name": "us:statutes/26/63#input.age",
                "entity": "Person",
                "entity_id": "person-1",
                "value": {"kind": "integer", "value": 70},
                "interval": {"start": "2026-01-01", "end": "2026-12-31"},
            }
        ]
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=json.dumps({"results": [{"outputs": {}}]}),
            stderr="",
        )

    runner = AxiomRulesRunner(
        program_path=tmp_path / "program.yaml",
        binary_path=tmp_path / "axiom-rules",
        subprocess_run=fake_run,
    )
    case = Case(
        case_id="case-1",
        period="2026",
        metadata={
            "axiom_input_records": [
                {
                    "name": "us:statutes/26/63#input.age",
                    "entity": "Person",
                    "entity_id": "person-1",
                    "value": 70,
                }
            ]
        },
    )

    [result] = runner.run_cases([case], [])

    assert result.errors == ()


def test_axiom_runner_records_execution_errors_per_case(tmp_path: Path) -> None:
    def fake_run(args, **kwargs):
        del kwargs
        if args[1] == "compile":
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(
            args,
            1,
            stdout="",
            stderr="missing input `adjusted_gross_income`",
        )

    runner = AxiomRulesRunner(
        program_path=tmp_path / "program.yaml",
        binary_path=tmp_path / "axiom-rules",
        subprocess_run=fake_run,
    )

    [result] = runner.run_cases(
        [Case(case_id="case-1", period="2026")],
        [Concepts.FEDERAL_INCOME_TAX],
    )

    assert result.values == {}
    assert result.errors == ("missing input `adjusted_gross_income`",)


def test_axiom_tax_concept_is_comparable_to_policyengine() -> None:
    concept_ids = {
        mapping.concept_id
        for mapping in comparable_mappings(
            "axiom",
            "policyengine",
            categories={"tax"},
        )
    }

    assert concept_ids == {Concepts.FEDERAL_INCOME_TAX}


def test_cli_builds_axiom_runner() -> None:
    runner = _build_runner(
        "axiom",
        "api",
        None,
        None,
        (),
        axiom_program=Path("/tmp/program.yaml"),
        axiom_engine_binary=Path("/tmp/axiom-rules"),
    )

    assert isinstance(runner, AxiomRulesRunner)


def test_cli_builds_generated_federal_tax_axiom_runner() -> None:
    runner = _build_runner(
        "axiom",
        "api",
        None,
        None,
        (Concepts.FEDERAL_INCOME_TAX,),
        axiom_program=None,
        axiom_engine_binary=Path("/tmp/axiom-rules"),
    )

    assert isinstance(runner, AxiomRulesRunner)
    assert runner.program_imports
