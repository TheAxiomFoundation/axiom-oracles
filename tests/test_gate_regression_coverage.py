"""Specification-derived regression coverage for the certification gates.

This is a defensive completeness suite.  Passing mutants prove documented
rejections; strict xfails name places where a gate does not yet satisfy its
own contract.  Gate implementations are deliberately never patched here.
"""

from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError
from functools import lru_cache
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str) -> ModuleType:
    path = REPO_ROOT / "scripts" / f"{name}.py"
    module_name = f"_gate_regression_{name}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _certificate_report(**updates: object) -> dict:
    report = {
        "suite": "victim",
        "summary": {
            "comparison_count": 1,
            "match_count": 1,
            "mismatch_count": 0,
        },
        "cases": [{"case_id": "case-1", "metadata": {"income": 1}}],
        "mismatches": [],
    }
    report.update(updates)
    return report


def _certificate_entry(report: str = "report.json", **updates: object) -> dict:
    entry = {
        "suite": "victim",
        "oracle_type": "reference",
        "oracle": "synthetic",
        "report": report,
    }
    entry.update(updates)
    return entry


def _write_certificate_report(tmp_path: Path, report: dict) -> Path:
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report) + "\n")
    return path


def _patch_clean_certificate_inputs(
    monkeypatch: pytest.MonkeyPatch,
    certify: ModuleType,
) -> None:
    monkeypatch.setattr(certify, "_load", lambda _path: {"suites": {}})
    monkeypatch.setattr(certify, "sha256_of", lambda _path: "0" * 64)
    monkeypatch.setattr(
        certify,
        "_exercise_block",
        lambda _suites, _census, _defects: ({}, True),
    )


def _leg(
    entry: dict,
    *,
    clean: bool,
    unexplained: int = 0,
    axiom_open: int = 0,
    mismatches: int = 0,
) -> tuple[dict, list[dict], list[str]]:
    return (
        {
            "suite": entry["suite"],
            "oracle_type": entry["oracle_type"],
            "oracle": entry.get("oracle", "synthetic"),
            "comparisons": 1,
            "matches": 1 if not mismatches else 0,
            "mismatches": mismatches,
            "weighted_mismatch_mass": None,
            "unexplained": unexplained,
            "axiom_attributed_open": axiom_open,
            "report_defects": [],
            "clean": clean,
        },
        [],
        [],
    )


# ---------------------------------------------------------------------------
# scripts/certify.py


def test_certificate_output_names_are_a_bijection_with_program_registry():
    certify = _load_script("certify")
    names = [certify._out_path(program).name for program in certify.PROGRAMS]
    assert len(names) == len(set(names)) == len(certify.PROGRAMS)
    assert all(name.endswith(".json") for name in names)


def test_certificate_computed_evidence_carries_exact_artifact_digests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    certify = _load_script("certify")
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    disposition = tmp_path / "dispositions" / "victim.yaml"
    disposition.parent.mkdir()
    disposition.write_text(
        yaml.safe_dump(
            {
                "schema": "axiom_oracles.dispositions.v1",
                "suite": "victim",
                "entries": [{"id": "d-1"}],
            }
        )
    )
    report = _certificate_report(
        summary={
            "comparison_count": 1,
            "match_count": 0,
            "mismatch_count": 1,
            "dispositioned": {
                "dispositions_file": "dispositions/victim.yaml",
                "unexplained_count": 0,
                "counts": {"upstream_engine_gap": 1, "unexplained": 0},
            },
        },
        mismatches=[{"case_id": "case-1"}],
    )
    report_path = _write_certificate_report(tmp_path, report)

    _leg_result, evidence, defects = certify._suite_verdict(_certificate_entry())

    assert not defects
    by_claim = {row["claim"]: row for row in evidence}
    assert by_claim["suite:victim"] == {
        "claim": "suite:victim",
        "mode": "computed",
        "artifact": "report.json",
        "sha256": _sha256(report_path),
    }
    assert by_claim["dispositions:victim"]["sha256"] == _sha256(disposition)


def test_certificate_reference_and_reality_oracle_semantics(
    monkeypatch: pytest.MonkeyPatch,
):
    certify = _load_script("certify")
    _patch_clean_certificate_inputs(monkeypatch, certify)

    def verdict(entry: dict):
        if entry["suite"] == "reference":
            return _leg(entry, clean=True)
        return _leg(entry, clean=False, unexplained=3, mismatches=3)

    monkeypatch.setattr(certify, "_suite_verdict", verdict)
    spec = {
        "period": "2026-01",
        "suites": [
            _certificate_entry("reference.json", suite="reference"),
            _certificate_entry(
                "reality.json", suite="reality", oracle_type="reality"
            ),
        ],
    }

    certificate = certify.build_certificate("program", spec)

    assert certificate["verdicts"]["conformant"]["value"] is True
    assert certificate["verdicts"]["conformant"]["reality_leads"] == 3
    assert not any("reality" in blocker for blocker in certificate["blockers"])


def test_certificate_declared_alias_can_bind_report_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    certify = _load_script("certify")
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    _write_certificate_report(
        tmp_path,
        _certificate_report(suite="historical-victim"),
    )

    leg, _evidence, defects = certify._suite_verdict(
        _certificate_entry(aliases=["historical-victim"])
    )

    assert leg["clean"] is True
    assert not any("identifies as" in defect for defect in defects)


@pytest.mark.parametrize(
    ("raw", "marker"),
    [
        pytest.param(True, "boolean", id="boolean"),
        pytest.param(1.5, "non-negative integer", id="fractional"),
        pytest.param("one", "non-negative integer", id="string"),
    ],
)
def test_certificate_count_rejects_non_integer_types(raw: object, marker: str):
    certify = _load_script("certify")
    defects: list[str] = []
    assert certify._count(raw, "comparison_count", defects, "victim") == 0
    assert any(marker in defect for defect in defects)


@pytest.mark.xfail(
    strict=True,
    reason="CERT-GAP-count-type: integral floats contradict the integer-only contract",
)
def test_certificate_count_rejects_integral_float():
    certify = _load_script("certify")
    defects: list[str] = []
    certify._count(1.0, "comparison_count", defects, "victim")
    assert defects


def test_certificate_rejects_nonconserving_summary_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    certify = _load_script("certify")
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    _write_certificate_report(
        tmp_path,
        _certificate_report(
            summary={
                "comparison_count": 2,
                "match_count": 1,
                "mismatch_count": 0,
            }
        ),
    )
    leg, _evidence, defects = certify._suite_verdict(_certificate_entry())
    assert leg["clean"] is False
    assert any("counts do not conserve" in defect for defect in defects)


@pytest.mark.parametrize(
    ("summary_update", "report_update"),
    [
        pytest.param({"error_count": 1}, {}, id="error-count"),
        pytest.param({"error_case_count": 1}, {}, id="error-case-count"),
        pytest.param({"errors_by_engine": {"engine": 1}}, {}, id="by-engine"),
        pytest.param({}, {"errors": [{"case_id": "case-1"}]}, id="top-level"),
    ],
)
def test_certificate_rejects_each_engine_error_shape_independently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    summary_update: dict,
    report_update: dict,
):
    certify = _load_script("certify")
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    report = _certificate_report(**report_update)
    report["summary"].update(summary_update)
    _write_certificate_report(tmp_path, report)
    leg, _evidence, defects = certify._suite_verdict(_certificate_entry())
    assert leg["clean"] is False
    assert any("engine error" in defect for defect in defects)


@pytest.mark.xfail(
    strict=True,
    reason="CERT-GAP-chunk-parse: any chunk-shaped filename is treated as case evidence",
)
def test_certificate_rejects_malformed_chunk_as_per_case_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    certify = _load_script("certify")
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    _write_certificate_report(tmp_path, _certificate_report(cases=[]))
    chunk_dir = tmp_path / "dashboard" / "public" / "data" / "cases" / "victim"
    chunk_dir.mkdir(parents=True)
    (chunk_dir / "chunk-0.json").write_text("{not-json")
    leg, _evidence, defects = certify._suite_verdict(_certificate_entry())
    assert leg["clean"] is False
    assert any("chunk" in defect and "JSON" in defect for defect in defects)


def test_certificate_rejects_nonnumeric_weighted_mismatch_mass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    certify = _load_script("certify")
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    report = _certificate_report()
    report["summary"]["weighted"] = {"mismatch_weight": "many"}
    _write_certificate_report(tmp_path, report)
    leg, _evidence, defects = certify._suite_verdict(_certificate_entry())
    assert leg["clean"] is False
    assert any("not numeric" in defect for defect in defects)


def test_certificate_rejects_traversing_disposition_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    certify = _load_script("certify")
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    report = _certificate_report()
    report["summary"]["dispositioned"] = {
        "dispositions_file": "dispositions/../victim.yaml",
        "unexplained_count": 0,
        "counts": {},
    }
    _write_certificate_report(tmp_path, report)
    leg, _evidence, defects = certify._suite_verdict(_certificate_entry())
    assert leg["clean"] is False
    assert any("not a repository-relative path" in defect for defect in defects)


@pytest.mark.xfail(
    strict=True,
    reason="CERT-GAP-disposition-shape: a directory/non-string citation can raise",
)
@pytest.mark.parametrize("citation", ["dispositions", {"path": "victim.yaml"}])
def test_certificate_disposition_citation_must_be_a_regular_relative_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    citation: object,
):
    certify = _load_script("certify")
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    (tmp_path / "dispositions").mkdir()
    report = _certificate_report()
    report["summary"]["dispositioned"] = {
        "dispositions_file": citation,
        "unexplained_count": 0,
        "counts": {},
    }
    _write_certificate_report(tmp_path, report)
    leg, _evidence, defects = certify._suite_verdict(_certificate_entry())
    assert leg["clean"] is False
    assert defects


@pytest.mark.xfail(
    strict=True,
    reason="CERT-GAP-disposition-schema: a suite-only document authorizes counts",
)
def test_certificate_same_suite_empty_dispositions_cannot_authorize(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    certify = _load_script("certify")
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    disposition = tmp_path / "empty.yaml"
    disposition.write_text("suite: victim\nentries: []\n")
    report = _certificate_report(
        summary={
            "comparison_count": 1,
            "match_count": 0,
            "mismatch_count": 1,
            "dispositioned": {
                "dispositions_file": "empty.yaml",
                "unexplained_count": 0,
                "counts": {"upstream_engine_gap": 1, "unexplained": 0},
            },
        },
        mismatches=[{"case_id": "case-1"}],
    )
    _write_certificate_report(tmp_path, report)
    leg, _evidence, defects = certify._suite_verdict(_certificate_entry())
    assert leg["clean"] is False
    assert any("dispositions document" in defect for defect in defects)


@pytest.mark.parametrize(
    ("counts", "marker"),
    [
        pytest.param({"invented": 1, "unexplained": 0}, "unknown", id="kind"),
        pytest.param(
            {"upstream_engine_gap": 0, "unexplained": 0},
            "do not conserve",
            id="under-count",
        ),
        pytest.param(
            {"upstream_engine_gap": 2, "unexplained": 0},
            "do not conserve",
            id="over-count",
        ),
    ],
)
def test_certificate_rejects_undefined_or_nonconserving_disposition_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    counts: dict,
    marker: str,
):
    certify = _load_script("certify")
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    (tmp_path / "dispositions.yaml").write_text(
        "schema: axiom_oracles.dispositions.v1\nsuite: victim\nentries:\n  - id: d-1\n"
    )
    report = _certificate_report(
        summary={
            "comparison_count": 1,
            "match_count": 0,
            "mismatch_count": 1,
            "dispositioned": {
                "dispositions_file": "dispositions.yaml",
                "unexplained_count": 0,
                "counts": counts,
            },
        },
        mismatches=[{"case_id": "case-1"}],
    )
    _write_certificate_report(tmp_path, report)
    leg, _evidence, defects = certify._suite_verdict(_certificate_entry())
    assert leg["clean"] is False
    assert any(marker in defect for defect in defects)


