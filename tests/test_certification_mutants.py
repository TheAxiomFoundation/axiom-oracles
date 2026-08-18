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


def test_nz_computed_exercise_does_not_promote_attested_other_premises():
    certify = _load("certify")
    for program in sorted(name for name in certify.PROGRAMS if name.startswith("nz/")):
        certificate = certify.build_certificate(program, certify.PROGRAMS[program])
        assert certificate["certified"]["value"] is False
        assert certificate["certified"]["state"] == "no"
        assert certificate["verdicts"]["exercised"]["mode"] == "computed"
        assert certificate["verdicts"]["exercised"]["value"] is True
        assert (
            certificate["verdicts"]["exercised"]["catalog_completeness"]["mode"]
            == "attested"
        )
        assert certificate["verdicts"]["exercised"]["capture_lineage"]["mode"] == (
            "attested"
        )
        assert any(blocker.startswith("exercise denominator:") for blocker in certificate["blockers"])
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


def _nz_trace_inputs(module):
    return (
        json.loads(module.SOURCE_PATH.read_text()),
        json.loads(module.TRACE_PATH.read_text()),
    )


def test_nz_bound_cases_fully_reconcile_every_existing_verdict():
    evidence = validate_suite_evidence(
        REPO / "dashboard/public/data/nz-treasury-incomeexplorer.json"
    )
    assert evidence.valid is True
    assert evidence.binding == "bound"
    assert evidence.reconciliation == "full"
    assert evidence.case_count == 104
    assert (
        evidence.comparison_count,
        evidence.match_count,
        evidence.mismatch_count,
    ) == (1_976, 1_454, 522)
    assert (
        evidence.case_verdicts_sha256
        == "2b7adb537af2627a937e4e61bf026aeee5e9555a2e4f2cdfb8677907f53c1bd5"
    )


def test_nz_missing_matched_verdict_cannot_preserve_headline_counts(tmp_path):
    data_dir = tmp_path / "dashboard/public/data"
    data_dir.mkdir(parents=True)
    report_path = data_dir / "nz-treasury-incomeexplorer.json"
    shutil.copy2(
        REPO / "dashboard/public/data/nz-treasury-incomeexplorer.json",
        report_path,
    )
    suite_dir = data_dir / "cases/nz-treasury-incomeexplorer"
    shutil.copytree(
        REPO / "dashboard/public/data/cases/nz-treasury-incomeexplorer",
        suite_dir,
    )
    chunk_path = suite_dir / "chunk-0.json"
    rows = json.loads(chunk_path.read_text())
    row = next(item for item in rows if item["v"])
    row["v"].pop()
    chunk_path.write_text(json.dumps(rows, separators=(",", ":")))

    evidence = validate_suite_evidence(report_path)
    assert evidence.valid is False
    assert any(
        "summary.match_count 1454 does not match parsed per-case verdicts 1453"
        in defect
        for defect in evidence.content_defects
    )


