import copy
import json
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts import de_axiom_legs as legs


PINNED_COMMIT = "d83ba3db30e2f63376aacf822d116687589b8564"
PINNED_TREE = "1e75a045e32100544f057ffe335065c1ef99c1bc"
ESTG_MODULE = "de/statutes/estg/66.yaml"
ESTG_MANIFEST = ".axiom/encoding-manifests/de/statutes/estg/66.json"
SGB_MODULE = "de/statutes/sgb-5/241.yaml"
SGB_MANIFEST = ".axiom/encoding-manifests/de/statutes/sgb-5/241.json"


def _pending_inspection(_oracle, *, rulespec_root=None):
    del rulespec_root
    return {
        "repository": legs.RULESPEC_REPOSITORY,
        "commit": PINNED_COMMIT,
        "tree": PINNED_TREE,
        "inspection_mode": "git-object-database-exact-ref",
        "checkout_head_ignored": True,
        "artifacts": [
            {"path": ESTG_MANIFEST, "presence": legs.PENDING_MARKER},
            {
                "path": SGB_MANIFEST,
                "presence": "on-pinned-ref",
                "sha256": "2" * 64,
            },
            {"path": ESTG_MODULE, "presence": legs.PENDING_MARKER},
            {
                "path": SGB_MODULE,
                "presence": "on-pinned-ref",
                "sha256": "3" * 64,
            },
        ],
        "claim_mode": "computed",
    }


@pytest.mark.parametrize("oracle", ["euromod", "gettsim"])
def test_pending_pair_is_one_tuple_with_six_nonconformant_views(monkeypatch, oracle):
    monkeypatch.setattr(legs, "inspect_pinned_ref", _pending_inspection)

    record = legs.build(oracle)

    assert record["record_schema"] == "axiom.unified_comparison_record.v1"
    assert record["suite"] == f"de-worker-dual-oracle-axiom-{oracle}"
    assert record["state"] == "leg-pending"
    assert record["pending"] == "module-not-on-main"
    assert record["engines"] == {"left": oracle, "right": "axiom"}
    assert record["tuple"]["jurisdiction"] == "de"
    assert record["tuple"]["oracle"]["id"] == oracle
    assert "oracles" not in record["tuple"]
    assert record["tuple"]["population"]["case_count"] == 13
    assert record["tuple"]["rulespec"]["commit"] == PINNED_COMMIT
    assert record["tuple"]["rulespec"]["tree"] == PINNED_TREE
    assert len(record["cases"]) == 13
    assert len(record["views"]) == 6
    assert all(
        view["state"] == "leg-pending"
        and view["pending"] == "module-not-on-main"
        and view["dependency_set"]["complete_on_pinned_ref"] is False
        for view in record["views"].values()
    )
    # Pending records bind only population inputs and dependency evidence.
    # They contain no fabricated comparisons or zero-valued output rows.
    assert "aggregates" not in record
    assert "summary" not in record
    assert all("matches" not in case and "mismatches" not in case for case in record["cases"])


def test_sgb_5_241_is_only_an_available_partial_health_dependency(monkeypatch):
    monkeypatch.setattr(legs, "inspect_pinned_ref", _pending_inspection)

    record = legs.build("euromod")
    health = record["views"]["de/health-insurance"]

    assert health["dependency_set"]["available_partial_dependencies"] == [
        SGB_MODULE,
        SGB_MANIFEST,
    ]
    artifact = health["dependency_set"]["artifacts"][0]
    assert artifact["nodes"] == [
        "de:statutes/sgb-5/241#general_contribution_rate"
    ]
    assert artifact["dependency_status"] == "available-partial"
    assert health["state"] == "leg-pending"


def test_pending_validator_rederives_and_rejects_marker_mutant(monkeypatch):
    monkeypatch.setattr(legs, "inspect_pinned_ref", _pending_inspection)
    record = legs.build("gettsim")
    assert legs.validate(copy.deepcopy(record), "gettsim") == record

    mutant = copy.deepcopy(record)
    mutant["views"]["de/kindergeld"]["pending"] = "conformant"
    with pytest.raises(legs.DEAxiomLegError, match="differs from exact pinned-ref"):
        legs.validate(mutant, "gettsim")


def test_module_present_can_never_be_emitted_as_module_not_on_main(monkeypatch):
    present = _pending_inspection("euromod")
    for artifact in present["artifacts"]:
        artifact["presence"] = "on-pinned-ref"
        artifact["sha256"] = "4" * 64
    monkeypatch.setattr(
        legs,
        "inspect_pinned_ref",
        lambda _oracle, *, rulespec_root=None: present,
    )

    with pytest.raises(
        legs.DEAxiomLegError,
        match="execution-environment-unavailable.*refusing to emit",
    ):
        legs.build("euromod")


