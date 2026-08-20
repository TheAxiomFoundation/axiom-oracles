"""Hermetic mutants for the NZ executable receipt."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "nz_executable_reproduction.py"
RECEIPT = REPO_ROOT / "conformance" / "executable" / "nz-treasury-incomeexplorer.json"


def _load_script():
    spec = importlib.util.spec_from_file_location("nz_executable_reproduction", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    return path


def _receipt_with_current_hashes(module, original, summary):
    """Model a coordinated in-place artifact edit while files live in tmp_path."""

    document = copy.deepcopy(original)
    for block, path in (
        ("composition", module.COMPOSITION_PATH),
        ("compiled_artifact", module.ARTIFACT_PATH),
        ("request_set", module.REQUESTS_PATH),
        ("independent_expected", module.GOLDEN_PATH),
        ("full_responses", module.FULL_RESPONSES_PATH),
        ("transcript", module.TRANSCRIPT_PATH),
        ("source_report", module.SOURCE_REPORT_PATH),
        ("execution_trace", module.EVALUATION_TRACE_PATH),
        ("treasury_snapshot", module.TREASURY_SNAPSHOT_PATH),
        ("reducer", module.REDUCER_PATH),
    ):
        document[block]["sha256"] = module._sha256(path)
    document["compiled_artifact"]["byte_count"] = module.ARTIFACT_PATH.stat().st_size
    document["programs"] = sorted(summary["programs"])
    document["summary"] = copy.deepcopy(summary)
    return document


def test_committed_nz_executable_receipt_validates_hermetically():
    module = _load_script()
    summary = module.validate_artifact(json.loads(RECEIPT.read_text()))

    assert summary["program_count"] == 7
    assert summary["request_count"] == 19
    assert summary["response_count"] == 19
    assert summary["comparison_cell_count"] == 22
    assert summary["all_trace_responses_reproduced"] is True
    assert summary["all_independent_cells_reproduced"] is True
    assert all(row["executable"] for row in summary["programs"].values())


def test_source_built_engine_mode_cannot_skip_live_replay(capsys):
    """MUTANT: the portable-build label cannot decorate a hermetic-only check."""

    module = _load_script()

    assert module.main(["--check", "--source-built-engine"]) == 1
    assert "--source-built-engine requires --live" in capsys.readouterr().err


def test_live_engine_checkout_must_match_pinned_head(tmp_path, monkeypatch):
    """MUTANT: a binary beside the wrong engine checkout cannot be replayed."""

    module = _load_script()
    engine_root = tmp_path / "axiom-rules-engine"
    engine_binary = tmp_path / "target" / "release" / "axiom-rules-engine"
    calls = []

    def wrong_head(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout="0" * 40 + "\n")

    monkeypatch.setattr(module, "_run", wrong_head)

    with pytest.raises(ValueError, match="does not match the pinned Git SHA"):
        module._prepare_live_engine(
            engine_root=engine_root,
            engine_binary=engine_binary,
            source_built_engine=False,
        )

    assert calls == [
        (["git", "-C", str(engine_root), "rev-parse", "HEAD"], {})
    ]


def test_source_built_engine_invokes_locked_release_build(tmp_path, monkeypatch):
    """MUTANT: source-built mode must issue the portable pinned Cargo build."""

    module = _load_script()
    engine_root = tmp_path / "axiom-rules-engine"
    engine_binary = tmp_path / "target" / "release" / "axiom-rules-engine"
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command[0] == "git":
            return SimpleNamespace(stdout=module.ENGINE_GIT_SHA + "\n")
        assert command[0] == "cargo"
        engine_binary.parent.mkdir(parents=True)
        engine_binary.write_bytes(b"hermetic fake source build")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(module, "_run", fake_run)
    module._prepare_live_engine(
        engine_root=engine_root,
        engine_binary=engine_binary,
        source_built_engine=True,
    )

    assert calls[0] == (
        ["git", "-C", str(engine_root), "rev-parse", "HEAD"],
        {},
    )
    build, options = calls[1]
    assert build == [
        "cargo",
        "build",
        "--locked",
        "--release",
        "--manifest-path",
        str(engine_root / "Cargo.toml"),
        "--bin",
        "axiom-rules-engine",
    ]
    assert options["cwd"] == engine_root
    assert options["env"]["CARGO_TARGET_DIR"] == str(tmp_path / "target")


def test_ci_wires_the_pinned_source_build_and_live_replay():
    """MUTANT: deleting the portable CI leg must make the test suite red."""

    module = _load_script()
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text())
    steps = workflow["jobs"]["test"]["steps"]
    cache = next(
        step
        for step in steps
        if step.get("name") == "Cache pinned NZ engine source build"
    )
    engine_checkout = next(
        step for step in steps if step.get("name") == "Checkout pinned NZ engine source"
    )
    rulespec_checkout = next(
        step
        for step in steps
        if step.get("name") == "Checkout pinned NZ RuleSpec source"
    )
    replay = next(
        step
        for step in steps
        if step.get("name") == "Build pinned NZ engine and replay committed requests"
    )

    assert cache["uses"] == "actions/cache@v4"
    assert module.ENGINE_GIT_SHA in cache["with"]["key"]
    assert engine_checkout["uses"] == "actions/checkout@v4"
    assert engine_checkout["with"]["repository"] == (
        "TheAxiomFoundation/axiom-rules-engine"
    )
    assert engine_checkout["with"]["ref"] == module.ENGINE_GIT_SHA
    assert rulespec_checkout["uses"] == "actions/checkout@v4"
    assert rulespec_checkout["with"]["repository"] == "TheAxiomFoundation/rulespec-nz"
    assert rulespec_checkout["with"]["ref"] == module.RULESPEC_SHA
    run = replay["run"]
    assert "cargo build --locked --release" in run
    assert "--bin axiom-rules-engine" in run
    assert "--check --live --source-built-engine" in run


def test_compiled_artifact_bytes_must_match_recorded_digest(tmp_path, monkeypatch):
    module = _load_script()
    mutant = tmp_path / "compiled-program.json"
    mutant.write_bytes(module.ARTIFACT_PATH.read_bytes() + b" ")
    monkeypatch.setattr(module, "ARTIFACT_PATH", mutant)

    with pytest.raises(ValueError, match="compiled artifact bytes drifted"):
        module.validate_artifact(json.loads(RECEIPT.read_text()))


def test_transcript_digest_is_bound_into_receipt():
    module = _load_script()
    mutant = copy.deepcopy(json.loads(RECEIPT.read_text()))
    mutant["transcript"]["sha256"] = "0" * 64

    with pytest.raises(ValueError, match="not derived from committed artifacts"):
        module.validate_artifact(mutant)


def test_response_sha256_is_derived_from_committed_full_response():
    module = _load_script()
    requests = module._load(module.REQUESTS_PATH)
    context = module._validate_requests(requests)
    responses = module._load(module.FULL_RESPONSES_PATH)
    mutant = copy.deepcopy(responses)
    mutant["requests"][0]["response_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="not derived from full response bytes"):
        module._validate_full_responses(mutant, requests, context)


def test_full_response_output_tamper_is_rejected_by_execution_trace():
    module = _load_script()
    requests = module._load(module.REQUESTS_PATH)
    context = module._validate_requests(requests)
    responses = module._load(module.FULL_RESPONSES_PATH)
    mutant = copy.deepcopy(responses)
    row = mutant["requests"][0]
    output = next(iter(row["response"]["results"][0]["outputs"].values()))
    output["value"]["value"] = "888888"
    row["response_sha256"] = module._sha256_bytes(module._canonical(row["response"]))

    with pytest.raises(ValueError, match="#476 execution trace"):
        module._validate_full_responses(mutant, requests, context)


def test_unexecuted_request_injection_is_rejected_even_when_root_is_declared():
    """MUTANT: new evidence request/root bytes absent from #476 must red."""

    module = _load_script()
    requests = module._load(module.REQUESTS_PATH)
    mutant = copy.deepcopy(requests)
    row = copy.deepcopy(mutant["requests"][0])
    row["id"] = "mutant-unexecuted-request"
    row["request"]["dataset"]["inputs"][0]["value"]["value"] = "888888"
    mutant["requests"].append(row)

    with pytest.raises(ValueError, match="absent from the committed #476"):
        module._validate_requests(mutant)


