"""Spec-driven compile-time overlays over a rulespec monorepo checkout.

An overlay replays an existing program composition against a different
parameter vintage without editing the source repo. The listed modules get
textual module-id rewrites (for example ``fy-2026-cola`` -> ``fy-2024-cola``),
the listed parameter rules get structural patches to their
``versions[0].formula`` value, and, when the spec has a ``version_windows``
block, every rule in each module the rewrites point at has its version window
moved onto the fiscal year that contains the caller's nominal month.

The window mapping exists because the replay cannot evaluate at a true
fiscal-year-2024 month: the shared SNAP chain's versions start 2025-10-01, so
the caller evaluates at a nominal month inside the chain's window (the SNAP QC
replay uses 2026-01, ``snap_qc_compare.NOMINAL_PERIOD``). The ``fy-2024-cola``
modules carry the FNS FY 2024 window, ``2023-10-01`` to ``2024-09-30``; a
version with an ``effective_to`` there selects nothing at the nominal month and
the engine aborts with "has no formula version". The mapping moves each version
from ``2023-10-01``..``2024-09-30`` to ``2025-10-01``..``2026-09-30`` (a version
with only ``effective_from`` keeps its open end) and leaves every formula and
value as encoded, so the engine reads FY 2024's numbers at the nominal month.

The overlay is *materialized* into a single self-contained rulespec root: it
copies the referenced top-level prefix trees (``us/``, ``us-co/``) as real
files, applies the rewrites and patches in place, and is compiled with that
root as the sole engine root — no fallback root. This
is a deliberate departure from a sparse overlay fronting the real monorepo,
which the axiom-rules-engine does not support: given two roots the engine
loads *every* root's copy of a shared module id rather than shadowing, so a
sparse copy of the composition sitting in front of the monorepo compiles both
the fy-2024-cola imports (from the overlay copy) and the fy-2026-cola imports
(from the monorepo copy) and aborts with a duplicate-rule error. Symlinking a
full mirror does not work either — the engine's module indexer does not follow
symlinked directories — and it only recognizes a root as serving the ``us:``
prefix when the root's own basename starts with ``rulespec-us``. The overlay
root therefore reuses the monorepo checkout's basename so prefix resolution is
identical, and every file it resolves is a real copy. This is the same
copy-then-patch discipline the EUROMOD platform patcher uses in
``axiom_oracles/adapters/euromod/_runner.py`` (it copies the one country XML it
edits and symlinks the rest, because its .NET engine reads files by path).

The overlay is a stopgap for a monorepo that hardcodes a vintage; the durable
fix is the parameter-set inversion tracked in
TheAxiomFoundation/rulespec-us#759, after which the fiscal year is a run-time
choice, the replay evaluates at true FY 2024 months, and the overlay retires
together with its window mapping and the nominal month.

Every mutation asserts its precondition and raises a clear error otherwise: a
rewrite that matches nothing, a patch whose from-value has drifted, or a
mapped version whose window is not the source fiscal year's (start on the
fiscal year's first day, end on its last day or open) all mean the base repo
moved and the overlay is stale. After mapping, the build checks that every
versioned rule in the program's import closure has exactly one version whose
window contains the nominal month, and raises :class:`OverlayDriftError`
naming each file and rule that does not. The build records provenance
(rewrite counts, applied patches, the window mapping with per-file rule and
version counts, and a sha256 of every changed file) so a report can prove
exactly which vintage it ran against.

The converse drift — the base repo gains a module that imports a rewritten id
but is not listed in ``rewrite_files`` — is caught after rewriting: the build
walks the program's import closure inside the overlay root and raises
:class:`OverlayDriftError` naming every module that still imports an id the
overlay rewrites. Without that check the engine sees both parameter vintages
and fails with a duplicate-rule error that names a rule, not the file
(rulespec-us#1176 added such an importer to California in 2026-07), or, when
nothing else imports the rewritten vintage, silently evaluates the old one.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from ..rulespec_roots import require_canonical_rulespec_root

OVERLAY_SPEC_SCHEMA_VERSION = "axiom_oracles.rulespec_overlay.v1"

_OVERLAYS_DIR = Path(__file__).with_name("overlays")

#: A canonical RuleSpec import prefix (``us``, ``us-ca``), mirroring the
#: engine's ``is_canonical_repo_prefix``: lowercase ASCII, digits, ``-``, ``_``.
_CANONICAL_PREFIX = re.compile(r"[a-z0-9_-]+")


class OverlayDriftError(ValueError):
    """The base repo moved under the overlay, so the overlay is stale.

    Raised when a module in the overlaid program's import closure still
    imports a module id the overlay rewrites (the base repo gained an importer
    that the spec's ``rewrite_files`` does not list), when a version the
    window mapping would move does not carry the source fiscal year's window,
    or when a versioned rule in the closure does not have exactly one version
    in force at the nominal month after the mapping."""


@dataclass(frozen=True)
class ParameterPatch:
    """A structural patch to one parameter rule's ``versions[0].formula``."""

    file: str
    rule: str
    from_value: str
    to_value: str
    source: str


@dataclass(frozen=True)
class VersionWindowMapping:
    """Move the rewrite targets' versions off ``source_fiscal_year``.

    Every rule in each module a ``module_id_rewrites`` value names must carry
    one version whose window is the source fiscal year (federal: October 1 of
    the prior year to September 30); the build moves it onto the fiscal year
    that contains the nominal month it is given.
    """

    source_fiscal_year: int


@dataclass(frozen=True)
class OverlaySpec:
    """A parsed ``axiom_oracles.rulespec_overlay.v1`` overlay spec."""

    name: str
    program: str
    notes: str
    module_id_rewrites: dict[str, str]
    rewrite_files: tuple[str, ...]
    parameter_patches: tuple[ParameterPatch, ...]
    version_windows: VersionWindowMapping | None = None


@dataclass(frozen=True)
class OverlayBuild:
    """A built sparse overlay tree ready to front a monorepo root."""

    overlay_root: Path
    program_path: Path
    provenance: dict[str, Any]


def load_overlay_spec(name_or_path: str | Path) -> OverlaySpec:
    """Load an overlay spec by packaged name or from an explicit path.

    A bare name (``"us-co-snap-fy2024"``) resolves to the packaged spec under
    ``axiom_oracles/bridges/overlays/``. A path, or a string that ends in
    ``.yaml`` / contains a path separator, is loaded directly.
    """
    path = _resolve_spec_path(name_or_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"overlay spec {path} must be a mapping")
    schema = data.get("schema")
    if schema != OVERLAY_SPEC_SCHEMA_VERSION:
        raise ValueError(
            f"overlay spec {path} has schema {schema!r}, "
            f"expected {OVERLAY_SPEC_SCHEMA_VERSION!r}"
        )
    rewrites = data.get("module_id_rewrites") or {}
    if not isinstance(rewrites, dict) or not rewrites:
        raise ValueError(f"overlay spec {path} needs a non-empty module_id_rewrites")

    def _require(mapping: dict, key: str, where: str) -> str:
        if key not in mapping:
            raise ValueError(f"overlay spec {path}: {where} is missing {key!r}")
        return str(mapping[key])

    patches = tuple(
        ParameterPatch(
            file=_require(entry, "file", f"parameter_patches[{index}]"),
            rule=_require(entry, "rule", f"parameter_patches[{index}]"),
            from_value=_require(entry, "from", f"parameter_patches[{index}]"),
            to_value=_require(entry, "to", f"parameter_patches[{index}]"),
            source=str(entry.get("source", "")),
        )
        for index, entry in enumerate(data.get("parameter_patches", []) or [])
    )
    version_windows = None
    raw_windows = data.get("version_windows")
    if raw_windows is not None:
        if not isinstance(raw_windows, dict):
            raise ValueError(f"overlay spec {path}: version_windows must be a mapping")
        fiscal_year = _require(raw_windows, "source_fiscal_year", "version_windows")
        if not re.fullmatch(r"[0-9]{4}", fiscal_year):
            raise ValueError(
                f"overlay spec {path}: version_windows.source_fiscal_year must be "
                f"a four-digit year, not {fiscal_year!r}"
            )
        version_windows = VersionWindowMapping(source_fiscal_year=int(fiscal_year))
    return OverlaySpec(
        name=_require(data, "name", "the spec"),
        program=_require(data, "program", "the spec"),
        notes=str(data.get("notes", "")),
        module_id_rewrites={str(k): str(v) for k, v in rewrites.items()},
        rewrite_files=tuple(str(item) for item in data.get("rewrite_files", []) or []),
        parameter_patches=patches,
        version_windows=version_windows,
    )


def _resolve_spec_path(name_or_path: str | Path) -> Path:
    if isinstance(name_or_path, Path):
        return name_or_path
    text = str(name_or_path)
    if text.endswith(".yaml") or "/" in text or "\\" in text:
        return Path(text)
    packaged = _OVERLAYS_DIR / f"{text}.yaml"
    if not packaged.exists():
        available = sorted(p.stem for p in _OVERLAYS_DIR.glob("*.yaml"))
        raise FileNotFoundError(
            f"no packaged overlay spec named {text!r}; available: {available}"
        )
    return packaged


def build_overlay(
    spec: OverlaySpec,
    rulespec_root: str | Path,
    dest_dir: str | Path,
    *,
    nominal_month: date | None = None,
) -> OverlayBuild:
    """Materialize ``spec`` as a single self-contained rulespec root.

    Copies the top-level prefix trees the spec touches (derived from the
    program path, ``rewrite_files``, ``parameter_patches``, and, with
    ``version_windows``, the rewrite targets) as real files into an overlay
    root that reuses ``rulespec_root``'s basename, then applies the module-id
    rewrites (asserting at least one replacement per file), the structural
    parameter patches (asserting each rule's ``versions[0].formula`` equals
    its from-value), and the version-window mapping (asserting every mapped
    version carries the source fiscal year's window, then that every versioned
    rule in the program's import closure has exactly one version in force at
    ``nominal_month``). A spec with ``version_windows`` needs
    ``nominal_month``, the date the caller will evaluate at. The overlay root
    is the sole repo root the engine should be given. Returns the overlay
    root, the path to the overlaid program composition, and a provenance dict.

    ``rulespec_root`` must be a canonical ``rulespec-<country>`` checkout
    (:mod:`axiom_oracles.rulespec_roots`), so the overlay is always derived
    from one; anything else raises ``ValueError`` before any copy.
    """
    rulespec_root = require_canonical_rulespec_root(rulespec_root)
    if spec.version_windows is not None and nominal_month is None:
        raise ValueError(
            f"overlay {spec.name} maps version windows onto a nominal month; "
            f"pass nominal_month, the date the engine will evaluate at"
        )
    overlay_root = Path(dest_dir) / rulespec_root.name

    for prefix in _prefix_dirs(spec):
        source = rulespec_root / prefix
        if not source.exists():
            raise ValueError(
                f"overlay {spec.name}: prefix directory {prefix} not found under "
                f"{rulespec_root}; the base repo moved and the overlay is stale"
            )
        # Hardlink where possible (the trees run to thousands of files while
        # the overlay modifies ~17); modified files are re-written through
        # _write_text_unlinked, which replaces the link with a fresh inode so
        # the source repo is never mutated through a shared link.
        shutil.copytree(
            source,
            overlay_root / prefix,
            dirs_exist_ok=True,
            symlinks=False,
            copy_function=_link_or_copy,
        )

    rewrite_counts: dict[str, int] = {}
    changed: list[str] = []
    for relative in spec.rewrite_files:
        target = overlay_root / relative
        if not target.exists():
            raise ValueError(
                f"overlay {spec.name}: rewrite file {relative} not materialized; "
                f"the base repo moved and the overlay is stale"
            )
        text, count = _rewrite_module_ids(
            target.read_text(encoding="utf-8"), spec.module_id_rewrites
        )
        if count < 1:
            raise ValueError(
                f"overlay {spec.name}: no module-id rewrites matched in {relative}; "
                f"the base repo moved and the overlay is stale"
            )
        _write_text_unlinked(target, text)
        rewrite_counts[relative] = count
        changed.append(relative)

    patch_records: list[dict[str, str]] = []
    for patch in spec.parameter_patches:
        target = overlay_root / patch.file
        if not target.exists():
            raise ValueError(
                f"overlay {spec.name}: patch file {patch.file} not materialized; "
                f"the base repo moved and the overlay is stale"
            )
        data = yaml.safe_load(target.read_text(encoding="utf-8"))
        _apply_parameter_patch(data, patch, spec.name)
        _write_text_unlinked(
            target,
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=1_000_000),
        )
        if patch.file not in changed:
            changed.append(patch.file)
        patch_records.append(
            {
                "file": patch.file,
                "rule": patch.rule,
                "from": patch.from_value,
                "to": patch.to_value,
                "source": patch.source,
            }
        )

    window_record: dict[str, Any] | None = None
    if spec.version_windows is not None:
        assert nominal_month is not None  # checked on entry
        window_record = _apply_version_windows(
            spec, overlay_root, spec.version_windows, nominal_month
        )
        for relative in window_record["files"]:
            if relative not in changed:
                changed.append(relative)

    unrewritten = find_unrewritten_importers(
        overlay_root, spec.program, spec.module_id_rewrites
    )
    if unrewritten:
        listing = "; ".join(
            f"{relative} imports {', '.join(imports)}"
            for relative, imports in unrewritten.items()
        )
        raise OverlayDriftError(
            f"overlay {spec.name}: {len(unrewritten)} module(s) in the import "
            f"closure of {spec.program} still import module ids this overlay "
            f"rewrites ({listing}). The compiled program would mix parameter "
            f"vintages (the engine reports that as a duplicate-rule error, or "
            f"silently evaluates the unrewritten vintage). Add each file to the "
            f"spec's rewrite_files; the base repo moved and the overlay is stale"
        )

    if nominal_month is not None:
        uncovered = rules_without_one_version_at(
            overlay_root, spec.program, nominal_month
        )
        if uncovered:
            listing = "; ".join(
                f"{relative}#{rule} has {count}"
                for relative, rule, count in uncovered[:20]
            )
            more = f" (and {len(uncovered) - 20} more)" if len(uncovered) > 20 else ""
            raise OverlayDriftError(
                f"overlay {spec.name}: {len(uncovered)} versioned rule(s) in the "
                f"import closure of {spec.program} do not have exactly one version "
                f"in force at the nominal month {nominal_month.isoformat()} "
                f"({listing}{more}); the engine would abort with no formula "
                f"version, or pick between overlapping ones. The base repo moved "
                f"and the overlay is stale"
            )

    file_sha256 = {relative: _sha256(overlay_root / relative) for relative in changed}
    # overlay_root (the per-run materialization tempdir) is deliberately NOT
    # recorded: it is nondeterministic machine-local state that would make
    # committed reports differ run-to-run; file_sha256 already pins the
    # materialized content and rulespec_root pins the checkout replayed.
    provenance = {
        "overlay": spec.name,
        "schema": OVERLAY_SPEC_SCHEMA_VERSION,
        "program": spec.program,
        "rulespec_root": str(rulespec_root),
        "module_id_rewrites": dict(spec.module_id_rewrites),
        "rewrite_counts": rewrite_counts,
        "patches": patch_records,
        "file_sha256": file_sha256,
    }
    if window_record is not None:
        provenance["version_windows"] = window_record
    return OverlayBuild(
        overlay_root=overlay_root,
        program_path=overlay_root / spec.program,
        provenance=provenance,
    )


