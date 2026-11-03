"""SNAP child support oracle adapters for 7 CFR 273.9(c)(17) and (d)(5).

Each Axiom concept must replay the PolicyEngine-US variable of the same
meaning:

- the (c)(17) exclusion replays ``snap_child_support_gross_income_deduction``,
  which PolicyEngine computes as its state exclusion parameter times countable
  child support;
- the (d)(5) deduction replays ``snap_child_support_deduction``, the countable
  child support that the parameter does not exclude;
- the State election to provide the deduction replays the negation of
  ``gov.usda.snap.income.deductions.child_support``, which is true when the
  state excludes. The values have that sense from policyengine-us 2.11.4
  (PolicyEngine/policyengine-us#9586).

The live tests replay the adapters in PolicyEngine-US the way axiom-encode's
validator reads these fields. Without a policyengine-us that has #9586 they
skip, unless AXIOM_ORACLES_REQUIRE_POLICYENGINE_LIVE=1 (set in CI's
policyengine-live job) turns the skip into a failure.
"""

from __future__ import annotations

import importlib.metadata
import os
from decimal import Decimal
from types import SimpleNamespace

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from axiom_oracles.bridges.adapters import (
    PE_US_ALL_VAR_ADAPTERS,
    PE_US_PROGRAM_VAR_ADAPTERS,
    PE_US_VAR_ADAPTERS,
    SNAP_ALIMONY_PAYMENTS_INPUT,
    SNAP_CHILD_SUPPORT_DEDUCTION_STATE,
    SNAP_CHILD_SUPPORT_ELECTION_INPUT,
    SNAP_CHILD_SUPPORT_EXCLUSION_STATE,
    SNAP_CHILD_SUPPORT_PAYMENTS_INPUT,
    SNAP_CHILD_SUPPORT_TREATMENT_PARAMETER,
    PolicyEngineUSVarAdapter,
    boolean_parameter_reading,
    get_pe_us_var_adapter,
)
from axiom_oracles.bridges.registry import load_policyengine_registry

EXCLUSION = get_pe_us_var_adapter("snap_child_support_income_exclusion")
DEDUCTION = get_pe_us_var_adapter("snap_child_support_deduction_for_net_income")
ELECTION = get_pe_us_var_adapter("snap_state_agency_provides_child_support_deduction")

# The rulespec-us modules that d324 encodes; (c)(17) imports (d)(5).
C_17 = "us:regulations/7-cfr/273/9/c/17"
D_5 = "us:regulations/7-cfr/273/9/d/5"
PERIOD = "2026-01"
POLICYENGINE_ELECTION_FIX = (2, 11, 4)
REQUIRE_LIVE = os.environ.get("AXIOM_ORACLES_REQUIRE_POLICYENGINE_LIVE") == "1"
CENT = 0.01


@pytest.mark.parametrize(
    ("rule_name", "pe_var"),
    [
        (
            "snap_child_support_income_exclusion",
            "snap_child_support_gross_income_deduction",
        ),
        ("snap_child_support_deduction_for_net_income", "snap_child_support_deduction"),
        # State deduction rules, such as us-ga:policies/dfcs/snap/3616.
        ("snap_child_support_deduction", "snap_child_support_deduction"),
        (
            "snap_state_agency_provides_child_support_deduction",
            "snap_state_agency_provides_child_support_deduction",
        ),
        (
            "snap_state_uses_child_support_deduction",
            "snap_state_agency_provides_child_support_deduction",
        ),
    ],
)
def test_each_concept_replays_the_policyengine_variable_of_the_same_meaning(
    rule_name: str, pe_var: str
) -> None:
    # The validator resolves adapters through PE_US_VAR_ADAPTERS_BY_NAME (last
    # entry wins); axiom-encode's classifier indexes rule_names (first wins).
    first_by_rule_name: dict[str, PolicyEngineUSVarAdapter] = {}
    for adapter in PE_US_VAR_ADAPTERS:
        for name in adapter.rule_names:
            first_by_rule_name.setdefault(name, adapter)

    assert get_pe_us_var_adapter(rule_name).pe_var == pe_var
    assert first_by_rule_name[rule_name].pe_var == pe_var


