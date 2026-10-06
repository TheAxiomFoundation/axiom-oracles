#!/usr/bin/env python3
"""Audit and classify new note-50/52 preview mismatches.

This lane-local postprocessor is deliberately pinned to rulespec-us #1311 and
the Yale source checkout used by the tariff campaign.  It reads only the
already-produced mismatch sidecar; it never evaluates the panel or mutates a
rulespec checkout.
"""

from __future__ import annotations

import ast
import csv
import gzip
import hashlib
import importlib.util
import json
import math
import re
import subprocess
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable


LANE_DIR = Path(__file__).resolve().parent
REPO_ROOT = LANE_DIR.parents[2]
RULESPEC_ROOT = Path(
    "/Users/maxghenis/PolicyEngine/_tariff-p5/b1/c6-roots/rulespec-us"
)
YALE_ROOT = Path("/Users/maxghenis/TheAxiomFoundation/_tariff-yale")

INPUT = LANE_DIR / "target-mismatch-cells.jsonl.gz"
TARGET_RECEIPT = LANE_DIR / "target-comparison-classification-receipt.json"
OUTPUT = LANE_DIR / "new-mismatch-cells.jsonl.gz"
RECEIPT = LANE_DIR / "mismatch-taxonomy-receipt.json"
CAMPAIGN_SOURCE = REPO_ROOT / "scripts/us_tariff_schedule_campaign.py"
PREVIEW_DRIVER = LANE_DIR / "preview_driver.py"

EXPECTED_RULESPEC_COMMIT = "3357f7dc710d18861b1fefdff115e2434e67b988"
EXPECTED_RULESPEC_TREE = "c3d530c72344310aa2fdfcebe5aec286b1ad4869"
EXPECTED_NOTE_TREES = {
    "note50": "f313eb5be207bb8d561ecb3d6e39ed083fc420c0",
    "note52": "edfc26f36d4c83a57a6006f1cd3b1058184bba8a",
}
EXPECTED_YALE_COMMIT = "c4307e514196618afcbf88cf7fd33746417eeabf"
EXPECTED_NOTES_SOURCE_RELPATH = (
    "data/corpus/provisions/us/statute/"
    "2026-08-04-usitc-hts-2026-rev15-notes.jsonl"
)
EXPECTED_NOTES_SOURCE_SHA256 = (
    "0f3ed7ef2efb64383825db65e615959200770e8511c8d4834b16e02892cb9ec8"
)

RULESPEC_FILE_SHA256 = {
    "tools/b16_entry_flags.py":
        "8032dde5fe4a9bc14448cc84e338181a69b912e37b74331d89e9d5f9ef746c8a",
    "tools/generate_incidence_tables.py":
        "ffb99f2901c6fc0bf96c30c81e972b6d507e5fd5c0e8d89c34a91dd67c41dd84",
    "tools/b16_oracle_reconcile.py":
        "1b81b5e7fc00772ae34c47ef5785262c52acd6a90e539bab0e9e6f834997af4e",
}
YALE_FILE_SHA256 = {
    "resources/s301_brazil_exempt_products.csv":
        "077e763ba3e2a8cfd8bf56a52dc2f04f5bafdf8eef53dd771ca9099386623898",
    "resources/s301_brazil_aircraft_products.csv":
        "5268dc619bca936b7f87625c96369516d7074066960d38d4319e72a1acca84cd",
    "resources/s301_brazil_pharma_products.csv":
        "322c0f562649cce35674df0d7c34ee7d5d4ada381784ba3873ec564100bcdab7",
    "resources/s301fl_final_common_exemptions.csv":
        "15b5e352cd810af33b90699bb595010f5aca43ea10de25ba1b2c6239acc96054",
    "resources/s301fl_final_country_exemptions.csv":
        "a38f8e42e9615b58dc09fd8a661b4a0fdb9d12e2121342a657fae69450215280",
}

TARGET_SLOTS = frozenset({
    "forced_labor_section_301",
    "brazil_section_301",
})
FLAG_FOR_SLOT = {
    "forced_labor_section_301": "entry_is_forced_labor_301_listed",
    "brazil_section_301": "entry_is_brazil_301_listed",
}
EFFECTIVE_FROM = {
    "forced_labor_section_301": "2026-07-24",
    "brazil_section_301": "2026-07-22",
}
PRIMARY_ORDER = (
    "encoded-full-exemption",
    "cafta-52i",
    "brazil-aircraft",
    "brazil-pharma",
    "forced-aircraft",
    "forced-pharma",
    "unmapped",
)
CONDITIONAL_LABELS = frozenset(PRIMARY_ORDER[1:-1])

