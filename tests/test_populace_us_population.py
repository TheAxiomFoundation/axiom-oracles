import hashlib
import importlib
import types

import pytest
from click.testing import CliRunner
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
    _PERSON_NON_WAGE_VARIABLES,
    _STRICT_PERSON_NON_WAGE_VARIABLES,
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


@pytest.mark.parametrize("case_unit", ["tax_unit", "household"])
def test_cases_carry_tax_exempt_interest_for_nonzero_persons(case_unit) -> None:
    """Both Case units carry the fact: tax-unit Cases feed the tax engines,
    household Cases the benefit lanes, whose Axiom inputs read it wherever the
    program's income definition counts it (axiom-oracles#567)."""
    cases = load_populace_us_cases(
        period="2026",
        case_unit=case_unit,
        microsimulation_factory=lambda dataset: FakeMicrosimulation(dataset),
    )

    head, child = cases[0].entities
    (other_head,) = cases[1].entities
    assert head.facts[Concepts.TAX_EXEMPT_INTEREST_INCOME] == 2_500
    assert other_head.facts[Concepts.TAX_EXEMPT_INTEREST_INCOME] == 700
    # Zeros are dropped, exactly like the shared non-wage table.
    assert Concepts.TAX_EXEMPT_INTEREST_INCOME not in child.facts


@pytest.mark.parametrize("case_unit", ["tax_unit", "household"])
def test_tax_exempt_interest_keeps_the_sign_it_is_given(case_unit) -> None:
    """Same cleaning as the shared table: the loader never floors; floors
    belong to the projections. (The pinned Populace person table has 13,354
    nonzero values and none negative, counted 2026-10-10; this fake-population
    test does not audit that artifact.)"""

    def factory(dataset):
        sim = FakeMicrosimulation(dataset)
        sim.person_data["tax_exempt_interest_income"] = [-40.0, 0.0, 700.0]
        return sim

    cases = load_populace_us_cases(
        period="2026",
        case_unit=case_unit,
        microsimulation_factory=factory,
    )

    assert cases[0].entities[0].facts[Concepts.TAX_EXEMPT_INTEREST_INCOME] == -40


def test_household_and_tax_unit_cases_carry_the_same_person_amounts() -> None:
    """The two Case units regroup one person table; each person's tax-exempt
    interest is identical whichever unit carries it."""

    def amounts(case_unit):
        cases = load_populace_us_cases(
            period="2026",
            case_unit=case_unit,
            microsimulation_factory=lambda dataset: FakeMicrosimulation(dataset),
        )
        return sorted(
            entity.fact(Concepts.TAX_EXEMPT_INTEREST_INCOME, 0)
            for case in cases
            for entity in case.entities
        )

    assert amounts("household") == amounts("tax_unit") == [0, 700, 2_500]


@pytest.mark.parametrize("case_unit", ["tax_unit", "household"])
def test_loader_fails_closed_when_tax_exempt_interest_is_missing(case_unit) -> None:
    """A renamed or missing PolicyEngine variable must stop the load, not
    load every person's tax-exempt interest as zero: on household Cases a
    silent zero would hide income from PolicyEngine and Axiom alike."""

    def factory(dataset):
        sim = FakeMicrosimulation(dataset)
        del sim.person_data["tax_exempt_interest_income"]
        return sim

    with pytest.raises(RuntimeError, match="'tax_exempt_interest_income'"):
        load_populace_us_cases(
            period="2026",
            case_unit=case_unit,
            microsimulation_factory=factory,
        )


def test_tax_exempt_interest_reads_the_policyengine_us_person_input() -> None:
    """The loader asks for exactly ``tax_exempt_interest_income``, which the
    installed policyengine-us defines as a Person, yearly, stored float input
    (no formula, so no aggregate alias can double-count it)."""
    assert _STRICT_PERSON_NON_WAGE_VARIABLES == {
        Concepts.TAX_EXEMPT_INTEREST_INCOME: "tax_exempt_interest_income",
    }
    assert Concepts.TAX_EXEMPT_INTEREST_INCOME not in _PERSON_NON_WAGE_VARIABLES

    policyengine_us = pytest.importorskip("policyengine_us")
    variable = policyengine_us.CountryTaxBenefitSystem().variables[
        "tax_exempt_interest_income"
    ]
    assert variable.entity.key == "person"
    assert variable.definition_period == "year"
    assert variable.value_type is float
    assert not variable.formulas
    assert not getattr(variable, "adds", None)


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
    def __init__(self, dataset, *, place_fips=None):
        self.dataset = dataset
        self.subsample_size = None
        self.calls = []
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
            "tax_exempt_interest_income": [2_500.0, 0.0, 700.0],
        }

    def subsample(self, sample_size):
        self.subsample_size = sample_size

    def calculate(self, variable, period, map_to=None):
        del period
        self.calls.append(variable)
        data = self.person_data if map_to == "person" else self.household_data
        if variable not in data:
            raise ValueError(variable)
        return FakeSeries(data[variable])


