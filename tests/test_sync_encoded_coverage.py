from scripts.sync_encoded_coverage import classify


def test_ohio_bounded_income_tax_schedule_is_classified() -> None:
    assert classify(
        "us-oh/policies/income_tax/pilot_liability_pipeline.yaml"
    ) == ("state_income_tax", "OH")
