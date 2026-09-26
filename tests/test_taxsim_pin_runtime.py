"""TAXSIM pin runtime: profile selection, resolution, verified lookup, fetch.

Everything here runs against temporary fake binaries and a fake pin document
(no policyengine-taxsim install, no real TAXSIM executable), except the
resolution tests over the committed pin document.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import subprocess
import zipfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from axiom_oracles.adapters.taxsim import pins
from axiom_oracles.cli import cli

SEP_LINUX = "8aa880aeea33fd501f669d42125615e3b2a0ab19c17d93a76457e9de16615059"
AUG_LINUX = "00a321d2467ba011992f8b83c6e485a9b710c48fca4262a23fec1de26942a89b"
V1_LINUX = "0d934f202541f43a7999907b523e5431183a1258dadef4ddc6121d3f31120442"


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch, tmp_path):
    monkeypatch.delenv(pins.PROFILE_ENV, raising=False)
    monkeypatch.delenv(pins.BINARY_DIR_ENV, raising=False)
    monkeypatch.setenv(pins.CACHE_DIR_ENV, str(tmp_path / "cache"))
    monkeypatch.setattr(pins, "installed_binary_path", lambda system=None: None)
    pins.clear_hash_cache()


# --------------------------------------------------------------------------
# Fake pin document


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fake_binaries() -> dict[str, dict[str, bytes]]:
    """vintage -> platform -> bytes. Each embeds a build stamp."""
    stamps = {"new": b'"cd2099010100"', "old": b'"cd2098010100"'}
    return {
        vintage: {
            system: b"#!/bin/sh\n# fake taxsim " + vintage.encode() + b" "
            + system.encode() + b"\n# " + stamp + b"\n"
            for system in pins.PLATFORMS
        }
        for vintage, stamp in stamps.items()
    }


def fake_doc(binaries: dict[str, dict[str, bytes]], *, git_commit: str = "a" * 40):
    real = pins.load_pins()
    doc_binaries = {}
    shas: dict[str, dict[str, str]] = {}
    for vintage, by_platform in binaries.items():
        for system, data in by_platform.items():
            sha = _sha(data)
            shas.setdefault(vintage, {})[system] = sha
            doc_binaries[sha] = {
                "platform": system,
                "build": "cd2099010100" if vintage == "new" else "cd2098010100",
                "bytes": len(data),
                "filename": f"fake-{system}.exe",
                "sources": [
                    {
                        "kind": "git",
                        "repo": "Example/fake-taxsim",
                        "commit": git_commit,
                        "path": f"bin/{vintage}/fake-{system}.exe",
                    }
                ],
            }
    doc = {
        "schema_version": pins.SCHEMA_VERSION,
        "default_profile": "new",
        "distribution": real["distribution"],
        "probes": {},
        "binaries": doc_binaries,
        "profiles": {
            "new": {
                "description": "new everywhere but GA/MD 2024-25",
                "binaries": dict(shas["new"]),
                "overrides": [
                    {
                        "id": "ga-md",
                        "states": [11, 21],
                        "state_postal": ["GA", "MD"],
                        "years": [2024, 2025],
                        "binaries": dict(shas["old"]),
                        "reason": "test",
                        "linked_issue": "https://example.test/1",
                        "source": "https://example.test/2",
                    }
                ],
            },
            "old": {
                "description": "old everywhere",
                "binaries": dict(shas["old"]),
                "overrides": [],
            },
        },
    }
    return doc, shas


def install_doc(monkeypatch, doc) -> pins.PinDocument:
    parsed = pins.parse_pin_document(doc)
    monkeypatch.setattr(pins, "load_pins", lambda: doc)
    monkeypatch.setattr(pins, "pin_document", lambda: parsed)
    return parsed


# --------------------------------------------------------------------------
# Profile selection (C4) and resolution over the committed pins


def test_profile_precedence_explicit_env_suite_default(monkeypatch) -> None:
    suite = {"taxsim_pin_profile": "policyengine-taxsim-2.30.0"}
    assert pins.active_profile() == ("dashboard-2026-09", "default_profile")
    assert pins.active_profile(suite_parameters=suite)[0] == (
        "policyengine-taxsim-2.30.0"
    )
    monkeypatch.setenv(pins.PROFILE_ENV, "pe-taxsim-main-2026-08")
    assert pins.active_profile(suite_parameters=suite) == (
        "pe-taxsim-main-2026-08",
        f"${pins.PROFILE_ENV}",
    )
    assert pins.active_profile("dashboard-2026-09", suite) == (
        "dashboard-2026-09",
        "argument",
    )


def test_unknown_profile_fails_closed_at_every_level(monkeypatch) -> None:
    with pytest.raises(pins.TaxsimPinError, match="declared profiles"):
        pins.active_profile("nope")
    with pytest.raises(pins.TaxsimPinError):
        pins.active_profile(suite_parameters={"taxsim_pin_profile": "nope"})
    monkeypatch.setenv(pins.PROFILE_ENV, "nope")
    with pytest.raises(pins.TaxsimPinError):
        pins.active_profile()


def test_dashboard_override_matches_exactly_ga_md_2024_2025() -> None:
    """Exhaustive: every SOI state 0-51 x years 2019-2027 on every platform."""
    profile = pins.get_profile("dashboard-2026-09")
    for system in pins.PLATFORMS:
        for state in range(0, 52):
            for year in range(2019, 2028):
                resolution = profile.resolve(state, year, system)
                in_override = state in (11, 21) and year in (2024, 2025)
                expected_scope = (
                    "override:ga-md-2024-2025-sigfpe" if in_override else "default"
                )
                assert resolution.scope == expected_scope, (system, state, year)
                expected_sha = (
                    profile.overrides[0].binaries[system]
                    if in_override
                    else profile.binaries[system]
                )
                assert resolution.sha256 == expected_sha


def test_resolve_binary_signature_and_coercion() -> None:
    assert pins.resolve_binary(11, 2024, "linux", "dashboard-2026-09") == AUG_LINUX
    assert pins.resolve_binary(11.0, "2024", "linux", "dashboard-2026-09") == (
        AUG_LINUX
    )
    assert pins.resolve_binary(0, 2024, "linux", "dashboard-2026-09") == SEP_LINUX
    assert pins.resolve_binary(11, 2024, "linux", "pe-taxsim-main-2026-08") == (
        AUG_LINUX
    )
    assert pins.resolve_binary(47, 2021, "linux", "policyengine-taxsim-2.30.0") == (
        V1_LINUX
    )
    with pytest.raises(pins.TaxsimPinError):
        pins.resolve_binary(11.5, 2024, "linux", "dashboard-2026-09")
    with pytest.raises(pins.TaxsimPinError):
        pins.resolve_binary(11, 2024, "plan9", "dashboard-2026-09")


# --------------------------------------------------------------------------
# Verified lookup (fail closed)


def test_missing_binary_raises_naming_sha_profile_cell_and_fetch(monkeypatch) -> None:
    doc, shas = fake_doc(fake_binaries())
    install_doc(monkeypatch, doc)
    sha = shas["old"]["linux"]
    with pytest.raises(pins.TaxsimPinError) as excinfo:
        pins.locate_binary(sha, profile="new", state=11, year=2024)
    message = str(excinfo.value)
    assert sha in message
    assert "'new'" in message
    assert "(state=11, year=2024)" in message
    assert f"{pins.FETCH_COMMAND} --platform linux --profile new" in message
    assert "(absent)" in message


def test_cache_hit_is_verified_and_mismatch_is_refused(monkeypatch) -> None:
    binaries = fake_binaries()
    doc, shas = fake_doc(binaries)
    install_doc(monkeypatch, doc)
    sha = shas["new"]["linux"]
    target = pins.cache_path(sha)
    target.parent.mkdir(parents=True)
    target.write_bytes(binaries["new"]["linux"])
    assert pins.locate_binary(sha) == target

    target.write_bytes(binaries["new"]["linux"] + b"tampered")
    pins.clear_hash_cache()
    with pytest.raises(pins.TaxsimPinError, match="does not match the pin"):
        pins.locate_binary(sha)


def test_env_binary_dir_precedes_cache_and_flat_layout_is_hash_checked(
    monkeypatch, tmp_path
) -> None:
    binaries = fake_binaries()
    doc, shas = fake_doc(binaries)
    install_doc(monkeypatch, doc)
    sha_new, sha_old = shas["new"]["linux"], shas["old"]["linux"]
    for sha, data in ((sha_new, binaries["new"]["linux"]),):
        cached = pins.cache_path(sha)
        cached.parent.mkdir(parents=True)
        cached.write_bytes(data)
    env_dir = tmp_path / "env-bins"
    (env_dir / sha_new).mkdir(parents=True)
    (env_dir / sha_new / "fake-linux.exe").write_bytes(binaries["new"]["linux"])
    # Flat layout holds the NEW bytes under the shared filename.
    (env_dir / "fake-linux.exe").write_bytes(binaries["new"]["linux"])
    monkeypatch.setenv(pins.BINARY_DIR_ENV, str(env_dir))

    assert pins.locate_binary(sha_new) == env_dir / sha_new / "fake-linux.exe"
    # The flat file hashes as NEW, so it can never satisfy OLD.
    with pytest.raises(pins.TaxsimPinError) as excinfo:
        pins.locate_binary(sha_old)
    assert str(env_dir / "fake-linux.exe") in str(excinfo.value)
    assert sha_new in str(excinfo.value)  # the observed (wrong) hash is shown


def test_installed_package_binary_is_used_only_when_its_hash_matches(
    monkeypatch, tmp_path
) -> None:
    binaries = fake_binaries()
    doc, shas = fake_doc(binaries)
    install_doc(monkeypatch, doc)
    host = pins.normalize_platform()
    installed = tmp_path / "share" / "taxsimtest.exe"
    installed.parent.mkdir(parents=True)
    installed.write_bytes(binaries["old"][host])
    monkeypatch.setattr(pins, "installed_binary_path", lambda system=None: installed)
    assert pins.locate_binary(shas["old"][host]) == installed
    with pytest.raises(pins.TaxsimPinError):
        pins.locate_binary(shas["new"][host])


def test_each_binary_is_hashed_once_per_path_mtime_and_size(
    monkeypatch, tmp_path
) -> None:
    calls = []
    real = pins.sha256_file

    def counting(path):
        calls.append(path)
        return real(path)

    monkeypatch.setattr(pins, "sha256_file", counting)
    path = tmp_path / "bin"
    path.write_bytes(b"abc")
    first = pins.cached_sha256(path)
    assert pins.cached_sha256(path) == first
    assert len(calls) == 1
    path.write_bytes(b"abcd")
    os.utime(path, ns=(1, 1))
    assert pins.cached_sha256(path) == _sha(b"abcd")
    assert len(calls) == 2


def test_build_stamp_reader_normalizes_both_stamp_formats() -> None:
    assert pins.build_stamp_from_bytes(b'xx"cdate-20260521"yy') == "20260521"
    assert pins.build_stamp_from_bytes(b'xx"cd2026090910"yy') == "cd2026090910"
    assert pins.build_stamp_from_bytes(b"nothing here cd20260909") is None


# --------------------------------------------------------------------------
# Fetching


def test_fetch_verifies_before_writing_and_tries_sources_in_order(
    monkeypatch,
) -> None:
    binaries = fake_binaries()
    doc, shas = fake_doc(binaries)
    sha = shas["new"]["linux"]
    doc["binaries"][sha]["sources"].append(
        {"kind": "url", "url": "https://example.test/linux", "retrieved_on": "x"}
    )
    install_doc(monkeypatch, doc)
    requested = []

    def download(url: str) -> bytes:
        requested.append(url)
        if "raw.githubusercontent.com" in url:
            return b"<html>404</html>"  # wrong bytes: must not be written
        return binaries["new"]["linux"]

    result = pins.fetch_binary(sha, download=download)
    assert result.status == "fetched"
    assert result.source == "url https://example.test/linux"
    assert requested[0] == (
        "https://raw.githubusercontent.com/Example/fake-taxsim/"
        + "a" * 40
        + "/bin/new/fake-linux.exe"
    )
    assert result.path.read_bytes() == binaries["new"]["linux"]
    assert os.access(result.path, os.X_OK)
    again = pins.fetch_binary(sha, download=download)
    assert again.status == "present"
    assert len(requested) == 2


def test_fetch_never_replaces_cache_with_unverified_bytes(monkeypatch) -> None:
    binaries = fake_binaries()
    doc, shas = fake_doc(binaries)
    install_doc(monkeypatch, doc)
    sha = shas["new"]["linux"]
    target = pins.cache_path(sha)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"corrupt")
    with pytest.raises(pins.TaxsimPinError, match="could not fetch verified bytes"):
        pins.fetch_binary(sha, download=lambda url: b"also wrong")
    assert target.read_bytes() == b"corrupt"
    result = pins.fetch_binary(sha, download=lambda url: binaries["new"]["linux"])
    assert result.status == "fetched"
    assert target.read_bytes() == binaries["new"]["linux"]


def test_fetch_extracts_from_a_verified_wheel(monkeypatch) -> None:
    binaries = fake_binaries()
    doc, shas = fake_doc(binaries)
    sha = shas["old"]["darwin"]
    buffer = io.BytesIO()
    member = "pkg-1.0.data/data/share/taxsimtest/fake-darwin.exe"
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(member, binaries["old"]["darwin"])
    wheel = buffer.getvalue()
    doc["binaries"][sha]["sources"] = [
        {
            "kind": "wheel",
            "package": "pkg",
            "version": "1.0",
            "filename": "pkg-1.0-py3-none-any.whl",
            "sha256": _sha(wheel),
            "bytes": len(wheel),
            "url": "https://example.test/pkg.whl",
            "member": member,
        }
    ]
    install_doc(monkeypatch, doc)
    result = pins.fetch_binary(sha, download=lambda url: wheel)
    assert result.source.startswith("wheel pkg-1.0-py3-none-any.whl!")
    assert result.path.read_bytes() == binaries["old"]["darwin"]

    pins_doc = pins.pin_document()
    tampered = wheel + b"x"
    result.path.unlink()
    with pytest.raises(pins.TaxsimPinError, match="does not match the pinned"):
        pins.fetch_binary(sha, download=lambda url: tampered)
    assert pins_doc.binaries[sha].bytes == len(binaries["old"]["darwin"])


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.test",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.test",
        },
    ).stdout.strip()


def test_fetch_reads_pinned_blobs_from_a_local_git_repo(monkeypatch, tmp_path) -> None:
    binaries = fake_binaries()
    repo = tmp_path / "fake-taxsim"
    repo.mkdir()
    _git(repo, "init", "-q")
    for vintage in ("new", "old"):
        folder = repo / "bin" / vintage
        folder.mkdir(parents=True)
        for system, data in binaries[vintage].items():
            (folder / f"fake-{system}.exe").write_bytes(data)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "binaries")
    commit = _git(repo, "rev-parse", "HEAD")
    doc, shas = fake_doc(binaries, git_commit=commit)
    install_doc(monkeypatch, doc)

    def no_network(url: str) -> bytes:
        raise AssertionError(f"network used: {url}")

    result = pins.fetch_binary(
        shas["old"]["windows"], from_git_repo=repo, download=no_network
    )
    assert result.source.startswith(f"local {repo}@{commit[:12]}")
    assert result.path.read_bytes() == binaries["old"]["windows"]


# --------------------------------------------------------------------------
# CLI


def test_cli_fetch_and_pin_status(monkeypatch) -> None:
    binaries = fake_binaries()
    doc, shas = fake_doc(binaries)
    install_doc(monkeypatch, doc)
    by_sha = {
        _sha(data): data for group in binaries.values() for data in group.values()
    }

    def download(url: str) -> bytes:
        name = url.rsplit("/", 2)
        vintage, filename = name[-2], name[-1]
        system = filename.removeprefix("fake-").removesuffix(".exe")
        return by_sha[shas[vintage][system]]

    monkeypatch.setattr(pins, "_http_download", download)
    runner = CliRunner()
    status = runner.invoke(
        cli, ["taxsim", "pin-status", "--platform", "linux", "--json"]
    )
    assert status.exit_code == 0, status.output
    payload = json.loads(status.output)
    assert payload["active_profile"] == "new"
    assert payload["active_profile_source"] == "default_profile"
    (profile,) = payload["profiles"]
    assert [row["scope"] for row in profile["resolution"]] == [
        "default",
        "override:ga-md",
    ]
    assert {b["status"] for b in profile["binaries"]} == {"missing"}

    fetched = runner.invoke(
        cli, ["taxsim", "fetch-binaries", "--profile", "new", "--platform", "linux"]
    )
    assert fetched.exit_code == 0, fetched.output
    assert fetched.output.count("fetched") == 2

    status = runner.invoke(
        cli, ["taxsim", "pin-status", "--platform", "linux", "--json"]
    )
    payload = json.loads(status.output)
    assert {b["status"] for b in payload["profiles"][0]["binaries"]} == {"verified"}

    everything = runner.invoke(
        cli, ["taxsim", "fetch-binaries", "--all-profiles", "--platform", "all"]
    )
    assert everything.exit_code == 0, everything.output
    assert everything.output.count("present") == 2
    assert everything.output.count("fetched") == 4


def test_cli_fetch_reports_unverifiable_sources(monkeypatch) -> None:
    doc, _ = fake_doc(fake_binaries())
    install_doc(monkeypatch, doc)
    monkeypatch.setattr(pins, "_http_download", lambda url: b"nope")
    result = CliRunner().invoke(
        cli, ["taxsim", "fetch-binaries", "--platform", "linux"]
    )
    assert result.exit_code != 0
    assert "could not fetch verified bytes" in result.output


def test_compare_rejects_unknown_taxsim_pin_profile() -> None:
    result = CliRunner().invoke(
        cli,
        ["compare", "axiom", "taxsim", "--taxsim-pin-profile", "nope"],
    )
    assert result.exit_code != 0
    assert "unknown TAXSIM pin profile 'nope'" in result.output


# --------------------------------------------------------------------------
# run_comparison.py: profile flag and provenance (C1)


def _load_run_comparison():
    module_path = Path(__file__).parents[1] / "scripts" / "run_comparison.py"
    spec = importlib.util.spec_from_file_location("run_comparison", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _taxsim_config(tmp_path: Path, **parameters) -> dict:
    return {
        "name": "fiit-taxsim-ecps",
        "runner": {
            "type": "axiom-oracles-compare",
            "axiom_rules_repo": str(tmp_path / "missing-rules"),
            "parameters": {
                "left": "axiom",
                "right": "taxsim",
                "population": "enhanced-cps",
                **parameters,
            },
        },
    }


def test_provenance_lifts_taxsim_engine_identity(monkeypatch, tmp_path) -> None:
    run_comparison = _load_run_comparison()
    import axiom_oracles.provenance as provenance

    monkeypatch.setattr(provenance, "resolve_rulespec_checkout", lambda slug: None)
    binaries = [
        {
            "sha256": SEP_LINUX,
            "build": "cd2026090910",
            "build_observed": "cd2026090910",
            "platform": "linux",
            "bytes": 2153328,
            "rows": 9,
            "scope": "default",
        },
        {
            "sha256": AUG_LINUX,
            "build": "cd2026081819",
            "build_observed": "cd2026081819",
            "platform": "linux",
            "bytes": 2129624,
            "rows": 1,
            "scope": "override:ga-md-2024-2025-sigfpe",
        },
    ]
    output = tmp_path / "r.json"
    output.write_text(
        json.dumps(
            {
                "suite": "fiit-taxsim-ecps",
                "engine_identity": {
                    "taxsim": {"pin_profile": "dashboard-2026-09", "binaries": binaries}
                },
            }
        )
    )
    block = run_comparison._build_run_provenance(
        _taxsim_config(tmp_path), "axiom-oracles-compare", output
    )
    oracle = block["oracle"]
    assert oracle["name"] == "taxsim"
    assert oracle["policyengine_taxsim"] == pins.pinned_version()
    assert oracle["taxsim_pin_profile"] == "dashboard-2026-09"
    assert oracle["taxsim_binaries"] == binaries
    for item in oracle["taxsim_binaries"]:
        assert set(item) == {
            "sha256",
            "build",
            "build_observed",
            "platform",
            "bytes",
            "rows",
            "scope",
        }


def test_provenance_of_a_legacy_report_keeps_only_the_version(
    monkeypatch, tmp_path
) -> None:
    run_comparison = _load_run_comparison()
    import axiom_oracles.provenance as provenance

    monkeypatch.setattr(provenance, "resolve_rulespec_checkout", lambda slug: None)
    output = tmp_path / "r.json"
    output.write_text(json.dumps({"suite": "fiit-taxsim-ecps"}))
    block = run_comparison._build_run_provenance(
        _taxsim_config(tmp_path), "axiom-oracles-compare", output
    )
    assert block["oracle"]["policyengine_taxsim"] == pins.pinned_version()
    assert "taxsim_binaries" not in block["oracle"]
    assert "taxsim_pin_profile" not in block["oracle"]


def test_run_comparison_passes_the_resolved_profile_to_the_cli(
    monkeypatch, tmp_path
) -> None:
    run_comparison = _load_run_comparison()
    monkeypatch.setattr(
        run_comparison, "_ensure_engine_binary", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        run_comparison, "_ensure_composed_axiom_program", lambda *_a, **_k: None
    )
    calls = []

    def fake_run(cmd, *, check, cwd=None, env=None, stdout=None,
                 capture_output=False, text=False):
        del check, cwd, env, capture_output, text
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(run_comparison.subprocess, "run", fake_run)
    rules = tmp_path / "rules"
    rules.mkdir()

    def run(**parameters):
        run_comparison._run_axiom_oracles_compare(
            {
                "axiom_rules_repo": str(rules),
                "parameters": {
                    "left": "axiom",
                    "right": "taxsim",
                    "concept": "us:tax/federal-income-tax#eitc",
                    "period": "2026",
                    "sample_size": 5,
                    **parameters,
                },
            },
            tmp_path / "out.json",
        )
        cmd = calls[-1]
        return cmd[cmd.index("--taxsim-pin-profile") + 1]

    assert run() == "dashboard-2026-09"
    assert run(taxsim_pin_profile="policyengine-taxsim-2.30.0") == (
        "policyengine-taxsim-2.30.0"
    )
    monkeypatch.setenv(pins.PROFILE_ENV, "pe-taxsim-main-2026-08")
    assert run(taxsim_pin_profile="policyengine-taxsim-2.30.0") == (
        "pe-taxsim-main-2026-08"
    )
    assert f"policyengine-taxsim=={pins.pinned_version()}" in calls[-1]


def test_relative_binary_dir_returns_absolute_verified_path(
    monkeypatch, tmp_path
) -> None:
    """A relative AXIOM_TAXSIM_BINARY_DIR must not yield a bare filename.

    subprocess looks a bare name up on PATH, so a verified relative path
    could execute a different same-named file under the pinned identity.
    """
    binaries = fake_binaries()
    doc, shas = fake_doc(binaries)
    install_doc(monkeypatch, doc)
    sha_new = shas["new"]["linux"]
    (tmp_path / "fake-linux.exe").write_bytes(binaries["new"]["linux"])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(pins.BINARY_DIR_ENV, ".")

    located = pins.locate_binary(sha_new)
    assert located.is_absolute()
    assert located == (tmp_path / "fake-linux.exe").resolve()


def test_execution_refuses_non_absolute_binary(tmp_path) -> None:
    from axiom_oracles.adapters.taxsim import execution

    source = tmp_path / "in.txt"
    source.write_text("taxsimid year state\n")
    with pytest.raises(ValueError, match="non-absolute"):
        execution.execute_taxsim_binary(
            "taxsimtest-linux.exe", source, tmp_path / "out.txt"
        )
