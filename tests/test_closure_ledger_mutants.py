"""Negative tests for the DK source-completeness closure ledger."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).parents[1]
SCRIPT = REPO_ROOT / "scripts" / "closure_ledger.py"
COMMITTED_ARTIFACT = (
    REPO_ROOT / "conformance" / "closure" / "dk-boerne-og-ungeydelse.yaml"
)
CORPUS_ROOT = "dk/statute/lbk-603-2025/boerne-og-ungeydelsesloven"
_MISSING = object()


def _provision_body(suffix: str) -> str:
    return (
        f"§ {suffix.removeprefix('paragraf-').replace('-', ' ')}. Test provision body."
    )


def _load_script():
    spec = importlib.util.spec_from_file_location("closure_ledger_mutant", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _write_corpus(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "citation_path": CORPUS_ROOT,
            "kind": "document",
            "metadata": {"block_count": 4},
            "source_as_of": "2026-08-04",
            "source_id": "hermetic-dk-child-benefit",
            "version": "hermetic-release",
        }
    ]
    for ordinal, suffix in enumerate(
        ("paragraf-1", "paragraf-1-a", "paragraf-2", "paragraf-4"), start=1
    ):
        body = _provision_body(suffix)
        rows.append(
            {
                "body": body,
                "citation_path": f"{CORPUS_ROOT}/{suffix}",
                "heading": body.split(" Test", 1)[0],
                "kind": "section",
                "ordinal": ordinal,
                "parent_citation_path": CORPUS_ROOT,
            }
        )
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


def _module(
    citation: str,
    summary: str,
    *,
    formula: str | None = None,
    status: str | None = None,
    source_sha256: str | None = None,
) -> dict:
    verification = {"corpus_citation_path": citation}
    if source_sha256 is not None:
        verification["source_sha256"] = source_sha256
    module = {"source_verification": verification, "summary": summary}
    if status is not None:
        module["status"] = status
    rules = []
    if formula is not None:
        rules.append(
            {
                "name": "result",
                "kind": "derived",
                "versions": [{"effective_from": "2025-01-01", "formula": formula}],
            }
        )
    return {"format": "rulespec/v1", "module": module, "rules": rules}


def _write_module(root: Path, path: str, document: dict) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True))


def _decisions() -> dict:
    captured = {
        "child_age_years",
        "payment_year_has_additional_statutory_increase",
        "person_only_taxable_part_of_year",
        "total_contributions_to_qualifying_pension_accounts",
    }
    scopes = {
        "current_year_income_reduction_allowance": "personskatteloven § 20",
        "pension_contribution_limit_under_pensionsbeskatningsloven_section_16": (
            "pensionsbeskatningsloven § 16"
        ),
        "percentage_change_rounded_to_one_decimal_place": "Danmarks Statistik CPI",
        "personskatteloven_section_7_income_basis": "personskatteloven § 7",
        "personskatteloven_section_7_income_basis_after_section_14_recalculation": (
            "personskatteloven § 14"
        ),
    }
    rows = []
    for name in sorted(captured | set(scopes)):
        row = {
            "name": name,
            "grounding": "captured" if name in captured else "uncaptured",
            "reason": f"Reviewed grounding for {name}.",
        }
        if name in scopes:
            row["uncaptured_scope"] = scopes[name]
        rows.append(row)
    return {"provisions": [], "input_grounding": rows}


def _baseline(tmp_path: Path):
    module = _load_script()
    corpus = tmp_path / "corpus" / "hermetic-release.jsonl"
    rulespec = tmp_path / "rulespec-dk"
    artifact = tmp_path / "dk-boerne-og-ungeydelse.yaml"
    corpus.parent.mkdir()
    rulespec.mkdir()
    _git(corpus.parent, "init", "-q", "-b", "main")
    _git(rulespec, "init", "-q", "-b", "main")
    _write_corpus(corpus)
    _git(corpus.parent, "add", corpus.name)
    _git(
        corpus.parent,
        "-c",
        "user.name=closure-ledger-test",
        "-c",
        "user.email=closure-ledger-test@example.invalid",
        "commit",
        "-qm",
        "hermetic corpus baseline",
    )

    statute_dir = "dk/statutes/lbk-603-2025/boerne-og-ungeydelsesloven"
    _write_module(
        rulespec,
        f"{statute_dir}/paragraf-1.yaml",
        _module(
            f"{CORPUS_ROOT}/paragraf-1",
            "Encoded amount and CPI rule.",
            source_sha256=hashlib.sha256(
                _provision_body("paragraf-1").encode()
            ).hexdigest(),
            formula="""if payment_year_has_additional_statutory_increase:
  child_age_years + percentage_change_rounded_to_one_decimal_place
