#!/usr/bin/env python3
"""Audit the CA SNAP #423 disposition transition against the literal base.

This checker is deliberately read-only.  It resolves an explicit ``--base-ref``
to a commit, reads the disposition source from that commit with ``git show``,
and reconciles all 345 issue-#362 rows against the honest current report and
its source, served, and compact artifacts.  It separately replays a hash-pinned
snapshot of the rejected PUB 275 exposure so the frozen #423 partition,
22-row drift receipt, and six corrected served links remain guarded without
reintroducing the invalid population binding.

The compact case artifacts intentionally use their current ``id/r/h/m``
schema.  They are validated against every canonical mismatch row; this checker
does not require or recreate the retired ``i/o/v`` evidence payload.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SUITE = "ca-snap-ecps"

BASE_DISPOSITIONS_RELATIVE_PATH = "dispositions/ca-snap-ecps.yaml"
CURRENT_DISPOSITIONS_PATH = ROOT / BASE_DISPOSITIONS_RELATIVE_PATH
CURRENT_REPORT_PATH = (
    ROOT / "dashboard/public/data/axiom-policyengine-ca-snap-ecps.json"
)
SERVED_DISPOSITIONS_PATH = ROOT / "dashboard/public/data/dispositions/ca-snap-ecps.json"
COMPACT_DIR = ROOT / "dashboard/public/data/cases/ca-snap-ecps"

BASE_DISPOSITIONS_SHA256 = (
    "18cfbe28f951261142bfa3c52d0c88f6d0a3d53b77b597fcd807b4d2e9a23086"
)
EXPECTED_BASE_ROWS = 345
EXPECTED_CURRENT_MISMATCHES = 484
# 288 at the #423 transition; 510 after the 2026-08 residual-tail triage
# added 174 verified CA entries (see dispositions/ca-snap-ecps.yaml classes
# dated 2026-07-30/08-02 and axiom-oracles#433/#436/#437/#441); 493 after
# the 2026-08-12 income-surface fixes (qualified-dividend projection,
# situation-path income pinning) pruned 43 expired entries and 9 vanished
# selector identities whose rows now match, and added 24 fresh-evidence
# entries for the rerun's residual rows.
EXPECTED_EXPANDED_DISPOSITIONS = 484
# At the #423 transition: vanished 192 / current_but_dropped 22 /
# reclassified 0 / kept 131. The 2026-08 residual-tail triage added CA
# entries covering 21 of the 22 dropped identities, moving them to
# reclassified; 1 identity remains honestly uncovered.
# 2026-08-12 income-surface fixes: 8 kept and 2 reclassified base rows
# healed (now matching), and 4 formerly-kept rows moved to reclassified
# under fresh tanf-zero entries after their pinned values shifted.
EXPECTED_PARTITION_COUNTS = {
    "vanished": 200,
    "current_but_dropped": 0,
    "reclassified": 23,
    "kept": 122,
}
EXPECTED_PARTITION_DIGESTS = {
    "vanished": ("16faf661a75baba07b85345cabc37a1d66ed728a593bef0bb44da1143313fcef"),
    "current_but_dropped": (
        "01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b"
    ),
    "reclassified": (
        "7ea47ad2d0f54b4b5627adb3895828c13363320338ae9191d7e9556e14358a82"
    ),
    "kept": ("dbcfdc50771b4b619289a1c2a2050047510bbe3ba8929913443cb86a526adf0a"),
}
REJECTED_SNAPSHOT_COMMIT = "c1084c2339ccc4bc41776f71b059fbabe8732916"
REJECTED_SNAPSHOT_SOURCE_SHA256 = (
    "c68761bf21c80df448ecd36545175d2e7dd97ffc790abf6e36b921b6c4054a99"
)
REJECTED_SNAPSHOT_REPORT_SHA256 = (
    "d2e095a5ab737f12c50c64b82d90f87377790b646382390cc0f1ab5286c26073"
)
REJECTED_SNAPSHOT_SERVED_SHA256 = (
    "443a8fde62070325c73c4c0e96f07eb92e978c91bf32d96cd3c9384fef2ba546"
)
REJECTED_SNAPSHOT_MISMATCHES = 1058
REJECTED_SNAPSHOT_EXPANDED_DISPOSITIONS = 866
REJECTED_SNAPSHOT_PARTITION_COUNTS = {
    "vanished": 156,
    "current_but_dropped": 17,
    "reclassified": 41,
    "kept": 131,
}
REJECTED_SNAPSHOT_PARTITION_DIGESTS = {
    "vanished": ("af843e621a8b2b2a56a4f9c7236be8daa48dfae4f4274b4c1644c037433585ed"),
    "current_but_dropped": (
        "bb4c55a9f6a95881471aaa80dd99e3ced7fcbb7a7e09a0481c52983f250e49e3"
    ),
    "reclassified": (
        "23b5b69fbe4e4ca601b00c34c3bb1dc38ec0317c23a18624e36e6a50918b3e3b"
    ),
    "kept": ("2cfc51bf11031bd398cc7cd27e568f8a321df35eb9006d1acd86db112851cba3"),
}
REJECTED_SNAPSHOT_CORRECTED_LINKS = {
    "ca-mce-pe-extra-net-test-paired-eligibility": (
        "https://github.com/PolicyEngine/policyengine-us/issues/9175"
    ),
    "ca-mce-pe-extra-net-test-paired-benefit": (
        "https://github.com/PolicyEngine/policyengine-us/issues/9175"
    ),
    "ca-mce-pe-extra-net-test-eligibility-only": (
        "https://github.com/PolicyEngine/policyengine-us/issues/9175"
    ),
    "ca-mce-pe-extra-net-test-benefit-only": (
        "https://github.com/PolicyEngine/policyengine-us/issues/9175"
    ),
    "ca-mce-acin-threshold-pe-eligibility": (
        "https://github.com/PolicyEngine/policyengine-us/issues/9176"
    ),
    "ca-mce-acin-threshold-pe-benefit": (
        "https://github.com/PolicyEngine/policyengine-us/issues/9176"
    ),
}
EXPECTED_BASE_IDENTITY_DIGEST = (
    "77036d3f70198c2c0c56ffa7e608e8d752338e26152e183ef01351eb48d584f8"
)
EXPECTED_MOVEMENT_COUNTS = {"moved": 107, "unchanged": 15}
EXPECTED_MOVEMENT_DIGESTS = {
    "moved": ("a8a5cd01e09f4bac0f27bf119129f4892e9854ee848341b6c29628c15b0a1f5c"),
    "unchanged": ("0101965bd8f991552543099f2f5a9f901237ee3cd69514d0f934cf9b315863e8"),
}
# These digests and explicit pins are the compact tracked receipt derived from
# the exhaustive requested-month trace named below. The kept digest binds all
# 131 current source/report pins; the drift map makes each of the other 22
# requested-month-to-current movements reviewable.
EXPECTED_DRIFT_ROWS_SHA256 = (
    "a6690ff3f32c6907495728483ff1cd37223d0c35dca1da95df27da294b762fd4"
)
# Frozen rejected-snapshot full drift receipt (pre-2026-08-12).
SNAPSHOT_DRIFT_ROWS_SHA256 = (
    "fa54f6fdf05592da62c3c03b74264a4dfb7d9828e4f33ea169e75fc033ad3a51"
)
EXPECTED_ACTIVE_DRIFT_ROWS_SHA256 = (
    "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"
)
EXPECTED_RETIRED_DRIFT_IDENTITY_SHA256 = (
    "429e4596e94ae9fe9c193e988754bb8a0d502811394a6dc7279ffed99d63dba7"
)
EXPECTED_RETIRED_DRIFT_ROWS_SHA256 = (
    "02a37dfb01999467520c2c54a1146d8e33d62a73c30d4243ff235963f1b95d37"
)
EXPECTED_RECLASSIFIED_ROWS_SHA256 = (
    "a36ac862d96966f22dc696bac331004aba5531c1a4711e651ed0ddd6b4998c8f"
)
# Drift-receipt rows whose identity the 2026-08 residual-tail triage covered
# with a new schema-validated disposition (third receipt exit alongside
# active and retired). Their per-row drift evidence stays pinned below.
EXPECTED_RECLASSIFIED_DRIFT_IDS = frozenset(
    {
        "ca-362-medical-input-ecps-57453-benefit",
        "ca-362-period-ecps-57313-benefit",
        "ca-362-period-self-employment-tanf-ecps-57027-benefit",
        "ca-362-period-self-employment-tanf-ecps-58088-benefit",
        "ca-362-period-self-employment-tanf-ecps-60409-benefit",
        "ca-362-self-employment-ecps-59016-benefit",
        "ca-362-self-employment-ecps-59103-benefit",
        "ca-362-self-employment-ecps-59173-benefit",
        "ca-362-self-employment-ecps-60859-benefit",
        "ca-362-self-employment-tanf-ecps-56991-benefit",
        "ca-362-self-employment-tanf-ecps-57529-benefit",
        "ca-362-self-employment-tanf-ecps-57845-benefit",
        "ca-362-self-employment-tanf-ecps-57891-benefit",
        "ca-362-self-employment-tanf-ecps-60756-benefit",
        "ca-362-self-employment-tanf-ecps-60777-benefit",
        "ca-362-self-employment-tanf-ecps-60978-benefit",
        "ca-362-self-employment-tanf-ecps-61251-benefit",
        "ca-362-self-employment-tanf-ecps-61495-benefit",
        "ca-362-tanf-ecps-60816-benefit",
        "ca-362-tanf-ecps-62327-benefit",
        "ca-362-period-tanf-ecps-58946-benefit",
        "ca-362-tanf-ecps-57173-benefit",
        "ca-362-tanf-ecps-60816-benefit",
        "ca-362-tanf-ecps-61665-benefit",
    }
)
EXPECTED_RECLASSIFIED_DRIFT_ROWS_SHA256 = "e7de046f5716cd860b7ef4e5857621fc4b1c31d5e280b6b3c39cce2c7de81d25"
# The 2026-08 residual-tail triage entries that absorbed the 21 formerly
# current_but_dropped identities (per-row verified; see each entry's
# evidence in dispositions/ca-snap-ecps.yaml).
EXPECTED_RECLASSIFIED_REPLACEMENTS: dict[str, int] = {
    "ca-bbce-tail-2026-07-30-benefit": 4,
    "ca-negative-se-loss-2026-07-30-benefit": 1,
    "pe-medical-imputation-counterfactual-57453": 1,
    "tanf-zero-counterfactual-56991": 1,
    "tanf-zero-counterfactual-57027": 1,
    "tanf-zero-counterfactual-57173": 1,
    "tanf-zero-counterfactual-57529": 1,
    "tanf-zero-counterfactual-57845": 1,
    "tanf-zero-counterfactual-57891": 1,
    "tanf-zero-counterfactual-58088": 1,
    "tanf-zero-counterfactual-58946": 1,
    "tanf-zero-counterfactual-60409": 1,
    "tanf-zero-counterfactual-60756": 1,
    "tanf-zero-counterfactual-60777": 1,
    "tanf-zero-counterfactual-60816": 1,
    "tanf-zero-counterfactual-60978": 1,
    "tanf-zero-counterfactual-61251": 1,
    "tanf-zero-counterfactual-61495": 1,
    "tanf-zero-counterfactual-61665": 1,
    "tanf-zero-counterfactual-62327": 1,
}
REJECTED_SNAPSHOT_ACTIVE_DRIFT_ROWS_SHA256 = (
    "ae82ff8f1ddc915403bb318acb1f3d393454ff7fc61a913025d9575d708d84ff"
)
REJECTED_SNAPSHOT_RETIRED_DRIFT_IDENTITY_SHA256 = (
    "5ea7cdca69cc1c8dc2c9676aa3d87513ea1678de9382982b74f6a38c2c6a72d4"
)
REJECTED_SNAPSHOT_RETIRED_DRIFT_ROWS_SHA256 = (
    "2d9580a3fd58a5b05a54042758bc110c27d7279bc1e07206037c0572d3b07232"
)
REJECTED_SNAPSHOT_RECLASSIFIED_ROWS_SHA256 = (
    "e70a713f5610eb393432df046fc8386c43cde3255769f9547ce939674b46373e"
)
REJECTED_SNAPSHOT_RECLASSIFIED_REPLACEMENTS = {
    "ca-mce-pe-extra-net-test-paired-eligibility": 20,
    "ca-mce-pe-extra-net-test-paired-benefit": 20,
    "ca-mce-pe-extra-net-test-benefit-only": 1,
}
EXPECTED_KEPT_REQUESTED_MONTH_ROWS_SHA256 = (
    "00d320ba07ed43fa901c48c6d68f0869377df69caad7d7cb23d4e44cd80b9c9d"
)
# The frozen rejected-snapshot replay retains the pre-2026-08-12 kept
# receipt (131 rows) and movement split.
SNAPSHOT_KEPT_REQUESTED_MONTH_ROWS_SHA256 = (
    "06524b90f0fd49fac9e2856c73d5ee787df4190003ba7e56b0a71d47f160e0f3"
)
SNAPSHOT_MOVEMENT_COUNTS = {"moved": 115, "unchanged": 16}
SNAPSHOT_MOVEMENT_DIGESTS = {
    "moved": ("c1c10db5635f1cb76ccc0908c64e1caf958c1826f5f87bd1dce03809589a6bab"),
    "unchanged": ("4ba943d873b252ba1ea84476ee669088829b327e8d9b66f1f73468efe01df475"),
}
REQUESTED_MONTH_TRACE_SHA256 = (
    "c46af9b87c8f5ad01f1909bc45e80e00b4c4a50e5b802ea4ccbe194b5954b568"
)
REQUESTED_MONTH_DRIFT_PINS = {
    "ca-362-medical-input-ecps-57453-benefit": {
        "left": 225.0,
        "right": 298.0,
        "difference": -73.0,
    },
    "ca-362-period-ecps-57313-benefit": {
        "left": 623.0,
        "right": 623.5999755859375,
        "difference": -0.5999755859375,
    },
    "ca-362-period-self-employment-tanf-ecps-57027-benefit": {
        "left": 1571.0,
        "right": 942.5,
        "difference": 628.5,
    },
    "ca-362-period-self-employment-tanf-ecps-58088-benefit": {
        "left": 687.0,
        "right": 548.199951171875,
        "difference": 138.800048828125,
    },
    "ca-362-period-self-employment-tanf-ecps-60409-benefit": {
        "left": 1196.0,
        "right": 716.0,
        "difference": 480.0,
    },
    "ca-362-self-employment-ecps-58987-benefit": {
        "left": 179.0,
        "right": 78.99998474121094,
        "difference": 100.00001525878906,
    },
    "ca-362-self-employment-ecps-59016-benefit": {
        "left": 298.0,
        "right": 88.29998779296875,
        "difference": 209.70001220703125,
    },
    "ca-362-self-employment-ecps-59103-benefit": {
        "left": 154.0,
        "right": 23.84000015258789,
        "difference": 130.1599998474121,
    },
    "ca-362-self-employment-ecps-59173-benefit": {
        "left": 421.0,
        "right": 277.79998779296875,
        "difference": 143.20001220703125,
    },
    "ca-362-self-employment-ecps-60319-benefit": {
        "left": 298.0,
        "right": 94.29998779296875,
        "difference": 203.70001220703125,
    },
    "ca-362-self-employment-ecps-60859-benefit": {
        "left": 994.0,
        "right": 286.89996337890625,
        "difference": 707.1000366210938,
    },
    "ca-362-self-employment-tanf-ecps-56991-benefit": {
        "left": 1183.0,
        "right": 818.199951171875,
        "difference": 364.800048828125,
    },
    "ca-362-self-employment-tanf-ecps-57529-benefit": {
        "left": 994.0,
        "right": 561.699951171875,
        "difference": 432.300048828125,
    },
    "ca-362-self-employment-tanf-ecps-57845-benefit": {
        "left": 1183.0,
        "right": 688.9000244140625,
        "difference": 494.0999755859375,
    },
    "ca-362-self-employment-tanf-ecps-57891-benefit": {
        "left": 994.0,
        "right": 557.7999877929688,
        "difference": 436.20001220703125,
    },
    "ca-362-self-employment-tanf-ecps-60756-benefit": {
        "left": 603.0,
        "right": 289.3999938964844,
        "difference": 313.6000061035156,
    },
    "ca-362-self-employment-tanf-ecps-60777-benefit": {
        "left": 785.0,
        "right": 387.79998779296875,
        "difference": 397.20001220703125,
    },
    "ca-362-self-employment-tanf-ecps-60978-benefit": {
        "left": 329.0,
        "right": 113.0999755859375,
        "difference": 215.9000244140625,
    },
    "ca-362-self-employment-tanf-ecps-61251-benefit": {
        "left": 994.0,
        "right": 557.5,
        "difference": 436.5,
    },
    "ca-362-self-employment-tanf-ecps-61495-benefit": {
        "left": 785.0,
        "right": 434.8999938964844,
        "difference": 350.1000061035156,
    },
    "ca-362-tanf-ecps-60816-benefit": {
        "left": 361.0,
        "right": 283.89996337890625,
        "difference": 77.10003662109375,
    },
    "ca-362-tanf-ecps-62327-benefit": {
        "left": 239.0,
        "right": 23.84000015258789,
        "difference": 215.1599998474121,
    },
}
REJECTED_SNAPSHOT_RETIRED_CURRENT_DRIFT_PINS = {
    "ca-362-self-employment-ecps-59016-benefit": {
        "left": 0.0,
        "right": 88.29998779296875,
        "difference": -88.29998779296875,
    },
    "ca-362-self-employment-ecps-59103-benefit": {
        "left": 0.0,
        "right": 23.84000015258789,
        "difference": -23.84000015258789,
    },
    "ca-362-self-employment-ecps-59173-benefit": {
        "left": 0.0,
        "right": 277.79998779296875,
        "difference": -277.79998779296875,
    },
    "ca-362-self-employment-ecps-60319-benefit": {
        "left": 0.0,
        "right": 94.29998779296875,
        "difference": -94.29998779296875,
    },
    "ca-362-self-employment-ecps-60859-benefit": {
        "left": 0.0,
        "right": 286.89996337890625,
        "difference": -286.89996337890625,
    },
}
# 2026-08-12: four kept identities drifted when the income-surface fixes
# rebuilt the report; fresh tanf-zero entries reclassify them and their
# pre-rerun report pins are the requested-month drift evidence. Live-only —
# the rejected-snapshot replay keeps the original 22-row receipt.
LIVE_REQUESTED_MONTH_DRIFT_PINS: dict[str, Any] = {
    **REQUESTED_MONTH_DRIFT_PINS,
    "ca-362-tanf-ecps-57173-benefit": {
        "left": 994.0,
        "right": 824.2000122070312,
        "difference": 169.79998779296875,
    },
    "ca-362-period-tanf-ecps-58946-benefit": {
        "left": 550.0,
        "right": 350.0,
        "difference": 200.0,
    },
    "ca-362-tanf-ecps-60816-benefit": {
        "left": 361.0,
        "right": 0.0,
        "difference": 361.0,
    },
    "ca-362-tanf-ecps-61665-benefit": {
        "left": 785.0,
        "right": 540.2000122070312,
        "difference": 244.79998779296875,
    },
}
LIVE_RECEIPT_EXPECTATIONS: dict[str, Any] = {
    "requested_month_drift_pins": LIVE_REQUESTED_MONTH_DRIFT_PINS,
    "kept_requested_month_rows_sha256": EXPECTED_KEPT_REQUESTED_MONTH_ROWS_SHA256,
    "movement_counts": EXPECTED_MOVEMENT_COUNTS,
    "movement_digests": EXPECTED_MOVEMENT_DIGESTS,
    "drift_rows_sha256": EXPECTED_DRIFT_ROWS_SHA256,
    "reclassified_replacements": EXPECTED_RECLASSIFIED_REPLACEMENTS,
    "reclassified_rows_sha256": EXPECTED_RECLASSIFIED_ROWS_SHA256,
    # 2026-08-12 income-surface fixes healed these two drift identities
    # (both engines now agree); their last committed report pins are the
    # retirement evidence.
    "retired_current_drift_pins": {
        "ca-362-self-employment-ecps-58987-benefit": {
            "left": 78.0,
            "right": 23.84000015258789,
            "difference": 54.15999984741211,
        },
        "ca-362-self-employment-ecps-60319-benefit": {
            "left": 0.0,
            "right": 94.29998779296875,
            "difference": -94.29998779296875,
        },
    },
    "active_drift_rows_sha256": EXPECTED_ACTIVE_DRIFT_ROWS_SHA256,
    "retired_drift_identity_sha256": EXPECTED_RETIRED_DRIFT_IDENTITY_SHA256,
    "retired_drift_rows_sha256": EXPECTED_RETIRED_DRIFT_ROWS_SHA256,
    "reclassified_drift_ids": EXPECTED_RECLASSIFIED_DRIFT_IDS,
    "reclassified_drift_rows_sha256": EXPECTED_RECLASSIFIED_DRIFT_ROWS_SHA256,
}
REJECTED_SNAPSHOT_RECEIPT_EXPECTATIONS: dict[str, Any] = {
    "requested_month_drift_pins": REQUESTED_MONTH_DRIFT_PINS,
    "kept_requested_month_rows_sha256": SNAPSHOT_KEPT_REQUESTED_MONTH_ROWS_SHA256,
    "movement_counts": SNAPSHOT_MOVEMENT_COUNTS,
    "movement_digests": SNAPSHOT_MOVEMENT_DIGESTS,
    "drift_rows_sha256": SNAPSHOT_DRIFT_ROWS_SHA256,
    "reclassified_replacements": REJECTED_SNAPSHOT_RECLASSIFIED_REPLACEMENTS,
    "reclassified_rows_sha256": REJECTED_SNAPSHOT_RECLASSIFIED_ROWS_SHA256,
    "retired_current_drift_pins": REJECTED_SNAPSHOT_RETIRED_CURRENT_DRIFT_PINS,
    "active_drift_rows_sha256": REJECTED_SNAPSHOT_ACTIVE_DRIFT_ROWS_SHA256,
    "retired_drift_identity_sha256": (REJECTED_SNAPSHOT_RETIRED_DRIFT_IDENTITY_SHA256),
    "retired_drift_rows_sha256": REJECTED_SNAPSHOT_RETIRED_DRIFT_ROWS_SHA256,
    # At the frozen snapshot no drift row had been reclassified yet; the
    # empty-rows digest keeps the snapshot receipt byte-stable.
    "reclassified_drift_ids": frozenset(),
    "reclassified_drift_rows_sha256": (
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"
    ),
}

BENEFIT_CONCEPT = "us:statutes/7/2014/u#snap_benefit"
ELIGIBILITY_CONCEPT = "us:statutes/7/2014/o#snap_eligible"
EXPECTED_CONCEPTS = {BENEFIT_CONCEPT, ELIGIBILITY_CONCEPT}
EXPECTED_ENGINES = {
    "left": "axiom",
    "right": "policyengine",
    "versions": {
        "axiom_rules_engine": "0.1.0",
        "policyengine": "4.18.9",
        "policyengine_core": "3.30.3",
        "policyengine_us": "1.767.3",
    },
}
EXPECTED_ORACLE_PROVENANCE = {
    "name": "policyengine",
    "policyengine_core": "3.30.3",
    "policyengine_package": "policyengine==4.18.9",
    "policyengine_us": "1.767.3",
}
EXPECTED_RULESPECS = [
    {
        "repo": "TheAxiomFoundation/rulespec-us",
        "sha": "edc62ea566a617cf5b9c3b620f712b73c6767c94",
    }
]
MOVEMENT_THRESHOLD = 0.005

Identity = tuple[str, str, str]


class ReconciliationError(ValueError):
    """Raised when any pinned reconciliation invariant fails."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReconciliationError(message)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _path_sha256(path: Path) -> str:
    return _sha256(path.read_bytes())


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _identity(row: dict[str, Any]) -> Identity:
    try:
        values = (row["case_id"], row["concept"], row["kind"])
    except KeyError as exc:
        raise ReconciliationError(
            f"row is missing identity field {exc.args[0]!r}"
        ) from exc
    if not all(isinstance(value, str) and value for value in values):
        raise ReconciliationError(f"invalid disposition identity: {values!r}")
    return values


