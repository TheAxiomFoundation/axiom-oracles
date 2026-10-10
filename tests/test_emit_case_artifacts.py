from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    path = Path(__file__).parents[1] / "scripts" / "emit_case_artifacts.py"
    spec = importlib.util.spec_from_file_location("emit_case_artifacts", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _canonical_report(*, mismatch_count: int = 2) -> dict:
    return {
        "case_count": 2,
        "engines": {
            "left": "axiom",
            "right": "policyengine",
            "versions": {
                "policyengine": "4.18.9",
                "policyengine_core": "3.30.3",
                "policyengine_us": "1.767.3",
            },
        },
        "mismatches": [
            {
                "case_id": "case-1",
                "concept": "benefit",
                "left": 24,
                "right": 100,
                "difference": -76,
                "disposition": {"disposition": "bridge_artifact"},
            },
            {
                "case_id": "case-2",
                "concept": "eligibility",
                "left": False,
                "right": True,
                "difference": None,
            },
        ],
        "summary": {"mismatch_count": mismatch_count},
    }


def _served_rows() -> list[dict]:
    return [
        {
            "id": "case-1",
            "r": 50,
            "h": {"n": 1, "e": 0, "a": [30]},
            "m": [
                {
                    "c": "benefit",
                    "l": 24,
                    "x": 100,
                    "d": 76,
                    "e": "bridge_artifact",
                }
            ],
        },
        {
            "id": "case-2",
            "r": 50,
            "h": {"n": 1, "e": 0, "a": [17]},
            "m": [
                {
                    "c": "eligibility",
                    "l": False,
                    "x": True,
                    "d": None,
                }
            ],
        },
    ]


def _write_fixture(
    module,
    tmp_path: Path,
    *,
    report: dict,
    rows: list[dict],
    index_updates: dict | None = None,
) -> dict:
    data = tmp_path / "data"
    out = data / "cases" / "test-suite"
    out.mkdir(parents=True)
    module.DASHBOARD_DATA = data
    module.OUT_ROOT = data / "cases"
    basename = "axiom-policyengine-test"
    (data / f"{basename}.json").write_text(json.dumps(report))
    (out / "chunk-0.json").write_text(json.dumps(rows))
    index = {
        "suite": "test-suite",
        "count": len(rows),
        "chunks": 1,
        "chunk_size": 500,
        "engines": report["engines"],
        "mismatch_concepts": sorted(
            {mismatch["concept"] for mismatch in report["mismatches"]}
        ),
        "source": "ignored-full-report.json",
        "total_cases": report["case_count"],
    }
    index.update(index_updates or {})
    (out / "index.json").write_text(json.dumps(index))
    return {"basename": basename}


def test_case_artifact_check_accepts_exact_annotations_and_values(tmp_path):
    module = _load_module()
    config = _write_fixture(
        module,
        tmp_path,
        report=_canonical_report(),
        rows=_served_rows(),
    )

    problems, stats = module.check_suite_artifacts("test-suite", config)

    assert problems == []
    assert stats == {
        "cases": 2,
        "mismatches": 2,
        "annotated": 1,
        "silent": 0,
    }


def test_case_artifact_check_accepts_v1_chunk_descriptors(tmp_path):
    module = _load_module()
    config = _write_fixture(
        module,
        tmp_path,
        report=_canonical_report(),
        rows=_served_rows(),
        index_updates={
            "schema_version": "axiom_oracles.chunk_index.v1",
            "chunk_count": 1,
            "chunks": [
                {
                    "name": "chunk-0.json",
                    "sha256": "0" * 64,
                    "cases": 2,
                }
            ],
        },
    )

    problems, stats = module.check_suite_artifacts("test-suite", config)

    assert problems == []
    assert stats["cases"] == 2


def test_compact_case_preserves_exact_execution_inputs():
    module = _load_module()
    inputs = {"benefit#input.amount": 919999.9999999999, "benefit#input.flag": False}
    row = module.compact_case(
        {
            "case_id": "case-1",
            "matches": [{"concept": "benefit", "left": 1, "right": 1}],
            "mismatches": [],
            "metadata": {
                "axiom_entity": "Person",
                "axiom_entity_id": "recipient",
                "axiom_inputs": inputs,
            },
        },
        {},
    )

    assert row["execution"] == {
        "schema_version": "axiom_oracles.case_execution.v1",
        "axiom_entity": "Person",
        "axiom_entity_id": "recipient",
        "axiom_inputs": inputs,
    }


def test_case_artifact_check_rejects_silent_classification(tmp_path):
    module = _load_module()
    rows = _served_rows()
    rows[1]["m"][0]["e"] = "axiom_encoding_gap"
    config = _write_fixture(
        module,
        tmp_path,
        report=_canonical_report(),
        rows=rows,
    )

    problems, _ = module.check_suite_artifacts("test-suite", config)

    assert any("1 silent classifications" in problem for problem in problems)


def test_case_artifact_check_reports_missing_and_obsolete_rows(tmp_path):
    module = _load_module()
    rows = _served_rows()
    rows[1]["id"] = "obsolete-case"
    config = _write_fixture(
        module,
        tmp_path,
        report=_canonical_report(),
        rows=rows,
    )

    problems, _ = module.check_suite_artifacts("test-suite", config)

    assert any("canonical mismatch row(s) missing" in problem for problem in problems)
    assert any("obsolete served mismatch row(s)" in problem for problem in problems)


def test_case_artifact_check_rejects_chunk_and_index_drift(tmp_path):
    module = _load_module()
    report = _canonical_report()
    config = _write_fixture(
        module,
        tmp_path,
        report=report,
        rows=_served_rows(),
        index_updates={
            "count": 99,
            "engines": {"left": "axiom", "right": "policyengine"},
            "total_cases": 99,
        },
    )
    stale = module.OUT_ROOT / "test-suite" / "chunk-1.json"
    stale.write_text("[]")

    problems, _ = module.check_suite_artifacts("test-suite", config)

    assert any("chunk file set drift" in problem for problem in problems)
    assert any("index count" in problem for problem in problems)
    assert any("index engines drift" in problem for problem in problems)
    assert any("index total_cases" in problem for problem in problems)


def test_case_artifact_check_accepts_complete_mismatch_only_artifact(tmp_path):
    module = _load_module()
    report = _canonical_report()
    report["case_count"] = 10
    report["mismatches"][1]["case_id"] = "case-1"
    rows = _served_rows()[:1]
    rows[0]["m"].append(_served_rows()[1]["m"][0])
    config = _write_fixture(
        module,
        tmp_path,
        report=report,
        rows=rows,
        index_updates={"partial": "mismatch-only"},
    )

    problems, stats = module.check_suite_artifacts("test-suite", config)

    assert problems == []
    assert stats["mismatches"] == 2


def test_case_artifact_check_fails_closed_on_incomplete_canonical_list(tmp_path):
    module = _load_module()
    report = _canonical_report(mismatch_count=3)
    config = _write_fixture(
        module,
        tmp_path,
        report=report,
        rows=_served_rows(),
    )

    problems, stats = module.check_suite_artifacts("test-suite", config)

    assert stats == {}
    assert problems == [
        "test-suite: canonical mismatch list is incomplete (2/3); "
        "compact parity is uncheckable"
    ]


def test_served_delta_parity_accepts_either_faithful_convention():
    """PR #475 CI: two served-delta sign conventions coexist on main — this
    emitter writes right-minus-left (dashboard_delta) while the populace
    campaign artifacts (AL/MA/NC/SC/TN SNAP) serve the report's stored
    left-minus-right `difference`. The parity check must accept either
    (both are faithful projections of the same (l, x)) and reject anything
    else — otherwise whichever suite is being worked on silently redefines
    the contract for the rest."""
    import importlib.util
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "_eca", repo / "scripts" / "emit_case_artifacts.py"
    )
    eca = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(eca)
    report = {
        "mismatches": [
            {"case_id": "c1", "concept": "k", "left": 10.0, "right": 16.0, "difference": -6.0},
        ]
    }
    canonical, problems = eca._canonical_mismatch_payloads(report)
    assert not problems
    payload = canonical[("c1", "k")]
    assert payload["d"] == -6.0  # stored (left-minus-right)
    assert payload["d_alt"] == eca.dashboard_delta(10.0, 16.0)  # right-minus-left
    assert payload["d_alt"] == 6.0
    # a served row carrying either is parity-clean; a third value is drift
    for served_d, ok in ((-6.0, True), (6.0, True), (5.0, False), (None, False)):
        served = {("c1", "k"): {"l": 10.0, "x": 16.0, "d": served_d, "e": None}}
        drift = [
            key
            for key in served
            if any(canonical[key][f] != served[key][f] for f in ("l", "x"))
            or not (
                served[key]["d"] == canonical[key]["d"]
                or served[key]["d"] == canonical[key]["d_alt"]
            )
        ]
        assert (not drift) is ok, (served_d, drift)
