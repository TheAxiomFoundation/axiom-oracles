"""Mutants the certification checks must kill (2026-07-26 audit, finding 16 lite).

Each test constructs an input the corresponding gate exists to reject and
asserts rejection. A check that has never been seen to fail is unproven; these
are the demonstrations, kept green forever. Grow this catalogue whenever a gate
gains a rule — a rule without a mutant here is not yet a rule.
"""

import copy
import importlib.util
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

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
            "period": "2025",
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
            "period": "2025",
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


def test_dk_opt_in_closure_gate_requires_full_source_verification(monkeypatch):
    """The opt-in integration gate rejects a failed full source re-derivation."""

    certify = _load("certify")
    producer = certify._producer_module("scripts/closure_ledger.py")
    calls = []

    def rejected_full_check(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            valid=False,
            errors=("coordinated provision-spine truncation",),
            document=None,
        )

    monkeypatch.setattr(producer, "verify_artifact", rejected_full_check)
    with pytest.raises(ValueError, match="failed full closure verification"):
        certify._closed_verdict(
            "dk/boerne-og-ungeydelse",
            certify.PROGRAMS["dk/boerne-og-ungeydelse"],
            [],
            verify_producer=True,
        )
    assert len(calls) == 1


def test_dk_opt_in_executable_gate_requires_full_reproduction(monkeypatch):
    """The opt-in integration gate rejects a well-shaped forged compiled hash."""

    certify = _load("certify")
    producer = certify._producer_module("scripts/executable_reproduction.py")
    artifact = json.loads(
        (REPO / "conformance/executable/dk-boerne-og-ungeydelse.json").read_text()
    )
    reproduced = copy.deepcopy(artifact)
    reproduced["compiled_artifacts"][0]["sha256"] = "0" * 64
    calls = []

    def forged_reproduction(**kwargs):
        calls.append(kwargs)
        return reproduced

    monkeypatch.setattr(producer, "build_reproduction", forged_reproduction)
    with pytest.raises(ValueError, match="compiled/replayed artifact drifted"):
        certify._executable_verdict(
            program="dk/boerne-og-ungeydelse",
            spec=certify.PROGRAMS["dk/boerne-og-ungeydelse"],
            legs=[],
            evidence=[],
            verify_producer=True,
        )
    assert len(calls) == 1
    assert calls[0]["rulespec_ref"] == artifact["rulespec"]["sha"]

def test_nz_two_endpoint_gate_misses_conditional_default_person_dependency():
    """S1 negative test: preserve proof that the supporting gate is insufficient."""
    nz = _load("nz_incomeexplorer")
    source = json.loads(nz.SOURCE_PATH.read_text())

    def conditional_default_person_calculator(wage, scenario):
        value = nz._acc_cell(wage, scenario)
        inputs = scenario["inputs"]
        if inputs.get("partnered") and inputs.get("gross_wage2") == 0:
            value += nz.Decimal("1")
        return value

    # Both selected endpoints leave the dependency dormant, so the gate passes.
    result = nz.assert_single_person_invariant(
        source,
        "nz/acc-earners-levy",
        calculator=conditional_default_person_calculator,
    )
    assert result["status"] == "pass"

    # An unsampled person 2 present at the default wage activates it.
    baseline = next(
        row for row in source["scenarios"]
        if row["id"] == nz.ATTESTATION_BASELINE_SCENARIO
    )
    unsampled = copy.deepcopy(baseline)
    unsampled["inputs"]["partnered"] = True
    unsampled["inputs"]["gross_wage2"] = 0
    wage = baseline["sampled_weekly_wages"][0]
    assert conditional_default_person_calculator(
        wage, unsampled
    ) == conditional_default_person_calculator(wage, baseline) + nz.Decimal("1")


def test_nz_unified_exercise_receipt_does_not_self_audit_a_bridge():
    census = _load("exercise_census")
    report_path = REPO / "dashboard/public/data/nz-treasury-incomeexplorer.json"
    report = json.loads(report_path.read_text())
    row = census._census_suite("nz-treasury-incomeexplorer", report, report_path)
    assert "bridge_declared" not in row
    assert "bridge_audited" not in row
    assert row["evidence_source"] == "unified-experiment-receipt"


