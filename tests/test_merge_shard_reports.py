import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.adapters.taxsim.pins import same_build


REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_merge_shard_reports():
    path = REPO_ROOT / "scripts" / "merge_shard_reports.py"
    spec = importlib.util.spec_from_file_location("merge_shard_reports", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _shard(errors_by_engine: dict[str, int]) -> dict:
    return {
        "schema_version": "axiom.comparison_report.v2",
        "suite": "sharded-suite",
        "population": "synthetic",
        "engines": {"left": "axiom", "right": "reference"},
        "locales": ["XX"],
        "case_count": 0,
        "summary": {
            "error_count": sum(errors_by_engine.values()),
            "errors_by_engine": errors_by_engine,
        },
    }


def test_merge_errors_by_engine_preserves_object_contract() -> None:
    merge = _load_merge_shard_reports().merge

    empty = merge([_shard({}), _shard({})])
    assert empty["summary"]["errors_by_engine"] == {}

    with_errors = merge(
        [
            _shard({}),
            _shard({"axiom": 1}),
            _shard({"axiom": 2, "reference": 1}),
        ]
    )
    assert with_errors["summary"]["error_count"] == 4
    assert with_errors["summary"]["errors_by_engine"] == {
        "axiom": 3,
        "reference": 1,
    }
    assert isinstance(with_errors["summary"]["errors_by_engine"], dict)


def _taxsim_shard(binaries: list[dict]) -> dict:
    shard = _shard({})
    shard["case_count"] = sum(binary["rows"] for binary in binaries)
    shard["engine_identity"] = {
        "taxsim": {
            "pinned_policyengine_taxsim": "2.30.0",
            "binaries": binaries,
        },
    }
    shard["provenance"] = {
        "schema": "axiom_oracles.provenance.v1",
        "generated_by": "shard-runner",
        "dataset": {"sha256": "dataset-sha"},
        "oracle": {
            "name": "taxsim",
            "policyengine_taxsim": "2.30.0",
            "taxsim_binaries": deepcopy(binaries),
        },
    }
    return shard


@pytest.mark.parametrize("second_sha", ["a" * 64, "b" * 64])
def test_merge_updates_existing_taxsim_provenance(second_sha: str) -> None:
    """Both identity locations describe every executed binary and its rows."""
    shards = [
        _taxsim_shard([{"path": "/binary", "sha256": "a" * 64, "rows": 3}]),
        _taxsim_shard([{"path": "/binary", "sha256": second_sha, "rows": 4}]),
    ]
    original = deepcopy(shards)

    merged = _load_merge_shard_reports().merge(shards)

    binaries = merged["engine_identity"]["taxsim"]["binaries"]
    assert merged["provenance"]["oracle"]["taxsim_binaries"] == binaries
    assert sum(binary["rows"] for binary in binaries) == 7
    assert len(binaries) == (1 if second_sha == "a" * 64 else 2)
    assert merged["provenance"] == {
        **original[0]["provenance"],
        "oracle": {
            **original[0]["provenance"]["oracle"],
            "taxsim_binaries": binaries,
        },
    }
    assert shards == original


def test_merge_equivalent_observed_taxsim_stamps() -> None:
    """CSV and verbose observations of one build share the first stamp."""
    binary = {
        "path": "/one-binary",
        "sha256": "a" * 64,
        "build": "cdate-20260521",
    }
    shards = [
        _taxsim_shard(
            [{**binary, "build_observed": "cdate-20260521", "rows": 3}]
        ),
        _taxsim_shard([{**binary, "build_observed": "20260521", "rows": 4}]),
    ]
    original = deepcopy(shards)

    merged = _load_merge_shard_reports().merge(shards)

    binaries = merged["engine_identity"]["taxsim"]["binaries"]
    assert binaries == [
        {**binary, "build_observed": "cdate-20260521", "rows": 7}
    ]
    assert merged["provenance"]["oracle"]["taxsim_binaries"] == binaries
    assert merged["case_count"] == 7
    assert shards == original


@settings(max_examples=100, deadline=None)
@given(
    partition=st.lists(
        st.lists(
            st.tuples(st.sampled_from(["a", "b", "c"]), st.integers(1, 10_000)),
            min_size=1,
            max_size=3,
        ),
        min_size=2,
        max_size=6,
    )
)
def test_merge_taxsim_provenance_conserves_rows_per_binary(partition) -> None:
    """Both identity locations sum rows for each binary across all shards."""
    shards = [
        _taxsim_shard(
            [
                {"path": "/binary", "sha256": sha * 64, "rows": rows}
                for sha, rows in part
            ]
        )
        for part in partition
    ]
    expected: dict[str, int] = {}
    for part in partition:
        for sha, rows in part:
            expected[sha * 64] = expected.get(sha * 64, 0) + rows

    merged = _load_merge_shard_reports().merge(shards)

    identity_binaries = merged["engine_identity"]["taxsim"]["binaries"]
    provenance_binaries = merged["provenance"]["oracle"]["taxsim_binaries"]
    assert provenance_binaries == identity_binaries
    assert {
        binary["sha256"]: binary["rows"] for binary in provenance_binaries
    } == expected


@settings(max_examples=100, deadline=None)
@given(
    partition=st.lists(
        st.lists(
            st.tuples(
                st.sampled_from(["a", "b", "c"]),
                st.sampled_from(["/binary-1", "/binary-2"]),
                st.sampled_from(
                    [
                        "cdate-20260521",
                        "20260521",
                        "cd2026081819",
                        "2026081819",
                        "cdate-compdate",
                        "compdate",
                    ]
                ),
                st.integers(1, 10_000),
            ),
            max_size=6,
        ),
        min_size=1,
        max_size=6,
    )
)
def test_merge_taxsim_stamp_partitions_conserve_rows(partition) -> None:
    """Every shard split preserves rows and one entry per equivalent stamp."""
    shards = [
        _taxsim_shard(
            [
                {
                    "path": path,
                    "sha256": sha * 64,
                    "build_observed": stamp,
                    "rows": rows,
                }
                for sha, path, stamp, rows in part
            ]
        )
        for part in partition
    ]
    expected_rows: dict[tuple[str, str], int] = {}
    expected_groups: list[dict] = []
    for shard in shards:
        for binary in shard["engine_identity"]["taxsim"]["binaries"]:
            key = (binary["sha256"], binary["path"])
            expected_rows[key] = expected_rows.get(key, 0) + binary["rows"]
            group = next(
                (
                    item
                    for item in expected_groups
                    if (item["sha256"], item["path"]) == key
                    and same_build(item["build_observed"], binary["build_observed"])
                ),
                None,
            )
            if group is None:
                expected_groups.append(dict(binary))
            else:
                group["rows"] += binary["rows"]

    merged = _load_merge_shard_reports().merge(shards)

    binaries = merged["engine_identity"]["taxsim"]["binaries"]
    assert merged["provenance"]["oracle"]["taxsim_binaries"] == binaries
    assert len(binaries) == len(expected_groups)
    actual_rows: dict[tuple[str, str], int] = {}
    for binary in binaries:
        key = (binary["sha256"], binary["path"])
        actual_rows[key] = actual_rows.get(key, 0) + binary["rows"]
    assert actual_rows == expected_rows
    assert merged["case_count"] == sum(expected_rows.values())
    for expected in expected_groups:
        matches = [
            binary
            for binary in binaries
            if (binary["sha256"], binary["path"])
            == (expected["sha256"], expected["path"])
            and same_build(binary["build_observed"], expected["build_observed"])
        ]
        assert matches == [expected]
