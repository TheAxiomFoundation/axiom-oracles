"""Adversarial tests for the mandatory causal-proof publication gate."""

from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import shutil

import pytest
import yaml

from scripts import certify
from scripts import us_tariff_publication as publication
from scripts import us_tariff_schedule_campaign as campaign

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def contracts():
    result, _evidence = publication._proof_contracts(publication._Snapshot(REPO))
    return result


@pytest.fixture
def enrollment(contracts):
    ledger = yaml.safe_load((REPO / publication.LEDGER_PATH).read_text())
    retired = getattr(publication, "RETIRED_BASE_IDS", frozenset())
    ledger["entries"] = [
        entry
        for entry in ledger["entries"]
        if entry["id"] not in contracts and entry["id"] not in retired
    ]
    for class_id, evidence in contracts.items():
        contract = evidence["contract"]
        ledger["entries"].append(
            {
                "id": class_id,
                "kind": "signature_class",
                "match": {},
                **{
                    key: deepcopy(contract[key])
                    for key in (
                        "disposition",
                        "attribution",
                        "expected_units",
                        "expected_signature_count",
                        "expected_signature_population_sha256",
                        "signatures",
                    )
                },
                "expires_on_source_change": True,
                "receipt": "Synthetic enrollment of the authenticated proof contract.",
                "reason": "Fixture for the publication consumer, not an emitted classification.",
                "evidence": {
                    "instrument_receipt": "synthetic-publication-fixture",
                    "receipt_type": "authenticated-causal-proof",
                    "sources": [evidence["binding"]["receipt"]],
                    evidence["marker"]: deepcopy(evidence["binding"]),
                },
            }
        )
    return ledger


def test_exact_authenticated_enrollment_is_valid(enrollment, contracts):
    entries, base_ids = publication._validate_enrollment(enrollment, contracts)
    assert len(base_ids) == publication.BASE_ENTRY_COUNT
    assert len(entries) == publication.BASE_ENTRY_COUNT + len(contracts)


def test_live_committed_publication_is_authenticated_and_conformant() -> None:
    report_path = REPO / publication.REPORT_PATH
    report = json.loads(report_path.read_text())

    evidence, authenticated_report_sha256 = publication.validate_publication(
        report, repo_root=REPO
    )

    assert report["conformant"] is True
    assert report["summary"]["unexplained"] == 0
    assert report["summary"]["engine_errors"] == 0
    assert (
        authenticated_report_sha256
        == hashlib.sha256(report_path.read_bytes()).hexdigest()
    )
    assert {row["artifact"] for row in evidence} >= {
        publication.LEDGER_PATH,
        publication.CLASSIFICATION_PATH,
    }


@pytest.mark.parametrize(
    "class_id",
    [
        "section232-steel-scope-projection-brazil",
        "yale-html-statutory-base-parser-defect",
        "section232-russia-aluminum-membership-vintage",
    ],
)
@pytest.mark.parametrize(
    "mutation",
    [
        "rename",
        "remove",
        "duplicate",
        "widen-baseline",
        "reorder-baseline",
        "unlisted-signature",
        "same-count-signature-substitution",
        "no-match-field",
        "broad-match",
        "wrong-count",
        "wrong-attribution",
        "no-expiry",
        "missing-marker",
        "stale-proof-hash",
        "substituted-identity-population",
        "missing-source",
    ],
)
def test_enrollment_bypass_mutants_are_rejected(
    enrollment, contracts, class_id, mutation
):
    mutant = deepcopy(enrollment)
    target = next(e for e in mutant["entries"] if e["id"] == class_id)
    marker = contracts[class_id]["marker"]
    if mutation == "rename":
        target["id"] = "renamed-to-avoid-proof-gate"
    elif mutation == "remove":
        mutant["entries"].remove(target)
    elif mutation == "duplicate":
        mutant["entries"].append(deepcopy(target))
    elif mutation == "widen-baseline":
        mutant["entries"][0]["match"] = {"slot": "base"}
    elif mutation == "reorder-baseline":
        mutant["entries"][0], mutant["entries"][1] = (
            mutant["entries"][1],
            mutant["entries"][0],
        )
    elif mutation == "unlisted-signature":
        target["signatures"].append("0" * 64)
    elif mutation == "same-count-signature-substitution":
        target["signatures"][0] = "0" * 64
    elif mutation == "no-match-field":
        del target["match"]
    elif mutation == "broad-match":
        target["match"] = {"slot": "brazil_section_301"}
    elif mutation == "wrong-count":
        target["expected_units"] += 1
    elif mutation == "wrong-attribution":
        target["attribution"] = "upstream-methodology"
    elif mutation == "no-expiry":
        target["expires_on_source_change"] = False
    elif mutation == "missing-marker":
        del target["evidence"][marker]
    elif mutation == "stale-proof-hash":
        target["evidence"][marker]["sha256"] = "0" * 64
    elif mutation == "substituted-identity-population":
        target["evidence"][marker]["identity_population_sha256"] = "0" * 64
    elif mutation == "missing-source":
        target["evidence"]["sources"] = []
    with pytest.raises(ValueError):
        publication._validate_enrollment(mutant, contracts)


