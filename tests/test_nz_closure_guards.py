"""Focused mutants for NZ closure trace independence and monotone floors."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_closure():
    path = REPO_ROOT / "scripts" / "nz_closure.py"
    spec = importlib.util.spec_from_file_location("nz_closure_guards", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "field", ["release_content_sha256", "release_selector_sha256"],
)
def test_check_rejects_wrong_named_release_hash(field, tmp_path, monkeypatch, capsys):
    """MUTANT: a reviewed snapshot cannot substitute another release identity."""

    closure = _load_closure()
    source = closure.load_source()
    source["corpus"][field] = "0" * 64
    mutant = tmp_path / "source.json"
    mutant.write_text(closure._render(source))
    # Re-reviewing snapshot bytes must not bypass the independent release pins.
    monkeypatch.setattr(closure, "SOURCE_PATH", mutant)
    monkeypatch.setattr(closure, "SOURCE_SHA256", hashlib.sha256(mutant.read_bytes()).hexdigest())
    monkeypatch.setattr("sys.argv", ["nz_closure.py", "--check"])

    assert closure.main() == 1
    assert "corpus release pin drifted" in capsys.readouterr().err
    # Control: with the committed snapshot back in place and the pin restored,
    # the release builds again.
    monkeypatch.undo()
    source["corpus"][field] = getattr(closure, field.upper())
    assert closure.build(source)["corpus_release"] == closure.RELEASE


def test_check_rejects_corpus_file_bytes_then_accepts_restored_pin(
    tmp_path, monkeypatch, capsys,
):
    """MUTANT: live --check hashes corpus bytes before reading citation paths."""

    closure = _load_closure()
    relative = "data/corpus/provisions/nz/statute/test-scope.jsonl"
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    original = b'{"citation_path":"nz/statute/mutant-control"}\n'
    expected_sha = hashlib.sha256(original).hexdigest()
    source = closure.load_source()
    selector = tmp_path / closure.RELEASE_SELECTOR_PATH
    selector.parent.mkdir(parents=True)
    selector.write_text(json.dumps({
        "name": closure.RELEASE,
        "scopes": [{"jurisdiction": "nz", "document_class": "statute", "version": "test-scope"}],
    }))
    monkeypatch.setattr(closure, "RELEASE_SELECTOR_SHA256", hashlib.sha256(selector.read_bytes()).hexdigest())
    monkeypatch.setattr(closure, "EXPECTED_PROVISION_SOURCES", {relative: (expected_sha, 1)})

    def local_release_git(_repo, *args):
        if args == ("rev-parse", closure.CORPUS_COMMIT):
            return closure.CORPUS_COMMIT
        if args[0] == "diff":
            return ""
        assert args == ("show", f"{closure.CORPUS_COMMIT}:.axiom/corpus-locks/nz/statute/test-scope.json")
        return json.dumps({"files": [{"path": relative, "sha256": expected_sha}]})

    monkeypatch.setattr(closure, "_git", local_release_git)
    path.write_bytes(original)
    assert closure._load_corpus_files(tmp_path) == {relative: original}
    selector.write_text(selector.read_text() + " ")
    with pytest.raises(closure.ClosureError, match="selector sha256 drifted"):
        closure._load_corpus_files(tmp_path)
    selector.write_text(selector.read_text().removesuffix(" "))
    path.write_bytes(original + b" ")
    monkeypatch.setattr("sys.argv", ["nz_closure.py", "--check", "--corpus-repo", str(tmp_path)])
    assert closure.main() == 1
    assert "file bytes do not match their pin" in capsys.readouterr().err

    path.write_bytes(original)
    assert closure._load_corpus_files(tmp_path) == {relative: original}
    # Restore the actual source's derived citation set to complete the CLI
    # control without materializing an entire corpus in the test directory.
    monkeypatch.setattr(closure, "_corpus_citation_paths", lambda _files: source["corpus"]["citation_paths"])
    # The live file-reader fixture has synthetic pins; the hermetic build still
    # checks the real source's committed per-file pins.
    monkeypatch.setattr(closure, "RELEASE_SELECTOR_SHA256", source["corpus"]["release_selector_sha256"])
    monkeypatch.setattr(closure, "_load_corpus_files", lambda _repo: {relative: original})
    monkeypatch.setattr(closure, "_provision_source_pins", lambda: source["corpus"]["provision_sources"])
    assert closure.main() == 0


def test_hermetic_check_rejects_changed_provision_file_pin():
    closure = _load_closure()
    source = closure.load_source()
    source["corpus"]["provision_sources"][0]["sha256"] = "0" * 64
    with pytest.raises(closure.ClosureError, match="provision source pins drifted"):
        closure.build(source)


def test_different_content_pins_start_a_new_ancestor_baseline(monkeypatch):
    closure = _load_closure()
    document = json.loads(closure.RATCHET_PATH.read_text())
    document["content_pins"]["rulespec_commit"] = "0" * 40
    monkeypatch.setattr(
        closure, "_git_history",
        lambda *_args: SimpleNamespace(returncode=0, stdout=json.dumps(document), stderr=""),
    )
    assert closure._ratchet_at_revision("previous-baseline", label="previous baseline", unavailable_is_note=False) is None


def test_executable_request_root_absent_from_execution_trace_is_rejected():
    """MUTANT: asserted request evidence cannot mint an unexecuted root."""

    closure = _load_closure()
    trace = json.loads(closure.EVALUATION_TRACE_PATH.read_text())
    evidence = json.loads(closure.REQUEST_TRACE_PATH.read_text())
    mutant = copy.deepcopy(evidence["requests"][0])
    mutant["id"] = "mutant-unexecuted-root"
    mutant["request"]["queries"][0]["outputs"].append(
        "nz:statutes/mutant#output_absent_from_execution_trace"
    )
    evidence["requests"].append(mutant)

    with pytest.raises(
        closure.ClosureError,
        match="request/root is absent from the committed evaluation trace",
    ):
        closure.load_requested_output_roots(
            trace=trace,
            request_evidence=evidence,
        )


def test_trace_ownership_is_not_derived_from_program_views(monkeypatch):
    """The execution row's view remains authoritative on the evidence side."""

    closure = _load_closure()
    expected = closure.load_requested_output_roots()
    declarations = copy.deepcopy(closure.PROGRAM_VIEWS)
    declarations["nz/main-benefits"] = {
        **declarations["nz/main-benefits"],
        "roots": ("nz:mutant/declaration#root",),
    }
    monkeypatch.setattr(closure, "PROGRAM_VIEWS", declarations)

    assert closure.load_requested_output_roots() == expected
    with pytest.raises(closure.ClosureError, match="not bijective"):
        closure.build(
            closure.load_source(),
            denominator_ratchet=json.loads(closure.RATCHET_PATH.read_text())[
                "programs"
            ],
            ancestor_denominator_ratchets={},
        )


