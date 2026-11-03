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
  lets the hash check run (and fail on tampering) without a full install;
* validate schema v2's ``binaries`` and ``profiles`` (always), and read the
  build stamp of, and run pe-taxsim's documented golden probe on, every
  profile binary whose verified bytes are on this host.

The dev-only ``test`` CI job installs neither policyengine-taxsim nor any
TAXSIM executable, so the binary tests skip there. The ``taxsim-pin`` job
installs the taxsim extra, fetches every profile's Linux binaries and sets
``AXIOM_TAXSIM_REQUIRE_BINARIES=1``, which turns the profile-binary skips
into failures.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import math
import os
import re
import subprocess
import zipfile
from pathlib import Path

import pytest

from axiom_oracles.adapters.taxsim import pins
from axiom_oracles.adapters.taxsim.projection import (
    _TAXSIM_STATE_CODES,
    TAXSIM_MAX_YEAR,
)
from axiom_oracles.cli import TAXSIM_DEFAULT_PERIOD

REQUIRE_BINARIES = os.environ.get("AXIOM_TAXSIM_REQUIRE_BINARIES") == "1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_WHEEL_BINARY_PREFIX = (
    "policyengine_taxsim-{version}.data/data/share/policyengine_taxsim/"
)


def test_pin_document_structure() -> None:
    doc = pins.load_pins()
    assert doc["schema_version"] == "axiom-oracles/taxsim-pin/v2"

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
        # The years the executable was run on bracket the edge of its range.
        assert all(years["first"] <= year <= years["last"] for year in years["ran"])
        assert all(not years["first"] <= year <= years["last"] for year in years["rejected"])
        assert years["last"] in years["ran"], name
        assert years["last"] + 1 in years["rejected"], name


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


# --------------------------------------------------------------------------
# Schema v2: pinned binaries and profiles



# External ground truth for the dashboard profile: the September 2026
# PolicyEngine TAXSIM dashboard metadata (policyengine-taxsim
# dashboard/public/data/<year>/summary_<year>.json) records
# taxsimBinarySha256 8aa880ae... for every year and taxsimFallback
# {states: [GA, MD], years: [2024, 2025], sha256: 00a321d2...} for 2024/2025.
DASHBOARD_LINUX_SHA = "8aa880aeea33fd501f669d42125615e3b2a0ab19c17d93a76457e9de16615059"
DASHBOARD_FALLBACK_LINUX_SHA = (
    "00a321d2467ba011992f8b83c6e485a9b710c48fca4262a23fec1de26942a89b"
)
V1_PIN_LINUX_SHA = "0d934f202541f43a7999907b523e5431183a1258dadef4ddc6121d3f31120442"


def _skip_or_fail(reason: str) -> None:
    if REQUIRE_BINARIES:
        pytest.fail(f"{reason} (AXIOM_TAXSIM_REQUIRE_BINARIES=1)")
    pytest.skip(reason)


def _host_platform() -> str | None:
    try:
        return pins.normalize_platform()
    except pins.TaxsimPinError:
        return None


# --------------------------------------------------------------------------
# Document structure



def test_pin_document_validates() -> None:
    assert pins.validate_pin_document(pins.load_pins()) == []
    doc = pins.pin_document()
    assert doc.default_profile in doc.profiles



def test_every_profile_resolves_to_pinned_binaries_on_every_claimed_platform() -> None:
    raw = pins.load_pins()
    binaries = raw["binaries"]
    for name, profile in raw["profiles"].items():
        claimed = set(profile["binaries"])
        assert claimed, name
        for system, sha in profile["binaries"].items():
            assert binaries[sha]["platform"] == system, (name, system)
        for override in profile["overrides"]:
            assert set(override["binaries"]) == claimed, (name, override["id"])
            for system, sha in override["binaries"].items():
                assert binaries[sha]["platform"] == system, (name, override["id"])


def test_override_state_codes_agree_with_projection_crosswalk() -> None:
    usps_by_code = {code: usps for usps, code in _TAXSIM_STATE_CODES.items()}
    for profile in pins.load_pins()["profiles"].values():
        for override in profile["overrides"]:
            assert [usps_by_code[code] for code in override["states"]] == (
                override["state_postal"]
            )


def test_every_binary_has_a_fetchable_pinned_source() -> None:
    for sha, meta in pins.load_pins()["binaries"].items():
        kinds = [source["kind"] for source in meta["sources"]]
        assert "git" in kinds, sha
        for source in meta["sources"]:
            if source["kind"] == "git":
                assert re.fullmatch(r"[0-9a-f]{40}", source["commit"]), sha
                assert source["path"].endswith(meta["filename"]), sha


