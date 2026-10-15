"""Source/data merge regressions, including the real round-2 rollout wedge."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace

from hypothesis import HealthCheck, Phase, given, settings, strategies as st
import pytest

from test_oracle_data import (
    advance_main,
    commit,
    data,
    git,
    repo as repo,
    seed_data,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "dashboard/public/data/manifest.json"
OVERVIEW = "dashboard/public/data/overview.json"
# Cover each aggregate family, including both served and canonical copies.
AGGREGATES = (
    OVERVIEW,
    "dashboard/public/data/freshness.json",
    "dashboard/public/data/conformance_scoreboard.json",
    "dashboard/public/data/conformance_detail_de.json",
    "dashboard/public/data/conformance_burndown.json",
    "conformance/scoreboard.json",
    "conformance/detail/de.json",
    "conformance/history/de/2026-10-14.json",
    "conformance/exercise-census.json",
    "conformance/de-certificate-census.json",
    "certificates/de-kindergeld.json",
    "comparisons/affected_map.json",
)
OPERATIONS = ("prepare", "materialize", "materialize-baseline")


def _operate(checkout: Path, operation: str) -> None:
    if operation == "prepare":
        data.prepare(checkout)
    else:
        data.materialize(checkout, baseline=operation == "materialize-baseline")


@pytest.mark.parametrize("operation", OPERATIONS)
def test_conflicting_one_line_aggregates_use_the_snapshot_side(repo, operation):
    """Rewritten aggregates never wedge publication or either reader mode."""
    repo.main = advance_main(repo, {path: '{"value":"base"}\n' for path in AGGREGATES})
    git(repo.checkout, "fetch", "origin", data.MAIN_REF)
    git(repo.checkout, "reset", "--hard", "FETCH_HEAD")
    seed_data(repo, {path: '{"value":"published"}\n' for path in AGGREGATES})
    main = advance_main(repo, {path: '{"value":"reviewed"}\n' for path in AGGREGATES})
    git(repo.checkout, "fetch", "origin", data.MAIN_REF)
    git(repo.checkout, "reset", "--hard", "FETCH_HEAD")

    _operate(repo.checkout, operation)

    expected = "reviewed" if operation == "prepare" else "published"
    for path in AGGREGATES:
        assert json.loads((repo.checkout / path).read_text()) == {"value": expected}
    assert git(repo.origin, "rev-parse", data.MAIN_REF) == main


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("report", [
    "dashboard/public/data/report.json",
    "conformance/detail/authored/inputs.json",
    "certificates/review/record.json",
])
def test_conflicting_primary_report_names_documented_recovery(repo, operation, report):
    """A reviewed report correction cannot be resolved as a disposable aggregate."""
    seed_data(repo, {report: '{"value":"published correction"}\n'})
    main = advance_main(repo, {report: '{"value":"reviewed correction"}\n'})
    git(repo.checkout, "fetch", "origin", data.MAIN_REF)
    git(repo.checkout, "reset", "--hard", "FETCH_HEAD")
    index = git(repo.checkout, "write-tree")

    with pytest.raises(data.DataError) as error:
        _operate(repo.checkout, operation)

    assert report in str(error.value)
    assert "comparisons/README.md" in str(error.value), "name the documented report-conflict recovery"
    assert git(repo.checkout, "rev-parse", "HEAD") == main
    assert git(repo.checkout, "write-tree") == index
    assert json.loads((repo.checkout / report).read_text())["value"] == "reviewed correction"


def _manifest_case(root: Path, main_reports: list[str], published_reports: list[str]):
    seed, origin, checkout = (root / name for name in ("seed", "origin.git", "checkout"))
    seed.mkdir()
    git(seed, "init", "--initial-branch=main")
    baseline = commit(seed, {MANIFEST: json.dumps({"reports": ["common.json"]}) + "\n"})
    git(root, "init", "--bare", str(origin))
    git(seed, "remote", "add", "origin", str(origin))
    git(seed, "push", "origin", "HEAD:refs/heads/main")
    case = SimpleNamespace(seed=seed, origin=origin, checkout=checkout, main=baseline)
    seed_data(case, {MANIFEST: json.dumps({"reports": published_reports}) + "\n"})
    advance_main(case, {MANIFEST: json.dumps({"reports": main_reports}) + "\n"})
    git(root, "clone", "--branch", "main", str(origin), str(checkout))
    return case


@pytest.mark.parametrize("operation", OPERATIONS)
@settings(
    max_examples=6,
    deadline=None,
    phases=[Phase.generate],
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    main_ids=st.lists(st.integers(min_value=0, max_value=5), min_size=1, max_size=3, unique=True),
    published_ids=st.lists(st.integers(min_value=0, max_value=5), min_size=1, max_size=3, unique=True),
)
def test_manifest_conflict_is_an_append_only_union(tmp_path, monkeypatch, operation, main_ids, published_ids):
    """No manifest addition is lost, regardless of the preferred aggregate side."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    monkeypatch.delenv("AXIOM_ORACLES_DATA_SOURCE", raising=False)
    main_reports = ["common.json", *(f"reviewed-{i}.json" for i in main_ids)]
    published_reports = ["common.json", *(f"published-{i}.json" for i in published_ids)]
    with tempfile.TemporaryDirectory(dir=tmp_path) as directory:
        case = _manifest_case(Path(directory), main_reports, published_reports)

        _operate(case.checkout, operation)

        reports = json.loads((case.checkout / MANIFEST).read_text())["reports"]
        assert set(reports) == set(main_reports) | set(published_reports)
        assert len(reports) == len(set(reports))


