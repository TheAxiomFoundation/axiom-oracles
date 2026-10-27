#!/usr/bin/env python
"""Canada federal schedule tax — Axiom (rulespec-ca) vs Statistics Canada SPSD/M.

Compares the encoded 2025 T1 Step-5 Part A schedule
(``ca:policies/cra/t1-2025/federal-tax-on-taxable-income``) against SPSM's
``imfedtax`` (federal tax before tax credits) for every taxfiler in an SPSM
case-output extract, driving both engines from SPSM's own ``imitax``
(taxable income, line 26000) so the comparison isolates the schedule.

Licence discipline (SPSD/M Licence Agreement v34):
- The extract (.prn) is Database-derived: it is read locally and NEVER
  committed. Only aggregate results (counts, match rates, mismatch-class
  magnitudes) are written to the dashboard report, which carries the s.4.1
  attribution notice.
- The run is reproducible by any SPSD/M licensee: the batch dialogue and
  variable list are committed, and the report records the database file
  fingerprints so a licensee can verify identical inputs before rerunning.

Usage:
    uv run python scripts/generate_ca_federal_tax_spsm.py \
        [--extract ~/.wine/drive_c/spsm-work/f25.prn] [--run-spsm]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.adapters.spsm import (  # noqa: E402
    SpsmRunner,
    parse_case_output,
)
from axiom_oracles.adapters.spsm.runner import (  # noqa: E402
    attribution_provenance,
)

RULESPEC_CA = Path.home() / "rulespec-ca"
MODULE_REL = "policies/cra/t1-2025/federal-tax-on-taxable-income"
MODULE_REF = f"ca:{MODULE_REL}"
INPUT_REF = f"{MODULE_REF}#input.taxable_income_line_26000"
OUTPUT_REF = f"{MODULE_REF}#federal_2025_t1_tax_on_taxable_income_line_76"
ENGINE_BINARY = (
    Path.home() / "axiom-rules-engine" / "target" / "release" / "axiom-rules-engine"
)
WORK = Path.home() / ".wine" / "drive_c" / "spsm-work"
CPI_NAME = "axiom_fedtax.cpi"
# SPSM rounds/keeps whole dollars in case output; the schedule multiplies a
# marginal rate into a whole-dollar taxable income, so a $2 band separates
# printing precision from genuine schedule disagreement.
TOLERANCE = 2.0

CPI_BODY = """####
## axiom_fedtax.cpi - lean case output for the axiom-oracles Canada
## federal schedule-tax lane (committed in scripts/, licence-safe: it is
## a variable NAME list, not Package content).
####
ASCFLAG       1
ASCUNIT       0
ASCSTYLE      1
ASCVARS       -
\thdseqhh
\thdprov
\tidage
\timicnet
\timdedfn
\timitax
\timfedtax
\timtaxcr
\timbft
\timamtdf
\tidipens
\timipnst
\t-
"""

DIALOGUE_CONTROL = "$spsd/ba25"
DIALOGUE_SAMPLE = None  # None = full database


def _dispositioned_block(
    *,
    counts: dict[str, int],
    comparison_count: int,
    match_count: int,
    unexplained_count: int,
) -> dict:
    """A ``summary.dispositioned`` block under the canonical semantics.

    ``explained_rate`` counts every classified row — the same
    ``CLASSIFIED_DISPOSITION_KINDS`` formula ``apply_dispositions`` uses —
    so a future encoding-gap classification here cannot silently diverge
    from the merge pipeline's definition of "explained".
    """
    from axiom_oracles.comparison.dispositions import (
        CLASSIFIED_DISPOSITION_KINDS,
        DISPOSITIONS_SCHEMA_VERSION,
    )

    classified = sum(
        counts.get(kind, 0) for kind in CLASSIFIED_DISPOSITION_KINDS
    )
    n = comparison_count
    return {
        "schema_version": DISPOSITIONS_SCHEMA_VERSION,
        "dispositions_file": None,
        "counts": counts,
        "unexplained_count": unexplained_count,
        "raw_match_rate": round(100.0 * match_count / n, 2) if n else 0,
        "explained_rate": (
            round(100.0 * (match_count + classified) / n, 2) if n else 0
        ),
        "expired_entries": [],
        "orphaned_entries": [],
    }


def run_spsm(output_name: str) -> Path:
    runner = SpsmRunner()
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / CPI_NAME).write_text(CPI_BODY)
    dialogue = runner.batch_dialogue(
        control_file=DIALOGUE_CONTROL,
        output_name=output_name,
        sample=DIALOGUE_SAMPLE,
        includes=(f"C:\\spsm-work\\{CPI_NAME}",),
    )
    process = runner.run_batch(dialogue, cwd=WORK)
    prn = WORK / f"{output_name}.prn"
    if not prn.exists():
        raise SystemExit(
            f"SPSM run produced no {prn}; tail of output:\n"
            + (process.stdout or "")[-2000:]
        )
    return prn


_TH = [0, 57375, 114750, 177882, 253414]
_RATE = [0.145, 0.205, 0.26, 0.29, 0.33]
_BASE = [0, 8319.38, 20081.25, 36495.57, 58399.85]


def _inverse_schedule(tax: float) -> float:
    """Taxable income that produces this 2025 schedule tax."""

    for bracket in range(4, -1, -1):
        if tax >= _BASE[bracket] - 0.01:
            return _TH[bracket] + (tax - _BASE[bracket]) / _RATE[bracket]
    return 0.0


def axiom_schedule_tax(
    taxable_incomes: list[float], chunk_size: int = 20_000
) -> list[float]:
    """Evaluate the encoded schedule for every taxable income, batched."""

    if len(taxable_incomes) > chunk_size:
        out: list[float] = []
        for start in range(0, len(taxable_incomes), chunk_size):
            out.extend(
                axiom_schedule_tax(
                    taxable_incomes[start : start + chunk_size]
                )
            )
        return out

    artifact = WORK / "ca-fedtax-compiled.json"
    if not artifact.exists():
        compile_proc = subprocess.run(
            [
                str(ENGINE_BINARY),
                "compile",
                "--program",
                str(RULESPEC_CA / f"{MODULE_REL}.yaml"),
                "--output",
                str(artifact),
            ],
            env={
                "AXIOM_RULESPEC_REPO_ROOTS": str(Path.home()),
                "PATH": "/usr/bin:/bin",
            },
            capture_output=True,
            text=True,
        )
        if compile_proc.returncode != 0:
            raise SystemExit(f"compile failed: {compile_proc.stderr[-800:]}")

    interval = {
        "period_kind": "tax_year",
        "start": "2025-01-01",
        "end": "2025-12-31",
        "name": "2025",
    }
    inputs = []
    queries = []
    for index, amount in enumerate(taxable_incomes):
        entity = f"p{index}"
        inputs.append(
            {
                "name": INPUT_REF,
                "entity": "Person",
                "entity_id": entity,
                "value": {"kind": "decimal", "value": f"{amount:.2f}"},
                "interval": interval,
            }
        )
        queries.append(
            {
                "entity_id": entity,
                "period": interval,
                "outputs": [OUTPUT_REF],
            }
        )
    request = {
        "mode": "fast",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }
    process = subprocess.run(
        [str(ENGINE_BINARY), "run-compiled", "--artifact", str(artifact)],
        input=json.dumps(request),
        capture_output=True,
        text=True,
    )
    if process.returncode != 0:
        raise SystemExit(f"engine run failed: {process.stderr[-800:]}")
    payload = json.loads(process.stdout)
    by_entity: dict[str, float] = {}
    for result in payload.get("results", []):
        entity = str(result.get("entity_id"))
        outputs = result.get("outputs") or {}
        output = outputs.get(OUTPUT_REF)
        if isinstance(output, dict):
            value = output.get("value")
            if isinstance(value, dict):
                value = value.get("value")
            if value is not None:
                by_entity[entity] = float(value)
    return [by_entity.get(f"p{i}", 0.0) for i in range(len(taxable_incomes))]


def database_fingerprints() -> list[dict]:
    runner = SpsmRunner()
    root = runner.require_install()
    rows = []
    for name in ("ba25.cpr", "ba25.mpr"):
        path = root / "spsd" / name
        if path.exists():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            rows.append({"file": name, "sha256": digest, "bytes": path.stat().st_size})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extract", type=Path, default=None)
    parser.add_argument("--run-spsm", action="store_true")
    parser.add_argument("--output-name", default="fed25")
    args = parser.parse_args()

    if args.run_spsm or args.extract is None:
        prn = run_spsm(args.output_name)
    else:
        prn = args.extract.expanduser()

    households = parse_case_output(prn)
    rows: list[tuple[int, int, float, float, float, float]] = []
    for household in households:
        taxable = household.values.get("imitax", [])
        fedtax = household.values.get("imfedtax", [])
        amtdf = household.values.get("imamtdf", [])
        pension = household.total("idipens")
        for member in range(len(fedtax)):
            ti = taxable[member] if member < len(taxable) else 0.0
            amt = amtdf[member] if member < len(amtdf) else 0.0
            rows.append(
                (household.sequence, member, ti, fedtax[member], amt, pension)
            )

    axiom_values = axiom_schedule_tax([row[2] for row in rows])

    matches = 0
    amt_class = 0
    split_class = 0
    other: list[dict] = []
    for (seq, member, ti, spsm_value, amt_flag, pension_received), axiom_value in zip(
        rows, axiom_values, strict=True
    ):
        diff = axiom_value - spsm_value
        if abs(diff) <= TOLERANCE:
            matches += 1
        elif amt_flag > 0:
            # Whenever the T691 minimum-tax path runs, SPSM REPLACES
            # imfedtax with netminamt — the minimum amount net of AMT
            # credits (glass-box Atxcalc.cpp: "The federal tax is set to
            # the net minimum amount", T691 row 94) — so for AMT filers
            # the printed variable is no longer the schedule output in
            # either direction. imamtdf ("difference due to minimum
            # tax") > 0 identifies exactly those filers.
            amt_class += 1
        elif (
            axiom_value - spsm_value > TOLERANCE
            and pension_received > 0
            and 0
            < (ti - _inverse_schedule(spsm_value))
            <= min(pension_received, ti * 0.5) + 1
        ):
            # SPSM's family block splits eligible pension income between
            # spouses and recomputes imfedtax on the POST-SPLIT taxable
            # while imitax prints the pre-split figure (glass-box
            # Atxcalc.cpp lines 1267-1304) — the same
            # variable-semantics family as the AMT overwrite. Verified
            # per-row: the implied income shift is positive, bounded by
            # both the household's actual eligible pension income and
            # the 50 percent legal cap.
            split_class += 1
        else:
            other.append(
                {
                    "kind": "axiom_above_spsm"
                    if diff > 0
                    else "spsm_above_axiom",
                    "difference": round(diff, 2),
                }
            )

    n = len(rows)
    report = {
        "schema_version": "axiom.comparison_report.v2",
        "suite": "ca-federal-schedule-tax-spsm",
        "population": "spsd-synthetic-2022",
        "engines": {"left": "axiom", "right": "spsm"},
        "locales": ["CA"],
        "scope": {"type": "country", "geoid": "CA"},
        "concepts": [
            {
                "concept": OUTPUT_REF,
                "description": (
                    "Federal tax on taxable income (2025 T1 Step 5 Part A) "
                    "vs SPSM imfedtax, both driven from SPSM taxable income"
                ),
            }
        ],
        # Standard aggregates row: the dashboard's oracle cards and program
        # pages compute totals/rates from report.aggregates, and the
        # front-page filter drops reports without it.
        "aggregates": [
            {
                "concept": OUTPUT_REF,
                "description": (
                    "Federal tax on taxable income (2025 T1 Step 5 "
                    "Part A) vs SPSM federal tax before credits"
                ),
                "category": "tax",
                "comparison": "amount",
                "comparison_count": n,
                "match_count": matches,
                "mismatch_count": n - matches,
                "components": [],
            }
        ],
        "case_count": len(households),
        "summary": {
            "comparison_count": n,
            "match_count": matches,
            "mismatch_count": n - matches,
            "amt_overwrite_class_count": amt_class,
            "pension_splitting_class_count": split_class,
            "unclassified_count": len(other),
            "match_rate": round(100.0 * matches / n, 2) if n else 0,
            # Standard disposition accounting: the AMT-overwrite class is
            # verified per-row (imamtdf > 0; glass-box Atxcalc.cpp T691
            # row 94 replaces imfedtax with netminamt) and attributed to
            # the oracle's variable semantics — an upstream engine
            # behavior, not a rules disagreement.
            "dispositioned": _dispositioned_block(
                counts={
                    "axiom_encoding_gap": 0,
                    "bridge_artifact": 0,
                    "explained_residual": 0,
                    "unexplained": 0,
                    "upstream_engine_gap": amt_class + split_class,
                },
                comparison_count=n,
                match_count=matches,
                unexplained_count=len(other),
            ),
        },
        "mismatches": other[:50],
        "provenance": {
            "generated": date.today().isoformat(),
            "generated_at": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "generator": "scripts/generate_ca_federal_tax_spsm.py",
            "oracle_run": {
                "dialogue_control_file": DIALOGUE_CONTROL,
                "sample": DIALOGUE_SAMPLE or "full-database",
                "case_output_include": CPI_NAME,
                "input_fingerprints": database_fingerprints(),
            },
            **attribution_provenance(),
            "privacy": (
                "Aggregate results only: per-household extract rows are "
                "Database-derived (SPSD/M Licence s.3.1) and never leave "
                "the local reports/ directory."
            ),
        },
    }
    out = REPO_ROOT / "dashboard" / "public" / "data" / (
        "axiom-spsm-ca-federal-schedule-tax.json"
    )
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        f"{n} taxfilers: {matches} match ({report['summary']['match_rate']}%), "
        f"{amt_class} AMT-class, {split_class} splitting-class, "
        f"{len(other)} unclassified"
    )
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
