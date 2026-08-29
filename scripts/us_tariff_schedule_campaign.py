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
import concurrent.futures
import csv
import fcntl
import gzip
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from functools import cache
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
while str(REPO_ROOT) in sys.path:
    sys.path.remove(str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT))
SELECTED = REPO_ROOT / "reference/us-tariff-schedule/selected-intervals.csv.gz"
OUT_DIR = REPO_ROOT / "reference/us-tariff-schedule"
ROUTING_ROWS = OUT_DIR / "disposition-routing.csv.gz"
ROUTING_RECEIPT = OUT_DIR / "disposition-routing-receipt.json"
INPUT_CONTRACT_RECEIPT = OUT_DIR / "declared-input-contract-receipt.json"
EVAL_DIR = OUT_DIR / "eval"
EVAL_MANIFEST = EVAL_DIR / "MANIFEST.json"
INPUT_CONTRACT_SCHEMA = "axiom_oracles.us_tariff_schedule.declared_input_contract.v4"
EVAL_RUN_IDENTITY_SCHEMA = "axiom_oracles.us_tariff_schedule.eval_run_identity.v4"
EVAL_MANIFEST_SCHEMA = "axiom_oracles.us_tariff_schedule.eval_manifest.v3"
COMPARISON_SCHEMA = "axiom_oracles.us_tariff_schedule.comparison_summary.v3"
COMPARISON_RECEIPT = OUT_DIR / "comparison-summary.json"
CLASSIFICATION_RECEIPT = OUT_DIR / "classification-receipt.json"
DISPOSITION_LEDGER = (
    REPO_ROOT / "reference/us-tariff-schedule/campaign-dispositions.yaml"
)
PREVIEW_DISPOSITION_LINE_SETS = (
    REPO_ROOT / "reference/us-tariff-schedule/preview-disposition-line-sets.json"
)
PREVIEW_SELECTOR_TRANSITION_RECEIPT = (
    REPO_ROOT / "reference/us-tariff-schedule/preview-selector-transition-receipt.json"
)
PREVIEW_DISPOSITION_PRODUCER_SOURCES = {
    "script": REPO_ROOT / "scripts/build_us_tariff_preview_disposition_receipt.py",
    "campaign_classifier": Path(__file__).resolve(),
}
PREVIEW_SELECTOR_TRANSITION_PRODUCER_SOURCES = {
    "script": (
        REPO_ROOT / "scripts/build_us_tariff_preview_selector_transition_receipt.py"
    ),
    "campaign_classifier": Path(__file__).resolve(),
    "full_closure_guard": (
        REPO_ROOT / "scripts/build_us_tariff_section232_equivalence_receipt.py"
    ),
}
PREVIEW_SELECTOR_TRANSITION_SCHEMA = (
    "axiom_oracles.us_tariff_schedule.preview_selector_transitions.v1"
)
PREVIEW_ALL_SELECTOR_SNAPSHOT_SHA256 = (
    "4c6a0074bae1ff88ceeedc8b6e8c0b28eb829670c5a4e1a1edbb210be382dba6"
)
TRANSITION_EXPECTED_PARENT_IDS = frozenset(
    {
        "aircraft-utilization-proxy-brazil",
        "aircraft-utilization-proxy-forced-labor",
        "cafta-52i-deferred",
        "chapter98-brazil",
        "chapter98-forced-labor",
        "pharma-utilization-proxy-brazil",
        "pharma-utilization-proxy-forced-labor-035",
        "pharma-utilization-proxy-forced-labor-non035",
        "section232-annex-brazil",
        "section232-annex-forced-labor",
        "section232-exposed-brazil",
        "section232-exposed-forced-labor",
        "section232-heading-brazil",
        "section232-heading-forced-labor",
        "yale-hts8-broadening-brazil",
        "yale-parser-zero-statutory-base",
        "yale-zero-pharma-brazil",
        "yale-zero-pharma-forced-labor",
    }
)
CAFTA_SUPERSESSION_RECEIPT = (
    OUT_DIR / "cafta-reference-defect-supersession-receipt.json"
)
CAFTA_SUPERSESSION_PRODUCER = (
    REPO_ROOT / "scripts/build_us_tariff_cafta_supersession_receipt.py"
)
CAFTA_SUPERSESSION_SCHEMA = (
    "axiom_oracles.us_tariff_schedule.cafta_reference_defect_supersession.v1"
)
CAFTA_PREVIEW_SELECTOR_ID = "cafta-52i-deferred"
CAFTA_EXPECTED_UNITS = 17_404
CAFTA_EXPECTED_SIGNATURES = 8_702
CAFTA_EXPECTED_ORIGIN_UNITS = {
    "CR": 1_260,
    "DO": 128,
    "GT": 108,
    "HN": 120,
    "NI": 15_636,
    "SV": 152,
}
CAFTA_PREVIEW_SNAPSHOT_SHA256 = (
    "531fce05b3c6ac32980fb0e570140ccde0b277d674b6f107724fab76f7ee57c3"
)
CAFTA_EXPECTED_ACTUAL_CASE_FEED_PROJECTION_SHA256 = (
    "89a12b14bfd36a845a31ec6d49be68a597a4d5ae038ab75a3215ef046aa0508c"
)
CAFTA_EXPECTED_IDENTITY_POPULATION_SHA256 = (
    "1ceb489cd916d87fd6bedc4797dba33f9562a7a25869e36adde96589aba619f3"
)
CAFTA_EXPECTED_HISTORICAL_MISMATCH_PROJECTION_SHA256 = (
    "f97e554b6c638a66ab994c52668510168490304f52e38523719bef2b26cf2852"
)
CAFTA_EXPECTED_DEFECT_PROJECTION_SHA256 = (
    "d124b93308c27e42cad8cff1d944c63e6f24d67973ea44ea1d623672ade27462"
)
CAFTA_EXPECTED_RSCRIPT_RECEIPT = {
    "path": "/Library/Frameworks/R.framework/Versions/4.3-arm64/Resources/bin/Rscript",
    "bytes": 70_912,
    "sha256": "258c64ed913846b06ab5f6829de9e69a23ce8e515cc6c61a34ece40cb274a49c",
}
CAFTA_EXPECTED_R_LIBRARY = (
    "/Library/Frameworks/R.framework/Versions/4.3-arm64/Resources/library"
)
CAFTA_EXPECTED_R_RUNTIME_TREE_RECEIPT = {
    "path": "/Library/Frameworks/R.framework/Versions/4.3-arm64/Resources",
    "file_count": 8_300,
    "bytes": 357_968_262,
    "manifest_sha256": (
        "23f7ebbac8578e60c99b7dd808fcb6d268f8b479240e6760383454b32f978641"
    ),
}
CAFTA_EXPECTED_DPLYR_TREE_RECEIPT = {
    "path": f"{CAFTA_EXPECTED_R_LIBRARY}/dplyr",
    "file_count": 68,
    "bytes": 2_618_210,
    "manifest_sha256": (
        "647bc333c2efabcc6519b6c16b5b3b90fa6a0c3a2515bdf008318314f30f79fc"
    ),
}
CAFTA_TIDY_EVAL_PROGRAM = f"""
.libPaths("{CAFTA_EXPECTED_R_LIBRARY}")
dplyr_path <- normalizePath(find.package("dplyr", lib.loc = .libPaths()[1]), mustWork = TRUE)
stopifnot(identical(dplyr_path, "{CAFTA_EXPECTED_R_LIBRARY}/dplyr"))
suppressPackageStartupMessages(library(dplyr, lib.loc = .libPaths()[1]))
rule_hit <- function(condition) {{
  rr <- tibble(condition = c("full", "fta"))
  rr %>% filter(.data$condition %in% condition)
}}
selected <- rule_hit("full")$condition
cat("r_version=", paste(R.version$major, R.version$minor, sep="."), "\\n", sep="")
cat("dplyr_version=", as.character(packageVersion("dplyr")), "\\n", sep="")
cat("dplyr_path=", dplyr_path, "\\n", sep="")
cat("selected_conditions=", paste(selected, collapse=","), "\\n", sep="")
""".strip()
CAFTA_EXPECTED_TIDY_EVAL_PROGRAM_SHA256 = (
    "27f678ccd8f1486fa88b6393ecbbd50cc28d01ae87d2e3e6ab1abfd85b6c0afb"
)
CAFTA_REFERENCE_PROVENANCE = OUT_DIR / "provenance.json"
CAFTA_REFERENCE_INTEGRITY_RECEIPT = OUT_DIR / "integrity-receipt.json"
CAFTA_SELECTED_PANEL_EXTRACTOR = REPO_ROOT / "scripts/extract_us_tariff_schedule.R"
CAFTA_CAMPAIGN_EQUIVALENCE_BASIS = (
    "identical selected population plus an exact per-unit historical-to-source-"
    "evaluation-to-comparison identity and arithmetic replay"
)
CAFTA_EXPECTED_DEFINITION = {
    "bounded_conclusion": (
        "the 17,404 preview cells are a Yale reference defect caused by "
        "the pinned tidy-eval name collision under the campaign's explicitly "
        "neutral false entry facts"
    ),
    "real_entry_frontier": (
        "unchanged: the receipt proves neither GN-29(d)(v) product status nor "
        "a DR-CAFTA duty-free claim for any actual entry"
    ),
    "stable_identity": [
        "case_id",
        "slot",
        "hts10",
        "hts_line",
        "iso2",
        "revision",
        "interval",
        "origin_regime",
        "expected",
    ],
    "supersession_condition": (
        "exact immutable population and fresh identity digest; zero evaluation "
        "or comparison engine errors; both Axiom entry predicates explicitly "
        "false; every Yale zero and delta reproduced by the pinned name-collision "
        "defect; corrected statutory rates equal Axiom on every cell"
    ),
}
CAFTA_EXPECTED_RDS_SHA256 = (
    "724a0be1dce45d423d5ce599bb56f2ab81cbf78b637ba59a3287738bfc488a35"
)
CAFTA_YALE_FILE_SHA256 = {
    "config/policy_params.yaml": "5f3d79b192b9fb6079e5ad10a1969e12f397567fc9f89d4e202403116ecb6346",
    "resources/mfn_exemption_shares.csv": "9505d04e441386ac08348de663c151743fdf3c537947cbe7ceab43b4d21381e1",
    "resources/s232_pharma_products.csv": "eb5f888ef3967c699b4f85618859d3556a9552e7d636ead2bbdc09256edcca04",
    "resources/s301fl_final_common_exemptions.csv": "15b5e352cd810af33b90699bb595010f5aca43ea10de25ba1b2c6239acc96054",
    "resources/s301fl_final_country_exemptions.csv": "a38f8e42e9615b58dc09fd8a661b4a0fdb9d12e2121342a657fae69450215280",
    "src/model/authority_adapter.R": "91d6adab284dc823fa4c541910d6c4a74494b3a09f3e5fb6b6a71a98e3b1288a",
    "src/pipeline/06_calculate_rates.R": "2620a122159c11cc2b116786925ccbc6d801cb274982034cd8105657ae13a76a",
}
CAFTA_YALE_ADAPTER_SOURCE_PROOF = {
    "rate_and_type_resolvers_first_line": 391,
    "rate_and_type_resolvers_sha256": "b4b03adb11756fd9ff2dda56313c0aea5dddf4511e0c1d65a1f2ce19caf05ebf",
    "exemption_resolver_first_line": 435,
    "exemption_resolver_sha256": "0237e0ee3978687f967b8cdaabbb3c4721984aac7899a4ee36bb7e294bf06869",
    "authority_builder_first_line": 485,
    "authority_builder_sha256": "06d6b8a59363f668fa2bcae8a35e157241b19fc1e8a254fd41dfa0f99b1db805",
}
CAFTA_YALE_SOURCE_PROOF_HASHES = {
    "rule_hit_function_sha256": "3257ccacb37c6d7ced57e112a3f0fc63015758df50afb5e08646790e6f617d3a",
    "rule_hit_use_site_sha256": "ccd1a2de00c1747444734437acb2567d59c43e39047f05ba98c21791ce52a61f",
    "statutory_capture_and_preference_scaling_sha256": "28ad1849ca43d61431e282b090b465e518da98978f90d143627815b50e57cd1c",
    "use_conditioned_scaling_sha256": "3093f85841b5209701730688ab822677928ad10e1c2b3a6d479fa274332534e0",
    "chapter98_precapture_transforms_sha256": "9950e34ca8d3bbd481985b04ffdf80ae828247df62155b0eb6ce773c26208e2b",
}
TRANSITION_UNCONDITIONAL_PRECEDENCE_FLAGS = (
    "entry_is_section_232_covered",
    "entry_is_s232_copper_primary_member",
    "entry_is_s232_copper_additional_member",
    "entry_is_s232_note37_softwood_member",
    "entry_is_s232_note37_upholstered_wood_furniture_member",
    "entry_is_s232_note38_mhd_vehicle_member",
    "entry_is_s232_note38_bus_member",
)
TRANSITION_CANDIDATE_PRECEDENCE_FLAGS = (
    "entry_is_s232_note33_vehicle_candidate",
    "entry_is_s232_note33_auto_part_candidate",
    "entry_is_s232_note37_cabinet_vanity_candidate",
    "entry_is_s232_note38_mhd_part_candidate",
    "entry_is_s232_note39_semiconductor_candidate",
    "entry_is_s232_note40_pharmaceutical_candidate",
)
TRANSITION_DECLARED_PRECEDENCE_FLAGS = (
    "entry_qualifies_for_note33_vehicle_heading_listed_in_notes_50_52",
    "entry_is_note33_g_automobile_part",
    "entry_qualifies_for_note33_certified_auto_part_heading_listed_in_notes_50_52",
    "entry_is_note33_auto_part_subject_to_import_adjustment_offset",
    "entry_is_note37_f_completed_kitchen_cabinet_vanity_or_part",
    "entry_is_note38_i_medium_or_heavy_duty_vehicle_part",
    "entry_qualifies_for_note38_certified_mhd_part_heading_listed_in_notes_50_52",
    "entry_is_note38_mhd_part_subject_to_import_adjustment_offset",
    "entry_qualifies_for_note39_heading_9903_79_01",
    "entry_is_note40_patented_pharmaceutical_article",
)
TRANSITION_NOTE16_MEMBERSHIP_FLAGS = (
    "entry_is_s232_note16_c_ii_derivative_aluminum_member",
    "entry_is_s232_note16_c_vi_derivative_aluminum_candidate",
    "entry_is_s232_note16_c_ix_derivative_aluminum_candidate",
)
TRANSITION_ANNEX_PATTERNS = (
    (),
    ("entry_is_s232_note33_auto_part_candidate",),
    ("entry_is_s232_note38_mhd_part_candidate",),
    (
        "entry_is_s232_note33_auto_part_candidate",
        "entry_is_s232_note38_mhd_part_candidate",
    ),
)
TRANSITION_HEADING_PATTERNS = (
    ("entry_is_s232_note33_vehicle_candidate",),
    ("entry_is_s232_note33_auto_part_candidate",),
    ("entry_is_s232_note37_cabinet_vanity_candidate",),
    ("entry_is_s232_note38_mhd_part_candidate",),
    (
        "entry_is_s232_note33_auto_part_candidate",
        "entry_is_s232_note38_mhd_part_candidate",
    ),
)
TRANSITION_PATTERN_SLUGS = {
    (): "yale-reference-defect",
    ("entry_is_s232_note33_vehicle_candidate",): "vehicle-candidate",
    ("entry_is_s232_note33_auto_part_candidate",): "auto-part-candidate",
    ("entry_is_s232_note37_cabinet_vanity_candidate",): "cabinet-vanity-candidate",
    ("entry_is_s232_note38_mhd_part_candidate",): "mhd-part-candidate",
    (
        "entry_is_s232_note33_auto_part_candidate",
        "entry_is_s232_note38_mhd_part_candidate",
    ): "auto-and-mhd-part-candidates",
}
TRANSITION_SECTION232_EXPOSED_PARENTS = frozenset(
    {"section232-exposed-brazil", "section232-exposed-forced-labor"}
)
TRANSITION_YALE_PARSER_RECEIPT = {
    "path": "scripts/parse_annex_products.R",
    "bytes": 11_189,
    "sha256": "8d560897f85d60ee2c2e1d3025a6b9bdd7406e67621aed428abe957ad1cf4bb6",
}
TRANSITION_YALE_PREVIEW_SOURCE_FILES = (
    "resources/s232_annex_products.csv",
    "resources/s232_derivative_products.csv",
    "src/model/data_loaders.R",
)
TRANSITION_YALE_CLASSIFICATION_PRECEDENCE = [
    "latest-effective direct annex row per normalized prefix",
    "longest-prefix direct match",
    "longest-prefix legacy derivative fallback only when direct is absent",
]
TRANSITION_EXPECTED_LEGACY_DERIVATIVE_FALLBACK_HTS10 = frozenset(
    {"9401999030", "9401999040", "9401999085"}
)
PREVIEW_HISTORICAL_TARGET_PATH = (
    "reference/us-tariff-schedule/preview-1311/target-mismatch-cells.jsonl.gz"
)
YALE_NOTE16_WEIGHT_ASSUMPTION = (
    REPO_ROOT / "reference/us-tariff-schedule/yale-note16-metal-weight-assumption.json"
)
YALE_NOTE16_WEIGHT_ASSUMPTION_PRODUCER = (
    REPO_ROOT / "scripts/build_us_tariff_yale_note16_weight_assumption.py"
)
YALE_NOTE16_WEIGHT_ASSUMPTION_SCHEMA = (
    "axiom_oracles.us_tariff_schedule.yale_note16_weight_assumption.v1"
)
NOTE16_WEIGHT_INPUT = (
    "entry_has_at_least_fifteen_percent_aggregate_applicable_listed_metal_weight"
)
NOTE16_WEIGHT_REFERENCE_VALUE = True
PREVIEW_DISPOSITION_INPUT_SHA256 = {
    "reference/us-tariff-schedule/preview-1311/mismatch-taxonomy-receipt.json": "3d1a7543d738d6e396e111ff909c245f082146aeeeeef27d57a5da38f30e25de",
    "reference/us-tariff-schedule/preview-1311/new-mismatch-cells.jsonl.gz": "7e26a7e746abd4d033b8dcc6b7d95efcece45b1405ac84238011500c84bbe029",
    "reference/us-tariff-schedule/preview-1311/old-residual-taxonomy-receipt.json": "b4f9d26d5a800cf1b0e6e50c6b3935ee18b24ca55bbcc5eecf9e10ab8f829bea",
    "reference/us-tariff-schedule/preview-1311/target-mismatch-cells.jsonl.gz": "d5b53173afe489686aff86a4d1d776bf821cb97945e9ebacd5ba6bc912a8b705",
    "reference/us-tariff-schedule/preview-1311/unmapped-cause-audit-receipt.json": "4572f1a121848337bcd0ea797c09e771fc55a3e0efaeb79c195979ddb5a5e29e",
    "reference/us-tariff-schedule/selected-intervals.csv.gz": "94af0a2b36c7cde0840220810791672ae494da38f288fd1cb3de1a122eb91826",
}
PREVIEW_YALE_COMMIT = "c4307e514196618afcbf88cf7fd33746417eeabf"
PREVIEW_YALE_TREE = "d3107eae32ae7ac366b319abd4ab7b13c78d5c3c"
YALE_NOTE16_WEIGHT_SOURCE_RECEIPTS = {
    "config/policy_params.yaml": {
        "path": "config/policy_params.yaml",
        "bytes": 50577,
        "sha256": ("5f3d79b192b9fb6079e5ad10a1969e12f397567fc9f89d4e202403116ecb6346"),
    },
    "docs/assumptions.md": {
        "path": "docs/assumptions.md",
        "bytes": 37812,
        "sha256": ("e2b65a9641895156c9e3fa1e06c05866e3cfdfb04075b26bee5117c0357f0dbf"),
    },
    "src/pipeline/06_calculate_rates.R": {
        "path": "src/pipeline/06_calculate_rates.R",
        "bytes": 179892,
        "sha256": ("2620a122159c11cc2b116786925ccbc6d801cb274982034cd8105657ae13a76a"),
    },
}
PREVIEW_SELECTOR_COUNT = 18
REPORT_PATH = REPO_ROOT / "conformance/detail/us-tariff-schedule.json"
WITNESS_REPLAY_RECEIPT = OUT_DIR / "witness-replay-execute-receipt.json"
CACHE_ROOT = Path(
    os.environ.get("AXIOM_TARIFF_C1_CACHE", "~/PolicyEngine/_tariff-p5/c1-cache")
).expanduser()
EVAL_PROJECTION_RECEIPT = OUT_DIR / "evaluation-projection-receipt.json"
SCHEMA = "axiom_oracles.us_tariff_schedule.disposition_routing.v1"
DISPOSITIONS = {
    "ad_valorem",
    "free",
    "specific",
    "compound",
    "component",
    "conditional",
    "empty",
}
COMPARABLE = {"ad_valorem", "free"}
COLUMN2_ORIGINS = {"CU", "KP", "BY", "RU"}
# The pinned table generator's explicit structural census: a statistical row
# with no rated ancestor.  It is not silently inferred from a failed lookup.
EXPECTED_UNOWNED = {"9802009100"}
COMPONENT_SLOTS = (
    "ieepa",
    "section_201",
    "section_122",
    "section_232_aluminum",
    "section_232_steel",
    "section_338",
    "china_section_301",
    "brazil_section_301",
    "forced_labor_section_301",
)
BASE_DEPENDENT_COMPONENTS = ("ieepa", "forced_labor_section_301")
EXPECTED_DROPPED_ENTRY_FLAGS = frozenset({"entry_is_line_c", "entry_is_line_e"})
CORE_CASE_FEED_INPUTS = frozenset({"country_of_origin", "hts_line", "hts_number"})
# C6 emits these historical aliases alongside the compiled compositions'
# canonical ``*_listed`` inputs.  The campaign consumes one canonical surface:
# aliases must agree exactly with their targets and are then removed before
# contract comparison or case construction.
ENTRY_FLAG_ALIASES = {
    "entry_is_brazil_301": "entry_is_brazil_301_listed",
    "entry_is_forced_labor_301": "entry_is_forced_labor_301_listed",
}
NEUTRAL_BOOLEAN_INPUTS = (
    "article_is_potash",
    "cbp_agrees_chapter_98_entry_is_appropriate",
    "entry_is_9802_excepted_entry",
    "entry_is_chapter_98_subchapter_xxiii_entry",
    "entry_is_entered_free_of_duty_under_dr_cafta",
    "entry_is_entered_free_of_duty_under_usmca",
    "entry_is_general_note_29_d_v_textile_or_apparel_good",
    "entry_is_humanitarian_donation_article",
    "entry_is_informational_material_article",
    "entry_is_personal_use_accompanied_baggage",
    "entry_is_properly_claimed_chapter_98_entry",
    "entry_is_usmca_duty_free_entry",
    "entry_loaded_and_in_transit_before_july_24_2026",
)
PROBE_BOOLEAN_INPUTS = ("entry_is_within_temporary_surcharge_effective_period",)
TEMPORARY_SURCHARGE_FIRST_DAY = date(2026, 2, 24)
TEMPORARY_SURCHARGE_LAST_DAY = date(2026, 7, 23)
PROBE_BOOLEAN_INPUT_CONTRACT = {
    "entry_is_within_temporary_surcharge_effective_period": {
        "derivation": "probe date is inside the inclusive effective-day interval",
        "effective_from": TEMPORARY_SURCHARGE_FIRST_DAY.isoformat(),
        "effective_through": TEMPORARY_SURCHARGE_LAST_DAY.isoformat(),
        "source_rule": (
            "us:policies/usitc/us-tariff-duty/overlays/section-122/"
            "proclamation#temporary_import_surcharge_applies"
        ),
    }
}
# Chapter 99a/99b have no flat column-2 table.  The input is intentionally
# absent: query planning excludes base-dependent outputs for column-2 origins,
# while non-column-2 cases take the other branch.  It must never be synthesized
# as zero.
CONDITIONALLY_UNFED_INPUTS_BY_CHAPTER = {
    "99a": frozenset({"resolved_non_ad_valorem_column2_rate"}),
    "99b": frozenset({"resolved_non_ad_valorem_column2_rate"}),
}
CONDITIONALLY_UNFED_INPUT_SEMANTICS = {
    "resolved_non_ad_valorem_column2_rate": (
        "No flat column-2 table exists for chapter 99a/99b. Column-2 cases "
        "are restricted to base-independent component outputs; non-column-2 "
        "cases take the General-rate branch. Never synthesize a zero value."
    )
}
OUTPUT_NAMES = (
    "mfn_ad_valorem_rate",
    "ieepa_component_rate",
    "section_201_component_rate",
    "section_122_component_rate",
    "section_232_aluminum_component_rate",
    "section_232_steel_component_rate",
    "section_338_component_rate",
    "china_section_301_component_rate",
    "brazil_section_301_component_rate",
    "forced_labor_section_301_component_rate",
    "schedule_statutory_stack",
)
TOLERANCE = 1e-12
_DELTA_VALUE_SETS: dict[int, tuple[list[float], frozenset[float]]] = {}
SELECTOR_FIELDS = frozenset(
    {
        "slot",
        "origin_regime",
        "revision",
        "delta",
        "disposition",
        "line_class",
        "iso2",
        "line_set",
        "date",
    }
)
NON_SLOT_SELECTOR_FIELDS = frozenset(
    {"origin_regime", "delta", "iso2", "line_set", "date"}
)
RULESPEC_US_ROOT = Path(
    os.environ.get(
        "RULESPEC_US_CHECKOUT",
        "/Users/maxghenis/TheAxiomFoundation/_b1wt/rulespec-us-b16",
    )
).expanduser()
DEFAULT_ENGINE_BINARY = Path(
    "/Users/maxghenis/TheAxiomFoundation/axiom-rules-engine-pinned/target/release/axiom-rules-engine"
)
CAMPAIGN_EVALUATOR_SOURCES = (
    "axiom_oracles/__init__.py",
    "axiom_oracles/adapters/__init__.py",
    "axiom_oracles/adapters/axiom/__init__.py",
    "axiom_oracles/adapters/axiom/_snap_co_base_inputs.py",
    "axiom_oracles/adapters/axiom/runner.py",
    "axiom_oracles/adapters/axiom/snap_co_projection.py",
    "axiom_oracles/adapters/axiom/tax_projection.py",
    "axiom_oracles/comparison/__init__.py",
    "axiom_oracles/comparison/comparator.py",
    "axiom_oracles/comparison/mappings.py",
    "axiom_oracles/comparison/report.py",
    "axiom_oracles/config/concept_mappings.yaml",
    "axiom_oracles/core/__init__.py",
    "axiom_oracles/core/case.py",
    "axiom_oracles/core/engine.py",
    "axiom_oracles/core/geography.py",
    "axiom_oracles/core/household.py",
    "axiom_oracles/core/results.py",
    "axiom_oracles/engine_compat.py",
)
INCIDENCE_ROOT = RULESPEC_US_ROOT / "us/policies/usitc/us-tariff-incidence/generated"
CH98_LINES = INCIDENCE_ROOT.parent.parent / "us-tariff-duty/lines/generated/ch98.yaml"
EXPECTED_COLUMNS = (
    "statutory_base_rate",
    "statutory_rate_232",
    "statutory_rate_ieepa_recip",
    "statutory_rate_ieepa_fent",
    "statutory_rate_301",
    "statutory_rate_301_cs",
    "statutory_rate_s301fl",
    "statutory_rate_s301br",
    "statutory_rate_s338",
    "statutory_rate_s122",
    "statutory_rate_section_201",
    "statutory_rate_other",
)
SLOT_OUTPUTS = {
    "base": ("mfn_ad_valorem_rate",),
    "ieepa": ("ieepa_component_rate",),
    "section_122": ("section_122_component_rate",),
    "section_201": ("section_201_component_rate",),
    "section_232": (
        "section_232_aluminum_component_rate",
        "section_232_steel_component_rate",
    ),
    "china_section_301": ("china_section_301_component_rate",),
    "brazil_section_301": ("brazil_section_301_component_rate",),
    "forced_labor_section_301": ("forced_labor_section_301_component_rate",),
    "section_338": ("section_338_component_rate",),
}
EXPECTED_SLOT_COLUMNS = {
    "base": ("statutory_base_rate",),
    "ieepa": ("statutory_rate_ieepa_recip", "statutory_rate_ieepa_fent"),
    "section_122": ("statutory_rate_s122",),
    "section_201": ("statutory_rate_section_201",),
    "section_232": ("statutory_rate_232",),
    "china_section_301": ("statutory_rate_301",),
    "brazil_section_301": ("statutory_rate_s301br",),
    "forced_labor_section_301": ("statutory_rate_s301fl",),
    "section_338": ("statutory_rate_s338",),
}
AUTHORITY_SLOTS = tuple(slot for slot in SLOT_OUTPUTS if slot != "base")
BASE_INDEPENDENT_AUTHORITY_SLOTS = (
    "section_201",
    "section_122",
    "section_232",
    "section_338",
    "china_section_301",
    "brazil_section_301",
)


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


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, allow_nan=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def _file_receipt(path: Path, *, relative_to: Path | None = None) -> dict[str, Any]:
    resolved = path.resolve()
    _require(resolved.is_file(), f"missing producer source: {resolved}")
    rendered_path = (
        str(resolved.relative_to(relative_to.resolve()))
        if relative_to is not None
        else str(resolved)
    )
    return {
        "path": rendered_path,
        "bytes": resolved.stat().st_size,
        "sha256": _sha256(resolved),
    }


