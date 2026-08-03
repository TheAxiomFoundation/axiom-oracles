"""Tests for the conformance harness: schema, universe, scoreboard, ratchets, gates.

Every gate has at least one NEGATIVE test that mutates state and asserts the gate
FAILS — a gate that cannot fail verifies nothing (the vacuous-gate lesson). The
universe backend is exercised against the committed uk.yaml facts and, when a
UKMOD/EUROMOD checkout is present, against the live XML.
"""

from __future__ import annotations

import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[1]
SCRIPTS = REPO_ROOT / "scripts"
CONFORMANCE_DIR = REPO_ROOT / "conformance"

from axiom_oracles.conformance.loader import (  # noqa: E402
    OracleIdentity,
    Universe,
    parse as parse_universe,
    serialize,
)
from axiom_oracles.conformance.ratchet import (  # noqa: E402
    RatchetInvariant,
    check_regressions,
)
from axiom_oracles.conformance.scoreboard import score_jurisdiction  # noqa: E402
from axiom_oracles.conformance.schema import (  # noqa: E402
    EXCLUSION_REASONS,
    UniversePolicy,
)
from axiom_oracles.conformance.universe import (  # noqa: E402
    EuromodUniverseBackend,
    PE_UK_PROGRAM_SPINE,
    PE_US_PROGRAM_SPINE,
    PolicyEngineUniverseBackend,
    YaleTariffUniverseBackend,
    _is_queryable_output,
    parse_r_string_vector,
    propose_scope,
    RawPolicy,
)


def _load_script(name: str):
    module_path = SCRIPTS / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Schema value object
# ---------------------------------------------------------------------------


def _in_scope(**kw) -> UniversePolicy:
    base = dict(
        id="uk:x_uk",
        oracle_policy_name="x_uk",
        output_vars=("x_s",),
        in_scope=True,
        suite="some-suite",
    )
    base.update(kw)
    return UniversePolicy(**base)


def test_unobservable_boundary_is_a_valid_exclusion_reason():
    assert "unobservable_boundary" in EXCLUSION_REASONS


def test_in_scope_row_is_valid_with_output_and_suite():
    assert _in_scope().validate() == []


def test_in_scope_row_may_have_null_suite_uncovered():
    """An in-scope policy with no assigned suite is a valid uncovered state."""
    assert _in_scope(suite=None).validate() == []


def test_in_scope_row_without_output_is_invalid():
    problems = _in_scope(output_vars=()).validate()
    assert any("output_var" in p for p in problems)


def test_extension_not_available_is_a_valid_exclusion_reason():
    assert "extension_not_available" in EXCLUSION_REASONS


def test_extension_not_available_requires_a_note():
    row = UniversePolicy(
        id="be:tco_be",
        oracle_policy_name="tco_be",
        output_vars=(),
        in_scope=False,
        exclusion_reason="extension_not_available",
    )
    assert any("extension_not_available requires a `note`" in p for p in row.validate())
    assert replace(row, note="no CT extension in the public release").validate() == []


def test_oracle_dataset_lacks_input_is_a_valid_exclusion_reason():
    assert "oracle_dataset_lacks_input" in EXCLUSION_REASONS


def _bfapl_row(**kw) -> UniversePolicy:
    """The bfapl_be shape: an observable `_s` surface excluded because its
    activating input is absent from the dataset schema."""
    base = dict(
        id="be:bfapl_be",
        oracle_policy_name="bfapl_be",
        output_vars=("bfapl_s",),
        in_scope=False,
        exclusion_reason="oracle_dataset_lacks_input",
    )
    base.update(kw)
    return UniversePolicy(**base)


def test_oracle_dataset_lacks_input_requires_a_note():
    """The reason is only meaningful with the absent input + probe pointer named."""
    row = _bfapl_row()
    assert any(
        "oracle_dataset_lacks_input requires a `note`" in p for p in row.validate()
    )
    # With a note naming the absent input it validates.
    assert replace(row, note="lpb input absent from BE HHoT schema; see #160").validate() == []


def test_oracle_models_repealed_law_requires_a_note():
    row = UniversePolicy(
        id="us-pe:nh_income_tax",
        oracle_policy_name="nh_income_tax",
        output_vars=("nh_income_tax",),
        in_scope=False,
        exclusion_reason="oracle_models_repealed_law",
    )
    assert any(
        "oracle_models_repealed_law requires a `note`" in problem
        for problem in row.validate()
    )
    assert replace(
        row,
        note="RSA Chapter 77 repealed; see the positive-I&D PolicyEngine probe.",
    ).validate() == []


def test_oracle_models_nonstatutory_amount_requires_a_note():
    row = UniversePolicy(
        id="us-pe:wic",
        oracle_policy_name="wic",
        output_vars=("wic",),
        in_scope=False,
        exclusion_reason="oracle_models_nonstatutory_amount",
    )
    assert any(
        "oracle_models_nonstatutory_amount requires a `note`" in problem
        for problem in row.validate()
    )
    assert replace(
        row,
        note=(
            "7 CFR Part 246 defines the in-kind food package; the oracle amount "
            "is an administratively estimated package value."
        ),
    ).validate() == []


def test_oracle_dataset_lacks_input_keeps_the_observable_output_var():
    """Unlike extension_not_available (no OutputVar), this reason carries a real
    queryable surface — the whole point is the output IS observable, just never
    non-zero. The row must still validate as excluded (an output_var on an
    out-of-scope row is fine; only in-scope rows REQUIRE one)."""
    row = _bfapl_row(note="lpb absent; probe lineage rulespec-be#86 / #150 / #160")
    assert row.output_vars == ("bfapl_s",)
    assert row.in_scope is False
    assert row.validate() == []


def test_mutating_dataset_lacks_input_to_an_unknown_reason_still_fails_validation():
    """NEGATIVE: the closed-enum gate must bite even for a well-formed row — swap
    the (valid) new reason for a typo/unknown one and validation must reject it,
    proving oracle_dataset_lacks_input was admitted by widening the enum, not by
    weakening the check."""
    valid = _bfapl_row(note="lpb absent; #160")
    assert valid.validate() == []
    bogus = replace(valid, exclusion_reason="oracle_dataset_lacks_inputt")  # typo
    problems = bogus.validate()
    assert any("not one of" in p for p in problems)
    assert "oracle_dataset_lacks_input" in ", ".join(problems)  # enum listed in msg


def test_in_scope_comparability_must_be_a_known_kind():
    # Default is full and valid.
    assert _in_scope().comparability == "full"
    # An unknown kind is rejected.
    assert any("comparability" in p for p in _in_scope(comparability="sorta").validate())
    # The documented non-default kinds validate.
    assert _in_scope(comparability="rate_only").validate() == []
    assert _in_scope(comparability="ceiling_only").validate() == []


def test_excluded_row_must_not_set_comparability():
    row = UniversePolicy(
        id="uk:y_uk",
        oracle_policy_name="y_uk",
        output_vars=(),
        in_scope=False,
        exclusion_reason="technical",
        comparability="rate_only",
    )
    assert any("must not set comparability" in p for p in row.validate())


def test_comparability_roundtrips_through_serialize():
    universe = Universe(
        jurisdiction="pe-uk",
        oracle=OracleIdentity("policyengine-uk", "X", "uk", "UK", "policyengine"),
        policies=[
            _in_scope(id="pe-uk:pip", oracle_policy_name="pip", suite=None,
                      comparability="rate_only"),
        ],
    )
    reloaded = parse_universe_from_string(serialize(universe))
    assert reloaded.policies[0].comparability == "rate_only"


def test_out_of_scope_requires_exclusion_reason():
    row = UniversePolicy(
        id="uk:y_uk", oracle_policy_name="y_uk", output_vars=(), in_scope=False
    )
    problems = row.validate()
    assert any("REQUIRE an exclusion_reason" in p for p in problems)


def test_out_of_scope_rejects_unknown_reason():
    row = UniversePolicy(
        id="uk:y_uk",
        oracle_policy_name="y_uk",
        output_vars=(),
        in_scope=False,
        exclusion_reason="because",
    )
    assert any("not one of" in p for p in row.validate())


def test_unobservable_boundary_requires_a_note():
    row = UniversePolicy(
        id="uk:bmu_uk",
        oracle_policy_name="bmu_uk",
        output_vars=("bmu_s",),
        in_scope=False,
        exclusion_reason="unobservable_boundary",
    )
    assert any("requires a `note`" in p for p in row.validate())
    # With a note it validates.
    assert row.validate() and replace(row, note="cited").validate() == []


def test_out_of_scope_must_not_name_a_suite():
    row = UniversePolicy(
        id="uk:y_uk",
        oracle_policy_name="y_uk",
        output_vars=(),
        in_scope=False,
        exclusion_reason="technical",
        suite="ghost",
    )
    assert any("must not name a `suite`" in p for p in row.validate())


def test_in_scope_row_rejects_exclusion_reason():
    problems = _in_scope(exclusion_reason="technical").validate()
    assert any("must not carry an exclusion_reason" in p for p in problems)


# ---------------------------------------------------------------------------
# Universe classification heuristics + queryability shape
# ---------------------------------------------------------------------------


def test_queryable_output_shape():
    assert _is_queryable_output("bmu_s") is True
    assert _is_queryable_output("tin_s") is True
    # i_-locals and tot_ aggregates are not queryable comparison surfaces.
    assert _is_queryable_output("i_bmu_prelimAmt") is False
    assert _is_queryable_output("tot_eligOwn") is False
    # bare non-_s is not an output surface.
    assert _is_queryable_output("dhr") is False


