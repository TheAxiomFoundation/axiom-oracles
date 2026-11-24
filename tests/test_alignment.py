"""Oracle alignment report: reach, expected suites, and every status path.

Everything here is synthetic: a small rulespec tree in a scratch git
repository, three program files, hand-written compiled artifacts in the
engine's artifact shape, and suite reports of four invented cases. No engine
binary and no population data are needed.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from axiom_oracles import alignment
from axiom_oracles.alignment import (
    AlignmentError,
    AlignmentInputs,
    CompileCache,
    ProgramFile,
    TreeIndex,
    bind_suites,
    build_report,
    classify_path,
    compile_programs,
    derive_status,
    exit_code,
    glob_regex,
    load_declarations,
    load_suites,
    module_literals,
    read_checkout,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CONCEPT = "us:statutes/9/100#benefit"
ORACLE = {"name": "synthetic-oracle", "version": "1"}
QC_CONCEPT = "us:statutes/9/100#stage_benefit"

P_DEMO = "rulespec-us:programs/us-zz/demo/fy-2026.yaml"
P_NOSUITE = "rulespec-us:programs/us-zz/nosuite/fy-2026.yaml"
P_MANUAL = "rulespec-us:programs/us-zz/manual/fy-2026.yaml"

M_BENEFIT = "us/statutes/9/100.yaml"
M_BASE = "us/statutes/9/200.yaml"
M_RATES = "us/policies/demo/rates.yaml"
M_ORPHAN = "us/statutes/9/300.yaml"
M_NOSUITE = "us/statutes/9/400.yaml"
M_MANUAL = "us/statutes/9/500.yaml"
M_UNREACHED = "us-zz/policies/manual/page.yaml"
#: The module a bridge-built suite declares as its root.
M_ROOT = "us/statutes/9/800.yaml"
#: Imported by the declared root, two modules away.
M_ROOT_IMPORT = "us/statutes/9/900.yaml"
M_ROOT_IMPORT_2 = "us/statutes/9/910.yaml"

PARAMETER_MANIFEST = "comparisons/parameter-oracles.yaml"


# ---------------------------------------------------------------------------
# Synthetic world
# ---------------------------------------------------------------------------


def _derived(module: str, name: str, expr: dict) -> dict:
    return {"id": f"{module}#{name}", "name": name, "expr": expr}


def _ref(name: str) -> dict:
    return {"kind": "derived", "name": name}


def demo_artifact() -> dict:
    """``benefit`` reads ``base_amount`` (another module), a parameter of a
    third module and a relation; ``orphan`` is compiled but not reached."""
    return {
        "engine_version": "0.0.0-fixture",
        "program": {
            "parameters": [{"id": "us:policies/demo/rates#rate", "name": "rate"}],
            "relations": [{"name": "us:statutes/9/200#relation.member_of_unit", "arity": 2}],
            "derived": [
                _derived(
                    "us:statutes/9/100",
                    "benefit",
                    {
                        "kind": "mul",
                        "left": _ref("base_amount"),
                        "right": {"kind": "parameter_lookup", "parameter": "rate"},
                        "where": {
                            "kind": "count_related",
                            "relation": "us:statutes/9/200#relation.member_of_unit",
                        },
                    },
                ),
                _derived("us:statutes/9/200", "base_amount", {"kind": "input", "name": "income"}),
                _derived("us:statutes/9/300", "orphan", {"kind": "input", "name": "x"}),
            ],
        },
    }


def single_rule_artifact(module: str, name: str) -> dict:
    return {
        "engine_version": "0.0.0-fixture",
        "program": {
            "parameters": [],
            "derived": [_derived(module, name, {"kind": "input", "name": "x"})],
        },
    }


def artifacts() -> dict[str, dict]:
    return {
        P_DEMO: demo_artifact(),
        P_NOSUITE: single_rule_artifact("us:statutes/9/400", "other_amount"),
        P_MANUAL: single_rule_artifact("us:statutes/9/500", "manual_amount"),
    }


class FakeCompiler:
    def __init__(self, artifacts: dict[str, dict]) -> None:
        self.artifacts = artifacts
        self.fail: set[str] = set()

    def compile(self, program: ProgramFile, side: str):
        if program.key in self.fail:
            raise AlignmentError("program_compile_failed", f"{program.key} ({side}): boom")
        return self.artifacts[program.key]


class CountingCompiler(FakeCompiler):
    """Reports composed imports, so identical-input compiles can be reused."""

    def __init__(self, artifacts):
        super().__init__(artifacts)
        self.calls = []

    def compile(self, program, side):
        self.calls.append((program.key, side))
        return {**copy.deepcopy(super().compile(program, side)), "composed_imports": []}

    def candidate_calls(self):
        return sorted(key for key, side in self.calls if side == "candidate")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _module_text(marker: str) -> str:
    return f"format: rulespec/v1\nrules:\n  - name: rule_{marker}\n"


def commit(root: Path) -> str:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    if not (root / ".git").exists():
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    git("add", "-A")
    git("commit", "-q", "--allow-empty", "-m", "fixture")
    return git("rev-parse", "HEAD")


def write_tree(root: Path) -> Path:
    for index, rel in enumerate(
        (M_BENEFIT, M_BASE, M_RATES, M_ORPHAN, M_NOSUITE, M_MANUAL, M_UNREACHED, M_ROOT_IMPORT_2)
    ):
        _write(root / rel, _module_text(str(index)))
    _write(root / M_ROOT, "imports:\n  - us:statutes/9/900#rule\n")
    _write(root / M_ROOT_IMPORT, "imports:\n  - target: us:statutes/9/910\n")
    _write(root / "us/statutes/9/100.test.yaml", "cases: []\n")
    _write(root / "us/statutes/9/800.test.yaml", "cases: []\n")
    _write(root / "README.md", "fixture\n")
    _write(root / "programs/us-zz/demo/fy-2026.yaml", "program: us-zz/demo\noutputs:\n  - benefit\n")
    _write(
        root / "programs/us-zz/nosuite/fy-2026.yaml",
        "program: us-zz/nosuite\noutputs:\n  - other_amount\n",
    )
    _write(
        root / "programs/us-zz/manual/fy-2026.yaml",
        "program: us-zz/manual\noutputs:\n  - manual_amount\n",
    )
    return root


def _suite_yaml(
    name: str,
    *,
    ci: str | None,
    program: str | None = None,
    runner: str = "axiom-oracles-compare",
    extra_params: str = "",
) -> str:
    lines = [f"name: {name}"]
    if ci is not None:
        lines.append(f"ci: {ci}")
    lines += ["runner:", f"  type: {runner}", "  parameters:", "    left: axiom", "    right: oracle"]
    if program:
        lines.append(f"    axiom_program: $HOME/rulespec-us/{program}")
        concept = CONCEPT if "demo" in program else "manual_amount"
        lines += ["    concepts:", f"      - {concept}"]
    return "\n".join(lines) + "\n" + extra_params


COVERAGE = {
    "schema": "axiom_oracles.alignment_coverage.v1",
    "sets": {"nine_hundreds": ["us/statutes/9/9*.yaml"]},
    "declarations": [
        {
            "id": "zz-bridge",
            "match": {"runner_type": "zz-bridge-compare"},
            "roots": ["us/statutes/9/800.yaml"],
            "paths": ["us/statutes/9/800.test.yaml"],
            "sources": ["axiom_oracles/bridges/zz_bridge.py"],
        },
        {
            "id": "zz-foreign",
            "match": {"runner_type": ["zz-foreign-compare"]},
            "reads_rulespec_us": False,
        },
    ],
}


def write_registry(root: Path, *, demo_ci: str | None = None, dispositions: dict | None = None) -> Path:
    _write(
        root / "comparisons/zz-demo.yaml",
        _suite_yaml("zz-demo", ci=demo_ci, program="programs/us-zz/demo/fy-2026.yaml"),
    )
    _write(
        root / "comparisons/zz-manual.yaml",
        _suite_yaml("zz-manual", ci="manual", program="programs/us-zz/manual/fy-2026.yaml"),
    )
    _write(
        root / "comparisons/zz-bridge.yaml",
        _suite_yaml("zz-bridge", ci="manual", runner="zz-bridge-compare"),
    )
    _write(
        root / "comparisons/zz-foreign.yaml",
        _suite_yaml("zz-foreign", ci=None, runner="zz-foreign-compare"),
    )
    _write(
        root / "comparisons/zz-pinned.yaml",
        _suite_yaml(
            "zz-pinned",
            ci=None,
            program="programs/us-zz/demo/fy-2026.yaml",
            extra_params="    axiom_rulespec_repo_roots_revision: abc1234\n",
        ),
    )
    _write(
        root / PARAMETER_MANIFEST,
        yaml.safe_dump(
            {
                "schema": "axiom_oracles.parameter_suite_list.v1",
                "suites": [
                    {
                        "suite": "zz-params",
                        "comparisons": [{"file": "us/policies/demo/rates.yaml", "rule": "rate"}],
                    }
                ],
            }
        ),
    )
    _write(root / "comparisons/zz-demo.fixtures.yaml", "concept: x\nfixtures: []\n")
    _write(root / "axiom_oracles/bridges/zz_bridge.py", 'ROOT = "us/statutes/9/800.yaml"\n')
    _write(root / alignment.COVERAGE_FILE, yaml.safe_dump(COVERAGE, sort_keys=False))
    if dispositions is not None:
        _write(root / "dispositions/zz-demo.yaml", yaml.safe_dump(dispositions, sort_keys=False))
    return root


def case(case_id: str, state: object) -> dict:
    concepts: tuple[str, ...] = (CONCEPT,)
    if isinstance(state, tuple):
        state, concepts = state
    row = {"case_id": case_id, "left_errors": [], "right_errors": [], "matches": [], "mismatches": []}
    if state == "match":
        row["matches"] = [{"concept": CONCEPT, "left": 10, "right": 10}]
    elif state == "mismatch":
        row["mismatches"] = [
            {"concept": concept, "kind": "amount_difference", "left": 10, "right": 12}
            for concept in concepts
        ]
    elif state == "error":
        row["left_errors"] = ["missing input"]
    elif state == "right_error":
        row["right_errors"] = ["oracle failed"]
    return row


def provenance(sha: str, suite: str) -> dict:
    return {
        "schema": "axiom_oracles.provenance.v1",
        "generated_by": f"scripts/run_comparison.py::{suite}",
        "run_kind": "manual",
        "oracle": dict(ORACLE),
        "engine": {"axiom_rules_engine_sha": "e" * 40},
        "rulespecs": [{"repo": "TheAxiomFoundation/rulespec-us", "sha": sha, "dirty": False}],
    }


def suite_report(states: dict[str, object], sha: str, *, suite: str = "zz-demo") -> dict:
    cases = [case(case_id, state) for case_id, state in states.items()]
    return {
        "suite": suite,
        "case_count": len(cases),
        "cases": cases,
        "mismatches": [{**row, "case_id": c["case_id"]} for c in cases for row in c["mismatches"]],
        "provenance": provenance(sha, suite),
    }


def replay_report(matched: dict[str, bool], sha: str, *, suite: str = "zz-demo") -> dict:
    """The SNAP QC replay's case rows (``snap_qc_compare.py``)."""
    return {
        "suite": suite,
        "case_count": len(matched),
        "cases": [
            {
                "case_id": case_id,
                "yrmonth": 202401,
                "weight": 1.0,
                "matched": ok,
                "stage": None if ok else "benefit",
            }
            for case_id, ok in matched.items()
        ],
        "mismatches": [
            {"case_id": case_id, "concept": QC_CONCEPT, "kind": "amount_difference", "left": 1, "right": 2}
            for case_id, ok in matched.items()
            if not ok
        ],
        "errors": [],
        "summary": {"error_case_count": 0},
        "provenance": provenance(sha, suite),
    }