def _identity_record(entry: dict[str, Any]) -> dict[str, str]:
    case_id, concept, kind = _identity(entry)
    entry_id = entry.get("id")
    if not isinstance(entry_id, str) or not entry_id:
        raise ReconciliationError("disposition entry has no non-empty id")
    return {
        "id": entry_id,
        "case_id": case_id,
        "concept": concept,
        "kind": kind,
    }


def _identity_digest(entries: list[dict[str, Any]]) -> str:
    lines = [
        "\t".join(
            (
                record["id"],
                record["case_id"],
                record["concept"],
                record["kind"],
            )
        )
        for record in (_identity_record(entry) for entry in entries)
    ]
    payload = ("\n".join(sorted(lines)) + "\n").encode()
    return _sha256(payload)


def _json_rows_digest(rows: list[dict[str, Any]]) -> str:
    raw = (json.dumps(rows, sort_keys=True, separators=(",", ":")) + "\n").encode()
    return _sha256(raw)


def _pin(row: dict[str, Any]) -> dict[str, Any]:
    if "left" not in row or "right" not in row:
        raise ReconciliationError(
            f"{row.get('id') or row.get('case_id')}: pin lacks left/right"
        )
    result = {"left": row["left"], "right": row["right"]}
    difference = row.get("difference")
    if isinstance(difference, int | float) and not isinstance(difference, bool):
        result["difference"] = difference
    return result


