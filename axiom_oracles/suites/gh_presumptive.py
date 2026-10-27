"""Ghana presumptive-turnover and CHRL oracle suite (GHAMOD).

``gh-presumptive-turnover`` compares two rulespec-gh modules against GHAMOD
(SOUTHMOD A4.0, country GH, system GH_2025) on small-business turnover:

* ``paragraph_5_turnover_tax_payable`` (Second Schedule paragraph 5 as
  substituted by Act 1071: three per cent of turnover in the
  (20,000, 500,000] band) against GHAMOD ``ttn01_s`` (3% of ``ytn``).
* ``covid_health_recovery_levy_amount`` (Act 1068 s.1(4): one per cent of
  the taxable supply value) against GHAMOD ``ttn02_s`` (1% of ``ytn`` for
  presumptive payers: the levy's statutory base is the taxable supply;
  GHAMOD prices the presumptive payer's turnover as that base, and the
  suite feeds the same value to both engines).

Live cases stay inside the band BOTH engines tax, turnover in
(20,000, 120,000), where the rates are exact (live run 2026-10-04:
30,000 -> 900/300; 60,000 -> 1,800/600; 119,999 -> 3,599.97/1,199.99 a
year). The top case is 119,999, not 120,000: GHAMOD's 120,000 ceiling is
all-or-nothing, and an input that uprates to 120,000 only to within
floating-point noise can land on either side of it (probed: two monthly
inputs a few floating-point steps apart around 120,000 a year get the full
3,600/1,200 and nil respectively).

Law equivalence: the whole suite compares at period 2025, GHAMOD's policy
year (GH_2025) and the levy's last live year. The COVID-19 Health Recovery
Levy (Repeal) Act, 2025 (Act 1150, gazette 10 Dec 2025) repeals the levy
from 2026, and the rulespec module carries the repeal as a zero-rate
version from 2025-12-10 (the engine reads the version live on the period
start, so 2025 prices 1% and 2026 prices nil). The comparison runner
applies ONE period to every synthetic case (the CLI overwrites
``Case.period`` with ``--period``), so a per-case 2025 period alone cannot
hold the levy cases at 2025 while the turnover cases run at 2026. The Act
1071 paragraph 5 band and rate carry a single version from 2021-12-30, so
the turnover-tax cases price identically at 2025 and 2026 and lose nothing
by sharing the 2025 period.

GHAMOD's eligibility band of 10,000 to 120,000 matches no in-force text:
the statutory band has been (20,000, 500,000] since Act 1071 (December
2021) and was (20,000, 200,000] under Act 902 (assented 30 December 2015);
the 120,000 ceiling is the original Act 896 text (assented 1 September
2015), and the 10,000 floor (probed: 9,990 a year gives 0, 10,010 gives
300.30 + 100.10) appears in none of the three. Probed
divergences: turnover 15,000 -> GHAMOD 450+150 vs statute 0; turnover
200,000 -> GHAMOD 0 vs statute 6,000 plus the levy. Recorded in
``ghamod_issues.json`` (``ghamod-ttn-eligibility-band-10k-120k-superseded``)
per the tinta04 pattern.

Input convention and license discipline follow ``gh_income_tax``: monetary
inputs pre-divide by the GH_2025 uprating index, the post-uprating ``ytn``
bridge keeps both engines on an identical turnover base, and no SOUTHMOD
model XML, dataset row, or DRD text is committed; expected values are
values GHAMOD itself produced.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .gh_income_tax import (
    EUROMOD_TO_AXIOM_INPUT_BRIDGE,
    GH_METADATA,
    GH_UPRATE_2017_TO_2025,
    _gh_base_row,
)

# GHAMOD's policy year and the CHRL's last live year (see the module
# docstring); comparisons/gh-presumptive-turnover.yaml runs at this period.
GH_PRESUMPTIVE_PERIOD = "2025"

PRESUMPTIVE_MODULE = (
    "gh:statutes/act-1071/income-tax-amendment-no2-2021/"
    "second-schedule-substitutions"
)
CHRL_MODULE = (
    "gh:statutes/act-1068/covid-19-health-recovery-levy-2021/"
    "section-1-imposition-of-levy"
)


def _presumptive_input(name: str) -> str:
    return f"{PRESUMPTIVE_MODULE}#input.{name}"


def _chrl_input(name: str) -> str:
    return f"{CHRL_MODULE}#input.{name}"


# Annual turnover sweep (nominal GHS) inside the band both engines tax.
# Expected annual amounts (GHAMOD-produced, live run 2026-10-04):
# 3% -> 900 · 1,800 · 3,599.97 and 1% -> 300 · 600 · 1,199.99. The top case
# sits one cedi inside GHAMOD's all-or-nothing 120,000 ceiling so uprating
# noise cannot tip it over (see the module docstring).
_TURNOVER_GRID: tuple[tuple[str, float], ...] = (
    ("30k", 30_000.0),
    ("60k", 60_000.0),
    ("119999-shared-band-top", 119_999.0),
)


def _presumptive_zero_inputs() -> dict[str, float | bool]:
    """Act 1071 paragraph 5 inputs, all off (for the CHRL cases).

    The Axiom runner batches the suite's cases into one engine request and
    queries the union of the suite's outputs on every case (the per-case
    ``outputs`` filter is applied to the comparisons afterwards), and the
    engine rejects a queried output whose free inputs are absent. Each case
    therefore also carries the other module's inputs, zero-filled, so the
    unused output evaluates to zero instead of failing the whole batch (the
    rw-excise convention).
    """
    return {
        _presumptive_input("business_turnover"): 0.0,
        _presumptive_input(
            "presumptive_taxation_applies_as_referred_to_in_paragraph_2_1_c_ii"
        ): False,
        _presumptive_input(
            "annual_turnover_average_for_three_consecutive_years"
        ): 0.0,
        _presumptive_input("turnover_calculated_using_modified_cash_basis"): 0.0,
    }


def _chrl_zero_inputs() -> dict[str, float | bool]:
    """Act 1068 inputs, all off (for the paragraph 5 turnover-tax cases)."""
    return {
        _chrl_input("taxable_supply_or_import_value"): 0.0,
        _chrl_input("supply_of_goods_or_services_made_in_country"): False,
        _chrl_input("supply_is_exempt_goods_or_services"): False,
        _chrl_input("import_of_goods_or_services"): False,
        _chrl_input("import_is_exempt_import"): False,
        _chrl_input("person_charges_value_added_tax_flat_rate"): False,
        _chrl_input("person_makes_supply_of_goods_or_services"): False,
    }


def gh_presumptive_turnover_cases() -> list[Case]:
    """Small-business turnover cases for the GHAMOD ttn01_s/ttn02_s oracles."""
    cases = [
        _turnover_case(f"gh-presumptive-{label}", turnover)
        for label, turnover in _TURNOVER_GRID
    ]
    cases.extend(
        _chrl_case(f"gh-chrl-{label}", turnover)
        for label, turnover in _TURNOVER_GRID
    )
    return cases


def _gh_small_business(idperson: int, annual_turnover: float) -> dict[str, float | int]:
    """A household head whose only income is small-business turnover (ytn)."""
    monthly = (annual_turnover / GH_UPRATE_2017_TO_2025) / 12.0
    row = _gh_base_row(1, idperson)
    row.update({"dag": 40, "dhh": 1, "ytn": monthly})
    return row


def _turnover_case(case_id: str, annual_turnover: float) -> Case:
    turnover_input = _presumptive_input("business_turnover")
    return Case(
        case_id=case_id,
        period=GH_PRESUMPTIVE_PERIOD,
        metadata={
            **GH_METADATA,
            "scenario": "single-small-business-presumptive-turnover",
            "annual_turnover": annual_turnover,
            # Placeholders; the post-uprating euromod ytn overwrites both via
            # the bridge so all engines price the identical turnover base.
            "axiom_inputs": {
                **_chrl_zero_inputs(),
                turnover_input: annual_turnover,
                _presumptive_input(
                    "presumptive_taxation_applies_as_referred_to_in_paragraph_2_1_c_ii"
                ): True,
                _presumptive_input(
                    "annual_turnover_average_for_three_consecutive_years"
                ): 0.0,
                _presumptive_input(
                    "turnover_calculated_using_modified_cash_basis"
                ): 0.0,
            },
            "euromod_inputs": [_gh_small_business(101, annual_turnover)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"ytn": [turnover_input]},
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
        outputs=(Concepts.GH_PRESUMPTIVE_TURNOVER_TAX,),
    )


def _chrl_case(case_id: str, annual_turnover: float) -> Case:
    """CHRL comparison at period 2025 — the levy's last live year."""
    supply_value_input = _chrl_input("taxable_supply_or_import_value")
    return Case(
        case_id=case_id,
        period=GH_PRESUMPTIVE_PERIOD,
        metadata={
            **GH_METADATA,
            "scenario": "single-small-business-chrl-2025",
            "annual_turnover": annual_turnover,
            "axiom_inputs": {
                **_presumptive_zero_inputs(),
                supply_value_input: annual_turnover,
                _chrl_input("supply_of_goods_or_services_made_in_country"): True,
                _chrl_input("supply_is_exempt_goods_or_services"): False,
                _chrl_input("import_of_goods_or_services"): False,
                _chrl_input("import_is_exempt_import"): False,
                _chrl_input("person_charges_value_added_tax_flat_rate"): False,
                _chrl_input("person_makes_supply_of_goods_or_services"): True,
            },
            "euromod_inputs": [_gh_small_business(101, annual_turnover)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"ytn": [supply_value_input]},
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
        outputs=(Concepts.GH_COVID_HEALTH_RECOVERY_LEVY,),
    )
