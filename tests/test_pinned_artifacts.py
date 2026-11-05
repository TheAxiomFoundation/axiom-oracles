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
        assert artifact.found_in


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
    """Only versions PyPI's index lists may stay out of the table.

    Offline, so this pins the expected set; scripts/check_pinned_artifacts.py
    checks the index itself. A new policyengine-us pin with no table row
    changes this set and fails here until someone checks the index.
    """
    check = _load_check_module()
    pins, _sources = check.inventory()
    unrecorded = {
        version
        for (package, version) in pins
        if package == "policyengine-us"
        and pinned_artifacts.lookup(package, version) is None
    }
    assert unrecorded == {
        # comparisons/ri-income-tax-liability.yaml: no recorded wheel (#659).
        "1.784.4",
        # .github/workflows/ci.yml's live-engine job: listed on PyPI's index.
        "2.15.13",
    }


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
        found_in="test",
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
    assert exc.value.kind == "mismatch"
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
    pins, sources, problems = check.scan()
    assert problems == []
    uses = {key: {str(use) for use in value} for key, value in pins.items()}
    assert any(
        use.startswith("scripts/run_comparison.py:")
        for use in uses[("policyengine-us", "1.752.2")]
    )
    assert "comparisons/us-snap-abawd-grid.yaml" in uses[("policyengine-us", "1.767.3")]
    # The probe recipes install 1.767.3 through --oracle-with-args.
    assert any(
        use.startswith("scripts/probe_us_sc_income_tax_2026.py:")
        for use in uses[("policyengine-us", "1.767.3")]
    )
    assert any(
        use.startswith("scripts/debug_policyengine_env.py:")
        for use in uses[("policyengine-us", "1.700.0")]
    )
    assert "axiom_oracles/adapters/taxsim/taxsim_pins.json" in uses[
        ("policyengine-taxsim", "2.30.0")
    ]
    assert ("spm-calculator", "0.3.1") in uses
    # The tax-ecps runner's install default counts; its provenance label in
    # _build_run_provenance does not.
    tax_ecps = uses[("policyengine-us", "1.729.0")]
    assert tax_ecps and all(use.startswith("scripts/run_comparison.py:") for use in tax_ecps)
    source = (REPO_ROOT / "scripts" / "run_comparison.py").read_text().splitlines()
    for use in tax_ecps:
        line = source[int(use.rsplit(":", 1)[1]) - 1]
        assert "policyengine_us_version" in line and "oracle" not in line, line
    # A source-pinned suite's version is a label, not an index pin.
    assert "comparisons/fiit-ecps.yaml" not in tax_ecps
    assert any(
        "comparisons/fiit-ecps.yaml" == str(use)
        for value in sources.values()
        for use in value
    )


# ---------------------------------------------------------------------------
# The scan reads every shape a pin can take. Each test writes one shape into a
# throwaway repository root and reads scan().
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_root(tmp_path, monkeypatch):
    check = _load_check_module()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "comparisons").mkdir()
    taxsim = tmp_path / "axiom_oracles" / "adapters" / "taxsim"
    taxsim.mkdir(parents=True)
    (taxsim / "taxsim_pins.json").write_text(
        '{"distribution": {"package": "policyengine-taxsim", "version": "2.30.0"}}'
    )
    monkeypatch.setattr(check, "REPO_ROOT", tmp_path)
    return check, tmp_path


def _uses(check):
    pins, sources, problems = check.scan()
    return (
        {key: sorted(map(str, value)) for key, value in pins.items()},
        {key: sorted(map(str, value)) for key, value in sources.items()},
        problems,
    )


@pytest.mark.parametrize(
    "line",
    [
        'PIN = "policyengine-us==9.9.9"',
        'PIN = "policyengine_us==9.9.9"',
        'PIN = "policyengine-us == 9.9.9"',
        'PIN = ("policyengine-us", "9.9.9")',
        "PIN = params.get('policyengine_us_version', '9.9.9')",
        "# uv run --with policyengine-us==9.9.9 python x.py",
    ],
    ids=["literal", "underscore", "spaced", "tuple", "param-default", "comment"],
)
def test_scan_reads_each_code_spelling(fake_root, line):
    check, root = fake_root
    (root / "scripts" / "anything.py").write_text(line + "\n")
    pins, _sources, problems = _uses(check)
    assert pins[("policyengine-us", "9.9.9")] == ["scripts/anything.py:1"]
    assert problems == []


def test_scan_reads_every_script_under_scripts(fake_root):
    check, root = fake_root
    nested = root / "scripts" / "lane" / "deep"
    nested.mkdir(parents=True)
    (nested / "run.sh").write_text("uv run --with policyengine-uk==9.9.9 x\n")
    (root / "scripts" / "probe_new.py").write_text('PIN = "--with policyengine-us==8.8.8"\n')
    (root / "scripts" / "recipe.py").write_text(
        "pinned_artifacts \\\n    --oracle-with-args 7.7.7) \\\n"
    )
    pins, _sources, _problems = _uses(check)
    assert pins[("policyengine-uk", "9.9.9")] == ["scripts/lane/deep/run.sh:1"]
    assert pins[("policyengine-us", "8.8.8")] == ["scripts/probe_new.py:1"]
    assert pins[("policyengine-us", "7.7.7")] == ["scripts/recipe.py:2"]


