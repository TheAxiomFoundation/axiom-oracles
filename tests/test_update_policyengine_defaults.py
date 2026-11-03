"""Release selection and evidence admission are independent of a network run."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "updater", ROOT / "scripts/update_policyengine_defaults.py"
)
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)

BASELINE = {
    "policyengine": "4.18.9",
    "policyengine-us": "1.752.2",
    "policyengine-core": "3.28.0",
    "spm-calculator": "0.3.1",
}
CANDIDATE = {
    "policyengine": "6.12.0",
    "policyengine-us": "2.91.12",
    "policyengine-core": "3.34.2",
    "spm-calculator": "1.0.0.post1",
}


def wheel(*, yanked=False, python=">=3.11", kind="bdist_wheel", sha="1" * 64):
    return {
        "yanked": yanked,
        "requires_python": python,
        "packagetype": kind,
        "digests": {"sha256": sha},
    }


def lock(packages=CANDIDATE):
    return "".join(
        f"{name}=={version} \\\n    --hash=sha256:{'1' * 64}\n"
        for name, version in packages.items()
    )


def result(packages):
    fixtures = json.loads(updater.FIXTURES.read_text())
    return {
        "packages": packages,
        "case_count": len(fixtures["cases"]),
        "comparison_count": len(fixtures["cases"]) * len(fixtures["variables"]),
        "batch_count": (len(fixtures["cases"]) + 1) // 2,
        "cases": [
            {
                "case_id": case["id"],
                "outputs": {variable: 42 for variable in fixtures["variables"]},
            }
            for case in fixtures["cases"]
        ],
        "errors": [],
    }


def proposal():
    return {
        "schema": 1,
        "base_commit": "a" * 40,
        "baseline": {"schema": 1, "packages": BASELINE},
        "candidate": {"schema": 1, "packages": CANDIDATE},
        "status": "passed",
        "latest_model": "2.91.12",
        "fixture_sha256": hashlib.sha256(updater.FIXTURES.read_bytes()).hexdigest(),
        "candidate_lock_sha256": hashlib.sha256(lock().encode()).hexdigest(),
        "changes": [],
        "baseline_result": result(BASELINE),
        "candidate_result": result(CANDIDATE),
        "limitations": ["bounded probe"],
        "errors": [],
    }


def test_latest_is_version_ordered_not_lexically_ordered_or_project_info():
    project = {
        "info": {"version": "99.0rc1"},
        "releases": {
            "2.9.0": [wheel()],
            "2.10.0": [wheel()],
            "99.0rc1": [wheel()],
            "100.0.dev1": [wheel()],
            "invalid": [wheel()],
            "100+local": [wheel()],
        },
    }
    assert updater.latest_stable_release(project) == "2.10.0"


def test_latest_skips_yanked_missing_sdist_only_and_incompatible_releases():
    project = {
        "releases": {
            "2.8": [wheel()],
            "2.9": [wheel(yanked=True)],
            "2.10": [],
            "2.11": [wheel(kind="sdist")],
            "2.12": [wheel(python=">=3.15")],
        }
    }
    assert updater.latest_stable_release(project) == "2.8"


def test_yanking_is_per_file_and_a_usable_non_yanked_wheel_remains_eligible():
    assert (
        updater.latest_stable_release(
            {"releases": {"2.1": [wheel(yanked=True), wheel()]}}
        )
        == "2.1"
    )


def test_stable_post_release_is_eligible_but_missing_yanked_metadata_is_not():
    missing_flag = wheel()
    missing_flag.pop("yanked")
    assert (
        updater.latest_stable_release(
            {
                "releases": {
                    "2.1": [wheel()],
                    "2.1.post1": [wheel()],
                    "3.0": [missing_flag],
                }
            }
        )
        == "2.1.post1"
    )


def test_no_release_fails_instead_of_silently_falling_back():
    with pytest.raises(ValueError, match="no final"):
        updater.latest_stable_release(
            {"releases": {"3.0rc1": [wheel()], "2.0": [wheel(yanked=True)]}}
        )


def test_lock_filter_removes_yanked_hash_even_when_another_file_is_usable():
    text = (
        "demo==1.0 \\\n    --hash=sha256:"
        + "1" * 64
        + " \\\n    --hash=sha256:"
        + "2" * 64
        + "\n"
    )
    filtered = updater.non_yanked_lock(
        text, lambda *_: {"urls": [wheel(), wheel(yanked=True, sha="2" * 64)]}
    )
    assert "1" * 64 in filtered
    assert "2" * 64 not in filtered
    assert updater.locked_versions(filtered) == {"demo": "1.0"}


def test_lock_filter_requires_the_resolved_hash_not_any_non_yanked_file():
    with pytest.raises(ValueError, match="no resolved non-yanked"):
        updater.non_yanked_lock(
            "demo==1.0 --hash=sha256:" + "1" * 64,
            lambda *_: {"urls": [wheel(sha="2" * 64)]},
        )


@pytest.mark.parametrize(
    "text",
    [
        "demo>=1.0 --hash=sha256:" + "1" * 64,
        "demo==1.0",
        "--index-url https://example.test",
        "-e /tmp/code",
        "demo @ https://example.test/x.whl --hash=sha256:" + "1" * 64,
        "demo==1.0rc1 --hash=sha256:" + "1" * 64,
        "demo==1.0 --trusted-host example.test --hash=sha256:" + "1" * 64,
    ],
)
def test_lock_refuses_executable_install_configuration_and_unfrozen_versions(text):
    with pytest.raises(ValueError):
        updater.locked_versions(text)


def test_candidate_lock_must_match_all_four_versions():
    updater.validate_candidate_lock(lock(), CANDIDATE)
    with pytest.raises(ValueError, match="does not match"):
        updater.validate_candidate_lock(lock(BASELINE), CANDIDATE)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.update(extra="unexpected"),
        lambda p: p.update(base_commit="main"),
        lambda p: p.update(latest_model="2.92.0"),
        lambda p: p["candidate_result"].update(comparison_count=0),
        lambda p: p["candidate_result"].update(packages=BASELINE),
        lambda p: p["candidate_result"].update(errors=["import failed"]),
        lambda p: p.update(candidate_lock_sha256="not-a-hash"),
        lambda p: p["candidate_result"].update(cases=[]),
        lambda p: p["candidate_result"]["cases"][0]["outputs"].pop("snap"),
        lambda p: p.update(fixture_sha256="b" * 64),
    ],
)
def test_success_cannot_hide_missing_or_wrong_runtime_evidence(mutation):
    payload = copy.deepcopy(proposal())
    mutation(payload)
    with pytest.raises(ValueError):
        updater.validate_proposal(payload)


def test_changed_output_arithmetic_is_checked():
    payload = proposal()
    payload["status"] = "needs-review"
    payload["candidate_result"]["cases"][0]["outputs"]["income_tax"] = 45
    payload["changes"] = [
        {
            "case_id": payload["candidate_result"]["cases"][0]["case_id"],
            "variable": "income_tax",
            "before": 42,
            "after": 45,
            "difference": 3,
        }
    ]
    updater.validate_proposal(payload)
    payload["changes"][0]["difference"] = 4
    with pytest.raises(ValueError, match="reconcile"):
        updater.validate_proposal(payload)


def test_numerical_changes_keep_zero_and_false_and_do_not_invent_missing_values():
    before = {"cases": [{"case_id": "one", "outputs": {"tax": 0, "eligible": False}}]}
    after = {"cases": [{"case_id": "one", "outputs": {"tax": 10, "eligible": True}}]}
    rows = updater.numerical_changes(before, after)
    assert [(r["variable"], r["difference"]) for r in rows] == [
        ("eligible", 1),
        ("tax", 10),
    ]


def test_no_update_does_not_resolve_install_or_change_files(monkeypatch, tmp_path):
    monkeypatch.setattr(updater, "load_defaults", lambda: CANDIDATE)
    monkeypatch.setattr(
        updater, "pypi_project", lambda name: {"releases": {"2.91.12": [wheel()]}}
    )
    monkeypatch.setattr(
        updater,
        "resolve_lock",
        lambda *_: pytest.fail("no install for unchanged model"),
    )
    # This unit test isolates the orchestration from dirty source under development.
    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda *a, **kw: type("Result", (), {"returncode": 0})(),
    )
    monkeypatch.setattr(updater.subprocess, "check_output", lambda *a, **kw: "a" * 40)
    payload = updater.probe(tmp_path / "proposal")
    assert payload["status"] == "no-update"
    assert payload["candidate"] is None
    assert not (tmp_path / "proposal/candidate-requirements.txt").exists()
    assert json.loads((tmp_path / "proposal/proposal.json").read_text()) == payload


def test_future_baseline_reuses_the_reviewed_lock_instead_of_resolving_again(
    monkeypatch, tmp_path
):
    reviewed = tmp_path / "reviewed.txt"
    reviewed.write_text(lock(BASELINE))
    monkeypatch.setattr(updater, "DEFAULT_REQUIREMENTS_PATH", reviewed)
    monkeypatch.setattr(
        updater,
        "resolve_lock",
        lambda *_: pytest.fail("reviewed lock must not be resolved again"),
    )
    assert updater.baseline_lock("uv", BASELINE, tmp_path, {}) == reviewed


def test_worker_outputs_do_not_hide_a_nonzero_process_exit(monkeypatch, tmp_path):
    monkeypatch.setattr(updater, "_run", lambda *a, **kw: None)

    def crashed_worker(cmd, **kwargs):
        Path(cmd[cmd.index("--output") + 1]).write_text(json.dumps(result(BASELINE)))
        return type(
            "Process", (), {"returncode": -11, "stderr": "native finalizer crashed"}
        )()

    monkeypatch.setattr(updater.subprocess, "run", crashed_worker)
    evidence = updater.execute_probe(
        "uv", tmp_path / "lock.txt", BASELINE, tmp_path / "probe", {}
    )
    assert evidence["comparison_count"] == 16
    assert any("exited -11" in error for error in evidence["errors"])


def test_a_broken_real_batch_cannot_pass_by_falling_back_to_singletons(monkeypatch):
    from axiom_oracles.adapters.policyengine import runner as adapter
    from axiom_oracles.core.results import EngineResult
    from scripts import probe_policyengine_update as worker

    class BrokenBatch:
        def __init__(self, **kwargs):
            pass

        def run_household(self, household, variables):
            return EngineResult(
                "policyengine", household.household_id, dict.fromkeys(variables, 42)
            )

        def run_case(self, case, variables):
            return EngineResult(
                "policyengine", case.case_id, dict.fromkeys(variables, 42)
            )

        def run_cases(self, cases, variables):
            return [self.run_case(case, variables) for case in cases]

        def _run_case_batch_once(self, cases, variables):
            raise ValueError("candidate batch API is broken")

    monkeypatch.setattr(adapter, "PolicyEngineRunner", BrokenBatch)
    monkeypatch.setattr(worker, "version", BASELINE.__getitem__)
    monkeypatch.setattr(
        worker.runpy, "run_path", lambda _: {"_PE_RUNTIME_BOOTSTRAP": ""}
    )
    with pytest.raises(ValueError, match="batch API is broken"):
        worker.run_probe(json.loads(updater.FIXTURES.read_text()), BASELINE)