def grid_report(match: dict[str, bool], sha: str, *, suite: str = "zz-demo") -> dict:
    """The federal tax grid's case rows."""
    return {
        "suite": suite,
        "concept": CONCEPT,
        "case_count": len(match),
        "cases": [
            {"case_id": case_id, "concept": CONCEPT, "axiom": 1.0, "policyengine": 1.0, "match": ok}
            for case_id, ok in match.items()
        ],
        "mismatches": [
            {"case_id": case_id, "concept": CONCEPT, "kind": "amount_difference", "left": 1, "right": 2}
            for case_id, ok in match.items()
            if not ok
        ],
        "summary": {"error_count": 0},
        "provenance": provenance(sha, suite),
    }


class FakeExecutor:
    evidence = "live_run"

    def __init__(self, base, candidate) -> None:
        self.reports = {"base": base, "candidate": candidate}
        self.calls: list[tuple[str, str]] = []
        self.bound = None

    def bind(self, registry_commit, commits) -> None:
        self.bound = (registry_commit, dict(commits))

    def run(self, suite: str, side: str):
        self.calls.append((suite, side))
        report = self.reports[side]
        if isinstance(report, Exception):
            raise report
        return report


def disposition_file(case_ids: list[str], concept: str = CONCEPT) -> dict:
    return {
        "schema": "axiom_oracles.dispositions.v1",
        "suite": "zz-demo",
        "entries": [
            {
                "id": "zz-known-difference",
                "concept": concept,
                "kind": "amount_difference",
                "case_selector": {"case_ids": case_ids},
                "disposition": "explained_residual",
                "evidence": {"mechanism": "A synthetic, documented difference."},
                "linked_issue": "https://github.com/TheAxiomFoundation/axiom-oracles/issues/441",
                "expires_on_source_change": False,
            }
        ],
    }


class World:
    """Three scratch repositories: base tree, candidate tree, registry."""

    def __init__(self, home: Path) -> None:
        self.home = home
        self.base = home / "base" / "rulespec-us"
        self.candidate = home / "candidate" / "rulespec-us"
        self.registry = home / "registry"
        self.commits: dict[str, str] = {}
        self.registry_commit = ""

    def build(
        self,
        changed=M_BENEFIT,
        *,
        demo_ci=None,
        dispositions=None,
        registry_edit=None,
        candidate_edit=None,
        base_edit=None,
        both_edit=None,
    ) -> "World":
        paths = [changed] if isinstance(changed, str) else list(changed or [])
        for root in (self.base, self.candidate):
            write_tree(root)
            if both_edit:
                both_edit(root)
        if base_edit:
            base_edit(self.base)
        for rel in paths:
            _write(
                self.candidate / rel,
                (self.candidate / rel).read_text() + "# changed\n"
                if (self.candidate / rel).exists()
                else _module_text("new"),
            )
        if candidate_edit:
            candidate_edit(self.candidate)
        self.commits = {"base": commit(self.base), "candidate": commit(self.candidate)}
        write_registry(self.registry, demo_ci=demo_ci, dispositions=dispositions)
        if registry_edit:
            registry_edit(self.registry)
        self.registry_commit = commit(self.registry)
        return self

    def report(self, *, compiler=None, executor=None, explicit=None, cache=None) -> dict:
        return build_report(
            AlignmentInputs(
                base_root=self.base,
                candidate_root=self.candidate,
                registry_root=self.registry,
                compiler=compiler or FakeCompiler(artifacts()),
                changed=explicit,
                executor=executor,
                include_registry_programs=False,
                cache=cache,
            )
        )


@pytest.fixture
def world(tmp_path):
    """``run(changed, ...)`` builds the three repositories and reports."""
    count = [0]

    def run(
        changed=M_BENEFIT,
        *,
        compiler=None,
        executor=None,
        explicit=None,
        cache=None,
        reports=None,
        report_edit=None,
        return_world=False,
        **build,
    ):
        count[0] += 1
        built = World(tmp_path / f"run{count[0]}").build(changed, **build)
        if reports is not None:
            make = reports[2] if len(reports) > 2 else suite_report
            base = make(reports[0], built.commits["base"])
            candidate = make(reports[1], built.commits["candidate"])
            if report_edit:
                report_edit(base, candidate)
            executor = FakeExecutor(base, candidate)
        result = built.report(compiler=compiler, executor=executor, explicit=explicit, cache=cache)
        return (result, built) if return_world else result

    return run


def reaching(report: dict, path: str) -> list[str]:
    row = next(r for r in report["reach"] if r["path"] == path)
    return [hit["program"] for hit in row["reaching_programs"]]


def expected(report: dict) -> list[str]:
    return [suite["suite"] for suite in report["expected_suites"]]


def assert_error(report: dict, cause: str) -> None:
    assert report["status"] == "error", report
    assert report["error"]["cause"] == cause, report["error"]
    assert "reason" not in report
    assert exit_code(report) == 2


# ---------------------------------------------------------------------------
# Reach
# ---------------------------------------------------------------------------


def test_classify_path():
    assert classify_path("programs/us-az/snap/fy-2026.yaml") == ("program", None)
    assert classify_path("us-az/policies/des/faa5/x/block-8.yaml") == (
        "module",
        "us-az:policies/des/faa5/x/block-8",
    )
    assert classify_path("us-az/policies/des/faa5/x/block-8.test.yaml") == (
        "test",
        "us-az:policies/des/faa5/x/block-8",
    )
    assert classify_path("us-la/statutes/47:294.yaml") == ("module", "us-la:statutes/47:294")
    assert classify_path("us-co/.axiom/encoding-manifests/x.yaml") == ("other", None)
    assert classify_path("tools/check.py") == ("other", None)
    assert classify_path("README.yaml") == ("other", None)


@pytest.mark.parametrize(
    "path",
    ["us/statutes/9/100.yml", "us/statutes/9/100.YAML", "US/statutes/9/100.yaml", "Programs/a.yaml"],
)
def test_rule_like_file_where_nothing_reads_it_is_unclassified(path):
    with pytest.raises(AlignmentError) as excinfo:
        classify_path(path)
    assert excinfo.value.cause == "changed_file_unclassified"


def test_change_to_an_unclassified_file_is_an_error(world):
    def yml(root: Path) -> None:
        _write(root / "us/statutes/9/100.yml", _module_text("yml"))

    assert_error(world(None, candidate_edit=yml), "changed_file_unclassified")


@pytest.mark.parametrize(
    "module, programs",
    [
        (M_BENEFIT, [P_DEMO]),  # the output's own module
        (M_BASE, [P_DEMO]),  # reached through a derived reference and a relation
        (M_RATES, [P_DEMO]),  # reached through a parameter lookup only
        (M_ORPHAN, []),  # compiled into the program, not reached by its output
        (M_UNREACHED, []),  # in no program at all
        (M_NOSUITE, [P_NOSUITE]),
    ],
)
def test_reach_follows_compared_outputs(world, module, programs):
    report = world(module)
    assert reaching(report, module) == programs
    for side in ("base", "candidate"):
        assert report["programs"][side]["program_files_found"] == 3
        assert report["programs"][side]["programs_compiled"] == 3


def test_reach_names_the_reached_rules(world):
    report = world(M_BASE)
    hit = report["reach"][0]["reaching_programs"][0]
    assert hit["via"] == "compared_outputs"
    assert hit["sides"] == ["base", "candidate"]
    assert hit["reached"] == ["base_amount", "relation.member_of_unit"]


def test_reach_follows_every_version_of_a_dated_rule(world):
    """A module read only by an earlier version of the output is reached."""
    dated = artifacts()
    benefit = dated[P_DEMO]["program"]["derived"][0]
    benefit["versions"] = [
        {"effective_from": "2020-01-01", "effective_to": "2025-12-31", "expr": _ref("orphan")},
        {"effective_from": "2026-01-01", "effective_to": None, "expr": benefit["expr"]},
    ]
    assert world(M_ORPHAN)["status"] == "no_reference"
    report = world(M_ORPHAN, compiler=FakeCompiler(dated))
    assert reaching(report, M_ORPHAN) == [P_DEMO]
    assert report["status"] == "reference_not_executed"


def test_program_file_change_reaches_its_own_program(world):
    report = world("programs/us-zz/demo/fy-2026.yaml")
    hit = report["reach"][0]["reaching_programs"][0]
    assert (hit["program"], hit["via"], hit["sides"]) == (P_DEMO, "program_file", ["base", "candidate"])
    assert expected(report) == ["zz-demo"]


def test_program_file_on_one_side_only_reaches_its_program(world):
    def remove(root: Path) -> None:
        (root / "programs/us-zz/manual/fy-2026.yaml").unlink()

    report = world(None, candidate_edit=remove)
    hit = report["reach"][0]["reaching_programs"][0]
    assert (hit["program"], hit["sides"]) == (P_MANUAL, ["base"])
    assert report["status"] == "reference_not_runnable"
    assert report["programs"]["candidate"]["program_files_found"] == 2

    report = world(None, base_edit=remove)
    hit = report["reach"][0]["reaching_programs"][0]
    assert (hit["program"], hit["sides"]) == (P_MANUAL, ["candidate"])
    assert report["status"] == "reference_not_runnable"


def test_companion_test_file_has_no_reach_of_its_own(world):
    report = world("us/statutes/9/100.test.yaml")
    assert report["reach"][0]["kind"] == "test"
    assert report["reach"][0]["reaching_programs"] == []
    assert report["status"] == "no_reference"


def test_reach_on_one_side_only_still_counts(world):
    """A candidate that unwires a module was still reached on base."""

    class SideCompiler(FakeCompiler):
        def __init__(self, artifacts, side):
            super().__init__(artifacts)
            self.side = side

        def compile(self, program, side):
            if program.key == P_DEMO and side == self.side:
                return single_rule_artifact("us:statutes/9/100", "benefit")
            return super().compile(program, side)

    for unwired, reached_on in (("candidate", "base"), ("base", "candidate")):
        report = world(M_BASE, compiler=SideCompiler(artifacts(), unwired))
        hit = report["reach"][0]["reaching_programs"][0]
        assert hit["sides"] == [reached_on]
        assert report["status"] == "reference_not_executed"


