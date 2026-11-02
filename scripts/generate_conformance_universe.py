#!/usr/bin/env python3
"""Generate ``conformance/<jurisdiction>.yaml`` from an oracle's model spine.

Universe facts are read from the oracle model, never hand-invented: for UKMOD /
EUROMOD this parses the country policy XML (``XMLParam/Countries/<CC>/<CC>.xml``)
and the variable registry (``VARCONFIG.xml``) — a pure XML parse, so no engine,
.NET, or licensed microdata is needed. DK commits that pure-XML extract and
reads it in CI; the other EUROMOD jurisdictions read a local model checkout.
Scope *decisions*
(``in_scope`` / ``exclusion_reason`` / ``suite`` / ``note``) already committed in
the file are preserved; only the generated facts are refreshed.

``--check`` re-derives the facts from the configured source and fails if the
committed universe drifts (the ``generate_affected_map --check`` pattern), so a
new oracle policy cannot silently disappear from the "all programs covered"
accounting.

For external-checkout jurisdictions, an absent model makes ``--check`` a clean
no-op. Artifact-backed DK is intentionally different: it always consumes the
committed spine, so CI verifies real content without the external model.

Usage::

    uv run scripts/generate_conformance_universe.py uk            # write uk.yaml
    uv run scripts/generate_conformance_universe.py uk --check    # verify; nonzero on drift
    uv run scripts/generate_conformance_universe.py --all --check # every configured jurisdiction
    # Refresh DK's reviewed, committed single-system extract from the local model:
    python scripts/generate_conformance_universe.py dk --extract-spine --model-root PATH

Model roots resolve from (in order): ``--model-root``, ``$UKMOD_MODEL_ROOT`` /
``$EUROMOD_MODEL_ROOT``, then the per-jurisdiction default recorded below.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.conformance.loader import (  # noqa: E402
    OracleIdentity,
    Universe,
    parse_if_exists,
    serialize,
)
from axiom_oracles.conformance.universe import (  # noqa: E402
    EUROMOD_SPINE_ARTIFACT_SCHEMA,
    PE_UK_PROGRAM_SPINE,
    PE_US_PROGRAM_SPINE,
    EuromodSpineArtifactBackend,
    EuromodUniverseBackend,
    PolicyEngineUniverseBackend,
    YaleTariffUniverseBackend,
    raw_to_universe_policy,
)

CONFORMANCE_DIR = REPO_ROOT / "conformance"

#: Program spines keyed by the ``spine`` field in :data:`JURISDICTIONS`. The
#: spine is the committed grouping (the row set); the pinned checkout supplies
#: every scored fact. ``uk`` is the default for backward compatibility.
_PE_SPINES = {"uk": PE_UK_PROGRAM_SPINE, "us": PE_US_PROGRAM_SPINE}


#: Per-jurisdiction generation config. A jurisdiction with ``implemented: False``
#: is skipped by ``--all`` (and named in ``--list``). ``dk`` deliberately reads a
#: reviewed committed extract: unlike the external-checkout path used by UK/BE,
#: its CI drift check must never become a clean no-op when the model is absent.
JURISDICTIONS: dict[str, dict] = {
    "uk": {
        "implemented": True,
        "backend": "euromod",
        "country": "UK",
        "model": "UKMOD_PUBLIC",
        "release": "B2026.03",
        "system": "UK_2026",
        "env_roots": ("UKMOD_MODEL_ROOT", "EUROMOD_MODEL_ROOT"),
        "default_root": "$HOME/Downloads/UKMOD_PUBLIC_B2026.03",
    },
    "be": {
        "implemented": True,
        "backend": "euromod",
        "country": "BE",
        "model": "EUROMOD",
        "release": "J2.0",
        "system": "BE_2025",
        "env_roots": ("EUROMOD_MODEL_ROOT",),
        "default_root": "$HOME/Downloads/EUROMOD_J2.0/EUROMOD_RELEASES_J2.0+",
    },
    "dk": {
        "implemented": True,
        "backend": "euromod",
        "country": "DK",
        "model": "EUROMOD",
        "release": "J2.0",
        "system": "DK_2025",
        "spine_artifact": "conformance/spines/dk-DK_2025.json",
        "env_roots": ("EUROMOD_MODEL_ROOT",),
        "default_root": "$HOME/Downloads/EUROMOD_J2.0/EUROMOD_RELEASES_J2.0+",
    },
    "uk-pe": {
        "implemented": True,
        "backend": "policyengine",
        "country": "UK",
        "model": "policyengine-uk",
        # release is read from the checkout's pyproject.toml at generation time so
        # the header pins the exact policyengine-uk version enumerated (a fact from
        # the checkout, never a floating latest). This literal is the fallback for
        # error text only; the generator overrides it from pinned_version().
        "release": "checkout",
        "system": "uk",
        "package": "policyengine_uk",
        "spine": "uk",
        "env_roots": ("POLICYENGINE_UK_CHECKOUT",),
        "default_root": "$HOME/PolicyEngine/policyengine-uk",
    },
    "us-pe": {
        "implemented": True,
        "backend": "policyengine",
        "country": "US",
        "model": "policyengine-us",
        # release is read from the pinned checkout at generation time (its
        # pyproject.toml, or the installed distribution metadata for a
        # pip-installed tree). This literal is the error-text fallback only.
        "release": "checkout",
        "system": "us",
        "package": "policyengine_us",
        "spine": "us",
        # PE-US composes many surfaces (state income taxes, income_tax_before_*,
        # standard_deduction, medicaid …) from an adds/subtracts variable list
        # rather than a def formula; those ARE computed, so the backend must not
        # read them as pure inputs.
        "include_adds_subtracts": True,
        "env_roots": ("POLICYENGINE_US_CHECKOUT",),
        "default_root": "$HOME/PolicyEngine/policyengine-us",
    },
    "us-tariff-yale": {
        "implemented": True,
        "backend": "yale-tariff",
        "country": "US",
        "model": "tariff-rate-tracker",
        # release is the checkout's pinned git commit, read at generation time
        # (the same pin reference/us-tariff-panel/yale_panel_provenance.json
        # stamps for the committed extract). This literal is error-text only.
        "release": "checkout",
        "system": "statutory_panel",
        "env_roots": ("YALE_TARIFF_CHECKOUT",),
        "default_root": "$HOME/TheAxiomFoundation/_tariff-yale",
    },
}


def _resolve_root(config: dict, override: str | None) -> Path | None:
    if override:
        return Path(override).expanduser()
    for env in config.get("env_roots", ()):
        value = os.environ.get(env)
        if value:
            return Path(value).expanduser()
    default = config.get("default_root")
    if default:
        candidate = Path(os.path.expandvars(default)).expanduser()
        if candidate.exists():
            return candidate
    return None


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _artifact_path(config: dict) -> Path:
    path = Path(config["spine_artifact"])
    return path if path.is_absolute() else REPO_ROOT / path


def generate_universe(
    jurisdiction: str, model_root: Path | None = None
) -> Universe:
    """Regenerate one jurisdiction's universe (facts fresh, decisions preserved)."""
    config = JURISDICTIONS[jurisdiction]
    release = config["release"]
    if config.get("spine_artifact"):
        backend = EuromodSpineArtifactBackend(
            _artifact_path(config),
            model=config["model"],
            release=release,
            country=config["country"],
            system=config["system"],
        )
    elif config["backend"] == "euromod":
        if model_root is None:
            raise ValueError(f"{jurisdiction}: EUROMOD model root is required")
        backend = EuromodUniverseBackend(
            model_root=model_root,
            country=config["country"],
            system=config["system"],
        )
    elif config["backend"] == "policyengine":
        if model_root is None:
            raise ValueError(
                f"{jurisdiction}: PolicyEngine checkout root is required"
            )
        backend = PolicyEngineUniverseBackend(
            checkout=model_root,
            package=config.get("package", "policyengine_uk"),
            spine=_PE_SPINES[config.get("spine", "uk")],
            include_adds_subtracts=config.get("include_adds_subtracts", False),
        )
        # Pin the exact version enumerated, read from the checkout (not memory).
        release = backend.pinned_version()
    elif config["backend"] == "yale-tariff":
        if model_root is None:
            raise ValueError(f"{jurisdiction}: Yale checkout root is required")
        backend = YaleTariffUniverseBackend(checkout=model_root)
        # Pin the exact git commit enumerated — the same identity the committed
        # reference extract's provenance stamp pins.
        release = backend.pinned_commit()
    else:
        raise NotImplementedError(
            f"{jurisdiction}: unknown backend {config['backend']!r}"
        )
    oracle = OracleIdentity(
        model=config["model"],
        release=release,
        system=config["system"],
        country=config["country"],
        backend=config["backend"],
    )
    committed = parse_if_exists(CONFORMANCE_DIR / f"{jurisdiction}.yaml")
    committed_by_name = committed.by_name() if committed else {}

    rows = []
    for raw in backend.raw_policies():
        rows.append(
            raw_to_universe_policy(
                raw,
                committed=committed_by_name.get(raw.name),
                jurisdiction=jurisdiction,
            )
        )
    return Universe(jurisdiction=jurisdiction, oracle=oracle, policies=rows)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _display_path(path: Path) -> str:
    try:
        return f"$HOME/{path.relative_to(Path.home())}"
    except ValueError:
        return str(path)