def test_certificate_without_disposition_machinery_leaves_mismatches_unexplained(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    certify = _load_script("certify")
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    _write_certificate_report(
        tmp_path,
        _certificate_report(
            summary={
                "comparison_count": 1,
                "match_count": 0,
                "mismatch_count": 1,
            },
            mismatches=[{"case_id": "case-1"}],
        ),
    )
    leg, _evidence, _defects = certify._suite_verdict(_certificate_entry())
    assert leg["unexplained"] == 1
    assert leg["clean"] is False


@pytest.mark.xfail(
    strict=True,
    reason="CERT-GAP-inline-dispositions: equal inline counts avoid the promised defect",
)
def test_certificate_inline_classifications_without_file_are_always_defective(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    certify = _load_script("certify")
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    report = _certificate_report()
    report["summary"]["dispositioned"] = {
        "unexplained_count": 1,
        "counts": {"upstream_engine_gap": 1},
    }
    _write_certificate_report(tmp_path, report)
    _leg_result, _evidence, defects = certify._suite_verdict(_certificate_entry())
    assert any("inline classifications" in defect for defect in defects)


def test_certificate_rejects_unstored_slim_mismatch_aggregate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    certify = _load_script("certify")
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    _write_certificate_report(
        tmp_path,
        _certificate_report(
            summary={
                "comparison_count": 1,
                "match_count": 0,
                "mismatch_count": 1,
            },
            mismatches=[],
        ),
    )
    leg, _evidence, defects = certify._suite_verdict(_certificate_entry())
    assert leg["clean"] is False
    assert any("aggregate unauditable" in defect for defect in defects)


@pytest.mark.xfail(
    strict=True,
    reason="CERT-GAP-empty-chunk-dir: directory existence bypasses slim auditing",
)
def test_certificate_empty_chunk_directory_does_not_make_slim_report_auditable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    certify = _load_script("certify")
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    _write_certificate_report(
        tmp_path,
        _certificate_report(
            summary={
                "comparison_count": 1,
                "match_count": 0,
                "mismatch_count": 1,
            },
            mismatches=[],
        ),
    )
    (tmp_path / "dashboard/public/data/cases/victim").mkdir(parents=True)
    _leg_result, _evidence, defects = certify._suite_verdict(_certificate_entry())
    assert any("aggregate unauditable" in defect for defect in defects)


def test_certificate_axiom_encoding_gap_keeps_leg_unclean(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    certify = _load_script("certify")
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    (tmp_path / "dispositions.yaml").write_text(
        "schema: axiom_oracles.dispositions.v1\nsuite: victim\nentries:\n  - id: d-1\n"
    )
    report = _certificate_report(
        summary={
            "comparison_count": 1,
            "match_count": 0,
            "mismatch_count": 1,
            "dispositioned": {
                "dispositions_file": "dispositions.yaml",
                "unexplained_count": 0,
                "counts": {"axiom_encoding_gap": 1, "unexplained": 0},
            },
        },
        mismatches=[{"case_id": "case-1"}],
    )
    _write_certificate_report(tmp_path, report)
    leg, _evidence, _defects = certify._suite_verdict(_certificate_entry())
    assert leg["axiom_attributed_open"] == 1
    assert leg["clean"] is False


@pytest.mark.parametrize(
    ("census", "marker"),
    [
        pytest.param({"suites": {}}, "no census row", id="missing-row"),
        pytest.param(
            {
                "suites": {
                    "victim": {
                        "evidence_fields": {},
                        "bridge_audited": True,
                    }
                }
            },
            "per_case_evidence_committed",
            id="no-fields",
        ),
        pytest.param(
            {
                "suites": {
                    "victim": {
                        "evidence_fields": {"income": {"distinct": 2}},
                        "bridge_audited": False,
                    }
                }
            },
            "bridge_audited",
            id="bridge-debt",
        ),
    ],
)
def test_certificate_exercise_requires_row_evidence_and_clean_bridge(
    census: dict,
    marker: str,
):
    certify = _load_script("certify")
    rows, complete = certify._exercise_block(
        [_certificate_entry()], census, []
    )
    assert complete is False
    assert marker in json.dumps(rows["victim"])


@pytest.mark.xfail(
    strict=True,
    reason="CERT-GAP-census-identity: main does not compare census path/SHA to registry",
)
@pytest.mark.parametrize(
    ("field", "value", "marker"),
    [
        pytest.param("report", "other.json", "census report path", id="path"),
        pytest.param("report_sha256", "0" * 64, "census report_sha256", id="sha"),
    ],
)
def test_certificate_census_report_identity_must_match_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
    marker: str,
):
    certify = _load_script("certify")
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    report = _write_certificate_report(tmp_path, _certificate_report())
    row = {
        "cases_scanned": 1,
        "report": "report.json",
        "report_sha256": _sha256(report),
        "evidence_fields": {"income": {"distinct": 2, "state": "varied"}},
        "varied_fields": 1,
        "constant_fields": 0,
        "bridged_through": {},
        "bridge_audited": True,
        "contested_reports": [],
        field: value,
    }
    defects: list[str] = []
    _rows, complete = certify._exercise_block(
        [_certificate_entry()], {"suites": {"victim": row}}, defects
    )
    assert complete is False
    assert any(marker in defect for defect in defects)


def test_certificate_conformance_requires_a_clean_reference_leg(
    monkeypatch: pytest.MonkeyPatch,
):
    certify = _load_script("certify")
    _patch_clean_certificate_inputs(monkeypatch, certify)

    for suites, clean in (
        ([_certificate_entry(oracle_type="reality")], True),
        ([_certificate_entry()], False),
    ):
        monkeypatch.setattr(
            certify,
            "_suite_verdict",
            lambda entry, clean=clean: _leg(
                entry, clean=clean, unexplained=0 if clean else 1
            ),
        )
        certificate = certify.build_certificate(
            "program", {"period": "2026-01", "suites": suites}
        )
        assert certificate["verdicts"]["conformant"]["value"] is False


@pytest.mark.xfail(
    strict=True,
    reason="CERT-GAP-attestation-pin: attested receipts are not required to carry a digest",
)
def test_certificate_attested_receipt_requires_sha_pin(
    monkeypatch: pytest.MonkeyPatch,
):
    certify = _load_script("certify")
    _patch_clean_certificate_inputs(monkeypatch, certify)
    monkeypatch.setattr(
        certify, "_suite_verdict", lambda entry: _leg(entry, clean=True)
    )
    spec = {
        "period": "2026-01",
        "suites": [_certificate_entry()],
        "attested": {
            "closed": {"status": "prototype", "value": True, "source": "receipt"},
            "executable": {
                "status": "attested_pass",
                "value": True,
                "source": "receipt",
            },
        },
    }
    certificate = certify.build_certificate("program", spec)
    assert any("sha" in blocker.lower() for blocker in certificate["blockers"])


@pytest.mark.xfail(
    strict=True,
    reason="CERT-GAP-computed-producer: registry status text self-authorizes computation",
)
def test_certificate_computed_premises_require_real_producers(
    monkeypatch: pytest.MonkeyPatch,
):
    certify = _load_script("certify")
    _patch_clean_certificate_inputs(monkeypatch, certify)
    monkeypatch.setattr(
        certify, "_suite_verdict", lambda entry: _leg(entry, clean=True)
    )
    spec = {
        "period": "2026-01",
        "suites": [_certificate_entry()],
        "attested": {
            "closed": {"status": "computed", "value": True, "source": "missing"},
            "executable": {
                "status": "computed",
                "value": True,
                "source": "missing",
            },
        },
    }
    certificate = certify.build_certificate("program", spec)
    assert certificate["certified"]["state"] != "yes"


@pytest.mark.xfail(
    strict=True,
    reason="CERT-GAP-oracle-enum: unknown types disappear from both verdict legs",
)
def test_certificate_unknown_oracle_type_is_a_defect(
    monkeypatch: pytest.MonkeyPatch,
):
    certify = _load_script("certify")
    _patch_clean_certificate_inputs(monkeypatch, certify)

    def verdict(entry: dict):
        return _leg(
            entry,
            clean=entry["oracle_type"] == "reference",
            unexplained=0 if entry["oracle_type"] == "reference" else 1,
        )

    monkeypatch.setattr(certify, "_suite_verdict", verdict)
    spec = {
        "period": "2026-01",
        "suites": [
            _certificate_entry(suite="clean"),
            _certificate_entry(suite="dirty", oracle_type="referance"),
        ],
    }
    certificate = certify.build_certificate("program", spec)
    assert certificate["verdicts"]["conformant"]["value"] is False
    assert any("oracle_type" in blocker for blocker in certificate["blockers"])


@pytest.mark.xfail(
    strict=True,
    reason="CERT-GAP-reality-axiom: an admitted Axiom defect is only a reality lead",
)
def test_certificate_reality_axiom_gap_violates_zero_open_defects(
    monkeypatch: pytest.MonkeyPatch,
):
    certify = _load_script("certify")
    _patch_clean_certificate_inputs(monkeypatch, certify)

    def verdict(entry: dict):
        if entry["oracle_type"] == "reference":
            return _leg(entry, clean=True)
        return _leg(entry, clean=False, axiom_open=1, mismatches=1)

    monkeypatch.setattr(certify, "_suite_verdict", verdict)
    spec = {
        "period": "2026-01",
        "suites": [
            _certificate_entry(suite="reference"),
            _certificate_entry(suite="reality", oracle_type="reality"),
        ],
    }
    certificate = certify.build_certificate("program", spec)
    assert any("reality" in blocker for blocker in certificate["blockers"])


@pytest.mark.xfail(
    strict=True,
    reason="CERT-GAP-report-errors: missing/malformed reports raise instead of becoming defects",
)
@pytest.mark.parametrize("payload", [None, "{not-json", "[]"])
def test_certificate_report_read_and_shape_failures_are_leg_defects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: str | None,
):
    certify = _load_script("certify")
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    if payload is not None:
        (tmp_path / "report.json").write_text(payload)
    leg, _evidence, defects = certify._suite_verdict(_certificate_entry())
    assert leg["clean"] is False
    assert defects


@pytest.mark.xfail(
    strict=True,
    reason="CERT-GAP-unexplained-type: unexplained_count is skipped when counts are empty",
)
def test_certificate_validates_unexplained_count_even_with_empty_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    certify = _load_script("certify")
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    report = _certificate_report()
    report["summary"]["dispositioned"] = {
        "counts": {},
        "unexplained_count": "one",
    }
    _write_certificate_report(tmp_path, report)
    leg, _evidence, defects = certify._suite_verdict(_certificate_entry())
    assert leg["clean"] is False
    assert any("unexplained_count" in defect for defect in defects)


@pytest.mark.xfail(
    strict=True,
    reason="CERT-GAP-exercise-strength: constant unbound evidence counts as exercised",
)
def test_certificate_exercise_requires_bound_material_variation():
    certify = _load_script("certify")
    row = {
        "cases_scanned": 0,
        "report": "report.json",
        "report_sha256": "0" * 64,
        "evidence_fields": {"irrelevant": {"distinct": 1, "state": "constant"}},
        "varied_fields": 0,
        "constant_fields": 1,
        "bridged_through": {},
        "bridge_audited": True,
        "binding": "unbound",
        "reconciliation": "none",
    }
    _rows, complete = certify._exercise_block(
        [_certificate_entry()], {"suites": {"victim": row}}, []
    )
    assert complete is False


@pytest.mark.xfail(
    strict=True,
    reason="CERT-GAP-manifest-binding: certificate omits the manifest path and SHA",
)
def test_certificate_cites_exact_bridge_manifest_identity(
    monkeypatch: pytest.MonkeyPatch,
):
    certify = _load_script("certify")
    _patch_clean_certificate_inputs(monkeypatch, certify)
    monkeypatch.setattr(
        certify, "_suite_verdict", lambda entry: _leg(entry, clean=True)
    )
    certificate = certify.build_certificate(
        "us-co/snap",
        {"period": "2026-01", "suites": [_certificate_entry(suite="co-snap-ecps")]},
    )
    manifests = [
        row for row in certificate["evidence"] if "/bridges/manifests/" in row["artifact"]
    ]
    assert manifests
    assert all(len(row["sha256"]) == 64 for row in manifests)


@pytest.mark.parametrize("mutant", ["missing", "drift", "stray"])
def test_certificate_check_rejects_missing_drifted_and_stray_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutant: str,
):
    certify = _load_script("certify")
    out_dir = tmp_path / "certificates"
    out_dir.mkdir()
    expected = {"program/node": {"schema": "expected"}}
    expected_path = out_dir / "program-node.json"
    if mutant != "missing":
        expected_path.write_text(
            json.dumps(expected["program/node"] if mutant == "stray" else {"bad": True})
        )
    if mutant == "stray":
        (out_dir / "retired.json").write_text("{}\n")
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(certify, "OUT_DIR", out_dir)
    monkeypatch.setattr(certify, "build_all", lambda: expected)
    monkeypatch.setattr(sys, "argv", ["certify.py", "--check"])
    assert certify.main() == 1


# ---------------------------------------------------------------------------
# scripts/exercise_census.py


def _patch_census_paths(
    monkeypatch: pytest.MonkeyPatch,
    census: ModuleType,
    tmp_path: Path,
) -> Path:
    data_dir = tmp_path / "dashboard" / "public" / "data"
    data_dir.mkdir(parents=True)
    monkeypatch.setattr(census, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(census, "DATA_DIR", data_dir)
    monkeypatch.setattr(census, "CASES_DIR", data_dir / "cases")
    monkeypatch.setattr(census, "BRIDGED_THROUGH", {})
    monkeypatch.setattr(census, "MANIFEST_STRICT_CLEAN", {})
    return data_dir


def test_census_enumerates_zero_evidence_and_contested_reports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    census = _load_script("exercise_census")
    data_dir = _patch_census_paths(monkeypatch, census, tmp_path)
    for name in ("a.json", "b.json"):
        (data_dir / name).write_text(
            json.dumps({"suite": "victim", "summary": {}, "cases": []}) + "\n"
        )
    result = census.build_census()
    row = result["suites"]["victim"]
    assert row["cases_scanned"] == 0
    assert row["evidence_fields"] == {}
    assert row["contested_reports"] == [
        "dashboard/public/data/a.json",
        "dashboard/public/data/b.json",
    ]


def test_census_extracts_compact_fields_concepts_states_and_exact_identities(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    census = _load_script("exercise_census")
    data_dir = _patch_census_paths(monkeypatch, census, tmp_path)
    report_path = data_dir / "report.json"
    report = {
        "suite": "victim",
        "cases": [{"metadata": {"inline-only": 99}}],
    }
    report_path.write_text(json.dumps(report) + "\n")
    chunk_dir = data_dir / "cases" / "victim"
    chunk_dir.mkdir(parents=True)
    chunk = chunk_dir / "chunk-0.json"
    chunk.write_text(
        json.dumps(
            [
                {
                    "id": "a",
                    "i": [{"n": "income", "v": 1}, {"n": "state", "v": "CO"}],
                    "v": [{"c": "benefit", "l": 10, "x": 10}],
                    "m": [],
                },
                {
                    "id": "b",
                    "i": [{"n": "income", "v": 2}, {"n": "state", "v": "CO"}],
                    "v": [{"c": "benefit", "l": 20, "x": 20}],
                    "m": [],
                },
            ]
        )
    )
    row = census._census_suite("victim", report, report_path)
    assert row["cases_scanned"] == 2
    assert row["evidence_source"] == "chunks"
    assert row["inline_cases_not_counted"] == 1
    assert row["evidence_fields"] == {
        "income": {"distinct": 2, "state": "varied"},
        "state": {"distinct": 1, "state": "constant"},
    }
    assert row["verdict_concepts"] == {"benefit": {"distinct_left_values": 2}}
    assert (row["varied_fields"], row["constant_fields"]) == (1, 1)
    assert row["report"] == "dashboard/public/data/report.json"
    assert row["report_sha256"] == _sha256(report_path)
    assert row["chunk_manifest"] == [
        {
            "chunk": "dashboard/public/data/cases/victim/chunk-0.json",
            "sha256": _sha256(chunk),
        }
    ]


@pytest.mark.xfail(
    strict=True,
    reason="CENSUS-GAP-presence: one observed value is called constant even if absent elsewhere",
)
def test_census_constant_requires_value_present_in_every_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    census = _load_script("exercise_census")
    data_dir = _patch_census_paths(monkeypatch, census, tmp_path)
    report_path = data_dir / "report.json"
    report = {
        "suite": "victim",
        "cases": [
            {"metadata": {"income": 1}},
            {"metadata": {}},
        ],
    }
    report_path.write_text(json.dumps(report))
    row = census._census_suite("victim", report, report_path)
    assert row["evidence_fields"]["income"]["state"] != "constant"


def test_census_bridge_manifest_aliases_and_no_manifest_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    census = _load_script("exercise_census")
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    (manifest_dir / "victim.yaml").write_text(
        yaml.safe_dump(
            {
                "suite": "victim",
                "aliases": ["victim-v1"],
                "bindings": [
                    {
                        "kind": "bridged",
                        "dimension": "deduction",
                        "mechanism": "oracle output is injected",
                    }
                ],
            }
        )
    )
    monkeypatch.setattr(census, "MANIFEST_DIR", manifest_dir)
    mapped = census._bridged_through_by_suite()
    assert mapped["victim"] == mapped["victim-v1"] == {
        "deduction": "oracle output is injected"
    }
    assert "unmanifested" not in mapped


def test_census_bridge_audit_uses_errors_findings_and_global_collisions(
    monkeypatch: pytest.MonkeyPatch,
):
    census = _load_script("exercise_census")
    manifests = {
        Path("clean.yaml"): {"suite": "clean"},
        Path("debt.yaml"): {"suite": "debt"},
    }

    class Loader:
        def exec_module(self, module: ModuleType) -> None:
            module.load_manifests = lambda: manifests
            module.global_collisions = lambda _manifests: ["collision"]
            module.validate = lambda path, _manifest: (
                ([], []) if path.name == "clean.yaml" else ([], ["finding"])
            )

    monkeypatch.setattr(
        importlib.util,
        "spec_from_file_location",
        lambda *_args, **_kwargs: SimpleNamespace(loader=Loader()),
    )
    monkeypatch.setattr(
        importlib.util,
        "module_from_spec",
        lambda _spec: ModuleType("_fake_manifest_validator"),
    )
    assert census._manifest_strict_clean() == {"clean": False, "debt": False}


@pytest.mark.xfail(
    strict=True,
    reason="CENSUS-GAP-byte-hash: read_text normalizes CRLF before hashing",
)
def test_census_chunk_manifest_hashes_exact_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    census = _load_script("exercise_census")
    data_dir = _patch_census_paths(monkeypatch, census, tmp_path)
    chunk_dir = data_dir / "cases" / "victim"
    chunk_dir.mkdir(parents=True)
    chunk = chunk_dir / "chunk-0.json"
    chunk.write_bytes(b"[\r\n{}\r\n]\r\n")
    _cases, manifest = census._chunk_cases("victim")
    assert manifest[0]["sha256"] == _sha256(chunk)


def test_census_inline_scope_keeps_scalar_stage_evidence_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    census = _load_script("exercise_census")
    data_dir = _patch_census_paths(monkeypatch, census, tmp_path)
    report_path = data_dir / "report.json"
    report = {
        "suite": "victim",
        "cases": [
            {
                "metadata": {
                    "scalar": 1,
                    "nested": {"not": "stage evidence"},
                }
            }
        ],
    }
    report_path.write_text(json.dumps(report))
    row = census._census_suite("victim", report, report_path)
    assert row["evidence_fields"] == {
        "scalar": {"distinct": 1, "state": "constant"}
    }


@pytest.mark.xfail(
    strict=True,
    reason="CENSUS-GAP-malformed-evidence: invalid committed reports/chunks are silently skipped",
)
@pytest.mark.parametrize("surface", ["report", "chunk"])
def test_census_malformed_committed_evidence_remains_visible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
):
    census = _load_script("exercise_census")
    data_dir = _patch_census_paths(monkeypatch, census, tmp_path)
    if surface == "report":
        (data_dir / "report.json").write_text("{not-json")
        assert census._iter_suite_reports()
    else:
        chunk_dir = data_dir / "cases" / "victim"
        chunk_dir.mkdir(parents=True)
        (chunk_dir / "chunk-0.json").write_text("{not-json")
        cases, manifest = census._chunk_cases("victim")
        assert cases or manifest


@pytest.mark.xfail(
    strict=True,
    reason="CENSUS-GAP-index-binding: main census does not expose bound/cardinality state",
)
def test_census_row_states_report_chunk_index_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    census = _load_script("exercise_census")
    data_dir = _patch_census_paths(monkeypatch, census, tmp_path)
    report_path = data_dir / "report.json"
    report = {"suite": "victim", "cases": []}
    report_path.write_text(json.dumps(report))
    row = census._census_suite("victim", report, report_path)
    assert row["binding"] in {"bound", "unbound"}
    assert row["reconciliation"] in {"cardinality", "none"}


@pytest.mark.parametrize("mutant", ["missing", "drift"])
def test_census_check_rejects_missing_and_drifted_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutant: str,
):
    census = _load_script("exercise_census")
    output = tmp_path / "exercise-census.json"
    if mutant == "drift":
        output.write_text("{}\n")
    monkeypatch.setattr(census, "OUTPUT_PATH", output)
    monkeypatch.setattr(census, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(census, "build_census", lambda: {"schema": "expected", "suites": {}})
    monkeypatch.setattr(sys, "argv", ["exercise_census.py", "--check"])
    assert census.main() == 1


def test_census_markdown_renders_all_promised_columns():
    census = _load_script("exercise_census")
    rendered = census.render_markdown(
        {
            "suites": {
                "victim": {
                    "cases_scanned": 3,
                    "varied_fields": 2,
                    "constant_fields": 1,
                    "bridge_audited": True,
                }
            }
        }
    )
    assert "| victim | 3 | 2 | 1 | yes |" in rendered


def test_census_missing_yaml_dependency_fails_explicitly(
    monkeypatch: pytest.MonkeyPatch,
):
    census = _load_script("exercise_census")
    real_import = __import__

    def import_without_yaml(name: str, *args: object, **kwargs: object):
        if name == "yaml":
            raise ModuleNotFoundError("yaml")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", import_without_yaml)
    with pytest.raises(SystemExit, match="PyYAML"):
        census._bridged_through_by_suite()


# ---------------------------------------------------------------------------
# scripts/validate_bridge_manifests.py


def _bridge_manifest(**updates: object) -> dict:
    manifest = {
        "schema": "axiom_oracles.bridge_manifest.v1",
        "suite": "victim",
        "program": "program",
        "population": {"pin_required": False},
        "oracle": {},
        "bindings": [
            {
                "kind": "mapped",
                "input": "income",
                "source": "population:income",
                "audit": "read",
            }
        ],
        "completeness": {"status": "pending"},
    }
    manifest.update(updates)
    return manifest


def _validate_manifest(
    monkeypatch: pytest.MonkeyPatch,
    manifest: dict,
    report: dict | None = None,
) -> tuple[list[str], list[str]]:
    bridge = _load_script("validate_bridge_manifests")
    monkeypatch.setattr(
        bridge,
        "_report_for",
        lambda _names: (
            ("dashboard/public/data/report.json", report or {})
            if report is not None
            else ("dashboard/public/data/report.json", {})
        ),
    )
    return bridge.validate(Path("victim.yaml"), manifest)


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param("schema", id="schema"),
        pytest.param("suite", id="suite"),
        pytest.param("program", id="program"),
        pytest.param("bindings", id="bindings"),
        pytest.param("population", id="population"),
        pytest.param("oracle", id="oracle"),
    ],
)
def test_bridge_manifest_requires_exact_schema_and_top_level_fields(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
):
    manifest = _bridge_manifest()
    if mutation == "schema":
        manifest["schema"] = "invented"
    else:
        del manifest[mutation]
    errors, _findings = _validate_manifest(monkeypatch, manifest)
    assert errors