BR_FULL_PREFIXES = (
    "brazil_301_unconditional_exemption_",
    "brazil_301_particular_exemption_",
)
FL_COMMON_FULL_PREFIXES = (
    "forced_labor_301_common_exemption_",
    "forced_labor_301_particular_exemption_",
)
CAFTA_ORIGINS = frozenset({"CR", "DO", "SV", "GT", "HN", "NI"})
FORCED_ORIGINS = frozenset({
    "AE", "AO", "AR", "AT", "AU", "BD", "BE", "BG", "BH", "BR",
    "BS", "CA", "CH", "CL", "CN", "CO", "CR", "CY", "CZ", "DE",
    "DK", "DO", "DZ", "EC", "EE", "EG", "ES", "FI", "FR", "GB",
    "GR", "GT", "GY", "HK", "HN", "HR", "HU", "ID", "IE", "IL",
    "IN", "IQ", "IT", "JO", "JP", "KH", "KR", "KW", "KZ", "LK",
    "LT", "LU", "LV", "LY", "MA", "MT", "MX", "MY", "NG", "NI",
    "NL", "NO", "NZ", "OM", "PE", "PH", "PK", "PL", "PT", "QA",
    "RO", "RU", "SA", "SE", "SG", "SI", "SK", "SV", "TH", "TR",
    "TT", "TW", "UY", "VE", "VN", "ZA",
})
EU_ORIGINS = frozenset({
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR",
    "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL",
    "PL", "PT", "RO", "SK", "SI", "ES", "SE",
})
ORIGIN_TABLE = {
    "GB": "united_kingdom",
    "CH": "switzerland",
    "MY": "malaysia",
    "KH": "cambodia",
    "GT": "guatemala",
    "SV": "el_salvador",
    "AR": "argentina",
    "BD": "bangladesh",
    "TW": "taiwan",
    "ID": "indonesia",
    "EC": "ecuador",
    "JO": "jordan",
}
YALE_COUNTRY_KEYS = {
    "united_kingdom": "4120",
    "european_union": (
        "4010;4050;4099;4190;4210;4231;4239;4279;4280;4330;4351;4359;"
        "4370;4470;4490;4510;4550;4700;4710;4730;4759;4791;4792;4840;"
        "4850;4870;4910"
    ),
    "switzerland": "4419",
    "malaysia": "5570",
    "cambodia": "5550",
    "guatemala": "2050",
    "el_salvador": "2110",
    "argentina": "3570",
    "bangladesh": "5380",
    "taiwan": "5830",
    "indonesia": "5600",
    "ecuador": "3310",
    "jordan": "5110",
}
CAFTA_COUNTRY_KEY = "2050;2110;2150;2190;2230;2470"

# Yale broadens these exact legal statistical breakouts to their HTS8 parents.
BROAD_PARENT_TO_LEGAL = {
    "04090000": "0409000005",
    "44079902": "4407990295",
    "84224091": "8422409181",
    "85051100": "8505110070",
    "85371091": "8537109170",
}


def render(payload: Any) -> str:
    return json.dumps(payload, allow_nan=False, indent=2, sort_keys=True) + "\n"


