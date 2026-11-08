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

Each row's ``found_in`` says where its URL and SHA-256 were found: a
``uv.lock`` this repository committed, a ``uv.lock`` in PolicyEngine's
policyengine-us-data repository, or an archived snapshot of PyPI's JSON API.
Integrity does not rest on that field. A files.pythonhosted.org URL's path is
the file's blake2b-256 digest, each row's digests were checked against the
downloaded bytes when it was added (``tests/test_pinned_artifacts.py`` pins
them), and ``fetch`` checks the SHA-256 on every download.
``scripts/check_pinned_artifacts.py`` fails, naming the file that pins it,
when a recorded file stops downloading or when a runtime pin is neither on
the index nor in this table.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PinnedArtifact:
    """One pruned distribution file, addressed by its hashed URL."""

    name: str
    version: str
    url: str
    sha256: str
    #: Where this URL and SHA-256 were found. Provenance of the lookup only:
    #: the digests, not this field, establish the file's integrity.
    found_in: str

    @property
    def filename(self) -> str:
        return self.url.rsplit("/", 1)[-1]


#: The one table of pruned PolicyEngine files. Wheels only: uv installs a
#: local wheel without building it.
PRUNED_ARTIFACTS: tuple[PinnedArtifact, ...] = (
    PinnedArtifact(
        name="policyengine-us",
        version="1.700.0",
        url=(
            "https://files.pythonhosted.org/packages/49/e9/"
            "2837a0d98e99efaf4d82aade276eee6eeff419df614863f08e3512961d2d/"
            "policyengine_us-1.700.0-py3-none-any.whl"
        ),
        sha256="7633d8aefcaf02d7628f841bc56750606f1d7fe409ff3ae7b0ef7e364a88e945",
        found_in="uv.lock in PolicyEngine/policyengine-us-data at 0eac8dc990",
    ),
    PinnedArtifact(
        name="policyengine-us",
        version="1.705.1",
        url=(
            "https://files.pythonhosted.org/packages/87/1d/"
            "71653e73a243ffb6e74463403b2a198cdea9ce9fa2dab8038d99ad70991b/"
            "policyengine_us-1.705.1-py3-none-any.whl"
        ),
        sha256="9db5121748d62961cb4867f18dab03da1be9abc986676e12e147e19afc6fd6aa",
        found_in="uv.lock in PolicyEngine/policyengine-us-data at b58cf3b38d",
    ),
    PinnedArtifact(
        name="policyengine-us",
        version="1.729.0",
        url=(
            "https://files.pythonhosted.org/packages/b9/7d/"
            "778f92ae94997b00c3c9ac34b345f6c9333435f905670ee4eeb2f5e19809/"
            "policyengine_us-1.729.0-py3-none-any.whl"
        ),
        sha256="8d21d3f7c0e82a9415edffe8ea53939330a63d9c8f6bd334299bddb697cf2c00",
        found_in="uv.lock in PolicyEngine/policyengine-us-data at 17e87f1026",
    ),
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
        found_in="uv.lock at 678dd840b4",
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
        found_in="uv.lock (the policyengine extra, since 29cb47dad4)",
    ),
    PinnedArtifact(
        name="policyengine-us",
        version="1.767.3",
        url=(
            "https://files.pythonhosted.org/packages/d1/9e/"
            "b2685b9ab9639d81a29d7da7fa02619d2e9b916f65ec4ef6d6c9230744a6/"
            "policyengine_us-1.767.3-py3-none-any.whl"
        ),
        sha256="777be3f3a66cbd266959791b007571a8fce94b1d0c2d13f40f8e991ca106fa6f",
        found_in="PyPI JSON API via Wayback snapshot 20260715063216",
    ),
)

CACHE_ENV = "AXIOM_ORACLES_ARTIFACT_CACHE"


class PinnedArtifactError(RuntimeError):
    """A pinned file could not be downloaded or did not match its SHA-256.

    ``kind`` tells the cases apart:

    - ``"gone"``: HTTP 404 or 410, the file was removed;
    - ``"transient"``: a 5xx, 408 or 429, a 403 marked as rate limiting
      (``Retry-After`` or ``X-RateLimit-Remaining: 0``), or a connection
      error, that persisted through every retry;
    - ``"refused"``: any other 4xx (a plain 403, 401, ...), which a retry
      would not change and which does not by itself mean the file is gone;
    - ``"mismatch"``: the bytes do not hash to the recorded SHA-256.
    """

    def __init__(self, message: str, *, kind: str):
        super().__init__(message)
        self.kind = kind


#: Retries after the first attempt for a transient status or a connection
#: error, and the wait before each one.
RETRY_DELAYS = (2.0, 4.0)
_sleep = time.sleep

