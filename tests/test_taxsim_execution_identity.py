"""Preflight and repeated observations describe the executable that runs."""

from __future__ import annotations

import hashlib
import os
import platform
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles import cli
from axiom_oracles.adapters.taxsim import TaxsimLawYearError, TaxsimPackageRunner, pins
from axiom_oracles.adapters.taxsim import runner as runner_module
from axiom_oracles.core.case import Case

FIXTURES = Path(__file__).parent / "fixtures" / "taxsim"


def _native_runner(monkeypatch, input_path):
    """Keep the upstream source-layout fallback when no path is supplied."""

    class NativeRunner:
        def __init__(self, frame, taxsim_path=None):
            self.input_df = frame
            self.taxsim_path = (
                taxsim_path or Path("resources") / pins.platform_binary_key()
            )

        def _create_taxsim_input_file(self, frame):
            frame.to_csv(input_path, index=False)
            return str(input_path)

    original = runner_module.import_module
    monkeypatch.setattr(
        runner_module,
        "import_module",
        lambda name: (
            SimpleNamespace(TaxsimRunner=NativeRunner)
            if name in {"policyengine_taxsim", "policyengine_taxsim.runners"}
            else original(name)
        ),
    )


@pytest.mark.skipif(os.name == "nt", reason="uses a POSIX shell script")
def test_cli_preflight_accepts_the_source_layout_binary_that_runs(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(pins, "installed_binary_path", lambda system=None: None)
    binary = Path("resources/taxsimtest/taxsimtest-linux.exe")
    binary.parent.mkdir(parents=True)
    binary.write_text(
        '#!/bin/sh\n# "cdate-20260521"\ncat >/dev/null\n'
        "printf 'taxsimid,year,fiitax,\"cdate-20260521\"\\n1,2026,42,0\\n'\n"
    )
    binary.chmod(0o755)
    _native_runner(monkeypatch, tmp_path / "input.csv")
    adapter = TaxsimPackageRunner()
    case = Case(
        case_id="source-case",
        period="2026",
        metadata={"taxsim_input": {"taxsimid": 1, "year": 2026}},
    )
    [result] = adapter.run_cases([case], variables=["fiitax"])
    assert result.values == {"fiitax": 42.0}
    assert not result.errors
    # Linux's static pin stops at 2024, but this actual binary is unpinned.
    cli._require_taxsim_law_year("2026")
    checked = pins.require_law_years([2026])
    assert checked["sha256"] == pins.sha256_file(binary)
    assert checked["pinned"] is False
    assert checked["law_years"] is None
    [recorded] = adapter.taxsim_identity()["binaries"]
    assert Path(recorded["path"]).resolve() == Path(checked["path"]).resolve()
    assert recorded["sha256"] == checked["sha256"]


@settings(max_examples=100, deadline=None)
@given(
    system=st.sampled_from(["linux", "darwin", "windows"]),
    installed=st.booleans(),
    pinned=st.booleans(),
    first=st.integers(1900, 2000),
    last=st.integers(2001, 2050),
    year=st.integers(1850, 2100),
)
def test_preflight_uses_the_selected_files_hash_and_range(
    tmp_path_factory, system, installed, pinned, first, last, year
):
    """Only the selected file's known hash can impose a pinned year range."""
    root = tmp_path_factory.mktemp("source-resolution")
    source = root / "resources" / pins.platform_binary_key(system)
    source.parent.mkdir(parents=True)
    source.write_bytes(b'"cdate-source"')
    share = root / "share-binary"
    share.write_bytes(b'"cdate-installed"')
    selected = share if installed else source
    digest = hashlib.sha256(selected.read_bytes()).hexdigest()
    entry = {
        "sha256": digest,
        "build": "cdate-selected",
        "law_years": {"first": first, "last": last},
    }
    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(root)
        patch.setattr(platform, "system", lambda: system)
        patch.setattr(
            pins,
            "installed_binary_path",
            lambda system=None: share if installed else None,
        )
        patch.setattr(
            pins,
            "pinned_entry_for_sha",
            lambda sha: ("selected", entry) if pinned and sha == digest else None,
        )
        _native_runner(patch, root / "input.csv")
        adapter = TaxsimPackageRunner()
        actual = adapter._runner_factory()(pd.DataFrame()).taxsim_path
        assert Path(actual).resolve() == selected.resolve()
        if pinned and not first <= year <= last:
            with pytest.raises(TaxsimLawYearError, match=f"{first}-{last} only"):
                pins.require_law_years([year])
        else:
            identity = pins.require_law_years([year])
            assert identity["sha256"] == digest
            assert Path(identity["path"]).resolve() == Path(actual).resolve()
            assert identity["pinned"] == pinned
            assert identity["law_years"] == (
                {"first": first, "last": last} if pinned else None
            )


def _cases(stem):
    return [
        Case(
            case_id=str(row["taxsimid"]),
            period=str(row["year"]),
            metadata={"taxsim_input": row},
        )
        for row in pd.read_csv(FIXTURES / f"{stem}_input.csv").to_dict(orient="records")
    ]


def _run_both_modes(adapter, order):
    total = 0
    for stem in order:
        cases = _cases(stem)
        results = adapter.run_cases(cases, variables=["fiitax", "siitax"])
        assert len(results) == len(cases)
        assert all(not result.errors for result in results)
        total += len(cases)
    [binary] = adapter.taxsim_identity()["binaries"]
    assert binary["rows"] == total
    assert pins.same_build(binary["build"], binary["build_observed"])


@pytest.mark.skipif(os.name == "nt", reason="uses a POSIX shell script")
@pytest.mark.parametrize("reverse", [False, True])
def test_one_runner_accepts_csv_and_verbose_from_one_unchanged_binary(
    tmp_path, monkeypatch, reverse
):
    binary = tmp_path / "taxsim"
    binary.write_text(
        '#!/bin/sh\n# "cdate-20260521"\n'
        'if awk -F, \'NR==1 {for(i=1;i<=NF;i++) if($i=="idtl") col=i} '
        "NR==2 {exit ($col == 5 ? 0 : 1)}'; "
        f'then cat "{FIXTURES / "california_idtl5_stdout.txt"}"; '
        f'else cat "{FIXTURES / "utah_elderly_idtl2_stdout.txt"}"; fi\n'
    )
    binary.chmod(0o755)
    monkeypatch.setattr(pins, "installed_binary_path", lambda system=None: binary)
    _native_runner(monkeypatch, tmp_path / "input.csv")
    before = pins.sha256_file(binary)
    order = ["utah_elderly_idtl2", "california_idtl5"]
    _run_both_modes(TaxsimPackageRunner(), order[::-1] if reverse else order)
    assert pins.sha256_file(binary) == before


@settings(max_examples=100, deadline=None)
@given(
    digits=st.integers(0, 9_999_999_999),
    observations=st.lists(
        st.tuples(st.booleans(), st.integers(0, 5000)), min_size=2, max_size=12
    ),
)
def test_equivalent_printed_stamps_preserve_one_build_and_its_row_count(
    tmp_path_factory, digits, observations
):
    binary = tmp_path_factory.mktemp("stamp-modes") / "taxsim"
    stamp = f"cd{digits:010d}"
    binary.write_bytes(f'"{stamp}"'.encode())
    recorder = pins.TaxsimIdentityRecorder()
    digest = pins.sha256_file(binary)
    # Always cross spellings once, then vary order and batch sizes.
    batches = [(False, 1), (True, 1), *observations]
    for verbose, rows in batches:
        recorder.observe(
            binary,
            rows=rows,
            build_observed=f"{digits:010d}" if verbose else stamp,
            sha256=digest,
        )
    [identity] = recorder.binaries()
    assert identity["sha256"] == digest
    assert identity["rows"] == sum(rows for _, rows in batches)
    assert pins.same_build(identity["build"], identity["build_observed"])


def test_pinned_macos_binary_accepts_both_modes_on_one_runner():
    binary = pins.installed_binary_path()
    if platform.system().lower() != "darwin" or binary is None:
        pytest.skip("requires the pinned macOS executable and upstream formatter")
    if (
        pins.sha256_file(binary)
        != pins.bundled_binaries()["taxsimtest/taxsimtest-osx.exe"]["sha256"]
    ):
        pytest.skip("installed executable is not the pinned macOS binary")
    pytest.importorskip("policyengine_taxsim")
    before = pins.sha256_file(binary)
    _run_both_modes(TaxsimPackageRunner(), ["utah_elderly_idtl2", "california_idtl5"])
    assert pins.sha256_file(binary) == before


@pytest.mark.skipif(os.name == "nt", reason="uses a POSIX shell script")
def test_upstream_source_layout_runner_agrees_with_preflight(tmp_path, monkeypatch):
    pytest.importorskip("policyengine_taxsim")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(pins, "installed_binary_path", lambda system=None: None)
    binary = Path("resources/taxsimtest/taxsimtest-linux.exe")
    binary.parent.mkdir(parents=True)
    binary.write_text(
        '#!/bin/sh\n# "cdate-20260521"\ncat >/dev/null\n'
        "printf 'taxsimid,year,fiitax,\"cdate-20260521\"\\n1,2026,42,0\\n'\n"
    )
    binary.chmod(0o755)
    adapter = TaxsimPackageRunner()
    execution = adapter._execute_binary(pd.DataFrame([{"taxsimid": 1, "year": 2026}]))
    assert execution.returncode == 0
    assert Path(execution.binary).resolve() == binary.resolve()
    cli._require_taxsim_law_year("2026")
    assert pins.require_law_years([2026])["sha256"] == pins.sha256_file(binary)
