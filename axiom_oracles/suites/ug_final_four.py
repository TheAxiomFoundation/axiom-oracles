"""Uganda LST, SCG, VAT and fuel-excise oracle suites (UGAMOD).

``ug-lst`` compares the rulespec-ug salaried-employee Local Service Tax
(Act 8 of 2008 Fifth Schedule graduated table) against UGAMOD ``tgv_s``
for formal employees (``loc01=1``) at mid-band monthly incomes — probed
exact at every tested band (5,000 at 150,000/m; 60,000 at 650,000/m;
100,000 at 1,500,000/m).

``ug-scg`` compares the Senior Citizens Grant national rule (SAGE
Handbook: Shs 25,000/month at age 80 and above) against UGAMOD
``boa_s`` (probed exact: 300,000/yr at 80 and 85; 0 at 79 outside the
rollout districts — the district lists at lower ages are dispositioned
in the module's deferrals, not compared).

``ug-vat`` compares the 18% standard rate (Rate of Tax Order 2006)
against UGAMOD ``tva_s`` on a single standard-rated COICOP item from
the model's own il_exp_vat01 list (restaurant meals, x1111101).

``ug-fuel-excise`` compares the Excise Duty (Amendment) Act 2024 item 8
rows (petrol Shs 1550/l, diesel Shs 1230/l) against UGAMOD ``tex10_s``
on litre inputs (probed exact: 278,000 at 100 litres of each).

License discipline as in ``ug_income_tax``.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .gh_income_tax import EUROMOD_TO_AXIOM_INPUT_BRIDGE
from .ug_income_tax import (
    UG_METADATA,
    UG_PERIOD,
    UG_UPRATE_2024_TO_2025,
    _ug_base_row,
)

LST_MODULE = "ug:statutes/act-2008-8/local-governments-amendment-no2-2008"
SCG_MODULE = "ug:policies/mglsd-scg/sage-handbook"
VAT_MODULE = "ug:regulations/vat-rate-of-tax-order-2006/rate-of-tax-order-2006"
FUEL_MODULE = "ug:statutes/act-2024-excise/excise-duty-amendment-2024"

# (label, monthly take-home income) — mid-band points so float drift in
# the pre-divide/uprate round trip cannot cross a band edge.
_LST_GRID = (
    ("band1-150k", 150_000.0),
    ("band3-350k", 350_000.0),
    ("band6-650k", 650_000.0),
    ("top-band-1500k", 1_500_000.0),
    ("below-100k-no-tax", 80_000.0),
)

_SCG_GRID = (("age-80", 80), ("age-85", 85), ("age-79-not-eligible", 79))

_VAT_GRID = (("restaurant-1200000", 1_200_000.0),)

# (label, annual petrol litres, annual diesel litres)
_FUEL_GRID = (
    ("100l-each", 100.0, 100.0),
    ("petrol-only-500l", 500.0, 0.0),
)


def ug_lst_cases() -> list[Case]:
    """Salaried-employee Local Service Tax cases for the UGAMOD tgv_s oracle."""
    cases = []
    for label, monthly in _LST_GRID:
        row = _ug_base_row(1, 101)
        row.update({"les": 3, "lfo": 1, "loc01": 1,
                    "yem": monthly / UG_UPRATE_2024_TO_2025})
        cases.append(Case(
            case_id=f"ug-lst-{label}",
            period=UG_PERIOD,
            metadata={
                **UG_METADATA,
                "scenario": "formal-employee-local-service-tax",
                "monthly_take_home_income": monthly,
                "axiom_inputs": {f"{LST_MODULE}#input.monthly_take_home_income": monthly},
                "euromod_inputs": [row],
            },
            entities=(Entity(entity_id="head", kind="person", facts={
                Concepts.PERSON_AGE: 40,
                Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
            }),),
            outputs=(Concepts.UG_LOCAL_SERVICE_TAX,),
        ))
    return cases


def ug_scg_cases() -> list[Case]:
    """Senior Citizens Grant national-rule cases for the UGAMOD boa_s oracle."""
    cases = []
    for label, age in _SCG_GRID:
        row = _ug_base_row(1, 101)
        row.update({"dag": age})
        cases.append(Case(
            case_id=f"ug-scg-{label}",
            period=UG_PERIOD,
            metadata={
                **UG_METADATA,
                "scenario": "older-person-senior-citizens-grant",
                "person_age": age,
                "axiom_inputs": {f"{SCG_MODULE}#input.person_age": age},
                "euromod_inputs": [row],
            },
            entities=(Entity(entity_id="head", kind="person", facts={
                Concepts.PERSON_AGE: age,
                Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
            }),),
            outputs=(Concepts.UG_SENIOR_CITIZENS_GRANT,),
        ))
    return cases


def ug_vat_cases() -> list[Case]:
    """Standard-rate VAT cases for the UGAMOD tva_s oracle."""
    cases = []
    for label, annual in _VAT_GRID:
        row = _ug_base_row(1, 101)
        monthly = (annual / UG_UPRATE_2024_TO_2025) / 12.0
        row.update({"x1111101": monthly, "xhh": monthly})
        value_input = f"{VAT_MODULE}#input.taxable_value"
        cases.append(Case(
            case_id=f"ug-vat-{label}",
            period=UG_PERIOD,
            metadata={
                **UG_METADATA,
                "scenario": "single-consumer-standard-rated-vat",
                "annual_standard_rated_consumption": annual,
                "axiom_inputs": {value_input: annual},
                "euromod_inputs": [row],
                EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"x1111101": [value_input]},
            },
            entities=(Entity(entity_id="head", kind="person", facts={
                Concepts.PERSON_AGE: 40,
                Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
            }),),
            outputs=(Concepts.UG_VAT_AMOUNT,),
        ))
    return cases


def ug_fuel_excise_cases() -> list[Case]:
    """Fuel excise cases for the UGAMOD tex10_s oracle (litres pass unuprated)."""
    cases = []
    for label, petrol, diesel in _FUEL_GRID:
        row = _ug_base_row(1, 101)
        row.update({"q0722101": petrol / 12.0, "q0722102": diesel / 12.0,
                    "x0722101": 1.0 if petrol else 0.0,
                    "x0722102": 1.0 if diesel else 0.0, "xhh": 1.0})
        cases.append(Case(
            case_id=f"ug-fuel-{label}",
            period=UG_PERIOD,
            metadata={
                **UG_METADATA,
                "scenario": "single-consumer-fuel-excise",
                "annual_petrol_litres": petrol,
                "annual_diesel_litres": diesel,
                "axiom_inputs": {
                    f"{FUEL_MODULE}#input.petrol_litres": petrol,
                    f"{FUEL_MODULE}#input.diesel_litres": diesel,
                },
                "euromod_inputs": [row],
            },
            entities=(Entity(entity_id="head", kind="person", facts={
                Concepts.PERSON_AGE: 40,
                Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
            }),),
            outputs=(Concepts.UG_FUEL_EXCISE_DUTY,),
        ))
    return cases