def extract_euromod_spine(
    jurisdiction: str,
    model_root: Path,
    *,
    extracted_at: str | None = None,
) -> Path:
    """Refresh a configured committed spine from the local EUROMOD XML."""
    config = JURISDICTIONS[jurisdiction]
    if config["backend"] != "euromod" or not config.get("spine_artifact"):
        raise ValueError(
            f"{jurisdiction}: --extract-spine requires a configured committed "
            "EUROMOD spine artifact"
        )
    model_root = model_root.expanduser().resolve()
    backend = EuromodUniverseBackend(
        model_root=model_root,
        country=config["country"],
        system=config["system"],
    )
    raw_policies = backend.raw_policies()
    country_xml = (
        model_root
        / "XMLParam"
        / "Countries"
        / config["country"]
        / f"{config['country']}.xml"
    )
    registry_xml = model_root / "XMLParam" / "Config" / "VARCONFIG.xml"
    when = extracted_at or datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    command = (
        "DOTNET_ROOT=$HOME/.dotnet-x64 PYTHONNET_RUNTIME=coreclr "
        "$HOME/.venvs/axiom-euromod-x64/bin/python "
        f"scripts/generate_conformance_universe.py {jurisdiction} "
        f"--extract-spine --model-root {_display_path(model_root)}"
    )
    document = {
        "schema": EUROMOD_SPINE_ARTIFACT_SCHEMA,
        "jurisdiction": jurisdiction,
        "oracle": {
            "model": config["model"],
            "release": config["release"],
            "country": config["country"],
        },
        "systems": [
            {
                "name": config["system"],
                "id": backend.system_id(),
            }
        ],
        "provenance": {
            "model_root": str(model_root),
            "model_release": model_root.name,
            "extraction_command": command,
            "extracted_at": when,
            "sources": [
                {
                    "path": str(country_xml.relative_to(model_root)),
                    "sha256": _sha256(country_xml),
                },
                {
                    "path": str(registry_xml.relative_to(model_root)),
                    "sha256": _sha256(registry_xml),
                },
            ],
        },
        "policies": [
            {
                "name": policy.name,
                "policy_type": policy.policy_type,
                "switch": policy.switch,
                "all_outputs": list(policy.all_outputs),
                "queryable_outputs": list(policy.queryable_outputs),
                "internal_outputs": list(policy.internal_outputs),
            }
            for policy in raw_policies
        ],
    }
    output_path = _artifact_path(config)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, indent=2) + "\n")
    return output_path