def test_registry_configs_pin_exact_ref_and_fail_loud_names():
    for oracle, path in legs.CONFIG_PATHS.items():
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
        params = config["runner"]["parameters"]
        canonical = f"comparisons/de-worker-dual-oracle/axiom-{oracle}.json"
        assert path.stem == config["name"] == f"de-worker-dual-oracle-axiom-{oracle}"
        assert config["runner"]["type"] == "de-axiom-oracle-compare"
        assert params["rulespec_upstream_sha"] == PINNED_COMMIT
        assert params["rulespec_upstream_tree"] == PINNED_TREE
        assert config["artifacts"]["canonical_record"] == canonical
        assert config["selector"]["report"] == canonical


def test_registered_runner_writes_pending_without_engine_or_oracle(monkeypatch, tmp_path):
    monkeypatch.setattr(legs, "inspect_pinned_ref", _pending_inspection)
    config = yaml.safe_load(legs.CONFIG_PATHS["euromod"].read_text(encoding="utf-8"))
    runner = copy.deepcopy(config["runner"])
    output = tmp_path / "leg.json"

    record = legs.run_registered_leg(runner, output)

    assert json.loads(output.read_text(encoding="utf-8")) == record
    assert runner["parameters"]["_verified_rulespec_upstream_sha"] == PINNED_COMMIT
    assert record["pending"] == "module-not-on-main"


def test_live_bundle_dispatches_all_pinned_execution_inputs(monkeypatch, tmp_path):
    """The signed-ref transition must reach the released-engine producer."""

    archive = tmp_path / "engine.tar.xz"
    public_key = tmp_path / "apply-public-key"
    euromod_python = tmp_path / "euromod-python"
    model_root = tmp_path / "euromod-model"
    rulespec_root = tmp_path / "rulespec-de"
    for path in (archive, public_key, euromod_python):
        path.write_bytes(b"fixture")
    model_root.mkdir()
    rulespec_root.mkdir()
    observed = []

    class ExecutableProducer:
        @staticmethod
        def produce(**kwargs):
            observed.append(kwargs)

    monkeypatch.setattr(
        legs.importlib,
        "import_module",
        lambda name: (
            ExecutableProducer
            if name == "scripts.de_executable"
            else pytest.fail(f"unexpected module import {name}")
        ),
    )

    legs._produce_live_bundle(
        {
            "engine_archive": str(archive),
            "signing_public_key": str(public_key),
            "euromod_model_root": str(model_root),
            "euromod_python": str(euromod_python),
        },
        rulespec_root,
    )

    assert observed == [
        {
            "engine_archive": archive.resolve(),
            "rulespec_root": rulespec_root,
            "signing_public_key": public_key.resolve(),
            "euromod_model_root": model_root.resolve(),
            "euromod_python": euromod_python.resolve(),
        }
    ]


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_exact_ref_inspection_ignores_checkout_head(monkeypatch, tmp_path):
    repo = tmp_path / "rulespec-de"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    sgb = repo / SGB_MODULE
    sgb.parent.mkdir(parents=True)
    sgb.write_text("format: rulespec/v1\nrules: {}\n", encoding="utf-8")
    _git(repo, "add", SGB_MODULE)
    _git(
        repo,
        "-c",
        "user.name=DE leg test",
        "-c",
        "user.email=de-leg@example.test",
        "commit",
        "--quiet",
        "-m",
        "pinned without estg",
    )
    pinned_commit = _git(repo, "rev-parse", "HEAD")
    pinned_tree = _git(repo, "rev-parse", "HEAD^{tree}")

    estg = repo / ESTG_MODULE
    manifest = repo / ESTG_MANIFEST
    estg.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)
    estg.write_text("format: rulespec/v1\nrules: {}\n", encoding="utf-8")
    manifest.write_text("{}\n", encoding="utf-8")
    _git(repo, "add", ESTG_MODULE, ESTG_MANIFEST)
    _git(
        repo,
        "-c",
        "user.name=DE leg test",
        "-c",
        "user.email=de-leg@example.test",
        "commit",
        "--quiet",
        "-m",
        "moving head has estg",
    )

    plan = legs._load_plan()
    config = {
        "runner": {"parameters": {"rulespec_root": str(repo)}}
    }
    monkeypatch.setattr(
        legs,
        "_shared_contract",
        lambda _oracle: (plan, config, pinned_commit, pinned_tree),
    )

    inspection = legs.inspect_pinned_ref("euromod", rulespec_root=repo)
    observed = {row["path"]: row for row in inspection["artifacts"]}
    assert inspection["commit"] == pinned_commit
    assert inspection["tree"] == pinned_tree
    assert inspection["checkout_head_ignored"] is True
    assert observed[ESTG_MODULE]["presence"] == "module-not-on-main"
    assert observed[ESTG_MANIFEST]["presence"] == "module-not-on-main"
    assert observed[SGB_MODULE]["presence"] == "on-pinned-ref"
