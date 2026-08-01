"""Tests for the canonical per-jurisdiction case grids.

Three guarantees, matching the O5 brief:

1. *Schema validation* — every checked-in ``grids/<jurisdiction>.yaml`` parses
   under the v1 schema and passes structural validation.
2. *Extraction equivalence* — each grid case set reconstructs, field by field,
   to the exact skeleton of the live suite it was extracted from. This is the
   byte-preserving proof: the grids and the suites describe the identical case
   list, so no comparison report can shift.
3. *Generator determinism* — the extractor and the boundary-case generator are
   idempotent (``--check`` is clean against the committed files).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from axiom_oracles.grids import (
    GRID_SCHEMA_VERSION,
    load_grid,
    load_grids,
    resolve_grid_case_set,
)
from axiom_oracles.grids.extract import case_skeleton, grid_case_from_spec
from axiom_oracles.grids.model import DEFAULT_GRID_ROOT
from axiom_oracles.suites import available_suites, load_suite

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GRID_ROOT = _REPO_ROOT / "grids"


# ---------------------------------------------------------------------------
# 1. Schema validation
# ---------------------------------------------------------------------------


def test_grid_root_matches_repo_grids_dir() -> None:
    # The packaged default root must resolve to the checked-in grids/ dir so
    # load_grids() finds the committed files without an override.
    assert DEFAULT_GRID_ROOT == _GRID_ROOT


def test_every_grid_file_parses_and_validates() -> None:
    grids = load_grids()
    assert grids, "expected at least one grids/<jurisdiction>.yaml"
    for grid in grids:
        assert grid.schema_version == GRID_SCHEMA_VERSION
        assert grid.validate() == []
        assert grid.case_sets, f"{grid.jurisdiction}: no case sets"


def test_expected_jurisdictions_present() -> None:
    jurisdictions = {grid.jurisdiction for grid in load_grids()}
    # us and be are extracted from suites on main; uk ships ahead of the UKMOD
    # suites landing (its equivalence check is guarded below). de and dk pin the
    # German dual-oracle and Denmark EUROMOD grids respectively.
    assert {"us", "be", "de", "dk"} <= jurisdictions


@pytest.mark.parametrize(
    "jurisdiction,expected_sets,expected_cases",
    [
        ("us", 3, 84),
        ("be", 30, 128),
        ("de", 1, 13),
        ("uk", 26, 143),
        ("dk", 1, 7),
    ],
)
def test_grid_case_counts(jurisdiction, expected_sets, expected_cases) -> None:
    grid = load_grid(jurisdiction)
    assert len(grid.case_sets) == expected_sets
    total = sum(len(case_set.cases) for case_set in grid.case_sets)
    assert total == expected_cases


def test_suggested_files_are_not_loaded_as_grids() -> None:
    # The generator writes grids/<cc>.suggested.yaml; load_grids() must ignore
    # them so proposals never enter the adopted set.
    names = {grid.jurisdiction for grid in load_grids()}
    assert not any(name.endswith(".suggested") for name in names)


# ---------------------------------------------------------------------------
# 2. Extraction equivalence — the byte-preserving proof
# ---------------------------------------------------------------------------


def _assert_case_set_matches_suite(jurisdiction: str, suite_name: str) -> None:
    grid = load_grid(jurisdiction)
    case_set = grid.case_set(suite_name)
    assert case_set is not None, f"{jurisdiction}: missing case set {suite_name!r}"

    live_cases = load_suite(suite_name)
    # Same case ids, same order.
    assert [c.id for c in case_set.cases] == [str(c.case_id) for c in live_cases]

    for spec, live in zip(case_set.cases, live_cases, strict=True):
        reconstructed = grid_case_from_spec(spec, case_set)
        expected = case_skeleton(live)
        assert reconstructed == expected, (
            f"{jurisdiction}/{suite_name}/{spec.id}: grid skeleton diverged from suite"
        )


def _suite_jurisdiction(suite_name: str) -> str:
    cases = load_suite(suite_name)
    locales = {case.locale for case in cases}
    if locales == {"BE"}:
        return "be"
    if locales == {"CA-ON"}:
        return "ca"
    if locales == {"DK"}:
        return "dk"
    if locales == {"DE"}:
        return "de"
    if locales == {"UK"}:
        return "uk"
    if locales <= {"US-NY-NYC", "US-NY", "US"}:
        return "us"
    raise AssertionError(f"unmapped locales for {suite_name}: {locales}")


@pytest.mark.parametrize("suite_name", sorted(available_suites()))
def test_grid_case_set_is_byte_preserving_extraction_of_suite(suite_name) -> None:
    jurisdiction = _suite_jurisdiction(suite_name)
    _assert_case_set_matches_suite(jurisdiction, suite_name)


def test_uk_grid_is_present_and_covers_the_worker_suites() -> None:
    # UK worker suites ship on main (UKMOD #127). The parametrized equivalence
    # test above already covers each UK suite; this pins the specific sets and
    # their live case-id order so a UK regression is unmistakable. Guarded so
    # the file still passes on an older checkout without the UK suites.
    if "uk-worker-pit" not in available_suites():
        pytest.skip("UK worker suites not present in this checkout")

    grid = load_grid("uk")
    for suite_name in (
        "uk-worker-pit",
        "uk-worker-nic",
        "uk-self-employed-nic",
        "uk-employer-nic",
        "uk-universal-credit",
        "uk-pension-credit",
        "uk-income-tax-savings",
        "uk-income-tax-dividend",
        "uk-income-tax-mixed",
    ):
        case_set = grid.case_set(suite_name)
        assert case_set is not None, f"grids/uk.yaml missing {suite_name!r}"
        live_cases = load_suite(suite_name)
        assert [c.id for c in case_set.cases] == [str(c.case_id) for c in live_cases]
        for spec, live in zip(case_set.cases, live_cases, strict=True):
            assert grid_case_from_spec(spec, case_set) == case_skeleton(live)


def test_mixed_entity_set_is_not_lifted_and_round_trips() -> None:
    # A set where only some cases carry an entity must keep per-case values, so
    # the reconstruction never re-inlines a default onto the entity-less case.
    from axiom_oracles.core.case import Case, Concepts, Entity
    from axiom_oracles.grids.extract import case_set_skeleton, case_skeleton
    from axiom_oracles.grids.model import _case_set_from_payload

    cases = [
        Case(
            case_id="with-entity",
            period="2026",
            metadata={"axiom_entity": "Household", "axiom_entity_id": "household"},
            entities=(Entity("head", "person", {Concepts.PERSON_AGE: 40}),),
        ),
        Case(
            case_id="without-entity",
            period="2026",
            entities=(Entity("head", "person", {Concepts.PERSON_AGE: 30}),),
        ),
    ]
    body = case_set_skeleton("mixed", cases)
    # entity must NOT be lifted to the set (one case lacks it).
    assert "entity" not in body
    assert "entity_id" not in body

    case_set = _case_set_from_payload("mixed", body, source_file=Path("mixed.yaml"))
    for spec, live in zip(case_set.cases, cases, strict=True):
        assert grid_case_from_spec(spec, case_set) == case_skeleton(live)


def test_divergent_entity_and_outputs_are_not_lifted_and_round_trip() -> None:
    # Present in every case but with different values: must stay per-case, and
    # the outputs-lifting path must resist the same mixed-presence hazard the
    # entity path guards against.
    from axiom_oracles.core.case import Case, Concepts, Entity
    from axiom_oracles.grids.extract import case_set_skeleton, case_skeleton
    from axiom_oracles.grids.model import _case_set_from_payload

    cases = [
        Case(
            case_id="taxunit-x",
            period="2026",
            metadata={"axiom_entity": "TaxUnit"},
            outputs=("us:x#y",),
            entities=(Entity("h", "person", {Concepts.PERSON_AGE: 40}),),
        ),
        Case(
            case_id="household-p",
            period="2026",
            metadata={"axiom_entity": "Household"},
            outputs=("us:p#q",),
            entities=(Entity("h", "person", {Concepts.PERSON_AGE: 30}),),
        ),
    ]
    body = case_set_skeleton("divergent", cases)
    assert "entity" not in body
    assert "outputs" not in body

    case_set = _case_set_from_payload("divergent", body, source_file=Path("x.yaml"))
    for spec, live in zip(case_set.cases, cases, strict=True):
        assert grid_case_from_spec(spec, case_set) == case_skeleton(live)


def test_shared_outputs_are_lifted_to_set_level() -> None:
    # The DRY payoff: a constant non-empty output surface is lifted once to the
    # set and dropped from each case, and still reconstructs exactly.
    from axiom_oracles.core.case import Case, Concepts, Entity
    from axiom_oracles.grids.extract import case_set_skeleton, case_skeleton
    from axiom_oracles.grids.model import _case_set_from_payload

    cases = [
        Case(
            case_id=f"c{i}",
            period="2026",
            outputs=("us:x#y",),
            entities=(Entity("h", "person", {Concepts.PERSON_AGE: 40 + i}),),
        )
        for i in range(2)
    ]
    body = case_set_skeleton("shared", cases)
    assert body["outputs"] == ["us:x#y"]
    assert all("outputs" not in case for case in body["cases"])

    case_set = _case_set_from_payload("shared", body, source_file=Path("x.yaml"))
    for spec, live in zip(case_set.cases, cases, strict=True):
        assert grid_case_from_spec(spec, case_set) == case_skeleton(live)


def test_mixed_locale_case_set_is_rejected() -> None:
    # A case set is single-jurisdiction; a mixed-locale set would lose per-case
    # locale silently, so extraction must reject it loudly.
    from axiom_oracles.core.case import Case
    from axiom_oracles.grids.extract import case_set_skeleton

    cases = [
        Case("a", "2026", metadata={"locale": "BE", "scope": {"type": "country", "geoid": "BE"}}),
        Case("b", "2026", metadata={"locale": "UK", "scope": {"type": "country", "geoid": "UK"}}),
    ]
    with pytest.raises(ValueError, match="mixes locales"):
        case_set_skeleton("mixed-locale", cases)


def test_colliding_fact_fragments_are_rejected() -> None:
    # Two concepts whose id fragments collide on the same short grid key must
    # raise rather than silently overwrite (the fragment-fallback landmine).
    from axiom_oracles.core.case import Case, Concepts
    from axiom_oracles.grids.extract import case_skeleton

    case = Case(
        "collide",
        "2026",
        facts={
            Concepts.MEDICAID_ELIGIBLE: True,
            Concepts.CHILD_HEALTH_PLUS_ELIGIBLE: True,  # both fragment to 'eligible'
        },
    )
    with pytest.raises(ValueError, match="collides"):
        case_skeleton(case)


def test_every_registered_suite_has_a_grid_case_set() -> None:
    # No suite is left out of the canonical grids: every registered suite
    # appears as a grid case set of the same name in its jurisdiction's grid.
    for suite_name in available_suites():
        jurisdiction = _suite_jurisdiction(suite_name)
        grid = load_grid(jurisdiction)
        assert grid.case_set(suite_name) is not None, (
            f"suite {suite_name!r} has no grid case set in {jurisdiction}.yaml"
        )


# ---------------------------------------------------------------------------
# 2b. Case-set references (the "configs reference grids, not inline cases" hook)
# ---------------------------------------------------------------------------


def test_resolve_qualified_case_set_reference() -> None:
    grid, case_set = resolve_grid_case_set("be:be-worker-pit")
    assert grid.jurisdiction == "be"
    assert case_set.name == "be-worker-pit"
    assert [c.id for c in case_set.cases] == [
        "be-worker-pit-10k",
        "be-worker-pit-30k",
        "be-worker-pit-60k",
    ]


def test_resolve_bare_case_set_reference() -> None:
    _grid, case_set = resolve_grid_case_set("nyc-synthetic")
    assert case_set.name == "nyc-synthetic"
    assert len(case_set.cases) == 40


def test_resolve_unknown_case_set_raises() -> None:
    with pytest.raises(KeyError):
        resolve_grid_case_set("does-not-exist")


def test_every_suite_name_is_resolvable_as_a_case_set_reference() -> None:
    # The reference mechanism that lets a comparison config point at a canonical
    # grid case set (instead of inlining cases) resolves for every suite.
    for suite_name in available_suites():
        _grid, case_set = resolve_grid_case_set(suite_name)
        assert case_set.name == suite_name


# ---------------------------------------------------------------------------
# 3. Generator determinism
# ---------------------------------------------------------------------------


def test_extractor_is_idempotent() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/extract_grids.py", "--check"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "grids/*.yaml out of date; run scripts/extract_grids.py\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_boundary_gate_degrades_cleanly() -> None:
    # The CI-safe guarantee: --check exits 0 whether or not the axiom-corpus
    # checkout is present. When present it enforces determinism (below); when
    # absent the committed suggestions stand alone. This test only asserts the
    # graceful-degradation half, so its meaning does not silently change with
    # the runner's filesystem — see test_boundary_generator_is_deterministic
    # for the real determinism check.
    result = subprocess.run(
        [sys.executable, "scripts/generate_boundary_cases.py", "--check"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "grids/*.suggested.yaml out of date; run "
        "scripts/generate_boundary_cases.py\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_boundary_generator_is_deterministic() -> None:
    # The real determinism check: regenerate the suggestions into a scratch
    # directory from the live corpus and assert byte-identical output to the
    # committed files. Requires the axiom-corpus checkout; skips visibly (rather
    # than passing vacuously) when it is absent, so the coverage gap is named.
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_gen_boundary", _REPO_ROOT / "scripts" / "generate_boundary_cases.py"
    )
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)

    registry_root = gen._discover_registry_root()
    if registry_root is None or not registry_root.is_dir():
        pytest.skip("axiom-corpus concept registry not available in this checkout")

    # Regenerate from build_suggestions and compare content to the committed
    # files, without touching them.
    payloads = gen.build_suggestions(registry_root, gen._DEFAULT_JURISDICTIONS)
    assert payloads, "corpus present but generator produced no suggestions"
    for jurisdiction, payload in payloads.items():
        rendered = gen._dump(payload)
        committed = _GRID_ROOT / f"{jurisdiction}.suggested.yaml"
        assert committed.exists(), (
            f"generator produced {jurisdiction} suggestions but "
            f"grids/{jurisdiction}.suggested.yaml is not committed"
        )
        assert rendered == committed.read_text(), (
            f"grids/{jurisdiction}.suggested.yaml differs from a fresh "
            "regeneration; run scripts/generate_boundary_cases.py"
        )
        # Determinism proper: a second independent render is byte-identical.
        second = gen._dump(gen.build_suggestions(registry_root, (jurisdiction,))[jurisdiction])
        assert rendered == second


def _load_boundary_gen():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_gen_boundary", _REPO_ROOT / "scripts" / "generate_boundary_cases.py"
    )
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    return gen


def _write_registry(tmp_path: Path, jurisdiction: str, concepts: list[dict]) -> Path:
    root = tmp_path / "data"
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{jurisdiction}.yaml").write_text(
        yaml.safe_dump({"concepts": concepts}, sort_keys=False)
    )
    return root


def _mapped_concept(name: str, engine: str, parameter: str, *, dtype="Money") -> dict:
    return {
        "id": f"test:{name}",
        "kind": "output",
        "name": name,
        "dtype": dtype,
        "mappings": {
            engine: {
                "mapping_type": "parameter_value",
                "parameter": parameter,
                "program": "income_tax",
            }
        },
    }


def test_uk_boundary_allowlist_surfaces_mapped_allowance_style_concepts(tmp_path) -> None:
    # #135: an "allowance"-style boundary the GLOBAL threshold regex does not
    # catch (no threshold/limit/bracket token) must be surfaced for UK once it
    # carries a parameter_value mapping. Proven against a synthetic registry so
    # the test does not depend on the live corpus mapping these yet.
    gen = _load_boundary_gen()
    for name, param in [
        ("savings_allowance", "gov.hmrc.income_tax.allowances.personal_savings_allowance.basic"),
        ("dividend_nil_rate_allowance", "gov.hmrc.income_tax.allowances.dividend_allowance"),
        ("applicable_work_allowance_amount", "gov.dwp.universal_credit.means_test.work_allowance"),
        ("prescribed_capital_limit_for_single_claimant", "gov.dwp.universal_credit.means_test.capital.limit"),
    ]:
        # Sanity: the global regex genuinely does NOT match these names, so the
        # allowlist is doing the work (guards against the test passing because
        # the base regex already caught it).
        assert not gen._THRESHOLD_NAME.search(name), name
        concept = _mapped_concept(name, "policyengine_uk", param)
        root = _write_registry(tmp_path, "uk", [concept])
        payload = gen.build_suggestions(root, ("uk",))["uk"]
        emitted = {
            case["probe"]["concept"]
            for cs in payload["case_sets"].values()
            for case in cs["cases"]
        }
        assert f"test:{name}" in emitted, f"UK allowlist did not surface {name}"


def test_us_does_not_inherit_uk_boundary_allowlist(tmp_path) -> None:
    # The scoping requirement: the same allowance-style concept under US must NOT
    # surface (US uses only the global regex), so broadening UK never balloons US.
    gen = _load_boundary_gen()
    concept = _mapped_concept(
        "savings_allowance", "policyengine_us", "gov.irs.something.allowance"
    )
    root = _write_registry(tmp_path, "us", [concept])
    payload = gen.build_suggestions(root, ("us",))
    # No case sets at all (the sole concept was filtered) — US stays untouched.
    assert "us" not in payload or not payload["us"]["case_sets"]


def test_global_threshold_regex_still_applies_to_all_jurisdictions(tmp_path) -> None:
    # The allowlist is additive: a genuinely threshold-named concept still
    # surfaces for both US and UK (the base behaviour is preserved).
    gen = _load_boundary_gen()
    for jurisdiction, engine in [("us", "policyengine_us"), ("uk", "policyengine_uk")]:
        concept = _mapped_concept(
            "income_limit", engine, "gov.x.income_limit"
        )
        root = _write_registry(tmp_path, jurisdiction, [concept])
        payload = gen.build_suggestions(root, (jurisdiction,))[jurisdiction]
        emitted = {
            case["probe"]["concept"]
            for cs in payload["case_sets"].values()
            for case in cs["cases"]
        }
        assert "test:income_limit" in emitted


def test_us_suggestions_byte_identical_after_allowlist_change() -> None:
    # #135 acceptance: the scoped allowlist must leave US output byte-identical.
    # Regenerate US from the live corpus and compare to the committed file;
    # skips visibly when the corpus checkout is absent.
    gen = _load_boundary_gen()
    registry_root = gen._discover_registry_root()
    if registry_root is None or not registry_root.is_dir():
        pytest.skip("axiom-corpus concept registry not available in this checkout")
    payload = gen.build_suggestions(registry_root, ("us",)).get("us")
    assert payload is not None, "corpus present but produced no US suggestions"
    rendered = gen._dump(payload)
    committed = (_GRID_ROOT / "us.suggested.yaml").read_text()
    assert rendered == committed, (
        "US boundary suggestions changed under the #135 allowlist — the UK-scoped "
        "tokens must not affect US output"
    )


def test_suggested_files_parse_and_carry_probe_provenance() -> None:
    # The suggestion files are valid YAML under the same schema version, and
    # every suggested case names the concept, PolicyEngine parameter, and side
    # it probes so a reviewer can act on it without this run's context.
    suggested = sorted(_GRID_ROOT.glob("*.suggested.yaml"))
    assert suggested, "expected at least grids/us.suggested.yaml"
    for path in suggested:
        payload = yaml.safe_load(path.read_text())
        assert payload["schema_version"] == GRID_SCHEMA_VERSION
        for case_set in payload["case_sets"].values():
            for case in case_set["cases"]:
                probe = case.get("probe")
                assert probe is not None, f"{path.name}: case {case['id']} has no probe"
                assert probe.get("concept"), f"{path.name}: probe missing concept"
                assert probe.get("parameter"), f"{path.name}: probe missing parameter"
                assert probe.get("side") in {"below", "above"}
                # The straddle value is intentionally unresolved.
                assert probe.get("value") is None


def test_suggested_case_ids_are_below_above_pairs() -> None:
    # Every probed threshold gets exactly a below/above pair, so a straddle is
    # always complete.
    for path in _GRID_ROOT.glob("*.suggested.yaml"):
        payload = yaml.safe_load(path.read_text())
        for case_set in payload["case_sets"].values():
            sides = [case["probe"]["side"] for case in case_set["cases"]]
            assert sides.count("below") == sides.count("above")


# ---------------------------------------------------------------------------
# Denmark suite/mapping pins (Sol pre-merge audit): the dk suite, its case
# count, and its Axiom<->EUROMOD concept mapping must not silently disappear.
# ---------------------------------------------------------------------------


def test_dk_child_youth_benefit_suite_pinned() -> None:
    assert "dk-child-youth-benefit" in available_suites()
    cases = load_suite("dk-child-youth-benefit")
    assert len(cases) == 7
    assert {case.locale for case in cases} == {"DK"}


def test_dk_child_youth_benefit_mapping_pinned() -> None:
    from axiom_oracles.comparison.mappings import mappings_by_concept
    from axiom_oracles.core.case import Concepts

    mapping = mappings_by_concept().get(Concepts.DK_CHILD_YOUTH_BENEFIT)
    assert mapping is not None, "dk child/youth benefit concept mapping missing"
    assert mapping.target_for_engine("euromod") == "bfachnm_s"
    assert (
        mapping.target_for_engine("axiom")
        == "single_recipient_annual_child_youth_benefit"
    )