def _pin_moved(before: dict[str, Any], after: dict[str, Any]) -> bool:
    for field in set(before) | set(after):
        old = before.get(field)
        new = after.get(field)
        if isinstance(old, bool) or isinstance(new, bool):
            if old is not new:
                return True
        elif old is None or new is None:
            if old != new:
                return True
        elif abs(float(old) - float(new)) > MOVEMENT_THRESHOLD:
            return True
    return False


def _resolve_base_ref(base_ref: str) -> str:
    if not base_ref.strip() or base_ref.startswith("-"):
        raise ReconciliationError(f"invalid base ref {base_ref!r}")
    try:
        resolved = subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "rev-parse",
                "--verify",
                "--end-of-options",
                f"{base_ref}^{{commit}}",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() if isinstance(exc.stderr, str) else ""
        raise ReconciliationError(
            f"cannot resolve base ref {base_ref!r}: {detail or exc}"
        ) from exc
    if re.fullmatch(r"[0-9a-f]{40,64}", resolved) is None:
        raise ReconciliationError(
            f"git resolved {base_ref!r} ambiguously: {resolved!r}"
        )
    return resolved


def _git_show(commit: str, relative_path: str) -> bytes:
    try:
        return subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "show",
                f"{commit}:{relative_path}",
            ],
            check=True,
            capture_output=True,
        ).stdout
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode(errors="replace").strip()
        raise ReconciliationError(
            f"cannot read {relative_path} from {commit}: {stderr or exc}"
        ) from exc