def test_propose_scope_defaults_are_conservative():
    # A policy with a queryable output is proposed in-scope (suite unset →
    # invalid until a reviewer names it, so it can't pass vacuously).
    in_scope, reason = propose_scope(
        RawPolicy("bx_uk", "ben", "on", ("bx_s",), ("bx_s",), ())
    )
    assert in_scope is True and reason is None
    # A def block with no queryable output → technical.
    in_scope, reason = propose_scope(
        RawPolicy("Uprate_uk", "def", "on", (), (), ())
    )
    assert in_scope is False and reason == "technical"
    # A ben policy with no queryable output → unobservable_boundary (a human
    # must look, not default to covered).
    in_scope, reason = propose_scope(
        RawPolicy("bz_uk", "ben", "on", ("i_z",), (), ("i_z",))
    )
    assert in_scope is False and reason == "unobservable_boundary"


# ---------------------------------------------------------------------------
# Committed universe integrity (UK + BE)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "jurisdiction", ["uk", "be", "uk-pe", "us-pe", "us-tariff-yale"]
)
def test_committed_universe_parses_and_validates(jurisdiction):
    path = CONFORMANCE_DIR / f"{jurisdiction}.yaml"
    universe = parse_universe(path)
    assert universe.validate() == []
    # Every out-of-scope row carries a known reason.
    for policy in universe.excluded():
        assert policy.exclusion_reason in EXCLUSION_REASONS


def test_uk_universe_flags_bmu_unobservable_with_citation():
    universe = parse_universe(CONFORMANCE_DIR / "uk.yaml")
    bmu = universe.by_name()["bmu_uk"]
    assert bmu.in_scope is False
    assert bmu.exclusion_reason == "unobservable_boundary"
    assert bmu.note and "2.5.6" in bmu.note
    # The i_-local boundary variables are recorded as internal-only evidence.
    assert "i_bmu_prelimAmt" in bmu.internal_only_vars
    assert "i_bmu_Deductions2" in bmu.internal_only_vars


def test_uk_universe_has_takeup_exclusion():
    universe = parse_universe(CONFORMANCE_DIR / "uk.yaml")
    reasons = {p.exclusion_reason for p in universe.excluded()}
    assert "takeup_adjustment" in reasons


def test_be_universe_marks_tco_extension_not_available():
    """tco_be is definitional-only with no consumption-tax extension present."""
    universe = parse_universe(CONFORMANCE_DIR / "be.yaml")
    tco = universe.by_name()["tco_be"]
    assert tco.in_scope is False
    assert tco.exclusion_reason == "extension_not_available"
    assert tco.note and "extension" in tco.note.lower()


def test_be_universe_excludes_bfapl_dataset_lacks_input_with_probe_pointer():
    """bfapl_be simulates + writes bfapl_s but the lpb activating input is absent
    from the BE HHoT demo schema, so it is excluded as oracle_dataset_lacks_input
    with the probe evidence pointer recorded in its note."""
    universe = parse_universe(CONFORMANCE_DIR / "be.yaml")
    bfapl = universe.by_name()["bfapl_be"]
    assert bfapl.in_scope is False
    assert bfapl.exclusion_reason == "oracle_dataset_lacks_input"
    # The observable surface is retained (the reason's defining property).
    assert "bfapl_s" in bfapl.output_vars
    # The note names the absent input and the probe lineage.
    assert bfapl.note is not None
    assert "lpb" in bfapl.note
    assert "rulespec-be#86" in bfapl.note


def test_uk_universe_excludes_nonstatutory_amount_rows():
    """bhosc01 (discretionary DHP), bched02 (administrative clothing-grant minimum)
    and bched01 (in-kind Free School Meals) each compute a payable ``_s`` output
    whose monetary value has no statutory basis, so they are excluded as
    oracle_models_nonstatutory_amount with the governing instrument in the note and
    the observable output surface retained (the reason's defining property)."""
    universe = parse_universe(CONFORMANCE_DIR / "uk.yaml")
    by_name = universe.by_name()
    for name, out_var, source_marker in (
        ("bhosc01_uk", "bhosc01_s", "2001/1167"),
        ("bched02_uk", "bched02_s", "s.54"),
        ("bched01_uk", "bched01_s", "s.53"),
    ):
        row = by_name[name]
        assert row.in_scope is False, name
        assert row.exclusion_reason == "oracle_models_nonstatutory_amount", name
        assert out_var in row.output_vars, name
        assert row.note is not None and source_marker in row.note, name


# ---------------------------------------------------------------------------
# Committed pe-uk universe (PolicyEngine-UK oracle)
# ---------------------------------------------------------------------------


def test_uk_pe_universe_is_policyengine_backed_and_version_pinned():
    """The pe-uk universe is defined against a pinned policyengine-uk version, so
    a conformance claim is scoped to one release, not a floating latest."""
    universe = parse_universe(CONFORMANCE_DIR / "uk-pe.yaml")
    assert universe.jurisdiction == "uk-pe"
    assert universe.oracle.backend == "policyengine"
    assert universe.oracle.model == "policyengine-uk"
    # release is a real pinned semver (e.g. 2.89.2), never the placeholder.
    assert universe.oracle.release not in {"", "TODO", "checkout"}
    assert universe.oracle.release[0].isdigit()
    assert universe.validate() == []


def test_uk_pe_rate_from_category_programs_carry_rate_only_comparability():
    """PIP/DLA apply a rate table over a frozen *_category input, so they are
    in-scope but comparable on rates only — the note records the standard."""
    universe = parse_universe(CONFORMANCE_DIR / "uk-pe.yaml")
    by_name = universe.by_name()
    for program in ("pip", "dla"):
        row = by_name[program]
        assert row.in_scope is True
        assert row.comparability == "rate_only"
        assert row.note and "rates-given-category" in row.note


def test_uk_pe_reported_ceiling_and_pure_input_excluded_as_input_carrying():
    """The reported-ceiling and pure-input passthroughs (no statutory surface a
    comparison can bind) are excluded with input_carrying + a per-row note."""
    universe = parse_universe(CONFORMANCE_DIR / "uk-pe.yaml")
    by_name = universe.by_name()
    for program in (
        "council_tax",
        "stamp_duty_land_tax",
        "esa_contrib",
        "incapacity_benefit",
        "council_tax_benefit",
        "esa_income",
        "sda",
        "ssmg",
    ):
        row = by_name[program]
        assert row.in_scope is False, program
        assert row.exclusion_reason == "input_carrying", program
        assert row.note, f"{program} needs a per-row note"


def test_uk_pe_council_tax_reduction_is_in_scope_on_this_pin():
    """council_tax_reduction gained a formula in the pinned policyengine-uk, so it
    is an in-scope (uncovered) program — the matrix's PE-side ambiguity resolved."""
    universe = parse_universe(CONFORMANCE_DIR / "uk-pe.yaml")
    ctr = universe.by_name()["council_tax_reduction"]
    assert ctr.in_scope is True
    assert ctr.exclusion_reason is None
    assert "council_tax_reduction" in ctr.output_vars


def test_uk_pe_covered_programs_name_a_live_pe_suite():
    """Every covered program points at a live PolicyEngine-UK suite.

    Two are population EFRS suites (uk-tax-benefits-efrs, uk-universal-credit-efrs);
    uk-council-tax-reduction is a synthetic pensioner case-grid comparing the
    SI 2012/2885 England pension-age scheme against PE-UK's council_tax_reduction
    (present from 2.89.2); uk-winter-fuel-payment-pe is a synthetic pensioner
    case-grid comparing the SI 2025/969 England-and-Wales Winter Fuel award pipeline
    against PE-UK's winter_fuel_allowance (the 2024/25 means-tested restriction).
    """
    universe = parse_universe(CONFORMANCE_DIR / "uk-pe.yaml")
    live_pe_suites = {
        "uk-tax-benefits-efrs",
        "uk-universal-credit-efrs",
        "uk-council-tax-reduction",
        "uk-winter-fuel-payment-pe",
        "uk-capital-gains-tax",
        "uk-business-rates",
        "uk-attendance-allowance-pe",
        "uk-tax-free-childcare-pe",
        "uk-vat",
        "uk-fuel-duty",
        "uk-tv-licence",
        "uk-lbtt-ltt",
    }
    covered_suites = {
        p.suite for p in universe.in_scope() if p.suite is not None
    }
    assert covered_suites <= live_pe_suites
    # The task's named covered additions are all present and suite-bound.
    by_name = universe.by_name()
    for program in (
        "income_tax",
        "national_insurance",
        "universal_credit",
        "housing_benefit",
        "pip",
        "dla",
        "marriage_allowance",
        "carers_allowance",
        "carer_support_payment",
    ):
        assert by_name[program].suite in {
            "uk-tax-benefits-efrs",
            "uk-universal-credit-efrs",
        }, program
    # Council Tax Reduction is covered by its case-grid suite.
    assert by_name["council_tax_reduction"].suite == "uk-council-tax-reduction"
    # Winter Fuel Payment is covered by its case-grid suite.
    assert (
        by_name["winter_fuel_allowance"].suite == "uk-winter-fuel-payment-pe"
    )
    # Attendance Allowance is covered by its rate-only case-grid suite.
    assert (
        by_name["attendance_allowance"].suite == "uk-attendance-allowance-pe"
    )
    # Tax-Free Childcare is covered by its below-cap top-up case-grid suite.
    assert (
        by_name["tax_free_childcare"].suite == "uk-tax-free-childcare-pe"
    )


