#!/usr/bin/env python3
"""Lane-local note-50/52 preview without modifying campaign source artifacts."""

from __future__ import annotations

import argparse
import copy
import csv
import gzip
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

import yaml


LANE_DIR = Path(__file__).resolve().parent
REPO_ROOT = LANE_DIR.parents[2]
RULESPEC_ROOT = Path(
    "/Users/maxghenis/PolicyEngine/_tariff-p5/b1/c6-roots/rulespec-us"
)
RULESPEC_SOURCE_WORKTREE = Path(
    "/Users/maxghenis/TheAxiomFoundation/_b1wt/rulespec-us/.worktrees/rulespec-us-c6"
)
ENGINE_BINARY = Path(
    "/Users/maxghenis/PolicyEngine/_tariff-p5/b1/c6-roots/"
    "axiom-rules-engine/target/release/axiom-rules-engine"
)
YALE_ROOT = Path("/Users/maxghenis/TheAxiomFoundation/_tariff-yale")
YALE_CAFTA_FTA = YALE_ROOT / "resources/s301fl_final_country_exemptions.csv"
CORPUS_ROOT = Path("/Users/maxghenis/TheAxiomFoundation/axiom-corpus")
CORPUS_PROVENANCE_COMMIT = "5cf7556ad3d68aa0596d58f7ac60942bb5db3120"
CORPUS_RELEASE = "us-rulespec-2026-08-09-cutover-surface-union"
CORPUS_SELECTOR_PATH = f"manifests/releases/{CORPUS_RELEASE}.json"
CORPUS_CONTENT_SHA256 = (
    "9591ed6ade8f264f34a79e89b99ae05ac04b19cb1bf6b69480108bdfee1eb435"
)
CORPUS_ACTIVATION_PREVIEW = Path(
    "/Users/maxghenis/PolicyEngine/_tariff-p5/b1/reviews/"
    "activation-preview-32637206404.md"
)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import us_tariff_schedule_campaign as campaign  # noqa: E402


TARGET_CLASSES = (
    "fed-false-family-forced-labor",
    "fed-false-family-brazil",
)
TARGET_SLOTS = (
    "forced_labor_section_301",
    "brazil_section_301",
)
SLOT_FLAG = {
    "forced_labor_section_301": "entry_is_forced_labor_301_listed",
    "brazil_section_301": "entry_is_brazil_301_listed",
}
SLOT_EFFECTIVE_FROM = {
    "forced_labor_section_301": "2026-07-24",
    "brazil_section_301": "2026-07-22",
}
CAFTA_ORIGINS = frozenset({"CR", "DO", "SV", "GT", "HN", "NI"})
FORCED_LABOR_ORIGINS = frozenset({
    "AE", "AO", "AR", "AT", "AU", "BD", "BE", "BG", "BH", "BR", "BS",
    "CA", "CH", "CL", "CN", "CO", "CR", "CY", "CZ", "DE", "DK", "DO",
    "DZ", "EC", "EE", "EG", "ES", "FI", "FR", "GB", "GR", "GT", "GY",
    "HK", "HN", "HR", "HU", "ID", "IE", "IL", "IN", "IQ", "IT", "JO",
    "JP", "KH", "KR", "KW", "KZ", "LK", "LT", "LU", "LV", "LY", "MA",
    "MT", "MX", "MY", "NG", "NI", "NL", "NO", "NZ", "OM", "PE", "PH",
    "PK", "PL", "PT", "QA", "RO", "RU", "SA", "SE", "SG", "SI", "SK",
    "SV", "TH", "TR", "TT", "TW", "UY", "VE", "VN", "ZA",
})
assert len(FORCED_LABOR_ORIGINS) == 86
ALIAS_PROJECTION = frozenset({
    "entry_is_brazil_301",
    "entry_is_forced_labor_301",
})
PARTITION_CHAPTERS = tuple(
    [f"{chapter:02d}" for chapter in range(1, 27)]
    + [f"{chapter:02d}" for chapter in range(28, 31)]
    + [f"{chapter:02d}" for chapter in range(32, 75)]
    + ["75", "76"]
    + [f"{chapter:02d}" for chapter in range(78, 97)]
    + ["98"]
)
assert len(PARTITION_CHAPTERS) == 94
EXPECTED_ENDPOINT_RECORDS = 19_085_544

FULL_CONTRACT = LANE_DIR / "declared-input-contract-full.json"
PARTITION_CONTRACT = LANE_DIR / "declared-input-contract-partition.json"
CONTRACT_EXECUTION = LANE_DIR / "input-contract-execution-receipt.json"
PROJECTION_RECEIPT = LANE_DIR / "evaluation-projection-receipt.json"
EVAL_MANIFEST = LANE_DIR / "eval" / "MANIFEST.json"
TARGET_COMPARISON = LANE_DIR / "target-comparison-classification-receipt.json"
TARGET_MISMATCH_CELLS = LANE_DIR / "target-mismatch-cells.jsonl.gz"
PROVENANCE_RECEIPT = LANE_DIR / "provenance-receipt.json"
STATIC_FOOTPRINT = LANE_DIR / "static-footprint-census-receipt.json"


