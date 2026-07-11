"""Validate Colorado SNAP RuleSpec output against the SNAP QC administrative file.

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
wires the Colorado composition to the FY 2026 COLA parameter set. The overlay
rewrites the cola module ids to ``fy-2024-cola`` and patches the four Colorado
SUA amounts, then the engine runs at the nominal period ``2026-01``: the chain
module versions are snapshot-dated to their 2025-10-01 effective dates, so a
true-FY-2024 period cannot select them today. Once
TheAxiomFoundation/rulespec-us#759 inverts parameter selection to be
period-driven, the overlay and the nominal period both retire.

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
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..comparison.report import COMPARISON_REPORT_SCHEMA_VERSION, MismatchKind
from . import snap_populace
from .rulespec_overlay import build_overlay, load_overlay_spec, rewrite_output_ids
from .snap_populace import (
    JURISDICTION_CONFIGS,
    ProjectedCase,
    axiom_engine_env,
    compile_program,
    load_base_inputs,
    month_period,
    outputs_by_reference,
    output_to_python,
    resolve_axiom_binary,
    run_axiom_cases,
    set_input_value,
)
from .rulespec_paths import require_rulespec_checkout

SUITE = "co-snap-qc"

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

#: ``FSMEDEXP`` is the allowable medical expense *in excess of $35* (codebook
#: PDF p.84), and the QC recomputation sets ``FSMEDDED = MAX(0, FSMEDEXP)`` —
#: it does not model Colorado's standard medical deduction demonstration
#: ($165 standard; Table F.4), only the statutory excess. The statutory engine
#: computes ``total - 35``, so the mapper feeds ``FSMEDEXP + 35`` and the
#: engine's deduction reproduces ``FSMEDDED`` exactly.
_MEDICAL_EXCESS_THRESHOLD = 35.0

#: Overlay parameter-patch rule name -> utility tier. The fiscal-year SUA
#: amounts are owned by the overlay spec's ``parameter_patches`` (the values
#: the engine actually computes with); :func:`sua_amounts_from_overlay`
#: derives the mapper's per-tier standard table from that single source so
#: the two can never drift.
_SUA_PATCH_RULE_TO_TIER = {
    "colorado_snap_heating_cooling_utility_allowance_amount": "heating_cooling",
    "colorado_snap_basic_utility_allowance_amount": "limited",
    "colorado_snap_one_utility_allowance_amount": "one_utility",
    "colorado_snap_telephone_utility_allowance_amount": "telephone",
}


def sua_amounts_from_overlay(spec: Any) -> dict[str, float]:
    """Derive the per-tier standard utility allowance table from an overlay spec.

    Reads the ``to`` value of each SUA parameter patch (QC technical
    documentation Table F.7 amounts, the values the patched engine computes
    with) and adds the zero ``none`` tier. Raises if the spec does not patch
    all four Colorado allowances — a partial table would silently misroute the
    UTIL-versus-standard comparison in :func:`map_qc_unit`.
    """
    amounts: dict[str, float] = {"none": 0.0}
    for patch in spec.parameter_patches:
        tier = _SUA_PATCH_RULE_TO_TIER.get(patch.rule)
        if tier is not None:
            amounts[tier] = float(patch.to_value)
    missing = set(_SUA_PATCH_RULE_TO_TIER.values()) - set(amounts)
    if missing:
        raise ValueError(
            f"overlay spec {spec.name!r} does not patch the "
            f"{sorted(missing)} standard utility allowance amounts"
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
    """A QC comparison target: a SNAP composition plus its FY overlay."""

    base: snap_populace.JurisdictionConfig
    overlay: str
    template: Path
    program: Path
    supported_fiscal_years: tuple[int, ...]
    state_fips: int


QC_JURISDICTIONS = {
    "us-co": QcJurisdiction(
        base=JURISDICTION_CONFIGS["us-co"],
        overlay="us-co-snap-fy2024",
        template=Path("us-co/policies/cdhs/snap/fy-2026-benefit-calculation.test.yaml"),
        program=Path("us-co/policies/cdhs/snap/fy-2026-benefit-calculation.yaml"),
        supported_fiscal_years=(2024,),
        state_fips=8,
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
    _Label(
        "snap_gross_monthly_income", "gross_income", "gross_income", "income", False
    ),
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
    _Label("snap_maximum_allotment", "maximum_allotment", None, "benefits", False),
    _Label("snap_regular_month_allotment", "benefit", "benefit", "benefits", True),
)


# --------------------------------------------------------------------------- #
# Projection: QC unit -> RuleSpec input surface
# --------------------------------------------------------------------------- #


def map_qc_unit(
    unit: Any,
    base_inputs: dict[str, Any],
    base_member: dict[str, Any],
    *,
    sua_amount_by_tier: dict[str, float],
) -> ProjectedCase:
    """Project one QC unit onto the Colorado SNAP composition input surface.

    ``base_inputs`` is the composition test template's household input mapping
    (legal-reference keyed, relations excluded) and ``base_member`` is one
    member entry from that template's ``member_of_household`` relation. Both are
    copied and overridden per :data:`snap_populace.set_input_value` friendly
    names; work, student, SSN, and citizenship member facts keep the template's
    passing defaults because the replay validates benefit computation, not
    eligibility screening. ``sua_amount_by_tier`` is the per-tier standard
    utility allowance table derived from the overlay spec via
    :func:`sua_amounts_from_overlay` — the same amounts the patched engine
    computes with.
    """
    inputs = dict(base_inputs)
    members = list(unit.members)

    if getattr(unit, "certified_size", None) is None:
        raise ValueError(
            f"QC unit {getattr(unit, 'case_id', '?')} has no certified size "
            "(CERTHHSZ); the loader excludes such rows, so this unit did not "
            "come from load_qc_units"
        )

    set_input_value(
        inputs,
        "snap_countable_earned_income",
        _money(_call(unit, "earned_income")),
    )

    # 4.404 itemized unearned income. The category sums come from the same
    # per-source member fields whose total reproduces FSUNEARN exactly.
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
    total_unearned = _call(unit, "unearned_income")
    other_unearned = (
        total_unearned - retirement_disability - assistance - direct_support
    )
    if other_unearned < -0.005:
        raise ValueError(
            f"QC unit {getattr(unit, 'case_id', '?')}: itemized unearned "
            f"categories exceed the unit total by {-other_unearned:.2f}; the "
            "per-source fields no longer reconstruct FSUNEARN"
        )
    set_input_value(
        inputs, "retirement_disability_payments", _money(retirement_disability)
    )
    set_input_value(inputs, "assistance_payments", _money(assistance))
    set_input_value(
        inputs, "direct_support_and_alimony_payments", _money(direct_support)
    )
    set_input_value(
        inputs, "other_gain_or_benefit_payments", _money(max(0.0, other_unearned))
    )

    set_input_value(inputs, "household_size", int(unit.certified_size))

    # Shelter and utilities. The QC-applied allowance (UTIL) is authoritative:
    # when it matches the tier's standard amount the tier flags exercise the
    # encoded allowance rules; when it is present but different (actual
    # expenses, SUA1 = 2, or a prorated allowance) the amount rides as an
    # incurred shelter cost instead; when UTIL is missing entirely the tier's
    # standard is presumed (the codebook edited SUA1 for consistency with
    # UTIL, so a recorded tier with a blank amount means the standard applied).
    # Units receiving the standard homeless shelter deduction (HOMEDED = 3)
    # take the flat-deduction path: the QC file zeroes FSSLTDED for them by
    # construction, so no utility flag is raised at all.
    shelter_costs = _money(getattr(unit, "shelter_expense", 0) or 0)
    utility_flags = _utility_flag_inputs(unit.utility_tier)
    homeless_claimed = bool(getattr(unit, "homeless_deduction_claimed", False))
    raw_utility_amount = getattr(unit, "utility_amount", None)
    tier = str(getattr(unit.utility_tier, "value", unit.utility_tier))
    if tier not in sua_amount_by_tier:
        raise ValueError(f"unknown SNAP QC utility tier {tier!r}")
    standard_amount = _money(sua_amount_by_tier[tier])
    if homeless_claimed:
        utility_flags = {name: False for name in utility_flags}
    elif (
        raw_utility_amount is not None and _money(raw_utility_amount) != standard_amount
    ):
        utility_flags = {name: False for name in utility_flags}
        shelter_costs = _money(shelter_costs + _money(raw_utility_amount))
    set_input_value(inputs, "household_shelter_costs_incurred", shelter_costs)
    for name, value in utility_flags.items():
        set_input_value(inputs, name, value)

    # Standard homeless shelter deduction (7 USC 2014(e)(6)(D); 10 CCR 2506-1
    # section 4.407.3(C)): a flat deduction replacing the excess-shelter path.
    # The two sub-elections stay False by construction: HOMEDED = 3 is defined
    # as receiving the STANDARD homeless deduction (a verified-higher-costs
    # election would be HOMEDED = 4, which carries its actuals in RENT and
    # takes the ordinary excess-shelter path), and a free-shelter month would
    # have produced no deduction and therefore not HOMEDED = 3.
    set_input_value(
        inputs, "all_household_members_experiencing_homelessness", homeless_claimed
    )
    set_input_value(inputs, "homeless_household_has_shelter_costs", homeless_claimed)
    set_input_value(inputs, "homeless_household_free_shelter_all_month", False)
    set_input_value(inputs, "verified_higher_homeless_shelter_costs", False)

    dependent_care = _money(getattr(unit, "dependent_care_expense", 0) or 0)
    set_input_value(
        inputs,
        "dependent_care_expense_necessary_for_work_or_training",
        dependent_care > 0,
    )
    set_input_value(inputs, "dependent_care_expenses_paid", dependent_care)
    set_input_value(inputs, "dependent_care_reimbursed_or_paid_by_other_program", 0)

    child_support_paid = _money(getattr(unit, "child_support_expense", 0) or 0)
    set_input_value(inputs, "child_support_payment_verified", child_support_paid > 0)
    set_input_value(
        inputs,
        "child_support_payment_history_months",
        3 if child_support_paid > 0 else 0,
    )
    set_input_value(inputs, "average_monthly_child_support_paid", child_support_paid)
    set_input_value(inputs, "estimated_monthly_child_support_paid", child_support_paid)

    # Reconstruct the deduction FNS actually applied. FSMEDDED equals the
    # excess FSMEDEXP in ordinary states, but in standard-medical-deduction
    # demonstration states it is a flat standard that differs from the excess
    # (10 FY2024 rows nationally, none in Colorado), so the applied deduction
    # — not the reported excess — is the operative amount. Feeding it plus the
    # $35 threshold makes the engine's ``total - 35`` reproduce FSMEDDED in
    # both kinds of state.
    applied_medical = getattr(
        getattr(unit, "expected", None), "medical_deduction", None
    )
    if applied_medical is None:
        applied_medical = getattr(unit, "medical_expenses", 0) or 0
    applied_medical = _money(applied_medical)
    set_input_value(
        inputs,
        "total_medical_expenses",
        _money(applied_medical + _MEDICAL_EXCESS_THRESHOLD)
        if applied_medical > 0
        else 0,
    )

    set_input_value(
        inputs, "snap_basic_categorical_eligible", bool(unit.categorically_eligible)
    )
    set_input_value(
        inputs,
        "liquid_resource_current_redemption_rate",
        _money(getattr(unit, "liquid_resources", 0) or 0),
    )

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
        elderly = bool(
            (member.age is not None and member.age >= 60) or member.elderly_or_disabled
        )
        set_input_value(member_dict, "snap_member_is_elderly_or_disabled", elderly)
        member_inputs.append(member_dict)

    entity_id = _entity_id(unit)
    return ProjectedCase(
        spm_unit_id=entity_id,
        household_id=entity_id,
        inputs=inputs,
        member_inputs=member_inputs,
        pe_outputs={},
    )


def _utility_flag_inputs(utility_tier: Any) -> dict[str, bool]:
    """Map a QC utility tier to the seven Colorado utility-cost flags."""
    tier = str(getattr(utility_tier, "value", utility_tier))
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
    rulespec_root: str | Path,
    axiom_binary: str | Path,
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

    rulespec_root = require_rulespec_checkout(Path(rulespec_root), country="us")
    axiom_binary = resolve_axiom_binary(Path(axiom_binary))
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
    base_member = _load_base_member(
        rulespec_root / config.template, config.base.relation_id
    )

    overlay_dir = Path(tempfile.mkdtemp(prefix="snap-qc-overlay-"))
    try:
        build = build_overlay(spec, rulespec_root, overlay_dir)
        # Single self-contained root. The engine unions module ids across roots
        # rather than shadowing, so fronting the monorepo with the overlay would
        # compile both the fy-2024 and fy-2026 cola imports and abort with a
        # duplicate-rule error. The materialized overlay is complete on its own.
        env = axiom_engine_env()
        sua_amount_by_tier = sua_amounts_from_overlay(spec)
        cases = [
            map_qc_unit(
                unit,
                base_inputs,
                base_member,
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
            rulespec_root=build.overlay_root,
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
    rulespec_root: Path,
    env: dict[str, str],
) -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="snap-qc-artifact-") as artifact_dir:
        artifact = Path(artifact_dir) / "program.compiled.json"
        compile_program(
            binary,
            program_path,
            artifact,
            rulespec_root=rulespec_root,
            env=env,
        )
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
) -> dict:
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
            expected_value = _expected_value(label, unit)
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
        "suite": SUITE,
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
            "generated_by": f"axiom_oracles.bridges.snap_qc_compare::{SUITE}",
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
        return (
            abs(round(float(axiom_value)) - round(float(expected_value))) <= tolerance
        )
    return abs(float(axiom_value) - float(expected_value)) <= stage_tolerance


def _first_divergent_stage(matches: dict[str, bool | None]) -> str | None:
    for label in _LABELS:
        if matches.get(label.stage) is False:
            return label.stage
    return None


def _expected_value(label: _Label, unit: Any) -> float | None:
    if label.label == "snap_maximum_allotment":
        return float(_fy2024_max_allotment(unit.certified_size))
    if label.expected_attr is None:
        return None
    value = getattr(unit.expected, label.expected_attr, None)
    if value is None:
        return None
    if label.expected_attr == "gross_income":
        # Colorado elects the 7 USC 2014(e)(4) child-support income exclusion,
        # so the composition removes child support paid from countable gross
        # income; the QC file books the same amount as a deduction instead
        # (FSCSDED; the FSCSEXP codebook entry notes the state split). Net
        # income is identical either way, so the gross comparison nets the
        # QC-recorded deduction out of FSGRINC.
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
    parser.add_argument("--rulespec-root", type=Path, required=True)
    parser.add_argument("--axiom-binary", type=Path, required=True)
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
