"""Verify the pinned TAXSIM binary identity.

Reproducibility of every TAXSIM oracle number depends on the exact bundled
binary. ``taxsim_pins.json`` pins the ``policyengine-taxsim`` release, its PyPI
artifact hashes, and the SHA-256, build stamp and accepted law years of each
bundled executable. These tests:

* validate the pin document's structure and internal consistency (always);
* recompute and compare the installed binary's hash and build stamp when
  ``policyengine-taxsim`` is installed (the ``taxsim`` extra; no CI workflow
  installs it), else skip with a reason;
* run the installed binary at its pinned last law year and the year after,
  and compare what it prints with the pinned build stamp and rejection line;
* recompute against a wheel when ``AXIOM_TAXSIM_WHEEL`` points to one, which
  lets the hash check run (and fail on tampering) without a full install.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import zipfile
from pathlib import Path

import pytest

from axiom_oracles.adapters.taxsim import pins
from axiom_oracles.adapters.taxsim.projection import TAXSIM_MAX_YEAR
from axiom_oracles.cli import TAXSIM_DEFAULT_PERIOD

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_WHEEL_BINARY_PREFIX = (
    "policyengine_taxsim-{version}.data/data/share/policyengine_taxsim/"
)


def test_pin_document_structure() -> None:
    doc = pins.load_pins()
    assert doc["schema_version"] == "axiom-oracles/taxsim-pin/v1"

    dist = doc["distribution"]
    assert dist["package"] == "policyengine-taxsim"
    assert re.fullmatch(r"\d+\.\d+\.\d+", dist["version"])
    for artifact in ("sdist", "wheel"):
        block = dist[artifact]
        assert _SHA256_RE.match(block["sha256"]), artifact
        assert isinstance(block["bytes"], int) and block["bytes"] > 0
        assert block["url"].startswith("https://files.pythonhosted.org/")

    binaries = doc["bundled_binaries"]
    assert binaries, "pin must record at least one bundled binary"
    for name, meta in binaries.items():
        assert name.endswith(".exe"), name
        assert _SHA256_RE.match(meta["sha256"]), name
        assert isinstance(meta["bytes"], int) and meta["bytes"] > 0
        assert re.fullmatch(r"cdate-\S+|cd\d{10}", meta["build"]), name
        assert meta["format"], name
        years = meta["law_years"]
        if years is None:
            continue
        assert isinstance(years["first"], int), name
        assert isinstance(years["last"], int), name
        assert years["first"] <= years["last"], name
        # The rejection line is a verbatim capture: it names the range.
        assert "TAXSIM: Federal tax calculator available" in years["rejection"]
        assert str(years["first"]) in years["rejection"], name
        assert str(years["last"]) in years["rejection"], name
        assert years["evidence"], name


def test_runtime_binary_points_at_pinned_entries() -> None:
    doc = pins.load_pins()
    binaries = doc["bundled_binaries"]
    runtime = doc["runtime_binary"]
    # Every platform's declared runtime binary must be a pinned binary.
    for key in runtime["by_platform"].values():
        assert key in binaries, key
    # The platform map in code agrees with the pin file's declared mapping.
    for system, key in (
        ("linux", "taxsimtest/taxsimtest-linux.exe"),
        ("darwin", "taxsimtest/taxsimtest-osx.exe"),
        ("windows", "taxsimtest/taxsimtest-windows.exe"),
    ):
        assert pins.platform_binary_key(system) == key
        assert runtime["by_platform"][system] == key


def test_adapter_max_year_is_the_last_year_a_pinned_platform_binary_accepts() -> None:
    doc = pins.load_pins()
    lasts = [
        pins.law_year_range(doc["bundled_binaries"][key])[1]
        for key in doc["runtime_binary"]["by_platform"].values()
        if pins.law_year_range(doc["bundled_binaries"][key]) is not None
    ]
    assert TAXSIM_MAX_YEAR == max(lasts)


def test_default_taxsim_period_runs_on_some_pinned_platform() -> None:
    year = int(TAXSIM_DEFAULT_PERIOD.split("-", 1)[0])
    doc = pins.load_pins()
    accepting = [
        system
        for system, key in doc["runtime_binary"]["by_platform"].items()
        if (years := pins.law_year_range(doc["bundled_binaries"][key]))
        and years[0] <= year <= years[1]
    ]
    assert accepting, f"no pinned platform binary accepts the default {year}"


def test_helpers_expose_pinned_version_and_binaries() -> None:
    assert pins.pinned_version() == pins.load_pins()["distribution"]["version"]
    assert pins.bundled_binaries() == pins.load_pins()["bundled_binaries"]


_VERSION_LITERAL_RE = re.compile(r"policyengine-taxsim==(\d+\.\d+\.\d+)")

# Files allowed to carry a versioned policyengine-taxsim literal, checked for
# agreement with the pin. pyproject.toml must declare the dependency; nothing
# else may hardcode a version (#266: a stale 2.21.2 literal in
# run_comparison.py silently regenerated four suites at 2024 law while the
# repo pin said 2.30.0). Runtime code sources the version via
# ``pins.pinned_version()``, which this guard cannot be fooled by.
_ALLOWED_LITERAL_FILES = {"pyproject.toml"}


def test_no_divergent_version_literals() -> None:
    """Every policyengine-taxsim== version literal must match the pin."""
    repo_root = Path(__file__).resolve().parent.parent
    pinned = pins.pinned_version()
    offenders: list[str] = []
    for pattern in ("scripts/*.py", "axiom_oracles/**/*.py", "pyproject.toml"):
        for path in repo_root.glob(pattern):
            rel = path.relative_to(repo_root).as_posix()
            for match in _VERSION_LITERAL_RE.finditer(path.read_text()):
                if rel not in _ALLOWED_LITERAL_FILES:
                    offenders.append(f"{rel}: hardcoded {match.group(0)}")
                elif match.group(1) != pinned:
                    offenders.append(
                        f"{rel}: {match.group(0)} != pinned {pinned}"
                    )
    assert not offenders, (
        "versioned policyengine-taxsim literals must live in pyproject.toml "
        "only and agree with taxsim_pins.json; use "
        "axiom_oracles.adapters.taxsim.pins.pinned_version() elsewhere:\n"
        + "\n".join(offenders)
    )


def _recompute_from_wheel(wheel_path: Path) -> dict[str, dict[str, object]]:
    """Return {pinned-key: {sha256, bytes}} for bundled binaries in a wheel."""
    version = pins.pinned_version()
    prefix = _WHEEL_BINARY_PREFIX.format(version=version)
    found: dict[str, dict[str, object]] = {}
    with zipfile.ZipFile(wheel_path) as zf:
        for info in zf.infolist():
            if not info.filename.startswith(prefix):
                continue
            rel = info.filename[len(prefix) :]
            if not rel.endswith(".exe"):
                continue
            data = zf.read(info.filename)
            found[rel] = {
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "build": pins.build_stamp_from_bytes(data),
            }
    return found


def test_installed_binary_matches_pin() -> None:
    """Recompute the installed TAXSIM binary hash and compare to the pin."""
    key = pins.platform_binary_key()
    if key is None:
        pytest.skip("no pinned TAXSIM binary for this platform")
    path = pins.installed_binary_path()
    if path is None:
        pytest.skip(
            "policyengine-taxsim is not installed; install the 'taxsim' extra "
            "to verify the bundled binary against the pin"
        )
    expected = pins.bundled_binaries()[key]
    actual_sha = pins.sha256_file(path)
    actual_bytes = path.stat().st_size
    assert actual_bytes == expected["bytes"], (
        f"{path} size {actual_bytes} != pinned {expected['bytes']} "
        f"(policyengine-taxsim {pins.pinned_version()} pin is stale)"
    )
    assert actual_sha == expected["sha256"], (
        f"{path} sha256 {actual_sha} != pinned {expected['sha256']} "
        f"(policyengine-taxsim {pins.pinned_version()} pin is stale)"
    )
    assert pins.read_build_stamp(path) == expected["build"]


def _run_installed(path: Path, year: int) -> subprocess.CompletedProcess:
    one_row = f"taxsimid,year,state,mstat,page,pwages,idtl\n1,{year},0,1,40,50000,0\n"
    return subprocess.run(
        [str(path)], input=one_row.encode(), capture_output=True, check=False
    )


def test_installed_binary_behaves_as_pinned_at_its_law_year_edge(tmp_path) -> None:
    """Execute the installed binary: last pinned year runs, the next is refused.

    A differential check of the pin against the executable itself: the CSV
    header must end with the pinned build stamp, and the year after the
    pinned range must print the pinned rejection line, ``STOP 1`` and exit 1.
    """
    key = pins.platform_binary_key()
    path = pins.installed_binary_path()
    if key is None or path is None:
        pytest.skip("policyengine-taxsim is not installed for this platform")
    expected = pins.bundled_binaries()[key]
    if pins.sha256_file(path) != expected["sha256"]:
        pytest.skip("installed binary is not the pinned one (see the hash test)")
    years = pins.law_year_range(expected)
    if years is None:
        pytest.skip(f"{key} has no pinned law-year range")
    if (os.name == "nt") != (key.endswith("windows.exe")):
        pytest.skip("binary does not run on this host")
    # Wheel installs can leave the data file without its execute bit
    # (TaxsimRunner chmods it before use); run an executable copy.
    copy = tmp_path / path.name
    copy.write_bytes(path.read_bytes())
    copy.chmod(0o755)
    path = copy

    accepted = _run_installed(path, years[1])
    assert accepted.returncode == 0, accepted.stdout
    header = accepted.stdout.decode().splitlines()[0]
    assert header.split(",")[-1] == f'"{expected["build"]}"'
    assert pins.build_stamp_from_stdout(accepted.stdout.decode()) == expected["build"]

    rejected = _run_installed(path, years[1] + 1)
    assert rejected.returncode == 1
    assert rejected.stdout.decode().splitlines()[0] == expected["law_years"]["rejection"]
    assert rejected.stderr.decode().strip() == "STOP 1"


def test_wheel_binaries_match_pin_when_wheel_available() -> None:
    """Recompute every bundled binary from a wheel and compare to the pin.

    Runs when ``AXIOM_TAXSIM_WHEEL`` points at the pinned wheel. This is the
    non-vacuous hash check: it reads real bytes and would fail on any hash or
    size drift, without requiring a full package install.
    """
    wheel_env = os.environ.get("AXIOM_TAXSIM_WHEEL")
    if not wheel_env:
        pytest.skip("set AXIOM_TAXSIM_WHEEL to the pinned wheel to run this check")
    wheel_path = Path(wheel_env)
    if not wheel_path.is_file():
        pytest.skip(f"AXIOM_TAXSIM_WHEEL not found: {wheel_path}")

    recomputed = _recompute_from_wheel(wheel_path)
    pinned = pins.bundled_binaries()
    # Every pinned binary must be present in the wheel with a matching hash
    # and the pinned build stamp in its bytes.
    for key, meta in pinned.items():
        assert key in recomputed, f"{key} missing from wheel {wheel_path}"
        assert recomputed[key]["sha256"] == meta["sha256"], key
        assert recomputed[key]["bytes"] == meta["bytes"], key
        assert recomputed[key]["build"] == meta["build"], key
