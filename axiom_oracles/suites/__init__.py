from __future__ import annotations

from .be_social_assistance import (
    be_elderly_income_support_cases,
    be_social_assistance_cases,
)
from .be_family_benefits import (
    be_family_birth_allowance_cases,
    be_family_child_benefit_base_cases,
    be_family_child_benefit_social_supplement_cases,
    be_family_child_benefit_wallonia_social_supplement_cases,
)
from .be_flemish_jobbonus import be_flemish_jobbonus_cases
from .be_flemish_social_protection import be_flemish_social_protection_premium_cases
from .be_self_employed import be_self_employed_ssc_cases
from .be_special_social_security import (
    be_special_social_security_contribution_cases,
)
from .be_worker import be_worker_pit_cases, be_worker_ssc_cases
from .nyc_basic import nyc_basic_cases
from .nyc_synthetic import nyc_synthetic_cases


def available_suites() -> tuple[str, ...]:
    return (
        "nyc-basic",
        "nyc-synthetic",
        "be-worker-pit",
        "be-worker-ssc",
        "be-self-employed-ssc",
        "be-special-social-security-contribution",
        "be-family-birth-allowance",
        "be-family-child-benefit-base",
        "be-family-child-benefit-social-supplement",
        "be-family-child-benefit-wallonia-social-supplement",
        "be-flemish-jobbonus",
        "be-flemish-social-protection-premium",
        "be-social-assistance",
        "be-elderly-income-support",
    )


def load_suite(name: str):
    if name == "nyc-basic":
        return nyc_basic_cases()
    if name == "nyc-synthetic":
        return nyc_synthetic_cases()
    if name == "be-worker-pit":
        return be_worker_pit_cases()
    if name == "be-worker-ssc":
        return be_worker_ssc_cases()
    if name == "be-self-employed-ssc":
        return be_self_employed_ssc_cases()
    if name == "be-special-social-security-contribution":
        return be_special_social_security_contribution_cases()
    if name == "be-family-birth-allowance":
        return be_family_birth_allowance_cases()
    if name == "be-family-child-benefit-base":
        return be_family_child_benefit_base_cases()
    if name == "be-family-child-benefit-social-supplement":
        return be_family_child_benefit_social_supplement_cases()
    if name == "be-family-child-benefit-wallonia-social-supplement":
        return be_family_child_benefit_wallonia_social_supplement_cases()
    if name == "be-flemish-jobbonus":
        return be_flemish_jobbonus_cases()
    if name == "be-flemish-social-protection-premium":
        return be_flemish_social_protection_premium_cases()
    if name == "be-social-assistance":
        return be_social_assistance_cases()
    if name == "be-elderly-income-support":
        return be_elderly_income_support_cases()
    raise ValueError(f"Unknown suite: {name}")


__all__ = [
    "available_suites",
    "be_elderly_income_support_cases",
    "be_family_birth_allowance_cases",
    "be_family_child_benefit_base_cases",
    "be_family_child_benefit_social_supplement_cases",
    "be_family_child_benefit_wallonia_social_supplement_cases",
    "be_flemish_jobbonus_cases",
    "be_flemish_social_protection_premium_cases",
    "be_self_employed_ssc_cases",
    "be_special_social_security_contribution_cases",
    "be_social_assistance_cases",
    "be_worker_pit_cases",
    "be_worker_ssc_cases",
    "load_suite",
    "nyc_basic_cases",
    "nyc_synthetic_cases",
]
