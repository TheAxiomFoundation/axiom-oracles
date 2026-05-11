from __future__ import annotations

from dataclasses import replace
from typing import Any

from ...core.case import Case, Concepts, Entity
from .runner import (
    AXIOM_INPUT_RECORD_OVERLAYS_METADATA_KEY,
    AXIOM_INPUT_RECORDS_METADATA_KEY,
    AXIOM_RELATIONS_METADATA_KEY,
    AXIOM_RESULT_SELECTION_METADATA_KEY,
)


AXIOM_TAX_UNIT_INPUTS_METADATA_KEY = "axiom_tax_unit_inputs"

US_FEDERAL_INCOME_TAX_IMPORTS = (
    "us:statutes/26/1/j",
    "us:statutes/26/21",
    "us:statutes/26/22",
    "us:statutes/26/24/d",
    "us:statutes/26/25A",
    "us:statutes/26/25B",
    "us:statutes/26/26",
    "us:statutes/26/32",
    "us:statutes/26/55",
    "us:statutes/26/63",
    "us:statutes/26/1401",
    "us:statutes/26/1411",
    "us:statutes/26/3101/a",
    "us:statutes/26/3101/b/1",
    "us:statutes/26/3101/b/2",
    "us:statutes/26/6401",
)

_TAX_UNIT_ID = "tax_unit"
_AXIOM_TAX_REF_PREFIX = "us:tax/federal-income-tax"
_ADDITIONAL_SENIOR_DEDUCTION_AMOUNT = 6_000
_ADDITIONAL_SENIOR_DEDUCTION_AGE = 65
_ADDITIONAL_SENIOR_DEDUCTION_PHASEOUT_RATE = 0.06
_ADDITIONAL_SENIOR_DEDUCTION_JOINT_THRESHOLD = 150_000
_ADDITIONAL_SENIOR_DEDUCTION_OTHER_THRESHOLD = 75_000

_POLICYENGINE_EXTERNAL_TAX_INPUTS = (
    "auto_loan_interest_deduction",
    "charitable_deduction_for_non_itemizers",
    "itemized_taxable_income_deductions",
    "overtime_income_deduction",
    "qualified_business_income_deduction",
    "tip_income_deduction",
)

_RELATION_REFS = (
    "us:statutes/26/21#relation.cdcc_member_of_tax_unit",
    "us:statutes/26/22#relation.elderly_disabled_member_of_tax_unit",
    "us:statutes/26/24/h#relation.member_of_tax_unit",
    "us:statutes/26/25A#relation.education_credit_member_of_tax_unit",
)

_SPOUSE_RELATIONS = {
    "spouse",
    "wife",
    "husband",
    "partner",
    "marriedpartner",
    "married_partner",
}

_HEAD_RELATIONS = {
    "head",
    "headofhousehold",
    "head_of_household",
    "householder",
    "referenceperson",
    "reference_person",
    "self",
}

_BOOLEAN_DEFAULTS_FALSE = (
    "amt_kiddie_tax_applies",
    "amt_part_iii_required",
    "aotc_disallowance_period_applies",
    "aotc_election_in_effect",
    "at_least_half_time_student",
    "completed_first_four_years_postsecondary_before_year",
    "disability_proof_furnished",
    "education_credit_election_in_effect",
    "education_credit_identification_requirements_met",
    "excludes_foreign_earned_income",
    "expenses_paid_to_allowed_provider",
    "has_felony_drug_conviction",
    "institution_employer_identification_number_included",
    "is_incapable_of_self_care",
    "is_nonresident_alien",
    "is_student_under_section_152_f_2",
    "joint_return_filed_for_spouse_distribution_year",
    "meets_higher_education_act_student_requirements",
    "medically_determinable_impairment",
    "payee_statement_received",
    "provider_identification_requirements_met",
    "qualifying_individual_identification_requirements_met",
    "retired_on_disability_before_year_end",
    "satisfies_cdcc_married_living_apart_rules",
    "satisfies_eitc_separated_spouse_rules",
    "section_151_deduction_allowed_to_another_taxpayer",
    "section_6013_resident_alien_election",
    "spouses_lived_apart_all_year",
    "tax_unit_itemizes",
    "taxable_year_begins_before_2027",
    "taxpayer_is_section_1_g_child",
    "unable_to_engage_substantial_gainful_activity",
)

