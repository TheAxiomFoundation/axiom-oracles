"""Build the API parity corpus release asset from corpora/api-parity/.

Validates every case against the minimal contract axiom-api's runner
requires (see axiom-oracles#459 / axiom-api#139), concatenates them into
one sorted JSON array, and prints the sha256 axiom-api pins in
data/parity-corpus.lock.json.

Usage: python scripts/build_api_parity_corpus.py [--out dist/api-parity-corpus.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent.parent / "corpora" / "api-parity"
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def validate_tolerance(tolerance: object, label: str) -> list[str]:
    """A tolerance decides what "matching" and "match" mean, so its amount
    must be a real, non-negative number (axiom-api src/parity.ts)."""
    if tolerance is None:
        return []
    if not isinstance(tolerance, dict):
        return [f"{label}: tolerance must be an object"]
    amount = tolerance.get("amount")
    if "amount" in tolerance and not (_finite_number(amount) and amount >= 0):
        return [f"{label}: tolerance.amount must be a finite, non-negative number"]
    return []


def validate_known_difference(value: object, mapped: list[str], label: str) -> list[str]:
    """The external counterpart of known_deviation: an issue, a note, and the
    engine's values pinned for exactly the mapped variables."""
    if not isinstance(value, dict):
        return [f"{label}: known_difference must be an object"]
    errors: list[str] = []
    issue = value.get("issue")
    if not isinstance(issue, str) or not re.fullmatch(r"https://\S+", issue):
        errors.append(f"{label}: known_difference.issue must be a tracking-issue URL")
    if not isinstance(value.get("note"), str) or not value["note"].strip():
        errors.append(f"{label}: known_difference.note required")
    pinned = value.get("pinned_engine_outputs")
    if not isinstance(pinned, dict):
        errors.append(f"{label}: known_difference.pinned_engine_outputs object required")
    elif sorted(pinned) != sorted(mapped):
        errors.append(
            f"{label}: known_difference.pinned_engine_outputs must pin exactly the mapped variables "
            f"({', '.join(sorted(mapped))})"
        )
    elif not all(_finite_number(pin) for pin in pinned.values()):
        errors.append(f"{label}: known_difference.pinned_engine_outputs values must be finite numbers")
    return errors


def validate_comparison(comparison: object, index: int, case: dict, name: str) -> list[str]:
    """Mirror axiom-api's validateExternalComparison, plus one authoring rule:
    a monthly case may not be compared with an annual value divided by 12,
    which is a mean over months whose parameters differ."""
    label = f"{name}: external_comparisons[{index}]"
    if not isinstance(comparison, dict):
        return [f"{label} must be an object"]
    errors: list[str] = []
    if not isinstance(comparison.get("id"), str) or not comparison["id"].strip():
        errors.append(f"{label}: non-empty string id required")
    if comparison.get("engine") != "policyengine":
        errors.append(f"{label}: engine must be policyengine")
    request = comparison.get("request")
    if not isinstance(request, dict):
        errors.append(f"{label}: request object required")
    else:
        if not isinstance(request.get("country_id"), str) or not request["country_id"].strip():
            errors.append(f"{label}: request.country_id required")
        if request.get("version") not in ("current", "frontier"):
            errors.append(f"{label}: request.version must be current or frontier")
        if not isinstance(request.get("household"), dict):
            errors.append(f"{label}: request.household object required")
    mappings = comparison.get("mappings")
    if not isinstance(mappings, list) or not mappings:
        return [*errors, f"{label}: mappings must be a non-empty array"]
    expected = case.get("expected_axiom_outputs")
    expected = expected if isinstance(expected, dict) else {}
    household = (case.get("axiom_request") or {}).get("household") or {}
    period = household.get("period") if isinstance(household, dict) else None
    mapped: list[str] = []
    for mapping_index, mapping in enumerate(mappings):
        where = f"{label}.mappings[{mapping_index}]"
        if not isinstance(mapping, dict):
            errors.append(f"{where} must be an object")
            continue
        variable = mapping.get("axiom_variable")
        if not isinstance(variable, str) or not variable.strip():
            errors.append(f"{where}.axiom_variable required")
            continue
        mapped.append(variable)
        if variable not in expected:
            errors.append(
                f"{where} maps {variable}, which is not in expected_axiom_outputs; "
                "external comparisons may map only expected outputs"
            )
        if not isinstance(mapping.get("external_path"), str) or not mapping["external_path"].strip():
            errors.append(f"{where}.external_path required")
        transform = mapping.get("transform")
        if transform not in (None, "annual_to_monthly"):
            errors.append(f"{where}.transform is unsupported")
        if transform == "annual_to_monthly" and isinstance(period, str) and MONTH.match(period):
            errors.append(
                f"{where} divides an annual value by 12 while the Axiom case computes {period}; "
                f"map the engine's {period} value instead"
            )
    if len(set(mapped)) != len(mapped):
        errors.append(f"{label}: mappings must name each axiom_variable once")
    errors.extend(validate_tolerance(comparison.get("tolerance"), label))
    if "known_difference" in comparison:
        errors.extend(validate_known_difference(comparison["known_difference"], mapped, label))
    return errors


def validate_case(case: dict, name: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(case.get("id"), str) or not case["id"].strip():
        errors.append(f"{name}: non-empty string id required")
    if not isinstance(case.get("axiom_request"), dict):
        errors.append(f"{name}: axiom_request object required")
    if not isinstance(case.get("expected_axiom_outputs"), dict):
        errors.append(f"{name}: expected_axiom_outputs object required")
    errors.extend(validate_tolerance(case.get("tolerance"), name))
    comparisons = case.get("external_comparisons")
    if comparisons is not None:
        if not isinstance(comparisons, list):
            errors.append(f"{name}: external_comparisons must be an array")
        else:
            for index, comparison in enumerate(comparisons):
                errors.extend(validate_comparison(comparison, index, case, name))
            ids = [c.get("id") for c in comparisons if isinstance(c, dict)]
            if len(set(ids)) != len(ids):
                errors.append(f"{name}: external_comparisons ids must be unique")
    deviation = case.get("known_deviation")
    if deviation is not None:
        if not isinstance(deviation, dict):
            errors.append(f"{name}: known_deviation must be an object")
        else:
            if not str(deviation.get("issue", "")).startswith("https://"):
                errors.append(f"{name}: known_deviation.issue must be a tracking-issue URL")
            if not isinstance(deviation.get("note"), str) or not deviation["note"].strip():
                errors.append(f"{name}: known_deviation.note required")
            if not isinstance(deviation.get("pinned_outputs"), dict):
                errors.append(f"{name}: known_deviation.pinned_outputs object required")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="dist/api-parity-corpus.json")
    args = parser.parse_args()

    files = sorted(CORPUS_DIR.glob("*.json"))
    if not files:
        print("no cases found in corpora/api-parity/", file=sys.stderr)
        return 1

    cases = []
    errors: list[str] = []
    seen_ids: set[str] = set()
    for path in files:
        case = json.loads(path.read_text())
        errors.extend(validate_case(case, path.name))
        case_id = case.get("id")
        if case_id in seen_ids:
            errors.append(f"{path.name}: duplicate case id {case_id}")
        seen_ids.add(case_id)
        cases.append(case)

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    cases.sort(key=lambda case: case["id"])
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(cases, indent=2, sort_keys=False) + "\n"
    out.write_text(payload)
    sha256 = hashlib.sha256(payload.encode()).hexdigest()
    print(f"wrote {out} ({len(cases)} cases)")
    print(f"sha256 {sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
