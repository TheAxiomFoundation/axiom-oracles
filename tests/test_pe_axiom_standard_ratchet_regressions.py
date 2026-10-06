"""Recorded companion status survives an issue improvement and other pay-downs."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest
import yaml

from axiom_oracles.comparison.dispositions import validate_dispositions
from axiom_oracles.comparison.pe_axiom_standard import (
    RATCHET_RELATIVE_PATH,
    Ratchet,
    check_history,
    check_records,
    collect_records,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "pe_axiom_standard_ratchet_script", REPO_ROOT / "scripts/pe_axiom_standard.py"
)
assert SPEC and SPEC.loader
script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(script)


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True
    )


def _write_documents(root: Path, documents: dict[str, dict]) -> None:
    for suite, document in documents.items():
        assert validate_dispositions(document, repo_root=REPO_ROOT) == []
        (root / "dispositions" / f"{suite}.yaml").write_text(
            yaml.safe_dump(document, sort_keys=False)
        )


@pytest.fixture
def paid_companion_baseline(tmp_path: Path):
    """Reach the reviewed state with real QBID/SALT dispositions and rows."""

    root = tmp_path / "repo"
    (root / "dispositions").mkdir(parents=True)
    data = root / "dashboard/public/data"
    data.mkdir(parents=True)
    documents = {}
    originals = {}
    for suite in ("us-qbid-grid", "us-salt-deduction-grid"):
        document = yaml.safe_load((REPO_ROOT / "dispositions" / f"{suite}.yaml").read_text())
        entry = copy.deepcopy(
            next(e for e in document["entries"] if "axiom_companion" in e)
        )
        originals[suite] = copy.deepcopy(entry)
        entry.pop("axiom_companion")
        document["entries"] = [entry]
        documents[suite] = document
        report_name = f"axiom-policyengine-{suite}.json"
        report = json.loads((REPO_ROOT / "dashboard/public/data" / report_name).read_text())
        report["mismatches"] = [
            row for row in report["mismatches"]
            if (row.get("disposition") or {}).get("id") == entry["id"]
        ]
        assert report["mismatches"]
        (data / report_name).write_text(json.dumps(report))
    (data / "known_causes.json").write_text('{"entries": []}')
    a = documents["us-qbid-grid"]["entries"][0]
    b = documents["us-salt-deduction-grid"]["entries"][0]
    a.pop("linked_issue", None)
    a["evidence"].pop("upstream_url", None)
    _write_documents(root, documents)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.org")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")
    assert script.main(["--init"], repo_root=root) == 0
    ratchet_path = root / RATCHET_RELATIVE_PATH
    initial_bytes = ratchet_path.read_bytes()
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "bootstrap missing Axiom sides")
    a["axiom_companion"] = copy.deepcopy(originals["us-qbid-grid"]["axiom_companion"])
    _write_documents(root, documents)
    assert script.main([], repo_root=root) == 0
    assert script.main(["--check"], repo_root=root) == 0
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "record the QBID companion improvement")
    paid = Ratchet.from_document(yaml.safe_load(ratchet_path.read_text()))
    assert paid.open_max == 1
    a["evidence"]["upstream_url"] = originals["us-qbid-grid"]["evidence"]["upstream_url"]
    a.pop("axiom_companion")
    a["axiom_encoding_debt"] = "https://github.com/TheAxiomFoundation/rulespec-us/issues/1486"
    b["axiom_companion"] = copy.deepcopy(originals["us-salt-deduction-grid"]["axiom_companion"])
    _write_documents(root, documents)
    records, errors = collect_records(root)
    assert errors == []
    assert sum(r.open for r in records) == paid.open_max
    return root, paid, records, initial_bytes


def test_live_gate_rejects_issue_improvement_with_companion_downgrade(
    paid_companion_baseline,
) -> None:
    _, paid, records, _ = paid_companion_baseline
    assert any(
        "grandfathered entry regressed" in problem
        and "axiom=companion" in problem
        and "axiom=debt" in problem
        for problem in check_records(records, paid)
    )
    assert check_history(paid, [("paid", paid)]) == []


@pytest.mark.parametrize(
    "argv,restore_initial,drop_current_row",
    [
        (["--check"], False, False),
        ([], False, False),
        ([], True, False),
        (["--raise-ceiling", "document encoding debt"], True, False),
        (["--check"], False, True),
        ([], False, True),
        (["--raise-ceiling", "document encoding debt"], False, True),
    ],
    ids=(
        "unchanged-check", "repin", "historical-repin", "historical-raise",
        "dropped-row-check", "dropped-row-repin", "dropped-row-raise",
    ),
)
def test_cli_refuses_companion_downgrade_even_when_other_debt_is_paid(
    paid_companion_baseline, capsys, argv, restore_initial, drop_current_row,
) -> None:
    root, _, records, initial_bytes = paid_companion_baseline
    ratchet_path = root / RATCHET_RELATIVE_PATH
    if restore_initial:
        # A stale working file must still inherit the committed companion rank.
        ratchet_path.write_bytes(initial_bytes)
    if drop_current_row:
        debt_key = next(r.key for r in records if r.axiom_status == "debt")
        document = yaml.safe_load(ratchet_path.read_text())
        document["grandfathered"] = [
            row for row in document["grandfathered"]
            if (row["source"], row["id"], row["concept"]) != debt_key
        ]
        ratchet_path.write_text(yaml.safe_dump(document, sort_keys=False))
    before = ratchet_path.read_bytes()
    capsys.readouterr()
    assert script.main(argv, repo_root=root) == 1
    err = capsys.readouterr().err
    assert "grandfathered entry regressed" in err
    assert "axiom=companion" in err and "axiom=debt" in err
    assert ratchet_path.read_bytes() == before
