#!/usr/bin/env python3
"""Regenerate encoded-program coverage from upstream corpus git trees.

Local corpus checkouts drift hundreds of commits behind origin/main, so this
script reads ``git ls-tree origin/main`` (after a fetch) for upstream rulespec
repos, classifies rule files into (program family, jurisdiction) buckets, and
rewrites the *generated* entries in ``dashboard/public/data/coverage_overview.json``'s
``axiom.programs`` list.

Hand-curated entries (anything without ``"generated": true``) are preserved
and take precedence: a generated entry is only added for (family,
jurisdiction) pairs no manual entry covers. Unclassified paths are reported
so classification gaps are visible instead of silently dropped.

Usage::

    python scripts/sync_encoded_coverage.py            # fetch + rewrite
    python scripts/sync_encoded_coverage.py --no-fetch # offline rerun
    python scripts/sync_encoded_coverage.py \
      --rulespec /path/to/rulespec-us --ref <commit> --no-fetch
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

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
        (
            r"^policies/income_tax/"
            r"2026_section_40_18_5_schedule_before_credits\.yaml$",
            ("state_income_tax", None),
        ),
    ],
    "ar": [
        (
            r"^policies/income_tax/pilot_liability_pipeline\.yaml$",
            ("state_income_tax", None),
        ),
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
        (
            r"^policies/income_tax/pilot_liability_pipeline\.yaml$",
            ("state_income_tax", None),
        ),
    ],
    "co": [
        (r"^(policies/cdhs/snap|regulations/10-ccr-2506-1/)", ("snap", None)),
        (r"^(policies/cdhs/colorado-works|regulations/9-ccr-2503-6/)", ("tanf", None)),
        (r"^regulations/9-ccr-2503-5/", ("state_ssi_supplement", None)),
        (r"^policies/cms/", ("medicaid_chip_bhp_thresholds", None)),
        (r"^statutes/39/", ("state_income_tax", None)),
    ],
    "ct": [
        (
            r"^policies/income_tax/"
            r"2026_resident_ordinary_tax_before_personal_credit\.yaml$",
            ("state_income_tax", None),
        ),
    ],
    "dc": [
        (
            r"^policies/income_tax/"
            r"2026_section_47_1806_03_schedule_before_credits\.yaml$",
            ("state_income_tax", None),
        ),
    ],
    "de": [
        (
            r"^policies/income_tax/pilot_liability_pipeline\.yaml$",
            ("state_income_tax", None),
        ),
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
        (
            r"^policies/income_tax/pilot_liability_pipeline\.yaml$",
            ("state_income_tax", None),
        ),
    ],
    "in": [
        (
            r"^policies/income_tax/pilot_liability_pipeline\.yaml$",
            ("state_income_tax", None),
        ),
    ],
    "ks": [
        (r"^policies/dcf/keesm/", ("tanf", None)),
        (
            r"^policies/income_tax/"
            r"2026_k40es_schedule_before_credits\.yaml$",
            ("state_income_tax", None),
        ),
    ],
    "ky": [(r"^policies/income_tax/", ("state_income_tax", None))],
    "mi": [(r"^policies/mdhhs/", ("state_ssi_supplement", None))],
    "mn": [
        (r"^policies/dhs/combined-manual/0020", ("state_ssi_supplement", None)),
        (r"^policies/dhs/combined-manual/0022", ("tanf", None)),
        (
            r"^policies/income_tax/pilot_liability_pipeline\.yaml$",
            ("state_income_tax", None),
        ),
    ],
    "mt": [
        (
            r"^policies/income_tax/pilot_liability_pipeline\.yaml$",
            ("state_income_tax", None),
        ),
    ],
    "ms": [
        (
            r"^policies/income_tax/"
            r"2026_section_27_7_5_schedule\.yaml$",
            ("state_income_tax", None),
        ),
    ],
    "ga": [
        (r"^policies/cms/", ("medicaid_chip_bhp_thresholds", None)),
        (r"^policies/decal/caps/", ("childcare_assistance", None)),
        (
            r"^policies/income_tax/"
            r"2026_annual_tax_before_nonrefundable_credits\.yaml$",
            ("state_income_tax", None),
        ),
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
        (
            r"^policies/income_tax/pilot_liability_pipeline\.yaml$",
            ("state_income_tax", None),
        ),
        (r"^policies/tax/", ("state_income_tax", None)),
        (r"^statutes/NYC", ("nyc_income_tax", "NYC")),
    ],
    "oh": [
        (
            r"^policies/income_tax/pilot_liability_pipeline\.yaml$",
            ("state_income_tax", None),
        ),
    ],
    "pa": [
        (
            r"^policies/income_tax/pilot_liability_pipeline\.yaml$",
            ("state_income_tax", None),
        ),
    ],
    "or": [(r"^policies/odhs/", ("snap", None))],
    "sc": [
        (r"^(policies/dss/snap|regulations/114/)", ("snap", None)),
        (
            r"^policies/income_tax/pilot_liability_pipeline\.yaml$",
            ("state_income_tax", None),
        ),
    ],
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


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def rule_files(repo: Path, fetch: bool, ref: str = "origin/main") -> list[str]:
    if fetch:
        subprocess.run(
            ["git", "-C", str(repo), "fetch", "-q", "origin", "main"],
            capture_output=True,
            check=False,
        )
    try:
        listing = git(repo, "ls-tree", "-r", "--name-only", ref)
    except subprocess.CalledProcessError:
        return []
    out = []
    for line in listing.splitlines():
        if not line.endswith(".yaml") or line.endswith(".test.yaml"):
            continue
        if SKIP_DIRS.search(line):
            continue
        out.append(line)
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
    parser.add_argument("--no-fetch", action="store_true")
    parser.add_argument(
        "--rulespec",
        type=Path,
        default=Path.home() / "rulespec-us",
        help="Path to the rulespec-us checkout (default: ~/rulespec-us).",
    )
    parser.add_argument(
        "--ref",
        default="origin/main",
        help="rulespec-us git ref to classify (default: origin/main).",
    )
    parser.add_argument(
        "--skip-canada",
        action="store_true",
        help="Preserve existing rulespec-ca generated entries.",
    )
    args = parser.parse_args()

    buckets: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"count": 0, "areas": set(), "trees": set()}
    )
    unclassified: dict[str, int] = defaultdict(int)

    # Upstream rulespec-us is a monorepo: us/ holds federal law, us-xx/ holds
    # each state's tree. The standalone rulespec-us-xx checkouts under ~ are
    # historical worktrees of the same content — reading only the monorepo
    # avoids double counting.
    repo = args.rulespec
    for path in rule_files(repo, fetch=not args.no_fetch, ref=args.ref):
        hit = classify(path)
        if hit is None:
            unclassified["/".join(path.split("/")[:3])] += 1
            continue
        family, jurisdiction = hit
        bucket = buckets[(family, jurisdiction)]
        bucket["count"] += 1
        bucket["areas"].add("/".join(path.split("/")[1:4]))
        bucket["trees"].add(f"rulespec-us {args.ref}")

    if not args.skip_canada:
        canada_repo = Path.home() / "rulespec-ca"
        for path in rule_files(canada_repo, fetch=not args.no_fetch):
            hit = classify_canada(path)
            if hit is None:
                unclassified[f"rulespec-ca:{'/'.join(path.split('/')[:3])}"] += 1
                continue
            family, jurisdiction = hit
            bucket = buckets[(family, jurisdiction)]
            bucket["count"] += 1
            bucket["areas"].add("/".join(path.split("/")[:3]))
            bucket["trees"].add("rulespec-ca origin/main")

    data = json.loads(COVERAGE_PATH.read_text())
    programs = data["axiom"]["programs"]
    manual_keys = {
        (p.get("program"), p.get("jurisdiction"))
        for p in programs
        if not p.get("generated")
    }
    programs[:] = [
        p
        for p in programs
        if not p.get("generated")
        or (
            args.skip_canada
            and str(p.get("source") or "").startswith("rulespec-ca ")
        )
    ]

    for (family, jurisdiction), bucket in sorted(buckets.items()):
        if (family, jurisdiction) in manual_keys:
            continue
        areas = ", ".join(sorted(bucket["areas"]))
        if len(areas) > 160:
            areas = areas[:157] + "…"
        trees = ", ".join(sorted(bucket["trees"]))
        programs.append(
            {
                "program": family,
                "jurisdiction": jurisdiction,
                "status": "coverageOnly",
                "generated": True,
                "source": f"{trees}: {areas} ({bucket['count']} rule files)",
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
