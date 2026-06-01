"""Project thin Axiom Cases into Colorado SNAP RuleSpec input records.

Colorado SNAP FY 2026 (rules-us-co/policies/cdhs/snap/fy-2026-benefit-calculation.yaml)
declares >340 fully-namespaced ``#input.X`` slots across federal SNAP statutes,
USDA policies, 7-CFR regulations, and the 10-CCR-2506-1 Colorado SNAP manual.
This module ships a baseline drawn from the upstream test fixture and lets a
Case override the small set of facts the ECPS population actually carries
(household size, member ages, citizenship, earned income).

Use ``attach_axiom_snap_co_inputs(cases)`` from the CLI when a SNAP comparison
is requested and the cases scope to Colorado. The runner picks the input
records up via ``case.metadata[AXIOM_INPUT_RECORDS_METADATA_KEY]``.
"""
from __future__ import annotations

import json
from dataclasses import replace
from functools import cache
from pathlib import Path
from typing import Any

from ...core.case import Case, Concepts, Entity
from ._snap_co_base_inputs import BASE_INPUTS, BASE_MEMBER
from .runner import (
    AXIOM_INPUT_RECORDS_METADATA_KEY,
    AXIOM_RELATIONS_METADATA_KEY,
)


_SNAP_HOUSEHOLD_ID = "household"
_SNAP_HOUSEHOLD_ENTITY = "Household"
_MEMBER_RELATION = "us:statutes/7/2012/j#relation.member_of_household"
_MEMBER_RELATION_RUNTIME = "member_of_household"
_WAGES_INPUT = "us-co:regulations/10-ccr-2506-1/4.403#input.employee_wages_received"
_HOUSEHOLD_SIZE_INPUT = (
    "us-co:regulations/10-ccr-2506-1/4.207.3#input.household_size"
)
_FEDERAL_NET_INCOME_DEFAULTS = {
    "us:policies/usda/snap/fy-2026-cola/deductions#input.household_size": None,
    "us:regulations/7-cfr/273/10#input.household_size": None,
}
_FEDERAL_MEMBER_DEFAULTS = {
    "us:regulations/7-cfr/273/6#input.member_refused_or_failed_to_provide_or_apply_for_ssn": False,
    "us:regulations/7-cfr/273/6#input.member_has_documentary_or_collateral_evidence_of_ssn_application_or_every_effort": False,
    "us:regulations/7-cfr/273/6#input.state_agency_fault_in_ssn_application_processing": False,
    "us:regulations/7-cfr/273/6#input.member_unable_to_obtain_documents_required_for_ssn_application_with_caseworker_assistance_needed": False,
    "us:regulations/7-cfr/273/6#input.member_ssn_application_filed_pending_state_agency_notification": False,
    "us:regulations/7-cfr/273/6#input.member_later_provided_ssn_ending_disqualification": False,
    "us:regulations/7-cfr/273/7#input.member_age_16_or_17_is_not_household_head_or_attends_school_or_training_half_time": False,
    "us:regulations/7-cfr/273/7#input.member_physically_or_mentally_unfit_for_employment": None,
    "us:regulations/7-cfr/273/7#input.member_subject_to_and_complying_with_title_iv_work_requirement": False,
    "us:regulations/7-cfr/273/7#input.member_responsible_for_dependent_child_under_six_or_incapacitated_person": False,
    "us:regulations/7-cfr/273/7#input.member_receiving_or_applying_for_unemployment_compensation_and_complying": False,
    "us:regulations/7-cfr/273/7#input.member_regular_participant_in_drug_or_alcohol_treatment": False,
    "us:regulations/7-cfr/273/7#input.member_weekly_work_hours": None,
    "us:regulations/7-cfr/273/7#input.member_weekly_wages": None,
    "us:regulations/7-cfr/273/7#input.federal_or_state_minimum_wage": 15,
    "us:regulations/7-cfr/273/7#input.migrant_or_seasonal_farmworker_under_contract_to_begin_employment_within_30_days": False,
    "us:regulations/7-cfr/273/7#input.alaska_subsistence_hunts_or_fishes_30_hours_weekly": False,
    "us:regulations/7-cfr/273/7#input.member_student_enrolled_at_least_half_time_and_student_eligible": False,
    "us:regulations/7-cfr/273/7#input.member_registered_for_work_or_registered_by_state": True,
    "us:regulations/7-cfr/273/7#input.member_participated_in_snap_et_if_assigned": True,
    "us:regulations/7-cfr/273/7#input.member_participated_in_workfare_if_assigned": True,
    "us:regulations/7-cfr/273/7#input.member_provided_employment_status_or_availability_information": True,
    "us:regulations/7-cfr/273/7#input.member_reported_to_referred_suitable_employer_if_referred": True,
    "us:regulations/7-cfr/273/7#input.member_accepted_bona_fide_suitable_employment_offer_if_offered": True,
    "us:regulations/7-cfr/273/7#input.member_voluntarily_quit_or_reduced_work_below_30_hours_without_good_cause": False,
    "us:regulations/7-cfr/273/7#input.member_snap_work_requirements_waived_due_to_pending_ssi_joint_application": False,
    "us:regulations/7-cfr/273/24#input.member_medically_certified_physically_or_mentally_unfit_for_employment": None,
    "us:regulations/7-cfr/273/24#input.member_is_parent_of_household_member_under_age_eighteen": False,
    "us:regulations/7-cfr/273/24#input.member_resides_with_household_member_under_age_eighteen": False,
    "us:regulations/7-cfr/273/24#input.member_is_pregnant": None,
    "us:regulations/7-cfr/273/24#input.member_is_homeless": False,
    "us:regulations/7-cfr/273/24#input.member_is_veteran": None,
    "us:regulations/7-cfr/273/24#input.member_age_24_or_younger_and_was_in_foster_care_on_attaining_age_18": False,
    "us:regulations/7-cfr/273/24#input.member_covered_by_abawd_time_limit_waiver": False,
    "us:regulations/7-cfr/273/24#input.member_abawd_weekly_work_hours": None,
    "us:regulations/7-cfr/273/24#input.member_abawd_monthly_work_hours": None,
    "us:regulations/7-cfr/273/24#input.member_participates_in_abawd_work_program_20_hours_weekly": False,
    "us:regulations/7-cfr/273/24#input.member_combines_work_and_work_program_20_hours_weekly": False,
    "us:regulations/7-cfr/273/24#input.member_participates_in_abawd_workfare_program": False,
    "us:regulations/7-cfr/273/24#input.snap_abawd_countable_months_in_three_year_period": 0,
    "us:regulations/7-cfr/273/24#input.member_regained_abawd_eligibility": False,
    "us:regulations/7-cfr/273/24#input.member_has_additional_three_month_abawd_eligibility": False,
}