def _yaml_document(raw: bytes, label: str) -> dict[str, Any]:
    try:
        document = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ReconciliationError(f"{label} is invalid YAML: {exc}") from exc
    if not isinstance(document, dict):
        raise ReconciliationError(f"{label} root must be a mapping")
    return document


def _json_bytes_document(
    raw: bytes,
    label: str,
) -> tuple[dict[str, Any], str]:
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReconciliationError(f"{label} is invalid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ReconciliationError(f"{label} root must be an object")
    return document, _sha256(raw)


def _json_document(path: Path, label: str) -> tuple[dict[str, Any], str]:
    return _json_bytes_document(path.read_bytes(), label)


def _validate_disposition_document(
    document: dict[str, Any],
    *,
    label: str,
) -> list[dict[str, Any]]:
    _require(
        document.get("schema") == "axiom_oracles.dispositions.v1",
        f"{label} schema does not match",
    )
    _require(document.get("suite") == SUITE, f"{label} suite does not match")
    entries = document.get("entries")
    _require(isinstance(entries, list), f"{label} entries must be a list")
    assert isinstance(entries, list)
    ids: set[str] = set()
    for index, entry in enumerate(entries):
        _require(
            isinstance(entry, dict),
            f"{label} entries[{index}] must be a mapping",
        )
        assert isinstance(entry, dict)
        entry_id = entry.get("id")
        _require(
            isinstance(entry_id, str) and bool(entry_id),
            f"{label} entries[{index}] has invalid id",
        )
        assert isinstance(entry_id, str)
        _require(entry_id not in ids, f"{label} duplicates id {entry_id!r}")
        ids.add(entry_id)
        _require(
            isinstance(entry.get("concept"), str) and bool(entry["concept"]),
            f"{label} {entry_id} has invalid concept",
        )
        _require(
            isinstance(entry.get("kind"), str) and bool(entry["kind"]),
            f"{label} {entry_id} has invalid kind",
        )
        _require(
            isinstance(entry.get("disposition"), str),
            f"{label} {entry_id} has invalid disposition",
        )
    return entries


def _load_base_dispositions(
    base_ref: str,
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    commit = _resolve_base_ref(base_ref)
    raw = _git_show(commit, BASE_DISPOSITIONS_RELATIVE_PATH)
    digest = _sha256(raw)
    _require(
        digest == BASE_DISPOSITIONS_SHA256,
        "literal base dispositions sha256 mismatch: "
        f"expected {BASE_DISPOSITIONS_SHA256}, got {digest}",
    )
    document = _yaml_document(raw, "literal base dispositions")
    entries = _validate_disposition_document(
        document,
        label="literal base dispositions",
    )
    issue_entries = [
        entry for entry in entries if str(entry["id"]).startswith("ca-362-")
    ]
    _require(
        len(entries) == 349,
        f"literal base must contain 349 total entries, got {len(entries)}",
    )
    _require(
        len(issue_entries) == EXPECTED_BASE_ROWS,
        "literal base must contain "
        f"{EXPECTED_BASE_ROWS} ca-362 rows, got {len(issue_entries)}",
    )
    base_digest = _identity_digest(issue_entries)
    _require(
        base_digest == EXPECTED_BASE_IDENTITY_DIGEST,
        "literal base ca-362 identity digest mismatch: "
        f"expected {EXPECTED_BASE_IDENTITY_DIGEST}, got {base_digest}",
    )
    return commit, document, issue_entries


def _load_current_dispositions() -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    str,
]:
    raw = CURRENT_DISPOSITIONS_PATH.read_bytes()
    document = _yaml_document(raw, "current dispositions")
    entries = _validate_disposition_document(
        document,
        label="current dispositions",
    )
    return document, entries, _sha256(raw)


def _load_rejected_snapshot_dispositions() -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    str,
]:
    raw = _git_show(REJECTED_SNAPSHOT_COMMIT, BASE_DISPOSITIONS_RELATIVE_PATH)
    digest = _sha256(raw)
    _require(
        digest == REJECTED_SNAPSHOT_SOURCE_SHA256,
        "rejected PUB 275 snapshot source sha256 mismatch: "
        f"expected {REJECTED_SNAPSHOT_SOURCE_SHA256}, got {digest}",
    )
    document = _yaml_document(raw, "rejected PUB 275 snapshot dispositions")
    entries = _validate_disposition_document(
        document,
        label="rejected PUB 275 snapshot dispositions",
    )
    entries_by_id = {entry["id"]: entry for entry in entries}
    for entry_id, expected_link in REJECTED_SNAPSHOT_CORRECTED_LINKS.items():
        entry = entries_by_id.get(entry_id)
        _require(
            entry is not None,
            f"rejected PUB 275 snapshot lacks corrected row {entry_id}",
        )
        assert entry is not None
        evidence = entry.get("evidence") or {}
        _require(
            isinstance(evidence, dict),
            f"rejected PUB 275 snapshot row {entry_id} has invalid evidence",
        )
        assert isinstance(evidence, dict)
        actual_link = entry.get("linked_issue") or evidence.get("upstream_url")
        _require(
            actual_link == expected_link,
            f"rejected PUB 275 snapshot row {entry_id} does not retain "
            f"corrected issue link {expected_link}",
        )
    return document, entries, digest


def _selected_case_ids(entry: dict[str, Any]) -> list[str]:
    direct = entry.get("case_id")
    selector = entry.get("case_selector")
    if direct is not None:
        _require(
            isinstance(direct, str) and bool(direct),
            f"{entry['id']}: direct case_id must be a non-empty string",
        )
        _require(selector is None, f"{entry['id']}: mixes direct and selector cases")
        return [direct]
    _require(
        isinstance(selector, dict),
        f"{entry['id']}: has neither direct case_id nor case_selector",
    )
    case_ids = selector.get("case_ids")
    _require(
        isinstance(case_ids, list) and bool(case_ids),
        f"{entry['id']}: case_selector.case_ids must be non-empty",
    )
    assert isinstance(case_ids, list)
    _require(
        all(isinstance(case_id, str) and case_id for case_id in case_ids),
        f"{entry['id']}: selector includes an invalid case id",
    )
    _require(
        len(set(case_ids)) == len(case_ids),
        f"{entry['id']}: selector duplicates a case id",
    )
    return case_ids


def _expanded_dispositions(
    entries: list[dict[str, Any]],
    *,
    expected_rows: int = EXPECTED_EXPANDED_DISPOSITIONS,
    label: str = "current",
) -> dict[Identity, dict[str, Any]]:
    expanded: dict[Identity, dict[str, Any]] = {}
    for entry in entries:
        for case_id in _selected_case_ids(entry):
            key = (case_id, entry["concept"], entry["kind"])
            _require(
                key not in expanded,
                f"{label} dispositions cover identity {key!r} more than once",
            )
            expanded[key] = entry
    _require(
        len(expanded) == expected_rows,
        f"{label} dispositions must expand to "
        f"{expected_rows} rows, got {len(expanded)}",
    )
    return expanded


def _expected_report_note(entry: dict[str, Any]) -> dict[str, Any]:
    note = {
        "disposition": entry["disposition"],
        "id": entry["id"],
    }
    if entry.get("linked_issue"):
        note["linked_issue"] = entry["linked_issue"]
    return note


# The live report rebuilt on the 0.2.0 engine (2026-08-12 income-surface
# fixes); the frozen rejected-snapshot replay stays on the 0.1.0-era stack.
LIVE_EXPECTED_ENGINES = {
    **EXPECTED_ENGINES,
    "versions": {**EXPECTED_ENGINES["versions"], "axiom_rules_engine": "0.2.0"},
}


def _validate_report_provenance(
    report: dict[str, Any],
    expected_engines: dict[str, Any] = LIVE_EXPECTED_ENGINES,
) -> None:
    _require(
        report.get("engines") == expected_engines,
        "current CA report engine/runtime stack drifted",
    )
    provenance = report.get("provenance")
    _require(
        isinstance(provenance, dict),
        "current CA report provenance is missing",
    )
    assert isinstance(provenance, dict)
    _require(
        provenance.get("oracle") == EXPECTED_ORACLE_PROVENANCE,
        "current CA report oracle provenance drifted",
    )
    _require(
        provenance.get("rulespecs") == EXPECTED_RULESPECS,
        "current CA report RuleSpec provenance drifted",
    )