def compact(payload: Any) -> str:
    return json.dumps(payload, allow_nan=False, separators=(",", ":"), sort_keys=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def file_receipt(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
    }


def git_value(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_file_hash(root: Path, relative: str, expected: str) -> dict[str, Any]:
    receipt = file_receipt(root / relative)
    require(
        receipt["sha256"] == expected,
        f"source hash drift for {receipt['path']}: {receipt['sha256']} != {expected}",
    )
    return receipt


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as source:
        return list(csv.DictReader(source))


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def literal_value(path: Path, name: str) -> Any:
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
        ):
            return ast.literal_eval(node.value)
    raise ValueError(f"literal {name} not found in {path}")


def literal_constant(path: Path, name: str) -> float:
    return float(literal_value(path, name))


def generated_atoms(
    tables: dict[str, set[int]], prefixes: Iterable[str]
) -> set[str]:
    result: set[str] = set()
    prefixes = tuple(prefixes)
    for name, values in tables.items():
        if not name.startswith(prefixes):
            continue
        shape = re.sub(r"_p\d+$", "", name)
        if shape.endswith("_membership_hts10"):
            width = 10
        elif shape.endswith("_subheading6_membership"):
            width = 6
        elif shape.endswith("_heading_membership"):
            width = 4
        else:
            width = 8
        result.update(str(value).zfill(width) for value in values)
    return result


def parity(
    generated: set[str], yale: set[str], *, expected_generated_only: set[str] | None = None,
    expected_yale_only: set[str] | None = None,
) -> dict[str, Any]:
    generated_only = generated - yale
    yale_only = yale - generated
    require(
        generated_only == (expected_generated_only or set()),
        f"unexpected generated-only source atoms: {sorted(generated_only)}",
    )
    require(
        yale_only == (expected_yale_only or set()),
        f"unexpected Yale-only source atoms: {sorted(yale_only)}",
    )
    return {
        "generated": len(generated),
        "yale": len(yale),
        "matched": len(generated & yale),
        "generated_only": sorted(generated_only),
        "yale_only": sorted(yale_only),
    }


def audit_sources() -> tuple[ModuleType, frozenset[str], frozenset[str], float, dict[str, Any]]:
    require(RULESPEC_ROOT.is_dir(), f"rulespec root absent: {RULESPEC_ROOT}")
    require(YALE_ROOT.is_dir(), f"Yale root absent: {YALE_ROOT}")
    require(git_value(RULESPEC_ROOT, "rev-parse", "HEAD") == EXPECTED_RULESPEC_COMMIT,
            "rulespec commit drift")
    require(git_value(RULESPEC_ROOT, "rev-parse", "HEAD^{tree}") == EXPECTED_RULESPEC_TREE,
            "rulespec tree drift")
    require(git_value(YALE_ROOT, "rev-parse", "HEAD") == EXPECTED_YALE_COMMIT,
            "Yale commit drift")

    note_tree_oids = {
        note: git_value(
            RULESPEC_ROOT,
            "rev-parse",
            f"HEAD:us/policies/usitc/us-tariff-incidence/generated/{note}",
        )
        for note in EXPECTED_NOTE_TREES
    }
    require(note_tree_oids == EXPECTED_NOTE_TREES, "generated note tree drift")
    scoped_rules_status = git_value(
        RULESPEC_ROOT,
        "status",
        "--porcelain",
        "--",
        *RULESPEC_FILE_SHA256,
        "us/policies/usitc/us-tariff-incidence/generated/note50",
        "us/policies/usitc/us-tariff-incidence/generated/note52",
    )
    require(not scoped_rules_status, f"dirty rulespec source paths: {scoped_rules_status}")
    scoped_yale_status = git_value(
        YALE_ROOT, "status", "--porcelain", "--", *YALE_FILE_SHA256
    )
    require(not scoped_yale_status, f"dirty Yale source paths: {scoped_yale_status}")

    rulespec_files = {
        relative: verify_file_hash(RULESPEC_ROOT, relative, expected)
        for relative, expected in RULESPEC_FILE_SHA256.items()
    }
    yale_files = {
        relative: verify_file_hash(YALE_ROOT, relative, expected)
        for relative, expected in YALE_FILE_SHA256.items()
    }
    generator = RULESPEC_ROOT / "tools/generate_incidence_tables.py"
    require(
        literal_value(generator, "RELPATH") == EXPECTED_NOTES_SOURCE_RELPATH,
        "generator corpus source path drift",
    )
    require(
        literal_value(generator, "SHA256") == EXPECTED_NOTES_SOURCE_SHA256,
        "generator corpus source hash drift",
    )
    page_paths = sorted(
        path
        for note in ("note50", "note52")
        for path in (
            RULESPEC_ROOT
            / "us/policies/usitc/us-tariff-incidence/generated"
            / note
        ).glob("page-*.yaml")
        if not path.name.endswith(".test.yaml")
    )
    require(len(page_paths) == 33, f"expected 33 page modules, got {len(page_paths)}")
    page_modules = [
        {
            "path": str(path.relative_to(RULESPEC_ROOT)),
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }
        for path in page_paths
    ]

    flags_module = load_module(
        RULESPEC_ROOT / "tools/b16_entry_flags.py", "preview_1311_b16_entry_flags"
    )
    flags_module._tables.cache_clear()
    tables = flags_module._tables()

    brazil_full_rows = read_csv(
        YALE_ROOT / "resources/s301_brazil_exempt_products.csv"
    )
    brazil_aircraft_rows = read_csv(
        YALE_ROOT / "resources/s301_brazil_aircraft_products.csv"
    )
    brazil_pharma_rows = read_csv(
        YALE_ROOT / "resources/s301_brazil_pharma_products.csv"
    )
    forced_common_rows = read_csv(
        YALE_ROOT / "resources/s301fl_final_common_exemptions.csv"
    )
    forced_country_rows = read_csv(
        YALE_ROOT / "resources/s301fl_final_country_exemptions.csv"
    )

    expected_statistical = set(BROAD_PARENT_TO_LEGAL.values())
    expected_parents = set(BROAD_PARENT_TO_LEGAL)
    parity_receipts = {
        "brazil_full": parity(
            generated_atoms(tables, BR_FULL_PREFIXES),
            {row["hts8"] for row in brazil_full_rows},
            expected_generated_only=expected_statistical,
            expected_yale_only=expected_parents,
        ),
        "brazil_aircraft": parity(
            generated_atoms(tables, ("brazil_301_aircraft_conditional_",)),
            {row["hts8"] for row in brazil_aircraft_rows},
        ),
        "brazil_pharma": parity(
            generated_atoms(tables, ("brazil_301_pharma_conditional_",)),
            {row["hts8"] for row in brazil_pharma_rows},
        ),
        "forced_common_full": parity(
            generated_atoms(tables, FL_COMMON_FULL_PREFIXES),
            {
                row["hts_code"]
                for row in forced_common_rows
                if row["condition"] in {"full", "ex"}
            },
        ),
        "forced_aircraft": parity(
            generated_atoms(tables, ("forced_labor_301_aircraft_conditional_",)),
            {
                row["hts_code"]
                for row in forced_common_rows
                if row["condition"] == "aircraft"
            },
        ),
        "forced_pharma": parity(
            generated_atoms(tables, ("forced_labor_301_pharma_conditional_",)),
            {
                row["hts_code"]
                for row in forced_common_rows
                if row["condition"] == "pharma"
            },
        ),
    }
    for origin, country_key in YALE_COUNTRY_KEYS.items():
        parity_receipts[f"forced_country_{origin}"] = parity(
            generated_atoms(tables, (f"note52_{origin}_exemption_",)),
            {
                row["hts_code"]
                for row in forced_country_rows
                if row["condition"] == "full" and row["countries"] == country_key
            },
        )

    cafta_rows = [
        row for row in forced_country_rows
        if row["condition"] == "fta" and row["countries"] == CAFTA_COUNTRY_KEY
    ]
    cafta8 = frozenset(row["hts_code"] for row in cafta_rows)
    require(len(cafta_rows) == 1_737 and len(cafta8) == 1_737,
            "Yale CAFTA source is not the pinned 1,737-code set")
    require(
        not [
            row for row in forced_country_rows
            if row["condition"] == "fta" and row["countries"] != CAFTA_COUNTRY_KEY
        ],
        "unexpected second Yale FTA country group",
    )

    tolerance = literal_constant(CAMPAIGN_SOURCE, "TOLERANCE")
    require(tolerance > 0 and math.isfinite(tolerance), "invalid campaign tolerance")
    source_receipt = {
        "rulespec": {
            "path": str(RULESPEC_ROOT),
            "commit": EXPECTED_RULESPEC_COMMIT,
            "tree": EXPECTED_RULESPEC_TREE,
            "note_tree_oids": note_tree_oids,
            "files": rulespec_files,
            "page_module_count": len(page_modules),
            "page_module_manifest_sha256": sha256_text(compact(page_modules)),
            "page_modules": page_modules,
            "generator_declared_corpus_source": {
                "relative_path": EXPECTED_NOTES_SOURCE_RELPATH,
                "sha256": EXPECTED_NOTES_SOURCE_SHA256,
            },
        },
        "yale": {
            "path": str(YALE_ROOT),
            "commit": EXPECTED_YALE_COMMIT,
            "files": yale_files,
            "cafta_condition": "fta",
            "cafta_country_code_group": CAFTA_COUNTRY_KEY,
            "cafta_iso2_origins": sorted(CAFTA_ORIGINS),
            "cafta_unique_hts8": len(cafta8),
        },
        "campaign_source": file_receipt(CAMPAIGN_SOURCE),
        "preview_driver": file_receipt(PREVIEW_DRIVER),
        "campaign_tolerance": tolerance,
        "source_parity": parity_receipts,
        "brazil_yale_statistical_broadening": [
            {"yale_hts8": parent, "legal_hts10": legal}
            for parent, legal in sorted(BROAD_PARENT_TO_LEGAL.items())
        ],
    }
    return (
        flags_module,
        cafta8,
        frozenset(row["hts8"] for row in brazil_full_rows),
        tolerance,
        source_receipt,
    )


def normalized_hts_line(value: Any) -> tuple[int, str]:
    digits = re.sub(r"\D", "", str(value))
    require(0 < len(digits) <= 10, f"invalid hts_line: {value!r}")
    digits = digits.zfill(10)
    return int(digits), digits


def classify_row(
    row: dict[str, Any],
    flags_module: ModuleType,
    cafta8: frozenset[str],
    yale_brazil_full: frozenset[str],
    tolerance: float,
) -> dict[str, Any]:
    require(row.get("new_disagreement") is True, "classifier received a non-new row")
    slot = row.get("slot")
    require(slot in TARGET_SLOTS, f"unexpected target slot: {slot!r}")
    context = row.get("context")
    require(isinstance(context, dict), "mismatch row lacks context")
    iso2 = context.get("iso2")
    require(isinstance(iso2, str) and len(iso2) == 2, f"invalid iso2: {iso2!r}")
    iso2 = iso2.upper()
    hts10 = flags_module._digits(str(context.get("hts10")))
    rate_line, rate_line_digits = normalized_hts_line(context.get("hts_line"))
    interval = context.get("interval")
    require(
        isinstance(interval, list)
        and len(interval) == 2
        and all(isinstance(value, str) for value in interval),
        f"invalid interval: {interval!r}",
    )
    probe = row.get("probe")
    require(isinstance(probe, str), f"invalid probe: {probe!r}")
    expected = float(row["expected"])
    actual = float(row["actual"])
    delta = float(row["delta"])
    require(all(math.isfinite(value) for value in (expected, actual, delta)),
            "non-finite mismatch value")
    require(abs((actual - expected) - delta) <= tolerance,
            "mismatch delta does not reconcile")
    flag_vector = context.get("flags")
    require(isinstance(flag_vector, dict), "mismatch row lacks flag vector")
    listed_flag = flag_vector.get(FLAG_FOR_SLOT[slot]) is True

    def fragment(prefix: str) -> bool:
        return bool(flags_module._fragment_member(prefix, rate_line, hts10))

    full_basis: list[str] = []
    if slot == "brazil_section_301" and iso2 == "BR":
        if fragment("brazil_301_unconditional_exemption_"):
            full_basis.append("brazil-unconditional")
        if fragment("brazil_301_particular_exemption_"):
            full_basis.append("brazil-particular")
    if slot == "forced_labor_section_301" and iso2 in FORCED_ORIGINS:
        if fragment("forced_labor_301_common_exemption_"):
            full_basis.append("forced-common")
        if fragment("forced_labor_301_particular_exemption_"):
            full_basis.append("forced-particular")
        origin_table = ORIGIN_TABLE.get(iso2) or (
            "european_union" if iso2 in EU_ORIGINS else None
        )
        if origin_table and fragment(f"note52_{origin_table}_exemption_"):
            full_basis.append(f"forced-country-{origin_table}")

    raw_labels: set[str] = set()
    if full_basis:
        raw_labels.add("encoded-full-exemption")
    if slot == "brazil_section_301" and iso2 == "BR":
        if fragment("brazil_301_aircraft_conditional_"):
            raw_labels.add("brazil-aircraft")
        if fragment("brazil_301_pharma_conditional_"):
            raw_labels.add("brazil-pharma")
    if slot == "forced_labor_section_301" and iso2 in FORCED_ORIGINS:
        if fragment("forced_labor_301_aircraft_conditional_"):
            raw_labels.add("forced-aircraft")
        if fragment("forced_labor_301_pharma_conditional_"):
            raw_labels.add("forced-pharma")
        if iso2 in CAFTA_ORIGINS and hts10[:8] in cafta8:
            raw_labels.add("cafta-52i")

    conditional_memberships = sorted(raw_labels & CONDITIONAL_LABELS)
    require(
        len(conditional_memberships) <= 1,
        f"overlapping conditional taxonomy requires review: {conditional_memberships}",
    )
    causal_shape = (
        expected == 0.0
        and actual > tolerance
        and delta > tolerance
        and listed_flag
        and probe >= EFFECTIVE_FROM[slot]
    )
    if full_basis:
        primary = "encoded-full-exemption"
    elif causal_shape and conditional_memberships:
        primary = conditional_memberships[0]
    else:
        primary = "unmapped"

    detail_labels: list[str] = []
    broadening = None
    parent = hts10[:8]
    if (
        slot == "brazil_section_301"
        and iso2 == "BR"
        and parent in BROAD_PARENT_TO_LEGAL
        and not full_basis
    ):
        require(parent in yale_brazil_full, "broadening parent absent from Yale source")
        broadening = {
            "yale_hts8": parent,
            "legal_hts10": BROAD_PARENT_TO_LEGAL[parent],
        }
        detail_labels.append("yale-full-list-statistical-broadening")
    if full_basis:
        detail_labels.append("encoded-full-new-mismatch-invariant")
        if listed_flag:
            detail_labels.append("encoded-full-flag-true-invariant")
    if conditional_memberships and not causal_shape and not full_basis:
        detail_labels.append("conditional-membership-noncausal-shape")
    if primary == "unmapped" and not conditional_memberships:
        detail_labels.append("no-audited-membership")

    all_labels = set(raw_labels)
    all_labels.add(primary)
    exact_cafta = causal_shape and "cafta-52i" in raw_labels and not full_basis
    require("cafta_52i_exact" in row, "mismatch row lacks exact CAFTA marker")
    require(
        bool(row["cafta_52i_exact"]) == exact_cafta,
        "taxonomy CAFTA join disagrees with preview-driver exact marker",
    )
    return {
        "taxonomy_primary": primary,
        "all_labels": sorted(all_labels),
        "full_basis": sorted(full_basis),
        "taxonomy_detail_labels": sorted(detail_labels),
        "causal_charge_vs_yale_zero": causal_shape,
        "listed_flag": listed_flag,
        "yale_full_list_statistical_broadening": broadening,
        "surprise": primary != "cafta-52i",
        "normalized": {
            "hts10": hts10,
            "hts_line": rate_line_digits,
            "iso2": iso2,
        },
    }


def counter_rows(
    counter: Counter[tuple[Any, ...]], fields: tuple[str, ...]
) -> list[dict[str, Any]]:
    return [
        dict(zip(fields, key, strict=True), units=units)
        for key, units in sorted(counter.items())
    ]


def sample(row: dict[str, Any]) -> dict[str, Any]:
    context = row["context"]
    return {
        "case_id": row["case_id"],
        "probe": row["probe"],
        "slot": row["slot"],
        "expected": row["expected"],
        "actual": row["actual"],
        "delta": row["delta"],
        "hts10": context["hts10"],
        "hts_line": context["hts_line"],
        "iso2": context["iso2"],
        "revision": context["revision"],
        "interval": context["interval"],
        "taxonomy_primary": row["taxonomy_primary"],
        "all_labels": row["all_labels"],
        "full_basis": row["full_basis"],
        "taxonomy_detail_labels": row["taxonomy_detail_labels"],
    }


def process(
    flags_module: ModuleType,
    cafta8: frozenset[str],
    yale_brazil_full: frozenset[str],
    tolerance: float,
) -> dict[str, Any]:
    primary_counts: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()
    full_basis_counts: Counter[str] = Counter()
    detail_counts: Counter[str] = Counter()
    by_primary_slot: Counter[tuple[str, str]] = Counter()
    by_primary_iso: Counter[tuple[str, str]] = Counter()
    by_primary_chapter: Counter[tuple[str, str]] = Counter()
    by_primary_revision: Counter[tuple[str, str]] = Counter()
    by_primary_interval: Counter[tuple[str, str, str]] = Counter()
    by_primary_delta: Counter[tuple[str, str]] = Counter()
    samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    surprise_groups: dict[tuple[Any, ...], dict[str, set[str] | int]] = {}
    input_rows = 0
    ignored_non_new = 0
    output_rows = 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=OUTPUT.parent, delete=False) as raw:
        temporary = Path(raw.name)
        try:
            with gzip.GzipFile(
                filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0
            ) as zipped:
                with gzip.open(INPUT, "rt") as source:
                    for line_number, line in enumerate(source, 1):
                        require(bool(line.strip()), f"blank input line {line_number}")
                        row = json.loads(line)
                        require(isinstance(row, dict), f"non-object input line {line_number}")
                        input_rows += 1
                        if row.get("new_disagreement") is not True:
                            ignored_non_new += 1
                            continue
                        taxonomy = classify_row(
                            row, flags_module, cafta8, yale_brazil_full, tolerance
                        )
                        reserved = set(taxonomy) & set(row)
                        require(not reserved, f"taxonomy output keys collide: {sorted(reserved)}")
                        output_row = row | taxonomy
                        zipped.write((compact(output_row) + "\n").encode())
                        output_rows += 1

                        primary = taxonomy["taxonomy_primary"]
                        context = row["context"]
                        _, hts_line = normalized_hts_line(context["hts_line"])
                        iso2 = str(context["iso2"]).upper()
                        interval = context["interval"]
                        delta_key = format(float(row["delta"]), ".17g")
                        primary_counts[primary] += 1
                        by_primary_slot[(primary, row["slot"])] += 1
                        by_primary_iso[(primary, iso2)] += 1
                        by_primary_chapter[(primary, hts_line[:2])] += 1
                        by_primary_revision[(primary, context["revision"])] += 1
                        by_primary_interval[(primary, interval[0], interval[1])] += 1
                        by_primary_delta[(primary, delta_key)] += 1
                        for label in taxonomy["all_labels"]:
                            label_counts[label] += 1
                        for basis in taxonomy["full_basis"]:
                            full_basis_counts[basis] += 1
                        for detail in taxonomy["taxonomy_detail_labels"]:
                            detail_counts[detail] += 1
                        if len(samples[primary]) < 5:
                            samples[primary].append(sample(output_row))

                        if taxonomy["surprise"]:
                            key = (
                                primary,
                                row["slot"],
                                context["hts10"],
                                context["hts_line"],
                                iso2,
                                context["revision"],
                                interval[0],
                                interval[1],
                                format(float(row["expected"]), ".17g"),
                                format(float(row["actual"]), ".17g"),
                                delta_key,
                                tuple(taxonomy["all_labels"]),
                                tuple(taxonomy["full_basis"]),
                                tuple(taxonomy["taxonomy_detail_labels"]),
                            )
                            group = surprise_groups.setdefault(
                                key,
                                {"units": 0, "case_ids": set(), "probes": set()},
                            )
                            group["units"] = int(group["units"]) + 1
                            assert isinstance(group["case_ids"], set)
                            assert isinstance(group["probes"], set)
                            group["case_ids"].add(str(row["case_id"]))
                            group["probes"].add(str(row["probe"]))
            temporary.replace(OUTPUT)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    require(input_rows == ignored_non_new + output_rows, "input row conservation failed")
    require(sum(primary_counts.values()) == output_rows, "primary conservation failed")
    require(set(primary_counts) <= set(PRIMARY_ORDER), "unknown primary taxonomy")

    exact_surprise_cells: list[dict[str, Any]] = []
    for key, group in sorted(surprise_groups.items()):
        (
            primary, slot, hts10, hts_line, iso2, revision,
            interval_from, interval_until, expected, actual, delta,
            all_labels, full_basis, details,
        ) = key
        exact_surprise_cells.append({
            "taxonomy_primary": primary,
            "slot": slot,
            "hts10": hts10,
            "hts_line": hts_line,
            "iso2": iso2,
            "revision": revision,
            "interval": [interval_from, interval_until],
            "expected": expected,
            "actual": actual,
            "delta": delta,
            "all_labels": list(all_labels),
            "full_basis": list(full_basis),
            "taxonomy_detail_labels": list(details),
            "units": group["units"],
            "case_ids": sorted(group["case_ids"]),
            "probes": sorted(group["probes"]),
        })

    return {
        "input_rows": input_rows,
        "ignored_non_new_rows": ignored_non_new,
        "new_disagreement_rows": output_rows,
        "primary_counts": {
            name: primary_counts.get(name, 0) for name in PRIMARY_ORDER
        },
        "all_label_counts": dict(sorted(label_counts.items())),
        "full_basis_counts": dict(sorted(full_basis_counts.items())),
        "detail_counts": dict(sorted(detail_counts.items())),
        "groupings": {
            "by_primary_slot": counter_rows(
                by_primary_slot, ("taxonomy_primary", "slot")
            ),
            "by_primary_iso2": counter_rows(
                by_primary_iso, ("taxonomy_primary", "iso2")
            ),
            "by_primary_chapter": counter_rows(
                by_primary_chapter, ("taxonomy_primary", "chapter")
            ),
            "by_primary_revision": counter_rows(
                by_primary_revision, ("taxonomy_primary", "revision")
            ),
            "by_primary_interval": counter_rows(
                by_primary_interval,
                ("taxonomy_primary", "interval_from", "interval_until"),
            ),
            "by_primary_delta": counter_rows(
                by_primary_delta, ("taxonomy_primary", "delta")
            ),
        },
        "samples": {name: samples.get(name, []) for name in PRIMARY_ORDER},
        "surprises": {
            "definition": (
                "every new disagreement except the separately expected/deferred "
                "cafta-52i population"
            ),
            "units": sum(
                units for primary, units in primary_counts.items()
                if primary != "cafta-52i"
            ),
            "distinct_cells": len(exact_surprise_cells),
            "exact_cells": exact_surprise_cells,
        },
        "conservation": {
            "input_equals_ignored_plus_new": input_rows == ignored_non_new + output_rows,
            "new_equals_exclusive_primary_sum": output_rows == sum(primary_counts.values()),
            "verdict": "PASS",
        },
    }


