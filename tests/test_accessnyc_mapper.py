from axiom_oracles.adapters.accessnyc import AccessNycInputMapper
from axiom_oracles.core.household import Household, MoneyAmount, Person


def test_accessnyc_payload_shape() -> None:
    household = Household(
        household_id="case-1",
        cash_on_hand=500,
        people=(
            Person.with_yearly_earnings(
                age=30,
                earnings=30_000,
                living_rental_on_lease=True,
            ),
            Person(
                age=4,
                relation="Child",
                expenses=(MoneyAmount(200, "Monthly", "ChildCare"),),
            ),
        ),
    )

    payload = AccessNycInputMapper().map_household(household)

    assert payload["household"][0]["caseId"] == "case-1"
    assert payload["household"][0]["cashOnHand"] == "500.00"
    assert payload["person"][0]["householdMemberType"] == "HeadOfHousehold"
    assert payload["person"][0]["incomes"] == [
        {"amount": "30000.00", "frequency": "Yearly", "type": "Wages"}
    ]
    assert payload["person"][1]["householdMemberType"] == "Child"
    assert payload["person"][1]["expenses"] == [
        {"amount": "200.00", "frequency": "Monthly", "type": "ChildCare"}
    ]
