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

Evidence modes are stated per claim:

* ``computed`` — this script re-derives the value from committed in-repo
  artifacts; drift fails ``--check``.
* ``attested`` — the value is carried from a sha-pinned external receipt
  (today: only the ops closure prototype). Attested is scaffolding, not
  certification; the roadmap is monotone conversion of attested claims to
  computed ones. Executability is computed from the governed CI receipt and
  fails closed when that receipt is missing or invalid.

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
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.executable_receipt import (  # noqa: E402
    validate_executable_receipt,
)

DATA_DIR = REPO_ROOT / "dashboard" / "public" / "data"
CENSUS_PATH = REPO_ROOT / "conformance" / "exercise-census.json"
OUT_DIR = REPO_ROOT / "certificates"

SCHEMA = "axiom_oracles.program_certificate.v1"

#: Program registry. One entry per certified (jurisdiction, program).
#: ``suites`` lists every comparison that bears on the program, typed.
#: ``attested`` carries the remaining external closure claim. ``executable``
#: pins the certificate-owned expectations independently re-checked against
#: the governed producer's committed receipt.
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
        },
        "executable": {
            "manifest": "certificates/executable/us-co-snap/manifest.json",
            "golden_input_sha256": (
                "8cbf093601f94a8f5a4517aeb27a4851439776d9d16933785c540839f4655dc3"
            ),
            "expected_outputs": {
                "snap_benefit_amount": 478,
                "snap_net_income": 226,
                "snap_eligible": "holds",
            },
        },
    },
}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _suite_verdict(entry: dict) -> tuple[dict, dict]:
    """Compute one suite's conformance leg from its committed report."""
    report_path = REPO_ROOT / entry["report"]
    report = _load(report_path)
    summary = report.get("summary") or {}
    dispositioned = summary.get("dispositioned") or {}
    counts = dispositioned.get("counts") or {}
    mismatch_count = int(summary.get("mismatch_count") or 0)
    # A mismatch with no disposition machinery applied is unexplained by
    # definition — absence of a dispositions file never counts as explained.
    unexplained = (
        int(dispositioned.get("unexplained_count") or 0)
        if dispositioned
        else mismatch_count
    )
    if dispositioned and dispositioned.get("dispositions_file") is None:
        unexplained = max(unexplained, mismatch_count)
    axiom_open = int(counts.get("axiom_encoding_gap") or 0)
    leg = {
        "suite": entry["suite"],
        "oracle_type": entry["oracle_type"],
        "oracle": entry["oracle"],
        "comparisons": summary.get("comparison_count"),
        "matches": summary.get("match_count"),
        "mismatches": mismatch_count,
        "unexplained": unexplained,
        "axiom_attributed_open": axiom_open,
        "clean": unexplained == 0 and axiom_open == 0,
    }
    evidence = {
        "claim": f"suite:{entry['suite']}",
        "mode": "computed",
        "artifact": entry["report"],
        "sha256": sha256_of(report_path),
    }
    return leg, evidence


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


def _executable_verdict(spec: dict) -> tuple[dict, dict | None]:
    """Compute executability from the producer receipt, never an attestation."""

    manifest_path = REPO_ROOT / spec["manifest"]
    validation = validate_executable_receipt(
        repo_root=REPO_ROOT,
        manifest_path=manifest_path,
        expected_outputs=spec["expected_outputs"],
    )
    failures = list(validation.failures)
    manifest_sha256 = sha256_of(manifest_path) if manifest_path.is_file() else None
    receipt_path = "certificates/executable/us-co-snap/receipt.json"
    try:
        manifest = _load(manifest_path)
        receipt_path = str(manifest.get("receipt_path") or receipt_path)
        manifest_input_sha = (manifest.get("golden") or {}).get("input_sha256")
        if manifest_input_sha != spec["golden_input_sha256"]:
            failures.append(
                "certificate golden input SHA-256 disagrees with the "
                "executable manifest"
            )
    except (OSError, json.JSONDecodeError, TypeError, AttributeError):
        # The validator already records the actionable malformed-manifest
        # failure. Keep certificate generation fail-closed and deterministic.
        pass

    holds = validation.valid and not failures
    verdict = {
        "value": holds,
        "mode": "computed",
        "receipt": receipt_path,
        "receipt_sha256": validation.receipt_sha256,
        "manifest": spec["manifest"],
        "manifest_sha256": manifest_sha256,
        "golden_input_sha256": spec["golden_input_sha256"],
        "expected_outputs": spec["expected_outputs"],
        "failures": failures,
    }
    if holds:
        verdict["evidence"] = validation.evidence

    evidence = None
    if validation.receipt_sha256:
        evidence = {
            "claim": "executable",
            "mode": "computed",
            "artifact": receipt_path,
            "sha256": validation.receipt_sha256,
            "accepted": holds,
        }
    return verdict, evidence


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
    for entry in spec["suites"]:
        leg, ev = _suite_verdict(entry)
        legs.append(leg)
        evidence.append(ev)

    reference_legs = [leg for leg in legs if leg["oracle_type"] == "reference"]
    reality_legs = [leg for leg in legs if leg["oracle_type"] == "reality"]
    conformant = bool(reference_legs) and all(leg["clean"] for leg in reference_legs)
    reality_leads = sum(leg["mismatches"] for leg in reality_legs)

    exercise_rows, exercise_complete = _exercise_block(spec["suites"], census)
    executable, executable_evidence = _executable_verdict(spec["executable"])
    if executable_evidence:
        evidence.append(executable_evidence)

    blockers = []
    for leg in reference_legs:
        if not leg["clean"]:
            blockers.append(
                f"{leg['suite']}: {leg['unexplained']} unexplained mismatch(es) "
                f"— disposition or fix before this leg counts"
            )
    if not exercise_complete:
        blockers.append(
            "exercise: census incomplete (missing per-case evidence or "
            "unaudited bridge) for at least one suite"
        )
    if not executable["value"]:
        detail = "; ".join(executable["failures"]) or "receipt did not validate"
        blockers.append(f"executable: {detail}")

    attested = spec.get("attested") or {}
    return {
        "schema": SCHEMA,
        "program": program,
        "period": spec["period"],
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
            "executable": executable,
        },
        "blockers": blockers,
        "evidence": evidence,
        "_comment": (
            "Generated by scripts/certify.py — do not hand-edit. Every "
            "computed field re-derives from the named artifacts under "
            "--check; the executable premise only holds for a receipt accepted "
            "against the pinned release and workflow manifests. Remaining "
            "attested fields are scaffolding, not certification. A certification "
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
            f"{program}: conformant={verdicts['conformant']['value']} "
            f"exercised={verdicts['exercised']['value']} "
            f"closed={verdicts['closed'].get('status')} "
            f"executable={verdicts['executable']['value']}"
        )
        for blocker in certificate["blockers"]:
            print(f"  blocker: {blocker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
