#!/usr/bin/env python3
"""Build or audit the evidence-pinned CA SNAP dispositions for issue #362.

Current reconciliation audit:
    python scripts/build_ca_snap_362_dispositions.py \
        --check --base-ref <literal-merged-base>

Legacy generation and its historical stale-output check take the exhaustive
JSON emitted by ``trace_ca_snap_residuals.py`` via ``--trace`` plus the same
explicit ``--base-ref``. The legacy path reads its report, compact cases, and
expected disposition source from that pinned Git snapshot, so it remains
reproducible after the tracked compact schema changed. The generator fails
closed on baseline drift, source misalignment, deduction confounds, or a
counterfactual outside the suite's $7 amount tolerance.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DISPOSITIONS_PATH = ROOT / "dispositions/ca-snap-ecps.yaml"

LEGACY_REPORT_RELATIVE_PATH = (
    "dashboard/public/data/axiom-policyengine-ca-snap-ecps.json"
)
LEGACY_CASE_DIR_RELATIVE_PATH = (
    "dashboard/public/data/cases/ca-snap-ecps"
)
LEGACY_REPORT_SHA256 = (
    "f89c9da976412c591e79917f1ca41061f9b7c5119529488c74c0deeb49db587f"
)
LEGACY_CASE_INDEX_SHA256 = (
    "a300c2e61eaaf1d117ee424efad73db2943db735a0f7302982bfbf76fd29aeb9"
)
LEGACY_CASE_CHUNKS_SHA256 = (
    "197125c9d62f9a1b8c7b4bea9a517287435be4a899c1d50a51df8b4edcc6a94f"
)
LEGACY_TRACE_SHA256 = (
    "c46af9b87c8f5ad01f1909bc45e80e00b4c4a50e5b802ea4ccbe194b5954b568"
)
EXPECTED_LEGACY_REPORT_ROWS = 684
EXPECTED_LEGACY_ISSUE_362_ANNOTATIONS = 345
EXPECTED_LEGACY_UNEXPLAINED_ROWS = 441
EXPECTED_LEGACY_CASES = 7101

BENEFIT_CONCEPT = "us:statutes/7/2014/u#snap_benefit"
ELIGIBILITY_CONCEPT = "us:statutes/7/2014/o#snap_eligible"
TOLERANCE = 7.0
SOURCE_TOLERANCE = 0.1

ISSUE_362 = "https://github.com/TheAxiomFoundation/axiom-oracles/issues/362"
ISSUE_397 = "https://github.com/TheAxiomFoundation/axiom-oracles/issues/397"
ISSUE_9157 = "https://github.com/PolicyEngine/policyengine-us/issues/9157"
PR_416 = "https://github.com/TheAxiomFoundation/axiom-oracles/pull/416"
SE_FIX = (
    "https://github.com/TheAxiomFoundation/axiom-oracles/commit/"
    "4b4e34c155809a8d6010545b0bb8c54a86a97d93"
)
SNAP_INCOME = (
    "https://www.ecfr.gov/current/title-7/chapter-II/subchapter-C/"
    "part-273#p-273.9(b)"
)
SNAP_STUDENT = (
    "https://www.ecfr.gov/current/title-7/chapter-II/subchapter-C/"
    "part-273#p-273.9(c)(7)"
)
SNAP_MEDICAL = (
    "https://www.ecfr.gov/current/title-7/chapter-II/subchapter-C/"
    "part-273#p-273.9(d)(3)"
)
SNAP_SHELTER = (
    "https://www.ecfr.gov/current/title-7/chapter-II/subchapter-C/"
    "part-273#p-273.9(d)(6)"
)
SNAP_DISABILITY = "https://www.law.cornell.edu/uscode/text/7/2012#j"


def _ids(text: str) -> frozenset[str]:
    return frozenset(f"ecps-{value}" for value in text.split())


STATIC_SE_GROSS = _ids(
    """
    57142 57208 57215 57322 57511 57615 57823 57841 58027 58092 58190
    58194 58210 58270 58320 58520 58612 58691 58771 58957 59009 59209
    59343 59385 59442 59593 59768 59982 59993 60109 60323 60333 60334
    60558 60638 61157 61261 61387 61408 61411 61977 62002 62596 62686
    68723 71406
    """
)
STATIC_SE_NET = _ids(
    """
    56920 56964 57444 57606 57677 57703 58098 58236 59014 59082 59120
    59123 59283 60499 61732 62042 62506 62715
    """
)
STATIC_SE = STATIC_SE_GROSS | STATIC_SE_NET

MINOR_DEFECT = _ids(
    "57065 57392 58015 58260 59775 60204 60550 60573 62068 62315"
)

TRACE_CLASSES = {
    "period": _ids(
        """
        57158 57289 57313 57404 57472 57737 57783 58054 58094 58317 58460
        58476 58945 59102 59371 59956 60408 60496 60519 60527 60610 60702
        60766 60888 61635 61700 61738 62402
        """
    ),
    "self_employment": _ids(
        """
        56910 56950 56964 57109 57142 57208 57215 57322 57444 57606 57615
        57677 57703 57717 57788 57823 57841 57876 58092 58173 58190 58194
        58236 58241 58270 58320 58376 58691 58957 58987 59016 59103 59123
        59173 59190 59209 59235 59283 59343 59385 59442 59768 59813 59889
        60107 60113 60237 60319 60333 60334 60386 60499 60558 60638 60733
        60859 60860 61157 61261 61387 61408 61485 61620 61627 61732 61977
        61978 62002 62042 62282 62596 62686 62715 68723 71406
        """
    ),
    "tanf": _ids(
        """
        56996 57016 57029 57057 57077 57173 57317 57363 57394 57694 57839
        57843 58102 58127 58171 58181 58192 58233 58303 58358 58603 58663
        58733 58765 58879 58903 58941 59012 59054 59224 59295 59318 59335
        59447 59497 59579 59607 59667 59771 59806 59827 59900 60032 60080
        60096 60198 60303 60342 60374 60397 60415 60509 60651 60690 60726
        60755 60810 60816 60935 61123 61133 61665 61760 61779 61816 61865
        61987 62230 62327 62363 62748 62869
        """
    ),
    "self_employment_tanf": _ids(
        """
        56991 57078 57302 57341 57491 57511 57529 57797 57845 57891 58027
        58394 58475 58612 58771 58835 59009 59014 59057 59435 59479 59502
        59946 59993 60124 60218 60441 60756 60777 60978 61018 61251 61315
        61411 61495 62072
        """
    ),
    "period_self_employment": _ids("58098 58520 59982 60109 60323"),
    "period_tanf": _ids(
        """
        57232 57252 57642 57658 58146 58272 58536 58833 58946 59043 59309
        59809 59988 60221 60358 60555 60557 60785 60931 61390 61433 61529
        62388 62433 62759 62763 62880
        """
    ),
    "period_self_employment_tanf": _ids(
        "56920 57027 58088 58210 59120 59258 59593 59608 60409"
    ),
}

# These output-closing income cases have a second, material deduction mismatch.
# They remain unexplained rather than relying on offsetting errors.
TRACE_DEDUCTION_CONFOUNDS = _ids("58879 59946 60237")

MEDICAL_BRIDGE = _ids("57453 59914 59967")
DISABILITY_CAP_BRIDGE = _ids("56995 58732 61918 61953 62479 62602")

EXPECTED_NEW_ROWS = 345
EXPECTED_REMAINING_ROWS = 96


class _DispositionDumper(yaml.SafeDumper):
    pass


def _represent_string(
    dumper: yaml.SafeDumper,
    value: str,
) -> yaml.nodes.ScalarNode:
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_DispositionDumper.add_representer(str, _represent_string)


def _round_half_up(value: float) -> int:
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _round_cents(value: float) -> float:
    return round(float(value), 2)


def _close(values: dict[str, Any], case: dict[str, Any]) -> bool:
    return (
        abs(float(values["snap"]) - case["report"]["axiom_benefit"])
        <= TOLERANCE
        and bool(values["is_snap_eligible"])
        == case["report"]["axiom_eligible"]
    )


def _exact_baseline(case: dict[str, Any]) -> bool:
    check = case["checks"]["live_baseline"]
    return bool(
        check["pe_benefit_matches_report"]
        and check["pe_eligibility_matches_report"]
    )


def _se_guard(case: dict[str, Any]) -> bool:
    pe = case["live_pe"]
    axiom = case["axiom_evidence"]["inputs"]
    return (
        float(pe["self_employment_income"]) > 0.01
        and abs(float(axiom["earned_income"]) * 12 - float(pe["employment_income"]))
        < SOURCE_TOLERANCE
    )


def _tanf_guard(case: dict[str, Any]) -> bool:
    pe = case["live_pe"]
    axiom = case["axiom_evidence"]["inputs"]
    return (
        float(pe["tanf"]) > 0.01
        and abs(float(pe["ca_tanf"]) - float(pe["tanf"])) < SOURCE_TOLERANCE
        and abs(
            float(axiom["unearned_income"]) * 12
            - (float(pe["snap_unearned_income"]) - float(pe["tanf"]))
        )
        < SOURCE_TOLERANCE
    )


def _compact_value(
    compact: dict[str, Any],
    surface: str,
    suffix: str,
) -> float | bool:
    matches = [
        row["v"] for row in compact[surface] if row["n"].endswith(suffix)
    ]
    if len(matches) != 1:
        raise ValueError(
            f"{compact['id']} has {len(matches)} compact values ending {suffix}"
        )
    return matches[0]


def _unexplained_rows(report: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {}
    for row in report["mismatches"]:
        if row.get("disposition") is None:
            rows.setdefault(row["case_id"], []).append(row)
    return rows


def _pinned(row: dict[str, Any]) -> dict[str, Any]:
    pinned = {"left": row["left"], "right": row["right"]}
    if isinstance(row.get("difference"), int | float) and not isinstance(
        row.get("difference"), bool
    ):
        pinned["difference"] = row["difference"]
    return pinned


def _entry(
    *,
    row: dict[str, Any],
    mechanism_id: str,
    disposition: str,
    linked_issue: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    concept_name = (
        "benefit" if row["concept"] == BENEFIT_CONCEPT else "eligibility"
    )
    return {
        "id": f"ca-362-{mechanism_id}-{row['case_id']}-{concept_name}",
        "concept": row["concept"],
        "case_id": row["case_id"],
        "kind": row["kind"],
        "disposition": disposition,
        "linked_issue": linked_issue,
        "evidence": copy.deepcopy(evidence),
        "expires_on_source_change": True,
        "pinned": _pinned(row),
    }


def _static_se_evidence(
    case: dict[str, Any],
    compact: dict[str, Any],
) -> dict[str, Any]:
    case_id = case["case_id"]
    if not _exact_baseline(case) or not _se_guard(case):
        raise ValueError(f"{case_id}: static SE proof lost baseline/source guard")
    if case["report"] != {
        "axiom_eligible": True,
        "pe_eligible": False,
        "axiom_benefit": case["report"]["axiom_benefit"],
        "pe_benefit": 0.0,
    }:
        raise ValueError(f"{case_id}: static SE proof no longer has A-only shape")

    axiom_inputs = case["axiom_evidence"]["inputs"]
    axiom_outputs = case["axiom_evidence"]["outputs"]
    se_monthly = 0.6 * float(case["live_pe"]["self_employment_income"]) / 12
    corrected_earned = _round_cents(
        float(axiom_inputs["earned_income"]) + se_monthly
    )
    corrected_gross = _round_cents(
        corrected_earned + float(axiom_inputs["unearned_income"])
    )
    gross_limit = float(
        _compact_value(
            compact,
            "o",
            "#snap_gross_income_limit_130_percent_fpl_48_states_dc",
        )
    )
    net_limit = float(
        _compact_value(
            compact,
            "o",
            "#snap_net_income_limit_100_percent_fpl_48_states_dc",
        )
    )

    if case_id in STATIC_SE_GROSS:
        corrected_gate_value = corrected_gross
        limit = gross_limit
        route = "gross"
    else:
        earned_deduction = math.floor(0.2 * corrected_earned)
        pre_shelter = max(
            corrected_gross
            - float(axiom_outputs["standard_deduction"])
            - earned_deduction
            - float(axiom_inputs["dependent_care_deduction"])
            - float(axiom_inputs["child_support_deduction"])
            - float(axiom_inputs["medical_deduction"]),
            0,
        )
        shelter = (
            float(axiom_inputs["housing_cost"])
            + float(axiom_outputs["utility_allowance"])
        )
        shelter_deduction = _round_half_up(
            max(shelter - 0.5 * pre_shelter, 0)
        )
        corrected_gate_value = max(pre_shelter - shelter_deduction, 0)
        limit = net_limit
        route = "net"

    margin = corrected_gate_value - limit
    if margin <= 0:
        raise ValueError(
            f"{case_id}: corrected Axiom {route} gate does not fail ({margin})"
        )

    return {
        "upstream_url": ISSUE_362,
        "mechanism": (
            "Exact-household Axiom-side counterfactual. The committed bridge "
            f"gave Axiom monthly earned income {axiom_inputs['earned_income']} "
            "from wages alone while live PE-US 1.767.3 carries annual "
            f"self-employment income {case['live_pe']['self_employment_income']}. "
            "Applying the landed 4b4e34c1 projection (60 percent of gross "
            f"self-employment) makes Axiom {route} income "
            f"{corrected_gate_value}, above its {route} limit {limit} by "
            f"{margin}. Corrected Axiom eligibility and benefit are therefore "
            "false/$0, exactly the pinned PolicyEngine result."
        ),
        "arithmetic": [
            {
                "expression": f"{corrected_gate_value} - {limit}",
                "equals": margin,
                "tolerance": 1e-7,
            }
        ],
        "sources": [
            "dashboard/public/data/axiom-policyengine-ca-snap-ecps.json",
            "scripts/trace_ca_snap_residuals.py",
            SE_FIX,
            SNAP_INCOME,
        ],
    }


def _minor_defect_evidence(case: dict[str, Any]) -> dict[str, Any]:
    if not _exact_baseline(case):
        raise ValueError(f"{case['case_id']}: minor repro baseline drifted")
    pe = case["live_pe"]
    axiom = case["axiom_evidence"]
    if (
        max(case["ages"]) > 17
        or float(pe["employment_income"]) <= 0
        or abs(float(pe["snap_earned_income"])) > 0.01
        or case["report"]["axiom_eligible"]
        or not case["report"]["pe_eligible"]
    ):
        raise ValueError(f"{case['case_id']}: minor earnings signature changed")
    input_delta = (
        float(pe["employment_income"]) / 12
        - float(axiom["inputs"]["earned_income"])
    )
    if abs(input_delta) > 0.01:
        raise ValueError(f"{case['case_id']}: minor wages do not align")
    return {
        "upstream_url": ISSUE_9157,
        "mechanism": (
            "Live minimal repro on PE 4.18.9 / PE-US 1.767.3 / Core 3.30.3. "
            f"The household ages are {case['ages']} and annual employment is "
            f"{pe['employment_income']}, but PE SNAP earned income is "
            f"{pe['snap_earned_income']}. Axiom receives the same wages as "
            f"{axiom['inputs']['earned_income']} monthly, counts them, fails "
            "the income gate, and returns false/$0. PE excludes K-12 earnings "
            "without the required co-resident-parent or parental-control "
            "condition; the exact pinned PE result remains eligible/positive."
        ),
        "arithmetic": [
            {
                "expression": (
                    f"{float(pe['employment_income'])} / 12 - "
                    f"{float(axiom['inputs']['earned_income'])}"
                ),
                "equals": input_delta,
                "tolerance": 1e-7,
            }
        ],
        "sources": [
            "dashboard/public/data/axiom-policyengine-ca-snap-ecps.json",
            "scripts/trace_ca_snap_residuals.py",
            ISSUE_9157,
            SNAP_STUDENT,
        ],
    }


def _select_trace_counterfactual(
    case: dict[str, Any],
    classification: str,
) -> tuple[str, dict[str, Any]]:
    annual = case["counterfactuals"]
    january = case["requested_month_counterfactuals"]
    candidates: list[tuple[str, dict[str, Any]]]
    if classification == "period":
        candidates = [("january_baseline", case["requested_month_pe"])]
    elif classification == "self_employment":
        candidates = [
            ("annual_zero_self_employment", annual["zero_self_employment"]),
            (
                "annual_zero_self_employment_and_tanf",
                annual["zero_self_employment_and_tanf"],
            ),
        ]
    elif classification == "tanf":
        candidates = [("annual_zero_tanf", annual["zero_tanf"])]
    elif classification == "self_employment_tanf":
        candidates = [
            (
                "annual_zero_self_employment_and_tanf",
                annual["zero_self_employment_and_tanf"],
            )
        ]
    elif classification == "period_self_employment":
        candidates = [
            ("january_zero_self_employment", january["zero_self_employment"]),
            (
                "january_zero_self_employment_and_tanf",
                january["zero_self_employment_and_tanf"],
            ),
        ]
    elif classification == "period_tanf":
        candidates = [("january_zero_tanf", january["zero_tanf"])]
    elif classification == "period_self_employment_tanf":
        candidates = [
            (
                "january_zero_self_employment_and_tanf",
                january["zero_self_employment_and_tanf"],
            )
        ]
    else:
        raise ValueError(classification)
    for label, values in candidates:
        if _close(values, case):
            return label, values
    raise ValueError(
        f"{case['case_id']}: no {classification} counterfactual closes"
    )


def _trace_evidence(
    case: dict[str, Any],
    classification: str,
) -> tuple[str, dict[str, Any]]:
    case_id = case["case_id"]
    if not _exact_baseline(case):
        raise ValueError(f"{case_id}: traced disposition has baseline drift")
    label, values = _select_trace_counterfactual(case, classification)
    uses_se = "self_employment" in classification
    uses_tanf = "tanf" in classification
    uses_period = "period" in classification
    if uses_se and not _se_guard(case):
        raise ValueError(f"{case_id}: SE source guard failed")
    if uses_tanf and not (
        _tanf_guard(case)
        or float(
            case["counterfactuals"]["zero_self_employment"].get("tanf", 0)
        )
        > 0.01
        or float(
            case["requested_month_counterfactuals"][
                "zero_self_employment"
            ].get("tanf", 0)
        )
        > 0.01
    ):
        raise ValueError(f"{case_id}: TANF source guard failed")

    pe = case["live_pe"]
    axiom = case["axiom_evidence"]["inputs"]
    delta = float(values["snap"]) - case["report"]["axiom_benefit"]
    sources = [
        "dashboard/public/data/axiom-policyengine-ca-snap-ecps.json",
        "scripts/trace_ca_snap_residuals.py",
        SNAP_INCOME,
    ]
    details = []
    linked_issue = ISSUE_362
    if uses_se:
        details.append(
            "PE carries annual self-employment "
            f"{pe['self_employment_income']} while Axiom earned input "
            f"{axiom['earned_income']} monthly equals PE wages/12"
        )
        sources.append(SE_FIX)
    if uses_tanf:
        details.append(
            "PE's state/aggregate TANF is omitted from Axiom unearned income "
            f"(baseline annual TANF {pe['tanf']})"
        )
        sources.append(ISSUE_397)
        linked_issue = ISSUE_397
    if uses_period:
        details.append(
            "the report uses the calendar-year monthly average although the "
            "suite requests January 2026"
        )
        sources.append(PR_416)
        if not uses_tanf and not uses_se:
            linked_issue = PR_416
    mechanism = (
        "Exact-household live bridge counterfactual on PE 4.18.9 / PE-US "
        "1.767.3 / Core 3.30.3. The live annual bridge reproduces the pinned "
        f"PE amount exactly. {'; '.join(details)}. Counterfactual {label} "
        f"keeps eligibility at {bool(values['is_snap_eligible'])} and gives "
        f"SNAP {values['snap']} versus Axiom "
        f"{case['report']['axiom_benefit']} (delta {delta}), within the "
        "$7 suite tolerance."
    )
    return linked_issue, {
        "upstream_url": linked_issue,
        "mechanism": mechanism,
        "arithmetic": [
            {
                "expression": (
                    f"{float(values['snap'])} - "
                    f"{case['report']['axiom_benefit']}"
                ),
                "equals": delta,
                "tolerance": 1e-7,
            }
        ],
        "sources": list(dict.fromkeys(sources)),
    }


def _axiom_allotment(
    case: dict[str, Any],
    *,
    medical: float = 0,
    include_self_employment: bool = False,
    cap_shelter: bool = False,
) -> dict[str, float]:
    inputs = case["axiom_evidence"]["inputs"]
    outputs = case["axiom_evidence"]["outputs"]
    earned = float(inputs["earned_income"])
    if include_self_employment:
        earned = _round_cents(
            earned + 0.6 * float(case["live_pe"]["self_employment_income"]) / 12
        )
    gross = _round_cents(earned + float(inputs["unearned_income"]))
    earned_deduction = math.floor(0.2 * earned)
    pre_shelter = max(
        gross
        - float(outputs["standard_deduction"])
        - earned_deduction
        - float(inputs["dependent_care_deduction"])
        - float(inputs["child_support_deduction"])
        - medical,
        0,
    )
    shelter = float(inputs["housing_cost"]) + float(outputs["utility_allowance"])
    excess_shelter = _round_half_up(max(shelter - 0.5 * pre_shelter, 0))
    shelter_deduction = (
        min(excess_shelter, 744) if cap_shelter else excess_shelter
    )
    net = max(pre_shelter - shelter_deduction, 0)
    contribution = math.ceil(0.3 * net)
    maximum = float(case["requested_month_pe"]["snap_max_allotment"])
    minimum = float(case["requested_month_pe"]["snap_min_allotment"])
    benefit = max(maximum - contribution, minimum)
    return {
        "earned": earned,
        "gross": gross,
        "pre_shelter": pre_shelter,
        "excess_shelter": excess_shelter,
        "shelter_deduction": shelter_deduction,
        "net": net,
        "contribution": contribution,
        "benefit": benefit,
    }


def _medical_evidence(case: dict[str, Any]) -> dict[str, Any]:
    if not _exact_baseline(case):
        raise ValueError(f"{case['case_id']}: medical baseline drift")
    medical = float(
        case["requested_month_pe"]["snap_excess_medical_expense_deduction"]
    )
    if medical <= 0 or float(case["axiom_evidence"]["inputs"]["medical_deduction"]):
        raise ValueError(f"{case['case_id']}: medical input signature changed")
    corrected = _axiom_allotment(case, medical=medical)
    jan_pe = float(case["requested_month_pe"]["snap"])
    delta = corrected["benefit"] - jan_pe
    if abs(delta) > TOLERANCE:
        raise ValueError(f"{case['case_id']}: medical counterfactual misses")
    return {
        "upstream_url": ISSUE_362,
        "mechanism": (
            "Exact-household deduction-stack counterfactual. Axiom receives "
            "zero medical deduction while direct January PE-US 1.767.3 applies "
            f"{medical}. Replaying Axiom's standard, earned, medical, shelter, "
            f"and 30-percent contribution stack gives net {corrected['net']} "
            f"and benefit {corrected['benefit']}; direct January PE is {jan_pe} "
            f"(delta {delta}). The report's annual-average PE amount is also "
            "removed by selecting the requested month."
        ),
        "arithmetic": [
            {
                "expression": f"{corrected['benefit']} - {jan_pe}",
                "equals": delta,
                "tolerance": 1e-7,
            }
        ],
        "sources": [
            "dashboard/public/data/axiom-policyengine-ca-snap-ecps.json",
            "scripts/trace_ca_snap_residuals.py",
            ISSUE_362,
            PR_416,
            SNAP_MEDICAL,
        ],
    }


def _disability_cap_evidence(case: dict[str, Any]) -> dict[str, Any]:
    if not _exact_baseline(case):
        raise ValueError(f"{case['case_id']}: shelter-cap baseline drift")
    if max(case["ages"]) >= 60 or bool(case["live_pe"]["has_usda_elderly_disabled"]):
        raise ValueError(f"{case['case_id']}: USDA disability signature changed")
    if float(case["axiom_evidence"]["outputs"]["shelter_deduction"]) <= 744:
        raise ValueError(f"{case['case_id']}: Axiom shelter is no longer uncapped")
    include_se = case["case_id"] == "ecps-61953"
    if include_se and not _se_guard(case):
        raise ValueError(f"{case['case_id']}: combined SE guard failed")
    corrected = _axiom_allotment(
        case,
        include_self_employment=include_se,
        cap_shelter=True,
    )
    jan_pe = float(case["requested_month_pe"]["snap"])
    delta = corrected["benefit"] - jan_pe
    if abs(delta) > TOLERANCE:
        raise ValueError(f"{case['case_id']}: shelter-cap counterfactual misses")
    se_clause = (
        " The same replay also adds the landed 60-percent self-employment "
        "projection."
        if include_se
        else ""
    )
    return {
        "upstream_url": ISSUE_362,
        "mechanism": (
            "Exact-household bridge counterfactual. Every member is under 60 "
            "and live PE reports no USDA elderly/disabled member, but Axiom's "
            "generic DISABLED projection uncaps a shelter deduction above "
            "$744. Applying the statutory nonelderly cap and direct January "
            f"parameters gives net {corrected['net']} and benefit "
            f"{corrected['benefit']}, versus January PE {jan_pe} (delta "
            f"{delta}).{se_clause}"
        ),
        "arithmetic": [
            {
                "expression": f"{corrected['benefit']} - {jan_pe}",
                "equals": delta,
                "tolerance": 1e-7,
            }
        ],
        "sources": [
            "dashboard/public/data/axiom-policyengine-ca-snap-ecps.json",
            "axiom_oracles/data/populace_input_mapping.yaml",
            "scripts/trace_ca_snap_residuals.py",
            ISSUE_362,
            PR_416,
            SNAP_DISABILITY,
            SNAP_SHELTER,
            *([SE_FIX] if include_se else []),
        ],
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--trace",
        type=Path,
        help=(
            "Legacy trace receipt to reproduce the historical #423 source; "
            "requires --base-ref."
        ),
    )
    parser.add_argument(
        "--base-ref",
        help="Git ref containing the literal merged #423 disposition set.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "With --base-ref, audit the current literal-base reconciliation. "
            "With --trace, retain the legacy generated-YAML stale check."
        ),
    )
    args = parser.parse_args(argv)
    if args.base_ref is None:
        parser.error("--base-ref is required")
    if args.trace is None and not args.check:
        parser.error("--base-ref without --trace requires --check")
    return args


def _check_current_reconciliation(base_ref: str) -> dict[str, Any]:
    from scripts.reconcile_ca_snap_423_dispositions import check_reconciliation

    return check_reconciliation(base_ref)


def _load_legacy_base_inputs(
    base_ref: str,
) -> tuple[
    str,
    dict[str, Any],
    dict[str, Any],
    dict[str, dict[str, Any]],
    str,
]:
    from scripts.reconcile_ca_snap_423_dispositions import (
        BASE_DISPOSITIONS_RELATIVE_PATH,
        _git_show,
        _load_base_dispositions,
        _sha256,
    )

    commit, existing, _issue_entries = _load_base_dispositions(base_ref)

    report_raw = _git_show(commit, LEGACY_REPORT_RELATIVE_PATH)
    report_digest = _sha256(report_raw)
    if report_digest != LEGACY_REPORT_SHA256:
        raise ValueError(
            "literal-base legacy report sha256 mismatch: "
            f"expected {LEGACY_REPORT_SHA256}, got {report_digest}"
        )
    report = json.loads(report_raw)
    mismatches = report.get("mismatches")
    if not isinstance(mismatches, list):
        raise ValueError("literal-base legacy report mismatches must be a list")
    if len(mismatches) != EXPECTED_LEGACY_REPORT_ROWS:
        raise ValueError(
            "literal-base legacy report row count mismatch: "
            f"expected {EXPECTED_LEGACY_REPORT_ROWS}, got {len(mismatches)}"
        )

    issue_annotations = 0
    for row in mismatches:
        disposition = row.get("disposition")
        if isinstance(disposition, dict) and str(
            disposition.get("id", "")
        ).startswith("ca-362-"):
            issue_annotations += 1
            row["disposition"] = None
    if issue_annotations != EXPECTED_LEGACY_ISSUE_362_ANNOTATIONS:
        raise ValueError(
            "literal-base legacy report issue #362 annotation mismatch: "
            f"expected {EXPECTED_LEGACY_ISSUE_362_ANNOTATIONS}, "
            f"got {issue_annotations}"
        )
    unexplained = sum(row.get("disposition") is None for row in mismatches)
    if unexplained != EXPECTED_LEGACY_UNEXPLAINED_ROWS:
        raise ValueError(
            "literal-base legacy unexplained-row mismatch: "
            f"expected {EXPECTED_LEGACY_UNEXPLAINED_ROWS}, got {unexplained}"
        )

    index_path = f"{LEGACY_CASE_DIR_RELATIVE_PATH}/index.json"
    index_raw = _git_show(commit, index_path)
    index_digest = _sha256(index_raw)
    if index_digest != LEGACY_CASE_INDEX_SHA256:
        raise ValueError(
            "literal-base legacy compact index sha256 mismatch: "
            f"expected {LEGACY_CASE_INDEX_SHA256}, got {index_digest}"
        )
    index = json.loads(index_raw)
    chunk_count = index.get("chunks")
    if not isinstance(chunk_count, int) or chunk_count <= 0:
        raise ValueError("literal-base legacy compact chunk count is invalid")

    chunks_digest = hashlib.sha256()
    compact: dict[str, dict[str, Any]] = {}
    for chunk_number in range(chunk_count):
        chunk_path = (
            f"{LEGACY_CASE_DIR_RELATIVE_PATH}/chunk-{chunk_number}.json"
        )
        chunk_raw = _git_show(commit, chunk_path)
        chunks_digest.update(chunk_raw)
        chunk_rows = json.loads(chunk_raw)
        if not isinstance(chunk_rows, list):
            raise ValueError(f"{chunk_path} must contain a list")
        for case in chunk_rows:
            case_id = case.get("id")
            if not isinstance(case_id, str) or not case_id:
                raise ValueError(f"{chunk_path} contains a case without an id")
            if case_id in compact:
                raise ValueError(f"duplicate legacy compact case {case_id}")
            if not isinstance(case.get("o"), list):
                raise ValueError(
                    f"{case_id} does not use the pinned legacy compact schema"
                )
            compact[case_id] = case
    observed_chunks_digest = chunks_digest.hexdigest()
    if observed_chunks_digest != LEGACY_CASE_CHUNKS_SHA256:
        raise ValueError(
            "literal-base legacy compact chunks sha256 mismatch: "
            f"expected {LEGACY_CASE_CHUNKS_SHA256}, "
            f"got {observed_chunks_digest}"
        )
    if len(compact) != EXPECTED_LEGACY_CASES:
        raise ValueError(
            "literal-base legacy compact case count mismatch: "
            f"expected {EXPECTED_LEGACY_CASES}, got {len(compact)}"
        )

    expected_text = _git_show(
        commit,
        BASE_DISPOSITIONS_RELATIVE_PATH,
    ).decode()
    return commit, report, existing, compact, expected_text


def _run_legacy(args: argparse.Namespace) -> int:
    assert args.trace is not None
    assert args.base_ref is not None
    trace_raw = args.trace.read_bytes()
    trace_digest = hashlib.sha256(trace_raw).hexdigest()
    if trace_digest != LEGACY_TRACE_SHA256:
        raise ValueError(
            "legacy trace sha256 mismatch: "
            f"expected {LEGACY_TRACE_SHA256}, got {trace_digest}"
        )
    trace = json.loads(trace_raw)
    if trace["runtime"] != {
        "policyengine": "4.18.9",
        "policyengine-core": "3.30.3",
        "policyengine-us": "1.767.3",
    }:
        raise ValueError(f"unexpected trace runtime: {trace['runtime']}")

    (
        _base_commit,
        report,
        existing,
        compact,
        expected_text,
    ) = _load_legacy_base_inputs(args.base_ref)
    cases = {case["case_id"]: case for case in trace["cases"]}
    unexplained = _unexplained_rows(report)
    selected: dict[tuple[str, str, str], dict[str, Any]] = {}

    def add_case(
        case_id: str,
        mechanism_id: str,
        disposition: str,
        linked_issue: str,
        evidence: dict[str, Any],
    ) -> None:
        for row in unexplained.get(case_id, []):
            key = (case_id, row["concept"], row["kind"])
            if key in selected:
                raise ValueError(f"duplicate new disposition: {key}")
            selected[key] = _entry(
                row=row,
                mechanism_id=mechanism_id,
                disposition=disposition,
                linked_issue=linked_issue,
                evidence=evidence,
            )

    for case_id in sorted(STATIC_SE):
        add_case(
            case_id,
            "self-employment-forward",
            "bridge_artifact",
            ISSUE_362,
            _static_se_evidence(cases[case_id], compact[case_id]),
        )

    for case_id in sorted(MINOR_DEFECT):
        add_case(
            case_id,
            "pe-student-earnings",
            "upstream_engine_gap",
            ISSUE_9157,
            _minor_defect_evidence(cases[case_id]),
        )

    seen_trace_cases: set[str] = set()
    for classification, case_ids in TRACE_CLASSES.items():
        overlap = seen_trace_cases & case_ids
        if overlap:
            raise ValueError(f"trace classes overlap: {sorted(overlap)}")
        seen_trace_cases.update(case_ids)
        for case_id in sorted(case_ids):
            if case_id in STATIC_SE or case_id in TRACE_DEDUCTION_CONFOUNDS:
                continue
            linked_issue, evidence = _trace_evidence(
                cases[case_id],
                classification,
            )
            add_case(
                case_id,
                classification.replace("_", "-"),
                "bridge_artifact",
                linked_issue,
                evidence,
            )

    for case_id in sorted(MEDICAL_BRIDGE):
        add_case(
            case_id,
            "medical-input",
            "bridge_artifact",
            ISSUE_362,
            _medical_evidence(cases[case_id]),
        )

    for case_id in sorted(DISABILITY_CAP_BRIDGE):
        add_case(
            case_id,
            "disability-shelter-cap",
            "bridge_artifact",
            ISSUE_362,
            _disability_cap_evidence(cases[case_id]),
        )

    if len(selected) != EXPECTED_NEW_ROWS:
        raise ValueError(
            f"expected {EXPECTED_NEW_ROWS} new rows, selected {len(selected)}"
        )
    remaining = sum(len(rows) for rows in unexplained.values()) - len(selected)
    if remaining != EXPECTED_REMAINING_ROWS:
        raise ValueError(
            f"expected {EXPECTED_REMAINING_ROWS} remaining rows, got {remaining}"
        )

    base_entries = [
        entry
        for entry in existing["entries"]
        if not str(entry.get("id", "")).startswith("ca-362-")
    ]
    existing_ids = {entry["id"] for entry in base_entries}
    additions = [
        selected[key]
        for key in sorted(
            selected,
            key=lambda item: (
                int(item[0].removeprefix("ecps-")),
                item[1],
                item[2],
            ),
        )
    ]
    duplicate_ids = existing_ids & {entry["id"] for entry in additions}
    if duplicate_ids:
        raise ValueError(f"generated IDs already exist: {sorted(duplicate_ids)}")

    output = {
        **{key: value for key, value in existing.items() if key != "entries"},
        "updated": "2026-07-28",
        "entries": [*base_entries, *additions],
    }
    text = yaml.dump(
        output,
        Dumper=_DispositionDumper,
        sort_keys=False,
        allow_unicode=True,
        width=100,
    )
    if args.check:
        if expected_text != text:
            raise SystemExit(
                "literal-base ca-snap-ecps dispositions do not reproduce"
            )
    else:
        DISPOSITIONS_PATH.write_text(text)
    print(
        f"Validated {len(additions)} evidence-pinned issue #362 rows; "
        f"{remaining} remain unexplained"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.trace is None:
        assert args.base_ref is not None
        receipt = _check_current_reconciliation(args.base_ref)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    return _run_legacy(args)


if __name__ == "__main__":
    raise SystemExit(main())
