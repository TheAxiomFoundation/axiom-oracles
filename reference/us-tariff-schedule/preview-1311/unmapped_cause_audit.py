#!/usr/bin/env python3
"""Deep, conserving audit of preview-1311 taxonomy_primary=unmapped rows.

This is a lane-local receipt generator.  It does not modify campaign inputs or
either source repository.  The decisive join is exact on the selected-panel
identity carried by the campaign record:

  (hts10, iso2, revision, clipped_from, clipped_until, origin_regime)

Run from the axiom-oracles-cert checkout with its virtual environment:

  .venv/bin/python reference/us-tariff-schedule/preview-1311/unmapped_cause_audit.py
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable

import yaml


HERE = Path(__file__).resolve().parent
CERT_ROOT = HERE.parents[2]
DEFAULT_MISMATCH = HERE / "new-mismatch-cells.jsonl.gz"
DEFAULT_TAXONOMY_RECEIPT = HERE / "mismatch-taxonomy-receipt.json"
DEFAULT_SELECTED = CERT_ROOT / "reference/us-tariff-schedule/selected-intervals.csv.gz"
DEFAULT_STATIC_RECEIPT = HERE / "static-footprint-census-receipt.json"
DEFAULT_YALE_ROOT = Path("/Users/maxghenis/TheAxiomFoundation/_tariff-yale")
DEFAULT_RULESPEC_ROOT = Path("/Users/maxghenis/PolicyEngine/_tariff-p5/b1/c6-roots/rulespec-us")
DEFAULT_OUTPUT = HERE / "unmapped-cause-audit-receipt.json"
IN_SCOPE_ANNEX_TIERS = frozenset({"annex_1a", "annex_1b", "annex_1c", "annex_3",
                                  "annex_1b_inferred_derivative"})
TOLERANCE = 1e-12


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_receipt(path: Path) -> dict[str, Any]:
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}


def canonical(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def repo_receipt(repo: Path, scoped_paths: Iterable[Path]) -> dict[str, Any]:
    relative = [str(path.relative_to(repo)) for path in scoped_paths]
    status = git(repo, "status", "--short", "--", *relative)
    return {
        "root": str(repo),
        "commit": git(repo, "rev-parse", "HEAD"),
        "tree": git(repo, "rev-parse", "HEAD^{tree}"),
        "scoped_status": status.splitlines() if status else [],
    }


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as source:
        return list(csv.DictReader(source))


def normalize_code(value: str) -> str:
    return str(value).strip().replace(".", "")


def csv_prefixes(path: Path, column: str | None = None) -> set[str]:
    rows = read_csv(path)
    if not rows:
        return set()
    column = column or next(iter(rows[0]))
    return {normalize_code(row[column]) for row in rows if row.get(column)}


def text_prefixes(path: Path) -> set[str]:
    with path.open() as source:
        return {
            normalize_code(line) for line in source
            if line.strip() and not line.lstrip().startswith("#")
        }


def prefix_hit(code: str, prefixes: Iterable[str]) -> bool:
    return any(code.startswith(prefix) for prefix in prefixes)


def selected_key(row: dict[str, str]) -> tuple[str, ...]:
    return (
        row["hts10"], row["iso2"], row["revision"], row["clipped_from"],
        row["clipped_until"], row["origin_regime"],
    )


def mismatch_key(row: dict[str, Any]) -> tuple[str, ...]:
    context = row["context"]
    return (
        context["hts10"], context["iso2"], context["revision"],
        context["interval"][0], context["interval"][1], context["origin_regime"],
    )


def load_heading_families(yale_root: Path, policy: dict[str, Any]) -> tuple[dict[str, set[str]], list[Path]]:
    families: dict[str, set[str]] = defaultdict(set)
    sources: list[Path] = []
    aliases = {
        "autos_passenger": "auto_vehicle",
        "autos_light_trucks": "auto_vehicle",
        "copper": "copper",
        "softwood": "wood",
        "wood_furniture": "wood",
        "kitchen_cabinets": "wood",
        "mhd_vehicles": "mhd_vehicle_bus",
        "auto_parts": "auto_parts",
        "mhd_parts": "mhd_parts",
        "buses": "mhd_vehicle_bus",
        "semiconductors": "semiconductor",
    }
    for program, family in aliases.items():
        config = policy["section_232_headings"][program]
        if config.get("prefixes"):
            families[family].update(normalize_code(item) for item in config["prefixes"])
        elif config.get("products_file"):
            path = yale_root / config["products_file"]
            sources.append(path)
            families[family].update(csv_prefixes(path))
        elif config.get("prefixes_file"):
            path = yale_root / config["prefixes_file"]
            sources.append(path)
            families[family].update(text_prefixes(path))
        else:
            raise ValueError(f"unsupported Section 232 heading program {program}")
    return dict(families), sources


def build_annex_classifier(yale_root: Path) -> tuple[Callable[[str, str], str | None], list[Path]]:
    annex_path = yale_root / "resources/s232_annex_products.csv"
    derivative_path = yale_root / "resources/s232_derivative_products.csv"
    annex_rows = read_csv(annex_path)
    derivative_rows = read_csv(derivative_path)

    @lru_cache(maxsize=None)
    def maps_for_date(probe: str) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:
        latest: dict[str, tuple[str, str]] = {}
        for row in annex_rows:
            effective = row.get("effective_date") or "1900-01-01"
            if effective > probe:
                continue
            prefix = normalize_code(row["hts_prefix"])
            old = latest.get(prefix)
            if old is None or effective > old[0]:
                latest[prefix] = (effective, "annex_" + row["annex"])
        # Yale: longest-prefix-first, first-match-wins after latest-date dedupe.
        annex = tuple(sorted(((prefix, value[1]) for prefix, value in latest.items()),
                             key=lambda item: (-len(item[0]), item[0])))
        derivative = tuple(sorted({
            normalize_code(row["hts_prefix"]) for row in derivative_rows
            if (row.get("effective_date") or "1900-01-01") <= probe
        }, key=lambda item: (-len(item), item)))
        return annex, derivative

    @lru_cache(maxsize=None)
    def classify(code: str, probe: str) -> str | None:
        annex, derivative = maps_for_date(probe)
        for prefix, tier in annex:
            if code.startswith(prefix):
                return tier
        if prefix_hit(code, derivative):
            return "annex_1b_inferred_derivative"
        return None

    return classify, [annex_path, derivative_path]


def group_stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    interval_cells = {
        (
            item["row"]["slot"], item["row"]["context"]["hts10"],
            item["row"]["context"]["hts_line"], item["row"]["context"]["iso2"],
            item["row"]["context"]["revision"],
            *item["row"]["context"]["interval"], item["row"]["context"]["origin_regime"],
        )
        for item in records
    }
    effective_cells = {
        (
            item["row"]["slot"], item["row"]["context"]["hts10"],
            item["row"]["context"]["hts_line"], item["row"]["context"]["iso2"],
            item["row"]["context"]["origin_regime"],
        )
        for item in records
    }
    return {
        "units": len(records),
        "interval_slot_cells": len(interval_cells),
        "effective_slot_cells": len(effective_cells),
        "distinct_hts10": len({item["row"]["context"]["hts10"] for item in records}),
        "per_slot": dict(sorted(Counter(item["row"]["slot"] for item in records).items())),
    }


def grouped(records: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    values: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in records:
        value = item[field]
        if value is not None:
            values[str(value)].append(item)
    return {name: group_stats(values[name]) for name in sorted(values)}


def representatives(records: list[dict[str, Any]], limit: int = 4) -> list[dict[str, Any]]:
    answer: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in sorted(records, key=lambda value: (
        value["row"]["slot"], value["row"]["context"]["hts10"],
        value["row"]["context"]["iso2"], value["row"]["probe"],
    )):
        row = item["row"]
        context = row["context"]
        key = (row["slot"], context["hts10"], context["iso2"])
        if key in seen:
            continue
        seen.add(key)
        answer.append({
            "slot": row["slot"], "hts10": context["hts10"],
            "hts_line": context["hts_line"], "iso2": context["iso2"],
            "interval": context["interval"], "probe": row["probe"],
            "expected": row["expected"], "actual": row["actual"],
            "statutory_rate_232": item["statutory_rate_232"],
            "annex_tier": item["annex_tier"],
            "heading_source_families": item["heading_families"],
            "entry_is_section_232_covered": bool(
                context["flags"].get("entry_is_section_232_covered", False)
            ),
        })
        if len(answer) == limit:
            break
    return answer


def interval_stability(records: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for slot in ("brazil_section_301", "forced_labor_section_301"):
        maps: dict[str, dict[tuple[str, ...], tuple[float, str, str | None]]] = defaultdict(dict)
        for item in records:
            row = item["row"]
            if row["slot"] != slot:
                continue
            context = row["context"]
            interval = "..".join(context["interval"])
            base = (
                context["hts10"], context["hts_line"], context["iso2"],
                context["origin_regime"],
            )
            value = (float(row["actual"]), item["top_cause"], item["section232_subcause"])
            previous = maps[interval].setdefault(base, value)
            require(previous == value, f"probe endpoints disagree within {slot} {interval} {base}")
        intervals = sorted(maps)
        comparisons = []
        for left, right in zip(intervals, intervals[1:]):
            left_keys, right_keys = set(maps[left]), set(maps[right])
            shared = left_keys & right_keys
            comparisons.append({
                "left": left, "right": right,
                "left_only_cells": len(left_keys - right_keys),
                "right_only_cells": len(right_keys - left_keys),
                "shared_cells": len(shared),
                "actual_rate_changed_cells": sum(
                    abs(maps[left][key][0] - maps[right][key][0]) > TOLERANCE
                    for key in shared
                ),
                "cause_changed_cells": sum(
                    maps[left][key][1:] != maps[right][key][1:] for key in shared
                ),
            })
        result[slot] = {
            "cells_per_interval": {name: len(maps[name]) for name in intervals},
            "adjacent_comparisons": comparisons,
        }
    return result


def rate_key(value: float) -> str:
    return format(float(value), ".12g")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mismatch", type=Path, default=DEFAULT_MISMATCH)
    parser.add_argument("--selected", type=Path, default=DEFAULT_SELECTED)
    parser.add_argument("--taxonomy-receipt", type=Path, default=DEFAULT_TAXONOMY_RECEIPT)
    parser.add_argument("--static-receipt", type=Path, default=DEFAULT_STATIC_RECEIPT)
    parser.add_argument("--yale-root", type=Path, default=DEFAULT_YALE_ROOT)
    parser.add_argument("--rulespec-root", type=Path, default=DEFAULT_RULESPEC_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    inputs = {
        "new_mismatch_cells": file_receipt(args.mismatch),
        "selected_intervals": file_receipt(args.selected),
        "taxonomy_receipt": file_receipt(args.taxonomy_receipt),
        "static_footprint_receipt": file_receipt(args.static_receipt),
    }
    taxonomy_receipt = json.loads(args.taxonomy_receipt.read_text())
    static_receipt = json.loads(args.static_receipt.read_text())
    require(
        inputs["new_mismatch_cells"]["sha256"]
        == taxonomy_receipt["outputs"]["new_mismatch_cells"]["sha256"],
        "new-mismatch hash does not match taxonomy receipt",
    )
    require(
        inputs["selected_intervals"]["sha256"]
        == static_receipt["inputs"]["selected_intervals"]["sha256"],
        "selected-interval hash does not match preview static receipt",
    )

    policy_path = args.yale_root / "config/policy_params.yaml"
    calculator_path = args.yale_root / "src/pipeline/06_calculate_rates.R"
    loader_path = args.yale_root / "src/model/data_loaders.R"
    ch98_path = args.yale_root / "resources/ieepa_exempt_products.csv"
    pharma_path = args.yale_root / "resources/s232_pharma_products.csv"
    with policy_path.open() as source:
        policy = yaml.safe_load(source)
    heading_families, heading_sources = load_heading_families(args.yale_root, policy)
    annex_classifier, annex_sources = build_annex_classifier(args.yale_root)
    ch98_codes = {
        code for code in csv_prefixes(ch98_path, "hts10") if code.startswith("98")
    }
    patented_pharma = csv_prefixes(pharma_path, "hts10")

    rulespec_sources = [
        args.rulespec_root / "tools/b16_entry_flags.py",
        args.rulespec_root / "us/policies/cbp/us-tariff-duty/composition.yaml",
    ]
    yale_sources = list(dict.fromkeys([
        policy_path, calculator_path, loader_path, ch98_path, pharma_path,
        *heading_sources, *annex_sources,
    ]))
    sources = {
        "yale_repo": repo_receipt(args.yale_root, yale_sources),
        "rulespec_repo": repo_receipt(args.rulespec_root, rulespec_sources),
        "files": {
            str(path): file_receipt(path) for path in sorted(yale_sources + rulespec_sources)
        },
    }

    needed: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    input_units = 0
    with gzip.open(args.mismatch, "rt") as source:
        for line in source:
            row = json.loads(line)
            if row.get("taxonomy_primary") != "unmapped":
                continue
            input_units += 1
            needed[mismatch_key(row)].append(row)
    require(input_units == 187_588, f"unexpected unmapped input units: {input_units}")

    selected_hits: dict[tuple[str, ...], dict[str, str]] = {}
    duplicate_hits: Counter[tuple[str, ...]] = Counter()
    selected_rows_scanned = 0
    with gzip.open(args.selected, "rt", newline="") as source:
        for selected in csv.DictReader(source):
            selected_rows_scanned += 1
            key = selected_key(selected)
            if key not in needed:
                continue
            duplicate_hits[key] += 1
            selected_hits[key] = selected
    require(len(selected_hits) == len(needed), "not every mismatch interval key joined to selected panel")
    require(max(duplicate_hits.values(), default=0) == 1, "selected-panel join was not unique")

    flat10 = set(policy["section_301_forced_labor"]["tier_10pct"])
    net10 = set(policy["section_301_forced_labor"]["tier_10pct_net_mfn"])
    net125 = set(policy["section_301_forced_labor"]["tier_12_5pct_net_mfn"])
    flat125 = set(policy["section_301_forced_labor"]["tier_12_5pct"])

    def country_tier(code: str) -> str:
        if code in flat10:
            return "flat_10pct"
        if code in net10:
            return "net_mfn_10pct"
        if code in net125:
            return "net_mfn_12_5pct"
        if code in flat125:
            return "flat_12_5pct"
        return "unknown"

    records: list[dict[str, Any]] = []
    for key, rows in needed.items():
        selected = selected_hits[key]
        statutory_rate_232 = float(selected["statutory_rate_232"] or 0)
        code = selected["hts10"]
        annex_tier = annex_classifier(code, selected["clipped_from"])
        family_hits = sorted(
            family for family, prefixes in heading_families.items()
            if prefix_hit(code, prefixes)
        )
        for row in rows:
            slot_column = (
                "statutory_rate_s301fl" if row["slot"] == "forced_labor_section_301"
                else "statutory_rate_s301br"
            )
            require(
                abs(float(selected[slot_column]) - float(row["expected"])) <= TOLERANCE,
                f"selected expected rate disagrees with mismatch record {row['case_id']}",
            )
            require(abs(float(row["expected"])) <= TOLERANCE, "unmapped row expected was not zero")
            broadening = "yale-full-list-statistical-broadening" in row.get(
                "taxonomy_detail_labels", []
            )
            is_ch98 = code.startswith("98")
            flag_232 = bool(row["context"]["flags"].get("entry_is_section_232_covered", False))
            if broadening:
                top_cause = "brazil_yale_hts8_statistical_broadening"
            elif is_ch98:
                top_cause = "yale_ch98_secondary_code_zeroing"
            elif statutory_rate_232 > 0:
                top_cause = "yale_section232_per_article_mask"
            else:
                top_cause = "unexplained"

            section232_subcause = None
            if top_cause == "yale_section232_per_article_mask":
                if flag_232:
                    section232_subcause = "engine_metal_fact_exposed_but_unconsumed"
                elif annex_tier in IN_SCOPE_ANNEX_TIERS:
                    section232_subcause = "unflagged_in_scope_annex"
                elif family_hits:
                    section232_subcause = "unflagged_heading_program_source_membership"
                else:
                    section232_subcause = "unflagged_positive_statutory_other"
            records.append({
                "row": row, "selected": selected,
                "statutory_rate_232": statutory_rate_232,
                "annex_tier": annex_tier,
                "heading_families": family_hits,
                "top_cause": top_cause,
                "section232_subcause": section232_subcause,
                "forced_country_tier": country_tier(selected["country"]),
            })

    top = grouped(records, "top_cause")
    require("unexplained" not in top, "unexplained rows remain")
    require(sum(item["units"] for item in top.values()) == input_units, "top causes do not conserve")
    section232_records = [item for item in records if item["top_cause"] == "yale_section232_per_article_mask"]
    section232_subcauses = grouped(section232_records, "section232_subcause")
    require(
        sum(item["units"] for item in section232_subcauses.values()) == len(section232_records),
        "Section 232 subcauses do not conserve",
    )

    broadening_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in records:
        detail = item["row"].get("yale_full_list_statistical_broadening")
        if detail:
            broadening_groups[
                detail["yale_hts8"] + " -> legal " + detail["legal_hts10"]
            ].append(item)

    heading_membership: dict[str, Any] = {}
    for family in sorted(heading_families):
        members = [item for item in section232_records if family in item["heading_families"]]
        heading_membership[family] = group_stats(members)
    heading_combinations = Counter(
        "+".join(item["heading_families"]) if item["heading_families"] else "none"
        for item in section232_records
    )
    unflagged_heading = [
        item for item in section232_records
        if item["section232_subcause"] == "unflagged_heading_program_source_membership"
    ]
    unflagged_heading_combinations = Counter(
        "+".join(item["heading_families"]) for item in unflagged_heading
    )

    annex_tiers = Counter(item["annex_tier"] or "none" for item in section232_records)
    rate_tier_cross = Counter()
    rate_tier_actuals: dict[str, Counter[str]] = defaultdict(Counter)
    for item in records:
        if item["row"]["slot"] != "forced_labor_section_301":
            continue
        tier = item["forced_country_tier"]
        require(tier != "unknown", f"unknown forced-labor country tier: {item['selected']['country']}")
        rate_tier_cross[(tier, item["top_cause"])] += 1
        rate_tier_actuals[tier][rate_key(item["row"]["actual"])] += 1

    ch98_records = [item for item in records if item["top_cause"] == "yale_ch98_secondary_code_zeroing"]
    require(all(item["row"]["context"]["hts10"] in ch98_codes for item in ch98_records),
            "not every Chapter 98 cause row is in Yale's Chapter 98 zero list")
    patent_records = [
        item for item in records if item["row"]["context"]["hts10"] in patented_pharma
    ]
    broad_records = [
        item for item in records if item["top_cause"] == "brazil_yale_hts8_statistical_broadening"
    ]

    stability = interval_stability(records)
    all_stable = all(
        comparison["left_only_cells"] == 0
        and comparison["right_only_cells"] == 0
        and comparison["actual_rate_changed_cells"] == 0
        and comparison["cause_changed_cells"] == 0
        for slot in stability.values() for comparison in slot["adjacent_comparisons"]
    )
    require(all_stable, "unmapped mismatch population changed across effective-date boundaries")

    categories_for_samples = {
        **{name: [item for item in records if item["top_cause"] == name] for name in top},
        **{
            name: [item for item in section232_records if item["section232_subcause"] == name]
            for name in section232_subcauses
        },
    }
    receipt: dict[str, Any] = {
        "schema": "axiom_oracles.us_tariff_schedule.preview_1311_unmapped_cause_audit.v1",
        "inputs": inputs,
        "sources": sources,
        "join": {
            "key": ["hts10", "iso2", "revision", "clipped_from", "clipped_until", "origin_regime"],
            "selected_rows_scanned": selected_rows_scanned,
            "mismatch_interval_keys": len(needed),
            "joined_keys": len(selected_hits),
            "missing_keys": len(needed) - len(selected_hits),
            "duplicate_selected_keys": sum(count > 1 for count in duplicate_hits.values()),
        },
        "definitions": {
            "unit": "one campaign case-slot probe endpoint",
            "interval_slot_cell": "unique slot+hts10+hts_line+iso2+revision+clipped interval+origin_regime",
            "effective_slot_cell": "unique slot+hts10+hts_line+iso2+origin_regime, ignoring interval/probe",
            "exclusive_top_precedence": [
                "Brazil Yale HTS8 statistical broadening",
                "Chapter 98 secondary-code zeroing",
                "selected-panel statutory_rate_232 > 0",
                "unexplained",
            ],
        },
        "classification": {
            "input_unmapped_units": input_units,
            "exclusive_top_causes": top,
            "top_conservation": {
                "exclusive_sum": sum(item["units"] for item in top.values()),
                "equals_input": sum(item["units"] for item in top.values()) == input_units,
            },
            "section232_exclusive_subcauses": section232_subcauses,
            "section232_subcause_conservation": {
                "exclusive_sum": sum(item["units"] for item in section232_subcauses.values()),
                "equals_section232_top": sum(item["units"] for item in section232_subcauses.values())
                == len(section232_records),
            },
            "section232_annex_tier_units": dict(sorted(annex_tiers.items())),
            "section232_heading_source_membership_nonexclusive": heading_membership,
            "section232_heading_source_combination_units_nonexclusive_population": dict(
                sorted(heading_combinations.items())
            ),
            "unflagged_heading_exclusive_population_combination_units": dict(
                sorted(unflagged_heading_combinations.items())
            ),
            "brazil_broadening_by_yale_parent": {
                name: group_stats(group) for name, group in sorted(broadening_groups.items())
            },
            "overlaps": {
                "brazil_broadening_with_positive_statutory_rate_232_units": sum(
                    item["statutory_rate_232"] > 0 for item in broad_records
                ),
                "chapter98_in_yale_ch98_zero_list_units": sum(
                    item["row"]["context"]["hts10"] in ch98_codes for item in ch98_records
                ),
                "patented_pharma_source_membership_units": len(patent_records),
            },
        },
        "timing_and_rates": {
            "interval_population_and_rate_stability": stability,
            "all_interval_sets_rates_and_causes_stable": all_stable,
            "forced_country_tier_by_top_cause_units": {
                tier + " | " + cause: units
                for (tier, cause), units in sorted(rate_tier_cross.items())
            },
            "forced_actual_rate_units_by_country_tier": {
                tier: dict(sorted(counter.items(), key=lambda item: float(item[0])))
                for tier, counter in sorted(rate_tier_actuals.items())
            },
            "patented_pharma_effective_2026_07_31_membership": group_stats(patent_records),
        },
        "interpretation": {
            "direct_pr_formula_gap_units": section232_subcauses[
                "engine_metal_fact_exposed_but_unconsumed"
            ]["units"],
            "additional_pr_fact_surface_gap_units": (
                section232_subcauses["unflagged_in_scope_annex"]["units"]
                + section232_subcauses["unflagged_heading_program_source_membership"]["units"]
            ),
            "yale_positive_statutory_scope_review_units": section232_subcauses.get(
                "unflagged_positive_statutory_other", {"units": 0}
            )["units"],
            "panel_or_entry_semantics_units_exclusive": (
                top["brazil_yale_hts8_statistical_broadening"]["units"]
                + top["yale_ch98_secondary_code_zeroing"]["units"]
            ),
            "effective_date_gap_units": 0,
            "country_rate_vintage_gap_units": 0,
            "notes": [
                "The exposed entry_is_section_232_covered fact is true for the direct formula-gap population, but PR #1311's note-50/52 formulas do not consume it.",
                "Unflagged annex and heading-program rows require a broader per-article Section 232 fact surface to reproduce Yale's mask.",
                "The exact latest-effective-date, longest-prefix annex classifier leaves no positive-statutory row outside an in-scope annex tier or a heading-program source family.",
                "Every Chapter 98 row is in Yale's Chapter 98 zero list. Rulespec deliberately keeps forced_labor_section_301_component_rate as a non-exempt panel projection and applies Chapter 98 only in the entry-level component, so these are panel/entry semantics rather than an effective-date failure.",
                "The varying forced-labor actual rates below 10/12.5 percent are the intended net-of-MFN country-tier formulas. The same cells and rates persist across July 24 and July 31.",
                "No unmapped row belongs to Yale's patented-pharma source list, so the July 31 patented-pharma gate creates no residual in this population.",
            ],
        },
        "representative_cells": {
            name: representatives(group) for name, group in sorted(categories_for_samples.items())
        },
        "commands": {
            "generate": (
                ".venv/bin/python "
                "reference/us-tariff-schedule/preview-1311/unmapped_cause_audit.py"
            ),
        },
        "script": file_receipt(Path(__file__).resolve()),
        "verdict": "PASS",
    }
    receipt["receipt_payload_hash_scope"] = "all keys except receipt_payload_sha256"
    receipt["receipt_payload_sha256"] = hashlib.sha256(canonical(receipt)).hexdigest()
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "verdict": receipt["verdict"],
        "output": file_receipt(args.output),
        "input_unmapped_units": input_units,
        "exclusive_top_units": {name: value["units"] for name, value in top.items()},
        "section232_subcause_units": {
            name: value["units"] for name, value in section232_subcauses.items()
        },
        "all_interval_sets_rates_and_causes_stable": all_stable,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
