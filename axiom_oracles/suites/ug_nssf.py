"""Uganda NSSF contribution oracle suite (UGAMOD ``tscee_s``/``tscer_s``).

``ug-nssf-contributions`` compares the rulespec-ug NSSF standard
contribution module (Cap. 230: the fifteen percent employer-paid
standard contribution on monthly total wages, s.10, with the five
percent employee's share the employer may deduct, s.11; the
employer-net share is their derived difference) against UGAMOD's
``tscee_s`` (employee share) and ``tscer_s`` (employer share) — probed
exact at every tested income with no ceiling and no age window (in
contrast to GHAMOD's age-15-45 contributor cap, rulespec-gh finding #4).

License discipline as in ``ug_income_tax``.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .gh_income_tax import EUROMOD_TO_AXIOM_INPUT_BRIDGE
from .ug_income_tax import UG_METADATA, UG_PERIOD, _ug_formal_earner

NSSF_MODULE = (
    "ug:statutes/cap-230/national-social-security-fund-act/"
    "section-10-payment-of-standard-contribution-by-employers"
)

# Annual gross wages (post-uprating UGX): the PAYE probe income plus a
# low and a high earner (no ceiling observed to 124m/yr).
_WAGE_GRID = (
    ("1200000-low", 1_200_000.0),
    ("probe-income", 6_225_375.60),
    ("12m", 12_000_000.0),
    ("124m-high", 124_507_512.48),
)


def ug_nssf_contributions_cases() -> list[Case]:
    """Single formal-sector employee NSSF cases for tscee_s/tscer_s."""
    return [
        _nssf_case(f"ug-nssf-{label}", wages)
        for label, wages in _WAGE_GRID
    ]


def _nssf_case(case_id: str, annual_wages: float) -> Case:
    wages_input = f"{NSSF_MODULE}#input.total_wages"
    return Case(
        case_id=case_id,
        period=UG_PERIOD,
        metadata={
            **UG_METADATA,
            "scenario": "single-formal-employee-nssf",
            "annual_total_wages": annual_wages,
            "axiom_inputs": {wages_input: annual_wages},
            "euromod_inputs": [_ug_formal_earner(101, annual_wages)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"yem": [wages_input]},
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 35,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.YEARLY_EARNED_INCOME: annual_wages,
                },
            ),
        ),
        outputs=(
            Concepts.UG_NSSF_EMPLOYEE_SHARE,
            Concepts.UG_NSSF_EMPLOYER_NET_SHARE,
        ),
    )
