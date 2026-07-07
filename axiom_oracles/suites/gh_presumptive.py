"""Ghana presumptive-turnover and CHRL oracle suite (GHAMOD).

``gh-presumptive-turnover`` compares two rulespec-gh modules against GHAMOD
(SOUTHMOD A4.0, country GH, system GH_2025) on small-business turnover:

* ``paragraph_5_turnover_tax_payable`` (Second Schedule paragraph 5 as
  substituted by Act 1071: three per cent of turnover in the
  (20,000, 500,000] band) against GHAMOD ``ttn01_s`` (3% of ``ytn``).
* ``covid_health_recovery_levy_amount`` (Act 1068 s.1(4): one per cent of
  the taxable supply value) against GHAMOD ``ttn02_s`` (1% of ``ytn`` for
  presumptive payers — the levy's statutory base is the taxable supply;
  GHAMOD prices the presumptive payer's turnover as that base, and the
  suite feeds the same value to both engines).

Live cases stay inside the band BOTH engines tax — turnover in
(20,000, 120,000] — where the rates are exact (probed: 30,000 → 900/300;
60,000 → 1,800/600; 120,000 → 3,600/1,200 annually). GHAMOD's eligibility
band 10,000-120,000 matches no in-force text: the statutory band has been
(20,000, 500,000] since Act 1071 (Dec 2021), was (20,000, 200,000] from
Act 902 (Dec 2015), and the original (20,000, 120,000] ceiling lasted
under a month; the 10,000 floor appears in no print. Probed divergences:
turnover 15,000 → GHAMOD 450+150 vs statute 0; turnover 200,000 → GHAMOD
0 vs statute 6,000. Recorded in ``ghamod_issues.json``
(``ghamod-ttn-eligibility-band-10k-120k-superseded``) per the tinta04
pattern.

Input convention and license discipline follow ``gh_income_tax``: monetary
inputs pre-divide by the GH_2025 uprating index, the post-uprating ``ytn``
bridge keeps both engines on an identical turnover base, and no SOUTHMOD
model XML, dataset row, or DRD text is committed — expected values are
values GHAMOD itself produced.
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

PRESUMPTIVE_MODULE = (
    "gh:statutes/act-1071/income-tax-amendment-no2-2021/"
    "second-schedule-substitutions"
)
CHRL_MODULE = (
    "gh:statutes/act-1068/covid-19-health-recovery-levy-2021/"
    "section-1-imposition-of-levy"
)


def _presumptive_input(name: str) -> str:
    return f"{PRESUMPTIVE_MODULE}#{name}"


def _chrl_input(name: str) -> str:
    return f"{CHRL_MODULE}#{name}"


# Annual turnover sweep (nominal GHS) inside the shared (20,000, 120,000]
# band. Expected annual amounts (GHAMOD-produced, probed live):
# 3% -> 900 · 1,800 · 3,600 and 1% -> 300 · 600 · 1,200.
_TURNOVER_GRID: tuple[tuple[str, float], ...] = (
    ("30k", 30_000.0),
    ("60k", 60_000.0),
    ("120k-shared-band-top", 120_000.0),
)


def gh_presumptive_turnover_cases() -> list[Case]:
    """Small-business turnover cases for the GHAMOD ttn01_s/ttn02_s oracles."""
    return [
        _turnover_case(f"gh-presumptive-{label}", turnover)
        for label, turnover in _TURNOVER_GRID
    ]


def _gh_small_business(idperson: int, annual_turnover: float) -> dict[str, float | int]:
    """A household head whose only income is small-business turnover (ytn)."""
    monthly = (annual_turnover / GH_UPRATE_2017_TO_2025) / 12.0
    row = _gh_base_row(1, idperson)
    row.update({"dag": 40, "dhh": 1, "ytn": monthly})
    return row


def _turnover_case(case_id: str, annual_turnover: float) -> Case:
    turnover_input = _presumptive_input("input.business_turnover")
    supply_value_input = _chrl_input("input.taxable_supply_or_import_value")
    return Case(
        case_id=case_id,
        period=GH_PERIOD,
        metadata={
            **GH_METADATA,
            "scenario": "single-small-business-presumptive-turnover",
            "annual_turnover": annual_turnover,
            # Placeholders; the post-uprating euromod ytn overwrites both via
            # the bridge so all engines price the identical turnover base.
            "axiom_inputs": {
                turnover_input: annual_turnover,
                _presumptive_input(
                    "input.presumptive_taxation_applies_as_referred_to_in_paragraph_2_1_c_ii"
                ): True,
                _presumptive_input(
                    "input.annual_turnover_average_for_three_consecutive_years"
                ): 0.0,
                _presumptive_input(
                    "input.turnover_calculated_using_modified_cash_basis"
                ): 0.0,
                supply_value_input: annual_turnover,
                _chrl_input("input.supply_of_goods_or_services_made_in_country"): True,
                _chrl_input("input.supply_is_exempt_goods_or_services"): False,
                _chrl_input("input.import_of_goods_or_services"): False,
                _chrl_input("input.import_is_exempt_import"): False,
                _chrl_input("input.person_charges_value_added_tax_flat_rate"): False,
                _chrl_input("input.person_makes_supply_of_goods_or_services"): True,
            },
            "euromod_inputs": [_gh_small_business(101, annual_turnover)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "ytn": [turnover_input, supply_value_input]
            },
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 40,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.SELF_EMPLOYMENT_INCOME: annual_turnover,
                },
            ),
        ),
        outputs=(
            Concepts.GH_PRESUMPTIVE_TURNOVER_TAX,
            Concepts.GH_COVID_HEALTH_RECOVERY_LEVY,
        ),
    )
