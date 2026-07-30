from axiom_oracles.adapters.policyengine import PolicyEngineTaxsimRunner
from axiom_oracles.adapters.policyengine.runner import (
    _calculation_period,
)
from axiom_oracles.adapters.prd import PrdPackageRunner
from axiom_oracles.adapters.taxsim import TaxsimPackageRunner
from axiom_oracles.core.case import Case, Concepts, Entity


class _FakeVariable:
    def __init__(self, definition_period: str) -> None:
        self.definition_period = definition_period


class _FakePolicyEngineModel:
    def __init__(self, definition_period: str) -> None:
        self.definition_period = definition_period

    def get_variable(self, variable: str) -> _FakeVariable:
        del variable
        return _FakeVariable(self.definition_period)


class _FakePolicyEngine:
    def __init__(self, definition_period: str) -> None:
        self.us = type("FakeUS", (), {"model": _FakePolicyEngineModel(definition_period)})()


def test_policyengine_month_variable_is_computed_at_the_requested_month() -> None:
    # Month-defined variables must be evaluated at the requested month itself:
    # PE's year-shaped annual sum spans two federal fiscal years (SNAP COLAs
    # land October 1), so annual/12 is not any month's value.
    assert (
        _calculation_period(_FakePolicyEngine("month"), "snap", "2026-01", 2026)
        == "2026-01"
    )
    assert (
        _calculation_period(
            _FakePolicyEngine("month"), "is_snap_eligible", "2026-01", 2026
        )
        == "2026-01"
    )


def test_policyengine_year_variables_and_year_requests_stay_year_shaped() -> None:
    assert (
        _calculation_period(_FakePolicyEngine("year"), "income_tax", "2026-01", 2026)
        == 2026
    )
    assert (
        _calculation_period(_FakePolicyEngine("month"), "snap", "2026", 2026) == 2026
    )


def test_taxsim_package_runner_wraps_taxsim_format_rows() -> None:
    captured_inputs = []

    class FakeTaxsimRunner:
        def __init__(self, input_frame):
            captured_inputs.append(input_frame)

        def run(self, show_progress=False):
            del show_progress
            return [
                {"taxsimid": "case-1", "fiitax": 100, "siitax": 25, "unused": 1}
            ]

    case = Case(
        case_id="case-1",
        period="2024",
        metadata={
            "taxsim_input": {
                "year": 2024,
                "state": 36,
                "mstat": 1,
                "page": 40,
            }
        },
    )

    results = TaxsimPackageRunner(runner_factory=FakeTaxsimRunner).run_cases(
        [case],
        variables=["fiitax", "siitax"],
    )

    assert captured_inputs[0].iloc[0]["taxsimid"] == "case-1"
    assert captured_inputs[0].iloc[0]["year"] == 2024
    assert results[0].engine == "taxsim"
    assert results[0].household_id == "case-1"
    assert results[0].values == {"fiitax": 100, "siitax": 25}


def test_taxsim_package_runner_projects_cases_and_maps_canonical_concepts() -> None:
    captured_inputs = []

    class FakeTaxsimRunner:
        def __init__(self, input_frame):
            captured_inputs.append(input_frame)

        def run(self, show_progress=False):
            del show_progress
            return [{"taxsimid": 1.0, "fiitax": 100, "siitax": 25, "unused": 1}]

    case = Case(
        case_id="case-1",
        period="2024",
        metadata={"scope": {"type": "census_state", "geoid": "36"}},
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 40,
                    Concepts.YEARLY_EARNED_INCOME: 50_000,
                },
            ),
        ),
    )

    results = TaxsimPackageRunner(runner_factory=FakeTaxsimRunner).run_cases(
        [case],
        variables=[
            Concepts.FEDERAL_INCOME_TAX,
            Concepts.STATE_INCOME_TAX,
        ],
    )

    input_row = captured_inputs[0].to_dict(orient="records")[0]
    assert input_row["taxsimid"] == 1
    assert input_row["state"] == 33
    assert results[0].household_id == "case-1"
    assert results[0].values == {"fiitax": 100, "siitax": 25}


