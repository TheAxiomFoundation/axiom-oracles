"""Direct TAXSIM callers attribute rows to the bytes checked before execution."""

from __future__ import annotations

import importlib.util
import io
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from axiom_oracles.adapters.taxsim import TaxsimIdentityError, pins
from axiom_oracles.bridges import state_tax_populace_runner as bridge

pytestmark = pytest.mark.skipif(os.name == "nt", reason="uses a POSIX shell script")


def _write_binary(
    path: Path, *, payload: str = "original", mutate: bool = False, liability: int = 1
):
    path.write_text(
        '#!/bin/sh\n# "cdate-20260521"\n'
        f"# {payload}\n"
        "printf 'taxsimid,siitax,staxbc,cdate-20260521\\n'\n"
        'i=1\nwhile [ "$i" -le "$1" ]; do\n'
        f'  printf "%s,{liability},{liability},0\\n" "$i"\n'
        "  i=$((i + 1))\ndone\n"
        + ('printf "# replaced\\n" >> "$0"\n' if mutate else "")
    )
    path.chmod(0o755)


@pytest.fixture(params=["grid", "populace"])
def direct_call(request, monkeypatch, tmp_path):
    """Exercise each caller through an upstream-compatible runner interface."""
    binary = tmp_path / "executed-taxsim"

    class Runner:
        def __init__(self, frame, taxsim_path=None):
            self.frame = frame
            # The runner's actual path governs provenance, even if its
            # constructor was given a different suggested executable.
            self.taxsim_path = binary

        def run(self, show_progress=False):
            result = subprocess.run(
                [str(self.taxsim_path), str(len(self.frame))],
                capture_output=True,
                text=True,
                check=True,
            )
            return pd.read_csv(io.StringIO(result.stdout))

    if request.param == "grid":
        path = (
            Path(__file__).parents[1] / "scripts/generate_state_income_tax_liability.py"
        )
        spec = importlib.util.spec_from_file_location("_direct_taxsim_grid_test", path)
        assert spec is not None and spec.loader is not None
        generator = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, spec.name, generator)
        spec.loader.exec_module(generator)
        native = ModuleType("policyengine_taxsim.runners.taxsim_runner")
        native.TaxsimRunner = Runner
        monkeypatch.setitem(sys.modules, native.__name__, native)
        monkeypatch.setattr(generator, "_taxsim_binary", lambda: tmp_path / "suggested")
        monkeypatch.setattr(generator, "_taxsim_output_column", lambda state: "siitax")

        def invoke(recorder, rows=1):
            return generator._taxsim_liabilities(
                [
                    generator.Case(f"probe-{i}", "AZ", "single", 30_000)
                    for i in range(rows)
                ],
                recorder,
            )

    else:

        class Simulation:
            def __init__(self, dataset):
                self.rows = dataset

            def calculate(self, variable, period, map_to=None):
                if variable in {"person_id", "tax_unit_id"}:
                    return list(range(1, self.rows + 1))
                value = {
                    "age": 40,
                    "is_tax_unit_head": True,
                    "is_tax_unit_spouse": False,
                    "employment_income": 30_000,
                }.get(variable, 0)
                return [value] * self.rows

        def invoke(recorder, rows=1):
            ids = list(range(1, rows + 1))
            return bridge.calculate_taxsim_targets(
                dataset=rows,
                raw_tax_units=pd.DataFrame({"tax_unit_id": ids}),
                raw_persons=pd.DataFrame({"person_id": ids, "person_tax_unit_id": ids}),
                routes=[
                    bridge.TaxUnitRoute(i, i, "UT", "49", 1, bridge.DISPOSITION_READY)
                    for i in ids
                ],
                year=2026,
                microsimulation_factory=Simulation,
                taxsim_runner_factory=Runner,
                identity_recorder=recorder,
            )

    return binary, invoke


def test_direct_call_rejects_binary_mutation_during_execution(direct_call):
    binary, invoke = direct_call
    _write_binary(binary, mutate=True)
    before = pins.sha256_file(binary)
    recorder = pins.TaxsimIdentityRecorder()

    with pytest.raises(TaxsimIdentityError, match="changed during the run"):
        invoke(recorder)

    assert pins.sha256_file(binary) != before
    assert recorder.to_dict() is None


def test_direct_call_rejects_same_stamp_replacement_between_batches(direct_call):
    binary, invoke = direct_call
    _write_binary(binary)
    recorder = pins.TaxsimIdentityRecorder()
    invoke(recorder)
    first = recorder.binaries()[0]
    _write_binary(binary, payload="replacement")
    assert pins.sha256_file(binary) != first["sha256"]

    with pytest.raises(TaxsimIdentityError, match="changed during the run"):
        invoke(recorder)

    # A rejected replacement contributes no rows to the first executable.
    assert recorder.binaries()[0]["rows"] == 1


def test_direct_call_rejects_later_replacement_after_pre_run_hash(
    direct_call, monkeypatch
):
    binary, invoke = direct_call
    _write_binary(binary)
    recorder = pins.TaxsimIdentityRecorder()
    invoke(recorder)
    original = recorder.binaries()
    executed = []
    published = []
    run = subprocess.run

    def replace_then_run(*args, **kwargs):
        # Both direct callers have captured their pre-run hash at this point.
        _write_binary(binary, payload="replacement", liability=99)
        digest = pins.sha256_file(binary)
        result = run(*args, **kwargs)
        executed.append((digest, pd.read_csv(io.StringIO(result.stdout))))
        return result

    monkeypatch.setattr(subprocess, "run", replace_then_run)
    with pytest.raises(TaxsimIdentityError, match="changed during the run"):
        published.append(invoke(recorder, rows=2))

    [(digest, output)] = executed
    assert digest != original[0]["sha256"]
    assert digest == pins.sha256_file(binary)
    assert output["siitax"].tolist() == [99, 99]
    assert published == []
    assert recorder.binaries() == original


@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    payload=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", max_size=30),
    batches=st.lists(st.integers(min_value=1, max_value=4), min_size=1, max_size=4),
)
def test_direct_call_hash_and_rows_describe_each_execution(
    direct_call, payload, batches
):
    binary, invoke = direct_call
    _write_binary(binary, payload=payload)
    before = pins.sha256_file(binary)
    recorder = pins.TaxsimIdentityRecorder()
    for rows in batches:
        invoke(recorder, rows)

    [identity] = recorder.binaries()
    assert identity["path"] == str(binary)
    assert identity["sha256"] == before == pins.sha256_file(binary)
    assert identity["rows"] == sum(batches)
