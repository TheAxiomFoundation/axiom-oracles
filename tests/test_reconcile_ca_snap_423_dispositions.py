from __future__ import annotations

from copy import deepcopy

import pytest

from scripts import reconcile_ca_snap_423_dispositions as reconciliation


BASE_REF = "819f370bf0346e4a6a8dfb1c8c4f0d873d6d0340"


def _current_inputs():
    current_document, current_entries, _digest = (
        reconciliation._load_current_dispositions()
    )
    expanded = reconciliation._expanded_dispositions(current_entries)
    report, report_by_identity, cases_by_id, _report_digest = (
        reconciliation._load_and_validate_report(expanded)
    )
    current_issue_by_id = {
        entry["id"]: entry
        for entry in current_entries
        if entry["id"].startswith("ca-362-")
    }
    return (
        current_document,
        current_entries,
        expanded,
        report,
        report_by_identity,
        cases_by_id,
        current_issue_by_id,
    )


def test_literal_base_ref_is_hash_pinned_and_has_345_issue_rows():
    commit, document, entries = reconciliation._load_base_dispositions(BASE_REF)

    assert commit == BASE_REF
    assert document["suite"] == "ca-snap-ecps"
    assert len(document["entries"]) == 349
    assert len(entries) == 345
    assert (
        reconciliation._identity_digest(entries)
        == reconciliation.EXPECTED_BASE_IDENTITY_DIGEST
    )


def test_literal_base_hash_rejects_byte_drift(monkeypatch):
    commit = reconciliation._resolve_base_ref(BASE_REF)
    raw = reconciliation._git_show(
        commit,
        reconciliation.BASE_DISPOSITIONS_RELATIVE_PATH,
    )
    monkeypatch.setattr(
        reconciliation,
        "_git_show",
        lambda _commit, _path: raw + b"\n",
    )

    with pytest.raises(
        reconciliation.ReconciliationError,
        match="literal base dispositions sha256 mismatch",
    ):
        reconciliation._load_base_dispositions(BASE_REF)


@pytest.mark.parametrize("base_ref", ["", "   ", "--not-a-ref"])
def test_literal_base_ref_rejects_unsafe_values(base_ref):
    with pytest.raises(
        reconciliation.ReconciliationError,
        match="invalid base ref",
    ):
        reconciliation._resolve_base_ref(base_ref)


def test_report_runtime_provenance_is_pinned():
    report, _digest = reconciliation._json_document(
        reconciliation.CURRENT_REPORT_PATH,
        "current CA report",
    )
    tampered = deepcopy(report)
    tampered["engines"]["versions"]["policyengine_us"] = "9.999.0"

    with pytest.raises(
        reconciliation.ReconciliationError,
        match="engine/runtime stack drifted",
    ):
        reconciliation._validate_report_provenance(tampered)


def test_repository_reconciles_exact_partition_and_current_compact_schema():
    receipt = reconciliation.check_reconciliation(BASE_REF)

    assert receipt["base"] == {
        "commit": BASE_REF,
        "path": "dispositions/ca-snap-ecps.yaml",
        "sha256": reconciliation.BASE_DISPOSITIONS_SHA256,
        "identity_sha256": reconciliation.EXPECTED_BASE_IDENTITY_DIGEST,
    }
    partition = receipt["partition"]
    assert partition["base_rows"] == 345
    assert partition["vanished"]["count"] == 156
    assert partition["current_but_dropped"]["count"] == 17
    assert partition["reclassified"]["count"] == 41
    assert partition["kept"]["count"] == 131
    assert len(partition["drifted_rows"]) == 22
    assert (
        partition["drift_evidence_trace_sha256"]
        == reconciliation.REQUESTED_MONTH_TRACE_SHA256
    )
    assert partition["drifted_rows_sha256"] == reconciliation.EXPECTED_DRIFT_ROWS_SHA256
    assert (
        partition["active_drifted_rows_sha256"]
        == reconciliation.EXPECTED_ACTIVE_DRIFT_ROWS_SHA256
    )
    assert (
        partition["retired_drifted_rows_sha256"]
        == reconciliation.EXPECTED_RETIRED_DRIFT_ROWS_SHA256
    )
    assert partition["reclassified_replacements"] == {
        "counts": reconciliation.EXPECTED_RECLASSIFIED_REPLACEMENTS,
        "rows_sha256": reconciliation.EXPECTED_RECLASSIFIED_ROWS_SHA256,
        "rows": partition["reclassified_replacements"]["rows"],
    }
    assert len(partition["reclassified_replacements"]["rows"]) == 41
    assert receipt["retained_pin_movement"]["moved"]["count"] == 115
    assert receipt["retained_pin_movement"]["unchanged"]["count"] == 16
    assert receipt["retained_pin_movement"]["requested_month_evidence"] == {
        "count": 131,
        "trace_sha256": reconciliation.REQUESTED_MONTH_TRACE_SHA256,
        "rows_sha256": (reconciliation.EXPECTED_KEPT_REQUESTED_MONTH_ROWS_SHA256),
    }
    assert receipt["current"]["report"]["mismatches"] == 1058
    assert receipt["current"]["source_dispositions"]["expanded_rows"] == 866
    assert receipt["current"]["compact"]["cases"] == 7101
    assert receipt["current"]["compact"]["mismatches"] == 1058
    assert receipt["current"]["compact"]["annotated"] == 866

    # This literal #423 identity remains a mismatch, but the rerun's causal
    # selector now supplies its annotation instead of the retired direct id.
    assert (
        "ca-362-self-employment-ecps-58241-benefit" in partition["reclassified"]["ids"]
    )


