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
    # suites landing (its equivalence check is guarded below).
    assert {"us", "be"} <= jurisdictions


@pytest.mark.parametrize(
    "jurisdiction,expected_sets,expected_cases",
    [("us", 2, 44), ("be", 21, 91), ("uk", 8, 52)],
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
