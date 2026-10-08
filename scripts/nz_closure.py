#!/usr/bin/env python3
"""Compute NZ RuleSpec closure against the pinned corpus release by citation path."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
from nz_programs import PROGRAM_VIEWS  # noqa: E402

OUT_DIR = REPO_ROOT / "closure" / "nz"
SOURCE_PATH = OUT_DIR / "source.json"
SUMMARY_PATH = OUT_DIR / "summary.json"
REQUEST_TRACE_PATH = (
    REPO_ROOT
    / "conformance"
    / "executable"
    / "nz-treasury-incomeexplorer"
    / "requests.json"
)
EVALUATION_TRACE_PATH = (
    REPO_ROOT / "comparisons" / "nz-treasury-incomeexplorer" / "evaluation-traces.json"
)
RATCHET_PATH = OUT_DIR / "denominator-ratchet.json"
SOURCE_SHA256 = "a69b872fbc9fd9a98132ea5b7f5272d8be9631d3060651603b2b3c1f7cd64aea"
EVALUATION_TRACE_SHA256 = (
    "43cca386b15e71fc07fa8fb223b2bef8d351e0bb56ecfdf05fe98e790e66f4da"
)
RULESPEC_REPO = Path("/Users/maxghenis/TheAxiomFoundation/rulespec-nz")
CORPUS_REPO = Path("/Users/maxghenis/TheAxiomFoundation/axiom-corpus")
RULESPEC_SHA = "89a7d25dc03a4d045348620283332de10b1047da"
CORPUS_RELEASE_REF = "origin/release/nz-rulespec-2026-07-18"
CORPUS_RELEASE_SHA = "3f7b5d985bce759cb487f1b7fd050f5cbf007d17"
ROOTS = ("nz/statutes", "nz/regulations", "nz/policies")
CORPUS_FILES = (
    "data/corpus/provisions/nz/statute/2026-06-16-rulespec-nz-pco.jsonl",
    "data/corpus/provisions/nz/regulation/2026-06-16-rulespec-nz-pco.jsonl",
    "data/corpus/provisions/nz/district-plan/2026-07-18-wellington-district-plan.jsonl",
)
LEDGER_REPO_PATH = "known-missing-money-atoms.yaml"
RATCHET_REPO_PATH = RATCHET_PATH.relative_to(REPO_ROOT).as_posix()

TRACE_SCHEMA = "axiom_oracles.nz_evaluation_traces.v1"
TRACE_SUITE = "nz-treasury-incomeexplorer"
TRACE_EVALUATION_COUNT = 883
TRACE_ENGINE = {
    "binary_sha256": "56fbffea1e0e32c52b6fcbddbca76223bb185b33b49368c288e0c7213b0126e1",
    "git_sha": "d59969b53430ae2fd97eb4349d44ad23ce930d85",
}
TRACE_COMPILED_PROGRAM = {
    "artifact_sha256": "b1d72c1f4840a1774aefbddc9692e22a79ced26cde6c44efb4c01fc394a15c33",
    "derived_outputs": 176,
    "engine_evaluations": TRACE_EVALUATION_COUNT,
    "input_slots": 328,
    "parameters": 129,
    "relations": 0,
}
TRACE_CAPTURE = {
    "lineage_mode": "attested",
    "source_comparison": {
        "artifact": "comparisons/nz-treasury-incomeexplorer/source-comparison.json",
        "regenerated_sha256": (
            "7b58fcfdb50f8627f0228bf024d95cde3ef3d50caae7f2d9de2862d82ea6e8c6"
        ),
        "regeneration_difference": "provenance only",
        "sha256": "abd3bcbebc01c73e58c27496db5897a306bb0496ae1d53e5abbd5ae487010b3b",
        "substance_sha256": (
            "a52a16d81433c91bc73e107fdaa5cdbc701d908f5c359615fd317cb82e6b8a15"
        ),
    },
    "source_harness": {
        "path": "nz-lane/emtr_reproduction/run.py",
        "repository": "TheAxiomFoundation/ops",
        "repository_commit": "bcf631b59968be4907e679b4704f5e029e2188ab",
        "repository_commit_status": "pinned",
        "sha256": "9aa0fc64af8dca4a8f7574e98923fe0022561679027c2ed5325bf381e9c6ab27",
    },
}

REQUEST_EVIDENCE_PROVENANCE = {
    "compiled_sha256": TRACE_COMPILED_PROGRAM["artifact_sha256"],
    "engine_binary_sha256": TRACE_ENGINE["binary_sha256"],
    "engine_git_sha": TRACE_ENGINE["git_sha"],
    "harness": "TheAxiomFoundation/ops/nz-lane/emtr_reproduction/run.py",
    "harness_commit": "bcf631b5",
    "rulespec_commit": RULESPEC_SHA,
}


class ClosureError(ValueError):
    pass


def _git(repo: Path, *args: str) -> str:
    process = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if process.returncode:
        raise ClosureError(process.stderr.strip() or process.stdout.strip())
    return process.stdout


def _citations(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "corpus_citation_path" and isinstance(child, str):
                found.add(child)
            found.update(_citations(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_citations(child))
    return found


def _formula_texts(value: object) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "formula" and isinstance(child, str):
                found.append(child)
            else:
                found.extend(_formula_texts(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_formula_texts(child))
    return found


def _list_sha256(values: list[str]) -> str:
    raw = json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _node_id(path: str, name: str) -> str:
    module = path.removeprefix("nz/").removesuffix(".yaml")
    return f"nz:{module}#{name}"


def load_source() -> dict:
    """Load the versioned denominator only when its review pin still matches."""

    try:
        raw = SOURCE_PATH.read_bytes()
        if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
            raise ClosureError(
                "NZ closure source bytes changed; review and re-pin the denominator"
            )
        source = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ClosureError(f"cannot read the NZ closure source: {exc}") from exc
    if not isinstance(source, dict):
        raise ClosureError("NZ closure source must contain an object")
    return source


def _load_json_object(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ClosureError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ClosureError(f"{label} must contain an object")
    return value


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _derive_requested_output_roots(
    trace: dict,
) -> tuple[dict[str, list[str]], dict[str, set[tuple[str, tuple[str, ...]]]]]:
    """Derive ownership exclusively from each execution-emitted trace row.

    ``PROGRAM_VIEWS`` deliberately does not participate here. It is the
    declaration side of the later bijection, not an ownership oracle for the
    execution evidence.
    """

    expected_keys = {
        "_comment",
        "capture",
        "compiled_program",
        "engine",
        "evaluation_count",
        "evaluations",
        "period",
        "rulespec_commit",
        "schema",
        "suite",
    }
    if set(trace) != expected_keys:
        raise ClosureError("NZ evaluation trace top-level shape drifted")
    if trace.get("schema") != TRACE_SCHEMA or trace.get("suite") != TRACE_SUITE:
        raise ClosureError("unexpected NZ evaluation trace schema or suite")
    if (
        trace.get("capture") != TRACE_CAPTURE
        or trace.get("compiled_program") != TRACE_COMPILED_PROGRAM
        or trace.get("engine") != TRACE_ENGINE
        or trace.get("rulespec_commit") != RULESPEC_SHA
        or trace.get("period") != {"start": "2026-04-01", "end": "2027-03-31"}
    ):
        raise ClosureError("NZ evaluation trace provenance drifted")
    evaluations = trace.get("evaluations")
    if (
        not isinstance(evaluations, list)
        or isinstance(trace.get("evaluation_count"), bool)
        or trace.get("evaluation_count") != len(evaluations)
        or len(evaluations) != TRACE_EVALUATION_COUNT
    ):
        raise ClosureError("NZ evaluation trace must contain 883 evaluations")

    derived: dict[str, set[str]] = {}
    canonical_requests: dict[str, set[tuple[str, tuple[str, ...]]]] = {}
    for index, evaluation in enumerate(evaluations, start=1):
        location = f"NZ evaluation trace row {index - 1}"
        if not isinstance(evaluation, dict) or set(evaluation) != {
            "evaluation_id",
            "request",
            "requested_output_roots",
            "response",
            "view",
        }:
            raise ClosureError(f"{location} has invalid canonical shape")
        if evaluation.get("evaluation_id") != f"nz-ie-eval-{index:04d}":
            raise ClosureError(f"{location} has a missing, duplicate, or reordered id")
        view = evaluation.get("view")
        if not isinstance(view, str) or not view:
            raise ClosureError(f"{location} has an invalid emitted view")
        request = evaluation.get("request")
        if (
            not isinstance(request, dict)
            or set(request) != {"dataset", "mode", "queries"}
            or request.get("mode") != "explain"
        ):
            raise ClosureError(f"{location} has an invalid explain request")
        dataset = request.get("dataset")
        if (
            not isinstance(dataset, dict)
            or set(dataset) != {"inputs", "relations"}
            or not isinstance(dataset.get("inputs"), list)
            or not dataset["inputs"]
            or dataset.get("relations") != []
        ):
            raise ClosureError(f"{location} has an invalid request dataset")
        queries = request.get("queries")
        if not isinstance(queries, list) or len(queries) != 1:
            raise ClosureError(f"{location} must contain exactly one query")
        query = queries[0]
        if not isinstance(query, dict) or set(query) != {
            "entity_id",
            "outputs",
            "period",
        }:
            raise ClosureError(f"{location} query has invalid canonical shape")
        outputs = query.get("outputs")
        if (
            not isinstance(outputs, list)
            or not outputs
            or outputs != list(dict.fromkeys(outputs))
            or not all(isinstance(output, str) and output for output in outputs)
        ):
            raise ClosureError(f"{location} has invalid requested outputs")
        if evaluation.get("requested_output_roots") != outputs:
            raise ClosureError(
                f"{location} requested_output_roots differ from request outputs"
            )
        expected_period = {
            "period_kind": "tax_year",
            "start": trace["period"]["start"],
            "end": trace["period"]["end"],
        }
        entity_id = query.get("entity_id")
        if (
            not isinstance(entity_id, str)
            or not entity_id
            or query.get("period") != expected_period
        ):
            raise ClosureError(f"{location} query entity or period drifted")
        response = evaluation.get("response")
        if (
            not isinstance(response, dict)
            or set(response) != {"entity_id", "metadata", "outputs", "period"}
            or response.get("entity_id") != entity_id
            or response.get("period") != expected_period
            or response.get("metadata")
            != {"actual_mode": "explain", "requested_mode": "explain"}
        ):
            raise ClosureError(f"{location} response envelope drifted")
        returned = response.get("outputs")
        if not isinstance(returned, dict) or set(returned) != set(outputs):
            raise ClosureError(
                f"{location} response outputs do not biject request outputs"
            )
        if any(
            not isinstance(returned[root], dict) or returned[root].get("id") != root
            for root in outputs
        ):
            raise ClosureError(f"{location} response output identity drifted")

        roots = tuple(outputs)
        derived.setdefault(view, set()).update(roots)
        canonical_requests.setdefault(_canonical_json(request), set()).add(
            (view, roots)
        )

    return (
        {view: sorted(roots) for view, roots in sorted(derived.items())},
        canonical_requests,
    )


def _validate_request_evidence_binding(
    evidence: dict,
    *,
    trace_roots: dict[str, list[str]],
    canonical_trace_requests: dict[str, set[tuple[str, tuple[str, ...]]]],
) -> None:
    """Bind the committed executable request subset to actual trace calls."""

    if evidence.get("schema") != "axiom_oracles.nz_executable_requests.v1":
        raise ClosureError("unexpected NZ executable request evidence schema")
    if evidence.get("provenance") != REQUEST_EVIDENCE_PROVENANCE:
        raise ClosureError("NZ executable request evidence provenance drifted")
    rows = evidence.get("requests")
    if not isinstance(rows, list) or not rows:
        raise ClosureError("NZ executable request evidence has no requests")
    seen_ids: set[str] = set()
    roots_from_matched_trace: dict[str, set[str]] = {}
    for index, row in enumerate(rows):
        location = f"NZ executable request evidence row {index}"
        if not isinstance(row, dict):
            raise ClosureError(f"{location} is invalid")
        request_id = row.get("id")
        if not isinstance(request_id, str) or not request_id or request_id in seen_ids:
            raise ClosureError(f"{location} has a missing or duplicate id")
        seen_ids.add(request_id)
        declared_program = row.get("program")
        if not isinstance(declared_program, str) or not declared_program:
            raise ClosureError(f"{location} has an invalid declared program")
        request = row.get("request")
        if not isinstance(request, dict):
            raise ClosureError(f"{location} has no canonical request")
        matches = canonical_trace_requests.get(_canonical_json(request))
        if not matches:
            raise ClosureError(
                f"{location} request/root is absent from the committed evaluation trace"
            )
        if len(matches) != 1:
            raise ClosureError(
                f"{location} has ambiguous ownership in the evaluation trace"
            )
        # Ownership comes from the matched trace evaluation. The evidence row's
        # program label is intentionally not used to normalize this side.
        view, requested_roots = next(iter(matches))
        if declared_program != view:
            raise ClosureError(
                f"{location} declared program differs from trace-emitted ownership"
            )
        roots_from_matched_trace.setdefault(view, set()).update(requested_roots)
    matched = {
        view: sorted(roots) for view, roots in sorted(roots_from_matched_trace.items())
    }
    if matched != trace_roots:
        raise ClosureError(
            "NZ executable request evidence does not cover the trace-derived root set"
        )
    if evidence.get("requested_outputs_by_program") != trace_roots:
        raise ClosureError(
            "NZ executable request evidence summary differs from trace-derived roots"
        )


def load_requested_output_roots(
    *,
    trace: dict | None = None,
    request_evidence: dict | None = None,
) -> dict[str, list[str]]:
    """Derive per-program roots from #476's committed execution trace."""

    if trace is None:
        if hashlib.sha256(EVALUATION_TRACE_PATH.read_bytes()).hexdigest() != (
            EVALUATION_TRACE_SHA256
        ):
            raise ClosureError(
                "NZ evaluation trace bytes changed; review and re-pin the execution evidence"
            )
        trace = _load_json_object(EVALUATION_TRACE_PATH, "NZ evaluation trace")
    if request_evidence is None:
        request_evidence = _load_json_object(
            REQUEST_TRACE_PATH, "NZ executable request evidence"
        )
    roots, canonical_requests = _derive_requested_output_roots(trace)
    _validate_request_evidence_binding(
        request_evidence,
        trace_roots=roots,
        canonical_trace_requests=canonical_requests,
    )
    return roots