def _directory_tree_receipt(path: Path) -> dict[str, Any]:
    """Commit to every regular file in an installed runtime package tree."""

    resolved = path.resolve()
    _require(resolved.is_dir(), f"missing runtime package tree: {resolved}")
    files = sorted(item for item in resolved.rglob("*") if item.is_file())
    total_bytes = 0
    manifest = hashlib.sha256()
    for item in files:
        size = item.stat().st_size
        total_bytes += size
        manifest.update(
            (
                f"{item.relative_to(resolved).as_posix()}\t{size}\t{_sha256(item)}\n"
            ).encode()
        )
    return {
        "path": str(resolved),
        "file_count": len(files),
        "bytes": total_bytes,
        "manifest_sha256": manifest.hexdigest(),
    }


def _yale_note16_weight_assumption() -> dict[str, Any]:
    """Validate the explicit Yale point-estimate bridge for Note 16(c).

    The receipt deliberately distinguishes a reference-model assumption from a
    transaction-level metal-weight fact.  Its boolean is consumed only behind
    the independently derived Note 16(c)(vi)/(ix) candidate predicates.
    """

    _require(
        YALE_NOTE16_WEIGHT_ASSUMPTION.is_file(),
        "Yale Note 16 metal-weight assumption receipt is missing",
    )
    receipt = json.loads(YALE_NOTE16_WEIGHT_ASSUMPTION.read_text())
    expected_fields = {
        "schema",
        "verdict",
        "producer",
        "yale_source",
        "configuration",
        "model_implementation",
        "campaign_binding",
        "receipt_payload_sha256",
    }
    _require(
        isinstance(receipt, dict)
        and set(receipt) == expected_fields
        and receipt.get("schema") == YALE_NOTE16_WEIGHT_ASSUMPTION_SCHEMA
        and receipt.get("verdict") == "PASS",
        "Yale Note 16 metal-weight assumption receipt is malformed",
    )
    received_digest = receipt.get("receipt_payload_sha256")
    digest_payload = dict(receipt)
    digest_payload.pop("receipt_payload_sha256", None)
    _require(
        received_digest == _canonical_sha256(digest_payload),
        "Yale Note 16 metal-weight assumption payload digest drift",
    )
    _require(
        receipt.get("producer")
        == _file_receipt(YALE_NOTE16_WEIGHT_ASSUMPTION_PRODUCER, relative_to=REPO_ROOT),
        "Yale Note 16 metal-weight assumption producer drift",
    )
    yale_source = receipt.get("yale_source")
    _require(
        yale_source
        == {
            "commit": PREVIEW_YALE_COMMIT,
            "tree": PREVIEW_YALE_TREE,
            "files": YALE_NOTE16_WEIGHT_SOURCE_RECEIPTS,
        },
        "Yale Note 16 metal-weight assumption source drift",
    )
    _require(
        receipt.get("configuration")
        == {
            "threshold": 0.15,
            "applies_to": ["annex_1b", "annex_3"],
            "excludes_chapters": ["72", "73", "74", "76"],
            "aggregate_share": 0.0,
        },
        "Yale Note 16 metal-weight assumption configuration drift",
    )
    _require(
        receipt.get("model_implementation")
        == {
            "below_threshold_route_is_share_scaled": True,
            "route_executes_only_when_aggregate_share_is_positive": True,
            "baseline_below_threshold_share": 0.0,
            "baseline_at_or_above_threshold_share": 1.0,
        },
        "Yale Note 16 metal-weight assumption implementation drift",
    )
    binding = receipt.get("campaign_binding")
    _require(
        isinstance(binding, dict)
        and binding.get("input") == NOTE16_WEIGHT_INPUT
        and binding.get("value") is NOTE16_WEIGHT_REFERENCE_VALUE
        and "reference-model assumption only" in binding.get("factual_status", "")
        and "candidate" in binding.get("scope", ""),
        "Yale Note 16 metal-weight campaign binding drift",
    )
    return receipt


def _yale_note16_weight_assumption_identity() -> dict[str, Any]:
    receipt = _yale_note16_weight_assumption()
    return {
        **_file_receipt(YALE_NOTE16_WEIGHT_ASSUMPTION, relative_to=REPO_ROOT),
        "schema": receipt["schema"],
        "receipt_payload_sha256": receipt["receipt_payload_sha256"],
        "campaign_binding": receipt["campaign_binding"],
        "yale_commit": receipt["yale_source"]["commit"],
        "yale_tree": receipt["yale_source"]["tree"],
    }


def _campaign_evaluator_identity() -> dict[str, Any]:
    """Bind the Python implementation that constructs and parses engine runs.

    Importing ``AxiomRulesRunner`` executes the listed package modules, while
    ``run_cases`` consults the concept mapping before invoking the engine.  A
    receipt for the campaign script alone would therefore allow adapter,
    compatibility, result-parsing, or mapping changes to reuse old shards.
    """

    sources = [
        _file_receipt(REPO_ROOT / relative, relative_to=REPO_ROOT)
        for relative in CAMPAIGN_EVALUATOR_SOURCES
    ]
    identity = {
        "campaign": _file_receipt(Path(__file__), relative_to=REPO_ROOT),
        "oracle_sources": sources,
        "python": {
            "executable": _file_receipt(Path(sys.executable)),
            "version": sys.version,
        },
        "pyyaml_version": yaml.__version__,
    }
    identity["producer_sha256"] = _canonical_sha256(identity)
    return identity


