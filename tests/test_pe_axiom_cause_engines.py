"""Offline ports of review 20261005-081739's malformed-engine witnesses.

Every supplied known-cause engines value must be a left/right engine pair.
Python must select the same live cause as the dashboard, even for malformed
inputs which the syntax gate then rejects.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from hypothesis import example, given, settings, strategies as st

from axiom_oracles.comparison.pe_axiom_standard import _cause_for, collect_records

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
PROPERTY_SETTINGS = settings(max_examples=150, deadline=None, derandomize=True)
ENGINE_NAMES = st.sampled_from(("axiom", "policyengine", "taxsim"))
SCALARS = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=12),
)
VALID_ENGINES = st.fixed_dictionaries({"left": ENGINE_NAMES, "right": ENGINE_NAMES})
INVALID_ENGINES = st.one_of(
    SCALARS,
    st.lists(SCALARS, max_size=4),
    st.just({}),
    st.fixed_dictionaries({"left": ENGINE_NAMES}),
    st.fixed_dictionaries({"right": ENGINE_NAMES}),
    st.fixed_dictionaries({"left": st.none(), "right": ENGINE_NAMES}),
    st.fixed_dictionaries({"left": ENGINE_NAMES, "right": st.booleans()}),
    st.fixed_dictionaries({"left": st.just(""), "right": ENGINE_NAMES}),
    st.fixed_dictionaries({"left": ENGINE_NAMES, "right": st.just("")}),
    st.fixed_dictionaries(
        {"left": ENGINE_NAMES, "right": ENGINE_NAMES, "extra": SCALARS}
    ),
)
CAUSES = st.fixed_dictionaries(
    {
        "suite": st.sampled_from(("example", "other")),
        "concept": st.sampled_from(("amount", "other")),
        "kind": st.sampled_from(("amount_difference", "other")),
    },
    optional={"engines": st.one_of(VALID_ENGINES, INVALID_ENGINES)},
)
REPORTS = st.fixed_dictionaries(
    {"suite": st.just("example")},
    optional={
        "engines": st.one_of(
            VALID_ENGINES,
            st.just({}),
            st.just({"axiom": "version", "policyengine": "version"}),
        )
    },
)

JS_CAUSE_FOR = r"""
const fs = require("fs");
const source = fs.readFileSync("dashboard/src/utils/programs.js", "utf8");
const begin = source.indexOf("export function causeFor(");
const end = source.indexOf("\n/**", begin);
if (begin < 0 || end < 0) throw new Error("causeFor source not found");
eval(source.slice(begin, end).replace("export ", ""));
const [causes, report, concept, kind] = JSON.parse(fs.readFileSync(0, "utf8"));
const picked = causeFor(causes, report, concept, kind);
console.log(JSON.stringify(causes.indexOf(picked)));
"""


def _dashboard_pick(causes, report, concept="amount", kind="amount_difference"):
    result = subprocess.run(
        [NODE, "-e", JS_CAUSE_FOR],
        cwd=ROOT,
        input=json.dumps([causes, report, concept, kind]),
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    return json.loads(result.stdout)


def _python_pick(causes, report, concept="amount", kind="amount_difference"):
    selected = _cause_for(causes, report, concept, kind)
    return next((i for i, cause in enumerate(causes) if cause is selected), -1)


def _write(root, report, causes):
    data = root / "dashboard/public/data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "report.json").write_text(json.dumps(report))
    (data / "known_causes.json").write_text(json.dumps({"entries": causes}))
    return collect_records(root)


def _cause(**fields):
    return {
        "suite": "example",
        "concept": "amount",
        "kind": "amount_difference",
        "fix_owner": "policyengine",
        **fields,
    }


MALFORMED = [
    pytest.param(None, id="null"),
    pytest.param({}, id="empty-mapping"),
    pytest.param([], id="empty-array"),
    pytest.param(["axiom", "policyengine"], id="pair-array"),
    pytest.param("policyengine", id="string"),
    pytest.param("", id="empty-string"),
    pytest.param(True, id="true"),
    pytest.param(False, id="false"),
    pytest.param(1, id="number"),
    pytest.param(0, id="zero"),
    pytest.param(1.5, id="fraction"),
    pytest.param({"left": "axiom"}, id="missing-right"),
    pytest.param({"right": "policyengine"}, id="missing-left"),
    pytest.param({"left": "", "right": "policyengine"}, id="blank-left"),
    pytest.param({"left": "axiom", "right": ""}, id="blank-right"),
    pytest.param({"left": None, "right": "policyengine"}, id="null-left"),
    pytest.param({"left": "axiom", "right": True}, id="boolean-right"),
    pytest.param(
        {"left": "axiom", "right": "policyengine", "extra": "value"},
        id="unknown-key",
    ),
]


@pytest.mark.parametrize("engines", MALFORMED)
@pytest.mark.parametrize("live", [True, False], ids=["live", "inactive"])
def test_every_supplied_malformed_engines_value_is_rejected(tmp_path, engines, live):
    report = {
        "suite": "example",
        "engines": {"axiom": "version", "policyengine": "version"},
        "summary": {"mismatch_count": int(live)},
        "mismatches": [
            {"case_id": "case", "concept": "amount", "kind": "amount_difference"}
        ]
        if live
        else [],
    }
    _, errors = _write(tmp_path, report, [_cause(engines=engines)])
    assert any("engines" in error for error in errors), errors


@pytest.mark.skipif(NODE is None, reason="node runtime not available")
@pytest.mark.parametrize("engines", [[], ["axiom", "policyengine"], "policyengine", True])
def test_malformed_engines_cannot_erase_live_policyengine_cause(tmp_path, engines):
    # Retain the review witness's real multi-engine ND report and PE row.
    report = json.loads(
        (
            ROOT
            / "dashboard/public/data/axiom-policyengine-taxsim-nd-income-tax-liability.json"
        ).read_text()
    )
    row = next(
        row
        for row in report["mismatches"]
        if "policyengine" in (row.get("left_engine"), row.get("right_engine"))
    )
    cause = {
        "suite": report["suite"],
        "concept": row["concept"],
        "kind": row["kind"],
        "fix_owner": "policyengine",
        "engines": engines,
    }
    generic = {key: value for key, value in cause.items() if key != "engines"}
    generic["fix_owner"] = "axiom"
    causes = [generic, cause]
    assert _dashboard_pick(causes, report, row["concept"], row["kind"]) == 1
    assert _python_pick(causes, report, row["concept"], row["kind"]) == 1
    records, errors = _write(tmp_path, report, causes)
    assert len(records) == 1
    assert any("engines" in error for error in errors), errors


@pytest.mark.skipif(NODE is None, reason="node runtime not available")
@PROPERTY_SETTINGS
@example(causes=[_cause(fix_owner="axiom"), _cause(engines=[])], report={"suite": "example"})
@example(causes=[_cause(engines={})], report={"suite": "example"})
@example(causes=[_cause(engines={"left": None})], report={"suite": "example"})
@given(causes=st.lists(CAUSES, max_size=10), report=REPORTS)
def test_generated_cause_selection_agrees_with_dashboard(causes, report):
    assert _python_pick(causes, report) == _dashboard_pick(causes, report)


@PROPERTY_SETTINGS
@given(engines=INVALID_ENGINES)
def test_generated_malformed_engine_values_fail_closed(tmp_path_factory, engines):
    report = {"suite": "example", "summary": {"mismatch_count": 0}, "mismatches": []}
    root = tmp_path_factory.mktemp("invalid-known-cause-engines")
    _, errors = _write(root, report, [_cause(engines=engines)])
    assert any("engines" in error for error in errors), (engines, errors)


@pytest.mark.parametrize("scoped", [False, True], ids=["generic", "engine-pair"])
def test_valid_engine_shape_remains_accepted(tmp_path, scoped):
    fields = {"engines": {"left": "axiom", "right": "policyengine"}} if scoped else {}
    report = {"suite": "example", "summary": {"mismatch_count": 0}, "mismatches": []}
    _, errors = _write(tmp_path, report, [_cause(**fields)])
    assert errors == []
