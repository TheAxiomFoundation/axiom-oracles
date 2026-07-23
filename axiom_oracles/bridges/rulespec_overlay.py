"""Spec-driven compile-time overlays over a rulespec monorepo checkout.

An overlay replays an existing program composition against a different
parameter vintage without editing the source repo. The listed modules get
textual module-id rewrites (for example ``fy-2026-cola`` -> ``fy-2024-cola``)
and the listed parameter rules get structural patches to their
``versions[0].formula`` value.

The overlay is *materialized* into a single self-contained rulespec root: it
copies the referenced top-level prefix trees (``us/``, ``us-co/``) as real
files, applies the rewrites and patches in place, and is compiled with that
root as the sole ``AXIOM_RULESPEC_REPO_ROOTS`` entry — no fallback root. This
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
choice and the overlay retires.

Every mutation asserts its precondition and raises a clear error otherwise: a
rewrite that matches nothing, or a patch whose from-value has drifted, both
mean the base repo moved and the overlay is stale. The build records
provenance (rewrite counts, applied patches, and a sha256 of every changed
file) so a report can prove exactly which vintage it ran against.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

OVERLAY_SPEC_SCHEMA_VERSION = "axiom_oracles.rulespec_overlay.v1"

_OVERLAYS_DIR = Path(__file__).with_name("overlays")


@dataclass(frozen=True)
class ParameterPatch:
    """A structural patch to one parameter rule's ``versions[0].formula``."""

    file: str
    rule: str
    from_value: str
    to_value: str
    source: str


@dataclass(frozen=True)
class OverlaySpec:
    """A parsed ``axiom_oracles.rulespec_overlay.v1`` overlay spec."""

    name: str
    program: str
    notes: str
    module_id_rewrites: dict[str, str]
    rewrite_files: tuple[str, ...]
    parameter_patches: tuple[ParameterPatch, ...]


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
    return OverlaySpec(
        name=_require(data, "name", "the spec"),
        program=_require(data, "program", "the spec"),
        notes=str(data.get("notes", "")),
        module_id_rewrites={str(k): str(v) for k, v in rewrites.items()},
        rewrite_files=tuple(str(item) for item in data.get("rewrite_files", []) or []),
        parameter_patches=patches,
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
) -> OverlayBuild:
    """Materialize ``spec`` as a single self-contained rulespec root.

    Copies the top-level prefix trees the spec touches (derived from the
    program path, ``rewrite_files``, and ``parameter_patches``) as real files
    into an overlay root that reuses ``rulespec_root``'s basename, then applies
    the module-id rewrites (asserting at least one replacement per file) and
    the structural parameter patches (asserting each rule's
    ``versions[0].formula`` equals its from-value). The overlay root is the
    sole repo root the engine should be given. Returns the overlay root, the
    path to the overlaid program composition, and a provenance dict.
    """
    rulespec_root = Path(rulespec_root)
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
    return OverlayBuild(
        overlay_root=overlay_root,
        program_path=overlay_root / spec.program,
        provenance=provenance,
    )


def _prefix_dirs(spec: OverlaySpec) -> list[str]:
    """Top-level prefix directories the spec's files live under (for example
    ``us`` and ``us-co``). These are the trees materialized into the overlay."""
    prefixes = {Path(spec.program).parts[0]}
    prefixes.update(Path(relative).parts[0] for relative in spec.rewrite_files)
    prefixes.update(Path(patch.file).parts[0] for patch in spec.parameter_patches)
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
