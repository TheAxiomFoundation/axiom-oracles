import hashlib
import types

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.core.case import Concepts
from axiom_oracles.core.geography import GeographyScope
from axiom_oracles.populations.populace_us import (
    NYC_ENHANCED_CPS_DATASET,
    POPULACE_PINS,
    POPULACE_US_DATASET,
    PopulacePin,
    PopulaceUsCaseLoader,
    _clean_number,
    _resolve_populace_dataset,
    _scope_from_geography,
    dataset_for_scope,
    load_populace_us_cases,
)


def _install_fake_hf(monkeypatch, *, on_download):
    """Stub huggingface_hub so resolution tests need no network/heavy install.

    ``on_download`` records the kwargs the resolver passes to
    ``hf_hub_download`` and returns a local path (a real file, so the sha256
    gate reads actual bytes).
    """
    stub = types.ModuleType("huggingface_hub")
    stub.hf_hub_download = on_download
    monkeypatch.setitem(__import__("sys").modules, "huggingface_hub", stub)


def _artifact_file(tmp_path, contents: bytes):
    """Write ``contents`` to a temp artifact and return (path, its sha256)."""
    path = tmp_path / "populace_us_2024.h5"
    path.write_bytes(contents)
    return str(path), hashlib.sha256(contents).hexdigest()


def test_national_scope_defaults_to_the_populace_artifact() -> None:
    assert dataset_for_scope(None) == POPULACE_US_DATASET
    assert dataset_for_scope(GeographyScope(type="census_state", geoid="06")) == (
        POPULACE_US_DATASET
    )


def test_nyc_scope_uses_nyc_enhanced_cps_dataset() -> None:
    # The one remaining eCPS-derived path: populace-us has no place grain
    # yet (PolicyEngine/populace#204), so NYC keeps its dedicated file.
    assert (
        dataset_for_scope(GeographyScope(type="census_place", geoid="3651000"))
        == NYC_ENHANCED_CPS_DATASET
    )


def test_certified_populace_us_artifact_is_pinned() -> None:
    # The default US population must be content-pinned, not HF-latest: latest
    # follows the sparse L0 refit with dead input bases (populace#278).
    pin = POPULACE_PINS[("policyengine/populace-us", "populace_us_2024.h5")]
    assert pin.revision == "populace-us-2024-f0af251-703bd81a565c-20260620T201958Z"
    assert pin.sha256 == (
        "16be6338f9d0b3c339883dae59949e995663b64cf145de6728b3dd0f916c5d5f"
    )


def test_populace_reference_resolves_pinned_revision_and_verifies_hash(
    monkeypatch, tmp_path
) -> None:
    # huggingface_hub arrives with the policyengine extra; stub it so the
    # resolution contract tests without the heavyweight install.
    pin = POPULACE_PINS[("policyengine/populace-us", "populace_us_2024.h5")]
    local, digest = _artifact_file(tmp_path, b"dense-certified-bytes")
    monkeypatch.setitem(
        POPULACE_PINS,
        ("policyengine/populace-us", "populace_us_2024.h5"),
        PopulacePin(revision=pin.revision, sha256=digest),
    )
    calls = {}

    def fake_download(*, repo_id, filename, repo_type, revision):
        calls.update(
            repo_id=repo_id, filename=filename, repo_type=repo_type, revision=revision
        )
        return local

    _install_fake_hf(monkeypatch, on_download=fake_download)
    path = _resolve_populace_dataset(POPULACE_US_DATASET)
    assert path == local
    # The pinned revision is passed through, and the repo is the dataset repo.
    assert calls == {
        "repo_id": "policyengine/populace-us",
        "filename": "populace_us_2024.h5",
        "repo_type": "dataset",
        "revision": pin.revision,
    }


