"""Oracle alignment report: reach, expected suites, and every status path.

Everything here is synthetic: a five-module rulespec tree, three program
files, hand-written compiled artifacts in the engine's artifact shape, and
suite reports of four invented cases. No engine binary and no population data
are needed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from axiom_oracles import alignment
from axiom_oracles.alignment import (
    AlignmentError,
    AlignmentInputs,
    ProgramFile,
    build_report,
    changed_files,
    classify_path,
    compare_suite_reports,
    derive_status,
    exit_code,
    load_suites,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
BASE_SHA = "b" * 40
CANDIDATE_SHA = "c" * 40
CONCEPT = "us:statutes/9/100#benefit"

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
M_HARNESS = "us/statutes/9/900.yaml"
M_UNBOUND_SUITE = "us/statutes/9/800.yaml"


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
                _derived(
                    "us:statutes/9/200",
                    "base_amount",
                    {"kind": "input", "name": "income"},
                ),
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


class FakeCompiler:
    def __init__(self, artifacts: dict[str, dict]) -> None:
        self.artifacts = artifacts
        self.fail: set[str] = set()
        self.skip: set[str] = set()

    def compile(self, program: ProgramFile, side: str):
        if program.key in self.fail:
            raise AlignmentError("program_compile_failed", f"{program.key} ({side}): boom")
        return self.artifacts[program.key]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _module_text(marker: str) -> str:
    return f"format: rulespec/v1\nrules:\n  - name: rule_{marker}\n"


def make_tree(root: Path, *, edits: dict[str, str] | None = None) -> Path:
    for index, rel in enumerate(
        (M_BENEFIT, M_BASE, M_RATES, M_ORPHAN, M_NOSUITE, M_MANUAL, M_UNREACHED, M_HARNESS, M_UNBOUND_SUITE)
    ):
        _write(root / rel, _module_text(str(index)))
    _write(root / "us/statutes/9/100.test.yaml", "cases: []\n")
    _write(root / "programs/us-zz/demo/fy-2026.yaml", "program: us-zz/demo\noutputs:\n  - benefit\n")
    _write(
        root / "programs/us-zz/nosuite/fy-2026.yaml",
        "program: us-zz/nosuite\noutputs:\n  - other_amount\n",
    )
    _write(
        root / "programs/us-zz/manual/fy-2026.yaml",
        "program: us-zz/manual\noutputs:\n  - manual_amount\n",
    )
    for rel, text in (edits or {}).items():
        _write(root / rel, text)
    return root


def _suite_yaml(name: str, *, ci: str | None, program: str | None, extra: str = "") -> str:
    lines = [f"name: {name}"]
    if ci is not None:
        lines.append(f"ci: {ci}")
    lines += ["runner:", "  type: axiom-oracles-compare", "  parameters:", "    left: axiom"]
    if program:
        lines.append(f"    axiom_program: $HOME/rulespec-us/{program}")
        lines += ["    concepts:", f"      - {CONCEPT}" if "demo" in program else "      - manual_amount"]
    return "\n".join(lines) + "\n" + extra


def make_registry(root: Path, *, demo_ci: str | None = None, dispositions: dict | None = None) -> Path:
    _write(
        root / "comparisons/zz-demo.yaml",
        _suite_yaml("zz-demo", ci=demo_ci, program="programs/us-zz/demo/fy-2026.yaml"),
    )
    _write(
        root / "comparisons/zz-manual.yaml",
        _suite_yaml("zz-manual", ci="manual", program="programs/us-zz/manual/fy-2026.yaml"),
    )
    _write(
        root / "comparisons/zz-unbound.yaml",
        _suite_yaml("zz-unbound", ci="manual", program=None, extra="# reads us:statutes/9/800\n"),
    )
    _write(root / "comparisons/not-a-suite.yaml", "schema: other\nsuites: []\n")
    _write(root / "axiom_oracles/bridges/demo_bridge.py", 'IMPORTS = ["us:statutes/9/900"]\n')
    if dispositions is not None:
        _write(root / "dispositions/zz-demo.yaml", yaml.safe_dump(dispositions, sort_keys=False))
    commit(root)
    return root


def commit(root: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
            check=True,
            capture_output=True,
        )

    if not (root / ".git").exists():
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    git("add", "-A")
    git("commit", "-q", "--allow-empty", "-m", "fixture")


def artifacts() -> dict[str, dict]:
    return {
        P_DEMO: demo_artifact(),
        P_NOSUITE: single_rule_artifact("us:statutes/9/400", "other_amount"),
        P_MANUAL: single_rule_artifact("us:statutes/9/500", "manual_amount"),
    }


def case(case_id: str, state: str, concepts: tuple[str, ...] = (CONCEPT,)) -> dict:
    row = {
        "case_id": case_id,
        "left_errors": [],
        "right_errors": [],
        "matches": [],
        "mismatches": [],
    }
    if state == "match":
        row["matches"] = [{"concept": CONCEPT, "left": 10, "right": 10}]
    elif state == "mismatch":
        row["mismatches"] = [
            {"concept": concept, "kind": "amount_difference", "left": 10, "right": 12}
            for concept in concepts
        ]
    elif state == "error":
        row["left_errors"] = ["missing input"]
    return row


def suite_report(states: dict[str, object], sha: str, *, suite: str = "zz-demo") -> dict:
    cases = []
    for case_id, state in states.items():
        if isinstance(state, tuple):
            cases.append(case(case_id, state[0], state[1]))
        else:
            cases.append(case(case_id, str(state)))
    mismatches = [
        {**row, "case_id": c["case_id"]} for c in cases for row in c["mismatches"]
    ]
    return {
        "suite": suite,
        "case_count": len(cases),
        "cases": cases,
        "mismatches": mismatches,
        "provenance": {"rulespecs": [{"repo": "TheAxiomFoundation/rulespec-us", "sha": sha}]},
    }


class FakeExecutor:
    def __init__(self, base: dict | None, candidate: dict | None) -> None:
        self.reports = {"base": base, "candidate": candidate}
        self.calls: list[tuple[str, str]] = []

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


@pytest.fixture
def world(tmp_path):
    """``run(changed_module, ...)`` builds the trees and returns the report."""

    def run(
        changed: str | list[str] | None = M_BENEFIT,
        *,
        demo_ci: str | None = None,
        dispositions: dict | None = None,
        executor=None,
        compiler: FakeCompiler | None = None,
        explicit: bool = False,
        registry_edit=None,
        candidate_edit=None,
    ) -> dict:
        index = len(list(tmp_path.iterdir()))
        home = tmp_path / f"run{index}"
        base = make_tree(home / "base" / "rulespec-us")
        paths = [changed] if isinstance(changed, str) else list(changed or [])
        edits = {
            rel: (
                "program: us-zz/demo\noutputs:\n  - benefit\n# rewired\n"
                if rel.startswith("programs/")
                else _module_text("changed")
            )
            for rel in paths
        }
        candidate = make_tree(home / "candidate" / "rulespec-us", edits=edits)
        if candidate_edit:
            candidate_edit(candidate)
        registry = make_registry(home / "registry", demo_ci=demo_ci, dispositions=dispositions)
        if registry_edit:
            registry_edit(registry)
            commit(registry)
        inputs = AlignmentInputs(
            base_root=base,
            candidate_root=candidate,
            registry_root=registry,
            compiler=compiler or FakeCompiler(artifacts()),
            changed=paths if explicit else None,
            executor=executor,
            base_sha=BASE_SHA,
            candidate_sha=CANDIDATE_SHA,
            include_registry_programs=False,
        )
        return build_report(inputs)

    return run


def reaching(report: dict, path: str) -> list[str]:
    row = next(r for r in report["reach"] if r["path"] == path)
    return [hit["program"] for hit in row["reaching_programs"]]


# ---------------------------------------------------------------------------
# Reach
# ---------------------------------------------------------------------------


def test_classify_path():
    assert classify_path("programs/us-az/snap/fy-2026.yaml") == ("program", None)
    assert classify_path("us-az/policies/des/faa5/x/block-8.yaml") == (
        "module",
        "us-az:policies/des/faa5/x/block-8",
    )
    assert classify_path("us-az/policies/des/faa5/x/block-8.test.yaml") == ("other", None)
    assert classify_path("tools/check.py") == ("other", None)
    assert classify_path("README.yaml") == ("other", None)


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


def test_program_file_change_reaches_its_own_program(world):
    report = world("programs/us-zz/demo/fy-2026.yaml")
    hit = report["reach"][0]["reaching_programs"][0]
    assert (hit["program"], hit["via"]) == (P_DEMO, "program_file")
    assert [s["suite"] for s in report["expected_suites"]] == ["zz-demo"]


def test_companion_test_file_has_no_reach_of_its_own(world):
    report = world("us/statutes/9/100.test.yaml")
    assert report["reach"][0]["kind"] == "other"
    assert report["status"] == "no_reference"


def test_reach_on_one_side_only_still_counts(world):
    """A candidate that unwires a module was still reached on base."""

    class SideCompiler(FakeCompiler):
        def compile(self, program, side):
            if program.key == P_DEMO and side == "candidate":
                return single_rule_artifact("us:statutes/9/100", "benefit")
            return super().compile(program, side)

    report = world(M_BASE, compiler=SideCompiler(artifacts()))
    hit = report["reach"][0]["reaching_programs"][0]
    assert hit["sides"] == ["base"]
    assert report["status"] == "reference_not_executed"


class CountingCompiler(FakeCompiler):
    """Reports composed imports, so identical-input compiles can be reused."""

    def __init__(self, artifacts):
        super().__init__(artifacts)
        self.calls = []

    def compile(self, program, side):
        self.calls.append((program.key, side))
        return {**super().compile(program, side), "composed_imports": []}

    def candidate_calls(self):
        return sorted(key for key, side in self.calls if side == "candidate")


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
    report = world(M_ORPHAN, compiler=compiler)
    assert compiler.candidate_calls() == [P_DEMO]

    # A program file changes: that program is recompiled.
    compiler = CountingCompiler(artifacts())
    world("programs/us-zz/demo/fy-2026.yaml", compiler=compiler)
    assert compiler.candidate_calls() == [P_DEMO]

    # A module that a compiled module names (an import) changes.
    compiler = CountingCompiler(artifacts())

    def importing(candidate: Path) -> None:
        _write(candidate / M_NOSUITE, "imports:\n  - us-zz:policies/manual/page\n")

    world(M_UNREACHED, compiler=compiler, candidate_edit=importing)
    assert compiler.candidate_calls() == [P_NOSUITE]


def test_new_file_in_an_imported_directory_forces_a_recompile(world):
    compiler = CountingCompiler(artifacts())

    def add(candidate: Path) -> None:
        _write(candidate / "us/statutes/9/100/extra.yaml", _module_text("new"))

    world(M_UNREACHED, compiler=compiler, candidate_edit=add)
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


def test_persistent_cache_is_bound_to_inputs_and_toolchain(tmp_path):
    from axiom_oracles.alignment import CompileCache, TreeIndex, compile_programs, discover_programs

    root = make_tree(tmp_path / "rulespec-us")
    programs = {"base": discover_programs(root, "rulespec-us"), "candidate": []}
    trees = {"base": TreeIndex(root)}

    def run(salt):
        compiler = CountingCompiler(artifacts())
        compile_programs(
            programs, compiler, trees=trees, cache=CompileCache(tmp_path / "cache", salt=salt)
        )
        return len(compiler.calls)

    assert run("toolchain-a") == 3
    assert run("toolchain-a") == 0
    assert run("toolchain-b") == 3
    _write(root / M_BENEFIT, _module_text("edited"))
    trees["base"] = TreeIndex(root)
    assert run("toolchain-a") == 1


def test_tree_diff_and_explicit_list_agree(world):
    assert world(M_BASE)["reach"] == world(M_BASE, explicit=True)["reach"]


def test_explicit_changed_file_must_differ(tmp_path):
    base = make_tree(tmp_path / "b")
    candidate = make_tree(tmp_path / "c")
    with pytest.raises(AlignmentError) as excinfo:
        changed_files(base, candidate, [M_BASE])
    assert excinfo.value.cause == "changed_file_unchanged"


def test_provenance(world):
    report = world(M_BASE)
    provenance = report["provenance"]
    assert len(provenance["registry_commit"]) == 40
    assert provenance["registry_dirty"] is False
    assert provenance["rulespec_commit"] == {"base": BASE_SHA, "candidate": CANDIDATE_SHA}
    assert provenance["tool_version"].endswith("+derivation.1")
    assert set(provenance["compiled_programs"]["candidate"]) == {P_DEMO, P_NOSUITE, P_MANUAL}
    assert all(len(v) == 64 for v in provenance["compiled_programs"]["base"].values())
    (changed,) = provenance["changed_files"]
    assert changed["path"] == M_BASE
    assert changed["base_sha256"] != changed["candidate_sha256"]
    assert len(changed["candidate_sha256"]) == 64
    assert report["report_only"] is True


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


def test_orphan_rule_in_a_suite_program_is_no_reference(world):
    report = world(M_ORPHAN)
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


def test_unbound_suite_naming_the_module_is_expected(world):
    report = world(M_UNBOUND_SUITE)
    (suite,) = report["expected_suites"]
    assert (suite["suite"], suite["binding"], suite["mode"]) == (
        "zz-unbound",
        "module_reference",
        "manual",
    )
    assert report["status"] == "reference_not_runnable"


def test_runner_source_suite_is_expected_for_its_jurisdiction_only(world, monkeypatch):
    monkeypatch.setitem(
        alignment.RUNNER_SOURCES, "zz-bridge-compare", ("axiom_oracles/bridges/zz_bridge.py",)
    )

    def edit(registry: Path) -> None:
        # Two adjacent literals, as a long path is written in bridge sources.
        _write(
            registry / "axiom_oracles/bridges/zz_bridge.py",
            'A = Path(\n    "us-zz/policies/manual/"\n    "page.yaml"\n)\n'
            'B = Path("us-yy/policies/manual/page.yaml")\n',
        )
        for name, jurisdiction in (("zz-bridge", "us-zz"), ("yy-bridge", "us-yy")):
            _write(
                registry / f"comparisons/{name}.yaml",
                f"name: {name}\nci: snap-qc-replay\nrunner:\n  type: zz-bridge-compare\n"
                f"  parameters:\n    jurisdiction: {jurisdiction}\n",
            )

    report = world(M_UNREACHED, registry_edit=edit)
    (suite,) = report["expected_suites"]
    assert (suite["suite"], suite["binding"], suite["mode"]) == (
        "zz-bridge",
        "runner_source_reference",
        "runnable",
    )
    assert report["status"] == "reference_not_executed"


def test_harness_reference_by_file_path(world):
    def edit(registry: Path) -> None:
        _write(
            registry / "scripts/some_runner.py",
            'PROGRAM = "us-zz/policies/manual/page.test.yaml"\n',
        )

    assert_error(world(M_UNREACHED, registry_edit=edit), "reach_incomplete_harness_reference")


def test_suite_registry_counts(world):
    report = world(M_BENEFIT)
    assert report["suite_registry"] == {
        "suites": 3,
        "runnable": 1,
        "manual": 2,
        "program_bound": 2,
    }


# ---------------------------------------------------------------------------
# Status: errors are never no_reference
# ---------------------------------------------------------------------------


def assert_error(report: dict, cause: str) -> None:
    assert report["status"] == "error", report
    assert report["error"]["cause"] == cause, report["error"]
    assert "reason" not in report
    assert exit_code(report) == 2


def test_compile_failure_is_an_error_not_no_reference(world):
    compiler = FakeCompiler(artifacts())
    compiler.fail = {P_DEMO}
    # Without the failed program nothing would reach this module.
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
    def edit(candidate: Path) -> None:
        _write(candidate / "programs/us-zz/nosuite/fy-2026.yaml", "program: us-zz/nosuite\n")

    assert_error(world(M_UNREACHED, candidate_edit=edit), "program_without_outputs")


@pytest.mark.parametrize(
    "breakage, cause",
    [
        (lambda r: (r / "comparisons/zz-demo.yaml").write_text("name: [unclosed\n"), "registry_unreadable"),
        (lambda r: (r / "comparisons/zz-demo.yaml").write_text("- a\n- b\n"), "registry_unreadable"),
        (
            lambda r: (r / "comparisons/zz-copy.yaml").write_text(
                (r / "comparisons/zz-demo.yaml").read_text()
            ),
            "registry_unreadable",
        ),
        (
            lambda r: (r / "comparisons/zz-demo.yaml").write_text("name: zz-demo\nrunner: {}\n"),
            "registry_unreadable",
        ),
        (
            lambda r: (r / "comparisons/zz-demo.yaml").write_text(
                "name: zz-demo\nci: [manual]\nrunner:\n  type: x\n"
            ),
            "registry_unreadable",
        ),
    ],
)
def test_unreadable_registry_is_an_error(world, breakage, cause):
    assert_error(world(M_UNREACHED, registry_edit=breakage), cause)


def test_missing_registry_is_an_error(tmp_path):
    with pytest.raises(AlignmentError) as excinfo:
        load_suites(tmp_path)
    assert excinfo.value.cause == "registry_unreadable"
    (tmp_path / "comparisons").mkdir()
    with pytest.raises(AlignmentError) as excinfo:
        load_suites(tmp_path)
    assert excinfo.value.cause == "registry_unreadable"


def test_registry_that_is_not_a_checkout_is_an_error(tmp_path):
    base = make_tree(tmp_path / "base" / "rulespec-us")
    candidate = make_tree(
        tmp_path / "candidate" / "rulespec-us", edits={M_UNREACHED: _module_text("changed")}
    )
    registry = tmp_path / "registry"
    _write(registry / "comparisons/zz-demo.yaml", _suite_yaml("zz-demo", ci=None, program=None))
    report = build_report(
        AlignmentInputs(
            base_root=base,
            candidate_root=candidate,
            registry_root=registry,
            compiler=FakeCompiler(artifacts()),
            include_registry_programs=False,
        )
    )
    assert_error(report, "registry_unreadable")


def test_identical_trees_are_an_error(world):
    assert_error(world(None), "no_changed_files")


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


def test_count_check_compares_files_found_with_programs_compiled(tmp_path):
    root = make_tree(tmp_path / "rulespec-us")
    programs = {"base": alignment.discover_programs(root, "rulespec-us"), "candidate": []}
    compiled, counts = alignment.compile_programs(programs, FakeCompiler(artifacts()))
    assert counts["base"]["program_files_found"] == counts["base"]["programs_compiled"] == 3
    del compiled["base"][P_DEMO]
    with pytest.raises(AlignmentError) as excinfo:
        alignment._count_check(programs, compiled)
    assert excinfo.value.cause == "program_count_mismatch"


def test_harness_reference_blocks_no_reference(world):
    """A module a bridge names outside every program file may be compiled by
    a suite this report cannot bind; that is unknown, not ``no_reference``."""
    report = world(M_HARNESS)
    assert_error(report, "reach_incomplete_harness_reference")
    assert report["harness_references"]["hits"] == {
        "us:statutes/9/900": ["axiom_oracles/bridges/demo_bridge.py"]
    }


def test_harness_reference_through_an_importing_module(world):
    def edit(candidate: Path) -> None:
        _write(candidate / M_HARNESS, "imports:\n  - us-zz:policies/manual/page\n")

    # Only the page is listed as changed; the bridge-named module imports it.
    report = world(M_UNREACHED, candidate_edit=edit, explicit=True)
    assert_error(report, "reach_incomplete_harness_reference")
    assert list(report["harness_references"]["hits"]) == ["us:statutes/9/900"]


def test_internal_failure_is_an_error(world, monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(alignment, "compute_reach", explode)
    assert_error(world(M_UNREACHED), "internal_error")


# ---------------------------------------------------------------------------
# Status: aligned / regressed
# ---------------------------------------------------------------------------

ALL_MATCH = {"a": "match", "b": "match", "c": "mismatch", "d": "match"}


def run_executed(world, base_states, candidate_states, **kwargs):
    executor = FakeExecutor(
        suite_report(base_states, BASE_SHA), suite_report(candidate_states, CANDIDATE_SHA)
    )
    return world(M_BENEFIT, executor=executor, **kwargs)


def test_aligned_when_no_case_regresses(world):
    report = run_executed(world, ALL_MATCH, {**ALL_MATCH, "c": "match"})
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
    assert exit_code(report) == 0


def test_aligned_when_nothing_changes(world):
    report = run_executed(world, ALL_MATCH, ALL_MATCH)
    assert report["status"] == "aligned"
    assert report["counts"]["matched_before"] == report["counts"]["matched_after"] == 3


def test_regressed_when_a_matching_case_mismatches(world):
    report = run_executed(world, ALL_MATCH, {**ALL_MATCH, "a": "mismatch"})
    assert report["status"] == "regressed"
    assert report["regressed_suites"] == ["zz-demo"]
    assert report["counts"]["newly_mismatched"] == 1
    assert report["counts"]["matched_after"] == 2
    assert report["executions"][0]["regressions"] == [
        {"case_id": "a", "kind": "newly_mismatched", "concepts": [CONCEPT]}
    ]
    assert exit_code(report) == 0  # report only


def test_one_regression_is_not_offset_by_new_matches(world):
    report = run_executed(world, ALL_MATCH, {**ALL_MATCH, "a": "mismatch", "c": "match"})
    assert report["status"] == "regressed"
    assert report["counts"]["matched_before"] == report["counts"]["matched_after"] == 3


def test_disposition_that_selects_the_case_keeps_it_aligned(world):
    report = run_executed(
        world,
        ALL_MATCH,
        {**ALL_MATCH, "a": "mismatch"},
        dispositions=disposition_file(["a"]),
    )
    assert report["status"] == "aligned"
    assert report["counts"]["newly_mismatched"] == 1
    assert report["counts"]["dispositioned"] == 1


def test_disposition_that_selects_another_case_does_not_hide_a_regression(world):
    report = run_executed(
        world,
        ALL_MATCH,
        {**ALL_MATCH, "a": "mismatch"},
        dispositions=disposition_file(["c"]),
    )
    assert report["status"] == "regressed"
    assert report["counts"]["dispositioned"] == 0


def test_disposition_for_another_concept_does_not_hide_a_regression(world):
    report = run_executed(
        world,
        ALL_MATCH,
        {**ALL_MATCH, "a": "mismatch"},
        dispositions=disposition_file(["a"], concept="us:statutes/9/100#other"),
    )
    assert report["status"] == "regressed"


def test_disposition_must_select_every_new_mismatch_row_of_the_case(world):
    both = ("mismatch", (CONCEPT, "us:statutes/9/100#second"))
    report = run_executed(
        world, ALL_MATCH, {**ALL_MATCH, "a": both}, dispositions=disposition_file(["a"])
    )
    assert report["status"] == "regressed"


def test_newly_errored_case_is_a_regression(world):
    report = run_executed(
        world, ALL_MATCH, {**ALL_MATCH, "a": "error"}, dispositions=disposition_file(["a"])
    )
    assert report["status"] == "regressed"
    assert report["counts"]["newly_errored"] == 1


def test_new_mismatching_output_in_an_already_mismatched_case_is_a_regression(world):
    both = ("mismatch", (CONCEPT, "us:statutes/9/100#second"))
    report = run_executed(world, ALL_MATCH, {**ALL_MATCH, "c": both})
    assert report["status"] == "regressed"
    assert report["counts"]["newly_mismatched"] == 0
    assert report["counts"]["newly_mismatched_outputs_in_mismatched_cases"] == 1


def test_error_to_match_is_newly_matched(world):
    report = run_executed(world, {**ALL_MATCH, "a": "error"}, ALL_MATCH)
    assert report["status"] == "aligned"
    assert report["counts"]["newly_matched"] == 1


def test_invalid_dispositions_file_is_an_error(world):
    bad = disposition_file(["a"])
    bad["schema"] = "something.else"
    assert_error(
        run_executed(world, ALL_MATCH, ALL_MATCH, dispositions=bad), "dispositions_unreadable"
    )


# --- execution failures ----------------------------------------------------


def test_zero_cases_is_an_error(world):
    assert_error(run_executed(world, ALL_MATCH, {}), "zero_cases")
    assert_error(run_executed(world, {}, {}), "zero_cases")


def test_case_count_difference_is_an_error(world):
    fewer = {k: v for k, v in ALL_MATCH.items() if k != "c"}
    assert_error(run_executed(world, ALL_MATCH, fewer), "case_count_differs")


def test_different_case_ids_are_an_error(world):
    renamed = {("z" if k == "c" else k): v for k, v in ALL_MATCH.items()}
    assert_error(run_executed(world, ALL_MATCH, renamed), "case_ids_differ")


def test_suite_run_failure_is_an_error(world):
    executor = FakeExecutor(
        suite_report(ALL_MATCH, BASE_SHA), AlignmentError("suite_run_failed", "exit 1")
    )
    assert_error(world(M_BENEFIT, executor=executor), "suite_run_failed")


def test_timeout_is_an_error(world):
    executor = FakeExecutor(AlignmentError("timeout", "suite zz-demo (base)"), None)
    assert_error(world(M_BENEFIT, executor=executor), "timeout")


def test_reemitted_report_is_an_error(world):
    candidate = suite_report(ALL_MATCH, CANDIDATE_SHA)
    candidate["provenance"]["reemitted_report"] = True
    executor = FakeExecutor(suite_report(ALL_MATCH, BASE_SHA), candidate)
    assert_error(world(M_BENEFIT, executor=executor), "suite_run_failed")


def test_report_for_another_commit_is_an_error(world):
    executor = FakeExecutor(suite_report(ALL_MATCH, BASE_SHA), suite_report(ALL_MATCH, BASE_SHA))
    assert_error(world(M_BENEFIT, executor=executor), "suite_report_provenance_mismatch")


def test_truncated_report_is_an_error(world):
    candidate = suite_report(ALL_MATCH, CANDIDATE_SHA)
    candidate["case_count"] = 40
    executor = FakeExecutor(suite_report(ALL_MATCH, BASE_SHA), candidate)
    assert_error(world(M_BENEFIT, executor=executor), "suite_report_truncated")


def test_report_for_another_suite_is_an_error(world):
    executor = FakeExecutor(
        suite_report(ALL_MATCH, BASE_SHA),
        suite_report(ALL_MATCH, CANDIDATE_SHA, suite="zz-other"),
    )
    assert_error(world(M_BENEFIT, executor=executor), "suite_run_failed")


def test_case_that_compared_nothing_is_an_error(world):
    assert_error(run_executed(world, ALL_MATCH, {**ALL_MATCH, "a": "empty"}), "suite_run_failed")


def test_compare_needs_both_commits():
    report = suite_report(ALL_MATCH, BASE_SHA)
    with pytest.raises(AlignmentError) as excinfo:
        compare_suite_reports("zz-demo", report, report, expected_sha={"base": BASE_SHA})
    assert excinfo.value.cause == "side_commit_unknown"


# --- derive_status in isolation --------------------------------------------


def _expected(name: str, mode: str) -> dict:
    return {"suite": name, "mode": mode}


def _execution(name: str, status: str) -> dict:
    return {"suite": name, "status": status, "counts": {"cases": 1}}


def test_derive_status_requires_every_runnable_suite_executed():
    expected = [_expected("a", "runnable"), _expected("b", "runnable")]
    with pytest.raises(AlignmentError) as excinfo:
        derive_status([], expected, {}, [_execution("a", "aligned")])
    assert excinfo.value.cause == "suite_run_incomplete"


def test_derive_status_one_regressed_suite_regresses_the_change():
    expected = [_expected("a", "runnable"), _expected("b", "runnable"), _expected("m", "manual")]
    result = derive_status(
        [], expected, {}, [_execution("a", "aligned"), _execution("b", "regressed")]
    )
    assert result["status"] == "regressed"
    assert result["regressed_suites"] == ["b"]
    assert result["manual_suites_not_run"] == ["m"]
    assert result["counts"] == {"cases": 2}


def test_derive_status_rejects_an_execution_without_a_result():
    with pytest.raises(AlignmentError) as excinfo:
        derive_status([], [_expected("a", "runnable")], {}, [_execution("a", "error")])
    assert excinfo.value.cause == "suite_run_failed"


def test_derive_status_harness_hits_do_not_override_an_expected_suite():
    result = derive_status([], [_expected("m", "manual")], {"us:x/y": ["f.py"]}, None)
    assert result["status"] == "reference_not_runnable"


# ---------------------------------------------------------------------------
# CLI and the real registry
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
    base = make_tree(tmp_path / "base" / "rulespec-us")
    candidate = make_tree(
        tmp_path / "candidate" / "rulespec-us", edits={M_BASE: _module_text("changed")}
    )
    registry = make_registry(tmp_path / "registry")
    _write_compiled(tmp_path / "compiled")
    reports = tmp_path / "reports"
    _write(reports / "base/zz-demo.json", json.dumps(suite_report(ALL_MATCH, BASE_SHA)))
    _write(
        reports / "candidate/zz-demo.json",
        json.dumps(suite_report({**ALL_MATCH, "b": "mismatch"}, CANDIDATE_SHA)),
    )
    common = [
        "--base-root", str(base),
        "--candidate-root", str(candidate),
        "--registry-root", str(registry),
        "--compiled-dir", str(tmp_path / "compiled"),
        "--no-registry-programs",
        "--base-sha", BASE_SHA,
        "--candidate-sha", CANDIDATE_SHA,
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

    result = _cli(*common, "--quiet")
    assert result.returncode == 0 and result.stdout == ""

    (tmp_path / "compiled/candidate/rulespec-us/programs/us-zz/demo/fy-2026.yaml.json").unlink()
    result = _cli(*common)
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert (report["status"], report["error"]["cause"]) == ("error", "program_compile_failed")


def test_cli_rejects_an_incomplete_tree_choice(tmp_path):
    assert _cli("--base-root", str(tmp_path)).returncode == 2


def test_real_registry_loads_and_every_suite_has_a_mode():
    suites = load_suites(REPO_ROOT)
    assert len(suites) > 100
    assert {suite.mode for suite in suites} == {"runnable", "manual"}
    by_name = {suite.name: suite for suite in suites}
    az = by_name["az-snap-ecps"]
    assert az.program_key == "rulespec-us:programs/us-az/snap/fy-2026.yaml"
    assert by_name["az-tanf-ecps"].program_key == "axiom-oracles:programs/us-az/tanf/fy-2026.yaml"
    assert by_name["ssi-ecps"].program_key == "axiom-oracles:programs/us/ssi/fy-2026.yaml"
    assert by_name["uk-universal-credit-efrs"].program_key is None
    # SNAP QC suites compile a state composition module named in the bridge.
    for name, jurisdiction in (("az-snap-qc", "us-az"), ("co-snap-qc", "us-co")):
        suite = by_name[name]
        assert (suite.program_key, suite.binding) == (None, "runner_source_reference")
        assert suite.mode == "runnable"
        assert suite.module_literals
        assert {m.split(":", 1)[0] for m in suite.module_literals} == {jurisdiction}
        assert any("fy-2026-benefit-calculation" in m for m in suite.module_literals)
    for suite in suites:
        if suite.mode == "manual":
            assert suite.ci == "manual"