# ---------------------------------------------------------------------------
# us-pe universe (PolicyEngine-US backed, per-state granularity)
# ---------------------------------------------------------------------------


def test_us_pe_spine_is_well_formed():
    """The committed US grouping (row set / badge denominator) is deterministic:
    unique program names, each keyed on at least one output variable."""
    names = [p.name for p in PE_US_PROGRAM_SPINE]
    assert len(names) == len(set(names)), "duplicate program names in the spine"
    assert all(p.outputs for p in PE_US_PROGRAM_SPINE)
    # The spine is large and honest (per-state income tax + TANF dominate).
    assert len(PE_US_PROGRAM_SPINE) >= 100


def test_us_pe_universe_is_policyengine_backed_and_version_pinned():
    """us-pe is scoped to one pinned policyengine-us release, not a floating
    latest (the header pins from the enumerated checkout)."""
    universe = parse_universe(CONFORMANCE_DIR / "us-pe.yaml")
    assert universe.jurisdiction == "us-pe"
    assert universe.oracle.backend == "policyengine"
    assert universe.oracle.model == "policyengine-us"
    assert universe.oracle.release not in {"", "TODO", "checkout"}
    assert universe.oracle.release[0].isdigit()
    assert universe.validate() == []


def test_us_pe_input_carried_programs_are_excluded():
    """Reported income PE-US only carries (no statutory computation) is excluded
    input_carrying; the reform-only basic_income lever is technical — the PE-US
    analogue of the uk-pe reported-passthrough exclusions."""
    universe = parse_universe(CONFORMANCE_DIR / "us-pe.yaml")
    by_name = universe.by_name()
    for program in (
        "social_security",
        "unemployment_compensation",
        "child_support_received",
        "workers_compensation",
        "educational_assistance",
        "financial_assistance",
        "survivor_benefits",
    ):
        row = by_name[program]
        assert row.in_scope is False, program
        assert row.exclusion_reason == "input_carrying", program
    assert by_name["basic_income"].exclusion_reason == "technical"


def test_us_pe_state_programs_are_per_state():
    """State income tax and TANF are one row PER STATE — mirroring PE-US's own
    per-state variable tree (<state>_income_tax, STATE_TANF_VARIABLES), not
    collapsed to a single national row. SNAP/SSI stay national (one PE variable)."""
    import re

    universe = parse_universe(CONFORMANCE_DIR / "us-pe.yaml")
    by_name = universe.by_name()
    # Per-state income tax rows are keyed <2-letter-state>_income_tax.
    state_iit = [n for n in by_name if re.fullmatch(r"[a-z]{2}_income_tax", n)]
    assert len(state_iit) == 44  # states PE computes an income tax for
    # A representative sample of per-state TANF programs (varied names).
    for tanf in ("ca_tanf", "ny_tanf", "mn_mfip", "ak_atap", "ma_tafdc", "wy_power"):
        assert tanf in by_name, tanf
        assert by_name[tanf].in_scope is True
    # SNAP and SSI are single national rows keyed on their national variable.
    assert "snap" in by_name["snap"].output_vars
    assert "ssi" in by_name["ssi"].output_vars


def test_us_pe_covered_programs_name_a_live_pe_suite():
    """Every covered us-pe program points at a live PolicyEngine-US suite that
    runs vs PE-2026 — the day-one registrations (federal income tax + payroll via
    fiit-ecps, SSI, SNAP, Medicaid categorical, reviewed state income-tax
    comparisons, and the per-state TANF suites)."""
    import re

    universe = parse_universe(CONFORMANCE_DIR / "us-pe.yaml")
    live_pe_suites = {
        "fiit-ecps",
        "ssi-ecps",
        "ca-snap-ecps",
        "medicaid-magi-co-ecps",
        "nc-income-tax-liability",
        "ms-income-tax-liability",
        "al-tanf-ecps",
        "ga-tanf-ecps",
        "de-tanf-ecps",
        "az-tanf-ecps",
        "ca-tanf-ecps",
        "co-tanf-ecps",
        "ks-tanf-ecps",
        "mn-tanf-ecps",
        "ny-tanf-ecps",
        "wa-tanf-ecps",
        "us-aca-ptc-grid",
        "us-additional-medicare-grid",
        "us-elderly-disabled-grid",
        "us-llc-grid",
        "us-niit-grid",
        "us-qbid-grid",
        "us-savers-grid",
        "us-seca-grid",
        "us-salt-deduction-grid",
        "us-itemized-taxable-income-deductions-grid",
    }
    covered = {p.suite for p in universe.in_scope() if p.suite is not None}
    assert covered <= live_pe_suites
    by_name = universe.by_name()
    # Federal income tax + payroll ride the fiit-ecps bridge.
    for program in ("income_tax", "eitc", "ctc", "employee_social_security_tax"):
        assert by_name[program].suite == "fiit-ecps", program
    # SNAP is one national row registered to its canonical (largest) suite.
    assert by_name["snap"].suite == "ca-snap-ecps"
    assert by_name["aca_ptc"].suite == "us-aca-ptc-grid"
    assert (
        by_name["additional_medicare_tax"].suite
        == "us-additional-medicare-grid"
    )
    assert (
        by_name["elderly_disabled_credit"].suite
        == "us-elderly-disabled-grid"
    )
    assert by_name["lifetime_learning_credit"].suite == "us-llc-grid"
    assert by_name["net_investment_income_tax"].suite == "us-niit-grid"
    assert (
        by_name["qualified_business_income_deduction"].suite
        == "us-qbid-grid"
    )
    assert (
        by_name["itemized_taxable_income_deductions"].suite
        == "us-itemized-taxable-income-deductions-grid"
    )
    assert (
        "all five filing statuses"
        in by_name["itemized_taxable_income_deductions"].note
    )
    assert by_name["salt_deduction"].suite == "us-salt-deduction-grid"
    assert "all five filing statuses" in by_name["salt_deduction"].note
    chunk_one_suites = {
        "us-salt-deduction-grid",
        "us-itemized-taxable-income-deductions-grid",
    }
    assert {
        row.oracle_policy_name: row.suite
        for row in universe.in_scope()
        if row.suite in chunk_one_suites
    } == {
        "salt_deduction": "us-salt-deduction-grid",
        "itemized_taxable_income_deductions": (
            "us-itemized-taxable-income-deductions-grid"
        ),
    }
    assert {
        name: by_name[name].suite
        for name in (
            "alternative_minimum_tax",
            "foreign_tax_credit",
            "taxable_income",
        )
    } == {
        "alternative_minimum_tax": None,
        "foreign_tax_credit": None,
        "taxable_income": None,
    }
    assert by_name["savers_credit"].suite == "us-savers-grid"
    assert "34 fixture-bound" in by_name["savers_credit"].note
    assert "reviewed direct PE-US target" in by_name["savers_credit"].note
    assert "23/34" in by_name["savers_credit"].note
    assert "policyengine-us/issues/9151" in by_name["savers_credit"].note
    assert by_name["self_employment_tax"].suite == "us-seca-grid"
    # State income-tax coverage counts only a comparison that proves the final
    # public variable. These blocked grids exercise useful narrower components,
    # but none proves the corresponding final liability.
    assert by_name["co_income_tax"].suite is None
    assert by_name["ny_income_tax"].suite is None
    nh_income_tax = by_name["nh_income_tax"]
    assert nh_income_tax.in_scope is False
    assert nh_income_tax.exclusion_reason == "oracle_models_repealed_law"
    assert nh_income_tax.suite is None
    assert nh_income_tax.note
    assert "probe_us_nh_repealed_income_tax.py" in nh_income_tax.note
    narrow_state_targets = {
        "al_income_tax": "al_income_tax_before_non_refundable_credits",
        "az_income_tax": "az_income_tax_before_non_refundable_credits",
        "ca_income_tax": "ca_income_tax_before_refundable_credits",
        "dc_income_tax": "dc_income_tax_before_credits",
        "de_income_tax": "de_income_tax_before_non_refundable_credits_indv",
        "ga_income_tax": "ga_income_tax_before_non_refundable_credits",
        "hi_income_tax": "hi_income_tax_before_non_refundable_credits",
        "ia_income_tax": "ia_income_tax_before_credits",
        "id_income_tax": "id_income_tax_before_refundable_credits",
        "il_income_tax": "il_income_tax_before_non_refundable_credits",
        "in_income_tax": "in_agi_tax",
        "ks_income_tax": "ks_income_tax_before_credits",
        "ky_income_tax": "ky_income_tax_before_non_refundable_credits_unit",
        "la_income_tax": "la_income_tax_before_non_refundable_credits",
        "ma_income_tax": "ma_income_tax",
        "md_income_tax": "md_income_tax_before_credits",
        "me_income_tax": "me_income_tax_before_refundable_credits",
        "mi_income_tax": "mi_income_tax_before_non_refundable_credits",
        "mn_income_tax": "mn_income_tax_before_refundable_credits",
        "mo_income_tax": "mo_income_tax_before_credits",
        "mt_income_tax": "mt_income_tax_before_non_refundable_credits_joint",
        "nd_income_tax": "nd_income_tax_before_credits",
        "ne_income_tax": "ne_income_tax_before_credits",
        "nj_income_tax": "nj_main_income_tax",
        "nm_income_tax": "nm_income_tax_before_non_refundable_credits",
        "oh_income_tax": "oh_income_tax_before_non_refundable_credits",
        "ok_income_tax": "ok_income_tax_before_credits",
        "or_income_tax": "or_income_tax_before_credits",
        "pa_income_tax": "pa_income_tax_before_forgiveness",
        "ri_income_tax": "ri_income_tax_before_non_refundable_credits",
        "sc_income_tax": "sc_income_tax_before_non_refundable_credits",
        "ut_income_tax": "ut_income_tax_before_credits",
        "va_income_tax": "va_income_tax_before_non_refundable_credits",
        "vt_income_tax": "vt_income_tax_before_non_refundable_credits",
        "wa_income_tax": "wa_income_tax_before_refundable_credits",
        "wi_income_tax": "wi_income_tax_before_credits",
        "wv_income_tax": "wv_income_tax_before_non_refundable_credits",
    }
    for final_variable, compared_surface in narrow_state_targets.items():
        row = by_name[final_variable]
        assert row.in_scope is True, final_variable
        assert row.suite is None, final_variable
        assert compared_surface in row.note, final_variable
    ct_income_tax = by_name["ct_income_tax"]
    assert ct_income_tax.in_scope is True
    assert ct_income_tax.suite is None
    assert "ordinary section 12-700 tax before the personal credit" in (
        ct_income_tax.note
    )
    assert "final ct_income_tax" in ct_income_tax.note
    # North Carolina is the reviewed 2026 exception whose narrower target
    # is provably identical to the generated final variable over every
    # positive-weight routed Populace tax unit. Alabama and Connecticut
    # deliberately are not promoted from their narrower component comparisons
    # to final liability.
    final_equivalent_state_targets = {
        "nc_income_tax": ("nc_income_tax_before_credits", "2,169"),
    }
    for final_variable, (compared_surface, population_count) in (
        final_equivalent_state_targets.items()
    ):
        row = by_name[final_variable]
        assert row.suite == f"{final_variable[:2]}-income-tax-liability"
        assert compared_surface in row.note
        assert population_count in row.note
    covered_state_income_taxes = {
        variable
        for variable, row in by_name.items()
        if re.fullmatch(r"[a-z]{2}_income_tax", variable) and row.suite is not None
    }
    assert covered_state_income_taxes == set(final_equivalent_state_targets)
    # Per-state TANF suites bind their state's variable (incl. renamed ones).
    assert by_name["mn_mfip"].suite == "mn-tanf-ecps"