def _overview(root: Path, *, check: bool = False) -> None:
    result = subprocess.run(
        [sys.executable, "scripts/generate_dashboard_overview.py", *(["--check"] if check else [])],
        cwd=root, text=True, capture_output=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_real_rollout_refresh_survives_an_ordinary_add_suite_pr(tmp_path, monkeypatch):
    """Rebuild the reviewer's cd2ccfc68/fa43e7560 wedge with actual report bytes.

    Git alternates share the existing objects, and one sparse checkout is
    reused by both readers and the publisher. This copies no full corpus.
    """
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    monkeypatch.delenv("AXIOM_ORACLES_DATA_SOURCE", raising=False)
    rollout = "cd2ccfc68f3358ec9c3380875da1501535044e74"
    refresh = "fa43e75600799677ec73289b7dcae221390025ae"
    for ref in (rollout, refresh):
        if not git(ROOT, "rev-parse", "--verify", ref, check=False):
            pytest.skip("historical rollout objects are unavailable in this shallow checkout")
    assert git(ROOT, "rev-parse", f"{refresh}^1") == rollout
    common = git(ROOT, "rev-parse", "--path-format=absolute", "--git-common-dir")
    checkout, origin = tmp_path / "checkout", tmp_path / "origin.git"
    git(tmp_path, "clone", "--shared", "--no-checkout", common, str(checkout))
    git(checkout, "sparse-checkout", "set", "--no-cone", "/scripts/", *(f"/{path}" for path in data.DATA_PATHS))
    git(checkout, "checkout", "--detach", rollout)
    original = "axiom-policyengine-ca-snap-ecps.json"
    added = "axiom-policyengine-zz-new-suite.json"
    shutil.copy2(checkout / "dashboard/public/data" / original, checkout / "dashboard/public/data" / added)
    manifest = json.loads((checkout / MANIFEST).read_text())
    manifest["reports"].append(added)
    (checkout / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n")
    _overview(checkout)
    _overview(checkout, check=True)
    main = commit(checkout, {})
    reviewed_overview = (checkout / OVERVIEW).read_bytes()
    published_overview = subprocess.run(
        ["git", "show", f"{refresh}:{OVERVIEW}"], cwd=ROOT, capture_output=True, check=True,
    ).stdout
    assert reviewed_overview != published_overview
    git(tmp_path, "init", "--bare", str(origin))
    (origin / "objects/info/alternates").write_text(f"{common}/objects\n")
    git(checkout, "remote", "set-url", "origin", str(origin))
    git(checkout, "push", "origin", f"{main}:{data.MAIN_REF}", f"{refresh}:{data.DATA_REF}")

    # The exact refresh is clean until the ordinary reviewed PR lands.
    refresh_tree = git(checkout, "rev-parse", f"{refresh}^{{tree}}")
    assert data._merge_tree(checkout, rollout, refresh) == refresh_tree
    assert data._reader_merge_tree(checkout, rollout, refresh) == refresh_tree

    for baseline in (False, True):
        git(checkout, "reset", "--hard", main)
        data.materialize(checkout, baseline=baseline)
        assert (checkout / OVERVIEW).read_bytes() == published_overview
        overview = json.loads(published_overview)
        for name, digest in overview["sources"].items():
            assert hashlib.sha256((checkout / "dashboard/public/data" / name).read_bytes()).hexdigest() == digest

    data.prepare(checkout)
    assert (checkout / OVERVIEW).read_bytes() == reviewed_overview
    _overview(checkout)
    _overview(checkout, check=True)
    regenerated = json.loads((checkout / OVERVIEW).read_text())
    assert added in regenerated["sources"]
    assert regenerated["sources"] != json.loads(reviewed_overview)["sources"]
    assert git(origin, "rev-parse", data.MAIN_REF) == main
