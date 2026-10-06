"""Dashboard bucket identifiers cannot erase a PolicyEngine attribution.

The ledger stringifies row concept/kind and then splits on ``::``. Reject
identifiers outside the unambiguous string domain before selecting causes.
"""

import copy
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from hypothesis import example, given, settings, strategies as st

from axiom_oracles.comparison.pe_axiom_standard import (
    RATCHET_RELATIVE_PATH,
    CompanionResolver,
    Ratchet,
    check_records,
    collect_records,
    derive_ratchet,
    known_cause_id,
    serialize_ratchet,
)
from axiom_oracles.comparison.report import MismatchKind
from axiom_oracles.evidence import build_chunk_index, validate_suite_evidence

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
CONCEPT = "us:policies/example#amount"
PROPERTY_SETTINGS = settings(max_examples=100, deadline=None, derandomize=True)

# Execute the actual dashboard ledger bucket builder and causeFor. The five
# stubs only supply presentation metadata; none participates in selection.
# displayEngines returns the raw engine pair: the dashboard maps it through
# platformOracle for row labels only, and cause matching keeps report.engines.
JS_BUCKETS = r"""
const fs = require("fs");
const helpers = fs.readFileSync("dashboard/src/utils/programs.js", "utf8");
const causeBegin = helpers.indexOf("export function causeFor(");
const causeEnd = helpers.indexOf("\n/**", causeBegin);
const ledger = fs.readFileSync("dashboard/src/components/OraclesV2.jsx", "utf8");
const begin = ledger.indexOf("function buildClasses(");
const end = ledger.indexOf("\nfunction ActionChip(", begin);
if ([causeBegin, causeEnd, begin, end].some(i => i < 0)) {
  throw new Error("dashboard selection source not found");
}
function topLevelAggregates(aggregates) { return aggregates || []; }
function suiteLabel(suite) { return suite; }
function suiteMeta() { return {}; }
function otherOracle() { return ""; }
function displayEngines(report) { return (report && report.engines) || {}; }
eval(helpers.slice(causeBegin, causeEnd).replace("export ", ""));
eval(ledger.slice(begin, end));
const [reports, causes] = JSON.parse(fs.readFileSync(0, "utf8"));
console.log(JSON.stringify(buildClasses(reports, causes).map(row => ({
  concept: row.concept,
  kind: row.kind,
  cause: causes.indexOf(row.cause),
}))));
"""


def _dashboard_buckets(reports, causes):
    result = subprocess.run(
        [NODE, "-e", JS_BUCKETS],
        cwd=ROOT,
        input=json.dumps([reports, causes]),
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    return json.loads(result.stdout)


def _report(**fields):
    return {
        "suite": "example",
        "engines": {"left": "axiom", "right": "policyengine"},
        "summary": {"mismatch_count": 1},
        "mismatches": [
            {
                "case_id": "case",
                "concept": CONCEPT,
                "kind": "amount_difference",
                "left": 10,
                "right": 5,
            }
        ],
        **fields,
    }


def _cause(**fields):
    return {
        "suite": "example",
        "concept": CONCEPT,
        "kind": "amount_difference",
        "fix_owner": "policyengine",
        **fields,
    }


def _write(root, report, causes, filename="report.json"):
    data = root / "dashboard/public/data"
    data.mkdir(parents=True, exist_ok=True)
    path = data / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report))
    (data / "known_causes.json").write_text(json.dumps({"entries": causes}))
    return path, collect_records(root)