def _load_and_validate_report(
    expanded: dict[Identity, dict[str, Any]],
    *,
    raw: bytes | None = None,
    expected_mismatches: int = EXPECTED_CURRENT_MISMATCHES,
    expected_sha256: str | None = None,
    label: str = "current CA report",
    expected_engines: dict[str, Any] = LIVE_EXPECTED_ENGINES,
) -> tuple[
    dict[str, Any],
    dict[Identity, dict[str, Any]],
    dict[str, dict[str, Any]],
    str,
]:
    report, digest = (
        _json_document(CURRENT_REPORT_PATH, label)
        if raw is None
        else _json_bytes_document(raw, label)
    )
    if expected_sha256 is not None:
        _require(
            digest == expected_sha256,
            f"{label} sha256 mismatch: expected {expected_sha256}, got {digest}",
        )
    _require(
        report.get("schema_version") == "axiom.comparison_report.v2.1",
        "current CA report schema does not match",
    )
    _require(report.get("suite") == SUITE, "current CA report suite does not match")
    _validate_report_provenance(report, expected_engines)
    concepts = report.get("concepts")
    _require(isinstance(concepts, list), "current CA report concepts must be a list")
    assert isinstance(concepts, list)
    concept_ids = {
        concept.get("id") for concept in concepts if isinstance(concept, dict)
    }
    _require(
        concept_ids == EXPECTED_CONCEPTS and len(concepts) == 2,
        f"current CA report concept set drifted: {sorted(concept_ids)}",
    )

    cases = report.get("cases")
    case_count = report.get("case_count")
    _require(
        isinstance(case_count, int) and case_count > 0,
        "current CA report case_count must be positive",
    )
    _require(
        isinstance(cases, list) and len(cases) <= case_count,
        "current CA report cases must be a bounded list",
    )
    assert isinstance(cases, list)
    cases_by_id: dict[str, dict[str, Any]] = {}
    nested_by_identity: dict[Identity, dict[str, Any]] = {}
    for case in cases:
        _require(isinstance(case, dict), "current CA report has a non-object case")
        assert isinstance(case, dict)
        case_id = case.get("case_id")
        _require(
            isinstance(case_id, str) and bool(case_id),
            "current CA report case has invalid case_id",
        )
        assert isinstance(case_id, str)
        _require(
            case_id not in cases_by_id,
            f"current CA report duplicates case {case_id}",
        )
        cases_by_id[case_id] = case
        nested = case.get("mismatches") or []
        _require(
            isinstance(nested, list),
            f"current CA report case {case_id} mismatches must be a list",
        )
        for row in nested:
            _require(
                isinstance(row, dict),
                f"current CA report case {case_id} has a non-object mismatch",
            )
            assert isinstance(row, dict)
            nested_row = {"case_id": case_id, **row}
            key = _identity(nested_row)
            _require(
                key not in nested_by_identity,
                f"current CA report duplicates nested identity {key!r}",
            )
            nested_by_identity[key] = nested_row

    mismatches = report.get("mismatches")
    _require(
        isinstance(mismatches, list),
        "current CA report mismatches must be a list",
    )
    assert isinstance(mismatches, list)
    summary = report.get("summary")
    _require(isinstance(summary, dict), "current CA report summary is missing")
    assert isinstance(summary, dict)
    _require(
        len(mismatches) == expected_mismatches,
        f"{label} must contain {expected_mismatches} mismatches, got {len(mismatches)}",
    )
    _require(
        summary.get("mismatch_count") == len(mismatches),
        "current CA report mismatch_count does not match stored rows",
    )
    _require(
        summary.get("stored_mismatch_example_count") == len(mismatches),
        "current CA report mismatch list is incomplete",
    )
    _require(
        summary.get("comparison_count") == case_count * len(concepts),
        "current CA report comparison_count drifted",
    )
    _require(
        summary.get("match_count") + summary.get("mismatch_count")
        == summary.get("comparison_count"),
        "current CA report match/mismatch totals do not close",
    )

    report_by_identity: dict[Identity, dict[str, Any]] = {}
    for row in mismatches:
        _require(
            isinstance(row, dict),
            "current CA report contains a non-object top-level mismatch",
        )
        assert isinstance(row, dict)
        key = _identity(row)
        _require(
            key not in report_by_identity,
            f"current CA report duplicates identity {key!r}",
        )
        report_by_identity[key] = row
        nested = nested_by_identity.get(key)
        _require(
            nested is not None,
            f"current CA report top-level identity {key!r} lacks nested evidence",
        )
        assert nested is not None
        _require(
            _pin(nested) == _pin(row),
            f"current CA report nested pin drift for {key!r}",
        )
        disposition_entry = expanded.get(key)
        expected_note = (
            _expected_report_note(disposition_entry)
            if disposition_entry is not None
            else None
        )
        _require(
            row.get("disposition") == expected_note,
            f"current CA report disposition drift for {key!r}",
        )
    _require(
        set(nested_by_identity) == set(report_by_identity),
        "current CA report nested/top-level mismatch identities differ",
    )
    mismatch_case_ids = {case_id for case_id, _concept, _kind in report_by_identity}
    _require(
        set(cases_by_id) == mismatch_case_ids,
        "current CA report case rows are not the exact mismatch-household set",
    )
    _require(
        set(expanded) <= set(report_by_identity),
        "current dispositions include a non-mismatch identity",
    )
    return report, report_by_identity, cases_by_id, digest


def _served_entry(entry: dict[str, Any]) -> dict[str, Any]:
    evidence = entry.get("evidence") or {}
    _require(
        isinstance(evidence, dict),
        f"{entry['id']}: evidence must be a mapping",
    )
    arithmetic = [
        {"expression": item.get("expression"), "equals": item.get("equals")}
        for item in evidence.get("arithmetic") or []
        if isinstance(item, dict) and item.get("expression") is not None
    ]
    mechanism = str(evidence.get("mechanism") or "").strip() or None
    return {
        "id": entry["id"],
        "concept": entry["concept"],
        "kind": entry["kind"],
        "disposition": entry["disposition"],
        "mechanism": mechanism,
        "cases": _selected_case_ids(entry),
        "arithmetic": arithmetic,
        "linked_issue": entry.get("linked_issue") or evidence.get("upstream_url"),
    }


def _validate_served_dispositions(
    source_document: dict[str, Any],
    entries: list[dict[str, Any]],
    *,
    raw: bytes | None = None,
    expected_sha256: str | None = None,
    label: str = "served CA dispositions",
) -> str:
    served, digest = (
        _json_document(SERVED_DISPOSITIONS_PATH, label)
        if raw is None
        else _json_bytes_document(raw, label)
    )
    if expected_sha256 is not None:
        _require(
            digest == expected_sha256,
            f"{label} sha256 mismatch: expected {expected_sha256}, got {digest}",
        )
    _require(
        served.get("suite") == SUITE,
        f"{label} suite does not match",
    )
    _require(
        served.get("updated") == source_document.get("updated"),
        f"{label} updated date drifted",
    )
    expected = [_served_entry(entry) for entry in entries]
    _require(
        served.get("entries") == expected,
        f"{label} do not exactly match compacted source entries",
    )
    return digest


def _expected_compact_household(case: dict[str, Any]) -> dict[str, Any]:
    metadata = case.get("metadata") or {}
    _require(
        isinstance(metadata, dict),
        f"{case.get('case_id')}: report metadata must be an object",
    )
    summary = metadata.get("household_summary") or {}
    _require(
        isinstance(summary, dict),
        f"{case.get('case_id')}: household_summary must be an object",
    )
    ages = summary.get("ages") or []
    earned = summary.get("yearly_earned_income_per_person")
    _require(
        isinstance(ages, list),
        f"{case.get('case_id')}: household ages must be a list",
    )
    if earned is not None:
        _require(
            isinstance(earned, list),
            f"{case.get('case_id')}: household earned income must be a list",
        )
    return {
        "n": summary.get("household_size") or len(ages) or None,
        "e": round(sum(earned)) if earned else None,
        "a": ages,
    }


def _validate_compact_household_shape(
    household: Any,
    *,
    case_id: str,
) -> None:
    _require(
        isinstance(household, dict) and set(household) == {"n", "e", "a"},
        f"CA compact household summary shape drift for {case_id}",
    )
    assert isinstance(household, dict)
    _require(
        household["n"] is None
        or (
            isinstance(household["n"], int)
            and not isinstance(household["n"], bool)
            and household["n"] > 0
        ),
        f"CA compact household size is invalid for {case_id}",
    )
    _require(
        household["e"] is None
        or (
            isinstance(household["e"], int | float)
            and not isinstance(household["e"], bool)
        ),
        f"CA compact earned income is invalid for {case_id}",
    )
    _require(
        isinstance(household["a"], list)
        and all(
            isinstance(age, int | float) and not isinstance(age, bool)
            for age in household["a"]
        ),
        f"CA compact ages are invalid for {case_id}",
    )


