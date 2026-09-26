"""Pinned ledger coverage and evidence checks against every recorded mismatch."""

from collections import defaultdict
from pathlib import Path

import pytest

from axiom_oracles.comparison.dispositions import (
    CLASSIFIED_DISPOSITION_KINDS,
    apply_dispositions,
    load_dispositions,
    row_binary_sha256,
    selection_binding,
)
from axiom_oracles.comparison.report_io import load_report

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SHA = "8aa880aeea33fd501f669d42125615e3b2a0ab19c17d93a76457e9de16615059"
FALLBACK_SHA = "00a321d2467ba011992f8b83c6e485a9b710c48fca4262a23fec1de26942a89b"
DARWIN_SHA = "02286edad9c023b0f61d32e6aed680370ecf3e767c217bbb0289f85b64ff105d"

# Fixed counts from the reviewed release, independent of the report's persisted
# disposition summary and selector_binding counts. Updating a selector requires
# explicitly reviewing its coverage changes here.
EXPECTED = {
    2021: {
        "matched": 168094, "explained": 17204, "unexplained": 37396,
        "entries": {
            "addmed-in-fiitax": 539,
            "niit-scorp": 1793,
            "niit-addmed-scorp": 8559,
            "niit-no-scorp": 83,
            "niit-addmed-no-scorp": 3443,
            "rebate-timing": 14872,
            "al-federal-residual": 134,
            "al-state-residual": 595,
        },
    },
    2022: {
        "matched": 175546, "explained": 17211, "unexplained": 29937,
        "entries": {
            "addmed-in-fiitax": 478,
            "niit-scorp": 1618,
            "niit-addmed-scorp": 6996,
            "niit-no-scorp": 84,
            "niit-addmed-no-scorp": 3332,
            "rebate-timing": 15115,
            "al-federal-residual": 160,
            "al-state-residual": 391,
        },
    },
    2023: {
        "matched": 183593, "explained": 6677, "unexplained": 32424,
        "entries": {
            "addmed-in-fiitax": 506,
            "niit-scorp": 1784,
            "niit-addmed-scorp": 8464,
            "niit-no-scorp": 84,
            "niit-addmed-no-scorp": 3455,
            "rebate-timing": 4387,
            "al-federal-residual": 121,
            "al-state-residual": 388,
        },
    },
    2024: {
        "matched": 188026, "explained": 12603, "unexplained": 22065,
        "entries": {
            "niit-scorp": 9669,
            "niit-no-scorp": 1152,
            "rebate-timing": 2934,
            "md-august-county-signature": 739,
            "al-federal-residual": 128,
            "al-state-residual": 375,
        },
    },
    2025: {
        "matched": 188070, "explained": 11818, "unexplained": 22806,
        "entries": {
            "niit-scorp": 9127,
            "niit-no-scorp": 1003,
            "rebate-timing": 1261,
            "md-august-county-signature": 742,
            "al-federal-residual": 154,
            "al-state-residual": 378,
            "la-standard-deduction-omission": 1430,
            "la-other-state-residual": 481,
        },
    },
}


