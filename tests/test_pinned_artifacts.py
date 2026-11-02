"""The pruned-PolicyEngine artifact table and the check that watches it."""

from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
from pathlib import Path

import pytest
import requests

from axiom_oracles import pinned_artifacts

REPO_ROOT = Path(__file__).resolve().parents[1]
# Captured at import, before tests/conftest.py stubs fetch for every test.
REAL_FETCH = pinned_artifacts.fetch

_HASHED_URL = re.compile(
    r"https://files\.pythonhosted\.org/packages/[0-9a-f]{2}/[0-9a-f]{2}/"
    r"[0-9a-f]{60}/(?P<filename>[^/]+)"
)


def _load_check_module():
    path = REPO_ROOT / "scripts" / "check_pinned_artifacts.py"
    spec = importlib.util.spec_from_file_location("check_pinned_artifacts", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # dataclasses resolves string annotations through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _lock_files(name: str) -> dict[str, tuple[str, str]]:
    """``{version: (wheel url, sha256)}`` for ``name`` in uv.lock."""
    lock = (REPO_ROOT / "uv.lock").read_text()
    out = {}
    for block in lock.split("[[package]]"):
        if f'\nname = "{name}"\n' not in block:
            continue
        version = re.search(r'\nversion = "([^"]+)"', block).group(1)
        wheel = re.search(
            r'\{ url = "([^"]+\.whl)", hash = "sha256:([0-9a-f]{64})"', block
        )
        if wheel:
            out[version] = (wheel.group(1), wheel.group(2))
    return out


def test_table_entries_are_unique_hashed_wheels():
    seen = set()
    for artifact in pinned_artifacts.PRUNED_ARTIFACTS:
        key = (artifact.name, artifact.version)
        assert key not in seen, key
        seen.add(key)
        match = _HASHED_URL.fullmatch(artifact.url)
        assert match, artifact.url
        wheel = artifact.name.replace("-", "_")
        assert match["filename"] == f"{wheel}-{artifact.version}-py3-none-any.whl"
        assert re.fullmatch(r"[0-9a-f]{64}", artifact.sha256)
        assert artifact.recorded_in


# Each pruned release a comparison pins, with the SHA-256 checked against the
# downloaded bytes and the blake2b-256 digest in the URL path when the row was
# added. A row that drifts from these fails here, offline.
EXPECTED_ROWS = {
    "1.700.0": "7633d8aefcaf02d7628f841bc56750606f1d7fe409ff3ae7b0ef7e364a88e945",
    "1.705.1": "9db5121748d62961cb4867f18dab03da1be9abc986676e12e147e19afc6fd6aa",
    "1.729.0": "8d21d3f7c0e82a9415edffe8ea53939330a63d9c8f6bd334299bddb697cf2c00",
    "1.752.2": "7e30468ae369ddd14e5d834c12cacbc5b5159c809b0990caf204c0747ef4c096",
    "1.764.6": "2b2c5c02c26ab212270948db1f30129728b625fc6109fc9ca0c604b714546909",
    "1.767.3": "777be3f3a66cbd266959791b007571a8fce94b1d0c2d13f40f8e991ca106fa6f",
}
EXPECTED_URL_DIGESTS = {
    "1.700.0": "49e92837a0d98e99efaf4d82aade276eee6eeff419df614863f08e3512961d2d",
    "1.705.1": "871d71653e73a243ffb6e74463403b2a198cdea9ce9fa2dab8038d99ad70991b",
    "1.729.0": "b97d778f92ae94997b00c3c9ac34b345f6c9333435f905670ee4eeb2f5e19809",
    "1.752.2": "7f85bbee92f747a382779bae41a67da39fa5a8592d068853a64226279e6c32a7",
    "1.764.6": "e25a0566666f30ad06e416f0cf25b24bdee73acd71897fb2de3c0ac43b59e3e3",
    "1.767.3": "d19eb2685b9ab9639d81a29d7da7fa02619d2e9b916f65ec4ef6d6c9230744a6",
}


def test_table_holds_exactly_the_expected_rows():
    rows = {
        artifact.version: artifact
        for artifact in pinned_artifacts.PRUNED_ARTIFACTS
        if artifact.name == "policyengine-us"
    }
    assert {v: a.sha256 for v, a in rows.items()} == EXPECTED_ROWS
    for version, artifact in rows.items():
        digest = "".join(artifact.url.split("/packages/", 1)[1].split("/")[:3])
        assert digest == EXPECTED_URL_DIGESTS[version], version


@pytest.mark.parametrize("version", sorted(EXPECTED_ROWS))
def test_each_row_installs_as_its_verified_wheel(version):
    artifact = pinned_artifacts.lookup("policyengine-us", version)
    assert artifact is not None
    requirement = pinned_artifacts.requirement(f"policyengine-us=={version}")
    path = pinned_artifacts.cache_path(artifact)
    assert requirement == f"policyengine-us @ {path.resolve().as_uri()}"
    assert path.parent.name == EXPECTED_ROWS[version]
    assert path.name == f"policyengine_us-{version}-py3-none-any.whl"


def test_every_runtime_policyengine_us_pin_is_listed_or_recorded():
    """Only versions PyPI's index lists may stay out of the table."""
    check = _load_check_module()
    pins, _sources = check.inventory()
    pruned = {
        version
        for (package, version) in pins
        if package == "policyengine-us"
        and pinned_artifacts.lookup(package, version) is None
    }
    # 1.784.4 (comparisons/ri-income-tax-liability.yaml) has no recorded
    # wheel; its recovery is tracked in #659.
    assert pruned == {"1.784.4"}


def test_table_agrees_with_uv_lock():
    """The CI install reads uv.lock; runtime pins read the table. Same bytes."""
    locked = _lock_files("policyengine-us")
    assert locked, "uv.lock records no policyengine-us wheel"
    for version, (url, sha256) in locked.items():
        artifact = pinned_artifacts.lookup("policyengine-us", version)
        assert artifact is not None, (
            f"uv.lock installs policyengine-us {version}; record it in "
            "axiom_oracles/pinned_artifacts.py"
        )
        assert (artifact.url, artifact.sha256) == (url, sha256)


def test_the_default_in_repo_oracle_pin_is_recoverable():
    import importlib.util as util

    spec = util.spec_from_file_location(
        "run_comparison", REPO_ROOT / "scripts" / "run_comparison.py"
    )
    run_comparison = util.module_from_spec(spec)
    spec.loader.exec_module(run_comparison)
    name, version = run_comparison._PE_ORACLE_PINS[1].split("==")
    assert pinned_artifacts.lookup(name, version) is not None


def test_requirement_passes_unlisted_pins_through():
    assert pinned_artifacts.requirement("policyengine-uk==2.89.2") == (
        "policyengine-uk==2.89.2"
    )
    assert pinned_artifacts.requirement("numba>=0.60") == "numba>=0.60"
    source = "policyengine-us @ https://example.invalid/x.tar.gz"
    assert pinned_artifacts.requirement(source) == source


def test_requirement_installs_a_pruned_pin_from_the_verified_wheel():
    artifact = pinned_artifacts.lookup("policyengine_us", "1.752.2")
    assert artifact is not None
    expected = f"policyengine-us @ {pinned_artifacts.cache_path(artifact).resolve().as_uri()}"
    assert pinned_artifacts.requirement("policyengine-us==1.752.2") == expected
    assert pinned_artifacts.with_args(
        ("policyengine==4.18.9", "policyengine-us==1.752.2")
    ) == ["--with", "policyengine==4.18.9", "--with", expected]


class _Response:
    def __init__(self, status: int, body: bytes = b""):
        self.status_code = status
        self._body = body

    def iter_content(self, size):
        for start in range(0, len(self._body), size):
            yield self._body[start : start + size]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _artifact(body: bytes) -> pinned_artifacts.PinnedArtifact:
    return pinned_artifacts.PinnedArtifact(
        name="policyengine-us",
        version="0.0.1",
        url="https://files.pythonhosted.org/packages/aa/bb/"
        + "c" * 60
        + "/policyengine_us-0.0.1-py3-none-any.whl",
        sha256=hashlib.sha256(body).hexdigest(),
        recorded_in="test",
    )


def test_fetch_downloads_verifies_and_reuses(monkeypatch, tmp_path):
    monkeypatch.setenv(pinned_artifacts.CACHE_ENV, str(tmp_path))
    body = b"wheel bytes"
    artifact = _artifact(body)
    calls = []

    def fake_get(url, **_kwargs):
        calls.append(url)
        return _Response(200, body)

    monkeypatch.setattr(requests, "get", fake_get)
    path = REAL_FETCH(artifact)
    assert path == tmp_path / artifact.sha256 / artifact.filename
    assert path.read_bytes() == body
    assert REAL_FETCH(artifact) == path
    assert calls == [artifact.url]
    # A corrupted cache entry is downloaded again, not trusted.
    path.write_bytes(b"corrupt")
    assert REAL_FETCH(artifact).read_bytes() == body
    assert len(calls) == 2


def test_fetch_refuses_bytes_that_do_not_match(monkeypatch, tmp_path):
    monkeypatch.setenv(pinned_artifacts.CACHE_ENV, str(tmp_path))
    artifact = _artifact(b"expected")
    monkeypatch.setattr(requests, "get", lambda *_a, **_k: _Response(200, b"other"))
    with pytest.raises(pinned_artifacts.PinnedArtifactError) as exc:
        REAL_FETCH(artifact)
    assert "policyengine-us==0.0.1" in str(exc.value)
    assert "axiom_oracles/pinned_artifacts.py" in str(exc.value)
    assert not pinned_artifacts.cache_path(artifact).exists()
    assert list(pinned_artifacts.cache_path(artifact).parent.iterdir()) == []


def test_fetch_names_the_file_when_it_stops_downloading(monkeypatch, tmp_path):
    monkeypatch.setenv(pinned_artifacts.CACHE_ENV, str(tmp_path))
    artifact = _artifact(b"x")
    monkeypatch.setattr(requests, "get", lambda *_a, **_k: _Response(404))
    with pytest.raises(pinned_artifacts.PinnedArtifactError, match="HTTP 404"):
        REAL_FETCH(artifact)


def test_inventory_finds_the_runtime_pins():
    check = _load_check_module()
    pins, sources = check.inventory()
    uses = {key: {str(use) for use in value} for key, value in pins.items()}
    assert any(
        use.startswith("scripts/run_comparison.py:")
        for use in uses[("policyengine-us", "1.752.2")]
    )
    assert "comparisons/us-snap-abawd-grid.yaml" in uses[("policyengine-us", "1.767.3")]
    assert any(
        use.startswith("scripts/debug_policyengine_env.py:")
        for use in uses[("policyengine-us", "1.700.0")]
    )
    assert "axiom_oracles/adapters/taxsim/taxsim_pins.json" in uses[
        ("policyengine-taxsim", "2.30.0")
    ]
    assert ("spm-calculator", "0.3.1") in uses
    # A source-pinned suite's version is a label, not an index pin.
    assert "comparisons/fiit-ecps.yaml" not in uses.get(
        ("policyengine-us", "1.729.0"), set()
    )
    assert any(
        "comparisons/fiit-ecps.yaml" == str(use)
        for value in sources.values()
        for use in value
    )


class _Session:
    def __init__(self, listed: dict[str, list[str]], head_status: int = 200):
        self.listed = listed
        self.head_status = head_status

    def get(self, url, **_kwargs):
        package = url.rstrip("/").rsplit("/", 1)[-1]
        versions = self.listed.get(package, [])

        class R:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"versions": versions}

        return R()

    def head(self, url, **_kwargs):
        return type("R", (), {"status_code": self.head_status})()


