"""Colorado FY2024 SNAP raw-facts simulation artifact driver.

This module is deliberately separate from :mod:`snap_qc_compare`.  The latter
is the certified QC comparison bridge and must remain byte-identical.  This
driver reuses its stable loading, projection, overlay, and engine seams, then
overrides only the Colorado facts approved for the Stage-A diagnostic.

The output is a counterfactual-simulation artifact, never an oracle report.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import os
import subprocess
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import yaml

from . import snap_qc_compare as certified
from .rulespec_overlay import (
    OverlaySpec,
    ParameterPatch,
    build_overlay,
    load_overlay_spec,
    rewrite_output_ids,
)
from .snap_populace import (
    ProjectedCase,
    axiom_rules_env,
    compile_program,
    load_base_inputs,
    month_period,
    output_to_python,
    outputs_by_reference,
    run_axiom_cases,
    set_input_value,
)


ARTIFACT_SCHEMA = "axiom.snap_qc_simulation.v1"
MANIFEST_SCHEMA = "axiom.snap_qc_simulation_manifest.v1"
ARTIFACT_CLASS_LABEL = (
    "counterfactual simulation artifact — not an oracle report; produced on a "
    "certified pinned toolchain with a locally modified input bridge "
    "(raw-facts mode)"
)
COMPOSITION_VARIANT_LABEL = (
    "simulation composition variant — not a candidate encoding change"
)
JURISDICTION = "us-co"
FISCAL_YEAR = 2024
EXPECTED_CASE_COUNT = 856
EXPECTED_CERTIFIED_CELLS = 5_136
SMD_CENSORED_VALUE = 165
SMD_CENSORED_CASE_COUNT = 46
SMD_DONOR_CASE_COUNT = 7
SMD_ZERO_CASE_COUNT = 803
SMD_PARAMETER_FILE = "us-co/regulations/10-ccr-2506-1/4.407.61.yaml"
SMD_PARAMETER_RULE = "snap_state_sme_flat_amount"
COMPOSITION_ADAPTER_FILE = "us-co/policies/cdhs/snap/fy-2026-benefit-calculation.yaml"
COMPOSITION_ADAPTER_RULE = "snap_total_medical_expenses"
COMPOSITION_ADAPTER_FROM = "total_medical_expenses"
COMPOSITION_ADAPTER_TO = (
    "if medical_deduction > 0:\n"
    "    medical_deduction + snap_medical_expense_threshold\n"
    "else: 0"
)
ROUND1_BASELINE_CASES_SHA256 = (
    "a46de9dc09107a69f710580b80ee069a8e3050fd403d1b67d0197d12b06aaaa5"
)
POINT_LOGNORMAL_MU = 4.01472265193314
POINT_LOGNORMAL_SIGMA = 0.959967962318517
POINT_CONDITIONAL_MEAN = 57.4207275695204

ASSUMPTION_STATEMENTS = {
    "floor": (
        "For each of the 46 cases identified by MED_DED_DEMO = 1 and public "
        "FSMEDEXP = $165, assume the unrecoverable pre-recode allowable "
        "medical-expense excess above $35 was $1, the minimum positive "
        "whole-dollar amount consistent with the QC minimodel condition "
        "0 < excess <= $165. The engine therefore receives $36 in total "
        "medical expenses and, with Colorado's SMD set to $0, computes a $1 "
        "actual-excess medical deduction."
    ),
    "point": (
        "For each of the 46 cases identified by MED_DED_DEMO = 1 and public "
        "FSMEDEXP = $165, assume the unrecoverable pre-recode allowable "
        "medical-expense excess above $35 was $57. This is the nearest whole "
        "dollar to the $57.4207276 conditional mean E[X | 0 < X <= $165] "
        "from an HWGT-weighted left-censored lognormal maximum-likelihood fit "
        "to the 46 censored Colorado records and the seven exact non-recoded "
        "Colorado excesses above $165 ($175, $200, $227, $314, $314, $360, "
        "$470; ln-dollar mu = 4.014722652 and sigma = 0.959967962). The "
        "engine therefore receives $92 in total medical expenses and, with "
        "Colorado's SMD set to $0, computes a $57 actual-excess medical "
        "deduction. This point estimate is a deterministic parametric "
        "imputation, not recovery of the censored actuals."
    ),
    "ceiling": (
        "For each of the 46 cases identified by MED_DED_DEMO = 1 and public "
        "FSMEDEXP = $165, assume the unrecoverable pre-recode allowable "
        "medical-expense excess above $35 was $165, the maximum amount "
        "consistent with the QC minimodel condition 0 < excess <= $165. The "
        "engine therefore receives $200 in total medical expenses and, with "
        "Colorado's SMD set to $0, computes a $165 actual-excess medical "
        "deduction."
    ),
}
ASSUMED_CENSORED_EXCESS = {"floor": 1, "point": 57, "ceiling": 165}


# These are all inside the pinned Colorado composition closure.  The six
# certified comparison labels are added separately so their COLA ids receive
# the base overlay's FY2024 rewrite.
EXTRA_OUTPUT_IDS = {
    "categorical_resource_exemption": (
        "us-co:regulations/10-ccr-2506-1/4.408"
        "#snap_categorically_eligible_for_resource_exemption"
    ),
    "child_support_deduction": (
        "us-co:regulations/10-ccr-2506-1/4.407.5#child_support_deduction"
    ),
    "co_expanded_categorical_gross_income_limit": (
        "us-co:regulations/10-ccr-2506-1/4.401.1"
        "#co_snap_expanded_categorical_gross_income_limit"
    ),
    "dependent_care_deduction": (
        "us-co:regulations/10-ccr-2506-1/4.407.4#dependent_care_deduction"
    ),
    "federal_medical_deduction": (
        "us:regulations/7-cfr/273/10#snap_excess_medical_deduction_for_net_income"
    ),
    "federal_medical_surface": (
        "us-co:policies/cdhs/snap/fy-2026-benefit-calculation"
        "#snap_total_medical_expenses"
    ),
    "medical_deduction": ("us-co:regulations/10-ccr-2506-1/4.407.61#medical_deduction"),
    "medical_excess": ("us-co:regulations/10-ccr-2506-1/4.407.6#medical_excess"),
    "passes_gross_income_test": (
        "us-co:regulations/10-ccr-2506-1/4.401#passes_gross_income_test"
    ),
    "snap_basic_utility_allowance_eligible": (
        "us-co:regulations/10-ccr-2506-1/4.407.31#snap_basic_utility_allowance_eligible"
    ),
    "snap_countable_financial_resources": (
        "us-co:regulations/10-ccr-2506-1/4.408#snap_countable_financial_resources"
    ),
    "snap_eligible": (
        "us-co:policies/cdhs/snap/fy-2026-benefit-calculation#snap_eligible"
    ),
    "snap_financial_resources_within_limit": (
        "us:regulations/7-cfr/273/8#snap_financial_resources_within_limit"
    ),
    "snap_heating_cooling_utility_allowance_eligible": (
        "us-co:regulations/10-ccr-2506-1/4.407.31"
        "#snap_heating_cooling_utility_allowance_eligible"
    ),
    "snap_income_eligible": (
        "us-co:regulations/10-ccr-2506-1/4.401#snap_income_eligible"
    ),
    "snap_individual_utility_allowance": (
        "us-co:regulations/10-ccr-2506-1/4.407.31#snap_individual_utility_allowance"
    ),
    "snap_limited_utility_allowance": (
        "us-co:regulations/10-ccr-2506-1/4.407.31#snap_limited_utility_allowance"
    ),
    "snap_one_utility_allowance": (
        "us-co:regulations/10-ccr-2506-1/4.407.31#snap_one_utility_allowance"
    ),
    "snap_one_utility_allowance_eligible": (
        "us-co:regulations/10-ccr-2506-1/4.407.31#snap_one_utility_allowance_eligible"
    ),
    "snap_resource_eligible": ("us:regulations/7-cfr/273/8#snap_resource_eligible"),
    "snap_resource_limit_categorical_exemption_applies": (
        "us:regulations/7-cfr/273/8#snap_resource_limit_categorical_exemption_applies"
    ),
    "snap_standard_utility_allowance": (
        "us-co:regulations/10-ccr-2506-1/4.407.31#snap_standard_utility_allowance"
    ),
    "snap_telephone_allowance_eligible": (
        "us-co:regulations/10-ccr-2506-1/4.407.31#snap_telephone_allowance_eligible"
    ),
}

UTILITY_AMOUNT_LABELS = (
    "snap_standard_utility_allowance",
    "snap_limited_utility_allowance",
    "snap_one_utility_allowance",
    "snap_individual_utility_allowance",
)


def _default_workspace() -> Path:
    return Path(__file__).resolve().parents[3]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_head(path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _clean(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    number = round(float(value), 6)
    if number.is_integer():
        return int(number)
    return number


def _raw_number(unit: Any, name: str) -> int | float | None:
    text = str(unit.raw.get(name, "")).strip()
    if not text or text == ".":
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return _clean(number)


def _raw_int(unit: Any, name: str) -> int | None:
    value = _raw_number(unit, name)
    return None if value is None else int(value)


def _json_bytes(value: Any, *, pretty: bool = False) -> bytes:
    if pretty:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
    else:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    return (text + "\n").encode("utf-8")


def _jsonl_bytes(rows: Iterable[dict[str, Any]]) -> bytes:
    return b"".join(_json_bytes(row) for row in rows)


def _overlay_dict(spec: OverlaySpec) -> dict[str, Any]:
    return {
        "module_id_rewrites": dict(spec.module_id_rewrites),
        "name": spec.name,
        "notes": spec.notes,
        "parameter_patches": [
            dataclasses.asdict(patch) for patch in spec.parameter_patches
        ],
        "program": spec.program,
        "rewrite_files": list(spec.rewrite_files),
    }


def _apply_composition_adapter(build: Any) -> Any:
    """Bind Colorado's medical deduction into 273.10 in the overlay only."""
    target = build.overlay_root / COMPOSITION_ADAPTER_FILE
    source = Path(build.provenance["rulespec_root"]) / COMPOSITION_ADAPTER_FILE
    if not target.exists() or not source.exists():
        raise RuntimeError("composition adapter target or source is missing")

    source_sha256 = _sha256(source)
    before_sha256 = _sha256(target)
    text = target.read_text(encoding="utf-8")
    rule_marker = f"- name: {COMPOSITION_ADAPTER_RULE}\n"
    if text.count(rule_marker) != 1:
        raise RuntimeError(
            f"expected exactly one {COMPOSITION_ADAPTER_RULE} rule in "
            f"{COMPOSITION_ADAPTER_FILE}"
        )
    start = text.index(rule_marker)
    end = text.find("\n- name: ", start + len(rule_marker))
    if end < 0:
        end = len(text)
    rule_text = text[start:end]
    old_formula = "    formula: |-\n      " + COMPOSITION_ADAPTER_FROM
    new_formula = "    formula: |-\n" + "\n".join(
        f"      {line}" for line in COMPOSITION_ADAPTER_TO.splitlines()
    )
    if rule_text.count(old_formula) != 1:
        raise RuntimeError(
            f"{COMPOSITION_ADAPTER_FILE}#{COMPOSITION_ADAPTER_RULE} did not "
            f"have the expected formula {COMPOSITION_ADAPTER_FROM!r}"
        )
    adapted_rule = rule_text.replace(old_formula, new_formula, 1)
    adapted_text = text[:start] + adapted_rule + text[end:]

    # Materialized overlays use hardlinks for untouched files. Always replace
    # through a fresh inode, even though this program was already unlinked by
    # the FY2024 module-id rewrite.
    temp = target.with_name(target.name + ".composition-adapter-tmp")
    temp.write_text(adapted_text, encoding="utf-8")
    os.replace(temp, target)
    if _sha256(source) != source_sha256:
        raise RuntimeError("composition adapter mutated the source RuleSpec checkout")

    after_sha256 = _sha256(target)
    file_sha256 = dict(build.provenance["file_sha256"])
    file_sha256[COMPOSITION_ADAPTER_FILE] = after_sha256
    variant = {
        "candidate_encoding_change": False,
        "file": COMPOSITION_ADAPTER_FILE,
        "label": COMPOSITION_VARIANT_LABEL,
        "materialized_file_sha256_after": after_sha256,
        "materialized_file_sha256_before": before_sha256,
        "rule": COMPOSITION_ADAPTER_RULE,
        "source_checkout_file_sha256": source_sha256,
        "source_checkout_modified": False,
        "structural_patch": {
            "from": COMPOSITION_ADAPTER_FROM,
            "to": COMPOSITION_ADAPTER_TO,
        },
    }
    provenance = dict(build.provenance)
    provenance["file_sha256"] = dict(sorted(file_sha256.items()))
    provenance["simulation_composition_variant"] = variant
    return dataclasses.replace(build, provenance=provenance)


