"""Exercise snapshot safety and liveness against source/refresh interleavings.

The small repositories use the real overview generator. Their shell entrypoint
contains only that generator's check gate, so these tests exercise the generic
publisher's isolated-candidate boundary without constructing every other
aggregate family's inputs. The real-data regression tests cover the full corpus.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from hypothesis import HealthCheck, Phase, example, given, settings
from hypothesis import strategies as st
from test_oracle_data import commit, data, git

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "dashboard/public/data/manifest.json"
OVERVIEW = "dashboard/public/data/overview.json"
SNAPSHOT = "dashboard/public/data/snapshot.json"
REVIEWED = "dashboard/public/data/reviewed.json"
BOT_REPORT = "dashboard/public/data/bot.json"
KPI = "dashboard/public/data/rule_verification.json"
KPI_SUMMARY = "dashboard/public/data/rule_verification_summary.json"
SCHEMA = "axiom.oracle_data_snapshot.v1"
# Keep the reader contract independent of the implementation's scope constant.
# A scope-omission mutation must not shrink both the producer and this oracle.
SCOPES = (
    "dashboard/public/data/",
    "conformance/scoreboard.json",
    "conformance/detail/",
    "conformance/history/",
    "conformance/exercise-census.json",
    "conformance/de-certificate-census.json",
    "conformance/executable/de-kindergeld-status.json",
    "conformance/executable/nz-treasury-incomeexplorer.json",
    "certificates/",
    "closure/de/summary.json",
    "closure/nz/summary.json",
    "comparisons/de-worker-dual-oracle/axiom-euromod.json",
    "comparisons/de-worker-dual-oracle/axiom-gettsim.json",
    "comparisons/de-worker-dual-oracle/unified-record.json",
    "comparisons/affected_map.json",
    "comparisons/nz-treasury-incomeexplorer/single-person-attestations.json",
    "axiom_oracles/data/euromod_be_coverage.json",
)


def _json(value) -> str:
    return json.dumps(value, sort_keys=True) + "\n"


def _write(root: Path, name: str, value) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json(value))


def _overview(root: Path, *, check: bool = False) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/generate_dashboard_overview.py",
            *(["--check"] if check else []),
        ],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _tree_files(root: Path, tree: str) -> dict:
    """Independent Git-tree oracle; deliberately do not call snapshot helpers."""
    result = subprocess.run(
        ["git", "ls-tree", "-r", "-z", tree, "--", *SCOPES],
        cwd=root,
        capture_output=True,
        check=True,
    )
    files = {}
    for entry in result.stdout.split(b"\0"):
        if entry:
            header, name = entry.split(b"\t", 1)
            mode, _, oid = header.decode().split()
            path = name.decode()
            if path != SNAPSHOT:
                files[path] = {"oid": oid, "mode": mode}
    return files


def _data_files(root: Path) -> dict[str, tuple[bytes, str]]:
    files = {}
    for scope in SCOPES:
        path = root / scope
        paths = path.rglob("*") if path.is_dir() else (path,)
        for candidate in paths:
            if candidate.is_file() or candidate.is_symlink():
                relative = candidate.relative_to(root).as_posix()
                if candidate.is_symlink():
                    payload = candidate.readlink().as_posix().encode()
                    mode = "120000"
                else:
                    payload = candidate.read_bytes()
                    mode = (
                        "100755"
                        if candidate.stat().st_mode & stat.S_IXUSR
                        else "100644"
                    )
                files[relative] = (payload, mode)
    return files


def _actual_files(root: Path) -> dict:
    actual = {}
    for path, (payload, mode) in _data_files(root).items():
        if path == SNAPSHOT:
            continue
        # Git's SHA-1 blob identity includes the header, unlike overview.sources.
        oid = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
        actual[path] = {"oid": oid, "mode": mode}
    return actual


def _assert_bound(root: Path) -> None:
    """Compare all materialized bytes/modes to the manifest, independently."""
    snapshot = json.loads((root / SNAPSHOT).read_bytes())
    assert snapshot == {"schema": SCHEMA, "files": _actual_files(root)}
    bundle = json.loads((root / OVERVIEW).read_bytes())
    for name, digest in bundle["sources"].items():
        assert (
            hashlib.sha256(
                (root / "dashboard/public/data" / name).read_bytes()
            ).hexdigest()
            == digest
        )


def _state(root: Path) -> tuple:
    location = root / ".git/oracle-data-materialized.json"
    return (
        git(root, "rev-parse", "HEAD"),
        git(root, "write-tree"),
        git(root, "status", "--porcelain", "--untracked-files=all"),
        _data_files(root),
        location.read_bytes() if location.exists() else None,
    )


def _case(root: Path) -> SimpleNamespace:
    seed = root / "seed"
    seed.mkdir()
    git(seed, "init", "--initial-branch=main")
    scripts = seed / "scripts"
    scripts.mkdir()
    shutil.copy2(ROOT / "scripts/generate_dashboard_overview.py", scripts)
    # This is a fixture's entire derived family, not a replacement generator.
    (scripts / "commit_refreshed_report.sh").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        '[ "${VERIFY_DERIVED_REFRESH:-}" = 1 ]\n'
        '"$PYTHON" scripts/generate_dashboard_overview.py --check\n'
    )
    _write(seed, MANIFEST, {"reports": ["reviewed.json", "bot.json"]})
    _write(seed, REVIEWED, {"suite": "reviewed", "revision": 0})
    _write(seed, BOT_REPORT, {"suite": "bot", "revision": 0})
    _write(seed, KPI, {"revision": 0})
    _write(seed, KPI_SUMMARY, {"revision": 0})
    for scope in SCOPES[1:]:
        name = scope + "probe/probe.json" if scope.endswith("/") else scope
        _write(seed, name, {"family": scope, "revision": 0})
    _overview(seed)
    commit(seed, {"source.py": "reviewed source\n"})
    _write(seed, SNAPSHOT, {"schema": SCHEMA, "files": _tree_files(seed, "HEAD")})
    main = commit(seed, {})
    origin = root / "origin.git"
    git(root, "init", "--bare", str(origin))
    git(seed, "remote", "add", "origin", str(origin))
    git(seed, "push", "origin", f"HEAD:{data.MAIN_REF}", f"HEAD:{data.DATA_REF}")
    paths = {}
    for name in ("publisher", "reader", "baseline_reader", "audit"):
        path = root / name
        git(root, "clone", "--branch", "main", str(origin), str(path))
        paths[name] = path
    return SimpleNamespace(seed=seed, origin=origin, main=main, **paths)


@pytest.fixture
def snapshot_case(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    monkeypatch.delenv("AXIOM_ORACLES_DATA_SOURCE", raising=False)
    return _case(tmp_path)


def _published(case) -> str:
    return git(case.origin, "rev-parse", data.DATA_REF)


def _audit_publication(case) -> None:
    git(case.audit, "fetch", "origin", data.DATA_REF)
    git(case.audit, "reset", "--hard", "FETCH_HEAD")
    git(case.audit, "clean", "-fd", "--", *SCOPES)
    _overview(case.audit, check=True)
    _assert_bound(case.audit)


def _review(case, revision: int, operation: str) -> None:
    git(case.seed, "checkout", "main")
    manifest = json.loads((case.seed / MANIFEST).read_text())
    if operation == "main-add":
        name = f"reviewed-{revision}.json"
        manifest["reports"].append(name)
        _write(case.seed, "dashboard/public/data/" + name, {"revision": revision})
    elif operation == "main-delete":
        if (case.seed / REVIEWED).exists():
            (case.seed / REVIEWED).unlink()
            manifest["reports"].remove("reviewed.json")
        else:
            # Repeated deletions still touch a real report and cannot be no-ops.
            _write(
                case.seed, BOT_REPORT, {"suite": "bot", "reviewed_revision": revision}
            )
    else:
        target = BOT_REPORT if operation == "main-edit-bot" else REVIEWED
        name = Path(target).name
        if name not in manifest["reports"]:
            manifest["reports"].append(name)
        _write(case.seed, target, {"suite": name, "reviewed_revision": revision})
    _write(case.seed, MANIFEST, manifest)
    _overview(case.seed)
    case.main = commit(case.seed, {})
    git(case.seed, "push", "origin", f"HEAD:{data.MAIN_REF}")


def _read(case, *, baseline: bool) -> bool:
    reader = case.baseline_reader if baseline else case.reader
    git(reader, "fetch", "origin", data.MAIN_REF)
    git(reader, "reset", "--hard", "FETCH_HEAD")
    git(reader, "clean", "-fd", "--", *SCOPES)
    before = _state(reader)
    try:
        data.materialize(reader, baseline=baseline)
    except data.DataError:
        assert _state(reader) == before, "a rejected read must not partly materialize"
        return False
    if baseline:
        # Producer baselines intentionally admit unreconciled aggregates and
        # bindings. They must still check out the exact Git tree they merged.
        assert _actual_files(reader) == _tree_files(reader, "HEAD")
    else:
        _assert_bound(reader)
        _overview(reader, check=True)
    return True


def _refresh(case, revision: int, operation: str) -> bool:
    before = _published(case)
    prepared = _state(case.publisher)
    try:
        data.prepare(case.publisher)
    except data.DataError:
        assert _state(case.publisher) == prepared
        assert _published(case) == before
        return False
    group = "dashboard" if operation == "bot-report" else "kpi"
    if group == "dashboard":
        _write(case.publisher, BOT_REPORT, {"suite": "bot", "bot_revision": revision})
        _overview(case.publisher)
    else:
        _write(case.publisher, KPI, {"revision": revision})
        _write(case.publisher, KPI_SUMMARY, {"revision": revision})
    if operation == "bot-race":
        _review(case, revision, "main-add")
    try:
        published = data.publish(case.publisher, group=group, message="fixture refresh")
    except data.DataError:
        assert _published(case) == before, (
            "failed verification must leave the remote unchanged"
        )
        return False
    assert published, "every generated revision changes the selected publication group"
    _audit_publication(case)
    return True


OPERATIONS = (
    "main-add",
    "main-edit",
    "main-delete",
    "main-edit-bot",
    "bot-kpi",
    "bot-report",
    "bot-race",
    "read",
)
MAIN_OPERATIONS = tuple(op for op in OPERATIONS if op.startswith("main-"))
ARBITRARY_SCHEDULE = st.lists(st.sampled_from(OPERATIONS), min_size=1, max_size=8)
# Every generated safety schedule reaches a stale merged candidate, varying
# the reviewed change and everything that follows it. Disabling the candidate
# gate must therefore fail generated examples as well as pinned regressions.
SAFETY_SCHEDULE = st.tuples(
    st.sampled_from(["main-add", "main-edit", "main-delete"]),
    ARBITRARY_SCHEDULE,
).map(lambda parts: ["bot-report", parts[0], "bot-kpi", *parts[1]])
LIVENESS_SCHEDULE = st.tuples(
    st.lists(st.sampled_from(OPERATIONS), max_size=4),
    st.sampled_from(MAIN_OPERATIONS),
    st.lists(st.sampled_from(OPERATIONS), max_size=4),
).map(lambda parts: [*parts[0], parts[1], *parts[2]])


@settings(
    max_examples=12,
    deadline=None,
    database=None,
    phases=[Phase.explicit, Phase.generate],
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@example(schedule=["bot-report", "main-edit", "bot-kpi", "read"])
@example(schedule=["main-add", "bot-kpi", "bot-report", "main-delete", "read"])
@example(schedule=["bot-report", "main-edit-bot", "bot-report", "read"])
@example(schedule=["bot-race", "read", "bot-report"])
@given(schedule=SAFETY_SCHEDULE)
def test_every_successful_interleaving_is_verified_and_bound(
    tmp_path, monkeypatch, schedule
):
    """Any successful transition preserves freshness and full-scope identity.

    Generated schedules vary additions, edits, deletions, refresh groups and a
    main update between prepare and publish. Rejected primary-report conflicts
    remain valid outcomes, but must leave readers and the remote unchanged.
    """
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    monkeypatch.delenv("AXIOM_ORACLES_DATA_SOURCE", raising=False)
    with tempfile.TemporaryDirectory(dir=tmp_path) as directory:
        case = _case(Path(directory))
        # Non-vacuity: every example exercises a successful publication/read.
        assert _refresh(case, 1, "bot-kpi")
        assert _read(case, baseline=False)
        assert _read(case, baseline=True)
        for revision, operation in enumerate(schedule, start=2):
            if operation.startswith("main-"):
                _review(case, revision, operation)
            elif operation.startswith("bot-"):
                _refresh(case, revision, operation)
            for baseline in (False, True):
                _read(case, baseline=baseline)


def _reconcile(case) -> None:
    """The automated workflow: reviewed merge, all generators, gated publish."""
    data.prepare(case.publisher, reconcile=True)
    _overview(case.publisher)
    data.publish(case.publisher, group="all", message="automated reconcile")
    _audit_publication(case)


@settings(
    max_examples=12,
    deadline=None,
    database=None,
    phases=[Phase.explicit, Phase.generate],
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@example(schedule=["bot-report", "main-edit", "bot-kpi", "read"])
@example(schedule=["main-add", "bot-kpi", "bot-report", "main-delete", "read"])
@example(schedule=["bot-report", "main-edit-bot", "bot-report", "read"])
@example(schedule=["bot-race", "read", "bot-report"])
@given(schedule=LIVENESS_SCHEDULE)
def test_one_automated_reconcile_restores_reads_after_every_main_data_commit(
    tmp_path, monkeypatch, schedule
):
    """A reviewed data commit requires at most one producer run to restore reads.

    Primary report conflicts, additions/deletions, and a main update racing a
    producer all remain recoverable. Every schedule also finishes readable.
    Successful consumer reads retain the independent safety oracle above.
    """
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    monkeypatch.delenv("AXIOM_ORACLES_DATA_SOURCE", raising=False)
    with tempfile.TemporaryDirectory(dir=tmp_path) as directory:
        case = _case(Path(directory))
        assert _refresh(case, 1, "bot-kpi")
        assert _read(case, baseline=False)
        for revision, operation in enumerate(schedule, start=2):
            previous_main = case.main
            if operation.startswith("main-"):
                _review(case, revision, operation)
            elif operation.startswith("bot-"):
                _refresh(case, revision, operation)
            if case.main != previous_main:
                _read(case, baseline=False)
                # Baselines may refuse unresolved primary-report conflicts,
                # which the automated reconcile explicitly resolves to main.
                baseline = _read(case, baseline=True)
                if operation in ("main-add", "bot-race"):
                    assert baseline, (
                        "producer baselines must not require consumer binding",
                        schedule,
                        operation,
                    )
                _reconcile(case)
                assert _read(case, baseline=False), (
                    "one automated reconcile must restore a consumer read",
                    schedule,
                    operation,
                )
                changed = git(
                    case.seed, "diff", "--name-only", previous_main, case.main
                ).splitlines()
                for name in changed:
                    if name in (MANIFEST, OVERVIEW, SNAPSHOT):
                        continue
                    reviewed, materialized = case.seed / name, case.reader / name
                    assert materialized.exists() == reviewed.exists()
                    if reviewed.exists():
                        assert materialized.read_bytes() == reviewed.read_bytes(), (
                            "reconcile must retain reviewed main corrections",
                            name,
                        )
                assert _read(case, baseline=True)
        _reconcile(case)
        assert _read(case, baseline=False), "no generated schedule may end wedged"
        assert _read(case, baseline=True)


def test_kpi_candidate_cannot_borrow_unstaged_aggregate_repair(snapshot_case):
    case = snapshot_case
    # A reviewed report lands without its rebuilt overview. A local repair
    # outside the KPI group must not make the committed KPI candidate pass.
    commit(case.seed, {REVIEWED: _json({"reviewed_revision": 1})})
    git(case.seed, "push", "origin", f"HEAD:{data.MAIN_REF}")
    data.prepare(case.publisher)
    _overview(case.publisher)
    _write(case.publisher, KPI, {"revision": 1})
    before = _published(case)

    with pytest.raises(data.DataError, match="freshness gates failed"):
        data.publish(case.publisher, group="kpi", message="must reject stale candidate")

    assert _published(case) == before


def test_publication_binds_the_staged_candidate_after_scope_add(snapshot_case):
    case = snapshot_case
    data.prepare(case.publisher)
    _write(case.publisher, BOT_REPORT, {"revision": "previous staged bytes"})
    _overview(case.publisher)
    git(case.publisher, "add", "--", "dashboard/public/data/")
    _write(case.publisher, BOT_REPORT, {"revision": "current generated bytes"})
    _overview(case.publisher)

    assert data.publish(
        case.publisher, group="dashboard", message="bind actual candidate"
    )

    _audit_publication(case)
    assert json.loads((case.audit / BOT_REPORT).read_bytes()) == {
        "revision": "current generated bytes"
    }


def test_snapshot_writer_refuses_clean_normalization_of_raw_report_bytes(snapshot_case):
    root = snapshot_case.publisher
    git(root, "config", "core.autocrlf", "input")
    report = root / REVIEWED
    report.write_bytes(report.read_bytes().replace(b"\n", b"\r\n"))
    before = _state(root)

    with pytest.raises(data.DataError, match="generated bytes differ"):
        data.write_snapshot(root)

    assert _state(root) == before


def test_snapshot_writer_refuses_ignored_regenerated_overview_absent_from_candidate(
    snapshot_case,
):
    case = snapshot_case
    commit(
        case.seed,
        {
            OVERVIEW: None,
            ".gitignore": "/dashboard/public/data/overview.json\n",
        },
    )
    git(case.seed, "push", "origin", f"HEAD:{data.MAIN_REF}")
    data.prepare(case.publisher)
    _overview(case.publisher)
    _overview(case.publisher, check=True)
    assert git(case.publisher, "check-ignore", OVERVIEW) == OVERVIEW
    assert git(case.publisher, "ls-files", "--", OVERVIEW) == ""
    before = _state(case.publisher)

    with pytest.raises(
        data.DataError, match="generated files are outside the candidate snapshot"
    ):
        data.write_snapshot(case.publisher)

    assert _state(case.publisher) == before


def test_snapshot_writer_refuses_ignored_untracked_binding_metadata(snapshot_case):
    case = snapshot_case
    commit(
        case.seed,
        {
            SNAPSHOT: None,
            ".gitignore": "/dashboard/public/data/snapshot.json\n",
        },
    )
    git(case.seed, "push", "origin", f"HEAD:{data.MAIN_REF}")
    data.prepare(case.publisher)
    _overview(case.publisher, check=True)
    assert not (case.publisher / SNAPSHOT).exists()
    assert git(case.publisher, "check-ignore", SNAPSHOT) == SNAPSHOT
    before = _state(case.publisher)

    with pytest.raises(data.DataError, match="snapshot.json is ignored"):
        data.write_snapshot(case.publisher)

    assert _state(case.publisher) == before


def test_snapshot_writer_handles_absent_optional_families_and_tracked_deletions(
    snapshot_case,
):
    case = snapshot_case
    absent = "conformance/exercise-census.json"
    deleted = "conformance/de-certificate-census.json"
    commit(case.seed, {absent: None})
    git(case.seed, "push", "origin", f"HEAD:{data.MAIN_REF}")
    data.prepare(case.publisher)
    (case.publisher / deleted).unlink()
    head = git(case.publisher, "rev-parse", "HEAD")
    index = git(case.publisher, "write-tree")

    error = None
    try:
        data.write_snapshot(case.publisher)
    except data.DataError as exc:
        error = str(exc)
    assert error is None, error

    assert git(case.publisher, "rev-parse", "HEAD") == head
    assert git(case.publisher, "write-tree") == index
    _assert_bound(case.publisher)
    files = json.loads((case.publisher / SNAPSHOT).read_text())["files"]
    assert absent not in files
    assert deleted not in files


def test_snapshot_writer_binds_uncommitted_refresh_without_changing_real_index(
    snapshot_case,
):
    root = snapshot_case.publisher
    (root / "source.py").write_text("keep this staged source edit\n")
    git(root, "add", "--", "source.py")
    _write(root, KPI, {"revision": "uncommitted refresh"})
    _write(root, KPI_SUMMARY, {"revision": "uncommitted refresh"})
    head = git(root, "rev-parse", "HEAD")
    index = git(root, "write-tree")
    previous = (root / SNAPSHOT).read_bytes()

    data.write_snapshot(root)

    assert git(root, "rev-parse", "HEAD") == head
    assert git(root, "write-tree") == index
    assert (root / "source.py").read_text() == "keep this staged source edit\n"
    assert (root / SNAPSHOT).read_bytes() != previous
    _assert_bound(root)


@pytest.mark.parametrize(
    "name", ["snapshot.json", "./snapshot.json", "../data/snapshot.json", "absolute"]
)
def test_publication_cannot_invalidate_overview_by_rewriting_its_snapshot_input(
    snapshot_case,
    name,
):
    case = snapshot_case
    data.prepare(case.publisher)
    manifest = json.loads((case.publisher / MANIFEST).read_text())
    if name == "absolute":
        name = str(case.publisher / SNAPSHOT)
    manifest["reports"].append(name)
    _write(case.publisher, MANIFEST, manifest)
    _overview(case.publisher)
    _overview(case.publisher, check=True)
    before = _published(case)

    # Binding changes snapshot.json. The gate must reject this dependency or
    # check the final bound tree, rather than validate then invalidate it.
    with pytest.raises(data.DataError, match="snapshot.json is reserved metadata"):
        data.publish(case.publisher, group="dashboard", message="reject binding cycle")

    assert _published(case) == before


@pytest.mark.parametrize("absolute", [False, True])
def test_publication_refuses_overview_dependencies_outside_the_bound_directory(
    snapshot_case,
    absolute,
):
    case = snapshot_case
    # Commit the dependency as source so the isolated candidate contains the
    # real input too; freshness checks must not fail merely because it is absent.
    outside = "dashboard/public/outside.json"
    commit(case.seed, {outside: _json({"outside": "valid report input"})})
    git(case.seed, "push", "origin", f"HEAD:{data.MAIN_REF}")
    data.prepare(case.publisher)
    manifest = json.loads((case.publisher / MANIFEST).read_text())
    name = str(case.publisher / outside) if absolute else "../outside.json"
    manifest["reports"].append(name)
    _write(case.publisher, MANIFEST, manifest)
    _overview(case.publisher)
    _overview(case.publisher, check=True)
    assert name in json.loads((case.publisher / OVERVIEW).read_text())["sources"]
    before = _published(case)

    with pytest.raises(data.DataError, match="invalid report manifest"):
        data.publish(
            case.publisher, group="dashboard", message="reject unbound dependency"
        )

    assert _published(case) == before


def test_reader_requires_the_published_binding_even_if_main_rebinds_its_own_data(
    snapshot_case,
):
    case = snapshot_case
    # Main alone edits a report and then writes a full, internally valid hash
    # manifest. This must not bless the old overview as a published snapshot.
    commit(case.seed, {REVIEWED: _json({"reviewed_revision": 1})})
    _write(
        case.seed, SNAPSHOT, {"schema": SCHEMA, "files": _tree_files(case.seed, "HEAD")}
    )
    main = commit(case.seed, {})
    assert json.loads((case.seed / SNAPSHOT).read_text()) == {
        "schema": SCHEMA,
        "files": _tree_files(case.seed, "HEAD"),
    }
    result = subprocess.run(
        [sys.executable, "scripts/generate_dashboard_overview.py", "--check"],
        cwd=case.seed,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 1 and "stale" in result.stdout
    git(case.seed, "push", "origin", f"{main}:{data.MAIN_REF}")
    reader = case.reader
    git(reader, "fetch", "origin", data.MAIN_REF)
    git(reader, "reset", "--hard", "FETCH_HEAD")
    before = _state(reader)
    published = _published(case)

    with pytest.raises(data.DataError):
        data.materialize(reader)

    assert _state(reader) == before
    assert _published(case) == published


@pytest.mark.parametrize("path", [REVIEWED, SNAPSHOT])
@pytest.mark.parametrize("staged", [False, True])
def test_reader_checks_local_edits_even_when_bound_path_has_no_remote_delta(
    snapshot_case, path, staged
):
    case = snapshot_case
    (case.reader / path).write_text('{"local":"keep this edit"}\n')
    if staged:
        git(case.reader, "add", "--", path)
    before = _state(case.reader)

    with pytest.raises(data.DataError):
        data.materialize(case.reader)

    assert _state(case.reader) == before


@pytest.mark.parametrize("baseline", [False, True])
@pytest.mark.parametrize("staged", [False, True])
@pytest.mark.parametrize(
    "path",
    [
        "dashboard/public/data/untracked.json",
        "certificates/untracked.json",
        "conformance/detail/untracked.json",
    ],
)
def test_reader_refuses_local_generated_files_outside_bound_set(
    snapshot_case,
    baseline,
    staged,
    path,
):
    case = snapshot_case
    reader = case.baseline_reader if baseline else case.reader
    _write(reader, path, {"local": "keep this unbound generated file"})
    if staged:
        git(reader, "add", "--", path)
    before = _state(reader)

    with pytest.raises(data.DataError):
        data.materialize(reader, baseline=baseline)

    assert _state(reader) == before


@pytest.mark.parametrize("baseline", [False, True])
@pytest.mark.parametrize(
    "setting",
    [
        "attributes-eol",
        "core.autocrlf",
        "autocrlf-alias",
        "core.eol",
        "filter",
        "working-tree-encoding",
    ],
)
def test_reader_bypasses_checkout_transformations_or_refuses_without_changes(
    snapshot_case,
    baseline,
    setting,
):
    case = snapshot_case
    attributes = {
        "attributes-eol": "text eol=crlf",
        "filter": "filter=fixture",
        "working-tree-encoding": "working-tree-encoding=UTF-8",
    }
    if setting in attributes:
        commit(
            case.seed,
            {
                ".gitattributes": f"dashboard/public/data/*.json {attributes[setting]}\n",
            },
        )
        git(case.seed, "push", "origin", f"HEAD:{data.MAIN_REF}")
    reader = case.baseline_reader if baseline else case.reader
    git(reader, "fetch", "origin", data.MAIN_REF)
    git(reader, "reset", "--hard", "FETCH_HEAD")
    if setting == "core.autocrlf":
        git(reader, "config", setting, "true")
    elif setting == "autocrlf-alias":
        git(reader, "config", "core.autocrlf", "yes")
    elif setting == "core.eol":
        git(reader, "config", setting, "crlf")
    elif setting == "filter":
        git(reader, "config", "filter.fixture.clean", "cat")
        git(reader, "config", "filter.fixture.smudge", "cat")
    # Local configurations can already have smudged the checkout during the
    # explicit reset above. Preserve those raw-byte edits by refusing safely;
    # otherwise a successful read must reproduce the exact bound Git blobs.
    _read(case, baseline=baseline)


@pytest.mark.parametrize("baseline", [False, True])
def test_reader_never_succeeds_with_a_new_report_smudged_to_crlf(
    snapshot_case, baseline
):
    case = snapshot_case
    report = "dashboard/public/data/new-filtered.json"
    git(case.seed, "checkout", "-B", "oracle-data", case.main)
    manifest = json.loads((case.seed / MANIFEST).read_text())
    manifest["reports"].append(Path(report).name)
    # Match the append-only union's canonical formatting, so an incidental
    # manifest rewrite cannot refuse the read before the checkout-byte guard.
    (case.seed / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n")
    _write(case.seed, report, {"new": "published LF bytes"})
    _overview(case.seed)
    commit(case.seed, {})
    _write(
        case.seed, SNAPSHOT, {"schema": SCHEMA, "files": _tree_files(case.seed, "HEAD")}
    )
    commit(case.seed, {})
    _assert_bound(case.seed)
    _overview(case.seed, check=True)
    git(case.seed, "push", "origin", f"HEAD:{data.DATA_REF}")
    git(case.seed, "checkout", "main")
    commit(case.seed, {".gitattributes": f"{report} text eol=crlf\n"})
    git(case.seed, "push", "origin", f"HEAD:{data.MAIN_REF}")
    reader = case.baseline_reader if baseline else case.reader
    git(reader, "fetch", "origin", data.MAIN_REF)
    git(reader, "reset", "--hard", "FETCH_HEAD")
    assert not (reader / report).exists()
    # Existing files are still the exact published LF bytes. Only restoring
    # the new report would introduce CRLF, so raw pre-read hashes cannot mask
    # a missing checkout-transformation guard.
    _assert_bound(reader)
    git(reader, "fetch", "origin", data.DATA_REF)
    candidate = data._reader_merge_tree(
        reader, git(reader, "rev-parse", "HEAD"), _published(case)
    )
    assert json.loads(git(reader, "show", f"{candidate}:{SNAPSHOT}")) == {
        "schema": SCHEMA,
        "files": _tree_files(reader, candidate),
    }

    # A refusal must leave all bytes unchanged. A successful read must satisfy
    # the independent whole-file-set oracle, including the new report's bytes.
    _read(case, baseline=baseline)


@pytest.mark.parametrize(
    "corruption",
    [
        "missing-snapshot",
        "invalid-json",
        "wrong-schema",
        "missing-entry",
        "extra-entry",
        "wrong-oid",
        "wrong-mode",
        "report-tamper",
        "aggregate-tamper",
    ],
)
def test_invalid_snapshot_is_refused_before_any_materialization(
    snapshot_case, corruption
):
    case = snapshot_case
    git(case.seed, "checkout", "-B", "oracle-data", case.main)
    snapshot = json.loads((case.seed / SNAPSHOT).read_text())
    if corruption == "missing-snapshot":
        (case.seed / SNAPSHOT).unlink()
    elif corruption == "invalid-json":
        (case.seed / SNAPSHOT).write_text("{broken\n")
    elif corruption == "report-tamper":
        _write(case.seed, REVIEWED, {"unbound": "new report bytes"})
    elif corruption == "aggregate-tamper":
        _write(case.seed, OVERVIEW, {"unbound": "new aggregate bytes"})
    else:
        if corruption == "wrong-schema":
            snapshot["schema"] = "unknown"
        elif corruption == "missing-entry":
            del snapshot["files"][REVIEWED]
        elif corruption == "extra-entry":
            snapshot["files"]["dashboard/public/data/absent.json"] = {
                "oid": "a" * 40,
                "mode": "100644",
            }
        elif corruption == "wrong-oid":
            snapshot["files"][REVIEWED]["oid"] = "a" * 40
        else:
            snapshot["files"][REVIEWED]["mode"] = "100755"
        _write(case.seed, SNAPSHOT, snapshot)
    commit(case.seed, {})
    git(case.seed, "push", "origin", f"HEAD:{data.DATA_REF}")
    reader = case.reader
    before = _state(reader)

    with pytest.raises(data.DataError):
        data.materialize(reader)

    assert _state(reader) == before


DELAYED_LIVENESS_SCHEDULE = st.tuples(
    st.lists(st.sampled_from(OPERATIONS), max_size=4),
    st.sampled_from(MAIN_OPERATIONS),
    st.lists(st.sampled_from(OPERATIONS), max_size=4),
    st.sampled_from(MAIN_OPERATIONS),
).map(lambda parts: [*parts[0], parts[1], *parts[2], parts[3]])


@settings(
    max_examples=12,
    deadline=None,
    database=None,
    phases=[Phase.explicit, Phase.generate],
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@example(schedule=["bot-report", "main-edit", "main-add", "bot-kpi", "main-delete"])
@example(
    schedule=[
        "bot-report",
        "main-edit-bot",
        "main-delete",
        "bot-report",
        "main-add",
    ]
)
@example(schedule=["main-add", "bot-race", "main-delete", "main-edit-bot"])
@example(schedule=["main-delete", "main-delete", "bot-report", "main-edit"])
@given(schedule=DELAYED_LIVENESS_SCHEDULE)
def test_one_delayed_reconcile_restores_reads_from_reachable_pending_main_states(
    tmp_path, monkeypatch, schedule
):
    """Several unpublished main updates still need only one final producer run.

    Build the reachable state with arbitrary reviewed changes, failed/successful
    bot runs, and read attempts, without invoking the reconcile producer. After
    one further main data commit, a single producer must restore bound reads.
    """
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    monkeypatch.delenv("AXIOM_ORACLES_DATA_SOURCE", raising=False)
    with tempfile.TemporaryDirectory(dir=tmp_path) as directory:
        case = _case(Path(directory))
        assert _refresh(case, 1, "bot-kpi")
        assert _read(case, baseline=False)
        for revision, operation in enumerate(schedule[:-1], start=2):
            if operation.startswith("main-"):
                _review(case, revision, operation)
            elif operation.startswith("bot-"):
                _refresh(case, revision, operation)
            for baseline in (False, True):
                _read(case, baseline=baseline)

        previous_main = case.main
        assert schedule[-1] in MAIN_OPERATIONS
        _review(case, len(schedule) + 2, schedule[-1])
        _read(case, baseline=False)
        _read(case, baseline=True)
        # Exactly one reconcile follows the entire pending-main schedule.
        _reconcile(case)
        assert _read(case, baseline=False), (
            "one delayed producer must restore a consumer read",
            schedule,
        )
        changed = git(
            case.seed, "diff", "--name-only", previous_main, case.main
        ).splitlines()
        for name in changed:
            if name in (MANIFEST, OVERVIEW, SNAPSHOT):
                continue
            reviewed, materialized = case.seed / name, case.reader / name
            assert materialized.exists() == reviewed.exists()
            if reviewed.exists():
                assert materialized.read_bytes() == reviewed.read_bytes(), (
                    "delayed reconcile must retain the final reviewed correction",
                    name,
                )
        assert _read(case, baseline=True), "no delayed schedule may end wedged"
