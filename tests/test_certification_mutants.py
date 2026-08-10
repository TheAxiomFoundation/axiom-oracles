"""Mutants the certification checks must kill (2026-07-26 audit, finding 16 lite).

Each test constructs an input the corresponding gate exists to reject and
asserts rejection. A check that has never been seen to fail is unproven; these
are the demonstrations, kept green forever. Grow this catalogue whenever a gate
gains a rule — a rule without a mutant here is not yet a rule.
"""

import copy
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

from axiom_oracles.evidence import (
    build_chunk_index,
    report_identity,
    sha256_path,
    strict_json_loads,
    validate_suite_evidence,
)

REPO = Path(__file__).resolve().parent.parent
EVIDENCE_FIXTURES = REPO / "tests" / "fixtures" / "evidence"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_zero_work_report_is_a_defect(tmp_path, monkeypatch):
    certify = _load("certify")
    mutant = REPO / "dashboard/public/data/zz-test-mutant.json"
    mutant.write_text(json.dumps({"suite": "victim", "summary": {}, "cases": []}))
    try:
        leg, _evs, defects = certify._suite_verdict(
            {
                "suite": "victim",
                "oracle_type": "reference",
                "oracle": "x",
                "report": "dashboard/public/data/zz-test-mutant.json",
            }
        )
        assert leg["clean"] is False
        assert any("zero comparisons" in d for d in defects)
    finally:
        mutant.unlink()


def test_missing_or_malformed_report_surfaces_a_leg_defect():
    certify = _load("certify")
    missing = "dashboard/public/data/zz-test-missing-report.json"
    malformed_path = REPO / "dashboard/public/data/zz-test-malformed-report.json"
    malformed_path.write_text("{not-json")
    try:
        for report, marker in (
            (missing, "does not exist"),
            (
                malformed_path.relative_to(REPO).as_posix(),
                "is not valid JSON",
            ),
        ):
            leg, _evidence, defects = certify._suite_verdict(
                {
                    "suite": "victim",
                    "oracle_type": "reference",
                    "oracle": "synthetic",
                    "report": report,
                }
            )
            assert leg["clean"] is False
            assert any(marker in defect for defect in defects), defects
    finally:
        malformed_path.unlink()


def test_malformed_nested_report_shapes_surface_leg_defects():
    certify = _load("certify")
    mutant_path = REPO / "dashboard/public/data/zz-test-malformed-shapes.json"
    base_summary = {
        "comparison_count": 0,
        "match_count": 0,
        "mismatch_count": 0,
    }
    mutants = (
        (
            {"suite": []},
            "report suite must be a non-empty, safe path component",
        ),
        ({"summary": []}, "report summary must be an object"),
        (
            {"summary": {**base_summary, "errors_by_engine": []}},
            "errors_by_engine must be an object",
        ),
        ({"summary": base_summary, "errors": 1}, "errors must be an array"),
        (
            {"summary": {**base_summary, "weighted": []}},
            "weighted must be an object",
        ),
        (
            {"summary": {**base_summary, "dispositioned": []}},
            "dispositioned must be an object",
        ),
        (
            {
                "summary": {
                    **base_summary,
                    "dispositioned": {"counts": []},
                }
            },
            "dispositioned.counts must be an object",
        ),
        (
            {
                "summary": {
                    **base_summary,
                    "dispositioned": {"dispositions_file": {"invalid": True}},
                }
            },
            "dispositions_file must be a repository-relative string",
        ),
        ({"summary": base_summary, "cases": {}}, "report cases must be an array"),
        ({"summary": base_summary, "mismatches": 1}, "mismatches must be an array"),
    )
    try:
        for updates, marker in mutants:
            report = {
                "suite": "victim",
                "case_count": 0,
                "summary": base_summary,
                "cases": [],
                **updates,
            }
            mutant_path.write_text(json.dumps(report))
            leg, _evidence, defects = certify._suite_verdict(
                {
                    "suite": "victim",
                    "oracle_type": "reference",
                    "oracle": "synthetic",
                    "report": mutant_path.relative_to(REPO).as_posix(),
                }
            )
            assert leg["clean"] is False
            assert any(marker in defect for defect in defects), (marker, defects)
    finally:
        mutant_path.unlink()


def test_mislabeled_report_is_a_defect():
    certify = _load("certify")
    mutant = REPO / "dashboard/public/data/zz-test-mutant2.json"
    mutant.write_text(
        json.dumps(
            {
                "suite": "someone-else",
                "summary": {
                    "comparison_count": 5,
                    "match_count": 5,
                    "mismatch_count": 0,
                },
            }
        )
    )
    try:
        leg, _evs, defects = certify._suite_verdict(
            {
                "suite": "victim",
                "oracle_type": "reference",
                "oracle": "x",
                "report": "dashboard/public/data/zz-test-mutant2.json",
            }
        )
        assert leg["clean"] is False
        assert any("identifies as" in d for d in defects)
    finally:
        mutant.unlink()


def test_nonexistent_disposition_file_is_a_defect():
    certify = _load("certify")
    mutant = REPO / "dashboard/public/data/zz-test-mutant3.json"
    mutant.write_text(
        json.dumps(
            {
                "suite": "victim",
                "summary": {
                    "comparison_count": 5,
                    "match_count": 0,
                    "mismatch_count": 5,
                    "dispositioned": {
                        "dispositions_file": "dispositions/does-not-exist.yaml",
                        "unexplained_count": 0,
                        "counts": {"upstream_engine_gap": 5},
                    },
                },
                "mismatches": [{} for _ in range(5)],
            }
        )
    )
    try:
        leg, _evs, defects = certify._suite_verdict(
            {
                "suite": "victim",
                "oracle_type": "reference",
                "oracle": "x",
                "report": "dashboard/public/data/zz-test-mutant3.json",
            }
        )
        assert leg["clean"] is False
        assert leg["unexplained"] == 5
        assert any("does not exist" in d for d in defects)
    finally:
        mutant.unlink()