def _process(
    jurisdiction: str, *, check: bool, model_root: str | None
) -> int:
    config = JURISDICTIONS[jurisdiction]
    output_path = CONFORMANCE_DIR / f"{jurisdiction}.yaml"

    if not config.get("implemented"):
        todo = config.get("todo", "not yet implemented")
        print(f"conformance[{jurisdiction}]: TODO hook — {todo}")
        return 0

    # Artifact-backed jurisdictions always read the committed extract. This is
    # intentionally before root resolution: their CI check must fail on drift
    # even on runners that do not have the external model checkout.
    root = None if config.get("spine_artifact") else _resolve_root(config, model_root)
    if not config.get("spine_artifact") and (root is None or not root.exists()):
        if check:
            # No model checkout on this runner: the committed universe stands
            # alone (like the boundary-case gate). Nothing to verify against.
            print(
                f"conformance[{jurisdiction}] --check: model checkout absent "
                f"(looked for {config.get('default_root')} / "
                f"{'/'.join(config.get('env_roots', ()))}); committed universe "
                "left unverified this run (no-op clean)."
            )
            return 0
        sys.stderr.write(
            f"conformance[{jurisdiction}]: model checkout not found. Set "
            f"--model-root or one of {', '.join(config.get('env_roots', ()))}, or "
            f"place it at {config.get('default_root')}.\n"
        )
        return 2

    # The policyengine backend pins by VERSION, not by a release-stamped path the
    # way the euromod default_root does (UKMOD_PUBLIC_B2026.03). So when a
    # checkout is present but its version differs from the committed universe
    # header's release, it is not the pinned oracle — during --check treat that
    # like an absent checkout (no-op clean), so a runner that happens to have a
    # different policyengine-uk checked out cannot spuriously fail the drift gate.
    if check and config["backend"] in ("policyengine", "yale-tariff"):
        committed = parse_if_exists(output_path)
        if committed is not None:
            try:
                if config["backend"] == "yale-tariff":
                    present_version = YaleTariffUniverseBackend(
                        checkout=root
                    ).pinned_commit()
                else:
                    present_version = PolicyEngineUniverseBackend(
                        checkout=root,
                        package=config.get("package", "policyengine_uk"),
                    ).pinned_version()
            except (FileNotFoundError, ValueError):
                present_version = None
            if present_version and present_version != committed.oracle.release:
                print(
                    f"conformance[{jurisdiction}] --check: checkout at {root} is "
                    f"{config['model']}@{present_version}, not the pinned "
                    f"{committed.oracle.release}; committed universe left unverified "
                    "this run (no-op clean — pin a matching checkout to enforce)."
                )
                return 0

    try:
        universe = generate_universe(jurisdiction, root)
    except (FileNotFoundError, ValueError) as exc:
        if config.get("spine_artifact"):
            sys.stderr.write(
                f"conformance[{jurisdiction}] committed spine invalid: {exc}\n"
            )
            return 1
        raise
    except ImportError as exc:
        # The policyengine backend imports the pinned checkout; a runner that has
        # the directory but not the package's installed dependencies cannot
        # enumerate. During --check this is the same clean no-op as an absent
        # checkout (the committed universe stands alone); a write run must fail.
        if check and config["backend"] == "policyengine":
            print(
                f"conformance[{jurisdiction}] --check: checkout present at {root} "
                f"but {config.get('package', 'the package')} is not importable "
                f"({exc}); committed universe left unverified this run (no-op clean)."
            )
            return 0
        raise

    problems = universe.validate()
    serialized = serialize(universe)

    if check:
        if problems:
            for problem in problems:
                sys.stderr.write(
                    f"conformance[{jurisdiction}] INVALID: {problem}\n"
                )
            return 1
        if not output_path.exists():
            sys.stderr.write(
                f"{_rel(output_path)} is missing; run "
                f"`uv run scripts/generate_conformance_universe.py {jurisdiction}`.\n"
            )
            return 1
        if output_path.read_text() != serialized:
            sys.stderr.write(
                f"{_rel(output_path)} is stale — the {config['model']}_"
                f"{config['release']} model spine no longer matches the committed "
                f"universe. Run `uv run scripts/generate_conformance_universe.py "
                f"{jurisdiction}` and review the diff (a new/removed oracle policy "
                "needs a scope decision).\n"
            )
            return 1
        n_in = len(universe.in_scope())
        n_ex = len(universe.excluded())
        print(
            f"conformance[{jurisdiction}] OK: {len(universe.policies)} policies "
            f"({n_in} in scope, {n_ex} excluded) match "
            f"{universe.oracle.label}"
        )
        return 0

    if problems:
        # Still write so the author can see the refreshed facts alongside the
        # decisions they need to fix, but signal failure.
        output_path.write_text(serialized)
        for problem in problems:
            sys.stderr.write(f"conformance[{jurisdiction}] INVALID: {problem}\n")
        sys.stderr.write(
            f"Wrote {_rel(output_path)} with refreshed facts, but scope decisions "
            "are inconsistent (see above).\n"
        )
        return 1

    output_path.write_text(serialized)
    print(
        f"Wrote {_rel(output_path)}: {len(universe.policies)} policies "
        f"({len(universe.in_scope())} in scope, {len(universe.excluded())} "
        f"excluded) from {universe.oracle.label}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "jurisdiction",
        nargs="?",
        help="Jurisdiction key. Omit with --all.",
    )
    parser.add_argument("--all", action="store_true", help="Process every jurisdiction.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="Verify the committed universe matches a fresh regeneration.",
    )
    mode.add_argument(
        "--extract-spine",
        action="store_true",
        help="Refresh a configured committed EUROMOD spine from the local model.",
    )
    parser.add_argument("--model-root", help="Override the oracle model checkout path.")
    parser.add_argument("--list", action="store_true", help="List configured jurisdictions.")
    args = parser.parse_args()

    if args.list:
        for key, config in JURISDICTIONS.items():
            state = "implemented" if config.get("implemented") else "TODO hook"
            print(f"{key:8} {state:12} {config['model']} ({config['backend']})")
        return 0

    if args.extract_spine:
        if args.all or not args.jurisdiction:
            parser.error("--extract-spine requires exactly one jurisdiction")
        if args.jurisdiction not in JURISDICTIONS:
            parser.error(f"unknown jurisdiction {args.jurisdiction!r}")
        config = JURISDICTIONS[args.jurisdiction]
        root = _resolve_root(config, args.model_root)
        if root is None or not root.exists():
            sys.stderr.write(
                f"conformance[{args.jurisdiction}]: model checkout not found; "
                "set --model-root or the configured environment root.\n"
            )
            return 2
        try:
            output_path = extract_euromod_spine(args.jurisdiction, root)
        except (FileNotFoundError, ValueError) as exc:
            sys.stderr.write(
                f"conformance[{args.jurisdiction}] spine extraction failed: "
                f"{exc}\n"
            )
            return 1
        print(
            f"Wrote {_rel(output_path)} from {config['model']}_"
            f"{config['release']}/{config['system']}"
        )
        return 0

    if args.all:
        targets = list(JURISDICTIONS)
    elif args.jurisdiction:
        if args.jurisdiction not in JURISDICTIONS:
            sys.stderr.write(
                f"Unknown jurisdiction {args.jurisdiction!r}; known: "
                f"{', '.join(JURISDICTIONS)}\n"
            )
            return 2
        targets = [args.jurisdiction]
    else:
        parser.error("give a jurisdiction or --all")
        return 2

    rc = 0
    for jurisdiction in targets:
        rc = max(rc, _process(jurisdiction, check=args.check, model_root=args.model_root))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
