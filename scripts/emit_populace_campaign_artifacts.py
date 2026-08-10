#!/usr/bin/env python
"""Emit per-state dashboard reports from the state-tax Populace campaign.

The campaign runner (scripts/run_state_tax_populace.py) writes ONE
campaign-level report covering every ready state over the full pinned US
Populace. The dashboard is suite-keyed, so this script projects that
report into one slim axiom.comparison_report.v2 per state
(``axiom-policyengine-<st>-income-tax-populace.json``) and registers each
in ``dashboard/public/data/manifest.json``. Each projected report cites
the campaign report as its source of record.

Usage:
    .venv/bin/python scripts/emit_populace_campaign_artifacts.py [campaign.json]

With no argument the newest reports/state-tax-populace-campaign-*.json is
used.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import yaml

from axiom_oracles.provenance import RUN_KINDS, build_provenance

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS = REPO_ROOT / "reports"
DASH_DATA = REPO_ROOT / "dashboard" / "public" / "data"
POPULACE_SUITE_CONFIG = REPO_ROOT / "comparisons/state-income-tax-populace.yaml"
RETIRED_MANIFEST_REPORTS = frozenset(
    {
        "axiom-policyengine-taxsim-al-income-tax-liability.json",
        "axiom-policyengine-taxsim-de-income-tax-liability.json",
    }
)

_DESCRIPTION_BY_OUTPUT = {
    (
        "us-al:policies/income_tax/"
        "2026_section_40_18_5_schedule_before_credits"
        "#al_pit_2026_section_40_18_5_schedule_before_credits"
    ): (
        "Alabama Code section 40-18-5 schedule before credits, computed from "
        "caller-supplied completed Alabama taxable income and the reviewed "
        "joint-or-surviving-spouse schedule classifier, over every routed tax "
        "unit in the pinned US Populace"
    ),
    (
        "us-ar:policies/income_tax/pilot_liability_pipeline"
        "#ar_pit_pilot_income_tax_before_non_refundable_credits_indiv"
    ): (
        "Arkansas Act 2 of 2026 section 1 individual schedule component before "
        "nonrefundable credits, computed from caller-supplied completed "
        "Arkansas individual taxable income at Person grain and summed to "
        "TaxUnit only for comparison accounting over every routed tax unit and "
        "linked person in the pinned US Populace; this bounded suite excludes "
        "taxable-income construction, filing-unit aggregation or method "
        "selection, low-income tables, credits, payments, and final liability"
    ),
    (
        "us-ct:policies/income_tax/"
        "2026_resident_ordinary_tax_before_personal_credit"
        "#ct_pit_2026_resident_ordinary_tax_before_personal_credit"
    ): (
        "Connecticut resident ordinary section 12-700 tax before the "
        "personal credit over every routed tax unit in the pinned US Populace"
    ),
    (
        "us-ca:policies/income_tax/pilot_liability_pipeline"
        "#ca_pit_pilot_behavioral_health_services_tax"
    ): (
        "California Behavioral Health Services Tax, computed as 1 percent of "
        "caller-supplied completed California taxable income above $1 million, "
        "over every routed tax unit in the pinned US Populace; this component "
        "suite does not claim broad California income-tax liability"
    ),
    (
        "us-dc:policies/income_tax/"
        "2026_section_47_1806_03_schedule_before_credits"
        "#dc_pit_2026_section_47_1806_03_schedule_before_credits"
    ): (
        "District of Columbia section 47-1806.03(a)(11) joint-method "
        "schedule before credits, computed from caller-supplied completed "
        "joint-method District taxable income, over every routed tax unit in "
        "the pinned US Populace"
    ),
    (
        "us-de:policies/income_tax/pilot_liability_pipeline"
        "#de_pit_pilot_separate_schedule_tax"
    ): (
        "Delaware Code title 30 section 1102(a)(14) individual schedule "
        "component before nonrefundable credits, computed from caller-supplied "
        "completed Delaware taxable income at Person grain and summed to "
        "TaxUnit only for comparison accounting over every routed tax unit and "
        "linked person in the pinned US Populace; this bounded suite excludes "
        "filing-method selection, combined-return computation, credits, "
        "payments, and final liability"
    ),
    (
        "us-ga:policies/income_tax/"
        "2026_annual_tax_before_nonrefundable_credits"
        "#ga_pit_2026_annual_tax_before_nonrefundable_credits"
    ): (
        "Georgia section 48-7-20 annual tax before nonrefundable credits, "
        "computed from caller-supplied completed Georgia taxable net income, "
        "over every routed tax unit in the pinned US Populace"
    ),
    (
        "us-ks:policies/income_tax/2026_k40es_schedule_before_credits"
        "#ks_pit_2026_k40es_schedule_before_credits"
    ): (
        "Official Kansas tax-year-2026 K-40ES joint or all-other-filer "
        "schedule before credits, computed from caller-supplied completed "
        "Kansas taxable income, over every routed tax unit in the pinned US "
        "Populace"
    ),
    (
        "us-il:policies/income_tax/pilot_liability_pipeline"
        "#il_pit_pilot_income_tax_liability"
    ): (
        "Illinois annual individual income tax before nonrefundable credits, "
        "computed from caller-supplied completed Illinois taxable income and "
        "completed investment-credit recapture over every routed tax unit in "
        "the pinned US Populace; this bounded suite excludes taxable-income "
        "construction, credit computation, payments, and final annual "
        "liability"
    ),
    (
        "us-in:policies/income_tax/pilot_liability_pipeline"
        "#in_pit_pilot_income_tax_liability"
    ): (
        "Indiana adjusted-gross-income tax before credits and excluding county "
        "tax, computed by applying the tax-year-2026 2.95 percent state rate "
        "to caller-supplied completed Indiana adjusted gross income over every "
        "routed tax unit in the pinned US Populace; this bounded suite excludes "
        "adjusted-gross-income construction, county tax, credits, payments, "
        "and final annual liability"
    ),
    (
        "us-ms:policies/income_tax/2026_section_27_7_5_schedule"
        "#ms_pit_2026_section_27_7_5_schedule_tax"
    ): (
        "Mississippi section 27-7-5 Person-grain calendar-year-2026 schedule "
        "tax, computed from caller-supplied completed Mississippi taxable "
        "income and summed to tax units only for Populace accounting"
    ),
    (
        "us-mn:policies/income_tax/pilot_liability_pipeline"
        "#mn_pit_pilot_schedule_tax"
    ): (
        "Minnesota tax-year-2026 continuous graduated schedule under section "
        "290.06, computed from caller-supplied completed Minnesota taxable net "
        "income and reviewed filing-status classifiers over every routed tax "
        "unit in the pinned US Populace; this schedule suite does not claim "
        "tax-table rounding, alternative minimum tax, net investment income "
        "tax, credits, payments, or final Minnesota liability"
    ),
    (
        "us-mt:policies/income_tax/pilot_liability_pipeline"
        "#mt_pit_pilot_income_tax_liability"
    ): (
        "Montana tax-year-2026 individual income tax before nonrefundable "
        "credits under MCA 15-30-2103, computed from caller-supplied completed "
        "Montana taxable income, its reviewed section 1222 net-long-term-"
        "capital-gain portion, and filing-status classifiers over every routed "
        "tax unit in the pinned US Populace; this bounded suite excludes "
        "taxable-income construction, credits, payments, and final annual "
        "liability"
    ),
    (
        "us-ny:policies/income_tax/pilot_liability_pipeline"
        "#ny_pit_pilot_main_income_tax"
    ): (
        "New York Tax Law section 601 main resident individual-income-tax "
        "schedule, computed from caller-supplied completed New York taxable "
        "income and strict filing-status schedule classifiers over every "
        "routed tax unit in the pinned US Populace; this bounded suite "
        "excludes section 601(d-5) supplemental tax, credits, local taxes, "
        "payments, and final liability"
    ),
    (
        "us-ok:policies/income_tax/pilot_liability_pipeline"
        "#ok_pit_pilot_income_tax_liability"
    ): (
        "Oklahoma tax-year-2026 individual income tax before credits, computed "
        "from caller-supplied completed Oklahoma taxable income under the "
        "enacted single-or-separate or doubled-width joint, surviving-spouse, "
        "and head-of-household schedule over every routed tax unit in the "
        "pinned US Populace; this bounded suite excludes taxable-income "
        "construction, credits, payments, and final annual liability"
    ),
    (
        "us-pa:policies/income_tax/pilot_liability_pipeline"
        "#pa_pit_pilot_income_tax_liability"
    ): (
        "Pennsylvania resident income tax before forgiveness, computed by "
        "applying the tax-year-2026 3.07 percent rate to caller-supplied "
        "completed Pennsylvania adjusted taxable income over every routed tax "
        "unit in the pinned US Populace; the runtime fails closed unless every "
        "selected boundary is nonnegative, and this bounded suite excludes "
        "adjusted-taxable-income construction, forgiveness, credits, payments, "
        "and final annual liability"
    ),
    (
        "us-sc:policies/income_tax/pilot_liability_pipeline"
        "#sc_pit_pilot_income_tax_liability"
    ): (
        "South Carolina tax-year-2026 individual income tax before "
        "nonrefundable credits, computed from caller-supplied completed South "
        "Carolina taxable income under the enacted two-bracket schedule over "
        "every routed tax unit in the pinned US Populace; the runtime fails "
        "closed unless every selected boundary is nonnegative, and this "
        "bounded suite excludes taxable-income construction, nonrefundable "
        "credits, payments, and final annual liability"
    ),
    (
        "us-oh:policies/income_tax/pilot_liability_pipeline"
        "#oh_pit_pilot_schedule_tax"
    ): (
        "Ohio Revised Code section 5747.02(A)(3)(c) tax-year-2026 "
        "nonbusiness-income schedule before nonrefundable credits, computed "
        "from caller-supplied completed Ohio taxable nonbusiness income, over "
        "every routed tax unit in the pinned US Populace"
    ),
    (
        "us-ut:policies/income_tax/"
        "2026_full_year_resident_before_credit_schedule"
        "#ut_pit_2026_resident_income_tax_before_credits"
    ): (
        "Utah section 59-10-104 full-year-resident tax before credits, "
        "including the section 59-10-104.1 exemption gate, over every routed "
        "tax unit in the pinned US Populace"
    ),
}

_REQUIRED_RUNTIME_FIELDS = {
    "rulespec": ("repository", "commit", "working_tree"),
    "axiom_engine": (
        "repository",
        "commit",
        "executable_sha256",
        "working_tree",
    ),
    "packages": ("policyengine", "policyengine-us"),
}
_REQUIRED_DATASET_FIELDS = ("source", "revision", "sha256", "built_with", "country")


def _require_nonempty_fields(value: object, fields: tuple[str, ...], label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"campaign report {label} must be an object")
    missing = [
        field
        for field in fields
        if not isinstance(value.get(field), str) or not value[field].strip()
    ]
    if missing:
        raise ValueError(
            f"campaign report {label} must carry {', '.join(fields)}; "
            f"missing {', '.join(missing)}"
        )
    return value


def latest_campaign_report() -> Path:
    candidates = sorted(REPORTS.glob("state-tax-populace-campaign-*.json"))
    if not candidates:
        raise SystemExit("no reports/state-tax-populace-campaign-*.json found")
    return candidates[-1]


def validate_campaign_run_provenance(campaign: dict) -> tuple[str, str, dict]:
    """Return exact campaign-run provenance or fail before projecting.

    A projection is a view of an existing comparison, not a new oracle run.
    Its freshness timestamp and run kind must therefore come from the source
    campaign and may never default to projection time or local environment.
    """

    generated_at = campaign.get("generated_at")
    if not isinstance(generated_at, str):
        raise ValueError("campaign report is missing generated_at")
    try:
        datetime.strptime(generated_at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValueError(
            "campaign report generated_at must be UTC YYYY-MM-DDTHH:MM:SSZ"
        ) from exc

    run_kind = campaign.get("run_kind")
    if run_kind not in RUN_KINDS:
        raise ValueError(
            f"campaign report run_kind must be one of {RUN_KINDS}; got {run_kind!r}"
        )

    runtime = campaign.get("runtime_provenance")
    if not isinstance(runtime, dict):
        raise ValueError("campaign report runtime_provenance must be an object")
    for section, fields in _REQUIRED_RUNTIME_FIELDS.items():
        _require_nonempty_fields(
            runtime.get(section),
            fields,
            f"runtime_provenance.{section}",
        )
    _require_nonempty_fields(
        campaign.get("dataset_identity"),
        _REQUIRED_DATASET_FIELDS,
        "dataset_identity",
    )
    return generated_at, run_kind, runtime


def project_state(
    state: str,
    entry: dict,
    campaign: dict,
    source_name: str,
) -> dict:
    compared = int(entry["compared_count"])
    mismatches = entry.get("mismatches") or []
    mismatch_count = int(entry["mismatch_count"])
    matched = compared - mismatch_count
    rate = (matched / compared * 100) if compared else 100.0
    concept = entry["output"]
    description = _DESCRIPTION_BY_OUTPUT.get(
        concept,
        (
            "State income tax liability over every routed tax unit in the "
            "pinned US Populace"
        ),
    )
    aggregate = {
        "comparison": "amount",
        "comparison_count": compared,
        "compared": compared,
        "components": [],
        "concept": concept,
        "description": description,
        "match_count": matched,
        "match_rate": rate,
        "matched": matched,
        "mismatch_count": mismatch_count,
        "missing_both_count": 0,
        "missing_left_count": 0,
        "missing_right_count": 0,
        "parent": None,
        "weighted_match_rate": rate,
    }
    generated_at, run_kind, runtime = validate_campaign_run_provenance(campaign)
    rulespec = runtime.get("rulespec") or {}
    standard_provenance = build_provenance(
        generated_by=(
            "scripts/emit_populace_campaign_artifacts.py"
            f"::{state.lower()}-income-tax-populace"
        ),
        run_kind=run_kind,
        generated_at=generated_at,
        rulespecs=[
            {
                "repo": rulespec.get("repository"),
                "sha": rulespec.get("commit"),
            }
        ]
        if rulespec.get("repository")
        else None,
    )
    standard_provenance.update(
        {
            "campaign_report": source_name,
            "dataset_identity": campaign.get("dataset_identity"),
            "runtime_provenance": runtime or None,
            "tolerance": entry.get("tolerance"),
            "relative_tolerance": entry.get("relative_tolerance"),
            "max_absolute_difference": entry.get("max_absolute_difference"),
            "weighted_compared_tax_units": entry.get("weighted_compared_tax_units"),
            "branch_diagnostics": (
                campaign.get("projection_diagnostics", {}).get(state)
            ),
        }
    )
    return {
        "schema_version": "axiom.comparison_report.v2",
        "suite": f"{state.lower()}-income-tax-populace",
        "case_count": compared,
        "population": "populace-us",
        "engines": {
            "axiom": entry["program"],
            "policyengine": entry["policyengine_target"],
        },
        "aggregates": [aggregate],
        "cases": [],
        "mismatches": mismatches,
        "errors": [],
        "summary": {
            "comparison_count": compared,
            "match_count": matched,
            "match_rate": rate,
            "mismatch_count": mismatch_count,
        },
        "provenance": standard_provenance,
    }


CASES_ROOT = DASH_DATA / "cases"
CHUNK_SIZE = 500


def configured_populace_reports(
    config_path: Path = POPULACE_SUITE_CONFIG,
) -> frozenset[str]:
    """Return every dashboard report required by the Populace suite registry."""

    config = yaml.safe_load(config_path.read_text()) or {}
    suites = config.get("suites") or []
    reports = {
        suite.get("report")
        for suite in suites
        if isinstance(suite, dict) and isinstance(suite.get("report"), str)
    }
    if len(reports) != len(suites):
        raise ValueError(
            "Populace suite registry must declare one unique report per suite"
        )
    return frozenset(reports)


def reconcile_manifest_reports(
    reports: list[str],
    *,
    data_dir: Path = DASH_DATA,
    required_reports: frozenset[str] = frozenset(),
) -> list[str]:
    """Retire reviewed ghosts and fail closed on every other missing report.

    The manifest is a load list, not a registry of intended future reports.
    A report may be removed only through the explicit retirement allowlist.
    Missing configured reports or missing files are publication failures.
    """

    reconciled = [
        name for name in reports if name not in RETIRED_MANIFEST_REPORTS
    ]
    missing_required_entries = sorted(required_reports - set(reconciled))
    if missing_required_entries:
        raise ValueError(
            "manifest is missing required configured Populace report(s): "
            + ", ".join(missing_required_entries)
        )
    missing_files = sorted(
        name for name in reconciled if not (data_dir / name).is_file()
    )
    if missing_files:
        raise ValueError(
            "manifest references unpublished dashboard report(s): "
            + ", ".join(missing_files)
        )
    return reconciled


def emit_case_chunks(state: str, entry: dict) -> str | None:
    """Project the campaign's per-tax-unit rows into case-explorer chunks.

    Campaign reports produced before the runner persisted rows have no
    ``cases`` key; those states keep the explorer's no-evidence message
    until the next campaign run.
    """

    rows = entry.get("cases") or []
    if not rows:
        return None
    suite = f"{state.lower()}-income-tax-populace"
    concept = entry.get("output") or "state_income_tax"
    out_rows = []
    for row in rows:
        matched = bool(row.get("matched"))
        compact = {
            "id": row.get("tax_unit_id"),
            "r": 1.0 if matched else 0.0,
            "h": {},
            "m": []
            if matched
            else [
                {
                    "c": concept,
                    "l": row.get("axiom"),
                    "x": row.get("policyengine"),
                    "d": round(
                        (row.get("axiom") or 0) - (row.get("policyengine") or 0),
                        2,
                    ),
                }
            ],
            "v": [
                {
                    "c": concept,
                    "l": row.get("axiom"),
                    "x": row.get("policyengine"),
                }
            ]
            if matched
            else [],
        }
        out_rows.append(compact)
    out_rows.sort(key=lambda r: r["r"])
    out_dir = CASES_ROOT / suite
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("chunk-*.json"):
        stale.unlink()
    chunks = [out_rows[i : i + CHUNK_SIZE] for i in range(0, len(out_rows), CHUNK_SIZE)]
    for i, chunk in enumerate(chunks):
        (out_dir / f"chunk-{i}.json").write_text(
            json.dumps(chunk, separators=(",", ":"))
        )
    index = {
        "suite": suite,
        "count": len(out_rows),
        "total_cases": len(out_rows),
        "chunks": len(chunks),
        "chunk_size": CHUNK_SIZE,
        "engines": {"left": "axiom", "right": "policyengine"},
        "mismatch_concepts": [concept],
        "source": "state-tax-populace-campaign",
    }
    (out_dir / "index.json").write_text(json.dumps(index, indent=1) + "\n")
    return f"{suite}: {len(out_rows)} cases in {len(chunks)} chunks"


def main() -> int:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else latest_campaign_report()
    campaign = json.loads(source.read_text())
    validate_campaign_run_provenance(campaign)
    states = (campaign.get("comparison") or {}).get("states") or {}
    if not states:
        raise SystemExit(f"{source} carries no per-state comparison block")

    manifest_path = DASH_DATA / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    reports = list(manifest.get("reports") or [])

    for state, entry in sorted(states.items()):
        emitted = emit_case_chunks(state, entry)
        if emitted:
            print(emitted)
        report = project_state(
            state,
            entry,
            campaign,
            source.name,
        )
        filename = f"axiom-policyengine-{state.lower()}-income-tax-populace.json"
        (DASH_DATA / filename).write_text(
            json.dumps(report, indent=1, sort_keys=True) + "\n"
        )
        if filename not in reports:
            reports.append(filename)
        print(
            f"{state}: {report['summary']['match_count']}/"
            f"{report['summary']['comparison_count']} -> {filename}"
        )

    manifest["reports"] = reconcile_manifest_reports(
        reports,
        required_reports=configured_populace_reports(),
    )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"manifest: {len(manifest['reports'])} reports")
    return 0


if __name__ == "__main__":
    sys.exit(main())
