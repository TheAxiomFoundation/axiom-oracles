#!/usr/bin/env python
"""Check Alabama's canonical section 40-18-5 fixtures against PolicyEngine."""

from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path

import yaml

MODULE = (
    "us-al:policies/income_tax/"
    "2026_section_40_18_5_schedule_before_credits"
)
TAXABLE_INCOME = (
    f"{MODULE}#input."
    "al_pit_2026_section_40_18_5_completed_taxable_income"
)
JOINT_SCHEDULE = (
    f"{MODULE}#input."
    "al_pit_2026_section_40_18_5_married_joint_schedule_applies"
)
OUTPUT = f"{MODULE}#al_pit_2026_section_40_18_5_schedule_before_credits"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rulespec-root", type=Path, required=True)
    parser.add_argument("--year", type=int, default=2026)
    return parser


def fixture_path(rulespec_root: Path) -> Path:
    jurisdiction, module_path = MODULE.split(":", 1)
    return rulespec_root / jurisdiction / f"{module_path}.test.yaml"


def main() -> int:
    args = _parser().parse_args()
    cases = yaml.safe_load(fixture_path(args.rulespec_root).read_text())

    from policyengine_us import CountryTaxBenefitSystem

    rates = (
        CountryTaxBenefitSystem()
        .parameters(args.year)
        .gov.states.al.tax.income.rates
    )
    failures: list[str] = []
    compared = 0
    for case in cases:
        inputs = case["input"]
        outputs = case["output"]
        if OUTPUT not in outputs:
            continue
        taxable_income = max(Decimal("0"), Decimal(str(inputs[TAXABLE_INCOME])))
        schedule = rates.joint if inputs[JOINT_SCHEDULE] else rates.single
        actual = Decimal(str(schedule.calc([float(taxable_income)])[0]))
        expected = Decimal(str(outputs[OUTPUT]))
        compared += 1
        if abs(actual - expected) > Decimal("0.000001"):
            failures.append(
                f"{case['name']}: RuleSpec={expected}, PolicyEngine={actual}"
            )
    if compared != 18:
        failures.append(f"expected 18 canonical fixtures; found {compared}")
    if failures:
        raise SystemExit("\n".join(failures))
    print(
        f"AL canonical schedule grid: {compared}/{compared} PolicyEngine "
        f"parameter-scale matches for {args.year}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