@pytest.mark.xfail(
    strict=True,
    reason="MANIFEST-GAP-root-shape: non-mapping YAML raises before a schema error",
)
def test_bridge_manifest_root_must_be_a_mapping():
    bridge = _load_script("validate_bridge_manifests")
    errors, _findings = bridge.validate(Path("victim.yaml"), [])
    assert errors


@pytest.mark.parametrize(
    "bindings",
    [
        pytest.param([], id="empty"),
        pytest.param({}, id="mapping"),
        pytest.param("binding", id="string"),
    ],
)
def test_bridge_manifest_bindings_are_a_nonempty_list(
    monkeypatch: pytest.MonkeyPatch,
    bindings: object,
):
    errors, _findings = _validate_manifest(
        monkeypatch, _bridge_manifest(bindings=bindings)
    )
    assert any("bindings must be a non-empty list" in error for error in errors)


@pytest.mark.parametrize(
    ("binding", "marker"),
    [
        pytest.param("not-a-map", "not a mapping", id="mapping"),
        pytest.param(
            {"kind": "invented", "input": "x", "audit": "read"},
            "not in",
            id="kind",
        ),
        pytest.param(
            {"kind": "mapped", "input": "x", "source": "x", "audit": "done"},
            "read|partial",
            id="audit",
        ),
        pytest.param(
            {"kind": "mapped", "source": "x", "audit": "read"},
            "names neither",
            id="name",
        ),
    ],
)
def test_bridge_manifest_binding_shape_kind_audit_and_name(
    monkeypatch: pytest.MonkeyPatch,
    binding: object,
    marker: str,
):
    errors, _findings = _validate_manifest(
        monkeypatch, _bridge_manifest(bindings=[binding])
    )
    assert any(marker in error for error in errors)


def test_bridge_manifest_rejects_duplicate_input_bindings(
    monkeypatch: pytest.MonkeyPatch,
):
    bindings = [
        {
            "kind": "mapped",
            "input": "income",
            "source": "population:income",
            "audit": "read",
        },
        {
            "kind": "constant",
            "input": "income",
            "reason": "fixture",
            "audit": "read",
        },
    ]
    errors, _findings = _validate_manifest(
        monkeypatch, _bridge_manifest(bindings=bindings)
    )
    assert any("bound more than once" in error for error in errors)


@pytest.mark.xfail(
    strict=True,
    reason="MANIFEST-GAP-inputs-type: scalar inputs are iterated character by character",
)
def test_bridge_manifest_inputs_must_be_an_array(
    monkeypatch: pytest.MonkeyPatch,
):
    errors, _findings = _validate_manifest(
        monkeypatch,
        _bridge_manifest(
            bindings=[
                {
                    "kind": "mapped",
                    "inputs": "abc",
                    "source": "population:x",
                    "audit": "read",
                }
            ]
        ),
    )
    assert any("inputs" in error and "list" in error for error in errors)


def test_bridge_manifest_covered_by_requires_a_checkable_reference_and_reports_debt(
    monkeypatch: pytest.MonkeyPatch,
):
    bridge = _load_script("validate_bridge_manifests")
    monkeypatch.setattr(
        bridge,
        "_report_for",
        lambda _names: ("dashboard/public/data/report.json", {}),
    )
    monkeypatch.setattr(
        bridge,
        "_covered_by_resolves",
        lambda ref: ref == "tests/verified.json",
    )
    binding = {
        "kind": "bridged",
        "dimension": "deduction",
        "source": "oracle:deduction",
        "mechanism": "injected",
        "covered_by": ["tests/verified.json", "sibling/review.md"],
        "audit": "read",
    }
    errors, findings = bridge.validate(
        Path("victim.yaml"), _bridge_manifest(bindings=[binding])
    )
    assert not errors
    assert any("sibling/review.md" in finding for finding in findings)

    binding["covered_by"] = ["sibling/review.md"]
    errors, _findings = bridge.validate(
        Path("victim.yaml"), _bridge_manifest(bindings=[binding])
    )
    assert any("no covered_by entry" in error for error in errors)


@pytest.mark.parametrize(
    ("binding", "marker"),
    [
        pytest.param(
            {
                "kind": "bridged",
                "dimension": "x",
                "covered_by": ["ok"],
                "audit": "read",
            },
            "requires source and mechanism",
            id="bridged",
        ),
        pytest.param(
            {"kind": "mapped", "input": "x", "audit": "read"},
            "requires source or source_function",
            id="mapped",
        ),
        pytest.param(
            {"kind": "projected", "input": "x", "audit": "read"},
            "requires source or source_function",
            id="projected",
        ),
        pytest.param(
            {"kind": "constant", "input": "x", "audit": "read"},
            "requires a reason",
            id="constant",
        ),
    ],
)
def test_bridge_manifest_kind_specific_fields_are_required(
    monkeypatch: pytest.MonkeyPatch,
    binding: dict,
    marker: str,
):
    bridge = _load_script("validate_bridge_manifests")
    monkeypatch.setattr(
        bridge,
        "_report_for",
        lambda _names: ("dashboard/public/data/report.json", {}),
    )
    monkeypatch.setattr(bridge, "_covered_by_resolves", lambda _ref: True)
    errors, _findings = bridge.validate(
        Path("victim.yaml"), _bridge_manifest(bindings=[binding])
    )
    assert any(marker in error for error in errors)


def test_bridge_manifest_report_can_be_found_through_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    bridge = _load_script("validate_bridge_manifests")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "report.json").write_text(json.dumps({"suite": "legacy"}))
    monkeypatch.setattr(bridge, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(bridge, "DATA_DIR", data_dir)
    errors, _findings = bridge.validate(
        Path("victim.yaml"), _bridge_manifest(aliases=["legacy"])
    )
    assert not any("no committed report" in error for error in errors)


@pytest.mark.xfail(
    strict=True,
    reason="MANIFEST-GAP-population-pin: one malformed token satisfies revision+SHA pinning",
)
def test_bridge_manifest_population_pin_requires_revision_and_valid_sha(
    monkeypatch: pytest.MonkeyPatch,
):
    errors, findings = _validate_manifest(
        monkeypatch,
        _bridge_manifest(population={"pin_required": True}),
        report={"dataset_identity": {"sha256": "yes"}},
    )
    assert any("population pin" in problem for problem in [*errors, *findings])


def test_bridge_manifest_partial_and_unverified_completeness_are_findings(
    monkeypatch: pytest.MonkeyPatch,
):
    manifest = _bridge_manifest()
    manifest["bindings"][0]["audit"] = "partial"
    errors, findings = _validate_manifest(monkeypatch, manifest)
    assert not errors
    assert any("audit=partial" in finding for finding in findings)
    assert any("input-catalog verification pending" in finding for finding in findings)


def test_bridge_manifest_global_suite_and_alias_collisions_are_errors():
    bridge = _load_script("validate_bridge_manifests")
    manifests = {
        Path("one.yaml"): {"suite": "one", "aliases": ["shared"]},
        Path("two.yaml"): {"suite": "shared"},
    }
    errors = bridge.global_collisions(manifests)
    assert len(errors) == 1
    assert "namespace must be unique" in errors[0]


@pytest.mark.parametrize(
    ("strict", "errors", "findings", "expected"),
    [
        pytest.param(False, ["error"], [], 1, id="errors-always-fail"),
        pytest.param(False, [], ["finding"], 0, id="findings-visible"),
        pytest.param(True, [], ["finding"], 1, id="strict-findings-fail"),
    ],
)
def test_bridge_manifest_cli_error_and_finding_exit_policy(
    monkeypatch: pytest.MonkeyPatch,
    strict: bool,
    errors: list[str],
    findings: list[str],
    expected: int,
):
    bridge = _load_script("validate_bridge_manifests")
    manifests = {Path("victim.yaml"): _bridge_manifest()}
    monkeypatch.setattr(bridge, "load_manifests", lambda: manifests)
    monkeypatch.setattr(bridge, "global_collisions", lambda _manifests: [])
    monkeypatch.setattr(bridge, "validate", lambda _path, _manifest: (errors, findings))
    argv = ["validate_bridge_manifests.py"] + (["--strict"] if strict else [])
    monkeypatch.setattr(sys, "argv", argv)
    assert bridge.main() == expected


def test_bridge_manifest_cli_rejects_empty_manifest_set(
    monkeypatch: pytest.MonkeyPatch,
):
    bridge = _load_script("validate_bridge_manifests")
    monkeypatch.setattr(bridge, "load_manifests", lambda: {})
    monkeypatch.setattr(sys, "argv", ["validate_bridge_manifests.py"])
    assert bridge.main() == 1


@pytest.mark.xfail(
    strict=True,
    reason="MANIFEST-GAP-canonical-report: first sorted report silently wins a contest",
)
def test_bridge_manifest_rejects_multiple_reports_for_one_suite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    bridge = _load_script("validate_bridge_manifests")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for name in ("a.json", "b.json"):
        (data_dir / name).write_text(json.dumps({"suite": "victim"}))
    monkeypatch.setattr(bridge, "DATA_DIR", data_dir)
    errors, _findings = bridge.validate(Path("victim.yaml"), _bridge_manifest())
    assert any("multiple" in error or "ambiguous" in error for error in errors)


# ---------------------------------------------------------------------------
# scripts/closure_universe.py


def _load_closure_test_helpers() -> ModuleType:
    path = REPO_ROOT / "tests" / "test_closure_mutants.py"
    name = "_gate_regression_closure_helpers"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_closure_scope_declares_exact_program_roots_and_module_prefixes():
    closure = _load_script("closure_universe")
    assert closure.PROGRAM == "us-co/snap"
    assert [config.root for config in closure.ROOTS] == [
        "state-10-ccr-2506-1",
        "us-7-cfr-273",
        "us-7-usc-51",
    ]
    assert {config.source_file for config in closure.ROOTS} == {
        "co-provisions.jsonl",
        "cfr-273.jsonl",
        "usc-51.jsonl",
    }
    assert {config.module_root for config in closure.ROOTS} == {
        "us-co/regulations/10-ccr-2506-1",
        "us/regulations/7-cfr/273",
        "us/statutes/7",
    }


def test_closure_source_loader_keeps_every_nonblank_row_kind(tmp_path: Path):
    closure = _load_script("closure_universe")
    config = closure.RootConfig(
        root="synthetic",
        source_file="source.jsonl",
        citation_root="us/test",
        module_root="us/tests",
    )
    data = tmp_path / "data"
    data.mkdir()
    rows = [
        {"citation_path": f"us/test/{kind}", "heading": kind, "kind": kind}
        for kind in ("document", "part", "subpart", "title", "section")
    ]
    (data / config.source_file).write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n\n"
    )
    errors: list[str] = []
    loaded = closure._load_source_rows(config, data, errors)
    assert not errors
    assert {row["citation"] for row in loaded} == {
        row["citation_path"] for row in rows
    }


