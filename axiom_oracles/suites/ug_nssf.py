"""Uganda NSSF contribution oracle suite (UGAMOD ``tscee_s``/``tscer_s``).

``ug-nssf-contributions`` compares the rulespec-ug NSSF standard
contribution module (Cap. 230: the fifteen percent employer-paid
standard contribution on monthly total wages, s.10, with the five
percent employee's share the employer may deduct, s.11; the
employer-net share is their derived difference) against UGAMOD's
``tscee_s`` (employee share) and ``tscer_s`` (employer share). Run live
exact on a 1.2m to 124.5m wage sweep at age 35 (no ceiling observed in
either engine) and at the probe income at ages 60 and 70, where both
engines still charge the full five and ten percent. Further uncommitted
probes at ages 15, 17, 55, 56, 65, 80 and 95 gave the same charge, so
UGAMOD applies no age window, in contrast to GHAMOD's age-15-45
contributor cap (rulespec-gh finding #4). The rulespec-ug s.10 module
has no age input either. Whether the Act limits contributions by age is
not settled here: the captured corpus holds only ss.10-12, not the
Act's definition of "eligible employee", and s.12(1)(b) requires a ten
percent special contribution, in place of the standard contribution,
for employees aged 55 or over only where the Minister has applied
s.12 to them by statutory order.

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

_BASE_AGE = 35

# (label, annual gross wages in post-uprating UGX, age): the PAYE probe
# income plus a low and a high earner at the base age (no ceiling
# observed to 124m/yr), then the probe income at older ages so the
# suite itself shows whether either engine stops charging the standard
# contribution with age.
_WAGE_GRID = (
    ("1200000-low", 1_200_000.0, _BASE_AGE),
    ("probe-income", 6_225_375.60, _BASE_AGE),
    ("12m", 12_000_000.0, _BASE_AGE),
    ("124m-high", 124_507_512.48, _BASE_AGE),
    ("probe-income-age-60", 6_225_375.60, 60),
    ("probe-income-age-70", 6_225_375.60, 70),
)


def ug_nssf_contributions_cases() -> list[Case]:
    """Single formal-sector employee NSSF cases for tscee_s/tscer_s."""
    return [
        _nssf_case(f"ug-nssf-{label}", wages, age)
        for label, wages, age in _WAGE_GRID
    ]


def _nssf_case(case_id: str, annual_wages: float, age: int) -> Case:
    wages_input = f"{NSSF_MODULE}#input.total_wages"
    row = _ug_formal_earner(101, annual_wages)
    row["dag"] = age
    return Case(
        case_id=case_id,
        period=UG_PERIOD,
        metadata={
            **UG_METADATA,
            "scenario": "single-formal-employee-nssf",
            "annual_total_wages": annual_wages,
            "axiom_inputs": {wages_input: annual_wages},
            "euromod_inputs": [row],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"yem": [wages_input]},
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: age,
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
