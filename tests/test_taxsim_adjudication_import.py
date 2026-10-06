"""The public import preserves the complete reviewed census and hard cases.

These checks need only committed public artifacts. The private input census is
required for reproducible regeneration, not for CI's import-coverage assertions.
"""

import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def imported():
    review = json.loads((ROOT / "adjudications/taxsim-import-decisions.json").read_text())
    document = yaml.safe_load((ROOT / "adjudications/taxsim-emulator.yaml").read_text())
    records = document["adjudications"]
    return review, records, {record["id"]: record for record in records}


def test_all_reviewed_and_mandatory_candidates_survive_import(imported):
    review, records, by_id = imported
    candidates = review["candidate_ids"]
    mandatory = review["mandatory_candidate_ids"]
    assert review["reviewed_candidates"] == len(candidates) == len(set(candidates)) == 485
    assert review["reviewed_comments"] == 1052
    assert len(mandatory) == len(set(mandatory)) == 111
    assert set(mandatory) <= set(candidates) <= by_id.keys()
    assert len(records) == len(by_id)
    # Reviewing every candidate also preserves explicit verdicts outside the
    # census's 111 initial proposals, including open outcomes after re-reading.
    assert {f"pe-taxsim-{number}" for number in review["decisions"]} <= by_id.keys()
    extras = {
        f"pe-taxsim-{number}-{jurisdiction.lower()}"
        for number, jurisdictions in review["jurisdiction_splits"].items()
        for jurisdiction in jurisdictions[1:]
    }
    assert by_id.keys() == set(candidates) | extras | {"pe-taxsim-1249"}


def test_manifest_pins_every_reviewed_comment_file_and_census_input(imported):
    review, _, _ = imported
    sources = review["input_sha256"]
    expected_comments = {
        f"comments/{candidate.removeprefix('pe-taxsim-')}.json"
        for candidate in review["candidate_ids"]
    }
    assert len(expected_comments) == 485
    assert sources.keys() == expected_comments | {
        "issues.json", "rule_level.json", "census_counts.json",
    }
    assert len(sources) == 488
    assert all(re.fullmatch(r"[0-9a-f]{64}", value) for value in sources.values())


def test_policyengine_allowlist_has_merged_emulator_pr_provenance():
    config = yaml.safe_load((ROOT / "adjudications/maintainers.yaml").read_text())
    assert config["engines"]["taxsim"]["maintainers"] == ["feenberg"]
    policyengine = config["engines"]["policyengine"]
    assert set(policyengine["maintainers"]) == {
        row["author"] for row in policyengine["provenance"]
    }
    for row in policyengine["provenance"]:
        assert row["mergedAt"]
        assert row["url"] == (
            f"https://github.com/PolicyEngine/policyengine-taxsim/pull/{row['number']}"
        )


def test_only_needed_comment_snapshots_are_retained(imported):
    _, records, _ = imported
    referenced = {
        atom["snapshot"]
        for record in records for atom in record["proof_atoms"]
        if atom["kind"] == "maintainer_statement"
    }
    committed = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "adjudications/snapshots").glob("*.json")
    }
    assert committed == referenced
    for relative in sorted(committed):
        snapshot = json.loads((ROOT / relative).read_text())
        assert snapshot.keys() == {"url", "author", "createdAt", "body"}
        assert re.fullmatch(
            r"https://github\.com/PolicyEngine/policyengine-taxsim/"
            r"(?:issues|pull)/\d+#issuecomment-\d+", snapshot["url"],
        )
        assert isinstance(snapshot["author"], str)
        assert isinstance(snapshot["body"], str)


def test_generic_agreement_does_not_misattribute_policyengine_error(imported):
    # In #1115 the detailed preceding comment identifies PolicyEngine's Kansas
    # taxable-income test; Feenberg's "Agreed, corrected" cannot turn it into
    # an admission of a TAXSIM defect.
    record = imported[2]["pe-taxsim-1115"]
    assert record["verdict"] != "taxsim_wrong"
    assert not any(
        atom.get("engine") == "taxsim" and atom.get("acknowledges_error")
        for atom in record["proof_atoms"]
    )


def test_ambiguous_correction_without_identified_engine_error_stays_unready(imported):
    # #1138 starts as a question about pension income. Neither an explicit
    # TAXSIM result nor a statement of a TAXSIM code correction establishes
    # what Feenberg's generic agreement corrected.
    record = imported[2]["pe-taxsim-1138"]
    assert record["status"] != "evidence_ready"
    assert not any(atom.get("acknowledges_error") for atom in record["proof_atoms"])


def test_output_alignment_and_reproducer_discussions_are_not_imported_as_proof(imported):
    _, records, by_id = imported
    for number in (259, 846, 1064):
        assert by_id[f"pe-taxsim-{number}"]["verdict"] == "open"
    assert all(not record["proof_atoms"] for record in records if record["verdict"] == "open")


@pytest.mark.parametrize("number,jurisdiction,years,quote", [
    (1169, "MT", [2023], "Agreed. Corrected."),
    (1230, "MD", [2021], "Agreed, corrected."),
])
def test_explicit_taxsim_corrections_retain_only_demonstrated_years(
    imported, number, jurisdiction, years, quote,
):
    # #1169 explicitly says TAXSIM applied the 2024 elderly subtraction in
    # 2023. #1230 isolates 2021; its 2022/2025 controls remain unchanged.
    record = imported[2][f"pe-taxsim-{number}"]
    assert record["verdict"] == "taxsim_wrong"
    assert record["attribution"] == "taxsim"
    assert record["status"] == "evidence_ready"
    assert record["jurisdiction"] == jurisdiction
    assert record["law_years"] == years
    admissions = [atom for atom in record["proof_atoms"] if atom.get("acknowledges_error")]
    assert len(admissions) == 1
    assert admissions[0]["kind"] == "maintainer_statement"
    assert admissions[0]["engine"] == "taxsim"
    assert admissions[0]["author"] == "feenberg"
    assert admissions[0]["quote"] == quote