class _InputsCaptured(Exception):
    """Stop the real CLI after runner construction, before engine execution."""


def _capture_cli_population(
    monkeypatch, arguments, *, build_runners=False, allow_empty_surface=False
):
    cli_module = importlib.import_module("axiom_oracles.cli")
    original_loader = cli_module.load_populace_us_cases
    original_build_runner = cli_module._build_runner
    captured = {"runners": {}}

    def fake_source_loader(**kwargs):
        captured["loader_kwargs"] = kwargs.copy()
        if selector := kwargs.get("case_unit_selector"):

            def capture_case_unit(locales):
                case_unit = selector(locales)
                captured["loader_kwargs"]["case_unit"] = case_unit
                return case_unit

            kwargs["case_unit_selector"] = capture_case_unit
        cases = original_loader(
            **kwargs, microsimulation_factory=FakeMicrosimulation
        )
        captured["cases"] = cases
        return cases

    def capture_runner(engine, *args, **kwargs):
        captured["concepts"] = args[3]
        if build_runners:
            captured["runners"][engine] = original_build_runner(
                engine, *args, **kwargs
            )
            if len(captured["runners"]) < 2:
                return captured["runners"][engine]
        raise _InputsCaptured

    monkeypatch.setattr(cli_module, "load_populace_us_cases", fake_source_loader)
    monkeypatch.setattr(cli_module, "_build_runner", capture_runner)
    monkeypatch.setattr(
        cli_module, "_echo_resolved_axiom_composition", lambda *args: None
    )
    result = CliRunner().invoke(cli_module.cli, ["compare", *arguments])
    if allow_empty_surface and "No comparable concepts found" in result.output:
        captured["concepts"] = ()
        return captured
    assert isinstance(result.exception, _InputsCaptured), (
        result.output, result.exception
    )
    return captured


TAX_SURFACE_SELECTIONS = (
    (),
    ("--category", "tax"),
    ("--concept", Concepts.FEDERAL_INCOME_TAX),
    ("--suite", "nyc-synthetic"),
    ("--category", "tax", "--category", "food"),
)


@pytest.mark.parametrize("selection", TAX_SURFACE_SELECTIONS)
def test_cli_tax_surface_carries_interest_to_both_real_runner_inputs(
    monkeypatch, selection
):
    """A tax-only mapped surface always loads tax units, even with no filters.

    ECPS's --suite is a label; synthetic suite construction stays separate.
    These assertions inspect real runner inputs, without executing liabilities.
    """
    from axiom_oracles.adapters.policyengine import PolicyEngineRunner
    from axiom_oracles.adapters.taxcalc import TaxCalcPackageRunner

    captured = _capture_cli_population(
        monkeypatch, ["taxcalc", "policyengine", *selection], build_runners=True
    )
    taxcalc = captured["runners"]["taxcalc"]
    policyengine = captured["runners"]["policyengine"]
    assert type(taxcalc) is TaxCalcPackageRunner
    assert type(policyengine) is PolicyEngineRunner
    case = captured["cases"][0]
    head = case.entities[0]
    pe_inputs = policyengine._build_situation_from_case(case)["people"]
    assert pe_inputs[head.entity_id]["tax_exempt_interest_income"] == {2026: 2_500}
    assert taxcalc._input_rows([case])[0]["e00400"] == 2_500
    assert captured["concepts"] == (Concepts.FEDERAL_INCOME_TAX,)
    assert captured["loader_kwargs"]["case_unit"] == "tax_unit"
    assert case.case_id == "ecps-tax-unit-1001"


@settings(max_examples=25, deadline=None, derandomize=True)
@given(
    selection=st.sampled_from(TAX_SURFACE_SELECTIONS),
    reversed_pair=st.booleans(),
)
def test_property_cli_tax_grain_is_independent_of_surface_selection(
    selection, reversed_pair
):
    # Use a fresh patch context per generated command, without fixture reuse.
    pair = ["policyengine", "taxcalc"] if reversed_pair else ["taxcalc", "policyengine"]
    with pytest.MonkeyPatch.context() as patches:
        captured = _capture_cli_population(patches, [*pair, *selection])
    assert captured["concepts"] == (Concepts.FEDERAL_INCOME_TAX,)
    assert captured["loader_kwargs"]["case_unit"] == "tax_unit"
    assert captured["cases"][0].entities[0].fact(
        Concepts.TAX_EXEMPT_INTEREST_INCOME
    ) == 2_500


