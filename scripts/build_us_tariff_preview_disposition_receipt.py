#!/usr/bin/env python3
"""Build exact, fail-closed disposition line sets for the PR #1311 preview.

The receipt is campaign-local.  It derives every selector from the pinned
preview mismatch artifacts, replays the source-backed Section 232 precedence
from ``unmapped-cause-audit-receipt.json``, and validates conservation using
the campaign classifier's signature aggregation (not merely row by row).

The current campaign signature intentionally receives special scrutiny:
selectors are evaluated on the first exemplar for each mismatch signature,
exactly as ``classify_campaign`` does.  A signature spanning two intended
classes makes the receipt STOP even if row-level selectors would conserve.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import us_tariff_schedule_campaign as campaign  # noqa: E402


PREVIEW = REPO_ROOT / "reference/us-tariff-schedule/preview-1311"
TARGET_MISMATCH = PREVIEW / "target-mismatch-cells.jsonl.gz"
NEW_MISMATCH = PREVIEW / "new-mismatch-cells.jsonl.gz"
OLD_RECEIPT = PREVIEW / "old-residual-taxonomy-receipt.json"
TAXONOMY_RECEIPT = PREVIEW / "mismatch-taxonomy-receipt.json"
UNMAPPED_RECEIPT = PREVIEW / "unmapped-cause-audit-receipt.json"
DEFAULT_OUTPUT = (
    REPO_ROOT / "reference/us-tariff-schedule/preview-disposition-line-sets.json"
)
DEFAULT_YALE_ROOT = Path("/Users/maxghenis/TheAxiomFoundation/_tariff-yale")
TOLERANCE = 1e-12
IN_SCOPE_ANNEX_TIERS = frozenset(
    {"annex_1a", "annex_1b", "annex_1c", "annex_3", "annex_1b_inferred_derivative"}
)

EXPECTED_HASHES = {
    TARGET_MISMATCH: "d5b53173afe489686aff86a4d1d776bf821cb97945e9ebacd5ba6bc912a8b705",
    NEW_MISMATCH: "7e26a7e746abd4d033b8dcc6b7d95efcece45b1405ac84238011500c84bbe029",
    OLD_RECEIPT: "b4f9d26d5a800cf1b0e6e50c6b3935ee18b24ca55bbcc5eecf9e10ab8f829bea",
    TAXONOMY_RECEIPT: "3d1a7543d738d6e396e111ff909c245f082146aeeeeef27d57a5da38f30e25de",
    UNMAPPED_RECEIPT: "4572f1a121848337bcd0ea797c09e771fc55a3e0efaeb79c195979ddb5a5e29e",
}

EXPECTED_SELECTOR_UNITS = {
    "aircraft-utilization-proxy-brazil": 3_654,
    "aircraft-utilization-proxy-forced-labor": 71_168,
    "pharma-utilization-proxy-brazil": 5_082,
    "pharma-utilization-proxy-forced-labor-non035": 67_430,
    "pharma-utilization-proxy-forced-labor-035": 988,
    "yale-parser-zero-statutory-base": 68,
    "yale-zero-aircraft-brazil": 414,
    "yale-zero-aircraft-forced-labor": 40_392,
    "yale-zero-pharma-brazil": 84,
    "yale-zero-pharma-forced-labor": 1_058,
    "cafta-52i-deferred": 17_404,
    "section232-exposed-brazil": 8_826,
    "section232-exposed-forced-labor": 110_856,
    "section232-annex-brazil": 2_346,
    "section232-annex-forced-labor": 31_488,
    "section232-heading-brazil": 2_334,
    "section232-heading-forced-labor": 30_104,
    "chapter98-brazil": 6,
    "chapter98-forced-labor": 1_508,
    "yale-hts8-broadening-brazil": 120,
}

EXPECTED_LOGICAL_UNITS = {
    "aircraft-utilization-proxy": 74_822,
    "pharma-utilization-proxy": 73_500,
    "yale-parser-zero-statutory-base": 68,
    "yale-zero-aircraft-conditional": 40_806,
    "yale-zero-pharma-conditional": 1_142,
    "cafta-52i-deferred": 17_404,
    "section232-exposed-unconsumed": 119_682,
    "section232-annex-membership": 33_834,
    "section232-heading-program": 32_438,
    "chapter98-handling": 1_514,
    "yale-hts8-broadening": 120,
}
EXPECTED_LOGICAL_RULINGS = {
    "aircraft-utilization-proxy": ("explained_residual", "reference-behavior"),
    "pharma-utilization-proxy": ("explained_residual", "reference-behavior"),
    "yale-parser-zero-statutory-base": ("upstream_engine_gap", "reference-defect"),
    "yale-zero-aircraft-conditional": ("explained_residual", "reference-behavior"),
    "yale-zero-pharma-conditional": ("explained_residual", "reference-behavior"),
    "cafta-52i-deferred": ("axiom_encoding_gap", "axiom-attributed-open"),
    "section232-exposed-unconsumed": ("axiom_encoding_gap", "axiom-attributed-open"),
    "section232-annex-membership": ("axiom_encoding_gap", "axiom-attributed-open"),
    "section232-heading-program": ("axiom_encoding_gap", "axiom-attributed-open"),
    "chapter98-handling": ("explained_residual", "reference-behavior"),
    "yale-hts8-broadening": ("upstream_engine_gap", "reference-defect"),
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def render(value: Any) -> str:
    return json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"


def canonical(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def values_sha256(values: Iterable[str]) -> str:
    material = ("\n".join(sorted(values)) + "\n").encode()
    return hashlib.sha256(material).hexdigest()


def relative(path: Path) -> str:
    return str(path.resolve().relative_to(REPO_ROOT))


def input_receipt(path: Path) -> dict[str, Any]:
    require(path.is_file(), f"missing preview input: {path}")
    actual = sha256(path)
    require(actual == EXPECTED_HASHES[path], f"preview input hash drift: {path}: {actual}")
    return {"path": relative(path), "bytes": path.stat().st_size, "sha256": actual}


def normalize_code(value: str) -> str:
    return str(value).strip().replace(".", "")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as source:
        return list(csv.DictReader(source))


def csv_prefixes(path: Path, column: str | None = None) -> set[str]:
    rows = read_csv(path)
    require(bool(rows), f"empty Yale source: {path}")
    column = column or next(iter(rows[0]))
    return {normalize_code(row[column]) for row in rows if row.get(column)}


def text_prefixes(path: Path) -> set[str]:
    with path.open() as source:
        return {
            normalize_code(line)
            for line in source
            if line.strip() and not line.lstrip().startswith("#")
        }


def prefix_hit(code: str, prefixes: Iterable[str]) -> bool:
    return any(code.startswith(prefix) for prefix in prefixes)


def git_value(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()


def verify_yale_sources(
    yale_root: Path, audit: dict[str, Any]
) -> tuple[dict[str, set[str]], Any, dict[str, Any]]:
    expected_repo = audit["sources"]["yale_repo"]
    commit = git_value(yale_root, "rev-parse", "HEAD")
    tree = git_value(yale_root, "rev-parse", "HEAD^{tree}")
    require(commit == expected_repo["commit"], f"Yale commit drift: {commit}")
    require(tree == expected_repo["tree"], f"Yale tree drift: {tree}")

    expected_root = Path(expected_repo["root"])
    verified_files: dict[str, dict[str, Any]] = {}
    for source_path, receipt in audit["sources"]["files"].items():
        old_path = Path(source_path)
        try:
            source_relative = old_path.relative_to(expected_root)
        except ValueError:
            continue
        actual_path = yale_root / source_relative
        require(actual_path.is_file(), f"missing pinned Yale source: {actual_path}")
        actual_hash = sha256(actual_path)
        require(actual_hash == receipt["sha256"], f"Yale source hash drift: {source_relative}")
        verified_files[str(source_relative)] = {
            "bytes": actual_path.stat().st_size,
            "sha256": actual_hash,
        }

    policy_path = yale_root / "config/policy_params.yaml"
    policy = yaml.safe_load(policy_path.read_text())
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
    heading_families: dict[str, set[str]] = defaultdict(set)
    for program, family in aliases.items():
        config = policy["section_232_headings"][program]
        if config.get("prefixes"):
            heading_families[family].update(normalize_code(item) for item in config["prefixes"])
        elif config.get("products_file"):
            heading_families[family].update(csv_prefixes(yale_root / config["products_file"]))
        elif config.get("prefixes_file"):
            heading_families[family].update(text_prefixes(yale_root / config["prefixes_file"]))
        else:
            raise ValueError(f"unsupported Section 232 heading program: {program}")

    annex_rows = read_csv(yale_root / "resources/s232_annex_products.csv")
    derivative_rows = read_csv(yale_root / "resources/s232_derivative_products.csv")

    @lru_cache(maxsize=None)
    def annex_tier(code: str, probe: str) -> str | None:
        latest: dict[str, tuple[str, str]] = {}
        for row in annex_rows:
            effective = row.get("effective_date") or "1900-01-01"
            if effective > probe:
                continue
            prefix = normalize_code(row["hts_prefix"])
            previous = latest.get(prefix)
            if previous is None or effective > previous[0]:
                latest[prefix] = (effective, "annex_" + row["annex"])
        annex = sorted(
            ((prefix, value[1]) for prefix, value in latest.items()),
            key=lambda item: (-len(item[0]), item[0]),
        )
        for prefix, tier in annex:
            if code.startswith(prefix):
                return tier
        derivative = sorted(
            {
                normalize_code(row["hts_prefix"])
                for row in derivative_rows
                if (row.get("effective_date") or "1900-01-01") <= probe
            },
            key=lambda item: (-len(item), item),
        )
        return "annex_1b_inferred_derivative" if prefix_hit(code, derivative) else None

    source_receipt = {
        "commit": commit,
        "tree": tree,
        "files": dict(sorted(verified_files.items())),
    }
    return dict(heading_families), annex_tier, source_receipt


def record_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return row["case_id"], row["probe"], row["slot"]


def near(left: float, right: float) -> bool:
    return abs(left - right) <= TOLERANCE


def legacy_signature(row: dict[str, Any]) -> str:
    """Pre-ruling signature that lost the selector's HTS10 and ISO2 axes."""
    context = row["context"]
    payload = {
        "authority_slot": row["slot"],
        "delta": row["delta"],
        "flag_vector": context["flags"],
        "revision_interval_regime": [context["revision"], *context["interval"]],
        "origin_regime": context["origin_regime"],
        "line_incidence_signature": [
            context["hts_line"],
            sorted(name for name, value in context["flags"].items() if value),
        ],
    }
    return hashlib.sha256(render(payload).encode()).hexdigest()