def test_check_names_the_file_for_each_unrecoverable_pin(monkeypatch):
    check = _load_check_module()
    monkeypatch.setattr(check.pinned_artifacts, "fetch", lambda artifact: None)
    pins = {
        ("policyengine-us", "1.752.2"): {check.Use("scripts/run_comparison.py", 7)},
        ("policyengine-us", "1.784.4"): {check.Use("comparisons/x.yaml")},
        ("policyengine-uk", "2.89.2"): {check.Use("scripts/run_comparison.py", 9)},
    }
    sources = {"https://github.com/a.tar.gz": {check.Use("comparisons/y.yaml")}}
    monkeypatch.setattr(check, "inventory", lambda: (pins, sources))
    monkeypatch.setattr(
        requests,
        "Session",
        lambda: _Session({"policyengine-uk": ["2.89.2"]}, head_status=404),
    )
    failures = check.check()
    assert failures == [
        "comparisons/x.yaml: policyengine-us==1.784.4: PyPI's index no longer "
        "lists it and axiom_oracles/pinned_artifacts.py has no hashed URL for it",
        "comparisons/y.yaml: policyengine_us_source https://github.com/a.tar.gz: "
        "HTTP 404",
    ]


def test_check_fails_when_a_recorded_file_stops_downloading(monkeypatch):
    check = _load_check_module()

    def gone(artifact):
        raise pinned_artifacts.PinnedArtifactError(f"{artifact.filename}: HTTP 404")

    monkeypatch.setattr(check.pinned_artifacts, "fetch", gone)
    monkeypatch.setattr(check, "inventory", lambda: ({}, {}))
    monkeypatch.setattr(requests, "Session", lambda: _Session({}))
    failures = check.check()
    assert len(failures) == len(pinned_artifacts.PRUNED_ARTIFACTS)
    assert all(
        failure.startswith("axiom_oracles/pinned_artifacts.py: policyengine-us==")
        for failure in failures
    )
