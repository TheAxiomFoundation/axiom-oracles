"""Arizona SNAP screener grid: synthetic households at each screener path's edges.

The ``az-snap-ecps`` comparison prices Arizona households drawn from the
populace artifact. Most of them are ineligible on both sides, and none
exercises utility allowances, dependent care, child support, homelessness,
resources, or the medical deduction band (axiom-oracles#700). This suite is
the complement: deterministic synthetic households, no microdata, that put
every fact a benefits screener collects at the boundaries where Arizona SNAP
changes its answer.

Every household lives in Arizona and is generated from a small base by one
*path block*. A block crosses only its own factors (full cross product of the
listed values); every other factor stays at the base value. That is the
pairing rule: one-factor-at-a-time sweeps around a fixed base, with a full
cross product inside each block. No randomness; case ids name their factors.

Base household of size ``n``: a head and ``n - 1`` children (ages cycle
through ``CHILD_AGES``), no shelter cost, no utilities, no expenses, no
resources. The head is 35 with unemployment compensation as unearned income
(non-elderly), 62 with Social Security (elderly, under the Medicare age so
PolicyEngine's modeled Part B premium stays out), or 45 with Social Security
disability benefits (disabled). Monthly gross income is a percentage of the
monthly HHS poverty guideline for ``n`` (48 states and DC), unrounded.

Income placement uses the FY2026 guideline year (2025 HHS guidelines), the
year in force at the comparison period 2026-01. ``households("fy2027")``
places the same grid on the FY2027 year (2026 guidelines) for a local run at
an FY2027 period; it is not a registered suite, so the canonical grid file
carries one copy. The shelter, minimum-benefit and resource blocks place
their edges with FY2026 SNAP amounts (``FY2026``); at other periods those
rows sit near, not on, the edge.

``PATHS`` records, for each block, the Axiom rules and PolicyEngine
variables it is meant to exercise. ``docs/az-snap-screener-grid.md`` explains
how to read a run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.case import Case, Concepts, Entity

SUITE_NAME = "us-az-snap-screener"
PERIOD = "2026-01"
AZ_SCOPE = {"type": "census_state", "geoid": "04"}
AZ_METADATA = {"locale": "US", "scope": AZ_SCOPE}

#: HHS poverty guidelines, 48 states and DC: (first person, each additional).
#: SNAP uses the guideline published in a calendar year from 1 October.
#: Both equal policyengine-us 1.767.3 ``snap_fpg`` x 12 at 2026-01 and 2026-10.
GUIDELINES = {
    "fy2026": (15_650, 5_500),
    "fy2027": (15_960, 5_680),
}

#: FY2026 SNAP amounts (USDA FNS FY2026 COLA, 48 states and DC) that place
#: the shelter, minimum-benefit and resource edges.
FY2026 = {
    "standard_deduction": {1: 209, 2: 209, 3: 209, 4: 223, 5: 261},
    "standard_deduction_6_plus": 299,
    "maximum_allotment": {1: 298, 2: 546},
    "shelter_cap": 744,
    "asset_limit_elderly_or_disabled": 4_500,
    "asset_limit_other": 3_000,
}

CHILD_AGES = (8, 3, 10, 5, 12, 1, 14, 6, 16)
SIZES = tuple(range(1, 11))
INCOME_PERCENTS = (0, 50, 129, 130, 131, 164, 165, 166, 184, 185, 186, 199, 200, 201)
MEDICAL_AMOUNTS = ("0", "35", "35.01", "100", "180", "180.01", "300")

HEAD_KINDS = {
    # kind: (age, disabled)
    "none": (35, False),
    "elderly": (62, False),
    "disabled": (45, True),
}


@dataclass(frozen=True)
class PathSpec:
    """What one block is meant to exercise on each side."""

    description: str
    axiom_rules: tuple[str, ...]
    policyengine_variables: tuple[str, ...]


PATHS: dict[str, PathSpec] = {
    "income": PathSpec(
        "Gross income at 129-131, 164-166, 184-186 and 199-201% of the "
        "guideline, sizes 1-10, earned or unearned, head non-elderly, "
        "elderly or disabled.",
        (
            "us-az:policies/des/faa5/na-categorical-eligibility (expanded "
            "categorical eligibility gross test)",
            "us:regulations/7-cfr/273/9 (130% gross and 100% net tests)",
            "us-az:policies/des/faa5/na-eligibility-and-benefit-determination "
            "(gross income test, block 5)",
            "us:regulations/7-cfr/273/10 (net income, allotment, earned "
            "income deduction)",
            "us:policies/usda/snap/fy-2026-cola (standards, maximum allotments)",
        ),
        (
            "meets_snap_categorical_eligibility",
            "meets_snap_gross_income_test",
            "meets_snap_net_income_test",
            "snap_gross_income",
            "snap_earned_income_deduction",
            "snap_max_allotment",
            "snap",
        ),
    ),
    "medical": PathSpec(
        "Elderly or disabled head with medical expenses at $0, $35, $35.01, "
        "$100, $180, $180.01 and $300 a month; controls without an elderly "
        "or disabled member, and a 70-year-old (Medicare Part B).",
        (
            "us:regulations/7-cfr/273/10 (snap_excess_medical_deduction_for_"
            "net_income; its operands are inputs on main)",
            "us-az:policies/des/faa5/na-medical-expenses-and-deduction/"
            "medical-deduction (Arizona SMD; in scope, not wired: "
            "rulespec-us#952)",
            "us:statutes/7/2012/j (elderly or disabled member)",
        ),
        (
            "snap_excess_medical_expense_deduction",
            "snap_allowable_medical_expenses",
            "other_medical_expenses",
            "medicare_part_b_premium",
            "is_usda_elderly",
            "is_usda_disabled",
        ),
    ),
    "shelter": PathSpec(
        "Shelter cost placing the excess shelter cost $1 below, at, $1 above "
        "and $300 above the FY2026 cap, with and without an elderly member "
        "(uncapped).",
        (
            "us:regulations/7-cfr/273/10 (snap_excess_shelter_cost, "
            "snap_excess_shelter_deduction_for_net_income)",
            "us-az:policies/des/faa5/shelter-expenses-and-deduction",
        ),
        (
            "snap_excess_shelter_expense_deduction",
            "housing_cost",
            "has_usda_elderly_disabled",
        ),
    ),
    "utility": PathSpec(
        "Standard (heating or cooling), limited (two other bills), telephone "
        "and no utility allowance, sizes 1-6, with and without rent and an "
        "elderly member.",
        (
            "us-az:policies/des/faa5/na-utility-expenses-and-allowances/"
            "utility-allowance-eligibility (SUA, LUA, telephone tests)",
            "us-az:policies/des/faa6/utility-allowance-current-amount",
            "us-az:policies/des/faa5/na-eligibility-and-benefit-determination/"
            "fy-2026-benefit-calculation (az_applied_utility_allowance, "
            "shelter_costs)",
        ),
        (
            "snap_utility_allowance_type",
            "snap_standard_utility_allowance",
            "snap_limited_utility_allowance",
            "snap_individual_utility_allowance",
            "snap_utility_allowance",
        ),
    ),
    "homeless": PathSpec(
        "Homeless household with $0, $100 and $250 of monthly shelter cost.",
        (
            "us:regulations/7-cfr/273/10 (snap_homeless_shelter_deduction_"
            "for_net_income)",
            "us:policies/usda/snap/fy-2026-cola/deductions "
            "(snap_homeless_shelter_deduction)",
        ),
        ("snap_excess_shelter_expense_deduction", "is_homeless"),
    ),
    "dependent_care": PathSpec(
        "Working head paying $0, $200 or $800 a month for a child aged 3 or "
        "10, at 50, 100 and 130% of the guideline.",
        (
            "us-az:policies/des/faa5/dependent-care-expense/na-dependent-care "
            "(snap_allowable_monthly_dependent_care_expenses)",
            "us:regulations/7-cfr/273/10 (snap_net_income_before_shelter)",
        ),
        ("snap_dependent_care_deduction", "childcare_expenses"),
    ),
    "child_support": PathSpec(
        "Head paying $0, $150 or $600 a month of child support, earned "
        "income at 50, 100, 129 and 131% of the guideline.",
        (
            "us:regulations/7-cfr/273/10 (snap_allowable_monthly_child_"
            "support_payments operand)",
            "us-az:policies/des/faa5/na-child-support-expense (in scope, "
            "not wired)",
        ),
        (
            "snap_child_support_deduction",
            "snap_child_support_gross_income_deduction",
            "child_support_expense",
        ),
    ),
    "income_mix": PathSpec(
        "Earned share of gross income 0, 25, 50, 75 and 100% at 50, 100 and "
        "129% of the guideline.",
        (
            "us:regulations/7-cfr/273/10 (snap_earned_income_deduction_for_"
            "net_income)",
            "us:regulations/7-cfr/273/9",
        ),
        ("snap_earned_income", "snap_unearned_income", "snap_earned_income_deduction"),
    ),
    "resources": PathSpec(
        "Elderly head above the expanded categorical eligibility limit (190 "
        "and 210%) with net income under 100% through shelter cost, liquid "
        "resources around the elderly/disabled limit; controls at 120% where "
        "categorical eligibility waives the test.",
        (
            "us:regulations/7-cfr/273/8 (snap_financial_resources_within_limit, "
            "snap_resource_limit_categorical_exemption_applies)",
            "us:policies/usda/snap/fy-2026-cola/deductions (snap_asset_limit)",
            "programs/us-az/snap/fy-2026 (az_ordinary_resource_and_income_"
            "eligible)",
        ),
        ("meets_snap_asset_test", "snap_assets", "bank_account_assets"),
    ),
    "minimum_benefit": PathSpec(
        "Sizes 1-2 whose computed allotment is 30, 25, 24, 23, 10, 1, 0 and "
        "-5 dollars before the minimum benefit.",
        (
            "us:regulations/7-cfr/273/10 (snap_monthly_allotment minimum "
            "benefit branch)",
            "us:policies/usda/snap/fy-2026-cola (snap_minimum_benefit)",
        ),
        ("snap_min_allotment", "snap_normal_allotment", "snap"),
    ),
}


@dataclass(frozen=True)
class _Household:
    case_id: str
    path: str
    size: int
    head_kind: str
    gross: float  # monthly
    earned_share: float = 1.0
    rent: float = 0.0  # monthly
    medical: float = 0.0  # monthly, on the head
    child_support: float = 0.0  # monthly, paid by the head
    dependent_care: float = 0.0  # monthly
    youngest_child_age: int | None = None
    heating: float = 0.0  # monthly bills
    electricity: float = 0.0
    water: float = 0.0
    phone: float = 0.0
    homeless: bool = False
    assets: float = 0.0
    head_age: int | None = None


def guideline_monthly(size: int, year: str = "fy2026") -> float:
    first, additional = GUIDELINES[year]
    return (first + additional * (size - 1)) / 12


def standard_deduction_fy2026(size: int) -> int:
    return FY2026["standard_deduction"].get(size, FY2026["standard_deduction_6_plus"])


def _money(value: float) -> float:
    return round(value + 0.0, 2)


def _income_block(year: str) -> list[_Household]:
    rows = []
    for size in SIZES:
        for percent in INCOME_PERCENTS:
            for kind in ("earned", "unearned"):
                if percent == 0 and kind == "unearned":
                    continue
                for head in HEAD_KINDS:
                    rows.append(
                        _Household(
                            f"azs-income-n{size}-p{percent}-{kind}-{head}",
                            "income",
                            size,
                            head,
                            _money(guideline_monthly(size, year) * percent / 100),
                            earned_share=1.0 if kind == "earned" else 0.0,
                        )
                    )
    return rows


def _medical_block(year: str) -> list[_Household]:
    rows = []
    for head in ("elderly", "disabled"):
        for size in (1, 3):
            for percent in (50, 100):
                for amount in MEDICAL_AMOUNTS:
                    rows.append(
                        _Household(
                            f"azs-medical-{head}-n{size}-p{percent}-m{amount}",
                            "medical",
                            size,
                            head,
                            _money(guideline_monthly(size, year) * percent / 100),
                            earned_share=0.0,
                            medical=float(amount),
                        )
                    )
    for size in (1, 3):
        for amount in ("100", "300"):
            rows.append(
                _Household(
                    f"azs-medical-none-n{size}-p50-m{amount}",
                    "medical",
                    size,
                    "none",
                    _money(guideline_monthly(size, year) * 0.5),
                    earned_share=0.0,
                    medical=float(amount),
                )
            )
    for percent in (50, 150):
        for amount in ("0", "100"):
            rows.append(
                _Household(
                    f"azs-medical-age70-n1-p{percent}-m{amount}",
                    "medical",
                    1,
                    "elderly",
                    _money(guideline_monthly(1, year) * percent / 100),
                    earned_share=0.0,
                    medical=float(amount),
                    head_age=70,
                )
            )
    return rows


def _shelter_block(year: str) -> list[_Household]:
    rows = []
    for size in (1, 3, 5):
        for head in ("none", "elderly"):
            for percent in (50, 100):
                gross = _money(guideline_monthly(size, year) * percent / 100)
                net_before_shelter = max(0.0, gross - standard_deduction_fy2026(size))
                for delta in (-1, 0, 1, 300):
                    rent = _money(
                        FY2026["shelter_cap"] + 0.5 * net_before_shelter + delta
                    )
                    rows.append(
                        _Household(
                            f"azs-shelter-{head}-n{size}-p{percent}-cap{delta:+d}",
                            "shelter",
                            size,
                            head,
                            gross,
                            earned_share=0.0,
                            rent=rent,
                        )
                    )
    return rows


UTILITY_TIERS = {
    "sua": {"heating": 100.0, "electricity": 60.0},
    "lua": {"electricity": 60.0, "water": 40.0},
    "telephone": {"phone": 50.0},
    "none": {},
}


def _utility_block(year: str) -> list[_Household]:
    rows = []
    for tier, bills in UTILITY_TIERS.items():
        for size in range(1, 7):
            for rent in (0, 600):
                for head in ("none", "elderly"):
                    rows.append(
                        _Household(
                            f"azs-utility-{tier}-n{size}-rent{rent}-{head}",
                            "utility",
                            size,
                            head,
                            _money(guideline_monthly(size, year) * 0.5),
                            earned_share=0.0,
                            rent=float(rent),
                            **bills,
                        )
                    )
    return rows


def _homeless_block(year: str) -> list[_Household]:
    return [
        _Household(
            f"azs-homeless-n{size}-p{percent}-shelter{shelter}",
            "homeless",
            size,
            "none",
            _money(guideline_monthly(size, year) * percent / 100),
            earned_share=0.0,
            rent=float(shelter),
            homeless=True,
        )
        for size in (1, 2, 4)
        for percent in (0, 50)
        for shelter in (0, 100, 250)
    ]


def _dependent_care_block(year: str) -> list[_Household]:
    return [
        _Household(
            f"azs-depcare-n{size}-child{age}-p{percent}-care{care}",
            "dependent_care",
            size,
            "none",
            _money(guideline_monthly(size, year) * percent / 100),
            earned_share=1.0,
            dependent_care=float(care),
            youngest_child_age=age,
        )
        for size in (2, 3, 4)
        for age in (3, 10)
        for percent in (50, 100, 130)
        for care in (0, 200, 800)
    ]


def _child_support_block(year: str) -> list[_Household]:
    return [
        _Household(
            f"azs-childsupport-n{size}-p{percent}-paid{paid}",
            "child_support",
            size,
            "none",
            _money(guideline_monthly(size, year) * percent / 100),
            earned_share=1.0,
            child_support=float(paid),
        )
        for size in (1, 2, 3)
        for percent in (50, 100, 129, 131)
        for paid in (0, 150, 600)
    ]


def _income_mix_block(year: str) -> list[_Household]:
    return [
        _Household(
            f"azs-mix-n{size}-p{percent}-earned{share}",
            "income_mix",
            size,
            "none",
            _money(guideline_monthly(size, year) * percent / 100),
            earned_share=share / 100,
        )
        for size in (1, 2, 4)
        for percent in (50, 100, 129)
        for share in (0, 25, 50, 75, 100)
    ]


def _resource_block(year: str) -> list[_Household]:
    rows = []
    limit = FY2026["asset_limit_elderly_or_disabled"]
    for size in (1, 2):
        for percent in (190, 210):
            gross = _money(guideline_monthly(size, year) * percent / 100)
            net_before_shelter = gross - standard_deduction_fy2026(size)
            # Excess shelter (uncapped: elderly head) that leaves net income
            # at 80% of the guideline.
            excess = net_before_shelter - 0.8 * guideline_monthly(size, year)
            rent = _money(excess + 0.5 * net_before_shelter)
            for assets in (0, limit - 1, limit, limit + 1, 10_000):
                rows.append(
                    _Household(
                        f"azs-resources-elderly-n{size}-p{percent}-assets{assets}",
                        "resources",
                        size,
                        "elderly",
                        gross,
                        earned_share=0.0,
                        rent=rent,
                        assets=float(assets),
                    )
                )
    other = FY2026["asset_limit_other"]
    for assets in (0, other - 1, other + 1, 50_000):
        rows.append(
            _Household(
                f"azs-resources-none-n2-p120-assets{assets}",
                "resources",
                2,
                "none",
                _money(guideline_monthly(2, year) * 1.2),
                earned_share=1.0,
                assets=float(assets),
            )
        )
    return rows


def _minimum_benefit_block(year: str) -> list[_Household]:
    rows = []
    for size in (1, 2):
        maximum = FY2026["maximum_allotment"][size]
        for target in (30, 25, 24, 23, 10, 1, 0, -5):
            # Allotment before minimums = maximum - 30% of net income (no
            # shelter): net = (maximum - target) / 0.3.
            net = (maximum - target) / 0.3
            gross = _money(net + standard_deduction_fy2026(size))
            rows.append(
                _Household(
                    f"azs-minbenefit-n{size}-target{target}",
                    "minimum_benefit",
                    size,
                    "none",
                    gross,
                    earned_share=0.0,
                )
            )
    return rows


_BLOCKS = (
    _income_block,
    _medical_block,
    _shelter_block,
    _utility_block,
    _homeless_block,
    _dependent_care_block,
    _child_support_block,
    _income_mix_block,
    _resource_block,
    _minimum_benefit_block,
)


def households(year: str = "fy2026") -> list[_Household]:
    rows = [row for block in _BLOCKS for row in block(year)]
    ids = [row.case_id for row in rows]
    if len(ids) != len(set(ids)):
        raise RuntimeError("screener grid case ids must be unique")
    return rows


def us_az_snap_screener_cases() -> list[Case]:
    """Screener grid with income placed on the FY2026 guideline year."""
    return [_case(row) for row in households("fy2026")]


def us_az_snap_screener_fy2027_cases() -> list[Case]:
    """Screener grid with income placed on the FY2027 guideline year.

    Not registered as a suite (see the module docstring)."""
    return [_case(row) for row in households("fy2027")]


def _case(row: _Household) -> Case:
    age, disabled = HEAD_KINDS[row.head_kind]
    if row.head_age is not None:
        age = row.head_age
    annual_gross = row.gross * 12
    earned = _money(annual_gross * row.earned_share)
    unearned = _money(annual_gross - earned)
    head_facts: dict[str, Any] = {
        Concepts.PERSON_AGE: age,
        Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
    }
    if disabled:
        head_facts[Concepts.DISABLED] = True
        # USDA disability needs a disability benefit: the head gets at least
        # $100 a month of Social Security disability, inside gross income.
        ssdi = _money(max(unearned, min(1_200.0, annual_gross)))
        earned = _money(annual_gross - ssdi)
        if ssdi > 0:
            head_facts[Concepts.SOCIAL_SECURITY_BENEFITS] = ssdi
            head_facts[Concepts.SOCIAL_SECURITY_DISABILITY_BENEFITS] = ssdi
    elif unearned > 0:
        concept = (
            Concepts.SOCIAL_SECURITY_BENEFITS
            if row.head_kind == "elderly"
            else Concepts.UNEMPLOYMENT_INSURANCE_INCOME
        )
        head_facts[concept] = unearned
    head_facts[Concepts.YEARLY_EARNED_INCOME] = earned
    for concept, monthly in (
        (Concepts.OUT_OF_POCKET_MEDICAL_EXPENSES, row.medical),
        (Concepts.CHILD_SUPPORT_PAID, row.child_support),
    ):
        if monthly:
            head_facts[concept] = _money(monthly * 12)
    entities = [Entity(entity_id="head", kind="person", facts=head_facts)]
    child_ages = list(CHILD_AGES[: row.size - 1])
    if row.youngest_child_age is not None and child_ages:
        # The cared-for child is the youngest; older siblings keep the base
        # ages, raised to at least that age.
        youngest = row.youngest_child_age
        child_ages = [youngest] + [max(age, youngest) for age in child_ages[1:]]
    for index, child_age in enumerate(child_ages, start=1):
        entities.append(
            Entity(
                entity_id=f"child-{index}",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: child_age,
                    Concepts.HOUSEHOLD_RELATION: "Child",
                },
            )
        )
    # Every screener Case sets DEPENDENT_CARE_PAID, even at 0: it overrides
    # PolicyEngine's childcare_expenses formula. The other screener facts
    # appear only when non-zero (absent reads as 0 or false on both sides).
    facts: dict[str, Any] = {
        Concepts.STATE_CODE: "AZ",
        Concepts.DEPENDENT_CARE_PAID: _money(row.dependent_care * 12),
    }
    for concept, value in (
        (Concepts.RENT_PAID, _money(row.rent * 12)),
        (Concepts.HEATING_COOLING_EXPENSE, _money(row.heating * 12)),
        (Concepts.ELECTRICITY_EXPENSE, _money(row.electricity * 12)),
        (Concepts.WATER_EXPENSE, _money(row.water * 12)),
        (Concepts.PHONE_EXPENSE, _money(row.phone * 12)),
        (Concepts.LIQUID_ASSETS, _money(row.assets)),
    ):
        if value:
            facts[concept] = value
    if row.homeless:
        facts[Concepts.HOMELESS] = True
    return Case(
        case_id=row.case_id,
        period=PERIOD,
        facts=facts,
        entities=tuple(entities),
        metadata={**AZ_METADATA, "screener_path": row.path},
    )


def path_of(case: Case) -> str:
    return str(case.metadata.get("screener_path", ""))


__all__ = [
    "PATHS",
    "SUITE_NAME",
    "households",
    "path_of",
    "us_az_snap_screener_cases",
    "us_az_snap_screener_fy2027_cases",
]