def test_hidden_weighted_mass_is_a_defect():
    certify = _load("certify")
    mutant = REPO / "dashboard/public/data/zz-test-mutant4.json"
    mutant.write_text(
        json.dumps(
            {
                "suite": "victim",
                "summary": {
                    "comparison_count": 5,
                    "match_count": 5,
                    "mismatch_count": 0,
                    "weighted": {"mismatch_weight": 120000.0},
                },
            }
        )
    )
    try:
        leg, _evs, defects = certify._suite_verdict(
            {
                "suite": "victim",
                "oracle_type": "reference",
                "oracle": "x",
                "report": "dashboard/public/data/zz-test-mutant4.json",
            }
        )
        assert leg["clean"] is False
        assert any("weighted" in d for d in defects)
    finally:
        mutant.unlink()


def test_numeric_canonicalization_collapses_equal_values():
    census = _load("exercise_census")
    assert census._canonical_value(1) == census._canonical_value(1.0)
    assert census._canonical_value(0.0) == census._canonical_value(-0.0)
    big_a = "900719925474099310"
    big_b = "900719925474099311"
    assert census._canonical_value(big_a) != census._canonical_value(big_b)


# ── Round 2: the inputs the 2026-07-26 fix-verification demonstrated ─────────
# Each of these produced a clean verdict or a silent pass before the second
# round of remediations. They are kept as the standing proof that it no longer
# does. A rule without a mutant here is not yet a rule.


def _mutant(name: str, payload: dict):
    path = REPO / "dashboard/public/data" / name
    path.write_text(json.dumps(payload))
    return path


def _verdict(name: str, suite: str = "victim"):
    certify = _load("certify")
    return certify._suite_verdict(
        {
            "suite": suite,
            "oracle_type": "reference",
            "oracle": "x",
            "report": f"dashboard/public/data/{name}",
        }
    )


def test_errors_under_errors_by_engine_are_counted():
    """Conserving counts + an errored engine used to certify clean."""
    name = "zz-r2-errors.json"
    _mutant(
        name,
        {
            "suite": "victim",
            "cases": [],
            "errors": [{"message": "engine died"}],
            "summary": {
                "comparison_count": 5,
                "match_count": 5,
                "mismatch_count": 0,
                "errors_by_engine": {"left": 1},
            },
        },
    )
    try:
        leg, _e, defects = _verdict(name)
        assert leg["clean"] is False
        assert any("error" in d for d in defects)
    finally:
        (REPO / "dashboard/public/data" / name).unlink()


def test_counts_without_any_case_evidence_are_a_defect():
    name = "zz-r2-nocases.json"
    _mutant(
        name,
        {
            "suite": "victim",
            "summary": {
                "comparison_count": 5,
                "match_count": 5,
                "mismatch_count": 0,
            },
        },
    )
    try:
        leg, _e, defects = _verdict(name)
        assert leg["clean"] is False
        assert any("no per-case evidence" in d for d in defects)
    finally:
        (REPO / "dashboard/public/data" / name).unlink()


def test_foreign_dispositions_file_cannot_explain_this_suite():
    """Any existing file used to authorize disposition accounting."""
    name = "zz-r2-foreign-disp.json"
    _mutant(
        name,
        {
            "suite": "victim",
            "mismatches": [{}],
            "cases": [{"metadata": {"x": 1}}],
            "summary": {
                "comparison_count": 1,
                "match_count": 0,
                "mismatch_count": 1,
                "dispositioned": {
                    "dispositions_file": "dispositions/co-snap-ecps.yaml",
                    "counts": {"unexplained": 1},
                    "unexplained_count": 0,
                },
            },
        },
    )
    try:
        leg, _e, defects = _verdict(name)
        assert leg["clean"] is False
        assert any("declares suite" in d for d in defects)
        assert any("disagrees with unexplained_count" in d for d in defects)
    finally:
        (REPO / "dashboard/public/data" / name).unlink()


def test_absolute_disposition_path_is_rejected():
    name = "zz-r2-abspath.json"
    _mutant(
        name,
        {
            "suite": "victim",
            "mismatches": [{}],
            "cases": [{"metadata": {"x": 1}}],
            "summary": {
                "comparison_count": 1,
                "match_count": 0,
                "mismatch_count": 1,
                "dispositioned": {
                    "dispositions_file": "/dev/null",
                    "counts": {"unexplained": 0},
                    "unexplained_count": 0,
                },
            },
        },
    )
    try:
        leg, _e, defects = _verdict(name)
        assert leg["clean"] is False
        assert any("repository-relative" in d for d in defects)
    finally:
        (REPO / "dashboard/public/data" / name).unlink()


def test_long_exact_integers_do_not_merge():
    """Decimal's 28-digit default context merged these."""
    census = _load("exercise_census")
    a = "1234567890123456789012345678901"
    b = "1234567890123456789012345678902"
    assert census._canonical_value(a) != census._canonical_value(b)


def test_nonfinite_values_stay_distinct_from_numbers():
    census = _load("exercise_census")
    assert census._canonical_value("NaN") != census._canonical_value("1")
    assert census._canonical_value("Infinity") != census._canonical_value("1")
    # sNaN previously raised InvalidOperation out of the canonicaliser.
    census._canonical_value("sNaN")


