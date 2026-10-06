"""Binding invariants over the complete, registry-derived premise route space.

Exactly one route selects each premise for every subset of dispatch flags, and
dispatch invokes that route. Every pair emitting computed premises must bind
one lowercase 40-character hexadecimal commit containing a-f; missing, malformed,
or unequal commits block certification. Program sets must be comparable and equal
whenever required or present on either side. Attested premises cannot certify.
These rules include pending DE and every registered PROGRAMS entry; DE signature
alignment must not hide a mismatched closure commit. Every artifact-bearing route
rejects non-finite JSON/YAML before admitting evidence. The fixture census must
cover the registries exactly, so adding a route requires extending these proofs.

The finite route/flag/binding matrices are exhaustive. Hypothesis additionally
checks commit admission against an independent scalar predicate. Composition
tests replace route builders and unrelated premises with controlled evidence;
artifact admission tests invoke the actual builders and strict loader.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import itertools
import json
import sys
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from hypothesis import example, given, settings, strategies as st
from axiom_oracles.evidence import _reject_duplicate_json_keys, strict_json_loads


REPO = Path(__file__).resolve().parents[1]
_MODULE_SPEC = importlib.util.spec_from_file_location(
    "_certify_route_binding_tests", REPO / "scripts/certify.py"
)
assert _MODULE_SPEC is not None and _MODULE_SPEC.loader is not None
certify = importlib.util.module_from_spec(_MODULE_SPEC)
sys.modules[_MODULE_SPEC.name] = certify
_MODULE_SPEC.loader.exec_module(certify)

GOOD_COMMIT = "abcdef0123456789abcdef0123456789abcdef01"
OTHER_COMMIT = "fedcba9876543210fedcba9876543210fedcba98"
PROGRAM_SET = {"rows_sha256": "a" * 64, "program_count": 2}
MISSING = object()

# Every entry explicitly identifies its dispatch key and artifact, or the lack
# of an artifact. Neither unknown routes nor implicit fallback coverage is enough.
ROUTE_FIXTURES = {
    ("closed", "attested_receipt"): ("attested_closed_receipt", "closed.json"),
    ("closed", "producer"): ("computed.closed", "closed.json"),
    ("closed", "summary"): ("computed_closed", "summary.json"),
    ("closed", "attested"): (None, None),
    ("executable", "pending_de"): ("pending_de_candidate", None),
    ("executable", "de_status"): ("computed_de_executable", "status.json"),
    ("executable", "attested_receipt"): (
        "attested_executable_receipt",
        "executable.json",
    ),
    ("executable", "producer"): ("computed.executable", "executable.json"),
    ("executable", "unsupported"): ("computed_executable", None),
    ("executable", "attested"): (None, None),
}
ALL_ROUTES = (*certify.CLOSED_ROUTES, *certify.EXECUTABLE_ROUTES)
ROUTE_PAIRS = tuple(itertools.product(certify.CLOSED_ROUTES, certify.EXECUTABLE_ROUTES))
COMPUTED_PAIRS = tuple(
    pair for pair in ROUTE_PAIRS if all(route.can_emit_computed for route in pair)
)
DISPATCH_KEYS = tuple(
    sorted({route.dispatch_key for route in ALL_ROUTES if route.dispatch_key})
)


def _pair_id(pair):
    return "/".join(route.name for route in pair)


def _set_dispatch(spec, key, value):
    if key.startswith("computed."):
        spec.setdefault("computed", {})[key.split(".", 1)[1]] = value
    else:
        spec[key] = value


def _route_spec(route):
    key, artifact = ROUTE_FIXTURES[(route.premise, route.name)]
    spec = {}
    if key is not None:
        value = (
            {"artifact": artifact, "producer": "scripts/test-producer.py"}
            if key.startswith("computed.")
            else artifact or True
        )
        _set_dispatch(spec, key, value)
    return spec


def _pair_spec(closed_route, exec_route):
    spec = {"period": "2025", "suites": [{"suite": "binding-control"}]}
    for route in (closed_route, exec_route):
        part = _route_spec(route)
        if "computed" in part:
            spec.setdefault("computed", {}).update(part.pop("computed"))
        spec.update(part)
    return spec


def _block(route, commit=GOOD_COMMIT):
    block = {
        "mode": "computed" if route.can_emit_computed else "attested",
        "value": True,
        "status": "computed_pass" if route.can_emit_computed else "attested",
    }
    if route.premise == "closed":
        # DE alignment reads this declaration and moves rulespec_commit to
        # source_universe; the central binding must already have seen the pin.
        block["declared_sources"] = [{"citation_path": "de/statute/estg/66"}]
        if commit is not MISSING:
            block["rulespec_commit"] = commit
    elif route.name == "de_status":
        observation = {} if commit is MISSING else {"commit": commit}
        block["required_inputs"] = [
            {
                "id": "signed-rulespec-estg-66-2025",
                "state": "valid",
                "checkout_observation": observation,
            }
        ]
    elif commit is not MISSING:
        block["rulespec_sha"] = commit
    return block


def _is_commit(value):
    return (
        isinstance(value, str)
        and len(value) == 40
        and set(value) <= set("0123456789abcdef")
        and bool(set(value) & set("abcdef"))
    )


def _is_binding(blocker):
    return blocker.startswith(
        (
            "producers' rulespec provenance is not comparable:",
            "producers disagree on the rulespec commit:",
            "producers' program-set provenance is not comparable:",
            "producers disagree on the exact program set:",
        )
    )


def _replace_builders(monkeypatch, closed_block, exec_block):
    for registry, block in (
        ("CLOSED_ROUTES", closed_block),
        ("EXECUTABLE_ROUTES", exec_block),
    ):

        def build(*args, _block=block, **kwargs):
            return copy.deepcopy(_block)

        monkeypatch.setattr(
            certify,
            registry,
            tuple(replace(route, build=build) for route in getattr(certify, registry)),
        )


@pytest.fixture
def passing_other_premises(monkeypatch):
    """Make a binding failure the only possible new reason to reject a pair."""
    monkeypatch.setattr(certify, "_exercise_census_for", lambda spec: ({}, []))
    # The real _exercise_block returns (rows: dict, complete: bool).
    monkeypatch.setattr(certify, "_exercise_block", lambda *args: ({}, True))
    monkeypatch.setattr(certify, "_attested_exercise_catalog", lambda *args: None)
    monkeypatch.setattr(certify, "_single_person_evidence", lambda *args: None)
    monkeypatch.setattr(
        certify, "_nz_external_attestation_evidence", lambda *args: None
    )
    monkeypatch.setattr(
        certify,
        "_de_exercise_verdict",
        lambda *args: ({"mode": "computed", "value": True}, True),
    )
    monkeypatch.setattr(certify, "_de_census_row", lambda *args: {"blockers": []})

    def suite(entry):
        return (
            {
                "suite": entry["suite"],
                "oracle_type": "reference",
                "clean": True,
                "mismatches": 0,
                "unexplained": 0,
                "axiom_attributed_open": 0,
            },
            [],
            [],
        )

    monkeypatch.setattr(certify, "_suite_verdict", suite)
    # The tariff's reporting scope is independent of its premise bindings.
    monkeypatch.setattr(
        certify,
        "_load",
        lambda *args: {
            "scope": {
                "trajectory_quotient_label": "control",
                "limitation": "control",
                "components_only_statement": "control",
                "open": {"axiom_attributed_open_classes": {}},
            }
        },
    )


def test_registry_census_is_exact_and_routes_are_frozen():
    assert _is_commit(GOOD_COMMIT) and _is_commit(OTHER_COMMIT)
    assert {
        (route.premise, route.name) for route in ALL_ROUTES
    } == ROUTE_FIXTURES.keys()
    assert len({(route.premise, route.name) for route in ALL_ROUTES}) == len(ALL_ROUTES)
    for route in ALL_ROUTES:
        assert route.dispatch_key == ROUTE_FIXTURES[(route.premise, route.name)][0]
        assert isinstance(route.can_emit_computed, bool)
        with pytest.raises(FrozenInstanceError):
            route.name = "unregistered"


def test_every_dispatch_flag_subset_selects_exactly_one_and_dispatches_it(monkeypatch):
    for registry in ("CLOSED_ROUTES", "EXECUTABLE_ROUTES"):

        def marker(route):
            return lambda *args, **kwargs: {"selected": route.name}

        monkeypatch.setattr(
            certify,
            registry,
            tuple(
                replace(route, build=marker(route))
                for route in getattr(certify, registry)
            ),
        )
    visited = {"closed": set(), "executable": set()}
    for flags in itertools.product((False, True), repeat=len(DISPATCH_KEYS)):
        spec = {}
        for key, present in zip(DISPATCH_KEYS, flags, strict=True):
            if present:
                _set_dispatch(spec, key, {} if key.startswith("computed.") else True)
        for premise, routes, dispatch in (
            ("closed", certify.CLOSED_ROUTES, certify._closed_verdict),
            ("executable", certify.EXECUTABLE_ROUTES, certify._executable_verdict),
        ):
            selected = [route for route in routes if route.selects(spec)]
            assert len(selected) == 1, (spec, premise, selected)
            assert certify._select_route(routes, spec) is selected[0]
            assert dispatch("test/bindings", spec, []) == {"selected": selected[0].name}
            visited[premise].add(selected[0].name)
    assert visited["closed"] == {route.name for route in certify.CLOSED_ROUTES}
    assert visited["executable"] == {route.name for route in certify.EXECUTABLE_ROUTES}


@pytest.mark.parametrize(
    "closed_route,exec_route", ROUTE_PAIRS, ids=[_pair_id(p) for p in ROUTE_PAIRS]
)
def test_every_route_pair_is_reachable_and_attestation_never_certifies(
    closed_route,
    exec_route,
    monkeypatch,
    passing_other_premises,
):
    spec = _pair_spec(closed_route, exec_route)
    assert certify._select_route(certify.CLOSED_ROUTES, spec).name == closed_route.name
    assert (
        certify._select_route(certify.EXECUTABLE_ROUTES, spec).name == exec_route.name
    )
    closed, executable = _block(closed_route), _block(exec_route)
    _replace_builders(monkeypatch, closed, executable)
    certificate = certify.build_certificate("test/bindings", spec)
    assert not any(_is_binding(b) for b in certificate["blockers"])
    if not all(route.can_emit_computed for route in (closed_route, exec_route)):
        assert certificate["certified"]["state"] != "yes"
    elif exec_route.name != "pending_de":
        assert certificate["certified"]["state"] == "yes"


COMMIT_CASES = (
    (GOOD_COMMIT, GOOD_COMMIT, None),
    (GOOD_COMMIT, OTHER_COMMIT, "disagree"),
    *(
        case
        for bad in ("6" * 40, GOOD_COMMIT.upper(), 6 * 10**39, None, MISSING)
        for case in (
            (bad, GOOD_COMMIT, "not comparable"),
            (GOOD_COMMIT, bad, "not comparable"),
            (bad, bad, "not comparable"),
        )
    ),
)


@pytest.mark.parametrize(
    "closed_route,exec_route", COMPUTED_PAIRS, ids=[_pair_id(p) for p in COMPUTED_PAIRS]
)
@pytest.mark.parametrize("closed_commit,exec_commit,marker", COMMIT_CASES)
def test_computed_pair_commit_matrix_blocks_certificate(
    closed_route,
    exec_route,
    closed_commit,
    exec_commit,
    marker,
    monkeypatch,
    passing_other_premises,
):
    spec = _pair_spec(closed_route, exec_route)
    closed, executable = (
        _block(closed_route, closed_commit),
        _block(exec_route, exec_commit),
    )
    blockers = certify._cross_premise_blockers(
        spec, closed_route, closed, exec_route, executable
    )
    assert (not blockers) if marker is None else any(marker in b for b in blockers)
    _replace_builders(monkeypatch, closed, executable)
    certificate = certify.build_certificate("test/bindings", spec)
    if marker is not None:
        assert certificate["certified"]["state"] != "yes"
        assert any(marker in b for b in certificate["blockers"])
    elif exec_route.name != "pending_de":
        assert certificate["certified"]["state"] == "yes"


PROGRAM_SET_CASES = (
    (False, MISSING, MISSING, None),
    (True, MISSING, MISSING, "not comparable"),
    (False, PROGRAM_SET, MISSING, "not comparable"),
    (False, MISSING, PROGRAM_SET, "not comparable"),
    (False, None, None, "not comparable"),
    (False, PROGRAM_SET, PROGRAM_SET, None),
    (True, PROGRAM_SET, PROGRAM_SET, None),
    (False, PROGRAM_SET, {**PROGRAM_SET, "rows_sha256": "b" * 64}, "disagree"),
    (False, PROGRAM_SET, {**PROGRAM_SET, "program_count": 3}, "disagree"),
    *(
        case
        for field, invalid in (
            ("rows_sha256", "A" * 64),
            ("rows_sha256", "g" * 64),
            ("rows_sha256", "a" * 63),
            ("rows_sha256", None),
            ("rows_sha256", 123),
            ("program_count", True),
            ("program_count", "2"),
            ("program_count", 2.0),
            ("program_count", None),
            ("program_count", 0),
            ("program_count", -1),
        )
        for malformed in ({**PROGRAM_SET, field: invalid},)
        for case in (
            (False, malformed, PROGRAM_SET, "not comparable"),
            (False, PROGRAM_SET, malformed, "not comparable"),
            (False, malformed, malformed, "not comparable"),
        )
    ),
    (True, {}, {}, "not comparable"),
)


@pytest.mark.parametrize(
    "closed_route,exec_route", COMPUTED_PAIRS, ids=[_pair_id(p) for p in COMPUTED_PAIRS]
)
@pytest.mark.parametrize("required,closed_set,exec_set,marker", PROGRAM_SET_CASES)
def test_computed_pair_program_set_matrix_blocks_certificate(
    closed_route,
    exec_route,
    required,
    closed_set,
    exec_set,
    marker,
    monkeypatch,
    passing_other_premises,
):
    spec = _pair_spec(closed_route, exec_route)
    spec["require_program_set_binding"] = required
    closed, executable = _block(closed_route), _block(exec_route)
    for block, value in ((closed, closed_set), (executable, exec_set)):
        if value is not MISSING:
            block["program_set"] = copy.deepcopy(value)
    blockers = certify._cross_premise_blockers(
        spec, closed_route, closed, exec_route, executable
    )
    assert (not blockers) if marker is None else any(marker in b for b in blockers)
    _replace_builders(monkeypatch, closed, executable)
    certificate = certify.build_certificate("test/bindings", spec)
    if marker is not None:
        assert certificate["certified"]["state"] != "yes"
        assert any(marker in b for b in certificate["blockers"])
    elif exec_route.name != "pending_de":
        assert certificate["certified"]["state"] == "yes"


@pytest.mark.parametrize(
    "closed_route,exec_route", COMPUTED_PAIRS, ids=[_pair_id(p) for p in COMPUTED_PAIRS]
)
@settings(max_examples=100, deadline=None)
@given(
    value=st.one_of(
        st.text(max_size=60),
        st.integers(),
        st.none(),
        st.booleans(),
        st.floats(),
        st.text(alphabet="0123456789abcdef", min_size=40, max_size=40),
        st.text(alphabet="0123456789", min_size=40, max_size=40),
    ),
    side=st.sampled_from(("closed", "executable", "both")),
)
@example(value="a" + "0" * 39, side="both")
@example(value="0" * 40, side="both")
@example(value="A" + "0" * 39, side="both")
@example(value=GOOD_COMMIT + "\n", side="both")
def test_commit_shape_property_across_every_computed_pair(
    closed_route, exec_route, value, side
):
    closed_commit = value if side in {"closed", "both"} else GOOD_COMMIT
    exec_commit = value if side in {"executable", "both"} else GOOD_COMMIT
    blockers = certify._cross_premise_blockers(
        {},
        closed_route,
        _block(closed_route, closed_commit),
        exec_route,
        _block(exec_route, exec_commit),
    )
    admitted = _is_commit(closed_commit) and _is_commit(exec_commit)
    assert bool(blockers) == (not admitted or closed_commit != exec_commit)
    if not admitted:
        assert any("not comparable" in b for b in blockers)


@pytest.mark.parametrize("program", tuple(certify.PROGRAMS))
@pytest.mark.parametrize("commit", (GOOD_COMMIT, OTHER_COMMIT, "6" * 40, None))
def test_every_registered_program_composes_the_binding_gate(
    program,
    commit,
    monkeypatch,
    passing_other_premises,
):
    spec = copy.deepcopy(certify.PROGRAMS[program])
    closed_route = certify._select_route(certify.CLOSED_ROUTES, spec)
    exec_route = certify._select_route(certify.EXECUTABLE_ROUTES, spec)
    assert (closed_route.premise, closed_route.name) in ROUTE_FIXTURES
    assert (exec_route.premise, exec_route.name) in ROUTE_FIXTURES
    closed, executable = _block(closed_route), _block(exec_route, commit)
    if spec.get("require_program_set_binding"):
        closed["program_set"] = executable["program_set"] = PROGRAM_SET
    _replace_builders(monkeypatch, closed, executable)
    certificate = certify.build_certificate(program, spec)
    both_computed = closed_route.can_emit_computed and exec_route.can_emit_computed
    binding_blockers = [b for b in certificate["blockers"] if _is_binding(b)]
    if both_computed and commit != GOOD_COMMIT:
        assert certificate["certified"]["state"] != "yes"
        marker = "disagree" if commit == OTHER_COMMIT else "not comparable"
        assert any(marker in b for b in binding_blockers), (program, certificate)
    else:
        assert not binding_blockers, (program, certificate)
    if not both_computed:
        assert certificate["certified"]["state"] != "yes"


def test_pending_de_real_executable_route_exposes_no_comparable_commit():
    route = next(
        route for route in certify.EXECUTABLE_ROUTES if route.name == "pending_de"
    )
    block = route.build("de/pending", _route_spec(route), [])
    assert block["mode"] == "computed"
    assert route.commit_of(block) is None
    for closed_route in certify.CLOSED_ROUTES:
        if closed_route.can_emit_computed:
            blockers = certify._cross_premise_blockers(
                {},
                closed_route,
                _block(closed_route),
                route,
                block,
            )
            assert any("not comparable" in blocker for blocker in blockers)


@pytest.mark.parametrize("program", tuple(certify.PROGRAMS))
def test_real_program_premises_expose_the_committed_provenance(program, monkeypatch):
    """Exercise artifact-to-block projections, including DE before alignment.

    Only DE's platform-dependent engine replay is substituted by its committed
    status; its certificate adapter and every other premise builder run normally.
    """
    spec = certify.PROGRAMS[program]
    original_generator = certify._load_generator

    def generator(name, path):
        if path.name == "de_executable.py":
            status = certify._load(REPO / spec["computed_de_executable"])
            return SimpleNamespace(build_status=lambda: copy.deepcopy(status))
        return original_generator(name, path)

    monkeypatch.setattr(certify, "_load_generator", generator)
    closed_route = certify._select_route(certify.CLOSED_ROUTES, spec)
    exec_route = certify._select_route(certify.EXECUTABLE_ROUTES, spec)
    closed = certify._closed_verdict(program, spec, [])
    executable = certify._executable_verdict(program, spec, [])
    committed = certify._load(
        REPO / "certificates" / (program.replace("/", "-") + ".json")
    )
    for route, block in ((closed_route, closed), (exec_route, executable)):
        assert (block["mode"] == "computed") is route.can_emit_computed
        assert route.commit_of(block) == route.commit_of(
            committed["verdicts"][route.premise]
        )
    blockers = certify._cross_premise_blockers(
        spec, closed_route, closed, exec_route, executable
    )
    if spec.get("pending_de_candidate"):
        assert len(blockers) == 1 and "not comparable" in blockers[0]
    else:
        assert blockers == []
    if closed_route.can_emit_computed and exec_route.can_emit_computed:
        assert _is_commit(closed_route.commit_of(closed))
        # Change just the executable commit at the actual route's exposed field.
        mutant = copy.deepcopy(executable)
        if exec_route.name == "de_status":
            signed = next(
                row
                for row in mutant["required_inputs"]
                if row["id"] == "signed-rulespec-estg-66-2025"
            )
            signed["checkout_observation"]["commit"] = OTHER_COMMIT
        else:
            mutant["rulespec_sha"] = OTHER_COMMIT
        assert any(
            "disagree" in blocker
            for blocker in certify._cross_premise_blockers(
                spec,
                closed_route,
                closed,
                exec_route,
                mutant,
            )
        )


@pytest.mark.parametrize("commit", (None, "6" * 40, GOOD_COMMIT))
def test_arbitrary_summary_cannot_rescue_missing_or_malformed_producer_pin(
    commit, monkeypatch
):
    monkeypatch.setattr(
        certify,
        "_producer_closed_verdict",
        lambda *args, **kwargs: {
            "mode": "computed",
            "value": True,
            "rulespec_commit": commit,
        },
    )
    monkeypatch.setattr(
        certify,
        "_rederived_closure_scope",
        lambda *args: ({}, {"rulespec_commit": OTHER_COMMIT}),
    )
    block = certify._closed_producer_verdict(
        "test/bindings", {"computed_closed": "arbitrary-summary.json"}, []
    )
    assert block["rulespec_commit"] == commit


@pytest.mark.parametrize(
    "premise,scoped",
    (("closed", False), ("closed", True), ("executable", False), ("executable", True)),
)
@pytest.mark.parametrize("program_set", (PROGRAM_SET, None))
def test_producer_projection_preserves_program_set(
    premise, scoped, program_set, tmp_path, monkeypatch
):
    """A producer cannot hide program-set evidence by returning scoped results."""
    program = "test/bindings"
    summary = {"closed" if premise == "closed" else "executable": True}
    if scoped:
        summary = {"programs": {program: summary}}
    document = {
        "computed": {},
        "rulespec_commit": GOOD_COMMIT,
        "rulespec": {"sha": GOOD_COMMIT},
        "program_set": program_set,
        "generated_facts": {
            "rulespec": {"commit": GOOD_COMMIT},
            "program_set": program_set,
        },
    }
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        certify,
        "_producer_module",
        lambda *args: SimpleNamespace(
            validate_artifact=lambda *args, **kwargs: summary
        ),
    )
    routes = certify.CLOSED_ROUTES if premise == "closed" else certify.EXECUTABLE_ROUTES
    route = next(route for route in routes if route.name == "producer")
    spec = _route_spec(route)
    (tmp_path / spec["computed"][premise]["artifact"]).write_text(json.dumps(document))
    block = route.build(program, spec, [])
    assert "program_set" in block and block["program_set"] == program_set


@pytest.mark.parametrize("program_set", (PROGRAM_SET, None))
def test_summary_projection_preserves_program_set(program_set, tmp_path, monkeypatch):
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    (tmp_path / "summary.json").write_text(json.dumps({"program_set": program_set}))
    route = next(route for route in certify.CLOSED_ROUTES if route.name == "summary")
    block = route.build("test/bindings", _route_spec(route), [])
    assert "program_set" in block and block["program_set"] == program_set


@pytest.mark.parametrize(
    "route", ALL_ROUTES, ids=lambda route: f"{route.premise}/{route.name}"
)
@pytest.mark.parametrize("token", ("NaN", "Infinity", "-Infinity", "1e999"))
def test_every_artifact_route_rejects_nonfinite_json(
    route, token, tmp_path, monkeypatch
):
    _key, artifact = ROUTE_FIXTURES[(route.premise, route.name)]
    if artifact is None:
        # These registry/absent-evidence routes read no artifact; the complete
        # computed matrix above still requires pending DE to fail provenance.
        assert route.name in {"attested", "unsupported", "pending_de"}
        return
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        certify,
        "_load_generator",
        lambda *args: SimpleNamespace(build_status=lambda: {}),
    )
    path = tmp_path / artifact
    path.write_text('{"nested": [{"outside_admitted_fields": ' + token + "}]}")
    with pytest.raises(ValueError, match="non-finite|non-standard|NaN|Infinity"):
        route.build("test/bindings", _route_spec(route), [])


@pytest.mark.parametrize("premise", ("closed", "executable"))
@pytest.mark.parametrize("token", (".nan", ".inf", "-.inf"))
def test_producer_routes_reject_nonfinite_yaml(premise, token, tmp_path, monkeypatch):
    routes = certify.CLOSED_ROUTES if premise == "closed" else certify.EXECUTABLE_ROUTES
    route = next(route for route in routes if route.name == "producer")
    spec = _route_spec(route)
    spec["computed"][premise]["artifact"] = "artifact.yaml"
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    (tmp_path / "artifact.yaml").write_text(
        f"nested:\n  - outside_admitted_fields: {token}\n"
    )
    with pytest.raises(ValueError, match="non-finite|nonfinite"):
        route.build("test/bindings", spec, [])


@pytest.mark.parametrize(
    "suffix,raw",
    (
        ("json", '{"v": [NaN]}'),
        ("json", '{"v": [Infinity]}'),
        ("json", '{"v": [-Infinity]}'),
        ("json", '{"v": [1e999]}'),
        ("yaml", "v: [.nan]"),
        ("yaml", "v: [.inf]"),
        ("yml", "v: [-.inf]"),
    ),
)
def test_strict_loader_rejects_nonfinite_anywhere(suffix, raw, tmp_path):
    path = tmp_path / f"artifact.{suffix}"
    path.write_text(raw)
    with pytest.raises(ValueError):
        certify._load(path)


@pytest.mark.parametrize(
    "route", ALL_ROUTES, ids=lambda route: f"{route.premise}/{route.name}"
)
def test_every_artifact_route_rejects_duplicate_json_keys(route, tmp_path, monkeypatch):
    """Bytes that name two commits must not be read as whichever came last.

    Independent review of this change (2026-09-25) reached certified=yes
    through a premise artifact carrying conflicting duplicate commit keys.
    """
    _key, artifact = ROUTE_FIXTURES[(route.premise, route.name)]
    if artifact is None:
        assert route.name in {"attested", "unsupported", "pending_de"}
        return
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        certify,
        "_load_generator",
        lambda *args: SimpleNamespace(build_status=lambda: {}),
    )
    path = tmp_path / artifact
    path.write_text(
        '{"rulespec": {"sha": "%s", "sha": "%s"}}' % (GOOD_COMMIT, "f" * 40)
    )
    with pytest.raises(ValueError, match="duplicate"):
        route.build("test/bindings", _route_spec(route), [])


def test_strict_json_rejects_duplicate_keys(tmp_path):
    path = tmp_path / "artifact.json"
    path.write_text('{"commit": "first", "nested": {"commit": 1, "commit": 2}}')
    with pytest.raises(ValueError, match="duplicate"):
        certify._load(path)


@pytest.mark.parametrize(
    "raw,reason",
    [
        ("commit: first\ncommit: second\n", "duplicate"),
        ("a: &a {commit: bad}\nb: &b {commit: good}\n<<: *a\n<<: *b\n", "merge"),
        ("a: &a {commit: bad}\nb: &b {commit: good}\n<<: [*a, *b]\n", "merge"),
        ("a: &a {commit: bad}\n<<: *a\ncommit: good\n", "merge"),
        ("a: &a {commit: bad}\ncommit: good\n<<: *a\n", "merge"),
    ],
)
def test_strict_yaml_rejects_duplicate_keys(tmp_path, raw, reason):
    path = tmp_path / "artifact.yaml"
    path.write_text(raw)
    with pytest.raises(ValueError, match=reason):
        certify._load(path)


STRICT_PRODUCERS = (
    "certify",
    "executable_reproduction",
    "exercise_census",
    "closure_ledger",
    "closure_universe",
    "nz_incomeexplorer",
    "nz_exercise_denominator",
    "nz_executable_reproduction",
    "nz_closure",
    "de_axiom_legs",
    "de_certificate_census",
    "de_unified_comparison",
    "de_executable",
    "de_closure",
    "de_closure_ledger",
    "tariff_executable_reproduction",
    "us_tariff_closure",
)


@pytest.mark.parametrize(
    "module",
    [*(f"scripts/{name}.py" for name in STRICT_PRODUCERS), "axiom_oracles/conformance/unexplained.py"],
)
def test_certify_has_no_raw_artifact_parser_outside_strict_loaders(module):
    tree = ast.parse((REPO / module).read_text())
    violations = []

    class ParserCalls(ast.NodeVisitor):
        def __init__(self):
            self.functions = []

        def visit_FunctionDef(self, node):
            self.functions.append(node.name)
            self.generic_visit(node)
            self.functions.pop()

        def visit_Call(self, node):
            function = node.func
            if isinstance(function, ast.Attribute) and isinstance(
                function.value, ast.Name
            ):
                raw = (
                    function.value.id == "json"
                    and function.attr in {"load", "loads"}
                    or function.value.id == "yaml"
                    and function.attr in {"load", "safe_load"}
                )
                if raw:
                    violations.append((node.lineno, ast.unparse(function)))
            self.generic_visit(node)

    ParserCalls().visit(tree)
    assert not violations, f"premise parsing bypasses strict admission: {violations}"


def test_premise_dispatch_cannot_branch_outside_its_registry():
    tree = ast.parse((REPO / "scripts/certify.py").read_text())
    functions = {
        node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    for name, registry in (
        ("_closed_verdict", "CLOSED_ROUTES"),
        ("_executable_verdict", "EXECUTABLE_ROUTES"),
        ("build_certificate", "CERTIFICATE_ROUTES"),
    ):
        function = functions[name]
        returns = [node for node in ast.walk(function) if isinstance(node, ast.Return)]
        assert len(returns) == 1
        expression = returns[0].value
        assert isinstance(expression, ast.Call)
        assert isinstance(expression.func, ast.Attribute)
        assert expression.func.attr == "build"
        assert ast.unparse(expression.func.value) == f"_select_route({registry}, spec)"
        # Argument compatibility may branch on evidence; premise selection
        # may not inspect spec or program anywhere outside the registry.
        for branch in (node for node in ast.walk(function) if isinstance(node, ast.If)):
            names = {node.id for node in ast.walk(branch.test) if isinstance(node, ast.Name)}
            assert not names & {"spec", "program"}


def test_certificate_dispatch_is_exhaustive_and_registry_only(monkeypatch):
    assert {(route.name, route.dispatch_key) for route in certify.CERTIFICATE_ROUTES} == {
        ("pending_de", "pending_de_candidate"), ("standard", None)
    }
    for route in certify.CERTIFICATE_ROUTES:
        with pytest.raises(FrozenInstanceError):
            route.name = "unregistered"
    monkeypatch.setattr(
        certify, "CERTIFICATE_ROUTES",
        tuple(replace(route, build=lambda *args, _name=route.name, **kwargs: {
            "selected": _name, "verify_producers": kwargs["verify_producers"],
        }) for route in certify.CERTIFICATE_ROUTES),
    )
    visited = set()
    for flags in itertools.product((False, True), repeat=len(DISPATCH_KEYS)):
        spec = {}
        for key, present in zip(DISPATCH_KEYS, flags, strict=True):
            if present:
                _set_dispatch(spec, key, {} if key.startswith("computed.") else True)
        selected = [route for route in certify.CERTIFICATE_ROUTES if route.selects(spec)]
        assert len(selected) == 1
        for verify in (False, True):
            assert certify.build_certificate("test/bindings", spec, verify_producers=verify) == {
                "selected": selected[0].name, "verify_producers": verify,
            }
        visited.add(selected[0].name)
    assert visited == {route.name for route in certify.CERTIFICATE_ROUTES}


@pytest.mark.parametrize("exec_route", certify.EXECUTABLE_ROUTES, ids=lambda r: r.name)
def test_executable_route_cannot_drop_census_or_missing_leg_blockers(
    exec_route, passing_other_premises, monkeypatch
):
    if exec_route.name == "pending_de":
        return  # Its complete certificate builder already preserves census blockers.
    closed_route = next(route for route in certify.CLOSED_ROUTES if route.name == "producer")
    spec = _pair_spec(closed_route, exec_route)
    spec["de_census_program"] = True
    monkeypatch.setattr(certify, "_de_census_row", lambda *args: {"blockers": ["census: unresolved"]})
    original = certify._suite_verdict

    def missing_leg(entry):
        leg, evidence, defects = original(entry)
        leg["missing_required_legs"] = ["axiom-vs-synthetic-leg"]
        return leg, evidence, defects

    monkeypatch.setattr(certify, "_suite_verdict", missing_leg)
    _replace_builders(monkeypatch, _block(closed_route), _block(exec_route))
    certificate = certify.build_certificate("test/bindings", spec)
    assert "census: unresolved" in certificate["blockers"]
    assert "binding-control: missing required leg axiom-vs-synthetic-leg" in certificate["blockers"]
    assert certificate["certified"]["state"] != "yes"


@pytest.mark.parametrize("first_pin", ["f" * 64, ".nan"])
def test_dk_producer_rejects_review_duplicate_engine_pin(tmp_path, first_pin):
    module = certify._load_generator(
        "_duplicate_dk_engine_pin", REPO / "scripts/executable_reproduction.py"
    )
    for row in module.REPORT_SPECS:
        relative = row["config"]
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = (REPO / relative).read_text()
        marker = "    engine_binary_sha256: "
        assert raw.count(marker) == 1
        path.write_text(raw.replace(marker, f"{marker}{first_pin}\n{marker}", 1))
    with pytest.raises(ValueError, match="duplicate YAML key.*engine_binary_sha256"):
        module._configured_engine_pin(tmp_path)


@pytest.mark.parametrize(
    "raw,reason",
    [
        ("suite: forged\nsuite: real\nbindings: []\n", "duplicate"),
        ("defaults: &a {suite: forged}\n<<: *a\nsuite: real\nbindings: []\n", "merge"),
    ],
)
def test_census_producer_rejects_ambiguous_bridge_manifest(tmp_path, monkeypatch, raw, reason):
    module = certify._load_generator(
        "_duplicate_census_bridge", REPO / "scripts/exercise_census.py"
    )
    monkeypatch.setattr(module, "MANIFEST_DIR", tmp_path)
    path = tmp_path / "bridge.yaml"
    path.write_text("suite: real\nbindings: []\n")
    assert module._bridged_through_by_suite() == {"real": {}}
    path.write_text(raw)
    with pytest.raises(ValueError, match=reason):
        module._bridged_through_by_suite()


@given(count=st.integers())
def test_program_set_cardinality_must_be_positive(count):
    closed_route = next(route for route in certify.CLOSED_ROUTES if route.name == "producer")
    exec_route = next(route for route in certify.EXECUTABLE_ROUTES if route.name == "producer")
    closed, executable = _block(closed_route), _block(exec_route)
    closed["program_set"] = executable["program_set"] = {**PROGRAM_SET, "program_count": count}
    blockers = certify._cross_premise_blockers({}, closed_route, closed, exec_route, executable)
    assert bool(blockers) is (count < 1)


@given(st.lists(st.tuples(st.text(max_size=8), st.integers()), max_size=30))
def test_strict_json_mapping_admission_preserves_unique_pairs(pairs):
    raw = "{" + ",".join(f"{json.dumps(key)}:{value}" for key, value in pairs) + "}"
    if len({key for key, _ in pairs}) != len(pairs):
        with pytest.raises(ValueError, match="duplicate JSON key"):
            strict_json_loads(raw)
    else:
        assert strict_json_loads(raw) == dict(pairs)


@given(size=st.integers(min_value=2, max_value=100))
@example(size=100)
def test_strict_json_distinct_keys_do_not_trigger_pairwise_scans(size):
    """Distinct hash-separated keys need at most linear equality comparisons."""
    class CountedKey(str):
        comparisons = 0

        def __new__(cls, ordinal):
            key = super().__new__(cls, str(ordinal))
            key.ordinal = ordinal
            return key

        def __hash__(self):
            return self.ordinal

        def __eq__(self, other):
            type(self).comparisons += 1
            return super().__eq__(other)

    pairs = [(CountedKey(index), index) for index in range(size)]
    parsed = _reject_duplicate_json_keys(pairs)
    assert CountedKey.comparisons <= size
    assert list(parsed.values()) == list(range(size))
