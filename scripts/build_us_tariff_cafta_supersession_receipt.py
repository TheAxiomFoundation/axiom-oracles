#!/usr/bin/env python3
"""Prove the bounded CAFTA preview class is a Yale reference defect.

The historical preview contains 17,404 Note-52(i)-labelled mismatching cells.
This post-comparison producer proves, without changing campaign evaluation
inputs, that the same cells remain mismatches when both statutory entry facts
are explicitly fed false, and that Yale's zero is caused by a pinned tidy-eval
name collision that promotes every ``condition=fta`` row to ``full``.

The receipt supports reclassifying this *preview discrepancy* only.  It does
not establish that any real entry is a GN-29(d)(v) good or is entered free of
duty under DR-CAFTA.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import shutil
import stat
import subprocess
import tempfile
from collections import Counter
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Any, Callable, Iterable

import yaml

from scripts import build_us_tariff_section232_equivalence_receipt as foundation
from scripts import us_tariff_schedule_campaign as campaign


REPO_ROOT = Path(__file__).resolve().parent.parent
PRODUCER_SOURCE = Path(__file__).resolve()
FOUNDATION_SOURCE = Path(foundation.__file__).resolve()
EXPECTED_FOUNDATION_SHA256 = (
    "34e92d18ef1dcba5a2ace50b6d2dd2bee348530e7b9ad628a3aaed3bcf353441"
)
PREVIEW_RECEIPT = foundation.PREVIEW_RECEIPT
HISTORICAL_ARTIFACT = foundation.HISTORICAL_ARTIFACT
EVAL_MANIFEST = foundation.EVAL_MANIFEST
COMPARISON_RECEIPT = foundation.COMPARISON_RECEIPT
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "reference/us-tariff-schedule/cafta-reference-defect-supersession-receipt.json"
)
DEFAULT_YALE_ROOT = Path("/Users/maxghenis/TheAxiomFoundation/_tariff-yale")
PROVENANCE = REPO_ROOT / "reference/us-tariff-schedule/provenance.json"
INTEGRITY_RECEIPT = REPO_ROOT / "reference/us-tariff-schedule/integrity-receipt.json"
SELECTED_EXTRACTOR = REPO_ROOT / "scripts/extract_us_tariff_schedule.R"

SCHEMA = "axiom_oracles.us_tariff_schedule.cafta_reference_defect_supersession.v1"
PREVIEW_SCHEMA = foundation.PREVIEW_SCHEMA
INPUT_CONTRACT_SCHEMA = campaign.INPUT_CONTRACT_SCHEMA
EVAL_RUN_IDENTITY_SCHEMA = campaign.EVAL_RUN_IDENTITY_SCHEMA
EVAL_MANIFEST_SCHEMA = campaign.EVAL_MANIFEST_SCHEMA
COMPARISON_SCHEMA = campaign.COMPARISON_SCHEMA
REFERENCE_PROVENANCE_SCHEMA = "axiom_oracles.us_tariff_schedule_reference.v1"
EXPECTED_RULESPEC_COMMIT = "4f591c4267063094cc6da9d590872ea982940b81"
EXPECTED_CAFTA_UNITS = 17_404
EXPECTED_CAFTA_SIGNATURES = 8_702
CAFTA_SELECTOR_ID = "cafta-52i-deferred"
CAFTA_INPUTS = (
    "entry_is_entered_free_of_duty_under_dr_cafta",
    "entry_is_general_note_29_d_v_textile_or_apparel_good",
)
ISO2_TO_CENSUS_COUNTRY = {
    "CR": "2230",
    "DO": "2470",
    "GT": "2050",
    "HN": "2150",
    "NI": "2190",
    "SV": "2110",
}
EXPECTED_ORIGIN_UNITS = {
    "CR": 1_260,
    "DO": 128,
    "GT": 108,
    "HN": 120,
    "NI": 15_636,
    "SV": 152,
}
EXPECTED_YALE_COMMIT = campaign.PREVIEW_YALE_COMMIT
EXPECTED_YALE_TREE = campaign.PREVIEW_YALE_TREE
EXPECTED_YALE_FILES = {
    "config/policy_params.yaml": "5f3d79b192b9fb6079e5ad10a1969e12f397567fc9f89d4e202403116ecb6346",
    "resources/mfn_exemption_shares.csv": "9505d04e441386ac08348de663c151743fdf3c537947cbe7ceab43b4d21381e1",
    "resources/s301fl_final_common_exemptions.csv": "15b5e352cd810af33b90699bb595010f5aca43ea10de25ba1b2c6239acc96054",
    "resources/s301fl_final_country_exemptions.csv": "a38f8e42e9615b58dc09fd8a661b4a0fdb9d12e2121342a657fae69450215280",
    "resources/s232_pharma_products.csv": "eb5f888ef3967c699b4f85618859d3556a9552e7d636ead2bbdc09256edcca04",
    "src/model/authority_adapter.R": "91d6adab284dc823fa4c541910d6c4a74494b3a09f3e5fb6b6a71a98e3b1288a",
    "src/pipeline/06_calculate_rates.R": "2620a122159c11cc2b116786925ccbc6d801cb274982034cd8105657ae13a76a",
}
EXPECTED_RULE_HIT_SOURCE_SHA256 = (
    "3257ccacb37c6d7ced57e112a3f0fc63015758df50afb5e08646790e6f617d3a"
)
EXPECTED_RULE_HIT_USE_SHA256 = (
    "ccd1a2de00c1747444734437acb2567d59c43e39047f05ba98c21791ce52a61f"
)
EXPECTED_STATUTORY_CAPTURE_SHA256 = (
    "28ad1849ca43d61431e282b090b465e518da98978f90d143627815b50e57cd1c"
)
EXPECTED_USE_CONDITIONED_SHA256 = (
    "3093f85841b5209701730688ab822677928ad10e1c2b3a6d479fa274332534e0"
)
EXPECTED_CHAPTER98_PRECAPTURE_SHA256 = (
    "9950e34ca8d3bbd481985b04ffdf80ae828247df62155b0eb6ce773c26208e2b"
)
EXPECTED_ADAPTER_RATE_TYPE_SHA256 = (
    "b4b03adb11756fd9ff2dda56313c0aea5dddf4511e0c1d65a1f2ce19caf05ebf"
)
EXPECTED_ADAPTER_EXEMPT_SHA256 = (
    "0237e0ee3978687f967b8cdaabbb3c4721984aac7899a4ee36bb7e294bf06869"
)
EXPECTED_ADAPTER_BUILD_SHA256 = (
    "06d6b8a59363f668fa2bcae8a35e157241b19fc1e8a254fd41dfa0f99b1db805"
)
EXPECTED_RDS_SHA256 = "724a0be1dce45d423d5ce599bb56f2ab81cbf78b637ba59a3287738bfc488a35"
EXPECTED_R_VERSION = "4.3.0"
EXPECTED_DPLYR_VERSION = "1.1.2"
TOLERANCE = foundation.TOLERANCE

# Producer-independent snapshot of the exact historical CAFTA population.  It
# deliberately excludes disposition/attribution so the proof survives the
# reclassification it is intended to authorize.
EXPECTED_PREVIEW_CAFTA_SNAPSHOT_SHA256 = (
    "531fce05b3c6ac32980fb0e570140ccde0b277d674b6f107724fab76f7ee57c3"
)
EXPECTED_DEFINITION = campaign.CAFTA_EXPECTED_DEFINITION


def require(condition: bool, message: str) -> None:
    foundation.require(condition, message)


def render(value: Any) -> str:
    return foundation.render(value)


def canonical_sha256(value: Any) -> str:
    return foundation.canonical_sha256(value)


def population_sha256(values: Iterable[dict[str, Any]]) -> str:
    return foundation.population_sha256(values)


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


def _require_file_receipt_unchanged(
    path: Path,
    receipt: dict[str, Any],
    *,
    label: str,
    relative_to: Path | None = None,
) -> None:
    require(
        foundation.file_receipt(path, relative_to=relative_to) == receipt,
        f"{label} changed during CAFTA proof",
    )


def cafta_preview_snapshot(preview: dict[str, Any]) -> dict[str, Any]:
    selectors = [
        item
        for item in preview.get("selectors", [])
        if isinstance(item, dict) and item.get("id") == CAFTA_SELECTOR_ID
    ]
    require(len(selectors) == 1, "preview does not contain exactly one CAFTA selector")
    selector = selectors[0]
    match = selector.get("match")
    require(isinstance(match, dict), "preview CAFTA selector match is malformed")
    line_set_name = match.get("line_set")
    line_sets = preview.get("line_sets")
    require(
        isinstance(line_sets, dict)
        and isinstance(line_set_name, str)
        and line_set_name in line_sets,
        "preview CAFTA line set is missing",
    )
    inputs = preview.get("inputs")
    require(isinstance(inputs, dict), "preview input receipts are malformed")
    selected_inputs = {
        path: inputs.get(path)
        for path in (
            foundation.HISTORICAL_LOGICAL_PATH,
            foundation.SELECTED_LOGICAL_PATH,
        )
    }
    return {
        "schema": preview.get("schema"),
        "inputs": selected_inputs,
        "selector": {
            field: selector.get(field)
            for field in (
                "id",
                "logical_class",
                "expected_units",
                "expected_signature_count",
                "expected_signature_population_sha256",
                "match",
            )
        },
        "line_set": {line_set_name: line_sets[line_set_name]},
        "census": {
            "selector_units": preview.get("census", {})
            .get("per_selector", {})
            .get(CAFTA_SELECTOR_ID),
            "origin_units": preview.get("evidence_census", {}).get(
                "cafta_units_by_origin"
            ),
        },
    }


def _validate_preview(
    path: Path,
) -> tuple[
    dict[str, Any],
    dict[str, dict[str, Any]],
    dict[str, frozenset[str]],
    dict[str, Any],
    dict[str, Any],
]:
    preview = foundation.load_json(path)
    require(
        preview.get("schema") == PREVIEW_SCHEMA and preview.get("verdict") == "PASS",
        "preview disposition receipt is not a PASS v1 receipt",
    )
    without_digest = dict(preview)
    payload_sha256 = without_digest.pop("receipt_payload_sha256", None)
    require(
        payload_sha256 == canonical_sha256(without_digest),
        "preview payload digest drift",
    )
    preview_builder = (
        REPO_ROOT / "scripts/build_us_tariff_preview_disposition_receipt.py"
    )
    require(
        preview.get("producer", {}).get("script")
        == foundation.file_receipt(preview_builder, relative_to=REPO_ROOT),
        "preview CAFTA classifier producer drift",
    )
    require(
        canonical_sha256(cafta_preview_snapshot(preview))
        == EXPECTED_PREVIEW_CAFTA_SNAPSHOT_SHA256,
        "immutable preview CAFTA snapshot drift",
    )
    selector = next(
        item for item in preview["selectors"] if item.get("id") == CAFTA_SELECTOR_ID
    )
    require(
        selector.get("logical_class") == CAFTA_SELECTOR_ID
        and selector.get("expected_units") == EXPECTED_CAFTA_UNITS
        and selector.get("expected_signature_count") == EXPECTED_CAFTA_SIGNATURES
        and selector.get("match", {}).get("slot") == "forced_labor_section_301"
        and selector.get("match", {}).get("delta") == {"sign": "pos"},
        "preview CAFTA selector contract drift",
    )
    line_set_name = selector["match"]["line_set"]
    line_set = preview["line_sets"][line_set_name]
    values = line_set.get("values")
    require(
        line_set.get("width") == 10
        and isinstance(values, list)
        and values == sorted(set(values))
        and line_set.get("value_count") == len(values)
        and line_set.get("values_sha256") == foundation.values_sha256(values),
        "preview CAFTA line-set receipt drift",
    )
    require(
        preview.get("evidence_census", {}).get("cafta_units_by_origin")
        == EXPECTED_ORIGIN_UNITS,
        "preview CAFTA origin census drift",
    )
    inputs = preview["inputs"]
    historical_receipt = foundation._valid_receipt(
        inputs.get(foundation.HISTORICAL_LOGICAL_PATH),
        label=foundation.HISTORICAL_LOGICAL_PATH,
    )
    selected_receipt = foundation._valid_receipt(
        inputs.get(foundation.SELECTED_LOGICAL_PATH),
        label=foundation.SELECTED_LOGICAL_PATH,
    )
    return (
        preview,
        {CAFTA_SELECTOR_ID: selector},
        {line_set_name: frozenset(values)},
        historical_receipt,
        selected_receipt,
    )


def _validate_input_contract(
    *, repo_root: Path, run_identity: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    receipt = run_identity.get("input_contract")
    require(
        isinstance(receipt, dict)
        and set(receipt) == {"path", "bytes", "sha256", "schema"}
        and receipt.get("schema") == INPUT_CONTRACT_SCHEMA,
        "evaluation input-contract receipt is malformed",
    )
    path = foundation._resolve_receipted_path(receipt["path"], repo_root)
    require(
        path.stat().st_size == receipt["bytes"]
        and foundation.sha256(path) == receipt["sha256"],
        "evaluation input-contract artifact drift",
    )
    contract = foundation.load_json(path)
    require(
        contract.get("schema") == INPUT_CONTRACT_SCHEMA
        and contract.get("verdict") == "PASS",
        "declared input contract is not a current-schema PASS receipt",
    )
    neutral_inputs = contract.get("neutral_boolean_inputs")
    require(
        contract.get("neutral_boolean_value") is False
        and isinstance(neutral_inputs, list)
        and all(name in neutral_inputs for name in CAFTA_INPUTS),
        "CAFTA entry predicates are not explicitly neutral false",
    )
    chapters = contract.get("chapters")
    run_chapters = run_identity.get("chapters")
    require(
        isinstance(chapters, list)
        and isinstance(run_chapters, dict)
        and len(chapters) == 100,
        "input-contract chapter coverage drift",
    )
    chapter_ids = [
        chapter.get("chapter") if isinstance(chapter, dict) else None
        for chapter in chapters
    ]
    require(
        len(set(chapter_ids)) == len(chapter_ids)
        and chapter_ids == list(run_chapters)
        and set(chapter_ids) == set(run_chapters),
        "input-contract chapters do not bind uniquely to run identity",
    )
    for chapter in chapters:
        require(isinstance(chapter, dict), "input-contract chapter is malformed")
        feed = chapter.get("case_feed_inputs")
        require(
            isinstance(feed, list)
            and all(name in feed for name in CAFTA_INPUTS)
            and chapter.get("missing_declared_entry_inputs") == []
            and chapter.get("missing_reachable_inputs") == [],
            f"CAFTA predicate feed is incomplete in chapter {chapter.get('chapter')}",
        )
    proof = {
        "predicates": {name: False for name in CAFTA_INPUTS},
        "scope": "all campaign cases in all 100 compiled chapters",
        "contract_sha256": receipt["sha256"],
        "chapter_contracts_checked": len(chapters),
    }
    return foundation.file_receipt(path, relative_to=repo_root), proof


def _validate_reference_provenance(
    *, selected_receipt: dict[str, Any]
) -> dict[str, Any]:
    provenance_file = foundation.file_receipt(PROVENANCE, relative_to=REPO_ROOT)
    integrity_file = foundation.file_receipt(INTEGRITY_RECEIPT, relative_to=REPO_ROOT)
    extractor_file = foundation.file_receipt(SELECTED_EXTRACTOR, relative_to=REPO_ROOT)
    provenance = foundation.load_json(PROVENANCE)
    integrity = foundation.load_json(INTEGRITY_RECEIPT)
    require(
        provenance.get("schema") == REFERENCE_PROVENANCE_SCHEMA
        and provenance.get("yale_commit") == EXPECTED_YALE_COMMIT
        and provenance.get("rds_sha256") == EXPECTED_RDS_SHA256
        and provenance.get("extractor_sha256") == extractor_file["sha256"]
        and provenance.get("selected_extract_sha256") == selected_receipt["sha256"],
        "selected-panel provenance binding drift",
    )
    require(
        "statutory_rate_s301fl" in integrity.get("schema_columns", [])
        and "statutory_rate_s301fl" in integrity.get("statutory_columns", [])
        and integrity.get("duplicate_keys") == 0
        and integrity.get("interval_gaps_or_overlaps") == 0,
        "selected-panel statutory-field integrity drift",
    )
    return {
        "provenance": provenance_file,
        "integrity_receipt": integrity_file,
        "extractor": extractor_file,
        "rds_path": provenance["rds_path"],
        "rds_sha256": provenance["rds_sha256"],
        "compared_field": "statutory_rate_s301fl",
    }


def _extract_yale_defect_source(path: Path) -> dict[str, Any]:
    source = path.read_text()
    function_start = source.index("    rule_hit <- function(condition) {")
    function_end = source.index("\n\n    # Full §232-scope exclusion", function_start)
    function_source = source[function_start:function_end] + "\n"
    use_start = source.index("    country_full_hit <- rule_hit('full')", function_end)
    use_end = source.index("\n\n    fl_tbl <-", use_start)
    use_source = source[use_start:use_end] + "\n"
    function_sha256 = hashlib.sha256(function_source.encode()).hexdigest()
    use_sha256 = hashlib.sha256(use_source.encode()).hexdigest()
    statutory_start = source.index(
        "  # Save statutory rates for all non-232 authorities"
    )
    statutory_end = source.index("\n\n    n_adjusted <-", statutory_start)
    statutory_source = source[statutory_start:statutory_end] + "\n"
    statutory_sha256 = hashlib.sha256(statutory_source.encode()).hexdigest()
    use_conditioned_start = source.index(
        "    air_hit <- code_hit(common_air) | rule_hit('aircraft')"
    )
    use_conditioned_end = source.index(
        "\n\n    message('  Section 301 forced labor final action",
        use_conditioned_start,
    )
    use_conditioned_source = source[use_conditioned_start:use_conditioned_end] + "\n"
    use_conditioned_sha256 = hashlib.sha256(use_conditioned_source.encode()).hexdigest()
    chapter98_start = source.index(
        "  # 6b3. Chapter 98 secondary-classification treatment, ALL authorities."
    )
    chapter98_end = source.index(
        "\n\n  # Save statutory rates for all non-232 authorities", chapter98_start
    )
    chapter98_source = source[chapter98_start:chapter98_end] + "\n"
    chapter98_sha256 = hashlib.sha256(chapter98_source.encode()).hexdigest()
    require(
        function_sha256 == EXPECTED_RULE_HIT_SOURCE_SHA256
        and use_sha256 == EXPECTED_RULE_HIT_USE_SHA256
        and statutory_sha256 == EXPECTED_STATUTORY_CAPTURE_SHA256
        and use_conditioned_sha256 == EXPECTED_USE_CONDITIONED_SHA256
        and chapter98_sha256 == EXPECTED_CHAPTER98_PRECAPTURE_SHA256,
        "Yale rule_hit source or use-site drift",
    )
    require(
        "filter(.data$condition %in% condition)" in function_source
        and "country_full_hit <- rule_hit('full')" in use_source
        and "covered <- !common_full_hit & !country_full_hit" in use_source
        and "statutory_rate_s301fl      = rate_s301fl" in statutory_source
        and statutory_source.index("statutory_rate_s301fl")
        < statutory_source.index("rate_s301fl = if_else")
        and "rule_hit('aircraft')" in use_conditioned_source
        and "rule_hit('pharma')" in use_conditioned_source
        and "ch98_cols <- c('rate_301', 'rate_301_cs', 'rate_s301fl'"
        in chapter98_source
        and "startsWith(rates$hts10, code)" in chapter98_source,
        "Yale tidy-eval defect structure drift",
    )
    return {
        "rule_hit_function_sha256": function_sha256,
        "rule_hit_use_site_sha256": use_sha256,
        "statutory_capture_and_preference_scaling_sha256": statutory_sha256,
        "use_conditioned_scaling_sha256": use_conditioned_sha256,
        "chapter98_precapture_transforms_sha256": chapter98_sha256,
        "rule_hit_function_first_line": source[:function_start].count("\n") + 1,
        "rule_hit_use_site_first_line": source[:use_start].count("\n") + 1,
        "statutory_capture_first_line": source[:statutory_start].count("\n") + 1,
        "use_conditioned_first_line": source[:use_conditioned_start].count("\n") + 1,
        "chapter98_precapture_first_line": source[:chapter98_start].count("\n") + 1,
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


def _extract_yale_adapter_source(path: Path) -> dict[str, Any]:
    source = path.read_text()

    def block(start_marker: str, end_marker: str) -> tuple[str, int]:
        start = source.index(start_marker)
        end = source.index(end_marker, start)
        return source[start:end] + "\n", source[:start].count("\n") + 1

    rate_type, rate_type_line = block(
        ".resolve_s301fl_by_country <- function", "\n\n# Generic date-windowed"
    )
    exempt, exempt_line = block(
        "# Date-gated patented-pharma", "\n\n# Build the section_301_forced_labor"
    )
    build, build_line = block(
        ".build_section_301_forced_labor <- function",
        "\n\n# Build the section_301_brazil",
    )
    receipts = {
        "rate_and_type_resolvers_sha256": hashlib.sha256(
            rate_type.encode()
        ).hexdigest(),
        "exemption_resolver_sha256": hashlib.sha256(exempt.encode()).hexdigest(),
        "authority_builder_sha256": hashlib.sha256(build.encode()).hexdigest(),
    }
    require(
        receipts
        == {
            "rate_and_type_resolvers_sha256": EXPECTED_ADAPTER_RATE_TYPE_SHA256,
            "exemption_resolver_sha256": EXPECTED_ADAPTER_EXEMPT_SHA256,
            "authority_builder_sha256": EXPECTED_ADAPTER_BUILD_SHA256,
        }
        and "by_country_type <- function" in rate_type
        and "rep('surcharge'" in rate_type
        and "rep('floor'" in rate_type
        and "common$condition == 'aircraft'" in exempt
        and "common$condition == 'pharma'" in exempt
        and ".resolve_s301fl_exempt(cfg, effective_date)" in build,
        "Yale forced-labor adapter source drift",
    )
    return receipts | {
        "rate_and_type_resolvers_first_line": rate_type_line,
        "exemption_resolver_first_line": exempt_line,
        "authority_builder_first_line": build_line,
    }


def _validate_tidy_eval_reproduction_output(output: str) -> dict[str, Any]:
    fields: dict[str, str] = {}
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        require(
            bool(separator) and key not in fields, "malformed tidy-eval reproduction"
        )
        fields[key] = value
    require(
        fields
        == {
            "r_version": EXPECTED_R_VERSION,
            "dplyr_version": EXPECTED_DPLYR_VERSION,
            "dplyr_path": campaign.CAFTA_EXPECTED_DPLYR_TREE_RECEIPT["path"],
            "selected_conditions": "full,fta",
        },
        "tidy-eval name-collision reproduction drift",
    )
    return fields


def _directory_tree_receipt(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    require(resolved.is_dir(), f"missing runtime package tree: {resolved}")
    files = sorted(item for item in resolved.rglob("*") if item.is_file())
    total_bytes = 0
    manifest = hashlib.sha256()
    for item in files:
        size = item.stat().st_size
        total_bytes += size
        manifest.update(
            (
                f"{item.relative_to(resolved).as_posix()}\t{size}\t"
                f"{foundation.sha256(item)}\n"
            ).encode()
        )
    return {
        "path": str(resolved),
        "file_count": len(files),
        "bytes": total_bytes,
        "manifest_sha256": manifest.hexdigest(),
    }


def _run_tidy_eval_reproduction() -> dict[str, Any]:
    rscript_value = shutil.which("Rscript")
    require(rscript_value is not None, "Rscript is required for tidy-eval reproduction")
    rscript = Path(rscript_value).resolve()
    rscript_receipt = foundation.file_receipt(rscript)
    require(
        rscript_receipt == campaign.CAFTA_EXPECTED_RSCRIPT_RECEIPT,
        "tidy-eval Rscript runtime drift",
    )
    runtime_receipt = _directory_tree_receipt(
        Path(campaign.CAFTA_EXPECTED_R_RUNTIME_TREE_RECEIPT["path"])
    )
    require(
        runtime_receipt == campaign.CAFTA_EXPECTED_R_RUNTIME_TREE_RECEIPT,
        "tidy-eval R runtime tree drift",
    )
    dplyr_receipt = _directory_tree_receipt(
        Path(campaign.CAFTA_EXPECTED_DPLYR_TREE_RECEIPT["path"])
    )
    require(
        dplyr_receipt == campaign.CAFTA_EXPECTED_DPLYR_TREE_RECEIPT,
        "tidy-eval dplyr runtime drift",
    )
    program = campaign.CAFTA_TIDY_EVAL_PROGRAM
    with tempfile.TemporaryDirectory(prefix="axiom-cafta-r-") as runtime_home:
        completed = subprocess.run(
            [str(rscript), "--vanilla", "-e", program],
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
    require(not completed.stderr, "tidy-eval reproduction emitted stderr")
    fields = _validate_tidy_eval_reproduction_output(completed.stdout)
    program_sha256 = hashlib.sha256(program.encode()).hexdigest()
    require(
        program_sha256 == campaign.CAFTA_EXPECTED_TIDY_EVAL_PROGRAM_SHA256,
        "tidy-eval reproduction program drift",
    )
    require(
        foundation.file_receipt(rscript) == rscript_receipt
        and _directory_tree_receipt(Path(runtime_receipt["path"])) == runtime_receipt
        and _directory_tree_receipt(Path(dplyr_receipt["path"])) == dplyr_receipt,
        "tidy-eval runtime changed during reproduction",
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


def _require_yale_sources_clean(yale_root: Path) -> None:
    relevant = sorted(EXPECTED_YALE_FILES)
    status = subprocess.run(
        ["git", "-C", str(yale_root), "status", "--porcelain=v1", "--", *relevant],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    require(not status, "relevant Yale tracked worktree files are dirty or untracked")


def _load_yale_defect(
    yale_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    revision = subprocess.run(
        ["git", "-C", str(yale_root), "rev-parse", "HEAD", "HEAD^{tree}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    require(
        revision == [EXPECTED_YALE_COMMIT, EXPECTED_YALE_TREE],
        "Yale checkout commit/tree drift",
    )
    _require_yale_sources_clean(yale_root)
    files: dict[str, Any] = {}
    for relative, expected_sha256 in EXPECTED_YALE_FILES.items():
        path = yale_root / relative
        receipt = foundation.file_receipt(path, relative_to=yale_root)
        require(receipt["sha256"] == expected_sha256, f"Yale source drift: {relative}")
        files[relative] = receipt

    country_rules: dict[str, set[tuple[str, str]]] = {}
    rules_path = yale_root / "resources/s301fl_final_country_exemptions.csv"
    with rules_path.open(newline="") as source:
        rows = csv.DictReader(source)
        require(
            rows.fieldnames == ["countries", "hts_code", "condition"],
            "Yale forced-labor exemption columns drift",
        )
        for row in rows:
            code = row["hts_code"]
            require(len(code) in {8, 10} and code.isdigit(), "malformed Yale FTA code")
            for country in row["countries"].split(";"):
                country_rules.setdefault(row["condition"], set()).add((country, code))

    common_rules: dict[str, set[str]] = {}
    common_path = yale_root / "resources/s301fl_final_common_exemptions.csv"
    with common_path.open(newline="") as source:
        rows = csv.DictReader(source)
        require(
            rows.fieldnames == ["hts_code", "condition"],
            "Yale forced-labor common exemption columns drift",
        )
        for row in rows:
            code = row["hts_code"]
            require(
                len(code) in {8, 10} and code.isdigit(), "malformed Yale common code"
            )
            common_rules.setdefault(row["condition"], set()).add(code)

    patented_pharma: set[str] = set()
    patent_path = yale_root / "resources/s232_pharma_products.csv"
    with patent_path.open(newline="") as source:
        rows = csv.DictReader(source)
        require(rows.fieldnames == ["hts10"], "Yale patented-pharma columns drift")
        for row in rows:
            code = row["hts10"]
            require(len(code) == 10 and code.isdigit(), "malformed Yale patent code")
            patented_pharma.add(code)

    policy = yaml.safe_load((yale_root / "config/policy_params.yaml").read_text())[
        "section_301_forced_labor"
    ]
    rate_10 = float(policy["rate_10"])
    rate_12_5 = float(policy["rate_12_5"])
    target_rates: dict[str, float] = {}
    rate_types: dict[str, str] = {}
    for tier_name, rate, rate_type in (
        ("tier_10pct", rate_10, "surcharge"),
        ("tier_12_5pct", rate_12_5, "surcharge"),
        ("tier_10pct_net_mfn", rate_10, "floor"),
        ("tier_12_5pct_net_mfn", rate_12_5, "floor"),
    ):
        for country in policy[tier_name]:
            target_rates[country] = rate
            rate_types[country] = rate_type
    require(
        {country for country in ISO2_TO_CENSUS_COUNTRY.values()} <= set(target_rates),
        "Yale CAFTA country-tier rates are incomplete",
    )
    source_proof = _extract_yale_defect_source(
        yale_root / "src/pipeline/06_calculate_rates.R"
    )
    adapter_proof = _extract_yale_adapter_source(
        yale_root / "src/model/authority_adapter.R"
    )
    reproduction = _run_tidy_eval_reproduction()
    model = {
        "fta_rules": country_rules.get("fta", set()),
        "intended_country_full_rules": country_rules.get("full", set()),
        "country_aircraft_rules": country_rules.get("aircraft", set()),
        "country_pharma_rules": country_rules.get("pharma", set()),
        "common_full_rules": common_rules.get("full", set())
        | common_rules.get("ex", set()),
        "common_aircraft_rules": common_rules.get("aircraft", set()),
        "common_pharma_rules": common_rules.get("pharma", set()),
        "patented_pharma": patented_pharma,
        "target_rates": target_rates,
        "rate_types": rate_types,
    }
    return model, {
        "commit": EXPECTED_YALE_COMMIT,
        "tree": EXPECTED_YALE_TREE,
        "files": dict(sorted(files.items())),
        "source_proof": source_proof,
        "adapter_source_proof": adapter_proof,
        "deterministic_minimal_reproduction": reproduction,
    }


def _revalidate_yale_evidence(yale_root: Path, receipt: dict[str, Any]) -> None:
    revision = subprocess.run(
        ["git", "-C", str(yale_root), "rev-parse", "HEAD", "HEAD^{tree}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    require(
        revision == [receipt["commit"], receipt["tree"]],
        "Yale checkout changed during CAFTA proof",
    )
    _require_yale_sources_clean(yale_root)
    for relative, expected in receipt["files"].items():
        _require_file_receipt_unchanged(
            yale_root / relative,
            expected,
            label=f"Yale source {relative}",
            relative_to=yale_root,
        )
    require(
        _extract_yale_defect_source(yale_root / "src/pipeline/06_calculate_rates.R")
        == receipt["source_proof"]
        and _extract_yale_adapter_source(yale_root / "src/model/authority_adapter.R")
        == receipt["adapter_source_proof"]
        and _run_tidy_eval_reproduction()
        == receipt["deterministic_minimal_reproduction"],
        "Yale source/runtime proof changed during CAFTA proof",
    )


def _replay_yale_defect(
    *,
    identity: dict[str, Any],
    actual: float,
    expected: float,
    delta: float,
    defect_model: dict[str, Any],
) -> dict[str, Any]:
    iso2 = identity["iso2"]
    country = ISO2_TO_CENSUS_COUNTRY.get(iso2)
    require(country is not None, f"unexpected CAFTA origin: {iso2}")
    hts10 = identity["hts10"]
    fta_rules = defect_model["fta_rules"]
    country_full_rules = defect_model["intended_country_full_rules"]
    country_aircraft_rules = defect_model["country_aircraft_rules"]
    country_pharma_rules = defect_model["country_pharma_rules"]
    common_full_rules = defect_model["common_full_rules"]
    common_aircraft_rules = defect_model["common_aircraft_rules"]
    common_pharma_rules = defect_model["common_pharma_rules"]
    patented_pharma = defect_model["patented_pharma"]
    target_rate = defect_model["target_rates"].get(country)
    rate_type = defect_model["rate_types"].get(country)
    country_keys = {(country, hts10[:8]), (country, hts10)}
    code_keys = {hts10[:8], hts10}
    require(
        bool(country_keys & fta_rules),
        f"historical CAFTA cell is absent from Yale condition=fta rules: {country}/{hts10}",
    )
    require(
        not (country_keys & country_full_rules)
        and not (country_keys & country_aircraft_rules)
        and not (country_keys & country_pharma_rules)
        and not (code_keys & common_full_rules)
        and not (code_keys & common_aircraft_rules)
        and not (code_keys & common_pharma_rules)
        and hts10 not in patented_pharma,
        f"historical CAFTA cell has a non-bug Yale exclusion: {country}/{hts10}",
    )
    require(
        target_rate is not None
        and rate_type == "surcharge"
        and not hts10.startswith("98")
        and abs(expected) <= TOLERANCE
        and abs(actual - target_rate) <= TOLERANCE
        and abs(delta - actual) <= TOLERANCE,
        f"Yale name-collision zero does not reproduce comparison cell: {identity['case_id']}",
    )
    return {
        "identity": identity,
        "country": country,
        "statutory_country_tier_rate": target_rate,
        "country_rate_type": rate_type,
        "axiom_neutral_fact_rate": actual,
        "yale_reference_defect_rate": expected,
        "delta": delta,
        "fta_rule_membership": True,
        "intended_country_full_rule_membership": False,
        "country_aircraft_rule_membership": False,
        "country_pharma_rule_membership": False,
        "common_full_rule_membership": False,
        "common_aircraft_rule_membership": False,
        "common_pharma_rule_membership": False,
        "patented_pharma_membership": False,
        "section232_precedence_cleared_by_preview_receipt": True,
        "chapter98_secondary_zeroing": False,
        "chapter98_value_basis_scaling": False,
        "rule_hit_full_includes_fta_row": True,
        "country_full_hit": True,
        "covered": False,
        "predicted_yale_rate_s301fl": 0.0,
        "corrected_yale_statutory_rate_s301fl": target_rate,
        "corrected_yale_matches_axiom": True,
    }


def _normalized_per_slot(value: Any) -> dict[str, dict[str, int]]:
    return foundation._normalized_per_slot(value)


def _validate_campaign_and_rulespec_runtime(
    run_identity: dict[str, Any],
) -> tuple[Path, Any, dict[str, Any]]:
    require(
        run_identity.get("schema") == EVAL_RUN_IDENTITY_SCHEMA,
        "evaluation run identity schema is stale",
    )
    require(
        campaign._campaign_evaluator_identity()
        == run_identity.get("campaign_evaluator"),
        "fresh campaign producer no longer matches evaluation run identity",
    )
    rulespec = run_identity.get("rulespec")
    require(
        isinstance(rulespec, dict)
        and set(rulespec)
        == {
            "root",
            "head_commit",
            "head_tree",
            "dirty",
            "tracked_worktree_diff_sha256",
            "untracked",
            "content_sha256",
        }
        and rulespec.get("head_commit") == EXPECTED_RULESPEC_COMMIT
        and rulespec.get("dirty") is False
        and rulespec.get("tracked_worktree_diff_sha256")
        == hashlib.sha256(b"").hexdigest()
        and rulespec.get("untracked") == [],
        "evaluation RuleSpec receipt is not the exact clean final checkout",
    )
    rulespec_root = Path(rulespec["root"]).resolve()
    require(
        campaign._rulespec_root_identity(rulespec_root) == rulespec,
        "current RuleSpec checkout differs from evaluation run identity",
    )
    entry_flags, producers = campaign._load_entry_flag_tool(rulespec_root)
    require(
        producers == run_identity.get("entry_flag_producers"),
        "current entry-flag producers differ from evaluation run identity",
    )
    return rulespec_root, entry_flags, producers


def _reconstruct_joined_cafta_feeds(
    *,
    run_identity: dict[str, Any],
    source_eval_units: dict[tuple[str, str], dict[str, Any]],
    entry_flags: Any,
    expected_units: int = EXPECTED_CAFTA_UNITS,
) -> list[dict[str, Any]]:
    chapters = run_identity["chapters"]
    projections: list[dict[str, Any]] = []
    for key, source_eval in source_eval_units.items():
        record = source_eval.get("evaluation_record")
        comparison_row = source_eval.get("comparison")
        require(
            isinstance(record, dict) and isinstance(comparison_row, dict),
            f"joined CAFTA source evaluation metadata is malformed: {key}",
        )
        chapter = record.get("chapter")
        probe = record.get("probe")
        country = record.get("country")
        identity = source_eval["identity"]
        require(
            isinstance(chapter, str)
            and chapter in chapters
            and isinstance(probe, str)
            and country == ISO2_TO_CENSUS_COUNTRY.get(identity["iso2"]),
            f"joined CAFTA source evaluation routing is malformed: {key}",
        )
        chapter_contract = chapters[chapter]
        feed, forwarded_flags = campaign._case_feed(
            {"hts10": identity["hts10"], "iso2": identity["iso2"]},
            {"hts_line": identity["hts_line"]},
            entry_flags,
            probe=probe,
            case_feed_inputs=chapter_contract["case_feed_inputs"],
        )
        require(
            forwarded_flags == comparison_row["context"]["flags"],
            f"reconstructed CAFTA entry flags differ from evaluation record: {key}",
        )
        actual_predicates = {name: feed.get(name) for name in CAFTA_INPUTS}
        require(
            actual_predicates == {name: False for name in CAFTA_INPUTS},
            f"joined CAFTA evaluation did not actually feed both predicates false: {key}",
        )
        projections.append(
            {
                "identity": identity,
                "chapter": chapter,
                "probe": probe,
                "actual_cafta_inputs": actual_predicates,
            }
        )
    require(
        len(projections) == expected_units,
        "joined CAFTA case-feed reconstruction census drift",
    )
    return projections


def _scan_fresh_reference_population(
    *,
    comparison_artifact: Path,
    comparison: dict[str, Any],
    historical_units: dict[tuple[str, str], dict[str, Any]],
    historical_rows: list[dict[str, Any]],
    source_eval_units: dict[tuple[str, str], dict[str, Any]],
    defect_model: dict[str, Any],
    expected_origin_units: dict[str, int] = EXPECTED_ORIGIN_UNITS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    historical_by_key = {
        foundation._identity_key(row["identity"]): row for row in historical_rows
    }
    require(
        len(historical_by_key) == len(historical_rows),
        "duplicate historical CAFTA projection identity",
    )
    found: set[tuple[str, str]] = set()
    per_slot: dict[str, Counter[str]] = {}
    defect_rows: list[dict[str, Any]] = []
    origin_census: Counter[str] = Counter()
    rows_scanned = 0
    engine_error_rows = 0
    tolerance = foundation._finite_number(
        comparison.get("tolerance"), label="comparison tolerance"
    )
    for row in foundation._iter_jsonl_gzip(comparison_artifact):
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
        per_slot.setdefault(slot, Counter())["match" if matched else "mismatch"] += 1
        if slot == "engine_error":
            engine_error_rows += 1
            continue
        key = (case_id, slot)
        historical = historical_units.get(key)
        if historical is None:
            continue
        require(key not in found, f"duplicate fresh CAFTA identity: {key}")
        found.add(key)
        identity = foundation._identity(row, label="fresh CAFTA")
        require(
            identity == historical["identity"],
            f"fresh CAFTA legal identity drift: {key}",
        )
        require(
            matched is False,
            f"CAFTA preview cell no longer has a reference discrepancy: {key}",
        )
        source_eval = source_eval_units.get(key)
        require(
            isinstance(source_eval, dict),
            f"fresh CAFTA cell lacks source evaluation: {key}",
        )
        source_row = source_eval["comparison"]
        current_flags = source_row["context"].get("flags")
        require(
            isinstance(current_flags, dict)
            and current_flags.get("entry_is_section_232_covered") is False,
            f"fresh CAFTA source record has Section-232 coverage: {key}",
        )
        actual = foundation._finite_number(
            row.get("actual"), label="fresh CAFTA actual"
        )
        expected = foundation._finite_number(
            row.get("expected"), label="fresh CAFTA expected"
        )
        delta = foundation._finite_number(row.get("delta"), label="fresh CAFTA delta")
        require(
            row.get("context") == source_row["context"]
            and source_row["match"] is False
            and abs(actual - source_row["actual"]) <= tolerance
            and abs(expected - source_row["expected"]) <= tolerance
            and abs(delta - source_row["delta"]) <= tolerance
            and abs((actual - expected) - delta) <= tolerance,
            f"fresh CAFTA comparison disagrees with source evaluation: {key}",
        )
        old = historical_by_key[key]
        require(
            abs(actual - old["historical_actual"]) <= tolerance
            and abs(delta - old["historical_delta"]) <= tolerance,
            f"fresh CAFTA discrepancy differs from immutable preview: {key}",
        )
        defect_rows.append(
            _replay_yale_defect(
                identity=identity,
                actual=actual,
                expected=expected,
                delta=delta,
                defect_model=defect_model,
            )
        )
        origin_census[identity["iso2"]] += 1
    require(
        engine_error_rows == 0, "fresh comparison artifact contains engine-error rows"
    )
    require(
        set(historical_units) == found,
        f"fresh comparison is missing {len(set(historical_units) - found)} CAFTA identities",
    )
    observed_per_slot = {
        slot: dict(counter) for slot, counter in sorted(per_slot.items())
    }
    require(
        observed_per_slot == _normalized_per_slot(comparison.get("per_slot")),
        "comparison artifact per-slot census disagrees with receipt",
    )
    require(
        dict(sorted(origin_census.items())) == expected_origin_units,
        "fresh CAFTA origin census drift",
    )
    return defect_rows, {
        "comparison_rows_scanned": rows_scanned,
        "joined_historical_units": len(found),
        "engine_error_rows": engine_error_rows,
        "fresh_mismatching_units": len(found),
        "fresh_matching_units": 0,
        "origin_units": dict(sorted(origin_census.items())),
    }


def _build_receipt_impl(
    *,
    repo_root: Path,
    producer_source: Path,
    preview_receipt_path: Path,
    historical_artifact_path: Path,
    eval_manifest_path: Path,
    comparison_receipt_path: Path,
    yale_root: Path,
    manifest_locked: bool = False,
) -> dict[str, Any]:
    producer = {
        "script": foundation.file_receipt(producer_source, relative_to=repo_root)
    }
    identity_helper = foundation.file_receipt(FOUNDATION_SOURCE, relative_to=repo_root)
    require(
        identity_helper["sha256"] == EXPECTED_FOUNDATION_SHA256,
        "identity helper source pin drift",
    )
    preview_file = foundation.file_receipt(preview_receipt_path, relative_to=repo_root)
    preview, selectors, line_sets, historical_receipt, selected_receipt = (
        _validate_preview(preview_receipt_path)
    )
    reference_provenance = _validate_reference_provenance(
        selected_receipt=selected_receipt
    )
    (
        historical_units,
        historical_identities,
        historical_projections,
        historical_scanned,
    ) = foundation._load_historical_units(
        path=historical_artifact_path,
        expected_receipt=historical_receipt,
        selectors=selectors,
        line_sets=line_sets,
        expected_selector_units={CAFTA_SELECTOR_ID: EXPECTED_CAFTA_UNITS},
    )
    defect_model, yale_receipt = _load_yale_defect(yale_root)
    historical_defect_rows = [
        _replay_yale_defect(
            identity=row["identity"],
            actual=row["historical_actual"],
            expected=row["identity"]["expected"],
            delta=row["historical_delta"],
            defect_model=defect_model,
        )
        for row in historical_projections[CAFTA_SELECTOR_ID]
    ]
    require(
        len(historical_defect_rows) == EXPECTED_CAFTA_UNITS,
        "historical CAFTA defect replay census drift",
    )

    lock = (
        nullcontext()
        if manifest_locked
        else foundation._manifest_lock(eval_manifest_path)
    )
    with lock:
        manifest_file = foundation.file_receipt(
            eval_manifest_path, relative_to=repo_root
        )
        comparison_file = foundation.file_receipt(
            comparison_receipt_path, relative_to=repo_root
        )
        (
            manifest,
            comparison,
            comparison_artifact,
            binding_audit,
            source_eval_units,
            shard_receipts,
        ) = foundation._validate_eval_and_comparison_bindings(
            repo_root=repo_root,
            eval_manifest_path=eval_manifest_path,
            comparison_receipt_path=comparison_receipt_path,
            preview=preview,
            selected_receipt=selected_receipt,
            historical_units=historical_units,
        )
        require(
            manifest.get("schema") == EVAL_MANIFEST_SCHEMA
            and comparison.get("schema") == COMPARISON_SCHEMA,
            "evaluation or comparison schema differs from the current campaign",
        )
        rulespec_root, entry_flags, _entry_flag_producers = (
            _validate_campaign_and_rulespec_runtime(manifest["run_identity"])
        )
        input_contract_file, predicate_proof = _validate_input_contract(
            repo_root=repo_root, run_identity=manifest["run_identity"]
        )
        actual_feed_rows = _reconstruct_joined_cafta_feeds(
            run_identity=manifest["run_identity"],
            source_eval_units=source_eval_units,
            entry_flags=entry_flags,
        )
        predicate_proof |= {
            "joined_fresh_evaluation_records": len(actual_feed_rows),
            "actual_case_feed_projection_sha256": population_sha256(actual_feed_rows),
            "all_joined_actual_case_feeds_false_false": True,
        }
        defect_rows, fresh_audit = _scan_fresh_reference_population(
            comparison_artifact=comparison_artifact,
            comparison=comparison,
            historical_units=historical_units,
            historical_rows=historical_projections[CAFTA_SELECTOR_ID],
            source_eval_units=source_eval_units,
            defect_model=defect_model,
        )
        require(
            foundation.file_receipt(eval_manifest_path, relative_to=repo_root)
            == manifest_file
            and foundation.file_receipt(comparison_receipt_path, relative_to=repo_root)
            == comparison_file
            and foundation.file_receipt(comparison_artifact)
            == comparison["comparison_artifact"]
            and all(
                foundation.file_receipt(Path(receipt["path"])) == receipt
                for receipt in shard_receipts
            ),
            "evaluation/comparison evidence changed during CAFTA proof",
        )

    historical_labeled = [
        {"selector": CAFTA_SELECTOR_ID, "identity": identity}
        for identity in historical_identities[CAFTA_SELECTOR_ID]
    ]
    fresh_labeled = [
        {"selector": CAFTA_SELECTOR_ID, "identity": row["identity"]}
        for row in defect_rows
    ]
    historical_digest = population_sha256(historical_labeled)
    fresh_digest = population_sha256(fresh_labeled)
    require(historical_digest == fresh_digest, "fresh CAFTA identity population drift")
    require(
        len(defect_rows) == EXPECTED_CAFTA_UNITS,
        "aggregate CAFTA supersession census drift",
    )

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "verdict": "PASS",
        "producer": producer,
        "definition": EXPECTED_DEFINITION,
        "inputs": {
            "immutable_preview_receipt": preview_file,
            "historical_target_mismatch_artifact": historical_receipt,
            "evaluation_manifest": manifest_file,
            "comparison_receipt": comparison_file,
            "comparison_artifact": comparison["comparison_artifact"],
            "declared_input_contract": input_contract_file,
            "reference_provenance": reference_provenance["provenance"],
            "reference_integrity_receipt": reference_provenance["integrity_receipt"],
            "selected_panel_extractor": reference_provenance["extractor"],
        },
        "bindings": {
            "preview_receipt_payload_sha256": preview["receipt_payload_sha256"],
            "preview_cafta_snapshot_sha256": canonical_sha256(
                cafta_preview_snapshot(preview)
            ),
            "rulespec": manifest["run_identity"]["rulespec"],
            "campaign_evaluator": manifest["run_identity"]["campaign_evaluator"],
            "selected_population_sha256": selected_receipt["sha256"],
            "reference_rds_path": reference_provenance["rds_path"],
            "reference_rds_sha256": reference_provenance["rds_sha256"],
            "reference_compared_field": reference_provenance["compared_field"],
            **binding_audit,
        },
        "axiom_predicate_proof": predicate_proof,
        "yale_reference_defect": yale_receipt,
        "zero_error_proof": {
            "evaluation_shard_engine_errors": 0,
            "observed_evaluation_record_errors": 0,
            "comparison_receipt_engine_errors": 0,
            "comparison_artifact_engine_error_rows": fresh_audit["engine_error_rows"],
        },
        "census": {
            "historical_artifact_rows_scanned": historical_scanned,
            "fresh_comparison_rows_scanned": fresh_audit["comparison_rows_scanned"],
            "cafta_units": EXPECTED_CAFTA_UNITS,
            "cafta_signatures": EXPECTED_CAFTA_SIGNATURES,
            "origin_units": fresh_audit["origin_units"],
        },
        "supersession": {
            "authorized_disposition_after_pass": "upstream_engine_gap",
            "authorized_attribution_after_pass": "reference-defect",
            "historical_identity_population_sha256": historical_digest,
            "fresh_identity_population_sha256": fresh_digest,
            "historical_mismatch_projection_sha256": population_sha256(
                historical_projections[CAFTA_SELECTOR_ID]
            ),
            "historical_defect_projection_sha256": population_sha256(
                historical_defect_rows
            ),
            "fresh_defect_projection_sha256": population_sha256(defect_rows),
            "joined_historical_units": fresh_audit["joined_historical_units"],
            "missing_historical_units": 0,
            "duplicate_historical_identities": 0,
            "duplicate_fresh_identities": 0,
            "fresh_mismatching_units": EXPECTED_CAFTA_UNITS,
            "all_present": True,
            "all_unique": True,
            "all_predicates_false": True,
            "all_yale_defect_zeros_reproduced": True,
            "all_corrected_yale_statutory_rates_match_axiom": True,
        },
    }
    payload["receipt_payload_sha256"] = canonical_sha256(payload)
    selected_path = foundation._resolve_receipted_path(
        selected_receipt["path"], repo_root
    )
    input_contract_path = foundation._resolve_receipted_path(
        manifest["run_identity"]["input_contract"]["path"], repo_root
    )
    _require_file_receipt_unchanged(
        producer_source,
        producer["script"],
        label="producer",
        relative_to=repo_root,
    )
    _require_file_receipt_unchanged(
        FOUNDATION_SOURCE,
        identity_helper,
        label="identity helper",
        relative_to=repo_root,
    )
    _require_file_receipt_unchanged(
        preview_receipt_path,
        preview_file,
        label="immutable preview",
        relative_to=repo_root,
    )
    _require_file_receipt_unchanged(
        selected_path,
        selected_receipt,
        label="selected population",
        relative_to=repo_root,
    )
    _require_file_receipt_unchanged(
        input_contract_path,
        input_contract_file,
        label="declared input contract",
        relative_to=repo_root,
    )
    _require_file_receipt_unchanged(
        PROVENANCE,
        reference_provenance["provenance"],
        label="reference provenance",
        relative_to=repo_root,
    )
    _require_file_receipt_unchanged(
        INTEGRITY_RECEIPT,
        reference_provenance["integrity_receipt"],
        label="reference integrity receipt",
        relative_to=repo_root,
    )
    _require_file_receipt_unchanged(
        SELECTED_EXTRACTOR,
        reference_provenance["extractor"],
        label="selected-panel extractor",
        relative_to=repo_root,
    )
    _require_file_receipt_unchanged(
        eval_manifest_path,
        manifest_file,
        label="evaluation manifest",
        relative_to=repo_root,
    )
    _require_file_receipt_unchanged(
        comparison_receipt_path,
        comparison_file,
        label="comparison receipt",
        relative_to=repo_root,
    )
    require(
        historical_artifact_path.stat().st_size == historical_receipt["bytes"]
        and foundation.sha256(historical_artifact_path) == historical_receipt["sha256"],
        "historical target artifact changed during CAFTA proof",
    )
    _revalidate_yale_evidence(yale_root, yale_receipt)
    require(
        campaign._rulespec_root_identity(rulespec_root)
        == manifest["run_identity"]["rulespec"]
        and campaign._campaign_evaluator_identity()
        == manifest["run_identity"]["campaign_evaluator"],
        "RuleSpec or campaign runtime changed during CAFTA proof",
    )
    return payload


def _build_receipt_transaction(
    *,
    repo_root: Path,
    producer_source: Path,
    preview_receipt_path: Path,
    historical_artifact_path: Path,
    eval_manifest_path: Path,
    comparison_receipt_path: Path,
    yale_root: Path,
    manifest_locked: bool = False,
) -> tuple[dict[str, Any], Callable[[], None]]:
    proof_inputs = _ProofInputs()
    with proof_inputs.capture_foundation():
        payload = _build_receipt_impl(
            repo_root=repo_root,
            producer_source=producer_source,
            preview_receipt_path=preview_receipt_path,
            historical_artifact_path=historical_artifact_path,
            eval_manifest_path=eval_manifest_path,
            comparison_receipt_path=comparison_receipt_path,
            yale_root=yale_root,
            manifest_locked=manifest_locked,
        )
    proof_inputs.seal()

    def require_current() -> None:
        with proof_inputs.capture_foundation():
            proof_inputs.require_current()
            _revalidate_yale_evidence(yale_root, payload["yale_reference_defect"])
            require(
                campaign._rulespec_root_identity(campaign.RULESPEC_US_ROOT)
                == payload["bindings"]["rulespec"]
                and campaign._campaign_evaluator_identity()
                == payload["bindings"]["campaign_evaluator"],
                "RuleSpec or campaign runtime changed during CAFTA publication",
            )
            proof_inputs.require_current()

    require_current()
    return payload, require_current


def build_receipt(
    *,
    repo_root: Path,
    producer_source: Path,
    preview_receipt_path: Path,
    historical_artifact_path: Path,
    eval_manifest_path: Path,
    comparison_receipt_path: Path,
    yale_root: Path,
    manifest_locked: bool = False,
    _return_transaction: bool = False,
) -> dict[str, Any] | tuple[dict[str, Any], Callable[[], None]]:
    transaction = _build_receipt_transaction(
        repo_root=repo_root,
        producer_source=producer_source,
        preview_receipt_path=preview_receipt_path,
        historical_artifact_path=historical_artifact_path,
        eval_manifest_path=eval_manifest_path,
        comparison_receipt_path=comparison_receipt_path,
        yale_root=yale_root,
        manifest_locked=manifest_locked,
    )
    return transaction if _return_transaction else transaction[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview-receipt", type=Path, default=PREVIEW_RECEIPT)
    parser.add_argument("--historical-artifact", type=Path, default=HISTORICAL_ARTIFACT)
    parser.add_argument("--eval-manifest", type=Path, default=EVAL_MANIFEST)
    parser.add_argument("--comparison-receipt", type=Path, default=COMPARISON_RECEIPT)
    parser.add_argument("--yale-root", type=Path, default=DEFAULT_YALE_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check", action="store_true", help="compare generated bytes; do not write"
    )
    args = parser.parse_args()
    eval_manifest_path = args.eval_manifest.resolve()
    output_path = args.output.resolve()
    with foundation._manifest_lock(eval_manifest_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        previous_output = _output_snapshot(output_path)
        built = build_receipt(
            repo_root=REPO_ROOT,
            producer_source=PRODUCER_SOURCE,
            preview_receipt_path=args.preview_receipt.resolve(),
            historical_artifact_path=args.historical_artifact.resolve(),
            eval_manifest_path=eval_manifest_path,
            comparison_receipt_path=args.comparison_receipt.resolve(),
            yale_root=args.yale_root.resolve(),
            manifest_locked=True,
            _return_transaction=True,
        )
        if isinstance(built, tuple):
            receipt, require_current = built
        else:  # Preserve test and downstream monkeypatch compatibility.
            receipt, require_current = built, lambda: None
        output = render(receipt).encode()
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
                "verdict": receipt["verdict"],
                "output": str(output_path),
                "output_sha256": hashlib.sha256(output).hexdigest(),
                "cafta_units": receipt["census"]["cafta_units"],
            }
        ),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