def test_dashboard_profile_matches_dashboard_metadata() -> None:
    doc = pins.pin_document()
    profile = doc.profiles["dashboard-2026-09"]
    assert profile.binaries["linux"] == DASHBOARD_LINUX_SHA
    (override,) = profile.overrides
    assert override.id == "ga-md-2024-2025-sigfpe"
    assert override.states == frozenset({11, 21})
    assert override.years == frozenset({2024, 2025})
    assert override.binaries["linux"] == DASHBOARD_FALLBACK_LINUX_SHA
    raw_override = pins.load_pins()["profiles"]["dashboard-2026-09"]["overrides"][0]
    assert raw_override["linked_issue"].endswith("/issues/1214")
    # The dashboard's own metadata, pinned to a commit (#1215 closed unmerged).
    assert raw_override["source"].endswith(
        "/blob/9c987d8f23955dd1564af43dee3fac4054c0dbf2/"
        "dashboard/public/data/2024/summary_2024.json"
    )


def test_default_profile_is_the_policyengine_taxsim_2_30_0_binaries() -> None:
    """The default stays the 2.30.0 wheel's binaries, the v1 pin's executables."""
    assert pins.pin_document().default_profile == "policyengine-taxsim-2.30.0"
    assert pins.pinned_version() == "2.30.0"
    profile = pins.pin_document().profiles["policyengine-taxsim-2.30.0"]
    bundled = pins.bundled_binaries()
    for system, sha in profile.binaries.items():
        assert bundled[pins.platform_binary_key(system)]["sha256"] == sha


def test_legacy_profile_keeps_the_v1_pinned_binaries() -> None:
    profile = pins.pin_document().profiles["policyengine-taxsim-2.30.0"]
    assert profile.binaries == {
        "linux": V1_PIN_LINUX_SHA,
        "darwin": "0d9e43a983055d44eec9e5de7edfc933fa061b2a336716d760fe98abf4336319",
        "windows": "92e011693cbfd45634fe57a041e31099926246bddaad20b5143485ffac9297cb",
    }
    assert profile.overrides == ()


def test_bundled_binaries_that_are_pinned_carry_a_matching_wheel_source() -> None:
    raw = pins.load_pins()
    dist = raw["distribution"]
    prefix = _WHEEL_BINARY_PREFIX.format(version=dist["version"])
    for key, meta in raw["bundled_binaries"].items():
        pinned = raw["binaries"].get(meta["sha256"])
        if pinned is None:
            continue
        assert pinned["bytes"] == meta["bytes"], key
        wheel_sources = [
            source
            for source in pinned["sources"]
            if source["kind"] == "wheel" and source["version"] == dist["version"]
        ]
        assert wheel_sources, key
        for source in wheel_sources:
            assert source["member"] == prefix + key
            assert source["sha256"] == dist["wheel"]["sha256"]


def test_probe_results_reference_declared_probes() -> None:
    raw = pins.load_pins()
    for sha, meta in raw["binaries"].items():
        for result in meta.get("probe_results", []):
            assert result["probe"] in raw["probes"], sha
            assert result["evidence"]["kind"] in {"documented", "computed"}


def _mutated(mutate) -> list[str]:
    doc = copy.deepcopy(pins.load_pins())
    mutate(doc)
    return pins.validate_pin_document(doc)


def test_validator_rejects_wrong_postal_code() -> None:
    def mutate(doc):
        doc["profiles"]["dashboard-2026-09"]["overrides"][0]["state_postal"] = [
            "GA",
            "MA",
        ]

    assert any("not 'MA'" in error for error in _mutated(mutate))


def test_validator_rejects_unpinned_and_cross_platform_references() -> None:
    def unpinned(doc):
        doc["profiles"]["pe-taxsim-main-2026-08"]["binaries"]["linux"] = "0" * 64

    def cross_platform(doc):
        doc["profiles"]["pe-taxsim-main-2026-08"]["binaries"]["darwin"] = (
            DASHBOARD_LINUX_SHA
        )

    assert any("is not a pinned binary" in e for e in _mutated(unpinned))
    assert any("pinned as a 'linux' binary" in e for e in _mutated(cross_platform))


def test_validator_rejects_missing_default_overlaps_and_partial_overrides() -> None:
    def missing_default(doc):
        doc["default_profile"] = "no-such-profile"

    def overlap(doc):
        overrides = doc["profiles"]["dashboard-2026-09"]["overrides"]
        clone = copy.deepcopy(overrides[0])
        clone["id"] = "second"
        clone["states"], clone["state_postal"], clone["years"] = [21], ["MD"], [2025]
        overrides.append(clone)

    def partial(doc):
        del doc["profiles"]["dashboard-2026-09"]["overrides"][0]["binaries"]["darwin"]

    def bad_schema(doc):
        doc["schema_version"] = "axiom-oracles/taxsim-pin/v1"

    assert any("default_profile" in e for e in _mutated(missing_default))
    assert any("already claimed" in e for e in _mutated(overlap))
    assert any("same platforms" in e for e in _mutated(partial))
    assert any("schema_version" in e for e in _mutated(bad_schema))
    with pytest.raises(pins.TaxsimPinError):
        doc = copy.deepcopy(pins.load_pins())
        doc["default_profile"] = "nope"
        pins.parse_pin_document(doc)




def _host_binaries() -> list[str]:
    host = _host_platform()
    if host is None:
        return []
    return [
        sha
        for sha, binary in pins.pin_document().binaries.items()
        if binary.platform == host
    ]


