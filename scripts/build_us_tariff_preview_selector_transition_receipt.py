#!/usr/bin/env python3
"""Prove fail-closed transitions from historical tariff preview selectors.

The immutable preview receipt records historical mismatch populations under
an older campaign flag schema.  This producer joins every historical selector
identity to the current evaluation and comparison, proves the exact current
population, and emits fresh child contracts rather than relabeling immutable
parents in place.  The six Section-232 parents retain their stricter legal
partition proof; CAFTA reclassification additionally requires its independent
reference-defect supersession receipt.

The original all-match equivalence producer remains the full-closure guard.
This producer does not weaken or replace its ``match=true`` requirement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import stat
import tempfile
from collections import Counter, defaultdict
from contextlib import contextmanager, nullcontext
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

try:
    from scripts import build_us_tariff_cafta_supersession_receipt as cafta
    from scripts import build_us_tariff_section232_equivalence_receipt as full
    from scripts import build_us_tariff_preview_disposition_receipt as preview_builder
    from scripts import us_tariff_schedule_campaign as campaign
except ModuleNotFoundError:  # Direct execution from scripts/.
    import build_us_tariff_cafta_supersession_receipt as cafta
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
CAFTA_SELECTOR_ID = cafta.CAFTA_SELECTOR_ID
CAFTA_SUPERSESSION_RECEIPT = cafta.DEFAULT_OUTPUT

# Producer-independent snapshot of all 18 immutable preview selectors.  Like
# the original Section-232 pin, it excludes mutable producer receipts while
# including the complete selector contracts, line sets, source receipts, and
# census selected by ``EXPECTED_SELECTOR_UNITS``.
EXPECTED_PREVIEW_ALL_SELECTOR_SNAPSHOT_SHA256 = (
    "4c6a0074bae1ff88ceeedc8b6e8c0b28eb829670c5a4e1a1edbb210be382dba6"
)
EXPECTED_PARENT_IDS = frozenset(preview_builder.EXPECTED_SELECTOR_UNITS)

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
        original_sha256 = full.sha256
        original_file_receipt = full.file_receipt
        full.sha256 = self.sha256
        full.file_receipt = self.file_receipt
        try:
            yield
        finally:
            full.sha256 = original_sha256
            full.file_receipt = original_file_receipt


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


def _valid_delta_bound(value: Any, *, selector_id: str) -> dict[str, Any]:
    require(
        isinstance(value, dict) and set(value) in ({"sign"}, {"values"}),
        f"preview selector delta bound is malformed: {selector_id}",
    )
    if "sign" in value:
        require(
            value["sign"] in {"pos", "neg"},
            f"preview selector delta sign is malformed: {selector_id}",
        )
    else:
        values = value["values"]
        require(
            isinstance(values, list)
            and bool(values)
            and all(
                isinstance(item, (int, float))
                and not isinstance(item, bool)
                and math.isfinite(item)
                for item in values
            )
            and values == sorted(set(values)),
            f"preview selector delta values are malformed: {selector_id}",
        )
    return value


def _delta_matches(value: float, bound: dict[str, Any]) -> bool:
    if "sign" in bound:
        return (
            value > full.TOLERANCE
            if bound["sign"] == "pos"
            else value < -full.TOLERANCE
        )
    return any(abs(value - expected) <= full.TOLERANCE for expected in bound["values"])


def _validate_preview(
    path: Path,
    *,
    expected_snapshot_sha256: str,
    expected_selector_units: dict[str, int],
    expected_producer: dict[str, Any] | None = None,
) -> tuple[
    dict[str, Any],
    dict[str, dict[str, Any]],
    dict[str, frozenset[str]],
    dict[str, Any],
    dict[str, Any],
]:
    """Validate an immutable preview selector set without §232-only bounds."""

    preview = full.load_json(path)
    require(
        preview.get("schema") == full.PREVIEW_SCHEMA
        and preview.get("verdict") == "PASS",
        "preview disposition receipt is not a PASS v1 receipt",
    )
    without_digest = dict(preview)
    payload_sha256 = without_digest.pop("receipt_payload_sha256", None)
    require(
        payload_sha256 == full.canonical_sha256(without_digest),
        "preview payload digest drift",
    )
    if expected_producer is None:
        expected_producer = {
            "script": full.file_receipt(
                preview_builder.PRODUCER_SOURCE, relative_to=REPO_ROOT
            ),
            "campaign_classifier": full.file_receipt(
                preview_builder.CAMPAIGN_SOURCE, relative_to=REPO_ROOT
            ),
        }
    require(
        preview.get("producer") == expected_producer,
        "preview receipt producer drift",
    )
    require(
        full.canonical_sha256(
            full.preview_section232_snapshot(preview, expected_selector_units)
        )
        == expected_snapshot_sha256,
        "immutable preview all-selector snapshot drift",
    )

    inputs = preview.get("inputs")
    require(isinstance(inputs, dict), "preview input receipts are malformed")
    historical_receipt = full._valid_receipt(
        inputs.get(full.HISTORICAL_LOGICAL_PATH),
        label=full.HISTORICAL_LOGICAL_PATH,
    )
    selected_receipt = full._valid_receipt(
        inputs.get(full.SELECTED_LOGICAL_PATH),
        label=full.SELECTED_LOGICAL_PATH,
    )
    require(
        historical_receipt["path"] == full.HISTORICAL_LOGICAL_PATH
        and selected_receipt["path"] == full.SELECTED_LOGICAL_PATH,
        "preview input logical paths drifted",
    )

    raw_selectors = preview.get("selectors")
    raw_line_sets = preview.get("line_sets")
    require(
        isinstance(raw_selectors, list) and isinstance(raw_line_sets, dict),
        "preview selectors or line sets are malformed",
    )
    selector_fields = {
        "id",
        "logical_class",
        "disposition",
        "attribution",
        "expected_units",
        "expected_signature_count",
        "expected_signature_population_sha256",
        "match",
    }
    selectors: dict[str, dict[str, Any]] = {}
    line_sets: dict[str, frozenset[str]] = {}
    for item in raw_selectors:
        require(
            isinstance(item, dict) and set(item) == selector_fields,
            "preview selector contract fields are malformed",
        )
        selector_id = item.get("id")
        require(
            isinstance(selector_id, str)
            and selector_id in expected_selector_units
            and selector_id not in selectors,
            f"preview selector id is unexpected or duplicated: {selector_id}",
        )
        require(
            all(
                isinstance(item.get(field), str) and bool(item[field])
                for field in ("logical_class", "disposition", "attribution")
            )
            and item.get("expected_units") == expected_selector_units[selector_id]
            and isinstance(item.get("expected_signature_count"), int)
            and not isinstance(item["expected_signature_count"], bool)
            and 0 < item["expected_signature_count"] <= item["expected_units"]
            and isinstance(item.get("expected_signature_population_sha256"), str)
            and full.HEX64.fullmatch(item["expected_signature_population_sha256"])
            is not None,
            f"preview selector ruling or census is malformed: {selector_id}",
        )
        match = item.get("match")
        require(
            isinstance(match, dict)
            and set(match) == {"slot", "line_set", "delta"}
            and match.get("slot") in {"brazil_section_301", "forced_labor_section_301"},
            f"preview selector match is malformed: {selector_id}",
        )
        _valid_delta_bound(match["delta"], selector_id=selector_id)
        line_set_name = match.get("line_set")
        line_receipt = raw_line_sets.get(line_set_name)
        require(
            isinstance(line_set_name, str)
            and line_set_name.startswith("preview-1311-")
            and isinstance(line_receipt, dict)
            and set(line_receipt)
            == {"width", "value_count", "values_sha256", "values"},
            f"preview selector line set is missing or malformed: {selector_id}",
        )
        values = line_receipt.get("values")
        require(
            line_receipt.get("width") == 10
            and isinstance(values, list)
            and values == sorted(set(values))
            and all(
                isinstance(value, str) and len(value) == 10 and value.isdigit()
                for value in values
            )
            and line_receipt.get("value_count") == len(values)
            and line_receipt.get("values_sha256") == full.values_sha256(values)
            and line_set_name not in line_sets,
            f"preview selector line-set receipt drifted: {selector_id}",
        )
        selectors[selector_id] = item
        line_sets[line_set_name] = frozenset(values)

    require(
        set(selectors) == set(expected_selector_units)
        and len(line_sets) == len(selectors),
        "preview receipt does not contain exactly the expected selector set",
    )
    census = preview.get("census")
    require(
        isinstance(census, dict)
        and census.get("per_selector") == expected_selector_units
        and census.get("total") == sum(expected_selector_units.values()),
        "preview selector census disagrees with contracts",
    )
    return preview, selectors, line_sets, historical_receipt, selected_receipt


def _validated_fresh_flag_names(
    *, repo_root: Path, run_identity: dict[str, Any]
) -> tuple[frozenset[str], Path, dict[str, Any]]:
    """Derive the exact fresh row schema from the receipted input contract."""

    binding = run_identity.get("input_contract")
    require(
        isinstance(binding, dict)
        and set(binding) == {"path", "bytes", "sha256", "schema"}
        and isinstance(binding.get("path"), str)
        and bool(binding["path"])
        and isinstance(binding.get("bytes"), int)
        and not isinstance(binding["bytes"], bool)
        and binding["bytes"] >= 0
        and isinstance(binding.get("sha256"), str)
        and full.HEX64.fullmatch(binding["sha256"]) is not None
        and binding.get("schema") == campaign.INPUT_CONTRACT_SCHEMA,
        "evaluation run input-contract binding is malformed",
    )
    contract_path = full._resolve_receipted_path(binding["path"], repo_root)
    contract_file = full.file_receipt(contract_path, relative_to=repo_root)
    require(
        {**contract_file, "schema": binding["schema"]} == binding,
        "evaluation run input-contract file drift",
    )
    contract = full.load_json(contract_path)
    emitted = contract.get("emitted_entry_flags")
    dropped = contract.get("expected_dropped_entry_flags")
    require(
        contract.get("schema") == campaign.INPUT_CONTRACT_SCHEMA
        and contract.get("verdict") == "PASS"
        and isinstance(emitted, list)
        and all(isinstance(name, str) and name.startswith("entry_") for name in emitted)
        and emitted == sorted(set(emitted))
        and isinstance(dropped, list)
        and dropped == sorted(campaign.EXPECTED_DROPPED_ENTRY_FLAGS)
        and set(dropped) <= set(emitted)
        and contract.get("entry_flag_producers")
        == run_identity.get("entry_flag_producers")
        and contract.get("reference_assumptions")
        == run_identity.get("reference_assumptions")
        and contract.get("rulespec") == run_identity.get("rulespec")
        and contract.get("engine") == run_identity.get("engine"),
        "declared input contract does not bind the fresh flag schema",
    )
    fresh_flag_names = frozenset(emitted) - frozenset(dropped)
    require(bool(fresh_flag_names), "receipted fresh flag schema is empty")
    return fresh_flag_names, contract_path, contract_file


def _row_matches_selector(
    row: dict[str, Any],
    *,
    match: dict[str, Any],
    line_sets: dict[str, frozenset[str]],
) -> bool:
    context = row.get("context")
    if not isinstance(context, dict) or not isinstance(context.get("hts10"), str):
        return False
    delta = full._finite_number(row.get("delta"), label="selector delta")
    return (
        row.get("slot") == match["slot"]
        and context["hts10"] in line_sets[match["line_set"]]
        and _delta_matches(delta, match["delta"])
    )


def _load_historical_units(
    *,
    path: Path,
    expected_receipt: dict[str, Any],
    selectors: dict[str, dict[str, Any]],
    line_sets: dict[str, frozenset[str]],
    expected_selector_units: dict[str, int],
) -> tuple[
    dict[tuple[str, str], dict[str, Any]],
    dict[str, list[dict[str, Any]]],
    int,
]:
    """Load all preview parents, including negative and exact-value deltas."""

    require(
        path.is_file()
        and path.stat().st_size == expected_receipt["bytes"]
        and full.sha256(path) == expected_receipt["sha256"],
        "historical target mismatch artifact does not match immutable preview",
    )
    units: dict[tuple[str, str], dict[str, Any]] = {}
    identities: dict[str, list[dict[str, Any]]] = defaultdict(list)
    signature_populations: dict[str, Counter[str]] = defaultdict(Counter)
    rows_scanned = 0
    for row in full._iter_jsonl_gzip(path):
        rows_scanned += 1
        matches = [
            selector_id
            for selector_id, selector in selectors.items()
            if _row_matches_selector(row, match=selector["match"], line_sets=line_sets)
        ]
        require(
            len(matches) <= 1,
            f"historical preview selector overlap: {matches}",
        )
        if not matches:
            continue
        selector_id = matches[0]
        new_disagreement = row.get("new_disagreement")
        old_target_class = row.get("old_target_class")
        require(
            new_disagreement is None or isinstance(new_disagreement, bool),
            f"historical preview new-disagreement state is malformed: {row.get('case_id')}",
        )
        require(
            old_target_class is None
            or (isinstance(old_target_class, str) and bool(old_target_class)),
            f"historical preview old-target class is malformed: {row.get('case_id')}",
        )
        identity = full._identity(row, label="historical")
        key = full._identity_key(identity)
        require(key not in units, f"duplicate historical preview identity: {key}")
        actual = full._finite_number(row.get("actual"), label="historical actual")
        delta = full._finite_number(row.get("delta"), label="historical delta")
        require(
            abs((actual - identity["expected"]) - delta) <= full.TOLERANCE
            and abs(delta) > full.TOLERANCE,
            f"historical preview mismatch arithmetic drift: {key}",
        )
        context = row.get("context")
        require(
            isinstance(context, dict) and isinstance(context.get("flags"), dict),
            f"historical preview flag vector is malformed: {key}",
        )
        signature = campaign.mismatch_signature(row)
        signature_populations[selector_id][signature] += 1
        units[key] = {"selector": selector_id, "identity": identity}
        identities[selector_id].append(identity)

    census = {selector_id: len(identities[selector_id]) for selector_id in selectors}
    require(
        census == expected_selector_units,
        f"historical preview identity census drift: {census}",
    )
    require(
        rows_scanned == sum(expected_selector_units.values()),
        "historical preview contains unclassified rows",
    )
    for selector_id, selector in selectors.items():
        population = signature_populations[selector_id]
        require(
            len(population) == selector["expected_signature_count"]
            and campaign.signature_population_sha256(population.items())
            == selector["expected_signature_population_sha256"],
            f"historical preview signature population drift: {selector_id}",
        )
    return units, dict(identities), rows_scanned


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
                    if (row.get("effective_date") or "1900-01-01") <= interval_start
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
        derivative_hits = [prefix for prefix in derivative if hts10.startswith(prefix)]
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
            and (flags[NOTE16_METAL_CHAPTER_FLAG] or flags[NOTE16_WEIGHT_INPUT])
        )
        or (
            flags["entry_is_s232_note16_c_ix_derivative_aluminum_candidate"]
            and (flags[NOTE16_METAL_CHAPTER_FLAG] or flags[NOTE16_WEIGHT_INPUT])
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


def _child_ruling(parent_id: str, pattern: tuple[str, ...]) -> dict[str, str]:
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
        "logical_class": (f"section232-{family}-{slug}-conditional-reference-behavior"),
        "disposition": "explained_residual",
        "attribution": "reference-behavior",
    }


def _fresh_rebind_child_ruling(
    parent_id: str, parent: dict[str, Any]
) -> dict[str, str]:
    if parent_id == CAFTA_SELECTOR_ID:
        return {
            "id": "cafta-52i-yale-reference-defect",
            "logical_class": "cafta-52i-yale-reference-defect",
            "disposition": "upstream_engine_gap",
            "attribution": "reference-defect",
        }
    return {
        "id": f"{parent_id}-fresh-signature-rebind",
        "logical_class": parent["logical_class"],
        "disposition": parent["disposition"],
        "attribution": parent["attribution"],
    }


def _actual_file_receipt(receipt: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    path = full._resolve_receipted_path(receipt["path"], repo_root)
    relative_to = None if Path(receipt["path"]).is_absolute() else repo_root
    return full.file_receipt(path, relative_to=relative_to)


def _validated_cafta_supersession_receipt(
    *,
    path: Path,
    repo_root: Path,
    producer_source: Path,
    preview_file: dict[str, Any],
    preview: dict[str, Any],
    preview_payload_sha256: str,
    historical_receipt: dict[str, Any],
    selected_receipt: dict[str, Any],
    manifest_file: dict[str, Any],
    comparison_file: dict[str, Any],
    comparison_artifact: dict[str, Any],
    manifest: dict[str, Any],
    comparison: dict[str, Any],
    historical_identity_population_sha256: str,
    fresh_identity_population_sha256: str,
) -> dict[str, Any]:
    """Validate and reduce the independent CAFTA proof for transition evidence."""

    receipt_file = full.file_receipt(path, relative_to=repo_root)
    receipt = full.load_json(path)
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
    require(
        set(receipt) == expected_fields
        and receipt.get("schema") == cafta.SCHEMA
        and receipt.get("verdict") == "PASS",
        "CAFTA supersession receipt is not a complete PASS receipt",
    )
    without_digest = dict(receipt)
    payload_sha256 = without_digest.pop("receipt_payload_sha256", None)
    require(
        isinstance(payload_sha256, str)
        and full.HEX64.fullmatch(payload_sha256) is not None
        and payload_sha256 == full.canonical_sha256(without_digest),
        "CAFTA supersession receipt payload digest drift",
    )
    expected_producer = {
        "script": full.file_receipt(producer_source, relative_to=repo_root)
    }
    identity_helper = full.file_receipt(cafta.FOUNDATION_SOURCE, relative_to=repo_root)
    require(
        receipt.get("producer") == expected_producer
        and identity_helper["sha256"] == cafta.EXPECTED_FOUNDATION_SHA256,
        "CAFTA supersession receipt producer drift",
    )

    inputs = receipt.get("inputs")
    expected_input_names = {
        "immutable_preview_receipt",
        "historical_target_mismatch_artifact",
        "evaluation_manifest",
        "comparison_receipt",
        "comparison_artifact",
        "declared_input_contract",
        "reference_provenance",
        "reference_integrity_receipt",
        "selected_panel_extractor",
    }
    require(
        isinstance(inputs, dict) and set(inputs) == expected_input_names,
        "CAFTA supersession receipt inputs are malformed",
    )
    shared_inputs = {
        "immutable_preview_receipt": preview_file,
        "historical_target_mismatch_artifact": historical_receipt,
        "evaluation_manifest": manifest_file,
        "comparison_receipt": comparison_file,
        "comparison_artifact": comparison_artifact,
    }
    require(
        all(inputs.get(name) == value for name, value in shared_inputs.items()),
        "CAFTA supersession receipt is bound to different transition evidence",
    )
    for name in expected_input_names - set(shared_inputs):
        input_receipt = full._valid_receipt(inputs.get(name), label=f"CAFTA {name}")
        require(
            _actual_file_receipt(input_receipt, repo_root=repo_root) == input_receipt,
            f"CAFTA supersession input changed: {name}",
        )

    bindings = receipt.get("bindings")
    run_identity = manifest.get("run_identity")
    chapters = run_identity.get("chapters") if isinstance(run_identity, dict) else None
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
    require(
        isinstance(bindings, dict)
        and isinstance(run_identity, dict)
        and isinstance(chapters, dict)
        and bool(chapters)
        and run_identity.get("selected_population") == selected_receipt
        and isinstance(campaign_source, dict)
        and bindings.get("preview_receipt_payload_sha256") == preview_payload_sha256
        and bindings.get("preview_cafta_snapshot_sha256")
        == cafta.EXPECTED_PREVIEW_CAFTA_SNAPSHOT_SHA256
        and bindings.get("rulespec") == run_identity.get("rulespec")
        and bindings.get("campaign_evaluator") == campaign_evaluator
        and bindings.get("selected_population_sha256") == selected_receipt["sha256"]
        and bindings.get("generation_id") == comparison.get("generation_id")
        and bindings.get("run_identity_sha256") == comparison.get("run_identity_sha256")
        and bindings.get("evaluation_manifest_sha256")
        == comparison.get("evaluation_manifest_sha256")
        and bindings.get("fresh_campaign_classifier_sha256")
        == campaign_source.get("sha256")
        and bindings.get("preview_campaign_classifier_sha256")
        == campaign_source.get("sha256")
        and bindings.get("campaign_producer_identity_required") is False
        and bindings.get("evaluation_shard_engine_errors") == 0
        and bindings.get("observed_evaluation_record_errors") == 0
        and bindings.get("comparison_receipt_engine_errors") == 0
        and bindings.get("evaluated_chapters") == len(chapters)
        and isinstance(bindings.get("evaluated_cases"), int)
        and not isinstance(bindings["evaluated_cases"], bool)
        and bindings["evaluated_cases"] > 0
        and bindings.get("evaluated_cases") == bindings.get("observed_evaluated_cases")
        and bindings.get("reference_compared_field") == "statutory_rate_s301fl",
        "CAFTA supersession receipt runtime binding drift",
    )

    zero_errors = receipt.get("zero_error_proof")
    require(
        zero_errors
        == {
            "evaluation_shard_engine_errors": 0,
            "observed_evaluation_record_errors": 0,
            "comparison_receipt_engine_errors": 0,
            "comparison_artifact_engine_error_rows": 0,
        },
        "CAFTA supersession receipt does not prove zero engine errors",
    )
    predicate_proof = receipt.get("axiom_predicate_proof")
    require(
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
        and predicate_proof.get("predicates")
        == {name: False for name in cafta.CAFTA_INPUTS}
        and predicate_proof.get("all_joined_actual_case_feeds_false_false") is True
        and predicate_proof.get("joined_fresh_evaluation_records")
        == cafta.EXPECTED_CAFTA_UNITS
        and predicate_proof.get("chapter_contracts_checked") == len(chapters)
        and predicate_proof.get("contract_sha256")
        == inputs["declared_input_contract"]["sha256"]
        and predicate_proof.get("scope")
        == "all campaign cases in all 100 compiled chapters"
        and predicate_proof.get("actual_case_feed_projection_sha256")
        == campaign.CAFTA_EXPECTED_ACTUAL_CASE_FEED_PROJECTION_SHA256,
        "CAFTA supersession receipt predicate proof drift",
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
    require(
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
        and fresh_rows_scanned == campaign._comparison_observation_count(comparison)
        and census.get("cafta_units") == cafta.EXPECTED_CAFTA_UNITS
        and census.get("cafta_signatures") == cafta.EXPECTED_CAFTA_SIGNATURES
        and census.get("origin_units") == cafta.EXPECTED_ORIGIN_UNITS,
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
    projection_hashes = (
        "historical_mismatch_projection_sha256",
        "historical_defect_projection_sha256",
        "fresh_defect_projection_sha256",
    )
    require(
        isinstance(supersession, dict)
        and set(supersession) == supersession_fields
        and supersession.get("authorized_disposition_after_pass")
        == "upstream_engine_gap"
        and supersession.get("authorized_attribution_after_pass") == "reference-defect"
        and supersession.get("historical_identity_population_sha256")
        == historical_identity_population_sha256
        and supersession.get("fresh_identity_population_sha256")
        == fresh_identity_population_sha256
        and historical_identity_population_sha256
        == campaign.CAFTA_EXPECTED_IDENTITY_POPULATION_SHA256
        and fresh_identity_population_sha256
        == campaign.CAFTA_EXPECTED_IDENTITY_POPULATION_SHA256
        and historical_identity_population_sha256 == fresh_identity_population_sha256
        and all(
            isinstance(supersession.get(name), str)
            and full.HEX64.fullmatch(supersession[name]) is not None
            for name in projection_hashes
        )
        and supersession.get("historical_mismatch_projection_sha256")
        == campaign.CAFTA_EXPECTED_HISTORICAL_MISMATCH_PROJECTION_SHA256
        and supersession.get("historical_defect_projection_sha256")
        == campaign.CAFTA_EXPECTED_DEFECT_PROJECTION_SHA256
        and supersession.get("fresh_defect_projection_sha256")
        == campaign.CAFTA_EXPECTED_DEFECT_PROJECTION_SHA256
        and supersession.get("joined_historical_units") == cafta.EXPECTED_CAFTA_UNITS
        and supersession.get("fresh_mismatching_units") == cafta.EXPECTED_CAFTA_UNITS
        and all(
            supersession.get(name) == 0
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
    require(
        definition == cafta.EXPECTED_DEFINITION,
        "CAFTA supersession receipt lacks bounded defect evidence",
    )
    campaign._validate_cafta_yale_defect_evidence(yale_defect)
    require(
        full.file_receipt(path, relative_to=repo_root) == receipt_file
        and full.file_receipt(producer_source, relative_to=repo_root)
        == expected_producer["script"]
        and full.file_receipt(cafta.FOUNDATION_SOURCE, relative_to=repo_root)
        == identity_helper,
        "CAFTA supersession receipt or producer changed during validation",
    )
    return {"file": receipt_file, "payload": receipt}


def _scan_fresh_transitions(
    *,
    path: Path,
    comparison: dict[str, Any],
    historical_units: dict[tuple[str, str], dict[str, Any]],
    source_eval_units: dict[tuple[str, str], dict[str, Any]],
    selectors: dict[str, dict[str, Any]],
    line_sets: dict[str, frozenset[str]],
    parent_ids: set[str],
    expected_fresh_flag_names: frozenset[str],
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
            "fresh_identities": [],
            "rebind_population": Counter(),
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
        require(key not in found, f"duplicate fresh preview identity: {key}")
        found.add(key)
        identity = full._identity(row, label="fresh")
        require(
            identity == historical["identity"],
            f"fresh preview legal identity drift: {key}",
        )
        source_eval = source_eval_units.get(key)
        require(
            isinstance(source_eval, dict),
            f"fresh preview cell lacks source evaluation: {key}",
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
        parent_id = historical["selector"]
        state = parent_state[parent_id]
        raw_flags = row["context"].get("flags")
        require(
            isinstance(raw_flags, dict)
            and set(raw_flags) == expected_fresh_flag_names
            and all(type(value) is bool for value in raw_flags.values()),
            f"fresh preview flag schema drift: {key}",
        )
        if not parent_id.startswith("section232-"):
            require(
                matched is False,
                f"fresh non-Section-232 selector unexpectedly matches: {key}",
            )
            require(
                abs(delta) > tolerance
                and _row_matches_selector(
                    row,
                    match=selectors[parent_id]["match"],
                    line_sets=line_sets,
                ),
                f"fresh non-Section-232 population escaped its immutable parent: {key}",
            )
            signature = campaign.mismatch_signature(row)
            state["residual"][signature] += 1
            state["rebind_population"][signature] += 1
            state["fresh_identities"].append(
                {"selector": parent_id, "identity": identity}
            )
            continue

        flags = _typed_flags(raw_flags, key=key)
        require(
            flags[NOTE16_WEIGHT_INPUT],
            f"fresh Section-232 row lost the receipted Yale metal-weight assumption: {key}",
        )
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
        f"fresh comparison is missing {len(missing)} historical preview identities",
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


def _fresh_rebind_transition_item(
    *,
    parent_id: str,
    parent: dict[str, Any],
    state: dict[str, Any],
    cafta_proof: dict[str, Any] | None,
) -> tuple[dict[str, Any], Counter[str], str]:
    residual: Counter[str] = state["residual"]
    rebind_population: Counter[str] = state["rebind_population"]
    residual_units = sum(residual.values())
    require(
        state["matches"] == 0
        and residual == rebind_population
        and residual_units == parent["expected_units"]
        and not state["patterns"]
        and not state["child_populations"]
        and len(state["fresh_identities"]) == residual_units,
        f"fresh non-Section-232 transition does not conserve: {parent_id}",
    )
    require(
        (parent_id == CAFTA_SELECTOR_ID) == (cafta_proof is not None),
        f"CAFTA supersession proof presence drift: {parent_id}",
    )
    ruling = _fresh_rebind_child_ruling(parent_id, parent)
    child_units = sum(rebind_population.values())
    child_digest = campaign.signature_population_sha256(rebind_population.items())
    child = {
        **ruling,
        "parent_id": parent_id,
        "expected_units": child_units,
        "expected_signature_count": len(rebind_population),
        "expected_signature_population_sha256": child_digest,
        "match": parent["match"],
    }
    evidence = {
        "classification": (
            "cafta-reference-defect-receipted-fresh-signature"
            if parent_id == CAFTA_SELECTOR_ID
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
            ruling["id"]: {
                "units": child_units,
                "signature_count": len(rebind_population),
                "signature_population_sha256": child_digest,
            }
        },
        **(
            {"cafta_supersession_receipt": cafta_proof}
            if cafta_proof is not None
            else {}
        ),
    }
    return (
        {
            "parent_id": parent_id,
            "parent_contract": parent,
            "status": "superseded",
            "historical_units": parent["expected_units"],
            "fresh_matching_units": 0,
            "fresh_residual_population": {
                "units": residual_units,
                "signature_count": len(residual),
                "signature_population_sha256": (
                    campaign.signature_population_sha256(residual.items())
                ),
            },
            "children": [child],
            "evidence": evidence,
        },
        rebind_population,
        ruling["id"],
    )


def _transition_items(
    *,
    selectors: dict[str, dict[str, Any]],
    parent_state: dict[str, dict[str, Any]],
    expected_parent_patterns: dict[str, frozenset[tuple[str, ...]]],
    expected_fallback_hts10: frozenset[str] | None,
    yale_source_receipt: dict[str, Any],
    cafta_proof: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    require(
        set(parent_state) == set(selectors),
        "preview transition parent set drift",
    )
    require(
        set(expected_parent_patterns) <= set(selectors)
        and all(
            parent_id.startswith("section232-")
            for parent_id in expected_parent_patterns
        ),
        "Section-232 expected-pattern parent set drift",
    )
    require(
        (CAFTA_SELECTOR_ID in selectors) == (cafta_proof is not None),
        "CAFTA transition proof coverage drift",
    )
    transitions: list[dict[str, Any]] = []
    child_ids = set(selectors)
    all_child_signatures: set[str] = set()
    all_defect_fallback_hts10: set[str] = set()
    total_defect_units = 0
    for parent_id in sorted(selectors):
        parent = selectors[parent_id]
        state = parent_state[parent_id]
        if not parent_id.startswith("section232-"):
            item, population, child_id = _fresh_rebind_transition_item(
                parent_id=parent_id,
                parent=parent,
                state=state,
                cafta_proof=(cafta_proof if parent_id == CAFTA_SELECTOR_ID else None),
            )
            require(
                child_id not in child_ids,
                f"preview transition child id collides: {child_id}",
            )
            require(
                not (all_child_signatures & set(population)),
                f"preview transition child populations overlap: {parent_id}",
            )
            child_ids.add(child_id)
            all_child_signatures.update(population)
            transitions.append(item)
            continue
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
        if parent_id in expected_parent_patterns:
            require(
                status == "superseded"
                and observed_patterns == expected_parent_patterns[parent_id],
                f"fresh Section-232 transition pattern drift: {parent_id}: "
                f"{sorted(map(_pattern_name, observed_patterns))}",
            )
        else:
            require(
                status == "retired" and not child_populations and not patterns,
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
            require(
                ruling["id"] not in child_ids,
                f"preview transition child id collides: {ruling['id']}",
            )
            require(
                not (all_child_signatures & set(population)),
                f"preview transition child populations overlap: {parent_id}",
            )
            child_ids.add(ruling["id"])
            all_child_signatures.update(population)
            child_units = sum(population.values())
            child_digest = campaign.signature_population_sha256(population.items())
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
                len(source_identities)
                == sum(defect_population.values())
                == sum(source_arms.values()),
                f"Yale annex defect source proof does not conserve: {parent_id}",
            )
            source_union: Counter[str] = Counter()
            per_arm: dict[str, dict[str, Any]] = {}
            for arm, population in sorted(source_populations.items()):
                require(
                    arm
                    in {
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


def _build_receipt_impl(
    *,
    repo_root: Path = REPO_ROOT,
    producer_source: Path = PRODUCER_SOURCE,
    campaign_source: Path = CAMPAIGN_SOURCE,
    full_closure_guard_source: Path = FULL_CLOSURE_GUARD_SOURCE,
    preview_receipt_path: Path = full.PREVIEW_RECEIPT,
    historical_artifact_path: Path = full.HISTORICAL_ARTIFACT,
    eval_manifest_path: Path = full.EVAL_MANIFEST,
    comparison_receipt_path: Path = full.COMPARISON_RECEIPT,
    cafta_receipt_path: Path = CAFTA_SUPERSESSION_RECEIPT,
    cafta_producer_source: Path = cafta.PRODUCER_SOURCE,
    expected_preview_snapshot_sha256: str = EXPECTED_PREVIEW_ALL_SELECTOR_SNAPSHOT_SHA256,
    expected_selector_units: dict[str, int] = preview_builder.EXPECTED_SELECTOR_UNITS,
    expected_parent_ids: frozenset[str] = EXPECTED_PARENT_IDS,
    expected_parent_patterns: dict[
        str, frozenset[tuple[str, ...]]
    ] = EXPECTED_PARENT_PATTERNS,
    expected_fallback_hts10: frozenset[str] | None = (
        EXPECTED_LEGACY_DERIVATIVE_FALLBACK_HTS10
    ),
    yale_root: Path = preview_builder.DEFAULT_YALE_ROOT,
    expected_yale_parser_receipt: dict[str, Any] = YALE_PARSER_RECEIPT,
    expected_reference_assumptions: dict[str, Any] | None = None,
    manifest_locked: bool = False,
) -> dict[str, Any]:
    require(
        set(expected_selector_units) == expected_parent_ids
        and bool(expected_parent_ids),
        "expected preview transition parent set drift",
    )
    if expected_reference_assumptions is None:
        expected_reference_assumptions = {
            "yale_note16_metal_weight": (
                campaign._yale_note16_weight_assumption_identity()
            )
        }
    require(
        isinstance(expected_reference_assumptions, dict)
        and set(expected_reference_assumptions) == {"yale_note16_metal_weight"}
        and isinstance(expected_reference_assumptions["yale_note16_metal_weight"], dict)
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
    preview_builder_file = full.file_receipt(
        preview_builder.PRODUCER_SOURCE, relative_to=repo_root
    )
    preview_producer = {
        "script": preview_builder_file,
        "campaign_classifier": producer["campaign_classifier"],
    }
    preview_file = full.file_receipt(preview_receipt_path, relative_to=repo_root)
    preview, selectors, line_sets, historical_receipt, selected_receipt = (
        _validate_preview(
            preview_receipt_path,
            expected_snapshot_sha256=expected_preview_snapshot_sha256,
            expected_selector_units=expected_selector_units,
            expected_producer=preview_producer,
        )
    )
    yale_annex_classifier, yale_source_receipt = _verified_yale_annex_classifier(
        yale_root=yale_root,
        preview=preview,
        expected_parser_receipt=expected_yale_parser_receipt,
    )
    historical_units, historical_identities, historical_rows_scanned = (
        _load_historical_units(
            path=historical_artifact_path,
            expected_receipt=historical_receipt,
            selectors=selectors,
            line_sets=line_sets,
            expected_selector_units=expected_selector_units,
        )
    )

    lock = nullcontext() if manifest_locked else full._manifest_lock(eval_manifest_path)
    with lock:
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
        reference_assumptions = manifest["run_identity"].get("reference_assumptions")
        require(
            isinstance(rulespec, dict)
            and bool(rulespec)
            and isinstance(entry_flag_producers, dict)
            and bool(entry_flag_producers)
            and reference_assumptions == expected_reference_assumptions,
            "evaluation run lacks RuleSpec, entry-flag, or reference-assumption provenance",
        )
        (
            expected_fresh_flag_names,
            input_contract_path,
            input_contract_file,
        ) = _validated_fresh_flag_names(
            repo_root=repo_root,
            run_identity=manifest["run_identity"],
        )
        parent_state, comparison_audit = _scan_fresh_transitions(
            path=artifact_path,
            comparison=comparison,
            historical_units=historical_units,
            source_eval_units=source_eval_units,
            selectors=selectors,
            line_sets=line_sets,
            parent_ids=set(selectors),
            expected_fresh_flag_names=expected_fresh_flag_names,
            yale_annex_classifier=yale_annex_classifier,
        )
        cafta_proof: dict[str, Any] | None = None
        if CAFTA_SELECTOR_ID in selectors:
            cafta_parent = selectors[CAFTA_SELECTOR_ID]
            require(
                cafta_parent["expected_units"] == cafta.EXPECTED_CAFTA_UNITS
                and sum(parent_state[CAFTA_SELECTOR_ID]["rebind_population"].values())
                == cafta.EXPECTED_CAFTA_UNITS,
                "fresh CAFTA parent unit census drift",
            )
            historical_cafta_digest = full.population_sha256(
                {
                    "selector": CAFTA_SELECTOR_ID,
                    "identity": identity,
                }
                for identity in historical_identities[CAFTA_SELECTOR_ID]
            )
            fresh_cafta_digest = full.population_sha256(
                parent_state[CAFTA_SELECTOR_ID]["fresh_identities"]
            )
            cafta_proof = _validated_cafta_supersession_receipt(
                path=cafta_receipt_path,
                repo_root=repo_root,
                producer_source=cafta_producer_source,
                preview_file=preview_file,
                preview=preview,
                preview_payload_sha256=preview["receipt_payload_sha256"],
                historical_receipt=historical_receipt,
                selected_receipt=selected_receipt,
                manifest_file=manifest_file,
                comparison_file=comparison_file,
                comparison_artifact=comparison["comparison_artifact"],
                manifest=manifest,
                comparison=comparison,
                historical_identity_population_sha256=(historical_cafta_digest),
                fresh_identity_population_sha256=fresh_cafta_digest,
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
            )
            and full.file_receipt(input_contract_path, relative_to=repo_root)
            == input_contract_file,
            "evaluation/comparison evidence changed during transition proof",
        )

    transitions = _transition_items(
        selectors=selectors,
        parent_state=parent_state,
        expected_parent_patterns=expected_parent_patterns,
        expected_fallback_hts10=expected_fallback_hts10,
        yale_source_receipt=yale_source_receipt,
        cafta_proof=cafta_proof,
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
        historical_rows_scanned == len(historical_units)
        and comparison_audit["joined_historical_units"] == len(historical_units),
        "preview transition scan census is malformed",
    )
    payload["receipt_payload_sha256"] = full.canonical_sha256(payload)
    require(
        full.file_receipt(producer_source, relative_to=repo_root) == producer["script"]
        and full.file_receipt(preview_builder.PRODUCER_SOURCE, relative_to=repo_root)
        == preview_builder_file
        and full.file_receipt(campaign_source, relative_to=repo_root)
        == producer["campaign_classifier"]
        and full.file_receipt(full_closure_guard_source, relative_to=repo_root)
        == producer["full_closure_guard"]
        and full.file_receipt(preview_receipt_path, relative_to=repo_root)
        == preview_file
        and historical_artifact_path.stat().st_size == historical_receipt["bytes"]
        and full.sha256(historical_artifact_path) == historical_receipt["sha256"]
        and full.file_receipt(input_contract_path, relative_to=repo_root)
        == input_contract_file
        and (
            cafta_proof is None
            or full.file_receipt(cafta_receipt_path, relative_to=repo_root)
            == cafta_proof["file"]
        ),
        "transition producer or preview evidence changed during receipt build",
    )
    return payload


def _build_receipt_transaction(
    *,
    repo_root: Path = REPO_ROOT,
    producer_source: Path = PRODUCER_SOURCE,
    campaign_source: Path = CAMPAIGN_SOURCE,
    full_closure_guard_source: Path = FULL_CLOSURE_GUARD_SOURCE,
    preview_receipt_path: Path = full.PREVIEW_RECEIPT,
    historical_artifact_path: Path = full.HISTORICAL_ARTIFACT,
    eval_manifest_path: Path = full.EVAL_MANIFEST,
    comparison_receipt_path: Path = full.COMPARISON_RECEIPT,
    cafta_receipt_path: Path = CAFTA_SUPERSESSION_RECEIPT,
    cafta_producer_source: Path = cafta.PRODUCER_SOURCE,
    expected_preview_snapshot_sha256: str = EXPECTED_PREVIEW_ALL_SELECTOR_SNAPSHOT_SHA256,
    expected_selector_units: dict[str, int] = preview_builder.EXPECTED_SELECTOR_UNITS,
    expected_parent_ids: frozenset[str] = EXPECTED_PARENT_IDS,
    expected_parent_patterns: dict[
        str, frozenset[tuple[str, ...]]
    ] = EXPECTED_PARENT_PATTERNS,
    expected_fallback_hts10: frozenset[str] | None = (
        EXPECTED_LEGACY_DERIVATIVE_FALLBACK_HTS10
    ),
    yale_root: Path = preview_builder.DEFAULT_YALE_ROOT,
    expected_yale_parser_receipt: dict[str, Any] = YALE_PARSER_RECEIPT,
    expected_reference_assumptions: dict[str, Any] | None = None,
    manifest_locked: bool = False,
) -> tuple[dict[str, Any], Callable[[], None]]:
    proof_inputs = _ProofInputs()
    uses_live_reference_assumption = expected_reference_assumptions is None
    pinned_note16_identity: dict[str, Any] | None = None
    with proof_inputs.capture_foundation():
        if uses_live_reference_assumption:
            note16_receipt_file = proof_inputs.file_receipt(
                campaign.YALE_NOTE16_WEIGHT_ASSUMPTION,
                relative_to=repo_root,
            )
            note16_producer_file = proof_inputs.file_receipt(
                campaign.YALE_NOTE16_WEIGHT_ASSUMPTION_PRODUCER,
                relative_to=repo_root,
            )
            pinned_note16_identity = campaign._yale_note16_weight_assumption_identity()
            require(
                {
                    name: pinned_note16_identity[name]
                    for name in ("path", "bytes", "sha256")
                }
                == note16_receipt_file,
                "Yale Note 16 assumption receipt identity drift",
            )
            note16_receipt = json.loads(
                campaign.YALE_NOTE16_WEIGHT_ASSUMPTION.read_text()
            )
            require(
                isinstance(note16_receipt, dict)
                and note16_receipt.get("producer") == note16_producer_file,
                "Yale Note 16 assumption producer drift",
            )
            proof_inputs.require_current()
            effective_reference_assumptions = {
                "yale_note16_metal_weight": pinned_note16_identity
            }
        else:
            effective_reference_assumptions = expected_reference_assumptions
        payload = _build_receipt_impl(
            repo_root=repo_root,
            producer_source=producer_source,
            campaign_source=campaign_source,
            full_closure_guard_source=full_closure_guard_source,
            preview_receipt_path=preview_receipt_path,
            historical_artifact_path=historical_artifact_path,
            eval_manifest_path=eval_manifest_path,
            comparison_receipt_path=comparison_receipt_path,
            cafta_receipt_path=cafta_receipt_path,
            cafta_producer_source=cafta_producer_source,
            expected_preview_snapshot_sha256=expected_preview_snapshot_sha256,
            expected_selector_units=expected_selector_units,
            expected_parent_ids=expected_parent_ids,
            expected_parent_patterns=expected_parent_patterns,
            expected_fallback_hts10=expected_fallback_hts10,
            yale_root=yale_root,
            expected_yale_parser_receipt=expected_yale_parser_receipt,
            expected_reference_assumptions=effective_reference_assumptions,
            manifest_locked=manifest_locked,
        )
        preview = full.load_json(preview_receipt_path)
        _classifier, pinned_yale_source = _verified_yale_annex_classifier(
            yale_root=yale_root,
            preview=preview,
            expected_parser_receipt=expected_yale_parser_receipt,
        )
    emitted_yale_sources = {
        full.canonical_sha256(source)
        for transition in payload["transitions"]
        if isinstance(transition.get("evidence"), dict)
        for proof in [transition["evidence"].get("yale_annex_defect_source_proof")]
        if isinstance(proof, dict)
        for source in [proof.get("pinned_yale_source")]
        if isinstance(source, dict)
    }
    require(
        emitted_yale_sources <= {full.canonical_sha256(pinned_yale_source)},
        "transition receipt contains inconsistent pinned Yale source evidence",
    )
    proof_inputs.seal()

    def require_current() -> None:
        with proof_inputs.capture_foundation():
            proof_inputs.require_current()
            if uses_live_reference_assumption:
                require(
                    campaign._yale_note16_weight_assumption_identity()
                    == pinned_note16_identity,
                    "Yale Note 16 assumption changed during transition publication",
                )
            preview = full.load_json(preview_receipt_path)
            _classifier, current_yale_source = _verified_yale_annex_classifier(
                yale_root=yale_root,
                preview=preview,
                expected_parser_receipt=expected_yale_parser_receipt,
            )
            require(
                current_yale_source == pinned_yale_source,
                "pinned Yale source changed during transition publication",
            )
            proof_inputs.require_current()

    require_current()
    return payload, require_current


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
    cafta_receipt_path: Path = CAFTA_SUPERSESSION_RECEIPT,
    cafta_producer_source: Path = cafta.PRODUCER_SOURCE,
    expected_preview_snapshot_sha256: str = EXPECTED_PREVIEW_ALL_SELECTOR_SNAPSHOT_SHA256,
    expected_selector_units: dict[str, int] = preview_builder.EXPECTED_SELECTOR_UNITS,
    expected_parent_ids: frozenset[str] = EXPECTED_PARENT_IDS,
    expected_parent_patterns: dict[
        str, frozenset[tuple[str, ...]]
    ] = EXPECTED_PARENT_PATTERNS,
    expected_fallback_hts10: frozenset[str] | None = (
        EXPECTED_LEGACY_DERIVATIVE_FALLBACK_HTS10
    ),
    yale_root: Path = preview_builder.DEFAULT_YALE_ROOT,
    expected_yale_parser_receipt: dict[str, Any] = YALE_PARSER_RECEIPT,
    expected_reference_assumptions: dict[str, Any] | None = None,
    manifest_locked: bool = False,
    _return_transaction: bool = False,
) -> dict[str, Any] | tuple[dict[str, Any], Callable[[], None]]:
    transaction = _build_receipt_transaction(
        repo_root=repo_root,
        producer_source=producer_source,
        campaign_source=campaign_source,
        full_closure_guard_source=full_closure_guard_source,
        preview_receipt_path=preview_receipt_path,
        historical_artifact_path=historical_artifact_path,
        eval_manifest_path=eval_manifest_path,
        comparison_receipt_path=comparison_receipt_path,
        cafta_receipt_path=cafta_receipt_path,
        cafta_producer_source=cafta_producer_source,
        expected_preview_snapshot_sha256=expected_preview_snapshot_sha256,
        expected_selector_units=expected_selector_units,
        expected_parent_ids=expected_parent_ids,
        expected_parent_patterns=expected_parent_patterns,
        expected_fallback_hts10=expected_fallback_hts10,
        yale_root=yale_root,
        expected_yale_parser_receipt=expected_yale_parser_receipt,
        expected_reference_assumptions=expected_reference_assumptions,
        manifest_locked=manifest_locked,
    )
    return transaction if _return_transaction else transaction[0]


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
        "--cafta-receipt", type=Path, default=CAFTA_SUPERSESSION_RECEIPT
    )
    parser.add_argument(
        "--yale-root", type=Path, default=preview_builder.DEFAULT_YALE_ROOT
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    eval_manifest_path = args.eval_manifest.resolve()
    output_path = args.output.resolve()
    with full._manifest_lock(eval_manifest_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        previous_output = _output_snapshot(output_path)
        built = build_receipt(
            preview_receipt_path=args.preview_receipt.resolve(),
            historical_artifact_path=args.historical_artifact.resolve(),
            eval_manifest_path=eval_manifest_path,
            comparison_receipt_path=args.comparison_receipt.resolve(),
            cafta_receipt_path=args.cafta_receipt.resolve(),
            yale_root=args.yale_root.resolve(),
            manifest_locked=True,
            _return_transaction=True,
        )
        if isinstance(built, tuple):
            receipt, require_current = built
        else:  # Preserve test and downstream monkeypatch compatibility.
            receipt, require_current = built, lambda: None
        output = full.render(receipt).encode()
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
        full.render(
            {
                "verdict": receipt["verdict"],
                "output": str(output_path),
                "output_sha256": hashlib.sha256(output).hexdigest(),
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
