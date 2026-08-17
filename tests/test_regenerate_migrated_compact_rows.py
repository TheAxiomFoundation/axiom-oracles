import copy
import json

import pytest

from scripts.regenerate_migrated_compact_rows import (
    _validate_projection,
    project_dispositions,
)


CONCEPT = "us:statutes/example#benefit"


def _full_report(disposition: str | None) -> dict:
    mismatch = {
        "case_id": "case-1",
        "concept": CONCEPT,
        "left": 10,
        "right": 20,
    }
    if disposition is not None:
        mismatch["disposition"] = {
            "id": "known-explanation",
            "disposition": disposition,
        }
    count_kind = disposition or "unexplained"
    return {
        "suite": "projection-suite",
        "case_count": 1,
        "cases": [],
        "concepts": [
            {
                "id": CONCEPT,
                "comparison": "amount",
                "tolerance": 0.01,
                "relative_tolerance": 0,
            }
        ],
        "aggregates": [
            {
                "concept": CONCEPT,
                "comparison_count": 1,
                "mismatch_count": 1,
                "comparison_weight": 1,
                "left_weighted_sum": 10,
                "right_weighted_sum": 20,
            }
        ],
        "mismatches": [mismatch],
        "summary": {
            "comparison_count": 1,
            "match_count": 0,
            "mismatch_count": 1,
            "dispositioned": {
                "counts": {count_kind: 1},
                "unexplained_count": int(disposition is None),
            },
        },
    }


def _full_chunks(marker: str | None) -> list[tuple[str, list[dict]]]:
    mismatch = {
        "c": CONCEPT,
        "l": 10,
        "x": 20,
        "d": 10,
    }
    if marker is not None:
        mismatch["e"] = marker
    return [
        (
            "chunk-0.json",
            [
                {
                    "id": "case-1",
                    "r": 0,
                    "h": {},
                    "v": [],
                    "m": [mismatch],
                }
            ],
        )
    ]


@pytest.mark.parametrize(
    ("report_marker", "source_marker"),
    [
        pytest.param("explained_residual", None, id="add-marker"),
        pytest.param(None, "stale_explanation", id="remove-stale-marker"),
    ],
)
def test_project_dispositions_reconciles_markers_bidirectionally(
    tmp_path, report_marker, source_marker
):
    report = _full_report(report_marker)
    source = _full_chunks(source_marker)
    source[0][1][0]["m"][0]["d"] = -10

    projected = project_dispositions(report, source)
    projected_mismatch = projected[0][1][0]["m"][0]
    assert projected_mismatch["d"] == 10
    assert source[0][1][0]["m"][0]["d"] == -10
    if report_marker is None:
        assert "e" not in projected_mismatch
        assert source[0][1][0]["m"][0]["e"] == source_marker
    else:
        assert projected_mismatch["e"] == report_marker
        assert "e" not in source[0][1][0]["m"][0]

    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report))
    assert (
        _validate_projection(
            report_path,
            report,
            report["suite"],
            projected,
        )
        == "full"
    )


def test_project_dispositions_derives_exact_match_rate_endpoint():
    report = _full_report(None)
    report["mismatches"] = []
    source = _full_chunks(None)
    row = source[0][1][0]
    row["r"] = 99.9999995
    row["v"] = [{"c": CONCEPT, "l": 10, "x": 10}]
    row["m"] = []

    projected = project_dispositions(report, source)

    assert projected[0][1][0]["r"] == 100.0
    assert source[0][1][0]["r"] == 99.9999995


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        pytest.param("duplicate", "repeats concept", id="duplicate-mismatch"),
        pytest.param("overlap", "appears in both", id="match-mismatch-overlap"),
    ],
)
def test_project_dispositions_rejects_duplicate_or_overlapping_concepts(
    mutation, message
):
    report = _full_report(None)
    chunks = _full_chunks(None)
    row = chunks[0][1][0]
    if mutation == "duplicate":
        row["m"].append(copy.deepcopy(row["m"][0]))
    else:
        row["v"].append(
            {
                "c": CONCEPT,
                "l": 10,
                "x": 10,
                "d": 0,
            }
        )

    with pytest.raises(ValueError, match=message):
        project_dispositions(report, chunks)


def test_validate_projection_rejects_same_id_foreign_values(tmp_path):
    report = _full_report("explained_residual")
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report))
    chunks = _full_chunks("explained_residual")
    chunks[0][1][0]["m"][0]["x"] = 999

    with pytest.raises(
        ValueError,
        match=r"right value 999 .*does not reconcile",
    ):
        _validate_projection(
            report_path,
            report,
            report["suite"],
            chunks,
        )


def test_qc_like_cardinality_rows_use_the_same_projection_path(tmp_path):
    report = {
        "suite": "qc-like-suite",
        "case_count": 2,
        "cases": [],
        "mismatches": [],
        "summary": {
            "comparison_count": 2,
            "match_count": 2,
            "mismatch_count": 0,
        },
    }
    chunks = [
        (
            "chunk-0.json",
            [
                {"id": "qc-1", "r": None, "h": {}, "m": []},
                {"id": "qc-2", "r": None, "h": {}, "m": []},
            ],
        )
    ]

    projected = project_dispositions(report, chunks)
    assert projected == chunks

    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report))
    assert (
        _validate_projection(
            report_path,
            report,
            report["suite"],
            projected,
        )
        == "cardinality"
    )