def _binary_id(sha: str) -> str:
    return f"{sha[:12]}-{pins.pin_document().binaries[sha].build}"


def _verified_or_skip(sha: str) -> Path:
    path = pins.find_verified_binary(sha)
    if path is None:
        binary = pins.pinned_binary(sha)
        _skip_or_fail(
            f"TAXSIM binary {sha} ({binary.platform}, build {binary.build}) is "
            f"not present; run `{pins.FETCH_COMMAND} --all-profiles --platform "
            f"{binary.platform}`"
        )
    return path


def _run_probe(binary: Path, probe: dict, tmp_path: Path) -> tuple[list[str], dict]:
    input_file = tmp_path / "probe.csv"
    output_file = tmp_path / "probe.out"
    input_file.write_text(
        ",".join(probe["columns"])
        + "\n"
        + ",".join(str(value) for value in probe["values"])
        + "\n"
    )
    assert binary.is_absolute()
    with input_file.open("rb") as stdin, output_file.open("wb") as stdout:
        process = subprocess.run(
            [str(binary)], stdin=stdin, stdout=stdout, stderr=subprocess.PIPE
        )
    assert process.returncode == 0, process.stderr.decode(errors="replace")
    rows = list(csv.reader(io.StringIO(output_file.read_text())))
    header = [column.strip().strip('"') for column in rows[0]]
    values = dict(zip(header, (value.strip() for value in rows[1]), strict=False))
    return header, values


@pytest.mark.parametrize("sha", _host_binaries(), ids=_binary_id)
def test_pinned_binary_embeds_its_pinned_build_stamp(sha: str) -> None:
    path = _verified_or_skip(sha)
    assert pins.same_build(pins.read_build_stamp(path), pins.pinned_binary(sha).build)


@pytest.mark.skipif(_host_platform() == "windows", reason="POSIX probe harness")
@pytest.mark.parametrize("sha", _host_binaries(), ids=_binary_id)
def test_golden_probe_executes_pinned_binary(sha: str, tmp_path: Path) -> None:
    """Execute the binary on pe-taxsim's canonical VA 2021 opt(30) record.

    The output header's build stamp must equal the pin, and every
    *documented* expectation recorded for this exact binary must hold.
    Binaries without documented values (and ``computed`` observations) are
    only required to run and return a finite siitax.
    """
    path = _verified_or_skip(sha)
    binary = pins.pinned_binary(sha)
    probes = pins.pin_document().probes
    header, values = _run_probe(path, probes["va-2021-opt30"], tmp_path)
    assert pins.same_build(header[-1], binary.build)
    assert math.isfinite(float(values["siitax"]))
    for result in binary.probe_results:
        if result["evidence"]["kind"] != "documented":
            continue
        probe_header, probe_values = (
            (header, values)
            if result["probe"] == "va-2021-opt30"
            else _run_probe(path, probes[result["probe"]], tmp_path)
        )
        del probe_header
        for column, expected in result["expect"].items():
            assert float(probe_values[column]) == pytest.approx(expected, abs=0.005), (
                f"{column} on {sha} ({binary.build}); evidence: "
                f"{result['evidence']['ref']}"
            )



SEPTEMBER_COMMIT = "c245a3eb92e412bc2beb5b0ffaf909ecc36d7a18"
EARLIER_PR_1206_HEAD = "997311aad2ee883d5ebf0d10c9082a902ab17e03"


def _september_builds() -> dict[str, dict]:
    return {
        sha: meta
        for sha, meta in pins.load_pins()["binaries"].items()
        if meta["build"] in {"cd2026090910", "cd2026090110"}
    }


def test_september_builds_name_the_branch_commit_first() -> None:
    """The September builds no longer live on #1206's head; the branch that
    bundles them is tried first, the earlier #1206 head second."""
    builds = _september_builds()
    assert len(builds) == 3
    for sha, meta in builds.items():
        commits = [s["commit"] for s in meta["sources"] if s["kind"] == "git"]
        assert commits == [SEPTEMBER_COMMIT, EARLIER_PR_1206_HEAD], sha
        first = next(s for s in meta["sources"] if s["kind"] == "git")
        assert "codex/refresh-new-taxsim-september" in first["ref"]


@pytest.mark.parametrize("sha", sorted(_september_builds()), ids=lambda sha: sha[:12])
def test_every_september_git_source_serves_the_pinned_bytes(sha: str) -> None:
    """Each pinned git blob of a September build hashes to its pin (network)."""
    if not REQUIRE_BINARIES:
        pytest.skip("downloads pinned blobs; set AXIOM_TAXSIM_REQUIRE_BINARIES=1")
    binary = pins.pinned_binary(sha)
    for source in binary.sources:
        if source["kind"] != "git":
            continue
        url = (
            f"https://raw.githubusercontent.com/{source['repo']}/"
            f"{source['commit']}/{source['path']}"
        )
        assert pins.verify_bytes(binary, pins._http_download(url)) is None, url