US_SNAP_CO_PROGRAM_PATH = (
    "policies/cdhs/snap/fy-2026-benefit-calculation.yaml"
)

# Precompiled artifact shipped alongside this projection. Bundling the
# artifact lets axiom-oracles use `axiom-rules-engine run-compiled` and
# avoid recompiling the CO SNAP YAML on every case — which would also
# require an engine binary that supports `kind: reiteration`.
US_SNAP_CO_COMPILED_ARTIFACT_PATH = (
    Path(__file__).parent / "artifacts" / "co-snap.compiled.json"
)


@cache
def _compiled_reference_targets() -> frozenset[str]:
    artifact = json.loads(US_SNAP_CO_COMPILED_ARTIFACT_PATH.read_text())
    program = artifact.get("program") if isinstance(artifact, dict) else {}
    if not isinstance(program, dict):
        return frozenset()
    targets: set[str] = set()
    for collection in ("derived", "parameters"):
        for item in program.get(collection, []):
            if not isinstance(item, dict):
                continue
            item_id = item.get("id")
            if isinstance(item_id, str) and "#" in item_id:
                targets.add(item_id.split("#", 1)[0])
    return frozenset(targets)


def _supported_input_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reference_targets = _compiled_reference_targets()
    if not reference_targets:
        return records
    supported = []
    for record in records:
        name = str(record.get("name"))
        if "#" not in name:
            supported.append(record)
            continue
        if name.split("#", 1)[0] in reference_targets:
            supported.append(record)
    return supported