@pytest.mark.parametrize(
    ("mutation", "marker"),
    [
        pytest.param("missing", "could not be read", id="missing"),
        pytest.param("invalid-json", "invalid JSON", id="json"),
        pytest.param("non-object", "must be a JSON object", id="object"),
        pytest.param("missing-citation", "citation_path", id="citation"),
        pytest.param("outside-root", "outside declared root", id="root"),
        pytest.param("duplicate", "duplicate citation_path", id="duplicate"),
        pytest.param("heading-type", "heading", id="heading"),
    ],
)
def test_closure_source_rows_fail_closed_on_shape_identity_and_heading(
    tmp_path: Path,
    mutation: str,
    marker: str,
):
    closure = _load_script("closure_universe")
    config = closure.RootConfig(
        root="synthetic",
        source_file="source.jsonl",
        citation_root="us/test",
        module_root="us/tests",
    )
    data = tmp_path / "data"
    data.mkdir()
    valid = {"citation_path": "us/test/a", "heading": "A"}
    if mutation == "missing":
        raw = None
    elif mutation == "invalid-json":
        raw = "{not-json\n"
    elif mutation == "non-object":
        raw = "[]\n"
    elif mutation == "missing-citation":
        raw = json.dumps({"heading": "A"}) + "\n"
    elif mutation == "outside-root":
        raw = json.dumps({**valid, "citation_path": "us/other/a"}) + "\n"
    elif mutation == "duplicate":
        raw = json.dumps(valid) + "\n" + json.dumps(valid) + "\n"
    else:
        raw = json.dumps({**valid, "heading": 7}) + "\n"
    if raw is not None:
        (data / config.source_file).write_text(raw)
    errors: list[str] = []
    closure._load_source_rows(config, data, errors)
    assert any(marker in error for error in errors)


def test_closure_missing_or_null_source_heading_becomes_empty_string(
    tmp_path: Path,
):
    closure = _load_script("closure_universe")
    config = closure.RootConfig(
        root="synthetic",
        source_file="source.jsonl",
        citation_root="us/test",
        module_root="us/tests",
    )
    data = tmp_path / "data"
    data.mkdir()
    (data / config.source_file).write_text(
        json.dumps({"citation_path": "us/test/a"})
        + "\n"
        + json.dumps({"citation_path": "us/test/b", "heading": None})
        + "\n"
    )
    errors: list[str] = []
    assert closure._load_source_rows(config, data, errors) == [
        {"citation": "us/test/a", "heading": ""},
        {"citation": "us/test/b", "heading": ""},
    ]
    assert not errors


@pytest.mark.parametrize(
    ("mutation", "marker"),
    [
        pytest.param("missing", "is missing", id="missing"),
        pytest.param("root-shape", "YAML mapping", id="root-map"),
        pytest.param("schema", "expected schema", id="schema"),
        pytest.param("snapshots-type", "snapshots", id="snapshot-list"),
        pytest.param("snapshot-shape", "must be a mapping", id="snapshot-map"),
        pytest.param("duplicate", "duplicate snapshot", id="duplicate"),
        pytest.param("metadata", "source_repo", id="metadata"),
        pytest.param("unsafe", "unsafe snapshot path", id="safe-path"),
        pytest.param("sha-format", "lowercase 64-hex", id="sha-format"),
        pytest.param("sha-drift", "sha256 mismatch", id="sha-drift"),
        pytest.param("required", "required file", id="required-files"),
    ],
)
def test_closure_provenance_validates_schema_snapshots_metadata_and_exact_bytes(
    tmp_path: Path,
    mutation: str,
    marker: str,
):
    helpers = _load_closure_test_helpers()
    closure_dir = helpers._write_inputs(tmp_path)
    closure = _load_script("closure_universe")
    provenance_path = closure_dir / "data" / "provenance.yaml"
    document = yaml.safe_load(provenance_path.read_text())
    if mutation == "missing":
        provenance_path.unlink()
    elif mutation == "root-shape":
        document = ["not-a-mapping"]
    elif mutation == "schema":
        document["schema"] = "invented"
    elif mutation == "snapshots-type":
        document["snapshots"] = {}
    elif mutation == "snapshot-shape":
        document["snapshots"][0] = "not-a-map"
    elif mutation == "duplicate":
        document["snapshots"].append(copy.deepcopy(document["snapshots"][0]))
    elif mutation == "metadata":
        document["snapshots"][0]["source_repo"] = ""
    elif mutation == "unsafe":
        document["snapshots"][0]["file"] = "../source.jsonl"
    elif mutation == "sha-format":
        document["snapshots"][0]["sha256"] = "ABC"
    elif mutation == "sha-drift":
        source = closure_dir / "data" / document["snapshots"][0]["file"]
        source.write_text(source.read_text() + "\n")
    else:
        document["snapshots"] = document["snapshots"][1:]
    if mutation != "missing":
        provenance_path.write_text(yaml.safe_dump(document, sort_keys=False))
    errors: list[str] = []
    closure._load_provenance(closure_dir / "data", errors)
    assert any(marker in error for error in errors)


def test_closure_pinned_tree_is_duplicate_free(tmp_path: Path):
    closure = _load_script("closure_universe")
    tree = tmp_path / "rulespec-us-files.txt"
    tree.write_text("us/tests/a.yaml\nus/tests/a.yaml\n")
    errors: list[str] = []
    assert closure._load_tree(tree, errors) == {"us/tests/a.yaml"}
    assert any("duplicate paths" in error for error in errors)


@pytest.mark.parametrize(
    ("kind", "payload", "marker"),
    [
        pytest.param("universe", "[", "could not be read", id="universe-yaml"),
        pytest.param("universe", "- not-a-mapping\n", "YAML mapping", id="universe-map"),
        pytest.param("summary", "{", "could not be read", id="summary-json"),
        pytest.param("summary", "[]\n", "JSON object", id="summary-object"),
    ],
)
def test_closure_artifact_loaders_reject_malformed_or_nonmapping_roots(
    tmp_path: Path,
    kind: str,
    payload: str,
    marker: str,
):
    closure = _load_script("closure_universe")
    path = tmp_path / ("universe.yaml" if kind == "universe" else "summary.json")
    path.write_text(payload)
    errors: list[str] = []
    loaded = (
        closure._load_universe(path, errors)
        if kind == "universe"
        else closure._load_summary(path, errors)
    )
    assert loaded is None
    assert any(marker in error for error in errors)


@pytest.mark.parametrize(
    ("mutation", "marker"),
    [
        pytest.param("schema", "expected schema", id="schema"),
        pytest.param("program", "expected program", id="program"),
        pytest.param("root", "expected root", id="root"),
        pytest.param("provenance", "provenance", id="provenance"),
        pytest.param("provenance-sha", "lowercase 64-hex", id="provenance-sha"),
        pytest.param("ratchet", "ratchet", id="ratchet"),
        pytest.param("ratchet-pin", "content-identity", id="ratchet-pin"),
        pytest.param("pending-max", "pending_max", id="pending-max"),
    ],
)
def test_closure_universe_artifact_validates_identity_provenance_and_ratchet(
    tmp_path: Path,
    mutation: str,
    marker: str,
):
    helpers = _load_closure_test_helpers()
    closure, closure_dir = helpers._generate_baseline(tmp_path)
    config = closure.ROOTS[0]
    path, document = helpers._load_universe(closure_dir, helpers.STATE_UNIVERSE)
    if mutation == "schema":
        document["schema"] = "invented"
    elif mutation == "program":
        document["program"] = "other"
    elif mutation == "root":
        document["root"] = "other"
    elif mutation == "provenance":
        document["provenance"] = []
    elif mutation == "provenance-sha":
        document["provenance"]["source_sha256"] = "bad"
    elif mutation == "ratchet":
        document["ratchet"] = []
    elif mutation == "ratchet-pin":
        document["ratchet"]["pins_sha256"] = "0" * 64
    else:
        document["ratchet"]["pending_max"] = True
    errors: list[str] = []
    closure._validate_universe(
        document,
        config=config,
        path=path,
        tree_paths=closure._load_tree(
            closure_dir / "data" / closure.TREE_FILE, []
        ),
        allow_missing_pins=False,
        allow_generated_path_drift=False,
        errors=errors,
    )
    assert any(marker in error for error in errors)


@pytest.mark.parametrize(
    ("mutation", "marker"),
    [
        pytest.param("schema", "expected schema", id="schema"),
        pytest.param("program", "expected program", id="program"),
        pytest.param("roots-type", "roots", id="roots-list"),
        pytest.param("duplicate-root", "duplicate root", id="duplicate-root"),
        pytest.param("missing-root", "missing roots", id="root-inventory"),
        pytest.param("total", "total", id="total-type"),
        pytest.param("status", "by_status", id="status-type"),
        pytest.param("conservation", "status counts total", id="conservation"),
        pytest.param("reason", "reason counts", id="reason-count"),
        pytest.param("pin", "pins_sha256", id="pin"),
        pytest.param("pending", "pending_max", id="pending"),
    ],
)
def test_closure_summary_validates_identity_inventory_counts_and_pins(
    tmp_path: Path,
    mutation: str,
    marker: str,
):
    helpers = _load_closure_test_helpers()
    closure, closure_dir = helpers._generate_baseline(tmp_path)
    path = closure_dir / "summary.json"
    document = json.loads(path.read_text())
    row = document["roots"][0]
    if mutation == "schema":
        document["schema"] = "invented"
    elif mutation == "program":
        document["program"] = "other"
    elif mutation == "roots-type":
        document["roots"] = {}
    elif mutation == "duplicate-root":
        document["roots"].append(copy.deepcopy(row))
    elif mutation == "missing-root":
        document["roots"] = document["roots"][1:]
    elif mutation == "total":
        row["total"] = True
    elif mutation == "status":
        row["by_status"]["pending"] = -1
    elif mutation == "conservation":
        row["total"] += 1
    elif mutation == "reason":
        row["by_reason"] = {"": -1}
    elif mutation == "pin":
        row["pins_sha256"] = "bad"
    else:
        row["pending_max"] = False
    errors: list[str] = []
    closure._validate_summary_baseline(
        document,
        path=path,
        allow_missing_pins=False,
        errors=errors,
    )
    assert any(marker in error for error in errors)


@pytest.mark.parametrize(
    ("row", "tree", "marker"),
    [
        pytest.param("not-a-map", set(), "must be a mapping", id="mapping"),
        pytest.param(
            {"heading": "A", "status": "pending"},
            set(),
            "citation",
            id="citation",
        ),
        pytest.param(
            {"citation": "us/test/a", "heading": 1, "status": "pending"},
            set(),
            "heading",
            id="heading",
        ),
        pytest.param(
            {
                "citation": "us/test/a",
                "heading": "A",
                "note": 1,
                "status": "pending",
            },
            set(),
            "note",
            id="note",
        ),
        pytest.param(
            {"citation": "us/test/a", "heading": "A", "status": "done"},
            set(),
            "must be one of",
            id="status",
        ),
        pytest.param(
            {
                "citation": "us/test/a",
                "heading": "A",
                "status": "encoded",
                "encoded_by": [],
            },
            set(),
            "non-empty list",
            id="encoded-empty",
        ),
        pytest.param(
            {
                "citation": "us/test/a",
                "heading": "A",
                "status": "encoded",
                "encoded_by": ["us/tests/a.yaml", "us/tests/a.yaml"],
            },
            {"us/tests/a.yaml"},
            "duplicate paths",
            id="encoded-duplicate",
        ),
        pytest.param(
            {
                "citation": "us/test/a",
                "heading": "A",
                "status": "excluded",
                "basis": "Source text.",
            },
            set(),
            "reason",
            id="excluded-reason",
        ),
        pytest.param(
            {
                "citation": "us/test/a",
                "heading": "A",
                "status": "pending",
                "reason": "reserved",
            },
            set(),
            "must not carry",
            id="pending-contradiction",
        ),
        pytest.param(
            {
                "citation": "us/test/a",
                "heading": "A",
                "status": "encoded",
                "encoded_by": ["us/tests/a.yaml"],
                "basis": "contradiction",
            },
            {"us/tests/a.yaml"},
            "must not carry",
            id="encoded-contradiction",
        ),
        pytest.param(
            {
                "citation": "us/test/a",
                "heading": "A",
                "status": "excluded",
                "reason": "reserved",
                "basis": "Text says reserved.",
                "encoded_by": ["us/tests/a.yaml"],
            },
            {"us/tests/a.yaml"},
            "must not carry",
            id="excluded-contradiction",
        ),
    ],
)
def test_closure_provision_shape_status_and_contradiction_invariants(
    row: object,
    tree: set[str],
    marker: str,
):
    closure = _load_script("closure_universe")
    errors: list[str] = []
    closure._validate_provision_rows(
        [row],
        config=closure.RootConfig("synthetic", "source", "us/test", "us/tests"),
        label="mutant",
        tree_paths=tree,
        allow_generated_path_drift=False,
        errors=errors,
    )
    assert any(marker in error for error in errors)


@pytest.mark.parametrize("mutation", ["provisions-type", "duplicate-citation"])
def test_closure_provisions_are_a_list_with_unique_citations(mutation: str):
    closure = _load_script("closure_universe")
    row = {"citation": "us/test/a", "heading": "A", "status": "pending"}
    rows: object = {} if mutation == "provisions-type" else [row, copy.deepcopy(row)]
    errors: list[str] = []
    closure._validate_provision_rows(
        rows,
        config=closure.RootConfig("synthetic", "source", "us/test", "us/tests"),
        label="mutant",
        tree_paths=set(),
        allow_generated_path_drift=False,
        errors=errors,
    )
    assert errors


@pytest.mark.parametrize(
    "path",
    [
        pytest.param(" us/tests/a.yaml", id="whitespace"),
        pytest.param("/us/tests/a.yaml", id="absolute"),
        pytest.param("us/tests/../a.yaml", id="traversal"),
        pytest.param("us\\tests\\a.yaml", id="backslash"),
        pytest.param("us/tests/a.json", id="extension"),
        pytest.param("us/tests/a.test.yaml", id="test-module"),
    ],
)
def test_closure_named_modules_must_be_safe_production_yaml_paths(path: str):
    closure = _load_script("closure_universe")
    errors: list[str] = []
    closure._validate_encoded_by(
        [path], label="mutant", tree_paths={path}, errors=errors
    )
    assert any("safe, non-test" in error for error in errors)


@pytest.mark.xfail(
    strict=True,
    reason="CLOSURE-GAP-basis-grounding: any nonblank exclusion prose is accepted",
)
def test_closure_exclusion_basis_must_be_grounded_in_pinned_source_text():
    closure = _load_script("closure_universe")
    config = closure.ROOTS[0]
    errors: list[str] = []
    closure._validate_provision_rows(
        [
            {
                "citation": f"{config.citation_root}/eligibility-formula",
                "heading": "Eligibility amount formula",
                "status": "excluded",
                "reason": "no_household_computation",
                "basis": "Reviewed.",
            }
        ],
        config=config,
        label="mutant",
        tree_paths=set(),
        allow_generated_path_drift=False,
        errors=errors,
    )
    assert errors


