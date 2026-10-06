import importlib.util
from pathlib import Path


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
