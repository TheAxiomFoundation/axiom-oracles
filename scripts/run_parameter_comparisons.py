"""Run every config-driven parameter-oracle suite against PolicyEngine.

Suites are declared in ``comparisons/parameter-oracles.yaml``. For each
comparison, the Axiom side is evaluated from the encoded rulespec formulas
read off **upstream** rulespec-us origin/main (``git show``), and the
PolicyEngine side from its parameter system at the configured instant.

One ``axiom.comparison_report.v1`` JSON is written per suite to
``dashboard/public/data/axiom-policyengine-<suite>.json``, matching the
shape of the SSA and Colorado health-threshold parameter reports.

Usage:
    .venv/bin/python scripts/run_parameter_comparisons.py
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import yaml

from run_ssa_parameter_comparison import (  # noqa: E402 — sibling module
    _ALLOWED_FORMULA,
    evaluate_rulespec_text,
    policyengine_value,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "comparisons" / "parameter-oracles.yaml"
DATA_DIR = REPO_ROOT / "dashboard" / "public" / "data"
RULESPEC_REPO = Path.home() / "rulespec-us"


def upstream_text(path: str) -> str:
    return subprocess.run(
        ["git", "-C", str(RULESPEC_REPO), "show", f"origin/main:{path}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def axiom_value(values: dict[str, float], spec: dict) -> float:
    formula = spec.get("axiom_formula")
    if not formula:
        value = values[spec["rule"]]
        # Table parameters (payment-standard schedules) are keyed by
        # assistance-unit size; `key` selects one entry.
        if "key" in spec:
            return float(value[spec["key"]])
        return value
    if not _ALLOWED_FORMULA.match(formula):
        raise ValueError(f"unsupported axiom_formula: {formula}")
    names = {n: values[n] for n in re.findall(r"[a-z_][a-z0-9_]*", formula) if n in values}
    return float(eval(formula, {"__builtins__": {}}, names))  # noqa: S307


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


def build_suite_report(suite: dict, period: str, parameters) -> dict:
    file_cache: dict[str, dict[str, float]] = {}
    concepts, aggregates, cases, mismatches = [], [], [], []
    category = suite.get("category", "cash")

    for spec in suite["comparisons"]:
        if spec["file"] not in file_cache:
            file_cache[spec["file"]] = evaluate_rulespec_text(
                upstream_text(spec["file"]), source=spec["file"], as_of=period
            )
        left = axiom_value(file_cache[spec["file"]], spec)
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
                    "axiom_source": f"rulespec-us origin/main: {spec['file']}",
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
        "scope": {"period": period, "source": "rulespec-us origin/main"},
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


def main() -> None:
    from policyengine_us import CountryTaxBenefitSystem

    config = yaml.safe_load(CONFIG_PATH.read_text())
    period = config["period"]
    parameters = CountryTaxBenefitSystem().parameters

    manifest_path = DATA_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text())

    for suite in config["suites"]:
        report = build_suite_report(suite, period, parameters)
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