def test_coordinated_golden_and_transcript_888888_tamper_is_rejected():
    """MUTANT: the audit's self-authoritative 888888 edit cannot mint truth."""

    module = _load_script()
    _report, expected_cells = module._source_and_expected_cells()
    golden = module._load(module.GOLDEN_PATH)
    transcript = module._load(module.TRANSCRIPT_PATH)
    golden_mutant = copy.deepcopy(golden)
    transcript_mutant = copy.deepcopy(transcript)
    golden_cell = next(
        cell
        for cell in golden_mutant["comparison_cells"]
        if cell["weekly_wage"] == 0 and cell["column"] == "net_benefit"
    )
    transcript_cell = next(
        cell
        for cell in transcript_mutant["comparison_cells"]
        if cell["weekly_wage"] == 0 and cell["column"] == "net_benefit"
    )
    golden_cell["declared_rulespec_value"] = "888888"
    transcript_cell["declared_rulespec_value"] = "888888"
    transcript_cell["rulespec_value"] = "888888"

    # The Treasury/source-derived expected document is reconstructed rather
    # than accepted from either coordinated artifact.
    with pytest.raises(ValueError, match="not derived from Treasury"):
        module._validate_golden(golden_mutant, expected_cells)


def test_end_to_end_full_response_transcript_888888_tamper_reds(
    tmp_path,
    monkeypatch,
):
    """MUTANT: the audit's old golden-output attack reds at the #476 trace."""

    module = _load_script()
    receipt = module._load(module.RECEIPT_PATH)
    full_responses = module._load(module.FULL_RESPONSES_PATH)
    transcript = module._load(module.TRANSCRIPT_PATH)
    response_row = next(
        row for row in full_responses["requests"] if row["id"] == "golden-00"
    )
    output = next(
        iter(response_row["response"]["results"][0]["outputs"].values())
    )
    output["value"]["value"] = "888888"
    response_row["response_sha256"] = module._sha256_bytes(
        module._canonical(response_row["response"])
    )
    transcript_request = next(
        row for row in transcript["requests"] if row["id"] == "golden-00"
    )
    transcript_request["response_sha256"] = response_row["response_sha256"]
    transcript_cell = next(
        cell
        for cell in transcript["comparison_cells"]
        if cell["weekly_wage"] == 0 and cell["column"] == "net_benefit"
    )
    transcript_cell["rulespec_value"] = "888888"

    full_responses_path = _write(tmp_path / "full-responses.json", full_responses)
    transcript_path = _write(tmp_path / "transcript.json", transcript)
    monkeypatch.setattr(module, "FULL_RESPONSES_PATH", full_responses_path)
    monkeypatch.setattr(module, "TRANSCRIPT_PATH", transcript_path)
    mutant_receipt = _receipt_with_current_hashes(
        module, receipt, receipt["summary"]
    )

    with pytest.raises(ValueError, match="#476 execution trace"):
        module.validate_artifact(mutant_receipt)


