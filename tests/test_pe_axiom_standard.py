"""The PolicyEngine -> Axiom standard gate must be able to fail.

Follows the repo's gate-testing convention (tests/test_unexplained_ratchet.py,
tests/test_conformance.py): every CI gate carries negative tests proving it
bites, plus a test that the committed state passes.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from axiom_oracles.comparison.dispositions import (
    DISPOSITIONS_SCHEMA_VERSION,
    validate_dispositions,
)
from axiom_oracles.comparison import pe_axiom_standard as standard
from axiom_oracles.comparison.pe_axiom_standard import (
    RATCHET_RELATIVE_PATH,
    CompanionPointer,
    CompanionResolver,
    GitHubSource,
    Ratchet,
    RatchetDocumentError,
    Record,
    SourceUnavailable,
    attribute_disposition,
    check_history,
    check_records,
    collect_records,
    committed_versions,
    derive_ratchet,
    is_pe_issue_url,
    is_pe_link_url,
    legal_id_companion_path,
    serialize_ratchet,
    suggest_companions,
    validate_axiom_side_fields,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "pe_axiom_standard_script", REPO_ROOT / "scripts" / "pe_axiom_standard.py"
)
script = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(script)

SHA = "0" * 39 + "1"
OTHER_SHA = "f" * 40
CONCEPT = "us:policies/income_tax/example_pipeline#federal_example"
TEST_PATH = "us/policies/income_tax/example_pipeline.test.yaml"
PE_ISSUE = "https://github.com/PolicyEngine/policyengine-us/issues/9999"
DEBT_ISSUE = "https://github.com/TheAxiomFoundation/rulespec-us/issues/4242"


# --------------------------------------------------------------------------
# Committed state
# --------------------------------------------------------------------------


def test_committed_ratchet_passes_against_committed_data() -> None:
    records, syntax_errors = collect_records(REPO_ROOT)
    assert syntax_errors == []
    committed = Ratchet.from_document(
        yaml.safe_load((REPO_ROOT / RATCHET_RELATIVE_PATH).read_text())
    )
    assert check_records(records, committed) == []
    # A re-pin may only tighten the committed file, never loosen it.
    tightened = derive_ratchet(records, committed)
    assert tightened["open_max"] <= committed.open_max
    assert {
        (row["source"], row["id"], row["concept"]) for row in tightened["grandfathered"]
    } <= set(committed.grandfathered)


def _real_data_copy(tmp_path: Path) -> Path:
    """The committed dispositions + ratchet, beside the real dashboard data.

    Dispositions and the ratchet are copied (the test edits them); the
    222 MB dashboard data directory is symlinked, read-only.
    """

    root = tmp_path / "repo"
    (root / "dashboard" / "public").mkdir(parents=True)
    (root / "dashboard" / "public" / "data").symlink_to(
        REPO_ROOT / "dashboard" / "public" / "data"
    )
    shutil.copytree(REPO_ROOT / "dispositions", root / "dispositions")
    (root / "conformance").mkdir()
    shutil.copy(REPO_ROOT / RATCHET_RELATIVE_PATH, root / RATCHET_RELATIVE_PATH)
    return root


def _append_synthetic_entry(root: Path, suite: str, entry: dict) -> None:
    path = root / "dispositions" / f"{suite}.yaml"
    document = yaml.safe_load(path.read_text())
    document["entries"].append(entry)
    path.write_text(yaml.safe_dump(document, sort_keys=False))


def test_real_data_passes_then_a_synthetic_new_pe_disposition_fails(
    tmp_path: Path, capsys
) -> None:
    root = _real_data_copy(tmp_path)
    assert _run(root, "--check") == 0
    assert "pe-axiom standard OK" in capsys.readouterr().out

    # A brand-new upstream_engine_gap in a PolicyEngine-only suite (Axiom vs
    # PolicyEngine SALT grid), with neither the PolicyEngine issue nor an
    # Axiom side: it must fail, and name exactly what is missing.
    synthetic = {
        "id": "synthetic-new-pe-bug",
        "concept": "us:policies/income_tax/salt_deduction_pipeline#federal_salt_deduction",
        "case_id": "salt-single-base",
        "kind": "amount_difference",
        "disposition": "upstream_engine_gap",
        "evidence": {
            "mechanism": "Synthetic: PolicyEngine applies a stale cap.",
            "arithmetic": [{"expression": "10000 - 9000", "equals": 1000}],
        },
        "expires_on_source_change": True,
    }
    _append_synthetic_entry(root, "us-salt-deduction-grid", synthetic)
    capsys.readouterr()
    assert _run(root, "--check") == 1
    err = capsys.readouterr().err
    assert "[synthetic-new-pe-bug]" in err
    assert "lacks a PolicyEngine issue URL and axiom_companion or axiom_encoding_debt" in err
    assert "cannot be grandfathered" in err
    # Only the synthetic entry is reported; the grandfathered baseline holds.
    assert err.count("lacks") == 1

    # With the PolicyEngine issue alone it still fails (Axiom side missing).
    _real_copy = _real_data_copy(tmp_path / "second")
    synthetic["linked_issue"] = PE_ISSUE
    _append_synthetic_entry(_real_copy, "us-salt-deduction-grid", synthetic)
    capsys.readouterr()
    assert _run(_real_copy, "--check") == 1
    assert "lacks axiom_companion or axiom_encoding_debt" in capsys.readouterr().err


def test_real_data_companion_backed_new_attribution_passes(tmp_path: Path) -> None:
    root = _real_data_copy(tmp_path)
    _append_synthetic_entry(
        root,
        "us-salt-deduction-grid",
        {
            "id": "synthetic-backed-pe-bug",
            "concept": "us:policies/income_tax/salt_deduction_pipeline#federal_salt_deduction",
            "case_id": "salt-single-base",
            "disposition": "upstream_engine_gap",
            "evidence": {"mechanism": "Synthetic.", "upstream_url": PE_ISSUE},
            "expires_on_source_change": True,
            "axiom_companion": _companion(),
        },
    )
    assert _run(root, "--check") == 0


def test_attribution_is_computed_not_named() -> None:
    # nd-open-rows-axiom-pe-divergent is named "pe" but its rows are TAXSIM
    # rows; nd-policyengine-* rows are PolicyEngine rows.
    records, _ = collect_records(REPO_ROOT)
    ids = {(r.source, r.id) for r in records}
    assert ("dispositions/nd-income-tax-liability.yaml", "nd-open-rows-axiom-pe-divergent") not in ids
    assert ("dispositions/nd-income-tax-liability.yaml", "nd-policyengine-2026-single-150000") in ids
    assert not any(r.id.startswith("taxsim-") for r in records)


# --------------------------------------------------------------------------
# Field syntax
# --------------------------------------------------------------------------


def _companion(**overrides) -> dict:
    companion = {
        "legal_ids": [CONCEPT],
        "tests": [f"rulespec-us@{SHA}:{TEST_PATH}#disputed-case"],
    }
    companion.update(overrides)
    return companion


def test_well_formed_axiom_side_fields_pass() -> None:
    assert validate_axiom_side_fields({"axiom_companion": _companion()}, "e") == []
    assert validate_axiom_side_fields({"axiom_encoding_debt": DEBT_ISSUE}, "e") == []
    assert validate_axiom_side_fields({}, "e") == []


@pytest.mark.parametrize(
    ("entry", "needle"),
    [
        ({"axiom_companion": _companion(), "axiom_encoding_debt": DEBT_ISSUE}, "exactly one"),
        ({"axiom_encoding_debt": "https://github.com/PolicyEngine/policyengine-us/issues/1"}, "rulespec-* issue"),
        ({"axiom_encoding_debt": "https://github.com/TheAxiomFoundation/axiom-oracles/issues/1"}, "rulespec-* issue"),
        ({"axiom_companion": _companion(tests=[f"rulespec-us@{SHA[:7]}:{TEST_PATH}#c"])}, "40-hex"),
        ({"axiom_companion": _companion(tests=[f"rulespec-us@{SHA}:us/x.yaml#c"])}, "40-hex"),
        ({"axiom_companion": _companion(tests=[f"rulespec-us@{SHA}:{TEST_PATH}"])}, "40-hex"),
        ({"axiom_companion": _companion(tests=[f"rulespec-us@{SHA}:../x.test.yaml#c"])}, "40-hex"),
        ({"axiom_companion": _companion(legal_ids=["federal_example"])}, "legal id"),
        ({"axiom_companion": _companion(legal_ids=[])}, "non-empty"),
        ({"axiom_companion": _companion(extra=1)}, "unknown keys"),
    ],
)
def test_malformed_axiom_side_fields_fail(entry: dict, needle: str) -> None:
    errors = validate_axiom_side_fields(entry, "e")
    assert errors and any(needle in error for error in errors), errors


def test_dispositions_schema_rejects_axiom_side_on_other_kinds() -> None:
    entry = {
        "id": "x",
        "concept": CONCEPT,
        "case_id": "c",
        "disposition": "explained_residual",
        "evidence": {"mechanism": "m", "arithmetic": [{"expression": "1 - 1", "equals": 0}]},
        "expires_on_source_change": True,
        "axiom_encoding_debt": DEBT_ISSUE,
    }
    document = {"schema": DISPOSITIONS_SCHEMA_VERSION, "suite": "s", "entries": [entry]}
    errors = validate_dispositions(document)
    assert any("belong on upstream_engine_gap" in e for e in errors)
    entry["disposition"] = "upstream_engine_gap"
    assert validate_dispositions(document) == []


def test_pointer_round_trips() -> None:
    raw = f"rulespec-us@{SHA}:{TEST_PATH}#case with spaces"
    pointer = CompanionPointer.parse(raw)
    assert pointer is not None
    assert (pointer.repo, pointer.sha, pointer.path, pointer.case) == (
        "rulespec-us", SHA, TEST_PATH, "case with spaces"
    )
    assert str(pointer) == raw


def test_legal_id_maps_to_companion_file() -> None:
    assert legal_id_companion_path("us-tn:policies/cms/x#y") == ("rulespec-us", "us-tn/policies/cms/x.test.yaml")
    assert legal_id_companion_path("uk:policies/govuk/lbtt#t") == ("rulespec-uk", "uk/policies/govuk/lbtt.test.yaml")
    assert legal_id_companion_path("not a legal id") is None


# --------------------------------------------------------------------------
# Attribution
# --------------------------------------------------------------------------


def _gap(entry_id: str = "gap", **overrides) -> dict:
    entry = {
        "id": entry_id,
        "concept": CONCEPT,
        "case_id": "disputed-case",
        "disposition": "upstream_engine_gap",
        "evidence": {"mechanism": "PolicyEngine applies a stale threshold.", "arithmetic": [{"expression": "10 - 5", "equals": 5}]},
        "expires_on_source_change": True,
    }
    entry.update(overrides)
    return entry


def _row(entry_id: str = "gap", *, left_engine=None, right_engine=None, left=10.0, right=5.0, case_id="disputed-case") -> dict:
    row = {
        "case_id": case_id,
        "concept": CONCEPT,
        "kind": "amount_difference",
        "left": left,
        "right": right,
        "difference": left - right,
        "disposition": {"id": entry_id, "disposition": "upstream_engine_gap"},
    }
    if left_engine:
        row["left_engine"] = left_engine
        row["right_engine"] = right_engine
    return row


def _report(rows, engines=None, suite="example-grid") -> dict:
    return {
        "suite": suite,
        "engines": engines or {"left": "axiom", "right": "policyengine"},
        "summary": {"mismatch_count": len(rows)},
        "mismatches": rows,
    }


def test_rows_with_policyengine_counterpart_attribute_to_pe() -> None:
    basis, cases, values = attribute_disposition(_gap(), [_report([_row()])])
    assert basis == "rows"
    assert cases == ("disputed-case",)
    assert values == {"disputed-case": (10.0,)}


def test_axiom_side_follows_the_report_orientation() -> None:
    report = _report([_row(left=5.0, right=10.0)], engines={"left": "policyengine", "right": "axiom"})
    _, _, values = attribute_disposition(_gap(), [report])
    assert values == {"disputed-case": (10.0,)}


def test_taxsim_rows_in_a_multi_oracle_report_are_not_pe() -> None:
    engines = {"axiom": "x", "policyengine": "y", "taxsim": "z"}
    row = _row(left_engine="axiom", right_engine="taxsim")
    assert attribute_disposition(_gap("axiom-pe-agree"), [_report([row], engines)])[0] is None
    row_pe = _row(left_engine="axiom", right_engine="policyengine")
    assert attribute_disposition(_gap(), [_report([row_pe], engines)])[0] == "rows"


def test_unannotated_entry_falls_back_to_a_pe_only_report() -> None:
    assert attribute_disposition(_gap(), [_report([])])[0] == "report"
    multi = _report([], engines={"axiom": "x", "policyengine": "y", "taxsim": "z"})
    assert attribute_disposition(_gap(), [multi])[0] is None
    # An expired multi-oracle entry keeps its attribution through its kind.
    pe_kind = _gap(kind="policyengine_amount_difference")
    assert attribute_disposition(pe_kind, [multi])[0] == "kind"
    taxsim_only = _report([], engines={"left": "axiom", "right": "taxsim"})
    assert attribute_disposition(pe_kind, [taxsim_only])[0] is None


def test_policyengine_issue_link_attributes_regardless_of_rows() -> None:
    taxsim = _report([_row(left_engine="axiom", right_engine="taxsim")], engines={"left": "axiom", "right": "taxsim"})
    assert attribute_disposition(_gap(linked_issue=PE_ISSUE), [taxsim])[0] == "url"
    # A PolicyEngine code link is evidence, not an issue: no attribution.
    blob = _gap(evidence={"mechanism": "m", "upstream_url": "https://github.com/PolicyEngine/policyengine-us/blob/main/x.py"})
    assert attribute_disposition(blob, [taxsim])[0] is None


def test_only_upstream_engine_gap_attributes() -> None:
    for kind in ("explained_residual", "bridge_artifact", "axiom_encoding_gap", "unexplained"):
        assert attribute_disposition(_gap(disposition=kind, linked_issue=PE_ISSUE), [_report([_row()])])[0] is None


PE_PULL = "https://github.com/PolicyEngine/policyengine-us/pull/8614"


@pytest.mark.parametrize(
    ("url", "link", "issue"),
    [
        (PE_ISSUE, True, True),
        (PE_ISSUE + "#issuecomment-2400000000", True, True),
        (PE_ISSUE + "?q=1", True, True),
        (PE_ISSUE.replace("PolicyEngine", "policyengine"), True, True),
        (PE_PULL, True, False),
        ("https://github.com/PolicyEngine/policyengine-us/issues/0", False, False),
        ("https://github.com/PolicyEngine/policyengine-us/blob/main/x.py", False, False),
        ("https://github.com/PSLmodels/Tax-Calculator/issues/2900", False, False),
    ],
)
def test_pe_links_attribute_but_only_issues_satisfy_the_standard(url, link, issue) -> None:
    assert is_pe_link_url(url) is link
    assert is_pe_issue_url(url) is issue


def test_a_pull_request_attributes_but_is_not_the_pe_issue(tmp_path: Path, capsys) -> None:
    taxsim = _report([_row(left_engine="axiom", right_engine="taxsim")], engines={"left": "axiom", "right": "taxsim"})
    assert attribute_disposition(_gap(linked_issue=PE_PULL), [taxsim])[0] == "url"
    _write_repo(tmp_path, [])
    assert _run(tmp_path, "--init") == 0
    _write_repo(tmp_path, [_gap("new-bug", linked_issue=PE_PULL, axiom_companion=_companion())])
    capsys.readouterr()
    assert _run(tmp_path, "--check") == 1
    assert "lacks a PolicyEngine issue URL" in capsys.readouterr().err
    # The issue the pull request closes satisfies it.
    fixed = _gap("new-bug", linked_issue=PE_PULL, axiom_companion=_companion())
    fixed["evidence"]["upstream_url"] = PE_ISSUE
    _write_repo(tmp_path, [fixed])
    assert _run(tmp_path, "--check") == 0


def test_rows_without_an_axiom_leg_do_not_blame_policyengine() -> None:
    # Tax-Calculator vs PolicyEngine: the row does not say which oracle is wrong.
    oracles = _report([_row(left_engine="taxcalc", right_engine="policyengine")], engines={"left": "taxcalc", "right": "policyengine"})
    assert attribute_disposition(_gap(), [oracles])[0] is None
    assert attribute_disposition(_gap(linked_issue=PE_ISSUE), [oracles])[0] == "url"


# --------------------------------------------------------------------------
# Gate over a synthetic repository
# --------------------------------------------------------------------------


def _write_repo(root: Path, entries: list[dict], *, rows=None, known_causes=None) -> None:
    (root / "dispositions").mkdir(parents=True, exist_ok=True)
    (root / "dashboard" / "public" / "data").mkdir(parents=True, exist_ok=True)
    (root / "dispositions" / "example-grid.yaml").write_text(
        yaml.safe_dump({"schema": DISPOSITIONS_SCHEMA_VERSION, "suite": "example-grid", "entries": entries}, sort_keys=False)
    )
    rows = rows if rows is not None else [_row(entry["id"]) for entry in entries]
    (root / "dashboard" / "public" / "data" / "axiom-policyengine-example-grid.json").write_text(json.dumps(_report(rows)))
    (root / "dashboard" / "public" / "data" / "known_causes.json").write_text(json.dumps({"entries": known_causes or []}))


def _run(root: Path, *argv: str) -> int:
    return script.main(list(argv), repo_root=root)


def test_gate_bites_on_a_new_pe_attribution_lacking_both_fields(tmp_path: Path, capsys) -> None:
    _write_repo(tmp_path, [_gap("old-bug", linked_issue=PE_ISSUE)])
    assert _run(tmp_path, "--init") == 0
    assert _run(tmp_path, "--check") == 0

    _write_repo(tmp_path, [_gap("old-bug", linked_issue=PE_ISSUE), _gap("new-bug", linked_issue=PE_ISSUE)])
    capsys.readouterr()
    assert _run(tmp_path, "--check") == 1
    err = capsys.readouterr().err
    assert "[new-bug]" in err and "lacks axiom_companion or axiom_encoding_debt" in err
    assert "[old-bug]" not in err


def test_new_attribution_also_needs_the_pe_issue(tmp_path: Path, capsys) -> None:
    _write_repo(tmp_path, [])
    assert _run(tmp_path, "--init") == 0
    _write_repo(tmp_path, [_gap("new-bug", axiom_companion=_companion())])
    capsys.readouterr()
    assert _run(tmp_path, "--check") == 1
    assert "lacks a PolicyEngine issue URL" in capsys.readouterr().err


def test_a_companion_from_another_country_is_refused_offline(tmp_path: Path, capsys) -> None:
    _write_repo(tmp_path, [])
    assert _run(tmp_path, "--init") == 0
    unrelated = _companion(
        legal_ids=["uk:policies/govuk/lbtt#land_and_buildings_transaction_tax"],
        tests=[f"rulespec-uk@{SHA}:uk/policies/govuk/lbtt.test.yaml#case"],
    )
    _write_repo(tmp_path, [_gap("new-bug", linked_issue=PE_ISSUE, axiom_companion=unrelated)])
    capsys.readouterr()
    assert _run(tmp_path, "--check") == 1
    err = capsys.readouterr().err
    assert "outside the disputed concept's country" in err and "outside rulespec-us" in err


def test_companion_backed_attribution_passes_without_touching_the_ceiling(tmp_path: Path) -> None:
    _write_repo(tmp_path, [_gap("old-bug", linked_issue=PE_ISSUE)])
    assert _run(tmp_path, "--init") == 0
    _write_repo(
        tmp_path,
        [
            _gap("old-bug", linked_issue=PE_ISSUE),
            _gap("new-bug", linked_issue=PE_ISSUE, axiom_companion=_companion()),
        ],
    )
    assert _run(tmp_path, "--check") == 0


def test_new_debt_is_counted_and_the_ceiling_only_falls(tmp_path: Path, capsys) -> None:
    _write_repo(tmp_path, [_gap("old-bug", linked_issue=PE_ISSUE)])
    assert _run(tmp_path, "--init") == 0  # open_max 1
    two = [
        _gap("old-bug", linked_issue=PE_ISSUE),
        _gap("new-bug", linked_issue=PE_ISSUE, axiom_encoding_debt=DEBT_ISSUE),
    ]
    _write_repo(tmp_path, two)
    capsys.readouterr()
    assert _run(tmp_path, "--check") == 1
    assert "RATCHET regressed" in capsys.readouterr().err
    # Re-pinning never absorbs the rise...
    assert _run(tmp_path) == 1
    # ...paying down the old debt does:
    two[0]["axiom_companion"] = _companion()
    _write_repo(tmp_path, two)
    capsys.readouterr()
    assert _run(tmp_path, "--check") == 0
    assert "re-pin to drop them" in capsys.readouterr().err
    assert _run(tmp_path) == 0
    assert _run(tmp_path, "--check") == 0
    document = yaml.safe_load((tmp_path / RATCHET_RELATIVE_PATH).read_text())
    assert document["open_max"] == 1 and document["grandfathered"] == []


def test_raise_ceiling_is_deliberate_and_recorded(tmp_path: Path, capsys) -> None:
    _write_repo(tmp_path, [_gap("old-bug", linked_issue=PE_ISSUE)])
    assert _run(tmp_path, "--init") == 0
    _write_repo(
        tmp_path,
        [
            _gap("old-bug", linked_issue=PE_ISSUE),
            _gap("new-bug", linked_issue=PE_ISSUE, axiom_encoding_debt=DEBT_ISSUE),
        ],
    )
    assert _run(tmp_path, "--raise-ceiling", "   ") == 1  # a reason is required
    assert _run(tmp_path, "--raise-ceiling", "PE#9999 needs a new encoding") == 0
    assert _run(tmp_path, "--check") == 0
    document = yaml.safe_load((tmp_path / RATCHET_RELATIVE_PATH).read_text())
    assert document["open_max"] == 2
    (raise_record,) = document["debt_raises"]
    assert raise_record["from"] == 1 and raise_record["to"] == 2
    assert raise_record["reason"] == "PE#9999 needs a new encoding"
    # A raise never absorbs a NEW attribution that lacks its Axiom side.
    _write_repo(
        tmp_path,
        [
            _gap("old-bug", linked_issue=PE_ISSUE),
            _gap("new-bug", linked_issue=PE_ISSUE, axiom_encoding_debt=DEBT_ISSUE),
            _gap("bare-bug", linked_issue=PE_ISSUE),
        ],
    )
    capsys.readouterr()
    assert _run(tmp_path, "--raise-ceiling", "absorb it") == 1
    assert "[bare-bug]" in capsys.readouterr().err


def test_init_refuses_once_the_ratchet_exists(tmp_path: Path, capsys) -> None:
    _write_repo(tmp_path, [])
    assert _run(tmp_path, "--init") == 0
    _write_repo(tmp_path, [_gap("new-bug", linked_issue=PE_ISSUE)])
    capsys.readouterr()
    assert _run(tmp_path, "--init") == 1
    assert "grandfather door is closed" in capsys.readouterr().err


def test_grandfathered_entry_may_not_regress(tmp_path: Path, capsys) -> None:
    _write_repo(tmp_path, [_gap("old-bug", linked_issue=PE_ISSUE)])
    assert _run(tmp_path, "--init") == 0
    _write_repo(tmp_path, [_gap("old-bug")])  # PolicyEngine issue link dropped
    capsys.readouterr()
    assert _run(tmp_path, "--check") == 1
    assert "regressed from pe_issue=present" in capsys.readouterr().err


def test_slack_is_reported_and_repin_tightens(tmp_path: Path, capsys) -> None:
    _write_repo(tmp_path, [_gap("old-bug", linked_issue=PE_ISSUE)])
    assert _run(tmp_path, "--init") == 0
    _write_repo(tmp_path, [])  # the mismatch cleared and its entry was deleted
    capsys.readouterr()
    assert _run(tmp_path, "--check") == 0
    err = capsys.readouterr().err
    assert "open_max can tighten 1 -> 0" in err and "re-pin" in err
    assert _run(tmp_path) == 0
    document = yaml.safe_load((tmp_path / RATCHET_RELATIVE_PATH).read_text())
    assert document["open_max"] == 0 and document["grandfathered"] == []
    # Once tightened, the slack is gone: new debt now needs a raise.
    _write_repo(tmp_path, [_gap("new-bug", linked_issue=PE_ISSUE, axiom_encoding_debt=DEBT_ISSUE)])
    assert _run(tmp_path, "--check") == 1


LIVE = [_row("unannotated")]  # an unexplained mismatch bucket a known cause can explain


def _cause(**overrides) -> dict:
    cause = {"suite": "example-grid", "concept": CONCEPT, "kind": "amount_difference", "fix_owner": "policyengine-data", "label": "l", "description": "d"}
    cause.update(overrides)
    return cause


def test_known_cause_owned_by_policyengine_is_gated(tmp_path: Path, capsys) -> None:
    cause = _cause()
    _write_repo(tmp_path, [], rows=LIVE)
    assert _run(tmp_path, "--init") == 0
    _write_repo(tmp_path, [], rows=LIVE, known_causes=[cause])
    capsys.readouterr()
    assert _run(tmp_path, "--check") == 1
    assert "known_causes.json [example-grid|" in capsys.readouterr().err
    cause.update(issue_url=PE_ISSUE, axiom_encoding_debt="not a url")
    _write_repo(tmp_path, [], rows=LIVE, known_causes=[cause])
    assert _run(tmp_path, "--check") == 1
    assert "axiom_encoding_debt must be a TheAxiomFoundation" in capsys.readouterr().err
    cause.update(axiom_encoding_debt=DEBT_ISSUE)
    _write_repo(tmp_path, [], rows=LIVE, known_causes=[cause])
    assert _run(tmp_path, "--raise-ceiling", "known cause debt") == 0
    assert _run(tmp_path, "--check") == 0


def test_known_cause_companion_syntax_is_checked_on_its_own(tmp_path: Path, capsys) -> None:
    # A placeholder companion keeps the open count at 0, so only the syntax
    # check can fail these runs.
    cause = _cause(issue_url=PE_ISSUE, axiom_companion={"legal_ids": ["TODO"], "tests": ["TODO"]})
    _write_repo(tmp_path, [], rows=LIVE)
    assert _run(tmp_path, "--init") == 0
    _write_repo(tmp_path, [], rows=LIVE, known_causes=[cause])
    capsys.readouterr()
    assert _run(tmp_path, "--check") == 1
    err = capsys.readouterr().err
    assert "axiom_companion.legal_ids[0] must be" in err and "axiom_companion.tests[0] must be" in err


def test_a_known_cause_with_no_live_mismatch_attributes_nothing(tmp_path: Path) -> None:
    # PolicyEngine fixed it: the report has no row in the cause's bucket.
    _write_repo(tmp_path, [], rows=[], known_causes=[_cause()])
    records, _ = collect_records(tmp_path)
    assert records == []
    # A sampled report keeps it live through its per-concept count.
    report = _report([])
    report["summary"] = {"mismatch_count": 3, "mismatches_by_concept": [{"value": CONCEPT, "count": 3}]}
    (tmp_path / "dashboard" / "public" / "data" / "axiom-policyengine-example-grid.json").write_text(json.dumps(report))
    records, _ = collect_records(tmp_path)
    assert [r.basis for r in records] == ["fix_owner"]
    # causeFor prefers the engine-specific cause; the engine-less one is not live.
    specific = _cause(engines={"left": "axiom", "right": "policyengine"}, label="specific")
    _write_repo(tmp_path, [], rows=LIVE, known_causes=[_cause(), specific])
    records, _ = collect_records(tmp_path)
    assert [r.id for r in records] == [f"example-grid|{CONCEPT}|amount_difference|axiom-policyengine"]


@pytest.mark.parametrize(
    ("owner", "attributed"),
    [("policyengine", True), ("policyengine-data", True), ("upstream-policyengine", True), ("source-vs-pe-convention", False), ("upstream-taxsim", False)],
)
def test_known_cause_owner_names_policyengine_as_a_token(tmp_path: Path, owner: str, attributed: bool) -> None:
    _write_repo(tmp_path, [], rows=LIVE, known_causes=[_cause(fix_owner=owner)])
    records, _ = collect_records(tmp_path)
    assert bool(records) is attributed


def test_two_causes_for_one_bucket_attribute_once(tmp_path: Path) -> None:
    # The dashboard shows the first matching cause; only that one attributes,
    # so a second cause cannot slip in under the first one's grandfathered row
    # alongside it.
    first, second = _cause(label="first"), _cause(label="second", fix_owner="policyengine")
    _write_repo(tmp_path, [], rows=LIVE, known_causes=[first, second])
    records, errors = collect_records(tmp_path)
    assert errors == [] and [r.entry["label"] for r in records] == ["first"]


def test_duplicate_attribution_keys_are_refused(tmp_path: Path) -> None:
    _write_repo(tmp_path, [_gap("dup", linked_issue=PE_ISSUE), _gap("dup", linked_issue=PE_ISSUE)])
    _, errors = collect_records(tmp_path)
    assert any("share the key" in error for error in errors)


def test_missing_ratchet_file_fails_the_check(tmp_path: Path, capsys) -> None:
    _write_repo(tmp_path, [])
    assert _run(tmp_path, "--check") == 1
    assert "--init" in capsys.readouterr().err


# --------------------------------------------------------------------------
# Monotonic across committed history
# --------------------------------------------------------------------------

ROW = {"basis": "rows", "pe_issue": "present", "axiom": "missing"}


def _ratchet(open_max: int, keys: list[str], raises=(), **status) -> Ratchet:
    return Ratchet(
        open_max=open_max,
        grandfathered={
            ("dispositions/x.yaml", key, CONCEPT): dict(
                ROW, source="dispositions/x.yaml", id=key, concept=CONCEPT, **status
            )
            for key in keys
        },
        debt_raises=[
            {"date": "2026-09-24", "from": start, "to": end, "reason": f"r{start}-{end}"}
            for start, end in raises
        ],
    )


def test_history_blocks_grandfather_growth_and_ceiling_rise() -> None:
    history = [("c2", _ratchet(2, ["a", "b"])), ("c1", _ratchet(3, ["a", "b"]))]
    assert check_history(_ratchet(2, ["a"]), history) == []
    grown = check_history(_ratchet(2, ["a", "b", "c"]), history)
    assert len(grown) == 1 and "grandfather door is closed" in grown[0]
    # The floor is the LOWEST committed value, not just the latest one.
    risen = check_history(_ratchet(3, ["a"]), history)
    assert len(risen) == 1 and "exceeds the committed floor 2" in risen[0]
    assert check_history(_ratchet(9, ["z"]), []) == []


def test_history_allows_a_raise_only_by_its_recorded_increment() -> None:
    history = [("c1", _ratchet(2, ["a"]))]
    # A raise of +3 appended in the current version lifts the ceiling by 3.
    assert check_history(_ratchet(5, ["a"], raises=[(2, 5)]), history) == []
    assert any(
        "exceeds the committed floor 5" in p
        for p in check_history(_ratchet(6, ["a"], raises=[(2, 5)]), history)
    )
    # Once committed, the raised ceiling only falls again.
    raised_history = [("c2", _ratchet(4, ["a"], raises=[(2, 5)]))] + history
    assert check_history(_ratchet(4, ["a"], raises=[(2, 5)]), raised_history) == []
    problems = check_history(_ratchet(5, ["a"], raises=[(2, 5)]), raised_history)
    assert any("exceeds the committed floor 4" in p for p in problems)
    # Deleting or rewriting a recorded raise is refused.
    rewritten = _ratchet(4, ["a"], raises=[(2, 5)])
    rewritten.debt_raises[0]["reason"] = "something else"
    assert any("the log only grows" in p for p in check_history(rewritten, raised_history))
    assert any(
        "the log only grows" in p
        for p in check_history(_ratchet(2, ["a"]), raised_history)
    )


def test_parallel_branches_merge() -> None:
    # A pay-down on one branch (10 -> 8) and a raise on another (+2): the
    # merge may keep the pay-down plus the raise, 10, and no more.
    m0 = ("m0", _ratchet(10, ["a"]))
    f1 = ("f1", _ratchet(8, ["a"]))
    m1 = ("m1", _ratchet(12, ["a"], raises=[(10, 12)]))
    assert check_history(_ratchet(10, ["a"], raises=[(10, 12)]), [f1, m1, m0]) == []
    assert any(
        "exceeds the committed floor 10" in p
        for p in check_history(_ratchet(11, ["a"], raises=[(10, 12)]), [f1, m1, m0])
    )
    # Two raises in parallel (+1, +2) merge to both increments.
    a = ("a", _ratchet(3, ["a"], raises=[(2, 3)]))
    b = ("b", _ratchet(4, ["a"], raises=[(2, 4)]))
    base = ("base", _ratchet(2, ["a"]))
    merged = _ratchet(5, ["a"], raises=[(2, 3), (2, 4)])
    assert check_history(merged, [a, b, base]) == []
    assert any(
        "exceeds the committed floor 5" in p
        for p in check_history(_ratchet(6, ["a"], raises=[(2, 3), (2, 4)]), [a, b, base])
    )
    # A merge that keeps only one side's raise drops the other's record.
    assert any("the log only grows" in p for p in check_history(_ratchet(3, ["a"], raises=[(2, 3)]), [a, b, base]))


def test_history_blocks_lowering_a_grandfathered_status() -> None:
    history = [("c1", _ratchet(1, ["a"]))]
    lowered = check_history(_ratchet(1, ["a"], pe_issue="missing"), history)
    assert len(lowered) == 1 and "fell below" in lowered[0]


def test_ratchet_document_is_validated() -> None:
    good = derive_ratchet([], None)
    assert Ratchet.from_document(good).open_max == 0
    for mutate in (
        lambda d: d.update(open_max=-1),
        lambda d: d.update(extra=1),
        lambda d: d.update(schema="other"),
        lambda d: d.update(debt_raises=[{"date": "x", "from": 0, "to": 1, "reason": ""}]),
        lambda d: d.update(grandfathered=[{"source": "s", "id": "i"}]),
        # A raise record must be numeric and must raise. (What it may raise
        # open_max to is a history rule: see check_history.)
        lambda d: d.update(debt_raises=[_raise("0", 1)]),
        lambda d: d.update(debt_raises=[_raise(0, True)]),
        lambda d: d.update(debt_raises=[_raise(1, 1)]),
        lambda d: d.update(debt_raises=[_raise(-1, 1)]),
    ):
        document = copy.deepcopy(good)
        mutate(document)
        with pytest.raises(RatchetDocumentError):
            Ratchet.from_document(document)
    raised = dict(copy.deepcopy(good), open_max=3)
    raised["debt_raises"] = [_raise(0, 2), _raise(1, 4)]
    assert Ratchet.from_document(raised).open_max == 3
    # Committed versions are read leniently: a later schema may add keys.
    later = dict(copy.deepcopy(raised), added_later=True)
    later["debt_raises"][0]["approved_by"] = "someone"
    with pytest.raises(RatchetDocumentError):
        Ratchet.from_document(later)
    assert Ratchet.from_document(later, strict=False) == Ratchet.from_document(raised)


def _raise(start, end) -> dict:
    return {"date": "2026-09-27", "from": start, "to": end, "reason": "r"}


def _git_repo(tmp_path: Path):
    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(tmp_path), *args], check=True, capture_output=True
        )

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.org")
    git("config", "user.name", "t")
    git("config", "commit.gpgsign", "false")
    return git


def test_check_reads_every_committed_version(tmp_path: Path, capsys) -> None:
    git = _git_repo(tmp_path)
    _write_repo(tmp_path, [_gap("old-bug", linked_issue=PE_ISSUE)])
    assert _run(tmp_path, "--init") == 0
    git("add", "-A")
    git("commit", "-q", "-m", "introduce the standard")
    versions, errors = committed_versions(tmp_path)
    assert errors == [] and versions is not None and len(versions) == 1
    capsys.readouterr()
    assert _run(tmp_path, "--check") == 0
    assert "monotonic vs 1 committed version(s)" in capsys.readouterr().out

    # Hand-edit the ratchet to grandfather a brand-new non-compliant entry and
    # raise the ceiling to fit it — in the same commit. The offline presence
    # check is satisfied by the edited file; the history check is not.
    _write_repo(
        tmp_path,
        [_gap("old-bug", linked_issue=PE_ISSUE), _gap("new-bug", linked_issue=PE_ISSUE)],
    )
    path = tmp_path / RATCHET_RELATIVE_PATH
    document = yaml.safe_load(path.read_text())
    document["grandfathered"].append(dict(document["grandfathered"][0], id="new-bug"))
    document["grandfathered"].sort(key=lambda row: row["id"])
    document["open_max"] = 2
    path.write_text(serialize_ratchet(document))
    git("commit", "-q", "-am", "sneak")
    capsys.readouterr()
    assert _run(tmp_path, "--check") == 1
    err = capsys.readouterr().err
    assert "grandfather door is closed" in err
    assert "exceeds the committed floor 1" in err


def test_a_committed_raise_passes_and_later_versions_ratchet_from_it(
    tmp_path: Path, capsys
) -> None:
    git = _git_repo(tmp_path)
    _write_repo(tmp_path, [_gap("old-bug", linked_issue=PE_ISSUE)])
    assert _run(tmp_path, "--init") == 0
    git("add", "-A")
    git("commit", "-q", "-m", "introduce")
    entries = [
        _gap("old-bug", linked_issue=PE_ISSUE),
        _gap("new-bug", linked_issue=PE_ISSUE, axiom_encoding_debt=DEBT_ISSUE),
    ]
    _write_repo(tmp_path, entries)
    assert _run(tmp_path, "--raise-ceiling", "new PE bug; encoding queued") == 0
    git("commit", "-q", "-am", "raise")
    assert _run(tmp_path, "--check") == 0
    # Pay the new debt down, re-pin (tighten), commit; the old ceiling of 2
    # can no longer come back without another recorded raise.
    entries[1] = _gap("new-bug", linked_issue=PE_ISSUE, axiom_companion=_companion())
    _write_repo(tmp_path, entries)
    assert _run(tmp_path) == 0
    git("commit", "-q", "-am", "tighten")
    path = tmp_path / RATCHET_RELATIVE_PATH
    document = yaml.safe_load(path.read_text())
    assert document["open_max"] == 1
    document["open_max"] = 2
    path.write_text(serialize_ratchet(document))
    capsys.readouterr()
    assert _run(tmp_path, "--check") == 1
    assert "exceeds the committed floor 1" in capsys.readouterr().err


def test_a_hand_edited_raise_is_bound_by_its_record(tmp_path: Path, capsys) -> None:
    git = _git_repo(tmp_path)
    _write_repo(tmp_path, [_gap("old-bug", linked_issue=PE_ISSUE)])
    assert _run(tmp_path, "--init") == 0
    git("add", "-A")
    git("commit", "-q", "-m", "introduce")
    path = tmp_path / RATCHET_RELATIVE_PATH
    document = yaml.safe_load(path.read_text())
    assert document["open_max"] == 1
    # One raise record worth +1 cannot carry open_max to 500...
    document["debt_raises"] = [_raise(1, 2)]
    document["open_max"] = 500
    path.write_text(serialize_ratchet(document))
    capsys.readouterr()
    assert _run(tmp_path, "--check") == 1
    assert "exceeds the committed floor 2" in capsys.readouterr().err
    # ...and a record's increment is what counts, not where it claims to end.
    document["debt_raises"] = [_raise(400, 500)]
    path.write_text(serialize_ratchet(document))
    assert _run(tmp_path, "--check") == 1
    assert "exceeds the committed floor 101" in capsys.readouterr().err
    # The honest record of the same raise passes the history check.
    document["debt_raises"] = [_raise(1, 500)]
    path.write_text(serialize_ratchet(document))
    assert _run(tmp_path, "--check") == 0


def test_shallow_checkout_is_refused(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    git = _git_repo(source)
    _write_repo(source, [])
    assert _run(source, "--init") == 0
    git("add", "-A")
    git("commit", "-q", "-m", "one")
    (source / "README").write_text("x")
    git("add", "-A")
    git("commit", "-q", "-m", "two")
    clone = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", f"file://{source}", str(clone)],
        check=True,
        capture_output=True,
    )
    versions, errors = committed_versions(clone)
    assert versions is None and errors and "shallow" in errors[0]


# --------------------------------------------------------------------------
# Companion resolution
# --------------------------------------------------------------------------


class FakeSource:
    def __init__(self, files: dict, merged: set[str] | None = None, main: str = SHA):
        self.files = files
        self.merged = merged if merged is not None else {SHA}
        self.main = main

    def read(self, repo, sha, path):
        return self.files.get((repo, sha, path))

    def is_merged(self, repo, sha):
        return sha in self.merged

    def main_sha(self, repo):
        return self.main

    def fetch_json(self, url):
        return 200, {
            "number": int(url.rsplit("/", 1)[1]),
            "html_url": url.replace("https://api.github.com/repos/", "https://github.com/"),
        }


def _test_file(value: str = "10") -> str:
    return yaml.safe_dump(
        [
            {"name": "disputed-case", "period": 2026, "input": {}, "output": {CONCEPT: value}},
            {"name": "other-case", "period": 2026, "input": {}, "output": {CONCEPT: "5", "us:x#y": "1"}},
        ]
    )


def _record(**entry_overrides) -> Record:
    entry = _gap(linked_issue=PE_ISSUE, axiom_companion=_companion())
    entry.update(entry_overrides)
    return Record(
        source="dispositions/example-grid.yaml",
        id="gap",
        suite="example-grid",
        concept=CONCEPT,
        basis="rows",
        pe_issue=PE_ISSUE,
        entry=entry,
        case_ids=("disputed-case",),
        axiom_values={"disputed-case": (10.0,)},
        row_kinds=("amount_difference",),
    )


def test_companion_resolves_when_the_case_pins_the_disputed_value() -> None:
    source = FakeSource({("rulespec-us", SHA, TEST_PATH): _test_file("10")})
    assert CompanionResolver(source).resolve(_record()) == []


@pytest.mark.parametrize(
    ("files", "merged", "companion", "needle"),
    [
        ({}, None, None, "not found (or not YAML) at the pinned commit"),
        ({("rulespec-us", SHA, TEST_PATH): _test_file("10")}, set(), None, "not on rulespec-us main"),
        ({("rulespec-us", SHA, TEST_PATH): _test_file("5")}, None, None, "disputed Axiom value is 10.0"),
        ({("rulespec-us", SHA, TEST_PATH): _test_file("10")}, None, _companion(tests=[f"rulespec-us@{SHA}:{TEST_PATH}#absent"]), "no case named 'absent'"),
        ({("rulespec-us", SHA, TEST_PATH): _test_file("10")}, None, _companion(legal_ids=[CONCEPT, "us:other#output"]), "does not assert us:other#output"),
    ],
)
def test_companion_resolution_bites(files, merged, companion, needle) -> None:
    source = FakeSource(files, merged=merged)
    record = _record(**({"axiom_companion": companion} if companion else {}))
    problems = CompanionResolver(source).resolve(record)
    assert problems and any(needle in p for p in problems), problems


def test_value_check_only_applies_to_the_disputed_case() -> None:
    # A minimal reproduction under a different case name asserts its own
    # value (disclosed limit: its inputs cannot be mapped to the disputed case).
    companion = _companion(tests=[f"rulespec-us@{SHA}:{TEST_PATH}#other-case"], legal_ids=[CONCEPT, "us:x#y"])
    source = FakeSource({("rulespec-us", SHA, TEST_PATH): _test_file("5")})
    assert CompanionResolver(source).resolve(_record(axiom_companion=companion)) == []


def test_suggest_finds_existing_companion_cases() -> None:
    record = copy.copy(_record())
    record.entry = _gap(linked_issue=PE_ISSUE)
    source = FakeSource({("rulespec-us", SHA, TEST_PATH.replace("example_pipeline", "example_pipeline")): _test_file()})
    suggestions = suggest_companions([record], source)
    assert suggestions == [
        {
            "source": "dispositions/example-grid.yaml",
            "id": "gap",
            "axiom_companion": {
                "legal_ids": [CONCEPT],
                "tests": [f"rulespec-us@{SHA}:{TEST_PATH}#disputed-case"],
            },
        }
    ]


def test_a_rulespec_concept_must_be_declared_among_legal_ids() -> None:
    # The disputed concept is asserted in its own module's companion test, so
    # a companion that names only some other output is refused...
    companion = _companion(tests=[f"rulespec-us@{SHA}:{TEST_PATH}#other-case"], legal_ids=["us:x#y"])
    source = FakeSource({("rulespec-us", SHA, TEST_PATH): _test_file("10")})
    problems = CompanionResolver(source).resolve(_record(axiom_companion=companion))
    assert any("declare it among legal_ids" in p for p in problems), problems
    # ...while a comparison-surface concept with no RuleSpec module is not
    # (disclosed limit: no crosswalk yet from such concepts to legal ids).
    record = _record(axiom_companion=companion)
    record.concept = "us:tax/federal-income-tax#eitc"
    assert CompanionResolver(source).resolve(record) == []


def _one_case(value) -> str:
    return yaml.safe_dump([{"name": "disputed-case", "period": 2026, "input": {}, "output": {CONCEPT: value}}])


@pytest.mark.parametrize(
    ("axiom_value", "asserted", "needle"),
    [
        (False, "not_holds", None),
        (False, "holds", "disputed Axiom value is False"),
        (True, "holds", None),
        (True, 1, None),
        (1.0, "holds", None),
        (10.0, ["10"], None),
        (10.0, ["5"], "disputed Axiom value is 10.0"),
        (10.0, ["10", "5"], "cannot compare"),
        (10.0, "garbage", "cannot compare"),
    ],
)
def test_value_check_reads_judgments_and_one_row_tables(axiom_value, asserted, needle) -> None:
    source = FakeSource({("rulespec-us", SHA, TEST_PATH): _one_case(asserted)})
    record = _record()
    if isinstance(axiom_value, bool) or asserted in ("holds", "not_holds"):
        record.entry["kind"] = "eligibility_right_only"
        record.row_kinds = ("eligibility_right_only",)
    record.axiom_values = {"disputed-case": (axiom_value,)}
    problems = CompanionResolver(source).resolve(record)
    if needle is None:
        assert problems == []
    else:
        assert any(needle in p for p in problems), problems


@pytest.mark.parametrize(
    ("main_file", "needle"),
    [
        (None, "gone from rulespec-us main"),
        (_one_case("7"), "no longer asserts"),
        (yaml.safe_dump([{"name": "disputed-case", "output": {"us:x#y": "1"}}]), "no longer asserts"),
        (_one_case("10"), None),
        (_one_case(10), None),
    ],
)
def test_the_pinned_case_must_still_be_on_main(main_file, needle) -> None:
    files = {("rulespec-us", SHA, TEST_PATH): _one_case("10")}
    if main_file is not None:
        files[("rulespec-us", OTHER_SHA, TEST_PATH)] = main_file
    source = FakeSource(files, main=OTHER_SHA)
    problems = CompanionResolver(source).resolve(_record())
    if needle is None:
        assert problems == []
    else:
        assert any(needle in p for p in problems), problems
        # --no-require-merged (local experiments) skips the main-line checks.
        assert CompanionResolver(source, require_merged=False).resolve(_record()) == []


class FlakySource(FakeSource):
    def read(self, repo, sha, path):
        raise SourceUnavailable("503")


def test_transient_failures_are_reported_as_such() -> None:
    problems = CompanionResolver(FlakySource({})).resolve(_record())
    assert any("transient; re-run" in p for p in problems) and not any("not found" in p for p in problems)

    class Unknown(FakeSource):
        def is_merged(self, repo, sha):
            return None

        def main_sha(self, repo):
            return None

    source = Unknown({("rulespec-us", SHA, TEST_PATH): _test_file("10")})
    problems = CompanionResolver(source).resolve(_record())
    assert any("cannot verify the commit is on rulespec-us main" in p for p in problems)
    assert any("cannot read rulespec-us main" in p for p in problems)


class Issues:
    def __init__(self, payload):
        self.payload = payload

    def issue(self, repo, number):
        return self.payload

    def fetch_json(self, url):
        return 200, {
            "number": int(url.rsplit("/", 1)[1]),
            "html_url": url.replace("https://api.github.com/repos/", "https://github.com/"),
        }


def _debt_record(url: str = DEBT_ISSUE) -> Record:
    record = _record(axiom_companion=None)
    record.entry = _gap(linked_issue=PE_ISSUE, axiom_encoding_debt=url)
    return record


@pytest.mark.parametrize(
    ("payload", "needle"),
    [
        ({"state": "open", "pull_request": None}, None),
        ({"state": "open"}, None),
        ({}, "no such issue"),
        (None, "cannot verify the issue"),
        ({"state": "open", "pull_request": {"url": "x"}}, "is a pull request"),
        ({"state": "closed"}, "the issue is closed"),
    ],
)
def test_encoding_debt_must_be_an_open_rulespec_issue(payload, needle) -> None:
    resolver = CompanionResolver(FakeSource({}), issue_source=Issues(payload))
    problems = resolver.resolve_debt(_debt_record())
    if needle is None:
        assert problems == []
    else:
        assert any(needle in p for p in problems), problems
    assert CompanionResolver(FakeSource({})).resolve_debt(_debt_record()) == [
        f"dispositions/example-grid.yaml [gap] axiom_encoding_debt {DEBT_ISSUE}: no GitHub source to verify the issue"
    ]


# --------------------------------------------------------------------------
# GitHub source: transient failures are retried and never read as absence
# --------------------------------------------------------------------------


class _Response:
    def __init__(self, status: int, body: bytes):
        self.status, self.body = status, body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _urlopen(script_: list):
    calls = []

    def urlopen(request, timeout=None):
        calls.append(request.full_url)
        step = script_[min(len(calls) - 1, len(script_) - 1)]
        if isinstance(step, BaseException):
            raise step
        status, body = step
        if status != 200:
            raise standard.urllib.error.HTTPError(request.full_url, status, "x", {}, None)
        return _Response(status, body)

    return urlopen, calls


@pytest.mark.parametrize(
    ("steps", "expected", "attempts"),
    [
        ([(503, b""), (200, b"ok")], "ok", 2),
        ([(404, b"")], None, 1),
        ([standard.http.client.RemoteDisconnected("x"), (200, b"ok")], "ok", 2),
        ([TimeoutError("t")], SourceUnavailable, 3),
        ([(429, b"")], SourceUnavailable, 3),
        ([(403, b"")], SourceUnavailable, 1),
    ],
)
def test_github_reads_retry_transients(monkeypatch, steps, expected, attempts) -> None:
    urlopen, calls = _urlopen(steps)
    monkeypatch.setattr(standard.urllib.request, "urlopen", urlopen)
    source = GitHubSource(backoff=0)
    if expected is SourceUnavailable:
        with pytest.raises(SourceUnavailable):
            source.read("rulespec-us", SHA, TEST_PATH)
    else:
        assert source.read("rulespec-us", SHA, TEST_PATH) == expected
    assert len(calls) == attempts


def test_github_issue_and_compare_answers(monkeypatch) -> None:
    source = GitHubSource(backoff=0)
    for steps, expected in (
        ([(200, json.dumps({"state": "open"}).encode())], {"state": "open"}),
        ([(404, b"")], {}),
        ([(503, b"")], None),
    ):
        monkeypatch.setattr(standard.urllib.request, "urlopen", _urlopen(steps)[0])
        assert source.issue("rulespec-us", 1) == expected
    for steps, expected in (
        ([(200, json.dumps({"status": "ahead"}).encode())], True),
        ([(200, json.dumps({"status": "diverged"}).encode())], False),
        ([(404, b"")], False),
        ([(503, b"")], None),
        ([(200, b"not json")], None),
    ):
        monkeypatch.setattr(standard.urllib.request, "urlopen", _urlopen(steps)[0])
        assert source.is_merged("rulespec-us", SHA) is expected


# --------------------------------------------------------------------------
# The --resolve CI step, end to end against a local RuleSpec clone
# --------------------------------------------------------------------------


def _rev(repo: Path) -> str:
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()


def _rulespec(tmp_path: Path) -> tuple[Path, str, str]:
    """A local rulespec-us clone: one commit on main, one on an unmerged branch."""

    repo = tmp_path / "rulespec-us"
    repo.mkdir()
    git = _git_repo(repo)
    (repo / TEST_PATH).parent.mkdir(parents=True)
    (repo / TEST_PATH).write_text(_test_file("10"))
    git("add", "-A")
    git("commit", "-q", "-m", "companion")
    merged = _rev(repo)
    git("checkout", "-q", "-b", "feature")
    (repo / "README").write_text("x")
    git("add", "-A")
    git("commit", "-q", "-m", "unmerged")
    unmerged = _rev(repo)
    git("checkout", "-q", "main")
    return repo, merged, unmerged


def _resolve(root: Path, repo: Path, *extra: str) -> int:
    return _run(root, "--resolve", "--rulespec-checkout", f"rulespec-us={repo}", "--rulespec-main-ref", "main", *extra)


def _pointed(sha: str, case: str = "disputed-case", **overrides) -> dict:
    return _gap("bug", linked_issue=PE_ISSUE, axiom_companion=_companion(tests=[f"rulespec-us@{sha}:{TEST_PATH}#{case}"]), **overrides)


def test_resolve_cli_passes_then_bites(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setattr(script, "GitHubSource", lambda **_: Issues({"state": "open"}))
    repo, merged, unmerged = _rulespec(tmp_path)
    root = tmp_path / "oracles"
    _write_repo(root, [_pointed(merged)])
    assert _resolve(root, repo) == 0
    assert "1 companion-backed attributions resolved" in capsys.readouterr().out
    _write_repo(root, [_pointed(merged, case="absent")])
    assert _resolve(root, repo) == 1
    assert "no case named 'absent'" in capsys.readouterr().err
    _write_repo(root, [_pointed(unmerged)])
    assert _resolve(root, repo) == 1
    assert "not on rulespec-us main" in capsys.readouterr().err
    assert _resolve(root, repo, "--no-require-merged") == 0
    # The case is later deleted on RuleSpec main: the pointer stops resolving.
    (repo / TEST_PATH).write_text(yaml.safe_dump([{"name": "other-case", "output": {CONCEPT: "5"}}]))
    subprocess.run(["git", "-C", str(repo), "commit", "-qam", "drop the case"], check=True, capture_output=True)
    _write_repo(root, [_pointed(merged)])
    capsys.readouterr()
    assert _resolve(root, repo) == 1
    assert "gone from rulespec-us main" in capsys.readouterr().err
    # Known-cause syntax errors fail the step too.
    _write_repo(root, [], known_causes=[_cause(issue_url=PE_ISSUE, axiom_encoding_debt="not-a-url")])
    assert _resolve(root, repo) == 1
    assert "axiom_encoding_debt must be" in capsys.readouterr().err
    # Encoding debt is checked against GitHub issues even with local clones.
    monkeypatch.setattr(script, "GitHubSource", lambda **_: Issues({"state": "closed"}))
    _write_repo(root, [_gap("bug", linked_issue=PE_ISSUE, axiom_encoding_debt=DEBT_ISSUE)])
    assert _resolve(root, repo) == 1
    assert "the issue is closed" in capsys.readouterr().err
    monkeypatch.setattr(script, "GitHubSource", lambda **_: Issues({"state": "open"}))
    assert _resolve(root, repo) == 0
    assert "1 encoding-debt issues open" in capsys.readouterr().out


# --------------------------------------------------------------------------
# History through the CLI: failures cannot switch the check off, and the
# named remedies work after a revert or a merge
# --------------------------------------------------------------------------


def test_shallow_checkout_fails_the_cli_check(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source"
    source.mkdir()
    git = _git_repo(source)
    _write_repo(source, [])
    assert _run(source, "--init") == 0
    git("add", "-A")
    git("commit", "-q", "-m", "one")
    (source / "README").write_text("x")
    git("add", "-A")
    git("commit", "-q", "-m", "two")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{source}", str(clone)], check=True, capture_output=True)
    capsys.readouterr()
    assert _run(clone, "--check") == 1
    assert "shallow Git checkout" in capsys.readouterr().err


def _two_debts(tmp_path: Path):
    git = _git_repo(tmp_path)
    entries = [
        _gap("e1", linked_issue=PE_ISSUE, axiom_encoding_debt=DEBT_ISSUE),
        _gap("e2", linked_issue=PE_ISSUE, axiom_encoding_debt=DEBT_ISSUE),
    ]
    _write_repo(tmp_path, entries)
    assert _run(tmp_path, "--init") == 0  # open_max 2
    git("add", "-A")
    git("commit", "-q", "-m", "m0")
    return git, entries


def test_a_malformed_committed_version_is_not_skipped(tmp_path: Path, capsys) -> None:
    git, _ = _two_debts(tmp_path)
    path = tmp_path / RATCHET_RELATIVE_PATH
    good = path.read_text()
    # An extra key is tolerated in history (a later schema may add one), so
    # this committed tightening still binds...
    document = yaml.safe_load(good)
    document["open_max"] = 1
    document["added_later"] = True
    path.write_text(yaml.safe_dump(document, sort_keys=False))
    git("commit", "-q", "-am", "tighten, with an extra key")
    path.write_text(good)
    git("commit", "-q", "-am", "loosen")
    capsys.readouterr()
    assert _run(tmp_path, "--check") == 1
    assert "exceeds the committed floor 1" in capsys.readouterr().err
    # ...and a version whose ceiling cannot be read is never skipped.
    document["open_max"] = "one"
    path.write_text(yaml.safe_dump(document, sort_keys=False))
    git("commit", "-q", "-am", "malformed")
    path.write_text(good)
    git("commit", "-q", "-am", "loosen again")
    assert _run(tmp_path, "--check") == 1
    assert "cannot be skipped" in capsys.readouterr().err


def test_raise_ceiling_works_after_a_revert(tmp_path: Path, capsys) -> None:
    git, entries = _two_debts(tmp_path)
    entries[0] = _gap("e1", linked_issue=PE_ISSUE, axiom_companion=_companion())
    _write_repo(tmp_path, entries)
    assert _run(tmp_path) == 0  # re-pin: open_max 1
    git("commit", "-q", "-am", "pay down e1")
    git("revert", "--no-edit", "HEAD")  # the companion was wrong
    capsys.readouterr()
    assert _run(tmp_path, "--check") == 1
    assert "exceeds the committed floor 1" in capsys.readouterr().err
    assert _run(tmp_path, "--raise-ceiling", "revert: e1's companion was wrong") == 0
    document = yaml.safe_load((tmp_path / RATCHET_RELATIVE_PATH).read_text())
    assert [(r["from"], r["to"]) for r in document["debt_raises"]] == [(1, 2)]
    assert _run(tmp_path, "--check") == 0


def test_a_pay_down_and_a_raise_on_parallel_branches_merge(tmp_path: Path, capsys) -> None:
    git, entries = _two_debts(tmp_path)
    git("checkout", "-q", "-b", "paydown")
    paid = [_gap("e1", linked_issue=PE_ISSUE, axiom_companion=_companion()), entries[1]]
    _write_repo(tmp_path, paid)
    assert _run(tmp_path) == 0  # open_max 1
    git("commit", "-q", "-am", "pay down e1")
    git("checkout", "-q", "main")
    raised = entries + [_gap("e3", linked_issue=PE_ISSUE, axiom_encoding_debt=DEBT_ISSUE)]
    _write_repo(tmp_path, raised)
    assert _run(tmp_path, "--raise-ceiling", "e3 is new debt") == 0  # 2 -> 3
    git("commit", "-q", "-am", "raise for e3")
    # Merge the pay-down; take main's ratchet file, write the merged data,
    # re-pin. The merged ceiling is the pay-down plus the raise: 1 + 1 = 2.
    subprocess.run(["git", "-C", str(tmp_path), "merge", "-q", "--no-edit", "paydown"], capture_output=True)
    git("checkout", "-q", "main", "--", str(RATCHET_RELATIVE_PATH))
    _write_repo(tmp_path, [paid[0], entries[1], raised[2]])
    assert _run(tmp_path) == 0
    document = yaml.safe_load((tmp_path / RATCHET_RELATIVE_PATH).read_text())
    assert document["open_max"] == 2 and len(document["debt_raises"]) == 1
    git("add", "-A")
    git("commit", "-q", "--no-edit", "-m", "merge paydown")
    capsys.readouterr()
    assert _run(tmp_path, "--check") == 0
    # The merge cannot keep main's ceiling of 3: the pay-down is not undone.
    document["open_max"] = 3
    (tmp_path / RATCHET_RELATIVE_PATH).write_text(serialize_ratchet(document))
    assert _run(tmp_path, "--check") == 1
    assert "exceeds the committed floor 2" in capsys.readouterr().err
