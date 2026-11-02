#!/usr/bin/env python3
"""Reduce pinned NZ engine responses to the declared comparison cells.

This is the committed, deterministic port of the host-side arithmetic used by
``nz-lane/emtr_reproduction/run.py`` at ops commit ``bcf631b5``.  The selected
receipt covers the lone-parent Area 1 scenario at weekly wages 0 and 740.  The
engine requests are the cache-miss sequence emitted by ``ModelEvaluator``;
this module applies the same period conversions, benefit/IWTC host branch,
Best Start family aggregation, and component composition as
``ModelEvaluator.evaluate_state``.

Only raw, full engine responses enter this reducer.  No value from the source
comparison report or from the Treasury snapshot is accepted as a RuleSpec
result.
"""

from __future__ import annotations

from decimal import Decimal, getcontext
from typing import Any, Mapping

getcontext().prec = 40

SCENARIO_ID = "single_parent_three_children_area1_rent"
WEEKLY_WAGES = (0, 740)
WEEKS_IN_MODEL_YEAR = Decimal(365) / Decimal(7)
ORACLE_IWTC_WEEKLY_THRESHOLD = Decimal("1226.7") / Decimal("52.2")
ORACLE_SIX_DECIMAL_TOLERANCE = Decimal("0.0000005")

TAX_OUTPUT = (
    "nz:statutes/income_tax/schedule_1/individual_income_tax"
    "#individual_income_tax_before_credits"
)
ACC_OUTPUT = "nz:regulations/acc/earners_levy#acc_standard_earners_levy_including_gst"
SOLE_PARENT_OUTPUT = (
    "nz:statutes/social_security/main_benefits/rates"
    "#sole_parent_support_net_weekly_payment"
)
FTC_BEFORE_OUTPUT = (
    "nz:statutes/income_tax/family_scheme/tax_credits"
    "#family_tax_credit_before_abatement"
)
FTC_OUTPUT = (
    "nz:statutes/income_tax/family_scheme/tax_credits#family_tax_credit_after_abatement"
)
IWTC_BEFORE_OUTPUT = (
    "nz:statutes/income_tax/family_scheme/tax_credits"
    "#in_work_tax_credit_before_abatement"
)
IWTC_REMAINING_ABATEMENT_OUTPUT = (
    "nz:statutes/income_tax/family_scheme/tax_credits"
    "#wff_abatement_remaining_after_family_tax_credit"
)
MFTC_OUTPUT = (
    "nz:statutes/income_tax/family_scheme/tax_credits#minimum_family_tax_credit"
)
IETC_OUTPUT = (
    "nz:statutes/income_tax/credits/individual_credits#independent_earner_tax_credit"
)
WEP_RATE_OUTPUT = (
    "nz:statutes/social_security/winter_energy_payment/core"
    "#winter_energy_payment_rate_per_winter_period"
)
BEST_START_BEFORE_OUTPUT = (
    "nz:statutes/income_tax/family_scheme/tax_credits"
    "#best_start_tax_credit_before_abatement"
)
BEST_START_ABATEMENT_OUTPUT = (
    "nz:statutes/income_tax/family_scheme/tax_credits#best_start_credit_abatement"
)
AS_UNROUNDED_OUTPUT = (
    "nz:statutes/social_security/accommodation_supplement/core"
    "#accommodation_supplement_weekly_amount_before_rounding"
)

COMPARISON_COLUMNS = (
    "wage1_tax",
    "wage1_ACC_levy",
    "net_benefit",
    "FTC_abated",
    "IWTC_abated",
    "MFTC",
    "IETC_abated",
    "WinterEnergy",
    "BestStart_Total",
    "AS_Amount",
    "WFF_abated",
)

