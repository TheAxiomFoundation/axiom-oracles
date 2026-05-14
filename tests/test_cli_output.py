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


def test_cli_report_output_caps_mismatches_without_case_rows(capsys) -> None:
    report = {
        "population": "enhanced-cps",
        "suite": "tax",
        "case_count": 55,
        "locales": [],
        "concepts": [{"id": "concept"}],
        "summary": {
            "comparison_count": 55,
            "mismatch_count": 55,
        },
        "cases": [],
        "mismatches": [
            {
                "case_id": f"case-{index}",
                "description": "Benefit",
                "left": 1,
                "right": 2,
            }
            for index in range(55)
        ],
    }

    _echo_comparison_report(report)

    output = capsys.readouterr().out
    assert "case-49" in output
    assert "case-50" not in output
    assert "5 additional mismatches omitted" in output
