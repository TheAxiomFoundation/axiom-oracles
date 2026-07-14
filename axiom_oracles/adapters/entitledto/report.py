"""Build the UK Council Tax Reduction calculator-oracle report.

Assembles, per suite case, the three CTR figures the oracle compares:

* **entitledto** — the recorded per-council ground truth (``pending`` until a
  human captures it);
* **PolicyEngine-UK** — the committed 2.89.2 reference value (national schemes +
  five named councils; ``0`` where the council's scheme is unsupported);
* **hand-computed statutory** — the national-scheme formula
  ``max(0, liability - 0.20·max(0, applicable_income - applicable_amount))``
  evaluated on PolicyEngine's own applicable amount / income (so the schemes are
  commensurable, the sibling Axiom-vs-PE grid's convention). It is ``None`` for
  a council's *local* working-age scheme, which needs that council's published
  scheme document (or entitledto) to evaluate.

While every fixture is ``pending_capture`` the report grades nothing — it is a
truthful "0 captured / 8 pending" artifact that lists, for each case, the PE and
statutory values and what entitledto still has to fill. Once fixtures are
captured the same builder grades entitledto against both, through the shared
Comparator.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...comparison.comparator import Comparator
from ...comparison.mappings import ProgramMapping
from ...core.results import EngineResult
from ...suites.uk_ctr import PERIOD, uk_ctr_cases
from .recorded import EntitledToRecordedRunner, load_captures_by_id

SCHEMA_VERSION = "axiom.calculator_oracle_report.v1"
CTR_CONCEPT = (
    "uk:policies/govuk/council-tax-reduction#council_tax_reduction_annual_amount"
)
DEFAULT_PE_REFERENCE = (
    Path(__file__).resolve().parent / "fixtures" / "uk_ctr_policyengine_reference.json"
)

# The three national prescribed/consolidated schemes PolicyEngine and the
# statutory hand-check both implement with the same means test.
_NATIONAL_SCHEMES = frozenset(
    {
        "england-pension-age-prescribed",
        "scotland-working-age-national",
        "wales-working-age-national",
    }
)

_CTR_MAPPING = ProgramMapping(
    standard=CTR_CONCEPT,
    description="UK Council Tax Reduction annual amount",
    category="benefits",
    comparison="amount",
    tolerance=0.01,
    targets={
        "entitledto": "council_tax_reduction",
        "policyengine": "council_tax_reduction",
    },
)


def _hand_computed_statutory(
    scheme: str,
    liability: float,
    applicable_amount: float,
    applicable_income: float,
    capital: float,
    params: dict[str, Any],
) -> dict[str, Any]:
    """The national-scheme statutory CTR on PolicyEngine's applicable amount/income."""
    if scheme not in _NATIONAL_SCHEMES:
        return {
            "annual_gbp": None,
            "basis": "local working-age scheme — requires the council's published "
            "scheme (or entitledto) to evaluate; no national formula applies",
        }
    key = "england_pensioner" if "pension" in scheme else scheme.split("-")[0]
    p = params.get(key, {})
    max_support = float(p.get("maximum_support_rate", 1.0))
    withdrawal = float(p.get("withdrawal_rate", 0.2))
    capital_limit = float(p.get("capital_limit", 16000.0))
    if capital > capital_limit:
        value = 0.0
    else:
        excess = max(0.0, applicable_income - applicable_amount)
        value = max(0.0, liability * max_support - withdrawal * excess)
    return {
        "annual_gbp": round(value, 2),
        "basis": (
            f"max(0, {liability:.0f}·{max_support:g} − {withdrawal:g}·max(0, "
            f"{applicable_income:.0f} − {applicable_amount:.0f})); "
            f"capital {capital:.0f} vs limit {capital_limit:.0f}"
        ),
    }