def find_unrewritten_importers(
    overlay_root: str | Path,
    program: str,
    module_id_rewrites: dict[str, str],
) -> dict[str, list[str]]:
    """Map each closure module that still imports a rewritten id to those imports.

    Walks the import closure of ``program`` (a path relative to
    ``overlay_root``) through every module's ``imports`` list and ``extends``
    base, resolving them the way the axiom-rules-engine loader does for a
    single country-monorepo root: a canonical ``prefix:path`` import is the
    file ``<overlay_root>/<prefix>/<path>.yaml``, and a relative import
    resolves against the importing file's directory; a ``#fragment`` and
    surrounding quotes are ignored. An import is flagged when the overlay's
    own rewrite pattern would still change its resolved module id, i.e. the
    id is one the overlay was meant to rewrite. Imports that do not resolve to
    a file inside the overlay root are not followed (the engine reports those
    itself). Returns ``{relative file: [offending imports]}`` in walk order;
    empty when the closure is clean.
    """
    root_resolved = Path(overlay_root).resolve()
    offenders: dict[str, list[str]] = {}
    for relative, _data, references in _walk_import_closure(overlay_root, program):
        for raw, target in references:
            module_id = _module_id_for_path(root_resolved, target) or raw
            if _rewrite_module_ids(module_id, module_id_rewrites)[1]:
                offenders.setdefault(relative, []).append(raw.strip())
    return offenders