def test_deleted_module_is_reached_through_base(world):
    def remove(root: Path) -> None:
        (root / M_BASE).unlink()

    report = world(None, candidate_edit=remove)
    assert reaching(report, M_BASE) == [P_DEMO]
    assert report["provenance"]["changed_files"][0]["candidate_sha256"] is None


def test_unresolved_suite_concept_widens_reach_to_every_rule(world):
    """A concept the walk cannot place makes every rule of the program count
    as compared, so an orphan module is not called ``no_reference``."""

    def edit(registry: Path) -> None:
        path = registry / "comparisons/zz-demo.yaml"
        path.write_text(path.read_text().replace(CONCEPT, "us:statutes/9/100#mapped_elsewhere"))

    assert world(M_ORPHAN)["status"] == "no_reference"
    report = world(M_ORPHAN, registry_edit=edit)
    assert report["status"] == "reference_not_executed"
    hit = report["reach"][0]["reaching_programs"][0]
    assert hit["via"] == "every_rule_unresolved_suite_concept"
    (suite,) = report["expected_suites"]
    assert suite["unresolved_concepts"] == ["us:statutes/9/100#mapped_elsewhere"]
    # A module in no program stays unreached.
    assert world(M_UNREACHED, registry_edit=edit)["status"] == "no_reference"


def test_suite_concepts_are_roots_beside_the_program_outputs(world):
    def edit(registry: Path) -> None:
        path = registry / "comparisons/zz-demo.yaml"
        path.write_text(path.read_text().replace(CONCEPT, "us:statutes/9/300#orphan"))

    report = world(M_ORPHAN, registry_edit=edit)
    assert reaching(report, M_ORPHAN) == [P_DEMO]
    assert report["expected_suites"][0]["compared_concepts_reach_change"] is True


def test_provenance(world):
    report, built = world(M_BASE, return_world=True)
    provenance_block = report["provenance"]
    assert provenance_block["registry_commit"] == built.registry_commit
    assert provenance_block["registry_dirty"] is False
    assert provenance_block["rulespec_commit"] == built.commits
    assert provenance_block["tool_version"].endswith("+derivation.2")
    assert len(provenance_block["coverage_declarations_sha256"]) == 64
    assert set(provenance_block["compiled_programs"]["candidate"]) == {P_DEMO, P_NOSUITE, P_MANUAL}
    assert all(len(v) == 64 for v in provenance_block["compiled_programs"]["base"].values())
    (changed,) = provenance_block["changed_files"]
    assert changed["path"] == M_BASE
    assert changed["base_sha256"] == hashlib.sha256((built.base / M_BASE).read_bytes()).hexdigest()
    assert changed["candidate_sha256"] != changed["base_sha256"]
    assert report["report_only"] is True


# ---------------------------------------------------------------------------
# The two trees
# ---------------------------------------------------------------------------


def test_changed_files_come_from_the_commits(world):
    def more(root: Path) -> None:
        _write(root / "tools/new.py", "x = 1\n")
        _write(root / "us/statutes/9/100.test.yaml", "cases: [1]\n")

    report = world(M_BASE, candidate_edit=more)
    assert [(row["path"], row["kind"]) for row in report["reach"]] == [
        ("tools/new.py", "other"),
        ("us/statutes/9/100.test.yaml", "test"),
        (M_BASE, "module"),
    ]


def test_given_changed_list_must_equal_the_tree_diff(world):
    assert world([M_BASE, M_UNREACHED], explicit=[M_BASE, M_UNREACHED])["status"] != "error"
    assert world([M_BASE, M_UNREACHED], explicit=[M_UNREACHED, M_BASE])["status"] != "error"
    # A subset would hide a change; a superset names a file that did not change.
    assert_error(world([M_BASE, M_UNREACHED], explicit=[M_UNREACHED]), "changed_files_mismatch")
    assert_error(world(M_UNREACHED, explicit=[M_UNREACHED, M_BASE]), "changed_files_mismatch")
    assert_error(world(M_BASE, explicit=[M_BASE, M_BASE]), "changed_files_mismatch")


@pytest.mark.parametrize(
    "spelling",
    [
        "us//statutes/9/100.yaml",
        "us/./statutes/9/100.yaml",
        "./us/statutes/9/100.yaml",
        "US/statutes/9/100.yaml",
        "us/statutes/9/100.YAML",
        "us/statutes/9/../9/100.yaml",
        "/us/statutes/9/100.yaml",
        " us/statutes/9/100.yaml",
    ],
)
def test_given_changed_path_is_not_normalised(world, spelling):
    assert_error(world(M_BENEFIT, explicit=[spelling]), "changed_files_mismatch")


def test_identical_trees_are_an_error(world):
    assert_error(world(None), "no_changed_files")


def test_tree_with_uncommitted_change_is_an_error(tmp_path):
    for side, edit in (
        ("base", lambda root: _write(root / M_BASE, "edited\n")),
        ("candidate", lambda root: _write(root / "us/statutes/9/new.yaml", "untracked\n")),
        ("candidate", lambda root: _write(root / "notes.txt", "untracked elsewhere\n")),
    ):
        built = World(tmp_path / f"{side}{len(list(tmp_path.iterdir()))}").build(M_BASE)
        edit(getattr(built, side))
        assert_error(built.report(), "rulespec_tree_dirty")


def test_tree_that_is_not_a_checkout_is_an_error(tmp_path):
    built = World(tmp_path / "w").build(M_BASE)
    shutil.rmtree(built.candidate / ".git")
    assert_error(built.report(), "rulespec_tree_not_a_checkout")


def test_sparse_or_partly_deleted_tree_is_an_error(tmp_path):
    """Files the commit tracks but the work tree lacks, with a clean status."""
    built = World(tmp_path / "w").build(M_BASE)
    git = ["git", "-C", str(built.base)]
    subprocess.run([*git, "update-index", "--skip-worktree", M_MANUAL], check=True)
    (built.base / M_MANUAL).unlink()
    assert subprocess.run([*git, "status", "--porcelain"], capture_output=True).stdout == b""
    assert_error(built.report(), "rulespec_tree_incomplete")


def test_tree_without_programs_is_an_error(world):
    def no_programs(root: Path) -> None:
        shutil.rmtree(root / "programs")

    def disabled(root: Path) -> None:
        for path in list((root / "programs").rglob("*.yaml")):
            path.rename(path.with_suffix(".yaml.disabled"))

    # Without the check, the manual suite's program is gone and nothing reaches.
    assert_error(world(M_MANUAL, both_edit=no_programs), "no_programs")
    assert_error(world(M_MANUAL, candidate_edit=no_programs), "no_programs")
    assert_error(world(M_MANUAL, base_edit=no_programs), "no_programs")
    assert_error(world(M_MANUAL, both_edit=disabled), "no_programs")


def test_program_listing_comes_from_the_commit(tmp_path):
    built = World(tmp_path / "w").build(M_BASE)
    checkout = read_checkout(built.base, "base")
    assert [p.relpath for p in alignment.checkout_programs(checkout)] == [
        "programs/us-zz/demo/fy-2026.yaml",
        "programs/us-zz/manual/fy-2026.yaml",
        "programs/us-zz/nosuite/fy-2026.yaml",
    ]
    assert checkout.commit == built.commits["base"]


def test_unreadable_module_file_is_an_error(tmp_path):
    built = World(tmp_path / "w").build(M_BASE)
    (built.candidate / M_ORPHAN).write_bytes(b"\xff\xfe not text")
    commit(built.candidate)
    assert_error(built.report(), "rulespec_tree_unreadable")


# ---------------------------------------------------------------------------
# Status: the non-executed states
# ---------------------------------------------------------------------------


def test_no_reference_when_no_program_reaches(world):
    report = world(M_UNREACHED)
    assert (report["status"], report["reason"]) == ("no_reference", "no_program_reaches")
    assert report["expected_suites"] == []
    assert exit_code(report) == 0


def test_no_reference_when_reaching_program_has_no_suite(world):
    report = world(M_NOSUITE)
    assert (report["status"], report["reason"]) == (
        "no_reference",
        "no_suite_for_reaching_programs",
    )
    assert exit_code(report) == 0


def test_no_reference_for_a_file_no_suite_reads(world):
    def tooling(root: Path) -> None:
        _write(root / "tools/new.py", "x = 1\n")

    report = world(None, candidate_edit=tooling)
    assert (report["status"], report["reason"]) == ("no_reference", "no_program_reaches")


def test_reference_not_runnable_when_every_expected_suite_is_manual(world):
    report = world(M_MANUAL)
    assert report["status"] == "reference_not_runnable"
    assert report["manual_suites"] == ["zz-manual"]
    assert report["expected_suites"][0]["mode"] == "manual"
    assert "reason" not in report
    assert exit_code(report) == 0


def test_manual_marker_comes_from_the_suite_file(world):
    report = world(M_BENEFIT, demo_ci="manual")
    assert report["status"] == "reference_not_runnable"
    assert report["manual_suites"] == ["zz-demo"]


def test_a_ci_lane_suite_is_runnable(world):
    report = world(M_BENEFIT, demo_ci="snap-qc-replay")
    (suite,) = report["expected_suites"]
    assert (suite["mode"], suite["ci"]) == ("runnable", "snap-qc-replay")
    assert report["status"] == "reference_not_executed"


def test_reference_not_executed_without_an_executor(world):
    report = world(M_BENEFIT)
    assert report["status"] == "reference_not_executed"
    assert report["runnable_suites"] == ["zz-demo"]
    assert exit_code(report) == 0


def test_manual_suites_are_not_executed(world):
    executor = FakeExecutor(None, None)
    report = world(M_MANUAL, executor=executor)
    assert report["status"] == "reference_not_runnable"
    assert executor.calls == []


def test_mixed_expected_suites_list_both(world):
    report = world([M_BENEFIT, M_MANUAL])
    assert report["status"] == "reference_not_executed"
    assert report["runnable_suites"] == ["zz-demo"]
    assert report["manual_suites"] == ["zz-manual"]


def test_pinned_suite_cannot_observe_a_candidate(world):
    """zz-pinned names the demo program but replays a pinned snapshot."""
    report = world(M_BENEFIT)
    assert expected(report) == ["zz-demo"]
    assert report["suite_registry"]["pinned_snapshot_suites"] == ["zz-pinned"]


