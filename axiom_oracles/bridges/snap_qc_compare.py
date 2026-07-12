"""Validate state SNAP RuleSpec output against the SNAP QC administrative file.

The USDA SNAP Quality Control (QC) public-use file is a monthly sample of
active-case reviews. Each record carries the case's reported benefit
(``RAWBEN``) and, more usefully as ground truth, ``FSBEN`` — the benefit that
FNS/Mathematica *reconstruct* from the edited case inputs and the official
fiscal-year parameters via the QC Minimodel. Because that reconstruction is a
faithful re-run of the statutory benefit computation over clean inputs, it is a
per-case oracle for a benefit engine: project the QC unit's income, size,
shelter, utilities, deductions, and resources onto the RuleSpec composition's
input surface, run the engine, and compare the regular monthly allotment and
its intermediate stages against the QC constructed values.

This oracle validates the *benefit computation*, not eligibility screening. The
public file already contains only complete, eligible, internally consistent
reviews, so work-registration, student, SSN, and citizenship member facts stay
at the composition test template's passing defaults; the replay exercises the
income -> deduction -> net-income -> allotment arithmetic, which is what the QC
constructed intermediates let us check stage by stage.

The FY 2024 evaluation runs through a compile-time overlay
(:mod:`axiom_oracles.bridges.rulespec_overlay`) because the rulespec-us monorepo
wires each state composition to the FY 2026 COLA parameter set. The overlay
rewrites the cola module ids to ``fy-2024-cola`` and patches the state's
standard-utility-allowance amounts, then the engine runs at the nominal period
``2026-01``: the chain module versions are snapshot-dated to their 2025-10-01
effective dates, so a true-FY-2024 period cannot select them today. Once
TheAxiomFoundation/rulespec-us#759 inverts parameter selection to be
period-driven, the overlay and the nominal period both retire.

Jurisdictions
-------------
Each :data:`QC_JURISDICTIONS` entry wraps a ``snap_populace``
``JurisdictionConfig`` (composition, output ids, relations) with the QC
specifics: the fiscal-year overlay, the QC ``STATE`` FIPS code, how the
overlay's SUA patch rules map to QC utility tiers (and, for New York, to the
regional schedules), and the state's child-support election:

* ``us-co`` — Colorado elects the 7 USC 2014(e)(4) child-support *exclusion*
  (netted out of the compared gross income); unearned income is itemized into
  the 10 CCR 2506-1 section 4.404 categories; four statewide SUA tiers.
* ``us-ny`` — child support is a *deduction* (fed through the federal
  273.10/2014(e)(6) inputs); three SUA tiers on three regional schedules
  (New York City, Nassau/Suffolk, rest of state) — the public file carries no
  sub-state geography, so the mapper infers the region from the QC-applied
  ``UTIL`` amount, which is authoritative over ``SUA1`` (§7 of the playbook);
  every in-scope FY 2024 row is categorically eligible, projected through the
  18 NYCRR 387.14(a)(5) public-assistance path member facts; NYSCAP units
  (``SSI_CAP = 4``) are in scope because they follow the regular benefit
  determination.
* ``us-ca`` — child support is fed as a deduction; the encoded CalFresh chain
  carries only the heating/cooling SUA, so limited/telephone-tier units ride
  their applied ``UTIL`` as an incurred shelter cost; the homeless shelter
  deduction feeds the federal claimed-amount input from the file's own
  ``HOMELESS_DED``; categorical eligibility rides the federal
  resource-exemption flag.

Cross-lane note: this module reads QC unit/member/expected objects by the
frozen shapes in ``axiom_oracles.populations.snap_qc`` (Lane A). Beyond the
frozen ``QcMember`` accessors ``earned_income()`` / ``unearned_income()`` and
the ``age`` / ``elderly_or_disabled`` fields, :func:`map_qc_unit` reads the
per-source monthly attributes ``social_security``, ``ssi``, ``tanf``,
``general_assistance``, and ``child_support`` (received) to itemize unearned
income into the Colorado 4.404 categories; missing attributes degrade to zero.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

from ..comparison.report import COMPARISON_REPORT_SCHEMA_VERSION, MismatchKind
from . import snap_populace
from .rulespec_overlay import build_overlay, load_overlay_spec, rewrite_output_ids
from .snap_populace import (
    JURISDICTION_CONFIGS,
    ProjectedCase,
    axiom_rules_env,
    compile_program,
    load_base_inputs,
    month_period,
    outputs_by_reference,
    output_to_python,
    project_deduction_inputs,
    resolve_axiom_binary,
    resolve_workspace_root,
    run_axiom_cases,
    set_input_value,
)


def suite_name(jurisdiction: str) -> str:
    """``us-co`` -> ``co-snap-qc``, matching the comparison registry names."""
    return f"{jurisdiction.split('-', 1)[1]}-snap-qc"

#: Everything is evaluated at this nominal month; see the module docstring and
#: TheAxiomFoundation/rulespec-us#759 for why true-period evaluation is not yet
#: possible.
NOMINAL_PERIOD = (2026, 1)

#: Bound the per-request payload size when running the engine over many cases.
CHUNK_SIZE = 500

#: FY 2024 SNAP standard-deduction module id, before the overlay rewrites it to
#: ``fy-2024-cola`` (rulespec-us monorepo ships the composition on fy-2026-cola).
_PRE_REWRITE_STANDARD_DEDUCTION_ID = (
    "us:policies/usda/snap/fy-2026-cola/deductions#snap_standard_deduction"
)

#: FY 2024 48-state/DC maximum allotment by SNAP household size, with the
#: additional-member increment above eight. Verified against the FNS FY 2024
#: COLA memo and the QC technical documentation appendix F (page 183).
FY2024_MAX_ALLOTMENT_48_STATES = {
    1: 291,
    2: 535,
    3: 766,
    4: 973,
    5: 1155,
    6: 1386,
    7: 1532,
    8: 1751,
}
FY2024_MAX_ALLOTMENT_ADDITIONAL_MEMBER = 219

#: Statewide (single-schedule) SUA region key. Jurisdictions with one schedule
#: per tier use this; New York's regional schedules use the region names the
#: encoded 18 NYCRR 387.12(f)(3)(v) rules branch on.
STATEWIDE = "statewide"


def sua_amounts_from_overlay(
    spec: Any, config: "QcJurisdiction"
) -> dict[str, dict[str, float]]:
    """Derive the tier -> region -> amount SUA table from an overlay spec.

    The fiscal-year SUA amounts are owned by the overlay spec's
    ``parameter_patches`` (the values the patched engine computes with);
    this derives the mapper's standard table from that single source so the
    two can never drift. The jurisdiction's ``sua_tier_by_patch_rule`` names
    the patch rules it expects; a missing patch raises, because a partial
    table would silently misroute the UTIL-versus-standard comparison in
    :func:`map_qc_unit`. The zero ``none`` tier is always present.
    """
    amounts: dict[str, dict[str, float]] = {"none": {STATEWIDE: 0.0}}
    seen: set[str] = set()
    for patch in spec.parameter_patches:
        target = config.sua_tier_by_patch_rule.get(patch.rule)
        if target is None:
            continue
        tier, region = target
        amounts.setdefault(tier, {})[region] = float(patch.to_value)
        seen.add(patch.rule)
    missing = set(config.sua_tier_by_patch_rule) - seen
    if missing:
        raise ValueError(
            f"overlay spec {spec.name!r} does not patch the "
            f"{sorted(missing)} standard utility allowance amounts"
        )
    for tier, entries in amounts.items():
        values = list(entries.values())
        if len(set(values)) != len(values):
            # Region inference matches the QC-applied UTIL amount against the
            # schedule, so two regions sharing an amount within a tier would
            # misroute silently (all FY2024 amounts are distinct).
            raise ValueError(
                f"overlay spec {spec.name!r}: tier {tier!r} has duplicate "
                f"standard amounts across regions ({sorted(entries.items())}); "
                "UTIL-based region inference would be ambiguous"
            )
    return amounts

#: The seven Colorado utility-cost flags (10 CCR 2506-1 section 4.407.31) that
#: drive the standard utility allowance tier.
_HEATING_COOLING_FLAG = (
    "household_incurred_or_anticipated_heating_or_cooling_costs_separate_from_"
    "rent_or_mortgage"
)
_NON_HEATING_UTILITY_FLAGS = (
    "household_pays_electricity_utility_cost",
    "household_pays_water_utility_cost",
    "household_pays_sewer_utility_cost",
    "household_pays_trash_utility_cost",
    "household_pays_cooking_fuel_utility_cost",
)
_TELEPHONE_FLAG = "household_pays_telephone_service_cost"


@dataclass(frozen=True)
class QcJurisdiction:
    """A QC comparison target: a SNAP composition plus its FY overlay.

    ``sua_tier_by_patch_rule`` maps each overlay SUA parameter-patch rule to
    the ``(tier, region)`` it standardizes, tying the mapper's UTIL-matching
    table to the amounts the patched engine computes with.
    ``child_support_convention`` is the state's 7 USC 2014(e)(4) election:
    ``"exclusion"`` states remove child support paid from countable gross
    income (so the compared gross nets the QC-booked deduction out of
    FSGRINC), while ``"deduction"`` states feed it through the federal
    deduction inputs and compare gross unadjusted.
    """

    base: snap_populace.JurisdictionConfig
    overlay: str
    template: Path
    program: Path
    supported_fiscal_years: tuple[int, ...]
    state_fips: int
    sua_tier_by_patch_rule: Mapping[str, tuple[str, str]] = field(
        default_factory=dict
    )
    child_support_convention: str = "deduction"
    #: Compared-label output ids that replace the ``base`` config's for the QC
    #: replay only (applied before the overlay rewrite). New York uses this to
    #: score the 273.10 regulatory chain — the whole-dollar computation FNS
    #: applies — instead of the composition's statutory-chain surface; see the
    #: us-ny entry.
    output_id_overrides: Mapping[str, str] = field(default_factory=dict)


QC_JURISDICTIONS = {
    "us-co": QcJurisdiction(
        base=JURISDICTION_CONFIGS["us-co"],
        overlay="us-co-snap-fy2024",
        template=Path("us-co/policies/cdhs/snap/fy-2026-benefit-calculation.test.yaml"),
        program=Path("us-co/policies/cdhs/snap/fy-2026-benefit-calculation.yaml"),
        supported_fiscal_years=(2024,),
        state_fips=8,
        sua_tier_by_patch_rule={
            "colorado_snap_heating_cooling_utility_allowance_amount": (
                "heating_cooling",
                STATEWIDE,
            ),
            "colorado_snap_basic_utility_allowance_amount": ("limited", STATEWIDE),
            "colorado_snap_one_utility_allowance_amount": (
                "one_utility",
                STATEWIDE,
            ),
            "colorado_snap_telephone_utility_allowance_amount": (
                "telephone",
                STATEWIDE,
            ),
        },
        child_support_convention="exclusion",
    ),
    "us-ny": QcJurisdiction(
        base=JURISDICTION_CONFIGS["us-ny"],
        overlay="us-ny-snap-fy2024",
        template=Path("us-ny/policies/otda/snap/fy-2026-benefit-calculation.test.yaml"),
        program=Path("us-ny/policies/otda/snap/fy-2026-benefit-calculation.yaml"),
        supported_fiscal_years=(2024,),
        state_fips=36,
        sua_tier_by_patch_rule={
            # 18 NYCRR 387.12(f)(3)(v)(a): heating/cooling, three regions.
            "heating_cooling_standard_amount_new_york_city": (
                "heating_cooling",
                "new_york_city",
            ),
            "heating_cooling_standard_amount_nassau_suffolk": (
                "heating_cooling",
                "nassau_suffolk",
            ),
            "heating_cooling_standard_amount_rest_of_state": (
                "heating_cooling",
                "rest_of_state",
            ),
            # (v)(b): utilities-other-than-heating (the QC "limited" tier).
            "utilities_standard_amount_new_york_city": ("limited", "new_york_city"),
            "utilities_standard_amount_nassau_suffolk": ("limited", "nassau_suffolk"),
            "utilities_standard_amount_rest_of_state": ("limited", "rest_of_state"),
            # (v)(c): telephone-only, one statewide amount; rest_of_state
            # leaves both encoded region flags false.
            "telephone_standard_allowance_amount": ("telephone", "rest_of_state"),
        },
        child_support_convention="deduction",
        # The composition's public benefit surface rides the pure-statutory
        # 2014(e)/2017(a) chain, which carries cents; FNS's Minimodel — and
        # New York's own system (QC tech doc footnote 20) — compute in whole
        # dollars under the 273.10(e)(1)(ii)(A) election, which the encoded
        # 273.10 chain implements (rulespec-us#826). The replay therefore
        # scores the 273.10 regulatory chain, fed by the same projected
        # inputs (map_qc_unit pins its shelter total to the composition's
        # own allowable shelter costs). Wiring the composition's public
        # surface to the rounded chain is the companion rulespec-us finding.
        output_id_overrides={
            "snap_regular_month_allotment": (
                "us:regulations/7-cfr/273/10#snap_monthly_allotment"
            ),
            "snap_net_income": (
                "us:regulations/7-cfr/273/10#snap_net_monthly_income"
            ),
            "snap_excess_shelter_deduction": (
                "us:regulations/7-cfr/273/10"
                "#snap_excess_shelter_deduction_for_net_income"
            ),
        },
    ),
    "us-ca": QcJurisdiction(
        base=JURISDICTION_CONFIGS["us-ca"],
        overlay="us-ca-snap-fy2024",
        template=Path("us-ca/policies/cdss/snap/fy-2026-benefit-calculation.test.yaml"),
        program=Path("us-ca/policies/cdss/snap/fy-2026-benefit-calculation.yaml"),
        supported_fiscal_years=(2024,),
        state_fips=6,
        # The encoded CalFresh chain carries only the heating/cooling SUA;
        # limited- and telephone-tier QC units (Table F.7: 158 and 19 dollars)
        # ride their applied UTIL amount as an incurred shelter cost.
        sua_tier_by_patch_rule={
            "snap_standard_utility_allowance_amount": (
                "heating_cooling",
                STATEWIDE,
            ),
        },
        child_support_convention="deduction",
    ),
}


@dataclass(frozen=True)
class _Label:
    """A compared axiom output and the QC value it is checked against."""

    label: str
    stage: str
    expected_attr: str | None
    category: str
    is_benefit: bool


#: Compared labels in the contract's stage order: the first stage whose axiom
#: value diverges from the QC value localizes a mismatch. ``expected_attr`` is a
#: ``QcExpected`` attribute, or ``None`` for the maximum allotment (checked
#: against the FY 2024 table by size, which the QC file does not store directly).
#: The earned-income, medical, dependent-care, and child-support deductions are
#: not separately bound axiom outputs, so a divergence there first surfaces at
#: the standard-deduction, shelter-deduction, or net-income stage.
_LABELS: tuple[_Label, ...] = (
    _Label("snap_gross_monthly_income", "gross_income", "gross_income", "income", False),
    _Label(
        "snap_standard_deduction",
        "standard_deduction",
        "standard_deduction",
        "deductions",
        False,
    ),
    _Label(
        "snap_excess_shelter_deduction",
        "shelter_deduction",
        "shelter_deduction",
        "deductions",
        False,
    ),
    _Label("snap_net_income", "net_income", "net_income", "income", False),
    _Label(
        "snap_maximum_allotment", "maximum_allotment", None, "benefits", False
    ),
    _Label(
        "snap_regular_month_allotment", "benefit", "benefit", "benefits", True
    ),
)


# --------------------------------------------------------------------------- #
# Projection: QC unit -> RuleSpec input surface
# --------------------------------------------------------------------------- #


#: Every QC utility tier the loader can produce (``UtilityTier`` values).
_KNOWN_TIERS = frozenset(
    {"heating_cooling", "limited", "one_utility", "telephone", "none"}
)

#: The 18 NYCRR 387.14(a)(5) public-assistance categorical member fact. Fully
#: qualified because it lives on the categorical relation's member surface,
#: not the composition test template's member entry.
_NY_CATEGORICAL_MEMBER_INPUT = (
    "us-ny:regulations/18-nycrr/387/14/a/5#input."
    "member_receives_family_assistance_nonemergency_safety_net_or_ssi_benefits"
)


def map_qc_unit(
    unit: Any,
    base_inputs: dict[str, Any],
    base_member: dict[str, Any],
    *,
    config: QcJurisdiction,
    sua_amount_by_tier: dict[str, dict[str, float]],
) -> ProjectedCase:
    """Project one QC unit onto a state SNAP composition input surface.

    ``base_inputs`` is the composition test template's household input mapping
    (legal-reference keyed, relations excluded) and ``base_member`` is one
    member entry from that template's ``member_of_household`` relation. Both are
    copied and overridden per :data:`snap_populace.set_input_value` friendly
    names; work, student, SSN, and citizenship member facts keep the template's
    passing defaults because the replay validates benefit computation, not
    eligibility screening. ``sua_amount_by_tier`` is the tier -> region ->
    amount standard utility allowance table derived from the overlay spec via
    :func:`sua_amounts_from_overlay` — the same amounts the patched engine
    computes with. The per-jurisdiction income, deduction, utility, homeless,
    and categorical-eligibility projections are keyed on
    ``config.base.jurisdiction`` (see the module docstring).
    """
    inputs = dict(base_inputs)
    members = list(unit.members)
    jurisdiction = config.base.jurisdiction

    if getattr(unit, "certified_size", None) is None:
        raise ValueError(
            f"QC unit {getattr(unit, 'case_id', '?')} has no certified size "
            "(CERTHHSZ); the loader excludes such rows, so this unit did not "
            "come from load_qc_units"
        )

    for name, value in _income_resource_inputs(jurisdiction, unit, members).items():
        set_input_value(inputs, name, value)

    set_input_value(inputs, "household_size", int(unit.certified_size))

    # Shelter and utilities. The QC-applied allowance (UTIL) is authoritative:
    # when it matches an encoded standard amount the tier (and, for New York,
    # region) flags exercise the encoded allowance rules; when it is present
    # but different (actual expenses, SUA1 = 2, a prorated allowance, or a
    # tier the jurisdiction does not encode) the amount rides as an incurred
    # shelter cost instead; when UTIL is missing entirely the tier's standard
    # is presumed where that is unambiguous (a single schedule). Units
    # receiving the standard homeless shelter deduction (HOMEDED = 3) take the
    # flat-deduction path: the QC file zeroes FSSLTDED for them by
    # construction, so no utility flag is raised at all.
    shelter_costs, matched_sua_amount, utility_flags = (
        _project_shelter_and_utilities(jurisdiction, unit, sua_amount_by_tier)
    )
    set_input_value(inputs, "household_shelter_costs_incurred", shelter_costs)
    for name, value in utility_flags.items():
        set_input_value(inputs, name, value)
    if jurisdiction == "us-ny":
        # The scored 273.10 chain's inputs that no New York composition rule
        # binds and the composition test template does not carry. The shelter
        # total is pinned to the same total the composition's shelter_costs
        # rule computes (incurred costs plus the matched standard allowance),
        # so the regulatory and statutory chains always agree on shelter.
        # QC reviews are active ongoing cases, so the initial-month proration
        # path stays off, and New York's whole-dollar system rounds the
        # thirty-percent reduction up (the ceil and floor branches coincide
        # for whole-dollar maximum allotments in any case).
        inputs[
            "us:regulations/7-cfr/273/10#input.snap_total_allowable_shelter_expenses"
        ] = _money(shelter_costs + matched_sua_amount)
        inputs["us:regulations/7-cfr/273/10#input.household_initial_month"] = False
        inputs[
            "us:regulations/7-cfr/273/10#input."
            "state_agency_rounds_thirty_percent_net_income_up"
        ] = True
        inputs["us:regulations/7-cfr/273/10#input.household_size"] = int(
            unit.certified_size
        )

    homeless_claimed = bool(getattr(unit, "homeless_deduction_claimed", False))
    for name, value in _homeless_inputs(jurisdiction, unit, homeless_claimed).items():
        set_input_value(inputs, name, value)

    dependent_care = _money(getattr(unit, "dependent_care_expense", 0) or 0)

    # Child support: feed the deduction FNS actually applied (FSCSDED), not
    # the reported payment (FSCSEXP). The two match wherever a payment was
    # allowed, but the file carries rows whose reported payment was not
    # allowed as a deduction (FSCSDED = 0), and the applied amount is what
    # enters FSTOTDED — the same applied-amount convention the medical feed
    # uses.
    child_support_deduction = _money(
        getattr(getattr(unit, "expected", None), "child_support_deduction", None)
        or 0
    )

    # Reconstruct the medical deduction FNS actually applied. FSMEDDED equals
    # the excess FSMEDEXP in ordinary states, but in standard-medical-deduction
    # demonstration states it is a flat standard that differs from the excess
    # (10 FY2024 rows nationally), so the applied deduction — not the
    # reported excess — is the operative amount. project_deduction_inputs
    # feeds it plus the $35 threshold, so the engine's ``total - 35``
    # reproduces FSMEDDED in both kinds of state.
    applied_medical = getattr(
        getattr(unit, "expected", None), "medical_deduction", None
    )
    if applied_medical is None:
        applied_medical = getattr(unit, "medical_expenses", 0) or 0
    applied_medical = _money(applied_medical)

    for name, value in project_deduction_inputs(
        config.base,
        dependent_care_deduction=dependent_care,
        child_support_deduction=child_support_deduction,
        medical_deduction=applied_medical,
    ).items():
        set_input_value(inputs, name, value)

    for name, value in _categorical_inputs(jurisdiction, unit, dependent_care).items():
        set_input_value(inputs, name, value)

    # Unit-level elderly-or-disabled status comes from the file's own
    # constructed counts (FSNELDER/FSNDIS) when present: members include
    # non-participants whose income counts but whose age or disability does
    # not confer unit status, so a member-derived OR can overstate it (one
    # real Colorado row: a disabled non-participant made the unit look
    # uncapped for shelter while FNS applied the cap). The engine only
    # consumes any-member-is-elderly-or-disabled, so the unit flag rides on
    # the first member.
    unit_ed = getattr(unit, "unit_has_elderly_or_disabled", None)

    member_inputs: list[dict[str, Any]] = []
    for member in members:
        member_dict = dict(base_member)
        # The member's work-requirement age (7 CFR 273.7 and 273.24) is pinned to
        # the exempting value 60, exactly as snap_populace models work-eligible
        # members: at 60 the engine short-circuits the general and ABAWD work
        # tests, so no eligible QC case is screened out and no member work input
        # is required. The real QC age instead drives the elderly-or-disabled
        # flag below, which is what the benefit computation depends on (shelter
        # cap, medical deduction entitlement, gross-test exemption). This oracle
        # validates benefit computation, not work screening.
        member_dict.update(snap_populace.project_work_member_inputs(True))
        if unit_ed is None:
            elderly = bool(
                (member.age is not None and member.age >= 60)
                or member.elderly_or_disabled
            )
        else:
            elderly = bool(unit_ed) and not member_inputs
        set_input_value(member_dict, "snap_member_is_elderly_or_disabled", elderly)
        if jurisdiction == "us-ny":
            # Every in-scope FY 2024 New York row is categorically eligible
            # (CAT_ELIG 1/2/3), so the replay raises the 387.14(a)(5)
            # public-assistance path on every member — the same
            # passing-defaults convention the work pin uses, because the
            # oracle validates benefit computation, not eligibility
            # adjudication. run_axiom_cases enrolls each member in the
            # categorical relation alongside member_of_household.
            member_dict[_NY_CATEGORICAL_MEMBER_INPUT] = bool(
                unit.categorically_eligible
            )
        member_inputs.append(member_dict)

    entity_id = _entity_id(unit)
    return ProjectedCase(
        spm_unit_id=entity_id,
        household_id=entity_id,
        inputs=inputs,
        member_inputs=member_inputs,
        pe_outputs={},
    )


def _income_resource_inputs(
    jurisdiction: str, unit: Any, members: list[Any]
) -> dict[str, Any]:
    """Project unit income and countable resources onto the state's inputs."""
    earned = _money(_call(unit, "earned_income"))
    total_unearned = _call(unit, "unearned_income")
    liquid = _money(getattr(unit, "liquid_resources", 0) or 0)
    if jurisdiction == "us-ny":
        return {
            "snap_countable_earned_income": earned,
            "snap_countable_unearned_income": _money(total_unearned),
            "snap_gross_monthly_earned_income": earned,
            "snap_total_monthly_unearned_income": _money(total_unearned),
            "snap_income_exclusions": 0,
            "snap_countable_financial_resources": liquid,
        }
    if jurisdiction == "us-ca":
        return {
            "snap_gross_monthly_earned_income": earned,
            "snap_total_monthly_unearned_income": _money(total_unearned),
            "snap_countable_financial_resources": liquid,
        }

    # Colorado: 4.404 itemized unearned income. The category sums come from
    # the same per-source member fields whose total reproduces FSUNEARN
    # exactly.
    retirement_disability = sum(
        _source(member, "social_security") + _source(member, "ssi")
        for member in members
    )
    assistance = sum(
        _source(member, "tanf") + _source(member, "general_assistance")
        for member in members
    )
    direct_support = sum(
        _source(member, "child_support") + _source(member, "alimony")
        for member in members
    )
    other_unearned = (
        total_unearned - retirement_disability - assistance - direct_support
    )
    if other_unearned < -0.005:
        raise ValueError(
            f"QC unit {getattr(unit, 'case_id', '?')}: itemized unearned "
            f"categories exceed the unit total by {-other_unearned:.2f}; the "
            "per-source fields no longer reconstruct FSUNEARN"
        )
    return {
        "snap_countable_earned_income": earned,
        "retirement_disability_payments": _money(retirement_disability),
        "assistance_payments": _money(assistance),
        "direct_support_and_alimony_payments": _money(direct_support),
        "other_gain_or_benefit_payments": _money(max(0.0, other_unearned)),
        "liquid_resource_current_redemption_rate": liquid,
    }


