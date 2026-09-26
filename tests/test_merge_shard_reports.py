import copy
import importlib.util
from pathlib import Path

import pytest

from axiom_oracles.comparison.dispositions import (
    DISPOSITIONS_SCHEMA_VERSION,
    apply_dispositions,
    selection_binding,
    validate_dispositions,
)


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


def _binary(sha: str, *, rows: int = 1, **overrides) -> dict:
    return {
        "sha256": sha * 64,
        "build": "2025-01-01",
        "build_observed": "2025-01-01",
        "platform": "linux-x86_64",
        "bytes": 123,
        "rows": rows,
        "scope": "default",
        **overrides,
    }


def _taxsim_shard(case_id: str, binaries: list[dict], location: str) -> dict:
    shard = _shard({})
    shard["engines"] = {"left": "axiom", "right": "taxsim"}
    shard["case_count"] = 1
    shard["summary"].update(comparison_count=1, mismatch_count=1)
    shard["mismatches"] = [{
        "case_id": case_id,
        "concept": "us:test#income_tax",
        "kind": "amount_difference",
        "left": 10,
        "right": 0,
        "difference": 10,
    }]
    if location in ("engine_identity", "both"):
        shard["engine_identity"] = {
            "taxsim": {"pin_profile": "test-profile", "binaries": copy.deepcopy(binaries)},
        }
    if location in ("provenance", "both"):
        shard["provenance"] = {"oracle": {
            "taxsim_pin_profile": "test-profile",
            "taxsim_binaries": copy.deepcopy(binaries),
            "policyengine_taxsim": "2.30.0",
        }}
    return shard


@pytest.mark.parametrize("location", ["engine_identity", "provenance", "both"])
def test_merge_mixed_taxsim_binaries_expires_a_only_disposition(location: str) -> None:
    shards = [
        _taxsim_shard("case-a", [_binary("a")], location),
        _taxsim_shard("case-b", [_binary("b", scope="state:6/year:2024")], location),
    ]
    merged = _load_merge_shard_reports().merge(shards)
    dispositions = {
        "schema": DISPOSITIONS_SCHEMA_VERSION,
        "suite": "sharded-suite",
        "entries": [{
            "id": "binary-a-gap",
            "concept": "us:test#income_tax",
            "case_selector": {"case_id_prefix": "case-"},
            "disposition": "upstream_engine_gap",
            "attribution": "taxsim",
            "evidence": {
                "mechanism": "This TAXSIM binary returns zero.",
                "row_arithmetic": [{"expression": "right", "equals": 0}],
            },
            "expires_on_source_change": True,
            "oracle_binding": {"taxsim_binary_sha256": ["a" * 64]},
            "selector_binding": selection_binding(merged["mismatches"]),
        }],
    }
    assert validate_dispositions(dispositions, suite_engines=("axiom", "taxsim")) == []

    dispositioned = apply_dispositions(merged, dispositions)
    block = dispositioned["summary"]["dispositioned"]
    assert block["counts"]["upstream_engine_gap"] == 0
    assert block["expired_reasons"] == {"binary-a-gap": "oracle_identity_changed"}
    assert all("disposition" not in row for row in dispositioned["mismatches"])
    for binaries in (
        (merged.get("engine_identity") or {}).get("taxsim", {}).get("binaries"),
        (merged.get("provenance") or {}).get("oracle", {}).get("taxsim_binaries"),
    ):
        if binaries is not None:
            assert {binary["sha256"] for binary in binaries} == {"a" * 64, "b" * 64}


@pytest.mark.parametrize("location", ["engine_identity", "provenance", "both"])
def test_merge_taxsim_binary_rows_by_sha_scope_and_platform(location: str) -> None:
    first = _taxsim_shard("case-a", [_binary("a", rows=2)], location)
    second = _taxsim_shard("case-b", [
        _binary("a", rows=3),
        _binary("a", scope="state:6/year:2024"),
        _binary("a", platform="darwin-arm64"),
    ], location)
    original = copy.deepcopy([first, second])
    merged = _load_merge_shard_reports().merge([first, second])
    binaries = (
        merged["engine_identity"]["taxsim"]["binaries"]
        if location != "provenance"
        else merged["provenance"]["oracle"]["taxsim_binaries"]
    )
    assert len(binaries) == 3
    assert sorted(binary["rows"] for binary in binaries) == [1, 1, 5]
    assert [first, second] == original
    if location == "both":
        assert binaries == merged["provenance"]["oracle"]["taxsim_binaries"]


