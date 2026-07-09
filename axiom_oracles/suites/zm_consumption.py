"""Zambia consumption-tax oracle suites (MicroZAMOD VAT and excise).

``zm-vat`` (ZM_2025) — the rulespec-zm VAT standard rate (16% per the
Value Added Tax (Rate of Tax) Order, 2008, S.I. No. 14 of 2008, over
the Cap. 331 s.9(3) default) against MicroZAMOD ``tva_s`` on a
non-excise VAT-base expenditure item (COICOP x011119). Consumption
x-vars carry their own per-group uprating indices (probed: 1.5163 for
the x0111* food group, 1.3029 for the alcohol group, both distinct
from the 1.4430 employment index), so each case bridges the engine's
own post-uprating expenditure onto the module's ``taxable_value`` -
the Ghana/Uganda consumption-suite convention - making parity exact
regardless of index.

``zm-excise-ad-valorem`` (ZM_2025) — the rulespec-zm wine and spirits
duty rates (60 percent, assembled across Acts 19/2018, 45/2021,
25/2022 and 25/2023) against MicroZAMOD ``tex02_s`` on single-item
expenditure cases (wine x02110; spirits x02121), bridged post-uprating
- probed exact (60% x uprated value).

Dispositions (rulespec-zm#1 findings, probed live, no agreement zone -
not live cases):
- Cigarettes (finding 3): the model prices K0.400/piece (the CY2024
  K400/mille) - probed 480.00 on 1,200 sticks/yr - where the CY2025
  statutory rate is K452/mille (Act 24 of 2024) -> 542.40.
- Transport fuels (finding 4): the model applies K2.07/l (the
  CY2021-24 combined petrol figure) to all fuel litres - probed
  2,484.00 on 1,200 l/yr - where the CY2025 statutory rows are petrol
  K2.34/l (-> 2,808.00) and diesel K0.75/l (-> 900.00).
- Clear beer (finding 5): the model taxes clear-beer expenditure at a
  flat 20% (probed 312.69 on 1,563.48 uprated) - matching only the
  sorghum-feedstock suspended rate - where the statutory Second
  Schedule rate is 60% and the S.I. 66/71 of 2023 suspension layer
  (malt 20%, cassava 5%, SME/excess sorghum excluded, self-revoking
  31 December 2026) matches none of the model's flat treatment.
- Opaque beer: the statutory duty is specific (K0.25/litre) but the
  model taxes opaque-beer EXPENDITURE at the 60% ad-valorem group rate
  (probed 938.07 on 1,563.48 uprated value) - a base-and-rate mismatch
  with no directly comparable live case; recorded with the ledger.

License discipline as elsewhere: the SOUTHMOD bundle is referenced by
path only; expected values are values MicroZAMOD itself produced; no
bundle content is committed.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .gh_income_tax import EUROMOD_TO_AXIOM_INPUT_BRIDGE
from .zm_core import ZM_METADATA, ZM_PERIOD_2025, ZM_UPRATE_2022_TO_2025, _zm_base_row

VAT_MODULE = "zm:statutes/cap-331/value-added-tax-act"
EXCISE_MODULE = "zm:statutes/act-2024-24/customs-and-excise-amendment-2024"

# Annual raw (pre-uprating) expenditure targets; the bridge overwrites
# the Axiom input with the engine's own post-uprating value, so these
# only need to land in sensible regions.
_VAT_GRID = (
    ("1200-low", 1_200.0),
    ("12000-mid", 12_000.0),
    ("60000-high", 60_000.0),
)

_AD_VALOREM_GRID = (
    ("wine-1200", "x02110", "wine_taxable_value", "zm-excise-wine", 1_200.0),
    ("wine-24000", "x02110", "wine_taxable_value", "zm-excise-wine", 24_000.0),
    ("spirits-1200", "x02121", "spirits_taxable_value", "zm-excise-spirits", 1_200.0),
    ("spirits-24000", "x02121", "spirits_taxable_value", "zm-excise-spirits", 24_000.0),
)


def _zm_spender(idperson: int, var: str, annual_raw: float) -> dict[str, float | int]:
    row = _zm_base_row(1, idperson)
    row[var] = annual_raw / 12.0
    return row


def zm_vat_cases() -> list[Case]:
    """Non-excise VAT expenditure cases for the tva_s oracle."""
    return [_vat_case(f"zm-vat-{label}", annual) for label, annual in _VAT_GRID]


def _vat_case(case_id: str, annual_raw: float) -> Case:
    taxable_value = f"{VAT_MODULE}#input.taxable_value"
    return Case(
        case_id=case_id,
        period=ZM_PERIOD_2025,
        metadata={
            **ZM_METADATA,
            "scenario": "household-vat-standard-rate",
            "yearly_expenditure_raw": annual_raw,
            # Placeholder; the engine's post-uprating x011119 overwrites
            # it via the bridge (per-group uprating indices differ).
            "axiom_inputs": {taxable_value: annual_raw},
            "euromod_inputs": [_zm_spender(101, "x011119", annual_raw)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"x011119": [taxable_value]},
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 35,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                },
            ),
        ),
        outputs=(Concepts.ZM_VAT_AMOUNT,),
    )


def zm_excise_ad_valorem_cases() -> list[Case]:
    """Wine and spirits ad-valorem excise cases for the tex02_s oracle."""
    return [
        _ad_valorem_case(f"zm-excise-{label}", var, input_name, annual)
        for label, var, input_name, _, annual in _AD_VALOREM_GRID
    ]


def _ad_valorem_case(
    case_id: str, euromod_var: str, input_name: str, annual_raw: float
) -> Case:
    axiom_input = f"{EXCISE_MODULE}#input.{input_name}"
    concept = (
        Concepts.ZM_WINE_DUTY
        if input_name == "wine_taxable_value"
        else Concepts.ZM_SPIRITS_DUTY
    )
    return Case(
        case_id=case_id,
        period=ZM_PERIOD_2025,
        metadata={
            **ZM_METADATA,
            "scenario": "household-ad-valorem-excise",
            "yearly_expenditure_raw": annual_raw,
            "axiom_inputs": {axiom_input: annual_raw},
            "euromod_inputs": [_zm_spender(101, euromod_var, annual_raw)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {euromod_var: [axiom_input]},
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 35,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                },
            ),
        ),
        outputs=(concept,),
    )
