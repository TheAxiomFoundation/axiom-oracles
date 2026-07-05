"""PolicyEngine population loaders for Axiom validation oracles.

Loading is *pinned by default*. A published Populace artifact is only trusted
when it matches a verified ``(repo_id, filename, revision, sha256)`` pin, so an
oracle run compares against known input bases rather than whatever Hugging Face
currently serves as ``latest``. See :data:`POPULACE_PINS` for the certified pins
and the resolution order documented on :func:`load_populace_dataset`.

Why pinning matters: ``populace.data.load()`` (populace-data 0.1.0) always
fetches the HF-latest revision with no pin. As of 2026-07-02 HF-latest for the
US dataset is a *sparse* refit that zeroes untargeted input bases (IRA/HSA/
self-employed pension/childcare and dozens of other engine inputs) per
PolicyEngine/populace#278. Comparing an encoder oracle against that artifact
would silently score against ~$0 bases. The dense certified pin below is the
last artifact verified to carry those inputs.
"""

from __future__ import annotations

import hashlib
import os
import warnings
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

DEFAULT_US_POPULACE_YEAR = 2024
DEFAULT_UK_POPULACE_YEAR = 2023
DEFAULT_LOCAL_POPULACE_DATA_PACKAGE = (
    Path.home() / "PolicyEngine" / "populace" / "packages" / "populace-data"
)
DEFAULT_HUGGINGFACE_CACHE_ROOT = Path.home() / ".cache" / "huggingface" / "hub"
DEFAULT_POPULACE_YEARS = {
    "us": DEFAULT_US_POPULACE_YEAR,
    "uk": DEFAULT_UK_POPULACE_YEAR,
}
POLICYENGINE_DATASET_CLASSES = {
    "us": ("policyengine_us.data", "USSingleYearDataset"),
    "uk": ("policyengine_uk.data", "UKSingleYearDataset"),
}

#: Escape-hatch env var. When set truthy, the loader is allowed to fall back to
#: the unpinned ``populace.data.load()`` package and the Hugging Face cache scan
#: (both of which resolve to HF-latest, i.e. the sparse #278 artifact for the US
#: dataset). Off by default: unpinned data is opt-in, never a silent fallback.
ALLOW_UNPINNED_ENV = "AXIOM_POPULACE_ALLOW_UNPINNED"

#: Provenance ``source`` values recorded for each loaded artifact.
SOURCE_PINNED = "pinned"
SOURCE_LOCAL_OVERRIDE = "local-override"
SOURCE_UNPINNED = "unpinned"


@dataclass(frozen=True)
class PopulacePin:
    """A verified Populace artifact pin.

    ``sha256`` is the digest of the artifact file itself (verified after
    download); ``built_with`` is the PolicyEngine model-package version the
    artifact was calibrated with, recorded for provenance and compatibility
    notes. ``repo_type`` is the Hugging Face repo type passed to
    ``hf_hub_download`` (datasets are ``"dataset"``).
    """

    country: str
    repo_id: str
    filename: str
    revision: str
    sha256: str
    built_with: str
    repo_type: str = "dataset"


# ---------------------------------------------------------------------------
# UPGRADE NOTE
# ---------------------------------------------------------------------------
# These pins are the *dense* certified Populace artifacts (verified 2026-07-02
# against policyengine.py's certified bundle manifest at bundle 4.18.6 / tag
# 4.18.0 history: src/policyengine/data/bundle/manifest.json). They intentionally
# predate the sparse-l0-refit artifact that is currently HF-latest, because that
# sparse artifact zeroes untargeted engine input bases (PolicyEngine/populace#278,
# closed 2026-07-02 by pipeline-fix PR #279 — but the rebuilt dense-parity
# artifact is not yet published/certified).
#
# RE-PIN WHEN: a post-#279 sparse (or dense-parity) Populace release is certified
# as the default in the policyengine.py bundle. At that point, read the new
# (repo_id, filename, revision, sha256, built_with_model_version) out of that
# bundle's manifest.json certified_data_artifact/datasets block and update the
# values below. Do NOT bump to HF-latest without going through that certification.
# For a one-off re-pin without a code change, set the env overrides:
#   AXIOM_POPULACE_US_REVISION / AXIOM_POPULACE_US_SHA256 (and UK equivalents).
# ---------------------------------------------------------------------------
POPULACE_PINS: dict[str, PopulacePin] = {
    "us": PopulacePin(
        country="us",
        repo_id="policyengine/populace-us",
        filename="populace_us_2024.h5",
        revision="populace-us-2024-f0af251-703bd81a565c-20260620T201958Z",
        sha256="16be6338f9d0b3c339883dae59949e995663b64cf145de6728b3dd0f916c5d5f",
        built_with="1.729.0",
    ),
    "uk": PopulacePin(
        country="uk",
        repo_id="policyengine/populace-uk-private",
        filename="populace_uk_2023.h5",
        revision="populace-uk-2023-dd68c73-4aa4b14-20260619T023711Z",
        sha256="f17306ccb2aad7ff0130be3589b560afb2e2a12a943570911cd0c77f07934833",
        built_with="2.89.2",
    ),
}


