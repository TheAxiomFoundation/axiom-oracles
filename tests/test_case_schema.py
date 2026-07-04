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
    # Axiom maps the SNAP benefit concept to the composed payable benefit,
    # not the imported federal monthly-allotment diagnostic, so state
    # eligibility gates can zero out ineligible households.
    snap_target = "snap_benefit"
    left = [
        EngineResult(
            "axiom",
            "case-1",
            {snap_target: 120.00},
        )
    ]
    right = [EngineResult("policyengine", "case-1", {"snap_normal_allotment": 120.50})]

    comparison = Comparator(mappings).compare(left, right)[0]
    snap = next(
        item
        for item in comparison.comparisons
        if item.variable == Concepts.SNAP_BENEFIT
    )

    assert snap.matches
    assert snap.difference == -0.5


def test_concept_mapping_compares_accessnyc_eligibility_code() -> None:
    mappings = load_program_mappings()
    left = [EngineResult("accessnyc", "case-1", {"S2R007": True})]
    right = [EngineResult("policyengine", "case-1", {"is_snap_eligible": True})]

    comparison = Comparator(mappings).compare(left, right)[0]
    snap = next(
        item
        for item in comparison.comparisons
        if item.variable == Concepts.SNAP_ELIGIBLE
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


def test_component_concepts_can_be_selected_directly() -> None:
    mappings = comparable_mappings(
        "axiom",
        "policyengine",
        concepts={Concepts.EITC},
    )

    assert [mapping.concept_id for mapping in mappings] == [Concepts.EITC]


def test_parent_concepts_do_not_expand_components_by_default() -> None:
    mappings = comparable_mappings(
        "axiom",
        "policyengine",
        concepts={Concepts.FEDERAL_INCOME_TAX},
    )

    assert [mapping.concept_id for mapping in mappings] == [Concepts.FEDERAL_INCOME_TAX]


def test_parent_concepts_expand_components_when_requested() -> None:
    mappings = comparable_mappings(
        "axiom",
        "policyengine",
        concepts={Concepts.FEDERAL_INCOME_TAX},
        include_components=True,
    )

    assert [mapping.concept_id for mapping in mappings] == [
        Concepts.FEDERAL_INCOME_TAX,
        Concepts.STANDARD_DEDUCTION,
        Concepts.TAXABLE_INCOME,
        Concepts.TAX_BEFORE_CREDITS,
        Concepts.NONREFUNDABLE_CREDITS,
        Concepts.EITC,
        Concepts.CTC,
        Concepts.CDCC,
        Concepts.AOTC,
        Concepts.AMT,
        Concepts.CAPITAL_GAIN,
        Concepts.EMPLOYEE_OASDI,
        Concepts.EMPLOYEE_MEDICARE,
        Concepts.EMPLOYER_OASDI,
        Concepts.EMPLOYER_MEDICARE,
    ]


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


def test_axiom_euromod_scope_intersection_is_country_ambiguous() -> None:
    assert comparison_scope_for_targets("axiom", "euromod") is None


def test_belgium_euromod_concepts_are_locale_filtered() -> None:
    mappings = comparable_mappings(
        "axiom",
        "euromod",
        load_program_mappings(),
        locales={"BE"},
    )

    assert {mapping.concept_id for mapping in mappings} == {
        Concepts.BE_WORKER_PIT_BEFORE_WITHHOLDING,
        Concepts.BE_EMPLOYEE_SOCIAL_CONTRIBUTIONS_BEFORE_REDUCTIONS,
        Concepts.BE_EMPLOYEE_WORK_BONUS_REDUCTION,
        Concepts.BE_EMPLOYEE_SOCIAL_CONTRIBUTIONS,
        Concepts.BE_SOCIAL_INTEGRATION_INCOME_SUPPORT,
        Concepts.BE_INCOME_GUARANTEE_FOR_ELDERLY,
        Concepts.BE_SELF_EMPLOYED_SOCIAL_CONTRIBUTIONS,
        Concepts.BE_SPECIAL_SOCIAL_SECURITY_CONTRIBUTION,
        Concepts.BE_FLEMISH_SOCIAL_PROTECTION_PREMIUM,
        Concepts.BE_FAMILY_BIRTH_ALLOWANCE,
        Concepts.BE_FAMILY_CHILD_BENEFIT_BASE,
    }

    assert (
        comparable_mappings(
            "axiom",
            "euromod",
            load_program_mappings(),
            locales={"US-NY-NYC"},
        )
        == []
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


def test_belgium_worker_suites_define_oracle_concepts_and_inputs() -> None:
    pit_cases = load_suite("be-worker-pit")
    ssc_cases = load_suite("be-worker-ssc")

    assert {case.locale for case in pit_cases + ssc_cases} == {"BE"}
    assert {case.scope for case in pit_cases + ssc_cases} == {
        GeographyScope(type="country", geoid="BE")
    }
    assert {case.outputs for case in pit_cases} == {
        (Concepts.BE_WORKER_PIT_BEFORE_WITHHOLDING,)
    }
    assert [case.metadata["yearly_earned_income"] for case in pit_cases] == [
        10_000,
        30_000,
        60_000,
    ]
    assert {case.outputs for case in ssc_cases} == {
        (
            Concepts.BE_EMPLOYEE_SOCIAL_CONTRIBUTIONS_BEFORE_REDUCTIONS,
            Concepts.BE_EMPLOYEE_WORK_BONUS_REDUCTION,
            Concepts.BE_EMPLOYEE_SOCIAL_CONTRIBUTIONS,
        )
    }
    assert all(case.metadata["axiom_entity"] == "Person" for case in pit_cases)
    assert all(
        "#input." in key for case in pit_cases for key in case.metadata["axiom_inputs"]
    )
    assert all(
        "#input." in key for case in ssc_cases for key in case.metadata["axiom_inputs"]
    )
    assert all("euromod_inputs" in case.metadata for case in pit_cases + ssc_cases)


def test_belgium_self_employed_suite_defines_oracle_concept_and_inputs() -> None:
    cases = load_suite("be-self-employed-ssc")

    assert len(cases) == 7
    assert {case.locale for case in cases} == {"BE"}
    assert {case.scope for case in cases} == {
        GeographyScope(type="country", geoid="BE")
    }
    assert {case.outputs for case in cases} == {
        (Concepts.BE_SELF_EMPLOYED_SOCIAL_CONTRIBUTIONS,)
    }
    assert all(case.metadata["axiom_entity"] == "Person" for case in cases)
    assert all(case.metadata["axiom_entity_id"] == "head" for case in cases)
    assert all(
        "#input." in key for case in cases for key in case.metadata["axiom_inputs"]
    )
    assert {case.metadata["scenario"] for case in cases} == {
        "single-main-activity-self-employed-ssc",
        "secondary-activity-self-employed-ssc",
        "post-pension-self-employed-ssc",
    }

    cases_by_id = {str(case.case_id): case for case in cases}
    main_30k = cases_by_id["be-self-employed-ssc-30k"]
    assert (
        main_30k.metadata["axiom_inputs"][
            "be:regulations/social_security/self_employed/contributions#input."
            "belgium_self_employed_gross_professional_income"
        ]
        == 30_000
    )
    assert main_30k.metadata["euromod_to_axiom_input_bridge"] == {
        "yse": [
            "be:regulations/social_security/self_employed/contributions#input."
            "belgium_self_employed_gross_professional_income"
        ]
    }
    assert main_30k.metadata["euromod_inputs"][0]["yse"] == 2_500

    secondary = cases_by_id["be-self-employed-ssc-secondary-10k"]
    assert secondary.metadata["euromod_inputs"][0]["yem"] == 1_000
    assert (
        secondary.metadata["axiom_inputs"][
            "be:regulations/social_security/self_employed/contributions#input."
            "belgium_self_employed_is_secondary_activity"
        ]
        is True
    )

    post_pension = cases_by_id["be-self-employed-ssc-post-pension-10k"]
    assert post_pension.metadata["euromod_inputs"][0]["dag"] == 66
    assert post_pension.metadata["euromod_inputs"][0]["poa"] == 1_000
    assert (
        post_pension.metadata["axiom_inputs"][
            "be:regulations/social_security/self_employed/contributions#input."
            "belgium_self_employed_receives_retirement_or_survivor_pension"
        ]
        is True
    )
    assert {case.period for case in cases} == {"2025"}


def test_belgium_special_social_security_suite_defines_oracle_concept_and_inputs() -> (
    None
):
    cases = load_suite("be-special-social-security-contribution")

    assert len(cases) == 7
    assert {case.locale for case in cases} == {"BE"}
    assert {case.scope for case in cases} == {
        GeographyScope(type="country", geoid="BE")
    }
    assert {case.outputs for case in cases} == {
        (Concepts.BE_SPECIAL_SOCIAL_SECURITY_CONTRIBUTION,)
    }
    assert all(case.metadata["axiom_entity"] == "Household" for case in cases)
    assert all(case.metadata["axiom_entity_id"] == "household" for case in cases)
    assert all(
        "#input." in key for case in cases for key in case.metadata["axiom_inputs"]
    )
    assert {case.metadata["scenario"] for case in cases} == {
        "single-worker-special-social-security-contribution",
        "joint-worker-special-social-security-contribution",
    }

    by_id = {case.case_id: case for case in cases}
    single_30k = by_id["be-special-social-security-single-30k"]
    household_income_input = (
        "be:statutes/social_security/special_contribution#input."
        "belgium_special_social_security_article_107_household_income"
    )
    assert single_30k.metadata["axiom_inputs"][household_income_input] == 30_000
    assert single_30k.metadata["euromod_to_axiom_input_bridge"] == {
        "il_taxabley": [household_income_input]
    }
    assert single_30k.metadata["euromod_inputs"][0]["yem"] == 2_500
    assert (
        single_30k.metadata["axiom_inputs"][
            "be:statutes/social_security/special_contribution#input."
            "belgium_special_social_security_joint_assessment"
        ]
        is False
    )

    joint = by_id["be-special-social-security-joint-two-earner-30k-20k"]
    assert len(joint.metadata["euromod_inputs"]) == 2
    assert joint.metadata["euromod_inputs"][0]["idpartner"] == 102
    assert joint.metadata["euromod_inputs"][1]["idpartner"] == 101
    assert (
        joint.metadata["axiom_inputs"][
            "be:statutes/social_security/special_contribution#input."
            "belgium_special_social_security_joint_assessment"
        ]
        is True
    )
    assert {case.period for case in cases} == {"2025"}


def test_belgium_flemish_social_protection_suite_defines_oracle_concept_and_inputs() -> (
    None
):
    cases = load_suite("be-flemish-social-protection-premium")

    assert len(cases) == 2
    assert {case.locale for case in cases} == {"BE"}
    assert {case.scope for case in cases} == {
        GeographyScope(type="country", geoid="BE")
    }
    assert {case.outputs for case in cases} == {
        (Concepts.BE_FLEMISH_SOCIAL_PROTECTION_PREMIUM,)
    }
    assert all(case.metadata["axiom_entity"] == "Person" for case in cases)
    assert all(case.metadata["axiom_entity_id"] == "head" for case in cases)
    assert all(
        "#input." in key for case in cases for key in case.metadata["axiom_inputs"]
    )
    assert all(
        case.metadata["axiom_inputs"][
            "be-vlg:regulations/social_security/flemish_social_protection/premium#input."
            "flanders_social_protection_premium_year"
        ]
        == 2025
        for case in cases
    )
    by_id = {case.case_id: case for case in cases}
    ordinary = by_id["be-flemish-social-protection-premium-ordinary-adult"]
    reduced = by_id["be-flemish-social-protection-premium-reduced-adult"]
    increased_reimbursement_input = (
        "be-vlg:regulations/social_security/flemish_social_protection/premium#input."
        "flanders_social_protection_has_increased_health_insurance_reimbursement_on_previous_january_1"
    )
    assert ordinary.metadata["axiom_inputs"][increased_reimbursement_input] is False
    assert reduced.metadata["axiom_inputs"][increased_reimbursement_input] is True
    assert ordinary.metadata["euromod_inputs"][0]["drgn1"] == 2
    assert ordinary.metadata["euromod_inputs"][0]["yem"] == 5_000
    assert reduced.metadata["euromod_inputs"][0]["bsa"] == 1
    assert {case.period for case in cases} == {"2025"}


def test_belgium_family_birth_allowance_suite_defines_oracle_concept_and_inputs() -> (
    None
):
    cases = load_suite("be-family-birth-allowance")

    assert len(cases) == 7
    assert {case.locale for case in cases} == {"BE"}
    assert {case.scope for case in cases} == {
        GeographyScope(type="country", geoid="BE")
    }
    assert {case.outputs for case in cases} == {
        (Concepts.BE_FAMILY_BIRTH_ALLOWANCE,)
    }
    assert all(case.metadata["axiom_entity"] == "Household" for case in cases)
    assert all(case.metadata["axiom_entity_id"] == "household" for case in cases)
    assert all(
        "#input." in key for case in cases for key in case.metadata["axiom_inputs"]
    )
    assert {case.metadata["scenario"] for case in cases} == {
        "brussels-first-child-or-multiple-birth",
        "brussels-later-child",
        "flanders-first-child",
        "flanders-later-child",
        "wallonia-first-child",
        "wallonia-later-child",
        "german-speaking-community-not-yet-encoded",
    }

    by_id = {case.case_id: case for case in cases}
    brussels_first = by_id["be-family-birth-allowance-brussels-first-newborn"]
    brussels_later = by_id["be-family-birth-allowance-brussels-later-newborn"]
    german_zero = by_id["be-family-birth-allowance-german-region-newborn-zero"]
    first_or_multiple_input = (
        "be:statutes/family_benefits/birth_allowance#input."
        "belgium_family_benefits_birth_allowance_brussels_first_child_or_multiple_birth"
    )
    region_input = (
        "be:statutes/family_benefits/birth_allowance#input."
        "belgium_family_benefits_birth_allowance_region"
    )
    child_age_input = (
        "be:statutes/family_benefits/birth_allowance#input."
        "belgium_family_benefits_birth_allowance_child_age_years"
    )
    assert brussels_first.metadata["axiom_inputs"][first_or_multiple_input] is True
    assert brussels_later.metadata["axiom_inputs"][first_or_multiple_input] is False
    assert brussels_first.metadata["axiom_inputs"][region_input] == 1
    assert brussels_later.metadata["axiom_inputs"][child_age_input] == 0
    assert len(brussels_later.metadata["euromod_inputs"]) == 3
    assert brussels_later.metadata["euromod_inputs"][1]["dag"] == 5
    assert brussels_later.metadata["euromod_inputs"][2]["dag"] == 0
    assert brussels_later.metadata["euromod_inputs"][2]["idmother"] == 101
    assert german_zero.metadata["axiom_inputs"][region_input] == 4
    assert german_zero.metadata["euromod_inputs"][1]["drgn1"] == 4
    assert {case.period for case in cases} == {"2025"}


def test_belgium_family_child_benefit_base_suite_defines_oracle_concept_and_inputs() -> (
    None
):
    cases = load_suite("be-family-child-benefit-base")

    assert len(cases) == 9
    assert {case.locale for case in cases} == {"BE"}
    assert {case.scope for case in cases} == {
        GeographyScope(type="country", geoid="BE")
    }
    assert {case.outputs for case in cases} == {
        (Concepts.BE_FAMILY_CHILD_BENEFIT_BASE,)
    }
    assert all(case.metadata["axiom_entity"] == "Household" for case in cases)
    assert all(case.metadata["axiom_entity_id"] == "household" for case in cases)
    assert all(
        "#input." in key for case in cases for key in case.metadata["axiom_inputs"]
    )
    assert {case.metadata["scenario"] for case in cases} == {
        "brussels-new-system-under-6",
        "brussels-transition-age-6",
        "brussels-transition-age-13",
        "brussels-age-18-not-enrolled",
        "brussels-age-18-higher-education",
        "wallonia-new-system-under-6",
        "wallonia-pre-2020-age-6",
        "wallonia-pre-2020-age-13",
        "wallonia-pre-2020-age-18",
    }

    by_id = {case.case_id: case for case in cases}
    brussels_age_0 = by_id["be-family-child-benefit-base-brussels-age-0"]
    brussels_age_18_no_he = by_id[
        "be-family-child-benefit-base-brussels-age-18-no-higher-education"
    ]
    brussels_age_18_he = by_id[
        "be-family-child-benefit-base-brussels-age-18-higher-education"
    ]
    wallonia_age_13 = by_id["be-family-child-benefit-base-wallonia-age-13"]
    region_input = (
        "be:statutes/family_benefits/child_benefit_base_2025#input."
        "belgium_family_benefits_child_benefit_region"
    )
    child_age_input = (
        "be:statutes/family_benefits/child_benefit_base_2025#input."
        "belgium_family_benefits_child_benefit_child_age_years"
    )
    child_count_input = (
        "be:statutes/family_benefits/child_benefit_base_2025#input."
        "belgium_family_benefits_child_benefit_household_child_count"
    )
    higher_education_input = (
        "be:statutes/family_benefits/child_benefit_base_2025#input."
        "belgium_family_benefits_child_benefit_child_enrolled_in_higher_education"
    )
    assert brussels_age_0.metadata["axiom_inputs"][region_input] == 1
    assert brussels_age_0.metadata["axiom_inputs"][child_age_input] == 0
    assert brussels_age_0.metadata["axiom_inputs"][child_count_input] == 1
    assert (
        brussels_age_18_no_he.metadata["axiom_inputs"][higher_education_input]
        is False
    )
    assert brussels_age_18_he.metadata["axiom_inputs"][higher_education_input] is True
    assert wallonia_age_13.metadata["axiom_inputs"][region_input] == 3
    assert wallonia_age_13.metadata["axiom_inputs"][child_age_input] == 13
    assert len(brussels_age_18_he.metadata["euromod_inputs"]) == 2
    assert brussels_age_18_he.metadata["euromod_inputs"][0]["yem"] == 5_000
    assert brussels_age_18_he.metadata["euromod_inputs"][1]["dag"] == 18
    assert brussels_age_18_he.metadata["euromod_inputs"][1]["idmother"] == 101
    assert brussels_age_18_he.metadata["euromod_inputs"][1]["les"] == 6
    assert brussels_age_18_he.metadata["euromod_inputs"][1]["dec"] == 6
    assert brussels_age_18_he.metadata["euromod_inputs"][1]["xed00"] == 1
    assert brussels_age_18_he.metadata["euromod_inputs"][1]["byr"] == 2007
    assert brussels_age_18_no_he.metadata["euromod_inputs"][1]["dec"] == 0
    assert brussels_age_18_no_he.metadata["euromod_inputs"][1]["xed00"] == 1
    assert {case.period for case in cases} == {"2025"}


def test_belgium_social_assistance_suite_defines_oracle_concept_and_inputs() -> None:
    cases = load_suite("be-social-assistance")

    assert len(cases) == 1
    [case] = cases
    assert case.locale == "BE"
    assert case.scope == GeographyScope(type="country", geoid="BE")
    assert case.outputs == (Concepts.BE_SOCIAL_INTEGRATION_INCOME_SUPPORT,)
    assert case.metadata["axiom_entity"] == "Person"
    assert case.metadata["axiom_entity_id"] == "head"
    assert all("#input." in key for key in case.metadata["axiom_inputs"])
    assert (
        case.metadata["axiom_inputs"][
            "be:statutes/social_integration/payable_amount#input."
            "belgium_social_integration_use_supplied_chapter_2_countable_annual_resources"
        ]
        is True
    )
    assert "euromod_inputs" in case.metadata
    assert case.metadata["euromod_inputs"][0]["dag"] == 35
    assert case.period == "2025"


def test_belgium_elderly_income_support_suite_defines_oracle_concept_and_inputs() -> (
    None
):
    cases = load_suite("be-elderly-income-support")

    assert len(cases) == 1
    [case] = cases
    assert case.locale == "BE"
    assert case.scope == GeographyScope(type="country", geoid="BE")
    assert case.outputs == (Concepts.BE_INCOME_GUARANTEE_FOR_ELDERLY,)
    assert case.metadata["axiom_entity"] == "Person"
    assert case.metadata["axiom_entity_id"] == "head"
    assert all("#input." in key for key in case.metadata["axiom_inputs"])
    assert (
        case.metadata["axiom_inputs"][
            "be:statutes/income_guarantee_for_elderly/payable_amount#input."
            "belgium_grapa_use_supplied_article_6_maximum_annual_amount"
        ]
        is True
    )
    assert (
        case.metadata["axiom_inputs"][
            "be:statutes/income_guarantee_for_elderly/payable_amount#input."
            "belgium_grapa_supplied_article_6_maximum_annual_amount"
        ]
        == 18_964.44
    )
    assert "euromod_inputs" in case.metadata
    assert case.metadata["euromod_inputs"][0]["dag"] == 70
    assert case.metadata["euromod_policy_switch_overrides"] == [("bsaoa_be", True)]
    assert case.period == "2025"


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


def test_policyengine_projection_uses_taxable_interest_income() -> None:
    case = Case(
        case_id="interest-income",
        period="2026",
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 40,
                    Concepts.INTEREST_INCOME: 1_000,
                },
            ),
        ),
    )

    person = PolicyEngineRunner()._build_situation_from_case(case)["people"]["head"]

    assert person["taxable_interest_income"] == {2026: 1_000}
    assert "interest_income" not in person


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


