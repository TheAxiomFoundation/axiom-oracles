from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from axiom_oracles.adapters.taxsim.projection import TAXSIM_MAX_YEAR, _year


DOCUMENTATION = Path(__file__).parents[1] / "docs" / "policyengine-taxsim.md"


def _section(heading: str) -> str:
    text = DOCUMENTATION.read_text().split(heading, maxsplit=1)[1]
    return " ".join(text.split("\n## ", maxsplit=1)[0].split())


def test_binary_probe_documentation_qualifies_unrun_windows() -> None:
    section = _section("## Platforms and binary identity")

    assert "Each was run" not in section
    assert "Windows was not run; its law-year range is unknown" in section


@given(st.integers(min_value=TAXSIM_MAX_YEAR + 1, max_value=2100))
def test_projection_error_limits_support_claim_to_binaries_run(year: int) -> None:
    with pytest.raises(RuntimeError) as exc:
        _year(str(year))

    message = str(exc.value)
    assert "Among pinned TAXSIM executables that have been run" in message
    assert "Windows law-year range is unknown" in message


def test_historical_binary_experiments_are_attributed_without_new_receipts() -> None:
    section = _section("### Why the pin was not moved for Linux")

    assert "recorded by the original author" in section
    assert "not re-run for these fixes" in section
    assert "19-wheel investigation" in section
    assert "row and column counts" in section
    assert "child-credit probes" in section


def test_historical_smoke_numbers_are_attributed_without_new_receipts() -> None:
    section = _section("## Reproduce The Smoke Test")

    assert "recorded by the original author" in section
    assert "not re-run for these fixes" in section
    assert "Linux smoke" in section