def rules_without_one_version_at(
    overlay_root: str | Path,
    program: str,
    on: date,
) -> list[tuple[str, str, int]]:
    """List the versioned rules in ``program``'s closure not in force once at ``on``.

    Walks the same import closure as :func:`find_unrewritten_importers` and
    counts the versions whose window contains ``on``; the engine's window test is
    ``effective_from <= on`` and, when ``effective_to`` is set,
    ``on <= effective_to`` (``from`` and ``to`` are the loader's aliases). A
    non-empty ``versions`` list takes precedence over top-level fields.
    Otherwise, a non-null top-level ``formula`` or ``effective_from`` (or
    ``from``) synthesizes one version carrying the top-level window, just as
    the engine's ``RuleDefinition::effective_versions`` does. Rules with neither are
    skipped. Returns ``(relative file, rule name, number of versions in force)``
    for every rule where that number is not exactly
    one, in walk order; empty when every versioned rule resolves.
    """
    offenders: list[tuple[str, str, int]] = []
    for relative, data, _references in _walk_import_closure(overlay_root, program):
        rules = data.get("rules")
        if not isinstance(rules, list):
            continue
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            versions = rule.get("versions")
            if not isinstance(versions, list) or not versions:
                _, start = _version_date(rule, "effective_from", "from")
                if rule.get("formula") is None and start is None:
                    continue
                versions = [rule]
            in_force = sum(
                1
                for version in versions
                if isinstance(version, dict) and _window_contains(version, on)
            )
            if in_force != 1:
                offenders.append((relative, str(rule.get("name")), in_force))
    return offenders