def test_parameter_manifest_suite_covers_its_files(world):
    report = world(M_RATES)
    assert expected(report) == ["zz-demo", "zz-params"]
    by_name = {suite["suite"]: suite for suite in report["expected_suites"]}
    assert by_name["zz-params"]["binding"] == "parameter_files"
    assert by_name["zz-params"]["mode"] == "manual"
    assert by_name["zz-params"]["covered_files"] == {M_RATES: "declared_path"}


def test_suite_registry_counts(world):
    report = world(M_BENEFIT)
    assert report["suite_registry"] == {
        "suites": 6,
        "runnable": 3,
        "manual": 3,
        "by_binding": {
            "declared": 1,
            "declared_reads_no_rulespec_us": 1,
            "parameter_files": 1,
            "pinned_snapshot": 1,
            "program": 2,
        },
        "pinned_snapshot_suites": ["zz-pinned"],
    }


# ---------------------------------------------------------------------------
# Declared coverage
# ---------------------------------------------------------------------------


def test_glob_regex():
    assert glob_regex("us/statutes/26/**").match("us/statutes/26/32/c.yaml")
    assert not glob_regex("us/statutes/26/**").match("us/statutes/260/x.yaml")
    assert glob_regex("us/policies/cbp/**/ch*.yaml").match("us/policies/cbp/gen/ch02/ch02.yaml")
    assert not glob_regex("us/*.yaml").match("us/a/b.yaml")
    assert glob_regex("us-??/x.yaml").match("us-co/x.yaml")
    assert not glob_regex("us/x.yaml").match("us/xxyaml")


@pytest.mark.parametrize(
    "changed, how",
    [
        (M_ROOT, "declared_path"),  # the root module itself
        (M_ROOT_IMPORT, "declared_root_closure"),  # imported by the root
        (M_ROOT_IMPORT_2, "declared_root_closure"),  # imported two modules away
        ("us/statutes/9/800.test.yaml", "declared_path"),  # a file the harness reads
    ],
)
def test_declared_suite_covers_roots_their_imports_and_paths(world, changed, how):
    report = world(changed)
    (suite,) = report["expected_suites"]
    assert (suite["suite"], suite["binding"], suite["declaration"]) == (
        "zz-bridge",
        "declared",
        "zz-bridge",
    )
    assert suite["covered_files"] == {changed: how}
    assert report["status"] == "reference_not_runnable"


def test_declared_suite_covers_what_only_the_base_tree_imports(world):
    def unwire(root: Path) -> None:
        _write(root / M_ROOT, "imports: []\n")

    report = world(M_ROOT_IMPORT, candidate_edit=unwire)
    assert report["expected_suites"][0]["covered_files"][M_ROOT_IMPORT] == "declared_root_closure"


def test_declared_root_glob_covers_a_module_named_no_where(world):
    """A harness that reads a directory by glob covers a new file in it."""

    def edit(registry: Path) -> None:
        doc = copy.deepcopy(COVERAGE)
        doc["declarations"][0]["roots"] = ["@nine_hundreds", "us/statutes/9/800.yaml"]
        _write(registry / alignment.COVERAGE_FILE, yaml.safe_dump(doc, sort_keys=False))

    report = world("us/statutes/9/999.yaml", registry_edit=edit)
    assert report["expected_suites"][0]["covered_files"] == {
        "us/statutes/9/999.yaml": "declared_path"
    }
    assert world("us/statutes/9/999.yaml")["status"] == "no_reference"


def test_declared_bridge_suite_is_expected_beside_a_program_suite(world):
    """A bound suite does not hide a bridge suite that also reads the module."""

    def edit(registry: Path) -> None:
        doc = copy.deepcopy(COVERAGE)
        doc["declarations"][0]["roots"].append("us/statutes/9/100.yaml")
        _write(registry / alignment.COVERAGE_FILE, yaml.safe_dump(doc, sort_keys=False))

    report = world(M_BENEFIT, registry_edit=edit)
    assert expected(report) == ["zz-bridge", "zz-demo"]
    assert report["manual_suites"] == ["zz-bridge"]


def test_suite_that_reads_no_rulespec_us_is_never_expected(world):
    report = world([M_BENEFIT, M_ROOT, M_RATES, M_MANUAL])
    assert "zz-foreign" not in expected(report)


def _add_suite(name: str, **kwargs):
    def edit(registry: Path) -> None:
        _write(registry / f"comparisons/{name}.yaml", _suite_yaml(name, **kwargs))

    return edit


def test_suite_with_no_binding_and_no_declaration_is_an_error(world):
    """An undeclared suite could cover anything: nothing is ``no_reference``,
    and no other status is given either, while one exists."""
    edit = _add_suite("zz-new", ci="manual", runner="zz-unknown-compare")
    for changed in (M_UNREACHED, M_NOSUITE, M_BENEFIT, M_MANUAL):
        report = world(changed, registry_edit=edit)
        assert_error(report, "reference_unbound")
        assert "zz-new" in report["error"]["detail"]


@pytest.mark.parametrize(
    "ref",
    [
        "$RULESPEC_US/programs/us-zz/manual/fy-2026.yaml",
        "$HOME/TheAxiomFoundation/rulespec-us-main/programs/us-zz/manual/fy-2026.yaml",
        "$HOME/rulespec-us/programs/us-zz/missing/fy-2026.yaml",
        "$HOME/axiom-programs/uk/universal-credit/fy-2026-27.yaml",
    ],
)
def test_suite_whose_program_does_not_resolve_is_an_error(world, ref):
    def edit(registry: Path) -> None:
        path = registry / "comparisons/zz-manual.yaml"
        path.write_text(
            path.read_text().replace("$HOME/rulespec-us/programs/us-zz/manual/fy-2026.yaml", ref)
        )

    assert_error(world(M_MANUAL, registry_edit=edit), "reference_unbound")


def test_registry_program_reference_forms():
    key = alignment._program_key_from_ref
    assert key("$HOME/rulespec-us/programs/us-az/snap/fy-2026.yaml") == (
        "rulespec-us:programs/us-az/snap/fy-2026.yaml"
    )
    assert key("$HOME/axiom-oracles/programs/us/ssi/fy-2026.yaml") == (
        "axiom-oracles:programs/us/ssi/fy-2026.yaml"
    )
    assert key("programs/us/ssi/fy-2026.yaml") == "axiom-oracles:programs/us/ssi/fy-2026.yaml"
    assert key("$HOME/fork/rulespec-us-main/programs/x.yaml") is None


def test_suite_file_with_yml_suffix_is_read(world):
    def edit(registry: Path) -> None:
        os.rename(registry / "comparisons/zz-manual.yaml", registry / "comparisons/zz-manual.yml")

    report = world(M_MANUAL, registry_edit=edit)
    assert report["manual_suites"] == ["zz-manual"]


def test_manifest_row_naming_a_program_is_bound_to_it(world):
    def edit(registry: Path) -> None:
        (registry / "comparisons/zz-manual.yaml").unlink()
        _write(
            registry / "comparisons/campaign.yaml",
            yaml.safe_dump(
                {
                    "schema_version": "axiom.campaign_projection_suite_list.v1",
                    "suites": [
                        {
                            "suite": "zz-manual",
                            "axiom_program": "$HOME/rulespec-us/programs/us-zz/manual/fy-2026.yaml",
                        }
                    ],
                }
            ),
        )

    report = world(M_MANUAL, registry_edit=edit)
    assert report["status"] == "reference_not_runnable"
    assert report["manual_suites"] == ["zz-manual"]


def test_manifest_suite_uses_a_declaration_with_its_state(world):
    def edit(registry: Path) -> None:
        _write(
            registry / "comparisons/campaign.yaml",
            yaml.safe_dump(
                {
                    "schema_version": "axiom.campaign_projection_suite_list.v1",
                    "suites": [{"suite": "zz-campaign", "jurisdiction": "ZZ"}],
                }
            ),
        )
        doc = copy.deepcopy(COVERAGE)
        doc["declarations"].append(
            {
                "id": "campaign",
                "match": {"source": "comparisons/campaign.yaml"},
                "roots": ["us-{state}/**"],
            }
        )
        _write(registry / alignment.COVERAGE_FILE, yaml.safe_dump(doc, sort_keys=False))

    report = world(M_UNREACHED, registry_edit=edit)
    assert report["status"] == "reference_not_runnable"
    assert report["manual_suites"] == ["zz-campaign"]


def _coverage_edit(mutate):
    def edit(registry: Path) -> None:
        doc = copy.deepcopy(COVERAGE)
        mutate(doc, registry)
        _write(registry / alignment.COVERAGE_FILE, yaml.safe_dump(doc, sort_keys=False))

    return edit


@pytest.mark.parametrize(
    "mutate",
    [
        lambda doc, reg: doc.update(schema="other"),
        lambda doc, reg: doc.update(declarations="none"),
        lambda doc, reg: doc["declarations"].append(dict(doc["declarations"][0])),  # duplicate id
        lambda doc, reg: doc["declarations"].append(  # two declarations match zz-bridge
            {"id": "again", "match": {"suites": ["zz-b*"]}, "roots": ["us/**"]}
        ),
        lambda doc, reg: doc["declarations"][0].update(roots=["@missing_set"]),
        lambda doc, reg: doc["declarations"][0].update(roots=["../outside/**"]),
        lambda doc, reg: doc["declarations"][0].update(roots=[], paths=[]),
        lambda doc, reg: doc["declarations"][0].update(roots=["us-{state}/**"]),  # no such variable
        lambda doc, reg: doc["declarations"][0].update(sources=["scripts/gone.py"]),
        lambda doc, reg: doc["declarations"][0].update(reads_rulespec_us="no"),
        lambda doc, reg: doc["declarations"][1].update(roots=["us/**"]),  # none, with globs
        lambda doc, reg: doc["declarations"][0].update(match={"runner": "x"}),
        lambda doc, reg: doc["declarations"][0].update(covers=["us/**"]),
    ],
)
def test_unreadable_declarations_are_an_error(world, mutate):
    assert_error(
        world(M_UNREACHED, registry_edit=_coverage_edit(mutate)), "coverage_declarations_unreadable"
    )


def test_missing_declarations_file_is_an_error(world):
    def edit(registry: Path) -> None:
        (registry / alignment.COVERAGE_FILE).unlink()

    assert_error(world(M_UNREACHED, registry_edit=edit), "coverage_declarations_unreadable")


def test_module_literals():
    text = 'import:\n  target: us:statutes/26/152/c#rule\n  hash: sha256:6b4df92c\nurl: https://x.org/a/b\n'
    assert module_literals(text) == {"us:statutes/26/152/c"}
    assert module_literals("- us-la:statutes/47:294#x and us-la:statutes/47:294.1") == {
        "us-la:statutes/47:294",
        "us-la:statutes/47:294.1",
    }
    split = 'A = Path(\n    "us-zz/policies/manual/"\n    "page.yaml"\n)\n'
    assert module_literals(split) == set()
    assert module_literals(split, paths=True) == {"us-zz:policies/manual/page"}
    assert module_literals('T = "us/statutes/9/100.test.yaml"', paths=True) == {"us:statutes/9/100"}