def _cli(root, mode):
    spec = importlib.util.spec_from_file_location(
        "bucket_identity_cli", ROOT / "scripts/pe_axiom_standard.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main([mode], repo_root=root)


@pytest.mark.skipif(NODE is None, reason="node runtime not available")
def test_boolean_kind_cannot_hide_dashboard_policyengine_cause(tmp_path):
    report = json.loads(
        (
            ROOT / "dashboard/public/data/axiom-policyengine-co-state-supplement.json"
        ).read_text()
    )
    row = report["mismatches"][0]
    row["kind"] = True
    report["cases"][0]["mismatches"][0]["kind"] = True
    report["cases"][0]["matches"] = []
    report["concepts"][0]["relative_tolerance"] = 0
    cause = _cause(suite=report["suite"], concept=row["concept"], kind="true")
    assert _dashboard_buckets([report], [cause])[0]["cause"] == 0
    path, (_, errors) = _write(tmp_path, report, [cause])
    index = build_chunk_index(path)
    index_path = path.parent / "cases" / report["suite"] / "index.json"
    index_path.parent.mkdir(parents=True)
    index_path.write_text(json.dumps(index))
    # The general evidence validator accepts this witness, so the new gate
    # must validate the identifier on its own.
    assert validate_suite_evidence(path).valid
    ratchet_path = tmp_path / RATCHET_RELATIVE_PATH
    ratchet_path.parent.mkdir(parents=True)
    ratchet_path.write_text(serialize_ratchet(derive_ratchet([], None)))
    assert any("kind" in error for error in errors), errors
    assert _cli(tmp_path, "--check") == 1
    assert _cli(tmp_path, "--resolve") == 1


@pytest.mark.skipif(NODE is None, reason="node runtime not available")
def test_missing_summary_cannot_hide_dashboard_policyengine_cause(tmp_path):
    report, cause = _report(), _cause()
    report.pop("summary")
    assert _dashboard_buckets([report], [cause])[0]["cause"] == 0
    _, (records, errors) = _write(tmp_path, report, [cause])
    assert errors == [] and len(records) == 1
    assert check_records(records, Ratchet(open_max=1))
    ratchet_path = tmp_path / RATCHET_RELATIVE_PATH
    ratchet_path.parent.mkdir(parents=True)
    ratchet_path.write_text(serialize_ratchet(derive_ratchet([], None)))
    assert _cli(tmp_path, "--check") == 1


def _dashboard_loaded_buckets(filename, report, causes):
    prefix = JS_BUCKETS.split("const [reports, causes] =")[0]
    script = prefix + r"""
const loader = fs.readFileSync("dashboard/src/utils/data.js", "utf8");
eval(loader.replace('import { topLevelAggregates } from "./suites";', "")
  .replaceAll("export ", ""));
const [filename, report, causes] = JSON.parse(fs.readFileSync(0, "utf8"));
global.fetch = async url => {
  if (url === "/data/manifest.json") {
    return {ok: true, json: async () => ({reports: [filename]})};
  }
  if (url === "/data/" + filename) {
    return {ok: true, json: async () => report};
  }
  if (url === "/data/known_causes.json") {
    return {ok: true, json: async () => ({entries: causes})};
  }
  return {ok: false};
};
(async () => {
  const loaded = await loadOracleData();
  console.log(JSON.stringify(buildClasses(loaded.reports, loaded.knownCauses)
    .map(row => ({suite: row.suite, cause: causes.indexOf(row.cause)}))));
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    result = subprocess.run(
        [NODE, "-e", script],
        cwd=ROOT,
        input=json.dumps([filename, report, causes]),
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    return json.loads(result.stdout)


@pytest.mark.skipif(NODE is None, reason="node runtime not available")
def test_dashboard_filename_suite_alias_cannot_hide_policyengine_cause(tmp_path):
    filename = "axiom-policyengine-fl-snap-ecps.json"
    report, cause = _report(suite="nyc-synthetic"), _cause(suite="fl-snap-ecps")
    assert _dashboard_loaded_buckets(filename, report, [cause]) == [
        {"suite": "fl-snap-ecps", "cause": 0}
    ]
    _, (records, errors) = _write(tmp_path, report, [cause], filename)
    assert errors == [] and len(records) == 1
    assert records[0].suite == "fl-snap-ecps"
    assert check_records(records, Ratchet(open_max=1))


@pytest.mark.skipif(NODE is None, reason="node runtime not available")
@pytest.mark.parametrize("filename", ["nested/report.json", "nested/report.payload"])
def test_manifest_report_cannot_hide_policyengine_cause(tmp_path, filename):
    report, cause = _report(), _cause()
    assert _dashboard_loaded_buckets(filename, report, [cause]) == [
        {"suite": "example", "cause": 0}
    ]
    path, _ = _write(tmp_path, report, [cause], filename)
    data = tmp_path / "dashboard/public/data"
    (data / "manifest.json").write_text(json.dumps({"reports": [filename]}))
    assert path.is_file()
    records, errors = collect_records(tmp_path)
    assert errors == [] and len(records) == 1
    assert check_records(records, Ratchet(open_max=1))


@pytest.mark.skipif(NODE is None, reason="node runtime not available")
def test_suite_alias_uses_full_dashboard_filename(tmp_path):
    filename = "nested/axiom-policyengine-fl-snap-ecps.json"
    report, cause = _report(suite="nyc-synthetic"), _cause(suite="fl-snap-ecps")
    assert _dashboard_loaded_buckets(filename, report, [cause]) == [
        {"suite": "nyc-synthetic", "cause": -1}
    ]
    _write(tmp_path, report, [cause], filename)
    data = tmp_path / "dashboard/public/data"
    (data / "manifest.json").write_text(json.dumps({"reports": [filename]}))
    records, errors = collect_records(tmp_path)
    assert records == [] and errors == []


@pytest.mark.parametrize(
    "locator",
    [
        "nested/report.json?alias/ignored.json",
        "nested/report.json#alias",
        "nested/%72eport.json",
        "../report.json",
        "./report.json",
        "/report.json",
        "nested//report.json",
        "nested/report.json/",
        "nested\\report.json",
        "C:\\report.json",
        " report.json",
        "",
        None,
        True,
        1,
        [],
        {},
    ],
)
def test_manifest_report_locators_fail_closed(tmp_path, locator):
    _write(tmp_path, _report(), [_cause()])
    data = tmp_path / "dashboard/public/data"
    (data / "manifest.json").write_text(json.dumps({"reports": [locator]}))
    _, errors = collect_records(tmp_path)
    assert any("manifest.json" in error for error in errors), errors


@pytest.mark.parametrize("problem", ["missing", "invalid-json", "symlink", "parent-symlink"])
def test_manifest_reports_must_be_readable_literal_files(tmp_path, problem):
    data = tmp_path / "dashboard/public/data"
    _write(tmp_path, _report(), [_cause()])
    filename = "nested/report.json"
    nested = data / "nested"
    if problem == "parent-symlink":
        target = data / "actual"
        target.mkdir()
        (target / "report.json").write_text(json.dumps(_report()))
        nested.symlink_to(target, target_is_directory=True)
    else:
        nested.mkdir()
        path = nested / "report.json"
        if problem == "invalid-json":
            path.write_text("{")
        elif problem == "symlink":
            path.symlink_to(data / "report.json")
    (data / "manifest.json").write_text(json.dumps({"reports": [filename]}))
    _, errors = collect_records(tmp_path)
    assert any("missing" in error or "JSON" in error or "symlink" in error
               for error in errors), errors


@PROPERTY_SETTINGS
@given(
    directories=st.lists(st.text(alphabet="abc-_", min_size=1, max_size=8), max_size=3),
    extension=st.sampled_from((".json", ".payload")),
)
def test_generated_manifest_reports_always_attribute_once(
    tmp_path_factory, directories, extension
):
    root = tmp_path_factory.mktemp("manifest-reports")
    filename = "/".join([*directories, "report" + extension])
    _write(root, _report(), [_cause()], filename)
    data = root / "dashboard/public/data"
    (data / "manifest.json").write_text(json.dumps({"reports": [filename, filename]}))
    records, errors = collect_records(root)
    assert errors == [] and len(records) == 1
    assert check_records(records, Ratchet(open_max=1))


INVALID_IDENTIFIERS = [
    pytest.param(None, id="null"),
    pytest.param(True, id="true"),
    pytest.param(False, id="false"),
    pytest.param(0, id="zero"),
    pytest.param(1, id="integer"),
    pytest.param(1.5, id="fraction"),
    pytest.param([], id="array"),
    pytest.param({}, id="object"),
    pytest.param("", id="empty-string"),
    pytest.param(" \t", id="blank-string"),
]


@pytest.mark.parametrize("value", INVALID_IDENTIFIERS)
@pytest.mark.parametrize("field", ["suite", "concept", "kind"])
@pytest.mark.parametrize("location", ["report", "cause"])
def test_malformed_bucket_identifiers_fail_closed(tmp_path, location, field, value):
    report, cause = _report(), _cause()
    target = cause if location == "cause" else (
        report if field == "suite" else report["mismatches"][0]
    )
    target[field] = value
    _, (_, errors) = _write(tmp_path, report, [cause])
    assert any(field in error for error in errors), errors


@pytest.mark.parametrize("field", ["suite", "concept", "kind"])
@pytest.mark.parametrize("location", ["report", "cause"])
def test_missing_bucket_identifiers_fail_closed(tmp_path, location, field):
    report, cause = _report(), _cause()
    target = cause if location == "cause" else (
        report if field == "suite" else report["mismatches"][0]
    )
    target.pop(field)
    _, (_, errors) = _write(tmp_path, report, [cause])
    assert any(field in error for error in errors), errors


@pytest.mark.skipif(NODE is None, reason="node runtime not available")
@pytest.mark.parametrize("field", ["concept", "kind"])
def test_bucket_delimiter_cannot_hide_dashboard_cause(tmp_path, field):
    report, cause = _report(), _cause()
    row = report["mismatches"][0]
    if field == "concept":
        row[field] = CONCEPT + "::amount_difference"
    else:
        row[field] += "::ignored"
    assert _dashboard_buckets([report], [cause])[0]["cause"] == 0
    _, (_, errors) = _write(tmp_path, report, [cause])
    assert any(field in error and "::" in error for error in errors), errors


@pytest.mark.parametrize("field", ["concept", "kind"])
def test_inactive_cause_delimiter_is_rejected(tmp_path, field):
    report, cause = _report(), _cause()
    cause[field] += "::hidden"
    _, (_, errors) = _write(tmp_path, report, [cause])
    assert any(field in error and "::" in error for error in errors), errors


def test_kind_cannot_impersonate_scoped_grandfather_identity(tmp_path):
    report = _report()
    scoped = _cause(engines=copy.deepcopy(report["engines"]))
    _, (baseline, errors) = _write(tmp_path, report, [scoped])
    assert errors == [] and len(baseline) == 1
    ratchet = Ratchet.from_document(derive_ratchet(baseline, None))
    forged = _cause(kind="amount_difference|axiom-policyengine")
    report["mismatches"][0]["kind"] = forged["kind"]
    _, (records, errors) = _write(tmp_path, report, [forged])
    assert errors or check_records(records, ratchet)


def test_different_engine_pairs_have_distinct_cause_identity():
    first = _cause(engines={"left": "axiom", "right": "policyengine-us"})
    second = _cause(engines={"left": "axiom-policyengine", "right": "us"})
    assert known_cause_id(first) != known_cause_id(second)


@PROPERTY_SETTINGS
@example(first=("axiom", "policyengine-us"), second=("axiom-policyengine", "us"))
@example(first=("a-b", "c"), second=("a%2Db", "c"))
@example(first=("a", "b|c"), second=("a", "b%7Cc"))
@given(
    first=st.tuples(
        st.text(alphabet="ab%|-_", min_size=1, max_size=15),
        st.text(alphabet="ab%|-_", min_size=1, max_size=15),
    ),
    second=st.tuples(
        st.text(alphabet="ab%|-_", min_size=1, max_size=15),
        st.text(alphabet="ab%|-_", min_size=1, max_size=15),
    ),
)
def test_generated_engine_pair_identity_is_injective(first, second):
    first_cause = _cause(engines=dict(zip(("left", "right"), first)))
    second_cause = _cause(engines=dict(zip(("left", "right"), second)))
    assert (known_cause_id(first_cause) == known_cause_id(second_cause)) == (
        first == second
    )


def test_legacy_rows_become_validated_when_a_cause_targets_them(tmp_path):
    report = _report()
    report["schema_version"] = "axiom.comparison_report.v2"
    report["engines"]["right"] = "spsm"
    report["mismatches"][0].pop("concept")
    # The committed SPSM diagnostic has this legacy shape. It is not part of
    # attribution until an explanation for its suite is supplied.
    _, (records, errors) = _write(tmp_path, report, [])
    assert records == [] and errors == []
    _, (_, errors) = _write(tmp_path, report, [_cause(concept="undefined")])
    assert any("concept" in error for error in errors), errors


@pytest.mark.parametrize("location", ["report", "row", "annotation", "disposition-file"])
def test_legacy_shape_cannot_hide_a_trusted_bucket(tmp_path, location):
    report = _report()
    report["engines"]["right"] = "spsm"
    row = report["mismatches"][0]
    row.pop("concept")
    if location == "report":
        report["engines"]["right"] = "policyengine"
    elif location == "row":
        row.update(left_engine="axiom", right_engine="policyengine")
    elif location == "annotation":
        row["disposition"] = {"id": "gap", "disposition": "upstream_engine_gap"}
    else:
        dispositions = tmp_path / "dispositions"
        dispositions.mkdir()
        (dispositions / "example.yaml").write_text("suite: example\nentries: []\n")
    _, (_, errors) = _write(tmp_path, report, [])
    assert any("concept" in error for error in errors), errors


KINDS = tuple(
    value for key, value in vars(MismatchKind).items() if key.isupper()
) + (
    "policyengine_amount_difference",
    "judgment_difference",
    "total_difference",
    "future_unknown_kind",
)


@pytest.mark.skipif(NODE is None, reason="node runtime not available")
@pytest.mark.parametrize("kind", KINDS)
def test_every_string_kind_keeps_selected_policyengine_cause_gated(tmp_path, kind):
    report, cause = _report(), _cause(kind=kind)
    report["mismatches"][0]["kind"] = kind
    assert _dashboard_buckets([report], [cause])[0]["cause"] == 0
    _, (records, errors) = _write(tmp_path, report, [cause])
    assert errors == [] and len(records) == 1
    assert check_records(records, Ratchet(open_max=1)), kind
    assert records[0].row_kinds == (kind,)


class BooleanCompanionSource:
    def read(self, repo, sha, path):
        return json.dumps([{"name": "case", "output": {CONCEPT: False}}])

    def is_regular_file(self, repo, sha, path):
        return True

    def is_merged(self, repo, sha):
        return True

    def main_sha(self, repo):
        return "a" * 40

    def fetch_json(self, url):
        return 200, {
            "number": 1,
            "state": "closed",
            "html_url": "https://github.com/PolicyEngine/policyengine-us/issues/1",
        }


@pytest.mark.parametrize("kind", KINDS)
def test_only_actual_eligibility_kinds_allow_boolean_companion(tmp_path, kind):
    report = _report()
    report["mismatches"][0].update(kind=kind, left=0, right=1)
    cause = _cause(
        kind=kind,
        issue_url="https://github.com/PolicyEngine/policyengine-us/issues/1",
        axiom_companion={
            "legal_ids": [CONCEPT],
            "tests": [
                "rulespec-us@" + "a" * 40 + ":us/policies/example.test.yaml#case"
            ],
        },
    )
    _, (records, errors) = _write(tmp_path, report, [cause])
    assert errors == [] and len(records) == 1
    problems = CompanionResolver(BooleanCompanionSource()).resolve(records[0])
    if kind in (
        MismatchKind.ELIGIBILITY_LEFT_ONLY,
        MismatchKind.ELIGIBILITY_RIGHT_ONLY,
    ):
        assert problems == [], problems
    else:
        assert any(
            "False with the disputed Axiom value 0.0" in problem
            for problem in problems
        ), problems


def test_summary_metadata_without_report_markers_is_ignored(tmp_path):
    data = tmp_path / "dashboard/public/data"
    data.mkdir(parents=True)
    (data / "rule_verification.json").write_text(
        json.dumps({"summary": {"verified": 1}, "rules": []})
    )
    records, errors = collect_records(tmp_path)
    assert records == [] and errors == []


BAD_JSON_IDENTIFIERS = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.lists(st.integers(), max_size=3),
    st.dictionaries(st.text(max_size=3), st.integers(), max_size=3),
    st.sampled_from(("", " ", "\t")),
)


@PROPERTY_SETTINGS
@given(
    value=BAD_JSON_IDENTIFIERS,
    field=st.sampled_from(("suite", "concept", "kind")),
    location=st.sampled_from(("report", "cause")),
)
def test_generated_invalid_identifiers_never_pass_gate(
    tmp_path_factory, value, field, location
):
    report, cause = _report(), _cause()
    target = cause if location == "cause" else (
        report if field == "suite" else report["mismatches"][0]
    )
    target[field] = value
    _, (_, errors) = _write(
        tmp_path_factory.mktemp("invalid-bucket"), report, [cause]
    )
    assert any(field in error for error in errors), (location, field, value, errors)


IDENTIFIERS = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")), min_size=1, max_size=10
)


@pytest.mark.skipif(NODE is None, reason="node runtime not available")
@PROPERTY_SETTINGS
@given(
    concept=IDENTIFIERS,
    kind=IDENTIFIERS,
    owners=st.lists(st.sampled_from(("axiom", "policyengine")), min_size=1, max_size=5),
    specific=st.lists(st.booleans(), min_size=1, max_size=5),
    engine=st.sampled_from(("policyengine", "taxsim")),
)
def test_generated_valid_buckets_agree_with_actual_dashboard(
    tmp_path_factory, concept, kind, owners, specific, engine
):
    report = _report()
    report["mismatches"][0].update(concept=concept, kind=kind)
    report["engines"]["right"] = engine
    causes = []
    for index, owner in enumerate(owners):
        cause = _cause(concept=concept, kind=kind, fix_owner=owner)
        if specific[index % len(specific)]:
            cause["engines"] = copy.deepcopy(report["engines"])
        causes.append(cause)
    picked = _dashboard_buckets([report], causes)[0]["cause"]
    _, (records, errors) = _write(
        tmp_path_factory.mktemp("valid-bucket"), report, causes
    )
    assert errors == []
    expected = picked >= 0 and causes[picked]["fix_owner"] == "policyengine"
    assert bool(records) == expected
    if expected:
        assert records[0].entry == causes[picked]
        assert records[0].case_ids == ("case",)
        assert records[0].axiom_values == {"case": (10,)}