def test_scan_does_not_read_remediation_hints_outside_scripts(fake_root):
    check, root = fake_root
    bridges = root / "axiom_oracles" / "bridges"
    bridges.mkdir(parents=True)
    (bridges / "hint.py").write_text('"Run with: uv run --with policyengine-core==9.9.9"\n')
    pins, _sources, _problems = _uses(check)
    assert ("policyengine-core", "9.9.9") not in pins


def test_scan_resolves_or_refuses_fstring_versions(fake_root):
    check, root = fake_root
    (root / "scripts" / "f.py").write_text(
        "a = f\"policyengine-us=={params.get('policyengine_us_version', '9.9.9')}\"\n"
        'b = f"policyengine-core=={mystery}"\n'
    )
    pins, _sources, problems = _uses(check)
    assert pins[("policyengine-us", "9.9.9")] == ["scripts/f.py:1"]
    assert len(problems) == 1
    assert problems[0].startswith("scripts/f.py:2: policyengine-core=={mystery}")


def test_scan_skips_provenance_label_scopes(fake_root, monkeypatch):
    check, root = fake_root
    monkeypatch.setitem(
        check.LABEL_SCOPES, ("scripts/labels.py", "_build_run_provenance"), "labels"
    )
    (root / "scripts" / "labels.py").write_text(
        "def _build_run_provenance(params):\n"
        "    return params.get('policyengine_us_version', '1.1.1')\n"
        "\n"
        "def run(params):\n"
        "    return params.get('policyengine_us_version', '2.2.2')\n"
    )
    pins, _sources, _problems = _uses(check)
    assert ("policyengine-us", "1.1.1") not in pins
    assert pins[("policyengine-us", "2.2.2")] == ["scripts/labels.py:5"]


def test_scan_reads_yaml_keys_at_any_depth(fake_root):
    check, root = fake_root
    (root / "comparisons" / "nested.yaml").write_text(
        "runner:\n"
        "  parameters:\n"
        "    stack:\n"
        "      policyengine_core_version: '1.0.1'\n"
        "runners:\n"
        "  - parameters:\n"
        "      policyengine_us_version: '1.0.2'\n"
        "  - oracle:\n"
        "      policyengine_us: '1.0.3'\n"
        "notes:\n"
        "  - install with policyengine-uk==1.0.4\n"
    )
    sub = root / "comparisons" / "fixtures"
    sub.mkdir()
    (sub / "deep.yaml").write_text("a: {b: {policyengine_version: '1.0.5'}}\n")
    pins, _sources, problems = _uses(check)
    assert problems == []
    assert pins[("policyengine-core", "1.0.1")] == ["comparisons/nested.yaml"]
    assert pins[("policyengine-us", "1.0.2")] == ["comparisons/nested.yaml"]
    assert pins[("policyengine-us", "1.0.3")] == ["comparisons/nested.yaml"]
    assert pins[("policyengine-uk", "1.0.4")] == ["comparisons/nested.yaml"]
    assert pins[("policyengine", "1.0.5")] == ["comparisons/fixtures/deep.yaml"]


def test_scan_treats_a_source_pinned_version_as_a_label(fake_root):
    check, root = fake_root
    archive = (
        "https://github.com/PolicyEngine/policyengine-us/archive/" + "a" * 40 + ".tar.gz"
    )
    (root / "comparisons" / "s.yaml").write_text(
        "runner:\n  parameters:\n"
        "    policyengine_us_version: '1.0.6'\n"
        f"    policyengine_us_source: {archive}\n"
    )
    pins, sources, _problems = _uses(check)
    assert ("policyengine-us", "1.0.6") not in pins
    assert sources[archive] == ["comparisons/s.yaml"]


def test_scan_fails_closed_on_unparseable_yaml(fake_root):
    check, root = fake_root
    (root / "comparisons" / "broken.yaml").write_text("runner: [unclosed\n")
    _pins, _sources, problems = _uses(check)
    assert len(problems) == 1
    assert problems[0].startswith("comparisons/broken.yaml: cannot parse")


# ---------------------------------------------------------------------------
# Network behavior: retries, transient versus gone, and known-open breaks.
# ---------------------------------------------------------------------------


class _Reply:
    def __init__(self, status: int, versions=()):
        self.status_code = status
        self._versions = list(versions)

    def json(self):
        return {"versions": self._versions}


