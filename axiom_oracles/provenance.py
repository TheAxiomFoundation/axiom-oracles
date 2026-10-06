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
        axiom_rules_engine_sha: …      # git SHA of the axiom-rules checkout
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
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROVENANCE_SCHEMA_VERSION = "axiom_oracles.provenance.v1"

#: Rulespec repos all live under this owner. A bare ``rulespec-*`` directory
#: basename (from a local rsync'd root with no git remote) is canonicalized to
#: ``<OWNER>/<basename>`` so a report's ``rulespecs[].repo`` slug matches the
#: affected-map's keys and ``select_affected_suites.py`` can diff SHAs.
RULESPEC_OWNER = "TheAxiomFoundation"

#: Local checkout directory basenames that differ from the upstream repo name.
_RULESPEC_DIR_ALIASES = {"rulespec-uk-official": "rulespec-uk"}

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


def _remote_url(repo: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
    return result.stdout.strip() or None


def repo_slug_from_remote(url: str | None) -> str | None:
    """Reduce a git remote URL to its ``owner/repo`` slug.

    Handles both ``git@github.com:Owner/repo.git`` and
    ``https://github.com/Owner/repo(.git)`` forms. Returns None for anything
    that is not obviously a GitHub-style remote.
    """
    if not url:
        return None
    url = url.strip()
    if url.endswith(".git"):
        url = url[: -len(".git")]
    if url.startswith("git@") and ":" in url:
        url = url.split(":", 1)[1]
    elif "github.com/" in url:
        url = url.split("github.com/", 1)[1]
    else:
        return None
    parts = [p for p in url.split("/") if p]
    if len(parts) < 2:
        return None
    return f"{parts[-2]}/{parts[-1]}"


def rulespec_provenance(paths: list[Path | str] | None) -> list[dict[str, Any]]:
    """Resolve ``{repo, sha}`` provenance for each rulespec checkout path.

    ``paths`` are local checkout directories (as the runner resolves them from
    ``rulespec_root`` / ``rulespec_roots``). Each is walked up to its enclosing
    git repo; the ``repo`` slug comes from the origin remote when available,
    otherwise from the directory basename so a report is never left with an
    anonymous rulespec entry. Deduplicated on ``(repo, sha)``, order-stable.
    """
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str | None, str | None]] = set()
    for raw in paths or []:
        path = Path(os.path.expandvars(os.path.expanduser(str(raw))))
        if not path.exists():
            # Record the intended repo even when the checkout is absent, keyed
            # by basename — the affected-rerun map still needs a name to diff.
            repo = canonical_rulespec_slug(path.name) if path.name else None
            sha = None
        else:
            remote_slug = repo_slug_from_remote(_remote_url(path))
            repo = remote_slug or canonical_rulespec_slug(path.name)
            sha = _git_sha(path)
        key = (repo, sha)
        if key in seen:
            continue
        seen.add(key)
        entries.append({"repo": repo, "sha": sha})
    return entries


def resolve_rulespec_checkout(slug: str) -> Path | None:
    """Locate a local checkout for a rulespec repo slug via layout conventions.

    The comparison harnesses resolve rulespec repos from a small set of
    supervised-layout locations (`~/TheAxiomFoundation/<name>`, a `~/<name>`
    symlink, the `~/.axiom-oracles/roots/<name>` synced-roots dir, and the
    `rulespec-uk-official` alias). This walks the same conventions so a
    report's provenance can record the SHA of the checkout the run actually
    resolved. Git-bearing candidates win over bare directories (an rsync'd
    root without `.git` has no SHA to record); returns None when nothing
    matches.
    """
    name = slug.split("/", 1)[-1]
    candidate_names = [name] + [
        alias for alias, target in _RULESPEC_DIR_ALIASES.items() if target == name
    ]
    home = Path.home()
    candidates = []
    # AXIOM_RULESPEC_US_ROOT pins the rulespec-us checkout a comparison runs
    # against (see scripts/run_comparison.py); the recorded SHA must come
    # from the same checkout the run actually resolved, not whatever branch
    # the developer's convention-path checkout happens to be on.
    override = os.environ.get("AXIOM_RULESPEC_US_ROOT")
    if override and name == "rulespec-us":
        candidates.append(Path(override))
    for candidate_name in candidate_names:
        candidates.extend(
            [
                home / "TheAxiomFoundation" / candidate_name,
                home / candidate_name,
                home / ".axiom-oracles" / "roots" / candidate_name,
            ]
        )
    existing = [path for path in candidates if path.exists()]
    for path in existing:
        if _git_sha(path):
            return path
    return existing[0] if existing else None


def canonical_rulespec_slug(name: str) -> str:
    """Canonicalize a rulespec repo name to its ``<OWNER>/<repo>`` slug.

    The single source of truth for rulespec slug canonicalization, shared by
    the report stamper (this module) and the affected-map generator
    (``scripts/generate_affected_map.py``) so a report's ``rulespecs[].repo``
    and the affected-map's keys are always the *same string* — otherwise the
    rerun selector would silently fail to match a suite to its repo. Accepts a
    bare dir basename (``rulespec-us``), an rsync alias (``rulespec-uk-official``
    → ``rulespec-uk``), or an already-canonical ``owner/repo`` slug (passthrough).
    Non-rulespec names pass through unchanged (they are never affected-map keys).
    """
    resolved = _RULESPEC_DIR_ALIASES.get(name, name)
    if "/" in resolved or not resolved.startswith("rulespec-"):
        return resolved
    return f"{RULESPEC_OWNER}/{resolved}"


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


def engine_provenance(axiom_rules_repo: Path | str | None) -> dict[str, Any]:
    """Axiom-side engine identity: git SHA + crate version if resolvable."""
    repo = (
        Path(os.path.expandvars(os.path.expanduser(str(axiom_rules_repo))))
        if axiom_rules_repo
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


def dataset_provenance_from_identity(identity: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalize the encode/populace ``dataset_identity`` block into provenance.

    Reuses the pinned-populace identity fields threaded from axiom-encode#952 /
    populace#80 (``source``/``repo_id``/``filename``/``revision``/``sha256``/
    ``built_with``). Returns None when identity is absent so the caller can omit
    the sub-block entirely.
    """
    if not identity:
        return None
    keep = ("source", "repo_id", "filename", "revision", "sha256", "built_with", "country")
    out = {k: identity[k] for k in keep if identity.get(k) is not None}
    return out or None
