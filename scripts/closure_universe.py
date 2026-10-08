#!/usr/bin/env python3
"""Generate and validate the pinned closure universes for the CO SNAP program.

Closure is the completeness analogue of conformance: each declared legal root
has a source-derived denominator, and every provision is classified as encoded,
excluded with a reviewed reason, or pending. The denominator comes only from
the pinned JSONL snapshots in ``closure/data``. Encoding status comes only from
an exact citation-path join against the pinned RuleSpec file inventory.

Human review lives on top of those generated facts. Regeneration preserves
excluded classifications (including reason and basis), corrected ``encoded_by``
paths, and notes. It refreshes citations, headings, and ordinary encoded/pending
statuses from the pins.

Modes::

    uv run scripts/closure_universe.py --generate
    uv run scripts/closure_universe.py --check

``--check`` is read-only and fails on stale artifacts, invalid classifications,
bad provenance hashes, missing RuleSpec paths, citation drift, or a pending
regression while the provenance pins are unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

UNIVERSE_SCHEMA = "axiom_oracles.closure.universe.v1"
SUMMARY_SCHEMA = "axiom_oracles.closure.summary.v1"
PROVENANCE_SCHEMA = "axiom_oracles.closure.provenance.v1"
PROGRAM = "us-co/snap"
TREE_FILE = "rulespec-us-files.txt"

STATUSES: tuple[str, ...] = ("encoded", "excluded", "pending")
FIXED_EXCLUSION_REASONS: tuple[str, ...] = (
    "container_heading",
    "procedural_no_point_in_time_effect",
    "reserved",
    "no_household_computation",
)
OPERATIONALIZED_PREFIX = "operationalized_by:"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PIN_IDENTITY_FIELDS: tuple[str, ...] = (
    "source_file",
    "source_sha256",
    "rulespec_file",
    "rulespec_sha256",
)


@dataclass(frozen=True)
class RootConfig:
    """One declared closure root and its mechanical citation-to-module join."""

    root: str
    source_file: str
    citation_root: str
    module_root: str


@dataclass(frozen=True)
class RatchetBaseline:
    """Cross-bound pending ceiling from the prior universe and summary."""

    pins_sha256: str
    pending_max: int


ROOTS: tuple[RootConfig, ...] = (
    RootConfig(
        root="state-10-ccr-2506-1",
        source_file="co-provisions.jsonl",
        citation_root="us-co/regulation/10-ccr-2506-1",
        module_root="us-co/regulations/10-ccr-2506-1",
    ),
    RootConfig(
        root="us-7-cfr-273",
        source_file="cfr-273.jsonl",
        citation_root="us/regulation/7/273",
        module_root="us/regulations/7-cfr/273",
    ),
    RootConfig(
        root="us-7-usc-51",
        source_file="usc-51.jsonl",
        citation_root="us/statute/7",
        module_root="us/statutes/7",
    ),
)


class _ClosureDumper(yaml.SafeDumper):
    """YAML dumper with the repository's indented block-sequence convention."""

    def increase_indent(self, flow: bool = False, indentless: bool = False):
        return super().increase_indent(flow, False)


def _represent_ordered(dumper: yaml.Dumper, data: dict) -> yaml.nodes.MappingNode:
    return dumper.represent_mapping("tag:yaml.org,2002:map", data.items())


_ClosureDumper.add_representer(dict, _represent_ordered)


def _display(path: Path) -> str:
    """Return a useful path in both the real repo and tmpdir mutant tests."""

    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pins_sha256(provenance: Mapping[str, Any]) -> str:
    """Fingerprint only the pinned content identity, not descriptive prose.

    Repositories and refs remain canonical generated provenance fields, so a
    stale edit still fails byte-level checking. They are deliberately excluded
    here: changing a URL/ref label while the pinned bytes are identical must
    never reset the pending ratchet.
    """

    identity = {field: provenance.get(field) for field in _PIN_IDENTITY_FIELDS}
    encoded = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _safe_data_path(data_dir: Path, filename: str) -> Path | None:
    relative = PurePosixPath(filename)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    return data_dir.joinpath(*relative.parts)


def _load_provenance(data_dir: Path, errors: list[str]) -> dict[str, dict[str, Any]]:
    """Load provenance.yaml and verify every declared snapshot against its pin."""

    path = data_dir / "provenance.yaml"
    if not path.is_file():
        errors.append(f"{_display(path)} is missing")
        return {}
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        errors.append(f"{_display(path)} could not be read: {exc}")
        return {}
    if not isinstance(document, Mapping):
        errors.append(f"{_display(path)} must contain a YAML mapping")
        return {}
    if document.get("schema") != PROVENANCE_SCHEMA:
        errors.append(
            f"{_display(path)}: expected schema {PROVENANCE_SCHEMA!r}, "
            f"got {document.get('schema')!r}"
        )

    snapshots = document.get("snapshots")
    if not isinstance(snapshots, list):
        errors.append(f"{_display(path)}: `snapshots` must be a list")
        return {}

    by_file: dict[str, dict[str, Any]] = {}
    for index, snapshot in enumerate(snapshots):
        label = f"{_display(path)} snapshots[{index}]"
        if not isinstance(snapshot, Mapping):
            errors.append(f"{label} must be a mapping")
            continue
        filename = snapshot.get("file")
        if not _nonempty_string(filename):
            errors.append(f"{label} requires a non-empty `file`")
            continue
        filename = str(filename)
        if filename in by_file:
            errors.append(f"{label}: duplicate snapshot file {filename!r}")
            continue
        entry = dict(snapshot)
        by_file[filename] = entry

        for field in ("source_repo", "source_ref", "extraction"):
            if not _nonempty_string(entry.get(field)):
                errors.append(f"{label} requires a non-empty `{field}`")

        declared_sha = entry.get("sha256")
        if not isinstance(declared_sha, str) or not _SHA256_RE.fullmatch(declared_sha):
            errors.append(f"{label} requires a lowercase 64-hex `sha256`")

        snapshot_path = _safe_data_path(data_dir, filename)
        if snapshot_path is None:
            errors.append(f"{label}: unsafe snapshot path {filename!r}")
            continue
        if not snapshot_path.is_file():
            errors.append(f"{_display(snapshot_path)} is missing")
            continue
        actual_sha = _sha256(snapshot_path)
        if declared_sha != actual_sha:
            errors.append(
                f"{_display(snapshot_path)} sha256 mismatch: provenance pins "
                f"{declared_sha!r}, actual file is {actual_sha}"
            )

    required_files = {config.source_file for config in ROOTS} | {TREE_FILE}
    for filename in sorted(required_files - by_file.keys()):
        errors.append(
            f"{_display(path)} has no snapshot entry for required file {filename!r}"
        )
    return by_file