else:
  child_age_years
""",
        ),
    )
    _write_module(
        rulespec,
        f"{statute_dir}/paragraf-1-a.yaml",
        _module(
            f"{CORPUS_ROOT}/paragraf-1-a",
            "Encoded income reduction rule.",
            source_sha256=hashlib.sha256(
                _provision_body("paragraf-1-a").encode()
            ).hexdigest(),
            formula="""(if person_only_taxable_part_of_year:
  personskatteloven_section_7_income_basis_after_section_14_recalculation
else:
  personskatteloven_section_7_income_basis)
- min(
    total_contributions_to_qualifying_pension_accounts,
    pension_contribution_limit_under_pensionsbeskatningsloven_section_16
  )
- current_year_income_reduction_allowance
""",
        ),
    )
    _write_module(
        rulespec,
        f"{statute_dir}/paragraf-4.yaml",
        _module(
            f"{CORPUS_ROOT}/paragraf-4",
            "Recipient routing requires a multi-person entity surface.",
            status="entity_not_supported",
            source_sha256=hashlib.sha256(
                _provision_body("paragraf-4").encode()
            ).hexdigest(),
        ),
    )
    _write_module(
        rulespec,
        "dk/statutes/composed/boerne-og-ungeydelse-pipeline.yaml",
        _module(
            CORPUS_ROOT,
            "Composed program using the current-year allowance.",
            formula="current_year_income_reduction_allowance",
        ),
    )
    _git(rulespec, "add", "dk/statutes")
    _git(
        rulespec,
        "-c",
        "user.name=closure-ledger-test",
        "-c",
        "user.email=closure-ledger-test@example.invalid",
        "commit",
        "-qm",
        "hermetic RuleSpec baseline",
    )
    artifact.write_text(
        yaml.safe_dump(
            {"committed_decisions": _decisions()},
            sort_keys=False,
            allow_unicode=True,
        )
    )
    args = [
        "--artifact",
        str(artifact),
        "--corpus-release",
        str(corpus),
        "--corpus-ref",
        "main",
        "--rulespec-root",
        str(rulespec),
        "--rulespec-ref",
        "main",
    ]
    assert module.main(["--generate", *args]) == 0
    return module, artifact, args


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _write(module, path: Path, document: dict) -> None:
    path.write_text(module.serialize_artifact(document))


def _path_arg(args: list[str], name: str) -> Path:
    return Path(args[args.index(name) + 1])


def _commit_rulespec_change(root: Path, path: Path, message: str) -> None:
    _git(root, "add", str(path.relative_to(root)))
    _git(
        root,
        "-c",
        "user.name=closure-ledger-test",
        "-c",
        "user.email=closure-ledger-test@example.invalid",
        "commit",
        "-qm",
        message,
    )


def _configure_composed_proof_atom(
    source: dict,
    *,
    required: object = True,
    atom_path: str = "versions[0].formula",
    excerpt: str = "§ 2. Test provision body.",
) -> None:
    if required is _MISSING:
        source["module"].pop("proof_validation", None)
    else:
        source["module"]["proof_validation"] = {"required": required}
    source["rules"][0]["metadata"] = {
        "proof": {
            "atoms": [
                {
                    "path": atom_path,
                    "kind": "formula",
                    "source": {
                        "corpus_citation_path": f"{CORPUS_ROOT}/paragraf-2",
                        "excerpt": excerpt,
                    },
                }
            ]
        }
    }


def test_committed_dk_closure_artifact_is_internally_valid_and_closed() -> None:
    module = _load_script()
    document = _load(COMMITTED_ARTIFACT)
    summary = module.validate_artifact(document)

    assert summary.closed is True
    assert summary.encoded_count == 9
    assert summary.partially_encoded_count == 0
    assert summary.pending_count == 0
    assert summary.frontier_complete is True
    assert document["computed"]["provision_counts"] == {
        "total": 24,
        "encoded": 9,
        "partially-encoded": 0,
        "classified-with-reason": 1,
        "excluded-with-reason": 14,
        "pending": 0,
    }
    former_partial = next(
        row
        for row in document["computed"]["ledger"]
        if row["citation_path"] == f"{CORPUS_ROOT}/paragraf-5"
    )
    assert former_partial["status"] == "encoded"
    assert former_partial["encoded_by"].endswith("/paragraf-5.yaml")


def test_generation_parses_inputs_and_preserves_committed_decisions(
    tmp_path: Path,
) -> None:
    module, artifact, _ = _baseline(tmp_path)
    document = _load(artifact)

    assert document["committed_decisions"] == _decisions()
    assert {row["name"] for row in document["generated_facts"]["module_inputs"]} == {
        row["name"] for row in _decisions()["input_grounding"]
    }
    assert module.validate_artifact(document).frontier_complete is True


def test_check_rejects_a_paragraf_dropped_from_the_ledger(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module, artifact, args = _baseline(tmp_path)
    document = _load(artifact)
    document["computed"]["ledger"] = document["computed"]["ledger"][:-1]
    _write(module, artifact, document)

    assert module.main(["--check", *args]) == 1
    assert "ledger" in capsys.readouterr().err.lower()


def test_check_rejects_a_pending_row_hidden_as_an_exclusion(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module, artifact, args = _baseline(tmp_path)
    document = _load(artifact)
    pending = next(
        row for row in document["computed"]["ledger"] if row["status"] == "pending"
    )
    pending.update(
        {
            "status": "excluded-with-reason",
            "classification": "mutant",
            "reason": "This row was hidden without a committed decision.",
        }
    )
    counts = document["computed"]["provision_counts"]
    counts["pending"] -= 1
    counts["excluded-with-reason"] += 1
    document["computed"]["pending"] = []
    document["computed"]["closed"] = True
    _write(module, artifact, document)

    assert module.main(["--check", *args]) == 1
    error = capsys.readouterr().err.lower()
    assert "ledger" in error or "computed" in error


def test_validator_rejects_an_atom_level_partial_claim_hidden_as_pending() -> None:
    """A proof-atom join cannot be erased by relabeling its row and counts.

    The committed artifact no longer carries a partially-encoded row (wave 2
    encoded § 5 directly), so the mutant SYNTHESIZES the state the validator
    must protect: remove § 5's direct module (and its now-orphaned inputs and
    grounding rows), let the producer's own derivation rebuild the computed
    block — § 5 becomes partially-encoded via the composed proof atoms — then
    relabel that row as pending. The atoms still exist in the generated
    facts, so the relabel must be rejected."""

    module = _load_script()
    document = _load(COMMITTED_ARTIFACT)
    citation = f"{CORPUS_ROOT}/paragraf-5"
    modules = document["generated_facts"]["rulespec_modules"]
    direct = next(
        row for row in modules if row.get("source_citation_path") == citation
    )
    modules.remove(direct)
    remaining_ids = {m["module_id"] for m in modules}
    document["generated_facts"]["module_inputs"] = [
        r
        for r in document["generated_facts"]["module_inputs"]
        if r.get("module") in remaining_ids
    ]
    live_names = {r["name"] for r in document["generated_facts"]["module_inputs"]}
    document["committed_decisions"]["input_grounding"] = [
        r
        for r in document["committed_decisions"]["input_grounding"]
        if r["name"] in live_names
    ]
    derivation_errors: list[str] = []
    document["computed"] = module._derive_computed(
        document["generated_facts"],
        document["committed_decisions"],
        derivation_errors,
    )
    assert derivation_errors == []
    summary = module.validate_artifact(document)
    assert summary.partially_encoded_count == 1
    row = next(
        r for r in document["computed"]["ledger"] if r["citation_path"] == citation
    )
    assert row["status"] == "partially-encoded"

    row["status"] = "pending"
    row.pop("partially_encoded_by")
    row.pop("proof_atom_count")
    counts = document["computed"]["provision_counts"]
    counts["partially-encoded"] -= 1
    counts["pending"] += 1
    document["computed"]["partially_encoded"] = []
    document["computed"]["pending"] = [citation]

    import pytest as _pytest

    with _pytest.raises(module.ClosureLedgerError, match="computed"):
        module.validate_artifact(document)


def test_validator_rejects_duplicate_or_noncanonical_proof_atoms() -> None:
    module = _load_script()
    document = _load(COMMITTED_ARTIFACT)
    composed = next(
        row
        for row in document["generated_facts"]["rulespec_modules"]
        if row["source_citation_path"] == CORPUS_ROOT and row["proof_atoms"]
    )
    composed["proof_atoms"].append(dict(composed["proof_atoms"][0]))

    with pytest.raises(module.ClosureLedgerError, match="duplicates"):
        module.validate_artifact(document)


def test_check_rejects_a_frontier_input_removed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module, artifact, args = _baseline(tmp_path)
    document = _load(artifact)
    frontier = document["computed"]["boundary_frontier"]
    frontier["inputs"].pop()
    frontier["uncaptured_input_count"] -= 1
    _write(module, artifact, document)

    assert module.main(["--check", *args]) == 1
    assert "frontier" in capsys.readouterr().err.lower()


def test_check_rejects_a_grounding_decision_removed_with_its_frontier_row(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module, artifact, args = _baseline(tmp_path)
    document = _load(artifact)
    removed = next(
        row
        for row in document["committed_decisions"]["input_grounding"]
        if row["grounding"] == "uncaptured"
    )
    document["committed_decisions"]["input_grounding"].remove(removed)
    frontier = document["computed"]["boundary_frontier"]
    frontier["inputs"] = [
        row for row in frontier["inputs"] if row["input"] != removed["name"]
    ]
    frontier["uncaptured_input_count"] -= 1
    frontier["complete"] = False
    _write(module, artifact, document)

    assert module.main(["--check", *args]) == 1
    assert "grounding" in capsys.readouterr().err.lower()


@pytest.mark.parametrize(
    "mutated_hash",
    [None, "0" * 64],
    ids=("missing", "stale"),
)
def test_check_rejects_missing_or_stale_direct_module_source_hash(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    mutated_hash: str | None,
) -> None:
    module, _, args = _baseline(tmp_path)
    rulespec = _path_arg(args, "--rulespec-root")
    path = (
        rulespec / "dk/statutes/lbk-603-2025/boerne-og-ungeydelsesloven/paragraf-1.yaml"
    )
    document = yaml.safe_load(path.read_text())
    verification = document["module"]["source_verification"]
    if mutated_hash is None:
        verification.pop("source_sha256")
    else:
        verification["source_sha256"] = mutated_hash
    path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True))
    _commit_rulespec_change(rulespec, path, "mutate source hash")

    assert module.main(["--check", *args]) == 1
    assert "source_sha256" in capsys.readouterr().err


def test_check_rejects_an_unknown_module_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module, _, args = _baseline(tmp_path)
    rulespec = _path_arg(args, "--rulespec-root")
    path = (
        rulespec / "dk/statutes/lbk-603-2025/boerne-og-ungeydelsesloven/paragraf-4.yaml"
    )
    document = yaml.safe_load(path.read_text())
    document["module"]["status"] = "reviewed_but_not_executable"
    path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True))
    _commit_rulespec_change(rulespec, path, "mutate module status")

    assert module.main(["--check", *args]) == 1
    assert "unsupported module status" in capsys.readouterr().err


def test_full_verifier_rejects_a_coordinated_generated_spine_truncation(
    tmp_path: Path,
) -> None:
    module, artifact, args = _baseline(tmp_path)
    document = _load(artifact)
    generated = document["generated_facts"]
    generated["provision_spine"].pop(2)
    for ordinal, row in enumerate(generated["provision_spine"], start=1):
        row["ordinal"] = ordinal
    generated["corpus_release"]["declared_block_count"] -= 1
    errors: list[str] = []
    document["computed"] = module._derive_computed(  # noqa: SLF001
        generated,
        document["committed_decisions"],
        errors,
    )
    assert not errors
    # The internally coordinated rewrite is why certification must use the
    # full source verifier, not only the hermetic consistency validator.
    module.validate_artifact(document)
    _write(module, artifact, document)

    result = module.verify_artifact(
        artifact_path=artifact,
        corpus_release=_path_arg(args, "--corpus-release"),
        corpus_ref="main",
        rulespec_root=_path_arg(args, "--rulespec-root"),
        rulespec_ref="main",
    )
    assert result.valid is False
    assert any("drift" in error for error in result.errors)


def test_full_check_rejects_a_composed_proof_atom_hidden_with_its_partial_row(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Live atom evidence survives a coordinated generated-facts rewrite."""

    module, artifact, args = _baseline(tmp_path)
    rulespec = _path_arg(args, "--rulespec-root")
    path = rulespec / "dk/statutes/composed/boerne-og-ungeydelse-pipeline.yaml"
    source = yaml.safe_load(path.read_text())
    _configure_composed_proof_atom(source)
    path.write_text(yaml.safe_dump(source, sort_keys=False, allow_unicode=True))
    _commit_rulespec_change(rulespec, path, "add composed provision proof atom")
    assert module.main(["--generate", *args]) == 0

    document = _load(artifact)
    composed = next(
        row
        for row in document["generated_facts"]["rulespec_modules"]
        if row["path"] == "dk/statutes/composed/boerne-og-ungeydelse-pipeline.yaml"
    )
    assert len(composed["proof_atoms"]) == 1
    partial = next(
        row
        for row in document["computed"]["ledger"]
        if row["citation_path"] == f"{CORPUS_ROOT}/paragraf-2"
    )
    assert partial["status"] == "partially-encoded"

    # Coordinately hide both the generated atom and the derived partial row.
    # Hermetic derivation cannot inspect the sibling Git blob, so only the full
    # producer check can prove that the generated fact was erased.
    composed["proof_atoms"] = []
    errors: list[str] = []
    document["computed"] = module._derive_computed(  # noqa: SLF001
        document["generated_facts"],
        document["committed_decisions"],
        errors,
    )
    assert not errors
    module.validate_artifact(document)
    _write(module, artifact, document)

    assert module.main(["--check", *args]) == 1
    assert "drift" in capsys.readouterr().err.lower()


