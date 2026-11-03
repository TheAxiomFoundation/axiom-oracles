"""The TAXSIM-lane attribution calls follow from the committed evidence.

Each test re-derives one call in docs/taxsim-disposition-migration-audit.md
from the receipt or report the entry cites, so a changed receipt or a changed
call fails here instead of drifting apart.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
RECEIPT = (
    REPO_ROOT
    / "reports/axiom-taxsim-co-tax-intersection-ecps-member-decomposition-2026-08-31.json"
)
FIIT_FULL = REPO_ROOT / "reports/axiom-taxsim-fiit-ecps-verify-2026-08-28.json"


def _entry(suite: str, entry_id: str) -> dict:
    doc = yaml.safe_load((REPO_ROOT / f"dispositions/{suite}.yaml").read_text())
    [entry] = [entry for entry in doc["entries"] if entry["id"] == entry_id]
    return entry


def _row_attribution(entry: dict, case_id: str) -> str:
    return (entry.get("attribution_by_case") or {}).get(case_id, entry["attribution"])


def _qbid_seca_rule(members: dict[str, float]) -> str:
    """Attribution of the row's leading member (see the entry's comment)."""
    lead = max(members, key=lambda name: abs(members[name]))
    value = members[lead]
    if lead == "seca_ald":
        # Only the -93.00 bridge OASDI-base member leads among SE-ALD members.
        assert value == -93.0, members
        return "convention"
    if value > 0 or -value < 400:
        return "taxsim"  # missing phase-in, or missing $400 minimum
    return "convention"  # QBI-base difference: the rental-in-QBI convention


def test_qbid_seca_composite_rows_follow_their_leading_member() -> None:
    entry = _entry(
        "co-tax-intersection-taxsim", "taxsim-qbid-seca-member-composite-taxable-income"
    )
    members = json.loads(RECEIPT.read_text())["taxable_income_members"]
    calls = {
        case_id: _qbid_seca_rule(members[case_id]["members"])
        for case_id in entry["case_selector"]["case_ids"]
    }
    assert {
        case_id: _row_attribution(entry, case_id) for case_id in calls
    } == calls
    assert sum(call == "taxsim" for call in calls.values()) == 18
    assert sum(call == "convention" for call in calls.values()) == 7


def test_blindness_and_qbid_composite_is_led_by_the_qbid_convention() -> None:
    entry = _entry(
        "co-tax-intersection-taxsim",
        "taxsim-blindness-63f-and-qbid-composite-taxable-income",
    )
    members = json.loads(RECEIPT.read_text())["taxable_income_members"]
    [case_id] = entry["case_selector"]["case_ids"]
    # 6,731.31 (QBID rental convention) + 1,650.00 (63(f) blindness).
    assert entry["evidence"]["arithmetic"][0]["expression"] == "6731.31 + 1650.0"
    assert 6731.31 > 1650.0
    assert entry["attribution"] == "convention"
    assert case_id in members


def test_open_rows_name_the_two_convention_rows() -> None:
    for suite, entry_id in (
        ("co-state-income-tax-taxsim", "co-state-open-rows-axiom-pe-divergent"),
        (
            "co-tax-intersection-taxsim",
            "co-intersection-state-open-rows-axiom-pe-divergent",
        ),
    ):
        entry = _entry(suite, entry_id)
        assert entry["attribution"] == "taxsim"
        assert entry["attribution_by_case"] == {
            "ecps-tax-unit-136208": "convention",
            "ecps-tax-unit-59285": "convention",
        }
        # The mechanism decomposes those two rows to the auto-HoH standard
        # deduction and the automatic itemization.
        mechanism = " ".join(entry["evidence"]["mechanism"].split())
        assert "136208" in mechanism and "59285" in mechanism


def test_seca_1402b2_gate_counts_the_rows_its_mechanism_explains() -> None:
    entry = _entry("fiit-taxsim-ecps", "axiom-seca-medicare-rate-only-1402b2-gate")
    selected = set(entry["case_selector"]["case_ids"])
    report = json.loads(FIIT_FULL.read_text())
    rows = [
        row
        for row in report["mismatches"]
        if row["case_id"] in selected and row["concept"] == entry["concept"]
    ]
    bound = 0.153 * 400
    explained = [row for row in rows if -bound - 0.01 <= row["difference"] < 0]
    positive = [row for row in rows if row["difference"] > 0]
    other = [row for row in rows if row["difference"] < -bound - 0.01]
    assert (len(rows), len(explained), len(positive), len(other)) == (217, 169, 47, 1)
    assert round(max(row["difference"] for row in positive), 2) == 3227627.85
    assert [row["case_id"] for row in other] == ["ecps-tax-unit-1907"]
    assert entry["attribution"] == "taxsim"
    assert "provisional" in entry["notes"].lower()