def test_nz_attested_premises_cannot_certify():
    certify = _load("certify")
    for program in sorted(name for name in certify.PROGRAMS if name.startswith("nz/")):
        certificate = certify.build_certificate(program, certify.PROGRAMS[program])
        assert certificate["certified"]["value"] is False
        assert certificate["certified"]["state"] == "no"
        assert certificate["verdicts"]["exercised"]["mode"] == "attested"
        assert certificate["verdicts"]["closed"]["mode"] == "attested"
        assert certificate["verdicts"]["executable"]["mode"] == "attested"


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
    """Attested status strings cannot replace verified producer artifacts."""
    certify = _load("certify")
    spec = copy.deepcopy(certify.PROGRAMS["dk/boerne-og-ungeydelse"])
    spec.pop("computed")
    spec["attested"] = {
        "closed": {"status": "computed", "value": True},
        "executable": {"status": "computed", "value": True},
    }

    cert = certify.build_certificate("dk/boerne-og-ungeydelse", spec)

    assert cert["verdicts"]["conformant"]["mode"] == "computed"
    assert cert["verdicts"]["conformant"]["value"] is True
    assert cert["verdicts"]["exercised"]["mode"] == "computed"
    assert cert["verdicts"]["exercised"]["value"] is True
    assert cert["verdicts"]["closed"]["mode"] == "attested"
    assert cert["verdicts"]["closed"]["value"] is True
    assert cert["verdicts"]["executable"]["mode"] == "attested"
    assert cert["verdicts"]["executable"]["value"] is True
    assert cert["blockers"] == []
    assert cert["certified"]["value"] is False
    assert cert["certified"]["state"] == "unavailable"