def test_scalar_aliases_are_rejected():
    """A scalar alias iterates character-by-character and bypassed collisions."""
    vbm = _load("validate_bridge_manifests")
    errors, _f = vbm.validate(
        REPO / "axiom_oracles/bridges/manifests/zz-r2.yaml",
        {
            "schema": "axiom_oracles.bridge_manifest.v1",
            "suite": "zz",
            "aliases": "victim",
            "program": "p",
            "population": {},
            "oracle": {},
            "bindings": [
                {"kind": "constant", "group": "g", "reason": "r", "audit": "read"}
            ],
        },
    )
    assert any("must be a list" in e for e in errors)


def test_self_asserted_completeness_is_rejected():
    vbm = _load("validate_bridge_manifests")
    errors, _f = vbm.validate(
        REPO / "axiom_oracles/bridges/manifests/zz-r2b.yaml",
        {
            "schema": "axiom_oracles.bridge_manifest.v1",
            "suite": "zz",
            "program": "p",
            "population": {},
            "oracle": {},
            "bindings": [
                {"kind": "constant", "group": "g", "reason": "r", "audit": "read"}
            ],
            "completeness": {"status": "verified"},
        },
    )
    assert any("cannot be self-asserted" in e for e in errors)


def test_covered_by_must_resolve_to_something_real():
    vbm = _load("validate_bridge_manifests")
    assert vbm._covered_by_resolves("ABCDEFGHIJKL") is False
    assert vbm._covered_by_resolves("see the other suite, TBD") is False
    assert (
        vbm._covered_by_resolves("dashboard/public/data/axiom-snapqc-co-snap.json")
        is True
    )


def test_certified_requires_computed_true_premises_not_status_strings():
    certify = _load("certify")
    cert = certify.build_certificate("us-co/snap", certify.PROGRAMS["us-co/snap"])
    assert cert["certified"]["state"] == "unavailable"
    assert cert["certified"]["value"] is False


# ── Round 3: inputs from the second fix-verification ─────────────────────────


def test_invalid_counts_are_recorded_not_zeroed():
    """`error_count: "one"` became "no errors"; negatives cancelled real ones."""
    name = "zz-r3-junkcounts.json"
    _mutant(
        name,
        {
            "suite": "victim",
            "cases": [{"metadata": {"x": 1}}],
            "errors": [{"message": "boom"}],
            "summary": {
                "comparison_count": 1,
                "match_count": 1,
                "mismatch_count": 0,
                "error_count": "one",
            },
        },
    )
    try:
        leg, _e, defects = _verdict(name)
        assert leg["clean"] is False
        assert any("not a non-negative integer" in d for d in defects)
        assert any("error" in d for d in defects)
    finally:
        (REPO / "dashboard/public/data" / name).unlink()


def test_negative_count_cannot_cancel_a_real_error():
    name = "zz-r3-negcancel.json"
    _mutant(
        name,
        {
            "suite": "victim",
            "cases": [{"metadata": {"x": 1}}],
            "errors": [{"message": "boom"}],
            "summary": {
                "comparison_count": 1,
                "match_count": 1,
                "mismatch_count": 0,
                "error_count": -1,
            },
        },
    )
    try:
        leg, _e, defects = _verdict(name)
        assert leg["clean"] is False
        assert any("negative" in d for d in defects)
    finally:
        (REPO / "dashboard/public/data" / name).unlink()


def test_junk_case_rows_are_not_evidence():
    """`cases: [null]` satisfied the non-empty check."""
    name = "zz-r3-nullcases.json"
    _mutant(
        name,
        {
            "suite": "victim",
            "cases": [None],
            "summary": {
                "comparison_count": 1,
                "match_count": 1,
                "mismatch_count": 0,
            },
        },
    )
    try:
        leg, _e, defects = _verdict(name)
        assert leg["clean"] is False
        assert any("no per-case evidence" in d for d in defects)
    finally:
        (REPO / "dashboard/public/data" / name).unlink()


def test_unreadable_dispositions_file_cannot_authorize():
    """A file with no `suite:` returned None and was accepted."""
    name = "zz-r3-notadisp.json"
    _mutant(
        name,
        {
            "suite": "victim",
            "cases": [{"metadata": {"x": 1}}],
            "mismatches": [{}],
            "summary": {
                "comparison_count": 1,
                "match_count": 0,
                "mismatch_count": 1,
                "dispositioned": {
                    "dispositions_file": "README.md",
                    "counts": {"unexplained": 0},
                    "unexplained_count": 0,
                },
            },
        },
    )
    try:
        leg, _e, defects = _verdict(name)
        assert leg["clean"] is False
        assert any("not a readable dispositions document" in d for d in defects)
    finally:
        (REPO / "dashboard/public/data" / name).unlink()


def test_same_suite_empty_dispositions_document_cannot_authorize(tmp_path):
    """A matching suite declaration is not disposition evidence by itself."""
    suffix = tmp_path.name.replace("-", "_")
    report_name = f"zz-r5-empty-disp-{suffix}.json"
    artifact_name = f"zz-r5-empty-disp-{suffix}.yaml"
    report_path = REPO / "dashboard/public/data" / report_name
    artifact_path = REPO / "dashboard/public/data" / artifact_name
    try:
        artifact_path.write_text(
            json.dumps(
                {
                    "schema": "axiom_oracles.dispositions.v1",
                    "suite": "victim",
                    "entries": [],
                }
            )
        )
        _mutant(
            report_name,
            {
                "suite": "victim",
                "cases": [{"metadata": {"x": 1}}],
                "mismatches": [{}],
                "summary": {
                    "comparison_count": 1,
                    "match_count": 0,
                    "mismatch_count": 1,
                    "dispositioned": {
                        "dispositions_file": artifact_path.relative_to(REPO).as_posix(),
                        "counts": {"upstream_engine_gap": 1},
                        "unexplained_count": 0,
                    },
                },
            },
        )

        leg, _evidence, defects = _verdict(report_name)

        assert leg["clean"] is False
        assert any(
            "not a readable dispositions document" in defect for defect in defects
        ), defects
        assert leg["unexplained"] == 1
    finally:
        report_path.unlink(missing_ok=True)
        artifact_path.unlink(missing_ok=True)


