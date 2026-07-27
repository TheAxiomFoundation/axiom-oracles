"""Hermetic negative tests for the closure-universe CI gate."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parents[1]
SCRIPT = REPO_ROOT / "scripts" / "closure_universe.py"

CORPUS_REPO = "https://github.com/TheAxiomFoundation/axiom-corpus.git"
CORPUS_REF = "origin/main@bf97b17baebfdf12601f7c23697524bf5adcdaed"
RULESPEC_REPO = "https://github.com/TheAxiomFoundation/rulespec-us.git"
RULESPEC_REF = "origin/main@1158ba5b248c3cbbfe1768357f03ca43c8b3618e"

STATE_UNIVERSE = "state-10-ccr-2506-1.yaml"
CFR_UNIVERSE = "us-7-cfr-273.yaml"


def _load_script():
    spec = importlib.util.spec_from_file_location("closure_universe", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_jsonl(path: Path, row: dict) -> None:
    path.write_text(json.dumps(row, sort_keys=True) + "\n")


def _provision(
    citation: str,
    heading: str,
    *,
    kind: str = "section",
    version: str,
) -> dict:
    return {
        "body": f"Test body for {heading}.",
        "citation_label": heading,
        "citation_path": citation,
        "document_class": "regulation" if "regulation" in citation else "statute",
        "heading": heading,
        "id": hashlib.sha256(citation.encode()).hexdigest(),
        "jurisdiction": citation.split("/", 1)[0],
        "kind": kind,
        "language": "en",
        "level": 2,
        "version": version,
    }


def _snapshot_entry(
    data_dir: Path,
    filename: str,
    *,
    source_repo: str,
    source_ref: str,
    source_path: str,
) -> dict:
    return {
        "file": filename,
        "source_repo": source_repo,
        "source_ref": source_ref,
        "source_path": source_path,
        "sha256": _sha256(data_dir / filename),
        "extraction": "Hermetic one-row test snapshot.",
    }


def _write_inputs(tmp_path: Path) -> Path:
    """Create one valid provision per configured root and a pinned file tree."""
    closure_dir = tmp_path / "closure"
    data_dir = closure_dir / "data"
    data_dir.mkdir(parents=True)

    _write_jsonl(
        data_dir / "cfr-273.jsonl",
        _provision(
            "us/regulation/7/273/1",
            "7 CFR 273.1",
            version="2026-07-15-title-7-part-273",
        ),
    )
    _write_jsonl(
        data_dir / "usc-51.jsonl",
        _provision(
            "us/statute/7/2011",
            "7 U.S.C. 2011",
            version="2026-07-21-snap-chapter-51-title-7-title-7",
        ),
    )
    _write_jsonl(
        data_dir / "co-provisions.jsonl",
        _provision(
            "us-co/regulation/10-ccr-2506-1/4.100",
            "10 CCR 2506-1 4.100",
            version="2026-07-16-10-ccr-2506-1",
        ),
    )

    # Federal rows resolve exactly to modules. The Colorado row intentionally
    # has no module so the baseline has one pending provision for ratchet tests.
    (data_dir / "rulespec-us-files.txt").write_text(
        "us/regulations/7-cfr/273/1.yaml\nus/statutes/7/2011.yaml\n"
    )

    provenance = {
        "schema": "axiom_oracles.closure.provenance.v1",
        "as_of": "2026-07-27",
        "snapshots": [
            _snapshot_entry(
                data_dir,
                "cfr-273.jsonl",
                source_repo=CORPUS_REPO,
                source_ref=CORPUS_REF,
                source_path=(
                    "data/corpus/provisions/us/regulation/"
                    "2026-07-15-title-7-part-273.jsonl"
                ),
            ),
            _snapshot_entry(
                data_dir,
                "usc-51.jsonl",
                source_repo=CORPUS_REPO,
                source_ref=CORPUS_REF,
                source_path=(
                    "data/corpus/provisions/us/statute/"
                    "2026-07-21-snap-chapter-51-title-7-title-7.jsonl"
                ),
            ),
            _snapshot_entry(
                data_dir,
                "co-provisions.jsonl",
                source_repo=CORPUS_REPO,
                source_ref=CORPUS_REF,
                source_path=(
                    "data/corpus/provisions/us-co/regulation/"
                    "2026-07-16-10-ccr-2506-1.jsonl"
                ),
            ),
            _snapshot_entry(
                data_dir,
                "rulespec-us-files.txt",
                source_repo=RULESPEC_REPO,
                source_ref=RULESPEC_REF,
                source_path=".",
            ),
        ],
    }
    (data_dir / "provenance.yaml").write_text(
        yaml.safe_dump(provenance, sort_keys=False)
    )
    return closure_dir


def _generate_baseline(tmp_path: Path):
    module = _load_script()
    closure_dir = _write_inputs(tmp_path)
    assert module.main(["--generate", "--closure-dir", str(closure_dir)]) == 0
    return module, closure_dir


def _load_universe(closure_dir: Path, filename: str) -> tuple[Path, dict]:
    path = closure_dir / "universes" / "us-co-snap" / filename
    return path, yaml.safe_load(path.read_text())


def _write_universe(path: Path, document: dict) -> None:
    path.write_text(yaml.safe_dump(document, sort_keys=False))


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
    )


def _update_snapshot_hash(closure_dir: Path, filename: str) -> None:
    """Refresh one tmpdir provenance digest after a deliberate pin mutation."""

    path = closure_dir / "data" / "provenance.yaml"
    provenance = yaml.safe_load(path.read_text())
    snapshot = next(row for row in provenance["snapshots"] if row["file"] == filename)
    snapshot["sha256"] = _sha256(closure_dir / "data" / filename)
    path.write_text(yaml.safe_dump(provenance, sort_keys=False))


def _commit_closure_baseline(closure_dir: Path) -> None:
    """Commit a tmpdir baseline so coordinated edits face immutable history."""

    repo = closure_dir.parent
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", "closure")
    _git(
        repo,
        "-c",
        "user.name=closure-test",
        "-c",
        "user.email=closure-test@example.invalid",
        "commit",
        "-q",
        "-m",
        "closure baseline",
    )


def _tighten_state_pending_to_zero(module, closure_dir: Path) -> tuple[Path, dict]:
    """Replace the one pending state row with a reviewed exclusion and tighten."""
    path, document = _load_universe(closure_dir, STATE_UNIVERSE)
    row = document["provisions"][0]
    assert row["status"] == "pending"
    assert document["ratchet"]["pending_max"] == 1
    row["status"] = "excluded"
    row["reason"] = "container_heading"
    row["basis"] = "This test row is a bodyless heading container."
    _write_universe(path, document)
    assert module.main(["--generate", "--closure-dir", str(closure_dir)]) == 0
    return _load_universe(closure_dir, STATE_UNIVERSE)


def test_generated_baseline_passes_check(tmp_path, capsys):
    module, closure_dir = _generate_baseline(tmp_path)

    assert module.main(["--check", "--closure-dir", str(closure_dir)]) == 0
    assert "closure" in capsys.readouterr().out.lower()


def test_excluded_without_basis_fails(tmp_path, capsys):
    module, closure_dir = _generate_baseline(tmp_path)
    path, document = _load_universe(closure_dir, STATE_UNIVERSE)
    row = document["provisions"][0]
    row["status"] = "excluded"
    row["reason"] = "container_heading"
    row.pop("basis", None)
    _write_universe(path, document)

    assert module.main(["--check", "--closure-dir", str(closure_dir)]) == 1
    error = capsys.readouterr().err.lower()
    assert "4.100" in error
    assert "basis" in error


def test_ghost_encoded_by_fails(tmp_path, capsys):
    module, closure_dir = _generate_baseline(tmp_path)
    path, document = _load_universe(closure_dir, CFR_UNIVERSE)
    row = document["provisions"][0]
    row["encoded_by"] = ["us/regulations/7-cfr/273/ghost.yaml"]
    _write_universe(path, document)

    assert module.main(["--check", "--closure-dir", str(closure_dir)]) == 1
    error = capsys.readouterr().err.lower()
    assert "ghost.yaml" in error
    assert "pinned tree" in error


def test_taxonomy_violating_reason_fails(tmp_path, capsys):
    module, closure_dir = _generate_baseline(tmp_path)
    path, document = _load_universe(closure_dir, STATE_UNIVERSE)
    row = document["provisions"][0]
    row["status"] = "excluded"
    row["reason"] = "procedural"
    row["basis"] = "The test provision is procedural."
    _write_universe(path, document)

    assert module.main(["--check", "--closure-dir", str(closure_dir)]) == 1
    error = capsys.readouterr().err.lower()
    assert "procedural" in error
    assert "taxonomy" in error


def test_pending_regression_fails_when_provenance_is_unchanged(tmp_path, capsys):
    module, closure_dir = _generate_baseline(tmp_path)
    path, document = _tighten_state_pending_to_zero(module, closure_dir)
    assert document["ratchet"]["pending_max"] == 0
    row = document["provisions"][0]
    row["status"] = "pending"
    row.pop("reason")
    row.pop("basis")
    _write_universe(path, document)

    assert module.main(["--check", "--closure-dir", str(closure_dir)]) == 1
    error = capsys.readouterr().err.lower()
    assert "state-10-ccr-2506-1" in error
    assert "pending" in error
    assert "ratchet" in error


def test_pending_regression_cannot_raise_only_universe_ceiling(tmp_path, capsys):
    module, closure_dir = _generate_baseline(tmp_path)
    path, document = _tighten_state_pending_to_zero(module, closure_dir)
    row = document["provisions"][0]
    row["status"] = "pending"
    row.pop("reason")
    row.pop("basis")
    document["ratchet"]["pending_max"] = 1
    _write_universe(path, document)

    assert module.main(["--generate", "--closure-dir", str(closure_dir)]) == 1
    error = capsys.readouterr().err.lower()
    assert "state-10-ccr-2506-1" in error
    assert "ratchet" in error
    assert "summary" in error


def test_pending_regression_cannot_reset_via_universe_provenance(tmp_path, capsys):
    module, closure_dir = _generate_baseline(tmp_path)
    path, document = _tighten_state_pending_to_zero(module, closure_dir)
    row = document["provisions"][0]
    row["status"] = "pending"
    row.pop("reason")
    row.pop("basis")
    document["provenance"]["source_repo"] = "https://example.invalid/tampered.git"
    _write_universe(path, document)

    assert module.main(["--generate", "--closure-dir", str(closure_dir)]) == 1
    error = capsys.readouterr().err.lower()
    assert "state-10-ccr-2506-1" in error
    assert "ratchet" in error
    assert "provenance" in error or "pins" in error


def test_pending_regression_cannot_raise_both_committed_ceilings(tmp_path, capsys):
    module, closure_dir = _generate_baseline(tmp_path)
    path, document = _tighten_state_pending_to_zero(module, closure_dir)
    _commit_closure_baseline(closure_dir)

    row = document["provisions"][0]
    row["status"] = "pending"
    row.pop("reason")
    row.pop("basis")
    document["ratchet"]["pending_max"] = 1
    _write_universe(path, document)

    summary_path = closure_dir / "summary.json"
    summary = json.loads(summary_path.read_text())
    state = next(
        root for root in summary["roots"] if root["root"] == "state-10-ccr-2506-1"
    )
    state["by_status"] = {"encoded": 0, "excluded": 0, "pending": 1}
    state["pending_max"] = 1
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")

    assert module.main(["--generate", "--closure-dir", str(closure_dir)]) == 1
    error = capsys.readouterr().err.lower()
    assert "state-10-ccr-2506-1" in error
    assert "ratchet" in error
    assert "regressed" in error


def test_pending_regression_cannot_forge_a_pin_reset(tmp_path, capsys):
    module, closure_dir = _generate_baseline(tmp_path)
    path, document = _tighten_state_pending_to_zero(module, closure_dir)
    _commit_closure_baseline(closure_dir)

    row = document["provisions"][0]
    row["status"] = "pending"
    row.pop("reason")
    row.pop("basis")
    document["provenance"]["source_sha256"] = "1" * 64
    forged_pins = module._pins_sha256(document["provenance"])
    document["ratchet"] = {
        "pins_sha256": forged_pins,
        "pending_max": 1,
    }
    _write_universe(path, document)

    summary_path = closure_dir / "summary.json"
    summary = json.loads(summary_path.read_text())
    state = next(
        root for root in summary["roots"] if root["root"] == "state-10-ccr-2506-1"
    )
    state["by_status"] = {"encoded": 0, "excluded": 0, "pending": 1}
    state["pins_sha256"] = forged_pins
    state["pending_max"] = 1
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")

    assert module.main(["--generate", "--closure-dir", str(closure_dir)]) == 1
    error = capsys.readouterr().err.lower()
    assert "state-10-ccr-2506-1" in error
    assert "ratchet" in error
    assert "regressed" in error


def test_pending_regression_cannot_hide_in_simplified_merge_history(tmp_path, capsys):
    module, closure_dir = _generate_baseline(tmp_path)
    _commit_closure_baseline(closure_dir)
    repo = closure_dir.parent
    _git(repo, "branch", "stale")

    _tighten_state_pending_to_zero(module, closure_dir)
    _git(repo, "add", "closure")
    _git(
        repo,
        "-c",
        "user.name=closure-test",
        "-c",
        "user.email=closure-test@example.invalid",
        "commit",
        "-q",
        "-m",
        "tighten pending floor",
    )

    _git(repo, "checkout", "-q", "stale")
    _git(
        repo,
        "-c",
        "user.name=closure-test",
        "-c",
        "user.email=closure-test@example.invalid",
        "merge",
        "-q",
        "-s",
        "ours",
        "main",
        "-m",
        "retain stale universe across merge",
    )

    assert module.main(["--check", "--closure-dir", str(closure_dir)]) == 1
    error = capsys.readouterr().err.lower()
    assert "state-10-ccr-2506-1" in error
    assert "ratchet" in error
    assert "regressed" in error


def test_pin_update_rederives_an_ordinary_encoded_row(tmp_path, capsys):
    module, closure_dir = _generate_baseline(tmp_path)
    tree_path = closure_dir / "data" / "rulespec-us-files.txt"
    tree_path.write_text("us/statutes/7/2011.yaml\n")
    _update_snapshot_hash(closure_dir, "rulespec-us-files.txt")

    assert module.main(["--generate", "--closure-dir", str(closure_dir)]) == 0
    _, document = _load_universe(closure_dir, CFR_UNIVERSE)
    assert document["provisions"][0]["status"] == "pending"
    assert "encoded_by" not in document["provisions"][0]
    assert module.main(["--check", "--closure-dir", str(closure_dir)]) == 0
    capsys.readouterr()


def test_corrected_encoded_by_survives_regeneration(tmp_path, capsys):
    module, closure_dir = _generate_baseline(tmp_path)
    path, document = _load_universe(closure_dir, STATE_UNIVERSE)
    corrected_path = "us/regulations/7-cfr/273/1.yaml"
    document["provisions"][0]["status"] = "encoded"
    document["provisions"][0]["encoded_by"] = [corrected_path]
    _write_universe(path, document)

    assert module.main(["--generate", "--closure-dir", str(closure_dir)]) == 0
    _, regenerated = _load_universe(closure_dir, STATE_UNIVERSE)
    assert regenerated["provisions"][0]["status"] == "encoded"
    assert regenerated["provisions"][0]["encoded_by"] == [corrected_path]
    assert module.main(["--check", "--closure-dir", str(closure_dir)]) == 0
    capsys.readouterr()


def test_descendant_module_does_not_encode_its_parent(tmp_path, capsys):
    module, closure_dir = _generate_baseline(tmp_path)
    data_dir = closure_dir / "data"
    _write_jsonl(
        data_dir / "cfr-273.jsonl",
        _provision(
            "us/regulation/7/273/2",
            "7 CFR 273.2",
            version="2026-07-15-title-7-part-273",
        ),
    )
    (data_dir / "rulespec-us-files.txt").write_text(
        "us/regulations/7-cfr/273/2/j.yaml\nus/statutes/7/2011.yaml\n"
    )
    _update_snapshot_hash(closure_dir, "cfr-273.jsonl")
    _update_snapshot_hash(closure_dir, "rulespec-us-files.txt")

    assert module.main(["--generate", "--closure-dir", str(closure_dir)]) == 0
    _, document = _load_universe(closure_dir, CFR_UNIVERSE)
    assert document["provisions"][0]["citation"].endswith("/273/2")
    assert document["provisions"][0]["status"] == "pending"
    assert module.main(["--check", "--closure-dir", str(closure_dir)]) == 0
    capsys.readouterr()


def test_citation_drift_fails(tmp_path, capsys):
    module, closure_dir = _generate_baseline(tmp_path)
    path, document = _load_universe(closure_dir, STATE_UNIVERSE)
    document["provisions"][0]["citation"] = "us-co/regulation/10-ccr-2506-1/4.999"
    _write_universe(path, document)

    assert module.main(["--check", "--closure-dir", str(closure_dir)]) == 1
    error = capsys.readouterr().err.lower()
    assert "citation drift" in error
    assert "4.999" in error


def test_operationalized_by_tolerates_yaml_spacing_but_not_unsafe_paths(
    tmp_path, capsys
):
    """`operationalized_by: <path>` is the natural YAML form and must pass.

    The parse strips the separator so spacing cannot decide a verdict, but the
    extracted path is still held to every safety property. Both halves are
    asserted: the spaced form of a module that exists is accepted, and a spaced
    form naming a traversal path is still rejected.
    """
    module, closure_dir = _generate_baseline(tmp_path)
    path, document = _load_universe(closure_dir, STATE_UNIVERSE)
    row = document["provisions"][0]
    row["status"] = "excluded"
    row.pop("encoded_by", None)
    row["reason"] = "operationalized_by: us/regulations/7-cfr/273/1.yaml"
    row["basis"] = "Spaced YAML form naming a module present in the pinned tree."
    _write_universe(path, document)
    assert module.main(["--generate", "--closure-dir", str(closure_dir)]) == 0
    assert module.main(["--check", "--closure-dir", str(closure_dir)]) == 0
    capsys.readouterr()

    _, document = _load_universe(closure_dir, STATE_UNIVERSE)
    row = document["provisions"][0]
    row["reason"] = "operationalized_by: ../../etc/passwd.yaml"
    _write_universe(path, document)
    assert module.main(["--check", "--closure-dir", str(closure_dir)]) == 1
    assert "operationalized_by" in capsys.readouterr().err.lower()


def test_partial_coverage_survives_regeneration_and_requires_a_statement(
    tmp_path, capsys
):
    """A joined module that defers its substantive content stays pending.

    A citation-path join proves a module file exists; it cannot prove the
    module computes the provision. Seven 7 CFR 273 modules declare
    `deferred_outputs` naming what they do not compute, so a plain status edit
    is not enough — regeneration would re-upgrade the row from the join and
    silently restore the overstatement. The marker must survive, and it must
    say what is missing.
    """
    module, closure_dir = _generate_baseline(tmp_path)
    path, document = _load_universe(closure_dir, STATE_UNIVERSE)
    row = document["provisions"][0]
    row["status"] = "encoded"
    row["encoded_by"] = ["us/regulations/7-cfr/273/1.yaml"]
    _write_universe(path, document)
    assert module.main(["--generate", "--closure-dir", str(closure_dir)]) == 0

    _, document = _load_universe(closure_dir, STATE_UNIVERSE)
    row = document["provisions"][0]
    row["status"] = "pending"
    row.pop("encoded_by")
    row["partial_coverage"] = "Module defers paragraphs (b) and (c) via deferred_outputs."
    _write_universe(path, document)
    assert module.main(["--generate", "--closure-dir", str(closure_dir)]) == 0

    _, regenerated = _load_universe(closure_dir, STATE_UNIVERSE)
    assert regenerated["provisions"][0]["status"] == "pending"
    assert "partial_coverage" in regenerated["provisions"][0]
    assert module.main(["--check", "--closure-dir", str(closure_dir)]) == 0
    capsys.readouterr()

    _, document = _load_universe(closure_dir, STATE_UNIVERSE)
    document["provisions"][0]["partial_coverage"] = "   "
    _write_universe(path, document)
    assert module.main(["--check", "--closure-dir", str(closure_dir)]) == 1
    assert "partial_coverage" in capsys.readouterr().err.lower()


def test_disclosure_is_what_distinguishes_a_correction_from_a_regression(
    tmp_path, capsys
):
    """Same pending rise, opposite verdicts, decided only by disclosure.

    `test_pending_regression_fails_when_provenance_is_unchanged` already proves
    a bare rise is blocked at a tightened baseline. This asserts the other arm
    at the same baseline: the identical rise is ACCEPTED when the row states
    which outputs the joined module does not compute. If both arms ever agree,
    the allowance has either become a hole or stopped working.
    """
    module, closure_dir = _generate_baseline(tmp_path)
    path, document = _tighten_state_pending_to_zero(module, closure_dir)
    assert document["ratchet"]["pending_max"] == 0
    row = document["provisions"][0]
    row["status"] = "pending"
    row.pop("reason")
    row.pop("basis")
    row["partial_coverage"] = (
        "The joined module declares deferred_outputs for paragraphs (b) and "
        "(c); the join proves the file exists, not that it computes them."
    )
    _write_universe(path, document)

    assert module.main(["--generate", "--closure-dir", str(closure_dir)]) == 0
    assert module.main(["--check", "--closure-dir", str(closure_dir)]) == 0
    capsys.readouterr()
