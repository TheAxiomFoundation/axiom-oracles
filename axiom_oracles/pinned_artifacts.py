"""Pinned PolicyEngine artifacts that PyPI's index no longer lists.

PolicyEngine prunes old ``policyengine-us`` releases from PyPI's index. A
pruned release no longer resolves by version (``uv run --with
policyengine-us==1.752.2`` fails with "no version of policyengine-us"), but
files.pythonhosted.org still serves its files at their hashed URLs. This
table records the hashed URL and SHA-256 of each pruned file a comparison
installs, so the comparison keeps running on the exact release it pins
instead of being re-pinned to a release whose numbers differ.

Every runtime install of a PolicyEngine-family pin goes through
:func:`requirement` (``scripts/run_comparison.py``'s ``uv run --with``
arguments and ``scripts/debug_policyengine_env.py``). A pin listed here is
downloaded once, checked against the recorded SHA-256, and handed to uv as a
local wheel; a pin not listed here is passed through unchanged and resolves
from the index. The CI install of the ``policyengine`` extra reads the same
files from ``uv.lock``; ``tests/test_pinned_artifacts.py`` keeps the two in
agreement.

Each URL and hash comes from a ``uv.lock`` this repository committed, so the
SHA-256 is the one uv recorded when the release was still on the index.
``scripts/check_pinned_artifacts.py`` fails, naming the file that pins it,
when a recorded file stops downloading or when a runtime pin is neither on
the index nor in this table.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PinnedArtifact:
    """One pruned distribution file, addressed by its hashed URL."""

    name: str
    version: str
    url: str
    sha256: str
    #: Where the URL and hash were recorded (a commit of uv.lock).
    recorded_in: str

    @property
    def filename(self) -> str:
        return self.url.rsplit("/", 1)[-1]


#: The one table of pruned PolicyEngine files. Wheels only: uv installs a
#: local wheel without building it.
PRUNED_ARTIFACTS: tuple[PinnedArtifact, ...] = (
    PinnedArtifact(
        name="policyengine-us",
        version="1.752.2",
        url=(
            "https://files.pythonhosted.org/packages/7f/85/"
            "bbee92f747a382779bae41a67da39fa5a8592d068853a64226279e6c32a7/"
            "policyengine_us-1.752.2-py3-none-any.whl"
        ),
        sha256="7e30468ae369ddd14e5d834c12cacbc5b5159c809b0990caf204c0747ef4c096",
        # d9ada03d72 added it; 29cb47dad4 replaced it with 1.764.6.
        recorded_in="uv.lock at 678dd840b4",
    ),
    PinnedArtifact(
        name="policyengine-us",
        version="1.764.6",
        url=(
            "https://files.pythonhosted.org/packages/e2/5a/"
            "0566666f30ad06e416f0cf25b24bdee73acd71897fb2de3c0ac43b59e3e3/"
            "policyengine_us-1.764.6-py3-none-any.whl"
        ),
        sha256="2b2c5c02c26ab212270948db1f30129728b625fc6109fc9ca0c604b714546909",
        recorded_in="uv.lock (the policyengine extra, since 29cb47dad4)",
    ),
)

CACHE_ENV = "AXIOM_ORACLES_ARTIFACT_CACHE"


class PinnedArtifactError(RuntimeError):
    """A pinned file could not be downloaded or did not match its SHA-256."""


def _normalize(name: str) -> str:
    return name.strip().lower().replace("_", "-").replace(".", "-")


def lookup(name: str, version: str) -> PinnedArtifact | None:
    """The table entry for ``name==version``, or None when it is not pruned."""
    key = (_normalize(name), version.strip())
    for artifact in PRUNED_ARTIFACTS:
        if (_normalize(artifact.name), artifact.version) == key:
            return artifact
    return None


def cache_dir() -> Path:
    override = os.environ.get(CACHE_ENV)
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "axiom-oracles" / "pinned-artifacts"


def cache_path(artifact: PinnedArtifact) -> Path:
    """Where the verified file lives: keyed by SHA-256, named as uploaded."""
    return cache_dir() / artifact.sha256 / artifact.filename


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(artifact: PinnedArtifact, *, timeout: float = 120.0) -> Path:
    """Download ``artifact`` once, verify its SHA-256, and return its path.

    A cached file is re-hashed before reuse. Raises PinnedArtifactError,
    naming the file and the table, when the download fails or the bytes do
    not match the recorded hash.
    """
    import requests

    target = cache_path(artifact)
    if target.exists() and _sha256(target) == artifact.sha256:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    where = (
        f"{artifact.name}=={artifact.version} ({artifact.filename}, recorded in "
        f"{artifact.recorded_in}; table: axiom_oracles/pinned_artifacts.py)"
    )
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".download-")
    tmp = Path(tmp_name)
    try:
        digest = hashlib.sha256()
        try:
            with os.fdopen(fd, "wb") as out, requests.get(
                artifact.url, stream=True, timeout=timeout
            ) as response:
                if response.status_code != 200:
                    raise PinnedArtifactError(
                        f"pinned artifact {where} no longer downloads: HTTP "
                        f"{response.status_code} from {artifact.url}"
                    )
                for chunk in response.iter_content(1 << 20):
                    digest.update(chunk)
                    out.write(chunk)
        except requests.RequestException as exc:
            raise PinnedArtifactError(
                f"pinned artifact {where} could not be downloaded from "
                f"{artifact.url}: {exc}"
            ) from exc
        if digest.hexdigest() != artifact.sha256:
            raise PinnedArtifactError(
                f"pinned artifact {where} has SHA-256 {digest.hexdigest()}, "
                f"expected {artifact.sha256}"
            )
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    return target


def requirement(pin: str) -> str:
    """The requirement uv should install for ``pin``.

    ``name==version`` for a pruned release in the table becomes a direct
    reference to the verified local wheel (``name @ file:///...``), which uv
    installs under the same name and version. Any other requirement is
    returned unchanged.
    """
    name, sep, version = pin.partition("==")
    if not sep:
        return pin
    artifact = lookup(name, version)
    if artifact is None:
        return pin
    return f"{artifact.name} @ {fetch(artifact).resolve().as_uri()}"


def with_args(pins) -> list[str]:
    """``uv run --with`` arguments for ``pins``, pruned releases resolved."""
    return [arg for pin in pins for arg in ("--with", requirement(pin))]
