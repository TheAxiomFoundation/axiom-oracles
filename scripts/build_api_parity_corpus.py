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
import sys
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent.parent / "corpora" / "api-parity"


def validate_case(case: dict, name: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(case.get("id"), str) or not case["id"].strip():
        errors.append(f"{name}: non-empty string id required")
    if not isinstance(case.get("axiom_request"), dict):
        errors.append(f"{name}: axiom_request object required")
    if not isinstance(case.get("expected_axiom_outputs"), dict):
        errors.append(f"{name}: expected_axiom_outputs object required")
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