def test_us_pe_tier3_scope_decisions_are_evidence_backed():
    universe = parse_universe(CONFORMANCE_DIR / "us-pe.yaml")
    by_name = universe.by_name()

    credit_25c = by_name["energy_efficient_home_improvement_credit"]
    assert credit_25c.in_scope is False
    assert credit_25c.exclusion_reason == "oracle_models_repealed_law"
    assert credit_25c.suite is None
    assert credit_25c.note
    assert "scripts/probe_us_ira_2026.py" in credit_25c.note

    spm_cap = by_name["spm_unit_capped_housing_subsidy"]
    assert spm_cap.in_scope is False
    assert spm_cap.exclusion_reason == "technical"
    assert spm_cap.suite is None
    assert spm_cap.note
    assert "hud_hap" in spm_cap.note
    assert "scripts/probe_us_ira_2026.py" in spm_cap.note

    held_rows = (
        "residential_clean_energy_credit",
        "new_clean_vehicle_credit",
        "used_clean_vehicle_credit",
        "high_efficiency_electric_home_rebate",
        "residential_efficiency_electrification_rebate",
    )
    for name in held_rows:
        assert by_name[name].in_scope is True
        assert by_name[name].exclusion_reason is None
        assert by_name[name].suite is None


def test_us_pe_nonstatutory_amount_rows_name_mechanism_and_eligibility():
    universe = parse_universe(CONFORMANCE_DIR / "us-pe.yaml")
    by_name = universe.by_name()
    expected = {
        "wic": ("gov.usda.wic.value", "is_wic_eligible"),
        "free_school_meals": (
            "gov.usda.school_meals.amount.nslp",
            "school_meal_tier",
        ),
        "reduced_price_school_meals": (
            "gov.usda.school_meals.amount.nslp",
            "school_meal_tier",
        ),
        "chip": (
            "calibration.gov.hhs.cms.chip.spending.separate_chip.total",
            "is_chip_eligible",
        ),
        "head_start": (
            "gov.hhs.head_start.spending",
            "is_head_start_eligible",
        ),
        "early_head_start": (
            "gov.hhs.head_start.early_head_start.spending",
            "is_early_head_start_eligible",
        ),
        "commodity_supplemental_food_program": (
            "gov.usda.csfp.amount",
            "commodity_supplemental_food_program_eligible",
        ),
    }

    excluded = {
        name
        for name, row in by_name.items()
        if row.exclusion_reason == "oracle_models_nonstatutory_amount"
    }
    assert excluded == set(expected)

    for name, (mechanism_path, eligibility_surface) in expected.items():
        row = by_name[name]
        assert row.output_vars == (name,)
        assert row.in_scope is False
        assert row.suite is None
        assert row.note is not None
        assert "PolicyEngine-US 1.767.3" in row.note
        assert mechanism_path in row.note
        assert eligibility_surface in row.note
        assert "compared separately" in row.note


def test_serialize_is_stable_roundtrip():
    universe = parse_universe(CONFORMANCE_DIR / "uk.yaml")
    once = serialize(universe)
    twice = serialize(parse_universe_from_string(once))
    assert once == twice


def parse_universe_from_string(text: str) -> Universe:
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        fh.write(text)
        name = fh.name
    return parse_universe(name)


# ---------------------------------------------------------------------------
# Live UKMOD XML backend (skipped when the checkout is absent)
# ---------------------------------------------------------------------------

_UKMOD_ROOT = Path.home() / "Downloads" / "UKMOD_PUBLIC_B2026.03"


@pytest.mark.skipif(
    not (_UKMOD_ROOT / "XMLParam").exists(),
    reason="UKMOD checkout not present on this runner",
)
def test_ukmod_backend_enumerates_bmu_with_internal_boundary():
    backend = EuromodUniverseBackend(_UKMOD_ROOT, country="UK", system="UK_2026")
    by_name = {p.name: p for p in backend.raw_policies()}
    # 67 policies in UK_2026.
    assert len(by_name) == 67
    bmu = by_name["bmu_uk"]
    # bmu_s and ymn01_s ARE queryable; the applicable-amount/deduction locals are NOT.
    assert "bmu_s" in bmu.queryable_outputs
    assert "ymn01_s" in bmu.queryable_outputs
    assert "i_bmu_prelimAmt" in bmu.internal_outputs
    assert "i_bmu_Deductions2" in bmu.internal_outputs


@pytest.mark.skipif(
    not (_UKMOD_ROOT / "XMLParam").exists(),
    reason="UKMOD checkout not present on this runner",
)
def test_ukmod_generated_facts_match_committed_universe():
    """The committed uk.yaml facts must equal a fresh generation (no drift)."""
    gen = _load_script("generate_conformance_universe.py")
    universe = gen.generate_universe("uk", _UKMOD_ROOT)
    committed = parse_universe(CONFORMANCE_DIR / "uk.yaml")
    assert serialize(universe) == serialize(committed)


# ---------------------------------------------------------------------------
# Yale tariff-rate-tracker backend (R-literal parser + committed universe)
# ---------------------------------------------------------------------------

_YALE_ROOT = Path.home() / "TheAxiomFoundation" / "_tariff-yale"


def test_parse_r_string_vector_reads_literals_na_and_integers():
    source = """
    rate_col = c('rate_232', "rate_301", NA),
    panel_order = c(1L, 2L, NA),
    """
    assert parse_r_string_vector(source, "rate_col") == [
        "rate_232",
        "rate_301",
        None,
    ]
    assert parse_r_string_vector(source, "panel_order") == ["1", "2", None]


def test_parse_r_string_vector_rejects_spliced_expressions():
    """A spliced expression inside c(...) must raise: a universe fact has to be
    a literal the parse can pin, never something re-derived by memory."""
    source = "rate_col = c('rate_232', registry$rate_col[schema_group == 'x'])"
    with pytest.raises(ValueError, match="non-literal"):
        parse_r_string_vector(source, "rate_col")


def test_parse_r_string_vector_raises_on_missing_vector():
    with pytest.raises(ValueError, match="not found"):
        parse_r_string_vector("other = c('a')", "rate_col")


def test_us_tariff_yale_universe_pin_matches_reference_provenance():
    """The universe's oracle release must equal the committed reference
    extract's yale_commit — one pin for both surfaces, so a divergent
    universe/extract pair cannot pass silently."""
    universe = parse_universe(CONFORMANCE_DIR / "us-tariff-yale.yaml")
    assert universe.oracle.backend == "yale-tariff"
    assert universe.oracle.model == "tariff-rate-tracker"
    provenance = json.loads(
        (
            REPO_ROOT / "reference" / "us-tariff-panel" / "yale_panel_provenance.json"
        ).read_text()
    )
    assert universe.oracle.release == provenance["yale_commit"]