def test_populace_resolution_fails_loudly_on_sha256_mismatch(
    monkeypatch, tmp_path
) -> None:
    # A moved tag or corrupt transfer must raise, never silently swap the
    # population under a comparison.
    pin = POPULACE_PINS[("policyengine/populace-us", "populace_us_2024.h5")]
    local, _ = _artifact_file(tmp_path, b"sparse-wrong-artifact")
    monkeypatch.setitem(
        POPULACE_PINS,
        ("policyengine/populace-us", "populace_us_2024.h5"),
        PopulacePin(revision=pin.revision, sha256="0" * 64),
    )

    def fake_download(*, repo_id, filename, repo_type, revision):
        return local

    _install_fake_hf(monkeypatch, on_download=fake_download)
    with pytest.raises(RuntimeError, match="failed its sha256 check"):
        _resolve_populace_dataset(POPULACE_US_DATASET)


def test_inline_revision_override_is_passed_through(monkeypatch, tmp_path) -> None:
    # An unregistered repo/file with an inline @revision resolves at that ref
    # and skips hashing (no pin => no expected digest).
    local, _ = _artifact_file(tmp_path, b"adhoc")
    calls = {}

    def fake_download(*, repo_id, filename, repo_type, revision):
        calls.update(repo_id=repo_id, revision=revision)
        return local

    _install_fake_hf(monkeypatch, on_download=fake_download)
    path = _resolve_populace_dataset(
        "populace://policyengine/populace-us-experiments/probe.h5@abc123"
    )
    assert path == local
    assert calls == {"repo_id": "policyengine/populace-us-experiments", "revision": "abc123"}


def test_inline_revision_conflicting_with_pin_raises(monkeypatch, tmp_path) -> None:
    # If a caller pins a different revision inline than the registered pin,
    # refuse rather than resolve an ambiguous reference.
    def fake_download(*, repo_id, filename, repo_type, revision):  # pragma: no cover
        raise AssertionError("must not download on ambiguous pin")

    _install_fake_hf(monkeypatch, on_download=fake_download)
    with pytest.raises(ValueError, match="ambiguous pin"):
        _resolve_populace_dataset(POPULACE_US_DATASET + "@some-other-revision")


def test_unpinned_reference_resolves_latest_without_hashing(
    monkeypatch, tmp_path
) -> None:
    # A populace:// reference with no registered pin and no inline revision
    # still works (revision=None => HF-latest), for ad-hoc/experimental repos.
    local, _ = _artifact_file(tmp_path, b"latest")
    calls = {}

    def fake_download(*, repo_id, filename, repo_type, revision):
        calls.update(revision=revision)
        return local

    _install_fake_hf(monkeypatch, on_download=fake_download)
    path = _resolve_populace_dataset("populace://some/other-dataset/file.h5")
    assert path == local
    assert calls == {"revision": None}


def test_loader_projects_sampled_ecps_households_to_cases() -> None:
    sims = []

    def factory(dataset):
        sim = FakeMicrosimulation(dataset)
        sims.append(sim)
        return sim

    cases = load_populace_us_cases(
        scope=GeographyScope(type="census_place", geoid="3651000"),
        period="2026-05",
        sample_size=2,
        microsimulation_factory=factory,
    )

    assert sims[0].dataset == NYC_ENHANCED_CPS_DATASET
    assert sims[0].subsample_size == 2
    assert [case.case_id for case in cases] == ["ecps-101", "ecps-202"]
    assert cases[0].metadata["population"] == "enhanced-cps"
    assert cases[0].metadata["household_weight"] == 12.5
    assert cases[0].scope == GeographyScope(type="census_place", geoid="3651000")
    assert cases[0].entities[0].facts[Concepts.HOUSEHOLD_RELATION] == (
        "HeadOfHousehold"
    )
    assert cases[0].entities[1].facts[Concepts.HOUSEHOLD_RELATION] == "Child"
    assert cases[0].entities[0].facts[Concepts.YEARLY_EARNED_INCOME] == 20_000
    assert cases[0].entities[0].facts[Concepts.BENEFITS_MEDICAID] is True


def test_loader_can_project_sampled_ecps_tax_units_to_cases() -> None:
    cases = load_populace_us_cases(
        period="2026",
        sample_size=2,
        case_unit="tax_unit",
        microsimulation_factory=lambda dataset: FakeMicrosimulation(dataset),
    )

    assert [case.case_id for case in cases] == [
        "ecps-tax-unit-1001",
        "ecps-tax-unit-2002",
    ]
    assert cases[0].metadata["case_unit"] == "tax_unit"
    assert cases[0].metadata["household_id"] == 101
    assert cases[0].entities[0].facts[Concepts.HOUSEHOLD_RELATION] == (
        "HeadOfHousehold"
    )
    assert cases[0].entities[1].facts[Concepts.HOUSEHOLD_RELATION] == "Child"
    assert cases[1].entities[0].facts[Concepts.HOUSEHOLD_RELATION] == (
        "HeadOfHousehold"
    )


