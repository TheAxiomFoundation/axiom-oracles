"""Specification-derived regression coverage for the certification gates.

This is a defensive completeness suite.  Passing mutants prove documented
rejections; strict xfails name places where a gate does not yet satisfy its
own contract.  Gate implementations are deliberately never patched here.
"""

from __future__ import annotations

import copy
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