# These IDs are not arbitrary aliases: requests.json commits and
# ancestor-protects the exact cache-miss key set produced by the pinned host.
REQUESTS_BY_WAGE: dict[int, dict[str, str | None]] = {
    0: {
        "benefit": "golden-00",
        "tax_with_wage": "golden-01",
        "tax_without_wage": "golden-01",
        "acc": "golden-02",
        "family": "golden-03",
        "best_start": "golden-04",
        "ietc": "golden-05",
        "winter_energy": "golden-06",
        "as_statutory": "golden-08",
        "as_treasury_host": "golden-09",
    },
    740: {
        "benefit": "golden-10",
        "tax_with_wage": "golden-11",
        "tax_without_wage": "golden-12",
        "acc": "golden-13",
        "family": "golden-14",
        "best_start": "golden-15",
        "ietc": "golden-16",
        "winter_energy": None,
        "as_statutory": "golden-17",
        "as_treasury_host": "golden-18",
    },
}


class ReducerError(ValueError):
    """A committed response cannot be reduced under the pinned host contract."""


def decimal_text(value: Decimal) -> str:
    """Match the pinned host's stable, non-exponent decimal rendering."""

    if value.is_zero():
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _scalar(
    responses: Mapping[str, Mapping[str, Any]], request_id: str | None, output: str
) -> Decimal:
    if request_id is None:
        raise ReducerError(f"no engine request supplies {output}")
    try:
        response = responses[request_id]
        results = response["results"]
        item = results[0]["outputs"][output]
    except (KeyError, IndexError, TypeError) as exc:
        raise ReducerError(f"{request_id}: engine response omits {output}") from exc
    if not isinstance(results, list) or len(results) != 1:
        raise ReducerError(f"{request_id}: expected exactly one engine result")
    if item.get("kind") != "scalar":
        raise ReducerError(f"{request_id}: {output} is not a scalar")
    try:
        return Decimal(str(item["value"]["value"]))
    except (KeyError, TypeError, ArithmeticError) as exc:
        raise ReducerError(f"{request_id}: {output} has no decimal value") from exc


def reduce_states(
    responses: Mapping[str, Mapping[str, Any]],
) -> dict[int, dict[str, Decimal]]:
    """Apply the pinned host reduction to both selected weekly-wage states."""

    states: dict[int, dict[str, Decimal]] = {}
    for wage in WEEKLY_WAGES:
        ids = REQUESTS_BY_WAGE[wage]
        scheduled_benefit = _scalar(responses, ids["benefit"], SOLE_PARENT_OUTPUT)
        # IncomeExplorer's raw IWTC branch zeros the already-evaluated main
        # benefit once the scenario crosses its source-defined host threshold.
        net_benefit = (
            Decimal(0)
            if Decimal(wage) >= ORACLE_IWTC_WEEKLY_THRESHOLD
            else scheduled_benefit
        )

        tax_with_wage = _scalar(responses, ids["tax_with_wage"], TAX_OUTPUT)
        tax_without_wage = _scalar(responses, ids["tax_without_wage"], TAX_OUTPUT)
        wage_tax = (tax_with_wage - tax_without_wage) / WEEKS_IN_MODEL_YEAR
        acc = _scalar(responses, ids["acc"], ACC_OUTPUT) / WEEKS_IN_MODEL_YEAR

        ftc = _scalar(responses, ids["family"], FTC_OUTPUT) / WEEKS_IN_MODEL_YEAR
        iwtc_before = _scalar(responses, ids["family"], IWTC_BEFORE_OUTPUT) / Decimal(
            52
        )
        iwtc_remaining = (
            _scalar(responses, ids["family"], IWTC_REMAINING_ABATEMENT_OUTPUT)
            / WEEKS_IN_MODEL_YEAR
        )
        iwtc = max(Decimal(0), iwtc_before - iwtc_remaining)
        mftc = _scalar(responses, ids["family"], MFTC_OUTPUT) / Decimal(52)

        # Ages 0 and 1 are eligible. The host evaluates identical inputs once
        # through its cache, sums two before-abatement amounts, and subtracts
        # the single family abatement exactly once.
        best_start_before = _scalar(
            responses, ids["best_start"], BEST_START_BEFORE_OUTPUT
        )
        best_start_abatement = _scalar(
            responses, ids["best_start"], BEST_START_ABATEMENT_OUTPUT
        )
        best_start = (
            max(Decimal(0), Decimal(2) * best_start_before - best_start_abatement)
            / WEEKS_IN_MODEL_YEAR
        )

        ietc = _scalar(responses, ids["ietc"], IETC_OUTPUT) / WEEKS_IN_MODEL_YEAR
        winter = (
            _scalar(responses, ids["winter_energy"], WEP_RATE_OUTPUT)
            / WEEKS_IN_MODEL_YEAR
            if net_benefit > 0
            else Decimal(0)
        )
        accommodation = _scalar(responses, ids["as_statutory"], AS_UNROUNDED_OUTPUT)
        accommodation_aligned = _scalar(
            responses, ids["as_treasury_host"], AS_UNROUNDED_OUTPUT
        )
        states[wage] = {
            "wage1_tax": wage_tax,
            "wage1_ACC_levy": acc,
            "net_benefit": net_benefit,
            "FTC_abated": ftc,
            "IWTC_abated": iwtc,
            "MFTC": mftc,
            "IETC_abated": ietc,
            "WinterEnergy": winter,
            "BestStart_Total": best_start,
            "AS_Amount": accommodation,
            "WFF_abated": ftc + iwtc,
            "AS_Amount_treasury_host_aligned": accommodation_aligned,
        }
    return states


