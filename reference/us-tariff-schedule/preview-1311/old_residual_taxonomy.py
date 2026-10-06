#!/usr/bin/env python3
"""Conserving taxonomy for old-class residuals in the #1311 preview.

This is a read-only analysis of the campaign artifacts and the two pinned source
trees.  It writes one JSON receipt and makes no repository or toolchain edits.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml


FORCED_FLAT_10 = {
    "AR", "BD", "KH", "CA", "EC", "SV", "GT", "HN", "IN", "ID",
    "JO", "MY", "MX", "PK", "LK", "TT", "GB",
}
FORCED_CAP_10 = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR",
    "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL",
    "PL", "PT", "RO", "SK", "SI", "ES", "SE", "TW",
}
FORCED_CAP_12_5 = {"JP", "KR", "CH"}
FORCED_FLAT_12_5 = {
    "DZ", "AO", "AU", "BS", "BH", "BR", "CL", "CN", "CO", "CR",
    "DO", "EG", "GY", "HK", "IQ", "IL", "KZ", "KW", "LY", "MA",
    "NZ", "NI", "NG", "NO", "OM", "PE", "PH", "QA", "RU", "SA",
    "SG", "ZA", "TH", "TR", "AE", "UY", "VE", "VN",
}

CAP_LINES = {"8712005000", "8714915000", "8714921000", "8714949000"}
TARGET_REVISIONS = {"bnd_2026-07-24", "bnd_2026-07-31"}
RAW_REVISIONS = ("10", "11", "12")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mismatch-cells", type=Path, required=True)
    parser.add_argument("--selected-intervals", type=Path, required=True)
    parser.add_argument("--classification-receipt", type=Path, required=True)
    parser.add_argument("--yale-root", type=Path, required=True)
    parser.add_argument("--rulespec-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_receipt(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    return {
        "path": str(resolved),
        "bytes": resolved.stat().st_size,
        "sha256": sha256(resolved),
    }


def git_value(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, text=True, capture_output=True
    ).stdout.strip()


def git_receipt(root: Path) -> dict[str, Any]:
    return {
        "path": str(root.resolve()),
        "commit": git_value(root, "rev-parse", "HEAD"),
        "tree": git_value(root, "rev-parse", "HEAD^{tree}"),
    }


def read_codes(path: Path, column: str, condition: str | None = None) -> set[str]:
    result: set[str] = set()
    with path.open(newline="") as stream:
        for row in csv.DictReader(stream):
            if condition is None or row.get("condition") == condition:
                result.add(str(row[column]).strip())
    return result


def code_hit(codes: set[str], hts10: str) -> bool:
    return hts10 in codes or hts10[:8] in codes


def origin_tier(slot: str, iso2: str) -> str:
    if slot == "brazil_section_301":
        return "brazil-25"
    if iso2 in FORCED_FLAT_10:
        return "flat-10"
    if iso2 in FORCED_CAP_10:
        return "mfn-cap-10"
    if iso2 in FORCED_CAP_12_5:
        return "mfn-cap-12.5"
    if iso2 in FORCED_FLAT_12_5:
        return "flat-12.5"
    raise AssertionError(f"unknown forced-labor origin: {iso2}")


def rate_token(value: float) -> str:
    return format(float(value), ".17g")


def interval_token(value: list[str]) -> str:
    return f"{value[0]}..{value[1]}"


def compact_row(row: dict[str, Any]) -> dict[str, Any]:
    context = row["context"]
    return {
        "case_id": row["case_id"],
        "slot": row["slot"],
        "probe": row["probe"],
        "expected": row["expected"],
        "actual": row["actual"],
        "delta_actual_minus_expected": row["delta"],
        "hts10": context["hts10"],
        "hts_line": context["hts_line"],
        "chapter": context["hts_line"][:2],
        "iso2": context["iso2"],
        "origin_tier": origin_tier(row["slot"], context["iso2"]),
        "revision": context["revision"],
        "interval": context["interval"],
        "origin_regime": context["origin_regime"],
        "true_flags": sorted(k for k, value in context["flags"].items() if value),
        "old_target_class": row["old_target_class"],
        "current_class": row["current_class"],
        "new_disagreement": row["new_disagreement"],
        "cafta_52i_exact": row["cafta_52i_exact"],
    }


class Accumulator:
    def __init__(self, label: str, cause: str, relation: str) -> None:
        self.label = label
        self.cause = cause
        self.relation = relation
        self.units = 0
        self.rate_pairs: Counter[tuple[float, float, float]] = Counter()
        self.probes: Counter[str] = Counter()
        self.intervals: Counter[str] = Counter()
        self.revisions: Counter[str] = Counter()
        self.origins: Counter[str] = Counter()
        self.origin_tiers: Counter[str] = Counter()
        self.chapters: Counter[str] = Counter()
        self.flag_signatures: Counter[str] = Counter()
        self.flag_true: Counter[str] = Counter()
        self.current_classes: Counter[str] = Counter()
        self.case_ids: set[str] = set()
        self.hts10: set[str] = set()
        self.hts_lines: set[str] = set()
        self.hts10_origins: set[tuple[str, str]] = set()
        self.interval_cells: set[tuple[str, str, str, tuple[str, str]]] = set()
        self.representatives: dict[str, tuple[tuple[Any, ...], dict[str, Any]]] = {}

    def add(self, row: dict[str, Any]) -> None:
        context = row["context"]
        tier = origin_tier(row["slot"], context["iso2"])
        true_flags = tuple(sorted(k for k, value in context["flags"].items() if value))
        self.units += 1
        self.rate_pairs[(row["expected"], row["actual"], row["delta"])] += 1
        self.probes[row["probe"]] += 1
        self.intervals[interval_token(context["interval"])] += 1
        self.revisions[context["revision"]] += 1
        self.origins[context["iso2"]] += 1
        self.origin_tiers[tier] += 1
        self.chapters[context["hts_line"][:2]] += 1
        self.flag_signatures[",".join(true_flags) or "<none>"] += 1
        self.flag_true.update(true_flags)
        self.current_classes[row["current_class"] or "__null__"] += 1
        self.case_ids.add(row["case_id"])
        self.hts10.add(context["hts10"])
        self.hts_lines.add(context["hts_line"])
        self.hts10_origins.add((context["hts10"], context["iso2"]))
        self.interval_cells.add(
            (
                context["hts10"],
                context["iso2"],
                context["revision"],
                tuple(context["interval"]),
            )
        )
        order = (
            context["hts10"], context["iso2"], row["probe"], row["case_id"]
        )
        old = self.representatives.get(tier)
        if old is None or order < old[0]:
            self.representatives[tier] = (order, compact_row(row))

    def as_json(self) -> dict[str, Any]:
        case_digest = hashlib.sha256(
            "\n".join(sorted(self.case_ids)).encode()
        ).hexdigest()
        rate_pairs = [
            {
                "expected": rate_token(expected),
                "actual": rate_token(actual),
                "delta_actual_minus_expected": rate_token(delta),
                "units": units,
            }
            for (expected, actual, delta), units in sorted(
                self.rate_pairs.items(), key=lambda item: item[0]
            )
        ]
        return {
            "units": self.units,
            "cause_axis": self.cause,
            "expected_actual_relation": self.relation,
            "case_id_set_sha256": case_digest,
            "distinct": {
                "case_ids": len(self.case_ids),
                "hts10": len(self.hts10),
                "hts_lines": len(self.hts_lines),
                "origins": len(self.origins),
                "chapters": len(self.chapters),
                "hts10_origin_cells": len(self.hts10_origins),
                "interval_cells": len(self.interval_cells),
                "rate_pairs": len(self.rate_pairs),
            },
            "by_rate_pair": rate_pairs,
            "by_probe": dict(sorted(self.probes.items())),
            "by_interval": dict(sorted(self.intervals.items())),
            "by_revision": dict(sorted(self.revisions.items())),
            "by_origin": dict(sorted(self.origins.items())),
            "by_origin_tier": dict(sorted(self.origin_tiers.items())),
            "by_chapter": dict(sorted(self.chapters.items())),
            "by_flag_signature": dict(sorted(self.flag_signatures.items())),
            "flag_true_counts": dict(sorted(self.flag_true.items())),
            "by_current_class": dict(sorted(self.current_classes.items())),
            "representatives_by_origin_tier": {
                tier: value[1] for tier, value in sorted(self.representatives.items())
            },
        }


def conditional_rulespec_sets(
    rulespec_root: Path,
) -> tuple[dict[str, set[str]], list[dict[str, Any]], list[Path]]:
    prefixes = {
        "brazil_aircraft": "brazil_301_aircraft_conditional_membership_",
        "brazil_pharma": "brazil_301_pharma_conditional_membership_",
        "forced_aircraft": "forced_labor_301_aircraft_conditional_membership_",
        "forced_pharma": "forced_labor_301_pharma_conditional_membership_",
    }
    found = {label: set() for label in prefixes}
    deferred: list[dict[str, Any]] = []
    source_paths: list[Path] = []
    base = rulespec_root / "us/policies/usitc/us-tariff-incidence/generated"
    for family in ("note50", "note52"):
        for path in sorted((base / family).glob("page-*.yaml")):
            if path.name.endswith(".test.yaml"):
                continue
            module = yaml.safe_load(path.read_text())
            path_used = False
            for item in module.get("module", {}).get("deferred_outputs", []):
                output = str(item.get("output", ""))
                if any(prefix in output for prefix in prefixes.values()):
                    deferred.append(
                        {
                            "path": str(path.relative_to(rulespec_root)),
                            "output": output,
                            "reason": item.get("reason", "").strip(),
                        }
                    )
                    path_used = True
            for rule in module.get("rules", []):
                name = str(rule.get("name", ""))
                for label, prefix in prefixes.items():
                    if not name.startswith(prefix):
                        continue
                    path_used = True
                    for version in rule.get("versions", []):
                        for key in version.get("values", {}):
                            found[label].add(f"{int(key):08d}")
            if path_used:
                source_paths.append(path)
    return found, deferred, source_paths


def raw_hts_rate_proof(yale_root: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    paths: list[Path] = []
    for revision in RAW_REVISIONS:
        path = yale_root / f"data/hts_archives/hts_2026_rev_{revision}.json.gz"
        paths.append(path)
        with gzip.open(path, "rt") as stream:
            rows = json.load(stream)
        seen: set[str] = set()
        for row in rows:
            hts10 = re.sub(r"\D", "", str(row.get("htsno", "")))
            if hts10 not in CAP_LINES:
                continue
            raw = str(row.get("general", ""))
            trimmed = raw.strip()
            records.append(
                {
                    "revision": f"2026_rev_{revision}",
                    "hts10": hts10,
                    "general_raw": raw,
                    "accepted_by_yale_simple_percent_regex": bool(
                        re.fullmatch(r"[0-9.]+%", trimmed)
                    ),
                    "contains_empty_underline_markup": "<u></u>" in raw,
                }
            )
            seen.add(hts10)
        assert seen == CAP_LINES, (revision, sorted(CAP_LINES - seen))
    return {
        "records": sorted(records, key=lambda row: (row["revision"], row["hts10"])),
        "archives": [file_receipt(path) for path in paths],
    }


def rulespec_ch87_rates(rulespec_root: Path) -> tuple[dict[str, float], Path]:
    path = rulespec_root / "us/policies/usitc/us-tariff-duty/lines/generated/ch87.yaml"
    module = yaml.safe_load(path.read_text())
    rule = next(rule for rule in module["rules"] if rule["name"] == "ch87_general_rate")
    values: dict[int, Any] = {}
    for version in rule["versions"]:
        values.update(version.get("values", {}))
    result = {hts10: float(values[int(hts10)]) for hts10 in sorted(CAP_LINES)}
    return result, path


def selected_base_proof(
    selected_path: Path, cap_cells: dict[tuple[str, str], dict[str, Any]]
) -> dict[tuple[str, str], dict[str, set[str]]]:
    proof: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    with gzip.open(selected_path, "rt", newline="") as stream:
        for row in csv.DictReader(stream):
            key = (row["hts10"], row["iso2"])
            if key not in cap_cells or row["revision"] not in TARGET_REVISIONS:
                continue
            proof[key][row["revision"]].add(row["statutory_base_rate"])
    for key in cap_cells:
        assert set(proof[key]) == TARGET_REVISIONS, (key, proof[key])
        assert all(values == {"0"} for values in proof[key].values()), (key, proof[key])
    return proof


def main() -> None:
    args = parse_args()
    mismatch_path = args.mismatch_cells.resolve()
    selected_path = args.selected_intervals.resolve()
    classification_path = args.classification_receipt.resolve()
    yale_root = args.yale_root.resolve()
    rulespec_root = args.rulespec_root.resolve()
    output_path = args.output.resolve()

    yale_files = {
        "policy_params": yale_root / "config/policy_params.yaml",
        "calculator": yale_root / "src/pipeline/06_calculate_rates.R",
        "rate_parser": yale_root / "src/core/helpers.R",
        "forced_common": yale_root / "resources/s301fl_final_common_exemptions.csv",
        "forced_country": yale_root / "resources/s301fl_final_country_exemptions.csv",
        "brazil_aircraft": yale_root / "resources/s301_brazil_aircraft_products.csv",
        "brazil_pharma": yale_root / "resources/s301_brazil_pharma_products.csv",
    }
    fl_air = read_codes(yale_files["forced_common"], "hts_code", "aircraft")
    fl_pharma = read_codes(yale_files["forced_common"], "hts_code", "pharma")
    br_air = read_codes(yale_files["brazil_aircraft"], "hts8")
    br_pharma = read_codes(yale_files["brazil_pharma"], "hts8")

    accumulators = {
        "forced_aircraft_conditional_proxy": Accumulator(
            "forced_aircraft_conditional_proxy",
            "conditional-use model/input comparability",
            "expected = 0.10 * actual (Yale 90% exempt utilization proxy)",
        ),
        "forced_pharma_conditional_proxy": Accumulator(
            "forced_pharma_conditional_proxy",
            "conditional-use model/input comparability",
            "expected = 0.50 * actual (Yale 50% exempt utilization proxy)",
        ),
        "brazil_aircraft_conditional_proxy": Accumulator(
            "brazil_aircraft_conditional_proxy",
            "conditional-use model/input comparability",
            "expected = 0.10 * actual (Yale 90% exempt utilization proxy)",
        ),
        "brazil_pharma_conditional_proxy": Accumulator(
            "brazil_pharma_conditional_proxy",
            "conditional-use model/input comparability",
            "expected = 0.50 * actual (Yale 50% exempt utilization proxy)",
        ),
        "forced_mfn_cap_rate_input_parser": Accumulator(
            "forced_mfn_cap_rate_input_parser",
            "MFN-cap rate input/parser vintage",
            "Axiom actual = max(cap - current General rate, 0); Yale expected = full cap because its target-vintage statutory base is zero",
        ),
    }
    per_slot: Counter[str] = Counter()
    per_old_class: Counter[str] = Counter()
    new_disagreement: Counter[str] = Counter()
    cafta_exact: Counter[str] = Counter()
    cafta_heuristic: Counter[str] = Counter()
    listed_false = 0
    conditional_overlap = 0
    cap_cells: dict[tuple[str, str], dict[str, Any]] = {}

    with gzip.open(mismatch_path, "rt") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("old_target_class") is None:
                continue
            slot = row["slot"]
            context = row["context"]
            hts10 = context["hts10"]
            expected = float(row["expected"])
            actual = float(row["actual"])
            flags = context["flags"]
            per_slot[slot] += 1
            per_old_class[row["old_target_class"]] += 1
            new_disagreement[str(bool(row["new_disagreement"])).lower()] += 1
            cafta_exact[str(bool(row["cafta_52i_exact"])).lower()] += 1
            cafta_heuristic[
                str(bool(row["cafta_52i_country_heuristic"])).lower()
            ] += 1

            relevant_flag = (
                "entry_is_forced_labor_301_listed"
                if slot == "forced_labor_section_301"
                else "entry_is_brazil_301_listed"
            )
            if not flags.get(relevant_flag, False):
                listed_false += 1

            if slot == "forced_labor_section_301":
                air_hit = code_hit(fl_air, hts10)
                pharma_hit = code_hit(fl_pharma, hts10)
                conditional_overlap += int(air_hit and pharma_hit)
                if air_hit:
                    category = "forced_aircraft_conditional_proxy"
                    assert math.isclose(expected, actual * 0.10, abs_tol=1e-12)
                elif pharma_hit:
                    category = "forced_pharma_conditional_proxy"
                    assert math.isclose(expected, actual * 0.50, abs_tol=1e-12)
                else:
                    category = "forced_mfn_cap_rate_input_parser"
                    assert hts10 in CAP_LINES
                    assert expected > actual
                    key = (hts10, context["iso2"])
                    cap_cells.setdefault(key, compact_row(row))
            elif slot == "brazil_section_301":
                air_hit = code_hit(br_air, hts10)
                pharma_hit = code_hit(br_pharma, hts10)
                conditional_overlap += int(air_hit and pharma_hit)
                if air_hit:
                    category = "brazil_aircraft_conditional_proxy"
                    assert math.isclose(expected, actual * 0.10, abs_tol=1e-12)
                elif pharma_hit:
                    category = "brazil_pharma_conditional_proxy"
                    assert math.isclose(expected, actual * 0.50, abs_tol=1e-12)
                else:
                    raise AssertionError(f"unclassified Brazil residual: {row}")
            else:
                raise AssertionError(f"unexpected old-class slot: {slot}")
            accumulators[category].add(row)

    total = sum(per_slot.values())
    assert total == 148_390, total
    assert per_slot == {
        "forced_labor_section_301": 139_654,
        "brazil_section_301": 8_736,
    }
    assert conditional_overlap == 0
    assert listed_false == 0
    assert new_disagreement == {"false": total}
    assert cafta_exact == {"false": total}
    assert cafta_heuristic == {"false": total}
    expected_category_counts = {
        "forced_aircraft_conditional_proxy": 71_168,
        "forced_pharma_conditional_proxy": 68_418,
        "brazil_aircraft_conditional_proxy": 3_654,
        "brazil_pharma_conditional_proxy": 5_082,
        "forced_mfn_cap_rate_input_parser": 68,
    }
    assert {
        key: accumulator.units for key, accumulator in accumulators.items()
    } == expected_category_counts
    assert len(cap_cells) == 17

    rulespec_sets, deferred_outputs, conditional_paths = conditional_rulespec_sets(
        rulespec_root
    )
    yale_sets = {
        "brazil_aircraft": br_air,
        "brazil_pharma": br_pharma,
        "forced_aircraft": fl_air,
        "forced_pharma": fl_pharma,
    }
    parity: dict[str, Any] = {}
    for label in sorted(yale_sets):
        only_rulespec = sorted(rulespec_sets[label] - yale_sets[label])
        only_yale = sorted(yale_sets[label] - rulespec_sets[label])
        parity[label] = {
            "rulespec_unique_hts8": len(rulespec_sets[label]),
            "yale_unique_hts8": len(yale_sets[label]),
            "only_rulespec": only_rulespec,
            "only_yale": only_yale,
            "exact": not only_rulespec and not only_yale,
        }
        assert parity[label]["exact"], (label, only_rulespec, only_yale)

    selected_proof = selected_base_proof(selected_path, cap_cells)
    ch87_rates, ch87_path = rulespec_ch87_rates(rulespec_root)
    cap_cell_proof: list[dict[str, Any]] = []
    for key, representative in sorted(cap_cells.items()):
        hts10, iso2 = key
        cap = 0.10 if iso2 in FORCED_CAP_10 else 0.125
        general_rate = ch87_rates[hts10]
        actual = float(representative["actual"])
        expected = float(representative["expected"])
        assert math.isclose(expected, cap, abs_tol=1e-12)
        assert math.isclose(actual, max(cap - general_rate, 0), abs_tol=1e-12)
        cap_cell_proof.append(
            {
                "hts10": hts10,
                "iso2": iso2,
                "origin_tier": origin_tier("forced_labor_section_301", iso2),
                "units": 4,
                "probes": ["2026-07-24", "2026-07-30", "2026-07-31", "2026-08-01"],
                "yale_expected": rate_token(expected),
                "axiom_actual": rate_token(actual),
                "delta_actual_minus_expected": rate_token(actual - expected),
                "rulespec_general_rate": rate_token(general_rate),
                "formula_check": rate_token(max(cap - general_rate, 0)),
                "yale_selected_statutory_base_rate": {
                    revision: sorted(values)
                    for revision, values in sorted(selected_proof[key].items())
                },
                "representative_case_id": representative["case_id"],
            }
        )

    with classification_path.open() as stream:
        classification = json.load(stream)
    post_rebind = classification["post_rebind_target_units"]
    assert post_rebind["fed-false-family-forced-labor"]["residual"] == 139_654
    assert post_rebind["fed-false-family-brazil"]["residual"] == 8_736

    conditional_units = total - accumulators[
        "forced_mfn_cap_rate_input_parser"
    ].units
    receipt = {
        "schema": "axiom_oracles.us_tariff_schedule.preview_1311_old_residual_taxonomy.v1",
        "verdict": "PASS",
        "definition": {
            "selected_rows": "old_target_class is non-null in target-mismatch-cells.jsonl.gz",
            "delta": "actual - expected",
            "unit": "one compared component at one campaign endpoint case",
        },
        "conservation": {
            "old_non_new_residual_units": total,
            "by_slot": dict(sorted(per_slot.items())),
            "by_old_target_class": dict(sorted(per_old_class.items())),
            "category_sum": sum(a.units for a in accumulators.values()),
            "conditional_use_model_proxy_units": conditional_units,
            "mfn_cap_rate_input_parser_units": accumulators[
                "forced_mfn_cap_rate_input_parser"
            ].units,
            "date_issue_units": 0,
            "listed_flag_issue_units": listed_false,
            "cap_formula_issue_units": 0,
            "cafta_52i_overlap_units": cafta_exact.get("true", 0),
            "conditional_membership_overlap_units": conditional_overlap,
            "new_disagreement": dict(sorted(new_disagreement.items())),
            "cafta_52i_exact": dict(sorted(cafta_exact.items())),
            "cafta_52i_country_heuristic": dict(sorted(cafta_heuristic.items())),
            "post_rebind_target_units": post_rebind,
        },
        "categories": {
            key: accumulator.as_json()
            for key, accumulator in sorted(accumulators.items())
        },
        "conditional_source_parity": parity,
        "conditional_wiring_deferred_outputs": deferred_outputs,
        "mfn_cap_parser_proof": {
            "summary": "The four Yale target-vintage General strings retain their numeric rates but append <u></u>; Yale parse_rate accepts only an entire bare N% string and produces a zero panel base downstream. RuleSpec retains the numeric General rates, and every Axiom result equals max(cap - General, 0).",
            "cap_cell_count": len(cap_cells),
            "units": accumulators["forced_mfn_cap_rate_input_parser"].units,
            "cells": cap_cell_proof,
            "raw_hts": raw_hts_rate_proof(yale_root),
            "rulespec_general_rates": {
                hts10: rate_token(rate) for hts10, rate in sorted(ch87_rates.items())
            },
        },
        "provenance": {
            "command_argv": [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
            "script": file_receipt(Path(__file__)),
            "mismatch_cells": file_receipt(mismatch_path),
            "selected_intervals": file_receipt(selected_path),
            "classification_receipt": file_receipt(classification_path),
            "yale": git_receipt(yale_root),
            "rulespec": git_receipt(rulespec_root),
            "yale_sources": {
                label: file_receipt(path) for label, path in sorted(yale_files.items())
            },
            "rulespec_sources": {
                "entry_flag_tool": file_receipt(rulespec_root / "tools/b16_entry_flags.py"),
                "ch87_general_rate": file_receipt(ch87_path),
                "conditional_modules": [file_receipt(path) for path in conditional_paths],
            },
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "output": str(output_path),
        "units": total,
        "categories": expected_category_counts,
        "verdict": "PASS",
    }, sort_keys=True))


if __name__ == "__main__":
    main()
