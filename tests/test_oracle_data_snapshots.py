"""Real-corpus regressions for publication and reader snapshot consistency.

The fixture uses real report bytes from the reviewed rollout and refresh
commits, the production aggregation script, current publication entry points,
and a local bare origin. It never contacts a network remote
or substitutes a synthetic report for the historical repository data.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_oracle_data import commit, data, git

ROOT = Path(__file__).resolve().parents[1]
ROLLOUT = "cd2ccfc68f3358ec9c3380875da1501535044e74"
REFRESH = "fa43e75600799677ec73289b7dcae221390025ae"
MANIFEST = "dashboard/public/data/manifest.json"
OVERVIEW = "dashboard/public/data/overview.json"
REVIEWED_REPORT = "dashboard/public/data/axiom-euromod-be-article-51-forfait.json"
ADDED_REPORT = "dashboard/public/data/review-added-ordinary-suite.json"


def overview(root: Path, *, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            "scripts/generate_dashboard_overview.py",
            *(["--check"] if check else []),
        ],
        cwd=root,
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )


def regenerate_overview(root: Path) -> None:
    result = overview(root)
    assert result.returncode == 0, result.stdout + result.stderr
    assert_consistent(root)


def assert_consistent(root: Path) -> None:
    bundle = json.loads((root / OVERVIEW).read_bytes())
    reports = json.loads((root / MANIFEST).read_bytes())["reports"]
    assert set(bundle["sources"]) == {
        name for name in reports if (root / "dashboard/public/data" / name).exists()
    }
    for name, digest in bundle["sources"].items():
        assert (
            hashlib.sha256(
                (root / "dashboard/public/data" / name).read_bytes()
            ).hexdigest()
            == digest
        ), name
    result = overview(root, check=True)
    assert result.returncode == 0, result.stdout + result.stderr


def checkpoint(root: Path) -> tuple:
    """Compare HEAD, index, tracked edit bytes, and untracked data on refusal."""
    delta = subprocess.run(
        ["git", "diff", "--binary", "HEAD"],
        cwd=root,
        capture_output=True,
        check=True,
    ).stdout
    untracked = git(
        root, "ls-files", "--others", "--exclude-standard", "--", *data.DATA_PATHS
    )
    return (
        git(root, "rev-parse", "HEAD"),
        git(root, "write-tree"),
        git(root, "status", "--porcelain"),
        hashlib.sha256(delta).hexdigest(),
        {
            path: hashlib.sha256((root / path).read_bytes()).hexdigest()
            for path in untracked.splitlines()
        },
    )


def bind_snapshot(root: Path) -> None:
    """Bind a test-local mechanics commit; do not claim full publication gates."""
    git(root, "add", "-A", "--", *data.DATA_PATHS)
    if hasattr(data, "_snapshot_document"):
        tree = git(root, "write-tree")
        document = data._snapshot_document(root, tree)
        (root / data.SNAPSHOT_PATH).write_text(
            json.dumps(document, sort_keys=True) + "\n"
        )


def assert_snapshot(root: Path) -> None:
    """Independently hash every materialized file named by the binding."""
    if not hasattr(data, "SNAPSHOT_PATH"):
        return
    document = json.loads((root / data.SNAPSHOT_PATH).read_bytes())
    for name, identity in document["files"].items():
        payload = (root / name).read_bytes()
        oid = hashlib.sha1(
            f"blob {len(payload)}\0".encode() + payload,
            usedforsecurity=False,
        ).hexdigest()
        assert oid == identity["oid"], name
        mode = "100755" if (root / name).stat().st_mode & 0o111 else "100644"
        assert mode == identity["mode"], name


def recover_and_read(repo) -> None:
    """Check real overview reconciliation, ordinary local push, then a reader.

    This isolates merge/binding mechanics. The full derived regeneration and
    verification chain belongs to the separate bounded recovery checks.
    """
    root = repo.checkout
    data.prepare(root)
    regenerate_overview(root)
    bind_snapshot(root)
    commit(root, {})
    git(root, "push", "origin", f"HEAD:{data.DATA_REF}")
    assert git(repo.origin, "rev-parse", data.MAIN_REF) == repo.main
    reset(repo, data.MAIN_REF)
    before = checkpoint(root)
    data.materialize(root)
    assert git(root, "rev-parse", "HEAD") == repo.main
    assert git(root, "write-tree") == before[1]
    assert_consistent(root)
    assert_snapshot(root)


def remote_tips(repo) -> tuple[str, str]:
    return tuple(
        git(repo.origin, "rev-parse", ref) for ref in (data.MAIN_REF, data.DATA_REF)
    )


def reset(repo, ref: str) -> None:
    git(repo.checkout, "fetch", "--no-tags", "origin", ref)
    git(repo.checkout, "checkout", "--detach", "--force", "FETCH_HEAD")
    git(repo.checkout, "clean", "-fdq")


def refresh(root: Path, path: str, marker: str) -> None:
    target = root / path
    document = json.loads(target.read_bytes())
    document.setdefault("provenance", {})["snapshot_regression"] = marker
    target.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")


@pytest.fixture
def historical_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    monkeypatch.delenv("AXIOM_ORACLES_DATA_SOURCE", raising=False)
    monkeypatch.setenv("RULESPEC_DE_REPO", str(tmp_path / "absent-rulespec-de"))
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        monkeypatch.setenv(name, "4")
    for ref in (ROLLOUT, REFRESH):
        assert git(ROOT, "rev-parse", "--verify", ref, check=False), ref
    assert git(ROOT, "rev-parse", f"{REFRESH}^1") == ROLLOUT
    common = git(ROOT, "rev-parse", "--path-format=absolute", "--git-common-dir")
    checkout, origin = tmp_path / "checkout", tmp_path / "origin.git"
    git(tmp_path, "clone", "--shared", "--no-checkout", common, str(checkout))
    git(
        checkout,
        "sparse-checkout",
        "set",
        "--no-cone",
        "/scripts/",
        *(f"/{path}" for path in data.DATA_PATHS),
    )
    git(checkout, "checkout", "--detach", ROLLOUT)
    # Keep historical report/generator bytes, but put the current publication
    # entry points on the source side. A stale candidate must reach the real
    # freshness gates, rather than stop because the historic shell runner
    # predates its check-only mode.
    source_updated = False
    for name in ("scripts/oracle_data.py", "scripts/commit_refreshed_report.sh"):
        if (
            not (checkout / name).exists()
            or (checkout / name).read_bytes() != (ROOT / name).read_bytes()
        ):
            shutil.copy2(ROOT / name, checkout / name)
            source_updated = True
    source_main = commit(checkout, {}) if source_updated else ROLLOUT
    git(tmp_path, "init", "--bare", str(origin))
    (origin / "objects/info/alternates").write_text(f"{common}/objects\n")
    git(checkout, "remote", "set-url", "origin", str(origin))
    # A shared clone inherits advertisements from the source repository. Only
    # the two heads of this private origin are relevant to publication guards.
    for ref in git(
        checkout, "for-each-ref", "--format=%(refname)", "refs/remotes/origin"
    ).splitlines():
        git(checkout, "update-ref", "-d", ref)
    git(
        checkout,
        "push",
        "origin",
        f"{source_main}:{data.MAIN_REF}",
        f"{REFRESH}:{data.DATA_REF}",
    )
    repo = SimpleNamespace(checkout=checkout, origin=origin, main=source_main)
    reset(repo, data.DATA_REF)
    assert_consistent(checkout)
    # Rollout data predates binding support. Give the historical bytes a valid
    # binding so the reader regression reaches the mixed-tree check, rather
    # than passing merely because it rejects an unsigned legacy snapshot.
    if hasattr(data, "_snapshot_document"):
        bind_snapshot(checkout)
        commit(checkout, {})
        git(checkout, "push", "origin", f"HEAD:{data.DATA_REF}")
    reset(repo, data.MAIN_REF)
    return repo


def test_kpi_publication_refuses_or_repairs_real_stale_aggregates(historical_repo):
    """The review's KPI-only publication must never ship a rejected overview."""
    repo, root = historical_repo, historical_repo.checkout
    original = root / "dashboard/public/data/axiom-policyengine-ca-snap-ecps.json"
    shutil.copy2(original, root / ADDED_REPORT)
    manifest = json.loads((root / MANIFEST).read_bytes())
    manifest["reports"].append(Path(ADDED_REPORT).name)
    (root / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n")
    regenerate_overview(root)
    repo.main = commit(root, {})
    git(root, "push", "origin", f"HEAD:{data.MAIN_REF}")
    reviewed_overview = (root / OVERVIEW).read_bytes()
    reset(repo, data.DATA_REF)
    data.prepare(root)
    assert (root / OVERVIEW).read_bytes() == reviewed_overview
    for path in data.PUBLISH_GROUPS["kpi"]:
        refresh(root, path, "scheduled-kpi-generation")
    before, tips = checkpoint(root), remote_tips(repo)
    try:
        published = data.publish(
            root, group="kpi", message="fixture: scheduled KPI generation"
        )
    except data.DataError as exc:
        assert "publication freshness gates failed" in str(exc), str(exc)
        assert checkpoint(root) == before
        assert remote_tips(repo) == tips
    else:
        assert published
        assert git(repo.origin, "rev-parse", data.MAIN_REF) == repo.main
        assert git(repo.origin, "rev-parse", data.DATA_REF) == git(
            root, "rev-parse", "HEAD"
        )
        assert_consistent(root)
        assert_snapshot(root)
    recover_and_read(repo)


def test_reader_refuses_or_repairs_real_interleaved_report_snapshot(historical_repo):
    """A reviewed report edit cannot be paired with the prior data overview."""
    repo, root = historical_repo, historical_repo.checkout
    # This real report is unchanged by the historical bot refresh. Thus only
    # its overview conflicts: main's report survives a successful Git merge.
    assert git(root, "rev-parse", f"{ROLLOUT}:{REVIEWED_REPORT}") == git(
        root,
        "rev-parse",
        f"{REFRESH}:{REVIEWED_REPORT}",
    )
    refresh(root, REVIEWED_REPORT, "reviewed-main-report-correction")
    regenerate_overview(root)
    repo.main = commit(root, {})
    git(root, "push", "origin", f"HEAD:{data.MAIN_REF}")
    before, tips = checkpoint(root), remote_tips(repo)
    try:
        data.materialize(root)
    except data.DataError:
        assert checkpoint(root) == before
        assert remote_tips(repo) == tips
    else:
        assert git(root, "rev-parse", "HEAD") == repo.main
        assert git(root, "write-tree") == before[1]
        assert_consistent(root)
        assert_snapshot(root)
    recover_and_read(repo)
