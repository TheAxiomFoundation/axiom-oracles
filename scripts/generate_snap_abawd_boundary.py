#!/usr/bin/env python3
"""Generate the SNAP ABAWD post-P.L. 119-21 boundary case-grid report.

Behavioral companion to the structural closure warning recorded in PR #400
(``closure/classifications/a2-usc-1.yaml``): the current 7 U.S.C. 2015(o)(3)
exceptions, as struck and replaced by P.L. 119-21 section 10102(a), materially
differ from the pre-amendment 7 CFR 273.24(c) list.  Closure detection alone
does not verify executable outcomes, so this grid runs the statute boundaries
through both engines:

* ``axiom`` replays the nine post-P.L. 119-21 boundary cases from the
  rulespec-us companion fixture ``us/regulations/7-cfr/273/24.test.yaml``
  (engine-verified in rulespec-us CI at or after the #1212 encoding fix) and
  fails closed unless each replayed verdict equals the pinned legal
  expectation; and
* ``policyengine`` builds a fresh PolicyEngine-US ``Simulation`` per case at
  period 2026-07 under the reviewed 2026 oracle stack and reads
  ``meets_snap_abawd_work_requirements`` for the tested member.

The boundary matrix (each case sets every unrelated exception false; the
negative cases additionally pin zero qualifying work, four countable months,
no waiver, and no regained/additional eligibility so a wrong exception verdict
cannot be masked by another eligibility branch):

===========================  ==========================================
Case                         Expected direct exception verdict
===========================  ==========================================
age 55                       not excepted (P.L. 119-21 ends the FRA 55+
                             phase-in boundary)
age 64                       not excepted, although the age-60 general
                             work exemption of 7 CFR 273.7(b)(1)(i)
                             holds — (o)(3)(D) reaches only the
                             statutory (d)(2) exemptions
age 65                       excepted under the USDA operational reading
                             (FNS OBBBA ABAWD memorandum, 2025-10-03);
                             the statute's literal "over 65" is recorded
                             in the module proof metadata
age 66                       excepted under either reading
age 23, former foster        not excepted — the FRA former-foster-youth
                             branch ended effective 2025-07-04.  The
                             PolicyEngine leg sets ``was_in_foster_care``
                             TRUE to prove the input no longer flips the
                             post-P.L. 119-21 verdict; the Axiom module
                             encodes the repeal by carrying no such fact
qualifying Indian /          excepted — 2015(o)(3)(F)
Urban Indian
California Indian            excepted — 2015(o)(3)(G).  PolicyEngine
                             folds (F) and (G) into the single
                             ``is_snap_abawd_indian_exempt`` input
child aged 13                excepted — responsibility for a dependent
                             child under 14, 2015(o)(3)(C)
child aged 14                not excepted on that basis
===========================  ==========================================

Comparison boundary: Axiom ``snap_member_abawd_exception_applies`` against
PolicyEngine ``meets_snap_abawd_work_requirements``.  Under this grid's
construction the PolicyEngine composite reduces exactly to its 2015(o)(3)
exception set: the work-activity arm reads zero hours and no workfare, the
waiver arm reads the empty default county geography, the discretionary
exemption input defaults false, and PolicyEngine's own documentation states
the no-month-history simplification is exact for members who have already
exhausted their countable months — which the fixture pins at four.  The one
architectural difference is the dependent-child exception: PolicyEngine
implements 2015(o)(3)(C) upstream in ``meets_snap_work_requirements_person``
(routing any member of an SPM unit containing a child under 14 around the
ABAWD test entirely), so its ABAWD composite is expected to stay false on the
child-13 case while Axiom's direct exception holds.  That single residual is
classified in ``dispositions/us-snap-abawd-grid.yaml``;
``meets_snap_work_requirements_person`` is carried per case as a diagnostic so
the routing is visible in the report.

Run through the registry so the reviewed PolicyEngine pins and dashboard
provenance are applied:

    uv run scripts/run_comparison.py us-snap-abawd-grid --summary
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from importlib.metadata import version as distribution_version
from pathlib import Path
from typing import Any, Mapping

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.comparison.dispositions import report_json_text  # noqa: E402

SUITE = "us-snap-abawd-grid"
TITLE = "SNAP ABAWD post-P.L. 119-21 boundaries — Axiom vs PolicyEngine"
VALIDATION_YEAR = 2026
VALIDATION_PERIOD = "2026-07"
ENGINE_VERSIONS = {
    "policyengine": "4.18.9",
    "policyengine_core": "3.30.3",
    "policyengine_us": "1.767.3",
}

MODULE = "us:regulations/7-cfr/273/24"
GENERAL_MODULE = "us:regulations/7-cfr/273/7"
FIXTURE_PATH = Path("us/regulations/7-cfr/273/24.test.yaml")

AXIOM_OUTPUT = f"{MODULE}#snap_member_abawd_exception_applies"
PE_OUTPUT = "meets_snap_abawd_work_requirements"
PE_BOUNDARY = (
    "Person-level ABAWD composite at 2026-07; reduces to the 2015(o)(3) "
    "exception set under this grid's zero-work, months-exhausted, no-waiver "
    "construction (dependent-child exception handled upstream, see "
    "dispositions)"
)

# Axiom-side judgments replayed from the fixture whenever the case asserts
# them; the compared output is validated as present on every case.
AXIOM_DIAGNOSTIC_OUTPUTS = (
    f"{MODULE}#snap_member_abawd_time_limit_inapplicable",
    f"{MODULE}#snap_member_abawd_time_limit_eligible",
    f"{MODULE}#snap_member_abawd_responsible_for_dependent_child_under_fourteen",
    f"{MODULE}#snap_member_work_requirement_eligible",
    f"{MODULE}#snap_member_work_requirement_ineligible",
    f"{GENERAL_MODULE}#snap_member_general_work_requirement_eligible",
    f"{GENERAL_MODULE}#snap_member_general_work_requirement_exempt",
    f"{GENERAL_MODULE}#snap_member_statutory_work_registration_exemption_applies",
)

PE_DIAGNOSTIC_VARIABLES = (
    "meets_snap_work_requirements_person",
    "meets_snap_general_work_requirements",
    "is_snap_abawd_hr1_in_effect",
)

# Exception facts local to the 273.24 module; every fixture case must assign
# all seven so no unrelated exception can carry a verdict.
EXCEPTION_FACTS = (
    "member_medically_certified_physically_or_mentally_unfit_for_employment",
    "member_is_parent_or_household_member_responsible_for_dependent_child",
    "member_is_pregnant",
    "member_is_indian_or_urban_indian",
    "member_is_california_indian",
)

# The downstream construction pinned on every negative case: zero qualifying
# work, more than three countable months, and no regained or additional
# eligibility, so the failed exception is observable end to end.
NEGATIVE_CONSTRUCTION = {
    "member_abawd_weekly_work_hours": 0,
    "member_abawd_monthly_work_hours": 0,
    "member_participates_in_abawd_work_program_20_hours_weekly": False,
    "member_combines_work_and_work_program_20_hours_weekly": False,
    "member_participates_in_abawd_workfare_program": False,
    "snap_abawd_countable_months_in_three_year_period": 4,
    "member_regained_abawd_eligibility": False,
    "member_has_additional_three_month_abawd_eligibility": False,
}

# All cases run in a state that adopted the P.L. 119-21 criteria on the
# federal effective date (California, Hawaii, and Alaska carry delayed
# state-level ``hr1_in_effect`` parameters).
PE_STATE = "TX"


@dataclass(frozen=True)
class BoundaryCase:
    """One statute-boundary case: fixture identity plus its PE projection."""

    case_id: str
    description: str
    age: int
    expected_exception: bool
    child_age: int | None = None
    indian: bool = False
    pe_foster: bool = False


CASES: tuple[BoundaryCase, ...] = (
    BoundaryCase(
        case_id="age_55_subject_to_time_limit_post_hr1",
        description=(
            "Age 55 is inside the post-P.L. 119-21 18-64 band; the FRA-era "
            "55+ age exception no longer applies"
        ),
        age=55,
        expected_exception=False,
    ),
    BoundaryCase(
        case_id="age_64_subject_despite_general_work_exemption",
        description=(
            "Age 64 is ABAWD-subject although the 7 CFR 273.7(b)(1)(i) "
            "age-60 general work exemption holds; 2015(o)(3)(D) reaches "
            "only the statutory (d)(2) exemptions"
        ),
        age=64,
        expected_exception=False,
    ),
    BoundaryCase(
        case_id="age_65_excepted_under_usda_operational_reading",
        description=(
            "Age 65 is excepted under the USDA operational reading of "
            "'under 18, or over 65' (FNS OBBBA ABAWD memorandum, "
            "2025-10-03); the literal statutory wording is recorded in the "
            "module proof metadata"
        ),
        age=65,
        expected_exception=True,
    ),
    BoundaryCase(
        case_id="age_66_excepted_under_either_reading",
        description="Age 66 is excepted under either boundary reading",
        age=66,
        expected_exception=True,
    ),
    BoundaryCase(
        case_id="age_23_no_exception_post_hr1",
        description=(
            "Age 23 with former-foster history: the FRA former-foster-youth "
            "exception ended 2025-07-04.  The PolicyEngine leg sets "
            "was_in_foster_care TRUE to prove the retired input no longer "
            "flips the verdict; the Axiom module encodes the repeal by "
            "carrying no former-foster fact"
        ),
        age=23,
        expected_exception=False,
        pe_foster=True,
    ),
    BoundaryCase(
        case_id="indian_or_urban_indian_excepted",
        description="Qualifying Indian or Urban Indian, 2015(o)(3)(F)",
        age=40,
        expected_exception=True,
        indian=True,
    ),
    BoundaryCase(
        case_id="california_indian_excepted",
        description=(
            "California Indian, 2015(o)(3)(G); PolicyEngine folds (F) and "
            "(G) into the single is_snap_abawd_indian_exempt input"
        ),
        age=40,
        expected_exception=True,
        indian=True,
    ),
    BoundaryCase(
        case_id="abawd_exception_applies_to_responsible_adult_with_child_under_fourteen",
        description=(
            "Responsibility for a dependent child aged 13 — under the "
            "2015(o)(3)(C) age-14 boundary"
        ),
        age=30,
        expected_exception=True,
        child_age=13,
    ),
    BoundaryCase(
        case_id="abawd_no_exception_for_dependent_child_aged_fourteen",
        description=(
            "Responsibility for a dependent child aged 14 — at the "
            "2015(o)(3)(C) boundary, no exception on that basis"
        ),
        age=30,
        expected_exception=False,
        child_age=14,
    ),
)


def _module_input(name: str) -> str:
    return f"{MODULE}#input.{name}"


def _fixture_file(roots: list[Path]) -> Path:
    candidates = [root / FIXTURE_PATH for root in roots]
    matches = [path for path in candidates if path.is_file()]
    if not matches:
        tried = "\n".join(f"  - {path}" for path in candidates)
        raise FileNotFoundError(
            f"{SUITE}: RuleSpec companion fixture not found; tried:\n{tried}"
        )
    if len(matches) > 1:
        choices = "\n".join(f"  - {path}" for path in matches)
        raise RuntimeError(
            f"{SUITE}: fixture is ambiguous across rulespec roots:\n{choices}"
        )
    return matches[0]


def _fixture_records(path: Path) -> dict[str, dict[str, Any]]:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, list) or not all(
        isinstance(record, dict) for record in raw
    ):
        raise ValueError(f"{path}: expected a list of test-case mappings")
    records = {str(record.get("name")): record for record in raw}
    if len(records) != len(raw):
        raise ValueError(f"{path}: duplicate test-case names")
    return records


def _require_input(
    case: BoundaryCase,
    inputs: Mapping[str, Any],
    name: str,
    expected: Any,
) -> None:
    key = _module_input(name)
    if key not in inputs:
        raise ValueError(f"{SUITE}: case {case.case_id!r} does not assign {key}")
    actual = inputs[key]
    if actual != expected or isinstance(actual, bool) != isinstance(expected, bool):
        raise ValueError(
            f"{SUITE}: case {case.case_id!r} assigns {key} = {actual!r}; "
            f"the boundary construction requires {expected!r}"
        )


def _validate_fixture_case(case: BoundaryCase, record: Mapping[str, Any]) -> None:
    """Fail closed unless the fixture case still pins the §2015(o)(3) boundary.

    Verdict drift is a comparison mismatch, but construction drift — a case
    that stops zeroing the unrelated exceptions or the downstream branches —
    would silently turn the matrix vacuous, so the construction is exact.
    """

    if record.get("period") != VALIDATION_PERIOD:
        raise ValueError(
            f"{SUITE}: case {case.case_id!r} runs period "
            f"{record.get('period')!r}; the post-P.L. 119-21 matrix is "
            f"pinned to {VALIDATION_PERIOD}"
        )
    inputs = record.get("input")
    if not isinstance(inputs, Mapping):
        raise ValueError(f"{SUITE}: case {case.case_id!r} has no input mapping")

    foster_facts = [key for key in inputs if "foster" in key.lower()]
    if foster_facts:
        raise ValueError(
            f"{SUITE}: case {case.case_id!r} assigns former-foster facts "
            f"{foster_facts}; P.L. 119-21 removed that exception and the "
            "module must not re-grow the input silently"
        )

    _require_input(case, inputs, "member_age", case.age)
    _require_input(case, inputs, "member_covered_by_abawd_time_limit_waiver", False)
    _require_input(
        case,
        inputs,
        "member_is_parent_or_household_member_responsible_for_dependent_child",
        case.child_age is not None,
    )
    if case.child_age is not None:
        _require_input(
            case, inputs, "member_youngest_dependent_child_age", case.child_age
        )
    indian_facts = {
        "indian_or_urban_indian_excepted": "member_is_indian_or_urban_indian",
        "california_indian_excepted": "member_is_california_indian",
    }
    own_flag = indian_facts.get(case.case_id)
    for fact in EXCEPTION_FACTS:
        if fact == "member_is_parent_or_household_member_responsible_for_dependent_child":
            continue
        _require_input(case, inputs, fact, fact == own_flag)
    if not case.expected_exception:
        for fact, expected in NEGATIVE_CONSTRUCTION.items():
            _require_input(case, inputs, fact, expected)


def _replayed_verdicts(
    case: BoundaryCase,
    record: Mapping[str, Any],
) -> tuple[bool, dict[str, bool]]:
    outputs = record.get("output")
    if not isinstance(outputs, Mapping):
        raise ValueError(f"{SUITE}: case {case.case_id!r} has no output mapping")
    verdicts: dict[str, bool] = {}
    for concept, verdict in outputs.items():
        if verdict not in ("holds", "not_holds"):
            raise ValueError(
                f"{SUITE}: case {case.case_id!r} output {concept} has "
                f"non-boolean verdict {verdict!r}"
            )
        verdicts[str(concept)] = verdict == "holds"
    if AXIOM_OUTPUT not in verdicts:
        raise ValueError(
            f"{SUITE}: case {case.case_id!r} does not assert {AXIOM_OUTPUT}"
        )
    compared = verdicts.pop(AXIOM_OUTPUT)
    if compared != case.expected_exception:
        raise ValueError(
            f"{SUITE}: case {case.case_id!r} replays "
            f"{AXIOM_OUTPUT} = {compared}, but the pinned P.L. 119-21 "
            f"boundary expectation is {case.expected_exception} — the "
            "rulespec-us encoding has moved off the statute boundary"
        )
    diagnostics = {
        concept: value
        for concept, value in verdicts.items()
        if concept in AXIOM_DIAGNOSTIC_OUTPUTS
    }
    return compared, diagnostics


def _axiom_values(
    roots: list[Path],
) -> tuple[dict[str, bool], dict[str, dict[str, bool]], dict[str, dict[str, Any]]]:
    fixture = _fixture_file(roots)
    records = _fixture_records(fixture)
    missing = sorted(
        case.case_id for case in CASES if case.case_id not in records
    )
    if missing:
        raise ValueError(
            f"{SUITE}: fixture {fixture} lacks boundary cases {missing}"
        )
    values: dict[str, bool] = {}
    diagnostics: dict[str, dict[str, bool]] = {}
    module_inputs: dict[str, dict[str, Any]] = {}
    for case in CASES:
        record = records[case.case_id]
        _validate_fixture_case(case, record)
        compared, case_diagnostics = _replayed_verdicts(case, record)
        values[case.case_id] = compared
        diagnostics[case.case_id] = case_diagnostics
        module_inputs[case.case_id] = {
            key.split("#input.", 1)[1]: value
            for key, value in record["input"].items()
            if key.startswith(f"{MODULE}#input.")
        }
    return values, diagnostics, module_inputs


def _pe_situation(case: BoundaryCase) -> dict[str, Any]:
    member: dict[str, Any] = {
        "age": {VALIDATION_YEAR: case.age},
        # PolicyEngine's hours input defaults to full-time (default_value =
        # 40); the boundary construction pins zero qualifying work so the
        # work-activity arm cannot carry the composite.
        "weekly_hours_worked_before_lsr": {VALIDATION_YEAR: 0},
    }
    if case.indian:
        member["is_snap_abawd_indian_exempt"] = {VALIDATION_YEAR: True}
    if case.pe_foster:
        member["was_in_foster_care"] = {VALIDATION_YEAR: True}
    people: dict[str, Any] = {"member": member}
    members = ["member"]
    if case.child_age is not None:
        people["child"] = {
            "age": {VALIDATION_YEAR: case.child_age},
            "is_tax_unit_dependent": {VALIDATION_YEAR: True},
            "weekly_hours_worked_before_lsr": {VALIDATION_YEAR: 0},
        }
        members.append("child")
    return {
        "people": people,
        "tax_units": {"tax_unit": {"members": members}},
        "families": {"family": {"members": members}},
        "spm_units": {"spm_unit": {"members": members}},
        "households": {
            "household": {
                "members": members,
                "state_code": {VALIDATION_YEAR: PE_STATE},
            }
        },
    }


def _verify_pe_parameters(tax_benefit_system: Any) -> None:
    """Pin the oracle's own statute boundaries before trusting its verdicts.

    The exempted-age brackets must flip from the FRA 55+ boundary to the
    P.L. 119-21 band exactly at the 2025-07-04 effective date, the
    dependent-child threshold must fall 18 -> 14, and the federal
    ``in_effect`` switch must be on at the validation period (and off just
    before enactment, so the pre-HR1 snapshot the formulas read is real).
    """

    at = tax_benefit_system.parameters
    post = at(f"{VALIDATION_PERIOD}-01").gov.usda.snap.work_requirements.abawd
    pre = at("2025-06-01").gov.usda.snap.work_requirements.abawd
    checks = [
        ("in_effect at 2026-07", post.in_effect, True),
        ("in_effect at 2025-06", pre.in_effect, False),
        ("dependent threshold at 2026-07", post.age_threshold.dependent, 14),
        ("dependent threshold at 2025-06", pre.age_threshold.dependent, 18),
        ("exempted at age 17", bool(post.age_threshold.exempted.calc(17)), True),
        ("exempted at age 55", bool(post.age_threshold.exempted.calc(55)), False),
        ("exempted at age 64", bool(post.age_threshold.exempted.calc(64)), False),
        ("exempted at age 65", bool(post.age_threshold.exempted.calc(65)), True),
        ("exempted at age 66", bool(post.age_threshold.exempted.calc(66)), True),
        ("pre-HR1 exempted at age 55", bool(pre.age_threshold.exempted.calc(55)), True),
        ("pre-HR1 former-foster age", pre.age_threshold.former_foster_care, 24),
    ]
    for label, actual, expected in checks:
        if actual != expected:
            raise RuntimeError(
                f"{SUITE}: PolicyEngine parameter check failed — {label} is "
                f"{actual!r}, expected {expected!r}"
            )


def _pe_values(
    cases: tuple[BoundaryCase, ...],
) -> tuple[dict[str, bool], dict[str, dict[str, bool]]]:
    actual_versions = {
        "policyengine": distribution_version("policyengine"),
        "policyengine_core": distribution_version("policyengine-core"),
        "policyengine_us": distribution_version("policyengine-us"),
    }
    if actual_versions != ENGINE_VERSIONS:
        raise RuntimeError(
            f"{SUITE}: runtime PolicyEngine stack {actual_versions} does not "
            f"match reviewed stack {ENGINE_VERSIONS}"
        )
    from policyengine_us import Simulation

    values: dict[str, bool] = {}
    diagnostics: dict[str, dict[str, bool]] = {}
    parameters_verified = False
    for case in cases:
        simulation = Simulation(situation=_pe_situation(case))
        if not parameters_verified:
            _verify_pe_parameters(simulation.tax_benefit_system)
            parameters_verified = True
        computed = simulation.calculate(PE_OUTPUT, VALIDATION_PERIOD)
        expected_people = 1 if case.child_age is None else 2
        if len(computed) != expected_people:
            raise RuntimeError(
                f"{SUITE}: case {case.case_id!r} computed {len(computed)} "
                f"person values; expected {expected_people}"
            )
        values[case.case_id] = bool(computed[0])
        diagnostics[case.case_id] = {
            variable: bool(
                simulation.calculate(variable, VALIDATION_PERIOD)[0]
            )
            for variable in PE_DIAGNOSTIC_VARIABLES
        }
    return values, diagnostics


def _assert_non_vacuous(
    axiom: Mapping[str, bool],
    policyengine: Mapping[str, bool],
) -> None:
    """Both engines must produce both verdict directions across the grid.

    A constant-True or constant-False engine would still 'agree' with part of
    the matrix; requiring both directions on each side keeps the boundary
    comparison non-degenerate (the same both-directions rule the sanity
    fixtures document).
    """

    for engine, values in (("axiom", axiom), ("policyengine", policyengine)):
        observed = set(values.values())
        if observed != {True, False}:
            raise RuntimeError(
                f"{SUITE}: {engine} produced only {sorted(observed)!r} across "
                "the boundary grid; the comparison would be degenerate"
            )


def _build_report(
    axiom: Mapping[str, bool],
    axiom_diagnostics: Mapping[str, Mapping[str, bool]],
    module_inputs: Mapping[str, Mapping[str, Any]],
    policyengine: Mapping[str, bool],
    pe_diagnostics: Mapping[str, Mapping[str, bool]],
) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    match_count = 0
    left_positive = 0
    right_positive = 0
    for case in CASES:
        axiom_value = axiom[case.case_id]
        pe_value = policyengine[case.case_id]
        matched = axiom_value == pe_value
        match_count += int(matched)
        left_positive += int(axiom_value)
        right_positive += int(pe_value)
        case_report: dict[str, Any] = {
            "case_id": case.case_id,
            "description": case.description,
            "concept": AXIOM_OUTPUT,
            "period": VALIDATION_PERIOD,
            "inputs": {
                "module_inputs": dict(module_inputs[case.case_id]),
                "policyengine_only": {
                    # PolicyEngine's hours input defaults to full-time;
                    # zeroed to mirror the fixture's zero-work construction.
                    "weekly_hours_worked_before_lsr": 0,
                    **({"was_in_foster_care": True} if case.pe_foster else {}),
                },
                "state_code": PE_STATE,
            },
            "axiom": axiom_value,
            "policyengine": pe_value,
            "matched": matched,
            "axiom_diagnostics": dict(axiom_diagnostics[case.case_id]),
            "policyengine_diagnostics": dict(pe_diagnostics[case.case_id]),
        }
        cases.append(case_report)
        if not matched:
            mismatches.append(
                {
                    "case_id": case.case_id,
                    "concept": AXIOM_OUTPUT,
                    "kind": "judgment_difference",
                    "engines": ["axiom", "policyengine"],
                    "left_engine": "axiom",
                    "right_engine": "policyengine",
                    "left": axiom_value,
                    "right": pe_value,
                }
            )
    comparison_count = len(cases)
    mismatch_count = len(mismatches)
    match_rate = 100.0 * match_count / comparison_count
    aggregate = {
        "concept": AXIOM_OUTPUT,
        "comparison": "judgment",
        "comparison_count": comparison_count,
        "match_count": match_count,
        "mismatch_count": mismatch_count,
        "compared": comparison_count,
        "matched": match_count,
        "mismatched": mismatch_count,
        "match_rate": match_rate,
        "left_positive_rate": 100.0 * left_positive / comparison_count,
        "right_positive_rate": 100.0 * right_positive / comparison_count,
    }
    return {
        "schema_version": "axiom.comparison_report.v2",
        "suite": SUITE,
        "concept": AXIOM_OUTPUT,
        "population": "case-grid",
        "validation_year": VALIDATION_YEAR,
        "validation_period": VALIDATION_PERIOD,
        "engines": {
            "left": "axiom",
            "right": "policyengine",
            "versions": dict(ENGINE_VERSIONS),
        },
        "engine_bindings": {
            "axiom": {
                "module": MODULE,
                "output": AXIOM_OUTPUT,
                "outputs": [AXIOM_OUTPUT],
                "fixture": str(FIXTURE_PATH),
                "diagnostic_outputs": list(AXIOM_DIAGNOSTIC_OUTPUTS),
            },
            "policyengine": {
                "outputs": [PE_OUTPUT],
                "diagnostic_outputs": list(PE_DIAGNOSTIC_VARIABLES),
                "boundary": PE_BOUNDARY,
            },
        },
        "case_count": comparison_count,
        "scenario_count": comparison_count,
        "concepts": [
            {
                "id": AXIOM_OUTPUT,
                "description": TITLE,
                "category": "benefits",
                "comparison": "judgment",
                "priority": "high",
                "components": [],
                "parent": None,
            }
        ],
        "aggregates": [aggregate],
        "summary": {
            "comparison_count": comparison_count,
            "match_count": match_count,
            "mismatch_count": mismatch_count,
            "error_count": 0,
            "errors_by_engine": {},
            "mismatches_by_concept": (
                [{"value": AXIOM_OUTPUT, "count": mismatch_count}]
                if mismatch_count
                else []
            ),
            "mismatches_by_kind": (
                [{"value": "judgment_difference", "count": mismatch_count}]
                if mismatch_count
                else []
            ),
            "mismatches_by_scenario": {},
            "axiom_vs_policyengine_match_rate": match_rate,
        },
        "mismatches": mismatches,
        "cases": cases,
    }


def generate(roots: list[Path]) -> dict[str, Any]:
    if not roots:
        raise ValueError("at least one --rulespec-root is required")
    axiom, axiom_diagnostics, module_inputs = _axiom_values(roots)
    policyengine, pe_diagnostics = _pe_values(CASES)
    _assert_non_vacuous(axiom, policyengine)
    return _build_report(
        axiom,
        axiom_diagnostics,
        module_inputs,
        policyengine,
        pe_diagnostics,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rulespec-root",
        action="append",
        type=Path,
        default=[],
        help="RuleSpec checkout root; repeatable and supplied by comparison YAML",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = generate([root.resolve() for root in args.rulespec_root])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report_json_text(report))
    summary = report["summary"]
    print(
        f"{report['suite']}: {summary['match_count']}/{report['case_count']} "
        f"matches ({summary['axiom_vs_policyengine_match_rate']:.2f}%)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
