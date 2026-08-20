#!/usr/bin/env python3
"""Program certificate: one generated answer per certification question.

Today a certification question answered by reading harness code produced
confidently wrong answers in both directions about the same suite. The
certificate is the structural fix: for each (jurisdiction, program), one
committed document carrying the verdicts, where every field names the artifact
and sha it derives from, and ``--check`` recomputes the whole thing. If a
question about a program's validation posture is not answerable from its
certificate, that is a certificate defect to file — not a prompt to go read
adapters.

Two evidence modes, stated per claim:

* ``computed`` — this script invokes the named producer's pure validator and
  re-derives the value from committed in-repo artifacts; drift fails
  ``--check``. Producer integration gates may additionally replay external,
  commit-pinned toolchains.
* ``attested`` — the value is carried from a sha-pinned external receipt.
  Attested is scaffolding, not certification; the roadmap is monotone
  conversion of attested claims to computed ones.

Oracle types matter to the verdict. ``reference`` oracles (another
implementation) can be wrong in code, so their unexplained mismatches block
the conformant verdict. ``reality`` oracles (recorded administrative outcomes)
cannot have bugs filed against them; their disagreements are reported as
leads and do not block, but are never hidden.

Modes::

    uv run python scripts/certify.py            # write certificates + summary
    uv run python scripts/certify.py --check    # CI: fail on drift
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path
from types import ModuleType

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
#: A git object id: 40 lowercase hex chars with at least one of a-f (a
#: decimal-only string is not a realistic commit and is the !!str-digit forgery
#: shape from delta-audit #8). Shared shape with closure_ledger/_HEX_GIT_SHA and
#: executable_reproduction/HEX_40.
GIT_SHA = re.compile(r"^(?=[0-9a-f]{40}$)(?=.*[a-f])[0-9a-f]{40}$")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.comparison.dispositions import (  # noqa: E402
    validate_dispositions,
)
from axiom_oracles.evidence import validate_suite_evidence  # noqa: E402

DATA_DIR = REPO_ROOT / "dashboard" / "public" / "data"
CENSUS_PATH = REPO_ROOT / "conformance" / "exercise-census.json"
OUT_DIR = REPO_ROOT / "certificates"
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from nz_programs import SINGLE_PERSON_PROGRAMS  # noqa: E402

SCHEMA = "axiom_oracles.program_certificate.v1"
_NZ_REPORT_CACHE: dict | None = None

#: Program registry. One entry per certified (jurisdiction, program).
#: ``suites`` lists every comparison that bears on the program, typed.
#: ``attested`` carries sha-pinned claims from outside this repo, verbatim,
#: with their provenance; nothing here is recomputable in-repo yet.
PROGRAMS: dict[str, dict] = {
    "us-co/snap": {
        "period": "2026-01",
        "suites": [
            {
                "suite": "co-snap-ecps",
                "oracle_type": "reference",
                "oracle": "policyengine-us 1.705.1 over the populace population",
                "report": "dashboard/public/data/axiom-policyengine-co-snap-ecps.json",
            },
            {
                "suite": "co-snap-qc",
                "oracle_type": "reality",
                "oracle": "USDA SNAP QC FY2024 administrative sample "
                "(rulespec overlay, per-patch citations in report provenance)",
                "report": "dashboard/public/data/axiom-snapqc-co-snap.json",
            },
        ],
        "attested": {
            "closed": {
                "value": {
                    "state_root": "10 CCR 2506-1: 281/289 sections encoded, "
                    "0 untested modules, 6 container headings, 2 pending review",
                    "federal_reg_root": "7 CFR 273 fully ingested "
                    "(2026-07-15-title-7-part-273, 39 provisions); "
                    "11/30 sections carry any encoding",
                    "federal_statute_root": "7 USC ch. 51 ingested (827); "
                    "21 modules encoded, remainder unclassified",
                    "frontier": "72 boundary input facts, 0 cross-program imports",
                },
                "source": "TheAxiomFoundation/ops closure/co-snap-closure-2026-07-26.md",
                "source_commits": ["ee4bcfe6aa9b", "968e9e2805e2"],
                "status": "prototype",
            },
            "executable": {
                "value": {
                    "tuple": "engine v0.1.1 x program-artifacts-59a10dab866e",
                    "loads_and_runs": True,
                    "golden_values_reproduce": True,
                    "detail": "stranger-path rc=0: snap_eligible=holds, gated "
                    "snap_allotment=478, snap_net_income=226 (the corrected "
                    "statutory figure — the prior certified 226.50 was the "
                    "un-rounded value; 7 CFR 273.10(e)(1)(ii)(A)). Parity "
                    "local leg PASS; BOM execution.golden_values PASS. "
                    "Cross-surface still red: the hosted API returns the "
                    "un-rounded 226.5 (axiom-api#115).",
                },
                "source": "TheAxiomFoundation/ops launch-readiness/parity/"
                "fixtures/GOLDEN-HOUSEHOLD.md (ops#6)",
                "source_commit": "9f680b7",
                "status": "attested_pass",
            },
        },
    },
    "dk/boerne-og-ungeydelse": {
        "period": "2025",
        "suites": [
            {
                "suite": "dk-child-youth-benefit",
                "oracle_type": "reference",
                "oracle": "EUROMOD J2.0+ DK_2025 (public JRC release, "
                "DK_training_data synthetic rows; pinned engine 05eac9d2)",
                "report": "dashboard/public/data/"
                "axiom-euromod-dk-child-youth-benefit.json",
            },
            {
                "suite": "dk-child-youth-benefit-2023",
                "oracle_type": "reference",
                "oracle": "EUROMOD J2.0+ DK_2023 (the ec-jrc#19 supplement "
                "witness year)",
                "report": "dashboard/public/data/"
                "axiom-euromod-dk-child-youth-benefit-2023.json",
            },
            {
                "suite": "dk-child-youth-benefit-couple",
                "oracle_type": "reference",
                "oracle": "EUROMOD J2.0+ DK_2025 couple household (the "
                "ec-jrc#18 spousal-taper witness)",
                "report": "dashboard/public/data/"
                "axiom-euromod-dk-child-youth-benefit-couple.json",
            },
        ],
        # DK is the first program with committed, independently checkable
        # closed and executable producer artifacts. Ordinary certification is
        # hermetic: it validates those receipts and their in-repo inputs. The
        # opt-in ``--verify-producers`` integration gate additionally re-derives
        # closure from external Git sources and recompiles/replays executable.
        # The jurisdiction scoreboard (conformance/dk.yaml) separately records
        # the honest full-parity burndown.
        "computed": {
            "closed": {
                "artifact": ("conformance/closure/dk-boerne-og-ungeydelse.yaml"),
                "producer": "scripts/closure_ledger.py",
            },
            "executable": {
                "artifact": ("conformance/executable/dk-boerne-og-ungeydelse.json"),
                "producer": "scripts/executable_reproduction.py",
            },
        },
        "attested": {},
    },
    "us/tariff-duty": {
        "period": "2026",
        "suites": [
            {
                "suite": "us-tariff-schedule",
                "oracle_type": "reference",
                "oracle": (
                    "Yale Budget Lab tariff-rate-tracker legal-date statutory "
                    "panel at c4307e514196618afcbf88cf7fd33746417eeabf"
                ),
                "report": "conformance/detail/us-tariff-schedule.json",
                "report_contract": "us_tariff_schedule_v1",
            }
        ],
        "scope_from_suite": "us-tariff-schedule",
        "computed": {
            "closed": {
                "artifact": "conformance/closure/us-tariff-duty.yaml",
                "producer": "scripts/closure_ledger.py",
                "contract": "us_tariff_closure_v1",
                "include_burndown": True,
            },
            "executable": {
                "artifact": "conformance/executable/us-tariff-witness.json",
                "producer": "scripts/tariff_executable_reproduction.py",
            },
        },
        "attested": {},
    },
}

NZ_AGGREGATION_BLOCKER = (
    "host-side aggregation pin: rulespec-nz#108 prerequisite 2 remains open; "
    "person/child/family aggregation is still performed by the comparison "
    "harness because the compiled composition carries no relations. Structural "
    "fix axiom-rules-engine#134 is not yet ratified."
)
NZ_ACC_LOCALITY_BLOCKER = (
    "person-locality is not yet proven — the two-endpoint perturbation cannot "
    "exclude conditional/default-dormant cross-person dependencies "
    "(adversarial review S1); structural cure = axiom-rules-engine#134 stage 2 "
    "(prototype exists on feat/unit-derivation-stage2)."
)
for _nz_program in (
    "nz/acc-earners-levy",
    "nz/accommodation-supplement",
    "nz/income-tax",
    "nz/independent-earner-tax-credit",
    "nz/main-benefits",
    "nz/winter-energy-payment",
    "nz/working-for-families",
):
    PROGRAMS[_nz_program] = {
        "period": "2026-04-01/2027-03-31",
        "suites": [
            {
                "suite": "nz-treasury-incomeexplorer",
                "view": _nz_program,
                "oracle_type": "reference",
                "oracle": "NZ Treasury IncomeExplorer raw emtr() at "
                "741a6ca4f5d27b1dc00b43dc395e39ffc4040a4b (TY27_BEFU25)",
                "report": "dashboard/public/data/nz-treasury-incomeexplorer.json",
            }
        ],
        "computed": {
            "closed": {
                "artifact": "closure/nz/summary.json",
                "producer": "scripts/nz_closure.py",
                "external_verification": "hermetic_program_scoped",
            },
            "executable": {
                "artifact": ("conformance/executable/nz-treasury-incomeexplorer.json"),
                "producer": "scripts/nz_executable_reproduction.py",
                "external_verification": "dedicated_source_build_ci",
            },
            "exercise_denominator": {
                "producer": "scripts/nz_exercise_denominator.py",
            },
        },
        "attested_exercise_catalog_receipt": (
            "comparisons/nz-treasury-incomeexplorer/source-comparison.json"
        ),
        "certified_false_when_blocked": True,
        "blockers": (
            [NZ_ACC_LOCALITY_BLOCKER]
            if _nz_program in SINGLE_PERSON_PROGRAMS
            else [NZ_AGGREGATION_BLOCKER]
        ),
        "single_person_attestation": (
            "comparisons/nz-treasury-incomeexplorer/single-person-attestations.json"
            if _nz_program in SINGLE_PERSON_PROGRAMS
            else None
        ),
    }


#: The only disposition kinds with defined meaning. An unrecognized kind in a
#: report's counts is a defect, not a silently-ignored extra column.
KNOWN_DISPOSITION_KINDS = {
    "explained_residual",
    "upstream_engine_gap",
    "bridge_artifact",
    "axiom_encoding_gap",
    "unexplained",
}


def _count(raw, field: str, defects: list[str], suite: str) -> int:
    """Read a count, recording invalidity instead of silently zeroing it.

    Coercing junk to 0 masks defects: `error_count: "one"` became "no errors",
    a negative count cancelled a real one, and `mismatch_count: "one"` hid a
    stored mismatch (round-2 audit finding 2). A count must be a non-negative
    integer or it is a producer defect, stated as such.
    """
    if raw is None:
        return 0
    if isinstance(raw, bool):
        defects.append(f"{suite}: {field} is a boolean, not a count")
        return 0
    if isinstance(raw, int):
        if raw < 0:
            defects.append(f"{suite}: {field} is negative ({raw})")
            return 0
        return raw
    if isinstance(raw, float) and raw.is_integer() and raw >= 0:
        return int(raw)
    defects.append(f"{suite}: {field} is not a non-negative integer ({raw!r})")
    return 0


def _dispositions_suite(path: Path) -> str | None:
    """The suite a valid, nonempty dispositions file declares, else None.

    Hashing a file proves which bytes were cited. Only full schema validation
    proves that those bytes are a dispositions document with entries rather
    than an unrelated same-suite artifact.
    """
    try:
        import yaml
    except ModuleNotFoundError:  # pragma: no cover - environment guard
        sys.exit(
            "certify needs PyYAML to suite-bind dispositions files. Run under "
            "the project env (`uv run python scripts/certify.py`)."
        )
    try:
        payload = yaml.safe_load(path.read_text())
    except Exception:
        return None
    errors = validate_dispositions(
        payload,
        path_label=str(path),
        repo_root=REPO_ROOT,
    )
    if errors:
        return None
    return str(payload["suite"])


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _rederived_nz_report() -> dict:
    """Recompute the unified NZ report from its sha-pinned input receipt."""

    global _NZ_REPORT_CACHE
    if _NZ_REPORT_CACHE is None:
        module_path = REPO_ROOT / "scripts" / "nz_incomeexplorer.py"
        module_spec = importlib.util.spec_from_file_location(
            "_certificate_nz_incomeexplorer", module_path
        )
        if module_spec is None or module_spec.loader is None:
            raise ValueError("cannot load the NZ IncomeExplorer verifier")
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        _NZ_REPORT_CACHE = module.build()
    return _NZ_REPORT_CACHE


def _tariff_schedule_suite_verdict(
    entry: dict,
) -> tuple[dict, list[dict], list[str]]:
    """Validate the scale campaign's aggregate, content-addressed report.

    The supervised tariff campaign commits its 19-million-case evidence through
    a shard manifest and reconciliation receipts, so its report intentionally
    uses aggregate ``total/matches/mismatches`` names rather than duplicating
    ordinary dashboard case rows.  Do not promote its typed ``conformant`` flag:
    derive the verdict again from the conserved counts and producer rule.
    """

    defects: list[str] = []
    report_path = _repo_artifact_path(entry["report"], label=entry["suite"])
    try:
        report = _load(report_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{entry['report']} is not readable JSON: {exc}") from exc
    if not isinstance(report, dict):
        raise ValueError(f"{entry['report']} must contain an object")
    if report.get("schema") != "axiom.comparison_report.v2":
        defects.append(f"{entry['suite']}: wrong scale-report schema")
    if report.get("suite") != entry["suite"]:
        defects.append(f"{entry['suite']}: scale report identifies another suite")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        summary = {}
        defects.append(f"{entry['suite']}: summary must be an object")
    total = _count(summary.get("total"), "total", defects, entry["suite"])
    matches = _count(summary.get("matches"), "matches", defects, entry["suite"])
    mismatches = _count(
        summary.get("mismatches"), "mismatches", defects, entry["suite"]
    )
    explained = _count(summary.get("explained"), "explained", defects, entry["suite"])
    unexplained = _count(
        summary.get("unexplained"), "unexplained", defects, entry["suite"]
    )
    engine_errors = _count(
        summary.get("engine_errors"), "engine_errors", defects, entry["suite"]
    )
    if total <= 0:
        defects.append(f"{entry['suite']}: zero comparison units")
    if matches + mismatches != total:
        defects.append(f"{entry['suite']}: scale-report counts do not conserve")
    if explained + unexplained != mismatches:
        defects.append(f"{entry['suite']}: classification counts do not conserve")
    derived_conformant = unexplained == 0 and engine_errors == 0
    scoreboard = report.get("scoreboard")
    if not isinstance(scoreboard, dict):
        defects.append(f"{entry['suite']}: scoreboard must be an object")
    else:
        if scoreboard.get("derivation") != "unexplained == 0 and engine_errors == 0":
            defects.append(f"{entry['suite']}: scoreboard derivation changed")
        if scoreboard.get("conformant") is not derived_conformant:
            defects.append(
                f"{entry['suite']}: scoreboard conformant flag is fabricated"
            )
    if report.get("conformant") is not derived_conformant:
        defects.append(f"{entry['suite']}: report conformant flag is fabricated")
    classification = report.get("classification")
    if not isinstance(classification, dict):
        classification = {}
        defects.append(f"{entry['suite']}: classification must be an object")
    class_attribution = classification.get("class_attribution")
    class_census = classification.get("class_census")
    if not isinstance(class_attribution, dict):
        class_attribution = {}
        defects.append(f"{entry['suite']}: class_attribution must be an object")
    if not isinstance(class_census, dict):
        class_census = {}
        defects.append(f"{entry['suite']}: class_census must be an object")
    axiom_open_classes: dict[str, int] = {}
    for class_name, raw_class in class_attribution.items():
        if not isinstance(raw_class, dict):
            defects.append(
                f"{entry['suite']}: class_attribution.{class_name} must be an object"
            )
            continue
        if raw_class.get("attribution") != "axiom-attributed-open":
            continue
        units = _count(
            raw_class.get("units"),
            f"classification.class_attribution.{class_name}.units",
            defects,
            entry["suite"],
        )
        census_units = _count(
            class_census.get(class_name),
            f"classification.class_census.{class_name}",
            defects,
            entry["suite"],
        )
        if units != census_units:
            defects.append(
                f"{entry['suite']}: open class {class_name} units do not match "
                f"the class census ({units} != {census_units})"
            )
        axiom_open_classes[class_name] = units
    scope = report.get("scope")
    open_scope = scope.get("open") if isinstance(scope, dict) else None
    scoped_classes = (
        open_scope.get("axiom_attributed_open_classes")
        if isinstance(open_scope, dict)
        else None
    )
    if not isinstance(scoped_classes, dict):
        defects.append(f"{entry['suite']}: scope lacks axiom-attributed-open classes")
    else:
        scoped_units = {
            class_name: raw_class.get("units")
            for class_name, raw_class in scoped_classes.items()
            if isinstance(raw_class, dict)
        }
        if scoped_units != axiom_open_classes:
            defects.append(
                f"{entry['suite']}: scope open classes do not match classification"
            )
    if axiom_open_classes and (
        not isinstance(open_scope, dict) or open_scope.get("status") != "OPEN"
    ):
        defects.append(f"{entry['suite']}: nonempty open classes require OPEN scope")
    axiom_open = sum(axiom_open_classes.values())
    clean = derived_conformant and axiom_open == 0 and not defects
    evidence = [
        {
            "claim": f"suite:{entry['suite']}",
            "mode": "computed",
            "artifact": entry["report"],
            "sha256": sha256_of(report_path),
        }
    ]
    return (
        {
            "suite": entry["suite"],
            "oracle_type": entry["oracle_type"],
            "oracle": entry["oracle"],
            "comparisons": total,
            "matches": matches,
            "mismatches": mismatches,
            "weighted_mismatch_mass": None,
            "unexplained": unexplained,
            "axiom_attributed_open": axiom_open,
            "axiom_attributed_open_classes": axiom_open_classes,
            "binding": "bound",
            "reconciliation": "full",
            "evidence_cases": total,
            "report_defects": defects,
            "clean": clean,
        },
        evidence,
        defects,
    )


def _suite_verdict(entry: dict) -> tuple[dict, list[dict], list[str]]:
    """Compute one suite's conformance leg from its committed report.

    Hardened per the 2026-07-26 cross-family audit: a report only counts as a
    comparison when it identifies itself as this suite, performed a nonzero
    number of comparisons without engine errors, and its counts conserve.
    A zero-work or mislabeled report is a defect, never a clean leg.
    """
    if entry.get("report_contract") == "us_tariff_schedule_v1":
        return _tariff_schedule_suite_verdict(entry)

    defects: list[str] = []
    report_path = REPO_ROOT / entry["report"]
    execution_evidence = validate_suite_evidence(report_path)
    defects.extend(execution_evidence.defects)
    reconciliation_sufficient = (
        execution_evidence.reconciliation == "full"
        if entry["oracle_type"] == "reference"
        else execution_evidence.reconciliation != "none"
    )
    if (
        entry["oracle_type"] == "reference"
        and execution_evidence.valid
        and execution_evidence.binding == "bound"
        and execution_evidence.reconciliation != "full"
    ):
        defects.append(
            f"{entry['suite']}: reference oracle requires full semantic "
            f"reconciliation (got {execution_evidence.reconciliation})"
        )
    evidence_gate_clean = (
        execution_evidence.valid
        and execution_evidence.binding == "bound"
        and reconciliation_sufficient
    )
    try:
        loaded_report = _load(report_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        # The validator already records the precise parse/read defect. Keep
        # computing a defective leg so the certificate surfaces that finding
        # instead of crashing before it can report it.
        report = {}
        report_loaded = False
    else:
        report = loaded_report if isinstance(loaded_report, dict) else {}
        report_loaded = True
    if entry["suite"] == "nz-treasury-incomeexplorer" and report_loaded:
        if report != _rederived_nz_report():
            raise ValueError(
                "NZ IncomeExplorer report does not rederive from its pinned receipt"
            )
    view_name = entry.get("view")
    if view_name:
        raw_views = report.get("views")
        if not isinstance(raw_views, dict):
            defects.append(f"{entry['suite']}: report views must be an object")
            raw_views = {}
        view = raw_views.get(view_name)
        if not isinstance(view, dict):
            defects.append(
                f"{entry['suite']}: report has no subgraph view {view_name!r}"
            )
            view = {}
        raw_summary = view.get("summary")
    else:
        raw_summary = report.get("summary")
    if raw_summary is not None and not isinstance(raw_summary, dict):
        defects.append(f"{entry['suite']}: summary must be an object")
    summary = raw_summary if isinstance(raw_summary, dict) else {}

    # Report identity: the artifact must claim the suite it is cited for.
    reported_suite = report.get("suite")
    accepted = {entry["suite"], *entry.get("aliases", [])}
    if not isinstance(reported_suite, str) or reported_suite not in accepted:
        defects.append(
            f"{entry['suite']}: report {entry['report']} identifies as "
            f"{reported_suite!r}, not this suite"
        )

    comparisons = _count(
        summary.get("comparison_count"), "comparison_count", defects, entry["suite"]
    )
    matches = _count(summary.get("match_count"), "match_count", defects, entry["suite"])
    mismatch_count = _count(
        summary.get("mismatch_count"), "mismatch_count", defects, entry["suite"]
    )
    # Errors appear under several shapes across runners; a check that reads
    # only one key lets an errored run certify (audit finding 2). Count them
    # all, including the top-level list.
    raw_errors_by_engine = summary.get("errors_by_engine")
    if raw_errors_by_engine is None:
        errors_by_engine = {}
    elif isinstance(raw_errors_by_engine, dict):
        errors_by_engine = raw_errors_by_engine
    else:
        errors_by_engine = {}
        defects.append(f"{entry['suite']}: errors_by_engine must be an object")
    raw_errors = report.get("errors")
    if raw_errors is None:
        errors = []
    elif isinstance(raw_errors, list):
        errors = raw_errors
    else:
        errors = []
        defects.append(f"{entry['suite']}: errors must be an array")
    error_count = (
        _count(summary.get("error_count"), "error_count", defects, entry["suite"])
        + _count(
            summary.get("error_case_count"), "error_case_count", defects, entry["suite"]
        )
        + sum(
            _count(v, f"errors_by_engine[{k}]", defects, entry["suite"])
            for k, v in errors_by_engine.items()
        )
        + len(errors)
    )
    if comparisons <= 0:
        defects.append(
            f"{entry['suite']}: zero comparisons — a report that did no work "
            "cannot evidence anything"
        )
    # A positive comparison count must be backed by per-case evidence
    # somewhere: inline cases or committed chunks. Counts alone are an
    # assertion, not evidence (audit finding 2).
    raw_cases = report.get("cases")
    inline_rows = raw_cases if isinstance(raw_cases, list) else []
    inline_cases = sum(1 for c in inline_rows if isinstance(c, dict) and c)
    if comparisons > 0 and not inline_cases and not execution_evidence.chunk_case_count:
        defects.append(
            f"{entry['suite']}: claims {comparisons} comparisons with no "
            "per-case evidence (no inline cases, no committed chunks)"
        )
    if matches + mismatch_count != comparisons:
        defects.append(
            f"{entry['suite']}: counts do not conserve "
            f"({matches} + {mismatch_count} != {comparisons})"
        )
    if error_count:
        defects.append(
            f"{entry['suite']}: {error_count} engine error(s) recorded — "
            "errored cases are not comparisons"
        )

    # Weighted evidence must not contradict the raw counts (a zero raw
    # mismatch count with nonzero weighted mismatch mass is hidden failure).
    raw_weighted = summary.get("weighted")
    if raw_weighted is None:
        weighted = {}
    elif isinstance(raw_weighted, dict):
        weighted = raw_weighted
    else:
        weighted = {}
        defects.append(f"{entry['suite']}: weighted must be an object")
    try:
        weighted_mismatch = float(weighted.get("mismatch_weight") or 0)
    except (TypeError, ValueError):
        weighted_mismatch = 0.0
        defects.append(f"{entry['suite']}: weighted mismatch_weight is not numeric")
    if weighted_mismatch != weighted_mismatch or weighted_mismatch in (
        float("inf"),
        float("-inf"),
    ):
        defects.append(f"{entry['suite']}: weighted mismatch_weight is not finite")
        weighted_mismatch = 0.0
    elif weighted_mismatch < 0:
        defects.append(
            f"{entry['suite']}: weighted mismatch_weight is negative "
            f"({weighted_mismatch})"
        )
        weighted_mismatch = 0.0
    if mismatch_count == 0 and weighted_mismatch > 0:
        defects.append(
            f"{entry['suite']}: raw mismatch count is 0 but weighted mismatch "
            f"mass is {weighted_mismatch} — weighted failures hidden"
        )

    # Disposition accounting. Three explicit modes:
    #   file   — a dispositions file is named; it must exist, be hashed, and
    #            its counts must conserve against the mismatch count.
    #   none   — no machinery; every mismatch is unexplained by definition.
    #   inline — classifications exist with no file (generator-classified);
    #            unvalidated, so the leg is defective until migrated.
    raw_dispositioned = summary.get("dispositioned")
    if raw_dispositioned is None:
        dispositioned = {}
    elif isinstance(raw_dispositioned, dict):
        dispositioned = raw_dispositioned
    else:
        dispositioned = {}
        defects.append(f"{entry['suite']}: dispositioned must be an object")
    raw_counts = dispositioned.get("counts")
    if raw_counts is None:
        counts = {}
    elif isinstance(raw_counts, dict):
        counts = raw_counts
    else:
        counts = {}
        defects.append(f"{entry['suite']}: dispositioned.counts must be an object")
    evidence: list[dict] = []
    if execution_evidence.report_sha256 is not None:
        evidence.append(
            {
                "claim": f"suite:{entry['suite']}",
                "mode": "computed",
                "artifact": entry["report"],
                "sha256": execution_evidence.report_sha256,
            }
        )
    if execution_evidence.suite:
        index_path = (
            report_path.parent / "cases" / execution_evidence.suite / "index.json"
        )
        if index_path.is_file():
            try:
                index_artifact = index_path.relative_to(REPO_ROOT).as_posix()
            except ValueError:
                index_artifact = index_path.as_posix()
            try:
                index_sha256 = sha256_of(index_path)
            except OSError as exc:
                defects.append(
                    f"{entry['suite']}: case evidence index cannot be read "
                    f"({exc.strerror or type(exc).__name__})"
                )
            else:
                evidence.append(
                    {
                        "claim": f"case-evidence-index:{entry['suite']}",
                        "mode": "computed",
                        "artifact": index_artifact,
                        "sha256": index_sha256,
                    }
                )
    raw_disposition_file = dispositioned.get("dispositions_file")
    if raw_disposition_file in (None, ""):
        disposition_file = None
    elif isinstance(raw_disposition_file, str):
        disposition_file = raw_disposition_file
    else:
        disposition_file = None
        defects.append(
            f"{entry['suite']}: dispositions_file must be a repository-relative string"
        )
    classified = sum(
        _count(v, f"counts.{k}", defects, entry["suite"]) for k, v in counts.items()
    )
    if disposition_file:
        if str(disposition_file).startswith("/") or ".." in str(disposition_file):
            defects.append(
                f"{entry['suite']}: dispositions_file {disposition_file!r} is "
                "not a repository-relative path"
            )
            dispositions_path = None
        else:
            dispositions_path = REPO_ROOT / disposition_file
        if dispositions_path is None or not dispositions_path.exists():
            if dispositions_path is not None:
                defects.append(
                    f"{entry['suite']}: dispositions_file {disposition_file!r} "
                    "does not exist in the repository"
                )
            unexplained = mismatch_count
        else:
            evidence.append(
                {
                    "claim": f"dispositions:{entry['suite']}",
                    "mode": "computed",
                    "artifact": disposition_file,
                    "sha256": sha256_of(dispositions_path),
                }
            )
            # The file must declare the suite it is cited for, or one report's
            # mismatches can be "explained" by another suite's file entirely
            # (audit finding 3).
            declared = _dispositions_suite(dispositions_path)
            authorized = declared in accepted
            if declared is None:
                # An unreadable, non-mapping, or suite-less file is not a
                # dispositions artifact — any repository file could otherwise
                # authorize accounting (round-2 audit finding 2).
                defects.append(
                    f"{entry['suite']}: {disposition_file} is not a readable "
                    "dispositions document declaring a suite"
                )
            elif declared not in accepted:
                defects.append(
                    f"{entry['suite']}: {disposition_file} declares suite "
                    f"{declared!r}, which is not this suite"
                )
            if not authorized:
                # A same-suite label alone cannot authorize report-provided
                # disposition counts. Diagnose their internal shape, then
                # fail closed to the raw mismatch total.
                reported_unexplained = _count(
                    dispositioned.get("unexplained_count"),
                    "unexplained_count",
                    defects,
                    entry["suite"],
                )
                counted_unexplained = _count(
                    counts.get("unexplained"),
                    "counts.unexplained",
                    defects,
                    entry["suite"],
                )
                if counted_unexplained != reported_unexplained:
                    defects.append(
                        f"{entry['suite']}: counts.unexplained "
                        f"({counted_unexplained}) disagrees with "
                        f"unexplained_count ({reported_unexplained})"
                    )
                unexplained = mismatch_count
            else:
                unexplained = _count(
                    dispositioned.get("unexplained_count"),
                    "unexplained_count",
                    defects,
                    entry["suite"],
                )
                # counts.unexplained and unexplained_count must agree; a
                # summary that reports both, differently, is not reconciled.
                counted_unexplained = _count(
                    counts.get("unexplained"),
                    "counts.unexplained",
                    defects,
                    entry["suite"],
                )
                if counted_unexplained != unexplained:
                    defects.append(
                        f"{entry['suite']}: counts.unexplained "
                        f"({counted_unexplained}) disagrees with "
                        f"unexplained_count ({unexplained})"
                    )
                    unexplained = max(unexplained, counted_unexplained)
                unknown = set(counts) - KNOWN_DISPOSITION_KINDS
                if unknown:
                    defects.append(
                        f"{entry['suite']}: unknown disposition kind(s) "
                        f"{sorted(unknown)} — only "
                        f"{sorted(KNOWN_DISPOSITION_KINDS)} carry defined meaning"
                    )
                if classified != mismatch_count:
                    defects.append(
                        f"{entry['suite']}: disposition counts ({classified}) "
                        f"do not conserve against mismatches ({mismatch_count})"
                    )
    elif classified:
        inline_unexplained = _count(
            dispositioned.get("unexplained_count"),
            "unexplained_count",
            defects,
            entry["suite"],
        )
        if classified != inline_unexplained:
            defects.append(
                f"{entry['suite']}: inline classifications present with no "
                "dispositions file — unvalidated; migrate before they can explain"
            )
        unexplained = mismatch_count
    else:
        unexplained = mismatch_count

    # Slim-report guard: when the summary claims mismatches the report body
    # does not carry and no per-case chunks exist, the aggregate cannot be
    # audited from committed evidence.
    raw_mismatches = report.get("mismatches")
    if raw_mismatches is None:
        mismatch_rows = []
    elif isinstance(raw_mismatches, list):
        mismatch_rows = raw_mismatches
    else:
        mismatch_rows = []
        defects.append(f"{entry['suite']}: mismatches must be an array")
    stored = len(mismatch_rows)
    if (
        mismatch_count > stored
        and not execution_evidence.chunk_case_count
        and execution_evidence.reconciliation != "full"
    ):
        defects.append(
            f"{entry['suite']}: {mismatch_count} mismatches claimed, "
            f"{stored} stored, no per-case chunks — aggregate unauditable"
        )

    axiom_open = _count(
        counts.get("axiom_encoding_gap"),
        "counts.axiom_encoding_gap",
        defects,
        entry["suite"],
    )
    leg = {
        "suite": entry["suite"],
        "oracle_type": entry["oracle_type"],
        "oracle": entry["oracle"],
        "comparisons": comparisons,
        "matches": matches,
        "mismatches": mismatch_count,
        "weighted_mismatch_mass": weighted_mismatch or None,
        "unexplained": unexplained,
        "axiom_attributed_open": axiom_open,
        "binding": execution_evidence.binding,
        "reconciliation": execution_evidence.reconciliation,
        "evidence_cases": execution_evidence.case_count,
        "report_defects": defects,
        "clean": (
            evidence_gate_clean and not defects and unexplained == 0 and axiom_open == 0
        ),
    }
    if view_name:
        leg["view"] = view_name
    return leg, evidence, defects


def _repo_artifact_path(relative: object, *, label: str) -> Path:
    """Resolve a configured artifact without permitting repository escape."""

    if not isinstance(relative, str) or not relative:
        raise ValueError(f"{label} requires a non-empty repository-relative artifact")
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"{label} artifact must be repository-relative: {relative!r}")
    path = (REPO_ROOT / candidate).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as exc:  # pragma: no cover - defense beyond lexical guard
        raise ValueError(
            f"{label} artifact escapes the repository: {relative!r}"
        ) from exc
    return path


@lru_cache(maxsize=None)
def _producer_module(relative: str) -> ModuleType:
    """Load one in-repo producer so certification can reuse its pure validator."""

    path = _repo_artifact_path(relative, label="computed producer")
    if not path.is_file():
        raise ValueError(f"computed producer is missing: {relative}")
    module_name = f"_axiom_certificate_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - importlib guard
        raise ValueError(f"could not load computed producer: {relative}")
    module = importlib.util.module_from_spec(spec)
    # Dataclass and other runtime annotation helpers resolve their module by
    # name while the file executes, so register it before exec_module.
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _attested_verdict(spec: dict, name: str) -> dict:
    """Emit sha-pinned scaffolding without promoting registry status strings.

    A registry block is a CLAIM. Its `status`/`mode` strings are labels the
    registry author typed, not evidence; only a producer artifact (or NZ's
    rederived closure summary) can make a premise computed. Flipping
    `status: computed` on an attested block therefore changes NOTHING about
    the emitted mode — that flip minted a full certified=yes live during the
    DK launch audit (historical finding-7 class), so it is closed here for
    every program at once.
    """

    block = dict((spec.get("attested") or {}).get(name) or {})
    return {**block, "mode": "attested"}


def _producer_closed_verdict(
    program: str,
    spec: dict,
    evidence: list[dict],
    *,
    verify_producer: bool = False,
) -> dict | None:
    """Computed closure from a committed artifact and its named producer.

    Returns None when the program declares no closed producer (or its artifact
    is absent) so the caller falls through to the other evidence classes. Both
    object-style producer summaries and program-scoped mapping summaries are
    supported; a mapping that declares ``programs`` must contain this program.
    """

    config = (spec.get("computed") or {}).get("closed")
    if not isinstance(config, dict):
        return None
    artifact_ref = config.get("artifact")
    artifact_path = _repo_artifact_path(
        artifact_ref,
        label=f"{program} closed producer",
    )
    if not artifact_path.is_file():
        return None

    try:
        document = (
            yaml.safe_load(artifact_path.read_text())
            if artifact_path.suffix in {".yaml", ".yml"}
            else json.loads(artifact_path.read_text())
        )
    except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(
            f"{artifact_ref} is not readable closure evidence: {exc}"
        ) from exc
    if not isinstance(document, dict):
        raise ValueError(f"{artifact_ref} closure artifact must contain an object")
    producer = _producer_module(str(config.get("producer") or ""))
    if config.get("contract") == "us_tariff_closure_v1":
        if verify_producer:
            raise ValueError(
                f"{artifact_ref}: full producer verification must be run with "
                "the C3 tariff producer checkout"
            )
        computed = document.get("computed")
        decisions = (document.get("committed_decisions") or {}).get("ledger")
        if not isinstance(computed, dict) or not isinstance(decisions, list):
            raise ValueError(f"{artifact_ref} has malformed tariff closure blocks")
        open_rows = [
            row
            for row in decisions
            if isinstance(row, dict)
            and row.get("status") in ("pending", "partially-encoded")
        ]
        expected_burndown = [
            {
                "family": row.get("family"),
                "root": row.get("root"),
                "status": row.get("status"),
                "blocker": row.get("reason"),
            }
            for row in open_rows
        ]
        frontier = computed.get("boundary_frontier")
        derived_closed = not open_rows
        if computed.get("closed") is not derived_closed:
            raise ValueError(f"{artifact_ref} computed.closed is fabricated")
        if computed.get("burndown") != expected_burndown:
            raise ValueError(f"{artifact_ref} burndown is not derived from the ledger")
        if not isinstance(frontier, dict) or frontier.get("complete") is not True:
            raise ValueError(f"{artifact_ref} boundary frontier is incomplete")

        class _TariffSummary:
            closed = derived_closed
            non_encoded_reasons_complete = all(
                isinstance(row, dict)
                and isinstance(row.get("reason"), str)
                and bool(row["reason"])
                for row in decisions
            )

        summary = _TariffSummary()
    else:
        try:
            summary = (
                producer.validate_artifact(document, repo_root=REPO_ROOT)
                if artifact_path.suffix == ".json"
                else producer.validate_artifact(document)
            )
        except ValueError as exc:
            raise ValueError(
                f"{artifact_ref} failed closure validation: {exc}"
            ) from exc
    if (
        verify_producer
        and config.get("contract") != "us_tariff_closure_v1"
        and config.get("external_verification") != "hermetic_program_scoped"
    ):
        try:
            verification = producer.verify_artifact(artifact_path=artifact_path)
        except ValueError as exc:
            raise ValueError(
                f"{artifact_ref} closure verification crashed: {exc}"
            ) from exc
        if not getattr(verification, "valid", False):
            errors = getattr(verification, "errors", ())
            detail = (
                "; ".join(str(error) for error in errors) or "unknown producer error"
            )
            raise ValueError(
                f"{artifact_ref} failed full closure verification: {detail}"
            )
    scoped: dict | None = None
    if isinstance(summary, dict):
        if "programs" in summary:
            programs = summary["programs"]
            if not isinstance(programs, dict) or not isinstance(
                programs.get(program), dict
            ):
                raise ValueError(f"{artifact_ref} has no closure scope for {program}")
            scoped = programs[program]
        else:
            scoped = summary
        value = scoped.get("closed")
    else:
        value = getattr(summary, "closed", None)
    if not isinstance(value, bool):
        raise ValueError(f"{artifact_ref} validator returned no closed boolean")
    # Central completeness requirement (oracles#491): a closure claim must
    # disposition the act's subordinate instruments (regulations, guidance,
    # rate publications), not just the act's own provisions. A closure
    # artifact whose computed block carries no complete instrument frontier
    # cannot compute closed=true, whatever its producer says — in the US,
    # certifying statute-only closure would be very wrong.
    _computed_block = document.get("computed")
    _instrument_frontier = (
        _computed_block.get("instrument_frontier")
        if isinstance(_computed_block, dict)
        else None
    )
    _instrument_frontier_summary = (
        {
            key: _instrument_frontier.get(key)
            for key in (
                "instrument_count",
                "supplemental_count",
                "counts",
                "pending",
                "complete",
            )
        }
        if isinstance(_instrument_frontier, dict)
        else {
            "complete": False,
            "missing": True,
            "requirement": (
                "closure must disposition the act's subordinate instruments "
                "(oracles#491); this artifact declares none"
            ),
        }
    )
    if _instrument_frontier_summary.get("complete") is not True:
        value = False
    _dependency_block = (
        _computed_block.get("dependency_closure")
        if isinstance(_computed_block, dict)
        else None
    )
    # A dependency-closure block only satisfies the gate when it is
    # COMPLETE and internally consistent: all four fields present and
    # well-typed, closed=true, and the enumerations actually empty. A bare
    # {"closed": true} — or any block whose count and lists disagree — is
    # treated as malformed and fails closed (launch-audit delta finding).
    _dependency_well_formed = (
        isinstance(_dependency_block, dict)
        and isinstance(_dependency_block.get("open_dependency_count"), int)
        and isinstance(_dependency_block.get("law_derived_inputs"), list)
        and isinstance(
            _dependency_block.get("instruments_bearing_on_computed"), list
        )
        and isinstance(_dependency_block.get("closed"), bool)
        and _dependency_block["open_dependency_count"]
        == len(_dependency_block["law_derived_inputs"])
        + len(_dependency_block["instruments_bearing_on_computed"])
        and _dependency_block["closed"]
        == (_dependency_block["open_dependency_count"] == 0)
    )
    if _dependency_well_formed:
        _dependency_summary = {
            key: _dependency_block[key]
            for key in (
                "open_dependency_count",
                "law_derived_inputs",
                "instruments_bearing_on_computed",
                "closed",
            )
        }
    elif isinstance(_dependency_block, dict):
        _dependency_summary = {
            "closed": False,
            "malformed": True,
            "requirement": (
                "the dependency-closure block must carry a well-typed "
                "open_dependency_count, law_derived_inputs, and "
                "instruments_bearing_on_computed that agree with its closed "
                "flag (CERTIFIED.md v3); this artifact's block is incomplete "
                "or inconsistent"
            ),
        }
    else:
        _dependency_summary = {
            "closed": False,
            "missing": True,
            "requirement": (
                "closure must type every leaf and encode every law-derived "
                "dependency (CERTIFIED.md v3); this artifact declares no "
                "dependency-closure block"
            ),
        }
    if not _dependency_well_formed or _dependency_summary.get("closed") is not True:
        value = False
    evidence.append(
        {
            "claim": f"closed:{program}",
            "mode": "computed",
            "artifact": str(artifact_ref),
            "sha256": sha256_of(artifact_path),
            "verification": "producer_artifact_validation",
        }
    )

    if scoped is not None and isinstance(summary.get("programs"), dict):
        return {
            "mode": "computed",
            "status": "computed_pass" if value else "computed_open",
            "value": value,
            "instrument_frontier": _instrument_frontier_summary,
            "dependency_closure": _dependency_summary,
            "artifact": str(artifact_ref),
            "corpus_release": document.get("corpus_release"),
            "rulespec_commit": document.get("rulespec_commit"),
            "pending_citations": len(scoped.get("pending_citations") or []),
            "pending_money_atoms": scoped.get("pending_money_atoms"),
            "root_node_count": scoped.get("root_node_count"),
            "root_nodes": scoped.get("root_nodes"),
            "subgraph_node_count": scoped.get("subgraph_node_count"),
            "citation_root_count": scoped.get("citation_root_count"),
            "by_status": scoped.get("by_status"),
            "denominator_ratchet": scoped.get("denominator_ratchet"),
        }

    computed = document.get("computed")
    if not isinstance(computed, dict):
        raise ValueError(f"{artifact_ref} has no computed closure block")
    facts = document.get("generated_facts") or {}
    ledger_rulespec = facts.get("rulespec") if isinstance(facts, dict) else None
    return {
        "mode": "computed",
        "value": value,
        "status": "computed_closed" if value else "computed_open",
        "artifact": str(artifact_ref),
        "rulespec_commit": (
            ledger_rulespec.get("commit") if isinstance(ledger_rulespec, dict) else None
        ),
        "provision_counts": computed.get("provision_counts"),
        "boundary_frontier": computed.get("boundary_frontier"),
        "instrument_frontier": _instrument_frontier_summary,
        "dependency_closure": _dependency_summary,
        **(
            {"burndown": computed.get("burndown")}
            if config.get("include_burndown")
            else {}
        ),
        "non_encoded_reasons_complete": summary.non_encoded_reasons_complete,
    }


def _producer_executable_verdict(
    program: str,
    spec: dict,
    evidence: list[dict],
    *,
    verify_producer: bool = False,
) -> dict | None:
    """Computed execution from a committed receipt and its named producer.

    ``verify_producer`` retains the DK producer's external compile/replay gate.
    Producers such as NZ that expose a hermetic program-scoped validator but
    no generic ``build_reproduction`` hook remain validated by that committed
    contract; their pinned-engine replay runs in their dedicated CI gate.
    """

    config = (spec.get("computed") or {}).get("executable")
    if not isinstance(config, dict):
        return None
    artifact_ref = config.get("artifact")
    artifact_path = _repo_artifact_path(
        artifact_ref,
        label=f"{program} executable producer",
    )
    if not artifact_path.is_file():
        return None

    try:
        document = json.loads(artifact_path.read_text())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"{artifact_ref} is not readable executable JSON: {exc}"
        ) from exc
    producer = _producer_module(str(config.get("producer") or ""))
    try:
        summary = producer.validate_artifact(document, repo_root=REPO_ROOT)
    except ValueError as exc:
        raise ValueError(f"{artifact_ref} failed executable validation: {exc}") from exc
    if (
        verify_producer
        and config.get("external_verification") != "dedicated_source_build_ci"
    ):
        try:
            reproduced = producer.build_reproduction(
                repo_root=REPO_ROOT,
                rulespec_ref=document["rulespec"]["sha"],
            )
            producer.validate_artifact(reproduced, repo_root=REPO_ROOT)
            rendered = producer._render(reproduced)
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError(
                f"{artifact_ref} failed full executable verification: {exc}"
            ) from exc
        if artifact_path.read_text() != rendered:
            raise ValueError(
                f"{artifact_ref} failed full executable verification: "
                "compiled/replayed artifact drifted"
            )
    if not isinstance(summary, dict):
        raise ValueError(f"{artifact_ref} validator returned no executable summary")
    if "programs" in summary:
        programs = summary["programs"]
        if not isinstance(programs, dict) or not isinstance(
            programs.get(program), dict
        ):
            raise ValueError(f"{artifact_ref} has no executable scope for {program}")
        scoped = programs[program]
    else:
        programs = None
        scoped = summary
    value = scoped.get("executable")
    if not isinstance(value, bool):
        raise ValueError(f"{artifact_ref} validator returned no executable boolean")
    evidence.append(
        {
            "claim": f"executable:{program}",
            "mode": "computed",
            "artifact": str(artifact_ref),
            "sha256": sha256_of(artifact_path),
            "verification": "producer_artifact_validation",
        }
    )
    if programs is not None:
        return {
            "mode": "computed",
            "status": "computed_pass" if value else "computed_fail",
            "value": value,
            "artifact": str(artifact_ref),
            "rulespec_sha": (document.get("rulespec") or {}).get("sha"),
            "engine": document.get("engine"),
            "compiled_artifact": document.get("compiled_artifact"),
            "request_set": document.get("request_set"),
            "execution_trace": document.get("execution_trace"),
            "treasury_snapshot": document.get("treasury_snapshot"),
            "reducer": document.get("reducer"),
            "independent_expected": document.get("independent_expected"),
            "full_responses": document.get("full_responses"),
            "transcript": document.get("transcript"),
            "summary": scoped,
        }
    return {
        "mode": "computed",
        "value": value,
        "status": "computed_pass" if value else "computed_fail",
        "artifact": str(artifact_ref),
        "case_count": summary.get("case_count"),
        "matched_case_count": summary.get("matched_case_count"),
        "engine_binary_sha256": (document.get("engine") or {}).get("binary_sha256"),
        "configured_engine_sha256": (document.get("engine") or {}).get(
            "configured_sha256"
        ),
        "rulespec_sha": (document.get("rulespec") or {}).get("sha"),
        "compiled_artifacts": [
            {
                "program": row.get("program"),
                "sha256": row.get("sha256"),
            }
            for row in document.get("compiled_artifacts") or []
            if isinstance(row, dict)
        ],
    }


def _closed_verdict(
    program: str,
    spec: dict,
    evidence: list[dict],
    *,
    verify_producer: bool = False,
) -> dict:
    """One closure verdict for every evidence class, in strength order:
    NZ attested receipt (attested), DK producer ledger (computed), NZ
    rederived closure summary (computed), else the registry block (attested,
    whatever its strings say)."""

    attested_path_string = spec.get("attested_closed_receipt")
    if attested_path_string:
        path = REPO_ROOT / attested_path_string
        closure = _load(path)
        scoped = (closure.get("programs") or {}).get(program)
        if not isinstance(scoped, dict):
            raise ValueError(f"NZ closure receipt has no program scope for {program}")
        evidence.append(
            {
                "claim": f"closure receipt:{program}",
                "mode": "attested",
                "artifact": attested_path_string,
                "sha256": sha256_of(path),
            }
        )
        return {
            "mode": "attested",
            "status": "attested_receipt",
            "value": scoped.get("closed") is True,
            "downgrade_reason": (
                "Adversarial review S4: no independently emitted requested-output "
                "trace, root-set bijection, and monotone root/citation denominator "
                "ratchet are all present; exact-path closure remains evidence only."
            ),
            "corpus_release": closure.get("corpus_release"),
            "rulespec_commit": closure.get("rulespec_commit"),
            "pending_citations": len(scoped.get("pending_citations") or []),
            "pending_money_atoms": scoped.get("pending_money_atoms"),
            "root_node_count": scoped.get("root_node_count"),
            "root_nodes": scoped.get("root_nodes"),
            "subgraph_node_count": scoped.get("subgraph_node_count"),
            "citation_root_count": scoped.get("citation_root_count"),
            "by_status": scoped.get("by_status"),
        }
    produced = _producer_closed_verdict(
        program, spec, evidence, verify_producer=verify_producer
    )
    if produced is not None:
        return produced
    path_string = spec.get("computed_closed")
    if not path_string:
        return _attested_verdict(spec, "closed")
    path = REPO_ROOT / path_string
    closure = _load(path)
    if path_string == "closure/nz/summary.json":
        module_path = REPO_ROOT / "scripts" / "nz_closure.py"
        module_spec = importlib.util.spec_from_file_location(
            "_certificate_nz_closure", module_path
        )
        if module_spec is None or module_spec.loader is None:
            raise ValueError("cannot load the NZ closure verifier")
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        expected = module.build(module.load_source())
        if closure != expected:
            raise ValueError(
                "closure/nz/summary.json does not rederive from its versioned input"
            )
        scoped = (closure.get("programs") or {}).get(program)
        if not isinstance(scoped, dict):
            raise ValueError(f"NZ closure has no program scope for {program}")
    else:
        scoped = closure
    value = scoped.get("closed") is True
    evidence.append(
        {
            "claim": f"closure census:{program}",
            "mode": "computed",
            "artifact": path_string,
            "sha256": sha256_of(path),
        }
    )
    return {
        "mode": "computed",
        "status": "computed_pass" if value else "computed_open",
        "value": value,
        "corpus_release": closure.get("corpus_release"),
        "rulespec_commit": closure.get("rulespec_commit"),
        "pending_citations": len(scoped.get("pending_citations") or []),
        "pending_money_atoms": scoped.get("pending_money_atoms"),
        "root_node_count": scoped.get("root_node_count"),
        "root_nodes": scoped.get("root_nodes"),
        "subgraph_node_count": scoped.get("subgraph_node_count"),
        "citation_root_count": scoped.get("citation_root_count"),
        "by_status": scoped.get("by_status"),
    }


def _single_person_evidence(program: str, spec: dict, evidence: list[dict]) -> None:
    path_string = spec.get("single_person_attestation")
    if not path_string:
        return
    path = REPO_ROOT / path_string
    committed = _load(path)
    module_path = REPO_ROOT / "scripts" / "nz_incomeexplorer.py"
    module_spec = importlib.util.spec_from_file_location(
        "_certificate_nz_single_person", module_path
    )
    if module_spec is None or module_spec.loader is None:
        raise ValueError("cannot load the NZ single-person verifier")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    expected = module.build_single_person_attestations()
    if committed != expected:
        raise ValueError("NZ single-person attestation does not rederive")
    row = (committed.get("programs") or {}).get(program)
    if not isinstance(row, dict) or row.get("status") != "pass":
        raise ValueError(f"NZ single-person attestation does not pass for {program}")
    evidence.append(
        {
            "claim": f"single-person invariant:{program}",
            "mode": "computed",
            "artifact": path_string,
            "sha256": sha256_of(path),
            "limitation": (
                "Supporting two-endpoint evidence only; it does not prove "
                "person-locality or clear the S1 blocker."
            ),
        }
    )


def _executable_verdict(
    program: str,
    spec: dict,
    legs: list[dict] | None = None,
    evidence: list[dict] | None = None,
    *,
    verify_producer: bool = False,
) -> dict:
    """One execution verdict for every evidence class.

    ``legs`` is retained for the legacy executable dispatcher. The three-arg
    form added by the shared producer adapter passes evidence in that position,
    so normalize both call shapes before dispatching.
    """

    if evidence is None:
        evidence = legs if legs is not None else []
        legs = []

    attested_path_string = spec.get("attested_executable_receipt")
    if attested_path_string:
        path = REPO_ROOT / attested_path_string
        report = _load(path)
        receipt = report.get("compiled_program") or {}
        evidence.append(
            {
                "claim": "compiled-program execution receipt (commit-pinned harness)",
                "mode": "attested",
                "artifact": attested_path_string,
                "sha256": sha256_of(path),
            }
        )
        return {
            "mode": "attested",
            "status": "attested_receipt",
            "value": True,
            "receipt": receipt,
            "limitation": (
                "The generator and comparison harness lineage is commit-pinned, but "
                "the compiled artifact bytes and an executable transcript are not "
                "committed; metadata syntax and a digest string are not a computed "
                "execution check (adversarial review S3)."
            ),
        }
    produced = _producer_executable_verdict(
        program, spec, evidence, verify_producer=verify_producer
    )
    if produced is not None:
        return produced
    if not spec.get("computed_executable"):
        return _attested_verdict(spec, "executable")
    raise ValueError(
        "computed executable verdict requested without a verifier that loads and "
        "runs committed artifact bytes"
    )


def _attested_exercise_verdict(spec: dict, evidence: list[dict]) -> dict:
    path_string = spec["attested_exercise_receipt"]
    path = REPO_ROOT / path_string
    source = _load(path)
    catalog = source.get("exercise_input_catalog")
    if not isinstance(catalog, dict) or not catalog:
        raise ValueError("NZ exercise attestation has no exercise_input_catalog")
    state_counts = Counter(
        row.get("state") for row in catalog.values() if isinstance(row, dict)
    )
    evidence.append(
        {
            "claim": "exercise input catalog (commit-pinned external receipt)",
            "mode": "attested",
            "artifact": path_string,
            "sha256": sha256_of(path),
        }
    )
    return {
        "mode": "attested",
        "status": "attested_receipt",
        "value": True,
        "receipt": {
            "artifact": path_string,
            "sha256": sha256_of(path),
            "input_catalog_count": len(catalog),
            "varied_fields": state_counts.get("varied", 0),
            "constant_fields": state_counts.get("constant", 0),
            "not_supplied_fields": state_counts.get("not_supplied", 0),
        },
        "limitation": (
            "The harness lineage is commit-pinned, but the catalog is suite-wide "
            "and not recomputed from committed, per-evaluation, view-scoped "
            "request/output traces (adversarial review S2)."
        ),
    }


def _attested_exercise_catalog(
    spec: dict,
    evidence: list[dict],
) -> dict | None:
    """The NZ completeness boundary: computed when the denominator producer
    cross-derives it from committed artifacts, attested otherwise."""

    path_string = spec.get("attested_exercise_catalog_receipt")
    if not path_string:
        return None
    config = (spec.get("computed") or {}).get("exercise_denominator")
    if isinstance(config, dict):
        producer = _producer_module(str(config.get("producer") or ""))
        try:
            summary = producer.validate(repo_root=REPO_ROOT)
        except ValueError as exc:
            raise ValueError(f"exercise denominator failed to compute: {exc}") from exc
        path = REPO_ROOT / path_string
        evidence.append(
            {
                "claim": "compiled input universe and capture cardinality",
                "mode": "computed",
                "artifact": path_string,
                "sha256": sha256_of(path),
                "verification": "producer_cross_derivation",
            }
        )
        return {
            "mode": "computed",
            "artifact": path_string,
            "sha256": sha256_of(path),
            "input_count": summary["input_count"],
            "supplied_input_count": summary["supplied_input_count"],
            "not_supplied_count": summary["not_supplied_count"],
            "expected_evaluation_count": summary["evaluation_count"],
            "universe_source": summary["universe_source"],
        }
    path = REPO_ROOT / path_string
    source = _load(path)
    catalog = source.get("exercise_input_catalog")
    compiled = source.get("compiled_program")
    if not isinstance(catalog, dict) or not isinstance(compiled, dict):
        raise ValueError("NZ exercise completeness receipt is malformed")
    state_counts = Counter(
        row.get("state") for row in catalog.values() if isinstance(row, dict)
    )
    if len(catalog) != compiled.get("input_slots"):
        raise ValueError("NZ exercise catalog does not match its attested denominator")
    evidence.append(
        {
            "claim": "compiled input universe and capture cardinality",
            "mode": "attested",
            "artifact": path_string,
            "sha256": sha256_of(path),
        }
    )
    return {
        "mode": "attested",
        "artifact": path_string,
        "sha256": sha256_of(path),
        "input_count": len(catalog),
        "supplied_input_count": (
            state_counts.get("varied", 0) + state_counts.get("constant", 0)
        ),
        "not_supplied_count": state_counts.get("not_supplied", 0),
        "expected_evaluation_count": compiled.get("engine_evaluations"),
        "limitation": (
            "The compiled artifact bytes, compiler-produced input enumeration, "
            "and in-repo capture execution are not committed."
        ),
    }


def _nz_external_attestation_evidence(spec: dict, evidence: list[dict]) -> None:
    if not any(
        entry.get("suite") == "nz-treasury-incomeexplorer"
        for entry in spec.get("suites", [])
    ):
        return
    snapshot = (
        REPO_ROOT
        / "comparisons/nz-treasury-incomeexplorer/treasury-emtr-snapshot-expanded.json"
    )
    evidence.append(
        {
            "claim": "Treasury oracle snapshot (commit-pinned external receipt)",
            "mode": "attested",
            "artifact": str(snapshot.relative_to(REPO_ROOT)),
            "sha256": sha256_of(snapshot),
        }
    )


def _exercise_block(
    suites: list[dict], census: dict, defects: list[str]
) -> tuple[dict, bool]:
    rows = {}
    complete = True
    for entry in suites:
        row = (census.get("suites") or {}).get(entry["suite"])
        if row is None:
            rows[entry["suite"]] = {"status": "no census row"}
            complete = False
            continue

        expected_report = entry["report"]
        expected_path = REPO_ROOT / expected_report
        expected_sha256: str | None
        if expected_path.is_file():
            try:
                expected_sha256 = sha256_of(expected_path)
            except OSError as exc:
                expected_sha256 = None
                complete = False
                defects.append(
                    f"{entry['suite']}: registry report {expected_report!r} "
                    f"cannot be read ({exc.strerror or type(exc).__name__})"
                )
        else:
            expected_sha256 = None
            complete = False
            defects.append(
                f"{entry['suite']}: registry report {expected_report!r} "
                "does not exist and cannot be matched to the census"
            )
        report_identity_matches = (
            row.get("report") == expected_report
            and expected_sha256 is not None
            and row.get("report_sha256") == expected_sha256
        )
        if row.get("report") != expected_report:
            complete = False
            defects.append(
                f"{entry['suite']}: census report path {row.get('report')!r} "
                f"diverges from registry report {expected_report!r}"
            )
        if expected_sha256 is not None and row.get("report_sha256") != expected_sha256:
            complete = False
            defects.append(
                f"{entry['suite']}: census report_sha256 "
                f"{row.get('report_sha256')!r} diverges from registry report "
                f"bytes {expected_sha256}"
            )

        has_evidence = bool(row.get("evidence_fields"))
        if not has_evidence:
            complete = False
        # A suite claimed by more than one committed report is ambiguous
        # evidence: the census records the contest, and the certificate must
        # treat it as a defect rather than inherit whichever sorted last
        # (round-2 audit finding 4).
        contested = row.get("contested_reports") or []
        if contested:
            complete = False
            defects.append(
                f"{entry['suite']}: {len(contested)} committed reports claim "
                f"this suite ({', '.join(contested)}) — evidence is ambiguous "
                "until one is canonical"
            )
        view_scoped_traces = (
            row.get("evidence_source") == "view-scoped-evaluation-traces"
        )
        trace_complete = (
            row.get("trace_binding") == "bound"
            and row.get("root_reconciliation") == "exact"
            and bool(row.get("root_set_receipts"))
        )
        rows[entry["suite"]] = {
            **(
                {"evaluations": row.get("evaluations_scanned")}
                if view_scoped_traces
                else {"cases": row.get("cases_scanned")}
            ),
            "report": row.get("report"),
            "report_sha256": row.get("report_sha256"),
            "registry_report": expected_report,
            "registry_report_sha256": expected_sha256,
            "report_identity_matches_registry": report_identity_matches,
            "contested_reports": contested,
            "varied_fields": row.get("varied_fields"),
            "constant_fields": row.get("constant_fields"),
            **(
                {}
                if view_scoped_traces
                else {
                    "bridged_through": sorted(
                        (row.get("bridged_through") or {}).keys()
                    ),
                    "bridge_audited": bool(row.get("bridge_audited")),
                }
            ),
            **(
                {"per_evaluation_traces_committed": has_evidence}
                if view_scoped_traces
                else {"per_case_evidence_committed": has_evidence}
            ),
            "binding": (
                row.get("trace_binding") if view_scoped_traces else row.get("binding")
            ),
            "reconciliation": (
                row.get("root_reconciliation")
                if view_scoped_traces
                else row.get("reconciliation")
            ),
            **(
                {
                    "view": row.get("view"),
                    "trace_artifact": row.get("trace_artifact"),
                    "trace_sha256": row.get("trace_sha256"),
                    "trace_binding": row.get("trace_binding"),
                    "root_reconciliation": row.get("root_reconciliation"),
                    "requested_output_roots": row.get("requested_output_roots"),
                    "requested_output_root_sets": row.get("requested_output_root_sets"),
                    "root_set_receipts": row.get("root_set_receipts"),
                    "capture_lineage_mode": row.get("capture_lineage_mode"),
                }
                if view_scoped_traces
                else {}
            ),
        }
        if view_scoped_traces and not trace_complete:
            complete = False
            defects.append(
                f"{entry['suite']}: view-scoped request/output traces are not "
                "bound with exact requested-root reconciliation"
            )
        elif not view_scoped_traces and not row.get("bridge_audited"):
            complete = False
    return rows, complete


def _exercise_census_for(spec: dict) -> tuple[dict, list[dict]]:
    """Return the exercise rows and evidence relevant to one certificate.

    Conventional suites use the committed global census. Unified records
    carry a complete experiment receipt of their own and are recomputed from
    that receipt here. This keeps adding an unrelated unified record from
    invalidating every existing certificate merely by changing the global
    census artifact's hash.
    """

    census = _load(CENSUS_PATH)
    evidence = [
        {
            "claim": "exercise census",
            "mode": "computed",
            "artifact": str(CENSUS_PATH.relative_to(REPO_ROOT)),
            "sha256": sha256_of(CENSUS_PATH),
        }
    ]
    unified_entries = [
        entry
        for entry in spec["suites"]
        if entry["suite"] == "nz-treasury-incomeexplorer"
    ]
    if not unified_entries:
        return census, evidence

    module_path = REPO_ROOT / "scripts" / "exercise_census.py"
    module_spec = importlib.util.spec_from_file_location(
        "_certificate_exercise_census", module_path
    )
    if module_spec is None or module_spec.loader is None:
        raise ValueError("cannot load the exercise-census verifier")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)

    suites = dict(census.get("suites") or {})
    unified_evidence: list[dict] = []
    for entry in unified_entries:
        report_path = REPO_ROOT / entry["report"]
        report = _load(report_path)
        row = module._census_suite(
            entry["suite"], report, report_path, view=entry.get("view")
        )
        suites[entry["suite"]] = row
        unified_evidence.append(
            {
                "claim": f"view-scoped evaluation traces:{entry.get('view')}",
                "mode": "computed",
                "artifact": row["trace_artifact"],
                "sha256": row["trace_sha256"],
            }
        )
    census = {**census, "suites": suites}

    # A certificate containing only unified suites derives no verdict from the
    # global census, so do not cite it. The suite report evidence added by
    # _suite_verdict sha-binds the exact experiment receipt consumed above.
    if len(unified_entries) == len(spec["suites"]):
        evidence = unified_evidence
    else:
        evidence.extend(unified_evidence)
    return census, evidence


def build_certificate(
    program: str,
    spec: dict,
    *,
    verify_producers: bool = False,
) -> dict:
    if spec.get("attested_exercise_receipt"):
        census, evidence = {}, []
    else:
        census, evidence = _exercise_census_for(spec)
    legs = []
    all_defects: list[str] = []
    for entry in spec["suites"]:
        leg, evs, defects = _suite_verdict(entry)
        legs.append(leg)
        evidence.extend(evs)
        all_defects.extend(defects)
    _single_person_evidence(program, spec, evidence)
    _nz_external_attestation_evidence(spec, evidence)

    reference_legs = [leg for leg in legs if leg["oracle_type"] == "reference"]
    reality_legs = [leg for leg in legs if leg["oracle_type"] == "reality"]
    conformant = bool(reference_legs) and all(leg["clean"] for leg in reference_legs)
    reality_leads = sum(leg["mismatches"] for leg in reality_legs)

    if spec.get("attested_exercise_receipt"):
        exercised_block = _attested_exercise_verdict(spec, evidence)
        exercise_complete = False
    else:
        exercise_rows, exercise_complete = _exercise_block(
            spec["suites"], census, all_defects
        )
        catalog_completeness = _attested_exercise_catalog(spec, evidence)
        exercised_block = {
            "value": exercise_complete,
            "mode": "computed",
            "suites": exercise_rows,
            **(
                {
                    "scope": (
                        "supplied-input variation and exact requested-output "
                        "root sets observed in the committed traces"
                    ),
                    "catalog_completeness": catalog_completeness,
                    "capture_lineage": (
                        {
                            "mode": "computed",
                            "basis": (
                                "committed evaluation traces bind to the "
                                "byte-verified compiled artifact and pinned "
                                "engine, and their cardinality cross-derives "
                                "from the committed record; traces are a lower "
                                "bound on exercise — an unrecorded call could "
                                "only add variation, never subtract it — so "
                                "with the denominator derived from the "
                                "committed artifact, capture completeness is "
                                "not load-bearing"
                            ),
                        }
                        if catalog_completeness.get("mode") == "computed"
                        else {
                            "mode": "attested",
                            "limitation": (
                                "The external capture instrumentation and "
                                "executable capture transcript are not "
                                "committed in this repository."
                            ),
                        }
                    ),
                }
                if catalog_completeness is not None
                else {}
            ),
        }

    blockers = [*all_defects, *(spec.get("blockers") or [])]
    for leg in reference_legs:
        if leg["unexplained"] or leg["axiom_attributed_open"]:
            open_classes = leg.get("axiom_attributed_open_classes") or {}
            open_detail = ", ".join(
                f"{name}={units}" for name, units in sorted(open_classes.items())
            )
            blockers.append(
                f"{leg['suite']}: {leg['unexplained']} unexplained mismatch(es), "
                f"{leg['axiom_attributed_open']} axiom-attributed-open unit(s)"
                + (f" ({open_detail})" if open_detail else "")
                + " — disposition or fix before this leg counts"
            )
    if not exercise_complete:
        if spec.get("attested_exercise_receipt"):
            blockers.append(
                "exercise: the commit-pinned, sha-bound input catalog is attested, "
                "not computed from committed per-evaluation, view-scoped "
                "request/output traces"
            )
        else:
            blockers.append(
                "exercise: census incomplete (missing per-case evidence or "
                "unaudited bridge) for at least one suite"
            )

    closed_block = _closed_verdict(
        program, spec, evidence, verify_producer=verify_producers
    )
    executable_block = _executable_verdict(
        program, spec, legs, evidence, verify_producer=verify_producers
    )
    scope = None
    scope_suite = spec.get("scope_from_suite")
    if scope_suite is not None:
        scope_entries = [
            entry for entry in spec["suites"] if entry["suite"] == scope_suite
        ]
        if len(scope_entries) != 1:
            raise ValueError(f"{program}: scope_from_suite must name exactly one suite")
        scope_report = _load(
            _repo_artifact_path(scope_entries[0]["report"], label=f"{program} scope")
        )
        raw_scope = (
            scope_report.get("scope") if isinstance(scope_report, dict) else None
        )
        required_scope = {
            "trajectory_quotient_label",
            "limitation",
            "components_only_statement",
            "open",
        }
        if not isinstance(raw_scope, dict) or not required_scope <= raw_scope.keys():
            raise ValueError(f"{program}: suite report lacks the required scope block")
        open_scope = raw_scope.get("open")
        if not isinstance(open_scope, dict) or not isinstance(
            open_scope.get("axiom_attributed_open_classes"), dict
        ):
            raise ValueError(f"{program}: scope lacks axiom-attributed-open classes")
        scope = raw_scope
        scope["certificate_premise"] = (
            "S1 zero unexplained means every mismatch is classified; it does not "
            "close axiom-attributed-open classes. Those open units independently "
            "make the conformant premise false."
        )
    # ONE rulespec commit across producer-computed premises. The closure
    # ledger and the executable receipt each verify their OWN recorded pin
    # (and the receipt binds the reports' provenance), but a coherently
    # regenerated ledger at a different commit would pass its own check while
    # the receipt sat at another — "the encoded law is closed at X" and "the
    # encoded law executes at Y" is not a certificate about one artifact.
    # Both blocks are producer-computed for DK and NZ; a mismatch is a blocker
    # on the certificate (never a crash), so certified cannot be yes on it.
    closed_commit = closed_block.get("rulespec_commit")
    executable_commit = executable_block.get("rulespec_sha")
    if (
        closed_block.get("mode") == "computed"
        and executable_block.get("mode") == "computed"
    ):
        # Fail closed: two computed premises with no comparable provenance is
        # a blocker, not a silent skip — a 40-DIGIT integer commit slipped
        # through a str()-coercing validator and would have skipped this
        # comparison (delta-audit #7); a !!str-tagged digit string then passed
        # both validators' hex regex and, coordinated on both sides, satisfied
        # plain equality (delta-audit #8). Equality only counts between values
        # that are each a real git object id (GIT_SHA: lowercase hex with at
        # least one a-f).
        if not (
            isinstance(closed_commit, str)
            and isinstance(executable_commit, str)
            and GIT_SHA.fullmatch(closed_commit)
            and GIT_SHA.fullmatch(executable_commit)
        ):
            blockers.append(
                "producers' rulespec provenance is not comparable: closure ledger "
                f"commit={closed_commit!r}, executable receipt sha="
                f"{executable_commit!r}; both must be string SHAs"
            )
        elif closed_commit != executable_commit:
            blockers.append(
                "producers disagree on the rulespec commit: closure ledger "
                f"{closed_commit[:12]} vs executable receipt {executable_commit[:12]}; "
                "regenerate both at one commit"
            )

    # The single public predicate (adopted from the 2026-07-26 design review):
    # "certified" is reserved for the conjunction of all four verdicts holding
    # in computed mode with no open defects. A certificate resting on attested
    # premises is scaffolding, and saying so is the point.
    # A status string alone must never authorize certification: flipping two
    # registry strings to "computed" would otherwise certify while the
    # underlying values are false and the emitted mode is still attested
    # (audit finding 7). Require, per premise, that it is genuinely computed
    # AND true. If no producer computes closed/executable, `certified` is
    # explicitly UNAVAILABLE rather than silently false — an unreachable
    # claim reported as a verdict is its own defect.
    def _premise(block: dict) -> tuple[bool, bool]:
        """Return ``(is_computed, is_true)`` for an emitted premise.

        The mode the certificate EMITS is what a reader sees, so that is what
        must be computed — checking the registry's `status` string instead let
        a premise flip to computed while the emitted mode stayed attested
        (round-2 audit finding 3).
        """
        return block.get("mode") == "computed", block.get("value") is True

    closed_computed, closed_true = _premise(closed_block)
    exec_computed, exec_true = _premise(executable_block)
    premises_computed = closed_computed and exec_computed
    if spec.get("certified_false_when_blocked") and blockers:
        certified_state = "no"
    elif not premises_computed:
        certified_state = "unavailable"
    elif (
        conformant and exercise_complete and not blockers and closed_true and exec_true
    ):
        certified_state = "yes"
    else:
        certified_state = "no"
    certified = certified_state == "yes"
    certified_rule = (
        "computed(conformant AND exercised AND closed AND executable) with zero "
        "open defects. A premise counts only when its mode is computed AND its "
        "value is true; attested premises never satisfy it. The canonical definition, including the closure requirements (spine, instruments, dependency closure with leaf discipline), is CERTIFIED.md at the repository root."
    )
    if not premises_computed:
        certified_rule += (
            " state=unavailable means no producer computes closed/executable yet, "
            "so certification is not merely withheld but not yet offerable."
        )
    return {
        "schema": SCHEMA,
        "program": program,
        "period": spec["period"],
        "certified": {
            "value": certified,
            "state": certified_state,
            "rule": certified_rule,
        },
        "verdicts": {
            "conformant": {
                "value": conformant,
                "mode": "computed",
                "reference_legs": [
                    leg for leg in legs if leg["oracle_type"] == "reference"
                ],
                "reality_legs": [
                    {
                        **leg,
                        "note": "reality-oracle disagreements are leads, not defects",
                    }
                    for leg in reality_legs
                ],
                "reality_leads": reality_leads,
            },
            "exercised": exercised_block,
            "closed": {
                **closed_block,
            },
            "executable": {
                **executable_block,
            },
        },
        "blockers": blockers,
        **({"scope": scope} if scope_suite is not None else {}),
        "evidence": evidence,
        "_comment": (
            "Generated by scripts/certify.py — do not hand-edit. Every "
            "computed field re-derives from the named artifacts under "
            "--check; attested fields carry sha-pinned external receipts "
            "and are scaffolding, not certification. A certification "
            "question not answerable from this document is a certificate "
            "defect to file."
            + (
                " For the tariff certificate, S1 zero unexplained records complete "
                "classification, while axiom-attributed-open units independently "
                "block the computed conformant premise."
                if program == "us/tariff-duty"
                else ""
            )
            + (
                " NZ exercise roadmap: commit per-evaluation request/output "
                "traces and derive exercise separately for each certificate "
                "view and requested-output root set."
                if spec.get("attested_exercise_receipt")
                else ""
            )
        ),
    }


def build_all(*, verify_producers: bool = False) -> dict[str, dict]:
    return {
        program: build_certificate(
            program,
            spec,
            verify_producers=verify_producers,
        )
        for program, spec in PROGRAMS.items()
    }


def _out_path(program: str) -> Path:
    return OUT_DIR / f"{program.replace('/', '-')}.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--verify-producers",
        action="store_true",
        help=(
            "opt-in integration gate: additionally re-derive computed closure "
            "from external Git sources and recompile/replay executable "
            "reproductions before certifying"
        ),
    )
    args = parser.parse_args()

    certificates = build_all(verify_producers=args.verify_producers)
    if args.check:
        # An unexpected certificate is a defect, not a curiosity: certificates/
        # is inside the bot's derived_paths, so a retired or stray file there is
        # restored and committed by a refresh (round-3 audit finding 7).
        expected = {_out_path(program).name for program in certificates}
        if OUT_DIR.exists():
            stray = sorted(
                p.name for p in OUT_DIR.glob("*.json") if p.name not in expected
            )
            if stray:
                print(
                    "certificates/ contains files no program generates: "
                    + ", ".join(stray)
                    + " — remove them or add their program to PROGRAMS",
                    file=sys.stderr,
                )
                return 1
        for program, certificate in certificates.items():
            path = _out_path(program)
            if not path.exists():
                print(f"missing {path.relative_to(REPO_ROOT)}", file=sys.stderr)
                return 1
            if json.loads(path.read_text()) != certificate:
                print(
                    f"certificate drifted for {program} — regenerate with "
                    "`uv run python scripts/certify.py`",
                    file=sys.stderr,
                )
                return 1
        print("certificates up to date")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for program, certificate in certificates.items():
        path = _out_path(program)
        path.write_text(json.dumps(certificate, indent=2, sort_keys=True) + "\n")
        verdicts = certificate["verdicts"]
        print(
            f"{program}: CERTIFIED={certificate['certified']['state'].upper()} | "
            f"conformant={verdicts['conformant']['value']} "
            f"exercised={verdicts['exercised']['value']} "
            f"closed={verdicts['closed'].get('status')} "
            f"executable={verdicts['executable'].get('status')}"
        )
        for blocker in certificate["blockers"]:
            print(f"  blocker: {blocker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
