#!/usr/bin/env python3
"""Regenerate encoded-program coverage from canonical RuleSpec checkouts.

The script reads only explicitly supplied ``rulespec-<country>`` checkouts,
classifies canonical ``.yaml`` rule files into program/jurisdiction buckets, and
rewrites the *generated* entries in ``dashboard/public/data/coverage_overview.json``'s
``axiom.programs`` list.

Hand-curated entries (anything without ``"generated": true``) are preserved
and take precedence: a generated entry is only added for (family,
jurisdiction) pairs no manual entry covers. Unclassified paths are reported
so classification gaps are visible instead of silently dropped.

Usage::

    python scripts/sync_encoded_coverage.py \
      --rulespec-root ~/TheAxiomFoundation/rulespec-us \
      --rulespec-root ~/TheAxiomFoundation/rulespec-ca
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from axiom_oracles.bridges.repo_routing import (
    RULESPEC_ATOMIC_ROOTS,
    canonical_rulespec_module_path,
    iter_jurisdiction_content_dirs,
)
from axiom_oracles.bridges.rulespec_paths import require_rulespec_checkout

REPO_ROOT = Path(__file__).resolve().parents[1]
COVERAGE_PATH = REPO_ROOT / "dashboard" / "public" / "data" / "coverage_overview.json"

# (regex on repo-relative rule path) → (family, jurisdiction or None=from repo)
# First match wins. Jurisdiction None means "use the repo's state code".
FEDERAL_RULES = [
    (r"^policies/ssa/", ("social_security", "US")),
    (r"^statutes/42/1382", ("ssi", "US")),
    (r"^statutes/42/1396", ("medicaid_eligibility_groups", "US")),
    (r"^statutes/42/1397jj", ("chip", "US")),
    (r"^regulations/42-cfr/457/", ("chip", "US")),
    (r"^regulations/42-cfr/(431|435|438|600)/", ("medicaid_eligibility_groups", "US")),
    (r"^statutes/42/1786", ("wic", "US")),
    (r"^statutes/42/426", ("medicare", "US")),
    (r"^statutes/42/18795", ("energy_rebates", "US")),
    (r"^statutes/8/", ("immigrant_eligibility", "US")),
    (r"^(statutes/20/|policies/ed/)", ("pell_grant", "US")),
    (r"^regulations/45-cfr/1302/", ("head_start", "US")),
    (r"^regulations/47-cfr/54/", ("lifeline", "US")),
    (r"^(statutes/7/|regulations/7-cfr/|policies/usda/)", ("snap_federal", "US")),
    (r"^(statutes/26/|policies/irs/)", ("federal_income_tax", "US")),
    (r"^statutes/(5|37)/", ("other_federal", "US")),
]

STATE_RULES = {
    "ak": [
        (r"^policies/dpa/apa/", ("state_ssi_supplement", None)),
        (r"^(policies/dpa/atap/|regulations/aac/title-7/chapter-45/)", ("tanf", None)),
    ],
    "al": [
        (r"^policies/dhr/poe/", ("snap", None)),
        (r"^regulations/660-4/", ("snap", None)),
    ],
    "az": [
        (r"^policies/des/ccap/", ("childcare_assistance", None)),
        (r"^policies/des/faa5/(ca-|two-parent)", ("tanf", None)),
        (r"^policies/des/faa5/transitional-child-care", ("childcare_assistance", None)),
        (r"^policies/des/faa5/", ("snap", None)),
        (
            r"^regulations/aac/title-6/chapter-5/article-49/",
            ("childcare_assistance", None),
        ),
    ],
    "ca": [
        (r"^(policies/cdss/snap|regulations/mpp/)", ("snap", None)),
        (r"^policies/cdss/calworks/", ("tanf", None)),
        (r"^regulations/cdss/eas/49/", ("state_ssi_supplement", None)),
    ],
    "co": [
        (r"^(policies/cdhs/snap|regulations/10-ccr-2506-1/)", ("snap", None)),
        (r"^(policies/cdhs/colorado-works|regulations/9-ccr-2503-6/)", ("tanf", None)),
        (r"^regulations/9-ccr-2503-5/", ("state_ssi_supplement", None)),
        (r"^policies/cms/", ("medicaid_chip_bhp_thresholds", None)),
        (r"^statutes/39/", ("state_income_tax", None)),
    ],
    "fl": [
        (r"ess-program-policy-manual/.*fs-tca", ("snap", None)),
        (r"ess-program-policy-manual/.*(cic-rap|tca)", ("tanf", None)),
        (
            r"ess-program-policy-manual/.*(mfam|mssi)",
            ("medicaid_eligibility_groups", None),
        ),
        (
            r"^(policies/dcf/ess-program-policy-manual/|regulations/fac/65a-1/)",
            ("snap", None),
        ),
    ],
    "il": [
        (r"^(policies/dhs/csmm/|statutes/320/)", ("state_ssi_supplement", None)),
    ],
    "ks": [(r"^policies/dcf/keesm/", ("tanf", None))],
    "mi": [(r"^policies/mdhhs/", ("state_ssi_supplement", None))],
    "mn": [
        (r"^policies/dhs/combined-manual/0020", ("state_ssi_supplement", None)),
        (r"^policies/dhs/combined-manual/0022", ("tanf", None)),
    ],
    "ga": [
        (r"^policies/cms/", ("medicaid_chip_bhp_thresholds", None)),
        (r"^policies/decal/caps/", ("childcare_assistance", None)),
    ],
    "id": [(r"^regulations/idapa/16/03/04/", ("snap", None))],
    "ma": [(r"^(policies/dta/snap|regulations/106-cmr/)", ("snap", None))],
    "nc": [
        (r"^policies/dhhs/fns/", ("snap", None)),
        (r"^regulations/10a-ncac/71u/", ("snap", None)),
    ],
    "nh": [(r"^regulations/he-w-700/", ("snap", None))],
    "ny": [
        (r"^(policies/otda/snap|regulations/18-nycrr/387)", ("snap", None)),
        (r"^(policies/otda/tanf|regulations/18-nycrr/385)", ("tanf", None)),
        (r"^policies/tax/", ("state_income_tax", None)),
        (r"^statutes/NYC", ("nyc_income_tax", "NYC")),
    ],
    "or": [(r"^policies/odhs/", ("snap", None))],
    "sc": [(r"^(policies/dss/snap|regulations/114/)", ("snap", None))],
    "tn": [
        (r"^policies/dhs/snap/", ("snap", None)),
        (r"^regulations/1240-01/", ("snap", None)),
    ],
    "ut": [(r"^policies/dws/", ("snap", None))],
    "wa": [
        (r"^regulations/388/388-474/", ("state_ssi_supplement", None)),
        (r"^regulations/388/", ("tanf", None)),
    ],
}

# Last-resort keyword classification for state paths no explicit rule matched;
# keeps newly landed manuals visible (with correct family) until a precise
# pattern is added above.
GENERIC_STATE_RULES = [
    (r"(snap|food-stamp|food-and-nutrition|fns)", "snap"),
    (r"(tanf|colorado-works|temporary-cash|tca|works-program)", "tanf"),
    (r"policies/cms/", "medicaid_chip_bhp_thresholds"),
    (r"(medicaid|mssi|mfam)", "medicaid_eligibility_groups"),
    (r"(income-tax|/tax/)", "state_income_tax"),
    (r"(child-?care|ccdf|caps)", "childcare_assistance"),
]

SKIP_DIRS = re.compile(
    r"(^|/)(\.axiom|artifacts|_compose|\.github|programs|sources|tests)(/|$)"
    r"|^known-[a-z-]+\.yaml$"
)


def rule_files(repo: Path) -> list[str]:
    """Return canonical ``.yaml`` modules relative to one country checkout."""

    out = []
    for _jurisdiction, content_root in iter_jurisdiction_content_dirs(repo):
        for root_name in RULESPEC_ATOMIC_ROOTS:
            canonical_root = content_root / root_name
            if not canonical_root.is_dir() or canonical_root.is_symlink():
                continue
            for path in canonical_root.rglob("*"):
                relative = path.relative_to(repo).as_posix()
                if path.is_symlink():
                    raise ValueError(
                        f"symlinked RuleSpec content is unsupported: {path}"
                    )
                if path.is_file() and path.suffix == ".yml":
                    raise ValueError(
                        f"legacy .yml RuleSpec module is unsupported: {path}"
                    )
                if path.suffix != ".yaml" or not path.is_file():
                    continue
                if (
                    canonical_rulespec_module_path(path, content_root=content_root)
                    is None
                ):
                    raise ValueError(f"noncanonical RuleSpec module path: {path}")
                if relative.endswith(".test.yaml") or SKIP_DIRS.search(relative):
                    continue
                out.append(relative)
    return out


def classify(path: str):
    """Classify one monorepo path: ``us/...`` federal, ``us-xx/...`` state."""
    first, _, rest = path.partition("/")
    if first == "us":
        for pattern, (family, jurisdiction) in FEDERAL_RULES:
            if re.search(pattern, rest):
                return family, jurisdiction
        return None
    match = re.match(r"^us-([a-z]{2})$", first)
    if not match:
        return None
    state = match.group(1).upper()
    for pattern, (family, jurisdiction) in STATE_RULES.get(match.group(1), []):
        if re.search(pattern, rest):
            return family, jurisdiction or state
    for pattern, family in GENERIC_STATE_RULES:
        if re.search(pattern, rest):
            return family, state
    return None


CANADA_RULES = [
    (
        r"^policies/(cra/benefits-2026|esdc/benefits-2026)/",
        ("canada_family_benefits", "CAN"),
    ),
    (
        r"^policies/(cra|revenu-quebec)/",
        ("canada_personal_income_tax", "CAN"),
    ),
]


def classify_canada(path: str):
    for pattern, hit in CANADA_RULES:
        if re.search(pattern, path):
            return hit
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rulespec-root",
        action="append",
        type=Path,
        required=True,
        help="Exact canonical country checkout; repeat for each country.",
    )
    args = parser.parse_args()

    buckets: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"count": 0, "areas": set(), "repos": set()}
    )
    unclassified: dict[str, int] = defaultdict(int)

    checkouts = [require_rulespec_checkout(path) for path in args.rulespec_root]
    for repo in checkouts:
        country = repo.name.removeprefix("rulespec-")
        if country not in {"us", "ca"}:
            parser.error(f"unsupported coverage classifier country: {country}")
        for path in rule_files(repo):
            if country == "us":
                hit = classify(path)
                area = "/".join(path.split("/")[1:4])
            else:
                _jurisdiction, _, content_path = path.partition("/")
                hit = classify_canada(content_path)
                area = "/".join(content_path.split("/")[:3])
            if hit is None:
                unclassified[f"{repo.name}:{'/'.join(path.split('/')[:3])}"] += 1
                continue
            family, jurisdiction = hit
            bucket = buckets[(family, jurisdiction)]
            bucket["count"] += 1
            bucket["areas"].add(area)
            bucket["repos"].add(repo.name)

    data = json.loads(COVERAGE_PATH.read_text())
    programs = data["axiom"]["programs"]
    manual_keys = {
        (p.get("program"), p.get("jurisdiction"))
        for p in programs
        if not p.get("generated")
    }
    programs[:] = [p for p in programs if not p.get("generated")]

    for (family, jurisdiction), bucket in sorted(buckets.items()):
        if (family, jurisdiction) in manual_keys:
            continue
        areas = ", ".join(sorted(bucket["areas"]))
        if len(areas) > 160:
            areas = areas[:157] + "…"
        repos = ", ".join(sorted(bucket["repos"]))
        programs.append(
            {
                "program": family,
                "jurisdiction": jurisdiction,
                "status": "coverageOnly",
                "generated": True,
                "source": f"{repos}: {areas} ({bucket['count']} rule files)",
                "known_non_tanf_gaps": [
                    "encoded upstream; no comparison suite yet",
                ],
            }
        )

    COVERAGE_PATH.write_text(json.dumps(data, indent=1) + "\n")

    total = sum(b["count"] for b in buckets.values())
    print(
        f"classified {total} rule files into {len(buckets)} (family, jurisdiction) buckets"
    )
    for (family, jurisdiction), bucket in sorted(buckets.items()):
        marker = "manual" if (family, jurisdiction) in manual_keys else "generated"
        print(f"  {family:32} {jurisdiction:4} {bucket['count']:5} rules  [{marker}]")
    if unclassified:
        print(f"unclassified ({sum(unclassified.values())} files):")
        for key, count in sorted(unclassified.items(), key=lambda kv: -kv[1])[:15]:
            print(f"  {count:5}  {key}")


if __name__ == "__main__":
    main()
