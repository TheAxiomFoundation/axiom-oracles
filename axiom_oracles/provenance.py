"""Provenance blocks for comparison reports (O2).

A checked-in comparison report should record exactly what produced it, so a
reader can answer "is this number stale, and against which rules/engine/data
did it run" without re-deriving anything. :func:`build_provenance` assembles
that block from the pieces the runner already has in hand; it is intentionally
tolerant — every field degrades to ``None``/absent rather than raising, because
a provenance stamp must never be the thing that fails a run.

The block shape (``axiom_oracles.provenance.v1``)::

    provenance:
      schema: axiom_oracles.provenance.v1
      generated_at: 2026-07-05T12:00:00Z
      generated_by: scripts/run_comparison.py::fiit-ecps
      run_kind: weekly | pr-triggered | manual
      rulespecs:                       # the rulespec repos the cases ran against
        - repo: TheAxiomFoundation/rulespec-us
          sha: 9c1f2ab…                 # 40-hex, or None when unresolved
      engine:                          # the Axiom side under test
        axiom_rules_engine_sha: …      # git SHA of the engine checkout
        axiom_rules_engine_version: …  # crate version if resolvable
      oracle:                          # the oracle side it was compared to
        name: policyengine             # or euromod
        policyengine_package: policyengine==4.11.0
        policyengine_us: 1.729.0
        # …or, for EUROMOD:
        euromod_release: J2.0
        euromod_system: BE_2025
        euromod_dataset: BE_2024_c1_2015_03_e2
      dataset:                         # reuse the pinned-populace identity (#80/#952)
        source: populace-hf
        repo_id: policyengine/populace-us
        filename: populace_us_2024.h5
        revision: populace-us-2024-…
        sha256: 16be6338…              # 12-hex prefix
        built_with: 1.729.0

Only ``schema`` and ``generated_at`` are guaranteed present. ``run_kind`` is a
free-form-but-validated enum (see :data:`RUN_KINDS`) resolved from the
``AXIOM_ORACLES_RUN_KIND`` environment variable, defaulting to ``manual`` so a
local run is never mislabeled as a scheduled one.
"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from axiom_oracles.bridges.repo_routing import canonical_rulespec_checkout_name

PROVENANCE_SCHEMA_VERSION = "axiom_oracles.provenance.v1"

#: Canonical RuleSpec country checkouts all live under this owner.
RULESPEC_OWNER = "TheAxiomFoundation"

#: Valid ``run_kind`` values. ``weekly`` = the full backstop matrix,
#: ``pr-triggered`` = a PR CI run, ``affected-rerun`` = the 6-hourly
#: stale-suite sweep, ``manual`` = a local/ad-hoc run (the default).
RUN_KINDS = ("weekly", "pr-triggered", "affected-rerun", "manual")

_RUN_KIND_ENV = "AXIOM_ORACLES_RUN_KIND"
_GENERATED_BY_ENV = "AXIOM_ORACLES_GENERATED_BY"


def resolve_run_kind(default: str = "manual") -> str:
    """Return the run kind from the environment, validated against RUN_KINDS."""
    value = (os.environ.get(_RUN_KIND_ENV) or "").strip().lower()
    if value in RUN_KINDS:
        return value
    return default


def _git_sha(repo: Path) -> str | None:
    """Best-effort 40-hex HEAD SHA of a git checkout; None if unavailable."""
    if repo is None:
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
    sha = result.stdout.strip()
    return sha or None


def rulespec_provenance(paths: list[Path | str] | None) -> list[dict[str, Any]]:
    """Resolve ``{repo, sha}`` provenance for each rulespec checkout path.

    Every path must name one exact ``rulespec-<country>`` checkout. Missing
    canonical paths may be recorded with a null SHA when a licensed comparison
    is skipped, but flat roots, aliases, workspaces, symlinks, and Git-origin
    identity inference are rejected. Deduplicated on ``(repo, sha)``.
    """
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str | None, str | None]] = set()
    for raw in paths or []:
        path = Path(os.path.expandvars(os.path.expanduser(str(raw))))
        name = canonical_rulespec_checkout_name(path, require_exists=False)
        if name is None:
            raise ValueError(
                f"RuleSpec provenance path is not an exact canonical checkout: {path}"
            )
        repo = canonical_rulespec_slug(name)
        sha = _git_sha(path) if path.exists() else None
        key = (repo, sha)
        if key in seen:
            continue
        seen.add(key)
        entries.append({"repo": repo, "sha": sha})
    return entries


def canonical_rulespec_slug(name: str) -> str:
    """Return the one canonical owner/country-checkout slug or raise."""

    bare = name.removeprefix(f"{RULESPEC_OWNER}/")
    if re.fullmatch(r"rulespec-[a-z]{2}", bare) is None:
        raise ValueError(f"not a canonical RuleSpec country checkout: {name!r}")
    if "/" in name and name != f"{RULESPEC_OWNER}/{bare}":
        raise ValueError(f"not a canonical RuleSpec repository slug: {name!r}")
    return f"{RULESPEC_OWNER}/{bare}"


def build_provenance(
    *,
    generated_by: str,
    run_kind: str | None = None,
    rulespecs: list[dict[str, Any]] | None = None,
    engine: dict[str, Any] | None = None,
    oracle: dict[str, Any] | None = None,
    dataset: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Assemble a provenance block. Empty sub-blocks are omitted, not null."""
    # The caller's per-suite `generated_by` (e.g. run_comparison.py::<suite>)
    # wins — it carries the suite suffix that makes the field identifying. The
    # env var is only a fallback for callers that pass nothing meaningful, so a
    # one-time `export` can't silently flatten every suite to one label.
    block: dict[str, Any] = {
        "schema": PROVENANCE_SCHEMA_VERSION,
        "generated_at": generated_at
        or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_by": generated_by or os.environ.get(_GENERATED_BY_ENV) or "unknown",
        "run_kind": run_kind or resolve_run_kind(),
    }
    if rulespecs:
        block["rulespecs"] = rulespecs
    if engine:
        block["engine"] = {k: v for k, v in engine.items() if v is not None}
    if oracle:
        block["oracle"] = {k: v for k, v in oracle.items() if v is not None}
    if dataset:
        block["dataset"] = {k: v for k, v in dataset.items() if v is not None}
    return block


