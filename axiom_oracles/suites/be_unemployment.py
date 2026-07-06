from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .be_worker import BE_METADATA

# Composed rulespec-be ordinary-unemployment pilot pipeline (RD 25.11.1991).
PILOT_MODULE = "be:regulations/unemployment/pilot_oracle_pipeline"
BENEFIT_MODULE = "be:regulations/unemployment/benefit_amount"
MINIMUM_MODULE = "be:regulations/unemployment/minimum_daily_amounts"
PAYABLE_MODULE = "be:regulations/unemployment/payable_amount"
EUROMOD_TO_AXIOM_INPUT_BRIDGE = "euromod_to_axiom_input_bridge"

# EUROMOD BE_2025 bun_be applies a 6-day-week average-daily-wage convention.
# The oracle bridge feeds EUROMOD's post-uprating prior wage (yempv_s) into the
# statute's average daily wage. The runner annualizes yempv_s (multiplies the
# monthly demo value by twelve), so the bridge divides by twelve months and by
# the standard 26 compensable days per month (312 in total) to recover the
# monthly-basis average daily wage, so both engines compute the ordinary
# benefit from the same gross prior wage.
COMPENSABLE_DAYS = 26
MONTHS_PER_YEAR = 12
YEMPV_S_TO_DAILY_WAGE_DIVISOR = COMPENSABLE_DAYS * MONTHS_PER_YEAR
AVERAGE_DAILY_WAGE_INPUT = (
    f"{BENEFIT_MODULE}#input.belgium_unemployment_average_daily_wage"
)


def be_unemployment_cases() -> list[Case]:
    """Belgium ordinary first-period unemployment cases for EUROMOD BE_2025.

    Each case is a single unemployed adult in the first indemnification month
    (``lunmy = 1``) whose prior wage sits in the Article 114 65% ordinary
    replacement band. The EUROMOD ``bun_be`` policy is switched on per run
    (``euromod_policy_switch_overrides``) because BE_2025 ships it off; its
    ``bun_s`` output stores one month of the ordinary benefit divided by twelve,
    so the runner's annualization (multiply by twelve) recovers a monthly
    benefit that is compared against the composed pilot's monthly ordinary
    payable amount. The prior-wage sweep straddles EUROMOD's stylised monthly
    highwage cap (3432.38 EUR/month) and the statute's Article 111 A1 daily
    wage cap (92.3956 EUR/day), so the sweep isolates the two engines' distinct
    wage-cap thresholds.
    """

    return [
        _single_ordinary_first_month_case("be-unemployment-single-2400", 2400.0),
        _single_ordinary_first_month_case("be-unemployment-single-2800", 2800.0),
        _single_ordinary_first_month_case("be-unemployment-single-3200", 3200.0),
        _single_ordinary_first_month_case("be-unemployment-single-3600", 3600.0),
    ]


def _single_ordinary_first_month_case(case_id: str, prior_monthly_wage: float) -> Case:
    return Case(
        case_id=case_id,
        period="2025",
        metadata={
            **BE_METADATA,
            "scenario": "single-ordinary-first-month-unemployment",
            "prior_monthly_wage": prior_monthly_wage,
            "euromod_inputs": [_euromod_unemployed_input(prior_monthly_wage)],
            "euromod_policy_switch_overrides": [("bun_be", True)],
            # Supply the pilot's ordinary-benefit composition inputs. The prior
            # average daily wage is bridged from EUROMOD's post-uprating yempv_s
            # (divided by the 26 compensable days) so both engines compute on the
            # same gross wage; the remaining inputs select the isolated household
            # status and the first ordinary indemnification month.
            "axiom_inputs": {
                _benefit_input("belgium_unemployment_article_111_wage_cap_selector"): 1,
                _minimum_input("belgium_unemployment_household_status_code"): 2,
                _minimum_input("belgium_unemployment_indemnification_month_number"): 1,
                _payable_input("belgium_unemployment_monthly_compensable_days"): (
                    COMPENSABLE_DAYS
                ),
                AVERAGE_DAILY_WAGE_INPUT: prior_monthly_wage / COMPENSABLE_DAYS,
            },
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yempv_s": {
                    "inputs": [AVERAGE_DAILY_WAGE_INPUT],
                    "divide_by": YEMPV_S_TO_DAILY_WAGE_DIVISOR,
                },
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
        outputs=(Concepts.BE_UNEMPLOYMENT_ORDINARY_BENEFIT,),
    )


def _euromod_unemployed_input(prior_monthly_wage: float) -> dict[str, float | int]:
    # A single unemployed adult receiving unemployment benefit (bun=1) in the
    # first month of the spell (lunmy=1), with a long enough work history
    # (liwmy, liwwh) to clear the qualifying period, and the prior employment
    # income carried in yempv (monthly).
    return {
        "idperson": 101,
        "idpartner": 0,
        "idmother": 0,
        "idfather": 0,
        "dag": 40,
        "dgn": 1,
        "dms": 1,
        "dec": 0,
        "les": 5,
        "lhw": 0,
        "loc": 5,
        "bun": 1,
        "lunmy": 1,
        "liwmy": 48,
        "liwwh": 40,
        "yem": 0,
        "yempv": prior_monthly_wage,
        "yivwg": prior_monthly_wage / (40 * 52 / 12),
        "yse": 0,
        "yiy": 0,
        "poa": 0,
    }


def _benefit_input(name: str) -> str:
    return f"{BENEFIT_MODULE}#input.{name}"


def _minimum_input(name: str) -> str:
    return f"{MINIMUM_MODULE}#input.{name}"


def _payable_input(name: str) -> str:
    return f"{PAYABLE_MODULE}#input.{name}"
