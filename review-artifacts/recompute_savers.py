#!/usr/bin/env python3
"""Independently recompute the PR #417 Saver's Credit grid.

This review helper deliberately uses three paths for every case:

1. execute the pinned RuleSpec with the local released Axiom binary;
2. calculate PolicyEngine-US live through the PR generator's exact-version gate;
3. calculate section 25B directly from the statutory thresholds and caps.

It prints JSON to stdout and does not mutate repository reports.
"""

from __future__ import annotations

import json
import subprocess
from decimal import Decimal
from importlib.metadata import version as distribution_version
from pathlib import Path
from typing import Any

from scripts.generate_federal_tax_liability import (
    ENGINE_VERSIONS,
    POLICIES,
    _policyengine_values,
)

AXIOM_BINARY = Path(
    "/Users/maxghenis/TheAxiomFoundation/"
    "axiom-rules-engine/target/release/axiom-rules-engine"
)
COMPILED_ARTIFACT = Path("/private/tmp/pr417-savers-v011.compiled.json")
MODULE = "us:policies/income_tax/savers_credit_pipeline"
PREFIX = f"{MODULE}#input."
OUTPUTS = (
    f"{MODULE}#pipeline_savers_credit_modified_adjusted_gross_income",
    f"{MODULE}#pipeline_savers_credit_applicable_percentage",
    f"{MODULE}#primary_savers_credit_contributions_taken_into_account",
    f"{MODULE}#spouse_savers_credit_contributions_taken_into_account",
    f"{MODULE}#federal_savers_credit",
)
STATUS_CODES = {
    "single": 0,
    "joint": 1,
    "separate": 2,
    "head_of_household": 3,
    "surviving_spouse": 4,
}
INPUT_FIELDS = (
    ("section_911_excluded_income", "section_911_excluded_income", "decimal"),
    ("section_931_excluded_income", "section_931_excluded_income", "decimal"),
    ("section_933_excluded_income", "section_933_excluded_income", "decimal"),
    ("filing_status", "filing_status", "integer"),
    ("adjusted_gross_income", "adjusted_gross_income", "decimal"),
    ("primary_age_at_close_of_taxable_year", "primary_age", "integer"),
    (
        "primary_is_student_under_section_152_f_2",
        "primary_is_student",
        "bool",
    ),
    (
        "primary_may_be_claimed_as_dependent_by_another_taxpayer",
        "primary_is_dependent",
        "bool",
    ),
    ("spouse_age_at_close_of_taxable_year", "spouse_age", "integer"),
    (
        "spouse_is_student_under_section_152_f_2",
        "spouse_is_student",
        "bool",
    ),
    (
        "spouse_may_be_claimed_as_dependent_by_another_taxpayer",
        "spouse_is_dependent",
        "bool",
    ),
    (
        "primary_qualified_retirement_savings_contributions",
        "primary_contributions",
        "decimal",
    ),
    (
        "spouse_qualified_retirement_savings_contributions",
        "spouse_contributions",
        "decimal",
    ),
)


def _value(kind: str, value: Any) -> dict[str, Any]:
    if kind == "decimal":
        encoded: Any = str(value)
    elif kind == "integer":
        encoded = int(value)
    else:
        encoded = bool(value)
    return {"kind": kind, "value": encoded}