@pytest.mark.parametrize(
    ("mutation", "marker"),
    [
        ("trace-schema", "wrong schema or suite"),
        ("trace-suite", "wrong schema or suite"),
        ("capture-lineage", "capture lineage"),
        ("source-receipt", "not bound to the source comparison"),
        ("harness-receipt", "harness provenance"),
        ("compiled-receipt", "compiled-program receipt"),
        ("engine-receipt", "engine receipt"),
        ("rulespec-receipt", "RuleSpec receipt"),
        ("trace-period", "trace period"),
        ("missing-source-catalog", "no exercise input catalog"),
        ("malformed-source-catalog-row", "source catalog slot"),
        ("duplicate-source-catalog-name", "canonical names are not unique"),
        ("missing-evaluation", "evaluation count"),
        ("malformed-evaluation", "must be an object"),
        ("reordered-id", "missing, duplicate, or reordered id"),
        ("request-mode", "not explain mode"),
        ("relations", "zero-relation request"),
        ("missing-inputs", "no typed inputs"),
        ("query-count", "exactly one query"),
        ("malformed-query", "query must be an object"),
        ("invalid-outputs", "requested outputs are invalid"),
        ("declared-roots", "requested-output root receipt"),
        ("missing-returned-output", "do not biject requested roots"),
        ("cross-view-root", "cross or escape NZ views"),
        ("wrong-view", "wrong certificate view"),
        ("regrouped-root-set", "unexpected requested-output root set"),
        ("query-period", "query period"),
        ("query-entity", "query entity_id"),
        ("unknown-input", "unknown or duplicate input"),
        ("malformed-input-record", "must be an object"),
        ("input-binding", "entity or interval"),
        ("malformed-input", "not a typed decimal string"),
        ("response-object", "response must be an object"),
        ("response-mode", "response mode receipt"),
        ("response-entity", "response entity_id"),
        ("response-period", "response period"),
        ("output-identity", "lost identity"),
        ("malformed-scalar", "returned scalar"),
        ("malformed-judgment", "returned judgment"),
        ("unknown-output-kind", "unknown kind"),
        ("changed-typed-input", "do not reproduce the supplied-input receipt"),
    ],
)
def test_nz_view_scoped_trace_mutants_are_killed(mutation, marker):
    nz = _load("nz_incomeexplorer")
    source, traces = _nz_trace_inputs(nz)
    mutant = {**traces, "evaluations": list(traces["evaluations"])}

    def evaluation(index=0):
        row = copy.deepcopy(mutant["evaluations"][index])
        mutant["evaluations"][index] = row
        return row

    def bind_mutant_source():
        mutant["capture"] = copy.deepcopy(mutant["capture"])
        mutant["capture"]["source_comparison"]["substance_sha256"] = (
            nz._canonical_sha256(nz._without_provenance(source))
        )

    if mutation == "trace-schema":
        mutant["schema"] = "mutant"
    elif mutation == "trace-suite":
        mutant["suite"] = "mutant"
    elif mutation == "capture-lineage":
        mutant["capture"] = copy.deepcopy(mutant["capture"])
        mutant["capture"]["lineage_mode"] = "computed"
    elif mutation == "source-receipt":
        mutant["capture"] = copy.deepcopy(mutant["capture"])
        mutant["capture"]["source_comparison"]["regenerated_sha256"] = "0" * 64
    elif mutation == "harness-receipt":
        mutant["capture"] = copy.deepcopy(mutant["capture"])
        mutant["capture"]["source_harness"]["sha256"] = "0" * 64
    elif mutation == "compiled-receipt":
        mutant["compiled_program"] = {
            **mutant["compiled_program"],
            "derived_outputs": mutant["compiled_program"]["derived_outputs"] + 1,
        }
    elif mutation == "engine-receipt":
        mutant["engine"] = {**mutant["engine"], "git_sha": "0" * 40}
    elif mutation == "rulespec-receipt":
        mutant["rulespec_commit"] = "0" * 40
    elif mutation == "trace-period":
        mutant["period"] = {**mutant["period"], "end": "2027-04-01"}
    elif mutation == "missing-source-catalog":
        source = {**source, "exercise_input_catalog": {}}
        bind_mutant_source()
    elif mutation == "malformed-source-catalog-row":
        source = copy.deepcopy(source)
        slot = next(iter(source["exercise_input_catalog"]))
        source["exercise_input_catalog"][slot] = None
        bind_mutant_source()
    elif mutation == "duplicate-source-catalog-name":
        source = copy.deepcopy(source)
        rows = iter(source["exercise_input_catalog"].values())
        first = next(rows)["canonical_request_name"]
        next(rows)["canonical_request_name"] = first
        bind_mutant_source()
    elif mutation == "missing-evaluation":
        mutant["evaluations"].pop()
    elif mutation == "malformed-evaluation":
        mutant["evaluations"][0] = None
    elif mutation == "reordered-id":
        evaluation()["evaluation_id"] = "nz-ie-eval-9999"
    elif mutation == "request-mode":
        evaluation()["request"]["mode"] = "values"
    elif mutation == "relations":
        evaluation()["request"]["dataset"]["relations"] = [{}]
    elif mutation == "missing-inputs":
        evaluation()["request"]["dataset"]["inputs"] = []
    elif mutation == "query-count":
        evaluation()["request"]["queries"] = []
    elif mutation == "malformed-query":
        evaluation()["request"]["queries"] = [None]
    elif mutation == "invalid-outputs":
        evaluation()["request"]["queries"][0]["outputs"] = []
    elif mutation == "declared-roots":
        evaluation()["requested_output_roots"] = ["mutant"]
    elif mutation == "changed-typed-input":
        evaluation()["request"]["dataset"]["inputs"][0]["value"]["value"] = (
            "999999999"
        )
    elif mutation == "missing-returned-output":
        row = evaluation()
        root = row["requested_output_roots"][0]
        del row["response"]["outputs"][root]
    elif mutation == "cross-view-root":
        row = evaluation()
        foreign = nz.PROGRAM_VIEWS["nz/income-tax"]["roots"][0]
        template = copy.deepcopy(
            next(iter(row["response"]["outputs"].values()))
        )
        template["id"] = foreign
        row["request"]["queries"][0]["outputs"].append(foreign)
        row["requested_output_roots"].append(foreign)
        row["response"]["outputs"][foreign] = template
    elif mutation == "wrong-view":
        evaluation()["view"] = "nz/income-tax"
    elif mutation == "regrouped-root-set":
        index = next(
            i
            for i, row in enumerate(mutant["evaluations"])
            if row["view"] == "nz/working-for-families"
            and len(row["requested_output_roots"]) == 7
        )
        row = evaluation(index)
        root = row["requested_output_roots"].pop()
        row["request"]["queries"][0]["outputs"].remove(root)
        del row["response"]["outputs"][root]
    elif mutation == "query-period":
        evaluation()["request"]["queries"][0]["period"]["end"] = "2027-04-01"
    elif mutation == "query-entity":
        evaluation()["request"]["queries"][0]["entity_id"] = ""
    elif mutation == "unknown-input":
        evaluation()["request"]["dataset"]["inputs"][0]["name"] = "mutant"
    elif mutation == "malformed-input-record":
        evaluation()["request"]["dataset"]["inputs"][0] = None
    elif mutation == "input-binding":
        evaluation()["request"]["dataset"]["inputs"][0]["entity_id"] = "mutant"
    elif mutation == "malformed-input":
        evaluation()["request"]["dataset"]["inputs"][0]["value"]["value"] = True
    elif mutation == "response-object":
        evaluation()["response"] = None
    elif mutation == "response-mode":
        evaluation()["response"]["metadata"]["actual_mode"] = "values"
    elif mutation == "response-entity":
        evaluation()["response"]["entity_id"] = "mutant"
    elif mutation == "response-period":
        evaluation()["response"]["period"]["end"] = "2027-04-01"
    elif mutation == "output-identity":
        row = evaluation()
        next(iter(row["response"]["outputs"].values()))["id"] = "mutant"
    elif mutation == "malformed-scalar":
        row = evaluation()
        next(iter(row["response"]["outputs"].values()))["value"]["value"] = (
            "not-a-number"
        )
    elif mutation == "malformed-judgment":
        index = next(
            i
            for i, row in enumerate(mutant["evaluations"])
            if any(
                item.get("kind") == "judgment"
                for item in row["response"]["outputs"].values()
            )
        )
        row = evaluation(index)
        item = next(
            item
            for item in row["response"]["outputs"].values()
            if item.get("kind") == "judgment"
        )
        item["outcome"] = "maybe"
    elif mutation == "unknown-output-kind":
        row = evaluation()
        next(iter(row["response"]["outputs"].values()))["kind"] = "mutant"

    with pytest.raises(nz.NZRecordError, match=marker):
        nz._trace_view_receipts(source, mutant, verify_file_hash=False)


