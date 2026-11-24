"""Oracle alignment report for a candidate RuleSpec change (report only).

Given a ``rulespec-us`` tree at a base commit, the same tree at a candidate
commit, and the suite registry of this repository, the report answers three
questions and gates nothing:

``reach``
    For each changed RuleSpec module, which ``programs/**.yaml`` files have a
    compared output that transitively depends on it. Every program file is
    composed and compiled the way ``scripts/run_comparison.py`` does it, and
    the dependency walk is :func:`axiom_oracles.coverage._transitive_dependencies`
    over the compiled program, extended to the parameters and relations the
    reached rules read. A program that fails to compile is an error: an
    incomplete walk is never read as "nothing reaches".

``expected_suites``
    The comparison suites bound to a reaching program, each marked
    ``runnable`` or ``manual`` from the suite file's ``ci`` key.

``status``
    Exactly one of ``no_reference``, ``reference_not_runnable``,
    ``reference_not_executed``, ``aligned``, ``regressed`` or ``error``.
    ``no_reference`` is reported only when the whole derivation completed and
    the expected suite set is empty. Any failure is ``error`` with a cause.

Nothing here reads household data. Execution of suites is delegated to an
executor object, so the derivation is testable with synthetic fixtures.
"""

from __future__ import annotations

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
TOOL_NAME = "axiom_oracles.alignment"
#: Bumped when the derivation rules change, independent of the package version.
DERIVATION_VERSION = "1"

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

SIDES = ("base", "candidate")

JURISDICTION_DIR = re.compile(r"^[a-z]{2}(-[a-z0-9]+)?$")
#: ``us:statutes/7/2014/e/2`` — a RuleSpec module id written as a literal.
MODULE_LITERAL = re.compile(
    r"(?<![A-Za-z0-9_/-])([a-z]{2}(?:-[a-z0-9]+)?):"
    r"((?:statutes|regulations|policies)/[A-Za-z0-9_.\-/]*[A-Za-z0-9_])"
)
#: Registry directories whose files can name a module the harness compiles
#: outside any ``programs/**.yaml`` file (bridges, overlays, generated programs).
HARNESS_SCAN_DIRS = ("axiom_oracles", "scripts", "comparisons")
HARNESS_SCAN_SUFFIXES = (".py", ".yaml", ".yml", ".json")
#: Runner types that compose ``programs/<jurisdiction>/snap/fy-2026.yaml`` from
#: a ``jurisdiction`` parameter instead of naming the program file.
JURISDICTION_SNAP_RUNNERS = ("snap-qc-compare",)


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
        return sha256_bytes(path.read_bytes())
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


