"""Oracle alignment report for a candidate RuleSpec change (report only).

Given a ``rulespec-us`` checkout at a base commit, one at a candidate commit,
and the suite registry of this repository, the report answers three questions
and gates nothing:

``reach``
    For each changed file, which ``programs/**.yaml`` files have a compared
    output that transitively depends on it. Every program file is composed and
    compiled the way ``scripts/run_comparison.py`` does it; the walk is
    :func:`axiom_oracles.coverage._transitive_dependencies` over the compiled
    program, extended to the parameters and relations the reached rules read.

``expected_suites``
    The comparison suites that can observe the change, each marked
    ``runnable`` or ``manual``. A suite covers a change through the program
    file it names, or through a coverage declaration
    (``axiom_oracles/config/alignment_coverage.yaml``). A suite with neither
    could cover anything, so its existence is an error.

``status``
    Exactly one of ``no_reference``, ``reference_not_runnable``,
    ``reference_not_executed``, ``aligned``, ``regressed`` or ``error``.
    ``no_reference`` is reported only when the whole derivation completed and
    the expected suite set is empty. Any failure is ``error`` with a cause.

Nothing here reads household data. Suite execution is delegated to an
executor object, so the derivation is testable with synthetic fixtures.
"""

from __future__ import annotations

import bisect
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any, Protocol

import yaml

from axiom_oracles.coverage import _transitive_dependencies

SCHEMA = "axiom_oracles.alignment_report.v1"
COVERAGE_SCHEMA = "axiom_oracles.alignment_coverage.v1"
SUPPLIED_SCHEMA = "axiom_oracles.alignment_supplied_reports.v1"
CACHE_SCHEMA = "axiom_oracles.alignment_cache_entry.v1"
TOOL_NAME = "axiom_oracles.alignment"
#: Bumped when the derivation rules change, independent of the package version.
DERIVATION_VERSION = "2"

STATUS_NO_REFERENCE = "no_reference"
STATUS_NOT_RUNNABLE = "reference_not_runnable"
STATUS_NOT_EXECUTED = "reference_not_executed"
STATUS_ALIGNED = "aligned"
STATUS_REGRESSED = "regressed"
STATUS_ERROR = "error"

REASON_NO_PROGRAM = "no_program_reaches"
REASON_NO_SUITE = "no_suite_for_reaching_programs"

MODE_RUNNABLE = "runnable"
MODE_MANUAL = "manual"

ORIGIN_RULESPEC = "rulespec-us"
ORIGIN_REGISTRY = "axiom-oracles"
RULESPEC_REPO = "TheAxiomFoundation/rulespec-us"

SIDES = ("base", "candidate")

BINDING_PROGRAM = "program"
BINDING_PINNED = "pinned_snapshot"
BINDING_NO_AXIOM = "no_axiom_side"
BINDING_PARAMETER_FILES = "parameter_files"
BINDING_DECLARED = "declared"
BINDING_NONE = "declared_reads_no_rulespec_us"

COVERAGE_FILE = "axiom_oracles/config/alignment_coverage.yaml"
PARAMETER_MANIFEST_SCHEMA = "axiom_oracles.parameter_suite_list.v1"
CAMPAIGN_MANIFEST_SCHEMA = "axiom.campaign_projection_suite_list.v1"

JURISDICTION_DIR = re.compile(r"^[a-z]{2}(-[a-z0-9]+)?$")
#: ``us:statutes/7/2014/e/2`` — a RuleSpec module id written as a literal. A
#: path segment may hold a colon (``us-la:statutes/47:294``).
MODULE_LITERAL = re.compile(
    r"(?<![A-Za-z0-9_/.:-])([a-z]{2}(?:-[a-z0-9]+)?):"
    r"([A-Za-z0-9_][A-Za-z0-9_.\-:]*/[A-Za-z0-9_.\-/:]*[A-Za-z0-9_])"
)
#: ``us-co/policies/cdhs/snap/x.yaml`` — a module named by its file path.
MODULE_PATH_LITERAL = re.compile(
    r"(?<![A-Za-z0-9_.-])([a-z]{2}(?:-[a-z0-9]+)?)/"
    r"((?:statutes|regulations|policies)/[A-Za-z0-9_.\-/:]*?[A-Za-z0-9_])(\.test)?\.yaml"
)
#: Adjacent string literals split over two source lines.
_SPLIT_LITERAL = re.compile(r"""["']\s*\n\s*["']""")
UNATTRIBUTED = "<unattributed>"


class AlignmentError(Exception):
    """A failure of the derivation. Reported as ``status: error``."""

    def __init__(self, cause: str, detail: str) -> None:
        super().__init__(f"{cause}: {detail}")
        self.cause = cause
        self.detail = detail


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str | None:
    try:
        return sha256_bytes(Path(path).read_bytes())
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return None