def test_equal_count_partition_swap_fails_identity_digest():
    _commit, _document, base_entries = reconciliation._load_base_dispositions(BASE_REF)
    (
        _current_document,
        _current_entries,
        expanded,
        _report,
        report_by_identity,
        _cases_by_id,
        current_issue_by_id,
    ) = _current_inputs()
    partitions = reconciliation._partition_base_entries(
        base_entries,
        report_by_identity,
        current_issue_by_id,
        expanded,
    )
    kept = partitions["kept"][0]
    dropped = partitions["current_but_dropped"][0]

    tampered = dict(current_issue_by_id)
    tampered_expanded = dict(expanded)
    del tampered[kept["id"]]
    del tampered_expanded[reconciliation._identity(kept)]
    tampered[dropped["id"]] = dropped

    with pytest.raises(
        reconciliation.ReconciliationError,
        match="identity digest mismatch",
    ):
        reconciliation._partition_base_entries(
            base_entries,
            report_by_identity,
            tampered,
            tampered_expanded,
        )


def test_reclassified_receipt_rejects_equal_count_replacement_swap():
    (
        _current_document,
        _current_entries,
        expanded,
        _report,
        report_by_identity,
        _cases_by_id,
        current_issue_by_id,
    ) = _current_inputs()
    _commit, _document, base_entries = reconciliation._load_base_dispositions(BASE_REF)
    partitions = reconciliation._partition_base_entries(
        base_entries,
        report_by_identity,
        current_issue_by_id,
        expanded,
    )
    paired = next(
        entry
        for entry in partitions["reclassified"]
        if expanded[reconciliation._identity(entry)]["id"]
        == "ca-mce-pe-extra-net-test-paired-benefit"
    )
    benefit_only = next(
        entry
        for entry in partitions["reclassified"]
        if expanded[reconciliation._identity(entry)]["id"]
        == "ca-mce-pe-extra-net-test-benefit-only"
    )
    paired_key = reconciliation._identity(paired)
    benefit_only_key = reconciliation._identity(benefit_only)
    tampered_expanded = dict(expanded)
    tampered_expanded[paired_key] = deepcopy(expanded[paired_key])
    tampered_expanded[benefit_only_key] = deepcopy(expanded[benefit_only_key])
    tampered_expanded[paired_key]["id"], tampered_expanded[benefit_only_key]["id"] = (
        tampered_expanded[benefit_only_key]["id"],
        tampered_expanded[paired_key]["id"],
    )

    with pytest.raises(
        reconciliation.ReconciliationError,
        match="reclassified replacement receipt digest mismatch",
    ):
        reconciliation._partition_receipt(
            partitions,
            report_by_identity,
            current_issue_by_id,
            tampered_expanded,
        )


def test_compact_checker_rejects_retired_output_schema():
    (
        _current_document,
        _current_entries,
        _expanded,
        report,
        report_by_identity,
        cases_by_id,
        _current_issue_by_id,
    ) = _current_inputs()
    index, rows, _receipt = reconciliation._load_compact_rows(
        report,
        report_by_identity,
        cases_by_id,
    )
    tampered = list(rows)
    tampered[0] = {**tampered[0], "o": []}

    with pytest.raises(
        reconciliation.ReconciliationError,
        match="not exact id/r/h/m schema",
    ):
        reconciliation._validate_compact_rows(
            report,
            report_by_identity,
            cases_by_id,
            index,
            tampered,
        )


def test_compact_checker_rejects_silent_annotation():
    (
        _current_document,
        _current_entries,
        _expanded,
        report,
        report_by_identity,
        cases_by_id,
        _current_issue_by_id,
    ) = _current_inputs()
    index, rows, _receipt = reconciliation._load_compact_rows(
        report,
        report_by_identity,
        cases_by_id,
    )
    target_index = next(
        index for index, row in enumerate(rows) if row["m"] and "e" not in row["m"][0]
    )
    tampered = list(rows)
    replacement = deepcopy(tampered[target_index])
    replacement["m"][0]["e"] = "bridge_artifact"
    tampered[target_index] = replacement

    with pytest.raises(
        reconciliation.ReconciliationError,
        match="compact mismatch payload drift",
    ):
        reconciliation._validate_compact_rows(
            report,
            report_by_identity,
            cases_by_id,
            index,
            tampered,
        )


