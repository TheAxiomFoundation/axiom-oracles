from __future__ import annotations

from ..core.case import Case


FAMILY_MODULE = "ca:policies/cra/benefits-2026/federal-family-and-climate-benefits"
CCB = f"{FAMILY_MODULE}#canada_child_benefit_annual_amount"
CHILD_DISABILITY_BENEFIT = f"{FAMILY_MODULE}#child_disability_benefit_annual_amount"
GROCERIES_AND_ESSENTIALS_BENEFIT = (
    f"{FAMILY_MODULE}#canada_groceries_and_essentials_benefit_annual_amount"
)

CA_SCOPE = {"type": "country", "geoid": "CA"}


def ca_cra_family_benefit_cases() -> list[Case]:
    return [
        _case(
            "ca-cra-family-low-income-two-children",
            adjusted_family_net_income=30_000,
            children=(
                {"name": "Child 1", "date_of_birth": "2018-01-01"},
                {"name": "Child 2", "date_of_birth": "2022-01-01"},
            ),
        ),
        _case(
            "ca-cra-family-ccb-first-phaseout",
            adjusted_family_net_income=45_000,
            children=(
                {"name": "Child 1", "date_of_birth": "2022-01-01"},
            ),
        ),
        _case(
            "ca-cra-family-disabled-child",
            adjusted_family_net_income=90_000,
            children=(
                {
                    "name": "Child 1",
                    "date_of_birth": "2018-01-01",
                    "disabled": True,
                },
            ),
        ),
    ]


def _case(
    case_id: str,
    *,
    adjusted_family_net_income: float,
    children: tuple[dict, ...],
) -> Case:
    under_6 = sum(child["date_of_birth"] > "2020-07-01" for child in children)
    age_6_to_17 = len(children) - under_6
    disabled = sum(bool(child.get("disabled")) for child in children)
    inputs = {
        _input("adjusted_family_net_income"): adjusted_family_net_income,
        _input("ccb_children_under_6_count"): under_6,
        _input("ccb_children_6_to_17_count"): age_6_to_17,
        _input("child_disability_benefit_eligible_child_count"): disabled,
        _input("cgeb_child_count"): len(children),
        _input("cgeb_has_spouse_or_common_law_partner"): False,
        _input("gst_hst_credit_top_up_child_count"): len(children),
        _input("gst_hst_credit_top_up_has_spouse_or_common_law_partner"): False,
        _input("january_2026_gst_hst_credit_payment"): 0,
    }
    return Case(
        case_id=case_id,
        period="2026-07-01",
        outputs=(CCB, CHILD_DISABILITY_BENEFIT, GROCERIES_AND_ESSENTIALS_BENEFIT),
        metadata={
            "locale": "CA-ON",
            "scope": CA_SCOPE,
            "scenario": "cra-child-family-benefits",
            "axiom_entity": "Family",
            "axiom_entity_id": "family",
            "axiom_inputs": inputs,
            "canada_child_family": {
                "tax_year": 2025,
                "province": "ON",
                "marital_status": "SINGLE",
                "applicant_date_of_birth": "1990-01-01",
                "children": list(children),
                "net_income": adjusted_family_net_income,
                "working_income": adjusted_family_net_income,
            },
            "canada_child_family_outputs": {
                "canada_child_benefit": CCB,
                "child_disability_benefit": CHILD_DISABILITY_BENEFIT,
                "canada_groceries_and_essentials_benefit": (
                    GROCERIES_AND_ESSENTIALS_BENEFIT
                ),
            },
        },
    )


def _input(name: str) -> str:
    return f"{FAMILY_MODULE}#input.{name}"
