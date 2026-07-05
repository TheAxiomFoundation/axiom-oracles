from __future__ import annotations

from ..core.case import Case, Concepts, Entity


UK_SCOPE = {"type": "country", "geoid": "UK"}
UK_METADATA = {
    "locale": "UK",
    "scope": UK_SCOPE,
    "axiom_entity": "Person",
    "axiom_entity_id": "head",
}
PIT_MODULE = "uk:statutes/ukpga/2007/3/worker_oracle_pipeline"
NIC_MODULE = "uk:statutes/ukpga/1992/4/worker_oracle_pipeline"
EUROMOD_TO_AXIOM_INPUT_BRIDGE = "euromod_to_axiom_input_bridge"
WORKER_INCOMES = (30_000.0, 45_000.0, 60_000.0, 130_000.0, 360_000.0)


def uk_worker_pit_cases() -> list[Case]:
    """Single-worker UK PIT cases for the UKMOD UK_2025 oracle."""

    return [
        _single_worker_pit_case(f"uk-worker-pit-{_income_label(income)}", income)
        for income in WORKER_INCOMES
    ]


def uk_worker_nic_cases() -> list[Case]:
    """Single-worker UK employee-NIC cases for the UKMOD UK_2025 oracle."""

    return [
        _single_worker_nic_case(f"uk-worker-nic-{_income_label(income)}", income)
        for income in WORKER_INCOMES
    ]


def _single_worker_pit_case(case_id: str, annual_income: float) -> Case:
    gross_input = _pit_input("annual_gross_employment_income")
    return _single_worker_case(
        case_id,
        annual_income,
        output=Concepts.UK_INCOME_TAX,
        axiom_inputs={gross_input: annual_income},
        metadata_extra={
            "scenario": "single-worker-pit",
            "yearly_earned_income": annual_income,
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"yem": [gross_input]},
        },
    )


def _single_worker_nic_case(case_id: str, annual_income: float) -> Case:
    gross_input = _nic_input("annual_gross_employment_income")
    return _single_worker_case(
        case_id,
        annual_income,
        output=Concepts.UK_EMPLOYEE_NIC,
        axiom_inputs={gross_input: annual_income},
        metadata_extra={
            "scenario": "single-worker-nic",
            "yearly_earned_income": annual_income,
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"yem": [gross_input]},
        },
    )


def _single_worker_case(
    case_id: str,
    annual_income: float,
    *,
    output: str,
    axiom_inputs: dict[str, float],
    metadata_extra: dict[str, object],
) -> Case:
    return Case(
        case_id=case_id,
        period="2025",
        metadata={
            **UK_METADATA,
            **metadata_extra,
            "axiom_inputs": axiom_inputs,
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
        outputs=(output,),
    )


def _pit_input(name: str) -> str:
    return f"{PIT_MODULE}#input.{name}"


def _nic_input(name: str) -> str:
    return f"{NIC_MODULE}#input.{name}"


def _income_label(income: float) -> str:
    return f"{int(income / 1000)}k"
