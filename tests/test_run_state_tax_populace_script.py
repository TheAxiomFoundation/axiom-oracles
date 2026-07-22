from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from axiom_oracles.bridges.state_tax_populace_runner import (
    DISPOSITION_BLOCKED,
    DISPOSITION_READY,
    TaxUnitRoute,
)
import scripts.run_state_tax_populace as campaign


def _contract():
    jurisdictions = {
        "CA": SimpleNamespace(status="blocked"),
        "NJ": SimpleNamespace(status="ready"),
        "NM": SimpleNamespace(status="ready"),
    }
    return SimpleNamespace(
        validation_year=2026,
        populace_year=2024,
        by_state=lambda: jurisdictions,
    )


@pytest.mark.parametrize(
    ("state", "error"),
    [
        ("XX", "unknown campaign state abbreviation.*XX"),
        ("ca", "requested campaign state.*not ready: CA"),
    ],
)
def test_invalid_requested_state_fails_before_dataset_load(
    monkeypatch, tmp_path, state: str, error: str
) -> None:
    monkeypatch.setattr(campaign, "load_state_tax_populace_contract", _contract)

    def reject_dataset_load(*args, **kwargs):
        pytest.fail("invalid state should fail before the dataset is loaded")

    monkeypatch.setattr(campaign, "load_populace_dataset", reject_dataset_load)

    with pytest.raises(SystemExit, match=error):
        campaign.main(
            [
                "--state",
                state,
                "--rulespec-root",
                str(tmp_path),
                "--axiom-rules-path",
                str(tmp_path),
                "--output",
                str(tmp_path / "report.json"),
            ]
        )


def test_repeatable_state_filter_preserves_national_routing_report(
    monkeypatch, tmp_path
) -> None:
    routes = (
        TaxUnitRoute(1, 1, "NJ", "34", 1, DISPOSITION_READY),
        TaxUnitRoute(2, 2, "NM", "35", 1, DISPOSITION_READY),
        TaxUnitRoute(3, 3, "CA", "06", 1, DISPOSITION_BLOCKED),
    )
    calls: dict[str, tuple[TaxUnitRoute, ...]] = {}

    monkeypatch.setattr(campaign, "load_state_tax_populace_contract", _contract)
    monkeypatch.setattr(campaign, "load_populace_dataset", lambda *a, **k: "dataset")
    monkeypatch.setattr(campaign, "validate_campaign_dataset_identity", lambda *a, **k: None)
    monkeypatch.setattr(campaign, "population_table", lambda dataset, table: table)
    monkeypatch.setattr(campaign, "route_tax_units", lambda **kwargs: routes)

    def targets(**kwargs):
        calls["targets"] = tuple(kwargs["routes"])
        return {"NJ": {1: 0.0}}

    def projections(**kwargs):
        calls["projections"] = tuple(kwargs["routes"])
        return {"NJ": {}}

    def routing_report(received_routes, **kwargs):
        calls["routing"] = tuple(received_routes)
        return {"scope": "national"}

    def comparison(**kwargs):
        calls["comparison"] = tuple(kwargs["routes"])
        calls["known_tax_unit_ids"] = set(kwargs["known_tax_unit_ids"])
        return {"scope": "filtered"}

    monkeypatch.setattr(campaign, "calculate_policyengine_targets", targets)
    monkeypatch.setattr(
        campaign, "calculate_policyengine_projection_inputs", projections
    )
    monkeypatch.setattr(campaign, "population_routing_report", routing_report)
    monkeypatch.setattr(campaign, "compare_ready_state_tax_units", comparison)
    monkeypatch.setattr(campaign, "runtime_provenance", lambda **kwargs: {})

    output = tmp_path / "report.json"
    assert campaign.main(
        [
            "--state",
            "nj",
            "--state",
            "NJ",
            "--rulespec-root",
            str(tmp_path),
            "--axiom-rules-path",
            str(tmp_path),
            "--output",
            str(output),
        ]
    ) == 0

    report = json.loads(output.read_text())
    assert report["requested_states"] == ["NJ"]
    assert report["routing"] == {"scope": "national"}
    assert report["comparison"] == {"scope": "filtered"}
    assert calls["routing"] == routes
    expected_filtered = (routes[0],)
    assert calls["targets"] == expected_filtered
    assert calls["projections"] == expected_filtered
    assert calls["comparison"] == expected_filtered
    assert calls["known_tax_unit_ids"] == {1, 2, 3}
