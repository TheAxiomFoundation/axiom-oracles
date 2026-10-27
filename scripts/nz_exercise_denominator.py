"""Compute the NZ exercise denominator from committed artifacts.

The exercised verdict computes per-view supplied-input variation and exact
requested-output root sets from the committed per-evaluation traces. Two legs
of its denominator remained commit-pinned external attestations:

* the compiled input-slot universe (328 slots, including the never-supplied
  ones) — the suite catalog asserted it, and nothing committed derived it;
* the capture cardinality (883 engine evaluations) — recorded by the harness,
  not cross-derived in-repo.

Both now derive from committed, digest-pinned artifacts:

* the compiled program artifact (committed and byte-verified against the same
  pinned digest the executable verdict enforces) carries the compiler-emitted
  ``metadata.input_catalog``; this module requires a BIJECTION between those
  slots and the suite's ``exercise_input_catalog``, and that both match the
  recorded ``input_slots`` denominator;
* the committed evaluation traces must contain exactly the recorded number of
  evaluations, and their compiled-program and engine pins must name the same
  committed artifact and pinned engine.

Soundness note recorded in the verdict: the committed traces are a LOWER
bound on exercise — an unrecorded engine call could only add variation or
roots, never subtract observed ones — so once the denominator derives from
the committed artifact rather than the capture, capture completeness stops
being load-bearing for the exercised verdict.

``validate()`` raises :class:`DenominatorError` on any drift; ``certify.py``
flips the exercised sub-verdicts to computed only when it passes.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))


def _executable_module():
    spec = importlib.util.spec_from_file_location(
        "_nz_executable_reproduction_pins",
        REPO_ROOT / "scripts" / "nz_executable_reproduction.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_EXECUTABLE = _executable_module()
ARTIFACT_PATH = _EXECUTABLE.ARTIFACT_PATH
COMPILED_SHA256 = _EXECUTABLE.COMPILED_SHA256
ENGINE_GIT_SHA = _EXECUTABLE.ENGINE_GIT_SHA
ENGINE_BINARY_SHA256 = _EXECUTABLE.ENGINE_BINARY_SHA256
SOURCE_REPORT_PATH = _EXECUTABLE.SOURCE_REPORT_PATH
TRACES_PATH = (
    REPO_ROOT / "comparisons" / "nz-treasury-incomeexplorer" / "evaluation-traces.json"
)


class DenominatorError(ValueError):
    """The exercise denominator does not derive from committed artifacts."""


def _load(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DenominatorError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise DenominatorError(f"{label} must contain an object")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DenominatorError(message)


def validate(*, repo_root: Path = REPO_ROOT) -> dict:
    """Cross-derive the exercise denominator; raise DenominatorError on drift."""

    _require(
        Path(repo_root).resolve() == REPO_ROOT.resolve(),
        "NZ exercise denominator must validate at the repository root",
    )
    _require(
        _EXECUTABLE._sha256(ARTIFACT_PATH) == COMPILED_SHA256,
        "committed compiled artifact bytes drifted from the pinned digest",
    )
    artifact = _load(ARTIFACT_PATH, "compiled program artifact")
    compiler_catalog = (artifact.get("metadata") or {}).get("input_catalog")
    _require(
        isinstance(compiler_catalog, list) and compiler_catalog,
        "compiled artifact has no compiler-emitted input catalog",
    )
    compiler_slots: set[str] = set()
    for row in compiler_catalog:
        slot = row.get("slot") if isinstance(row, dict) else None
        _require(
            isinstance(slot, str) and bool(slot),
            "compiler input catalog contains an invalid slot entry",
        )
        _require(slot not in compiler_slots, f"compiler input catalog repeats slot {slot}")
        compiler_slots.add(slot)

    report = _load(SOURCE_REPORT_PATH, "source comparison")
    suite_catalog = report.get("exercise_input_catalog")
    _require(
        isinstance(suite_catalog, dict) and bool(suite_catalog),
        "source comparison has no exercise_input_catalog",
    )
    missing = sorted(compiler_slots - set(suite_catalog))
    extra = sorted(set(suite_catalog) - compiler_slots)
    _require(
        not missing and not extra,
        "suite exercise catalog is not bijective with the compiler-emitted "
        f"input catalog (missing from suite: {missing[:3]}; "
        f"unknown to compiler: {extra[:3]})",
    )
    compiled = report.get("compiled_program") or {}
    _require(
        compiled.get("artifact_sha256") == COMPILED_SHA256,
        "source comparison names a different compiled artifact",
    )
    input_slots = compiled.get("input_slots")
    _require(
        input_slots == len(compiler_slots),
        f"recorded input_slots denominator ({input_slots}) does not equal the "
        f"compiler-emitted universe ({len(compiler_slots)})",
    )
    state_counts = Counter(
        row.get("state") for row in suite_catalog.values() if isinstance(row, dict)
    )
    supplied = state_counts.get("varied", 0) + state_counts.get("constant", 0)
    not_supplied = state_counts.get("not_supplied", 0)
    _require(
        supplied + not_supplied == len(suite_catalog),
        "suite exercise catalog contains rows with unknown supply states",
    )

    traces = _load(TRACES_PATH, "evaluation traces")
    evaluations = traces.get("evaluations")
    _require(
        isinstance(evaluations, list) and bool(evaluations),
        "evaluation traces contain no evaluations",
    )
    _require(
        traces.get("evaluation_count") == len(evaluations),
        "evaluation trace count field is not derived from its rows",
    )
    _require(
        compiled.get("engine_evaluations") == len(evaluations),
        f"recorded capture cardinality ({compiled.get('engine_evaluations')}) does "
        f"not equal the committed trace count ({len(evaluations)})",
    )
    traces_compiled = traces.get("compiled_program") or {}
    _require(
        traces_compiled.get("artifact_sha256") == COMPILED_SHA256,
        "evaluation traces name a different compiled artifact",
    )
    _require(
        traces_compiled.get("input_slots") == len(compiler_slots),
        "evaluation traces record a different input-slot denominator",
    )
    traces_engine = traces.get("engine") or {}
    _require(
        traces_engine.get("git_sha") == ENGINE_GIT_SHA
        and traces_engine.get("binary_sha256") == ENGINE_BINARY_SHA256,
        "evaluation traces name a different engine than the pinned one",
    )

    return {
        "input_count": len(compiler_slots),
        "supplied_input_count": supplied,
        "not_supplied_count": not_supplied,
        "evaluation_count": len(evaluations),
        "artifact_sha256": COMPILED_SHA256,
        "universe_source": "compiled-artifact metadata.input_catalog (byte-verified)",
        "lower_bound_soundness": (
            "committed traces can only understate exercise; the denominator "
            "derives from the committed artifact, so capture completeness is "
            "not load-bearing"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.parse_args(argv)
    try:
        summary = validate()
    except DenominatorError as exc:
        print(f"NZ exercise denominator ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        "NZ exercise denominator OK: "
        f"{summary['input_count']} slots from the committed artifact "
        f"({summary['supplied_input_count']} supplied, "
        f"{summary['not_supplied_count']} never supplied), "
        f"{summary['evaluation_count']} committed evaluation traces"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
