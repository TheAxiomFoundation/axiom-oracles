#!/usr/bin/env python3
"""Exercise the existing PE adapter in one isolated, version-asserted runtime.

This is a small synthetic compatibility probe, not Axiom parity certification
or evidence about a population dataset. The parent runs it once per version.
"""

from __future__ import annotations

import argparse
from importlib.metadata import version
import json
import math
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run_probe(fixtures: dict, expected: dict[str, str]) -> dict:
    from axiom_oracles.adapters.policyengine.runner import PolicyEngineRunner
    from axiom_oracles.core.case import Case, Concepts, Entity
    from axiom_oracles.core.household import Household, Person

    actual = {name: version(name) for name in expected}
    if actual != expected:
        raise ValueError(
            f"installed versions differ: expected {expected}; got {actual}"
        )
    # Use the exact import prelude used by generic comparisons, including its
    # explicit local-data certification override. No CLI is executed here.
    bootstrap = runpy.run_path(str(ROOT / "scripts/run_comparison.py"))[
        "_PE_RUNTIME_BOOTSTRAP"
    ]
    exec(bootstrap, {})
    runner = PolicyEngineRunner(batch_size=2)
    variables = fixtures["variables"]
    cases = []
    errors = []
    households = []
    for item in fixtures["cases"]:
        households.append(
            Household(
                household_id=item["id"],
                year=fixtures["year"],
                state=item["state"],
                county_fips=item["county_fips"],
                people=tuple(
                    Person.with_yearly_earnings(
                        age=person["age"],
                        earnings=person["earnings"],
                        relation=person["relation"],
                    )
                    for person in item["people"]
                ),
            )
        )
        cases.append(
            Case(
                case_id=item["id"],
                period=str(fixtures["year"]),
                facts={Concepts.STATE_CODE: item["state"]},
                metadata={
                    "scope": {"type": "census_county", "geoid": item["county_fips"]}
                },
                entities=tuple(
                    Entity(
                        entity_id=f"person-{index}",
                        kind="person",
                        facts={
                            Concepts.PERSON_AGE: person["age"],
                            Concepts.YEARLY_EARNED_INCOME: person["earnings"],
                            Concepts.HOUSEHOLD_RELATION: person["relation"],
                        },
                    )
                    for index, person in enumerate(item["people"])
                ),
            )
        )
    observed = []
    for household in households:
        result = runner.run_household(household, variables)
        values = {}
        errors.extend(f"{household.household_id}: {error}" for error in result.errors)
        for variable in variables:
            value = result.values.get(variable)
            if type(value) not in (int, float, bool) or not math.isfinite(value):
                errors.append(f"{household.household_id}: missing/invalid {variable}")
            else:
                values[variable] = value
        observed.append({"case_id": household.household_id, "outputs": values})
    # Also exercise the actual Case batch path; its values must agree with
    # singleton Case calls, not with Household projections with different roles.
    singles = [runner.run_case(case, variables) for case in cases]
    batches = []
    batch_count = 0
    batch_differences = []
    for start in range(0, len(cases), 2):
        # The public runner intentionally falls back to singleton calls after
        # some batch errors. An update probe must expose those regressions.
        batches.extend(runner._run_case_batch_once(cases[start : start + 2], variables))
        batch_count += 1
    if len(batches) != len(cases) or [r.household_id for r in batches] != [
        c.case_id for c in cases
    ]:
        errors.append("batch results have missing, extra or reordered cases")
    for case, single, batch in zip(cases, singles, batches, strict=True):
        errors.extend(f"{case.case_id} singleton: {e}" for e in single.errors)
        errors.extend(f"{case.case_id} batch: {e}" for e in batch.errors)
        for variable in variables:
            left, right = single.values.get(variable), batch.values.get(variable)
            if (
                type(left) not in (int, float, bool)
                or type(right) not in (int, float, bool)
                or not math.isfinite(left)
                or not math.isfinite(right)
            ):
                errors.append(
                    f"{case.case_id}: singleton/batch missing or invalid {variable}"
                )
            elif not math.isclose(left, right, rel_tol=1e-6, abs_tol=0.01):
                batch_differences.append(
                    {
                        "case_id": case.case_id,
                        "variable": variable,
                        "singleton": left,
                        "batch": right,
                        "difference": right - left,
                    }
                )
    count = sum(len(row["outputs"]) for row in observed)
    if count != len(cases) * len(variables) or not count:
        errors.append("probe did not return every required household output")
    return {
        "packages": actual,
        "case_count": len(cases),
        "comparison_count": count,
        "batch_count": batch_count,
        "batch_differences": batch_differences,
        "cases": observed,
        "errors": [str(e)[:1500] for e in errors[:50]],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--packages", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Retain finite historical batch differences as review evidence",
    )
    args = parser.parse_args()
    try:
        result = run_probe(
            json.loads(args.fixtures.read_text()), json.loads(args.packages.read_text())
        )
    except Exception as exc:
        result = {
            "case_count": 0,
            "comparison_count": 0,
            "cases": [],
            "errors": [f"{type(exc).__name__}: {exc}"[:1500]],
        }
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return (
        1
        if result["errors"] or (result.get("batch_differences") and not args.baseline)
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
