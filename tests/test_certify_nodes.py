from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "certify_nodes.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("_test_certify_nodes", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


certify_nodes = _load_module()


@pytest.fixture(scope="module")
def generated():
    return certify_nodes.build_outputs(ROOT, as_of="2026-08-20")


def test_real_registry_drives_five_exact_graph_candidates(generated) -> None:
    ledger_text, refusal_text, results = generated
    assert [row["node"] for row in results] == [
        "dk:statutes/composed/boerne-og-ungeydelse-pipeline#single_recipient_annual_child_youth_benefit",
        "dk:statutes/composed/boerne-og-ungeydelse-couple-pipeline#couple_recipient_annual_child_youth_benefit",
        "us-co:regulations/10-ccr-2506-1/4.207.2#snap_allotment",
        "us:statutes/7/2014/e/6/A#snap_net_income",
        "us-co:policies/cdhs/snap/fy-2026-benefit-calculation#snap_eligible",
    ]
    assert all(row["membership"]["holds"] for row in results)
    assert all(not row["certified"] for row in results)

    ledger = yaml.safe_load(ledger_text)
    assert ledger == {
        "schema": "axiom.certified_nodes.v1",
        "generated": True,
        "as_of": "2026-08-20",
        "nodes": [],
    }
    assert isinstance(ledger["as_of"], str)

    sidecar = json.loads(refusal_text)
    assert sidecar["format"] == "axiom-validation-evidence/1"
    assert sidecar["schema"] == "axiom_oracles.node_certification_refusals.v1"
    assert sidecar["summary"] == {
        "candidates": 5,
        "certified": 0,
        "refused": 5,
        "by_program": {
            "dk/boerne-og-ungeydelse": {
                "candidates": 2,
                "certified": 0,
                "refused": 2,
            },
            "us-co/snap": {
                "candidates": 3,
                "certified": 0,
                "refused": 3,
            },
        },
        "refusal_codes": {
            "closed.computed_open": 3,
            "executable.release_receipt_missing": 3,
            "exercised.computed_false": 3,
            "provision_rooted.producer_missing": 5,
        },
    }
    assert len(sidecar["entries"]) == 5
    assert {row["legal_id"] for row in sidecar["entries"]} == {
        row["node"] for row in results
    }
    assert all(
        row["oracle"] and row["evidence"] and row["shortfall"]
        for row in sidecar["entries"]
    )


def test_registry_certified_program_without_engine_136_provenance_refuses(
    generated,
) -> None:
    """Required mutant: program green cannot manufacture node provenance."""

    _, _, results = generated
    dk = [row for row in results if row["program"] == "dk/boerne-og-ungeydelse"]
    assert len(dk) == 2
    for row in dk:
        assert row["program_certificate"]["state"] == "yes"
        assert row["program_certificate"]["value"] is True
        assert all(
            row["criteria"][name]["holds"]
            for name in ("conformant", "exercised", "closed", "executable")
        )
        assert row["criteria"]["provision_rooted"]["holds"] is False
        assert row["refusals"] == [
            {
                "criterion": "provision_rooted",
                "code": "provision_rooted.producer_missing",
                "producer": "TheAxiomFoundation/axiom-rules-engine#136",
                "message": (
                    "the compiled node carries no engine #136 provision "
                    "provenance annotation"
                ),
            }
        ]

    criterion, refusal = certify_nodes.assess_provision_rooted(
        {"corpus_citation_path": "a/real/path"}
    )
    assert criterion["holds"] is False
    assert refusal["code"] == "provision_rooted.producer_missing"


def test_source_reproduction_offered_where_release_tier_required_refuses() -> None:
    """Required mutant: source replay is not a published-release receipt."""

    criterion, refusal = certify_nodes.assess_executable_tier(
        "release_receipt",
        "source_reproduction",
        {"artifact": "mutant-source-reproduction.json"},
    )
    assert criterion == {
        "holds": False,
        "evidence": {
            "artifact": "mutant-source-reproduction.json",
            "required_tier": "release_receipt",
            "offered_tier": "source_reproduction",
        },
    }
    assert refusal["code"] == "executable.tier_insufficient"
    assert refusal["producer"] == "TheAxiomFoundation/axiom-oracles#461"