def test_weighted_mass_must_be_finite_and_nonnegative():
    for weight, marker in ((float("nan"), "finite"), (-5.0, "negative")):
        name = f"zz-r3-w{marker}.json"
        _mutant(
            name,
            {
                "suite": "victim",
                "cases": [{"metadata": {"x": 1}}],
                "summary": {
                    "comparison_count": 1,
                    "match_count": 1,
                    "mismatch_count": 0,
                    "weighted": {"mismatch_weight": weight},
                },
            },
        )
        try:
            leg, _e, defects = _verdict(name)
            assert leg["clean"] is False, marker
            assert any(marker in d for d in defects), (marker, defects)
        finally:
            (REPO / "dashboard/public/data" / name).unlink()


def test_certified_cannot_activate_by_flipping_status_alone():
    """status: computed with an attested emitted mode reproduced state=yes."""
    import copy

    certify = _load("certify")
    spec = copy.deepcopy(certify.PROGRAMS["us-co/snap"])
    spec["attested"]["closed"].update(status="computed", value=True)
    spec["attested"]["executable"].update(status="computed", value=True)
    cert = certify.build_certificate("us-co/snap", spec)
    # Mode must follow the same determination — they can no longer disagree.
    assert cert["verdicts"]["closed"]["mode"] == "computed"
    # And with exercised still false, the verdict is a plain no.
    assert cert["certified"]["state"] == "no"

    spec2 = copy.deepcopy(spec)
    spec2["attested"]["executable"]["value"] = False
    assert certify.build_certificate("us-co/snap", spec2)["certified"]["state"] == "no"


@pytest.mark.parametrize("premise", ("closed", "executable"))
@pytest.mark.parametrize(
    ("status", "registry_mode", "derived_mode"),
    (
        pytest.param("prototype", "computed", "attested", id="attested-wins"),
        pytest.param("computed", "attested", "computed", id="computed-wins"),
    ),
)
def test_registry_mode_cannot_override_derived_emitted_mode(
    premise,
    status,
    registry_mode,
    derived_mode,
):
    import copy

    certify = _load("certify")
    spec = copy.deepcopy(certify.PROGRAMS["us-co/snap"])
    spec["attested"][premise].update(
        status=status,
        mode=registry_mode,
    )

    certificate = certify.build_certificate("us-co/snap", spec)

    assert certificate["verdicts"][premise]["mode"] == derived_mode


def test_covered_by_rejects_ghosts_and_absolute_paths():
    vbm = _load("validate_bridge_manifests")
    assert vbm._covered_by_resolves("ghost-sibling/no-such/evidence.yaml") is False
    assert vbm._covered_by_resolves("/etc/passwd") is False
    assert vbm._covered_by_resolves("../../../etc/passwd") is False


def test_contested_reports_are_a_certificate_defect():
    """A durable synthetic contest blocks regardless of live NYC cleanup."""
    certify = _load("certify")
    census = json.loads(
        (EVIDENCE_FIXTURES / "contested_reports" / "census.json").read_text()
    )
    defects: list[str] = []
    _rows, complete = certify._exercise_block(
        [
            {
                "suite": "synthetic-contested",
                "oracle_type": "reference",
                "oracle": "x",
                "report": "tests/fixtures/evidence/contested_reports/report-b.json",
            }
        ],
        census,
        defects,
    )
    assert complete is False
    assert any("claim this suite" in d for d in defects)


# ── #378: strict execution-evidence boundary ─────────────────────────────────


def _evidence_fixture(name: str):
    return validate_suite_evidence(
        EVIDENCE_FIXTURES / name / "dashboard" / "public" / "data" / "report.json"
    )


def _certification_fixture(name: str, oracle_type: str = "reference"):
    certify = _load("certify")
    report_path = (
        EVIDENCE_FIXTURES / name / "dashboard" / "public" / "data" / "report.json"
    )
    report = json.loads(report_path.read_text())
    return certify._suite_verdict(
        {
            "suite": report["suite"],
            "oracle_type": oracle_type,
            "oracle": "synthetic",
            "report": report_path.relative_to(REPO).as_posix(),
        }
    )


def _copied_evidence_fixture(tmp_path: Path, name: str = "full_bound"):
    fixture = tmp_path / name.replace("_", "-")
    shutil.copytree(EVIDENCE_FIXTURES / name, fixture)
    report_path = fixture / "dashboard" / "public" / "data" / "report.json"
    report = json.loads(report_path.read_text())
    suite_dir = fixture / "dashboard" / "public" / "data" / "cases" / report["suite"]
    return report_path, suite_dir


def _refresh_fixture_binding(
    report_path: Path,
    suite_dir: Path,
    *,
    refresh_case_verdicts: bool = True,
) -> None:
    """Rebind a synthetic mutant after deliberately changing its content."""

    index_path = suite_dir / "index.json"
    index = json.loads(index_path.read_text())
    index["report_path"], index["report_sha256"] = report_identity(report_path)
    total = 0
    for descriptor in index["chunks"]:
        chunk_path = suite_dir / descriptor["name"]
        payload = json.loads(chunk_path.read_text())
        rows = payload if isinstance(payload, list) else payload["cases"]
        descriptor["sha256"] = sha256_path(chunk_path)
        descriptor["cases"] = len(rows)
        total += len(rows)
    index["count"] = total
    index["chunk_count"] = len(index["chunks"])
    if refresh_case_verdicts:
        evidence = validate_suite_evidence(report_path)
        if evidence.case_verdicts_sha256 is None:
            index.pop("case_verdicts_sha256", None)
        else:
            index["case_verdicts_sha256"] = evidence.case_verdicts_sha256
    index_path.write_text(json.dumps(index, indent=2) + "\n")