def test_policyengine_tax_case_runs_use_batched_dataset_path(monkeypatch) -> None:
    calls = []

    def fail_run_case(*_args, **_kwargs):
        raise AssertionError("tax cases should use the batched dataset path")

    def fake_batch(self, cases, variables):
        calls.append(([case.case_id for case in cases], tuple(variables)))
        return [
            EngineResult("policyengine", case.case_id, {"income_tax": index})
            for index, case in enumerate(cases)
        ]

    monkeypatch.setattr(PolicyEngineRunner, "run_case", fail_run_case)
    monkeypatch.setattr(PolicyEngineRunner, "_run_case_batch", fake_batch)

    cases = [
        Case(case_id="case-1", period="2026"),
        Case(case_id="case-2", period="2026"),
    ]

    results = PolicyEngineRunner().run_cases(cases, ["income_tax"])

    assert calls == [(["case-1", "case-2"], ("income_tax",))]
    assert [result.household_id for result in results] == ["case-1", "case-2"]
    assert [result.values["income_tax"] for result in results] == [0, 1]


def test_policyengine_dataset_rows_zero_fill_sparse_tax_inputs() -> None:
    case = Case(
        case_id="sparse-tax-inputs",
        period="2026",
        facts={
            Concepts.PROPERTY_TAX_PAID: 2_000,
            Concepts.MORTGAGE_INTEREST_PAID: 5_000,
            Concepts.RENT_PAID: 12_000,
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 73,
                    Concepts.SOCIAL_SECURITY_BENEFITS: 32_240.64,
                },
            ),
            Entity(
                entity_id="spouse",
                kind="person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Spouse",
                    Concepts.PERSON_AGE: 74,
                    Concepts.YEARLY_EARNED_INCOME: 163_996.50,
                    Concepts.INTEREST_INCOME: 0.78,
                },
            ),
            Entity(
                entity_id="adult-child",
                kind="person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Other",
                    Concepts.PERSON_AGE: 52,
                    Concepts.YEARLY_EARNED_INCOME: 43_732.40,
                },
            ),
        ),
    )

    (
        person_rows,
        _household_rows,
        _marital_unit_rows,
        _family_rows,
        _spm_unit_rows,
        tax_unit_rows,
        _entity_ids_by_case,
    ) = PolicyEngineRunner()._policyengine_dataset_rows([case], ["income_tax"])

    rows_by_id = {row["person_id"]: row for row in person_rows}
    for row in person_rows:
        for (
            pe_variable
        ) in policyengine_runner_module._PERSON_INCOME_CONCEPT_TO_PE.values():
            assert pe_variable in row
        for (
            pe_variable
        ) in policyengine_runner_module._PERSON_CASE_CONCEPT_TO_PE.values():
            assert pe_variable in row

    assert rows_by_id["case_0__head"]["social_security"] == 32_240.64
    assert rows_by_id["case_0__head"]["taxable_interest_income"] == 0
    assert rows_by_id["case_0__head"]["real_estate_taxes"] == 2_000
    assert rows_by_id["case_0__head"]["deductible_mortgage_interest"] == 5_000
    assert rows_by_id["case_0__head"]["pre_subsidy_rent"] == 12_000
    assert rows_by_id["case_0__spouse"]["taxable_interest_income"] == 0.78
    assert rows_by_id["case_0__spouse"]["social_security"] == 0
    assert rows_by_id["case_0__spouse"]["real_estate_taxes"] == 0
    assert rows_by_id["case_0__spouse"]["deductible_mortgage_interest"] == 0
    assert rows_by_id["case_0__spouse"]["pre_subsidy_rent"] == 0
    assert rows_by_id["case_0__adult-child"]["social_security"] == 0
    assert rows_by_id["case_0__adult-child"]["taxable_interest_income"] == 0
    assert rows_by_id["case_0__adult-child"]["real_estate_taxes"] == 0
    assert rows_by_id["case_0__adult-child"]["deductible_mortgage_interest"] == 0
    assert rows_by_id["case_0__adult-child"]["pre_subsidy_rent"] == 0

    spm_unit_row = _spm_unit_rows[0]
    assert spm_unit_row["housing_cost"] == 12_000

    tax_unit_row = tax_unit_rows[0]
    for pe_variable in policyengine_runner_module._TAX_UNIT_CONCEPT_TO_PE.values():
        assert pe_variable in tax_unit_row
    assert tax_unit_row["misc_deduction"] == 0