def _materialized_parameter_formula(build: Any, *, file: str, rule: str) -> str:
    data = yaml.safe_load((build.overlay_root / file).read_text(encoding="utf-8"))
    for entry in data.get("rules", []):
        if entry.get("name") == rule:
            versions = entry.get("versions") or []
            if len(versions) != 1 or "formula" not in versions[0]:
                raise RuntimeError(f"unexpected versions for {file}#{rule}")
            return str(versions[0]["formula"])
    raise RuntimeError(f"missing materialized parameter {file}#{rule}")


def _output_ids(spec: OverlaySpec) -> dict[str, str]:
    config = certified.QC_JURISDICTIONS[JURISDICTION]
    output_ids = certified._output_id_by_label(config, spec.module_id_rewrites)
    extras = rewrite_output_ids(EXTRA_OUTPUT_IDS, spec.module_id_rewrites)
    overlap = set(output_ids) & set(extras)
    if overlap:
        raise ValueError(f"duplicate output labels: {sorted(overlap)}")
    output_ids.update(extras)
    return dict(sorted(output_ids.items()))


def _categorical_inputs(unit: Any) -> tuple[bool, bool]:
    """Preserve the recorded categorical type, then exercise CO's path.

    CAT_ELIG=1/3 is projected as basic categorical and CAT_ELIG=2 as expanded
    categorical.  The recorded type remains a QC-derived entitlement fact: the
    public file cannot derive all of 4.206's TANF/MOE and disqualification
    antecedents.  Unlike the certified bridge, this does not collapse every
    positive code to the basic path; expanded cases therefore face 4.401.1's
    encoded 200%-FPL gross-income limit.
    """
    code = _raw_int(unit, "CAT_ELIG")
    if code not in (0, 1, 2, 3, None):
        raise ValueError(f"{unit.case_id}: unknown CAT_ELIG code {code}")
    return code in (1, 3), code == 2


def _is_smd_censored(unit: Any) -> bool:
    return (
        _raw_int(unit, "MED_DED_DEMO") == 1
        and _raw_number(unit, "FSMEDEXP") == SMD_CENSORED_VALUE
    )


def _medical_total_from_public_excess(
    unit: Any, *, excess_override: float | None = None
) -> float:
    """Translate FSMEDEXP's documented excess amount to the engine input.

    The RuleSpec input is *total* medical expense and its rule subtracts $35.
    The PUF's FSMEDEXP is already the amount in excess of $35, so a positive
    value is translated back to total by adding $35.  This is a schema-unit
    conversion, not recovery of unedited actual expenses: the QC minimodel has
    already replaced 46 Colorado sub-threshold actuals with the $165 SMD.
    """
    excess = (
        float(excess_override)
        if excess_override is not None
        else float(getattr(unit, "medical_expenses", 0) or 0)
    )
    return excess + 35 if excess > 0 else 0.0


def map_raw_facts_case(
    unit: Any,
    base_inputs: dict[str, Any],
    base_member: dict[str, Any],
    *,
    config: Any,
    sua_amount_by_tier: dict[str, dict[str, float]],
    medical_excess_override: float | None = None,
) -> ProjectedCase:
    """Project one CO unit without FSMEDDED, FSCSDED, or numeric UTIL."""
    case = certified.map_qc_unit(
        unit,
        base_inputs,
        base_member,
        config=config,
        sua_amount_by_tier=sua_amount_by_tier,
    )
    inputs = dict(case.inputs)

    # Numeric UTIL is diagnostic only.  RENT remains the incurred shelter cost;
    # SUA1 selects witness facts and the encoding selects the FY2024 amount.
    set_input_value(
        inputs,
        "household_shelter_costs_incurred",
        float(getattr(unit, "shelter_expense", 0) or 0),
    )
    tier = str(getattr(unit.utility_tier, "value", unit.utility_tier))
    if bool(getattr(unit, "homeless_deduction_claimed", False)):
        # The standard homeless flat deduction replaces the ordinary excess-
        # shelter path.  Preserve the certified bridge's no-utility behavior
        # to avoid introducing an allowance into that replaced path.
        tier_for_engine = "none"
    else:
        tier_for_engine = tier
    utility_flags = certified._utility_flag_inputs(
        JURISDICTION,
        tier_for_engine,
        certified.STATEWIDE if tier_for_engine != "none" else None,
    )
    for name, value in utility_flags.items():
        set_input_value(inputs, name, value)

    # FSMEDEXP, not FSMEDDED, is now the sole medical amount source.
    set_input_value(
        inputs,
        "total_medical_expenses",
        _medical_total_from_public_excess(
            unit,
            excess_override=medical_excess_override,
        ),
    )

    # FSCSEXP is the sole child-support amount source.  Verification and
    # history are not public; the positive recorded amount is projected as a
    # verified three-month average (also supplied as the estimate).
    child_support = float(getattr(unit, "child_support_expense", 0) or 0)
    set_input_value(inputs, "child_support_payment_verified", child_support > 0)
    set_input_value(
        inputs,
        "child_support_payment_history_months",
        3 if child_support > 0 else 0,
    )
    set_input_value(inputs, "average_monthly_child_support_paid", child_support)
    set_input_value(inputs, "estimated_monthly_child_support_paid", child_support)

    # LIQRESOR is explicitly re-projected here.  It is a QC-constructed
    # countable amount, not the unedited RAWLQRES field; the manifest says so.
    set_input_value(
        inputs,
        "liquid_resource_current_redemption_rate",
        float(getattr(unit, "liquid_resources", 0) or 0),
    )
    basic, expanded = _categorical_inputs(unit)
    set_input_value(inputs, "snap_basic_categorical_eligible", basic)
    set_input_value(inputs, "snap_expanded_categorical_eligible", expanded)

    return ProjectedCase(
        spm_unit_id=case.spm_unit_id,
        household_id=case.household_id,
        inputs=inputs,
        member_inputs=case.member_inputs,
        pe_outputs=case.pe_outputs,
    )


