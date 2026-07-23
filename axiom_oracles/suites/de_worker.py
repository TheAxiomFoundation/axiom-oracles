"""Germany's 2025 direct EUROMOD↔GETTSIM worker comparison grid."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..core.case import Case, Concepts, Entity


DE_SCOPE = {"type": "country", "geoid": "DE"}
DE_WORKER_PERIOD = "2025"
DE_INPUT_UPRATING_FACTOR = 61.0 / 56.0

DE_WORKER_OUTPUTS = (
    Concepts.DE_EMPLOYEE_HEALTH_INSURANCE_CONTRIBUTION_MONTHLY,
    Concepts.DE_EMPLOYEE_PENSION_INSURANCE_CONTRIBUTION_MONTHLY,
    Concepts.DE_EMPLOYEE_UNEMPLOYMENT_INSURANCE_CONTRIBUTION_MONTHLY,
    Concepts.DE_EMPLOYEE_LONG_TERM_CARE_INSURANCE_CONTRIBUTION_MONTHLY,
    Concepts.DE_INCOME_TAX_INCLUDING_SOLIDARITY_SURCHARGE_ANNUAL,
    Concepts.DE_KINDERGELD_MONTHLY,
)

# String leaves are the result aliases returned by GETTSIM. Keeping each alias
# equal to its official target path makes the mapping and report self-describing.
DE_GETTSIM_TARGETS = {
    "einkommensteuer": {
        "betrag_y_sn": "einkommensteuer.betrag_y_sn",
    },
    "solidaritätszuschlag": {
        "betrag_y_sn": "solidaritätszuschlag.betrag_y_sn",
    },
    "sozialversicherung": {
        "kranken": {
            "beitrag": {
                "betrag_versicherter_m": (
                    "sozialversicherung.kranken.beitrag.betrag_versicherter_m"
                )
            }
        },
        "rente": {
            "beitrag": {
                "betrag_versicherter_m": (
                    "sozialversicherung.rente.beitrag.betrag_versicherter_m"
                )
            }
        },
        "arbeitslosen": {
            "beitrag": {
                "betrag_versicherter_m": (
                    "sozialversicherung.arbeitslosen.beitrag.betrag_versicherter_m"
                )
            }
        },
        "pflege": {
            "beitrag": {
                "betrag_versicherter_m": (
                    "sozialversicherung.pflege.beitrag.betrag_versicherter_m"
                )
            }
        },
    },
    "kindergeld": {"betrag_m": "kindergeld.betrag_m"},
}

_SINGLE_WEST_MONTHLY_EARNINGS = (500, 1200, 2500, 4000, 5500, 7500, 9000, 12000)


def de_worker_dual_oracle_cases() -> list[Case]:
    """The 13-household DE_2025 parity grid, in its pinned report order."""

    cases = [
        _case(
            f"single-w-{monthly}",
            (float(monthly),),
            scenario="single-worker-west",
        )
        for monthly in _SINGLE_WEST_MONTHLY_EARNINGS
    ]
    cases.extend(
        [
            _case(
                "single-e-4000",
                (4000.0,),
                scenario="single-worker-east",
                west=False,
            ),
            _case(
                "couple-8000-0",
                (8000.0, 0.0),
                scenario="married-couple-one-earner",
                married=True,
            ),
            _case(
                "couple-4000-2000",
                (4000.0, 2000.0),
                scenario="married-couple-two-earner",
                married=True,
            ),
            _case(
                "parent-1child-4000",
                (4000.0,),
                scenario="single-parent-one-child",
                child_birth_years=(2015,),
            ),
            _case(
                "parent-2children-4000",
                (4000.0,),
                scenario="single-parent-two-children",
                child_birth_years=(2015, 2018),
            ),
        ]
    )
    return cases


def reduce_gettsim_household_values(
    values: Mapping[str, Sequence[float | int]],
) -> dict[str, float | int]:
    """Reduce GETTSIM's per-person outputs to the compared household amount.

    Steuernummer-level annual targets (``*_y_sn``) are replicated on joint
    partners, so they reduce with MAX. Ordinary person-level monthly targets
    reduce with SUM.
    """

    reduced: dict[str, float | int] = {}
    for target, column in values.items():
        if not column:
            reduced[target] = 0
        elif target.endswith("_y_sn"):
            reduced[target] = max(column)
        else:
            reduced[target] = sum(column)
    return reduced


def _case(
    case_id: str,
    monthly_earnings: tuple[float, ...],
    *,
    scenario: str,
    west: bool = True,
    married: bool = False,
    child_birth_years: tuple[int, ...] = (),
) -> Case:
    if married and len(monthly_earnings) != 2:
        raise ValueError("married DE worker cases require exactly two adults")
    if not married and len(monthly_earnings) != 1:
        raise ValueError("non-married DE worker cases require exactly one adult")

    adult_count = len(monthly_earnings)
    child_count = len(child_birth_years)
    person_ids = tuple(101 + index for index in range(adult_count + child_count))

    euromod_rows = []
    entities = []
    gettsim_persons: list[dict[str, object]] = []
    for index, monthly in enumerate(monthly_earnings):
        is_head = index == 0
        partner_id = person_ids[1 - index] if married else 0
        age = 35 if is_head else 34
        euromod_rows.append(
            _euromod_person(
                person_ids[index],
                age=age,
                monthly=monthly,
                west=west,
                sex=1 if is_head else 2,
                partner=partner_id,
            )
        )
        entities.append(
            Entity(
                entity_id="head" if is_head else "partner",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: age,
                    Concepts.HOUSEHOLD_RELATION: (
                        "HeadOfHousehold" if is_head else "Spouse"
                    ),
                    Concepts.YEARLY_EARNED_INCOME: monthly * 12,
                },
            )
        )
        gettsim_person: dict[str, object] = {}
        if monthly:
            gettsim_person["einnahmen__bruttolohn_m"] = (
                monthly * DE_INPUT_UPRATING_FACTOR
            )
        if not is_head:
            gettsim_person["alter"] = age
        if married:
            gettsim_person["einkommensteuer__gemeinsam_veranlagt"] = True
        gettsim_persons.append(gettsim_person)

    for child_index, birth_year in enumerate(child_birth_years, start=adult_count):
        age = 2025 - birth_year
        euromod_rows.append(
            _euromod_person(
                person_ids[child_index],
                age=age,
                west=west,
                mother=person_ids[0],
            )
        )
        entities.append(
            Entity(
                entity_id=f"child{child_index - adult_count + 1}",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: age,
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.YEARLY_EARNED_INCOME: 0.0,
                },
            )
        )
        gettsim_persons.append({"geburtsjahr": birth_year})

    if child_count:
        gettsim_persons[0].update(
            {
                "sozialversicherung__pflege__beitrag__hat_kinder": True,
                "familie__alleinerziehend": True,
            }
        )

    gettsim_case: dict[str, object] = {"persons": gettsim_persons}
    if married:
        gettsim_case["spouse_pairs"] = [[0, 1]]
    if child_count:
        child_indices = range(adult_count, adult_count + child_count)
        gettsim_case["parents"] = {
            child_index: [0, None] for child_index in child_indices
        }
        gettsim_case["kindergeld_recipients"] = {
            child_index: 0
            for child_index in range(adult_count, adult_count + child_count)
        }

    return Case(
        case_id=case_id,
        period=DE_WORKER_PERIOD,
        metadata={
            "locale": "DE",
            "scope": DE_SCOPE,
            "scenario": scenario,
            "yearly_earned_income": sum(monthly_earnings) * 12,
            "nominal_monthly_earnings": list(monthly_earnings),
            "region": "west" if west else "east",
            "joint_assessment": married,
            "child_birth_years": list(child_birth_years),
            "euromod_inputs": euromod_rows,
            "gettsim_case": gettsim_case,
        },
        entities=tuple(entities),
        outputs=DE_WORKER_OUTPUTS,
    )


def _euromod_person(
    idperson: int,
    *,
    age: int = 35,
    monthly: float = 0.0,
    west: bool = True,
    sex: int = 1,
    partner: int = 0,
    mother: int = 0,
    father: int = 0,
) -> dict[str, float | int]:
    employed = monthly > 0
    return {
        "idperson": idperson,
        "idpartner": partner,
        "idmother": mother,
        "idfather": father,
        "dwt": 1.0,
        "dag": age,
        "dgn": sex,
        "dms": 2 if partner else 1,
        "les": 3 if employed else (6 if age < 16 else 1),
        "lhw": 40 if employed else 0,
        "liwwh": 40 if employed else 0,
        "liwmy": 12 if employed else 0,
        "yem": monthly,
        "yemmy": 12 if employed else 0,
        "lcs": 0,
        "dec": 1 if age < 16 else 0,
        "drgn1": 9 if west else 4,
    }
