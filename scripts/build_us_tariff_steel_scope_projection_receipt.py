#!/usr/bin/env python3
"""Reproduce the bounded steel-scope projection discrepancy, without relabelling.

The proof precedes, and never reads, the disposition ledger, classification,
report, or certificate. Its normal consumer validates a small committed proof
against independent frozen-population anchors. ``--check`` additionally rescans
all recorded evaluations and history and executes the actual pinned engine.

This is a controlled input-comparability explanation, not a determination that
either model's steel scope is legally correct. The Rev-15 snapshot date is not
the first legal coverage date. No new R policy calculation is performed.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
import csv
import gzip
import hashlib
import io
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

from scripts import build_us_tariff_section232_equivalence_receipt as foundation  # noqa: E402
from scripts import us_tariff_schedule_campaign as campaign  # noqa: E402


SCHEMA = "axiom_oracles.us_tariff_schedule.steel_scope_projection.v1"
PRODUCER_PATH = "scripts/build_us_tariff_steel_scope_projection_receipt.py"
DEFAULT_OUTPUT = (
    REPO_ROOT / "reference/us-tariff-schedule/steel-scope-projection-receipt.json"
)
DEFAULT_HISTORICAL_ARTIFACT = Path(
    "/Users/maxghenis/TheAxiomFoundation/axiom-oracles-cert/reference/"
    "us-tariff-schedule/preview-1311/target-mismatch-cells.jsonl.gz"
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
EXPECTED_ENGINE_SHA256 = (
    "674ca6e70afdccb59c3d6847933bc24b4590105e49db54790f2dcd0bdbbe32d7"
)
EXPECTED_YALE_COMMIT = "c4307e514196618afcbf88cf7fd33746417eeabf"
EXPECTED_YALE_TREE = "d3107eae32ae7ac366b319abd4ab7b13c78d5c3c"
EXPECTED_RUN_IDENTITY_SHA256 = (
    "0d5b10e153cf38dc14a1a181c41d393e6bba05fe32ef2a8fe48015624be67f40"
)
EXPECTED_GENERATION_ID = "3b25bc33665d4eed90a21409872a54bb"
EXPECTED_ARTIFACT_SHA256 = (
    "ba3ef3bd731102a277fbeb0e25c163444876f1c18a784cca215dad9bca83033d"
)
EXPECTED_IDENTITY_POPULATION_SHA256 = (
    "689ab6f1568348971ae30fef51ef6160f55f711bdc2970fb58d3a0f801b4d122"
)
EXPECTED_SIGNATURE_POPULATION_SHA256 = (
    "49d4a1956c772b4e0628d90e421efa1eaee1ba509c2fcff46b7a2503352a336a"
)
# Independently established by the preceding hash-checked, full-recorded-data
# anti-join and actual paired engine replay, not taken from this proof itself.
EXPECTED_RECORD_POPULATION_SHA256 = (
    "671be73524433e1df2c0aff5794365f9b20bdebc6157a0db746c0bb689106429"
)
EXPECTED_FEED_POPULATION_SHA256 = (
    "8779082d9da2b3f852c973b55136a563c8f8e63fc06dafed8ed463f79d861e0e"
)
EXPECTED_OUTPUT_POPULATION_SHA256 = (
    "2ae6602be2fcea5c11c36cabadd97233db8310c9e816fe832fd06e5c57367399"
)
EXPECTED_FOUNDATION_SHA256 = (
    "34e92d18ef1dcba5a2ace50b6d2dd2bee348530e7b9ad628a3aaed3bcf353441"
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
HISTORICAL_RECEIPT = {
    "path": "reference/us-tariff-schedule/preview-1311/target-mismatch-cells.jsonl.gz",
    "bytes": 10_088_070,
    "sha256": "d5b53173afe489686aff86a4d1d776bf821cb97945e9ebacd5ba6bc912a8b705",
}
YALE_FILE_ANCHORS = {
    "src/model/data_loaders.R": (
        43137,
        "a088811f84ff19eaf6fce28f2587152c69ed50e53435ddedd2425fd369b62ccc",
    ),
    "src/model/authority_adapter.R": (
        65357,
        "91d6adab284dc823fa4c541910d6c4a74494b3a09f3e5fb6b6a71a98e3b1288a",
    ),
    "src/pipeline/06_calculate_rates.R": (
        179892,
        "2620a122159c11cc2b116786925ccbc6d801cb274982034cd8105657ae13a76a",
    ),
    "config/policy_params.yaml": (
        50577,
        "5f3d79b192b9fb6079e5ad10a1969e12f397567fc9f89d4e202403116ecb6346",
    ),
    "resources/s232_derivative_products.csv": (
        25415,
        "4502c782a356b2843cf7652ccaf3dcb2c7af1ac1556fec16e00062acc844a0bb",
    ),
    "resources/s232_annex_products.csv": (
        44677,
        "90b800fc3556b25cbf4cef982dc3232c86e367e1b7ec6f53621a116fc7b4a68d",
    ),
}
SLOTS = ("brazil_section_301", "forced_labor_section_301")
CHANGED_INPUTS = ("entry_is_section_232_covered", "entry_is_section_232_steel")
CLASS_CONTRACTS = {
    "brazil_section_301": {
        "id": "section232-steel-scope-projection-brazil",
        "expected_units": 6,
        "expected_signature_count": 3,
        "expected_signature_population_sha256": "cf7a7744920e20e7f0044ba5b03524c41acbb0e8ee88e7758f5f8ce99692ce22",
        "identity_population_sha256": "5ecb59148a0ff8f62d9ebc06cbe5fd22d11ba4a8cb577f72db9111beb1cf16d3",
    },
    "forced_labor_section_301": {
        "id": "section232-steel-scope-projection-forced-labor",
        "expected_units": 108,
        "expected_signature_count": 54,
        "expected_signature_population_sha256": "e94e80f21e45138872676b054107a432bdd8fb7f54beae22bcd778734f5ecb0e",
        "identity_population_sha256": "8c8fa2857ff60eba1de9b9a92c6ba65e1439a249a170fdd05d5ea476ad7730d7",
    },
}
EXPECTED_CENSUS = {
    "evaluated_shards": 100,
    "evaluated_records": 19_118_619,
    "historical_records": 395_330,
    "fresh_target_mismatch_units": {
        "brazil_section_301": 11_562,
        "forced_labor_section_301": 206_504,
    },
    "historical_remaining_mismatch_units": {
        "brazil_section_301": 11_556,
        "forced_labor_section_301": 206_396,
    },
    "new_target_units": 114,
    "new_unique_cases": 110,
    "new_signatures": 57,
    "duplicate_evaluation_case_ids": 0,
    "duplicate_historical_unit_keys": 0,
    "new_historical_key_overlap": 0,
    "historical_identity_drifts": 0,
    "engine_errors": 0,
}
LIMITATIONS = {
    "attribution_scope": "Bounded downstream steel-scope input comparability; no legal-rightness determination.",
    "counterfactual": "Only the two Section-232 steel/covered flags are changed to false. This deliberately differs from the pinned incidence producer and is not a production input correction.",
    "vintage": "Rev-15 codified state effective 2026-08-03 is a snapshot, not a historical panel or evidence that steel coverage first began on that date.",
    "coverage": "No transaction-fact coverage, source closure, whole-case parity, or certification claim follows from this explanation.",
    "remaining_counterfactual_differences": "Four Russian cases retain base and total differences; this proof covers only the 114 Brazil/forced-labor target units.",
}
SOURCE_FACTS = {
    "verification": "Pinned source/data inspection plus recorded Yale values; no new R policy calculation.",
    "yale_annex_rows": [
        {
            "hts_prefix": "940399",
            "annex": "1b",
            "metal_type": "steel",
            "source": "proclamation",
            "effective_date": "2026-04-06",
        },
        {
            "hts_prefix": "9403999020",
            "annex": "2",
            "metal_type": "aluminum",
            "source": "proclamation",
            "effective_date": "2026-04-06",
        },
    ],
    "legacy_steel_row": {
        "hts_prefix": "9403999020",
        "ch99_code": "9903.81.91",
        "derivative_type": "steel",
        "effective_date": "2025-03-12",
    },
    "winner": {
        "hts_prefix": "9403999020",
        "tier": "annex_2",
        "metal_type": "aluminum",
        "flat_rate": 0.0,
    },
    "yale_selection": "Date-gated longest-prefix-first, first-match-wins, without a metal-type partition; historical derivative fallback runs only when no annex tier matched.",
    "yale_scope": "The shared .s232_in_scope excludes annex_2; Note52 forced labor and Note50 Brazil consume that scope.",
    "axiom_projection": "b16_entry_flags._tables unions membership versions for steel; _member uses exact hts10 for this table. The separately date-selected aluminum precedence flags are false for this cohort.",
    "axiom_precedence": "entry_is_section_232_covered activates entry_is_note50_52_section_232_precedence_exempt and zeroes both target components.",
    "source_locations": {
        "yale_date_and_winner": "src/model/data_loaders.R:639-750",
        "yale_adapter": "src/model/authority_adapter.R:817-838",
        "yale_scope_and_consumers": "src/pipeline/06_calculate_rates.R:910-923,970,1084",
        "yale_annex_override": "src/pipeline/06_calculate_rates.R:2589-2619",
        "axiom_union_and_exact_key": "tools/b16_entry_flags.py:123-126,154-164",
        "axiom_snapshot_and_atom": "us/policies/usitc/us-tariff-incidence/generated/note16-232-steel.yaml:12,3449",
        "axiom_precedence_branches": "us/policies/cbp/us-tariff-schedule/generated/ch94/ch94.yaml:889,3288,3446",
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
    # JSON canonicalization distinguishes booleans from integer measurements.
    require(canonical_sha256(actual) == canonical_sha256(expected), f"{label} drift")


def _small_inputs(repo_root: Path) -> tuple[dict, dict, dict, dict]:
    documents, receipts = {}, {}
    for name, (relative, digest) in SMALL_INPUTS.items():
        path = repo_root / relative
        receipt = foundation.file_receipt(path, relative_to=repo_root)
        require(receipt["sha256"] == digest, f"frozen {name} source drift")
        documents[name] = foundation.load_json(path)
        receipts[name] = receipt
    manifest = documents["evaluation_manifest"]
    comparison = documents["comparison_receipt"]
    contract = documents["input_contract"]
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
        "run identity binding drift",
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
    require(
        run["chapters"]["94"]["compiled_artifact_sha256"] == EXPECTED_ARTIFACT_SHA256,
        "chapter94 artifact pin drift",
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
            "shard key or engine error drift",
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
    for slot, count in EXPECTED_CENSUS["fresh_target_mismatch_units"].items():
        require(
            comparison["per_slot"][slot]["mismatch"] == count,
            "target comparison census drift",
        )
    require(
        comparison["engine_errors"] == 0
        and comparison["tolerance"] == campaign.TOLERANCE,
        "comparison engine error or tolerance drift",
    )
    return manifest, comparison, contract, receipts


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
    helper = foundation.file_receipt(
        repo_root / "scripts/build_us_tariff_section232_equivalence_receipt.py",
        relative_to=repo_root,
    )
    require(
        helper["sha256"] == EXPECTED_FOUNDATION_SHA256,
        "comparison identity helper source drift",
    )
    return {
        "script": foundation.file_receipt(
            repo_root / PRODUCER_PATH, relative_to=repo_root
        ),
        "identity_helper": helper,
        "campaign_evaluator": evaluator,
    }


def _source_identity(run: dict) -> dict:
    return {
        "rulespec": run["rulespec"],
        "entry_flag_producers": run["entry_flag_producers"],
        "chapter94": run["chapters"]["94"],
        "engine": run["engine"],
        "yale": {
            "commit": EXPECTED_YALE_COMMIT,
            "tree": EXPECTED_YALE_TREE,
            "files": [
                {"path": path, "bytes": size, "sha256": digest}
                for path, (size, digest) in sorted(YALE_FILE_ANCHORS.items())
            ],
        },
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


def _units_from_records(records: Iterable[dict]) -> list[dict]:
    units = []
    seen = set()
    for record in records:
        require(not record["engine_errors"], "recorded engine error")
        for row in campaign.compare_record(record):
            if row["slot"] not in SLOTS or row["match"]:
                continue
            identity = foundation._identity(row, label="steel scope")
            key = foundation._identity_key(identity)
            require(key not in seen, "duplicate target unit key")
            seen.add(key)
            require(
                row["actual"] == 0 and row["delta"] < 0,
                "target sign or recorded output drift",
            )
            units.append(
                {"identity": identity, "signature": campaign.mismatch_signature(row)}
            )
    return sorted(units, key=lambda u: foundation._identity_key(u["identity"]))


def _classes(units: list[dict]) -> list[dict]:
    result = []
    for slot, expected in CLASS_CONTRACTS.items():
        selected = [u for u in units if u["identity"]["slot"] == slot]
        population = Counter(u["signature"] for u in selected)
        measured = {
            "id": expected["id"],
            "expected_units": len(selected),
            "expected_signature_count": len(population),
            "expected_signature_population_sha256": campaign.signature_population_sha256(
                population.items()
            ),
            "identity_population_sha256": population_sha256(
                u["identity"] for u in selected
            ),
        }
        _same(measured, expected, f"trusted {slot} class population")
        require(set(population.values()) == {2}, "target signature multiplicity drift")
        result.append(
            {
                **measured,
                "slot": slot,
                "disposition": "explained_residual",
                "attribution": "input-comparability",
                "signatures": sorted(population),
            }
        )
    return sorted(result, key=lambda row: row["id"])


def _validate_case_evidence(cases: Any, run: dict) -> tuple[list[dict], dict]:
    require(
        isinstance(cases, list) and len(cases) == 110,
        "actual case population count drift",
    )
    records = [case["recorded_evaluation"] for case in cases]
    case_ids = [r["case_id"] for r in records]
    require(
        case_ids == sorted(set(case_ids)),
        "missing, unsorted, or duplicate recorded case",
    )
    require(
        population_sha256(records) == EXPECTED_RECORD_POPULATION_SHA256,
        "trusted recorded evaluation population drift",
    )
    feeds = [
        {
            "case_id": c["recorded_evaluation"]["case_id"],
            "baseline_inputs": c["baseline_inputs"],
            "counterfactual_inputs": c["counterfactual_inputs"],
        }
        for c in cases
    ]
    require(
        population_sha256(feeds) == EXPECTED_FEED_POPULATION_SHA256,
        "trusted actual feed population drift",
    )
    outputs = [
        {
            "case_id": c["recorded_evaluation"]["case_id"],
            "baseline_outputs": c["baseline_outputs"],
            "counterfactual_outputs": c["counterfactual_outputs"],
        }
        for c in cases
    ]
    require(
        population_sha256(outputs) == EXPECTED_OUTPUT_POPULATION_SHA256,
        "trusted paired output population drift",
    )
    units = _units_from_records(records)
    require(len(units) == 114, "target unit count drift")
    require(
        population_sha256(u["identity"] for u in units)
        == EXPECTED_IDENTITY_POPULATION_SHA256,
        "trusted target identity population drift",
    )
    signatures = Counter(u["signature"] for u in units)
    require(
        len(signatures) == 57
        and campaign.signature_population_sha256(signatures.items())
        == EXPECTED_SIGNATURE_POPULATION_SHA256,
        "trusted target signature population drift",
    )
    counterfactual_residuals = Counter()
    residual_origins = set()
    changed_outputs = Counter()
    target_matches = Counter()
    for case in cases:
        require(
            set(case)
            == {
                "recorded_evaluation",
                "baseline_inputs",
                "counterfactual_inputs",
                "baseline_outputs",
                "counterfactual_outputs",
            },
            "case evidence fields drift",
        )
        record = case["recorded_evaluation"]
        require(
            record["chapter"] == "94"
            and record["hts10"] == "9403999020"
            and record["hts_line"] == "9403999000",
            "target tariff route drift",
        )
        row = _case_row(record)
        dates = list(campaign._probe_dates(row))
        require(record["probe"] in dates, "recorded endpoint probe drift")
        require(
            campaign._case_id(row, record["probe"], dates.index(record["probe"]))
            == record["case_id"],
            "probe/case identity drift",
        )
        feed = case["baseline_inputs"]
        variant = case["counterfactual_inputs"]
        reconstructed = {
            "hts_line": int(record["hts_line"]),
            "hts_number": record["hts10"],
            "country_of_origin": record["iso2"],
            **{name: False for name in campaign.NEUTRAL_BOOLEAN_INPUTS},
            **campaign._probe_boolean_inputs(record["probe"]),
            **record["flags"],
        }
        _same(feed, reconstructed, "recorded case feed reconstruction")
        require(
            set(feed) == set(run["chapters"]["94"]["case_feed_inputs"]),
            "case feed contract drift",
        )
        require(
            all(feed[name] is True for name in CHANGED_INPUTS),
            "baseline steel scope input drift",
        )
        _same(
            variant,
            {**feed, **dict.fromkeys(CHANGED_INPUTS, False)},
            "exact two-input counterfactual",
        )
        _same(
            case["baseline_outputs"],
            record["actual"],
            "baseline recorded output replay",
        )
        require(
            set(case["baseline_outputs"])
            == set(case["counterfactual_outputs"])
            == set(campaign.OUTPUT_NAMES),
            "paired output surface drift",
        )
        require(
            record["actual"]["section_232_steel_component_rate"] == 0.5
            and float(record["expected"]["statutory_rate_232"]) == 0,
            "recorded upstream steel difference drift",
        )
        for name in campaign.OUTPUT_NAMES:
            changed_outputs[name] += (
                case["baseline_outputs"][name] != case["counterfactual_outputs"][name]
            )
        for slot in SLOTS:
            name = campaign.SLOT_OUTPUTS[slot][0]
            expected = float(
                record["expected"][campaign.EXPECTED_SLOT_COLUMNS[slot][0]]
            )
            if record["actual"][name] != expected:
                require(
                    case["counterfactual_outputs"][name] == expected,
                    "counterfactual does not exactly match target",
                )
                target_matches[slot] += 1
        variant_record = {**record, "actual": case["counterfactual_outputs"]}
        for comparison in campaign.compare_record(variant_record):
            if not comparison["match"]:
                counterfactual_residuals[comparison["slot"]] += 1
                residual_origins.add(record["iso2"])
    _same(
        dict(target_matches),
        {
            slot: contract["expected_units"]
            for slot, contract in CLASS_CONTRACTS.items()
        },
        "counterfactual target counts",
    )
    _same(
        dict(counterfactual_residuals),
        {"base": 4, "total": 4},
        "counterfactual non-target residuals",
    )
    require(residual_origins == {"RU"}, "counterfactual non-target origin drift")
    replay = {
        "compiled_artifact_sha256": EXPECTED_ARTIFACT_SHA256,
        "baseline_exact_cases": 110,
        "baseline_exact_recorded_output_values": 1210,
        "baseline_exact_target_units": 114,
        "counterfactual_exact_target_units": dict(target_matches),
        "changed_inputs_only": {
            name: {"from": True, "to": False} for name in CHANGED_INPUTS
        },
        "counterfactual_other_slot_mismatches": dict(counterfactual_residuals),
        "counterfactual_other_slot_origins": sorted(residual_origins),
        "changed_output_case_counts": {
            name: count for name, count in changed_outputs.items() if count
        },
        "whole_case_parity_claimed": False,
        "engine_errors": 0,
        "recorded_evaluation_population_sha256": EXPECTED_RECORD_POPULATION_SHA256,
        "actual_feed_population_sha256": EXPECTED_FEED_POPULATION_SHA256,
        "paired_output_population_sha256": EXPECTED_OUTPUT_POPULATION_SHA256,
    }
    return units, replay


def validate_artifact(document: Any, *, repo_root: Path = REPO_ROOT) -> dict:
    """Validate the bounded small proof; never scan data or execute an engine.

    Fixed independently observed population hashes are trust anchors, not claims
    accepted because the supplied document has a valid self-hash. External source
    mounts are unnecessary here; full ``--check`` verifies those actual bytes.
    """
    try:
        require(isinstance(document, dict), "steel scope proof must be an object")
        expected_fields = {
            "schema",
            "verdict",
            "producer",
            "bindings",
            "inputs",
            "source_identity",
            "source_facts",
            "shards",
            "census",
            "cases",
            "units",
            "classes",
            "replay",
            "limitations",
            "receipt_payload_sha256",
        }
        require(
            set(document) == expected_fields, "steel scope proof schema fields drift"
        )
        require(
            document["schema"] == SCHEMA and document["verdict"] == "PASS",
            "steel scope proof schema or verdict drift",
        )
        payload = {
            key: value
            for key, value in document.items()
            if key != "receipt_payload_sha256"
        }
        require(
            canonical_sha256(payload) == document["receipt_payload_sha256"],
            "steel scope proof payload digest drift",
        )
        manifest, comparison, _contract, inputs = _small_inputs(Path(repo_root))
        run = manifest["run_identity"]
        _same(
            document["producer"],
            _producer_sources(Path(repo_root), run),
            "proof producer",
        )
        _same(
            document["bindings"],
            {
                "run_identity_sha256": EXPECTED_RUN_IDENTITY_SHA256,
                "generation_id": EXPECTED_GENERATION_ID,
                "identity_population_sha256": EXPECTED_IDENTITY_POPULATION_SHA256,
                "signature_population_sha256": EXPECTED_SIGNATURE_POPULATION_SHA256,
            },
            "proof bindings",
        )
        _same(
            document["inputs"],
            {
                **inputs,
                "historical_artifact": HISTORICAL_RECEIPT,
                "comparison_artifact": comparison["comparison_artifact"],
            },
            "proof input receipts",
        )
        _same(
            document["source_identity"],
            _source_identity(run),
            "trusted source identity",
        )
        _same(document["source_facts"], SOURCE_FACTS, "trusted source facts")
        _same(
            document["shards"],
            sorted(manifest["shards"].values(), key=lambda s: s["chapter"]),
            "all-shard bindings",
        )
        _same(document["census"], EXPECTED_CENSUS, "complete scan census")
        _same(document["limitations"], LIMITATIONS, "proof limitations")
        units, replay = _validate_case_evidence(document["cases"], run)
        _same(document["units"], units, "exact target units")
        _same(document["classes"], _classes(units), "exact explained classes")
        _same(document["replay"], replay, "paired replay measurements")
        return document
    except (KeyError, TypeError, IndexError, OSError, OverflowError) as exc:
        raise ValueError(f"malformed or unavailable steel scope proof: {exc}") from exc


def _check_historical_file(path: Path) -> None:
    receipt = foundation.file_receipt(path)
    require(
        receipt["sha256"] == HISTORICAL_RECEIPT["sha256"]
        and receipt["bytes"] == HISTORICAL_RECEIPT["bytes"],
        "immutable historical artifact drift",
    )


def _historical_identities(rows: Iterable[dict]) -> dict:
    result = {}
    for row in rows:
        identity = foundation._identity(row, label="historical steel scope anti-join")
        key = foundation._identity_key(identity)
        require(key not in result, "duplicate historical unit key")
        result[key] = identity
    require(len(result) == 395_330, "historical record census drift")
    return result


def _unique_case_buckets(paths: Iterable[Path]) -> None:
    # Partitioning keeps the global duplicate audit bounded in memory; every
    # recorded case ID, including matching/non-target cases, is audited.
    for path in paths:
        values = path.read_bytes().splitlines()
        values.sort()
        require(
            all(a != b for a, b in zip(values, values[1:])),
            "duplicate evaluation case id",
        )


def _scan_recorded_inputs(
    manifest: dict, historical_path: Path, work: Path
) -> tuple[list[dict], dict]:
    _check_historical_file(historical_path)
    historical = _historical_identities(foundation._iter_jsonl_gzip(historical_path))
    fields = {
        slot: (campaign.SLOT_OUTPUTS[slot][0], campaign.EXPECTED_SLOT_COLUMNS[slot][0])
        for slot in SLOTS
    }
    require(
        all(
            len(campaign.SLOT_OUTPUTS[s]) == len(campaign.EXPECTED_SLOT_COLUMNS[s]) == 1
            for s in SLOTS
        ),
        "target slot output contract drift",
    )
    pattern = re.compile(
        rb'"('
        + b"|".join(n.encode() for names in fields.values() for n in names)
        + rb')":("[^"]*"|[-+0-9.eE]+)'
    )
    header = re.compile(rb'"case_id":"schedule-([0-9a-f]{24})","chapter":"([^"]+)"')
    zero_tokens = tuple(
        token
        for actual, expected in fields.values()
        for token in ((f'"{actual}":0.0,').encode(), (f'"{expected}":"0",').encode())
    )
    fresh, remaining = Counter(), Counter()
    new_records, new_units, seen_units = {}, {}, set()
    total_records = 0
    bucket_paths = {
        digit.encode(): work / f"case-ids-{digit}.txt" for digit in "0123456789abcdef"
    }
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
                    require(
                        b'"engine_errors":[]' in prefix,
                        "recorded evaluation engine error",
                    )
                    match = header.search(prefix)
                    require(
                        match is not None and match[2].decode() == shard["chapter"],
                        "recorded case/chapter identity drift",
                    )
                    case_hex = match[1]
                    buckets[case_hex[:1]].write(case_hex + b"\n")
                    if all(token in prefix for token in zero_tokens):
                        continue
                    values = {
                        name.decode(): float(value.strip(b'"'))
                        for name, value in pattern.findall(prefix)
                    }
                    candidates = {
                        slot
                        for slot, (actual, expected) in fields.items()
                        if actual in values
                        and expected in values
                        and abs(values[actual] - values[expected]) > campaign.TOLERANCE
                    }
                    if not candidates:
                        continue
                    record = foundation.parse_json(
                        line.decode(), label="recorded evaluation"
                    )
                    for row in campaign.compare_record(record):
                        if row["slot"] not in SLOTS or row["match"]:
                            continue
                        require(
                            row["slot"] in candidates, "numeric prefilter disagreement"
                        )
                        unit = foundation._identity(
                            row, label="fresh steel scope anti-join"
                        )
                        key = foundation._identity_key(unit)
                        require(key not in seen_units, "duplicate fresh mismatch unit")
                        seen_units.add(key)
                        fresh[row["slot"]] += 1
                        if key in historical:
                            _same(unit, historical[key], "historical identity")
                            remaining[row["slot"]] += 1
                        else:
                            require(key not in new_units, "duplicate new unit")
                            new_units[key] = unit
                            _same(
                                new_records.setdefault(record["case_id"], record),
                                record,
                                "shared recorded case",
                            )
            require(observed == shard["cases"], "missing or extra evaluation records")
            total_records += observed
            require(
                foundation.sha256(path) == shard["sha256"],
                "fresh shard changed during scan",
            )
            if number % 10 == 0:
                print(
                    f"steel-scope scan: {number}/100 shards, {total_records:,} records",
                    flush=True,
                )
    _unique_case_buckets(bucket_paths.values())
    _check_historical_file(historical_path)
    require(
        not set(new_units).intersection(historical), "new/history population overlap"
    )
    units = _units_from_records(new_records.values())
    _same(
        [u["identity"] for u in units],
        [new_units[key] for key in sorted(new_units)],
        "new case/unit anti-join",
    )
    census = {
        **EXPECTED_CENSUS,
        "evaluated_shards": len(manifest["shards"]),
        "evaluated_records": total_records,
        "historical_records": len(historical),
        "fresh_target_mismatch_units": dict(fresh),
        "historical_remaining_mismatch_units": dict(remaining),
        "new_target_units": len(new_units),
        "new_unique_cases": len(new_records),
        "new_signatures": len({u["signature"] for u in units}),
    }
    _same(census, EXPECTED_CENSUS, "observed complete anti-join census")
    require(
        population_sha256(new_units.values()) == EXPECTED_IDENTITY_POPULATION_SHA256,
        "trusted new identity population drift",
    )
    _classes(units)
    return [new_records[key] for key in sorted(new_records)], census


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
    for name, (size, digest) in YALE_FILE_ANCHORS.items():
        _same(
            foundation.file_receipt(yale_root / name, relative_to=yale_root),
            {"path": name, "bytes": size, "sha256": digest},
            "pinned Yale source",
        )
    _same(
        campaign._rulespec_root_identity(rulespec_root),
        run["rulespec"],
        "actual RuleSpec source",
    )
    _same(foundation.file_receipt(engine), run["engine"], "actual engine source")
    _same(
        campaign._campaign_evaluator_identity(),
        run["campaign_evaluator"],
        "actual evaluator/runtime",
    )
    with (yale_root / "resources/s232_annex_products.csv").open(newline="") as source:
        rows = list(csv.DictReader(source))
    for expected in SOURCE_FACTS["yale_annex_rows"]:
        require(rows.count(expected) == 1, "Yale exact annex source row drift")
    with (yale_root / "resources/s232_derivative_products.csv").open(
        newline=""
    ) as source:
        rows = list(csv.DictReader(source))
    require(
        rows.count(SOURCE_FACTS["legacy_steel_row"]) == 1, "Yale legacy steel row drift"
    )
    loader = (yale_root / "src/model/data_loaders.R").read_text()
    for fragment in (
        "effective_date <= as.character(!!effective_date)",
        "arrange(desc(nchar(hts_prefix)))",
        "idx[mask & is.na(idx)] <- pat$.row[i]",
        "!is.na(tier) ~ tier,",
        "deriv_hit    ~ 'annex_1b'",
    ):
        require(fragment in loader, "Yale date/winner/fallback source shape drift")


def _paired_replay(
    records: list[dict], run: dict, rulespec_root: Path, engine: Path, work: Path
) -> list[dict]:
    from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner
    from axiom_oracles.core.case import Case

    captured_engine = engine.read_bytes()
    require(
        hashlib.sha256(captured_engine).hexdigest() == EXPECTED_ENGINE_SHA256,
        "captured engine pin drift",
    )
    snapshot_engine = work / "axiom-rules-engine"
    snapshot_engine.write_bytes(captured_engine)
    snapshot_engine.chmod(0o700)
    snapshot = work / "rulespec-us"
    snapshot.mkdir()
    archive_bytes = campaign._git_output(
        rulespec_root, "archive", "--format=tar", EXPECTED_RULESPEC_COMMIT
    )
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
        archive.extractall(snapshot, filter="data")
    chapter = run["chapters"]["94"]
    require(
        foundation.sha256(snapshot / chapter["module"]) == chapter["module_sha256"],
        "captured chapter94 source drift",
    )
    entry_flags, provenance = campaign._load_entry_flag_tool(snapshot)
    _same(provenance, run["entry_flag_producers"], "captured entry producer")
    artifact = work / "chapter94.compiled.json"
    subprocess.run(
        [
            str(snapshot_engine),
            "compile",
            "--program",
            str(snapshot / chapter["module"]),
            "--output",
            str(artifact),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=campaign._engine_environment(snapshot),
    )
    require(
        foundation.sha256(artifact) == EXPECTED_ARTIFACT_SHA256,
        "recompiled artifact differs from frozen evaluation",
    )
    declared = campaign.declared_inputs_from_artifact(artifact)
    require(
        set(chapter["case_feed_inputs"]) <= declared, "compiled case feed surface drift"
    )
    module = "us:policies/cbp/us-tariff-schedule/generated/ch94/ch94"
    outputs = [f"{module}#{name}" for name in campaign.OUTPUT_NAMES]
    evidence, groups = [], {"baseline": [], "counterfactual": []}
    for record in records:
        feed, flags = campaign._case_feed(
            _case_row(record),
            {"hts_line": record["hts_line"]},
            entry_flags,
            probe=record["probe"],
            case_feed_inputs=chapter["case_feed_inputs"],
        )
        _same(flags, record["flags"], "recorded versus freshly produced flags")
        require(
            all(feed[name] is True for name in CHANGED_INPUTS),
            "actual baseline scope drift",
        )
        variant = {**feed, **dict.fromkeys(CHANGED_INPUTS, False)}
        evidence.append(
            {
                "recorded_evaluation": record,
                "baseline_inputs": feed,
                "counterfactual_inputs": variant,
            }
        )
        for label, inputs in (("baseline", feed), ("counterfactual", variant)):
            groups[label].append(
                Case(
                    case_id=record["case_id"],
                    period=record["probe"],
                    metadata={
                        "axiom_entity": "CustomsEntry",
                        "axiom_entity_id": "entry",
                        "axiom_inputs": {
                            f"{module}#input.{name}": value
                            for name, value in inputs.items()
                        },
                    },
                    outputs=tuple(outputs),
                )
            )
    runner = AxiomRulesRunner(
        compiled_artifact_path=artifact,
        binary_path=snapshot_engine,
        default_entity="CustomsEntry",
        default_entity_id="entry",
        rulespec_repo_roots=(snapshot,),
        batch_size=5000,
        subprocess_run=campaign._engine_subprocess_runner(snapshot),
    )
    for label, cases in groups.items():
        results = runner.run_cases(cases, outputs)
        require(len(results) == len(cases), "missing paired engine result")
        for case, result, item in zip(cases, results, evidence, strict=True):
            require(
                not result.errors and str(result.household_id) == case.case_id,
                "paired engine error or identity drift",
            )
            item[f"{label}_outputs"] = campaign._result_values(
                result, campaign.OUTPUT_NAMES
            )
    require(
        foundation.sha256(snapshot_engine) == EXPECTED_ENGINE_SHA256,
        "private engine changed during replay",
    )
    require(
        foundation.sha256(artifact) == EXPECTED_ARTIFACT_SHA256,
        "private artifact changed during replay",
    )
    _same(
        campaign._load_entry_flag_tool(snapshot)[1],
        provenance,
        "private entry producer after replay",
    )
    _validate_case_evidence(evidence, run)
    return evidence


def _build_receipt_impl(
    *,
    repo_root: Path = REPO_ROOT,
    historical_artifact: Path = DEFAULT_HISTORICAL_ARTIFACT,
    rulespec_root: Path = DEFAULT_RULESPEC_ROOT,
    engine_binary: Path = DEFAULT_ENGINE,
    yale_root: Path = DEFAULT_YALE_ROOT,
) -> dict:
    """Fully rederive the proof; the publishing CLI owns the manifest lock."""
    repo_root, historical_artifact, rulespec_root, engine_binary, yale_root = (
        Path(p).resolve()
        for p in (
            repo_root,
            historical_artifact,
            rulespec_root,
            engine_binary,
            yale_root,
        )
    )
    require(
        repo_root == REPO_ROOT and campaign.RULESPEC_US_ROOT == rulespec_root,
        "producer requires its exact frozen checkout and RULESPEC_US_CHECKOUT",
    )
    manifest, comparison, _contract, inputs = _small_inputs(repo_root)
    run = manifest["run_identity"]
    producer = _producer_sources(repo_root, run)
    _verify_external_sources(yale_root, rulespec_root, engine_binary, run)
    comparison_path = Path(comparison["comparison_artifact"]["path"])
    _same(
        foundation.file_receipt(comparison_path),
        comparison["comparison_artifact"],
        "actual comparison artifact",
    )
    with tempfile.TemporaryDirectory(prefix="tariff-steel-scope-proof-") as raw:
        work = Path(raw)
        records, census = _scan_recorded_inputs(manifest, historical_artifact, work)
        cases = _paired_replay(records, run, rulespec_root, engine_binary, work)
    units, replay = _validate_case_evidence(cases, run)
    document = {
        "schema": SCHEMA,
        "verdict": "PASS",
        "producer": producer,
        "bindings": {
            "run_identity_sha256": EXPECTED_RUN_IDENTITY_SHA256,
            "generation_id": EXPECTED_GENERATION_ID,
            "identity_population_sha256": EXPECTED_IDENTITY_POPULATION_SHA256,
            "signature_population_sha256": EXPECTED_SIGNATURE_POPULATION_SHA256,
        },
        "inputs": {
            **inputs,
            "historical_artifact": HISTORICAL_RECEIPT,
            "comparison_artifact": comparison["comparison_artifact"],
        },
        "source_identity": _source_identity(run),
        "source_facts": SOURCE_FACTS,
        "shards": sorted(manifest["shards"].values(), key=lambda s: s["chapter"]),
        "census": census,
        "cases": cases,
        "units": units,
        "classes": _classes(units),
        "replay": replay,
        "limitations": LIMITATIONS,
    }
    _verify_external_sources(yale_root, rulespec_root, engine_binary, run)
    _same(_producer_sources(repo_root, run), producer, "producer after full proof")
    _same(_small_inputs(repo_root)[3], inputs, "small inputs after full proof")
    _same(
        foundation.file_receipt(comparison_path),
        comparison["comparison_artifact"],
        "comparison artifact after full proof",
    )
    _check_historical_file(historical_artifact)
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
    historical_artifact: Path = DEFAULT_HISTORICAL_ARTIFACT,
    rulespec_root: Path = DEFAULT_RULESPEC_ROOT,
    engine_binary: Path = DEFAULT_ENGINE,
    yale_root: Path = DEFAULT_YALE_ROOT,
) -> tuple[dict, Callable[[], None]]:
    proof_inputs = _ProofInputs()
    with proof_inputs.capture_foundation():
        document = _build_receipt_impl(
            repo_root=repo_root,
            historical_artifact=historical_artifact,
            rulespec_root=rulespec_root,
            engine_binary=engine_binary,
            yale_root=yale_root,
        )
    proof_inputs.discard_ephemeral("tariff-steel-scope-proof-")
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
    historical_artifact: Path = DEFAULT_HISTORICAL_ARTIFACT,
    rulespec_root: Path = DEFAULT_RULESPEC_ROOT,
    engine_binary: Path = DEFAULT_ENGINE,
    yale_root: Path = DEFAULT_YALE_ROOT,
    _return_transaction: bool = False,
) -> dict | tuple[dict, Callable[[], None]]:
    transaction = _build_receipt_transaction(
        repo_root=repo_root,
        historical_artifact=historical_artifact,
        rulespec_root=rulespec_root,
        engine_binary=engine_binary,
        yale_root=yale_root,
    )
    return transaction if _return_transaction else transaction[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--historical-artifact", type=Path, default=DEFAULT_HISTORICAL_ARTIFACT
    )
    parser.add_argument("--rulespec-root", type=Path, default=DEFAULT_RULESPEC_ROOT)
    parser.add_argument("--engine-binary", type=Path, default=DEFAULT_ENGINE)
    parser.add_argument("--yale-root", type=Path, default=DEFAULT_YALE_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="Rescan and execute the engine, then require byte-identical committed proof",
    )
    mode.add_argument("--generate", action="store_true")
    args = parser.parse_args()
    output_path = args.output.resolve()
    with foundation._manifest_lock(foundation.EVAL_MANIFEST):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        previous_output = _output_snapshot(output_path)
        built = build_receipt(
            historical_artifact=args.historical_artifact,
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
                "units": 114,
                "signatures": 57,
                "receipt_payload_sha256": document["receipt_payload_sha256"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        ValueError,
        OSError,
        subprocess.CalledProcessError,
        yaml.YAMLError,
    ) as error:
        raise SystemExit(f"steel scope proof failed: {error}") from error
