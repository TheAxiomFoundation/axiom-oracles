"""UK-CTR calculator-oracle report builder: fail-closed, pending, and captured grading."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from axiom_oracles.adapters.entitledto import CAPTURE_STATUS_CAPTURED
from axiom_oracles.adapters.entitledto.report import (
    DEFAULT_PE_REFERENCE,
    _hand_computed_statutory,
    build_uk_ctr_report,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CID = "ctr-eng-wa-kingston-single-earner"


def test_pending_report_grades_nothing_but_carries_pe_and_statutory() -> None:
    report = build_uk_ctr_report()
    assert report["capture"]["captured"] == 0
    assert report["capture"]["pending"] == 8
    assert report["capture"]["graded"] == 0
    assert report["summary"]["graded_comparison_count"] == 0
    assert "not agreements" in report["summary"]["note"]
    assert len(report["cases"]) == 8
    by_id = {c["case_id"]: c for c in report["cases"]}

    # National schemes: statutory hand-check equals PolicyEngine exactly.
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

    # Unsupported councils: PolicyEngine returns 0; national formula does not apply.
    for cid in ("ctr-eng-wa-manchester-single-earner", "ctr-eng-wa-birmingham-couple-1kid"):
        row = by_id[cid]
        assert row["policyengine"]["scheme_supported"] is False
        assert row["policyengine"]["annual_gbp"] == 0.0
        assert row["hand_computed_statutory"]["annual_gbp"] is None

    kingston = by_id[_CID]
    assert kingston["policyengine"]["annual_gbp"] == 1181.0
    assert kingston["hand_computed_statutory"]["annual_gbp"] is None
    assert kingston["entitledto"]["status"] == "pending_capture"
    assert kingston["entitledto"]["errors"]  # the pending reason is surfaced


def test_independent_statutory_hand_check() -> None:
    # Not fed PolicyEngine's parameters: pins the national formula against a
    # hand-worked case. Single pensioner, liability £2,000, applicable amount
    # £13,312, applicable income £16,114, capital £5,000 (< £16,000):
    #   2000 - 0.20 * (16114 - 13312) = 2000 - 560.40 = 1439.60
    out = _hand_computed_statutory(
        scheme="england-pension-age-prescribed",
        liability=2000.0,
        applicable_amount=13312.0,
        applicable_income=16114.0,
        capital=5000.0,
        params={"england_pensioner": {
            "maximum_support_rate": 1.0, "withdrawal_rate": 0.2, "capital_limit": 16000.0}},
    )
    assert out["annual_gbp"] == 1439.60

    # Capital over the £16,000 limit extinguishes the award.
    over = _hand_computed_statutory(
        scheme="scotland-working-age-national",
        liability=1300.0, applicable_amount=4969.0, applicable_income=5000.0,
        capital=16001.0,
        params={"scotland": {"maximum_support_rate": 1.0, "withdrawal_rate": 0.2,
                             "capital_limit": 16000.0}},
    )
    assert over["annual_gbp"] == 0.0

    # A local scheme has no national formula.
    local = _hand_computed_statutory(
        scheme="manchester-working-age-local", liability=1600.0,
        applicable_amount=4969.0, applicable_income=15510.0, capital=3000.0, params={})
    assert local["annual_gbp"] is None


def _seed_pending(dir_: Path) -> None:
    """Copy the committed pending fixtures so the report's bijection holds."""
    from axiom_oracles.adapters.entitledto.recorded import DEFAULT_FIXTURES_DIR

    for src in DEFAULT_FIXTURES_DIR.glob("*.json"):
        (dir_ / src.name).write_text(src.read_text())


def _write_captured(dir_: Path, ctr_annual: float, liability: float = 2171.0) -> None:
    _seed_pending(dir_)
    fixture = {
        "case_id": _CID,
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
            "entitledto_council_tax_liability_gbp": liability,
        },
        "inputs": {},
        "outputs": {"council_tax_reduction": {"annual_gbp": ctr_annual}},
    }
    (dir_ / f"{_CID}.json").write_text(json.dumps(fixture))


def test_captured_case_grades_against_policyengine(tmp_path: Path) -> None:
    _write_captured(tmp_path, ctr_annual=1181.0)  # equals PE
    report = build_uk_ctr_report(fixtures_dir=tmp_path)
    assert report["capture"]["captured"] == 1
    assert report["capture"]["pending"] == 7
    kingston = next(c for c in report["cases"] if c["case_id"] == _CID)
    assert kingston["status"] == "captured"
    assert kingston["entitledto"]["annual_gbp"] == 1181.0
    assert kingston["entitledto_vs_policyengine"]["match"] is True
    assert kingston["policyengine_liability_parity"]["match"] is True
    assert report["summary"]["graded_comparison_count"] == 1
    assert report["summary"]["match_count"] == 1


