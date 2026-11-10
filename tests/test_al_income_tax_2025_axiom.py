"""Execution-boundary tests; no Alabama tax law is implemented here."""

import hashlib
import tempfile
from pathlib import Path

import pandas as pd
import pytest
import yaml

from axiom_oracles.core.results import EngineResult
from axiom_oracles.suites import al_income_tax_2025_axiom as lane


@pytest.fixture
def inputs():
    households = pd.DataFrame(
        {
            "taxsimid": [88052, 88053],
            "year": [2025, 2025],
            "state": [1, 1],
            "mstat": [1, 2],
            "pwages": [10000.0, 20000.0],
            "depx": [0, 1],
            "age1": [None, 8],
        }
    ).set_index("taxsimid")
    frame = pd.DataFrame(index=households.index)
    for feed in ("pe", "taxsim"):
        for suffix, values in {
            "v10": [10000.0, 20000.0],
            "niit": [3.0, 4.0],
            "v25": [50.0, 60.0],
            "actc": [70.0, 80.0],
            "fiitax": [90.0, 100.0],
            "v36": [999.0, 888.0],
        }.items():
            frame[f"{feed}_raw_{suffix}"] = values
    frame["pe_sidecar_income_tax_before_refundable_credits"] = [111.0, 222.0]
    frame["pe_sidecar_american_opportunity_credit"] = [333.0, 444.0]
    return households, frame


def _module(tmp_path):
    root = tmp_path / "rulespec-us"
    module = root / lane.MODULE_PATH
    module.parent.mkdir(parents=True)
    module.write_text("format: rulespec/v1\nrules: []\n")
    return root


def _complete_form_inputs(frame):
    for feed in ("pe", "taxsim"):
        for index, field in enumerate(lane.FEDERAL_FIELDS):
            frame[f"{feed}_federal_{field}"] = [index + 1.0, index + 2.0]
            frame[f"{feed}_federal_{field}_status"] = "verified_form_line"


def test_absent_module_preserves_missing_form_lines_and_null_outputs(inputs, tmp_path):
    households, frame = inputs
    scratch = tmp_path / "unused-scratch"
    result = lane.evaluate_axiom_legs(
        households,
        frame,
        rulespec_root=tmp_path / "absent",
        scratch_dir=scratch,
    )
    assert not scratch.exists()
    for leg in result.values():
        assert leg["status"] == "pending_module"
        assert leg["module_path"] == lane.MODULE_PATH.as_posix()
        assert leg["compiled"] is False
        for case in leg["cases"]:
            assert all(value is None for value in case["outputs"].values())
            assert case["unavailable_inputs"] == [
                "form_1040_line_22",
                "form_1040_line_29",
                "form_1040_line_30",
                "schedule_3_line_13a",
            ]
            assert case["federal_inputs"]["form_1040_line_22"] is None
            assert case["federal_inputs"]["form_1040_line_29"] is None
    pe_case = result["pe_federal"]["cases"][0]
    assert pe_case["federal_inputs"]["form_1040_line_27a"] == 50
    assert pe_case["federal_input_sources"]["form_8960_line_17"] == "pe_raw_niit"


def test_candidate_form_inputs_do_not_certify_missing_amounts(inputs, tmp_path):
    households, frame = inputs
    for feed in ("pe", "taxsim"):
        for field in lane.FEDERAL_FIELDS:
            frame[f"{feed}_federal_{field}"] = 0.0
        frame[f"{feed}_federal_status"] = "incomplete_candidate_crosswalk"
    result = lane.evaluate_axiom_legs(
        households,
        frame,
        rulespec_root=tmp_path / "absent",
        scratch_dir=tmp_path,
    )
    assert (
        result["taxsim_federal"]["cases"][0]["federal_inputs"]["form_1040_line_22"]
        is None
    )


def test_present_module_compiles_but_incomplete_inputs_are_not_run(
    inputs, tmp_path, monkeypatch
):
    households, frame = inputs
    root = _module(tmp_path)
    compiled = []

    def compile_only(root, scratch):
        compiled.append((root, scratch))

        class NoEvaluation:
            def run_cases(self, *args, **kwargs):
                pytest.fail("Incomplete federal inputs must not reach the engine")

        return NoEvaluation()

    monkeypatch.setattr(lane, "_compile", compile_only)
    result = lane.evaluate_axiom_legs(
        households,
        frame,
        rulespec_root=root,
        scratch_dir=tmp_path / "scratch",
    )
    assert len(compiled) == 1
    for leg in result.values():
        assert leg["status"] == "unavailable_input"
        assert leg["compiled"] is True
        assert leg["evaluated_households"] == 0
        assert all(case["outputs"]["liability"] is None for case in leg["cases"])