@pytest.mark.parametrize(
    "table",
    [PE_US_ALL_VAR_ADAPTERS, *PE_US_PROGRAM_VAR_ADAPTERS.values()],
    ids=["all", *PE_US_PROGRAM_VAR_ADAPTERS],
)
def test_no_name_belongs_to_two_adapters(table) -> None:
    # A shared name makes the first-wins and last-wins lookups disagree, which
    # is how the (d)(5) name once resolved to PolicyEngine's exclusion.
    owners: dict[str, set[int]] = {}
    for adapter in table:
        for name in {adapter.pe_var, *adapter.rule_names}:
            owners.setdefault(name, set()).add(id(adapter))
    assert {name for name, ids in owners.items() if len(ids) > 1} == set()


def test_exclusion_and_deduction_replay_distinct_variables_from_one_household() -> None:
    assert EXCLUSION.pe_var != DEDUCTION.pe_var
    for field in (
        "annualized_person_inputs",
        "direct_spm_overrides",
        "state_code_from_boolean_input",
        "boolean_input_parameter_check",
        "monthly",
        "spm",
    ):
        assert getattr(EXCLUSION, field) == getattr(DEDUCTION, field), field
    assert EXCLUSION.annualized_person_inputs == (
        (SNAP_CHILD_SUPPORT_PAYMENTS_INPUT, "child_support_expense"),
        (SNAP_ALIMONY_PAYMENTS_INPUT, "alimony_expense"),
    )
    assert EXCLUSION.direct_spm_overrides == (
        (SNAP_CHILD_SUPPORT_PAYMENTS_INPUT, "snap_countable_child_support_expense"),
    )


def test_every_child_support_election_read_is_inverted() -> None:
    # Regression guard: the parameter is true when the state EXCLUDES, so no
    # adapter may read it as "the state deducts".
    readers = [
        adapter
        for adapter in PE_US_ALL_VAR_ADAPTERS
        if adapter.parameter_path == SNAP_CHILD_SUPPORT_TREATMENT_PARAMETER
    ]
    assert readers == [ELECTION]
    assert ELECTION.parameter_value_mode == "inverted_bool"
    for adapter in PE_US_ALL_VAR_ADAPTERS:
        check = adapter.boolean_input_parameter_check
        if check is not None and check[1] == SNAP_CHILD_SUPPORT_TREATMENT_PARAMETER:
            assert check == (
                SNAP_CHILD_SUPPORT_ELECTION_INPUT,
                SNAP_CHILD_SUPPORT_TREATMENT_PARAMETER,
                "inverted_bool",
            )
    for adapter in (EXCLUSION, DEDUCTION, ELECTION):
        assert adapter.state_code_from_boolean_input == (
            SNAP_CHILD_SUPPORT_ELECTION_INPUT,
            SNAP_CHILD_SUPPORT_DEDUCTION_STATE,
            SNAP_CHILD_SUPPORT_EXCLUSION_STATE,
        )
        assert adapter.default_state_code is None


def test_boolean_parameter_reading_follows_the_mode() -> None:
    parameters = {"flag": {"TX": False, "CA": True}}

    class Node(dict):
        def __getattr__(self, name):
            return Node(self[name]) if isinstance(self[name], dict) else self[name]

    root = Node(parameters)
    assert boolean_parameter_reading(root, "flag", "bool", "CA") is True
    assert boolean_parameter_reading(root, "flag", "inverted_bool", "CA") is False
    assert boolean_parameter_reading(root, "flag", "inverted_bool", "TX") is True
    with pytest.raises(ValueError, match="unsupported"):
        boolean_parameter_reading(root, "flag", "float", "TX")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"parameter_value_mode": "inverted"},
        {"boolean_input_parameter_check": ("flag", "gov.flag", "float")},
    ],
)
def test_unknown_parameter_value_modes_are_rejected(kwargs) -> None:
    with pytest.raises(ValueError, match="unsupported"):
        PolicyEngineUSVarAdapter(rule_names=("x",), pe_var="x", **kwargs)


