"""Output evidence from the FIIT producer, whose targets differ from Comparator.

The legacy FIIT adapter discarded ``output_summary``. Its surface aggregates
still record the full producer loop: every named output is compared for each
tax unit (``bridges.tax_populace.compare_outputs``). Recover those bindings only
when the surface count proves that full loop; otherwise use explicit mismatch
output labels and mark the recording incomplete. The liability parent is the
sum of these comparisons, not a comparison of PolicyEngine's ``income_tax``.
"""

from axiom_oracles.bridges.tax_populace import PAYROLL_SURFACES, SURFACE_OUTPUTS


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


def fiit_output_rows(output_summary: list[dict]) -> tuple[list[dict], bool]:
    """Stamp exactly the positive output rows the FIIT producer compared."""
    counts: dict[tuple[str, str], int] = {}
    complete = True
    for row in output_summary:
        compared = _int(row.get("compared"))
        if compared <= 0:
            continue
        surface = row.get("surface")
        concept = FIIT_SURFACE_CONCEPT_IDS.get(surface)
        target = SURFACE_OUTPUTS.get(surface, {}).get(row.get("output"), {}).get("pe")
        if concept is None or not target:
            complete = False
            continue
        key = (concept, target)
        counts[key] = counts.get(key, 0) + compared
    return [
        {
            "engine": "policyengine",
            "concept": concept,
            "variable": target,
            "comparisons": compared,
        }
        for (concept, target), compared in counts.items()
    ], complete


def legacy_fiit_outputs(
    report: dict, oracle_engine: str
) -> tuple[frozenset[str], bool] | None:
    """Recover known FIIT producer bindings without consulting generic mappings."""
    if oracle_engine != "policyengine" or report.get("suite") != "fiit-ecps":
        return None
    provenance = report.get("provenance")
    if (
        not isinstance(provenance, dict)
        or provenance.get("generated_by") != "scripts/run_comparison.py::fiit-ecps"
    ):
        # An unidentified FIIT producer cannot be assigned another runner's
        # bindings. Keep execution evidence, but leave output coverage unknown.
        return frozenset(), False
    if isinstance(report.get("output_summary"), list):
        rows, complete = fiit_output_rows(report["output_summary"])
        return frozenset(row["variable"] for row in rows), complete

    concept_surfaces = {
        concept: surface
        for surface, concept in FIIT_SURFACE_CONCEPT_IDS.items()
        if concept != FIIT_PARENT
    }
    aggregates = [
        row
        for row in report.get("aggregates") or []
        if isinstance(row, dict) and _int(row.get("comparison_count")) > 0
    ]
    names: set[str] = set()
    complete = bool(aggregates)
    case_count = _int(report.get("case_count"))
    component_counts = {
        row.get("concept"): _int(row.get("comparison_count"))
        for row in aggregates
        if row.get("concept") != FIIT_PARENT
    }
    for aggregate in aggregates:
        concept = aggregate.get("concept")
        count = _int(aggregate.get("comparison_count"))
        if concept == FIIT_PARENT:
            components = aggregate.get("components") or []
            if (
                not components
                or set(components) != set(component_counts)
                or sum(component_counts.values()) != count
            ):
                complete = False
            continue
        surface = concept_surfaces.get(concept)
        outputs = SURFACE_OUTPUTS.get(surface, {})
        if not outputs:
            complete = False
            continue
        full_surface = (
            surface in PAYROLL_SURFACES and len(outputs) == 1
        ) or (case_count > 0 and count == case_count * len(outputs))
        if full_surface:
            names.update(spec["pe"] for spec in outputs.values())
            continue
        complete = False
        # A mismatch itself proves the named output was compared. It does not
        # prove that every other output configured for that surface was read.
        for mismatch in report.get("mismatches") or []:
            if mismatch.get("concept") != concept:
                continue
            output = str(mismatch.get("description") or "").rsplit("output=", 1)[-1]
            if output in outputs:
                names.add(outputs[output]["pe"])
    return frozenset(names), complete


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
