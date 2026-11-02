"""Committed-evidence invariants for the Germany dual-oracle lane."""

import json
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "dashboard" / "public" / "data"
REPORT_NAME = "euromod-gettsim-de-worker-dual-oracle.json"
REPORT_PATH = DATA_DIR / REPORT_NAME
TAX = (
    "de:policies/worker_dual_oracle_baseline"
    "#income_tax_including_solidarity_surcharge_annual"
)
CARE = (
    "de:policies/worker_dual_oracle_baseline"
    "#employee_long_term_care_insurance_contribution_monthly"
)


def _report() -> dict:
    return json.loads(REPORT_PATH.read_text())


def test_de_dual_oracle_report_is_published_and_manifested() -> None:
    manifest = json.loads((DATA_DIR / "manifest.json").read_text())

    assert REPORT_PATH.exists()
    assert REPORT_NAME in manifest["reports"]


def test_de_dual_oracle_report_pins_live_run_contract() -> None:
    report = _report()

    assert report["schema_version"] == "axiom.comparison_report.v2.1"
    assert report["suite"] == "de-worker-dual-oracle"
    assert report["population"] == "synthetic"
    assert report["engines"] == {"left": "euromod", "right": "gettsim"}
    assert report["case_count"] == 13

    summary = report["summary"]
    assert summary["comparison_count"] == 78
    assert summary["match_count"] == 66
    assert summary["mismatch_count"] == 12
    assert summary["error_count"] == 0

    dispositioned = summary["dispositioned"]
    assert dispositioned["raw_match_rate"] == 84.615385
    assert dispositioned["explained_rate"] == 100
    assert dispositioned["unexplained_count"] == 0
    assert dispositioned["counts"] == {
        "axiom_encoding_gap": 0,
        "bridge_artifact": 0,
        "explained_residual": 0,
        "unexplained": 0,
        "upstream_engine_gap": 12,
    }
    assert dispositioned["expired_entries"] == []
    assert dispositioned["orphaned_entries"] == []

    provenance = report["provenance"]
    assert provenance.get("rulespecs", []) == []
    assert provenance.get("engine", {}) == {}
    assert provenance["oracle"] == {
        "name": "euromod-gettsim",
        "euromod_release": "J2.0+",
        "euromod_country": "DE",
        "euromod_system": "DE_2025",
        "euromod_dataset": "DE_2024_b1_2015_03_e2",
        "gettsim_version": "1.2.1",
        "gettsim_policy_date": "2025-06-30",
    }
    assert report["engine_metadata"]["euromod"] == {
        "country": "DE",
        "system": "DE_2025",
        "dataset": "DE_2024_b1_2015_03_e2",
        "template_dataset": "DE_training_data",
        "extra_columns": ["drgn1"],
    }


def test_de_dual_oracle_report_pins_filed_findings_only() -> None:
    mismatches = _report()["mismatches"]

    assert {(row["case_id"], row["concept"]) for row in mismatches} == {
        ("single-w-1200", CARE),
        ("single-w-2500", TAX),
        ("single-w-4000", TAX),
        ("single-w-5500", TAX),
        ("single-w-7500", TAX),
        ("single-w-9000", TAX),
        ("single-w-12000", TAX),
        ("single-e-4000", TAX),
        ("couple-8000-0", TAX),
        ("couple-4000-2000", TAX),
        ("parent-1child-4000", TAX),
        ("parent-2children-4000", TAX),
    }
    assert all(row["kind"] == "amount_difference" for row in mismatches)
    assert all(row["tolerance"] == 0.01 for row in mismatches)
    assert all(abs(row["difference"]) > row["tolerance"] for row in mismatches)
    assert Counter(row["disposition"]["id"] for row in mismatches) == {
        "euromod-vorsorgeaufwendungen-deduction-haircut-and-pauschbetrag": 9,
        "euromod-child-allowance-without-kindergeld-addback": 2,
        "euromod-midijob-childless-care-surcharge-base": 1,
    }

