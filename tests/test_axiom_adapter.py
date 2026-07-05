import json
import subprocess
from pathlib import Path

import yaml

from axiom_oracles.adapters.axiom import (
    AxiomRulesRunner,
    US_TAX_ORACLE_BRIDGE_TARGET,
    US_TAX_ORACLE_IMPORTS,
    US_TAX_ORACLE_PROGRAM_RULES,
    attach_axiom_snap_co_inputs,
)
from axiom_oracles.adapters.axiom.runner import _scalar_value
from axiom_oracles.cli import _build_runner
from axiom_oracles.comparison.mappings import comparable_mappings, load_program_mappings
from axiom_oracles.core.case import Case, Concepts, Entity


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
                "entity_id": "case-0::tax_unit",
                "interval": {"start": "2026-01-01", "end": "2026-12-31"},
                "value": {"kind": "integer", "value": 1000},
            },
            {
                "name": "us:statutes/26/6401#input.eitc",
                "entity": "TaxUnit",
                "entity_id": "case-0::tax_unit",
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


def test_axiom_runner_aliases_unique_local_output_to_qualified_id(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "program.compiled.json"
    artifact_path.write_text(
        json.dumps(
            {
                "program": {
                    "derived": [
                        {
                            "id": "us-co:policies/cdhs/snap/fy-2026-benefit-calculation#snap_eligible",
                            "name": "snap_eligible",
                        }
                    ]
                }
            }
        )
    )

    def fake_run(args, **kwargs):
        request = json.loads(kwargs["input"])
        assert request["queries"][0]["outputs"] == [
            "us-co:policies/cdhs/snap/fy-2026-benefit-calculation#snap_eligible"
        ]
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=json.dumps(
                {
                    "results": [
                        {
                            "outputs": {
                                "us-co:policies/cdhs/snap/fy-2026-benefit-calculation#snap_eligible": {
                                    "kind": "judgment",
                                    "outcome": "not_holds",
                                }
                            }
                        }
                    ]
                }
            ),
            stderr="",
        )

    runner = AxiomRulesRunner(
        compiled_artifact_path=artifact_path,
        binary_path=tmp_path / "axiom-rules",
        subprocess_run=fake_run,
    )

    [result] = runner.run_cases(
        [Case(case_id="case-1", period="2026-01")],
        ["snap_eligible"],
    )

    assert result.errors == ()
    assert result.values["snap_eligible"] is False


def test_axiom_runner_accepts_explicit_input_records(tmp_path: Path) -> None:
    def fake_run(args, **kwargs):
        if args[1] == "compile":
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        request = json.loads(kwargs["input"])
        assert request["dataset"]["inputs"] == [
            {
                "name": "us:statutes/26/63#input.age",
                "entity": "Person",
                "entity_id": "case-0::person-1",
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


def test_snap_co_projection_uses_repaired_colorado_income_surface() -> None:
    [case] = attach_axiom_snap_co_inputs(
        [
            Case(
                case_id="co-snap",
                period="2026-01",
                entities=(
                    Entity(
                        entity_id="person-1",
                        kind="person",
                        facts={Concepts.YEARLY_EARNED_INCOME: 30_000},
                    ),
                ),
            )
        ]
    )

    records = {
        record["name"]: record["value"]
        for record in case.metadata["axiom_input_records"]
        if record["entity"] == "Household"
    }

    assert "us:regulations/7-cfr/273/9#input.snap_gross_monthly_income" not in records
    assert (
        "us:statutes/7/2014/e/6/A#input.snap_monthly_household_income"
        not in records
    )
    assert (
        "us:regulations/7-cfr/273/10#input.snap_gross_monthly_earned_income"
        not in records
    )
    assert (
        records[
            "us-co:regulations/10-ccr-2506-1/4.403#input."
            "employee_wages_received"
        ]
        == 2500
    )
    relation_names = {
        relation["name"] for relation in case.metadata["axiom_relations"]
    }
    assert "us:statutes/7/2012/j#relation.member_of_household" in relation_names
    assert "member_of_household" in relation_names
    member_records = {
        record["name"]: record["value"]
        for record in case.metadata["axiom_input_records"]
        if record["entity"] == "Person"
    }
    assert (
        member_records[
            "us:regulations/7-cfr/273/6#input."
            "member_refused_or_failed_to_provide_or_apply_for_ssn"
        ]
        is False
    )


def test_axiom_runner_serializes_float_inputs_without_exponents() -> None:
    assert _scalar_value(-1.232816068197709e-13) == {
        "kind": "decimal",
        "value": "0",
    }
    assert _scalar_value(123.450000) == {
        "kind": "decimal",
        "value": "123.45",
    }
    assert _scalar_value(1.2e6) == {
        "kind": "decimal",
        "value": "1200000",
    }


def test_axiom_runner_selects_best_input_overlay_candidate(tmp_path: Path) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args[1] == "compile":
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        request = json.loads(kwargs["input"])
        itemization_records = [
            record
            for record in request["dataset"]["inputs"]
            if record["name"]
            == "us:statutes/26/63#input."
            "individual_makes_election_to_itemize_deductions_for_taxable_year"
        ]
        assert len(itemization_records) == 1
        itemizes = itemization_records[0]["value"]["value"]
        income_tax = 400 if itemizes else 500
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=json.dumps(
                {
                    "results": [
                        {
                            "outputs": {
                                "us:statutes/26/6401#income_tax": {
                                    "kind": "scalar",
                                    "value": {
                                        "kind": "decimal",
                                        "value": str(income_tax),
                                    },
                                }
                            }
                        }
                    ]
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
            "axiom_input_records": [
                {
                    "name": "us:statutes/26/63#input."
                    "individual_makes_election_to_itemize_deductions_for_taxable_year",
                    "entity": "TaxUnit",
                    "entity_id": "tax_unit",
                    "value": False,
                }
            ],
            "axiom_input_record_overlays": [
                [
                    {
                        "name": "us:statutes/26/63#input."
                        "individual_makes_election_to_itemize_deductions_for_taxable_year",
                        "entity": "TaxUnit",
                        "entity_id": "tax_unit",
                        "value": False,
                    }
                ],
                [
                    {
                        "name": "us:statutes/26/63#input."
                        "individual_makes_election_to_itemize_deductions_for_taxable_year",
                        "entity": "TaxUnit",
                        "entity_id": "tax_unit",
                        "value": True,
                    }
                ],
            ],
            "axiom_result_selection": {
                "strategy": "min",
                "output": "us:statutes/26/6401#income_tax",
            },
        },
    )

    [result] = runner.run_cases([case], [Concepts.FEDERAL_INCOME_TAX])

    assert [call[0][1] for call in calls] == [
        "compile",
        "run-compiled",
        "run-compiled",
    ]
    assert result.errors == ()
    assert result.values == {"us:statutes/26/6401#income_tax": 400.0}
    assert result.raw["selected_candidate"] == 1


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


def test_axiom_runner_can_prune_inputs_not_consumed_by_generated_program(
    tmp_path: Path,
) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args[1] == "compile":
            output_path = Path(args[args.index("--output") + 1])
            output_path.write_text(
                json.dumps(
                    {
                        "program": {
                            "derived": [
                                {
                                    "id": "us:statutes/26/example#tax",
                                    "name": "tax",
                                    "expr": {
                                        "kind": "input",
                                        "name": "allowed_amount",
                                    },
                                }
                            ],
                            "parameters": [],
                            "relations": [
                                {
                                    "name": "us:statutes/26/example#relation.allowed_relation",
                                    "arity": 2,
                                }
                            ],
                        },
                        "metadata": {},
                    }
                )
            )
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        request = json.loads(kwargs["input"])
        assert request["dataset"]["inputs"] == [
            {
                "name": "us:tax/federal-income-tax#input.allowed_amount",
                "entity": "TaxUnit",
                "entity_id": "case-0::tax_unit",
                "interval": {"start": "2026-01-01", "end": "2026-12-31"},
                "value": {"kind": "integer", "value": 100},
            }
        ]
        assert request["dataset"]["relations"] == [
            {
                "name": "us:statutes/26/example#relation.allowed_relation",
                "tuple": ["case-0::person-1", "case-0::tax_unit"],
                "interval": {"start": "2026-01-01", "end": "2026-12-31"},
            }
        ]
        assert request["queries"] == [
            {
                "entity_id": "case-0::tax_unit",
                "period": {
                    "period_kind": "tax_year",
                    "start": "2026-01-01",
                    "end": "2026-12-31",
                    "name": "2026",
                },
                "outputs": ["us:statutes/26/example#tax"],
            }
        ]
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=json.dumps(
                {
                    "results": [
                        {
                            "outputs": {
                                "us:statutes/26/example#tax": {
                                    "kind": "scalar",
                                    "value": {
                                        "kind": "integer",
                                        "value": 100,
                                    },
                                }
                            }
                        }
                    ]
                }
            ),
            stderr="",
        )

    runner = AxiomRulesRunner(
        program_path=tmp_path / "program.yaml",
        binary_path=tmp_path / "axiom-rules",
        prune_unsupported_inputs=True,
        subprocess_run=fake_run,
    )
    case = Case(
        case_id="case-1",
        period="2026",
        metadata={
            "axiom_input_records": [
                {
                    "name": "us:tax/federal-income-tax#input.allowed_amount",
                    "entity": "TaxUnit",
                    "entity_id": "tax_unit",
                    "value": 100,
                },
                {
                    "name": "us:tax/federal-income-tax#input.not_yet_encoded",
                    "entity": "TaxUnit",
                    "entity_id": "tax_unit",
                    "value": 200,
                },
            ],
            "axiom_relations": [
                {
                    "name": "us:statutes/26/example#relation.allowed_relation",
                    "tuple": ["person-1", "tax_unit"],
                },
                {
                    "name": "us:statutes/26/example#relation.not_yet_encoded",
                    "tuple": ["person-2", "tax_unit"],
                },
            ],
        },
    )

    [result] = runner.run_cases(
        [case],
        [
            "us:statutes/26/example#tax",
            "us:statutes/26/example#not_yet_encoded",
        ],
    )

    assert result.errors == ()
    assert result.values == {"us:statutes/26/example#tax": 100}
    assert [call[0][1] for call in calls] == ["compile", "run-compiled"]


def test_axiom_runner_writes_generated_program_rules(tmp_path: Path) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args[1] == "compile":
            program_path = Path(args[args.index("--program") + 1])
            program = yaml.safe_load(program_path.read_text())
            assert program == {
                "format": "rulespec/v1",
                "imports": ["us:statutes/26/example"],
                "rules": [
                    {
                        "name": "bridge_amount",
                        "kind": "derived",
                        "entity": "TaxUnit",
                        "dtype": "Money",
                        "period": "Year",
                        "unit": "USD",
                        "source": "test bridge",
                        "versions": [
                            {
                                "effective_from": "2026-01-01",
                                "formula": "upstream_amount",
                            }
                        ],
                    }
                ],
            }
            output_path = Path(args[args.index("--output") + 1])
            output_path.write_text(
                json.dumps(
                    {
                        "program": {
                            "derived": [
                                {
                                    "id": "us:statutes/26/example#tax",
                                    "name": "tax",
                                    "expr": {"kind": "integer", "value": 0},
                                }
                            ],
                            "parameters": [],
                            "relations": [],
                        },
                        "metadata": {},
                    }
                )
            )
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=json.dumps(
                {
                    "results": [
                        {
                            "outputs": {
                                "us:statutes/26/example#tax": {
                                    "kind": "scalar",
                                    "value": {
                                        "kind": "integer",
                                        "value": 0,
                                    },
                                }
                            }
                        }
                    ]
                }
            ),
            stderr="",
        )

    runner = AxiomRulesRunner(
        binary_path=tmp_path / "axiom-rules",
        program_imports=("us:statutes/26/example",),
        program_rules=(
            {
                "name": "bridge_amount",
                "kind": "derived",
                "entity": "TaxUnit",
                "dtype": "Money",
                "period": "Year",
                "unit": "USD",
                "source": "test bridge",
                "versions": [
                    {
                        "effective_from": "2026-01-01",
                        "formula": "upstream_amount",
                    }
                ],
            },
        ),
        subprocess_run=fake_run,
    )

    [result] = runner.run_cases(
        [Case(case_id="case-1", period="2026")],
        ["us:statutes/26/example#tax"],
    )

    assert result.errors == ()
    assert [call[0][1] for call in calls] == ["compile", "run-compiled"]


def test_axiom_runner_writes_generated_program_under_canonical_target(
    tmp_path: Path,
) -> None:
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args[1] == "compile":
            program_path = Path(args[args.index("--program") + 1])
            assert program_path.parts[-3:] == (
                "rulespec-us",
                "tax",
                "oracle-bridge.yaml",
            )
            output_path = Path(args[args.index("--output") + 1])
            output_path.write_text(
                json.dumps(
                    {
                        "program": {
                            "derived": [
                                {
                                    "id": (
                                        "us:tax/oracle-bridge"
                                        "#taxable_income"
                                    ),
                                    "name": "taxable_income",
                                    "expr": {"kind": "integer", "value": 0},
                                }
                            ],
                            "parameters": [],
                            "relations": [],
                        },
                        "metadata": {},
                    }
                )
            )
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        request = json.loads(kwargs["input"])
        assert request["queries"][0]["outputs"] == [
            "us:tax/oracle-bridge#taxable_income"
        ]
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=json.dumps(
                {
                    "results": [
                        {
                            "outputs": {
                                "us:tax/oracle-bridge#taxable_income": {
                                    "kind": "scalar",
                                    "value": {
                                        "kind": "integer",
                                        "value": 0,
                                    },
                                }
                            }
                        }
                    ]
                }
            ),
            stderr="",
        )

    runner = AxiomRulesRunner(
        binary_path=tmp_path / "axiom-rules",
        program_imports=("us:statutes/26/example",),
        program_rules=(
            {
                "name": "taxable_income",
                "kind": "derived",
                "entity": "TaxUnit",
                "dtype": "Money",
                "period": "Year",
                "unit": "USD",
                "source": "test bridge",
                "versions": [
                    {
                        "effective_from": "2026-01-01",
                        "formula": "0",
                    }
                ],
            },
        ),
        generated_program_target=US_TAX_ORACLE_BRIDGE_TARGET,
        subprocess_run=fake_run,
    )

    [result] = runner.run_cases(
        [Case(case_id="case-1", period="2026")],
        ["us:tax/oracle-bridge#taxable_income"],
    )

    assert result.errors == ()
    assert result.values == {
        "us:tax/oracle-bridge#taxable_income": 0
    }
    assert [call[0][1] for call in calls] == ["compile", "run-compiled"]


