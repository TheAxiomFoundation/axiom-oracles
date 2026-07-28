import pytest

from axiom_oracles.adapters.policyengine import PolicyEngineRunner
from axiom_oracles.core.case import Case, Concepts, Entity


def test_policyengine_runner_uses_requested_month_across_october_snap_cola() -> None:
    pytest.importorskip("policyengine")
    pytest.importorskip("policyengine_us")

    runner = PolicyEngineRunner(batch_size=1)
    expected = {
        "2026-01": {
            "snap_min_allotment": 23.84000015258789,
            "snap_max_allotment": 298.0,
        },
        "2026-10": {
            "snap_min_allotment": 24.3743953704834,
            "snap_max_allotment": 304.6799621582031,
        },
    }
    actual = {}

    for period, period_expected in expected.items():
        case = Case(
            case_id=f"snap-cola-{period}",
            period=period,
            facts={Concepts.STATE_CODE: "MA"},
            entities=(
                Entity(
                    entity_id="head",
                    kind="person",
                    facts={Concepts.PERSON_AGE: 70},
                ),
            ),
        )

        result = runner.run_cases(
            [case],
            variables=[
                "snap_min_allotment",
                "snap_max_allotment",
                "snap_standard_deduction",
            ],
        )[0]
        actual[period] = result.values

        assert result.errors == ()
        assert result.values["snap_min_allotment"] == pytest.approx(
            period_expected["snap_min_allotment"]
        )
        assert result.values["snap_max_allotment"] == pytest.approx(
            period_expected["snap_max_allotment"]
        )
        if period == "2026-01":
            assert result.values["snap_standard_deduction"] == pytest.approx(209.0)

    assert actual["2026-01"] != actual["2026-10"]
    calendar_average = 287.68316650390625 / 12
    assert actual["2026-01"]["snap_min_allotment"] != pytest.approx(calendar_average)
    assert actual["2026-10"]["snap_min_allotment"] != pytest.approx(calendar_average)

    alaska_case = Case(
        case_id="snap-alaska-2026-01",
        period="2026-01",
        facts={Concepts.STATE_CODE: "AK"},
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={Concepts.PERSON_AGE: 70},
            ),
        ),
    )
    alaska_result = runner.run_cases(
        [alaska_case],
        variables=["snap_min_allotment", "snap_max_allotment"],
    )[0]

    assert alaska_result.values["snap_min_allotment"] == pytest.approx(30.8)
    assert alaska_result.values["snap_max_allotment"] == pytest.approx(385.0)


def test_unknown_definition_period_fails_closed(monkeypatch) -> None:
    """An undetermined definition period must never serve the annual value.

    With every lookup unavailable, a numeric variable requested for a month
    previously fell through the != "month" branch and returned the annual
    output-dataset sum (e.g. al_tanf 3,648 instead of 304).
    """
    from axiom_oracles.adapters.policyengine import runner as runner_module

    monkeypatch.setattr(
        runner_module,
        "_policyengine_definition_period",
        lambda pe, variable: "",
    )
    monkeypatch.setattr(
        runner_module,
        "_policyengine_variable_is_boolean",
        lambda pe, variable, value: False,
    )
    monkeypatch.setattr(
        runner_module,
        "_policyengine_metadata_available",
        lambda pe: True,
    )
    with pytest.raises(RuntimeError, match="definition period"):
        runner_module._normalize_value_for_requested_period(
            object(),
            "al_tanf",
            "2026-01",
            3648.0,
        )
    # A year request never consults the definition period and stays untouched.
    assert (
        runner_module._normalize_value_for_requested_period(
            object(),
            "al_tanf",
            "2026",
            3648.0,
        )
        == 3648.0
    )


def test_metadata_less_stub_engines_stay_year_shaped(monkeypatch) -> None:
    """Without any metadata source, outputs pass through as year-shaped."""
    from axiom_oracles.adapters.policyengine import runner as runner_module

    monkeypatch.setattr(
        runner_module,
        "_policyengine_definition_period",
        lambda pe, variable: "",
    )
    monkeypatch.setattr(
        runner_module,
        "_policyengine_variable_is_boolean",
        lambda pe, variable, value: False,
    )
    monkeypatch.setattr(
        runner_module,
        "_policyengine_metadata_available",
        lambda pe: False,
    )
    assert (
        runner_module._normalize_value_for_requested_period(
            object(),
            "income_tax",
            "2026-05",
            3820.0,
        )
        == 3820.0
    )
