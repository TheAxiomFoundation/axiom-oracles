from __future__ import annotations

from .be_birth_leave import be_birth_leave_cases
from .ca_cra_family_benefits import ca_cra_family_benefit_cases
from .ca_cra_pdoc import ca_cra_pdoc_cases
from .be_social_assistance import (
    be_elderly_income_support_cases,
    be_social_assistance_cases,
)
from .be_study_allowance import be_study_allowance_cases
from .be_family_benefits import (
    be_family_birth_allowance_cases,
    be_family_child_benefit_brussels_same_age_household_cases,
    be_family_child_benefit_base_cases,
    be_family_child_benefit_income_list_cases,
    be_family_child_benefit_social_supplement_cases,
    be_family_child_benefit_wallonia_social_supplement_cases,
)
from .be_flemish_jobbonus import be_flemish_jobbonus_cases
from .be_flemish_social_protection import be_flemish_social_protection_premium_cases
from .be_maternity_leave import be_maternity_leave_cases
from .be_pensioner_contributions import be_pensioner_contributions_cases
from .be_property_tax import (
    be_cadastral_income_indexation_cases,
    be_property_tax_cases,
)
from .be_regional_local_capital import (
    be_capital_income_tax_cases,
    be_local_municipal_pit_cases,
    be_regional_pit_surcharge_cases,
)
from .be_self_employed import be_self_employed_ssc_cases
from .be_special_social_security import (
    be_special_social_security_contribution_cases,
)
from .be_unemployment import be_unemployment_cases
from .be_worker import (
    be_article_51_forfait_cases,
    be_employer_ssc_cases,
    be_marital_quotient_cases,
    be_pit_work_bonus_credit_cases,
    be_worker_disposable_income_list_cases,
    be_worker_pit_cases,
    be_worker_ssc_cases,
    be_worker_tax_income_list_cases,
)
from .dk_child_youth_benefit import (
    dk_child_youth_benefit_2023_cases,
    dk_child_youth_benefit_cases,
    dk_child_youth_benefit_couple_cases,
)
from .de_worker import de_worker_dual_oracle_cases
from .nyc_basic import nyc_basic_cases
from .nyc_synthetic import nyc_synthetic_cases
from .uk_income_tax import (
    uk_income_tax_dividend_cases,
    uk_income_tax_mixed_cases,
    uk_income_tax_savings_cases,
    uk_income_tax_scottish_cases,
)
from .uk_self_employed import (
    uk_employer_secondary_nic_cases,
    uk_self_employed_nic_cases,
)
from .uk_benefit_cap import uk_benefit_cap_cases
from .uk_child_benefit import uk_child_benefit_cases
from .uk_ctr import uk_ctr_cases
from .uk_housing_benefit import uk_housing_benefit_cases
from .uk_scottish_child_payment import uk_scottish_child_payment_cases
from .uk_child_winter_heating_payment import uk_child_winter_heating_payment_cases
from .uk_contribution_based_jsa import uk_contribution_based_jsa_cases
from .uk_scottish_carer_supplement import uk_scottish_carer_supplement_cases
from .uk_passported_grants import (
    uk_best_start_foods_cases,
    uk_healthy_start_cases,
    uk_sure_start_maternity_grant_cases,
)
from .uk_pension_credit import uk_pension_credit_cases
from .uk_personal_allowance import uk_personal_allowance_cases
from .uk_statutory_pay import (
    uk_maternity_allowance_cases,
    uk_statutory_maternity_pay_cases,
    uk_statutory_paternity_pay_cases,
)
from .uk_universal_credit import uk_universal_credit_cases
from .uk_winter_fuel import uk_winter_fuel_cases
from .uk_worker import (
    uk_worker_nic_cases,
    uk_worker_pit_cases,
)
from .us_tariff import us_tariff_cases