class _Session:
    """Scripted replies: ``index[package]`` and ``head[url]`` are lists of a
    status or an exception, consumed one per request; the last one repeats."""

    def __init__(self, index=None, head=None, listed=None):
        self.index = index or {}
        self.head_script = head or {}
        self.listed = listed or {}
        self.calls: list[str] = []

    @staticmethod
    def _next(script):
        item = script.pop(0) if len(script) > 1 else script[0]
        if isinstance(item, Exception):
            raise item
        return item

    def get(self, url, **_kwargs):
        package = url.rstrip("/").rsplit("/", 1)[-1]
        self.calls.append(f"get {package}")
        status = self._next(self.index.get(package, [200]))
        return _Reply(status, self.listed.get(package, []))

    def head(self, url, **_kwargs):
        self.calls.append(f"head {url}")
        return _Reply(self._next(self.head_script.get(url, [200])))


@pytest.fixture
def no_sleep(monkeypatch):
    waits: list[float] = []
    monkeypatch.setattr(pinned_artifacts, "_sleep", waits.append)
    return waits


def _run_check(monkeypatch, session, pins, sources=None):
    check = _load_check_module()
    monkeypatch.setattr(check.pinned_artifacts, "fetch", lambda artifact: None)
    monkeypatch.setattr(check, "scan", lambda: (pins, sources or {}, []))
    monkeypatch.setattr(requests, "Session", lambda: session)
    return check, check.check()


def test_check_names_the_file_for_each_unrecoverable_pin(monkeypatch, no_sleep):
    check = _load_check_module()
    pins = {
        ("policyengine-us", "1.752.2"): {check.Use("scripts/run_comparison.py", 7)},
        ("policyengine-us", "9.9.9"): {check.Use("comparisons/x.yaml")},
        ("policyengine-uk", "2.89.2"): {check.Use("scripts/run_comparison.py", 9)},
    }
    sources = {"https://github.com/a.tar.gz": {check.Use("comparisons/y.yaml")}}
    session = _Session(
        listed={"policyengine-uk": ["2.89.2"]},
        head={"https://github.com/a.tar.gz": [404]},
    )
    _check, (failures, warnings) = _run_check(monkeypatch, session, pins, sources)
    assert failures == [
        "comparisons/x.yaml: policyengine-us==9.9.9: PyPI's index no longer "
        "lists it and axiom_oracles/pinned_artifacts.py has no hashed URL for it",
        "comparisons/y.yaml: policyengine-us archive https://github.com/a.tar.gz: "
        "HTTP 404",
    ]
    assert warnings == []
    # A 404 is a removal: never retried.
    assert session.calls.count("head https://github.com/a.tar.gz") == 1
    assert no_sleep == []


def test_known_open_breaks_warn_and_only_new_ones_fail(monkeypatch, no_sleep):
    check = _load_check_module()
    ri = "comparisons/ri-income-tax-liability.yaml"
    assert check.KNOWN_OPEN[("policyengine-us", "1.784.4", ri)] == "#659"
    pins = {
        # A new suite adopting the known-open pin is a new break.
        ("policyengine-us", "1.784.4"): {
            check.Use(ri),
            check.Use("comparisons/new-on-1784.yaml"),
        },
        ("policyengine-us", "9.9.9"): {check.Use("comparisons/new.yaml")},
    }
    _check, (failures, warnings) = _run_check(monkeypatch, _Session(), pins)
    assert [w.split(":")[0] for w in warnings] == [ri]
    assert warnings[0].endswith("(known open: #659)")
    assert sorted(f.split(":")[0] for f in failures) == [
        "comparisons/new-on-1784.yaml",
        "comparisons/new.yaml",
    ]


def test_check_reports_an_unreadable_index(monkeypatch, no_sleep):
    check = _load_check_module()
    pins = {("policyengine-uk", "2.89.2"): {check.Use("scripts/x.py", 1)}}
    session = _Session(index={"policyengine-uk": [404]})
    _check, (failures, _warnings) = _run_check(monkeypatch, session, pins)
    assert failures == ["policyengine-uk: cannot read PyPI's index: HTTP 404"]


def test_check_retries_a_server_error_then_succeeds(monkeypatch, no_sleep):
    check = _load_check_module()
    pins = {("policyengine-uk", "2.89.2"): {check.Use("scripts/x.py", 1)}}
    session = _Session(
        index={"policyengine-uk": [503, 200]}, listed={"policyengine-uk": ["2.89.2"]}
    )
    _check, (failures, _warnings) = _run_check(monkeypatch, session, pins)
    assert failures == []
    assert session.calls == ["get policyengine-uk", "get policyengine-uk"]
    assert no_sleep == [pinned_artifacts.RETRY_DELAYS[0]]


def test_check_calls_a_persistent_server_error_transient(monkeypatch, no_sleep):
    check = _load_check_module()
    url = "https://github.com/a.tar.gz"
    pins = {}
    sources = {url: {check.Use("comparisons/y.yaml")}}
    session = _Session(head={url: [502]})
    _check, (failures, _warnings) = _run_check(monkeypatch, session, pins, sources)
    attempts = len(pinned_artifacts.RETRY_DELAYS) + 1
    assert session.calls == [f"head {url}"] * attempts
    assert failures == [
        f"comparisons/y.yaml: policyengine-us archive {url}: transient: HTTP 502 "
        f"on all {attempts} attempts, not a removal"
    ]
    assert no_sleep == list(pinned_artifacts.RETRY_DELAYS)