def test_us_tariff_yale_scope_decisions():
    """10 statutory-surface rows in scope on the us-tariff-panel suite, each
    with a note. Four rows are excluded as technical: the Swiss framework
    metadata and stacking/framing outputs (effective-layer machinery, no
    statutory surface), plus the two authority columns the reference never
    exercises with a nonzero rate at pin c4307e51 (other, rate_301_cs) —
    each of those carries an explicit re-inclusion tripwire keyed to the
    suite's per-refresh column_exposure derivation."""
    universe = parse_universe(CONFORMANCE_DIR / "us-tariff-yale.yaml")
    in_scope = [p for p in universe.policies if p.in_scope]
    excluded = universe.excluded()
    assert len(in_scope) == 10
    for row in in_scope:
        assert row.suite == "us-tariff-panel", row.oracle_policy_name
        assert row.note, row.oracle_policy_name
        # Every in-scope surface is a statutory_* column (pre-exemption,
        # pre-stacking) — the comparison boundary the suite binds.
        assert all(
            v.startswith("statutory_") for v in row.output_vars
        ), row.oracle_policy_name
    assert {p.oracle_policy_name for p in excluded} == {
        "swiss_framework",
        "stacking_outputs",
        "other",
        "rate_301_cs",
    }
    for row in excluded:
        assert row.exclusion_reason == "technical"
        assert row.note, row.oracle_policy_name
    # The zero-exposure exclusions must state their re-inclusion tripwire —
    # narrowing the universe without one is the failure mode the sol stack
    # review's F3 witness gate exists to prevent.
    for name in ("other", "rate_301_cs"):
        row = next(p for p in excluded if p.oracle_policy_name == name)
        assert "tripwire" in row.note, name
        assert "column_exposure" in row.note, name


@pytest.mark.skipif(
    not (_YALE_ROOT / "src" / "model" / "authority_registry.R").exists(),
    reason="Yale tariff-rate-tracker checkout not present on this runner",
)
def test_yale_generated_facts_match_committed_universe():
    """The committed us-tariff-yale.yaml facts must equal a fresh generation
    from the pinned checkout (no drift)."""
    backend = YaleTariffUniverseBackend(_YALE_ROOT)
    if backend.pinned_commit() != parse_universe(
        CONFORMANCE_DIR / "us-tariff-yale.yaml"
    ).oracle.release:
        pytest.skip("local Yale checkout is not at the pinned commit")
    gen = _load_script("generate_conformance_universe.py")
    universe = gen.generate_universe("us-tariff-yale", _YALE_ROOT)
    committed = parse_universe(CONFORMANCE_DIR / "us-tariff-yale.yaml")
    assert serialize(universe) == serialize(committed)


# ---------------------------------------------------------------------------
# Live policyengine-uk backend (skipped when the package is not importable)
# ---------------------------------------------------------------------------


def _policyengine_uk_checkout():
    """A checkout root to enumerate from: the package's own install dir's parent
    (its repo root), which carries pyproject.toml alongside the package."""
    import policyengine_uk  # type: ignore

    return Path(policyengine_uk.__file__).resolve().parents[1]


def _importable_pe_uk_matches_pin() -> bool:
    """True only when policyengine_uk is importable AND its version equals the
    committed uk-pe universe's pinned release. The spine is pinned to that exact
    version (variables are added/removed across releases — e.g.
    council_tax_reduction gained a formula after 2.88.52), so enumerating against
    a different importable copy is a version mismatch, not a test target. Same
    version-gating the drift --check applies."""
    import importlib.util

    if importlib.util.find_spec("policyengine_uk") is None:
        return False
    try:
        pinned = parse_universe(CONFORMANCE_DIR / "uk-pe.yaml").oracle.release
        present = PolicyEngineUniverseBackend(
            checkout=_policyengine_uk_checkout()
        ).pinned_version()
    except Exception:
        return False
    return present == pinned


@pytest.mark.skipif(
    not _importable_pe_uk_matches_pin(),
    reason="importable policyengine_uk version does not match the pinned uk-pe release",
)
def test_policyengine_backend_enumerates_program_spine_from_code():
    """The backend reads each program's simulation kind from the checkout's code:
    income_tax computes (rules), council_tax is a pure input, pip is a rate table
    over a frozen category. Facts, not memory."""
    backend = PolicyEngineUniverseBackend(checkout=_policyengine_uk_checkout())
    by_name = {p.name: p for p in backend.raw_policies()}
    # One RawPolicy per spine program.
    assert len(by_name) == len(PE_UK_PROGRAM_SPINE)
    # income_tax is a rules engine with a queryable computed output.
    assert by_name["income_tax"].policy_type == "rules"
    assert "income_tax" in by_name["income_tax"].queryable_outputs
    # council_tax is a pure input: no queryable (formula-bearing) output, and the
    # variable is recorded as internal-only evidence.
    assert by_name["council_tax"].queryable_outputs == ()
    assert "council_tax" in by_name["council_tax"].internal_outputs
    assert by_name["council_tax"].policy_type == "pure_input"
    # A version can be pinned from the checkout's pyproject.toml.
    assert backend.pinned_version()[0].isdigit()


@pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("policyengine_uk")
    is None,
    reason="policyengine_uk not importable on this runner",
)
def test_policyengine_backend_raises_on_missing_spine_variable():
    """A spine variable absent from the checkout must fail loudly (a drift signal),
    not silently drop the program's surface."""
    from axiom_oracles.conformance.universe import PolicyEngineProgram

    backend = PolicyEngineUniverseBackend(
        checkout=_policyengine_uk_checkout(),
        spine=(PolicyEngineProgram("ghost", ("a_variable_that_does_not_exist",)),),
    )
    with pytest.raises(ValueError, match="not found in the pinned checkout"):
        backend.raw_policies()


class _FakeVarIndex:
    """A stand-in variable index for kind-classification unit tests."""

    def __init__(self, *, formulas=(), composes=(), sources=None):
        self._f = set(formulas)
        self._c = set(composes)
        self._s = sources or {}

    def has_formula(self, name):
        return name in self._f

    def has_adds_or_subtracts(self, name):
        return name in self._c

    def formula_source(self, name):
        return self._s.get(name, "")


def test_pe_variable_kind_treats_adds_subtracts_as_computed_only_when_enabled():
    """PE-US composes surfaces (state income taxes, standard_deduction, medicaid)
    from an adds/subtracts list, not a def formula. With the PE-US flag those are
    computed (rules); without it (PE-UK default) a no-formula variable stays a
    pure input, so PE-UK's committed facts are unchanged by this backend."""
    from axiom_oracles.conformance.universe import (
        PE_KIND_INPUT,
        PE_KIND_RULES,
        _pe_variable_kind,
    )

    composed = _FakeVarIndex(composes=["ca_income_tax"])
    assert (
        _pe_variable_kind("ca_income_tax", composed, include_adds_subtracts=True)
        == PE_KIND_RULES
    )
    assert (
        _pe_variable_kind("ca_income_tax", composed, include_adds_subtracts=False)
        == PE_KIND_INPUT
    )
    # A def-formula surface is rules regardless of the flag.
    formula = _FakeVarIndex(formulas=["snap"], sources={"snap": "def formula(): 0"})
    assert (
        _pe_variable_kind("snap", formula, include_adds_subtracts=True)
        == PE_KIND_RULES
    )
    # A bare input is a pure input under both.
    empty = _FakeVarIndex()
    assert (
        _pe_variable_kind("child_support_received", empty, include_adds_subtracts=True)
        == PE_KIND_INPUT
    )


def _policyengine_us_checkout():
    import policyengine_us  # type: ignore

    return Path(policyengine_us.__file__).resolve().parents[1]


def _importable_pe_us_matches_pin() -> bool:
    """True only when policyengine_us is importable AND its version equals the
    committed us-pe universe's pinned release (same version-gating the drift
    --check applies — the spine is pinned to that exact release)."""
    import importlib.util

    if importlib.util.find_spec("policyengine_us") is None:
        return False
    try:
        pinned = parse_universe(CONFORMANCE_DIR / "us-pe.yaml").oracle.release
        present = PolicyEngineUniverseBackend(
            checkout=_policyengine_us_checkout(), package="policyengine_us"
        ).pinned_version()
    except Exception:
        return False
    return present == pinned


@pytest.mark.skipif(
    not _importable_pe_us_matches_pin(),
    reason="importable policyengine_us version does not match the pinned us-pe release",
)
def test_policyengine_us_backend_reads_composed_surfaces_from_code():
    """Against the pinned checkout the US backend reads composed (adds/subtracts)
    surfaces as computed and reported inputs as internal — facts, not memory."""
    backend = PolicyEngineUniverseBackend(
        checkout=_policyengine_us_checkout(),
        package="policyengine_us",
        spine=PE_US_PROGRAM_SPINE,
        include_adds_subtracts=True,
    )
    by_name = {p.name: p for p in backend.raw_policies()}
    assert len(by_name) == len(PE_US_PROGRAM_SPINE)
    # A compose-based state income tax is a computed (queryable) rules surface.
    assert by_name["ca_income_tax"].policy_type == "rules"
    assert "ca_income_tax" in by_name["ca_income_tax"].queryable_outputs
    # snap is a def-formula rules surface.
    assert by_name["snap"].policy_type == "rules"
    # Reported passthroughs carry no queryable surface (internal-only evidence).
    assert by_name["child_support_received"].queryable_outputs == ()
    assert "child_support_received" in by_name["child_support_received"].internal_outputs
    # The pinned version is read from the checkout (pyproject or installed metadata).
    assert backend.pinned_version()[0].isdigit()


# ---------------------------------------------------------------------------
# Scoreboard predicate
# ---------------------------------------------------------------------------


def _universe(policies: list[UniversePolicy]) -> Universe:
    return Universe(
        jurisdiction="tx",
        oracle=OracleIdentity("M", "R", "S", "TX", "euromod"),
        policies=policies,
    )