def available_suites() -> tuple[str, ...]:
    return (
        "ca-cra-family-benefits",
        "ca-cra-pdoc",
        "nyc-basic",
        "nyc-synthetic",
        "be-worker-pit",
        "be-article-51-forfait",
        "be-work-bonus-credit",
        "be-marital-quotient",
        "be-worker-tax-income-list",
        "be-worker-disposable-income-list",
        "be-worker-ssc",
        "be-employer-ssc",
        "be-self-employed-ssc",
        "be-special-social-security-contribution",
        "be-birth-leave",
        "be-maternity-leave",
        "be-family-birth-allowance",
        "be-family-child-benefit-base",
        "be-family-child-benefit-income-list",
        "be-family-child-benefit-social-supplement",
        "be-family-child-benefit-brussels-same-age-household",
        "be-family-child-benefit-wallonia-social-supplement",
        "be-flemish-jobbonus",
        "be-cadastral-income-indexation",
        "be-property-tax",
        "be-regional-pit-surcharge",
        "be-local-municipal-pit",
        "be-capital-income-tax",
        "be-flemish-social-protection-premium",
        "be-social-assistance",
        "be-elderly-income-support",
        "be-study-allowance",
        "be-unemployment",
        "be-pensioner-contributions",
        "dk-child-youth-benefit",
        "dk-child-youth-benefit-2023",
        "dk-child-youth-benefit-couple",
        "de-worker-dual-oracle",
        "uk-worker-pit",
        "uk-personal-allowance",
        "uk-worker-nic",
        "uk-self-employed-nic",
        "uk-employer-nic",
        "uk-universal-credit",
        "uk-benefit-cap",
        "uk-winter-fuel",
        "uk-pension-credit",
        "uk-housing-benefit",
        "uk-ctr",
        "uk-scottish-child-payment",
        "uk-child-winter-heating-payment",
        "uk-contribution-based-jsa",
        "uk-scottish-carer-supplement",
        "uk-income-tax-scottish",
        "uk-child-benefit",
        "uk-statutory-maternity-pay",
        "uk-maternity-allowance",
        "uk-statutory-paternity-pay",
        "uk-sure-start-maternity-grant",
        "uk-healthy-start",
        "uk-best-start-foods",
        "uk-income-tax-savings",
        "uk-income-tax-dividend",
        "uk-income-tax-mixed",
        "us-tariff",
    )


def load_suite(name: str):
    if name == "ca-cra-family-benefits":
        return ca_cra_family_benefit_cases()
    if name == "ca-cra-pdoc":
        return ca_cra_pdoc_cases()
    if name == "nyc-basic":
        return nyc_basic_cases()
    if name == "nyc-synthetic":
        return nyc_synthetic_cases()
    if name == "be-worker-pit":
        return be_worker_pit_cases()
    if name == "be-article-51-forfait":
        return be_article_51_forfait_cases()
    if name == "be-work-bonus-credit":
        return be_pit_work_bonus_credit_cases()
    if name == "be-marital-quotient":
        return be_marital_quotient_cases()
    if name == "be-worker-tax-income-list":
        return be_worker_tax_income_list_cases()
    if name == "be-worker-disposable-income-list":
        return be_worker_disposable_income_list_cases()
    if name == "be-worker-ssc":
        return be_worker_ssc_cases()
    if name == "be-employer-ssc":
        return be_employer_ssc_cases()
    if name == "be-self-employed-ssc":
        return be_self_employed_ssc_cases()
    if name == "be-special-social-security-contribution":
        return be_special_social_security_contribution_cases()
    if name == "be-birth-leave":
        return be_birth_leave_cases()
    if name == "be-maternity-leave":
        return be_maternity_leave_cases()
    if name == "be-family-birth-allowance":
        return be_family_birth_allowance_cases()
    if name == "be-family-child-benefit-base":
        return be_family_child_benefit_base_cases()
    if name == "be-family-child-benefit-income-list":
        return be_family_child_benefit_income_list_cases()
    if name == "be-family-child-benefit-social-supplement":
        return be_family_child_benefit_social_supplement_cases()
    if name == "be-family-child-benefit-brussels-same-age-household":
        return be_family_child_benefit_brussels_same_age_household_cases()
    if name == "be-family-child-benefit-wallonia-social-supplement":
        return be_family_child_benefit_wallonia_social_supplement_cases()
    if name == "be-flemish-jobbonus":
        return be_flemish_jobbonus_cases()
    if name == "be-cadastral-income-indexation":
        return be_cadastral_income_indexation_cases()
    if name == "be-property-tax":
        return be_property_tax_cases()
    if name == "be-regional-pit-surcharge":
        return be_regional_pit_surcharge_cases()
    if name == "be-local-municipal-pit":
        return be_local_municipal_pit_cases()
    if name == "be-capital-income-tax":
        return be_capital_income_tax_cases()
    if name == "be-flemish-social-protection-premium":
        return be_flemish_social_protection_premium_cases()
    if name == "be-social-assistance":
        return be_social_assistance_cases()
    if name == "be-elderly-income-support":
        return be_elderly_income_support_cases()
    if name == "be-study-allowance":
        return be_study_allowance_cases()
    if name == "be-unemployment":
        return be_unemployment_cases()
    if name == "be-pensioner-contributions":
        return be_pensioner_contributions_cases()
    if name == "dk-child-youth-benefit":
        return dk_child_youth_benefit_cases()
    if name == "dk-child-youth-benefit-2023":
        return dk_child_youth_benefit_2023_cases()
    if name == "dk-child-youth-benefit-couple":
        return dk_child_youth_benefit_couple_cases()
    if name == "de-worker-dual-oracle":
        return de_worker_dual_oracle_cases()
    if name == "uk-worker-pit":
        return uk_worker_pit_cases()
    if name == "uk-personal-allowance":
        return uk_personal_allowance_cases()
    if name == "uk-worker-nic":
        return uk_worker_nic_cases()
    if name == "uk-self-employed-nic":
        return uk_self_employed_nic_cases()
    if name == "uk-employer-nic":
        return uk_employer_secondary_nic_cases()
    if name == "uk-universal-credit":
        return uk_universal_credit_cases()
    if name == "uk-benefit-cap":
        return uk_benefit_cap_cases()
    if name == "uk-winter-fuel":
        return uk_winter_fuel_cases()
    if name == "uk-pension-credit":
        return uk_pension_credit_cases()
    if name == "uk-housing-benefit":
        return uk_housing_benefit_cases()
    if name == "uk-ctr":
        return uk_ctr_cases()
    if name == "uk-scottish-child-payment":
        return uk_scottish_child_payment_cases()
    if name == "uk-child-winter-heating-payment":
        return uk_child_winter_heating_payment_cases()
    if name == "uk-contribution-based-jsa":
        return uk_contribution_based_jsa_cases()
    if name == "uk-scottish-carer-supplement":
        return uk_scottish_carer_supplement_cases()
    if name == "uk-income-tax-scottish":
        return uk_income_tax_scottish_cases()
    if name == "uk-child-benefit":
        return uk_child_benefit_cases()
    if name == "uk-statutory-maternity-pay":
        return uk_statutory_maternity_pay_cases()
    if name == "uk-maternity-allowance":
        return uk_maternity_allowance_cases()
    if name == "uk-statutory-paternity-pay":
        return uk_statutory_paternity_pay_cases()
    if name == "uk-sure-start-maternity-grant":
        return uk_sure_start_maternity_grant_cases()
    if name == "uk-healthy-start":
        return uk_healthy_start_cases()
    if name == "uk-best-start-foods":
        return uk_best_start_foods_cases()
    if name == "uk-income-tax-savings":
        return uk_income_tax_savings_cases()
    if name == "uk-income-tax-dividend":
        return uk_income_tax_dividend_cases()
    if name == "uk-income-tax-mixed":
        return uk_income_tax_mixed_cases()
    if name == "us-tariff":
        return us_tariff_cases()
    raise ValueError(f"Unknown suite: {name}")


