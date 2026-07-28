from __future__ import annotations

import hashlib
import subprocess
from types import SimpleNamespace

import pytest

from axiom_oracles.adapters.policyengine import runner as policyengine_runner
from scripts import build_ca_snap_362_dispositions as builder
from scripts import trace_ca_snap_residuals as tracer


BASE_REF = "7dac6fef7019a00ed2b097db9250973223f9e907"


def _base_report_bytes() -> bytes:
    return subprocess.run(
        [
            "git",
            "-C",
            str(tracer.ROOT),
            "show",
            f"{BASE_REF}:{tracer.REPORT_RELATIVE_PATH}",
        ],
        check=True,
        capture_output=True,
    ).stdout


def test_base_report_ref_and_path_resolve_the_same_pinned_state(tmp_path):
    report_from_ref, ref_source = tracer._load_base_report(
        base_ref=BASE_REF,
        base_report=None,
    )
    path = tmp_path / "base-report.json"
    path.write_bytes(_base_report_bytes())
    report_from_path, path_source = tracer._load_base_report(
        base_ref=None,
        base_report=path,
    )

    assert report_from_path == report_from_ref
    assert ref_source == {
        "kind": "git",
        "commit": BASE_REF,
        "sha256": tracer.BASE_REPORT_SHA256,
    }
    assert path_source["kind"] == "path"
    assert path_source["sha256"] == tracer.BASE_REPORT_SHA256
    unexplained = [
        row for row in report_from_ref["mismatches"] if row.get("disposition") is None
    ]
    assert len(unexplained) == 441
    assert len({row["case_id"] for row in unexplained}) == 361


def test_base_report_hash_gate_rejects_semantically_equal_byte_drift(tmp_path):
    path = tmp_path / "base-report.json"
    path.write_bytes(_base_report_bytes() + b"\n")

    with pytest.raises(ValueError, match="sha256 mismatch"):
        tracer._load_base_report(base_ref=None, base_report=path)


def test_base_dispositions_come_from_explicit_base_not_current_output(
    tmp_path,
    monkeypatch,
):
    _, source = tracer._load_base_report(
        base_ref=BASE_REF,
        base_report=None,
    )
    corrupt_output = tmp_path / "ca-snap-ecps.yaml"
    corrupt_output.write_text(
        "schema: axiom_oracles.dispositions.v1\n"
        "suite: ca-snap-ecps\n"
        "entries:\n"
        "- id: silently-corrupted-current-output\n"
    )
    monkeypatch.setattr(builder, "DISPOSITIONS_PATH", corrupt_output)

    base = builder._load_base_dispositions(
        base_source=source,
        base_dispositions=None,
    )

    retained = [
        entry for entry in base["entries"] if not entry["id"].startswith("ca-362-")
    ]
    assert len(retained) == 4
    assert all(entry["id"].startswith("ca-bbce-") for entry in retained)
    assert "silently-corrupted-current-output" not in {
        entry["id"] for entry in base["entries"]
    }

    corrected_text = (tracer.ROOT / builder.DISPOSITIONS_RELATIVE_PATH).read_text()
    corrected = builder.yaml.safe_load(corrected_text)
    additions = [
        entry for entry in corrected["entries"] if entry["id"].startswith("ca-362-")
    ]
    rebuilt = builder._render_dispositions(base, additions)
    assert rebuilt == corrected_text
    assert rebuilt != corrupt_output.read_text()


def test_base_dispositions_path_is_required_and_hash_pinned(tmp_path):
    path = tmp_path / "base-dispositions.yaml"
    raw = subprocess.run(
        [
            "git",
            "-C",
            str(tracer.ROOT),
            "show",
            f"{BASE_REF}:{builder.DISPOSITIONS_RELATIVE_PATH}",
        ],
        check=True,
        capture_output=True,
    ).stdout
    path.write_bytes(raw)
    source = {"kind": "path", "path": "base-report.json"}

    document = builder._load_base_dispositions(
        base_source=source,
        base_dispositions=path,
    )
    assert document["suite"] == "ca-snap-ecps"

    with pytest.raises(ValueError, match="requires the matching"):
        builder._load_base_dispositions(
            base_source=source,
            base_dispositions=None,
        )

    path.write_bytes(raw + b"\n")
    with pytest.raises(ValueError, match="sha256 mismatch"):
        builder._load_base_dispositions(
            base_source=source,
            base_dispositions=path,
        )