def test_policyengine_household_calculator_input_includes_tax_leaf_inputs() -> None:
    case = Case(
        case_id="household-calculator-tax-inputs",
        period="2026",
        facts={
            Concepts.PROPERTY_TAX_PAID: 2_000,
            Concepts.MORTGAGE_INTEREST_PAID: 5_000,
            Concepts.RENT_PAID: 12_000,
            Concepts.ITEMIZED_DEDUCTIONS_OTHER: 300,
            Concepts.CHILDCARE_EXPENSES: 400,
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 73,
                    Concepts.SOCIAL_SECURITY_BENEFITS: 32_240.64,
                },
            ),
            Entity(
                entity_id="spouse",
                kind="person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Spouse",
                    Concepts.PERSON_AGE: 74,
                    Concepts.YEARLY_EARNED_INCOME: 163_996.50,
                    Concepts.INTEREST_INCOME: 0.78,
                },
            ),
        ),
    )

    household_input = PolicyEngineRunner()._build_household_calculator_input_from_case(
        case,
        variables=["income_tax"],
    )

    assert household_input["people"][0]["social_security"] == 32_240.64
    assert household_input["people"][0]["real_estate_taxes"] == 2_000
    assert household_input["people"][0]["deductible_mortgage_interest"] == 5_000
    assert household_input["people"][0]["pre_subsidy_rent"] == 12_000
    assert household_input["people"][1]["taxable_interest_income"] == 0.78
    assert household_input["spm_unit"]["housing_cost"] == 12_000
    assert household_input["tax_unit"]["misc_deduction"] == 300
    assert household_input["tax_unit"]["tax_unit_childcare_expenses"] == 400


def test_policyengine_household_projection_includes_pregnancy_fact() -> None:
    household = Household(
        household_id="pregnant-adult",
        people=(Person(age=30, pregnant=True),),
        year=2026,
    )

    situation = PolicyEngineRunner()._build_situation(household)

    assert situation["people"]["person_0"]["is_pregnant"][2026] is True
