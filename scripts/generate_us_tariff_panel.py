#!/usr/bin/env python3
"""US tariff panel comparison: rulespec-us spine vs the Yale Budget Lab panel.

Companion to TheAxiomFoundation/axiom-oracles#444 (P5). Evaluates every
covered (HTS-10 line, country, validity interval) cell of the committed Yale
panel extract (``reference/us-tariff-panel/``, see its README for the
supervised extraction leg) through the composed rulespec-us pipeline
``us:policies/cbp/us-tariff-duty/composition`` at both interval endpoints
clipped to the encoded temporal domain, and grades the per-authority
component rates and the statutory total exactly (tolerance 1e-12).

The reference side is reviewer-independent: the Yale panel is built from
their pipeline (legal-date mode, ``--full --unweighted
--skip-release-check``), never from artifacts shared with the rulespec-us
implementation. Expected totals are the SUM of their ``statutory_*`` columns
— never the panel's stored effective (utilization-share-scaled) totals.

Mismatches are expected and must stay visible (reference-vintage gaps,
uncovered authorities, preference-semantics boundaries); they are grouped
losslessly by signature — every member unit is enumerated, nothing is
capped or dropped.

Run locally (needs a built axiom rules engine and a rulespec-us checkout
with the us-tariff-duty spine)::

    RULESPEC_US_CHECKOUT=/path/to/rulespec-us \
      uv run python scripts/generate_us_tariff_panel.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS = REPO_ROOT / "reports"
DASH_PUBLIC = REPO_ROOT / "dashboard" / "public" / "data"

sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.suites.us_tariff_panel import (  # noqa: E402
    AUTHORITY_SLOTS,
    COMPOSITION_MODULE,
    DOMAIN_START,
    OUTPUTS,
    REFERENCE_DIRNAME,
    TOLERANCE,
    TOTAL,
    PanelInterval,
    case_id,
    column_exposure,
    covered_units,
    load_provenance,
    load_reference,
    panel_case,
    straddle_clipped,
    temporal_debt,
    temporal_debt_records,
)

RULESPEC_US = Path(
    os.environ.get("RULESPEC_US_CHECKOUT")
    or os.path.expanduser("~/TheAxiomFoundation/rulespec-us")
)
COMPOSITION_PATH = "us/policies/cbp/us-tariff-duty/composition.yaml"

BASENAME = "axiom-yale-us-tariff-panel"
VALIDATION_YEAR = 2026


def _evaluate(units: list[tuple[PanelInterval, date]]) -> dict[str, dict[str, float]]:
    """Engine values for every unit, keyed by case id. Any error is fatal."""
    from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner

    program = RULESPEC_US / COMPOSITION_PATH
    if not program.exists():
        raise FileNotFoundError(
            f"composition module not found: {program} "
            "(set RULESPEC_US_CHECKOUT to a rulespec-us checkout with the "
            "us-tariff-duty spine)"
        )
    runner = AxiomRulesRunner(
        program_path=program,
        binary_path=os.environ.get("AXIOM_RULES_ENGINE_BINARY"),
        default_entity="CustomsEntry",
        default_entity_id="entry",
        rulespec_repo_roots=(RULESPEC_US,),
        mode="explain",
    )
    cases = [panel_case(interval, probe) for interval, probe in units]
    results = runner.run_cases(cases, list(OUTPUTS))
    values: dict[str, dict[str, float]] = {}
    for result in results:
        if result.errors:
            # One out-of-domain case poisons its whole engine batch, so a
            # failure here is a harness defect (domain clipping bug), never
            # a skippable case.
            raise RuntimeError(
                f"axiom rules engine failed for {result.household_id}: "
                f"{result.errors}"
            )
        values[str(result.household_id)] = {
            concept: float(value) for concept, value in result.values.items()
        }
    return values


def _match(left: float, right: float) -> bool:
    return abs(left - right) <= TOLERANCE


def _composition_effective_dates(node: object) -> set[date]:
    """Every ``effective_from`` date anywhere in a parsed composition doc."""
    dates: set[date] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "effective_from":
                dates.add(
                    value if isinstance(value, date) else date.fromisoformat(str(value))
                )
            else:
                dates |= _composition_effective_dates(value)
    elif isinstance(node, list):
        for item in node:
            dates |= _composition_effective_dates(item)
    return dates


def assert_domain_matches_composition(composition_path: Path) -> None:
    """DOMAIN_START must equal the live spine's earliest effective_from.

    The temporal-debt account (pre-domain + straddle-clipped intervals in
    the report scope) is only honest while the hardcoded ``DOMAIN_START``
    matches what the composed spine actually parameterizes. If the spine
    burns down coverage to earlier dates (or narrows), a stale constant
    would silently mis-classify debt as covered or vice versa — so the
    generator refuses to run on a divergent pair (sol stack review F4).
    """
    import yaml

    doc = yaml.safe_load(composition_path.read_text())
    dates = _composition_effective_dates(doc)
    if not dates:
        raise SystemExit(
            f"no effective_from dates found in {composition_path} — cannot "
            "verify DOMAIN_START against the live composition"
        )
    earliest = min(dates)
    if earliest != DOMAIN_START:
        raise SystemExit(
            f"DOMAIN_START {DOMAIN_START.isoformat()} does not match the "
            f"composed spine's earliest effective_from "
            f"({earliest.isoformat()} in {composition_path}) — update "
            "axiom_oracles/suites/us_tariff_panel.py and re-derive the "
            "temporal-debt account in the same reviewed diff"
        )


def build_report(
    intervals: list[PanelInterval],
    unbridged: list[str],
    units: list[tuple[PanelInterval, date]],
    values: dict[str, dict[str, float]],
    reference_provenance: dict,
) -> dict:
    slot_matches: dict[str, int] = defaultdict(int)
    slot_mismatches: dict[str, int] = defaultdict(int)
    internal_inconsistencies = 0

    # One dispositions-addressable row per mismatched unit (case_id = unit id,
    # concept = the composed total): apply_dispositions matches rows by
    # case_id/concept and counts annotated ROWS against the unit-grain
    # match/comparison counts, so the mismatch list must be unit-grain too.
    unit_rows: list[dict] = []
    # Lossless signature grouping: (hts10, slot, expected, actual) -> members.
    groups: dict[tuple[str, str, float, float], dict] = {}
    # Case families for the dashboard: (hts10, expected vector, actual
    # vector) -> member cells. Rates are step functions over countries, so
    # this is compact without dropping anything.
    families: dict[tuple, dict] = {}

    for interval, probe in units:
        cid = case_id(interval, probe)
        vals = values[cid]
        expected_by_slot: dict[str, float] = {}
        actual_by_slot: dict[str, float] = {}
        slot_deltas: dict[str, dict[str, float]] = {}
        unit_ok = True
        for slot, (concept, yale_columns) in AUTHORITY_SLOTS.items():
            expected = sum(interval.rates[column] for column in yale_columns)
            actual = vals[concept] if concept is not None else 0.0
            expected_by_slot[slot] = expected
            actual_by_slot[slot] = actual
            if _match(actual, expected):
                slot_matches[slot] += 1
                continue
            unit_ok = False
            slot_mismatches[slot] += 1
            slot_deltas[slot] = {"axiom": actual, "yale": expected}
            key = (interval.hts10, slot, round(expected, 12), round(actual, 12))
            group = groups.setdefault(
                key,
                {
                    "kind": "component_difference",
                    "hts_number": interval.hts10,
                    "authority": slot,
                    "concept": concept,
                    "engines": ["axiom", "yale_statutory"],
                    "left_engine": "axiom",
                    "right_engine": "yale_statutory",
                    "left": actual,
                    "right": expected,
                    "difference": actual - expected,
                    "unit_count": 0,
                    "units": [],
                },
            )
            group["unit_count"] += 1
            group["units"].append(cid)

        expected_total = interval.statutory_total
        actual_total = vals[TOTAL]
        expected_by_slot["total"] = expected_total
        actual_by_slot["total"] = actual_total
        total_ok = _match(actual_total, expected_total)
        if total_ok:
            slot_matches["total"] += 1
        else:
            unit_ok = False
            slot_mismatches["total"] += 1
            slot_deltas["total"] = {
                "axiom": actual_total,
                "yale": expected_total,
            }
            key = (interval.hts10, "total", round(expected_total, 12),
                   round(actual_total, 12))
            group = groups.setdefault(
                key,
                {
                    "kind": "total_difference",
                    "hts_number": interval.hts10,
                    "authority": "total",
                    "concept": TOTAL,
                    "engines": ["axiom", "yale_statutory"],
                    "left_engine": "axiom",
                    "right_engine": "yale_statutory",
                    "left": actual_total,
                    "right": expected_total,
                    "difference": actual_total - expected_total,
                    "unit_count": 0,
                    "units": [],
                },
            )
            group["unit_count"] += 1
            group["units"].append(cid)

        # Engine-side self-consistency: our components must sum to our total.
        component_sum = sum(
            vals[concept]
            for concept, _ in AUTHORITY_SLOTS.values()
            if concept is not None
        )
        if not _match(component_sum, actual_total):
            internal_inconsistencies += 1

        if not unit_ok:
            unit_rows.append(
                {
                    "case_id": cid,
                    # A slot mismatch can in principle cancel in the total;
                    # the kind records which is live for this unit.
                    "kind": (
                        "component_difference"
                        if total_ok
                        else "total_difference"
                    ),
                    "concept": TOTAL,
                    "authority": "total",
                    "hts_number": interval.hts10,
                    "country_census": interval.country_census,
                    "iso2": interval.iso2,
                    "probe_date": probe.isoformat(),
                    "engines": ["axiom", "yale_statutory"],
                    "left_engine": "axiom",
                    "right_engine": "yale_statutory",
                    "left": actual_total,
                    "right": expected_total,
                    "difference": actual_total - expected_total,
                    "slots": slot_deltas,
                }
            )

        family_key = (
            interval.hts10,
            tuple(sorted(expected_by_slot.items())),
            tuple(sorted(actual_by_slot.items())),
        )
        family = families.setdefault(
            family_key,
            {
                "hts_number": interval.hts10,
                "expected": expected_by_slot,
                "axiom": actual_by_slot,
                "match": unit_ok,
                "unit_count": 0,
                "countries": set(),
                "probe_dates": set(),
            },
        )
        family["unit_count"] += 1
        family["countries"].add(interval.country_census)
        family["probe_dates"].add(probe.isoformat())

    n_units = len(units)
    unit_mismatch_count = len(unit_rows)
    match_count = n_units - unit_mismatch_count
    match_rate = round(100.0 * match_count / n_units, 6) if n_units else 100.0
    debt = temporal_debt(intervals)

    mismatches = sorted(
        unit_rows,
        key=lambda r: (
            r["hts_number"],
            r["country_census"],
            r["probe_date"],
        ),
    )
    signatures = sorted(
        groups.values(),
        key=lambda g: (-g["unit_count"], g["hts_number"], g["authority"]),
    )
    case_rows = []
    for index, family in enumerate(
        sorted(
            families.values(),
            key=lambda f: (f["hts_number"], -f["unit_count"]),
        )
    ):
        case_rows.append(
            {
                "case_id": f"family-{family['hts_number']}-{index:04d}",
                "scenario": "panel-cell-family",
                "hts_number": family["hts_number"],
                "match": family["match"],
                "unit_count": family["unit_count"],
                "countries": sorted(family["countries"]),
                "probe_dates": sorted(family["probe_dates"]),
                "expected": family["expected"],
                "axiom": family["axiom"],
            }
        )

    return {
        "schema_version": "axiom.comparison_report.v2",
        "suite": "us-tariff-panel",
        "concept": TOTAL,
        "population": "yale-panel-covered-slice",
        "validation_year": VALIDATION_YEAR,
        "locales": ["US"],
        "scope": {
            "covered_lines": sorted({i.hts10 for i in intervals}),
            "countries": len({i.country_census for i in intervals}),
            "domain_start": DOMAIN_START.isoformat(),
            "in_scope_intervals": len(intervals),
            "covered_intervals": len(intervals) - len(debt),
            "temporal_debt_intervals": len(debt),
            # Addressable temporal debt (sol stack review F4): every
            # unaudited (interval, kind) group is enumerated — an aggregate
            # count alone can neither be audited nor burned down.
            "temporal_debt": {
                "pre_domain_intervals": len(debt),
                "straddle_clipped_intervals": len(straddle_clipped(intervals)),
                "records": temporal_debt_records(intervals),
            },
            # Positive-exposure witness basis (sol stack review F3): the
            # scoreboard refuses a covered verdict for a policy whose
            # statutory columns are 0 everywhere in the covered slice —
            # such a comparison exercises nothing.
            "column_exposure": column_exposure(units),
            "comparison_units": n_units,
            "authority_slots": list(AUTHORITY_SLOTS) + ["total"],
            # Reference vintage lives here (not only under provenance):
            # the run_comparison chain replaces the provenance block with
            # its normalized runner provenance, and the published report
            # must keep the Yale pin + extract sha for staleness honesty.
            "reference": reference_provenance,
        },
        "engines": {
            "axiom": TOTAL,
            "yale_statutory": (
                "Yale Budget Lab tariff-rate-tracker statutory panel "
                "(legal-date mode; committed covered-slice extract)"
            ),
        },
        "tolerance": {"absolute": TOLERANCE, "relative": 0.0},
        "case_count": n_units,
        "summary": {
            "comparison_count": n_units,
            "match_count": match_count,
            "mismatch_count": unit_mismatch_count,
            "axiom_vs_yale_statutory_match_rate": match_rate,
            "weighted": {
                "comparison_weight": n_units,
                "match_weight": match_count,
                "mismatch_weight": unit_mismatch_count,
                "match_rate": match_rate,
            },
            "slots": {
                slot: {
                    "matches": slot_matches.get(slot, 0),
                    "mismatches": slot_mismatches.get(slot, 0),
                }
                for slot in list(AUTHORITY_SLOTS) + ["total"]
            },
            "mismatches_by_concept": [
                {
                    "count": slot_mismatches[slot],
                    "value": AUTHORITY_SLOTS[slot][0] or f"(uncovered:{slot})",
                }
                for slot in AUTHORITY_SLOTS
                if slot_mismatches.get(slot)
            ]
            + (
                [{"count": slot_mismatches["total"], "value": TOTAL}]
                if slot_mismatches.get("total")
                else []
            ),
            "mismatches_by_kind": [
                {
                    "count": sum(1 for r in mismatches if r["kind"] == kind),
                    "value": kind,
                }
                for kind in ("component_difference", "total_difference")
                if any(r["kind"] == kind for r in mismatches)
            ],
            "internal_component_sum_inconsistencies": internal_inconsistencies,
            "unbridged_census_codes": unbridged,
            "error_count": 0,
            "errors_by_engine": [],
        },
        "mismatches": mismatches,
        # Lossless signature index over the unit rows: every member unit of
        # every (hts10, authority slot, expected, actual) signature is
        # enumerated — nothing is capped or dropped.
        "mismatch_signatures": signatures,
        "errors": [],
        "cases": case_rows,
        "provenance": {
            "generated": datetime.now(timezone.utc).date().isoformat(),
            "generator": "scripts/generate_us_tariff_panel.py",
            "axiom_engine": (
                f"axiom rules engine over rulespec-us {COMPOSITION_PATH} "
                f"({COMPOSITION_MODULE})"
            ),
            "reference": reference_provenance,
            "commensurability": (
                "Both sides are statutory ad-valorem rate stacks for the "
                "same (HTS-10 line, origin, date) cell in legal-date mode. "
                "The reference side is the Yale panel's statutory_* columns "
                "(their statutory layer, before utilization/share "
                "estimation); the axiom side is the composed per-authority "
                "component rates. Totals compare our composed total against "
                "the SUM of their statutory columns — their stored "
                "total_rate/total_additional are effective (share-scaled) "
                "and are never used. Differences are real semantic, "
                "encoding, or reference-vintage differences; they are "
                "grouped losslessly by signature and classified in the "
                "dispositions file, never suppressed."
            ),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="US tariff panel comparison generator"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=(
            "Write the full report ONLY to this run-private path. Used by "
            "scripts/run_comparison.py so its handoff can never pick up a "
            "stale shared artifact (a prior dashboard or reports/ file) as "
            "this run's output. Without --out, the dated reports/ copy and "
            "the dashboard slot are written (manual supervised runs)."
        ),
    )
    args = parser.parse_args(argv)
    assert_domain_matches_composition(RULESPEC_US / COMPOSITION_PATH)
    reference_dir = REPO_ROOT / REFERENCE_DIRNAME
    intervals, unbridged = load_reference(reference_dir)
    if unbridged:
        # A census code without a bridge entry means silently dropped
        # comparison rows — refuse to emit a narrowed report.
        raise SystemExit(
            f"unbridged census code(s) in the panel extract: {unbridged} — "
            "rebuild the bridge (scripts/build_census_iso_bridge.py) before "
            "generating the report"
        )
    reference_provenance = load_provenance(reference_dir)
    units = covered_units(intervals)
    print(
        f"{len(intervals)} in-scope intervals, "
        f"{len(intervals) - len(temporal_debt(intervals))} covered, "
        f"{len(units)} comparison units"
    )
    values = _evaluate(units)
    report = build_report(intervals, unbridged, units, values, reference_provenance)

    payload = json.dumps(report, indent=2) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload)
    else:
        REPORTS.mkdir(exist_ok=True)
        DASH_PUBLIC.mkdir(parents=True, exist_ok=True)
        stamp = date.today().isoformat()
        (REPORTS / f"{BASENAME}-{stamp}.json").write_text(payload)
        (DASH_PUBLIC / f"{BASENAME}.json").write_text(payload)

    summary = report["summary"]
    print(
        f"us-tariff-panel: match {summary['axiom_vs_yale_statutory_match_rate']}% "
        f"({summary['match_count']}/{report['case_count']} units); "
        f"{len(report['mismatches'])} mismatched units in "
        f"{len(report['mismatch_signatures'])} signatures"
    )
    for slot, counts in summary["slots"].items():
        if counts["mismatches"]:
            print(f"  {slot}: {counts['mismatches']} mismatched units")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