_TAX_UNIT_NUMERIC_DEFAULTS = (
    "able_account_contributions",
    "allocable_investment_deductions",
    "alternative_minimum_tax_foreign_tax_credit",
    "amt_tax_including_capital_gains",
    "annuity_income",
    "aotc_prior_year_election_count",
    "auto_loan_interest_deduction",
    "capital_gains_28_percent_rate_gain",
    "charitable_deduction_for_non_itemizers",
    "cost_of_living_adjustment_25b",
    "ctc_limiting_tax_liability",
    "dependent_care_assistance_exclusion",
    "dividend_income",
    "eitc_relevant_investment_income",
    "elective_deferrals",
    "eligible_deferred_compensation_deferrals",
    "energy_efficient_home_improvement_credit",
    "excess_payroll_tax_withheld",
    "excludable_educational_assistance",
    "exemptions",
    "financial_trading_business_income",
    "foreign_tax_credit",
    "form_4972_lumpsum_distributions",
    "impairment_duration_months",
    "individual_testing_period_distributions",
    "itemized_taxable_income_deductions",
    "long_term_capital_gains",
    "min_head_spouse_earned",
    "misc_deduction",
    "new_clean_vehicle_credit",
    "other_nontaxable_pension_annuity_disability_benefits_subject_to_reduction",
    "overtime_income_deduction",
    "passive_activity_business_income",
    "pension_annuity_disability_benefits_received",
    "qualified_business_income_deduction",
    "qualified_dividend_income",
    "qualified_plan_distributions",
    "qualified_retirement_contributions",
    "qualified_retirement_penalty",
    "qualified_tuition_and_related_expenses",
    "recapture_of_investment_credit",
    "recovery_rebate_credit",
    "refundable_payroll_tax_credit",
    "rental_income",
    "residential_clean_energy_credit",
    "royalty_income",
    "salt_deduction",
    "section_104_a_4_va_benefits",
    "section_22_disability_income",
    "section_401_k_8_distribution",
    "section_401_m_6_distribution",
    "section_402_g_2_distribution",
    "section_404_k_distribution",
    "section_408A_d_3_distribution",
    "section_408_d_4_distribution",
    "section_72_p_distribution",
    "section_911_disallowed_deductions_and_exclusions",
    "section_911_excluded_gross_income",
    "section_911_excluded_income",
    "section_931_excluded_income",
    "section_933_excluded_income",
    "self_employment_income",
    "self_employment_income_subject_to_1401_b",
    "self_employment_tax_ald",
    "short_term_capital_gains",
    "social_security_benefits_received",
    "spouse_testing_period_distributions",
    "tax_unit_childcare_expenses",
    "taxable_interest_income",
    "taxable_net_gain_from_dispositions",
    "taxable_pension_annuity_disability_benefits_included",
    "taxable_social_security_benefits_included",
    "tip_income_deduction",
    "trustee_to_trustee_transfer_or_rollover_distribution_portion",
    "unrecaptured_section_1250_gain",
    "unreported_payroll_tax",
    "used_clean_vehicle_credit",
    "voluntary_employee_qualified_plan_contributions",
    "wagering_losses_deduction",
)


def attach_axiom_tax_inputs(cases: list[Case]) -> list[Case]:
    """Attach Axiom federal tax input records to ECPS-style neutral cases."""

    return [attach_axiom_tax_inputs_to_case(case) for case in cases]


def attach_axiom_tax_itemization_choice(cases: list[Case]) -> list[Case]:
    """Attach oracle-comparison itemization candidates to Axiom tax cases."""

    return [attach_axiom_tax_itemization_choice_to_case(case) for case in cases]


def attach_axiom_tax_itemization_choice_to_case(case: Case) -> Case:
    metadata = dict(case.metadata)
    metadata[AXIOM_INPUT_RECORD_OVERLAYS_METADATA_KEY] = _itemization_overlays()
    metadata[AXIOM_RESULT_SELECTION_METADATA_KEY] = {
        "strategy": "min",
        "output": "us:statutes/26/6401#income_tax",
    }
    return replace(case, metadata=metadata)