def test_nz_exercise_is_derived_separately_for_each_requested_root_set():
    nz = _load("nz_incomeexplorer")
    views = nz.derive_bound_trace_views()

    benefits = views["nz/main-benefits"]["root_set_receipts"]
    assert [(row["evaluation_count"], len(row["evidence_fields"])) for row in benefits] == [
        (150, 11),
        (16, 2),
    ]
    wff = views["nz/working-for-families"]["root_set_receipts"]
    assert [(row["evaluation_count"], len(row["evidence_fields"])) for row in wff] == [
        (41, 40),
        (137, 91),
    ]


def test_nz_every_declared_root_set_must_be_observed(monkeypatch):
    nz = _load("nz_incomeexplorer")
    source, traces = _nz_trace_inputs(nz)
    benefits = nz.REQUESTED_OUTPUT_ROOT_SETS["nz/main-benefits"]
    monkeypatch.setitem(
        nz.REQUESTED_OUTPUT_ROOT_SETS,
        "nz/main-benefits",
        (*benefits, tuple(nz.PROGRAM_VIEWS["nz/main-benefits"]["roots"])),
    )
    with pytest.raises(nz.NZRecordError, match="root sets do not exactly close"):
        nz._trace_view_receipts(source, traces, verify_file_hash=False)


def test_nz_trace_receipt_is_hard_bound_to_exact_bytes(tmp_path, monkeypatch):
    nz = _load("nz_incomeexplorer")
    source, traces = _nz_trace_inputs(nz)
    mutant_path = tmp_path / "evaluation-traces.json"
    mutant_path.write_bytes(nz.TRACE_PATH.read_bytes() + b"\n")
    monkeypatch.setattr(nz, "TRACE_PATH", mutant_path)
    with pytest.raises(nz.NZRecordError, match="trace bytes changed"):
        nz._trace_view_receipts(source, traces)


@pytest.mark.parametrize(
    ("mutation", "marker"),
    [
        ("raw-schema", "raw NZ trace capture has the wrong schema"),
        ("comparison-substance", "changed comparison substance"),
        ("comparison-bytes", "comparison bytes changed"),
        ("missing-evaluations", "raw NZ trace capture has no evaluations"),
        ("missing-outputs", "has no outputs"),
        ("cross-view-outputs", "crosses views"),
    ],
)
def test_nz_trace_normalizer_mutants_are_killed(mutation, marker, monkeypatch):
    nz = _load("nz_incomeexplorer")
    source, traces = _nz_trace_inputs(nz)
    capture = {**traces, "schema": nz.RAW_TRACE_SCHEMA}
    regenerated = copy.deepcopy(source)

    if mutation == "raw-schema":
        capture["schema"] = "mutant"
    elif mutation == "comparison-substance":
        regenerated["_mutant"] = True
    elif mutation == "comparison-bytes":
        regenerated.setdefault("provenance", {})["mutant"] = True
    else:
        monkeypatch.setattr(
            nz,
            "REGENERATED_SOURCE_SHA256",
            nz._canonical_file_sha(regenerated),
        )
        if mutation == "missing-evaluations":
            capture["evaluations"] = None
        elif mutation == "missing-outputs":
            capture["evaluations"] = [{"request": {"queries": [{}]}}]
        else:
            capture["evaluations"] = [
                {
                    "request": {
                        "queries": [
                            {
                                "outputs": [
                                    nz.PROGRAM_VIEWS["nz/income-tax"]["roots"][0],
                                    nz.PROGRAM_VIEWS["nz/acc-earners-levy"]["roots"][
                                        0
                                    ],
                                ]
                            }
                        ]
                    }
                }
            ]

    with pytest.raises(nz.NZRecordError, match=marker):
        nz.build_trace_document(capture, regenerated)


def test_nz_attested_catalog_denominator_cannot_contradict_its_receipt(monkeypatch):
    certify = _load("certify")
    source_path = (
        REPO / "comparisons/nz-treasury-incomeexplorer/source-comparison.json"
    )
    mutant = json.loads(source_path.read_text())
    mutant["compiled_program"]["input_slots"] += 1
    original_load = certify._load

    def load_with_mutant(path):
        return mutant if path == source_path else original_load(path)

    monkeypatch.setattr(certify, "_load", load_with_mutant)
    with pytest.raises(ValueError, match="attested denominator"):
        certify._attested_exercise_catalog(
            certify.PROGRAMS["nz/income-tax"],
            [],
        )


