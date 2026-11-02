"""Uganda LST, SCG, VAT and fuel-excise oracle suites (UGAMOD).

``ug-lst`` compares the rulespec-ug salaried-employee Local Service Tax
(Act 8 of 2008, regulation 3 table: nil to 100,000 a month, then ten
bands from 5,000 to 100,000 shillings a year) against UGAMOD ``tgv_s``
for formal employees (``loc01=1``), with one case in every band plus
the nil band. The base is a reading, not a settled fact. The statute
and the rulespec-ug module band on "monthly take-home salary" (input
``monthly_take_home_income``). UGAMOD bands on gross employment income:
probed live, 610,000 a month gross returns 60,000 (band 6), whereas a
base net of the 5% NSSF share (579,500) would fall in band 5 (40,000)
and a base net of NSSF and PAYE (494,500) in band 4 (30,000). This
suite feeds the SAME gross monthly figure to both engines (UGAMOD
``yem``, pre-divided by the uprating index; Axiom
``monthly_take_home_income``, unbridged), so it tests the band table
under UGAMOD's gross base and says nothing about which base the
statute means. Under a net-pay reading (gross less PAYE and the
employee NSSF share), 7 of the 12 cases (450,000 to 950,000 a month)
would land one or more bands lower. Which reading is right is open
(a methodology question, not decided here).

``ug-scg`` compares the Senior Citizens Grant national rule (SAGE
Handbook: Shs 25,000/month at age 80 and above) against UGAMOD
``boa_s`` (probed exact: 300,000/yr at 80 and 85; 0 at 79 on a row
that sets no district input). The rulespec-ug module encodes the
age-80 national rule only: the handbook's national-ID and
no-other-government-pension conditions are not encoded (the synthetic
rows carry no pension income), and the earlier pilot and FY2016/17
district rollouts (lower ages or oldest-100 selection) are outside the
module, so they are not compared.

``ug-vat`` compares the 18% standard rate (Rate of Tax Order 2006)
against UGAMOD ``tva_s`` on a single standard-rated expenditure item
(restaurant meals, x1111101). Consumption x-vars carry their own
uprating index (x1111101 rises about 4.43% from the 2024 dataset to
UG_2025, not the 3.76% employment index), and detailed COICOP inputs
are not echoed in the UG_2025 output frame, so the bridge reads the
engine's own post-uprating standard-rated VAT base, the
``il_exp_vat01`` output (which UG_2025 does return), onto the module's
``taxable_value``. The base comes from that output, not from
``tva_s``, so the case still tests the 18% rate rather than restating
it (probed live: tva_s = 0.18 x il_exp_vat01 exactly). The case also
adopts UGAMOD's convention that the expenditure figure is the
VAT-exclusive taxable value; parity says nothing about whether survey
spending is VAT-inclusive.

``ug-fuel-excise`` compares the Excise Duty (Amendment) Act 2024
Schedule 2 items 8(a) and (b) (petrol Shs 1550/l, diesel Shs 1230/l) against
UGAMOD ``tex10_s`` on litre inputs, which pass unuprated (probed exact:
278,000 at 100 litres of each; 775,000 at 500 litres of petrol). The
vintage is open: rulespec-ug encodes only the 2024 rows (effective
1 July 2024) and the FY2025/26 amendment print has not been captured
(rulespec-ug#1, open item 1), so the match shows that UG_2025 and the
encoding both price the 2024 rows, not that those rows are the
FY2025/26 law.

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

# (label, monthly GROSS employment income in UGX). The same number goes
# to UGAMOD as gross yem (pre-divided by the uprating index) and to Axiom
# as the module's monthly_take_home_income input; see the module
# docstring for why that is a reading, not a settled base. Mid-band
# points (and one point 10,000 above an edge) so float drift in the
# pre-divide/uprate round trip cannot cross a band edge. One case per
# regulation 3 band plus the nil band.
_LST_GRID = (
    ("below-100k-no-tax", 80_000.0),
    ("band1-150k", 150_000.0),
    ("band2-250k", 250_000.0),
    ("band3-350k", 350_000.0),
    ("band4-450k", 450_000.0),
    ("band5-550k", 550_000.0),
    ("band6-610k-just-above-edge", 610_000.0),
    ("band6-650k", 650_000.0),
    ("band7-750k", 750_000.0),
    ("band8-850k", 850_000.0),
    ("band9-950k", 950_000.0),
    ("top-band-1500k", 1_500_000.0),
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
                "monthly_gross_employment_income": monthly,
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
                # x1111101 itself is not a column of the UG_2025 output
                # frame; il_exp_vat01 (the model's post-uprating
                # standard-rated base) is. Probed live: on this row it
                # reads 1,207,776.66 a year against the nominal
                # 1,200,000, and tva_s = 0.18 x il_exp_vat01.
                EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"il_exp_vat01": [value_input]},
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