def verify_target_receipt(input_receipt: dict[str, Any]) -> dict[str, Any]:
    require(TARGET_RECEIPT.is_file(), f"target receipt absent: {TARGET_RECEIPT}")
    target = json.loads(TARGET_RECEIPT.read_text())
    require(
        target.get("schema")
        == "axiom_oracles.us_tariff_schedule.preview_1311_target_classification.v1",
        "unexpected target receipt schema",
    )
    require(target.get("verdict") == "PASS", "target receipt is not a PASS")
    artifact = target.get("artifacts", {}).get("mismatch_cells", {})
    require(Path(artifact.get("path", "")).resolve() == INPUT.resolve(),
            "target receipt points to another mismatch artifact")
    require(artifact.get("sha256") == input_receipt["sha256"],
            "target receipt mismatch artifact hash drift")
    require(artifact.get("bytes") == input_receipt["bytes"],
            "target receipt mismatch artifact byte drift")
    return target


def write_receipt(payload: dict[str, Any]) -> None:
    payload_digest = sha256_text(render(payload))
    final = payload | {
        "receipt_payload_sha256": payload_digest,
        "receipt_payload_hash_scope": "canonical payload before these two receipt_payload fields",
    }
    with tempfile.NamedTemporaryFile("w", dir=RECEIPT.parent, delete=False) as target:
        target.write(render(final))
        temporary = Path(target.name)
    temporary.replace(RECEIPT)