def test_module_id_with_a_colon_is_followed(world):
    def tree(root: Path) -> None:
        _write(root / "us-la/statutes/47:294.yaml", _module_text("la"))
        _write(root / M_ROOT, "imports:\n  - us-la:statutes/47:294#rule\n")

    report = world("us-la/statutes/47:294.yaml", both_edit=tree)
    assert report["reach"][0]["module"] == "us-la:statutes/47:294"
    assert expected(report) == ["zz-bridge"]


# ---------------------------------------------------------------------------
# Status: errors are never no_reference
# ---------------------------------------------------------------------------


def test_compile_failure_is_an_error_not_no_reference(world):
    for failing in (P_DEMO, P_NOSUITE):
        compiler = FakeCompiler(artifacts())
        compiler.fail = {failing}
        # Without the failed program nothing would reach these modules.
        assert_error(world(M_BENEFIT, compiler=compiler), "program_compile_failed")
        assert_error(world(M_UNREACHED, compiler=compiler), "program_compile_failed")


def test_compiled_count_mismatch_is_an_error(world, monkeypatch):
    real = alignment.compile_programs

    def dropping(programs, compiler, **kwargs):
        trimmed = {side: list(items)[:-1] for side, items in programs.items()}
        compiled, _ = real(trimmed, compiler, **kwargs)
        return alignment._count_check(programs, compiled)

    monkeypatch.setattr(alignment, "compile_programs", dropping)
    assert_error(world(M_UNREACHED), "program_count_mismatch")


def test_count_check_compares_files_found_with_programs_compiled(tmp_path):
    built = World(tmp_path / "w").build(M_BASE)
    programs = {
        "base": alignment.checkout_programs(read_checkout(built.base, "base")),
        "candidate": [],
    }
    compiled, counts = compile_programs(programs, FakeCompiler(artifacts()))
    assert counts["base"]["program_files_found"] == counts["base"]["programs_compiled"] == 3
    extra = dict(compiled["base"])
    del compiled["base"][P_DEMO]
    with pytest.raises(AlignmentError) as excinfo:
        alignment._count_check(programs, compiled)
    assert excinfo.value.cause == "program_count_mismatch"
    compiled["base"] = {**extra, "rulespec-us:programs/ghost.yaml": extra[P_DEMO]}
    with pytest.raises(AlignmentError):
        alignment._count_check(programs, compiled)


def test_uncompiled_program_is_an_error_in_the_reach_walk(tmp_path):
    built = World(tmp_path / "w").build(M_BASE)
    programs = {
        "base": alignment.checkout_programs(read_checkout(built.base, "base")),
        "candidate": [],
    }
    compiled, _ = compile_programs(programs, FakeCompiler(artifacts()))
    del compiled["base"][P_NOSUITE]
    with pytest.raises(AlignmentError) as excinfo:
        alignment.compute_reach([], programs, compiled, [])
    assert excinfo.value.cause == "program_count_mismatch"


def test_artifact_without_rules_is_an_error(world):
    bad = artifacts()
    bad[P_NOSUITE] = {"program": {"derived": []}}
    assert_error(world(M_UNREACHED, compiler=FakeCompiler(bad)), "program_compile_failed")


def test_declared_output_missing_from_the_compiled_program_is_an_error(world):
    bad = artifacts()
    bad[P_DEMO] = single_rule_artifact("us:statutes/9/100", "not_the_output")
    assert_error(world(M_UNREACHED, compiler=FakeCompiler(bad)), "output_not_in_compiled_program")


def test_duplicate_rule_names_are_an_error(world):
    bad = artifacts()
    bad[P_DEMO]["program"]["derived"].append(
        _derived("us:statutes/9/300", "benefit", {"kind": "input", "name": "x"})
    )
    assert_error(world(M_UNREACHED, compiler=FakeCompiler(bad)), "compiled_program_ambiguous")


def test_program_without_outputs_is_an_error(world):
    def edit(root: Path) -> None:
        _write(root / "programs/us-zz/nosuite/fy-2026.yaml", "program: us-zz/nosuite\n")

    assert_error(world(M_UNREACHED, candidate_edit=edit), "program_without_outputs")


@pytest.mark.parametrize(
    "breakage",
    [
        lambda r: (r / "comparisons/zz-demo.yaml").write_text("name: [unclosed\n"),
        lambda r: (r / "comparisons/zz-demo.yaml").write_text("- a\n- b\n"),
        lambda r: (r / "comparisons/zz-copy.yaml").write_text(
            (r / "comparisons/zz-demo.yaml").read_text()
        ),
        lambda r: (r / "comparisons/zz-demo.yaml").write_text("name: zz-demo\nrunner: {}\n"),
        lambda r: (r / "comparisons/zz-demo.yaml").write_text(
            "name: zz-demo\nci: [manual]\nrunner:\n  type: x\n"
        ),
        lambda r: (r / "comparisons/zz-demo.yaml").write_text(
            "name: zz-demo\nci: true\nrunner:\n  type: x\n"
        ),
        # A file that is neither a suite nor a known manifest.
        lambda r: (r / "comparisons/notes.yaml").write_text("schema: other\nsuites: []\n"),
        lambda r: (r / "comparisons/notes.yaml").write_text("title: something\n"),
        lambda r: (r / PARAMETER_MANIFEST).write_text(
            "schema: axiom_oracles.parameter_suite_list.v1\nsuites: []\n"
        ),
        lambda r: (r / PARAMETER_MANIFEST).write_text(
            "schema: axiom_oracles.parameter_suite_list.v1\nsuites:\n  - suite: a\n"
        ),
        # A suite file in a subdirectory would not be read.
        lambda r: _write(
            r / "comparisons/sub/zz-sub.yaml", _suite_yaml("zz-sub", ci="manual")
        ),
    ],
)
def test_unreadable_registry_is_an_error(world, breakage):
    assert_error(world(M_UNREACHED, registry_edit=breakage), "registry_unreadable")


def test_missing_registry_is_an_error(tmp_path):
    with pytest.raises(AlignmentError) as excinfo:
        load_suites(tmp_path)
    assert excinfo.value.cause == "registry_unreadable"
    (tmp_path / "comparisons").mkdir()
    with pytest.raises(AlignmentError) as excinfo:
        load_suites(tmp_path)
    assert excinfo.value.cause == "registry_unreadable"


def test_registry_that_is_not_a_checkout_is_an_error(tmp_path):
    built = World(tmp_path / "w").build(M_UNREACHED)
    shutil.rmtree(built.registry / ".git")
    assert_error(built.report(), "registry_unreadable")


