"""Compare SNAP RuleSpec output against PolicyEngine over Populace.

The comparator projects PolicyEngine Populace SPM-unit records into a
jurisdiction's SNAP composition input surface, including related member facts,
runs the Axiom rules engine over the projected records, and compares regular monthly SNAP
allotments against PolicyEngine's normal allotment. It uses these targets
because population records do not include application dates for initial-month
proration, and PolicyEngine's top-level ``snap`` microsimulation value includes
take-up adjustments.

For oracle parity, use ``--utility-projection policyengine-type``. That maps
PolicyEngine's own utility-allowance type into the closest jurisdictional
utility facts. The default ``raw-expenses`` mode projects itemized utility
expenses directly and is useful for diagnosing data-projection gaps.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import tempfile
from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from . import snapscreener
from .population import (
    DEFAULT_US_POPULACE_YEAR,
    format_dataset_identity,
    load_populace_dataset,
    populace_data_requirement,
)

try:
    import numpy as np
except ImportError:  # pragma: no cover - exercised only without optional oracle deps
    np = None


PE_COMPARED_OUTPUT = "snap_normal_allotment"
COMPARED_AXIOM_OUTPUT = "snap_regular_month_allotment"
AXIOM_RELATION_ID_BY_LABEL = {
    "member_of_household": "us:statutes/7/2012/j#relation.member_of_household",
}
COMMON_AXIOM_OUTPUT_ID_BY_LABEL = {
    "snap_regular_month_allotment": "us:statutes/7/2017/a#snap_regular_month_allotment",
    "snap_gross_monthly_income": (
        "us:regulations/7-cfr/273/10#snap_total_gross_income"
    ),
    "snap_net_income": "us:statutes/7/2014/e/6/A#snap_net_income",
    "snap_maximum_allotment": (
        "us:policies/usda/snap/fy-2026-cola/maximum-allotments#snap_maximum_allotment"
    ),
    "snap_excess_shelter_deduction": (
        "us:regulations/7-cfr/273/10#snap_excess_shelter_deduction_for_net_income"
    ),
}


@dataclass(frozen=True)
class JurisdictionConfig:
    jurisdiction: str
    state_code: str
    repo_name: str
    program_relative_path: Path
    output_id_by_label: dict[str, str]
    utility_allowance_labels: tuple[str, ...]
    relation_id: str
    member_entity_type: str
    temp_prefix: str
    display_name: str
    additional_relation_ids: tuple[str, ...] = ()


JURISDICTION_CONFIGS = {
    "us-co": JurisdictionConfig(
        jurisdiction="us-co",
        state_code="CO",
        repo_name="rulespec-us-co",
        program_relative_path=Path(
            "policies/cdhs/snap/fy-2026-benefit-calculation.yaml"
        ),
        output_id_by_label={
            **COMMON_AXIOM_OUTPUT_ID_BY_LABEL,
            "snap_regular_month_allotment": (
                "us-co:regulations/10-ccr-2506-1/4.207.2#snap_allotment"
            ),
            "snap_net_income": "us:regulations/7-cfr/273/10#snap_net_monthly_income",
            "snap_eligible": (
                "us-co:policies/cdhs/snap/fy-2026-benefit-calculation#snap_eligible"
            ),
            "snap_standard_utility_allowance": (
                "us-co:regulations/10-ccr-2506-1/4.407.31#snap_standard_utility_allowance"
            ),
            "snap_limited_utility_allowance": (
                "us-co:regulations/10-ccr-2506-1/4.407.31#snap_limited_utility_allowance"
            ),
            "snap_one_utility_allowance": (
                "us-co:regulations/10-ccr-2506-1/4.407.31#snap_one_utility_allowance"
            ),
            "snap_individual_utility_allowance": (
                "us-co:regulations/10-ccr-2506-1/4.407.31#snap_individual_utility_allowance"
            ),
        },
        utility_allowance_labels=(
            "snap_standard_utility_allowance",
            "snap_limited_utility_allowance",
            "snap_one_utility_allowance",
            "snap_individual_utility_allowance",
        ),
        relation_id=AXIOM_RELATION_ID_BY_LABEL["member_of_household"],
        member_entity_type="Person",
        temp_prefix="co-snap-pe-populace-",
        display_name="Colorado SNAP",
    ),
    "us-ca": JurisdictionConfig(
        jurisdiction="us-ca",
        state_code="CA",
        repo_name="rulespec-us-ca",
        program_relative_path=Path(
            "policies/cdss/snap/fy-2026-benefit-calculation.yaml"
        ),
        output_id_by_label={
            **COMMON_AXIOM_OUTPUT_ID_BY_LABEL,
            "snap_regular_month_allotment": (
                "us:policies/usda/snap/state-plan-composition#snap_benefit"
            ),
            "snap_net_income": "us:regulations/7-cfr/273/10#snap_net_monthly_income",
            "snap_eligible": (
                "us-ca:policies/cdss/snap/fy-2026-benefit-calculation#snap_eligible"
            ),
            "snap_excess_shelter_deduction": (
                "us-ca:policies/cdss/snap/fy-2026-benefit-calculation#snap_excess_shelter_deduction"
            ),
            "snap_standard_utility_allowance": (
                "us-ca:policies/cdss/snap/standard-utility-allowance#snap_standard_utility_allowance"
            ),
            "snap_net_income_before_shelter": (
                "us:regulations/7-cfr/273/10#snap_net_income_before_shelter"
            ),
            "snap_standard_deduction": (
                "us:policies/usda/snap/fy-2026-cola/deductions#snap_standard_deduction"
            ),
            "snap_earned_income_deduction_for_net_income": (
                "us:regulations/7-cfr/273/10#snap_earned_income_deduction_for_net_income"
            ),
            "snap_excess_medical_deduction_for_net_income": (
                "us:regulations/7-cfr/273/10#snap_excess_medical_deduction_for_net_income"
            ),
            "snap_excess_shelter_cost": (
                "us:regulations/7-cfr/273/10#snap_excess_shelter_cost"
            ),
            "snap_full_excess_shelter_deduction_applies": (
                "us:regulations/7-cfr/273/9#snap_full_excess_shelter_deduction_applies"
            ),
        },
        utility_allowance_labels=("snap_standard_utility_allowance",),
        relation_id=(
            "us:policies/usda/snap/state-plan-composition#relation.member_of_household"
        ),
        member_entity_type="Person",
        temp_prefix="ca-snap-pe-populace-",
        display_name="California SNAP",
        additional_relation_ids=(AXIOM_RELATION_ID_BY_LABEL["member_of_household"],),
    ),
    "us-az": JurisdictionConfig(
        jurisdiction="us-az",
        state_code="AZ",
        repo_name="rulespec-us-az",
        program_relative_path=Path(
            "policies/des/faa5/na-eligibility-and-benefit-determination/"
            "fy-2026-benefit-calculation.yaml"
        ),
        output_id_by_label={
            **COMMON_AXIOM_OUTPUT_ID_BY_LABEL,
            "snap_regular_month_allotment": (
                "us:policies/usda/snap/state-plan-composition#snap_benefit"
            ),
            "snap_gross_monthly_income": (
                "us:policies/usda/snap/state-plan-composition#snap_gross_monthly_income"
            ),
            "snap_net_income": "us:regulations/7-cfr/273/10#snap_net_monthly_income",
            "snap_eligible": (
                "us-az:policies/des/faa5/na-eligibility-and-benefit-determination/fy-2026-benefit-calculation#snap_eligible"
            ),
            "snap_excess_shelter_deduction": (
                "us:regulations/7-cfr/273/10#snap_excess_shelter_deduction_for_net_income"
            ),
        },
        utility_allowance_labels=(),
        relation_id=AXIOM_RELATION_ID_BY_LABEL["member_of_household"],
        member_entity_type="Person",
        temp_prefix="az-snap-pe-populace-",
        display_name="Arizona SNAP",
    ),
    "us-ga": JurisdictionConfig(
        jurisdiction="us-ga",
        state_code="GA",
        repo_name="rulespec-us-ga",
        program_relative_path=Path(
            "policies/dfcs/snap/fy-2026-benefit-calculation.yaml"
        ),
        output_id_by_label={
            **COMMON_AXIOM_OUTPUT_ID_BY_LABEL,
            "snap_regular_month_allotment": (
                "us:policies/usda/snap/state-plan-composition#snap_benefit"
            ),
            "snap_gross_monthly_income": (
                "us:policies/usda/snap/state-plan-composition#snap_gross_monthly_income"
            ),
            "snap_net_income": "us:regulations/7-cfr/273/10#snap_net_monthly_income",
            "snap_eligible": (
                "us-ga:policies/dfcs/snap/fy-2026-benefit-calculation#snap_eligible"
            ),
            "snap_excess_shelter_deduction": (
                "us-ga:policies/dfcs/snap/fy-2026-benefit-calculation#snap_excess_shelter_deduction"
            ),
        },
        utility_allowance_labels=(),
        relation_id=(
            "us:policies/usda/snap/state-plan-composition#relation.member_of_household"
        ),
        member_entity_type="Person",
        temp_prefix="ga-snap-pe-populace-",
        display_name="Georgia SNAP",
        additional_relation_ids=(AXIOM_RELATION_ID_BY_LABEL["member_of_household"],),
    ),
    "us-md": JurisdictionConfig(
        jurisdiction="us-md",
        state_code="MD",
        repo_name="rulespec-us-md",
        program_relative_path=Path(
            "policies/dhs/fia/snap/fy-2026-benefit-calculation.yaml"
        ),
        output_id_by_label={
            **COMMON_AXIOM_OUTPUT_ID_BY_LABEL,
            "snap_regular_month_allotment": (
                "us:policies/usda/snap/state-plan-composition#snap_benefit"
            ),
            "snap_gross_monthly_income": (
                "us:policies/usda/snap/state-plan-composition#snap_gross_monthly_income"
            ),
            "snap_net_income": "us:regulations/7-cfr/273/10#snap_net_monthly_income",
            "snap_eligible": (
                "us-md:policies/dhs/fia/snap/fy-2026-benefit-calculation#snap_eligible"
            ),
            "snap_excess_shelter_deduction": (
                "us-md:policies/dhs/fia/snap/fy-2026-benefit-calculation#snap_excess_shelter_deduction"
            ),
        },
        utility_allowance_labels=(),
        relation_id=(
            "us:policies/usda/snap/state-plan-composition#relation.member_of_household"
        ),
        member_entity_type="Person",
        temp_prefix="md-snap-pe-populace-",
        display_name="Maryland SNAP",
        additional_relation_ids=(AXIOM_RELATION_ID_BY_LABEL["member_of_household"],),
    ),
    "us-tx": JurisdictionConfig(
        jurisdiction="us-tx",
        state_code="TX",
        repo_name="rulespec-us-tx",
        program_relative_path=Path(
            "policies/hhs/texas-works-handbook/fy-2026-benefit-calculation.yaml"
        ),
        output_id_by_label={
            **COMMON_AXIOM_OUTPUT_ID_BY_LABEL,
            "snap_regular_month_allotment": (
                "us:policies/usda/snap/state-plan-composition#snap_benefit"
            ),
            "snap_gross_monthly_income": (
                "us:policies/usda/snap/state-plan-composition#snap_gross_monthly_income"
            ),
            "snap_net_income": "us:regulations/7-cfr/273/10#snap_net_monthly_income",
            "snap_eligible": (
                "us-tx:policies/hhs/texas-works-handbook/fy-2026-benefit-calculation#snap_eligible"
            ),
            "snap_excess_shelter_deduction": (
                "us-tx:policies/hhs/texas-works-handbook/fy-2026-benefit-calculation#snap_excess_shelter_deduction"
            ),
        },
        utility_allowance_labels=(),
        relation_id=(
            "us:policies/usda/snap/state-plan-composition#relation.member_of_household"
        ),
        member_entity_type="Person",
        temp_prefix="tx-snap-pe-populace-",
        display_name="Texas SNAP",
        additional_relation_ids=(AXIOM_RELATION_ID_BY_LABEL["member_of_household"],),
    ),
    "us-ny": JurisdictionConfig(
        jurisdiction="us-ny",
        state_code="NY",
        repo_name="rulespec-us-ny",
        program_relative_path=Path(
            "policies/otda/snap/fy-2026-benefit-calculation.yaml"
        ),
        output_id_by_label={
            **COMMON_AXIOM_OUTPUT_ID_BY_LABEL,
            "snap_gross_monthly_income": (
                "us:policies/usda/snap/state-plan-composition#snap_gross_monthly_income"
            ),
            "snap_eligible": (
                "us-ny:policies/otda/snap/fy-2026-benefit-calculation#snap_eligible"
            ),
            "snap_excess_shelter_deduction": (
                "us-ny:policies/otda/snap/fy-2026-benefit-calculation#snap_excess_shelter_deduction"
            ),
            "snap_standard_utility_allowance": (
                "us-ny:regulations/18-nycrr/387/12/f/3/v/a#snap_standard_utility_allowance"
            ),
            "snap_limited_utility_allowance": (
                "us-ny:regulations/18-nycrr/387/12/f/3/v/b#snap_limited_utility_allowance"
            ),
            "snap_individual_utility_allowance": (
                "us-ny:regulations/18-nycrr/387/12/f/3/v/c#snap_individual_utility_allowance"
            ),
            "snap_total_gross_income": (
                "us:regulations/7-cfr/273/10#snap_total_gross_income"
            ),
            "snap_standard_income_eligible": (
                "us:regulations/7-cfr/273/9#snap_standard_income_eligible"
            ),
            "snap_resource_eligible": (
                "us:regulations/7-cfr/273/8#snap_resource_eligible"
            ),
            "ny_snap_categorically_eligible": (
                "us-ny:regulations/18-nycrr/387/14/a/5#ny_snap_categorically_eligible"
            ),
            "snap_income_limit_exemption_for_categorically_eligible_household": (
                "us-ny:regulations/18-nycrr/387/14/a/5"
                "#snap_income_limit_exemption_for_categorically_eligible_household"
            ),
            "ny_snap_all_members_public_assistance_categorical_path_satisfied": (
                "us-ny:regulations/18-nycrr/387/14/a/5"
                "#ny_snap_all_members_public_assistance_categorical_path_satisfied"
            ),
            "ny_snap_elderly_disabled_200_percent_categorical_path_satisfied": (
                "us-ny:regulations/18-nycrr/387/14/a/5"
                "#ny_snap_elderly_disabled_200_percent_categorical_path_satisfied"
            ),
            "ny_snap_dependent_care_200_percent_categorical_path_satisfied": (
                "us-ny:regulations/18-nycrr/387/14/a/5"
                "#ny_snap_dependent_care_200_percent_categorical_path_satisfied"
            ),
            "ny_snap_earned_income_150_percent_categorical_path_satisfied": (
                "us-ny:regulations/18-nycrr/387/14/a/5"
                "#ny_snap_earned_income_150_percent_categorical_path_satisfied"
            ),
            "ny_snap_residual_130_percent_categorical_path_satisfied": (
                "us-ny:regulations/18-nycrr/387/14/a/5"
                "#ny_snap_residual_130_percent_categorical_path_satisfied"
            ),
        },
        utility_allowance_labels=(
            "snap_standard_utility_allowance",
            "snap_limited_utility_allowance",
            "snap_individual_utility_allowance",
        ),
        relation_id=(
            "us:policies/usda/snap/state-plan-composition"
            "#relation.member_of_household"
        ),
        member_entity_type="Person",
        temp_prefix="ny-snap-pe-populace-",
        display_name="New York SNAP",
        additional_relation_ids=(
            AXIOM_RELATION_ID_BY_LABEL["member_of_household"],
            "us-ny:regulations/18-nycrr/387/14/a/5#relation."
            "ny_snap_categorical_member_of_household",
        ),
    ),
}
AXIOM_MEMBER_INPUT_ID_BY_LABEL = {
    "snap_member_is_elderly_or_disabled": (
        "us:statutes/7/2012/j#input.snap_member_is_elderly_or_disabled"
    ),
    "member_is_us_citizen": ("us:regulations/7-cfr/273/4#input.member_is_us_citizen"),
    "member_is_us_noncitizen_national": (
        "us:regulations/7-cfr/273/4#input.member_is_us_noncitizen_national"
    ),
    "member_is_american_indian_born_in_canada_or_recognized_indian_tribe_member": (
        "us:regulations/7-cfr/273/4#input.member_is_american_indian_born_in_canada_or_recognized_indian_tribe_member"
    ),
    "member_is_hmong_or_highland_laotian_qualifying_person_or_family_member": (
        "us:regulations/7-cfr/273/4#input.member_is_hmong_or_highland_laotian_qualifying_person_or_family_member"
    ),
    "member_is_trafficking_victim_or_qualifying_family_member": (
        "us:regulations/7-cfr/273/4#input.member_is_trafficking_victim_or_qualifying_family_member"
    ),
    "member_is_qualified_alien_with_forty_qualifying_quarters": (
        "us:regulations/7-cfr/273/4#input.member_is_qualified_alien_with_forty_qualifying_quarters"
    ),
    "member_is_refugee": "us:regulations/7-cfr/273/4#input.member_is_refugee",
    "member_is_asylee": "us:regulations/7-cfr/273/4#input.member_is_asylee",
    "member_has_deportation_or_removal_withheld": (
        "us:regulations/7-cfr/273/4#input.member_has_deportation_or_removal_withheld"
    ),
    "member_is_cuban_or_haitian_entrant": (
        "us:regulations/7-cfr/273/4#input.member_is_cuban_or_haitian_entrant"
    ),
    "member_is_amerasian_immigrant": (
        "us:regulations/7-cfr/273/4#input.member_is_amerasian_immigrant"
    ),
    "member_has_eligible_military_connection": (
        "us:regulations/7-cfr/273/4#input.member_has_eligible_military_connection"
    ),
    "member_receives_blindness_or_disability_benefits": (
        "us:regulations/7-cfr/273/4#input.member_receives_blindness_or_disability_benefits"
    ),
    "member_was_lawfully_residing_on_1996_08_22_and_born_on_or_before_1931_08_22": (
        "us:regulations/7-cfr/273/4#input.member_was_lawfully_residing_on_1996_08_22_and_born_on_or_before_1931_08_22"
    ),
    "member_is_under_age_eighteen": (
        "us:regulations/7-cfr/273/4#input.member_is_under_age_eighteen"
    ),
    "member_is_qualified_alien_subject_to_five_year_wait": (
        "us:regulations/7-cfr/273/4#input.member_is_qualified_alien_subject_to_five_year_wait"
    ),
    "qualified_alien_five_year_status_period_met": (
        "us:regulations/7-cfr/273/4#input.qualified_alien_five_year_status_period_met"
    ),
    "alien_status_documentation_missing_or_unwilling": (
        "us:regulations/7-cfr/273/4#input.alien_status_documentation_missing_or_unwilling"
    ),
    "member_refused_or_failed_to_provide_or_apply_for_ssn": (
        "us:regulations/7-cfr/273/6#input.member_refused_or_failed_to_provide_or_apply_for_ssn"
    ),
    "member_has_documentary_or_collateral_evidence_of_ssn_application_or_every_effort": (
        "us:regulations/7-cfr/273/6#input.member_has_documentary_or_collateral_evidence_of_ssn_application_or_every_effort"
    ),
    "state_agency_fault_in_ssn_application_processing": (
        "us:regulations/7-cfr/273/6#input.state_agency_fault_in_ssn_application_processing"
    ),
    "member_unable_to_obtain_documents_required_for_ssn_application_with_caseworker_assistance_needed": (
        "us:regulations/7-cfr/273/6#input.member_unable_to_obtain_documents_required_for_ssn_application_with_caseworker_assistance_needed"
    ),
    "member_ssn_application_filed_pending_state_agency_notification": (
        "us:regulations/7-cfr/273/6#input.member_ssn_application_filed_pending_state_agency_notification"
    ),
    "member_later_provided_ssn_ending_disqualification": (
        "us:regulations/7-cfr/273/6#input.member_later_provided_ssn_ending_disqualification"
    ),
    "enrolled_at_least_half_time": (
        "us:regulations/7-cfr/273/5#input.enrolled_at_least_half_time"
    ),
    "enrolled_in_business_technical_trade_or_vocational_school_requiring_high_school_diploma": (
        "us:regulations/7-cfr/273/5#input.enrolled_in_business_technical_trade_or_vocational_school_requiring_high_school_diploma"
    ),
    "enrolled_in_college_or_university_degree_program": (
        "us:regulations/7-cfr/273/5#input.enrolled_in_college_or_university_degree_program"
    ),
    "student_age": "us:regulations/7-cfr/273/5#input.student_age",
    "student_physically_or_mentally_unfit": (
        "us:regulations/7-cfr/273/5#input.student_physically_or_mentally_unfit"
    ),
    "student_receives_tanf": ("us:regulations/7-cfr/273/5#input.student_receives_tanf"),
    "enrolled_through_jobs_or_successor_program": (
        "us:regulations/7-cfr/273/5#input.enrolled_through_jobs_or_successor_program"
    ),
    "student_paid_employment_hours_per_week": (
        "us:regulations/7-cfr/273/5#input.student_paid_employment_hours_per_week"
    ),
    "student_self_employment_hours_per_week": (
        "us:regulations/7-cfr/273/5#input.student_self_employment_hours_per_week"
    ),
    "student_self_employment_weekly_earnings": (
        "us:regulations/7-cfr/273/5#input.student_self_employment_weekly_earnings"
    ),
    "federal_minimum_wage": ("us:regulations/7-cfr/273/5#input.federal_minimum_wage"),
    "state_agency_averaged_student_work_hours_meet_twenty_per_week": (
        "us:regulations/7-cfr/273/5#input.state_agency_averaged_student_work_hours_meet_twenty_per_week"
    ),
    "student_participating_in_state_or_federally_financed_work_study": (
        "us:regulations/7-cfr/273/5#input.student_participating_in_state_or_federally_financed_work_study"
    ),
    "work_study_approved_at_snap_application": (
        "us:regulations/7-cfr/273/5#input.work_study_approved_at_snap_application"
    ),
    "work_study_approved_for_school_term": (
        "us:regulations/7-cfr/273/5#input.work_study_approved_for_school_term"
    ),
    "student_anticipates_working_in_work_study": (
        "us:regulations/7-cfr/273/5#input.student_anticipates_working_in_work_study"
    ),
    "work_study_exemption_period_active": (
        "us:regulations/7-cfr/273/5#input.work_study_exemption_period_active"
    ),
    "known_student_refused_work_study_assignment": (
        "us:regulations/7-cfr/273/5#input.known_student_refused_work_study_assignment"
    ),
    "student_participating_in_on_the_job_training_program": (
        "us:regulations/7-cfr/273/5#input.student_participating_in_on_the_job_training_program"
    ),
    "student_currently_being_trained_by_employer": (
        "us:regulations/7-cfr/273/5#input.student_currently_being_trained_by_employer"
    ),
    "responsible_for_care_of_dependent_household_member_under_age_six": (
        "us:regulations/7-cfr/273/5#input.responsible_for_care_of_dependent_household_member_under_age_six"
    ),
    "responsible_for_care_of_dependent_household_member_age_six_to_under_twelve": (
        "us:regulations/7-cfr/273/5#input.responsible_for_care_of_dependent_household_member_age_six_to_under_twelve"
    ),
    "adequate_child_care_unavailable_to_attend_class_and_meet_student_work_requirement": (
        "us:regulations/7-cfr/273/5#input.adequate_child_care_unavailable_to_attend_class_and_meet_student_work_requirement"
    ),
    "single_parent_enrolled_full_time_in_higher_education": (
        "us:regulations/7-cfr/273/5#input.single_parent_enrolled_full_time_in_higher_education"
    ),
    "responsible_for_care_of_dependent_child_under_twelve": (
        "us:regulations/7-cfr/273/5#input.responsible_for_care_of_dependent_child_under_twelve"
    ),
    "single_parent_household_condition_satisfied": (
        "us:regulations/7-cfr/273/5#input.single_parent_household_condition_satisfied"
    ),
    "assigned_or_placed_in_higher_education_through_qualifying_employment_training_program": (
        "us:regulations/7-cfr/273/5#input.assigned_or_placed_in_higher_education_through_qualifying_employment_training_program"
    ),
}

STUDENT_MEMBER_INPUT_DEFAULTS = {
    "enrolled_at_least_half_time": False,
    "enrolled_in_business_technical_trade_or_vocational_school_requiring_high_school_diploma": False,
    "enrolled_in_college_or_university_degree_program": False,
    "student_age": 50,
    "student_physically_or_mentally_unfit": False,
    "student_receives_tanf": False,
    "enrolled_through_jobs_or_successor_program": False,
    "student_paid_employment_hours_per_week": 0,
    "student_self_employment_hours_per_week": 0,
    "student_self_employment_weekly_earnings": 0,
    "federal_minimum_wage": 7.25,
    "state_agency_averaged_student_work_hours_meet_twenty_per_week": False,
    "student_participating_in_state_or_federally_financed_work_study": False,
    "work_study_approved_at_snap_application": False,
    "work_study_approved_for_school_term": False,
    "student_anticipates_working_in_work_study": False,
    "work_study_exemption_period_active": False,
    "known_student_refused_work_study_assignment": False,
    "student_participating_in_on_the_job_training_program": False,
    "student_currently_being_trained_by_employer": False,
    "responsible_for_care_of_dependent_household_member_under_age_six": False,
    "responsible_for_care_of_dependent_household_member_age_six_to_under_twelve": False,
    "adequate_child_care_unavailable_to_attend_class_and_meet_student_work_requirement": False,
    "single_parent_enrolled_full_time_in_higher_education": False,
    "responsible_for_care_of_dependent_child_under_twelve": False,
    "single_parent_household_condition_satisfied": False,
    "assigned_or_placed_in_higher_education_through_qualifying_employment_training_program": False,
}

CITIZENSHIP_MEMBER_INPUT_DEFAULTS = {
    "member_is_us_citizen": False,
    "member_is_us_noncitizen_national": False,
    "member_is_american_indian_born_in_canada_or_recognized_indian_tribe_member": False,
    "member_is_hmong_or_highland_laotian_qualifying_person_or_family_member": False,
    "member_is_trafficking_victim_or_qualifying_family_member": False,
    "member_is_qualified_alien_with_forty_qualifying_quarters": False,
    "member_is_refugee": False,
    "member_is_asylee": False,
    "member_has_deportation_or_removal_withheld": False,
    "member_is_cuban_or_haitian_entrant": False,
    "member_is_amerasian_immigrant": False,
    "member_has_eligible_military_connection": False,
    "member_receives_blindness_or_disability_benefits": False,
    "member_was_lawfully_residing_on_1996_08_22_and_born_on_or_before_1931_08_22": False,
    "member_is_under_age_eighteen": False,
    "member_is_qualified_alien_subject_to_five_year_wait": False,
    "qualified_alien_five_year_status_period_met": False,
    "alien_status_documentation_missing_or_unwilling": False,
}

SSN_MEMBER_INPUT_DEFAULTS = {
    "member_refused_or_failed_to_provide_or_apply_for_ssn": False,
    "member_has_documentary_or_collateral_evidence_of_ssn_application_or_every_effort": False,
    "state_agency_fault_in_ssn_application_processing": False,
    "member_unable_to_obtain_documents_required_for_ssn_application_with_caseworker_assistance_needed": False,
    "member_ssn_application_filed_pending_state_agency_notification": False,
    "member_later_provided_ssn_ending_disqualification": False,
}

GENERAL_WORK_MEMBER_AGE_INPUT = "us:regulations/7-cfr/273/7#input.member_age"
ABAWD_MEMBER_AGE_INPUT = "us:regulations/7-cfr/273/24#input.member_age"
WORK_MEMBER_ELIGIBLE_INPUTS = {
    GENERAL_WORK_MEMBER_AGE_INPUT: 60,
    ABAWD_MEMBER_AGE_INPUT: 60,
}
WORK_MEMBER_INELIGIBLE_INPUTS = {
    GENERAL_WORK_MEMBER_AGE_INPUT: 30,
    "us:regulations/7-cfr/273/7#input.member_age_16_or_17_is_not_household_head_or_attends_school_or_training_half_time": False,
    "us:regulations/7-cfr/273/7#input.member_physically_or_mentally_unfit_for_employment": False,
    "us:regulations/7-cfr/273/7#input.member_subject_to_and_complying_with_title_iv_work_requirement": False,
    "us:regulations/7-cfr/273/7#input.member_responsible_for_dependent_child_under_six_or_incapacitated_person": False,
    "us:regulations/7-cfr/273/7#input.member_receiving_or_applying_for_unemployment_compensation_and_complying": False,
    "us:regulations/7-cfr/273/7#input.member_regular_participant_in_drug_or_alcohol_treatment": False,
    "us:regulations/7-cfr/273/7#input.member_weekly_work_hours": 0,
    "us:regulations/7-cfr/273/7#input.member_weekly_wages": 0,
    "us:regulations/7-cfr/273/7#input.federal_or_state_minimum_wage": 7.25,
    "us:regulations/7-cfr/273/7#input.migrant_or_seasonal_farmworker_under_contract_to_begin_employment_within_30_days": False,
    "us:regulations/7-cfr/273/7#input.alaska_subsistence_hunts_or_fishes_30_hours_weekly": False,
    "us:regulations/7-cfr/273/7#input.member_student_enrolled_at_least_half_time_and_student_eligible": False,
    "us:regulations/7-cfr/273/7#input.member_snap_work_requirements_waived_due_to_pending_ssi_joint_application": False,
    "us:regulations/7-cfr/273/7#input.member_registered_for_work_or_registered_by_state": False,
    "us:regulations/7-cfr/273/7#input.member_participated_in_snap_et_if_assigned": True,
    "us:regulations/7-cfr/273/7#input.member_participated_in_workfare_if_assigned": True,
    "us:regulations/7-cfr/273/7#input.member_provided_employment_status_or_availability_information": True,
    "us:regulations/7-cfr/273/7#input.member_reported_to_referred_suitable_employer_if_referred": True,
    "us:regulations/7-cfr/273/7#input.member_accepted_bona_fide_suitable_employment_offer_if_offered": True,
    "us:regulations/7-cfr/273/7#input.member_voluntarily_quit_or_reduced_work_below_30_hours_without_good_cause": False,
    ABAWD_MEMBER_AGE_INPUT: 30,
    "us:regulations/7-cfr/273/24#input.member_medically_certified_physically_or_mentally_unfit_for_employment": False,
    "us:regulations/7-cfr/273/24#input.member_is_parent_of_household_member_under_age_eighteen": False,
    "us:regulations/7-cfr/273/24#input.member_resides_with_household_member_under_age_eighteen": False,
    "us:regulations/7-cfr/273/24#input.member_is_pregnant": False,
    "us:regulations/7-cfr/273/24#input.member_is_homeless": False,
    "us:regulations/7-cfr/273/24#input.member_is_veteran": False,
    "us:regulations/7-cfr/273/24#input.member_age_24_or_younger_and_was_in_foster_care_on_attaining_age_18": False,
    "us:regulations/7-cfr/273/24#input.member_covered_by_abawd_time_limit_waiver": False,
    "us:regulations/7-cfr/273/24#input.member_abawd_weekly_work_hours": 0,
    "us:regulations/7-cfr/273/24#input.member_abawd_monthly_work_hours": 0,
    "us:regulations/7-cfr/273/24#input.member_participates_in_abawd_work_program_20_hours_weekly": False,
    "us:regulations/7-cfr/273/24#input.member_combines_work_and_work_program_20_hours_weekly": False,
    "us:regulations/7-cfr/273/24#input.member_participates_in_abawd_workfare_program": False,
    "us:regulations/7-cfr/273/24#input.snap_abawd_countable_months_in_three_year_period": 4,
    "us:regulations/7-cfr/273/24#input.member_regained_abawd_eligibility": False,
    "us:regulations/7-cfr/273/24#input.member_has_additional_three_month_abawd_eligibility": False,
}


@dataclass(frozen=True)
class Period:
    label: str
    year: int
    month: int
    start: date
    end: date


@dataclass
class ProjectedCase:
    spm_unit_id: int
    household_id: int
    inputs: dict[str, Any]
    member_inputs: list[dict[str, Any]]
    pe_outputs: dict[str, Any]


def configure_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--jurisdiction",
        choices=sorted(JURISDICTION_CONFIGS),
        default="us-co",
        help="RuleSpec jurisdiction composition to compare.",
    )
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--month", type=int, default=1)
    parser.add_argument(
        "--state",
        default=None,
        help="PolicyEngine state code filter. Defaults from --jurisdiction.",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help=(
            "Limit after state filtering. Omit to run all matching Populace SPM units."
        ),
    )
    parser.add_argument(
        "--positive-snap-only",
        action="store_true",
        help=(
            "Only compare Populace SPM units where PolicyEngine normal allotment "
            "is positive."
        ),
    )
    parser.add_argument(
        "--utility-projection",
        choices=("raw-expenses", "policyengine-type"),
        default="raw-expenses",
        help=(
            "How to project Populace utility facts. raw-expenses uses itemized "
            "utility expenses from Populace. policyengine-type maps "
            "PolicyEngine's utility-allowance type into jurisdiction utility "
            "facts for oracle parity."
        ),
    )
    parser.add_argument(
        "--populace-year",
        type=int,
        default=DEFAULT_US_POPULACE_YEAR,
        help="Published US Populace dataset year to load.",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=1.5,
        help=(
            "Dollar tolerance for matching PE. Defaults to 1.5 because PE's "
            "normal allotment can retain fractional dollars while RuleSpec "
            "floors final allotments to whole dollars."
        ),
    )
    parser.add_argument("--max-differences", type=int, default=20)
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="Exit nonzero when any row differs by more than --tolerance.",
    )
    parser.add_argument(
        "--min-match-rate",
        type=float,
        default=None,
        help=(
            "Exit nonzero when the match rate is below this threshold. "
            "Use this for population oracles with documented upstream oracle gaps."
        ),
    )
    parser.add_argument(
        "--program",
        type=Path,
        default=None,
        help="Override the jurisdiction composition RuleSpec file.",
    )
    parser.add_argument(
        "--test-template",
        type=Path,
        default=None,
        help="Override the companion test template used for input references.",
    )
    parser.add_argument(
        "--axiom-binary",
        type=Path,
        default=None,
        help="Path to the axiom-rules-engine binary. Defaults to a sibling checkout.",
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=None,
        help="Workspace containing axiom-rules-engine and rulespec-* repos.",
    )
    parser.add_argument("--write-csv", type=Path, default=None)
    parser.add_argument(
        "--external-oracle",
        choices=("snapscreener",),
        action="append",
        default=[],
        help=(
            "Run an additional diagnostic external oracle. SnapScreener is "
            "fetched as public browser JavaScript and recorded by SHA256."
        ),
    )
    parser.add_argument(
        "--snapscreener-api-js",
        type=Path,
        default=None,
        help=(
            "Use a local SnapScreener api.js bundle instead of fetching "
            "https://tools.snapscreener.com/api.js."
        ),
    )
    parser.add_argument(
        "--snapscreener-cache-dir",
        type=Path,
        default=None,
        help="Directory for the fetched SnapScreener api.js bundle.",
    )
    return parser


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    configure_parser(parser)
    return parser.parse_args()


def _workspace_candidates() -> list[Path]:
    candidates = [
        Path.cwd(),
        Path.cwd().parent,
        Path.home() / "TheAxiomFoundation",
    ]
    module_path = Path(__file__).resolve()
    candidates.extend(module_path.parents)
    return candidates


def resolve_workspace_root(override: Path | None = None) -> Path:
    if override is not None:
        return override.resolve()
    for candidate in _workspace_candidates():
        if (candidate / "axiom-rules-engine").exists() or any(
            candidate.glob("rulespec-*")
        ):
            return candidate.resolve()
        if (candidate / "_axiom" / "axiom-rules-engine").exists():
            return candidate.resolve()
    return (Path.home() / "TheAxiomFoundation").resolve()


def resolve_program_path(
    config: JurisdictionConfig, workspace_root: Path, override: Path | None
) -> Path:
    if override is not None:
        return override.resolve()
    cwd_program = Path.cwd() / config.program_relative_path
    if cwd_program.exists():
        return cwd_program.resolve()
    # The country monorepo's jurisdiction twin is the canonical copy — it is
    # the only layout post-hard-cut engines can resolve imports from (a state
    # repo is not a valid engine root) — so prefer it; the standalone state
    # repo remains the supervised-machine fallback.
    monorepo_program = (
        workspace_root / "rulespec-us" / config.jurisdiction / config.program_relative_path
    )
    if monorepo_program.exists():
        return monorepo_program.resolve()
    return (workspace_root / config.repo_name / config.program_relative_path).resolve()


def resolve_test_template_path(program: Path, override: Path | None) -> Path:
    if override is not None:
        return override.resolve()
    return program.with_name(f"{program.stem}.test.yaml")


def resolve_axiom_binary(workspace_root: Path, override: Path | None) -> Path:
    if override is not None:
        return override.resolve()
    candidates = [
        workspace_root
        / "axiom-rules-engine"
        / "target"
        / "debug"
        / "axiom-rules-engine",
        workspace_root
        / "_axiom"
        / "axiom-rules-engine"
        / "target"
        / "debug"
        / "axiom-rules-engine",
        Path.cwd()
        / "_axiom"
        / "axiom-rules-engine"
        / "target"
        / "debug"
        / "axiom-rules-engine",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0].resolve()


def axiom_rules_env(program: Path, workspace_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    active_roots: list[Path] = []
    current_repo = program.resolve()
    for parent in current_repo.parents:
        if parent.name.startswith("rulespec-"):
            active_roots.append(parent)
            break
    roots = [
        workspace_root / "rulespec-us",
        workspace_root / "_axiom" / "rulespec-us",
        program.parent,
        program.parent.parent,
    ]
    roots.extend(sorted(workspace_root.glob("rulespec-*")))
    roots.extend(sorted((workspace_root / "_axiom").glob("rulespec-*")))
    existing = [path.resolve() for path in roots if path.exists()]
    configured = [
        Path(path).resolve()
        for path in env.get("AXIOM_RULESPEC_REPO_ROOTS", "").split(os.pathsep)
        if path
    ]
    unique_roots = []
    seen: set[Path] = set()
    for path in [*active_roots, *configured, *existing]:
        if path in seen:
            continue
        seen.add(path)
        unique_roots.append(path)
    env["AXIOM_RULESPEC_REPO_ROOTS"] = os.pathsep.join(
        str(path) for path in unique_roots
    )
    return env


def month_period(year: int, month: int) -> Period:
    return Period(
        label=f"{year:04d}-{month:02d}",
        year=year,
        month=month,
        start=date(year, month, 1),
        end=date(year, month, monthrange(year, month)[1]),
    )


def load_base_inputs(path: Path) -> dict[str, Any]:
    cases = yaml.safe_load(path.read_text())
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"{path} must contain at least one test case")
    inputs = cases[0].get("input")
    if not isinstance(inputs, dict):
        raise ValueError(f"{path} first test case must contain an input mapping")
    return {
        str(reference): value
        for reference, value in inputs.items()
        if "#relation." not in str(reference)
    }


def _friendly_input_name(reference: str) -> str | None:
    marker = "#input."
    if marker not in reference:
        return None
    return reference.split(marker, 1)[1]


def legal_input_index(inputs: dict[str, Any]) -> dict[str, str]:
    index: dict[str, str] = {}
    for reference in inputs:
        name = _friendly_input_name(str(reference))
        if name:
            index[name] = str(reference)
    return index


def set_input_value(
    inputs: dict[str, Any],
    name: str,
    value: Any,
    *,
    required: bool = True,
) -> None:
    matched = False
    for reference in list(inputs):
        if _friendly_input_name(str(reference)) == name:
            inputs[reference] = value
            matched = True
    if matched:
        return
    if required:
        inputs[name] = value


def legalize_inputs(
    inputs: dict[str, Any],
    reference_by_name: dict[str, str],
) -> dict[str, Any]:
    legal: dict[str, Any] = {}
    for name, value in inputs.items():
        if "#" in name and ":" in name:
            reference = name
        else:
            reference = reference_by_name.get(name)
            if reference is None:
                raise KeyError(f"no legal RuleSpec input reference for `{name}`")
        legal[reference] = value
    return legal


def project_student_member_inputs(student_eligible: bool) -> dict[str, Any]:
    inputs = dict(STUDENT_MEMBER_INPUT_DEFAULTS)
    if not student_eligible:
        inputs.update(
            {
                "enrolled_at_least_half_time": True,
                "enrolled_in_college_or_university_degree_program": True,
                "student_age": 20,
            }
        )
    return inputs


def project_citizenship_member_inputs(immigration_eligible: bool) -> dict[str, Any]:
    inputs = dict(CITIZENSHIP_MEMBER_INPUT_DEFAULTS)
    if immigration_eligible:
        inputs["member_is_us_citizen"] = True
    return inputs


def project_work_member_inputs(work_eligible: bool) -> dict[str, Any]:
    if work_eligible:
        return dict(WORK_MEMBER_ELIGIBLE_INPUTS)
    return dict(WORK_MEMBER_INELIGIBLE_INPUTS)


def project_income_resource_inputs(
    config: JurisdictionConfig,
    values: dict[str, Any],
    idx: int,
) -> dict[str, Any]:
    earned_income = money(values["snap_earned_income"][idx])
    unearned_income = money(values["snap_unearned_income"][idx])
    assets = money(values["snap_assets"][idx])
    if config.jurisdiction == "us-ny":
        return {
            "snap_gross_monthly_earned_income": earned_income,
            "snap_total_monthly_unearned_income": unearned_income,
            "snap_income_exclusions": 0,
            "snap_countable_financial_resources": assets,
        }
    if config.jurisdiction == "us-ca":
        return {
            "snap_gross_monthly_earned_income": earned_income,
            "snap_total_monthly_unearned_income": unearned_income,
            "snap_countable_financial_resources": assets,
            "snap_categorically_eligible_for_resource_exemption": bool(
                values["meets_snap_categorical_eligibility"][idx]
            ),
        }
    if config.jurisdiction == "us-az":
        return {
            "snap_gross_monthly_earned_income": earned_income,
            "snap_total_monthly_unearned_income": unearned_income,
        }
    return {
        "employee_wages_received": earned_income,
        "other_gain_or_benefit_payments": unearned_income,
        "liquid_resource_current_redemption_rate": assets,
        "snap_basic_categorical_eligible": bool(
            values["meets_snap_categorical_eligibility"][idx]
        ),
        "snap_expanded_categorical_eligible": False,
    }


def project_deduction_inputs(
    config: JurisdictionConfig,
    *,
    dependent_care_deduction: float,
    child_support_deduction: float,
    medical_deduction: float,
) -> dict[str, Any]:
    if config.jurisdiction in ("us-ca", "us-ga", "us-md", "us-az", "us-tx"):
        # These compositions ride the federal state-plan module's 273.10
        # chain only (the 2014(e) statutory modules are not composed), so
        # just the regulatory inputs.
        return {
            "household_entitled_to_excess_medical_deduction": medical_deduction > 0,
            "snap_allowable_monthly_dependent_care_expenses": (
                dependent_care_deduction
            ),
            "snap_allowable_monthly_child_support_payments": child_support_deduction,
            "snap_total_medical_expenses": medical_expenses_for_deduction(
                medical_deduction
            ),
        }
    if config.jurisdiction == "us-ny":
        return {
            "dependent_care_deduction": dependent_care_deduction,
            "child_support_deduction": child_support_deduction,
            "medical_deduction": medical_deduction,
            (
                "us:regulations/7-cfr/273/10#input."
                "household_entitled_to_excess_medical_deduction"
            ): medical_deduction > 0,
            (
                "us:regulations/7-cfr/273/10#input.snap_total_medical_expenses"
            ): medical_expenses_for_deduction(medical_deduction),
            (
                "us:regulations/7-cfr/273/10#input."
                "snap_allowable_monthly_dependent_care_expenses"
            ): dependent_care_deduction,
            (
                "us:regulations/7-cfr/273/10#input."
                "snap_allowable_monthly_child_support_payments"
            ): child_support_deduction,
        }
    return {
        "dependent_care_expense_necessary_for_work_or_training": (
            dependent_care_deduction > 0
        ),
        "dependent_care_expenses_paid": dependent_care_deduction,
        "dependent_care_reimbursed_or_paid_by_other_program": 0,
        "child_support_payment_verified": child_support_deduction > 0,
        "child_support_payment_history_months": (
            3 if child_support_deduction > 0 else 0
        ),
        "average_monthly_child_support_paid": child_support_deduction,
        "estimated_monthly_child_support_paid": child_support_deduction,
        "total_medical_expenses": medical_expenses_for_deduction(medical_deduction),
    }


def array(values: Any) -> np.ndarray:
    require_numpy()
    if hasattr(values, "to_numpy"):
        return values.to_numpy()
    if hasattr(values, "values"):
        return np.asarray(values.values)
    return np.asarray(values)


def require_numpy() -> None:
    if np is None:
        raise SystemExit(
            "numpy is required. Run with: "
            "uv run --with numpy --with "
            f"{populace_data_requirement('us')} axiom-encode "
            "snap-populace-compare"
        )


def calculate(sim: Any, name: str, period: str | int) -> np.ndarray:
    return array(sim.calculate(name, period=period))


def calculate_or_default(
    sim: Any, name: str, period: str | int, default: Any, size: int
) -> np.ndarray:
    try:
        return calculate(sim, name, period)
    except Exception:
        return np.full(size, default)


def any_by_id(ids: np.ndarray, values: np.ndarray) -> dict[int, bool]:
    result: dict[int, bool] = {}
    for raw_id, value in zip(ids, values, strict=False):
        key = int(raw_id)
        result[key] = bool(result.get(key, False) or bool(value))
    return result


def all_by_id(ids: np.ndarray, values: np.ndarray) -> dict[int, bool]:
    result: dict[int, bool] = {}
    seen: set[int] = set()
    for raw_id, value in zip(ids, values, strict=False):
        key = int(raw_id)
        if key not in seen:
            result[key] = True
            seen.add(key)
        result[key] = bool(result[key] and bool(value))
    return result


def build_state_map(
    sim: Any, year: int, spm_ids: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    person_spm = calculate(sim, "person_spm_unit_id", year)
    person_household = calculate(sim, "person_household_id", year)
    household_ids = calculate(sim, "household_id", year)
    household_states = calculate(sim, "state_code_str", year).astype(str)

    household_state_by_id = {
        int(household_id): state
        for household_id, state in zip(household_ids, household_states, strict=False)
    }
    spm_household_by_id: dict[int, int] = {}
    for spm_id, household_id in zip(person_spm, person_household, strict=False):
        spm_household_by_id.setdefault(int(spm_id), int(household_id))

    states = np.array(
        [
            household_state_by_id.get(spm_household_by_id.get(int(spm_id), -1), "")
            for spm_id in spm_ids
        ]
    )
    household_for_spm = np.array(
        [spm_household_by_id.get(int(spm_id), -1) for spm_id in spm_ids],
        dtype=np.int64,
    )
    return states, household_for_spm


def build_household_value_map(
    sim: Any,
    name: str,
    period: str | int,
    *,
    household_year: int,
    default: Any,
) -> dict[int, Any]:
    household_ids = calculate(sim, "household_id", household_year)
    values = calculate_or_default(sim, name, period, default, len(household_ids))
    return {
        int(household_id): native(value)
        for household_id, value in zip(household_ids, values, strict=False)
    }


def load_policyengine_cases(
    *,
    config: JurisdictionConfig,
    base_inputs: dict[str, Any],
    period: Period,
    state: str,
    sample_size: int | None,
    positive_snap_only: bool,
    utility_projection: str,
    populace_year: int,
    provenance: dict[str, Any] | None = None,
) -> list[ProjectedCase]:
    try:
        from policyengine_us import Microsimulation
    except ImportError as exc:
        raise SystemExit(
            "policyengine-us is required. Run with: "
            f"uv run --with {populace_data_requirement('us')} --with numpy axiom-encode "
            "snap-populace-compare"
        ) from exc

    print(f"Loading PolicyEngine Populace US {populace_year} dataset...")
    dataset = load_populace_dataset(
        "us",
        year=populace_year,
        command="snap-populace-compare",
        provenance=provenance,
    )
    sim = Microsimulation(dataset=dataset)

    period_label = period.label
    year = period.year
    spm_ids = calculate(sim, "spm_unit_id", year)
    spm_unit_size = calculate(sim, "spm_unit_size", year)
    snap_unit_size = calculate(sim, "snap_unit_size", period_label)
    states, household_ids = build_state_map(sim, year, spm_ids)
    utility_region_by_household_id = build_household_value_map(
        sim,
        "snap_utility_region_str",
        period_label,
        household_year=year,
        default="",
    )

    pe_snap = calculate(sim, PE_COMPARED_OUTPUT, period_label)
    state_mask = states == state
    valid_size_mask = snap_unit_size >= 1
    skipped_empty_units = int(np.count_nonzero(state_mask & ~valid_size_mask))
    mask = state_mask & valid_size_mask
    if positive_snap_only:
        mask &= pe_snap > 0

    indices = np.flatnonzero(mask)
    if sample_size is not None:
        indices = indices[:sample_size]

    print(f"Projecting {len(indices):,} {state} Populace SPM units...")
    if skipped_empty_units:
        print(
            f"Skipped {skipped_empty_units:,} {state} Populace SPM units "
            "with SNAP unit size < 1."
        )

    person_spm = calculate(sim, "person_spm_unit_id", year)
    student_ok_by_spm = any_by_id(
        person_spm,
        ~calculate(sim, "is_snap_ineligible_student", year).astype(bool),
    )
    immigration_ok_by_spm = any_by_id(
        person_spm,
        calculate(sim, "is_snap_immigration_status_eligible", period_label).astype(
            bool
        ),
    )
    all_members_receive_ssi_by_spm = all_by_id(
        person_spm,
        calculate(sim, "ssi", period_label) > 0,
    )

    values = {
        "spm_unit_size": spm_unit_size,
        "snap_unit_size": snap_unit_size,
        PE_COMPARED_OUTPUT: pe_snap,
        "snap": calculate(sim, "snap", period_label),
        "is_snap_eligible": calculate(sim, "is_snap_eligible", period_label),
        "snap_gross_income": calculate(sim, "snap_gross_income", period_label),
        "snap_earned_income": calculate(sim, "snap_earned_income", period_label),
        "snap_unearned_income": calculate(sim, "snap_unearned_income", period_label),
        "snap_net_income": calculate(sim, "snap_net_income", period_label),
        "snap_max_allotment": calculate(sim, "snap_max_allotment", period_label),
        "snap_min_allotment": calculate(sim, "snap_min_allotment", period_label),
        "snap_standard_deduction": calculate(
            sim, "snap_standard_deduction", period_label
        ),
        "snap_earned_income_deduction": calculate(
            sim, "snap_earned_income_deduction", period_label
        ),
        "snap_dependent_care_deduction": calculate(
            sim, "snap_dependent_care_deduction", period_label
        ),
        "snap_child_support_deduction": calculate(
            sim, "snap_child_support_deduction", period_label
        ),
        "snap_child_support_gross_income_deduction": calculate(
            sim, "snap_child_support_gross_income_deduction", period_label
        ),
        "snap_excess_medical_expense_deduction": calculate(
            sim, "snap_excess_medical_expense_deduction", period_label
        ),
        "snap_utility_allowance": calculate(
            sim, "snap_utility_allowance", period_label
        ),
        "snap_utility_allowance_type": calculate(
            sim, "snap_utility_allowance_type", period_label
        ),
        "snap_excess_shelter_expense_deduction": calculate(
            sim, "snap_excess_shelter_expense_deduction", period_label
        ),
        "housing_cost": calculate(sim, "housing_cost", period_label),
        "snap_assets": calculate(sim, "snap_assets", year),
        "has_usda_elderly_disabled": calculate(
            sim, "has_usda_elderly_disabled", period_label
        ),
        "meets_snap_categorical_eligibility": calculate(
            sim, "meets_snap_categorical_eligibility", period_label
        ),
        "meets_snap_work_requirements": calculate(
            sim, "meets_snap_work_requirements", period_label
        ),
        "heating_cooling_expense": calculate(sim, "heating_cooling_expense", year),
        "pre_subsidy_electricity_expense": calculate(
            sim, "pre_subsidy_electricity_expense", year
        ),
        "gas_expense": calculate(sim, "gas_expense", year),
        "phone_expense": calculate(sim, "phone_expense", year),
        "trash_expense": calculate(sim, "trash_expense", year),
        "water_expense": calculate(sim, "water_expense", year),
        "sewage_expense": calculate(sim, "sewage_expense", year),
    }

    household_input_ref_by_name = legal_input_index(base_inputs)
    member_input_ref_by_name = dict(AXIOM_MEMBER_INPUT_ID_BY_LABEL)

    cases: list[ProjectedCase] = []
    for idx in indices:
        spm_id = int(spm_ids[idx])
        utility_region = str(
            utility_region_by_household_id.get(int(household_ids[idx]), "")
        )
        utility_inputs = project_raw_utility_inputs(config, values, idx, utility_region)
        if utility_projection == "policyengine-type":
            utility_inputs = project_utility_allowance_type(
                config,
                str(native(values["snap_utility_allowance_type"][idx])),
                utility_region,
            )
        dependent_care_deduction = money(values["snap_dependent_care_deduction"][idx])
        child_support_deduction = projected_child_support_payment(values, idx)
        medical_deduction = money(values["snap_excess_medical_expense_deduction"][idx])

        inputs = dict(base_inputs)
        projected_inputs = {
            **project_income_resource_inputs(config, values, idx),
            "household_size": int(values["snap_unit_size"][idx]),
            "household_shelter_costs_incurred": money(values["housing_cost"][idx]),
            "household_lives_in_application_state": True,
            "household_in_project_area_solely_for_vacation": False,
            "household_contains_individual_participating_in_more_than_one_household_or_project_area": False,
            "resident_of_battered_women_and_children_shelter_and_prior_abusive_household_member": False,
            **project_deduction_inputs(
                config,
                dependent_care_deduction=dependent_care_deduction,
                child_support_deduction=child_support_deduction,
                medical_deduction=medical_deduction,
            ),
            **project_jurisdiction_household_inputs(config, values, idx),
            **utility_inputs,
        }
        for input_name, value in projected_inputs.items():
            set_input_value(inputs, input_name, value)
        set_input_value(
            inputs,
            "snap_claimed_homeless_shelter_deduction",
            0,
            required=False,
        )
        if config.jurisdiction == "us-ny":
            inputs[
                "us:regulations/7-cfr/273/10#input."
                "snap_claimed_homeless_shelter_deduction"
            ] = 0
        member_inputs = project_student_member_inputs(
            bool(student_ok_by_spm.get(spm_id, False))
        )
        member_inputs.update(
            project_citizenship_member_inputs(
                bool(immigration_ok_by_spm.get(spm_id, False))
            )
        )
        member_inputs.update(SSN_MEMBER_INPUT_DEFAULTS)
        member_inputs.update(
            project_work_member_inputs(
                bool(values["meets_snap_work_requirements"][idx])
            )
        )
        member_inputs.update(project_jurisdiction_member_inputs(config))
        if config.jurisdiction == "us-ny":
            member_inputs[
                "us-ny:regulations/18-nycrr/387/14/a/5#input."
                "member_receives_family_assistance_nonemergency_safety_net_or_ssi_benefits"
            ] = bool(all_members_receive_ssi_by_spm.get(spm_id, False))
        member_inputs["snap_member_is_elderly_or_disabled"] = bool(
            values["has_usda_elderly_disabled"][idx]
        )
        pe_outputs = {name: native(values[name][idx]) for name in values}
        pe_outputs["snap_utility_region_str"] = utility_region
        pe_outputs["all_members_receive_ssi"] = bool(
            all_members_receive_ssi_by_spm.get(spm_id, False)
        )
        cases.append(
            ProjectedCase(
                spm_unit_id=spm_id,
                household_id=int(household_ids[idx]),
                inputs=legalize_inputs(inputs, household_input_ref_by_name),
                member_inputs=[
                    legalize_inputs(
                        member_inputs,
                        member_input_ref_by_name,
                    )
                ],
                pe_outputs=pe_outputs,
            )
        )

    return cases


def project_jurisdiction_household_inputs(
    config: JurisdictionConfig,
    values: dict[str, np.ndarray],
    idx: int,
) -> dict[str, Any]:
    dependent_care_deduction = money(values["snap_dependent_care_deduction"][idx])
    if config.jurisdiction == "us-ny":
        return {
            "household_has_out_of_pocket_dependent_care_expenses": (
                dependent_care_deduction > 0
            ),
            "household_has_earned_income_budgeted_for_snap": (
                money(values["snap_earned_income"][idx]) > 0
            ),
            "household_member_disqualified_for_failure_to_comply_with_work_requirements": (
                not bool(values["meets_snap_work_requirements"][idx])
            ),
            "household_member_disqualified_for_failure_to_comply_with_periodic_reporting_requirements": False,
            "household_member_disqualified_for_intentional_program_violation": False,
            "household_member_ineligible_to_participate_in_snap": False,
        }
    if config.jurisdiction == "us-az":
        return {
            "na_net_income": money(values["snap_net_income"][idx]),
            "na_budgetary_unit_is_eligible": bool(values["is_snap_eligible"][idx]),
            "budgetary_unit_participant_count": int(values["snap_unit_size"][idx]),
            "thrifty_food_plan_amount_for_budgetary_unit_size": money(
                values["snap_max_allotment"][idx]
            ),
            "minimum_na_allotment": money(values["snap_min_allotment"][idx]),
            "initial_month_proration_applies": False,
            "prorated_initial_month_na_benefit": 0,
            "snap_excess_shelter_deduction_for_net_income": money(
                values["snap_excess_shelter_expense_deduction"][idx]
            ),
        }
    return {}


def project_jurisdiction_member_inputs(config: JurisdictionConfig) -> dict[str, Any]:
    if config.jurisdiction == "us-ny":
        base = "us-ny:regulations/18-nycrr/387/14/a/5#input."
        return {
            f"{base}member_receives_family_assistance_nonemergency_safety_net_or_ssi_benefits": False,
            f"{base}member_authorized_to_receive_family_assistance_nonemergency_safety_net_or_ssi_benefits_but_not_yet_paid": False,
            f"{base}member_family_assistance_nonemergency_safety_net_or_ssi_benefits_suspended_or_being_recouped": False,
            f"{base}member_determined_eligible_for_family_assistance_or_nonemergency_safety_net_benefits": False,
            f"{base}member_paid_family_assistance_or_nonemergency_safety_net_benefits": False,
            f"{base}member_family_assistance_or_nonemergency_safety_net_grant_amount": 0,
        }
    return {}


def projected_child_support_payment(values: dict[str, Any], idx: int) -> float:
    return money(values["snap_child_support_deduction"][idx]) + money(
        values["snap_child_support_gross_income_deduction"][idx]
    )


def project_raw_utility_inputs(
    config: JurisdictionConfig,
    values: dict[str, np.ndarray],
    idx: int,
    utility_region: str,
) -> dict[str, bool]:
    if config.jurisdiction == "us-ca":
        return {
            "household_has_heating_and_cooling_costs_separate_from_rent_or_mortgage": bool(
                values["heating_cooling_expense"][idx] > 0
            )
        }
    if config.jurisdiction == "us-ny":
        non_phone_utility = any(
            bool(values[name][idx] > 0)
            for name in (
                "pre_subsidy_electricity_expense",
                "water_expense",
                "sewage_expense",
                "trash_expense",
                "gas_expense",
            )
        )
        inputs = new_york_utility_region_inputs(utility_region)
        inputs.update(
            {
                "household_incurred_or_anticipated_heating_or_cooling_costs_separate_from_rent_or_mortgage": bool(
                    values["heating_cooling_expense"][idx] > 0
                ),
                "household_billed_separately_for_non_telephone_standard_utility": (
                    non_phone_utility
                ),
                "household_incurred_or_anticipated_basic_service_cost_for_one_telephone": bool(
                    values["phone_expense"][idx] > 0
                ),
            }
        )
        return inputs

    return {
        "household_incurred_or_anticipated_heating_or_cooling_costs_separate_from_rent_or_mortgage": bool(
            values["heating_cooling_expense"][idx] > 0
        ),
        "household_pays_electricity_utility_cost": bool(
            values["pre_subsidy_electricity_expense"][idx] > 0
        ),
        "household_pays_water_utility_cost": bool(values["water_expense"][idx] > 0),
        "household_pays_sewer_utility_cost": bool(values["sewage_expense"][idx] > 0),
        "household_pays_trash_utility_cost": bool(values["trash_expense"][idx] > 0),
        "household_pays_cooking_fuel_utility_cost": bool(
            values["gas_expense"][idx] > 0
        ),
        "household_pays_telephone_service_cost": bool(values["phone_expense"][idx] > 0),
    }


def project_utility_allowance_type(
    config: JurisdictionConfig, utility_type: str, utility_region: str
) -> dict[str, bool]:
    if config.jurisdiction == "us-ca":
        return {
            "household_has_heating_and_cooling_costs_separate_from_rent_or_mortgage": (
                utility_type == "SUA"
            )
        }
    if config.jurisdiction == "us-ny":
        inputs = new_york_utility_region_inputs(utility_region)
        if utility_type == "SUA":
            inputs[
                "household_incurred_or_anticipated_heating_or_cooling_costs_separate_from_rent_or_mortgage"
            ] = True
        elif utility_type in {"BUA", "LUA"}:
            inputs["household_billed_separately_for_non_telephone_standard_utility"] = (
                True
            )
        elif utility_type in {"TUA", "IUA"}:
            inputs[
                "household_incurred_or_anticipated_basic_service_cost_for_one_telephone"
            ] = True
        return inputs

    inputs = {
        "household_incurred_or_anticipated_heating_or_cooling_costs_separate_from_rent_or_mortgage": False,
        "household_pays_electricity_utility_cost": False,
        "household_pays_water_utility_cost": False,
        "household_pays_sewer_utility_cost": False,
        "household_pays_trash_utility_cost": False,
        "household_pays_cooking_fuel_utility_cost": False,
        "household_pays_telephone_service_cost": False,
    }
    if utility_type == "SUA":
        inputs[
            "household_incurred_or_anticipated_heating_or_cooling_costs_separate_from_rent_or_mortgage"
        ] = True
    elif utility_type == "LUA":
        inputs["household_pays_electricity_utility_cost"] = True
        inputs["household_pays_water_utility_cost"] = True
    elif utility_type == "IUA":
        inputs["household_pays_electricity_utility_cost"] = True
    return inputs


def new_york_utility_region_inputs(utility_region: str) -> dict[str, bool]:
    return {
        "household_incurred_or_anticipated_heating_or_cooling_costs_separate_from_rent_or_mortgage": False,
        "household_in_central_meter_housing_charged_only_for_excess_heating_or_cooling": False,
        "household_entitled_to_heap_or_liheaa_payment": False,
        "household_resides_in_new_york_city": utility_region == "NY_NYC",
        "household_resides_in_nassau_or_suffolk_county": utility_region == "NY_NAS",
        "household_billed_separately_for_non_telephone_standard_utility": False,
        "household_incurred_or_anticipated_basic_service_cost_for_one_telephone": False,
    }


def medical_expenses_for_deduction(deduction: float) -> float:
    if deduction <= 0:
        return 0
    return deduction + 35


def money(value: Any) -> float:
    value = float(value)
    if not math.isfinite(value):
        return 0.0
    return round(value, 6)


def native(value: Any) -> Any:
    if np is not None and isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float):
        return money(value)
    return value


def scalar_value(value: Any) -> dict[str, Any]:
    value = native(value)
    if isinstance(value, bool):
        return {"kind": "bool", "value": value}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"kind": "integer", "value": value}
    if isinstance(value, float):
        return {"kind": "decimal", "value": decimal_literal(value)}
    if isinstance(value, str):
        if len(value) == 10 and value[4] == "-" and value[7] == "-":
            return {"kind": "date", "value": value}
        return {"kind": "text", "value": value}
    raise TypeError(f"unsupported input value {value!r}")


def decimal_literal(value: float) -> str:
    literal = f"{value:.6f}".rstrip("0").rstrip(".")
    return literal or "0"


def compile_program(
    binary: Path,
    program: Path,
    output: Path,
    *,
    env: dict[str, str],
    workspace_root: Path | None = None,
) -> None:
    # Post-hard-cut engines take explicit --rulespec-root flags naming
    # canonical rulespec-<cc> checkouts (staged pure: jurisdiction dirs only)
    # and compile the composition via compile-composed; older engines reject
    # both and fall back to the legacy env-resolved `compile` inside
    # compile_with_engine (#296).
    from axiom_oracles.engine_compat import (
        compile_with_engine,
        explicit_engine_roots,
        import_prefixes,
        stage_pure_root,
    )

    program_doc: dict = {}
    try:
        program_doc = yaml.safe_load(Path(program).read_text()) or {}
    except (OSError, yaml.YAMLError):
        program_doc = {}
    composed = (
        isinstance(program_doc, dict)
        and (program_doc.get("module") or {}).get("kind") == "composition"
    )
    candidates: list[Path | str] = []
    if workspace_root is not None:
        candidates.append(workspace_root)
    roots = explicit_engine_roots(candidates, program=program)
    jurisdictions = import_prefixes(
        [e for e in (program_doc.get("imports") or []) if isinstance(e, str)]
        if isinstance(program_doc, dict)
        else []
    )
    staged_roots: list[Path] = []
    if roots and jurisdictions:
        with_stage = tempfile.mkdtemp(prefix="snap-populace-roots-")
        staged_roots = [
            stage_pure_root(root, jurisdictions, Path(with_stage)) for root in roots
        ]
    compile_with_engine(
        binary,
        Path(program),
        Path(output),
        roots=staged_roots or roots,
        composed=composed,
        env=env,
    )


def run_axiom_cases(
    *,
    binary: Path,
    artifact: Path,
    cases: list[ProjectedCase],
    period: Period,
    output_ids: list[str],
    relation_id: str,
    additional_relation_ids: tuple[str, ...],
    member_entity_type: str,
    env: dict[str, str],
) -> list[dict[str, Any]]:
    interval = {
        "start": period.start.isoformat(),
        "end": period.end.isoformat(),
    }
    period_json = {
        "period_kind": "month",
        "start": period.start.isoformat(),
        "end": period.end.isoformat(),
        "name": period.label,
    }
    inputs = []
    relations = []
    queries = []
    for case in cases:
        entity_id = f"spm-{case.spm_unit_id}"
        for name, value in case.inputs.items():
            inputs.append(
                {
                    "name": name,
                    "entity": "Household",
                    "entity_id": entity_id,
                    "interval": interval,
                    "value": scalar_value(value),
                }
            )
        for member_index, member_inputs in enumerate(case.member_inputs, 1):
            member_entity_id = f"{entity_id}-member-{member_index}"
            for current_relation_id in (relation_id, *additional_relation_ids):
                relations.append(
                    {
                        "name": current_relation_id,
                        "tuple": [member_entity_id, entity_id],
                        "interval": interval,
                    }
                )
            for name, value in member_inputs.items():
                inputs.append(
                    {
                        "name": name,
                        "entity": member_entity_type,
                        "entity_id": member_entity_id,
                        "interval": interval,
                        "value": scalar_value(value),
                    }
                )
        queries.append(
            {
                "entity_id": entity_id,
                "period": period_json,
                "outputs": output_ids,
            }
        )

    request = {
        "mode": "fast",
        "dataset": {"inputs": inputs, "relations": relations},
        "queries": queries,
    }
    result = subprocess.run(
        [str(binary), "run-compiled", "--artifact", str(artifact)],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    payload = json.loads(result.stdout)
    return payload["results"]


def output_to_python(output: dict[str, Any]) -> Any:
    if output.get("kind") == "judgment":
        return output.get("outcome")
    value = output.get("value", {})
    raw = value.get("value")
    if value.get("kind") == "decimal":
        return float(raw)
    return raw


def outputs_by_reference(outputs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    references: dict[str, dict[str, Any]] = {}
    for output_key, output in outputs.items():
        if not isinstance(output, dict):
            continue
        references[str(output_key)] = output
        output_id = str(output.get("id") or "").strip()
        if output_id:
            references[output_id] = output
    return references


def compare(
    cases: list[ProjectedCase],
    results: list[dict[str, Any]],
    tolerance: float,
    *,
    output_id_by_label: dict[str, str],
    utility_allowance_labels: tuple[str, ...],
):
    rows = []
    for case, result in zip(cases, results, strict=True):
        raw_outputs = result.get("outputs", {})
        if not isinstance(raw_outputs, dict):
            raise ValueError(
                f"Axiom result for SPM unit {case.spm_unit_id} has no outputs"
            )
        output_references = outputs_by_reference(raw_outputs)
        missing_outputs = sorted(
            output_id
            for output_id in output_id_by_label.values()
            if output_id not in output_references
        )
        if missing_outputs:
            joined = ", ".join(missing_outputs)
            raise ValueError(
                f"Axiom result for SPM unit {case.spm_unit_id} is missing {joined}"
            )
        outputs = {
            label: output_to_python(output_references[output_id])
            for label, output_id in output_id_by_label.items()
        }
        axiom_snap = float(outputs[COMPARED_AXIOM_OUTPUT])
        pe_snap = float(case.pe_outputs[PE_COMPARED_OUTPUT])
        diff = axiom_snap - pe_snap
        row = {
            "spm_unit_id": case.spm_unit_id,
            "household_id": case.household_id,
            "pe_snap": pe_snap,
            "axiom_snap_allotment": axiom_snap,
            "difference": diff,
            "absolute_difference": abs(diff),
            "match": abs(diff) <= tolerance,
            "pe_snap_eligible": bool(case.pe_outputs["is_snap_eligible"]),
            "axiom_snap_eligible": outputs["snap_eligible"],
            "pe_gross_income": case.pe_outputs["snap_gross_income"],
            "axiom_gross_income": outputs["snap_gross_monthly_income"],
            "pe_net_income": case.pe_outputs["snap_net_income"],
            "axiom_net_income": outputs["snap_net_income"],
            "pe_net_income_before_shelter": (
                float(case.pe_outputs["snap_net_income"])
                + float(case.pe_outputs["snap_excess_shelter_expense_deduction"])
            ),
            "pe_standard_deduction": case.pe_outputs["snap_standard_deduction"],
            "pe_earned_income_deduction": case.pe_outputs[
                "snap_earned_income_deduction"
            ],
            "pe_dependent_care_deduction": case.pe_outputs[
                "snap_dependent_care_deduction"
            ],
            "pe_child_support_deduction": projected_child_support_payment(
                {
                    "snap_child_support_deduction": [
                        case.pe_outputs["snap_child_support_deduction"]
                    ],
                    "snap_child_support_gross_income_deduction": [
                        case.pe_outputs["snap_child_support_gross_income_deduction"]
                    ],
                },
                0,
            ),
            "pe_medical_deduction": case.pe_outputs[
                "snap_excess_medical_expense_deduction"
            ],
            "pe_max_allotment": case.pe_outputs["snap_max_allotment"],
            "axiom_max_allotment": outputs["snap_maximum_allotment"],
            "pe_utility_allowance": case.pe_outputs["snap_utility_allowance"],
            "axiom_utility_allowance": sum(
                float(outputs[name]) for name in utility_allowance_labels
            ),
            "pe_housing_cost": case.pe_outputs["housing_cost"],
            "pe_has_usda_elderly_disabled": case.pe_outputs[
                "has_usda_elderly_disabled"
            ],
            "pe_meets_snap_categorical_eligibility": case.pe_outputs[
                "meets_snap_categorical_eligibility"
            ],
            "pe_snap_utility_allowance_type": case.pe_outputs[
                "snap_utility_allowance_type"
            ],
            "pe_shelter_deduction": case.pe_outputs[
                "snap_excess_shelter_expense_deduction"
            ],
            "axiom_shelter_deduction": outputs["snap_excess_shelter_deduction"],
        }
        for label, value in outputs.items():
            key = f"axiom_{label}"
            if key not in row:
                row[key] = value
        rows.append(row)
    return rows


def add_snapscreener_results(
    rows: list[dict[str, Any]],
    payloads: list[dict[str, Any]],
    results: list[dict[str, Any]],
    tolerance: float,
) -> None:
    for row, payload, result in zip(rows, payloads, results, strict=True):
        row["snapscreener_state_key"] = payload["state_or_territory"]
        row["snapscreener_status"] = result.get("status")
        errors = result.get("errors") or []
        row["snapscreener_error"] = "; ".join(str(error) for error in errors)
        row["snapscreener_comparable"] = primary_oracles_find_eligible(row)
        if result.get("status") != "OK":
            row["snapscreener_snap"] = None
            row["snapscreener_eligible"] = None
            row["axiom_snapscreener_difference"] = None
            row["pe_snapscreener_difference"] = None
            row["axiom_snapscreener_match"] = False
            row["pe_snapscreener_match"] = False
            continue
        snapscreener_snap = float(result.get("estimated_monthly_benefit") or 0)
        axiom_difference = row["axiom_snap_allotment"] - snapscreener_snap
        pe_difference = row["pe_snap"] - snapscreener_snap
        row["snapscreener_snap"] = snapscreener_snap
        row["snapscreener_eligible"] = bool(result.get("estimated_eligibility"))
        row["axiom_snapscreener_difference"] = axiom_difference
        row["pe_snapscreener_difference"] = pe_difference
        row["axiom_snapscreener_match"] = abs(axiom_difference) <= tolerance
        row["pe_snapscreener_match"] = abs(pe_difference) <= tolerance


def primary_oracles_find_eligible(row: dict[str, Any]) -> bool:
    return bool(row["pe_snap_eligible"]) or row["axiom_snap_eligible"] == "holds"


def print_summary(
    rows: list[dict[str, Any]], tolerance: float, max_differences: int
) -> None:
    total = len(rows)
    matches = sum(1 for row in rows if row["match"])
    diffs = sorted(rows, key=lambda row: row["absolute_difference"], reverse=True)
    mean_abs = sum(row["absolute_difference"] for row in rows) / total if total else 0.0
    print()
    print(f"Compared {total:,} PolicyEngine Populace SPM units")
    print(f"Tolerance: ${tolerance:,.2f}")
    print(
        f"Matches: {matches:,}/{total:,} ({matches / total:.1%})"
        if total
        else "No rows"
    )
    print(f"Mean absolute difference: ${mean_abs:,.2f}")
    if diffs:
        print(f"Max absolute difference: ${diffs[0]['absolute_difference']:,.2f}")
    print()
    print(f"Top {min(max_differences, len(diffs))} differences:")
    for row in diffs[:max_differences]:
        print(
            "  "
            f"spm={row['spm_unit_id']} "
            f"PE=${row['pe_snap']:.2f} Axiom=${row['axiom_snap_allotment']:.2f} "
            f"diff=${row['difference']:.2f} "
            f"eligible PE={row['pe_snap_eligible']} Axiom={row['axiom_snap_eligible']} "
            f"gross PE=${row['pe_gross_income']:.2f} Axiom=${row['axiom_gross_income']:.2f} "
            f"net PE=${row['pe_net_income']:.2f} Axiom=${row['axiom_net_income']:.2f} "
            f"utility PE=${row['pe_utility_allowance']:.2f} Axiom=${row['axiom_utility_allowance']:.2f}"
        )


def print_snapscreener_summary(
    rows: list[dict[str, Any]], tolerance: float, max_differences: int
) -> None:
    if not rows or "snapscreener_status" not in rows[0]:
        return
    valid_rows = [row for row in rows if row["snapscreener_status"] == "OK"]
    comparable_rows = [row for row in valid_rows if row["snapscreener_comparable"]]
    noncomparable_positive = [
        row
        for row in valid_rows
        if not row["snapscreener_comparable"] and row["snapscreener_snap"] > 0
    ]
    disagreement_rows = [
        row
        for row in comparable_rows
        if bool(row["pe_snap_eligible"]) != (row["axiom_snap_eligible"] == "holds")
    ]
    axiom_matches = sum(1 for row in comparable_rows if row["axiom_snapscreener_match"])
    pe_matches = sum(1 for row in comparable_rows if row["pe_snapscreener_match"])
    disagreement_axiom_matches = sum(
        1 for row in disagreement_rows if row["axiom_snapscreener_match"]
    )
    disagreement_pe_matches = sum(
        1 for row in disagreement_rows if row["pe_snapscreener_match"]
    )
    print()
    print("SnapScreener diagnostic oracle")
    print(f"Rows: {len(valid_rows):,}/{len(rows):,} OK")
    print(
        f"Comparable rows: {len(comparable_rows):,} "
        "(PolicyEngine or Axiom marks SNAP eligible)"
    )
    if noncomparable_positive:
        print(
            f"Excluded {len(noncomparable_positive):,} row(s) where PE and Axiom "
            "both mark ineligible but SnapScreener estimates a positive benefit."
        )
    print(f"Tolerance: ${tolerance:,.2f}")
    if comparable_rows:
        print(
            f"Axiom matches SnapScreener: "
            f"{axiom_matches:,}/{len(comparable_rows):,} "
            f"({axiom_matches / len(comparable_rows):.1%})"
        )
        print(
            f"PolicyEngine matches SnapScreener: "
            f"{pe_matches:,}/{len(comparable_rows):,} "
            f"({pe_matches / len(comparable_rows):.1%})"
        )
    if disagreement_rows:
        print(
            f"On PE/Axiom eligibility disagreements: "
            f"Axiom {disagreement_axiom_matches:,}/{len(disagreement_rows):,}, "
            f"PolicyEngine {disagreement_pe_matches:,}/{len(disagreement_rows):,} "
            "match SnapScreener."
        )
    diffs = sorted(
        comparable_rows,
        key=lambda row: abs(row["axiom_snapscreener_difference"]),
        reverse=True,
    )
    print(f"Top {min(max_differences, len(diffs))} Axiom/SnapScreener differences:")
    for row in diffs[:max_differences]:
        print(
            "  "
            f"spm={row['spm_unit_id']} state={row['snapscreener_state_key']} "
            f"SnapScreener=${row['snapscreener_snap']:.2f} "
            f"Axiom=${row['axiom_snap_allotment']:.2f} "
            f"PE=${row['pe_snap']:.2f} "
            f"AxiomDiff=${row['axiom_snapscreener_difference']:.2f} "
            f"PEDiff=${row['pe_snapscreener_difference']:.2f}"
        )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main(args: argparse.Namespace | None = None) -> int:
    if args is None:
        args = parse_args()
    config = JURISDICTION_CONFIGS[args.jurisdiction]
    workspace_root = resolve_workspace_root(args.workspace_root)
    program = resolve_program_path(config, workspace_root, args.program)
    test_template = resolve_test_template_path(program, args.test_template)
    axiom_binary = resolve_axiom_binary(workspace_root, args.axiom_binary)
    state = (args.state or config.state_code).upper()
    env = axiom_rules_env(program, workspace_root)
    period = month_period(args.year, args.month)
    base_inputs = load_base_inputs(test_template)
    print(f"Jurisdiction: {config.jurisdiction}")
    print(f"Program: {program}")
    print(f"Utility projection: {args.utility_projection}")
    dataset_identity: dict[str, Any] = {}
    cases = load_policyengine_cases(
        config=config,
        base_inputs=base_inputs,
        period=period,
        state=state,
        sample_size=args.sample_size,
        positive_snap_only=args.positive_snap_only,
        utility_projection=args.utility_projection,
        populace_year=args.populace_year,
        provenance=dataset_identity,
    )
    identity_line = format_dataset_identity(dataset_identity)
    if identity_line:
        print(identity_line)
    if not cases:
        print("No matching Populace SPM units.")
        return 1

    with tempfile.TemporaryDirectory(prefix=config.temp_prefix) as temp_dir:
        artifact = Path(temp_dir) / "program.compiled.json"
        print(f"Compiling {config.display_name} RuleSpec composition...")
        compile_program(
            axiom_binary, program, artifact, env=env, workspace_root=workspace_root
        )
        print("Running the Axiom rules engine over projected Populace records...")
        results = run_axiom_cases(
            binary=axiom_binary,
            artifact=artifact,
            cases=cases,
            period=period,
            output_ids=list(config.output_id_by_label.values()),
            relation_id=config.relation_id,
            additional_relation_ids=config.additional_relation_ids,
            member_entity_type=config.member_entity_type,
            env=env,
        )

    rows = compare(
        cases,
        results,
        args.tolerance,
        output_id_by_label=config.output_id_by_label,
        utility_allowance_labels=config.utility_allowance_labels,
    )
    if "snapscreener" in args.external_oracle:
        bundle = snapscreener.ensure_api_js(
            api_js=args.snapscreener_api_js,
            cache_dir=args.snapscreener_cache_dir,
        )
        print(
            "Running SnapScreener diagnostic oracle "
            f"({bundle.url}, sha256={bundle.sha256})..."
        )
        snapscreener_payloads = snapscreener.project_payloads(cases, state=state)
        snapscreener_results = snapscreener.run_payloads(
            snapscreener_payloads,
            api_js=bundle.path,
        )
        add_snapscreener_results(
            rows,
            snapscreener_payloads,
            snapscreener_results,
            args.tolerance,
        )
    print_summary(rows, args.tolerance, args.max_differences)
    print_snapscreener_summary(rows, args.tolerance, args.max_differences)
    if args.write_csv is not None:
        write_csv(args.write_csv, rows)
        print(f"Wrote {args.write_csv}")
        if dataset_identity:
            identity_path = args.write_csv.with_suffix(
                args.write_csv.suffix + ".dataset_identity.json"
            )
            identity_path.write_text(
                json.dumps(dataset_identity, indent=2, sort_keys=True)
            )
            print(f"Wrote {identity_path}")

    match_rate = sum(1 for row in rows if row["match"]) / len(rows) if rows else 0
    if args.min_match_rate is not None and match_rate < args.min_match_rate:
        print(
            f"Match rate {match_rate:.1%} is below required {args.min_match_rate:.1%}"
        )
        return 1
    if args.fail_on_mismatch and not all(row["match"] for row in rows):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
