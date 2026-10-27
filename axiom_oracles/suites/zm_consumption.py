"""Zambia consumption-tax oracle suites (MicroZAMOD VAT and excise).

``zm-vat`` (ZM_2025) — the rulespec-zm VAT standard rate (16% per the
Value Added Tax (Rate of Tax) Order, 2008, S.I. No. 14 of 2008, over
the Cap. 331 s.9(3) default) against MicroZAMOD ``tva_s`` on a
non-excise expenditure item (COICOP x011119). Detailed COICOP input
variables are not in the engine's output frame (a bridge keyed on
``x011119`` fails with "not a column of the ZM_2025 output"), but the
frame does carry ``il_vat01``, the model's VAT-base income list (probed:
151.63 per month on 100.00 raw x011119), of which ``tva_s`` is exactly
16%. Each case
bridges ``il_vat01`` onto the module's ``taxable_value``. The base comes
from the model's income list, not from ``tva_s``, so the comparison
tests the rate: a model rate other than 16% would mismatch. (Inverting
``tva_s`` by the statutory rate to get the base would make the case
unable to fail.) Convention adopted for parity: the model treats household
spend as the VAT-exclusive taxable value and Axiom is given the same
value, so the case tests the rate on the model's base, not the statutory
definition of taxable value.

``zm-excise-ad-valorem`` (ZM_2025) — the rulespec-zm act-2024-24
``wine_duty`` and ``spirits_duty`` (60 percent: wine per Act 19 of 2018
Second Schedule heading 5, spirits per Act 45 of 2021 heading 6, both
imported into the CY2025 module) against MicroZAMOD ``tex02_s`` on
single-item expenditure cases, spirits on ``x02110`` and wine on
``x02121`` (COICOP 02.1.1 spirits, 02.1.2 wine). The output frame
carries no post-uprating value for these items (probed: no output
column on a single-item spirits or wine row holds the uprated value;
``il_vat01`` and the ``ils_coicop*`` lists are zero), so there is
nothing to bridge. The Axiom input is instead the
raw expenditure times ``ZM_UPRATE_ALCOHOL_2022_TO_2025``, the factor
ZM_2025 applies to these items, probed two ways that do not involve
the excise rate under test: on the spirits and wine rows ``tva_s /
0.16 - tex02_s`` (VAT charged on the excise-inclusive value, with the
16% rate tested by zm-vat) equals raw x 1.30287129078748, and on the
opaque-beer expenditure row ``x021303``, which carries VAT but no
excise, ``tva_s / 0.16`` gives the same factor. A model rate other than
60% therefore mismatches. The factor is a static probe, so a future
release that re-indexes these items would also mismatch and need the
constant re-probed. Inverting ``tex02_s`` by 60% to get the base would
make the case unable to fail. Convention adopted for parity: the model
charges the duty on household retail spend, and Axiom is given that same
uprated spend as the duty base, so the case tests the 60% rate on the
model's base, not the statutory duty base. Each case supplies both module inputs
(the item it does not buy at zero) because the runner queries every
suite output on every case.

Excise findings outside the grid (rulespec-zm#1; the rulespec-zm
concepts below have no concept mapping, so no live case compares
them; re-probed on ZM_2025 on 2026-10-04; ledger entries in
``axiom_oracles/data/microzamod_issues.json``):
- Cigarettes (finding 3): ``tex03_s`` is 40.00 per month on 100 sticks
  per month (``q02301``), i.e. K0.400 per piece, the CY2024 K400 per
  mille, where Act 24 of 2024 sets K452 per mille from 2025 (480.00 vs
  542.40 a year on 1,200 sticks).
- Transport fuels (finding 4): ``tex05_s`` is 207.00 per month on 100
  litres per month (``q07222``), i.e. K2.07 per litre, the pre-2025
  petrol row (Act 19 of 2018; Act 45 of 2021), on one fuel quantity
  that does not separate petrol from diesel, where Act 24 of 2024 sets
  petrol at K2.34 and diesel at K0.75 per litre from 2025 (2,484.00 vs
  2,808.00 or 900.00 a year on 1,200 litres).
- Clear beer (finding 5): ``tex02_s`` is 26.06 per month on 100.00 raw
  clear-beer expenditure (``x021302``), a flat 20% of the 130.29
  uprated value, where the statutory Second Schedule rate is 60% and
  the suspension instruments set feedstock- and producer-specific
  rates (ZRA Practice Note 1 of 2024: malt 40%, sorghum 20%, cassava
  10%; S.I. No. 66 of 2023 cuts malt to 20% and cassava to 5% for small
  and medium manufacturers and excess quantities, and S.I. No. 71 of
  2023 excludes those sorghum cases from suspension). A flat 20%
  matches the sorghum rate and the reduced malt rate only.

Opaque beer (the July 2026 entry is RETRACTED): ZM_2025 charges
``tex02_s`` of 25.00 per month on 100 litres per month of
``q021303``, the statutory K0.25 per litre (Act 45 of 2021,
2203.00.10), and no excise on opaque-beer expenditure ``x021303``
(VAT only). The July value (938.07 on 1,200 a year) equals what the
model charges on the same spend of the spirits or wine items above, so
it was not an opaque-beer observation. Opaque beer is an agreement
zone between the model and the statute that no live case exercises.

License discipline as elsewhere: the SOUTHMOD bundle is referenced by
path only; expected values are values MicroZAMOD itself produced; no
bundle content is committed.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .gh_income_tax import EUROMOD_TO_AXIOM_INPUT_BRIDGE
from .zm_core import ZM_METADATA, ZM_PERIOD_2025, _zm_base_row

VAT_MODULE = "zm:statutes/cap-331/value-added-tax-act"
EXCISE_MODULE = "zm:statutes/act-2024-24/customs-and-excise-amendment-2024"

# Uprating factor ZM_2025 applies to the 2022-vintage spirits and wine
# expenditure items, probed live without using the excise rate: on
# single-item spirits and wine rows tva_s / 0.16 - tex02_s = raw x this,
# and on the VAT-only opaque-beer expenditure row tva_s / 0.16 = raw x
# this.
ZM_UPRATE_ALCOHOL_2022_TO_2025 = 1.30287129078748

# Annual raw (pre-uprating) expenditure targets. VAT cases bridge the
# engine's own post-uprating base (il_vat01), so these only need to land
# in sensible regions; excise cases feed raw x the alcohol factor.
_VAT_GRID = (
    ("1200-low", 1_200.0),
    ("12000-mid", 12_000.0),
    ("60000-high", 60_000.0),
)

# (label, MicroZAMOD expenditure variable, module input, annual raw).
# The variables follow COICOP: x02110 is spirits (02.1.1) and x02121 is
# wine (02.1.2).
_AD_VALOREM_GRID = (
    ("wine-1200", "x02121", "wine_taxable_value", 1_200.0),
    ("wine-24000", "x02121", "wine_taxable_value", 24_000.0),
    ("spirits-1200", "x02110", "spirits_taxable_value", 1_200.0),
    ("spirits-24000", "x02110", "spirits_taxable_value", 24_000.0),
)

# The suite queries both ad-valorem outputs on every case, so each case
# supplies both inputs (the item it does not buy at zero).
_AD_VALOREM_INPUTS = ("wine_taxable_value", "spirits_taxable_value")


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
            # Placeholder; the engine's il_vat01 income list (the
            # post-uprating value of the item) overwrites it via the
            # bridge (x-vars are not in the output frame).
            "axiom_inputs": {taxable_value: annual_raw},
            "euromod_inputs": [_zm_spender(101, "x011119", annual_raw)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"il_vat01": [taxable_value]},
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
        for label, var, input_name, annual in _AD_VALOREM_GRID
    ]


def _ad_valorem_case(
    case_id: str, euromod_var: str, input_name: str, annual_raw: float
) -> Case:
    axiom_inputs = {
        f"{EXCISE_MODULE}#input.{name}": 0.0 for name in _AD_VALOREM_INPUTS
    }
    axiom_inputs[f"{EXCISE_MODULE}#input.{input_name}"] = (
        annual_raw * ZM_UPRATE_ALCOHOL_2022_TO_2025
    )
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
            # Raw spend x the probed alcohol uprating factor (no output
            # column carries the uprated value of these items, so there
            # is nothing to bridge).
            "axiom_inputs": axiom_inputs,
            "euromod_inputs": [_zm_spender(101, euromod_var, annual_raw)],
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