def attach_policyengine_tax_unit_inputs(cases: list[Case]) -> list[Case]:
    """Attach external tax inputs calculated by the PolicyEngine projection."""

    from ..policyengine.runner import PolicyEngineRunner

    runner = PolicyEngineRunner()
    projected = []
    for case in cases:
        metadata = dict(case.metadata)
        existing = metadata.get(AXIOM_TAX_UNIT_INPUTS_METADATA_KEY)
        if existing:
            projected.append(case)
            continue
        result = runner.run_case(case, list(_POLICYENGINE_EXTERNAL_TAX_INPUTS))
        values = {
            name: result.values[name]
            for name in _POLICYENGINE_EXTERNAL_TAX_INPUTS
            if name in result.values
        }
        metadata[AXIOM_TAX_UNIT_INPUTS_METADATA_KEY] = values
        projected.append(replace(case, metadata=metadata))
    return projected


def attach_axiom_tax_inputs_to_case(case: Case) -> Case:
    metadata = dict(case.metadata)
    if metadata.get(AXIOM_INPUT_RECORDS_METADATA_KEY):
        return case

    people = _people(case)
    if not people:
        raise RuntimeError("Axiom federal tax projection requires at least one person.")

    records = _tax_unit_input_records(case, people)
    records.extend(_person_input_records(people))
    relations = _relation_records(people)
    metadata[AXIOM_INPUT_RECORDS_METADATA_KEY] = records
    metadata[AXIOM_RELATIONS_METADATA_KEY] = [
        *metadata.get(AXIOM_RELATIONS_METADATA_KEY, []),
        *relations,
    ]
    return replace(case, metadata=metadata)


def _tax_unit_input_records(case: Case, people: list[Entity]) -> list[dict[str, Any]]:
    head, spouse = _tax_filers(people)
    dependents = [person for person in people if person not in (head, spouse)]
    wages = _earned_income(head) + (_earned_income(spouse) if spouse else 0)
    earned_income = wages
    agi = wages
    filing_status = _filing_status(spouse=spouse, dependents=dependents)

    inputs: dict[str, Any] = {
        "adjusted_gross_income": agi,
        "additional_senior_deduction": _additional_senior_deduction(
            agi=agi,
            filing_status=filing_status,
            head=head,
            spouse=spouse,
        ),
        "age_at_close_of_taxable_year": _age(head),
        "earned_income": earned_income,
        "employee_medicare_tax": wages * 0.0145,
        "employee_social_security_tax": wages * 0.062,
        "filer_adjusted_earnings": earned_income,
        "filer_meets_eitc_identification_requirements": True,
        "filing_status": filing_status,
        "modified_adjusted_gross_income": agi,
        "wages": wages,
        "wages_taken_into_account_for_additional_medicare_tax": wages,
    }
    for name in _BOOLEAN_DEFAULTS_FALSE:
        inputs.setdefault(name, _boolean_default(name, case))
    for name in _TAX_UNIT_NUMERIC_DEFAULTS:
        inputs.setdefault(name, 0)
    inputs.update(_case_axiom_tax_unit_inputs(case))
    return [_input_record(name, "TaxUnit", _TAX_UNIT_ID, value) for name, value in inputs.items()]


def _person_input_records(people: list[Entity]) -> list[dict[str, Any]]:
    head, spouse = _tax_filers(people)
    records = []
    for person in people:
        age = _age(person)
        is_dependent = person is not head and person is not spouse
        inputs: dict[str, Any] = {
            "age": age,
            "age_at_close_of_taxable_year": age,
            "earned_income": _earned_income(person),
            "has_same_principal_place_of_abode_more_than_half_year": is_dependent,
            "is_qualifying_child_dependent": is_dependent and age < 19,
            "is_section_152_a_1_dependent": is_dependent and age < 19,
            "is_spouse": person is spouse,
            "is_tax_unit_dependent": is_dependent,
            "is_taxpayer": person is head or person is spouse,
            "meets_ctc_child_identification_requirements": is_dependent,
            "meets_eitc_identification_requirements": is_dependent,
        }
        for name in _BOOLEAN_DEFAULTS_FALSE:
            inputs.setdefault(name, False)
        for name in _TAX_UNIT_NUMERIC_DEFAULTS:
            inputs.setdefault(name, 0)
        for name, value in inputs.items():
            records.append(_input_record(name, "Person", person.entity_id, value))
    return records


def _relation_records(people: list[Entity]) -> list[dict[str, Any]]:
    return [
        {
            "name": relation_ref,
            "tuple": [person.entity_id, _TAX_UNIT_ID],
        }
        for relation_ref in _RELATION_REFS
        for person in people
    ]