def test_full_and_cardinality_reconciliation_are_stated_honestly():
    full = _evidence_fixture("full_bound")
    assert full.valid is True
    assert full.binding == "bound"
    assert full.reconciliation == "full"
    assert (full.comparison_count, full.match_count, full.mismatch_count) == (
        3,
        2,
        1,
    )

    cardinality = _evidence_fixture("cardinality_bound")
    assert cardinality.valid is True
    assert cardinality.binding == "bound"
    assert cardinality.reconciliation == "cardinality"


def test_reference_leg_requires_full_semantic_reconciliation():
    reference, evidence, defects = _certification_fixture("cardinality_bound")
    assert reference["clean"] is False
    assert reference["binding"] == "bound"
    assert reference["reconciliation"] == "cardinality"
    assert reference["evidence_cases"] == 2
    assert any(
        "reference oracle requires full semantic reconciliation" in defect
        for defect in defects
    )
    assert any(
        item["claim"] == "case-evidence-index:cardinality-bound" for item in evidence
    )

    reality, _evidence, reality_defects = _certification_fixture(
        "cardinality_bound", oracle_type="reality"
    )
    assert reality_defects == []
    assert reality["clean"] is True
    assert reality["reconciliation"] == "cardinality"


def test_certificate_leg_requires_bound_reconciled_execution_evidence():
    mutants = {
        "dummy_metadata": ("unbound", "none", "no case id"),
        "foreign_chunks": ("unbound", "full", "report_path"),
        "duplicate_case": ("bound", "full", "duplicate case id"),
        "malformed_row": ("bound", "none", ".m must be an array"),
        "stale_report_sha": ("unbound", "cardinality", "report_sha256"),
    }
    for fixture, (binding, reconciliation, marker) in mutants.items():
        leg, _evidence, fixture_defects = _certification_fixture(fixture)
        assert leg["clean"] is False, fixture
        assert leg["binding"] == binding, fixture
        assert leg["reconciliation"] == reconciliation, fixture
        assert any(marker in defect for defect in fixture_defects), (
            fixture,
            fixture_defects,
        )


def test_same_id_foreign_values_do_not_semantically_bind(tmp_path):
    report_path, suite_dir = _copied_evidence_fixture(tmp_path)
    chunk_path = suite_dir / "chunk-0.json"
    chunk = json.loads(chunk_path.read_text())
    chunk[1]["m"][0].update(l=1000, x=1200, d=200)
    chunk_path.write_text(json.dumps(chunk, separators=(",", ":")))
    _refresh_fixture_binding(report_path, suite_dir)

    evidence = validate_suite_evidence(report_path)
    assert evidence.binding == "bound"
    assert evidence.reconciliation == "full"
    assert evidence.valid is False
    assert any(
        "report mismatch" in defect and "value" in defect
        for defect in evidence.content_defects
    )


def test_matched_amount_values_must_reconcile_with_aggregate_sums(tmp_path):
    """A same-outcome 0→999 substitution must move and violate both sums."""

    report_path, suite_dir = _copied_evidence_fixture(tmp_path)
    chunk_path = suite_dir / "chunk-0.json"
    chunk = json.loads(chunk_path.read_text())
    verdict = next(
        row
        for row in chunk[0]["v"]
        if row["c"] == "benefit"
    )
    verdict.update(l=999, x=999)
    chunk_path.write_text(json.dumps(chunk, separators=(",", ":")))
    _refresh_fixture_binding(report_path, suite_dir)

    evidence = validate_suite_evidence(report_path)
    assert evidence.binding == "bound"
    assert evidence.reconciliation == "full"
    assert evidence.valid is False
    for field in ("left_weighted_sum", "right_weighted_sum"):
        assert any(field in defect for defect in evidence.content_defects)


def test_matched_eligibility_values_must_reconcile_with_positive_weights(
    tmp_path,
):
    report_path, suite_dir = _copied_evidence_fixture(tmp_path)
    chunk_path = suite_dir / "chunk-0.json"
    chunk = json.loads(chunk_path.read_text())
    verdict = next(
        row
        for row in chunk[0]["v"]
        if row["c"] == "eligibility"
    )
    verdict.update(l=True, x=True)
    chunk_path.write_text(json.dumps(chunk, separators=(",", ":")))
    _refresh_fixture_binding(report_path, suite_dir)

    evidence = validate_suite_evidence(report_path)
    assert evidence.binding == "bound"
    assert evidence.reconciliation == "full"
    assert evidence.valid is False
    for field in ("left_positive_weight", "right_positive_weight"):
        assert any(field in defect for defect in evidence.content_defects)


def test_permuted_matched_case_values_must_reconcile_with_case_identity(
    tmp_path,
):
    """The exact live 50666↔50669 permutation must not hide behind equal totals."""

    data_dir = tmp_path / "dashboard" / "public" / "data"
    data_dir.mkdir(parents=True)
    report_path = data_dir / "axiom-policyengine-co-snap-ecps.json"
    shutil.copy2(
        REPO / "dashboard" / "public" / "data" / report_path.name,
        report_path,
    )
    suite_dir = data_dir / "cases" / "co-snap-ecps"
    shutil.copytree(
        REPO / "dashboard" / "public" / "data" / "cases" / "co-snap-ecps",
        suite_dir,
    )

    chunk_path = suite_dir / "chunk-0.json"
    chunk = json.loads(chunk_path.read_text())
    first = next(row for row in chunk if row["id"] == "ecps-spm-50666")
    second = next(row for row in chunk if row["id"] == "ecps-spm-50669")
    for concept in (
        "us:statutes/7/2014/u#snap_benefit",
        "us:statutes/7/2014/o#snap_eligible",
    ):
        first_verdict = next(row for row in first["v"] if row["c"] == concept)
        second_verdict = next(row for row in second["v"] if row["c"] == concept)
        first_verdict["l"], second_verdict["l"] = (
            second_verdict["l"],
            first_verdict["l"],
        )
        first_verdict["x"], second_verdict["x"] = (
            second_verdict["x"],
            first_verdict["x"],
        )
    chunk_path.write_text(json.dumps(chunk, separators=(",", ":")))
    _refresh_fixture_binding(
        report_path,
        suite_dir,
        refresh_case_verdicts=False,
    )

    evidence = validate_suite_evidence(report_path)
    assert evidence.content_valid is True
    assert evidence.reconciliation == "full"
    assert evidence.binding == "unbound"
    assert evidence.valid is False
    assert any(
        "case_verdicts_sha256" in defect
        and "per-case verdict identity" in defect
        for defect in evidence.binding_defects
    )