DIV = Concepts.DIVIDEND_INCOME
QDIV = Concepts.QUALIFIED_DIVIDEND_INCOME
CGD = Concepts.NON_SCHEDULE_D_CAPITAL_GAIN_DISTRIBUTIONS
STCG = Concepts.SHORT_TERM_CAPITAL_GAINS
LTCG = Concepts.LONG_TERM_CAPITAL_GAINS


def _load(case_unit, *, drop=(), **person_overrides):
    """Cases plus the fake simulation that produced them.

    The fake has persons 1 and 2 (a head and her child) in tax unit 1001 and
    person 3 alone in tax unit 2002, one household each.
    """
    sims = []

    def factory(dataset):
        sims.append(
            FakeMicrosimulation(dataset, person_overrides=person_overrides, drop=drop)
        )
        return sims[-1]

    cases = load_populace_us_cases(
        period="2026",
        case_unit=case_unit,
        microsimulation_factory=factory,
    )
    return cases, sims[-1]


def _facts(cases):
    return {
        entity.entity_id: entity.facts for case in cases for entity in case.entities
    }


@pytest.mark.parametrize("case_unit", ["household", "tax_unit"])
def test_loader_reads_form_1040_lines_3b_and_3a_from_the_dividend_split(
    case_unit,
) -> None:
    cases, sim = _load(
        case_unit,
        qualified_dividend_income=[3_000, 0, 250],
        non_qualified_dividend_income=[2_000, 0, 0],
        # The artifact's stored legacy column: never line 3b.
        dividend_income=[777, 777, 777],
    )
    facts = _facts(cases)

    # Line 3b is qualified + non-qualified; line 3a is the qualified part.
    assert facts["person-1"][DIV] == 5_000
    assert facts["person-1"][QDIV] == 3_000
    assert DIV not in facts["person-2"] and QDIV not in facts["person-2"]
    assert facts["person-3"][DIV] == 250
    assert facts["person-3"][QDIV] == 250
    assert "dividend_income" not in sim.calculated
    assert "ordinary_dividend_income" not in sim.calculated


def test_loader_carries_line_7a_on_tax_unit_cases_only() -> None:
    overrides = {"non_sch_d_capital_gains": [2_000, 0, 500]}

    tax_cases, _ = _load("tax_unit", **overrides)
    facts = _facts(tax_cases)
    assert facts["person-1"][CGD] == 2_000
    assert CGD not in facts["person-2"]
    assert facts["person-3"][CGD] == 500
    assert all(
        "capital_gain_distributions_folded_into_schedule_d" not in case.metadata
        for case in tax_cases
    )

    # Household Cases feed the benefit lanes, whose Axiom encodings read no
    # capital gains: they neither carry nor calculate line 7a.
    household_cases, household_sim = _load("household", **overrides)
    assert all(CGD not in facts for facts in _facts(household_cases).values())
    assert "non_sch_d_capital_gains" not in household_sim.calculated


def test_loader_moves_line_7a_onto_schedule_d_when_the_tax_unit_files_one() -> None:
    cases, _ = _load(
        "tax_unit",
        non_sch_d_capital_gains=[2_000, 300, 500],
        # Tax unit 1001 has a Schedule D amount (the child's short-term
        # loss), so Exception 1 fails for it; tax unit 2002 has none.
        short_term_capital_gains=[0, -400, 0],
        long_term_capital_gains=[5_000, 0, 0],
    )
    facts = _facts(cases)
    by_id = {case.case_id: case for case in cases}

    assert CGD not in facts["person-1"] and CGD not in facts["person-2"]
    assert facts["person-1"][LTCG] == 7_000
    assert facts["person-2"][LTCG] == 300
    assert facts["person-2"][STCG] == -400
    assert (
        by_id["ecps-tax-unit-1001"].metadata[
            "capital_gain_distributions_folded_into_schedule_d"
        ]
        == 2
    )
    assert facts["person-3"][CGD] == 500
    assert LTCG not in facts["person-3"]
    assert (
        "capital_gain_distributions_folded_into_schedule_d"
        not in by_id["ecps-tax-unit-2002"].metadata
    )


