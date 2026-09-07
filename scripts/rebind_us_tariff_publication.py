#!/usr/bin/env python3
"""Carry audited tariff measurements across an exact proof-metadata rebind.

The original ledger, classification and report are immutable hash-pinned
baselines. This producer changes only 39 existing ledger hash scalars, three
classification input hashes, and an explicit historical-provenance annotation.
It does not recalculate a comparison, signature, population, assignment or rate.
The original sidecar remains evidence for the baseline classification; the
rebind receipt proves the unchanged semantics of the successor publication.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import rebind_us_tariff_campaign_dispositions as ledger_rebind  # noqa: E402

REFERENCE = "reference/us-tariff-schedule/"
BASELINE = REFERENCE + "publication-baseline/"
RECEIPT = REFERENCE + "publication-metadata-rebind.json"
LEDGER = REFERENCE + "campaign-dispositions.yaml"
CLASSIFICATION = REFERENCE + "classification-receipt.json"
REPORT = "conformance/detail/us-tariff-schedule.json"
EXERCISE = "axiom_oracles/bridges/exercise_receipts/us-tariff-schedule.json"
BASELINE_HASHES = {
    "campaign-dispositions.yaml": "2ebafef886b4f2e57724e5f6a06e5703709684b9f7c58470a585d0fe5201cf7d",
    "classification-receipt.json": "6df388c81e30fe918d8b3dd6211bde23e25d07e5ebfc554fef994911d41a4a35",
    "comparison-report.json": "41d7080f41aa4c585b505bdb7e65798cb1c5adef51ef854f661babcfb58012be",
    "exercise-receipt.json": "7e9f6ec11c67cbc17b951c816dc7116dd028c8e2d56b4bfdfa7e9702ce24a9d9",
}
# These are the completed, previously verified proof bytes rescued by 5673d70e8.
# A different proof generation requires a new reviewed rebind, not a new scan
# inferred from a merely self-consistent payload hash.
PROOF_HASHES = {
    "preview-selector-transition-receipt.json": "51f8f1405fbd398b4bb55f916abcb562901e1ff8bcc900b4a5d9bdee30fb2671",
    "cafta-reference-defect-supersession-receipt.json": "f77eb238e20780e39afc84b8a43954ceb8e59a54a4002b485715bccf33a1ea29",
    "steel-scope-projection-receipt.json": "8b21d6faf20a6686d6beac106f19ea36db4543e958bec6a3b344c624dab4e793",
    "remaining-residual-receipt.json": "f9c0c5325803ba21a4fa1b1902b116af6ca38e24af3b08631ebb58a7fb72f547",
}
PROOF_SCHEMAS = (
    ledger_rebind.TRANSITION_SCHEMA,
    ledger_rebind.CAFTA_SCHEMA,
    ledger_rebind.STEEL_SCHEMA,
    ledger_rebind.REMAINING_SCHEMA,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def render(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode()


def build(repo: Path = ROOT) -> dict[str, bytes]:
    baseline = {}
    for name, expected in BASELINE_HASHES.items():
        body = (repo / BASELINE / name).read_bytes()
        require(digest(body) == expected, f"audited baseline changed: {name}")
        baseline[name] = body
    proofs = []
    for (name, expected), schema in zip(
        PROOF_HASHES.items(), PROOF_SCHEMAS, strict=True
    ):
        proof = ledger_rebind.load_proof(repo / REFERENCE / name, schema, repo)
        require(
            proof.file_receipt["sha256"] == expected,
            f"reviewed proof generation changed: {name}",
        )
        proofs.append(proof)
    transition, cafta, steel, remaining = proofs
    targets = ledger_rebind._targets(transition, cafta, steel, remaining)
    old_ledger = ledger_rebind.parse_yaml(
        baseline["campaign-dispositions.yaml"], label="audited baseline"
    )
    old_entries = ledger_rebind._entry_catalog(old_ledger)
    ledger_rebind._validate_transition_entries(
        old_entries, ledger_rebind._transition_children(transition)
    )
    ledger_rebind._validate_cafta_embedding(transition, cafta)
    ledger_rebind._validate_class_entries(
        old_entries, steel, ledger_rebind.STEEL_ENTRY_IDS, "steel_scope_projection"
    )
    ledger_rebind._validate_class_entries(
        old_entries, remaining, ledger_rebind.REMAINING_ENTRY_IDS, "remaining_residuals"
    )
    text, changed = ledger_rebind._render_rebound_ledger(
        baseline["campaign-dispositions.yaml"].decode(), targets
    )
    require(len(changed) == 39, "rebind must change exactly 39 historical hash scalars")
    expected_ledger = copy.deepcopy(old_ledger)
    expected_entries = ledger_rebind._entry_catalog(expected_ledger)
    changes = []
    for target in targets:
        previous = ledger_rebind._mapping_at(
            old_entries[target.entry_id], target.path, label="baseline target"
        )
        ledger_rebind._set_mapping_at(
            expected_entries[target.entry_id], target.path, target.value
        )
        changes.append(
            {
                "entry_id": target.entry_id,
                "path": list(target.path),
                "before": previous,
                "after": target.value,
            }
        )
    require(
        ledger_rebind.parse_yaml(text, label="rebound ledger") == expected_ledger,
        "ledger changed outside the 39 permitted metadata fields",
    )
    ledger_bytes = text.encode()
    old_classification = json.loads(baseline["classification-receipt.json"])
    new_classification = copy.deepcopy(old_classification)
    new_inputs = {
        "disposition_ledger_sha256": digest(ledger_bytes),
        "preview_selector_transition_receipt_sha256": transition.file_receipt["sha256"],
        "preview_selector_transition_payload_sha256": transition.payload_sha256,
    }
    new_classification["inputs"].update(new_inputs)
    new_classification["metadata_rebind"] = {
        "receipt": RECEIPT,
        "audited_classification_sha256": BASELINE_HASHES["classification-receipt.json"],
        "method": "39 ledger proof-hash fields only; all selector semantics, classifications, sidecar and measured populations preserved; no bulk replay",
    }
    old_report = json.loads(baseline["comparison-report.json"])
    require(
        {
            key: value
            for key, value in old_report["classification"].items()
            if key != "class_attribution"
        }
        == old_classification,
        "baseline report/classification disagree",
    )
    new_report = copy.deepcopy(old_report)
    new_report["classification"] = {
        **new_classification,
        "class_attribution": old_report["classification"]["class_attribution"],
    }
    output = {
        LEDGER: ledger_bytes,
        CLASSIFICATION: render(new_classification),
        REPORT: render(new_report),
    }
    exercise = json.loads(baseline["exercise-receipt.json"])
    require(
        exercise["report_sha256"] == BASELINE_HASHES["comparison-report.json"],
        "baseline exercise/report disagree",
    )
    exercise["report_sha256"] = digest(output[REPORT])
    report_bindings = [
        row for row in exercise["evidence_artifacts"] if row["path"] == REPORT
    ]
    require(
        len(report_bindings) == 1
        and report_bindings[0]["sha256"] == BASELINE_HASHES["comparison-report.json"],
        "baseline exercise artifact binding disagrees",
    )
    report_bindings[0]["sha256"] = digest(output[REPORT])
    output[EXERCISE] = render(exercise)
    receipt = {
        "schema": "axiom_oracles.us_tariff_schedule.publication_metadata_rebind.v1",
        "producer": "scripts/rebind_us_tariff_publication.py",
        "source_generation": "preserved unfinished frontier rebuild at 5673d70e8b0de52b60c1fb0792e4c478704ba6a6",
        "baseline": {BASELINE + key: value for key, value in BASELINE_HASHES.items()},
        "proofs": {REFERENCE + key: value for key, value in PROOF_HASHES.items()},
        "successors": {path: digest(body) for path, body in output.items()},
        "ledger_hash_changes": changes,
        "classification_input_hash_changes": [
            {"field": key, "before": old_classification["inputs"][key], "after": value}
            for key, value in new_inputs.items()
        ],
        "preserved_classification_fields": sorted(set(old_classification) - {"inputs"}),
        "preserved_measurements_sha256": ledger_rebind.canonical_sha256(
            {key: value for key, value in old_classification.items() if key != "inputs"}
        ),
        "preserved_report_fields": sorted(set(old_report) - {"classification"}),
        "preserved_comparison_units": old_report["summary"]["total"],
        "preserved_mismatch_units": old_classification["mismatches"],
        "new_comparison_rows_scanned": 0,
        "exercise_change": "two report-hash fields only; measured cardinalities and field states unchanged",
        "new_semantic_or_legal_claims": False,
        "certified": False,
        "release_authorized": False,
    }
    output[RECEIPT] = render(receipt)
    return output


def check(repo: Path = ROOT) -> None:
    for relative, expected in build(repo).items():
        require(
            (repo / relative).read_bytes() == expected,
            f"metadata-rebound artifact drift: {relative}",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        if args.check:
            check()
        else:
            products = build()
            # All products are prepared first. Each file replaces atomically;
            # the certificate gate fails closed until the complete set agrees.
            for relative, body in products.items():
                path = ROOT / relative
                temporary = path.with_suffix(path.suffix + ".tmp")
                temporary.write_bytes(body)
                temporary.replace(path)
    except (OSError, ValueError, KeyError) as exc:
        print(f"tariff publication rebind failed: {exc}", file=sys.stderr)
        return 1
    print(
        "metadata rebind verified: 39 ledger hashes, 3 classification input hashes; 216111132 prior comparison units preserved, 0 scanned"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