def _report(suite: str, *, comparisons: int, matches: int, dispositioned=None):
    summary = {
        "comparison_count": comparisons,
        "match_count": matches,
        "mismatch_count": comparisons - matches,
    }
    if dispositioned is not None:
        summary["dispositioned"] = dispositioned
    return {"suite": suite, "engines": {"left": "euromod", "right": "axiom"},
            "summary": summary, "mismatches": []}


def test_scoreboard_conformant_when_all_covered_and_clean():
    universe = _universe([
        _in_scope(id="tx:a", oracle_policy_name="a", suite="suite-a"),
    ])
    reports = [_report("suite-a", comparisons=5, matches=5)]
    board, _ = score_jurisdiction(universe, reports)
    assert board.covered == 1 and board.policies_in_scope == 1
    assert board.conformant is True
    assert board.blocking_reasons == []


def test_scoreboard_not_conformant_when_a_policy_is_uncovered():
    universe = _universe([
        _in_scope(id="tx:a", oracle_policy_name="a", suite="suite-a"),
        _in_scope(id="tx:b", oracle_policy_name="b", suite=None),  # uncovered
    ])
    reports = [_report("suite-a", comparisons=5, matches=5)]
    board, _ = score_jurisdiction(universe, reports)
    assert board.covered == 1 and board.policies_in_scope == 2
    assert board.conformant is False
    assert any("not covered" in r for r in board.blocking_reasons)


def test_scoreboard_covered_requires_a_live_report_not_just_a_named_suite():
    """A suite named in the universe with NO committed report is uncovered."""
    universe = _universe([
        _in_scope(id="tx:a", oracle_policy_name="a", suite="ghost-suite"),
    ])
    board, _ = score_jurisdiction(universe, [])  # no reports at all
    assert board.covered == 0
    assert board.conformant is False


def test_scoreboard_unexplained_blocks_conformance():
    universe = _universe([
        _in_scope(id="tx:a", oracle_policy_name="a", suite="suite-a"),
    ])
    # 5 comparisons, 3 matches, 2 mismatches, no dispositions → 2 unexplained.
    reports = [_report("suite-a", comparisons=5, matches=3)]
    board, _ = score_jurisdiction(universe, reports)
    assert board.unexplained_total == 2
    assert board.conformant is False
    assert any("unexplained" in r for r in board.blocking_reasons)


def test_scoreboard_explained_residuals_do_not_block_conformance():
    """Raw < 100% but fully dispositioned upstream → conformant (the whole point)."""
    universe = _universe([
        _in_scope(id="tx:a", oracle_policy_name="a", suite="suite-a"),
    ])
    dispositioned = {
        "raw_match_rate": 60.0,
        "explained_rate": 100.0,
        "unexplained_count": 0,
        "counts": {
            "upstream_engine_gap": 2,
            "axiom_encoding_gap": 0,
            "bridge_artifact": 0,
            "explained_residual": 0,
            "unexplained": 0,
        },
    }
    reports = [_report("suite-a", comparisons=5, matches=3, dispositioned=dispositioned)]
    board, scores = score_jurisdiction(universe, reports)
    assert board.covered == 1
    assert board.unexplained_total == 0
    assert board.axiom_attributed_open == 0
    assert board.oracle_attributed == 2
    assert board.conformant is True
    # The drill-down shows both raw and explained rates side by side.
    covered_row = next(s for s in scores if s.covered)
    assert covered_row.raw_match_rate == 60.0
    assert covered_row.explained_rate == 100.0


def test_scoreboard_axiom_encoding_gap_blocks_conformance():
    universe = _universe([
        _in_scope(id="tx:a", oracle_policy_name="a", suite="suite-a"),
    ])
    dispositioned = {
        "raw_match_rate": 80.0,
        "explained_rate": 80.0,
        "unexplained_count": 0,
        "counts": {"axiom_encoding_gap": 1, "upstream_engine_gap": 0,
                   "bridge_artifact": 0, "explained_residual": 0, "unexplained": 0},
    }
    reports = [_report("suite-a", comparisons=5, matches=4, dispositioned=dispositioned)]
    board, _ = score_jurisdiction(universe, reports)
    assert board.axiom_attributed_open == 1
    assert board.conformant is False
    assert any("Axiom-attributed" in r for r in board.blocking_reasons)


def test_scoreboard_open_rulespec_issue_counts_as_axiom_attributed():
    universe = _universe([
        _in_scope(id="tx:a", oracle_policy_name="a", suite="suite-a"),
    ])
    report = _report("suite-a", comparisons=5, matches=4, dispositioned={
        "raw_match_rate": 80.0, "explained_rate": 100.0, "unexplained_count": 0,
        "counts": {"axiom_encoding_gap": 0, "upstream_engine_gap": 1,
                   "bridge_artifact": 0, "explained_residual": 0, "unexplained": 0},
    })
    report["mismatches"] = [{
        "disposition": {
            "disposition": "upstream_engine_gap",
            "linked_issue": "https://github.com/TheAxiomFoundation/rulespec-uk/issues/9",
        }
    }]
    board, _ = score_jurisdiction(universe, [report])
    # The linked OPEN rulespec issue makes this Axiom-attributed despite the
    # upstream_engine_gap label.
    assert board.axiom_attributed_open == 1
    assert board.conformant is False


def test_scoreboard_shared_report_counts_residual_once():
    """N in-scope policies covered by ONE report must count that report's mismatch
    signals once toward the headline — the PE-UK case (12 programs share
    uk-tax-benefits-efrs). Summing per-policy would multiply the residual N-fold
    and, if it were unexplained/axiom-attributed, inflate the conformance
    predicate and the ratchet. The per-policy drill-down still shows each row's
    report stats."""
    universe = _universe([
        _in_scope(id="tx:a", oracle_policy_name="a", suite="shared"),
        _in_scope(id="tx:b", oracle_policy_name="b", suite="shared"),
        _in_scope(id="tx:c", oracle_policy_name="c", suite="shared"),
    ])
    dispositioned = {
        "raw_match_rate": 60.0,
        "explained_rate": 100.0,
        "unexplained_count": 0,
        "counts": {
            "upstream_engine_gap": 5,
            "axiom_encoding_gap": 0,
            "bridge_artifact": 0,
            "explained_residual": 0,
            "unexplained": 0,
        },
    }
    reports = [_report("shared", comparisons=10, matches=5, dispositioned=dispositioned)]
    board, scores = score_jurisdiction(universe, reports)
    assert board.covered == 3
    # 5 upstream gaps counted ONCE, not 3× = 15.
    assert board.oracle_attributed == 5
    assert board.unexplained_total == 0
    assert board.axiom_attributed_open == 0
    assert board.conformant is True
    # Each covered drill-down row still reports the shared report's stats.
    covered_rows = [s for s in scores if s.covered]
    assert len(covered_rows) == 3
    assert all(s.oracle_attributed == 5 for s in covered_rows)


def test_scoreboard_shared_report_unexplained_counts_once_and_blocks_once():
    """The dedup must apply to the gating signals too: a shared report with 2
    unexplained mismatches contributes 2 (not 2×N) — otherwise the ratchet floor
    would move by a phantom multiple."""
    universe = _universe([
        _in_scope(id="tx:a", oracle_policy_name="a", suite="shared"),
        _in_scope(id="tx:b", oracle_policy_name="b", suite="shared"),
    ])
    # 10 comparisons, 8 matches, no dispositions → 2 unexplained on the report.
    reports = [_report("shared", comparisons=10, matches=8)]
    board, _ = score_jurisdiction(universe, reports)
    assert board.covered == 2
    assert board.unexplained_total == 2  # once, not 4
    assert board.conformant is False


def test_scoreboard_excluded_breakdown_by_reason():
    universe = _universe([
        UniversePolicy(id="tx:d", oracle_policy_name="d", output_vars=(),
                       in_scope=False, exclusion_reason="technical"),
        UniversePolicy(id="tx:e", oracle_policy_name="e", output_vars=(),
                       in_scope=False, exclusion_reason="takeup_adjustment"),
        UniversePolicy(id="tx:f", oracle_policy_name="f", output_vars=("f_s",),
                       in_scope=False, exclusion_reason="unobservable_boundary",
                       note="cited"),
        # An oracle_dataset_lacks_input row carries a real output_var but is still
        # excluded — the breakdown must pick it up under its own reason.
        UniversePolicy(id="tx:g", oracle_policy_name="g", output_vars=("g_s",),
                       in_scope=False, exclusion_reason="oracle_dataset_lacks_input",
                       note="activating input absent"),
    ])
    board, _ = score_jurisdiction(universe, [])
    assert board.excluded == 4
    assert board.excluded_by_reason == {
        "oracle_dataset_lacks_input": 1, "takeup_adjustment": 1,
        "technical": 1, "unobservable_boundary": 1,
    }
    # Excluded policies are never counted as covered.
    assert board.covered == 0 and board.policies_in_scope == 0