def test_closure_note_survives_while_heading_refreshes_from_pinned_source():
    closure = _load_script("closure_universe")
    config = closure.RootConfig("synthetic", "source", "us/test", "us/tests")
    rows = closure._merge_provisions(
        config,
        [{"citation": "us/test/a", "heading": "New heading"}],
        set(),
        [
            {
                "citation": "us/test/a",
                "heading": "Old heading",
                "status": "pending",
                "note": "Reviewed note.",
            }
        ],
    )
    assert rows == [
        {
            "citation": "us/test/a",
            "heading": "New heading",
            "status": "pending",
            "note": "Reviewed note.",
        }
    ]


def test_closure_join_found_module_requires_partial_coverage_statement():
    closure = _load_script("closure_universe")
    errors: list[str] = []
    closure._validate_provision_rows(
        [
            {
                "citation": "us/test/a",
                "heading": "A",
                "status": "pending",
                "join_found_module": "us/tests/a.yaml",
            }
        ],
        config=closure.RootConfig("synthetic", "source", "us/test", "us/tests"),
        label="mutant",
        tree_paths={"us/tests/a.yaml"},
        allow_generated_path_drift=False,
        errors=errors,
    )
    assert any("requires `partial_coverage`" in error for error in errors)


@pytest.mark.xfail(
    strict=True,
    reason="CLOSURE-GAP-partial-binding: disclosure is not bound to a joined/deferred module",
)
def test_closure_partial_coverage_requires_present_joined_deferred_module():
    closure = _load_script("closure_universe")
    errors: list[str] = []
    closure._validate_provision_rows(
        [
            {
                "citation": "us/test/a",
                "heading": "A",
                "status": "pending",
                "partial_coverage": "An unspecified module defers an output.",
                "join_found_module": "us/tests/ghost.yaml",
            }
        ],
        config=closure.RootConfig("synthetic", "source", "us/test", "us/tests"),
        label="mutant",
        tree_paths=set(),
        allow_generated_path_drift=False,
        errors=errors,
    )
    assert errors


@pytest.mark.parametrize("mutant", ["missing-universe", "missing-summary", "stale-summary"])
def test_closure_check_is_read_only_and_rejects_missing_or_stale_artifacts(
    tmp_path: Path,
    mutant: str,
):
    helpers = _load_closure_test_helpers()
    closure, closure_dir = helpers._generate_baseline(tmp_path)
    if mutant == "missing-universe":
        target = (
            closure_dir
            / "universes"
            / "us-co-snap"
            / helpers.STATE_UNIVERSE
        )
        target.unlink()
    else:
        target = closure_dir / "summary.json"
        if mutant == "missing-summary":
            target.unlink()
        else:
            target.write_text(target.read_text() + " \n")
    before = {
        path: path.read_bytes()
        for path in closure_dir.rglob("*")
        if path.is_file()
    }
    assert closure.run(closure_dir, check=True) == 1
    after = {
        path: path.read_bytes()
        for path in closure_dir.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_closure_summary_counts_reasons_and_closed_are_exact():
    closure = _load_script("closure_universe")
    universes = {
        "a": {
            "ratchet": {"pins_sha256": "1" * 64, "pending_max": 0},
            "provisions": [
                {
                    "citation": "us/test/a",
                    "heading": "A",
                    "status": "excluded",
                    "reason": "reserved",
                    "basis": "Reserved.",
                },
                {
                    "citation": "us/test/b",
                    "heading": "B",
                    "status": "encoded",
                    "encoded_by": ["us/tests/b.yaml"],
                },
            ],
        },
        "b": {
            "ratchet": {"pins_sha256": "2" * 64, "pending_max": 1},
            "provisions": [
                {"citation": "us/test/c", "heading": "C", "status": "pending"}
            ],
        },
    }
    errors: list[str] = []
    summary = closure._summary_document(
        universes, tree_paths={"us/tests/b.yaml"}, errors=errors
    )
    assert not errors
    assert summary["closed"] is False
    assert summary["roots"][0]["by_status"] == {
        "encoded": 1,
        "excluded": 1,
        "pending": 0,
    }
    assert summary["roots"][0]["by_reason"] == {"reserved": 1}


def test_closure_generate_writes_exact_artifact_set_deterministically(tmp_path: Path):
    helpers = _load_closure_test_helpers()
    closure = _load_script("closure_universe")
    closure_dir = helpers._write_inputs(tmp_path)
    assert closure.run(closure_dir, check=False) == 0
    paths = sorted(
        path.relative_to(closure_dir).as_posix()
        for path in closure_dir.rglob("*")
        if path.is_file() and ("universes/" in path.as_posix() or path.name == "summary.json")
    )
    assert paths == [
        "summary.json",
        "universes/us-co-snap/state-10-ccr-2506-1.yaml",
        "universes/us-co-snap/us-7-cfr-273.yaml",
        "universes/us-co-snap/us-7-usc-51.yaml",
    ]
    before = {path: path.read_bytes() for path in closure_dir.rglob("*") if path.is_file()}
    assert closure.run(closure_dir, check=False) == 0
    after = {path: path.read_bytes() for path in closure_dir.rglob("*") if path.is_file()}
    assert after == before


@pytest.mark.xfail(
    strict=True,
    reason="CLOSURE-GAP-empty-denominator: zero pinned rows yield closed=true",
)
def test_closure_empty_pinned_denominator_cannot_be_closed():
    closure = _load_script("closure_universe")
    universes = {
        config.root: {
            "ratchet": {"pins_sha256": "0" * 64, "pending_max": 0},
            "provisions": [],
        }
        for config in closure.ROOTS
    }
    errors: list[str] = []
    summary = closure._summary_document(universes, tree_paths=set(), errors=errors)
    assert errors or summary["closed"] is False


def test_closure_v1_ratchet_migration_requires_both_matching_copies():
    closure = _load_script("closure_universe")
    config = closure.ROOTS[0]
    provenance = {
        "source_file": config.source_file,
        "source_repo": "repo",
        "source_ref": "ref",
        "source_sha256": "1" * 64,
        "rulespec_file": closure.TREE_FILE,
        "rulespec_repo": "repo",
        "rulespec_ref": "ref",
        "rulespec_sha256": "2" * 64,
    }
    current = closure._pins_sha256(provenance)
    committed = {
        "provenance": provenance,
        "ratchet": {"pending_max": 3},
    }
    summary = {"pending_max": 3}
    errors: list[str] = []
    baseline = closure._ratchet_baseline(
        config,
        committed=committed,
        summary_row=summary,
        current_pins=current,
        errors=errors,
    )
    assert baseline == closure.RatchetBaseline(current, 3)
    assert not errors

    committed["ratchet"]["pins_sha256"] = current
    errors = []
    assert (
        closure._ratchet_baseline(
            config,
            committed=committed,
            summary_row=summary,
            current_pins=current,
            errors=errors,
        )
        is None
    )
    assert any("missing from the summary" in error for error in errors)


def test_closure_source_pin_change_starts_new_ratchet_baseline(tmp_path: Path):
    helpers = _load_closure_test_helpers()
    closure, closure_dir = helpers._generate_baseline(tmp_path)
    source = closure_dir / "data" / "co-provisions.jsonl"
    added = helpers._provision(
        "us-co/regulation/10-ccr-2506-1/4.101",
        "10 CCR 2506-1 4.101",
        version="2026-07-16-10-ccr-2506-1",
    )
    source.write_text(source.read_text() + json.dumps(added) + "\n")
    helpers._update_snapshot_hash(closure_dir, "co-provisions.jsonl")
    assert closure.main(["--generate", "--closure-dir", str(closure_dir)]) == 0
    _path, document = helpers._load_universe(closure_dir, helpers.STATE_UNIVERSE)
    assert document["ratchet"]["pending_max"] == 2


def test_closure_ratchet_fingerprint_ignores_descriptive_provenance_text():
    closure = _load_script("closure_universe")
    first = {
        "source_file": "source.jsonl",
        "source_repo": "old repo",
        "source_ref": "old ref",
        "source_sha256": "1" * 64,
        "rulespec_file": closure.TREE_FILE,
        "rulespec_repo": "old repo",
        "rulespec_ref": "old ref",
        "rulespec_sha256": "2" * 64,
    }
    second = {
        **first,
        "source_repo": "new repo",
        "source_ref": "new ref",
        "rulespec_repo": "new repo",
        "rulespec_ref": "new ref",
    }
    assert closure._pins_sha256(first) == closure._pins_sha256(second)


def test_closure_rejects_shallow_checkout_for_history_ratchet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    closure = _load_script("closure_universe")
    closure_dir = tmp_path / "closure"
    closure_dir.mkdir()

    def git_result(_repo: Path, *args: str):
        if args == ("rev-parse", "--show-toplevel"):
            return subprocess.CompletedProcess(args, 0, stdout=f"{tmp_path}\n".encode())
        if args == ("rev-parse", "--is-shallow-repository"):
            return subprocess.CompletedProcess(args, 0, stdout=b"true\n")
        raise AssertionError(args)

    monkeypatch.setattr(closure, "_run_git", git_result)
    errors: list[str] = []
    assert (
        closure._history_ratchet_baseline(
            closure_dir,
            closure.ROOTS[0],
            current_pins="0" * 64,
            errors=errors,
        )
        is None
    )
    assert any("shallow Git checkout" in error for error in errors)


def test_closure_pending_rise_exceeding_disclosures_is_rejected():
    closure = _load_script("closure_universe")
    config = closure.RootConfig("synthetic", "source", "us/test", "us/tests")
    snapshots = {
        "source": {
            "source_repo": "repo",
            "source_ref": "ref",
            "sha256": "1" * 64,
        },
        closure.TREE_FILE: {
            "source_repo": "repo",
            "source_ref": "ref",
            "sha256": "2" * 64,
        },
    }
    provenance = closure._generated_provenance(config, snapshots)
    source_rows = [
        {"citation": f"us/test/{name}", "heading": name} for name in ("a", "b")
    ]
    committed = [
        {
            "citation": "us/test/a",
            "heading": "a",
            "status": "pending",
            "partial_coverage": "A deferred output.",
        },
        {"citation": "us/test/b", "heading": "b", "status": "pending"},
    ]
    errors: list[str] = []
    closure._build_universe(
        config,
        source_rows=source_rows,
        tree_paths={"us/tests/a.yaml"},
        snapshots=snapshots,
        committed_rows=committed,
        baseline=closure.RatchetBaseline(closure._pins_sha256(provenance), 0),
        errors=errors,
    )
    assert any("only 1 of the 2" in error for error in errors)


@pytest.mark.xfail(
    strict=True,
    reason="CLOSURE-GAP-ratchet-disclosure: old disclosures mask unrelated reopenings",
)
def test_closure_existing_disclosure_cannot_mask_unrelated_pending_rise():
    closure = _load_script("closure_universe")
    config = closure.RootConfig("synthetic", "source", "us/test", "us/tests")
    snapshots = {
        "source": {"source_repo": "repo", "source_ref": "ref", "sha256": "1" * 64},
        closure.TREE_FILE: {
            "source_repo": "repo",
            "source_ref": "ref",
            "sha256": "2" * 64,
        },
    }
    provenance = closure._generated_provenance(config, snapshots)
    errors: list[str] = []
    closure._build_universe(
        config,
        source_rows=[
            {"citation": "us/test/a", "heading": "A"},
            {"citation": "us/test/b", "heading": "B"},
        ],
        tree_paths={"us/tests/a.yaml"},
        snapshots=snapshots,
        committed_rows=[
            {
                "citation": "us/test/a",
                "heading": "A",
                "status": "pending",
                "partial_coverage": "Old disclosed deferred output.",
            },
            {"citation": "us/test/b", "heading": "B", "status": "pending"},
        ],
        baseline=closure.RatchetBaseline(closure._pins_sha256(provenance), 1),
        errors=errors,
    )
    assert errors


def test_closure_published_universe_counts_match_reviewed_result():
    summary = json.loads((REPO_ROOT / "closure" / "summary.json").read_text())
    assert summary["closed"] is False
    assert {
        row["root"]: (row["total"], row["by_status"])
        for row in summary["roots"]
    } == {
        "state-10-ccr-2506-1": (
            290,
            {"encoded": 281, "excluded": 9, "pending": 0},
        ),
        "us-7-cfr-273": (
            39,
            {"encoded": 2, "excluded": 14, "pending": 23},
        ),
        "us-7-usc-51": (
            827,
            {"encoded": 16, "excluded": 544, "pending": 267},
        ),
    }


@pytest.mark.xfail(
    strict=True,
    reason="CLOSURE-GAP-source-path: provenance records but does not require source_path",
)
def test_closure_snapshot_provenance_requires_source_path(tmp_path: Path):
    helpers = _load_closure_test_helpers()
    closure_dir = helpers._write_inputs(tmp_path)
    closure = _load_script("closure_universe")
    path = closure_dir / "data" / "provenance.yaml"
    document = yaml.safe_load(path.read_text())
    for snapshot in document["snapshots"]:
        snapshot.pop("source_path", None)
    path.write_text(yaml.safe_dump(document, sort_keys=False))
    errors: list[str] = []
    closure._load_provenance(closure_dir / "data", errors)
    assert any("source_path" in error for error in errors)


# ---------------------------------------------------------------------------
# scripts/merge_closure_classifications.py


def _merge_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    provision: dict | None = None,
    pending_max: int = 1,
) -> tuple[ModuleType, Path, Path, Path]:
    merge = _load_script("merge_closure_classifications")
    universes = tmp_path / "universes"
    classifications = tmp_path / "classifications"
    universes.mkdir()
    classifications.mkdir()
    tree = tmp_path / "rulespec-us-files.txt"
    tree.write_text("us/tests/a.yaml\nus/tests/corrected.yaml\n")
    if provision is None:
        provision = {"citation": "us/test/a", "heading": "A", "status": "pending"}
    universe = {
        "schema": "axiom_oracles.closure_universe.v1",
        "program": "us-co/snap",
        "root": "synthetic",
        "ratchet": {"pins_sha256": "0" * 64, "pending_max": pending_max},
        "provisions": [provision],
    }
    universe_path = universes / "synthetic.yaml"
    universe_path.write_text(
        "# generated header\n" + yaml.safe_dump(universe, sort_keys=False)
    )
    monkeypatch.setattr(merge, "UNIVERSE_DIR", universes)
    monkeypatch.setattr(merge, "PINNED_TREE", tree)
    return merge, classifications, universe_path, tree


def _write_classification(path: Path, row: object, *, root: str = "rows") -> None:
    payload: object = {root: [row]} if root else [row]
    path.write_text(yaml.safe_dump(payload, sort_keys=False))


@pytest.mark.parametrize("root", ["", "rows", "provisions"])
def test_merge_closure_accepts_list_rows_and_provisions_roots(
    tmp_path: Path,
    root: str,
):
    merge = _load_script("merge_closure_classifications")
    path = tmp_path / "classifications.yaml"
    row = {"citation": "us/test/a", "status": "pending"}
    _write_classification(path, row, root=root)
    assert merge._rows_from(path) == [row]


@pytest.mark.xfail(
    strict=True,
    reason="MERGE-GAP-ingestion: malformed or citation-less rows are silently dropped",
)
@pytest.mark.parametrize(
    "row",
    [
        pytest.param({"citaiton": "us/test/a", "status": "pending"}, id="citation"),
        pytest.param("not-a-map", id="mapping"),
    ],
)
def test_merge_closure_rejects_rows_it_cannot_ingest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    row: object,
):
    merge, classifications, _universe, _tree = _merge_workspace(
        tmp_path, monkeypatch
    )
    _write_classification(classifications / "mutant.yaml", row)
    assert merge.main(["--in", str(classifications), "--dry-run"]) != 0


