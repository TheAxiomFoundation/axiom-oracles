"""Shipped entitledto UK-CTR fixtures: suite integrity, validity, no skeleton drift."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from axiom_oracles.adapters.entitledto import (
    CAPTURE_STATUS_CAPTURED,
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
    for cid in (
        "ctr-sco-wa-glasgow-single-earner",
        "ctr-eng-wa-kingston-single-earner",
        "ctr-eng-wa-manchester-single-earner",
    ):
        meta = by_id[cid].metadata
        assert meta["claimant_employment_income"] == 11000.0
        assert meta["couple"] is False
        assert meta["tenure"] == "private_rent"


def test_shipped_fixtures_bijection_with_suite() -> None:
    captures = load_captures_by_id()
    assert set(captures) == {str(c.case_id) for c in uk_ctr_cases()}


def test_every_shipped_fixture_is_valid_pending_or_captured() -> None:
    # Accept either a valid pending stub or a valid capture, so a legitimate
    # capture never breaks CI (the pending→captured transition must be allowed).
    for case_id, capture in load_captures_by_id().items():
        assert capture.capture_status in (
            CAPTURE_STATUS_PENDING,
            CAPTURE_STATUS_CAPTURED,
        ), case_id
        assert validate_capture(capture) == [], (case_id, validate_capture(capture))


def test_currently_shipped_fixtures_are_pending() -> None:
    # State check (not a permanent invariant): the committed fixtures are pending
    # because capture requires entitledto's written consent. When a case is
    # captured this list shrinks — expected, and the validity test above still
    # guards it.
    pending = [
        cid
        for cid, cap in load_captures_by_id().items()
        if cap.capture_status == CAPTURE_STATUS_PENDING
    ]
    assert len(pending) == 8


def test_fixture_inputs_equal_the_mapper_projection() -> None:
    mapper = EntitledToInputMapper()
    captures = load_captures_by_id()
    for case in uk_ctr_cases():
        assert captures[str(case.case_id)].inputs == mapper.map_case(case), case.case_id


def test_fixture_skeletons_are_not_stale_against_the_generator() -> None:
    # Drift gate compares only the IMMUTABLE skeleton (inputs + base provenance),
    # so a captured fixture with the same inputs still passes.
    gen = _load_generator()
    for case in uk_ctr_cases():
        committed = json.loads(
            (DEFAULT_FIXTURES_DIR / f"{case.case_id}.json").read_text()
        )
        assert gen.immutable_skeleton(committed) == gen.immutable_skeleton(
            gen.build_fixture(case)
        ), case.case_id