@pytest.mark.parametrize(
    "selection",
    [
        (),
        ("--category", "food"),
        ("--category", "tax", "--category", "food"),
        ("--concept", Concepts.SNAP_BENEFIT),
        ("--concept", Concepts.FEDERAL_INCOME_TAX, "--concept", Concepts.SNAP_BENEFIT),
        ("--suite", "nyc-synthetic", "--category", "food"),
    ],
)
def test_cli_benefit_and_mixed_surfaces_preserve_household_cases(
    monkeypatch, selection
):
    """Household construction keeps the same ids, facts, people and metadata,
    and household Cases carry tax-exempt interest like tax-unit Cases do
    (axiom-oracles#567)."""
    captured = _capture_cli_population(
        monkeypatch, ["axiom", "policyengine", *selection]
    )
    assert captured["loader_kwargs"]["case_unit"] == "household"
    before = load_populace_us_cases(
        **captured["loader_kwargs"], microsimulation_factory=FakeMicrosimulation
    )
    assert captured["cases"] == before
    assert [case.case_id for case in before] == ["ecps-101", "ecps-202"]
    assert [
        [person.fact(Concepts.TAX_EXEMPT_INTEREST_INCOME, 0) for person in case.entities]
        for case in before
    ] == [[2_500, 0], [700]]


CA_TAX = (
    "us-ca:policies/income_tax/pilot_liability_pipeline"
    "#ca_pit_pilot_income_tax_liability"
)


@pytest.mark.parametrize(
    "selection",
    [
        ("--category", "tax"),
        ("--concept", Concepts.FEDERAL_INCOME_TAX, "--concept", CA_TAX),
        ("--concept", CA_TAX, "--locale", "US-CA"),
    ],
)
def test_cli_state_tax_selections_preserve_interest_in_real_inputs(
    monkeypatch, selection
):
    from axiom_oracles.adapters.axiom.tax_projection import (
        attach_axiom_tax_inputs_to_case,
    )
    from axiom_oracles.adapters.policyengine import PolicyEngineRunner

    captured = _capture_cli_population(
        monkeypatch, ["axiom", "policyengine", *selection]
    )
    case = captured["cases"][0]
    assert captured["loader_kwargs"]["case_unit"] == "tax_unit"
    assert case.entities[0].fact(Concepts.TAX_EXEMPT_INTEREST_INCOME) == 2_500
    pe_inputs = PolicyEngineRunner()._build_situation_from_case(case)["people"]
    assert pe_inputs[case.entities[0].entity_id]["tax_exempt_interest_income"] == {
        2026: 2_500
    }
    records = attach_axiom_tax_inputs_to_case(case).metadata["axiom_input_records"]
    for name in (
        "us:statutes/26/86#input.tax_exempt_interest_received_or_accrued",
        "us:tax/federal-income-tax#input.eitc_relevant_investment_income",
    ):
        assert [
            record["value"]
            for record in records
            if record["name"] == name and record["entity"] == "TaxUnit"
        ] == [2_500]
    if selection[0] == "--category":
        assert CA_TAX not in captured["concepts"]
        assert any(concept.startswith("us-ny:") for concept in captured["concepts"])
    elif "--locale" in selection:
        assert captured["concepts"] == (CA_TAX,)
    else:
        assert captured["concepts"] == (Concepts.FEDERAL_INCOME_TAX,)


@st.composite
def real_mapping_selections(draw):
    from axiom_oracles.comparison.mappings import load_program_mappings

    mappings = [
        mapping
        for mapping in load_program_mappings()
        if mapping.target_for_engine("policyengine")
    ]
    pair = draw(
        st.sampled_from(
            [
                ("axiom", "policyengine"),
                ("taxcalc", "policyengine"),
                ("policyengine", "taxsim"),
                ("axiom", "taxsim"),
            ]
        )
    )
    if draw(st.booleans()):
        pair = pair[::-1]
    # Draw actual mapping rows, including outputs unsupported by the pair.
    rows = draw(
        st.lists(
            st.sampled_from(mappings),
            min_size=1,
            max_size=4,
            unique_by=lambda m: m.concept_id,
        )
    )
    mode = draw(st.sampled_from(["default", "category", "concepts", "suite"]))
    arguments = list(pair)
    concepts = set()
    categories = set()
    if mode == "concepts":
        concepts = {row.concept_id for row in rows}
        for concept in sorted(concepts):
            arguments.extend(["--concept", concept])
    elif mode == "category":
        categories = {row.category for row in rows}
        for category in sorted(categories):
            arguments.extend(["--category", category])
    if mode == "suite" or draw(st.booleans()):
        arguments.extend(["--suite", "nyc-synthetic"])
    locales = draw(
        st.sampled_from(
            [(), ("US-CA",), ("US-NY-NYC",), ("US-CO",), ("US-CA", "US-NY")]
        )
    )
    for locale in locales:
        arguments.extend(["--locale", locale])
    components = draw(st.booleans())
    if components:
        arguments.append("--include-components")
    return pair, arguments, concepts, categories, locales, components