def test_internal_failure_is_an_error(world, monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(alignment, "compute_reach", explode)
    report = world(M_UNREACHED)
    assert_error(report, "internal_error")


def test_error_report_drops_any_earlier_status_fields():
    report = {"status": "no_reference", "reason": "no_program_reaches", "counts": {}}
    alignment._mark_error(report, "x", "y")
    assert report == {"status": "error", "error": {"cause": "x", "detail": "y"}}


# ---------------------------------------------------------------------------
# Status: aligned / regressed
# ---------------------------------------------------------------------------

ALL_MATCH = {"a": "match", "b": "match", "c": "mismatch", "d": "match"}
SECOND = "us:statutes/9/100#second"


def test_aligned_when_no_case_regresses(world):
    report = world(reports=(ALL_MATCH, {**ALL_MATCH, "c": "match"}))
    assert report["status"] == "aligned"
    assert report["executed_suites"] == ["zz-demo"]
    assert report["counts"] == {
        "cases": 4,
        "matched_before": 3,
        "matched_after": 4,
        "newly_matched": 1,
        "newly_mismatched": 0,
        "newly_errored": 0,
        "newly_mismatched_outputs_in_mismatched_cases": 0,
        "dispositioned": 0,
        "undispositioned_regressions": 0,
    }
    (execution,) = report["executions"]
    assert (execution["report_shape"], execution["evidence"]) == ("population", "live_run")
    assert exit_code(report) == 0


def test_aligned_when_nothing_changes(world):
    report = world(reports=(ALL_MATCH, ALL_MATCH))
    assert report["status"] == "aligned"
    assert report["counts"]["matched_before"] == report["counts"]["matched_after"] == 3


def test_regressed_when_a_matching_case_mismatches(world):
    report = world(reports=(ALL_MATCH, {**ALL_MATCH, "a": "mismatch"}))
    assert report["status"] == "regressed"
    assert report["regressed_suites"] == ["zz-demo"]
    assert report["counts"]["newly_mismatched"] == 1
    assert report["counts"]["matched_after"] == 2
    assert report["executions"][0]["regressions"] == [
        {"case_id": "a", "kind": "newly_mismatched", "concepts": [CONCEPT]}
    ]
    assert exit_code(report) == 0  # report only


def test_one_regression_is_not_offset_by_new_matches(world):
    report = world(reports=(ALL_MATCH, {**ALL_MATCH, "a": "mismatch", "c": "match"}))
    assert report["status"] == "regressed"
    assert report["counts"]["matched_before"] == report["counts"]["matched_after"] == 3


def test_disposition_that_selects_the_case_keeps_it_aligned(world):
    report = world(
        reports=(ALL_MATCH, {**ALL_MATCH, "a": "mismatch"}), dispositions=disposition_file(["a"])
    )
    assert report["status"] == "aligned"
    assert report["counts"]["newly_mismatched"] == 1
    assert report["counts"]["dispositioned"] == 1


def test_disposition_that_selects_another_case_does_not_hide_a_regression(world):
    report = world(
        reports=(ALL_MATCH, {**ALL_MATCH, "a": "mismatch"}), dispositions=disposition_file(["c"])
    )
    assert report["status"] == "regressed"
    assert report["counts"]["dispositioned"] == 0


def test_disposition_for_another_concept_does_not_hide_a_regression(world):
    report = world(
        reports=(ALL_MATCH, {**ALL_MATCH, "a": "mismatch"}),
        dispositions=disposition_file(["a"], concept="us:statutes/9/100#other"),
    )
    assert report["status"] == "regressed"


def test_disposition_must_select_every_new_mismatch_row_of_the_case(world):
    both = ("mismatch", (CONCEPT, SECOND))
    report = world(reports=(ALL_MATCH, {**ALL_MATCH, "a": both}), dispositions=disposition_file(["a"]))
    assert report["status"] == "regressed"


def test_disposition_whose_pinned_values_moved_does_not_select(world):
    for pinned, status in (({"left": 10, "right": 12}, "aligned"), ({"left": 10, "right": 11}, "regressed")):
        doc = disposition_file(["a"])
        entry = doc["entries"][0]
        entry.pop("case_selector")
        entry["case_id"] = "a"
        entry["pinned"] = pinned
        report = world(reports=(ALL_MATCH, {**ALL_MATCH, "a": "mismatch"}), dispositions=doc)
        assert report["status"] == status, report.get("error")


def test_disposition_needs_the_report_level_mismatch_row(world):
    def drop_rows(base, candidate):
        candidate["mismatches"] = []

    report = world(
        reports=(ALL_MATCH, {**ALL_MATCH, "a": "mismatch"}),
        dispositions=disposition_file(["a"]),
        report_edit=drop_rows,
    )
    assert report["status"] == "regressed"


def test_newly_errored_case_is_a_regression(world):
    for state in ("error", "right_error"):
        report = world(
            reports=(ALL_MATCH, {**ALL_MATCH, "a": state}), dispositions=disposition_file(["a"])
        )
        assert report["status"] == "regressed"
        assert report["counts"]["newly_errored"] == 1
    # A case that already errored on base is not new.
    report = world(reports=({**ALL_MATCH, "a": "error"}, {**ALL_MATCH, "a": "right_error"}))
    assert report["status"] == "aligned"


def test_new_mismatching_output_in_an_already_mismatched_case_is_a_regression(world):
    both = ("mismatch", (CONCEPT, SECOND))
    report = world(reports=(ALL_MATCH, {**ALL_MATCH, "c": both}))
    assert report["status"] == "regressed"
    assert report["counts"]["newly_mismatched"] == 0
    assert report["counts"]["newly_mismatched_outputs_in_mismatched_cases"] == 1


def test_error_to_match_is_newly_matched(world):
    report = world(reports=({**ALL_MATCH, "a": "error"}, ALL_MATCH))
    assert report["status"] == "aligned"
    assert report["counts"]["newly_matched"] == 1


def test_base_error_to_candidate_mismatch_is_a_regression(world):
    report = world(reports=({**ALL_MATCH, "a": "error"}, {**ALL_MATCH, "a": "mismatch"}))
    assert report["status"] == "regressed"
    assert report["counts"]["newly_mismatched"] == 1
    report = world(
        reports=({**ALL_MATCH, "a": "error"}, {**ALL_MATCH, "a": "mismatch"}),
        dispositions=disposition_file(["a"]),
    )
    assert report["status"] == "aligned"


def test_case_with_matches_and_mismatches_is_a_mismatch(world):
    def mixed(base, candidate):
        candidate["cases"][0]["matches"] = [{"concept": SECOND, "left": 1, "right": 1}]
        base["cases"][0]["matches"].append({"concept": SECOND, "left": 1, "right": 1})

    report = world(reports=(ALL_MATCH, {**ALL_MATCH, "a": "mismatch"}), report_edit=mixed)
    assert report["status"] == "regressed"
    assert report["counts"]["matched_after"] == 2


def test_output_no_longer_compared_on_candidate_is_an_error(world):
    def shrink(base, candidate):
        base["cases"][0]["matches"].append({"concept": SECOND, "left": 1, "right": 1})

    assert_error(world(reports=(ALL_MATCH, ALL_MATCH), report_edit=shrink), "compared_outputs_differ")

    def grow(base, candidate):
        candidate["cases"][0]["matches"].append({"concept": SECOND, "left": 1, "right": 1})

    assert world(reports=(ALL_MATCH, ALL_MATCH), report_edit=grow)["status"] == "aligned"


def test_invalid_dispositions_file_is_an_error(world):
    bad = disposition_file(["a"])
    bad["schema"] = "something.else"
    assert_error(world(reports=(ALL_MATCH, ALL_MATCH), dispositions=bad), "dispositions_unreadable")


# --- the report shapes of the runnable suites --------------------------------


def test_snap_qc_replay_report_shape(world):
    same = {"a": True, "b": True, "c": False}
    report = world(reports=(same, same, replay_report))
    assert report["status"] == "aligned"
    assert report["executions"][0]["report_shape"] == "replay"
    assert report["counts"]["cases"] == 3

    report = world(reports=(same, {**same, "a": False}, replay_report))
    assert report["status"] == "regressed"
    assert report["executions"][0]["regressions"] == [
        {"case_id": "a@202401", "kind": "newly_mismatched", "concepts": [QC_CONCEPT]}
    ]

    report = world(reports=(same, {**same, "c": True}, replay_report))
    assert (report["status"], report["counts"]["newly_matched"]) == ("aligned", 1)

    report = world(
        reports=(same, {**same, "a": False}, replay_report),
        dispositions=disposition_file(["a"], concept=QC_CONCEPT),
    )
    assert (report["status"], report["counts"]["dispositioned"]) == ("aligned", 1)


def test_replay_mismatch_without_a_report_level_row_cannot_be_dispositioned(world):
    def drop_rows(base, candidate):
        candidate["mismatches"] = []

    same = {"a": True}
    report = world(
        reports=(same, {"a": False}, replay_report),
        dispositions=disposition_file(["a"], concept=QC_CONCEPT),
        report_edit=drop_rows,
    )
    assert report["status"] == "regressed"
    assert report["executions"][0]["regressions"][0]["concepts"] == ["<unattributed>"]


def test_replay_run_that_recorded_errors_is_an_error(world):
    for key in ("error_case_count", "error_count"):

        def errors(base, candidate, key=key):
            candidate["summary"][key] = 2

        assert_error(
            world(reports=({"a": True}, {"a": True}, replay_report), report_edit=errors),
            "suite_run_failed",
        )

    def listed(base, candidate):
        candidate["errors"] = [{"engine": "axiom", "message": "x"}]

    assert_error(
        world(reports=({"a": True}, {"a": True}, replay_report), report_edit=listed),
        "suite_run_failed",
    )


def test_tax_grid_report_shape(world):
    same = {"a": True, "b": True}
    report = world(reports=(same, same, grid_report))
    assert report["status"] == "aligned"
    assert report["executions"][0]["report_shape"] == "grid"
    report = world(reports=(same, {**same, "b": False}, grid_report))
    assert report["status"] == "regressed"
    assert report["executions"][0]["regressions"][0]["concepts"] == [CONCEPT]


def test_report_shape_without_a_case_state_is_an_error(world):
    def state_grid(base, candidate):
        for report in (base, candidate):
            report["cases"] = [
                {"case_id": "a", "concept": CONCEPT, "axiom": 1, "axiom_vs_policyengine": True}
            ]
            report["case_count"] = 1

    assert_error(
        world(reports=(ALL_MATCH, ALL_MATCH), report_edit=state_grid),
        "suite_report_shape_unsupported",
    )


def test_reports_of_two_shapes_are_an_error(world):
    def swap(base, candidate):
        candidate.update(replay_report({k: True for k in ALL_MATCH}, _commit_of(candidate)))

    assert_error(
        world(reports=(ALL_MATCH, ALL_MATCH), report_edit=swap), "suite_report_shape_unsupported"
    )


def _commit_of(report: dict) -> str:
    return report["provenance"]["rulespecs"][0]["sha"]


# --- execution failures ------------------------------------------------------


def test_zero_cases_is_an_error(world):
    assert_error(world(reports=(ALL_MATCH, {})), "zero_cases")
    assert_error(world(reports=({}, {})), "zero_cases")


def test_case_count_difference_is_an_error(world):
    fewer = {k: v for k, v in ALL_MATCH.items() if k != "c"}
    assert_error(world(reports=(ALL_MATCH, fewer)), "case_count_differs")
    assert_error(world(reports=(fewer, ALL_MATCH)), "case_count_differs")


def test_different_case_ids_are_an_error(world):
    renamed = {("z" if k == "c" else k): v for k, v in ALL_MATCH.items()}
    assert_error(world(reports=(ALL_MATCH, renamed)), "case_ids_differ")


def test_duplicate_case_id_is_an_error(world):
    def duplicate(base, candidate):
        candidate["cases"].append(copy.deepcopy(candidate["cases"][0]))
        candidate["case_count"] = 5

    assert_error(world(reports=(ALL_MATCH, ALL_MATCH), report_edit=duplicate), "suite_run_failed")


def test_suite_run_failure_is_an_error(world, tmp_path):
    built = World(tmp_path / "w").build(M_BENEFIT)
    executor = FakeExecutor(
        suite_report(ALL_MATCH, built.commits["base"]), AlignmentError("suite_run_failed", "exit 1")
    )
    assert_error(built.report(executor=executor), "suite_run_failed")
    executor = FakeExecutor(AlignmentError("timeout", "suite zz-demo (base)"), None)
    assert_error(built.report(executor=executor), "timeout")


@pytest.mark.parametrize(
    "tamper, cause",
    [
        (lambda c: c["provenance"].update(reemitted_report=True), "suite_run_failed"),
        (lambda c: c["provenance"].update(run_kind="reemitted"), "suite_run_failed"),
        (lambda c: c.update(suite="zz-other"), "suite_run_failed"),
        (lambda c: c.pop("suite"), "suite_run_failed"),
        (lambda c: c.update(case_count=40), "suite_report_truncated"),
        (lambda c: c.pop("case_count"), "suite_report_truncated"),
        (lambda c: c.update(case_count=True), "suite_report_truncated"),
        (
            lambda c: c.update(dashboard_truncation={"shown_case_rows": 4, "total_case_rows": 9}),
            "suite_report_truncated",
        ),
        (lambda c: c["cases"][0].update(matches=[], mismatches=[]), "suite_run_failed"),
        (lambda c: c.pop("provenance"), "suite_report_provenance_mismatch"),
        (
            lambda c: c["provenance"].update(generated_by="scripts/run_comparison.py::zz-other"),
            "suite_report_provenance_mismatch",
        ),
        (lambda c: c["provenance"].update(generated_by="zz-demo"), "suite_report_provenance_mismatch"),
        (lambda c: c["provenance"].update(oracle={}), "suite_report_provenance_mismatch"),
        (
            lambda c: c["provenance"].update(oracle={"name": "another-oracle"}),
            "suite_report_provenance_mismatch",
        ),
        (
            lambda c: c["provenance"].update(engine={"axiom_rules_engine_sha": "f" * 40}),
            "suite_report_provenance_mismatch",
        ),
        (lambda c: c["provenance"]["rulespecs"][0].update(sha="d" * 40), "suite_report_provenance_mismatch"),
        (lambda c: c["provenance"]["rulespecs"][0].update(dirty=True), "suite_report_provenance_mismatch"),
        (lambda c: c["provenance"]["rulespecs"][0].pop("dirty"), "suite_report_provenance_mismatch"),
        # A second row for the repository, whatever its commit.
        (
            lambda c: c["provenance"]["rulespecs"].append(
                {"repo": "TheAxiomFoundation/rulespec-us", "sha": "d" * 40, "dirty": False}
            ),
            "suite_report_provenance_mismatch",
        ),
        (
            lambda c: c["provenance"]["rulespecs"].append(dict(c["provenance"]["rulespecs"][0])),
            "suite_report_provenance_mismatch",
        ),
        # The commit recorded for another repository of the same short name.
        (
            lambda c: c["provenance"]["rulespecs"][0].update(repo="someone/rulespec-us"),
            "suite_report_provenance_mismatch",
        ),
        (
            lambda c: c["provenance"]["rulespecs"][0].update(repo="TheAxiomFoundation/rulespec-us-fork"),
            "suite_report_provenance_mismatch",
        ),
    ],
)
def test_report_that_is_not_one_live_run_of_the_suite_is_an_error(world, tamper, cause):
    def edit(base, candidate):
        tamper(candidate)

    assert_error(world(reports=(ALL_MATCH, ALL_MATCH), report_edit=edit), cause)


def test_base_report_is_checked_too(world):
    def edit(base, candidate):
        base["provenance"]["rulespecs"][0]["sha"] = _commit_of(candidate)

    assert_error(world(reports=(ALL_MATCH, ALL_MATCH), report_edit=edit), "suite_report_provenance_mismatch")


def test_both_reports_truncated_alike_is_an_error(world):
    def truncate(base, candidate):
        for report in (base, candidate):
            report.pop("case_count")
            report["cases"] = report["cases"][:1]

    assert_error(world(reports=(ALL_MATCH, ALL_MATCH), report_edit=truncate), "suite_report_truncated")


def test_compare_needs_both_commits():
    report = suite_report(ALL_MATCH, "b" * 40)
    with pytest.raises(AlignmentError) as excinfo:
        alignment.compare_suite_reports("zz-demo", report, report, commits={"base": "b" * 40})
    assert excinfo.value.cause == "side_commit_unknown"


# --- supplied reports --------------------------------------------------------


def _supply(directory: Path, built: World, base: dict, candidate: dict, **overrides) -> Path:
    digests = {}
    for side, report in (("base", base), ("candidate", candidate)):
        text = json.dumps(report)
        _write(directory / side / "zz-demo.json", text)
        digests[side] = hashlib.sha256(text.encode()).hexdigest()
    manifest = {
        "schema": "axiom_oracles.alignment_supplied_reports.v1",
        "registry_commit": built.registry_commit,
        "rulespec_commit": dict(built.commits),
        "reports": {"zz-demo": digests},
    }
    manifest.update(overrides)
    _write(directory / "manifest.json", json.dumps(manifest))
    return directory


def test_supplied_reports_are_bound_by_a_manifest(tmp_path):
    built = World(tmp_path / "w").build(M_BENEFIT)
    base = suite_report(ALL_MATCH, built.commits["base"])
    candidate = suite_report({**ALL_MATCH, "b": "mismatch"}, built.commits["candidate"])

    def run(directory):
        return built.report(executor=alignment.ReportsDirExecutor(directory))

    report = run(_supply(tmp_path / "ok", built, base, candidate))
    assert report["status"] == "regressed"
    assert report["executions"][0]["evidence"] == "supplied_reports"

    assert_error(run(tmp_path / "absent"), "supplied_reports_unbound")
    assert_error(
        run(_supply(tmp_path / "r", built, base, candidate, registry_commit="0" * 40)),
        "supplied_reports_unbound",
    )
    swapped = {"base": built.commits["candidate"], "candidate": built.commits["base"]}
    assert_error(
        run(_supply(tmp_path / "c", built, base, candidate, rulespec_commit=swapped)),
        "supplied_reports_unbound",
    )
    assert_error(
        run(_supply(tmp_path / "s", built, base, candidate, schema="other")),
        "supplied_reports_unbound",
    )
    assert_error(
        run(_supply(tmp_path / "n", built, base, candidate, reports={})), "supplied_reports_unbound"
    )
    edited = _supply(tmp_path / "e", built, base, candidate)
    _write(edited / "candidate/zz-demo.json", json.dumps(suite_report(ALL_MATCH, built.commits["candidate"])))
    assert_error(run(edited), "supplied_reports_unbound")
    missing = _supply(tmp_path / "m", built, base, candidate)
    (missing / "base/zz-demo.json").unlink()
    assert_error(run(missing), "suite_run_failed")


def test_supplied_report_is_not_read_before_the_manifest_is_checked(tmp_path):
    with pytest.raises(AlignmentError) as excinfo:
        alignment.ReportsDirExecutor(tmp_path).run("zz-demo", "base")
    assert excinfo.value.cause == "supplied_reports_unbound"


# --- derive_status in isolation ----------------------------------------------


def _expected(name: str, mode: str) -> dict:
    return {"suite": name, "mode": mode}


def _execution(name: str, status: str) -> dict:
    return {"suite": name, "status": status, "counts": {"cases": 1}}


def test_derive_status_requires_every_runnable_suite_executed():
    expected_suites = [_expected("a", "runnable"), _expected("b", "runnable")]
    with pytest.raises(AlignmentError) as excinfo:
        derive_status([], expected_suites, [_execution("a", "aligned")])
    assert excinfo.value.cause == "suite_run_incomplete"
    with pytest.raises(AlignmentError):
        derive_status([], expected_suites, [])


def test_derive_status_one_regressed_suite_regresses_the_change():
    expected_suites = [_expected("a", "runnable"), _expected("b", "runnable"), _expected("m", "manual")]
    result = derive_status(
        [], expected_suites, [_execution("a", "aligned"), _execution("b", "regressed")]
    )
    assert result["status"] == "regressed"
    assert result["regressed_suites"] == ["b"]
    assert result["manual_suites_not_run"] == ["m"]
    assert result["counts"] == {"cases": 2}


def test_derive_status_rejects_an_execution_without_a_result():
    with pytest.raises(AlignmentError) as excinfo:
        derive_status([], [_expected("a", "runnable")], [_execution("a", "error")])
    assert excinfo.value.cause == "suite_run_failed"


# ---------------------------------------------------------------------------
# Artifact reuse
# ---------------------------------------------------------------------------


def test_candidate_program_is_recompiled_only_when_its_inputs_changed(world):
    # A module no program reads: every candidate program takes the base artifact.
    compiler = CountingCompiler(artifacts())
    report = world(M_UNREACHED, compiler=compiler)
    assert report["programs"]["candidate"]["reused"] == 3
    assert report["programs"]["base"]["reused"] == 0
    assert compiler.candidate_calls() == []
    assert report["provenance"]["compiled_programs"]["candidate"] == (
        report["provenance"]["compiled_programs"]["base"]
    )

    # A module only the demo program compiled from: only that one is recompiled.
    compiler = CountingCompiler(artifacts())
    world(M_ORPHAN, compiler=compiler)
    assert compiler.candidate_calls() == [P_DEMO]

    # A program file changes: that program is recompiled.
    compiler = CountingCompiler(artifacts())
    world("programs/us-zz/demo/fy-2026.yaml", compiler=compiler)
    assert compiler.candidate_calls() == [P_DEMO]

    # A companion test file changes: nothing is recompiled.
    compiler = CountingCompiler(artifacts())
    world("us/statutes/9/100.test.yaml", compiler=compiler)
    assert compiler.candidate_calls() == []


def test_new_file_in_an_imported_directory_forces_a_recompile(world):
    compiler = CountingCompiler(artifacts())

    def add(root: Path) -> None:
        _write(root / "us/statutes/9/100/extra.yaml", _module_text("new"))

    world(None, compiler=compiler, candidate_edit=add)
    assert compiler.candidate_calls() == [P_DEMO]


def test_compiler_that_reports_no_imports_is_never_reused(world):
    class Counting(FakeCompiler):
        calls = 0

        def compile(self, program, side):
            Counting.calls += 1
            return super().compile(program, side)

    report = world(M_UNREACHED, compiler=Counting(artifacts()))
    assert Counting.calls == 6
    assert report["programs"]["candidate"]["reused"] == 0


class CacheBench:
    def __init__(self, tmp_path: Path, edits: dict[str, str] | None = None) -> None:
        self.root = write_tree(tmp_path / "rulespec-us")
        for rel, text in (edits or {}).items():
            _write(self.root / rel, text)
        commit(self.root)
        self.cache_dir = tmp_path / "cache"

    def tree(self) -> TreeIndex:
        return TreeIndex(read_checkout(self.root, "base"))

    def run(self, salt="toolchain-a", cache=None) -> list[str]:
        checkout = read_checkout(self.root, "base")
        programs = {"base": alignment.checkout_programs(checkout), "candidate": []}
        compiler = CountingCompiler(artifacts())
        compile_programs(
            programs,
            compiler,
            trees={"base": TreeIndex(checkout)},
            cache=cache or CompileCache(self.cache_dir, salt=salt),
        )
        return sorted(key for key, _ in compiler.calls)

    def edit(self, rel: str, text: str) -> None:
        _write(self.root / rel, text)
        commit(self.root)

    def entries(self, key: str, salt="toolchain-a") -> list[Path]:
        slot = hashlib.sha256(f"{salt}\0{key}".encode()).hexdigest()
        return sorted((self.cache_dir / slot).glob("*.json"))


def test_persistent_cache_is_bound_to_inputs_and_toolchain(tmp_path):
    bench = CacheBench(tmp_path)
    assert len(bench.run()) == 3
    assert bench.run() == []
    assert len(bench.run(salt="toolchain-b")) == 3
    bench.edit(M_BENEFIT, _module_text("edited"))
    assert bench.run() == [P_DEMO]
    bench.edit("programs/us-zz/manual/fy-2026.yaml", "program: us-zz/manual\noutputs:\n  - manual_amount\n# x\n")
    assert bench.run() == [P_MANUAL]


def test_cache_follows_what_a_compiled_module_imports(tmp_path):
    """A module that contributes no rule to the artifact still feeds the
    compile when a compiled module imports it."""
    bench = CacheBench(
        tmp_path,
        {M_NOSUITE: "imports:\n  - us:statutes/9/800\n", M_ROOT_IMPORT_2: "imports:\n  - us-zz:policies/manual/page#rule\n"},
    )
    cache = CompileCache()
    assert len(bench.run(cache=cache)) == 3
    assert bench.run(cache=cache) == []
    bench.edit(M_UNREACHED, _module_text("edited four imports away"))
    assert bench.run(cache=cache) == [P_NOSUITE]
    bench.edit("us/statutes/9/100.test.yaml", "cases: [1]\n")
    assert bench.run(cache=cache) == []
    bench.edit("us/statutes/9/400/extra.test.yaml", "cases: []\n")
    assert bench.run(cache=cache) == []
    bench.edit("us/statutes/9/400/extra.yaml", _module_text("in the directory"))
    assert bench.run(cache=cache) == [P_NOSUITE]


def test_cache_entry_that_is_not_whole_is_recompiled(tmp_path):
    bench = CacheBench(tmp_path)
    bench.run()
    (entry_path,) = bench.entries(P_MANUAL)
    good = entry_path.read_text()

    def with_entry(mutate) -> list[str]:
        entry = json.loads(good)
        mutate(entry)
        entry_path.write_text(json.dumps(entry))
        return bench.run()

    assert bench.run() == []
    # The artifact re-pointed at another module, digest left alone.
    assert with_entry(
        lambda e: e["artifact"]["program"]["derived"][0].update(id="us:statutes/9/999#manual_amount")
    ) == [P_MANUAL]
    # The same, with the digest recomputed: the recorded inputs no longer fit.
    def repoint(entry):
        entry["artifact"]["program"]["derived"][0]["id"] = "us:statutes/9/999#manual_amount"
        entry["artifact_sha256"] = alignment.canonical_json_sha256(entry["artifact"])

    assert with_entry(repoint) == [P_MANUAL]
    # An entry that claims to have read nothing but the program file.
    def no_inputs(entry):
        entry["inputs"]["files"] = {}
        entry["inputs"]["dirs"] = {}

    assert with_entry(no_inputs) == [P_MANUAL]
    assert with_entry(lambda e: e.pop("artifact_sha256")) == [P_MANUAL]
    assert with_entry(lambda e: e.update(schema="other")) == [P_MANUAL]
    assert with_entry(lambda e: e.pop("artifact")) == [P_MANUAL]
    assert with_entry(lambda e: e["artifact"].pop("composed_imports")) == [P_MANUAL]
    assert with_entry(lambda e: e["inputs"].update(program=P_DEMO)) == [P_MANUAL]
    entry_path.write_text("{not json")
    assert bench.run() == [P_MANUAL]


def test_in_memory_reuse_checks_the_program_and_its_files(tmp_path):
    bench = CacheBench(tmp_path)
    tree = bench.tree()
    program = alignment.checkout_programs(read_checkout(bench.root, "base"))[0]
    recorded = tree.program_inputs(program, {"us:statutes/9/100"})
    assert tree.matches(program, recorded)
    assert not tree.matches(program, {**recorded, "program": "rulespec-us:programs/other.yaml"})
    assert not tree.matches(program, {**recorded, "program_sha256": "0" * 64})
    assert not tree.matches(program, {**recorded, "files": {M_BENEFIT: "0"}})
    assert not tree.matches(program, {**recorded, "dirs": {"us/statutes/9/100/": "0"}})
    assert not tree.matches(program, {**recorded, "files": None})


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _write_compiled(directory: Path) -> None:
    for side in ("base", "candidate"):
        for key, artifact in artifacts().items():
            origin, relpath = key.split(":", 1)
            _write(directory / side / origin / f"{relpath}.json", json.dumps(artifact))


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "alignment_report.py"), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def test_cli_end_to_end_with_supplied_reports(tmp_path):
    built = World(tmp_path / "w").build(M_BASE)
    _write_compiled(tmp_path / "compiled")
    reports = _supply(
        tmp_path / "reports",
        built,
        suite_report(ALL_MATCH, built.commits["base"]),
        suite_report({**ALL_MATCH, "b": "mismatch"}, built.commits["candidate"]),
    )
    common = [
        "--base-root", str(built.base),
        "--candidate-root", str(built.candidate),
        "--registry-root", str(built.registry),
        "--compiled-dir", str(tmp_path / "compiled"),
        "--no-registry-programs",
    ]  # fmt: skip
    output = tmp_path / "out" / "report.json"
    result = _cli(*common, "--reports-dir", str(reports), "--output", str(output))
    assert result.returncode == 0, result.stderr
    printed = json.loads(result.stdout)
    written = json.loads(output.read_text())
    assert printed == written
    assert written["status"] == "regressed"
    assert written["schema"] == "axiom_oracles.alignment_report.v1"
    assert written["provenance"]["toolchain"]["compiler"] == "precompiled_artifacts"
    assert written["provenance"]["rulespec_commit"] == built.commits

    result = _cli(*common, "--quiet", "--changed", M_BASE)
    assert result.returncode == 0 and result.stdout == ""
    result = _cli(*common, "--changed", M_BENEFIT)
    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["cause"] == "changed_files_mismatch"

    (tmp_path / "compiled/candidate/rulespec-us/programs/us-zz/demo/fy-2026.yaml.json").unlink()
    result = _cli(*common)
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert (report["status"], report["error"]["cause"]) == ("error", "program_compile_failed")