def _axiom_request() -> dict[str, Any]:
    inputs = []
    queries = []
    config = POLICIES["savers_credit"]
    for index, case in enumerate(config.cases, start=1):
        entity_id = f"tax-unit-{index}"
        for axiom_name, case_name, kind in INPUT_FIELDS:
            raw_value = (
                STATUS_CODES[case.filing_status]
                if case_name == "filing_status"
                else case.inputs[case_name]
            )
            inputs.append(
                {
                    "name": f"{PREFIX}{axiom_name}",
                    "entity": "TaxUnit",
                    "entity_id": entity_id,
                    "interval": {
                        "start": "2026-01-01",
                        "end": "2026-12-31",
                    },
                    "value": _value(kind, raw_value),
                }
            )
        queries.append(
            {
                "entity_id": entity_id,
                "period": {
                    "period_kind": "tax_year",
                    "start": "2026-01-01",
                    "end": "2026-12-31",
                },
                "outputs": list(OUTPUTS),
            }
        )
    return {
        "mode": "fast",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


def _decimal_output(result: dict[str, Any], output: str) -> Decimal:
    value = result["outputs"][output]["value"]["value"]
    return Decimal(str(value))


def _statute(case: Any) -> dict[str, Decimal]:
    inputs = case.inputs
    modified_agi = sum(
        Decimal(str(inputs[name]))
        for name in (
            "adjusted_gross_income",
            "section_911_excluded_income",
            "section_931_excluded_income",
            "section_933_excluded_income",
        )
    )
    ceilings = {
        "joint": (Decimal("48500"), Decimal("52500"), Decimal("80500")),
        "head_of_household": (
            Decimal("36375"),
            Decimal("39375"),
            Decimal("60375"),
        ),
    }.get(
        case.filing_status,
        (Decimal("24250"), Decimal("26250"), Decimal("40250")),
    )
    if modified_agi <= ceilings[0]:
        rate = Decimal("0.5")
    elif modified_agi <= ceilings[1]:
        rate = Decimal("0.2")
    elif modified_agi <= ceilings[2]:
        rate = Decimal("0.1")
    else:
        rate = Decimal("0")

    def eligible(prefix: str) -> bool:
        return (
            int(inputs[f"{prefix}_age"]) >= 18
            and not bool(inputs[f"{prefix}_is_student"])
            and not bool(inputs[f"{prefix}_is_dependent"])
        )

    primary_base = min(
        max(Decimal(str(inputs["primary_contributions"])), 0),
        Decimal("2000"),
    )
    spouse_base = min(
        max(Decimal(str(inputs["spouse_contributions"])), 0),
        Decimal("2000"),
    )
    eligible_primary_base = primary_base if eligible("primary") else Decimal("0")
    eligible_spouse_base = (
        spouse_base
        if case.filing_status == "joint" and eligible("spouse")
        else Decimal("0")
    )
    return {
        "modified_agi": modified_agi,
        "rate": rate,
        "primary_base": primary_base,
        "spouse_base": spouse_base,
        "credit": rate * (eligible_primary_base + eligible_spouse_base),
    }


def main() -> None:
    actual_versions = {
        "policyengine": distribution_version("policyengine"),
        "policyengine_core": distribution_version("policyengine-core"),
        "policyengine_us": distribution_version("policyengine-us"),
    }
    assert actual_versions == ENGINE_VERSIONS
    config = POLICIES["savers_credit"]
    completed = subprocess.run(
        [
            str(AXIOM_BINARY),
            "run-compiled",
            "--artifact",
            str(COMPILED_ARTIFACT),
        ],
        input=json.dumps(_axiom_request()),
        text=True,
        capture_output=True,
        check=True,
    )
    axiom_results = json.loads(completed.stdout)["results"]
    pe_values, _ = _policyengine_values(config)
    records = []
    for case, result in zip(config.cases, axiom_results, strict=True):
        statute = _statute(case)
        axiom_credit = _decimal_output(result, OUTPUTS[-1])
        axiom_magi = _decimal_output(result, OUTPUTS[0])
        axiom_rate = _decimal_output(result, OUTPUTS[1])
        axiom_primary_base = _decimal_output(result, OUTPUTS[2])
        axiom_spouse_base = _decimal_output(result, OUTPUTS[3])
        assert axiom_credit == statute["credit"], case.case_id
        assert axiom_magi == statute["modified_agi"], case.case_id
        assert axiom_rate == statute["rate"], case.case_id
        assert axiom_primary_base == statute["primary_base"], case.case_id
        assert axiom_spouse_base == statute["spouse_base"], case.case_id
        records.append(
            {
                "case_id": case.case_id,
                "filing_status": case.filing_status,
                "agi": case.inputs["adjusted_gross_income"],
                "modified_agi": str(statute["modified_agi"]),
                "rate": str(statute["rate"]),
                "primary_base": str(statute["primary_base"]),
                "spouse_base": str(statute["spouse_base"]),
                "statute": str(statute["credit"]),
                "axiom": str(axiom_credit),
                "policyengine": pe_values[case.case_id],
                "axiom_minus_policyengine": (
                    float(axiom_credit) - pe_values[case.case_id]
                ),
            }
        )
    print(
        json.dumps(
            {
                "versions": actual_versions,
                "compiled_artifact": str(COMPILED_ARTIFACT),
                "case_count": len(records),
                "all_axiom_outputs_equal_independent_statute_math": True,
                "records": records,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
