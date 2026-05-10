from axiom_programs import Household, Person


single_parent = Household(
    household_id=1,
    year=2026,
    people=(
        Person.with_yearly_earnings(age=30, earnings=30_000),
        Person(age=5, relation="Child"),
    ),
)

single_adult = Household(
    household_id=2,
    year=2026,
    people=(Person.with_yearly_earnings(age=40, earnings=20_000),),
)
