from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from axiom_oracles.bridges.state_tax_populace_runner import (
    DISPOSITION_BLOCKED,
    DISPOSITION_READY,
    TaxUnitRoute,
)
import scripts.run_state_tax_populace as campaign


def _contract():
    jurisdictions = {
        "CA": SimpleNamespace(status="blocked"),
        "NJ": SimpleNamespace(status="ready"),
        "NM": SimpleNamespace(status="ready"),
    }
    return SimpleNamespace(
        validation_year=2026,
        populace_year=2024,
        by_state=lambda: jurisdictions,
    )


@pytest.mark.parametrize(
    ("state", "error"),
    [
        ("XX", "unknown campaign state abbreviation.*XX"),
        ("ca", "requested campaign state.*not ready: CA"),
        ("NH", "no broad current PIT: NH"),
    ],
)
def test_invalid_requested_state_fails_before_dataset_load(
    monkeypatch, tmp_path, state: str, error: str
) -> None:
    monkeypatch.setattr(campaign, "load_state_tax_populace_contract", _contract)

    def reject_dataset_load(*args, **kwargs):
        pytest.fail("invalid state should fail before the dataset is loaded")

    monkeypatch.setattr(campaign, "load_populace_dataset", reject_dataset_load)

    with pytest.raises(SystemExit, match=error):
        campaign.main(
            [
                "--state",
                state,
                "--rulespec-root",
                str(tmp_path),
                "--axiom-rules-path",
                str(tmp_path),
                "--output",
                str(tmp_path / "report.json"),
            ]
        )


def test_repeatable_state_filter_preserves_national_routing_report(
    monkeypatch, tmp_path
) -> None:
    routes = (
        TaxUnitRoute(1, 1, "NJ", "34", 1, DISPOSITION_READY),
        TaxUnitRoute(2, 2, "NM", "35", 1, DISPOSITION_READY),
        TaxUnitRoute(3, 3, "CA", "06", 1, DISPOSITION_BLOCKED),
    )
    calls: dict[str, tuple[TaxUnitRoute, ...]] = {}

    monkeypatch.setattr(campaign, "load_state_tax_populace_contract", _contract)
    monkeypatch.setattr(campaign, "load_populace_dataset", lambda *a, **k: "dataset")
    monkeypatch.setattr(campaign, "validate_campaign_dataset_identity", lambda *a, **k: None)
    monkeypatch.setattr(campaign, "population_table", lambda dataset, table: table)
    monkeypatch.setattr(campaign, "route_tax_units", lambda **kwargs: routes)

    def targets(**kwargs):
        calls["targets"] = tuple(kwargs["routes"])
        return {"NJ": {1: 0.0}}

    def projections(**kwargs):
        calls["projections"] = tuple(kwargs["routes"])
        return {"NJ": {}}

    def routing_report(received_routes, **kwargs):
        calls["routing"] = tuple(received_routes)
        return {"scope": "national"}

    def comparison(**kwargs):
        calls["comparison"] = tuple(kwargs["routes"])
        calls["known_tax_unit_ids"] = set(kwargs["known_tax_unit_ids"])
        return {"scope": "filtered"}

    monkeypatch.setattr(campaign, "calculate_policyengine_targets", targets)
    monkeypatch.setattr(
        campaign, "calculate_policyengine_projection_inputs", projections
    )
    monkeypatch.setattr(campaign, "population_routing_report", routing_report)
    monkeypatch.setattr(campaign, "compare_ready_state_tax_units", comparison)
    monkeypatch.setattr(campaign, "runtime_provenance", lambda **kwargs: {})

    output = tmp_path / "report.json"
    assert campaign.main(
        [
            "--state",
            "nj",
            "--state",
            "NJ",
            "--rulespec-root",
            str(tmp_path),
            "--axiom-rules-path",
            str(tmp_path),
            "--output",
            str(output),
        ]
    ) == 0

    report = json.loads(output.read_text())
    assert report["requested_states"] == ["NJ"]
    assert report["routing"] == {"scope": "national"}
    assert report["comparison"] == {"scope": "filtered"}
    assert calls["routing"] == routes
    expected_filtered = (routes[0],)
    assert calls["targets"] == expected_filtered
    assert calls["projections"] == expected_filtered
    assert calls["comparison"] == expected_filtered
    assert calls["known_tax_unit_ids"] == {1, 2, 3}


def test_utah_projection_diagnostics_pin_exempt_and_domain_branch_counts() -> None:
    prefix = (
        "us-ut:policies/income_tax/"
        "2026_full_year_resident_before_credit_schedule#input."
    )
    routes = (
        TaxUnitRoute(1, 1, "UT", "49", 1, DISPOSITION_READY),
        TaxUnitRoute(2, 2, "UT", "49", 1, DISPOSITION_READY),
        TaxUnitRoute(3, 3, "UT", "49", 1, DISPOSITION_BLOCKED),
    )
    diagnostics = campaign._projection_branch_diagnostics(
        {
            "UT": {
                f"{prefix}ut_pit_2026_state_taxable_income": {
                    1: -5.0,
                    2: 100.0,
                    3: -10.0,
                },
                (
                    f"{prefix}"
                    "ut_pit_2026_is_exempt_under_section_59_10_104_1"
                ): {1: True, 2: False, 3: True},
            }
        },
        routes,
    )

    assert diagnostics == {
        "UT": {
            "compared_tax_unit_count": 2,
            "exempt_count": 1,
            "nonexempt_count": 1,
            "negative_taxable_income_count": 1,
        }
    }


def test_dc_projection_diagnostics_pin_taxable_income_floor_branches() -> None:
    slot = (
        "us-dc:policies/income_tax/"
        "2026_section_47_1806_03_schedule_before_credits#input."
        "dc_pit_2026_section_47_1806_03_completed_joint_method_taxable_income"
    )
    routes = (
        TaxUnitRoute(1, 1, "DC", "11", 1, DISPOSITION_READY),
        TaxUnitRoute(2, 2, "DC", "11", 1, DISPOSITION_READY),
        TaxUnitRoute(3, 3, "DC", "11", 1, DISPOSITION_READY),
        TaxUnitRoute(4, 4, "DC", "11", 1, DISPOSITION_BLOCKED),
    )

    diagnostics = campaign._projection_branch_diagnostics(
        {"DC": {slot: {1: -5.0, 2: 0.0, 3: 100.0, 4: -10.0}}},
        routes,
    )

    assert diagnostics == {
        "DC": {
            "compared_tax_unit_count": 3,
            "negative_taxable_income_count": 1,
            "zero_taxable_income_count": 1,
            "positive_taxable_income_count": 1,
        }
    }