def _git_output(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def _rulespec_root_identity(rulespec_root: Path) -> dict[str, Any]:
    """Bind the exact RuleSpec checkout, including non-committed content."""

    root = rulespec_root.resolve()
    _require(root.is_dir(), f"RuleSpec root is missing: {root}")
    top = Path(
        _git_output(root, "rev-parse", "--show-toplevel").decode().strip()
    ).resolve()
    _require(
        top == root, f"RuleSpec root must be the git worktree root: {root} != {top}"
    )
    head = _git_output(root, "rev-parse", "HEAD").decode().strip()
    tree = _git_output(root, "rev-parse", "HEAD^{tree}").decode().strip()
    tracked_diff = _git_output(root, "diff", "--no-ext-diff", "--binary", "HEAD", "--")
    untracked_names = [
        item.decode()
        for item in _git_output(
            root, "ls-files", "--others", "--exclude-standard", "-z"
        ).split(b"\0")
        if item
    ]
    untracked = []
    for name in sorted(untracked_names):
        path = root / name
        if path.is_symlink():
            material = os.readlink(path).encode()
            kind = "symlink"
        else:
            _require(path.is_file(), f"unsupported untracked RuleSpec path: {name}")
            material = path.read_bytes()
            kind = "file"
        untracked.append(
            {
                "path": name,
                "kind": kind,
                "bytes": len(material),
                "sha256": hashlib.sha256(material).hexdigest(),
            }
        )
    content = {
        "head_tree": tree,
        "tracked_worktree_diff_sha256": hashlib.sha256(tracked_diff).hexdigest(),
        "untracked": untracked,
    }
    return {
        "root": str(root),
        "head_commit": head,
        "head_tree": tree,
        "dirty": bool(tracked_diff or untracked),
        "tracked_worktree_diff_sha256": content["tracked_worktree_diff_sha256"],
        "untracked": untracked,
        "content_sha256": _canonical_sha256(content),
    }


def _load_entry_flag_tool(
    rulespec_root: Path,
) -> tuple[Any, dict[str, Any]]:
    """Load the entry preparer from one explicit checkout and receipt its inputs."""

    root = rulespec_root.resolve()
    source = root / "tools/b16_entry_flags.py"
    tool_receipt = _file_receipt(source, relative_to=root)
    module_name = (
        "_axiom_tariff_entry_flags_"
        + hashlib.sha256((str(source) + tool_receipt["sha256"]).encode()).hexdigest()
    )
    spec = importlib.util.spec_from_file_location(module_name, source)
    _require(
        spec is not None and spec.loader is not None,
        f"cannot load entry-flag producer: {source}",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    entry_flags = getattr(module, "entry_flags", None)
    module_names = getattr(module, "MODULES", None)
    note16_aluminum_precedence_module = getattr(
        module, "NOTE16_ALUMINUM_PRECEDENCE_MODULE", None
    )
    incidence_dir = getattr(module, "INCIDENCE_DIR", None)
    _require(callable(entry_flags), "entry-flag producer lacks entry_flags")
    _require(
        isinstance(module_names, tuple)
        and module_names
        and all(isinstance(name, str) and name for name in module_names),
        "entry-flag producer MODULES is malformed",
    )
    _require(
        isinstance(note16_aluminum_precedence_module, str)
        and bool(note16_aluminum_precedence_module),
        "entry-flag producer NOTE16_ALUMINUM_PRECEDENCE_MODULE is malformed",
    )
    expected_incidence = root / "us/policies/usitc/us-tariff-incidence/generated"
    _require(
        isinstance(incidence_dir, Path)
        and incidence_dir.resolve() == expected_incidence.resolve(),
        "entry-flag producer incidence root escaped the requested checkout",
    )
    dependency_paths = [expected_incidence / name for name in module_names]
    # b16_entry_flags._note16_aluminum_precedence_tables() loads this
    # effective-dated table separately from MODULES.  It affects every
    # Note 16(c) entry classification, so bind it to the same producer digest
    # that flows through the input contract, run identity, and eval manifest.
    dependency_paths.append(expected_incidence / note16_aluminum_precedence_module)
    # b16_entry_flags._tables() also consumes every non-test per-page Note 50
    # and Note 52 fragment.  Receipt the exact dynamic inputs, not only the
    # top-level MODULES tuple.
    for directory in ("note50", "note52"):
        dependency_paths.extend(
            path
            for path in sorted((expected_incidence / directory).glob("page-*.yaml"))
            if not path.name.endswith(".test.yaml")
        )
    _require(
        len(dependency_paths) == len(set(dependency_paths)),
        "entry-flag producer dependency paths are duplicated",
    )
    dependencies = [_file_receipt(path, relative_to=root) for path in dependency_paths]
    provenance = {
        "tool": tool_receipt,
        "dependencies": dependencies,
        "producer_sha256": _canonical_sha256(
            {
                "tool": tool_receipt,
                "dependencies": dependencies,
            }
        ),
    }
    return entry_flags, provenance


def signature_population_sha256(population: Iterable[tuple[str, int]]) -> str:
    """Hash a selector's exact mismatch-signature population and multiplicities."""

    normalized: list[list[str | int]] = []
    seen: set[str] = set()
    for signature, units in population:
        _require(
            isinstance(signature, str)
            and re.fullmatch(r"[0-9a-f]{64}", signature) is not None,
            "selector population contains an invalid mismatch signature",
        )
        _require(
            signature not in seen, "selector population contains a duplicate signature"
        )
        _require(
            isinstance(units, int) and not isinstance(units, bool) and units > 0,
            "selector population contains an invalid multiplicity",
        )
        seen.add(signature)
        normalized.append([signature, units])
    normalized.sort(key=lambda item: item[0])
    return hashlib.sha256(
        json.dumps(
            normalized, allow_nan=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def _collect_artifact_inputs(node: Any, inputs: set[str]) -> None:
    """Collect the engine's compiled input surface, including input-or-else."""
    if isinstance(node, list):
        for item in node:
            _collect_artifact_inputs(item, inputs)
    elif isinstance(node, dict):
        if node.get("kind") in {"input", "input_or_else"}:
            name = node.get("name")
            _require(isinstance(name, str) and name, "compiled input has no name")
            inputs.add(name)
        for value in node.values():
            _collect_artifact_inputs(value, inputs)


def declared_inputs_from_artifact(path: Path) -> frozenset[str]:
    payload = json.loads(path.read_text())
    program = payload.get("program")
    _require(isinstance(program, dict), f"{path}: compiled artifact has no program")
    inputs: set[str] = set()
    _collect_artifact_inputs(program, inputs)
    _require(inputs, f"{path}: compiled artifact declares no inputs")
    return frozenset(inputs)


def reachable_inputs_from_artifact(
    path: Path, output_names: Iterable[str]
) -> frozenset[str]:
    """Collect inputs in the all-version dependency closure of campaign outputs."""

    payload = json.loads(path.read_text())
    program = payload.get("program")
    _require(isinstance(program, dict), f"{path}: compiled artifact has no program")
    derived = program.get("derived")
    _require(
        isinstance(derived, list), f"{path}: compiled artifact has no derived rules"
    )
    by_name = {
        rule.get("name"): rule
        for rule in derived
        if isinstance(rule, dict) and isinstance(rule.get("name"), str)
    }
    requested = tuple(output_names)
    _require(
        set(requested) <= set(by_name),
        f"{path}: campaign outputs absent from artifact: {sorted(set(requested) - set(by_name))}",
    )
    inputs: set[str] = set()
    visited: set[str] = set()

    def visit_expression(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                visit_expression(item)
            return
        if not isinstance(node, dict):
            return
        kind = node.get("kind")
        if kind in {"input", "input_or_else"}:
            name = node.get("name")
            _require(isinstance(name, str) and name, "compiled input has no name")
            inputs.add(name)
        elif kind == "derived":
            name = node.get("name")
            _require(
                isinstance(name, str) and name in by_name,
                f"{path}: unresolved derived dependency {name!r}",
            )
            visit_rule(name)
        for value in node.values():
            visit_expression(value)

    def visit_rule(name: str) -> None:
        if name in visited:
            return
        visited.add(name)
        rule = by_name[name]
        visit_expression(rule.get("expr"))
        versions = rule.get("versions", [])
        _require(isinstance(versions, list), f"{path}: malformed versions for {name}")
        for version in versions:
            _require(isinstance(version, dict), f"{path}: malformed version for {name}")
            visit_expression(version.get("expr"))

    for name in requested:
        visit_rule(name)
    return frozenset(inputs)


def canonicalize_entry_flags(
    raw_flags: dict[str, Any],
) -> tuple[dict[str, bool], tuple[str, ...]]:
    """Validate and remove C6 aliases before campaign input consumption."""

    flags = {
        name: value for name, value in raw_flags.items() if name.startswith("entry_")
    }
    malformed = sorted(name for name, value in flags.items() if type(value) is not bool)
    _require(not malformed, f"entry flags must be boolean: {malformed}")
    observed = []
    for alias, canonical in ENTRY_FLAG_ALIASES.items():
        if alias not in flags:
            continue
        _require(
            canonical in flags,
            f"entry-flag alias {alias} was emitted without canonical {canonical}",
        )
        _require(
            flags[alias] == flags[canonical],
            f"entry-flag alias disagreement: {alias} != {canonical}",
        )
        observed.append(alias)
        del flags[alias]
    return flags, tuple(sorted(observed))


def _probe_boolean_inputs(probe: str) -> dict[str, bool]:
    probe_day = date.fromisoformat(probe)
    return {
        "entry_is_within_temporary_surcharge_effective_period": (
            TEMPORARY_SURCHARGE_FIRST_DAY <= probe_day <= TEMPORARY_SURCHARGE_LAST_DAY
        )
    }


def _case_feed_input_names(emitted_flag_names: Iterable[str]) -> frozenset[str]:
    return frozenset(
        CORE_CASE_FEED_INPUTS
        | set(NEUTRAL_BOOLEAN_INPUTS)
        | set(PROBE_BOOLEAN_INPUTS)
        | (set(emitted_flag_names) - EXPECTED_DROPPED_ENTRY_FLAGS)
    )


def _case_feed_contract(
    *,
    chapter: str,
    declared_inputs: Iterable[str],
    reachable_inputs: Iterable[str],
    emitted_flag_names: Iterable[str],
) -> dict[str, Any]:
    """Validate and describe the exact input surface supplied by the campaign."""

    declared = frozenset(declared_inputs)
    reachable = frozenset(reachable_inputs)
    emitted = frozenset(emitted_flag_names)
    case_feed_inputs = _case_feed_input_names(emitted)
    dropped = emitted - declared
    _require(
        dropped == EXPECTED_DROPPED_ENTRY_FLAGS,
        f"chapter {chapter}: dropped entry flags changed: {sorted(dropped)}",
    )
    undeclared = case_feed_inputs - declared
    _require(
        not undeclared,
        f"chapter {chapter}: case-feed inputs are undeclared: {sorted(undeclared)}",
    )
    declared_entry_inputs = frozenset(
        name for name in declared if name.startswith("entry_")
    )
    missing_entry_inputs = declared_entry_inputs - case_feed_inputs
    _require(
        not missing_entry_inputs,
        f"chapter {chapter}: declared entry inputs absent from feed: {sorted(missing_entry_inputs)}",
    )
    conditionally_unfed = CONDITIONALLY_UNFED_INPUTS_BY_CHAPTER.get(
        chapter, frozenset()
    )
    missing_reachable = reachable - case_feed_inputs
    _require(
        missing_reachable == conditionally_unfed,
        f"chapter {chapter}: reachable unfed inputs changed: expected "
        f"{sorted(conditionally_unfed)}, got {sorted(missing_reachable)}",
    )
    return {
        "case_feed_inputs": sorted(case_feed_inputs),
        "declared_entry_inputs": sorted(declared_entry_inputs),
        "declared_entry_flags": sorted(declared & emitted),
        "reachable_campaign_inputs": sorted(reachable),
        "conditionally_unfed_reachable_inputs": sorted(conditionally_unfed),
        "dropped_entry_flags": sorted(dropped),
        "missing_declared_entry_inputs": [],
        "missing_reachable_inputs": [],
    }


def filter_declared_feed(
    feed: dict[str, Any],
    declared_inputs: Iterable[str],
    *,
    emitted_flag_names: Iterable[str],
    expected_dropped_flags: frozenset[str] = EXPECTED_DROPPED_ENTRY_FLAGS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fail-closed projection of one case feed onto its compiled input surface.

    Only surplus fields emitted by the entry-flag tool may be projected away.
    Every field in the receipted campaign case-feed contract must already be
    present: the engine supports
    ``input_or_else`` defaults, but this campaign deliberately does not rely on
    them because an accidentally unfed declared input must remain observable.
    """
    declared = frozenset(declared_inputs)
    supplied = frozenset(feed)
    emitted = frozenset(emitted_flag_names)
    dropped = supplied - declared
    missing = declared - supplied
    _require(
        dropped <= emitted,
        f"undeclared non-flag inputs in feed: {sorted(dropped - emitted)}",
    )
    _require(
        dropped == expected_dropped_flags,
        f"dropped entry flags changed: expected {sorted(expected_dropped_flags)}, got {sorted(dropped)}",
    )
    _require(not missing, f"declared inputs absent from feed: {sorted(missing)}")
    filtered = {name: value for name, value in feed.items() if name in declared}
    return filtered, {
        "declared_input_count": len(declared),
        "supplied_input_count": len(supplied),
        "forwarded_input_count": len(filtered),
        "dropped_entry_flags": sorted(dropped),
        "missing_declared_inputs": sorted(missing),
        "absent_declared_input_semantics": (
            "STOP in harness before engine; engine input_or_else can substitute its "
            "per-reference default, while a strict input raises MissingInput"
        ),
    }


def _engine_environment(
    rulespec_root: Path, base: dict[str, str] | None = None
) -> dict[str, str]:
    """Make legacy engine fallback resolve the same explicit RuleSpec root."""

    env = dict(os.environ if base is None else base)
    env.pop("AXIOM_RULESPEC_ROOT", None)
    env["AXIOM_RULESPEC_REPO_ROOTS"] = str(rulespec_root.resolve().parent)
    return env


def _engine_subprocess_runner(rulespec_root: Path) -> Any:
    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        kwargs["env"] = _engine_environment(rulespec_root, kwargs.get("env"))
        return subprocess.run(command, **kwargs)

    return run


def build_input_contract_receipt(
    *, rulespec_root: Path, engine_binary: Path
) -> dict[str, Any]:
    """Compile all generated compositions and receipt their entry-flag surface."""
    rulespec_root = rulespec_root.resolve()
    engine_binary = engine_binary.resolve()
    rulespec_identity = _rulespec_root_identity(rulespec_root)
    engine_receipt = _file_receipt(engine_binary)
    entry_flags, entry_flag_producers = _load_entry_flag_tool(rulespec_root)

    reference_assumption = _yale_note16_weight_assumption_identity()
    raw_emitted = entry_flags(
        102294000,
        "0102294024",
        "CA",
        entry_date="2026-07-24",
        **{NOTE16_WEIGHT_INPUT: NOTE16_WEIGHT_REFERENCE_VALUE},
    )
    emitted, observed_aliases = canonicalize_entry_flags(raw_emitted)
    # The tool also returns incidence diagnostics (``s232_*``, list-specific
    # helpers).  The harness feeds only its public entry-input namespace.
    emitted_names = frozenset(emitted)
    modules = sorted(
        path
        for path in (
            rulespec_root / "us/policies/cbp/us-tariff-schedule/generated"
        ).glob("ch*/ch*.yaml")
        if not path.name.endswith(".test.yaml")
    )
    _require(
        len(modules) == 100,
        f"expected 100 generated compositions, found {len(modules)}",
    )
    env = _engine_environment(rulespec_root)
    chapters = []
    with tempfile.TemporaryDirectory(prefix="tariff-input-contract-") as raw:
        work = Path(raw)
        for index, module in enumerate(modules):
            artifact = work / f"chapter-{index:03d}.json"
            subprocess.run(
                [
                    str(engine_binary),
                    "compile",
                    "--program",
                    str(module.resolve()),
                    "--output",
                    str(artifact),
                ],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            declared = declared_inputs_from_artifact(artifact)
            reachable = reachable_inputs_from_artifact(artifact, OUTPUT_NAMES)
            chapter = module.parent.name.removeprefix("ch")
            feed_contract = _case_feed_contract(
                chapter=chapter,
                declared_inputs=declared,
                reachable_inputs=reachable,
                emitted_flag_names=emitted_names,
            )
            chapters.append(
                {
                    "chapter": chapter,
                    "module": str(module.relative_to(rulespec_root)),
                    "module_sha256": _sha256(module),
                    "artifact_sha256": _sha256(artifact),
                    "declared_input_count": len(declared),
                    **feed_contract,
                    "missing_declared_entry_flags": [],
                }
            )
    receipt = {
        "schema": INPUT_CONTRACT_SCHEMA,
        "rulespec": rulespec_identity,
        "engine": engine_receipt,
        "entry_flag_producers": entry_flag_producers,
        "composition_count": len(chapters),
        "entry_flag_tool": str(
            (rulespec_root / "tools/b16_entry_flags.py").relative_to(rulespec_root)
        ),
        "entry_flag_tool_sha256": _sha256(rulespec_root / "tools/b16_entry_flags.py"),
        "entry_flag_aliases": dict(ENTRY_FLAG_ALIASES),
        "observed_entry_flag_aliases": list(observed_aliases),
        "emitted_entry_flags": sorted(emitted_names),
        "reference_assumptions": {
            "yale_note16_metal_weight": reference_assumption,
        },
        "expected_dropped_entry_flags": sorted(EXPECTED_DROPPED_ENTRY_FLAGS),
        "neutral_boolean_inputs": list(NEUTRAL_BOOLEAN_INPUTS),
        "neutral_boolean_value": False,
        "probe_boolean_inputs": PROBE_BOOLEAN_INPUT_CONTRACT,
        "conditionally_unfed_inputs_by_chapter": {
            chapter: sorted(inputs)
            for chapter, inputs in CONDITIONALLY_UNFED_INPUTS_BY_CHAPTER.items()
        },
        "conditionally_unfed_input_semantics": CONDITIONALLY_UNFED_INPUT_SEMANTICS,
        "absent_declared_input_semantics": {
            "harness": "STOP before engine execution",
            "engine_strict_input": "MissingInput",
            "engine_input_or_else": "substitutes the compiled per-reference default",
            "campaign_policy": "never default a declared case-feed input silently",
        },
        "chapters": chapters,
        "verdict": "PASS",
    }
    _require(
        _rulespec_root_identity(rulespec_root) == rulespec_identity,
        "RuleSpec checkout changed during input-contract compilation",
    )
    _require(
        _file_receipt(engine_binary) == engine_receipt,
        "engine binary changed during input-contract compilation",
    )
    _require(
        _load_entry_flag_tool(rulespec_root)[1] == entry_flag_producers,
        "entry-flag producers changed during input-contract compilation",
    )
    return receipt


def _chapter_table_paths(rulespec_root: Path) -> list[Path]:
    directory = rulespec_root / "us/policies/usitc/us-tariff-duty/lines/generated"
    paths = sorted(
        path
        for path in directory.glob("ch*.yaml")
        if not path.name.endswith(".test.yaml")
    )
    _require(
        len(paths) == 100, f"expected 100 generated chapter tables, found {len(paths)}"
    )
    return paths


def _rule_values(payload: dict, name: str) -> dict[int, str]:
    rules = [rule for rule in payload.get("rules", []) if rule.get("name") == name]
    _require(len(rules) == 1, f"expected exactly one {name} rule")
    versions = rules[0].get("versions", [])
    _require(
        len(versions) == 1 and isinstance(versions[0].get("values"), dict),
        f"bad {name} values",
    )
    values = {int(key): str(value) for key, value in versions[0]["values"].items()}
    _require(
        values and set(values.values()) <= DISPOSITIONS, f"invalid {name} disposition"
    )
    return values


def load_tables(
    rulespec_root: Path,
) -> tuple[dict[str, dict[int, tuple[str, str]]], list[dict[str, Any]]]:
    tables: dict[str, dict[int, tuple[str, str]]] = {}
    sources = []
    for path in _chapter_table_paths(rulespec_root):
        shard = path.stem.removeprefix("ch")
        payload = yaml.safe_load(path.read_text())
        general = _rule_values(payload, f"ch{shard}_general_disposition")
        column2 = _rule_values(payload, f"ch{shard}_column2_disposition")
        _require(set(general) == set(column2), f"ch{shard} disposition keysets differ")
        tables[shard] = {key: (general[key], column2[key]) for key in general}
        sources.append(
            {"path": str(path.relative_to(rulespec_root)), "sha256": _sha256(path)}
        )
    return tables, sources


def verify_component_formulas(rulespec_root: Path) -> dict[str, Any]:
    """Prove generated authority components do not query base or total."""
    directory = rulespec_root / "us/policies/cbp/us-tariff-schedule/generated"
    paths = sorted(
        path
        for path in directory.glob("ch*/ch*.yaml")
        if not path.name.endswith(".test.yaml")
    )
    _require(
        len(paths) == 100, f"expected 100 generated compositions, found {len(paths)}"
    )
    digest = hashlib.sha256()
    checked = 0
    forbidden = (
        "mfn_ad_valorem_rate",
        "schedule_base_general_rate",
        "schedule_statutory_stack",
    )
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
    _require(
        dependent == set(BASE_DEPENDENT_COMPONENTS),
        f"component/base dependency inventory changed: {sorted(dependent)}",
    )
    return {
        "generated_compositions": len(paths),
        "component_formulas_checked": checked,
        "composition_hash_aggregate": digest.hexdigest(),
        "base_or_total_required_by_component": sorted(dependent),
    }


def route_member(
    hts10: str, tables: dict[str, dict[int, tuple[str, str]]]
) -> tuple[str, int, str, str]:
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
    _require(
        len(best) == 1, f"ambiguous generated disposition route for {hts10}: {best}"
    )
    key, shard, general, column2 = best[0]
    return shard, key, general, column2


def query_plan(
    disposition: str, *, column2_rate_available: bool = True
) -> dict[str, Any]:
    _require(disposition in DISPOSITIONS, f"unknown disposition {disposition!r}")
    comparable = disposition in COMPARABLE and column2_rate_available
    reason = (
        None
        if comparable
        else (
            f"non_ad_valorem_base:{disposition}"
            if disposition not in COMPARABLE
            else "structurally_unavailable:column2_rate"
        )
    )
    compared_components = list(
        AUTHORITY_SLOTS if comparable else BASE_INDEPENDENT_AUTHORITY_SLOTS
    )
    excluded_components = [] if comparable else ["ieepa", "forced_labor_section_301"]
    return {
        "base": "compare" if comparable else "known_not_comparable",
        "total": "compare" if comparable else "known_not_comparable",
        "reason": reason,
        "components": compared_components,
        "excluded_components": excluded_components,
        "component_exclusion_reason": None
        if comparable
        else "requires_noncomparable_base",
    }


def _selected_rows(path: Path) -> Iterable[dict[str, str]]:
    with gzip.open(path, "rt", newline="") as source:
        yield from csv.DictReader(source)


def build_prepass(
    *, rulespec_root: Path, selected_path: Path = SELECTED
) -> tuple[list[dict[str, str]], dict[str, Any]]:
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
        output_rows.append(
            {
                "hts10": member,
                "chapter_shard": shard,
                "hts_line": f"{line:010d}",
                "general_disposition": general,
                "column2_disposition": column2,
            }
        )

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
        cell_counts[
            "full_comparison" if plan["base"] == "compare" else "components_only"
        ] += 1
        if not column2_available and disposition in COMPARABLE:
            cell_counts["structurally_unavailable_column2"] += 1

    excluded = cell_counts["components_only"]
    receipt = {
        "schema": SCHEMA,
        "selected_source": {
            "path": str(selected_path.relative_to(REPO_ROOT)),
            "sha256": _sha256(selected_path),
        },
        "rulespec_tables": sources,
        "routing_rows": len(output_rows),
        "evaluated_cells": total,
        "full_comparison_cells": cell_counts["full_comparison"],
        "non_ad_valorem_components_only_cells": excluded,
        "non_ad_valorem_share": excluded / total,
        "structurally_unavailable_column2_cells": cell_counts[
            "structurally_unavailable_column2"
        ],
        "base_dependent_component_excluded_slots": excluded
        * len(BASE_DEPENDENT_COMPONENTS),
        "selected_disposition_counts": dict(sorted(disposition_counts.items())),
        "scope_statement": (
            f"{excluded} of {total} evaluated cells carry a non-ad-valorem statutory base "
            "and are compared on authority components only"
        ),
        "component_formula_contract": {
            "queried_for_every_cell": [
                slot
                for slot in COMPONENT_SLOTS
                if slot not in BASE_DEPENDENT_COMPONENTS
            ],
            "queried_only_with_comparable_base": list(BASE_DEPENDENT_COMPONENTS),
            **formula_receipt,
        },
    }
    _require(
        total > 0
        and sum(cell_counts[k] for k in ("full_comparison", "components_only"))
        == total,
        "disposition routing does not conserve selected cells",
    )
    return output_rows, receipt


def write_prepass(rows: list[dict[str, str]], receipt: dict[str, Any]) -> None:
    # gzip mtime=0 makes the content-addressed routing artifact reproducible.
    with ROUTING_ROWS.open("wb") as raw:
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0
        ) as compressed:
            with io.TextIOWrapper(compressed, newline="") as target:
                writer = csv.DictWriter(target, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
    receipt["routing_artifact"] = {
        "path": str(ROUTING_ROWS.relative_to(REPO_ROOT)),
        "sha256": _sha256(ROUTING_ROWS),
    }
    ROUTING_RECEIPT.write_text(_render(receipt))


def _routing_by_member() -> dict[str, dict[str, str]]:
    with gzip.open(ROUTING_ROWS, "rt", newline="") as source:
        rows = list(csv.DictReader(source))
    _require(len(rows) == 20_508, f"routing member count changed: {len(rows)}")
    return {row["hts10"]: row for row in rows}


def _probe_dates(row: dict[str, str]) -> tuple[str, ...]:
    start = date.fromisoformat(row["clipped_from"])
    end = date.fromisoformat(row["clipped_until"])
    _require(start <= end, f"inverted clipped interval: {row}")
    return (
        (start.isoformat(),) if start == end else (start.isoformat(), end.isoformat())
    )


def _first_shard_cases(
    *, rulespec_root: Path, limit: int, case_feed_inputs: Iterable[str]
) -> tuple[list[Any], list[str]]:
    """Build the deterministic timing shard using only full-comparison cells."""
    from axiom_oracles.core.case import Case

    entry_flags, _provenance = _load_entry_flag_tool(rulespec_root)

    routes = _routing_by_member()
    chapter = "01"
    module = f"us:policies/cbp/us-tariff-schedule/generated/ch{chapter}/ch{chapter}"
    outputs = [f"{module}#{name}" for name in OUTPUT_NAMES]
    cases = []
    for row in _selected_rows(SELECTED):
        route = routes[row["hts10"]]
        if route["chapter_shard"] != chapter:
            continue
        disposition = (
            route["column2_disposition"]
            if row["iso2"] in COLUMN2_ORIGINS
            else route["general_disposition"]
        )
        if disposition not in COMPARABLE:
            continue
        for probe in _probe_dates(row):
            feed, _flags = _case_feed(
                row,
                route,
                entry_flags,
                probe=probe,
                case_feed_inputs=case_feed_inputs,
            )
            cases.append(
                Case(
                    case_id=f"{row['hts10']}-{row['country']}-{probe}",
                    period=probe,
                    metadata={
                        "axiom_entity": "CustomsEntry",
                        "axiom_entity_id": "entry",
                        "axiom_inputs": {
                            f"{module}#input.{name}": value
                            for name, value in feed.items()
                        },
                    },
                    outputs=tuple(outputs),
                )
            )
            if len(cases) == limit:
                return cases, outputs
    raise ValueError(
        f"chapter {chapter} has only {len(cases)} timing cases; need {limit}"
    )


def evaluate_projection(
    *, rulespec_root: Path, engine_binary: Path, limit: int = 5_001
) -> dict[str, Any]:
    """Run and deterministically replay the first shard, then enforce 16 hours."""
    from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner

    contract = _validated_input_contract(
        rulespec_root=rulespec_root, engine_binary=engine_binary
    )
    chapter_contract = next(
        item for item in contract["chapters"] if item["chapter"] == "01"
    )
    cases, outputs = _first_shard_cases(
        rulespec_root=rulespec_root,
        limit=limit,
        case_feed_inputs=chapter_contract["case_feed_inputs"],
    )
    program = (
        rulespec_root / "us/policies/cbp/us-tariff-schedule/generated/ch01/ch01.yaml"
    )
    runs = []
    value_hashes = []
    for _replay in range(2):
        started = time.perf_counter()
        runner = AxiomRulesRunner(
            program_path=program,
            binary_path=engine_binary,
            default_entity="CustomsEntry",
            default_entity_id="entry",
            rulespec_repo_roots=(rulespec_root,),
            batch_size=limit,
            subprocess_run=_engine_subprocess_runner(rulespec_root),
        )
        results = runner.run_cases(cases, outputs)
        elapsed = time.perf_counter() - started
        errors = [result for result in results if result.errors]
        if errors:
            raise ValueError(f"first shard engine errors: {errors[0].errors}")
        canonical = _render(
            [
                {"case_id": str(result.household_id), "values": result.values}
                for result in results
            ]
        ).encode()
        value_hashes.append(hashlib.sha256(canonical).hexdigest())
        runs.append({"engine_wall_clock_seconds": elapsed, "case_count": len(results)})
    _require(
        len(set(value_hashes)) == 1, f"first-shard determinism failure: {value_hashes}"
    )
    selected_cells = json.loads(ROUTING_RECEIPT.read_text())["evaluated_cells"]
    endpoint_upper_bound = selected_cells * 2
    projected_seconds = (
        max(run["engine_wall_clock_seconds"] for run in runs)
        * endpoint_upper_bound
        / limit
        / 3
    )
    receipt = {
        "schema": "axiom_oracles.us_tariff_schedule.evaluation_projection.v1",
        "chapter_shard": "01",
        "batch_cases": limit,
        "replay_runs": runs,
        "result_sha256": value_hashes[0],
        "deterministic": True,
        "selected_interval_cells": selected_cells,
        "endpoint_case_upper_bound": endpoint_upper_bound,
        "maximum_concurrent_engine_processes": 3,
        "projection_method": "slowest replay seconds/case * two-endpoint upper bound / 3 workers",
        "projected_engine_seconds": projected_seconds,
        "projected_engine_hours": projected_seconds / 3600,
        "ceiling_hours": 16,
        "verdict": "PASS"
        if projected_seconds <= 16 * 3600
        else "STOP_16H_PROJECTION_BREACH",
    }
    EVAL_PROJECTION_RECEIPT.write_text(_render(receipt))
    return receipt


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = _render(payload)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as target:
        target.write(rendered)
        temporary = Path(target.name)
    temporary.replace(path)


@contextmanager
def _bound_gzip_text_source(
    path: Path, expected_sha256: str
) -> Iterator[io.TextIOBase]:
    """Yield gzip text from the same stable file descriptor that was hashed."""

    def descriptor_sha256(source: io.BufferedReader) -> str:
        source.seek(0)
        digest = hashlib.sha256()
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
        return digest.hexdigest()

    with path.open("rb") as raw:
        before = os.fstat(raw.fileno())
        _require(
            descriptor_sha256(raw) == expected_sha256,
            "comparison artifact hash mismatch",
        )
        raw.seek(0)
        with gzip.GzipFile(fileobj=raw, mode="rb") as compressed:
            with io.TextIOWrapper(compressed) as source:
                yield source
        after = os.fstat(raw.fileno())
        stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        _require(
            all(
                getattr(before, field) == getattr(after, field)
                for field in stable_fields
            )
            and descriptor_sha256(raw) == expected_sha256,
            "comparison artifact changed during classification scan",
        )
    _require(
        path.is_file() and _sha256(path) == expected_sha256,
        "comparison artifact changed after classification scan",
    )


def _install_classification_sidecar(temporary: Path, destination: Path) -> str:
    """Install exactly the sidecar bytes produced by this classification run."""

    produced_sha256 = _sha256(temporary)
    temporary.replace(destination)
    _require(
        destination.is_file() and _sha256(destination) == produced_sha256,
        "classification sidecar changed during production",
    )
    return produced_sha256


@contextmanager
def _eval_manifest_lock() -> Iterator[None]:
    """Serialize every manifest transition across campaign processes."""

    lock_path = EVAL_MANIFEST.with_name(f".{EVAL_MANIFEST.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _new_eval_generation_id() -> str:
    return uuid.uuid4().hex


def _valid_eval_generation_id(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value) is not None


def _validated_input_contract(
    *,
    rulespec_root: Path,
    engine_binary: Path,
    rulespec_identity: dict[str, Any] | None = None,
    engine_receipt: dict[str, Any] | None = None,
    entry_flag_producers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _require(INPUT_CONTRACT_RECEIPT.is_file(), "declared-input contract is missing")
    contract = json.loads(INPUT_CONTRACT_RECEIPT.read_text())
    _require(
        contract.get("schema") == INPUT_CONTRACT_SCHEMA,
        "declared-input contract schema is stale; regenerate input-contract",
    )
    rulespec_root = rulespec_root.resolve()
    engine_binary = engine_binary.resolve()
    rulespec_identity = rulespec_identity or _rulespec_root_identity(rulespec_root)
    engine_receipt = engine_receipt or _file_receipt(engine_binary)
    entry_flag_producers = (
        entry_flag_producers or _load_entry_flag_tool(rulespec_root)[1]
    )
    _require(
        contract.get("rulespec") == rulespec_identity,
        "declared-input contract RuleSpec provenance is stale",
    )
    _require(
        contract.get("engine") == engine_receipt,
        "declared-input contract engine provenance is stale",
    )
    _require(
        contract.get("entry_flag_producers") == entry_flag_producers,
        "declared-input contract entry-flag provenance is stale",
    )
    _require(
        contract.get("entry_flag_tool_sha256")
        == entry_flag_producers["tool"]["sha256"],
        "declared-input contract entry-flag tool hash is stale",
    )
    _require(
        contract.get("neutral_boolean_inputs") == list(NEUTRAL_BOOLEAN_INPUTS)
        and contract.get("neutral_boolean_value") is False,
        "declared-input contract neutral-input semantics are stale",
    )
    _require(
        contract.get("probe_boolean_inputs") == PROBE_BOOLEAN_INPUT_CONTRACT,
        "declared-input contract probe-input semantics are stale",
    )
    _require(
        contract.get("reference_assumptions")
        == {"yale_note16_metal_weight": (_yale_note16_weight_assumption_identity())},
        "declared-input contract reference-assumption semantics are stale",
    )
    expected_conditionally_unfed = {
        chapter: sorted(inputs)
        for chapter, inputs in CONDITIONALLY_UNFED_INPUTS_BY_CHAPTER.items()
    }
    _require(
        contract.get("conditionally_unfed_inputs_by_chapter")
        == expected_conditionally_unfed,
        "declared-input contract conditional-input semantics are stale",
    )
    _require(
        contract.get("conditionally_unfed_input_semantics")
        == CONDITIONALLY_UNFED_INPUT_SEMANTICS,
        "declared-input contract conditional-input rationale is stale",
    )
    emitted = contract.get("emitted_entry_flags")
    _require(
        isinstance(emitted, list)
        and all(isinstance(name, str) and name for name in emitted),
        "declared-input contract emitted entry flags are malformed",
    )
    expected_case_feed_inputs = sorted(_case_feed_input_names(emitted))
    chapters = contract.get("chapters")
    _require(
        isinstance(chapters, list)
        and contract.get("composition_count") == len(chapters) == 100,
        "declared-input contract chapter census is stale",
    )
    expected_modules = sorted(
        path
        for path in (
            rulespec_root / "us/policies/cbp/us-tariff-schedule/generated"
        ).glob("ch*/ch*.yaml")
        if not path.name.endswith(".test.yaml")
    )
    _require(
        len(expected_modules) == 100,
        f"expected 100 generated compositions, found {len(expected_modules)}",
    )
    by_chapter: dict[str, dict[str, Any]] = {}
    for chapter in chapters:
        _require(isinstance(chapter, dict), "malformed input-contract chapter")
        name = chapter.get("chapter")
        _require(
            isinstance(name, str) and name not in by_chapter,
            f"duplicate or malformed input-contract chapter: {name!r}",
        )
        module = _module_path(rulespec_root, name)
        _require(
            chapter.get("module") == str(module.relative_to(rulespec_root))
            and chapter.get("module_sha256") == _sha256(module),
            f"declared-input contract module provenance is stale: {name}",
        )
        _require(
            isinstance(chapter.get("artifact_sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", chapter["artifact_sha256"]) is not None,
            f"declared-input contract artifact hash is malformed: {name}",
        )
        _require(
            chapter.get("case_feed_inputs") == expected_case_feed_inputs
            and chapter.get("missing_declared_entry_inputs") == []
            and chapter.get("missing_reachable_inputs") == []
            and chapter.get("conditionally_unfed_reachable_inputs")
            == expected_conditionally_unfed.get(name, []),
            f"declared-input contract case-feed surface is stale: {name}",
        )
        _require(
            set(chapter.get("declared_entry_inputs", []))
            <= set(chapter["case_feed_inputs"]),
            f"declared-input contract omits public entry inputs: {name}",
        )
        by_chapter[name] = chapter
    _require(
        set(by_chapter)
        == {path.parent.name.removeprefix("ch") for path in expected_modules},
        "declared-input contract chapter set is stale",
    )
    _require(contract.get("verdict") == "PASS", "declared-input contract is not PASS")
    return contract


def _current_run_identity(
    *, rulespec_root: Path, engine_binary: Path
) -> dict[str, Any]:
    """Derive the complete content identity used by evaluation and comparison."""

    _require_rulespec_root_consistency(rulespec_root)
    rulespec_root = rulespec_root.resolve()
    engine_binary = engine_binary.resolve()
    rulespec_identity = _rulespec_root_identity(rulespec_root)
    engine_receipt = _file_receipt(engine_binary)
    _entry_flags, entry_flag_producers = _load_entry_flag_tool(rulespec_root)
    contract = _validated_input_contract(
        rulespec_root=rulespec_root,
        engine_binary=engine_binary,
        rulespec_identity=rulespec_identity,
        engine_receipt=engine_receipt,
        entry_flag_producers=entry_flag_producers,
    )
    chapters = {
        item["chapter"]: {
            "module": item["module"],
            "module_sha256": item["module_sha256"],
            "compiled_artifact_sha256": item["artifact_sha256"],
            "case_feed_inputs": item["case_feed_inputs"],
            "conditionally_unfed_reachable_inputs": item[
                "conditionally_unfed_reachable_inputs"
            ],
        }
        for item in contract["chapters"]
    }
    return {
        "schema": EVAL_RUN_IDENTITY_SCHEMA,
        "rulespec": rulespec_identity,
        "engine": engine_receipt,
        "entry_flag_producers": entry_flag_producers,
        "input_contract": {
            **_file_receipt(INPUT_CONTRACT_RECEIPT, relative_to=REPO_ROOT),
            "schema": contract["schema"],
        },
        "reference_assumptions": contract["reference_assumptions"],
        "campaign_evaluator": _campaign_evaluator_identity(),
        "selected_population": _file_receipt(SELECTED, relative_to=REPO_ROOT),
        "routing": _file_receipt(ROUTING_ROWS, relative_to=REPO_ROOT),
        "outputs": list(OUTPUT_NAMES),
        "chapters": chapters,
    }


def _run_identity_sha256(run_identity: dict[str, Any]) -> str:
    return _canonical_sha256(run_identity)


def _empty_eval_manifest(
    run_identity: dict[str, Any] | None = None,
    generation_id: str | None = None,
) -> dict[str, Any]:
    manifest: dict[str, Any] = {"schema": EVAL_MANIFEST_SCHEMA, "shards": {}}
    if run_identity is not None:
        _require(
            _valid_eval_generation_id(generation_id),
            "evaluation manifest requires a valid generation id",
        )
        manifest["run_identity"] = run_identity
        manifest["run_identity_sha256"] = _run_identity_sha256(run_identity)
        manifest["generation_id"] = generation_id
    return manifest


def _load_manifest() -> dict[str, Any]:
    if not EVAL_MANIFEST.exists():
        return _empty_eval_manifest()
    payload = json.loads(EVAL_MANIFEST.read_text())
    _require(payload.get("schema") == EVAL_MANIFEST_SCHEMA, "bad eval manifest schema")
    _require(isinstance(payload.get("shards"), dict), "bad eval manifest shards")
    return payload


def _prepare_eval_manifest(
    manifest: dict[str, Any],
    current_keys: dict[str, str],
    run_identity: dict[str, Any],
    generation_id: str,
) -> dict[str, Any]:
    """Drop downstream bindings and shards superseded by current inputs.

    Shard keys commit the RuleSpec module, engine, selected population, routing,
    outputs, and declared-input contract.  Carrying a non-current key into a
    rebind would leave two receipts for one chapter and make comparison order
    dependent.  Comparison bindings are downstream evidence and are likewise
    invalid as soon as a new evaluation begins.
    """

    _require(
        _valid_eval_generation_id(generation_id),
        "evaluation manifest requires a valid generation id",
    )
    prepared = _empty_eval_manifest(run_identity, generation_id)
    run_identity_sha256 = _run_identity_sha256(run_identity)
    if (
        manifest.get("run_identity") != run_identity
        or manifest.get("run_identity_sha256") != run_identity_sha256
        or manifest.get("generation_id") != generation_id
    ):
        return prepared
    expected_by_key = {key: chapter for chapter, key in current_keys.items()}
    for key, shard in manifest["shards"].items():
        if key not in expected_by_key:
            continue
        chapter = expected_by_key[key]
        _require(isinstance(shard, dict), f"invalid shard receipt {key}")
        _require(
            shard.get("key") == key
            and shard.get("chapter") == chapter
            and shard.get("run_identity_sha256") == run_identity_sha256
            and shard.get("generation_id") == generation_id,
            f"invalid shard identity {key}",
        )
        prepared["shards"][key] = shard
    return prepared


def _chapter_from_route(route: dict[str, str]) -> str:
    return route["chapter_shard"]


def _case_feed(
    row: dict[str, str],
    route: dict[str, str],
    entry_flags: Any,
    *,
    probe: str,
    case_feed_inputs: Iterable[str],
) -> tuple[dict[str, Any], dict[str, bool]]:
    raw_flags = entry_flags(
        int(route["hts_line"]),
        row["hts10"],
        row["iso2"],
        entry_date=probe,
        **{NOTE16_WEIGHT_INPUT: NOTE16_WEIGHT_REFERENCE_VALUE},
    )
    public_flags, _aliases = canonicalize_entry_flags(raw_flags)
    reserved = (
        CORE_CASE_FEED_INPUTS | set(NEUTRAL_BOOLEAN_INPUTS) | set(PROBE_BOOLEAN_INPUTS)
    )
    overlap = set(public_flags) & reserved
    _require(
        not overlap,
        f"entry-flag producer overlaps campaign-owned inputs: {sorted(overlap)}",
    )
    unfiltered_feed = {
        "hts_line": int(route["hts_line"]),
        "hts_number": row["hts10"],
        "country_of_origin": row["iso2"],
        **{name: False for name in NEUTRAL_BOOLEAN_INPUTS},
        **_probe_boolean_inputs(probe),
        **public_flags,
    }
    feed, _receipt = filter_declared_feed(
        unfiltered_feed,
        case_feed_inputs,
        emitted_flag_names=public_flags,
    )
    flags = {key: value for key, value in public_flags.items() if key in feed}
    return feed, flags


def _case_id(row: dict[str, str], probe: str, ordinal: int) -> str:
    identity = "|".join(
        (
            row["hts10"],
            row["country"],
            row["revision"],
            row["clipped_from"],
            row["clipped_until"],
            probe,
            str(ordinal),
        )
    )
    return "schedule-" + hashlib.sha256(identity.encode()).hexdigest()[:24]


def _chapter_records(chapter: str) -> Iterator[dict[str, Any]]:
    routes = _routing_by_member()
    for row in _selected_rows(SELECTED):
        route = routes[row["hts10"]]
        if _chapter_from_route(route) != chapter:
            continue
        disposition = (
            route["column2_disposition"]
            if row["iso2"] in COLUMN2_ORIGINS
            else route["general_disposition"]
        )
        column2_available = not (
            row["iso2"] in COLUMN2_ORIGINS and route["chapter_shard"] in {"99a", "99b"}
        )
        plan = query_plan(disposition, column2_rate_available=column2_available)
        for ordinal, probe in enumerate(_probe_dates(row)):
            yield {
                "row": row,
                "route": route,
                "plan": plan,
                "probe": probe,
                "ordinal": ordinal,
            }


def _module_path(rulespec_root: Path, chapter: str) -> Path:
    return (
        rulespec_root
        / f"us/policies/cbp/us-tariff-schedule/generated/ch{chapter}/ch{chapter}.yaml"
    )


def _shard_key(
    *, chapter: str, run_identity: dict[str, Any], generation_id: str
) -> str:
    _require(
        _valid_eval_generation_id(generation_id),
        "shard key requires a valid generation id",
    )
    chapter_identity = run_identity.get("chapters", {}).get(chapter)
    _require(
        isinstance(chapter_identity, dict), f"unknown run-identity chapter: {chapter}"
    )
    ingredients = {
        "chapter": chapter,
        "chapter_identity": chapter_identity,
        "generation_id": generation_id,
        "run_identity_sha256": _run_identity_sha256(run_identity),
    }
    return _canonical_sha256(ingredients)


def _current_shard_keys(
    run_identity: dict[str, Any], generation_id: str
) -> dict[str, str]:
    chapters = run_identity.get("chapters")
    _require(
        isinstance(chapters, dict) and chapters,
        "evaluation run identity has no chapters",
    )
    return {
        chapter: _shard_key(
            chapter=chapter,
            run_identity=run_identity,
            generation_id=generation_id,
        )
        for chapter in chapters
    }


def _result_values(result: Any, requested: Iterable[str]) -> dict[str, float]:
    values = {}
    for key, value in result.values.items():
        short = key.rsplit("#", 1)[-1]
        _require(short in OUTPUT_NAMES, f"unexpected engine output {key}")
        number = float(value)
        _require(
            number == number and abs(number) != float("inf"),
            f"non-finite engine output {key}",
        )
        values[short] = number
    _require(
        set(values) == set(requested),
        f"missing engine outputs: {sorted(set(requested) - set(values))}",
    )
    return values


def _evaluate_chapter(
    chapter: str,
    *,
    rulespec_root: Path,
    engine_binary: Path,
    cache_dir: Path,
    run_identity: dict[str, Any],
    generation_id: str,
    expected_key: str,
) -> dict[str, Any]:
    from axiom_oracles.adapters.axiom import runner as runner_module
    from axiom_oracles.core import case as case_module

    _require(
        Path(runner_module.__file__).resolve()
        == (REPO_ROOT / "axiom_oracles/adapters/axiom/runner.py").resolve()
        and Path(case_module.__file__).resolve()
        == (REPO_ROOT / "axiom_oracles/core/case.py").resolve(),
        "campaign evaluator imports resolve outside the receipted checkout",
    )
    AxiomRulesRunner = runner_module.AxiomRulesRunner
    Case = case_module.Case

    entry_flags, entry_flag_producers = _load_entry_flag_tool(rulespec_root)
    _require(
        entry_flag_producers == run_identity.get("entry_flag_producers"),
        f"chapter {chapter}: entry-flag producer drift before evaluation",
    )

    started = time.perf_counter()

    records = list(_chapter_records(chapter))
    chapter_identity = run_identity.get("chapters", {}).get(chapter)
    _require(
        isinstance(chapter_identity, dict),
        f"chapter {chapter}: run identity has no chapter contract",
    )
    case_feed_inputs = chapter_identity.get("case_feed_inputs")
    _require(
        isinstance(case_feed_inputs, list),
        f"chapter {chapter}: run identity has no case-feed surface",
    )
    module_ref = f"us:policies/cbp/us-tariff-schedule/generated/ch{chapter}/ch{chapter}"
    cases: dict[str, list[Any]] = {"full": [], "components": []}
    contexts: dict[str, list[Any]] = {"full": [], "components": []}
    for record in records:
        feed, flags = _case_feed(
            record["row"],
            record["route"],
            entry_flags,
            probe=record["probe"],
            case_feed_inputs=case_feed_inputs,
        )
        case_id = _case_id(record["row"], record["probe"], record["ordinal"])
        group = "full" if record["plan"]["base"] == "compare" else "components"
        if (
            chapter in CONDITIONALLY_UNFED_INPUTS_BY_CHAPTER
            and record["row"]["iso2"] in COLUMN2_ORIGINS
        ):
            _require(
                group == "components",
                f"chapter {chapter}: unresolved non-ad-valorem column-2 input "
                "reached base-dependent outputs",
            )
        requested = list(
            dict.fromkeys(
                name
                for slot in record["plan"]["components"]
                for name in SLOT_OUTPUTS[slot]
            )
        )
        if group == "full":
            requested += ["mfn_ad_valorem_rate", "schedule_statutory_stack"]
        outputs = tuple(f"{module_ref}#{name}" for name in requested)
        cases[group].append(
            Case(
                case_id=case_id,
                period=record["probe"],
                metadata={
                    "axiom_entity": "CustomsEntry",
                    "axiom_entity_id": "entry",
                    "axiom_inputs": {
                        f"{module_ref}#input.{name}": value
                        for name, value in feed.items()
                    },
                },
                outputs=outputs,
            )
        )
        contexts[group].append((record, flags, case_id, requested))
    runner = AxiomRulesRunner(
        program_path=_module_path(rulespec_root, chapter),
        binary_path=engine_binary,
        default_entity="CustomsEntry",
        default_entity_id="entry",
        rulespec_repo_roots=(rulespec_root,),
        batch_size=5_000,
        subprocess_run=_engine_subprocess_runner(rulespec_root),
    )
    paired = []
    for group in ("full", "components"):
        group_cases = cases[group]
        if not group_cases:
            continue
        variables = list(group_cases[0].outputs)
        results = runner.run_cases(group_cases, variables)
        _require(
            len(results) == len(contexts[group]),
            f"chapter {chapter}: missing engine results",
        )
        paired.extend(zip(results, contexts[group], strict=True))
    key = _shard_key(
        chapter=chapter,
        run_identity=run_identity,
        generation_id=generation_id,
    )
    _require(key == expected_key, f"chapter {chapter}: expected shard key drift")
    path = cache_dir / key[:2] / f"{key}.jsonl.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    errors = 0
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as raw:
        temporary = Path(raw.name)
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=raw, compresslevel=6, mtime=0
        ) as zipped:
            for result, (record, flags, case_id, requested) in paired:
                error = list(result.errors or [])
                errors += bool(error)
                payload = {
                    "case_id": case_id,
                    "chapter": chapter,
                    "probe": record["probe"],
                    "expected": {
                        name: record["row"][name] for name in EXPECTED_COLUMNS
                    },
                    "actual": None if error else _result_values(result, requested),
                    "engine_errors": error,
                    "plan": record["plan"],
                    "hts10": record["row"]["hts10"],
                    "country": record["row"]["country"],
                    "iso2": record["row"]["iso2"],
                    "revision": record["row"]["revision"],
                    "interval": [
                        record["row"]["clipped_from"],
                        record["row"]["clipped_until"],
                    ],
                    "origin_regime": record["row"]["origin_regime"],
                    "flags": flags,
                    "hts_line": record["route"]["hts_line"],
                }
                zipped.write(
                    (
                        json.dumps(payload, sort_keys=True, separators=(",", ":"))
                        + "\n"
                    ).encode()
                )
    temporary.replace(path)
    return {
        "chapter": chapter,
        "key": key,
        "run_identity_sha256": _run_identity_sha256(run_identity),
        "generation_id": generation_id,
        "sha256": _sha256(path),
        "path": str(path),
        "cases": sum(map(len, cases.values())),
        "engine_errors": errors,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


def evaluate_campaign(
    *,
    rulespec_root: Path,
    engine_binary: Path,
    workers: int,
    chapters: Iterable[str] | None = None,
    resume: bool = False,
    fresh: bool = False,
    cache_dir: Path | None = None,
) -> dict[str, Any]:
    _require(1 <= workers <= 3, "workers must be between 1 and 3")
    _require(not (fresh and resume), "--fresh and --resume are mutually exclusive")
    rulespec_root = rulespec_root.resolve()
    engine_binary = engine_binary.resolve()
    run_identity = _current_run_identity(
        rulespec_root=rulespec_root, engine_binary=engine_binary
    )
    run_identity_sha256 = _run_identity_sha256(run_identity)
    with _eval_manifest_lock():
        if fresh:
            generation_id = _new_eval_generation_id()
            manifest = _empty_eval_manifest(run_identity, generation_id)
        else:
            existing = _load_manifest()
            generation_id = existing.get("generation_id")
            if (
                existing.get("run_identity") != run_identity
                or existing.get("run_identity_sha256") != run_identity_sha256
                or not _valid_eval_generation_id(generation_id)
            ):
                generation_id = _new_eval_generation_id()
            current_keys = _current_shard_keys(run_identity, generation_id)
            manifest = _prepare_eval_manifest(
                existing, current_keys, run_identity, generation_id
            )
        current_keys = _current_shard_keys(run_identity, generation_id)
        declared_chapters = sorted(current_keys)
        chosen = sorted(set(chapters or declared_chapters))
        _require(
            set(chosen) <= set(declared_chapters),
            f"unknown chapters: {sorted(set(chosen) - set(declared_chapters))}",
        )
        pending = []
        resume_skips = []
        for chapter in chosen:
            key = current_keys[chapter]
            old = manifest["shards"].get(key)
            complete = (
                old
                and Path(old["path"]).is_file()
                and _sha256(Path(old["path"])) == old["sha256"]
            )
            if resume and complete:
                resume_skips.append(old)
                continue
            # A chapter being recomputed is absent before the worker starts.
            # Comparison can never mistake the previous receipt for the
            # output of an in-flight or interrupted non-fresh invocation.
            manifest["shards"].pop(key, None)
            pending.append(chapter)
        # Commit the invalidation before launching any engine process.  An
        # interrupted rebind therefore cannot retain old comparison bindings
        # or superseded shards and masquerade as a complete current run.
        _atomic_json(EVAL_MANIFEST, manifest)
    cache = cache_dir or CACHE_ROOT / "eval"
    for old in resume_skips:
        print(
            f"{old['chapter']}: resume skip cases={old['cases']} "
            f"errors={old['engine_errors']}",
            flush=True,
        )
    campaign_started = time.perf_counter()
    finished = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _evaluate_chapter,
                chapter,
                rulespec_root=rulespec_root,
                engine_binary=engine_binary,
                cache_dir=cache,
                run_identity=run_identity,
                generation_id=generation_id,
                expected_key=current_keys[chapter],
            ): chapter
            for chapter in pending
        }
        for future in concurrent.futures.as_completed(futures):
            receipt = future.result()
            _require(
                receipt.get("key") == current_keys.get(receipt.get("chapter"))
                and receipt.get("run_identity_sha256") == run_identity_sha256
                and receipt.get("generation_id") == generation_id,
                f"evaluation returned a non-current shard: {receipt.get('chapter')}",
            )
            with _eval_manifest_lock():
                _require(
                    _current_run_identity(
                        rulespec_root=rulespec_root, engine_binary=engine_binary
                    )
                    == run_identity,
                    "evaluation producers changed while the campaign was running",
                )
                published = _load_manifest()
                _require(
                    published.get("run_identity") == run_identity
                    and published.get("run_identity_sha256") == run_identity_sha256
                    and published.get("generation_id") == generation_id,
                    "evaluation manifest was replaced by another run",
                )
                manifest = _prepare_eval_manifest(
                    published, current_keys, run_identity, generation_id
                )
                manifest["shards"][receipt["key"]] = receipt
                _atomic_json(EVAL_MANIFEST, manifest)
            finished += 1
            elapsed = time.perf_counter() - campaign_started
            eta = elapsed / finished * (len(pending) - finished) if finished else 0
            print(
                f"{receipt['chapter']}: cases={receipt['cases']} errors={receipt['engine_errors']} "
                f"elapsed={receipt['elapsed_seconds']:.1f}s ETA={eta:.0f}s",
                flush=True,
            )
    return manifest


def _iter_eval_records(manifest: dict[str, Any]) -> Iterator[dict[str, Any]]:
    seen_chapters = set()
    run_identity_sha256 = manifest.get("run_identity_sha256")
    generation_id = manifest.get("generation_id")
    _require(
        _valid_eval_generation_id(generation_id),
        "evaluation manifest generation id is malformed",
    )
    for key, shard in sorted(
        manifest["shards"].items(), key=lambda item: item[1]["chapter"]
    ):
        _require(
            shard.get("key") == key
            and shard.get("run_identity_sha256") == run_identity_sha256
            and shard.get("generation_id") == generation_id,
            f"invalid shard identity {key}",
        )
        path = Path(shard["path"])
        _require(
            path.is_file() and _sha256(path) == shard["sha256"],
            f"invalid shard {shard['key']}",
        )
        _require(
            shard["chapter"] not in seen_chapters,
            f"duplicate chapter shard {shard['chapter']}",
        )
        seen_chapters.add(shard["chapter"])
        records = 0
        with gzip.open(path, "rt") as source:
            for line in source:
                record = json.loads(line)
                _require(
                    record.get("chapter") == shard["chapter"],
                    f"shard {key} contains a foreign chapter record",
                )
                records += 1
                yield record
        _require(
            records == shard.get("cases"),
            f"shard {key} case count does not match its receipt",
        )


def _expected_slots(expected: dict[str, str]) -> dict[str, float]:
    values = {name: float(value) for name, value in expected.items()}
    return {
        slot: sum(values[name] for name in columns)
        for slot, columns in EXPECTED_SLOT_COLUMNS.items()
    }


def compare_record(
    record: dict[str, Any], tolerance: float = TOLERANCE
) -> list[dict[str, Any]]:
    if record["engine_errors"]:
        return [
            {
                "case_id": record["case_id"],
                "slot": "engine_error",
                "match": False,
                "error": record["engine_errors"],
                "delta": None,
            }
        ]
    expected = _expected_slots(record["expected"])
    comparable = list(record["plan"]["components"])
    if record["plan"]["base"] == "compare":
        comparable += ["base"]
    actual = {
        slot: sum(record["actual"][name] for name in SLOT_OUTPUTS[slot])
        for slot in comparable
    }
    rows = []
    for slot in comparable:
        delta = actual[slot] - expected[slot]
        rows.append(
            {
                "case_id": record["case_id"],
                "slot": slot,
                "expected": expected[slot],
                "actual": actual[slot],
                "delta": delta,
                "match": abs(delta) <= tolerance,
            }
        )
    yale_total = sum(float(record["expected"][name]) for name in EXPECTED_COLUMNS)
    axiom_total = sum(actual.values())
    if record["plan"]["total"] == "compare":
        total_delta = axiom_total - yale_total
        rows.append(
            {
                "case_id": record["case_id"],
                "slot": "total",
                "expected": yale_total,
                "actual": axiom_total,
                "delta": total_delta,
                "match": abs(total_delta) <= tolerance,
            }
        )
        stack_delta = record["actual"]["schedule_statutory_stack"] - axiom_total
        rows.append(
            {
                "case_id": record["case_id"],
                "slot": "axiom_total_reconciliation",
                "expected": axiom_total,
                "actual": record["actual"]["schedule_statutory_stack"],
                "delta": stack_delta,
                "match": abs(stack_delta) <= tolerance,
            }
        )
        yale_rebuilt = (
            sum(expected.values())
            + float(record["expected"]["statutory_rate_301_cs"])
            + float(record["expected"]["statutory_rate_other"])
        )
        rows.append(
            {
                "case_id": record["case_id"],
                "slot": "yale_total_reconciliation",
                "expected": yale_total,
                "actual": yale_rebuilt,
                "delta": yale_rebuilt - yale_total,
                "match": abs(yale_rebuilt - yale_total) <= tolerance,
            }
        )
    for row in rows:
        row["context"] = {
            key: record[key]
            for key in (
                "hts10",
                "hts_line",
                "iso2",
                "revision",
                "interval",
                "origin_regime",
                "flags",
            )
        }
    return rows


def _require_current_complete_manifest_locked(
    *, rulespec_root: Path, engine_binary: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    run_identity = _current_run_identity(
        rulespec_root=rulespec_root.resolve(),
        engine_binary=engine_binary.resolve(),
    )
    run_identity_sha256 = _run_identity_sha256(run_identity)
    manifest = _load_manifest()
    generation_id = manifest.get("generation_id")
    _require(
        _valid_eval_generation_id(generation_id),
        "evaluation manifest generation id is absent or malformed",
    )
    current_keys = _current_shard_keys(run_identity, generation_id)
    _require(
        manifest.get("run_identity") == run_identity
        and manifest.get("run_identity_sha256") == run_identity_sha256,
        "evaluation manifest is bound to a different producer run",
    )
    expected_keys = set(current_keys.values())
    _require(
        set(manifest["shards"]) == expected_keys,
        "evaluation manifest is incomplete or contains stale shards",
    )
    expected_by_key = {key: chapter for chapter, key in current_keys.items()}
    for key, shard in manifest["shards"].items():
        _require(
            isinstance(shard, dict)
            and shard.get("key") == key
            and shard.get("chapter") == expected_by_key[key]
            and shard.get("run_identity_sha256") == run_identity_sha256
            and shard.get("generation_id") == generation_id,
            f"evaluation manifest contains a non-current shard identity: {key}",
        )
        path = Path(shard.get("path", ""))
        _require(
            path.is_file()
            and isinstance(shard.get("sha256"), str)
            and _sha256(path) == shard["sha256"],
            f"evaluation manifest contains an invalid shard artifact: {key}",
        )
    evaluation_manifest = _empty_eval_manifest(run_identity, generation_id)
    evaluation_manifest["shards"] = manifest["shards"]
    return manifest, evaluation_manifest, run_identity


def _require_current_complete_manifest(
    *, rulespec_root: Path, engine_binary: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    with _eval_manifest_lock():
        return _require_current_complete_manifest_locked(
            rulespec_root=rulespec_root, engine_binary=engine_binary
        )


def _load_bound_comparison_locked(
    *, rulespec_root: Path, engine_binary: Path
) -> dict[str, Any]:
    manifest, evaluation_manifest, run_identity = (
        _require_current_complete_manifest_locked(
            rulespec_root=rulespec_root, engine_binary=engine_binary
        )
    )
    _require(COMPARISON_RECEIPT.is_file(), "comparison receipt is missing")
    comparison_receipt = _file_receipt(COMPARISON_RECEIPT, relative_to=REPO_ROOT)
    _require(
        manifest.get("comparison_receipt") == comparison_receipt,
        "evaluation manifest comparison-receipt binding is absent or stale",
    )
    comparison = json.loads(COMPARISON_RECEIPT.read_text())
    evaluation_sha256 = _canonical_sha256(evaluation_manifest)
    _require(
        comparison.get("schema") == COMPARISON_SCHEMA,
        "comparison receipt schema is stale",
    )
    _require(
        comparison.get("run_identity_sha256") == _run_identity_sha256(run_identity)
        and comparison.get("generation_id") == evaluation_manifest["generation_id"]
        and comparison.get("evaluation_manifest_sha256") == evaluation_sha256,
        "comparison receipt evaluation binding is stale",
    )
    artifact = comparison.get("comparison_artifact")
    _require(
        isinstance(artifact, dict) and isinstance(artifact.get("path"), str),
        "comparison artifact receipt is malformed",
    )
    artifact_path = Path(artifact["path"])
    _require(artifact_path.is_file(), "comparison artifact is missing")
    actual_artifact = _file_receipt(artifact_path)
    _require(artifact == actual_artifact, "comparison artifact receipt is stale")
    _require(
        manifest.get("comparison_artifact") == artifact,
        "evaluation manifest comparison-artifact binding is absent or stale",
    )
    return comparison


def _load_bound_comparison(
    *, rulespec_root: Path, engine_binary: Path
) -> dict[str, Any]:
    with _eval_manifest_lock():
        return _load_bound_comparison_locked(
            rulespec_root=rulespec_root, engine_binary=engine_binary
        )


def compare_campaign(
    *,
    rulespec_root: Path = RULESPEC_US_ROOT,
    engine_binary: Path = DEFAULT_ENGINE_BINARY,
    cache_dir: Path | None = None,
) -> dict[str, Any]:
    with _eval_manifest_lock():
        return _compare_campaign_locked(
            rulespec_root=rulespec_root,
            engine_binary=engine_binary,
            cache_dir=cache_dir,
        )


def _compare_campaign_locked(
    *,
    rulespec_root: Path,
    engine_binary: Path,
    cache_dir: Path | None,
) -> dict[str, Any]:
    _manifest, evaluation_manifest, run_identity = (
        _require_current_complete_manifest_locked(
            rulespec_root=rulespec_root, engine_binary=engine_binary
        )
    )
    # Clear any old downstream binding before producing a replacement.  A
    # crash anywhere below leaves a complete but deliberately unbound run.
    _atomic_json(EVAL_MANIFEST, evaluation_manifest)
    counts: dict[str, Counter[str]] = {}
    digest = _canonical_sha256(evaluation_manifest)
    output = (cache_dir or CACHE_ROOT / "compare") / digest[:2] / f"{digest}.jsonl.gz"
    output.parent.mkdir(parents=True, exist_ok=True)
    engine_errors = 0
    with tempfile.NamedTemporaryFile("wb", dir=output.parent, delete=False) as raw:
        temporary = Path(raw.name)
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            for record in _iter_eval_records(evaluation_manifest):
                for comparison in compare_record(record):
                    slot = comparison["slot"]
                    counts.setdefault(slot, Counter())[
                        "match" if comparison["match"] else "mismatch"
                    ] += 1
                    engine_errors += slot == "engine_error"
                    zipped.write(
                        (
                            json.dumps(
                                comparison, sort_keys=True, separators=(",", ":")
                            )
                            + "\n"
                        ).encode()
                    )
    temporary.replace(output)
    receipt = {
        "schema": COMPARISON_SCHEMA,
        "run_identity_sha256": _run_identity_sha256(run_identity),
        "generation_id": evaluation_manifest["generation_id"],
        "evaluation_manifest_sha256": digest,
        "tolerance": TOLERANCE,
        "comparison_artifact": _file_receipt(output),
        "per_slot": {slot: dict(counter) for slot, counter in sorted(counts.items())},
        "engine_errors": engine_errors,
    }
    _atomic_json(COMPARISON_RECEIPT, receipt)
    _published, current_evaluation_manifest, current_identity = (
        _require_current_complete_manifest_locked(
            rulespec_root=rulespec_root, engine_binary=engine_binary
        )
    )
    _require(
        current_evaluation_manifest == evaluation_manifest
        and current_identity == run_identity,
        "evaluation manifest changed during comparison",
    )
    evaluation_manifest["comparison_artifact"] = receipt["comparison_artifact"]
    evaluation_manifest["comparison_receipt"] = _file_receipt(
        COMPARISON_RECEIPT, relative_to=REPO_ROOT
    )
    _atomic_json(EVAL_MANIFEST, evaluation_manifest)
    return receipt


def mismatch_signature(row: dict[str, Any]) -> str:
    context = row["context"]
    signature = {
        "authority_slot": row["slot"],
        "delta": row["delta"],
        "flag_vector": context["flags"],
        "revision_interval_regime": [context["revision"], *context["interval"]],
        "origin_regime": context["origin_regime"],
        # Structured selectors can bind both HTS10 and ISO2. They therefore
        # belong in the aggregation identity: otherwise two selector-distinct
        # units can collapse behind one arbitrary first exemplar.
        "line_incidence_signature": [
            context["hts10"],
            context["hts_line"],
            context["iso2"],
            sorted(name for name, value in context["flags"].items() if value),
        ],
    }
    return hashlib.sha256(_render(signature).encode()).hexdigest()


def _routing_dispositions(
    routing_bytes: bytes | None = None,
) -> dict[str, tuple[str, str]]:
    routing_bytes = (
        ROUTING_ROWS.read_bytes() if routing_bytes is None else routing_bytes
    )
    source = io.StringIO(gzip.decompress(routing_bytes).decode())
    return {
        row["hts10"]: (row["general_disposition"], row["column2_disposition"])
        for row in csv.DictReader(source)
    }


def mismatch_unit(
    row: dict[str, Any], routes: dict[str, tuple[str, str]]
) -> dict[str, Any]:
    context = row["context"]
    general, column2 = routes[context["hts10"]]
    return {
        "slot": row["slot"],
        "origin_regime": context["origin_regime"],
        "revision": context["revision"],
        "delta": row["delta"],
        "disposition": column2 if context["iso2"] in COLUMN2_ORIGINS else general,
        "hts10": context["hts10"],
        "hts_line": context["hts_line"],
        "flags": context["flags"],
        "interval": context["interval"],
        "iso2": context["iso2"],
    }


def _match_scalar_or_list(value: Any, selector: Any, field: str) -> bool:
    if selector == "any":
        return True
    _require(
        isinstance(selector, list) and selector,
        f"selector {field} must be any or a nonempty list",
    )
    _require(
        all(isinstance(item, str) and item for item in selector),
        f"selector {field} has invalid values",
    )
    return value in selector


def _delta_value_set(values: list[float]) -> frozenset[float]:
    """Compile large receipted exact-value selectors once."""
    key = id(values)
    cached = _DELTA_VALUE_SETS.get(key)
    if cached is None or cached[0] is not values:
        cached = (values, frozenset(values))
        _DELTA_VALUE_SETS[key] = cached
    return cached[1]


def _match_line_class(unit: dict[str, Any], selector: Any) -> bool:
    if isinstance(selector, str):
        _require(
            selector in {"yale_member_only", "yale_rate_line"},
            f"unknown line_class {selector}",
        )
        return (unit["hts10"] != unit["hts_line"]) == (selector == "yale_member_only")
    _require(
        isinstance(selector, dict) and selector,
        "line_class must be a named class or nonempty mapping",
    )
    allowed = {"membership", "hts_prefix", "hts10", "flags"}
    _require(
        set(selector) <= allowed,
        f"unknown line_class fields: {sorted(set(selector) - allowed)}",
    )
    if "membership" in selector:
        _require(
            selector["membership"] in {"member_only", "rate_line"},
            "invalid line_class membership",
        )
        if (unit["hts10"] != unit["hts_line"]) != (
            selector["membership"] == "member_only"
        ):
            return False
    for field in ("hts_prefix", "hts10"):
        if field not in selector:
            continue
        values = selector[field]
        _require(
            isinstance(values, list)
            and values
            and all(isinstance(v, str) and v for v in values),
            f"line_class {field} must be a nonempty string list",
        )
        if field == "hts_prefix" and not any(
            unit["hts10"].startswith(value) for value in values
        ):
            return False
        if field == "hts10" and unit["hts10"] not in values:
            return False
    if "flags" in selector:
        flags = selector["flags"]
        _require(
            isinstance(flags, dict) and flags,
            "line_class flags must be a nonempty mapping",
        )
        _require(
            all(name in unit["flags"] for name in flags),
            "line_class references unknown flag",
        )
        _require(
            all(isinstance(value, bool) for value in flags.values()),
            "line_class flag values must be boolean",
        )
        if any(unit["flags"][name] is not value for name, value in flags.items()):
            return False
    return True


@cache
def _membership_rules(path: Path) -> dict[str, tuple[int, frozenset[str]]]:
    _require(path.is_file(), f"line-set membership table unavailable: {path}")
    payload = yaml.safe_load(path.read_text())
    result: dict[str, tuple[int, frozenset[str]]] = {}
    for rule in payload.get("rules", []):
        name = rule.get("name", "")
        if "membership" not in name and path != CH98_LINES:
            continue
        values = rule.get("versions", [{}])[0].get("values", {})
        if not isinstance(values, dict) or not values:
            continue
        width = (
            10
            if "hts10" in name
            else 6
            if "subheading6" in name
            else 4
            if "heading" in name
            else 8
        )
        result[name] = (
            width,
            frozenset(str(key).zfill(width) for key, value in values.items() if value),
        )
    return result


def _preview_all_selector_snapshot(preview: dict[str, Any]) -> dict[str, Any]:
    """Project the producer-independent immutable all-selector ruling."""

    raw_selectors = preview.get("selectors")
    raw_line_sets = preview.get("line_sets")
    inputs = preview.get("inputs")
    census = preview.get("census", {}).get("per_selector")
    _require(
        isinstance(raw_selectors, list)
        and isinstance(raw_line_sets, dict)
        and isinstance(inputs, dict)
        and isinstance(census, dict),
        "preview all-selector snapshot inputs are malformed",
    )
    selectors = sorted(
        (
            item
            for item in raw_selectors
            if isinstance(item, dict)
            and item.get("id") in TRANSITION_EXPECTED_PARENT_IDS
        ),
        key=lambda item: item["id"],
    )
    line_set_names = {
        item.get("match", {}).get("line_set")
        for item in selectors
        if isinstance(item.get("match"), dict)
    }
    _require(
        len(selectors) == len(TRANSITION_EXPECTED_PARENT_IDS)
        and {item["id"] for item in selectors} == TRANSITION_EXPECTED_PARENT_IDS
        and None not in line_set_names
        and line_set_names <= set(raw_line_sets),
        "preview all-selector snapshot coverage is malformed",
    )
    return {
        "schema": preview.get("schema"),
        "inputs": inputs,
        "yale_sources": preview.get("yale_sources"),
        "definition": preview.get("definition"),
        "selectors": selectors,
        "line_sets": {name: raw_line_sets[name] for name in sorted(line_set_names)},
        "census": {
            selector_id: census.get(selector_id)
            for selector_id in sorted(TRANSITION_EXPECTED_PARENT_IDS)
        },
    }


def _require_immutable_preview_all_selector_snapshot(
    preview: dict[str, Any],
) -> None:
    _require(
        _canonical_sha256(_preview_all_selector_snapshot(preview))
        == PREVIEW_ALL_SELECTOR_SNAPSHOT_SHA256,
        "immutable preview all-selector snapshot drift",
    )


def _preview_disposition_receipt() -> dict[str, Any]:
    preview = json.loads(PREVIEW_DISPOSITION_LINE_SETS.read_text())
    _require(
        preview.get("schema")
        == "axiom_oracles.us_tariff_schedule.preview_disposition_line_sets.v1"
        and preview.get("verdict") == "PASS",
        "invalid preview disposition line-set receipt",
    )
    received_digest = preview.get("receipt_payload_sha256")
    digest_payload = dict(preview)
    digest_payload.pop("receipt_payload_sha256", None)
    _require(
        received_digest
        == hashlib.sha256(
            json.dumps(
                digest_payload, allow_nan=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest(),
        "preview disposition line-set payload digest drift",
    )
    inputs = preview.get("inputs")
    _require(isinstance(inputs, dict), "preview disposition inputs are malformed")
    input_hashes = {
        name: receipt.get("sha256") if isinstance(receipt, dict) else None
        for name, receipt in inputs.items()
    }
    _require(
        input_hashes == PREVIEW_DISPOSITION_INPUT_SHA256,
        "preview disposition source hash drift",
    )
    expected_producer = {
        name: {
            "path": str(path.relative_to(REPO_ROOT)),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for name, path in PREVIEW_DISPOSITION_PRODUCER_SOURCES.items()
    }
    _require(
        preview.get("producer") == expected_producer,
        "preview disposition producer source drift",
    )
    yale_sources = preview.get("yale_sources")
    _require(isinstance(yale_sources, dict), "preview Yale source receipt is malformed")
    _require(
        yale_sources.get("commit") == PREVIEW_YALE_COMMIT
        and yale_sources.get("tree") == PREVIEW_YALE_TREE,
        "preview Yale source pin drift",
    )
    _require_immutable_preview_all_selector_snapshot(preview)
    return preview


def _preview_transition_is_required(
    entries: list[dict[str, Any]], preview: dict[str, Any]
) -> bool:
    """Return whether the ledger enrolls a child of a preview selector.

    A missing historical selector is still handled by the ordinary retirement
    guard.  Transition evidence becomes mandatory only when a new ledger id
    reuses one of the immutable preview line sets; this keeps evaluation,
    comparison, and unchanged-ledger classification independent of a future
    transition receipt.
    """

    historical_ids = {
        selector.get("id")
        for selector in preview.get("selectors", [])
        if isinstance(selector, dict)
    }
    historical_line_sets = (
        set(preview["line_sets"])
        if isinstance(preview.get("line_sets"), dict)
        else set()
    )
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("id") in historical_ids:
            continue
        match = entry.get("match")
        line_set = match.get("line_set") if isinstance(match, dict) else None
        if line_set in historical_line_sets:
            return True
    return False


def _cafta_transition_evidence(
    transitions: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the sole CAFTA transition and its embedded authenticated receipt."""

    cafta_items = [
        item
        for item in transitions
        if isinstance(item, dict) and item.get("parent_id") == CAFTA_PREVIEW_SELECTOR_ID
    ]
    wrappers = [
        (item, item.get("evidence", {}).get("cafta_supersession_receipt"))
        for item in transitions
        if isinstance(item, dict)
        and isinstance(item.get("evidence"), dict)
        and "cafta_supersession_receipt" in item["evidence"]
    ]
    _require(
        len(cafta_items) == 1
        and len(wrappers) == 1
        and wrappers[0][0] is cafta_items[0],
        "CAFTA supersession evidence is missing or attached to the wrong parent",
    )
    wrapper = wrappers[0][1]
    _require(
        isinstance(wrapper, dict) and set(wrapper) == {"file", "payload"},
        "CAFTA supersession evidence wrapper is malformed",
    )
    return cafta_items[0], wrapper


def _run_cafta_tidy_eval_reproduction() -> dict[str, Any]:
    """Independently replay the bounded Yale tidy-eval defect."""

    rscript_value = shutil.which("Rscript")
    _require(rscript_value is not None, "Rscript is required for CAFTA proof replay")
    rscript = Path(rscript_value).resolve()
    rscript_receipt = _file_receipt(rscript)
    _require(
        rscript_receipt == CAFTA_EXPECTED_RSCRIPT_RECEIPT,
        "CAFTA tidy-eval Rscript runtime drift",
    )
    runtime_receipt = _directory_tree_receipt(
        Path(CAFTA_EXPECTED_R_RUNTIME_TREE_RECEIPT["path"])
    )
    _require(
        runtime_receipt == CAFTA_EXPECTED_R_RUNTIME_TREE_RECEIPT,
        "CAFTA tidy-eval R runtime tree drift",
    )
    dplyr_receipt = _directory_tree_receipt(
        Path(CAFTA_EXPECTED_DPLYR_TREE_RECEIPT["path"])
    )
    _require(
        dplyr_receipt == CAFTA_EXPECTED_DPLYR_TREE_RECEIPT,
        "CAFTA tidy-eval dplyr runtime drift",
    )
    with tempfile.TemporaryDirectory(prefix="axiom-cafta-r-") as runtime_home:
        completed = subprocess.run(
            [str(rscript), "--vanilla", "-e", CAFTA_TIDY_EVAL_PROGRAM],
            check=True,
            capture_output=True,
            text=True,
            env={
                "HOME": runtime_home,
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": "/usr/bin:/bin",
                "TMPDIR": runtime_home,
            },
        )
    _require(not completed.stderr, "CAFTA tidy-eval replay emitted stderr")
    fields: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        key, separator, value = line.partition("=")
        _require(
            bool(separator) and key not in fields,
            "malformed CAFTA tidy-eval replay",
        )
        fields[key] = value
    _require(
        fields
        == {
            "r_version": "4.3.0",
            "dplyr_version": "1.1.2",
            "dplyr_path": CAFTA_EXPECTED_DPLYR_TREE_RECEIPT["path"],
            "selected_conditions": "full,fta",
        },
        "CAFTA tidy-eval replay drift",
    )
    program_sha256 = hashlib.sha256(CAFTA_TIDY_EVAL_PROGRAM.encode()).hexdigest()
    _require(
        program_sha256 == CAFTA_EXPECTED_TIDY_EVAL_PROGRAM_SHA256,
        "CAFTA tidy-eval replay program drift",
    )
    _require(
        _file_receipt(rscript) == rscript_receipt
        and _directory_tree_receipt(Path(runtime_receipt["path"])) == runtime_receipt
        and _directory_tree_receipt(Path(dplyr_receipt["path"])) == dplyr_receipt,
        "CAFTA tidy-eval runtime changed during replay",
    )
    return {
        "rscript": rscript_receipt,
        "r_runtime_tree": runtime_receipt,
        "dplyr_tree": dplyr_receipt,
        "program_sha256": program_sha256,
        **fields,
        "result": (
            "PASS: rule_hit('full') selected both the full and fta rows under "
            "the pinned .data$condition %in% condition expression"
        ),
    }


def _comparison_observation_count(comparison: dict[str, Any]) -> int:
    """Return the exact row census represented by comparison per-slot counts."""

    per_slot = comparison.get("per_slot")
    _require(
        isinstance(per_slot, dict) and bool(per_slot),
        "comparison per-slot census is malformed",
    )
    total = 0
    for slot, counts in per_slot.items():
        _require(
            isinstance(slot, str)
            and bool(slot)
            and isinstance(counts, dict)
            and bool(counts)
            and set(counts) <= {"match", "mismatch"}
            and all(type(units) is int and units >= 0 for units in counts.values()),
            f"comparison per-slot census is malformed: {slot}",
        )
        total += sum(counts.values())
    return total


def _validate_cafta_yale_defect_evidence(value: Any) -> None:
    """Validate every producer-emitted arm of the pinned Yale defect proof."""

    _require(
        isinstance(value, dict)
        and set(value)
        == {
            "adapter_source_proof",
            "commit",
            "deterministic_minimal_reproduction",
            "files",
            "source_proof",
            "tree",
        }
        and value.get("commit") == PREVIEW_YALE_COMMIT
        and value.get("tree") == PREVIEW_YALE_TREE,
        "CAFTA supersession Yale defect proof is malformed",
    )
    _require(
        value.get("adapter_source_proof") == CAFTA_YALE_ADAPTER_SOURCE_PROOF,
        "CAFTA supersession Yale adapter proof drift",
    )
    files = value.get("files")
    _require(
        isinstance(files, dict) and set(files) == set(CAFTA_YALE_FILE_SHA256),
        "CAFTA supersession Yale file proof is incomplete",
    )
    for path, expected_sha256 in CAFTA_YALE_FILE_SHA256.items():
        file_receipt = files.get(path)
        _require(
            isinstance(file_receipt, dict)
            and set(file_receipt) == {"path", "bytes", "sha256"}
            and file_receipt.get("path") == path
            and isinstance(file_receipt.get("bytes"), int)
            and not isinstance(file_receipt["bytes"], bool)
            and file_receipt["bytes"] > 0
            and file_receipt.get("sha256") == expected_sha256,
            f"CAFTA supersession Yale file proof drift: {path}",
        )

    source_proof = value.get("source_proof")
    source_lines = {
        "rule_hit_function_first_line": 959,
        "rule_hit_use_site_first_line": 973,
        "use_conditioned_first_line": 999,
        "chapter98_precapture_first_line": 2961,
        "statutory_capture_first_line": 3022,
    }
    source_text = {
        "defect": (
            "the function argument is named condition, but dplyr's data mask "
            "resolves the bare RHS condition to the condition column; therefore "
            ".data$condition %in% condition is true for every nonmissing row"
        ),
        "downstream_effect": (
            "rule_hit('full') includes condition=fta rows, making country_full_hit "
            "true, covered false, and rate_s301fl zero before preference scaling"
        ),
        "comparison_surface": (
            "statutory_rate_s301fl captures rate_s301fl before the later HS2-country "
            "preference scaling; fixing the name collision restores the statutory "
            "country-tier rate on the compared surface regardless of utilization share"
        ),
    }
    _require(
        isinstance(source_proof, dict)
        and set(source_proof)
        == set(source_lines) | set(source_text) | set(CAFTA_YALE_SOURCE_PROOF_HASHES)
        and all(
            source_proof.get(field) == expected
            for field, expected in source_lines.items()
        )
        and all(
            source_proof.get(field) == expected
            for field, expected in source_text.items()
        )
        and all(
            source_proof.get(field) == expected
            for field, expected in CAFTA_YALE_SOURCE_PROOF_HASHES.items()
        ),
        "CAFTA supersession Yale source proof drift",
    )

    _require(
        value.get("deterministic_minimal_reproduction")
        == _run_cafta_tidy_eval_reproduction(),
        "CAFTA supersession Yale minimal reproduction drift",
    )


def _validate_cafta_transition_evidence(
    *,
    transitions: list[dict[str, Any]],
    comparison: dict[str, Any],
    preview: dict[str, Any],
    manifest: dict[str, Any],
    transition_inputs: dict[str, Any],
) -> None:
    """Authenticate the independent CAFTA proof embedded in the transition."""

    cafta_item, wrapper = _cafta_transition_evidence(transitions)
    expected_file = _file_receipt(CAFTA_SUPERSESSION_RECEIPT, relative_to=REPO_ROOT)
    _require(
        wrapper.get("file") == expected_file,
        "CAFTA supersession receipt file binding is stale",
    )
    try:
        receipt_on_disk = json.loads(CAFTA_SUPERSESSION_RECEIPT.read_text())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("CAFTA supersession receipt file is malformed") from exc
    receipt = wrapper.get("payload")
    _require(
        isinstance(receipt, dict) and receipt_on_disk == receipt,
        "embedded CAFTA supersession payload differs from the current file",
    )
    expected_fields = {
        "schema",
        "verdict",
        "producer",
        "definition",
        "inputs",
        "bindings",
        "axiom_predicate_proof",
        "yale_reference_defect",
        "zero_error_proof",
        "census",
        "supersession",
        "receipt_payload_sha256",
    }
    _require(
        set(receipt) == expected_fields
        and receipt.get("schema") == CAFTA_SUPERSESSION_SCHEMA
        and receipt.get("verdict") == "PASS",
        "CAFTA supersession receipt is not a complete PASS v1 receipt",
    )
    received_digest = receipt.get("receipt_payload_sha256")
    digest_payload = dict(receipt)
    digest_payload.pop("receipt_payload_sha256", None)
    _require(
        isinstance(received_digest, str)
        and re.fullmatch(r"[0-9a-f]{64}", received_digest) is not None
        and received_digest == _canonical_sha256(digest_payload),
        "CAFTA supersession receipt payload digest drift",
    )
    _require(
        receipt.get("producer")
        == {
            "script": _file_receipt(CAFTA_SUPERSESSION_PRODUCER, relative_to=REPO_ROOT)
        },
        "CAFTA supersession receipt producer source drift",
    )

    expected_inputs = {
        "immutable_preview_receipt": transition_inputs["immutable_preview_receipt"],
        "historical_target_mismatch_artifact": transition_inputs[
            "historical_target_mismatch_artifact"
        ],
        "evaluation_manifest": transition_inputs["evaluation_manifest"],
        "comparison_receipt": transition_inputs["comparison_receipt"],
        "comparison_artifact": transition_inputs["comparison_artifact"],
        "declared_input_contract": _file_receipt(
            INPUT_CONTRACT_RECEIPT, relative_to=REPO_ROOT
        ),
        "reference_provenance": _file_receipt(
            CAFTA_REFERENCE_PROVENANCE, relative_to=REPO_ROOT
        ),
        "reference_integrity_receipt": _file_receipt(
            CAFTA_REFERENCE_INTEGRITY_RECEIPT, relative_to=REPO_ROOT
        ),
        "selected_panel_extractor": _file_receipt(
            CAFTA_SELECTED_PANEL_EXTRACTOR, relative_to=REPO_ROOT
        ),
    }
    _require(
        receipt.get("inputs") == expected_inputs,
        "CAFTA supersession receipt input binding is stale",
    )
    try:
        reference_provenance = json.loads(CAFTA_REFERENCE_PROVENANCE.read_text())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("CAFTA reference provenance is malformed") from exc
    _require(
        isinstance(reference_provenance, dict)
        and reference_provenance.get("schema")
        == "axiom_oracles.us_tariff_schedule_reference.v1"
        and reference_provenance.get("yale_commit") == PREVIEW_YALE_COMMIT
        and isinstance(reference_provenance.get("rds_path"), str)
        and bool(reference_provenance["rds_path"])
        and reference_provenance.get("rds_sha256") == CAFTA_EXPECTED_RDS_SHA256
        and reference_provenance.get("selected_extract_sha256") == _sha256(SELECTED)
        and reference_provenance.get("extractor_sha256")
        == expected_inputs["selected_panel_extractor"]["sha256"],
        "CAFTA reference provenance binding drift",
    )

    run_identity = manifest.get("run_identity")
    selected_population = _file_receipt(SELECTED, relative_to=REPO_ROOT)
    campaign_evaluator = (
        run_identity.get("campaign_evaluator")
        if isinstance(run_identity, dict)
        else None
    )
    campaign_source = (
        campaign_evaluator.get("campaign")
        if isinstance(campaign_evaluator, dict)
        else None
    )
    preview_producer = preview.get("producer")
    preview_campaign_source = (
        preview_producer.get("campaign_classifier")
        if isinstance(preview_producer, dict)
        else None
    )
    chapters = run_identity.get("chapters") if isinstance(run_identity, dict) else None
    shards = manifest.get("shards")
    valid_shard_case_census = (
        isinstance(shards, dict)
        and bool(shards)
        and all(
            isinstance(shard, dict)
            and type(shard.get("cases")) is int
            and shard["cases"] >= 0
            for shard in shards.values()
        )
    )
    manifest_cases = (
        sum(shard["cases"] for shard in shards.values())
        if valid_shard_case_census
        else None
    )
    bindings = receipt.get("bindings")
    binding_fields = {
        "campaign_evaluator",
        "campaign_producer_identity_required",
        "campaign_semantic_equivalence_basis",
        "comparison_receipt_engine_errors",
        "evaluated_cases",
        "evaluated_chapters",
        "evaluation_manifest_sha256",
        "evaluation_shard_engine_errors",
        "fresh_campaign_classifier_sha256",
        "generation_id",
        "observed_evaluated_cases",
        "observed_evaluation_record_errors",
        "preview_cafta_snapshot_sha256",
        "preview_campaign_classifier_sha256",
        "preview_receipt_payload_sha256",
        "reference_compared_field",
        "reference_rds_path",
        "reference_rds_sha256",
        "rulespec",
        "run_identity_sha256",
        "selected_population_sha256",
    }
    _require(
        isinstance(run_identity, dict)
        and isinstance(chapters, dict)
        and len(chapters) == 100
        and valid_shard_case_census
        and run_identity.get("selected_population") == selected_population
        and isinstance(campaign_source, dict)
        and isinstance(preview_campaign_source, dict)
        and isinstance(bindings, dict)
        and set(bindings) == binding_fields
        and bindings.get("preview_receipt_payload_sha256")
        == preview.get("receipt_payload_sha256")
        and bindings.get("preview_cafta_snapshot_sha256")
        == CAFTA_PREVIEW_SNAPSHOT_SHA256
        and bindings.get("generation_id") == comparison.get("generation_id")
        and bindings.get("run_identity_sha256") == comparison.get("run_identity_sha256")
        and bindings.get("evaluation_manifest_sha256")
        == comparison.get("evaluation_manifest_sha256")
        and bindings.get("rulespec") == run_identity.get("rulespec")
        and bindings.get("campaign_evaluator") == campaign_evaluator
        and bindings.get("selected_population_sha256") == selected_population["sha256"]
        and bindings.get("fresh_campaign_classifier_sha256")
        == campaign_source.get("sha256")
        and bindings.get("preview_campaign_classifier_sha256")
        == preview_campaign_source.get("sha256")
        and bindings.get("campaign_producer_identity_required") is False
        and bindings.get("campaign_semantic_equivalence_basis")
        == CAFTA_CAMPAIGN_EQUIVALENCE_BASIS
        and type(bindings.get("evaluation_shard_engine_errors")) is int
        and bindings["evaluation_shard_engine_errors"] == 0
        and type(bindings.get("observed_evaluation_record_errors")) is int
        and bindings["observed_evaluation_record_errors"] == 0
        and type(bindings.get("comparison_receipt_engine_errors")) is int
        and bindings["comparison_receipt_engine_errors"] == 0
        and type(bindings.get("evaluated_chapters")) is int
        and bindings.get("evaluated_chapters") == len(chapters)
        and type(bindings.get("evaluated_cases")) is int
        and bindings.get("evaluated_cases") == manifest_cases
        and type(bindings.get("observed_evaluated_cases")) is int
        and bindings.get("observed_evaluated_cases") == manifest_cases
        and type(manifest_cases) is int
        and manifest_cases > 0
        and bindings.get("reference_compared_field") == "statutory_rate_s301fl"
        and bindings.get("reference_rds_path") == reference_provenance["rds_path"]
        and bindings.get("reference_rds_sha256") == reference_provenance["rds_sha256"],
        "CAFTA supersession receipt run binding is stale",
    )

    zero_error_fields = {
        "evaluation_shard_engine_errors": 0,
        "observed_evaluation_record_errors": 0,
        "comparison_receipt_engine_errors": 0,
        "comparison_artifact_engine_error_rows": 0,
    }
    zero_errors = receipt.get("zero_error_proof")
    _require(
        isinstance(zero_errors, dict)
        and set(zero_errors) == set(zero_error_fields)
        and all(type(zero_errors[name]) is int for name in zero_error_fields)
        and zero_errors == zero_error_fields,
        "CAFTA supersession receipt cannot rely on engine errors",
    )
    predicates = {
        "entry_is_entered_free_of_duty_under_dr_cafta": False,
        "entry_is_general_note_29_d_v_textile_or_apparel_good": False,
    }
    predicate_proof = receipt.get("axiom_predicate_proof")
    _require(
        isinstance(predicate_proof, dict)
        and set(predicate_proof)
        == {
            "actual_case_feed_projection_sha256",
            "all_joined_actual_case_feeds_false_false",
            "chapter_contracts_checked",
            "contract_sha256",
            "joined_fresh_evaluation_records",
            "predicates",
            "scope",
        }
        and predicate_proof.get("predicates") == predicates
        and predicate_proof.get("all_joined_actual_case_feeds_false_false") is True
        and type(predicate_proof.get("joined_fresh_evaluation_records")) is int
        and predicate_proof.get("joined_fresh_evaluation_records")
        == CAFTA_EXPECTED_UNITS
        and type(predicate_proof.get("chapter_contracts_checked")) is int
        and predicate_proof.get("chapter_contracts_checked") == len(chapters)
        and predicate_proof.get("scope")
        == "all campaign cases in all 100 compiled chapters"
        and predicate_proof.get("contract_sha256")
        == expected_inputs["declared_input_contract"]["sha256"]
        and predicate_proof.get("actual_case_feed_projection_sha256")
        == CAFTA_EXPECTED_ACTUAL_CASE_FEED_PROJECTION_SHA256,
        "CAFTA supersession actual-predicate proof drift",
    )
    census = receipt.get("census")
    historical_rows_scanned = (
        census.get("historical_artifact_rows_scanned")
        if isinstance(census, dict)
        else None
    )
    fresh_rows_scanned = (
        census.get("fresh_comparison_rows_scanned")
        if isinstance(census, dict)
        else None
    )
    _require(
        isinstance(census, dict)
        and set(census)
        == {
            "historical_artifact_rows_scanned",
            "fresh_comparison_rows_scanned",
            "cafta_units",
            "cafta_signatures",
            "origin_units",
        }
        and type(historical_rows_scanned) is int
        and historical_rows_scanned == preview.get("census", {}).get("total")
        and type(fresh_rows_scanned) is int
        and fresh_rows_scanned == _comparison_observation_count(comparison)
        and type(census.get("cafta_units")) is int
        and census.get("cafta_units") == CAFTA_EXPECTED_UNITS
        and type(census.get("cafta_signatures")) is int
        and census.get("cafta_signatures") == CAFTA_EXPECTED_SIGNATURES
        and isinstance(census.get("origin_units"), dict)
        and all(type(units) is int for units in census["origin_units"].values())
        and census.get("origin_units") == CAFTA_EXPECTED_ORIGIN_UNITS,
        "CAFTA supersession receipt census drift",
    )

    supersession = receipt.get("supersession")
    supersession_fields = {
        "authorized_disposition_after_pass",
        "authorized_attribution_after_pass",
        "historical_identity_population_sha256",
        "fresh_identity_population_sha256",
        "historical_mismatch_projection_sha256",
        "historical_defect_projection_sha256",
        "fresh_defect_projection_sha256",
        "joined_historical_units",
        "missing_historical_units",
        "duplicate_historical_identities",
        "duplicate_fresh_identities",
        "fresh_mismatching_units",
        "all_present",
        "all_unique",
        "all_predicates_false",
        "all_yale_defect_zeros_reproduced",
        "all_corrected_yale_statutory_rates_match_axiom",
    }
    identity_hashes = (
        "historical_identity_population_sha256",
        "fresh_identity_population_sha256",
        "historical_mismatch_projection_sha256",
        "historical_defect_projection_sha256",
        "fresh_defect_projection_sha256",
    )
    _require(
        isinstance(supersession, dict)
        and set(supersession) == supersession_fields
        and supersession.get("authorized_disposition_after_pass")
        == "upstream_engine_gap"
        and supersession.get("authorized_attribution_after_pass") == "reference-defect"
        and all(
            isinstance(supersession.get(name), str)
            and re.fullmatch(r"[0-9a-f]{64}", supersession[name]) is not None
            for name in identity_hashes
        )
        and supersession.get("historical_identity_population_sha256")
        == CAFTA_EXPECTED_IDENTITY_POPULATION_SHA256
        and supersession.get("fresh_identity_population_sha256")
        == CAFTA_EXPECTED_IDENTITY_POPULATION_SHA256
        and supersession.get("historical_mismatch_projection_sha256")
        == CAFTA_EXPECTED_HISTORICAL_MISMATCH_PROJECTION_SHA256
        and supersession.get("historical_defect_projection_sha256")
        == CAFTA_EXPECTED_DEFECT_PROJECTION_SHA256
        and supersession.get("fresh_defect_projection_sha256")
        == CAFTA_EXPECTED_DEFECT_PROJECTION_SHA256
        and type(supersession.get("joined_historical_units")) is int
        and supersession.get("joined_historical_units") == CAFTA_EXPECTED_UNITS
        and type(supersession.get("fresh_mismatching_units")) is int
        and supersession.get("fresh_mismatching_units") == CAFTA_EXPECTED_UNITS
        and all(
            type(supersession.get(name)) is int and supersession.get(name) == 0
            for name in (
                "missing_historical_units",
                "duplicate_historical_identities",
                "duplicate_fresh_identities",
            )
        )
        and all(
            supersession.get(name) is True
            for name in (
                "all_present",
                "all_unique",
                "all_predicates_false",
                "all_yale_defect_zeros_reproduced",
                "all_corrected_yale_statutory_rates_match_axiom",
            )
        ),
        "CAFTA supersession authorization or identity proof drift",
    )
    definition = receipt.get("definition")
    yale_defect = receipt.get("yale_reference_defect")
    _require(
        definition == CAFTA_EXPECTED_DEFINITION,
        "CAFTA supersession receipt definition drift",
    )
    _validate_cafta_yale_defect_evidence(yale_defect)
    children = cafta_item.get("children")
    _require(
        isinstance(children, list)
        and len(children) == 1
        and isinstance(children[0], dict)
        and children[0].get("disposition")
        == supersession["authorized_disposition_after_pass"]
        and children[0].get("attribution")
        == supersession["authorized_attribution_after_pass"]
        and type(children[0].get("expected_units")) is int
        and children[0].get("expected_units") == CAFTA_EXPECTED_UNITS,
        "CAFTA transition child exceeds the authorized receipt ruling",
    )
    try:
        final_receipt_on_disk = json.loads(CAFTA_SUPERSESSION_RECEIPT.read_text())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "CAFTA supersession receipt changed during transition validation"
        ) from exc
    _require(
        _file_receipt(CAFTA_SUPERSESSION_RECEIPT, relative_to=REPO_ROOT)
        == expected_file
        and final_receipt_on_disk == receipt,
        "CAFTA supersession receipt changed during transition validation",
    )


def _require_current_cafta_transition_file(transition: dict[str, Any]) -> None:
    """Close the CAFTA-file TOCTOU window before classification publication."""

    raw_transitions = transition.get("transitions")
    if not isinstance(raw_transitions, list):
        return
    wrappers = [
        item.get("evidence", {}).get("cafta_supersession_receipt")
        for item in raw_transitions
        if isinstance(item, dict)
        and isinstance(item.get("evidence"), dict)
        and "cafta_supersession_receipt" in item["evidence"]
    ]
    if not wrappers:
        return
    _require(len(wrappers) == 1, "duplicate CAFTA supersession evidence")
    wrapper = wrappers[0]
    _require(
        isinstance(wrapper, dict)
        and set(wrapper) == {"file", "payload"}
        and wrapper["file"]
        == _file_receipt(CAFTA_SUPERSESSION_RECEIPT, relative_to=REPO_ROOT),
        "CAFTA supersession receipt changed before classification",
    )
    try:
        current_payload = json.loads(CAFTA_SUPERSESSION_RECEIPT.read_text())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "CAFTA supersession receipt changed before classification"
        ) from exc
    _require(
        current_payload == wrapper["payload"],
        "CAFTA supersession receipt changed before classification",
    )
    _require(
        current_payload.get("producer")
        == {
            "script": _file_receipt(CAFTA_SUPERSESSION_PRODUCER, relative_to=REPO_ROOT)
        },
        "CAFTA supersession producer changed before classification",
    )


def _preview_selector_transition_receipt(
    comparison: dict[str, Any], preview: dict[str, Any]
) -> dict[str, Any]:
    """Load a current, comparison-bound preview-selector transition receipt."""

    path = PREVIEW_SELECTOR_TRANSITION_RECEIPT
    _require(path.is_file(), f"preview selector transition receipt is missing: {path}")
    receipt = json.loads(path.read_text())
    _require(
        isinstance(receipt, dict)
        and set(receipt)
        == {
            "schema",
            "verdict",
            "producer",
            "inputs",
            "bindings",
            "zero_error_proof",
            "transitions",
            "receipt_payload_sha256",
        }
        and receipt.get("schema") == PREVIEW_SELECTOR_TRANSITION_SCHEMA
        and receipt.get("verdict") == "PASS",
        "preview selector transition receipt is not a PASS v1 receipt",
    )
    received_digest = receipt.get("receipt_payload_sha256")
    digest_payload = dict(receipt)
    digest_payload.pop("receipt_payload_sha256", None)
    _require(
        received_digest == _canonical_sha256(digest_payload),
        "preview selector transition payload digest drift",
    )
    expected_producer = {
        name: _file_receipt(source, relative_to=REPO_ROOT)
        for name, source in PREVIEW_SELECTOR_TRANSITION_PRODUCER_SOURCES.items()
    }
    _require(
        receipt.get("producer") == expected_producer,
        "preview selector transition producer source drift",
    )
    artifact_receipt = comparison.get("comparison_artifact")
    _require(
        isinstance(artifact_receipt, dict),
        "comparison artifact receipt is malformed",
    )
    expected_inputs = {
        "immutable_preview_receipt": _file_receipt(
            PREVIEW_DISPOSITION_LINE_SETS, relative_to=REPO_ROOT
        ),
        "historical_target_mismatch_artifact": preview.get("inputs", {}).get(
            PREVIEW_HISTORICAL_TARGET_PATH
        ),
        "evaluation_manifest": _file_receipt(EVAL_MANIFEST, relative_to=REPO_ROOT),
        "comparison_receipt": _file_receipt(COMPARISON_RECEIPT, relative_to=REPO_ROOT),
        "comparison_artifact": artifact_receipt,
    }
    _require(
        receipt.get("inputs") == expected_inputs,
        "preview selector transition input binding is stale",
    )
    manifest = json.loads(EVAL_MANIFEST.read_text())
    run_identity = manifest.get("run_identity")
    expected_reference_assumptions = {
        "yale_note16_metal_weight": _yale_note16_weight_assumption_identity()
    }
    _require(
        isinstance(run_identity, dict)
        and isinstance(run_identity.get("rulespec"), dict)
        and isinstance(run_identity.get("entry_flag_producers"), dict)
        and run_identity.get("reference_assumptions") == expected_reference_assumptions,
        "evaluation manifest transition provenance is malformed",
    )
    expected_bindings = {
        "preview_receipt_payload_sha256": preview.get("receipt_payload_sha256"),
        "generation_id": comparison.get("generation_id"),
        "run_identity_sha256": comparison.get("run_identity_sha256"),
        "evaluation_manifest_sha256": comparison.get("evaluation_manifest_sha256"),
        "rulespec": run_identity["rulespec"],
        "entry_flag_producers": run_identity["entry_flag_producers"],
        "reference_assumptions": expected_reference_assumptions,
    }
    _require(
        receipt.get("bindings") == expected_bindings,
        "preview selector transition run binding is stale",
    )
    shards = manifest.get("shards")
    _require(
        isinstance(shards, dict)
        and bool(shards)
        and all(
            isinstance(shard, dict)
            and isinstance(shard.get("engine_errors"), int)
            and not isinstance(shard["engine_errors"], bool)
            and shard["engine_errors"] >= 0
            for shard in shards.values()
        ),
        "evaluation manifest engine-error census is malformed",
    )
    evaluation_errors = sum(shard["engine_errors"] for shard in shards.values())
    _require(
        comparison.get("engine_errors") == 0
        and evaluation_errors == 0
        and receipt.get("zero_error_proof")
        == {
            "evaluation_shard_engine_errors": 0,
            "observed_evaluation_record_errors": 0,
            "comparison_receipt_engine_errors": 0,
            "comparison_artifact_engine_error_rows": 0,
        },
        "preview selector transition cannot rely on engine errors",
    )
    transitions = receipt.get("transitions")
    _require(
        isinstance(transitions, list) and bool(transitions),
        "preview selector transition list is malformed",
    )
    expected_parent_ids = TRANSITION_EXPECTED_PARENT_IDS
    parent_ids = [
        item.get("parent_id") if isinstance(item, dict) else None
        for item in transitions
    ]
    _require(
        len(expected_parent_ids) == PREVIEW_SELECTOR_COUNT
        and len(parent_ids) == len(set(parent_ids))
        and set(parent_ids) == expected_parent_ids,
        "preview selector transition parent coverage is incomplete",
    )
    _validate_cafta_transition_evidence(
        transitions=transitions,
        comparison=comparison,
        preview=preview,
        manifest=manifest,
        transition_inputs=expected_inputs,
    )
    return receipt


def _transition_for_entries(
    entries: list[dict[str, Any]],
    comparison: dict[str, Any],
    preview: dict[str, Any],
) -> dict[str, Any] | None:
    if not _preview_transition_is_required(entries, preview):
        return None
    return _preview_selector_transition_receipt(comparison, preview)


def _transition_flag_vector(pattern: tuple[str, ...]) -> dict[str, bool]:
    flags = {name: False for name in TRANSITION_UNCONDITIONAL_PRECEDENCE_FLAGS}
    flags.update(
        {name: name in pattern for name in TRANSITION_CANDIDATE_PRECEDENCE_FLAGS}
    )
    flags.update({name: False for name in TRANSITION_DECLARED_PRECEDENCE_FLAGS})
    flags.update({name: False for name in TRANSITION_NOTE16_MEMBERSHIP_FLAGS})
    flags[NOTE16_WEIGHT_INPUT] = True
    return flags


def _transition_pattern_name(pattern: tuple[str, ...]) -> str:
    return "+".join(pattern) if pattern else "none"


def _expected_transition_yale_source_receipt(
    preview: dict[str, Any],
) -> dict[str, Any]:
    """Rebuild the producer's exact pinned Yale annex-source identity."""

    yale_sources = preview.get("yale_sources")
    source_files = yale_sources.get("files") if isinstance(yale_sources, dict) else None
    _require(
        isinstance(yale_sources, dict)
        and set(yale_sources) == {"commit", "tree", "files"}
        and yale_sources.get("commit") == PREVIEW_YALE_COMMIT
        and yale_sources.get("tree") == PREVIEW_YALE_TREE
        and isinstance(source_files, dict),
        "preview Yale annex source identity is malformed",
    )
    files: dict[str, dict[str, Any]] = {}
    for logical_path in TRANSITION_YALE_PREVIEW_SOURCE_FILES:
        receipt = source_files.get(logical_path)
        _require(
            isinstance(receipt, dict)
            and set(receipt) == {"bytes", "sha256"}
            and type(receipt.get("bytes")) is int
            and receipt["bytes"] > 0
            and isinstance(receipt.get("sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", receipt["sha256"]) is not None,
            f"preview Yale annex source receipt drift: {logical_path}",
        )
        files[logical_path] = {"path": logical_path, **receipt}
    files[TRANSITION_YALE_PARSER_RECEIPT["path"]] = dict(TRANSITION_YALE_PARSER_RECEIPT)
    return {
        "commit": PREVIEW_YALE_COMMIT,
        "tree": PREVIEW_YALE_TREE,
        "files": dict(sorted(files.items())),
        "classification_precedence": list(TRANSITION_YALE_CLASSIFICATION_PRECEDENCE),
    }


def _validate_section232_transition_evidence(
    item: dict[str, Any],
    expected_children: list[dict[str, Any]],
    preview: dict[str, Any],
) -> frozenset[str]:
    """Authenticate producer evidence for every transition parent."""

    parent_id = item["parent_id"]
    if not parent_id.startswith("section232-"):
        parent = item["parent_contract"]
        children = item["children"]
        evidence = item["evidence"]
        _require(
            item["status"] == "superseded" and len(children) == 1,
            f"non-Section-232 transition shape drift: {parent_id}",
        )
        child = children[0]
        expected_evidence = {
            "classification": (
                "cafta-reference-defect-receipted-fresh-signature"
                if parent_id == CAFTA_PREVIEW_SELECTOR_ID
                else "fresh-signature-rebind-preserved-ruling"
            ),
            "historical_ruling": {
                field: parent[field]
                for field in ("logical_class", "disposition", "attribution")
            },
            "fresh_ruling": {
                field: child[field]
                for field in ("logical_class", "disposition", "attribution")
            },
            "child_populations": {
                child["id"]: {
                    "units": child["expected_units"],
                    "signature_count": child["expected_signature_count"],
                    "signature_population_sha256": child[
                        "expected_signature_population_sha256"
                    ],
                }
            },
        }
        if parent_id == CAFTA_PREVIEW_SELECTOR_ID:
            wrapper = evidence.get("cafta_supersession_receipt")
            _require(
                isinstance(wrapper, dict)
                and set(wrapper) == {"file", "payload"}
                and isinstance(wrapper.get("file"), dict)
                and isinstance(wrapper.get("payload"), dict),
                "CAFTA transition evidence wrapper is malformed",
            )
            expected_evidence["cafta_supersession_receipt"] = wrapper
        _require(
            evidence == expected_evidence,
            f"non-Section-232 transition evidence drift: {parent_id}",
        )
        return frozenset()
    evidence = item["evidence"]
    is_annex = "-annex-" in parent_id
    has_annex_defect = is_annex and item["status"] == "superseded"
    evidence_fields = {
        "current_precedence_true_units",
        "current_precedence_false_units",
        "candidate_pattern_units",
        "child_populations",
        "classification",
    }
    if has_annex_defect:
        evidence_fields.add("yale_annex_defect_source_proof")
    _require(
        isinstance(evidence, dict) and set(evidence) == evidence_fields,
        f"Section-232 transition evidence fields drift: {parent_id}",
    )
    _require(
        type(evidence.get("current_precedence_true_units")) is int
        and evidence["current_precedence_true_units"] == item["fresh_matching_units"]
        and type(evidence.get("current_precedence_false_units")) is int
        and evidence["current_precedence_false_units"]
        == item["fresh_residual_population"]["units"],
        f"Section-232 transition evidence census drift: {parent_id}",
    )

    if item["status"] == "retired":
        patterns: tuple[tuple[str, ...], ...] = ()
        expected_classification = "fully-fixed-exposed"
    elif is_annex:
        patterns = TRANSITION_ANNEX_PATTERNS
        expected_classification = (
            "disjoint-reference-defect-and-conditional-reference-behavior"
        )
    else:
        patterns = TRANSITION_HEADING_PATTERNS
        expected_classification = "disjoint-conditional-reference-behavior"
    actual_children = {child["id"]: child for child in item["children"]}
    expected_pattern_units = {
        _transition_pattern_name(pattern): actual_children[child["id"]][
            "expected_units"
        ]
        for pattern, child in zip(patterns, expected_children, strict=True)
    }
    expected_child_populations = {
        expected_child["id"]: {
            "candidate_pattern": _transition_pattern_name(pattern),
            "units": actual_children[expected_child["id"]]["expected_units"],
            "signature_count": actual_children[expected_child["id"]][
                "expected_signature_count"
            ],
            "signature_population_sha256": actual_children[expected_child["id"]][
                "expected_signature_population_sha256"
            ],
        }
        for pattern, expected_child in zip(patterns, expected_children, strict=True)
    }
    _require(
        evidence.get("classification") == expected_classification
        and evidence.get("candidate_pattern_units") == expected_pattern_units
        and evidence.get("child_populations") == expected_child_populations,
        f"Section-232 transition evidence ruling drift: {parent_id}",
    )
    if not has_annex_defect:
        return frozenset()

    defect_child_id = next(
        child["id"]
        for pattern, child in zip(patterns, expected_children, strict=True)
        if not pattern
    )
    defect_child = actual_children[defect_child_id]
    proof = evidence.get("yale_annex_defect_source_proof")
    proof_fields = {
        "classification",
        "units",
        "per_arm",
        "pinned_yale_source",
    }
    _require(
        isinstance(proof, dict)
        and set(proof) == proof_fields
        and proof.get("classification")
        == "pinned-yale-direct-annex-or-derivative-fallback"
        and type(proof.get("units")) is int
        and proof["units"] == defect_child["expected_units"]
        and proof.get("pinned_yale_source")
        == _expected_transition_yale_source_receipt(preview),
        f"Section-232 annex Yale source proof drift: {parent_id}",
    )
    per_arm = proof.get("per_arm")
    allowed_arms = {
        "annex_proclamation_prefix",
        "legacy_derivative_fallback",
    }
    _require(
        isinstance(per_arm, dict) and bool(per_arm) and set(per_arm) <= allowed_arms,
        f"Section-232 annex Yale source arms drift: {parent_id}",
    )
    arm_units = 0
    arm_signatures = 0
    fallback_hts10: set[str] = set()
    for arm, population in per_arm.items():
        _require(
            isinstance(population, dict)
            and set(population)
            == {
                "units",
                "signature_count",
                "signature_population_sha256",
                "hts10",
            }
            and type(population.get("units")) is int
            and population["units"] > 0
            and type(population.get("signature_count")) is int
            and 0 < population["signature_count"] <= population["units"]
            and isinstance(population.get("signature_population_sha256"), str)
            and re.fullmatch(
                r"[0-9a-f]{64}",
                population["signature_population_sha256"],
            )
            is not None
            and isinstance(population.get("hts10"), list)
            and bool(population["hts10"])
            and population["hts10"] == sorted(set(population["hts10"]))
            and all(
                isinstance(hts10, str) and re.fullmatch(r"[0-9]{10}", hts10) is not None
                for hts10 in population["hts10"]
            )
            and len(population["hts10"]) <= population["units"],
            f"Section-232 annex Yale source-arm census drift: {parent_id}: {arm}",
        )
        arm_units += population["units"]
        arm_signatures += population["signature_count"]
        if arm == "legacy_derivative_fallback":
            fallback_hts10.update(population["hts10"])
    _require(
        arm_units == defect_child["expected_units"]
        and arm_signatures == defect_child["expected_signature_count"]
        and (
            len(per_arm) > 1
            or next(iter(per_arm.values()))["signature_population_sha256"]
            == defect_child["expected_signature_population_sha256"]
        ),
        f"Section-232 annex Yale source proof does not conserve: {parent_id}",
    )
    return frozenset(fallback_hts10)


def _expected_preview_transition_semantics(
    parent_id: str, parent: dict[str, Any]
) -> tuple[str, list[dict[str, Any]]]:
    """Return the only authorized semantic transition for a preview parent."""

    if parent_id in TRANSITION_SECTION232_EXPOSED_PARENTS:
        return "retired", []
    section232_patterns: tuple[tuple[str, ...], ...] | None = None
    family = ""
    if parent_id in {
        "section232-annex-brazil",
        "section232-annex-forced-labor",
    }:
        family = "annex"
        section232_patterns = TRANSITION_ANNEX_PATTERNS
    elif parent_id in {
        "section232-heading-brazil",
        "section232-heading-forced-labor",
    }:
        family = "heading"
        section232_patterns = TRANSITION_HEADING_PATTERNS
    elif parent_id.startswith("section232-"):
        raise ValueError(f"unsupported Section-232 transition parent: {parent_id}")

    if section232_patterns is not None:
        country = "forced-labor" if parent_id.endswith("-forced-labor") else "brazil"
        children: list[dict[str, Any]] = []
        for pattern in section232_patterns:
            slug = TRANSITION_PATTERN_SLUGS[pattern]
            if family == "annex" and not pattern:
                logical_class = "section232-annex-yale-reference-defect"
                disposition = "upstream_engine_gap"
                attribution = "reference-defect"
            else:
                logical_class = (
                    f"section232-{family}-{slug}-conditional-reference-behavior"
                )
                disposition = "explained_residual"
                attribution = "reference-behavior"
            children.append(
                {
                    "id": f"section232-{family}-{slug}-{country}",
                    "parent_id": parent_id,
                    "logical_class": logical_class,
                    "disposition": disposition,
                    "attribution": attribution,
                    "match": {
                        **parent["match"],
                        "line_class": {"flags": _transition_flag_vector(pattern)},
                    },
                }
            )
        return "superseded", children

    if parent_id == CAFTA_PREVIEW_SELECTOR_ID:
        child_id = "cafta-52i-yale-reference-defect"
        logical_class = child_id
        disposition = "upstream_engine_gap"
        attribution = "reference-defect"
    else:
        child_id = f"{parent_id}-fresh-signature-rebind"
        logical_class = parent["logical_class"]
        disposition = parent["disposition"]
        attribution = parent["attribution"]
    return (
        "superseded",
        [
            {
                "id": child_id,
                "parent_id": parent_id,
                "logical_class": logical_class,
                "disposition": disposition,
                "attribution": attribution,
                "match": parent["match"],
            }
        ],
    )


def _preview_selector_snapshot(
    entries: list[dict[str, Any]],
    preview: dict[str, Any] | None = None,
    transition: dict[str, Any] | None = None,
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    """Bind active, retired, and superseded selectors to preview history.

    The receipt describes a historical mismatch population, not a requirement
    that every mismatch survive future RuleSpec fixes.  A selector may leave
    the ledger only after its receipted match population vanishes completely;
    a partially surviving selector needs a separately bound transition receipt
    whose children exactly partition its fresh residual population.
    """

    preview = _preview_disposition_receipt() if preview is None else preview
    _require_immutable_preview_all_selector_snapshot(preview)
    selectors = preview.get("selectors")
    _require(
        isinstance(selectors, list) and len(selectors) == PREVIEW_SELECTOR_COUNT,
        "preview selector census drift",
    )
    line_sets = preview.get("line_sets")
    _require(
        isinstance(line_sets, dict) and len(line_sets) == PREVIEW_SELECTOR_COUNT,
        "preview line-set census drift",
    )
    ledger_by_id: dict[str, dict[str, Any]] = {}
    for entry in entries:
        _require(isinstance(entry, dict), "disposition ledger entry is malformed")
        entry_id = entry.get("id")
        if isinstance(entry_id, str):
            _require(
                entry_id not in ledger_by_id, f"duplicate disposition id: {entry_id}"
            )
            ledger_by_id[entry_id] = entry
    expected_fields = {
        "id",
        "logical_class",
        "disposition",
        "attribution",
        "expected_units",
        "expected_signature_count",
        "expected_signature_population_sha256",
        "match",
    }
    historical: dict[str, dict[str, Any]] = {}
    receipt_ids: set[str] = set()
    for selector in selectors:
        _require(
            isinstance(selector, dict) and set(selector) == expected_fields,
            "invalid preview selector contract fields",
        )
        selector_id = selector.get("id")
        _require(
            isinstance(selector_id, str) and selector_id, "invalid preview selector id"
        )
        _require(
            selector_id not in receipt_ids,
            f"duplicate preview selector id: {selector_id}",
        )
        receipt_ids.add(selector_id)
        _require(
            isinstance(selector.get("logical_class"), str)
            and bool(selector["logical_class"]),
            f"invalid preview logical class: {selector_id}",
        )
        _require(
            isinstance(selector.get("expected_units"), int)
            and not isinstance(selector["expected_units"], bool)
            and selector["expected_units"] > 0,
            f"invalid preview expected-unit count: {selector_id}",
        )
        _require(
            isinstance(selector.get("expected_signature_count"), int)
            and not isinstance(selector["expected_signature_count"], bool)
            and selector["expected_signature_count"] > 0,
            f"invalid preview expected-signature count: {selector_id}",
        )
        _require(
            isinstance(selector.get("expected_signature_population_sha256"), str)
            and re.fullmatch(
                r"[0-9a-f]{64}", selector["expected_signature_population_sha256"]
            )
            is not None,
            f"invalid preview signature-population hash: {selector_id}",
        )
        match = selector.get("match")
        _require(
            isinstance(match, dict) and set(match) == {"slot", "line_set", "delta"},
            f"invalid preview selector match fields: {selector_id}",
        )
        _require(
            match["slot"] in {"brazil_section_301", "forced_labor_section_301"},
            f"invalid preview selector slot: {selector_id}",
        )
        _require(
            isinstance(match["line_set"], str)
            and match["line_set"].startswith("preview-1311-")
            and match["line_set"] in line_sets,
            f"invalid preview selector line set: {selector_id}",
        )
        delta = match["delta"]
        _require(
            isinstance(delta, dict) and set(delta) in ({"sign"}, {"values"}),
            f"invalid preview selector delta bound: {selector_id}",
        )
        if "sign" in delta:
            _require(
                delta["sign"] in {"pos", "neg"},
                f"invalid preview selector delta sign: {selector_id}",
            )
        else:
            values = delta["values"]
            _require(
                isinstance(values, list)
                and values
                and all(
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and math.isfinite(value)
                    for value in values
                )
                and values == sorted(set(values)),
                f"invalid preview selector delta values: {selector_id}",
            )
        historical[selector_id] = selector
    receipt_line_sets = [
        selector["match"].get("line_set")
        if isinstance(selector.get("match"), dict)
        else None
        for selector in selectors
    ]
    _require(
        len(set(receipt_line_sets)) == len(receipt_line_sets)
        and set(receipt_line_sets) == set(line_sets),
        "preview selectors and line sets are not one-to-one",
    )
    transition_by_parent: dict[str, dict[str, Any]] = {}
    child_by_id: dict[str, dict[str, Any]] = {}
    empty_population_digest = signature_population_sha256([])
    if transition is not None:
        raw_transitions = transition.get("transitions")
        _require(
            isinstance(raw_transitions, list) and raw_transitions,
            "preview selector transition list is malformed",
        )
        transition_fields = {
            "parent_id",
            "parent_contract",
            "status",
            "historical_units",
            "fresh_matching_units",
            "fresh_residual_population",
            "children",
            "evidence",
        }
        population_fields = {
            "units",
            "signature_count",
            "signature_population_sha256",
        }
        child_fields = {
            "id",
            "parent_id",
            "logical_class",
            "disposition",
            "attribution",
            "expected_units",
            "expected_signature_count",
            "expected_signature_population_sha256",
            "match",
        }
        transition_child_count = 0
        annex_fallback_hts10: set[str] = set()
        for item in raw_transitions:
            _require(
                isinstance(item, dict) and set(item) == transition_fields,
                "preview selector transition fields are malformed",
            )
            parent_id = item.get("parent_id")
            _require(
                isinstance(parent_id, str)
                and parent_id in historical
                and parent_id not in transition_by_parent,
                f"preview selector transition parent is invalid: {parent_id}",
            )
            parent = historical[parent_id]
            _require(
                item.get("parent_contract") == parent,
                f"preview selector transition parent contract drift: {parent_id}",
            )
            _require(
                item.get("status") in {"retired", "superseded"},
                f"preview selector transition status is invalid: {parent_id}",
            )
            historical_units = item.get("historical_units")
            fresh_matching_units = item.get("fresh_matching_units")
            residual = item.get("fresh_residual_population")
            _require(
                historical_units == parent["expected_units"]
                and isinstance(fresh_matching_units, int)
                and not isinstance(fresh_matching_units, bool)
                and fresh_matching_units >= 0
                and isinstance(residual, dict)
                and set(residual) == population_fields,
                f"preview selector transition census is malformed: {parent_id}",
            )
            residual_units = residual.get("units")
            residual_signatures = residual.get("signature_count")
            residual_digest = residual.get("signature_population_sha256")
            _require(
                isinstance(residual_units, int)
                and not isinstance(residual_units, bool)
                and residual_units >= 0
                and isinstance(residual_signatures, int)
                and not isinstance(residual_signatures, bool)
                and residual_signatures >= 0
                and isinstance(residual_digest, str)
                and re.fullmatch(r"[0-9a-f]{64}", residual_digest) is not None
                and residual_signatures <= residual_units
                and (
                    (
                        residual_units == residual_signatures == 0
                        and residual_digest == empty_population_digest
                    )
                    or (residual_units > 0 and residual_signatures > 0)
                )
                and fresh_matching_units + residual_units == historical_units,
                f"preview selector transition does not conserve: {parent_id}",
            )
            children = item.get("children")
            _require(
                isinstance(children, list)
                and isinstance(item.get("evidence"), dict)
                and bool(item["evidence"]),
                f"preview selector transition children are malformed: {parent_id}",
            )
            child_units = 0
            for child in children:
                _require(
                    isinstance(child, dict) and set(child) == child_fields,
                    f"preview selector transition child fields are malformed: {parent_id}",
                )
                child_id = child.get("id")
                _require(
                    isinstance(child_id, str)
                    and bool(child_id)
                    and child_id not in historical
                    and child_id not in child_by_id
                    and child.get("parent_id") == parent_id,
                    f"preview selector transition child id is invalid: {child_id}",
                )
                _require(
                    isinstance(child.get("logical_class"), str)
                    and bool(child["logical_class"])
                    and isinstance(child.get("disposition"), str)
                    and bool(child["disposition"])
                    and isinstance(child.get("attribution"), str)
                    and bool(child["attribution"]),
                    f"preview selector transition child ruling is malformed: {child_id}",
                )
                _require(
                    isinstance(child.get("expected_units"), int)
                    and not isinstance(child["expected_units"], bool)
                    and child["expected_units"] > 0
                    and isinstance(child.get("expected_signature_count"), int)
                    and not isinstance(child["expected_signature_count"], bool)
                    and child["expected_signature_count"] > 0
                    and child["expected_signature_count"] <= child["expected_units"]
                    and isinstance(
                        child.get("expected_signature_population_sha256"), str
                    )
                    and re.fullmatch(
                        r"[0-9a-f]{64}",
                        child["expected_signature_population_sha256"],
                    )
                    is not None,
                    f"preview selector transition child census is malformed: {child_id}",
                )
                child_match = child.get("match")
                parent_match = parent["match"]
                extra_fields = (
                    set(child_match) - set(parent_match)
                    if isinstance(child_match, dict)
                    else set()
                )
                _require(
                    isinstance(child_match, dict)
                    and child_match
                    and set(child_match) <= SELECTOR_FIELDS
                    and set(parent_match) <= set(child_match)
                    and all(
                        child_match[field] == selector
                        for field, selector in parent_match.items()
                    )
                    and all(child_match[field] != "any" for field in extra_fields)
                    and any(
                        field in NON_SLOT_SELECTOR_FIELDS and selector != "any"
                        for field, selector in child_match.items()
                    ),
                    "preview selector transition child does not preserve "
                    f"parent match: {child_id}",
                )
                child_units += child["expected_units"]
                child_by_id[child_id] = child
            if item["status"] == "retired":
                _require(
                    residual_units == residual_signatures == 0 and not children,
                    f"retired preview selector retains a child: {parent_id}",
                )
            else:
                _require(
                    residual_units > 0
                    and residual_signatures > 0
                    and bool(children)
                    and child_units == residual_units,
                    f"superseded preview selector child census drift: {parent_id}",
                )
            expected_status, expected_children = _expected_preview_transition_semantics(
                parent_id, parent
            )
            semantic_fields = {
                "id",
                "parent_id",
                "logical_class",
                "disposition",
                "attribution",
                "match",
            }
            actual_semantics = {
                child["id"]: {field: child[field] for field in semantic_fields}
                for child in children
            }
            expected_semantics = {child["id"]: child for child in expected_children}
            _require(
                item["status"] == expected_status
                and actual_semantics == expected_semantics,
                f"preview selector transition semantics drift: {parent_id}",
            )
            annex_fallback_hts10.update(
                _validate_section232_transition_evidence(
                    item, expected_children, preview
                )
            )
            transition_child_count += len(children)
            transition_by_parent[parent_id] = item
        _require(
            set(transition_by_parent) == set(historical),
            "preview selector transition parent coverage is incomplete",
        )
        _require(
            transition_child_count == 30,
            "preview selector transition child census is not exactly 30",
        )
        _require(
            annex_fallback_hts10
            == TRANSITION_EXPECTED_LEGACY_DERIVATIVE_FALLBACK_HTS10,
            "Section-232 annex Yale derivative-fallback population drift",
        )

    contract: dict[str, dict[str, Any]] = {}
    retired: dict[str, dict[str, Any]] = {}
    superseded: dict[str, dict[str, Any]] = {}
    for selector_id, selector in historical.items():
        transition_item = transition_by_parent.get(selector_id)
        ledger_entry = ledger_by_id.get(selector_id)
        if transition_item is not None:
            _require(
                ledger_entry is None,
                f"transitioned preview parent remains in ledger: {selector_id}",
            )
            if transition_item["status"] == "retired":
                retired[selector_id] = selector
            else:
                superseded[selector_id] = transition_item
            continue
        if ledger_entry is None:
            retired[selector_id] = selector
            continue
        _require(
            ledger_entry.get("match") == selector.get("match"),
            f"preview selector match drift: {selector_id}",
        )
        _require(
            ledger_entry.get("disposition") == selector.get("disposition"),
            f"preview selector disposition drift: {selector_id}",
        )
        _require(
            ledger_entry.get("attribution") == selector.get("attribution"),
            f"preview selector attribution drift: {selector_id}",
        )
        _require(
            ledger_entry.get("expires_on_source_change") is True,
            f"preview selector lost source-change expiry: {selector_id}",
        )
        contract[selector_id] = selector

    for child_id, child in child_by_id.items():
        ledger_entry = ledger_by_id.get(child_id)
        _require(
            ledger_entry is not None,
            f"preview selector transition child is missing from ledger: {child_id}",
        )
        _require(
            ledger_entry.get("match") == child["match"],
            f"preview selector transition child match drift: {child_id}",
        )
        _require(
            ledger_entry.get("logical_class") == child["logical_class"],
            f"preview selector transition child logical class drift: {child_id}",
        )
        _require(
            ledger_entry.get("disposition") == child["disposition"],
            f"preview selector transition child disposition drift: {child_id}",
        )
        _require(
            ledger_entry.get("attribution") == child["attribution"],
            f"preview selector transition child attribution drift: {child_id}",
        )
        _require(
            ledger_entry.get("expires_on_source_change") is True,
            f"preview selector transition child lost source-change expiry: {child_id}",
        )
        contract[child_id] = child

    for entry_id, entry in ledger_by_id.items():
        match = entry.get("match")
        line_set = match.get("line_set") if isinstance(match, dict) else None
        if line_set in line_sets:
            _require(
                entry_id in receipt_ids or entry_id in child_by_id,
                f"unreceipted preview selector in disposition ledger: {entry_id}",
            )
    census = preview.get("census", {}).get("per_selector")
    _require(
        isinstance(census, dict)
        and census
        == {
            selector_id: selector["expected_units"]
            for selector_id, selector in sorted(historical.items())
        },
        "preview selector census does not match selector contracts",
    )
    _require(
        preview.get("census", {}).get("total")
        == sum(selector["expected_units"] for selector in selectors),
        "preview selector total does not conserve",
    )
    return contract, retired, superseded


def _preview_selector_contract(
    entries: list[dict[str, Any]], preview: dict[str, Any] | None = None
) -> dict[str, dict[str, Any]]:
    """Return the still-enrolled portion of the receipted preview snapshot."""

    contract, _retired, _superseded = _preview_selector_snapshot(entries, preview)
    return contract


def _enforce_preview_selector_population(
    contract: dict[str, dict[str, Any]],
    signature_classes: dict[str, str | None],
    counts: Counter[str],
) -> None:
    """Require every still-active expiring selector to remain snapshot-exact."""

    selected: dict[str, list[tuple[str, int]]] = {
        selector_id: [] for selector_id in contract
    }
    for signature, selector_id in signature_classes.items():
        if selector_id in selected:
            selected[selector_id].append((signature, counts[signature]))
    for selector_id, expected in contract.items():
        population = selected[selector_id]
        actual_units = sum(units for _, units in population)
        _require(
            actual_units == expected["expected_units"],
            f"preview selector population expired: {selector_id}: unit count drift "
            f"(expected {expected['expected_units']}, got {actual_units})",
        )
        _require(
            len(population) == expected["expected_signature_count"],
            f"preview selector population expired: {selector_id}: signature count drift "
            f"(expected {expected['expected_signature_count']}, got {len(population)})",
        )
        actual_digest = signature_population_sha256(population)
        _require(
            actual_digest == expected["expected_signature_population_sha256"],
            f"preview selector population expired: {selector_id}: signature digest drift "
            f"(expected {expected['expected_signature_population_sha256']}, got {actual_digest})",
        )


def _enforce_retired_preview_selectors_absent(
    retired: dict[str, dict[str, Any]],
    observed: dict[str, dict[str, Any]],
    counts: Counter[str],
    *,
    engine_errors: int,
) -> None:
    """Prove that every preview selector removed from the ledger is absent."""

    _require(
        not retired
        or (
            isinstance(engine_errors, int)
            and not isinstance(engine_errors, bool)
            and engine_errors == 0
        ),
        "retired preview selector absence cannot be proven with engine errors",
    )
    for selector_id, snapshot in retired.items():
        population = [
            (signature, counts[signature])
            for signature, unit in observed.items()
            if selector_matches(unit, snapshot["match"])
        ]
        _require(
            not population,
            f"retired preview selector remains live: {selector_id}: "
            f"{sum(units for _, units in population)} units",
        )


def _enforce_preview_selector_transitions(
    superseded: dict[str, dict[str, Any]],
    observed: dict[str, dict[str, Any]],
    counts: Counter[str],
    signature_classes: dict[str, str | None],
    *,
    engine_errors: int,
) -> None:
    """Require each superseded parent to equal its disjoint child union."""

    _require(
        not superseded
        or (
            isinstance(engine_errors, int)
            and not isinstance(engine_errors, bool)
            and engine_errors == 0
        ),
        "superseded preview selector partition cannot be proven with engine errors",
    )
    for parent_id, transition in superseded.items():
        parent = transition["parent_contract"]
        parent_population = {
            signature: counts[signature]
            for signature, unit in observed.items()
            if selector_matches(unit, parent["match"])
        }
        expected_parent = transition["fresh_residual_population"]
        _require(
            sum(parent_population.values()) == expected_parent["units"],
            f"superseded preview parent unit count drift: {parent_id}",
        )
        _require(
            len(parent_population) == expected_parent["signature_count"],
            f"superseded preview parent signature count drift: {parent_id}",
        )
        _require(
            signature_population_sha256(parent_population.items())
            == expected_parent["signature_population_sha256"],
            f"superseded preview parent signature digest drift: {parent_id}",
        )
        child_ids = {child["id"] for child in transition["children"]}
        classified_child_population = {
            signature: counts[signature]
            for signature, class_id in signature_classes.items()
            if class_id in child_ids
        }
        outside_parent = set(classified_child_population) - set(parent_population)
        _require(
            not outside_parent,
            f"preview selector transition child escaped parent: {parent_id}",
        )
        _require(
            classified_child_population == parent_population,
            f"preview selector transition children do not partition parent: {parent_id}",
        )
        matched_child_population: dict[str, int] = {}
        for child in transition["children"]:
            child_id = child["id"]
            population = {
                signature: counts[signature]
                for signature, unit in observed.items()
                if selector_matches(unit, child["match"])
            }
            _require(
                sum(population.values()) == child["expected_units"],
                f"preview selector transition child unit count drift: {child_id}",
            )
            _require(
                len(population) == child["expected_signature_count"],
                f"preview selector transition child signature count drift: {child_id}",
            )
            _require(
                signature_population_sha256(population.items())
                == child["expected_signature_population_sha256"],
                f"preview selector transition child signature digest drift: {child_id}",
            )
            classified_population = {
                signature: counts[signature]
                for signature, class_id in signature_classes.items()
                if class_id == child_id
            }
            _require(
                classified_population == population,
                f"preview selector transition child classification drift: {child_id}",
            )
            if child["logical_class"] == "section232-annex-yale-reference-defect":
                arm_populations: dict[str, Counter[str]] = {
                    "annex_proclamation_prefix": Counter(),
                    "legacy_derivative_fallback": Counter(),
                }
                arm_hts10: dict[str, set[str]] = {
                    name: set() for name in arm_populations
                }
                for signature, units in population.items():
                    hts10 = observed[signature].get("hts10")
                    _require(
                        isinstance(hts10, str)
                        and re.fullmatch(r"[0-9]{10}", hts10) is not None,
                        f"Section-232 annex defect child HTS10 drift: {child_id}",
                    )
                    arm = (
                        "legacy_derivative_fallback"
                        if hts10 in TRANSITION_EXPECTED_LEGACY_DERIVATIVE_FALLBACK_HTS10
                        else "annex_proclamation_prefix"
                    )
                    arm_populations[arm][signature] = units
                    arm_hts10[arm].add(hts10)
                actual_per_arm = {
                    arm: {
                        "units": sum(arm_population.values()),
                        "signature_count": len(arm_population),
                        "signature_population_sha256": (
                            signature_population_sha256(arm_population.items())
                        ),
                        "hts10": sorted(arm_hts10[arm]),
                    }
                    for arm, arm_population in sorted(arm_populations.items())
                    if arm_population
                }
                proof = transition["evidence"]["yale_annex_defect_source_proof"]
                _require(
                    proof["per_arm"] == actual_per_arm,
                    "Section-232 annex Yale source-arm population does not "
                    f"rederive: {child_id}",
                )
            overlap = set(matched_child_population) & set(population)
            _require(
                not overlap,
                f"preview selector transition children overlap: {parent_id}",
            )
            matched_child_population.update(population)
        _require(
            matched_child_population == parent_population,
            f"preview selector transition child matches do not partition parent: {parent_id}",
        )


def _classification_inputs(
    comparison: dict[str, Any],
    disposition_ledger: Path = DISPOSITION_LEDGER,
    *,
    preview: dict[str, Any] | None = None,
    transition: dict[str, Any] | None = None,
    routing_sha256: str | None = None,
) -> dict[str, str]:
    preview = _preview_disposition_receipt() if preview is None else preview
    preview_bytes = PREVIEW_DISPOSITION_LINE_SETS.read_bytes()
    try:
        preview_on_disk = json.loads(preview_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("preview disposition receipt changed or is malformed") from exc
    _require(
        preview_on_disk == preview,
        "preview disposition receipt changed during classification",
    )
    artifact = comparison.get("comparison_artifact")
    _require(isinstance(artifact, dict), "comparison artifact receipt is malformed")
    comparison_sha = artifact.get("sha256")
    _require(
        isinstance(comparison_sha, str)
        and re.fullmatch(r"[0-9a-f]{64}", comparison_sha),
        "comparison artifact hash is malformed",
    )
    _require(COMPARISON_RECEIPT.is_file(), "comparison receipt is missing")
    comparison_bytes = COMPARISON_RECEIPT.read_bytes()
    try:
        comparison_on_disk = json.loads(comparison_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("comparison receipt changed or is malformed") from exc
    _require(
        comparison_on_disk == comparison,
        "comparison receipt changed during classification",
    )
    _require(ROUTING_ROWS.is_file(), "disposition routing artifact is missing")
    current_routing_sha256 = _sha256(ROUTING_ROWS)
    routing_sha256 = (
        current_routing_sha256 if routing_sha256 is None else routing_sha256
    )
    _require(
        isinstance(routing_sha256, str)
        and re.fullmatch(r"[0-9a-f]{64}", routing_sha256) is not None
        and current_routing_sha256 == routing_sha256,
        "disposition routing changed during classification",
    )
    inputs = {
        "comparison_artifact_sha256": comparison_sha,
        "comparison_receipt_sha256": hashlib.sha256(comparison_bytes).hexdigest(),
        "disposition_ledger_sha256": _sha256(disposition_ledger),
        "preview_disposition_receipt_sha256": hashlib.sha256(preview_bytes).hexdigest(),
        "preview_disposition_payload_sha256": preview["receipt_payload_sha256"],
        "routing_rows_sha256": routing_sha256,
    }
    if transition is not None:
        transition_bytes = PREVIEW_SELECTOR_TRANSITION_RECEIPT.read_bytes()
        try:
            transition_on_disk = json.loads(transition_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                "preview selector transition receipt changed or is malformed"
            ) from exc
        _require(
            transition_on_disk == transition,
            "preview selector transition receipt changed during classification",
        )
        _require_current_cafta_transition_file(transition)
        inputs.update(
            {
                "preview_selector_transition_receipt_sha256": hashlib.sha256(
                    transition_bytes
                ).hexdigest(),
                "preview_selector_transition_payload_sha256": transition[
                    "receipt_payload_sha256"
                ],
            }
        )
    return inputs


def _override_classification_inputs(
    comparison: dict[str, Any],
    selector_digest: str,
    *,
    routing_sha256: str | None = None,
) -> dict[str, str]:
    """Bind every mutable source used by an override classification."""

    artifact = comparison.get("comparison_artifact")
    _require(isinstance(artifact, dict), "comparison artifact receipt is malformed")
    artifact_sha256 = artifact.get("sha256")
    _require(
        isinstance(artifact_sha256, str)
        and re.fullmatch(r"[0-9a-f]{64}", artifact_sha256) is not None,
        "comparison artifact hash is malformed",
    )
    _require(COMPARISON_RECEIPT.is_file(), "comparison receipt is missing")
    comparison_bytes = COMPARISON_RECEIPT.read_bytes()
    try:
        comparison_on_disk = json.loads(comparison_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("comparison receipt changed or is malformed") from exc
    _require(
        comparison_on_disk == comparison,
        "comparison receipt changed during classification",
    )
    _require(ROUTING_ROWS.is_file(), "disposition routing artifact is missing")
    current_routing_sha256 = _sha256(ROUTING_ROWS)
    routing_sha256 = (
        current_routing_sha256 if routing_sha256 is None else routing_sha256
    )
    _require(
        isinstance(routing_sha256, str)
        and re.fullmatch(r"[0-9a-f]{64}", routing_sha256) is not None
        and current_routing_sha256 == routing_sha256,
        "disposition routing changed during classification",
    )
    return {
        "comparison_artifact_sha256": artifact_sha256,
        "comparison_receipt_sha256": hashlib.sha256(comparison_bytes).hexdigest(),
        "override_selector_sha256": selector_digest,
        "routing_rows_sha256": routing_sha256,
    }


def _classification_sidecar_path(inputs: dict[str, str]) -> Path:
    digest = _canonical_sha256(inputs)
    return CACHE_ROOT / "classify" / digest[:2] / f"{digest}.jsonl.gz"


# Order-independent commitment used to cross-bind the streamed comparison rows
# to the signature-aggregated sidecar.  Two domain-separated SHA-256 terms are
# summed modulo the secp256k1 field prime, weighted by exact multiplicity.
_POPULATION_MODULUS = 2**256 - 2**32 - 977


def _population_state() -> list[Any]:
    return [0, 0, 0, Counter()]


def _add_population_item(
    state: list[Any], item: dict[str, Any], units: int = 1
) -> None:
    _require(
        isinstance(units, int) and not isinstance(units, bool) and units > 0,
        "classification population multiplicity is invalid",
    )
    payload = json.dumps(
        item, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode()
    for index, domain in enumerate((b"\x00", b"\x01")):
        term = int.from_bytes(hashlib.sha256(domain + payload).digest(), "big")
        state[index] = (state[index] + units * term) % _POPULATION_MODULUS
    state[2] += units
    state[3][item["kind"]] += units


def _population_receipt(state: list[Any]) -> dict[str, Any]:
    return {
        "schema": "axiom_oracles.us_tariff_schedule.classification_population.v1",
        "algorithm": "two-domain-sha256-sums-mod-secp256k1-prime",
        "units": state[2],
        "units_by_kind": dict(sorted(state[3].items())),
        "accumulators": [f"{state[0]:064x}", f"{state[1]:064x}"],
    }


def _classification_population_from_aggregates(
    observed: dict[str, dict[str, Any]],
    counts: Counter[str],
    total_signature_compositions: Counter[tuple[str, ...]],
    engine_errors: int,
) -> dict[str, Any]:
    state = _population_state()
    for signature, fields in observed.items():
        _add_population_item(
            state,
            {
                "kind": "component_signature",
                "signature": signature,
                "fields": fields,
            },
            counts[signature],
        )
    for signatures, units in total_signature_compositions.items():
        _add_population_item(
            state,
            {
                "kind": "total_signature_composition",
                "signatures": list(signatures),
            },
            units,
        )
    if engine_errors:
        _add_population_item(state, {"kind": "engine_error"}, engine_errors)
    return _population_receipt(state)


def _audit_comparison_artifact(
    artifact: Path,
    *,
    expected_sha256: str,
    expected_routing_sha256: str,
    routes: dict[str, tuple[str, str]] | None = None,
) -> dict[str, Any]:
    if routes is None:
        routing_bytes = ROUTING_ROWS.read_bytes()
        _require(
            hashlib.sha256(routing_bytes).hexdigest() == expected_routing_sha256,
            "disposition routing changed during comparison audit",
        )
        routes = _routing_dispositions(routing_bytes)
    state = _population_state()
    per_slot: dict[str, Counter[str]] = {}
    engine_errors = 0
    active_case: str | None = None
    active_signatures: list[str] = []
    with _bound_gzip_text_source(artifact, expected_sha256) as source:
        for line in source:
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError("comparison artifact contains invalid JSON") from exc
            _require(isinstance(row, dict), "comparison artifact row is malformed")
            slot = row.get("slot")
            matched = row.get("match")
            _require(
                isinstance(slot, str) and isinstance(matched, bool),
                "comparison artifact row lacks slot/match state",
            )
            per_slot.setdefault(slot, Counter())[
                "match" if matched else "mismatch"
            ] += 1
            case_id = row.get("case_id")
            if case_id != active_case:
                active_signatures = []
                active_case = case_id
            if slot == "total":
                if not matched:
                    _require(
                        active_signatures,
                        "total mismatch lacks a mismatching component composition",
                    )
                    _add_population_item(
                        state,
                        {
                            "kind": "total_signature_composition",
                            "signatures": sorted(active_signatures),
                        },
                    )
                active_signatures = []
                continue
            if matched:
                continue
            if slot == "engine_error":
                engine_errors += 1
                _add_population_item(state, {"kind": "engine_error"})
                continue
            signature = mismatch_signature(row)
            fields = mismatch_unit(row, routes)
            active_signatures.append(signature)
            _add_population_item(
                state,
                {
                    "kind": "component_signature",
                    "signature": signature,
                    "fields": fields,
                },
            )
    return {
        "per_slot": {slot: dict(counter) for slot, counter in sorted(per_slot.items())},
        "engine_errors": engine_errors,
        "classification_population": _population_receipt(state),
    }


def _rederive_classification_sidecar(
    sidecar: Path, entries: list[dict[str, Any]]
) -> dict[str, Any]:
    expected_fields = {
        "slot",
        "origin_regime",
        "revision",
        "delta",
        "disposition",
        "hts10",
        "hts_line",
        "flags",
        "interval",
        "iso2",
    }
    signature_classes: dict[str, str | None] = {}
    signature_counts: Counter[str] = Counter()
    observed: dict[str, dict[str, Any]] = {}
    class_census: Counter[str] = Counter()
    per_slot: dict[str, Counter[str]] = {}
    sample_signatures: dict[str, list[str]] = {}
    component_units = 0
    component_unexplained = 0
    total_records: list[tuple[tuple[str, ...], int]] = []
    engine_errors: int | None = None
    population_state = _population_state()
    with gzip.open(sidecar, "rt") as source:
        for line in source:
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "classification sidecar contains invalid JSON"
                ) from exc
            _require(isinstance(row, dict), "classification sidecar row is malformed")
            kind = row.get("kind")
            if kind == "component_signature":
                _require(
                    set(row) == {"kind", "signature", "units", "class", "fields"},
                    "classification component sidecar row has unexpected fields",
                )
                signature = row["signature"]
                units = row["units"]
                fields = row["fields"]
                _require(
                    isinstance(signature, str)
                    and re.fullmatch(r"[0-9a-f]{64}", signature) is not None
                    and signature not in signature_classes,
                    "classification sidecar signature is invalid or duplicated",
                )
                _require(
                    isinstance(units, int)
                    and not isinstance(units, bool)
                    and units > 0,
                    "classification sidecar multiplicity is invalid",
                )
                _require(
                    isinstance(fields, dict) and set(fields) == expected_fields,
                    "classification sidecar mismatch unit is malformed",
                )
                signature_row = {
                    "slot": fields["slot"],
                    "delta": fields["delta"],
                    "context": {
                        "flags": fields["flags"],
                        "revision": fields["revision"],
                        "interval": fields["interval"],
                        "origin_regime": fields["origin_regime"],
                        "hts10": fields["hts10"],
                        "hts_line": fields["hts_line"],
                        "iso2": fields["iso2"],
                    },
                }
                _require(
                    mismatch_signature(signature_row) == signature,
                    "classification sidecar signature does not match its fields",
                )
                class_id = matching_class_id(signature, fields, entries)
                _require(
                    row["class"] == class_id,
                    "classification sidecar class does not rederive",
                )
                _add_population_item(
                    population_state,
                    {
                        "kind": "component_signature",
                        "signature": signature,
                        "fields": fields,
                    },
                    units,
                )
                signature_classes[signature] = class_id
                signature_counts[signature] = units
                observed[signature] = fields
                component_units += units
                bucket = class_id or "__unexplained__"
                per_slot.setdefault(bucket, Counter())[fields["slot"]] += units
                sample_signatures.setdefault(bucket, [])
                if len(sample_signatures[bucket]) < 5:
                    sample_signatures[bucket].append(signature)
                if class_id is None:
                    component_unexplained += units
                else:
                    class_census[class_id] += units
            elif kind == "total_signature_composition":
                _require(
                    set(row) == {"kind", "signatures", "units"},
                    "classification total-composition sidecar row has unexpected fields",
                )
                signatures = row["signatures"]
                units = row["units"]
                _require(
                    isinstance(signatures, list)
                    and signatures
                    and all(isinstance(signature, str) for signature in signatures)
                    and signatures == sorted(signatures),
                    "classification total-composition signatures are malformed",
                )
                _require(
                    isinstance(units, int)
                    and not isinstance(units, bool)
                    and units > 0,
                    "classification total-composition multiplicity is invalid",
                )
                _add_population_item(
                    population_state,
                    {
                        "kind": "total_signature_composition",
                        "signatures": signatures,
                    },
                    units,
                )
                total_records.append((tuple(signatures), units))
            elif kind == "engine_errors":
                _require(
                    set(row) == {"kind", "units"}
                    and engine_errors is None
                    and isinstance(row["units"], int)
                    and not isinstance(row["units"], bool)
                    and row["units"] >= 0,
                    "classification engine-error sidecar row is malformed",
                )
                engine_errors = row["units"]
                if engine_errors:
                    _add_population_item(
                        population_state, {"kind": "engine_error"}, engine_errors
                    )
            else:
                raise ValueError(f"unknown classification sidecar row kind: {kind!r}")
    _require(
        engine_errors is not None, "classification sidecar lacks engine-error census"
    )
    derived_total_units = 0
    total_unexplained = 0
    derived_total_compositions: Counter[str] = Counter()
    for signatures, units in total_records:
        _require(
            all(signature in signature_classes for signature in signatures),
            "classification total composition references an unknown signature",
        )
        component_classes = {signature_classes[signature] for signature in signatures}
        if None in component_classes:
            total_unexplained += units
            continue
        class_composition = tuple(sorted(component_classes))
        derived_total_units += units
        derived_total_compositions[" + ".join(class_composition)] += units
    unexplained = component_unexplained + total_unexplained + engine_errors
    classified = sum(class_census.values()) + derived_total_units
    mismatches = (
        component_units + sum(units for _, units in total_records) + engine_errors
    )
    _require(
        mismatches == classified + unexplained,
        "rederived classification sidecar does not conserve",
    )
    return {
        "mismatches": mismatches,
        "classified": classified,
        "unexplained": unexplained,
        "engine_errors": engine_errors,
        "class_census": dict(sorted(class_census.items())),
        "derived_total_units": derived_total_units,
        "derived_total_compositions": dict(sorted(derived_total_compositions.items())),
        "observed_signature_count": len(signature_classes),
        "groups": {
            name: {
                "units": sum(per_slot[name].values()),
                "per_slot": dict(sorted(per_slot[name].items())),
                "sample_signatures": sample_signatures[name],
            }
            for name in sorted(per_slot)
        },
        "classification_population": _population_receipt(population_state),
        "_signature_classes": signature_classes,
        "_signature_counts": signature_counts,
        "_observed": observed,
    }


def _validate_classification_handoff(
    comparison: dict[str, Any],
    classification: dict[str, Any],
    entries: list[dict[str, Any]],
) -> None:
    _require(
        classification.get("schema")
        == "axiom_oracles.us_tariff_schedule.classification.v2",
        "classification receipt schema is stale",
    )
    preview = _preview_disposition_receipt()
    transition = _transition_for_entries(entries, comparison, preview)
    (
        preview_contract,
        retired_preview_contract,
        superseded_preview_contract,
    ) = _preview_selector_snapshot(entries, preview, transition)
    _require(
        classification.get("inputs")
        == _classification_inputs(comparison, preview=preview, transition=transition),
        "classification receipt input binding is stale",
    )
    entry_ids = [entry.get("id") for entry in entries]
    _require(
        all(isinstance(entry_id, str) and entry_id for entry_id in entry_ids)
        and len(set(entry_ids)) == len(entry_ids),
        "disposition ledger ids are malformed",
    )
    allowed_ids = set(entry_ids)
    class_census = classification.get("class_census")
    _require(
        isinstance(class_census, dict)
        and all(
            class_id in allowed_ids
            and isinstance(units, int)
            and not isinstance(units, bool)
            and units >= 0
            for class_id, units in class_census.items()
        ),
        "classification receipt contains unknown or malformed class census entries",
    )
    _require(
        all(
            class_census.get(selector_id, 0) == selector["expected_units"]
            for selector_id, selector in preview_contract.items()
        ),
        "classification receipt preview-selector census is stale",
    )
    groups = classification.get("groups")
    _require(
        isinstance(groups, dict) and set(groups) <= allowed_ids | {"__unexplained__"},
        "classification receipt contains unknown groups",
    )
    compositions = classification.get("derived_total_compositions")
    _require(
        isinstance(compositions, dict)
        and all(
            set(composition.split(" + ")) <= allowed_ids
            and isinstance(units, int)
            and not isinstance(units, bool)
            and units >= 0
            for composition, units in compositions.items()
        ),
        "classification receipt contains unknown derived-total classes",
    )
    _require(
        classification.get("selector_count") == len(entries),
        "classification selector count is stale",
    )
    class_units = sum(class_census.values())
    derived_units = classification.get("derived_total_units")
    classified = classification.get("classified")
    unexplained = classification.get("unexplained")
    mismatches = classification.get("mismatches")
    _require(
        all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in (derived_units, classified, unexplained, mismatches)
        )
        and min(derived_units, classified, unexplained, mismatches) >= 0
        and classified == class_units + derived_units
        and mismatches == classified + unexplained,
        "classification receipt does not conserve",
    )
    _require(
        classification.get("engine_errors") == comparison.get("engine_errors"),
        "classification engine-error census is stale",
    )
    comparison_slots = comparison.get("per_slot")
    _require(
        isinstance(comparison_slots, dict)
        and all(
            isinstance(slot, dict)
            and isinstance(slot.get("mismatch", 0), int)
            and not isinstance(slot.get("mismatch", 0), bool)
            and slot.get("mismatch", 0) >= 0
            for slot in comparison_slots.values()
        )
        and mismatches
        == sum(slot.get("mismatch", 0) for slot in comparison_slots.values()),
        "classification mismatch census is stale",
    )
    sidecar_receipt = classification.get("sidecar")
    expected_sidecar = _classification_sidecar_path(classification["inputs"])
    _require(
        isinstance(sidecar_receipt, dict)
        and sidecar_receipt.get("schema")
        == "axiom_oracles.us_tariff_schedule.classification_sidecar.v2"
        and sidecar_receipt.get("path") == str(expected_sidecar)
        and isinstance(sidecar_receipt.get("sha256"), str)
        and re.fullmatch(r"[0-9a-f]{64}", sidecar_receipt["sha256"]) is not None,
        "classification sidecar receipt is stale",
    )
    _require(
        expected_sidecar.is_file()
        and _sha256(expected_sidecar) == sidecar_receipt["sha256"],
        "classification sidecar is absent or has drifted",
    )
    rederived = _rederive_classification_sidecar(expected_sidecar, entries)
    sidecar_signature_classes = rederived.pop("_signature_classes")
    sidecar_signature_counts = rederived.pop("_signature_counts")
    sidecar_observed = rederived.pop("_observed")
    _enforce_preview_selector_population(
        preview_contract, sidecar_signature_classes, sidecar_signature_counts
    )
    _enforce_retired_preview_selectors_absent(
        retired_preview_contract,
        sidecar_observed,
        sidecar_signature_counts,
        engine_errors=rederived["engine_errors"],
    )
    _enforce_preview_selector_transitions(
        superseded_preview_contract,
        sidecar_observed,
        sidecar_signature_counts,
        sidecar_signature_classes,
        engine_errors=rederived["engine_errors"],
    )
    for field, expected in rederived.items():
        _require(
            classification.get(field) == expected,
            f"classification {field} does not rederive from sidecar",
        )
    artifact_path = Path(comparison["comparison_artifact"].get("path", ""))
    _require(
        artifact_path.is_file()
        and _sha256(artifact_path)
        == classification["inputs"]["comparison_artifact_sha256"],
        "comparison artifact is absent or has drifted",
    )
    artifact_audit = _audit_comparison_artifact(
        artifact_path,
        expected_sha256=classification["inputs"]["comparison_artifact_sha256"],
        expected_routing_sha256=classification["inputs"]["routing_rows_sha256"],
    )
    _require(
        comparison.get("per_slot") == artifact_audit["per_slot"],
        "comparison per-slot census does not rederive from artifact",
    )
    _require(
        comparison.get("engine_errors") == artifact_audit["engine_errors"],
        "comparison engine-error census does not rederive from artifact",
    )
    _require(
        rederived["classification_population"]
        == artifact_audit["classification_population"],
        "classification sidecar population is not derived from comparison artifact",
    )
    _require(
        classification.get("conservation") == "PASS",
        "classification conservation verdict is missing",
    )


@cache
def _named_line_sets() -> dict[str, tuple[tuple[int, frozenset[str]], ...]]:
    tables = {
        stem: _membership_rules(INCIDENCE_ROOT / f"{stem}.yaml")
        for stem in (
            "note16-232-steel",
            "note19-232-aluminum",
            "note20-china-301",
            "note2aa-122-exemptions",
        )
    }
    metal = tuple(tables["note16-232-steel"].values()) + tuple(
        tables["note19-232-aluminum"].values()
    )
    note20 = tuple(tables["note20-china-301"].values())
    s122 = tables["note2aa-122-exemptions"]
    unconditional = tuple(
        value for name, value in s122.items() if "aa_ii_" in name or "aa_iii_" in name
    )
    gn6 = tuple(
        value
        for name, value in s122.items()
        if "aa_iv_" in name or "gn6_conditional" in name
    )
    result = {
        "metal-membership-union": metal,
        "not-metal-membership-union": metal,
        "note20-membership-union": note20,
        "not-note20-membership-union": note20,
        "s122-unconditional-membership": unconditional,
        "s122-gn6-conditional-membership": gn6,
        "s122-no-exemption-membership": unconditional + gn6,
        "chapter-98-lines": ((2, frozenset({"98"})),),
    }
    preview = _preview_disposition_receipt()
    for name, receipt in preview.get("line_sets", {}).items():
        width = receipt.get("width")
        values = receipt.get("values")
        _require(
            isinstance(name, str)
            and name.startswith("preview-1311-")
            and width == 10
            and isinstance(values, list)
            and values,
            "invalid preview disposition line-set entry",
        )
        _require(
            values == sorted(set(values))
            and all(
                isinstance(value, str) and len(value) == width and value.isdigit()
                for value in values
            ),
            f"invalid exact HTS10 values in {name}",
        )
        _require(
            receipt.get("value_count") == len(values), f"line-set count drift: {name}"
        )
        _require(
            receipt.get("values_sha256")
            == hashlib.sha256(("\n".join(values) + "\n").encode()).hexdigest(),
            f"line-set value hash drift: {name}",
        )
        _require(name not in result, f"duplicate named line set: {name}")
        result[name] = ((width, frozenset(values)),)
    _require(
        len(preview.get("selectors", [])) == PREVIEW_SELECTOR_COUNT,
        "preview selector census drift",
    )
    return result


def _line_set_contains(unit: dict[str, Any], name: str) -> bool:
    _require(name in _named_line_sets(), f"unknown line_set {name}")
    code = unit["hts10"]
    member = any(code[:width] in values for width, values in _named_line_sets()[name])
    if name == "s122-gn6-conditional-membership":
        return member and not code.startswith("98")
    if name == "s122-unconditional-membership":
        gn6 = any(
            code[:width] in values
            for width, values in _named_line_sets()["s122-gn6-conditional-membership"]
        )
        return member and not gn6 and not code.startswith("98")
    if name.startswith("not-") or name == "s122-no-exemption-membership":
        return not member and not (
            name == "s122-no-exemption-membership" and code.startswith("98")
        )
    return member


def selector_matches(unit: dict[str, Any], match: dict[str, Any]) -> bool:
    _require(
        isinstance(match, dict) and match,
        "structured selector match must be a nonempty mapping",
    )
    _require(
        set(match) <= SELECTOR_FIELDS,
        f"unknown selector fields: {sorted(set(match) - SELECTOR_FIELDS)}",
    )
    _require(
        not all(selector == "any" for selector in match.values()),
        "universal disposition selector is forbidden",
    )
    _require(
        any(
            field in NON_SLOT_SELECTOR_FIELDS and selector != "any"
            for field, selector in match.items()
        ),
        "slot-only disposition selector is forbidden; a non-slot bound is required",
    )
    for field, selector in match.items():
        if field in {"slot", "origin_regime", "revision", "disposition", "iso2"}:
            if field == "slot":
                _require(
                    isinstance(selector, str) and selector,
                    "selector slot must be an exact string",
                )
                if unit[field] != selector:
                    return False
            elif not _match_scalar_or_list(unit[field], selector, field):
                return False
        elif field == "delta":
            if selector == "any":
                continue
            _require(
                isinstance(selector, dict)
                and set(selector) <= {"sign", "min", "max", "values"},
                "selector delta must be any or a sign/min/max/values mapping",
            )
            _require(
                selector and selector.get("sign") in {None, "pos", "neg"},
                "invalid delta sign",
            )
            if "values" in selector:
                values = selector["values"]
                _require(
                    isinstance(values, list)
                    and values
                    and all(isinstance(v, (int, float)) for v in values),
                    "selector delta values must be a nonempty numeric list",
                )
                exact_values = _delta_value_set(values)
                if unit[field] not in exact_values and not any(
                    abs(unit[field] - value) <= TOLERANCE for value in values
                ):
                    return False
            if selector.get("sign") == "pos" and unit[field] <= 0:
                return False
            if selector.get("sign") == "neg" and unit[field] >= 0:
                return False
            if "min" in selector and unit[field] < selector["min"]:
                return False
            if "max" in selector and unit[field] > selector["max"]:
                return False
        elif field == "line_class" and not _match_line_class(unit, selector):
            return False
        elif field == "line_set":
            _require(
                isinstance(selector, str) and selector, "line_set must be a named set"
            )
            if not _line_set_contains(unit, selector):
                return False
        elif field == "date":
            _require(
                isinstance(selector, dict)
                and selector
                and set(selector) <= {"from", "through"},
                "date selector must be a from/through mapping",
            )
            start, end = unit["interval"]
            if selector.get("from") and start < selector["from"]:
                return False
            if selector.get("through") and end > selector["through"]:
                return False
    return True


def validate_dispositions(
    entries: list[dict[str, Any]], observed: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    selectors: list[dict[str, Any]] = []
    claimed_signatures: set[str] = set()
    for entry in entries:
        _require(
            isinstance(entry.get("id"), str) and entry["id"], "disposition lacks id"
        )
        signatures = entry.get("signatures", [])
        match = entry.get("match")
        _require(
            bool(signatures) != bool(match),
            f"disposition {entry['id']} must have exactly one of signatures or match",
        )
        evidence = entry.get("evidence", {})
        _require(
            evidence.get("instrument_receipt") and evidence.get("receipt_type"),
            f"disposition {entry.get('id')} lacks instrument receipt fields",
        )
        _require(
            entry.get("attribution") and entry.get("receipt") and entry.get("reason"),
            f"disposition {entry.get('id')} lacks attribution/receipt/reason",
        )
        for signature in signatures:
            _require(signature in observed, f"stale disposition signature {signature}")
            _require(
                signature not in claimed_signatures,
                f"overlapping disposition signature {signature}",
            )
            claimed_signatures.add(signature)
        if match:
            # Schema validation is independent of whether this particular census
            # happens to contain a matching row.
            selector_matches(
                next(
                    iter(observed.values()),
                    {
                        "slot": "base",
                        "origin_regime": "x",
                        "revision": "x",
                        "delta": 1.0,
                        "disposition": "free",
                        "hts10": "0000000000",
                        "hts_line": "0000000000",
                        "flags": {},
                        "interval": ["", ""],
                        "iso2": "US",
                    },
                ),
                match,
            )
        selectors.append(entry)
    return selectors


def matching_class_id(
    signature: str, unit: dict[str, Any], selectors: list[dict[str, Any]]
) -> str | None:
    matches = [
        entry["id"]
        for entry in selectors
        if signature in entry.get("signatures", [])
        or (entry.get("match") and selector_matches(unit, entry["match"]))
    ]
    _require(
        len(matches) <= 1,
        f"classification conservation failure: overlapping selectors {matches} for {signature}",
    )
    return matches[0] if matches else None


def _require_current_classification_publication(
    *,
    comparison: dict[str, Any],
    disposition_ledger: Path,
    entries: list[dict[str, Any]],
    preview: dict[str, Any],
    transition: dict[str, Any] | None,
    classification_inputs: dict[str, str],
    artifact: Path,
    sidecar: Path,
    sidecar_sha256: str,
    rulespec_root: Path | None = None,
    engine_binary: Path | None = None,
) -> None:
    """Revalidate every mutable classification input immediately before publish."""

    if rulespec_root is not None or engine_binary is not None:
        _require(
            rulespec_root is not None and engine_binary is not None,
            "classification run-identity revalidation is incomplete",
        )
        current_comparison = _load_bound_comparison_locked(
            rulespec_root=rulespec_root,
            engine_binary=engine_binary,
        )
        _require(
            current_comparison == comparison,
            "bound comparison changed before classification publication",
        )
    current_ledger = yaml.safe_load(disposition_ledger.read_text())
    _require(
        isinstance(current_ledger, dict)
        and current_ledger.get("suite") == "us-tariff-schedule"
        and current_ledger.get("entries") == entries,
        "classification disposition ledger changed before publication",
    )
    current_preview = _preview_disposition_receipt()
    _require(
        current_preview == preview,
        "preview disposition receipt changed before classification publication",
    )
    current_transition = _transition_for_entries(entries, comparison, current_preview)
    _require(
        current_transition == transition,
        "preview selector transition changed before classification publication",
    )
    current_inputs = _classification_inputs(
        comparison,
        disposition_ledger,
        preview=current_preview,
        transition=current_transition,
        routing_sha256=classification_inputs.get("routing_rows_sha256"),
    )
    _require(
        current_inputs == classification_inputs,
        "classification inputs changed before publication",
    )
    _require(
        artifact.is_file()
        and _sha256(artifact) == comparison["comparison_artifact"]["sha256"],
        "comparison artifact changed before classification publication",
    )
    _require(
        sidecar.is_file() and _sha256(sidecar) == sidecar_sha256,
        "classification sidecar changed before publication",
    )


def _publish_classification_receipt(
    receipt: dict[str, Any], require_current: Callable[[], None]
) -> None:
    """Publish only while the receipt's complete mutable input set stays current."""

    require_current()
    rendered = _render(receipt)
    published = False
    try:
        _atomic_json(CLASSIFICATION_RECEIPT, receipt)
        published = True
        _require(
            CLASSIFICATION_RECEIPT.is_file()
            and CLASSIFICATION_RECEIPT.read_text() == rendered,
            "classification receipt changed during publication",
        )
        require_current()
        _require(
            CLASSIFICATION_RECEIPT.is_file()
            and CLASSIFICATION_RECEIPT.read_text() == rendered,
            "classification receipt changed during publication",
        )
    except Exception:
        if published and CLASSIFICATION_RECEIPT.is_file():
            CLASSIFICATION_RECEIPT.unlink()
        raise


def classify_campaign(
    *,
    rulespec_root: Path = RULESPEC_US_ROOT,
    engine_binary: Path = DEFAULT_ENGINE_BINARY,
    disposition_ledger: Path = DISPOSITION_LEDGER,
    entries_override: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    with _eval_manifest_lock():
        return _classify_campaign_locked(
            rulespec_root=rulespec_root,
            engine_binary=engine_binary,
            disposition_ledger=disposition_ledger,
            entries_override=entries_override,
        )


def _classify_campaign_locked(
    *,
    rulespec_root: Path,
    engine_binary: Path,
    disposition_ledger: Path,
    entries_override: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    comparison = _load_bound_comparison_locked(
        rulespec_root=rulespec_root, engine_binary=engine_binary
    )
    artifact = Path(comparison["comparison_artifact"]["path"])
    _require(
        _sha256(artifact) == comparison["comparison_artifact"]["sha256"],
        "comparison artifact hash mismatch",
    )
    observed: dict[str, dict[str, Any]] = {}
    counts: Counter[str] = Counter()
    total_signature_compositions: Counter[tuple[str, ...]] = Counter()
    routing_bytes = ROUTING_ROWS.read_bytes()
    routing_sha256 = hashlib.sha256(routing_bytes).hexdigest()
    routes = _routing_dispositions(routing_bytes)
    engine_errors = 0
    active_case: str | None = None
    active_signatures: list[str] = []
    with _bound_gzip_text_source(
        artifact, comparison["comparison_artifact"]["sha256"]
    ) as source:
        for line in source:
            row = json.loads(line)
            case_id = row.get("case_id")
            if case_id != active_case:
                # Components-only non-ad-valorem cases intentionally have no
                # comparable total row; their component classes do not derive
                # a total classification unit.
                active_signatures = []
                active_case = case_id
            if row["slot"] == "total":
                if not row["match"]:
                    _require(
                        active_signatures,
                        "total mismatch lacks a mismatching component composition",
                    )
                    total_signature_compositions[tuple(sorted(active_signatures))] += 1
                active_signatures = []
                continue
            if row["match"]:
                continue
            if row["slot"] == "engine_error":
                engine_errors += 1
                continue
            signature = mismatch_signature(row)
            counts[signature] += 1
            observed.setdefault(signature, mismatch_unit(row, routes))
            active_signatures.append(signature)
    ledger = yaml.safe_load(disposition_ledger.read_text())
    _require(ledger.get("suite") == "us-tariff-schedule", "wrong disposition suite")
    entries = (
        ledger.get("entries", []) if entries_override is None else entries_override
    )
    if entries_override is None:
        preview = _preview_disposition_receipt()
        transition = _transition_for_entries(entries, comparison, preview)
        (
            preview_contract,
            retired_preview_contract,
            superseded_preview_contract,
        ) = _preview_selector_snapshot(entries, preview, transition)
    else:
        preview = transition = None
        preview_contract = retired_preview_contract = superseded_preview_contract = None
    selectors = validate_dispositions(entries, observed)
    signature_classes = {
        signature: matching_class_id(signature, unit, selectors)
        for signature, unit in observed.items()
    }
    if preview_contract is not None:
        _enforce_preview_selector_population(
            preview_contract, signature_classes, counts
        )
        _enforce_retired_preview_selectors_absent(
            retired_preview_contract or {},
            observed,
            counts,
            engine_errors=engine_errors,
        )
        _enforce_preview_selector_transitions(
            superseded_preview_contract or {},
            observed,
            counts,
            signature_classes,
            engine_errors=engine_errors,
        )
    census: Counter[str] = Counter()
    derived_total_compositions: Counter[str] = Counter()
    per_slot: dict[str, Counter[str]] = {}
    sample_signatures: dict[str, list[str]] = {}
    unexplained = engine_errors
    derived_total_units = 0
    for signature_composition, units in total_signature_compositions.items():
        component_classes = {
            signature_classes[signature] for signature in signature_composition
        }
        if None in component_classes:
            unexplained += units
            continue
        class_composition = tuple(sorted(component_classes))
        derived_total_units += units
        derived_total_compositions[" + ".join(class_composition)] += units
    selector_digest = (
        _sha256(disposition_ledger)
        if entries_override is None
        else hashlib.sha256(_render(entries).encode()).hexdigest()
    )
    classification_inputs = (
        _classification_inputs(
            comparison,
            disposition_ledger,
            preview=preview,
            transition=transition,
            routing_sha256=routing_sha256,
        )
        if entries_override is None
        else _override_classification_inputs(
            comparison,
            selector_digest,
            routing_sha256=routing_sha256,
        )
    )
    digest = hashlib.sha256(
        (comparison["comparison_artifact"]["sha256"] + selector_digest).encode()
    ).hexdigest()
    sidecar = (
        _classification_sidecar_path(classification_inputs)
        if entries_override is None
        else CACHE_ROOT / "classify" / digest[:2] / f"{digest}.jsonl.gz"
    )
    classification_population = _classification_population_from_aggregates(
        observed, counts, total_signature_compositions, engine_errors
    )
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=sidecar.parent, delete=False) as raw:
        temporary = Path(raw.name)
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            for signature, unit in observed.items():
                count = counts[signature]
                class_id = signature_classes[signature]
                bucket = class_id or "__unexplained__"
                per_slot.setdefault(bucket, Counter())[unit["slot"]] += count
                sample_signatures.setdefault(bucket, [])
                if len(sample_signatures[bucket]) < 5:
                    sample_signatures[bucket].append(signature)
                zipped.write(
                    (
                        json.dumps(
                            {
                                "kind": "component_signature",
                                "signature": signature,
                                "units": count,
                                "class": class_id,
                                "fields": unit,
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n"
                    ).encode()
                )
                if class_id is None:
                    unexplained += count
                else:
                    census[class_id] += count
            for signature_composition, units in total_signature_compositions.items():
                zipped.write(
                    (
                        json.dumps(
                            {
                                "kind": "total_signature_composition",
                                "signatures": list(signature_composition),
                                "units": units,
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n"
                    ).encode()
                )
            zipped.write(
                (
                    json.dumps(
                        {"kind": "engine_errors", "units": engine_errors},
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                ).encode()
            )
    produced_sidecar_sha256 = _install_classification_sidecar(temporary, sidecar)
    mismatch_total = (
        sum(counts.values())
        + sum(total_signature_compositions.values())
        + engine_errors
    )
    _require(
        mismatch_total == sum(census.values()) + derived_total_units + unexplained,
        "classification conservation failure",
    )
    receipt = {
        "schema": "axiom_oracles.us_tariff_schedule.classification.v2",
        "inputs": classification_inputs,
        "mismatches": mismatch_total,
        "classified": sum(census.values()) + derived_total_units,
        "unexplained": unexplained,
        "engine_errors": engine_errors,
        "class_census": dict(sorted(census.items())),
        "derived_total_units": derived_total_units,
        "derived_total_compositions": dict(sorted(derived_total_compositions.items())),
        "classification_population": classification_population,
        "observed_signature_count": len(observed),
        "selector_count": len(selectors),
        "groups": {
            name: {
                "units": sum(per_slot[name].values()),
                "per_slot": dict(sorted(per_slot[name].items())),
                "sample_signatures": sample_signatures[name],
            }
            for name in sorted(per_slot)
        },
        "sidecar": {
            "schema": "axiom_oracles.us_tariff_schedule.classification_sidecar.v2",
            "path": str(sidecar),
            "sha256": produced_sidecar_sha256,
        },
        "conservation": "PASS",
    }
    if entries_override is None:

        def require_current_publication() -> None:
            _require_current_classification_publication(
                comparison=comparison,
                disposition_ledger=disposition_ledger,
                entries=entries,
                preview=preview,
                transition=transition,
                classification_inputs=classification_inputs,
                artifact=artifact,
                sidecar=sidecar,
                sidecar_sha256=receipt["sidecar"]["sha256"],
                rulespec_root=rulespec_root,
                engine_binary=engine_binary,
            )

    else:

        def require_current_publication() -> None:
            current_comparison = _load_bound_comparison_locked(
                rulespec_root=rulespec_root,
                engine_binary=engine_binary,
            )
            _require(
                current_comparison == comparison
                and _override_classification_inputs(
                    current_comparison,
                    selector_digest,
                    routing_sha256=classification_inputs["routing_rows_sha256"],
                )
                == classification_inputs
                and artifact.is_file()
                and _sha256(artifact)
                == current_comparison["comparison_artifact"]["sha256"]
                and sidecar.is_file()
                and _sha256(sidecar) == receipt["sidecar"]["sha256"],
                "override classification inputs changed before publication",
            )

    _publish_classification_receipt(receipt, require_current_publication)
    return receipt


def enforce_excluded_exposure(exposure: dict[str, Any]) -> None:
    for column in ("statutory_rate_301_cs", "statutory_rate_other"):
        value = exposure.get(column)
        _require(
            isinstance(value, (int, float)) and value == value and value == 0,
            f"X1 excluded-column exposure is nonzero or missing: {column}={value!r}",
        )


def computed_conformant(*, unexplained: int, engine_errors: int) -> bool:
    return unexplained == 0 and engine_errors == 0


def build_report(
    *,
    rulespec_root: Path = RULESPEC_US_ROOT,
    engine_binary: Path = DEFAULT_ENGINE_BINARY,
) -> dict[str, Any]:
    with _eval_manifest_lock():
        return _build_report_locked(
            rulespec_root=rulespec_root,
            engine_binary=engine_binary,
        )


def _build_report_locked(*, rulespec_root: Path, engine_binary: Path) -> dict[str, Any]:
    comparison = _load_bound_comparison_locked(
        rulespec_root=rulespec_root, engine_binary=engine_binary
    )
    classification = json.loads(CLASSIFICATION_RECEIPT.read_text())
    quotient = json.loads((OUT_DIR / "quotient-receipt.json").read_text())
    routing = json.loads(ROUTING_RECEIPT.read_text())
    exposure = json.loads((OUT_DIR / "full-exposure.json").read_text())
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    _require(
        isinstance(ledger, dict) and ledger.get("suite") == "us-tariff-schedule",
        "wrong disposition suite",
    )
    ledger_entries = ledger.get("entries")
    _require(
        isinstance(ledger_entries, list), "disposition ledger entries are malformed"
    )
    _validate_classification_handoff(comparison, classification, ledger_entries)
    enforce_excluded_exposure(exposure)
    per_slot = comparison["per_slot"]
    matches = sum(item.get("match", 0) for item in per_slot.values())
    mismatches = sum(item.get("mismatch", 0) for item in per_slot.values())
    unexplained = classification["unexplained"]
    conformant = computed_conformant(
        unexplained=unexplained, engine_errors=comparison["engine_errors"]
    )
    scope_sentence = (
        routing["scope_statement"]
        + f" ({routing['non_ad_valorem_share'] * 100:.4f}%; components-only)."
    )
    entries = {entry["id"]: entry for entry in ledger_entries}
    class_attribution = {
        name: {
            "units": classification["class_census"].get(name, 0),
            "attribution": entry["attribution"],
            "receipt": entry["receipt"],
            "bounds": entry["match"],
        }
        for name, entry in entries.items()
    }
    open_classes = {
        name: item
        for name, item in class_attribution.items()
        if item["attribution"] == "axiom-attributed-open"
    }
    report = {
        "schema": "axiom.comparison_report.v2",
        "suite": "us-tariff-schedule",
        "title": "US tariff full schedule — Axiom bulk path vs Yale statutory panel",
        "conformant": conformant,
        "summary": {
            "total": matches + mismatches,
            "matches": matches,
            "mismatches": mismatches,
            "explained": classification["classified"],
            "unexplained": unexplained,
            "engine_errors": comparison["engine_errors"],
        },
        "output_summary": per_slot,
        "column_exposure": exposure,
        "scope": {
            "full_universe_interval_cells": quotient["full_interval_cells"],
            "evaluated_quotient_interval_cells": quotient["evaluated_interval_cells"],
            "trajectory_quotient_label": "lossless partition of the EXPECTED side",
            "components_only_interval_cells": routing[
                "non_ad_valorem_components_only_cells"
            ],
            "components_only_share": routing["non_ad_valorem_share"],
            "components_only_statement": scope_sentence,
            "limitation": "This comparison does not prove identical behavior across grouped countries. It does not prove identical Axiom behavior for unprobed countries grouped by Yale trajectory.",
            "open": {
                "status": "OPEN",
                "axiom_attributed_open_classes": open_classes,
                "statement": "Upstream-methodology classes are receipted divergences, not agreement.",
            },
        },
        "classification": classification | {"class_attribution": class_attribution},
        "scoreboard": {
            "gate": "S1",
            "conformant": conformant,
            "derivation": "unexplained == 0 and engine_errors == 0",
        },
    }
    _atomic_json(REPORT_PATH, report)
    return report


def _witness_surface(summary: dict[str, Any]) -> dict[str, Any]:
    # The replay-invariant raw comparison surface. The regenerated detail
    # legitimately differs in run date and truncated example ordering, so
    # W1 compares this surface, not file bytes.
    concept = {
        row["value"]: row["count"] for row in summary.get("mismatches_by_concept", [])
    }
    return {
        "comparison_count": summary.get("comparison_count"),
        "match_count": summary.get("match_count"),
        "mismatch_count": summary.get("mismatch_count"),
        "error_count": summary.get("error_count"),
        "internal_component_sum_inconsistencies": summary.get(
            "internal_component_sum_inconsistencies"
        ),
        "mismatches_by_concept": concept,
    }


def witness_replay(*, execute: bool = False) -> dict[str, Any]:
    dashboard = REPO_ROOT / "dashboard/public/data/axiom-yale-us-tariff-panel.json"
    _require(dashboard.is_file(), "missing committed us-tariff-panel detail")
    before = dashboard.read_bytes()
    payload = json.loads(before)
    summary = payload.get("summary", {})
    dispositioned = summary.get("dispositioned", {})
    verdict = (
        summary.get("error_count") == 0 and dispositioned.get("unexplained_count") == 0
    )
    _require(verdict, "us-tariff-panel witness is not conformant")
    fresh_surface = None
    if execute:
        try:
            subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts/run_comparison.py"),
                    "us-tariff-panel",
                ],
                check=True,
            )
            fresh = json.loads(dashboard.read_bytes())
            fresh_surface = _witness_surface(fresh.get("summary", {}))
            _require(
                fresh_surface == _witness_surface(summary),
                "us-tariff-panel raw comparison surface changed during replay",
            )
        finally:
            dashboard.write_bytes(before)
    _require(
        dashboard.read_bytes() == before, "us-tariff-panel detail bytes not restored"
    )
    receipt = {
        "schema": "axiom_oracles.us_tariff_schedule.witness_replay.v1",
        "conformant": True,
        "detail_sha256": hashlib.sha256(before).hexdigest(),
        "byte_stable": True,
        "surface_reproduced": fresh_surface is not None,
        "surface": _witness_surface(summary),
    }
    if execute:
        _atomic_json(WITNESS_REPLAY_RECEIPT, receipt)
    return receipt


def _require_rulespec_root_consistency(requested: Path) -> None:
    configured = RULESPEC_US_ROOT.resolve()
    _require(
        requested.resolve() == configured,
        "--rulespec-root must match the import-time RULESPEC_US_CHECKOUT "
        f"({configured}); export RULESPEC_US_CHECKOUT={requested.resolve()} before "
        "invoking the campaign",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        epilog=(
            "For a RuleSpec rebind, export RULESPEC_US_CHECKOUT before starting "
            "this process; disposition incidence tables are bound at import time. "
            "Example: RULESPEC_US_CHECKOUT=/path/to/rulespec-us "
            "python scripts/us_tariff_schedule_campaign.py input-contract && "
            "python scripts/us_tariff_schedule_campaign.py evaluate --fresh"
        )
    )
    parser.add_argument(
        "stage",
        choices=(
            "prepass",
            "input-contract",
            "projection",
            "evaluate",
            "compare",
            "classify",
            "report",
            "witness-replay",
        ),
    )
    parser.add_argument("--rulespec-root", type=Path, default=RULESPEC_US_ROOT)
    parser.add_argument("--engine-binary", type=Path, default=DEFAULT_ENGINE_BINARY)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument(
        "--chapters", help="comma-separated chapters, for example CH01,CH72"
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="start evaluation from an empty manifest and invalidate downstream bindings",
    )
    args = parser.parse_args()
    _require_rulespec_root_consistency(args.rulespec_root)
    started = time.perf_counter()
    if args.stage == "projection":
        receipt = evaluate_projection(
            rulespec_root=args.rulespec_root.resolve(),
            engine_binary=args.engine_binary.resolve(),
        )
        print(_render(receipt), end="")
        return 0 if receipt["verdict"] == "PASS" else 2
    if args.stage == "evaluate":
        chapters = (
            None
            if not args.chapters
            else [
                item.strip().upper().removeprefix("CH")
                for item in args.chapters.split(",")
            ]
        )
        receipt = evaluate_campaign(
            rulespec_root=args.rulespec_root.resolve(),
            engine_binary=args.engine_binary.resolve(),
            workers=args.workers,
            chapters=chapters,
            resume=args.resume,
            fresh=args.fresh,
        )
        print(_render(receipt), end="")
        return 0
    if args.stage == "compare":
        print(
            _render(
                compare_campaign(
                    rulespec_root=args.rulespec_root.resolve(),
                    engine_binary=args.engine_binary.resolve(),
                )
            ),
            end="",
        )
        return 0
    if args.stage == "classify":
        print(
            _render(
                classify_campaign(
                    rulespec_root=args.rulespec_root.resolve(),
                    engine_binary=args.engine_binary.resolve(),
                )
            ),
            end="",
        )
        return 0
    if args.stage == "report":
        print(
            _render(
                build_report(
                    rulespec_root=args.rulespec_root.resolve(),
                    engine_binary=args.engine_binary.resolve(),
                )
            ),
            end="",
        )
        return 0
    if args.stage == "witness-replay":
        print(_render(witness_replay(execute=True)), end="")
        return 0
    if args.stage == "input-contract":
        _require(args.engine_binary is not None, "--engine-binary is required")
        receipt = build_input_contract_receipt(
            rulespec_root=args.rulespec_root.resolve(),
            engine_binary=args.engine_binary.resolve(),
        )
        receipt["stage_wall_clock_seconds"] = round(time.perf_counter() - started, 3)
        INPUT_CONTRACT_RECEIPT.write_text(_render(receipt))
        print(_render(receipt), end="")
        return 0
    rows, receipt = build_prepass(rulespec_root=args.rulespec_root.resolve())
    receipt["stage_wall_clock_seconds"] = round(time.perf_counter() - started, 3)
    write_prepass(rows, receipt)
    print(_render(receipt), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
