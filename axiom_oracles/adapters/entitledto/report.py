"""Build the UK Council Tax Reduction calculator-oracle report.

Assembles, per suite case, the three CTR figures the oracle compares:

* **entitledto** — the recorded per-council calculator *reference* (entitledto
  publishes estimates, not authoritative awards); ``pending`` until a human
  captures it under entitledto's express permission;
* **PolicyEngine-UK** — the committed 2.89.2 reference value (national schemes +
  five named councils; ``0`` where the council's scheme is unsupported);
* **hand-computed statutory** — the national-scheme formula
  ``max(0, liability - 0.20·max(0, applicable_income - applicable_amount))``
  evaluated on PolicyEngine's own applicable amount / income (so the schemes are
  commensurable, the sibling Axiom-vs-PE grid's convention). It is ``None`` for
  a council's *local* working-age scheme, which needs that council's published
  scheme document (or entitledto) to evaluate.

The builder is fail-closed: every suite case must have exactly one recorded
fixture and one PolicyEngine reference row (missing/extra either side raises,
never a defaulted-to-zero award). While every fixture is ``pending_capture`` the
report grades nothing — it is a truthful "0 captured / 8 pending" artifact. Once
a fixture is captured (and validates), the same builder grades entitledto against
PolicyEngine and the statutory hand-check, reconciled to the council-tax
liability entitledto actually used.

A captured case enters the graded match/mismatch counts only when the pair is
commensurable: PolicyEngine must actually model the council's scheme
(``scheme_supported``), and PolicyEngine's council-tax liability must equal the
liability entitledto derived. A capture failing either condition is reported
descriptively (``captured_not_graded``) with the reason — an unsupported
council's fallback value or a differently-priced liability must never
manufacture a match or a mismatch.
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

# Fields every PolicyEngine reference row must carry (fail-closed: a missing row
# or field raises rather than defaulting an applicable amount/income to zero,
# which would fabricate a full statutory award).
_REQUIRED_PE_FIELDS = (
    "council_tax",
    "council_tax_reduction",
    "scheme_supported",
    "applicable_amount",
    "applicable_income",
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


def _require_bijection(cases: list, pe_cases: dict, captures: dict) -> None:
    ids = {str(c.case_id) for c in cases}
    missing_pe = ids - set(pe_cases)
    extra_pe = set(pe_cases) - ids
    missing_fx = ids - set(captures)
    extra_fx = set(captures) - ids
    problems = []
    if missing_pe:
        problems.append(f"suite cases with no PolicyEngine reference row: {sorted(missing_pe)}")
    if extra_pe:
        problems.append(f"PolicyEngine reference rows with no suite case: {sorted(extra_pe)}")
    if missing_fx:
        problems.append(f"suite cases with no entitledto fixture: {sorted(missing_fx)}")
    if extra_fx:
        problems.append(f"entitledto fixtures with no suite case: {sorted(extra_fx)}")
    for cid, pe in pe_cases.items():
        missing_fields = [f for f in _REQUIRED_PE_FIELDS if f not in pe]
        if missing_fields:
            problems.append(f"PolicyEngine reference {cid} missing {missing_fields}")
    if problems:
        raise ValueError("uk-ctr report inputs are inconsistent: " + "; ".join(problems))


def build_uk_ctr_report(
    fixtures_dir: str | Path | None = None,
    pe_reference_path: str | Path | None = None,
) -> dict[str, Any]:
    reference = json.loads(Path(pe_reference_path or DEFAULT_PE_REFERENCE).read_text())
    pe_cases: dict[str, Any] = reference["cases"]
    params = reference["provenance"].get("ctr_national_scheme_parameters", {})

    captures = load_captures_by_id(fixtures_dir)
    runner = EntitledToRecordedRunner(fixtures_dir)
    cases = uk_ctr_cases()
    _require_bijection(cases, pe_cases, captures)
    results = {r.household_id: r for r in runner.run_cases(cases)}
    comparator = Comparator([_CTR_MAPPING])

    case_rows: list[dict[str, Any]] = []
    captured = 0
    pending = 0
    invalid = 0
    captured_not_graded = 0
    match_count = 0
    mismatch_count = 0

    for case in cases:
        cid = str(case.case_id)
        meta = case.metadata
        pe = pe_cases[cid]
        capture = captures[cid]
        left = results[cid]
        is_captured = capture.is_captured
        claims_captured = capture.capture_status == "captured"

        # Council-tax liability: for a captured case, entitledto derived it from
        # postcode + band (after any single-person discount), so the statutory
        # hand-check is reconciled to that; otherwise the modelled placeholder.
        pe_liability = float(pe["council_tax"])
        if is_captured:
            liability = float(
                capture.provenance["entitledto_council_tax_liability_gbp"]
            )
        else:
            liability = pe_liability

        statutory = _hand_computed_statutory(
            scheme=meta["ctr_scheme"],
            liability=liability,
            applicable_amount=float(pe["applicable_amount"]),
            applicable_income=float(pe["applicable_income"]),
            capital=float(meta["capital"]),
            params=params,
        )

        entitledto_value = left.values.get("council_tax_reduction") if is_captured else None
        if is_captured:
            display_status = "captured"
        elif claims_captured:
            display_status = "invalid_capture"
        else:
            display_status = "pending_capture"

        row: dict[str, Any] = {
            "case_id": cid,
            "scenario": meta["scenario"],
            "council_name": meta["local_authority_name"],
            "ctr_scheme": meta["ctr_scheme"],
            "council_tax_liability": round(liability, 2),
            "status": display_status,
            "entitledto": {
                "status": display_status,
                "annual_gbp": entitledto_value,
                "errors": list(left.errors),
            },
            "policyengine": {
                "annual_gbp": pe["council_tax_reduction"],
                "scheme_supported": pe["scheme_supported"],
                "council_tax_liability": round(pe_liability, 2),
            },
            "hand_computed_statutory": statutory,
        }

        if is_captured:
            captured += 1
            # PolicyEngine was computed at the modelled liability; when the
            # captured entitledto liability differs the two awards are not
            # commensurable (re-run PolicyEngine at the entitledto liability
            # for exact parity).
            parity_match = abs(pe_liability - liability) < 0.01
            row["policyengine_liability_parity"] = {
                "reference_liability": round(pe_liability, 2),
                "entitledto_liability": round(liability, 2),
                "match": parity_match,
            }
            # Grade only commensurable pairs: PolicyEngine must actually model
            # this council's scheme (an unsupported council's value is the
            # constructed-household fallback, not the scheme), and both engines
            # must have priced the same council-tax liability. Everything else
            # is reported descriptively, never as a match or mismatch.
            scheme_supported = bool(pe["scheme_supported"])
            if scheme_supported and parity_match:
                right = EngineResult(
                    engine="policyengine",
                    household_id=cid,
                    values={"council_tax_reduction": pe["council_tax_reduction"]},
                )
                [comparison] = comparator.compare([left], [right])
                for vc in comparison.comparisons:
                    row["entitledto_vs_policyengine"] = {
                        "graded": True,
                        "difference": vc.difference,
                        "match": vc.matches,
                    }
                    match_count += int(vc.matches)
                    mismatch_count += int(not vc.matches)
            else:
                reasons = []
                if not scheme_supported:
                    reasons.append(
                        "policyengine does not model this council's scheme "
                        "(fallback value, not the scheme)"
                    )
                if not parity_match:
                    reasons.append(
                        "policyengine liability differs from the captured "
                        "entitledto liability (re-run PolicyEngine at "
                        f"{round(liability, 2)} for a gradeable pair)"
                    )
                row["entitledto_vs_policyengine"] = {
                    "graded": False,
                    "not_graded_reason": "; ".join(reasons),
                }
                captured_not_graded += 1
            if statutory["annual_gbp"] is not None and entitledto_value is not None:
                row["entitledto_vs_statutory"] = {
                    "difference": round(entitledto_value - statutory["annual_gbp"], 2)
                }
        elif claims_captured:
            invalid += 1
        else:
            pending += 1
        case_rows.append(row)

    graded = match_count + mismatch_count
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
            "entitledto": "recorded per-council calculator reference (council_tax_reduction)",
            "policyengine": "council_tax_reduction",
        },
        "policyengine_reference": reference["provenance"],
        "capture": {
            "status": "captured" if pending == 0 and invalid == 0 else "pending_capture",
            "captured": captured,
            "pending": pending,
            "invalid": invalid,
            "captured_not_graded": captured_not_graded,
            "graded": graded,
            "protocol": (
                "axiom_oracles/adapters/entitledto/fixtures/uk_ctr/CAPTURE-PROTOCOL.md"
            ),
        },
        "case_count": len(cases),
        "summary": {
            "graded_comparison_count": graded,
            "match_count": match_count,
            "mismatch_count": mismatch_count,
            "captured_not_graded_count": captured_not_graded,
            "pending_count": pending,
            "invalid_count": invalid,
            "note": (
                "Nothing is graded until entitledto fixtures are captured; "
                "pending cases are not agreements. A captured case is graded "
                "against PolicyEngine only when PolicyEngine models the "
                "council's scheme and both engines priced the same council-tax "
                "liability; other captures are reported descriptively."
            ),
        },
        "cases": case_rows,
    }