@pytest.mark.parametrize("location", ["engine_identity", "provenance"])
def test_merge_rejects_different_taxsim_pin_profiles(location: str) -> None:
    first = _taxsim_shard("case-a", [_binary("a")], location)
    second = _taxsim_shard("case-b", [_binary("b")], location)
    if location == "engine_identity":
        second[location]["taxsim"]["pin_profile"] = "other-profile"
    else:
        second[location]["oracle"]["taxsim_pin_profile"] = "other-profile"
    with pytest.raises(SystemExit, match="pin_profile"):
        _load_merge_shard_reports().merge([first, second])


@pytest.mark.parametrize("location", ["engine_identity", "provenance"])
@pytest.mark.parametrize("missing_first", [False, True])
def test_merge_rejects_incomplete_taxsim_identity(location: str, missing_first: bool) -> None:
    first = _taxsim_shard("case-a", [_binary("a")], location)
    second = _taxsim_shard("case-b", [_binary("b")], location)
    del (first if missing_first else second)[location]
    with pytest.raises(SystemExit, match="identity"):
        _load_merge_shard_reports().merge([first, second])


@pytest.mark.parametrize("other_version", ["2.31.0", None])
def test_merge_rejects_inconsistent_taxsim_wrapper_version(other_version: str | None) -> None:
    first = _taxsim_shard("case-a", [_binary("a")], "provenance")
    second = _taxsim_shard("case-b", [_binary("b")], "provenance")
    if other_version is None:
        del second["provenance"]["oracle"]["policyengine_taxsim"]
    else:
        second["provenance"]["oracle"]["policyengine_taxsim"] = other_version
    with pytest.raises(SystemExit, match="policyengine_taxsim"):
        _load_merge_shard_reports().merge([first, second])


def test_merge_rejects_disagreement_between_taxsim_identity_locations() -> None:
    first = _taxsim_shard("case-a", [_binary("a")], "both")
    second = _taxsim_shard("case-b", [_binary("b")], "both")
    second["provenance"]["oracle"]["taxsim_binaries"] = [_binary("a")]
    with pytest.raises(SystemExit, match="identity disagrees"):
        _load_merge_shard_reports().merge([first, second])


def test_merge_preserves_non_taxsim_identity_metadata() -> None:
    shards = [_shard({}), _shard({})]
    for shard in shards:
        shard["engine_identity"] = {"reference": {"release": "1"}}
        shard["provenance"] = {"oracle": {"name": "reference", "version": "1"}}
    merged = _load_merge_shard_reports().merge(shards)
    assert merged["engine_identity"] == shards[0]["engine_identity"]
    assert merged["provenance"] == shards[0]["provenance"]


@pytest.mark.parametrize("location", ["engine_identity", "provenance", "both"])
def test_merge_rejects_empty_binary_identity_for_nonempty_shard(location: str) -> None:
    first = _taxsim_shard("case-a", [_binary("a")], location)
    second = _taxsim_shard("case-b", [], location)
    with pytest.raises(SystemExit, match="incomplete TAXSIM identity"):
        _load_merge_shard_reports().merge([first, second])


@pytest.mark.parametrize("location", ["engine_identity", "provenance", "both"])
def test_merge_accepts_empty_binary_identity_for_empty_shard(location: str) -> None:
    first = _taxsim_shard("case-a", [_binary("a")], location)
    second = _taxsim_shard("case-b", [], location)
    second.update(case_count=0, mismatches=[], summary={})
    merged = _load_merge_shard_reports().merge([first, second])
    assert merged["case_count"] == 1
    assert merged["mismatches"] == first["mismatches"]


@pytest.mark.parametrize("other_version", ["2.31.0", None])
def test_merge_rejects_inconsistent_legacy_taxsim_identity(other_version: str | None) -> None:
    first = _shard({})
    second = _shard({})
    first["provenance"] = {"oracle": {"policyengine_taxsim": "2.30.0"}}
    if other_version is not None:
        second["provenance"] = {"oracle": {"policyengine_taxsim": other_version}}
    with pytest.raises(SystemExit, match="policyengine_taxsim"):
        _load_merge_shard_reports().merge([first, second])
