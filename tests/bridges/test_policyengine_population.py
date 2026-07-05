from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from axiom_oracles.bridges import population


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------
def _clear_populace_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop every AXIOM_POPULACE_* env var so tests start from a clean slate."""
    for key in _env_keys():
        monkeypatch.delenv(key, raising=False)


def _env_keys() -> tuple[str, ...]:
    return (
        "AXIOM_POPULACE_US_2024_H5",
        "AXIOM_POPULACE_UK_2023_H5",
        "AXIOM_POPULACE_US_H5",
        "AXIOM_POPULACE_UK_H5",
        "AXIOM_POPULACE_H5",
        "AXIOM_POPULACE_DATASET",
        "AXIOM_POPULACE_DATA_PATH",
        "AXIOM_POPULACE_US_REVISION",
        "AXIOM_POPULACE_US_SHA256",
        "AXIOM_POPULACE_UK_REVISION",
        "AXIOM_POPULACE_UK_SHA256",
        population.ALLOW_UNPINNED_ENV,
    )


def _install_fake_hf_hub(
    monkeypatch: pytest.MonkeyPatch, downloaded_path
) -> dict[str, object]:
    """Install a fake ``huggingface_hub`` module and capture download kwargs."""
    captured: dict[str, object] = {}

    def fake_hf_hub_download(**kwargs):
        captured.update(kwargs)
        return str(downloaded_path)

    module = ModuleType("huggingface_hub")
    module.hf_hub_download = fake_hf_hub_download  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "huggingface_hub", module)
    return captured


def _stub_instantiate(monkeypatch: pytest.MonkeyPatch):
    """Replace dataset instantiation with a sentinel that echoes its path."""

    def fake_instantiate(country: str, path, command: str):
        return SimpleNamespace(country=country, file_path=str(path))

    monkeypatch.setattr(population, "_instantiate_dataset", fake_instantiate)


# ---------------------------------------------------------------------------
# Pin structure and env-override resolution
# ---------------------------------------------------------------------------
def test_pins_match_certified_bundle_values():
    us = population.POPULACE_PINS["us"]
    assert us.repo_id == "policyengine/populace-us"
    assert us.filename == "populace_us_2024.h5"
    assert us.revision == "populace-us-2024-f0af251-703bd81a565c-20260620T201958Z"
    assert us.sha256 == (
        "16be6338f9d0b3c339883dae59949e995663b64cf145de6728b3dd0f916c5d5f"
    )
    assert us.built_with == "1.729.0"
    assert us.repo_type == "dataset"

    uk = population.POPULACE_PINS["uk"]
    assert uk.repo_id == "policyengine/populace-uk-private"
    assert uk.filename == "populace_uk_2023.h5"
    assert uk.revision == "populace-uk-2023-dd68c73-4aa4b14-20260619T023711Z"
    assert uk.sha256 == (
        "f17306ccb2aad7ff0130be3589b560afb2e2a12a943570911cd0c77f07934833"
    )
    assert uk.built_with == "2.89.2"


def test_resolve_pin_defaults_to_baseline(monkeypatch):
    _clear_populace_env(monkeypatch)
    assert population.resolve_populace_pin("us") == population.POPULACE_PINS["us"]


def test_resolve_pin_applies_env_revision_and_sha_overrides(monkeypatch):
    _clear_populace_env(monkeypatch)
    monkeypatch.setenv("AXIOM_POPULACE_US_REVISION", "custom-rev")
    monkeypatch.setenv("AXIOM_POPULACE_US_SHA256", "AABBCC")

    pin = population.resolve_populace_pin("us")

    assert pin.revision == "custom-rev"
    assert pin.sha256 == "aabbcc"  # lower-cased
    # Unrelated fields keep their baseline values.
    assert pin.repo_id == "policyengine/populace-us"
    assert pin.filename == "populace_us_2024.h5"


def test_resolve_pin_partial_override_keeps_other_field(monkeypatch):
    _clear_populace_env(monkeypatch)
    monkeypatch.setenv("AXIOM_POPULACE_US_REVISION", "only-rev")

    pin = population.resolve_populace_pin("us")

    assert pin.revision == "only-rev"
    assert pin.sha256 == population.POPULACE_PINS["us"].sha256


def test_resolve_pin_unknown_country_is_none(monkeypatch):
    _clear_populace_env(monkeypatch)
    assert population.resolve_populace_pin("fr") is None


def test_resolve_pin_whitespace_override_is_treated_as_unset(monkeypatch):
    _clear_populace_env(monkeypatch)
    monkeypatch.setenv("AXIOM_POPULACE_US_REVISION", "   ")
    monkeypatch.setenv("AXIOM_POPULACE_US_SHA256", "\t")

    # A blank override must not collapse the pin to "" — it falls back to base.
    assert population.resolve_populace_pin("us") == population.POPULACE_PINS["us"]


# ---------------------------------------------------------------------------
# Resolution order: local override > pinned download > unpinned fallback
# ---------------------------------------------------------------------------
def test_load_prefers_pinned_download_by_default(monkeypatch, tmp_path):
    _clear_populace_env(monkeypatch)
    artifact = tmp_path / "populace_us_2024.h5"
    artifact.write_bytes(b"pinned-bytes")
    captured = _install_fake_hf_hub(monkeypatch, artifact)
    _stub_instantiate(monkeypatch)
    pin = population.POPULACE_PINS["us"]
    monkeypatch.setattr(population, "file_sha256", lambda path, **_: pin.sha256)

    provenance: dict[str, object] = {}
    dataset = population.load_populace_dataset(
        "us",
        year=2024,
        command="tax-populace-compare",
        provenance=provenance,
    )

    assert dataset.file_path == str(artifact)
    # hf_hub_download was called with the pinned revision + repo.
    assert captured["repo_id"] == pin.repo_id
    assert captured["filename"] == pin.filename
    assert captured["revision"] == pin.revision
    assert captured["repo_type"] == "dataset"
    assert provenance["source"] == population.SOURCE_PINNED
    assert provenance["revision"] == pin.revision
    assert provenance["sha256"] == pin.sha256[:12]
    assert provenance["built_with"] == pin.built_with


def test_local_override_takes_precedence_over_pin(monkeypatch, tmp_path):
    _clear_populace_env(monkeypatch)
    artifact = tmp_path / "populace_us_2024.h5"
    artifact.write_bytes(b"local-bytes")
    monkeypatch.setenv("AXIOM_POPULACE_US_2024_H5", str(artifact))
    _stub_instantiate(monkeypatch)
    # Matching digest -> no warning, source=local-override.
    pin = population.POPULACE_PINS["us"]
    monkeypatch.setattr(population, "file_sha256", lambda path, **_: pin.sha256)

    # If the pinned path were taken it would need huggingface_hub; ensure it is
    # absent so a regression that ignores the override fails loudly.
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)

    provenance: dict[str, object] = {}
    dataset = population.load_populace_dataset(
        "us",
        year=2024,
        command="tax-populace-compare",
        provenance=provenance,
    )

    assert dataset.file_path == str(artifact)
    assert provenance["source"] == population.SOURCE_LOCAL_OVERRIDE
    assert provenance["path"] == str(artifact)


def test_local_override_sha_mismatch_warns_but_loads(monkeypatch, tmp_path):
    _clear_populace_env(monkeypatch)
    artifact = tmp_path / "populace_us_2024.h5"
    artifact.write_bytes(b"experimental-bytes")
    monkeypatch.setenv("AXIOM_POPULACE_US_2024_H5", str(artifact))
    _stub_instantiate(monkeypatch)
    monkeypatch.setattr(population, "file_sha256", lambda path, **_: "0" * 64)

    with pytest.warns(UserWarning, match="does not match the certified pin"):
        dataset = population.load_populace_dataset(
            "us",
            year=2024,
            command="tax-populace-compare",
        )

    assert dataset.file_path == str(artifact)


# ---------------------------------------------------------------------------
# sha256 verification of the pinned download is fatal on mismatch
# ---------------------------------------------------------------------------
def test_pinned_download_fails_on_sha_mismatch(monkeypatch, tmp_path):
    _clear_populace_env(monkeypatch)
    artifact = tmp_path / "populace_us_2024.h5"
    artifact.write_bytes(b"tampered")
    _install_fake_hf_hub(monkeypatch, artifact)
    _stub_instantiate(monkeypatch)
    monkeypatch.setattr(population, "file_sha256", lambda path, **_: "deadbeef" * 8)

    with pytest.raises(SystemExit, match="sha256 mismatch"):
        population.load_populace_dataset(
            "us",
            year=2024,
            command="tax-populace-compare",
        )


def test_pinned_download_missing_hf_hub_exits_with_install_message(
    monkeypatch, tmp_path
):
    _clear_populace_env(monkeypatch)
    _stub_instantiate(monkeypatch)
    # Force ``import huggingface_hub`` to fail inside pinned_populace_download.
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)

    with pytest.raises(SystemExit, match="huggingface-hub"):
        population.load_populace_dataset(
            "us",
            year=2024,
            command="tax-populace-compare",
        )


def test_pinned_download_verifies_real_sha256_end_to_end(monkeypatch, tmp_path):
    """Exercise the real file_sha256 path (no monkeypatched digest)."""
    _clear_populace_env(monkeypatch)
    payload = b"real-artifact-bytes-for-hashing"
    import hashlib

    digest = hashlib.sha256(payload).hexdigest()
    artifact = tmp_path / "populace_us_2024.h5"
    artifact.write_bytes(payload)
    _install_fake_hf_hub(monkeypatch, artifact)
    _stub_instantiate(monkeypatch)
    monkeypatch.setenv("AXIOM_POPULACE_US_SHA256", digest)

    provenance: dict[str, object] = {}
    population.load_populace_dataset(
        "us",
        year=2024,
        command="tax-populace-compare",
        provenance=provenance,
    )

    assert provenance["source"] == population.SOURCE_PINNED
    assert provenance["sha256"] == digest[:12]


# ---------------------------------------------------------------------------
# Unpinned escape hatch gating
# ---------------------------------------------------------------------------
def test_unpinned_fallback_disabled_by_default_raises_with_278(monkeypatch):
    _clear_populace_env(monkeypatch)
    # Country with no pin -> pinned path is unavailable, so the loader must hit
    # the escape-hatch gate rather than silently falling through.
    with pytest.raises(SystemExit) as excinfo:
        population.load_populace_dataset(
            "fr",
            year=2024,
            command="tax-populace-compare",
        )
    message = str(excinfo.value)
    assert "populace#278" in message
    assert population.ALLOW_UNPINNED_ENV in message


def _install_fake_populace(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = ModuleType("populace")
    data_module = ModuleType("populace.data")

    def fake_load(country, year):
        return SimpleNamespace(country=country, year=year, unpinned=True)

    data_module.load = fake_load  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "populace", fake)
    monkeypatch.setitem(sys.modules, "populace.data", data_module)


def test_unpinned_fallback_allowed_warns_and_loads(monkeypatch):
    _clear_populace_env(monkeypatch)
    monkeypatch.setenv(population.ALLOW_UNPINNED_ENV, "1")
    _install_fake_populace(monkeypatch)

    provenance: dict[str, object] = {}
    with pytest.warns(UserWarning, match="populace#278"):
        dataset = population.load_populace_dataset(
            "fr",
            year=2024,
            command="tax-populace-compare",
            provenance=provenance,
        )

    assert dataset.unpinned is True
    assert provenance["source"] == population.SOURCE_UNPINNED


def test_unpinned_escape_hatch_overrides_pin_for_pinned_country(monkeypatch):
    """The escape hatch is checked *before* the pin, so an operator can force
    HF-latest even for a country (US) that has a certified pin."""
    _clear_populace_env(monkeypatch)
    monkeypatch.setenv(population.ALLOW_UNPINNED_ENV, "1")
    _install_fake_populace(monkeypatch)
    # If the pinned path were taken it would import huggingface_hub; make it
    # absent so a regression that ignores the escape hatch fails loudly.
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)

    provenance: dict[str, object] = {}
    with pytest.warns(UserWarning, match="populace#278"):
        dataset = population.load_populace_dataset(
            "us",
            year=2024,
            command="tax-populace-compare",
            provenance=provenance,
        )

    assert dataset.unpinned is True
    assert provenance["source"] == population.SOURCE_UNPINNED


def test_unpinned_fallback_allowed_flag_variants(monkeypatch):
    _clear_populace_env(monkeypatch)
    for truthy in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv(population.ALLOW_UNPINNED_ENV, truthy)
        assert population.unpinned_fallback_allowed() is True
    for falsy in ("", "0", "false", "no", "off"):
        monkeypatch.setenv(population.ALLOW_UNPINNED_ENV, falsy)
        assert population.unpinned_fallback_allowed() is False


# ---------------------------------------------------------------------------
# Existing local-artifact / env-override behavior (retained)
# ---------------------------------------------------------------------------
def test_local_populace_artifact_prefers_specific_env(monkeypatch, tmp_path):
    _clear_populace_env(monkeypatch)
    artifact = tmp_path / "populace_us_2024.h5"
    artifact.write_text("")
    monkeypatch.setenv("AXIOM_POPULACE_US_2024_H5", str(artifact))

    assert population.local_populace_artifact_path("US", year=2024) == artifact


def test_local_populace_artifact_rejects_missing_env_override(monkeypatch, tmp_path):
    _clear_populace_env(monkeypatch)
    missing = tmp_path / "missing.h5"
    monkeypatch.setenv("AXIOM_POPULACE_US_H5", str(missing))

    with pytest.raises(FileNotFoundError, match="AXIOM_POPULACE_US_H5"):
        population.local_populace_artifact_path("us", year=2024)


def test_load_populace_dataset_exits_for_missing_env_override(monkeypatch, tmp_path):
    _clear_populace_env(monkeypatch)
    missing = tmp_path / "missing.h5"
    monkeypatch.setenv("AXIOM_POPULACE_US_H5", str(missing))

    with pytest.raises(SystemExit, match="AXIOM_POPULACE_US_H5"):
        population.load_populace_dataset(
            "us",
            year=2024,
            command="tax-populace-compare",
        )


def test_local_populace_artifact_no_longer_scans_hf_cache(monkeypatch, tmp_path):
    """The default resolver returns None with no env override; the HF-cache scan
    moved behind the unpinned escape hatch (``unpinned_huggingface_cache_artifact``)."""
    _clear_populace_env(monkeypatch)
    cache_root = tmp_path / "hub"
    repo = cache_root / "datasets--policyengine--populace-us"
    snapshot = repo / "snapshots" / "abc123"
    snapshot.mkdir(parents=True)
    artifact = snapshot / "populace_us_2024.h5"
    artifact.write_text("")
    refs = repo / "refs"
    refs.mkdir()
    (refs / "main").write_text("abc123\n")

    assert (
        population.local_populace_artifact_path(
            "us",
            year=2024,
            cache_root=cache_root,
        )
        is None
    )
    # The scan still works when invoked explicitly (the unpinned path uses it).
    assert (
        population.unpinned_huggingface_cache_artifact(
            "us",
            year=2024,
            cache_root=cache_root,
        )
        == artifact
    )


def test_load_populace_dataset_uses_local_engine_dataset_without_populace_data(
    monkeypatch, tmp_path
):
    _clear_populace_env(monkeypatch)
    artifact = tmp_path / "populace_us_2024.h5"
    artifact.write_bytes(b"local-artifact")
    monkeypatch.setenv("AXIOM_POPULACE_US_2024_H5", str(artifact))
    # Matching pin digest keeps the load quiet (no mismatch warning).
    monkeypatch.setattr(
        population,
        "file_sha256",
        lambda path, **_: population.POPULACE_PINS["us"].sha256,
    )
    imports: list[str] = []

    class FakeDataset:
        def __init__(self, *, file_path: str):
            self.file_path = file_path

    def fake_import_module(name: str) -> SimpleNamespace:
        imports.append(name)
        return SimpleNamespace(USSingleYearDataset=FakeDataset)

    monkeypatch.setattr(population, "import_module", fake_import_module)

    dataset = population.load_populace_dataset(
        "us",
        year=2024,
        command="tax-populace-compare",
    )

    assert dataset.file_path == str(artifact)
    assert imports == ["policyengine_us.data"]


# ---------------------------------------------------------------------------
# file_sha256 + provenance formatting
# ---------------------------------------------------------------------------
def test_file_sha256_matches_hashlib(tmp_path):
    import hashlib

    payload = b"x" * (2 * 1024 * 1024 + 7)  # spans multiple chunks
    path = tmp_path / "blob.bin"
    path.write_bytes(payload)

    assert population.file_sha256(path) == hashlib.sha256(payload).hexdigest()


def test_format_dataset_identity_pinned_hides_path():
    line = population.format_dataset_identity(
        {
            "source": population.SOURCE_PINNED,
            "revision": "rev-1",
            "sha256": "abc123def456",
            "built_with": "1.729.0",
            "path": "/cache/x.h5",
        }
    )
    assert "source=pinned" in line
    assert "revision=rev-1" in line
    assert "sha256=abc123def456" in line
    assert "built_with_pe=1.729.0" in line
    assert "path=" not in line  # noise for the pinned cache path


def test_format_dataset_identity_local_override_shows_path():
    line = population.format_dataset_identity(
        {
            "source": population.SOURCE_LOCAL_OVERRIDE,
            "revision": None,
            "sha256": "deadbeef0000",
            "path": "/tmp/experiment.h5",
        }
    )
    assert "source=local-override" in line
    assert "path=/tmp/experiment.h5" in line


def test_format_dataset_identity_empty_is_blank():
    assert population.format_dataset_identity(None) == ""
    assert population.format_dataset_identity({}) == ""