def test_declared_cell_777777_tamper_fails_fresh_reducer(tmp_path, monkeypatch):
    """MUTANT: audit's declared-cell edit cannot evade engine reconstruction."""

    module = _load_script()
    source = module._load(module.SOURCE_REPORT_PATH)
    source_row = next(
        row
        for row in source["comparisons"]
        if row["scenario_id"] == module.SCENARIO_ID
        and row["weekly_wage"] == 0
        and row["column"] == "net_benefit"
    )
    source_row["rulespec"] = "777777"
    source_path = _write(tmp_path / "source-comparison.json", source)
    monkeypatch.setattr(module, "SOURCE_REPORT_PATH", source_path)
    monkeypatch.setattr(module, "SOURCE_REPORT_SHA256", module._sha256(source_path))

    _report, expected_cells = module._source_and_expected_cells()
    requests = module._load(module.REQUESTS_PATH)
    context = module._validate_requests(requests)
    full_responses = module._load(module.FULL_RESPONSES_PATH)
    responses_by_id = module._validate_full_responses(full_responses, requests, context)
    transcript = module._transcript_document(
        requests, full_responses, responses_by_id, expected_cells
    )

    with pytest.raises(ValueError, match="fresh reduced cells differ"):
        module._validate_transcript(
            transcript,
            requests,
            full_responses,
            responses_by_id,
            expected_cells,
            context["roots"],
        )