def test_check_calls_a_persistent_connection_error_transient(monkeypatch, no_sleep):
    check = _load_check_module()
    pins = {("policyengine-uk", "2.89.2"): {check.Use("scripts/x.py", 1)}}
    session = _Session(index={"policyengine-uk": [requests.ConnectionError("reset")]})
    _check, (failures, _warnings) = _run_check(monkeypatch, session, pins)
    assert len(failures) == 1
    assert failures[0].startswith(
        "policyengine-uk: cannot read PyPI's index: transient: connection failed"
    )


def test_check_fails_when_a_recorded_file_stops_downloading(monkeypatch):
    check = _load_check_module()

    def gone(artifact):
        raise pinned_artifacts.PinnedArtifactError(
            f"{artifact.filename}: HTTP 404", kind="gone"
        )

    monkeypatch.setattr(check.pinned_artifacts, "fetch", gone)
    monkeypatch.setattr(check, "scan", lambda: ({}, {}, []))
    monkeypatch.setattr(requests, "Session", lambda: _Session())
    failures, _warnings = check.check()
    assert len(failures) == len(pinned_artifacts.PRUNED_ARTIFACTS)
    assert all(
        failure.startswith("axiom_oracles/pinned_artifacts.py: policyengine-us==")
        and "[gone]" in failure
        for failure in failures
    )


def test_check_fails_on_scan_problems(monkeypatch):
    check = _load_check_module()
    monkeypatch.setattr(check.pinned_artifacts, "fetch", lambda artifact: None)
    monkeypatch.setattr(check, "scan", lambda: ({}, {}, ["comparisons/b.yaml: cannot parse"]))
    monkeypatch.setattr(requests, "Session", lambda: _Session())
    failures, _warnings = check.check()
    assert failures == ["comparisons/b.yaml: cannot parse"]


def test_fetch_retries_a_server_error_then_verifies(monkeypatch, tmp_path, no_sleep):
    monkeypatch.setenv(pinned_artifacts.CACHE_ENV, str(tmp_path))
    body = b"wheel"
    artifact = _artifact(body)
    replies = [_Response(503), _Response(200, body)]
    monkeypatch.setattr(requests, "get", lambda *_a, **_k: replies.pop(0))
    assert REAL_FETCH(artifact).read_bytes() == body
    assert no_sleep == [pinned_artifacts.RETRY_DELAYS[0]]


def test_fetch_calls_a_persistent_server_error_transient(monkeypatch, tmp_path, no_sleep):
    monkeypatch.setenv(pinned_artifacts.CACHE_ENV, str(tmp_path))
    artifact = _artifact(b"x")
    calls = []

    def always_503(*_a, **_k):
        calls.append(1)
        return _Response(503)

    monkeypatch.setattr(requests, "get", always_503)
    with pytest.raises(pinned_artifacts.PinnedArtifactError) as exc:
        REAL_FETCH(artifact)
    assert exc.value.kind == "transient"
    assert len(calls) == len(pinned_artifacts.RETRY_DELAYS) + 1
    assert list(pinned_artifacts.cache_path(artifact).parent.iterdir()) == []


def test_fetch_retries_a_connection_error(monkeypatch, tmp_path, no_sleep):
    monkeypatch.setenv(pinned_artifacts.CACHE_ENV, str(tmp_path))
    artifact = _artifact(b"x")

    def refused(*_a, **_k):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(requests, "get", refused)
    with pytest.raises(pinned_artifacts.PinnedArtifactError) as exc:
        REAL_FETCH(artifact)
    assert exc.value.kind == "transient"
    assert no_sleep == list(pinned_artifacts.RETRY_DELAYS)


def test_fetch_does_not_retry_a_removal(monkeypatch, tmp_path, no_sleep):
    monkeypatch.setenv(pinned_artifacts.CACHE_ENV, str(tmp_path))
    artifact = _artifact(b"x")
    calls = []

    def gone(*_a, **_k):
        calls.append(1)
        return _Response(404)

    monkeypatch.setattr(requests, "get", gone)
    with pytest.raises(pinned_artifacts.PinnedArtifactError) as exc:
        REAL_FETCH(artifact)
    assert exc.value.kind == "gone"
    assert calls == [1] and no_sleep == []


# ---------------------------------------------------------------------------
# The probe recipe, the lock's source, and isolated overlays.
# ---------------------------------------------------------------------------


def test_oracle_with_args_uses_the_suites_stack_and_companions():
    args = pinned_artifacts.oracle_with_args("1.767.3")
    wheel = pinned_artifacts.cache_path(pinned_artifacts.lookup("policyengine-us", "1.767.3"))
    assert args == [
        "--with",
        "policyengine==4.18.9",
        "--with",
        f"policyengine-us@{wheel.resolve().as_uri()}",
        "--with",
        "policyengine-core==3.30.3",
        "--with",
        "spm-calculator==0.3.1",
    ]
    assert not any(ch.isspace() for arg in args for ch in arg)


