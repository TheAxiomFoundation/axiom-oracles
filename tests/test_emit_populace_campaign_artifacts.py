from scripts.emit_populace_campaign_artifacts import project_state


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
        {},
        "campaign.json",
    )

    description = report["aggregates"][0]["description"]
    assert "ordinary section 12-700 tax before the personal credit" in description
    assert description != (
        "State income tax liability over every routed tax unit in the "
        "pinned US Populace"
    )
