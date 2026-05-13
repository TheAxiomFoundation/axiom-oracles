import json
import subprocess
from pathlib import Path

import yaml

from axiom_oracles.adapters.axiom import (
    AxiomRulesRunner,
    US_FEDERAL_INCOME_TAX_BRIDGE_TARGET,
    US_FEDERAL_INCOME_TAX_IMPORTS,
    US_FEDERAL_INCOME_TAX_PROGRAM_RULES,
)
from axiom_oracles.cli import _build_runner
from axiom_oracles.comparison.mappings import comparable_mappings, load_program_mappings
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
            assert program_path.parts[-4:] == (
                "rulespec-us",
                "tax",
                "federal-income-tax",
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
                                        "us:tax/federal-income-tax/oracle-bridge"
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
            "us:tax/federal-income-tax/oracle-bridge#taxable_income"
        ]
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=json.dumps(
                {
                    "results": [
                        {
                            "outputs": {
                                "us:tax/federal-income-tax/oracle-bridge#taxable_income": {
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
        generated_program_target=US_FEDERAL_INCOME_TAX_BRIDGE_TARGET,
        subprocess_run=fake_run,
    )

    [result] = runner.run_cases(
        [Case(case_id="case-1", period="2026")],
        ["us:tax/federal-income-tax/oracle-bridge#taxable_income"],
    )

    assert result.errors == ()
    assert result.values == {
        "us:tax/federal-income-tax/oracle-bridge#taxable_income": 0
    }
    assert [call[0][1] for call in calls] == ["compile", "run-compiled"]


def test_axiom_tax_concept_is_comparable_to_policyengine() -> None:
    concept_ids = {
        mapping.concept_id
        for mapping in comparable_mappings(
            "axiom",
            "policyengine",
            categories={"tax"},
        )
    }

    # FIT liability plus its decomposed comparison targets.
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

    assert mapping.targets["axiom"] == "us:tax/federal-income-tax/oracle-bridge#ctc_value"
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
    assert runner.program_rules == US_FEDERAL_INCOME_TAX_PROGRAM_RULES
    assert runner.generated_program_target == US_FEDERAL_INCOME_TAX_BRIDGE_TARGET
    assert runner.prune_unsupported_inputs
    assert (
        "us:policies/irs/rev-proc-2025-32/standard-deduction"
        in US_FEDERAL_INCOME_TAX_IMPORTS
    )
    assert "us:statutes/26/86" in US_FEDERAL_INCOME_TAX_IMPORTS
    assert "us:statutes/26/1402/a" in US_FEDERAL_INCOME_TAX_IMPORTS
    assert "us:statutes/26/164/f" in US_FEDERAL_INCOME_TAX_IMPORTS
    generated_rule_names = {
        rule["name"] for rule in US_FEDERAL_INCOME_TAX_PROGRAM_RULES
    }
    generated_rules_by_name = {
        rule["name"]: rule for rule in US_FEDERAL_INCOME_TAX_PROGRAM_RULES
    }
    assert "self_employment_income" in generated_rule_names
    assert "self_employment_1401_taxes" in generated_rule_names
    assert "self_employment_tax_ald" in generated_rule_names
    assert "taxable_earned_income_under_section_32" in generated_rule_names
    assert (
        generated_rules_by_name["self_employment_income"]["versions"][0]["formula"]
        == "max(0, net_earnings_from_self_employment)"
    )
    assert "additional_senior_deduction" in generated_rule_names
    assert "additional_senior_deduction_magi" in generated_rule_names
    assert "ctc_value" in generated_rule_names
    assert (
        generated_rules_by_name["ctc_value"]["versions"][0]["formula"]
        == "min(ctc_credit_without_subsection_and_26a_limit, ctc_refundable_limitation_increase_amount)"
    )
    assert "business_income_of_tax_unit" in generated_rule_names
    assert "business_income_for_qbid" in generated_rule_names
    assert "qualified_business_income_deduction_phaseout_rate" in generated_rule_names
    assert "qualified_business_income_deduction" in generated_rule_names
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
    assert "capital_gains_worksheet_line_10" in generated_rule_names
    assert "capital_gains_worksheet_line_13" in generated_rule_names
    assert "capital_gains_worksheet_line_14" in generated_rule_names
    assert "capital_gains_worksheet_line_19" in generated_rule_names
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
        == "short_term_capital_gains + long_term_capital_gains"
    )
    assert "deduction_provided_in_section_199A" in generated_rule_names
    assert "us:statutes/26/24/d" not in US_FEDERAL_INCOME_TAX_IMPORTS
    assert "us:statutes/26/63" not in US_FEDERAL_INCOME_TAX_IMPORTS