def test_scoreboard_witness_gate_uncovers_zero_exposure_policies():
    """A report whose exposure basis never exercises a policy's output
    columns with a positive rate does NOT cover that policy — comparing an
    all-zero column against an implicit 0 verifies nothing (F3)."""
    universe = _universe([
        _in_scope(id="tx:a", oracle_policy_name="a", suite="suite-a",
                  output_vars=("x_s",)),
        _in_scope(id="tx:b", oracle_policy_name="b", suite="suite-a",
                  output_vars=("y_s",)),
    ])
    report = _report("suite-a", comparisons=5, matches=5)
    report["scope"] = {"column_exposure": {"x_s": 5, "y_s": 0}}
    board, scores = score_jurisdiction(universe, [report])
    assert board.covered == 1 and board.policies_in_scope == 2
    assert board.uncovered_policies == ["b"]
    assert board.unwitnessed_policies == ["b"]
    assert board.conformant is False
    assert any("positive-exposure witness" in r for r in board.blocking_reasons)
    by_name = {s.oracle_policy_name: s for s in scores}
    assert by_name["a"].status == "conformant" and by_name["a"].covered
    assert by_name["b"].status == "unwitnessed" and not by_name["b"].covered


def test_scoreboard_witness_accepts_any_positive_output_var():
    """One positive column among a policy's output_vars is a witness."""
    universe = _universe([
        _in_scope(id="tx:a", oracle_policy_name="a", suite="suite-a",
                  output_vars=("y_s", "x_s")),
    ])
    report = _report("suite-a", comparisons=5, matches=5)
    report["scope"] = {"column_exposure": {"x_s": 3, "y_s": 0}}
    board, _ = score_jurisdiction(universe, [report])
    assert board.covered == 1 and board.unwitnessed_policies == []
    assert board.conformant is True


def test_scoreboard_without_exposure_basis_keeps_presence_coverage():
    """Reports with no scope.column_exposure (other jurisdictions) keep the
    presence-only coverage rule — the witness gate never fires blind."""
    universe = _universe([
        _in_scope(id="tx:a", oracle_policy_name="a", suite="suite-a",
                  output_vars=("x_s",)),
    ])
    board, _ = score_jurisdiction(
        universe, [_report("suite-a", comparisons=5, matches=5)]
    )
    assert board.covered == 1
    assert board.unwitnessed_policies == []
    assert board.temporal_debt is None


def test_scoreboard_surfaces_temporal_debt_from_covered_reports():
    """A covered report's scope.temporal_debt account lands on the
    jurisdiction summary instead of being clipped out of the story (F4)."""
    universe = _universe([
        _in_scope(id="tx:a", oracle_policy_name="a", suite="suite-a",
                  output_vars=("x_s",)),
    ])
    report = _report("suite-a", comparisons=5, matches=5)
    report["scope"] = {
        "column_exposure": {"x_s": 5},
        "temporal_debt": {
            "pre_domain_intervals": 100,
            "straddle_clipped_intervals": 7,
            "records": [{"debt_id": "d1"}, {"debt_id": "d2"}],
        },
    }
    board, _ = score_jurisdiction(universe, [report])
    assert board.temporal_debt == {
        "pre_domain_intervals": 100,
        "straddle_clipped_intervals": 7,
        "addressable_records": 2,
    }
    # Debt is surfaced, not a conformance blocker.
    assert board.conformant is True


def test_committed_us_tariff_yale_scoreboard_pins_witnessed_coverage():
    """The live us-tariff-yale verdict: CONFORMANT — 10 of 10 in-scope
    policies witnessed-covered, unexplained 0, axiom-attributed 0. The two
    authorities the reference never exercises with a positive rate (301_cs,
    other) are excluded-with-reason under the technical class with explicit
    re-inclusion tripwires (universe test above), and the temporal-debt
    account rides the summary (sol stack review F3/F4)."""
    scoreboard = json.loads((CONFORMANCE_DIR / "scoreboard.json").read_text())
    entry = {j["jurisdiction"]: j for j in scoreboard["jurisdictions"]}[
        "us-tariff-yale"
    ]
    assert entry["policies_in_scope"] == 10
    assert entry["covered"] == 10
    assert entry["covered_pct"] == 100.0
    assert entry["excluded"] == 4
    assert entry["excluded_by_reason"] == {"technical": 4}
    assert entry["conformant"] is True
    assert entry["uncovered_policies"] == []
    assert entry["unwitnessed_policies"] == []
    assert entry["temporal_debt"] == {
        "pre_domain_intervals": 48000,
        "straddle_clipped_intervals": 1200,
        "addressable_records": 205,
    }
    assert entry["oracle_attributed"] == 8283
    assert entry["axiom_attributed_open"] == 0


def test_committed_be_scoreboard_counts_dataset_lacks_input_exclusion():
    """The live BE scoreboard's excluded-by-reason breakdown surfaces the
    class (regression guard against the reason silently vanishing from the join).

    Three BE policies are excluded under it: bfapl_be (parental-leave allowance;
    lpb input absent, axiom-oracles#150/#158/#160) and the two Covid-19 wage-
    compensation schemes yemcomp_be / ysecomp_be, whose sole activator
    (bwkmceemy_s/bwkmcsemy_s, written only by the switched-off TransLMA_be from
    lmcee/lmcse/lindi columns absent from BE_training_data) is unreachable — a
    112-combination live probe returned 0 in every cell (axiom-oracles#142)."""
    import yaml as _yaml  # noqa: F401  (json already imported at module top)
    scoreboard = json.loads((CONFORMANCE_DIR / "scoreboard.json").read_text())
    be = next(j for j in scoreboard["jurisdictions"] if j["jurisdiction"] == "be")
    assert be["excluded_by_reason"].get("oracle_dataset_lacks_input") == 3
    detail = json.loads((CONFORMANCE_DIR / "detail" / "be.json").read_text())
    excluded_ids = {
        row["id"]
        for row in detail["policies"]
        if row.get("exclusion_reason") == "oracle_dataset_lacks_input"
    }
    assert {"be:bfapl_be", "be:yemcomp_be", "be:ysecomp_be"} <= excluded_ids


# ---------------------------------------------------------------------------
# Ratchet invariants — one NEGATIVE per invariant
# ---------------------------------------------------------------------------


def _summary(covered, unexplained, axiom_open, in_scope=10):
    return {
        "jurisdiction": "uk",
        "covered": covered,
        "unexplained_total": unexplained,
        "axiom_attributed_open": axiom_open,
        "policies_in_scope": in_scope,
    }


def test_ratchet_passes_when_stable():
    ratchet = RatchetInvariant("uk", covered_min=4, unexplained_max=0,
                               axiom_attributed_open_max=0, policies_in_scope=10)
    assert check_regressions(ratchet, _summary(4, 0, 0)) == []
    # Improvement (more covered) also passes.
    assert check_regressions(ratchet, _summary(6, 0, 0)) == []


def test_ratchet_fails_when_coverage_falls():
    ratchet = RatchetInvariant("uk", covered_min=4, unexplained_max=0,
                               axiom_attributed_open_max=0, policies_in_scope=10)
    violations = check_regressions(ratchet, _summary(3, 0, 0))
    assert violations and "covered" in violations[0]


def test_ratchet_fails_when_unexplained_rises():
    ratchet = RatchetInvariant("uk", covered_min=4, unexplained_max=0,
                               axiom_attributed_open_max=0, policies_in_scope=10)
    violations = check_regressions(ratchet, _summary(4, 1, 0))
    assert violations and "unexplained_total" in violations[0]


def test_ratchet_fails_when_axiom_gap_rises():
    ratchet = RatchetInvariant("uk", covered_min=4, unexplained_max=0,
                               axiom_attributed_open_max=0, policies_in_scope=10)
    violations = check_regressions(ratchet, _summary(4, 0, 1))
    assert violations and "axiom_attributed_open" in violations[0]


# ---------------------------------------------------------------------------
# Committed ratchet floor is consistent with the committed scoreboard
# ---------------------------------------------------------------------------


def test_committed_ratchet_not_violated_by_committed_scoreboard():
    import yaml

    ratchet_doc = yaml.safe_load((CONFORMANCE_DIR / "ratchet.yaml").read_text())
    scoreboard = json.loads((CONFORMANCE_DIR / "scoreboard.json").read_text())
    by_jur = {j["jurisdiction"]: j for j in scoreboard["jurisdictions"]}
    for row in ratchet_doc["ratchets"]:
        ratchet = RatchetInvariant.from_row(row)
        summary = by_jur[row["jurisdiction"]]
        assert check_regressions(ratchet, summary) == []


# ---------------------------------------------------------------------------
# GATE --check negative tests (the anti-vacuous requirement)
# ---------------------------------------------------------------------------


def test_scoreboard_check_fails_on_mutated_commit(tmp_path, monkeypatch):
    """NEGATIVE: mutating the committed scoreboard.json must fail --check."""
    sb = _load_script("conformance_scoreboard.py")
    original = sb.SCOREBOARD_PATH.read_text()
    mutated = json.loads(original)
    mutated["jurisdictions"][0]["covered"] += 1  # a lie
    sb.SCOREBOARD_PATH.write_text(json.dumps(mutated, indent=2) + "\n")
    try:
        rc = _run_check(sb)
    finally:
        sb.SCOREBOARD_PATH.write_text(original)
    assert rc == 1


def _run_check(module):
    import sys

    argv = sys.argv
    sys.argv = ["prog", "--check"]
    try:
        return module.main()
    finally:
        sys.argv = argv


def test_scoreboard_check_passes_when_committed_matches():
    sb = _load_script("conformance_scoreboard.py")
    assert _run_check(sb) == 0


