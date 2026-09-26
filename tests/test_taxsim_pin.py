"""Verify the pinned TAXSIM binary identity (pin schema v2).

Reproducibility of every TAXSIM oracle number depends on the exact executable
that ran. ``taxsim_pins.json`` pins every executable by SHA-256, groups them
into (state, year) profiles, and pins the ``policyengine-taxsim`` package that
wraps them. These tests:

* validate the pin document's structure and internal consistency (always);
* recompute the installed package's bundled binary hash, and every bundled
  binary from a wheel when ``AXIOM_TAXSIM_WHEEL`` points at one;
* read each locally available pinned binary's embedded build stamp and run
  the documented golden probe on it.

Binary-dependent tests skip when the bytes are absent. With
``AXIOM_TAXSIM_REQUIRE_BINARIES=1`` (the CI ``taxsim-pin`` job, which fetches
every profile's Linux binaries first) those skips become failures, so the job
cannot pass by skipping.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import math
import os
import re
import zipfile
from pathlib import Path

import pytest

from axiom_oracles.adapters.taxsim import pins
from axiom_oracles.adapters.taxsim.execution import execute_taxsim_binary
from axiom_oracles.adapters.taxsim.projection import _TAXSIM_STATE_CODES

REQUIRE_BINARIES = os.environ.get("AXIOM_TAXSIM_REQUIRE_BINARIES") == "1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_WHEEL_BINARY_PREFIX = (
    "policyengine_taxsim-{version}.data/data/share/policyengine_taxsim/"
)

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


def test_distribution_block_structure() -> None:
    dist = pins.load_pins()["distribution"]
    assert dist["package"] == "policyengine-taxsim"
    assert re.fullmatch(r"\d+\.\d+\.\d+", dist["version"])
    for artifact in ("sdist", "wheel"):
        block = dist[artifact]
        assert _SHA256_RE.match(block["sha256"]), artifact
        assert isinstance(block["bytes"], int) and block["bytes"] > 0
        assert block["url"].startswith("https://files.pythonhosted.org/")
        assert dist["version"] in block["filename"]
    for system in pins.PLATFORMS:
        key = pins.platform_binary_key(system)
        assert key in dist["bundled_binaries"], key


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
    assert raw_override["source"].endswith("/pull/1215")


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
    for key, meta in dist["bundled_binaries"].items():
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


def test_helpers_expose_pinned_version_and_binaries() -> None:
    assert pins.pinned_version() == pins.load_pins()["distribution"]["version"]
    assert pins.bundled_binaries() == pins.load_pins()["distribution"][
        "bundled_binaries"
    ]


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
    found_pyproject = False
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
                else:
                    found_pyproject = True
    assert not offenders, (
        "versioned policyengine-taxsim literals must live in pyproject.toml "
        "only and agree with taxsim_pins.json; use "
        "axiom_oracles.adapters.taxsim.pins.pinned_version() elsewhere:\n"
        + "\n".join(offenders)
    )
    assert found_pyproject, "pyproject.toml must pin policyengine-taxsim=="


# --------------------------------------------------------------------------
# Package-bundled binaries


def _recompute_from_wheel(wheel_path: Path) -> dict[str, dict[str, object]]:
    """Return {bundled-key: {sha256, bytes}} for bundled binaries in a wheel."""
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
            }
    return found


def test_installed_binary_matches_pin() -> None:
    """Recompute the installed package's bundled binary hash vs the pin."""
    key = pins.platform_binary_key()
    if key is None:
        pytest.skip("no pinned TAXSIM binary for this platform")
    path = pins.installed_binary_path()
    if path is None:
        _skip_or_fail(
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


def test_wheel_binaries_match_pin_when_wheel_available() -> None:
    """Recompute the wheel and every bundled binary from its bytes.

    Runs when ``AXIOM_TAXSIM_WHEEL`` points at the pinned wheel (the CI
    ``taxsim-pin`` job downloads it). It reads real bytes and fails on any
    hash or size drift, without requiring a full package install.
    """
    wheel_env = os.environ.get("AXIOM_TAXSIM_WHEEL")
    if not wheel_env:
        _skip_or_fail("set AXIOM_TAXSIM_WHEEL to the pinned wheel to run this check")
    wheel_path = Path(wheel_env)
    if not wheel_path.is_file():
        _skip_or_fail(f"AXIOM_TAXSIM_WHEEL not found: {wheel_path}")

    wheel = pins.load_pins()["distribution"]["wheel"]
    assert pins.sha256_file(wheel_path) == wheel["sha256"]
    assert wheel_path.stat().st_size == wheel["bytes"]
    recomputed = _recompute_from_wheel(wheel_path)
    for key, meta in pins.bundled_binaries().items():
        assert key in recomputed, f"{key} missing from wheel {wheel_path}"
        assert recomputed[key]["sha256"] == meta["sha256"], key
        assert recomputed[key]["bytes"] == meta["bytes"], key


# --------------------------------------------------------------------------
# Pinned binaries: build stamps and the golden probe


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
    execute_taxsim_binary(binary, input_file, output_file)
    rows = list(csv.reader(io.StringIO(output_file.read_text())))
    header = [column.strip().strip('"') for column in rows[0]]
    values = dict(zip(header, (value.strip() for value in rows[1]), strict=False))
    return header, values


def _normalize_stamp(column: str) -> str:
    return column[len("cdate-") :] if column.startswith("cdate-") else column


@pytest.mark.parametrize("sha", _host_binaries(), ids=_binary_id)
def test_pinned_binary_embeds_its_pinned_build_stamp(sha: str) -> None:
    path = _verified_or_skip(sha)
    assert pins.read_build_stamp(path) == pins.pinned_binary(sha).build


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
    assert _normalize_stamp(header[-1]) == binary.build
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
