"""Form 1040 dividend and capital-gain-distribution semantics for the Case.

Every engine projection (PolicyEngine, Axiom, TAXSIM, Tax-Calculator and the
Axiom benefit mapping) reads dividends and capital gain distributions through
this module, so all of them price the same household from the same facts.

The Case carries these amounts the way Form 1040 (2025) reports them:

- ``Concepts.DIVIDEND_INCOME`` is line 3b, ordinary dividends. The 2025
  instructions for line 3b: "Enter your total ordinary dividends on line 3b.
  This amount should be shown in box 1a of Form(s) 1099-DIV."
- ``Concepts.QUALIFIED_DIVIDEND_INCOME`` is line 3a, which is part of line 3b,
  not an addition to it. The 2025 instructions for line 3a: "Qualified
  dividends are also included in the ordinary dividend total required to be
  shown on line 3b." Line 3a feeds line 2 of the Qualified Dividends and
  Capital Gain Tax Worksheet (26 USC 1(h)).
- ``Concepts.NON_SCHEDULE_D_CAPITAL_GAIN_DISTRIBUTIONS`` is line 7a on the
  no-Schedule-D path. The 2025 instructions for line 7a: "If Exception 1
  applies, enter your total capital gain distributions (from box 2a of
  Form(s) 1099-DIV) on line 7a and check the box 'Schedule D not required' on
  line 7b." Exception 1 requires that "You have no capital losses, and your
  only capital gains are capital gain distributions from Form(s) 1099-DIV,
  box 2a". A return that carries this concept therefore carries no Schedule D
  amounts (``SHORT_TERM_CAPITAL_GAINS``, ``LONG_TERM_CAPITAL_GAINS``); when
  Exception 1 fails, Exception 2 lists "Capital gain distributions" among the
  amounts reported on Schedule D, and 26 USC 852(b)(3)(B) treats a capital
  gain dividend "as a gain from the sale or exchange of a capital asset held
  for more than 1 year". :func:`fold_capital_gain_distributions_into_schedule_d`
  applies that rule to a producer's tax unit.

Where the amounts flow on the 2025 return (each engine must follow them):
line 3b and line 7a both enter total income (the Social Security Benefits
Worksheet, line 3, combines "lines 1z, 2b, 3b, 4b, 5b, 7a, and 8");
the Qualified Dividends and Capital Gain Tax Worksheet takes line 3a on its
line 2 and, when Schedule D is not filed, line 7a on its line 3; and the EIC
investment income (Pub. 596 Worksheet 1) takes line 3b on its line 3 and
line 7a (a loss entered as zero) on its line 5.

Amounts are never negative: they are payments reported on Form 1099-DIV.
The normalization below keeps a Case that violates the line 3a / line 3b
relation (qualified above ordinary, which some legacy rows carry) priced
identically by every engine: qualified dividends are floored at zero and
ordinary dividends are never less than the qualified part.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, MutableMapping
from dataclasses import dataclass
import math
from typing import Any

from .case import Concepts, Entity


@dataclass(frozen=True)
class Dividends:
    """Form 1040 lines 3b (``ordinary``) and 3a (``qualified``)."""

    ordinary: float = 0.0
    qualified: float = 0.0

    @property
    def non_qualified(self) -> float:
        """Ordinary dividends that are not qualified (line 3b less line 3a)."""

        return self.ordinary - self.qualified

    def __add__(self, other: "Dividends") -> "Dividends":
        return Dividends(
            ordinary=self.ordinary + other.ordinary,
            qualified=self.qualified + other.qualified,
        )


def person_dividends(person: Entity | Mapping[str, Any]) -> Dividends:
    """One person's line 3b / line 3a pair, normalized as the module states."""

    qualified = max(0.0, _fact(person, Concepts.QUALIFIED_DIVIDEND_INCOME))
    ordinary = max(qualified, _fact(person, Concepts.DIVIDEND_INCOME))
    return Dividends(ordinary=ordinary, qualified=qualified)


def sum_dividends(people: Iterable[Entity | Mapping[str, Any]]) -> Dividends:
    total = Dividends()
    for person in people:
        total = total + person_dividends(person)
    return total


def person_non_schedule_d_capital_gain_distributions(
    person: Entity | Mapping[str, Any],
) -> float:
    """One person's line 7a capital gain distributions (no Schedule D)."""

    return max(
        0.0,
        _fact(person, Concepts.NON_SCHEDULE_D_CAPITAL_GAIN_DISTRIBUTIONS),
    )


def sum_non_schedule_d_capital_gain_distributions(
    people: Iterable[Entity | Mapping[str, Any]],
) -> float:
    return sum(person_non_schedule_d_capital_gain_distributions(p) for p in people)


def normalized_investment_income_facts(facts: Mapping[str, Any]) -> dict[str, Any]:
    """A copy of person facts with the dividend and line 7a facts normalized.

    For projections that read facts by concept id (the Axiom benefit
    mapping), so they see exactly the amounts the tax projections see.
    Facts that are absent stay absent.
    """

    normalized = dict(facts)
    if Concepts.DIVIDEND_INCOME in facts or Concepts.QUALIFIED_DIVIDEND_INCOME in facts:
        dividends = person_dividends(facts)
        normalized[Concepts.DIVIDEND_INCOME] = dividends.ordinary
        normalized[Concepts.QUALIFIED_DIVIDEND_INCOME] = dividends.qualified
    if Concepts.NON_SCHEDULE_D_CAPITAL_GAIN_DISTRIBUTIONS in facts:
        normalized[Concepts.NON_SCHEDULE_D_CAPITAL_GAIN_DISTRIBUTIONS] = (
            person_non_schedule_d_capital_gain_distributions(facts)
        )
    return normalized


def fold_capital_gain_distributions_into_schedule_d(
    members: Iterable[MutableMapping[str, Any]],
) -> int:
    """Move a tax unit's line 7a distributions onto Schedule D when it files one.

    ``members`` are the mutable fact mappings of one tax unit's people. When
    any member carries a Schedule D amount (a nonzero short- or long-term
    capital gain or loss), Exception 1 does not apply, so each member's
    capital gain distributions are added to that member's long-term capital
    gains (26 USC 852(b)(3)(B)) and the no-Schedule-D fact is removed.
    Every engine aggregates capital gains over the tax unit, so folding at
    the tax unit guarantees no engine sees both paths at once. Returns the
    number of members whose distributions were folded.
    """

    members = list(members)
    files_schedule_d = any(
        _fact(member, Concepts.SHORT_TERM_CAPITAL_GAINS)
        or _fact(member, Concepts.LONG_TERM_CAPITAL_GAINS)
        for member in members
    )
    if not files_schedule_d:
        return 0
    folded = 0
    for member in members:
        distributions = person_non_schedule_d_capital_gain_distributions(member)
        member.pop(Concepts.NON_SCHEDULE_D_CAPITAL_GAIN_DISTRIBUTIONS, None)
        if not distributions:
            continue
        member[Concepts.LONG_TERM_CAPITAL_GAINS] = (
            _fact(member, Concepts.LONG_TERM_CAPITAL_GAINS) + distributions
        )
        folded += 1
    return folded


def _fact(person: Entity | Mapping[str, Any], concept: str) -> float:
    if isinstance(person, Entity):
        raw = person.fact(concept, 0)
    else:
        raw = person.get(concept, 0)
    if raw in (None, ""):
        return 0.0
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError(f"Case fact {concept} must be finite, got {raw!r}")
    return value