def test_aggregate_values_require_reproducible_unit_weight(tmp_path):
    report_path, suite_dir = _copied_evidence_fixture(tmp_path)
    report = json.loads(report_path.read_text())
    aggregate = next(
        row
        for row in report["aggregates"]
        if row["concept"] == "benefit"
    )
    del aggregate["comparison_weight"]
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    _refresh_fixture_binding(report_path, suite_dir)

    evidence = validate_suite_evidence(report_path)
    assert evidence.binding == "bound"
    assert evidence.reconciliation == "full"
    assert evidence.valid is False
    assert any(
        "comparison_weight is required" in defect
        for defect in evidence.content_defects
    )


@pytest.mark.parametrize(
    ("mutation", "marker", "detail"),
    [
        pytest.param("d", ".d", "representation tolerance", id="d-drift"),
        pytest.param(
            "r",
            ".r",
            "exact stored verdict match rate endpoint",
            id="r-drift",
        ),
    ],
)
def test_dashboard_semantic_fields_must_match_stored_verdicts(
    tmp_path,
    mutation,
    marker,
    detail,
):
    report_path, suite_dir = _copied_evidence_fixture(tmp_path)
    chunk_path = suite_dir / "chunk-0.json"
    chunk = json.loads(chunk_path.read_text())
    if mutation == "d":
        chunk[1]["m"][0]["d"] = 1_000_000_000
    else:
        chunk[1]["r"] = 100
    chunk_path.write_text(json.dumps(chunk, separators=(",", ":")))
    _refresh_fixture_binding(report_path, suite_dir)

    evidence = validate_suite_evidence(report_path)
    assert evidence.binding == "bound"
    assert evidence.reconciliation == "full"
    assert evidence.valid is False
    assert any(
        marker in defect and detail in defect
        for defect in evidence.content_defects
    )


def test_full_agreement_rate_must_be_exact_at_semantic_boundary(tmp_path):
    report_path, suite_dir = _copied_evidence_fixture(tmp_path)
    chunk_path = suite_dir / "chunk-0.json"
    chunk = json.loads(chunk_path.read_text())
    chunk[0]["r"] = 99.9999995
    chunk_path.write_text(json.dumps(chunk, separators=(",", ":")))
    _refresh_fixture_binding(report_path, suite_dir)

    evidence = validate_suite_evidence(report_path)
    assert evidence.binding == "bound"
    assert evidence.reconciliation == "full"
    assert evidence.valid is False
    assert any(
        ".r 99.9999995 does not equal the exact stored verdict match rate "
        "endpoint 100.0" in defect
        for defect in evidence.content_defects
    )


@pytest.mark.parametrize("rate", [-1, 100.0000005, 101])
def test_dashboard_match_rate_is_bounded_even_without_full_verdicts(
    tmp_path,
    rate,
):
    report_path, suite_dir = _copied_evidence_fixture(
        tmp_path,
        "cardinality_bound",
    )
    chunk_path = suite_dir / "chunk-0.json"
    chunk = json.loads(chunk_path.read_text())
    chunk[0]["r"] = rate
    chunk_path.write_text(json.dumps(chunk, separators=(",", ":")))
    _refresh_fixture_binding(report_path, suite_dir)

    evidence = validate_suite_evidence(report_path)
    assert evidence.binding == "bound"
    assert evidence.reconciliation == "cardinality"
    assert evidence.valid is False
    assert any(
        ".r must be between 0 and 100" in defect
        for defect in evidence.content_defects
    )


def test_partial_mismatch_row_cannot_claim_full_agreement(tmp_path):
    report_path, suite_dir = _copied_evidence_fixture(tmp_path)
    chunk_path = suite_dir / "chunk-0.json"
    chunk = json.loads(chunk_path.read_text())
    del chunk[1]["v"]
    chunk[1]["r"] = 100
    chunk_path.write_text(json.dumps(chunk, separators=(",", ":")))
    _refresh_fixture_binding(report_path, suite_dir)

    evidence = validate_suite_evidence(report_path)
    assert evidence.binding == "bound"
    assert evidence.valid is False
    assert any(
        ".r cannot claim 100 percent agreement" in defect
        for defect in evidence.content_defects
    )