def test_empty_structured_match_does_not_claim_unlisted_signatures(
    enrollment, contracts
):
    entries = [e for e in enrollment["entries"] if e["id"] in contracts]
    selected = entries[0]
    assert (
        campaign.matching_class_id(selected["signatures"][0], {}, entries)
        == selected["id"]
    )
    assert campaign.matching_class_id("0" * 64, {}, entries) is None


def _write_json(root, relative, document):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")


@pytest.fixture
def publication_fixture(tmp_path, enrollment, contracts, monkeypatch):
    """Real authenticated small proofs; synthetic OPEN aggregate consumer data.

    No raw comparison scan or clean-conformance claim is represented by this
    fixture. All totals deliberately stay unexplained, isolating this gate.
    """
    # This synthetic OPEN classification is not the frozen campaign rebind.
    # Its new metadata gate has independent real-baseline/mutant coverage in
    # test_us_tariff_publication_rebind.py; this fixture isolates other gates.
    monkeypatch.setattr(publication, "_validate_metadata_rebind", lambda _: [])

    def copy_path(relative):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / relative, path)

    def copy_receipted_files(value):
        if isinstance(value, dict):
            path = value.get("path")
            if (
                isinstance(path, str)
                and not Path(path).is_absolute()
                and (REPO / path).is_file()
            ):
                copy_path(path)
            for item in value.values():
                copy_receipted_files(item)
        elif isinstance(value, list):
            for item in value:
                copy_receipted_files(item)

    for _marker, _module, relative in publication.PROOF_SPECS:
        proof = json.loads((REPO / relative).read_text())
        copy_path(relative)
        copy_receipted_files(proof["producer"])
        copy_receipted_files(proof["inputs"])
    for relative in publication.PINNED_PROOFS:
        copy_path(relative)
    copy_path(publication.COMPARISON_PATH)
    ledger_path = tmp_path / publication.LEDGER_PATH
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(yaml.safe_dump(enrollment, sort_keys=False))
    entries, base_ids = publication._validate_enrollment(enrollment, contracts)
    actual = json.loads((REPO / publication.CLASSIFICATION_PATH).read_text())
    comparison = json.loads((REPO / publication.COMPARISON_PATH).read_text())
    census = {key: actual["class_census"].get(key, 0) for key in base_ids}
    groups = {
        key: deepcopy(actual["groups"][key])
        for key in base_ids
        if key in actual["groups"]
    }
    for class_id, authenticated in contracts.items():
        contract = authenticated["contract"]
        census[class_id] = contract["expected_units"]
        groups[class_id] = {
            "units": contract["expected_units"],
            "per_slot": {contract["slot"]: contract["expected_units"]},
        }
    classified = sum(census.values())
    mismatches = sum(v.get("mismatch", 0) for v in comparison["per_slot"].values())
    direct_slots = {}
    for group in groups.values():
        for slot, count in group["per_slot"].items():
            direct_slots[slot] = direct_slots.get(slot, 0) + count
    unexplained_slots = {
        slot: data.get("mismatch", 0) - direct_slots.get(slot, 0)
        for slot, data in comparison["per_slot"].items()
        if slot != "total" and data.get("mismatch", 0) - direct_slots.get(slot, 0) > 0
    }
    if unexplained_slots:
        groups["__unexplained__"] = {
            "units": sum(unexplained_slots.values()),
            "per_slot": unexplained_slots,
        }
    classification = {
        **actual,
        "class_census": census,
        "groups": groups,
        "selector_count": len(entries),
        "derived_total_units": 0,
        "derived_total_compositions": {},
        "classified": classified,
        "unexplained": mismatches - classified,
        "inputs": {
            **publication.PINNED_CLASSIFICATION_INPUTS,
            "disposition_ledger_sha256": hashlib.sha256(
                ledger_path.read_bytes()
            ).hexdigest(),
        },
    }
    _write_json(tmp_path, publication.CLASSIFICATION_PATH, classification)
    # Only this synthetic fixture's immutable classification bytes substitute
    # for the independently audited live-run anchor. Mutants cannot rebind it.
    monkeypatch.setattr(
        publication,
        "TRUSTED_CLASSIFICATION_SHA256",
        hashlib.sha256(
            (tmp_path / publication.CLASSIFICATION_PATH).read_bytes()
        ).hexdigest(),
    )
    matches = sum(v.get("match", 0) for v in comparison["per_slot"].values())
    report = {
        "schema": "axiom.comparison_report.v2",
        "suite": publication.SUITE,
        "conformant": False,
        "summary": {
            "total": matches + mismatches,
            "matches": matches,
            "mismatches": mismatches,
            "explained": classified,
            "unexplained": mismatches - classified,
            "engine_errors": 0,
        },
        "output_summary": comparison["per_slot"],
        "classification": {
            **classification,
            "class_attribution": {
                key: {
                    "units": census.get(key, 0),
                    "attribution": entry["attribution"],
                    "receipt": entry["receipt"],
                    "bounds": entry["match"],
                }
                for key, entry in entries.items()
            },
        },
    }
    _write_json(tmp_path, publication.REPORT_PATH, report)
    assert report["summary"]["unexplained"] > 0
    return tmp_path, report


