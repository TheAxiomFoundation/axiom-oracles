"""Ratified NZ IncomeExplorer program/subgraph declarations.

The roots are the RuleSpec outputs the pinned comparison harness actually
requests while computing each program's compared cells.  They are node IDs,
not filename filters: closure follows their transitive RuleSpec dependencies
and collects citations from the reached nodes.
"""

from __future__ import annotations


PROGRAM_VIEWS = {
    "nz/acc-earners-levy": {
        "columns": ("wage1_ACC_levy",),
        "roots": (
            "nz:regulations/acc/earners_levy#acc_standard_earners_levy_including_gst",
        ),
    },
    "nz/accommodation-supplement": {
        "columns": ("AS_Amount",),
        "roots": (
            "nz:statutes/social_security/accommodation_supplement/core#accommodation_supplement_weekly_amount_before_rounding",
            "nz:statutes/social_security/accommodation_supplement/core#accommodation_supplement_rounded_weekly_payment",
            "nz:statutes/social_security/accommodation_supplement/core#accommodation_supplement_weekly_qualifying_accommodation_costs",
        ),
    },
    "nz/income-tax": {
        "columns": ("wage1_tax",),
        "roots": (
            "nz:statutes/income_tax/schedule_1/individual_income_tax#individual_income_tax_before_credits",
        ),
    },
    "nz/independent-earner-tax-credit": {
        "columns": ("IETC_abated",),
        "roots": (
            "nz:statutes/income_tax/credits/individual_credits#independent_earner_tax_credit",
        ),
    },
    "nz/main-benefits": {
        "columns": ("net_benefit",),
        "roots": (
            "nz:statutes/social_security/main_benefits/rates#jobseeker_support_net_weekly_payment",
            "nz:statutes/social_security/main_benefits/rates#sole_parent_support_net_weekly_payment",
        ),
    },
    "nz/winter-energy-payment": {
        "columns": ("WinterEnergy",),
        "roots": (
            "nz:statutes/social_security/winter_energy_payment/core#winter_energy_payment_rate_per_winter_period",
        ),
    },
    "nz/working-for-families": {
        "columns": (
            "FTC_abated",
            "IWTC_abated",
            "MFTC",
            "BestStart_Total",
            "WFF_abated",
        ),
        "roots": (
            "nz:statutes/income_tax/family_scheme/tax_credits#family_tax_credit_after_abatement",
            "nz:statutes/income_tax/family_scheme/tax_credits#in_work_tax_credit_before_abatement",
            "nz:statutes/income_tax/family_scheme/tax_credits#minimum_family_tax_credit",
            "nz:statutes/income_tax/family_scheme/tax_credits#best_start_tax_credit",
            "nz:statutes/income_tax/family_scheme/tax_credits#family_tax_credit_before_abatement",
            "nz:statutes/income_tax/family_scheme/tax_credits#wff_abatement_remaining_after_family_tax_credit",
            "nz:statutes/income_tax/family_scheme/eligibility#entitled_to_in_work_tax_credit",
            "nz:statutes/income_tax/family_scheme/tax_credits#best_start_tax_credit_before_abatement",
            "nz:statutes/income_tax/family_scheme/tax_credits#best_start_credit_abatement",
            "nz:statutes/income_tax/family_scheme/family_scheme_income#family_scheme_income",
        ),
    },
}


# The comparison harness makes one engine request per tuple below.  Keeping
# the request groupings beside the certificate views makes "exact root-set"
# a checkable contract instead of merely checking that the union of roots is
# eventually seen.  Main benefits and Working for Families deliberately use
# two distinct request shapes.
REQUESTED_OUTPUT_ROOT_SETS = {
    view: (tuple(spec["roots"]),) for view, spec in PROGRAM_VIEWS.items()
}
REQUESTED_OUTPUT_ROOT_SETS["nz/main-benefits"] = tuple(
    (root,) for root in PROGRAM_VIEWS["nz/main-benefits"]["roots"]
)
_wff_roots = PROGRAM_VIEWS["nz/working-for-families"]["roots"]
REQUESTED_OUTPUT_ROOT_SETS["nz/working-for-families"] = (
    (_wff_roots[7], _wff_roots[8], _wff_roots[3]),
    (
        _wff_roots[4],
        _wff_roots[0],
        _wff_roots[1],
        _wff_roots[5],
        _wff_roots[6],
        _wff_roots[2],
        _wff_roots[9],
    ),
)
del _wff_roots


# Only ACC's compared cell is a direct function of primary-person earnings.
# Every other view's harness path performs a family/partner/child operation.
SINGLE_PERSON_PROGRAMS = frozenset({"nz/acc-earners-levy"})