def test_oracle_stack_params_refuses_disagreeing_suites(tmp_path):
    for name, core in (("a", "3.30.3"), ("b", "3.28.0")):
        (tmp_path / f"{name}.yaml").write_text(
            "runner:\n  parameters:\n"
            "    policyengine_version: '4.18.9'\n"
            "    policyengine_us_version: '9.9.9'\n"
            f"    policyengine_core_version: '{core}'\n"
        )
    with pytest.raises(SystemExit, match="different stacks"):
        pinned_artifacts.oracle_stack_params("9.9.9", tmp_path)
    with pytest.raises(SystemExit, match="no comparisons suite pins policyengine-us 8.8.8"):
        pinned_artifacts.oracle_stack_params("8.8.8", tmp_path)


def test_oracle_with_args_refuses_a_version_no_suite_pins(capsys):
    # 1.729.0 is in the table and pinned by the tax-ecps runner default, but
    # the one suite on it (fiit-ecps) installs it from a policyengine_us_source
    # archive, so no suite stack exists to print.
    with pytest.raises(SystemExit) as exc:
        pinned_artifacts.main(["--oracle-with-args", "1.729.0"])
    assert "no comparisons suite pins policyengine-us 1.729.0" in str(exc.value.code)
    assert capsys.readouterr().out == ""


def test_oracle_stack_params_ignores_source_pinned_suites(tmp_path):
    (tmp_path / "source.yaml").write_text(
        "runner:\n  parameters:\n"
        "    policyengine_version: '4.11.0'\n"
        "    policyengine_us_version: '7.7.7'\n"
        "    policyengine_core_version: '3.26.11'\n"
        "    policyengine_us_source: https://github.com/x/archive/y.tar.gz\n"
    )
    nested = tmp_path / "fixtures"
    nested.mkdir()
    (nested / "by-version.yaml").write_text(
        "runner:\n  parameters:\n"
        "    policyengine_version: '4.18.9'\n"
        "    policyengine_us_version: '7.7.7'\n"
        "    policyengine_core_version: '3.30.3'\n"
    )
    # The source-pinned suite does not install 7.7.7 by version, so it neither
    # supplies nor contradicts the stack; the subdirectory suite is read.
    assert pinned_artifacts.oracle_stack_params("7.7.7", tmp_path) == {
        "policyengine_us_version": "7.7.7",
        "policyengine_version": "4.18.9",
        "policyengine_core_version": "3.30.3",
    }


def test_main_prints_the_oracle_with_args(capsys):
    assert pinned_artifacts.main(["--oracle-with-args", "1.767.3"]) == 0
    printed = capsys.readouterr().out.split()
    assert printed == pinned_artifacts.oracle_with_args("1.767.3")


def test_pyproject_source_is_the_table_row_uv_lock_installs():
    import tomllib

    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    source = pyproject["tool"]["uv"]["sources"]["policyengine-us"]
    artifact = pinned_artifacts.lookup("policyengine-us", "1.764.6")
    assert source == {"url": artifact.url}
    extras = pyproject["project"]["optional-dependencies"]
    for extra in ("policyengine", "taxsim"):
        assert "policyengine-us==1.764.6" in extras[extra], extra


_PE_MARKERS = re.compile(
    r"_pe_oracle_with_args|with_args\(|\bpe_pins\b|PE_ORACLE_PINS"
    r"|(?i:policyengine(?:[-_.]+(?:us|core|uk|taxsim))?)\s*(?:={2,3}|@)"
)


def _command_sequences(tree):
    """``(node, elements)`` for each list or tuple literal, with ``+`` chains
    of them (``["uv"] + ["run", ...]``) flattened into one sequence. The
    operands of a chain are not reported on their own."""
    import ast

    def flatten(node):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            # An operand that is not a literal (``list(...)``, a name) stands
            # in as one unknown element.
            return (flatten(node.left) or [node.left]) + (flatten(node.right) or [node.right])
        if isinstance(node, (ast.List, ast.Tuple)):
            return list(node.elts)
        return None

    operands = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            operands.update({id(node.left), id(node.right)})
    for node in ast.walk(tree):
        if id(node) in operands:
            continue
        elements = flatten(node)
        if elements is not None:
            yield node, elements