def _input_record(
    name: str,
    entity: str,
    entity_id: str,
    value: Any,
) -> dict[str, Any]:
    return {
        "name": _input_ref(name),
        "entity": entity,
        "entity_id": entity_id,
        "value": value,
    }


def _input_ref(name: str) -> str:
    return f"{_AXIOM_TAX_REF_PREFIX}#input.{name}"


def _case_axiom_tax_unit_inputs(case: Case) -> dict[str, Any]:
    raw_inputs = case.metadata.get(AXIOM_TAX_UNIT_INPUTS_METADATA_KEY, {})
    if not raw_inputs:
        return {}
    if not isinstance(raw_inputs, dict):
        raise RuntimeError("metadata['axiom_tax_unit_inputs'] must be a mapping.")
    if "tax_unit_itemizes" in raw_inputs:
        raise RuntimeError(
            "metadata['axiom_tax_unit_inputs'] must not include tax_unit_itemizes; "
            "itemization status is resolved by Axiom candidate selection."
        )
    return dict(raw_inputs)


def _itemization_overlays() -> list[list[dict[str, Any]]]:
    return [
        [_input_record("tax_unit_itemizes", "TaxUnit", _TAX_UNIT_ID, False)],
        [_input_record("tax_unit_itemizes", "TaxUnit", _TAX_UNIT_ID, True)],
    ]


def _filing_status(*, spouse: Entity | None, dependents: list[Entity]) -> int:
    if spouse is not None:
        return 1
    if dependents:
        return 3
    return 0


def _additional_senior_deduction(
    *,
    agi: float,
    filing_status: int,
    head: Entity,
    spouse: Entity | None,
) -> float:
    eligible_seniors = sum(
        _age(person) >= _ADDITIONAL_SENIOR_DEDUCTION_AGE
        for person in (head, spouse)
        if person is not None
    )
    if eligible_seniors == 0:
        return 0
    threshold = (
        _ADDITIONAL_SENIOR_DEDUCTION_JOINT_THRESHOLD
        if filing_status == 1
        else _ADDITIONAL_SENIOR_DEDUCTION_OTHER_THRESHOLD
    )
    phaseout = max(0, agi - threshold) * _ADDITIONAL_SENIOR_DEDUCTION_PHASEOUT_RATE
    per_senior_allowed = max(0, _ADDITIONAL_SENIOR_DEDUCTION_AMOUNT - phaseout)
    return per_senior_allowed * eligible_seniors


def _boolean_default(name: str, case: Case) -> bool:
    if name == "taxable_year_begins_before_2027":
        year = int(str(case.period).split("-", maxsplit=1)[0])
        return year < 2027
    return False


def _people(case: Case) -> list[Entity]:
    return [
        entity
        for entity in case.entities
        if str(entity.kind).lower().replace("_", "-") == "person"
    ]


def _head(people: list[Entity]) -> Entity:
    for person in people:
        if _relation(person) in _HEAD_RELATIONS:
            return person
    return people[0]


def _tax_filers(people: list[Entity]) -> tuple[Entity, Entity | None]:
    explicit_head = _head(people)
    explicit_spouse = _spouse(people, explicit_head)
    if explicit_spouse is not None:
        return explicit_head, explicit_spouse

    adult_people = [person for person in people if _age(person) >= 19]
    if not adult_people:
        return explicit_head, None
    ranked = sorted(
        adult_people,
        key=lambda person: (_age(person), _earned_income(person)),
        reverse=True,
    )
    head = ranked[0]
    spouse = ranked[1] if len(ranked) > 1 else None
    return head, spouse


def _spouse(people: list[Entity], head: Entity) -> Entity | None:
    for person in people:
        if person is not head and _relation(person) in _SPOUSE_RELATIONS:
            return person
    return None


def _relation(entity: Entity) -> str:
    return (
        str(entity.fact(Concepts.HOUSEHOLD_RELATION, ""))
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
    )


def _age(entity: Entity) -> int:
    return int(_number(entity.fact(Concepts.PERSON_AGE, 0)))


def _earned_income(entity: Entity) -> float:
    return _number(entity.fact(Concepts.YEARLY_EARNED_INCOME, 0))


def _number(value: Any) -> float:
    if value is None or value == "":
        return 0
    return float(value)