@pytest.mark.parametrize(
    ("legal_id", "adapter"),
    [
        (f"{C_17}#snap_child_support_income_exclusion", EXCLUSION),
        (f"{D_5}#snap_child_support_deduction_for_net_income", DEDUCTION),
        (f"{D_5}#snap_state_agency_provides_child_support_deduction", ELECTION),
    ],
)
def test_registry_routes_the_federal_rules_to_their_adapters(
    legal_id: str, adapter: PolicyEngineUSVarAdapter
) -> None:
    # The validator reaches an adapter only through an exact registry row;
    # the us:regulations/7-cfr/273/ prefix row is not comparable.
    mapping = load_policyengine_registry().mapping_for_legal_id(legal_id, country="us")
    assert mapping is not None
    assert mapping.match_type == "exact"
    assert mapping.mapping_type == "direct_variable"
    assert mapping.comparable
    assert get_pe_us_var_adapter(mapping.policyengine_variable) is adapter
    assert legal_id.partition("#")[2] in adapter.rule_names
    assert mapping.comparison == adapter.comparison


# Live PolicyEngine-US replays.


def _version_tuple(version: str) -> tuple[int, ...]:
    parts = []
    for part in version.split(".")[:3]:
        digits = "".join(char for char in part if char.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts)


@pytest.fixture(scope="module")
def pe():
    def unavailable(reason: str):
        if REQUIRE_LIVE:
            pytest.fail(reason)
        pytest.skip(reason)

    try:
        import policyengine_us
    except ImportError:
        unavailable("policyengine-us is not installed")
    version = importlib.metadata.version("policyengine-us")
    if _version_tuple(version) < POLICYENGINE_ELECTION_FIX:
        unavailable(
            f"policyengine-us {version} predates PolicyEngine/policyengine-us#9586 "
            "(2.11.4); its child support election has the opposite sense"
        )
    return SimpleNamespace(
        Simulation=policyengine_us.Simulation,
        parameters=policyengine_us.CountryTaxBenefitSystem().parameters,
    )


def _parameter_node(pe, path: str, period: str | None = None):
    node = pe.parameters(period) if period is not None else pe.parameters
    for part in path.split("."):
        node = getattr(node, part)
    return node


def _replay_state(adapter: PolicyEngineUSVarAdapter, inputs: dict) -> str:
    input_key, true_state, false_state = adapter.state_code_from_boolean_input
    return true_state if bool(inputs[input_key]) else false_state


def _parameter_reading(pe, path: str, mode: str, state: str) -> bool:
    value = bool(_parameter_node(pe, path, PERIOD)[state])
    return not value if mode == "inverted_bool" else value


def _replay(pe, adapter: PolicyEngineUSVarAdapter, inputs: dict) -> tuple[str, float]:
    """Replay one adapter as axiom-encode's validator builds the scenario."""
    year = PERIOD[:4]
    state = _replay_state(adapter, inputs)
    if adapter.parameter_path is not None:
        reading = _parameter_reading(
            pe, adapter.parameter_path, adapter.parameter_value_mode, state
        )
        return state, 1.0 if reading else 0.0
    adult = {"age": {year: 30}}
    for rule_key, pe_key in adapter.annualized_person_inputs:
        if inputs.get(rule_key) is not None:
            adult[pe_key] = {year: float(inputs[rule_key]) * 12}
    spm_unit = {"members": ["adult"]}
    for rule_key, pe_key in adapter.direct_spm_overrides:
        if inputs.get(rule_key) is not None:
            spm_unit[pe_key] = {PERIOD: float(inputs[rule_key])}
    situation = {
        "people": {"adult": adult},
        "tax_units": {"tu": {"members": ["adult"], "filing_status": {year: "SINGLE"}}},
        "spm_units": {"spm": spm_unit},
        "households": {
            "hh": {
                "members": ["adult"],
                "state_name": {year: state},
                "state_code_str": {year: state},
            }
        },
        "families": {"fam": {"members": ["adult"]}},
        "marital_units": {"mu": {"members": ["adult"]}},
    }
    simulation = pe.Simulation(situation=situation)
    return state, float(simulation.calculate(adapter.pe_var, PERIOD)[0])


def _check_admits(pe, adapter: PolicyEngineUSVarAdapter, inputs: dict) -> bool:
    input_key, path, mode = adapter.boolean_input_parameter_check
    state = _replay_state(adapter, inputs)
    return _parameter_reading(pe, path, mode, state) == bool(inputs[input_key])