def build_uk_ctr_report(
    fixtures_dir: str | Path | None = None,
    pe_reference_path: str | Path | None = None,
) -> dict[str, Any]:
    reference = json.loads(
        Path(pe_reference_path or DEFAULT_PE_REFERENCE).read_text()
    )
    pe_cases: dict[str, Any] = reference["cases"]
    params = reference["provenance"].get("ctr_national_scheme_parameters", {})

    captures = load_captures_by_id(fixtures_dir)
    runner = EntitledToRecordedRunner(fixtures_dir)
    cases = uk_ctr_cases()
    results = {r.household_id: r for r in runner.run_cases(cases)}
    comparator = Comparator([_CTR_MAPPING])

    case_rows: list[dict[str, Any]] = []
    captured = 0
    pending = 0
    match_count = 0
    mismatch_count = 0

    for case in cases:
        cid = str(case.case_id)
        meta = case.metadata
        pe = pe_cases.get(cid, {})
        capture = captures.get(cid)
        left = results[cid]
        statutory = _hand_computed_statutory(
            scheme=meta["ctr_scheme"],
            liability=float(pe.get("council_tax", meta["annual_council_tax_liability"])),
            applicable_amount=float(pe.get("applicable_amount", 0.0)),
            applicable_income=float(pe.get("applicable_income", 0.0)),
            capital=float(meta["capital"]),
            params=params,
        )
        is_captured = bool(capture and capture.is_captured)
        entitledto_value = left.values.get("council_tax_reduction") if is_captured else None

        row: dict[str, Any] = {
            "case_id": cid,
            "scenario": meta["scenario"],
            "council_name": meta["local_authority_name"],
            "ctr_scheme": meta["ctr_scheme"],
            "council_tax_liability": round(
                float(pe.get("council_tax", meta["annual_council_tax_liability"])), 2
            ),
            "status": "captured" if is_captured else "pending_capture",
            "entitledto": {
                "status": "captured" if is_captured else "pending_capture",
                "annual_gbp": entitledto_value,
            },
            "policyengine": {
                "annual_gbp": pe.get("council_tax_reduction"),
                "scheme_supported": pe.get("scheme_supported"),
            },
            "hand_computed_statutory": statutory,
        }

        if is_captured:
            captured += 1
            right = EngineResult(
                engine="policyengine",
                household_id=cid,
                values={"council_tax_reduction": pe.get("council_tax_reduction")},
            )
            [comparison] = comparator.compare([left], [right])
            for vc in comparison.comparisons:
                row["entitledto_vs_policyengine"] = {
                    "difference": vc.difference,
                    "match": vc.matches,
                }
                match_count += int(vc.matches)
                mismatch_count += int(not vc.matches)
            if statutory["annual_gbp"] is not None and entitledto_value is not None:
                row["entitledto_vs_statutory"] = {
                    "difference": round(entitledto_value - statutory["annual_gbp"], 2)
                }
        else:
            pending += 1
        case_rows.append(row)

    return {
        "schema_version": SCHEMA_VERSION,
        "suite": "uk-ctr",
        "oracle": "entitledto",
        "concept": CTR_CONCEPT,
        "population": "case-grid",
        "validation_year": int(PERIOD),
        "locales": ["UK"],
        "scope": {"type": "country", "geoid": "UK"},
        "engines": {
            "entitledto": "recorded per-council calculator (council_tax_reduction)",
            "policyengine": "council_tax_reduction",
        },
        "policyengine_reference": reference["provenance"],
        "capture": {
            "status": "captured" if pending == 0 else "pending_capture",
            "captured": captured,
            "pending": pending,
            "protocol": (
                "axiom_oracles/adapters/entitledto/fixtures/uk_ctr/"
                "CAPTURE-PROTOCOL.md"
            ),
        },
        "case_count": len(cases),
        "summary": {
            "comparison_count": match_count + mismatch_count,
            "match_count": match_count,
            "mismatch_count": mismatch_count,
            "pending_count": pending,
        },
        "cases": case_rows,
    }
