#!/usr/bin/env python3
"""Generate comparisons/affected_map.json — the suite → rulespec-repo map (O2).

Each comparison suite exercises encoded rules that live in one or more rulespec
repos. When a rulespec repo's ``main`` moves ahead of the SHA a suite last ran
against, that suite's checked-in report is *stale-affected* and should be rerun
— but only that suite, not the whole weekly matrix. This script derives the
mapping deterministically from the committed comparison configs so the
affected-rerun workflow (``.github/workflows/affected-rerun.yml``) has a
committed, reviewable source of truth instead of re-parsing configs in bash.

Derivation, per suite, unions three signals (all deterministic):

1. **rulespec checkout path** — the singular explicit ``rulespec_root``. Its
   exact ``rulespec-<country>`` basename names the repo directly.
2. **concept id prefixes** — a concept like ``us-co:policies/…#co_tanf_benefit``
   is encoded in ``rulespec-us``; ``us:statutes/…`` is in the same checkout;
   ``uk:…`` in the UK rulespec; ``be:…`` in ``rulespec-be``. This backstops
   suites whose rulespec paths are indirected (e.g. rsync'd roots).
3. **parameter-suite ``file:`` prefixes** — the non-registry
   ``parameter-oracles.yaml`` names files like ``us-ga/policies/…`` whose top
   path segment maps to a rulespec repo the same way.

The output is sorted and stable; ``--check`` fails if the committed file drifts
from a fresh regeneration, so CI keeps it honest.

Usage:
    uv run scripts/generate_affected_map.py            # write the file
    uv run scripts/generate_affected_map.py --check    # verify; non-zero on drift
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - CI installs pyyaml
    sys.stderr.write("PyYAML is required (uv pip install pyyaml).\n")
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPARISONS_DIR = REPO_ROOT / "comparisons"
OUTPUT_PATH = COMPARISONS_DIR / "affected_map.json"

# Canonical slug logic lives in axiom_oracles.provenance so that the slugs the
# report stamper writes (provenance.rulespecs[].repo) and the keys this map
# emits are produced by ONE function — otherwise the two could diverge and the
# affected-rerun selector would silently fail to match a suite to its repo.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from axiom_oracles.provenance import (  # noqa: E402
    RULESPEC_OWNER,
    canonical_rulespec_slug as _slug,
)
from axiom_oracles.bridges.repo_routing import jurisdiction_country  # noqa: E402


def _rel(path: Path) -> str:
    """Repo-relative display path, tolerant of paths outside the repo (tests)."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _repo_from_path(path_str: str) -> str | None:
    """Map a declared exact canonical checkout path to its repository slug.

    This generator is deterministic metadata tooling: it validates the lexical
    basename in the registry without inspecting whatever happens to exist at
    the expanded local path on the machine running ``--check``.
    """

    path = Path(os.path.expandvars(os.path.expanduser(str(path_str))))
    try:
        return _slug(path.name)
    except ValueError as exc:
        raise ValueError(
            f"not an exact canonical RuleSpec checkout path: {path}"
        ) from exc


def _repo_from_prefix(prefix: str) -> str | None:
    """Map a concept/file jurisdiction prefix (``us``, ``us-co``, ``uk``, ``be``)
    to its canonical country-checkout slug."""
    prefix = prefix.strip().lower()
    if not prefix:
        return None
    return _slug(f"rulespec-{jurisdiction_country(prefix)}")


def _concept_prefix(concept: str) -> str | None:
    # ``us-co:policies/…#co_tanf_benefit`` → ``us-co``. A concept id without a
    # ``:`` has no jurisdiction prefix; return None rather than feeding the whole
    # (underscored) body into the slugger and minting a garbage repo name.
    if ":" not in concept:
        return None
    head = concept.split(":", 1)[0]
    return head or None


