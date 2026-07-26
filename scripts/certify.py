#!/usr/bin/env python3
"""Program certificate: one generated answer per certification question.

Today a certification question answered by reading harness code produced
confidently wrong answers in both directions about the same suite. The
certificate is the structural fix: for each (jurisdiction, program), one
committed document carrying the verdicts, where every field names the artifact
and sha it derives from, and ``--check`` recomputes the whole thing. If a
question about a program's validation posture is not answerable from its
certificate, that is a certificate defect to file — not a prompt to go read
adapters.

Two evidence modes, stated per claim:

* ``computed`` — this script re-derives the value from committed in-repo
  artifacts; drift fails ``--check``.
* ``attested`` — the value is carried from a sha-pinned external receipt
  (today: the ops closure prototype and the engine-execution receipts).
  Attested is scaffolding, not certification; the roadmap is monotone
  conversion of attested claims to computed ones.

Oracle types matter to the verdict. ``reference`` oracles (another
implementation) can be wrong in code, so their unexplained mismatches block
the conformant verdict. ``reality`` oracles (recorded administrative outcomes)
cannot have bugs filed against them; their disagreements are reported as
leads and do not block, but are never hidden.

Modes::

    uv run python scripts/certify.py            # write certificates + summary
    uv run python scripts/certify.py --check    # CI: fail on drift
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "dashboard" / "public" / "data"
CENSUS_PATH = REPO_ROOT / "conformance" / "exercise-census.json"
OUT_DIR = REPO_ROOT / "certificates"

SCHEMA = "axiom_oracles.program_certificate.v1"

#: Program registry. One entry per certified (jurisdiction, program).
#: ``suites`` lists every comparison that bears on the program, typed.
#: ``attested`` carries sha-pinned claims from outside this repo, verbatim,
#: with their provenance; nothing here is recomputable in-repo yet.
PROGRAMS: dict[str, dict] = {
    "us-co/snap": {
        "period": "2026-01",
        "suites": [
            {
                "suite": "co-snap-ecps",
                "oracle_type": "reference",
                "oracle": "policyengine-us 1.705.1 over the populace population",
                "report": "dashboard/public/data/axiom-policyengine-co-snap-ecps.json",
            },
            {
                "suite": "co-snap-qc",
                "oracle_type": "reality",
                "oracle": "USDA SNAP QC FY2024 administrative sample "
                "(rulespec overlay, per-patch citations in report provenance)",
                "report": "dashboard/public/data/axiom-snapqc-co-snap.json",
            },
        ],
        "attested": {
            "closed": {
                "value": {
                    "state_root": "10 CCR 2506-1: 281/289 sections encoded, "
                    "0 untested modules, 6 container headings, 2 pending review",
                    "federal_reg_root": "7 CFR 273 fully ingested "
                    "(2026-07-15-title-7-part-273, 39 provisions); "
                    "11/30 sections carry any encoding",
                    "federal_statute_root": "7 USC ch. 51 ingested (827); "
                    "21 modules encoded, remainder unclassified",
                    "frontier": "72 boundary input facts, 0 cross-program imports",
                },
                "source": "TheAxiomFoundation/ops closure/co-snap-closure-2026-07-26.md",
                "source_commits": ["ee4bcfe6aa9b", "968e9e2805e2"],
                "status": "prototype",
            },
            "executable": {
                "value": {
                    "tuple": "engine v0.1.1 x program-artifacts-59a10dab866e",
                    "loads_and_runs": True,
                    "golden_values_reproduce": False,
                    "detail": "rc=0, snap_monthly_allotment=478; committed "
                    "fixture predates the input-naming cutover: SSN inputs "
                    "default false, eligibility evaluates not_holds, the "
                    "correctly-gated output returns 0, net income 226 vs "
                    "certified 226.50 — fixture regeneration pending; the "
                    "gated binding is the intended contract",
                },
                "source": "TheAxiomFoundation/ops launch-readiness/receipts/"
                "engine-v0.1.1-receipt-2026-07-26.md",
                "source_commit": "81ccb7b",
                "status": "fail_open_item",
            },
        },
    },
}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _suite_verdict(entry: dict) -> tuple[dict, list[dict], list[str]]:
    """Compute one suite's conformance leg from its committed report.

    Hardened per the 2026-07-26 cross-family audit: a report only counts as a
    comparison when it identifies itself as this suite, performed a nonzero
    number of comparisons without engine errors, and its counts conserve.
    A zero-work or mislabeled report is a defect, never a clean leg.
    """
    defects: list[str] = []
    report_path = REPO_ROOT / entry["report"]
    report = _load(report_path)
    summary = report.get("summary") or {}

    # Report identity: the artifact must claim the suite it is cited for.
    reported_suite = report.get("suite")
    accepted = {entry["suite"], *entry.get("aliases", [])}
    if reported_suite not in accepted:
        defects.append(
            f"{entry['suite']}: report {entry['report']} identifies as "
            f"{reported_suite!r}, not this suite"
        )

    comparisons = int(summary.get("comparison_count") or 0)
    matches = int(summary.get("match_count") or 0)
    mismatch_count = int(summary.get("mismatch_count") or 0)
    error_count = int(
        summary.get("error_count") or summary.get("error_case_count") or 0
    )
    if comparisons <= 0:
        defects.append(
            f"{entry['suite']}: zero comparisons — a report that did no work "
            "cannot evidence anything"
        )
    if matches + mismatch_count != comparisons:
        defects.append(
            f"{entry['suite']}: counts do not conserve "
            f"({matches} + {mismatch_count} != {comparisons})"
        )
    if error_count:
        defects.append(
            f"{entry['suite']}: {error_count} engine error(s) recorded — "
            "errored cases are not comparisons"
        )

    # Weighted evidence must not contradict the raw counts (a zero raw
    # mismatch count with nonzero weighted mismatch mass is hidden failure).
    weighted = summary.get("weighted") or {}
    weighted_mismatch = float(weighted.get("mismatch_weight") or 0)
    if mismatch_count == 0 and weighted_mismatch > 0:
        defects.append(
            f"{entry['suite']}: raw mismatch count is 0 but weighted mismatch "
            f"mass is {weighted_mismatch} — weighted failures hidden"
        )

    # Disposition accounting. Three explicit modes:
    #   file   — a dispositions file is named; it must exist, be hashed, and
    #            its counts must conserve against the mismatch count.
    #   none   — no machinery; every mismatch is unexplained by definition.
    #   inline — classifications exist with no file (generator-classified);
    #            unvalidated, so the leg is defective until migrated.
    dispositioned = summary.get("dispositioned") or {}
    counts = dispositioned.get("counts") or {}
    evidence: list[dict] = [
        {
            "claim": f"suite:{entry['suite']}",
            "mode": "computed",
            "artifact": entry["report"],
            "sha256": sha256_of(report_path),
        }
    ]
    disposition_file = dispositioned.get("dispositions_file")
    classified = sum(int(v or 0) for v in counts.values())
    if disposition_file:
        dispositions_path = REPO_ROOT / disposition_file
        if not dispositions_path.exists():
            defects.append(
                f"{entry['suite']}: dispositions_file {disposition_file!r} "
                "does not exist in the repository"
            )
            unexplained = mismatch_count
        else:
            evidence.append(
                {
                    "claim": f"dispositions:{entry['suite']}",
                    "mode": "computed",
                    "artifact": disposition_file,
                    "sha256": sha256_of(dispositions_path),
                }
            )
            unexplained = int(dispositioned.get("unexplained_count") or 0)
            if classified != mismatch_count:
                defects.append(
                    f"{entry['suite']}: disposition counts ({classified}) do "
                    f"not conserve against mismatches ({mismatch_count})"
                )
    elif classified and classified != int(
        dispositioned.get("unexplained_count") or 0
    ):
        defects.append(
            f"{entry['suite']}: inline classifications present with no "
            "dispositions file — unvalidated; migrate before they can explain"
        )
        unexplained = mismatch_count
    else:
        unexplained = mismatch_count

    # Slim-report guard: when the summary claims mismatches the report body
    # does not carry and no per-case chunks exist, the aggregate cannot be
    # audited from committed evidence.
    stored = len(report.get("mismatches") or [])
    chunk_dir = REPO_ROOT / "dashboard" / "public" / "data" / "cases" / str(
        reported_suite or entry["suite"]
    )
    if mismatch_count > stored and not chunk_dir.is_dir():
        defects.append(
            f"{entry['suite']}: {mismatch_count} mismatches claimed, "
            f"{stored} stored, no per-case chunks — aggregate unauditable"
        )

    axiom_open = int(counts.get("axiom_encoding_gap") or 0)
    leg = {
        "suite": entry["suite"],
        "oracle_type": entry["oracle_type"],
        "oracle": entry["oracle"],
        "comparisons": comparisons,
        "matches": matches,
        "mismatches": mismatch_count,
        "weighted_mismatch_mass": weighted_mismatch or None,
        "unexplained": unexplained,
        "axiom_attributed_open": axiom_open,
        "report_defects": defects,
        "clean": not defects and unexplained == 0 and axiom_open == 0,
    }
    return leg, evidence, defects


def _exercise_block(suites: list[dict], census: dict) -> tuple[dict, bool]:
    rows = {}
    complete = True
    for entry in suites:
        row = (census.get("suites") or {}).get(entry["suite"])
        if row is None:
            rows[entry["suite"]] = {"status": "no census row"}
            complete = False
            continue
        has_evidence = bool(row.get("evidence_fields"))
        if not has_evidence:
            complete = False
        rows[entry["suite"]] = {
            "cases": row.get("cases_scanned"),
            "varied_fields": row.get("varied_fields"),
            "constant_fields": row.get("constant_fields"),
            "bridged_through": sorted((row.get("bridged_through") or {}).keys()),
            "bridge_audited": bool(row.get("bridge_audited")),
            "per_case_evidence_committed": has_evidence,
        }
        if not row.get("bridge_audited"):
            complete = False
    return rows, complete


def build_certificate(program: str, spec: dict) -> dict:
    census = _load(CENSUS_PATH)
    legs = []
    evidence = [
        {
            "claim": "exercise census",
            "mode": "computed",
            "artifact": str(CENSUS_PATH.relative_to(REPO_ROOT)),
            "sha256": sha256_of(CENSUS_PATH),
        }
    ]
    all_defects: list[str] = []
    for entry in spec["suites"]:
        leg, evs, defects = _suite_verdict(entry)
        legs.append(leg)
        evidence.extend(evs)
        all_defects.extend(defects)

    reference_legs = [leg for leg in legs if leg["oracle_type"] == "reference"]
    reality_legs = [leg for leg in legs if leg["oracle_type"] == "reality"]
    conformant = bool(reference_legs) and all(leg["clean"] for leg in reference_legs)
    reality_leads = sum(leg["mismatches"] for leg in reality_legs)

    exercise_rows, exercise_complete = _exercise_block(spec["suites"], census)

    blockers = list(all_defects)
    for leg in reference_legs:
        if leg["unexplained"] or leg["axiom_attributed_open"]:
            blockers.append(
                f"{leg['suite']}: {leg['unexplained']} unexplained mismatch(es) "
                f"— disposition or fix before this leg counts"
            )
    if not exercise_complete:
        blockers.append(
            "exercise: census incomplete (missing per-case evidence or "
            "unaudited bridge) for at least one suite"
        )

    attested = spec.get("attested") or {}
    # The single public predicate (adopted from the 2026-07-26 design review):
    # "certified" is reserved for the conjunction of all four verdicts holding
    # in computed mode with no open defects. closed and executable are attested
    # today, so certified is necessarily false — by design, not oversight: a
    # certificate resting on attested premises is scaffolding, and saying so
    # is the point.
    certified = bool(
        conformant
        and exercise_complete
        and not blockers
        and attested.get("closed", {}).get("status") == "computed"
        and attested.get("executable", {}).get("status") == "computed"
    )
    return {
        "schema": SCHEMA,
        "program": program,
        "period": spec["period"],
        "certified": {
            "value": certified,
            "rule": "computed(conformant AND exercised AND closed AND "
            "executable) with zero open defects; attested premises never "
            "satisfy it",
        },
        "verdicts": {
            "conformant": {
                "value": conformant,
                "mode": "computed",
                "reference_legs": [leg for leg in legs if leg["oracle_type"] == "reference"],
                "reality_legs": [
                    {**leg, "note": "reality-oracle disagreements are leads, not defects"}
                    for leg in reality_legs
                ],
                "reality_leads": reality_leads,
            },
            "exercised": {
                "value": exercise_complete,
                "mode": "computed",
                "suites": exercise_rows,
            },
            "closed": {"mode": "attested", **attested.get("closed", {})},
            "executable": {"mode": "attested", **attested.get("executable", {})},
        },
        "blockers": blockers,
        "evidence": evidence,
        "_comment": (
            "Generated by scripts/certify.py — do not hand-edit. Every "
            "computed field re-derives from the named artifacts under "
            "--check; attested fields carry sha-pinned external receipts "
            "and are scaffolding, not certification. A certification "
            "question not answerable from this document is a certificate "
            "defect to file."
        ),
    }


def build_all() -> dict[str, dict]:
    return {
        program: build_certificate(program, spec) for program, spec in PROGRAMS.items()
    }


def _out_path(program: str) -> Path:
    return OUT_DIR / f"{program.replace('/', '-')}.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    certificates = build_all()
    if args.check:
        for program, certificate in certificates.items():
            path = _out_path(program)
            if not path.exists():
                print(f"missing {path.relative_to(REPO_ROOT)}", file=sys.stderr)
                return 1
            if json.loads(path.read_text()) != certificate:
                print(
                    f"certificate drifted for {program} — regenerate with "
                    "`uv run python scripts/certify.py`",
                    file=sys.stderr,
                )
                return 1
        print("certificates up to date")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for program, certificate in certificates.items():
        path = _out_path(program)
        path.write_text(json.dumps(certificate, indent=2, sort_keys=True) + "\n")
        verdicts = certificate["verdicts"]
        print(
            f"{program}: CERTIFIED={certificate['certified']['value']} | "
            f"conformant={verdicts['conformant']['value']} "
            f"exercised={verdicts['exercised']['value']} "
            f"closed={verdicts['closed'].get('status')} "
            f"executable={verdicts['executable'].get('status')}"
        )
        for blocker in certificate["blockers"]:
            print(f"  blocker: {blocker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