def _python_overlays(path: Path) -> list[tuple[int, bool]]:
    """``(line, isolated)`` for each ``"uv", "run", ..., "--no-project", ...``
    list or tuple, or ``+`` chain of them, in a function that installs
    PolicyEngine pins."""
    import ast

    text = path.read_text()
    tree = ast.parse(text)
    functions = [
        n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    found = []
    for node, elements in _command_sequences(tree):
        values = [e.value if isinstance(e, ast.Constant) else None for e in elements]
        if not any(values[i : i + 2] == ["uv", "run"] for i in range(len(values) - 1)):
            continue
        flags = {v for v in values if isinstance(v, str)}
        if "--no-project" not in flags or "--directory" in flags:
            continue  # project runs use that project's own environment
        enclosing = [
            f for f in functions if f.lineno <= node.lineno <= f.end_lineno
        ]
        scope = min(enclosing, key=lambda f: f.end_lineno - f.lineno) if enclosing else node
        if _PE_MARKERS.search(ast.get_source_segment(text, scope) or ""):
            found.append((node.lineno, "--isolated" in flags))
    return found


def _shell_overlays(path: Path) -> list[tuple[int, bool]]:
    """``(line, isolated)`` for each ``uv run --no-project`` shell command that
    installs a PolicyEngine pin (continuation lines joined)."""
    found = []
    lines = path.read_text().splitlines()
    i = 0
    while i < len(lines):
        start, command = i, lines[i]
        while command.rstrip().endswith("\\") and i + 1 < len(lines):
            i += 1
            command = command.rstrip()[:-1] + " " + lines[i]
        i += 1
        if command.lstrip().startswith("#") or "uv run" not in command:
            continue
        if "--no-project" in command and _PE_MARKERS.search(command):
            found.append((start + 1, "--isolated" in command.split()))
    return found


def _script_language(path: Path) -> str | None:
    """``"python"`` or ``"shell"`` from the suffix, else from the shebang."""
    if path.suffix == ".py":
        return "python"
    if path.suffix in (".sh", ".bash"):
        return "shell"
    with path.open("rb") as handle:
        first = handle.readline(200).decode("utf-8", "replace")
    if not first.startswith("#!"):
        return None
    words = first[2:].split()
    if words and words[0].rsplit("/", 1)[-1] == "env":
        words = [w for w in words[1:] if not w.startswith("-") and "=" not in w]
    if not words:
        return None
    interpreter = words[0].rsplit("/", 1)[-1]
    if re.fullmatch(r"python[\d.]*", interpreter):
        return "python"
    if interpreter in ("sh", "bash", "dash", "zsh", "ksh"):
        return "shell"
    return None


def _overlay_sites(root: Path) -> dict[tuple[str, int], bool]:
    """``{(file, line): isolated}`` for every PolicyEngine overlay under ``root``."""
    overlays = {}
    for tree in ("scripts", "ops"):
        for path in sorted((root / tree).rglob("*")):
            if "__pycache__" in path.parts or not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            language = _script_language(path)
            if language == "python":
                overlays[rel] = _python_overlays(path)
            elif language == "shell":
                overlays[rel] = _shell_overlays(path)
    return {(rel, line): isolated for rel, found in overlays.items() for line, isolated in found}


def test_every_policyengine_overlay_is_isolated():
    """A ``--no-project`` `uv run` that installs PolicyEngine pins must not
    layer on the checkout's .venv: every script under scripts/ and ops/,
    Python and shell. (The snap-ecps run uses ``--directory``: axiom-encode's
    project.)"""
    sites = _overlay_sites(REPO_ROOT)
    assert sum(1 for rel, _ in sites if rel == "scripts/run_comparison.py") >= 15
    assert any(rel == "scripts/debug_policyengine_env.py" for rel, _ in sites)
    assert any(rel == "scripts/fiit_ecps_eitc_attribution/run_stage.sh" for rel, _ in sites)
    missing = sorted(f"{rel}:{line}" for (rel, line), isolated in sites.items() if not isolated)
    assert missing == []


_PY_HEAD = "import subprocess\n\n\ndef run(pins):\n"
#: Each shape the overlay scan must recognize: (file, text, line of the site).
#: ``{iso}`` is replaced by ``--isolated`` (or removed) in the command.
_OVERLAY_SHAPES = {
    "tuple": (
        "scripts/tuple_site.py",
        _PY_HEAD + '    cmd = ("uv", "run",{iso} "--no-project", *_pe_oracle_with_args(pins), "python")\n'
        "    return subprocess.run(cmd)\n",
        5,
    ),
    "concatenated-list": (
        "scripts/concat_site.py",
        _PY_HEAD + '    cmd = ["uv"] + ["run",{iso} "--no-project", *_pe_oracle_with_args(pins)]\n'
        '    return subprocess.run(cmd + ["python"])\n',
        5,
    ),
    "concatenated-tuple-chain": (
        "scripts/chain_site.py",
        _PY_HEAD + '    cmd = ("uv",) + ("run",{iso}) + ("--no-project", *_pe_oracle_with_args(pins))\n'
        "    return subprocess.run(cmd)\n",
        5,
    ),
    "extensionless-shell": (
        "scripts/run_oracle",
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        "uv run{iso} --no-project --with policyengine-us==1.2.3 python x.py\n",
        3,
    ),
    "ops-shell": (
        "ops/run_oracle.sh",
        "#!/bin/sh\nuv run{iso} --no-project \\\n  --with policyengine-us==1.2.3 python x.py\n",
        2,
    ),
}


def _write_shape(root: Path, shape: str, *, isolated: bool) -> tuple[str, int]:
    rel, text, line = _OVERLAY_SHAPES[shape]
    python = rel.endswith(".py")
    iso = (' "--isolated",' if python else " --isolated") if isolated else ""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace("{iso}", iso))
    return rel, line


