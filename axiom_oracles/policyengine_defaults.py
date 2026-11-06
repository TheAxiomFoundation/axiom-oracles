"""Reviewed package versions for comparisons that use the default US oracle.

The manifest is the input to the weekly update proposal. Explicit suite
versions and the encoder's historical population environments remain separate.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Mapping

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version


SCHEMA = 1
PACKAGE_NAMES = (
    "policyengine",
    "policyengine-us",
    "policyengine-core",
    "spm-calculator",
)
PE_PACKAGE_NAMES = PACKAGE_NAMES[:3]
MANIFEST_RELATIVE_PATH = Path("data/policyengine_defaults.json")
DEFAULTS_PATH = Path(__file__).resolve().parents[1] / MANIFEST_RELATIVE_PATH
DEFAULT_REQUIREMENTS_PATH = (
    Path(__file__).resolve().parents[1] / "requirements/policyengine-defaults.txt"
)


def validate_defaults(document: object) -> dict[str, str]:
    """Return the four exact, stable package versions or reject the manifest."""
    if not isinstance(document, dict) or set(document) != {"schema", "packages"}:
        raise ValueError("oracle defaults must contain exactly schema and packages")
    if type(document["schema"]) is not int or document["schema"] != SCHEMA:
        raise ValueError(f"oracle defaults schema must be {SCHEMA}")
    packages = document["packages"]
    if not isinstance(packages, dict) or set(packages) != set(PACKAGE_NAMES):
        raise ValueError(
            "oracle defaults packages must contain exactly " + ", ".join(PACKAGE_NAMES)
        )
    for name in PACKAGE_NAMES:
        value = packages[name]
        if not isinstance(value, str):
            raise ValueError(f"{name} must be an exact stable version string")
        try:
            version = Version(value)
        except InvalidVersion as exc:
            raise ValueError(f"{name} must be an exact stable version string") from exc
        if (
            str(version) != value
            or version.is_prerelease
            or version.is_devrelease
            or version.local is not None
        ):
            raise ValueError(f"{name} must be an exact stable version string")
    return {name: packages[name] for name in PACKAGE_NAMES}


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate manifest field: {key}")
        result[key] = value
    return result


def load_defaults(path: Path | str | None = None) -> dict[str, str]:
    """Read and validate a manifest without accepting silent fallback versions."""
    source = DEFAULTS_PATH if path is None else Path(path)
    try:
        document = json.loads(source.read_text(), object_pairs_hook=_unique_object)
        return validate_defaults(document)
    except (OSError, ValueError) as exc:
        raise ValueError(f"{source}: {exc}") from exc


def pe_pins(packages: Mapping[str, str]) -> tuple[str, str, str]:
    """The wrapper, US model and core requirement strings, in runner order."""
    return tuple(f"{name}=={packages[name]}" for name in PE_PACKAGE_NAMES)


def validate_requirements_lock(text: str, packages: Mapping[str, str]) -> None:
    """Require hash-bearing exact pins and the manifest's complete profile.

    This is a static data check. ``uv run --with-requirements`` freezes the
    selected versions, but does not enforce these hashes; the update probe's
    separate ``uv pip sync --require-hashes`` verifies its tested environment.
    """
    if len(text.encode()) > 2_000_000:
        raise ValueError("default requirements lock exceeds 2 MB")
    versions = {}
    for line in text.replace("\\\n", " ").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        hashes = re.findall(r"(?:^|\s)--hash=sha256:([0-9a-f]{64})(?=\s|$)", line)
        requirement_text = re.sub(r"\s+--hash=sha256:[0-9a-f]{64}(?=\s|$)", "", line)
        if not hashes or "--" in requirement_text:
            raise ValueError("every default requirement must have only SHA-256 hash options")
        try:
            requirement = Requirement(requirement_text)
        except InvalidRequirement as exc:
            raise ValueError("default requirements must contain exact package pins") from exc
        specifiers = list(requirement.specifier)
        if (
            requirement.url
            or requirement.extras
            or requirement.marker is not None
            or len(specifiers) != 1
            or specifiers[0].operator != "=="
            or "*" in specifiers[0].version
        ):
            raise ValueError("default requirements must contain unconditional exact public-index pins")
        version = Version(specifiers[0].version)
        if version.is_prerelease or version.is_devrelease or version.local is not None:
            raise ValueError("default requirements must contain stable versions")
        name = canonicalize_name(requirement.name)
        if name in versions:
            raise ValueError(f"default requirements contain duplicate package {name}")
        versions[name] = str(version)
    if not versions:
        raise ValueError("default requirements lock is empty")
    expected = validate_defaults({"schema": SCHEMA, "packages": dict(packages)})
    if any(versions.get(name) != version for name, version in expected.items()):
        raise ValueError("default requirements lock does not match the manifest package versions")