def test_publication_checks_real_proofs_without_bulk_replay(publication_fixture):
    root, report = publication_fixture
    evidence, report_hash = publication.validate_publication(report, repo_root=root)
    assert len(evidence) == len(publication.PROOF_SPECS) + 2
    assert (
        report_hash
        == hashlib.sha256((root / publication.REPORT_PATH).read_bytes()).hexdigest()
    )


@pytest.mark.parametrize("proof_index", [0, 1])
@pytest.mark.parametrize(
    "mutation",
    [
        "missing-proof",
        "stale-proof",
        "renamed-class",
        "stale-ledger-binding",
        "baseline-count",
        "target-multiplicity",
        "report-attribution",
        "population",
        "duplicate-ledger-key",
        "duplicate-report-key",
        "duplicate-proof-key",
        "drift-during-validation",
    ],
)
def test_full_publication_mutants_are_rejected(
    publication_fixture, contracts, monkeypatch, mutation, proof_index
):
    root, report = publication_fixture
    marker = publication.PROOF_SPECS[proof_index][0]
    class_id = next(
        name for name, evidence in contracts.items() if evidence["marker"] == marker
    )
    proof_relative = contracts[class_id]["binding"]["receipt"]
    if mutation == "missing-proof":
        (root / proof_relative).unlink()
    elif mutation == "stale-proof":
        proof_path = root / proof_relative
        proof = json.loads(proof_path.read_text())
        proof["verdict"] = "FAIL"
        _write_json(root, proof_relative, proof)
    elif mutation == "renamed-class":
        path = root / publication.LEDGER_PATH
        path.write_text(
            path.read_text().replace(class_id, "renamed-to-avoid-proof-gate")
        )
    elif mutation == "stale-ledger-binding":
        path = root / publication.LEDGER_PATH
        path.write_text(path.read_text() + "\n# same parsed data, new bytes\n")
    elif mutation == "report-attribution":
        report["classification"]["class_attribution"][class_id]["attribution"] = (
            "upstream-methodology"
        )
        _write_json(root, publication.REPORT_PATH, report)
    elif mutation in {"baseline-count", "target-multiplicity", "population"}:
        classification = json.loads(
            (root / publication.CLASSIFICATION_PATH).read_text()
        )
        if mutation == "population":
            classification["classification_population"]["accumulators"][0] = "0" * 64
        else:
            key = (
                class_id
                if mutation == "target-multiplicity"
                else next(
                    k for k in classification["class_census"] if k not in contracts
                )
            )
            classification["class_census"][key] += 1
        _write_json(root, publication.CLASSIFICATION_PATH, classification)
    elif mutation == "duplicate-ledger-key":
        path = root / publication.LEDGER_PATH
        path.write_text(path.read_text() + "\nsuite: us-tariff-schedule\n")
    elif mutation in {"duplicate-report-key", "duplicate-proof-key"}:
        relative = (
            publication.REPORT_PATH
            if mutation == "duplicate-report-key"
            else proof_relative
        )
        path = root / relative
        path.write_text(path.read_text().replace("{", '{"schema":"duplicate",', 1))
    elif mutation == "drift-during-validation":
        original = publication._validate_enrollment

        def drift(ledger, authenticated):
            result = original(ledger, authenticated)
            path = root / proof_relative
            path.write_text(path.read_text() + "\n")
            return result

        monkeypatch.setattr(publication, "_validate_enrollment", drift)
    with pytest.raises(ValueError):
        publication.validate_publication(report, repo_root=root)