def _walk_import_closure(
    overlay_root: str | Path, program: str
) -> list[tuple[str, dict[str, Any], list[tuple[str, Path]]]]:
    """``(relative file, parsed module, [(raw reference, target path)])`` per
    module in ``program``'s import closure, breadth first.

    Follows ``imports`` and ``extends`` as :func:`find_unrewritten_importers`
    documents; files outside the root, missing files, and files that do not
    parse to a mapping are not followed.
    """
    root = Path(overlay_root)
    root_resolved = root.resolve()
    queue: list[Path] = [root / program]
    seen: set[Path] = set()
    modules: list[tuple[str, dict[str, Any], list[tuple[str, Path]]]] = []
    while queue:
        path = queue.pop(0)
        resolved = path.resolve()
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        try:
            resolved.relative_to(root_resolved)
        except ValueError:
            continue
        try:
            data = yaml.safe_load(resolved.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue  # not ours to diagnose; the engine rejects it by name
        if not isinstance(data, dict):
            continue
        relative = resolved.relative_to(root_resolved).as_posix()
        references: list[tuple[str, Path]] = []
        imports = data.get("imports") or []
        if isinstance(imports, list):
            for entry in imports:
                if isinstance(entry, str):
                    target = _resolve_import_path(root, resolved, entry)
                    if target is not None:
                        references.append((entry, target))
        extends = data.get("extends")
        if isinstance(extends, str) and extends.strip():
            references.append((extends, resolved.parent / extends.strip()))
        modules.append((relative, data, references))
        queue.extend(target for _raw, target in references)
    return modules


def fiscal_year_window(fiscal_year: int) -> tuple[date, date]:
    """Federal fiscal year ``fiscal_year``: October 1 of the prior year to
    September 30, both inclusive."""
    return date(fiscal_year - 1, 10, 1), date(fiscal_year, 9, 30)


def fiscal_year_containing(day: date) -> int:
    """The federal fiscal year that contains ``day``."""
    return day.year + 1 if day.month >= 10 else day.year


def _version_date(version: dict[str, Any], key: str, alias: str) -> tuple[str | None, date | None]:
    """``(key used, parsed date)`` for one window bound, honoring the alias."""
    for name in (key, alias):
        if name in version:
            value = version[name]
            if value is None:
                return name, None
            if isinstance(value, date):
                return name, value
            return name, date.fromisoformat(str(value).strip())
    return None, None


def _window_contains(version: dict[str, Any], on: date) -> bool:
    _, start = _version_date(version, "effective_from", "from")
    _, end = _version_date(version, "effective_to", "to")
    return (start is None or start <= on) and (end is None or on <= end)


def _module_id_file(module_id: str) -> str | None:
    """``us:policies/x#rule`` -> ``us/policies/x.yaml`` (None if not canonical)."""
    target = module_id.split("#", 1)[0].strip()
    prefix, sep, rest = target.partition(":")
    rest = rest.strip().strip("/")
    if not sep or not _CANONICAL_PREFIX.fullmatch(prefix) or not rest:
        return None
    if ".." in Path(rest).parts:
        return None
    return f"{prefix}/{_with_yaml_suffix(rest)}"


def _window_mapping_files(spec: OverlaySpec) -> list[str]:
    """The files of the modules the rewrites point at, in spec order."""
    files: list[str] = []
    for target in spec.module_id_rewrites.values():
        relative = _module_id_file(target)
        if relative is None:
            raise ValueError(
                f"overlay {spec.name}: version_windows needs every "
                f"module_id_rewrites value to be a canonical module id "
                f"(prefix:path), not {target!r}"
            )
        if relative not in files:
            files.append(relative)
    return files


def _apply_version_windows(
    spec: OverlaySpec,
    overlay_root: Path,
    mapping: VersionWindowMapping,
    nominal_month: date,
) -> dict[str, Any]:
    """Move every rewrite-target version onto the nominal month's fiscal year.

    Precondition, per rule with versions: exactly one version, starting on the
    source fiscal year's first day and either ending on its last day or open.
    No mapped rule may carry a top-level window or formula, even alongside
    ``versions`` (the mapping would leave those fields untouched). Anything
    else raises :class:`OverlayDriftError` naming the file and rule. Formulas
    and values are never touched. Returns the provenance record.
    """
    source_start, source_end = fiscal_year_window(mapping.source_fiscal_year)
    target_fiscal_year = fiscal_year_containing(nominal_month)
    target_start, target_end = fiscal_year_window(target_fiscal_year)
    files: dict[str, dict[str, int]] = {}
    for relative in _window_mapping_files(spec):
        target = overlay_root / relative
        if not target.exists():
            raise ValueError(
                f"overlay {spec.name}: version-window module {relative} not "
                f"materialized; the base repo moved and the overlay is stale"
            )
        data = yaml.safe_load(target.read_text(encoding="utf-8"))
        rules = data.get("rules") if isinstance(data, dict) else None
        if not isinstance(rules, list):
            raise OverlayDriftError(
                f"overlay {spec.name}: {relative} has no rules list to map; "
                f"the base repo moved and the overlay is stale"
            )
        counts = {"rules": 0, "closed_versions": 0, "open_versions": 0}
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            name = rule.get("name")
            versions = rule.get("versions")
            stray = sorted(
                key
                for key in ("effective_from", "from", "effective_to", "to", "formula")
                if key in rule
            )
            if stray:
                raise OverlayDriftError(
                    f"overlay {spec.name}: {relative}#{name} carries "
                    f"{', '.join(stray)} outside a versions list, which the "
                    f"window mapping does not move; the base repo moved and "
                    f"the overlay is stale"
                )
            if not versions:
                continue
            if not isinstance(versions, list) or len(versions) != 1:
                count = len(versions) if isinstance(versions, list) else versions
                raise OverlayDriftError(
                    f"overlay {spec.name}: {relative}#{name} has {count} versions, "
                    f"expected exactly one for the FY {mapping.source_fiscal_year} "
                    f"window; the base repo moved and the overlay is stale"
                )
            version = versions[0]
            if not isinstance(version, dict):
                raise OverlayDriftError(
                    f"overlay {spec.name}: {relative}#{name} versions[0] is not a "
                    f"mapping; the base repo moved and the overlay is stale"
                )
            try:
                from_key, start = _version_date(version, "effective_from", "from")
                to_key, end = _version_date(version, "effective_to", "to")
            except ValueError as error:
                raise OverlayDriftError(
                    f"overlay {spec.name}: {relative}#{name} versions[0] has an "
                    f"unreadable window ({error}); the base repo moved and the "
                    f"overlay is stale"
                ) from error
            if from_key is None or start != source_start or end not in (None, source_end):
                shown_end = end.isoformat() if end is not None else "open"
                shown_start = start.isoformat() if start is not None else "none"
                raise OverlayDriftError(
                    f"overlay {spec.name}: {relative}#{name} versions[0] window is "
                    f"{shown_start}..{shown_end}, expected "
                    f"{source_start.isoformat()}..{source_end.isoformat()} (or an "
                    f"open end), the FY {mapping.source_fiscal_year} window; the "
                    f"base repo moved and the overlay is stale"
                )
            version[from_key] = target_start.isoformat()
            if end is None:
                counts["open_versions"] += 1
            else:
                assert to_key is not None
                version[to_key] = target_end.isoformat()
                counts["closed_versions"] += 1
            counts["rules"] += 1
        if counts["rules"] == 0:
            raise OverlayDriftError(
                f"overlay {spec.name}: {relative} has no versioned rules to map; "
                f"the base repo moved and the overlay is stale"
            )
        _write_text_unlinked(
            target,
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=1_000_000),
        )
        files[relative] = counts
    return {
        "nominal_month": nominal_month.isoformat(),
        "source_fiscal_year": mapping.source_fiscal_year,
        "source_window": [source_start.isoformat(), source_end.isoformat()],
        "target_fiscal_year": target_fiscal_year,
        "target_window": [target_start.isoformat(), target_end.isoformat()],
        "files": files,
    }


