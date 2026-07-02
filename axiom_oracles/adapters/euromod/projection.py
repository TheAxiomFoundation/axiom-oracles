"""Project thin Axiom cases into EUROMOD-platform input rows.

EUROMOD-platform models (EUROMOD itself, UKMOD, and the other national
spin-offs) consume one person-per-row tables with the standard EUROMOD
variable names: ``idhh``/``idperson`` ids, demographics (``dag`` age,
``dgn`` gender, ``dms`` marital status), and monetary variables (``yem``
employment income, ``yse`` self-employment, ``yiy`` investment income,
``poa`` pensions). Monetary case facts are annual (the Axiom concept
convention); EUROMOD dataset configurations are usually monthly, so the
projection divides by 12 unless the dataset is declared annual.

Cases may bypass projection entirely by carrying fully-formed rows in
``metadata["euromod_inputs"]`` (a list of row dicts, one per person) — the
same escape hatch the TAXSIM adapter provides via ``taxsim_input``.
"""

from __future__ import annotations

from typing import Any

from axiom_oracles.core.case import Case, Concepts, Entity

#: The minimal input schema shared by UKMOD's and EUROMOD's demo datasets.
#: Every projected row carries every column (engines refuse ragged input).
EUROMOD_INPUT_COLUMNS: tuple[str, ...] = (
    "idhh",
    "idperson",
    "idpartner",
    "idmother",
    "idfather",
    "dct",
    "dwt",
    "dag",
    "dec",
    "les",
    "yem",
    "dgn",
    "lhw",
    "dms",
    "loc",
    "yse",
    "yiy",
    "poa",
    "ddi",
    "boa",
    "poa00",
    "yseev",
)

#: EUROMOD labour-status code for an employee (``les``).
_LES_EMPLOYED = 3
#: EUROMOD marital-status codes (``dms``).
_DMS_SINGLE = 1
_DMS_MARRIED = 2

_ADULT_RELATIONS = {"headofhousehold", "head", "spouse", "partner"}


def euromod_input_rows(
    case: Case,
    *,
    household_number: int,
    country_code: int,
    monthly_inputs: bool = True,
) -> list[dict[str, Any]]:
    """Project one case into EUROMOD input rows (one per person).

    Args:
        case: A concept-keyed case. Person entities carry ages, incomes,
            and household relations; ``metadata["euromod_inputs"]`` (a list
            of row dicts) overrides the projected demographics/income while
            keeping the adapter-assigned ``idhh`` (results are grouped by
            it).
        household_number: Sequential ``idhh`` the adapter assigned to this
            case (1-based case position; deterministic result grouping).
        country_code: The model's ``dct`` country code (15 in UKMOD's demo
            data). Columns absent from the target dataset's schema —
            EUROMOD's has no ``dct`` at all — are dropped by the worker's
            template overlay.
        monthly_inputs: Divide annual monetary facts by 12 (the usual
            EUROMOD dataset convention). Pass ``False`` for datasets
            declared annual.

    Returns:
        Row dicts covering every :data:`EUROMOD_INPUT_COLUMNS` key.

    Raises:
        ValueError: If the case has no person entities and no explicit
            ``euromod_inputs`` metadata.
    """
    explicit = case.metadata.get("euromod_inputs")
    if explicit is not None:
        return [dict(row) | {"idhh": household_number} for row in explicit]

    persons = case.entities_of_kind("person")
    if not persons:
        raise ValueError(
            f"Case {case.case_id!r} has no person entities and no "
            "metadata['euromod_inputs'] rows."
        )

    household_id = household_number
    adults = [p for p in persons if _relation(p) in _ADULT_RELATIONS]
    head = adults[0] if adults else persons[0]
    spouse = adults[1] if len(adults) > 1 else None

    person_ids = {
        person.entity_id: household_id * 100 + index + 1
        for index, person in enumerate(persons)
    }

    rows = []
    for person in persons:
        is_head = person is head
        is_spouse = spouse is not None and person is spouse
        partner_id = 0
        if is_head and spouse is not None:
            partner_id = person_ids[spouse.entity_id]
        elif is_spouse:
            partner_id = person_ids[head.entity_id]
        is_child = not (is_head or is_spouse)
        factor = 12.0 if monthly_inputs else 1.0
        employment = float(person.fact(Concepts.YEARLY_EARNED_INCOME, 0.0) or 0.0)
        investment = float(person.fact(Concepts.INTEREST_INCOME, 0.0) or 0.0) + float(
            person.fact(Concepts.DIVIDEND_INCOME, 0.0) or 0.0
        )
        pension = float(person.fact(Concepts.PENSION_INCOME, 0.0) or 0.0)
        age = int(person.fact(Concepts.PERSON_AGE, 0) or 0)
        rows.append(
            {
                "idhh": household_id,
                "idperson": person_ids[person.entity_id],
                "idpartner": partner_id,
                "idmother": person_ids[head.entity_id] if is_child else 0,
                "idfather": 0,
                "dct": country_code,
                "dwt": 1.0,
                "dag": age,
                "dec": 0,
                "les": _LES_EMPLOYED if employment > 0 else 0,
                "yem": employment / factor,
                "dgn": 1 if is_head else 0,
                "lhw": 40 if employment > 0 else 0,
                "dms": _DMS_MARRIED if (is_head or is_spouse) and spouse is not None
                else _DMS_SINGLE,
                "loc": 5,
                "yse": 0.0,
                "yiy": investment / factor,
                "poa": pension / factor,
                "ddi": 1 if person.fact(Concepts.DISABLED) else 0,
                "boa": 0.0,
                "poa00": 0.0,
                "yseev": 0.0,
            }
        )
    return rows


def _relation(person: Entity) -> str:
    value = person.fact(Concepts.HOUSEHOLD_RELATION, "") or ""
    return str(value).replace("_", "").replace(" ", "").lower()