def canonical_json_sha256(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256_bytes(text.encode("utf-8"))


def tool_version() -> str:
    try:
        package = metadata.version("axiom-oracles")
    except metadata.PackageNotFoundError:
        package = "unknown"
    return f"{package}+derivation.{DERIVATION_VERSION}"


def _tail(text: str, limit: int = 600) -> str:
    text = " ".join((text or "").split())
    return text[-limit:] if len(text) > limit else text


def _git(root: Path, *args: str, timeout: float = 300.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def git_head(root: Path) -> str | None:
    """The commit a checkout is at, or ``None`` when ``root`` is not the top
    level of one."""
    try:
        result = _git(root, "rev-parse", "--verify", "HEAD^{commit}", timeout=60)
        if result.returncode != 0:
            return None
        top = _git(root, "rev-parse", "--show-toplevel", timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    # A plain directory inside another repository is not a checkout of its own.
    if top.returncode != 0:
        return None
    if Path(top.stdout.decode().strip()).resolve() != Path(root).resolve():
        return None
    return result.stdout.decode().strip() or None


def git_dirty(root: Path) -> bool | None:
    """Whether a checkout has any change, staged or not, or an untracked file."""
    try:
        result = _git(root, "status", "--porcelain", "--untracked-files=all")
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return bool(result.stdout.strip())


def glob_regex(pattern: str) -> re.Pattern[str]:
    """``*`` stays inside one path segment; ``**`` crosses segments."""
    out = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**", index):
            out.append(".*")
            index += 2
        elif pattern[index] == "*":
            out.append("[^/]*")
            index += 1
        elif pattern[index] == "?":
            out.append("[^/]")
            index += 1
        else:
            out.append(re.escape(pattern[index]))
            index += 1
    return re.compile("".join(out) + r"\Z")


# ---------------------------------------------------------------------------
# Checkouts and changed files
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Checkout:
    """A clean, complete git checkout: its commit and every tracked file."""

    root: Path
    commit: str
    blobs: Mapping[str, str]


def read_checkout(root: Path, side: str) -> Checkout:
    """Read ``root`` as a checkout and refuse one the report cannot trust.

    The work tree must be the top level of a git checkout, hold no staged,
    unstaged or untracked change, and hold every file its commit tracks (a
    sparse or partly deleted checkout is refused). The file list and the blob
    ids then come from the commit, so the tree on disk is the tree of the
    commit.
    """
    root = Path(root)
    commit = git_head(root)
    if commit is None:
        raise AlignmentError("rulespec_tree_not_a_checkout", f"{side}: not a git checkout")
    dirty = git_dirty(root)
    if dirty is None:
        raise AlignmentError("rulespec_tree_unreadable", f"{side}: git status failed")
    if dirty:
        raise AlignmentError(
            "rulespec_tree_dirty", f"{side}: the checkout has uncommitted or untracked files"
        )
    try:
        listing = _git(root, "ls-tree", "-r", "-z", "HEAD")
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AlignmentError("rulespec_tree_unreadable", f"{side}: {exc}") from exc
    if listing.returncode != 0:
        raise AlignmentError("rulespec_tree_unreadable", f"{side}: git ls-tree failed")
    blobs: dict[str, str] = {}
    for entry in listing.stdout.split(b"\0"):
        if not entry:
            continue
        meta, _, raw_path = entry.partition(b"\t")
        fields = meta.split()
        if len(fields) != 3:
            raise AlignmentError("rulespec_tree_unreadable", f"{side}: unexpected ls-tree row")
        try:
            path = raw_path.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AlignmentError("rulespec_tree_unreadable", f"{side}: {exc}") from exc
        blobs[path] = f"{fields[1].decode()}:{fields[2].decode()}"
    missing = [path for path in blobs if not os.path.lexists(root / path)]
    if missing:
        raise AlignmentError(
            "rulespec_tree_incomplete",
            f"{side}: {len(missing)} tracked files are absent from the work tree "
            f"(first: {sorted(missing)[0]})",
        )
    return Checkout(root=root, commit=commit, blobs=blobs)


def _is_jurisdiction_path(relpath: str) -> bool:
    head = relpath.split("/", 1)[0]
    return "/" in relpath and bool(JURISDICTION_DIR.match(head))


def classify_path(relpath: str) -> tuple[str, str | None]:
    """``(kind, module_id)`` for a path relative to the rulespec root.

    ``program``: a ``programs/**.yaml`` file. ``module``: a RuleSpec module
    under a jurisdiction directory. ``test``: a module's companion
    ``.test.yaml`` file (``module_id`` is that module). ``other``: anything
    else. A file that looks like a rule file but is not where the engine reads
    one (a ``.yml`` module, a jurisdiction directory spelled in another case)
    raises: the report cannot say what reads it.
    """
    if relpath.startswith("programs/") and relpath.endswith((".yaml", ".yml")):
        return "program", None
    head = relpath.split("/", 1)[0]
    if _is_jurisdiction_path(relpath):
        jurisdiction, rest = relpath.split("/", 1)
        if rest.startswith(".axiom/") or "/.axiom/" in rest:
            return "other", None
        if rest.endswith(".test.yaml"):
            return "test", f"{jurisdiction}:{rest[: -len('.test.yaml')]}"
        if rest.endswith(".yaml"):
            return "module", f"{jurisdiction}:{rest[: -len('.yaml')]}"
        if rest.lower().endswith((".yml", ".yaml")):
            raise AlignmentError(
                "changed_file_unclassified", f"{relpath}: a rule-like file with an unread suffix"
            )
        return "other", None
    if "/" in relpath and head != head.lower() and JURISDICTION_DIR.match(head.lower()):
        raise AlignmentError(
            "changed_file_unclassified",
            f"{relpath}: a directory named like a jurisdiction in another letter case",
        )
    if relpath.lower().startswith("programs/") and not relpath.startswith("programs/"):
        raise AlignmentError(
            "changed_file_unclassified", f"{relpath}: programs/ in another letter case"
        )
    return "other", None


def changed_files(
    base: Checkout, candidate: Checkout, explicit: Sequence[str] | None = None
) -> list[dict[str, Any]]:
    """Every file that differs between the two commits, with both digests.

    The set is always derived from the two trees. ``explicit`` (the caller's
    own list) must name exactly that set, spelled exactly as git spells it;
    any difference is an error, so a list cannot hide or misname a change.
    """
    paths = sorted(
        path
        for path in set(base.blobs) | set(candidate.blobs)
        if base.blobs.get(path) != candidate.blobs.get(path)
    )
    if explicit is not None:
        given = [str(item) for item in explicit]
        missing = sorted(set(paths) - set(given))
        extra = sorted(set(given) - set(paths))
        if missing or extra or len(given) != len(set(given)):
            raise AlignmentError(
                "changed_files_mismatch",
                f"the given list differs from the tree diff: {len(missing)} changed files "
                f"not listed (first: {missing[:1]}), {len(extra)} listed files that did "
                f"not change (first: {extra[:1]})",
            )
    out = []
    for relpath in paths:
        kind, module = classify_path(relpath)
        out.append(
            {
                "path": relpath,
                "kind": kind,
                "module": module,
                "base_sha256": sha256_file(base.root / relpath) if relpath in base.blobs else None,
                "candidate_sha256": (
                    sha256_file(candidate.root / relpath) if relpath in candidate.blobs else None
                ),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Programs and compilation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProgramFile:
    origin: str
    relpath: str
    path: Path

    @property
    def key(self) -> str:
        return f"{self.origin}:{self.relpath}"


def checkout_programs(checkout: Checkout) -> list[ProgramFile]:
    """The program files the commit tracks under ``programs/``."""
    return [
        ProgramFile(ORIGIN_RULESPEC, path, checkout.root / path)
        for path in sorted(checkout.blobs)
        if path.startswith("programs/") and path.endswith((".yaml", ".yml"))
    ]


def discover_programs(root: Path, origin: str) -> list[ProgramFile]:
    """The program files on disk under ``root/programs`` (the registry's own)."""
    programs_dir = Path(root) / "programs"
    if not programs_dir.is_dir():
        return []
    found = []
    for path in sorted(programs_dir.rglob("*")):
        if path.is_file() and path.suffix in (".yaml", ".yml"):
            found.append(ProgramFile(origin, path.relative_to(root).as_posix(), path))
    return found


class Compiler(Protocol):
    def compile(self, program: ProgramFile, side: str) -> Mapping[str, Any]:
        """Return the compiled artifact (the engine's JSON) for one program.

        A compiler that also sets ``composed_imports`` (the module ids the
        composed program imports) lets an identical-input compile be reused.
        """


class ComposeEngineCompiler:
    """Compose with ``axiom-compose`` and compile with ``axiom-rules-engine``.

    The same two steps as ``scripts/run_comparison.py``'s
    ``_ensure_composed_axiom_program``: compose against the side's canonical
    ``rulespec-us`` checkout, then ``compile-composed`` against a staged pure
    root (jurisdiction directories only).
    """

    def __init__(
        self,
        *,
        roots: Mapping[str, Path],
        compose_binary: Path,
        engine_binary: Path,
        work_dir: Path,
        timeout: float = 600.0,
        cwd: Path | None = None,
    ) -> None:
        self.roots = {side: Path(root) for side, root in roots.items()}
        self.compose_binary = Path(compose_binary)
        self.engine_binary = Path(engine_binary)
        self.work_dir = Path(work_dir).resolve()
        self.timeout = timeout
        self.cwd = cwd
        self._staged: dict[str, Path] = {}
        self._stage_dirs: list[Path] = []

    def close(self) -> None:
        for stage_dir in self._stage_dirs:
            shutil.rmtree(stage_dir, ignore_errors=True)
        self._stage_dirs.clear()
        self._staged.clear()

    def prepare(self) -> None:
        from axiom_oracles.engine_compat import stage_pure_root

        for binary in (self.compose_binary, self.engine_binary):
            if not binary.is_file():
                raise AlignmentError("toolchain_missing", f"no such binary: {binary.name}")
        for side, root in self.roots.items():
            try:
                jurisdictions = {
                    child.name
                    for child in root.iterdir()
                    if child.is_dir() and JURISDICTION_DIR.match(child.name)
                }
                # Staged under the system temp directory: the engine refuses
                # a root that sits inside another repository's work tree.
                stage_dir = Path(tempfile.mkdtemp(prefix=f"alignment-roots-{side}."))
                self._stage_dirs.append(stage_dir)
                self._staged[side] = stage_pure_root(root, jurisdictions, stage_dir)
            except (OSError, ValueError) as exc:
                raise AlignmentError("rulespec_root_not_canonical", f"{side}: {exc}") from exc

    def compile(self, program: ProgramFile, side: str) -> Mapping[str, Any]:
        from axiom_oracles.engine_compat import compile_with_engine

        if side not in self._staged:
            raise AlignmentError("toolchain_missing", "prepare() was not called")
        slug = re.sub(r"[^A-Za-z0-9]+", "-", program.key).strip("-")
        out_dir = self.work_dir / "compiled" / side
        out_dir.mkdir(parents=True, exist_ok=True)
        composed = out_dir / f"{slug}.composed.yaml"
        compiled = out_dir / f"{slug}.compiled.json"
        cmd = [
            str(self.compose_binary),
            str(program.path),
            "--rulespec-root",
            str(self.roots[side]),
            "-o",
            str(composed),
        ]
        try:
            result = subprocess.run(
                cmd,
                text=True,
                capture_output=True,
                check=False,
                timeout=self.timeout,
                cwd=self.cwd,
            )
        except subprocess.TimeoutExpired as exc:
            raise AlignmentError("timeout", f"compose of {program.key} ({side})") from exc
        if result.returncode != 0:
            raise AlignmentError(
                "program_compile_failed",
                f"compose of {program.key} ({side}): {_tail(result.stderr or result.stdout)}",
            )
        try:
            composed_doc = yaml.safe_load(composed.read_text()) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise AlignmentError(
                "program_compile_failed", f"composed {program.key} ({side}) unreadable: {exc}"
            ) from exc
        is_composition = (composed_doc.get("module") or {}).get("kind") == "composition"
        try:
            compile_with_engine(
                self.engine_binary,
                composed,
                compiled,
                roots=[self._staged[side]],
                composed=is_composition,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise AlignmentError("timeout", f"compile of {program.key} ({side})") from exc
        except (RuntimeError, ValueError, OSError) as exc:
            raise AlignmentError(
                "program_compile_failed", f"compile of {program.key} ({side}): {_tail(str(exc))}"
            ) from exc
        try:
            artifact = json.loads(compiled.read_text())
        except (OSError, ValueError) as exc:
            raise AlignmentError(
                "program_compile_failed", f"artifact of {program.key} ({side}) unreadable: {exc}"
            ) from exc
        if isinstance(artifact, dict):
            artifact["composed_imports"] = [
                entry for entry in composed_doc.get("imports") or [] if isinstance(entry, str)
            ]
        return artifact


def program_outputs(program: ProgramFile) -> list[str]:
    """The ``outputs`` a program file declares (its compared outputs)."""
    try:
        doc = yaml.safe_load(program.path.read_text())
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise AlignmentError("program_unreadable", f"{program.key}: {exc}") from exc
    if not isinstance(doc, Mapping):
        raise AlignmentError("program_unreadable", f"{program.key}: not a mapping")
    outputs = doc.get("outputs")
    if not isinstance(outputs, list) or not outputs or not all(
        isinstance(item, str) and item for item in outputs
    ):
        raise AlignmentError("program_without_outputs", f"{program.key} declares no outputs")
    return list(outputs)


def _module_of(identifier: str) -> str | None:
    if not isinstance(identifier, str) or "#" not in identifier:
        return None
    return identifier.split("#", 1)[0]


def _walk_refs(node: Any, parameters: set[str], relations: set[str]) -> None:
    if isinstance(node, Mapping):
        parameter = node.get("parameter")
        if isinstance(parameter, str):
            parameters.add(parameter)
        relation = node.get("relation")
        if isinstance(relation, str):
            relations.add(relation)
        for value in node.values():
            _walk_refs(value, parameters, relations)
    elif isinstance(node, list):
        for item in node:
            _walk_refs(item, parameters, relations)


@dataclass
class CompiledProgram:
    program: ProgramFile
    side: str
    sha256: str
    engine_version: str | None
    derived_by_name: dict[str, Mapping[str, Any]]
    parameter_ids: dict[str, list[str]]
    #: Modules the artifact compiled from plus the composed imports, or
    #: ``None`` when the compiler did not report the imports.
    seed_modules: frozenset[str] | None = None
    reused: bool = False

    def resolve_root(self, root: str) -> str | None:
        """The derived-rule name for an output or a ``module#name`` concept."""
        if root in self.derived_by_name:
            return root
        short = root.rsplit("#", 1)[-1]
        if short in self.derived_by_name:
            return short
        return None

    def reached_modules(self, roots: Iterable[str]) -> dict[str, set[str]]:
        """``module id -> names`` of rules, parameters and relations reached.

        Every version of a dated rule is walked, not only its current
        expression.
        """
        reached: dict[str, set[str]] = {}
        names: set[str] = set()
        for root in roots:
            names |= _transitive_dependencies(root, self.derived_by_name)
        for name in names:
            rule = self.derived_by_name[name]
            module = _module_of(str(rule.get("id") or ""))
            # A rule without a module id is written in the program file
            # itself; a change to that file reaches the program directly.
            if module is not None:
                reached.setdefault(module, set()).add(name)
            parameters: set[str] = set()
            relations: set[str] = set()
            _walk_refs({k: v for k, v in rule.items() if k not in ("id", "name")}, parameters, relations)
            for parameter in parameters:
                for identifier in self.parameter_ids.get(parameter, []):
                    owner = _module_of(identifier)
                    if owner:
                        reached.setdefault(owner, set()).add(parameter)
            for relation in relations:
                owner = _module_of(relation)
                if owner:
                    reached.setdefault(owner, set()).add(relation.split("#", 1)[1])
        return reached


def index_compiled(program: ProgramFile, side: str, artifact: Mapping[str, Any]) -> CompiledProgram:
    if not isinstance(artifact, Mapping):
        raise AlignmentError("program_compile_failed", f"{program.key} ({side}): no artifact")
    body = artifact.get("program", artifact)
    derived = body.get("derived") if isinstance(body, Mapping) else None
    if not isinstance(derived, list) or not derived:
        raise AlignmentError(
            "program_compile_failed", f"{program.key} ({side}): artifact has no derived rules"
        )
    derived_by_name: dict[str, Mapping[str, Any]] = {}
    for rule in derived:
        name = rule.get("name") if isinstance(rule, Mapping) else None
        if not isinstance(name, str) or not name:
            raise AlignmentError(
                "program_compile_failed", f"{program.key} ({side}): unnamed derived rule"
            )
        if name in derived_by_name:
            raise AlignmentError(
                "compiled_program_ambiguous",
                f"{program.key} ({side}): two derived rules named {name!r}",
            )
        derived_by_name[name] = rule
    parameter_ids: dict[str, list[str]] = {}
    for parameter in body.get("parameters") or []:
        if isinstance(parameter, Mapping) and isinstance(parameter.get("name"), str):
            parameter_ids.setdefault(parameter["name"], []).append(str(parameter.get("id") or ""))
    identifiers = [str(rule.get("id") or "") for rule in derived]
    identifiers += [i for ids in parameter_ids.values() for i in ids]
    identifiers += [
        str(relation.get("name") or "")
        for relation in body.get("relations") or []
        if isinstance(relation, Mapping)
    ]
    imports = artifact.get("composed_imports")
    seeds: frozenset[str] | None = None
    if isinstance(imports, list):
        seeds = frozenset(
            {m for m in (_module_of(i) for i in identifiers) if m}
            | {str(i).split("#", 1)[0] for i in imports if isinstance(i, str) and ":" in i}
        )
    return CompiledProgram(
        seed_modules=seeds,
        program=program,
        side=side,
        sha256=canonical_json_sha256(body),
        engine_version=(
            str(artifact.get("engine_version")) if artifact.get("engine_version") else None
        ),
        derived_by_name=derived_by_name,
        parameter_ids=parameter_ids,
    )


def module_literals(text: str, *, paths: bool = False) -> set[str]:
    """Module ids written as ``us:path`` literals; with ``paths`` also modules
    named by file path (``us/path.yaml``), as harness sources write them."""
    found = {f"{m.group(1)}:{m.group(2)}" for m in MODULE_LITERAL.finditer(text)}
    if paths:
        joined = _SPLIT_LITERAL.sub("", text)
        for source in (text, joined):
            found |= {f"{m.group(1)}:{m.group(2)}" for m in MODULE_LITERAL.finditer(source)}
            found |= {f"{m.group(1)}:{m.group(2)}" for m in MODULE_PATH_LITERAL.finditer(source)}
    return found


class TreeIndex:
    """Files, modules and module references of one rulespec checkout."""

    def __init__(self, checkout: Checkout) -> None:
        self.root = checkout.root
        self.digests = dict(checkout.blobs)
        self.paths = sorted(self.digests)
        self.modules: dict[str, str] = {}
        self.references: dict[str, set[str]] = {}
        for relpath in self.paths:
            try:
                kind, module = classify_path(relpath)
            except AlignmentError:
                continue
            if kind != "module" or module is None:
                continue
            self.modules[relpath] = module
            try:
                text = (self.root / relpath).read_text()
            except (OSError, UnicodeDecodeError) as exc:
                raise AlignmentError(
                    "rulespec_tree_unreadable", f"{relpath}: {type(exc).__name__}"
                ) from exc
            self.references[module] = module_literals(text) - {module}
        self._reverse: dict[str, set[str]] | None = None

    def closure(self, modules: Iterable[str]) -> set[str]:
        """``modules`` plus every module they name, transitively."""
        seen: set[str] = set()
        stack = list(modules)
        while stack:
            module = stack.pop()
            if module in seen:
                continue
            seen.add(module)
            stack.extend(self.references.get(module, ()))
        return seen

    def referencing(self, modules: Iterable[str]) -> set[str]:
        """``modules`` plus every module that names one of them, transitively."""
        if self._reverse is None:
            reverse: dict[str, set[str]] = {}
            for module, targets in self.references.items():
                for target in targets:
                    reverse.setdefault(target, set()).add(module)
            self._reverse = reverse
        seen: set[str] = set()
        stack = list(modules)
        while stack:
            module = stack.pop()
            if module in seen:
                continue
            seen.add(module)
            stack.extend(self._reverse.get(module, ()))
        return seen

    def _under(self, prefix: str) -> list[str]:
        start = bisect.bisect_left(self.paths, prefix)
        out = []
        for path in self.paths[start:]:
            if not path.startswith(prefix):
                break
            if not path.endswith(".test.yaml"):
                out.append(path)
        return out

    def program_inputs(self, program: ProgramFile, seeds: Iterable[str]) -> dict[str, Any]:
        """Digests of everything a compile of ``program`` can read here.

        The program file, the file of every module in the closure of
        ``seeds``, and the listing of the directory of the same name (an
        import may name a directory of modules).
        """
        files: dict[str, str | None] = {}
        dirs: dict[str, str] = {}
        for module in sorted(self.closure(seeds)):
            jurisdiction, rest = module.split(":", 1)
            stem = f"{jurisdiction}/{rest}"
            files[f"{stem}.yaml"] = self.digests.get(f"{stem}.yaml")
            listing = [(path, self.digests[path]) for path in self._under(f"{stem}/")]
            dirs[f"{stem}/"] = canonical_json_sha256(listing)
        return {
            "program": program.key,
            "program_sha256": sha256_file(program.path),
            "files": files,
            "dirs": dirs,
        }

    def matches(self, program: ProgramFile, recorded: Mapping[str, Any]) -> bool:
        if recorded.get("program") != program.key:
            return False
        if recorded.get("program_sha256") != sha256_file(program.path):
            return False
        files = recorded.get("files")
        dirs = recorded.get("dirs")
        if not isinstance(files, Mapping) or not isinstance(dirs, Mapping):
            return False
        for path, digest in files.items():
            if self.digests.get(path) != digest:
                return False
        for prefix, digest in dirs.items():
            listing = [(path, self.digests[path]) for path in self._under(prefix)]
            if canonical_json_sha256(listing) != digest:
                return False
        return True


class CompileCache:
    """Compiled artifacts keyed by the bytes of everything the compile read.

    Always in memory for one report, so a candidate program whose inputs equal
    base is not compiled twice. With ``directory`` the entries persist across
    reports. ``salt`` names the toolchain; entries of another toolchain are
    never read.

    An entry on disk is used only when it is whole: its recorded inputs are
    exactly the inputs this report computes for the artifact it holds, and
    the artifact's digest is the recorded one. Anything else is ignored and
    the program is compiled. That catches damage and stale entries. It does
    not make a directory that another party can write trustworthy: someone
    who can write a consistent entry can supply any artifact, so the
    directory must be private to the runs that use it.
    """

    def __init__(self, directory: Path | None = None, salt: str = "") -> None:
        self.directory = Path(directory) if directory is not None else None
        self.salt = salt
        self._memory: dict[str, list[tuple[Mapping[str, Any], Mapping[str, Any]]]] = {}

    def _slot(self, program: ProgramFile) -> str:
        return sha256_bytes(f"{self.salt}\0{program.key}".encode())

    @staticmethod
    def _whole(entry: Any, program: ProgramFile, side: str, tree: TreeIndex) -> bool:
        if not isinstance(entry, Mapping) or entry.get("schema") != CACHE_SCHEMA:
            return False
        inputs, artifact = entry.get("inputs"), entry.get("artifact")
        if not isinstance(inputs, Mapping) or not isinstance(artifact, Mapping):
            return False
        if entry.get("artifact_sha256") != canonical_json_sha256(artifact):
            return False
        try:
            unit = index_compiled(program, side, artifact)
        except AlignmentError:
            return False
        if unit.seed_modules is None:
            return False
        # The recorded inputs must be the ones this artifact's own modules
        # and imports give in this tree: a record that lists fewer files than
        # the artifact read is refused.
        return tree.program_inputs(program, unit.seed_modules) == dict(inputs)

    def get(self, program: ProgramFile, side: str, tree: TreeIndex) -> Mapping[str, Any] | None:
        slot = self._slot(program)
        for recorded, artifact in self._memory.get(slot, []):
            if tree.matches(program, recorded):
                return artifact
        if self.directory is None:
            return None
        for path in sorted((self.directory / slot).glob("*.json")):
            try:
                entry = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            if self._whole(entry, program, side, tree):
                self._memory.setdefault(slot, []).append((entry["inputs"], entry["artifact"]))
                return entry["artifact"]
        return None

    def put(
        self, program: ProgramFile, tree: TreeIndex, unit: CompiledProgram, artifact: Mapping[str, Any]
    ) -> None:
        if unit.seed_modules is None:
            return
        recorded = tree.program_inputs(program, unit.seed_modules)
        slot = self._slot(program)
        self._memory.setdefault(slot, []).append((recorded, artifact))
        if self.directory is None:
            return
        target = self.directory / slot
        target.mkdir(parents=True, exist_ok=True)
        name = canonical_json_sha256(recorded)[:24]
        temporary = target / f".{name}.{os.getpid()}.tmp"
        temporary.write_text(
            json.dumps(
                {
                    "schema": CACHE_SCHEMA,
                    "inputs": recorded,
                    "artifact_sha256": canonical_json_sha256(artifact),
                    "artifact": artifact,
                }
            )
        )
        temporary.replace(target / f"{name}.json")


def compile_programs(
    programs: Mapping[str, Sequence[ProgramFile]],
    compiler: Compiler,
    *,
    jobs: int = 4,
    trees: Mapping[str, TreeIndex] | None = None,
    cache: CompileCache | None = None,
) -> tuple[dict[str, dict[str, CompiledProgram]], dict[str, dict[str, int]]]:
    """Compile every program on every side. Any failure raises.

    Returns ``(compiled[side][key], counts[side])``. A side whose compiled
    count differs from the number of program files found is an error.

    With ``trees`` and ``cache`` a program is not compiled again when the
    cache holds an artifact whose recorded inputs are byte-identical in this
    side's tree. Base is compiled first, so an unchanged candidate program
    takes the base artifact.
    """

    def one(task: tuple[str, ProgramFile]) -> CompiledProgram | AlignmentError:
        side, program = task
        try:
            tree = trees.get(side) if trees is not None else None
            if cache is not None and tree is not None:
                cached = cache.get(program, side, tree)
                if cached is not None:
                    unit = index_compiled(program, side, cached)
                    unit.reused = True
                    return unit
            artifact = compiler.compile(program, side)
            unit = index_compiled(program, side, artifact)
            if cache is not None and tree is not None:
                cache.put(program, tree, unit, artifact)
            return unit
        except AlignmentError as exc:
            return exc

    compiled: dict[str, dict[str, CompiledProgram]] = {side: {} for side in SIDES}
    failures: list[AlignmentError] = []
    attempted = 0
    for side in SIDES:
        tasks = [(side, program) for program in programs.get(side, [])]
        attempted += len(tasks)
        if not tasks:
            continue
        with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
            for item in pool.map(one, tasks):
                if isinstance(item, AlignmentError):
                    failures.append(item)
                else:
                    compiled[item.side][item.program.key] = item
    if failures:
        causes = {failure.cause for failure in failures}
        raise AlignmentError(
            causes.pop() if len(causes) == 1 else "program_compile_failed",
            f"{len(failures)} of {attempted} program compiles failed: "
            + " | ".join(failure.detail for failure in failures),
        )
    return _count_check(programs, compiled)


def _count_check(
    programs: Mapping[str, Sequence[ProgramFile]],
    compiled: dict[str, dict[str, CompiledProgram]],
) -> tuple[dict[str, dict[str, CompiledProgram]], dict[str, dict[str, int]]]:
    """Program files found against programs compiled, per side."""
    counts = {}
    for side in SIDES:
        found = len(programs.get(side, []))
        done = len(compiled[side])
        counts[side] = {
            "program_files_found": found,
            "programs_compiled": done,
            "reused": sum(unit.reused for unit in compiled[side].values()),
        }
        if found != done:
            raise AlignmentError(
                "program_count_mismatch",
                f"{side}: {found} program files found, {done} compiled",
            )
    return compiled, counts


# ---------------------------------------------------------------------------
# Suite registry and coverage declarations
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Suite:
    name: str
    file: str
    ci: str | None
    mode: str
    #: ``None`` for a suite listed in a manifest instead of its own file.
    runner_type: str | None
    program_key: str | None
    concepts: tuple[str, ...]
    variables: Mapping[str, str]
    pinned: bool = False
    no_axiom_side: bool = False
    parameter_files: tuple[str, ...] = ()


@dataclass(frozen=True)
class BoundSuite:
    suite: Suite
    binding: str
    declaration: str | None = None
    roots: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()


def _program_key_from_ref(ref: Any) -> str | None:
    """Map an ``axiom_program`` value to a program key.

    ``.../rulespec-us/programs/x.yaml`` names a program of the rulespec tree;
    ``.../axiom-oracles/programs/x.yaml`` or a relative ``programs/x.yaml``
    names one of this repository. Anything else gives ``None``: the suite
    then needs a coverage declaration.
    """
    text = str(ref).replace("\\", "/")
    if "/programs/" in f"/{text}":
        head, rel = f"/{text}".rsplit("/programs/", 1)
        relpath = f"programs/{rel}"
        owner = head.rstrip("/").rsplit("/", 1)[-1]
        if owner == "rulespec-us":
            return f"{ORIGIN_RULESPEC}:{relpath}"
        if owner in ("axiom-oracles", ""):
            return f"{ORIGIN_REGISTRY}:{relpath}"
    return None


def _registry_error(detail: str) -> AlignmentError:
    return AlignmentError("registry_unreadable", detail)


def _suite_variables(params: Mapping[str, Any]) -> dict[str, str]:
    variables: dict[str, str] = {}
    jurisdiction = params.get("jurisdiction")
    if isinstance(jurisdiction, str) and jurisdiction:
        if JURISDICTION_DIR.match(jurisdiction):
            variables["jurisdiction"] = jurisdiction
            if "-" in jurisdiction:
                variables["state"] = jurisdiction.split("-", 1)[1]
        elif re.fullmatch(r"[A-Za-z]{2}", jurisdiction):
            variables["state"] = jurisdiction.lower()
            variables["jurisdiction"] = f"us-{jurisdiction.lower()}"
    state = params.get("state")
    if isinstance(state, str) and re.fullmatch(r"[A-Za-z]{2}", state):
        variables["state"] = state.lower()
        variables.setdefault("jurisdiction", f"us-{state.lower()}")
    return variables


def _runner_suite(path: Path, doc: Mapping[str, Any]) -> Suite:
    runner = doc.get("runner")
    name = doc.get("name")
    if not isinstance(runner, Mapping) or not isinstance(runner.get("type"), str):
        raise _registry_error(f"{path.name}: runner without a type")
    if not isinstance(name, str) or not name:
        raise _registry_error(f"{path.name}: suite without a name")
    ci = doc.get("ci")
    if ci is not None and not isinstance(ci, str):
        raise _registry_error(f"{path.name}: ci is not a string")
    params = runner.get("parameters") or {}
    if not isinstance(params, Mapping):
        raise _registry_error(f"{path.name}: parameters not a mapping")
    concepts = params.get("concepts") or []
    if not isinstance(concepts, list) or not all(isinstance(c, str) for c in concepts):
        raise _registry_error(f"{path.name}: concepts not a string list")
    pinned = bool(params.get("rulespec_upstream_sha") and params.get("rulespec_upstream_tree")) or bool(
        params.get("axiom_rulespec_repo_roots_revision")
        or runner.get("axiom_rulespec_repo_roots_revision")
    )
    sides = (params.get("left"), params.get("right"))
    return Suite(
        name=name,
        file=f"comparisons/{path.name}",
        ci=ci,
        # ``manual`` for ``ci: manual``; every other suite runs in a CI lane.
        mode=MODE_MANUAL if ci == "manual" else MODE_RUNNABLE,
        runner_type=runner["type"],
        program_key=(
            _program_key_from_ref(params["axiom_program"]) if params.get("axiom_program") else None
        ),
        concepts=tuple(concepts),
        variables=_suite_variables(params),
        pinned=pinned,
        no_axiom_side=(
            runner["type"] == "axiom-oracles-compare"
            and all(isinstance(side, str) for side in sides)
            and "axiom" not in sides
        ),
    )


def _manifest_suites(path: Path, doc: Mapping[str, Any]) -> list[Suite]:
    """Suites listed in a manifest (no runner of their own).

    They are not dispatched through ``run_comparison.py``, so they are always
    ``manual`` here.
    """
    rows = doc.get("suites")
    schema = doc.get("schema") or doc.get("schema_version")
    if schema not in (PARAMETER_MANIFEST_SCHEMA, CAMPAIGN_MANIFEST_SCHEMA):
        raise _registry_error(f"{path.name}: neither a suite nor a known suite manifest")
    if not isinstance(rows, list) or not rows:
        raise _registry_error(f"{path.name}: manifest without suites")
    out = []
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("suite"), str) or not row["suite"]:
            raise _registry_error(f"{path.name}: manifest row without a suite name")
        files: tuple[str, ...] = ()
        if schema == PARAMETER_MANIFEST_SCHEMA:
            comparisons = row.get("comparisons")
            if not isinstance(comparisons, list) or not comparisons:
                raise _registry_error(f"{path.name}: {row['suite']} has no comparisons")
            names = []
            for comparison in comparisons:
                target = comparison.get("file") if isinstance(comparison, Mapping) else None
                if not isinstance(target, str) or not target:
                    raise _registry_error(f"{path.name}: {row['suite']} comparison without a file")
                names.append(target)
            files = tuple(sorted(set(names)))
        out.append(
            Suite(
                name=row["suite"],
                file=f"comparisons/{path.name}",
                ci="manual",
                mode=MODE_MANUAL,
                runner_type=None,
                program_key=(
                    _program_key_from_ref(row["axiom_program"]) if row.get("axiom_program") else None
                ),
                concepts=(),
                variables=_suite_variables(row),
                parameter_files=files,
            )
        )
    return out


def load_suites(registry_root: Path) -> list[Suite]:
    """Every suite of ``comparisons/``: suite files and manifest rows.

    An unreadable registry, a file that does not parse, a file that is
    neither a suite, a known manifest nor a fixtures file, a suite file in a
    subdirectory, a suite without a name or runner type, a duplicate name, or
    an empty registry all raise ``registry_unreadable``.
    """
    directory = Path(registry_root) / "comparisons"
    if not directory.is_dir():
        raise _registry_error("no comparisons/ directory")
    suites: dict[str, Suite] = {}
    try:
        entries = sorted(directory.iterdir())
    except OSError as exc:
        raise _registry_error(f"comparisons/: {exc}") from exc
    for path in entries:
        if path.is_dir():
            nested = [p for p in path.rglob("*") if p.suffix in (".yaml", ".yml")]
            if any(_looks_like_suite(p) for p in nested):
                raise _registry_error(f"comparisons/{path.name}/ holds a suite file")
            continue
        if path.suffix not in (".yaml", ".yml"):
            continue
        if path.name.endswith((".fixtures.yaml", ".fixtures.yml")):
            continue
        try:
            doc = yaml.safe_load(path.read_text())
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            raise _registry_error(f"{path.name}: {exc}") from exc
        if not isinstance(doc, Mapping):
            raise _registry_error(f"{path.name}: not a mapping")
        found = [_runner_suite(path, doc)] if "runner" in doc else _manifest_suites(path, doc)
        for suite in found:
            if suite.name in suites:
                raise _registry_error(f"duplicate suite name {suite.name!r}")
            suites[suite.name] = suite
    if not suites:
        raise _registry_error("comparisons/ holds no suite")
    return [suites[name] for name in sorted(suites)]


def _looks_like_suite(path: Path) -> bool:
    try:
        doc = yaml.safe_load(path.read_text())
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return True
    return isinstance(doc, Mapping) and ("runner" in doc or "suites" in doc)


@dataclass(frozen=True)
class Declaration:
    id: str
    runner_types: tuple[str, ...] | None
    suites: tuple[str, ...] | None
    source: str | None
    reads_rulespec_us: bool
    roots: tuple[str, ...]
    paths: tuple[str, ...]
    sources: tuple[str, ...]

    def matches(self, suite: Suite) -> bool:
        if self.runner_types is not None and suite.runner_type not in self.runner_types:
            return False
        if self.suites is not None and not any(
            fnmatch.fnmatchcase(suite.name, pattern) for pattern in self.suites
        ):
            return False
        if self.source is not None and suite.file != self.source:
            return False
        return True


def _string_list(value: Any, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise AlignmentError("coverage_declarations_unreadable", f"{label} is not a string list")
    return tuple(value)


def load_declarations(registry_root: Path) -> tuple[list[Declaration], str]:
    """The coverage declarations and the sha256 of their file."""
    path = Path(registry_root) / COVERAGE_FILE
    try:
        raw = path.read_bytes()
        doc = yaml.safe_load(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise AlignmentError(
            "coverage_declarations_unreadable", f"{COVERAGE_FILE}: {type(exc).__name__}"
        ) from exc
    if not isinstance(doc, Mapping) or doc.get("schema") != COVERAGE_SCHEMA:
        raise AlignmentError("coverage_declarations_unreadable", "unknown schema")
    sets = doc.get("sets") or {}
    if not isinstance(sets, Mapping):
        raise AlignmentError("coverage_declarations_unreadable", "sets is not a mapping")
    named = {str(key): _string_list(value, f"set {key}") for key, value in sets.items()}

    def expand(values: tuple[str, ...], label: str) -> tuple[str, ...]:
        out: list[str] = []
        for value in values:
            if value.startswith("@"):
                if value[1:] not in named:
                    raise AlignmentError(
                        "coverage_declarations_unreadable", f"{label}: unknown set {value}"
                    )
                out.extend(named[value[1:]])
            else:
                out.append(value)
        for pattern in out:
            if pattern.startswith("/") or ".." in pattern.split("/") or not pattern:
                raise AlignmentError(
                    "coverage_declarations_unreadable", f"{label}: bad glob {pattern!r}"
                )
        return tuple(out)

    rows = doc.get("declarations")
    if not isinstance(rows, list):
        raise AlignmentError("coverage_declarations_unreadable", "declarations is not a list")
    declarations: list[Declaration] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("id"), str):
            raise AlignmentError("coverage_declarations_unreadable", "declaration without an id")
        label = f"declaration {row['id']}"
        if row["id"] in seen:
            raise AlignmentError("coverage_declarations_unreadable", f"{label}: duplicate id")
        seen.add(row["id"])
        unknown = set(row) - {"id", "match", "reads_rulespec_us", "roots", "paths", "sources"}
        if unknown:
            raise AlignmentError(
                "coverage_declarations_unreadable", f"{label}: unknown keys {sorted(unknown)}"
            )
        match = row.get("match")
        if not isinstance(match, Mapping) or not match or set(match) - {
            "runner_type",
            "suites",
            "source",
        }:
            raise AlignmentError("coverage_declarations_unreadable", f"{label}: bad match")
        reads = row.get("reads_rulespec_us", True)
        if not isinstance(reads, bool):
            raise AlignmentError(
                "coverage_declarations_unreadable", f"{label}: reads_rulespec_us is not a boolean"
            )
        roots = expand(_string_list(row.get("roots"), f"{label} roots"), label)
        paths = expand(_string_list(row.get("paths"), f"{label} paths"), label)
        if reads and not (roots or paths):
            raise AlignmentError(
                "coverage_declarations_unreadable", f"{label}: declares no roots and no paths"
            )
        if not reads and (roots or paths):
            raise AlignmentError(
                "coverage_declarations_unreadable",
                f"{label}: reads_rulespec_us is false but globs are given",
            )
        source = match.get("source")
        if source is not None and not isinstance(source, str):
            raise AlignmentError("coverage_declarations_unreadable", f"{label}: bad source")
        declarations.append(
            Declaration(
                id=row["id"],
                runner_types=(
                    _string_list(match["runner_type"], f"{label} runner_type")
                    if "runner_type" in match
                    else None
                ),
                suites=_string_list(match["suites"], f"{label} suites") if "suites" in match else None,
                source=source,
                reads_rulespec_us=reads,
                roots=roots,
                paths=paths,
                sources=_string_list(row.get("sources"), f"{label} sources"),
            )
        )
        for source_file in declarations[-1].sources:
            if not (Path(registry_root) / source_file).is_file():
                raise AlignmentError(
                    "coverage_declarations_unreadable",
                    f"{label}: source {source_file} does not exist",
                )
    return declarations, sha256_bytes(raw)


def _fill(patterns: tuple[str, ...], suite: Suite, declaration: Declaration) -> tuple[str, ...]:
    out = []
    for pattern in patterns:
        for variable in re.findall(r"\{([a-z_]+)\}", pattern):
            if variable not in suite.variables:
                raise AlignmentError(
                    "coverage_declarations_unreadable",
                    f"declaration {declaration.id} needs {{{variable}}}, which suite "
                    f"{suite.name} does not give",
                )
            pattern = pattern.replace(f"{{{variable}}}", suite.variables[variable])
        out.append(pattern)
    return tuple(out)


def bind_suites(
    suites: Sequence[Suite], known_programs: set[str], declarations: Sequence[Declaration]
) -> list[BoundSuite]:
    """Give every suite the one way it covers a rulespec-us change.

    A suite that replays a pinned snapshot, or has no Axiom side, covers
    nothing. Otherwise a named program file that compiled binds the suite to
    that program; a parameter manifest row is bound to its files; any other
    suite must match exactly one declaration. A suite left without a binding
    raises ``reference_unbound``: it could cover anything.
    """
    bound: list[BoundSuite] = []
    unbound: list[str] = []
    for suite in suites:
        matching = [d for d in declarations if d.matches(suite)]
        if len(matching) > 1:
            raise AlignmentError(
                "coverage_declarations_unreadable",
                f"suite {suite.name} matches declarations {[d.id for d in matching]}",
            )
        if suite.pinned:
            bound.append(BoundSuite(suite, BINDING_PINNED))
        elif suite.no_axiom_side:
            bound.append(BoundSuite(suite, BINDING_NO_AXIOM))
        elif suite.program_key is not None and suite.program_key in known_programs:
            bound.append(BoundSuite(suite, BINDING_PROGRAM))
        elif suite.parameter_files:
            bound.append(
                BoundSuite(suite, BINDING_PARAMETER_FILES, roots=suite.parameter_files)
            )
        elif matching:
            declaration = matching[0]
            if not declaration.reads_rulespec_us:
                bound.append(BoundSuite(suite, BINDING_NONE, declaration.id))
            else:
                bound.append(
                    BoundSuite(
                        suite,
                        BINDING_DECLARED,
                        declaration.id,
                        roots=_fill(declaration.roots, suite, declaration),
                        paths=_fill(declaration.paths, suite, declaration),
                    )
                )
        else:
            unbound.append(suite.name)
    if unbound:
        raise AlignmentError(
            "reference_unbound",
            f"{len(unbound)} suites have no program binding and no coverage declaration "
            f"in {COVERAGE_FILE}: {', '.join(sorted(unbound))}",
        )
    return bound


# ---------------------------------------------------------------------------
# Reach and expected suites
# ---------------------------------------------------------------------------


def compute_reach(
    changed: Sequence[Mapping[str, Any]],
    programs: Mapping[str, Sequence[ProgramFile]],
    compiled: Mapping[str, Mapping[str, CompiledProgram]],
    suites: Sequence[Suite],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, set[str]]]]:
    """Per changed file, the programs whose compared outputs depend on it.

    Returns ``(reach rows, suite_concept_reach)`` where
    ``suite_concept_reach[suite][side]`` is the set of modules the suite's own
    compared concepts reach in its program.
    """
    suites_by_program: dict[str, list[Suite]] = {}
    for suite in suites:
        if suite.program_key:
            suites_by_program.setdefault(suite.program_key, []).append(suite)

    reached: dict[str, dict[str, dict[str, set[str]]]] = {side: {} for side in SIDES}
    suite_reach: dict[str, dict[str, set[str]]] = {}
    unresolved: dict[str, set[str]] = {}
    widened: set[str] = set()
    for side in SIDES:
        for program in programs.get(side, []):
            unit = compiled[side].get(program.key)
            if unit is None:
                raise AlignmentError(
                    "program_count_mismatch", f"{program.key} ({side}) was not compiled"
                )
            roots = []
            for output in program_outputs(program):
                name = unit.resolve_root(output)
                if name is None:
                    raise AlignmentError(
                        "output_not_in_compiled_program",
                        f"{program.key} ({side}) declares output {output!r} "
                        "that its compiled program does not define",
                    )
                roots.append(name)
            for suite in suites_by_program.get(program.key, []):
                concept_roots = []
                for concept in suite.concepts:
                    name = unit.resolve_root(concept)
                    if name is None:
                        # The suite compares something this walk cannot place
                        # in the program (a concept the harness maps to another
                        # rule name). Every rule of the program then counts as
                        # compared: wider than the truth, never narrower.
                        unresolved.setdefault(suite.name, set()).add(concept)
                        concept_roots = list(unit.derived_by_name)
                        break
                    concept_roots.append(name)
                roots.extend(concept_roots)
                suite_reach.setdefault(suite.name, {})[side] = set(
                    unit.reached_modules(concept_roots)
                )
            reached[side][program.key] = unit.reached_modules(roots)
            if any(s.name in unresolved for s in suites_by_program.get(program.key, [])):
                widened.add(program.key)

    rows = []
    for item in changed:
        row: dict[str, Any] = {
            "path": item["path"],
            "kind": item["kind"],
            "module": item["module"],
            "reaching_programs": [],
        }
        hits: dict[str, dict[str, Any]] = {}
        if item["kind"] == "program":
            for side in SIDES:
                key = f"{ORIGIN_RULESPEC}:{item['path']}"
                if key in compiled[side]:
                    hits.setdefault(key, {"program": key, "sides": [], "via": "program_file"})[
                        "sides"
                    ].append(side)
        elif item["kind"] == "module":
            for side in SIDES:
                for key, modules in reached[side].items():
                    names = modules.get(item["module"])
                    if not names:
                        continue
                    hit = hits.setdefault(
                        key,
                        {
                            "program": key,
                            "sides": [],
                            "via": (
                                "every_rule_unresolved_suite_concept"
                                if key in widened
                                else "compared_outputs"
                            ),
                            "reached": set(),
                        },
                    )
                    hit["sides"].append(side)
                    hit["reached"] |= names
        for key in sorted(hits):
            hit = hits[key]
            if "reached" in hit:
                hit["reached"] = sorted(hit["reached"])
            row["reaching_programs"].append(hit)
        rows.append(row)
    for name, concepts in unresolved.items():
        suite_reach.setdefault(name, {})["unresolved_concepts"] = set(concepts)
    return rows, suite_reach


class DeclaredCoverage:
    """What declared suites cover in the two trees.

    A declared root is a module file the harness compiles; the suite covers
    it and every module it names, transitively, in either tree. A declared
    path is a file the harness reads as a file.
    """

    def __init__(self, trees: Mapping[str, TreeIndex]) -> None:
        self.trees = trees
        self._covered: dict[tuple[str, ...], set[str]] = {}
        self._regex: dict[str, re.Pattern[str]] = {}

    def regex(self, pattern: str) -> re.Pattern[str]:
        if pattern not in self._regex:
            self._regex[pattern] = glob_regex(pattern)
        return self._regex[pattern]

    def path_matches(self, patterns: Iterable[str], path: str) -> bool:
        return any(self.regex(pattern).match(path) for pattern in patterns)

    def covered_modules(self, roots: tuple[str, ...]) -> set[str]:
        if roots not in self._covered:
            covered: set[str] = set()
            for tree in self.trees.values():
                seeds = {
                    module
                    for path, module in tree.modules.items()
                    if self.path_matches(roots, path)
                }
                covered |= tree.closure(seeds)
            self._covered[roots] = covered
        return self._covered[roots]

    def covers(self, bound: BoundSuite, row: Mapping[str, Any]) -> str | None:
        """How ``bound`` covers one changed file, or ``None``."""
        path = row["path"]
        if self.path_matches(bound.roots, path) or self.path_matches(bound.paths, path):
            return "declared_path"
        if row["kind"] == "module" and row["module"] in self.covered_modules(bound.roots):
            return "declared_root_closure"
        return None


def expected_suites(
    reach: Sequence[Mapping[str, Any]],
    bound_suites: Sequence[BoundSuite],
    suite_concept_reach: Mapping[str, Mapping[str, set[str]]],
    coverage: DeclaredCoverage,
) -> list[dict[str, Any]]:
    """The suites that can observe the change."""
    reaching = {hit["program"] for row in reach for hit in row["reaching_programs"]}
    changed_modules = {row["module"] for row in reach if row["kind"] == "module"}
    out = []
    for bound in bound_suites:
        suite = bound.suite
        entry: dict[str, Any] | None = None
        if bound.binding == BINDING_PROGRAM and suite.program_key in reaching:
            own: set[str] = set()
            own_reach = suite_concept_reach.get(suite.name, {})
            for side in SIDES:
                own |= own_reach.get(side, set())
            program_changed = any(
                hit["program"] == suite.program_key and hit["via"] == "program_file"
                for row in reach
                for hit in row["reaching_programs"]
            )
            entry = {
                "binding": bound.binding,
                "program": suite.program_key,
                "compared_concepts_reach_change": bool(own & changed_modules) or program_changed,
            }
            if own_reach.get("unresolved_concepts"):
                entry["unresolved_concepts"] = sorted(own_reach["unresolved_concepts"])
        elif bound.binding in (BINDING_DECLARED, BINDING_PARAMETER_FILES):
            covered = {}
            for row in reach:
                how = coverage.covers(bound, row)
                if how:
                    covered[row["path"]] = how
            if covered:
                entry = {"binding": bound.binding, "covered_files": covered}
                if bound.declaration:
                    entry["declaration"] = bound.declaration
        if entry is not None:
            out.append(
                {
                    "suite": suite.name,
                    "file": suite.file,
                    "ci": suite.ci,
                    "mode": suite.mode,
                    "runner_type": suite.runner_type,
                    **entry,
                }
            )
    return out


# ---------------------------------------------------------------------------
# Suite execution and per-case comparison
# ---------------------------------------------------------------------------


class SuiteExecutor(Protocol):
    #: ``live_run`` or ``supplied_reports``.
    evidence: str

    def bind(self, registry_commit: str, commits: Mapping[str, str]) -> None:
        """Check that this executor's reports belong to these commits."""

    def run(self, suite: str, side: str) -> Mapping[str, Any]:
        """Run ``suite`` against one side and return its comparison report."""


class ReportsDirExecutor:
    """Read already-produced reports from ``<dir>/<side>/<suite>.json``.

    ``<dir>/manifest.json`` must name the registry commit and both rulespec-us
    commits the reports were produced with and the sha256 of every report
    file. The manifest is the supplier's own statement: it binds the files to
    one run of this report, it does not prove who ran them.
    """

    evidence = "supplied_reports"

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self._manifest: Mapping[str, Any] | None = None

    def bind(self, registry_commit: str, commits: Mapping[str, str]) -> None:
        path = self.directory / "manifest.json"
        try:
            manifest = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            raise AlignmentError(
                "supplied_reports_unbound", f"manifest.json: {type(exc).__name__}"
            ) from exc
        if not isinstance(manifest, Mapping) or manifest.get("schema") != SUPPLIED_SCHEMA:
            raise AlignmentError("supplied_reports_unbound", "manifest.json: unknown schema")
        if manifest.get("registry_commit") != registry_commit:
            raise AlignmentError(
                "supplied_reports_unbound",
                "the reports were produced with another registry commit",
            )
        if manifest.get("rulespec_commit") != dict(commits):
            raise AlignmentError(
                "supplied_reports_unbound",
                "the reports were produced for other rulespec-us commits",
            )
        if not isinstance(manifest.get("reports"), Mapping):
            raise AlignmentError("supplied_reports_unbound", "manifest.json lists no reports")
        self._manifest = manifest

    def run(self, suite: str, side: str) -> Mapping[str, Any]:
        if self._manifest is None:
            raise AlignmentError("supplied_reports_unbound", "the manifest was not checked")
        path = self.directory / side / f"{suite}.json"
        try:
            raw = path.read_bytes()
        except FileNotFoundError as exc:
            raise AlignmentError(
                "suite_run_failed", f"no {side} report for suite {suite}"
            ) from exc
        except OSError as exc:
            raise AlignmentError(
                "suite_run_failed", f"{side} report for suite {suite} unreadable: {exc}"
            ) from exc
        listed = self._manifest["reports"].get(suite)
        if not isinstance(listed, Mapping) or listed.get(side) != sha256_bytes(raw):
            raise AlignmentError(
                "supplied_reports_unbound",
                f"the {side} report of suite {suite} is not the file the manifest lists",
            )
        try:
            return json.loads(raw)
        except ValueError as exc:
            raise AlignmentError(
                "suite_run_failed", f"{side} report for suite {suite} unreadable: {exc}"
            ) from exc


class RunComparisonExecutor:
    """Run ``scripts/run_comparison.py <suite>`` with ``HOME`` set per side.

    Suite files name their checkouts under ``$HOME`` (``$HOME/rulespec-us``),
    so each side gets a home directory that holds that side's ``rulespec-us``
    checkout. Tool repositories and caches of the real home are linked in.
    """

    evidence = "live_run"
    LINKED = ("axiom-compose", "axiom-rules-engine", "axiom-rules", "axiom-encode")
    CACHE_ENV = {
        "UV_CACHE_DIR": ".cache/uv",
        "UV_PYTHON_INSTALL_DIR": ".local/share/uv/python",
        "HF_HOME": ".cache/huggingface",
        "CARGO_HOME": ".cargo",
        "RUSTUP_HOME": ".rustup",
    }

    def __init__(
        self,
        *,
        registry_root: Path,
        homes: Mapping[str, Path],
        output_dir: Path,
        timeout: float = 3600.0,
        runner: Callable[..., Any] = subprocess.run,
    ) -> None:
        self.registry_root = Path(registry_root)
        self.homes = {side: Path(home) for side, home in homes.items()}
        self.output_dir = Path(output_dir)
        self.timeout = timeout
        self.runner = runner

    def bind(self, registry_commit: str, commits: Mapping[str, str]) -> None:
        return None

    def _environment(self, side: str) -> dict[str, str]:
        real_home = Path(os.environ.get("HOME", str(Path.home())))
        home = self.homes[side]
        env = dict(os.environ)
        for name, rel in self.CACHE_ENV.items():
            env.setdefault(name, str(real_home / rel))
        for name in self.LINKED:
            source = real_home / name
            target = home / name
            if source.exists() and not target.exists():
                target.symlink_to(source, target_is_directory=True)
        env["HOME"] = str(home)
        return env

    def run(self, suite: str, side: str) -> Mapping[str, Any]:
        out = self.output_dir / side / suite
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)
        cmd = [
            sys.executable,
            str(self.registry_root / "scripts" / "run_comparison.py"),
            suite,
            "--require-live",
            "--output-dir",
            str(out),
        ]
        try:
            result = self.runner(
                cmd,
                text=True,
                capture_output=True,
                check=False,
                timeout=self.timeout,
                cwd=str(self.registry_root),
                env=self._environment(side),
            )
        except subprocess.TimeoutExpired as exc:
            raise AlignmentError("timeout", f"suite {suite} ({side})") from exc
        if result.returncode != 0:
            raise AlignmentError(
                "suite_run_failed",
                f"suite {suite} ({side}) exited {result.returncode}: "
                f"{_tail(result.stderr or result.stdout)}",
            )
        reports = sorted(p for p in out.glob("*.json") if not p.name.endswith(".receipt.json"))
        if len(reports) != 1:
            raise AlignmentError(
                "suite_run_failed",
                f"suite {suite} ({side}) wrote {len(reports)} reports, expected 1",
            )
        try:
            return json.loads(reports[0].read_text())
        except (OSError, ValueError) as exc:
            raise AlignmentError(
                "suite_run_failed", f"suite {suite} ({side}) report unreadable: {exc}"
            ) from exc


@dataclass
class ParsedReport:
    #: ``case_id -> {state, mismatched, compared}``.
    cases: dict[str, dict[str, Any]]
    shape: str
    engine: Any
    oracle: Any


def _positive(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def parse_report(report: Mapping[str, Any], suite: str, side: str, commit: str) -> ParsedReport:
    """Check that a report is one live run of ``suite`` on ``commit`` and
    read its per-case states.

    Three case shapes are read: the population comparison (``matches`` /
    ``mismatches`` / ``left_errors`` / ``right_errors`` per case), the SNAP QC
    replay and boundary grids (``matched`` per case), and the federal tax
    grids (``match`` per case). Any other shape is an error.
    """
    label = f"suite {suite} ({side})"

    def fail(cause: str, detail: str) -> AlignmentError:
        return AlignmentError(cause, f"{label}: {detail}")

    if not isinstance(report, Mapping):
        raise fail("suite_run_failed", "the report is not an object")
    if report.get("suite") != suite:
        raise fail("suite_run_failed", f"the report names suite {report.get('suite')!r}")
    provenance = report.get("provenance")
    if not isinstance(provenance, Mapping):
        raise fail("suite_report_provenance_mismatch", "the report has no provenance")
    if provenance.get("reemitted_report") or "reemit" in str(provenance.get("run_kind", "")).lower():
        raise fail("suite_run_failed", "the run re-emitted a committed report instead of running")
    generated_by = str(provenance.get("generated_by", ""))
    if "::" not in generated_by or generated_by.rsplit("::", 1)[-1] != suite:
        raise fail("suite_report_provenance_mismatch", f"generated by {generated_by!r}")
    rows = provenance.get("rulespecs")
    ours = [
        row
        for row in (rows if isinstance(rows, list) else [])
        if isinstance(row, Mapping) and row.get("repo") == RULESPEC_REPO
    ]
    if len(ours) != 1 or ours[0].get("sha") != commit:
        raise fail(
            "suite_report_provenance_mismatch",
            f"ran against rulespec-us {[row.get('sha') for row in ours] or 'unrecorded'}, "
            f"expected exactly {commit}",
        )
    if ours[0].get("dirty") is not False:
        raise fail(
            "suite_report_provenance_mismatch",
            "the report does not record a clean rulespec-us checkout",
        )
    oracle = provenance.get("oracle")
    if not isinstance(oracle, Mapping) or not oracle:
        raise fail("suite_report_provenance_mismatch", "the report records no oracle identity")

    truncation = report.get("dashboard_truncation")
    if isinstance(truncation, Mapping) and truncation.get("shown_case_rows") != truncation.get(
        "total_case_rows"
    ):
        raise fail("suite_report_truncated", "the report is a truncated dashboard copy")
    cases = report.get("cases")
    if not isinstance(cases, list) or not cases:
        raise fail("zero_cases", "the report has no cases")
    declared = report.get("case_count")
    if not isinstance(declared, int) or isinstance(declared, bool):
        raise fail("suite_report_truncated", "the report records no case_count")
    if declared != len(cases):
        raise fail(
            "suite_report_truncated",
            f"case_count is {declared} but {len(cases)} case rows are present",
        )

    top_rows = [row for row in (report.get("mismatches") or []) if isinstance(row, Mapping)]
    top_by_case: dict[str, set[str]] = {}
    for row in top_rows:
        top_by_case.setdefault(str(row.get("case_id")), set()).add(str(row.get("concept")))
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    run_errors = bool(report.get("errors")) or any(
        _positive(summary.get(key)) for key in ("error_count", "error_case_count")
    )

    parsed: dict[str, dict[str, Any]] = {}
    shapes: set[str] = set()
    for case in cases:
        if not isinstance(case, Mapping) or not isinstance(case.get("case_id"), str):
            raise fail("suite_run_failed", "a case row has no case_id")
        case_id = case["case_id"]
        if "matches" in case or "left_errors" in case or "right_errors" in case:
            shape = "population"
            mismatches = [m for m in (case.get("mismatches") or []) if isinstance(m, Mapping)]
            matches = [m for m in (case.get("matches") or []) if isinstance(m, Mapping)]
            mismatched = {str(row.get("concept")) for row in mismatches}
            compared = mismatched | {str(row.get("concept")) for row in matches}
            if case.get("left_errors") or case.get("right_errors"):
                state = "error"
            elif mismatches:
                state = "mismatch"
            elif matches:
                state = "match"
            else:
                raise fail("suite_run_failed", f"case {case_id!r} compared nothing")
        elif isinstance(case.get("matched"), bool) or isinstance(case.get("match"), bool):
            flag = case["matched"] if isinstance(case.get("matched"), bool) else case["match"]
            shape = "replay" if "matched" in case else "grid"
            if case.get("yrmonth") is not None:
                case_id = f"{case_id}@{case['yrmonth']}"
            if run_errors:
                raise fail(
                    "suite_run_failed",
                    "the run recorded errors, and this report shape does not say which cases",
                )
            concept = str(case.get("concept") or report.get("concept") or "*")
            compared = {concept}
            state = "match" if flag else "mismatch"
            mismatched = set() if flag else (top_by_case.get(case["case_id"]) or {UNATTRIBUTED})
        else:
            raise fail(
                "suite_report_shape_unsupported",
                f"case rows carry {sorted(case)[:8]}; no per-case match state is read from them",
            )
        shapes.add(shape)
        if case_id in parsed:
            raise fail("suite_run_failed", f"duplicate case id {case_id!r}")
        parsed[case_id] = {"state": state, "mismatched": mismatched, "compared": compared}
    if len(shapes) != 1:
        raise fail("suite_report_shape_unsupported", f"mixed case shapes {sorted(shapes)}")
    return ParsedReport(
        cases=parsed, shape=shapes.pop(), engine=provenance.get("engine"), oracle=dict(oracle)
    )


def dispositioned_pairs(
    report: Mapping[str, Any], dispositions: Mapping[str, Any] | None
) -> set[tuple[str, str]]:
    """``(case_id, concept)`` of mismatch rows a disposition entry selects."""
    from axiom_oracles.comparison.dispositions import select_rows

    entries = list((dispositions or {}).get("entries") or [])
    rows = [row for row in (report.get("mismatches") or []) if isinstance(row, Mapping)]
    if not entries or not rows:
        return set()
    winners, _, _, _ = select_rows(entries, [dict(row) for row in rows], conservation=False)
    return {
        (str(row.get("case_id")), str(row.get("concept")))
        for row, winner in zip(rows, winners)
        if winner is not None
    }


def compare_suite_reports(
    suite: str,
    base: Mapping[str, Any],
    candidate: Mapping[str, Any],
    dispositions: Mapping[str, Any] | None = None,
    *,
    commits: Mapping[str, str],
) -> dict[str, Any]:
    """Per-case comparison of a suite's base and candidate reports.

    ``regressed`` when a case that matched, or errored, on base mismatches on
    candidate, or a compared output that matched now mismatches, and no
    disposition entry selects every new mismatch row of the case; or when a
    case newly errors. Both reports must hold the same cases and compare, in
    every case, at least the outputs base compared.
    """
    for side in SIDES:
        if not commits.get(side):
            raise AlignmentError(
                "side_commit_unknown", f"no {side} commit to check suite {suite}'s report against"
            )
    before_report = parse_report(base, suite, "base", commits["base"])
    after_report = parse_report(candidate, suite, "candidate", commits["candidate"])
    before, after = before_report.cases, after_report.cases
    if before_report.shape != after_report.shape:
        raise AlignmentError(
            "suite_report_shape_unsupported", f"suite {suite}: the two reports differ in shape"
        )
    if before_report.oracle != after_report.oracle:
        raise AlignmentError(
            "suite_report_provenance_mismatch",
            f"suite {suite}: base and candidate ran against different oracle identities",
        )
    if before_report.engine != after_report.engine:
        raise AlignmentError(
            "suite_report_provenance_mismatch",
            f"suite {suite}: base and candidate ran with different engine identities",
        )
    if len(before) != len(after):
        raise AlignmentError(
            "case_count_differs",
            f"suite {suite}: {len(before)} base cases, {len(after)} candidate cases",
        )
    if set(before) != set(after):
        raise AlignmentError("case_ids_differ", f"suite {suite}: base and candidate case ids differ")
    selected = dispositioned_pairs(candidate, dispositions)

    counts = {
        "cases": len(before),
        "matched_before": 0,
        "matched_after": 0,
        "newly_matched": 0,
        "newly_mismatched": 0,
        "newly_errored": 0,
        "newly_mismatched_outputs_in_mismatched_cases": 0,
        "dispositioned": 0,
        "undispositioned_regressions": 0,
    }
    regressions: list[dict[str, Any]] = []
    for case_id in sorted(before):
        was, now = before[case_id], after[case_id]
        plain_id = case_id.split("@", 1)[0] if before_report.shape != "population" else case_id
        counts["matched_before"] += was["state"] == "match"
        counts["matched_after"] += now["state"] == "match"
        if was["state"] != "match" and now["state"] == "match":
            counts["newly_matched"] += 1
        if now["state"] == "error":
            if was["state"] != "error":
                counts["newly_errored"] += 1
                counts["undispositioned_regressions"] += 1
                regressions.append({"case_id": case_id, "kind": "newly_errored"})
            continue
        if was["state"] != "error" and not was["compared"] <= now["compared"]:
            raise AlignmentError(
                "compared_outputs_differ",
                f"suite {suite}: case {case_id!r} no longer compares "
                f"{sorted(was['compared'] - now['compared'])}",
            )
        if now["state"] != "mismatch":
            continue
        if was["state"] == "mismatch":
            new_concepts = set(now["mismatched"]) - set(was["mismatched"])
            if not new_concepts:
                continue
            kind = "newly_mismatched_output"
            counts["newly_mismatched_outputs_in_mismatched_cases"] += 1
        else:
            # A case that matched, or that did not run to a comparison, on base.
            new_concepts = set(now["mismatched"])
            kind = "newly_mismatched"
            counts["newly_mismatched"] += 1
        if new_concepts and all((plain_id, concept) in selected for concept in new_concepts):
            counts["dispositioned"] += 1
            continue
        counts["undispositioned_regressions"] += 1
        regressions.append({"case_id": case_id, "kind": kind, "concepts": sorted(new_concepts)})
    return {
        "suite": suite,
        "status": STATUS_REGRESSED if counts["undispositioned_regressions"] else STATUS_ALIGNED,
        "report_shape": before_report.shape,
        "engine_identity_recorded": bool(before_report.engine),
        "counts": counts,
        "regressions": regressions[:200],
        "regressions_truncated": len(regressions) > 200,
    }


# ---------------------------------------------------------------------------
# Status derivation
# ---------------------------------------------------------------------------


def derive_status(
    reach: Sequence[Mapping[str, Any]],
    expected: Sequence[Mapping[str, Any]],
    executions: Sequence[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """The single status of a completed derivation.

    Called only after reach, the suite bindings and the expected suite set
    were computed without a failure; a failure never reaches this function.
    ``executions`` is ``None`` when suites were not executed, otherwise one
    result per runnable expected suite.
    """
    runnable = [s["suite"] for s in expected if s["mode"] == MODE_RUNNABLE]
    manual = [s["suite"] for s in expected if s["mode"] != MODE_RUNNABLE]
    if not expected:
        reaching = any(row["reaching_programs"] for row in reach)
        return {
            "status": STATUS_NO_REFERENCE,
            "reason": REASON_NO_SUITE if reaching else REASON_NO_PROGRAM,
        }
    if not runnable:
        return {"status": STATUS_NOT_RUNNABLE, "manual_suites": manual}
    if executions is None:
        return {
            "status": STATUS_NOT_EXECUTED,
            "runnable_suites": runnable,
            "manual_suites": manual,
        }
    executed = [e["suite"] for e in executions]
    if sorted(executed) != sorted(runnable):
        raise AlignmentError(
            "suite_run_incomplete",
            f"executed {sorted(executed)}, expected the runnable suites {sorted(runnable)}",
        )
    totals: dict[str, int] = {}
    for execution in executions:
        if execution.get("status") not in (STATUS_ALIGNED, STATUS_REGRESSED):
            raise AlignmentError(
                "suite_run_failed", f"suite {execution.get('suite')} has no comparison result"
            )
        for key, value in execution["counts"].items():
            totals[key] = totals.get(key, 0) + int(value)
    regressed = [e["suite"] for e in executions if e["status"] == STATUS_REGRESSED]
    return {
        "status": STATUS_REGRESSED if regressed else STATUS_ALIGNED,
        "executed_suites": sorted(executed),
        "regressed_suites": sorted(regressed),
        "manual_suites_not_run": manual,
        "counts": totals,
    }


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------


@dataclass
class AlignmentInputs:
    base_root: Path
    candidate_root: Path
    registry_root: Path
    compiler: Compiler
    changed: Sequence[str] | None = None
    executor: SuiteExecutor | None = None
    include_registry_programs: bool = True
    jobs: int = 4
    reuse_unchanged_programs: bool = True
    cache: CompileCache | None = None
    toolchain: Mapping[str, Any] = field(default_factory=dict)


def _load_dispositions(registry_root: Path, suite: str) -> Mapping[str, Any] | None:
    from axiom_oracles.comparison.dispositions import (
        DispositionError,
        dispositions_path_for_suite,
        load_dispositions,
    )

    path = dispositions_path_for_suite(Path(registry_root) / "dispositions", suite)
    if path is None:
        return None
    try:
        return load_dispositions(path, repo_root=Path(registry_root))
    except (DispositionError, OSError, yaml.YAMLError) as exc:
        raise AlignmentError("dispositions_unreadable", f"{path.name}: {_tail(str(exc))}") from exc


def _derive(inputs: AlignmentInputs, report: dict[str, Any]) -> None:
    registry_root = Path(inputs.registry_root)
    provenance = report["provenance"]

    registry_sha = git_head(registry_root)
    if registry_sha is None:
        raise AlignmentError("registry_unreadable", "the registry is not a git checkout")
    provenance["registry_commit"] = registry_sha
    provenance["registry_dirty"] = git_dirty(registry_root)

    checkouts = {
        "base": read_checkout(inputs.base_root, "base"),
        "candidate": read_checkout(inputs.candidate_root, "candidate"),
    }
    commits = {side: checkouts[side].commit for side in SIDES}
    provenance["rulespec_commit"] = dict(commits)
    provenance["rulespec_tree_files"] = {side: len(checkouts[side].blobs) for side in SIDES}

    suites = load_suites(registry_root)
    declarations, declarations_sha = load_declarations(registry_root)
    provenance["coverage_declarations_sha256"] = declarations_sha

    changed = changed_files(checkouts["base"], checkouts["candidate"], inputs.changed)
    if not changed:
        raise AlignmentError("no_changed_files", "base and candidate do not differ")
    provenance["changed_files"] = changed

    trees = {side: TreeIndex(checkouts[side]) for side in SIDES}
    programs: dict[str, list[ProgramFile]] = {}
    for side in SIDES:
        programs[side] = checkout_programs(checkouts[side])
        if not programs[side]:
            raise AlignmentError(
                "no_programs",
                f"{side}: the commit tracks no program file under programs/; "
                "this is not a rulespec-us tree the report can read",
            )
        if inputs.include_registry_programs:
            programs[side] += discover_programs(registry_root, ORIGIN_REGISTRY)
    compiled, counts = compile_programs(
        programs,
        inputs.compiler,
        jobs=inputs.jobs,
        trees=trees if inputs.reuse_unchanged_programs else None,
        cache=(inputs.cache or CompileCache()) if inputs.reuse_unchanged_programs else None,
    )
    report["programs"] = counts
    provenance["compiled_programs"] = {
        side: {key: unit.sha256 for key, unit in sorted(compiled[side].items())} for side in SIDES
    }
    provenance["engine_versions"] = sorted(
        {unit.engine_version for side in SIDES for unit in compiled[side].values() if unit.engine_version}
    )

    known_programs = {key for side in SIDES for key in compiled[side]}
    bound = bind_suites(suites, known_programs, declarations)
    by_binding: dict[str, int] = {}
    for item in bound:
        by_binding[item.binding] = by_binding.get(item.binding, 0) + 1
    report["suite_registry"] = {
        "suites": len(suites),
        "runnable": sum(s.mode == MODE_RUNNABLE for s in suites),
        "manual": sum(s.mode == MODE_MANUAL for s in suites),
        "by_binding": dict(sorted(by_binding.items())),
        "pinned_snapshot_suites": sorted(
            item.suite.name for item in bound if item.binding == BINDING_PINNED
        ),
    }

    reach, suite_reach = compute_reach(changed, programs, compiled, suites)
    report["reach"] = reach
    expected = expected_suites(reach, bound, suite_reach, DeclaredCoverage(trees))
    report["expected_suites"] = expected

    executions: list[dict[str, Any]] | None = None
    runnable = [s["suite"] for s in expected if s["mode"] == MODE_RUNNABLE]
    if inputs.executor is not None and runnable:
        inputs.executor.bind(registry_sha, commits)
        executions = []
        for suite in runnable:
            base = inputs.executor.run(suite, "base")
            candidate = inputs.executor.run(suite, "candidate")
            result = compare_suite_reports(
                suite,
                base,
                candidate,
                _load_dispositions(registry_root, suite),
                commits=commits,
            )
            result["evidence"] = inputs.executor.evidence
            executions.append(result)
        report["executions"] = executions

    report.update(derive_status(reach, expected, executions))


def build_report(inputs: AlignmentInputs) -> dict[str, Any]:
    """The alignment report. Never raises for a derivation failure: a failure
    is the report ``{"status": "error", "error": {"cause", "detail"}}``."""
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "report_only": True,
        "status": STATUS_ERROR,
        "provenance": {
            "tool": TOOL_NAME,
            "tool_version": tool_version(),
            "toolchain": dict(inputs.toolchain),
        },
    }
    try:
        _derive(inputs, report)
    except AlignmentError as exc:
        _mark_error(report, exc.cause, exc.detail)
    except Exception as exc:  # noqa: BLE001 - any failure is an error report
        _mark_error(report, "internal_error", f"{type(exc).__name__}: {_tail(str(exc))}")
    return report


def _mark_error(report: dict[str, Any], cause: str, detail: str) -> None:
    for key in ("reason", "manual_suites", "runnable_suites", "counts"):
        report.pop(key, None)
    report["status"] = STATUS_ERROR
    report["error"] = {"cause": cause, "detail": detail}


def exit_code(report: Mapping[str, Any]) -> int:
    """``0`` for every completed derivation (report only), ``2`` for an error."""
    return 2 if report.get("status") == STATUS_ERROR else 0


def materialize_checkout(source_repo: Path, revision: str, destination: Path) -> str:
    """Clone ``source_repo`` at ``revision`` into ``destination``.

    The clone keeps the source's ``origin`` URL so it is a canonical checkout
    for the engine. The source repository is only read.
    """
    destination = Path(destination)
    if destination.exists():
        raise AlignmentError("checkout_failed", f"{destination.name} already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)

    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args], text=True, capture_output=True, check=False, timeout=900
        )
        if result.returncode != 0:
            raise AlignmentError("checkout_failed", f"git {args[0]}: {_tail(result.stderr)}")
        return result.stdout.strip()

    origin = git("-C", str(source_repo), "remote", "get-url", "origin")
    sha = git("-C", str(source_repo), "rev-parse", "--verify", f"{revision}^{{commit}}")
    git("clone", "--quiet", "--shared", "--no-checkout", str(source_repo), str(destination))
    git("-C", str(destination), "remote", "set-url", "origin", origin)
    git("-C", str(destination), "checkout", "--quiet", "--detach", sha)
    return sha


def temporary_work_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="alignment-report.")).resolve()
