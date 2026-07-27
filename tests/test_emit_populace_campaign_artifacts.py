import pytest

from scripts.emit_populace_campaign_artifacts import project_state


def _campaign() -> dict:
    return {
        "generated_at": "2026-07-26T12:00:00Z",
        "run_kind": "manual",
        "dataset_identity": {
            "source": "pinned",
            "revision": "populace-us-test",
            "sha256": "3" * 12,
            "built_with": "1.729.0",
            "country": "us",
        },
        "runtime_provenance": {
            "rulespec": {
                "repository": "TheAxiomFoundation/rulespec-us",
                "commit": "1" * 40,
                "working_tree": "clean",
            },
            "axiom_engine": {
                "repository": "TheAxiomFoundation/axiom-rules-engine",
                "commit": "2" * 40,
                "executable_sha256": "4" * 64,
                "working_tree": "clean",
            },
            "packages": {
                "policyengine": "4.18.9",
                "policyengine-us": "1.752.2",
            },
        },
    }


def test_connecticut_dashboard_description_names_narrow_component():
    output = (
        "us-ct:policies/income_tax/"
        "2026_resident_ordinary_tax_before_personal_credit"
        "#ct_pit_2026_resident_ordinary_tax_before_personal_credit"
    )
    report = project_state(
        "CT",
        {
            "compared_count": 1,
            "mismatch_count": 0,
            "output": output,
            "program": output.split("#", 1)[0],
            "policyengine_target": (
                "ct_resident_ordinary_tax_before_personal_credit_derived"
            ),
        },
        _campaign(),
        "campaign.json",
    )

    description = report["aggregates"][0]["description"]
    assert "ordinary section 12-700 tax before the personal credit" in description
    assert description != (
        "State income tax liability over every routed tax unit in the "
        "pinned US Populace"
    )


def test_georgia_dashboard_description_names_narrow_component():
    output = (
        "us-ga:policies/income_tax/"
        "2026_annual_tax_before_nonrefundable_credits"
        "#ga_pit_2026_annual_tax_before_nonrefundable_credits"
    )
    report = project_state(
        "GA",
        {
            "compared_count": 1,
            "mismatch_count": 0,
            "output": output,
            "program": output.split("#", 1)[0],
            "policyengine_target": "ga_income_tax_before_non_refundable_credits",
        },
        _campaign(),
        "campaign.json",
    )

    description = report["aggregates"][0]["description"]
    assert "section 48-7-20 annual tax before nonrefundable credits" in description
    assert "caller-supplied completed Georgia taxable net income" in description
    assert "liability" not in description.lower()


def test_projected_report_carries_standard_rulespec_provenance():
    report = project_state(
        "CT",
        {
            "compared_count": 1,
            "mismatch_count": 0,
            "output": "us-ct:policies/income_tax/example#output",
            "program": "us-ct:policies/income_tax/example",
            "policyengine_target": "ct_example",
        },
        _campaign(),
        "campaign.json",
    )

    provenance = report["provenance"]
    assert provenance["schema"] == "axiom_oracles.provenance.v1"
    assert provenance["generated_at"] == "2026-07-26T12:00:00Z"
    assert provenance["run_kind"] == "manual"
    assert provenance["rulespecs"] == [
        {
            "repo": "TheAxiomFoundation/rulespec-us",
            "sha": "1" * 40,
        }
    ]


@pytest.mark.parametrize("missing", ["generated_at", "run_kind"])
def test_projector_fails_closed_on_missing_campaign_run_provenance(missing):
    campaign = _campaign()
    campaign.pop(missing)
    with pytest.raises(ValueError, match=missing):
        project_state(
            "CT",
            {
                "compared_count": 1,
                "mismatch_count": 0,
                "output": "us-ct:policies/income_tax/example#output",
                "program": "us-ct:policies/income_tax/example",
                "policyengine_target": "ct_example",
            },
            campaign,
            "campaign.json",
        )


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("rulespec", "working_tree"),
        ("axiom_engine", "executable_sha256"),
        ("axiom_engine", "working_tree"),
        ("packages", "policyengine-us"),
    ],
)
def test_projector_fails_closed_on_incomplete_runtime_identity(section, field):
    campaign = _campaign()
    campaign["runtime_provenance"][section].pop(field)
    with pytest.raises(ValueError, match=field):
        project_state(
            "CT",
            {
                "compared_count": 1,
                "mismatch_count": 0,
                "output": "us-ct:policies/income_tax/example#output",
                "program": "us-ct:policies/income_tax/example",
                "policyengine_target": "ct_example",
            },
            campaign,
            "campaign.json",
        )


@pytest.mark.parametrize(
    ("container", "section", "field"),
    [
        ("runtime_provenance", "rulespec", "commit"),
        ("runtime_provenance", "axiom_engine", "executable_sha256"),
        ("runtime_provenance", "packages", "policyengine-us"),
        ("dataset_identity", None, "sha256"),
    ],
)
def test_projector_rejects_non_string_identity(container, section, field):
    campaign = _campaign()
    identity = campaign[container]
    if section is not None:
        identity = identity[section]
    identity[field] = True

    with pytest.raises(ValueError, match=field):
        project_state(
            "CT",
            {
                "compared_count": 1,
                "mismatch_count": 0,
                "output": "us-ct:policies/income_tax/example#output",
                "program": "us-ct:policies/income_tax/example",
                "policyengine_target": "ct_example",
            },
            campaign,
            "campaign.json",
        )


@pytest.mark.parametrize("field", ["source", "built_with", "country"])
def test_projector_fails_closed_on_incomplete_dataset_identity(field):
    campaign = _campaign()
    campaign["dataset_identity"].pop(field)
    with pytest.raises(ValueError, match=field):
        project_state(
            "CT",
            {
                "compared_count": 1,
                "mismatch_count": 0,
                "output": "us-ct:policies/income_tax/example#output",
                "program": "us-ct:policies/income_tax/example",
                "policyengine_target": "ct_example",
            },
            campaign,
            "campaign.json",
        )


def test_reprojection_is_deterministic_and_preserves_campaign_time():
    entry = {
        "compared_count": 1,
        "mismatch_count": 0,
        "output": "us-ct:policies/income_tax/example#output",
        "program": "us-ct:policies/income_tax/example",
        "policyengine_target": "ct_example",
    }
    first = project_state("CT", entry, _campaign(), "campaign.json")
    second = project_state("CT", entry, _campaign(), "campaign.json")

    assert first == second
    assert first["provenance"]["generated_at"] == "2026-07-26T12:00:00Z"
