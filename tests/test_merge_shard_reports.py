import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


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