def _validate_ratchet_programs(
    programs: object,
    *,
    label: str,
    require_current_program_set: bool,
) -> dict[str, dict[str, int]]:
    if not isinstance(programs, dict):
        raise ClosureError(f"{label} programs must contain an object")
    if require_current_program_set and set(programs) != set(PROGRAM_VIEWS):
        raise ClosureError("NZ closure denominator ratchet program set drifted")
    for program, row in programs.items():
        if not isinstance(program, str) or not isinstance(row, dict):
            raise ClosureError(f"{label} row {program!r} is invalid")
        for field in ("requested_output_count_min", "citation_count_min"):
            value = row.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ClosureError(f"{program}: {field} must be a non-negative integer")
    return programs


def _ratchet_from_document(
    document: dict,
    *,
    label: str,
    require_current_program_set: bool,
) -> dict[str, dict[str, int]]:
    if document.get("schema") != "axiom_oracles.nz_closure_denominator_ratchet.v1":
        raise ClosureError(f"unexpected {label} schema")
    return _validate_ratchet_programs(
        document.get("programs"),
        label=label,
        require_current_program_set=require_current_program_set,
    )


def _history_note(message: str) -> None:
    print(
        f"NZ closure NOTE: {message}; ancestor floor check failed open", file=sys.stderr
    )