def _inputs(payment: float, election: bool, alimony: float = 0.0) -> dict:
    return {
        SNAP_CHILD_SUPPORT_PAYMENTS_INPUT: payment,
        SNAP_ALIMONY_PAYMENTS_INPUT: alimony,
        SNAP_CHILD_SUPPORT_ELECTION_INPUT: election,
    }


@pytest.mark.parametrize(
    ("state", "excludes"),
    [
        (SNAP_CHILD_SUPPORT_DEDUCTION_STATE, False),
        (SNAP_CHILD_SUPPORT_EXCLUSION_STATE, True),
    ],
)
def test_replay_states_hold_their_election_at_every_dated_value(
    pe, state: str, excludes: bool
) -> None:
    node = _parameter_node(pe, SNAP_CHILD_SUPPORT_TREATMENT_PARAMETER)
    values = [entry.value for entry in node.children[state].values_list]
    assert values
    assert all(bool(value) is excludes for value in values)
    # The population replay projects the election with this reading.
    assert boolean_parameter_reading(
        pe.parameters(PERIOD),
        SNAP_CHILD_SUPPORT_TREATMENT_PARAMETER,
        "inverted_bool",
        state,
    ) is (not excludes)


@pytest.mark.parametrize(
    ("election", "state", "excluded", "deducted", "provides_deduction"),
    [
        (True, "TX", 0.0, 300.0, 1.0),
        (False, "CA", 300.0, 0.0, 0.0),
    ],
)
def test_texas_deducts_and_california_excludes(
    pe, election, state, excluded, deducted, provides_deduction
) -> None:
    inputs = _inputs(300.0, election)
    assert _replay(pe, EXCLUSION, inputs) == (state, pytest.approx(excluded))
    assert _replay(pe, DEDUCTION, inputs) == (state, pytest.approx(deducted))
    assert _replay(pe, ELECTION, inputs) == (state, provides_deduction)
    assert all(
        _check_admits(pe, adapter, inputs)
        for adapter in (EXCLUSION, DEDUCTION, ELECTION)
    )


@pytest.mark.parametrize(
    ("payment", "alimony", "election", "excluded", "deducted"),
    [
        # The companion cases specified for the d/5 and c/17 modules.
        (300.0, 0.0, True, 0.0, 300.0),
        (300.0, 0.0, False, 300.0, 0.0),
        (0.0, 250.0, True, 0.0, 0.0),
        (300.0, 250.0, True, 0.0, 300.0),
        (125.50, 0.0, True, 0.0, 125.50),
        (125.50, 0.0, False, 125.50, 0.0),
        (0.0, 0.0, True, 0.0, 0.0),
        (0.0, 0.0, False, 0.0, 0.0),
    ],
)
def test_federal_companion_cases_replay_to_their_expected_values(
    pe, payment, alimony, election, excluded, deducted
) -> None:
    inputs = _inputs(payment, election, alimony)
    assert _replay(pe, EXCLUSION, inputs)[1] == pytest.approx(excluded, abs=CENT)
    assert _replay(pe, DEDUCTION, inputs)[1] == pytest.approx(deducted, abs=CENT)


@settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    alimony=st.sampled_from([0, 250, 1_000]),
    payment=st.decimals(
        min_value=0,
        max_value=20_000,
        places=2,
        allow_nan=False,
        allow_infinity=False,
    ),
    election=st.booleans(),
)
def test_policyengine_excludes_or_deducts_each_payment_exactly_once(
    pe, payment: Decimal, election: bool, alimony: int
) -> None:
    # Alimony never enters either amount.
    amount = float(payment)
    inputs = _inputs(amount, election, float(alimony))
    exclusion_state, excluded = _replay(pe, EXCLUSION, inputs)
    deduction_state, deducted = _replay(pe, DEDUCTION, inputs)

    assert exclusion_state == deduction_state
    assert _check_admits(pe, EXCLUSION, inputs)
    assert excluded >= 0 and deducted >= 0
    assert excluded + deducted == pytest.approx(amount, abs=CENT)
    assert min(excluded, deducted) == pytest.approx(0.0, abs=CENT)
    assert (deducted if election else excluded) == pytest.approx(amount, abs=CENT)