def repos_for_registry_config(config: dict) -> set[str]:
    repos: set[str] = set()
    runner = config.get("runner") or {}
    params = runner.get("parameters") or {}

    legacy_keys = {
        key
        for section in (runner, params)
        for key in ("rulespec_roots", "rulespec_remote", "axiom_rulespec_repo_roots")
        if key in section
    }
    if legacy_keys:
        raise ValueError(
            "legacy RuleSpec routing keys are unsupported: "
            + ", ".join(sorted(legacy_keys))
        )

    uses_axiom = runner.get("type") != "axiom-oracles-compare" or "axiom" in {
        params.get("left"),
        params.get("right"),
    }
    root = runner.get("rulespec_root") or params.get("rulespec_root")
    if uses_axiom and not root:
        raise ValueError(
            f"comparison {config.get('name', '<unnamed>')!r} must declare "
            "one explicit rulespec_root"
        )
    if root:
        repos.add(_repo_from_path(str(root)))

    concepts = params.get("concepts") or (
        [params["concept"]] if params.get("concept") else []
    )
    for concept in concepts if uses_axiom else ():
        prefix = _concept_prefix(str(concept))
        slug = _repo_from_prefix(prefix) if prefix else None
        if slug:
            repos.add(slug)

    # State and federal US rules share the same canonical country checkout.
    jurisdiction = params.get("jurisdiction")
    if runner.get("type") == "axiom-encode-snap-populace-compare" and jurisdiction:
        state_slug = _repo_from_prefix(str(jurisdiction))
        if state_slug:
            repos.add(state_slug)
        repos.add(_slug("rulespec-us"))

    # The SNAP QC administrative-data lane uses that same country checkout.
    if runner.get("type") == "snap-qc-compare" and jurisdiction:
        state_slug = _repo_from_prefix(str(jurisdiction))
        if state_slug:
            repos.add(state_slug)
        repos.add(_slug("rulespec-us"))

    # EUROMOD/UKMOD also declares an exact country checkout; the country field
    # remains a cross-checking dependency signal.
    euromod_country = params.get("euromod_country")
    if runner.get("type") == "euromod-synthetic-compare" and euromod_country:
        country_slug = _repo_from_prefix(str(euromod_country))
        if country_slug:
            repos.add(country_slug)

    return repos


def parameter_suite_entries(config: dict) -> list[dict]:
    """Derive one affected-map entry per suite in ``parameter-oracles.yaml``.

    The parameter runner reads encoded formulas from ``file:`` paths whose top
    segment (``us``, ``us-ga``, ``us-co``…) names the rulespec repo. Each suite
    also writes ``axiom-policyengine-<suite>.json``, so the map keys match the
    dashboard report suites the freshness view checks.
    """
    entries: list[dict] = []
    for suite in config.get("suites") or []:
        repos: set[str] = set()
        for comparison in suite.get("comparisons") or []:
            file_ref = str(comparison.get("file") or "")
            top = file_ref.split("/", 1)[0]
            slug = _repo_from_prefix(top) if top else None
            if slug:
                repos.add(slug)
        entries.append(
            {
                "suite": suite["suite"],
                "report": f"axiom-policyengine-{suite['suite']}.json",
                "repos": sorted(repos),
                "source": "comparisons/parameter-oracles.yaml",
            }
        )
    return entries


def build_map() -> dict:
    entries: list[dict] = []
    for path in sorted(COMPARISONS_DIR.glob("*.yaml")):
        if path.name.endswith(".fixtures.yaml"):
            continue
        config = yaml.safe_load(path.read_text())
        if not isinstance(config, dict):
            continue
        # The declarative parameter-suite list is not a single runner config;
        # it fans out to one entry per suite it declares.
        if config.get("kind") == "parameter-suite-list":
            entries.extend(parameter_suite_entries(config))
            continue
        if "name" not in config:
            # Defensive: any other non-registry file is skipped, not crashed
            # on (the #73 lesson — never let one odd file break the tool).
            continue
        suite = (config.get("dashboard") or {}).get("suite", config["name"])
        report = (config.get("dashboard") or {}).get("filename")
        entries.append(
            {
                "suite": suite,
                "report": report,
                "repos": sorted(repos_for_registry_config(config)),
                "source": f"comparisons/{path.name}",
            }
        )

    entries.sort(key=lambda e: (e["suite"], e.get("source", "")))
    return {
        "schema": "axiom_oracles.affected_map.v1",
        "_comment": (
            "Generated by scripts/generate_affected_map.py — do not hand-edit. "
            "Maps each comparison suite to the rulespec repos its concepts "
            "exercise. The affected-rerun workflow reruns only suites whose "
            "affected repos have advanced past the SHA their report last ran "
            "against (report provenance.rulespecs)."
        ),
        "owner": RULESPEC_OWNER,
        "suites": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the committed file matches a fresh regeneration.",
    )
    args = parser.parse_args()

    generated = build_map()
    serialized = json.dumps(generated, indent=2) + "\n"

    if args.check:
        if not OUTPUT_PATH.exists():
            sys.stderr.write(
                f"{_rel(OUTPUT_PATH)} is missing; run "
                "`uv run scripts/generate_affected_map.py`.\n"
            )
            return 1
        current = OUTPUT_PATH.read_text()
        if current != serialized:
            sys.stderr.write(
                f"{_rel(OUTPUT_PATH)} is stale; run "
                "`uv run scripts/generate_affected_map.py`.\n"
            )
            return 1
        suites = generated["suites"]
        print(
            f"affected_map OK: {len(suites)} suites, "
            f"{sum(len(s['repos']) for s in suites)} suite-repo edges"
        )
        return 0

    OUTPUT_PATH.write_text(serialized)
    print(f"Wrote {_rel(OUTPUT_PATH)}: {len(generated['suites'])} suites")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