def _categorical_inputs(
    jurisdiction: str, unit: Any, dependent_care: float
) -> dict[str, Any]:
    """Project the QC categorical-eligibility finding onto the state's inputs.

    Every retained QC unit is eligible by construction, so these inputs are
    passing values for the eligibility gates the benefit chain is composed
    behind — not an adjudication of the state's categorical paths.
    """
    categorically_eligible = bool(unit.categorically_eligible)
    if jurisdiction == "us-ny":
        # The member-level public-assistance path fact is raised in
        # map_qc_unit's member loop; these household facts feed the BBCE
        # paths' antecedents from the unit's own record.
        return {
            "household_has_out_of_pocket_dependent_care_expenses": (
                dependent_care > 0
            ),
            "household_has_earned_income_budgeted_for_snap": (
                _money(_call(unit, "earned_income")) > 0
            ),
        }
    if jurisdiction == "us-ca":
        return {
            "snap_categorically_eligible_for_resource_exemption": (
                categorically_eligible
            ),
        }
    return {"snap_basic_categorical_eligible": categorically_eligible}


def _homeless_inputs(
    jurisdiction: str, unit: Any, homeless_claimed: bool
) -> dict[str, Any]:
    """Project the HOMEDED = 3 flat-deduction path onto the state's inputs.

    Standard homeless shelter deduction (7 USC 2014(e)(6)(D)): a flat
    deduction replacing the excess-shelter path. Colorado (10 CCR 2506-1
    section 4.407.3(C)) and New York (18 NYCRR 387.12(f)(3)(vi)) encode the
    same four household facts; the two sub-elections stay False by
    construction, because HOMEDED = 3 is defined as receiving the STANDARD
    homeless deduction (a verified-higher-costs election would be HOMEDED = 4,
    which carries its actuals in RENT and takes the ordinary excess-shelter
    path), and a free-shelter month would have produced no deduction and
    therefore not HOMEDED = 3. California's composition instead feeds the
    federal 273.10 claimed-amount input, so the file's own applied
    HOMELESS_DED rides through ``min(claimed, indexed maximum)``.
    """
    if jurisdiction == "us-ca":
        claimed = (
            _money(getattr(unit, "homeless_deduction_amount", 0) or 0)
            if homeless_claimed
            else 0
        )
        return {"snap_claimed_homeless_shelter_deduction": claimed}
    inputs: dict[str, Any] = {
        "all_household_members_experiencing_homelessness": homeless_claimed,
        "homeless_household_has_shelter_costs": homeless_claimed,
        "homeless_household_free_shelter_all_month": False,
        "verified_higher_homeless_shelter_costs": False,
    }
    if jurisdiction == "us-ny":
        # New York's flat path flows through the 387.12(f)(3)(vi) allowable
        # shelter costs, not the federal claimed-amount deduction, and the
        # composition test template does not carry the 273.10 input — the
        # engine still requires it, so it is pinned to zero by full reference,
        # exactly as the snap_populace New York projection does. (No FY 2024
        # New York row claims the standard homeless deduction.)
        inputs[
            "us:regulations/7-cfr/273/10#input."
            "snap_claimed_homeless_shelter_deduction"
        ] = 0
    return inputs


