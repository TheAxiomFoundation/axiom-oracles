#!/usr/bin/env python3
"""Prove fail-closed transitions from historical tariff preview selectors.

The immutable preview receipt records historical mismatch populations.  A
partially fixed population must not be relabeled in place or treated as fully
retired.  This producer joins every historical Section-232 identity to the
current evaluation and comparison, proves the exact match/residual partition,
and emits current child contracts for the residual only.

The original all-match equivalence producer remains the full-closure guard.
This producer does not weaken or replace its ``match=true`` requirement.
"""

from __future__ import annotations

import argparse
import hashlib
import tempfile
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

try:
    from scripts import build_us_tariff_section232_equivalence_receipt as full
    from scripts import build_us_tariff_preview_disposition_receipt as preview_builder
    from scripts import us_tariff_schedule_campaign as campaign
except ModuleNotFoundError:  # Direct execution from scripts/.
    import build_us_tariff_section232_equivalence_receipt as full
    import build_us_tariff_preview_disposition_receipt as preview_builder
    import us_tariff_schedule_campaign as campaign


REPO_ROOT = Path(__file__).resolve().parent.parent
PRODUCER_SOURCE = Path(__file__).resolve()
CAMPAIGN_SOURCE = REPO_ROOT / "scripts/us_tariff_schedule_campaign.py"
FULL_CLOSURE_GUARD_SOURCE = (
    REPO_ROOT / "scripts/build_us_tariff_section232_equivalence_receipt.py"
)
DEFAULT_OUTPUT = (
    REPO_ROOT / "reference/us-tariff-schedule/preview-selector-transition-receipt.json"
)
SCHEMA = "axiom_oracles.us_tariff_schedule.preview_selector_transitions.v1"

