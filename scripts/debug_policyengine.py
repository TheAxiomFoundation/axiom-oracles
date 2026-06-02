from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from debug_policyengine_env import ensure_pinned_policyengine_env  # noqa: E402


ensure_pinned_policyengine_env(Path(__file__).resolve(), ROOT)


def _allow_uncertified_policyengine_data() -> None:
    os.environ["POLICYENGINE_SKIP_COUNTRY_IMPORTS"] = "1"
    try:
        import policyengine.provenance.manifest as manifest

        def allow_local_oracle_data(
            country_id, runtime_model_version, runtime_data_build_fingerprint=None
        ):
            return manifest.DataCertification(
                compatibility_basis="axiom_oracle_local_policyengine_us_override",
                certified_for_model_version=runtime_model_version,
                data_build_fingerprint=runtime_data_build_fingerprint,
                certified_by="axiom-oracles debug_policyengine.py",
            )

        manifest.certify_data_release_compatibility = allow_local_oracle_data
        try:
            import policyengine.tax_benefit_models.common.model_version as model_version

            model_version.certify_data_release_compatibility = allow_local_oracle_data
        except ImportError:
            pass
    except ImportError:
        pass
    finally:
        os.environ.pop("POLICYENGINE_SKIP_COUNTRY_IMPORTS", None)


_allow_uncertified_policyengine_data()
try:
    import policyengine
    from policyengine.tax_benefit_models import us as _us

    policyengine.us = _us
except Exception:
    pass

from axiom_oracles.adapters.policyengine.runner import PolicyEngineRunner  # noqa: E402
from axiom_oracles.core.geography import GeographyScope  # noqa: E402
from axiom_oracles.populations.enhanced_cps import load_enhanced_cps_cases  # noqa: E402


DEFAULT_VARIABLES = [
    "is_snap_eligible",
    "snap_normal_allotment",
    "snap_gross_income",
    "snap_gross_income_fpg_ratio",
    "snap_net_income",
    "snap_net_income_fpg_ratio",
    "snap_earned_income",
    "snap_unearned_income",
    "snap_deductions",
    "snap_standard_deduction",
    "snap_earned_income_deduction",
    "snap_excess_shelter_expense_deduction",
    "snap_utility_allowance",
    "snap_utility_allowance_type",
    "snap_fpg",
    "snap_unit_size",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fips", required=True, help="State FIPS, e.g. 37")
    parser.add_argument("--case-ids", nargs="+", required=True)
    parser.add_argument("--sample-size", type=int, default=0)
    parser.add_argument("--variable", action="append", dest="variables")
    args = parser.parse_args(argv)

    cases = load_enhanced_cps_cases(
        period="2026-01",
        sample_size=args.sample_size,
        scope=GeographyScope(type="census_state", geoid=args.fips),
    )
    by_id = {case.case_id: case for case in cases}
    target_cases = [by_id[case_id] for case_id in args.case_ids if case_id in by_id]
    if not target_cases:
        print(f"None of {args.case_ids} found among {len(cases)} cases.")
        return 1

    variables = args.variables or DEFAULT_VARIABLES
    runner = PolicyEngineRunner(batch_size=len(target_cases))
    for case in target_cases:
        print(f"\n=== {case.case_id} ===")
        for variable in variables:
            result = runner.run_cases([case], variables=[variable])[0]
            if result.errors:
                error = result.errors[0] if result.errors else ""
                print(f"  {variable}: ERROR ({error[:120]})")
            else:
                print(f"  {variable}: {result.values.get(variable, '(missing)')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