def test_end_to_end_declared_cell_777777_tamper_fails_fresh_reducer(
    tmp_path,
    monkeypatch,
):
    """MUTANT: rehashing source/golden/receipt cannot overrule the reducer."""

    module = _load_script()
    receipt = module._load(module.RECEIPT_PATH)
    canonical_golden = module._load(module.GOLDEN_PATH)
    source = module._load(module.SOURCE_REPORT_PATH)
    source_row = next(
        row
        for row in source["comparisons"]
        if row["scenario_id"] == module.SCENARIO_ID
        and row["weekly_wage"] == 0
        and row["column"] == "net_benefit"
    )
    source_row["rulespec"] = "777777"
    source_path = _write(tmp_path / "source-comparison.json", source)
    monkeypatch.setattr(module, "SOURCE_REPORT_PATH", source_path)
    monkeypatch.setattr(module, "SOURCE_REPORT_SHA256", module._sha256(source_path))

    def expected_document(cells):
        return {
            "schema": module.GOLDEN_SCHEMA,
            "treasury_snapshot": copy.deepcopy(
                canonical_golden["treasury_snapshot"]
            ),
            "source_classifications": {
                "path": canonical_golden["source_classifications"]["path"],
                "sha256": module._sha256(source_path),
            },
            "comparison_cells": list(cells),
        }

    monkeypatch.setattr(module, "_expected_document", expected_document)
    _report, expected_cells = module._source_and_expected_cells()
    golden = expected_document(expected_cells)
    golden_path = _write(tmp_path / "golden-outputs.json", golden)
    monkeypatch.setattr(module, "GOLDEN_PATH", golden_path)

    requests = module._load(module.REQUESTS_PATH)
    context = module._validate_requests(requests)
    validate_ancestor_denominators = module._validate_ancestor_denominators

    def validate_mutant_ancestor_denominators(current_requests, current_cells):
        return validate_ancestor_denominators(
            current_requests,
            current_cells,
            ancestor_documents={
                "committed baseline": (requests, canonical_golden),
            },
        )

    monkeypatch.setattr(
        module,
        "_validate_ancestor_denominators",
        validate_mutant_ancestor_denominators,
    )
    full_responses = module._load(module.FULL_RESPONSES_PATH)
    responses_by_id = module._validate_full_responses(
        full_responses, requests, context
    )
    transcript = module._transcript_document(
        requests, full_responses, responses_by_id, expected_cells
    )
    transcript_path = _write(tmp_path / "transcript.json", transcript)
    monkeypatch.setattr(module, "TRANSCRIPT_PATH", transcript_path)
    mutant_summary = module._summary(transcript, context["roots"])
    assert mutant_summary["all_independent_cells_reproduced"] is False

    def expected_receipt(summary):
        return _receipt_with_current_hashes(module, receipt, summary)

    monkeypatch.setattr(module, "_receipt_document", expected_receipt)
    mutant_receipt = expected_receipt(mutant_summary)

    with pytest.raises(ValueError, match="fresh reduced cells differ"):
        module.validate_artifact(mutant_receipt)