def configure_campaign() -> None:
    """Rebind generated outputs to this lane and project only undeclared aliases."""
    campaign.CACHE_ROOT = LANE_DIR / "cache"
    campaign.INPUT_CONTRACT_RECEIPT = PARTITION_CONTRACT
    campaign.EVAL_DIR = EVAL_MANIFEST.parent
    campaign.EVAL_MANIFEST = EVAL_MANIFEST
    campaign.COMPARISON_RECEIPT = LANE_DIR / "unused-comparison-summary.json"
    campaign.CLASSIFICATION_RECEIPT = LANE_DIR / "unused-classification-receipt.json"
    campaign.EVAL_PROJECTION_RECEIPT = PROJECTION_RECEIPT
    campaign.INCIDENCE_ROOT = (
        RULESPEC_ROOT / "us/policies/usitc/us-tariff-incidence/generated"
    )
    campaign.CH98_LINES = (
        campaign.INCIDENCE_ROOT.parent.parent
        / "us-tariff-duty/lines/generated/ch98.yaml"
    )
    campaign.EXPECTED_DROPPED_ENTRY_FLAGS = frozenset(
        campaign.EXPECTED_DROPPED_ENTRY_FLAGS | ALIAS_PROJECTION
    )
    campaign._membership_rules.cache_clear()
    campaign._named_line_sets.cache_clear()


def render(payload: Any) -> str:
    return json.dumps(payload, allow_nan=False, indent=2, sort_keys=True) + "\n"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as target:
        target.write(render(payload))
        temporary = Path(target.name)
    temporary.replace(path)


