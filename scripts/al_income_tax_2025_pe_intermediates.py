"""Run the pe-taxsim PolicyEngine runner (same flags as the #1204 refresh:
assume_w2_wages=True, native SALT) on the 1,155 AL households for 2025 and
append Alabama + federal intermediate variables per tax unit.

Usage (inside the policyengine-taxsim 7d75045 environment, policyengine-us 2.6.17):
    python scripts/al_income_tax_2025_pe_intermediates.py \
        reference/al-income-tax-2025/households.csv pe_intermediates.csv

This produced reference/al-income-tax-2025/pe_intermediates.csv. It needs
policyengine-taxsim installed and is not part of the axiom-oracles environment.
"""

import sys
import pandas as pd
from policyengine_taxsim.runners.policyengine_runner import PolicyEngineRunner

AL_VARS = [
    "al_agi",
    "al_standard_deduction",
    "al_itemized_deductions",
    "al_deductions",
    "al_federal_income_tax_deduction",
    "al_personal_exemption",
    "al_dependent_exemption",
    "al_retirement_exemption",
    "al_taxable_income",
    "al_income_tax_before_non_refundable_credits",
    "al_non_refundable_credits",
    "al_income_tax_before_refundable_credits",
    "al_refundable_credits",
    "al_income_tax",
]
FED_VARS = [
    "adjusted_gross_income",
    "income_tax_before_credits",
    "income_tax_capped_non_refundable_credits",
    "net_investment_income_tax",
    "income_tax_before_refundable_credits",
    "eitc",
    "american_opportunity_credit",
    "refundable_ctc",
    "income_tax_refundable_credits",
    "income_tax",
    "recapture_of_investment_credit",
    "unreported_payroll_tax",
    "qualified_retirement_penalty",
    "tax_unit_taxable_social_security",
    "tax_unit_social_security",
    "taxable_pension_income",
]


class IntermediatesRunner(PolicyEngineRunner):
    def _extract_vectorized_results(self, sim, input_df, rebate_free_sim_factory=None):
        out = super()._extract_vectorized_results(
            sim, input_df, rebate_free_sim_factory
        )
        year = str(int(input_df["year"].iloc[0]))
        extra = {"taxsimid": input_df["taxsimid"].values}
        for v in AL_VARS + FED_VARS:
            try:
                extra["pe_" + v] = self._calc_tax_unit(sim, v, year)
            except Exception as exc:  # variable missing in this pe-us version
                print(f"skip {v}: {exc}", file=sys.stderr)
        ext = pd.DataFrame(extra)
        return out.merge(ext, on="taxsimid", how="left", validate="one_to_one")


if __name__ == "__main__":
    df = pd.read_csv(sys.argv[1])
    df["year"] = 2025
    r = IntermediatesRunner(df, assume_w2_wages=True, disable_salt=False)
    res = r.run(show_progress=False)
    res.to_csv(sys.argv[2], index=False)
    print(res.shape)