#: Statuses that mean the file was removed.
GONE_STATUSES = frozenset({404, 410})
#: 4xx statuses worth a retry: request timeout and rate limiting. A 403 is
#: retried too when its headers mark it as rate limiting (classify_status).
TRANSIENT_CLIENT_STATUSES = frozenset({408, 429})


def _rate_limited(headers: Mapping[str, str] | None) -> bool:
    """Do ``headers`` say the request was rate limited?

    Some hosts answer rate limiting with a 403 rather than a 429; they mark
    it with ``Retry-After`` or ``X-RateLimit-Remaining: 0``. Header names are
    compared case-insensitively, whatever mapping holds them.
    """
    if not headers:
        return False
    names = {str(name).lower(): str(value).strip() for name, value in headers.items()}
    return "retry-after" in names or names.get("x-ratelimit-remaining") == "0"


def classify_status(status: int, headers: Mapping[str, str] | None = None) -> str:
    """``"ok"``, ``"transient"`` (retry), ``"gone"`` or ``"refused"``.

    A 403 whose ``headers`` mark it as rate limiting is ``"transient"``; the
    headers change no other status's class.
    """
    if status == 200:
        return "ok"
    if 500 <= status < 600 or status in TRANSIENT_CLIENT_STATUSES:
        return "transient"
    if status in GONE_STATUSES:
        return "gone"
    if status == 403 and _rate_limited(headers):
        return "transient"
    return "refused"