def _git_history(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _ratchet_at_revision(
    revision: str,
    *,
    label: str,
    unavailable_is_note: bool,
) -> dict[str, dict[str, int]] | None:
    shown = _git_history("show", f"{revision}:{RATCHET_REPO_PATH}")
    if shown.returncode:
        if unavailable_is_note:
            _history_note(f"{label} has no readable {RATCHET_REPO_PATH}")
        return None
    try:
        document = json.loads(shown.stdout)
    except json.JSONDecodeError as exc:
        raise ClosureError(
            f"{label} denominator ratchet is invalid JSON: {exc}"
        ) from exc
    if not isinstance(document, dict):
        raise ClosureError(f"{label} denominator ratchet must contain an object")
    return _ratchet_from_document(
        document,
        label=f"{label} denominator ratchet",
        require_current_program_set=False,
    )


def _load_ancestor_denominator_ratchets() -> dict[str, dict[str, dict[str, int]]]:
    """Load merge-base and feature-history floors without requiring network access."""

    ancestors: dict[str, dict[str, dict[str, int]]] = {}

    # HEAD protects an uncommitted/staged lowering. The strict ancestor below
    # independently protects a lowering once that mutation itself is committed.
    head_ratchet = _ratchet_at_revision("HEAD", label="HEAD", unavailable_is_note=True)
    if head_ratchet is not None:
        ancestors["HEAD"] = head_ratchet

    # Walk every reachable version of the path, not only the direct parents.
    # GitHub Actions checks pull requests out at a synthetic merge commit. If
    # the PR tip itself lowers a floor, both that merge and its PR-tip parent
    # contain the lowered bytes while the older, higher floor sits one commit
    # farther back. A direct-parent-only check therefore accepts the lowering.
    # ``--full-history`` keeps both sides of merges; comparing every readable
    # version makes the effective floor the strictest value reachable from
    # HEAD, including the feature branch's pre-merge history.
    strict_history = _git_history(
        "rev-list", "--full-history", "HEAD", "--", RATCHET_REPO_PATH
    )
    if strict_history.returncode:
        _history_note(
            strict_history.stderr.strip()
            or f"reachable history for {RATCHET_REPO_PATH} is unavailable"
        )
    else:
        strict_found = False
        for revision in strict_history.stdout.splitlines():
            strict_ratchet = _ratchet_at_revision(
                revision,
                label=f"reachable HEAD history {revision}",
                unavailable_is_note=False,
            )
            if strict_ratchet is None:
                continue
            strict_found = True
            ancestors[f"reachable HEAD history {revision}"] = strict_ratchet
        if not strict_found:
            _history_note(
                f"reachable HEAD history containing {RATCHET_REPO_PATH} is unavailable"
            )

    merge_base = _git_history("merge-base", "HEAD", "origin/main")
    merge_base_revision = (
        merge_base.stdout.strip() if merge_base.returncode == 0 else ""
    )
    if not merge_base_revision:
        detail = (
            merge_base.stderr.strip() or "origin/main or its merge-base is unavailable"
        )
        _history_note(detail)
    else:
        merge_base_ratchet = _ratchet_at_revision(
            merge_base_revision,
            label=f"origin/main merge-base {merge_base_revision}",
            unavailable_is_note=True,
        )
        if merge_base_ratchet is not None:
            ancestors[f"origin/main merge-base {merge_base_revision}"] = (
                merge_base_ratchet
            )
    return ancestors


def _validate_ancestor_monotonicity(
    current: dict[str, dict[str, int]],
    *,
    ancestors: dict[str, dict[str, dict[str, int]]] | None = None,
) -> None:
    if ancestors is None:
        ancestors = _load_ancestor_denominator_ratchets()
    for label, ancestor in ancestors.items():
        ancestor = _validate_ratchet_programs(
            ancestor,
            label=label,
            require_current_program_set=False,
        )
        for program, old_row in ancestor.items():
            current_row = current.get(program)
            if current_row is None:
                raise ClosureError(
                    f"{program}: ancestor-monotone denominator RATCHET dropped the "
                    f"program present at {label}"
                )
            for field in ("requested_output_count_min", "citation_count_min"):
                old = old_row[field]
                new = current_row[field]
                if new < old:
                    raise ClosureError(
                        f"{program}: ancestor-monotone denominator RATCHET lowered "
                        f"{field} from {old} at {label} to {new}"
                    )


def load_denominator_ratchet(
    *,
    ancestor_ratchets: dict[str, dict[str, dict[str, int]]] | None = None,
) -> dict[str, dict[str, int]]:
    ratchet = _load_json_object(RATCHET_PATH, "NZ closure denominator ratchet")
    programs = _ratchet_from_document(
        ratchet,
        label="NZ closure denominator ratchet",
        require_current_program_set=True,
    )
    _validate_ancestor_monotonicity(programs, ancestors=ancestor_ratchets)
    return programs


def bootstrap_source() -> dict:
    if _git(RULESPEC_REPO, "rev-parse", RULESPEC_SHA).strip() != RULESPEC_SHA:
        raise ClosureError("pinned RuleSpec commit is unavailable")
    if _git(CORPUS_REPO, "rev-parse", CORPUS_RELEASE_REF).strip() != CORPUS_RELEASE_SHA:
        raise ClosureError("pinned corpus release ref moved or is unavailable")
    parsed_files: list[tuple[str, object]] = []
    rule_names: set[str] = set()
    for path in _git(
        RULESPEC_REPO,
        "ls-tree",
        "-r",
        "--name-only",
        RULESPEC_SHA,
        "--",
        *ROOTS,
    ).splitlines():
        raw = _git(RULESPEC_REPO, "show", f"{RULESPEC_SHA}:{path}")
        try:
            document = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise ClosureError(f"{path}: invalid YAML at pinned commit: {exc}") from exc
        parsed_files.append((path, document))
        rules = document.get("rules") or [] if isinstance(document, dict) else []
        for rule in rules:
            if not isinstance(rule, dict) or not isinstance(rule.get("name"), str):
                raise ClosureError(f"{path}: rule without a string name")
            name = rule["name"]
            if name in rule_names:
                raise ClosureError(f"duplicate RuleSpec rule name {name!r}")
            rule_names.add(name)
    files: list[dict] = []
    for path, document in parsed_files:
        nodes = []
        rules = document.get("rules") or [] if isinstance(document, dict) else []
        for rule in rules:
            name = rule["name"]
            citations = sorted(_citations(rule))
            tokens = {
                token
                for formula in _formula_texts(rule)
                for token in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", formula)
            }
            dependencies = sorted((tokens & rule_names) - {name})
            nodes.append(
                {
                    "id": _node_id(path, name),
                    "name": name,
                    "citations": citations,
                    "citations_sha256": _list_sha256(citations),
                    "dependencies": dependencies,
                    "dependencies_sha256": _list_sha256(dependencies),
                }
            )
        files.append(
            {
                "path": path,
                "citations": sorted(_citations(document)),
                "nodes": nodes,
            }
        )
    corpus_paths: set[str] = set()
    for path in CORPUS_FILES:
        for line_number, line in enumerate(
            _git(CORPUS_REPO, "show", f"{CORPUS_RELEASE_REF}:{path}").splitlines(), 1
        ):
            try:
                row = json.loads(line)
                citation = row["citation_path"]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise ClosureError(
                    f"{path}:{line_number}: invalid provision row"
                ) from exc
            if citation in corpus_paths:
                raise ClosureError(f"duplicate corpus citation path {citation!r}")
            corpus_paths.add(citation)
    ledger_raw = _git(RULESPEC_REPO, "show", f"{RULESPEC_SHA}:{LEDGER_REPO_PATH}")
    ledger = yaml.safe_load(ledger_raw)
    return {
        "schema": "axiom_oracles.nz_closure_source.v2",
        "rulespec": {
            "repository": "TheAxiomFoundation/rulespec-nz",
            "commit": RULESPEC_SHA,
            "roots": list(ROOTS),
            "files": files,
        },
        "program_roots": {
            program: sorted(spec["roots"])
            for program, spec in sorted(PROGRAM_VIEWS.items())
        },
        "corpus": {
            "repository": "TheAxiomFoundation/axiom-corpus",
            "release": "nz-rulespec-2026-07-18",
            "commit": CORPUS_RELEASE_SHA,
            "provision_sources": list(CORPUS_FILES),
            "citation_paths": sorted(corpus_paths),
        },
        "pending_ledger": {
            "source": f"TheAxiomFoundation/rulespec-nz/{LEDGER_REPO_PATH}",
            "sha256": hashlib.sha256(ledger_raw.encode()).hexdigest(),
            "document": ledger,
        },
    }


def build(
    source: dict,
    *,
    requested_output_roots: dict[str, list[str]] | None = None,
    denominator_ratchet: dict[str, dict[str, int]] | None = None,
    ancestor_denominator_ratchets: dict[str, dict[str, dict[str, int]]] | None = None,
) -> dict:
    if source.get("schema") != "axiom_oracles.nz_closure_source.v2":
        raise ClosureError("unexpected NZ closure source schema")
    rulespec = source.get("rulespec") or {}
    corpus = source.get("corpus") or {}
    ledger = source.get("pending_ledger") or {}
    if (
        rulespec.get("commit") != RULESPEC_SHA
        or tuple(rulespec.get("roots") or ()) != ROOTS
    ):
        raise ClosureError("NZ closure RuleSpec pin or declared roots drifted")
    if (
        corpus.get("release") != "nz-rulespec-2026-07-18"
        or corpus.get("commit") != CORPUS_RELEASE_SHA
    ):
        raise ClosureError("NZ closure corpus release pin drifted")
    if (ledger.get("document") or {}).get("total_allowed") != 0:
        raise ClosureError("known-missing-money-atoms ceiling rose above zero")
    corpus_paths = corpus.get("citation_paths") or []
    if corpus_paths != sorted(set(corpus_paths)):
        raise ClosureError("corpus citation paths must be unique and sorted")
    corpus_set = set(corpus_paths)
    files = rulespec.get("files") or []
    paths = [row.get("path") for row in files if isinstance(row, dict)]
    if paths != sorted(set(paths)):
        raise ClosureError("RuleSpec file inventory must be unique and sorted")
    expected_program_roots = {
        program: sorted(spec["roots"])
        for program, spec in sorted(PROGRAM_VIEWS.items())
    }
    if requested_output_roots is None:
        requested_output_roots = load_requested_output_roots()
    if denominator_ratchet is None:
        denominator_ratchet = load_denominator_ratchet(
            ancestor_ratchets=ancestor_denominator_ratchets
        )
    else:
        denominator_ratchet = _validate_ratchet_programs(
            denominator_ratchet,
            label="NZ closure denominator ratchet",
            require_current_program_set=True,
        )
        _validate_ancestor_monotonicity(
            denominator_ratchet,
            ancestors=ancestor_denominator_ratchets,
        )
    if set(requested_output_roots) != set(expected_program_roots):
        raise ClosureError("NZ requested-output trace program set drifted")
    if source.get("program_roots") != requested_output_roots:
        raise ClosureError(
            "NZ program root sets are not bijective with the independent "
            "requested-output trace"
        )
    if expected_program_roots != requested_output_roots:
        raise ClosureError(
            "NZ ratified node views are not bijective with the independent "
            "requested-output trace"
        )
    for program, roots in requested_output_roots.items():
        floor = denominator_ratchet[program]["requested_output_count_min"]
        if len(roots) < floor:
            raise ClosureError(
                f"{program}: requested-output denominator RATCHET regressed "
                f"from floor {floor} to {len(roots)}"
            )
    nodes_by_id: dict[str, dict] = {}
    nodes_by_name: dict[str, dict] = {}
    for row in files:
        file_citations = row.get("citations")
        if not isinstance(file_citations, list) or file_citations != sorted(
            set(file_citations)
        ):
            raise ClosureError(
                f"{row.get('path')}: citations must be unique and sorted"
            )
        for node in row.get("nodes") or []:
            if not isinstance(node, dict):
                raise ClosureError(f"{row.get('path')}: invalid node entry")
            node_id = node.get("id")
            name = node.get("name")
            if not isinstance(node_id, str) or not isinstance(name, str):
                raise ClosureError(f"{row.get('path')}: node lacks id or name")
            if node_id != _node_id(row["path"], name):
                raise ClosureError(
                    f"{node_id}: node id does not match its RuleSpec path"
                )
            if node_id in nodes_by_id or name in nodes_by_name:
                raise ClosureError(f"duplicate RuleSpec node {node_id!r}")
            citations = node.get("citations")
            dependencies = node.get("dependencies")
            if not isinstance(citations, list) or citations != sorted(set(citations)):
                raise ClosureError(f"{node_id}: citations must be unique and sorted")
            if node.get("citations_sha256") != _list_sha256(citations):
                raise ClosureError(f"{node_id}: cited path was dropped or changed")
            if not set(citations).issubset(file_citations):
                raise ClosureError(
                    f"{node_id}: node citation missing from its file census"
                )
            if not isinstance(dependencies, list) or dependencies != sorted(
                set(dependencies)
            ):
                raise ClosureError(f"{node_id}: dependencies must be unique and sorted")
            if node.get("dependencies_sha256") != _list_sha256(dependencies):
                raise ClosureError(f"{node_id}: dependency edge was dropped or changed")
            nodes_by_id[node_id] = node
            nodes_by_name[name] = node
    for node_id, node in nodes_by_id.items():
        missing_dependencies = set(node["dependencies"]) - set(nodes_by_name)
        if missing_dependencies:
            raise ClosureError(
                f"{node_id}: missing dependency node(s) {sorted(missing_dependencies)}"
            )
    summaries = []
    all_pending: set[str] = set()
    for root in ROOTS:
        root_files = [
            row for row in files if str(row.get("path", "")).startswith(root + "/")
        ]
        classifications = []
        for row in root_files:
            citations = row.get("citations")
            missing = sorted(set(citations) - corpus_set)
            all_pending.update(missing)
            if missing:
                status, reason = "pending", "citation_absent_from_pinned_corpus_release"
            elif citations:
                status, reason = "encoded", "all_citations_resolve_by_exact_path"
            else:
                status, reason = (
                    "excluded",
                    "storage_or_test_file_without_corpus_citation",
                )
            classifications.append(
                {
                    "path": row["path"],
                    "status": status,
                    "reason": reason,
                    "citations": citations,
                    "missing_citations": missing,
                }
            )
        by_status = {
            name: sum(row["status"] == name for row in classifications)
            for name in ("encoded", "excluded", "pending")
        }
        summaries.append(
            {
                "root": root,
                "total_files": len(classifications),
                "by_status": by_status,
                "classifications": classifications,
            }
        )
    classified = sum(root["total_files"] for root in summaries)
    if classified != len(files):
        raise ClosureError("a RuleSpec file fell outside every declared closure root")
    program_summaries = {}
    for program, root_nodes in expected_program_roots.items():
        reached: set[str] = set()
        stack = list(root_nodes)
        while stack:
            node_id = stack.pop()
            if node_id in reached:
                continue
            node = nodes_by_id.get(node_id)
            if node is None:
                raise ClosureError(f"{program}: unknown subgraph root {node_id!r}")
            reached.add(node_id)
            stack.extend(nodes_by_name[name]["id"] for name in node["dependencies"])
        citations = sorted(
            {
                citation
                for node_id in reached
                for citation in nodes_by_id[node_id]["citations"]
            }
        )
        citation_rows = [
            {
                "citation_path": citation,
                "status": "encoded" if citation in corpus_set else "pending",
                "reason": (
                    "exact_path_present_in_pinned_corpus_release"
                    if citation in corpus_set
                    else "citation_absent_from_pinned_corpus_release"
                ),
            }
            for citation in citations
        ]
        pending = [
            row["citation_path"] for row in citation_rows if row["status"] == "pending"
        ]
        citation_floor = denominator_ratchet[program]["citation_count_min"]
        if len(citation_rows) < citation_floor:
            raise ClosureError(
                f"{program}: citation denominator RATCHET regressed "
                f"from floor {citation_floor} to {len(citation_rows)}"
            )
        program_summaries[program] = {
            "closed": not pending,
            "root_nodes": root_nodes,
            "root_node_count": len(root_nodes),
            "subgraph_node_count": len(reached),
            "citation_root_count": len(citation_rows),
            "by_status": {
                "encoded": len(citation_rows) - len(pending),
                "excluded": 0,
                "pending": len(pending),
            },
            "citations": citation_rows,
            "pending_citations": pending,
            "pending_money_atoms": 0,
            "denominator_ratchet": {
                "requested_output_count_min": denominator_ratchet[program][
                    "requested_output_count_min"
                ],
                "citation_count_min": citation_floor,
            },
        }
    return {
        "schema": "axiom_oracles.nz_closure_summary.v2",
        "jurisdiction": "nz",
        "rulespec_commit": RULESPEC_SHA,
        "corpus_release": "nz-rulespec-2026-07-18",
        "corpus_commit": CORPUS_RELEASE_SHA,
        "roots": summaries,
        "pending_citations": sorted(all_pending),
        "pending_money_atoms": 0,
        "closed": not all_pending,
        "programs": program_summaries,
        "source": {
            "artifact": str(SOURCE_PATH.relative_to(REPO_ROOT)),
            "sha256": hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest(),
        },
        "requested_output_trace": {
            "artifact": str(EVALUATION_TRACE_PATH.relative_to(REPO_ROOT)),
            "sha256": hashlib.sha256(EVALUATION_TRACE_PATH.read_bytes()).hexdigest(),
        },
        "executable_request_evidence": {
            "artifact": str(REQUEST_TRACE_PATH.relative_to(REPO_ROOT)),
            "sha256": hashlib.sha256(REQUEST_TRACE_PATH.read_bytes()).hexdigest(),
        },
        "denominator_ratchet": {
            "artifact": str(RATCHET_PATH.relative_to(REPO_ROOT)),
            "sha256": hashlib.sha256(RATCHET_PATH.read_bytes()).hexdigest(),
        },
    }


def validate_artifact(document: dict, *, repo_root: Path = REPO_ROOT) -> dict:
    """Pure validator used by the shared computed-certificate predicate."""

    if Path(repo_root).resolve() != REPO_ROOT.resolve():
        raise ClosureError("NZ closure must validate at the repository root")
    expected = build(load_source())
    if document != expected:
        raise ClosureError(
            "NZ closure artifact does not rederive from committed inputs"
        )
    return expected


def _render(value: dict) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--bootstrap-source", action="store_true")
    args = parser.parse_args()
    try:
        if args.bootstrap_source:
            rendered = _render(bootstrap_source())
            if args.check:
                if not SOURCE_PATH.exists() or SOURCE_PATH.read_text() != rendered:
                    print("NZ closure source snapshot drifted", file=sys.stderr)
                    return 1
            else:
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                SOURCE_PATH.write_text(rendered)
            return 0
        source = load_source()
        summary = build(source)
    except (OSError, json.JSONDecodeError, ClosureError) as exc:
        print(f"NZ closure ERROR: {exc}", file=sys.stderr)
        return 1
    rendered = _render(summary)
    if args.check:
        if not SUMMARY_PATH.exists() or SUMMARY_PATH.read_text() != rendered:
            print("NZ closure summary drifted", file=sys.stderr)
            return 1
        print("NZ closure summary up to date")
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(rendered)
    print(f"wrote {SUMMARY_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