def _project_shelter_and_utilities(
    jurisdiction: str,
    unit: Any,
    sua_amount_by_tier: dict[str, dict[str, float]],
) -> tuple[float, float, dict[str, bool]]:
    """Resolve shelter costs and utility flags per the UTIL-authoritative rule.

    Returns the (possibly UTIL-augmented) incurred shelter cost, the matched
    standard allowance amount (zero when no encoded standard matched — the
    allowance either rode into the shelter cost or the unit has none), and the
    jurisdiction's utility flag inputs. The region is inferred by matching the
    QC-applied UTIL amount against the encoded schedule — for New York's three
    regional schedules that is the only region signal the public file carries.
    """
    shelter_costs = _money(getattr(unit, "shelter_expense", 0) or 0)
    homeless_claimed = bool(getattr(unit, "homeless_deduction_claimed", False))
    tier = str(getattr(unit.utility_tier, "value", unit.utility_tier))
    if tier not in _KNOWN_TIERS:
        raise ValueError(f"unknown SNAP QC utility tier {tier!r}")
    raw_utility_amount = getattr(unit, "utility_amount", None)
    entries = sua_amount_by_tier.get(tier)

    matched_region: str | None = None
    if homeless_claimed:
        # Flat-deduction path: no utility flag, and the applied allowance does
        # not ride as a cost (FSSLTDED is zeroed by construction).
        pass
    elif entries is None:
        # The jurisdiction does not encode this tier (for example California's
        # limited and telephone allowances): the applied allowance rides as an
        # incurred shelter cost, which reproduces the file's arithmetic.
        if raw_utility_amount is not None:
            shelter_costs = _money(shelter_costs + _money(raw_utility_amount))
    elif raw_utility_amount is None:
        # A recorded tier with a blank UTIL cell means the standard applied
        # (the codebook edited SUA1 for consistency with UTIL) — presumable
        # only when the jurisdiction has a single schedule. With multiple
        # regional schedules the standard is ambiguous, and falling through
        # silently would understate shelter; no FY2024 row hits this, so it
        # fails loudly instead of guessing a region.
        if len(entries) == 1:
            matched_region = next(iter(entries))
        else:
            raise ValueError(
                f"QC unit {getattr(unit, 'case_id', '?')}: utility tier "
                f"{tier!r} has no recorded UTIL amount and {len(entries)} "
                "regional schedules; the standard allowance is ambiguous"
            )
    else:
        applied = _money(raw_utility_amount)
        matched_region = next(
            (
                region
                for region, amount in entries.items()
                if _money(amount) == applied
            ),
            None,
        )
        if matched_region is None:
            shelter_costs = _money(shelter_costs + applied)

    flags = _utility_flag_inputs(
        jurisdiction,
        tier if matched_region is not None else "none",
        matched_region,
    )
    matched_amount = (
        _money(entries[matched_region])
        if matched_region is not None and entries is not None
        else 0.0
    )
    return shelter_costs, matched_amount, flags


