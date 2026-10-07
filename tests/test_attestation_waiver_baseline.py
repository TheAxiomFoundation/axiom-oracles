"""Migration waivers remain approved, artifact-bound, shrinking debt."""

from __future__ import annotations

import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import pytest

from axiom_oracles.conformance.attestation import EXECUTION_ATTESTATION_SCHEMA
from axiom_oracles.conformance.loader import OracleIdentity, Universe
from axiom_oracles.conformance.schema import UniversePolicy
from axiom_oracles.conformance.scoreboard import score_jurisdiction
from axiom_oracles.conformance.waivers import (
    AttestationWaiver,
    WaiverIndex,
    parse,
    serialize,
)

REPO_ROOT = Path(__file__).parents[1]


def _approved_waiver() -> AttestationWaiver:
    return AttestationWaiver(
        "be", "be:tintb_be", "be-marital-quotient", "compared_surface_differs"
    )


def _approved_report() -> dict:
    return json.loads(
        (REPO_ROOT / "dashboard/public/data/axiom-euromod-be-marital-quotient.json")
        .read_text()
    )


def _approved_universe() -> Universe:
    return Universe(
        jurisdiction="be",
        oracle=OracleIdentity("EUROMOD", "J2.0", "BE_2025", "BE", "euromod"),
        policies=[
            UniversePolicy(
                id="be:tintb_be",
                oracle_policy_name="tintb_be",
                output_vars=("tintasp_s",),
                in_scope=True,
                suite="be-marital-quotient",
            )
        ],
    )


@pytest.mark.parametrize(
    "waiver",
    [
        AttestationWaiver("tx", "tx:new", "new-suite", "compared_surface_differs"),
        replace(_approved_waiver(), suite="replacement-suite"),
        replace(_approved_waiver(), reason="oracle_variable_not_recorded"),
    ],
    ids=["addition", "suite-change", "reason-change"],
)
def test_current_waivers_cannot_expand_or_redefine_bootstrap_debt(tmp_path, waiver):
    path = tmp_path / "attestation_waivers.yaml"
    path.write_text(serialize([waiver]))
    with pytest.raises(ValueError, match="bootstrap"):
        parse(path)


def test_bootstrap_waiver_rows_cannot_be_duplicated(tmp_path):
    path = tmp_path / "attestation_waivers.yaml"
    path.write_text(serialize([_approved_waiver(), _approved_waiver()]))
    with pytest.raises(ValueError, match="duplicate"):
        parse(path)


def test_unchanged_approved_legacy_report_keeps_waived_coverage():
    board, scores = score_jurisdiction(
        _approved_universe(), [_approved_report()],
        waivers=WaiverIndex([_approved_waiver()]),
    )
    assert board.covered == 1
    assert board.conformant
    assert scores[0].output_attestation == "waived:compared_surface_differs"


def test_legacy_waiver_cannot_cover_a_replacement_report():
    report = _approved_report()
    report["generated_at"] = "2099-01-01T00:00:00Z"
    board, scores = score_jurisdiction(
        _approved_universe(), [report], waivers=WaiverIndex([_approved_waiver()])
    )
    assert board.covered == 0
    assert not board.conformant
    assert scores[0].status == "unbound"


def test_newly_stamped_report_cannot_use_legacy_waiver():
    report = _approved_report()
    summary = report["summary"]
    report["attestation"] = {
        "schema_version": EXECUTION_ATTESTATION_SCHEMA,
        "executed": True,
        "case_count": report["case_count"],
        "comparison_count": summary["comparison_count"],
        "error_count": 0,
        "engines": report["engines"],
        "outputs": [
            {
                "concept": report["aggregates"][0]["concept"],
                "engine": "euromod",
                "variable": "tin_s",
                "comparisons": report["aggregates"][0]["comparison_count"],
            }
        ],
    }
    board, scores = score_jurisdiction(
        _approved_universe(), [report], waivers=WaiverIndex([_approved_waiver()])
    )
    assert board.covered == 0
    assert not board.conformant
    assert scores[0].status == "unbound"


def test_adding_needed_waiver_with_new_stamped_unbound_report_fails_gate(
    tmp_path, monkeypatch
):
    """The independent review's waiver_repro.py, with the gate invariant asserted."""
    spec = importlib.util.spec_from_file_location(
        "attestation_gate", REPO_ROOT / "scripts/conformance_attestation.py"
    )
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    conf = tmp_path / "conformance"
    data = tmp_path / "data"
    conf.mkdir()
    data.mkdir()
    (conf / "tx.yaml").write_text(
        "schema: axiom_oracles.conformance.v1\n"
        "jurisdiction: tx\n"
        "oracle:\n"
        "  model: EUROMOD\n"
        "  release: J2.0\n"
        "  system: TX\n"
        "  country: TX\n"
        "  backend: euromod\n"
        "policies:\n"
        "- id: tx:new-unbound-policy\n"
        "  oracle_policy_name: new-unbound-policy\n"
        "  output_vars: [x_s]\n"
        "  in_scope: true\n"
        "  suite: new-suite\n"
    )
    report = {
        "suite": "new-suite",
        "engines": {"left": "euromod", "right": "axiom"},
        "case_count": 1,
        "summary": {
            "comparison_count": 1,
            "match_count": 1,
            "mismatch_count": 0,
            "error_count": 0,
        },
        "errors": [],
        "aggregates": [{"concept": "other-output", "comparison_count": 1}],
        "attestation": {
            "schema_version": EXECUTION_ATTESTATION_SCHEMA,
            "executed": True,
            "case_count": 1,
            "comparison_count": 1,
            "error_count": 0,
            "engines": {"left": "euromod", "right": "axiom"},
            "outputs": [{
                "concept": "other-output", "engine": "euromod",
                "variable": "y_s", "comparisons": 1,
            }],
        },
    }
    (data / "report.json").write_text(json.dumps(report))
    path = conf / "attestation_waivers.yaml"
    monkeypatch.setattr(gate, "CONFORMANCE_DIR", conf)
    monkeypatch.setattr(gate, "DASHBOARD_DATA_DIR", data)
    monkeypatch.setattr(gate, "WAIVERS_PATH", path)
    monkeypatch.setattr("sys.argv", ["conformance_attestation.py", "--check"])
    assert gate.main() == 1
    path.write_text(serialize([AttestationWaiver(
        "tx", "tx:new-unbound-policy", "new-suite", "compared_surface_differs",
        "New waiver for a newly stamped report.",
    )]))
    assert gate.main() == 1


def test_direct_waiver_index_cannot_approve_new_debt():
    report = _approved_report()
    report["suite"] = "new-suite"
    policy = replace(
        _approved_universe().policies[0], id="be:new", suite="new-suite"
    )
    universe = replace(_approved_universe(), policies=[policy])
    waiver = replace(_approved_waiver(), policy_id="be:new", suite="new-suite")
    board, _ = score_jurisdiction(universe, [report], waivers=WaiverIndex([waiver]))
    assert board.covered == 0
    assert not board.conformant