def test_nz_attested_catalog_receipt_must_have_catalog_and_compiled_shape(monkeypatch):
    certify = _load("certify")
    monkeypatch.setattr(
        certify,
        "_load",
        lambda _path: {"exercise_input_catalog": [], "compiled_program": {}},
    )
    with pytest.raises(ValueError, match="completeness receipt is malformed"):
        certify._attested_exercise_catalog(
            certify.PROGRAMS["nz/income-tax"],
            [],
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
    view = "nz/income-tax"
    name, row = next(iter(mutant["views"][view]["evidence_fields"].items()))
    row["distinct"] = row["distinct"] + 1
    with pytest.raises(ValueError, match="embedded view receipts diverge from traces"):
        census._unified_view_fields("nz-mutant", view, mutant)


@pytest.mark.parametrize(
    ("mutation", "view", "marker"),
    [
        ("schema", "nz/income-tax", "unsupported experiment receipt schema"),
        ("trace", "nz/income-tax", "lacks a bound trace artifact"),
        ("view", "nz/not-real", "has no view"),
    ],
)
def test_nz_certificate_trace_contract_mutants_are_killed(mutation, view, marker):
    census = _load("exercise_census")
    report = json.loads(
        (REPO / "dashboard/public/data/nz-treasury-incomeexplorer.json").read_text()
    )
    mutant = copy.deepcopy(report["experiment"])
    if mutation == "schema":
        mutant["schema"] = "mutant"
    elif mutation == "trace":
        mutant["trace"] = None

    with pytest.raises(ValueError, match=marker):
        census._unified_view_fields("nz-mutant", view, mutant)


@pytest.mark.parametrize(
    ("mutation", "marker"),
    [
        ("evaluation-count", "has no evaluation traces"),
        ("evidence-fields", "has no traced input fields"),
        ("field-state", "contradicts its traces"),
        ("root-set-count", "requested-root receipt is not exact"),
        ("trace-binding", "trace/root binding is incomplete"),
        ("root-reconciliation", "trace/root binding is incomplete"),
    ],
)
def test_nz_derived_view_shape_mutants_are_killed(mutation, marker, monkeypatch):
    census = _load("exercise_census")
    report = json.loads(
        (REPO / "dashboard/public/data/nz-treasury-incomeexplorer.json").read_text()
    )
    experiment = copy.deepcopy(report["experiment"])
    views = experiment["views"]
    row = views["nz/income-tax"]
    if mutation == "evaluation-count":
        row["evaluation_count"] = 0
    elif mutation == "evidence-fields":
        row["evidence_fields"] = {}
    elif mutation == "field-state":
        field = next(iter(row["evidence_fields"].values()))
        field["state"] = "constant"
    elif mutation == "root-set-count":
        row["root_set_receipts"][0]["evaluation_count"] += 1
    elif mutation == "trace-binding":
        row["trace_binding"] = "unbound"
    else:
        row["root_reconciliation"] = "none"
    trace = experiment["trace"]
    monkeypatch.setattr(census, "_bound_nz_trace_contract", lambda: (views, trace))

    with pytest.raises(ValueError, match=marker):
        census._unified_view_fields("nz-mutant", "nz/income-tax", experiment)


def test_nz_exercise_receipt_cannot_substitute_a_claimed_trace_hash():
    census = _load("exercise_census")
    report = json.loads(
        (REPO / "dashboard/public/data/nz-treasury-incomeexplorer.json").read_text()
    )
    mutant = copy.deepcopy(report["experiment"])
    mutant["trace"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="trace reference diverges"):
        census._unified_view_fields("nz-mutant", "nz/income-tax", mutant)


def test_nz_certificate_path_reopens_the_committed_trace_bytes(monkeypatch):
    census = _load("exercise_census")
    report = json.loads(
        (REPO / "dashboard/public/data/nz-treasury-incomeexplorer.json").read_text()
    )
    trace_path = (
        REPO / "comparisons/nz-treasury-incomeexplorer/evaluation-traces.json"
    ).resolve()
    original = Path.read_bytes

    def drift_trace_bytes(path):
        value = original(path)
        return value + b"\n" if path.resolve() == trace_path else value

    monkeypatch.setattr(Path, "read_bytes", drift_trace_bytes)
    census._bound_nz_trace_contract.cache_clear()
    with pytest.raises(ValueError, match="evaluation trace bytes changed"):
        census._census_suite(
            "nz-treasury-incomeexplorer",
            report,
            REPO / "dashboard/public/data/nz-treasury-incomeexplorer.json",
            view="nz/income-tax",
        )


def test_nz_exercise_receipt_is_certificate_scoped():
    """Adding NZ must not invalidate unrelated certificates via a global hash."""

    census = _load("exercise_census")
    certify = _load("certify")
    assert "nz-treasury-incomeexplorer" not in census.build_census()["suites"]

    scoped, evidence = certify._exercise_census_for(
        certify.PROGRAMS["nz/income-tax"]
    )
    assert "nz-treasury-incomeexplorer" in scoped["suites"]
    income_tax = scoped["suites"]["nz-treasury-incomeexplorer"]
    assert evidence[0]["claim"] == "view-scoped evaluation traces:nz/income-tax"

    wff_scoped, wff_evidence = certify._exercise_census_for(
        certify.PROGRAMS["nz/working-for-families"]
    )
    wff = wff_scoped["suites"]["nz-treasury-incomeexplorer"]
    assert income_tax["view"] == "nz/income-tax"
    assert wff["view"] == "nz/working-for-families"
    assert income_tax["evaluations_scanned"] == 91
    assert wff["evaluations_scanned"] == 178
    assert income_tax["requested_output_roots"] != wff["requested_output_roots"]
    assert wff_evidence[0]["claim"].endswith("nz/working-for-families")

    dk = certify.build_certificate(
        "dk/boerne-og-ungeydelse",
        certify.PROGRAMS["dk/boerne-og-ungeydelse"],
    )
    committed = json.loads(
        (REPO / "certificates/dk-boerne-og-ungeydelse.json").read_text()
    )
    assert dk == committed


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("trace_binding", "unbound"),
        ("root_reconciliation", "none"),
        ("root_set_receipts", []),
    ],
)
def test_nz_certificate_rejects_incomplete_trace_rows(field, value):
    census = _load("exercise_census")
    certify = _load("certify")
    report_path = REPO / "dashboard/public/data/nz-treasury-incomeexplorer.json"
    report = json.loads(report_path.read_text())
    row = census._census_suite(
        "nz-treasury-incomeexplorer",
        report,
        report_path,
        view="nz/income-tax",
    )
    row[field] = value
    entry = certify.PROGRAMS["nz/income-tax"]["suites"][0]
    defects = []
    _rows, complete = certify._exercise_block(
        [entry],
        {"suites": {"nz-treasury-incomeexplorer": row}},
        defects,
    )
    assert complete is False
    assert any("view-scoped request/output traces" in defect for defect in defects)


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


