"""Mutants the certification checks must kill (2026-07-26 audit, finding 16 lite).

Each test constructs an input the corresponding gate exists to reject and
asserts rejection. A check that has never been seen to fail is unproven; these
are the demonstrations, kept green forever. Grow this catalogue whenever a gate
gains a rule — a rule without a mutant here is not yet a rule.
"""

import copy
import importlib.util
import shutil
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent


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
            "dk/boerne-og-ungeydelse",
            certify.PROGRAMS["dk/boerne-og-ungeydelse"],
            [],
            verify_producer=True,
        )
    assert len(calls) == 1
    assert calls[0]["rulespec_ref"] == artifact["rulespec"]["sha"]


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


def test_weighted_mass_must_be_finite_and_nonnegative():
    # _verdict loads the module itself; no direct handle needed here.
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


def test_covered_by_rejects_ghosts_and_absolute_paths():
    vbm = _load("validate_bridge_manifests")
    assert vbm._covered_by_resolves("ghost-sibling/no-such/evidence.yaml") is False
    assert vbm._covered_by_resolves("/etc/passwd") is False
    assert vbm._covered_by_resolves("../../../etc/passwd") is False
    assert vbm._covered_by_resolves(".") is False
    assert vbm._covered_by_resolves("dashboard/public/data") is False


def test_contested_reports_are_a_certificate_defect():
    """nyc-synthetic: two reports claim the suite, sharing one chunk dir."""
    certify = _load("certify")
    census = json.loads((REPO / "conformance/exercise-census.json").read_text())
    assert census["suites"]["nyc-synthetic"].get("contested_reports")
    defects: list[str] = []
    _rows, complete = certify._exercise_block(
        [
            {
                "suite": "nyc-synthetic",
                "oracle_type": "reference",
                "oracle": "x",
                "report": "dashboard/public/data/axiom-policyengine.json",
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
    assert any("outside the shipped evidence roots" in f for f in mutated), mutated

    # Non-strict lanes may still cite such paths (visible debt, not enforced).
    manifest["strict"] = False
    _errors, relaxed = vbm.validate(path, manifest)
    assert not any("outside the shipped evidence roots" in f for f in relaxed)


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
