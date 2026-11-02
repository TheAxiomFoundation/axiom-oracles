from __future__ import annotations

from ...core.case import Case, Concepts
from ...core.household import Household, MoneyAmount, Person


class AccessNycInputMapper:
    """Map shared household objects to Benefits Screening API payloads."""

    def map_case(self, case: Case) -> dict:
        return self.map_household(self.case_to_household(case))

    def map_household(self, household: Household) -> dict:
        return {
            "household": [self._map_household_fields(household)],
            "person": [self._map_person(person) for person in household.people],
            "withholdPayload": False,
        }

    def map_households(self, households: list[Household]) -> list[dict]:
        return [self.map_household(household) for household in households]

    def case_to_household(self, case: Case) -> Household:
        people = []
        for entity in case.entities_of_kind("person"):
            yearly_earnings = entity.fact(Concepts.YEARLY_EARNED_INCOME, 0) or 0
            incomes = ()
            if yearly_earnings:
                incomes = (MoneyAmount(float(yearly_earnings), "Yearly", "Wages"),)
            people.append(
                Person(
                    age=int(entity.fact(Concepts.PERSON_AGE, 0) or 0),
                    relation=str(
                        entity.fact(
                            Concepts.HOUSEHOLD_RELATION,
                            "HeadOfHousehold" if not people else "Child",
                        )
                    ),
                    pregnant=bool(entity.fact(Concepts.PREGNANT, False)),
                    blind=bool(entity.fact(Concepts.BLIND, False)),
                    disabled=bool(entity.fact(Concepts.DISABLED, False)),
                    veteran=bool(entity.fact(Concepts.VETERAN, False)),
                    benefits_medicaid=bool(
                        entity.fact(Concepts.BENEFITS_MEDICAID, False)
                    ),
                    benefits_medicaid_disability=bool(
                        entity.fact(Concepts.BENEFITS_MEDICAID_DISABILITY, False)
                    ),
                    incomes=incomes,
                )
            )

        return Household(
            household_id=case.case_id,
            year=int(str(case.period).split("-", 1)[0]),
            cash_on_hand=float(case.fact(Concepts.CASH_ON_HAND, 0) or 0),
            living_renting=bool(case.fact(Concepts.LIVING_RENTING, True)),
            living_owner=bool(case.fact(Concepts.LIVING_OWNER, False)),
            people=tuple(people),
        )

    def _map_household_fields(self, household: Household) -> dict:
        return {
            "caseId": str(household.household_id),
            "cashOnHand": f"{household.cash_on_hand:.2f}",
            "livingRentalType": household.living_rental_type,
            "livingRenting": household.living_renting,
            "livingOwner": household.living_owner,
            "livingStayingWithFriend": household.living_staying_with_friend,
            "livingHotel": household.living_hotel,
            "livingShelter": household.living_shelter,
            "livingPreferNotToSay": household.living_prefer_not_to_say,
        }

    def _map_person(self, person: Person) -> dict:
        payload = {
            "age": person.age,
            "student": person.student,
            "studentFulltime": person.student_fulltime,
            "pregnant": person.pregnant,
            "unemployed": person.unemployed,
            "unemployedWorkedLast18Months": (
                person.unemployed_worked_last_18_months
            ),
            "blind": person.blind,
            "disabled": person.disabled,
            "veteran": person.veteran,
            "benefitsMedicaid": person.benefits_medicaid,
            "benefitsMedicaidDisability": person.benefits_medicaid_disability,
            "householdMemberType": person.relation,
            "livingOwnerOnDeed": person.living_owner_on_deed,
            "livingRentalOnLease": person.living_rental_on_lease,
        }
        if person.incomes:
            payload["incomes"] = [self._map_money(item) for item in person.incomes]
        if person.expenses:
            payload["expenses"] = [self._map_money(item) for item in person.expenses]
        return payload

    @staticmethod
    def _map_money(item: MoneyAmount) -> dict[str, str]:
        return item.as_accessnyc()