def test_axiom_tax_concept_is_comparable_to_policyengine() -> None:
    concept_ids = {
        mapping.concept_id
        for mapping in comparable_mappings(
            "axiom",
            "policyengine",
            categories={"tax"},
            include_components=True,
        )
    }

    # FIT liability plus its explicit decomposed comparison targets.
    assert Concepts.FEDERAL_INCOME_TAX in concept_ids
    assert Concepts.STANDARD_DEDUCTION in concept_ids
    assert Concepts.TAXABLE_INCOME in concept_ids
    assert Concepts.TAX_BEFORE_CREDITS in concept_ids
    assert Concepts.EITC in concept_ids
    assert Concepts.AMT in concept_ids
    assert Concepts.CTC in concept_ids


def test_federal_ctc_component_maps_to_total_ctc_value() -> None:
    mapping = next(
        mapping
        for mapping in load_program_mappings()
        if mapping.concept_id == Concepts.CTC
    )

    assert mapping.targets["axiom"] == "us:tax/oracle-bridge#ctc_value"
    assert mapping.targets["policyengine"] == "ctc_value"


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
    assert "us:statutes/26/1411" not in runner.program_imports
    assert "us:statutes/26/164/f" not in runner.program_imports
    assert "us:statutes/26/1401" not in runner.program_imports
    assert "us:statutes/26/1402/a" not in runner.program_imports
    assert runner.program_rules == US_TAX_ORACLE_PROGRAM_RULES
    assert runner.generated_program_target == US_TAX_ORACLE_BRIDGE_TARGET
    assert runner.prune_unsupported_inputs
    assert (
        "us:policies/irs/rev-proc-2025-32/standard-deduction"
        in US_TAX_ORACLE_IMPORTS
    )
    assert "us:statutes/26/86" in US_TAX_ORACLE_IMPORTS
    assert "us:statutes/26/1402/a" in US_TAX_ORACLE_IMPORTS
    assert "us:statutes/26/164/f" in US_TAX_ORACLE_IMPORTS
    generated_rule_names = {
        rule["name"] for rule in US_TAX_ORACLE_PROGRAM_RULES
    }
    generated_rules_by_name = {
        rule["name"]: rule for rule in US_TAX_ORACLE_PROGRAM_RULES
    }
    assert "self_employment_income" not in generated_rule_names
    assert "self_employment_oasdi_tax_rate" in generated_rule_names
    assert "self_employment_hospital_insurance_tax_rate" in generated_rule_names
    assert "self_employment_tax_deduction_fraction" in generated_rule_names
    assert "self_employment_tax_equivalent_deduction_fraction" in generated_rule_names
    assert "self_employment_1401_taxes" in generated_rule_names
    assert "self_employment_tax_ald" in generated_rule_names
    assert (
        "net_earnings_from_self_employment_after_self_employment_tax_deduction"
        in generated_rule_names
    )
    assert "taxable_earned_income_under_section_32" in generated_rule_names
    assert "eitc_relevant_investment_income" in generated_rule_names
    assert "earned_income" not in generated_rule_names
    assert (
        generated_rules_by_name["eitc_relevant_investment_income"]["versions"][0][
            "formula"
        ]
        == "filer_taxable_interest_income + tax_exempt_interest_received_or_accrued + filer_dividend_income + max(0, filer_short_term_capital_gains + filer_long_term_capital_gains) + max(0, filer_rental_income)"
    )
    assert "sum_where(business_income_of_tax_unit" in (
        generated_rules_by_name["self_employment_1401_taxes"]["versions"][0][
            "formula"
        ]
    )
    assert "additional_senior_deduction" in generated_rule_names
    assert "additional_senior_deduction_magi" in generated_rule_names
    assert "ctc_value" in generated_rule_names
    assert (
        generated_rules_by_name["ctc_value"]["versions"][0]["formula"]
        == "non_refundable_ctc + refundable_ctc"
    )
    assert "ctc_refundable_child_amount" in (
        generated_rules_by_name["ctc_refundable_cap"]["versions"][0]["formula"]
    )
    assert "business_income_of_tax_unit" in generated_rule_names
    assert "business_income_for_qbid" in generated_rule_names
    assert "person_adjusted_earnings_for_eitc" in generated_rule_names
    assert (
        "person_net_earnings_from_self_employment_after_self_employment_tax_deduction"
        in generated_rule_names
    )
    assert "qualified_business_income_deduction_phaseout_rate" in generated_rule_names
    assert "qualified_business_income_deduction" in generated_rule_names
    assert "state_income_tax" in generated_rule_names
    assert "state_withheld_income_tax" in generated_rule_names


