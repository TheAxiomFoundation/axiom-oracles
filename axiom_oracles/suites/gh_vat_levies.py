"""Ghana consumption-levy oracle suite (GHAMOD).

``gh-vat-levies`` compares the December 2025 reform's levy modules against
GHAMOD (SOUTHMOD A4.0, country GH, system GH_2025) on standard-rated
consumption:

* ``national_health_insurance_levy_amount`` (Act 1156 s.47: two and a half
  per cent) against GHAMOD ``tva01_s`` (2.5% of the standard basket).
* ``getfund_levy_amount`` (Act 1152 s.3A: two and a half per cent) against
  GHAMOD ``tva02_s`` (2.5%).

Law equivalence: both levy rates are unchanged across the reform boundary
(2.5% each under the prior Act 852/581 chain since 2018), so the 2026
modules compare against GH_2025 directly; the boundary differences are the
CHRL repeal (compared at period 2025 in ``gh_presumptive``) and VAT
deductibility restructuring. VAT itself (Act 1151 s.3, fifteen per cent)
has NO live case: GHAMOD emits no pure-VAT output — its runtime
``$VAT_rate`` is 0.21 (an effective-cascade shortcut) and the final
``tva_s`` re-adds the three levy components (27% of the base; the
``ils_taxco`` stats list adds them a third time, 33%) against a statutory
2025 cascade of 21.9% — recorded in ``ghamod_issues.json``
(``ghamod-tva-wedge-double-and-triple-counts-levies``) per the tinta04
pattern. The Axiom VAT branch is exercised by the rulespec-gh companion
tests.

The euromod side prices one standard-rated COICOP item (``x0111105``) with
matching household expenditure ``xhh`` (probed live: levies exactly 2.5%
each — 300/300 on 12,000, 1,500/1,500 on 60,000 annually). The
post-uprating basket bridge keeps both engines on the identical base. No
SOUTHMOD model XML, dataset row, or DRD text is committed — expected
values are values GHAMOD itself produced.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .gh_income_tax import (
    EUROMOD_TO_AXIOM_INPUT_BRIDGE,
    GH_METADATA,
    GH_PERIOD,
    GH_UPRATE_2017_TO_2025,
    _gh_base_row,
)

NHIL_MODULE = (
    "gh:statutes/act-1156/national-health-insurance-amendment-2025/"
    "section-47-nhil-substituted"
)
GETFUND_MODULE = (
    "gh:statutes/act-1152/ghana-education-trust-fund-amendment-2025/"
    "section-3a-getfund-levy-substituted"
)


def _nhil_input(name: str) -> str:
    return f"{NHIL_MODULE}#{name}"


def _getfund_input(name: str) -> str:
    return f"{GETFUND_MODULE}#{name}"


# Annual standard-rated consumption sweep (nominal GHS). Expected annual
# amounts (GHAMOD-produced, probed live): 2.5% each — 300/300 · 1,500/1,500.
_CONSUMPTION_GRID: tuple[tuple[str, float], ...] = (
    ("12k", 12_000.0),
    ("60k", 60_000.0),
)


def gh_vat_levies_cases() -> list[Case]:
    """Standard-rated consumption cases for the GHAMOD tva01_s/tva02_s oracles."""
    return [
        _levies_case(f"gh-levies-{label}", spend)
        for label, spend in _CONSUMPTION_GRID
    ]


def _gh_consumer(idperson: int, annual_spend: float) -> dict[str, float | int]:
    """A household head with standard-rated consumption (x0111105 = xhh)."""
    monthly = (annual_spend / GH_UPRATE_2017_TO_2025) / 12.0
    row = _gh_base_row(1, idperson)
    row.update({"dag": 40, "dhh": 1, "x0111105": monthly, "xhh": monthly})
    return row


def _levies_case(case_id: str, annual_spend: float) -> Case:
    nhil_value = _nhil_input("input.levy_chargeable_value")
    getfund_value = _getfund_input("input.taxable_value_of_goods_or_services")
    return Case(
        case_id=case_id,
        period=GH_PERIOD,
        metadata={
            **GH_METADATA,
            "scenario": "single-consumer-standard-rated-levies",
            "annual_standard_rated_consumption": annual_spend,
            # Placeholders; the post-uprating euromod basket overwrites both
            # via the bridge so all engines price the identical base.
            "axiom_inputs": {
                nhil_value: annual_spend,
                _nhil_input("input.supply_of_goods_or_services_made_in_country"): True,
                _nhil_input("input.exempt_goods_or_services"): False,
                _nhil_input("input.import_of_goods_or_services"): False,
                _nhil_input("input.exempt_import"): False,
                getfund_value: annual_spend,
                _getfund_input(
                    "input.supply_of_goods_or_services_made_in_country"
                ): True,
                _getfund_input("input.exempt_goods_or_services"): False,
                _getfund_input("input.import_of_goods_or_services"): False,
                _getfund_input("input.exempt_imports"): False,
            },
            "euromod_inputs": [_gh_consumer(101, annual_spend)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "ils_vat_std": [nhil_value, getfund_value]
            },
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 40,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                },
            ),
        ),
        outputs=(
            Concepts.GH_NHIL_AMOUNT,
            Concepts.GH_GETFUND_LEVY_AMOUNT,
        ),
    )
