"""Per-case gate diagnosis: re-run a single failing comparison case
through Axiom asking for every gate sub-rule, then print which one is
False so we can attribute the failure to a specific gate."""

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
    """Match the local ECPS override used by scripts/run_comparison.py."""
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
                certified_by="axiom-oracles debug_gate.py",
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

from axiom_oracles.populations.populace_us import load_populace_us_cases  # noqa: E402
from axiom_oracles.core.geography import GeographyScope  # noqa: E402
from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner  # noqa: E402
from axiom_oracles.adapters.axiom.generic_inputs import attach_generic_inputs  # noqa: E402


# Fully-qualified output IDs from the compiled program. The engine
# requires absolute refs for derived outputs that originate in imported
# RuleSpec modules; only program-local outputs (e.g. the synthesized
# snap_eligible/snap_eligible_core) accept bare names.
DEFAULT_GATE_OUTPUTS = [
    "snap_eligible",
    "snap_eligible_core",
    "us:regulations/7-cfr/273/3#snap_household_residency_eligible",
    "us-ny:regulations/18-nycrr/387/14/a/5#snap_income_eligible",
    "us:regulations/7-cfr/273/9#snap_standard_income_eligible",
    "us:regulations/7-cfr/273/9#snap_standard_gross_income_eligible",
    "us:regulations/7-cfr/273/9#snap_standard_net_income_eligible",
    "us:regulations/7-cfr/273/8#snap_resource_eligible",
    "us:regulations/7-cfr/273/2/j#snap_regular_categorically_eligible",
    "us-ny:regulations/18-nycrr/387/14/a/5#ny_snap_categorically_eligible",
    # Allotment chain
    "us:regulations/7-cfr/273/10#snap_monthly_allotment",
    "us:regulations/7-cfr/273/10#snap_calculated_monthly_allotment_before_minimums",
    "us:statutes/7/2017/a#snap_allotment_before_minimum",
    "us:regulations/7-cfr/273/9#snap_net_income",
    "us:regulations/7-cfr/273/9#snap_net_income_pre_shelter",
    "us:regulations/7-cfr/273/9#snap_excess_shelter_cost",
    "us:regulations/7-cfr/273/9#snap_standard_deduction",
    "us:regulations/7-cfr/273/9#snap_earned_income_deduction",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiled", required=True, type=Path)
    parser.add_argument("--rulespec-root", required=True, type=Path)
    parser.add_argument("--axiom-binary", required=True, type=Path)
    parser.add_argument("--fips", required=True, help="State FIPS (e.g. 36 for NY)")
    parser.add_argument(
        "--case-ids",
        nargs="+",
        required=True,
        help="ECPS case IDs to debug (e.g. ecps-7371)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=2000,
        help="ECPS sample size to scan for the case IDs",
    )
    parser.add_argument(
        "--output",
        action="append",
        dest="outputs",
        help="Axiom output id to inspect. Repeatable. Defaults to NY SNAP gate diagnostics.",
    )
    args = parser.parse_args(argv)

    cases = load_populace_us_cases(
        period="2026-01",
        sample_size=args.sample_size,
        scope=GeographyScope(type="census_state", geoid=args.fips),
    )
    by_id = {c.case_id: c for c in cases}
    target_cases = [by_id[cid] for cid in args.case_ids if cid in by_id]
    if not target_cases:
        print(f"None of {args.case_ids} found among {len(cases)} cases.")
        return 1

    target_cases = attach_generic_inputs(
        target_cases,
        compiled_program_path=args.compiled,
    )

    runner = AxiomRulesRunner(
        compiled_artifact_path=args.compiled,
        binary_path=args.axiom_binary,
        rulespec_root=args.rulespec_root,
    )
    # Ask one output at a time — different rules may demand different
    # input scopes; asking for all of them in one shot lets a single
    # missing-input error mask values for all other rules.
    for case in target_cases:
        print(f"\n=== {case.case_id} ===", flush=True)
        for output in args.outputs or DEFAULT_GATE_OUTPUTS:
            results = runner.run_cases([case], variables=[output])
            res = results[0]
            if res.errors:
                err = res.errors[0] if res.errors else ""
                print(f"  {output}: ERROR ({err[:80]})", flush=True)
            else:
                value = res.values.get(output, "(missing)")
                print(f"  {output}: {value}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