# ── strict covered_by: typed, suite-bound evidence (delta audits #2–#5) ─────


COUPLE_REPORT = "dashboard/public/data/axiom-euromod-dk-child-youth-benefit-couple.json"
COUPLE_INDEX = "dashboard/public/data/cases/dk-child-youth-benefit-couple/index.json"
COUPLE_CHUNK = "dashboard/public/data/cases/dk-child-youth-benefit-couple/chunk-0.json"


def _couple_manifest():
    vbm = _load("validate_bridge_manifests")
    path = REPO / "axiom_oracles/bridges/manifests/dk-child-youth-benefit-couple.yaml"
    manifest = yaml.safe_load(path.read_text())
    assert manifest.get("strict") is True
    errors, findings = vbm.validate(path, manifest)
    assert not errors and not findings, (errors, findings)
    binding = next(b for b in manifest["bindings"] if b.get("kind") == "bridged")
    return vbm, path, manifest, binding


def test_strict_typed_evidence_honest_forms_validate():
    vbm, path, manifest, binding = _couple_manifest()
    binding["covered_by"] = [
        {"report": COUPLE_REPORT, "claim": "the executed receipt"},
        {"chunk_index": COUPLE_INDEX, "claim": "the bound index"},
        {"chunk": COUPLE_CHUNK, "claim": "the case corpus"},
    ]
    errors, findings = vbm.validate(path, manifest)
    assert not errors and not findings, (errors, findings)


@pytest.mark.parametrize(
    "entry",
    [
        # bare string: the entire five-round smuggling saga was over free text —
        # prose is now a separate opaque field and strings are not evidence
        COUPLE_REPORT + " — executed receipt",
        "dk-child-youth-benefit-couple",
        "README.md",
        # wrong suite's report / index / an unlisted chunk (relevance gap)
        {"report": "dashboard/public/data/axiom-euromod-dk-child-youth-benefit.json", "claim": "x"},
        {"report": "conformance/exercise-census.json", "claim": "x"},
        {"report": "certificates/dk-boerne-og-ungeydelse.json", "claim": "x"},
        {"report": "axiom_oracles/bridges/manifests/dk-child-youth-benefit-couple.yaml", "claim": "self"},
        {"chunk_index": "dashboard/public/data/cases/dk-child-youth-benefit/index.json", "claim": "x"},
        {"chunk": "dashboard/public/data/cases/dk-child-youth-benefit/chunk-0.json", "claim": "x"},
        # physical: outside roots / unshipped / never-shipped / case-variant / abs
        {"report": "tests/test_certification_mutants.py", "claim": "x"},
        {"report": "axiom_oracles/__pycache__/x.pyc", "claim": "x"},
        {"report": COUPLE_REPORT.replace("axiom", "Axiom"), "claim": "x"},
        {"report": str(REPO / COUPLE_REPORT), "claim": "x"},
        # shape: two keys, unknown key, no key, empty/missing claim, non-str path
        {"report": COUPLE_REPORT, "chunk_index": COUPLE_INDEX, "claim": "x"},
        {"report": COUPLE_REPORT, "claim": "x", "note": "extra"},
        {"claim": "x"},
        {"report": COUPLE_REPORT, "claim": ""},
        {"report": COUPLE_REPORT},
        {"report": ["not", "a", "path"], "claim": "x"},
        {},
    ],
)
def test_strict_typed_evidence_rejects(entry):
    """MUTANTS: every non-conforming or non-relevant covered_by entry on a
    strict lane is a finding, so bridge_audited (and the certificate's
    exercised premise) can only rest on THIS suite's own execution receipt."""
    vbm, path, manifest, binding = _couple_manifest()
    binding["covered_by"] = [entry]
    _errors, findings = vbm.validate(path, manifest)
    assert findings, entry
    # ...and the census keys bridge_audited off it: strict-clean must be False
    # (validated through the validator the census itself loads)
    assert not (not _errors and not findings)