def load_populace_dataset(
    country: str,
    *,
    year: int | None = None,
    command: str,
    provenance: dict[str, Any] | None = None,
) -> Any:
    """Load a published Populace artifact as a PolicyEngine dataset.

    Resolution order (first match wins):

    1. **Explicit local override** — an ``AXIOM_POPULACE_*`` env var pointing at
       a local ``.h5``. Kept for development/experiments. The file's sha256 is
       compared against the country pin; a mismatch logs a *loud warning* but
       does not fail (local overrides are expected to differ from the pin).
       Recorded as ``source="local-override"``.
    2. **Unpinned escape hatch** — only when ``AXIOM_POPULACE_ALLOW_UNPINNED`` is
       set truthy: ``populace.data.load()`` (and, via the cache scan, HF-latest —
       the sparse #278 artifact for the US dataset). Checked *before* the pin so
       an operator can deliberately test a new release; emits a warning naming
       populace#278. Recorded as ``source="unpinned"``. Never reached silently.
    3. **Pinned Hugging Face download** (the default) — ``hf_hub_download`` at the
       pinned ``revision``, followed by sha256 verification against the pin. A
       mismatch is fatal. Recorded as ``source="pinned"``.
    4. **No pin + no escape hatch** — fails with ``SystemExit`` pointing at the
       pin and the escape hatch, rather than silently resolving to HF-latest.

    When ``provenance`` is a dict it is populated in place with
    ``{source, path, sha256, revision, built_with}`` (``sha256`` truncated to 12
    hex chars) so callers can thread dataset identity into comparison outputs.
    Passing ``None`` (the default) keeps every existing call site unchanged.
    """
    country = country.lower()
    sink = provenance if provenance is not None else None

    # (1) Explicit local override — verify against the pin, warn (don't fail).
    try:
        local_artifact = local_populace_artifact_path(country, year=year)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc
    if local_artifact is not None:
        # Hash once: verification and provenance share the digest (the artifact
        # can be multi-GB, so a second full-file read is worth avoiding).
        local_sha256 = _verify_local_override_against_pin(country, local_artifact)
        _record_provenance(
            sink,
            source=SOURCE_LOCAL_OVERRIDE,
            path=local_artifact,
            revision=None,
            country=country,
            sha256=local_sha256,
        )
        return _instantiate_dataset(country, local_artifact, command)

    # (2) Unpinned escape hatch — opt-in only. Checked before the pin so an
    # operator can *deliberately* load HF-latest (e.g. to test a new release)
    # even for a country that has a certified pin. It is never reached silently:
    # AXIOM_POPULACE_ALLOW_UNPINNED must be set truthy.
    pin = resolve_populace_pin(country)
    if unpinned_fallback_allowed():
        warnings.warn(unpinned_fallback_warning(country), stacklevel=2)
        resolved_year = (
            year if year is not None else DEFAULT_POPULACE_YEARS.get(country)
        )
        dataset = _load_unpinned_populace(country, resolved_year, command)
        _record_provenance(
            sink,
            source=SOURCE_UNPINNED,
            path=None,
            revision="latest" if resolved_year is None else str(resolved_year),
            country=country,
        )
        return dataset

    # (3) Pinned Hugging Face download — the default trusted path.
    if pin is not None:
        pinned_path = pinned_populace_download(pin, command=command)
        _record_provenance(
            sink,
            source=SOURCE_PINNED,
            path=pinned_path,
            revision=pin.revision,
            country=country,
            sha256=pin.sha256,
            built_with=pin.built_with,
        )
        return _instantiate_dataset(country, pinned_path, command)

    # (4) No pin for this country and the escape hatch is off — fail loudly
    # rather than silently resolving to HF-latest.
    raise SystemExit(unpinned_disallowed_message(country, command))


