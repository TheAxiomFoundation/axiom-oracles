from axiom_oracles.cli import _echo_comparison_report


def test_cli_report_output_omits_successful_cases(capsys) -> None:
    report = {
        "population": "enhanced-cps",
        "suite": "nyc-synthetic",
        "case_count": 2,
        "locales": [],
        "concepts": [{"id": "concept"}],
        "summary": {
            "comparison_count": 2,
            "mismatch_count": 1,
        },
        "cases": [
            {
                "case_id": "case-ok",
                "match_rate": 100,
                "mismatches": [],
            },
            {
                "case_id": "case-bad",
                "match_rate": 0,
                "mismatches": [
                    {
                        "description": "Benefit",
                        "left": 1,
                        "right": 2,
                    }
                ],
            },
        ],
    }

    _echo_comparison_report(report)

    output = capsys.readouterr().out
    assert "case-ok" not in output
    assert "case-bad" in output
    assert "Benefit: 1 != 2" in output