@pytest.mark.parametrize("premise", ("closed", "executable"))
@pytest.mark.parametrize(
    ("status", "registry_mode", "derived_mode"),
    (
        pytest.param("prototype", "computed", "attested", id="attested-wins"),
        # `status: computed` is a registry STRING like `mode:`; with no
        # producer behind the premise the derived mode is attested regardless
        # (the DK launch audit minted certified=yes through this exact flip).
        pytest.param("computed", "attested", "attested", id="status-string-loses"),
        pytest.param("computed", "computed", "attested", id="both-strings-lose"),
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
    assert vbm._covered_by_resolves(".") is False
    assert vbm._covered_by_resolves("dashboard/public/data") is False


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


def test_dk_manifest_dropped_suite_input_is_rejected():
    """Suite-backed completeness must kill a manifest/input drift mutant."""
    vbm = _load("validate_bridge_manifests")
    path = REPO / "axiom_oracles/bridges/manifests/dk-child-youth-benefit.yaml"
    manifest = yaml.safe_load(path.read_text())
    target = (
        "dk:statutes/lbk-603-2025/boerne-og-ungeydelsesloven/"
        "paragraf-1-a#input.total_contributions_to_qualifying_pension_accounts"
    )
    manifest["bindings"] = [
        binding for binding in manifest["bindings"] if binding.get("input") != target
    ]

    errors, _findings = vbm.validate(path, manifest)

    assert any(
        "bindings omit suite input(s)" in error and target in error for error in errors
    )


def test_dk_manifest_varying_input_cannot_be_declared_constant():
    """The 0/60000 pension witness proves the contribution input is mapped."""
    vbm = _load("validate_bridge_manifests")
    path = REPO / "axiom_oracles/bridges/manifests/dk-child-youth-benefit.yaml"
    manifest = copy.deepcopy(yaml.safe_load(path.read_text()))
    target = (
        "dk:statutes/lbk-603-2025/boerne-og-ungeydelsesloven/"
        "paragraf-1-a#input.total_contributions_to_qualifying_pension_accounts"
    )
    [binding] = [
        candidate
        for candidate in manifest["bindings"]
        if candidate.get("input") == target
    ]
    binding["kind"] = "constant"
    binding["reason"] = "mutant"

    errors, _findings = vbm.validate(path, manifest)

    assert any(
        "suite-varying input(s) cannot be kind=constant" in error and target in error
        for error in errors
    )


def test_dk_manifest_bridge_target_cannot_change_binding_kind():
    """The suite's tintbto target declarations make the bridged kind computed."""
    vbm = _load("validate_bridge_manifests")
    path = REPO / "axiom_oracles/bridges/manifests/dk-child-youth-benefit.yaml"
    manifest = copy.deepcopy(yaml.safe_load(path.read_text()))
    [binding] = [
        candidate
        for candidate in manifest["bindings"]
        if candidate.get("dimension") == "personskatteloven_section_7_income_basis"
    ]
    binding["kind"] = "constant"
    binding["reason"] = "mutant"

    errors, _findings = vbm.validate(path, manifest)

    assert any(
        "suite bridge target(s) must be kind=bridged" in error for error in errors
    )


def test_dk_manifest_bridge_source_cannot_drift_from_tintbto():
    """The suite names tintbto_s, so another bridge source cannot certify."""
    vbm = _load("validate_bridge_manifests")
    path = REPO / "axiom_oracles/bridges/manifests/dk-child-youth-benefit.yaml"
    manifest = copy.deepcopy(yaml.safe_load(path.read_text()))
    [binding] = [
        candidate
        for candidate in manifest["bindings"]
        if candidate.get("dimension") == "personskatteloven_section_7_income_basis"
    ]
    binding["source"] = "euromod:garbage"

    errors, _findings = vbm.validate(path, manifest)

    assert any("suite bridge target source mismatch" in error for error in errors)


def test_dk_manifest_rejects_multi_source_suite_target(monkeypatch):
    """One manifest source cannot hide a second source introduced by suite drift."""
    vbm = _load("validate_bridge_manifests")
    path = REPO / "axiom_oracles/bridges/manifests/dk-child-youth-benefit.yaml"
    manifest = yaml.safe_load(path.read_text())
    original_catalog = vbm._suite_input_catalog
    target = (
        "dk:statutes/lbk-603-2025/boerne-og-ungeydelsesloven/"
        "paragraf-1-a#input.personskatteloven_section_7_income_basis"
    )

    def multi_source_catalog(suite):
        catalog = original_catalog(suite)
        catalog[2][target].add("euromod:second_source")
        return catalog

    monkeypatch.setattr(vbm, "_suite_input_catalog", multi_source_catalog)
    errors, _findings = vbm.validate(path, manifest)

    assert any("suite bridge target source mismatch" in error for error in errors)


def test_dk_synthetic_population_declaration_cannot_be_dropped():
    """The committed synthetic report must force an honest population family."""
    vbm = _load("validate_bridge_manifests")
    path = REPO / "axiom_oracles/bridges/manifests/dk-child-youth-benefit.yaml"
    manifest = copy.deepcopy(yaml.safe_load(path.read_text()))
    manifest["population"] = {"pin_required": False}

    errors, _findings = vbm.validate(path, manifest)

    assert any("requires family=synthetic" in error for error in errors)
    assert any("must declare case_source=suite" in error for error in errors)


def test_strict_cli_cannot_be_disarmed_by_a_strict_lane_regressing(monkeypatch):
    """MUTANT: a finding on a strict-declared manifest is fatal under --strict
    even when a non-strict manifest with debt sits beside it — the mixed set
    must still exit nonzero (the strict lane's certificate rests on zero
    findings; debt elsewhere neither masks nor excuses it)."""
    vbm = _load("validate_bridge_manifests")
    strict_path = REPO / "strict.yaml"
    legacy_path = REPO / "legacy.yaml"
    manifests = {
        strict_path: {"strict": True},
        legacy_path: {"strict": False},
    }
    monkeypatch.setattr(vbm, "load_manifests", lambda: manifests)
    monkeypatch.setattr(vbm, "global_collisions", lambda _manifests: [])
    monkeypatch.setattr(
        vbm,
        "validate",
        lambda path, _manifest: ([], [f"{path.name}: mutant finding"]),
    )
    monkeypatch.setattr(
        vbm.sys,
        "argv",
        ["validate_bridge_manifests.py", "--strict"],
    )

    assert vbm.main() == 1


def test_strict_cli_treats_non_strict_findings_as_visible_debt(monkeypatch, capsys):
    """Only-debt sets (no strict-declared manifest has a finding) exit 0 under
    --strict, and the debt is printed — never silently swallowed."""
    vbm = _load("validate_bridge_manifests")
    legacy_path = REPO / "legacy.yaml"
    monkeypatch.setattr(vbm, "load_manifests", lambda: {legacy_path: {"strict": False}})
    monkeypatch.setattr(vbm, "global_collisions", lambda _manifests: [])
    monkeypatch.setattr(
        vbm,
        "validate",
        lambda path, _manifest: ([], [f"{path.name}: debt finding"]),
    )
    monkeypatch.setattr(vbm.sys, "argv", ["validate_bridge_manifests.py", "--strict"])

    assert vbm.main() == 0
    assert "legacy.yaml: debt finding" in capsys.readouterr().out


def test_bridge_manifest_identity_fields_are_typed():
    """Null identities and mapping aliases must be errors, never clean/crashes."""
    vbm = _load("validate_bridge_manifests")
    path = REPO / "axiom_oracles/bridges/manifests/dk-child-youth-benefit.yaml"
    original = yaml.safe_load(path.read_text())
    mutants = (
        ("program", None, "`program` must be a non-empty string"),
        ("oracle", None, "oracle must be a mapping"),
        ("aliases", [{"not": "a string"}], "every alias must be"),
    )

    for field, value, expected in mutants:
        manifest = copy.deepcopy(original)
        manifest[field] = value
        errors, _findings = vbm.validate(path, manifest)
        assert any(expected in error for error in errors)
        # main() asks for collisions before per-manifest validation; malformed
        # aliases therefore must be harmless here too.
        vbm.global_collisions({path: manifest})


def test_dropping_strict_opt_in_drops_bridge_audited():
    """MUTANT (delta-audit finding): a strict-clean lane that removes or
    falsifies its `strict: true` opt-in must LOSE bridge_audited — otherwise
    the lane could silence future --strict enforcement while its census row
    and certificate kept claiming audited/exercised. The opt-in is part of the
    certified claim, so census binds it."""
    census = _load("exercise_census")
    baseline = census._manifest_strict_clean()
    assert baseline.get("dk-child-youth-benifit") is None  # sanity: exact names only
    assert baseline["dk-child-youth-benefit"] is True

    path = REPO / "axiom_oracles/bridges/manifests/dk-child-youth-benefit.yaml"
    original = path.read_text()
    try:
        for mutant_text in (
            original.replace("strict: true", "strict: false"),
            original.replace("strict: true\n", ""),
        ):
            assert mutant_text != original
            path.write_text(mutant_text)
            mutated = census._manifest_strict_clean()
            assert mutated["dk-child-youth-benefit"] is False, (
                "a lane without the strict opt-in must not count as audited"
            )
    finally:
        path.write_text(original)
    assert census._manifest_strict_clean()["dk-child-youth-benefit"] is True


def test_strict_lane_evidence_must_be_shipped_bytes():
    """MUTANT (PR #475 CI regression): the couple manifest cited
    tests/test_package_targets.py as covered_by evidence. The file exists here,
    so the validator resolved it — but the refresh bot's hermetic tree carries
    no tests/, so there the citation was unverifiable, the couple suite lost
    bridge_audited, the census drifted, and the bot's idle path pushed. A
    strict lane's evidence must live under the shipped roots; citing an
    existing unshipped path is now an enforced finding, and the census must
    read identically with and without tests/ present."""
    vbm = _load("validate_bridge_manifests")
    path = REPO / "axiom_oracles/bridges/manifests/dk-child-youth-benefit-couple.yaml"
    manifest = yaml.safe_load(path.read_text())
    assert manifest.get("strict") is True
    errors, findings = vbm.validate(path, manifest)
    assert not errors and not findings, (errors, findings)

    # Any repo file outside the shipped roots — tests/ is the live example.
    unshipped = "tests/test_certification_mutants.py"
    assert (REPO / unshipped).is_file()
    binding = next(b for b in manifest["bindings"] if b.get("kind") == "bridged")
    binding["covered_by"] = list(binding["covered_by"]) + [
        f"{unshipped} — a fixture that only exists in a full checkout"
    ]
    _errors, mutated = vbm.validate(path, manifest)
    assert any(
        "is not a shipped, symlink-free evidence file" in f for f in mutated
    ), mutated

    # Non-strict lanes may still cite such paths (visible debt, not enforced).
    manifest["strict"] = False
    _errors, relaxed = vbm.validate(path, manifest)
    assert not any("is not a shipped, symlink-free evidence file" in f for f in relaxed)


def test_certified_lane_census_is_hermetic_without_tests_dir(tmp_path):
    """The census the refresh bot computes from its shipped tree (no tests/)
    must equal the committed census — otherwise the bot's idle path stops
    being idle (test_no_changes_second_run_is_a_noop). Reproduces the
    STRICT_EVIDENCE_ROOTS tree and asserts bridge_audited for every strict
    dk lane survives it."""
    vbm = _load("validate_bridge_manifests")
    tree = tmp_path / "shipped"
    for root in vbm.STRICT_EVIDENCE_ROOTS:
        src = REPO / root
        if src.is_dir():
            shutil.copytree(
                src, tree / root, ignore=shutil.ignore_patterns("__pycache__")
            )
    shutil.copytree(REPO / "scripts", tree / "scripts",
                    ignore=shutil.ignore_patterns("__pycache__"))
    assert not (tree / "tests").exists()
    spec = importlib.util.spec_from_file_location(
        "census_hermetic", tree / "scripts" / "exercise_census.py"
    )
    census = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(census)
    clean = census._manifest_strict_clean()
    for suite in (
        "dk-child-youth-benefit",
        "dk-child-youth-benefit-2023",
        "dk-child-youth-benefit-couple",
    ):
        assert clean.get(suite) is True, (suite, clean.get(suite))

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
# ── NZ IncomeExplorer: every new certification gate gets a killed mutant ──


def _nz_inputs(module):
    return (
        json.loads(module.SOURCE_PATH.read_text()),
        json.loads(module.SNAPSHOT_PATH.read_text()),
        json.loads(module.CLOSURES_PATH.read_text()),
    )


def test_nz_population_must_remain_treasurys_complete_spine():
    nz = _load("nz_incomeexplorer")
    source, snapshot, closures = _nz_inputs(nz)
    source["scenarios"][0]["sampled_weekly_wages"][0] += 1
    with pytest.raises(nz.NZRecordError, match="Treasury's complete 104-point"):
        nz._validate_inputs(source, snapshot, closures)


def test_nz_expired_disposition_makes_the_certificate_leg_red(tmp_path):
    nz = _load("nz_incomeexplorer")
    certify = _load("certify")
    ratchet = _load("unexplained_ratchet")
    source, snapshot, closures = _nz_inputs(nz)
    report = nz._base_report(source, snapshot, closures)

    from axiom_oracles.comparison.dispositions import (
        apply_dispositions,
        load_dispositions,
    )

    dispositions = load_dispositions(nz.DISPOSITIONS_PATH, repo_root=REPO)
    report["mismatches"][0]["left"] += 1
    report = apply_dispositions(
        report,
        dispositions,
        dispositions_file="dispositions/nz-treasury-incomeexplorer.yaml",
    )
    assert report["summary"]["dispositioned"]["unexplained_count"] == 1
    assert ratchet.count_unexplained(report, []) == 1
    assert ratchet.load_ratchet()["nz-treasury-incomeexplorer"] == 0

    mutant = REPO / "dashboard/public/data/zz-nz-expired-disposition.json"
    mutant.write_text(json.dumps(report))
    try:
        with pytest.raises(ValueError, match="does not rederive"):
            certify._suite_verdict(
                {
                    "suite": "nz-treasury-incomeexplorer",
                    "oracle_type": "reference",
                    "oracle": "mutant",
                    "report": str(mutant.relative_to(REPO)),
                }
            )
    finally:
        mutant.unlink()


def test_nz_program_is_only_a_view_of_the_unified_record():
    certify = _load("certify")
    _leg, _evidence, defects = certify._suite_verdict(
        {
            "suite": "nz-treasury-incomeexplorer",
            "view": "nz/not-a-real-subgraph",
            "oracle_type": "reference",
            "oracle": "mutant",
            "report": "dashboard/public/data/nz-treasury-incomeexplorer.json",
        }
    )
    assert any("no subgraph view" in defect for defect in defects)


def test_nz_exercise_receipt_cannot_fake_variation():
    census = _load("exercise_census")
    report = json.loads(
        (REPO / "dashboard/public/data/nz-treasury-incomeexplorer.json").read_text()
    )
    mutant = copy.deepcopy(report["experiment"])
    name, row = next(iter(mutant["active_inputs"].items()))
    row["state"] = "varied" if row["state"] == "constant" else "constant"
    with pytest.raises(ValueError, match="contradicts its observations"):
        census._unified_experiment_fields("nz-mutant", mutant)


def test_nz_exercise_receipt_is_certificate_scoped():
    """Adding NZ must not invalidate unrelated certificates via a global hash."""

    census = _load("exercise_census")
    certify = _load("certify")
    assert "nz-treasury-incomeexplorer" not in census.build_census()["suites"]

    scoped, evidence = certify._exercise_census_for(
        certify.PROGRAMS["nz/income-tax"]
    )
    assert "nz-treasury-incomeexplorer" in scoped["suites"]
    assert evidence == []

    dk = certify.build_certificate(
        "dk/boerne-og-ungeydelse",
        certify.PROGRAMS["dk/boerne-og-ungeydelse"],
    )
    committed = json.loads(
        (REPO / "certificates/dk-boerne-og-ungeydelse.json").read_text()
    )
    assert dk == committed


def test_nz_closure_resolves_by_exact_citation_path_only():
    closure = _load("nz_closure")
    source = json.loads(closure.SOURCE_PATH.read_text())
    mutant = copy.deepcopy(source)
    row = next(item for item in mutant["rulespec"]["files"] if item["citations"])
    missing = "nz/acts/mutant/section-999"
    row["citations"].append(missing)
    row["citations"].sort()
    summary = closure.build(mutant)
    assert missing in summary["pending_citations"]
    assert summary["closed"] is False


def test_nz_subgraph_root_cannot_be_silently_dropped():
    """MUTANT: deleting one ratified comparison root must fail closure."""

    closure = _load("nz_closure")
    source = json.loads(closure.SOURCE_PATH.read_text())
    mutant = copy.deepcopy(source)
    mutant["program_roots"]["nz/working-for-families"].pop()
    with pytest.raises(closure.ClosureError, match="program root sets drifted"):
        closure.build(mutant)


def test_nz_subgraph_cited_path_cannot_be_silently_dropped():
    """MUTANT: deleting a citation reached from ACC must fail its commitment."""

    closure = _load("nz_closure")
    source = json.loads(closure.SOURCE_PATH.read_text())
    mutant = copy.deepcopy(source)
    root_id = mutant["program_roots"]["nz/acc-earners-levy"][0]
    node = next(
        node
        for row in mutant["rulespec"]["files"]
        for node in row["nodes"]
        if node["id"] == root_id
    )
    node["citations"].pop()
    with pytest.raises(closure.ClosureError, match="cited path was dropped"):
        closure.build(mutant)


def test_unrelated_pending_path_does_not_red_acc_certificate_scope():
    """MUTANT: a pending citation outside ACC must stay jurisdiction-only."""

    closure = _load("nz_closure")
    source = json.loads(closure.SOURCE_PATH.read_text())
    mutant = copy.deepcopy(source)
    row = next(
        item
        for item in mutant["rulespec"]["files"]
        if item["path"] == "nz/statutes/income_tax/credits/individual_credits.yaml"
    )
    node = next(item for item in row["nodes"] if item["citations"])
    missing = "nz/statute/act/public/mutant/section/unrelated"
    node["citations"] = sorted([*node["citations"], missing])
    node["citations_sha256"] = closure._list_sha256(node["citations"])
    row["citations"] = sorted([*row["citations"], missing])
    summary = closure.build(mutant)
    assert missing in summary["pending_citations"]
    assert summary["closed"] is False
    assert summary["programs"]["nz/acc-earners-levy"]["closed"] is True
    assert (
        missing
        not in summary["programs"]["nz/acc-earners-levy"]["pending_citations"]
    )


def test_nz_single_person_attestation_recomputes_acc_cells():
    incomeexplorer = _load("nz_incomeexplorer")
    source = json.loads(incomeexplorer.SOURCE_PATH.read_text())
    row = incomeexplorer.assert_single_person_invariant(
        source, "nz/acc-earners-levy"
    )
    assert row["status"] == "pass"
    assert row["baseline_cells_sha256"] == row["perturbed_cells_sha256"]


def test_wff_cross_person_mutant_fails_single_person_gate():
    """MUTANT: route the perturbation gate through real WfF receipt cells."""

    incomeexplorer = _load("nz_incomeexplorer")
    source = json.loads(incomeexplorer.SOURCE_PATH.read_text())

    def wff_cell(wage, scenario):
        return incomeexplorer._rulespec_receipt_cells(
            source, scenario["id"], "WFF_abated"
        )[wage]

    with pytest.raises(
        incomeexplorer.NZRecordError,
        match="non-primary-person perturbation changed program cells",
    ):
        incomeexplorer.assert_single_person_invariant(
            source, "nz/working-for-families", calculator=wff_cell
        )


def test_nz_closure_denominator_bytes_are_pinned(tmp_path, monkeypatch):
    closure = _load("nz_closure")
    mutant = tmp_path / "source.json"
    mutant.write_text(closure.SOURCE_PATH.read_text() + " ")
    monkeypatch.setattr(closure, "SOURCE_PATH", mutant)
    with pytest.raises(closure.ClosureError, match="review and re-pin"):
        closure.load_source()


def test_nz_certificate_rederives_closure_instead_of_trusting_summary(
    tmp_path, monkeypatch
):
    certify = _load("certify")
    repo = tmp_path / "repo"
    (repo / "closure/nz").mkdir(parents=True)
    summary = json.loads((REPO / "closure/nz/summary.json").read_text())
    summary["closed"] = True
    (repo / "closure/nz/summary.json").write_text(json.dumps(summary))
    # Keep the verifier code and its own source paths rooted in the real tree;
    # only the allegedly-computed summary is redirected to the mutant.
    monkeypatch.setattr(certify, "REPO_ROOT", repo)
    real_spec_from_file_location = importlib.util.spec_from_file_location
    monkeypatch.setattr(
        importlib.util,
        "spec_from_file_location",
        lambda name, path: real_spec_from_file_location(
            name, REPO / "scripts/nz_closure.py"
        ),
    )
    with pytest.raises(ValueError, match="does not rederive"):
        certify._closed_verdict(
            "nz/income-tax", {"computed_closed": "closure/nz/summary.json"}, []
        )


def test_nz_money_atom_ledger_is_a_ceiling_not_a_target():
    closure = _load("nz_closure")
    source = json.loads(closure.SOURCE_PATH.read_text())
    source["pending_ledger"]["document"]["total_allowed"] = 1
    with pytest.raises(closure.ClosureError, match="ceiling rose above zero"):
        closure.build(source)


def test_nz_syntax_only_executable_metadata_has_no_computed_acceptance_path():
    certify = _load("certify")
    with pytest.raises(ValueError, match="without a verifier"):
        certify._executable_verdict(
            program="nz/mutant",
            spec={
                "computed_executable": True,
                "suites": [
                    {
                        "report": (
                            "dashboard/public/data/"
                            "nz-treasury-incomeexplorer.json"
                        )
                    }
                ],
            },
            legs=[{"suite": "nz-mutant"}],
            evidence=[],
        )


def test_strict_lane_evidence_cannot_be_a_suite_name_token():
    """MUTANT (delta-audit #2, item 7): `_covered_by_resolves` accepts any
    KNOWN_SUITES token for ordinary lanes, so replacing a strict binding's
    evidence with the bare suite name kept --strict, the census and the
    certificate green and byte-identical. A strict lane's covered_by entry
    must name an explicit shipped evidence FILE; a suite name is prose."""
    vbm = _load("validate_bridge_manifests")
    path = REPO / "axiom_oracles/bridges/manifests/dk-child-youth-benefit-couple.yaml"
    manifest = yaml.safe_load(path.read_text())
    assert manifest.get("strict") is True
    _errors, findings = vbm.validate(path, manifest)
    assert not findings, findings

    binding = next(b for b in manifest["bindings"] if b.get("kind") == "bridged")
    binding["covered_by"] = ["dk-child-youth-benefit-couple"]
    assert vbm._covered_by_resolves("dk-child-youth-benefit-couple")  # ordinary lanes: fine
    _errors, mutated = vbm.validate(path, manifest)
    assert any("names no explicit repository-relative evidence file" in f for f in mutated), mutated


def test_strict_lane_evidence_rejects_symlinked_roots(tmp_path):
    """MUTANT (delta-audit #2, item 7): containment was a string-prefix check,
    so a `docs/` symlink to a file OUTSIDE the evidence roots passed. Now
    containment resolves the path and refuses any symlink component."""
    vbm = _load("validate_bridge_manifests")
    outside = REPO / "tests" / "fixtures" / "evidence" / "contested_reports" / "census.json"
    assert outside.is_file()
    link_dir = REPO / "docs" / "zz-audit-symlink-mutant"
    assert not link_dir.exists()
    link_dir.symlink_to(REPO / "tests" / "fixtures" / "evidence" / "contested_reports")
    try:
        cited = "docs/zz-audit-symlink-mutant/census.json"
        assert (REPO / cited).is_file()  # lexically under docs/, physically not
        assert vbm._shipped_evidence_file(cited) is False
        shipped, offending = vbm._strict_evidence_tokens(f"{cited} — smuggled evidence")
        assert shipped == [] and offending == [cited]
    finally:
        link_dir.unlink()
    # And the honest citation form is accepted.
    assert vbm._shipped_evidence_file(
        "dashboard/public/data/axiom-euromod-dk-child-youth-benefit-couple.json"
    )


def test_census_binds_strict_manifest_identity():
    """Any byte change to a strict-clean manifest must move its census row
    (bridge_manifest_sha256), so no evidence edit — however the validator
    judges it — can leave census/certificate bytes identical."""
    census = _load("exercise_census")
    path = REPO / "axiom_oracles/bridges/manifests/dk-child-youth-benefit.yaml"
    original = path.read_text()
    before = census._manifest_strict_audit()["dk-child-youth-benefit"]
    assert before["clean"] is True
    assert len(before["manifest_sha256"]) == 64
    try:
        path.write_text(original + "\n# an innocuous trailing comment\n")
        after = census._manifest_strict_audit()["dk-child-youth-benefit"]
    finally:
        path.write_text(original)
    assert after["clean"] is True
    assert after["manifest_sha256"] != before["manifest_sha256"]
    assert census._manifest_strict_audit()["dk-child-youth-benefit"] == before