def resolve_populace_pin(country: str) -> PopulacePin | None:
    """Return the effective pin for ``country``, applying env re-pin overrides.

    ``AXIOM_POPULACE_{CC}_REVISION`` and ``AXIOM_POPULACE_{CC}_SHA256`` (with
    ``{CC}`` the upper-cased country token, e.g. ``US``/``UK``) let an operator
    re-pin to a different certified release without a code change. Either may be
    set independently; unset fields keep the baseline pin value.
    """
    country = country.lower()
    base = POPULACE_PINS.get(country)
    if base is None:
        return None
    token = country.upper().replace("-", "_")
    # Treat whitespace-only overrides as unset so a blank env var can never
    # collapse the pinned revision/sha to "" (which would resolve to HF-latest
    # or fail verification). Empty string -> fall back to the baseline field.
    revision = (os.environ.get(f"AXIOM_POPULACE_{token}_REVISION") or "").strip()
    sha256 = (os.environ.get(f"AXIOM_POPULACE_{token}_SHA256") or "").strip().lower()
    if not revision and not sha256:
        return base
    return PopulacePin(
        country=base.country,
        repo_id=base.repo_id,
        filename=base.filename,
        revision=revision or base.revision,
        sha256=sha256 or base.sha256,
        built_with=base.built_with,
        repo_type=base.repo_type,
    )


def pinned_populace_download(pin: PopulacePin, *, command: str) -> Path:
    """Download the pinned artifact from Hugging Face and verify its sha256.

    Raises ``SystemExit`` when ``huggingface_hub`` is unavailable, when the
    download fails, or when the downloaded file's digest does not match
    ``pin.sha256`` (a mismatch here is fatal — the pin is the contract).
    """
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise SystemExit(huggingface_hub_install_message(pin.country, command)) from exc
    try:
        downloaded = hf_hub_download(
            repo_id=pin.repo_id,
            filename=pin.filename,
            revision=pin.revision,
            repo_type=pin.repo_type,
        )
    except Exception as exc:  # pragma: no cover - depends on external HF access
        raise SystemExit(
            f"Failed to download pinned Populace {pin.country.upper()} artifact "
            f"{pin.repo_id}/{pin.filename}@{pin.revision}: {exc}"
        ) from exc
    path = Path(downloaded)
    actual = file_sha256(path)
    if actual.lower() != pin.sha256.lower():
        raise SystemExit(
            f"Pinned Populace {pin.country.upper()} artifact sha256 mismatch for "
            f"{pin.repo_id}/{pin.filename}@{pin.revision}: expected {pin.sha256}, "
            f"got {actual}. Refusing to load an artifact that does not match the "
            f"pin. If you intentionally re-pinned, set AXIOM_POPULACE_"
            f"{pin.country.upper()}_SHA256 to the new digest."
        )
    return path


