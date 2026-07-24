"""Engine-main compile compatibility for the oracle comparison lanes (#296).

The canonical RuleSpec hard cut (axiom-rules-engine #103/#109) changed the
engine CLI contract that this repo's compile call sites were built against:

* roots are explicit, repeatable ``--rulespec-root`` flags naming
  ``rulespec-<cc>`` (two-letter country) checkouts — the
  ``AXIOM_RULESPEC_REPO_ROOTS`` environment variable is no longer read, and a
  state repo (``rulespec-us-co``) is not a valid root;
* a root's top level may hold ONLY jurisdiction directories — upstream
  rulespec-us also carries ``programs/``, ``tools/``, docs, so compiles must
  stage a filtered copy (jurisdiction dirs only);
* ``compile`` demands the program live inside a configured root; a program
  outside every root (compose output in ``/tmp``, this repo's generated
  oracle-bridge programs) must go through ``compile-composed`` and carry a
  ``module: {kind: composition}`` mapping;
* alias paths (macOS ``/var`` → ``/private/var``) are rejected — every path
  handed to the engine must be fully resolved.

Older engine builds (pre-hard-cut, still common on supervised machines)
accept none of the new flags and resolve roots from the environment instead,
so every entry point here tries the new contract first and falls back to the
legacy invocation when the binary rejects the flag.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

#: Valid engine root directory names — canonical country checkouts only.
ENGINE_ROOT_NAME = re.compile(r"^rulespec-[a-z]{2}$")

#: Jurisdiction directory names inside a root (``us``, ``us-co``, ``uk``…).
JURISDICTION_DIR_NAME = re.compile(r"^[a-z]{2}(-[a-z0-9]+)?$")


def import_prefixes(imports: list) -> set[str]:
    """Jurisdiction prefixes (``us``, ``us-az``…) named by string imports."""
    prefixes: set[str] = set()
    for entry in imports or []:
        if not isinstance(entry, str) or ":" not in entry:
            continue
        prefix = entry.split(":", 1)[0].strip().lstrip("- ")
        if prefix:
            prefixes.add(prefix)
    return prefixes


def explicit_engine_roots(
    candidates: list[Path | str],
    *,
    program: Path | None = None,
) -> list[Path]:
    """Resolve candidate paths to canonical ``rulespec-<cc>`` engine roots.

    Accepts the looser inputs this repo's configs use — a rulespec checkout
    itself, a workspace directory holding several (``$HOME``,
    ``~/TheAxiomFoundation``), or a synced-roots dir — and normalizes to the
    engine contract: each returned path is an existing directory whose name
    is ``rulespec-<cc>``. The program's own enclosing root (when it lives in
    one) leads the list. State-repo checkouts (``rulespec-us-co``) are NOT
    valid engine roots and are dropped; their content is expected inside the
    country monorepo's jurisdiction dirs.
    """
    ordered: list[Path] = []

    def _add(path: Path) -> None:
        resolved = path.resolve()
        if resolved.exists() and resolved not in ordered:
            ordered.append(resolved)

    if program is not None:
        for parent in Path(program).resolve().parents:
            if ENGINE_ROOT_NAME.match(parent.name):
                _add(parent)
                break

    for raw in candidates or []:
        path = Path(os.path.expandvars(os.path.expanduser(str(raw))))
        if not path.exists():
            continue
        if ENGINE_ROOT_NAME.match(path.name):
            _add(path)
            continue
        if path.is_dir():
            for child in sorted(path.glob("rulespec-*")):
                if ENGINE_ROOT_NAME.match(child.name) and child.is_dir():
                    _add(child)
    return ordered


def stage_pure_root(
    root: Path,
    jurisdictions: set[str],
    stage_dir: Path,
) -> Path:
    """Copy just the requested jurisdiction dirs of ``root`` into a pure root.

    The engine requires a root's top level to hold only jurisdiction
    directories; upstream rulespec-us also carries ``programs/`` and repo
    plumbing, so compiles run against a staged filtered copy. Unrequested
    jurisdictions are omitted — a program that genuinely imports beyond its
    prefixes fails loudly on the unresolved import rather than being poisoned
    by unrelated content. Staged under the *resolved* ``stage_dir`` because
    the engine rejects alias paths.
    """
    staged = Path(stage_dir).resolve() / root.name
    staged.mkdir(parents=True, exist_ok=True)
    for name in sorted(jurisdictions):
        if not JURISDICTION_DIR_NAME.match(name):
            continue
        source = root / name
        target = staged / name
        if source.is_dir() and not target.exists():
            shutil.copytree(source, target, symlinks=True)
    return staged


def _default_run(cmd: list[str], **kwargs):
    return subprocess.run(cmd, **kwargs)


def compile_with_engine(
    binary: Path | str,
    program: Path,
    output: Path,
    *,
    roots: list[Path],
    composed: bool,
    env: dict[str, str] | None = None,
    legacy_program: Path | None = None,
    timeout: float | None = None,
    run=None,
) -> None:
    """Compile ``program`` under the engine-main contract, with legacy fallback.

    New engines: ``compile-composed`` (out-of-root compositions — compose
    output, generated oracle-bridge programs) or ``compile`` (atomic modules
    inside a root), with explicit ``--rulespec-root`` flags. Old engines
    reject the new surface ("unknown compile argument" for the flag, or an
    unknown-command report for the verb) and are re-invoked the pre-hard-cut
    way: bare ``compile`` reading ``AXIOM_RULESPEC_REPO_ROOTS`` from ``env``,
    against ``legacy_program`` when the caller keeps a separate legacy-shaped
    program file. Raises ``RuntimeError`` with the engine's stderr on real
    failures. ``run`` is an injectable ``subprocess.run``-compatible callable
    (the axiom adapter threads its own through for tests).
    """
    runner = run or _default_run
    verb = "compile-composed" if composed else "compile"
    cmd = [str(binary), verb, "--program", str(Path(program).resolve())]
    for root in roots:
        cmd.extend(["--rulespec-root", str(Path(root).resolve())])
    cmd.extend(["--output", str(output)])
    kwargs: dict = {"text": True, "capture_output": True, "check": False, "env": env}
    if timeout is not None:
        kwargs["timeout"] = timeout
    result = runner(cmd, **kwargs)
    if result.returncode == 0:
        return
    marker = (result.stderr or "").strip() or (result.stdout or "").strip()
    legacy_markers = ("unknown compile argument", "invalid choice", "unknown command")
    if not any(m in marker for m in legacy_markers):
        raise RuntimeError(marker or "Axiom RuleSpec compile failed")
    legacy_cmd = [
        str(binary),
        "compile",
        "--program",
        str(Path(legacy_program or program).resolve()),
        "--output",
        str(output),
    ]
    legacy = runner(legacy_cmd, **kwargs)
    if legacy.returncode != 0:
        legacy_marker = (
            (legacy.stderr or "").strip() or (legacy.stdout or "").strip()
        )
        # Both contracts failed: the new-contract error leads (it names the
        # canonical problem); the legacy attempt's error is appended so a
        # false legacy-marker match can never mask the real failure.
        raise RuntimeError(
            (marker or "Axiom RuleSpec compile failed")
            + (
                f"\n(legacy compile fallback also failed: {legacy_marker})"
                if legacy_marker
                else ""
            )
        )


class StagedRootCache:
    """Stage-once cache: (root, jurisdictions) → staged pure root.

    Per-process staging is enough — the copy is the expensive part and the
    cache directory lives until the object is garbage collected (the CLI
    process exit for the comparison lanes).
    """

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="axiom-staged-roots-")
        self._cache: dict[tuple[str, tuple[str, ...]], Path] = {}
        self._counter = 0

    def staged(self, root: Path, jurisdictions: set[str]) -> Path:
        key = (str(Path(root).resolve()), tuple(sorted(jurisdictions)))
        if key not in self._cache:
            self._counter += 1
            stage_dir = Path(self._tmp.name) / f"stage-{self._counter}"
            stage_dir.mkdir(parents=True, exist_ok=True)
            self._cache[key] = stage_pure_root(
                Path(root), jurisdictions, stage_dir
            )
        return self._cache[key]
