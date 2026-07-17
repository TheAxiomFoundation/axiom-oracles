#!/usr/bin/env python3
"""Reproduce the committed PolicyEngine-UK reference for the uk-ctr suite.

The reference (``axiom_oracles/adapters/entitledto/fixtures/
uk_ctr_policyengine_reference.json``) holds real PolicyEngine-UK 2.89.2 CTR / UC /
Pension Credit values for each suite case, plus the national CTR scheme
parameters. This script regenerates it *from the suite cases* (the same
`uk_ctr_cases()` the fixtures use), so the reference cannot silently drift from
the households it claims to describe.

Requires ``policyengine-uk`` (installed separately — heavy, PE-env only), so CI
skips it; ``tests/test_entitledto_report.py`` runs it only when PE is importable.
Pin the engine to the committed reference's version — an unpinned install floats
to the latest release and ``--check`` will refuse the version mismatch:

    uv run --with policyengine-uk==2.89.2 python scripts/generate_uk_ctr_pe_reference.py
    uv run --with policyengine-uk==2.89.2 python scripts/generate_uk_ctr_pe_reference.py --check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.adapters.entitledto.report import DEFAULT_PE_REFERENCE  # noqa: E402
from axiom_oracles.core.case import Concepts  # noqa: E402
from axiom_oracles.suites.uk_ctr import PERIOD, uk_ctr_cases  # noqa: E402

YEAR = int(PERIOD)

# Council name -> PolicyEngine LocalAuthority enum member and region. PE-specific,
# so it lives here rather than in the oracle-neutral suite metadata.
_LA_ENUM = {
    "Birmingham": "BIRMINGHAM",
    "Cornwall": "CORNWALL",
    "Glasgow City": "GLASGOW_CITY",
    "Cardiff": "CARDIFF",
    "Kingston upon Thames": "KINGSTON_UPON_THAMES",
    "Manchester": "MANCHESTER",
}
_REGION = {
    "Birmingham": "WEST_MIDLANDS",
    "Cornwall": "SOUTH_WEST",
    "Glasgow City": "SCOTLAND",
    "Cardiff": "WALES",
    "Kingston upon Thames": "LONDON",
    "Manchester": "NORTH_WEST",
}
_TENURE = {
    "private_rent": "RENT_PRIVATELY",
    "social_rent": "RENT_FROM_COUNCIL",
    "owner": "OWNED_OUTRIGHT",
}


def _situation_from_case(case) -> dict:
    meta = case.metadata
    people: dict[str, dict] = {}
    members: list[str] = []
    for entity in case.entities_of_kind("person"):
        pid = entity.entity_id
        members.append(pid)
        person = {"age": {YEAR: int(entity.fact(Concepts.PERSON_AGE))}}
        relation = str(entity.fact(Concepts.HOUSEHOLD_RELATION, ""))
        if relation == "HeadOfHousehold":
            if meta.get("claimant_employment_income"):
                person["employment_income"] = {YEAR: meta["claimant_employment_income"]}
            if meta.get("claimant_state_pension"):
                person["state_pension"] = {YEAR: meta["claimant_state_pension"]}
        elif relation == "Spouse":
            if meta.get("partner_employment_income"):
                person["employment_income"] = {YEAR: meta["partner_employment_income"]}
            if meta.get("partner_state_pension"):
                person["state_pension"] = {YEAR: meta["partner_state_pension"]}
        people[pid] = person

    council = meta["local_authority_name"]
    household = {
        "members": members,
        "country": {YEAR: meta["country"].upper()},
        "local_authority": {YEAR: _LA_ENUM[council]},
        "region": {YEAR: _REGION[council]},
        "council_tax": {YEAR: meta["annual_council_tax_liability"]},
        "savings": {YEAR: meta["capital"]},
    }
    if meta.get("tenure") in _TENURE and meta["tenure"] != "owner":
        household["tenure_type"] = {YEAR: _TENURE[meta["tenure"]]}
        household["rent"] = {YEAR: meta["monthly_rent"] * 12.0}
    return {
        "people": people,
        "benunits": {"bu": {"members": members, "claims_all_entitled_benefits": {YEAR: True}}},
        "households": {"h": household},
    }


def build_reference() -> dict:
    from policyengine_uk import Simulation

    cases = {}
    for case in uk_ctr_cases():
        sim = Simulation(situation=_situation_from_case(case))

        def hh(var: str) -> float:
            return float(sim.calculate(var, YEAR).sum())

        cases[str(case.case_id)] = {
            "council_tax": round(hh("council_tax"), 2),
            "council_tax_reduction": round(hh("council_tax_reduction"), 2),
            "scheme_supported": bool(hh("council_tax_reduction_scheme_supported")),
            "universal_credit": round(hh("universal_credit"), 2),
            "housing_benefit": round(hh("housing_benefit"), 2),
            "pension_credit": round(hh("pension_credit"), 2),
            "applicable_amount": round(hh("council_tax_reduction_applicable_amount"), 2),
            "applicable_income": round(hh("council_tax_reduction_applicable_income"), 2),
        }

    p = Simulation(situation=_situation_from_case(uk_ctr_cases()[0])).tax_benefit_system.parameters(
        f"{YEAR}-01-01"
    ).gov.local_authorities

    def g(node, *path):
        for step in path:
            node = getattr(node, step)
        return float(node)

    params = {
        "england_pensioner": {
            "maximum_support_rate": g(p, "england", "council_tax_reduction", "pensioners", "maximum_support_rate"),
            "withdrawal_rate": g(p, "england", "council_tax_reduction", "pensioners", "means_test", "withdrawal_rate"),
            "capital_limit": g(p, "england", "council_tax_reduction", "pensioners", "means_test", "capital_limit"),
        },
    }
    for cc in ("scotland", "wales"):
        params[cc] = {
            "maximum_support_rate": g(p, cc, "council_tax_reduction", "maximum_support_rate"),
            "withdrawal_rate": g(p, cc, "council_tax_reduction", "means_test", "withdrawal_rate"),
            "capital_limit": g(p, cc, "council_tax_reduction", "means_test", "capital_limit"),
        }
    k = p.kingston_upon_thames.council_tax_reduction
    params["kingston_upon_thames"] = {
        "withdrawal_rate": float(k.means_test.withdrawal_rate),
        "capital_limit": float(k.means_test.capital_limit),
        "tariff_income_threshold": float(k.means_test.tariff_income_threshold),
        "tariff_income_step": float(k.means_test.tariff_income_step),
    }

    import importlib.metadata as m

    return {
        "provenance": {
            "engine": "policyengine-uk",
            "version": m.version("policyengine-uk"),
            "period": str(YEAR),
            "method": (
                "Constructed single-household situations derived from uk_ctr_cases() "
                "(no survey data). claims_all_entitled_benefits forced True so "
                "would_claim=1. council_tax supplied as input; savings = capital. "
                "Unsupported councils return council_tax_benefit_reported (0 on a "
                "constructed household)."
            ),
            "generator": "scripts/generate_uk_ctr_pe_reference.py",
            "ctr_national_scheme_parameters": params,
        },
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_PE_REFERENCE)
    args = parser.parse_args()

    reference = build_reference()
    rendered = json.dumps(reference, indent=2) + "\n"
    if args.check:
        committed = json.loads(args.output.read_text())
        fresh = json.loads(rendered)
        # A check against a different engine release proves nothing about the
        # committed reference — same values under another version is a silent
        # provenance lie, different values is a confusing red herring.
        committed_version = committed["provenance"]["version"]
        fresh_version = fresh["provenance"]["version"]
        if committed_version != fresh_version:
            sys.stderr.write(
                f"policyengine-uk {fresh_version} installed but the committed "
                f"reference was generated with {committed_version}; install the "
                f"pinned version (uv run --with policyengine-uk=="
                f"{committed_version} …) or regenerate the reference.\n"
            )
            return 1
        if committed["cases"] != fresh["cases"]:
            sys.stderr.write("PE reference case values differ from a fresh run.\n")
            return 1
        committed_params = committed["provenance"]["ctr_national_scheme_parameters"]
        fresh_params = fresh["provenance"]["ctr_national_scheme_parameters"]
        if committed_params != fresh_params:
            sys.stderr.write(
                "PE reference CTR scheme parameters differ from a fresh run.\n"
            )
            return 1
        print(
            "PE reference matches a fresh PolicyEngine-UK "
            f"{fresh_version} run (cases + scheme parameters)."
        )
        return 0
    args.output.write_text(rendered)
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