@pytest.mark.parametrize(
    "required",
    [_MISSING, False],
    ids=("missing", "false"),
)
def test_full_check_rejects_composed_atoms_without_required_proof_validation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    required: object,
) -> None:
    module, _, args = _baseline(tmp_path)
    rulespec = _path_arg(args, "--rulespec-root")
    path = rulespec / "dk/statutes/composed/boerne-og-ungeydelse-pipeline.yaml"
    source = yaml.safe_load(path.read_text())
    _configure_composed_proof_atom(source, required=required)
    path.write_text(yaml.safe_dump(source, sort_keys=False, allow_unicode=True))
    _commit_rulespec_change(rulespec, path, "mutate composed proof validation")

    assert module.main(["--check", *args]) == 1
    assert "proof_validation.required=true" in capsys.readouterr().err


def test_full_check_rejects_a_nonresolving_composed_atom_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module, _, args = _baseline(tmp_path)
    rulespec = _path_arg(args, "--rulespec-root")
    path = rulespec / "dk/statutes/composed/boerne-og-ungeydelse-pipeline.yaml"
    source = yaml.safe_load(path.read_text())
    _configure_composed_proof_atom(source, atom_path="versions[777].formula")
    path.write_text(yaml.safe_dump(source, sort_keys=False, allow_unicode=True))
    _commit_rulespec_change(rulespec, path, "mutate composed proof atom path")

    assert module.main(["--check", *args]) == 1
    assert "does not resolve to a version formula" in capsys.readouterr().err