def _expected_compact_mismatches(
    case: dict[str, Any],
    report_by_identity: dict[Identity, dict[str, Any]],
) -> list[dict[str, Any]]:
    case_id = case["case_id"]
    expected: list[dict[str, Any]] = []
    for nested in case.get("mismatches") or []:
        key = (case_id, nested["concept"], nested["kind"])
        canonical = report_by_identity[key]
        row = {
            "c": nested["concept"],
            "l": nested["left"],
            "x": nested["right"],
            "d": nested.get("difference"),
        }
        disposition = canonical.get("disposition")
        if disposition is not None:
            row["e"] = disposition["disposition"]
        expected.append(row)
    return expected


def _load_compact_rows(
    report: dict[str, Any],
    report_by_identity: dict[Identity, dict[str, Any]],
    cases_by_id: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    index_path = COMPACT_DIR / "index.json"
    index, index_digest = _json_document(index_path, "CA compact index")
    declared_chunks = index.get("chunks")
    _require(
        isinstance(declared_chunks, int) and declared_chunks > 0,
        "CA compact index chunks must be a positive integer",
    )
    chunk_size = index.get("chunk_size")
    _require(
        isinstance(chunk_size, int) and chunk_size > 0,
        "CA compact index chunk_size must be positive",
    )
    expected_names = {f"chunk-{number}.json" for number in range(declared_chunks)}
    actual_paths = list(COMPACT_DIR.glob("chunk-*.json"))
    actual_names = {path.name for path in actual_paths}
    _require(
        actual_names == expected_names,
        "CA compact chunk set drifted: "
        f"missing={sorted(expected_names - actual_names)}, "
        f"extra={sorted(actual_names - expected_names)}",
    )

    rows: list[dict[str, Any]] = []
    chunk_receipts: list[dict[str, Any]] = []
    for number in range(declared_chunks):
        path = COMPACT_DIR / f"chunk-{number}.json"
        raw = path.read_bytes()
        try:
            chunk = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ReconciliationError(
                f"CA compact {path.name} is invalid JSON: {exc}"
            ) from exc
        _require(
            isinstance(chunk, list),
            f"CA compact {path.name} must be an array",
        )
        assert isinstance(chunk, list)
        _require(
            len(chunk) <= chunk_size,
            f"CA compact {path.name} exceeds chunk_size",
        )
        rows.extend(chunk)
        chunk_receipts.append({"path": _relative(path), "sha256": _sha256(raw)})

    _validate_compact_rows(
        report,
        report_by_identity,
        cases_by_id,
        index,
        rows,
    )
    receipt = {
        "index": {
            "path": _relative(index_path),
            "sha256": index_digest,
        },
        "chunks": chunk_receipts,
        "cases": len(rows),
        "mismatches": len(report_by_identity),
        "annotated": sum(
            row.get("disposition") is not None for row in report_by_identity.values()
        ),
    }
    return index, rows, receipt


def _validate_compact_rows(
    report: dict[str, Any],
    report_by_identity: dict[Identity, dict[str, Any]],
    cases_by_id: dict[str, dict[str, Any]],
    index: dict[str, Any],
    rows: list[dict[str, Any]],
) -> None:
    _require(index.get("suite") == SUITE, "CA compact index suite drifted")
    _require(
        index.get("engines") == report.get("engines"),
        "CA compact index engines drifted",
    )
    _require(
        index.get("count") == len(rows) == report.get("case_count"),
        "CA compact case count does not match the canonical report",
    )
    _require(
        index.get("total_cases") == report.get("case_count"),
        "CA compact total_cases drifted",
    )
    _require(
        index.get("partial") is None,
        "CA compact artifacts unexpectedly use mismatch-only mode",
    )
    _require(
        "input_slots" not in index and "output_slots" not in index,
        "CA compact index is not the current id/r/h/m schema",
    )
    expected_concepts = sorted({row["concept"] for row in report_by_identity.values()})
    _require(
        index.get("mismatch_concepts") == expected_concepts,
        "CA compact mismatch_concepts drifted",
    )

    compact_by_id: dict[str, dict[str, Any]] = {}
    compact_mismatches: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        _require(isinstance(row, dict), "CA compact contains a non-object case")
        assert isinstance(row, dict)
        _require(
            set(row) == {"id", "r", "h", "m"},
            f"CA compact case {row.get('id')} is not exact id/r/h/m schema",
        )
        case_id = row.get("id")
        _require(
            isinstance(case_id, str) and bool(case_id),
            f"CA compact has invalid case id {case_id!r}",
        )
        assert isinstance(case_id, str)
        _require(
            case_id not in compact_by_id,
            f"CA compact duplicates case {case_id}",
        )
        compact_by_id[case_id] = row
        _validate_compact_household_shape(row["h"], case_id=case_id)
        canonical_case = cases_by_id.get(case_id)
        if canonical_case is None:
            _require(
                row["r"] == 100.0 and row["m"] == [],
                f"CA compact clean-case payload drift for {case_id}",
            )
        else:
            _require(
                row["r"] == canonical_case.get("match_rate"),
                f"CA compact match rate drift for {case_id}",
            )
            _require(
                row["h"] == _expected_compact_household(canonical_case),
                f"CA compact household summary drift for {case_id}",
            )
            expected_rows = _expected_compact_mismatches(
                canonical_case,
                report_by_identity,
            )
            _require(
                row["m"] == expected_rows,
                f"CA compact mismatch payload drift for {case_id}",
            )
        for mismatch in row["m"]:
            key = (case_id, mismatch["c"])
            _require(
                key not in compact_mismatches,
                f"CA compact duplicates mismatch {key!r}",
            )
            compact_mismatches[key] = mismatch

    _require(
        set(cases_by_id) <= set(compact_by_id),
        "CA compact artifacts omit a canonical mismatch household",
    )
    canonical_case_concepts = {
        (case_id, concept) for case_id, concept, _kind in report_by_identity
    }
    _require(
        set(compact_mismatches) == canonical_case_concepts,
        "CA compact mismatch identity set differs from canonical report",
    )


def _partition_base_entries(
    base_entries: list[dict[str, Any]],
    report_by_identity: dict[Identity, dict[str, Any]],
    current_issue_by_id: dict[str, dict[str, Any]],
    expanded: dict[Identity, dict[str, Any]],
    *,
    expected_counts: dict[str, int] = EXPECTED_PARTITION_COUNTS,
    expected_digests: dict[str, str] = EXPECTED_PARTITION_DIGESTS,
    era_label: str = "current honest",
) -> dict[str, list[dict[str, Any]]]:
    partitions: dict[str, list[dict[str, Any]]] = {
        "vanished": [],
        "current_but_dropped": [],
        "reclassified": [],
        "kept": [],
    }
    for entry in base_entries:
        entry_id = entry["id"]
        key = _identity(entry)
        current_entry = current_issue_by_id.get(entry_id)
        if current_entry is not None:
            _require(
                _identity(current_entry) == key,
                f"current entry {entry_id} changed identity",
            )
            _require(
                key in report_by_identity,
                f"current entry {entry_id} is not a current mismatch",
            )
            partitions["kept"].append(entry)
        elif key not in report_by_identity:
            partitions["vanished"].append(entry)
        elif key in expanded:
            partitions["reclassified"].append(entry)
        else:
            partitions["current_but_dropped"].append(entry)

    total = sum(len(entries) for entries in partitions.values())
    _require(
        total == EXPECTED_BASE_ROWS,
        f"partition closes to {total}, expected {EXPECTED_BASE_ROWS}",
    )
    for partition_label, entries in partitions.items():
        expected_count = expected_counts[partition_label]
        _require(
            len(entries) == expected_count,
            f"{era_label} {partition_label} count is {len(entries)}, "
            f"expected {expected_count}",
        )
        digest = _identity_digest(entries)
        expected_digest = expected_digests[partition_label]
        _require(
            digest == expected_digest,
            f"{era_label} {partition_label} identity digest mismatch: "
            f"expected {expected_digest}, got {digest}",
        )
    return partitions


def _partition_receipt(
    partitions: dict[str, list[dict[str, Any]]],
    report_by_identity: dict[Identity, dict[str, Any]],
    current_issue_by_id: dict[str, dict[str, Any]],
    expanded: dict[Identity, dict[str, Any]],
    *,
    expectations: dict[str, Any] = LIVE_RECEIPT_EXPECTATIONS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    expected_reclassified_replacements = expectations["reclassified_replacements"]
    expected_reclassified_rows_sha256 = expectations["reclassified_rows_sha256"]
    retired_current_drift_pins = expectations["retired_current_drift_pins"]
    expected_active_drift_rows_sha256 = expectations["active_drift_rows_sha256"]
    expected_retired_drift_identity_sha256 = expectations[
        "retired_drift_identity_sha256"
    ]
    expected_retired_drift_rows_sha256 = expectations["retired_drift_rows_sha256"]
    movement: dict[str, list[dict[str, Any]]] = {
        "moved": [],
        "unchanged": [],
    }
    kept_requested_month_rows = []
    for entry in partitions["kept"]:
        entry_id = entry["id"]
        key = _identity(entry)
        current_row = report_by_identity[key]
        current_entry = current_issue_by_id[entry_id]
        current_pin = _pin(current_row)
        for field in (
            "disposition",
            "linked_issue",
            "expires_on_source_change",
        ):
            _require(
                current_entry.get(field) == entry.get(field),
                f"kept entry {entry_id} changed stable {field}",
            )
        _require(
            current_entry.get("pinned") == current_pin,
            f"kept entry {entry_id} pin differs from current report",
        )
        _require(
            expanded.get(key) == current_entry,
            f"kept entry {entry_id} is not the expanded source annotation",
        )
        label = (
            "moved"
            if _pin_moved(entry.get("pinned") or {}, current_pin)
            else "unchanged"
        )
        movement[label].append(entry)
        kept_requested_month_rows.append(
            {
                **_identity_record(entry),
                "requested_month_pin": current_pin,
            }
        )

    kept_requested_month_rows.sort(key=lambda row: row["id"])
    kept_requested_month_digest = _json_rows_digest(kept_requested_month_rows)
    expected_kept_digest = expectations["kept_requested_month_rows_sha256"]
    _require(
        kept_requested_month_digest == expected_kept_digest,
        "kept requested-month receipt digest mismatch: "
        f"expected {expected_kept_digest}, "
        f"got {kept_requested_month_digest}",
    )

    for label, entries in movement.items():
        _require(
            len(entries) == expectations["movement_counts"][label],
            f"{label} retained count is {len(entries)}, "
            f"expected {expectations['movement_counts'][label]}",
        )
        digest = _identity_digest(entries)
        expected = expectations["movement_digests"][label]
        _require(
            digest == expected,
            f"{label} retained identity digest mismatch: "
            f"expected {expected}, got {digest}",
        )

    for label in ("vanished", "current_but_dropped"):
        for entry in partitions[label]:
            key = _identity(entry)
            _require(
                key not in expanded,
                f"{label} entry {entry['id']} remains disposition-covered",
            )

    reclassified_rows = []
    replacement_counts: dict[str, int] = {}
    for entry in partitions["reclassified"]:
        key = _identity(entry)
        replacement = expanded.get(key)
        _require(
            replacement is not None,
            f"reclassified entry {entry['id']} lacks replacement coverage",
        )
        assert replacement is not None
        replacement_id = replacement["id"]
        replacement_counts[replacement_id] = (
            replacement_counts.get(replacement_id, 0) + 1
        )
        reclassified_rows.append(
            {
                **_identity_record(entry),
                "current_pin": _pin(report_by_identity[key]),
                "replacement_disposition_id": replacement_id,
            }
        )
    _require(
        replacement_counts == expected_reclassified_replacements,
        "reclassified replacement selector counts drifted: "
        f"expected {expected_reclassified_replacements}, "
        f"got {replacement_counts}",
    )
    reclassified_rows.sort(key=lambda row: row["id"])
    reclassified_rows_digest = _json_rows_digest(reclassified_rows)
    _require(
        reclassified_rows_digest == expected_reclassified_rows_sha256,
        "reclassified replacement receipt digest mismatch: "
        f"expected {expected_reclassified_rows_sha256}, "
        f"got {reclassified_rows_digest}",
    )

    partition_output: dict[str, Any] = {"base_rows": EXPECTED_BASE_ROWS}
    for label, entries in partitions.items():
        partition_output[label] = {
            "count": len(entries),
            "identity_sha256": _identity_digest(entries),
            "ids": sorted(entry["id"] for entry in entries),
        }

    drifted_rows = []
    active_drifted_rows = []
    retired_drifted_rows = []
    reclassified_drifted_rows = []
    dropped_by_id = {entry["id"]: entry for entry in partitions["current_but_dropped"]}
    vanished_by_id = {entry["id"]: entry for entry in partitions["vanished"]}
    reclassified_by_id = {entry["id"]: entry for entry in partitions["reclassified"]}
    dropped_ids = set(dropped_by_id)
    retired_ids = set(retired_current_drift_pins)
    # A drift row leaves the active receipt one of two ways: its identity
    # vanishes from the report (retired), or a later triage covers the
    # identity with a new schema-validated disposition (reclassified —
    # the 2026-08 residual-tail entries). Both exits stay receipted.
    reclassified_drift_ids = set(expectations["reclassified_drift_ids"])
    _require(
        dropped_ids | retired_ids | reclassified_drift_ids
        == set(expectations["requested_month_drift_pins"])
        and dropped_ids.isdisjoint(retired_ids)
        and dropped_ids.isdisjoint(reclassified_drift_ids)
        and retired_ids.isdisjoint(reclassified_drift_ids),
        "requested-month drift receipt ids differ from the active and retired "
        "drift partitions",
    )
    _require(
        reclassified_drift_ids <= set(reclassified_by_id),
        "reclassified drift receipt ids are not all in the reclassified "
        "partition",
    )
    _require(
        retired_ids <= set(vanished_by_id),
        "retired drift receipt ids are not all in the vanished partition",
    )
    retired_entries = [vanished_by_id[entry_id] for entry_id in sorted(retired_ids)]
    retired_identity_digest = _identity_digest(retired_entries)
    _require(
        retired_identity_digest == expected_retired_drift_identity_sha256,
        "retired drift identity digest mismatch: "
        f"expected {expected_retired_drift_identity_sha256}, "
        f"got {retired_identity_digest}",
    )
    requested_month_drift_pins = expectations["requested_month_drift_pins"]
    for entry_id in sorted(requested_month_drift_pins):
        retired = entry_id in retired_ids
        reclassified = entry_id in reclassified_drift_ids
        if retired:
            entry = vanished_by_id[entry_id]
        elif reclassified:
            entry = reclassified_by_id[entry_id]
        else:
            entry = dropped_by_id[entry_id]
        key = _identity(entry)
        literal_base_pin = _pin(entry.get("pinned") or {})
        requested_month_pin = requested_month_drift_pins[entry_id]
        current_pin = (
            retired_current_drift_pins[entry_id]
            if retired
            else _pin(report_by_identity[key])
        )
        _require(
            _pin_moved(requested_month_pin, current_pin),
            f"drift entry {entry_id} did not materially drift from "
            "requested-month evidence",
        )
        evidence = {
            **_identity_record(entry),
            "literal_base_pin": literal_base_pin,
            "requested_month_pin": requested_month_pin,
        }
        drifted_rows.append({**evidence, "current_pin": current_pin})
        if retired:
            retired_drifted_rows.append(evidence)
        elif reclassified:
            reclassified_drifted_rows.append({**evidence, "current_pin": current_pin})
        else:
            active_drifted_rows.append({**evidence, "current_pin": current_pin})
    drift_rows_digest = _json_rows_digest(drifted_rows)
    _require(
        drift_rows_digest == expectations["drift_rows_sha256"],
        "full drift-row receipt digest mismatch: "
        f"expected {expectations['drift_rows_sha256']}, got {drift_rows_digest}",
    )
    active_drift_rows_digest = _json_rows_digest(active_drifted_rows)
    _require(
        active_drift_rows_digest == expected_active_drift_rows_sha256,
        "active drift-row receipt digest mismatch: "
        f"expected {expected_active_drift_rows_sha256}, "
        f"got {active_drift_rows_digest}",
    )
    retired_drift_rows_digest = _json_rows_digest(retired_drifted_rows)
    _require(
        retired_drift_rows_digest == expected_retired_drift_rows_sha256,
        "retired drift-row receipt digest mismatch: "
        f"expected {expected_retired_drift_rows_sha256}, "
        f"got {retired_drift_rows_digest}",
    )
    expected_reclassified_drift_rows_sha256 = expectations[
        "reclassified_drift_rows_sha256"
    ]
    reclassified_drift_rows_digest = _json_rows_digest(reclassified_drifted_rows)
    _require(
        reclassified_drift_rows_digest == expected_reclassified_drift_rows_sha256,
        "reclassified drift-row receipt digest mismatch: "
        f"expected {expected_reclassified_drift_rows_sha256}, "
        f"got {reclassified_drift_rows_digest}",
    )

    movement_output: dict[str, Any] = {}
    for label, entries in movement.items():
        movement_output[label] = {
            "count": len(entries),
            "identity_sha256": _identity_digest(entries),
            "ids": sorted(entry["id"] for entry in entries),
        }
    movement_output["requested_month_evidence"] = {
        "count": len(kept_requested_month_rows),
        "trace_sha256": REQUESTED_MONTH_TRACE_SHA256,
        "rows_sha256": kept_requested_month_digest,
    }
    return (
        {
            **partition_output,
            "reclassified_replacements": {
                "counts": replacement_counts,
                "rows_sha256": reclassified_rows_digest,
                "rows": reclassified_rows,
            },
            "drift_evidence_trace_sha256": REQUESTED_MONTH_TRACE_SHA256,
            "drifted_rows_sha256": drift_rows_digest,
            "drifted_rows": drifted_rows,
            "active_drifted_rows_sha256": active_drift_rows_digest,
            "retired_drifted_rows_sha256": retired_drift_rows_digest,
        },
        movement_output,
    )


def _validate_partition_compact_evidence(
    partitions: dict[str, list[dict[str, Any]]],
    compact_rows: list[dict[str, Any]],
) -> None:
    compact_by_id = {row["id"]: row for row in compact_rows}
    for label, entries in partitions.items():
        for entry in entries:
            case_id = entry["case_id"]
            compact = compact_by_id.get(case_id)
            _require(
                compact is not None,
                f"{label} base entry {entry['id']} is absent from compact cases",
            )
            assert compact is not None
            concept_rows = [row for row in compact["m"] if row["c"] == entry["concept"]]
            expected_count = 0 if label == "vanished" else 1
            _require(
                len(concept_rows) == expected_count,
                f"{label} base entry {entry['id']} has "
                f"{len(concept_rows)} compact rows for its concept; "
                f"expected {expected_count}",
            )


def check_reconciliation(base_ref: str) -> dict[str, Any]:
    """Validate the complete reconciliation and return a deterministic receipt."""

    base_commit, _base_document, base_entries = _load_base_dispositions(base_ref)
    snapshot_commit = _resolve_base_ref(REJECTED_SNAPSHOT_COMMIT)
    _require(
        snapshot_commit == REJECTED_SNAPSHOT_COMMIT,
        "rejected PUB 275 snapshot commit did not resolve exactly",
    )

    (
        current_document,
        current_entries,
        current_dispositions_digest,
    ) = _load_current_dispositions()
    expanded = _expanded_dispositions(current_entries)
    (
        report,
        report_by_identity,
        cases_by_id,
        report_digest,
    ) = _load_and_validate_report(expanded)
    served_digest = _validate_served_dispositions(
        current_document,
        current_entries,
    )
    _index, compact_rows, compact_receipt = _load_compact_rows(
        report,
        report_by_identity,
        cases_by_id,
    )

    current_issue_entries = [
        entry for entry in current_entries if str(entry["id"]).startswith("ca-362-")
    ]
    current_issue_by_id = {entry["id"]: entry for entry in current_issue_entries}
    _require(
        len(current_issue_by_id) == EXPECTED_PARTITION_COUNTS["kept"],
        "current source must contain exactly "
        f"{EXPECTED_PARTITION_COUNTS['kept']} ca-362 entries",
    )
    base_ids = {entry["id"] for entry in base_entries}
    _require(
        set(current_issue_by_id) <= base_ids,
        "current source contains a ca-362 id outside the literal base",
    )

    partitions = _partition_base_entries(
        base_entries,
        report_by_identity,
        current_issue_by_id,
        expanded,
    )
    _validate_partition_compact_evidence(partitions, compact_rows)
    partition_receipt, movement_receipt = _partition_receipt(
        partitions,
        report_by_identity,
        current_issue_by_id,
        expanded,
    )

    (
        snapshot_document,
        snapshot_entries,
        snapshot_dispositions_digest,
    ) = _load_rejected_snapshot_dispositions()
    snapshot_expanded = _expanded_dispositions(
        snapshot_entries,
        expected_rows=REJECTED_SNAPSHOT_EXPANDED_DISPOSITIONS,
        label="rejected PUB 275 snapshot",
    )
    snapshot_report_raw = _git_show(
        snapshot_commit,
        _relative(CURRENT_REPORT_PATH),
    )
    (
        _snapshot_report,
        snapshot_report_by_identity,
        _snapshot_cases_by_id,
        snapshot_report_digest,
    ) = _load_and_validate_report(
        snapshot_expanded,
        raw=snapshot_report_raw,
        expected_mismatches=REJECTED_SNAPSHOT_MISMATCHES,
        expected_sha256=REJECTED_SNAPSHOT_REPORT_SHA256,
        label="rejected PUB 275 snapshot CA report",
        expected_engines=EXPECTED_ENGINES,
    )
    snapshot_served_raw = _git_show(
        snapshot_commit,
        _relative(SERVED_DISPOSITIONS_PATH),
    )
    snapshot_served_digest = _validate_served_dispositions(
        snapshot_document,
        snapshot_entries,
        raw=snapshot_served_raw,
        expected_sha256=REJECTED_SNAPSHOT_SERVED_SHA256,
        label="rejected PUB 275 snapshot served CA dispositions",
    )

    snapshot_issue_entries = [
        entry for entry in snapshot_entries if str(entry["id"]).startswith("ca-362-")
    ]
    snapshot_issue_by_id = {entry["id"]: entry for entry in snapshot_issue_entries}
    _require(
        len(snapshot_issue_by_id) == REJECTED_SNAPSHOT_PARTITION_COUNTS["kept"],
        "rejected PUB 275 snapshot source must contain exactly "
        f"{REJECTED_SNAPSHOT_PARTITION_COUNTS['kept']} ca-362 entries",
    )
    _require(
        set(snapshot_issue_by_id) <= base_ids,
        "rejected PUB 275 snapshot contains a ca-362 id outside the literal base",
    )
    snapshot_partitions = _partition_base_entries(
        base_entries,
        snapshot_report_by_identity,
        snapshot_issue_by_id,
        snapshot_expanded,
        expected_counts=REJECTED_SNAPSHOT_PARTITION_COUNTS,
        expected_digests=REJECTED_SNAPSHOT_PARTITION_DIGESTS,
        era_label="rejected PUB 275 snapshot",
    )
    (
        snapshot_partition_receipt,
        snapshot_movement_receipt,
    ) = _partition_receipt(
        snapshot_partitions,
        snapshot_report_by_identity,
        snapshot_issue_by_id,
        snapshot_expanded,
        expectations=REJECTED_SNAPSHOT_RECEIPT_EXPECTATIONS,
    )

    return {
        "schema": "axiom_oracles.ca_snap_423_reconciliation.v2",
        "suite": SUITE,
        "base": {
            "commit": base_commit,
            "path": BASE_DISPOSITIONS_RELATIVE_PATH,
            "sha256": BASE_DISPOSITIONS_SHA256,
            "identity_sha256": EXPECTED_BASE_IDENTITY_DIGEST,
        },
        "current": {
            "report": {
                "path": _relative(CURRENT_REPORT_PATH),
                "sha256": report_digest,
                "mismatches": len(report_by_identity),
            },
            "source_dispositions": {
                "path": _relative(CURRENT_DISPOSITIONS_PATH),
                "sha256": current_dispositions_digest,
                "entries": len(current_entries),
                "expanded_rows": len(expanded),
            },
            "served_dispositions": {
                "path": _relative(SERVED_DISPOSITIONS_PATH),
                "sha256": served_digest,
                "entries": len(current_entries),
            },
            "compact": compact_receipt,
            "partition": partition_receipt,
            "retained_pin_movement": movement_receipt,
        },
        "rejected_pub275_exposure_snapshot": {
            "commit": snapshot_commit,
            "reason": (
                "The snapshot manufactured household PUB 275 issuance by "
                "binding an unobserved administrative fact to true."
            ),
            "report": {
                "path": _relative(CURRENT_REPORT_PATH),
                "sha256": snapshot_report_digest,
                "mismatches": len(snapshot_report_by_identity),
            },
            "source_dispositions": {
                "path": _relative(CURRENT_DISPOSITIONS_PATH),
                "sha256": snapshot_dispositions_digest,
                "entries": len(snapshot_entries),
                "expanded_rows": len(snapshot_expanded),
            },
            "served_dispositions": {
                "path": _relative(SERVED_DISPOSITIONS_PATH),
                "sha256": snapshot_served_digest,
                "entries": len(snapshot_entries),
                "corrected_issue_links": REJECTED_SNAPSHOT_CORRECTED_LINKS,
            },
            "partition": snapshot_partition_receipt,
            "retained_pin_movement": snapshot_movement_receipt,
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-ref",
        required=True,
        help=(
            "Git ref containing the literal merged #423 disposition source. "
            "The ref is resolved to a commit before git-showing the pinned blob."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Audit committed artifacts without writing. The checker is always "
            "read-only; this flag makes the intended gate invocation explicit."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        receipt = check_reconciliation(args.base_ref)
    except (OSError, ReconciliationError) as exc:
        print(f"CA SNAP #423 reconciliation FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
