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
        "matched": 168094, "explained": 15411, "unexplained": 39189,
        "entries": {
            "rebate-timing": 14872,
            "niit-addmed-no-scorp": 3443,
            "addmed-in-fiitax": 539,
            "niit-no-scorp": 83,
            "niit-addmed-scorp": 8559,
            "niit-scorp-at-cap-single": 305,
            "niit-scorp-at-cap-joint": 1203,
            "niit-scorp-unreconciled": 282,
            "al-state-residual": 595,
            "al-federal-residual": 134,
            "niit-scorp": 3,
        },
    },
    2022: {
        "matched": 175546, "explained": 15593, "unexplained": 31555,
        "entries": {
            "rebate-timing": 15115,
            "niit-addmed-no-scorp": 3332,
            "addmed-in-fiitax": 478,
            "niit-no-scorp": 84,
            "niit-addmed-scorp": 6996,
            "niit-scorp-at-cap-joint": 1188,
            "niit-scorp-unreconciled": 288,
            "niit-scorp-at-cap-single": 139,
            "al-federal-residual": 160,
            "al-state-residual": 391,
            "niit-scorp": 3,
        },
    },
    2023: {
        "matched": 183593, "explained": 4893, "unexplained": 34208,
        "entries": {
            "niit-addmed-no-scorp": 3455,
            "addmed-in-fiitax": 506,
            "niit-no-scorp": 84,
            "rebate-timing": 4387,
            "niit-addmed-scorp": 8464,
            "niit-scorp-at-cap-joint": 1185,
            "niit-scorp-at-cap-single": 303,
            "niit-scorp-unreconciled": 293,
            "al-state-residual": 388,
            "al-federal-residual": 121,
            "niit-scorp": 3,
        },
    },
    2024: {
        "matched": 188026, "explained": 2934, "unexplained": 31734,
        "entries": {
            "niit-no-scorp": 1152,
            "md-august-county-signature": 739,
            "rebate-timing": 2934,
            "niit-scorp-unreconciled": 8170,
            "niit-scorp-at-cap-joint": 1184,
            "niit-scorp-at-cap-single": 222,
            "niit-scorp": 93,
            "al-state-residual": 375,
            "al-federal-residual": 128,
        },
    },
    2025: {
        "matched": 188070, "explained": 2691, "unexplained": 31933,
        "entries": {
            "niit-no-scorp": 1003,
            "md-august-county-signature": 742,
            "rebate-timing": 1261,
            "la-standard-deduction-omission": 1430,
            "la-other-state-residual": 481,
            "niit-scorp-unreconciled": 7736,
            "niit-scorp-at-cap-joint": 1015,
            "niit-scorp": 174,
            "niit-scorp-at-cap-single": 202,
            "al-federal-residual": 154,
            "al-state-residual": 378,
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

        if entry["id"] == "niit-scorp" or entry["id"].startswith("niit-scorp-at-cap-"):
            assert entry["disposition"] == "unexplained"
            assert entry["attribution"] == "two_sided"
            assert entry["adjudication"] == "pe-taxsim-1053"
        if entry["disposition"] != "unexplained":
            assert entry["adjudication"] in {"pe-taxsim-1225", "pe-taxsim-1222", "pe-taxsim-1068"}
        if entry["disposition"] == "explained_residual":
            assert entry["attribution"] in {"convention", "input"}
        if entry["disposition"] == "upstream_engine_gap":
            assert entry["attribution"] in {"taxsim", "policyengine"}

        arithmetic = entry["evidence"].get("row_arithmetic", [])
        if entry["disposition"] != "unexplained":
            assert arithmetic, entry["id"]
        if entry["id"].startswith("niit-scorp") or entry["id"] == "niit-addmed-scorp":
            assert all(row["facts"]["scorp"] != 0 for row in rows)
        if entry["id"] == "niit-scorp-unreconciled":
            assert entry["disposition"] == "unexplained"
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
    # PR #1249 has no qualifying maintainer comment atom: both observations
    # stay unexplained under the evidence registry, rather than inferring fault.
    assert block["unexplained_count"] == block["counts"]["unexplained"] == 2
    assert block["counts"]["upstream_engine_gap"] == 0
    assert block["raw_match_rate"] == 50
    assert block["explained_rate"] == 50
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
        if state == 0:
            assert entry["disposition"] == "unexplained"
            assert entry["attribution"] == "two_sided"
            assert entry["adjudication"] == "pe-taxsim-1249"
            assert entry["linked_issue"].endswith("/pull/1249")
        else:
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


NIIT_THRESHOLD = {1: 200000, 2: 250000, 6: 125000, 8: 200000}


@pytest.mark.parametrize("year", range(2021, 2026))
def test_scorp_niit_hypotheses_retain_their_numeric_signatures(year):
    """Downgrading evidence readiness preserves the recorded numeric classes.

    These equalities locate differences; they supply no external legal proof
    or historical applicability for the amounts used in the signatures.
    """
    suite = f"taxsim-emulator-ecps-{year}"
    report = load_report(ROOT / f"reports/taxsim-emulator/{suite}.json.gz")
    checked = 0
    for row in report["mismatches"]:
        entry_id = (row.get("disposition") or {}).get("id", "")
        if not entry_id.startswith("niit-scorp") or entry_id == "niit-scorp-unreconciled":
            continue
        left, right, scorp = row["aux"]["left"], row["aux"]["right"], row["facts"]["scorp"]
        gap = right["niit"] - left["niit"]
        assert abs(row["difference"] + gap) <= 1
        if entry_id == "niit-scorp":
            assert abs(gap - 0.038 * scorp) <= 1
        else:
            limit = 0.038 * (right["v10"] - NIIT_THRESHOLD[row["facts"]["mstat"]])
            assert abs(left["v10"] - right["v10"]) <= 1
            assert abs(right["niit"] - limit) <= 1
            assert left["niit"] < limit - 0.5
            assert left["niit"] + 0.038 * scorp >= limit - 1
        checked += 1
    assert checked == sum(
        count for entry_id, count in EXPECTED[year]["entries"].items()
        if entry_id.startswith("niit-scorp") and entry_id != "niit-scorp-unreconciled"
    )


@pytest.mark.parametrize("year,previous_explained,withdrawn", [
    (2021, 16922, 1511), (2022, 16923, 1330), (2023, 6384, 1491),
    (2024, 4433, 1499), (2025, 4082, 1391),
])
def test_registry_migration_intentionally_withdraws_historical_niit_claims(
    year, previous_explained, withdrawn
):
    assert EXPECTED[year]["explained"] == previous_explained - withdrawn
    assert withdrawn == sum(
        count for entry_id, count in EXPECTED[year]["entries"].items()
        if entry_id == "niit-scorp" or entry_id.startswith("niit-scorp-at-cap-")
    )
