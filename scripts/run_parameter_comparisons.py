"""Run every config-driven parameter-oracle suite against PolicyEngine.

Suites are declared in ``comparisons/parameter-oracles.yaml``. For each
comparison, the Axiom side is compiled and executed from one explicitly
supplied canonical rulespec-us checkout, and the PolicyEngine side comes from
its parameter system at the configured instant.

One ``axiom.comparison_report.v1`` JSON is written per suite to
``dashboard/public/data/axiom-policyengine-<suite>.json``, matching the
shape of the SSA and Colorado health-threshold parameter reports.

Usage:
    .venv/bin/python scripts/run_parameter_comparisons.py \
      --rulespec-root ~/TheAxiomFoundation/rulespec-us \
      --axiom-binary ~/TheAxiomFoundation/axiom-rules-engine/target/release/axiom-rules-engine
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from canonical_rulespec_runtime import parse_canonical_runtime_args
from run_ssa_parameter_comparison import (  # noqa: E402 — sibling module
    policyengine_value,
)

from axiom_oracles.bridges.parameter_runtime import evaluate_rulespec_formulas

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "comparisons" / "parameter-oracles.yaml"
DATA_DIR = REPO_ROOT / "dashboard" / "public" / "data"


def concept_id(spec: dict) -> str:
    root = spec["file"].removesuffix(".yaml")
    # us-ga/... → us-ga: prefix; us/... → us: prefix, matching corpus ids.
    first, _, rest = root.partition("/")
    prefix = "us" if first == "us" else first
    cid = f"{prefix}:{rest}#{spec['rule']}"
    # Table comparisons reuse one rule across several keys (e.g. payment
    # standards by unit size); the key must be part of the concept id.
    if "key" in spec:
        cid += f"@{spec['key']}"
    return cid


def build_suite_report(
    suite: dict,
    period: str,
    parameters,
    *,
    rulespec_root: Path,
    axiom_binary: Path,
) -> dict:
    period = str(suite.get("period", period))
    axiom_values: dict[int, float] = {}
    by_file: dict[str, list[dict]] = {}
    for spec in suite["comparisons"]:
        by_file.setdefault(spec["file"], []).append(spec)
    for file_ref, specs in by_file.items():
        first, _, rest = file_ref.partition("/")
        module_ref = f"{first}:{rest.removesuffix('.yaml')}"
        formulas = [
            str(
                spec.get("axiom_formula")
                or (f"{spec['rule']}[{spec['key']}]" if "key" in spec else spec["rule"])
            )
            for spec in specs
        ]
        values = evaluate_rulespec_formulas(
            module_ref,
            formulas,
            rulespec_root=rulespec_root,
            axiom_binary=axiom_binary,
            period=period,
        )
        axiom_values.update(
            (id(spec), value) for spec, value in zip(specs, values, strict=True)
        )

    concepts, aggregates, cases, mismatches = [], [], [], []
    category = suite.get("category", "cash")

    for spec in suite["comparisons"]:
        left = axiom_values[id(spec)]
        right = policyengine_value(parameters, spec["pe"], period)
        tolerance = float(spec.get("tolerance", 1e-9))
        matched = abs(left - right) <= tolerance
        cid = concept_id(spec)

        concepts.append(
            {
                "category": category,
                "comparison": "amount",
                "components": [],
                "description": spec["description"],
                "id": cid,
                "parent": None,
                "tolerance": tolerance,
            }
        )
        aggregates.append(
            {
                "category": category,
                "comparison": "amount",
                "comparison_count": 1,
                "comparison_weight": 1,
                "components": [],
                "concept": cid,
                "description": spec["description"],
                "left_weighted_sum": left,
                "match_count": 1 if matched else 0,
                "match_rate": 100.0 if matched else 0.0,
                "match_weight": 1 if matched else 0,
                "mismatch_count": 0 if matched else 1,
                "mismatch_weight": 0 if matched else 1,
                "missing_both_count": 0,
                "missing_left_count": 0,
                "missing_right_count": 0,
                "parent": None,
                "right_weighted_sum": right,
                "tolerance": tolerance,
                "weighted_difference": left - right,
                "weighted_match_rate": 100.0 if matched else 0.0,
            }
        )
        case_mismatches = []
        if not matched:
            entry = {
                "case_id": f"{suite['suite']}-{spec['rule']}",
                "concept": cid,
                "kind": "amount_difference",
                "left": left,
                "right": right,
                "difference": left - right,
            }
            case_mismatches.append(entry)
            mismatches.append(entry)
        cases.append(
            {
                "case_id": f"{suite['suite']}-{spec['rule']}",
                "left_engine": "axiom",
                "left_errors": [],
                "match_rate": 100.0 if matched else 0.0,
                "metadata": {
                    "axiom_rule": spec["rule"],
                    "axiom_source": f"rulespec-us/{spec['file']}",
                    "axiom_formula": spec.get("axiom_formula"),
                    "dataset": "encoded_parameter_oracle",
                    "policyengine_parameter": spec["pe"],
                    "population": "rulespec-parameters",
                    "period": period,
                },
                "mismatches": case_mismatches,
                "right_engine": "policyengine",
                "right_errors": [],
            }
        )

    comparison_count = len(suite["comparisons"])
    mismatch_count = len(mismatches)
    match_count = comparison_count - mismatch_count
    return {
        "aggregates": aggregates,
        "case_count": len(cases),
        "cases": cases,
        "concepts": concepts,
        "engines": {"left": "axiom", "right": "policyengine"},
        "errors": [],
        "locales": suite.get("locales", ["US"]),
        "mismatches": mismatches,
        "population": "rulespec-parameters",
        "schema_version": "axiom.comparison_report.v1",
        "scope": {"period": period, "source": "canonical rulespec-us checkout"},
        "suite": suite["suite"],
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
    from policyengine_us import CountryTaxBenefitSystem

    rulespec_root, axiom_binary = parse_canonical_runtime_args(argv, country="us")
    config = yaml.safe_load(CONFIG_PATH.read_text())
    period = config["period"]
    parameters = CountryTaxBenefitSystem().parameters

    manifest_path = DATA_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text())

    for suite in config["suites"]:
        report = build_suite_report(
            suite,
            period,
            parameters,
            rulespec_root=rulespec_root,
            axiom_binary=axiom_binary,
        )
        out_name = f"axiom-policyengine-{suite['suite']}.json"
        (DATA_DIR / out_name).write_text(
            json.dumps(report, indent=1, sort_keys=True) + "\n"
        )
        if out_name not in manifest["reports"]:
            manifest["reports"].append(out_name)
        summary = report["summary"]
        print(
            f"{suite['suite']}: {summary['match_count']}/{summary['comparison_count']} match"
        )
        for m in report["mismatches"]:
            print(f"  mismatch {m['concept']}: axiom={m['left']} pe={m['right']}")

    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
