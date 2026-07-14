"""UK-CTR calculator-oracle report builder + run_comparison runner."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from axiom_oracles.adapters.entitledto import CAPTURE_STATUS_CAPTURED
from axiom_oracles.adapters.entitledto.report import (
    DEFAULT_PE_REFERENCE,
    build_uk_ctr_report,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_pending_report_grades_nothing_but_carries_pe_and_statutory() -> None:
    report = build_uk_ctr_report()
    assert report["capture"] == {
        "status": "pending_capture",
        "captured": 0,
        "pending": 8,
        "protocol": "axiom_oracles/adapters/entitledto/fixtures/uk_ctr/"
        "CAPTURE-PROTOCOL.md",
    }
    assert report["summary"]["comparison_count"] == 0
    assert len(report["cases"]) == 8
    by_id = {c["case_id"]: c for c in report["cases"]}

    # National schemes: the statutory hand-check equals PolicyEngine exactly
    # (PE implements the national statute), so PE is a sound oracle there.
    for cid in (
        "ctr-eng-pa-birmingham-couple-gc",
        "ctr-eng-pa-cornwall-single-taper",
        "ctr-sco-wa-glasgow-single-earner",
        "ctr-wal-wa-cardiff-couple-2kids",
        "ctr-eng-pa-kingston-single",
    ):
        row = by_id[cid]
        assert row["hand_computed_statutory"]["annual_gbp"] == (
            row["policyengine"]["annual_gbp"]
        ), cid

    # Unsupported councils: PolicyEngine returns 0 (reported fallback) and the
    # national formula does not apply, so entitledto is the only ground truth.
    for cid in (
        "ctr-eng-wa-manchester-single-earner",
        "ctr-eng-wa-birmingham-couple-1kid",
    ):
        row = by_id[cid]
        assert row["policyengine"]["scheme_supported"] is False
        assert row["policyengine"]["annual_gbp"] == 0.0
        assert row["hand_computed_statutory"]["annual_gbp"] is None

    # Kingston's local scheme is a real per-council award PE models but the
    # national formula cannot reproduce.
    kingston = by_id["ctr-eng-wa-kingston-single-earner"]
    assert kingston["policyengine"]["annual_gbp"] == 1181.0
    assert kingston["hand_computed_statutory"]["annual_gbp"] is None


def _write_captured(dir_: Path, ctr_annual: float) -> None:
    fixture = {
        "case_id": "ctr-eng-wa-kingston-single-earner",
        "oracle": "entitledto",
        "provenance": {
            "capture_status": CAPTURE_STATUS_CAPTURED,
            "calculator": "entitledto",
            "calculator_url": "x",
            "scheme_year": "2026-27",
            "council_name": "Kingston upon Thames",
            "council_gss_code": "E09000021",
            "council_tax_band": "D",
            "capture_date": "2026-07-14",
            "captured_by": "tester",
        },
        "inputs": {},
        "outputs": {"council_tax_reduction": {"annual_gbp": ctr_annual}},
    }
    (dir_ / "ctr-eng-wa-kingston-single-earner.json").write_text(json.dumps(fixture))


def test_captured_case_grades_against_policyengine(tmp_path: Path) -> None:
    _write_captured(tmp_path, ctr_annual=1181.0)  # equals PE
    report = build_uk_ctr_report(fixtures_dir=tmp_path)
    assert report["capture"]["captured"] == 1
    assert report["capture"]["pending"] == 7
    kingston = next(
        c for c in report["cases"] if c["case_id"] == "ctr-eng-wa-kingston-single-earner"
    )
    assert kingston["status"] == "captured"
    assert kingston["entitledto"]["annual_gbp"] == 1181.0
    assert kingston["entitledto_vs_policyengine"]["match"] is True
    assert report["summary"]["comparison_count"] == 1
    assert report["summary"]["match_count"] == 1


def test_captured_divergence_surfaces_as_mismatch(tmp_path: Path) -> None:
    _write_captured(tmp_path, ctr_annual=900.0)  # differs from PE 1181
    report = build_uk_ctr_report(fixtures_dir=tmp_path)
    kingston = next(
        c for c in report["cases"] if c["case_id"] == "ctr-eng-wa-kingston-single-earner"
    )
    assert kingston["entitledto_vs_policyengine"]["match"] is False
    assert kingston["entitledto_vs_policyengine"]["difference"] == 900.0 - 1181.0
    assert report["summary"]["mismatch_count"] == 1


def test_committed_pe_reference_is_present() -> None:
    reference = json.loads(DEFAULT_PE_REFERENCE.read_text())
    assert reference["provenance"]["engine"] == "policyengine-uk"
    assert reference["provenance"]["version"] == "2.89.2"
    assert set(reference["cases"]) == {
        "ctr-eng-pa-birmingham-couple-gc",
        "ctr-eng-pa-cornwall-single-taper",
        "ctr-sco-wa-glasgow-single-earner",
        "ctr-wal-wa-cardiff-couple-2kids",
        "ctr-eng-wa-kingston-single-earner",
        "ctr-eng-pa-kingston-single",
        "ctr-eng-wa-manchester-single-earner",
        "ctr-eng-wa-birmingham-couple-1kid",
    }


def test_runner_registered_and_writes_report(tmp_path: Path) -> None:
    path = _REPO_ROOT / "scripts" / "run_comparison.py"
    spec = importlib.util.spec_from_file_location("run_comparison_ukctr", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert "uk-ctr-entitledto-recorded" in module.RUNNERS

    output = tmp_path / "report.json"
    module.RUNNERS["uk-ctr-entitledto-recorded"]({}, output)
    written = json.loads(output.read_text())
    assert written["suite"] == "uk-ctr"
    assert written["capture"]["pending"] == 8
