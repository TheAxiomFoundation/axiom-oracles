from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .geography import GeographyScope, normalize_scope


@dataclass(frozen=True)
class Entity:
    """A thin case entity with concept-keyed facts."""

    entity_id: str
    kind: str
    facts: Mapping[str, Any] = field(default_factory=dict)

    def fact(self, concept_id: str, default: Any = None) -> Any:
        return self.facts.get(concept_id, default)


@dataclass(frozen=True)
class Case:
    """Engine-neutral case data.

    Facts and requested outputs are keyed by canonical legal or Axiom concept IDs.
    Adapters project those facts into PolicyEngine variables, ACCESS NYC payloads,
    PRD fields, TAXSIM columns, or Axiom RuleSpec runtime inputs.
    """

    case_id: int | str
    period: str
    facts: Mapping[str, Any] = field(default_factory=dict)
    entities: tuple[Entity, ...] = field(default_factory=tuple)
    outputs: tuple[str, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def fact(self, concept_id: str, default: Any = None) -> Any:
        return self.facts.get(concept_id, default)

    def entities_of_kind(self, kind: str) -> tuple[Entity, ...]:
        return tuple(entity for entity in self.entities if entity.kind == kind)

    @property
    def locale(self) -> str | None:
        value = self.metadata.get("locale") or self.facts.get(Concepts.LOCALE)
        return str(value) if value else None

    @property
    def scope(self) -> GeographyScope | None:
        value = self.metadata.get("scope") or self.facts.get(Concepts.GEOGRAPHY_SCOPE)
        return normalize_scope(value)


class Concepts:
    """Cross-engine case facts used by bundled projections.

    Domain-specific outputs should usually use source-backed legal IDs, not these
    generic helper concepts. These helpers exist for facts like age and household
    relation that are needed to project a case into external engines.
    """

    PERSON_AGE = "axiom:demographics/person#age"
    HOUSEHOLD_RELATION = "axiom:demographics/person#household_relation"
    YEARLY_EARNED_INCOME = "axiom:income/person#yearly_earned_income"
    PREGNANT = "axiom:demographics/person#pregnant"
    BLIND = "axiom:demographics/person#blind"
    DISABLED = "axiom:demographics/person#disabled"
    VETERAN = "axiom:demographics/person#veteran"
    BENEFITS_MEDICAID = "axiom:benefits/person#medicaid"
    BENEFITS_MEDICAID_DISABILITY = "axiom:benefits/person#disability_medicaid"
    LIVING_RENTING = "axiom:housing/household#living_renting"
    LIVING_OWNER = "axiom:housing/household#living_owner"
    CASH_ON_HAND = "axiom:assets/household#cash_on_hand"
    LOCALE = "axiom:case#locale"
    GEOGRAPHY_SCOPE = "axiom:case#geography_scope"
    STATE_CODE = "axiom:location/household#state_code"

    # Income components (person-level, annual)
    DIVIDEND_INCOME = "axiom:income/person#dividend_income"
    QUALIFIED_DIVIDEND_INCOME = "axiom:income/person#qualified_dividend_income"
    INTEREST_INCOME = "axiom:income/person#interest_income"
    SHORT_TERM_CAPITAL_GAINS = "axiom:income/person#short_term_capital_gains"
    LONG_TERM_CAPITAL_GAINS = "axiom:income/person#long_term_capital_gains"
    PENSION_INCOME = "axiom:income/person#pension_income"
    TANF_BENEFITS = "axiom:income/person#tanf_benefits"
    SSI_BENEFITS = "axiom:income/person#ssi_benefits"
    SOCIAL_SECURITY_BENEFITS = "axiom:income/person#social_security_benefits"
    UNEMPLOYMENT_INSURANCE_INCOME = "axiom:income/person#unemployment_insurance"
    RENTAL_INCOME = "axiom:income/person#rental_income"
    SELF_EMPLOYMENT_INCOME = "axiom:income/person#self_employment_income"

    # Itemization / household-level inputs (annual)
    PROPERTY_TAX_PAID = "axiom:housing/household#property_tax_paid"
    MORTGAGE_INTEREST_PAID = "axiom:housing/household#mortgage_interest_paid"
    ITEMIZED_DEDUCTIONS_OTHER = "axiom:tax/household#itemized_deductions_other"
    RENT_PAID = "axiom:housing/household#rent_paid"
    CHILDCARE_EXPENSES = "axiom:tax/household#childcare_expenses"

    # Program outputs
    SNAP_BENEFIT = "us:statutes/7/2014/u#snap_benefit"
    SNAP_ELIGIBLE = "us:statutes/7/2014/o#snap_eligible"
    FEDERAL_INCOME_TAX = "us:tax/federal-income-tax#liability"
    STATE_INCOME_TAX = "us:tax/state-income-tax#liability"
    MEDICAID_ELIGIBLE = "us:programs/medicaid#eligible"
    MEDICAID_PREGNANT_WOMEN_ELIGIBLE = (
        "us:programs/medicaid-pregnant-women#eligible"
    )
    BASIC_HEALTH_PROGRAM_ELIGIBLE = "us:programs/basic-health-program#eligible"
    CHILD_HEALTH_PLUS_ELIGIBLE = "us:programs/child-health-plus#eligible"
    WIC_ELIGIBLE = "us:statutes/42/1786#wic_eligible"

    # Federal income tax components (sub-outputs of FEDERAL_INCOME_TAX)
    AGI = "us:tax/federal-income-tax#agi"
    STANDARD_DEDUCTION = "us:tax/federal-income-tax#standard_deduction"
    TAXABLE_INCOME = "us:tax/federal-income-tax#taxable_income"
    TAX_BEFORE_CREDITS = "us:tax/federal-income-tax#tax_before_credits"
    NONREFUNDABLE_CREDITS = "us:tax/federal-income-tax#nonrefundable_credits"
    EITC = "us:tax/federal-income-tax#eitc"
    CTC = "us:tax/federal-income-tax#ctc"
    CDCC = "us:tax/federal-income-tax#cdcc"
    AOTC = "us:tax/federal-income-tax#aotc"
    AMT = "us:tax/federal-income-tax#amt"
    CAPITAL_GAIN = "us:tax/federal-income-tax#capital_gain"
    # EUROMOD-platform oracle concepts (durable RuleSpec ids where the
    # encoding exists; UKMOD/EUROMOD outputs bridge to these).
    UK_INCOME_TAX = "uk:statutes/ukpga/2007/3/23#income_tax_liability"
    UK_EMPLOYEE_NIC = "uk:tax/national-insurance#employee_contributions"
    BE_PERSONAL_INCOME_TAX = (
        "be:statutes/income_tax/individual/tax_liability_pipeline"
        "#belgium_pit_final_income_tax_payable"
    )
    BE_WORKER_PIT_BEFORE_WITHHOLDING = (
        "be:statutes/income_tax/individual/pilot_worker_oracle_pipeline"
        "#belgium_pit_pilot_federal_and_local_tax_before_withholding"
    )
    BE_EMPLOYEE_SOCIAL_CONTRIBUTIONS = (
        "be:regulations/social_security/workers/employee_contributions"
        "#belgium_employee_social_security_ordinary_worker_contribution"
    )
    BE_EMPLOYEE_SOCIAL_CONTRIBUTIONS_BEFORE_REDUCTIONS = (
        "be:regulations/social_security/workers/employee_contributions"
        "#belgium_employee_social_security_article_38_contribution_before_reductions"
    )
    BE_EMPLOYEE_WORK_BONUS_REDUCTION = (
        "be:regulations/social_security/workers/work_bonus"
        "#belgium_worker_work_bonus_full_year_equal_monthly_total_reduction"
    )
    BE_SOCIAL_INTEGRATION_INCOME_SUPPORT = (
        "be:statutes/social_integration/payable_amount"
        "#belgium_social_integration_income_support_annual_amount"
    )
    BE_INCOME_GUARANTEE_FOR_ELDERLY = (
        "be:statutes/income_guarantee_for_elderly/payable_amount"
        "#belgium_grapa_income_guarantee_for_elderly_annual_amount"
    )
    BE_SELF_EMPLOYED_SOCIAL_CONTRIBUTIONS = (
        "be:regulations/social_security/self_employed/contributions"
        "#belgium_self_employed_selected_annual_social_contribution"
    )
    BE_SPECIAL_SOCIAL_SECURITY_CONTRIBUTION = (
        "be:statutes/social_security/special_contribution"
        "#belgium_special_social_security_article_108_annual_contribution"
    )
    BE_FLEMISH_SOCIAL_PROTECTION_PREMIUM = (
        "be-vlg:regulations/social_security/flemish_social_protection/premium"
        "#flanders_social_protection_annual_premium"
    )
    BE_FLEMISH_JOBBONUS = (
        "be-vlg:regulations/employment/jobbonus"
        "#flanders_jobbonus_annual_amount"
    )
    BE_FAMILY_BIRTH_ALLOWANCE = (
        "be:statutes/family_benefits/birth_allowance"
        "#belgium_family_benefits_birth_allowance_amount"
    )
    BE_FAMILY_CHILD_BENEFIT_BASE = (
        "be:statutes/family_benefits/child_benefit_base_2025"
        "#belgium_family_benefits_child_benefit_base_2025_annual_amount"
    )
    BE_FAMILY_CHILD_BENEFIT_WITH_SOCIAL_SUPPLEMENT = (
        "be:statutes/family_benefits/child_benefit_base_2025"
        "#belgium_child_benefit_brussels_2025_annual_amount_with_social_supplement"
    )
    BE_FAMILY_CHILD_BENEFIT_WALLONIA_WITH_SOCIAL_SUPPLEMENT = (
        "be:statutes/family_benefits/child_benefit_base_2025"
        "#belgium_child_benefit_wallonia_2025_annual_amount_with_social_supplement"
    )
    BE_WORKER_ARTICLE_17_UNCAPPED_COMPONENT_CONTRIBUTION = (
        "be:statutes/social_security/workers/contribution_rates"
        "#belgium_worker_article_17_uncapped_component_contribution"
    )

    EMPLOYEE_OASDI = "us:tax/payroll#employee_oasdi"
    EMPLOYEE_MEDICARE = "us:tax/payroll#employee_medicare"
    EMPLOYER_OASDI = "us:tax/payroll#employer_oasdi"
    EMPLOYER_MEDICARE = "us:tax/payroll#employer_medicare"