def test_policyengine_taxsim_runner_maps_taxsim_output_to_policyengine_targets() -> None:
    captured_inputs = []

    class FakePolicyEngineTaxsimRunner:
        def __init__(self, input_frame):
            captured_inputs.append(input_frame)

        def run(self, show_progress=False):
            del show_progress
            return [{"taxsimid": "case-1", "fiitax": 100, "siitax": 25, "unused": 1}]

    case = Case(
        case_id="case-1",
        period="2024",
        metadata={
            "taxsim_input": {
                "taxsimid": "case-1",
                "year": 2024,
                "state": 33,
                "mstat": 1,
                "page": 40,
            }
        },
    )

    results = PolicyEngineTaxsimRunner(
        runner_factory=FakePolicyEngineTaxsimRunner
    ).run_cases(
        [case],
        variables=[
            Concepts.FEDERAL_INCOME_TAX,
            Concepts.STATE_INCOME_TAX,
        ],
    )

    assert captured_inputs[0].iloc[0]["state"] == 33
    assert results[0].engine == "policyengine"
    assert results[0].household_id == "case-1"
    assert results[0].values == {"income_tax": 100, "state_income_tax": 25}


def test_policyengine_taxsim_pairs_prefer_canonical_concepts_on_shared_columns() -> None:
    from axiom_oracles.adapters.policyengine.taxsim_runner import (
        _taxsim_to_policyengine_pairs,
    )

    # The state pilot concepts share TAXSIM's `siitax` with the canonical
    # state-liability concept. The canonical mapping is declared first, so it
    # must claim the column no matter how many pilots are requested after it;
    # the pilots' PolicyEngine variables are not produced by the
    # policyengine-taxsim emulator and must stay unmapped rather than
    # clobbering `state_income_tax` (the last-writer-wins regression the
    # 2026-07-21 ECPS run surfaced).
    pairs = _taxsim_to_policyengine_pairs(
        [
            "state_income_tax",
            "nc_income_tax_before_credits",
            "co_income_tax_before_non_refundable_credits",
        ]
    )
    assert pairs["siitax"] == "state_income_tax"


def test_policyengine_taxsim_pairs_carry_aggregates_for_list_targets() -> None:
    from axiom_oracles.adapters.policyengine.taxsim_runner import (
        _taxsim_to_policyengine_pairs,
    )

    # Concepts whose PolicyEngine target is a summed list (employee_fica,
    # tax_before_credits) map their TAXSIM aggregate onto the first list
    # component; the comparator sums the components that are present, so the
    # concept-level value reproduces the aggregate exactly.
    pairs = _taxsim_to_policyengine_pairs(
        [
            "employee_social_security_tax",
            "employee_medicare_tax",
            "self_employment_tax",
            "income_tax_main_rates",
            "capital_gains_tax",
        ]
    )
    assert pairs["tfica"] == "employee_social_security_tax"
    assert pairs["v28"] == "income_tax_main_rates"


def test_prd_package_runner_wraps_external_prd_households() -> None:
    passed_households = []
    passed_programs = []

    class FakePrdRunner:
        def run_households(self, households, programs=None):
            passed_households.extend(households)
            passed_programs.extend(programs or [])
            return [{"hhid": "case-1", "value.snap": 120, "value.wic": 40}]

    prd_household = object()
    case = Case(
        case_id="case-1",
        period="2026",
        metadata={"prd_household": prd_household},
    )

    results = PrdPackageRunner(runner=FakePrdRunner()).run_cases(
        [case],
        variables=[Concepts.SNAP_BENEFIT],
    )

    assert passed_households == [prd_household]
    assert passed_programs == ["value.snap"]
    assert results[0].engine == "prd"
    assert results[0].household_id == "case-1"
    assert results[0].values == {"value.snap": 120}


def test_taxsim_installed_binary_path_walks_sys_path_archive_roots(
    monkeypatch, tmp_path
):
    """uv `--with` overlay envs put the wheel's share/ data files in a cached
    archive root while sys.prefix points at a bare temp dir — the resolver
    must find the bundled binary through the site-packages entries (#296)."""
    from axiom_oracles.adapters.taxsim import pins

    site = tmp_path / "archive" / "lib" / "python3.14" / "site-packages"
    site.mkdir(parents=True)
    exe = (
        tmp_path
        / "archive"
        / "share"
        / "policyengine_taxsim"
        / "taxsimtest"
        / "taxsimtest-osx.exe"
    )
    exe.parent.mkdir(parents=True)
    exe.touch()
    monkeypatch.setattr(pins.sys, "path", [str(site)])
    monkeypatch.setattr(pins.sys, "prefix", str(tmp_path / "empty-prefix"))
    monkeypatch.setattr(pins.sys, "base_prefix", str(tmp_path / "empty-prefix"))
    assert pins.installed_binary_path("darwin") == exe