def _utility_flag_inputs(
    jurisdiction: str, tier: str, region: str | None
) -> dict[str, bool]:
    """Map a matched QC utility tier (and region) to the state's cost flags."""
    if jurisdiction == "us-ny":
        # 18 NYCRR 387.12(f)(3)(v)(a)-(c): the three allowance rules branch on
        # the heating/cooling, other-utilities, and telephone facts plus the
        # two region facts; the central-meter and HEAP-entitlement facts stay
        # False (the QC file carries no central-meter fact, and the HEAP arm
        # only widens eligibility the heating/cooling fact already grants).
        return {
            _HEATING_COOLING_FLAG: tier == "heating_cooling",
            (
                "household_in_central_meter_housing_charged_only_for_"
                "excess_heating_or_cooling"
            ): False,
            "household_entitled_to_heap_or_liheaa_payment": False,
            (
                "household_billed_separately_for_non_telephone_standard_utility"
            ): tier == "limited",
            (
                "household_incurred_or_anticipated_basic_service_cost_for_"
                "one_telephone"
            ): tier == "telephone",
            "household_resides_in_new_york_city": region == "new_york_city",
            "household_resides_in_nassau_or_suffolk_county": (
                region == "nassau_suffolk"
            ),
        }
    if jurisdiction == "us-ca":
        # The encoded CalFresh chain carries a single heating/cooling SUA.
        return {
            (
                "household_has_heating_and_cooling_costs_separate_from_"
                "rent_or_mortgage"
            ): tier == "heating_cooling",
        }

    # Colorado: the seven 10 CCR 2506-1 section 4.407.31 utility-cost flags.
    flags = {name: False for name in _NON_HEATING_UTILITY_FLAGS}
    flags[_HEATING_COOLING_FLAG] = False
    flags[_TELEPHONE_FLAG] = False
    if tier == "heating_cooling":
        flags[_HEATING_COOLING_FLAG] = True
    elif tier == "limited":
        flags["household_pays_electricity_utility_cost"] = True
        flags["household_pays_water_utility_cost"] = True
    elif tier == "one_utility":
        flags["household_pays_electricity_utility_cost"] = True
    elif tier == "telephone":
        flags[_TELEPHONE_FLAG] = True
    elif tier != "none":
        raise ValueError(f"unknown SNAP QC utility tier {tier!r}")
    return flags


