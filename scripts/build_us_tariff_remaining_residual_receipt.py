#!/usr/bin/env python3
"""Reproduce two bounded residual causes without consuming their classification.

The base proof executes the pinned Yale R parser on complete original archives
and on a controlled, eleven-General-field markup-only variant. The aluminum
proof executes the actual pinned Axiom engine with only two incidence inputs
changed. Neither counterfactual determines legal scope or establishes closure.

Normal validation reads only this compact, losslessly encoded proof and small
committed inputs. Independent frozen-population anchors reject rehashed invented
records, feeds, source facts, or replay results. Every production ``--check``
additionally scans the complete frozen evaluation population and executes R and
Axiom again. The ledger, classification, report, and certificate are never read.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
import csv
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
from contextlib import contextmanager
from typing import Any, Callable, Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import build_us_tariff_cafta_supersession_receipt as cafta  # noqa: E402
from scripts import build_us_tariff_section232_equivalence_receipt as foundation  # noqa: E402
from scripts import us_tariff_schedule_campaign as campaign  # noqa: E402


SCHEMA = "axiom_oracles.us_tariff_schedule.remaining_residuals.v1"
PRODUCER_PATH = "scripts/build_us_tariff_remaining_residual_receipt.py"
DEFAULT_OUTPUT = (
    REPO_ROOT / "reference/us-tariff-schedule/remaining-residual-receipt.json"
)
DEFAULT_RULESPEC_ROOT = Path(
    "/Users/maxghenis/TheAxiomFoundation/_worktrees/"
    "tariff-policy-combined-20260829/rulespec-us"
)
DEFAULT_YALE_ROOT = Path("/Users/maxghenis/TheAxiomFoundation/_tariff-yale")
DEFAULT_ENGINE = Path(
    "/Users/maxghenis/TheAxiomFoundation/axiom-rules-engine-pinned/"
    "target/release/axiom-rules-engine"
)
EXPECTED_RULESPEC_COMMIT = "4f591c4267063094cc6da9d590872ea982940b81"
EXPECTED_YALE_COMMIT = "c4307e514196618afcbf88cf7fd33746417eeabf"
EXPECTED_YALE_TREE = "d3107eae32ae7ac366b319abd4ab7b13c78d5c3c"
EXPECTED_ENGINE_SHA256 = (
    "674ca6e70afdccb59c3d6847933bc24b4590105e49db54790f2dcd0bdbbe32d7"
)
EXPECTED_RUN_IDENTITY_SHA256 = (
    "0d5b10e153cf38dc14a1a181c41d393e6bba05fe32ef2a8fe48015624be67f40"
)
EXPECTED_GENERATION_ID = "3b25bc33665d4eed90a21409872a54bb"
EXPECTED_ARTIFACT_SHA256 = {
    "76": "b95c0c8b6df705fdcf60f78c97c80c387caac9a2333d87776c1d520b319b209a",
    "87": "93cf24f36c061c33f383f48580f38d0be35a377bf1a35cd5c4124dd5a0820f11",
}
# Independently established by a second agent's exact frozen-shard join and our
# preceding actual R/Axiom diagnostic, not accepted from this artifact's claims.
EXPECTED_RECORD_POPULATION_SHA256 = (
    "79a2082a2683be03b855be218ae3f63475ac1e8465b79037f03e10890e7bd0fa"
)
EXPECTED_CASE_POPULATION_SHA256 = (
    "b026489e09f6362ea90c24e16b43d3fefe5e98066f29522da0240a3f24089193"
)
EXPECTED_R_RESULT_SHA256 = (
    "08e2b3dbfa81434eddc4a6ff4a45c40fee00efafcb5ae40116fa33e816e164e0"
)
EXPECTED_SOURCE_RECORD_POPULATION_SHA256 = (
    "4bfe9690fbbf2d8dd02f399b506407382f3d56fab45e393b26e2785d717d02d6"
)
EXPECTED_FOUNDATION_SHA256 = (
    "34e92d18ef1dcba5a2ace50b6d2dd2bee348530e7b9ad628a3aaed3bcf353441"
)
EXPECTED_RUNTIME_HELPER_SHA256 = (
    "705d7694b91008aae843d22e4732fcc1ae5166d4fb5860712e7da375644bff90"
)
SMALL_INPUTS = {
    "evaluation_manifest": (
        "reference/us-tariff-schedule/eval/MANIFEST.json",
        "f11f8a72108bfdaa0aafb332b2fc47eb410dcf1970931dfbbf2e32d4a8f5ad1a",
    ),
    "comparison_receipt": (
        "reference/us-tariff-schedule/comparison-summary.json",
        "936e0653c8fc6e950c46951ddc7865d9a7943c2559165b7ab41364521d4cfcc7",
    ),
    "input_contract": (
        "reference/us-tariff-schedule/declared-input-contract-receipt.json",
        "e9db8760690ecd8a273e8e8e94095104a80e146fbe438ba41b14ab97b4abfd7a",
    ),
}
GENERAL = {
    "8708220000": ("8708220000", 0.025),
    "8708291500": ("8708291500", 0.025),
    "8708292500": ("8708292500", 0.025),
    "8708305020": ("87083050", 0.025),
    "8708305030": ("87083050", 0.025),
    "8708305040": ("87083050", 0.025),
    "8708305090": ("87083050", 0.025),
    "8708401110": ("87084011", 0.025),
    "8708401150": ("87084011", 0.025),
    "8708806510": ("87088065", 0.025),
    "8708806590": ("87088065", 0.025),
    "8708947510": ("87089475", 0.025),
    "8708947550": ("87089475", 0.025),
    "8712005000": ("8712005000", 0.037),
    "8714915000": ("8714915000", 0.06),
    "8714921000": ("8714921000", 0.05),
    "8714949000": ("8714949000", 0.1),
}
ALUMINUM_CODES = ("7616995120", "7616995150", "7616995175")
CHANGED_INPUTS = ("entry_is_section_232_aluminum", "entry_is_section_232_covered")
BASE_INTERVALS = {
    "2026_rev_9": ("2026-05-01", "2026-06-07", "2026_rev_9"),
    "2026_rev_11": ("2026-07-01", "2026-07-20", "2026_rev_11"),
    "2026_rev_12": ("2026-07-21", "2026-07-21", "2026_rev_12"),
    "bnd_2026-07-22": ("2026-07-22", "2026-07-23", "2026_rev_12"),
    "bnd_2026-07-24": ("2026-07-24", "2026-07-30", "2026_rev_12"),
    "bnd_2026-07-31": ("2026-07-31", "2026-08-01", "2026_rev_12"),
}
ALUMINUM_INTERVALS = {
    "2026_rev_3": ("2026-02-15", "2026-02-19", "2026_rev_3"),
    "bnd_2026-02-20": ("2026-02-20", "2026-02-23", "2026_rev_3"),
    "2026_rev_4": ("2026-02-24", "2026-03-31", "2026_rev_4"),
    "bnd_2026-04-01": ("2026-04-01", "2026-04-05", "2026_rev_4"),
}
ARCHIVE_ANCHORS = {
    "2026_rev_3": (
        718254,
        "e878e7bf8f2e85639029d01e117bfb40948a3cdfa33b460083c44ac455573688",
    ),
    "2026_rev_4": (
        718975,
        "359be1fb2c039b0864bf864805f667cc4ada1cc90ddad02d971e255f8afa74ce",
    ),
    "2026_rev_9": (
        709681,
        "d21284a0d08542bbf106b712c3f4b7a5338e93abd9de6c27b5ec6ea82f7ab313",
    ),
    "2026_rev_11": (
        712813,
        "e3dfb6efe3e06332df5580b079242ad2c651be658b204fe4713a70dc863ba811",
    ),
    "2026_rev_12": (
        712989,
        "7228358c06973566809e54eb4bb788948c4252e9b07ed486fdbb6a6146fbeb4a",
    ),
}
YALE_FILE_ANCHORS = {
    "src/model/policy_params.R": (
        21917,
        "8214dbfc1b5fd6a6cd3f56967cb403984c15ea849bc4e7a818d5a29e301d331e",
    ),
    "src/core/helpers.R": (
        18003,
        "4d493f990cfa630219e7338ada94af2dceda32240abeb8ff2983d3cbb6692e4d",
    ),
    "src/model/rate_schema.R": (
        25265,
        "ad4dbb13564913a1a4e6cfe1dda1e89d3f847a5d7aa0bd67035906e180ff95da",
    ),
    "src/pipeline/04_parse_products.R": (
        11777,
        "0f2075871bba55ee31a5b6682965567ef8c06543eac0f87196754be65744ba53",
    ),
    "src/pipeline/06_calculate_rates.R": (
        179892,
        "2620a122159c11cc2b116786925ccbc6d801cb274982034cd8105657ae13a76a",
    ),
    "src/model/data_loaders.R": (
        43137,
        "a088811f84ff19eaf6fce28f2587152c69ed50e53435ddedd2425fd369b62ccc",
    ),
    "src/model/authority_adapter.R": (
        65357,
        "91d6adab284dc823fa4c541910d6c4a74494b3a09f3e5fb6b6a71a98e3b1288a",
    ),
    "config/policy_params.yaml": (
        50577,
        "5f3d79b192b9fb6079e5ad10a1969e12f397567fc9f89d4e202403116ecb6346",
    ),
    "config/revision_dates.csv": (
        6548,
        "e107021bc0674f3f3b3bd38f967dbbea5b168d226929a5e30423b4a068abe346",
    ),
    "resources/s232_metal_chapter_products.csv": (
        15522,
        "c25998367b16a54292b91774af909abd3c0a7628412df9874a34b53cbfcfea98",
    ),
    "resources/s232_derivative_products.csv": (
        25415,
        "4502c782a356b2843cf7652ccaf3dcb2c7af1ac1556fec16e00062acc844a0bb",
    ),
    "resources/s232_annex_products.csv": (
        44677,
        "90b800fc3556b25cbf4cef982dc3232c86e367e1b7ec6f53621a116fc7b4a68d",
    ),
    **{
        f"data/hts_archives/hts_{rev}.json.gz": pin
        for rev, pin in ARCHIVE_ANCHORS.items()
    },
}
CLASS_CONTRACTS = {
    "base": {
        "id": "yale-html-statutory-base-parser-defect",
        "expected_units": 5709,
        "expected_signature_count": 3114,
        "expected_signature_population_sha256": "adfc38ed0b2f7cdf048cdd9e296e07f51e61ac21d8c20fdbedffa4e2179fb0c5",
        "identity_population_sha256": "8ae191bd52d5b76f13f634547a8cdde89247947a311bb7d5be069a532cadbb80",
        "disposition": "upstream_engine_gap",
        "attribution": "reference-defect",
    },
    "section_232": {
        "id": "section232-russia-aluminum-membership-vintage",
        "expected_units": 24,
        "expected_signature_count": 12,
        "expected_signature_population_sha256": "133cb29402eb016569638c03b1d87b9344e4900935ea5b7575be69529c5bbbaa",
        "identity_population_sha256": "fc2f37eff712e696ffc69664998e2eb0562d5b650bb2951fb610881bed7fe987",
        "disposition": "explained_residual",
        "attribution": "input-comparability",
    },
}
EXPECTED_CENSUS = {
    "evaluated_shards": 100,
    "evaluated_records": 19_118_619,
    "selected_unique_cases": 5733,
    "selected_target_units": {"base": 5709, "section_232": 24},
    "selected_signatures": {"base": 3114, "section_232": 12},
    "duplicate_evaluation_case_ids": 0,
    "duplicate_target_unit_keys": 0,
    "engine_errors": 0,
}
LIMITATIONS = {
    "base": "A reference parser/inheritance defect in the exact 5709 statutory-base units, not a preference/GN3(c) claim or a replacement of other GN3(b) findings.",
    "base_counterfactual": "Only empty <u></u> markup is removed from eleven General fields in each complete original archive. The actual parser, schema default, and pre-preference statutory capture are rerun; the full Yale policy pipeline and other counterfactual component outputs are not claimed reproduced.",
    "aluminum": "A bounded source/model membership-vintage input-comparability explanation. Yale already has the Russian 200% override; the pre-annex product lists do not include these three codes.",
    "aluminum_counterfactual": "Only entry_is_section_232_aluminum and entry_is_section_232_covered become false. This is an explicit diagnostic, not a production input correction.",
    "vintage": "The Rev-15 2026-08-03 codified snapshot is not a historical panel or legal onset. The Yale 2026-04-06 source membership date is likewise not an independent legal-rightness determination.",
    "coverage": "No whole-case parity, actual transaction-fact coverage, source closure, or certification follows from either bounded causal explanation.",
}
SOURCE_FACTS = {
    "base_source_map": [
        {"hts10": code, "source_hts": parent, "axiom_general": rate}
        for code, (parent, rate) in sorted(GENERAL.items())
    ],
    "base_intervals": {key: list(value) for key, value in BASE_INTERVALS.items()},
    "aluminum_intervals": {
        key: list(value) for key, value in ALUMINUM_INTERVALS.items()
    },
    "base_mechanism": "The anchored-percent parse_rate rejects tagged General text. Seven direct lines yield NA; ten statistical children inherit stale numeric zero because a malformed parent does not replace/clear rate_stack. default_base_cols coalesces NA to zero. statutory_base_rate is captured before preference scaling.",
    "aluminum_scope": {
        "pre_annex_matching_prefixes": {code: [] for code in ALUMINUM_CODES},
        "annex_matching_rows": {
            code: [
                {
                    "hts_prefix": code,
                    "annex": "1a",
                    "metal_type": "aluminum",
                    "source": "proclamation",
                    "effective_date": "2026-04-06",
                },
                {
                    "hts_prefix": "761699",
                    "annex": "1b",
                    "metal_type": "aluminum",
                    "source": "proclamation",
                    "effective_date": "2026-04-06",
                },
            ]
            for code in ALUMINUM_CODES
        },
        "existing_russia_override": {
            "countries": ["4621"],
            "rate": 2.0,
            "applies_to": ["aluminum"],
            "expiry_date": None,
        },
        "axiom_primary_membership": {
            "name": "s232_aluminum_primary_membership",
            "key": "76169951",
            "value": 1,
            "snapshot_effective_from": "2026-08-03",
        },
        "axiom_projection": "b16_entry_flags._tables unions membership versions; _member selects the eight-digit rate-line key for the Note19 primary table. Date gating of the current snapshot is not applied by that union.",
    },
    "source_locations": {
        "yale_rate_parser": "src/core/helpers.R:67-95",
        "yale_parent_stack": "src/pipeline/04_parse_products.R:72-83,114-130",
        "yale_default": "src/model/rate_schema.R:109-119",
        "yale_statutory_before_preference": "src/pipeline/06_calculate_rates.R:3042-3043,3063",
        "yale_aluminum_scope": "src/model/data_loaders.R:63-90;src/pipeline/06_calculate_rates.R:1945-1975",
        "yale_russia_override": "config/policy_params.yaml:276-280;src/model/policy_params.R:264-281;src/model/authority_adapter.R:86-104",
        "axiom_general": "us/policies/usitc/us-tariff-duty/lines/generated/ch87.yaml:1391-1508;us/policies/cbp/us-tariff-schedule/generated/ch87/ch87.yaml:2111-2133",
        "axiom_aluminum": "us/policies/usitc/us-tariff-incidence/generated/note19-232-aluminum.yaml:10,79-97;us/policies/cbp/us-tariff-schedule/generated/ch76/ch76.yaml:3025-3040",
    },
}

require = foundation.require
canonical_sha256 = foundation.canonical_sha256
population_sha256 = foundation.population_sha256
render = foundation.render


OutputSnapshot = tuple[bytes | None, tuple[int, ...] | None, int | None]
EvidenceSnapshot = tuple[tuple[int, ...], str]


def _file_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


class _ProofInputs:
    """Authenticate proof inputs once, then guard their filesystem identities."""

    def __init__(self) -> None:
        self._snapshots: dict[Path, EvidenceSnapshot] = {}
        self._sealed = False

    def sha256(self, path: Path) -> str:
        resolved = Path(path).resolve()
        prior = self._snapshots.get(resolved)
        if prior is not None:
            require(
                _file_identity(resolved.stat()) == prior[0],
                f"proof input changed: {resolved}",
            )
            return prior[1]
        require(not self._sealed, f"uncaptured proof input after build: {resolved}")
        digest = hashlib.sha256()
        with resolved.open("rb") as source:
            before = _file_identity(os.fstat(source.fileno()))
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
            after = _file_identity(os.fstat(source.fileno()))
        require(
            before == after == _file_identity(resolved.stat()),
            f"proof input changed while authenticating: {resolved}",
        )
        value = digest.hexdigest()
        self._snapshots[resolved] = (before, value)
        return value

    def file_receipt(
        self, path: Path, *, relative_to: Path | None = None
    ) -> dict[str, Any]:
        resolved = Path(path).resolve()
        digest = self.sha256(resolved)
        identity = self._snapshots[resolved][0]
        logical_path = str(resolved)
        if relative_to is not None:
            try:
                logical_path = str(resolved.relative_to(Path(relative_to).resolve()))
            except ValueError:
                pass
        return {"path": logical_path, "bytes": identity[2], "sha256": digest}

    def require_current(self) -> None:
        for path, (identity, _digest) in self._snapshots.items():
            require(
                _file_identity(path.stat()) == identity,
                f"proof input changed: {path}",
            )

    def discard_ephemeral(self, *prefixes: str) -> None:
        for path in tuple(self._snapshots):
            if any(
                part.startswith(prefix) for part in path.parts for prefix in prefixes
            ):
                del self._snapshots[path]

    def seal(self) -> None:
        self._sealed = True

    @contextmanager
    def capture_foundation(self):
        original_sha256 = foundation.sha256
        original_file_receipt = foundation.file_receipt
        foundation.sha256 = self.sha256
        foundation.file_receipt = self.file_receipt
        try:
            yield
        finally:
            foundation.sha256 = original_sha256
            foundation.file_receipt = original_file_receipt


def _output_snapshot(path: Path) -> OutputSnapshot:
    path = path.resolve()
    try:
        with path.open("rb") as source:
            before = os.fstat(source.fileno())
            body = source.read()
            after = os.fstat(source.fileno())
    except FileNotFoundError:
        require(not path.exists(), f"output changed while checking absence: {path}")
        return None, None, None
    identity = _file_identity(before)
    current = path.stat()
    require(
        identity == _file_identity(after) == _file_identity(current),
        f"output changed while snapshotting: {path}",
    )
    return body, identity, stat.S_IMODE(before.st_mode)


def _require_output_current(path: Path, expected: OutputSnapshot) -> None:
    require(
        _output_snapshot(path) == expected,
        f"output changed during proof transaction: {path}",
    )


def _fsync_directory(path: Path) -> None:
    directory_fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


Quarantine = tuple[Path, Path, OutputSnapshot]


def _same_file_after_topology_change(
    current: OutputSnapshot, expected: OutputSnapshot
) -> bool:
    return (
        current[0] == expected[0]
        and current[1] is not None
        and expected[1] is not None
        and current[1][:4] == expected[1][:4]
        and current[2] == expected[2]
    )


def _quarantine_live_path(
    path: Path, label: str, expected: OutputSnapshot
) -> Quarantine:
    directory = Path(tempfile.mkdtemp(prefix=f"{path.name}.{label}.", dir=path.parent))
    directory.chmod(0o700)
    candidate = directory / "candidate"
    try:
        os.rename(path, candidate)
    except BaseException:
        directory.rmdir()
        _fsync_directory(path.parent)
        raise
    return directory, candidate, expected


def _sync_quarantine_move(quarantine: Quarantine, path: Path) -> None:
    directory, _candidate, _snapshot = quarantine
    _fsync_directory(directory)
    _fsync_directory(path.parent)


def _link_quarantined_without_clobber(
    quarantine: Quarantine, path: Path
) -> Quarantine | None:
    directory, candidate, snapshot = quarantine
    current = _output_snapshot(candidate)
    require(
        _same_file_after_topology_change(current, snapshot),
        f"quarantined proof changed before linking: {candidate}",
    )
    try:
        os.link(candidate, path)
    except FileExistsError:
        return None
    linked = _output_snapshot(candidate)
    public = _output_snapshot(path)
    require(
        linked == public
        and linked[0] == current[0]
        and linked[1] is not None
        and current[1] is not None
        and linked[1][:4] == current[1][:4]
        and linked[2] == current[2],
        f"quarantined proof changed while linking: {candidate}",
    )
    _fsync_directory(path.parent)
    return directory, candidate, linked


def _delete_quarantine(quarantine: Quarantine, path: Path) -> None:
    directory, candidate, snapshot = quarantine
    _require_output_current(candidate, snapshot)
    candidate.unlink()
    _fsync_directory(directory)
    require(not candidate.exists(), f"quarantined proof cleanup failed: {candidate}")
    directory.rmdir()
    _fsync_directory(path.parent)


def _conditional_publish_output(
    path: Path,
    output: bytes,
    previous: OutputSnapshot,
    *,
    require_current: Callable[[], None] | None = None,
    before_replace: Callable[[], None] | None = None,
    after_destination_check: Callable[[], None] | None = None,
    before_install: Callable[[], None] | None = None,
    after_staged_unlink: Callable[[], None] | None = None,
    after_replace: Callable[[], None] | None = None,
    before_rollback_displace: Callable[[], None] | None = None,
    after_rollback_displace: Callable[[], None] | None = None,
) -> None:
    """Publish and roll back without ever clobbering a competing destination."""

    path = path.resolve()
    mode = previous[2] if previous[2] is not None else 0o644
    temporary: Path | None = None
    prepared: OutputSnapshot | None = None
    published: OutputSnapshot | None = None
    prior_quarantine: Quarantine | None = None
    installed = False
    committed = False
    primary_failure: BaseException | None = None
    preserved_conflicts: list[Path] = []
    current_guard = require_current or (lambda: None)
    try:
        current_guard()
        _require_output_current(path, previous)
        with tempfile.NamedTemporaryFile(
            "wb", dir=path.parent, prefix=path.name + ".proof.", delete=False
        ) as target:
            temporary = Path(target.name)
            target.write(output)
            target.flush()
            os.fchmod(target.fileno(), mode)
            os.fsync(target.fileno())
        prepared = _output_snapshot(temporary)
        current_guard()
        _require_output_current(path, previous)
        if before_replace is not None:
            before_replace()
        current_guard()
        _require_output_current(path, previous)
        _require_output_current(temporary, prepared)
        if after_destination_check is not None:
            after_destination_check()
        if previous[0] is not None:
            prior_quarantine = _quarantine_live_path(path, "prior", previous)
            _sync_quarantine_move(prior_quarantine, path)
            prior_quarantine = (
                prior_quarantine[0],
                prior_quarantine[1],
                _output_snapshot(prior_quarantine[1]),
            )
            if not _same_file_after_topology_change(prior_quarantine[2], previous):
                raise ValueError(f"output changed during proof transaction: {path}")
        if before_install is not None:
            before_install()
        _require_output_current(temporary, prepared)
        try:
            os.link(temporary, path)
        except FileExistsError as error:
            raise ValueError(
                f"concurrent proof output blocked no-clobber publication: {path}"
            ) from error
        installed = True
        _fsync_directory(path.parent)
        linked_stage = _output_snapshot(temporary)
        public_link = _output_snapshot(path)
        require(
            linked_stage == public_link
            and public_link[0] == output
            and public_link[1] is not None
            and prepared[1] is not None
            and public_link[1][:4] == prepared[1][:4]
            and public_link[2] == mode,
            f"published proof bytes or mode drifted: {path}",
        )
        prepared = linked_stage
        _require_output_current(temporary, prepared)
        temporary.unlink()
        temporary = None
        _fsync_directory(path.parent)
        if after_staged_unlink is not None:
            after_staged_unlink()
        observed_publication = _output_snapshot(path)
        require(
            observed_publication[0] == output
            and observed_publication[1] is not None
            and public_link[1] is not None
            and observed_publication[1][:4] == public_link[1][:4]
            and observed_publication[2] == mode,
            f"published proof changed while removing staged alias: {path}",
        )
        published = observed_publication
        if after_replace is not None:
            after_replace()
        current_guard()
        _require_output_current(path, published)
        committed = True
        if prior_quarantine is not None:
            _delete_quarantine(prior_quarantine, path)
            prior_quarantine = None
    except BaseException as error:
        primary_failure = error
        primary_error = error
        if committed:
            if prior_quarantine is not None:
                directory, candidate, _snapshot = prior_quarantine
                if candidate.exists():
                    primary_error.add_note(
                        "Committed proof retained; prior quarantine cleanup "
                        f"failed at: {candidate}"
                    )
                elif directory.exists():
                    try:
                        directory.rmdir()
                        _fsync_directory(path.parent)
                    except BaseException as cleanup_error:
                        primary_error.add_note(
                            "Empty committed quarantine cleanup failed at "
                            f"{directory}: {cleanup_error}"
                        )
            raise
        owned = published
        if owned is None and installed and prepared is not None:
            try:
                candidate = _output_snapshot(path)
            except BaseException as snapshot_error:
                primary_error.add_note(
                    f"Published proof ownership check failed: {snapshot_error}"
                )
                candidate = (None, None, None)
            if (
                candidate[0] == output
                and candidate[1] is not None
                and prepared[1] is not None
                and candidate[1][:2] == prepared[1][:2]
                and candidate[2] == mode
            ):
                owned = candidate

        def preserve(
            quarantine: Quarantine, cleanup_error: BaseException | None = None
        ) -> None:
            candidate_path = quarantine[1]
            if candidate_path.exists() and candidate_path not in preserved_conflicts:
                preserved_conflicts.append(candidate_path)
            if cleanup_error is not None:
                primary_error.add_note(
                    f"Proof quarantine operation failed for {candidate_path}: "
                    f"{cleanup_error}"
                )

        def restore(quarantine: Quarantine) -> None:
            try:
                linked = _link_quarantined_without_clobber(quarantine, path)
            except BaseException as restore_error:
                preserve(quarantine, restore_error)
                return
            if linked is None:
                preserve(quarantine)
                return
            try:
                _delete_quarantine(linked, path)
            except BaseException as cleanup_error:
                preserve(linked, cleanup_error)

        def delete(quarantine: Quarantine) -> None:
            try:
                _delete_quarantine(quarantine, path)
            except BaseException as cleanup_error:
                preserve(quarantine, cleanup_error)

        if owned is not None:
            if before_rollback_displace is not None:
                try:
                    before_rollback_displace()
                except BaseException as hook_error:
                    primary_error.add_note(f"Pre-rollback hook failed: {hook_error}")
            try:
                rollback_quarantine = _quarantine_live_path(path, "rollback", owned)
            except FileNotFoundError:
                rollback_quarantine = None
            except BaseException as displacement_error:
                primary_error.add_note(
                    f"Rollback quarantine displacement failed: {displacement_error}"
                )
                rollback_quarantine = None
            if rollback_quarantine is not None:
                try:
                    _sync_quarantine_move(rollback_quarantine, path)
                except BaseException as sync_error:
                    primary_error.add_note(
                        f"Rollback quarantine fsync failed: {sync_error}"
                    )
                try:
                    rollback_quarantine = (
                        rollback_quarantine[0],
                        rollback_quarantine[1],
                        _output_snapshot(rollback_quarantine[1]),
                    )
                except BaseException as authentication_error:
                    primary_error.add_note(
                        "Rollback quarantine authentication failed: "
                        f"{authentication_error}"
                    )
                    restore(rollback_quarantine)
                    rollback_quarantine = None
                if after_rollback_displace is not None:
                    try:
                        after_rollback_displace()
                    except BaseException as hook_error:
                        primary_error.add_note(
                            f"Post-displacement rollback hook failed: {hook_error}"
                        )
            if rollback_quarantine is not None and _same_file_after_topology_change(
                rollback_quarantine[2], owned
            ):
                if prior_quarantine is not None:
                    restore(prior_quarantine)
                    prior_quarantine = None
                delete(rollback_quarantine)
            else:
                if rollback_quarantine is not None:
                    restore(rollback_quarantine)
                if prior_quarantine is not None:
                    restore(prior_quarantine)
                    prior_quarantine = None
        elif prior_quarantine is not None:
            restore(prior_quarantine)
            prior_quarantine = None
        if preserved_conflicts:
            primary_error.add_note(
                "Concurrent proof data preserved at: "
                + ", ".join(str(item) for item in preserved_conflicts)
            )
        raise
    finally:
        if temporary is not None:
            try:
                staged = _output_snapshot(temporary)
                if prepared is not None and _same_file_after_topology_change(
                    staged, prepared
                ):
                    temporary.unlink()
                    _fsync_directory(path.parent)
                elif staged[0] is not None and primary_failure is not None:
                    primary_failure.add_note(
                        f"Changed staged proof preserved at: {temporary}"
                    )
            except BaseException as cleanup_error:
                if primary_failure is None:
                    raise
                primary_failure.add_note(
                    f"Staged proof cleanup failed for {temporary}: {cleanup_error}"
                )


def _check_output(
    path: Path,
    output: bytes,
    previous: OutputSnapshot,
    *,
    require_current: Callable[[], None] | None = None,
) -> None:
    current_guard = require_current or (lambda: None)
    current_guard()
    require(
        previous[0] == output,
        f"generated receipt missing or stale: {path}",
    )
    _require_output_current(path, previous)
    current_guard()
    _require_output_current(path, previous)


def _same(actual: Any, expected: Any, label: str) -> None:
    require(canonical_sha256(actual) == canonical_sha256(expected), f"{label} drift")


def _small_inputs(repo_root: Path) -> tuple[dict, dict, dict]:
    documents, receipts = {}, {}
    for name, (relative, digest) in SMALL_INPUTS.items():
        receipt = foundation.file_receipt(repo_root / relative, relative_to=repo_root)
        require(receipt["sha256"] == digest, f"frozen {name} source drift")
        documents[name] = foundation.load_json(repo_root / relative)
        receipts[name] = receipt
    manifest, comparison, contract = (documents[name] for name in SMALL_INPUTS)
    run = manifest["run_identity"]
    require(
        manifest["schema"] == campaign.EVAL_MANIFEST_SCHEMA, "manifest schema drift"
    )
    require(
        comparison["schema"] == campaign.COMPARISON_SCHEMA, "comparison schema drift"
    )
    require(
        contract["schema"] == campaign.INPUT_CONTRACT_SCHEMA
        and contract["verdict"] == "PASS",
        "input contract schema drift",
    )
    require(
        canonical_sha256(run) == EXPECTED_RUN_IDENTITY_SHA256,
        "trusted run identity drift",
    )
    require(
        manifest["run_identity_sha256"]
        == comparison["run_identity_sha256"]
        == EXPECTED_RUN_IDENTITY_SHA256,
        "run binding drift",
    )
    require(
        manifest["generation_id"]
        == comparison["generation_id"]
        == EXPECTED_GENERATION_ID,
        "generation binding drift",
    )
    _same(
        manifest["comparison_receipt"],
        receipts["comparison_receipt"],
        "comparison receipt binding",
    )
    _same(
        manifest["comparison_artifact"],
        comparison["comparison_artifact"],
        "comparison artifact binding",
    )
    _same(
        run["input_contract"],
        {**receipts["input_contract"], "schema": contract["schema"]},
        "input contract binding",
    )
    _same(run["rulespec"], contract["rulespec"], "RuleSpec contract binding")
    require(
        run["rulespec"]["head_commit"] == EXPECTED_RULESPEC_COMMIT
        and run["rulespec"]["dirty"] is False,
        "RuleSpec pin drift",
    )
    require(run["engine"]["sha256"] == EXPECTED_ENGINE_SHA256, "engine pin drift")
    for chapter, digest in EXPECTED_ARTIFACT_SHA256.items():
        require(
            run["chapters"][chapter]["compiled_artifact_sha256"] == digest,
            "compiled artifact pin drift",
        )
    evaluation_only = {
        name: manifest[name]
        for name in (
            "schema",
            "shards",
            "run_identity",
            "run_identity_sha256",
            "generation_id",
        )
    }
    require(
        canonical_sha256(evaluation_only) == comparison["evaluation_manifest_sha256"],
        "evaluation comparison binding drift",
    )
    shards = manifest["shards"]
    require(len(shards) == len(run["chapters"]) == 100, "shard census drift")
    require(
        {s["chapter"] for s in shards.values()} == set(run["chapters"]),
        "missing or duplicate chapter",
    )
    for key, shard in shards.items():
        require(
            shard["key"] == key and shard["engine_errors"] == 0,
            "shard key or error drift",
        )
        require(
            shard["run_identity_sha256"] == EXPECTED_RUN_IDENTITY_SHA256
            and shard["generation_id"] == EXPECTED_GENERATION_ID,
            "shard run binding drift",
        )
    require(
        sum(s["cases"] for s in shards.values()) == 19_118_619,
        "evaluated case census drift",
    )
    require(
        comparison["engine_errors"] == 0
        and comparison["tolerance"] == campaign.TOLERANCE == 1e-12,
        "comparison error or tolerance drift",
    )
    return manifest, comparison, receipts


def _producer_sources(repo_root: Path, run: dict) -> dict:
    evaluator = run["campaign_evaluator"]
    for expected in [evaluator["campaign"], *evaluator["oracle_sources"]]:
        _same(
            foundation.file_receipt(
                repo_root / expected["path"], relative_to=repo_root
            ),
            expected,
            "current evaluator source",
        )
    result = {"campaign_evaluator": evaluator}
    for label, relative, digest in (
        (
            "identity_helper",
            "scripts/build_us_tariff_section232_equivalence_receipt.py",
            EXPECTED_FOUNDATION_SHA256,
        ),
        (
            "runtime_helper",
            "scripts/build_us_tariff_cafta_supersession_receipt.py",
            EXPECTED_RUNTIME_HELPER_SHA256,
        ),
        ("script", PRODUCER_PATH, None),
    ):
        receipt = foundation.file_receipt(repo_root / relative, relative_to=repo_root)
        require(digest is None or receipt["sha256"] == digest, f"{label} source drift")
        result[label] = receipt
    return result


def _source_identity(run: dict) -> dict:
    return {
        "rulespec": run["rulespec"],
        "entry_flag_producers": run["entry_flag_producers"],
        "chapters": {
            chapter: run["chapters"][chapter] for chapter in EXPECTED_ARTIFACT_SHA256
        },
        "engine": run["engine"],
        "yale": {
            "commit": EXPECTED_YALE_COMMIT,
            "tree": EXPECTED_YALE_TREE,
            "files": [
                {"path": path, "bytes": size, "sha256": digest}
                for path, (size, digest) in sorted(YALE_FILE_ANCHORS.items())
            ],
        },
        "rscript": campaign.CAFTA_EXPECTED_RSCRIPT_RECEIPT,
        "r_runtime_tree": campaign.CAFTA_EXPECTED_R_RUNTIME_TREE_RECEIPT,
        "dplyr_tree": campaign.CAFTA_EXPECTED_DPLYR_TREE_RECEIPT,
    }


R_PROGRAM = r"""args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 3)
yale_root <- args[[1]]
request_path <- args[[2]]
scratch <- args[[3]]
fixed_library <- '/Library/Frameworks/R.framework/Versions/4.3-arm64/Resources/library'
.libPaths(fixed_library)
stopifnot(identical(normalizePath(.libPaths()), fixed_library))
for (package in c('dplyr', 'purrr', 'stringr', 'tidyr', 'jsonlite')) {
  stopifnot(startsWith(normalizePath(find.package(package, lib.loc = fixed_library)), fixed_library))
  suppressPackageStartupMessages(library(package, character.only = TRUE, lib.loc = fixed_library))
}
load_definitions <- function(relative, wanted) {
  expressions <- parse(file.path(yale_root, relative), keep.source = FALSE)
  found <- character()
  for (expr in expressions) {
    if (is.call(expr) && identical(expr[[1]], as.name('<-')) &&
        is.symbol(expr[[2]]) && as.character(expr[[2]]) %in% wanted) {
      eval(expr, envir = .GlobalEnv)
      found <- c(found, as.character(expr[[2]]))
    }
  }
  stopifnot(identical(sort(found), sort(wanted)))
}
load_definitions('src/core/helpers.R', c('parse_rate', 'is_simple_rate', 'classify_rate_type',
  'normalize_hts', 'extract_chapter99_refs'))
