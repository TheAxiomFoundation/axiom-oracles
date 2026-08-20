import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from axiom_oracles.evidence import strict_json_loads, validate_suite_evidence


REPO_ROOT = Path(__file__).resolve().parent.parent
COMPARISONS_DIR = REPO_ROOT / "comparisons"
DASHBOARD_DATA_DIR = REPO_ROOT / "dashboard" / "public" / "data"


def _load_bound_report_cases(report_name: str) -> tuple[dict, list[dict]]:
    """Load the authoritative case rows only after strict binding validation."""

    report_path = DASHBOARD_DATA_DIR / report_name
    report = strict_json_loads(report_path.read_text())
    assert isinstance(report, dict)

    evidence = validate_suite_evidence(report_path)
    assert evidence.valid, evidence.defects
    assert evidence.binding == "bound"
    assert evidence.reconciliation == "full"
    assert evidence.suite == report["suite"]

    case_dir = DASHBOARD_DATA_DIR / "cases" / evidence.suite
    cases: list[dict] = []
    for chunk in evidence.chunks:
        payload = strict_json_loads((case_dir / chunk.name).read_text())
        assert isinstance(payload, list)
        assert len(payload) == chunk.cases
        assert all(isinstance(case, dict) for case in payload)
        cases.extend(payload)
    assert len(cases) == evidence.case_count
    return report, cases


def test_dk_2023_child_youth_benefit_registry_config_shape() -> None:
    """Pin the DK_2023 oracle year and composed-pipeline date workaround."""

    config = yaml.safe_load(
        (COMPARISONS_DIR / "dk-child-youth-benefit-2023-euromod.yaml").read_text()
    )
    params = config["runner"]["parameters"]
    assert config["runner"]["type"] == "euromod-synthetic-compare"
    assert config["runner"]["axiom_rules_repo"].endswith(
        "/_worktrees/axiom-rules-engine-pin"
    )
    assert params["suite"] == "dk-child-youth-benefit-2023"
    assert str(params["period"]) == "2025-06-01"
    assert params["euromod_country"] == "DK"
    assert params["euromod_system"] == "DK_2023"
    assert params["euromod_dataset"] == "DK_training_data"
    assert config["dashboard"]["filename"] == (
        "axiom-euromod-dk-child-youth-benefit-2023.json"
    )


def test_dk_couple_child_youth_benefit_registry_config_shape() -> None:
    """Pin the household-sum couple witness to DK_2025 and the merged module."""

    config = yaml.safe_load(
        (COMPARISONS_DIR / "dk-child-youth-benefit-couple-euromod.yaml").read_text()
    )
    params = config["runner"]["parameters"]
    assert config["runner"]["type"] == "euromod-synthetic-compare"
    assert config["runner"]["axiom_rules_repo"].endswith(
        "/_worktrees/axiom-rules-engine-pin"
    )
    assert params["suite"] == "dk-child-youth-benefit-couple"
    assert str(params["period"]) == "2025-06-01"
    assert params["euromod_country"] == "DK"
    assert params["euromod_system"] == "DK_2025"
    assert params["euromod_dataset"] == "DK_training_data"
    assert config["dashboard"]["filename"] == (
        "axiom-euromod-dk-child-youth-benefit-couple.json"
    )


