from types import SimpleNamespace

from axiom_oracles import Case, Concepts, Entity
from axiom_oracles.adapters.accessnyc import AccessNycInputMapper, AccessNycPythonRunner
from axiom_oracles.adapters.policyengine import PolicyEngineRunner
from axiom_oracles.adapters.policyengine import runner as policyengine_runner_module
from axiom_oracles.comparison.comparator import Comparator
from axiom_oracles.comparison.mappings import (
    comparable_mappings,
    comparison_scope_for_targets,
    load_program_mappings,
)
from axiom_oracles.core.geography import GeographyScope
from axiom_oracles.core.household import Household, Person
from axiom_oracles.core.results import EngineResult
from axiom_oracles.suites import load_suite


def test_case_is_concept_keyed_and_projects_to_accessnyc_payload() -> None:
    case = Case(
        case_id="snap-case-1",
        period="2026-01",
        facts={Concepts.CASH_ON_HAND: 250},
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 30,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.YEARLY_EARNED_INCOME: 30_000,
                },
            ),
            Entity(
                entity_id="child",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 5,
                    Concepts.HOUSEHOLD_RELATION: "Child",
                },
            ),
        ),
        outputs=(Concepts.SNAP_ELIGIBLE,),
    )

    payload = AccessNycInputMapper().map_case(case)

    assert payload["household"][0]["caseId"] == "snap-case-1"
    assert payload["household"][0]["cashOnHand"] == "250.00"
    assert payload["person"][0]["age"] == 30
    assert payload["person"][0]["incomes"] == [
        {"amount": "30000.00", "frequency": "Yearly", "type": "Wages"}
    ]
    assert payload["person"][1]["householdMemberType"] == "Child"


def test_concept_mapping_compares_snap_amount_by_legal_id() -> None:
    mappings = load_program_mappings()
    left = [
        EngineResult(
            "axiom",
            "case-1",
            {Concepts.SNAP_BENEFIT: 120.00},
        )
    ]
    right = [EngineResult("policyengine", "case-1", {"snap": 120.50})]

    comparison = Comparator(mappings).compare(left, right)[0]
    snap = next(
        item for item in comparison.comparisons if item.variable == Concepts.SNAP_BENEFIT
    )

    assert snap.matches
    assert snap.difference == -0.5


def test_concept_mapping_compares_accessnyc_eligibility_code() -> None:
    mappings = load_program_mappings()
    left = [EngineResult("accessnyc", "case-1", {"S2R007": True})]
    right = [EngineResult("policyengine", "case-1", {"is_snap_eligible": True})]

    comparison = Comparator(mappings).compare(left, right)[0]
    snap = next(
        item for item in comparison.comparisons if item.variable == Concepts.SNAP_ELIGIBLE
    )

    assert snap.matches


def test_default_compare_concepts_are_engine_intersection_for_suite_locale() -> None:
    mappings = comparable_mappings(
        "accessnyc",
        "policyengine",
        load_program_mappings(),
        locales={"US-NY-NYC"},
    )

    concept_ids = {mapping.concept_id for mapping in mappings}

    assert Concepts.SNAP_ELIGIBLE in concept_ids
    assert Concepts.MEDICAID_ELIGIBLE not in concept_ids
    assert Concepts.MEDICAID_PREGNANT_WOMEN_ELIGIBLE not in concept_ids
    assert Concepts.CHILD_HEALTH_PLUS_ELIGIBLE not in concept_ids
    assert Concepts.SNAP_BENEFIT not in concept_ids
    assert Concepts.BASIC_HEALTH_PROGRAM_ELIGIBLE not in concept_ids


def test_accessnyc_targets_are_locale_filtered() -> None:
    mappings = comparable_mappings(
        "accessnyc",
        "policyengine",
        load_program_mappings(),
        locales={"US-CA"},
    )

    assert mappings == []


def test_accessnyc_policyengine_scope_intersection_is_nyc() -> None:
    assert comparison_scope_for_targets("accessnyc", "policyengine") == GeographyScope(
        type="census_place",
        geoid="3651000",
    )


def test_accessnyc_targets_are_scope_filtered() -> None:
    mappings = comparable_mappings(
        "accessnyc",
        "policyengine",
        load_program_mappings(),
        scope=GeographyScope(type="census_state", geoid="06"),
    )

    assert mappings == []


def test_nyc_suite_defines_cases_not_programs() -> None:
    cases = load_suite("nyc-basic")

    assert {case.locale for case in cases} == {"US-NY-NYC"}
    assert {case.scope for case in cases} == {
        GeographyScope(type="census_place", geoid="3651000")
    }
    assert all(not case.outputs for case in cases)
    assert all("_" not in str(case.case_id) for case in cases)


def test_nyc_synthetic_suite_has_triage_metadata() -> None:
    cases = load_suite("nyc-synthetic")

    assert len(cases) > len(load_suite("nyc-basic"))
    assert {case.locale for case in cases} == {"US-NY-NYC"}
    assert all(not case.outputs for case in cases)
    assert {case.metadata["scenario"] for case in cases} >= {
        "single-adult",
        "single-parent-infant",
        "pregnant-adult",
    }
    assert all("yearly_earned_income" in case.metadata for case in cases)
    assert all("ages" in case.metadata for case in cases)
    assert {case.period for case in cases} == {"2026-05"}


def test_accessnyc_python_runner_discovers_local_rule_codes(tmp_path) -> None:
    rules_dir = tmp_path / "src" / "rules" / "program_rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "S2R007.py").write_text("")
    (rules_dir / "S2R038.py").write_text("")
    (rules_dir / "__init__.py").write_text("")

    codes = AccessNycPythonRunner(repo_path=tmp_path).available_program_codes()

    assert codes == {"S2R007", "S2R038"}


