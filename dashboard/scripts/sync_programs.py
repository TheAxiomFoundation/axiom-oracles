#!/usr/bin/env python3
"""Sync dashboard/public/data/programs.json against the Axiom corpus.

For each concept in axiom_oracles/config/concept_mappings.yaml that targets
Axiom, this script:

1. Extracts the rule name from the Axiom target (e.g. ``us:statutes/26/6401#income_tax``
   → ``income_tax``).
2. Scans every YAML file across all configured corpus repos for top-level rule
   definitions matching that name.
3. Infers each match's jurisdiction from the repo name (e.g. ``rulespec-us`` →
   federal, ``rules-us-co`` → Colorado).
4. Emits a ``coverage`` list per program so the dashboard can show exactly
   which jurisdictions have an encoding.

A program with no encoded rule definitions anywhere is marked ``missing`` and
hidden from the dashboard. ``encoding_status`` and ``encoding_note`` from the
prior run are preserved so manual annotations (live/partial) survive.

Usage::

    uv run --with pyyaml python scripts/sync_programs.py \\
        --corpus ~/rulespec-us \\
        --corpus ~/rules-us-co
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write("This script requires PyYAML. Install with: pip install pyyaml\n")
    sys.exit(1)


# US state codes → display name. Add as new state repos land.
US_STATE_NAMES = {
    "al": "Alabama", "ak": "Alaska", "az": "Arizona", "ar": "Arkansas",
    "ca": "California", "co": "Colorado", "ct": "Connecticut", "de": "Delaware",
    "fl": "Florida", "ga": "Georgia", "hi": "Hawaii", "id": "Idaho",
    "il": "Illinois", "in": "Indiana", "ia": "Iowa", "ks": "Kansas",
    "ky": "Kentucky", "la": "Louisiana", "me": "Maine", "md": "Maryland",
    "ma": "Massachusetts", "mi": "Michigan", "mn": "Minnesota", "ms": "Mississippi",
    "mo": "Missouri", "mt": "Montana", "ne": "Nebraska", "nv": "Nevada",
    "nh": "New Hampshire", "nj": "New Jersey", "nm": "New Mexico", "ny": "New York",
    "nc": "North Carolina", "nd": "North Dakota", "oh": "Ohio", "ok": "Oklahoma",
    "or": "Oregon", "pa": "Pennsylvania", "ri": "Rhode Island", "sc": "South Carolina",
    "sd": "South Dakota", "tn": "Tennessee", "tx": "Texas", "ut": "Utah",
    "vt": "Vermont", "va": "Virginia", "wa": "Washington", "wv": "West Virginia",
    "wi": "Wisconsin", "wy": "Wyoming", "dc": "District of Columbia",
}


def jurisdiction_for(corpus_root: Path) -> dict:
    """Infer jurisdiction from a corpus repo name.

    rulespec-us       → {"label": "Federal (US)", "scope": "federal", "country": "US"}
    rules-us-co       → {"label": "Colorado", "scope": "state", "country": "US", "state": "CO"}
    rulespec-us-ca    → California (same pattern)
    rulespec-uk       → United Kingdom
    rulespec-ca       → Canada federal
    Anything else     → raw repo name.
    """
    name = corpus_root.name.lower()
    match = re.match(r"(rulespec|rules)-([a-z]{2})(?:-([a-z]{2}))?$", name)
    if not match:
        return {"label": corpus_root.name, "scope": "unknown"}
    _, country, sub = match.groups()
    if country == "us" and sub:
        state_name = US_STATE_NAMES.get(sub, sub.upper())
        return {
            "label": state_name,
            "scope": "state",
            "country": "US",
            "state": sub.upper(),
        }
    if country == "us":
        return {"label": "Federal (US)", "scope": "federal", "country": "US"}
    if country == "uk":
        return {"label": "United Kingdom", "scope": "federal", "country": "UK"}
    if country == "ca":
        return {"label": "Federal (Canada)", "scope": "federal", "country": "CA"}
    return {"label": corpus_root.name, "scope": "unknown"}


def extract_rule_names(yaml_path: Path) -> set[str]:
    """Return the set of top-level rule names defined in a RuleSpec YAML file."""
    try:
        doc = yaml.safe_load(yaml_path.read_text())
    except Exception:
        return set()
    if not isinstance(doc, dict):
        return set()
    rules = doc.get("rules") or []
    if not isinstance(rules, list):
        return set()
    names = set()
    for rule in rules:
        if isinstance(rule, dict) and "name" in rule:
            names.add(rule["name"])
    return names


def build_rule_index(corpus_roots: list[Path]) -> dict[str, list[dict]]:
    """Map rule_name → list of {corpus, file, jurisdiction} where it's defined."""
    index: dict[str, list[dict]] = {}
    for root in corpus_roots:
        if not root.exists():
            sys.stderr.write(f"warning: corpus root not found: {root}\n")
            continue
        jurisdiction = jurisdiction_for(root)
        for yaml_path in root.rglob("*.yaml"):
            if yaml_path.name.endswith(".test.yaml"):
                continue
            for name in extract_rule_names(yaml_path):
                index.setdefault(name, []).append(
                    {
                        "corpus": root.name,
                        "file": str(yaml_path.relative_to(root)),
                        **jurisdiction,
                    }
                )
    return index