def _entity_id(unit: Any) -> int:
    """Derive a stable positive integer entity id from a QC unit."""
    try:
        row_index = int(str(unit.case_id).rsplit("-", 1)[1])
    except (AttributeError, IndexError, ValueError):
        row_index = abs(hash(getattr(unit, "case_id", id(unit)))) % 1_000_000
    yrmonth = _int_or_zero(getattr(unit, "yrmonth", 0))
    return yrmonth * 1_000_000 + row_index


# --------------------------------------------------------------------------- #
# Comparison driver
# --------------------------------------------------------------------------- #


def run_snap_qc_comparison(
    *,
    fiscal_year: int,
    jurisdiction: str,
    sample_size: int | None = None,
    months: tuple[int, ...] | None = None,
    tolerance: float = 0.0,
    stage_tolerance: float = 1.0,
    workspace_root: str | Path | None = None,
    rulespec_root: str | Path | None = None,
    axiom_binary: str | Path | None = None,
    data_dir: str | Path | None = None,
    include_special_programs: bool = False,
    keep_overlay: bool = False,
) -> dict:
    """Run the SNAP QC oracle for one jurisdiction and fiscal year.

    Returns an ``axiom.comparison_report.v2`` report dict. Loads QC units via
    :mod:`axiom_oracles.populations.snap_qc`, builds the fiscal-year overlay,
    compiles the composition once, runs the engine over the projected cases in
    chunks, and compares the regular monthly allotment (headline) plus its
    intermediate stages against the QC constructed values.
    """
    if jurisdiction not in QC_JURISDICTIONS:
        raise ValueError(
            f"unknown jurisdiction {jurisdiction!r}; "
            f"available: {sorted(QC_JURISDICTIONS)}"
        )
    config = QC_JURISDICTIONS[jurisdiction]
    if fiscal_year not in config.supported_fiscal_years:
        raise ValueError(
            f"jurisdiction {jurisdiction!r} supports fiscal years "
            f"{config.supported_fiscal_years}, not {fiscal_year}"
        )

    workspace_root = resolve_workspace_root(
        Path(workspace_root) if workspace_root is not None else None
    )
    # Environment fallbacks live here, next to the loader's own
    # AXIOM_SNAP_QC_DATA_DIR, so the module CLI, the live test, and the
    # comparison runner all honor the same variables.
    if rulespec_root is None:
        rulespec_root = os.environ.get("AXIOM_SNAP_QC_RULESPEC_ROOT") or None
    rulespec_root = (
        Path(rulespec_root).expanduser()
        if rulespec_root is not None
        else workspace_root / "rulespec-us"
    )
    if axiom_binary is None:
        axiom_binary = os.environ.get("AXIOM_SNAP_QC_AXIOM_BINARY") or None
    axiom_binary = resolve_axiom_binary(
        workspace_root,
        Path(axiom_binary).expanduser() if axiom_binary is not None else None,
    )
    period = month_period(*NOMINAL_PERIOD)
    _validate_months(months, fiscal_year)

    spec = load_overlay_spec(config.overlay)
    output_id_by_label = _output_id_by_label(config, spec.module_id_rewrites)

    from ..populations import snap_qc as snap_qc_population

    units, exclusion_log = snap_qc_population.load_qc_units(
        fiscal_year,
        state_fips=config.state_fips,
        months=months,
        data_dir=data_dir,
        include_special_programs=include_special_programs,
    )
    units = list(units)
    if sample_size is not None:
        units = units[:sample_size]

    base_inputs = load_base_inputs(rulespec_root / config.template)
    base_member = _load_base_member(rulespec_root / config.template, config.base.relation_id)

    overlay_dir = Path(tempfile.mkdtemp(prefix="snap-qc-overlay-"))
    try:
        build = build_overlay(spec, rulespec_root, overlay_dir)
        # Single self-contained root. The engine unions module ids across roots
        # rather than shadowing, so fronting the monorepo with the overlay would
        # compile both the fy-2024 and fy-2026 cola imports and abort with a
        # duplicate-rule error. The materialized overlay is complete on its own.
        env = axiom_rules_env(build.program_path, workspace_root)
        env["AXIOM_RULESPEC_REPO_ROOTS"] = str(build.overlay_root)
        sua_amount_by_tier = sua_amounts_from_overlay(spec, config)
        cases = [
            map_qc_unit(
                unit,
                base_inputs,
                base_member,
                config=config,
                sua_amount_by_tier=sua_amount_by_tier,
            )
            for unit in units
        ]
        results = _run_cases(
            binary=axiom_binary,
            program_path=build.program_path,
            cases=cases,
            period=period,
            output_ids=list(output_id_by_label.values()),
            config=config,
            env=env,
        )
        report = _build_report(
            units=units,
            results=results,
            output_id_by_label=output_id_by_label,
            jurisdiction=jurisdiction,
            fiscal_year=fiscal_year,
            tolerance=tolerance,
            stage_tolerance=stage_tolerance,
            exclusion_log=exclusion_log,
            period=period,
            overlay_build=build,
            rulespec_root=rulespec_root,
            axiom_binary=axiom_binary,
            pins=_pins_for(snap_qc_population, fiscal_year),
            child_support_convention=config.child_support_convention,
        )
    finally:
        if not keep_overlay:
            shutil.rmtree(overlay_dir, ignore_errors=True)
    if keep_overlay:
        report["summary"]["provenance"]["overlay_kept_at"] = str(overlay_dir)
    return report