def is_transient_status(status: int, headers: Mapping[str, str] | None = None) -> bool:
    return classify_status(status, headers) == "transient"


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

    A cached file is re-hashed before reuse. A transient status (5xx, 408,
    429, or a rate-limited 403) or a connection error is retried ``len(RETRY_DELAYS)`` times with
    backoff. Raises PinnedArtifactError, naming the file and the table, when
    the download fails (``kind`` ``"gone"``, ``"refused"`` or
    ``"transient"``) or the bytes do not match the recorded hash
    (``"mismatch"``).
    """
    import requests

    target = cache_path(artifact)
    if target.exists() and _sha256(target) == artifact.sha256:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    where = (
        f"{artifact.name}=={artifact.version} ({artifact.filename}, found in "
        f"{artifact.found_in}; table: axiom_oracles/pinned_artifacts.py)"
    )
    attempts = len(RETRY_DELAYS) + 1
    for attempt in range(attempts):
        fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".download-")
        tmp = Path(tmp_name)
        try:
            digest = hashlib.sha256()
            try:
                with os.fdopen(fd, "wb") as out, requests.get(
                    artifact.url, stream=True, timeout=timeout
                ) as response:
                    status = response.status_code
                    kind = classify_status(status, response.headers)
                    if kind == "transient" and attempt + 1 < attempts:
                        _sleep(RETRY_DELAYS[attempt])
                        continue
                    if kind == "transient":
                        raise PinnedArtifactError(
                            f"pinned artifact {where}: HTTP {status} from "
                            f"{artifact.url} on all {attempts} attempts "
                            "(transient, not a removal)",
                            kind="transient",
                        )
                    if kind == "gone":
                        raise PinnedArtifactError(
                            f"pinned artifact {where} no longer downloads: HTTP "
                            f"{status} from {artifact.url}",
                            kind="gone",
                        )
                    if kind == "refused":
                        raise PinnedArtifactError(
                            f"pinned artifact {where}: HTTP {status} from "
                            f"{artifact.url} (refused; not retried, and not "
                            "by itself a removal)",
                            kind="refused",
                        )
                    for chunk in response.iter_content(1 << 20):
                        digest.update(chunk)
                        out.write(chunk)
            except requests.RequestException as exc:
                if attempt + 1 < attempts:
                    _sleep(RETRY_DELAYS[attempt])
                    continue
                raise PinnedArtifactError(
                    f"pinned artifact {where} could not be downloaded from "
                    f"{artifact.url} on all {attempts} attempts: {exc}",
                    kind="transient",
                ) from exc
            if digest.hexdigest() != artifact.sha256:
                raise PinnedArtifactError(
                    f"pinned artifact {where} has SHA-256 {digest.hexdigest()}, "
                    f"expected {artifact.sha256}",
                    kind="mismatch",
                )
            os.replace(tmp, target)
            return target
        finally:
            tmp.unlink(missing_ok=True)
    raise AssertionError("unreachable")  # pragma: no cover


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


def _load_run_comparison():
    """``scripts/run_comparison.py`` of this checkout, loaded by path."""
    import importlib.util
    import sys

    path = Path(__file__).resolve().parents[1] / "scripts" / "run_comparison.py"
    if not path.exists():
        raise SystemExit(
            f"--oracle-with-args needs a source checkout; {path} does not exist"
        )
    spec = importlib.util.spec_from_file_location("_run_comparison_for_recipe", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


#: The stack keys a suite pins beside ``policyengine_us_version``.
_STACK_KEYS = ("policyengine_version", "policyengine_core_version")


def oracle_stack_params(us_version: str, comparisons_dir: Path | None = None) -> dict:
    """The runner parameters of the PolicyEngine stack that pins ``us_version``.

    Comparison suites pin policyengine-us together with the ``policyengine``
    and ``policyengine-core`` releases it was reviewed with. Return those
    parameters when every suite that pins ``us_version`` (and installs it by
    version, not from a ``policyengine_us_source``) agrees on them. Refuse,
    naming the version, when no suite pins it (the in-repo defaults are not
    the stack any comparison runs that release with) or when suites disagree.
    """
    import yaml

    root = comparisons_dir or Path(__file__).resolve().parents[1] / "comparisons"
    stacks: dict[tuple, list[str]] = {}
    # The same files scripts/check_pinned_artifacts.py scans.
    for path in sorted(root.rglob("*.y*ml")):
        config = yaml.safe_load(path.read_text())
        params = (
            ((config or {}).get("runner") or {}).get("parameters")
            if isinstance(config, dict)
            else None
        ) or {}
        if str(params.get("policyengine_us_version")) != us_version:
            continue
        if params.get("policyengine_us_source"):
            continue
        key = tuple(params.get(name) for name in _STACK_KEYS)
        stacks.setdefault(key, []).append(path.relative_to(root).as_posix())
    if len(stacks) > 1:
        detail = "; ".join(
            f"{dict(zip(_STACK_KEYS, key))}: {', '.join(names)}"
            for key, names in sorted(stacks.items(), key=str)
        )
        raise SystemExit(
            f"suites pin policyengine-us {us_version} with different stacks: {detail}"
        )
    if not stacks:
        raise SystemExit(
            f"no comparisons suite pins policyengine-us {us_version} (by version, "
            "without a policyengine_us_source), so there is no suite stack to "
            "print; see where that release is pinned with "
            "scripts/check_pinned_artifacts.py --list"
        )
    params = {"policyengine_us_version": us_version}
    (key,) = stacks
    params.update({k: v for k, v in zip(_STACK_KEYS, key) if v is not None})
    return params


def oracle_with_args(us_version: str) -> list[str]:
    """The comparisons' full ``uv run --with`` list for a policyengine-us version.

    Built by ``scripts/run_comparison.py``'s own ``_resolve_pe_oracle_pins``
    and ``_pe_oracle_with_args``: the ``policyengine`` and
    ``policyengine-core`` pins of the suites that pin this version (refused
    when none does), the verified wheel of a pruned release, and the
    companion pins. A direct reference is written ``name@file:///...`` (valid
    PEP 508, no whitespace), so the list survives shell word splitting.
    """
    run_comparison = _load_run_comparison()
    pins = run_comparison._resolve_pe_oracle_pins(oracle_stack_params(us_version))
    args = [arg.replace(" @ ", "@", 1) for arg in run_comparison._pe_oracle_with_args(pins)]
    for arg in args:
        if any(ch.isspace() for ch in arg):
            raise SystemExit(f"cannot print {arg!r} for shell use: it contains whitespace")
    return args


def main(argv: list[str] | None = None) -> int:
    """Print the requirement uv should install for each ``name==version``.

    ``--oracle-with-args VERSION`` instead prints the comparisons' full
    ``--with`` list for that policyengine-us release, for manual runs from
    the repository root. ``&&`` keeps the run from starting without its pins
    when the inner command fails::

        pins=$(uv run -q python -m axiom_oracles.pinned_artifacts \\
            --oracle-with-args 1.767.3) &&
          uv run --python 3.13 --no-project --isolated $pins \\
            python scripts/probe_us_sc_income_tax_2026.py
    """
    import argparse

    parser = argparse.ArgumentParser(prog="python -m axiom_oracles.pinned_artifacts")
    parser.add_argument("pins", nargs="*", metavar="NAME==VERSION")
    parser.add_argument(
        "--oracle-with-args",
        metavar="VERSION",
        help="print the full uv --with list for this policyengine-us version",
    )
    args = parser.parse_args(argv)
    if args.oracle_with_args:
        if args.pins:
            parser.error("--oracle-with-args takes no NAME==VERSION arguments")
        print(" ".join(oracle_with_args(args.oracle_with_args)))
        return 0
    if not args.pins:
        parser.error("give NAME==VERSION pins or --oracle-with-args VERSION")
    for pin in args.pins:
        print(requirement(pin))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