def test_strict_typed_evidence_prose_is_opaque():
    """The claim is never parsed: any text — paths, unicode look-alikes,
    invisible characters — is fine there, because it proves nothing and the
    resolver never sees it."""
    vbm, path, manifest, binding = _couple_manifest()
    binding["covered_by"] = [
        {"report": COUPLE_REPORT, "claim": "see tests/x.py [C:secret] ~me ／ \u200b README.md ..."},
    ]
    errors, findings = vbm.validate(path, manifest)
    assert not errors and not findings, (errors, findings)


def test_shipped_evidence_file_physical_rules():
    """The single physical resolver: exact-case, symlink-free, shipped,
    resolved inside an evidence root — no string-prefix containment."""
    vbm = _load("validate_bridge_manifests")
    assert vbm._shipped_evidence_file(COUPLE_REPORT)
    assert vbm._shipped_evidence_file(COUPLE_INDEX)
    for bad in (
        "Dashboard/public/data/axiom-euromod-dk-child-youth-benefit-couple.json",
        "dashboard/public/data/AXIOM-euromod-dk-child-youth-benefit-couple.json",
        "docs/../tests/test_certification_mutants.py",
        "/etc/passwd",
        "axiom_oracles/__pycache__/x.pyc",
        "docs/.hidden/x.json",
        "docs/x.json~",
        "dashboard/public/data",  # a directory
        "docs-private/x.md",
    ):
        assert vbm._shipped_evidence_file(bad) is False, bad
    # symlinked directory under a root → rejected even though is_file() is True
    link_dir = REPO / "docs" / "zz-audit-symlink-mutant"
    assert not link_dir.exists()
    link_dir.symlink_to(REPO / "tests" / "fixtures" / "evidence" / "contested_reports")
    try:
        cited = "docs/zz-audit-symlink-mutant/census.json"
        assert (REPO / cited).is_file()
        assert vbm._shipped_evidence_file(cited) is False
    finally:
        link_dir.unlink()
    # git-untracked file under a root → rejected in a checkout
    stray = REPO / "docs" / "zz-untracked-evidence-mutant.md"
    assert not stray.exists()
    stray.write_text("not tracked\n")
    try:
        assert vbm._shipped_evidence_file("docs/zz-untracked-evidence-mutant.md") is False
    finally:
        stray.unlink()


def test_executable_receipt_binds_reports_provenance_commit():
    """MUTANT: the receipt recompiles at rulespec.sha; the reports it
    reproduces record which rulespec commit THEY executed. A receipt at
    9986b603 sat over reports whose provenance said bbc987b0 (identical
    module bytes, workflow-only descendant) unnoticed until the typed
    evidence contract cross-checked the manifests' claims. Now bound."""
    er = _load("executable_reproduction")
    document = json.loads(
        (REPO / "conformance/executable/dk-boerne-og-ungeydelse.json").read_text()
    )
    er.validate_artifact(document, repo_root=REPO)
    mutant = copy.deepcopy(document)
    other = "9986b6035c4e557b9b40645dfe2f3e4cffb6037c"
    mutant["rulespec"]["sha"] = other
    mutant["rulespec"]["ref"] = other
    with pytest.raises(ValueError, match="report provenance pins rulespec-dk"):
        er.validate_artifact(mutant, repo_root=REPO)


def test_closure_ledger_records_resolved_commits():
    """Hermetic half: the committed ledger's generated facts pin RESOLVED
    commits — ref equals commit for both the rulespec and corpus facts, and
    both are canonical git object ids. Runs everywhere (no external clones)."""
    facts = yaml.safe_load(
        (REPO / "conformance/closure/dk-boerne-og-ungeydelse.yaml").read_text()
    )["generated_facts"]
    for fact in ("rulespec", "corpus_release"):
        ref, commit = facts[fact]["ref"], facts[fact]["commit"]
        assert ref == commit, fact
        assert isinstance(commit, str) and len(commit) == 40, fact
        assert any(c in "abcdef" for c in commit), fact


@pytest.mark.skipif(
    not (Path.home() / "TheAxiomFoundation" / "rulespec-dk" / ".git").exists(),
    reason="needs the local rulespec-dk clone (the full re-derivation path; "
    "CI runs the hermetic validate/certify gates instead)",
)
def test_closure_check_pins_to_recorded_commit(tmp_path):
    """Default --check re-derives at the ledger's RECORDED rulespec commit
    (so rulespec-dk main advancing with unrelated commits cannot make the
    ledger stale); an EXPLICIT --rulespec-ref asks whether the ledger is
    current against THAT commit — an older commit reports drift."""
    # closure_ledger declares dataclasses under `from __future__ import
    # annotations`; they resolve their module by name at class-creation time,
    # so it must be registered in sys.modules before exec (certify.py's
    # _producer_module does the same).
    import sys

    spec = importlib.util.spec_from_file_location(
        "_mutant_closure_ledger", REPO / "scripts" / "closure_ledger.py"
    )
    cl = importlib.util.module_from_spec(spec)
    sys.modules["_mutant_closure_ledger"] = cl
    spec.loader.exec_module(cl)
    recorded = yaml.safe_load(
        (REPO / "conformance/closure/dk-boerne-og-ungeydelse.yaml").read_text()
    )["generated_facts"]["rulespec"]["commit"]
    assert len(recorded) == 40
    assert cl.main(["--check"]) == 0
    assert cl.main(["--check", "--rulespec-ref", recorded]) == 0
    # currency against the OLDER commit 9986b603 (same module bytes, but the
    # ledger records bbc987b0): the recorded pin differs → drift
    rc = cl.main(["--check", "--rulespec-ref", "9986b6035c4e557b9b40645dfe2f3e4cffb6037c"])
    assert rc == 1
    # and the ledger's own generated_facts.rulespec.ref is the immutable sha
    facts = yaml.safe_load(
        (REPO / "conformance/closure/dk-boerne-og-ungeydelse.yaml").read_text()
    )["generated_facts"]
    assert facts["rulespec"]["ref"] == facts["rulespec"]["commit"] == recorded
    assert facts["corpus_release"]["ref"] == facts["corpus_release"]["commit"]