def test_merge_closure_rejects_duplicate_classification_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    merge, classifications, universe, _tree = _merge_workspace(tmp_path, monkeypatch)
    row = {"citation": "us/test/a", "status": "pending"}
    _write_classification(classifications / "a.yaml", row)
    _write_classification(classifications / "b.yaml", row)
    before = universe.read_bytes()
    assert merge.main(["--in", str(classifications)]) == 1
    assert universe.read_bytes() == before


@pytest.mark.parametrize(
    ("mutation", "marker"),
    [
        pytest.param("absent", "not present", id="absent-citation"),
        pytest.param("unknown", "unknown status", id="unknown-status"),
        pytest.param("no-reason", "without a reason", id="exclusion-reason"),
        pytest.param("no-basis", "without a basis", id="exclusion-basis"),
        pytest.param("taxonomy", "outside the taxonomy", id="taxonomy"),
        pytest.param("operationalized", "absent from the pinned", id="operationalized"),
        pytest.param("downgrade-note", "requires a note", id="downgrade-note"),
        pytest.param("encoded-path", "absent from tree", id="encoded-path"),
        pytest.param("pending-rise", "RAISE pending", id="pending-rise"),
    ],
)
def test_merge_closure_refusals_return_nonzero_and_write_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mutation: str,
    marker: str,
):
    provision = {"citation": "us/test/a", "heading": "A", "status": "pending"}
    pending_max = 1
    row: dict = {"citation": "us/test/a", "status": "excluded", "reason": "reserved", "basis": "Reserved."}
    if mutation == "absent":
        row["citation"] = "us/test/missing"
    elif mutation == "unknown":
        row["status"] = "done"
    elif mutation == "no-reason":
        row.pop("reason")
    elif mutation == "no-basis":
        row.pop("basis")
    elif mutation == "taxonomy":
        row["reason"] = "invented"
    elif mutation == "operationalized":
        row["reason"] = "operationalized_by: us/tests/ghost.yaml"
    elif mutation == "downgrade-note":
        provision = {
            "citation": "us/test/a",
            "heading": "A",
            "status": "encoded",
            "encoded_by": ["us/tests/a.yaml"],
        }
        pending_max = 1
        row = {"citation": "us/test/a", "status": "pending"}
    elif mutation == "encoded-path":
        row = {
            "citation": "us/test/a",
            "status": "encoded",
            "encoded_by": ["us/tests/ghost.yaml"],
        }
    else:
        pending_max = 0
        row = {"citation": "us/test/a", "status": "pending"}
    merge, classifications, universe, _tree = _merge_workspace(
        tmp_path,
        monkeypatch,
        provision=provision,
        pending_max=pending_max,
    )
    _write_classification(classifications / "mutant.yaml", row)
    before = universe.read_bytes()
    assert merge.main(["--in", str(classifications)]) == 1
    assert marker in capsys.readouterr().err
    assert universe.read_bytes() == before


@pytest.mark.xfail(
    strict=True,
    reason="MERGE-GAP-basis-grounding: arbitrary nonblank basis text is accepted",
)
def test_merge_closure_exclusion_basis_is_grounded_in_provision_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    merge, classifications, _universe, _tree = _merge_workspace(tmp_path, monkeypatch)
    _write_classification(
        classifications / "mutant.yaml",
        {
            "citation": "us/test/a",
            "status": "excluded",
            "reason": "no_household_computation",
            "basis": "Reviewed.",
        },
    )
    assert merge.main(["--in", str(classifications), "--dry-run"]) != 0


@pytest.mark.xfail(
    strict=True,
    reason="MERGE-GAP-deferred-binding: downgrade note is not checked against module content",
)
def test_merge_closure_downgrade_requires_actual_deferred_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    provision = {
        "citation": "us/test/a",
        "heading": "A",
        "status": "encoded",
        "encoded_by": ["us/tests/a.yaml"],
    }
    merge, classifications, _universe, _tree = _merge_workspace(
        tmp_path, monkeypatch, provision=provision
    )
    _write_classification(
        classifications / "mutant.yaml",
        {
            "citation": "us/test/a",
            "status": "pending",
            "note": "Claims a deferred output, but no module bytes are available.",
        },
    )
    assert merge.main(["--in", str(classifications), "--dry-run"]) != 0


@pytest.mark.parametrize("action", ["exclude", "downgrade", "pending-note", "encode"])
def test_merge_closure_successful_actions_write_reviewed_fields_and_preserve_header(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
):
    provision = {"citation": "us/test/a", "heading": "A", "status": "pending"}
    if action == "downgrade":
        provision = {
            "citation": "us/test/a",
            "heading": "A",
            "status": "encoded",
            "encoded_by": ["us/tests/a.yaml"],
        }
    merge, classifications, universe, _tree = _merge_workspace(
        tmp_path, monkeypatch, provision=provision
    )
    if action == "exclude":
        row = {
            "citation": "us/test/a",
            "status": "excluded",
            "reason": "operationalized_by:   us/tests/a.yaml",
            "basis": "The provision delegates this computation.",
        }
    elif action == "downgrade":
        row = {
            "citation": "us/test/a",
            "status": "pending",
            "note": "  module   defers   benefit  ",
        }
    elif action == "pending-note":
        row = {
            "citation": "us/test/a",
            "status": "pending",
            "note": "  reviewed   later  ",
        }
    else:
        row = {
            "citation": "us/test/a",
            "status": "encoded",
            "encoded_by": ["us/tests/corrected.yaml"],
        }
    _write_classification(classifications / "review.yaml", row)
    assert merge.main(["--in", str(classifications)]) == 0
    assert universe.read_text().startswith("# generated header\n")
    document = yaml.safe_load(universe.read_text())
    result = document["provisions"][0]
    assert document["ratchet"]["pending_max"] == 1
    if action == "exclude":
        assert result["status"] == "excluded"
        assert result["reason"] == "operationalized_by: us/tests/a.yaml"
        assert "encoded_by" not in result
    elif action == "downgrade":
        assert result["status"] == "pending"
        assert result["partial_coverage"] == "module defers benefit"
        assert "encoded_by" not in result
    elif action == "pending-note":
        assert result["note"] == "reviewed later"
    else:
        assert result["encoded_by"] == ["us/tests/corrected.yaml"]


def test_merge_closure_dry_run_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    merge, classifications, universe, _tree = _merge_workspace(tmp_path, monkeypatch)
    _write_classification(
        classifications / "review.yaml",
        {
            "citation": "us/test/a",
            "status": "excluded",
            "reason": "reserved",
            "basis": "The provision is reserved.",
        },
    )
    before = universe.read_bytes()
    assert merge.main(["--in", str(classifications), "--dry-run"]) == 0
    assert universe.read_bytes() == before


@pytest.mark.xfail(
    strict=True,
    reason="MERGE-GAP-encoding-shape: empty, duplicate, or unsafe encoded_by is accepted",
)
@pytest.mark.parametrize(
    "paths",
    [
        pytest.param([], id="empty"),
        pytest.param(["us/tests/a.yaml", "us/tests/a.yaml"], id="duplicate"),
        pytest.param(["../escape.yaml"], id="unsafe"),
    ],
)
def test_merge_closure_rejects_invalid_encoded_by(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    paths: list[str],
):
    merge, classifications, _universe, tree = _merge_workspace(tmp_path, monkeypatch)
    if paths:
        tree.write_text(tree.read_text() + "\n".join(paths) + "\n")
    _write_classification(
        classifications / "mutant.yaml",
        {"citation": "us/test/a", "status": "encoded", "encoded_by": paths},
    )
    assert merge.main(["--in", str(classifications), "--dry-run"]) != 0


@pytest.mark.xfail(
    strict=True,
    reason="MERGE-GAP-status-invariants: encoding an excluded row leaves reason/basis",
)
def test_merge_closure_encoded_correction_removes_exclusion_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    provision = {
        "citation": "us/test/a",
        "heading": "A",
        "status": "excluded",
        "reason": "reserved",
        "basis": "Reserved.",
    }
    merge, classifications, _universe, _tree = _merge_workspace(
        tmp_path, monkeypatch, provision=provision
    )
    _write_classification(
        classifications / "mutant.yaml",
        {
            "citation": "us/test/a",
            "status": "encoded",
            "encoded_by": ["us/tests/a.yaml"],
        },
    )
    assert merge.main(["--in", str(classifications), "--dry-run"]) != 0


@pytest.mark.xfail(
    strict=True,
    reason="MERGE-DOC-GAP-ratchet: stale docstring says merger lowers pending_max",
)
def test_merge_closure_lowers_pending_max_as_docstring_promises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    merge, classifications, universe, _tree = _merge_workspace(tmp_path, monkeypatch)
    _write_classification(
        classifications / "review.yaml",
        {
            "citation": "us/test/a",
            "status": "excluded",
            "reason": "reserved",
            "basis": "The provision is reserved.",
        },
    )
    assert merge.main(["--in", str(classifications)]) == 0
    document = yaml.safe_load(universe.read_text())
    assert document["ratchet"]["pending_max"] == 0


def test_merge_then_closure_rejects_module_from_unpinned_tree_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    helpers = _load_closure_test_helpers()
    closure, closure_dir = helpers._generate_baseline(tmp_path)
    merge = _load_script("merge_closure_classifications")
    tree = closure_dir / "data" / "rulespec-us-files.txt"
    corrected = "us-co/regulations/10-ccr-2506-1/corrected.yaml"
    tree.write_text(tree.read_text() + corrected + "\n")
    classifications = tmp_path / "classifications"
    classifications.mkdir()
    _write_classification(
        classifications / "review.yaml",
        {
            "citation": "us-co/regulation/10-ccr-2506-1/4.100",
            "status": "encoded",
            "encoded_by": [corrected],
        },
    )
    monkeypatch.setattr(
        merge, "UNIVERSE_DIR", closure_dir / "universes" / "us-co-snap"
    )
    monkeypatch.setattr(merge, "PINNED_TREE", tree)
    assert merge.main(["--in", str(classifications)]) == 0
    assert closure.main(["--check", "--closure-dir", str(closure_dir)]) == 1


# ---------------------------------------------------------------------------
# origin/evidence-validator:axiom_oracles/evidence.py (read via git show)


EVIDENCE_REFS = (
    "origin/evidence-validator",
    "evidence-validator",
    "33a182ee",
)


def _git_branch_source(path: str) -> str:
    for ref in EVIDENCE_REFS:
        result = subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout
    pytest.skip(f"evidence-validator Git object unavailable for {path}")


@lru_cache
def _evidence_module() -> ModuleType:
    path = REPO_ROOT / "axiom_oracles" / "evidence.py"
    source = path.read_text() if path.is_file() else _git_branch_source(
        "axiom_oracles/evidence.py"
    )
    name = "_gate_regression_evidence"
    module = ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = "axiom_oracles"
    sys.modules[name] = module
    sys.modules["axiom_oracles.evidence"] = module
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


def _load_evidence_branch_script(name: str) -> ModuleType:
    _evidence_module()
    path = REPO_ROOT / "scripts" / f"{name}.py"
    source = _git_branch_source(f"scripts/{name}.py")
    module_name = f"_gate_regression_evidence_branch_{name}"
    module = ModuleType(module_name)
    module.__file__ = str(path)
    sys.modules[module_name] = module
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


def _full_evidence_documents() -> tuple[dict, list[dict]]:
    report = {
        "schema_version": "axiom.comparison_report.v2",
        "suite": "full-bound",
        "case_count": 2,
        "concepts": [
            {
                "id": "benefit",
                "comparison": "amount",
                "tolerance": 0,
                "relative_tolerance": 0,
            }
        ],
        "summary": {
            "comparison_count": 2,
            "match_count": 1,
            "mismatch_count": 1,
        },
        "aggregates": [
            {
                "concept": "benefit",
                "comparison_count": 2,
                "comparison_weight": 2,
                "match_count": 1,
                "mismatch_count": 1,
                "left_weighted_sum": 30,
                "right_weighted_sum": 31,
            }
        ],
        "mismatches": [
            {
                "case_id": "case-2",
                "concept": "benefit",
                "left": 20,
                "right": 21,
                "tolerance": 0,
                "relative_tolerance": 0,
            }
        ],
        "cases": [],
    }
    chunk = [
        {
            "id": "case-1",
            "r": 100,
            "h": {},
            "i": [{"n": "income", "v": 10}],
            "v": [{"c": "benefit", "l": 10, "x": 10}],
            "m": [],
        },
        {
            "id": "case-2",
            "r": 0,
            "h": {},
            "i": [{"n": "income", "v": 20}],
            "v": [],
            "m": [{"c": "benefit", "l": 20, "x": 21, "d": 1}],
        },
    ]
    return report, chunk


def _write_full_evidence(
    tmp_path: Path,
) -> tuple[ModuleType, Path, Path, Path]:
    evidence = _evidence_module()
    report, chunk = _full_evidence_documents()
    data_dir = tmp_path / "dashboard" / "public" / "data"
    suite_dir = data_dir / "cases" / report["suite"]
    suite_dir.mkdir(parents=True)
    report_path = data_dir / "report.json"
    chunk_path = suite_dir / "chunk-0.json"
    index_path = suite_dir / "index.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    chunk_path.write_text(json.dumps(chunk, separators=(",", ":")) + "\n")
    index_path.write_text(
        json.dumps(evidence.build_chunk_index(report_path), indent=2) + "\n"
    )
    validated = evidence.validate_suite_evidence(report_path)
    assert validated.binding == "bound"
    assert validated.reconciliation == "full"
    assert validated.valid is True
    return evidence, report_path, chunk_path, index_path


def _read_evidence(report_path: Path, chunk_path: Path) -> tuple[dict, list[dict]]:
    return json.loads(report_path.read_text()), json.loads(chunk_path.read_text())


def _write_evidence(
    report_path: Path,
    chunk_path: Path,
    report: dict,
    chunk: object,
) -> None:
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    chunk_path.write_text(json.dumps(chunk, separators=(",", ":")) + "\n")


def _refresh_evidence_index(
    evidence: ModuleType,
    report_path: Path,
    chunk_path: Path,
    index_path: Path,
    *,
    refresh_verdict_identity: bool = True,
) -> None:
    index = json.loads(index_path.read_text())
    index["report_path"], index["report_sha256"] = evidence.report_identity(
        report_path
    )
    payload = json.loads(chunk_path.read_text())
    rows = payload if isinstance(payload, list) else payload["cases"]
    index["chunks"] = [
        {
            "name": chunk_path.name,
            "sha256": evidence.sha256_path(chunk_path),
            "cases": len(rows),
        }
    ]
    index["chunk_count"] = 1
    index["count"] = len(rows)
    if refresh_verdict_identity:
        result = evidence.validate_suite_evidence(report_path)
        if result.case_verdicts_sha256 is None:
            index.pop("case_verdicts_sha256", None)
        else:
            index["case_verdicts_sha256"] = result.case_verdicts_sha256
    index_path.write_text(json.dumps(index, indent=2) + "\n")


