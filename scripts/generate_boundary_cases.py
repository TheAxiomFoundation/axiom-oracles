#!/usr/bin/env python
"""Propose threshold-straddling boundary cases from the axiom-corpus registry.

Reads the typed concept registry published by ``axiom-corpus``
(``src/axiom_corpus/concepts/data/<jurisdiction>.yaml``), finds concepts that
name a *threshold* — a bracket boundary, phase-out start, cap, floor, or income
limit — and emits, for each, a below/above pair of **suggested** cases that
straddle it. Output goes to ``grids/<cc>.suggested.yaml``.

Suggestions are never auto-included. ``axiom_oracles.grids.load_grids()``
ignores ``*.suggested.yaml`` on purpose: a human or agent reviews each probe,
fills the concrete boundary value from the referenced PolicyEngine parameter
(the corpus records *which* parameter, not its runtime value), and promotes the
case into the hand-maintained ``grids/<cc>.yaml`` if it earns its place.

Each suggested case carries a ``probe`` provenance block naming the concept id,
the PolicyEngine parameter, the program, and which side of the threshold it
sits on — so a reviewer can see exactly what law each case is meant to exercise.

Usage::

    uv run python scripts/generate_boundary_cases.py                 # us + uk
    uv run python scripts/generate_boundary_cases.py --jurisdiction us
    uv run python scripts/generate_boundary_cases.py --check         # up-to-date?
    uv run python scripts/generate_boundary_cases.py \
        --registry-root /path/to/axiom-corpus/src/axiom_corpus/concepts/data

Deterministic: identical registry input reproduces byte-identical output.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import yaml  # noqa: E402

from axiom_oracles.grids.model import GRID_SCHEMA_VERSION  # noqa: E402

GRID_ROOT = _REPO_ROOT / "grids"

# Jurisdictions to scan by default. BE has no corpus concept file yet (its
# thresholds live only in the oracle-side EUROMOD encodings), so it is omitted
# until axiom-corpus publishes be.yaml.
_DEFAULT_JURISDICTIONS = ("us", "uk")

# A concept whose *name* encodes a numeric boundary. Deliberately conservative:
# these tokens are the ones the corpus uses for statutory thresholds. Applied to
# EVERY jurisdiction — broadening it globally balloons US output (see #135), so
# jurisdiction-specific boundary vocabularies live in the scoped allowlist below.
_THRESHOLD_NAME = re.compile(
    r"threshold|phase[_-]?out[_-]?start|phase[_-]?out[_-]?begin|"
    r"_floor\b|_cap\b|_ceiling\b|_limit\b|bracket|income_limit",
    re.I,
)

# Per-jurisdiction *additional* boundary tokens (axiom-oracles#135). Some
# jurisdictions gate real discontinuities with names the global regex above does
# not catch — UK "allowance"-style boundaries (the personal savings allowance and
# dividend nil-rate allowance edge a nil-rate band; the Universal Credit work
# allowance sets the taper start; the UC capital limits are the £6k/£16k
# eligibility cliffs). Adding these tokens to the *global* regex would balloon the
# US grid (the US corpus has 144 further parameter_value-mapped numeric concepts
# whose names carry "allowance"/"amount"/"limit"-adjacent tokens — +288 cases,
# more than doubling US output). Scoping them per jurisdiction keeps US
# byte-identical (US falls back to the global regex alone) while letting UK reach
# its allowance/capital-limit boundaries the moment they carry a parameter_value
# mapping. As of this change the four families are still classified
# ``not_comparable`` upstream in the axiom-encode PE-mapping source
# (``oracles/policyengine/mappings/uk.yaml``: legal_id_prefix entries for
# ukpga/2007/3/12B, 13A and uksi/2013/376/18, /22 — "parameter-level comparisons
# not yet registered"), so this allowlist emits nothing for them YET; it removes
# the oracles-side name-filter blocker so they surface automatically if/when
# axiom-encode registers a parameter_value comparison. This keeps the two gates
# independent: the name filter (here) and the mapping gate (the corpus edge).
#
# NB these are boundary tokens (a straddle point), NOT benefit-amount tokens: a
# bare "allowance" would also drag in award LEVELS (e.g. attendance-allowance
# weekly rates) that are not thresholds a case straddles, so the UK set names the
# specific boundary families #135 calls out rather than every "allowance".
_JURISDICTION_BOUNDARY_TOKENS: dict[str, re.Pattern[str]] = {
    "uk": re.compile(
        r"savings_allowance|dividend_nil_rate|dividend_allowance|"
        r"work_allowance|capital_limit|prescribed_capital",
        re.I,
    ),
}


def _name_is_boundary(name: str, jurisdiction: str) -> bool:
    """True if the concept name reads as a numeric boundary for this jurisdiction.

    The global :data:`_THRESHOLD_NAME` applies everywhere; a jurisdiction may add
    boundary tokens via :data:`_JURISDICTION_BOUNDARY_TOKENS` without widening the
    match for any other jurisdiction (the #135 scoping requirement).
    """
    if _THRESHOLD_NAME.search(name):
        return True
    extra = _JURISDICTION_BOUNDARY_TOKENS.get(jurisdiction)
    return bool(extra and extra.search(name))


# dtypes that denote a numeric boundary a case can straddle. Judgment/String
# concepts are booleans/labels, not straddle-able amounts.
_NUMERIC_DTYPES = frozenset({"Money", "Rate", "Integer", "Count", "Decimal"})

_PE_ENGINES = ("policyengine_us", "policyengine_uk", "policyengine")


def _discover_registry_root() -> Path | None:
    """Locate the axiom-corpus concept data dir without importing the package."""
    env = os.environ.get("AXIOM_CORPUS_CONCEPTS_ROOT")
    if env:
        return Path(env)
    candidates = [
        _REPO_ROOT.parent / "axiom-corpus",
        Path.home() / "TheAxiomFoundation" / "axiom-corpus",
    ]
    for base in candidates:
        data = base / "src" / "axiom_corpus" / "concepts" / "data"
        if data.is_dir():
            return data
    return None


def _pe_mapping(concept: dict) -> dict | None:
    mappings = concept.get("mappings") or {}
    if not isinstance(mappings, dict):
        return None
    for engine in _PE_ENGINES:
        body = mappings.get(engine)
        if isinstance(body, dict):
            return body
    return None


def _threshold_concepts(registry_path: Path, jurisdiction: str) -> list[dict]:
    payload = yaml.safe_load(registry_path.read_text()) or {}
    concepts = payload.get("concepts") or []
    hits: list[dict] = []
    for concept in concepts:
        if not isinstance(concept, dict):
            continue
        name = str(concept.get("name", ""))
        if not _name_is_boundary(name, jurisdiction):
            continue
        if concept.get("dtype") not in _NUMERIC_DTYPES:
            continue
        pe = _pe_mapping(concept)
        # Require a parameter_value mapping so the probe references a concrete,
        # resolvable PolicyEngine parameter a reviewer can read the value from.
        if not pe or pe.get("mapping_type") != "parameter_value":
            continue
        if not pe.get("parameter"):
            continue
        hits.append(concept)
    # Stable order: by concept id.
    return sorted(hits, key=lambda c: str(c.get("id")))


def _entity_for(concept: dict) -> str:
    entity = concept.get("entity")
    if entity:
        return str(entity)
    # Default to the tax unit for US tax thresholds, else a person.
    program = (_pe_mapping(concept) or {}).get("program") or ""
    return "TaxUnit" if program == "tax" else "Person"


def _suggested_cases_for(concept: dict, jurisdiction: str) -> list[dict]:
    pe = _pe_mapping(concept) or {}
    concept_id = str(concept["id"])
    name = str(concept["name"])
    entity = _entity_for(concept)
    parameter = str(pe.get("parameter"))
    program = pe.get("program")
    dtype = concept.get("dtype")
    unit = concept.get("unit")

    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    base_id = f"{jurisdiction}-boundary-{slug}"
    cases: list[dict] = []
    for side in ("below", "above"):
        probe = {
            "concept": concept_id,
            "parameter": parameter,
            "side": side,
            # The concrete straddle value is intentionally unresolved: the
            # corpus records the parameter, not its runtime value. A reviewer
            # fills this from the referenced PolicyEngine parameter.
            "value": None,
        }
        if program:
            probe["program"] = str(program)
        if dtype:
            probe["dtype"] = str(dtype)
        if unit:
            probe["unit"] = str(unit)
        cases.append(
            {
                "id": f"{base_id}-{side}",
                "period": None,  # reviewer sets the tax year the parameter is for
                "scenario": f"boundary-{slug}-{side}",
                "entity": entity,
                "probe": probe,
            }
        )
    return cases


def build_suggestions(registry_root: Path, jurisdictions) -> dict[str, dict]:
    payloads: dict[str, dict] = {}
    for jurisdiction in jurisdictions:
        registry_path = registry_root / f"{jurisdiction}.yaml"
        if not registry_path.exists():
            continue
        concepts = _threshold_concepts(registry_path, jurisdiction)
        if not concepts:
            continue
        case_sets: dict[str, dict] = {}
        for concept in concepts:
            cases = _suggested_cases_for(concept, jurisdiction)
            # Group by program so a reviewer can adopt a program's probes as a
            # coherent case set.
            program = (_pe_mapping(concept) or {}).get("program") or "unmapped"
            set_name = f"boundary-{program}"
            case_sets.setdefault(set_name, {"cases": []})["cases"].extend(cases)
        ordered = {name: case_sets[name] for name in sorted(case_sets)}
        payloads[jurisdiction] = {
            "schema_version": GRID_SCHEMA_VERSION,
            "jurisdiction": jurisdiction,
            "generated_from": {
                "registry": f"axiom-corpus concepts/data/{jurisdiction}.yaml",
                "generator": "scripts/generate_boundary_cases.py",
                "note": (
                    "SUGGESTED threshold-straddling cases; not adopted. Each "
                    "case's probe.value is unresolved — fill it from the named "
                    "PolicyEngine parameter, set period, then promote into "
                    f"grids/{jurisdiction}.yaml if warranted."
                ),
            },
            "case_sets": ordered,
        }
    return payloads


class _Dumper(yaml.SafeDumper):
    pass


_Dumper.ignore_aliases = lambda self, data: True  # type: ignore[assignment]

_HEADER = (
    "# SUGGESTED boundary cases — GENERATED; NOT adopted, NOT loaded by "
    "load_grids().\n"
    "# Regenerate with: uv run python scripts/generate_boundary_cases.py\n"
    "# Each case probes one statutory threshold from the axiom-corpus concept\n"
    "# registry. probe.value is intentionally null: read it from the named\n"
    "# PolicyEngine parameter, set period, then promote into the adopted grid.\n"
    "# See grids/README.md (boundary-case generator).\n"
)


def _dump(payload: dict) -> str:
    return _HEADER + yaml.dump(
        payload,
        Dumper=_Dumper,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=100,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jurisdiction", help="Only this jurisdiction (us, uk).")
    parser.add_argument(
        "--registry-root",
        type=Path,
        help="axiom-corpus concepts/data dir (auto-discovered if omitted).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; exit non-zero if any suggestion file is stale.",
    )
    args = parser.parse_args()

    registry_root = args.registry_root or _discover_registry_root()
    if registry_root is None or not registry_root.is_dir():
        print(
            "Could not find the axiom-corpus concept registry. Pass "
            "--registry-root or set AXIOM_CORPUS_CONCEPTS_ROOT.",
            file=sys.stderr,
        )
        # A missing corpus checkout is not a CI failure — the committed
        # suggestion files stand on their own. Skip cleanly.
        return 0

    jurisdictions = (
        (args.jurisdiction,) if args.jurisdiction else _DEFAULT_JURISDICTIONS
    )
    GRID_ROOT.mkdir(parents=True, exist_ok=True)
    payloads = build_suggestions(registry_root, jurisdictions)

    stale: list[str] = []
    for jurisdiction in jurisdictions:
        path = GRID_ROOT / f"{jurisdiction}.suggested.yaml"
        payload = payloads.get(jurisdiction)
        if payload is None:
            continue
        rendered = _dump(payload)
        if args.check:
            existing = path.read_text() if path.exists() else ""
            if existing != rendered:
                stale.append(jurisdiction)
            continue
        path.write_text(rendered)
        case_count = sum(len(cs["cases"]) for cs in payload["case_sets"].values())
        print(
            f"wrote {path.relative_to(_REPO_ROOT)} "
            f"({len(payload['case_sets'])} probe sets, {case_count} suggested cases)"
        )

    if args.check and stale:
        print(
            "Suggestion files are out of date for: "
            + ", ".join(stale)
            + "\nRun: uv run python scripts/generate_boundary_cases.py"
        )
        return 1
    if args.check:
        print("Suggestions up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
