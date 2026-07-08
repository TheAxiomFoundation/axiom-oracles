"""Tests for the SNAP QC comparison bridge.

The ``map_qc_unit`` tests construct QC-shaped objects directly (per the frozen
contract fields) so they do not depend on Lane A's ``populations.snap_qc``. The
engine-gated live test reproduces the proven worked example through the real
overlay builder, ``map_qc_unit``, and run path.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from axiom_oracles.bridges import snap_populace, snap_qc_compare as sc
from axiom_oracles.bridges.rulespec_overlay import (
    build_overlay,
    load_overlay_spec,
    rewrite_output_ids,
)
from axiom_oracles.comparison.report import COMPARISON_REPORT_SCHEMA_VERSION

# --------------------------------------------------------------------------- #
# Legal-reference input keys the projection writes (subset of the CO template).
# --------------------------------------------------------------------------- #

CO = "us-co:regulations/10-ccr-2506-1"
COMP = "us-co:policies/cdhs/snap/fy-2026-benefit-calculation"
EARNED = f"{COMP}#input.snap_countable_earned_income"
SHELTER = f"{COMP}#input.household_shelter_costs_incurred"
SIZE = f"{CO}/4.207.3#input.household_size"
CATEG = f"{CO}/4.207.3#input.snap_basic_categorical_eligible"
RET = f"{CO}/4.404#input.retirement_disability_payments"
ASSIST = f"{CO}/4.404#input.assistance_payments"
DIRECT = f"{CO}/4.404#input.direct_support_and_alimony_payments"
OTHER = f"{CO}/4.404#input.other_gain_or_benefit_payments"
HEAT = (
    f"{CO}/4.407.31#input."
    "household_incurred_or_anticipated_heating_or_cooling_costs_separate_from_"
    "rent_or_mortgage"
)
ELEC = f"{CO}/4.407.31#input.household_pays_electricity_utility_cost"
WATER = f"{CO}/4.407.31#input.household_pays_water_utility_cost"
SEWER = f"{CO}/4.407.31#input.household_pays_sewer_utility_cost"
TRASH = f"{CO}/4.407.31#input.household_pays_trash_utility_cost"
COOK = f"{CO}/4.407.31#input.household_pays_cooking_fuel_utility_cost"
PHONE = f"{CO}/4.407.31#input.household_pays_telephone_service_cost"
DEPCARE_NEC = f"{CO}/4.407.4#input.dependent_care_expense_necessary_for_work_or_training"
DEPCARE_PAID = f"{CO}/4.407.4#input.dependent_care_expenses_paid"
CS_VERIFIED = f"{CO}/4.407.5#input.child_support_payment_verified"
CS_MONTHS = f"{CO}/4.407.5#input.child_support_payment_history_months"
CS_AVG = f"{CO}/4.407.5#input.average_monthly_child_support_paid"
MEDICAL = f"{CO}/4.407.6#input.total_medical_expenses"
LIQUID = f"{CO}/4.408.1#input.liquid_resource_current_redemption_rate"
ELDERLY = "us:statutes/7/2012/j#input.snap_member_is_elderly_or_disabled"
MEMBER_AGE_7 = "us:regulations/7-cfr/273/7#input.member_age"
MEMBER_AGE_24 = "us:regulations/7-cfr/273/24#input.member_age"

_UTILITY_KEYS = (HEAT, ELEC, WATER, SEWER, TRASH, COOK, PHONE)


def _base_inputs() -> dict:
    keys = [
        EARNED, SHELTER, SIZE, CATEG, RET, ASSIST, DIRECT, OTHER,
        DEPCARE_NEC, DEPCARE_PAID, CS_VERIFIED, CS_MONTHS, CS_AVG, MEDICAL, LIQUID,
    ]
    base = {key: 0 for key in keys}
    base[CATEG] = False
    base[DEPCARE_NEC] = False
    base[CS_VERIFIED] = False
    # Template default has the heating flag on; the projection must set all seven.
    base.update({flag: False for flag in _UTILITY_KEYS})
    base[HEAT] = True
    base[f"{CO}/4.407.4#input.dependent_care_reimbursed_or_paid_by_other_program"] = 0
    base[f"{CO}/4.407.5#input.estimated_monthly_child_support_paid"] = 0
    # Homeless shelter deduction flags (10 CCR 2506-1 section 4.407.3), present
    # in the composition test template with false defaults.
    base[f"{CO}/4.407.3#input.all_household_members_experiencing_homelessness"] = False
    base[f"{CO}/4.407.3#input.homeless_household_has_shelter_costs"] = False
    base[f"{CO}/4.407.3#input.homeless_household_free_shelter_all_month"] = False
    base[f"{CO}/4.407.3#input.verified_higher_homeless_shelter_costs"] = False
    return base


def _base_member() -> dict:
    return {ELDERLY: False, MEMBER_AGE_7: 60, MEMBER_AGE_24: 60}


def _member(**kwargs):
    values = {
        "index": 0,
        "age": 40,
        "elderly_or_disabled": False,
        "social_security": 0.0,
        "ssi": 0.0,
        "tanf": 0.0,
        "general_assistance": 0.0,
        "child_support": 0.0,
        "alimony": 0.0,
        "_earned": 0.0,
        "_unearned": 0.0,
    }
    values.update(kwargs)
    earned = values.pop("_earned")
    unearned = values.pop("_unearned")
    return SimpleNamespace(
        earned_income=lambda earned=earned: earned,
        unearned_income=lambda unearned=unearned: unearned,
        **values,
    )


#: The per-tier standard amounts come from the shipped overlay spec — the same
#: single source the run path derives them from — so the tests can never pin a
#: stale copy of the FY 2024 values.
_SUA_AMOUNTS = sc.sua_amounts_from_overlay(load_overlay_spec("us-co-snap-fy2024"))


def _unit(**kwargs):
    values = {
        "case_id": "2024-202401-7",
        "yrmonth": 202401,
        "certified_size": 1,
        "shelter_expense": 500.0,
        "utility_tier": "heating_cooling",
        "medical_expenses": 0.0,
        "dependent_care_expense": 0.0,
        "child_support_expense": 0.0,
        "categorically_eligible": False,
        "homeless_deduction_claimed": False,
        "liquid_resources": 0.0,
        "weight": 1.0,
        "members": [_member(_earned=1000.0)],
        "expected": SimpleNamespace(benefit=291, medical_deduction=None),
    }
    values.update(kwargs)
    # The QC-applied allowance defaults to the tier's FY 2024 standard so the
    # tier flags are exercised; override utility_amount to test the raw path.
    # Computed lazily: an unknown tier must reach the mapper's own error, and
    # an explicit utility_amount must not evaluate the table lookup at all.
    if "utility_amount" not in values:
        tier = str(getattr(values["utility_tier"], "value", values["utility_tier"]))
        values["utility_amount"] = _SUA_AMOUNTS[tier]
    members = values["members"]
    values.setdefault(
        "earned_income",
        lambda members=members: sum(m.earned_income() for m in members),
    )
    values.setdefault(
        "unearned_income",
        lambda members=members: sum(m.unearned_income() for m in members),
    )
    return SimpleNamespace(**values)


def _map(unit, base_inputs=None, base_member=None):
    return sc.map_qc_unit(
        unit,
        base_inputs if base_inputs is not None else _base_inputs(),
        base_member if base_member is not None else _base_member(),
        sua_amount_by_tier=_SUA_AMOUNTS,
    )


# --------------------------------------------------------------------------- #
# map_qc_unit golden tests
# --------------------------------------------------------------------------- #


def test_map_qc_unit_projects_household_and_member_facts() -> None:
    case = _map(_unit())
    inputs = case.inputs
    assert inputs[EARNED] == 1000
    assert inputs[SIZE] == 1
    assert inputs[SHELTER] == 500
    assert inputs[CATEG] is False
    assert inputs[LIQUID] == 0
    assert inputs[RET] == 0 and inputs[ASSIST] == 0
    assert inputs[DIRECT] == 0 and inputs[OTHER] == 0
    # Utility tier heating_cooling -> only the heating/cooling flag is true.
    assert inputs[HEAT] is True
    assert all(inputs[flag] is False for flag in _UTILITY_KEYS if flag != HEAT)
    # Work-requirement member age pinned to 60 (exempt); elderly flag off.
    member = case.member_inputs[0]
    assert member[MEMBER_AGE_7] == 60
    assert member[MEMBER_AGE_24] == 60
    assert member[ELDERLY] is False


def test_map_qc_unit_itemizes_unearned_into_4_404_categories() -> None:
    member = _member(
        social_security=100.0,
        ssi=50.0,
        tanf=30.0,
        general_assistance=20.0,
        child_support=40.0,
        _earned=0.0,
        _unearned=300.0,
    )
    inputs = _map(_unit(members=[member])).inputs
    assert inputs[RET] == 150  # social security + SSI
    assert inputs[ASSIST] == 50  # TANF + GA
    assert inputs[DIRECT] == 40  # child support received
    assert inputs[OTHER] == 60  # remaining unearned (300 - 150 - 50 - 40)


@pytest.mark.parametrize(
    "tier, expected_true",
    [
        ("heating_cooling", {HEAT}),
        ("limited", {ELEC, WATER}),
        ("one_utility", {ELEC}),
        ("telephone", {PHONE}),
        ("none", set()),
    ],
)
def test_map_qc_unit_utility_tiers(tier, expected_true) -> None:
    inputs = _map(_unit(utility_tier=tier)).inputs
    for flag in _UTILITY_KEYS:
        assert inputs[flag] is (flag in expected_true), flag


@pytest.mark.parametrize(
    "excess, projected",
    [(0.0, 0), (20.0, 55), (165.0, 200), (325.0, 360)],
)
def test_map_qc_unit_medical_excess_plus_threshold(excess, projected) -> None:
    # FSMEDEXP is the allowable expense in excess of $35 and the QC
    # recomputation sets FSMEDDED = MAX(0, FSMEDEXP), so the mapper feeds
    # excess + 35 and the engine's total - 35 reproduces FSMEDDED exactly.
    inputs = _map(_unit(medical_expenses=excess)).inputs
    assert inputs[MEDICAL] == projected


def test_map_qc_unit_homeless_deduction_claim_sets_flat_path() -> None:
    inputs = _map(
        _unit(homeless_deduction_claimed=True, utility_tier="telephone"),
    ).inputs
    homeless_flag = f"{CO}/4.407.3#input.all_household_members_experiencing_homelessness"
    has_costs = f"{CO}/4.407.3#input.homeless_household_has_shelter_costs"
    assert inputs[homeless_flag] is True
    assert inputs[has_costs] is True
    # The QC file zeroes FSSLTDED for HOMEDED = 3 units by construction, so no
    # utility flag is raised on the flat-deduction path.
    assert all(inputs[flag] is False for flag in _UTILITY_KEYS)


def test_map_qc_unit_nonstandard_utility_amount_rides_as_shelter_cost() -> None:
    # A prorated or actual-expense allowance (UTIL differing from the tier's
    # FY 2024 standard) is authoritative: no tier flag, amount added to the
    # incurred shelter costs.
    inputs = _map(
        _unit(utility_tier="heating_cooling", utility_amount=91.0),
    ).inputs
    assert all(inputs[flag] is False for flag in _UTILITY_KEYS)
    assert inputs[SHELTER] == 591


def test_expected_gross_nets_out_child_support_deduction() -> None:
    # Colorado elects the 7 USC 2014(e)(4) child-support income exclusion, so
    # the QC-recorded deduction is netted out of FSGRINC for the gross label.
    # In deduction states FSCSDED equals FSCSEXP; in exclusion states FSCSDED
    # is 0 and the netting is skipped — the FY2024 file has no partial rows.
    label = next(
        label for label in sc._LABELS if label.expected_attr == "gross_income"
    )
    unit = _unit(
        expected=SimpleNamespace(
            benefit=81, gross_income=1469.0, child_support_deduction=281.0
        )
    )
    assert sc._expected_value(label, unit) == 1188.0


def test_map_qc_unit_missing_utility_amount_presumes_tier_standard() -> None:
    # A recorded tier with a blank UTIL cell means the standard applied (the
    # codebook edited SUA1 for consistency with UTIL), so the tier flags stay
    # raised and nothing rides as an incurred cost.
    inputs = _map(_unit(utility_tier="heating_cooling", utility_amount=None)).inputs
    assert inputs[HEAT] is True
    assert inputs[SHELTER] == 500


def test_map_qc_unit_accepts_utility_tier_enum_instances() -> None:
    from axiom_oracles.populations.snap_qc import UtilityTier

    inputs = _map(
        _unit(
            utility_tier=UtilityTier.TELEPHONE,
            utility_amount=_SUA_AMOUNTS["telephone"],
        )
    ).inputs
    assert inputs[PHONE] is True
    assert all(inputs[flag] is False for flag in _UTILITY_KEYS if flag != PHONE)


def test_map_qc_unit_unknown_tier_raises() -> None:
    with pytest.raises(ValueError, match="unknown SNAP QC utility tier"):
        _map(_unit(utility_tier="jacuzzi", utility_amount=0.0))


def test_map_qc_unit_alimony_joins_direct_support() -> None:
    member = _member(child_support=40.0, alimony=25.0, _unearned=100.0)
    inputs = _map(_unit(members=[member])).inputs
    assert inputs[DIRECT] == 65  # child support received plus alimony
    assert inputs[OTHER] == 35  # 100 - 65


def test_map_qc_unit_missing_certified_size_raises() -> None:
    with pytest.raises(ValueError, match="certified size"):
        _map(_unit(certified_size=None))


def test_map_qc_unit_medical_feeds_applied_deduction() -> None:
    # The engine input reconstructs the deduction FNS applied (FSMEDDED plus
    # the $35 threshold): in standard-medical-deduction demonstration states
    # FSMEDDED is a flat standard that differs from the excess FSMEDEXP, so
    # FSMEDDED is the operative amount (10 such rows in FY2024, none in CO).
    unit = _unit(
        medical_expenses=130.0,
        expected=SimpleNamespace(benefit=291, medical_deduction=135.0),
    )
    assert _map(unit).inputs[MEDICAL] == 170  # 135 + 35


def test_validate_months_rejects_calendar_month_integers() -> None:
    with pytest.raises(ValueError, match="YRMONTH"):
        sc._validate_months((1, 2, 3), 2024)
    sc._validate_months((202310, 202409), 2024)


def test_sua_amounts_from_overlay_requires_all_four_patches() -> None:
    spec = SimpleNamespace(
        name="partial",
        parameter_patches=[
            SimpleNamespace(
                rule="colorado_snap_heating_cooling_utility_allowance_amount",
                to_value="560",
            )
        ],
    )
    with pytest.raises(ValueError, match="does not patch"):
        sc.sua_amounts_from_overlay(spec)


@pytest.mark.parametrize(
    "age, elderly_flag, expected",
    [(40, False, False), (65, False, True), (40, True, True), (None, False, False)],
)
def test_map_qc_unit_elderly_or_disabled_flag(age, elderly_flag, expected) -> None:
    member = _member(age=age, elderly_or_disabled=elderly_flag, _earned=1000.0)
    inputs = _map(_unit(members=[member]))
    assert inputs.member_inputs[0][ELDERLY] is expected


def test_map_qc_unit_projects_dependent_care_and_child_support_expense() -> None:
    inputs = _map(
        _unit(dependent_care_expense=120.0, child_support_expense=80.0),
    ).inputs
    assert inputs[DEPCARE_NEC] is True
    assert inputs[DEPCARE_PAID] == 120
    assert inputs[CS_VERIFIED] is True
    assert inputs[CS_MONTHS] == 3
    assert inputs[CS_AVG] == 80


# --------------------------------------------------------------------------- #
# Report shape test (stubbed engine results)
# --------------------------------------------------------------------------- #


def _decimal(value: float) -> dict:
    return {"kind": "decimal", "value": str(value)}


def _result(output_id_by_label: dict, values: dict) -> dict:
    outputs = {
        output_id_by_label[label]: {"id": output_id_by_label[label], "value": _decimal(v)}
        for label, v in values.items()
    }
    return {"outputs": outputs}


def _expected(benefit, gross, net, std, shelter, minimum=False):
    return SimpleNamespace(
        benefit=benefit,
        gross_income=gross,
        net_income=net,
        standard_deduction=std,
        shelter_deduction=shelter,
        received_minimum_benefit=minimum,
    )


def test_build_report_has_v2_shape_and_localizes_first_divergent_stage() -> None:
    output_id_by_label = {label.label: f"oid://{label.label}" for label in sc._LABELS}
    units = [
        SimpleNamespace(
            case_id="2024-202401-1",
            yrmonth=202401,
            weight=10.0,
            certified_size=1,
            expected=_expected(291, 1000, 0, 198, 672),
        ),
        SimpleNamespace(
            case_id="2024-202401-2",
            yrmonth=202401,
            weight=30.0,
            certified_size=1,
            expected=_expected(200, 900, 0, 198, 672),
        ),
    ]
    results = [
        _result(
            output_id_by_label,
            {
                "snap_gross_monthly_income": 1000,
                "snap_standard_deduction": 198,
                "snap_excess_shelter_deduction": 672,
                "snap_net_income": 0,
                "snap_maximum_allotment": 291,
                "snap_regular_month_allotment": 291,
            },
        ),
        _result(
            output_id_by_label,
            {
                "snap_gross_monthly_income": 1000,  # diverges from expected 900
                "snap_standard_deduction": 198,
                "snap_excess_shelter_deduction": 672,
                "snap_net_income": 0,
                "snap_maximum_allotment": 291,
                "snap_regular_month_allotment": 291,  # diverges from expected 200
            },
        ),
    ]
    exclusion_log = SimpleNamespace(
        total_loaded=5, total_excluded=1, counts={"mfip_unit": 1}
    )
    overlay_build = SimpleNamespace(provenance={"overlay": "us-co-snap-fy2024"})
    report = sc._build_report(
        units=units,
        results=results,
        output_id_by_label=output_id_by_label,
        jurisdiction="us-co",
        fiscal_year=2024,
        tolerance=0.0,
        stage_tolerance=1.0,
        exclusion_log=exclusion_log,
        period=snap_populace.month_period(2026, 1),
        overlay_build=overlay_build,
        rulespec_root=Path("/rulespec-us"),
        axiom_binary=Path("/engine"),
        pins=None,
    )

    assert set(report) == {
        "aggregates", "case_count", "cases", "concepts", "engines", "errors",
        "locales", "mismatches", "population", "provenance", "schema_version",
        "scope", "suite", "summary",
    }
    assert report["schema_version"] == COMPARISON_REPORT_SCHEMA_VERSION
    assert report["suite"] == "co-snap-qc"
    assert report["engines"] == {"left": "snap-qc", "right": "axiom"}
    assert report["locales"] == ["US-CO"]
    assert report["case_count"] == 2

    summary = report["summary"]
    assert summary["match_count"] == 1
    assert summary["mismatch_count"] == 1
    assert summary["match_rate"] == 50
    assert summary["weighted"]["match_rate"] == 25  # 10 / (10 + 30)
    assert summary["stages"] == [{"stage": "gross_income", "count": 1}]
    assert summary["exclusions"] == {
        "total_loaded": 5,
        "total_excluded": 1,
        "by_reason": {"mfip_unit": 1},
    }
    provenance = summary["provenance"]
    assert provenance["overlay"] == {"overlay": "us-co-snap-fy2024"}
    assert provenance["period"] == "2026-01"
    assert provenance["axiom_binary"] == "/engine"
    assert "759" in provenance["period_rationale"]

    assert len(report["mismatches"]) == 1
    mismatch = report["mismatches"][0]
    assert mismatch["qc_case_id"] == "2024-202401-2"
    assert mismatch["yrmonth"] == 202401
    assert mismatch["weight"] == 30
    assert mismatch["stage"] == "gross_income"
    assert mismatch["kind"] == "amount_difference"
    assert mismatch["received_minimum_benefit"] is False
    assert mismatch["difference"] == -91  # left (QC 200) minus right (axiom 291)
    assert mismatch["axiom"]["gross_income"] == 1000
    assert mismatch["qc"]["gross_income"] == 900

    labels = {label.label for label in sc._LABELS}
    assert {row["concept"] for row in report["aggregates"]} == {
        output_id_by_label[label] for label in labels
    }
    benefit_row = next(
        row
        for row in report["aggregates"]
        if row["concept"] == output_id_by_label["snap_regular_month_allotment"]
    )
    assert benefit_row["match_rate"] == 50
    assert len(report["cases"]) == 2


# --------------------------------------------------------------------------- #
# Engine-gated live test: reproduce the proven worked example end to end
# --------------------------------------------------------------------------- #

_ENGINE = Path(
    os.environ.get(
        "AXIOM_RULES_ENGINE_BIN",
        "/Users/maxghenis/TheAxiomFoundation/axiom-rules-engine/target/release/"
        "axiom-rules-engine",
    )
)
_RULESPEC_FY2024 = Path(
    os.environ.get(
        "RULESPEC_US_SNAP_FY2024_ROOT",
        "/Users/maxghenis/TheAxiomFoundation/_worktrees/rulespec-us-snap-fy2024",
    )
)
_LIVE = _ENGINE.exists() and (
    _RULESPEC_FY2024 / "us/policies/usda/snap/fy-2024-cola"
).exists()


@pytest.mark.skipif(
    not _LIVE,
    reason="axiom-rules-engine binary and rulespec-us fy-2024-cola worktree required",
)
def test_live_engine_reproduces_worked_example(tmp_path: Path) -> None:
    config = sc.QC_JURISDICTIONS["us-co"]
    spec = load_overlay_spec(config.overlay)
    output_id_by_label = sc._output_id_by_label(config, spec.module_id_rewrites)
    # Diagnostic: also query the Colorado standard utility allowance (HCSUA 560).
    output_id_by_label = {
        **output_id_by_label,
        **rewrite_output_ids(
            {
                "snap_standard_utility_allowance": config.base.output_id_by_label[
                    "snap_standard_utility_allowance"
                ]
            },
            spec.module_id_rewrites,
        ),
    }

    base_inputs = snap_populace.load_base_inputs(_RULESPEC_FY2024 / config.template)
    base_member = sc._load_base_member(
        _RULESPEC_FY2024 / config.template, config.base.relation_id
    )

    unit = _unit(members=[_member(age=40, _earned=1000.0)], shelter_expense=500.0)

    overlay_dir = Path(tempfile.mkdtemp(prefix="snap-qc-live-", dir=tmp_path))
    build = build_overlay(spec, _RULESPEC_FY2024, overlay_dir)
    env = snap_populace.axiom_rules_env(build.program_path, _RULESPEC_FY2024.parent)
    env["AXIOM_RULESPEC_REPO_ROOTS"] = str(build.overlay_root)

    case = sc.map_qc_unit(
        unit,
        base_inputs,
        base_member,
        sua_amount_by_tier=sc.sua_amounts_from_overlay(spec),
    )
    results = sc._run_cases(
        binary=_ENGINE,
        program_path=build.program_path,
        cases=[case],
        period=snap_populace.month_period(*sc.NOMINAL_PERIOD),
        output_ids=list(output_id_by_label.values()),
        config=config,
        env=env,
    )

    references = snap_populace.outputs_by_reference(results[0]["outputs"])

    def value(label: str) -> float:
        output = references[output_id_by_label[label]]
        return float(snap_populace.output_to_python(output))

    assert value("snap_regular_month_allotment") == 291
    assert value("snap_net_income") == 0
    assert value("snap_excess_shelter_deduction") == 672
    assert value("snap_standard_deduction") == 198
    assert value("snap_maximum_allotment") == 291
    assert value("snap_standard_utility_allowance") == 560