def test_present_module_runs_both_feeds_and_joins_results_by_id(
    inputs, tmp_path, monkeypatch
):
    households, frame = inputs
    _complete_form_inputs(frame)
    frame["taxsim_federal_form_1040_line_22"] = [301.0, 302.0]
    root = _module(tmp_path)
    calls = []
    original_tempdir = tempfile.tempdir

    class Runner:
        def run_cases(self, cases, outputs):
            assert Path(tempfile.gettempdir()).is_relative_to(tmp_path / "scratch")
            assert outputs == list(lane.RULESPEC_OUTPUTS.values())
            for case in cases:
                data = case.metadata["axiom_inputs"]
                assert case.period == "2025"
                assert (
                    data[f"{lane.MODULE}#input.taxsim_pwages"]
                    == households.loc[case.case_id, "pwages"]
                )
                assert not any(
                    "v36" in name or "taxable_income" in name for name in data
                )
                assert (
                    data[f"{lane.MODULE}#input.filing_status"]
                    == households.loc[case.case_id, "mstat"]
                )
            assert (
                f"{lane.MODULE}#input.taxsim_age1"
                not in cases[0].metadata["axiom_inputs"]
            )
            calls.append(cases)
            # Arbitrary engine-stub values test routing, not legal expectations.
            return [
                EngineResult(
                    engine="axiom",
                    household_id=case.case_id,
                    values={output: float(case.case_id) for output in outputs},
                )
                for case in reversed(cases)
            ]

    monkeypatch.setattr(lane, "_compile", lambda root, scratch: Runner())
    result = lane.evaluate_axiom_legs(
        households,
        frame,
        rulespec_root=root,
        scratch_dir=tmp_path / "scratch",
    )
    assert tempfile.tempdir == original_tempdir
    assert len(calls) == 2
    input_name = f"{lane.MODULE}#input.form_1040_line_22"
    assert calls[0][0].metadata["axiom_inputs"][input_name] == 1
    assert calls[1][0].metadata["axiom_inputs"][input_name] == 301
    for leg in result.values():
        assert leg["status"] == "evaluated"
        assert leg["evaluated_households"] == 2
        assert [case["outputs"]["liability"] for case in leg["cases"]] == [88052, 88053]


def test_compile_stages_canonical_root_and_uses_engine_compat(tmp_path, monkeypatch):
    root = _module(tmp_path)
    (root / "tools").mkdir()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    observed = []

    def compile_stub(binary, program, artifact, **kwargs):
        observed.append((binary, program, artifact, kwargs))
        document = yaml.safe_load(program.read_text())
        assert document["module"]["kind"] == "composition"
        assert document["imports"] == [lane.MODULE]
        staged = kwargs["roots"][0]
        assert staged.name == "rulespec-us"
        assert (staged / lane.MODULE_PATH).is_file()
        assert not (staged / "tools").exists()
        assert kwargs["composed"] is True
        artifact.write_text("{}")

    monkeypatch.setattr(lane, "compile_with_engine", compile_stub)
    runner = lane._compile(root, scratch)
    assert len(observed) == 1
    assert runner.compiled_artifact_path.is_file()


def test_compile_failure_is_not_reported_as_pending(inputs, tmp_path, monkeypatch):
    households, frame = inputs
    root = _module(tmp_path)

    def fail(root, scratch):
        raise RuntimeError("synthetic compiler failure")

    monkeypatch.setattr(lane, "_compile", fail)
    result = lane.evaluate_axiom_legs(
        households,
        frame,
        rulespec_root=root,
        scratch_dir=tmp_path / "scratch",
    )
    assert all(leg["status"] == "compile_error" for leg in result.values())
    assert all(leg["reason"] == "synthetic compiler failure" for leg in result.values())


def test_engine_identity_and_failed_outputs_remain_explicit(
    inputs, tmp_path, monkeypatch
):
    households, frame = inputs
    _complete_form_inputs(frame)
    root = _module(tmp_path)
    executable = tmp_path / "fake-engine"
    executable.write_bytes(b"synthetic engine identity")

    class Runner:
        binary_path = executable

        def run_cases(self, cases, outputs):
            return [
                EngineResult(
                    engine="axiom",
                    household_id=case.case_id,
                    values={output: "not a number" for output in outputs},
                    errors=("synthetic engine output failure",),
                )
                for case in cases
            ]

    monkeypatch.setattr(lane, "_compile", lambda root, scratch: Runner())
    result = lane.evaluate_axiom_legs(
        households,
        frame,
        rulespec_root=root,
        scratch_dir=tmp_path / "scratch",
    )
    for leg in result.values():
        assert leg["engine_binary"] == {
            "path": str(executable.resolve()),
            "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        }
        assert leg["status"] == "execution_error"
        assert leg["evaluated_households"] == 0
        for case in leg["cases"]:
            assert case["status"] == "execution_error"
            assert all(value is None for value in case["outputs"].values())
            assert "synthetic engine output failure" in case["errors"]
