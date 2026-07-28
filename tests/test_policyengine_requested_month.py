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
            variables=["snap_min_allotment", "snap_max_allotment"],
        )[0]
        actual[period] = result.values

        assert result.errors == ()
        assert result.values["snap_min_allotment"] == pytest.approx(
            period_expected["snap_min_allotment"]
        )
        assert result.values["snap_max_allotment"] == pytest.approx(
            period_expected["snap_max_allotment"]
        )

    assert actual["2026-01"] != actual["2026-10"]
    calendar_average = 287.68316650390625 / 12
    assert actual["2026-01"]["snap_min_allotment"] != pytest.approx(calendar_average)
    assert actual["2026-10"]["snap_min_allotment"] != pytest.approx(calendar_average)