def test_source_classification_tamper_fails_fresh_classifier(
    tmp_path,
    monkeypatch,
):
    """MUTANT: source labels cannot bypass the deterministic classifier."""

    module = _load_script()
    source = module._load(module.SOURCE_REPORT_PATH)
    source_row = next(
        row
        for row in source["comparisons"]
        if row["scenario_id"] == module.SCENARIO_ID
        and row["weekly_wage"] == 0
        and row["column"] == "net_benefit"
    )
    assert (source_row["classification"], source_row["reason_code"]) != (
        "match",
        "MATCH_SNAPSHOT_PRECISION",
    )
    source_row["classification"] = "match"
    source_row["reason_code"] = "MATCH_SNAPSHOT_PRECISION"
    source_path = _write(tmp_path / "source-comparison.json", source)
    monkeypatch.setattr(module, "SOURCE_REPORT_PATH", source_path)
    monkeypatch.setattr(module, "SOURCE_REPORT_SHA256", module._sha256(source_path))

    _report, expected_cells = module._source_and_expected_cells()
    requests = module._load(module.REQUESTS_PATH)
    context = module._validate_requests(requests)
    full_responses = module._load(module.FULL_RESPONSES_PATH)
    responses_by_id = module._validate_full_responses(full_responses, requests, context)
    transcript = module._transcript_document(
        requests, full_responses, responses_by_id, expected_cells
    )
    mutant_cell = next(
        cell
        for cell in transcript["comparison_cells"]
        if cell["weekly_wage"] == 0 and cell["column"] == "net_benefit"
    )
    assert mutant_cell["declared_rulespec_match"] is True
    assert mutant_cell["classification_match"] is False

    with pytest.raises(ValueError, match="fresh reduced cells differ"):
        module._validate_transcript(
            transcript,
            requests,
            full_responses,
            responses_by_id,
            expected_cells,
            context["roots"],
        )


def test_source_comparison_bytes_are_exactly_pinned(tmp_path, monkeypatch):
    module = _load_script()
    source = module._load(module.SOURCE_REPORT_PATH)
    source["mutant_unreceipted_field"] = True
    source_path = _write(tmp_path / "source-comparison.json", source)
    monkeypatch.setattr(module, "SOURCE_REPORT_PATH", source_path)

    with pytest.raises(ValueError, match="source comparison bytes drifted"):
        module._source_and_expected_cells()


def test_treasury_snapshot_bytes_are_exactly_pinned(tmp_path, monkeypatch):
    module = _load_script()
    snapshot = module._load(module.TREASURY_SNAPSHOT_PATH)
    snapshot["mutant_unreceipted_field"] = True
    snapshot_path = _write(tmp_path / "treasury-snapshot.json", snapshot)
    monkeypatch.setattr(module, "TREASURY_SNAPSHOT_PATH", snapshot_path)

    with pytest.raises(ValueError, match="Treasury snapshot bytes drifted"):
        module._source_and_expected_cells()


def test_rehashed_treasury_value_must_equal_source_comparison(
    tmp_path,
    monkeypatch,
):
    """MUTANT: even a re-pinned snapshot cannot rewrite a declared Treasury cell."""

    module = _load_script()
    mock_root = tmp_path / "repo"
    relative_dir = Path("comparisons/nz-treasury-incomeexplorer")
    (mock_root / relative_dir).mkdir(parents=True)
    snapshot = module._load(module.TREASURY_SNAPSHOT_PATH)
    target_scenario = next(
        row for row in snapshot["scenarios"] if row["id"] == module.SCENARIO_ID
    )
    target_output = next(
        row
        for row in target_scenario["sampled_outputs"]
        if row["gross_wage1"] == 0
    )
    target_output["net_benefit"] = "888888"
    snapshot_path = _write(
        mock_root / relative_dir / "treasury-emtr-snapshot-expanded.json",
        snapshot,
    )
    snapshot_sha = module._sha256(snapshot_path)

    source = module._load(module.SOURCE_REPORT_PATH)
    source["provenance"]["oracle_snapshot"]["sha256"] = snapshot_sha
    source_path = _write(
        mock_root / relative_dir / "source-comparison.json",
        source,
    )
    monkeypatch.setattr(module, "REPO_ROOT", mock_root)
    monkeypatch.setattr(module, "SOURCE_REPORT_PATH", source_path)
    monkeypatch.setattr(module, "SOURCE_REPORT_SHA256", module._sha256(source_path))
    monkeypatch.setattr(module, "TREASURY_SNAPSHOT_PATH", snapshot_path)
    monkeypatch.setattr(module, "TREASURY_SNAPSHOT_SHA256", snapshot_sha)

    with pytest.raises(ValueError, match="source Treasury value differs from snapshot"):
        module._source_and_expected_cells()


