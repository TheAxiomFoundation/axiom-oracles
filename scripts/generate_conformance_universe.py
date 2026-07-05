#!/usr/bin/env python3
"""Generate ``conformance/<jurisdiction>.yaml`` from an oracle's model spine.

Universe facts are read from the oracle model, never hand-invented: for UKMOD /
EUROMOD this parses the country policy XML (``XMLParam/Countries/<CC>/<CC>.xml``)
and the variable registry (``VARCONFIG.xml``) — a pure XML parse, so no engine,
.NET, or licensed microdata is needed and it runs in CI. Scope *decisions*
(``in_scope`` / ``exclusion_reason`` / ``suite`` / ``note``) already committed in
the file are preserved; only the generated facts are refreshed.

``--check`` re-derives the facts and fails if the committed universe drifts from
the model (the ``generate_affected_map --check`` pattern), so a new oracle
policy cannot silently disappear from the "all programs covered" accounting.

When the model checkout is absent (a runner without the UKMOD clone) ``--check``
is a clean no-op: the committed universe stands alone, exactly like the
boundary-case gate. Set the model root explicitly or via the environment.

Usage::

    uv run scripts/generate_conformance_universe.py uk            # write uk.yaml
    uv run scripts/generate_conformance_universe.py uk --check    # verify; nonzero on drift
    uv run scripts/generate_conformance_universe.py --all --check # every configured jurisdiction

Model roots resolve from (in order): ``--model-root``, ``$UKMOD_MODEL_ROOT`` /
``$EUROMOD_MODEL_ROOT``, then the per-jurisdiction default recorded below.
"""

from __future__ import annotations

import argparse
import os
import sys
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
    EuromodUniverseBackend,
    raw_to_universe_policy,
)

CONFORMANCE_DIR = REPO_ROOT / "conformance"


#: Per-jurisdiction generation config. ``uk`` is implemented and committed now;
#: ``be`` and ``pe-uk`` are documented TODO hooks — two scoper agents are
#: enumerating those universes concurrently, so this generator provides the
#: reproducible backend without pre-empting their row decisions. A jurisdiction
#: with ``implemented: False`` is skipped by ``--all`` (and named in ``--list``).
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
    "pe-uk": {
        "implemented": False,
        "backend": "policyengine",
        "country": "UK",
        "model": "policyengine-uk",
        "release": "TODO",
        "system": "uk",
        "env_roots": ("POLICYENGINE_UK_CHECKOUT",),
        "default_root": "$HOME/PolicyEngine/policyengine-uk",
        "todo": (
            "pe-uk universe is being scoped concurrently. Implement "
            "PolicyEngineUniverseBackend.raw_policies() against a pinned "
            "policyengine-uk checkout, then seed conformance/pe-uk.yaml."
        ),
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


def generate_universe(jurisdiction: str, model_root: Path) -> Universe:
    """Regenerate one jurisdiction's universe (facts fresh, decisions preserved)."""
    config = JURISDICTIONS[jurisdiction]
    if config["backend"] != "euromod":
        raise NotImplementedError(
            f"{jurisdiction}: only the euromod backend is implemented; "
            f"{config['backend']} is a documented TODO hook"
        )
    backend = EuromodUniverseBackend(
        model_root=model_root,
        country=config["country"],
        system=config["system"],
    )
    oracle = OracleIdentity(
        model=config["model"],
        release=config["release"],
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


def _process(
    jurisdiction: str, *, check: bool, model_root: str | None
) -> int:
    config = JURISDICTIONS[jurisdiction]
    output_path = CONFORMANCE_DIR / f"{jurisdiction}.yaml"

    if not config.get("implemented"):
        todo = config.get("todo", "not yet implemented")
        print(f"conformance[{jurisdiction}]: TODO hook — {todo}")
        return 0

    root = _resolve_root(config, model_root)
    if root is None or not root.exists():
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

    universe = generate_universe(jurisdiction, root)
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
        help="Jurisdiction key (uk, be, pe-uk). Omit with --all.",
    )
    parser.add_argument("--all", action="store_true", help="Process every jurisdiction.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the committed universe matches a fresh regeneration.",
    )
    parser.add_argument("--model-root", help="Override the oracle model checkout path.")
    parser.add_argument("--list", action="store_true", help="List configured jurisdictions.")
    args = parser.parse_args()

    if args.list:
        for key, config in JURISDICTIONS.items():
            state = "implemented" if config.get("implemented") else "TODO hook"
            print(f"{key:8} {state:12} {config['model']} ({config['backend']})")
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