@pytest.mark.parametrize(
    ("missing", "household_loads"),
    [
        ("qualified_dividend_income", False),
        ("non_qualified_dividend_income", False),
        ("non_sch_d_capital_gains", True),
    ],
)
def test_loader_fails_closed_when_an_investment_variable_is_missing(
    missing, household_loads
) -> None:
    # The shared table loads zeros for a variable PolicyEngine cannot
    # calculate; that silently zeroed a concept for the whole population.
    with pytest.raises(RuntimeError, match=missing):
        _load("tax_unit", drop=(missing,))
    if household_loads:
        _load("household", drop=(missing,))
    else:
        with pytest.raises(RuntimeError, match=missing):
            _load("household", drop=(missing,))


def test_loader_dividend_sources_are_policyengine_inputs() -> None:
    policyengine_us = pytest.importorskip("policyengine_us")
    variables = policyengine_us.system.system.variables
    from axiom_oracles.populations.populace_us import (
        _TAX_UNIT_PERSON_NON_WAGE_VARIABLES,
        POPULACE_DIVIDEND_VARIABLES,
    )

    for name in (
        *POPULACE_DIVIDEND_VARIABLES,
        *_TAX_UNIT_PERSON_NON_WAGE_VARIABLES.values(),
    ):
        variable = variables[name]
        assert variable.entity.key == "person"
        assert not variable.formulas and not getattr(variable, "adds", None)
    # PolicyEngine-US defines line 3b as exactly this sum.
    assert list(variables["ordinary_dividend_income"].adds) == list(
        POPULACE_DIVIDEND_VARIABLES
    )
    assert list(variables["dividend_income"].adds) == ["ordinary_dividend_income"]


AMOUNTS = st.lists(st.integers(0, 90_000), min_size=3, max_size=3)
SIGNED = st.lists(st.integers(-40_000, 90_000), min_size=3, max_size=3)


@settings(max_examples=150, deadline=None, derandomize=True)
@given(
    qualified=AMOUNTS,
    non_qualified=AMOUNTS,
    distributions=AMOUNTS,
    short_term=SIGNED,
    long_term=SIGNED,
)
def test_property_loader_emits_coherent_form_1040_facts(
    qualified, non_qualified, distributions, short_term, long_term
) -> None:
    overrides = {
        "qualified_dividend_income": qualified,
        "non_qualified_dividend_income": non_qualified,
        "non_sch_d_capital_gains": distributions,
        "short_term_capital_gains": short_term,
        "long_term_capital_gains": long_term,
    }
    tax_cases, _ = _load("tax_unit", **overrides)
    household_cases, _ = _load("household", **overrides)

    for cases in (tax_cases, household_cases):
        for index, facts in enumerate(_facts(cases).values()):
            # Line 3b = qualified + non-qualified >= line 3a >= 0.
            assert facts.get(DIV, 0) == qualified[index] + non_qualified[index]
            assert facts.get(QDIV, 0) == qualified[index]
            assert 0 <= facts.get(QDIV, 0) <= facts.get(DIV, 0)
    assert all(CGD not in facts for facts in _facts(household_cases).values())

    members_by_unit = {"ecps-tax-unit-1001": (0, 1), "ecps-tax-unit-2002": (2,)}
    for case in tax_cases:
        members = members_by_unit[case.case_id]
        facts = [entity.facts for entity in case.entities]
        files_schedule_d = any(short_term[i] or long_term[i] for i in members)
        carries_7a = any(CGD in row for row in facts)
        # Never both paths in one tax unit.
        assert not (files_schedule_d and carries_7a)
        # The fold conserves long-term gain plus line 7a.
        assert sum(row.get(LTCG, 0) + row.get(CGD, 0) for row in facts) == sum(
            long_term[i] + distributions[i] for i in members
        )
        if not files_schedule_d:
            assert [row.get(CGD, 0) for row in facts] == [
                distributions[i] for i in members
            ]