@pytest.mark.parametrize(
    ("report_kind", "chunk_kind"),
    [
        pytest.param("explained_residual", None, id="report-only"),
        pytest.param(None, "explained_residual", id="chunk-only"),
        pytest.param(
            "upstream_engine_gap",
            "explained_residual",
            id="different-kind",
        ),
    ],
)
def test_report_and_chunk_disposition_markers_must_agree(
    tmp_path, report_kind, chunk_kind
):
    report_path, suite_dir = _copied_evidence_fixture(tmp_path)
    report = json.loads(report_path.read_text())
    mismatch = report["mismatches"][0]
    if report_kind is not None:
        mismatch["disposition"] = {
            "id": "synthetic-disposition",
            "disposition": report_kind,
        }
        report["summary"]["dispositioned"] = {
            "counts": {report_kind: 1},
            "unexplained_count": 0,
        }
    report_path.write_text(json.dumps(report, indent=2) + "\n")

    chunk_path = suite_dir / "chunk-0.json"
    chunk = json.loads(chunk_path.read_text())
    compact_mismatch = chunk[1]["m"][0]
    if chunk_kind is not None:
        compact_mismatch["e"] = chunk_kind
    chunk_path.write_text(json.dumps(chunk, separators=(",", ":")))
    _refresh_fixture_binding(report_path, suite_dir)

    evidence = validate_suite_evidence(report_path)
    assert evidence.binding == "bound"
    assert evidence.reconciliation == "full"
    assert evidence.valid is False
    assert any(
        "disposition" in defect and "does not match" in defect
        for defect in evidence.content_defects
    )


@pytest.mark.parametrize(
    ("mutation", "marker"),
    [
        pytest.param("duplicate-match", "repeats concept", id="duplicate-match"),
        pytest.param(
            "duplicate-mismatch",
            "repeats concept",
            id="duplicate-mismatch",
        ),
        pytest.param(
            "match-mismatch-overlap",
            "appears in both",
            id="match-mismatch-overlap",
        ),
    ],
)
def test_duplicate_and_overlapping_case_concepts_are_rejected(
    tmp_path, mutation, marker
):
    report_path, suite_dir = _copied_evidence_fixture(tmp_path)
    chunk_path = suite_dir / "chunk-0.json"
    chunk = json.loads(chunk_path.read_text())
    if mutation == "duplicate-match":
        chunk[0]["v"].append(copy.deepcopy(chunk[0]["v"][0]))
    elif mutation == "duplicate-mismatch":
        chunk[1]["m"].append(copy.deepcopy(chunk[1]["m"][0]))
    else:
        chunk[1]["v"].append(copy.deepcopy(chunk[1]["m"][0]))
    chunk_path.write_text(json.dumps(chunk, separators=(",", ":")))
    _refresh_fixture_binding(report_path, suite_dir)

    evidence = validate_suite_evidence(report_path)
    assert evidence.binding == "bound"
    assert evidence.valid is False
    assert evidence.reconciliation != "cardinality"
    assert any(marker in defect for defect in evidence.content_defects)


def test_later_malformed_chunk_is_not_hidden_by_an_earlier_valid_chunk(
    tmp_path,
):
    report_path, suite_dir = _copied_evidence_fixture(tmp_path)
    _refresh_fixture_binding(report_path, suite_dir)
    malformed_path = suite_dir / "chunk-1.json"
    malformed_path.write_text("{not-json")

    index_path = suite_dir / "index.json"
    index = json.loads(index_path.read_text())
    index["chunk_count"] = 2
    index["chunks"].append(
        {
            "name": malformed_path.name,
            "sha256": sha256_path(malformed_path),
            "cases": 0,
        }
    )
    index_path.write_text(json.dumps(index, indent=2) + "\n")

    evidence = validate_suite_evidence(report_path)
    assert evidence.binding == "bound"
    assert evidence.valid is False
    assert any(
        "chunk-1.json is not valid JSON" in defect
        for defect in evidence.content_defects
    )


def test_qc_mismatch_signal_survives_compaction():
    """A future QC mismatch must not become an empty agreeing compact row."""

    from scripts.emit_case_artifacts import compact_case

    compact = compact_case(
        {
            "case_id": "qc-mismatch",
            "matched": False,
            "stage": "benefit",
        },
        {},
    )

    assert compact["m"] == [{"c": "benefit", "l": None, "x": None, "d": None}]
    assert "v" not in compact


