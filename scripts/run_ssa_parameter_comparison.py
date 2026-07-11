"""Compare SSA wage-indexed amounts encoded in rulespec-us against PolicyEngine.

The rulespec side is the set of ``kind: parameter`` rules under
``rulespec-us/us/policies/ssa/*/2026.yaml`` (contribution and benefit base, PIA
bend points, quarter of coverage, retirement earnings test exempt amounts,
and substantial gainful activity). Each file is compiled and executed by the
Axiom rules engine.

The PolicyEngine side is the parameter system evaluated at 2026-01-01, with
uprating applied.

Output is an ``axiom.comparison_report.v1`` JSON shaped like the Colorado
health-thresholds parameter report, written to
``dashboard/public/data/axiom-policyengine-ssa-parameters.json``.

Usage:
    uv run python scripts/run_ssa_parameter_comparison.py \
      --rulespec-root ~/TheAxiomFoundation/rulespec-us \
      --axiom-binary ~/TheAxiomFoundation/axiom-rules-engine/target/release/axiom-rules-engine
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from canonical_rulespec_runtime import parse_canonical_runtime_args

from axiom_oracles.bridges.parameter_runtime import evaluate_rulespec_outputs

PERIOD = "2026-01-01"
SUITE = "ssa-parameters"
REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = (
    REPO_ROOT
    / "dashboard"
    / "public"
    / "data"
    / "axiom-policyengine-ssa-parameters.json"
)

# (rulespec file, terminal rule name, PE accessor, description)
# PE accessors receive the root parameter node at the comparison instant.
COMPARISONS = [
    {
        "file": "policies/ssa/contribution-and-benefit-base/2026.yaml",
        "rule": "contribution_and_benefit_base_under_section_230_of_social_security_act",
        "description": "OASDI contribution and benefit base (taxable maximum)",
        "pe_parameter": "gov.irs.payroll.social_security.cap",
    },
    {
        "file": "policies/ssa/quarter-of-coverage/2026.yaml",
        "rule": "quarter_of_coverage_amount",
        "description": "Quarter of coverage earnings amount",
        "pe_parameter": "gov.ssa.social_security.quarters_of_coverage_threshold",
    },
    {
        "file": "policies/ssa/pia-bend-points/2026.yaml",
        "rule": "first_pia_bend_point",
        "description": "PIA formula first bend point",
        "pe_parameter": "gov.ssa.social_security.pia.formula_factors[1].threshold",
    },
    {
        "file": "policies/ssa/pia-bend-points/2026.yaml",
        "rule": "second_pia_bend_point",
        "description": "PIA formula second bend point",
        "pe_parameter": "gov.ssa.social_security.pia.formula_factors[2].threshold",
    },
    {
        "file": "policies/ssa/retirement-earnings-test/2026.yaml",
        "rule": "retirement_earnings_test_lower_annual_exempt_amount",
        "description": "Retirement earnings test annual exempt amount (under FRA)",
        "pe_parameter": "gov.ssa.social_security.earnings_test.exempt_amount_under_fra",
    },
    {
        "file": "policies/ssa/retirement-earnings-test/2026.yaml",
        "rule": "retirement_earnings_test_higher_annual_exempt_amount",
        "description": "Retirement earnings test annual exempt amount (year of FRA)",
        "pe_parameter": "gov.ssa.social_security.earnings_test.exempt_amount_year_of_fra",
    },
    {
        "file": "policies/ssa/substantial-gainful-activity/2026.yaml",
        "rule": "substantial_gainful_activity_blind_monthly_amount",
        "description": "Substantial gainful activity monthly amount (blind)",
        "pe_parameter": "gov.ssa.sga.blind",
    },
    {
        "file": "policies/ssa/substantial-gainful-activity/2026.yaml",
        "rule": "substantial_gainful_activity_non_blind_disabled_monthly_amount",
        "description": "Substantial gainful activity monthly amount (non-blind)",
        "pe_parameter": "gov.ssa.sga.non_blind",
    },
]


def policyengine_value(parameters, accessor: str, period: str = PERIOD) -> float:
    """Resolve a PE parameter accessor like ``a.b.c`` or ``a.b[1].threshold``."""
    bracket = re.match(
        r"^(?P<path>[\w.]+)\[(?P<index>\d+)\]\.(?P<field>threshold|amount)$",
        accessor,
    )
    if bracket:
        node = parameters
        for part in bracket.group("path").split("."):
            node = node.children[part]
        scale = node(period)
        index = int(bracket.group("index"))
        if bracket.group("field") == "threshold":
            return float(scale.thresholds[index])
        return float(scale.amounts[index])
    node = parameters
    for part in accessor.split("."):
        node = node.children[part]
    return float(node(period))


def build_report(*, rulespec_root: Path, axiom_binary: Path) -> dict:
    from policyengine_us import CountryTaxBenefitSystem

    parameters = CountryTaxBenefitSystem().parameters

    file_values: dict[str, dict[str, float]] = {}
    concepts = []
    aggregates = []
    cases = []
    mismatches = []

    for spec in COMPARISONS:
        rel = spec["file"]
        if rel not in file_values:
            module_ref = "us:" + rel.removesuffix(".yaml")
            file_specs = [item for item in COMPARISONS if item["file"] == rel]
            output_ids = [f"{module_ref}#{item['rule']}" for item in file_specs]
            executed = evaluate_rulespec_outputs(
                rulespec_root / "us" / rel,
                output_ids,
                rulespec_root=rulespec_root,
                axiom_binary=axiom_binary,
                period="2026",
            )
            file_values[rel] = {
                item["rule"]: float(executed[output_id])
                for item, output_id in zip(file_specs, output_ids, strict=True)
            }
        axiom_value = file_values[rel][spec["rule"]]
        pe_value = policyengine_value(parameters, spec["pe_parameter"])

        concept_root = "us:" + rel.removesuffix(".yaml").replace("/2026", "/2026")
        concept_id = f"{concept_root}#{spec['rule']}"
        tolerance = 1e-9
        matched = abs(axiom_value - pe_value) <= tolerance

        concepts.append(
            {
                "category": "cash",
                "comparison": "amount",
                "components": [],
                "description": spec["description"],
                "id": concept_id,
                "parent": None,
                "tolerance": tolerance,
            }
        )
        aggregates.append(
            {
                "category": "cash",
                "comparison": "amount",
                "comparison_count": 1,
                "comparison_weight": 1,
                "components": [],
                "concept": concept_id,
                "description": spec["description"],
                "left_weighted_sum": axiom_value,
                "match_count": 1 if matched else 0,
                "match_rate": 100.0 if matched else 0.0,
                "match_weight": 1 if matched else 0,
                "mismatch_count": 0 if matched else 1,
                "mismatch_weight": 0 if matched else 1,
                "missing_both_count": 0,
                "missing_left_count": 0,
                "missing_right_count": 0,
                "parent": None,
                "right_weighted_sum": pe_value,
                "tolerance": tolerance,
                "weighted_difference": axiom_value - pe_value,
                "weighted_match_rate": 100.0 if matched else 0.0,
            }
        )
        case_mismatches = []
        if not matched:
            entry = {
                "case_id": f"{SUITE}-{spec['rule']}",
                "concept": concept_id,
                "kind": "amount_difference",
                "left": axiom_value,
                "right": pe_value,
                "difference": axiom_value - pe_value,
            }
            case_mismatches.append(entry)
            mismatches.append(entry)
        cases.append(
            {
                "case_id": f"{SUITE}-{spec['rule']}",
                "left_engine": "axiom",
                "left_errors": [],
                "match_rate": 100.0 if matched else 0.0,
                "metadata": {
                    "axiom_rule": spec["rule"],
                    "axiom_source": f"rulespec-us/{rel}",
                    "dataset": "encoded_parameter_oracle",
                    "policyengine_parameter": spec["pe_parameter"],
                    "population": "rulespec-parameters",
                    "period": PERIOD,
                },
                "mismatches": case_mismatches,
                "right_engine": "policyengine",
                "right_errors": [],
            }
        )

    mismatch_count = len(mismatches)
    comparison_count = len(COMPARISONS)
    match_count = comparison_count - mismatch_count
    return {
        "aggregates": aggregates,
        "case_count": len(cases),
        "cases": cases,
        "concepts": concepts,
        "engines": {"left": "axiom", "right": "policyengine"},
        "errors": [],
        "locales": ["US"],
        "mismatches": mismatches,
        "population": "rulespec-parameters",
        "schema_version": "axiom.comparison_report.v1",
        "scope": {"period": PERIOD, "source": "rulespec-us/us/policies/ssa"},
        "suite": SUITE,
        "summary": {
            "comparison_count": comparison_count,
            "error_count": 0,
            "errors_by_engine": {},
            "match_count": match_count,
            "mismatch_count": mismatch_count,
            "mismatches_by_concept": [
                {"concept": m["concept"], "count": 1} for m in mismatches
            ],
            "mismatches_by_kind": (
                [{"count": mismatch_count, "kind": "amount_difference"}]
                if mismatch_count
                else []
            ),
            "mismatches_by_scenario": {},
            "weighted": {
                "comparison_weight": comparison_count,
                "match_rate": 100.0 * match_count / comparison_count,
                "match_weight": match_count,
                "mismatch_weight": mismatch_count,
            },
            "alarms": [],
        },
    }


def main(argv: list[str] | None = None) -> None:
    rulespec_root, axiom_binary = parse_canonical_runtime_args(argv, country="us")
    report = build_report(
        rulespec_root=rulespec_root,
        axiom_binary=axiom_binary,
    )
    OUTPUT_PATH.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    summary = report["summary"]
    print(f"wrote {OUTPUT_PATH}")
    print(
        f"{summary['match_count']}/{summary['comparison_count']} SSA parameters match"
    )
    for m in report["mismatches"]:
        print(f"  mismatch {m['concept']}: axiom={m['left']} pe={m['right']}")


if __name__ == "__main__":
    main()