def _resolve_import_path(root: Path, importer: Path, entry: str) -> Path | None:
    """Resolve one ``imports`` entry to its file, mirroring the engine loader."""
    target = entry.strip().strip("\"'")
    target = target.split("#", 1)[0].strip()
    if not target:
        return None
    prefix, sep, rest = target.partition(":")
    if sep and _CANONICAL_PREFIX.fullmatch(prefix):
        rest = rest.strip().strip("/")
        if not rest or ".." in Path(rest).parts:
            return None
        return root / prefix / _with_yaml_suffix(rest)
    if target.startswith("/"):
        return None
    return importer.parent / _with_yaml_suffix(target)


def _with_yaml_suffix(target: str) -> str:
    return target if target.endswith((".yaml", ".yml")) else f"{target}.yaml"


def _module_id_for_path(root: Path, path: Path) -> str | None:
    """``<root>/us-ca/policies/x.yaml`` -> ``us-ca:policies/x`` (None if outside)."""
    try:
        parts = path.resolve().relative_to(root).parts
    except ValueError:
        return None
    if len(parts) < 2:
        return None
    rest = "/".join(parts[1:])
    for suffix in (".yaml", ".yml"):
        if rest.endswith(suffix):
            rest = rest[: -len(suffix)]
            break
    return f"{parts[0]}:{rest}"