def test_dk_witness_reports_pin_live_outputs_and_dispositions() -> None:
    """Pin all three executed DK witnesses and the seven raw-match controls."""

    report_names = (
        "axiom-euromod-dk-child-youth-benefit.json",
        "axiom-euromod-dk-child-youth-benefit-2023.json",
        "axiom-euromod-dk-child-youth-benefit-couple.json",
    )
    reports_and_cases = [_load_bound_report_cases(name) for name in report_names]
    reports = [report for report, _cases in reports_and_cases]
    committed_cases = [cases for _report, cases in reports_and_cases]

    assert sum(report["summary"]["comparison_count"] for report in reports) == 10
    assert sum(report["summary"]["match_count"] for report in reports) == 7
    assert sum(report["summary"]["mismatch_count"] for report in reports) == 3
    assert all(
        report["summary"]["dispositioned"]["explained_rate"] == 100
        and report["summary"]["dispositioned"]["unexplained_count"] == 0
        for report in reports
    )
    assert (
        sum(
            report["summary"]["dispositioned"]["counts"]["upstream_engine_gap"]
            for report in reports
        )
        == 3
    )

    main_report, report_2023, couple_report = reports
    main_cases, _cases_2023, couple_cases = committed_cases
    assert len(main_cases) == 8
    assert all(case["v"] and not case["m"] for case in main_cases[:7])

    pension = main_report["mismatches"][0]
    assert pension["case_id"] == ("dk-child-youth-benefit-age5-yem1300000-pension60000")
    assert (pension["left"], pension["right"], pension["difference"]) == (
        11_184,
        # Age-35 recipient: the ORDINARY PBL § 16 cap (9.400 kr. in 2025)
        # applies, not the within-seven-years 61.200 kr. cap the first build
        # supplied (audit finding). 16764 - 2% x (1196000 - 9400/0.6 - 917000).
        11_497.333333333334,
        -313.33333333333394,
    )
    assert pension["disposition"]["id"] == (
        "euromod-dk-bfachnm-taper-pension-grossup-absent"
    )

    supplement = report_2023["mismatches"][0]
    assert (supplement["left"], supplement["right"], supplement["difference"]) == (
        15_624,
        15_684,
        -60,
    )
    assert supplement["disposition"]["id"] == (
        "euromod-dk-2023-bfachnm-supplement-600-vs-660"
    )

    couple = couple_report["mismatches"][0]
    assert couple["left"] == pytest.approx(7_504)
    assert couple["right"] == 8_384
    assert couple["difference"] == pytest.approx(-880)
    assert couple["disposition"]["id"] == ("euromod-dk-bfachnm-pre2022-spousal-taper")
    assert couple["disposition"]["disposition"] == "upstream_engine_gap"

    [couple_case] = couple_cases
    compact_inputs = {row["n"]: row["v"] for row in couple_case["i"]}
    assert compact_inputs["result_aggregation"] == {
        "entity_ids": ["earner", "non_earner"],
        "strategy": "sum",
    }
    components = compact_inputs["result_aggregation_applied"]["components"]
    concept = couple["concept"]
    assert [(row["entity_id"], row["values"][concept]) for row in components] == [
        ("earner", 0),
        ("non_earner", 8_384),
    ]


def test_dk_all_four_computed_premises_flow_to_certificate() -> None:
    """Pin the bridge audits plus both producer-backed premise modes."""
    suite_names = (
        "dk-child-youth-benefit",
        "dk-child-youth-benefit-2023",
        "dk-child-youth-benefit-couple",
    )
    census = json.loads((REPO_ROOT / "conformance/exercise-census.json").read_text())
    for suite in suite_names:
        row = census["suites"][suite]
        assert row["bridge_declared"] is True
        assert row["bridge_audited"] is True

    certificate = json.loads(
        (REPO_ROOT / "certificates/dk-boerne-og-ungeydelse.json").read_text()
    )
    verdicts = certificate["verdicts"]
    # The closed premise satisfies the instrument-frontier requirement
    # (oracles#491): the closure ledger dispositions every instrument in the
    # act's ELI graph plus the search-discovered supplement, so certify
    # computes closed=true under the strengthened predicate and certified
    # re-derives yes.
    assert {
        name: (block["mode"], block["value"]) for name, block in verdicts.items()
    } == {
        "conformant": ("computed", True),
        "exercised": ("computed", True),
        "closed": ("computed", True),
        "executable": ("computed", True),
    }
    closed_frontier = verdicts["closed"]["instrument_frontier"]
    assert closed_frontier["complete"] is True
    assert closed_frontier["counts"] == {
        "total": 28,
        "encoded": 0,
        "classified-with-reason": 17,
        "excluded-with-reason": 11,
        "pending": 0,
    }
    assert closed_frontier["pending"] == []
    assert not any(
        blocker.startswith("exercise:") for blocker in certificate["blockers"]
    )
    assert certificate["blockers"] == []
    assert certificate["certified"]["value"] is True
    assert certificate["certified"]["state"] == "yes"

    evidence = {row["artifact"]: row for row in certificate["evidence"]}
    for relative in (
        "conformance/closure/dk-boerne-og-ungeydelse.yaml",
        "conformance/executable/dk-boerne-og-ungeydelse.json",
    ):
        path = REPO_ROOT / relative
        assert evidence[relative]["mode"] == "computed"
        assert evidence[relative]["verification"] == ("producer_artifact_validation")
        assert (
            evidence[relative]["sha256"]
            == hashlib.sha256(path.read_bytes()).hexdigest()
        )

    assert (
        "no producer computes closed/executable yet"
        not in certificate["certified"]["rule"]
    )


def test_dk_certificate_artifact_check_is_hermetic(tmp_path: Path) -> None:
    """Ordinary CI must not depend on sibling Git checkouts or a macOS engine."""

    isolated_home = tmp_path / "empty-home"
    isolated_home.mkdir()
    env = os.environ.copy()
    env["HOME"] = str(isolated_home)
    process = subprocess.run(
        [sys.executable, "scripts/certify.py", "--check"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert process.returncode == 0, process.stderr
    assert "certificates up to date" in process.stdout