def test_unavailable_origin_main_floor_check_fails_open_loudly(
    monkeypatch,
    capsys,
):
    closure = _load_closure()
    real_git_history = closure._git_history

    def without_origin_main(*args):
        if args and args[0] == "show":
            # Supply a same-baseline ancestor even while this repin is still
            # uncommitted and real HEAD belongs to the preceding baseline.
            return SimpleNamespace(
                returncode=0,
                stdout=closure.RATCHET_PATH.read_text(),
                stderr="",
            )
        if args and args[0] == "merge-base":
            return SimpleNamespace(
                returncode=128,
                stdout="",
                stderr="fatal: Not a valid object name origin/main",
            )
        return real_git_history(*args)

    monkeypatch.setattr(closure, "_git_history", without_origin_main)
    ancestors = closure._load_ancestor_denominator_ratchets()

    assert ancestors
    note = capsys.readouterr().err
    assert "NZ closure NOTE:" in note
    assert "origin/main" in note
    assert "failed open" in note


def test_synthetic_merge_cannot_hide_an_older_higher_floor(monkeypatch):
    """MUTANT: a PR-tip lowering cannot hide behind GitHub's merge commit."""

    closure = _load_closure()
    lower = json.loads(closure.RATCHET_PATH.read_text())
    higher = copy.deepcopy(lower)
    program = "nz/working-for-families"
    field = "requested_output_count_min"
    higher["programs"][program][field] += 1
    walked_history = False

    def synthetic_merge_history(*args):
        nonlocal walked_history
        if args == (
            "rev-list",
            "--full-history",
            "HEAD",
            "--",
            closure.RATCHET_REPO_PATH,
        ):
            walked_history = True
            return SimpleNamespace(
                returncode=0,
                stdout="synthetic-merge\npr-tip\nolder-higher-floor\n",
                stderr="",
            )
        if args == ("merge-base", "HEAD", "origin/main"):
            return SimpleNamespace(returncode=0, stdout="base\n", stderr="")
        if args and args[0] == "show":
            revision = args[1].split(":", 1)[0]
            if revision in {"HEAD", "synthetic-merge", "pr-tip"}:
                return SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps(lower),
                    stderr="",
                )
            if revision == "older-higher-floor":
                return SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps(higher),
                    stderr="",
                )
            if revision == "base":
                return SimpleNamespace(returncode=128, stdout="", stderr="path absent")
        raise AssertionError(f"unexpected git invocation: {args!r}")

    monkeypatch.setattr(closure, "_git_history", synthetic_merge_history)
    ancestors = closure._load_ancestor_denominator_ratchets()

    assert walked_history is True
    with pytest.raises(
        closure.ClosureError,
        match=rf"lowered {field} from {higher['programs'][program][field]}",
    ):
        closure._validate_ancestor_monotonicity(lower["programs"], ancestors=ancestors)


