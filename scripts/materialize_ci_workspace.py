#!/usr/bin/env python3
"""Materialize the supervised workspace a comparison suite expects (O2/#296).

The comparison harnesses resolve rulespec checkouts, synced-root dirs, and the
axiom-compose venv from a small set of supervised-layout conventions under
``$HOME`` (``~/TheAxiomFoundation/<repo>``, a ``~/rulespec-us`` symlink,
``~/.axiom-oracles/roots/<repo>``, ``~/rulespec-uk-official``,
``~/axiom-compose/.venv/bin/axiom-compose``). CI runners have none of that, so
every leg whose suite needs any of it fails before the comparison starts —
the #296 failure classes.

This script makes a CI runner isomorphic to the supervised layout for ONE
suite, data-driven from committed sources of truth:

* ``comparisons/affected_map.json`` names the rulespec repos the suite
  exercises (the same map the affected-rerun selector diffs SHAs against);
  each one is shallow-cloned into ``<workspace>/TheAxiomFoundation/<name>``.
* the suite's ``comparisons/<name>.yaml`` names the path conventions it
  resolves (``$HOME/rulespec-us``, ``$HOME/.axiom-oracles/roots``,
  ``$HOME/rulespec-uk-official``) and whether it composes a program
  (``axiom_program`` → the axiom-compose venv); each referenced convention is
  materialized as a symlink into the cloned checkouts, and the compose venv
  is built with uv.

Every action is skip-if-present, so running against a real supervised machine
is a no-op — the script never replaces an existing checkout, symlink, or venv.

Usage:
    python3 scripts/materialize_ci_workspace.py <registry-name> [--workspace $HOME]
    python3 scripts/materialize_ci_workspace.py <registry-name> --plan   # print, no side effects
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - CI installs pyyaml
    sys.stderr.write("PyYAML is required (uv pip install pyyaml).\n")
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPARISONS_DIR = REPO_ROOT / "comparisons"
AFFECTED_MAP = COMPARISONS_DIR / "affected_map.json"

#: Directory under the workspace that mirrors the org checkout layout the
#: bridges' ``resolve_workspace_root`` falls back to (``~/TheAxiomFoundation``).
ORG_DIR_NAME = "TheAxiomFoundation"

#: Local checkout basenames that alias an upstream repo (mirrors
#: ``axiom_oracles.provenance._RULESPEC_DIR_ALIASES``).
UK_OFFICIAL_DIR = "rulespec-uk-official"
UK_OFFICIAL_TARGET = "rulespec-uk"

COMPOSE_SLUG = "TheAxiomFoundation/axiom-compose"
COMPOSE_DIR = "axiom-compose"


def _iter_strings(value) -> list[str]:
    """Every string in a nested config structure, depth-first."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _iter_strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _iter_strings(v)]
    return []


def mapped_repos(affected_map: dict, registry_name: str) -> list[str]:
    """The union of rulespec repos every map entry ties to this registry name.

    Matches on both ``name`` (what the rerun matrix dispatches) and ``suite``
    (the dashboard key) so a registry name shared by several dashboard suites
    still collects every repo any of them exercises.
    """
    repos: list[str] = []
    for entry in affected_map.get("suites", []):
        if registry_name not in (entry.get("name"), entry.get("suite")):
            continue
        for repo in entry.get("repos", []):
            if repo not in repos:
                repos.append(repo)
    return repos


def build_plan(config: dict, repos: list[str], workspace: Path) -> list[dict]:
    """Pure planning: the ordered actions materializing this suite's layout.

    Action kinds: ``clone`` (repo slug → dest), ``symlink`` (link → target),
    ``compose-venv`` (clone+build axiom-compose). Only missing paths produce
    actions — the plan is empty on a fully materialized (supervised) machine.
    """
    org_dir = workspace / ORG_DIR_NAME
    actions: list[dict] = []

    runner = config.get("runner") or {}
    strings = _iter_strings(runner)
    params = runner.get("parameters") or {}

    for slug in repos:
        dest = org_dir / slug.split("/", 1)[-1]
        if not dest.exists():
            actions.append({"kind": "clone", "repo": slug, "dest": str(dest)})

    def _symlink(link: Path, target: Path) -> None:
        if not link.exists() and not link.is_symlink():
            actions.append(
                {"kind": "symlink", "link": str(link), "target": str(target)}
            )

    repo_names = {slug.split("/", 1)[-1] for slug in repos}

    # Top-level ``$HOME/<rulespec-repo>`` symlinks for every mapped repo.
    # Suites reference these directly (``rulespec_roots: [$HOME/rulespec-us]``)
    # or indirectly — ``axiom_rulespec_repo_roots: $HOME`` makes the engine
    # scan the workspace for ``rulespec-*`` children — so the links must exist
    # whether or not the YAML names them explicitly.
    for name in sorted(repo_names):
        _symlink(workspace / name, org_dir / name)

    # ``$HOME/.axiom-oracles/roots`` — a synced-roots dir; provide one symlink
    # per mapped rulespec repo so globs and direct child references both work.
    if any("$HOME/.axiom-oracles/roots" in s for s in strings):
        roots_dir = workspace / ".axiom-oracles" / "roots"
        for name in sorted(repo_names):
            _symlink(roots_dir / name, org_dir / name)

    # ``$HOME/rulespec-uk-official`` — the pristine-main alias of rulespec-uk.
    if any(f"$HOME/{UK_OFFICIAL_DIR}" in s for s in strings):
        _symlink(workspace / UK_OFFICIAL_DIR, org_dir / UK_OFFICIAL_TARGET)

    # ``$HOME/axiom-oracles`` — suites name in-repo assets (axiom-programs
    # specs) through the supervised checkout path; point it at this checkout.
    if any("$HOME/axiom-oracles" in s for s in strings):
        _symlink(workspace / "axiom-oracles", REPO_ROOT)

    # ``$HOME/axiom-programs`` — the org's declarative compose-spec repo
    # (the UK efrs suites resolve their universal-credit program from it).
    if any("$HOME/axiom-programs" in s for s in strings):
        programs_dir = org_dir / "axiom-programs"
        if not programs_dir.exists():
            actions.append(
                {
                    "kind": "clone",
                    "repo": "TheAxiomFoundation/axiom-programs",
                    "dest": str(programs_dir),
                }
            )
        _symlink(workspace / "axiom-programs", programs_dir)

    # ``data_folder`` names a dataset CACHE the run itself populates — but the
    # runner resolves it fatally before downloading, so materialize the empty
    # directory when it lives under the workspace conventions.
    data_folder = params.get("data_folder")
    if isinstance(data_folder, str) and data_folder.startswith("$HOME/"):
        resolved = workspace / data_folder[len("$HOME/") :]
        if not resolved.exists():
            actions.append({"kind": "mkdir", "path": str(resolved)})

    # Composed-program suites need the axiom-compose venv at the conventional
    # ``$HOME/axiom-compose/.venv/bin/axiom-compose`` (the runner's default;
    # suites may also name it explicitly via ``axiom_compose_binary``).
    if params.get("axiom_program") or params.get("axiom_compose_binary"):
        binary = workspace / COMPOSE_DIR / ".venv" / "bin" / "axiom-compose"
        if not binary.exists():
            actions.append(
                {
                    "kind": "compose-venv",
                    "repo": COMPOSE_SLUG,
                    "dest": str(workspace / COMPOSE_DIR),
                }
            )

    return actions


