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
    # Composed single-employee pilot pipelines (rulespec-uk) that wire the
    # supplied s10/s23 and s8 stage boundaries from gross employment income,
    # so an end-to-end UKMOD comparison (tin_s, tscee_s) can run.
    UK_WORKER_INCOME_TAX_LIABILITY = (
        "uk:statutes/income_tax/individual/pilot_worker_oracle_pipeline"
        "#uk_pit_pilot_income_tax_liability"
    )
    UK_WORKER_CLASS_1_EMPLOYEE_NIC = (
        "uk:statutes/social_security/workers/pilot_worker_class_1_nic_pipeline"
        "#uk_nic_pilot_primary_class_1_contribution"
    )
    # Composed self-employed (Class 4 + Class 2) and employer secondary Class 1
    # pilot pipelines for the UKMOD tscse_s and tscer_s comparisons.
    UK_WORKER_SELF_EMPLOYED_NIC = (
        "uk:statutes/social_security/workers/pilot_worker_self_employed_nic_pipeline"
        "#uk_nic_pilot_se_self_employed_contribution"
    )
    UK_WORKER_EMPLOYER_SECONDARY_NIC = (
        "uk:statutes/social_security/workers/pilot_worker_employer_secondary_nic_pipeline"
        "#uk_nic_pilot_er_secondary_class_1_contribution"
    )
    # Composed household Universal Credit pilot pipeline (rulespec-uk#72, merged)
    # that wires the supplied standard-allowance, child, LCWRA, carer, housing,
    # childcare, work-allowance, income-taper, capital/tariff, and benefit-cap
    # stage boundaries from hypothetical household inputs, so an end-to-end
    # UKMOD comparison (UC award ``bsauc_s``) can run on a shared household
    # grid. The final award is the Welfare Reform Act 2012 section 8(1) monthly
    # amount, exposed as ``uc_pilot_award_amount`` by
    # ``uk/policies/universal_credit_composed_award_pipeline.yaml``.
    UK_HOUSEHOLD_UNIVERSAL_CREDIT_AWARD = (
        "uk:policies/universal_credit_composed_award_pipeline"
        "#uc_pilot_award_amount"
    )
    # Composed Pension Credit guarantee-credit award pipeline (rulespec-uk) that
    # wires the State Pension Credit Act 2002 section 2 standard-minimum-
    # guarantee, additional-amount, and income-difference stage boundaries from
    # hypothetical pensioner inputs, so an end-to-end UKMOD comparison (Pension
    # Credit ``boamt_s``) can run on a shared household grid. The final award is
    # the weekly guarantee credit, exposed as ``pc_pilot_award_amount`` by
    # ``uk/policies/pension_credit_composed_award_pipeline.yaml``.
    UK_HOUSEHOLD_PENSION_CREDIT_AWARD = (
        "uk:policies/pension_credit_composed_award_pipeline"
        "#pc_pilot_award_amount"
    )
    # Composed savings-and-dividend income tax pipeline (rulespec-uk) that wires
    # the section 12/12A/12B/13/13A stage boundaries from gross earned, savings,
    # and dividend income, so an end-to-end UKMOD tin_s comparison can run for
    # savings (yiytx) and dividend (ydvtx) income.
    UK_SAVINGS_DIVIDEND_INCOME_TAX_LIABILITY = (
        "uk:statutes/income_tax/individual/savings_dividend_oracle_pipeline"
        "#uk_svdv_income_tax_liability"
    )
    # Composed Scottish non-savings non-dividend income tax pipeline
    # (rulespec-uk) that wires the Scottish Rate Resolution 2026-27 bands and
    # the section 35 personal allowance from gross earned income, so an
    # end-to-end UKMOD tin_s comparison can run for a Scottish taxpayer
    # (region routed to Scotland via drgn1=12).
    UK_SCOTTISH_INCOME_TAX_LIABILITY = (
        "uk:statutes/income_tax/individual/scottish_income_tax_oracle_pipeline"
        "#uk_scotpit_income_tax_liability"
    )
    # Composed Child Benefit pipeline (rulespec-uk) that wires the SI 2006/965
    # enhanced/other weekly rates and the SSCBA 1992 s.141 entitlement from a
    # supplied child count, so an end-to-end UKMOD Child Benefit comparison can
    # run. This is the gross, pre-charge annual entitlement; the UKMOD side adds
    # the High Income Child Benefit Charge clawback (bchrd_s) back to bch_s to
    # reconstruct the same pre-charge amount (the charge is not corpus-encoded,
    # rulespec-uk#75).
    UK_CHILD_BENEFIT_ENTITLEMENT = (
        "uk:statutes/child_benefit/pilot_child_benefit_oracle_pipeline"
        "#uk_cb_pilot_annual_entitlement"
    )
    # Same composed Child Benefit pipeline, net of the High Income Child Benefit
    # Charge (ITEPA 2003 ss.681B-681H, now corpus-encoded via axiom-corpus#221
    # and rulespec-uk#84). The charge is netted off the s.141 gross entitlement
    # to a post-charge amount, so this compares directly against UKMOD's paid
    # bch_s alone (UKMOD nets its separately-reported bchrd_s clawback into
    # bch_s), rather than reconstructing the pre-charge amount as bch_s + bchrd_s.
    # This is the net-of-charge surface that closes rulespec-uk#75.
    UK_CHILD_BENEFIT_NET_OF_CHARGE = (
        "uk:statutes/child_benefit/pilot_child_benefit_oracle_pipeline"
        "#uk_cb_pilot_annual_entitlement_net_of_charge"
    )
    BE_PERSONAL_INCOME_TAX = (
        "be:statutes/income_tax/individual/tax_liability_pipeline"
        "#belgium_pit_final_income_tax_payable"
    )
    BE_WORKER_PIT_BEFORE_WITHHOLDING = (
        "be:statutes/income_tax/individual/pilot_worker_oracle_pipeline"
        "#belgium_pit_pilot_federal_and_local_tax_before_withholding"
    )
    BE_MARITAL_QUOTIENT_COUPLE_PIT_BEFORE_WITHHOLDING = (
        "be:statutes/income_tax/individual/couple_pit_oracle_pipeline"
        "#belgium_pit_couple_federal_and_local_tax_before_withholding"
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
    BE_EMPLOYER_SOCIAL_CONTRIBUTIONS = (
        "be:regulations/social_security/workers/employer_contributions"
        "#belgium_employer_social_security_ordinary_worker_contribution"
    )
    BE_SOCIAL_INTEGRATION_INCOME_SUPPORT = (
        "be:statutes/social_integration/payable_amount"
        "#belgium_social_integration_income_support_annual_amount"
    )
    BE_INCOME_GUARANTEE_FOR_ELDERLY = (
        "be:statutes/income_guarantee_for_elderly/payable_amount"
        "#belgium_grapa_income_guarantee_for_elderly_annual_amount"
    )
    BE_BIRTH_LEAVE_TOTAL_COMPENSATION = (
        "be:regulations/health_insurance/birth_leave/indemnity_rates"
        "#belgium_birth_leave_total_compensation_amount"
    )
    BE_MATERNITY_REST_PERIOD_AMOUNT = (
        "be:regulations/health_insurance/maternity/indemnity_rates"
        "#belgium_maternity_article_216_rest_period_amount"
    )
    BE_SELF_EMPLOYED_SOCIAL_CONTRIBUTIONS = (
        "be:regulations/social_security/self_employed/contributions"
        "#belgium_self_employed_selected_annual_social_contribution"
    )
    BE_SPECIAL_SOCIAL_SECURITY_CONTRIBUTION = (
        "be:statutes/social_security/special_contribution"
        "#belgium_special_social_security_article_108_annual_contribution"
    )
    BE_PENSIONER_HEALTH_AND_SOLIDARITY_CONTRIBUTION = (
        "be:statutes/social_security/non_labour_income_contributions"
        "#belgium_pensioner_total_annual_health_and_solidarity_withholding"
    )
    BE_FLEMISH_SOCIAL_PROTECTION_PREMIUM = (
        "be-vlg:regulations/social_security/flemish_social_protection/premium"
        "#flanders_social_protection_annual_premium"
    )
    BE_FLEMISH_JOBBONUS = (
        "be-vlg:regulations/employment/jobbonus"
        "#flanders_jobbonus_annual_amount"
    )
    BE_IMMOVABLE_WITHHOLDING_GROSS_WITH_SUPPLIED_CENTIMES = (
        "be:statutes/property_tax/gross_withholding_and_supplied_centimes"
        "#belgium_immovable_withholding_gross_tax_after_supplied_local_centimes"
    )
    BE_CADASTRAL_INCOME_INDEXED = (
        "be:statutes/property_tax/cadastral_income_indexation"
        "#belgium_immovable_withholding_taxable_cadastral_income_from_unindexed"
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
    BE_FAMILY_CHILD_BENEFIT_BRUSSELS_SAME_AGE_HOUSEHOLD_WITH_SOCIAL_SUPPLEMENT = (
        "be:statutes/family_benefits/child_benefit_base_2025"
        "#belgium_child_benefit_brussels_2025_same_age_children_annual_household_amount_with_social_supplement"
    )
    BE_FAMILY_CHILD_BENEFIT_WALLONIA_WITH_SOCIAL_SUPPLEMENT = (
        "be:statutes/family_benefits/child_benefit_base_2025"
        "#belgium_child_benefit_wallonia_2025_annual_amount_with_social_supplement"
    )
    BE_EUROMOD_ILS_BEN_FAMILY_BENEFIT_PILOT = (
        "be:policies/euromod_benefit_income_list"
        "#belgium_euromod_ils_ben_family_benefit_pilot_annual_amount"
    )
    BE_EUROMOD_ILS_TAX_WORKER_PIT_PILOT = (
        "be:policies/euromod_tax_income_list"
        "#belgium_euromod_ils_tax_worker_pit_pilot_annual_amount"
    )
    BE_EUROMOD_ILS_DISPY_WORKER_PIT_SIC_PILOT = (
        "be:policies/euromod_disposable_income_list"
        "#belgium_euromod_ils_dispy_worker_pit_sic_pilot_annual_amount"
    )
    BE_WORKER_ARTICLE_17_UNCAPPED_COMPONENT_CONTRIBUTION = (
        "be:statutes/social_security/workers/contribution_rates"
        "#belgium_worker_article_17_uncapped_component_contribution"
    )
    # Regional PIT additional tax (tinrg_be): the reduced State tax defined by
    # the special financing law article 5/2 multiplied by a supplied regional
    # additional-tax percentage. The reduced-tax base is a supplied stage
    # boundary; the case pins it from the engine so both sides levy the region's
    # rate on the identical base.
    BE_REGIONAL_ADDITIONAL_TAX = (
        "be:statutes/income_tax/individual/regional_surcharge"
        "#belgium_pit_regional_additional_tax"
    )
    # Local/municipal PIT additional tax (tinmu_be): the communal additional
    # centimes on the cumulative State-plus-regional tax. The base (reduced State
    # tax plus the regional additional tax) is supplied as two stage boundaries
    # pinned from the engine's tinna_s and tinrg_s, because EUROMOD applies tinmu
    # to tin_s after tinrg.
    BE_LOCAL_COMMUNAL_ADDITIONAL_TAX = (
        "be:statutes/income_tax/individual/regional_surcharge"
        "#belgium_pit_local_municipal_additional_tax"
    )
    # Separately-taxed capital-income tax (tinkt_be): taxable movable income at
    # the article 269 general 30% rate. The taxable movable income is a supplied
    # stage boundary pinned from the engine's post-uprating yiy_s.
    BE_CAPITAL_INCOME_SEPARATE_TAX = (
        "be:statutes/income_tax/movable_withholding/rates"
        "#belgium_capital_income_separate_tax"
    )

    EMPLOYEE_OASDI = "us:tax/payroll#employee_oasdi"
    EMPLOYEE_MEDICARE = "us:tax/payroll#employee_medicare"
    EMPLOYER_OASDI = "us:tax/payroll#employer_oasdi"
    EMPLOYER_MEDICARE = "us:tax/payroll#employer_medicare"