@pytest.mark.parametrize(
    ("mutation", "marker"),
    [
        pytest.param("non-object", "report must be an object", id="report-object"),
        pytest.param("count-missing", "summary.match_count is missing", id="count-missing"),
        pytest.param("count-bool", "is not a non-negative integer", id="count-type"),
        pytest.param("count-conservation", "summary counts do not conserve", id="counts-conserve"),
        pytest.param("case-count-type", "case_count is not a non-negative integer", id="case-count-type"),
        pytest.param("case-count-drift", "does not match 2 parsed cases", id="case-count-drift"),
        pytest.param("chunk-envelope", "object with a cases array", id="chunk-envelope"),
        pytest.param("inline-match-type", ".matched must be a boolean", id="inline-match-type"),
    ],
)
def test_evidence_report_count_case_and_chunk_shape_mutants(
    tmp_path: Path,
    mutation: str,
    marker: str,
):
    evidence, report_path, chunk_path, _index_path = _write_full_evidence(tmp_path)
    report, chunk = _read_evidence(report_path, chunk_path)
    if mutation == "non-object":
        report_path.write_text("[]\n")
    elif mutation == "count-missing":
        del report["summary"]["match_count"]
        report_path.write_text(json.dumps(report))
    elif mutation == "count-bool":
        report["summary"]["comparison_count"] = True
        report_path.write_text(json.dumps(report))
    elif mutation == "count-conservation":
        report["summary"]["comparison_count"] = 3
        report_path.write_text(json.dumps(report))
    elif mutation == "case-count-type":
        report["case_count"] = True
        report_path.write_text(json.dumps(report))
    elif mutation == "case-count-drift":
        report["case_count"] = 3
        report_path.write_text(json.dumps(report))
    elif mutation == "chunk-envelope":
        chunk_path.write_text(json.dumps({"cases": {}}))
    else:
        report["case_count"] = 3
        report["cases"] = [{"case_id": "inline", "matched": 1}]
        report_path.write_text(json.dumps(report))
    result = evidence.validate_suite_evidence(report_path)
    assert any(marker in defect for defect in result.content_defects), result.defects


@pytest.mark.parametrize(
    ("field", "counts", "actual"),
    [
        pytest.param(
            "comparison_count",
            {"comparison_count": 3, "match_count": 2, "mismatch_count": 1},
            2,
            id="comparison",
        ),
        pytest.param(
            "match_count",
            {"comparison_count": 2, "match_count": 0, "mismatch_count": 2},
            1,
            id="matches",
        ),
        pytest.param(
            "mismatch_count",
            {"comparison_count": 2, "match_count": 2, "mismatch_count": 0},
            1,
            id="mismatches",
        ),
    ],
)
def test_evidence_full_reconciliation_recomputes_each_summary_count(
    tmp_path: Path,
    field: str,
    counts: dict,
    actual: int,
):
    evidence, report_path, _chunk_path, _index_path = _write_full_evidence(tmp_path)
    report = json.loads(report_path.read_text())
    report["summary"] = counts
    report_path.write_text(json.dumps(report))
    result = evidence.validate_suite_evidence(report_path)
    assert any(
        f"summary.{field}" in defect
        and f"parsed per-case verdicts {actual}" in defect
        for defect in result.content_defects
    )


def test_evidence_cardinality_recomputes_chunk_row_count(tmp_path: Path):
    evidence = _evidence_module()
    data = tmp_path / "dashboard/public/data"
    suite_dir = data / "cases/cardinality"
    suite_dir.mkdir(parents=True)
    report_path = data / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "suite": "cardinality",
                "case_count": 1,
                "summary": {
                    "comparison_count": 2,
                    "match_count": 2,
                    "mismatch_count": 0,
                },
                "cases": [],
            }
        )
    )
    (suite_dir / "chunk-0.json").write_text(
        json.dumps([{"id": "case-1", "r": None, "h": {}, "m": []}])
    )
    result = evidence.validate_suite_evidence(report_path)
    assert result.reconciliation == "cardinality"
    assert any("parsed chunk cardinality 1" in defect for defect in result.content_defects)


def test_evidence_zero_cases_is_an_explicit_execution_evidence_defect(
    tmp_path: Path,
):
    evidence = _evidence_module()
    data = tmp_path / "dashboard/public/data"
    data.mkdir(parents=True)
    report_path = data / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "suite": "empty",
                "case_count": 0,
                "summary": {
                    "comparison_count": 0,
                    "match_count": 0,
                    "mismatch_count": 0,
                },
                "cases": [],
            }
        )
    )
    result = evidence.validate_suite_evidence(report_path)
    assert any(
        "no committed per-case execution evidence" in defect
        for defect in result.content_defects
    )


@pytest.mark.parametrize(
    ("mutation", "marker"),
    [
        pytest.param("id-type", "case id must be", id="id-type"),
        pytest.param("id-empty", "empty case id", id="id-empty"),
        pytest.param("id-text-collision", "duplicate case id '1'", id="id-normalization"),
        pytest.param("cross-source-collision", "duplicate case id", id="cross-source-id"),
        pytest.param("missing-r", ".r is missing", id="r-missing"),
        pytest.param("missing-h", ".h is missing", id="h-missing"),
        pytest.param("missing-m", ".m is missing", id="m-missing"),
        pytest.param("r-type", ".r must be a finite number or null", id="r-type"),
        pytest.param("h-type", ".h must be an object", id="h-type"),
        pytest.param("m-row", ".m[0] must be an object", id="m-row"),
        pytest.param("m-values", ".m[0] is missing l, x", id="m-values"),
        pytest.param("i-type", ".i must be an array", id="i-type"),
        pytest.param("i-row", ".i[0] must be an object", id="i-row"),
        pytest.param("i-value", ".i[0] is missing v", id="i-value"),
        pytest.param("i-name", ".i[0].n must be a non-empty string", id="i-name"),
        pytest.param("v-type", ".v must be an array", id="v-type"),
        pytest.param("v-row", ".v[0] must be an object", id="v-row"),
        pytest.param("v-values", ".v[0] is missing l, x", id="v-values"),
        pytest.param("disposition", ".e must be a non-empty string", id="disposition"),
        pytest.param("delta-missing", ".d is missing", id="delta-missing"),
        pytest.param("delta-nonnumeric", ".d must be null", id="delta-nonnumeric"),
        pytest.param("delta-null", ".d must be a finite number", id="delta-null"),
        pytest.param("explicit-rate-null", ".r must equal", id="rate-null"),
    ],
)
def test_evidence_compact_case_shape_and_dashboard_semantic_mutants(
    tmp_path: Path,
    mutation: str,
    marker: str,
):
    evidence, report_path, chunk_path, _index_path = _write_full_evidence(tmp_path)
    report, chunk = _read_evidence(report_path, chunk_path)
    if mutation == "id-type":
        chunk[0]["id"] = []
    elif mutation == "id-empty":
        chunk[0]["id"] = ""
    elif mutation == "id-text-collision":
        chunk[0]["id"], chunk[1]["id"] = 1, "1"
    elif mutation == "cross-source-collision":
        report["case_count"] = 3
        report["cases"] = [
            {"case_id": "case-1", "matches": [], "mismatches": []}
        ]
    elif mutation == "missing-r":
        del chunk[0]["r"]
    elif mutation == "missing-h":
        del chunk[0]["h"]
    elif mutation == "missing-m":
        del chunk[0]["m"]
    elif mutation == "r-type":
        chunk[0]["r"] = "100"
    elif mutation == "h-type":
        chunk[0]["h"] = []
    elif mutation == "m-row":
        chunk[1]["m"] = [None]
    elif mutation == "m-values":
        chunk[1]["m"] = [{"c": "benefit"}]
    elif mutation == "i-type":
        chunk[0]["i"] = {}
    elif mutation == "i-row":
        chunk[0]["i"] = [None]
    elif mutation == "i-value":
        chunk[0]["i"] = [{"n": "income"}]
    elif mutation == "i-name":
        chunk[0]["i"][0]["n"] = []
    elif mutation == "v-type":
        chunk[0]["v"] = {}
    elif mutation == "v-row":
        chunk[0]["v"] = [None]
    elif mutation == "v-values":
        chunk[0]["v"] = [{"c": "benefit"}]
    elif mutation == "disposition":
        chunk[1]["m"][0]["e"] = []
    elif mutation == "delta-missing":
        del chunk[1]["m"][0]["d"]
    elif mutation == "delta-nonnumeric":
        chunk[1]["m"][0].update(l="left", x="right", d=0)
    elif mutation == "delta-null":
        chunk[1]["m"][0]["d"] = None
    else:
        chunk[0]["r"] = None
    _write_evidence(report_path, chunk_path, report, chunk)
    result = evidence.validate_suite_evidence(report_path)
    assert any(marker in defect for defect in result.content_defects), result.defects


@pytest.mark.parametrize(
    ("mutation", "marker"),
    [
        pytest.param("concepts-type", "report concepts must be an array", id="concepts-type"),
        pytest.param("concept-row", "concepts[0] must be an object", id="concept-row"),
        pytest.param("concept-id", ".id must be a non-empty string", id="concept-id"),
        pytest.param("concept-duplicate", "report concepts repeats", id="concept-duplicate"),
        pytest.param("comparison-name", ".comparison must be a non-empty string", id="comparison"),
        pytest.param("tolerance-missing", ".tolerance is missing", id="tolerance-missing"),
        pytest.param("tolerance-invalid", "finite non-negative number", id="tolerance-invalid"),
        pytest.param("verdict-no-rule", "has no report concept definition", id="verdict-rule"),
        pytest.param("match-placement", "match tolerance semantics", id="match-placement"),
        pytest.param("mismatch-placement", "mismatch tolerance semantics", id="mismatch-placement"),
        pytest.param("aggregates-type", "report aggregates must be an array", id="aggregates-type"),
        pytest.param("aggregate-row", "aggregates[0] must be an object", id="aggregate-row"),
        pytest.param("aggregate-concept", ".concept must be a non-empty string", id="aggregate-concept"),
        pytest.param("aggregate-duplicate", "aggregates repeats concept", id="aggregate-duplicate"),
        pytest.param("aggregate-count", "is not a non-negative integer", id="aggregate-count"),
        pytest.param("aggregate-impossible", "exceeds comparison_count", id="aggregate-impossible"),
        pytest.param("aggregate-alias", "does not match derived verdict count", id="aggregate-alias"),
        pytest.param("aggregate-extra", "have no stored verdicts", id="aggregate-extra"),
        pytest.param("aggregate-missing", "have no report aggregate", id="aggregate-missing"),
        pytest.param("aggregate-drift", "stored verdicts contain", id="aggregate-drift"),
        pytest.param("weight-type", "comparison_weight must be a finite number", id="weight-type"),
        pytest.param("weight-drift", "cannot be reproduced", id="weight-drift"),
        pytest.param("aggregate-value", "must be a finite number", id="aggregate-value"),
        pytest.param("mismatches-type", "report mismatches must be an array", id="mismatches-type"),
        pytest.param("mismatch-row", "mismatches[0] must be an object", id="mismatch-row"),
        pytest.param("mismatch-concept", ".concept must be a non-empty string", id="mismatch-concept"),
        pytest.param("mismatch-values", "must carry left and right values", id="mismatch-values"),
        pytest.param("mismatch-duplicate", "mismatches repeats case/concept", id="mismatch-duplicate"),
        pytest.param("mismatch-extra", "have no stored mismatch verdict", id="mismatch-extra"),
        pytest.param("mismatch-missing", "have no report mismatch row", id="mismatch-missing"),
        pytest.param("report-disposition", "disposition must be an object", id="report-disposition"),
        pytest.param("disposition-counts", "counts must be an object", id="disposition-counts"),
        pytest.param("disposition-count-type", "is not a non-negative integer", id="disposition-count-type"),
        pytest.param("disposition-count-drift", "does not match 1 report mismatch", id="disposition-count-drift"),
    ],
)
def test_evidence_full_semantic_reconciliation_mutants(
    tmp_path: Path,
    mutation: str,
    marker: str,
):
    evidence, report_path, chunk_path, _index_path = _write_full_evidence(tmp_path)
    report, chunk = _read_evidence(report_path, chunk_path)
    concept = report["concepts"][0]
    aggregate = report["aggregates"][0]
    mismatch = report["mismatches"][0]
    if mutation == "concepts-type":
        report["concepts"] = {}
    elif mutation == "concept-row":
        report["concepts"] = [None]
    elif mutation == "concept-id":
        concept["id"] = ""
    elif mutation == "concept-duplicate":
        report["concepts"].append(copy.deepcopy(concept))
    elif mutation == "comparison-name":
        concept["comparison"] = ""
    elif mutation == "tolerance-missing":
        del concept["tolerance"]
    elif mutation == "tolerance-invalid":
        concept["relative_tolerance"] = -1
    elif mutation == "verdict-no-rule":
        chunk[0]["v"][0]["c"] = "other"
    elif mutation == "match-placement":
        chunk[0]["v"][0]["x"] = 11
    elif mutation == "mismatch-placement":
        chunk[1]["m"][0].update(x=20, d=0)
    elif mutation == "aggregates-type":
        report["aggregates"] = {}
    elif mutation == "aggregate-row":
        report["aggregates"] = [None]
    elif mutation == "aggregate-concept":
        aggregate["concept"] = ""
    elif mutation == "aggregate-duplicate":
        report["aggregates"].append(copy.deepcopy(aggregate))
    elif mutation == "aggregate-count":
        aggregate["comparison_count"] = True
    elif mutation == "aggregate-impossible":
        aggregate["mismatch_count"] = 3
    elif mutation == "aggregate-alias":
        aggregate["compared"] = 99
    elif mutation == "aggregate-extra":
        report["aggregates"].append(
            {"concept": "ghost", "comparison_count": 0, "mismatch_count": 0}
        )
    elif mutation == "aggregate-missing":
        report["aggregates"] = []
    elif mutation == "aggregate-drift":
        aggregate["mismatch_count"] = 0
        aggregate["match_count"] = 2
    elif mutation == "weight-type":
        aggregate["comparison_weight"] = "two"
    elif mutation == "weight-drift":
        aggregate["comparison_weight"] = 99
    elif mutation == "aggregate-value":
        aggregate["left_weighted_sum"] = "thirty"
    elif mutation == "mismatches-type":
        report["mismatches"] = {}
    elif mutation == "mismatch-row":
        report["mismatches"] = [None]
    elif mutation == "mismatch-concept":
        mismatch["concept"] = ""
    elif mutation == "mismatch-values":
        del mismatch["left"]
    elif mutation == "mismatch-duplicate":
        report["mismatches"].append(copy.deepcopy(mismatch))
    elif mutation == "mismatch-extra":
        mismatch["case_id"] = "ghost"
    elif mutation == "mismatch-missing":
        report["mismatches"] = []
    elif mutation == "report-disposition":
        mismatch["disposition"] = "explained_residual"
    else:
        mismatch["disposition"] = {
            "id": "d-1",
            "disposition": "explained_residual",
        }
        chunk[1]["m"][0]["e"] = "explained_residual"
        if mutation == "disposition-counts":
            counts: object = []
        elif mutation == "disposition-count-type":
            counts = {"explained_residual": "one"}
        else:
            counts = {"explained_residual": 0}
        report["summary"]["dispositioned"] = {"counts": counts}
    _write_evidence(report_path, chunk_path, report, chunk)
    result = evidence.validate_suite_evidence(report_path)
    assert any(marker in defect for defect in result.content_defects), result.defects


@pytest.mark.xfail(
    strict=True,
    reason="EVIDENCE-GAP-comparison-enum: unknown kinds fall through to eligibility truthiness",
)
def test_evidence_unknown_comparison_kind_fails_closed():
    evidence = _evidence_module()
    defects: list[str] = []
    evidence._concept_rules(
        {
            "concepts": [
                {
                    "id": "benefit",
                    "comparison": "ammount",
                    "tolerance": 0,
                    "relative_tolerance": 0,
                }
            ]
        },
        defects,
        "victim",
    )
    assert defects