UNCONDITIONAL_PRECEDENCE_FLAGS = (
    "entry_is_section_232_covered",
    "entry_is_s232_copper_primary_member",
    "entry_is_s232_copper_additional_member",
    "entry_is_s232_note37_softwood_member",
    "entry_is_s232_note37_upholstered_wood_furniture_member",
    "entry_is_s232_note38_mhd_vehicle_member",
    "entry_is_s232_note38_bus_member",
)
CANDIDATE_PRECEDENCE_FLAGS = (
    "entry_is_s232_note33_vehicle_candidate",
    "entry_is_s232_note33_auto_part_candidate",
    "entry_is_s232_note37_cabinet_vanity_candidate",
    "entry_is_s232_note38_mhd_part_candidate",
    "entry_is_s232_note39_semiconductor_candidate",
    "entry_is_s232_note40_pharmaceutical_candidate",
)
NOTE16_MEMBERSHIP_FLAGS = (
    "entry_is_s232_note16_c_ii_derivative_aluminum_member",
    "entry_is_s232_note16_c_vi_derivative_aluminum_candidate",
    "entry_is_s232_note16_c_ix_derivative_aluminum_candidate",
)
NOTE16_METAL_CHAPTER_FLAG = "entry_is_s232_note16_metal_chapter"
NOTE16_WEIGHT_INPUT = (
    "entry_has_at_least_fifteen_percent_aggregate_applicable_listed_metal_weight"
)
DECLARED_PRECEDENCE_FLAGS = (
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

ANNEX_RESIDUAL_PATTERNS = frozenset(
    {
        (),
        ("entry_is_s232_note33_auto_part_candidate",),
        ("entry_is_s232_note38_mhd_part_candidate",),
        (
            "entry_is_s232_note33_auto_part_candidate",
            "entry_is_s232_note38_mhd_part_candidate",
        ),
    }
)
HEADING_RESIDUAL_PATTERNS = frozenset(
    {
        ("entry_is_s232_note33_vehicle_candidate",),
        ("entry_is_s232_note33_auto_part_candidate",),
        ("entry_is_s232_note37_cabinet_vanity_candidate",),
        ("entry_is_s232_note38_mhd_part_candidate",),
        (
            "entry_is_s232_note33_auto_part_candidate",
            "entry_is_s232_note38_mhd_part_candidate",
        ),
    }
)
EXPECTED_PARENT_PATTERNS = {
    "section232-annex-brazil": ANNEX_RESIDUAL_PATTERNS,
    "section232-annex-forced-labor": ANNEX_RESIDUAL_PATTERNS,
    "section232-heading-brazil": HEADING_RESIDUAL_PATTERNS,
    "section232-heading-forced-labor": HEADING_RESIDUAL_PATTERNS,
}
PATTERN_SLUGS = {
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
YALE_PARSER_RECEIPT = {
    "path": "scripts/parse_annex_products.R",
    "bytes": 11_189,
    "sha256": "8d560897f85d60ee2c2e1d3025a6b9bdd7406e67621aed428abe957ad1cf4bb6",
}
YALE_PREVIEW_SOURCE_FILES = (
    "resources/s232_annex_products.csv",
    "resources/s232_derivative_products.csv",
    "src/model/data_loaders.R",
)
IN_SCOPE_DIRECT_ANNEX_TIERS = frozenset(
    tier
    for tier in preview_builder.IN_SCOPE_ANNEX_TIERS
    if tier != "annex_1b_inferred_derivative"
)
EXPECTED_LEGACY_DERIVATIVE_FALLBACK_HTS10 = frozenset(
    {"9401999030", "9401999040", "9401999085"}
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _logical_file_receipt(path: Path, *, logical_path: str) -> dict[str, Any]:
    require(path.is_file(), f"missing pinned Yale source: {path}")
    return {
        "path": logical_path,
        "bytes": path.stat().st_size,
        "sha256": full.sha256(path),
    }


def _verified_yale_annex_classifier(
    *,
    yale_root: Path,
    preview: dict[str, Any],
    expected_parser_receipt: dict[str, Any],
) -> tuple[Callable[[str, str], tuple[str, str]], dict[str, Any]]:
    """Replay the pinned Yale direct-annex-first classification semantics."""

    yale_sources = preview.get("yale_sources")
    require(
        isinstance(yale_sources, dict)
        and isinstance(yale_sources.get("files"), dict)
        and isinstance(yale_sources.get("commit"), str)
        and isinstance(yale_sources.get("tree"), str),
        "preview Yale source binding is malformed",
    )
    commit = preview_builder.git_value(yale_root, "rev-parse", "HEAD")
    tree = preview_builder.git_value(yale_root, "rev-parse", "HEAD^{tree}")
    require(commit == yale_sources["commit"], f"Yale commit drift: {commit}")
    require(tree == yale_sources["tree"], f"Yale tree drift: {tree}")

    verified_files: dict[str, dict[str, Any]] = {}
    for logical_path in YALE_PREVIEW_SOURCE_FILES:
        expected = yale_sources["files"].get(logical_path)
        require(
            isinstance(expected, dict)
            and isinstance(expected.get("bytes"), int)
            and isinstance(expected.get("sha256"), str),
            f"preview Yale source receipt is missing or malformed: {logical_path}",
        )
        actual = _logical_file_receipt(
            yale_root / logical_path, logical_path=logical_path
        )
        require(
            actual == {"path": logical_path, **expected},
            f"Yale source receipt drift: {logical_path}",
        )
        verified_files[logical_path] = actual

    require(
        isinstance(expected_parser_receipt, dict)
        and set(expected_parser_receipt) == {"path", "bytes", "sha256"}
        and expected_parser_receipt.get("path") == "scripts/parse_annex_products.R",
        "expected Yale annex-parser receipt is malformed",
    )
    parser = _logical_file_receipt(
        yale_root / expected_parser_receipt["path"],
        logical_path=expected_parser_receipt["path"],
    )
    require(parser == expected_parser_receipt, "Yale annex parser source drift")
    verified_files[parser["path"]] = parser

    annex_rows = preview_builder.read_csv(
        yale_root / "resources/s232_annex_products.csv"
    )
    derivative_rows = preview_builder.read_csv(
        yale_root / "resources/s232_derivative_products.csv"
    )
    require(bool(annex_rows), "pinned Yale annex source is empty")
    require(bool(derivative_rows), "pinned Yale derivative source is empty")

    @lru_cache(maxsize=None)
    def active_maps(
        interval_start: str,
    ) -> tuple[tuple[tuple[str, str, str], ...], tuple[str, ...]]:
        latest: dict[str, tuple[str, set[tuple[str, str]]]] = {}
        for row in annex_rows:
            effective = row.get("effective_date") or "1900-01-01"
            if effective > interval_start:
                continue
            prefix = preview_builder.normalize_code(row.get("hts_prefix", ""))
            tier = "annex_" + row.get("annex", "")
            source = row.get("source", "")
            require(
                prefix.isdigit() and len(prefix) in {4, 6, 8, 10},
                f"malformed Yale annex prefix: {prefix!r}",
            )
            prior = latest.get(prefix)
            fingerprint = (tier, source)
            if prior is None or effective > prior[0]:
                latest[prefix] = (effective, {fingerprint})
            elif effective == prior[0]:
                prior[1].add(fingerprint)
        direct: list[tuple[str, str, str]] = []
        for prefix, (_effective, fingerprints) in latest.items():
            require(
                len(fingerprints) == 1,
                f"ambiguous latest-effective Yale annex prefix: {prefix}",
            )
            tier, source = next(iter(fingerprints))
            direct.append((prefix, tier, source))
        direct.sort(key=lambda item: (-len(item[0]), item[0]))
        derivative = tuple(
            sorted(
                {
                    preview_builder.normalize_code(row.get("hts_prefix", ""))
                    for row in derivative_rows
                    if (row.get("effective_date") or "1900-01-01")
                    <= interval_start
                },
                key=lambda value: (-len(value), value),
            )
        )
        require(
            all(prefix.isdigit() and 1 <= len(prefix) <= 10 for prefix in derivative),
            "malformed Yale derivative prefix",
        )
        return tuple(direct), derivative

    @lru_cache(maxsize=None)
    def classify(hts10: str, interval_start: str) -> tuple[str, str]:
        require(
            isinstance(hts10, str)
            and len(hts10) == 10
            and hts10.isdigit()
            and isinstance(interval_start, str)
            and bool(interval_start),
            "Yale annex source proof identity is malformed",
        )
        direct, derivative = active_maps(interval_start)
        direct_hits = [row for row in direct if hts10.startswith(row[0])]
        if direct_hits:
            winning_prefix, tier, source = direct_hits[0]
            require(
                tier in IN_SCOPE_DIRECT_ANNEX_TIERS
                and source == "proclamation"
                and len(winning_prefix) in {4, 6},
                "Yale direct annex winner does not prove the reference-defect class: "
                f"{hts10}: {(winning_prefix, tier, source)}",
            )
            return "annex_proclamation_prefix", winning_prefix
        derivative_hits = [
            prefix for prefix in derivative if hts10.startswith(prefix)
        ]
        require(
            bool(derivative_hits),
            f"Yale annex defect row has no direct or derivative source: {hts10}",
        )
        return "legacy_derivative_fallback", derivative_hits[0]

    return classify, {
        "commit": commit,
        "tree": tree,
        "files": dict(sorted(verified_files.items())),
        "classification_precedence": [
            "latest-effective direct annex row per normalized prefix",
            "longest-prefix direct match",
            "longest-prefix legacy derivative fallback only when direct is absent",
        ],
    }


def _typed_flags(value: Any, *, key: tuple[str, str]) -> dict[str, bool]:
    required = set(
        UNCONDITIONAL_PRECEDENCE_FLAGS
        + CANDIDATE_PRECEDENCE_FLAGS
        + DECLARED_PRECEDENCE_FLAGS
        + NOTE16_MEMBERSHIP_FLAGS
        + (NOTE16_METAL_CHAPTER_FLAG, NOTE16_WEIGHT_INPUT)
    )
    require(
        isinstance(value, dict)
        and required <= set(value)
        and all(
            isinstance(name, str) and isinstance(flag, bool)
            for name, flag in value.items()
        ),
        f"fresh Section-232 flag vector is malformed: {key}",
    )
    return value


def _precedence_exempt(flags: dict[str, bool]) -> bool:
    return (
        any(flags[name] for name in UNCONDITIONAL_PRECEDENCE_FLAGS)
        or flags["entry_is_s232_note16_c_ii_derivative_aluminum_member"]
        or (
            flags["entry_is_s232_note16_c_vi_derivative_aluminum_candidate"]
            and (
                flags[NOTE16_METAL_CHAPTER_FLAG]
                or flags[NOTE16_WEIGHT_INPUT]
            )
        )
        or (
            flags["entry_is_s232_note16_c_ix_derivative_aluminum_candidate"]
            and (
                flags[NOTE16_METAL_CHAPTER_FLAG]
                or flags[NOTE16_WEIGHT_INPUT]
            )
        )
        or (
            flags["entry_is_s232_note33_vehicle_candidate"]
            and flags[
                "entry_qualifies_for_note33_vehicle_heading_listed_in_notes_50_52"
            ]
        )
        or (
            flags["entry_is_s232_note33_auto_part_candidate"]
            and flags["entry_is_note33_g_automobile_part"]
        )
        or flags[
            "entry_qualifies_for_note33_certified_auto_part_heading_listed_in_notes_50_52"
        ]
        or flags["entry_is_note33_auto_part_subject_to_import_adjustment_offset"]
        or (
            flags["entry_is_s232_note37_cabinet_vanity_candidate"]
            and flags["entry_is_note37_f_completed_kitchen_cabinet_vanity_or_part"]
        )
        or (
            flags["entry_is_s232_note38_mhd_part_candidate"]
            and flags["entry_is_note38_i_medium_or_heavy_duty_vehicle_part"]
        )
        or flags[
            "entry_qualifies_for_note38_certified_mhd_part_heading_listed_in_notes_50_52"
        ]
        or flags["entry_is_note38_mhd_part_subject_to_import_adjustment_offset"]
        or (
            flags["entry_is_s232_note39_semiconductor_candidate"]
            and flags["entry_qualifies_for_note39_heading_9903_79_01"]
        )
        or (
            flags["entry_is_s232_note40_pharmaceutical_candidate"]
            and flags["entry_is_note40_patented_pharmaceutical_article"]
        )
    )


def _candidate_pattern(flags: dict[str, bool]) -> tuple[str, ...]:
    return tuple(name for name in CANDIDATE_PRECEDENCE_FLAGS if flags[name])


def _pattern_name(pattern: tuple[str, ...]) -> str:
    return "+".join(pattern) if pattern else "none"


def _child_flag_vector(pattern: tuple[str, ...]) -> dict[str, bool]:
    require(
        pattern in ANNEX_RESIDUAL_PATTERNS | HEADING_RESIDUAL_PATTERNS,
        f"unsupported Section-232 child pattern: {_pattern_name(pattern)}",
    )
    flags = {name: False for name in UNCONDITIONAL_PRECEDENCE_FLAGS}
    flags.update({name: name in pattern for name in CANDIDATE_PRECEDENCE_FLAGS})
    flags.update({name: False for name in DECLARED_PRECEDENCE_FLAGS})
    flags.update({name: False for name in NOTE16_MEMBERSHIP_FLAGS})
    flags[NOTE16_WEIGHT_INPUT] = True
    require(
        NOTE16_METAL_CHAPTER_FLAG not in flags,
        "metal-chapter fact must not narrow residual child matches",
    )
    return flags


def _child_ruling(
    parent_id: str, pattern: tuple[str, ...]
) -> dict[str, str]:
    require(
        parent_id.startswith("section232-")
        and parent_id.endswith(("-brazil", "-forced-labor")),
        f"unsupported Section-232 transition parent: {parent_id}",
    )
    family = "annex" if "-annex-" in parent_id else "heading"
    country = "forced-labor" if parent_id.endswith("-forced-labor") else "brazil"
    slug = PATTERN_SLUGS[pattern]
    if family == "annex" and not pattern:
        return {
            "id": f"section232-annex-{slug}-{country}",
            "logical_class": "section232-annex-yale-reference-defect",
            "disposition": "upstream_engine_gap",
            "attribution": "reference-defect",
        }
    return {
        "id": f"section232-{family}-{slug}-{country}",
        "logical_class": (
            f"section232-{family}-{slug}-conditional-reference-behavior"
        ),
        "disposition": "explained_residual",
        "attribution": "reference-behavior",
    }


def _scan_fresh_transitions(
    *,
    path: Path,
    comparison: dict[str, Any],
    historical_units: dict[tuple[str, str], dict[str, Any]],
    source_eval_units: dict[tuple[str, str], dict[str, Any]],
    parent_ids: set[str],
    yale_annex_classifier: Callable[[str, str], tuple[str, str]],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    found: set[tuple[str, str]] = set()
    per_slot: dict[str, Counter[str]] = defaultdict(Counter)
    parent_state: dict[str, dict[str, Any]] = {
        parent_id: {
            "matches": 0,
            "residual": Counter(),
            "patterns": Counter(),
            "child_populations": defaultdict(Counter),
            "defect_source_identities": [],
            "defect_source_arms": Counter(),
            "defect_source_populations": defaultdict(Counter),
            "defect_source_hts10": defaultdict(set),
        }
        for parent_id in parent_ids
    }
    rows_scanned = 0
    engine_error_rows = 0
    tolerance = full._finite_number(
        comparison.get("tolerance"), label="comparison tolerance"
    )
    for row in full._iter_jsonl_gzip(path):
        rows_scanned += 1
        case_id = row.get("case_id")
        slot = row.get("slot")
        matched = row.get("match")
        require(
            isinstance(case_id, str)
            and isinstance(slot, str)
            and isinstance(matched, bool),
            f"fresh comparison row lacks typed identity/match state at row {rows_scanned}",
        )
        per_slot[slot]["match" if matched else "mismatch"] += 1
        if slot == "engine_error":
            engine_error_rows += 1
            continue
        key = (case_id, slot)
        historical = historical_units.get(key)
        if historical is None:
            continue
        require(key not in found, f"duplicate fresh Section-232 identity: {key}")
        found.add(key)
        identity = full._identity(row, label="fresh")
        require(
            identity == historical["identity"],
            f"fresh Section-232 legal identity drift: {key}",
        )
        source_eval = source_eval_units.get(key)
        require(
            isinstance(source_eval, dict),
            f"fresh Section-232 cell lacks source evaluation: {key}",
        )
        source_comparison = source_eval["comparison"]
        require(
            row.get("context") == source_comparison["context"]
            and matched is source_comparison["match"],
            f"fresh comparison row disagrees with source evaluation: {key}",
        )
        actual = full._finite_number(row.get("actual"), label="fresh actual")
        delta = full._finite_number(row.get("delta"), label="fresh delta")
        expected = identity["expected"]
        require(
            abs((actual - expected) - delta) <= tolerance
            and abs(actual - source_comparison["actual"]) <= tolerance
            and abs(expected - source_comparison["expected"]) <= tolerance
            and abs(delta - source_comparison["delta"]) <= tolerance,
            f"fresh comparison arithmetic disagrees with source evaluation: {key}",
        )
        flags = _typed_flags(row["context"].get("flags"), key=key)
        require(
            flags[NOTE16_WEIGHT_INPUT],
            f"fresh Section-232 row lost the receipted Yale metal-weight assumption: {key}",
        )
        parent_id = historical["selector"]
        state = parent_state[parent_id]
        if matched:
            require(
                abs(delta) <= tolerance
                and abs(actual - expected) <= tolerance
                and _precedence_exempt(flags),
                f"fresh Section-232 match lacks precedence evidence: {key}",
            )
            if "-exposed-" in parent_id:
                require(
                    flags["entry_is_section_232_covered"],
                    f"fresh exposed Section-232 match lost covered fact: {key}",
                )
            state["matches"] += 1
            continue

        require(
            delta > tolerance
            and abs(expected) <= tolerance
            and not _precedence_exempt(flags),
            f"fresh Section-232 residual has invalid legal state: {key}",
        )
        require(
            "-exposed-" not in parent_id,
            f"fresh exposed Section-232 selector still mismatches: {key}",
        )
        pattern = _candidate_pattern(flags)
        allowed_patterns = (
            ANNEX_RESIDUAL_PATTERNS
            if "-annex-" in parent_id
            else HEADING_RESIDUAL_PATTERNS
        )
        require(
            pattern in allowed_patterns
            and all(not flags[name] for name in DECLARED_PRECEDENCE_FLAGS)
            and all(not flags[name] for name in NOTE16_MEMBERSHIP_FLAGS),
            f"fresh Section-232 residual is not an exact supported class: {key}",
        )
        child_flags = _child_flag_vector(pattern)
        require(
            all(flags[name] is value for name, value in child_flags.items()),
            f"fresh Section-232 residual flag vector is not exact: {key}",
        )
        signature = campaign.mismatch_signature(row)
        state["patterns"][_pattern_name(pattern)] += 1
        state["residual"][signature] += 1
        state["child_populations"][pattern][signature] += 1
        if "-annex-" in parent_id and not pattern:
            context = row["context"]
            interval_start = context["interval"][0]
            arm, winning_prefix = yale_annex_classifier(
                context["hts10"], interval_start
            )
            state["defect_source_arms"][arm] += 1
            state["defect_source_populations"][arm][signature] += 1
            state["defect_source_hts10"][arm].add(context["hts10"])
            state["defect_source_identities"].append(
                [
                    case_id,
                    slot,
                    context["hts10"],
                    interval_start,
                    arm,
                    winning_prefix,
                ]
            )

    require(
        engine_error_rows == 0, "fresh comparison artifact contains engine-error rows"
    )
    missing = set(historical_units) - found
    require(
        not missing,
        f"fresh comparison is missing {len(missing)} historical Section-232 identities",
    )
    observed_per_slot = {
        slot: dict(counter) for slot, counter in sorted(per_slot.items())
    }
    require(
        observed_per_slot == full._normalized_per_slot(comparison.get("per_slot")),
        "comparison artifact per-slot census disagrees with receipt",
    )
    return parent_state, {
        "comparison_rows_scanned": rows_scanned,
        "engine_error_rows": engine_error_rows,
        "joined_historical_units": len(found),
    }


def _transition_items(
    *,
    selectors: dict[str, dict[str, Any]],
    parent_state: dict[str, dict[str, Any]],
    expected_parent_patterns: dict[str, frozenset[tuple[str, ...]]],
    expected_fallback_hts10: frozenset[str] | None,
    yale_source_receipt: dict[str, Any],
) -> list[dict[str, Any]]:
    require(
        set(parent_state) == set(selectors),
        "Section-232 transition parent set drift",
    )
    require(
        set(expected_parent_patterns) <= set(selectors),
        "Section-232 expected-pattern parent set drift",
    )
    transitions: list[dict[str, Any]] = []
    all_defect_fallback_hts10: set[str] = set()
    total_defect_units = 0
    for parent_id in sorted(selectors):
        parent = selectors[parent_id]
        state = parent_state[parent_id]
        residual: Counter[str] = state["residual"]
        residual_units = sum(residual.values())
        residual_signatures = len(residual)
        residual_sha256 = campaign.signature_population_sha256(residual.items())
        require(
            state["matches"] + residual_units == parent["expected_units"],
            f"fresh Section-232 transition does not conserve: {parent_id}",
        )
        status = "superseded" if residual_units else "retired"
        patterns = dict(sorted(state["patterns"].items()))
        child_populations: dict[tuple[str, ...], Counter[str]] = state[
            "child_populations"
        ]
        observed_patterns = frozenset(child_populations)
        if status == "superseded":
            require(
                observed_patterns == expected_parent_patterns.get(parent_id),
                f"fresh Section-232 transition pattern drift: {parent_id}: "
                f"{sorted(map(_pattern_name, observed_patterns))}",
            )
        else:
            require(
                not child_populations and not patterns,
                f"retired Section-232 parent retains residual patterns: {parent_id}",
            )
        child_union: Counter[str] = Counter()
        for population in child_populations.values():
            require(
                not (set(child_union) & set(population)),
                f"Section-232 child signature populations overlap: {parent_id}",
            )
            child_union.update(population)
        require(
            child_union == residual,
            f"Section-232 children do not exactly partition residual: {parent_id}",
        )
        children: list[dict[str, Any]] = []
        child_evidence: dict[str, dict[str, Any]] = {}
        for pattern in sorted(child_populations, key=_pattern_name):
            population = child_populations[pattern]
            ruling = _child_ruling(parent_id, pattern)
            child_units = sum(population.values())
            child_digest = campaign.signature_population_sha256(
                population.items()
            )
            child_match = {
                **parent["match"],
                "line_class": {"flags": _child_flag_vector(pattern)},
            }
            children.append(
                {
                    **ruling,
                    "parent_id": parent_id,
                    "expected_units": child_units,
                    "expected_signature_count": len(population),
                    "expected_signature_population_sha256": child_digest,
                    "match": child_match,
                }
            )
            child_evidence[ruling["id"]] = {
                "candidate_pattern": _pattern_name(pattern),
                "units": child_units,
                "signature_count": len(population),
                "signature_population_sha256": child_digest,
            }

        defect_source_proof: dict[str, Any] | None = None
        if "-annex-" in parent_id and () in child_populations:
            defect_population = child_populations[()]
            source_identities = sorted(state["defect_source_identities"])
            source_arms: Counter[str] = state["defect_source_arms"]
            source_populations: dict[str, Counter[str]] = state[
                "defect_source_populations"
            ]
            require(
                len(source_identities) == sum(defect_population.values())
                == sum(source_arms.values()),
                f"Yale annex defect source proof does not conserve: {parent_id}",
            )
            source_union: Counter[str] = Counter()
            per_arm: dict[str, dict[str, Any]] = {}
            for arm, population in sorted(source_populations.items()):
                require(
                    arm in {
                        "annex_proclamation_prefix",
                        "legacy_derivative_fallback",
                    }
                    and not (set(source_union) & set(population)),
                    f"Yale annex defect source arms overlap or drift: {parent_id}",
                )
                require(
                    sum(population.values()) == source_arms[arm],
                    f"Yale annex defect source-arm census drift: {parent_id}: {arm}",
                )
                source_union.update(population)
                per_arm[arm] = {
                    "units": sum(population.values()),
                    "signature_count": len(population),
                    "signature_population_sha256": (
                        campaign.signature_population_sha256(population.items())
                    ),
                    "hts10": sorted(state["defect_source_hts10"][arm]),
                }
            require(
                source_union == defect_population,
                f"Yale annex defect source arms do not partition child: {parent_id}",
            )
            total_defect_units += sum(defect_population.values())
            all_defect_fallback_hts10.update(
                state["defect_source_hts10"]["legacy_derivative_fallback"]
            )
            defect_source_proof = {
                "classification": "pinned-yale-direct-annex-or-derivative-fallback",
                "units": len(source_identities),
                "identity_sha256": full.canonical_sha256(source_identities),
                "identity_fields": [
                    "case_id",
                    "slot",
                    "hts10",
                    "interval_start",
                    "arm",
                    "winning_prefix",
                ],
                "per_arm": per_arm,
                "pinned_yale_source": yale_source_receipt,
            }
        transitions.append(
            {
                "parent_id": parent_id,
                "parent_contract": parent,
                "status": status,
                "historical_units": parent["expected_units"],
                "fresh_matching_units": state["matches"],
                "fresh_residual_population": {
                    "units": residual_units,
                    "signature_count": residual_signatures,
                    "signature_population_sha256": residual_sha256,
                },
                "children": children,
                "evidence": {
                    "current_precedence_true_units": state["matches"],
                    "current_precedence_false_units": residual_units,
                    "candidate_pattern_units": patterns,
                    "child_populations": child_evidence,
                    **(
                        {"yale_annex_defect_source_proof": defect_source_proof}
                        if defect_source_proof is not None
                        else {}
                    ),
                    "classification": (
                        "fully-fixed-exposed"
                        if status == "retired" and "-exposed-" in parent_id
                        else "fully-fixed"
                        if status == "retired"
                        else "disjoint-conditional-reference-behavior"
                        if "-heading-" in parent_id
                        else "disjoint-reference-defect-and-conditional-reference-behavior"
                    ),
                },
            }
        )
    if total_defect_units and expected_fallback_hts10 is not None:
        require(
            all_defect_fallback_hts10 == expected_fallback_hts10,
            "Yale legacy derivative fallback HTS10 population drift: "
            f"{sorted(all_defect_fallback_hts10)}",
        )
    return transitions


def build_receipt(
    *,
    repo_root: Path = REPO_ROOT,
    producer_source: Path = PRODUCER_SOURCE,
    campaign_source: Path = CAMPAIGN_SOURCE,
    full_closure_guard_source: Path = FULL_CLOSURE_GUARD_SOURCE,
    preview_receipt_path: Path = full.PREVIEW_RECEIPT,
    historical_artifact_path: Path = full.HISTORICAL_ARTIFACT,
    eval_manifest_path: Path = full.EVAL_MANIFEST,
    comparison_receipt_path: Path = full.COMPARISON_RECEIPT,
    expected_preview_snapshot_sha256: str = full.EXPECTED_PREVIEW_SECTION232_SNAPSHOT_SHA256,
    expected_selector_units: dict[str, int] = full.SECTION232_SELECTOR_UNITS,
    expected_parent_patterns: dict[
        str, frozenset[tuple[str, ...]]
    ] = EXPECTED_PARENT_PATTERNS,
    expected_fallback_hts10: frozenset[str] | None = (
        EXPECTED_LEGACY_DERIVATIVE_FALLBACK_HTS10
    ),
    yale_root: Path = preview_builder.DEFAULT_YALE_ROOT,
    expected_yale_parser_receipt: dict[str, Any] = YALE_PARSER_RECEIPT,
    expected_reference_assumptions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if expected_reference_assumptions is None:
        expected_reference_assumptions = {
            "yale_note16_metal_weight": (
                campaign._yale_note16_weight_assumption_identity()
            )
        }
    require(
        isinstance(expected_reference_assumptions, dict)
        and set(expected_reference_assumptions)
        == {"yale_note16_metal_weight"}
        and isinstance(
            expected_reference_assumptions["yale_note16_metal_weight"], dict
        )
        and bool(expected_reference_assumptions["yale_note16_metal_weight"]),
        "expected reference-assumption identity is malformed",
    )
    producer = {
        "script": full.file_receipt(producer_source, relative_to=repo_root),
        "campaign_classifier": full.file_receipt(
            campaign_source, relative_to=repo_root
        ),
        "full_closure_guard": full.file_receipt(
            full_closure_guard_source, relative_to=repo_root
        ),
    }
    preview_file = full.file_receipt(preview_receipt_path, relative_to=repo_root)
    preview, selectors, line_sets, historical_receipt, selected_receipt = (
        full._validate_preview(
            preview_receipt_path,
            expected_snapshot_sha256=expected_preview_snapshot_sha256,
            expected_selector_units=expected_selector_units,
        )
    )
    require(
        preview.get("producer", {}).get("campaign_classifier")
        == producer["campaign_classifier"],
        "preview receipt is not bound to the current campaign classifier",
    )
    yale_annex_classifier, yale_source_receipt = (
        _verified_yale_annex_classifier(
            yale_root=yale_root,
            preview=preview,
            expected_parser_receipt=expected_yale_parser_receipt,
        )
    )
    historical_units, _identities, _projections, historical_rows_scanned = (
        full._load_historical_units(
            path=historical_artifact_path,
            expected_receipt=historical_receipt,
            selectors=selectors,
            line_sets=line_sets,
            expected_selector_units=expected_selector_units,
        )
    )

    with full._manifest_lock(eval_manifest_path):
        manifest_file = full.file_receipt(eval_manifest_path, relative_to=repo_root)
        comparison_file = full.file_receipt(
            comparison_receipt_path, relative_to=repo_root
        )
        (
            manifest,
            comparison,
            artifact_path,
            binding_audit,
            source_eval_units,
            shard_receipts,
        ) = full._validate_eval_and_comparison_bindings(
            repo_root=repo_root,
            eval_manifest_path=eval_manifest_path,
            comparison_receipt_path=comparison_receipt_path,
            preview=preview,
            selected_receipt=selected_receipt,
            historical_units=historical_units,
        )
        run_campaign = (
            manifest["run_identity"].get("campaign_evaluator", {}).get("campaign")
        )
        require(
            run_campaign == producer["campaign_classifier"],
            "evaluation run is not bound to the current campaign classifier",
        )
        rulespec = manifest["run_identity"].get("rulespec")
        entry_flag_producers = manifest["run_identity"].get("entry_flag_producers")
        reference_assumptions = manifest["run_identity"].get(
            "reference_assumptions"
        )
        require(
            isinstance(rulespec, dict)
            and bool(rulespec)
            and isinstance(entry_flag_producers, dict)
            and bool(entry_flag_producers)
            and reference_assumptions == expected_reference_assumptions,
            "evaluation run lacks RuleSpec, entry-flag, or reference-assumption provenance",
        )
        parent_state, comparison_audit = _scan_fresh_transitions(
            path=artifact_path,
            comparison=comparison,
            historical_units=historical_units,
            source_eval_units=source_eval_units,
            parent_ids=set(selectors),
            yale_annex_classifier=yale_annex_classifier,
        )
        require(
            full.file_receipt(eval_manifest_path, relative_to=repo_root)
            == manifest_file
            and full.file_receipt(comparison_receipt_path, relative_to=repo_root)
            == comparison_file
            and full.file_receipt(artifact_path) == comparison["comparison_artifact"]
            and all(
                full.file_receipt(Path(receipt["path"])) == receipt
                for receipt in shard_receipts
            ),
            "evaluation/comparison evidence changed during transition proof",
        )

    transitions = _transition_items(
        selectors=selectors,
        parent_state=parent_state,
        expected_parent_patterns=expected_parent_patterns,
        expected_fallback_hts10=expected_fallback_hts10,
        yale_source_receipt=yale_source_receipt,
    )
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "verdict": "PASS",
        "producer": producer,
        "inputs": {
            "immutable_preview_receipt": preview_file,
            "historical_target_mismatch_artifact": historical_receipt,
            "evaluation_manifest": manifest_file,
            "comparison_receipt": comparison_file,
            "comparison_artifact": comparison["comparison_artifact"],
        },
        "bindings": {
            "preview_receipt_payload_sha256": preview["receipt_payload_sha256"],
            "generation_id": comparison["generation_id"],
            "run_identity_sha256": comparison["run_identity_sha256"],
            "evaluation_manifest_sha256": comparison["evaluation_manifest_sha256"],
            "rulespec": rulespec,
            "entry_flag_producers": entry_flag_producers,
            "reference_assumptions": reference_assumptions,
        },
        "zero_error_proof": {
            "evaluation_shard_engine_errors": binding_audit[
                "evaluation_shard_engine_errors"
            ],
            "observed_evaluation_record_errors": binding_audit[
                "observed_evaluation_record_errors"
            ],
            "comparison_receipt_engine_errors": binding_audit[
                "comparison_receipt_engine_errors"
            ],
            "comparison_artifact_engine_error_rows": comparison_audit[
                "engine_error_rows"
            ],
        },
        "transitions": transitions,
    }
    require(
        historical_rows_scanned >= len(historical_units)
        and comparison_audit["joined_historical_units"] == len(historical_units),
        "Section-232 transition scan census is malformed",
    )
    payload["receipt_payload_sha256"] = full.canonical_sha256(payload)
    require(
        full.file_receipt(producer_source, relative_to=repo_root) == producer["script"]
        and full.file_receipt(campaign_source, relative_to=repo_root)
        == producer["campaign_classifier"]
        and full.file_receipt(full_closure_guard_source, relative_to=repo_root)
        == producer["full_closure_guard"]
        and full.file_receipt(preview_receipt_path, relative_to=repo_root)
        == preview_file
        and historical_artifact_path.stat().st_size == historical_receipt["bytes"]
        and full.sha256(historical_artifact_path) == historical_receipt["sha256"],
        "transition producer or preview evidence changed during receipt build",
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview-receipt", type=Path, default=full.PREVIEW_RECEIPT)
    parser.add_argument(
        "--historical-artifact", type=Path, default=full.HISTORICAL_ARTIFACT
    )
    parser.add_argument("--eval-manifest", type=Path, default=full.EVAL_MANIFEST)
    parser.add_argument(
        "--comparison-receipt", type=Path, default=full.COMPARISON_RECEIPT
    )
    parser.add_argument(
        "--yale-root", type=Path, default=preview_builder.DEFAULT_YALE_ROOT
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    receipt = build_receipt(
        preview_receipt_path=args.preview_receipt.resolve(),
        historical_artifact_path=args.historical_artifact.resolve(),
        eval_manifest_path=args.eval_manifest.resolve(),
        comparison_receipt_path=args.comparison_receipt.resolve(),
        yale_root=args.yale_root.resolve(),
    )
    output = full.render(receipt)
    if args.check:
        require(args.output.is_file(), f"generated receipt missing: {args.output}")
        require(
            args.output.read_text() == output,
            f"generated receipt drift: {args.output}",
        )
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", dir=args.output.parent, delete=False
        ) as target:
            target.write(output)
            temporary = Path(target.name)
        temporary.replace(args.output)
    print(
        full.render(
            {
                "verdict": receipt["verdict"],
                "output": str(args.output.resolve()),
                "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
                "transitions": len(receipt["transitions"]),
                "children": sum(
                    len(item["children"]) for item in receipt["transitions"]
                ),
            }
        ),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
