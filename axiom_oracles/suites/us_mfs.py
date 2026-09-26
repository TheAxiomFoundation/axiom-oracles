"""Married-filing-separately (TAXSIM ``mstat`` 6) federal tax suite.

Thirteen synthetic Colorado returns, each one spouse's separate return at the
2026 law year. The Case carries the filer and any dependent child only: the
other spouse files their own return and is never an entity here, which the
MFS projections enforce (``axiom_oracles/core/case.py``,
``Concepts.MARRIED_FILING_SEPARATELY``). Every projection resolves the MFS and
spouse-residence facts through ``axiom_oracles.core.filing.separate_filing``.

The scope is the Colorado state (FIPS 08) rather than the nation because the
Axiom leg keeps federal liability, taxable income and tax before credits only
for Colorado households: ``_prepare_cases_for_engines`` in
``axiom_oracles/cli.py`` filters to ``_is_co_household`` whenever those
concepts are requested, since the oracle bridge's state-income-tax leg (used
for the SALT itemization choice) implements Colorado only.

Case families (ids are stable contracts; comparison reports key on them):

- ``childless-wages``: filer 40, wages only. The wage points straddle the
  26 USC 3101(b)(2) Additional Medicare Tax thresholds as encoded in the
  pinned rulespec-us ``us/statutes/26/3101/b/2.yaml`` ($125,000, one-half of
  the $250,000 joint amount, for a separate return; $200,000 otherwise), so
  $150,000 sits between them. At $450,000 and $750,000, taxable income net
  of the $16,100 separate-return standard deduction exceeds the $384,350
  separate-return 37% threshold, while $450,000 stays below the $640,600
  single threshold (pinned rulespec-us ``us/policies/irs/rev-proc-2025-32``
  ``standard-deduction.yaml`` and ``income-tax-brackets.yaml``).
- ``child-lived-apart``: filer 35 with an 8-year-old child, spouses lived
  apart all year (so, by the resolver's default, the spouse was also absent
  for the last six months of the year, 26 USC 7703(b)(3) and 32(d)(2)(C)(i)).
- ``social-security``: filer 70 with Social Security benefits. The
  cohabiting cases set ``LIVED_APART_FROM_SPOUSE_ALL_YEAR`` False, which
  selects the zero 26 USC 86(c)(1)(C) base amount; the lived-apart case sets
  it True, which selects the $25,000 86(c)(1)(A) base (pinned rulespec-us
  ``us/statutes/26/86.yaml``, ``social_security_base_amount``).
- ``childless-eitc``: filer 30, low wages across the childless EITC range.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.case import Case, Concepts, Entity

SUITE_NAME = "us-mfs"
PERIOD = "2026"
US_MFS_SCOPE = {"type": "census_state", "geoid": "08"}
US_MFS_METADATA = {"locale": "US", "scope": US_MFS_SCOPE}
US_MFS_FACTS = {
    Concepts.STATE_CODE: "CO",
    Concepts.MARRIED_FILING_SEPARATELY: True,
}


@dataclass(frozen=True)
class _MfsCase:
    case_id: str
    scenario: str
    filer_age: int
    wages: int
    social_security: int = 0
    child_ages: tuple[int, ...] = ()
    lived_apart_from_spouse_all_year: bool | None = None


_CASES: tuple[_MfsCase, ...] = (
    *(
        _MfsCase(f"mfs-wages-{wages}", "childless-wages", 40, wages)
        for wages in (40_000, 150_000, 250_000, 450_000, 750_000)
    ),
    *(
        _MfsCase(
            f"mfs-child-wages-{wages}",
            "child-lived-apart",
            35,
            wages,
            child_ages=(8,),
            lived_apart_from_spouse_all_year=True,
        )
        for wages in (15_000, 45_000)
    ),
    _MfsCase(
        "mfs-ss-cohabiting-wages-20000-ss-24000",
        "social-security",
        70,
        20_000,
        social_security=24_000,
        lived_apart_from_spouse_all_year=False,
    ),
    _MfsCase(
        "mfs-ss-cohabiting-ss-30000",
        "social-security",
        70,
        0,
        social_security=30_000,
        lived_apart_from_spouse_all_year=False,
    ),
    _MfsCase(
        "mfs-ss-lived-apart-wages-20000-ss-24000",
        "social-security",
        70,
        20_000,
        social_security=24_000,
        lived_apart_from_spouse_all_year=True,
    ),
    *(
        _MfsCase(f"mfs-eitc-wages-{wages}", "childless-eitc", 30, wages)
        for wages in (6_000, 11_000, 16_000)
    ),
)


def us_mfs_cases() -> list[Case]:
    """Married-filing-separately returns for the TAXSIM mstat-6 lanes."""

    return [_case(spec) for spec in _CASES]


def _case(spec: _MfsCase) -> Case:
    head_facts: dict[str, Any] = {
        Concepts.PERSON_AGE: spec.filer_age,
        Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
        Concepts.YEARLY_EARNED_INCOME: spec.wages,
    }
    if spec.social_security:
        head_facts[Concepts.SOCIAL_SECURITY_BENEFITS] = spec.social_security
    entities = [Entity(entity_id="head", kind="person", facts=head_facts)]
    for index, age in enumerate(spec.child_ages, start=1):
        entities.append(
            Entity(
                entity_id=f"child-{index}",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: age,
                    Concepts.HOUSEHOLD_RELATION: "Child",
                },
            )
        )

    facts: dict[str, Any] = dict(US_MFS_FACTS)
    if spec.lived_apart_from_spouse_all_year is not None:
        facts[Concepts.LIVED_APART_FROM_SPOUSE_ALL_YEAR] = (
            spec.lived_apart_from_spouse_all_year
        )
    return Case(
        case_id=spec.case_id,
        period=PERIOD,
        metadata={
            **US_MFS_METADATA,
            "suite": SUITE_NAME,
            "scenario": spec.scenario,
        },
        facts=facts,
        entities=tuple(entities),
    )
