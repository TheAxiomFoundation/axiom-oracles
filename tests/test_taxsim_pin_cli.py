"""`compare` hands the resolved TAXSIM pin profile to the runner and preflight."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from click.testing import CliRunner

from axiom_oracles.adapters.policyengine import PolicyEngineTaxsimRunner
from axiom_oracles.adapters.taxsim import TaxsimPackageRunner, pins

FIXTURE = Path(__file__).parent / "fixtures" / "taxsim_csv" / "cps_households_sample.csv"
FEDERAL = "us:tax/federal-income-tax#liability"


class _Echo:
    """A runner protocol stand-in that answers every row with a constant."""

    def __init__(self, frame, value: float) -> None:
        self.frame = frame
        self.value = value

    def run(self, show_progress: bool = False):
        del show_progress
        return [
            {"taxsimid": row["taxsimid"], "fiitax": self.value, "income_tax": self.value}
            for row in self.frame.to_dict(orient="records")
        ]


@pytest.fixture
def recorded(monkeypatch):
    cli = importlib.import_module("axiom_oracles.cli")
    calls = {"runner": [], "preflight": []}

    def build_runner(engine, *args, **kwargs):
        if engine == "taxsim":
            calls["runner"].append(kwargs.get("taxsim_pin_profile"))
            return TaxsimPackageRunner(runner_factory=lambda frame: _Echo(frame, 1.0))
        return PolicyEngineTaxsimRunner(runner_factory=lambda frame: _Echo(frame, 2.0))

    monkeypatch.setattr(cli, "_build_runner", build_runner)
    monkeypatch.setattr(
        cli,
        "_require_taxsim_law_year",
        lambda period, profile=None: calls["preflight"].append((period, profile)),
    )
    monkeypatch.delenv(pins.PROFILE_ENV, raising=False)
    return cli, calls


def _compare(cli, *extra, env=None):
    return CliRunner().invoke(
        cli.cli,
        [
            "compare",
            "policyengine",
            "taxsim",
            "--population",
            "taxsim-csv",
            "--taxsim-csv",
            str(FIXTURE),
            "--concept",
            FEDERAL,
            "--period",
            "2021",
            *extra,
        ],
        env=env,
    )


def test_compare_passes_the_flag_to_the_runner_and_the_preflight(recorded) -> None:
    cli, calls = recorded
    run = _compare(cli, "--taxsim-pin-profile", "dashboard-2026-09")
    assert run.exit_code == 0, run.output
    assert calls["preflight"] == [("2021", "dashboard-2026-09")]
    assert calls["runner"] == ["dashboard-2026-09"]


def test_compare_passes_the_env_profile_when_no_flag_is_given(recorded) -> None:
    cli, calls = recorded
    run = _compare(cli, env={pins.PROFILE_ENV: "pe-taxsim-main-2026-08"})
    assert run.exit_code == 0, run.output
    assert calls["preflight"] == [("2021", "pe-taxsim-main-2026-08")]
    assert calls["runner"] == ["pe-taxsim-main-2026-08"]


def test_compare_passes_the_default_profile_by_name(recorded) -> None:
    cli, calls = recorded
    run = _compare(cli)
    assert run.exit_code == 0, run.output
    default = pins.pin_document().default_profile
    assert calls["preflight"] == [("2021", default)]
    assert calls["runner"] == [default]


def test_build_runner_gives_the_taxsim_runner_its_profile() -> None:
    cli = importlib.import_module("axiom_oracles.cli")
    runner = cli._build_runner(
        "taxsim", "rules", None, None, (), taxsim_pin_profile="dashboard-2026-09"
    )
    assert isinstance(runner, TaxsimPackageRunner)
    assert runner.pin_profile == "dashboard-2026-09"
    assert runner.resolved_pin_profile() == "dashboard-2026-09"