def engine_provenance(axiom_engine_repo: Path | str | None) -> dict[str, Any]:
    """Axiom-side engine identity: git SHA + crate version if resolvable."""
    repo = (
        Path(os.path.expandvars(os.path.expanduser(str(axiom_engine_repo))))
        if axiom_engine_repo
        else None
    )
    return {
        "axiom_rules_engine_sha": _git_sha(repo) if repo else None,
        "axiom_rules_engine_version": _crate_version(repo) if repo else None,
    }


def _crate_version(repo: Path) -> str | None:
    """Parse ``version = "…"`` from the engine crate's Cargo.toml (top table)."""
    for candidate in (repo / "Cargo.toml",):
        if not candidate.exists():
            continue
        in_package = False
        try:
            for line in candidate.read_text().splitlines():
                stripped = line.strip()
                if stripped.startswith("["):
                    in_package = stripped == "[package]"
                    continue
                if in_package and stripped.startswith("version"):
                    _, _, rhs = stripped.partition("=")
                    return rhs.strip().strip('"').strip("'") or None
        except OSError:
            return None
    return None


def dataset_provenance_from_identity(
    identity: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Normalize the encode/populace ``dataset_identity`` block into provenance.

    Reuses the pinned-populace identity fields threaded from axiom-encode#952 /
    populace#80 (``source``/``repo_id``/``filename``/``revision``/``sha256``/
    ``built_with``). Returns None when identity is absent so the caller can omit
    the sub-block entirely.
    """
    if not identity:
        return None
    keep = (
        "source",
        "repo_id",
        "filename",
        "revision",
        "sha256",
        "built_with",
        "country",
    )
    out = {k: identity[k] for k in keep if identity.get(k) is not None}
    return out or None
