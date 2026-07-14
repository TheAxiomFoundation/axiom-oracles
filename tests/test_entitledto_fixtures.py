"""Shipped entitledto UK-CTR fixtures: suite integrity, validity, no drift."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from axiom_oracles.adapters.entitledto import (
    CAPTURE_STATUS_PENDING,
    EntitledToInputMapper,
    load_captures_by_id,
    validate_capture,
)
from axiom_oracles.adapters.entitledto.recorded import DEFAULT_FIXTURES_DIR
from axiom_oracles.suites import available_suites, load_suite
from axiom_oracles.suites.uk_ctr import uk_ctr_cases

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_generator():
    path = _REPO_ROOT / "scripts" / "generate_uk_ctr_entitledto_fixtures.py"
    spec = importlib.util.spec_from_file_location("gen_uk_ctr", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_suite_registered_and_uk_scoped() -> None:
    assert "uk-ctr" in available_suites()
    cases = load_suite("uk-ctr")
    assert len(cases) == 8
    assert {c.locale for c in cases} == {"UK"}
    # Ids are unique and stable.
    ids = [str(c.case_id) for c in cases]
    assert len(set(ids)) == len(ids)


def test_suite_spans_all_ctr_schemes() -> None:
    schemes = {c.metadata["ctr_scheme"] for c in uk_ctr_cases()}
    assert {
        "england-pension-age-prescribed",
        "scotland-working-age-national",
        "wales-working-age-national",
        "kingston-upon-thames-working-age-local",
        "manchester-working-age-local",
        "birmingham-working-age-local",
    } <= schemes


def test_three_councils_share_one_income_profile() -> None:
    # Scotland (national), Kingston (supported local) and Manchester (unsupported)
    # share an identical single-renter £11k profile, so one income point exposes
    # three schemes — the per-council variation the oracle measures.
    by_id = {c.case_id: c for c in uk_ctr_cases()}
    trio = [
        by_id["ctr-sco-wa-glasgow-single-earner"],
        by_id["ctr-eng-wa-kingston-single-earner"],
        by_id["ctr-eng-wa-manchester-single-earner"],
    ]
    for case in trio:
        assert case.metadata["claimant_employment_income"] == 11000.0
        assert case.metadata["couple"] is False
        assert case.metadata["tenure"] == "private_rent"


def test_every_shipped_fixture_is_a_valid_pending_stub() -> None:
    captures = load_captures_by_id()
    assert set(captures) == {str(c.case_id) for c in uk_ctr_cases()}
    for case_id, capture in captures.items():
        assert capture.capture_status == CAPTURE_STATUS_PENDING, case_id
        assert capture.outputs is None, case_id
        # Provenance is complete even while pending, so a reviewer knows exactly
        # which council/scheme/year each stub is for.
        assert validate_capture(capture) == [], (case_id, validate_capture(capture))


def test_fixture_inputs_equal_the_mapper_projection() -> None:
    mapper = EntitledToInputMapper()
    captures = load_captures_by_id()
    for case in uk_ctr_cases():
        capture = captures[str(case.case_id)]
        assert capture.inputs == mapper.map_case(case), case.case_id


def test_fixtures_are_not_stale_against_the_generator() -> None:
    # CI drift gate: the committed fixtures must equal a fresh generation.
    gen = _load_generator()
    for case in uk_ctr_cases():
        rendered = gen._render(gen.build_fixture(case))
        path = DEFAULT_FIXTURES_DIR / f"{case.case_id}.json"
        assert path.read_text() == rendered, (
            f"{path.name} is stale; run "
            "scripts/generate_uk_ctr_entitledto_fixtures.py"
        )