@pytest.mark.parametrize("shape", sorted(_OVERLAY_SHAPES))
def test_overlay_scan_finds_each_unisolated_shape(tmp_path, shape):
    rel, line = _write_shape(tmp_path, shape, isolated=False)
    assert _overlay_sites(tmp_path) == {(rel, line): False}


@pytest.mark.parametrize("shape", sorted(_OVERLAY_SHAPES))
def test_overlay_scan_accepts_each_isolated_shape(tmp_path, shape):
    rel, line = _write_shape(tmp_path, shape, isolated=True)
    assert _overlay_sites(tmp_path) == {(rel, line): True}


def test_overlay_scan_counts_a_concatenation_once(tmp_path):
    # The operands of ``["uv", "run"] + [...]`` are not separate sites.
    path = tmp_path / "scripts" / "once.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        _PY_HEAD + '    cmd = ["uv", "run", "--no-project"] + ["--isolated"] + '
        "list(_pe_oracle_with_args(pins))\n    return subprocess.run(cmd)\n"
    )
    assert _overlay_sites(tmp_path) == {("scripts/once.py", 5): True}


def test_overlay_scan_skips_a_non_shell_extensionless_file(tmp_path):
    path = tmp_path / "scripts" / "notes"
    path.parent.mkdir(parents=True)
    path.write_text("uv run --no-project --with policyengine-us==1.2.3 python x.py\n")
    assert _overlay_sites(tmp_path) == {}


# ---------------------------------------------------------------------------
# Status classes: 404/410 gone; 408, 429 and 5xx retried then transient; any
# other 4xx refused at once.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "kind", "tries"),
    [
        (404, "gone", 1),
        (410, "gone", 1),
        (408, "transient", 3),
        (429, "transient", 3),
        (500, "transient", 3),
        (503, "transient", 3),
        (403, "refused", 1),
        (401, "refused", 1),
        (451, "refused", 1),
    ],
)
def test_fetch_classifies_each_status(monkeypatch, tmp_path, no_sleep, status, kind, tries):
    monkeypatch.setenv(pinned_artifacts.CACHE_ENV, str(tmp_path))
    artifact = _artifact(b"x")
    calls = []

    def reply(*_a, **_k):
        calls.append(status)
        return _Response(status)

    monkeypatch.setattr(requests, "get", reply)
    with pytest.raises(pinned_artifacts.PinnedArtifactError) as exc:
        REAL_FETCH(artifact)
    assert exc.value.kind == kind
    assert len(calls) == tries
    assert no_sleep == list(pinned_artifacts.RETRY_DELAYS[: tries - 1])


@pytest.mark.parametrize("status", [408, 429])
def test_fetch_recovers_after_a_retried_client_status(monkeypatch, tmp_path, no_sleep, status):
    monkeypatch.setenv(pinned_artifacts.CACHE_ENV, str(tmp_path))
    body = b"wheel"
    artifact = _artifact(body)
    replies = [_Response(status), _Response(200, body)]
    monkeypatch.setattr(requests, "get", lambda *_a, **_k: replies.pop(0))
    assert REAL_FETCH(artifact).read_bytes() == body


@pytest.mark.parametrize(
    ("status", "described", "tries"),
    [
        (404, "HTTP 404", 1),
        (410, "HTTP 410", 1),
        (429, "transient: HTTP 429 on all 3 attempts, not a removal", 3),
        (403, "refused: HTTP 403, not retried and not by itself a removal", 1),
    ],
)
def test_check_classifies_each_archive_status(monkeypatch, no_sleep, status, described, tries):
    check = _load_check_module()
    url = "https://github.com/a.tar.gz"
    session = _Session(head={url: [status]})
    _check, (failures, _warnings) = _run_check(
        monkeypatch, session, {}, {url: {check.Use("comparisons/y.yaml")}}
    )
    assert failures == [f"comparisons/y.yaml: policyengine-us archive {url}: {described}"]
    assert session.calls == [f"head {url}"] * tries


# ---------------------------------------------------------------------------
# RESOLVED_ELSEWHERE is keyed by function; label scopes must install nothing.
# ---------------------------------------------------------------------------


def test_scan_refuses_an_unlisted_fstring_in_a_new_function(fake_root):
    check, root = fake_root
    (root / "scripts" / "run_comparison.py").write_text(
        "import subprocess\n"
        "\n"
        "def _resolve_pe_oracle_pins(params):\n"
        "    us = params.get('policyengine_us_version')\n"
        "    return f'policyengine-us=={us}'\n"
        "\n"
        "def _run_new_suite(runner, output):\n"
        "    us = '1.691.3'\n"
        "    core = '3.20.0'\n"
        "    subprocess.run(['uv', 'run', '--with', f'policyengine-us=={us}',\n"
        "                    '--with', f'policyengine-core=={core}'])\n"
    )
    _pins, _sources, problems = _uses(check)
    # The listed (file, function, expression) passes; the same names in a new
    # function do not.
    assert [problem.split(":")[1] for problem in problems] == ["10", "11"]
    assert all("_run_new_suite" in problem for problem in problems)


