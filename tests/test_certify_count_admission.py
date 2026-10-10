"""Publication rejects bad counts while internal legs retain soft diagnostics."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st


REPO = Path(__file__).resolve().parents[1]
MODULE_SPEC = importlib.util.spec_from_file_location(
    "_certify_count_admission_tests", REPO / "scripts/certify.py"
)
certify = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = certify
MODULE_SPEC.loader.exec_module(certify)


def _entry(**kwargs):
    return {"suite": "test-counts", "report": "report.json", **kwargs}


def _write_report(tmp_path, monkeypatch, report):
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    (tmp_path / "report.json").write_text(json.dumps(report, allow_nan=False))


@pytest.mark.parametrize(
    "report,entry",
    [
        ({"summary": {field: None}}, _entry())
        for field in (
            "comparison_count",
            "match_count",
            "mismatch_count",
            "error_count",
            "error_case_count",
        )
    ]
    + [
        ({"summary": {"errors_by_engine": {"axiom": "one"}}}, _entry()),
        ({"summary": {"dispositioned": {"unexplained_count": False}}}, _entry()),
        ({"summary": {"dispositioned": {"counts": {"unexplained": -1}}}}, _entry()),
        (
            {"views": {"selected": {"summary": {"mismatch_count": "bad"}}}},
            _entry(view="selected"),
        ),
        (
            {
                "views": {
                    "selected": {"legs": [{"state": "complete", "match_count": None}]}
                }
            },
            _entry(view="selected", computed_de_unified=True),
        ),
        (
            {"summary": {"total": "bad"}},
            _entry(report_contract="us_tariff_schedule_v1"),
        ),
        (
            {
                "classification": {
                    "class_attribution": {
                        "open": {"attribution": "axiom-attributed-open", "units": False}
                    }
                }
            },
            _entry(report_contract="us_tariff_schedule_v1"),
        ),
        (
            {
                "classification": {
                    "class_attribution": {
                        "open": {"attribution": "axiom-attributed-open", "units": 1}
                    },
                    "class_census": {"open": None},
                }
            },
            _entry(report_contract="us_tariff_schedule_v1"),
        ),
    ],
)
def test_present_invalid_counts_fail_publication_preflight(
    report, entry, tmp_path, monkeypatch
):
    _write_report(tmp_path, monkeypatch, report)
    with pytest.raises(ValueError, match="boolean|negative|non-negative integer"):
        certify._preflight_suite_count_admission(entry)


INVALID_COUNTS = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(max_value=-1),
    st.floats(allow_nan=False, allow_infinity=False).filter(
        lambda x: x < 0 or not x.is_integer()
    ),
    st.text(),
    st.lists(st.integers(), max_size=4),
    st.dictionaries(st.text(), st.integers(), max_size=4),
)


@given(raw=INVALID_COUNTS)
@settings(deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_unparseable_count_never_reaches_a_published_zero(raw, tmp_path, monkeypatch):
    # Reusing this temporary file across examples deliberately exercises the
    # same publication boundary with independently generated malformed values.
    _write_report(tmp_path, monkeypatch, {"summary": {"mismatch_count": raw}})
    with pytest.raises(ValueError):
        certify._preflight_suite_count_admission(_entry())


def test_publisher_preserves_existing_certificate_when_count_admission_fails(
    tmp_path, monkeypatch
):
    _write_report(tmp_path, monkeypatch, {"summary": {"mismatch_count": "unparseable"}})
    out = tmp_path / "certificates"
    out.mkdir()
    published = out / "test-program.json"
    published.write_bytes(b'{"existing_public_count": 7}\n')
    before = published.read_bytes()
    monkeypatch.setattr(certify, "OUT_DIR", out)
    monkeypatch.setattr(certify, "PROGRAMS", {"test/program": {"suites": [_entry()]}})

    def unexpected_evaluation(*_args, **_kwargs):
        raise AssertionError(
            "invalid counts must fail before evaluating certificate premises"
        )

    monkeypatch.setattr(certify, "_exercise_census_for", unexpected_evaluation)
    with pytest.raises(ValueError, match="mismatch_count.*unparseable"):
        certify.main(["--program", "test/program"])
    assert published.read_bytes() == before
    assert sorted(path.name for path in out.iterdir()) == [published.name]


@pytest.mark.parametrize("report", ({}, {"summary": {}}))
def test_absent_count_evidence_retains_existing_leg_diagnostics(
    report, tmp_path, monkeypatch
):
    _write_report(tmp_path, monkeypatch, report)
    assert certify._preflight_suite_count_admission(_entry()) is None


def test_missing_report_retains_existing_leg_diagnostics(tmp_path, monkeypatch):
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    assert certify._preflight_suite_count_admission(_entry()) is None


@pytest.mark.parametrize(
    "report,entry",
    [(value, _entry()) for value in (None, False, [], "bad")]
    + [({"summary": value}, _entry()) for value in (None, False, [], "bad")]
    + [
        ({"summary": {field: value}}, _entry())
        for field in ("errors_by_engine", "dispositioned")
        for value in (None, False, [], "bad")
    ]
    + [
        ({"summary": {"dispositioned": {"counts": value}}}, _entry())
        for value in (None, False, [], "bad")
    ]
    + [
        ({"views": False}, _entry(view="selected")),
        ({"views": {"selected": False}}, _entry(view="selected")),
        ({"views": {"selected": {"summary": False}}}, _entry(view="selected")),
        (
            {"views": {"selected": {"legs": False}}},
            _entry(view="selected", computed_de_unified=True),
        ),
        ({"classification": False}, _entry(report_contract="us_tariff_schedule_v1")),
        (
            {"classification": {"class_attribution": False}},
            _entry(report_contract="us_tariff_schedule_v1"),
        ),
        (
            {"classification": {"class_census": False}},
            _entry(report_contract="us_tariff_schedule_v1"),
        ),
    ],
)
def test_supplied_count_containers_cannot_be_replaced_with_empty_objects(
    report, entry, tmp_path, monkeypatch
):
    _write_report(tmp_path, monkeypatch, report)
    with pytest.raises(ValueError, match="must.*object|must.*array"):
        certify._preflight_suite_count_admission(entry)


@pytest.mark.parametrize(
    "raw",
    (
        b"{not-json",
        b"\xff",
        b'{"summary": false}',
        b'{"summary": {"dispositioned": {"counts": false}}}',
    ),
)
def test_bad_report_cannot_replace_an_existing_published_certificate(
    raw, tmp_path, monkeypatch
):
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    (tmp_path / "report.json").write_bytes(raw)
    out = tmp_path / "certificates"
    out.mkdir()
    published = out / "test-program.json"
    published.write_bytes(b'{"existing_public_count": 7}\n')
    before = published.read_bytes()
    monkeypatch.setattr(certify, "OUT_DIR", out)
    monkeypatch.setattr(certify, "PROGRAMS", {"test/program": {"suites": [_entry()]}})
    with pytest.raises((ValueError, UnicodeDecodeError)):
        certify.main(["--program", "test/program"])
    assert published.read_bytes() == before


def test_missing_source_can_still_publish_the_established_diagnostic_certificate(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(certify, "OUT_DIR", tmp_path / "certificates")
    spec = {
        "period": "2026",
        "suites": [_entry(oracle_type="reference", oracle="absent test source")],
    }
    monkeypatch.setattr(certify, "PROGRAMS", {"test/program": spec})
    monkeypatch.setattr(certify, "_exercise_census_for", lambda _spec: ({}, []))
    monkeypatch.setattr(certify, "_exercise_block", lambda *_args: ({}, False))
    assert certify.main(["--program", "test/program"]) == 0
    published = json.loads((certify.OUT_DIR / "test-program.json").read_text())
    leg = published["verdicts"]["conformant"]["reference_legs"][0]
    assert leg["clean"] is False
    assert leg["report_defects"]
    assert published["certified"]["value"] is False


def test_preflight_selects_only_the_registered_view(tmp_path, monkeypatch):
    _write_report(
        tmp_path,
        monkeypatch,
        {
            "views": {
                "selected": {"summary": {"comparison_count": 1}},
                "other": {"summary": {"comparison_count": "unparseable"}},
            }
        },
    )
    assert certify._preflight_suite_count_admission(_entry(view="selected")) is None


def test_current_certificate_sources_require_no_count_compatibility_exemption():
    for spec in certify.PROGRAMS.values():
        for entry in spec.get("suites", []):
            assert certify._preflight_suite_count_admission(entry) is None