@pytest.mark.parametrize(
    "class_id", ["section232-steel-scope-projection-brazil", "renamed-class", ""]
)
def test_certificate_cannot_skip_proof_gate_by_renaming_or_removing_class(
    tmp_path, monkeypatch, class_id
):
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    entry = {
        "suite": publication.SUITE,
        "oracle_type": "reference",
        "oracle": "synthetic",
        "report": "synthetic.json",
    }
    census = {class_id: 1} if class_id else {}
    report = {
        "schema": "axiom.comparison_report.v2",
        "suite": publication.SUITE,
        "conformant": True,
        "summary": {
            "total": 2,
            "matches": 1,
            "mismatches": 1,
            "explained": 1,
            "unexplained": 0,
            "engine_errors": 0,
        },
        "scoreboard": {
            "conformant": True,
            "derivation": "unexplained == 0 and engine_errors == 0",
        },
        "classification": {
            "class_census": census,
            "class_attribution": {
                key: {"units": units, "attribution": "input-comparability"}
                for key, units in census.items()
            },
        },
        "scope": {"open": {"status": "OPEN", "axiom_attributed_open_classes": {}}},
    }
    _write_json(tmp_path, entry["report"], report)
    calls = []

    def rejected_proof(actual_report, actual_entry):
        calls.append((actual_report, actual_entry))
        raise ValueError("deliberately missing causal proof")

    monkeypatch.setattr(certify, "_validate_tariff_publication", rejected_proof)
    leg, _evidence, defects = certify._tariff_schedule_suite_verdict(entry)
    assert len(calls) == 1
    assert leg["clean"] is False
    assert any("deliberately missing causal proof" in defect for defect in defects)


def test_missing_independent_classification_anchor_is_rejected(
    publication_fixture, monkeypatch
):
    root, report = publication_fixture
    monkeypatch.setattr(publication, "TRUSTED_CLASSIFICATION_SHA256", None)
    with pytest.raises(ValueError, match="independently audited"):
        publication.validate_publication(report, repo_root=root)


def test_coordinated_total_relabeling_cannot_reuse_raw_population_digest(
    publication_fixture, contracts
):
    root, report = publication_fixture
    classification = json.loads((root / publication.CLASSIFICATION_PATH).read_text())
    # The raw population digest and every proof/ledger binding stay unchanged.
    # Only total assignment and its conserved aggregate views lie.
    target = next(iter(contracts))
    totals = report["output_summary"]["total"]["mismatch"]
    classification["derived_total_compositions"] = {target: totals}
    classification["derived_total_units"] = totals
    classification["classified"] += totals
    classification["unexplained"] -= totals
    report["classification"].update(classification)
    report["summary"]["explained"] += totals
    report["summary"]["unexplained"] -= totals
    _write_json(root, publication.CLASSIFICATION_PATH, classification)
    _write_json(root, publication.REPORT_PATH, report)
    with pytest.raises(ValueError, match="independently audited"):
        publication.validate_publication(report, repo_root=root)


