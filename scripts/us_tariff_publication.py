"""Mandatory, small-artifact evidence gate for the frozen tariff campaign.

The full campaign producer audits the comparison stream and classification
sidecar before emitting a report. This consumer additionally requires the
independently reproduced explanations used to enroll fresh exact signatures.
The chain is one-way: causal proof -> ledger -> classification -> report ->
certificate. A renamed class or deleted evidence marker cannot disable it.

These run-specific anchors preserve 42 reviewed migration entries. The two
older preference/rate explanations are retired as causal evidence improves.
Their replacements need independent proofs, not widened historical selectors.
None of this closes legal dependencies.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SUITE = "us-tariff-schedule"
LEDGER_PATH = "reference/us-tariff-schedule/campaign-dispositions.yaml"
CLASSIFICATION_PATH = "reference/us-tariff-schedule/classification-receipt.json"
COMPARISON_PATH = "reference/us-tariff-schedule/comparison-summary.json"
REPORT_PATH = "conformance/detail/us-tariff-schedule.json"
# The original full sidecar/stream audit is preserved in publication-baseline.
# This successor is its verified metadata-only rebind; reproduce the exact
# transformation with scripts/rebind_us_tariff_publication.py --check.
# No comparison population, signature assignment or sidecar was recomputed.
# Missing is deliberately red.
# This binds composition assignments as well as counts; a raw population hash
# alone cannot prove how component signatures were assigned to total classes.
TRUSTED_CLASSIFICATION_SHA256 = (
    "36ee1920af8b1ed94d90b01c48eeedf0441cf1a9653e5f3fcb084ba639f7ed95"
)
RETIRED_BASE_IDS = frozenset(
    {
        "preference-entry-semantics",
        "vintage-revision-232-changed-rate",
    }
)
BASE_ENTRY_COUNT = 42
BASE_ENTRIES_SHA256 = "2af5fe1a28092898428538d797ac00ddcddbea39bd2b54ae0e697e265fce04db"
BASE_CLASS_MEASUREMENTS_SHA256 = (
    "767727ff1936341e8fca19ae534a8dd5a319583ee6d891e1c95180557d07608f"
)
CLASSIFICATION_POPULATION = {
    "schema": "axiom_oracles.us_tariff_schedule.classification_population.v1",
    "algorithm": "two-domain-sha256-sums-mod-secp256k1-prime",
    "units": 6_807_741,
    "units_by_kind": {
        "component_signature": 3_740_478,
        "total_signature_composition": 3_067_263,
    },
    "accumulators": [
        "4c38649708307c9935ac42227007edc9914a5c2e04e8e785b582ce041fe06046",
        "bdc732bbc7e58ca01f8db9c3ab6b37c0261fedaadfe94349a08fb7a995337095",
    ],
}
PINNED_CLASSIFICATION_INPUTS = {
    "comparison_artifact_sha256": "3e0f72d28abe9a2d0f4cb9ed53920f225039b896794302afe4671c5271110fd0",
    "comparison_receipt_sha256": "936e0653c8fc6e950c46951ddc7865d9a7943c2559165b7ab41364521d4cfcc7",
    "preview_disposition_receipt_sha256": "f112b376dd7d4af5933b3adee070aabf93b84eac77c7a901843d99429cc37181",
    "preview_disposition_payload_sha256": "7fd2ce585bf84d40aeabfdca0bbea82fac23c4c02a7f5976236e6cd657314f18",
    "preview_selector_transition_receipt_sha256": "51f8f1405fbd398b4bb55f916abcb562901e1ff8bcc900b4a5d9bdee30fb2671",
    "preview_selector_transition_payload_sha256": "11dd2d05a60742dbc2b09eb095c12e2e49110f439302a43dd92ae54a82c3b3ca",
    "routing_rows_sha256": "7236c015bee357f33063a3ab7917c1b4ad42390d97ad2ecda26fad9bb21232b3",
}
PINNED_PROOFS = {
    "reference/us-tariff-schedule/preview-disposition-line-sets.json": PINNED_CLASSIFICATION_INPUTS[
        "preview_disposition_receipt_sha256"
    ],
    "reference/us-tariff-schedule/preview-selector-transition-receipt.json": PINNED_CLASSIFICATION_INPUTS[
        "preview_selector_transition_receipt_sha256"
    ],
    "reference/us-tariff-schedule/cafta-reference-defect-supersession-receipt.json": (
        "f77eb238e20780e39afc84b8a43954ceb8e59a54a4002b485715bccf33a1ea29"
    ),
}
PROOF_SPECS = (
    (
        "steel_scope_projection",
        "scripts.build_us_tariff_steel_scope_projection_receipt",
        "reference/us-tariff-schedule/steel-scope-projection-receipt.json",
    ),
    (
        "remaining_residuals",
        "scripts.build_us_tariff_remaining_residual_receipt",
        "reference/us-tariff-schedule/remaining-residual-receipt.json",
    ),
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"tariff publication: {message}")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate key {key!r}")
        result[key] = value
    return result


class _UniqueSafeLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        return _unique_pairs(
            [
                (
                    self.construct_object(key, deep=deep),
                    self.construct_object(value, deep=deep),
                )
                for key, value in node.value
            ]
        )


def _count(value: Any, label: str) -> int:
    _require(type(value) is int and value >= 0, f"invalid count: {label}")
    return value


class _Snapshot:
    """Read each small committed artifact once and reject mid-validation drift."""

    def __init__(self, repo_root: Path):
        self.root = repo_root.resolve()
        self.files: dict[str, bytes] = {}

    def read(self, relative: str) -> bytes:
        path = (self.root / relative).resolve()
        _require(path.is_relative_to(self.root), "artifact escaped the repository")
        if relative not in self.files:
            self.files[relative] = path.read_bytes()
        return self.files[relative]

    def json(self, relative: str) -> dict:
        def reject_constant(value):
            raise ValueError(f"tariff publication: non-finite JSON value {value}")

        value = json.loads(
            self.read(relative),
            object_pairs_hook=_unique_pairs,
            parse_constant=reject_constant,
        )
        _require(isinstance(value, dict), f"{relative} must be an object")
        return value

    def sha256(self, relative: str) -> str:
        return hashlib.sha256(self.read(relative)).hexdigest()

    def require_unchanged(self) -> None:
        for relative, original in self.files.items():
            _require(
                (self.root / relative).read_bytes() == original,
                f"artifact changed during validation: {relative}",
            )


def _proof_contracts(snapshot: _Snapshot) -> tuple[dict, list[dict]]:
    contracts = {}
    evidence = []
    for marker, module_name, relative in PROOF_SPECS:
        proof = snapshot.json(relative)

        # The causal validator checks these source receipts itself; retaining
        # their bytes also closes the consumer's check-to-publication window.
        def capture_sources(value):
            if isinstance(value, list):
                for item in value:
                    capture_sources(item)
            elif isinstance(value, dict):
                path = value.get("path")
                if isinstance(path, str) and not Path(path).is_absolute():
                    captured = snapshot.read(path)
                    _require(
                        type(value.get("bytes")) is int
                        and len(captured) == value["bytes"]
                        and hashlib.sha256(captured).hexdigest() == value.get("sha256"),
                        f"captured proof source/input differs from its receipt: {path}",
                    )
                for item in value.values():
                    capture_sources(item)

        capture_sources(proof.get("producer"))
        inputs = proof.get("inputs")
        _require(isinstance(inputs, dict), "causal proof inputs are missing")
        for input_name, receipt in inputs.items():
            # These are the two external bulk populations whose fixed receipts
            # the small validator authenticates without opening their bodies.
            # Every other relative source/input is mandatory even if missing.
            if input_name not in {"historical_artifact", "comparison_artifact"}:
                capture_sources(receipt)
        producer = importlib.import_module(module_name)
        producer.validate_artifact(proof, repo_root=snapshot.root)
        proof_hash = snapshot.sha256(relative)
        for contract in proof["classes"]:
            class_id = contract["id"]
            _require(class_id not in contracts, "duplicate causal-proof class")
            contracts[class_id] = {
                "contract": contract,
                "marker": marker,
                "binding": {
                    "receipt": relative,
                    "sha256": proof_hash,
                    "receipt_payload_sha256": proof["receipt_payload_sha256"],
                    "identity_population_sha256": contract[
                        "identity_population_sha256"
                    ],
                },
            }
        evidence.append(
            {
                "claim": f"suite:{SUITE}:causal-proof:{marker}",
                "mode": "computed",
                "artifact": relative,
                "sha256": proof_hash,
            }
        )
    _require(bool(contracts), "no authenticated causal explanations")
    return contracts, evidence


def _validate_enrollment(ledger: dict, contracts: dict) -> tuple[dict, list[str]]:
    _require(
        ledger.get("schema") == "axiom_oracles.dispositions.v1", "wrong ledger schema"
    )
    _require(ledger.get("suite") == SUITE, "wrong ledger suite")
    raw_entries = ledger.get("entries")
    _require(isinstance(raw_entries, list), "ledger entries must be a list")
    _require(all(isinstance(e, dict) for e in raw_entries), "malformed ledger entry")
    ids = [e.get("id") for e in raw_entries]
    _require(all(isinstance(i, str) and i for i in ids), "invalid class id")
    _require(len(set(ids)) == len(ids), "duplicate ledger class")
    entries = dict(zip(ids, raw_entries, strict=True))
    _require(
        not RETIRED_BASE_IDS.intersection(entries),
        "superseded causal explanation was restored",
    )
    base_entries = [e for e in raw_entries if e["id"] not in contracts]
    _require(
        len(base_entries) == BASE_ENTRY_COUNT
        and _canonical_sha256(base_entries) == BASE_ENTRIES_SHA256,
        "reviewed baseline selectors changed or an unproved class was added",
    )
    _require(
        set(contracts) <= set(entries),
        "required causal-proof class is missing or renamed",
    )
    for class_id, authenticated in contracts.items():
        entry = entries[class_id]
        contract = authenticated["contract"]
        for field in (
            "disposition",
            "attribution",
            "expected_units",
            "expected_signature_count",
            "expected_signature_population_sha256",
            "signatures",
        ):
            _require(
                entry.get(field) == contract[field],
                f"{class_id}: {field} differs from proof",
            )
        _require(
            entry.get("kind") == "signature_class", f"{class_id}: wrong matcher kind"
        )
        _require(
            entry.get("match") == {}, f"{class_id}: only exact signatures may match"
        )
        _require(
            entry.get("expires_on_source_change") is True,
            f"{class_id}: proof must expire",
        )
        _require(
            all(
                isinstance(entry.get(field), str) and entry[field].strip()
                for field in ("receipt", "reason")
            ),
            f"{class_id}: missing explanation",
        )
        metadata = entry.get("evidence")
        _require(isinstance(metadata, dict), f"{class_id}: missing proof metadata")
        _require(
            metadata.get(authenticated["marker"]) == authenticated["binding"],
            f"{class_id}: causal-proof binding is missing or stale",
        )
        sources = metadata.get("sources")
        _require(
            isinstance(sources, list)
            and authenticated["binding"]["receipt"] in sources,
            f"{class_id}: source list omits the proof",
        )
    return entries, [e["id"] for e in base_entries]


def _validate_classification(
    classification: dict,
    entries: dict,
    base_ids: list[str],
    contracts: dict,
    comparison: dict,
) -> None:
    _require(
        classification.get("schema")
        == "axiom_oracles.us_tariff_schedule.classification.v2",
        "wrong classification schema",
    )
    _require(
        classification.get("selector_count") == len(entries), "selector census drift"
    )
    _require(
        classification.get("conservation") == "PASS",
        "classification conservation did not pass",
    )
    _require(
        _canonical_sha256(classification.get("classification_population"))
        == _canonical_sha256(CLASSIFICATION_POPULATION),
        "classification population changed",
    )
    census = classification.get("class_census")
    groups = classification.get("groups")
    compositions = classification.get("derived_total_compositions")
    _require(
        isinstance(census, dict) and set(census) <= set(entries), "unknown class census"
    )
    _require(
        isinstance(groups, dict) and set(groups) <= set(entries) | {"__unexplained__"},
        "unknown classification groups",
    )
    _require(isinstance(compositions, dict), "missing derived total compositions")
    measurements = {}
    direct_by_slot: Counter[str] = Counter()
    for class_id in entries:
        units = _count(census.get(class_id, 0), class_id)
        group = groups.get(class_id, {"units": 0, "per_slot": {}})
        _require(isinstance(group, dict), f"{class_id}: malformed group")
        _require(
            _count(group.get("units"), class_id) == units,
            f"{class_id}: group count differs",
        )
        per_slot = group.get("per_slot")
        _require(isinstance(per_slot, dict), f"{class_id}: missing slot census")
        _require(
            sum(_count(v, f"{class_id}/{k}") for k, v in per_slot.items()) == units,
            f"{class_id}: slot counts do not conserve",
        )
        direct_by_slot.update(per_slot)
        if class_id in base_ids:
            measurements[class_id] = {"units": units, "per_slot": per_slot}
        else:
            contract = contracts[class_id]["contract"]
            _require(
                units == contract["expected_units"],
                f"{class_id}: target multiplicity changed",
            )
            _require(
                per_slot == {contract["slot"]: units},
                f"{class_id}: target slot changed",
            )
    _require(
        _canonical_sha256(measurements) == BASE_CLASS_MEASUREMENTS_SHA256,
        "baseline class measurements changed",
    )
    for composition, units in compositions.items():
        _require(
            isinstance(composition, str)
            and bool(composition)
            and set(composition.split(" + ")) <= set(entries),
            "unproved total composition",
        )
        _count(units, composition)
    derived = _count(classification.get("derived_total_units"), "derived totals")
    classified = _count(classification.get("classified"), "classified")
    unexplained = _count(classification.get("unexplained"), "unexplained")
    mismatches = _count(classification.get("mismatches"), "mismatches")
    _require(
        sum(compositions.values()) == derived, "derived total counts do not conserve"
    )
    _require(
        sum(census.values()) + derived == classified
        and classified + unexplained == mismatches,
        "classification counts do not conserve",
    )
    _require(
        _count(classification.get("engine_errors"), "engine errors")
        == comparison["engine_errors"]
        == 0,
        "engine errors remain",
    )
    per_slot = comparison["per_slot"]
    _require(
        mismatches == sum(v.get("mismatch", 0) for v in per_slot.values()),
        "comparison mismatch census differs",
    )
    _require(
        derived <= per_slot["total"].get("mismatch", 0),
        "derived totals exceed comparison population",
    )
    _require(
        all(
            slot != "total" and count <= per_slot.get(slot, {}).get("mismatch", 0)
            for slot, count in direct_by_slot.items()
        ),
        "class census exceeds its component population",
    )
    remaining_slots = {
        slot: record.get("mismatch", 0) - direct_by_slot.get(slot, 0)
        for slot, record in per_slot.items()
        if slot != "total"
        and record.get("mismatch", 0) - direct_by_slot.get(slot, 0) > 0
    }
    remaining_direct = sum(remaining_slots.values())
    unexplained_group = groups.get("__unexplained__", {"units": 0, "per_slot": {}})
    _require(
        isinstance(unexplained_group, dict)
        and _count(unexplained_group.get("units"), "unexplained direct units")
        == remaining_direct
        and unexplained_group.get("per_slot") == remaining_slots,
        "unexplained component census does not rederive",
    )
    _require(
        unexplained
        == remaining_direct + per_slot["total"].get("mismatch", 0) - derived,
        "unexplained component and total counts do not conserve",
    )


def _validate_metadata_rebind(snapshot: _Snapshot) -> list[dict]:
    from scripts import rebind_us_tariff_publication as rebind

    # Every byte is either independently pinned baseline/proof evidence or an
    # exact derivative of it. Read derivatives through the publication snapshot
    # so a later concurrent change cannot leave a valid mixed-generation gate.
    for relative, expected in rebind.build(snapshot.root).items():
        _require(
            snapshot.read(relative) == expected,
            f"metadata-rebound artifact drift: {relative}",
        )
    return [
        {
            "claim": f"suite:{SUITE}:publication-metadata-rebind",
            "mode": "computed",
            "artifact": rebind.RECEIPT,
            "sha256": snapshot.sha256(rebind.RECEIPT),
        }
    ]


def validate_publication(
    report: dict, *, repo_root: Path = REPO_ROOT, report_path: str = REPORT_PATH
) -> tuple[list[dict], str]:
    """Authenticate the run-specific publication using committed small files."""
    snapshot = _Snapshot(Path(repo_root))
    try:
        _require(
            snapshot.json(report_path) == report, "report changed during validation"
        )
        ledger = yaml.load(snapshot.read(LEDGER_PATH), Loader=_UniqueSafeLoader)
        _require(isinstance(ledger, dict), "ledger must be an object")
        contracts, evidence = _proof_contracts(snapshot)
        entries, base_ids = _validate_enrollment(ledger, contracts)
        comparison = snapshot.json(COMPARISON_PATH)
        _require(
            snapshot.sha256(COMPARISON_PATH)
            == PINNED_CLASSIFICATION_INPUTS["comparison_receipt_sha256"],
            "comparison receipt changed",
        )
        for relative, expected_hash in PINNED_PROOFS.items():
            snapshot.json(relative)
            _require(
                snapshot.sha256(relative) == expected_hash,
                f"historical proof changed: {relative}",
            )
        evidence.extend(_validate_metadata_rebind(snapshot))
        classification = snapshot.json(CLASSIFICATION_PATH)
        _require(
            isinstance(TRUSTED_CLASSIFICATION_SHA256, str)
            and snapshot.sha256(CLASSIFICATION_PATH) == TRUSTED_CLASSIFICATION_SHA256,
            "final classification has not been independently audited or its bytes changed",
        )
        _require(
            classification.get("inputs")
            == {
                **PINNED_CLASSIFICATION_INPUTS,
                "disposition_ledger_sha256": snapshot.sha256(LEDGER_PATH),
            },
            "classification input bindings are stale",
        )
        _validate_classification(
            classification, entries, base_ids, contracts, comparison
        )
        expected_attribution = {
            class_id: {
                "units": classification["class_census"].get(class_id, 0),
                "attribution": entry["attribution"],
                "receipt": entry["receipt"],
                "bounds": entry["match"],
            }
            for class_id, entry in entries.items()
        }
        _require(
            report.get("classification")
            == {**classification, "class_attribution": expected_attribution},
            "report classification or attribution does not rederive",
        )
        slots = comparison["per_slot"]
        matches = sum(v.get("match", 0) for v in slots.values())
        mismatches = sum(v.get("mismatch", 0) for v in slots.values())
        _require(
            report.get("summary")
            == {
                "total": matches + mismatches,
                "matches": matches,
                "mismatches": mismatches,
                "explained": classification["classified"],
                "unexplained": classification["unexplained"],
                "engine_errors": comparison["engine_errors"],
            },
            "report summary does not rederive",
        )
        _require(
            report.get("output_summary") == slots,
            "report output census does not rederive",
        )
        for relative in (LEDGER_PATH, CLASSIFICATION_PATH):
            evidence.append(
                {
                    "claim": f"suite:{SUITE}:publication",
                    "mode": "computed",
                    "artifact": relative,
                    "sha256": snapshot.sha256(relative),
                }
            )
        snapshot.require_unchanged()
        # Return the authenticated report hash, never a later pathname hash.
        return evidence, snapshot.sha256(report_path)
    except (KeyError, TypeError, OSError, yaml.YAMLError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"tariff publication: missing or malformed evidence: {exc}"
        ) from exc
