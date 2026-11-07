"""Binding discovery verifies a slim report's source before using its rows."""

import hashlib
import json

import pytest
import yaml

from scripts import bind_dispositions


@pytest.fixture
def pointed_report(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    reports.mkdir()
    dashboard = tmp_path / "dashboard" / "public" / "data"
    dashboard.mkdir(parents=True)
    dispositions = tmp_path / "dispositions"
    dispositions.mkdir()
    monkeypatch.setattr(bind_dispositions, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(bind_dispositions, "DASHBOARD_DATA_DIR", dashboard)
    monkeypatch.setattr(bind_dispositions, "DISPOSITIONS_DIR", dispositions)

    suite = "source-taxsim"
    row = {
        "case_id": "case-1",
        "concept": "us:test#income_tax",
        "kind": "amount_difference",
        "left": 10,
        "right": 0,
        "difference": 10,
    }
    full = {
        "suite": suite,
        "engines": {"left": "policyengine", "right": "taxsim"},
        "summary": {"mismatch_count": 1},
        "mismatches": [row],
    }
    source = reports / "full.json"
    source.write_text(json.dumps(full))
    slim = {
        **full,
        "summary": {
            "mismatch_count": 1,
            "dispositioned": {
                "source_report": {
                    "path": "reports/full.json",
                    "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                }
            },
        },
        "mismatches": [],
    }
    slim_path = dashboard / "slim.json"
    slim_path.write_text(json.dumps(slim))
    entry = {
        "id": "taxsim-gap",
        "case_id": row["case_id"],
        "concept": row["concept"],
        "disposition": "upstream_engine_gap",
        "attribution": "taxsim",
        "evidence": {"mechanism": "TAXSIM returns zero for this case."},
        "expires_on_source_change": True,
        "pinned": {"left": row["left"], "right": row["right"]},
        "oracle_binding": {"identity_unrecorded": True},
    }
    ledger = dispositions / f"{suite}.yaml"
    ledger.write_text(yaml.safe_dump({"suite": suite, "entries": [entry]}))
    return suite, source, full, slim_path, slim, ledger


def test_binding_discovery_accepts_verified_source(pointed_report, capsys):
    suite, source, full, _, _, ledger = pointed_report
    before = ledger.read_bytes()

    assert bind_dispositions.resolve_full_report(suite, None) == (source, full)
    assert bind_dispositions.main([suite, "--check"]) == 0
    assert "every binding matches" in capsys.readouterr().out
    assert ledger.read_bytes() == before


@pytest.mark.parametrize("has_other_full_report", [False, True])
def test_binding_check_rejects_source_sha_mismatch(
    pointed_report, capsys, has_other_full_report
):
    suite, _, full, slim_path, slim, ledger = pointed_report
    slim["summary"]["dispositioned"]["source_report"]["sha256"] = "0" * 64
    slim_path.write_text(json.dumps(slim))
    if has_other_full_report:
        (slim_path.parent / "other-full.json").write_text(json.dumps(full))
    before = ledger.read_bytes()

    with pytest.raises(SystemExit, match="source_report.*sha256 mismatch"):
        bind_dispositions.main([suite, "--check"])

    assert "every binding matches" not in capsys.readouterr().out
    assert ledger.read_bytes() == before


def test_binding_discovery_rejects_source_without_sha(pointed_report):
    suite, _, _, slim_path, slim, _ = pointed_report
    del slim["summary"]["dispositioned"]["source_report"]["sha256"]
    slim_path.write_text(json.dumps(slim))

    with pytest.raises(SystemExit, match="needs string `path` and `sha256`"):
        bind_dispositions.resolve_full_report(suite, None)