def test_full_check_rejects_a_fabricated_composed_atom_excerpt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module, _, args = _baseline(tmp_path)
    rulespec = _path_arg(args, "--rulespec-root")
    path = rulespec / "dk/statutes/composed/boerne-og-ungeydelse-pipeline.yaml"
    source = yaml.safe_load(path.read_text())
    _configure_composed_proof_atom(
        source,
        excerpt="This cadence text is absent from the pinned provision.",
    )
    path.write_text(yaml.safe_dump(source, sort_keys=False, allow_unicode=True))
    _commit_rulespec_change(rulespec, path, "mutate composed proof atom excerpt")

    assert module.main(["--check", *args]) == 1
    assert "does not occur in pinned corpus provision" in capsys.readouterr().err


def test_rulespec_ref_is_resolved_once_before_tree_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, _, args = _baseline(tmp_path)
    rulespec = _path_arg(args, "--rulespec-root")
    resolved = subprocess.run(
        ["git", "-C", str(rulespec), "rev-parse", "main"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    observed: list[str] = []
    original_paths = module._rulespec_paths  # noqa: SLF001
    original_blob = module._rulespec_blob  # noqa: SLF001

    def paths(root: Path, ref: str) -> list[str]:
        observed.append(ref)
        return original_paths(root, ref)

    def blob(root: Path, ref: str, path: str) -> bytes:
        observed.append(ref)
        return original_blob(root, ref, path)

    monkeypatch.setattr(module, "_rulespec_paths", paths)
    monkeypatch.setattr(module, "_rulespec_blob", blob)
    module._read_rulespec_facts(rulespec, "main")  # noqa: SLF001
    assert observed and set(observed) == {resolved}


def test_dirty_truncated_corpus_worktree_cannot_change_ref_derived_ledger(
    tmp_path: Path,
) -> None:
    module, artifact, args = _baseline(tmp_path)
    committed_artifact = artifact.read_text()
    corpus = _path_arg(args, "--corpus-release")
    # Leave only the document line in the mutable worktree. Both modes must
    # continue to consume the exact committed blob selected by --corpus-ref.
    corpus.write_text(corpus.read_text().splitlines(keepends=True)[0])

    assert module.main(["--check", *args]) == 0
    assert module.main(["--generate", *args]) == 0
    assert artifact.read_text() == committed_artifact


def test_check_rejects_an_untracked_corpus_release(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module, _, args = _baseline(tmp_path)
    tracked = _path_arg(args, "--corpus-release")
    untracked = tracked.with_name("untracked-release.jsonl")
    untracked.write_bytes(tracked.read_bytes())
    mutant_args = list(args)
    mutant_args[mutant_args.index("--corpus-release") + 1] = str(untracked)

    assert module.main(["--check", *mutant_args]) == 1
    assert "not tracked" in capsys.readouterr().err


def test_full_check_accepts_the_hermetic_baseline(tmp_path: Path) -> None:
    module, _, args = _baseline(tmp_path)
    assert module.main(["--check", *args]) == 0