def _prefix_dirs(spec: OverlaySpec) -> list[str]:
    """Top-level prefix directories the spec's files live under (for example
    ``us`` and ``us-co``). These are the trees materialized into the overlay."""
    prefixes = {Path(spec.program).parts[0]}
    prefixes.update(Path(relative).parts[0] for relative in spec.rewrite_files)
    prefixes.update(Path(patch.file).parts[0] for patch in spec.parameter_patches)
    if spec.version_windows is not None:
        prefixes.update(
            Path(relative).parts[0] for relative in _window_mapping_files(spec)
        )
    return sorted(prefixes)


def rewrite_output_ids(
    output_id_by_label: dict[str, str],
    module_id_rewrites: dict[str, str],
) -> dict[str, str]:
    """Apply the overlay's module-id rewrites to a label -> output-id map.

    Output ids that reference a rewritten module (for example a
    ``fy-2026-cola`` parameter) must be queried under the overlaid id, so the
    comparison rewrites them the same way the module files were rewritten.
    """
    return {
        label: _rewrite_module_ids(output_id, module_id_rewrites)[0]
        for label, output_id in output_id_by_label.items()
    }


def _link_or_copy(source: str, destination: str) -> None:
    """Hardlink ``source`` to ``destination``, copying when linking cannot work
    (cross-device destinations, filesystems without hardlinks)."""
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def _write_text_unlinked(target: Path, text: str) -> None:
    """Write ``text`` to ``target`` through a fresh inode.

    Overlay trees are hardlinked from the source repo, so an in-place write
    would mutate the original file through the shared link; writing a sibling
    temp file and replacing the target breaks the link first.
    """
    temp = target.with_name(target.name + ".overlay-tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, target)


def _rewrite_module_ids(text: str, rewrites: dict[str, str]) -> tuple[str, int]:
    """Rewrite module ids in one pass over the text.

    A single alternation (longest ids first) replaces every occurrence
    simultaneously, so one pair's replacement can never be re-matched by a
    later pair — sequential ``str.replace`` chains would let
    ``{a: b, b: c}`` rewrite ``a`` all the way to ``c``.
    """
    if not rewrites:
        return text, 0
    pattern = re.compile(
        "|".join(
            re.escape(old) for old in sorted(rewrites, key=len, reverse=True)
        )
    )
    count = 0

    def _substitute(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return rewrites[match.group(0)]

    return pattern.sub(_substitute, text), count


def _apply_parameter_patch(data: Any, patch: ParameterPatch, overlay_name: str) -> None:
    rules = data.get("rules") if isinstance(data, dict) else None
    if not isinstance(rules, list):
        raise ValueError(
            f"overlay {overlay_name}: {patch.file} has no rules list to patch"
        )
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("name") != patch.rule:
            continue
        versions = rule.get("versions")
        if not isinstance(versions, list) or not versions:
            raise ValueError(
                f"overlay {overlay_name}: rule {patch.rule!r} in {patch.file} "
                f"has no versions to patch"
            )
        current = versions[0].get("formula")
        if str(current) != patch.from_value:
            raise ValueError(
                f"overlay {overlay_name}: {patch.file}#{patch.rule} "
                f"versions[0].formula is {current!r}, expected {patch.from_value!r}; "
                f"the base repo moved and the overlay is stale"
            )
        versions[0]["formula"] = patch.to_value
        return
    raise ValueError(
        f"overlay {overlay_name}: rule {patch.rule!r} not found in {patch.file}"
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