def test_strict_evidence_rejects_never_shipped_files():
    """MUTANT (delta-audit #4): a gitignored __pycache__/*.pyc under an
    evidence root exists on this disk but in no clone and not in the refresh
    bot's rsync'd tree; it passed as strict evidence. Never-shipped
    components/suffixes are rejected outright, and — when the tree is a git
    checkout — the path must be git-tracked."""
    vbm = _load("validate_bridge_manifests")
    for bad in (
        "axiom_oracles/__pycache__/x.pyc",
        "axiom_oracles/x.pyc",
        "docs/.hidden/evidence.json",
        "docs/evidence.json~",
        "reports/node_modules/x.json",
    ):
        assert vbm._plausibly_shipped(bad) is False, bad
    assert vbm._plausibly_shipped(
        "dashboard/public/data/axiom-euromod-dk-child-youth-benefit-couple.json"
    )
    # git gate: an untracked file under a root is not evidence in a checkout
    stray = REPO / "docs" / "zz-untracked-evidence-mutant.md"
    assert not stray.exists()
    stray.write_text("not tracked\n")
    try:
        assert vbm._shipped_evidence_file("docs/zz-untracked-evidence-mutant.md") is False
    finally:
        stray.unlink()


def test_producers_must_agree_on_one_rulespec_commit(tmp_path, monkeypatch):
    """MUTANT (delta-audit #6): the closure ledger and executable receipt each
    verify their OWN recorded pin, so a ledger coherently regenerated at
    9986b603 passes its own check while the receipt sits at bbc987b0 (byte-
    identical modules, different commit). certify must refuse to treat those
    as one certificate: a producer-commit mismatch is a blocker."""
    certify = _load("certify")
    ledger_path = REPO / "conformance/closure/dk-boerne-og-ungeydelse.yaml"
    original = ledger_path.read_text()
    doc = yaml.safe_load(original)
    facts = doc["generated_facts"]["rulespec"]
    assert facts["commit"] == facts["ref"]
    receipt = json.loads(
        (REPO / "conformance/executable/dk-boerne-og-ungeydelse.json").read_text()
    )
    assert receipt["rulespec"]["sha"] == facts["commit"]  # baseline agrees

    other = "9986b6035c4e557b9b40645dfe2f3e4cffb6037c"
    # A "coherently regenerated" ledger at the other commit: the pin moves,
    # everything else (identical module bytes) stays. Serialize through the
    # producer so the artifact is byte-canonical for its own validator.
    facts["commit"] = other
    facts["ref"] = other
    import sys

    spec = importlib.util.spec_from_file_location(
        "_mutant_closure_ledger_drift", REPO / "scripts" / "closure_ledger.py"
    )
    cl = importlib.util.module_from_spec(spec)
    sys.modules["_mutant_closure_ledger_drift"] = cl
    spec.loader.exec_module(cl)
    ledger_path.write_text(cl.serialize_artifact(doc))
    try:
        cert = certify.build_certificate(
            "dk/boerne-og-ungeydelse", certify.PROGRAMS["dk/boerne-og-ungeydelse"]
        )
    finally:
        ledger_path.write_text(original)
    assert cert["verdicts"]["closed"]["mode"] == "computed"
    assert cert["verdicts"]["closed"]["rulespec_commit"] == other
    assert cert["verdicts"]["executable"]["rulespec_sha"] == receipt["rulespec"]["sha"]
    assert any("producers disagree on the rulespec commit" in b for b in cert["blockers"]), cert["blockers"]
    assert cert["certified"]["value"] is False


