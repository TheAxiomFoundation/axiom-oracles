#!/usr/bin/env python3
"""Reproduce the US tariff source-completeness ledger.

Contract (adopted from axiom-oracles PR #475, commits 5402e5bf6 and
75bb586ae): generated facts come only from immutable corpus and RuleSpec Git
objects; review decisions are committed; ``computed`` is their pure join.

Statuses mean: ``encoded`` is present in the composed executable program;
``partially-encoded`` has an encoded rule or membership table but is not fully
composed; ``excluded-with-reason`` is in a declared root but cannot affect the
program result for the stated reason; ``pending`` can affect it and is not
encoded.  A declared corpus root is the complete, versioned source population
whose denominator is promised here, not merely citations selected by modules.

The boundary-input frontier is complete only when every entry fact reachable
from the promised outputs has a named external semantic scope. Missing scopes
are explicit and keep the frontier incomplete. ``--check`` re-censuses both
repositories, reproduces the committed input inventory with the pinned engine,
and requires byte-identical output. ``closed`` is true only when there are no
partial/pending families, all root populations reconcile, and the complete
input frontier is classified.
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
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "conformance/closure/us-tariff-duty.yaml"
CORPUS = Path.home() / "TheAxiomFoundation/_worktrees/axiom-corpus-gn29-20260828"
CORPUS_REF = "cc18c703741425a3ebf994a2975cae158bd305d1"
RULESPEC = (
    Path.home()
    / "TheAxiomFoundation/_worktrees/tariff-policy-combined-20260829/rulespec-us"
)
RULESPEC_REF = "4f591c4267063094cc6da9d590872ea982940b81"
SCHEDULE = "data/corpus/provisions/us/statute/2026-08-09-usitc-hts-2026-rev15-full-schedule.jsonl"
NOTES = "data/corpus/provisions/us/statute/2026-08-04-usitc-hts-2026-rev15-notes.jsonl"
GENERAL_NOTE_29 = "data/corpus/provisions/us/statute/2026-08-28-usitc-hts-2026-rev15-general-note-29.jsonl"
SCHEMA = "axiom_oracles.closure.ledger.v1"
SCHEDULE_SHA256 = "6c8d07d21a1e3f2233197c1b2f96169f01a1a768dd2509a71c0fdb03d4a99d14"
SCHEDULE_VERSION = "2026-08-09-usitc-hts-2026-rev15-full-schedule"
SCHEDULE_DECLARED_COUNT = 29_845
NOTES_SHA256 = "0f3ed7ef2efb64383825db65e615959200770e8511c8d4834b16e02892cb9ec8"
NOTES_VERSION = "2026-08-04-usitc-hts-2026-rev15-notes"
NOTES_DECLARED_COUNT = 805
GENERAL_NOTE_29_SHA256 = (
    "3b3de5d98c81bad3cc560fcb738551591d7b7b5c080ca914718047a4a797368b"
)
GENERAL_NOTE_29_VERSION = "2026-08-28-usitc-hts-2026-rev15-general-note-29"
GENERAL_NOTE_29_DECLARED_COUNT = 93
RULESPEC_MODULE_COUNT = 415
RULESPEC_PATHS_SHA256 = (
    "4dcc60251e73e11ec25c0909c57aa523b46a50569bfec964545bb6c6adcef1e3"
)
STATUSES = ("encoded", "partially-encoded", "excluded-with-reason", "pending")
MODULE_PREFIXES = (
    "us/policies/usitc/us-tariff-duty/",
    "us/policies/cbp/us-tariff-",
    "us/policies/usitc/us-tariff-incidence/",
)
INPUT_INVENTORY_ENGINE = (
    Path.home()
    / "TheAxiomFoundation/axiom-rules-engine-pinned/target/release/axiom-rules-engine"
)
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


@dataclass(frozen=True)
class ClosureSummary:
    """Hermetically derived certificate inputs from a valid ledger."""

    closed: bool
    non_encoded_reasons_complete: bool


@dataclass(frozen=True)
class VerificationResult:
    """Result of re-deriving a ledger from its immutable source objects."""

    document: dict[str, Any] | None
    expected: dict[str, Any] | None
    errors: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.errors


EXPECTED_PROGRAM = {"id": "us/tariff-duty", "rulespec_ref": RULESPEC_REF}
EXPECTED_CORPUS_ROOTS = {
    "hts-rate-provisions": {
        "path": SCHEDULE,
        "commit": CORPUS_REF,
        "sha256": SCHEDULE_SHA256,
        "version": SCHEDULE_VERSION,
        "declared_count": SCHEDULE_DECLARED_COUNT,
    },
    "chapter-99-notes": {
        "path": NOTES,
        "commit": CORPUS_REF,
        "sha256": NOTES_SHA256,
        "version": NOTES_VERSION,
        "declared_count": NOTES_DECLARED_COUNT,
    },
    "dr-cafta-general-note-29": {
        "path": GENERAL_NOTE_29,
        "commit": CORPUS_REF,
        "sha256": GENERAL_NOTE_29_SHA256,
        "version": GENERAL_NOTE_29_VERSION,
        "declared_count": GENERAL_NOTE_29_DECLARED_COUNT,
    },
    "fr-instrument-families": {
        "derived_from": "composition source_verification plus overlays",
        "rulespec_commit": RULESPEC_REF,
    },
}
EXPECTED_RULESPEC_FACTS = {
    "commit": RULESPEC_REF,
    "module_count": RULESPEC_MODULE_COUNT,
    "paths_sha256": RULESPEC_PATHS_SHA256,
}
EXPECTED_SOURCE_COUNTS = {
    "rated-minus-9802": 13_781,
    "rated-9802": 5,
    "unrated": 16_059,
    "chapter99-remainder": 799,
    "general-note-29-d-v": 1,
    "general-note-29-remainder": 92,
}


DECISIONS = [
    {
        "root": "hts-rate-provisions",
        "family": "rated-lines-except-9802",
        "status": "encoded",
        "count_source": "rated-minus-9802",
        "reason": "B1.2 generated chapter tables supply the Rev-15 column rates.",
    },
    {
        "root": "hts-rate-provisions",
        "family": "9802-partial-value-rated-lines",
        "status": "partially-encoded",
        "count_source": "rated-9802",
        "reason": "The rate rows are passthroughs, but dutiable partial value is supplied as an entry input rather than derived.",
    },
    {
        "root": "hts-rate-provisions",
        "family": "unrated-structural-rows",
        "status": "excluded-with-reason",
        "count_source": "unrated",
        "reason": "Headings without a Rates of duty (1-General) field do not themselves supply a rate line.",
    },
    {
        "root": "chapter-99-notes",
        "family": "note-20-section-301-lists",
        "status": "encoded",
        "count": 1,
        "membership_rows": 301,
        "reason": "Incidence membership tables are composed for the original China list overlays.",
    },
    {
        "root": "chapter-99-notes",
        "family": "notes-16-19-section-232-metals",
        "status": "encoded",
        "count": 1,
        "membership_rows": 232,
        "reason": "Steel/aluminum incidence and composed overlays are present.",
    },
    {
        "root": "chapter-99-notes",
        "family": "note-18-section-201",
        "status": "encoded",
        "count": 1,
        "membership_rows": 201,
        "reason": "Section 201 solar incidence and overlay are composed.",
    },
    {
        "root": "chapter-99-notes",
        "family": "note-2aa-section-122",
        "status": "encoded",
        "count": 1,
        "membership_rows": 122,
        "reason": "Section 122 incidence and overlay are composed.",
    },
    {
        "root": "chapter-99-notes",
        "family": "notes-50-52-section-232-sector-precedence",
        "status": "partially-encoded",
        "count": 1,
        "reason": "Generated schedules derive the notes 50(a)(vi) and 52(f) precedence judgment, but transaction and certification qualifications remain declared entry facts rather than source-derived judgments.",
    },
    {
        "root": "chapter-99-notes",
        "family": "note-51-section-338",
        "status": "pending",
        "count": 1,
        "reason": "The Rev-15 chapter-99 root predates the August 19 section-338 action and contains no note 51; ingest the codified note and reconcile it to the Federal Register-backed composition.",
    },
    {
        "root": "chapter-99-notes",
        "family": "other-chapter-99-pages",
        "status": "partially-encoded",
        "count_source": "chapter99-remainder",
        "reason": "Generated schedules compose many 9903.01/.02/.05 and sector-precedence surfaces, but no page-level census proves every other chapter-99 note covered.",
    },
    {
        "root": "dr-cafta-general-note-29",
        "family": "note-29-d-v-textile-apparel-definition",
        "status": "partially-encoded",
        "count_source": "general-note-29-d-v",
        "reason": "The note 52(i) exception cites and composes General Note 29(d)(v), but membership still requires the WTO Agreement on Textiles and Clothing annex and a historical HTS concordance and is therefore a declared entry fact.",
    },
    {
        "root": "dr-cafta-general-note-29",
        "family": "note-29-origin-and-free-duty-remainder",
        "status": "pending",
        "count_source": "general-note-29-remainder",
        "reason": "The remaining 92 pages are ingested but their origin and tariff-treatment rules are not encoded; entry under DR-CAFTA free of duty remains a declared transaction fact.",
    },
    {
        "root": "fr-instrument-families",
        "family": "section-232-metal-instruments",
        "status": "encoded",
        "count": 1,
        "reason": "2018 and 2025 metal actions plus the 2026 annex restructure are represented in the composed aluminum/steel overlays.",
    },
    {
        "root": "fr-instrument-families",
        "family": "section-232-non-metal-annexes",
        "status": "pending",
        "count": 6,
        "reason": "Selected codified memberships now support notes 50/52 section-301 precedence, but the automobile/parts, copper, semiconductor, pharmaceutical, medium/heavy-duty-vehicle, and wood section-232 duty actions and their complete proclamation annexes are not composed.",
    },
    {
        "root": "fr-instrument-families",
        "family": "china-301-original-2018-actions",
        "status": "pending",
        "count": 1,
        "reason": "Original 2018 instruments are absent from the D0 corpus.",
    },
    {
        "root": "fr-instrument-families",
        "family": "china-301-2024-action",
        "status": "partially-encoded",
        "count": 1,
        "reason": "The 2024 action rate is composed, but generated schedules still consume a declared note-31 membership fact because the complete membership table is absent.",
    },
    {
        "root": "fr-instrument-families",
        "family": "brazil-301",
        "status": "encoded",
        "count": 1,
        "reason": "The Brazil component is composed in generated statutory stacks with note-50 exclusions and the locally derived notes-50/52 sector-precedence judgment.",
    },
    {
        "root": "fr-instrument-families",
        "family": "forced-labor-301",
        "status": "partially-encoded",
        "count": 1,
        "reason": "Country tiers and the entry-level exception wrapper are composed, including note 52(i), but section-232 qualifications and both General Note 29(d)(v) and DR-CAFTA free-duty eligibility remain declared facts.",
    },
    {
        "root": "fr-instrument-families",
        "family": "solar-china",
        "status": "partially-encoded",
        "count": 1,
        "reason": "The solar-China rate is composed, but generated schedules still consume a declared note-31 membership fact because the complete membership table is absent.",
    },
    {
        "root": "fr-instrument-families",
        "family": "section-201-proclamation-10339",
        "status": "encoded",
        "count": 1,
        "reason": "The solar safeguard is encoded and composed.",
    },
    {
        "root": "fr-instrument-families",
        "family": "section-122-proclamation-11012",
        "status": "encoded",
        "count": 1,
        "reason": "The temporary surcharge and exclusions are encoded and composed.",
    },
    {
        "root": "fr-instrument-families",
        "family": "ieepa-orders-and-termination",
        "status": "encoded",
        "count": 1,
        "reason": "Fentanyl, reciprocal families, exclusions, and termination are composed for the codified Rev-15 state.",
    },
    {
        "root": "fr-instrument-families",
        "family": "section-338-instruments",
        "status": "partially-encoded",
        "count": 1,
        "reason": "The Federal Register-backed section-338 component and entry wrapper are composed, but the later codified note-51 root and complete membership surface remain absent.",
    },
    {
        "root": "fr-instrument-families",
        "family": "historical-vintages",
        "status": "pending",
        "count": 1,
        "reason": "This ledger covers the Rev-15 codified state only; historical schedule/instrument vintages are not a reproduced root.",
    },
]

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


def _git(root: Path, *args: str) -> bytes:
    p = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    if p.returncode:
        raise ValueError(p.stderr.decode(errors="replace").strip())
    return p.stdout


def _blob_facts(
    root: Path, ref: str, relative: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    commit = _git(root, "rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()
    blob = _git(root, "show", f"{commit}:{relative}")
    rows = [json.loads(line) for line in blob.splitlines() if line.strip()]
    return rows, {
        "path": relative,
        "commit": commit,
        "sha256": hashlib.sha256(blob).hexdigest(),
        "version": rows[0]["version"],
    }


def _input_scopes_sha256(rows: Sequence[tuple[str, str]]) -> str:
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


def _canonical_input_scope_digest() -> str:
    names = tuple(name for name, _scope in CANONICAL_INPUT_SCOPES)
    digest = _input_scopes_sha256(CANONICAL_INPUT_SCOPES)
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


def _audited_input_inventory() -> dict[str, Any]:
    digest = hashlib.sha256(
        ("\n".join(AUDITED_REACHABLE_INPUTS) + "\n").encode()
    ).hexdigest()
    if len(AUDITED_REACHABLE_INPUTS) != 58 or digest != AUDITED_REACHABLE_INPUTS_SHA256:
        raise ValueError("audited reachable-input inventory pin changed")
    input_scopes_digest = _canonical_input_scope_digest()
    return {
        "rulespec_ref": RULESPEC_REF,
        "engine_sha256": INPUT_INVENTORY_ENGINE_SHA256,
        "method": "committed audit of all-version compiled dependencies; reproduced by --generate and --check",
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


def _reachable_inputs_from_program(
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
    rulespec_root: Path = RULESPEC,
    rulespec_ref: str = RULESPEC_REF,
    engine_binary: Path = INPUT_INVENTORY_ENGINE,
) -> tuple[str, ...]:
    """Recheck the audited input union using an immutable Git export and Axiom."""
    audit = _audited_input_inventory()
    commit = (
        _git(rulespec_root, "rev-parse", "--verify", f"{rulespec_ref}^{{commit}}")
        .decode()
        .strip()
    )
    if commit != audit["rulespec_ref"]:
        raise ValueError("input inventory RuleSpec source pin drift")
    engine_binary = engine_binary.resolve()
    engine_bytes = engine_binary.read_bytes()
    engine_digest = hashlib.sha256(engine_bytes).hexdigest()
    if engine_digest != audit["engine_sha256"]:
        raise ValueError("input inventory engine source pin drift")
    paths = (
        _git(rulespec_root, "ls-tree", "-r", "--name-only", commit)
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
        archive_bytes = _git(rulespec_root, "archive", "--format=tar", commit)
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
            result = subprocess.run(
                [
                    str(snapshot_engine),
                    "compile",
                    "--program",
                    str(snapshot / module_path),
                    "--output",
                    "/dev/stdout",
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            if result.returncode:
                raise ValueError(
                    f"input inventory compile failed for {module_path}: {result.stderr.strip()}"
                )
            # The pinned CLI appends a human-readable compile summary after JSON.
            payload, _ = json.JSONDecoder().raw_decode(result.stdout)
            program = payload.get("program") if isinstance(payload, Mapping) else None
            if not isinstance(program, Mapping):
                raise ValueError("compiled input inventory has no program")
            inputs.update(_reachable_inputs_from_program(program, outputs))
    if hashlib.sha256(engine_binary.read_bytes()).hexdigest() != engine_digest:
        raise ValueError("input inventory engine changed during compilation")
    observed = tuple(sorted(inputs))
    if observed != AUDITED_REACHABLE_INPUTS:
        raise ValueError(
            "compiled reachable-input inventory changed: "
            f"missing={sorted(set(AUDITED_REACHABLE_INPUTS) - inputs)}, "
            f"unexpected={sorted(inputs - set(AUDITED_REACHABLE_INPUTS))}"
        )
    return observed


def _decision_state(
    source_counts: Mapping[str, int],
) -> tuple[dict[str, Any], dict[str, Any]]:
    ledger: list[dict[str, Any]] = []
    for decision in DECISIONS:
        row = dict(decision)
        count_source = row.pop("count_source", None)
        if count_source is not None:
            row["count"] = source_counts[count_source]
        ledger.append(row)
    counts: dict[str, dict[str, int]] = {}
    for row in ledger:
        bucket = counts.setdefault(row["root"], {status: 0 for status in STATUSES})
        bucket[row["status"]] += row["count"]
    pending = [
        {
            "family": row["family"],
            "root": row["root"],
            "status": row["status"],
            "blocker": row["reason"],
        }
        for row in ledger
        if row["status"] in ("pending", "partially-encoded")
    ]
    frontier = [
        {"input": name, "grounding": "uncaptured", "uncaptured_scope": scope}
        for name, scope in INPUTS
    ]
    audited_inventory = _audited_input_inventory()
    declared_input_names = [name for name, _scope in INPUTS]
    declared_input_counts = Counter(declared_input_names)
    scoped_inputs = {
        name for name, scope in INPUTS if isinstance(scope, str) and scope.strip()
    }
    required_inputs = set(audited_inventory["inputs"])
    missing_inputs = sorted(required_inputs - scoped_inputs)
    unexpected_inputs = sorted(set(declared_input_names) - required_inputs)
    duplicate_inputs = sorted(
        name for name, count in declared_input_counts.items() if count != 1
    )
    input_scopes_digest = _input_scopes_sha256(INPUTS)
    scope_contract_complete = (
        input_scopes_digest == audited_inventory["input_scopes_sha256"]
    )
    frontier_complete = not (
        missing_inputs
        or unexpected_inputs
        or duplicate_inputs
        or not scope_contract_complete
    )
    decisions = {
        "ledger": ledger,
        "input_grounding": frontier,
        "audited_input_inventory": audited_inventory,
    }
    computed = {
        "counts_by_status_per_root": counts,
        "burndown": pending,
        "boundary_frontier": {
            "complete": frontier_complete,
            "input_count": len(frontier),
            "inputs": frontier,
            "required_input_count": len(audited_inventory["inputs"]),
            "missing_input_count": len(missing_inputs),
            "missing_inputs": missing_inputs,
            "unexpected_input_count": len(unexpected_inputs),
            "unexpected_inputs": unexpected_inputs,
            "duplicate_input_count": len(duplicate_inputs),
            "duplicate_inputs": duplicate_inputs,
            "scope_contract_complete": scope_contract_complete,
            "input_scopes_sha256": input_scopes_digest,
        },
        "closed": not pending
        and frontier_complete
        and all(sum(values.values()) > 0 for values in counts.values()),
    }
    return decisions, computed


def build(
    *,
    corpus_root: Path = CORPUS,
    corpus_ref: str = CORPUS_REF,
    rulespec_root: Path = RULESPEC,
    rulespec_ref: str = RULESPEC_REF,
    engine_binary: Path = INPUT_INVENTORY_ENGINE,
) -> dict[str, Any]:
    schedule, sf = _blob_facts(corpus_root, corpus_ref, SCHEDULE)
    notes, nf = _blob_facts(corpus_root, corpus_ref, NOTES)
    general_note_29, gn29f = _blob_facts(corpus_root, corpus_ref, GENERAL_NOTE_29)
    srows = schedule[1:]
    rated = [
        r for r in srows if r.get("body") and "Rates of duty (1-General):" in r["body"]
    ]
    r9802 = [r for r in rated if r["citation_path"].split("/")[-1].startswith("9802")]
    chapter99 = [
        r for r in notes if r.get("parent_citation_path") == "us/statute/hts/chapter-99"
    ]
    general_note_29_pages = [
        r
        for r in general_note_29
        if r.get("parent_citation_path") == "us/statute/hts/general-note-29"
    ]
    general_note_29_d_v = [
        r
        for r in general_note_29_pages
        if r.get("citation_path") == "us/statute/hts/general-note-29/page-4"
    ]
    rs_commit = (
        _git(rulespec_root, "rev-parse", "--verify", f"{rulespec_ref}^{{commit}}")
        .decode()
        .strip()
    )
    paths = (
        _git(rulespec_root, "ls-tree", "-r", "--name-only", rs_commit)
        .decode()
        .splitlines()
    )
    modules = sorted(
        p
        for p in paths
        if p.endswith(".yaml")
        and not p.endswith(".test.yaml")
        and p.startswith(MODULE_PREFIXES)
    )
    reproduce_input_inventory(
        rulespec_root=rulespec_root,
        rulespec_ref=rs_commit,
        engine_binary=engine_binary,
    )
    source_counts = {
        "rated-minus-9802": len(rated) - len(r9802),
        "rated-9802": len(r9802),
        "unrated": len(srows) - len(rated),
        "chapter99-remainder": len(chapter99) - 6,
        "general-note-29-d-v": len(general_note_29_d_v),
        "general-note-29-remainder": len(general_note_29_pages)
        - len(general_note_29_d_v),
    }
    decisions, computed = _decision_state(source_counts)
    return {
        "schema": SCHEMA,
        "program": {"id": "us/tariff-duty", "rulespec_ref": rs_commit},
        "generated_facts": {
            "corpus_roots": {
                "hts-rate-provisions": {**sf, "declared_count": len(srows)},
                "chapter-99-notes": {
                    **nf,
                    "declared_count": len(chapter99),
                },
                "dr-cafta-general-note-29": {
                    **gn29f,
                    "declared_count": len(general_note_29_pages),
                },
                "fr-instrument-families": {
                    "derived_from": "composition source_verification plus overlays",
                    "rulespec_commit": rs_commit,
                },
            },
            "rulespec": {
                "commit": rs_commit,
                "module_count": len(modules),
                "paths_sha256": hashlib.sha256(
                    ("\n".join(modules) + "\n").encode()
                ).hexdigest(),
            },
        },
        "committed_decisions": decisions,
        "computed": computed,
    }


def serialize(doc: dict[str, Any]) -> str:
    return (
        "# GENERATED facts; edit decisions in scripts/us_tariff_closure.py.\n"
        + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=110)
    )


def validate(doc: dict[str, Any]) -> list[str]:
    errors = []
    expected_decisions, expected_computed = _decision_state(EXPECTED_SOURCE_COUNTS)
    if doc.get("schema") != SCHEMA:
        errors.append("wrong schema")
    if doc.get("program") != EXPECTED_PROGRAM:
        errors.append("program source pin drift")
    generated_facts = doc.get("generated_facts")
    if not isinstance(generated_facts, Mapping):
        errors.append("generated source facts are malformed")
        roots: Mapping[str, Any] = {}
    else:
        roots = generated_facts.get("corpus_roots", {})
        if roots != EXPECTED_CORPUS_ROOTS:
            errors.append("generated corpus source pins changed")
        if generated_facts.get("rulespec") != EXPECTED_RULESPEC_FACTS:
            errors.append("generated RuleSpec source pin changed")
    committed_decisions = doc.get("committed_decisions")
    if committed_decisions != expected_decisions:
        errors.append("committed closure decisions changed")
    computed = doc.get("computed")
    if computed != expected_computed:
        errors.append("computed closure state changed")
    if not isinstance(computed, Mapping):
        computed = {}
    ledger = (
        committed_decisions.get("ledger", [])
        if isinstance(committed_decisions, Mapping)
        else []
    )
    if not isinstance(ledger, list):
        errors.append("invalid status or missing reason")
        ledger = []
    elif any(
        not isinstance(row, Mapping)
        or row.get("status") not in STATUSES
        or not row.get("reason")
        for row in ledger
    ):
        errors.append("invalid status or missing reason")
    expected_frontier = expected_computed["boundary_frontier"]
    should_close = expected_frontier["complete"] and not any(
        r.get("status") in ("pending", "partially-encoded") for r in ledger
    )
    if computed.get("closed") != should_close:
        errors.append("computed.closed is not derived")
    frontier = computed.get("boundary_frontier", {})
    if not isinstance(frontier, Mapping):
        errors.append("boundary frontier is malformed")
        frontier = {}
    if (
        type(frontier.get("complete")) is not bool
        or frontier.get("complete") != expected_frontier["complete"]
    ):
        errors.append("boundary frontier completeness is not derived")
    if frontier.get("input_count") != len(INPUTS):
        errors.append("boundary frontier input count changed")
    if any(
        frontier.get(key) != expected_frontier[key]
        for key in (
            "required_input_count",
            "missing_input_count",
            "missing_inputs",
            "unexpected_input_count",
            "unexpected_inputs",
            "duplicate_input_count",
            "duplicate_inputs",
            "scope_contract_complete",
            "input_scopes_sha256",
        )
    ):
        errors.append("boundary frontier input set is not derived")
    expected_inputs = [
        {"input": name, "grounding": "uncaptured", "uncaptured_scope": scope}
        for name, scope in INPUTS
    ]
    if frontier.get("inputs") != expected_inputs:
        errors.append("boundary frontier inputs changed")
    expected_burndown = [
        {
            "family": row.get("family"),
            "root": row.get("root"),
            "status": row.get("status"),
            "blocker": row.get("reason"),
        }
        for row in ledger
        if isinstance(row, Mapping)
        and row.get("status") in ("pending", "partially-encoded")
    ]
    if computed.get("burndown") != expected_burndown:
        errors.append("computed.burndown is not derived")
    counts = computed.get("counts_by_status_per_root")
    if not isinstance(counts, Mapping) or not isinstance(roots, Mapping):
        errors.append("root counts are malformed")
    else:
        for root in (
            "hts-rate-provisions",
            "chapter-99-notes",
            "dr-cafta-general-note-29",
        ):
            bucket = counts.get(root)
            fact = roots.get(root)
            if not isinstance(bucket, Mapping) or not isinstance(fact, Mapping):
                errors.append(f"missing declared root: {root}")
            elif sum(bucket.values()) != fact.get("declared_count"):
                errors.append(f"declared root does not reconcile: {root}")
    return errors


def validate_artifact(doc: dict[str, Any]) -> ClosureSummary:
    """Validate committed derivations without requiring sibling repositories."""

    errors = validate(doc)
    if errors:
        raise ValueError("; ".join(errors))
    ledger = doc["committed_decisions"]["ledger"]
    return ClosureSummary(
        closed=doc["computed"]["closed"],
        non_encoded_reasons_complete=all(
            isinstance(row, Mapping)
            and isinstance(row.get("reason"), str)
            and bool(row["reason"])
            for row in ledger
        ),
    )


def verify_artifact(
    *,
    artifact_path: Path = ARTIFACT,
    corpus_root: Path = CORPUS,
    corpus_ref: str = CORPUS_REF,
    rulespec_root: Path = RULESPEC,
    rulespec_ref: str = RULESPEC_REF,
    engine_binary: Path = INPUT_INVENTORY_ENGINE,
) -> VerificationResult:
    """Re-derive a ledger from pinned Git objects and engine input reachability."""

    document: dict[str, Any] | None = None
    expected: dict[str, Any] | None = None
    errors: list[str] = []
    try:
        document = yaml.safe_load(artifact_path.read_text()) or {}
        validate_artifact(document)
        expected = build(
            corpus_root=corpus_root,
            corpus_ref=corpus_ref,
            rulespec_root=rulespec_root,
            rulespec_ref=rulespec_ref,
            engine_binary=engine_binary,
        )
        if document != expected:
            errors.append("closure artifact drift; run --generate")
    except (OSError, ValueError, KeyError, json.JSONDecodeError, yaml.YAMLError) as exc:
        errors.append(str(exc))
    return VerificationResult(document, expected, tuple(errors))


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--generate", action="store_true")
    mode.add_argument("--check", action="store_true")
    p.add_argument("--artifact", type=Path, default=ARTIFACT)
    p.add_argument("--corpus-root", type=Path, default=CORPUS)
    p.add_argument("--corpus-ref", default=CORPUS_REF)
    p.add_argument("--rulespec-root", type=Path, default=RULESPEC)
    p.add_argument("--rulespec-ref", default=RULESPEC_REF)
    p.add_argument("--engine-binary", type=Path, default=INPUT_INVENTORY_ENGINE)
    args = p.parse_args(argv)
    try:
        expected = build(
            corpus_root=args.corpus_root,
            corpus_ref=args.corpus_ref,
            rulespec_root=args.rulespec_root,
            rulespec_ref=args.rulespec_ref,
            engine_binary=args.engine_binary,
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"closure ledger error: {exc}", file=sys.stderr)
        return 1
    errors = validate(expected)
    text = serialize(expected)
    if args.check:
        if not args.artifact.exists() or args.artifact.read_text() != text:
            errors.append("closure artifact drift; run --generate")
    else:
        args.artifact.parent.mkdir(parents=True, exist_ok=True)
        args.artifact.write_text(text)
    if errors:
        for e in errors:
            print(f"closure ledger error: {e}", file=sys.stderr)
        return 1
    print(
        f"closure ledger up to date: closed={str(expected['computed']['closed']).lower()}, "
        f"frontier_complete={str(expected['computed']['boundary_frontier']['complete']).lower()}, "
        f"missing_inputs={expected['computed']['boundary_frontier']['missing_input_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