@pytest.mark.parametrize(
    "field",
    ["requested_output_count_min", "citation_count_min"],
)
def test_lowering_a_floor_below_its_ancestor_is_rejected_with_counts_untouched(
    field,
):
    """MUTANT: changing only a committed floor must fail monotonically."""

    closure = _load_closure()
    source = closure.load_source()
    roots = closure.load_requested_output_roots()
    ancestor = json.loads(closure.RATCHET_PATH.read_text())["programs"]
    current = copy.deepcopy(ancestor)
    program = "nz/working-for-families"
    current[program][field] -= 1

    # The observed root/citation denominators are untouched and still exceed
    # the mutant floor; ancestor comparison is the only guard that can bite.
    assert len(roots[program]) >= ancestor[program]["requested_output_count_min"]
    with pytest.raises(
        closure.ClosureError,
        match=rf"ancestor-monotone denominator RATCHET lowered {field}",
    ):
        closure.build(
            source,
            requested_output_roots=roots,
            denominator_ratchet=current,
            ancestor_denominator_ratchets={"test ancestor": ancestor},
        )


def test_committed_floor_only_decrement_fails_through_real_git_history(
    tmp_path,
    monkeypatch,
):
    """MUTANT: a committed floor-only regression reds the normal history gate."""

    closure = _load_closure()
    baseline = json.loads(closure.RATCHET_PATH.read_text())
    mutant = copy.deepcopy(baseline)
    program = "nz/working-for-families"
    field = "citation_count_min"
    mutant["programs"][program][field] -= 1

    # The mutation changes one floor byte only. The observed closure source,
    # trace-derived roots, and therefore all root/citation counts stay outside
    # this temporary repository and are deliberately untouched.
    restored = copy.deepcopy(mutant)
    restored["programs"][program][field] += 1
    assert restored == baseline

    repo = tmp_path / "committed-floor-mutant"
    ratchet_path = repo / closure.RATCHET_REPO_PATH
    ratchet_path.parent.mkdir(parents=True)

    def git(*args):
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )

    git("init", "-q", "-b", "main")
    git("config", "user.name", "NZ closure mutant")
    git("config", "user.email", "nz-closure-mutant@example.invalid")
    ratchet_path.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n")
    git("add", closure.RATCHET_REPO_PATH)
    git("commit", "-q", "-m", "commit closure floors")
    git("update-ref", "refs/remotes/origin/main", "HEAD")

    ratchet_path.write_text(json.dumps(mutant, indent=2, sort_keys=True) + "\n")
    git("add", closure.RATCHET_REPO_PATH)
    git("commit", "-q", "-m", "mutant lowers one floor only")

    monkeypatch.setattr(closure, "REPO_ROOT", repo)
    monkeypatch.setattr(closure, "RATCHET_PATH", ratchet_path)

    with pytest.raises(
        closure.ClosureError,
        match=rf"ancestor-monotone denominator RATCHET lowered {field}",
    ):
        closure.load_denominator_ratchet()