def comparison_cells(
    responses: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return the 22 exact declared RuleSpec cell values in canonical order."""

    states = reduce_states(responses)
    return [
        {
            "scenario_id": SCENARIO_ID,
            "weekly_wage": wage,
            "column": column,
            "rulespec_value": decimal_text(states[wage][column]),
        }
        for wage in WEEKLY_WAGES
        for column in sorted(COMPARISON_COLUMNS)
    ]


def classify(
    *,
    column: str,
    wage: int,
    treasury_state: Mapping[str, Decimal],
    rulespec_states: Mapping[int, Mapping[str, Decimal]],
) -> tuple[str, str]:
    """Port the pinned classifier branches needed by the selected 22 cells."""

    rulespec = rulespec_states[wage][column]
    treasury = treasury_state[column]
    if abs(rulespec - treasury) <= ORACLE_SIX_DECIMAL_TOLERANCE:
        return "match", "MATCH_SNAPSHOT_PRECISION"

    treasury_benefit = treasury_state["net_benefit"]
    rulespec_benefit = rulespec_states[wage]["net_benefit"]
    benefit_vintage_active = (treasury_benefit > 0 or rulespec_benefit > 0) and abs(
        treasury_benefit - rulespec_benefit
    ) > ORACLE_SIX_DECIMAL_TOLERANCE

    if column == "wage1_tax":
        return (
            ("b", "B_BENEFIT_GROSSUP_TAX")
            if benefit_vintage_active
            else ("d", "D_UNEXPLAINED")
        )
    if column == "wage1_ACC_levy":
        return "c", "C_ACC_ANNUAL_CENTS"
    if column == "net_benefit":
        return "b", "B_BENEFIT_VINTAGE"
    if column in {
        "FTC_abated",
        "IWTC_abated",
        "MFTC",
        "BestStart_Total",
        "WFF_abated",
    }:
        return "b", "B_WFF_VINTAGE"
    if column == "WinterEnergy":
        return (
            ("b", "B_WINTER_ENERGY_BENEFIT_GATE")
            if benefit_vintage_active
            else ("d", "D_UNEXPLAINED")
        )
    if column == "AS_Amount":
        aligned = rulespec_states[wage]["AS_Amount_treasury_host_aligned"]
        if abs(treasury - aligned) > ORACLE_SIX_DECIMAL_TOLERANCE:
            return "b", "B_AS_UPSTREAM_VINTAGE"
        if abs(aligned - rulespec) > ORACLE_SIX_DECIMAL_TOLERANCE:
            return "c", "C_AS_STATUTORY_HOST"
        return "d", "D_UNEXPLAINED"
    # The selected IETC cells are exact matches. Reaching this branch means a
    # response was tampered or the declared subset changed and must not inherit
    # a source classification by assertion.
    return "d", "D_UNEXPLAINED"