def test_scan_refuses_an_install_inside_a_label_scope(fake_root):
    check, root = fake_root
    (root / "scripts" / "run_comparison.py").write_text(
        "import subprocess\n"
        "\n"
        "def _build_run_provenance(config, runner_type, output):\n"
        "    subprocess.run(['uv', 'run', '--with', 'policyengine-us==1.692.4', 'x'])\n"
        "    return {'policyengine_us': '1.692.4'}\n"
    )
    pins, _sources, problems = _uses(check)
    assert len(problems) == 1
    assert problems[0].startswith("scripts/run_comparison.py:4: label scope _build_run_provenance")
    # The scope is not skipped once it is refused, so its pin is counted too.
    assert pins[("policyengine-us", "1.692.4")] == ["scripts/run_comparison.py:4"]


def test_scan_reports_an_unparseable_python_file(fake_root):
    check, root = fake_root
    (root / "scripts" / "broken.py").write_text("def broken(:\n")
    _pins, _sources, problems = _uses(check)
    assert len(problems) == 1 and problems[0].startswith("scripts/broken.py:1: cannot parse")


# ---------------------------------------------------------------------------
# Spellings: PEP 503 names, ===, direct wheel URLs, non-literal versions, and
# the ops/ and .github/workflows/ trees.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        'PIN = "PolicyEngine-US==9.9.9"',
        'PIN = "policyengine.us==9.9.9"',
        'PIN = "policyengine__-us==9.9.9"',
        'PIN = "policyengine-us===9.9.9"',
    ],
    ids=["upper-case", "dotted", "mixed-run", "triple-equals"],
)
def test_scan_normalizes_names_and_reads_triple_equals(fake_root, line):
    check, root = fake_root
    (root / "scripts" / "anything.py").write_text(line + "\n")
    pins, _sources, problems = _uses(check)
    assert pins[("policyengine-us", "9.9.9")] == ["scripts/anything.py:1"]
    assert problems == []


@pytest.mark.parametrize(
    ("name", "line"),
    [
        ("concatenation", 'PIN = "policyengine-us==" + version'),
        ("percent", 'PIN = "policyengine-us==%s" % version'),
        ("shell-var", "uv run --with policyengine-us==$VER x"),
        ("shell-braced", "uv run --with policyengine-us==${VER} x"),
    ],
)
def test_scan_fails_closed_on_a_non_literal_version(fake_root, name, line):
    check, root = fake_root
    suffix = ".sh" if name.startswith("shell") else ".py"
    (root / "scripts" / f"pin{suffix}").write_text(line + "\n")
    _pins, _sources, problems = _uses(check)
    assert len(problems) == 1
    assert problems[0].startswith(f"scripts/pin{suffix}:1: ")
    assert "not a literal" in problems[0]


def test_scan_refuses_a_direct_url_to_an_unlisted_wheel(fake_root):
    check, root = fake_root
    listed = pinned_artifacts.lookup("policyengine-us", "1.767.3").url
    unlisted = (
        "https://files.pythonhosted.org/packages/aa/bb/" + "c" * 60
        + "/policyengine_us-9.9.9-py3-none-any.whl"
    )
    (root / "scripts" / "urls.sh").write_text(
        f'uv run --with "policyengine-us @ {listed}" a\n'
        f'uv run --with "policyengine-us @ {unlisted}" b\n'
    )
    _pins, _sources, problems = _uses(check)
    assert len(problems) == 1
    assert problems[0].startswith(f"scripts/urls.sh:2: policyengine-us @ {unlisted}")


@pytest.mark.parametrize("tree", ["ops", ".github/workflows"])
def test_scan_reads_ops_and_workflows(fake_root, tree):
    check, root = fake_root
    directory = root / tree
    directory.mkdir(parents=True)
    (directory / "job.yml").write_text(
        "steps:\n  - run: uv pip install policyengine-us==9.9.9\n"
    )
    pins, _sources, _problems = _uses(check)
    assert pins[("policyengine-us", "9.9.9")] == [f"{tree}/job.yml:2"]


def test_probe_recipes_fail_closed():
    """Each probe recipe assigns the printed --with list, then starts the
    probe only on ``&&``, so a failed inner command never runs it unpinned."""
    probes = sorted((REPO_ROOT / "scripts").glob("probe_us_*.py"))
    recipes = 0
    for path in probes:
        doc = path.read_text()
        if "--oracle-with-args" not in doc:
            continue
        recipes += 1
        match = re.search(
            r"pins=\$\(uv run -q python -m axiom_oracles\.pinned_artifacts \\\n"
            r"\s+--oracle-with-args (\S+)\) &&\n"
            r"\s+uv run --python \S+ --no-project --isolated \$pins \\\n"
            rf"\s+python scripts/{re.escape(path.name)}\n",
            doc,
        )
        assert match, path.name
        assert pinned_artifacts.lookup("policyengine-us", match.group(1)), path.name
    assert recipes == 4