def test_cli_rejects_an_incomplete_tree_choice(tmp_path):
    assert _cli("--base-root", str(tmp_path)).returncode == 2


def test_cli_has_no_commit_override():
    assert _cli("--base-sha", "a" * 40).returncode == 2


# ---------------------------------------------------------------------------
# The real registry and its coverage declarations
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real():
    suites = load_suites(REPO_ROOT)
    declarations, _ = load_declarations(REPO_ROOT)
    known = {suite.program_key for suite in suites if suite.program_key}
    known -= {key for key in known if "uk/" in key}
    bound = bind_suites(suites, known, declarations)
    return suites, declarations, {item.suite.name: item for item in bound}


def test_every_real_suite_has_exactly_one_binding(real):
    suites, _, bound = real
    assert len(suites) == len(bound) > 200
    assert {suite.mode for suite in suites} == {"runnable", "manual"}
    for suite in suites:
        if suite.mode == "manual":
            assert suite.ci == "manual"
    assert bound["az-snap-ecps"].binding == "program"
    assert bound["az-snap-ecps"].suite.program_key == "rulespec-us:programs/us-az/snap/fy-2026.yaml"
    assert bound["az-tanf-ecps"].suite.program_key == "axiom-oracles:programs/us-az/tanf/fy-2026.yaml"
    assert bound["ssi-ecps"].suite.program_key == "axiom-oracles:programs/us/ssi/fy-2026.yaml"
    assert bound["uk-universal-credit-efrs"].binding == "declared_reads_no_rulespec_us"
    assert bound["us-niit-grid"].binding == "pinned_snapshot"
    assert bound["taxcalc-fiit-ecps"].binding == "no_axiom_side"
    assert bound["ga-health-thresholds"].binding == "parameter_files"
    assert bound["az-income-tax-liability"].roots[0] == "us-az/**"
    assert bound["al-income-tax-populace"].roots[0] == "us-al/**"
    assert bound["co-snap-ecps"].roots[0] == "us-co/**"
    assert bound["az-snap-qc"].suite.mode == "runnable"
    assert bound["us-snap-abawd-grid"].suite.mode == "runnable"