__all__ = [
    "available_suites",
    "be_article_51_forfait_cases",
    "be_birth_leave_cases",
    "ca_cra_family_benefit_cases",
    "ca_cra_pdoc_cases",
    "be_capital_income_tax_cases",
    "be_elderly_income_support_cases",
    "be_employer_ssc_cases",
    "be_family_birth_allowance_cases",
    "be_family_child_benefit_brussels_same_age_household_cases",
    "be_family_child_benefit_base_cases",
    "be_family_child_benefit_income_list_cases",
    "be_family_child_benefit_social_supplement_cases",
    "be_family_child_benefit_wallonia_social_supplement_cases",
    "be_flemish_jobbonus_cases",
    "be_flemish_social_protection_premium_cases",
    "be_local_municipal_pit_cases",
    "be_maternity_leave_cases",
    "be_pensioner_contributions_cases",
    "be_pit_work_bonus_credit_cases",
    "be_cadastral_income_indexation_cases",
    "be_property_tax_cases",
    "be_regional_pit_surcharge_cases",
    "be_self_employed_ssc_cases",
    "be_special_social_security_contribution_cases",
    "be_social_assistance_cases",
    "be_study_allowance_cases",
    "be_unemployment_cases",
    "be_worker_disposable_income_list_cases",
    "be_worker_pit_cases",
    "be_worker_ssc_cases",
    "be_worker_tax_income_list_cases",
    "dk_child_youth_benefit_cases",
    "de_worker_dual_oracle_cases",
    "load_suite",
    "nyc_basic_cases",
    "nyc_synthetic_cases",
    "uk_benefit_cap_cases",
    "uk_best_start_foods_cases",
    "uk_child_benefit_cases",
    "uk_ctr_cases",
    "uk_healthy_start_cases",
    "uk_housing_benefit_cases",
    "uk_scottish_child_payment_cases",
    "uk_child_winter_heating_payment_cases",
    "uk_contribution_based_jsa_cases",
    "uk_scottish_carer_supplement_cases",
    "uk_maternity_allowance_cases",
    "uk_winter_fuel_cases",
    "uk_pension_credit_cases",
    "uk_personal_allowance_cases",
    "uk_sure_start_maternity_grant_cases",
    "uk_statutory_maternity_pay_cases",
    "uk_statutory_paternity_pay_cases",
    "uk_employer_secondary_nic_cases",
    "uk_income_tax_dividend_cases",
    "uk_income_tax_mixed_cases",
    "uk_income_tax_savings_cases",
    "uk_income_tax_scottish_cases",
    "uk_self_employed_nic_cases",
    "uk_universal_credit_cases",
    "uk_worker_nic_cases",
    "uk_worker_pit_cases",
    "us_tariff_cases",
]