@pytest.mark.parametrize(
    ("field", "mutant"),
    [
        ("repository", "MutantFoundation/ops"),
        ("path", "nz-lane/emtr_reproduction/mutant.py"),
        ("repository_commit", "0" * 40),
        ("repository_commit_status", "floating"),
        ("sha256", "0" * 64),
    ],
)
def test_source_comparison_harness_provenance_is_exactly_pinned(
    tmp_path,
    monkeypatch,
    field,
    mutant,
):
    module = _load_script()
    source = module._load(module.SOURCE_REPORT_PATH)
    source["provenance"]["source_comparison_harness"][field] = mutant
    source_path = _write(tmp_path / "source-comparison.json", source)
    monkeypatch.setattr(module, "SOURCE_REPORT_PATH", source_path)
    monkeypatch.setattr(module, "SOURCE_REPORT_SHA256", module._sha256(source_path))

    with pytest.raises(ValueError, match="harness provenance drifted"):
        module._source_and_expected_cells()


def test_ancestor_request_and_cell_counts_cannot_decrease():
    module = _load_script()
    requests = module._load(module.REQUESTS_PATH)
    expected = module._load(module.GOLDEN_PATH)
    prior = {"ancestor": (requests, expected)}

    fewer_requests = copy.deepcopy(requests)
    fewer_requests["requests"].pop()
    with pytest.raises(ValueError, match="request count regressed"):
        module._validate_ancestor_denominators(
            fewer_requests, expected, ancestor_documents=prior
        )

    fewer_cells = copy.deepcopy(expected)
    fewer_cells["comparison_cells"].pop()
    with pytest.raises(ValueError, match="cell count regressed"):
        module._validate_ancestor_denominators(
            requests, fewer_cells, ancestor_documents=prior
        )


def test_ancestor_exact_request_and_cell_key_sets_cannot_be_substituted():
    module = _load_script()
    requests = module._load(module.REQUESTS_PATH)
    expected = module._load(module.GOLDEN_PATH)
    prior = {"ancestor": (requests, expected)}

    request_substitution = copy.deepcopy(requests)
    request_substitution["requests"][0]["id"] = "same-count-mutant"
    with pytest.raises(ValueError, match="exact request key set changed"):
        module._validate_ancestor_denominators(
            request_substitution, expected, ancestor_documents=prior
        )

    cell_substitution = copy.deepcopy(expected)
    cell_substitution["comparison_cells"][0]["column"] = "same_count_mutant"
    with pytest.raises(ValueError, match="exact comparison key set changed"):
        module._validate_ancestor_denominators(
            requests, cell_substitution, ancestor_documents=prior
        )


def test_unavailable_origin_main_denominator_check_fails_open_loudly(
    monkeypatch,
    capsys,
):
    module = _load_script()
    real_git_history = module._git_history

    def without_origin_main(*args):
        if args and args[0] == "merge-base":
            return SimpleNamespace(
                returncode=128,
                stdout="",
                stderr="fatal: Not a valid object name origin/main",
            )
        return real_git_history(*args)

    monkeypatch.setattr(module, "_git_history", without_origin_main)
    revisions = module._history_revisions()

    assert revisions
    note = capsys.readouterr().err
    assert "NZ executable NOTE:" in note
    assert "origin/main" in note
    assert "failed open" in note