def git_head(root: Path) -> str | None:
    """The commit a checkout is at, or ``None`` when ``root`` is not one."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "HEAD^{commit}"],
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    top = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    # A plain directory inside another repository is not a checkout of its own.
    if top.returncode != 0 or Path(top.stdout.strip()).resolve() != Path(root).resolve():
        return None
    return result.stdout.strip() or None


def git_dirty(root: Path) -> bool | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return bool(result.stdout.strip())


# ---------------------------------------------------------------------------
# Changed files
# ---------------------------------------------------------------------------


def _is_jurisdiction_path(relpath: str) -> bool:
    head = relpath.split("/", 1)[0]
    return "/" in relpath and bool(JURISDICTION_DIR.match(head))


def classify_path(relpath: str) -> tuple[str, str | None]:
    """``(kind, module_id)`` for a path relative to the rulespec root.

    ``program``: a ``programs/**.yaml`` file. ``module``: a RuleSpec module
    under a jurisdiction directory. ``other``: anything else (companion test
    files, manifests, tooling); it has no reach of its own.
    """
    relpath = relpath.strip().lstrip("./")
    if relpath.startswith("programs/") and relpath.endswith((".yaml", ".yml")):
        return "program", None
    if (
        _is_jurisdiction_path(relpath)
        and relpath.endswith(".yaml")
        and not relpath.endswith(".test.yaml")
    ):
        jurisdiction, rest = relpath.split("/", 1)
        return "module", f"{jurisdiction}:{rest[: -len('.yaml')]}"
    return "other", None


def _tree_digests(root: Path) -> dict[str, str]:
    """sha256 of every file under the jurisdiction dirs and ``programs/``."""
    digests: dict[str, str] = {}
    if not root.is_dir():
        raise AlignmentError("rulespec_root_unreadable", f"not a directory: {root.name}")
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if child.name != "programs" and not JURISDICTION_DIR.match(child.name):
            continue
        for path in sorted(child.rglob("*")):
            if path.is_file():
                digests[path.relative_to(root).as_posix()] = sha256_bytes(path.read_bytes())
    return digests


def changed_files(
    base_root: Path,
    candidate_root: Path,
    explicit: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """The changed files with both digests, from a tree diff or a given list.

    With ``explicit`` the list is taken as given, and a listed path whose
    bytes are identical on both sides is an error: the two trees are then not
    the base and candidate of that change.
    """
    if explicit is None:
        base = _tree_digests(base_root)
        candidate = _tree_digests(candidate_root)
        paths = sorted(p for p in set(base) | set(candidate) if base.get(p) != candidate.get(p))
        rows = [(p, base.get(p), candidate.get(p)) for p in paths]
    else:
        rows = []
        for raw in explicit:
            relpath = str(raw).strip().lstrip("./")
            if not relpath or relpath.startswith("/") or ".." in relpath.split("/"):
                raise AlignmentError("changed_file_invalid", f"not a relative path: {raw!r}")
            before = sha256_file(base_root / relpath)
            after = sha256_file(candidate_root / relpath)
            if before == after:
                raise AlignmentError(
                    "changed_file_unchanged",
                    f"{relpath} is identical (or absent) in base and candidate",
                )
            rows.append((relpath, before, after))
        rows.sort()
    out = []
    for relpath, before, after in rows:
        kind, module = classify_path(relpath)
        out.append(
            {
                "path": relpath,
                "kind": kind,
                "module": module,
                "base_sha256": before,
                "candidate_sha256": after,
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


def discover_programs(root: Path, origin: str) -> list[ProgramFile]:
    programs_dir = root / "programs"
    if not programs_dir.is_dir():
        return []
    found = []
    for path in sorted(programs_dir.rglob("*")):
        if path.is_file() and path.suffix in (".yaml", ".yml"):
            found.append(ProgramFile(origin, path.relative_to(root).as_posix(), path))
    return found


class Compiler(Protocol):
    def compile(self, program: ProgramFile, side: str) -> Mapping[str, Any]:
        """Return the compiled artifact (the engine's JSON) for one program."""


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

    def prepare(self) -> None:
        from axiom_oracles.engine_compat import stage_pure_root

        for binary in (self.compose_binary, self.engine_binary):
            if not binary.is_file():
                raise AlignmentError("toolchain_missing", f"no such binary: {binary.name}")
        for side, root in self.roots.items():
            jurisdictions = {
                child.name
                for child in root.iterdir()
                if child.is_dir() and JURISDICTION_DIR.match(child.name)
            }
            try:
                self._staged[side] = stage_pure_root(
                    root, jurisdictions, self.work_dir / "staged" / side
                )
            except ValueError as exc:
                raise AlignmentError("rulespec_root_not_canonical", f"{side}: {exc}") from exc

    def compile(self, program: ProgramFile, side: str) -> Mapping[str, Any]:
        from axiom_oracles.engine_compat import compile_with_engine

        if side not in self._staged:
            self.prepare()
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
            return json.loads(compiled.read_text())
        except (OSError, ValueError) as exc:
            raise AlignmentError(
                "program_compile_failed", f"artifact of {program.key} ({side}) unreadable: {exc}"
            ) from exc


def _tail(text: str, limit: int = 600) -> str:
    text = " ".join((text or "").split())
    return text[-limit:] if len(text) > limit else text


def program_outputs(program: ProgramFile) -> list[str]:
    """The ``outputs`` a program file declares (its compared outputs)."""
    try:
        doc = yaml.safe_load(program.path.read_text())
    except (OSError, yaml.YAMLError) as exc:
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

    def resolve_root(self, root: str) -> str | None:
        """The derived-rule name for an output or a ``module#name`` concept."""
        if root in self.derived_by_name:
            return root
        short = root.rsplit("#", 1)[-1]
        if short in self.derived_by_name:
            return short
        return None

    def reached_modules(self, roots: Iterable[str]) -> dict[str, set[str]]:
        """``module id -> names`` of rules, parameters and relations reached."""
        reached: dict[str, set[str]] = {}
        names: set[str] = set()
        for root in roots:
            names |= _transitive_dependencies(root, self.derived_by_name)
        for name in names:
            rule = self.derived_by_name[name]
            module = _module_of(str(rule.get("id") or ""))
            if module is None:
                raise AlignmentError(
                    "compiled_program_unattributed",
                    f"{self.program.key} ({self.side}): derived rule {name!r} has no module id",
                )
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
    return CompiledProgram(
        program=program,
        side=side,
        sha256=canonical_json_sha256(body),
        engine_version=(
            str(artifact.get("engine_version")) if artifact.get("engine_version") else None
        ),
        derived_by_name=derived_by_name,
        parameter_ids=parameter_ids,
    )


def compile_programs(
    programs: Mapping[str, Sequence[ProgramFile]],
    compiler: Compiler,
    *,
    jobs: int = 4,
) -> tuple[dict[str, dict[str, CompiledProgram]], dict[str, dict[str, int]]]:
    """Compile every program on every side. Any failure raises.

    Returns ``(compiled[side][key], counts[side])``. A side whose compiled
    count differs from the number of program files found is an error.
    """
    tasks = [(side, program) for side in SIDES for program in programs.get(side, [])]

    def one(task: tuple[str, ProgramFile]) -> CompiledProgram:
        side, program = task
        return index_compiled(program, side, compiler.compile(program, side))

    compiled: dict[str, dict[str, CompiledProgram]] = {side: {} for side in SIDES}
    if tasks:
        with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
            for item in pool.map(one, tasks):
                compiled[item.side][item.program.key] = item
    counts = {}
    for side in SIDES:
        found = len(programs.get(side, []))
        done = len(compiled[side])
        counts[side] = {"program_files_found": found, "programs_compiled": done}
        if found != done:
            raise AlignmentError(
                "program_count_mismatch",
                f"{side}: {found} program files found, {done} compiled",
            )
    return compiled, counts


# ---------------------------------------------------------------------------
# Suite registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Suite:
    name: str
    file: str
    ci: str | None
    runner_type: str
    program_key: str | None
    binding: str
    concepts: tuple[str, ...]
    module_literals: frozenset[str] = field(default_factory=frozenset)

    @property
    def mode(self) -> str:
        """``manual`` for ``ci: manual``; every other suite runs in a CI lane."""
        return MODE_MANUAL if self.ci == "manual" else MODE_RUNNABLE


def _program_key_from_ref(ref: str) -> tuple[str | None, str]:
    """Map an ``axiom_program`` value to a program key.

    ``.../rulespec-us/programs/x.yaml`` names a program of the rulespec tree;
    ``.../axiom-oracles/programs/x.yaml`` or a relative ``programs/x.yaml``
    names one of this repository. Anything else is a program this report does
    not compile (another country's tree).
    """
    text = str(ref).replace("\\", "/")
    if "/programs/" in f"/{text}":
        head, rel = f"/{text}".rsplit("/programs/", 1)
        relpath = f"programs/{rel}"
        owner = head.rstrip("/").rsplit("/", 1)[-1]
        if owner == "rulespec-us":
            return f"{ORIGIN_RULESPEC}:{relpath}", "axiom_program"
        if owner in ("axiom-oracles", ""):
            return f"{ORIGIN_REGISTRY}:{relpath}", "axiom_program"
    return None, "foreign_program"


def module_literals(text: str) -> set[str]:
    return {f"{m.group(1)}:{m.group(2)}" for m in MODULE_LITERAL.finditer(text)}


def load_suites(registry_root: Path) -> list[Suite]:
    """Every runner-backed suite of ``comparisons/*.yaml``.

    Unreadable registry, a file that does not parse, a suite without a name or
    runner type, a duplicate name, or an empty registry all raise
    ``registry_unreadable``.
    """
    directory = Path(registry_root) / "comparisons"
    if not directory.is_dir():
        raise AlignmentError("registry_unreadable", "no comparisons/ directory")
    suites: dict[str, Suite] = {}
    for path in sorted(directory.glob("*.yaml")):
        try:
            text = path.read_text()
            doc = yaml.safe_load(text)
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            raise AlignmentError("registry_unreadable", f"{path.name}: {exc}") from exc
        if not isinstance(doc, Mapping):
            raise AlignmentError("registry_unreadable", f"{path.name}: not a mapping")
        if "runner" not in doc:
            # Multi-suite manifests (parameter oracles, the state income tax
            # population lane) and fixture files are not program-bound suites.
            continue
        runner = doc.get("runner")
        name = doc.get("name")
        if not isinstance(runner, Mapping) or not isinstance(runner.get("type"), str):
            raise AlignmentError("registry_unreadable", f"{path.name}: runner without a type")
        if not isinstance(name, str) or not name:
            raise AlignmentError("registry_unreadable", f"{path.name}: suite without a name")
        if name in suites:
            raise AlignmentError("registry_unreadable", f"duplicate suite name {name!r}")
        ci = doc.get("ci")
        if ci is not None and not isinstance(ci, str):
            raise AlignmentError("registry_unreadable", f"{path.name}: ci is not a string")
        params = runner.get("parameters") or {}
        if not isinstance(params, Mapping):
            raise AlignmentError("registry_unreadable", f"{path.name}: parameters not a mapping")
        program_key: str | None = None
        binding = "unbound"
        if params.get("axiom_program"):
            program_key, binding = _program_key_from_ref(params["axiom_program"])
        elif runner["type"] in JURISDICTION_SNAP_RUNNERS and params.get("jurisdiction"):
            program_key = (
                f"{ORIGIN_RULESPEC}:programs/{params['jurisdiction']}/snap/fy-2026.yaml"
            )
            binding = "jurisdiction_snap_program"
        concepts = params.get("concepts") or []
        if not isinstance(concepts, list) or not all(isinstance(c, str) for c in concepts):
            raise AlignmentError("registry_unreadable", f"{path.name}: concepts not a string list")
        suites[name] = Suite(
            name=name,
            file=f"comparisons/{path.name}",
            ci=ci,
            runner_type=runner["type"],
            program_key=program_key,
            binding=binding,
            concepts=tuple(concepts),
            module_literals=frozenset(module_literals(text)),
        )
    if not suites:
        raise AlignmentError("registry_unreadable", "comparisons/ holds no runner-backed suite")
    return [suites[name] for name in sorted(suites)]


def harness_module_references(
    registry_root: Path, *, skip_files: Iterable[str] = ()
) -> dict[str, list[str]]:
    """``module id -> registry files`` that name it outside ``programs/``.

    Bridges and overlays compile RuleSpec modules without a program file. A
    module named there can be exercised by a suite this report cannot bind to
    a program, so the report must not call a change to it ``no_reference``.
    """
    skip = set(skip_files)
    references: dict[str, set[str]] = {}
    root = Path(registry_root)
    for directory in HARNESS_SCAN_DIRS:
        base = root / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in HARNESS_SCAN_SUFFIXES:
                continue
            rel = path.relative_to(root).as_posix()
            if rel in skip:
                continue
            try:
                text = path.read_text()
            except (OSError, UnicodeDecodeError):
                continue
            for module in module_literals(text):
                references.setdefault(module, set()).add(rel)
    return {module: sorted(files) for module, files in sorted(references.items())}


def importing_modules(roots: Iterable[Path], modules: Iterable[str]) -> set[str]:
    """``modules`` plus every module that names one of them, transitively.

    Read from the module files as text (any module-id literal counts as a
    reference), over every given tree. An over-approximation by design.
    """
    reverse: dict[str, set[str]] = {}
    for root in roots:
        for child in sorted(Path(root).iterdir()) if Path(root).is_dir() else []:
            if not child.is_dir() or not JURISDICTION_DIR.match(child.name):
                continue
            for path in child.rglob("*.yaml"):
                if path.name.endswith(".test.yaml"):
                    continue
                kind, module = classify_path(path.relative_to(root).as_posix())
                if kind != "module" or module is None:
                    continue
                try:
                    text = path.read_text()
                except (OSError, UnicodeDecodeError):
                    continue
                for target in module_literals(text):
                    if target != module:
                        reverse.setdefault(target, set()).add(module)
    seen: set[str] = set()
    stack = list(modules)
    while stack:
        module = stack.pop()
        if module in seen:
            continue
        seen.add(module)
        stack.extend(reverse.get(module, ()))
    return seen


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
                        raise AlignmentError(
                            "suite_concept_not_in_program",
                            f"suite {suite.name} compares {concept!r}, which "
                            f"{program.key} ({side}) does not define",
                        )
                    concept_roots.append(name)
                roots.extend(concept_roots)
                suite_reach.setdefault(suite.name, {})[side] = set(
                    unit.reached_modules(concept_roots)
                )
            reached[side][program.key] = unit.reached_modules(roots)

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
                        key, {"program": key, "sides": [], "via": "compared_outputs", "reached": set()}
                    )
                    hit["sides"].append(side)
                    hit["reached"] |= names
        for key in sorted(hits):
            hit = hits[key]
            if "reached" in hit:
                hit["reached"] = sorted(hit["reached"])
            row["reaching_programs"].append(hit)
        rows.append(row)
    return rows, suite_reach


def expected_suites(
    reach: Sequence[Mapping[str, Any]],
    suites: Sequence[Suite],
    known_programs: set[str],
    suite_concept_reach: Mapping[str, Mapping[str, set[str]]],
    referenced_modules: set[str],
) -> list[dict[str, Any]]:
    """Suites bound to a reaching program, plus unbound suites whose own file
    names a changed module (or a module that imports one)."""
    reaching = {hit["program"] for row in reach for hit in row["reaching_programs"]}
    changed_modules = {row["module"] for row in reach if row["module"]}
    out = []
    for suite in suites:
        entry: dict[str, Any] | None = None
        if suite.program_key and suite.program_key in reaching:
            own = set()
            for modules in suite_concept_reach.get(suite.name, {}).values():
                own |= modules
            program_changed = any(
                hit["program"] == suite.program_key and hit["via"] == "program_file"
                for row in reach
                for hit in row["reaching_programs"]
            )
            entry = {
                "suite": suite.name,
                "binding": suite.binding,
                "program": suite.program_key,
                "compared_concepts_reach_change": bool(own & changed_modules) or program_changed,
            }
        elif suite.program_key is None or suite.program_key not in known_programs:
            named = sorted(suite.module_literals & referenced_modules)
            if named:
                entry = {
                    "suite": suite.name,
                    "binding": "module_reference",
                    "program": None,
                    "referenced_modules": named,
                }
        if entry is not None:
            entry.update(
                {
                    "file": suite.file,
                    "ci": suite.ci,
                    "mode": suite.mode,
                    "runner_type": suite.runner_type,
                }
            )
            out.append(entry)
    return out


# ---------------------------------------------------------------------------
# Suite execution and per-case comparison
# ---------------------------------------------------------------------------


class SuiteExecutor(Protocol):
    def run(self, suite: str, side: str) -> Mapping[str, Any]:
        """Run ``suite`` against one side and return its comparison report."""


class ReportsDirExecutor:
    """Read already-produced reports from ``<dir>/<side>/<suite>.json``."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)

    def run(self, suite: str, side: str) -> Mapping[str, Any]:
        path = self.directory / side / f"{suite}.json"
        try:
            return json.loads(path.read_text())
        except FileNotFoundError as exc:
            raise AlignmentError(
                "suite_run_failed", f"no {side} report for suite {suite}"
            ) from exc
        except (OSError, ValueError) as exc:
            raise AlignmentError(
                "suite_run_failed", f"{side} report for suite {suite} unreadable: {exc}"
            ) from exc


class RunComparisonExecutor:
    """Run ``scripts/run_comparison.py <suite>`` with ``HOME`` set per side.

    Suite files name their checkouts under ``$HOME`` (``$HOME/rulespec-us``),
    so each side gets a home directory that holds that side's ``rulespec-us``
    checkout. Tool repositories and caches of the real home are linked in.
    """

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


def _case_states(report: Mapping[str, Any], suite: str, side: str) -> dict[str, dict[str, Any]]:
    """``case_id -> {state, mismatched}`` after checking the report is a run."""
    label = f"suite {suite} ({side})"
    if not isinstance(report, Mapping):
        raise AlignmentError("suite_run_failed", f"{label}: report is not an object")
    if report.get("suite") not in (None, suite):
        raise AlignmentError(
            "suite_run_failed", f"{label}: report is for suite {report.get('suite')!r}"
        )
    provenance = report.get("provenance") if isinstance(report.get("provenance"), Mapping) else {}
    if provenance.get("reemitted_report"):
        raise AlignmentError(
            "suite_run_failed", f"{label}: the run re-emitted a committed report instead of running"
        )
    cases = report.get("cases")
    if not isinstance(cases, list) or not cases:
        raise AlignmentError("zero_cases", f"{label}: the report has no cases")
    declared = report.get("case_count")
    if isinstance(declared, int) and not isinstance(declared, bool) and declared != len(cases):
        raise AlignmentError(
            "suite_report_truncated",
            f"{label}: case_count is {declared} but {len(cases)} case rows are present",
        )
    states: dict[str, dict[str, Any]] = {}
    for case in cases:
        if not isinstance(case, Mapping) or not isinstance(case.get("case_id"), str):
            raise AlignmentError("suite_run_failed", f"{label}: a case row has no case_id")
        case_id = case["case_id"]
        if case_id in states:
            raise AlignmentError("suite_run_failed", f"{label}: duplicate case_id {case_id!r}")
        mismatches = case.get("mismatches") or []
        matches = case.get("matches") or []
        errored = bool(case.get("left_errors")) or bool(case.get("right_errors"))
        if errored:
            state = "error"
        elif mismatches:
            state = "mismatch"
        elif matches:
            state = "match"
        else:
            raise AlignmentError(
                "suite_run_failed", f"{label}: case {case_id!r} compared nothing"
            )
        states[case_id] = {
            "state": state,
            "mismatched": {
                str(row.get("concept")) for row in mismatches if isinstance(row, Mapping)
            },
        }
    return states


def _rulespec_sha(report: Mapping[str, Any]) -> list[str]:
    provenance = report.get("provenance") if isinstance(report.get("provenance"), Mapping) else {}
    shas = []
    for row in provenance.get("rulespecs") or []:
        if isinstance(row, Mapping) and str(row.get("repo", "")).endswith("/rulespec-us"):
            shas.append(str(row.get("sha")))
    return shas


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
    expected_sha: Mapping[str, str | None] | None = None,
) -> dict[str, Any]:
    """Per-case comparison of a suite's base and candidate reports.

    ``regressed`` when a case that matched on base mismatches or errors on
    candidate, or a compared output that matched now mismatches, and no
    disposition entry selects every new mismatch row of the case.
    """
    expected_sha = expected_sha or {}
    for side, report in (("base", base), ("candidate", candidate)):
        want = expected_sha.get(side)
        if want is None:
            raise AlignmentError(
                "side_commit_unknown", f"no {side} commit to check suite {suite}'s report against"
            )
        got = _rulespec_sha(report) if isinstance(report, Mapping) else []
        if got != [want]:
            raise AlignmentError(
                "suite_report_provenance_mismatch",
                f"suite {suite} ({side}): report ran against rulespec-us {got or 'unrecorded'}, "
                f"expected {want}",
            )
    before = _case_states(base, suite, "base")
    after = _case_states(candidate, suite, "candidate")
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
        counts["matched_before"] += was["state"] == "match"
        counts["matched_after"] += now["state"] == "match"
        if was["state"] != "match" and now["state"] == "match":
            counts["newly_matched"] += 1
        if now["state"] == "error" and was["state"] != "error":
            counts["newly_errored"] += 1
            counts["undispositioned_regressions"] += 1
            regressions.append({"case_id": case_id, "kind": "newly_errored"})
            continue
        if now["state"] != "mismatch":
            continue
        if was["state"] == "match":
            new_concepts = set(now["mismatched"])
            kind = "newly_mismatched"
            counts["newly_mismatched"] += 1
        elif was["state"] == "mismatch":
            new_concepts = set(now["mismatched"]) - set(was["mismatched"])
            if not new_concepts:
                continue
            kind = "newly_mismatched_output"
            counts["newly_mismatched_outputs_in_mismatched_cases"] += 1
        else:
            continue
        if new_concepts and all((case_id, concept) in selected for concept in new_concepts):
            counts["dispositioned"] += 1
            continue
        counts["undispositioned_regressions"] += 1
        regressions.append(
            {"case_id": case_id, "kind": kind, "concepts": sorted(new_concepts)}
        )
    return {
        "suite": suite,
        "status": STATUS_REGRESSED if counts["undispositioned_regressions"] else STATUS_ALIGNED,
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
    harness_hits: Mapping[str, Sequence[str]],
    executions: Sequence[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """The single status of a completed derivation.

    Called only after reach and the expected suite set were computed without
    a failure; a failure never reaches this function. ``executions`` is
    ``None`` when suites were not executed, otherwise one result per runnable
    expected suite.
    """
    runnable = [s["suite"] for s in expected if s["mode"] == MODE_RUNNABLE]
    manual = [s["suite"] for s in expected if s["mode"] != MODE_RUNNABLE]
    if not expected:
        if harness_hits:
            raise AlignmentError(
                "reach_incomplete_harness_reference",
                "no program reaches the change, but the harness names "
                f"{', '.join(sorted(harness_hits))} outside any program file; "
                "the suites that compile it are not bound to a program",
            )
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
    base_sha: str | None = None
    candidate_sha: str | None = None
    include_registry_programs: bool = True
    jobs: int = 4
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
    shas = {
        "base": inputs.base_sha or git_head(inputs.base_root),
        "candidate": inputs.candidate_sha or git_head(inputs.candidate_root),
    }
    provenance["rulespec_commit"] = dict(shas)

    suites = load_suites(registry_root)
    report["suite_registry"] = {
        "suites": len(suites),
        "runnable": sum(s.mode == MODE_RUNNABLE for s in suites),
        "manual": sum(s.mode == MODE_MANUAL for s in suites),
        "program_bound": sum(s.program_key is not None for s in suites),
    }

    changed = changed_files(inputs.base_root, inputs.candidate_root, inputs.changed)
    if not changed:
        raise AlignmentError("no_changed_files", "base and candidate do not differ")
    provenance["changed_files"] = changed

    programs: dict[str, list[ProgramFile]] = {}
    for side, root in (("base", inputs.base_root), ("candidate", inputs.candidate_root)):
        programs[side] = discover_programs(Path(root), ORIGIN_RULESPEC)
        if inputs.include_registry_programs:
            programs[side] += discover_programs(registry_root, ORIGIN_REGISTRY)
    compiled, counts = compile_programs(programs, inputs.compiler, jobs=inputs.jobs)
    report["programs"] = counts
    provenance["compiled_programs"] = {
        side: {key: unit.sha256 for key, unit in sorted(compiled[side].items())} for side in SIDES
    }
    provenance["engine_versions"] = sorted(
        {unit.engine_version for side in SIDES for unit in compiled[side].values() if unit.engine_version}
    )

    reach, suite_reach = compute_reach(changed, programs, compiled, suites)
    report["reach"] = reach

    known_programs = {key for side in SIDES for key in compiled[side]}
    changed_modules = {row["module"] for row in reach if row["module"]}
    referenced = importing_modules([inputs.base_root, inputs.candidate_root], changed_modules)
    expected = expected_suites(reach, suites, known_programs, suite_reach, referenced)
    report["expected_suites"] = expected
    report["suites_with_missing_program"] = sorted(
        s.name
        for s in suites
        if s.program_key
        and s.program_key.startswith(f"{ORIGIN_RULESPEC}:")
        and s.program_key not in known_programs
    )

    harness = harness_module_references(registry_root, skip_files={s.file for s in suites})
    hits = {module: harness[module] for module in sorted(referenced) if module in harness}
    report["harness_references"] = {
        "modules_checked": len(referenced),
        "hits": hits,
    }

    executions: list[dict[str, Any]] | None = None
    runnable = [s["suite"] for s in expected if s["mode"] == MODE_RUNNABLE]
    if inputs.executor is not None and runnable:
        executions = []
        for suite in runnable:
            base = inputs.executor.run(suite, "base")
            candidate = inputs.executor.run(suite, "candidate")
            result = compare_suite_reports(
                suite,
                base,
                candidate,
                _load_dispositions(registry_root, suite),
                expected_sha=shas,
            )
            executions.append(result)
        report["executions"] = executions

    report.update(derive_status(reach, expected, hits, executions))


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

    def git(*args: str, cwd: Path | None = None) -> str:
        result = subprocess.run(
            ["git", *args], text=True, capture_output=True, check=False, cwd=cwd, timeout=900
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