def main() -> int:
    if not INPUT.is_file():
        raise SystemExit(
            f"STOP: {INPUT} does not exist; run only after target compare/classify completes"
        )
    require(PREVIEW_DRIVER.is_file(), f"preview driver absent: {PREVIEW_DRIVER}")
    input_receipt = file_receipt(INPUT)
    target = verify_target_receipt(input_receipt)
    flags_module, cafta8, yale_brazil_full, tolerance, sources = audit_sources()
    classification = process(
        flags_module, cafta8, yale_brazil_full, tolerance
    )
    require(
        classification["input_rows"] == target["mismatch_cell_rows"],
        "taxonomy input rows differ from target mismatch rows",
    )
    require(
        classification["new_disagreement_rows"]
        == target["new_disagreements"]["units"],
        "taxonomy new rows differ from target new-disagreement units",
    )
    taxonomy_by_slot = Counter({
        slot: sum(
            row["units"]
            for row in classification["groupings"]["by_primary_slot"]
            if row["slot"] == slot
        )
        for slot in TARGET_SLOTS
    })
    target_by_slot = Counter(target["new_disagreements"]["per_slot"])
    require(
        taxonomy_by_slot == target_by_slot,
        f"taxonomy per-slot counts differ from target: {taxonomy_by_slot} != {target_by_slot}",
    )
    require(
        classification["primary_counts"]["cafta-52i"]
        == target["cafta_52i_residual"]["units"],
        "taxonomy CAFTA count differs from target exact residual",
    )
    receipt = {
        "schema": "axiom_oracles.us_tariff_schedule.preview_1311_mismatch_taxonomy.v1",
        "verdict": "PASS",
        "taxonomy": {
            "primary_precedence": list(PRIMARY_ORDER),
            "multi_label_field": "all_labels",
            "full_basis_field": "full_basis",
            "conditional_causal_shape": (
                "Yale expected == 0; Axiom actual and delta > campaign tolerance; "
                "listed flag true; probe on/after action effective date"
            ),
            "cafta_scope": (
                "Exact Yale-panel join to condition=fta HTS8 and CAFTA origins; "
                "not independent proof of GN 29(d)(v) or duty-free entry facts"
            ),
            "encoded_full_precedence_reason": (
                "Full relief controls when a code also appears in a conditional table; "
                "any new mismatch in this bucket is an invariant failure"
            ),
        },
        "classification": classification,
        "inputs": {
            "mismatch_cells": input_receipt,
            "target_receipt": file_receipt(TARGET_RECEIPT),
        },
        "sources": sources,
        "script": file_receipt(Path(__file__).resolve()),
        "outputs": {
            "new_mismatch_cells": file_receipt(OUTPUT),
            "receipt_path": str(RECEIPT),
        },
    }
    write_receipt(receipt)
    print(render({
        "verdict": "PASS",
        "new_disagreement_rows": classification["new_disagreement_rows"],
        "primary_counts": classification["primary_counts"],
        "output": file_receipt(OUTPUT),
        "receipt": file_receipt(RECEIPT),
    }), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
