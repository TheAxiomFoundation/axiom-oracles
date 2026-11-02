"""Project an engine-neutral :class:`Case` into an entitledto calculator input record.

entitledto (https://www.entitledto.co.uk/) is a commercial UK benefits
calculator. Unlike ACCESS NYC it exposes **no** open-source engine or free
programmatic API, and its legal notices prohibit automated data collection
(see ``fixtures/uk_ctr/CAPTURE-PROTOCOL.md``). So this mapper does not *call*
entitledto — it produces the exact, ordered set of inputs a human types into
the public calculator to capture a case, which is also what a recorded fixture
records under ``inputs`` so a reviewer can reproduce (or audit) the capture.

The record is intentionally calculator-shaped (relationship status, where you
live, council tax band/liability, housing, each adult's income, children,
capital) rather than PolicyEngine- or RuleSpec-shaped: it is the manual-entry
projection, the entitledto analogue of ``AccessNycInputMapper.map_case``.
"""

from __future__ import annotations

from typing import Any

from ...core.case import Case, Concepts

# --- Case.metadata keys the UK-CTR suite sets (all flat, YAML-round-trippable
# scalars so the canonical grid extraction round-trips a case exactly). ---
COUNTRY = "country"
CTR_SCHEME = "ctr_scheme"
SCHEME_YEAR = "scheme_year"
CALCULATION_DATE = "calculation_date"
LOCAL_AUTHORITY_NAME = "local_authority_name"
LOCAL_AUTHORITY_GSS_CODE = "local_authority_gss_code"
LOCAL_AUTHORITY_POSTCODE = "local_authority_postcode"
COUNCIL_TAX_BAND = "council_tax_band"
ANNUAL_COUNCIL_TAX_LIABILITY = "annual_council_tax_liability"
TENURE = "tenure"
MONTHLY_RENT = "monthly_rent"
CAPITAL = "capital"
COUPLE = "couple"
PENSION_AGE = "pension_age"
CLAIMANT_EMPLOYMENT_INCOME = "claimant_employment_income"
CLAIMANT_STATE_PENSION = "claimant_state_pension"
CLAIMANT_PRIVATE_PENSION = "claimant_private_pension"
PARTNER_EMPLOYMENT_INCOME = "partner_employment_income"
PARTNER_STATE_PENSION = "partner_state_pension"
PARTNER_PRIVATE_PENSION = "partner_private_pension"

# The tenure vocabulary the record uses (entitledto asks how you pay for your
# home; only renters can be assessed for Housing Benefit, and council tax
# liability is independent of tenure).
TENURE_PRIVATE_RENT = "private_rent"
TENURE_SOCIAL_RENT = "social_rent"
TENURE_OWNER = "owner"
_RENTED_TENURES = frozenset({TENURE_PRIVATE_RENT, TENURE_SOCIAL_RENT})


class EntitledToInputMapper:
    """Map a shared :class:`Case` to an entitledto manual-entry input record."""

    calculator_url = "https://www.entitledto.co.uk/benefits-calculator/"

    def map_case(self, case: Case) -> dict[str, Any]:
        meta = case.metadata
        couple = bool(meta.get(COUPLE, False))
        record: dict[str, Any] = {
            "calculator": "entitledto",
            "calculator_url": self.calculator_url,
            "calculation_date": meta.get(CALCULATION_DATE),
            "scheme_year": meta.get(SCHEME_YEAR),
            "relationship_status": "couple" if couple else "single",
            "country": meta.get(COUNTRY),
            "ctr_scheme": meta.get(CTR_SCHEME),
            "local_authority": {
                "name": meta.get(LOCAL_AUTHORITY_NAME),
                "gss_code": meta.get(LOCAL_AUTHORITY_GSS_CODE),
                # entitledto resolves the billing authority (and its CTR scheme)
                # from a postcode, so this is the field a human actually enters.
                "postcode": meta.get(LOCAL_AUTHORITY_POSTCODE),
            },
            "council_tax": {
                "band": meta.get(COUNCIL_TAX_BAND),
                "annual_liability_gbp": _money(meta.get(ANNUAL_COUNCIL_TAX_LIABILITY)),
            },
            "housing": {
                "tenure": meta.get(TENURE),
                "monthly_rent_gbp": _money(meta.get(MONTHLY_RENT)),
                "assessed_for_rent_rebate": meta.get(TENURE) in _RENTED_TENURES,
            },
            "adults": self._adults(case, couple),
            "children": self._children(case),
            "capital_gbp": _money(meta.get(CAPITAL)),
            # All adult income amounts below are annual GBP, gross (before income
            # tax and National Insurance); entitledto's calculator asks for gross
            # pay and applies its own tax/NI model, so gross is the entry basis.
            "income_basis": "annual GBP, gross (before income tax and National Insurance)",
        }
        return record

    def _adults(self, case: Case, couple: bool) -> list[dict[str, Any]]:
        meta = case.metadata
        # Adults are the non-child people, taken positionally: the first is the
        # claimant, the second the partner. Positional (rather than by relation
        # label) so a case that omits an explicit relation still resolves.
        adult_ages = [
            _age(entity)
            for entity in case.entities_of_kind("person")
            if str(entity.fact(Concepts.HOUSEHOLD_RELATION, "")) != "Child"
        ]
        adults = [
            {
                "role": "claimant",
                "age": adult_ages[0] if adult_ages else None,
                "employment_income_annual_gbp": _money(
                    meta.get(CLAIMANT_EMPLOYMENT_INCOME)
                ),
                "state_pension_annual_gbp": _money(meta.get(CLAIMANT_STATE_PENSION)),
                "private_pension_annual_gbp": _money(
                    meta.get(CLAIMANT_PRIVATE_PENSION)
                ),
            }
        ]
        if couple:
            adults.append(
                {
                    "role": "partner",
                    "age": adult_ages[1] if len(adult_ages) > 1 else None,
                    "employment_income_annual_gbp": _money(
                        meta.get(PARTNER_EMPLOYMENT_INCOME)
                    ),
                    "state_pension_annual_gbp": _money(
                        meta.get(PARTNER_STATE_PENSION)
                    ),
                    "private_pension_annual_gbp": _money(
                        meta.get(PARTNER_PRIVATE_PENSION)
                    ),
                }
            )
        return adults

    @staticmethod
    def _children(case: Case) -> list[dict[str, Any]]:
        return [
            {"age": _age(entity)}
            for entity in case.entities_of_kind("person")
            if str(entity.fact(Concepts.HOUSEHOLD_RELATION, "")) == "Child"
        ]


def _age(entity: Any) -> int | None:
    value = entity.fact(Concepts.PERSON_AGE)
    return int(value) if value is not None else None


def _money(value: Any) -> float | None:
    """Round a monetary input to the penny; pass ``None`` through unchanged."""
    if value is None:
        return None
    return round(float(value), 2)
