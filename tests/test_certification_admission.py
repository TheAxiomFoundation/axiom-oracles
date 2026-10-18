"""Admission hardening must reject ambiguous evidence without moving outputs."""

import json
import sys

import pytest
from hypothesis import given, strategies as st

from axiom_oracles.evidence import strict_json_loads
from axiom_oracles.conformance.ratchet import RatchetInvariant
from scripts import conformance_ratchet


@given(st.text(), st.integers(), st.integers())
def test_repeated_json_keys_never_select_one_value(key, first, second):
    raw = f"{{{json.dumps(key)}:{first},{json.dumps(key)}:{second}}}"
    with pytest.raises(ValueError, match="duplicate JSON key"):
        strict_json_loads(raw)


@given(st.dictionaries(st.text(), st.integers()))
def test_unique_json_keys_preserve_values(document):
    assert strict_json_loads(json.dumps(document)) == document


@pytest.mark.parametrize("wrapper", ["{}", '[{}]', '{"nested":{}}'])
def test_repeated_keys_fail_at_every_depth(wrapper):
    duplicate = '{"commit":"a","commit":"b"}'
    with pytest.raises(ValueError, match="duplicate JSON key"):
        strict_json_loads(wrapper.replace("{}", duplicate))


@pytest.mark.parametrize("mode", ["--check", "--init", None])
def test_vanished_jurisdiction_cannot_pass_or_repin(monkeypatch, capsys, mode):
    monkeypatch.setattr(sys, "argv", ["ratchet", *([mode] if mode else [])])
    monkeypatch.setattr(conformance_ratchet, "_live_summaries", lambda: {})
    monkeypatch.setattr(
        conformance_ratchet, "_load_ratchets",
        lambda: {"us-pe": RatchetInvariant("us-pe", 1, 0, 0, 1)},
    )
    assert conformance_ratchet.main() == 1
    assert "[us-pe] pinned jurisdiction has no live scoreboard row" in capsys.readouterr().err


def test_invalid_report_is_a_gate_failure(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["ratchet", "--check"])

    def invalid_report():
        raise ValueError("report.json: invalid dashboard JSON")

    monkeypatch.setattr(conformance_ratchet, "_live_summaries", invalid_report)
    assert conformance_ratchet.main() == 1
    assert "report.json: invalid dashboard JSON" in capsys.readouterr().err
