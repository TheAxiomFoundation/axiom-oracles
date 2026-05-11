from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MoneyAmount:
    amount: float
    frequency: str = "Yearly"
    type: str = "Wages"

    def as_accessnyc(self) -> dict[str, str]:
        return {
            "amount": f"{self.amount:.2f}",
            "frequency": self.frequency,
            "type": self.type,
        }


@dataclass(frozen=True)
class Person:
    age: int
    relation: str = "HeadOfHousehold"
    student: bool = False
    student_fulltime: bool = False
    pregnant: bool = False
    unemployed: bool = False
    unemployed_worked_last_18_months: bool = False
    blind: bool = False
    disabled: bool = False
    veteran: bool = False
    benefits_medicaid: bool = False
    benefits_medicaid_disability: bool = False
    living_owner_on_deed: bool = False
    living_rental_on_lease: bool = False
    incomes: tuple[MoneyAmount, ...] = field(default_factory=tuple)
    expenses: tuple[MoneyAmount, ...] = field(default_factory=tuple)

    @classmethod
    def with_yearly_earnings(
        cls,
        age: int,
        earnings: float,
        relation: str = "HeadOfHousehold",
        **kwargs: Any,
    ) -> "Person":
        incomes = ()
        if earnings:
            incomes = (MoneyAmount(earnings, "Yearly", "Wages"),)
        return cls(age=age, relation=relation, incomes=incomes, **kwargs)

    @property
    def yearly_earned_income(self) -> float:
        return sum(
            income.amount
            for income in self.incomes
            if income.frequency == "Yearly"
            and income.type in {"Wages", "SelfEmployment"}
        )


@dataclass(frozen=True)
class Household:
    people: tuple[Person, ...]
    household_id: int | str = 1
    year: int = 2026
    state: str = "NY"
    city: str = "NYC"
    county_fips: str | None = None
    cash_on_hand: float = 0
    living_renting: bool = True
    living_owner: bool = False
    living_rental_type: str = "MarketRate"
    living_staying_with_friend: bool = False
    living_hotel: bool = False
    living_shelter: bool = False
    living_prefer_not_to_say: bool = False

    def __post_init__(self) -> None:
        if not self.people:
            raise ValueError("Household must include at least one person")
        if len(self.people) > 8:
            raise ValueError("ACCESS NYC accepts at most 8 people per household")
        if not any(p.relation == "HeadOfHousehold" for p in self.people):
            raise ValueError("At least one person must be HeadOfHousehold")

    @property
    def size(self) -> int:
        return len(self.people)

    @property
    def total_yearly_earned_income(self) -> float:
        return sum(person.yearly_earned_income for person in self.people)

    @property
    def ages(self) -> list[int]:
        return [person.age for person in self.people]
