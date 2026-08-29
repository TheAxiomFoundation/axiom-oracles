"""Hermetic regressions for the preview disposition receipt builder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import build_us_tariff_preview_disposition_receipt as builder


def test_preview_root_defaults_to_repo_local_inputs() -> None:
    args = builder.parse_args([])

    assert args.preview_root == builder.PREVIEW
    assert builder.resolve_input_paths(args.preview_root) == {
        path: path for path in builder.EXPECTED_HASHES
    }


def test_preview_root_redirects_only_preview_inputs(tmp_path: Path) -> None:
    args = builder.parse_args(["--preview-root", str(tmp_path)])
    resolved = builder.resolve_input_paths(args.preview_root)

    assert {
        logical: physical
        for logical, physical in resolved.items()
        if logical in builder.PREVIEW_INPUTS
    } == {
        logical: tmp_path / logical.name for logical in builder.PREVIEW_INPUTS
    }
    assert resolved[builder.SELECTED_INTERVALS] == builder.SELECTED_INTERVALS


def test_external_preview_input_keeps_logical_receipt_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    logical_path = builder.TARGET_MISMATCH
    physical_path = tmp_path / logical_path.name
    physical_path.write_bytes(b"pinned preview input\n")
    monkeypatch.setitem(
        builder.EXPECTED_HASHES, logical_path, builder.sha256(physical_path)
    )

    receipt = builder.input_receipt(physical_path, logical_path=logical_path)

    assert receipt == {
        "path": builder.relative(logical_path),
        "bytes": physical_path.stat().st_size,
        "sha256": builder.sha256(physical_path),
    }


def _new_row(**overrides):
    row = {
        "case_id": "case",
        "probe": "start",
        "slot": "brazil_section_301",
        "delta": 0.25,
        "taxonomy_primary": "brazil-aircraft",
        "yale_full_list_statistical_broadening": None,
        "context": {
            "flags": {"entry_is_section_232_covered": True},
            "hts10": "7304313000",
            "hts_line": "7304313000",
            "interval": ["2026-07-22", "2026-07-23"],
            "iso2": "BR",
        },
    }
    row.update(overrides)
    return row


def test_positive_section232_fact_precedes_aircraft_taxonomy() -> None:
    assert builder.classify_new_row(
        _new_row(), {}, lambda _code, _probe: None, 0.5
    ) == ("section232-exposed-brazil", "section232-exposed-unconsumed")


def test_positive_section232_heading_precedes_hts8_broadening() -> None:
    row = _new_row(
        taxonomy_primary="unmapped",
        yale_full_list_statistical_broadening={
            "yale_hts8": "85371091",
            "legal_hts10": "8537109170",
        },
        context={
            "flags": {"entry_is_section_232_covered": False},
            "hts10": "8537109120",
            "hts_line": "8537109100",
            "interval": ["2026-07-22", "2026-07-23"],
            "iso2": "BR",
        },
    )
    assert builder.classify_new_row(
        row, {"semiconductor": {"85371091"}}, lambda _code, _probe: None, 0.5
    ) == ("section232-heading-brazil", "section232-heading-program")


def test_positive_section232_annex_precedes_aircraft_taxonomy() -> None:
    row = _new_row(
        slot="forced_labor_section_301",
        taxonomy_primary="forced-aircraft",
        context={
            "flags": {"entry_is_section_232_covered": False},
            "hts10": "7616995190",
            "hts_line": "7616995100",
            "interval": ["2026-07-24", "2026-07-30"],
            "iso2": "CA",
        },
    )
    assert builder.classify_new_row(
        row, {}, lambda _code, _probe: "annex_1a", 0.5
    ) == ("section232-annex-forced-labor", "section232-annex-membership")


def test_zero_rate_aircraft_is_not_promoted_by_membership() -> None:
    row = _new_row()
    with pytest.raises(ValueError, match="aircraft row lacks positive statutory authority"):
        builder.classify_new_row(row, {}, lambda _code, _probe: None, 0)


def test_positive_rate_without_grounded_subcause_fails_closed() -> None:
    row = _new_row(taxonomy_primary="brazil-pharma")
    row["context"]["flags"]["entry_is_section_232_covered"] = False
    with pytest.raises(ValueError, match="positive statutory Section-232 row"):
        builder.classify_new_row(row, {}, lambda _code, _probe: None, 0.5)


def test_committed_receipt_records_corrected_open_population() -> None:
    receipt = json.loads(builder.DEFAULT_OUTPUT.read_text())
    selectors = {selector["id"]: selector for selector in receipt["selectors"]}

    assert receipt["producer"] == {
        "script": builder.source_receipt(builder.PRODUCER_SOURCE),
        "campaign_classifier": builder.source_receipt(builder.CAMPAIGN_SOURCE),
    }
    assert {
        selector_id: selector["expected_units"]
        for selector_id, selector in selectors.items()
    } == builder.EXPECTED_SELECTOR_UNITS
    assert receipt["census"]["per_logical_class"] == builder.EXPECTED_LOGICAL_UNITS
    for selector in selectors.values():
        assert (selector["disposition"], selector["attribution"]) == (
            builder.EXPECTED_LOGICAL_RULINGS[selector["logical_class"]]
        )
    open_units = sum(
        selector["expected_units"]
        for selector in selectors.values()
        if selector["attribution"] == "axiom-attributed-open"
    )
    assert open_units == builder.EXPECTED_AXIOM_OPEN_UNITS == 244_188
    assert receipt["census"]["per_attribution"]["axiom-attributed-open"] == open_units
    assert (
        receipt["evidence_census"]["statutory_precedence_overrides"]
        == builder.EXPECTED_STATUTORY_PRECEDENCE_OVERRIDES
    )
    assert (
        receipt["evidence_census"]["positive_statutory_section232_units"]
        == builder.EXPECTED_SECTION232_UNITS
    )
    assert {
        name: item["sha256"] for name, item in receipt["inputs"].items()
    } == {
        builder.relative(path): expected_sha
        for path, expected_sha in builder.EXPECTED_HASHES.items()
    }
    assert not any(selector_id.startswith("yale-zero-aircraft-") for selector_id in selectors)
    assert sum(
        selector["expected_units"]
        for selector in selectors.values()
        if selector["logical_class"].startswith("section232-")
    ) == builder.EXPECTED_SECTION232_UNITS == 226_784