def test_loader_skips_geographically_unresolvable_records() -> None:
    loader = PopulaceUsCaseLoader(
        dataset="memory://fake",
        microsimulation_factory=lambda dataset: FakeMicrosimulation(
            dataset,
            place_fips=[b"", b"51000"],
        ),
    )

    cases = loader.load_cases(
        scope=GeographyScope(type="census_place", geoid="3651000"),
        period="2026",
    )

    assert [case.case_id for case in cases] == ["ecps-202"]


def test_scope_from_geography_combines_state_and_county_components() -> None:
    assert _scope_from_geography(29, 135, "") == GeographyScope(
        type="census_county",
        geoid="29135",
    )
    assert _scope_from_geography(36, 36061, "") == GeographyScope(
        type="census_county",
        geoid="36061",
    )
    assert _scope_from_geography(21, 0, "") == GeographyScope(
        type="census_state",
        geoid="21",
    )
    assert _scope_from_geography(float("nan"), 0, "") is None


def test_clean_number_treats_unknown_as_missing() -> None:
    assert _clean_number("UNKNOWN") == 0


def test_deprecated_enhanced_cps_aliases_resolve_to_the_populace_loader() -> None:
    # The module was renamed enhanced_cps -> populace_us (axiom-oracles#74).
    # External callers may still use the old module path and names; they must
    # resolve to the SAME objects and emit a DeprecationWarning, so encode (and
    # any other consumer) migrates independently without behaviour change.
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        with pytest.raises(DeprecationWarning):
            import importlib

            importlib.import_module("axiom_oracles.populations.enhanced_cps")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        import importlib

        legacy = importlib.import_module("axiom_oracles.populations.enhanced_cps")

    assert legacy.load_enhanced_cps_cases is load_populace_us_cases
    assert legacy.EnhancedCpsCaseLoader is PopulaceUsCaseLoader
    # The package __init__ re-exports both the new and the aliased names.
    from axiom_oracles import populations

    assert populations.load_enhanced_cps_cases is load_populace_us_cases
    assert populations.load_populace_us_cases is load_populace_us_cases


class FakeSeries:
    def __init__(self, values):
        self.values = values


class FakeMicrosimulation:
    def __init__(self, dataset, *, place_fips=None, person_overrides=None, drop=()):
        self.dataset = dataset
        self.subsample_size = None
        self.calculated: list[str] = []
        self.household_data = {
            "household_id": [101, 202],
            "household_weight": [12.5, 34.0],
            "state_fips": [36, 36],
            "county_fips": ["36061", "36047"],
            "place_fips": place_fips or [b"51000", b"51000"],
        }
        self.person_data = {
            "household_id": [101, 101, 202],
            "person_id": [1, 2, 3],
            "tax_unit_id": [1001, 1001, 2002],
            "is_tax_unit_head": [True, False, True],
            "is_tax_unit_spouse": [False, False, False],
            "is_tax_unit_dependent": [False, True, False],
            "age": [30, 5, 67],
            "employment_income": [20_000, 0, 10_000],
            "is_pregnant": [False, False, False],
            "is_disabled": [False, False, True],
            "is_blind": [False, False, False],
            "is_veteran": [False, False, True],
            "has_medicaid_health_coverage_at_interview": [True, False, False],
            # The loader reads these fail-closed (POPULACE_DIVIDEND_VARIABLES
            # and the tax-unit line 7a table), so the fake must carry them.
            "qualified_dividend_income": [0, 0, 0],
            "non_qualified_dividend_income": [0, 0, 0],
            "non_sch_d_capital_gains": [0, 0, 0],
        }
        self.person_data.update(person_overrides or {})
        for variable in drop:
            del self.person_data[variable]

    def subsample(self, sample_size):
        self.subsample_size = sample_size

    def calculate(self, variable, period, map_to=None):
        del period
        self.calculated.append(variable)
        data = self.person_data if map_to == "person" else self.household_data
        if variable not in data:
            raise ValueError(variable)
        return FakeSeries(data[variable])