def _run_cases(
    *,
    binary: Path,
    program_path: Path,
    cases: list[ProjectedCase],
    period: snap_populace.Period,
    output_ids: list[str],
    config: QcJurisdiction,
    env: dict[str, str],
) -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="snap-qc-artifact-") as artifact_dir:
        artifact = Path(artifact_dir) / "program.compiled.json"
        compile_program(binary, program_path, artifact, env=env)
        results: list[dict[str, Any]] = []
        for start in range(0, len(cases), CHUNK_SIZE):
            chunk = cases[start : start + CHUNK_SIZE]
            if not chunk:
                continue
            results.extend(
                run_axiom_cases(
                    binary=binary,
                    artifact=artifact,
                    cases=chunk,
                    period=period,
                    output_ids=output_ids,
                    relation_id=config.base.relation_id,
                    additional_relation_ids=config.base.additional_relation_ids,
                    member_entity_type=config.base.member_entity_type,
                    env=env,
                )
            )
    return results


def _output_id_by_label(
    config: QcJurisdiction, module_id_rewrites: dict[str, str]
) -> dict[str, str]:
    """Build the compared label -> output-id map, overlay-rewritten."""
    base_ids = dict(config.base.output_id_by_label)
    base_ids["snap_standard_deduction"] = _PRE_REWRITE_STANDARD_DEDUCTION_ID
    base_ids.update(config.output_id_overrides)
    pre_rewrite = {label.label: base_ids[label.label] for label in _LABELS}
    return rewrite_output_ids(pre_rewrite, module_id_rewrites)


# --------------------------------------------------------------------------- #
# Report assembly (axiom.comparison_report.v2 shape)
# --------------------------------------------------------------------------- #


def _build_report(
    *,
    units: list[Any],
    results: list[dict[str, Any]],
    output_id_by_label: dict[str, str],
    jurisdiction: str,
    fiscal_year: int,
    tolerance: float,
    stage_tolerance: float,
    exclusion_log: Any,
    period: snap_populace.Period,
    overlay_build: Any,
    rulespec_root: Path,
    axiom_binary: Path,
    pins: Any,
    child_support_convention: str = "deduction",
) -> dict:
    suite = suite_name(jurisdiction)
    locale = "-".join(part.upper() for part in jurisdiction.split("-"))
    aggregates = {label.label: _fresh_bucket() for label in _LABELS}
    # Concept id per stage: the compared output whose divergence localizes a
    # mismatch. Stamped onto mismatch rows so dispositions and dashboards can
    # key on the concept, mirroring the comparator's v2 rows.
    concept_by_stage = {
        label.stage: output_id_by_label.get(label.label) for label in _LABELS
    }
    stage_counts: dict[str, int] = {}
    mismatches: list[dict] = []
    errors: list[dict] = []
    case_rows: list[dict] = []

    match_count = 0
    mismatch_count = 0
    comparison_count = 0
    comparison_weight = 0.0
    match_weight = 0.0
    mismatch_weight = 0.0
    error_case_count = 0
    error_case_weight = 0.0

    for unit, result in zip(units, results, strict=True):
        weight = _float_or(getattr(unit, "weight", 1.0), 1.0)
        references = outputs_by_reference(result.get("outputs", {}))
        axiom_values: dict[str, float | None] = {}
        expected_values: dict[str, float | None] = {}
        matches: dict[str, bool | None] = {}

        for label in _LABELS:
            output_id = output_id_by_label[label.label]
            axiom_value = _axiom_value(references, output_id)
            if axiom_value is None:
                errors.append(
                    {
                        "case_id": _case_id(unit),
                        "side": "right",
                        "engine": "axiom",
                        "error": f"missing output {output_id}",
                    }
                )
            expected_value = _expected_value(
                label, unit, child_support_convention=child_support_convention
            )
            axiom_values[label.stage] = axiom_value
            expected_values[label.stage] = expected_value
            match = _matches(
                label, axiom_value, expected_value, tolerance, stage_tolerance
            )
            matches[label.stage] = match
            _update_bucket(
                aggregates[label.label], axiom_value, expected_value, match, weight
            )

        benefit_stage = _benefit_stage()
        benefit_match = matches[benefit_stage]
        if benefit_match is None:
            # One side of the headline comparison is missing (a missing axiom
            # output already produced an errors row above; a missing QC
            # constructed benefit is excluded at load). These are
            # infrastructure failures, not divergences: they are counted
            # separately so a broken output id reads as N error cases, never
            # as a 0% match rate.
            error_case_count += 1
            error_case_weight += weight
            case_rows.append(
                {
                    "case_id": _case_id(unit),
                    "yrmonth": getattr(unit, "yrmonth", None),
                    "weight": _clean(weight),
                    "matched": None,
                    "stage": "error",
                }
            )
            continue
        comparison_count += 1
        comparison_weight += weight
        matched = bool(benefit_match)
        if matched:
            match_count += 1
            match_weight += weight
        else:
            mismatch_count += 1
            mismatch_weight += weight

        first_stage = _first_divergent_stage(matches)
        if not matched:
            if first_stage is not None:
                stage_counts[first_stage] = stage_counts.get(first_stage, 0) + 1
            mismatches.append(
                _mismatch_row(
                    unit,
                    weight,
                    first_stage,
                    axiom_values,
                    expected_values,
                    concept=concept_by_stage.get(first_stage),
                )
            )
        case_rows.append(
            {
                "case_id": _case_id(unit),
                "yrmonth": getattr(unit, "yrmonth", None),
                "weight": _clean(weight),
                "matched": matched,
                "stage": None if matched else first_stage,
            }
        )

    summary = {
        "comparison_count": comparison_count,
        "match_count": match_count,
        "mismatch_count": mismatch_count,
        "error_case_count": error_case_count,
        "match_rate": _percentage(match_count, comparison_count),
        "weighted": {
            "comparison_weight": _clean(comparison_weight),
            "match_weight": _clean(match_weight),
            "mismatch_weight": _clean(mismatch_weight),
            "error_case_weight": _clean(error_case_weight),
            "match_rate": _percentage(match_weight, comparison_weight),
        },
        "stages": [
            {"stage": stage, "count": stage_counts[stage]}
            for stage in _ordered_stages(stage_counts)
        ],
        "exclusions": _exclusion_summary(exclusion_log),
        "provenance": _oracle_provenance(
            overlay_build=overlay_build,
            pins=pins,
            axiom_binary=axiom_binary,
            period=period,
            rulespec_root=rulespec_root,
            fiscal_year=fiscal_year,
        ),
    }

    return {
        "schema_version": COMPARISON_REPORT_SCHEMA_VERSION,
        "suite": suite,
        "population": "snap-qc-puf",
        "engines": {"left": "snap-qc", "right": "axiom"},
        "locales": [locale],
        "scope": None,
        "concepts": _concept_rows(output_id_by_label, tolerance, stage_tolerance),
        "case_count": comparison_count,
        "summary": summary,
        "aggregates": _aggregate_rows(aggregates, output_id_by_label),
        "mismatches": mismatches,
        "errors": errors,
        "cases": case_rows,
        "provenance": {
            "schema": "axiom_oracles.provenance.v1",
            "generated_by": f"axiom_oracles.bridges.snap_qc_compare::{suite}",
            "oracle": {
                "name": "snap-qc",
                "fiscal_year": fiscal_year,
                "period": period.label,
            },
        },
    }