def test_policyengine_projection_includes_pregnancy_fact() -> None:
    case = Case(
        case_id="pregnant-adult",
        period="2026",
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 30,
                    Concepts.PREGNANT: True,
                },
            ),
        ),
    )

    situation = PolicyEngineRunner()._build_situation_from_case(case)

    assert situation["people"]["head"]["is_pregnant"][2026] is True


def test_policyengine_projection_includes_case_scope_geography() -> None:
    case = Case(
        case_id="nyc-case",
        period="2026",
        metadata={"scope": {"type": "census_place", "geoid": "3651000"}},
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={Concepts.PERSON_AGE: 30},
            ),
        ),
    )

    household = PolicyEngineRunner()._build_situation_from_case(case)["households"][
        "household"
    ]

    assert household["state_fips"] == {2026: 36}
    assert household["place_fips"] == {2026: "51000"}


def test_policyengine_projection_includes_case_scope_for_income_tax() -> None:
    case = Case(
        case_id="county-tax-case",
        period="2026",
        metadata={"scope": {"type": "census_county", "geoid": "36061"}},
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={Concepts.PERSON_AGE: 30},
            ),
        ),
    )

    household = PolicyEngineRunner()._build_situation_from_case(
        case,
        variables=["income_tax"],
    )["households"]["household"]

    assert household["state_fips"] == {2026: 36}
    assert household["county_fips"] == {2026: "36061"}


def test_policyengine_projection_includes_state_scope_for_itemized_deductions() -> None:
    case = Case(
        case_id="county-tax-case",
        period="2026",
        metadata={"scope": {"type": "census_county", "geoid": "36061"}},
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={Concepts.PERSON_AGE: 30},
            ),
        ),
    )

    household = PolicyEngineRunner()._build_situation_from_case(
        case,
        variables=["itemized_taxable_income_deductions"],
    )["households"]["household"]

    assert household["state_fips"] == {2026: 36}
    assert "county_fips" not in household


def test_policyengine_projection_sets_tax_unit_head_and_spouse_roles() -> None:
    case = Case(
        case_id="explicit-couple-with-older-adult",
        period="2026",
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 40,
                },
            ),
            Entity(
                entity_id="spouse",
                kind="person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Spouse",
                    Concepts.PERSON_AGE: 38,
                },
            ),
            Entity(
                entity_id="other",
                kind="person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Other",
                    Concepts.PERSON_AGE: 70,
                    Concepts.BLIND: True,
                },
            ),
        ),
    )

    people = PolicyEngineRunner()._build_situation_from_case(case)["people"]

    assert people["head"]["is_tax_unit_head"] == {2026: True}
    assert people["head"]["is_tax_unit_spouse"] == {2026: False}
    assert people["spouse"]["is_tax_unit_head"] == {2026: False}
    assert people["spouse"]["is_tax_unit_spouse"] == {2026: True}
    assert people["other"]["is_tax_unit_head"] == {2026: False}
    assert people["other"]["is_tax_unit_spouse"] == {2026: False}


def test_policyengine_projection_keeps_adult_child_out_of_spouse_role() -> None:
    case = Case(
        case_id="adult-child",
        period="2026",
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 45,
                },
            ),
            Entity(
                entity_id="adult-child",
                kind="person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.PERSON_AGE: 23,
                },
            ),
        ),
    )

    people = PolicyEngineRunner()._build_situation_from_case(case)["people"]

    assert people["head"]["is_tax_unit_head"] == {2026: True}
    assert people["adult-child"]["is_tax_unit_head"] == {2026: False}
    assert people["adult-child"]["is_tax_unit_spouse"] == {2026: False}


def test_policyengine_runner_calculates_case_variables_at_case_period(
    monkeypatch,
) -> None:
    calls = []

    class StubUS:
        @staticmethod
        def calculate_household(**kwargs):
            calls.append((tuple(kwargs["extra_variables"]), kwargs["year"]))
            return {"household": {"is_wic_eligible": False}}

    monkeypatch.setattr(
        policyengine_runner_module,
        "_policyengine",
        lambda: SimpleNamespace(us=StubUS()),
    )
    case = Case(
        case_id="wic-period",
        period="2026-05",
        entities=(
            Entity(
                entity_id="child",
                kind="person",
                facts={Concepts.PERSON_AGE: 2},
            ),
        ),
    )

    PolicyEngineRunner().run_case(case, ["is_wic_eligible"])

    assert calls == [(("is_wic_eligible",), 2026)]


def test_policyengine_runner_calculates_annual_case_variables_at_year(
    monkeypatch,
) -> None:
    calls = []

    class StubUS:
        @staticmethod
        def calculate_household(**kwargs):
            calls.append((tuple(kwargs["extra_variables"]), kwargs["year"]))
            return {"tax_unit": {"income_tax": 0}}

    monkeypatch.setattr(
        policyengine_runner_module,
        "_policyengine",
        lambda: SimpleNamespace(us=StubUS()),
    )
    case = Case(
        case_id="tax-period",
        period="2026-05",
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={Concepts.PERSON_AGE: 40},
            ),
        ),
    )

    PolicyEngineRunner().run_case(case, ["income_tax"])

    assert calls == [(("income_tax",), 2026)]


def test_policyengine_household_projection_includes_pregnancy_fact() -> None:
    household = Household(
        household_id="pregnant-adult",
        people=(Person(age=30, pregnant=True),),
        year=2026,
    )

    situation = PolicyEngineRunner()._build_situation(household)

    assert situation["people"]["person_0"]["is_pregnant"][2026] is True