@pytest.mark.parametrize(
    ("mutation", "marker"),
    [
        pytest.param("malformed", "not valid JSON", id="malformed"),
        pytest.param("non-object", "must be an object", id="object"),
        pytest.param("schema", "schema_version is not", id="schema"),
        pytest.param("suite", "declares suite", id="suite"),
        pytest.param("report-sha", "report_sha256 is invalid", id="report-sha"),
        pytest.param("verdict-sha", "case_verdicts_sha256 is invalid", id="verdict-sha"),
        pytest.param("chunks-type", "chunks must be an array", id="chunks-type"),
        pytest.param("descriptor-row", "chunks[0] must be an object", id="descriptor-row"),
        pytest.param("descriptor-name", ".name is invalid", id="descriptor-name"),
        pytest.param("descriptor-duplicate", "chunk index repeats", id="descriptor-duplicate"),
        pytest.param("descriptor-sha", ".sha256 is invalid", id="descriptor-sha"),
        pytest.param("descriptor-cases", ".cases is not a non-negative integer", id="descriptor-cases"),
        pytest.param("declared-extra", "names missing files", id="declared-extra"),
        pytest.param("actual-omitted", "omits committed chunks", id="actual-omitted"),
        pytest.param("chunk-sha", "sha256 does not match chunk index", id="chunk-sha"),
        pytest.param("chunk-cases", "case count does not match", id="chunk-cases"),
        pytest.param("chunk-count-type", "chunk_count is not", id="chunk-count-type"),
        pytest.param("chunk-count-value", "chunk index chunk_count", id="chunk-count-value"),
        pytest.param("count-type", "chunk index count is not", id="count-type"),
        pytest.param("count-value", "chunk index count", id="count-value"),
    ],
)
def test_evidence_chunk_index_shape_identity_set_and_cardinality_mutants(
    tmp_path: Path,
    mutation: str,
    marker: str,
):
    evidence, report_path, _chunk_path, index_path = _write_full_evidence(tmp_path)
    index = json.loads(index_path.read_text())
    descriptor = index["chunks"][0]
    if mutation == "malformed":
        index_path.write_text("{bad")
    elif mutation == "non-object":
        index_path.write_text("[]")
    elif mutation == "schema":
        index["schema_version"] = "legacy"
    elif mutation == "suite":
        index["suite"] = "foreign"
    elif mutation == "report-sha":
        index["report_sha256"] = "x"
    elif mutation == "verdict-sha":
        index["case_verdicts_sha256"] = "x"
    elif mutation == "chunks-type":
        index["chunks"] = {}
    elif mutation == "descriptor-row":
        index["chunks"] = [None]
    elif mutation == "descriptor-name":
        descriptor["name"] = "../chunk-0.json"
    elif mutation == "descriptor-duplicate":
        index["chunks"].append(copy.deepcopy(descriptor))
    elif mutation == "descriptor-sha":
        descriptor["sha256"] = "x"
    elif mutation == "descriptor-cases":
        descriptor["cases"] = True
    elif mutation == "declared-extra":
        index["chunks"].append(
            {"name": "chunk-1.json", "sha256": "0" * 64, "cases": 0}
        )
    elif mutation == "actual-omitted":
        index["chunks"] = []
    elif mutation == "chunk-sha":
        descriptor["sha256"] = "0" * 64
    elif mutation == "chunk-cases":
        descriptor["cases"] = 99
    elif mutation == "chunk-count-type":
        index["chunk_count"] = True
    elif mutation == "chunk-count-value":
        index["chunk_count"] = 2
    elif mutation == "count-type":
        index["count"] = True
    elif mutation == "count-value":
        index["count"] = 99
    if mutation not in {"malformed", "non-object"}:
        index_path.write_text(json.dumps(index))
    result = evidence.validate_suite_evidence(report_path)
    assert any(marker in defect for defect in result.binding_defects), result.defects


def test_evidence_chunk_object_cases_envelope_is_accepted(tmp_path: Path):
    evidence, report_path, chunk_path, index_path = _write_full_evidence(tmp_path)
    rows = json.loads(chunk_path.read_text())
    chunk_path.write_text(json.dumps({"cases": rows}))
    index_path.write_text(json.dumps(evidence.build_chunk_index(report_path)))
    result = evidence.validate_suite_evidence(report_path)
    assert (result.binding, result.reconciliation, result.valid) == (
        "bound",
        "full",
        True,
    )


def test_evidence_compared_values_may_be_arbitrary_json(tmp_path: Path):
    evidence, report_path, chunk_path, index_path = _write_full_evidence(tmp_path)
    report, chunk = _read_evidence(report_path, chunk_path)
    report.update(
        case_count=1,
        summary={"comparison_count": 1, "match_count": 1, "mismatch_count": 0},
        concepts=[
            {
                "id": "eligibility",
                "comparison": "eligibility",
                "tolerance": 0,
                "relative_tolerance": 0,
            }
        ],
        aggregates=[
            {
                "concept": "eligibility",
                "comparison_count": 1,
                "comparison_weight": 1,
                "match_count": 1,
                "mismatch_count": 0,
                "left_positive_weight": 1,
                "right_positive_weight": 1,
            }
        ],
        mismatches=[],
    )
    value = {"nested": [1, True, None]}
    chunk = [
        {
            "id": "json-case",
            "r": 100,
            "h": {},
            "m": [],
            "v": [{"c": "eligibility", "l": value, "x": copy.deepcopy(value)}],
        }
    ]
    _write_evidence(report_path, chunk_path, report, chunk)
    index_path.write_text(json.dumps(evidence.build_chunk_index(report_path)))
    assert evidence.validate_suite_evidence(report_path).valid is True


def test_evidence_case_verdict_commitment_is_row_order_independent(tmp_path: Path):
    evidence, report_path, chunk_path, index_path = _write_full_evidence(tmp_path)
    before = json.loads(index_path.read_text())["case_verdicts_sha256"]
    rows = json.loads(chunk_path.read_text())
    chunk_path.write_text(json.dumps(list(reversed(rows))))
    _refresh_evidence_index(
        evidence,
        report_path,
        chunk_path,
        index_path,
        refresh_verdict_identity=False,
    )
    result = evidence.validate_suite_evidence(report_path)
    assert result.case_verdicts_sha256 == before
    assert result.binding == "bound"
    assert result.valid is True


def test_evidence_defects_are_partitioned_ordered_and_results_immutable(
    tmp_path: Path,
):
    evidence, report_path, _chunk_path, _index_path = _write_full_evidence(tmp_path)
    report = json.loads(report_path.read_text())
    report["aggregates"][0]["left_weighted_sum"] = 999
    report_path.write_text(json.dumps(report))
    result = evidence.validate_suite_evidence(report_path)
    assert result.content_defects and result.binding_defects
    assert result.defects == result.content_defects + result.binding_defects
    assert result.content_valid is result.valid is result.clean is False
    with pytest.raises(FrozenInstanceError):
        result.binding = "bound"
    with pytest.raises(FrozenInstanceError):
        result.chunks[0].cases = 99


@pytest.mark.parametrize("surface", ["report", "chunk", "index"])
def test_evidence_unreadable_artifacts_surface_defects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
):
    evidence, report_path, chunk_path, index_path = _write_full_evidence(tmp_path)
    target = {"report": report_path, "chunk": chunk_path, "index": index_path}[surface]
    real_read_text = Path.read_text
    real_read_bytes = Path.read_bytes

    def blocked_text(path: Path, *args: object, **kwargs: object):
        if path.resolve() == target.resolve():
            raise PermissionError("blocked")
        return real_read_text(path, *args, **kwargs)

    def blocked_bytes(path: Path, *args: object, **kwargs: object):
        if path.resolve() == target.resolve():
            raise PermissionError("blocked")
        return real_read_bytes(path, *args, **kwargs)

    if surface == "chunk":
        monkeypatch.setattr(Path, "read_bytes", blocked_bytes)
    else:
        monkeypatch.setattr(Path, "read_text", blocked_text)
    result = evidence.validate_suite_evidence(report_path)
    marker = "cannot be read" if surface == "chunk" else "not valid JSON"
    assert any(marker in defect for defect in result.defects), result.defects


def test_evidence_build_index_rejects_invalid_content(tmp_path: Path):
    evidence, report_path, chunk_path, _index_path = _write_full_evidence(tmp_path)
    rows = json.loads(chunk_path.read_text())
    rows[0]["m"] = "not-an-array"
    chunk_path.write_text(json.dumps(rows))
    with pytest.raises(ValueError, match="cannot index inconsistent evidence"):
        evidence.build_chunk_index(report_path)


def test_evidence_build_index_recomputes_binding_and_preserves_legacy_metadata(
    tmp_path: Path,
):
    evidence, report_path, _chunk_path, index_path = _write_full_evidence(tmp_path)
    legacy = json.loads(index_path.read_text())
    legacy.update(
        report_path="stale",
        report_sha256="0" * 64,
        suite="stale",
        count=999,
        chunk_count=999,
        input_slots=["income"],
        display={"label": "legacy"},
    )
    index_path.write_text(json.dumps(legacy))
    rebuilt = evidence.build_chunk_index(report_path)
    identity, digest = evidence.report_identity(report_path)
    assert rebuilt["report_path"] == identity
    assert rebuilt["report_sha256"] == digest
    assert rebuilt["suite"] == "full-bound"
    assert rebuilt["count"] == 2
    assert rebuilt["chunk_count"] == 1
    assert rebuilt["input_slots"] == ["income"]
    assert rebuilt["display"] == {"label": "legacy"}


def test_evidence_build_index_orders_chunk_descriptors(tmp_path: Path):
    evidence, report_path, chunk_path, index_path = _write_full_evidence(tmp_path)
    rows = json.loads(chunk_path.read_text())
    chunk_path.write_text(json.dumps([rows[0]]))
    (chunk_path.parent / "chunk-1.json").write_text(json.dumps([rows[1]]))
    index = evidence.build_chunk_index(report_path)
    assert [row["name"] for row in index["chunks"]] == [
        "chunk-0.json",
        "chunk-1.json",
    ]
    index_path.write_text(json.dumps(index))
    assert evidence.validate_suite_evidence(report_path).valid is True


def test_evidence_validate_chunk_binding_infers_report_suite(tmp_path: Path):
    evidence, report_path, _chunk_path, _index_path = _write_full_evidence(tmp_path)
    result = evidence.validate_suite_evidence(report_path)
    assert evidence.validate_chunk_binding(report_path, result.chunks) == (
        "bound",
        (),
    )


@pytest.mark.xfail(
    strict=True,
    reason="EVIDENCE-GAP-cardinality-rate: verdict-free evidence may claim r=100",
)
def test_evidence_cardinality_only_case_requires_unmeasured_rate(tmp_path: Path):
    evidence = _evidence_module()
    data = tmp_path / "dashboard/public/data"
    suite_dir = data / "cases/cardinality"
    suite_dir.mkdir(parents=True)
    report_path = data / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "suite": "cardinality",
                "case_count": 1,
                "summary": {
                    "comparison_count": 1,
                    "match_count": 1,
                    "mismatch_count": 0,
                },
                "cases": [],
            }
        )
    )
    (suite_dir / "chunk-0.json").write_text(
        json.dumps([{"id": "case-1", "r": 100, "h": {}, "m": []}])
    )
    (suite_dir / "index.json").write_text(
        json.dumps(evidence.build_chunk_index(report_path))
    )
    result = evidence.validate_suite_evidence(report_path)
    assert result.content_valid is False
    assert any(".r" in defect and "unmeasured" in defect for defect in result.defects)


@pytest.mark.xfail(
    strict=True,
    reason="EVIDENCE-GAP-cardinality-label: malformed rows can still be labelled cardinality",
)
def test_evidence_cardinality_label_requires_well_formed_rows(tmp_path: Path):
    evidence = _evidence_module()
    data = tmp_path / "dashboard/public/data"
    suite_dir = data / "cases/cardinality"
    suite_dir.mkdir(parents=True)
    report_path = data / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "suite": "cardinality",
                "case_count": 1,
                "summary": {
                    "comparison_count": 1,
                    "match_count": 1,
                    "mismatch_count": 0,
                },
                "cases": [],
            }
        )
    )
    (suite_dir / "chunk-0.json").write_text(
        json.dumps([{"id": "case-1", "r": 100, "m": []}])
    )
    result = evidence.validate_suite_evidence(report_path)
    assert result.reconciliation == "none"


@pytest.mark.xfail(
    strict=True,
    reason="EVIDENCE-DOC-GAP-inline-boolean: PR result promises a full shape the module rejects",
)
def test_evidence_inline_boolean_case_supports_documented_full_reconciliation(
    tmp_path: Path,
):
    evidence = _evidence_module()
    data = tmp_path / "dashboard/public/data"
    data.mkdir(parents=True)
    report_path = data / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "suite": "inline",
                "case_count": 1,
                "summary": {
                    "comparison_count": 1,
                    "match_count": 1,
                    "mismatch_count": 0,
                },
                "cases": [{"case_id": "case-1", "matched": True}],
            }
        )
    )
    result = evidence.validate_suite_evidence(report_path)
    assert result.content_valid is True
    assert result.reconciliation == "full"


def test_evidence_branch_census_caps_strength_at_cardinality(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    evidence, report_path, _chunk_path, _index_path = _write_full_evidence(tmp_path)
    census = _load_evidence_branch_script("exercise_census")
    data_dir = report_path.parent
    monkeypatch.setattr(census, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(census, "DATA_DIR", data_dir)
    monkeypatch.setattr(census, "CASES_DIR", data_dir / "cases")
    monkeypatch.setattr(census, "BRIDGED_THROUGH", {})
    monkeypatch.setattr(census, "MANIFEST_STRICT_CLEAN", {})
    report = json.loads(report_path.read_text())
    row = census._census_suite(report["suite"], report, report_path)
    assert row["binding"] == "bound"
    assert row["reconciliation"] == "cardinality"
    assert evidence.validate_suite_evidence(report_path).reconciliation == "full"


def test_evidence_branch_census_keeps_legacy_unbound_index_visible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _evidence, report_path, _chunk_path, index_path = _write_full_evidence(tmp_path)
    index = json.loads(index_path.read_text())
    index["schema_version"] = "legacy"
    index_path.write_text(json.dumps(index))
    census = _load_evidence_branch_script("exercise_census")
    data_dir = report_path.parent
    monkeypatch.setattr(census, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(census, "DATA_DIR", data_dir)
    monkeypatch.setattr(census, "CASES_DIR", data_dir / "cases")
    monkeypatch.setattr(census, "BRIDGED_THROUGH", {})
    monkeypatch.setattr(census, "MANIFEST_STRICT_CLEAN", {})
    report = json.loads(report_path.read_text())
    row = census._census_suite(report["suite"], report, report_path)
    assert row["cases_scanned"] == 2
    assert row["binding"] == "unbound"
    assert row["reconciliation"] == "cardinality"


def test_evidence_branch_certificate_cites_exact_current_index_sha(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    evidence, report_path, _chunk_path, index_path = _write_full_evidence(tmp_path)
    certify = _load_evidence_branch_script("certify")
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    leg, citations, _defects = certify._suite_verdict(
        {
            "suite": "full-bound",
            "oracle_type": "reference",
            "oracle": "synthetic",
            "report": report_path.relative_to(tmp_path).as_posix(),
        }
    )
    citation = next(
        row for row in citations if row["claim"] == "case-evidence-index:full-bound"
    )
    assert citation["artifact"] == index_path.relative_to(tmp_path).as_posix()
    assert citation["sha256"] == evidence.sha256_path(index_path)
    assert leg["binding"] == "bound"