def _git_clone_command(slug: str, dest: Path) -> list[str]:
    """A plain-git clone command; token-authenticated when GH_TOKEN is set.

    The URL may embed the token, so it must never be printed or echoed —
    callers log only the slug and destination.
    """
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        url = f"https://x-access-token:{token}@github.com/{slug}.git"
    else:
        url = f"https://github.com/{slug}.git"
    return ["git", "clone", "--depth", "1", "--quiet", url, str(dest)]


def _clone(slug: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"cloning {slug} -> {dest}")
    if shutil.which("gh"):
        gh_cmd = [
            "gh", "repo", "clone", slug, str(dest), "--", "--depth", "1", "--quiet",
        ]
        result = subprocess.run(gh_cmd)
        if result.returncode == 0:
            return
        # gh occasionally fails instantly with no diagnostic under a busy
        # matrix (observed: the same clone succeeds in sibling legs of the
        # same run). Fall back to plain git with the same token rather than
        # failing the leg on CLI flakiness.
        print(
            f"gh repo clone failed (exit {result.returncode}); "
            "retrying with git",
            file=sys.stderr,
        )
        shutil.rmtree(dest, ignore_errors=True)
    subprocess.run(_git_clone_command(slug, dest), check=True)


def execute(actions: list[dict]) -> None:
    for action in actions:
        kind = action["kind"]
        if kind == "clone":
            _clone(action["repo"], Path(action["dest"]))
        elif kind == "symlink":
            link = Path(action["link"])
            link.parent.mkdir(parents=True, exist_ok=True)
            print(f"symlinking {link} -> {action['target']}")
            link.symlink_to(action["target"])
        elif kind == "mkdir":
            path = Path(action["path"])
            print(f"creating {path}")
            path.mkdir(parents=True, exist_ok=True)
        elif kind == "compose-venv":
            dest = Path(action["dest"])
            if not dest.exists():
                _clone(action["repo"], dest)
            venv = dest / ".venv"
            if not venv.exists():
                print(f"building axiom-compose venv in {dest}")
                subprocess.run(["uv", "venv", str(venv)], check=True, cwd=dest)
            subprocess.run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--quiet",
                    "--python",
                    str(venv / "bin" / "python"),
                    "-e",
                    ".",
                ],
                check=True,
                cwd=dest,
            )
        else:  # pragma: no cover - plan kinds are closed above
            raise SystemExit(f"unknown action kind {kind!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="run_comparison.py registry name (matrix leg)")
    parser.add_argument(
        "--workspace",
        default=os.environ.get("HOME", str(Path.home())),
        help="Directory to materialize the supervised layout under (default $HOME).",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Print the planned actions as JSON without executing them.",
    )
    args = parser.parse_args()

    config_path = COMPARISONS_DIR / f"{args.name}.yaml"
    if not config_path.exists():
        raise SystemExit(f"unknown comparison {args.name!r}: {config_path} missing")
    config = yaml.safe_load(config_path.read_text()) or {}

    affected_map = (
        json.loads(AFFECTED_MAP.read_text()) if AFFECTED_MAP.exists() else {}
    )
    repos = mapped_repos(affected_map, args.name)

    workspace = Path(os.path.expandvars(os.path.expanduser(args.workspace))).resolve()
    actions = build_plan(config, repos, workspace)

    if args.plan:
        print(json.dumps(actions, indent=2))
        return 0

    if not actions:
        print(f"{args.name}: workspace already materialized; nothing to do")
        return 0
    execute(actions)
    print(f"{args.name}: materialized {len(actions)} action(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
