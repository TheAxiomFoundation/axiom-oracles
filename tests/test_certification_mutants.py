"""Mutants the certification checks must kill (2026-07-26 audit, finding 16 lite).

Each test constructs an input the corresponding gate exists to reject and
asserts rejection. A check that has never been seen to fail is unproven; these
are the demonstrations, kept green forever. Grow this catalogue whenever a gate
gains a rule — a rule without a mutant here is not yet a rule.
"""

import importlib.util
import copy
import json
from pathlib import Path

import pytest

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
                "summary": {"comparison_count": 5, "match_count": 5, "mismatch_count": 0},
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
            "bindings": [{"kind": "constant", "group": "g", "reason": "r", "audit": "read"}],
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
            "bindings": [{"kind": "constant", "group": "g", "reason": "r", "audit": "read"}],
            "completeness": {"status": "verified"},
        },
    )
    assert any("cannot be self-asserted" in e for e in errors)


def test_covered_by_must_resolve_to_something_real():
    vbm = _load("validate_bridge_manifests")
    assert vbm._covered_by_resolves("ABCDEFGHIJKL") is False
    assert vbm._covered_by_resolves("see the other suite, TBD") is False
    assert vbm._covered_by_resolves("dashboard/public/data/axiom-snapqc-co-snap.json") is True


def test_certified_requires_computed_true_premises_not_status_strings():
    certify = _load("certify")
    cert = certify.build_certificate("us-co/snap", certify.PROGRAMS["us-co/snap"])
    assert cert["certified"]["state"] == "unavailable"
    assert cert["certified"]["value"] is False


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


def test_covered_by_rejects_ghosts_and_absolute_paths():
    vbm = _load("validate_bridge_manifests")
    assert vbm._covered_by_resolves("ghost-sibling/no-such/evidence.yaml") is False
    assert vbm._covered_by_resolves("/etc/passwd") is False
    assert vbm._covered_by_resolves("../../../etc/passwd") is False


def test_contested_reports_are_a_certificate_defect():
    """nyc-synthetic: two reports claim the suite, sharing one chunk dir."""
    certify = _load("certify")
    census = json.loads((REPO / "conformance/exercise-census.json").read_text())
    assert census["suites"]["nyc-synthetic"].get("contested_reports")
    defects: list[str] = []
    _rows, complete = certify._exercise_block(
        [{"suite": "nyc-synthetic", "oracle_type": "reference", "oracle": "x",
          "report": "dashboard/public/data/axiom-policyengine.json"}],
        census,
        defects,
    )
    assert complete is False
    assert any("claim this suite" in d for d in defects)


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
            {
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
            [{"suite": "nz-mutant"}],
            [],
        )
