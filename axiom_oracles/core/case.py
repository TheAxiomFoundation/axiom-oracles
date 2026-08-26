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

    # Resources (person-level stock). SSI countable resources — 42 USC 1382b(a)
    # resources net of the statutory exclusions — feed the 1382(a)(1)(B) resource
    # screen ($2,000 individual / $3,000 couple). PolicyEngine populates this from
    # the certified populace-us artifact, so Axiom must screen the same value.
    SSI_COUNTABLE_RESOURCES = "axiom:resources/person#ssi_countable_resources"

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
    MEDICAID_PREGNANT_WOMEN_ELIGIBLE = "us:programs/medicaid-pregnant-women#eligible"
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
    # The Income Tax Act 2007 section 35 personal allowance exposed as a named
    # step of the same composed worker-PIT pipeline (the preliminary allowance
    # less the section 35(2)-(3) income-limit taper), compared against UKMOD's
    # final personal allowance ``tinta_s`` on a pure single-individual income
    # sweep (axiom-oracles#190).
    UK_PERSONAL_ALLOWANCE = (
        "uk:statutes/income_tax/individual/pilot_worker_oracle_pipeline"
        "#uk_pit_pilot_personal_allowance"
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
        "uk:policies/universal_credit_composed_award_pipeline#uc_pilot_award_amount"
    )
    # Benefit-cap reduction of the Universal Credit award (UC Regulations 2013
    # regulation 80A/81), the monthly amount by which the section 8(1) award is
    # reduced when total welfare benefits exceed the regulation-80A relevant
    # amount. Exposed as ``uc_pilot_benefit_cap_reduction`` by the composed UC
    # pipeline; it is the direct analog of UKMOD's separate ``brduc_s`` output
    # (UKMOD carries the cap effect in ``brduc_s`` and reports the uncapped
    # ``bsauc_s``, so the reduction is compared on its own rather than through
    # the award).
    UK_HOUSEHOLD_BENEFIT_CAP_UC_REDUCTION = (
        "uk:policies/universal_credit_composed_award_pipeline"
        "#uc_pilot_benefit_cap_reduction"
    )
    # Composed Winter Fuel Payment award pipeline (rulespec-uk) that wires the
    # Social Fund Winter Fuel Payment Regulations 2025 (SI 2025/969) regulation 3
    # England-and-Wales standard amounts (£200 under-80, £300 at-80) with the
    # pension-age member count, the unit-level 80+ tier, and the 2025/26
    # income-recovery means-test gate supplied as inputs, so an end-to-end UKMOD
    # comparison (Winter Fuel ``boaht_s``) can run on a shared pensioner grid.
    # The final award is the annual household amount, exposed as
    # ``wfp_pilot_award_amount`` by
    # ``uk/policies/winter_fuel_payment_composed_award_pipeline.yaml``.
    UK_HOUSEHOLD_WINTER_FUEL_PAYMENT_AWARD = (
        "uk:policies/winter_fuel_payment_composed_award_pipeline#wfp_pilot_award_amount"
    )
    # Composed Pension Credit guarantee-credit award pipeline (rulespec-uk) that
    # wires the State Pension Credit Act 2002 section 2 standard-minimum-
    # guarantee, additional-amount, and income-difference stage boundaries from
    # hypothetical pensioner inputs, so an end-to-end UKMOD comparison (Pension
    # Credit ``boamt_s``) can run on a shared household grid. The final award is
    # the weekly guarantee credit, exposed as ``pc_pilot_award_amount`` by
    # ``uk/policies/pension_credit_composed_award_pipeline.yaml``.
    UK_HOUSEHOLD_PENSION_CREDIT_AWARD = (
        "uk:policies/pension_credit_composed_award_pipeline#pc_pilot_award_amount"
    )
    # Composed Housing Benefit entitlement pipeline (rulespec-uk#83) that wires
    # the Housing Benefit Regulations 2006 regulation 22 applicable amount, the
    # regulation 74 / regulation 55 non-dependant deductions, and the
    # regulation 70 / regulation 50 maximum benefit after the regulation 71 /
    # regulation 51 65 per cent taper from hypothetical renter inputs, so an
    # end-to-end UKMOD comparison (Housing Benefit ``bho_s``) can run on a
    # shared renter grid. The final award is the annual entitlement, exposed as
    # ``hb_pilot_entitlement`` by
    # ``uk/policies/housing_benefit_composed_entitlement_pipeline.yaml``.
    UK_HOUSEHOLD_HOUSING_BENEFIT_AWARD = (
        "uk:policies/housing_benefit_composed_entitlement_pipeline#hb_pilot_entitlement"
    )
    # Scottish Child Payment (rulespec-uk uk/policies/govuk/scottish-child-payment,
    # SSI 2020/351) — the devolved weekly payment for a qualifying child under 16
    # whose applicant or partner receives a qualifying means-tested benefit, paid
    # per child at the flat weekly rate. The per-child annual amount
    # (scottish_child_payment_annual_amount) grades against UKMOD's benefit-unit
    # Scottish Child Payment output bchmt_s on single-child Scotland cases.
    UK_HOUSEHOLD_SCOTTISH_CHILD_PAYMENT_AWARD = (
        "uk:policies/govuk/scottish-child-payment#scottish_child_payment_annual_amount"
    )
    # Child Winter Heating Payment (rulespec-uk
    # uk/policies/govuk/child-winter-heating-payment, SSI 2020/352) — the devolved
    # flat annual payment for a severely disabled child or young person in
    # Scotland on the high-rate care passport. The statutory payable value
    # (child_winter_heating_assistance_payable_value) grades against UKMOD's
    # bchht_s at an exact GBP 265.50/year.
    UK_HOUSEHOLD_CHILD_WINTER_HEATING_PAYMENT_AWARD = (
        "uk:policies/govuk/child-winter-heating-payment"
        "#child_winter_heating_assistance_payable_value"
    )
    # Contribution-based JSA (rulespec-uk
    # uk/policies/govuk/contribution-based-jobseekers-allowance, SI 1996/207 reg 79)
    # — the reserved, UK-wide age-related weekly amount annualised over 52 weeks.
    # The annual amount (contribution_based_jsa_annual_amount) grades against
    # UKMOD's bunct_s (u25 3944.61, 25+ 4982.25; 365/7-vs-52 residual).
    UK_HOUSEHOLD_CONTRIBUTION_BASED_JSA_AWARD = (
        "uk:policies/govuk/contribution-based-jobseekers-allowance"
        "#contribution_based_jsa_annual_amount"
    )
    # Scottish Carer Supplement (rulespec-uk
    # uk/policies/govuk/scottish-carer-supplement, SSI 2023/302 reg 16(1A)) — the
    # devolved carer top-up (GBP 11.70/week) annualised over 52 weeks. The annual
    # amount (scottish_carer_supplement_annual_amount) grades against UKMOD's
    # bcrdicm_s (609.55; small annualisation residual).
    UK_HOUSEHOLD_SCOTTISH_CARER_SUPPLEMENT_AWARD = (
        "uk:policies/govuk/scottish-carer-supplement"
        "#scottish_carer_supplement_annual_amount"
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
    # Statutory-pay / maternity stack. Each composed pilot reconstructs the live
    # UKMOD UK_2026 output (bmact_s / bmanc_s / bpact_s) from a supplied weekly
    # earnings figure: 0.9 x normal weekly earnings x the paid-period weeks, the
    # earnings-related limb UKMOD applies for the hypothetical case.
    UK_STATUTORY_MATERNITY_PAY = (
        "uk:statutes/statutory_maternity_pay/pilot_statutory_maternity_pay_oracle_pipeline"
        "#uk_smp_pilot_total_entitlement"
    )
    UK_MATERNITY_ALLOWANCE = (
        "uk:statutes/maternity_allowance/pilot_maternity_allowance_oracle_pipeline"
        "#uk_ma_pilot_total_entitlement"
    )
    UK_STATUTORY_PATERNITY_PAY = (
        "uk:statutes/statutory_paternity_pay/pilot_statutory_paternity_pay_oracle_pipeline"
        "#uk_spp_pilot_total_entitlement"
    )
    # Passported maternity/food grants. Each gates on a qualifying means-tested
    # benefit in payment (in the UKMOD comparison, Universal Credit bsauc_s>0
    # with the take-up draw pinned on) and, once passported, pays a deterministic
    # statutory amount UKMOD reports as bmamt_s / bmamt01_s / bmascmt01_s.
    #
    # Sure Start Maternity Grant: the £500 lump sum a passported family with a
    # child under one and no other dependent children receives (SI 2005/3061
    # reg.5). The composed pilot exposes it as a Person-level annual entitlement
    # (the reg.5 parameter itself is entity-less, so it does not project onto the
    # comparison's Person entity) that reconstructs the UKMOD bmamt_s.
    UK_SURE_START_MATERNITY_GRANT = (
        "uk:regulations/uksi/2005/3061/pilot_sure_start_maternity_grant_oracle_pipeline"
        "#uk_ssmg_pilot_annual_entitlement"
    )
    # Healthy Start (rest of UK): the composed pilot annualises the determined
    # weekly voucher value (SI 2005/3262 reg.8, £8.50/week for a child under one)
    # to the annual bmamt01_s, over 52 benefit weeks (0.27% below UKMOD's 365/7).
    UK_HEALTHY_START = (
        "uk:regulations/uksi/2005/3262/pilot_healthy_start_oracle_pipeline"
        "#uk_hs_pilot_annual_entitlement"
    )
    # Best Start Foods (Scotland): the composed pilot annualises the SSI 2019/193
    # reg.13 weekly value (£11.20/week doubled rate under one, £5.60 basic ages
    # one to three) to the annual bmascmt01_s, over 52 benefit weeks.
    UK_BEST_START_FOODS = (
        "uk:regulations/ssi/2019/193/pilot_best_start_foods_oracle_pipeline"
        "#uk_bsf_pilot_annual_entitlement"
    )
    # Stable semantic contracts for Germany's direct EUROMOD↔GETTSIM worker
    # baseline. These concepts deliberately name the common household amounts,
    # rather than either engine's variable, so a composed rulespec-de target can
    # attach later without changing the comparison history.
    DE_EMPLOYEE_HEALTH_INSURANCE_CONTRIBUTION_MONTHLY = (
        "de:policies/worker_dual_oracle_baseline"
        "#employee_health_insurance_contribution_monthly"
    )
    DE_EMPLOYEE_PENSION_INSURANCE_CONTRIBUTION_MONTHLY = (
        "de:policies/worker_dual_oracle_baseline"
        "#employee_pension_insurance_contribution_monthly"
    )
    DE_EMPLOYEE_UNEMPLOYMENT_INSURANCE_CONTRIBUTION_MONTHLY = (
        "de:policies/worker_dual_oracle_baseline"
        "#employee_unemployment_insurance_contribution_monthly"
    )
    DE_EMPLOYEE_LONG_TERM_CARE_INSURANCE_CONTRIBUTION_MONTHLY = (
        "de:policies/worker_dual_oracle_baseline"
        "#employee_long_term_care_insurance_contribution_monthly"
    )
    DE_INCOME_TAX_INCLUDING_SOLIDARITY_SURCHARGE_ANNUAL = (
        "de:policies/worker_dual_oracle_baseline"
        "#income_tax_including_solidarity_surcharge_annual"
    )
    DE_KINDERGELD_MONTHLY = "de:policies/worker_dual_oracle_baseline#kindergeld_monthly"
    BE_PERSONAL_INCOME_TAX = (
        "be:statutes/income_tax/individual/tax_liability_pipeline"
        "#belgium_pit_final_income_tax_payable"
    )
    BE_WORKER_PIT_BEFORE_WITHHOLDING = (
        "be:statutes/income_tax/individual/pilot_worker_oracle_pipeline"
        "#belgium_pit_pilot_federal_and_local_tax_before_withholding"
    )
    BE_ARTICLE_51_EMPLOYEE_FORFAIT = (
        "be:statutes/income_tax/individual/pilot_worker_oracle_pipeline"
        "#belgium_pit_pilot_worker_forfait_professional_expenses"
    )
    BE_ARTICLE_289TER1_WORK_BONUS_CREDIT = (
        "be:statutes/income_tax/individual/pilot_worker_oracle_pipeline"
        "#belgium_pit_pilot_article_289ter1_low_wage_work_bonus_credit"
    )
    BE_MARITAL_QUOTIENT_COUPLE_PIT_BEFORE_WITHHOLDING = (
        "be:statutes/income_tax/individual/couple_pit_oracle_pipeline"
        "#belgium_pit_couple_federal_and_local_tax_before_withholding"
    )
    BE_PENSIONER_PIT_BEFORE_WITHHOLDING = (
        "be:statutes/income_tax/individual/pensioner_pit_oracle_pipeline"
        "#belgium_pit_pensioner_federal_and_local_tax_before_withholding"
    )
    BE_PENSIONER_ANNUAL_SOCIAL_WITHHOLDING = (
        "be:statutes/income_tax/individual/pensioner_pit_oracle_pipeline"
        "#belgium_pit_pensioner_annual_social_withholding"
    )
    BE_PENSIONER_REPLACEMENT_REDUCTION = (
        "be:statutes/income_tax/individual/pensioner_pit_oracle_pipeline"
        "#belgium_pit_pensioner_replacement_reduction_after_limits"
    )
    BE_REPLACEMENT_UNEMPLOYMENT_REDUCTION = (
        "be:statutes/income_tax/individual/pensioner_pit_oracle_pipeline"
        "#belgium_pit_replacement_unemployment_reduction_after_limits"
    )
    BE_REPLACEMENT_SICKNESS_INVALIDITY_REDUCTION = (
        "be:statutes/income_tax/individual/pensioner_pit_oracle_pipeline"
        "#belgium_pit_replacement_sickness_invalidity_reduction_after_limits"
    )
    BE_SELF_EMPLOYMENT_PIT_BEFORE_WITHHOLDING = (
        "be:statutes/income_tax/individual/self_employed_oracle_pipeline"
        "#belgium_pit_self_employment_federal_regional_and_local_tax_before_withholding"
    )
    BE_SELF_EMPLOYMENT_COMBINED_TAXABLE_INCOME = (
        "be:statutes/income_tax/individual/self_employed_oracle_pipeline"
        "#belgium_pit_self_employment_combined_worker_and_self_employment_taxable_income"
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
    BE_UNEMPLOYMENT_ORDINARY_BENEFIT = (
        "be:regulations/unemployment/pilot_oracle_pipeline"
        "#belgium_unemployment_ordinary_pilot_monthly_payable_amount"
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
        "be-vlg:regulations/employment/jobbonus#flanders_jobbonus_annual_amount"
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
    BE_STUDY_ALLOWANCE = (
        "be:statutes/education/study_allowance_routing"
        "#belgium_study_allowance_annual_amount"
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

    # Composed Denmark børne- og ungeydelse pipelines (rulespec-dk). The
    # original surface pays one recipient and the couple surface applies § 4,
    # stk. 1 ligedeling plus a separate own-income § 1 a taper to each holder.
    # The couple comparison executes both Person rows and sums their results to
    # the household level, matching EUROMOD's bfachnm_s aggregation boundary.
    DK_CHILD_YOUTH_BENEFIT = (
        "dk:statutes/composed/boerne-og-ungeydelse-pipeline"
        "#single_recipient_annual_child_youth_benefit"
    )
    DK_COUPLE_CHILD_YOUTH_BENEFIT = (
        "dk:statutes/composed/boerne-og-ungeydelse-couple-pipeline"
        "#couple_recipient_annual_child_youth_benefit"
    )

    EMPLOYEE_OASDI = "us:tax/payroll#employee_oasdi"
    EMPLOYEE_MEDICARE = "us:tax/payroll#employee_medicare"
    EMPLOYER_OASDI = "us:tax/payroll#employer_oasdi"
    EMPLOYER_MEDICARE = "us:tax/payroll#employer_medicare"
    # Employee-side FICA plus SECA — the scope of TAXSIM's `tfica` column.
    EMPLOYEE_FICA = "us:tax/payroll#employee_fica"