load_definitions('src/model/rate_schema.R', c('is_valid_hts10', 'default_base_cols'))
load_definitions('src/pipeline/04_parse_products.R', 'parse_products')
pipeline_lines <- readLines(file.path(yale_root, 'src/pipeline/06_calculate_rates.R'), warn = FALSE)
capture_source <- paste(pipeline_lines[3042:3043], collapse = '\n')
stopifnot(grepl('mutate(statutory_base_rate = base_rate)', capture_source, fixed = TRUE))
capture_expression <- parse(text = capture_source)
stopifnot(length(capture_expression) == 1)
request <- fromJSON(request_path, simplifyDataFrame = FALSE)
target_map <- request$targets
target_codes <- vapply(target_map, function(x) x$hts10, character(1))
parent_codes <- unique(vapply(target_map, function(x) x$source_hts, character(1)))
stopifnot(length(parent_codes) == 11)
output <- list()
for (archive in request$archives) {
  original_path <- file.path(yale_root, archive$path)
  original_raw <- fromJSON(original_path, simplifyDataFrame = FALSE)
  codes <- vapply(original_raw, function(x) gsub('.', '', x$htsno %||% '', fixed = TRUE), character(1))
  original_products <- suppressMessages(parse_products(original_path))
  original_products <- original_products[original_products$hts10 %in% target_codes, ]
  stopifnot(nrow(original_products) == length(target_codes), !anyDuplicated(original_products$hts10))
  rates <- default_base_cols(original_products)
  eval(capture_expression, envir = .GlobalEnv)
  original_rates <- rates
  sanitized_raw <- original_raw
  for (parent in parent_codes) {
    positions <- which(codes == parent)
    stopifnot(length(positions) == 1)
    index <- positions[[1]]
    raw <- original_raw[[index]]$general
    stopifnot(length(raw) == 1, grepl('<u></u>', raw, fixed = TRUE))
    sanitized_raw[[index]]$general <- trimws(gsub('<u></u>', '', raw, fixed = TRUE))
    stopifnot(is.na(parse_rate(raw)), !is.na(parse_rate(sanitized_raw[[index]]$general)))
  }
  sanitized_path <- file.path(scratch, paste0(archive$revision, '-markup-only.json'))
  write_json(sanitized_raw, sanitized_path, auto_unbox = TRUE, null = 'null', digits = NA)
  roundtrip <- fromJSON(sanitized_path, simplifyDataFrame = FALSE)
  stopifnot(identical(roundtrip, sanitized_raw))
  for (parent in parent_codes) {
    index <- which(codes == parent)[[1]]
    roundtrip[[index]]$general <- original_raw[[index]]$general
  }
  stopifnot(identical(roundtrip, original_raw))
  sanitized_products <- suppressMessages(parse_products(sanitized_path))
  sanitized_products <- sanitized_products[sanitized_products$hts10 %in% target_codes, ]
  stopifnot(nrow(sanitized_products) == length(target_codes), !anyDuplicated(sanitized_products$hts10))
  rates <- default_base_cols(sanitized_products)
  eval(capture_expression, envir = .GlobalEnv)
  sanitized_rates <- rates
  for (target in target_map) {
    product_index <- which(codes == target$hts10)
    source_index <- which(codes == target$source_hts)
    stopifnot(length(product_index) == 1, length(source_index) == 1)
    original <- original_products[original_products$hts10 == target$hts10, ]
    before <- original_rates[original_rates$hts10 == target$hts10, ]
    after <- sanitized_rates[sanitized_rates$hts10 == target$hts10, ]
    raw <- original_raw[[source_index]]$general
    clean <- sanitized_raw[[source_index]]$general
    stopifnot(before$statutory_base_rate == 0,
      abs(after$statutory_base_rate - target$axiom_general) <= 1e-12)
    output[[length(output) + 1L]] <- list(
      revision = archive$revision, hts10 = target$hts10, source_hts = target$source_hts,
      product_index = product_index, source_index = source_index,
      product_indent = original_raw[[product_index]]$indent,
      source_indent = original_raw[[source_index]]$indent,
      product_general_raw = original_raw[[product_index]]$general,
      source_general_raw = raw, sanitized_source_general = clean,
      raw_parse_rate = parse_rate(raw), sanitized_parse_rate = parse_rate(clean),
      original_product_base_rate = original$base_rate,
      original_product_base_type = original$base_rate_type,
      baseline_statutory_base_rate = before$statutory_base_rate,
      sanitized_statutory_base_rate = after$statutory_base_rate,
      sanitized_delta_to_axiom_general = after$statutory_base_rate - target$axiom_general
    )
  }
  message('Completed actual original/sanitized whole-archive parsing: ', archive$revision)
}
loaded_paths <- setNames(lapply(loadedNamespaces(), function(x) {
  if (identical(x, 'base')) return(normalizePath(file.path(R.home('library'), 'base')))
  normalizePath(getNamespaceInfo(asNamespace(x), 'path'))
}), loadedNamespaces())
stopifnot(all(vapply(loaded_paths, function(x) startsWith(x, fixed_library), logical(1))))
cat(toJSON(list(r_version = paste(R.version$major, R.version$minor, sep = '.'),
  library = fixed_library, loaded_namespace_paths = loaded_paths,
  capture_source = capture_source, rows = output), auto_unbox = TRUE, na = 'null', digits = 16))