@pytest.mark.parametrize(
    ("denominator", "marker"),
    [
        ("requests", "request count regressed"),
        ("cells", "cell count regressed"),
    ],
)
def test_synthetic_pr_merge_cannot_hide_a_committed_denominator_deletion(
    tmp_path,
    monkeypatch,
    denominator,
    marker,
):
    """MUTANT: GitHub's synthetic merge layer cannot hide the prior floor."""

    module = _load_script()
    baseline_requests = module._load(module.REQUESTS_PATH)
    baseline_cells = module._load(module.GOLDEN_PATH)
    mutant_requests = copy.deepcopy(baseline_requests)
    mutant_cells = copy.deepcopy(baseline_cells)
    if denominator == "requests":
        mutant_requests["requests"].pop()
    else:
        mutant_cells["comparison_cells"].pop()

    repo = tmp_path / "synthetic-pr-merge"
    repo.mkdir()

    def git(*args):
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )

    git("init", "-q", "-b", "main")
    git("config", "user.name", "NZ executable mutant")
    git("config", "user.email", "nz-executable-mutant@example.invalid")
    (repo / "base.txt").write_text("base\n")
    git("add", "base.txt")
    git("commit", "-q", "-m", "base without NZ executable denominators")

    git("checkout", "-q", "-b", "feature")
    request_path = repo / module.REQUESTS_PATH.relative_to(module.REPO_ROOT)
    golden_path = repo / module.GOLDEN_PATH.relative_to(module.REPO_ROOT)
    request_path.parent.mkdir(parents=True)
    _write(request_path, baseline_requests)
    _write(golden_path, baseline_cells)
    git("add", str(request_path.relative_to(repo)), str(golden_path.relative_to(repo)))
    git("commit", "-q", "-m", "commit full denominator")

    _write(request_path, mutant_requests)
    _write(golden_path, mutant_cells)
    git("add", str(request_path.relative_to(repo)), str(golden_path.relative_to(repo)))
    git("commit", "-q", "-m", f"mutant deletes one {denominator} denominator")

    git("checkout", "-q", "main")
    (repo / "main.txt").write_text("main moved\n")
    git("add", "main.txt")
    git("commit", "-q", "-m", "main moved")
    git("update-ref", "refs/remotes/origin/main", "HEAD")
    git("merge", "-q", "--no-ff", "feature", "-m", "synthetic pull request merge")

    monkeypatch.setattr(module, "REPO_ROOT", repo)
    monkeypatch.setattr(module, "REQUESTS_PATH", request_path)
    monkeypatch.setattr(module, "GOLDEN_PATH", golden_path)

    with pytest.raises(ValueError, match=marker):
        module._validate_ancestor_denominators(mutant_requests, mutant_cells)


def test_refresh_receipt_reconstructs_a_corrupted_outer_receipt(tmp_path, monkeypatch):
    module = _load_script()
    corrupted = module._load(module.RECEIPT_PATH)
    corrupted["transcript"]["sha256"] = "0" * 64
    receipt_path = _write(tmp_path / "receipt.json", corrupted)
    monkeypatch.setattr(module, "RECEIPT_PATH", receipt_path)

    assert module.main(["--refresh-receipt"]) == 0
    restored = module._load(receipt_path)
    summary = module.validate_artifact(restored)
    assert restored == module._receipt_document(summary)


def test_check_mode_cannot_repair_a_corrupted_receipt(tmp_path, monkeypatch, capsys):
    """MUTANT: --check must stay read-only even when paired with refresh."""

    module = _load_script()
    corrupted = module._load(module.RECEIPT_PATH)
    corrupted["transcript"]["sha256"] = "0" * 64
    receipt_path = _write(tmp_path / "receipt.json", corrupted)
    before = receipt_path.read_bytes()
    monkeypatch.setattr(module, "RECEIPT_PATH", receipt_path)

    assert module.main(["--check", "--refresh-receipt"]) == 1
    assert receipt_path.read_bytes() == before
    assert "--check is read-only" in capsys.readouterr().err