@pytest.mark.parametrize("proof_index", [0, 1])
def test_source_capture_aba_cannot_validate_unpinned_snapshot(
    publication_fixture, monkeypatch, proof_index
):
    root, report = publication_fixture
    _marker, module_name, relative = publication.PROOF_SPECS[proof_index]
    proof = json.loads((root / relative).read_text())
    source_path = root / proof["producer"]["script"]["path"]
    correct = source_path.read_bytes()
    unpinned = correct + b"\n# unpinned snapshot\n"
    source_path.write_bytes(unpinned)
    producer = importlib.import_module(module_name)
    original_validator = producer.validate_artifact
    calls = []

    def temporary_good_source(document, *, repo_root):
        calls.append(True)
        source_path.write_bytes(correct)
        try:
            return original_validator(document, repo_root=repo_root)
        finally:
            source_path.write_bytes(unpinned)

    monkeypatch.setattr(producer, "validate_artifact", temporary_good_source)
    with pytest.raises(ValueError, match="captured proof source/input differs"):
        publication.validate_publication(report, repo_root=root)
    assert calls == []


def test_certificate_rejects_report_replacement_after_successful_gate(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    entry = {
        "suite": publication.SUITE,
        "oracle_type": "reference",
        "oracle": "synthetic",
        "report": "synthetic.json",
    }
    report = {
        "schema": "axiom.comparison_report.v2",
        "suite": publication.SUITE,
        "conformant": True,
        "summary": {
            "total": 2,
            "matches": 1,
            "mismatches": 1,
            "explained": 1,
            "unexplained": 0,
            "engine_errors": 0,
        },
        "scoreboard": {
            "conformant": True,
            "derivation": "unexplained == 0 and engine_errors == 0",
        },
        "classification": {
            "class_census": {"synthetic": 1},
            "class_attribution": {
                "synthetic": {"units": 1, "attribution": "input-comparability"}
            },
        },
        "scope": {"open": {"status": "OPEN", "axiom_attributed_open_classes": {}}},
    }
    _write_json(tmp_path, entry["report"], report)
    path = tmp_path / entry["report"]
    validated_hash = hashlib.sha256(path.read_bytes()).hexdigest()

    def valid_gate(_report, _entry):
        return [], validated_hash

    monkeypatch.setattr(certify, "_validate_tariff_publication", valid_gate)
    baseline, _evidence, defects = certify._tariff_schedule_suite_verdict(entry)
    assert baseline["clean"] is True and not defects

    def replace_after_gate(_report, _entry):
        replacement = deepcopy(report)
        replacement["summary"].update(unexplained=1, explained=0)
        replacement["conformant"] = False
        replacement["scoreboard"]["conformant"] = False
        temporary = tmp_path / "replacement.json"
        temporary.write_text(json.dumps(replacement))
        temporary.replace(path)
        return [], validated_hash

    monkeypatch.setattr(certify, "_validate_tariff_publication", replace_after_gate)
    leg, evidence, defects = certify._tariff_schedule_suite_verdict(entry)
    assert leg["clean"] is False
    assert any("report changed after publication" in defect for defect in defects)
    assert evidence[0]["sha256"] == validated_hash
    assert evidence[0]["sha256"] != hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("proof_index", [0, 1])
def test_missing_mandatory_source_cannot_appear_only_during_validator(
    publication_fixture, monkeypatch, proof_index
):
    root, report = publication_fixture
    _marker, module_name, relative = publication.PROOF_SPECS[proof_index]
    proof = json.loads((root / relative).read_text())
    source_path = root / proof["producer"]["script"]["path"]
    correct = source_path.read_bytes()
    source_path.unlink()
    producer = importlib.import_module(module_name)
    original_validator = producer.validate_artifact
    calls = []

    def temporary_source(document, *, repo_root):
        calls.append(True)
        source_path.write_bytes(correct)
        try:
            return original_validator(document, repo_root=repo_root)
        finally:
            source_path.unlink()

    monkeypatch.setattr(producer, "validate_artifact", temporary_source)
    with pytest.raises(ValueError, match="missing or malformed evidence"):
        publication.validate_publication(report, repo_root=root)
    assert calls == []
