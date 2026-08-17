#!/usr/bin/env python3
"""Fail-closed stages for the Yale full-schedule tariff campaign.

The disposition pre-pass is deliberately independent of the engine.  It maps
each Yale statistical member to the generated statutory rate line, receipts
the General and column-2 disposition texts, and fixes the query surface before
shards are planned.  A non-ad-valorem base suppresses only the base and total
queries; authority-component queries remain in the plan.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SELECTED = REPO_ROOT / "reference/us-tariff-schedule/selected-intervals.csv.gz"
OUT_DIR = REPO_ROOT / "reference/us-tariff-schedule"
ROUTING_ROWS = OUT_DIR / "disposition-routing.csv.gz"
ROUTING_RECEIPT = OUT_DIR / "disposition-routing-receipt.json"
SCHEMA = "axiom_oracles.us_tariff_schedule.disposition_routing.v1"
DISPOSITIONS = {
    "ad_valorem", "free", "specific", "compound", "component",
    "conditional", "empty",
}
COMPARABLE = {"ad_valorem", "free"}
COLUMN2_ORIGINS = {"CU", "KP", "BY", "RU"}
# The pinned table generator's explicit structural census: a statistical row
# with no rated ancestor.  It is not silently inferred from a failed lookup.
EXPECTED_UNOWNED = {"9802009100"}
COMPONENT_SLOTS = (
    "ieepa", "section_201", "section_122", "section_232_aluminum",
    "section_232_steel", "section_338", "china_section_301",
    "brazil_section_301", "forced_labor_section_301",
)
BASE_DEPENDENT_COMPONENTS = ("ieepa", "forced_labor_section_301")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _render(value: Any) -> str:
    return json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _chapter_table_paths(rulespec_root: Path) -> list[Path]:
    directory = rulespec_root / "us/policies/usitc/us-tariff-duty/lines/generated"
    paths = sorted(
        path for path in directory.glob("ch*.yaml")
        if not path.name.endswith(".test.yaml")
    )
    _require(len(paths) == 100, f"expected 100 generated chapter tables, found {len(paths)}")
    return paths


def _rule_values(payload: dict, name: str) -> dict[int, str]:
    rules = [rule for rule in payload.get("rules", []) if rule.get("name") == name]
    _require(len(rules) == 1, f"expected exactly one {name} rule")
    versions = rules[0].get("versions", [])
    _require(len(versions) == 1 and isinstance(versions[0].get("values"), dict), f"bad {name} values")
    values = {int(key): str(value) for key, value in versions[0]["values"].items()}
    _require(values and set(values.values()) <= DISPOSITIONS, f"invalid {name} disposition")
    return values


def load_tables(rulespec_root: Path) -> tuple[dict[str, dict[int, tuple[str, str]]], list[dict[str, Any]]]:
    tables: dict[str, dict[int, tuple[str, str]]] = {}
    sources = []
    for path in _chapter_table_paths(rulespec_root):
        shard = path.stem.removeprefix("ch")
        payload = yaml.safe_load(path.read_text())
        general = _rule_values(payload, f"ch{shard}_general_disposition")
        column2 = _rule_values(payload, f"ch{shard}_column2_disposition")
        _require(set(general) == set(column2), f"ch{shard} disposition keysets differ")
        tables[shard] = {key: (general[key], column2[key]) for key in general}
        sources.append({"path": str(path.relative_to(rulespec_root)), "sha256": _sha256(path)})
    return tables, sources


def verify_component_formulas(rulespec_root: Path) -> dict[str, Any]:
    """Prove generated authority components do not query base or total."""
    directory = rulespec_root / "us/policies/cbp/us-tariff-schedule/generated"
    paths = sorted(
        path for path in directory.glob("ch*/ch*.yaml")
        if not path.name.endswith(".test.yaml")
    )
    _require(len(paths) == 100, f"expected 100 generated compositions, found {len(paths)}")
    digest = hashlib.sha256()
    checked = 0
    forbidden = ("mfn_ad_valorem_rate", "schedule_base_general_rate", "schedule_statutory_stack")
    dependent: set[str] = set()
    for path in paths:
        raw = path.read_bytes()
        digest.update(hashlib.sha256(raw).digest())
        payload = yaml.safe_load(raw)
        by_name = {rule.get("name"): rule for rule in payload.get("rules", [])}
        for name in COMPONENT_SLOTS:
            rule_name = f"{name}_component_rate"
            rule = by_name.get(rule_name)
            _require(rule is not None, f"{path}: missing {rule_name}")
            formulas = "\n".join(
                str(version.get("formula", "")) for version in rule.get("versions", [])
            )
            if any(token in formulas for token in forbidden):
                dependent.add(name)
            checked += 1
    _require(dependent == set(BASE_DEPENDENT_COMPONENTS),
             f"component/base dependency inventory changed: {sorted(dependent)}")
    return {
        "generated_compositions": len(paths),
        "component_formulas_checked": checked,
        "composition_hash_aggregate": digest.hexdigest(),
        "base_or_total_required_by_component": sorted(dependent),
    }


def route_member(hts10: str, tables: dict[str, dict[int, tuple[str, str]]]) -> tuple[str, int, str, str]:
    _require(re.fullmatch(r"\d{10}", hts10) is not None, f"invalid HTS-10 {hts10!r}")
    if hts10 in EXPECTED_UNOWNED:
        return "98", int(hts10), "empty", "empty"
    shards = [hts10[:2]] if hts10[:2] != "99" else ["99a", "99b", "99c"]
    # HTS document order is numeric within a chapter.  An unrated statistical
    # member belongs to the most recent rated ancestor in that order (the same
    # indent-stack rule used by the pinned generator); exact rated members are
    # naturally their own owner.  Prefix matching is incorrect for structural
    # children such as 9817.22.05.00 under 9817.00.98.00.
    member_number = int(hts10)
    candidates = []
    for shard in shards:
        for key, dispositions in tables.get(shard, {}).items():
            if key <= member_number:
                candidates.append((key, shard, *dispositions))
    _require(candidates, f"no generated disposition route for {hts10}")
    best_key = max(row[0] for row in candidates)
    best = [row for row in candidates if row[0] == best_key]
    _require(len(best) == 1, f"ambiguous generated disposition route for {hts10}: {best}")
    key, shard, general, column2 = best[0]
    return shard, key, general, column2


def query_plan(disposition: str, *, column2_rate_available: bool = True) -> dict[str, Any]:
    _require(disposition in DISPOSITIONS, f"unknown disposition {disposition!r}")
    comparable = disposition in COMPARABLE and column2_rate_available
    reason = None if comparable else (
        f"non_ad_valorem_base:{disposition}"
        if disposition not in COMPARABLE else "structurally_unavailable:column2_rate"
    )
    compared_components = list(COMPONENT_SLOTS if comparable else (
        slot for slot in COMPONENT_SLOTS if slot not in BASE_DEPENDENT_COMPONENTS
    ))
    excluded_components = [] if comparable else list(BASE_DEPENDENT_COMPONENTS)
    return {
        "base": "compare" if comparable else "known_not_comparable",
        "total": "compare" if comparable else "known_not_comparable",
        "reason": reason,
        "components": compared_components,
        "excluded_components": excluded_components,
        "component_exclusion_reason": None if comparable else "requires_noncomparable_base",
    }


def _selected_rows(path: Path) -> Iterable[dict[str, str]]:
    with gzip.open(path, "rt", newline="") as source:
        yield from csv.DictReader(source)


def build_prepass(*, rulespec_root: Path, selected_path: Path = SELECTED) -> tuple[list[dict[str, str]], dict[str, Any]]:
    tables, sources = load_tables(rulespec_root)
    formula_receipt = verify_component_formulas(rulespec_root)
    unique_members: set[str] = set()
    for row in _selected_rows(selected_path):
        unique_members.add(row["hts10"])
    routes = {}
    output_rows = []
    for member in sorted(unique_members):
        shard, line, general, column2 = route_member(member, tables)
        routes[member] = (shard, line, general, column2)
        output_rows.append({
            "hts10": member, "chapter_shard": shard, "hts_line": f"{line:010d}",
            "general_disposition": general, "column2_disposition": column2,
        })

    cell_counts: Counter[str] = Counter()
    disposition_counts: Counter[str] = Counter()
    total = 0
    for row in _selected_rows(selected_path):
        total += 1
        shard, _line, general, column2 = routes[row["hts10"]]
        is_column2 = row["iso2"] in COLUMN2_ORIGINS
        disposition = column2 if is_column2 else general
        column2_available = not (is_column2 and shard in {"99a", "99b"})
        plan = query_plan(disposition, column2_rate_available=column2_available)
        disposition_counts[disposition] += 1
        cell_counts["full_comparison" if plan["base"] == "compare" else "components_only"] += 1
        if not column2_available and disposition in COMPARABLE:
            cell_counts["structurally_unavailable_column2"] += 1

    excluded = cell_counts["components_only"]
    receipt = {
        "schema": SCHEMA,
        "selected_source": {"path": str(selected_path.relative_to(REPO_ROOT)), "sha256": _sha256(selected_path)},
        "rulespec_tables": sources,
        "routing_rows": len(output_rows),
        "evaluated_cells": total,
        "full_comparison_cells": cell_counts["full_comparison"],
        "non_ad_valorem_components_only_cells": excluded,
        "non_ad_valorem_share": excluded / total,
        "structurally_unavailable_column2_cells": cell_counts["structurally_unavailable_column2"],
        "base_dependent_component_excluded_slots": excluded * len(BASE_DEPENDENT_COMPONENTS),
        "selected_disposition_counts": dict(sorted(disposition_counts.items())),
        "scope_statement": (
            f"{excluded} of {total} evaluated cells carry a non-ad-valorem statutory base "
            "and are compared on authority components only"
        ),
        "component_formula_contract": {
            "queried_for_every_cell": [
                slot for slot in COMPONENT_SLOTS if slot not in BASE_DEPENDENT_COMPONENTS
            ],
            "queried_only_with_comparable_base": list(BASE_DEPENDENT_COMPONENTS),
            **formula_receipt,
        },
    }
    _require(total > 0 and sum(cell_counts[k] for k in ("full_comparison", "components_only")) == total,
             "disposition routing does not conserve selected cells")
    return output_rows, receipt


def write_prepass(rows: list[dict[str, str]], receipt: dict[str, Any]) -> None:
    # gzip mtime=0 makes the content-addressed routing artifact reproducible.
    with ROUTING_ROWS.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as compressed:
            with io.TextIOWrapper(compressed, newline="") as target:
                writer = csv.DictWriter(target, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
    receipt["routing_artifact"] = {"path": str(ROUTING_ROWS.relative_to(REPO_ROOT)), "sha256": _sha256(ROUTING_ROWS)}
    ROUTING_RECEIPT.write_text(_render(receipt))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("prepass", choices=("prepass",))
    parser.add_argument("--rulespec-root", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    rows, receipt = build_prepass(rulespec_root=args.rulespec_root.resolve())
    receipt["stage_wall_clock_seconds"] = round(time.perf_counter() - started, 3)
    write_prepass(rows, receipt)
    print(_render(receipt), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