def attach_axiom_snap_co_inputs(cases: list[Case]) -> list[Case]:
    """Attach Axiom CO SNAP input records to cases that lack them."""
    projected = []
    for case in cases:
        metadata = dict(case.metadata)
        if metadata.get(AXIOM_INPUT_RECORDS_METADATA_KEY):
            projected.append(case)
            continue

        people = _people(case)
        household_size = max(len(people), 1)

        # Tax-unit/household level inputs: start from the test-fixture
        # baseline, then override the few fields the Case carries.
        monthly_income = _monthly_income(people)
        inputs = dict(BASE_INPUTS)
        inputs[_HOUSEHOLD_SIZE_INPUT] = household_size
        inputs[_WAGES_INPUT] = monthly_income
        for input_name, default in _FEDERAL_NET_INCOME_DEFAULTS.items():
            if default is None:
                value = monthly_income if "income" in input_name else household_size
            else:
                value = default
            inputs[input_name] = value

        records = [
            _input_record(name, _SNAP_HOUSEHOLD_ENTITY, _SNAP_HOUSEHOLD_ID, value)
            for name, value in inputs.items()
        ]

        # Member relation: one entry per person, with age and citizenship
        # carried from the Case.
        member_records = []
        relation_tuples = []
        for index, person in enumerate(people):
            person_id = f"snap-member-{index}"
            relation_tuples.append([person_id, _SNAP_HOUSEHOLD_ID])
            for input_name, default in BASE_MEMBER.items():
                value = _member_value(input_name, person, default)
                member_records.append(
                    _input_record(input_name, "Person", person_id, value)
                )
            for input_name, default in _FEDERAL_MEMBER_DEFAULTS.items():
                member_records.append(
                    _input_record(
                        input_name,
                        "Person",
                        person_id,
                        _member_value(input_name, person, default),
                    )
                )

        metadata[AXIOM_INPUT_RECORDS_METADATA_KEY] = _supported_input_records(
            records + member_records
        )
        metadata[AXIOM_RELATIONS_METADATA_KEY] = [
            *metadata.get(AXIOM_RELATIONS_METADATA_KEY, []),
            *[
                {"name": relation_name, "tuple": tup}
                for tup in relation_tuples
                for relation_name in (_MEMBER_RELATION, _MEMBER_RELATION_RUNTIME)
            ],
        ]
        # Output entity for SNAP outputs is the Household, not the default
        # TaxUnit used by the federal-income-tax projection.
        metadata["axiom_entity_id"] = _SNAP_HOUSEHOLD_ID
        metadata["axiom_entity"] = _SNAP_HOUSEHOLD_ENTITY

        projected.append(replace(case, metadata=metadata))
    return projected


def _people(case: Case) -> list[Entity]:
    return [
        entity
        for entity in case.entities
        if str(entity.kind).lower().replace("_", "-") == "person"
    ]


def _monthly_income(people: list[Entity]) -> float:
    """CO SNAP wage input is the household's anticipated monthly wages."""
    annual = sum(
        _number(person.fact(Concepts.YEARLY_EARNED_INCOME, 0)) for person in people
    )
    return round(annual / 12, 2)


def _member_value(input_name: str, person: Entity, default: Any) -> Any:
    if input_name.endswith("#input.member_age"):
        age = person.fact(Concepts.PERSON_AGE)
        if age is not None:
            return int(age)
    if "snap_member_is_elderly_or_disabled" in input_name:
        age = _number(person.fact(Concepts.PERSON_AGE, 0))
        disabled = bool(person.fact(Concepts.DISABLED, False))
        return age >= 60 or disabled
    if "physically_or_mentally_unfit_for_employment" in input_name:
        return bool(person.fact(Concepts.DISABLED, False))
    if input_name.endswith("#input.member_is_pregnant"):
        return bool(person.fact(Concepts.PREGNANT, False))
    if input_name.endswith("#input.member_is_veteran"):
        return bool(person.fact(Concepts.VETERAN, False))
    if input_name.endswith("#input.member_weekly_work_hours"):
        return 30 if _number(person.fact(Concepts.YEARLY_EARNED_INCOME, 0)) else 0
    if input_name.endswith("#input.member_weekly_wages"):
        return round(_number(person.fact(Concepts.YEARLY_EARNED_INCOME, 0)) / 52, 2)
    if input_name.endswith("#input.member_abawd_weekly_work_hours"):
        return 20 if _number(person.fact(Concepts.YEARLY_EARNED_INCOME, 0)) else 0
    if input_name.endswith("#input.member_abawd_monthly_work_hours"):
        return 80 if _number(person.fact(Concepts.YEARLY_EARNED_INCOME, 0)) else 0
    if "enrolled_at_least_half_time" in input_name:
        return False
    if "member_is_us_citizen" in input_name:
        return True
    return default


def _input_record(name: str, entity: str, entity_id: str, value: Any) -> dict:
    return {
        "name": name,
        "entity": entity,
        "entity_id": entity_id,
        "value": value,
    }


def _number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    return float(value)
