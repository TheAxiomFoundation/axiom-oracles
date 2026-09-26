#!/usr/bin/env python3
"""Reproduce the Alabama TY2025 eCPS lane from hash-verified saved outputs.

This ports the reviewed ``oracles-proto/assemble.py`` key-based assembly, not
Alabama tax law. The standard v2 report builder grades PE versus TAXSIM: its
denominator, missing-value handling and engine identities remain meaningful
while the two conditional Axiom federal feeds are pending. Axiom pairwise
reports are attached only for evaluated households, with coverage explicit.
The legacy state generator's special three-way shape assumes numeric Axiom
results for every case and cannot honestly represent this lane today.

Like that generator's _TOL['AL'], tolerance is $1 absolute, relative zero.
Unlike its _PE_VAR['AL'] pre-credit schedule surface, this TY2025 final-liability
lane compares al_income_tax/siitax, retaining staxbc separately. The $1–$15
band is diagnostic only. No fitted TAXSIM behavior is treated as law.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Also support direct execution without installing this checkout.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.comparison.comparator import Comparator  # noqa: E402
from axiom_oracles.comparison.mappings import ProgramMapping  # noqa: E402
from axiom_oracles.comparison.report import build_comparison_report  # noqa: E402
from axiom_oracles.core.case import Case, Concepts  # noqa: E402
from axiom_oracles.core.results import EngineResult  # noqa: E402
from axiom_oracles.provenance import rulespec_provenance  # noqa: E402
from axiom_oracles.suites.al_income_tax_2025_axiom import (  # noqa: E402
    FEDERAL_FIELDS,
    evaluate_axiom_legs,
)

REFERENCE_DIR = REPO_ROOT / "reference/al-income-tax-2025"
SUITE = "al-income-tax-2025-ecps"
CONCEPT = Concepts.STATE_INCOME_TAX
METRICS = {
    "agi": "v32",
    "exemptions": "v33",
    "standard_deduction": "v34",
    "itemized_deductions": "v35",
    "taxable_income": "v36",
    "tax_before_credits": "staxbc",
    "credits": "v40",
    "liability": "siitax",
}
OUTPUTS = [*METRICS, "deductions", "federal_tax_deduction"]
RAW = [
    *[f"v{i}" for i in range(32, 42)],
    "staxbc",
    "siitax",
    "fiitax",
    "niit",
    "v10",
    "v25",
    "actc",
    "srebate",
    "senergy",
    "sctc",
    "sptcr",
    "samt",
    "addmed",
]
PE_EXTRA = {
    "federal_tax_deduction": "al_federal_income_tax_deduction",
    "personal_exemption": "al_personal_exemption",
    "dependent_exemption": "al_dependent_exemption",
    "standard_deduction": "al_standard_deduction",
    "itemized_deductions": "al_itemized_deductions",
    "total_ti_deductions": "al_deductions",
}
REQUIRED_FILES = {
    "households.csv",
    "engine_outputs_state1.csv",
    "engine_outputs_state0.csv",
    "pe_intermediates.csv",
    "ground_truth_fixtures.yaml",
}
BANDS = ("within_1", "over_1_through_15", "over_15")
HOUSEHOLD_COLUMNS = (
    "year",
    "state",
    "mstat",
    "page",
    "sage",
    "depx",
    "pwages",
    "psemp",
    "swages",
    "ssemp",
    "dividends",
    "intrec",
    "stcg",
    "ltcg",
    "otherprop",
    "nonprop",
    "pensions",
    "gssi",
    "pui",
    "sui",
    "transfers",
    "rentpaid",
    "proptax",
    "otheritem",
    "childcare",
    "mortgage",
    "scorp",
    "idtl",
    *(f"age{i}" for i in range(1, 12)),
)


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_manifest(reference_dir: Path = REFERENCE_DIR) -> dict:
    manifest = json.loads((reference_dir / "manifest.json").read_text())
    require(REQUIRED_FILES <= manifest["files"].keys(), "Missing manifest inputs")
    for name, record in manifest["files"].items():
        path = reference_dir / name
        require(
            path.resolve().is_relative_to(reference_dir.resolve()),
            f"Invalid manifest path: {name}",
        )
        require(sha256(path) == record["sha256"], f"Manifest hash mismatch: {name}")
    return manifest


def _release(reference_dir: Path, state: int, households: pd.DataFrame) -> dict:
    data = pd.read_csv(reference_dir / f"engine_outputs_state{state}.csv")
    require(set(data.source) == {"policyengine", "taxsim"}, "Unexpected sources")
    require(
        bool((data.year.eq(2025) & data.state.eq(state)).all()), "Release year/state"
    )
    require(not data.duplicated(["source", "taxsimid"]).any(), "Duplicate release IDs")
    lanes = {}
    for source in ("policyengine", "taxsim"):
        lane = data[data.source.eq(source)].set_index("taxsimid").sort_index()
        require(
            lane.index.equals(households.index), f"{source}: missing/extra households"
        )
        for column in households.columns.difference(["state"]):
            require(column in lane, f"Missing source input {column}")
            require(
                bool(
                    np.isclose(
                        households[column],
                        lane[column],
                        atol=0.001,
                        rtol=1e-7,
                        equal_nan=True,
                    ).all()
                ),
                f"Source input mismatch {source}/{column}",
            )
        reported = [
            column
            for column in METRICS.values()
            if column != "v33" or source != "policyengine"
        ]
        require(
            bool(np.isfinite(lane[reported]).all().all()),
            f"Unavailable release components: {source}",
        )
        lanes[source] = lane
    return lanes


def assemble(reference_dir: Path = REFERENCE_DIR) -> tuple[pd.DataFrame, dict]:
    """Verify all saved evidence, then join strictly on taxsimid (never row order)."""
    manifest = verify_manifest(reference_dir)
    households = (
        pd.read_csv(reference_dir / "households.csv").set_index("taxsimid").sort_index()
    )
    require(
        households.index.is_unique
        and households.index.tolist() == list(range(88052, 89207)),
        "Expected exactly 1,155 unique taxsimids, 88052–89206",
    )
    require(
        bool((households.year.eq(2025) & households.state.eq(1)).all()),
        "Input year/state",
    )
    current = _release(reference_dir, 1, households)
    previous = _release(reference_dir, 0, households)
    side = (
        pd.read_csv(reference_dir / "pe_intermediates.csv")
        .set_index("taxsimid")
        .sort_index()
    )
    side = side.rename(columns=lambda c: c.removeprefix("pe_"))
    require(side.index.is_unique and side.index.equals(households.index), "Sidecar IDs")
    require(bool((side.year.eq(2025) & side.state.eq(1)).all()), "Sidecar year/state")
    require(
        bool(np.isfinite(side[list(PE_EXTRA.values())]).all().all()),
        "Unavailable PE components",
    )
    parts = [households, side.add_prefix("pe_sidecar_")]
    for source, prefix in (("policyengine", "pe"), ("taxsim", "taxsim")):
        raw = current[source]
        lane = pd.DataFrame({metric: raw[column] for metric, column in METRICS.items()})
        lane["deductions"] = raw[["v34", "v35"]].max(axis=1, skipna=False)
        lane["deductions_status"] = (
            "PE_formula_max_std_itemized" if prefix == "pe" else "observed_behavior_fit"
        )
        lane["federal_tax_deduction"] = np.nan
        lane["federal_tax_deduction_status"] = "unavailable"
        lane["exemptions_status"] = "v33_semantics_unverified"
        if prefix == "pe":
            for metric, variable in PE_EXTRA.items():
                lane[metric] = side[variable]
            lane["exemptions"] = side[
                ["al_personal_exemption", "al_dependent_exemption"]
            ].sum(axis=1, min_count=2)
            lane["exemptions_status"] = "direct_PE_replay"
            lane["federal_tax_deduction_status"] = "direct_PE_replay"
            for variable, column in [
                ("al_agi", "v32"),
                ("al_taxable_income", "v36"),
                ("al_income_tax", "siitax"),
            ]:
                lane["replay_minus_release_" + variable] = side[variable] - raw[column]
        lane["ti_floored"] = raw.v36.eq(0)
        # Residuals are arithmetic observations, not inferred federal deductions.
        lane["unallocated_ti_reduction"] = raw.v32 - lane.deductions - raw.v36
        lane["unallocated_after_v33"] = lane.unallocated_ti_reduction - raw.v33
        lane["unallocated_after_exemptions"] = (
            lane.unallocated_ti_reduction - lane.exemptions
        )
        lane["net_tax_reduction"] = raw.staxbc - raw.siitax
        lane["credit_reconciliation_residual"] = raw.staxbc - raw.v40 - raw.siitax
        for column in RAW:
            lane["raw_" + column] = raw[column]
        for column in ("fiitax", "niit"):
            lane[column + "_state0"] = previous[source][column]
            lane[column + "_state1_minus_state0"] = (
                raw[column] - previous[source][column]
            )
        parts.append(lane.add_prefix(prefix + "_"))
    frame = pd.concat(parts, axis=1).copy()
    # A refreshed, re-hashed reference release can supply direct form amounts.
    # Retain status alongside each amount: the adapter requires verified_form_line.
    # The present releases contain none of these supplemental form-line columns.
    for source, prefix in (("policyengine", "pe"), ("taxsim", "taxsim")):
        raw = current[source]
        for field in FEDERAL_FIELDS:
            if field in raw and field + "_status" in raw:
                frame[f"{prefix}_federal_{field}"] = raw[field]
                frame[f"{prefix}_federal_{field}_status"] = raw[field + "_status"]
    for metric in OUTPUTS:
        frame["pe_minus_taxsim_" + metric] = (
            frame["pe_" + metric] - frame["taxsim_" + metric]
        )
    delta = frame.pe_minus_taxsim_liability.abs()
    frame["pe_taxsim_liability_band"] = np.select(
        [delta <= 1, delta <= 15, delta > 15], BANDS, default="unavailable"
    )
    return frame, manifest


def cause_attribution(frame: pd.DataFrame) -> dict:
    """Observed component associations, not a causal/legal adjudication.

    The TI and liability identities below allocate arithmetic gaps exactly.
    No state tax rate, deduction chart or exemption formula is encoded here.
    A household can have several component differences; primary_stage chooses
    the first observed difference in calculation order, not a proven cause.
    """
    flags = pd.DataFrame(index=frame.index)
    for metric in (
        "agi",
        "deductions",
        "exemptions",
        "taxable_income",
        "tax_before_credits",
    ):
        flags[metric] = frame["pe_minus_taxsim_" + metric].abs() > 1
    flags["net_tax_reduction"] = (
        frame.pe_net_tax_reduction - frame.taxsim_net_tax_reduction
    ).abs() > 1
    primary = pd.Series("no_component_gap_over_1", index=frame.index)
    for name in reversed(list(flags.columns)):
        primary.loc[flags[name]] = name
    frame["first_observed_component_difference"] = primary
    # PE v33 is unreported: use its replay exemptions for the identity, while
    # retaining the raw unavailable v33. TAXSIM exemptions retain v33 semantics.
    ti_reconciled = (
        (frame.pe_raw_v32 - frame.taxsim_raw_v32)
        - frame.pe_minus_taxsim_deductions
        - frame.pe_minus_taxsim_exemptions
        - (
            frame.pe_unallocated_after_exemptions
            - frame.taxsim_unallocated_after_exemptions
        )
    )
    liability_reconciled = frame.pe_minus_taxsim_tax_before_credits - (
        frame.pe_net_tax_reduction - frame.taxsim_net_tax_reduction
    )
    return {
        "status": "observed_component_association",
        "interpretation": "Counts locate observed differences; they do not establish which engine is legally correct. Component counts overlap. Primary stage is first difference in calculation order.",
        "bands": {
            band: {
                "households": int(frame.pe_taxsim_liability_band.eq(band).sum()),
                "component_difference_counts": {
                    name: int(
                        flags.loc[frame.pe_taxsim_liability_band.eq(band), name].sum()
                    )
                    for name in flags
                },
                "primary_stage_counts": primary[frame.pe_taxsim_liability_band.eq(band)]
                .value_counts()
                .to_dict(),
            }
            for band in BANDS
        },
        "taxsim_deductions": {
            "status": "observed_behavior_fit",
            "expression": "max(v34, v35)",
            "limitation": "Candidate selected deduction only; not law. v33 semantics are unverified; the remaining TI residual is not a federal deduction.",
        },
        "taxable_income_identity": "v32 - max(v34,v35) - exemptions - unallocated_after_exemptions = v36; PE exemptions from replay, TAXSIM exemptions=v33",
        "taxable_income_gap_identity_max_abs_error": float(
            (ti_reconciled - frame.pe_minus_taxsim_taxable_income).abs().max()
        ),
        "liability_identity": "siitax = staxbc - net_tax_reduction",
        "liability_gap_identity_max_abs_error": float(
            (liability_reconciled - frame.pe_minus_taxsim_liability).abs().max()
        ),
        "zero_taxable_income_censored": {
            p: int(frame[p + "_ti_floored"].sum()) for p in ("pe", "taxsim")
        },
        "federal_deduction_comparison": "unavailable: TAXSIM does not report an identified federal deduction",
        "pe_replay_max_abs_drift": {
            variable: float(frame["pe_replay_minus_release_" + variable].abs().max())
            for variable in ("al_agi", "al_taxable_income", "al_income_tax")
        },
    }


def _pairwise(frame: pd.DataFrame, left: str, right: str, *, suite: str) -> dict:
    mapping = ProgramMapping(
        standard=CONCEPT,
        description="Alabama TY2025 final state income tax liability",
        category="tax",
        comparison="amount",
        tolerance=1,
        relative_tolerance=0,
        targets={left: "siitax", right: "siitax"},
    )
    cases = [
        Case(
            case_id=int(taxsimid),
            period="2025",
            outputs=(CONCEPT,),
            metadata={
                "locale": "US-AL",
                "taxsim_input": {
                    "taxsimid": int(taxsimid),
                    **{
                        k: None if pd.isna(row[k]) else row[k]
                        for k in HOUSEHOLD_COLUMNS
                    },
                },
            },
        )
        for taxsimid, row in frame.iterrows()
    ]
    results = {
        engine: [
            EngineResult(engine, int(i), {"siitax": float(value)})
            for i, value in frame[engine + "_liability"].items()
        ]
        for engine in (left, right)
    }
    return build_comparison_report(
        suite_name=suite,
        population="ecps",
        locales={"US-AL"},
        scope=None,
        cases=cases,
        mappings=[mapping],
        comparisons=Comparator([mapping]).compare(results[left], results[right]),
    )


def generate(
    *,
    reference_dir: Path = REFERENCE_DIR,
    rulespec_root: Path | None = None,
    output: Path | None = None,
    markdown_output: Path | None = None,
) -> dict:
    output = output or REPO_ROOT / "reports/al-income-tax-2025-three-way.json"
    rulespec_root = rulespec_root or Path(
        os.environ.get("RULESPEC_US_REPO", REPO_ROOT.parent / "rulespec-us")
    )
    frame, manifest = assemble(reference_dir)
    attribution = cause_attribution(frame)
    households = (
        pd.read_csv(reference_dir / "households.csv").set_index("taxsimid").sort_index()
    )
    legs = evaluate_axiom_legs(
        households,
        frame,
        rulespec_root=rulespec_root,
        scratch_dir=REPO_ROOT / ".cache/al-income-tax-2025",
    )
    report = _pairwise(
        frame.rename(columns={"pe_liability": "policyengine_liability"}),
        "policyengine",
        "taxsim",
        suite=SUITE,
    )
    report["period"] = "2025"
    report["status"] = "complete_pe_taxsim_with_conditional_axiom"
    report["diagnostic_bands"] = {
        band: int(frame.pe_taxsim_liability_band.eq(band).sum()) for band in BANDS
    }
    report["band_definitions"] = {
        "within_1": "abs(PE-TAXSIM) <= 1",
        "over_1_through_15": "1 < abs(PE-TAXSIM) <= 15",
        "over_15": "abs(PE-TAXSIM) > 15",
    }
    report["cause_attribution"] = attribution
    report["axiom_legs"] = legs
    report["axiom_pairwise_reports"] = {}
    for feed, leg in legs.items():
        prefix = "axiom_" + feed
        cases = pd.DataFrame(
            [
                {"taxsimid": row["taxsimid"], **row["outputs"], "status": row["status"]}
                for row in leg["cases"]
            ]
        ).set_index("taxsimid")
        for metric in OUTPUTS:
            frame[prefix + "_" + metric] = cases[metric]
        frame[prefix + "_status"] = cases.status
        available = cases.status.eq("evaluated") & frame[prefix + "_liability"].notna()
        if available.any():
            for comparator in ("policyengine", "taxsim"):
                subset = frame.loc[available].rename(
                    columns={"pe_liability": "policyengine_liability"}
                )
                edge = _pairwise(
                    subset, prefix, comparator, suite=f"{SUITE}-{feed}-vs-{comparator}"
                )
                edge["coverage"] = {
                    "evaluated": len(subset),
                    "unavailable": int((~available).sum()),
                    "total": len(frame),
                }
                report["axiom_pairwise_reports"][f"{feed}_vs_{comparator}"] = edge
    report["provenance"] = {
        "schema": "axiom_oracles.provenance.v1",
        "reference_manifest_sha256": sha256(reference_dir / "manifest.json"),
        "reference_manifest": manifest,
        "rulespecs": rulespec_provenance([rulespec_root])
        if any(leg["compiled"] for leg in legs.values())
        else [],
        "engine": {
            "status_by_federal_feed": {
                feed: leg["status"] for feed, leg in legs.items()
            }
        },
        "oracle": {
            "name": "policyengine-taxsim-saved-releases",
            "policyengine_us": manifest["provenance"]["engines"][
                "policyengine_us_version"
            ],
            "policyengine_core": manifest["provenance"]["engines"][
                "policyengine_core_version"
            ],
            "taxsim_binary_sha256": manifest["provenance"]["engines"][
                "taxsim_binary_sha256"
            ],
        },
        "dataset": {
            "source": "ecps-alabama",
            "filename": "households.csv",
            "sha256": manifest["files"]["households.csv"]["sha256"],
            "households": len(frame),
        },
        "engine_execution": "PE and TAXSIM are committed reference observations, not reruns; Axiom execution status is recorded separately for each federal feed.",
        "component_provenance": "State1 releases for liabilities/AGI/TI; PE sidecar replay for exemptions and deductions. Original release columns retained as *_raw_*; state0 is diagnostic only.",
        "prototype_csv_sha256": "b8d2389b40ccb9baf8b1644b3ede9b614f04d318599c2fe4f7e76d5ab37374b3",
        "prototype_note": "Assembly port extends the prototype with PE sidecar deduction components, observed associations and live-adapter statuses; the emitted CSV is not byte-identical to the prototype.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    components = output.with_name(output.stem + "-components.csv")
    frame.reset_index().to_csv(components, index=False, na_rep="", lineterminator="\n")
    report["component_table"] = {
        "path": components.name,
        "sha256": sha256(components),
        "rows": len(frame),
        "key": "taxsimid",
        "metrics": METRICS,
        "columns": ["taxsimid", *frame.columns],
    }
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    markdown_output = markdown_output or output.with_suffix(".md")
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.write_text(_markdown(report))
    return report


def _markdown(report: dict) -> str:
    lines = [
        "# Alabama TY2025 three-way lane",
        "",
        "1,155 eCPS households, taxsimid 88052–89206. Final liability: `siitax`.",
        "",
        "| PE versus TAXSIM absolute gap | Households |",
        "|---|---:|",
    ]
    for band, count in report["diagnostic_bands"].items():
        lines.append(f"| {report['band_definitions'][band]} | {count} |")
    lines += [
        "",
        "Tolerance is $1 absolute, relative zero; $1–$15 is a diagnostic band.",
        "",
        "Axiom federal feeds are one implementation, not independent votes.",
        "",
    ]
    for feed, leg in report["axiom_legs"].items():
        lines.append(
            f"- {feed}: **{leg['status']}** — {leg['reason']} (`{leg['module_path']}`)."
        )
    lines += [
        "",
        "Component attribution is observational, not legal adjudication. Multiple component differences may coexist.",
        "",
        "| Band | First observed difference (households) |",
        "|---|---|",
    ]
    for band, data in report["cause_attribution"]["bands"].items():
        counts = ", ".join(
            f"{name}: {count}" for name, count in data["primary_stage_counts"].items()
        )
        lines.append(f"| {band} | {counts} |")
    lines += [
        "",
        "TAXSIM `max(v34,v35)` is an `observed_behavior_fit`; its unallocated taxable-income reduction is not an identified federal deduction. Zero taxable income censors decomposition.",
        "",
        "PE component replay differs from saved release amounts by at most $4 AGI, $8 taxable income and $0.50 liability; both representations are retained.",
        "",
        "Federal crosswalks preserve unavailable Form 1040 line 22 and other unreported worksheet amounts. `fiitax` is never substituted for line 22.",
        "",
        "With these saved references, module availability enables compilation, but both feeds also need verified line 22, refundable AOTC, refundable adoption and Schedule 3 line 13a amounts before evaluation. A refreshed manifest may supply these as named form-line columns plus `<field>_status=verified_form_line` in each engine release.",
        "",
        f"Per-household component table: [{report['component_table']['path']}]({report['component_table']['path']}). Full provenance and crosswalks are in the JSON report.",
        "",
        "Ground-truth fixtures are documentary evidence and are not Python tax-law expectations. The signed corpus release is `us-rulespec-2026-09-14-wave4-r2-union`; narrow union axiom-corpus#746 and signing decision d270 remain pending.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-dir", type=Path, default=REFERENCE_DIR)
    parser.add_argument("--rulespec-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()
    report = generate(**vars(args))
    print(
        json.dumps(
            {
                "suite": report["suite"],
                "bands": report["diagnostic_bands"],
                "axiom": {k: v["status"] for k, v in report["axiom_legs"].items()},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