def git_value(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def receipt_file(path: Path) -> dict[str, Any]:
    return {"path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size}


def cafta_fta_source() -> tuple[frozenset[str], dict[str, Any]]:
    with YALE_CAFTA_FTA.open(newline="") as source:
        rows = list(csv.DictReader(source))
    fta_rows = [row for row in rows if row["condition"] == "fta"]
    codes = frozenset(row["hts_code"] for row in fta_rows)
    country_groups = sorted({row["countries"] for row in fta_rows})
    if len(fta_rows) != 1_737 or len(codes) != 1_737:
        raise ValueError("Yale CAFTA conditional list is not the pinned 1,737-code set")
    if country_groups != ["2050;2110;2150;2190;2230;2470"]:
        raise ValueError(f"unexpected Yale CAFTA country group: {country_groups}")
    campaign_provenance = json.loads(
        (REPO_ROOT / "reference/us-tariff-schedule/provenance.json").read_text()
    )
    yale_commit = git_value(YALE_ROOT, "rev-parse", "HEAD")
    if yale_commit != campaign_provenance["yale_commit"]:
        raise ValueError(
            f"Yale checkout drift: {yale_commit} != {campaign_provenance['yale_commit']}"
        )
    tracked_status = git_value(
        YALE_ROOT, "status", "--porcelain", "--", str(YALE_CAFTA_FTA.relative_to(YALE_ROOT))
    )
    if tracked_status:
        raise ValueError(f"Yale CAFTA source is dirty: {tracked_status}")
    return codes, {
        **receipt_file(YALE_CAFTA_FTA),
        "yale_commit": yale_commit,
        "condition": "fta",
        "source_rows": len(fta_rows),
        "unique_hts8": len(codes),
        "country_code_group": country_groups[0],
        "iso2_origins": sorted(CAFTA_ORIGINS),
    }


def corpus_release_source() -> dict[str, Any]:
    selector_raw = subprocess.run(
        [
            "git", "-C", str(CORPUS_ROOT), "show",
            f"{CORPUS_PROVENANCE_COMMIT}:{CORPUS_SELECTOR_PATH}",
        ],
        check=True,
        capture_output=True,
    ).stdout
    selector_file_sha256 = hashlib.sha256(selector_raw).hexdigest()
    selector = json.loads(selector_raw)
    canonical = {
        key: selector[key] for key in ("name", "quality_profile", "scopes")
    }
    selector_sha256 = hashlib.sha256(
        json.dumps(
            canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
    ).hexdigest()
    if selector_file_sha256 != "392f99a9804b66b48bdc758d7f576fa47c8822d3c48da68125ec12769bf4c166":
        raise ValueError(f"preview corpus selector bytes drift: {selector_file_sha256}")
    if selector_sha256 != "e8a66545095eff763e7e1dab473c9848e62a0407b83421bb0e879009e78a7fd9":
        raise ValueError(f"preview corpus selector digest drift: {selector_sha256}")
    if selector["name"] != CORPUS_RELEASE or len(selector["scopes"]) != 274:
        raise ValueError("preview corpus selector identity/scope count drift")

    gn29_items = 0
    missing_inventories: list[str] = []
    rev15_notes_items = None
    rev15_notes_roots: list[str] = []
    for scope in selector["scopes"]:
        inventory_path = (
            "data/corpus/inventory/"
            f"{scope['jurisdiction']}/{scope['document_class']}/{scope['version']}.json"
        )
        result = subprocess.run(
            [
                "git", "-C", str(CORPUS_ROOT), "show",
                f"{CORPUS_PROVENANCE_COMMIT}:{inventory_path}",
            ],
            capture_output=True,
        )
        if result.returncode:
            missing_inventories.append(inventory_path)
            continue
        inventory = json.loads(result.stdout)
        paths = [item["citation_path"] for item in inventory["items"]]
        gn29_items += sum(
            path == "us/statute/hts/general-note-29"
            or path.startswith("us/statute/hts/general-note-29/")
            for path in paths
        )
        if scope["version"] == "2026-08-04-usitc-hts-2026-rev15-notes":
            rev15_notes_items = len(paths)
            rev15_notes_roots = sorted({
                path for path in paths
                if path in {
                    "us/statute/hts/general-note-3",
                    "us/statute/hts/chapter-99",
                }
            })
    if missing_inventories or gn29_items or rev15_notes_items != 815:
        raise ValueError(
            "preview corpus GN29 audit drift: "
            f"missing={missing_inventories}, gn29={gn29_items}, "
            f"rev15_items={rev15_notes_items}"
        )
    if rev15_notes_roots != [
        "us/statute/hts/chapter-99", "us/statute/hts/general-note-3"
    ]:
        raise ValueError(f"unexpected Rev-15 note roots: {rev15_notes_roots}")
    activation_text = CORPUS_ACTIVATION_PREVIEW.read_text()
    if CORPUS_CONTENT_SHA256 not in activation_text:
        raise ValueError("signed release content hash absent from activation preview")
    return {
        "release": CORPUS_RELEASE,
        "provenance_commit": CORPUS_PROVENANCE_COMMIT,
        "selector_path": CORPUS_SELECTOR_PATH,
        "selector_file_sha256": selector_file_sha256,
        "selector_sha256": selector_sha256,
        "signed_release_content_sha256": CORPUS_CONTENT_SHA256,
        "selector_scopes": len(selector["scopes"]),
        "inventories_read": len(selector["scopes"]) - len(missing_inventories),
        "missing_inventories": missing_inventories,
        "general_note_29_inventory_items": gn29_items,
        "rev15_notes_inventory_items": rev15_notes_items,
        "rev15_notes_root_citations": rev15_notes_roots,
        "activation_preview": receipt_file(CORPUS_ACTIVATION_PREVIEW),
    }


def build_provenance_receipt() -> dict[str, Any]:
    _, cafta_source = cafta_fta_source()
    corpus_source = corpus_release_source()
    note_paths = sorted(
        list((campaign.INCIDENCE_ROOT / "note50").glob("page-*.yaml"))
        + list((campaign.INCIDENCE_ROOT / "note52").glob("page-*.yaml"))
    )
    baseline_manifest = REPO_ROOT / "reference/us-tariff-schedule/eval/MANIFEST.json"
    baseline = json.loads(baseline_manifest.read_text())
    partition_shards = [
        shard for shard in baseline["shards"].values()
        if shard["chapter"] in PARTITION_CHAPTERS
    ]
    payload = {
        "schema": "axiom_oracles.us_tariff_schedule.preview_1311_provenance.v1",
        "cert_baseline_commit": "903f5b8fba7ae80dcc7d3a5ba00c66ae3fa31da7",
        "driver": receipt_file(Path(__file__).resolve()),
        "rulespec": {
            "path": str(RULESPEC_ROOT),
            "commit": git_value(RULESPEC_ROOT, "rev-parse", "HEAD"),
            "tree": git_value(RULESPEC_ROOT, "rev-parse", "HEAD^{tree}"),
            "status_porcelain": git_value(RULESPEC_ROOT, "status", "--porcelain"),
            "entry_flag_tool": receipt_file(RULESPEC_ROOT / "tools/b16_entry_flags.py"),
            "page_modules": [
                {
                    "path": str(path.relative_to(RULESPEC_ROOT)),
                    "sha256": sha256(path),
                }
                for path in note_paths
            ],
            "source_worktree": {
                "path": str(RULESPEC_SOURCE_WORKTREE),
                "commit": git_value(RULESPEC_SOURCE_WORKTREE, "rev-parse", "HEAD"),
                "tree": git_value(RULESPEC_SOURCE_WORKTREE, "rev-parse", "HEAD^{tree}"),
                "status_porcelain": git_value(
                    RULESPEC_SOURCE_WORKTREE, "status", "--porcelain"
                ),
            },
        },
        "engine": {
            "path": str(ENGINE_BINARY),
            "resolved_path": str(ENGINE_BINARY.resolve()),
            "sha256": sha256(ENGINE_BINARY),
            "commit": git_value(ENGINE_BINARY.resolve().parents[2], "rev-parse", "HEAD"),
            "tree": git_value(
                ENGINE_BINARY.resolve().parents[2], "rev-parse", "HEAD^{tree}"
            ),
            "status_porcelain": git_value(
                ENGINE_BINARY.resolve().parents[2], "status", "--porcelain"
            ),
        },
        "campaign_inputs": {
            "selected_intervals": receipt_file(campaign.SELECTED),
            "routing": receipt_file(campaign.ROUTING_ROWS),
            "disposition_ledger": receipt_file(campaign.DISPOSITION_LEDGER),
            "baseline_manifest": receipt_file(baseline_manifest),
            "baseline_classification": receipt_file(
                REPO_ROOT / "reference/us-tariff-schedule/classification-receipt.json"
            ),
            "campaign_source": receipt_file(
                REPO_ROOT / "scripts/us_tariff_schedule_campaign.py"
            ),
            "certificate": receipt_file(
                REPO_ROOT / "certificates/us-tariff-duty.json"
            ),
            "yale_cafta_fta_list": cafta_source,
        },
        "preview_corpus_release": corpus_source,
        "partition": {
            "chapters": list(PARTITION_CHAPTERS),
            "chapter_count": len(PARTITION_CHAPTERS),
            "omitted_chapters": ["27", "31", "97", "99a", "99b", "99c"],
            "prior_endpoint_cases": sum(shard["cases"] for shard in partition_shards),
            "prior_sequential_shard_seconds": sum(
                shard["elapsed_seconds"] for shard in partition_shards
            ),
        },
        "preview_projection": {
            "dropped_undeclared_aliases": sorted(ALIAS_PROJECTION),
            "fed_declared_flags": [
                "entry_is_brazil_301_listed",
                "entry_is_forced_labor_301_listed",
            ],
            "source_edits": False,
        },
    }
    write_json(PROVENANCE_RECEIPT, payload)
    return payload


def input_contract() -> dict[str, Any]:
    started = time.perf_counter()
    full = campaign.build_input_contract_receipt(
        rulespec_root=RULESPEC_ROOT,
        engine_binary=ENGINE_BINARY,
    )
    write_json(FULL_CONTRACT, full)
    full_hash = sha256(FULL_CONTRACT)
    partition = copy.deepcopy(full)
    partition["chapters"] = [
        chapter for chapter in full["chapters"]
        if chapter["chapter"] in PARTITION_CHAPTERS
    ]
    partition["composition_count"] = len(partition["chapters"])
    partition["preview_partition"] = {
        "source_full_contract": receipt_file(FULL_CONTRACT),
        "chapters": list(PARTITION_CHAPTERS),
        "omitted_chapters": ["27", "31", "97", "99a", "99b", "99c"],
        "reason": (
            "union of the two committed open-class chapter footprints and every "
            "additional chapter with a C6 declared flag true on a compared Yale-zero cell"
        ),
    }
    assert len(partition["chapters"]) == len(PARTITION_CHAPTERS)
    write_json(PARTITION_CONTRACT, partition)
    provenance = build_provenance_receipt()
    execution = {
        "schema": "axiom_oracles.us_tariff_schedule.preview_1311_input_contract_execution.v1",
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "full_contract": receipt_file(FULL_CONTRACT),
        "partition_contract": receipt_file(PARTITION_CONTRACT),
        "provenance": receipt_file(PROVENANCE_RECEIPT),
        "full_contract_sha256_before_partition": full_hash,
        "verdict": "PASS",
    }
    write_json(CONTRACT_EXECUTION, execution)
    return execution | {"provenance_summary": provenance["partition"]}


def projection() -> dict[str, Any]:
    if not PARTITION_CONTRACT.is_file():
        raise ValueError("run input-contract first")
    return campaign.evaluate_projection(
        rulespec_root=RULESPEC_ROOT,
        engine_binary=ENGINE_BINARY,
    )


def evaluate(*, workers: int, resume: bool) -> dict[str, Any]:
    if not PARTITION_CONTRACT.is_file():
        raise ValueError("run input-contract first")
    result = campaign.evaluate_campaign(
        rulespec_root=RULESPEC_ROOT,
        engine_binary=ENGINE_BINARY,
        workers=workers,
        chapters=PARTITION_CHAPTERS,
        resume=resume,
        cache_dir=LANE_DIR / "cache/eval",
    )
    chapters = {shard["chapter"] for shard in result["shards"].values()}
    if chapters != set(PARTITION_CHAPTERS):
        raise ValueError(f"partition manifest mismatch: {sorted(chapters)}")
    return result


def _counter_rows(counter: Counter[tuple[Any, ...]], fields: tuple[str, ...]) -> list[dict[str, Any]]:
    return [
        dict(zip(fields, key, strict=True), units=units)
        for key, units in sorted(counter.items())
    ]


def static_footprint_census() -> dict[str, Any]:
    """Receipt the old target footprint and all changed-flag Yale-zero exposure."""
    sys.path.insert(0, str(RULESPEC_ROOT))
    from tools.b16_entry_flags import entry_flags  # type: ignore

    started = time.perf_counter()
    routes = campaign._routing_by_member()
    ledger = yaml.safe_load(campaign.DISPOSITION_LEDGER.read_text())
    target_entries = {
        entry["id"]: entry for entry in ledger["entries"]
        if entry["id"] in TARGET_CLASSES
    }
    class_for_slot = dict(zip(TARGET_SLOTS, TARGET_CLASSES, strict=True))
    expected_column = {
        "forced_labor_section_301": "statutory_rate_s301fl",
        "brazil_section_301": "statutory_rate_s301br",
    }
    cafta_fta_hts8, cafta_source = cafta_fta_source()
    baseline: Counter[str] = Counter()
    baseline_chapters: dict[str, set[str]] = {
        class_id: set() for class_id in TARGET_CLASSES
    }
    baseline_by_class_iso: Counter[tuple[str, str]] = Counter()
    baseline_by_class_probe: Counter[tuple[str, str]] = Counter()
    exposure: Counter[str] = Counter()
    exposure_by_slot_chapter: Counter[tuple[str, str]] = Counter()
    exposure_by_slot_iso: Counter[tuple[str, str]] = Counter()
    exposure_cells: dict[str, set[tuple[str, ...]]] = {
        slot: set() for slot in TARGET_SLOTS
    }
    cafta_exact: Counter[str] = Counter()
    cafta_exact_by_chapter: Counter[str] = Counter()
    cafta_exact_by_probe: Counter[str] = Counter()
    cafta_exact_cells: set[tuple[str, ...]] = set()
    flag_calls = 0
    last_flag_key: tuple[int, str, str] | None = None
    last_flags: dict[str, bool] | None = None
    selected_rows = 0

    for row in campaign._selected_rows(campaign.SELECTED):
        selected_rows += 1
        route = routes[row["hts10"]]
        disposition = (
            route["column2_disposition"]
            if row["iso2"] in campaign.COLUMN2_ORIGINS
            else route["general_disposition"]
        )
        column2_available = not (
            row["iso2"] in campaign.COLUMN2_ORIGINS
            and route["chapter_shard"] in {"99a", "99b"}
        )
        plan = campaign.query_plan(
            disposition, column2_rate_available=column2_available
        )
        probes = campaign._probe_dates(row)
        candidate_slots: list[tuple[str, float, list[str]]] = []
        for slot in TARGET_SLOTS:
            if slot not in plan["components"]:
                continue
            if slot == "brazil_section_301" and row["iso2"] != "BR":
                continue
            if (
                slot == "forced_labor_section_301"
                and row["iso2"] not in FORCED_LABOR_ORIGINS
            ):
                continue
            expected = float(row[expected_column[slot]])
            class_id = class_for_slot[slot]
            old_unit = {
                "slot": slot,
                "origin_regime": row["origin_regime"],
                "revision": row["revision"],
                "delta": -expected,
                "disposition": disposition,
                "hts10": row["hts10"],
                "hts_line": route["hts_line"],
                "flags": {},
                "interval": [row["clipped_from"], row["clipped_until"]],
                "iso2": row["iso2"],
            }
            if (
                abs(expected) > campaign.TOLERANCE
                and campaign.selector_matches(
                    old_unit, target_entries[class_id]["match"]
                )
            ):
                baseline[class_id] += len(probes)
                baseline_chapters[class_id].add(route["chapter_shard"])
                baseline_by_class_iso[(class_id, row["iso2"])] += len(probes)
                for probe in probes:
                    baseline_by_class_probe[(class_id, probe)] += 1
            eligible_probes = [
                probe for probe in probes
                if probe >= SLOT_EFFECTIVE_FROM[slot]
            ]
            if abs(expected) <= campaign.TOLERANCE and eligible_probes:
                candidate_slots.append((slot, expected, eligible_probes))

        if not candidate_slots:
            continue
        flag_key = (int(route["hts_line"]), row["hts10"], row["iso2"])
        if flag_key != last_flag_key:
            last_flags = entry_flags(*flag_key)
            last_flag_key = flag_key
            flag_calls += 1
        assert last_flags is not None
        for slot, _, eligible_probes in candidate_slots:
            if last_flags.get(SLOT_FLAG[slot]) is not True:
                continue
            units = len(eligible_probes)
            exposure[slot] += units
            exposure_by_slot_chapter[(slot, route["chapter_shard"])] += units
            exposure_by_slot_iso[(slot, row["iso2"])] += units
            exposure_cells[slot].add((
                row["hts10"], row["iso2"], row["revision"],
                row["clipped_from"], row["clipped_until"],
            ))
            if (
                slot == "forced_labor_section_301"
                and row["iso2"] in CAFTA_ORIGINS
                and row["hts10"][:8] in cafta_fta_hts8
            ):
                cafta_exact[row["iso2"]] += units
                cafta_exact_by_chapter[route["chapter_shard"]] += units
                for probe in eligible_probes:
                    cafta_exact_by_probe[probe] += 1
                cafta_exact_cells.add((
                    row["hts10"], row["iso2"], row["revision"],
                    row["clipped_from"], row["clipped_until"],
                ))

    baseline_expected = json.loads(
        (REPO_ROOT / "reference/us-tariff-schedule/classification-receipt.json").read_text()
    )["class_census"]
    expected_targets = {
        class_id: baseline_expected[class_id] for class_id in TARGET_CLASSES
    }
    if dict(baseline) != expected_targets:
        raise ValueError(
            f"static baseline reconstruction drift: {dict(baseline)} != {expected_targets}"
        )
    footprint = set().union(*baseline_chapters.values()) | {
        chapter for (_, chapter), units in exposure_by_slot_chapter.items() if units
    }
    if footprint != set(PARTITION_CHAPTERS):
        raise ValueError(
            f"static partition drift: {sorted(footprint)} != {list(PARTITION_CHAPTERS)}"
        )
    cafta_units = sum(cafta_exact.values())
    if cafta_units != 17_404:
        raise ValueError(f"static exact CAFTA census drift: {cafta_units} != 17404")
    if len(cafta_exact_cells) != 8_702:
        raise ValueError(
            f"static exact CAFTA interval-row drift: {len(cafta_exact_cells)} != 8702"
        )
    receipt = {
        "schema": "axiom_oracles.us_tariff_schedule.preview_1311_static_footprint.v1",
        "verdict": "PASS",
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "selected_interval_rows_scanned": selected_rows,
        "entry_flag_calls": flag_calls,
        "baseline_target_units": dict(baseline),
        "baseline_chapters": {
            class_id: sorted(chapters)
            for class_id, chapters in baseline_chapters.items()
        },
        "baseline_by_class_iso": _counter_rows(
            baseline_by_class_iso, ("class_id", "iso2")
        ),
        "baseline_by_class_probe": _counter_rows(
            baseline_by_class_probe, ("class_id", "probe")
        ),
        "flag_true_yale_zero_ceiling": {
            "per_slot": dict(exposure),
            "distinct_interval_cells": {
                slot: len(cells) for slot, cells in exposure_cells.items()
            },
            "by_slot_chapter": _counter_rows(
                exposure_by_slot_chapter, ("slot", "chapter")
            ),
            "by_slot_iso": _counter_rows(exposure_by_slot_iso, ("slot", "iso2")),
        },
        "exact_cafta_52i_panel": {
            "units": cafta_units,
            "interval_rows": len(cafta_exact_cells),
            "per_origin": dict(sorted(cafta_exact.items())),
            "by_chapter": dict(sorted(cafta_exact_by_chapter.items())),
            "by_probe": dict(sorted(cafta_exact_by_probe.items())),
            "source": cafta_source,
        },
        "partition": {
            "chapters": sorted(footprint),
            "chapter_count": len(footprint),
            "old_class_chapter_count": len(set().union(*baseline_chapters.values())),
            "added_for_changed_flag_exposure": sorted(
                footprint - set().union(*baseline_chapters.values())
            ),
            "omitted_chapters": ["27", "31", "97", "99a", "99b", "99c"],
        },
        "inputs": {
            "selected_intervals": receipt_file(campaign.SELECTED),
            "routing": receipt_file(campaign.ROUTING_ROWS),
            "disposition_ledger": receipt_file(campaign.DISPOSITION_LEDGER),
            "baseline_classification": receipt_file(
                REPO_ROOT / "reference/us-tariff-schedule/classification-receipt.json"
            ),
            "entry_flag_tool": receipt_file(RULESPEC_ROOT / "tools/b16_entry_flags.py"),
            "driver": receipt_file(Path(__file__).resolve()),
        },
    }
    write_json(STATIC_FOOTPRINT, receipt)
    return receipt


def target_compare_classify() -> dict[str, Any]:
    """Compare/classify the two changed slots without emitting all match rows."""
    manifest = campaign._load_manifest()
    expected_shards = {
        campaign._shard_key(
            chapter=chapter,
            rulespec_root=RULESPEC_ROOT,
            engine_binary=ENGINE_BINARY,
        ): chapter
        for chapter in PARTITION_CHAPTERS
    }
    if set(manifest["shards"]) != set(expected_shards):
        raise ValueError("manifest keys do not bind to the current preview inputs")
    for key, chapter in expected_shards.items():
        if manifest["shards"][key]["chapter"] != chapter:
            raise ValueError(f"manifest chapter/key mismatch: {chapter} {key}")
    chapters = {shard["chapter"] for shard in manifest["shards"].values()}
    if chapters != set(PARTITION_CHAPTERS):
        raise ValueError(f"partition manifest mismatch: {sorted(chapters)}")
    manifest_cases = sum(shard["cases"] for shard in manifest["shards"].values())
    if manifest_cases != EXPECTED_ENDPOINT_RECORDS:
        raise ValueError(
            f"partition case-count drift: {manifest_cases} != {EXPECTED_ENDPOINT_RECORDS}"
        )

    static = json.loads(STATIC_FOOTPRINT.read_text())
    if static.get("verdict") != "PASS":
        raise ValueError("static footprint receipt is not a PASS")
    static_cafta_units = static["exact_cafta_52i_panel"]["units"]
    if static_cafta_units != 17_404:
        raise ValueError(f"static CAFTA census drift: {static_cafta_units} != 17404")
    static_exposure = static["flag_true_yale_zero_ceiling"]["per_slot"]

    baseline = json.loads(
        (REPO_ROOT / "reference/us-tariff-schedule/classification-receipt.json").read_text()
    )
    baseline_targets = {
        class_id: baseline["class_census"][class_id]
        for class_id in TARGET_CLASSES
    }
    ledger = yaml.safe_load(campaign.DISPOSITION_LEDGER.read_text())
    entries = ledger["entries"]
    target_entries = {
        entry["id"]: entry for entry in entries if entry["id"] in TARGET_CLASSES
    }
    if set(target_entries) != set(TARGET_CLASSES):
        raise ValueError("target disposition entries are missing")
    routes = campaign._routing_dispositions()
    cafta_fta_hts8, cafta_source = cafta_fta_source()

    comparisons: dict[str, Counter[str]] = {
        slot: Counter() for slot in TARGET_SLOTS
    }
    reconstructed_old: Counter[str] = Counter()
    closed: Counter[str] = Counter()
    residual: Counter[str] = Counter()
    current_classes: Counter[str] = Counter()
    new_disagreements: Counter[str] = Counter()
    cafta_residual: Counter[str] = Counter()
    cafta_heuristic: Counter[str] = Counter()
    cafta_panel_exercise: Counter[str] = Counter()
    cafta_panel_cells: set[tuple[str, ...]] = set()
    cafta_residual_cells: set[tuple[str, ...]] = set()
    static_yale_zero_flagged: Counter[str] = Counter()
    by_slot_iso: Counter[tuple[str, str]] = Counter()
    by_slot_chapter: Counter[tuple[str, str]] = Counter()
    by_slot_revision: Counter[tuple[str, str]] = Counter()
    by_slot_interval: Counter[tuple[str, str, str]] = Counter()
    by_slot_delta: Counter[tuple[str, str]] = Counter()
    cafta_by_iso: Counter[tuple[str, str]] = Counter()
    cafta_by_chapter: Counter[tuple[str, str]] = Counter()
    cafta_by_interval: Counter[tuple[str, str, str]] = Counter()
    cafta_by_delta: Counter[tuple[str, str]] = Counter()
    engine_errors = 0
    endpoint_records = 0
    target_comparisons = 0
    mismatch_cells = 0

    TARGET_MISMATCH_CELLS.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=TARGET_MISMATCH_CELLS.parent, delete=False) as raw:
        temporary = Path(raw.name)
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as zipped:
            for record in campaign._iter_eval_records(manifest):
                endpoint_records += 1
                if record["engine_errors"]:
                    engine_errors += 1
                    continue
                for row in campaign.compare_record(record):
                    slot = row["slot"]
                    if slot not in TARGET_SLOTS:
                        continue
                    target_comparisons += 1
                    comparisons[slot]["match" if row["match"] else "mismatch"] += 1
                    unit = campaign.mismatch_unit(row, routes)
                    flag_name = SLOT_FLAG[slot]
                    if (
                        unit["flags"].get(flag_name) is True
                        and row["expected"] == 0
                        and record["probe"] >= SLOT_EFFECTIVE_FROM[slot]
                    ):
                        static_yale_zero_flagged[slot] += 1
                    is_exact_cafta_panel = (
                        slot == "forced_labor_section_301"
                        and unit["iso2"] in CAFTA_ORIGINS
                        and unit["hts10"][:8] in cafta_fta_hts8
                        and unit["flags"].get(flag_name) is True
                        and row["expected"] == 0
                        and record["probe"] >= SLOT_EFFECTIVE_FROM[slot]
                    )
                    if is_exact_cafta_panel:
                        cafta_panel_exercise[unit["iso2"]] += 1
                        cafta_panel_cells.add((
                            unit["hts10"], unit["iso2"], unit["revision"],
                            *unit["interval"],
                        ))

                    old_row = dict(row)
                    old_row["actual"] = 0.0
                    old_row["delta"] = -row["expected"]
                    old_row["match"] = abs(old_row["delta"]) <= campaign.TOLERANCE
                    old_unit = campaign.mismatch_unit(old_row, routes)
                    old_class = None
                    if not old_row["match"]:
                        matched = [
                            class_id for class_id, entry in target_entries.items()
                            if campaign.selector_matches(old_unit, entry["match"])
                        ]
                        if len(matched) > 1:
                            raise ValueError(f"old target selectors overlap: {matched}")
                        old_class = matched[0] if matched else None
                    if not old_row["match"] and old_class is None:
                        raise ValueError(
                            "pre-existing target-slot mismatch has no target disposition: "
                            f"{row['case_id']} {slot}"
                        )
                    if old_class:
                        reconstructed_old[old_class] += 1
                        if row["match"]:
                            closed[old_class] += 1
                        else:
                            residual[old_class] += 1

                    if row["match"]:
                        continue
                    mismatch_cells += 1
                    signature = campaign.mismatch_signature(row)
                    current_class = campaign.matching_class_id(signature, unit, entries)
                    current_classes[current_class or "__unexplained__"] += 1
                    is_new = old_row["match"]
                    if is_new:
                        new_disagreements[slot] += 1
                        chapter = unit["hts_line"][:2]
                        delta_key = format(row["delta"], ".17g")
                        by_slot_iso[(slot, unit["iso2"])] += 1
                        by_slot_chapter[(slot, chapter)] += 1
                        by_slot_revision[(slot, unit["revision"])] += 1
                        by_slot_interval[(slot, *unit["interval"])] += 1
                        by_slot_delta[(slot, delta_key)] += 1
                    is_cafta_heuristic = (
                        is_new
                        and slot == "forced_labor_section_301"
                        and unit["iso2"] in CAFTA_ORIGINS
                        and row["delta"] > campaign.TOLERANCE
                    )
                    if is_cafta_heuristic:
                        cafta_heuristic[unit["iso2"]] += 1
                    is_cafta = is_cafta_heuristic and is_exact_cafta_panel
                    if is_cafta:
                        cafta_residual[unit["iso2"]] += 1
                        cafta_residual_cells.add((
                            unit["hts10"], unit["iso2"], unit["revision"],
                            *unit["interval"],
                        ))
                        chapter = unit["hts_line"][:2]
                        delta_key = format(row["delta"], ".17g")
                        cafta_by_iso[(slot, unit["iso2"])] += 1
                        cafta_by_chapter[(slot, chapter)] += 1
                        cafta_by_interval[(slot, *unit["interval"])] += 1
                        cafta_by_delta[(slot, delta_key)] += 1
                    payload = {
                        "case_id": row["case_id"],
                        "probe": record["probe"],
                        "slot": slot,
                        "expected": row["expected"],
                        "actual": row["actual"],
                        "delta": row["delta"],
                        "old_target_class": old_class,
                        "current_class": current_class,
                        "new_disagreement": is_new,
                        "cafta_52i_country_heuristic": is_cafta_heuristic,
                        "cafta_52i_exact": is_cafta,
                        "context": row["context"],
                    }
                    zipped.write(
                        (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
                    )
        temporary.replace(TARGET_MISMATCH_CELLS)

    if dict(reconstructed_old) != baseline_targets:
        raise ValueError(
            f"baseline target reconstruction drift: {dict(reconstructed_old)} != {baseline_targets}"
        )
    if any(closed[class_id] + residual[class_id] != units for class_id, units in baseline_targets.items()):
        raise ValueError("target closure does not conserve baseline units")
    if endpoint_records != EXPECTED_ENDPOINT_RECORDS:
        raise ValueError(
            f"evaluated endpoint-record drift: {endpoint_records} != "
            f"{EXPECTED_ENDPOINT_RECORDS}"
        )
    if engine_errors:
        raise ValueError(f"target partition contains {engine_errors} engine-error records")
    if dict(static_yale_zero_flagged) != static_exposure:
        raise ValueError(
            "runtime flag-true/Yale-zero exposure differs from static census: "
            f"{dict(static_yale_zero_flagged)} != {static_exposure}"
        )

    cafta_units = sum(cafta_residual.values())
    cafta_panel_units = sum(cafta_panel_exercise.values())
    cafta_heuristic_units = sum(cafta_heuristic.values())
    if cafta_panel_units != static_cafta_units:
        raise ValueError(
            "runtime Note 52(i) panel exercise differs from static census: "
            f"{cafta_panel_units} != {static_cafta_units}"
        )
    if len(cafta_panel_cells) != static["exact_cafta_52i_panel"]["interval_rows"]:
        raise ValueError("runtime Note 52(i) interval rows differ from static census")
    if cafta_residual_cells != cafta_panel_cells:
        raise ValueError("runtime Note 52(i) residual cells differ from panel exercise")
    if cafta_units != cafta_panel_units:
        raise ValueError(
            "exact Note 52(i) panel exercise does not equal the post-rebind residual: "
            f"{cafta_panel_units} != {cafta_units}"
        )
    new_units = sum(new_disagreements.values())
    receipt = {
        "schema": "axiom_oracles.us_tariff_schedule.preview_1311_target_classification.v1",
        "verdict": "PASS" if engine_errors == 0 else "STOP_ENGINE_ERRORS",
        "scope": {
            "chapters": list(PARTITION_CHAPTERS),
            "chapter_count": len(PARTITION_CHAPTERS),
            "endpoint_records": endpoint_records,
            "target_component_comparisons": target_comparisons,
        },
        "engine_errors": engine_errors,
        "per_slot": {slot: dict(counts) for slot, counts in comparisons.items()},
        "baseline_committed": baseline_targets,
        "baseline_reconstructed": dict(reconstructed_old),
        "post_rebind_target_units": {
            class_id: {
                "baseline": baseline_targets[class_id],
                "closed": closed[class_id],
                "residual": residual[class_id],
            }
            for class_id in TARGET_CLASSES
        },
        "current_target_mismatch_classes": dict(current_classes),
        "new_disagreements": {
            "units": new_units,
            "per_slot": dict(new_disagreements),
            "non_cafta_units": new_units - cafta_units,
            "by_slot_iso": _counter_rows(by_slot_iso, ("slot", "iso2")),
            "by_slot_chapter": _counter_rows(by_slot_chapter, ("slot", "chapter")),
            "by_slot_revision": _counter_rows(by_slot_revision, ("slot", "revision")),
            "by_slot_interval": _counter_rows(
                by_slot_interval, ("slot", "interval_from", "interval_until")
            ),
            "by_slot_delta": _counter_rows(by_slot_delta, ("slot", "delta")),
        },
        "cafta_52i_residual": {
            "units": cafta_units,
            "panel_exercise_units": cafta_panel_units,
            "panel_interval_rows": len(cafta_panel_cells),
            "per_origin": dict(sorted(cafta_residual.items())),
            "panel_per_origin": dict(sorted(cafta_panel_exercise.items())),
            "by_chapter": _counter_rows(cafta_by_chapter, ("slot", "chapter")),
            "by_interval": _counter_rows(
                cafta_by_interval, ("slot", "interval_from", "interval_until")
            ),
            "by_delta": _counter_rows(cafta_by_delta, ("slot", "delta")),
            "exact_rule": (
                "new positive forced-labor mismatch joined by HTS8 to Yale condition=fta, "
                "origin in CR/DO/SV/GT/HN/NI, Yale expected zero, C6 declared flag true, "
                "and endpoint on or after 2026-07-24"
            ),
            "source": cafta_source,
            "country_heuristic_units": cafta_heuristic_units,
            "exact_equals_country_heuristic": cafta_units == cafta_heuristic_units,
        },
        "static_flag_true_yale_zero_ceiling": dict(static_yale_zero_flagged),
        "artifacts": {
            "mismatch_cells": receipt_file(TARGET_MISMATCH_CELLS),
            "manifest": receipt_file(EVAL_MANIFEST),
            "input_contract": receipt_file(PARTITION_CONTRACT),
            "provenance": receipt_file(PROVENANCE_RECEIPT),
            "static_footprint": receipt_file(STATIC_FOOTPRINT),
        },
        "mismatch_cell_rows": mismatch_cells,
    }
    write_json(TARGET_COMPARISON, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "stage",
        choices=(
            "input-contract", "projection", "static-footprint", "evaluate",
            "target-compare-classify",
        ),
    )
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()
    configure_campaign()
    if args.stage == "input-contract":
        result = input_contract()
    elif args.stage == "projection":
        result = projection()
    elif args.stage == "static-footprint":
        result = static_footprint_census()
    elif args.stage == "evaluate":
        result = evaluate(workers=args.workers, resume=not args.no_resume)
    else:
        result = target_compare_classify()
    print(render(result), end="")
    return 0 if result.get("verdict", "PASS") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