@pytest.mark.parametrize("case_id", ["ecps-59082", "ecps-62506"])
def test_compact_checker_requires_merged_only_vanished_households(case_id):
    (
        _current_document,
        _current_entries,
        expanded,
        report,
        report_by_identity,
        cases_by_id,
        current_issue_by_id,
    ) = _current_inputs()
    _commit, _document, base_entries = reconciliation._load_base_dispositions(BASE_REF)
    partitions = reconciliation._partition_base_entries(
        base_entries,
        report_by_identity,
        current_issue_by_id,
        expanded,
    )
    _index, rows, _receipt = reconciliation._load_compact_rows(
        report,
        report_by_identity,
        cases_by_id,
    )
    tampered = deepcopy(rows)
    target = next(row for row in tampered if row["id"] == case_id)
    target["id"] = f"{case_id}-fabricated-replacement"

    with pytest.raises(
        reconciliation.ReconciliationError,
        match="is absent from compact cases",
    ):
        reconciliation._validate_partition_compact_evidence(
            partitions,
            tampered,
        )


def test_kept_requested_month_digest_rejects_self_consistent_pin_tampering():
    (
        _current_document,
        _current_entries,
        expanded,
        _report,
        report_by_identity,
        _cases_by_id,
        current_issue_by_id,
    ) = _current_inputs()
    _commit, _document, base_entries = reconciliation._load_base_dispositions(BASE_REF)
    partitions = reconciliation._partition_base_entries(
        base_entries,
        report_by_identity,
        current_issue_by_id,
        expanded,
    )
    target = partitions["kept"][0]
    entry_id = target["id"]
    key = reconciliation._identity(target)
    tampered_report = deepcopy(report_by_identity)
    tampered_source = dict(current_issue_by_id)
    tampered_source[entry_id] = deepcopy(current_issue_by_id[entry_id])
    tampered_expanded = dict(expanded)
    tampered_report[key]["left"] += 50
    tampered_report[key]["difference"] += 50
    tampered_source[entry_id]["pinned"] = reconciliation._pin(tampered_report[key])
    tampered_expanded[key] = tampered_source[entry_id]

    with pytest.raises(
        reconciliation.ReconciliationError,
        match="kept requested-month receipt digest mismatch",
    ):
        reconciliation._partition_receipt(
            partitions,
            tampered_report,
            tampered_source,
            tampered_expanded,
        )


def test_full_drift_receipt_digest_catches_current_pin_tampering():
    (
        _current_document,
        _current_entries,
        expanded,
        _report,
        report_by_identity,
        _cases_by_id,
        current_issue_by_id,
    ) = _current_inputs()
    _commit, _document, base_entries = reconciliation._load_base_dispositions(BASE_REF)
    partitions = reconciliation._partition_base_entries(
        base_entries,
        report_by_identity,
        current_issue_by_id,
        expanded,
    )
    target = partitions["current_but_dropped"][0]
    key = reconciliation._identity(target)
    tampered_report = deepcopy(report_by_identity)
    tampered_report[key]["left"] += 1
    tampered_report[key]["difference"] += 1

    with pytest.raises(
        reconciliation.ReconciliationError,
        match="full drift-row receipt digest mismatch",
    ):
        reconciliation._partition_receipt(
            partitions,
            tampered_report,
            current_issue_by_id,
            expanded,
        )


def test_full_drift_receipt_digest_catches_retired_pin_tampering(monkeypatch):
    (
        _current_document,
        _current_entries,
        expanded,
        _report,
        report_by_identity,
        _cases_by_id,
        current_issue_by_id,
    ) = _current_inputs()
    _commit, _document, base_entries = reconciliation._load_base_dispositions(BASE_REF)
    partitions = reconciliation._partition_base_entries(
        base_entries,
        report_by_identity,
        current_issue_by_id,
        expanded,
    )
    tampered = deepcopy(reconciliation.RETIRED_CURRENT_DRIFT_PINS)
    entry_id = sorted(tampered)[0]
    tampered[entry_id]["right"] += 1
    monkeypatch.setattr(reconciliation, "RETIRED_CURRENT_DRIFT_PINS", tampered)

    with pytest.raises(
        reconciliation.ReconciliationError,
        match="full drift-row receipt digest mismatch",
    ):
        reconciliation._partition_receipt(
            partitions,
            report_by_identity,
            current_issue_by_id,
            expanded,
        )
