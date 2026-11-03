"""Married-filing-separately facts, read one way for every projection.

The TAXSIM, Axiom and PolicyEngine projections each need to know whether a
Case is one spouse's separate return and, if so, whether the spouses lived
apart. Reading the facts through :func:`separate_filing` keeps the three
engines on the same interpretation, so a projection disagreement cannot
masquerade as an engine residue.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .case import Case, Concepts


@dataclass(frozen=True)
class SeparateFiling:
    """Resolved separate-return facts for one Case (one tax unit)."""

    married_filing_separately: bool
    lived_apart_from_spouse_all_year: bool
    spouse_absent_last_six_months: bool


def separate_filing(case: Case) -> SeparateFiling:
    """Resolve the Case's married-filing-separately facts.

    ``LIVED_APART_FROM_SPOUSE_ALL_YEAR`` defaults to False. An absent
    ``SPOUSE_ABSENT_LAST_SIX_MONTHS`` inherits the lived-apart value, since
    living apart all year implies the spouse was absent for the last six
    months. The lived-apart facts are only meaningful on a separate return,
    so setting either without ``MARRIED_FILING_SEPARATELY`` raises.
    """

    mfs = _bool_fact(case, Concepts.MARRIED_FILING_SEPARATELY, False)
    lived_apart = _bool_fact(case, Concepts.LIVED_APART_FROM_SPOUSE_ALL_YEAR, False)
    absent = _bool_fact(case, Concepts.SPOUSE_ABSENT_LAST_SIX_MONTHS, lived_apart)
    if lived_apart and not absent:
        raise ValueError(
            f"Case {case.case_id!r}: a spouse who lived apart all year cannot "
            "have been a household member in the last six months."
        )
    if not mfs and (
        case.fact(Concepts.LIVED_APART_FROM_SPOUSE_ALL_YEAR) is not None
        or case.fact(Concepts.SPOUSE_ABSENT_LAST_SIX_MONTHS) is not None
    ):
        raise ValueError(
            f"Case {case.case_id!r} sets spouse-residence facts without "
            f"{Concepts.MARRIED_FILING_SEPARATELY}."
        )
    return SeparateFiling(
        married_filing_separately=mfs,
        lived_apart_from_spouse_all_year=lived_apart,
        spouse_absent_last_six_months=absent,
    )


def _bool_fact(case: Case, concept: str, default: bool) -> bool:
    value: Any = case.fact(concept)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ValueError(
        f"Case {case.case_id!r}: {concept} must be a bool, got {value!r}."
    )
