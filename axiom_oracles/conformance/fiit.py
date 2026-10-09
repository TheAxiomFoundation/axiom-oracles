"""Bind FIIT outputs to returned values, never configured output counts."""

from axiom_oracles.bridges.tax_populace import SURFACE_OUTPUTS
from axiom_oracles.conformance.observations import OutputEvidence, observed_output_value


FIIT_SURFACE_CONCEPT_IDS = {
    "ctc": "us:tax/federal-income-tax#ctc",
    "standard-deduction": "us:tax/federal-income-tax#standard_deduction",
    "capital-gain-definitions": "us:tax/federal-income-tax#capital_gain",
    "tax-before-credits": "us:tax/federal-income-tax#tax_before_credits",
    "eitc": "us:tax/federal-income-tax#eitc",
    "cdcc": "us:tax/federal-income-tax#cdcc",
    "aotc": "us:tax/federal-income-tax#aotc",
    "nonrefundable-credits": "us:tax/federal-income-tax#nonrefundable_credits",
    "income-tax": "us:tax/federal-income-tax#income_tax",
    "employee-oasdi": "us:tax/payroll#employee_oasdi",
    "employee-medicare": "us:tax/payroll#employee_medicare",
    "employer-oasdi": "us:tax/payroll#employer_oasdi",
    "employer-medicare": "us:tax/payroll#employer_medicare",
}
FIIT_PARENT = "us:tax/federal-income-tax#liability"


def fiit_output_rows(
    output_summary: list[dict], *, report: dict | None = None,
) -> tuple[list[dict], bool]:
    """Stamp only the returned FIIT values the shared predicate accepts."""
    counts: dict[tuple[str, str], int] = {}
    known_outputs: dict[tuple[str, str], tuple[str, str]] = {}
    evidence = OutputEvidence(report or {})
    complete = (
        report is not None
        and isinstance(report.get("observed_outputs"), list)
        and bool(report["observed_outputs"])
    )
    for row in output_summary:
        if not isinstance(row, dict):
            complete = False
            continue
        compared = _int(row.get("compared"))
        if compared <= 0:
            continue
        surface = row.get("surface")
        concept = FIIT_SURFACE_CONCEPT_IDS.get(surface)
        target = SURFACE_OUTPUTS.get(surface, {}).get(row.get("output"), {}).get("pe")
        if concept is None or not target:
            complete = False
            continue
        known_outputs[(surface, row.get("output"))] = (concept, target)
    for row in (report or {}).get("observed_outputs") or []:
        if not isinstance(row, dict):
            complete = False
            continue
        key = known_outputs.get((row.get("surface"), row.get("output")))
        if key is None or row.get("engine") != "policyengine":
            complete = False
            continue
        concept, target = key
        if row.get("variable") != target:
            complete = False
            continue
        if observed_output_value(
            report,
            case_id=row.get("case_id"),
            output=target,
            value=row.get("value"),
            engine="policyengine",
            concept=concept,
            targets=(target,),
            evidence=evidence,
        ):
            counts[key] = counts.get(key, 0) + 1
    return [
        {
            "engine": "policyengine",
            "concept": concept,
            "variable": target,
            "comparisons": compared,
        }
        for (concept, target), compared in counts.items()
    ], complete


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