def _run_batches(
    *,
    binary: Path,
    artifact: Path,
    cases: list[ProjectedCase],
    period: Any,
    output_ids: list[str],
    config: Any,
    env: dict[str, str],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for start in range(0, len(cases), certified.CHUNK_SIZE):
        results.extend(
            run_axiom_cases(
                binary=binary,
                artifact=artifact,
                cases=cases[start : start + certified.CHUNK_SIZE],
                period=period,
                output_ids=output_ids,
                relation_id=config.base.relation_id,
                additional_relation_ids=config.base.additional_relation_ids,
                member_entity_type=config.base.member_entity_type,
                env=env,
            )
        )
    return results


def _extract_outputs(
    result: dict[str, Any], output_id_by_label: dict[str, str]
) -> dict[str, Any]:
    references = outputs_by_reference(result.get("outputs", {}))
    values: dict[str, Any] = {}
    for label, output_id in output_id_by_label.items():
        output = references.get(output_id)
        if not isinstance(output, dict):
            raise RuntimeError(f"engine result is missing requested output {output_id}")
        values[label] = _clean(output_to_python(output))
    return values


def _equal(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is right
    try:
        return abs(float(left) - float(right)) <= 1e-9
    except (TypeError, ValueError):
        return left == right


def _expected_stages(unit: Any) -> dict[str, Any]:
    expected: dict[str, Any] = {}
    for label in certified._LABELS:
        expected[label.label] = _clean(
            certified._expected_value(
                label,
                unit,
                child_support_convention="exclusion",
            )
        )
    return expected


def _source_facts(unit: Any) -> dict[str, Any]:
    names = (
        "CAT_ELIG",
        "FSCSEXP",
        "FSCSDED",
        "FSMEDEXP",
        "FSMEDDED",
        "HOMEDED",
        "LIQRESOR",
        "MED_DED_DEMO",
        "PURE_PA",
        "RAWLQRES",
        "SUA1",
        "SUA2",
        "UTIL",
    )
    return {name: _raw_number(unit, name) for name in names}


def _driver_classes(
    unit: Any, outputs: dict[str, Any], expected: dict[str, Any]
) -> list[str]:
    drivers: list[str] = []
    if not _equal(outputs["medical_deduction"], unit.expected.medical_deduction):
        drivers.append("medical_derivation_gap")
    if not _equal(outputs["federal_medical_deduction"], outputs["medical_deduction"]):
        drivers.append("medical_benefit_path_gap")
    if not _equal(
        outputs["child_support_deduction"], unit.expected.child_support_deduction
    ):
        drivers.append("child_support_derivation_gap")

    encoded_utility = sum(float(outputs[label] or 0) for label in UTILITY_AMOUNT_LABELS)
    # HOMEDED=3 takes the replacement flat shelter path; its recorded utility
    # amount is not an operative stage driver in the composition.
    expected_utility = (
        0
        if bool(getattr(unit, "homeless_deduction_claimed", False))
        else float(getattr(unit, "utility_amount", 0) or 0)
    )
    if not _equal(encoded_utility, expected_utility):
        drivers.append("utility_tier_amount_gap")

    if (
        _raw_int(unit, "CAT_ELIG") == 2
        and outputs["passes_gross_income_test"] == "not_holds"
    ):
        drivers.append("categorical_200pct_path")
    if not _equal(
        outputs["snap_countable_financial_resources"],
        getattr(unit, "liquid_resources", 0) or 0,
    ):
        drivers.append("resource_derivation_gap")
    return sorted(drivers)


def _row(
    unit: Any, result: dict[str, Any], output_ids: dict[str, str]
) -> dict[str, Any]:
    outputs = _extract_outputs(result, output_ids)
    expected = _expected_stages(unit)
    stage_agreement = {
        label.label: _equal(outputs[label.label], expected[label.label])
        for label in certified._LABELS
    }
    first_divergent_stage = next(
        (
            label.stage
            for label in certified._LABELS
            if not stage_agreement[label.label]
        ),
        None,
    )
    source_facts = _source_facts(unit)
    identification_flags: list[str] = []
    if (
        source_facts["MED_DED_DEMO"] == 1
        and source_facts["FSMEDEXP"] == SMD_CENSORED_VALUE
    ):
        identification_flags.append("smd_actual_expense_censored")
    return {
        # Preserve the public file's source precision.  Rounding each case
        # before aggregation makes scenario-level weighted totals depend on
        # whether they were computed from rows or directly from the loader.
        "HWGT": getattr(unit, "weight", None),
        "YRMONTH": int(unit.yrmonth),
        "artifact_class": ARTIFACT_CLASS_LABEL,
        "benefit": outputs["snap_regular_month_allotment"],
        "case_id": str(unit.case_id),
        "driver_classes": _driver_classes(unit, outputs, expected),
        "first_divergent_stage": first_divergent_stage,
        "identification_flags": identification_flags,
        "outputs": outputs,
        "qc_expected": expected,
        "source_facts": source_facts,
        "stage_agreement": stage_agreement,
    }


DELTA_OUTPUT_LABELS = (
    "medical_excess",
    "medical_deduction",
    "federal_medical_surface",
    "federal_medical_deduction",
    "snap_excess_shelter_deduction",
    "snap_net_income",
    "snap_regular_month_allotment",
)


def _scenario_row(
    unit: Any,
    result: dict[str, Any],
    output_ids: dict[str, str],
    baseline: dict[str, Any],
    *,
    assumption_label: str,
) -> dict[str, Any]:
    row = _row(unit, result, output_ids)
    censored = _is_smd_censored(unit)
    observed_excess = float(getattr(unit, "medical_expenses", 0) or 0)
    assumed_excess = (
        float(ASSUMED_CENSORED_EXCESS[assumption_label])
        if censored
        else observed_excess
    )
    output_deltas = {
        label: _clean(float(row["outputs"][label]) - float(baseline["outputs"][label]))
        for label in DELTA_OUTPUT_LABELS
    }
    row.update(
        {
            "adapter_smd_on_baseline": {
                "benefit": baseline["benefit"],
                "outputs": {
                    label: baseline["outputs"][label] for label in DELTA_OUTPUT_LABELS
                },
            },
            "assumption_label": assumption_label,
            "assumption_statement": ASSUMPTION_STATEMENTS[assumption_label],
            "benefit_change_smd_off_minus_smd_on": output_deltas[
                "snap_regular_month_allotment"
            ],
            "candidate_encoding_change": False,
            "composition_variant": COMPOSITION_VARIANT_LABEL,
            "deltas_smd_off_minus_smd_on": output_deltas,
            "medical_deduction_branch": (
                "actual_excess" if assumed_excess > 0 else "none"
            ),
            "scenario": f"smd-off-{assumption_label}",
            "scenario_inputs": {
                "actual_excess_imputed": censored,
                "assumed_medical_expense_excess_above_35": _clean(assumed_excess),
                "engine_total_medical_expenses": _clean(
                    assumed_excess + 35 if assumed_excess > 0 else 0
                ),
                "observed_public_FSMEDEXP": _clean(observed_excess),
                "smd_standard_amount": 0,
            },
            "schema": ARTIFACT_SCHEMA,
        }
    )
    return row


def _distribution(
    rows: list[dict[str, Any]], *, delta_path: tuple[str, ...]
) -> list[dict[str, Any]]:
    grouped: dict[int | float, list[dict[str, Any]]] = {}
    for row in rows:
        value: Any = row
        for key in delta_path:
            value = value[key]
        grouped.setdefault(_clean(value), []).append(row)
    return [
        {
            "case_count": len(grouped[delta]),
            "delta": delta,
            "HWGT": _clean(sum(float(row["HWGT"] or 0) for row in grouped[delta])),
        }
        for delta in sorted(grouped, key=float)
    ]


def _contribution(rows: list[dict[str, Any]], *, total_weight: float) -> dict[str, Any]:
    weight = sum(float(row["HWGT"] or 0) for row in rows)
    weighted_sum = sum(
        float(row["HWGT"] or 0) * float(row["benefit_change_smd_off_minus_smd_on"])
        for row in rows
    )
    changed = [
        row
        for row in rows
        if not _equal(row["deltas_smd_off_minus_smd_on"]["medical_deduction"], 0)
    ]
    return {
        "benefit_delta_distribution": _distribution(
            rows,
            delta_path=("benefit_change_smd_off_minus_smd_on",),
        ),
        "case_count": len(rows),
        "changed_medical_deduction_case_count": len(changed),
        "changed_medical_deduction_HWGT": _clean(
            sum(float(row["HWGT"] or 0) for row in changed)
        ),
        "HWGT": _clean(weight),
        "overall_weighted_mean_benefit_change_contribution": _clean(
            weighted_sum / total_weight if total_weight else 0
        ),
        "subgroup_weighted_mean_benefit_change": _clean(
            weighted_sum / weight if weight else 0
        ),
        "weighted_sum_benefit_change": _clean(weighted_sum),
    }


def _scenario_diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_weight = sum(float(row["HWGT"] or 0) for row in rows)
    weighted_sum = sum(
        float(row["HWGT"] or 0) * float(row["benefit_change_smd_off_minus_smd_on"])
        for row in rows
    )
    changed = [
        row
        for row in rows
        if not _equal(row["deltas_smd_off_minus_smd_on"]["medical_deduction"], 0)
    ]
    censored = [
        row
        for row in rows
        if "smd_actual_expense_censored" in row["identification_flags"]
    ]
    noncensored = [row for row in rows if row not in censored]
    censored_contribution = _contribution(censored, total_weight=total_weight)
    noncensored_contribution = _contribution(
        noncensored,
        total_weight=total_weight,
    )
    reconciled = _clean(
        float(
            censored_contribution["overall_weighted_mean_benefit_change_contribution"]
        )
        + float(
            noncensored_contribution[
                "overall_weighted_mean_benefit_change_contribution"
            ]
        )
    )
    weighted_mean = _clean(weighted_sum / total_weight if total_weight else 0)
    if not _equal(reconciled, weighted_mean):
        raise RuntimeError(
            "censored/noncensored benefit contributions do not reconcile"
        )
    return {
        "benefit_delta_distribution_smd_off_minus_smd_on": _distribution(
            rows,
            delta_path=("benefit_change_smd_off_minus_smd_on",),
        ),
        "cases_with_changed_medical_deduction": len(changed),
        "changed_medical_deduction_HWGT": _clean(
            sum(float(row["HWGT"] or 0) for row in changed)
        ),
        "censored_case_contribution": censored_contribution,
        "delta_direction": "SMD-off minus adapter/SMD-on baseline",
        "medical_deduction_delta_distribution_smd_off_minus_smd_on": (
            _distribution(
                rows,
                delta_path=(
                    "deltas_smd_off_minus_smd_on",
                    "medical_deduction",
                ),
            )
        ),
        "noncensored_case_contribution": noncensored_contribution,
        "total_HWGT": _clean(total_weight),
        "weighted_mean_benefit_change": weighted_mean,
        "weighted_sum_benefit_change": _clean(weighted_sum),
    }


def _diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    stage_rows: list[dict[str, Any]] = []
    for label in certified._LABELS:
        divergent = [row for row in rows if not row["stage_agreement"][label.label]]
        stage_rows.append(
            {
                "agreement_count": len(rows) - len(divergent),
                "divergence_count": len(divergent),
                "divergence_weight": _clean(
                    sum(float(row["HWGT"] or 0) for row in divergent)
                ),
                "label": label.label,
                "stage": label.stage,
            }
        )

    driver_names = sorted(
        {driver for row in rows for driver in row.get("driver_classes", [])}
    )
    driver_rows: list[dict[str, Any]] = []
    for driver in driver_names:
        affected = [row for row in rows if driver in row["driver_classes"]]
        for label in certified._LABELS:
            divergent = [
                row for row in affected if not row["stage_agreement"][label.label]
            ]
            driver_rows.append(
                {
                    "affected_case_count": len(affected),
                    "driver": driver,
                    "stage": label.stage,
                    "stage_divergence_count": len(divergent),
                    "stage_divergence_weight": _clean(
                        sum(float(row["HWGT"] or 0) for row in divergent)
                    ),
                }
            )

    benefit_deltas = Counter(
        _clean(
            float(row["benefit"])
            - float(row["qc_expected"]["snap_regular_month_allotment"])
        )
        for row in rows
    )
    return {
        "benefit_delta_distribution_engine_minus_qc": [
            {"case_count": benefit_deltas[delta], "delta": delta}
            for delta in sorted(benefit_deltas, key=float)
        ],
        "by_driver_and_stage": driver_rows,
        "by_stage": stage_rows,
        "driver_case_counts": {
            driver: sum(driver in row["driver_classes"] for row in rows)
            for driver in driver_names
        },
        "smd_actual_expense_censored_case_count": sum(
            "smd_actual_expense_censored" in row["identification_flags"] for row in rows
        ),
        "smd_actual_expense_censored_weight": _clean(
            sum(
                float(row["HWGT"] or 0)
                for row in rows
                if "smd_actual_expense_censored" in row["identification_flags"]
            )
        ),
    }


def _driver_file_hashes() -> dict[str, str]:
    return {
        "axiom_oracles/bridges/simulation_driver.py": _sha256(Path(__file__)),
    }


def _canonical_wall_times(output_dir: Path) -> dict[str, Any] | None:
    """Reuse first-generation timings when regenerating identical artifacts.

    Wall-clock measurements are inherently nondeterministic.  The first run of
    a particular driver version records its measurements; subsequent full
    regenerations with the same driver hash retain those canonical timing
    fields while recomputing every engine row.  This lets the manifest contain
    real timings and still be byte-identical across artifact regenerations.
    """
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if existing.get("driver_file_sha256") != _driver_file_hashes():
        return None
    wall_times = existing.get("wall_times_seconds")
    return wall_times if isinstance(wall_times, dict) else None


def _certified_guard(
    *, workspace: Path, rulespec_root: Path, binary: Path, qc_csv: Path
) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    report = certified.run_snap_qc_comparison(
        fiscal_year=FISCAL_YEAR,
        jurisdiction=JURISDICTION,
        sample_size=None,
        tolerance=0,
        stage_tolerance=0,
        workspace_root=workspace,
        rulespec_root=rulespec_root,
        axiom_binary=binary,
        data_dir=qc_csv.parent,
        include_special_programs=False,
        keep_overlay=False,
    )
    elapsed = time.perf_counter() - started
    summary = report["summary"]
    comparison_cells = sum(row["comparison_count"] for row in report["aggregates"])
    mismatch_cells = sum(row["mismatch_count"] for row in report["aggregates"])
    if not (
        report["case_count"] == EXPECTED_CASE_COUNT
        and summary["match_count"] == EXPECTED_CASE_COUNT
        and summary["mismatch_count"] == 0
        and comparison_cells == EXPECTED_CERTIFIED_CELLS
        and mismatch_cells == 0
        and not report["errors"]
    ):
        raise RuntimeError("certified original-bridge regression guard failed")
    return (
        {
            "comparison_cell_count": comparison_cells,
            "error_count": len(report["errors"]),
            "match_count": summary["match_count"],
            "mismatch_cell_count": mismatch_cells,
            "mismatch_count": summary["mismatch_count"],
            "original_bridge_sha256": _sha256(Path(certified.__file__)),
            "status": "passed",
        },
        elapsed,
    )


def _pins(
    *, workspace: Path, rulespec_root: Path, binary: Path, qc_csv: Path
) -> dict[str, Any]:
    harness_root = workspace / "axiom-oracles"
    return {
        "engine": {
            "binary": str(binary),
            "binary_sha256": _sha256(binary),
            "commit": _git_head(workspace / "engine"),
        },
        "harness": {
            "commit": _git_head(harness_root),
            "worktree": str(harness_root),
        },
        "qc_csv": {"path": str(qc_csv), "sha256": _sha256(qc_csv)},
        "rulespec": {
            "commit": _git_head(rulespec_root),
            "worktree": str(rulespec_root),
        },
    }


def _exclusion_dict(log: Any) -> dict[str, Any]:
    return certified._exclusion_summary(log)


def generate_baseline(
    *,
    workspace: Path,
    rulespec_root: Path,
    binary: Path,
    qc_csv: Path,
    output_dir: Path,
    guard: dict[str, Any],
    guard_wall: float,
) -> dict[str, Any]:
    canonical_wall_times = _canonical_wall_times(output_dir)
    config = certified.QC_JURISDICTIONS[JURISDICTION]
    spec = load_overlay_spec(config.overlay)
    output_ids = _output_ids(spec)

    load_started = time.perf_counter()
    from ..populations.snap_qc import load_qc_units

    units, exclusion_log = load_qc_units(
        FISCAL_YEAR,
        state_fips=config.state_fips,
        data_dir=qc_csv.parent,
        include_special_programs=False,
    )
    units = sorted(units, key=lambda unit: (unit.yrmonth, str(unit.case_id)))
    load_wall = time.perf_counter() - load_started
    if len(units) != EXPECTED_CASE_COUNT:
        raise RuntimeError(
            f"loaded {len(units)} CO cases, expected {EXPECTED_CASE_COUNT}"
        )

    base_inputs = load_base_inputs(rulespec_root / config.template)
    base_member = certified._load_base_member(
        rulespec_root / config.template, config.base.relation_id
    )
    sua_amount_by_tier = certified.sua_amounts_from_overlay(spec, config)
    cases = [
        map_raw_facts_case(
            unit,
            base_inputs,
            base_member,
            config=config,
            sua_amount_by_tier=sua_amount_by_tier,
        )
        for unit in units
    ]

    scratch_parent = workspace / "simulations"
    scratch_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="co-raw-baseline-", dir=scratch_parent
    ) as scratch_text:
        scratch = Path(scratch_text)
        overlay_started = time.perf_counter()
        build = build_overlay(spec, rulespec_root, scratch / "overlay")
        overlay_wall = time.perf_counter() - overlay_started
        env = axiom_rules_env(build.program_path, workspace)
        env["AXIOM_RULESPEC_REPO_ROOTS"] = str(build.overlay_root)
        artifact = scratch / "co-fy2024-baseline.compiled.json"
        compile_started = time.perf_counter()
        compile_program(binary, build.program_path, artifact, env=env)
        compile_wall = time.perf_counter() - compile_started
        compiled_sha256 = _sha256(artifact)

        rendered_runs: list[bytes] = []
        execution_walls: list[float] = []
        for _ in range(2):
            execution_started = time.perf_counter()
            results = _run_batches(
                binary=binary,
                artifact=artifact,
                cases=cases,
                period=month_period(*certified.NOMINAL_PERIOD),
                output_ids=list(output_ids.values()),
                config=config,
                env=env,
            )
            execution_walls.append(time.perf_counter() - execution_started)
            rows = [
                _row(unit, result, output_ids)
                for unit, result in zip(units, results, strict=True)
            ]
            rendered_runs.append(_jsonl_bytes(rows))

        if rendered_runs[0] != rendered_runs[1]:
            raise RuntimeError("baseline JSONL was not byte-identical across two runs")

        cases_bytes = rendered_runs[0]
        cases_sha256 = hashlib.sha256(cases_bytes).hexdigest()
        diagnostics = _diagnostics(rows)
        overlay_spec_path = (
            Path(certified.__file__).with_name("overlays") / f"{config.overlay}.yaml"
        )
        measured_wall_times = {
            "certified_regression_guard": _clean(guard_wall),
            "engine_executions": [_clean(value) for value in execution_walls],
            "overlay_materialization": _clean(overlay_wall),
            "program_compile": _clean(compile_wall),
            "qc_load": _clean(load_wall),
        }
        manifest = {
            "artifact_class": ARTIFACT_CLASS_LABEL,
            "case_count": len(rows),
            "certified_original_bridge_regression_guard": guard,
            "compiled_artifact_sha256": compiled_sha256,
            "determinism": {
                "byte_identical": True,
                "engine_execution_count": 2,
                "fixed_order": "YRMONTH ascending, then case_id ascending",
                "jsonl_sha256_both_runs": [cases_sha256, cases_sha256],
                "serialization": "UTF-8; LF; terminal newline; sorted keys; compact JSONL",
            },
            "diagnostics": diagnostics,
            "driver_file_sha256": _driver_file_hashes(),
            "exclusions": _exclusion_dict(exclusion_log),
            "fiscal_year": FISCAL_YEAR,
            "jurisdiction": JURISDICTION,
            "limitations": {
                "categorical": (
                    "CAT_ELIG remains the QC-derived categorical-type entitlement "
                    "fact. Code 2 selects the encoded expanded path and its 200% "
                    "gross-income test; full 4.206 categorical eligibility is not "
                    "in the composition and its TANF/MOE/form/disqualification facts "
                    "are absent from the public file."
                ),
                "child_support": (
                    "FSCSEXP supplies the amount, but payment verification, legal "
                    "obligation, and history are unavailable; positive expense is "
                    "projected as a verified three-month average."
                ),
                "medical": (
                    "FSMEDEXP is documented as excess above $35, so the bridge adds "
                    "$35 solely to meet the encoding's total-expense input schema. "
                    "The QC minimodel has already replaced 46 sub-threshold Colorado "
                    "actuals with $165; their actual expenses cannot be recovered."
                ),
                "resources": (
                    "LIQRESOR is a QC-constructed countable-liquid-resource amount, "
                    "not elemental raw assets (RAWLQRES is the reported field). All "
                    "retained Colorado resource amounts are zero."
                ),
                "utility": (
                    "SUA1 remains the QC-edited entitlement tier. Itemized bills and "
                    "the precise LEAP/E-EBT route are unavailable; limited and "
                    "one-utility tiers use synthetic witness flags. Numeric UTIL is "
                    "diagnostic only and never enters the engine input. HOMEDED=3 "
                    "suppresses utility flags because the flat homeless deduction "
                    "replaces the ordinary shelter path."
                ),
            },
            "nominal_engine_period": "2026-01",
            "output_file": {
                "name": "cases.jsonl",
                "row_count": len(rows),
                "sha256": cases_sha256,
            },
            "overlay": {
                "materialization": build.provenance,
                "spec": _overlay_dict(spec),
                "spec_file": str(overlay_spec_path),
                "spec_file_sha256": _sha256(overlay_spec_path),
            },
            "pins": _pins(
                workspace=workspace,
                rulespec_root=rulespec_root,
                binary=binary,
                qc_csv=qc_csv,
            ),
            "queried_outputs": output_ids,
            "scenario": "baseline",
            "scenario_definition": (
                "Colorado FY2024 baseline on the certified pinned toolchain. "
                "The local bridge sources medical from FSMEDEXP, child support "
                "from FSCSEXP, utility entitlement from SUA1 with engine-selected "
                "allowance amounts, LIQRESOR for liquid resources, and preserves "
                "CAT_ELIG type so the encoding applies the expanded 200%-FPL path."
            ),
            "schema": MANIFEST_SCHEMA,
            "status": "complete_with_documented_public_data_limitations",
            "wall_times_note": (
                "Measured on the first complete generation for this exact driver "
                "version and retained on later full regenerations so the artifact "
                "remains byte-identical."
            ),
            "wall_times_seconds": canonical_wall_times or measured_wall_times,
        }

    manifest_bytes_1 = _json_bytes(manifest, pretty=True)
    manifest_bytes_2 = _json_bytes(manifest, pretty=True)
    if manifest_bytes_1 != manifest_bytes_2:
        raise RuntimeError("baseline manifest serialization was not deterministic")
    manifest["determinism"]["manifest_serialization_count"] = 2
    manifest_bytes_1 = _json_bytes(manifest, pretty=True)
    manifest_bytes_2 = _json_bytes(manifest, pretty=True)
    if manifest_bytes_1 != manifest_bytes_2:
        raise RuntimeError(
            "baseline final manifest serialization was not deterministic"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "cases.jsonl").write_bytes(cases_bytes)
    (output_dir / "manifest.json").write_bytes(manifest_bytes_1)
    return {
        "cases_jsonl_sha256": cases_sha256,
        "diagnostics": diagnostics,
        "manifest_sha256": hashlib.sha256(manifest_bytes_1).hexdigest(),
        "wall_times_seconds": manifest["wall_times_seconds"],
    }


def _smd_off_spec(base_spec: OverlaySpec) -> OverlaySpec:
    return dataclasses.replace(
        base_spec,
        name="us-co-snap-fy2024-smd-off-composition-variant",
        notes=(
            base_spec.notes
            + " Simulation-only SMD-off scalar patch, executed only with the "
            "materialized Colorado medical composition adapter; this is not a "
            "candidate encoding change."
        ),
        parameter_patches=base_spec.parameter_patches
        + (
            ParameterPatch(
                file=SMD_PARAMETER_FILE,
                rule=SMD_PARAMETER_RULE,
                from_value="165",
                to_value="0",
                source=(
                    "approved counterfactual semantics: SMD off while actual-expense "
                    "medical deduction remains"
                ),
            ),
        ),
    )


def _load_units(qc_csv: Path) -> tuple[list[Any], Any, float]:
    from ..populations.snap_qc import load_qc_units

    started = time.perf_counter()
    units, exclusion_log = load_qc_units(
        FISCAL_YEAR,
        state_fips=8,
        data_dir=qc_csv.parent,
        include_special_programs=False,
    )
    units = sorted(units, key=lambda unit: (unit.yrmonth, str(unit.case_id)))
    elapsed = time.perf_counter() - started
    if len(units) != EXPECTED_CASE_COUNT:
        raise RuntimeError(
            f"loaded {len(units)} CO cases, expected {EXPECTED_CASE_COUNT}"
        )
    return units, exclusion_log, elapsed


def _normal_cdf(value: float) -> float:
    return (1 + math.erf(value / math.sqrt(2))) / 2


def _censoring_metadata(units: list[Any]) -> dict[str, Any]:
    censored = [unit for unit in units if _is_smd_censored(unit)]
    donors = [
        unit
        for unit in units
        if _raw_int(unit, "MED_DED_DEMO") == 1
        and float(getattr(unit, "medical_expenses", 0) or 0) > SMD_CENSORED_VALUE
    ]
    zero = [
        unit for unit in units if float(getattr(unit, "medical_expenses", 0) or 0) == 0
    ]
    if (
        len(censored) != SMD_CENSORED_CASE_COUNT
        or len(donors) != SMD_DONOR_CASE_COUNT
        or len(zero) != SMD_ZERO_CASE_COUNT
        or len(censored) + len(donors) + len(zero) != len(units)
    ):
        raise RuntimeError(
            "unexpected Colorado medical-expense cohort partition; "
            "the bounded assumptions require re-audit"
        )

    donor_rows = sorted(
        (
            {
                "FSMEDEXP_excess_above_35": _clean(unit.medical_expenses),
                "HWGT": unit.weight,
                "case_id": str(unit.case_id),
            }
            for unit in donors
        ),
        key=lambda row: (float(row["FSMEDEXP_excess_above_35"]), row["case_id"]),
    )
    donor_values = [row["FSMEDEXP_excess_above_35"] for row in donor_rows]
    expected_values = [175, 200, 227, 314, 314, 360, 470]
    if donor_values != expected_values:
        raise RuntimeError(
            f"unexpected non-recoded donor values {donor_values}; expected "
            f"{expected_values}"
        )

    donor_weight = sum(float(unit.weight or 0) for unit in donors)
    censored_weight = sum(float(unit.weight or 0) for unit in censored)
    positive_weight = donor_weight + censored_weight
    weighted_donor_mean = (
        sum(float(unit.weight or 0) * float(unit.medical_expenses) for unit in donors)
        / donor_weight
    )

    upper = SMD_CENSORED_VALUE
    z_upper = (math.log(upper) - POINT_LOGNORMAL_MU) / POINT_LOGNORMAL_SIGMA
    fitted_censored_share = _normal_cdf(z_upper)
    fitted_conditional_mean = (
        math.exp(POINT_LOGNORMAL_MU + (POINT_LOGNORMAL_SIGMA**2) / 2)
        * _normal_cdf(z_upper - POINT_LOGNORMAL_SIGMA)
        / fitted_censored_share
    )
    if not math.isclose(
        fitted_conditional_mean,
        POINT_CONDITIONAL_MEAN,
        rel_tol=0,
        abs_tol=1e-9,
    ):
        raise RuntimeError("point-imputation fit constants do not reproduce")
    fitted_upper_mean = (
        math.exp(POINT_LOGNORMAL_MU + (POINT_LOGNORMAL_SIGMA**2) / 2)
        * (1 - _normal_cdf(z_upper - POINT_LOGNORMAL_SIGMA))
        / (1 - fitted_censored_share)
    )

    return {
        "censored": {
            "case_count": len(censored),
            "definition": "MED_DED_DEMO = 1 and public FSMEDEXP = $165",
            "HWGT": _clean(censored_weight),
            "identified_whole_dollar_excess_support": {
                "maximum": 165,
                "minimum": 1,
            },
            "identified_total_medical_expense_support": {
                "maximum": 200,
                "minimum": 36,
            },
        },
        "non_recoded_donors_above_standard": {
            "case_count": len(donor_rows),
            "cases": donor_rows,
            "definition": "MED_DED_DEMO = 1 and public FSMEDEXP > $165",
            "HWGT": _clean(donor_weight),
            "weighted_mean_excess_above_35": _clean(weighted_donor_mean),
        },
        "point_imputation_fit": {
            "conditional_mean_excess_above_35": _clean(fitted_conditional_mean),
            "distribution": "lognormal on positive pre-recode FSMEDEXP",
            "fit_method": (
                "HWGT-weighted maximum likelihood: seven exact density terms "
                "above $165 plus one left-censored probability term for the "
                "summed HWGT of the 46 cases with 0 < X <= $165"
            ),
            "fitted_censored_share_among_positive_HWGT": _clean(fitted_censored_share),
            "fitted_mean_conditional_above_165": _clean(fitted_upper_mean),
            "ln_dollar_mu": _clean(POINT_LOGNORMAL_MU),
            "observed_censored_share_among_positive_HWGT": _clean(
                censored_weight / positive_weight
            ),
            "observed_donor_weighted_mean_above_165": _clean(weighted_donor_mean),
            "rounded_point_excess_above_35": ASSUMED_CENSORED_EXCESS["point"],
            "sigma": _clean(POINT_LOGNORMAL_SIGMA),
        },
        "zero_medical_expense_case_count": len(zero),
    }


def _map_cases(
    units: list[Any],
    *,
    rulespec_root: Path,
    config: Any,
    spec: OverlaySpec,
    assumption_label: str | None,
) -> tuple[list[ProjectedCase], float]:
    started = time.perf_counter()
    base_inputs = load_base_inputs(rulespec_root / config.template)
    base_member = certified._load_base_member(
        rulespec_root / config.template, config.base.relation_id
    )
    sua_amount_by_tier = certified.sua_amounts_from_overlay(spec, config)
    cases = [
        map_raw_facts_case(
            unit,
            base_inputs,
            base_member,
            config=config,
            sua_amount_by_tier=sua_amount_by_tier,
            medical_excess_override=(
                ASSUMED_CENSORED_EXCESS[assumption_label]
                if assumption_label is not None and _is_smd_censored(unit)
                else None
            ),
        )
        for unit in units
    ]
    return cases, time.perf_counter() - started


def _compile_adapter_variant(
    *,
    spec: OverlaySpec,
    rulespec_root: Path,
    binary: Path,
    workspace: Path,
    scratch: Path,
    artifact_name: str,
) -> tuple[Any, Path, dict[str, str], dict[str, Any]]:
    materialization_started = time.perf_counter()
    build = build_overlay(spec, rulespec_root, scratch / "overlay")
    build = _apply_composition_adapter(build)
    materialization_wall = time.perf_counter() - materialization_started
    env = axiom_rules_env(build.program_path, workspace)
    env["AXIOM_RULESPEC_REPO_ROOTS"] = str(build.overlay_root)
    artifact = scratch / artifact_name
    compile_started = time.perf_counter()
    compile_program(binary, build.program_path, artifact, env=env)
    compile_wall = time.perf_counter() - compile_started
    return (
        build,
        artifact,
        env,
        {
            "compiled_artifact_sha256": _sha256(artifact),
            "overlay_materialization": _clean(materialization_wall),
            "program_compile": _clean(compile_wall),
        },
    )


def _adapter_baseline_invariance(
    *,
    workspace: Path,
    rulespec_root: Path,
    binary: Path,
    units: list[Any],
    cases: list[ProjectedCase],
    output_ids: dict[str, str],
    config: Any,
    build: Any,
    artifact: Path,
    env: dict[str, str],
    output_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rendered_runs: list[bytes] = []
    execution_walls: list[float] = []
    all_rows: list[list[dict[str, Any]]] = []
    for _ in range(2):
        started = time.perf_counter()
        results = _run_batches(
            binary=binary,
            artifact=artifact,
            cases=cases,
            period=month_period(*certified.NOMINAL_PERIOD),
            output_ids=list(output_ids.values()),
            config=config,
            env=env,
        )
        execution_walls.append(time.perf_counter() - started)
        rows = [
            _row(unit, result, output_ids)
            for unit, result in zip(units, results, strict=True)
        ]
        all_rows.append(rows)
        rendered_runs.append(_jsonl_bytes(rows))
    if rendered_runs[0] != rendered_runs[1]:
        raise RuntimeError("adapter/SMD-on baseline was not byte-identical")

    reference_path = output_root / "baseline" / "cases.jsonl"
    reference_sha256 = _sha256(reference_path)
    if reference_sha256 != ROUND1_BASELINE_CASES_SHA256:
        raise RuntimeError(
            f"round-1 baseline hash changed: {reference_sha256}; expected "
            f"{ROUND1_BASELINE_CASES_SHA256}"
        )
    reference_rows = [
        json.loads(line)
        for line in reference_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    reference_by_id = {row["case_id"]: row for row in reference_rows}
    rows = all_rows[0]
    actual_by_id = {row["case_id"]: row for row in rows}
    if set(reference_by_id) != set(actual_by_id):
        raise RuntimeError("adapter baseline case ids differ from round 1")

    chain_order = (
        "medical_excess",
        "medical_deduction",
        "federal_medical_deduction",
        "snap_excess_shelter_deduction",
        "snap_net_income",
        "snap_regular_month_allotment",
    )
    divergences: list[dict[str, Any]] = []
    for case_id in sorted(reference_by_id):
        reference = reference_by_id[case_id]
        actual = actual_by_id[case_id]
        differing_outputs = {
            label: {
                "adapter": actual["outputs"].get(label),
                "round_1": value,
            }
            for label, value in reference["outputs"].items()
            if not _equal(actual["outputs"].get(label), value)
        }
        benefit_differs = not _equal(actual["benefit"], reference["benefit"])
        if differing_outputs or benefit_differs:
            mechanism = next(
                (label for label in chain_order if label in differing_outputs),
                "non-chain output or final benefit",
            )
            divergences.append(
                {
                    "benefit": {
                        "adapter": actual["benefit"],
                        "round_1": reference["benefit"],
                    },
                    "case_id": case_id,
                    "differing_outputs": differing_outputs,
                    "first_mechanism": mechanism,
                }
            )

    branch_rows = [row for row in rows if _is_smd_censored_by_row(row)]
    smd_standard_amount = _materialized_parameter_formula(
        build,
        file=SMD_PARAMETER_FILE,
        rule=SMD_PARAMETER_RULE,
    )
    branch_failures = [
        row["case_id"]
        for row in branch_rows
        if not (
            _equal(row["outputs"]["medical_excess"], 165)
            and smd_standard_amount == "165"
            and _equal(row["outputs"]["medical_deduction"], 165)
            and _equal(row["outputs"]["federal_medical_surface"], 200)
            and _equal(row["outputs"]["federal_medical_deduction"], 165)
        )
    ]
    if len(branch_rows) != SMD_CENSORED_CASE_COUNT or branch_failures:
        divergences.append(
            {
                "branch_failure_case_ids": branch_failures,
                "expected_branch_case_count": SMD_CENSORED_CASE_COUNT,
                "observed_branch_case_count": len(branch_rows),
                "first_mechanism": "Colorado SMD branch proof",
            }
        )
    if divergences:
        failure = {
            "composition_variant": COMPOSITION_VARIANT_LABEL,
            "divergence_count": len(divergences),
            "divergences": divergences,
            "status": "stopped_before_smd_off",
        }
        failure_path = output_root / "smd-off" / "adapter-invariance-failure.json"
        failure_path.parent.mkdir(parents=True, exist_ok=True)
        failure_path.write_bytes(_json_bytes(failure, pretty=True))
        raise RuntimeError(
            f"adapter baseline diverged; per-case report: {failure_path}"
        )

    return rows, {
        "adapter_jsonl_sha256_both_runs": [
            hashlib.sha256(value).hexdigest() for value in rendered_runs
        ],
        "branch_proof": {
            "case_count": len(branch_rows),
            "condition": (
                "the materialized SMD parameter is $165 and medical_excess == "
                "medical_deduction == $165, so strict medical_excess > standard "
                "is false and the positive SMD branch governs; adapter surface "
                "== $200 and federal deduction == $165"
            ),
            "failure_count": 0,
            "materialized_smd_standard_amount": int(smd_standard_amount),
        },
        "byte_identical": True,
        "case_count": len(rows),
        "compared_fields": (
            "benefit and every round-1 outputs member, keyed by case_id"
        ),
        "composition_variant": build.provenance["simulation_composition_variant"],
        "divergence_count": 0,
        "engine_execution_count": 2,
        "engine_executions_seconds": [_clean(value) for value in execution_walls],
        "round_1_cases_jsonl": str(reference_path),
        "round_1_cases_jsonl_sha256": reference_sha256,
        "status": "passed",
    }


def _is_smd_censored_by_row(row: dict[str, Any]) -> bool:
    return "smd_actual_expense_censored" in row["identification_flags"]


def _scenario_fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_json_bytes(payload)).hexdigest()


def _canonical_scenario_wall_times(
    output_dir: Path, *, scenario_fingerprint: str
) -> dict[str, Any] | None:
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        manifest.get("driver_file_sha256") != _driver_file_hashes()
        or manifest.get("scenario_fingerprint") != scenario_fingerprint
    ):
        return None
    wall_times = manifest.get("wall_times_seconds")
    return wall_times if isinstance(wall_times, dict) else None


def _validate_scenario_rows(
    rows: list[dict[str, Any]], *, assumption_label: str, output_root: Path
) -> None:
    expected_excess = ASSUMED_CENSORED_EXCESS[assumption_label]
    surprises: list[dict[str, Any]] = []
    for row in rows:
        censored = _is_smd_censored_by_row(row)
        outputs = row["outputs"]
        deltas = row["deltas_smd_off_minus_smd_on"]
        if censored:
            expected_surface = expected_excess + 35
            if not (
                row["medical_deduction_branch"] == "actual_excess"
                and _equal(outputs["medical_excess"], expected_excess)
                and _equal(outputs["medical_deduction"], expected_excess)
                and _equal(outputs["federal_medical_surface"], expected_surface)
                and _equal(outputs["federal_medical_deduction"], expected_excess)
            ):
                surprises.append(
                    {
                        "case_id": row["case_id"],
                        "mechanism": "censored actual-excess branch mismatch",
                        "outputs": {
                            label: outputs[label]
                            for label in (
                                "medical_excess",
                                "medical_deduction",
                                "federal_medical_surface",
                                "federal_medical_deduction",
                            )
                        },
                    }
                )
        else:
            changed_chain = {
                label: delta for label, delta in deltas.items() if not _equal(delta, 0)
            }
            if changed_chain:
                surprises.append(
                    {
                        "case_id": row["case_id"],
                        "changed_chain": changed_chain,
                        "mechanism": "noncensored case changed",
                    }
                )
    diagnostics = _scenario_diagnostics(rows)
    expected_changed = 0 if assumption_label == "ceiling" else 46
    if diagnostics["cases_with_changed_medical_deduction"] != expected_changed:
        surprises.append(
            {
                "expected": expected_changed,
                "mechanism": "changed medical-deduction case count",
                "observed": diagnostics["cases_with_changed_medical_deduction"],
            }
        )
    if surprises:
        failure_path = (
            output_root / "smd-off" / f"{assumption_label}-structural-surprise.json"
        )
        failure_path.parent.mkdir(parents=True, exist_ok=True)
        failure_path.write_bytes(
            _json_bytes(
                {
                    "assumption": assumption_label,
                    "status": "stopped",
                    "surprises": surprises,
                },
                pretty=True,
            )
        )
        raise RuntimeError(f"new structural surprise; report: {failure_path}")


def _generate_smd_scenario(
    *,
    assumption_label: str,
    workspace: Path,
    rulespec_root: Path,
    binary: Path,
    qc_csv: Path,
    units: list[Any],
    exclusion_log: Any,
    config: Any,
    spec: OverlaySpec,
    output_ids: dict[str, str],
    baseline_by_id: dict[str, dict[str, Any]],
    baseline_invariance: dict[str, Any],
    build: Any,
    artifact: Path,
    env: dict[str, str],
    common_timings: dict[str, Any],
    cohort_metadata: dict[str, Any],
    guard: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    cases, mapping_wall = _map_cases(
        units,
        rulespec_root=rulespec_root,
        config=config,
        spec=spec,
        assumption_label=assumption_label,
    )
    rendered_runs: list[bytes] = []
    execution_walls: list[float] = []
    rows: list[dict[str, Any]] = []
    for _ in range(2):
        started = time.perf_counter()
        results = _run_batches(
            binary=binary,
            artifact=artifact,
            cases=cases,
            period=month_period(*certified.NOMINAL_PERIOD),
            output_ids=list(output_ids.values()),
            config=config,
            env=env,
        )
        execution_walls.append(time.perf_counter() - started)
        rows = [
            _scenario_row(
                unit,
                result,
                output_ids,
                baseline_by_id[str(unit.case_id)],
                assumption_label=assumption_label,
            )
            for unit, result in zip(units, results, strict=True)
        ]
        rendered_runs.append(_jsonl_bytes(rows))
    if rendered_runs[0] != rendered_runs[1]:
        raise RuntimeError(f"{assumption_label} JSONL was not byte-identical")
    _validate_scenario_rows(
        rows,
        assumption_label=assumption_label,
        output_root=output_dir.parents[1],
    )

    cases_bytes = rendered_runs[0]
    cases_sha256 = hashlib.sha256(cases_bytes).hexdigest()
    diagnostics = _scenario_diagnostics(rows)
    overlay_spec_path = (
        Path(certified.__file__).with_name("overlays")
        / f"{certified.QC_JURISDICTIONS[JURISDICTION].overlay}.yaml"
    )
    tech_doc = qc_csv.parent / "FY-2024-Tech-Doc.pdf"
    if not tech_doc.exists():
        raise FileNotFoundError(tech_doc)

    fingerprint_payload = {
        "adapter_file_sha256": build.provenance["simulation_composition_variant"][
            "materialized_file_sha256_after"
        ],
        "assumption_statement": ASSUMPTION_STATEMENTS[assumption_label],
        "compiled_artifact_sha256": _sha256(artifact),
        "driver_file_sha256": _driver_file_hashes(),
        "qc_csv_sha256": _sha256(qc_csv),
        "round_1_baseline_sha256": ROUND1_BASELINE_CASES_SHA256,
        "scenario": assumption_label,
        "smd_parameter_file_sha256": build.provenance["file_sha256"][
            SMD_PARAMETER_FILE
        ],
    }
    scenario_fingerprint = _scenario_fingerprint(fingerprint_payload)
    measured_wall_times = {
        **common_timings,
        "scenario_case_mapping": _clean(mapping_wall),
        "scenario_engine_executions": [_clean(value) for value in execution_walls],
    }
    canonical_wall_times = _canonical_scenario_wall_times(
        output_dir,
        scenario_fingerprint=scenario_fingerprint,
    )
    output_relative = (
        f"simulations/fy2024/{JURISDICTION}/smd-off/{assumption_label}/cases.jsonl"
    )
    materialized_hashes = {
        f"materialized-simulation-variant/{relative}": sha256
        for relative, sha256 in build.provenance["file_sha256"].items()
    }
    changed_and_added = {
        **_driver_file_hashes(),
        **materialized_hashes,
        output_relative: cases_sha256,
    }
    baseline_invariance_for_manifest = {
        key: value
        for key, value in baseline_invariance.items()
        if key != "engine_executions_seconds"
    }
    manifest = {
        "artifact_class": ARTIFACT_CLASS_LABEL,
        "assumption_label": assumption_label,
        "assumption_statement": ASSUMPTION_STATEMENTS[assumption_label],
        "baseline_invariance_check": baseline_invariance_for_manifest,
        "candidate_encoding_change": False,
        "case_count": len(rows),
        "changed_and_added_file_sha256": dict(sorted(changed_and_added.items())),
        "compiled_artifact_sha256": _sha256(artifact),
        "composition_variant": COMPOSITION_VARIANT_LABEL,
        "censoring_and_imputation": cohort_metadata,
        "certified_original_bridge_regression_guard": guard,
        "counterfactual_parameter": {
            "file": SMD_PARAMETER_FILE,
            "materialized_formula": int(
                _materialized_parameter_formula(
                    build,
                    file=SMD_PARAMETER_FILE,
                    rule=SMD_PARAMETER_RULE,
                )
            ),
            "rule": SMD_PARAMETER_RULE,
            "sha256": build.provenance["file_sha256"][SMD_PARAMETER_FILE],
        },
        "determinism": {
            "byte_identical": True,
            "engine_execution_count": 2,
            "fixed_order": "YRMONTH ascending, then case_id ascending",
            "jsonl_sha256_both_runs": [cases_sha256, cases_sha256],
            "manifest_serialization_count": 2,
            "serialization": (
                "UTF-8; LF; terminal newline; sorted keys; compact JSONL"
            ),
        },
        "diagnostics": diagnostics,
        "driver_file_sha256": _driver_file_hashes(),
        "exclusions": _exclusion_dict(exclusion_log),
        "fiscal_year": FISCAL_YEAR,
        "jurisdiction": JURISDICTION,
        "nominal_engine_period": "2026-01",
        "output_file": {
            "name": "cases.jsonl",
            "row_count": len(rows),
            "sha256": cases_sha256,
        },
        "overlay": {
            "materialization": build.provenance,
            "spec": _overlay_dict(spec),
            "spec_file": str(overlay_spec_path),
            "spec_file_sha256": _sha256(overlay_spec_path),
        },
        "pins": _pins(
            workspace=workspace,
            rulespec_root=rulespec_root,
            binary=binary,
            qc_csv=qc_csv,
        ),
        "queried_outputs": output_ids,
        "scenario": f"smd-off-{assumption_label}",
        "scenario_definition": (
            "Materialized simulation composition adapter plus Colorado's "
            "$165 standard medical deduction set to $0; actual-excess path "
            "governs, with the labeled bounded assumption applied only to the "
            "46 censored cases."
        ),
        "scenario_fingerprint": scenario_fingerprint,
        "scenario_fingerprint_inputs": fingerprint_payload,
        "schema": MANIFEST_SCHEMA,
        "source_documents": {
            "fy2024_snap_qc_technical_documentation": {
                "path": str(tech_doc),
                "sha256": _sha256(tech_doc),
            }
        },
        "status": "complete_bounded_sensitivity_run",
        "wall_times_note": (
            "Measured on the first complete generation for this exact scenario "
            "fingerprint and retained on later full regenerations so cases and "
            "manifest remain byte-identical."
        ),
        "wall_times_seconds": canonical_wall_times or measured_wall_times,
    }
    manifest_bytes = _json_bytes(manifest, pretty=True)
    if manifest_bytes != _json_bytes(manifest, pretty=True):
        raise RuntimeError(f"{assumption_label} manifest was not deterministic")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "cases.jsonl").write_bytes(cases_bytes)
    (output_dir / "manifest.json").write_bytes(manifest_bytes)
    return {
        "cases_jsonl_sha256": cases_sha256,
        "diagnostics": diagnostics,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "scenario_fingerprint": scenario_fingerprint,
        "wall_times_seconds": manifest["wall_times_seconds"],
    }


def _write_interval_index(
    *,
    output_dir: Path,
    scenario_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    child_hashes: dict[str, str] = {}
    runs: dict[str, Any] = {}
    for label in ("floor", "point", "ceiling"):
        child_dir = output_dir / label
        for name in ("cases.jsonl", "manifest.json"):
            relative = f"{label}/{name}"
            child_hashes[relative] = _sha256(child_dir / name)
        result = scenario_results[label]
        runs[label] = {
            "assumption_statement": ASSUMPTION_STATEMENTS[label],
            "cases_jsonl_sha256": result["cases_jsonl_sha256"],
            "manifest_sha256": result["manifest_sha256"],
            "weighted_mean_benefit_change": result["diagnostics"][
                "weighted_mean_benefit_change"
            ],
        }
    weighted_means = [
        float(runs[label]["weighted_mean_benefit_change"])
        for label in ("floor", "point", "ceiling")
    ]
    manifest = {
        "artifact_class": ARTIFACT_CLASS_LABEL,
        "candidate_encoding_change": False,
        "child_file_sha256": dict(sorted(child_hashes.items())),
        "composition_variant": COMPOSITION_VARIANT_LABEL,
        "honest_delta_interval_weighted_mean_benefit_change": {
            "maximum": _clean(max(weighted_means)),
            "minimum": _clean(min(weighted_means)),
        },
        "runs": runs,
        "scenario": "smd-off-bounded-interval-index",
        "schema": MANIFEST_SCHEMA,
        "status": "complete",
    }
    first = _json_bytes(manifest, pretty=True)
    second = _json_bytes(manifest, pretty=True)
    if first != second:
        raise RuntimeError("SMD-off interval index was not deterministic")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_bytes(first)
    return {"manifest_sha256": hashlib.sha256(first).hexdigest()}


def run(args: argparse.Namespace) -> dict[str, Any]:
    workspace = args.workspace.resolve()
    rulespec_root = (args.rulespec_root or workspace / "rulespec-us").resolve()
    binary = (
        args.axiom_binary
        or workspace / "cargo-target" / "release" / "axiom-rules-engine"
    ).resolve()
    qc_csv = (
        args.qc_csv or workspace.parent.parent / "snap-qc" / "qc_pub_fy2024.csv"
    ).resolve()
    output_root = (
        args.output_root or workspace / "simulations" / "fy2024" / JURISDICTION
    ).resolve()

    for required in (rulespec_root, binary, qc_csv):
        if not required.exists():
            raise FileNotFoundError(required)

    guard, guard_wall = _certified_guard(
        workspace=workspace,
        rulespec_root=rulespec_root,
        binary=binary,
        qc_csv=qc_csv,
    )
    units, exclusion_log, load_wall = _load_units(qc_csv)
    cohort_metadata = _censoring_metadata(units)
    config = certified.QC_JURISDICTIONS[JURISDICTION]
    base_spec = load_overlay_spec(config.overlay)
    output_ids = _output_ids(base_spec)

    scratch_parent = workspace / "simulations"
    scratch_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="co-smd-round1b-", dir=scratch_parent
    ) as scratch_text:
        scratch = Path(scratch_text)
        baseline_cases, baseline_mapping_wall = _map_cases(
            units,
            rulespec_root=rulespec_root,
            config=config,
            spec=base_spec,
            assumption_label=None,
        )
        baseline_build, baseline_artifact, baseline_env, baseline_compile = (
            _compile_adapter_variant(
                spec=base_spec,
                rulespec_root=rulespec_root,
                binary=binary,
                workspace=workspace,
                scratch=scratch / "adapter-smd-on",
                artifact_name="co-fy2024-adapter-smd-on.compiled.json",
            )
        )
        baseline_rows, baseline_invariance = _adapter_baseline_invariance(
            workspace=workspace,
            rulespec_root=rulespec_root,
            binary=binary,
            units=units,
            cases=baseline_cases,
            output_ids=output_ids,
            config=config,
            build=baseline_build,
            artifact=baseline_artifact,
            env=baseline_env,
            output_root=output_root,
        )
        baseline_by_id = {row["case_id"]: row for row in baseline_rows}

        smd_spec = _smd_off_spec(base_spec)
        smd_build, smd_artifact, smd_env, smd_compile = _compile_adapter_variant(
            spec=smd_spec,
            rulespec_root=rulespec_root,
            binary=binary,
            workspace=workspace,
            scratch=scratch / "adapter-smd-off",
            artifact_name="co-fy2024-adapter-smd-off.compiled.json",
        )
        materialized_smd_off_amount = _materialized_parameter_formula(
            smd_build,
            file=SMD_PARAMETER_FILE,
            rule=SMD_PARAMETER_RULE,
        )
        if materialized_smd_off_amount != "0":
            raise RuntimeError(
                "SMD-off materialization did not set the standard to zero"
            )
        common_timings = {
            "adapter_smd_off_overlay_materialization": smd_compile[
                "overlay_materialization"
            ],
            "adapter_smd_off_program_compile": smd_compile["program_compile"],
            "adapter_smd_on_case_mapping": _clean(baseline_mapping_wall),
            "adapter_smd_on_engine_executions": baseline_invariance[
                "engine_executions_seconds"
            ],
            "adapter_smd_on_overlay_materialization": baseline_compile[
                "overlay_materialization"
            ],
            "adapter_smd_on_program_compile": baseline_compile["program_compile"],
            "certified_regression_guard": _clean(guard_wall),
            "qc_load": _clean(load_wall),
        }
        scenario_results = {
            label: _generate_smd_scenario(
                assumption_label=label,
                workspace=workspace,
                rulespec_root=rulespec_root,
                binary=binary,
                qc_csv=qc_csv,
                units=units,
                exclusion_log=exclusion_log,
                config=config,
                spec=smd_spec,
                output_ids=output_ids,
                baseline_by_id=baseline_by_id,
                baseline_invariance=baseline_invariance,
                build=smd_build,
                artifact=smd_artifact,
                env=smd_env,
                common_timings=common_timings,
                cohort_metadata=cohort_metadata,
                guard=guard,
                output_dir=output_root / "smd-off" / label,
            )
            for label in ("floor", "point", "ceiling")
        }
    interval_index = _write_interval_index(
        output_dir=output_root / "smd-off",
        scenario_results=scenario_results,
    )
    return {
        "artifact_class": ARTIFACT_CLASS_LABEL,
        "baseline_invariance": baseline_invariance,
        "certified_guard": guard,
        "composition_variant": COMPOSITION_VARIANT_LABEL,
        "interval_index": interval_index,
        "output_root": str(output_root),
        "smd_off": scenario_results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=_default_workspace())
    parser.add_argument("--rulespec-root", type=Path)
    parser.add_argument("--axiom-binary", type=Path)
    parser.add_argument("--qc-csv", type=Path)
    parser.add_argument("--output-root", type=Path)
    return parser.parse_args()


def main() -> int:
    summary = run(parse_args())
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