def test_real_registry_with_an_unknown_program_is_unbound(real):
    suites, declarations, _ = real
    with pytest.raises(AlignmentError) as excinfo:
        bind_suites(suites, set(), declarations)
    assert excinfo.value.cause == "reference_unbound"
    assert "az-snap-ecps" in excinfo.value.detail


def test_every_real_declaration_is_used(real):
    suites, declarations, bound = real
    used = {item.declaration for item in bound.values() if item.declaration}
    assert used == {declaration.id for declaration in declarations}


def _affected_map() -> dict[str, dict]:
    rows = json.loads((REPO_ROOT / "comparisons" / "affected_map.json").read_text())["suites"]
    return {row["suite"]: row for row in rows}


def test_real_bindings_agree_with_the_affected_map(real):
    """The generated affected map says which suites exercise rulespec-us and
    which replay a pin. One known gap: it lists no repository for
    ``us-tariff-schedule``, which reads the generated tariff chapters."""
    _, _, bound = real
    rows = _affected_map()
    for name, item in bound.items():
        row = rows.get(name)
        if row is None:
            continue
        reads_us = "TheAxiomFoundation/rulespec-us" in row["repos"]
        if item.binding == "pinned_snapshot":
            assert row.get("pinned"), name
        else:
            assert not row.get("pinned"), name
        if item.binding in ("declared_reads_no_rulespec_us", "no_axiom_side"):
            assert not reads_us, name
        elif item.binding != "pinned_snapshot" and name != "us-tariff-schedule":
            assert reads_us, name
    assert bound["us-tariff-schedule"].binding == "declared"


def test_real_declarations_cover_what_their_sources_name(real):
    """Every module a declaration's source files name, by id or by path, for
    a jurisdiction the declaration's suites read, is inside its globs."""
    suites, declarations, bound = real
    checked = 0
    for declaration in declarations:
        if not declaration.sources:
            continue
        named: set[str] = set()
        for source in declaration.sources:
            named |= module_literals((REPO_ROOT / source).read_text(), paths=True)
        members = [item for item in bound.values() if item.declaration == declaration.id]
        assert members, declaration.id
        globs = [glob_regex(p) for item in members for p in (*item.roots, *item.paths)]
        jurisdictions = {"us"} | {
            item.suite.variables.get("jurisdiction", "us") for item in members
        } | {p.split("/", 1)[0] for item in members for p in item.roots}
        for module in sorted(named):
            jurisdiction, rest = module.split(":", 1)
            if jurisdiction not in jurisdictions:
                continue
            if rest.split("/", 1)[0] not in ("statutes", "regulations", "policies"):
                continue  # a concept id of the comparison vocabulary, not a module
            path = f"{jurisdiction}/{rest}.yaml"
            assert any(regex.match(path) for regex in globs), (declaration.id, path)
            checked += 1
    assert checked > 100


def test_snap_qc_declarations_match_the_bridge_configuration(real):
    from axiom_oracles.bridges.snap_qc_compare import QC_JURISDICTIONS

    _, _, bound = real
    for jurisdiction, config in QC_JURISDICTIONS.items():
        item = bound[f"{jurisdiction.split('-', 1)[1]}-snap-qc"]
        roots = [glob_regex(p) for p in item.roots]
        paths = [glob_regex(p) for p in (*item.roots, *item.paths)]
        assert any(regex.match(config.program.as_posix()) for regex in roots), jurisdiction
        assert any(regex.match(config.template.as_posix()) for regex in paths), jurisdiction
        overlay = yaml.safe_load(
            (REPO_ROOT / "axiom_oracles/bridges/overlays" / f"{config.overlay}.yaml").read_text()
        )
        files = [overlay["program"], *overlay.get("rewrite_files", [])]
        files += [patch["file"] for patch in overlay.get("parameter_patches", [])]
        for target in overlay.get("module_id_rewrites", {}).values():
            files.append(target.replace(":", "/", 1) + ".yaml")
        for file in files:
            assert any(regex.match(file) for regex in roots), (jurisdiction, file)


def test_tariff_schedule_chapters_are_covered(real):
    """The schedule campaign reads ``ch*/ch*.yaml`` by glob; no id names them."""
    _, _, bound = real
    chapter = "us/policies/cbp/us-tariff-schedule/generated/ch02/ch02.yaml"
    for name in ("us-tariff-schedule", "us-tariff", "us-tariff-panel"):
        assert any(glob_regex(p).match(chapter) for p in bound[name].roots), name
    source = (REPO_ROOT / "scripts/us_tariff_schedule_campaign.py").read_text()
    assert 'glob("ch*/ch*.yaml")' in source