def test_executable_receipt_families_have_distinct_labels(generated) -> None:
    assert (
        certify_nodes.recognize_executable_tier(
            "scripts/executable_reproduction.py",
            "axiom_oracles.executable_reproduction.v1",
        )
        == "source_reproduction"
    )
    assert (
        certify_nodes.recognize_executable_tier(
            "axiom_oracles/executable_receipt.py",
            "axiom_oracles.executable_receipt.v1",
        )
        == "release_receipt"
    )
    assert (
        certify_nodes.recognize_executable_tier(
            "scripts/executable_reproduction.py",
            "axiom_oracles.executable_receipt.v1",
        )
        is None
    )

    _, _, results = generated
    dk = [row for row in results if row["program"] == "dk/boerne-og-ungeydelse"]
    co = [row for row in results if row["program"] == "us-co/snap"]
    assert {tuple(row["executable_tier"].values()) for row in dk} == {
        ("source_reproduction", "source_reproduction")
    }
    assert {tuple(row["executable_tier"].values()) for row in co} == {
        ("release_receipt", None)
    }


def test_co_uses_computed_universes_not_legacy_certificate_attestation(
    generated,
) -> None:
    _, _, results = generated
    co = [row for row in results if row["program"] == "us-co/snap"]
    assert len(co) == 3
    for row in co:
        closure = row["criteria"]["closed"]
        assert closure["holds"] is False
        assert closure["evidence"]["producer"] == "scripts/closure_universe.py"
        assert closure["evidence"]["root_count"] == 3
        assert closure["evidence"]["provision_count"] == 1156
        assert closure["evidence"]["pending_count"] == 290
        assert closure["evidence"]["certificate_attestation_ignored"] is True


def test_comparison_aliases_are_not_silently_promoted_to_graph_nodes() -> None:
    registry, _ = certify_nodes.load_candidate_registry(ROOT)
    config = registry["programs"]["us-co/snap"]["membership"]
    for alias in (
        "us:statutes/7/2014/u#snap_benefit",
        "us:statutes/7/2014/o#snap_eligible",
    ):
        holds, _, _, refusal = certify_nodes._membership(
            ROOT,
            "us-co/snap",
            alias,
            config,
        )
        assert holds is False
        assert refusal["code"] == "program_subgraph.membership_unavailable"


def test_committed_generated_outputs_are_exact(generated) -> None:
    ledger_text, refusal_text, _ = generated
    assert (ROOT / "certified-nodes.yaml").read_text() == ledger_text
    assert (ROOT / "certified-node-refusals.json").read_text() == refusal_text

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "5 candidates, 0 certified" in result.stdout


def _js_yaml_package(foundation: Path) -> Path | None:
    configured = os.environ.get("AXIOM_JS_YAML_PACKAGE")
    candidates = [
        Path(configured) if configured else None,
        foundation / "atlas-viewer" / "node_modules" / "js-yaml",
        foundation / "axiom-foundation.org" / "node_modules" / "js-yaml",
        foundation / "axiom.org" / "node_modules" / "js-yaml",
    ]
    return next((path for path in candidates if path and path.is_dir()), None)


def test_real_mirror_script_round_trip_parity(tmp_path: Path) -> None:
    """Required parity mutant: run the downstream script on our bytes twice."""

    foundation = ROOT.parents[2]
    api_script = foundation / "axiom-api" / "scripts" / "mirror-certified-nodes.mjs"
    js_yaml = _js_yaml_package(foundation)
    if not api_script.is_file() or js_yaml is None:
        pytest.skip("axiom-api mirror or an installed js-yaml package is unavailable")

    scripts = tmp_path / "scripts"
    modules = tmp_path / "node_modules"
    scripts.mkdir()
    modules.mkdir()
    copied_script = scripts / api_script.name
    shutil.copy2(api_script, copied_script)
    (modules / "js-yaml").symlink_to(js_yaml, target_is_directory=True)
    assert copied_script.read_bytes() == api_script.read_bytes()

    source = ROOT / "certified-nodes.yaml"
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    outputs = [tmp_path / "ledger-a.json", tmp_path / "ledger-b.json"]
    for output in outputs:
        result = subprocess.run(
            [
                "node",
                str(copied_script),
                "--source",
                str(source),
                "--out",
                str(output),
            ],
            cwd=tmp_path,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert "Mirrored 0 certified nodes" in result.stdout
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before

    doc = yaml.safe_load(source.read_text())
    a = json.loads(outputs[0].read_text())
    b = json.loads(outputs[1].read_text())
    assert a["format"] == "axiom-certified-ledger/1"
    assert a["ledger_id"] == f"ops-certified-nodes@{doc['as_of']}"
    assert a["fixture"] is False
    assert a["entries"] == []
    assert a["vintage"] == {
        "encoding_release": "unreleased",
        "engine_release": "unreleased",
        "corpus_release": "unreleased",
    }
    a.pop("issued_at")
    b.pop("issued_at")
    assert a == b