def selector_match(
    row: dict[str, Any], selector: dict[str, Any], line_sets: dict[str, set[str]]
) -> bool:
    match = selector["match"]
    if row["slot"] != match["slot"]:
        return False
    if row["context"]["hts10"] not in line_sets[match["line_set"]]:
        return False
    delta = float(row["delta"])
    delta_match = match["delta"]
    if delta_match.get("sign") == "pos" and delta <= 0:
        return False
    if delta_match.get("sign") == "neg" and delta >= 0:
        return False
    if "values" in delta_match and not any(near(delta, float(value)) for value in delta_match["values"]):
        return False
    return True


def signature_audit(
    labels: dict[str, Counter[str]], units: Counter[str]
) -> dict[str, Any]:
    mixed = {signature: counts for signature, counts in labels.items() if len(counts) > 1}
    compositions = Counter(
        " + ".join(f"{name}:{count}" for name, count in sorted(counts.items()))
        for counts in mixed.values()
    )
    return {
        "signature_count": len(labels),
        "mixed_signature_count": len(mixed),
        "mixed_units": sum(units[signature] for signature in mixed),
        "mixed_compositions": dict(sorted(compositions.items())),
        "sample_mixed_signatures": [
            {"signature": signature, "classes": dict(sorted(mixed[signature].items()))}
            for signature in sorted(mixed)[:10]
        ],
        "pure": not mixed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--yale-root", type=Path, default=DEFAULT_YALE_ROOT)
    parser.add_argument("--check", action="store_true", help="compare generated bytes; do not write")
    parser.add_argument(
        "--allow-current-signature-gap", action="store_true",
        help="bootstrap only: emit a STOP receipt with the proposed HTS10-inclusive proof",
    )
    args = parser.parse_args()

    inputs = {relative(path): input_receipt(path) for path in EXPECTED_HASHES}
    old_receipt = json.loads(OLD_RECEIPT.read_text())
    taxonomy_receipt = json.loads(TAXONOMY_RECEIPT.read_text())
    unmapped_receipt = json.loads(UNMAPPED_RECEIPT.read_text())
    for name, receipt in (
        ("old residual", old_receipt),
        ("mismatch taxonomy", taxonomy_receipt),
        ("unmapped audit", unmapped_receipt),
    ):
        require(receipt.get("verdict") == "PASS", f"{name} receipt is not PASS")
    require(
        taxonomy_receipt["inputs"]["mismatch_cells"]["sha256"] == EXPECTED_HASHES[TARGET_MISMATCH],
        "taxonomy receipt is not bound to target mismatch artifact",
    )
    require(
        taxonomy_receipt["outputs"]["new_mismatch_cells"]["sha256"] == EXPECTED_HASHES[NEW_MISMATCH],
        "taxonomy receipt is not bound to new mismatch artifact",
    )
    require(
        unmapped_receipt["inputs"]["new_mismatch_cells"]["sha256"] == EXPECTED_HASHES[NEW_MISMATCH],
        "unmapped receipt is not bound to new mismatch artifact",
    )

    heading_families, annex_tier, yale_source_receipt = verify_yale_sources(
        args.yale_root.resolve(), unmapped_receipt
    )
    parser_pairs = {
        (cell["hts10"], cell["iso2"])
        for cell in old_receipt["mfn_cap_parser_proof"]["cells"]
    }

    populations: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"units": 0, "hts10": set(), "deltas": set(), "origins": set()}
    )
    logical_for_selector: dict[str, str] = {}
    new_labels: dict[tuple[str, str, str], str] = {}
    broadening_lines: Counter[tuple[str, str, str, str]] = Counter()
    cafta_origins: Counter[str] = Counter()

    def add(selector_id: str, logical_class: str, row: dict[str, Any]) -> None:
        population = populations[selector_id]
        population["units"] += 1
        population["hts10"].add(row["context"]["hts10"])
        population["deltas"].add(float(row["delta"]))
        population["origins"].add(row["context"]["iso2"])
        previous = logical_for_selector.setdefault(selector_id, logical_class)
        require(previous == logical_class, f"selector logical-class drift: {selector_id}")

    with gzip.open(NEW_MISMATCH, "rt") as source:
        for line in source:
            row = json.loads(line)
            taxonomy = row["taxonomy_primary"]
            context = row["context"]
            code = context["hts10"]
            slot_suffix = "brazil" if row["slot"] == "brazil_section_301" else "forced-labor"
            if taxonomy in {"brazil-aircraft", "forced-aircraft"}:
                logical = "yale-zero-aircraft-conditional"
                selector_id = f"yale-zero-aircraft-{slot_suffix}"
            elif taxonomy in {"brazil-pharma", "forced-pharma"}:
                logical = "yale-zero-pharma-conditional"
                selector_id = f"yale-zero-pharma-{slot_suffix}"
            elif taxonomy == "cafta-52i":
                logical = selector_id = "cafta-52i-deferred"
                cafta_origins[context["iso2"]] += 1
            elif taxonomy == "unmapped":
                broadening = row.get("yale_full_list_statistical_broadening")
                if broadening:
                    logical = "yale-hts8-broadening"
                    selector_id = "yale-hts8-broadening-brazil"
                    broadening_lines[(
                        broadening["yale_hts8"], broadening["legal_hts10"],
                        code, context["hts_line"],
                    )] += 1
                elif code.startswith("98"):
                    logical = "chapter98-handling"
                    selector_id = f"chapter98-{slot_suffix}"
                elif context["flags"].get("entry_is_section_232_covered"):
                    logical = "section232-exposed-unconsumed"
                    selector_id = f"section232-exposed-{slot_suffix}"
                else:
                    tier = annex_tier(code, context["interval"][0])
                    heading_hit = any(prefix_hit(code, prefixes) for prefixes in heading_families.values())
                    if tier in IN_SCOPE_ANNEX_TIERS:
                        logical = "section232-annex-membership"
                        selector_id = f"section232-annex-{slot_suffix}"
                    elif heading_hit:
                        logical = "section232-heading-program"
                        selector_id = f"section232-heading-{slot_suffix}"
                    else:
                        raise ValueError(f"unclassified preview unmapped row: {record_key(row)}")
            else:
                raise ValueError(f"unexpected preview taxonomy: {taxonomy!r}")
            require(record_key(row) not in new_labels, f"duplicate new mismatch key: {record_key(row)}")
            new_labels[record_key(row)] = selector_id
            add(selector_id, logical, row)

    require(len(new_labels) == 246_940, f"new mismatch row drift: {len(new_labels)}")

    parser_line_units: Counter[str] = Counter()

    def old_selector(row: dict[str, Any]) -> tuple[str, str]:
        context = row["context"]
        slot_suffix = "brazil" if row["slot"] == "brazil_section_301" else "forced-labor"
        actual, expected, delta = map(float, (row["actual"], row["expected"], row["delta"]))
        if (context["hts10"], context["iso2"]) in parser_pairs:
            require(row["slot"] == "forced_labor_section_301" and delta < 0, "parser-cell shape drift")
            parser_line_units[context["hts10"]] += 1
            return "yale-parser-zero-statutory-base", "yale-parser-zero-statutory-base"
        if near(expected, 0.10 * actual):
            return f"aircraft-utilization-proxy-{slot_suffix}", "aircraft-utilization-proxy"
        if near(expected, 0.50 * actual):
            if row["slot"] == "forced_labor_section_301":
                suffix = "035" if near(delta, 0.035) else "non035"
                return f"pharma-utilization-proxy-forced-labor-{suffix}", "pharma-utilization-proxy"
            return "pharma-utilization-proxy-brazil", "pharma-utilization-proxy"
        raise ValueError(f"unclassified old residual: {record_key(row)}")

    old_units = 0
    target_rows = 0
    current_labels: dict[str, Counter[str]] = defaultdict(Counter)
    current_units: Counter[str] = Counter()
    current_examples: dict[str, dict[str, Any]] = {}
    legacy_labels: dict[str, Counter[str]] = defaultdict(Counter)
    legacy_units: Counter[str] = Counter()
    legacy_examples: dict[str, dict[str, Any]] = {}
    intended_counts: Counter[str] = Counter()

    with gzip.open(TARGET_MISMATCH, "rt") as source:
        for line in source:
            row = json.loads(line)
            target_rows += 1
            if row.get("old_target_class"):
                selector_id, logical = old_selector(row)
                add(selector_id, logical, row)
                old_units += 1
            else:
                selector_id = new_labels.get(record_key(row), "")
                require(bool(selector_id), f"new target row absent from taxonomy sidecar: {record_key(row)}")
            intended_counts[selector_id] += 1
            signature_row = {"slot": row["slot"], "delta": row["delta"], "context": row["context"]}
            current = campaign.mismatch_signature(signature_row)
            legacy = legacy_signature(signature_row)
            current_labels[current][selector_id] += 1
            current_units[current] += 1
            current_examples.setdefault(current, row)
            legacy_labels[legacy][selector_id] += 1
            legacy_units[legacy] += 1
            legacy_examples.setdefault(legacy, row)

    require(target_rows == 395_330, f"target mismatch row drift: {target_rows}")
    require(old_units == 148_390, f"old residual row drift: {old_units}")
    require(old_units + len(new_labels) == target_rows, "old/new target conservation failure")
    require(dict(sorted(intended_counts.items())) == EXPECTED_SELECTOR_UNITS, "selector census drift")

    line_sets: dict[str, set[str]] = {}
    selectors: list[dict[str, Any]] = []
    for selector_id in sorted(populations):
        population = populations[selector_id]
        logical_class = logical_for_selector[selector_id]
        disposition, attribution = EXPECTED_LOGICAL_RULINGS[logical_class]
        line_set_name = "preview-1311-" + selector_id + "-hts10"
        line_sets[line_set_name] = set(population["hts10"])
        if selector_id == "yale-parser-zero-statutory-base":
            delta_match: dict[str, Any] = {"sign": "neg"}
        elif selector_id.startswith("pharma-utilization-proxy-") or selector_id.startswith("yale-zero-pharma-"):
            delta_match = {"values": sorted(population["deltas"])}
        else:
            delta_match = {"sign": "pos"}
        slot = (
            "brazil_section_301"
            if selector_id.endswith("-brazil")
            else "forced_labor_section_301"
        )
        selectors.append({
            "id": selector_id,
            "logical_class": logical_class,
            "disposition": disposition,
            "attribution": attribution,
            "expected_units": population["units"],
            "match": {"slot": slot, "line_set": line_set_name, "delta": delta_match},
        })

    require(len(selectors) == 20, f"selector count drift: {len(selectors)}")

    row_census: Counter[str] = Counter()
    row_overlaps = 0
    row_unexplained = 0
    with gzip.open(TARGET_MISMATCH, "rt") as source:
        for line in source:
            row = json.loads(line)
            matches = [item["id"] for item in selectors if selector_match(row, item, line_sets)]
            row_overlaps += len(matches) > 1
            row_unexplained += not matches
            if len(matches) == 1:
                row_census[matches[0]] += 1
    require(row_overlaps == 0 and row_unexplained == 0, "row-level selector conservation failure")
    require(dict(sorted(row_census.items())) == EXPECTED_SELECTOR_UNITS, "row-level selector census drift")

    def classify_signatures(
        examples: dict[str, dict[str, Any]], multiplicities: Counter[str]
    ) -> tuple[Counter[str], int, int, dict[str, list[tuple[str, int]]]]:
        census: Counter[str] = Counter()
        populations: dict[str, list[tuple[str, int]]] = defaultdict(list)
        overlaps = unexplained = 0
        for signature, row in examples.items():
            matches = [item["id"] for item in selectors if selector_match(row, item, line_sets)]
            if len(matches) > 1:
                overlaps += multiplicities[signature]
            elif not matches:
                unexplained += multiplicities[signature]
            else:
                census[matches[0]] += multiplicities[signature]
                populations[matches[0]].append((signature, multiplicities[signature]))
        return census, overlaps, unexplained, dict(populations)

    current_census, current_overlaps, current_unexplained, current_populations = classify_signatures(
        current_examples, current_units
    )
    legacy_census, legacy_overlaps, legacy_unexplained, _ = classify_signatures(
        legacy_examples, legacy_units
    )
    current_audit = signature_audit(current_labels, current_units)
    legacy_audit = signature_audit(legacy_labels, legacy_units)
    require(current_audit["pure"], "current campaign signature is not class-pure")
    require(current_overlaps == 0 and current_unexplained == 0, "current signature selector failure")
    require(dict(sorted(current_census.items())) == EXPECTED_SELECTOR_UNITS,
            "current signature census drift")
    for selector in selectors:
        population = current_populations.get(selector["id"], [])
        selector["expected_signature_count"] = len(population)
        selector["expected_signature_population_sha256"] = (
            campaign.signature_population_sha256(population)
        )
    require(legacy_audit["mixed_signature_count"] == 33, "legacy mixed-signature census drift")
    require(legacy_audit["mixed_units"] == 168, "legacy mixed-unit census drift")

    logical_census = Counter()
    for selector in selectors:
        logical_census[selector["logical_class"]] += selector["expected_units"]
    require(dict(sorted(logical_census.items())) == EXPECTED_LOGICAL_UNITS, "logical census drift")
    require(set(logical_census) == set(EXPECTED_LOGICAL_RULINGS), "logical ruling coverage drift")
    require(sum(logical_census.values()) == 395_330, "logical conservation failure")

    verdict = "PASS"
    payload: dict[str, Any] = {
        "schema": "axiom_oracles.us_tariff_schedule.preview_disposition_line_sets.v1",
        "verdict": verdict,
        "inputs": dict(sorted(inputs.items())),
        "yale_sources": yale_source_receipt,
        "definition": {
            "unit": "one mismatching target component at one campaign endpoint",
            "line_set_value_hash": "SHA-256 of sorted HTS10 values, one per line, with a final newline",
            "selector_contract": "exact slot + named exact HTS10 line_set + delta bound",
            "selector_population_hash": (
                "SHA-256 of the canonical sorted JSON [mismatch_signature, multiplicity] population"
            ),
            "taxonomy_precedence": unmapped_receipt["definitions"]["exclusive_top_precedence"],
        },
        "line_sets": {
            name: {
                "width": 10,
                "value_count": len(values),
                "values_sha256": values_sha256(values),
                "values": sorted(values),
            }
            for name, values in sorted(line_sets.items())
        },
        "selectors": selectors,
        "census": {
            "per_selector": dict(sorted(intended_counts.items())),
            "per_logical_class": dict(sorted(logical_census.items())),
            "per_slot": {
                "brazil_section_301": sum(
                    selector["expected_units"] for selector in selectors
                    if selector["match"]["slot"] == "brazil_section_301"
                ),
                "forced_labor_section_301": sum(
                    selector["expected_units"] for selector in selectors
                    if selector["match"]["slot"] == "forced_labor_section_301"
                ),
            },
            "old_residual": old_units,
            "new_disagreements": len(new_labels),
            "total": target_rows,
        },
        "classifier_signature_audit": {
            "current_campaign_signature": current_audit | {
                "selector_census": dict(sorted(current_census.items())),
                "overlap_units": current_overlaps,
                "unexplained_units": current_unexplained,
            },
            "legacy_pre_ruling_signature": legacy_audit | {
                "selector_census": dict(sorted(legacy_census.items())),
                "overlap_units": legacy_overlaps,
                "unexplained_units": legacy_unexplained,
            },
            "implemented_campaign_change": (
                "mismatch_signature now binds context.hts10 and context.iso2; the legacy signature merged "
                "annex and heading rows and classified by an arbitrary first exemplar."
            ),
        },
        "evidence_census": {
            "parser_units_by_hts10": dict(sorted(parser_line_units.items())),
            "broadening_lines": [
                {
                    "yale_hts8": key[0], "legal_hts10": key[1],
                    "mismatch_hts10": key[2], "hts_line": key[3], "units": units,
                }
                for key, units in sorted(broadening_lines.items())
            ],
            "cafta_units_by_origin": dict(sorted(cafta_origins.items())),
        },
        "conservation": {
            "identity": "148390 old + 246940 new = 395330",
            "row_selector_overlaps": row_overlaps,
            "row_selector_unexplained": row_unexplained,
            "current_signature_selector_overlaps": current_overlaps,
            "current_signature_selector_unexplained": current_unexplained,
            "result": "PASS",
        },
        "integration_constraints": [
            "Register each generated line set campaign-locally before using the selector matches.",
            "Each logical cross-slot class requires separate entries because slot must be exact.",
            "The existing fed-false-family-forced-labor selector overlaps the 68 parser rows and must be replaced or refined.",
            "Do not merge the 17,404 CAFTA units into a conformant/reference class; they remain axiom-attributed-open until encoded.",
        ],
    }
    payload["receipt_payload_sha256"] = hashlib.sha256(canonical(payload)).hexdigest()
    output = render(payload)

    if args.check:
        require(args.output.is_file(), f"generated receipt missing: {args.output}")
        require(args.output.read_text() == output, f"generated receipt drift: {args.output}")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=args.output.parent, delete=False) as target:
            target.write(output)
            temporary = Path(target.name)
        temporary.replace(args.output)

    summary = {
        "verdict": verdict,
        "output": str(args.output.resolve()),
        "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
        "line_sets": len(line_sets),
        "selectors": len(selectors),
        "units": target_rows,
        "legacy_mixed_signatures": legacy_audit["mixed_signature_count"],
        "legacy_mixed_units": legacy_audit["mixed_units"],
    }
    print(render(summary), end="")
    return 0 if verdict == "PASS" or args.allow_current_signature_gap else 2


if __name__ == "__main__":
    raise SystemExit(main())