def unpinned_fallback_allowed() -> bool:
    """Return True when the unpinned escape hatch env var is set truthy."""
    value = os.environ.get(ALLOW_UNPINNED_ENV, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _load_unpinned_populace(country: str, year: int | None, command: str) -> Any:
    """Load via the unpinned ``populace.data.load`` package (HF-latest)."""
    try:
        from populace.data import load
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise SystemExit(populace_install_message(country, command)) from exc
    try:
        return load(country, year)
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise SystemExit(populace_install_message(country, command)) from exc
    except Exception as exc:  # pragma: no cover - depends on external dataset access
        year_label = "latest" if year is None else str(year)
        raise SystemExit(
            f"Failed to load Populace {country.upper()} {year_label} dataset: {exc}"
        ) from exc


def _instantiate_dataset(country: str, path: Path, command: str) -> Any:
    """Instantiate the PolicyEngine dataset class for a local artifact path."""
    try:
        return load_policyengine_dataset_artifact(country, path)
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise SystemExit(
            policyengine_dataset_install_message(country, command)
        ) from exc
    except Exception as exc:  # pragma: no cover - depends on external dataset shape
        raise SystemExit(
            f"Failed to load Populace {country.upper()} artifact {path}: {exc}"
        ) from exc


def _verify_local_override_against_pin(country: str, path: Path) -> str:
    """Warn loudly when a local-override artifact's sha256 differs from the pin.

    Local overrides are for experiments, so a mismatch is a warning, not a
    failure. A *matching* digest is silent (the override just re-supplies the
    pinned artifact). Returns the computed digest so the caller can reuse it for
    provenance without re-reading a potentially multi-GB file.
    """
    actual = file_sha256(path)
    pin = resolve_populace_pin(country)
    if pin is None or actual.lower() == pin.sha256.lower():
        return actual
    warnings.warn(
        f"Local Populace {country.upper()} override {path} sha256 {actual[:12]} "
        f"does not match the certified pin {pin.sha256[:12]} "
        f"(revision {pin.revision}). Loading the override anyway; oracle results "
        f"will reflect this unpinned artifact, not the certified dataset.",
        stacklevel=3,
    )
    return actual


def _record_provenance(
    sink: dict[str, Any] | None,
    *,
    source: str,
    path: Path | None,
    revision: str | None,
    country: str,
    sha256: str | None = None,
    built_with: str | None = None,
) -> None:
    """Populate a caller-supplied provenance sink in place (no-op when None)."""
    if sink is None:
        return
    digest = sha256
    if digest is None and path is not None:
        try:
            digest = file_sha256(path)
        except OSError:
            digest = None
    sink.clear()
    sink.update(
        {
            "country": country,
            "source": source,
            "path": str(path) if path is not None else None,
            "sha256": digest[:12] if digest else None,
            "revision": revision,
            "built_with": built_with,
        }
    )


def format_dataset_identity(identity: dict[str, Any] | None) -> str:
    """Render a one-line ``Dataset:`` provenance string for human-readable output.

    Returns an empty string when ``identity`` is falsy so callers can guard on
    it. The shape matches the sink from :func:`load_populace_dataset`.
    """
    if not identity:
        return ""
    source = identity.get("source") or "unknown"
    parts = [f"source={source}"]
    revision = identity.get("revision")
    if revision:
        parts.append(f"revision={revision}")
    sha256 = identity.get("sha256")
    if sha256:
        parts.append(f"sha256={sha256}")
    built_with = identity.get("built_with")
    if built_with:
        parts.append(f"built_with_pe={built_with}")
    path = identity.get("path")
    if path and source != SOURCE_PINNED:
        parts.append(f"path={path}")
    return "Dataset: " + " ".join(parts)


def file_sha256(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 hex digest of a file, read in chunks."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_policyengine_dataset_artifact(country: str, path: Path) -> Any:
    """Load a local Populace H5 artifact using its PolicyEngine dataset class."""
    country = country.lower()
    dataset_spec = POLICYENGINE_DATASET_CLASSES.get(country)
    if dataset_spec is None:
        raise ValueError(
            f"No PolicyEngine dataset loader is configured for {country!r}."
        )
    module_name, class_name = dataset_spec
    dataset_class = getattr(import_module(module_name), class_name)
    return dataset_class(file_path=str(path))


def population_table(dataset: Any, name: str) -> Any:
    """Return an entity table from a PolicyEngine dataset object."""
    table = getattr(dataset, name, None)
    if table is None and hasattr(dataset, "data"):
        table = getattr(dataset.data, name, None)
    if table is None:
        raise ValueError(f"Populace dataset does not expose {name!r} table.")
    return table.copy() if hasattr(table, "copy") else table


def local_dataset_path(value: str | None) -> Path | None:
    """Return ``value`` as a local dataset path when it names an existing file."""
    if not value:
        return None
    path = Path(value).expanduser()
    if path.exists():
        return path
    return None


def local_populace_artifact_path(
    country: str,
    *,
    year: int | None = None,
    cache_root: Path | None = None,
) -> Path | None:
    """Return the explicit local Populace artifact override for ``country``.

    Resolves *only* ``AXIOM_POPULACE_*`` env-var overrides. The Hugging Face
    cache scan is intentionally gated behind the unpinned escape hatch and lives
    in :func:`unpinned_huggingface_cache_artifact`, so it is not reached here on
    the default (pinned) path.
    """
    country = country.lower()
    resolved_year = year or DEFAULT_POPULACE_YEARS.get(country)
    for env_var in local_populace_artifact_env_vars(country, resolved_year):
        override = os.environ.get(env_var)
        if not override:
            continue
        path = Path(override).expanduser()
        if not path.exists():
            raise FileNotFoundError(
                f"{env_var} points to a missing Populace artifact: {path}"
            )
        return path
    return None


def local_populace_artifact_env_vars(country: str, year: int | None) -> tuple[str, ...]:
    country_token = country.upper().replace("-", "_")
    names: list[str] = []
    if year is not None:
        names.append(f"AXIOM_POPULACE_{country_token}_{year}_H5")
    names.extend(
        [
            f"AXIOM_POPULACE_{country_token}_H5",
            "AXIOM_POPULACE_H5",
            "AXIOM_POPULACE_DATASET",
            "AXIOM_POPULACE_DATA_PATH",
        ]
    )
    return tuple(names)


def populace_artifact_filename(country: str, year: int) -> str:
    return f"populace_{country.lower()}_{int(year)}.h5"


def unpinned_huggingface_cache_artifact(
    country: str,
    *,
    year: int | None = None,
    cache_root: Path | None = None,
) -> Path | None:
    """Resolve a Populace artifact from the Hugging Face cache (unpinned).

    This is the HF-latest cache scan. It is *not* part of the default pinned
    path; the unpinned fallback uses it only when
    ``AXIOM_POPULACE_ALLOW_UNPINNED`` is set.
    """
    resolved_year = year or DEFAULT_POPULACE_YEARS.get(country)
    if resolved_year is None:
        return None
    return huggingface_cache_populace_artifact(
        country,
        populace_artifact_filename(country, resolved_year),
        cache_root=cache_root,
    )


def huggingface_cache_populace_artifact(
    country: str,
    filename: str,
    *,
    cache_root: Path | None = None,
) -> Path | None:
    """Resolve a Populace artifact already present in the Hugging Face cache."""
    root = cache_root or DEFAULT_HUGGINGFACE_CACHE_ROOT
    repo_cache = root / f"datasets--policyengine--populace-{country.lower()}"
    snapshots = repo_cache / "snapshots"
    refs = repo_cache / "refs"
    for ref in huggingface_cache_refs(refs):
        try:
            revision = ref.read_text().strip()
        except OSError:
            continue
        if not revision:
            continue
        candidate = snapshots / revision / filename
        if candidate.exists():
            return candidate
    if not snapshots.exists():
        return None
    candidates = [path for path in snapshots.glob(f"*/{filename}") if path.exists()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def huggingface_cache_refs(refs: Path) -> tuple[Path, ...]:
    if not refs.exists():
        return ()
    main = refs / "main"
    others = sorted(
        (path for path in refs.iterdir() if path.is_file() and path != main),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if main.exists():
        return (main, *others)
    return tuple(others)


def huggingface_hub_install_message(country: str, command: str) -> str:
    return (
        "Pinned Populace validation requires huggingface-hub and the matching "
        "PolicyEngine country engine. Run with: "
        f"uv run --with huggingface-hub --with {populace_data_requirement(country)} "
        f"axiom-encode {command}"
    )


def unpinned_disallowed_message(country: str, command: str) -> str:
    pin = resolve_populace_pin(country)
    pin_hint = (
        f" The certified pin is {pin.repo_id}/{pin.filename}@{pin.revision}."
        if pin is not None
        else ""
    )
    return (
        f"No pinned Populace {country.upper()} artifact could be loaded and the "
        f"unpinned fallback is disabled. Unpinned loading resolves to HF-latest, "
        f"which for the US dataset is the sparse artifact that zeroes untargeted "
        f"engine input bases (PolicyEngine/populace#278). To knowingly load "
        f"unpinned data, re-run with {ALLOW_UNPINNED_ENV}=1." + pin_hint
    )


def unpinned_fallback_warning(country: str) -> str:
    return (
        f"{ALLOW_UNPINNED_ENV} is set: loading UNPINNED Populace {country.upper()} "
        f"data (HF-latest). For the US dataset this is the sparse refit that "
        f"zeroes untargeted engine input bases (PolicyEngine/populace#278); oracle "
        f"comparisons against it may score against ~$0 bases. Prefer the certified "
        f"pin unless you are deliberately testing the latest release."
    )


def populace_install_message(country: str, command: str) -> str:
    return (
        "Populace validation requires populace-data and the matching "
        "PolicyEngine country engine. Run with: "
        f"uv run --with {populace_data_requirement(country)} "
        f"axiom-encode {command}"
    )


def policyengine_dataset_install_message(country: str, command: str) -> str:
    return (
        "Populace validation found a local artifact but requires the matching "
        "PolicyEngine country engine. Run with: "
        f"uv run --with {populace_data_requirement(country)} "
        f"axiom-encode {command}"
    )


def populace_data_requirement(country: str) -> str:
    """Return the best uv requirement string for the local Populace data shard."""
    country = country.lower()
    override = os.environ.get("AXIOM_POPULACE_DATA_PACKAGE")
    if override:
        return f"{Path(override).expanduser()}[{country}]"
    if DEFAULT_LOCAL_POPULACE_DATA_PACKAGE.exists():
        return f"{DEFAULT_LOCAL_POPULACE_DATA_PACKAGE}[{country}]"
    return f"populace-data[{country}]"
