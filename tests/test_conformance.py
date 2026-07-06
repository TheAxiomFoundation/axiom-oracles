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
    _is_queryable_output,
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


@pytest.mark.parametrize("jurisdiction", ["uk", "be"])
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


def test_committed_be_scoreboard_counts_dataset_lacks_input_exclusion():
    """The live BE scoreboard's excluded-by-reason breakdown surfaces the new
    class (regression guard against the reason silently vanishing from the join)."""
    import yaml as _yaml  # noqa: F401  (json already imported at module top)
    scoreboard = json.loads((CONFORMANCE_DIR / "scoreboard.json").read_text())
    be = next(j for j in scoreboard["jurisdictions"] if j["jurisdiction"] == "be")
    assert be["excluded_by_reason"].get("oracle_dataset_lacks_input") == 1


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