def _load_tree(path: Path, errors: list[str]) -> set[str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        errors.append(f"{_display(path)} could not be read: {exc}")
        return set()
    paths = [line for line in lines if line]
    duplicates = sorted(path for path, count in Counter(paths).items() if count > 1)
    if duplicates:
        errors.append(
            f"{_display(path)} contains duplicate paths: {_format_values(duplicates)}"
        )
    return set(paths)


def _load_source_rows(
    config: RootConfig, data_dir: Path, errors: list[str]
) -> list[dict[str, str]]:
    """Read every nonblank JSONL row; no kind or filename filtering is allowed."""

    path = data_dir / config.source_file
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    try:
        handle = path.open(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        errors.append(f"{_display(path)} could not be read: {exc}")
        return rows

    with handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                continue
            label = f"{_display(path)}:{line_number}"
            try:
                raw = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                errors.append(f"{label}: invalid JSON: {exc}")
                continue
            if not isinstance(raw, Mapping):
                errors.append(f"{label}: provision row must be a JSON object")
                continue
            citation = raw.get("citation_path")
            if not _nonempty_string(citation):
                errors.append(f"{label}: missing non-empty `citation_path`")
                continue
            citation = str(citation)
            if not (
                citation == config.citation_root
                or citation.startswith(config.citation_root + "/")
            ):
                errors.append(
                    f"{label}: citation {citation!r} is outside declared root "
                    f"{config.citation_root!r}"
                )
            if citation in seen:
                errors.append(
                    f"{label}: duplicate citation_path {citation!r} in source"
                )
                continue
            seen.add(citation)

            heading = raw.get("heading", "")
            if heading is None:
                heading = ""
            if not isinstance(heading, str):
                errors.append(f"{label}: `heading` must be a string when present")
                continue
            rows.append({"citation": citation, "heading": heading})
    return sorted(rows, key=lambda row: row["citation"])


def _load_universe(path: Path, errors: list[str]) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        errors.append(f"{_display(path)} could not be read: {exc}")
        return None
    if not isinstance(document, Mapping):
        errors.append(f"{_display(path)} must contain a YAML mapping")
        return None
    return dict(document)


def _load_summary(path: Path, errors: list[str]) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"{_display(path)} could not be read: {exc}")
        return None
    if not isinstance(document, Mapping):
        errors.append(f"{_display(path)} must contain a JSON object")
        return None
    return dict(document)


def _validate_summary_baseline(
    document: dict[str, Any],
    *,
    path: Path,
    allow_missing_pins: bool,
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    """Validate the committed summary copy of each root's ratchet baseline."""

    label = _display(path)
    if document.get("schema") != SUMMARY_SCHEMA:
        errors.append(
            f"{label}: expected schema {SUMMARY_SCHEMA!r}, "
            f"got {document.get('schema')!r}"
        )
    if document.get("program") != PROGRAM:
        errors.append(
            f"{label}: expected program {PROGRAM!r}, got {document.get('program')!r}"
        )
    raw_roots = document.get("roots")
    if not isinstance(raw_roots, list):
        errors.append(f"{label}: `roots` must be a list")
        return {}

    by_root: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(raw_roots):
        row_label = f"{label} roots[{index}]"
        if not isinstance(raw, Mapping):
            errors.append(f"{row_label} must be a mapping")
            continue
        row = dict(raw)
        root = row.get("root")
        if not _nonempty_string(root):
            errors.append(f"{row_label} requires a non-empty `root`")
            continue
        root = str(root)
        row_label = f"{label} root {root!r}"
        if root in by_root:
            errors.append(f"{row_label}: duplicate root")
            continue
        by_root[root] = row

        pending_max = row.get("pending_max")
        if (
            isinstance(pending_max, bool)
            or not isinstance(pending_max, int)
            or pending_max < 0
        ):
            errors.append(f"{row_label}: `pending_max` must be a non-negative integer")

        pins = row.get("pins_sha256")
        if pins is None and allow_missing_pins:
            pass
        elif not isinstance(pins, str) or not _SHA256_RE.fullmatch(pins):
            errors.append(f"{row_label}: `pins_sha256` must be lowercase 64-hex")

        total = row.get("total")
        if isinstance(total, bool) or not isinstance(total, int) or total < 0:
            errors.append(f"{row_label}: `total` must be a non-negative integer")
        by_status = row.get("by_status")
        if not isinstance(by_status, Mapping):
            errors.append(f"{row_label}: `by_status` must be a mapping")
        else:
            status_total = 0
            for status in STATUSES:
                count = by_status.get(status)
                if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                    errors.append(
                        f"{row_label}: by_status[{status!r}] must be a "
                        "non-negative integer"
                    )
                else:
                    status_total += count
            if isinstance(total, int) and not isinstance(total, bool):
                if status_total != total:
                    errors.append(
                        f"{row_label}: status counts total {status_total}, "
                        f"not declared total {total}"
                    )
        by_reason = row.get("by_reason")
        if not isinstance(by_reason, Mapping):
            errors.append(f"{row_label}: `by_reason` must be a mapping")
        else:
            for reason, count in by_reason.items():
                if not _nonempty_string(reason) or (
                    isinstance(count, bool) or not isinstance(count, int) or count < 0
                ):
                    errors.append(
                        f"{row_label}: reason counts require non-empty keys "
                        "and non-negative integer values"
                    )

    expected = {config.root for config in ROOTS}
    missing = sorted(expected - by_root.keys())
    extra = sorted(by_root.keys() - expected)
    if missing:
        errors.append(
            f"{label}: ratchet summary is missing roots {_format_values(missing)}"
        )
    if extra:
        errors.append(
            f"{label}: ratchet summary has unexpected roots {_format_values(extra)}"
        )
    return by_root


def _is_module_path(path: str) -> bool:
    if path != path.strip() or "\\" in path:
        return False
    relative = PurePosixPath(path)
    return (
        bool(path)
        and not relative.is_absolute()
        and ".." not in relative.parts
        and path.endswith(".yaml")
        and not path.endswith(".test.yaml")
    )


def _validate_named_path(
    value: object,
    *,
    field: str,
    label: str,
    tree_paths: set[str],
    errors: list[str],
) -> str | None:
    if not _nonempty_string(value):
        errors.append(f"{label}: `{field}` must be a non-empty path")
        return None
    path = str(value)
    if not _is_module_path(path):
        errors.append(
            f"{label}: `{field}` must name a safe, non-test `.yaml` module "
            f"path (got {path!r})"
        )
        return None
    if path not in tree_paths:
        errors.append(
            f"{label}: `{field}` path {path!r} is absent from the pinned tree "
            f"({TREE_FILE})"
        )
        return None
    return path


def _validate_encoded_by(
    value: object,
    *,
    label: str,
    tree_paths: set[str],
    errors: list[str],
) -> list[str]:
    if not isinstance(value, list) or not value:
        errors.append(f"{label}: `encoded_by` must be a non-empty list of module paths")
        return []
    paths: list[str] = []
    for index, raw_path in enumerate(value):
        path = _validate_named_path(
            raw_path,
            field=f"encoded_by[{index}]",
            label=label,
            tree_paths=tree_paths,
            errors=errors,
        )
        if path is not None:
            paths.append(path)
    duplicates = sorted(path for path, count in Counter(paths).items() if count > 1)
    if duplicates:
        errors.append(
            f"{label}: `encoded_by` contains duplicate paths: "
            f"{_format_values(duplicates)}"
        )
    return paths


def _reason_category(
    reason: object,
    *,
    label: str,
    tree_paths: set[str],
    errors: list[str],
) -> str | None:
    if not _nonempty_string(reason):
        errors.append(f"{label}: excluded rows require a non-empty `reason`")
        return None
    reason = str(reason)
    if reason in FIXED_EXCLUSION_REASONS:
        return reason
    if reason.startswith(OPERATIONALIZED_PREFIX):
        # `operationalized_by: <path>` is written by humans in YAML, where a
        # space after the colon is the natural form. Strip the separator here
        # so spacing cannot decide whether a gate passes; the extracted path is
        # still required to be trim-clean, relative, non-test and present in
        # the pinned tree, so no safety property is relaxed.
        path = reason.removeprefix(OPERATIONALIZED_PREFIX).strip()
        if _validate_named_path(
            path,
            field="operationalized_by path",
            label=label,
            tree_paths=tree_paths,
            errors=errors,
        ):
            return "operationalized_by"
        return None
    taxonomy = ", ".join((*FIXED_EXCLUSION_REASONS, f"{OPERATIONALIZED_PREFIX}<path>"))
    errors.append(
        f"{label}: reason {reason!r} is outside the declared taxonomy ({taxonomy})"
    )
    return None


def _validate_provision_rows(
    rows: object,
    *,
    config: RootConfig,
    label: str,
    tree_paths: set[str],
    allow_generated_path_drift: bool,
    errors: list[str],
) -> list[dict[str, Any]]:
    """Validate row shape and status-specific invariants, accumulating errors."""

    if not isinstance(rows, list):
        errors.append(f"{label}: `provisions` must be a list")
        return []

    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(rows):
        row_label = f"{label} provisions[{index}]"
        if not isinstance(raw, Mapping):
            errors.append(f"{row_label} must be a mapping")
            continue
        row = dict(raw)
        validated.append(row)

        citation = row.get("citation")
        citation_text: str | None = None
        if not _nonempty_string(citation):
            errors.append(f"{row_label}: missing non-empty `citation`")
        else:
            citation_text = str(citation)
            row_label = f"{label} provision {citation_text!r}"
            if citation_text in seen:
                errors.append(f"{row_label}: duplicate citation")
            seen.add(citation_text)

        if "heading" not in row or not isinstance(row.get("heading"), str):
            errors.append(f"{row_label}: `heading` must be a string")
        if "note" in row and not isinstance(row.get("note"), str):
            errors.append(f"{row_label}: `note` must be a string when present")

        status = row.get("status")
        if status not in STATUSES:
            errors.append(
                f"{row_label}: status {status!r} must be one of {', '.join(STATUSES)}"
            )
            continue

        if status == "encoded":
            validation_tree = tree_paths
            encoded_by = row.get("encoded_by")
            if citation_text is not None and allow_generated_path_drift:
                candidate = _module_candidate(config, citation_text)
                # A prior machine-generated exact join may disappear after a
                # legitimate RuleSpec pin update. Admit that one stale shape
                # while reading the old artifact so generation can re-derive
                # it as pending. A corrected path remains fully validated.
                if encoded_by == [candidate] and _is_module_path(candidate):
                    validation_tree = tree_paths | {candidate}
            _validate_encoded_by(
                encoded_by,
                label=row_label,
                tree_paths=validation_tree,
                errors=errors,
            )
            for contradictory in ("reason", "basis"):
                if contradictory in row:
                    errors.append(
                        f"{row_label}: encoded rows must not carry `{contradictory}`"
                    )
        elif status == "excluded":
            if "encoded_by" in row:
                errors.append(f"{row_label}: excluded rows must not carry `encoded_by`")
            _reason_category(
                row.get("reason"),
                label=row_label,
                tree_paths=tree_paths,
                errors=errors,
            )
            if not _nonempty_string(row.get("basis")):
                errors.append(f"{row_label}: excluded rows require a non-empty `basis`")
        else:
            for contradictory in ("encoded_by", "reason", "basis"):
                if contradictory in row:
                    errors.append(
                        f"{row_label}: pending rows must not carry `{contradictory}`"
                    )
            # `partial_coverage` records that a module file exists for this
            # provision but does not compute its substantive content. It is the
            # one way a row stays pending despite a successful join, so it must
            # say WHAT is missing — an empty or hand-wavy marker would let the
            # count be lowered by assertion.
            if "partial_coverage" in row and not _nonempty_string(
                row.get("partial_coverage")
            ):
                errors.append(
                    f"{row_label}: `partial_coverage` must state which outputs "
                    "the joined module declares it does not compute"
                )
            if "join_found_module" in row and "partial_coverage" not in row:
                errors.append(
                    f"{row_label}: `join_found_module` requires `partial_coverage`"
                )
    return validated


def _validate_universe(
    document: dict[str, Any],
    *,
    config: RootConfig,
    path: Path,
    tree_paths: set[str],
    allow_missing_pins: bool,
    allow_generated_path_drift: bool,
    errors: list[str],
) -> list[dict[str, Any]]:
    label = _display(path)
    if document.get("schema") != UNIVERSE_SCHEMA:
        errors.append(
            f"{label}: expected schema {UNIVERSE_SCHEMA!r}, "
            f"got {document.get('schema')!r}"
        )
    if document.get("program") != PROGRAM:
        errors.append(
            f"{label}: expected program {PROGRAM!r}, got {document.get('program')!r}"
        )
    if document.get("root") != config.root:
        errors.append(
            f"{label}: expected root {config.root!r}, got {document.get('root')!r}"
        )

    provenance = document.get("provenance")
    provenance_fields = (
        "source_file",
        "source_repo",
        "source_ref",
        "source_sha256",
        "rulespec_file",
        "rulespec_repo",
        "rulespec_ref",
        "rulespec_sha256",
    )
    if not isinstance(provenance, Mapping):
        errors.append(f"{label}: `provenance` must be a mapping")
    else:
        for field in provenance_fields:
            if not _nonempty_string(provenance.get(field)):
                errors.append(f"{label}: provenance requires a non-empty `{field}`")
        for field in ("source_sha256", "rulespec_sha256"):
            value = provenance.get(field)
            if isinstance(value, str) and not _SHA256_RE.fullmatch(value):
                errors.append(f"{label}: provenance `{field}` must be lowercase 64-hex")

    ratchet = document.get("ratchet")
    if not isinstance(ratchet, Mapping):
        errors.append(f"{label}: `ratchet` must be a mapping")
    else:
        pins = ratchet.get("pins_sha256")
        if pins is None and allow_missing_pins:
            pass
        elif not isinstance(pins, str) or not _SHA256_RE.fullmatch(pins):
            errors.append(f"{label}: ratchet `pins_sha256` must be lowercase 64-hex")
        elif isinstance(provenance, Mapping):
            provenance_pins = _pins_sha256(provenance)
            if pins != provenance_pins:
                errors.append(
                    f"{label}: ratchet `pins_sha256` does not match the "
                    "content-identity fingerprint of its provenance"
                )
        pending_max = ratchet.get("pending_max")
        if (
            isinstance(pending_max, bool)
            or not isinstance(pending_max, int)
            or pending_max < 0
        ):
            errors.append(
                f"{label}: ratchet `pending_max` must be a non-negative integer"
            )

    return _validate_provision_rows(
        document.get("provisions"),
        config=config,
        label=label,
        tree_paths=tree_paths,
        allow_generated_path_drift=allow_generated_path_drift,
        errors=errors,
    )


def _format_values(values: Sequence[str], limit: int = 8) -> str:
    shown = list(values[:limit])
    text = ", ".join(repr(value) for value in shown)
    if len(values) > limit:
        text += f", ... (+{len(values) - limit} more)"
    return text


def _check_citation_drift(
    source_rows: list[dict[str, str]],
    committed_rows: list[dict[str, Any]],
    *,
    root: str,
    errors: list[str],
) -> None:
    source = Counter(row["citation"] for row in source_rows)
    committed = Counter(
        str(row["citation"])
        for row in committed_rows
        if _nonempty_string(row.get("citation"))
    )
    missing = sorted((source - committed).elements())
    extra = sorted((committed - source).elements())
    if missing:
        errors.append(
            f"closure[{root}] citation drift: committed universe is missing "
            f"{_format_values(missing)}"
        )
    if extra:
        errors.append(
            f"closure[{root}] citation drift: committed universe has extra "
            f"{_format_values(extra)}"
        )


def _module_candidate(config: RootConfig, citation: str) -> str:
    suffix = citation.removeprefix(config.citation_root)
    return f"{config.module_root}{suffix}.yaml"


def _generated_provenance(
    config: RootConfig,
    snapshots: Mapping[str, Mapping[str, Any]],
) -> dict[str, str]:
    source = snapshots[config.source_file]
    rulespec = snapshots[TREE_FILE]
    return {
        "source_file": config.source_file,
        "source_repo": str(source["source_repo"]),
        "source_ref": str(source["source_ref"]),
        "source_sha256": str(source["sha256"]),
        "rulespec_file": TREE_FILE,
        "rulespec_repo": str(rulespec["source_repo"]),
        "rulespec_ref": str(rulespec["source_ref"]),
        "rulespec_sha256": str(rulespec["sha256"]),
    }


def _ratchet_baseline(
    config: RootConfig,
    *,
    committed: Mapping[str, Any] | None,
    summary_row: Mapping[str, Any] | None,
    current_pins: str,
    errors: list[str],
) -> RatchetBaseline | None:
    """Cross-check the two prior ratchet copies before either can authorize.

    The v1 artifacts initially committed before ``pins_sha256`` are admitted
    once, but only when both ceilings agree and the old universe's content
    identity still equals the current pinned content. A partial migration or a
    pin change must first be reviewed from a fully cross-bound baseline.
    """

    if committed is None and summary_row is None:
        return None
    if committed is None:
        errors.append(
            f"closure[{config.root}] ratchet baseline exists in summary but "
            "the universe side is missing"
        )
        return None
    if summary_row is None:
        errors.append(
            f"closure[{config.root}] ratchet baseline exists in the universe "
            "but its summary side is missing"
        )
        return None

    ratchet = committed.get("ratchet")
    if not isinstance(ratchet, Mapping):
        return None
    universe_max = ratchet.get("pending_max")
    summary_max = summary_row.get("pending_max")
    valid_universe_max = (
        not isinstance(universe_max, bool)
        and isinstance(universe_max, int)
        and universe_max >= 0
    )
    valid_summary_max = (
        not isinstance(summary_max, bool)
        and isinstance(summary_max, int)
        and summary_max >= 0
    )
    if not valid_universe_max or not valid_summary_max:
        return None
    if universe_max != summary_max:
        errors.append(
            f"closure[{config.root}] ratchet baseline disagrees with summary: "
            f"universe pending_max={universe_max}, "
            f"summary pending_max={summary_max}"
        )
        return None

    universe_pins = ratchet.get("pins_sha256")
    summary_pins = summary_row.get("pins_sha256")
    if universe_pins is None and summary_pins is None:
        provenance = committed.get("provenance")
        if not isinstance(provenance, Mapping):
            return None
        migrated_pins = _pins_sha256(provenance)
        if migrated_pins != current_pins:
            errors.append(
                f"closure[{config.root}] cannot migrate the v1 ratchet: the "
                "existing universe provenance pins do not match the current "
                "pinned content"
            )
            return None
        return RatchetBaseline(
            pins_sha256=migrated_pins,
            pending_max=universe_max,
        )

    if universe_pins is None or summary_pins is None:
        missing_side = "universe" if universe_pins is None else "summary"
        errors.append(
            f"closure[{config.root}] ratchet `pins_sha256` is missing from the "
            f"{missing_side} baseline copy; universe and summary must both "
            "carry it"
        )
        return None
    if (
        not isinstance(universe_pins, str)
        or not _SHA256_RE.fullmatch(universe_pins)
        or not isinstance(summary_pins, str)
        or not _SHA256_RE.fullmatch(summary_pins)
    ):
        return None
    if universe_pins != summary_pins:
        errors.append(
            f"closure[{config.root}] ratchet pin fingerprint disagrees with "
            f"summary: universe={universe_pins}, summary={summary_pins}"
        )
        return None
    return RatchetBaseline(
        pins_sha256=universe_pins,
        pending_max=universe_max,
    )


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    """Run a bounded, non-interactive Git query for ratchet history."""

    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        timeout=15,
    )


def _history_ratchet_baseline(
    closure_dir: Path,
    config: RootConfig,
    *,
    current_pins: str,
    errors: list[str],
) -> RatchetBaseline | None:
    """Derive the immutable pending floor from committed Git ancestors.

    Artifact metadata alone cannot prove monotonicity because a coordinated
    edit can raise every duplicated ceiling. In a repository checkout, inspect
    every committed version of this universe and take the lowest pending count
    carrying the current content-pin fingerprint. CI fetches full history so a
    pull request cannot erase the baseline already present on its base branch.

    Tmpdir callers without a Git repository retain the cross-bound artifact
    baseline; mutant tests that exercise coordinated edits initialize a local
    repository explicitly.
    """

    try:
        root_result = _run_git(closure_dir, "rev-parse", "--show-toplevel")
    except (OSError, subprocess.TimeoutExpired):
        return None
    if root_result.returncode != 0:
        return None

    try:
        repo_root = Path(root_result.stdout.decode("utf-8").strip()).resolve()
        relative_closure = closure_dir.resolve().relative_to(repo_root)
    except (UnicodeError, ValueError):
        return None

    try:
        shallow_result = _run_git(repo_root, "rev-parse", "--is-shallow-repository")
    except (OSError, subprocess.TimeoutExpired) as exc:
        errors.append(f"closure[{config.root}] could not inspect Git history: {exc}")
        return None
    if shallow_result.returncode != 0:
        errors.append(
            f"closure[{config.root}] could not determine whether Git history is shallow"
        )
        return None
    if shallow_result.stdout.strip() == b"true":
        errors.append(
            f"closure[{config.root}] cannot enforce the pending ratchet from a "
            "shallow Git checkout; fetch full history"
        )
        return None

    universe_relative = (
        relative_closure / "universes" / "us-co-snap" / f"{config.root}.yaml"
    ).as_posix()
    try:
        commits_result = _run_git(
            repo_root,
            "rev-list",
            "--full-history",
            "HEAD",
            "--",
            universe_relative,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        errors.append(f"closure[{config.root}] could not inspect Git history: {exc}")
        return None
    if commits_result.returncode != 0:
        errors.append(
            f"closure[{config.root}] could not enumerate prior universe versions"
        )
        return None

    pending_floor: int | None = None
    for commit in commits_result.stdout.decode("ascii").splitlines():
        try:
            artifact_result = _run_git(
                repo_root, "show", f"{commit}:{universe_relative}"
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if artifact_result.returncode != 0:
            continue
        try:
            historical = yaml.safe_load(artifact_result.stdout.decode("utf-8")) or {}
        except (UnicodeError, yaml.YAMLError):
            continue
        if not isinstance(historical, Mapping):
            continue
        if (
            historical.get("schema") != UNIVERSE_SCHEMA
            or historical.get("program") != PROGRAM
            or historical.get("root") != config.root
        ):
            continue
        provenance = historical.get("provenance")
        if not isinstance(provenance, Mapping):
            continue
        if _pins_sha256(provenance) != current_pins:
            continue
        rows = historical.get("provisions")
        if not isinstance(rows, list) or any(
            not isinstance(row, Mapping) or row.get("status") not in STATUSES
            for row in rows
        ):
            continue
        pending = sum(row.get("status") == "pending" for row in rows)
        pending_floor = (
            pending if pending_floor is None else min(pending_floor, pending)
        )

    if pending_floor is None:
        return None
    return RatchetBaseline(
        pins_sha256=current_pins,
        pending_max=pending_floor,
    )


def _strictest_ratchet_baseline(
    artifact: RatchetBaseline | None,
    history: RatchetBaseline | None,
    *,
    current_pins: str,
) -> RatchetBaseline | None:
    """Combine mutable artifact metadata with the ancestor-derived floor."""

    matching = [
        baseline
        for baseline in (artifact, history)
        if baseline is not None and baseline.pins_sha256 == current_pins
    ]
    if matching:
        return RatchetBaseline(
            pins_sha256=current_pins,
            pending_max=min(baseline.pending_max for baseline in matching),
        )
    return artifact


def _merge_provisions(
    config: RootConfig,
    source_rows: list[dict[str, str]],
    tree_paths: set[str],
    committed_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    committed_by_citation = {
        str(row["citation"]): row
        for row in committed_rows
        if _nonempty_string(row.get("citation"))
    }
    provisions: list[dict[str, Any]] = []
    for source in source_rows:
        citation = source["citation"]
        candidate = _module_candidate(config, citation)
        if candidate in tree_paths and _is_module_path(candidate):
            row: dict[str, Any] = {
                "citation": citation,
                "heading": source["heading"],
                "status": "encoded",
                "encoded_by": [candidate],
            }
        else:
            row = {
                "citation": citation,
                "heading": source["heading"],
                "status": "pending",
            }

        committed = committed_by_citation.get(citation)
        if committed is not None:
            if committed.get("status") == "pending" and _nonempty_string(
                committed.get("partial_coverage")
            ):
                # A citation-path join proves a module FILE exists for this
                # provision. It cannot prove the module computes the
                # provision's substantive content — and seven 7 CFR 273
                # modules carry machine-readable `deferred_outputs` blocks
                # declaring outputs they do not compute. Counting those as
                # encoded is the overstatement closure exists to prevent, so a
                # reviewed `partial_coverage` note holds the row at pending and
                # survives regeneration. The generated join result is kept
                # alongside it, so the disagreement stays visible rather than
                # being silently resolved in either direction.
                row = {
                    "citation": citation,
                    "heading": source["heading"],
                    "status": "pending",
                    "partial_coverage": committed.get("partial_coverage"),
                }
                if candidate in tree_paths and _is_module_path(candidate):
                    row["join_found_module"] = candidate
            elif committed.get("status") == "excluded":
                row = {
                    "citation": citation,
                    "heading": source["heading"],
                    "status": "excluded",
                    "reason": committed.get("reason"),
                    "basis": committed.get("basis"),
                }
            elif committed.get("status") == "encoded" and committed.get(
                "encoded_by"
            ) != [candidate]:
                row = {
                    "citation": citation,
                    "heading": source["heading"],
                    "status": "encoded",
                    "encoded_by": committed.get("encoded_by"),
                }
            if "note" in committed:
                row["note"] = committed.get("note")
        provisions.append(row)
    return provisions


def _pending_count(document: Mapping[str, Any]) -> int:
    rows = document.get("provisions") or []
    return sum(
        1 for row in rows if isinstance(row, Mapping) and row.get("status") == "pending"
    )


def _build_universe(
    config: RootConfig,
    *,
    source_rows: list[dict[str, str]],
    tree_paths: set[str],
    snapshots: Mapping[str, Mapping[str, Any]],
    committed_rows: list[dict[str, Any]],
    baseline: RatchetBaseline | None,
    errors: list[str],
) -> dict[str, Any]:
    provenance = _generated_provenance(config, snapshots)
    current_pins = _pins_sha256(provenance)
    provisions = _merge_provisions(config, source_rows, tree_paths, committed_rows)
    current_pending = sum(1 for row in provisions if row.get("status") == "pending")
    pending_max = current_pending

    if baseline is not None and baseline.pins_sha256 == current_pins:
        # The ratchet protects against work silently regressing. A
        # `partial_coverage` row is the opposite: a disclosure that a joined
        # module does not compute the provision, each one carrying a written
        # statement of what is missing. Forbidding disclosure-driven rises
        # would make recording a stub costlier than leaving it counted as
        # encoded — an incentive pointing exactly the wrong way. So a rise is
        # permitted only to the extent it is accounted for by disclosures, and
        # any excess is still a regression.
        disclosed = sum(1 for row in provisions if row.get("partial_coverage"))
        rise = current_pending - baseline.pending_max
        if rise > 0 and rise > disclosed:
            errors.append(
                f"closure[{config.root}] pending RATCHET regressed from "
                f"{baseline.pending_max} to {current_pending} while content "
                f"pins are unchanged; only {disclosed} of the {rise} added "
                "pending row(s) carry `partial_coverage`, and pending may "
                "otherwise only fall"
            )
        elif rise > 0:
            print(
                f"closure[{config.root}] pending rose {baseline.pending_max} -> "
                f"{current_pending}, accounted for by {disclosed} disclosed "
                "partial-coverage row(s): a joined module does not compute its "
                "provision. This is a correction, not a regression."
            )
        pending_max = min(baseline.pending_max, current_pending) if rise <= 0 else current_pending

    return {
        "schema": UNIVERSE_SCHEMA,
        "program": PROGRAM,
        "root": config.root,
        "provenance": provenance,
        "ratchet": {
            "pins_sha256": current_pins,
            "pending_max": pending_max,
        },
        "provisions": provisions,
    }


_UNIVERSE_HEADER = (
    f"# {UNIVERSE_SCHEMA} — generated facts + committed review classifications.\n"
    "# citation, heading, and baseline encoded/pending status come from the pinned\n"
    "# closure data. Excluded reason/basis, corrected encoded_by paths, and notes\n"
    "# are human-reviewed overlays preserved by scripts/closure_universe.py.\n"
)


def serialize_universe(document: Mapping[str, Any]) -> str:
    """Serialize one universe deterministically for byte-level drift checks."""

    body = yaml.dump(
        dict(document),
        Dumper=_ClosureDumper,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=100,
    )
    return _UNIVERSE_HEADER + body


def _summary_document(
    universes: Mapping[str, Mapping[str, Any]],
    *,
    tree_paths: set[str],
    errors: list[str],
) -> dict[str, Any]:
    roots: list[dict[str, Any]] = []
    for root in sorted(universes):
        universe = universes[root]
        rows = universe.get("provisions") or []
        by_status = {
            status: sum(
                1
                for row in rows
                if isinstance(row, Mapping) and row.get("status") == status
            )
            for status in STATUSES
        }
        reason_counts: Counter[str] = Counter()
        for index, row in enumerate(rows):
            if not isinstance(row, Mapping) or row.get("status") != "excluded":
                continue
            category = _reason_category(
                row.get("reason"),
                label=f"closure[{root}] provisions[{index}]",
                tree_paths=tree_paths,
                errors=errors,
            )
            if category:
                reason_counts[category] += 1
        ratchet = universe.get("ratchet") or {}
        pins_sha256 = ratchet.get("pins_sha256")
        pending_max = ratchet.get("pending_max")
        roots.append(
            {
                "root": root,
                "total": len(rows),
                "by_status": by_status,
                "by_reason": {
                    reason: reason_counts[reason] for reason in sorted(reason_counts)
                },
                "pins_sha256": pins_sha256,
                "pending_max": pending_max,
            }
        )
    return {
        "schema": SUMMARY_SCHEMA,
        "program": PROGRAM,
        "roots": roots,
        "closed": all(root["by_status"]["pending"] == 0 for root in roots),
    }


def serialize_summary(document: Mapping[str, Any]) -> str:
    return json.dumps(document, indent=2, sort_keys=False) + "\n"


def build_artifacts(
    closure_dir: str | Path,
    *,
    check_citation_drift: bool,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any] | None, list[str]]:
    """Build canonical artifacts in memory and return every validation problem."""

    closure_dir = Path(closure_dir)
    data_dir = closure_dir / "data"
    universe_dir = closure_dir / "universes" / "us-co-snap"
    summary_path = closure_dir / "summary.json"
    errors: list[str] = []

    universe_paths = {
        config.root: universe_dir / f"{config.root}.yaml" for config in ROOTS
    }
    present_universes = {
        root for root, path in universe_paths.items() if path.is_file()
    }
    summary_exists = summary_path.is_file()
    any_artifact_exists = bool(present_universes) or summary_exists
    if any_artifact_exists:
        if not summary_exists:
            errors.append(
                "closure ratchet baseline is missing summary.json while "
                "universe artifacts exist"
            )
        for root in sorted(universe_paths.keys() - present_universes):
            errors.append(
                f"closure[{root}] ratchet baseline is present in summary but "
                "the universe artifact is missing"
            )

    committed_summary = _load_summary(summary_path, errors) if summary_exists else None
    summary_rows = (
        _validate_summary_baseline(
            committed_summary,
            path=summary_path,
            allow_missing_pins=True,
            errors=errors,
        )
        if committed_summary is not None
        else {}
    )

    snapshots = _load_provenance(data_dir, errors)
    if any(
        filename not in snapshots
        for filename in ({config.source_file for config in ROOTS} | {TREE_FILE})
    ):
        return {}, None, errors
    if errors:
        # Hash/provenance failures make every derived classification untrustworthy.
        return {}, None, errors

    tree_paths = _load_tree(data_dir / TREE_FILE, errors)
    universes: dict[str, dict[str, Any]] = {}
    for config in ROOTS:
        source_rows = _load_source_rows(config, data_dir, errors)
        output_path = universe_paths[config.root]
        committed = _load_universe(output_path, errors)
        committed_rows: list[dict[str, Any]] = []
        if committed is not None:
            committed_rows = _validate_universe(
                committed,
                config=config,
                path=output_path,
                tree_paths=tree_paths,
                allow_missing_pins=True,
                allow_generated_path_drift=True,
                errors=errors,
            )
            if check_citation_drift:
                _check_citation_drift(
                    source_rows,
                    committed_rows,
                    root=config.root,
                    errors=errors,
                )
        elif check_citation_drift:
            errors.append(
                f"{_display(output_path)} is missing; run "
                "`uv run scripts/closure_universe.py --generate`"
            )

        current_provenance = _generated_provenance(config, snapshots)
        current_pins = _pins_sha256(current_provenance)
        artifact_baseline = _ratchet_baseline(
            config,
            committed=committed,
            summary_row=summary_rows.get(config.root),
            current_pins=current_pins,
            errors=errors,
        )
        history_baseline = _history_ratchet_baseline(
            closure_dir,
            config,
            current_pins=current_pins,
            errors=errors,
        )
        baseline = _strictest_ratchet_baseline(
            artifact_baseline,
            history_baseline,
            current_pins=current_pins,
        )
        universe = _build_universe(
            config,
            source_rows=source_rows,
            tree_paths=tree_paths,
            snapshots=snapshots,
            committed_rows=committed_rows,
            baseline=baseline,
            errors=errors,
        )
        _validate_universe(
            universe,
            config=config,
            path=output_path,
            tree_paths=tree_paths,
            allow_missing_pins=False,
            allow_generated_path_drift=False,
            errors=errors,
        )
        universes[config.root] = universe

    summary = _summary_document(universes, tree_paths=tree_paths, errors=errors)
    _validate_summary_baseline(
        summary,
        path=summary_path,
        allow_missing_pins=False,
        errors=errors,
    )
    return universes, summary, errors


def run(closure_dir: str | Path, *, check: bool) -> int:
    """Run check or generation mode against a real or temporary closure dir."""

    closure_dir = Path(closure_dir)
    universe_dir = closure_dir / "universes" / "us-co-snap"
    summary_path = closure_dir / "summary.json"
    universes, summary, errors = build_artifacts(
        closure_dir, check_citation_drift=check
    )

    if check and summary is not None:
        for root, universe in universes.items():
            path = universe_dir / f"{root}.yaml"
            expected = serialize_universe(universe)
            if path.is_file() and path.read_text(encoding="utf-8") != expected:
                errors.append(
                    f"{_display(path)} is stale; run "
                    "`uv run scripts/closure_universe.py --generate`"
                )
        expected_summary = serialize_summary(summary)
        if not summary_path.is_file():
            errors.append(
                f"{_display(summary_path)} is missing; run "
                "`uv run scripts/closure_universe.py --generate`"
            )
        elif summary_path.read_text(encoding="utf-8") != expected_summary:
            errors.append(
                f"{_display(summary_path)} is stale; run "
                "`uv run scripts/closure_universe.py --generate`"
            )

    if errors:
        for error in errors:
            sys.stderr.write(f"closure ERROR: {error}\n")
        return 1
    if summary is None:
        sys.stderr.write("closure ERROR: no summary could be generated\n")
        return 1

    if check:
        total = sum(root["total"] for root in summary["roots"])
        pending = sum(root["by_status"]["pending"] for root in summary["roots"])
        print(
            f"closure universes OK: {len(universes)} roots, {total} provisions, "
            f"{pending} pending, closed={str(summary['closed']).lower()}"
        )
        return 0

    universe_dir.mkdir(parents=True, exist_ok=True)
    for root, universe in universes.items():
        (universe_dir / f"{root}.yaml").write_text(
            serialize_universe(universe), encoding="utf-8"
        )
    summary_path.write_text(serialize_summary(summary), encoding="utf-8")
    total = sum(root["total"] for root in summary["roots"])
    print(
        f"Wrote {len(universes)} closure universes + "
        f"{_display(summary_path)} ({total} provisions)."
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument(
        "--generate",
        action="store_true",
        help="Write canonical universes and closure/summary.json.",
    )
    modes.add_argument(
        "--check",
        action="store_true",
        help="CI: validate pins/invariants and fail when artifacts drift.",
    )
    parser.add_argument(
        "--closure-dir",
        type=Path,
        default=REPO_ROOT / "closure",
        help="Closure artifact root (defaults to <repo>/closure; tests use tmpdirs).",
    )
    args = parser.parse_args(argv)
    return run(args.closure_dir, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