@pytest.mark.parametrize("year", range(2021, 2026))
def test_emulator_ledger_coverage_and_evidence(year):
    suite = f"taxsim-emulator-ecps-{year}"
    dispositions_file = f"dispositions/{suite}.yaml"
    report = load_report(ROOT / f"reports/taxsim-emulator/{suite}.json.gz")
    dispositions = load_dispositions(ROOT / dispositions_file, repo_root=ROOT)
    merged = apply_dispositions(
        report, dispositions, dispositions_file=dispositions_file, taxsim_lane=True
    )
    summary = merged["summary"]
    block = summary["dispositioned"]
    expected = EXPECTED[year]
    assert report["summary"]["dispositioned"] == block

    # apply_dispositions checks every arithmetic identity and rejects overlaps.
    # A single changed row, oracle, or arithmetic claim must invalidate coverage.
    assert block["expired_entries"] == []
    assert block["orphaned_entries"] == []
    assert summary["comparison_count"] == 222_694
    assert summary["match_count"] == expected["matched"]
    explained = sum(block["counts"][kind] for kind in CLASSIFIED_DISPOSITION_KINDS)
    assert explained == expected["explained"]
    assert block["unexplained_count"] == expected["unexplained"]
    assert expected["matched"] + explained + expected["unexplained"] == 222_694
    assert block["raw_match_rate"] == pytest.approx(
        expected["matched"] / 222_694 * 100, abs=0.000001
    )
    assert block["explained_rate"] == pytest.approx(
        (expected["matched"] + explained) / 222_694 * 100, abs=0.000001
    )

    selected = defaultdict(list)
    for row in merged["mismatches"]:
        if "disposition" in row:
            selected[row["disposition"]["id"]].append(row)
    assert {key: len(rows) for key, rows in selected.items()} == expected["entries"]

    for entry in dispositions["entries"]:
        rows = selected[entry["id"]]
        assert rows, entry["id"]
        assert entry["linked_issue"].startswith(
            "https://github.com/PolicyEngine/policyengine-taxsim/"
        )
        assert entry["attribution"] in {
            "taxsim", "policyengine", "convention", "input", "two_sided"
        }
        assert entry["expires_on_source_change"] is True
        assert entry["selector_binding"] == selection_binding(rows)
        recorded_shas = {row_binary_sha256(row) for row in rows}
        expected_shas = {
            FALLBACK_SHA
            if year >= 2024 and row["facts"]["taxsim_state"] in {11, 21}
            else DEFAULT_SHA
            for row in rows
        }
        assert recorded_shas == expected_shas, entry["id"]
        assert set(entry["oracle_binding"]["taxsim_binary_sha256"]) == recorded_shas

        if entry["disposition"] == "explained_residual":
            assert entry["attribution"] in {"convention", "input"}
        if entry["disposition"] == "upstream_engine_gap":
            assert entry["attribution"] in {"taxsim", "policyengine"}

        arithmetic = entry["evidence"].get("row_arithmetic", [])
        if entry["disposition"] != "unexplained":
            assert arithmetic, entry["id"]
        if entry["id"] in {"niit-scorp", "niit-addmed-scorp"}:
            assert all(row["facts"]["scorp"] != 0 for row in rows)
        if entry["id"] in {"niit-no-scorp", "niit-addmed-no-scorp"}:
            assert all(row["facts"]["scorp"] == 0 for row in rows)
            assert entry["disposition"] == "unexplained"
            assert entry["attribution"] == "two_sided"
        if entry["id"].startswith("niit-addmed-"):
            assert year <= 2023
            assert entry["disposition"] == "unexplained"
            assert entry["attribution"] == "two_sided"
        expressions = " ".join(item["expression"] for item in arithmetic)
        if year <= 2023 and "niit" in expressions and "addmed" in expressions:
            mixed = any(
                abs(row["aux"]["right"]["niit"] - row["aux"]["left"]["niit"]) > 1
                and row["aux"]["right"]["addmed"] > 1
                for row in rows
            )
            if mixed:
                assert entry["disposition"] == "unexplained", entry["id"]
                assert entry["attribution"] == "two_sided", entry["id"]


def test_sales_tax_probes_preserve_observations_without_claiming_resolution():
    suite = "taxsim-emulator-probes"
    dispositions_file = f"dispositions/{suite}.yaml"
    report = load_report(ROOT / f"reports/taxsim-emulator/{suite}.json")
    dispositions = load_dispositions(ROOT / dispositions_file, repo_root=ROOT)
    merged = apply_dispositions(
        report, dispositions, dispositions_file=dispositions_file, taxsim_lane=True
    )
    block = merged["summary"]["dispositioned"]
    assert report["summary"]["dispositioned"] == block
    assert block["expired_entries"] == []
    assert block["orphaned_entries"] == []
    assert block["unexplained_count"] == block["counts"]["unexplained"] == 2
    assert block["raw_match_rate"] == block["explained_rate"] == 50
    assert merged["summary"]["comparison_count"] == 4
    assert merged["summary"]["error_count"] == 0
    assert merged["summary"]["match_count"] == 2
    binary, = report["engine_identity"]["taxsim"]["binaries"]
    assert binary["platform"] == "darwin"
    assert binary["sha256"] == DARWIN_SHA

    observations = {
        "taxsim-77": (0, 50165.0, "state-zero-sales-tax"),
        "taxsim-78": (44, 49618.3, "texas-sales-tax-proxy"),
    }
    entries = {entry["case_id"]: entry for entry in dispositions["entries"]}
    assert set(entries) == set(observations)
    assert {row["case_id"] for row in merged["mismatches"]} == set(observations)
    for row in merged["mismatches"]:
        state, right, entry_id = observations[row["case_id"]]
        entry = entries[row["case_id"]]
        assert row["facts"]["taxsim_state"] == state
        assert row["left"] == 49315.8515625
        assert row["right"] == right
        assert row["difference"] == pytest.approx(49315.8515625 - right, abs=1e-9)
        assert row["disposition"]["id"] == entry["id"] == entry_id
        assert entry["disposition"] == "unexplained"
        assert entry["attribution"] == "two_sided"
        assert entry["oracle_binding"]["taxsim_binary_sha256"] == [DARWIN_SHA]
        assert entry["pinned"] == {"left": row["left"], "right": row["right"]}
        assert entry["evidence"]["row_arithmetic"]


@pytest.mark.parametrize("year", [2024, 2025])
def test_successful_macos_crash_probe_has_no_speculative_error_disposition(year):
    suite = f"taxsim-crash-probes-{year}"
    report = load_report(ROOT / f"reports/taxsim-emulator/{suite}.json")
    assert report["summary"]["comparison_count"] == 4
    assert report["summary"]["match_count"] == 4
    assert report["summary"]["mismatch_count"] == 0
    assert report["summary"]["error_count"] == 0
    assert report["mismatches"] == []
    binary, = report["engine_identity"]["taxsim"]["binaries"]
    assert binary["platform"] == "darwin"
    assert binary["sha256"] == DARWIN_SHA
    assert not (ROOT / f"dispositions/{suite}.yaml").exists()