cat('\n')
"""


def _r_request() -> dict:
    return {
        "targets": SOURCE_FACTS["base_source_map"],
        "archives": [
            {"revision": rev, "path": f"data/hts_archives/hts_{rev}.json.gz"}
            for rev in ("2026_rev_9", "2026_rev_11", "2026_rev_12")
        ],
    }


def _r_contract() -> dict:
    return {
        "program_sha256": hashlib.sha256(R_PROGRAM.encode()).hexdigest(),
        "request": _r_request(),
        "source_loading": "Actual named function definitions evaluated from the pinned source AST; exact statutory capture expression from source lines3042-3043.",
        "environment": {
            "LANG": "en_US.UTF-8",
            "LC_ALL": "en_US.UTF-8",
            "PATH": "/usr/bin:/bin",
            "TMPDIR": "<private-temporary-directory>",
        },
        "inherited_environment": False,
        "startup": ["--vanilla"],
        "full_archive_replays": 6,
        "changed_general_fields_per_archive": 11,
        "whole_archive_non_general_fields_unchanged": True,
        "cached_products_used": False,
        "result_sha256": EXPECTED_R_RESULT_SHA256,
        "tolerance": campaign.TOLERANCE,
    }


def _case_row(record: dict) -> dict:
    return {
        "hts10": record["hts10"],
        "iso2": record["iso2"],
        "country": record["country"],
        "revision": record["revision"],
        "clipped_from": record["interval"][0],
        "clipped_until": record["interval"][1],
    }


def _target_slot(record: dict) -> str | None:
    if record["hts10"] in GENERAL and record["iso2"] not in campaign.COLUMN2_ORIGINS:
        return "base"
    if (
        record["hts10"] in ALUMINUM_CODES
        and record["iso2"] == "RU"
        and "2026-02-15" <= record["probe"] <= "2026-04-05"
    ):
        return "section_232"
    return None


def _units_from_records(records: Iterable[dict]) -> list[dict]:
    units, seen = [], set()
    for record in records:
        require(not record["engine_errors"], "recorded engine error")
        slot = _target_slot(record)
        if slot is None:
            continue
        for row in campaign.compare_record(record):
            if row["slot"] != slot or row["match"]:
                continue
            key = (record["case_id"], slot)
            require(key not in seen, "duplicate target unit key")
            seen.add(key)
            require(
                row["actual"] > 0 and row["expected"] == 0 and row["delta"] > 0,
                "target sign or expected output drift",
            )
            units.append(
                {
                    "case_id": record["case_id"],
                    "slot": slot,
                    "signature": campaign.mismatch_signature(row),
                    "actual": row["actual"],
                    "expected": row["expected"],
                }
            )
    return sorted(units, key=lambda unit: (unit["case_id"], unit["slot"]))


def _identity(record: dict, slot: str) -> dict:
    return {
        **{
            key: record[key]
            for key in (
                "case_id",
                "hts10",
                "hts_line",
                "iso2",
                "revision",
                "interval",
                "origin_regime",
                "expected",
            )
        },
        "slot": slot,
    }


def _classes(units: list[dict], records: list[dict]) -> list[dict]:
    lookup = {record["case_id"]: record for record in records}
    result = []
    for slot, expected in CLASS_CONTRACTS.items():
        selected = [unit for unit in units if unit["slot"] == slot]
        population = Counter(unit["signature"] for unit in selected)
        identities = [_identity(lookup[u["case_id"]], slot) for u in selected]
        measured = {
            **{key: expected[key] for key in ("id", "disposition", "attribution")},
            "expected_units": len(selected),
            "expected_signature_count": len(population),
            "expected_signature_population_sha256": campaign.signature_population_sha256(
                population.items()
            ),
            # Matches the independent audit: one canonical sorted JSON array,
            # not the foundation helper's sorted-JSON-lines population hash.
            "identity_population_sha256": canonical_sha256(identities),
        }
        _same(measured, expected, f"trusted {slot} class population")
        require(set(population.values()) <= {1, 2}, "signature multiplicity drift")
        result.append({**measured, "slot": slot, "signatures": sorted(population)})
    return sorted(result, key=lambda row: row["id"])


def _catalog(values: Iterable[Any]) -> tuple[list, dict[bytes, int]]:
    unique = {foundation.canonical(value): value for value in values}
    ordered = sorted(unique)
    return [unique[key] for key in ordered], {key: i for i, key in enumerate(ordered)}


def _pack_cases(cases: list[dict]) -> dict:
    """Lossless catalogs retain every actual record/feed/output without 47MB repetition."""
    record_fields = sorted(cases[0]["recorded_evaluation"])
    input_fields = sorted(cases[0]["baseline_inputs"])
    output_fields = sorted(campaign.OUTPUT_NAMES)
    catalogs, indexes = {}, {}
    for field in record_fields:
        catalogs[field], indexes[field] = _catalog(
            c["recorded_evaluation"][field] for c in cases
        )
    vectors, vector_indexes = {}, {}
    for kind, fields in (("input", input_fields), ("output", output_fields)):
        vectors[kind], vector_indexes[kind] = _catalog(
            [c[f"{label}_{kind}s"][field] for field in fields]
            for c in cases
            for label in ("baseline", "counterfactual")
            if f"{label}_{kind}s" in c
        )
    rows = []
    for case in cases:
        require(
            set(case["recorded_evaluation"]) == set(record_fields),
            "record field surface drift",
        )
        row = [
            indexes[field][foundation.canonical(case["recorded_evaluation"][field])]
            for field in record_fields
        ]
        for label, kind, fields in (
            ("baseline", "input", input_fields),
            ("baseline", "output", output_fields),
            ("counterfactual", "input", input_fields),
            ("counterfactual", "output", output_fields),
        ):
            value = case.get(f"{label}_{kind}s")
            if value is None:
                row.append(None)
            else:
                require(set(value) == set(fields), "case vector field surface drift")
                row.append(
                    vector_indexes[kind][
                        foundation.canonical([value[f] for f in fields])
                    ]
                )
        rows.append(row)
    return {
        "encoding": "exact-field-catalogs.v1",
        "record_fields": record_fields,
        "record_catalogs": catalogs,
        "input_fields": input_fields,
        "input_vectors": vectors["input"],
        "output_fields": output_fields,
        "output_vectors": vectors["output"],
        "rows": rows,
    }


def _unpack_cases(packed: Any) -> list[dict]:
    require(
        isinstance(packed, dict)
        and set(packed)
        == {
            "encoding",
            "record_fields",
            "record_catalogs",
            "input_fields",
            "input_vectors",
            "output_fields",
            "output_vectors",
            "rows",
        },
        "case catalog schema drift",
    )
    require(packed["encoding"] == "exact-field-catalogs.v1", "case encoding drift")
    fields = packed["record_fields"]
    require(
        isinstance(fields, list) and fields == sorted(set(fields)),
        "record field catalog drift",
    )
    require(
        set(packed["record_catalogs"]) == set(fields), "record catalog fields drift"
    )
    require(
        isinstance(packed["rows"], list) and len(packed["rows"]) == 5733,
        "actual case population count drift",
    )

    def select(catalog: Any, index: Any) -> Any:
        require(
            isinstance(catalog, list)
            and type(index) is int
            and 0 <= index < len(catalog),
            "invalid catalog reference",
        )
        return catalog[index]

    result = []
    for row in packed["rows"]:
        require(
            isinstance(row, list) and len(row) == len(fields) + 4,
            "case catalog row width drift",
        )
        record = {
            field: select(packed["record_catalogs"][field], index)
            for field, index in zip(fields, row[: len(fields)], strict=True)
        }
        case = {"recorded_evaluation": record}
        for index, (label, kind) in zip(
            row[len(fields) :],
            (
                ("baseline", "input"),
                ("baseline", "output"),
                ("counterfactual", "input"),
                ("counterfactual", "output"),
            ),
            strict=True,
        ):
            if index is None:
                require(label == "counterfactual", "missing baseline vector")
                continue
            vector = select(packed[f"{kind}_vectors"], index)
            vector_fields = packed[f"{kind}_fields"]
            require(
                isinstance(vector, list) and len(vector) == len(vector_fields),
                "case vector width drift",
            )
            require(
                vector_fields == sorted(set(vector_fields)),
                "case vector field order drift",
            )
            case[f"{label}_{kind}s"] = dict(zip(vector_fields, vector, strict=True))
        result.append(case)
    _same(_pack_cases(result), packed, "canonical lossless case catalog")
    return result


def _validate_r_result(replay: dict, source_rows: list[dict]) -> dict[tuple, dict]:
    require(set(replay) == {"contract", "result"}, "R replay schema drift")
    _same(replay["contract"], _r_contract(), "R execution contract")
    result = replay["result"]
    require(
        canonical_sha256(result) == EXPECTED_R_RESULT_SHA256,
        "trusted actual R result drift",
    )
    require(
        result["r_version"] == "4.3.0" and len(result["rows"]) == 51,
        "R runtime or probe count drift",
    )
    lookup = {(r["revision"], r["hts10"]): r for r in result["rows"]}
    expected_keys = {
        (rev, code)
        for rev in ("2026_rev_9", "2026_rev_11", "2026_rev_12")
        for code in GENERAL
    }
    require(set(lookup) == expected_keys, "R vintage/HTS probe population drift")
    source_lookup = {(row["revision"], row["hts10"]): row for row in source_rows}
    for key, row in lookup.items():
        source = source_lookup[key]
        parent, rate = GENERAL[row["hts10"]]
        require(
            row["source_hts"] == parent and row["raw_parse_rate"] is None,
            "R raw rate source drift",
        )
        require(
            row["baseline_statutory_base_rate"] == 0,
            "R baseline statutory result drift",
        )
        require(
            abs(row["sanitized_statutory_base_rate"] - rate) <= campaign.TOLERANCE,
            "R sanitized General result drift",
        )
        for name in ("product_index", "source_index", "source_hts"):
            _same(row[name], source[name], "R source identity")
        for name in ("product", "source"):
            _same(
                row[f"{name}_general_raw"],
                source[name]["general"],
                "R actual raw General field",
            )
            _same(
                row[f"{name}_indent"],
                source[name]["indent"],
                "R original inheritance indent",
            )
        if parent == row["hts10"]:
            require(
                row["original_product_base_rate"] is None,
                "direct original NA result drift",
            )
        else:
            require(
                row["original_product_base_rate"] == 0
                and row["product_general_raw"] == "",
                "statistical inherited-zero result drift",
            )
        require(
            row["sanitized_source_general"]
            == row["source_general_raw"].replace("<u></u>", "").strip(),
            "markup-only General counterfactual drift",
        )
    return lookup


def _validate_cases(
    cases: list[dict], run: dict, r_lookup: dict
) -> tuple[list[dict], dict]:
    require(len(cases) == 5733, "actual case population count drift")
    require(
        population_sha256(cases) == EXPECTED_CASE_POPULATION_SHA256,
        "trusted actual case/feed/paired-output population drift",
    )
    records = [case["recorded_evaluation"] for case in cases]
    ids = [record["case_id"] for record in records]
    require(ids == sorted(set(ids)), "missing, unsorted, or duplicate actual case")
    require(
        population_sha256(records) == EXPECTED_RECORD_POPULATION_SHA256,
        "trusted recorded evaluation population drift",
    )
    units = _units_from_records(records)
    require(len(units) == len(cases), "case/target-unit population drift")
    _classes(units, records)
    r_matched, aluminum_matched, non_target = 0, 0, Counter()
    changed_outputs = Counter()
    for case in cases:
        record = case["recorded_evaluation"]
        slot = _target_slot(record)
        require(slot in CLASS_CONTRACTS, "unrelated case in bounded proof")
        expected_fields = {"recorded_evaluation", "baseline_inputs", "baseline_outputs"}
        if slot == "section_232":
            expected_fields |= {"counterfactual_inputs", "counterfactual_outputs"}
        require(set(case) == expected_fields, "actual case evidence fields drift")
        chapter = "87" if slot == "base" else "76"
        require(record["chapter"] == chapter, "target chapter drift")
        intervals = BASE_INTERVALS if slot == "base" else ALUMINUM_INTERVALS
        start, end, vintage = intervals[record["revision"]]
        _same(record["interval"], [start, end], "exact source interval")
        row = _case_row(record)
        dates = list(campaign._probe_dates(row))
        require(record["probe"] in dates, "recorded endpoint probe drift")
        require(
            campaign._case_id(row, record["probe"], dates.index(record["probe"]))
            == record["case_id"],
            "probe/case identity drift",
        )
        feed = case["baseline_inputs"]
        reconstructed = {
            "hts_line": int(record["hts_line"]),
            "hts_number": record["hts10"],
            "country_of_origin": record["iso2"],
            **{name: False for name in campaign.NEUTRAL_BOOLEAN_INPUTS},
            **campaign._probe_boolean_inputs(record["probe"]),
            **record["flags"],
        }
        _same(feed, reconstructed, "actual recorded feed reconstruction")
        require(
            set(feed) == set(run["chapters"][chapter]["case_feed_inputs"]),
            "compiled feed surface drift",
        )
        _same(
            case["baseline_outputs"],
            record["actual"],
            "baseline recorded Axiom output replay",
        )
        require(
            set(case["baseline_outputs"]) == set(campaign.OUTPUT_NAMES),
            "baseline output surface drift",
        )
        if slot == "base":
            parent, general = GENERAL[record["hts10"]]
            require(
                record["hts_line"] == parent.ljust(10, "0"),
                "General parent/rate-line route drift",
            )
            result = r_lookup[(vintage, record["hts10"])]
            require(
                record["actual"]["mfn_ad_valorem_rate"] == general,
                "actual Axiom General rate drift",
            )
            require(
                float(record["expected"]["statutory_base_rate"])
                == result["baseline_statutory_base_rate"]
                == 0,
                "recorded Yale versus actual R baseline drift",
            )
            require(
                abs(result["sanitized_statutory_base_rate"] - general)
                <= campaign.TOLERANCE,
                "R repaired versus actual Axiom General drift",
            )
            r_matched += 1
        else:
            require(
                record["hts_line"] == "7616995100",
                "aluminum parent rate-line route drift",
            )
            require(
                all(feed[name] is True for name in CHANGED_INPUTS),
                "actual aluminum scope drift",
            )
            _same(
                case["counterfactual_inputs"],
                {**feed, **dict.fromkeys(CHANGED_INPUTS, False)},
                "exact two-input aluminum counterfactual",
            )
            variant = case["counterfactual_outputs"]
            require(
                set(variant) == set(campaign.OUTPUT_NAMES),
                "counterfactual output surface drift",
            )
            require(
                record["actual"]["section_232_aluminum_component_rate"] == 2
                and record["actual"]["section_232_steel_component_rate"] == 0,
                "actual aluminum200 baseline drift",
            )
            require(
                variant["section_232_aluminum_component_rate"]
                == variant["section_232_steel_component_rate"]
                == float(record["expected"]["statutory_rate_232"])
                == 0,
                "counterfactual aluminum target does not match",
            )
            aluminum_matched += 1
            for name in campaign.OUTPUT_NAMES:
                changed_outputs[name] += variant[name] != case["baseline_outputs"][name]
            for compared in campaign.compare_record({**record, "actual": variant}):
                if not compared["match"]:
                    require(
                        compared["slot"] != "section_232",
                        "counterfactual target mismatch",
                    )
                    non_target[compared["slot"]] += 1
    require(
        r_matched == 5709 and aluminum_matched == 24,
        "causal replay target census drift",
    )
    replay = {
        "compiled_artifact_sha256": EXPECTED_ARTIFACT_SHA256,
        "baseline_exact_cases": 5733,
        "baseline_exact_recorded_output_values": 63063,
        "r_original_statutory_matches_recorded_base_units": r_matched,
        "r_markup_only_statutory_matches_actual_general_units": r_matched,
        "r_vintage_hts_probes": 51,
        "r_direct_original_na_probes": 21,
        "r_statistical_original_inherited_zero_probes": 30,
        "r_max_absolute_roundoff": max(
            abs(row["sanitized_delta_to_axiom_general"]) for row in r_lookup.values()
        ),
        "aluminum_counterfactual_exact_target_units": aluminum_matched,
        "aluminum_changed_inputs_only": {
            name: {"from": True, "to": False} for name in CHANGED_INPUTS
        },
        "aluminum_counterfactual_other_slot_mismatches": dict(
            sorted(non_target.items())
        ),
        "aluminum_changed_output_case_counts": {
            name: count for name, count in sorted(changed_outputs.items()) if count
        },
        "whole_case_parity_claimed": False,
        "engine_errors": 0,
        "recorded_evaluation_population_sha256": EXPECTED_RECORD_POPULATION_SHA256,
        "actual_case_feed_and_output_population_sha256": EXPECTED_CASE_POPULATION_SHA256,
    }
    return units, replay


def _bindings() -> dict:
    return {
        "run_identity_sha256": EXPECTED_RUN_IDENTITY_SHA256,
        "generation_id": EXPECTED_GENERATION_ID,
        "recorded_evaluation_population_sha256": EXPECTED_RECORD_POPULATION_SHA256,
        "actual_case_feed_and_output_population_sha256": EXPECTED_CASE_POPULATION_SHA256,
        "identity_digest_definition": "SHA256 of the canonical JSON array of identities sorted by (case_id,slot), each with case_id,slot,hts10,hts_line,iso2,revision,interval,origin_regime and the full original expected field map.",
    }


def validate_artifact(document: Any, *, repo_root: Path = REPO_ROOT) -> dict:
    """Validate the small committed proof without external data mounts or runtimes."""
    try:
        require(
            isinstance(document, dict)
            and set(document)
            == {
                "schema",
                "verdict",
                "producer",
                "bindings",
                "inputs",
                "source_identity",
                "source_facts",
                "source_records",
                "shards",
                "census",
                "cases",
                "units",
                "classes",
                "r_replay",
                "replay",
                "limitations",
                "receipt_payload_sha256",
            },
            "remaining residual proof schema fields drift",
        )
        require(
            document["schema"] == SCHEMA and document["verdict"] == "PASS",
            "proof schema or verdict drift",
        )
        payload = {
            key: value
            for key, value in document.items()
            if key != "receipt_payload_sha256"
        }
        require(
            canonical_sha256(payload) == document["receipt_payload_sha256"],
            "proof payload digest drift",
        )
        manifest, comparison, inputs = _small_inputs(Path(repo_root))
        run = manifest["run_identity"]
        _same(
            document["producer"],
            _producer_sources(Path(repo_root), run),
            "proof producer",
        )
        _same(document["bindings"], _bindings(), "proof bindings")
        _same(
            document["inputs"],
            {**inputs, "comparison_artifact": comparison["comparison_artifact"]},
            "proof input receipts",
        )
        _same(
            document["source_identity"],
            _source_identity(run),
            "trusted source identity",
        )
        _same(document["source_facts"], SOURCE_FACTS, "trusted source facts")
        source_rows = document["source_records"]
        require(
            isinstance(source_rows, list) and len(source_rows) == 57,
            "raw archive source population count drift",
        )
        source_keys = [(row["revision"], row["hts10"]) for row in source_rows]
        require(
            source_keys == sorted(set(source_keys)),
            "raw source order or duplicate identity drift",
        )
        require(
            population_sha256(source_rows) == EXPECTED_SOURCE_RECORD_POPULATION_SHA256,
            "trusted full raw archive record population drift",
        )
        _same(
            document["shards"],
            sorted(manifest["shards"].values(), key=lambda s: s["chapter"]),
            "all-shard bindings",
        )
        _same(document["census"], EXPECTED_CENSUS, "complete scan census")
        _same(document["limitations"], LIMITATIONS, "proof limitations")
        r_lookup = _validate_r_result(document["r_replay"], source_rows)
        cases = _unpack_cases(document["cases"])
        units, replay = _validate_cases(cases, run, r_lookup)
        _same(document["units"], units, "exact target units")
        _same(
            document["classes"],
            _classes(units, [c["recorded_evaluation"] for c in cases]),
            "exact residual classes",
        )
        _same(document["replay"], replay, "actual causal replay measurements")
        return document
    except (
        KeyError,
        TypeError,
        IndexError,
        OSError,
        OverflowError,
        AttributeError,
    ) as exc:
        raise ValueError(
            f"malformed or unavailable remaining residual proof: {exc}"
        ) from exc


def _check_runtime() -> None:
    _same(
        foundation.file_receipt(Path(campaign.CAFTA_EXPECTED_RSCRIPT_RECEIPT["path"])),
        campaign.CAFTA_EXPECTED_RSCRIPT_RECEIPT,
        "actual Rscript",
    )
    for label, expected in (
        ("full R runtime", campaign.CAFTA_EXPECTED_R_RUNTIME_TREE_RECEIPT),
        ("dplyr", campaign.CAFTA_EXPECTED_DPLYR_TREE_RECEIPT),
    ):
        _same(
            cafta._directory_tree_receipt(Path(expected["path"])),
            expected,
            f"actual {label} tree",
        )


def _verify_external_sources(
    yale_root: Path, rulespec_root: Path, engine: Path, run: dict
) -> None:
    require(
        campaign._git_output(yale_root, "rev-parse", "HEAD").decode().strip()
        == EXPECTED_YALE_COMMIT,
        "Yale commit drift",
    )
    require(
        campaign._git_output(yale_root, "rev-parse", "HEAD^{tree}").decode().strip()
        == EXPECTED_YALE_TREE,
        "Yale tree drift",
    )
    require(
        not campaign._git_output(
            yale_root, "diff", "--no-ext-diff", "--binary", "HEAD", "--"
        ),
        "Yale tracked source drift",
    )
    for relative, (size, digest) in YALE_FILE_ANCHORS.items():
        _same(
            foundation.file_receipt(yale_root / relative, relative_to=yale_root),
            {"path": relative, "bytes": size, "sha256": digest},
            "pinned Yale source",
        )
    _same(
        campaign._rulespec_root_identity(rulespec_root),
        run["rulespec"],
        "actual RuleSpec source",
    )
    _same(foundation.file_receipt(engine), run["engine"], "actual pinned engine")
    _same(
        campaign._campaign_evaluator_identity(),
        run["campaign_evaluator"],
        "actual frozen evaluator/runtime",
    )
    _check_runtime()


def _snapshot_sources(
    yale_root: Path, rulespec_root: Path, engine: Path, run: dict, work: Path
) -> tuple[Path, Path, Path]:
    # Immutable Git objects and captured engine bytes prevent live source/path
    # replacement from changing the code executed between endpoint guards.
    yale = work / "yale"
    for relative, (size, digest) in YALE_FILE_ANCHORS.items():
        content = campaign._git_output(
            yale_root, "show", f"{EXPECTED_YALE_COMMIT}:{relative}"
        )
        require(
            len(content) == size and hashlib.sha256(content).hexdigest() == digest,
            "captured Yale Git object drift",
        )
        destination = yale / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    rulespec = work / "rulespec-us"
    rulespec.mkdir()
    archive_bytes = campaign._git_output(
        rulespec_root, "archive", "--format=tar", EXPECTED_RULESPEC_COMMIT
    )
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
        archive.extractall(rulespec, filter="data")
    content = engine.read_bytes()
    require(
        hashlib.sha256(content).hexdigest() == EXPECTED_ENGINE_SHA256,
        "captured engine pin drift",
    )
    binary = work / "axiom-rules-engine"
    binary.write_bytes(content)
    binary.chmod(0o700)
    _verify_snapshot(yale, rulespec, binary, run)
    return yale, rulespec, binary


def _verify_snapshot(yale: Path, rulespec: Path, engine: Path, run: dict) -> None:
    for relative, (size, digest) in YALE_FILE_ANCHORS.items():
        _same(
            foundation.file_receipt(yale / relative, relative_to=yale),
            {"path": relative, "bytes": size, "sha256": digest},
            "private Yale source",
        )
    require(foundation.sha256(engine) == EXPECTED_ENGINE_SHA256, "private engine drift")
    _same(
        campaign._load_entry_flag_tool(rulespec)[1],
        run["entry_flag_producers"],
        "private entry flag source",
    )
    for chapter in EXPECTED_ARTIFACT_SHA256:
        expected = run["chapters"][chapter]
        require(
            foundation.sha256(rulespec / expected["module"])
            == expected["module_sha256"],
            "private chapter source drift",
        )


def _csv_rows(path: Path) -> list[dict]:
    with path.open(newline="") as source:
        return list(
            csv.DictReader(
                line
                for line in source
                if line.strip() and not line.lstrip().startswith("#")
            )
        )


def _source_records(yale: Path, rulespec: Path) -> list[dict]:
    result = []
    for revision in ARCHIVE_ANCHORS:
        with gzip.open(
            yale / f"data/hts_archives/hts_{revision}.json.gz", "rt"
        ) as source:
            raw = json.load(source, object_pairs_hook=foundation._no_duplicate_object)
        by_code = {}
        for index, row in enumerate(raw, 1):
            by_code.setdefault((row.get("htsno") or "").replace(".", ""), []).append(
                (index, row)
            )
        is_base = revision in {"2026_rev_9", "2026_rev_11", "2026_rev_12"}
        targets = sorted(GENERAL) if is_base else ALUMINUM_CODES
        for code in targets:
            require(
                len(by_code.get(code, [])) == 1,
                "missing or duplicate original product row",
            )
            index, product = by_code[code][0]
            datum = {
                "revision": revision,
                "hts10": code,
                "product_index": index,
                "product": product,
            }
            if is_base:
                parent = GENERAL[code][0]
                require(
                    len(by_code.get(parent, [])) == 1,
                    "missing or duplicate original parent row",
                )
                source_index, source = by_code[parent][0]
                datum.update(
                    source_hts=parent, source_index=source_index, source=source
                )
            result.append(datum)
    require(
        population_sha256(result) == EXPECTED_SOURCE_RECORD_POPULATION_SHA256,
        "actual full raw source population drift",
    )
    for relative in (
        "resources/s232_metal_chapter_products.csv",
        "resources/s232_derivative_products.csv",
    ):
        rows = _csv_rows(yale / relative)
        for code in ALUMINUM_CODES:
            matches = [
                row
                for row in rows
                if row["hts_prefix"] and code.startswith(row["hts_prefix"])
            ]
            require(not matches, "pre-annex Yale aluminum membership drift")
    rows = _csv_rows(yale / "resources/s232_annex_products.csv")
    for code, expected in SOURCE_FACTS["aluminum_scope"]["annex_matching_rows"].items():
        matches = [
            row
            for row in rows
            if row["hts_prefix"] and code.startswith(row["hts_prefix"])
        ]
        _same(matches, expected, "dated Yale annex membership")
    params = yaml.safe_load((yale / "config/policy_params.yaml").read_text())
    overrides = [
        row
        for row in params["section_232_country_exemptions"]
        if "4621" in row["countries"]
    ]
    _same(
        overrides,
        [SOURCE_FACTS["aluminum_scope"]["existing_russia_override"]],
        "existing Yale Russian200 override",
    )
    note19 = yaml.safe_load(
        (
            rulespec
            / "us/policies/usitc/us-tariff-incidence/generated/note19-232-aluminum.yaml"
        ).read_text()
    )
    primary = [
        rule
        for rule in note19["rules"]
        if rule["name"] == "s232_aluminum_primary_membership"
    ]
    require(len(primary) == 1, "Note19 primary membership source drift")
    _same(
        primary[0]["versions"],
        [{"effective_from": "2026-08-03", "values": {76169951: 1}}],
        "current Note19 primary membership snapshot",
    )
    require(
        "not a historical-vintage panel" in note19["module"]["summary"],
        "Note19 snapshot limitation drift",
    )
    vintage_dates = {
        row["revision"]: (
            row["policy_effective_date"]
            if row["policy_effective_date"] not in {"", "NA"}
            else row["effective_date"]
        )
        for row in _csv_rows(yale / "config/revision_dates.csv")
    }
    for start, end, vintage in [*BASE_INTERVALS.values(), *ALUMINUM_INTERVALS.values()]:
        for endpoint in (start, end):
            active = [
                (day, rev) for rev, day in vintage_dates.items() if day <= endpoint
            ]
            require(
                max(active)[1] == vintage,
                "Yale reference archive vintage selection drift",
            )
    for relative, fragments in {
        "src/core/helpers.R": ["grepl('^[0-9.]+%$', rate_string)", "return(NA_real_)"],
        "src/pipeline/04_parse_products.R": [
            "rate_stack[[as.character(indent)]] <<- parsed",
            "if (is.na(base_rate) && trimws(general) == '' && indent > 0)",
        ],
        "src/model/rate_schema.R": ["mutate(base_rate = coalesce(base_rate, 0))"],
        "src/model/data_loaders.R": [
            "filter(is.na(effective_date) | effective_date <= !!effective_date)"
        ],
        "src/pipeline/06_calculate_rates.R": [
            "load_232_metal_chapter_products(effective_date = effective_date)",
            "aluminum_products <- match_scope(alum_scope_prefixes)",
            "mutate(statutory_base_rate = base_rate)",
            "base_rate = base_rate * (1 - exemption_share)",
        ],
        "src/model/authority_adapter.R": [
            "metal %in% ex$applies_to",
            "bc[[cty]] <- as.numeric(ex$rate)",
        ],
        "src/model/policy_params.R": [
            "params$S232_COUNTRY_EXEMPTIONS <- map(params$section_232_country_exemptions",
            "rate = entry$rate",
        ],
    }.items():
        source = (yale / relative).read_text()
        require(
            all(fragment in source for fragment in fragments),
            "pinned Yale causal call-path shape drift",
        )
    return sorted(result, key=lambda row: (row["revision"], row["hts10"]))


def _scan_records(manifest: dict, work: Path) -> tuple[list[dict], dict]:
    header = re.compile(rb'"case_id":"schedule-([0-9a-f]{24})","chapter":"([^"]+)"')
    wanted = {code.encode() for code in (*GENERAL, *ALUMINUM_CODES)}
    bucket_paths = {
        digit.encode(): work / f"case-ids-{digit}.txt" for digit in "0123456789abcdef"
    }
    records, count = {}, 0
    with ExitStack() as stack:
        buckets = {
            digit: stack.enter_context(path.open("wb", buffering=1024 * 1024))
            for digit, path in bucket_paths.items()
        }
        for number, shard in enumerate(
            sorted(manifest["shards"].values(), key=lambda s: s["chapter"]), 1
        ):
            path = Path(shard["path"])
            require(
                foundation.sha256(path) == shard["sha256"], "fresh shard content drift"
            )
            observed = 0
            with gzip.open(path, "rb") as source:
                for line in source:
                    observed += 1
                    split = line.find(b',"flags":')
                    require(split > 0, "recorded serialization drift")
                    prefix = line[:split]
                    require(b'"engine_errors":[]' in prefix, "recorded engine error")
                    match = header.search(prefix)
                    require(
                        match is not None and match[2].decode() == shard["chapter"],
                        "recorded case/chapter identity drift",
                    )
                    case_hex = match[1]
                    buckets[case_hex[:1]].write(case_hex + b"\n")
                    marker = line.find(b',"hts10":"', split)
                    require(marker >= 0, "recorded HTS serialization drift")
                    if line[marker + 10 : marker + 20] not in wanted:
                        continue
                    record = foundation.parse_json(
                        line.decode(), label="recorded evaluation"
                    )
                    if _units_from_records([record]):
                        require(
                            record["case_id"] not in records, "duplicate target case"
                        )
                        records[record["case_id"]] = record
            require(observed == shard["cases"], "missing or extra evaluation records")
            count += observed
            require(
                foundation.sha256(path) == shard["sha256"],
                "fresh shard changed during scan",
            )
            if number % 10 == 0:
                print(
                    f"remaining-residual scan: {number}/100 shards, {count:,} records",
                    flush=True,
                )
    for path in bucket_paths.values():
        ids = path.read_bytes().splitlines()
        ids.sort()
        require(
            all(a != b for a, b in zip(ids, ids[1:])), "duplicate evaluation case id"
        )
    selected = [records[key] for key in sorted(records)]
    require(
        population_sha256(selected) == EXPECTED_RECORD_POPULATION_SHA256,
        "trusted complete selected record population drift",
    )
    units = _units_from_records(selected)
    classes = _classes(units, selected)
    census = {
        **EXPECTED_CENSUS,
        "evaluated_shards": len(manifest["shards"]),
        "evaluated_records": count,
        "selected_unique_cases": len(selected),
        "selected_target_units": {
            row["slot"]: row["expected_units"] for row in classes
        },
        "selected_signatures": {
            row["slot"]: row["expected_signature_count"] for row in classes
        },
    }
    _same(census, EXPECTED_CENSUS, "observed complete frozen census")
    return selected, census


def _run_r(yale: Path, source_rows: list[dict], work: Path) -> dict:
    _check_runtime()
    program = work / "remaining-residual-parser.R"
    program.write_text(R_PROGRAM)
    request = work / "remaining-residual-parser-request.json"
    request.write_text(render(_r_request()))
    program_receipt, request_receipt = (
        foundation.file_receipt(program),
        foundation.file_receipt(request),
    )
    completed = subprocess.run(
        [
            campaign.CAFTA_EXPECTED_RSCRIPT_RECEIPT["path"],
            "--vanilla",
            str(program),
            str(yale),
            str(request),
            str(work),
        ],
        env={
            "LANG": "en_US.UTF-8",
            "LC_ALL": "en_US.UTF-8",
            "PATH": "/usr/bin:/bin",
            "TMPDIR": str(work),
        },
        capture_output=True,
        text=True,
        timeout=900,
    )
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="", flush=True)
    completed.check_returncode()
    result = foundation.parse_json(completed.stdout, label="actual R parser result")
    replay = {"contract": _r_contract(), "result": result}
    _validate_r_result(replay, source_rows)
    _same(
        foundation.file_receipt(program),
        program_receipt,
        "private R program after replay",
    )
    _same(
        foundation.file_receipt(request),
        request_receipt,
        "private R request after replay",
    )
    _check_runtime()
    return replay


def _paired_replay(
    records: list[dict], run: dict, rulespec: Path, engine: Path, work: Path
) -> list[dict]:
    from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner
    from axiom_oracles.core.case import Case

    entry_flags, provenance = campaign._load_entry_flag_tool(rulespec)
    _same(provenance, run["entry_flag_producers"], "captured actual entry producer")
    evidence = []
    for chapter, digest in EXPECTED_ARTIFACT_SHA256.items():
        source = run["chapters"][chapter]
        artifact = work / f"ch{chapter}.compiled.json"
        subprocess.run(
            [
                str(engine),
                "compile",
                "--program",
                str(rulespec / source["module"]),
                "--output",
                str(artifact),
            ],
            check=True,
            capture_output=True,
            text=True,
            env=campaign._engine_environment(rulespec),
            timeout=300,
        )
        require(
            foundation.sha256(artifact) == digest,
            "recompiled artifact differs from frozen evaluation",
        )
        declared = campaign.declared_inputs_from_artifact(artifact)
        require(
            set(source["case_feed_inputs"]) <= declared,
            "compiled feed input surface drift",
        )
        module = f"us:policies/cbp/us-tariff-schedule/generated/ch{chapter}/ch{chapter}"
        outputs = [f"{module}#{name}" for name in campaign.OUTPUT_NAMES]
        groups, chapter_evidence = {"baseline": [], "counterfactual": []}, []
        for record in records:
            if record["chapter"] != chapter:
                continue
            feed, flags = campaign._case_feed(
                _case_row(record),
                {"hts_line": record["hts_line"]},
                entry_flags,
                probe=record["probe"],
                case_feed_inputs=source["case_feed_inputs"],
            )
            _same(flags, record["flags"], "recorded versus freshly produced flags")
            item = {"recorded_evaluation": record, "baseline_inputs": feed}
            chapter_evidence.append(item)
            inputs = [("baseline", feed)]
            if chapter == "76":
                require(
                    all(feed[name] is True for name in CHANGED_INPUTS),
                    "actual baseline aluminum scope drift",
                )
                variant = {**feed, **dict.fromkeys(CHANGED_INPUTS, False)}
                item["counterfactual_inputs"] = variant
                inputs.append(("counterfactual", variant))
            for label, values in inputs:
                groups[label].append(
                    Case(
                        case_id=record["case_id"],
                        period=record["probe"],
                        metadata={
                            "axiom_entity": "CustomsEntry",
                            "axiom_entity_id": "entry",
                            "axiom_inputs": {
                                f"{module}#input.{name}": value
                                for name, value in values.items()
                            },
                        },
                        outputs=tuple(outputs),
                    )
                )
        runner = AxiomRulesRunner(
            compiled_artifact_path=artifact,
            binary_path=engine,
            default_entity="CustomsEntry",
            default_entity_id="entry",
            rulespec_repo_roots=(rulespec,),
            batch_size=5000,
            subprocess_run=campaign._engine_subprocess_runner(rulespec),
        )
        for label, cases in groups.items():
            if not cases:
                continue
            results = runner.run_cases(cases, outputs)
            require(len(results) == len(cases), "missing paired engine result")
            for case, result, item in zip(
                cases, results, chapter_evidence, strict=True
            ):
                require(
                    not result.errors and str(result.household_id) == case.case_id,
                    "paired engine error or identity drift",
                )
                values = campaign._result_values(result, campaign.OUTPUT_NAMES)
                item[f"{label}_outputs"] = values
                if label == "baseline":
                    _same(
                        values,
                        item["recorded_evaluation"]["actual"],
                        "actual baseline recorded outputs",
                    )
        require(
            foundation.sha256(artifact) == digest,
            "private compiled artifact changed during replay",
        )
        evidence.extend(chapter_evidence)
        print(
            f"Axiom replay chapter{chapter}: {len(chapter_evidence):,} exact baseline cases",
            flush=True,
        )
    require(
        foundation.sha256(engine) == EXPECTED_ENGINE_SHA256,
        "private engine changed during replay",
    )
    _same(
        campaign._load_entry_flag_tool(rulespec)[1],
        provenance,
        "private entry producer after replay",
    )
    evidence.sort(key=lambda case: case["recorded_evaluation"]["case_id"])
    require(
        population_sha256(evidence) == EXPECTED_CASE_POPULATION_SHA256,
        "actual paired replay differs from independent frozen anchor",
    )
    return evidence


def _build_receipt_impl(
    *,
    repo_root: Path = REPO_ROOT,
    rulespec_root: Path = DEFAULT_RULESPEC_ROOT,
    engine_binary: Path = DEFAULT_ENGINE,
    yale_root: Path = DEFAULT_YALE_ROOT,
) -> dict:
    """Rescan and replay; the publishing CLI owns the manifest lock."""
    repo_root, rulespec_root, engine_binary, yale_root = (
        Path(path).resolve()
        for path in (repo_root, rulespec_root, engine_binary, yale_root)
    )
    require(
        repo_root == REPO_ROOT and campaign.RULESPEC_US_ROOT == rulespec_root,
        "producer requires its frozen checkout and RULESPEC_US_CHECKOUT",
    )
    manifest, comparison, inputs = _small_inputs(repo_root)
    run = manifest["run_identity"]
    producer = _producer_sources(repo_root, run)
    _verify_external_sources(yale_root, rulespec_root, engine_binary, run)
    comparison_path = Path(comparison["comparison_artifact"]["path"])
    _same(
        foundation.file_receipt(comparison_path),
        comparison["comparison_artifact"],
        "actual comparison artifact",
    )
    with tempfile.TemporaryDirectory(prefix="tariff-remaining-residual-proof-") as raw:
        work = Path(raw)
        yale, rulespec, binary = _snapshot_sources(
            yale_root, rulespec_root, engine_binary, run, work
        )
        source_rows = _source_records(yale, rulespec)
        records, census = _scan_records(manifest, work)
        r_replay = _run_r(yale, source_rows, work)
        cases = _paired_replay(records, run, rulespec, binary, work)
        _verify_snapshot(yale, rulespec, binary, run)
    r_lookup = _validate_r_result(r_replay, source_rows)
    units, replay = _validate_cases(cases, run, r_lookup)
    document = {
        "schema": SCHEMA,
        "verdict": "PASS",
        "producer": producer,
        "bindings": _bindings(),
        "inputs": {**inputs, "comparison_artifact": comparison["comparison_artifact"]},
        "source_identity": _source_identity(run),
        "source_facts": SOURCE_FACTS,
        "source_records": source_rows,
        "shards": sorted(
            manifest["shards"].values(), key=lambda shard: shard["chapter"]
        ),
        "census": census,
        "cases": _pack_cases(cases),
        "units": units,
        "classes": _classes(units, records),
        "r_replay": r_replay,
        "replay": replay,
        "limitations": LIMITATIONS,
    }
    _verify_external_sources(yale_root, rulespec_root, engine_binary, run)
    _same(_producer_sources(repo_root, run), producer, "producer after full proof")
    _same(_small_inputs(repo_root)[2], inputs, "small inputs after full proof")
    _same(
        foundation.file_receipt(comparison_path),
        comparison["comparison_artifact"],
        "comparison artifact after full proof",
    )
    for shard in manifest["shards"].values():
        require(
            foundation.sha256(Path(shard["path"])) == shard["sha256"],
            "shard changed after full proof",
        )
    document["receipt_payload_sha256"] = canonical_sha256(document)
    validate_artifact(document, repo_root=repo_root)
    return document


def _build_receipt_transaction(
    *,
    repo_root: Path = REPO_ROOT,
    rulespec_root: Path = DEFAULT_RULESPEC_ROOT,
    engine_binary: Path = DEFAULT_ENGINE,
    yale_root: Path = DEFAULT_YALE_ROOT,
) -> tuple[dict, Callable[[], None]]:
    proof_inputs = _ProofInputs()
    with proof_inputs.capture_foundation():
        document = _build_receipt_impl(
            repo_root=repo_root,
            rulespec_root=rulespec_root,
            engine_binary=engine_binary,
            yale_root=yale_root,
        )
    proof_inputs.discard_ephemeral("tariff-remaining-residual-proof-")
    proof_inputs.seal()
    run_guard = {
        "rulespec": document["source_identity"]["rulespec"],
        "engine": document["source_identity"]["engine"],
        "campaign_evaluator": document["producer"]["campaign_evaluator"],
    }

    def require_current() -> None:
        with proof_inputs.capture_foundation():
            proof_inputs.require_current()
            _verify_external_sources(
                Path(yale_root).resolve(),
                Path(rulespec_root).resolve(),
                Path(engine_binary).resolve(),
                run_guard,
            )
            proof_inputs.require_current()

    require_current()
    return document, require_current


def build_receipt(
    *,
    repo_root: Path = REPO_ROOT,
    rulespec_root: Path = DEFAULT_RULESPEC_ROOT,
    engine_binary: Path = DEFAULT_ENGINE,
    yale_root: Path = DEFAULT_YALE_ROOT,
    _return_transaction: bool = False,
) -> dict | tuple[dict, Callable[[], None]]:
    transaction = _build_receipt_transaction(
        repo_root=repo_root,
        rulespec_root=rulespec_root,
        engine_binary=engine_binary,
        yale_root=yale_root,
    )
    return transaction if _return_transaction else transaction[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rulespec-root", type=Path, default=DEFAULT_RULESPEC_ROOT)
    parser.add_argument("--engine-binary", type=Path, default=DEFAULT_ENGINE)
    parser.add_argument("--yale-root", type=Path, default=DEFAULT_YALE_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check",
        action="store_true",
        help="Fully rescan and replay, then require byte-identical committed proof",
    )
    mode.add_argument("--generate", action="store_true")
    args = parser.parse_args()
    output_path = args.output.resolve()
    with foundation._manifest_lock(foundation.EVAL_MANIFEST):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        previous_output = _output_snapshot(output_path)
        built = build_receipt(
            rulespec_root=args.rulespec_root,
            engine_binary=args.engine_binary,
            yale_root=args.yale_root,
            _return_transaction=True,
        )
        if isinstance(built, tuple):
            document, require_current = built
        else:  # Preserve test and downstream monkeypatch compatibility.
            document, require_current = built, lambda: None
        output = render(document).encode()
        if args.check:
            _check_output(
                output_path,
                output,
                previous_output,
                require_current=require_current,
            )
        else:
            _conditional_publish_output(
                output_path,
                output,
                previous_output,
                require_current=require_current,
            )
    print(
        render(
            {
                "verdict": "PASS",
                "mode": "check" if args.check else "generate",
                "output": str(output_path),
                "units": 5733,
                "signatures": 3126,
                "receipt_payload_sha256": document["receipt_payload_sha256"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.SubprocessError, yaml.YAMLError) as error:
        raise SystemExit(f"remaining residual proof failed: {error}") from error
