from pathlib import Path

import yaml


COMPARISONS_DIR = Path(__file__).resolve().parent.parent / "comparisons"


def test_dk_2023_child_youth_benefit_registry_config_shape() -> None:
    """Pin the DK_2023 oracle year and composed-pipeline date workaround."""

    config = yaml.safe_load(
        (COMPARISONS_DIR / "dk-child-youth-benefit-2023-euromod.yaml").read_text()
    )
    params = config["runner"]["parameters"]
    assert config["runner"]["type"] == "euromod-synthetic-compare"
    assert config["runner"]["axiom_rules_repo"].endswith(
        "/_worktrees/axiom-rules-engine-pin"
    )
    assert params["suite"] == "dk-child-youth-benefit-2023"
    assert str(params["period"]) == "2025-06-01"
    assert params["euromod_country"] == "DK"
    assert params["euromod_system"] == "DK_2023"
    assert params["euromod_dataset"] == "DK_training_data"
    assert config["dashboard"]["filename"] == (
        "axiom-euromod-dk-child-youth-benefit-2023.json"
    )