def test_trace_implementation_provenance_binds_tracer_and_runner_bytes():
    provenance = tracer._implementation_provenance()

    assert provenance == {
        "tracer_path": tracer.TRACER_RELATIVE_PATH,
        "tracer_sha256": tracer._sha256_path(tracer.ROOT / tracer.TRACER_RELATIVE_PATH),
        "runner_path": tracer.RUNNER_RELATIVE_PATH,
        "runner_sha256": tracer._sha256_path(tracer.ROOT / tracer.RUNNER_RELATIVE_PATH),
    }


def test_trace_hash_gate_rejects_unpinned_bytes(tmp_path, monkeypatch):
    path = tmp_path / "trace.json"
    raw = b'{"schema_version":"test"}\n'
    path.write_bytes(raw)
    monkeypatch.setattr(
        builder,
        "EXPECTED_TRACE_SHA256",
        hashlib.sha256(raw).hexdigest(),
    )

    assert builder._load_trace(path) == {"schema_version": "test"}

    path.write_bytes(raw + b"\n")
    with pytest.raises(ValueError, match="trace sha256 mismatch"):
        builder._load_trace(path)


def test_legacy_calendar_average_uses_overridden_annual_values(
    monkeypatch,
):
    monkeypatch.setattr(
        policyengine_runner,
        "_policyengine_variable_is_boolean",
        lambda _pe, variable, _value: variable == "eligible",
    )
    monkeypatch.setattr(
        policyengine_runner,
        "_policyengine_definition_period",
        lambda _pe, variable: (
            "month" if variable in {"snap", "snap_unearned_income"} else "year"
        ),
    )

    replay = tracer._LegacyCalendarAverageMixin()
    values = replay._requested_period_values(
        object(),
        [SimpleNamespace(period="2026-01")],
        [
            {
                "snap": 1_200.0,
                "snap_unearned_income": 2_400.0,
                "eligible": True,
                "tanf": 9_600.0,
            }
        ],
    )

    assert values == [{"snap": 100.0, "snap_unearned_income": 2_400.0}]


def test_challenged_static_cases_have_unambiguous_round_two_routes():
    assert builder.STATIC_SE_FAILED == {"ecps-59082", "ecps-62506"}
    assert not (builder.STATIC_SE_FAILED & builder.STATIC_SE)
    assert not (builder.STATIC_SE_MULTIMECHANISM & builder.STATIC_SE)

    trace_membership = {
        case_id: [
            classification
            for classification, case_ids in builder.TRACE_CLASSES.items()
            if case_id in case_ids
        ]
        for case_id in builder.STATIC_SE_MULTIMECHANISM
    }
    assert all(len(classes) == 1 for classes in trace_membership.values())
    assert sum("tanf" in classes[0] for classes in trace_membership.values()) == 11
    assert sum("period" in classes[0] for classes in trace_membership.values()) == 9


def _version_drift_cases() -> dict[str, dict]:
    cases = {}
    for case_id in builder.EXPECTED_VERSION_CHANGED_CASES:
        closes = case_id in builder.EXPECTED_GENUINE_VERSION_DRIFT
        cases[case_id] = {
            "case_id": case_id,
            "report": {
                "axiom_eligible": True,
                "pe_eligible": True,
                "axiom_benefit": 200.0,
                "pe_benefit": 100.0,
            },
            "live_pe": {"snap": 101.0, "is_snap_eligible": True},
            "requested_month_pe": {
                "snap": 200.0 if closes else 100.0,
                "is_snap_eligible": True,
            },
        }
    return cases


def test_version_drift_gate_requires_exact_three_close_seventy_four_persist():
    cases = _version_drift_cases()

    assert builder._validate_version_drift(cases) == (3, 74)

    persistent = next(
        case_id
        for case_id in builder.EXPECTED_VERSION_CHANGED_CASES
        if case_id not in builder.EXPECTED_GENUINE_VERSION_DRIFT
    )
    cases[persistent]["requested_month_pe"]["snap"] = 200.0
    with pytest.raises(ValueError, match="closure set"):
        builder._validate_version_drift(cases)


def test_induced_tanf_guard_requires_both_source_alignments():
    case = {
        "axiom_evidence": {"inputs": {"unearned_income": 0.19}},
        "counterfactuals": {
            "zero_self_employment": {
                "tanf": 9_109.94,
                "ca_tanf": 9_109.94,
                "snap_unearned_income": 9_112.22,
            }
        },
    }
    assert builder._induced_tanf_guard(case, requested_month=False)

    case["counterfactuals"]["zero_self_employment"]["ca_tanf"] += 1
    assert not builder._induced_tanf_guard(case, requested_month=False)
    case["counterfactuals"]["zero_self_employment"]["ca_tanf"] -= 1
    case["counterfactuals"]["zero_self_employment"]["snap_unearned_income"] += 1
    assert not builder._induced_tanf_guard(case, requested_month=False)
