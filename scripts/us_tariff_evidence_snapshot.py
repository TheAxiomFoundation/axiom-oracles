#!/usr/bin/env python3
"""Frozen source contract for the September 2026 US-tariff evidence package.

This module intentionally preserves the RuleSpec, corpus, and engine revisions
used to produce the bounded historical evidence snapshot.  It is independent
of the repository's live certification and closure code: importing it cannot
change or confer current conformance, closure, certification, or release
status.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_KIND = "frozen_historical_evidence"
CURRENT_CERTIFICATION_AUTHORITY = False
EVIDENCE_DIRECTORY = ROOT / "reference/us-tariff-schedule/boundary-evidence"
FRONTIER_INVENTORY = EVIDENCE_DIRECTORY / "frontier-inventory.json"

CORPUS_ROOT_ENV = "AXIOM_TARIFF_EVIDENCE_CORPUS_ROOT"
RULESPEC_ROOT_ENV = "AXIOM_TARIFF_EVIDENCE_RULESPEC_ROOT"
ENGINE_SOURCE_ROOT_ENV = "AXIOM_TARIFF_EVIDENCE_ENGINE_ROOT"
ENGINE_BINARY_ENV = "AXIOM_TARIFF_EVIDENCE_ENGINE_BINARY"
CORPUS_REF = "cc18c703741425a3ebf994a2975cae158bd305d1"
RULESPEC_REF = "4f591c4267063094cc6da9d590872ea982940b81"
ENGINE_SOURCE_REPOSITORY = "TheAxiomFoundation/axiom-rules-engine"
ENGINE_SOURCE_REF = "ffd8213271947b0189a9dd61a055c1e0e78908a0"
REPOSITORY_BASE_REF = "c7cd2346ef540801d2c89780420be77dc0654ff9"
NOTES = "data/corpus/provisions/us/statute/2026-08-04-usitc-hts-2026-rev15-notes.jsonl"
NOTES_SHA256 = "0f3ed7ef2efb64383825db65e615959200770e8511c8d4834b16e02892cb9ec8"
INPUT_INVENTORY_ENGINE_SHA256 = (
    "674ca6e70afdccb59c3d6847933bc24b4590105e49db54790f2dcd0bdbbe32d7"
)
WITNESS_MODULE = "us/policies/cbp/us-tariff-duty/composition.yaml"
SCHEDULE_MODULE_PREFIX = "us/policies/cbp/us-tariff-schedule/generated/"
# Audited from the pinned compiler's all-version dependency closure of the
# witness's us_tariff_duty and all 100 chapters' schedule_statutory_stack.
# Unreachable imported support rules and derived references are not inputs.
# build() independently reproduces this inventory from immutable Git objects.
AUDITED_REACHABLE_INPUTS = (
    "cbp_agrees_chapter_98_entry_is_appropriate",
    "country_of_origin",
    "customs_value",
    "entry_has_at_least_fifteen_percent_aggregate_applicable_listed_metal_weight",
    "entry_is_9802_excepted_entry",
    "entry_is_brazil_301_listed",
    "entry_is_china_301_2024_action",
    "entry_is_china_301_list123",
    "entry_is_china_301_list4a",
    "entry_is_china_301_solar",
    "entry_is_entered_free_of_duty_under_dr_cafta",
    "entry_is_entered_free_of_duty_under_usmca",
    "entry_is_forced_labor_301_listed",
    "entry_is_general_note_29_d_v_textile_or_apparel_good",
    "entry_is_humanitarian_donation_article",
    "entry_is_informational_material_article",
    "entry_is_line_a",
    "entry_is_line_b",
    "entry_is_line_d",
    "entry_is_note33_auto_part_subject_to_import_adjustment_offset",
    "entry_is_note33_g_automobile_part",
    "entry_is_note37_f_completed_kitchen_cabinet_vanity_or_part",
    "entry_is_note38_i_medium_or_heavy_duty_vehicle_part",
    "entry_is_note38_mhd_part_subject_to_import_adjustment_offset",
    "entry_is_note40_patented_pharmaceutical_article",
    "entry_is_personal_use_accompanied_baggage",
    "entry_is_properly_claimed_chapter_98_entry",
    "entry_is_s232_copper_additional_member",
    "entry_is_s232_copper_primary_member",
    "entry_is_s232_note16_c_ii_derivative_aluminum_member",
    "entry_is_s232_note16_c_ix_derivative_aluminum_candidate",
    "entry_is_s232_note16_c_vi_derivative_aluminum_candidate",
    "entry_is_s232_note16_metal_chapter",
    "entry_is_s232_note33_auto_part_candidate",
    "entry_is_s232_note33_vehicle_candidate",
    "entry_is_s232_note37_cabinet_vanity_candidate",
    "entry_is_s232_note37_softwood_member",
    "entry_is_s232_note37_upholstered_wood_furniture_member",
    "entry_is_s232_note38_bus_member",
    "entry_is_s232_note38_mhd_part_candidate",
    "entry_is_s232_note38_mhd_vehicle_member",
    "entry_is_s232_note39_semiconductor_candidate",
    "entry_is_s232_note40_pharmaceutical_candidate",
    "entry_is_section_122_exempt",
    "entry_is_section_201_cspv",
    "entry_is_section_232_aluminum",
    "entry_is_section_232_covered",
    "entry_is_section_232_steel",
    "entry_loaded_and_in_transit_before_july_24_2026",
    "entry_qualifies_for_note33_certified_auto_part_heading_listed_in_notes_50_52",
    "entry_qualifies_for_note33_vehicle_heading_listed_in_notes_50_52",
    "entry_qualifies_for_note38_certified_mhd_part_heading_listed_in_notes_50_52",
    "entry_qualifies_for_note39_heading_9903_79_01",
    "hts_line",
    "hts_number",
    "is_postal_shipment",
    "resolved_non_ad_valorem_column2_rate",
    "shipment_value",
)
AUDITED_REACHABLE_INPUTS_SHA256 = (
    "10c812c01fd7c46b309d9cde66b30b6020acef05a5c9c8f0b97fb3e32ae773b1"
)


# Exact source boundaries for every input reachable from the pinned compiler
# audit above.  ``uncaptured`` means the composed program consumes the fact but
# this ledger does not claim to derive it.  Naming a boundary therefore closes
# the interface inventory, not the underlying policy-family burndown.
CANONICAL_INPUT_SCOPES = (
    (
        "cbp_agrees_chapter_98_entry_is_appropriate",
        "CBP acceptance on the entry record that the declarant's Chapter 98 provision is appropriate under U.S. note 2(u); not inferable from the HTS number alone",
    ),
    (
        "country_of_origin",
        "CBP country-of-origin determination for the entry transaction; not a tariff-table membership proxy",
    ),
    ("customs_value", "19 U.S.C. 1401a appraised customs value for the entry"),
    (
        "entry_has_at_least_fifteen_percent_aggregate_applicable_listed_metal_weight",
        "real-entry determination under HTS U.S. note 16(c) of at least 15 percent aggregate applicable listed-metal weight; the campaign TRUE value is only a Yale-model assumption, not actual-entry proof",
    ),
    (
        "entry_is_9802_excepted_entry",
        "entry classification within the U.S. note 2(u) Chapter 98 exception for heading 9802.00.80 or subheading 9802.00.40, 9802.00.50, or 9802.00.60",
    ),
    (
        "entry_is_brazil_301_listed",
        "entry-preparation membership determination under HTS chapter 99 U.S. note 50 for the Brazil section-301 component",
    ),
    (
        "entry_is_china_301_2024_action",
        "entry-preparation membership determination against the complete HTS U.S. note 31 China 2024-action table, which the pinned program does not itself derive",
    ),
    (
        "entry_is_china_301_list123",
        "entry-preparation membership determination against the original China section-301 lists 1, 2, or 3 and their exclusions",
    ),
    (
        "entry_is_china_301_list4a",
        "entry-preparation membership determination against China section-301 list 4A and its exclusions",
    ),
    (
        "entry_is_china_301_solar",
        "entry-preparation membership determination against the complete HTS U.S. note 31 solar-products China section-301 table, which the pinned program does not itself derive",
    ),
    (
        "entry_is_entered_free_of_duty_under_dr_cafta",
        "declarant claim and transaction qualification for duty-free DR-CAFTA treatment, including applicable subchapter XXII treatment",
    ),
    (
        "entry_is_entered_free_of_duty_under_usmca",
        "declarant claim and transaction qualification for duty-free USMCA treatment used by HTS U.S. note 52(g)-(h)",
    ),
    (
        "entry_is_forced_labor_301_listed",
        "entry-preparation membership determination under HTS chapter 99 U.S. note 52 for the forced-labor section-301 component",
    ),
    (
        "entry_is_general_note_29_d_v_textile_or_apparel_good",
        "General Note 29(d)(v) classification under the WTO textiles-and-clothing annex and stated exclusions",
    ),
    (
        "entry_is_humanitarian_donation_article",
        "transaction determination that the article is a humanitarian donation described by HTS 9903.01.21 and U.S. note 2(t)",
    ),
    (
        "entry_is_informational_material_article",
        "article determination that the goods are informational material described by HTS 9903.01.22",
    ),
    (
        "entry_is_line_a",
        "generated-schedule adapter's exact HTS-number equality to 7202.11.10.00; the witness derives the same predicate from hts_number",
    ),
    (
        "entry_is_line_b",
        "generated-schedule adapter's exact HTS-number equality to 7601.10.30.00; the witness derives the same predicate from hts_number",
    ),
    (
        "entry_is_line_d",
        "generated-schedule adapter's exact HTS-number equality to 2203.00.00.30; the witness derives the same predicate from hts_number",
    ),
    (
        "entry_is_note33_auto_part_subject_to_import_adjustment_offset",
        "entry-level HTS U.S. note 33 automobile-part import-adjustment-offset determination",
    ),
    (
        "entry_is_note33_g_automobile_part",
        "entry-level determination that a U.S. note 33(g) candidate is an automobile part",
    ),
    (
        "entry_is_note37_f_completed_kitchen_cabinet_vanity_or_part",
        "entry-level determination that a U.S. note 37(f) candidate is a completed kitchen cabinet, vanity, or part",
    ),
    (
        "entry_is_note38_i_medium_or_heavy_duty_vehicle_part",
        "entry-level determination that a U.S. note 38(i) candidate is a medium- or heavy-duty-vehicle part",
    ),
    (
        "entry_is_note38_mhd_part_subject_to_import_adjustment_offset",
        "entry-level HTS U.S. note 38 medium/heavy-duty-vehicle-part import-adjustment-offset determination",
    ),
    (
        "entry_is_note40_patented_pharmaceutical_article",
        "entry-level determination that a U.S. note 40 candidate is covered by a valid unexpired U.S. patent",
    ),
    (
        "entry_is_personal_use_accompanied_baggage",
        "transaction determination that the goods are for personal use in accompanied baggage under HTS U.S. note 2(u)",
    ),
    (
        "entry_is_properly_claimed_chapter_98_entry",
        "declarant's Chapter 98 claim made under applicable CBP regulations for the entry transaction",
    ),
    (
        "entry_is_s232_copper_additional_member",
        "HTS U.S. note 16(c)(viii) additional-copper membership supplied by entry preparation",
    ),
    (
        "entry_is_s232_copper_primary_member",
        "HTS U.S. note 16(c)(v) primary-copper membership supplied by entry preparation",
    ),
    (
        "entry_is_s232_note16_c_ii_derivative_aluminum_member",
        "HTS U.S. note 16(c)(ii) derivative-aluminum membership supplied by entry preparation",
    ),
    (
        "entry_is_s232_note16_c_ix_derivative_aluminum_candidate",
        "HTS U.S. note 16(c)(ix) derivative-aluminum candidate membership supplied by entry preparation; candidate status alone does not establish the listed-metal-weight qualification",
    ),
    (
        "entry_is_s232_note16_c_vi_derivative_aluminum_candidate",
        "HTS U.S. note 16(c)(vi) derivative-aluminum candidate membership supplied by entry preparation; candidate status alone does not establish the listed-metal-weight qualification",
    ),
    (
        "entry_is_s232_note16_metal_chapter",
        "entry classification in HTS chapter 72, 73, 74, or 76 for the note 16(c)(vi)/(ix) listed-metal-weight exception",
    ),
    (
        "entry_is_s232_note33_auto_part_candidate",
        "HTS U.S. note 33(g) automobile-part candidate membership supplied by entry preparation",
    ),
    (
        "entry_is_s232_note33_vehicle_candidate",
        "HTS U.S. note 33(b) vehicle candidate membership supplied by entry preparation",
    ),
    (
        "entry_is_s232_note37_cabinet_vanity_candidate",
        "HTS U.S. note 37(f) cabinet/vanity candidate membership supplied by entry preparation",
    ),
    (
        "entry_is_s232_note37_softwood_member",
        "HTS U.S. note 37(b) softwood membership supplied by entry preparation",
    ),
    (
        "entry_is_s232_note37_upholstered_wood_furniture_member",
        "HTS U.S. note 37(d) upholstered-wood-furniture membership supplied by entry preparation",
    ),
    (
        "entry_is_s232_note38_bus_member",
        "HTS U.S. note 38(c) bus membership supplied by entry preparation",
    ),
    (
        "entry_is_s232_note38_mhd_part_candidate",
        "HTS U.S. note 38(i) medium/heavy-duty-vehicle-part candidate membership supplied by entry preparation",
    ),
    (
        "entry_is_s232_note38_mhd_vehicle_member",
        "HTS U.S. note 38(b) medium/heavy-duty-vehicle membership supplied by entry preparation",
    ),
    (
        "entry_is_s232_note39_semiconductor_candidate",
        "HTS U.S. note 39 semiconductor candidate membership supplied by entry preparation",
    ),
    (
        "entry_is_s232_note40_pharmaceutical_candidate",
        "HTS U.S. note 40 pharmaceutical candidate membership supplied by entry preparation",
    ),
    (
        "entry_is_section_122_exempt",
        "entry-preparation determination that an applicable section 122 surcharge exclusion in HTS U.S. note 2(aa) covers the entry",
    ),
    (
        "entry_is_section_201_cspv",
        "classification of the entry as a crystalline-silicon photovoltaic (CSPV) article within the expired HTS U.S. note 18 safeguard surface",
    ),
    (
        "entry_is_section_232_aluminum",
        "entry-preparation determination that the entry is an aluminum article or derivative covered by the applicable section 232 action",
    ),
    (
        "entry_is_section_232_covered",
        "entry-preparation determination of existing aluminum or steel section-232 coverage for cross-program exclusions",
    ),
    (
        "entry_is_section_232_steel",
        "entry-preparation determination that the entry is a steel article or derivative covered by the applicable section 232 action",
    ),
    (
        "entry_loaded_and_in_transit_before_july_24_2026",
        "carrier and entry records establishing the HTS 9903.05.85 transit condition before July 24, 2026 for entries before July 28, 2026",
    ),
    (
        "entry_qualifies_for_note33_certified_auto_part_heading_listed_in_notes_50_52",
        "importer certification for a U.S. note 33 automobile part whose heading is listed in notes 50 and 52",
    ),
    (
        "entry_qualifies_for_note33_vehicle_heading_listed_in_notes_50_52",
        "transaction qualification for a U.S. note 33 vehicle heading listed in notes 50 and 52",
    ),
    (
        "entry_qualifies_for_note38_certified_mhd_part_heading_listed_in_notes_50_52",
        "importer certification for a U.S. note 38 vehicle part whose heading is listed in notes 50 and 52",
    ),
    (
        "entry_qualifies_for_note39_heading_9903_79_01",
        "entry-level technical qualification for semiconductor heading 9903.79.01 under U.S. note 39",
    ),
    (
        "hts_line",
        "caller-selected exact HTS tariff-line key in the generated Rev-15 rate table after entry classification",
    ),
    (
        "hts_number",
        "full HTS statistical reporting number assigned to the entry by the declarant and accepted or corrected through CBP classification",
    ),
    ("is_postal_shipment", "carrier-channel fact that the shipment is postal"),
    (
        "resolved_non_ad_valorem_column2_rate",
        "entry-preparation resolution of the applicable specific, compound, or conditional non-ad-valorem column-2 duty to the Rate value consumed for chapter-99 schedule rows; no flat column-2 table value is inferred",
    ),
    (
        "shipment_value",
        "declared shipment value used by the postal/de-minimis branch, distinct from 19 U.S.C. 1401a customs value",
    ),
)
CANONICAL_INPUT_SCOPES_SHA256 = (
    "13625d5f125cea50515552e197e3d899d7b59467a2b04d121b2e73a2fef040a8"
)
# Keep a separate runtime copy so mutant tests exercise the same mutable
# declaration surface that the producer consumes without rewriting the
# independently digest-pinned semantic contract above.
INPUTS = list(CANONICAL_INPUT_SCOPES)


class EvidenceConfigurationError(ValueError):
    """Raised when an external frozen repository or engine is not configured."""


def configured_path(environment_variable: str, explicit: Path | None = None) -> Path:
    """Resolve an explicit/configured integration path without machine defaults."""
    raw = (
        str(explicit) if explicit is not None else os.environ.get(environment_variable)
    )
    if not raw:
        raise EvidenceConfigurationError(
            f"set {environment_variable} or pass the corresponding CLI path"
        )
    return Path(raw).expanduser().resolve()


def corpus_root(explicit: Path | None = None) -> Path:
    return configured_path(CORPUS_ROOT_ENV, explicit)


def rulespec_root(explicit: Path | None = None) -> Path:
    return configured_path(RULESPEC_ROOT_ENV, explicit)


def engine_source_root(explicit: Path | None = None) -> Path:
    return configured_path(ENGINE_SOURCE_ROOT_ENV, explicit)


def engine_binary(
    explicit: Path | None = None, *, source_root: Path | None = None
) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    configured = os.environ.get(ENGINE_BINARY_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    return engine_source_root(source_root) / "target/release/axiom-rules-engine"


def integration_configuration_available() -> bool:
    """Return whether clean-CI-external integration dependencies are configured."""
    try:
        paths = (
            corpus_root(),
            rulespec_root(),
            engine_source_root(),
            engine_binary(),
        )
    except EvidenceConfigurationError:
        return False
    return all(path.exists() for path in paths)


def git_command(root: Path, *args: str) -> bytes:
    p = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, check=False
    )
    if p.returncode:
        raise ValueError(p.stderr.decode(errors="replace").strip())
    return p.stdout


def verify_git_commit(root: Path, expected: str, label: str) -> str:
    commit = (
        git_command(root, "rev-parse", "--verify", f"{expected}^{{commit}}")
        .decode()
        .strip()
    )
    if commit != expected:
        raise ValueError(f"{label} source pin drift")
    return commit


def verify_engine_binding(
    *,
    source_root: Path | None = None,
    binary: Path | None = None,
) -> dict[str, str]:
    """Bind the frozen engine source object and separately pinned executable."""
    source = engine_source_root(source_root)
    verify_git_commit(source, ENGINE_SOURCE_REF, "engine")
    executable = engine_binary(binary, source_root=source)
    binary_digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    if binary_digest != INPUT_INVENTORY_ENGINE_SHA256:
        raise ValueError("frozen engine binary pin drift")
    return {
        "engine_source_repository": ENGINE_SOURCE_REPOSITORY,
        "engine_source_ref": ENGINE_SOURCE_REF,
        "engine_sha256": binary_digest,
    }


def input_scopes_sha256(rows: Sequence[tuple[str, str]]) -> str:
    payload = (
        json.dumps(
            list(rows),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def canonical_input_scope_digest() -> str:
    names = tuple(name for name, _scope in CANONICAL_INPUT_SCOPES)
    digest = input_scopes_sha256(CANONICAL_INPUT_SCOPES)
    if (
        len(CANONICAL_INPUT_SCOPES) != 58
        or names != AUDITED_REACHABLE_INPUTS
        or any(
            not isinstance(scope, str) or not scope.strip()
            for _name, scope in CANONICAL_INPUT_SCOPES
        )
        or digest != CANONICAL_INPUT_SCOPES_SHA256
    ):
        raise ValueError("canonical input-scope contract pin changed")
    return digest


def audited_input_inventory() -> dict[str, Any]:
    digest = hashlib.sha256(
        ("\n".join(AUDITED_REACHABLE_INPUTS) + "\n").encode()
    ).hexdigest()
    if len(AUDITED_REACHABLE_INPUTS) != 58 or digest != AUDITED_REACHABLE_INPUTS_SHA256:
        raise ValueError("audited reachable-input inventory pin changed")
    input_scopes_digest = canonical_input_scope_digest()
    return {
        "rulespec_ref": RULESPEC_REF,
        "engine_source_repository": ENGINE_SOURCE_REPOSITORY,
        "engine_source_ref": ENGINE_SOURCE_REF,
        "engine_sha256": INPUT_INVENTORY_ENGINE_SHA256,
        "method": "frozen historical all-version compiled-dependency audit; reproduced by reproduce_input_inventory",
        "module_scope": [WITNESS_MODULE, SCHEDULE_MODULE_PREFIX + "ch*/ch*.yaml"],
        "promised_outputs": {
            "witness": ["us_tariff_duty"],
            "schedule": ["schedule_statutory_stack"],
        },
        "schedule_composition_count": 100,
        "input_count": 58,
        "inputs_sha256": digest,
        "input_scopes_sha256": input_scopes_digest,
        "inputs": list(AUDITED_REACHABLE_INPUTS),
    }


def reachable_inputs_from_program(
    program: Mapping[str, Any], outputs: Sequence[str]
) -> set[str]:
    """Traverse compiled dependencies, not fixture keys or bare source tokens."""
    derived = program.get("derived")
    if not isinstance(derived, list) or any(
        not isinstance(rule, Mapping) or not isinstance(rule.get("name"), str)
        for rule in derived
    ):
        raise ValueError("compiled input inventory has malformed derived rules")
    by_name = {rule["name"]: rule for rule in derived}
    if len(by_name) != len(derived) or not set(outputs) <= by_name.keys():
        raise ValueError("compiled input inventory has missing or duplicate outputs")
    inputs: set[str] = set()
    visited: set[str] = set()

    def visit_expression(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                visit_expression(item)
        elif isinstance(node, Mapping):
            kind = node.get("kind")
            if kind in {"input", "input_or_else"}:
                name = node.get("name")
                if not isinstance(name, str) or not name:
                    raise ValueError("compiled input inventory has an unnamed input")
                inputs.add(name)
            elif kind == "derived":
                name = node.get("name")
                if not isinstance(name, str) or name not in by_name:
                    raise ValueError("compiled input inventory has an unresolved rule")
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
        if not isinstance(versions, list) or any(
            not isinstance(version, Mapping) for version in versions
        ):
            raise ValueError("compiled input inventory has malformed versions")
        for version in versions:
            visit_expression(version.get("expr"))

    for output in outputs:
        visit_rule(output)
    return inputs


def reproduce_input_inventory(
    *,
    rulespec_repository: Path | None = None,
    rulespec_ref: str = RULESPEC_REF,
    engine_repository: Path | None = None,
    engine_executable: Path | None = None,
) -> tuple[str, ...]:
    """Recheck the audited input union using an immutable Git export and Axiom."""
    audit = audited_input_inventory()
    rulespec_repository = rulespec_root(rulespec_repository)
    commit = verify_git_commit(rulespec_repository, rulespec_ref, "RuleSpec")
    if commit != audit["rulespec_ref"]:
        raise ValueError("input inventory RuleSpec source pin drift")
    engine_repository = engine_source_root(engine_repository)
    engine_executable = engine_binary(engine_executable, source_root=engine_repository)
    binding = verify_engine_binding(
        source_root=engine_repository, binary=engine_executable
    )
    engine_bytes = engine_executable.read_bytes()
    engine_digest = hashlib.sha256(engine_bytes).hexdigest()
    if binding["engine_source_ref"] != audit["engine_source_ref"]:
        raise ValueError("input inventory engine source pin drift")
    if engine_digest != audit["engine_sha256"]:
        raise ValueError("input inventory engine binary pin drift")
    paths = (
        git_command(rulespec_repository, "ls-tree", "-r", "--name-only", commit)
        .decode()
        .splitlines()
    )
    chapters = sorted(
        path
        for path in paths
        if path.startswith(SCHEDULE_MODULE_PREFIX)
        and path.endswith(".yaml")
        and not path.endswith(".test.yaml")
    )
    if len(chapters) != audit["schedule_composition_count"]:
        raise ValueError("input inventory schedule composition count changed")
    programs = [
        (WITNESS_MODULE, "programs/us/us-tariff-duty/fy-2026.yaml", "witness")
    ] + [
        (path, f"programs/us/us-tariff-schedule/{Path(path).stem}.yaml", "schedule")
        for path in chapters
    ]
    inputs: set[str] = set()
    with tempfile.TemporaryDirectory(prefix="tariff-closure-input-inventory-") as raw:
        snapshot = Path(raw) / "rulespec-us"
        snapshot.mkdir()
        # Execute the exact bytes just hashed, not a live path that could be
        # replaced between compilations while retaining the same final hash.
        snapshot_engine = Path(raw) / "axiom-rules-engine"
        snapshot_engine.write_bytes(engine_bytes)
        snapshot_engine.chmod(0o700)
        archive_bytes = git_command(
            rulespec_repository, "archive", "--format=tar", commit
        )
        try:
            with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
                archive.extractall(snapshot, filter="data")
        except tarfile.TarError as exc:
            raise ValueError(f"input inventory Git export failed: {exc}") from exc
        env = dict(os.environ)
        env.pop("AXIOM_RULESPEC_ROOT", None)
        env["AXIOM_RULESPEC_REPO_ROOTS"] = str(snapshot.parent)
        for module_path, spec_path, kind in programs:
            spec = yaml.safe_load((snapshot / spec_path).read_text())
            outputs = spec.get("outputs") if isinstance(spec, Mapping) else None
            if outputs != audit["promised_outputs"][kind]:
                raise ValueError(
                    f"input inventory promised outputs changed: {spec_path}"
                )
            compiled_path = Path(raw) / "inventory.compiled.json"
            compiled_path.unlink(missing_ok=True)
            result = subprocess.run(
                [
                    str(snapshot_engine),
                    "compile",
                    "--program",
                    str(snapshot / module_path),
                    "--output",
                    str(compiled_path),
                ],
                capture_output=True,
                check=False,
                text=True,
                env=env,
            )
            if result.returncode:
                raise ValueError(
                    f"input inventory compile failed for {module_path}: {result.stderr.strip()}"
                )
            # A regular file works under restricted device access and keeps the
            # CLI's human-readable stdout summary separate from artifact JSON.
            payload = json.loads(compiled_path.read_text())
            program = payload.get("program") if isinstance(payload, Mapping) else None
            if not isinstance(program, Mapping):
                raise TypeError("compiled input inventory has no program")
            inputs.update(reachable_inputs_from_program(program, outputs))
    if hashlib.sha256(engine_executable.read_bytes()).hexdigest() != engine_digest:
        raise ValueError("input inventory engine changed during compilation")
    observed = tuple(sorted(inputs))
    if observed != AUDITED_REACHABLE_INPUTS:
        raise ValueError(
            "compiled reachable-input inventory changed: "
            f"missing={sorted(set(AUDITED_REACHABLE_INPUTS) - inputs)}, "
            f"unexpected={sorted(inputs - set(AUDITED_REACHABLE_INPUTS))}"
        )
    return observed


SCOPE_EVIDENCE = {
    "cbp_agrees_chapter_98_entry_is_appropriate": (
        "note2-exceptions.json",
        384,
        "captured_for_frozen_snapshot",
        "bounded_source_truth_table_replay_matches",
        "no_mismatch_detected_in_bounded_checks",
    ),
    "entry_is_9802_excepted_entry": (
        "note2-exceptions.json",
        384,
        "captured_for_frozen_snapshot",
        "bounded_source_truth_table_replay_matches",
        "no_mismatch_detected_in_bounded_checks",
    ),
    "entry_is_china_301_2024_action": (
        "china-action.json",
        36,
        "captured_live_primary_source",
        "blocked_on_missing_adapter_note31_membership",
        "known_source_runtime_mismatch",
    ),
    "entry_is_china_301_list123": (
        "china-lists.json",
        18,
        "captured_live_primary_source",
        "blocked_on_beer_list3_overlap",
        "known_source_runtime_mismatch",
    ),
    "entry_is_china_301_list4a": (
        "china-lists.json",
        18,
        "captured_live_primary_source",
        "bounded_nonexcluded_list4a_replay_matches",
        "no_mismatch_detected_in_bounded_checks",
    ),
    "entry_is_china_301_solar": (
        "china-action.json",
        36,
        "captured_live_primary_source",
        "blocked_on_missing_adapter_note31_membership",
        "known_source_runtime_mismatch",
    ),
    "entry_is_entered_free_of_duty_under_usmca": (
        "note52-transit-usmca.json",
        230,
        "captured_live_primary_source",
        "bounded_stipulated_fact_replay_matches",
        "no_mismatch_detected_in_bounded_checks",
    ),
    "entry_is_humanitarian_donation_article": (
        "note2-exceptions.json",
        384,
        "captured_for_frozen_snapshot",
        "bounded_source_truth_table_replay_matches",
        "no_mismatch_detected_in_bounded_checks",
    ),
    "entry_is_informational_material_article": (
        "note2-exceptions.json",
        384,
        "captured_for_frozen_snapshot",
        "bounded_source_truth_table_replay_matches",
        "no_mismatch_detected_in_bounded_checks",
    ),
    "entry_is_line_a": (
        "hts-identity.json",
        63,
        "captured_live_primary_source",
        "bounded_canonical_contract_replay_matches",
        "no_mismatch_detected_in_bounded_checks",
    ),
    "entry_is_line_b": (
        "hts-identity.json",
        63,
        "captured_live_primary_source",
        "bounded_canonical_contract_replay_matches",
        "no_mismatch_detected_in_bounded_checks",
    ),
    "entry_is_line_d": (
        "hts-identity.json",
        63,
        "captured_live_primary_source",
        "bounded_canonical_contract_replay_matches",
        "no_mismatch_detected_in_bounded_checks",
    ),
    "entry_is_personal_use_accompanied_baggage": (
        "note2-exceptions.json",
        384,
        "captured_for_frozen_snapshot",
        "bounded_source_truth_table_replay_matches",
        "no_mismatch_detected_in_bounded_checks",
    ),
    "entry_is_properly_claimed_chapter_98_entry": (
        "note2-exceptions.json",
        384,
        "captured_for_frozen_snapshot",
        "bounded_source_truth_table_replay_matches",
        "no_mismatch_detected_in_bounded_checks",
    ),
    "entry_is_section_122_exempt": (
        "temporal-boundaries.json",
        23,
        "captured_live_primary_source",
        "blocked_at_subminute_activation",
        "known_source_runtime_mismatch",
    ),
    "entry_is_section_201_cspv": (
        "temporal-boundaries.json",
        20,
        "captured_live_primary_source",
        "bounded_postexpiry_replay_only",
        "post_expiry_only",
    ),
    "entry_is_section_232_aluminum": (
        "primary-metals.json",
        28,
        "captured_live_primary_source",
        "blocked_on_missing_uk_note16_d_qualification",
        "known_source_runtime_mismatch",
    ),
    "entry_is_section_232_steel": (
        "primary-metals.json",
        28,
        "captured_live_primary_source",
        "blocked_on_missing_uk_note16_d_qualification",
        "known_source_runtime_mismatch",
    ),
    "entry_loaded_and_in_transit_before_july_24_2026": (
        "note52-transit-usmca.json",
        230,
        "captured_live_primary_source",
        "blocked_at_subminute_entry_cutoff",
        "known_source_runtime_mismatch",
    ),
    "hts_line": (
        "hts-identity.json",
        63,
        "captured_live_primary_source",
        "bounded_canonical_contract_replay_matches",
        "no_mismatch_detected_in_bounded_checks",
    ),
    "resolved_non_ad_valorem_column2_rate": (
        "column2-resolution.json",
        41,
        "captured_live_primary_source",
        "blocked_on_external_non_ad_valorem_resolution_and_vintage_admission",
        "diagnostic_contract_only",
    ),
}

RECEIPT_PRODUCERS = {
    "note2-exceptions.json": "scripts/build_us_tariff_boundary_evidence.py",
    "note52-transit-usmca.json": "scripts/build_us_tariff_note52_boundary_evidence.py",
    "hts-identity.json": "scripts/build_us_tariff_identity_evidence.py",
    "china-action.json": "scripts/build_us_tariff_china_action_evidence.py",
    "temporal-boundaries.json": "scripts/build_us_tariff_temporal_evidence.py",
    "china-lists.json": "scripts/build_us_tariff_china_list_evidence.py",
    "column2-resolution.json": "scripts/build_us_tariff_column2_evidence.py",
    "primary-metals.json": "scripts/build_us_tariff_metal_evidence.py",
}


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_frontier_inventory(
    *,
    verify_reachable_inputs: bool = True,
    rulespec_repository: Path | None = None,
    engine_repository: Path | None = None,
    engine_executable: Path | None = None,
) -> dict[str, Any]:
    """Build the bounded historical inventory without touching live closure."""
    audit = audited_input_inventory()
    if verify_reachable_inputs:
        observed = reproduce_input_inventory(
            rulespec_repository=rulespec_repository,
            engine_repository=engine_repository,
            engine_executable=engine_executable,
        )
        if observed != AUDITED_REACHABLE_INPUTS:
            raise ValueError("live reachable-input reproduction drift")
    if set(SCOPE_EVIDENCE) - set(audit["inputs"]):
        raise ValueError("evidence scope is outside the frozen reachable-input set")
    if len(SCOPE_EVIDENCE) != 21:
        raise ValueError("bounded evidence scope count changed")

    receipts: dict[str, dict[str, Any]] = {}
    receipt_documents: dict[str, dict[str, Any]] = {}
    for filename, producer in RECEIPT_PRODUCERS.items():
        path = EVIDENCE_DIRECTORY / filename
        document = json.loads(path.read_bytes())
        if document.get("rulespec_ref") != RULESPEC_REF:
            raise ValueError(f"frozen RuleSpec pin drift: {filename}")
        if document.get("engine_sha256") != INPUT_INVENTORY_ENGINE_SHA256:
            raise ValueError(f"frozen engine pin drift: {filename}")
        if document.get("engine_source_ref") != ENGINE_SOURCE_REF:
            raise ValueError(f"frozen engine source pin drift: {filename}")
        claim = document.get("claim", {})
        if any(
            claim.get(key) is not False
            for key in ("closed", "certified", "release_authorized")
        ):
            raise ValueError(f"receipt overclaims admission: {filename}")
        producer_path = ROOT / producer
        producer_sha256 = file_sha256(producer_path)
        if document.get("producer_sha256") != producer_sha256:
            raise ValueError(f"producer binding drift: {filename}")
        receipts[filename] = {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": file_sha256(path),
            "producer": producer,
            "producer_sha256": producer_sha256,
        }
        receipt_documents[filename] = document

    replay_path = EVIDENCE_DIRECTORY / "continuation-replay-manifest.json"
    replay = json.loads(replay_path.read_bytes())
    totals = replay.get("verification", {}).get("totals")
    expected_totals = {
        "query_executions": 843,
        "successful_result_rows": 831,
        "returned_output_bindings": 1817,
        "native_missing_input_errors": 12,
        "distinct_entity_ids": 453,
    }
    if totals != expected_totals:
        raise ValueError("bounded replay population drift")
    mismatch_records = [
        row
        for name in (
            "note52-transit-usmca.json",
            "china-action.json",
            "temporal-boundaries.json",
            "china-lists.json",
            "primary-metals.json",
        )
        for row in receipt_documents[name].get("known_mismatches", [])
    ]
    mismatch_record_count = len(mismatch_records)
    mismatch_scenario_ids = {row["case_id"] for row in mismatch_records}
    identity_differences = receipt_documents["hts-identity.json"]["validation"][
        "raw_direct_witness_alias_differences"
    ]
    if (
        mismatch_record_count != 30
        or len(mismatch_scenario_ids) != 19
        or identity_differences != 9
    ):
        raise ValueError("bounded finding population drift")

    classes: dict[str, int] = {}
    inputs = []
    for name, scope in CANONICAL_INPUT_SCOPES:
        row: dict[str, Any] = {
            "input": name,
            "canonical_scope": scope,
            "grounding": "uncaptured",
            "among_21_evidence_covered_scopes": name in SCOPE_EVIDENCE,
            "evidence_receipt": None,
            "receipt_query_executions": 0,
            "bounded_source_evidence": "not_captured_this_batch",
        }
        evidence = SCOPE_EVIDENCE.get(name)
        if evidence:
            filename, cases, source_kind, status, coverage_class = evidence
            classes[coverage_class] = classes.get(coverage_class, 0) + 1
            row.update(
                evidence_receipt=receipts[filename]["path"],
                receipt_query_executions=cases,
                bounded_source_evidence=source_kind,
                scope_validation_status=status,
                evidence_class=coverage_class,
            )
        inputs.append(row)
    expected_classes = {
        "no_mismatch_detected_in_bounded_checks": 12,
        "known_source_runtime_mismatch": 7,
        "post_expiry_only": 1,
        "diagnostic_contract_only": 1,
    }
    if classes != expected_classes:
        raise ValueError("bounded evidence class population drift")

    live_path = EVIDENCE_DIRECTORY / "live-sources/receipt.json"
    live = json.loads(live_path.read_bytes())
    live_producer = ROOT / "scripts/us_tariff_live_source_evidence.py"
    if live.get("producer_sha256") != file_sha256(live_producer):
        raise ValueError("live-source producer binding drift")
    if any(
        live["claim"].get(key) is not False
        for key in ("closed", "certified", "release_authorized")
    ):
        raise ValueError("live-source receipt overclaims admission")

    return {
        "schema": "axiom_oracles.us_tariff_schedule.frozen_evidence_frontier.v2",
        "generated_by": "scripts/us_tariff_evidence_snapshot.py",
        "producer_sha256": file_sha256(Path(__file__)),
        "snapshot_kind": SNAPSHOT_KIND,
        "current_certification_authority": CURRENT_CERTIFICATION_AUTHORITY,
        "repository_base_ref": REPOSITORY_BASE_REF,
        "rulespec_ref": RULESPEC_REF,
        "corpus_ref": CORPUS_REF,
        "engine_source_repository": ENGINE_SOURCE_REPOSITORY,
        "engine_source_ref": ENGINE_SOURCE_REF,
        "engine_sha256": INPUT_INVENTORY_ENGINE_SHA256,
        "reachable_input_inventory_live_reproduced": verify_reachable_inputs,
        "canonical_scope_sha256": CANONICAL_INPUT_SCOPES_SHA256,
        "counts": {
            "reachable_inputs": 58,
            "named_scopes": 58,
            "evidence_covered_scopes": 21,
            "source_groundings_still_uncaptured": 58,
            "fully_admitted_or_grounded_scopes": 0,
            **expected_classes,
            "runtime_query_executions": totals["query_executions"],
            "distinct_runtime_entity_ids": totals["distinct_entity_ids"],
            "successful_runtime_result_rows": totals["successful_result_rows"],
            "returned_output_bindings": totals["returned_output_bindings"],
            "intentional_native_missing_input_errors": totals[
                "native_missing_input_errors"
            ],
            "source_runtime_mismatch_records": mismatch_record_count,
            "distinct_mismatch_scenarios": len(mismatch_scenario_ids),
            "raw_identity_differences": identity_differences,
        },
        "receipts": receipts,
        "live_source_supplement": {
            "path": live_path.relative_to(ROOT).as_posix(),
            "sha256": file_sha256(live_path),
            "producer": live["generated_by"],
            "producer_sha256": live["producer_sha256"],
        },
        "replay_manifest": {
            "path": replay_path.relative_to(ROOT).as_posix(),
            "sha256": file_sha256(replay_path),
            "manifest_sha256": replay["verification"]["manifest_sha256"],
        },
        "inputs": inputs,
        "claim": {
            "kind": "bounded_frozen_historical_evidence",
            "closed": False,
            "certified": False,
            "release_authorized": False,
            "current_certification_status_inferred": False,
            "expectation_provenance": "source-linked reviewed transcriptions",
            "expectations_independently_pdf_derived": False,
            "engine_binary_reproducible_build_verified": False,
        },
    }


def render_frontier_inventory(document: Mapping[str, Any]) -> str:
    return json.dumps(document, sort_keys=True, indent=2, allow_nan=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--rulespec-root", type=Path)
    parser.add_argument("--engine-root", type=Path)
    parser.add_argument("--engine", type=Path)
    args = parser.parse_args()
    try:
        body = render_frontier_inventory(
            build_frontier_inventory(
                verify_reachable_inputs=True,
                rulespec_repository=args.rulespec_root,
                engine_repository=args.engine_root,
                engine_executable=args.engine,
            )
        )
        if args.check:
            if FRONTIER_INVENTORY.read_text() != body:
                raise ValueError("frozen evidence frontier inventory drift")
        else:
            FRONTIER_INVENTORY.parent.mkdir(parents=True, exist_ok=True)
            temporary = FRONTIER_INVENTORY.with_suffix(".tmp")
            temporary.write_text(body)
            temporary.replace(FRONTIER_INVENTORY)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f"frozen evidence snapshot failed: {exc}", file=sys.stderr)
        return 1
    print(
        "frozen evidence frontier reproduced: 21 scopes, 58 uncaptured groundings, "
        "843 query executions / 453 distinct IDs, 1817 output bindings, "
        "30 mismatch records / 19 unique scenarios, certified=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
