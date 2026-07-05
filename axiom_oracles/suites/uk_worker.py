from __future__ import annotations

from ..core.case import Case, Concepts, Entity


UK_SCOPE = {"type": "country", "geoid": "UK"}
UK_METADATA = {
    "locale": "UK",
    "scope": UK_SCOPE,
    "axiom_entity": "Person",
    "axiom_entity_id": "head",
}
PIT_MODULE = "uk:statutes/income_tax/individual/pilot_worker_oracle_pipeline"
NIC_MODULE = "uk:statutes/social_security/workers/pilot_worker_class_1_nic_pipeline"
EUROMOD_TO_AXIOM_INPUT_BRIDGE = "euromod_to_axiom_input_bridge"

# The composed pilot pipelines are effective from the 2026-27 tax year, where
# every rate/threshold is imported from a grounded module (Finance Act 2026
# main rates, s10/s35 limits). 2025-26 and 2026-27 share frozen thresholds and
# rates, so UKMOD UK_2025 and UK_2026 return identical values for these cases.
UK_WORKER_PERIOD = "2026"

# Single-employee gross-employment-income grid. 130k and 360k exercise full
# personal-allowance withdrawal and the additional rate; 60k+ exercise the
# higher-rate band; all exercise the NIC main band and 50,270+ the additional
# NIC band.
_WORKER_INCOME_GRID: tuple[tuple[str, float], ...] = (
    ("30k", 30_000.0),
    ("45k", 45_000.0),
    ("60k", 60_000.0),
    ("130k", 130_000.0),
    ("360k", 360_000.0),
)


def uk_worker_pit_cases() -> list[Case]:
    """Single-employee UK income-tax cases for the UKMOD UK_2026 oracle."""

    return [
        _single_worker_pit_case(f"uk-worker-pit-{label}", income)
        for label, income in _WORKER_INCOME_GRID
    ]


def uk_worker_nic_cases() -> list[Case]:
    """Single-employee UK employee-NIC cases for the UKMOD UK_2026 oracle."""

    return [
        _single_worker_nic_case(f"uk-worker-nic-{label}", income)
        for label, income in _WORKER_INCOME_GRID
    ]


def _single_worker_pit_case(case_id: str, annual_income: float) -> Case:
    income_input = _pit_input("uk_pit_pilot_annual_employment_income")
    return _single_worker_case(
        case_id,
        annual_income,
        output=Concepts.UK_WORKER_INCOME_TAX_LIABILITY,
        axiom_inputs={
            income_input: annual_income,
            _pit_input("uk_pit_pilot_supplied_section_24_reliefs"): 0,
        },
        metadata_extra={
            "scenario": "single-worker-pit",
            "yearly_earned_income": annual_income,
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yem": [income_input],
            },
        },
    )


def _single_worker_nic_case(case_id: str, annual_income: float) -> Case:
    income_input = _nic_input("uk_nic_pilot_annual_employment_income")
    return _single_worker_case(
        case_id,
        annual_income,
        output=Concepts.UK_WORKER_CLASS_1_EMPLOYEE_NIC,
        axiom_inputs={
            income_input: annual_income,
        },
        metadata_extra={
            "scenario": "single-worker-nic",
            "yearly_earned_income": annual_income,
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yem": [income_input],
            },
        },
    )


def _single_worker_case(
    case_id: str,
    annual_income: float,
    *,
    output: str | tuple[str, ...],
    axiom_inputs: dict[str, float | bool],
    metadata_extra: dict[str, object],
) -> Case:
    outputs = output if isinstance(output, tuple) else (output,)
    return Case(
        case_id=case_id,
        period=UK_WORKER_PERIOD,
        metadata={
            **UK_METADATA,
            **metadata_extra,
            "axiom_inputs": axiom_inputs,
            "euromod_inputs": [_euromod_worker_input(annual_income)],
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 35,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.YEARLY_EARNED_INCOME: annual_income,
                },
            ),
        ),
        outputs=outputs,
    )


def _pit_input(name: str) -> str:
    return f"{PIT_MODULE}#input.{name}"


def _nic_input(name: str) -> str:
    return f"{NIC_MODULE}#input.{name}"


def _euromod_worker_input(annual_income: float) -> dict[str, float | int]:
    employed = annual_income > 0
    return {
        "idperson": 101,
        "idpartner": 0,
        "idmother": 0,
        "idfather": 0,
        "dag": 35,
        "dgn": 1,
        "dms": 1,
        "les": 3 if employed else 0,
        "lfs": 15 if employed else 0,
        "lhw": 38 if employed else 0,
        "liwmy": 12 if employed else 0,
        "liwwh": 120 if employed else 0,
        "yem": annual_income / 12,
        "yemmy": 12 if employed else 0,
    }