def test_ratchet_check_fails_when_committed_floor_is_beaten_down(tmp_path):
    """NEGATIVE: lowering committed covered_min below the live scoreboard, then
    forcing a regression, must fail --check.
    """
    rt = _load_script("conformance_ratchet.py")
    original = rt.RATCHET_PATH.read_text()
    import yaml

    doc = yaml.safe_load(original)
    # Raise every covered_min far above what the live scoreboard can meet →
    # guaranteed regression on --check.
    for row in doc["ratchets"]:
        row["covered_min"] = row["covered_min"] + 999
    rt.RATCHET_PATH.write_text(yaml.dump(doc))
    try:
        rc = _run_check(rt)
    finally:
        rt.RATCHET_PATH.write_text(original)
    assert rc == 1


def test_ratchet_check_passes_on_committed():
    rt = _load_script("conformance_ratchet.py")
    assert _run_check(rt) == 0


def test_universe_drift_check_fails_when_committed_is_edited(tmp_path):
    """NEGATIVE: editing a generated FACT in the committed universe must fail
    --check when the model checkout is present (proves the drift gate bites).
    """
    if not (_UKMOD_ROOT / "XMLParam").exists():
        pytest.skip("UKMOD checkout not present")
    gen = _load_script("generate_conformance_universe.py")
    path = CONFORMANCE_DIR / "uk.yaml"
    original = path.read_text()
    # Corrupt a generated fact: drop an output var from bmu_uk.
    tampered = original.replace("      - bmu_s\n", "", 1)
    assert tampered != original
    path.write_text(tampered)
    try:
        rc = gen._process("uk", check=True, model_root=str(_UKMOD_ROOT))
    finally:
        path.write_text(original)
    assert rc == 1


def test_burndown_check_fails_on_mutated_commit():
    """NEGATIVE: mutating the committed burn-down must fail --check."""
    bd = _load_script("conformance_burndown.py")
    original = bd.OUTPUT_PATH.read_text()
    mutated = json.loads(original)
    # Add a fabricated point.
    first_series = next(iter(mutated["series"].values()))
    first_series.append({"date": "1999-01-01", "in_scope": 0, "covered": 0,
                         "uncovered": 0, "unexplained": 0,
                         "axiom_attributed_open": 0, "gap": 0, "conformant": False})
    bd.OUTPUT_PATH.write_text(json.dumps(mutated, indent=2) + "\n")
    try:
        rc = _run_check(bd)
    finally:
        bd.OUTPUT_PATH.write_text(original)
    assert rc == 1


# ---------------------------------------------------------------------------
# Per-suite runnable-program compositions (axiom-oracles#185)
# ---------------------------------------------------------------------------

from axiom_oracles.conformance.compositions import (  # noqa: E402
    AXIOM_RULESPEC_ROOT_ENV,
    build_compositions_document,
    composition_for_suite,
    compositions_path,
    load_composition,
    parse as parse_compositions,
    repo_relative_program_path,
    resolve_suite_program,
    rulespec_imports_for_concepts,
    serialize as serialize_compositions,
)

BE_COMPOSITIONS_PATH = CONFORMANCE_DIR / "compositions" / "be.yaml"


def _covered_be_suites() -> dict[str, str]:
    """suite -> universe policy id for every in-scope, suite-named BE row."""
    universe = parse_universe(CONFORMANCE_DIR / "be.yaml")
    return {p.suite: p.id for p in universe.in_scope() if p.suite is not None}


def test_be_compositions_record_covers_exactly_the_covered_suites():
    """The record enumerates every covered BE suite — no more, no fewer."""
    document = parse_compositions(BE_COMPOSITIONS_PATH)
    assert {c.suite for c in document.compositions} == set(_covered_be_suites())


def test_be_compositions_record_is_fresh():
    """POSITIVE gate: committed record == a fresh regeneration, byte for byte."""
    fresh = serialize_compositions(build_compositions_document("be"))
    assert BE_COMPOSITIONS_PATH.read_text() == fresh


def test_recorded_imports_match_the_cli_runner_derivation():
    """Anti-drift tie: each recorded import-set is exactly what the CLI runner
    composes for that suite when --axiom-program is omitted.

    ``_build_runner`` derives ``program_imports`` from the suite's output
    concepts via the same :func:`rulespec_imports_for_concepts`, so the record
    describes the real run path — it cannot name a program the harness would
    not compile.
    """
    document = parse_compositions(BE_COMPOSITIONS_PATH)
    for composition in document.compositions:
        live = composition_for_suite(composition.suite)
        assert composition.imports == live.imports, composition.suite
        assert composition.imports == rulespec_imports_for_concepts(
            composition.outputs
        ), composition.suite
        assert composition.target == composition.imports[0], composition.suite
        assert composition.entity == live.entity, composition.suite
        assert composition.entity_id == live.entity_id, composition.suite


def test_recorded_paths_are_repo_relative_to_the_imports():
    """Every recorded program file is the import's monorepo path (…​.yaml)."""
    document = parse_compositions(BE_COMPOSITIONS_PATH)
    for composition in document.compositions:
        assert len(composition.paths) == len(composition.imports), composition.suite
        for module_ref, path in zip(composition.imports, composition.paths):
            assert path == repo_relative_program_path(module_ref)
            assert path.startswith("rulespec-be/")
            assert path.endswith(".yaml")


def test_marital_quotient_is_the_lone_couple_module_not_front_chained():
    """The archaeology finding, pinned: be-marital-quotient runs the single
    ``couple_pit_oracle_pipeline`` module as a TaxUnit — it is NOT front-chained
    with the SSC/forfait/work-bonus stages. Its EUROMOD residual is carried by
    dispositions (dispositions/be-marital-quotient.yaml), not by a wider
    program. This guards against a future edit that silently widens the slice
    and quietly changes what "covered" means for this policy.
    """
    composition = load_composition("be-marital-quotient")
    assert composition is not None
    assert composition.entity == "TaxUnit"
    assert composition.imports == (
        "be:statutes/income_tax/individual/couple_pit_oracle_pipeline",
    )
    # No employee-SSC / forfait / work-bonus module is chained in front.
    joined = " ".join(composition.imports)
    assert "employee_contributions" not in joined
    assert "work_bonus" not in joined
    # The engine post-uprating gross is bridged onto the Article 89 boundary —
    # the supplied default beyond the suite's own axiom_inputs.
    assert composition.input_bridge == {
        "yem": (
            "be:statutes/income_tax/individual/joint_assessment"
            "#input.belgium_pit_spouse_a_professional_income_after_article_89_exclusions",
        )
    }


def test_worker_ssc_composition_spans_two_modules():
    """be-worker-ssc is the one multi-module composition: its three outputs span
    employee_contributions and work_bonus."""
    composition = load_composition("be-worker-ssc")
    assert composition is not None
    assert composition.imports == (
        "be:regulations/social_security/workers/employee_contributions",
        "be:regulations/social_security/workers/work_bonus",
    )
    assert len(composition.paths) == 2


def test_resolve_suite_program_normalizes_a_rulespec_checkout_root(tmp_path):
    """resolve() lifts a rulespec-* checkout path to the workspace root that
    modules resolve against, and binds the single-module program to a file."""
    workspace = tmp_path
    checkout = workspace / "rulespec-be"
    module_rel = (
        "be/statutes/income_tax/individual/couple_pit_oracle_pipeline.yaml"
    )
    target = checkout / module_rel
    target.parent.mkdir(parents=True)
    target.write_text("format: rulespec/v1\n")

    composition = load_composition("be-marital-quotient")
    # Pointing straight at the checkout resolves to its parent workspace.
    resolved = composition.resolve(checkout)
    assert resolved.root == workspace
    assert resolved.single_program_path == target
    assert resolved.missing_paths() == ()
    # Pointing at the workspace directly resolves identically.
    assert composition.resolve(workspace).root == workspace


def test_resolve_suite_program_reads_env_and_falls_back(monkeypatch):
    """resolve_suite_program uses AXIOM_RULESPEC_ROOT; None for unknown suite or
    unset root (the caller then falls back to live concept-derivation)."""
    monkeypatch.setenv(AXIOM_RULESPEC_ROOT_ENV, str(Path.home() / "TheAxiomFoundation"))
    assert resolve_suite_program("uk-universal-credit") is None  # no BE record
    monkeypatch.delenv(AXIOM_RULESPEC_ROOT_ENV, raising=False)
    assert resolve_suite_program("be-marital-quotient") is None  # no root


def test_multi_module_composition_has_no_single_program_path(tmp_path):
    """A 2-module composition offers no single --axiom-program file; callers use
    the import-set the harness composes."""
    workspace = tmp_path
    composition = load_composition("be-worker-ssc")
    resolved = composition.resolve(workspace)
    assert resolved.single_program_path is None
    assert len(resolved.program_paths) == 2


def _run_compositions_check(module) -> int:
    import sys

    argv = sys.argv
    sys.argv = ["prog", "--all", "--check"]
    try:
        return module.main()
    finally:
        sys.argv = argv


def test_compositions_check_passes_on_committed():
    """POSITIVE: the committed record passes --check."""
    gen = _load_script("generate_conformance_compositions.py")
    assert _run_compositions_check(gen) == 0


def test_compositions_check_fails_on_mutated_commit():
    """NEGATIVE: mutating the committed record must fail --check (the gate bites)."""
    gen = _load_script("generate_conformance_compositions.py")
    path = compositions_path("be")
    original = path.read_text()
    # Flip a query entity — a lie about what the harness runs.
    tampered = original.replace("entity: TaxUnit", "entity: Household", 1)
    assert tampered != original
    path.write_text(tampered)
    try:
        rc = _run_compositions_check(gen)
    finally:
        path.write_text(original)
    assert rc == 1
