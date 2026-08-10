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


def test_california_projection_diagnostics_pin_bhst_branches() -> None:
    slot = (
        "us-ca:policies/income_tax/pilot_liability_pipeline#input."
        "ca_pit_pilot_supplied_completed_taxable_income"
    )
    routes = (
        TaxUnitRoute(1, 1, "CA", "06", 1, DISPOSITION_READY),
        TaxUnitRoute(2, 2, "CA", "06", 1, DISPOSITION_READY),
        TaxUnitRoute(3, 3, "CA", "06", 1, DISPOSITION_READY),
        TaxUnitRoute(4, 4, "CA", "06", 1, DISPOSITION_BLOCKED),
    )

    diagnostics = campaign._projection_branch_diagnostics(
        {
            "CA": {
                slot: {
                    1: -5.0,
                    2: 1_000_000.0,
                    3: 1_000_001.0,
                    4: 2_000_000.0,
                }
            }
        },
        routes,
    )

    assert diagnostics == {
        "CA": {
            "compared_tax_unit_count": 3,
            "zero_behavioral_health_services_tax_count": 2,
            "positive_behavioral_health_services_tax_count": 1,
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


def test_new_york_projection_diagnostics_pin_schedule_branches() -> None:
    prefix = "us-ny:policies/income_tax/pilot_liability_pipeline#input."
    routes = (
        TaxUnitRoute(1, 1, "NY", "36", 1, DISPOSITION_READY),
        TaxUnitRoute(2, 2, "NY", "36", 1, DISPOSITION_READY),
        TaxUnitRoute(3, 3, "NY", "36", 1, DISPOSITION_READY),
        TaxUnitRoute(4, 4, "NY", "36", 1, DISPOSITION_BLOCKED),
    )

    diagnostics = campaign._projection_branch_diagnostics(
        {
            "NY": {
                f"{prefix}ny_pit_pilot_state_taxable_income": {
                    1: -1.0,
                    2: 0.0,
                    3: 100.0,
                    4: 200.0,
                },
                (
                    f"{prefix}"
                    "ny_pit_pilot_filing_status_joint_or_surviving_spouse"
                ): {1: True, 2: False, 3: False, 4: True},
                (
                    f"{prefix}"
                    "ny_pit_pilot_filing_status_head_of_household"
                ): {1: False, 2: True, 3: False, 4: False},
            }
        },
        routes,
    )

    assert diagnostics == {
        "NY": {
            "compared_tax_unit_count": 3,
            "negative_taxable_income_count": 1,
            "zero_taxable_income_count": 1,
            "positive_taxable_income_count": 1,
            "joint_or_surviving_count": 1,
            "head_of_household_count": 1,
            "single_or_separate_count": 1,
        }
    }


def test_illinois_projection_diagnostics_pin_completed_boundaries() -> None:
    prefix = "us-il:policies/income_tax/pilot_liability_pipeline#input."
    routes = (
        TaxUnitRoute(1, 1, "IL", "17", 1, DISPOSITION_READY),
        TaxUnitRoute(2, 2, "IL", "17", 1, DISPOSITION_READY),
        TaxUnitRoute(3, 3, "IL", "17", 1, DISPOSITION_READY),
        TaxUnitRoute(4, 4, "IL", "17", 1, DISPOSITION_BLOCKED),
    )

    diagnostics = campaign._projection_branch_diagnostics(
        {
            "IL": {
                f"{prefix}il_pit_pilot_state_taxable_income": {
                    1: 0.0,
                    2: 100.0,
                    3: 200.0,
                    4: 300.0,
                },
                f"{prefix}il_pit_pilot_recapture_of_investment_credit": {
                    1: 0.0,
                    2: 0.0,
                    3: 25.0,
                    4: 50.0,
                },
            }
        },
        routes,
    )

    assert diagnostics == {
        "IL": {
            "compared_tax_unit_count": 3,
            "zero_taxable_income_count": 1,
            "positive_taxable_income_count": 2,
            "zero_recapture_count": 2,
            "positive_recapture_count": 1,
        }
    }


def test_indiana_projection_diagnostics_pin_agi_and_output_branches() -> None:
    slot = (
        "us-in:policies/income_tax/pilot_liability_pipeline#input."
        "in_pit_pilot_indiana_adjusted_gross_income"
    )
    routes = (
        TaxUnitRoute(1, 1, "IN", "18", 1, DISPOSITION_READY),
        TaxUnitRoute(2, 2, "IN", "18", 1, DISPOSITION_READY),
        TaxUnitRoute(3, 3, "IN", "18", 1, DISPOSITION_READY),
        TaxUnitRoute(4, 4, "IN", "18", 1, DISPOSITION_BLOCKED),
    )

    diagnostics = campaign._projection_branch_diagnostics(
        {
            "IN": {
                slot: {
                    1: -100.0,
                    2: 0.0,
                    3: 10_000.0,
                    4: 20_000.0,
                }
            }
        },
        routes,
        {
            "IN": {
                1: 0.0,
                2: 0.0,
                3: 295.0,
                4: 590.0,
            }
        },
    )

    assert diagnostics == {
        "IN": {
            "compared_tax_unit_count": 3,
            "nonpositive_agi_count": 2,
            "positive_agi_count": 1,
            "zero_output_count": 2,
            "positive_output_count": 1,
        }
    }


def test_indiana_projection_diagnostics_require_exact_target_inventory() -> None:
    slot = (
        "us-in:policies/income_tax/pilot_liability_pipeline#input."
        "in_pit_pilot_indiana_adjusted_gross_income"
    )
    with pytest.raises(ValueError, match="target values"):
        campaign._projection_branch_diagnostics(
            {"IN": {slot: {1: 100.0}}},
            (TaxUnitRoute(1, 1, "IN", "18", 1, DISPOSITION_READY),),
        )


def test_pennsylvania_projection_diagnostics_pin_nonnegative_boundary_and_output() -> None:
    slot = (
        "us-pa:policies/income_tax/pilot_liability_pipeline#input."
        "pa_pit_pilot_state_taxable_income"
    )
    routes = (
        TaxUnitRoute(1, 1, "PA", "42", 1, DISPOSITION_READY),
        TaxUnitRoute(2, 2, "PA", "42", 1, DISPOSITION_READY),
        TaxUnitRoute(3, 3, "PA", "42", 1, DISPOSITION_READY),
        TaxUnitRoute(4, 4, "PA", "42", 1, DISPOSITION_BLOCKED),
    )

    diagnostics = campaign._projection_branch_diagnostics(
        {
            "PA": {
                slot: {
                    1: 0.0,
                    2: 100.0,
                    3: 200.0,
                    4: -1.0,
                }
            }
        },
        routes,
        {
            "PA": {
                1: 0.0,
                2: 3.07,
                3: 6.14,
                4: -0.0307,
            }
        },
    )

    assert diagnostics == {
        "PA": {
            "compared_tax_unit_count": 3,
            "negative_adjusted_taxable_income_count": 0,
            "zero_adjusted_taxable_income_count": 1,
            "positive_adjusted_taxable_income_count": 2,
            "zero_output_count": 1,
            "positive_output_count": 2,
        }
    }


def test_pennsylvania_projection_diagnostics_require_exact_target_inventory() -> None:
    slot = (
        "us-pa:policies/income_tax/pilot_liability_pipeline#input."
        "pa_pit_pilot_state_taxable_income"
    )
    with pytest.raises(ValueError, match="target values"):
        campaign._projection_branch_diagnostics(
            {"PA": {slot: {1: 100.0}}},
            (TaxUnitRoute(1, 1, "PA", "42", 1, DISPOSITION_READY),),
        )


@pytest.mark.parametrize(
    ("taxable", "target", "message"),
    [
        (-1.0, 0.0, "nonnegative adjusted taxable income"),
        (0.0, -1.0, "nonnegative before-forgiveness tax"),
    ],
)
def test_pennsylvania_projection_diagnostics_reject_negative_values(
    taxable,
    target,
    message,
) -> None:
    slot = (
        "us-pa:policies/income_tax/pilot_liability_pipeline#input."
        "pa_pit_pilot_state_taxable_income"
    )
    with pytest.raises(ValueError, match=message):
        campaign._projection_branch_diagnostics(
            {"PA": {slot: {1: taxable}}},
            (TaxUnitRoute(1, 1, "PA", "42", 1, DISPOSITION_READY),),
            {"PA": {1: target}},
        )


def test_south_carolina_projection_diagnostics_pin_nonnegative_boundary_and_output() -> None:
    slot = (
        "us-sc:policies/income_tax/pilot_liability_pipeline#input."
        "sc_pit_pilot_state_taxable_income"
    )
    routes = (
        TaxUnitRoute(1, 1, "SC", "45", 1, DISPOSITION_READY),
        TaxUnitRoute(2, 2, "SC", "45", 1, DISPOSITION_READY),
        TaxUnitRoute(3, 3, "SC", "45", 1, DISPOSITION_READY),
        TaxUnitRoute(4, 4, "SC", "45", 1, DISPOSITION_BLOCKED),
    )

    diagnostics = campaign._projection_branch_diagnostics(
        {
            "SC": {
                slot: {
                    1: 0.0,
                    2: 30_000.0,
                    3: 100_000.0,
                    4: -1.0,
                }
            }
        },
        routes,
        {
            "SC": {
                1: 0.0,
                2: 596.81,
                3: 4_281.0,
                4: 0.0,
            }
        },
    )

    assert diagnostics == {
        "SC": {
            "compared_tax_unit_count": 3,
            "negative_taxable_income_count": 0,
            "zero_taxable_income_count": 1,
            "positive_taxable_income_count": 2,
            "zero_output_count": 1,
            "positive_output_count": 2,
        }
    }


def test_south_carolina_projection_diagnostics_require_exact_target_inventory() -> None:
    slot = (
        "us-sc:policies/income_tax/pilot_liability_pipeline#input."
        "sc_pit_pilot_state_taxable_income"
    )
    with pytest.raises(ValueError, match="target values"):
        campaign._projection_branch_diagnostics(
            {"SC": {slot: {1: 100.0}}},
            (TaxUnitRoute(1, 1, "SC", "45", 1, DISPOSITION_READY),),
        )


@pytest.mark.parametrize(
    ("taxable", "target", "message"),
    [
        (-1.0, 0.0, "nonnegative South Carolina taxable income"),
        (0.0, -1.0, "nonnegative tax before nonrefundable credits"),
    ],
)
def test_south_carolina_projection_diagnostics_reject_negative_values(
    taxable,
    target,
    message,
) -> None:
    slot = (
        "us-sc:policies/income_tax/pilot_liability_pipeline#input."
        "sc_pit_pilot_state_taxable_income"
    )
    with pytest.raises(ValueError, match=message):
        campaign._projection_branch_diagnostics(
            {"SC": {slot: {1: taxable}}},
            (TaxUnitRoute(1, 1, "SC", "45", 1, DISPOSITION_READY),),
            {"SC": {1: target}},
        )


@pytest.mark.parametrize(
    ("taxable", "recapture", "message"),
    [
        (-1.0, 0.0, "nonnegative completed taxable income"),
        (0.0, -1.0, "nonnegative completed investment-credit recapture"),
    ],
)
def test_illinois_projection_diagnostics_reject_negative_boundaries(
    taxable,
    recapture,
    message,
) -> None:
    prefix = "us-il:policies/income_tax/pilot_liability_pipeline#input."
    with pytest.raises(ValueError, match=message):
        campaign._projection_branch_diagnostics(
            {
                "IL": {
                    f"{prefix}il_pit_pilot_state_taxable_income": {
                        1: taxable
                    },
                    f"{prefix}il_pit_pilot_recapture_of_investment_credit": {
                        1: recapture
                    },
                }
            },
            (TaxUnitRoute(1, 1, "IL", "17", 1, DISPOSITION_READY),),
        )


@pytest.mark.parametrize(
    ("joint", "head", "message"),
    [
        (1, False, "strict Boolean"),
        (True, True, "mutually exclusive"),
    ],
)
def test_new_york_projection_diagnostics_reject_invalid_schedule_values(
    joint,
    head,
    message,
) -> None:
    prefix = "us-ny:policies/income_tax/pilot_liability_pipeline#input."
    with pytest.raises(ValueError, match=message):
        campaign._projection_branch_diagnostics(
            {
                "NY": {
                    f"{prefix}ny_pit_pilot_state_taxable_income": {1: 1.0},
                    (
                        f"{prefix}"
                        "ny_pit_pilot_filing_status_joint_or_surviving_spouse"
                    ): {1: joint},
                    (
                        f"{prefix}"
                        "ny_pit_pilot_filing_status_head_of_household"
                    ): {1: head},
                }
            },
            (TaxUnitRoute(1, 1, "NY", "36", 1, DISPOSITION_READY),),
        )