def test_captured_divergence_surfaces_as_mismatch(tmp_path: Path) -> None:
    _write_captured(tmp_path, ctr_annual=900.0)  # differs from PE 1181
    report = build_uk_ctr_report(fixtures_dir=tmp_path)
    kingston = next(c for c in report["cases"] if c["case_id"] == _CID)
    assert kingston["entitledto_vs_policyengine"]["match"] is False
    assert kingston["entitledto_vs_policyengine"]["difference"] == 900.0 - 1181.0
    assert report["summary"]["mismatch_count"] == 1


def test_captured_liability_mismatch_is_not_graded(tmp_path: Path) -> None:
    # entitledto's derived liability (e.g. after a single-person discount) differs
    # from PolicyEngine's modelled liability: the two awards priced different
    # bills, so the pair is reported descriptively, never as a match/mismatch.
    _write_captured(tmp_path, ctr_annual=1181.0, liability=1628.25)  # 75% of 2171
    report = build_uk_ctr_report(fixtures_dir=tmp_path)
    kingston = next(c for c in report["cases"] if c["case_id"] == _CID)
    parity = kingston["policyengine_liability_parity"]
    assert parity["match"] is False
    assert parity["entitledto_liability"] == 1628.25
    assert parity["reference_liability"] == 2171.0
    assert kingston["council_tax_liability"] == 1628.25  # statutory uses captured liability
    vs_pe = kingston["entitledto_vs_policyengine"]
    assert vs_pe["graded"] is False
    assert "liability differs" in vs_pe["not_graded_reason"]
    assert report["summary"]["graded_comparison_count"] == 0
    assert report["summary"]["match_count"] == 0
    assert report["summary"]["mismatch_count"] == 0
    assert report["summary"]["captured_not_graded_count"] == 1
    assert report["capture"]["captured"] == 1


def test_captured_unsupported_scheme_is_not_graded(tmp_path: Path) -> None:
    # PolicyEngine does not model Manchester's working-age scheme — its value is
    # the constructed-household fallback, not the scheme, so a captured
    # Manchester fixture must not manufacture a match or a mismatch.
    manchester = "ctr-eng-wa-manchester-single-earner"
    _seed_pending(tmp_path)
    reference = json.loads(DEFAULT_PE_REFERENCE.read_text())
    pe_row = reference["cases"][manchester]
    assert pe_row["scheme_supported"] is False
    fixture = json.loads((tmp_path / f"{manchester}.json").read_text())
    fixture["provenance"].update(
        {
            "capture_status": CAPTURE_STATUS_CAPTURED,
            "capture_date": "2026-07-14",
            "captured_by": "tester",
            "entitledto_council_tax_liability_gbp": pe_row["council_tax"],
        }
    )
    fixture["outputs"] = {"council_tax_reduction": {"annual_gbp": 750.0}}
    (tmp_path / f"{manchester}.json").write_text(json.dumps(fixture))

    report = build_uk_ctr_report(fixtures_dir=tmp_path)
    row = next(c for c in report["cases"] if c["case_id"] == manchester)
    vs_pe = row["entitledto_vs_policyengine"]
    assert vs_pe["graded"] is False
    assert "does not model" in vs_pe["not_graded_reason"]
    assert report["summary"]["graded_comparison_count"] == 0
    assert report["summary"]["captured_not_graded_count"] == 1


def test_missing_pe_reference_row_raises(tmp_path: Path) -> None:
    reference = json.loads(DEFAULT_PE_REFERENCE.read_text())
    reference["cases"].pop(_CID)  # drop a row → must not default to a full award
    ref_path = tmp_path / "ref.json"
    ref_path.write_text(json.dumps(reference))
    with pytest.raises(ValueError, match="no PolicyEngine reference row"):
        build_uk_ctr_report(pe_reference_path=ref_path)


def test_committed_pe_reference_schema() -> None:
    reference = json.loads(DEFAULT_PE_REFERENCE.read_text())
    assert reference["provenance"]["engine"] == "policyengine-uk"
    assert reference["provenance"]["generator"] == "scripts/generate_uk_ctr_pe_reference.py"
    assert set(reference["cases"]) == {str(c) for c in _suite_ids()}


def _suite_ids():
    from axiom_oracles.suites.uk_ctr import uk_ctr_cases

    return [c.case_id for c in uk_ctr_cases()]


def test_pe_reference_reproduces_from_policyengine() -> None:
    # Reproducibility gate: when PolicyEngine-UK is importable, the committed
    # reference case values must equal a fresh generation from the suite cases.
    pytest.importorskip("policyengine_uk")
    path = _REPO_ROOT / "scripts" / "generate_uk_ctr_pe_reference.py"
    spec = importlib.util.spec_from_file_location("gen_pe_ref", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    committed = json.loads(DEFAULT_PE_REFERENCE.read_text())
    fresh = module.build_reference()
    assert committed["cases"] == fresh["cases"]
