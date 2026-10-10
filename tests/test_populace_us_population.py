import hashlib
import types

import pytest

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
    """Same cleaning as the shared table: the loader never floors (the
    pinned artifact has no negative tax-exempt interest; floors belong to
    the projections)."""

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