def _mismatch_row(
    unit: Any,
    weight: float,
    first_stage: str | None,
    axiom_values: dict[str, float | None],
    expected_values: dict[str, float | None],
    *,
    concept: str | None = None,
) -> dict:
    benefit_stage = _benefit_stage()
    axiom_benefit = axiom_values.get(benefit_stage)
    expected_benefit = expected_values.get(benefit_stage)
    # Left minus right (QC minus axiom), matching the v2 schema's mismatch
    # convention and this report's own weighted aggregates.
    difference = (
        None
        if axiom_benefit is None or expected_benefit is None
        else _clean(float(expected_benefit) - float(axiom_benefit))
    )
    return {
        "case_id": _case_id(unit),
        "qc_case_id": _case_id(unit),
        "concept": concept,
        "yrmonth": getattr(unit, "yrmonth", None),
        "weight": _clean(weight),
        "stage": first_stage,
        "kind": MismatchKind.AMOUNT_DIFFERENCE,
        "received_minimum_benefit": _received_minimum_benefit(unit),
        "difference": difference,
        "axiom": {stage: _clean(value) for stage, value in axiom_values.items()},
        "qc": {stage: _clean(value) for stage, value in expected_values.items()},
    }


def _concept_rows(
    output_id_by_label: dict[str, str], tolerance: float, stage_tolerance: float
) -> list[dict]:
    rows = []
    for label in _LABELS:
        rows.append(
            {
                "id": output_id_by_label[label.label],
                "description": _describe(label),
                "category": label.category,
                "comparison": "amount",
                "tolerance": tolerance if label.is_benefit else stage_tolerance,
                "relative_tolerance": 0,
                "priority": "high" if label.is_benefit else "normal",
                "components": [],
                "parent": None,
            }
        )
    return rows


def _aggregate_rows(
    aggregates: dict[str, dict], output_id_by_label: dict[str, str]
) -> list[dict]:
    rows = []
    for label in _LABELS:
        bucket = aggregates[label.label]
        if not bucket["comparison_count"]:
            continue
        rows.append(
            {
                "concept": output_id_by_label[label.label],
                "description": _describe(label),
                "category": label.category,
                "comparison": "amount",
                "parent": None,
                "components": [],
                "comparison_count": bucket["comparison_count"],
                "mismatch_count": bucket["mismatch_count"],
                "missing_left_count": bucket["missing_left_count"],
                "missing_right_count": bucket["missing_right_count"],
                "missing_both_count": bucket["missing_both_count"],
                "match_rate": _percentage(
                    bucket["match_count"], bucket["comparison_count"]
                ),
                "comparison_weight": _clean(bucket["comparison_weight"]),
                "match_weight": _clean(bucket["match_weight"]),
                "mismatch_weight": _clean(bucket["mismatch_weight"]),
                "weighted_match_rate": _percentage(
                    bucket["match_weight"], bucket["comparison_weight"]
                ),
                "left_weighted_sum": _clean(bucket["left_weighted_sum"]),
                "right_weighted_sum": _clean(bucket["right_weighted_sum"]),
                "weighted_difference": _clean(
                    bucket["left_weighted_sum"] - bucket["right_weighted_sum"]
                ),
            }
        )
    return rows


def _oracle_provenance(
    *,
    overlay_build: Any,
    pins: Any,
    axiom_binary: Path,
    period: snap_populace.Period,
    rulespec_root: Path,
    fiscal_year: int,
) -> dict:
    return {
        "overlay": overlay_build.provenance,
        "pins": _pin_dict(pins),
        "axiom_binary": str(axiom_binary),
        "rulespec_root": str(rulespec_root),
        "fiscal_year": fiscal_year,
        "period": period.label,
        "period_rationale": (
            "Evaluated at the nominal month 2026-01: the Colorado SNAP chain "
            "module versions are snapshot-dated to 2025-10-01, so a true FY 2024 "
            "period cannot select them until the parameter-set inversion in "
            "TheAxiomFoundation/rulespec-us#759 lands."
        ),
    }


# --------------------------------------------------------------------------- #
# Small value helpers
# --------------------------------------------------------------------------- #


def _matches(
    label: _Label,
    axiom_value: float | None,
    expected_value: float | None,
    tolerance: float,
    stage_tolerance: float,
) -> bool | None:
    if axiom_value is None or expected_value is None:
        return None
    if label.is_benefit:
        return abs(round(float(axiom_value)) - round(float(expected_value))) <= tolerance
    return abs(float(axiom_value) - float(expected_value)) <= stage_tolerance


def _first_divergent_stage(matches: dict[str, bool | None]) -> str | None:
    for label in _LABELS:
        if matches.get(label.stage) is False:
            return label.stage
    return None


def _expected_value(
    label: _Label, unit: Any, *, child_support_convention: str = "deduction"
) -> float | None:
    if label.label == "snap_maximum_allotment":
        return float(_fy2024_max_allotment(unit.certified_size))
    if label.expected_attr is None:
        return None
    value = getattr(unit.expected, label.expected_attr, None)
    if value is None:
        return None
    if (
        label.expected_attr == "gross_income"
        and child_support_convention == "exclusion"
    ):
        # Exclusion states (Colorado's 7 USC 2014(e)(4) election) remove child
        # support paid from countable gross income in the composition; the QC
        # file books the same amount as a deduction instead (FSCSDED; the
        # FSCSEXP codebook entry notes the state split). Net income is
        # identical either way, so the gross comparison nets the QC-recorded
        # deduction out of FSGRINC. Deduction states compare gross unadjusted.
        child_support = getattr(unit.expected, "child_support_deduction", None)
        if child_support:
            return float(value) - float(child_support)
    return float(value)


def _axiom_value(references: dict[str, Any], output_id: str) -> float | None:
    output = references.get(output_id)
    if not isinstance(output, dict):
        return None
    value = output_to_python(output)
    if value is None or isinstance(value, str):
        return None
    return float(value)


def _fy2024_max_allotment(size: Any) -> int:
    size = int(size)
    if size <= 0:
        return 0
    if size in FY2024_MAX_ALLOTMENT_48_STATES:
        return FY2024_MAX_ALLOTMENT_48_STATES[size]
    return (
        FY2024_MAX_ALLOTMENT_48_STATES[8]
        + (size - 8) * FY2024_MAX_ALLOTMENT_ADDITIONAL_MEMBER
    )


def _fresh_bucket() -> dict[str, float | int]:
    return {
        "comparison_count": 0,
        "match_count": 0,
        "mismatch_count": 0,
        "comparison_weight": 0.0,
        "match_weight": 0.0,
        "mismatch_weight": 0.0,
        "left_weighted_sum": 0.0,
        "right_weighted_sum": 0.0,
        "missing_left_count": 0,
        "missing_right_count": 0,
        "missing_both_count": 0,
    }


def _update_bucket(
    bucket: dict[str, float | int],
    axiom_value: float | None,
    expected_value: float | None,
    match: bool | None,
    weight: float,
) -> None:
    if expected_value is None:
        bucket["missing_left_count"] += 1
    if axiom_value is None:
        bucket["missing_right_count"] += 1
    if axiom_value is None and expected_value is None:
        bucket["missing_both_count"] += 1
    if match is None:
        return
    bucket["comparison_count"] += 1
    bucket["comparison_weight"] += weight
    if match:
        bucket["match_count"] += 1
        bucket["match_weight"] += weight
    else:
        bucket["mismatch_count"] += 1
        bucket["mismatch_weight"] += weight
    bucket["left_weighted_sum"] += float(expected_value) * weight
    bucket["right_weighted_sum"] += float(axiom_value) * weight