def test_skipped_inline_v1_corpus_is_preserved(monkeypatch, tmp_path):
    """A skipped inline-only v1 report cannot be rebound without execution."""

    run_comparison = _load("run_comparison")
    monkeypatch.setattr(run_comparison, "DASHBOARD_DATA_DIR", tmp_path)
    suite = "inline-v1"
    report_path = tmp_path / "report.json"
    suite_dir = tmp_path / "cases" / suite
    suite_dir.mkdir(parents=True)
    index_path = suite_dir / "index.json"
    report = {
        "schema_version": "axiom.comparison_report.v2",
        "suite": suite,
        "case_count": 1,
        "concepts": [
            {
                "id": "benefit",
                "comparison": "amount",
                "tolerance": 0,
                "relative_tolerance": 0,
            }
        ],
        "aggregates": [
            {
                "concept": "benefit",
                "comparison_count": 1,
                "match_count": 1,
                "mismatch_count": 0,
            }
        ],
        "mismatches": [],
        "summary": {
            "comparison_count": 1,
            "match_count": 1,
            "mismatch_count": 0,
        },
        "cases": [
            {
                "case_id": "inline-1",
                "matches": [{"concept": "benefit", "left": 1, "right": 1}],
                "mismatches": [],
            }
        ],
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    index_path.write_text(json.dumps(build_chunk_index(report_path), indent=2) + "\n")
    before = (report_path.read_bytes(), index_path.read_bytes())
    assert validate_suite_evidence(report_path).valid is True

    skipped_copy = copy.deepcopy(report)
    skipped_copy["provenance"] = {"generated_at": "future skip"}
    run_comparison._write_dashboard_report(
        skipped_copy,
        report_path.name,
        preserve_existing_versioned=True,
    )

    assert (report_path.read_bytes(), index_path.read_bytes()) == before
    assert validate_suite_evidence(report_path).valid is True


def test_dummy_metadata_cannot_back_asserted_counts():
    evidence = _evidence_fixture("dummy_metadata")
    assert evidence.valid is False
    assert evidence.reconciliation == "none"
    assert any("no case id" in defect for defect in evidence.defects)
    assert any("do not support" in defect for defect in evidence.defects)


def test_uncontested_report_cannot_inherit_foreign_chunks():
    evidence = _evidence_fixture("foreign_chunks")
    assert evidence.content_valid is True
    assert evidence.binding == "unbound"
    assert any("report_path" in defect for defect in evidence.binding_defects)
    assert any("report_sha256" in defect for defect in evidence.binding_defects)


def test_duplicate_case_id_is_a_defect_even_with_a_valid_index():
    evidence = _evidence_fixture("duplicate_case")
    assert evidence.binding == "bound"
    assert evidence.valid is False
    assert any("duplicate case id" in defect for defect in evidence.defects)


def test_malformed_chunk_row_is_a_defect():
    evidence = _evidence_fixture("malformed_row")
    assert evidence.binding == "bound"
    assert evidence.reconciliation == "none"
    assert any(".m must be an array" in defect for defect in evidence.defects)


def test_partial_verdict_cannot_fall_back_to_cardinality():
    evidence = _evidence_fixture("partial_verdict")
    assert evidence.binding == "bound"
    assert evidence.reconciliation == "none"
    assert any("do not support" in defect for defect in evidence.defects)


def test_nonstandard_nonfinite_json_is_malformed_evidence():
    evidence = _evidence_fixture("nonfinite_row")
    assert evidence.binding == "bound"
    assert evidence.reconciliation == "none"
    assert any(
        "not valid JSON" in defect and "NaN" in defect
        for defect in evidence.content_defects
    )


def test_compact_concept_and_input_names_must_be_strings(tmp_path):
    fixture = tmp_path / "invalid-nested-name"
    shutil.copytree(EVIDENCE_FIXTURES / "full_bound", fixture)
    report_path = fixture / "dashboard" / "public" / "data" / "report.json"
    suite_dir = fixture / "dashboard" / "public" / "data" / "cases" / "full-bound"
    chunk_path = suite_dir / "chunk-0.json"
    chunk = json.loads(chunk_path.read_text())
    chunk[0]["v"][0]["c"] = []
    chunk_path.write_text(json.dumps(chunk, separators=(",", ":")))
    _refresh_fixture_binding(report_path, suite_dir)

    evidence = validate_suite_evidence(report_path)
    assert evidence.binding == "bound"
    assert evidence.valid is False
    assert any(
        ".c must be a non-empty string" in defect for defect in evidence.content_defects
    )


def test_json_parser_rejects_constants_and_overflowed_floats():
    for raw in ('{"value": NaN}', '{"value": 1e999}'):
        with pytest.raises(ValueError):
            strict_json_loads(raw)


def test_index_report_sha_must_match_exact_report_bytes():
    evidence = _evidence_fixture("stale_report_sha")
    assert evidence.content_valid is True
    assert evidence.binding == "unbound"
    assert any(
        "report_sha256" in defect and "does not match" in defect
        for defect in evidence.binding_defects
    )


def test_generator_refuses_to_rebind_changed_versioned_evidence(tmp_path):
    fixture = tmp_path / "cardinality-bound"
    shutil.copytree(EVIDENCE_FIXTURES / "cardinality_bound", fixture)
    report_path = fixture / "dashboard" / "public" / "data" / "report.json"
    index_path = (
        fixture
        / "dashboard"
        / "public"
        / "data"
        / "cases"
        / "cardinality-bound"
        / "index.json"
    )
    index_path.write_text(json.dumps(build_chunk_index(report_path), indent=2) + "\n")
    assert validate_suite_evidence(report_path).valid is True

    report = json.loads(report_path.read_text())
    report["provenance"] = {"mutant": "new report, old chunks"}
    report_path.write_text(json.dumps(report, indent=2) + "\n")

    generator = _load("generate_chunk_indexes")
    with pytest.raises(ValueError, match="refusing to rebind"):
        generator.generate(report_path, check=False, strip_inline=False)


def test_census_report_path_and_sha_must_match_the_registry():
    certify = _load("certify")
    report_path = (
        EVIDENCE_FIXTURES
        / "cardinality_bound"
        / "dashboard"
        / "public"
        / "data"
        / "report.json"
    )
    report = report_path.relative_to(REPO).as_posix()
    report_sha256 = certify.sha256_of(report_path)
    entry = {
        "suite": "cardinality-bound",
        "oracle_type": "reference",
        "oracle": "synthetic",
        "report": report,
    }
    row = {
        "cases_scanned": 2,
        "report": report,
        "report_sha256": report_sha256,
        "contested_reports": [],
        "evidence_fields": {"income": {"distinct": 2, "state": "varied"}},
        "varied_fields": 1,
        "constant_fields": 0,
        "bridged_through": {},
        "bridge_audited": True,
        "binding": "bound",
        "reconciliation": "cardinality",
    }

    rows, complete = certify._exercise_block(
        [entry], {"suites": {"cardinality-bound": row}}, []
    )
    assert complete is True
    assert rows["cardinality-bound"]["report_identity_matches_registry"] is True

    for field, value, marker in (
        (
            "report",
            "tests/fixtures/evidence/full_bound/dashboard/public/data/report.json",
            "census report path",
        ),
        ("report_sha256", "0" * 64, "census report_sha256"),
    ):
        mutant_row = {**row, field: value}
        defects: list[str] = []
        mutant_rows, mutant_complete = certify._exercise_block(
            [entry],
            {"suites": {"cardinality-bound": mutant_row}},
            defects,
        )
        assert mutant_complete is False, field
        assert (
            mutant_rows["cardinality-bound"]["report_identity_matches_registry"]
            is False
        )
        assert any(marker in defect for defect in defects), (field, defects)