def load_existing(programs_json: Path) -> dict[str, dict]:
    if not programs_json.exists():
        return {}
    payload = json.loads(programs_json.read_text())
    return {p["id"]: p for p in payload.get("programs", [])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        action="append",
        type=Path,
        required=True,
        help="Path to a rulespec corpus root. Can be repeated.",
    )
    parser.add_argument(
        "--mappings",
        type=Path,
        default=Path(__file__).resolve().parents[2]
        / "axiom_oracles/config/concept_mappings.yaml",
        help="Path to concept_mappings.yaml.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent.parent
        / "public/data/programs.json",
    )
    args = parser.parse_args()

    corpus_roots = [c.expanduser().resolve() for c in args.corpus]
    rule_index = build_rule_index(corpus_roots)

    with open(args.mappings) as fh:
        mappings = yaml.safe_load(fh)

    existing = load_existing(args.output)

    programs: list[dict] = []
    for concept_id, concept in (mappings.get("concepts") or {}).items():
        targets = concept.get("targets") or {}
        axiom_target = targets.get("axiom")
        if not axiom_target:
            continue

        prior = existing.get(concept_id, {})

        # Detect coverage by checking every alias of this concept across the
        # corpus. Aliases default to the rule name in the axiom_target but can
        # be hand-extended in programs.json (e.g., SNAP benefit also matches
        # ``snap_allotment``, the actual output rule used by state encodings).
        canonical_rule = (
            axiom_target.split("#", 1)[1] if "#" in axiom_target else None
        )
        aliases = list(prior.get("rule_aliases") or [])
        if canonical_rule and canonical_rule not in aliases:
            aliases.insert(0, canonical_rule)

        coverage = []
        for alias in aliases:
            coverage.extend(rule_index.get(alias, []))

        # Dedupe coverage by (corpus, file), preferring entries where the
        # canonical alias matched (more precise) over later ones.
        seen = set()
        unique_coverage = []
        for entry in coverage:
            key = (entry["corpus"], entry["file"])
            if key in seen:
                continue
            seen.add(key)
            unique_coverage.append(entry)

        present = bool(unique_coverage)

        # If the corpus actually contains the rule, preserve any hand-curated
        # status (live, partial, …). If it doesn't, force ``missing`` — manual
        # annotations should not paper over an empty corpus.
        if present:
            encoding_status = prior.get("encoding_status") or "present"
            if encoding_status == "missing":
                encoding_status = "present"
        else:
            encoding_status = "missing"

        program = {
            "id": concept_id,
            "name": concept.get("description", concept_id),
            "category": concept.get("category"),
            "axiom_ref": axiom_target.split("#", 1)[0],
            "axiom_target": axiom_target,
            "statute_label": prior.get(
                "statute_label", _statute_label(axiom_target)
            ),
            "comparison": concept.get("comparison"),
            "tolerance": concept.get("tolerance"),
            "oracles": prior.get("oracles") or sorted(_oracle_keys(targets)),
            "rule_aliases": aliases,
            "encoding_status": encoding_status,
            "coverage": unique_coverage,
        }
        if present and prior.get("encoding_note"):
            program["encoding_note"] = prior["encoding_note"]
        programs.append(program)

    out = {
        "_comment": (
            "Generated by dashboard/scripts/sync_programs.py. coverage[] lists "
            "every (corpus, file) where the Axiom rule is defined, with the "
            "inferred jurisdiction. encoding_status is auto-set to "
            "'present' or 'missing' on first generation, but hand-curated "
            "values like 'live' or 'partial' are preserved on re-run."
        ),
        "programs": programs,
    }
    args.output.write_text(json.dumps(out, indent=2) + "\n")

    live = sum(1 for p in programs if p["encoding_status"] not in ("missing",))
    print(f"Wrote {len(programs)} programs to {args.output} ({live} encoded)")
    for p in programs:
        if p["coverage"]:
            jurisdictions = ", ".join(
                sorted({c["label"] for c in p["coverage"]})
            )
            print(f"  ✓ {p['name']:<40s} {jurisdictions}")
        else:
            print(f"  ✗ {p['name']:<40s} (not in any corpus)")

    return 0


def _statute_label(target: str) -> str:
    base = target.split("#", 1)[0]
    if base.startswith("us:statutes/"):
        rest = base[len("us:statutes/"):]
        parts = rest.split("/")
        if len(parts) >= 2:
            title = parts[0]
            section = "/".join(parts[1:])
            return f"{title} USC § {section}"
    if base.startswith("us:programs/"):
        return base[len("us:programs/"):]
    return base


def _oracle_keys(targets: dict) -> set[str]:
    return {k for k, v in targets.items() if v}


if __name__ == "__main__":
    raise SystemExit(main())