def _ordered_stages(stage_counts: dict[str, int]) -> list[str]:
    order = [label.stage for label in _LABELS]
    return sorted(stage_counts, key=lambda stage: order.index(stage))


def _benefit_stage() -> str:
    return next(label.stage for label in _LABELS if label.is_benefit)


def _validate_months(months: tuple[int, ...] | None, fiscal_year: int) -> None:
    """Reject month filters that cannot match any YRMONTH in the fiscal year.

    The loader filters on the file's YRMONTH values (YYYYMM); fiscal year N
    spans October N-1 through September N. Calendar-month integers (1..12)
    silently match nothing, so they are rejected here instead of producing an
    empty comparison.
    """
    if months is None:
        return
    valid = {(fiscal_year - 1) * 100 + m for m in range(10, 13)} | {
        fiscal_year * 100 + m for m in range(1, 10)
    }
    bad = [m for m in months if m not in valid]
    if bad:
        raise ValueError(
            f"months must be YRMONTH values within fiscal year {fiscal_year} "
            f"({min(valid)}..{max(valid)}); got {bad}"
        )


def _describe(label: _Label) -> str:
    return label.stage.replace("_", " ")


def _load_base_member(path: Path, relation_id: str) -> dict[str, Any]:
    cases = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    members = cases[0]["input"].get(relation_id)
    if not isinstance(members, list) or not members:
        raise ValueError(
            f"{path} first test case has no members under relation {relation_id!r}"
        )
    return dict(members[0])


def _pins_for(module: Any, fiscal_year: int) -> Any:
    pins = getattr(module, "SNAP_QC_PINS", {})
    if isinstance(pins, dict):
        return pins.get(fiscal_year)
    return None


def _pin_dict(pin: Any) -> dict | None:
    if pin is None:
        return None
    for attr in ("_asdict", "as_dict"):
        method = getattr(pin, attr, None)
        if callable(method):
            return dict(method())
    from dataclasses import asdict, is_dataclass

    if is_dataclass(pin):
        return {key: _jsonable(value) for key, value in asdict(pin).items()}
    return {
        key: _jsonable(getattr(pin, key))
        for key in ("fiscal_year", "url", "sha256", "archive_member")
        if hasattr(pin, key)
    }


def _exclusion_summary(log: Any) -> dict:
    if log is None:
        return {}
    summary: dict[str, Any] = {}
    for attr in ("total_loaded", "total_excluded"):
        if hasattr(log, attr):
            summary[attr] = getattr(log, attr)
    counts = getattr(log, "counts", None)
    if isinstance(counts, dict):
        summary["by_reason"] = {str(key): int(value) for key, value in counts.items()}
    return summary


def _received_minimum_benefit(unit: Any) -> bool | None:
    value = getattr(getattr(unit, "expected", None), "received_minimum_benefit", None)
    return None if value is None else bool(value)


def _case_id(unit: Any) -> Any:
    return getattr(unit, "case_id", None)


def _call(member: Any, name: str) -> float:
    method = getattr(member, name, None)
    if callable(method):
        return _float_or(method(), 0.0)
    return _float_or(method, 0.0)


def _source(member: Any, name: str) -> float:
    return _float_or(getattr(member, name, 0.0), 0.0)


def _money(value: Any) -> float:
    return snap_populace.money(value)


def _float_or(value: Any, default: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _clean(value: Any) -> Any:
    if value is None:
        return None
    number = round(float(value), 6)
    if number.is_integer():
        return int(number)
    return number


def _percentage(numerator: float, denominator: float) -> float:
    if not denominator:
        return 0
    return _clean(numerator / denominator * 100)


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def configure_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--fiscal-year", type=int, default=2024)
    parser.add_argument(
        "--jurisdiction", choices=sorted(QC_JURISDICTIONS), default="us-co"
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Limit the number of QC units after state/month filtering.",
    )
    parser.add_argument(
        "--months",
        type=_month_list,
        default=None,
        help=(
            "Comma-separated YRMONTH sample months to include, as YYYYMM "
            "(for example 202310,202311); a fiscal year spans October through "
            "the following September."
        ),
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.0,
        help="Dollar tolerance for the headline benefit, after whole-dollar rounding.",
    )
    parser.add_argument(
        "--stage-tolerance",
        type=float,
        default=1.0,
        help="Dollar tolerance for the intermediate stage comparisons.",
    )
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--rulespec-root", type=Path, default=None)
    parser.add_argument("--workspace-root", type=Path, default=None)
    parser.add_argument("--axiom-binary", type=Path, default=None)
    parser.add_argument(
        "--output", type=Path, default=None, help="Write the report JSON here."
    )
    parser.add_argument(
        "--write-csv", type=Path, default=None, help="Write mismatch rows as CSV here."
    )
    parser.add_argument("--fail-on-mismatch", action="store_true")
    parser.add_argument("--min-match-rate", type=float, default=None)
    parser.add_argument("--include-special-programs", action="store_true")
    return parser


def _month_list(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split(",") if part.strip())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    configure_parser(parser)
    return parser.parse_args()


def main(args: argparse.Namespace | None = None) -> int:
    if args is None:
        args = parse_args()
    report = run_snap_qc_comparison(
        fiscal_year=args.fiscal_year,
        jurisdiction=args.jurisdiction,
        sample_size=args.sample_size,
        months=args.months,
        tolerance=args.tolerance,
        stage_tolerance=args.stage_tolerance,
        workspace_root=args.workspace_root,
        rulespec_root=args.rulespec_root,
        axiom_binary=args.axiom_binary,
        data_dir=args.data_dir,
        include_special_programs=args.include_special_programs,
    )
    summary = report["summary"]
    print(f"Suite: {report['suite']}")
    print(
        f"Benefit match: {summary['match_count']:,}/{summary['comparison_count']:,} "
        f"({summary['match_rate']}%), "
        f"HWGT-weighted {summary['weighted']['match_rate']}%"
    )
    if summary["stages"]:
        print("First divergent stage counts:")
        for row in summary["stages"]:
            print(f"  {row['stage']}: {row['count']:,}")
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True))
        print(f"Wrote {args.output}")
    if args.write_csv is not None:
        _write_mismatch_csv(args.write_csv, report["mismatches"])
        print(f"Wrote {args.write_csv}")

    match_rate = summary["match_rate"]
    if args.min_match_rate is not None and match_rate < args.min_match_rate:
        print(f"Match rate {match_rate}% is below required {args.min_match_rate}%")
        return 1
    if args.fail_on_mismatch and summary["mismatch_count"] > 0:
        return 1
    return 0


def _write_mismatch_csv(path: Path, mismatches: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "qc_case_id",
        "yrmonth",
        "weight",
        "stage",
        "received_minimum_benefit",
        "difference",
    ]
    stages = [label.stage for label in _LABELS]
    fieldnames.extend(f"axiom_{stage}" for stage in stages)
    fieldnames.extend(f"qc_{stage}" for stage in stages)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in mismatches:
            flat = {
                "qc_case_id": row["qc_case_id"],
                "yrmonth": row["yrmonth"],
                "weight": row["weight"],
                "stage": row["stage"],
                "received_minimum_benefit": row["received_minimum_benefit"],
                "difference": row["difference"],
            }
            for stage in stages:
                flat[f"axiom_{stage}"] = row["axiom"].get(stage)
                flat[f"qc_{stage}"] = row["qc"].get(stage)
            writer.writerow(flat)


if __name__ == "__main__":
    raise SystemExit(main())
