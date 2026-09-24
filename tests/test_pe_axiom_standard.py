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
from axiom_oracles.comparison.pe_axiom_standard import (
    RATCHET_RELATIVE_PATH,
    CompanionPointer,
    CompanionResolver,
    Ratchet,
    RatchetDocumentError,
    Record,
    attribute_disposition,
    check_history,
    check_records,
    collect_records,
    committed_versions,
    derive_ratchet,
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


def test_known_cause_owned_by_policyengine_is_gated(tmp_path: Path, capsys) -> None:
    cause = {"suite": "s", "concept": CONCEPT, "kind": "amount_difference", "fix_owner": "policyengine-data", "label": "l", "description": "d"}
    _write_repo(tmp_path, [])
    assert _run(tmp_path, "--init") == 0
    _write_repo(tmp_path, [], known_causes=[cause])
    capsys.readouterr()
    assert _run(tmp_path, "--check") == 1
    assert "known_causes.json [s|" in capsys.readouterr().err
    cause.update(issue_url=PE_ISSUE, axiom_encoding_debt="not a url")
    _write_repo(tmp_path, [], known_causes=[cause])
    assert _run(tmp_path, "--check") == 1  # malformed debt URL
    cause.update(axiom_encoding_debt=DEBT_ISSUE)
    _write_repo(tmp_path, [], known_causes=[cause])
    assert _run(tmp_path, "--raise-ceiling", "known cause debt") == 0
    assert _run(tmp_path, "--check") == 0


def test_missing_ratchet_file_fails_the_check(tmp_path: Path, capsys) -> None:
    _write_repo(tmp_path, [])
    assert _run(tmp_path, "--check") == 1
    assert "--init" in capsys.readouterr().err


# --------------------------------------------------------------------------
# Monotonic across committed history
# --------------------------------------------------------------------------

ROW = {"basis": "rows", "pe_issue": "present", "axiom": "missing"}


def _ratchet(open_max: int, keys: list[str], raises: int = 0, **status) -> Ratchet:
    return Ratchet(
        open_max=open_max,
        grandfathered={
            ("dispositions/x.yaml", key, CONCEPT): dict(
                ROW, source="dispositions/x.yaml", id=key, concept=CONCEPT, **status
            )
            for key in keys
        },
        debt_raises=[
            {"date": "2026-09-24", "from": i, "to": i + 1, "reason": f"r{i}"}
            for i in range(raises)
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


def test_history_allows_a_raise_only_as_an_appended_record() -> None:
    history = [("c1", _ratchet(2, ["a"]))]
    # A raise appended in the current version starts a new epoch.
    assert check_history(_ratchet(5, ["a"], raises=1), history) == []
    # Within that epoch the new ceiling only falls again.
    raised_history = [("c2", _ratchet(4, ["a"], raises=1))] + history
    assert check_history(_ratchet(4, ["a"], raises=1), raised_history) == []
    problems = check_history(_ratchet(5, ["a"], raises=1), raised_history)
    assert any("exceeds the committed floor 4" in p for p in problems)
    # Deleting or rewriting a recorded raise is refused.
    rewritten = _ratchet(4, ["a"], raises=1)
    rewritten.debt_raises[0]["reason"] = "something else"
    assert any("append-only" in p for p in check_history(rewritten, raised_history))
    assert any(
        "append-only" in p
        for p in check_history(_ratchet(2, ["a"]), raised_history)
    )


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
    ):
        document = copy.deepcopy(good)
        mutate(document)
        with pytest.raises(RatchetDocumentError):
            Ratchet.from_document(document)


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


def _test_file(value: str = "10") -> str:
    return yaml.safe_dump(
        [
            {"name": "disputed-case", "period": 2026, "input": {}, "output": {CONCEPT: value}},
            {"name": "other-case", "period": 2026, "input": {}, "output": {"us:x#y": "1"}},
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
    # A minimal reproduction under a different case name asserts its own value.
    companion = _companion(tests=[f"rulespec-us@{SHA}:{TEST_PATH}#other-case"], legal_ids=["us:x#y"])
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