def test_ledger_commit_must_be_a_string_sha_and_ref_must_equal_commit():
    """MUTANT (delta-audit #7): a 40-DIGIT YAML integer is a legal scalar
    that `str(commit)` turned into a passing "sha"; certification then emitted
    a computed closed premise while the commit cross-check silently skipped
    the non-string. The validator now requires a string SHA and ref==commit
    for both the rulespec and corpus facts, and certify treats non-comparable
    provenance on two computed premises as a blocker."""
    import sys

    spec = importlib.util.spec_from_file_location(
        "_mutant_closure_ledger_types", REPO / "scripts" / "closure_ledger.py"
    )
    cl = importlib.util.module_from_spec(spec)
    sys.modules["_mutant_closure_ledger_types"] = cl
    spec.loader.exec_module(cl)
    ledger_path = REPO / "conformance/closure/dk-boerne-og-ungeydelse.yaml"
    baseline = yaml.safe_load(ledger_path.read_text())
    assert cl._validation_errors(baseline) == []

    digits = int("1" * 40)  # a 40-digit integer, not a hex string
    # delta-audit #8: the !!str-tagged form is a 40-char DECIMAL string, which
    # is syntactically valid hex — it must still fail (a real git object id
    # has at least one of a-f; a decimal-only id is the forgery shape).
    digit_str = "1234567890123456789012345678901234567890"
    for fact in ("rulespec", "corpus_release"):
        for forged in (digits, digit_str):
            doc = copy.deepcopy(baseline)
            doc["generated_facts"][fact]["commit"] = forged
            doc["generated_facts"][fact]["ref"] = forged
            errors = cl._validation_errors(doc)
            assert any("commit must be a full git commit SHA" in e for e in errors), (
                fact, forged, errors
            )

        doc = copy.deepcopy(baseline)
        doc["generated_facts"][fact]["ref"] = "main"
        errors = cl._validation_errors(doc)
        assert any("must equal" in e and "commit" in e for e in errors), (fact, errors)

    # certify, fail-closed: even if a non-string commit reached the closed
    # block, two computed premises without comparable provenance BLOCK.
    certify = _load("certify")
    original_closed = certify._producer_closed_verdict

    def _tampered(program, spec_, evidence, *, verify_producer=False):
        block = original_closed(program, spec_, evidence, verify_producer=verify_producer)
        if block is not None:
            block["rulespec_commit"] = digits
        return block

    certify._producer_closed_verdict = _tampered
    try:
        cert = certify.build_certificate(
            "dk/boerne-og-ungeydelse", certify.PROGRAMS["dk/boerne-og-ungeydelse"]
        )
    finally:
        certify._producer_closed_verdict = original_closed
    assert cert["verdicts"]["closed"]["mode"] == "computed"
    assert cert["verdicts"]["executable"]["mode"] == "computed"
    assert any("provenance is not comparable" in b for b in cert["blockers"]), cert["blockers"]
    assert cert["certified"]["value"] is False

    # delta-audit #8: COORDINATED equal digit-only strings on both computed
    # sides satisfied plain equality. Equality now counts only between values
    # that are each a canonical git object id.
    original_exec = certify._producer_executable_verdict

    def _tampered_closed(program, spec_, evidence, *, verify_producer=False):
        block = original_closed(program, spec_, evidence, verify_producer=verify_producer)
        if block is not None:
            block["rulespec_commit"] = digit_str
        return block

    def _tampered_exec(program, spec_, evidence, *, verify_producer=False):
        block = original_exec(program, spec_, evidence, verify_producer=verify_producer)
        if block is not None:
            block["rulespec_sha"] = digit_str
        return block

    certify._producer_closed_verdict = _tampered_closed
    certify._producer_executable_verdict = _tampered_exec
    try:
        cert = certify.build_certificate(
            "dk/boerne-og-ungeydelse", certify.PROGRAMS["dk/boerne-og-ungeydelse"]
        )
    finally:
        certify._producer_closed_verdict = original_closed
        certify._producer_executable_verdict = original_exec
    assert cert["verdicts"]["closed"]["rulespec_commit"] == digit_str
    assert cert["verdicts"]["executable"]["rulespec_sha"] == digit_str
    assert any("provenance is not comparable" in b for b in cert["blockers"]), cert["blockers"]
    assert cert["certified"]["value"] is False
    assert cert["certified"]["state"] != "yes"


def test_executable_receipt_rejects_digit_only_sha():
    """delta-audit #8: the receipt's own sha regex accepted a decimal-only
    40-char string; canonical git object ids need at least one of a-f."""
    er = _load("executable_reproduction")
    document = json.loads(
        (REPO / "conformance/executable/dk-boerne-og-ungeydelse.json").read_text()
    )
    er.validate_artifact(document, repo_root=REPO)
    mutant = copy.deepcopy(document)
    digit_str = "1234567890123456789012345678901234567890"
    mutant["rulespec"]["sha"] = digit_str
    mutant["rulespec"]["ref"] = digit_str
    with pytest.raises(ValueError):
        er.validate_artifact(mutant, repo_root=REPO)


def test_tariff_scale_report_rejects_fabricated_conformant(monkeypatch):
    """The C1 report's typed premise is checked against producer semantics."""
    certify = _load("certify")
    entry = certify.PROGRAMS["us/tariff-duty"]["suites"][0]
    report = json.loads((REPO / entry["report"]).read_text())
    report["summary"]["unexplained"] = 1
    report["summary"]["explained"] -= 1
    monkeypatch.setattr(certify, "_load", lambda _path: report)
    leg, _evidence, defects = certify._tariff_schedule_suite_verdict(entry)
    assert leg["clean"] is False
    assert any("conformant flag is fabricated" in defect for defect in defects)


def test_tariff_scale_report_derives_open_axiom_units(monkeypatch):
    certify = _load("certify")
    entry = certify.PROGRAMS["us/tariff-duty"]["suites"][0]
    report = json.loads((REPO / entry["report"]).read_text())
    monkeypatch.setattr(certify, "_load", lambda _path: report)
    leg, _evidence, defects = certify._tariff_schedule_suite_verdict(entry)
    assert defects == []
    assert leg["axiom_attributed_open"] == 1_592_236
    assert leg["axiom_attributed_open_classes"] == {
        "fed-false-family-brazil": 93_198,
        "fed-false-family-forced-labor": 1_499_038,
    }
    assert leg["clean"] is False