@settings(max_examples=100, deadline=None, derandomize=True)
@given(selection=real_mapping_selections())
def test_property_cli_grain_matches_final_real_mapping_surface(selection):
    """For every successful selection, tax-unit grain iff all final outputs
    are tax-unit concepts, including state outputs and locale restrictions.
    """
    from axiom_oracles.comparison.mappings import (
        comparable_mappings,
        comparison_scope_for_targets,
    )

    pair, arguments, concepts, categories, locales, components = selection
    with pytest.MonkeyPatch.context() as patches:
        captured = _capture_cli_population(patches, arguments, allow_empty_surface=True)
    effective_locales = set(locales) or {
        case.locale for case in captured["cases"] if case.locale
    }
    expected = comparable_mappings(
        *pair,
        locales=effective_locales,
        scope=comparison_scope_for_targets(*pair),
        concepts=concepts or None,
        categories=categories or None,
        include_components=components,
    )
    assert captured["concepts"] == tuple(mapping.concept_id for mapping in expected)
    if not expected:
        return  # No compared surface and no runners execute.
    expected_unit = (
        "tax_unit"
        if all(mapping.case_unit == "tax_unit" for mapping in expected)
        else "household"
    )
    assert captured["loader_kwargs"]["case_unit"] == expected_unit
    assert all(
        case.metadata.get("case_unit", "household") == expected_unit
        for case in captured["cases"]
    )


@pytest.mark.parametrize("locales", [(), ("--locale", "US-CA")])
def test_cli_locale_filtering_precedes_grain_selection(monkeypatch, locales):
    """A locale-filtered benefit cannot force household grain for final tax outputs."""
    from dataclasses import replace
    from axiom_oracles.comparison.mappings import (
        comparable_mappings,
        mappings_by_concept,
    )

    cli_module = importlib.import_module("axiom_oracles.cli")
    registered = mappings_by_concept()
    surface = [
        registered[Concepts.FEDERAL_INCOME_TAX],
        replace(registered[Concepts.SNAP_BENEFIT], locales=("US-CA",)),
    ]
    monkeypatch.setattr(
        cli_module,
        "comparable_mappings",
        lambda *args, **kwargs: comparable_mappings(*args, mappings=surface, **kwargs),
    )
    captured = _capture_cli_population(
        monkeypatch,
        [
            "axiom",
            "policyengine",
            "--concept",
            Concepts.FEDERAL_INCOME_TAX,
            "--concept",
            Concepts.SNAP_BENEFIT,
            *locales,
        ],
    )
    assert captured["concepts"] == (
        (Concepts.FEDERAL_INCOME_TAX, Concepts.SNAP_BENEFIT)
        if locales
        else (Concepts.FEDERAL_INCOME_TAX,)
    )
    assert captured["loader_kwargs"]["case_unit"] == (
        "household" if locales else "tax_unit"
    )


def test_cli_grain_uses_mapped_outputs_instead_of_category_label(monkeypatch):
    """Even a tax category cannot convert a mapped benefit into a tax unit."""
    cli_module = importlib.import_module("axiom_oracles.cli")
    from axiom_oracles.comparison.mappings import ProgramMapping

    benefit = ProgramMapping(
        standard=Concepts.SNAP_BENEFIT,
        description="Benefit with a broad category label",
        category="tax",
        targets={"axiom": "snap", "policyengine": "snap"},
    )
    monkeypatch.setattr(cli_module, "comparable_mappings", lambda *a, **kw: [benefit])
    captured = _capture_cli_population(
        monkeypatch, ["axiom", "policyengine", "--category", "tax"]
    )
    assert captured["concepts"] == (Concepts.SNAP_BENEFIT,)
    assert captured["loader_kwargs"]["case_unit"] == "household"