def test_cli_builds_generated_tax_axiom_runner_for_state_income_tax() -> None:
    runner = _build_runner(
        "axiom",
        "api",
        None,
        None,
        (Concepts.STATE_INCOME_TAX,),
        axiom_program=None,
        axiom_engine_binary=Path("/tmp/axiom-rules"),
    )

    assert isinstance(runner, AxiomRulesRunner)
    assert runner.program_imports
    assert "us:statutes/26/1411" not in runner.program_imports
    assert "us:statutes/26/164/f" not in runner.program_imports
    assert "us:statutes/26/1401" not in runner.program_imports
    assert "us:statutes/26/1402/a" not in runner.program_imports
    assert set(runner.program_imports).issubset(set(US_TAX_ORACLE_IMPORTS))
    assert runner.program_rules == US_TAX_ORACLE_PROGRAM_RULES
    assert runner.generated_program_target == US_TAX_ORACLE_BRIDGE_TARGET
    generated_rule_names = {
        rule["name"] for rule in runner.program_rules
    }
    generated_rules_by_name = {
        rule["name"]: rule for rule in runner.program_rules
    }
    assert "self_employment_income" not in generated_rule_names
    assert "sum_where(filer_adjusted_earnings_of_tax_unit" in (
        generated_rules_by_name["taxable_earned_income_under_section_32"]["versions"][
            0
        ]["formula"]
    )
    assert "qualified_business_income_deduction_phaseout_rate" in (
        generated_rules_by_name["qualified_business_income_deduction_before_floor"][
            "versions"
        ][0]["formula"]
    )
    assert "sum_where(business_income_of_tax_unit" in (
        generated_rules_by_name["qualified_business_income"]["versions"][0]["formula"]
    )
    assert "amt_part_iii_required" in generated_rule_names
    assert "amt_tax_including_capital_gains" in generated_rule_names
    assert "alaska_permanent_fund_dividend" in generated_rule_names
    assert "alaska_permanent_fund_dividend_amount" in generated_rule_names
    assert "capital_gains_worksheet_line_10" in generated_rule_names
    assert "capital_gains_worksheet_line_13" in generated_rule_names
    assert "capital_gains_worksheet_line_14" in generated_rule_names
    assert "capital_gains_worksheet_line_19" in generated_rule_names
    assert "capital_gains_tax_qualified_dividend_income" in (
        generated_rules_by_name["capital_gains_worksheet_line_10"]["versions"][0][
            "formula"
        ]
    )
    assert "capital_gains_worksheet_line_10 > 0" in (
        generated_rules_by_name["amt_part_iii_required"]["versions"][0]["formula"]
    )
    assert "amt_capital_gain_line_31_tax" in (
        generated_rules_by_name["amt_tax_including_capital_gains"]["versions"][0][
            "formula"
        ]
    )
    assert (
        "taxable_net_gain_from_dispositions_after_active_partnership_s_corporation_exception"
        in generated_rule_names
    )
    assert (
        generated_rules_by_name[
            "taxable_net_gain_from_dispositions_after_active_partnership_s_corporation_exception"
        ]["versions"][0]["formula"]
        == "capital_gains_tax_short_term_capital_gains + capital_gains_tax_long_term_capital_gains"
    )
    assert "deduction_provided_in_section_199A" in generated_rule_names
    assert "us:statutes/26/24/d" not in US_TAX_ORACLE_IMPORTS
    assert "us:statutes/26/63" not in US_TAX_ORACLE_IMPORTS
