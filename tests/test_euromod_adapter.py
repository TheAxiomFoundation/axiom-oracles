"""EUROMOD-platform adapter: projection, subprocess contract, live engines.

The projection and subprocess-contract tests run everywhere. The live
tests execute real models and are gated on environment variables:

- ``UKMOD_MODEL_ROOT`` — a UKMOD checkout (e.g. ``UKMOD_PUBLIC_B2026.03``,
  openly downloadable from github.com/centreformicrosimulation/UKMOD-PUBLIC).
- ``EUROMOD_MODEL_ROOT_BE`` — a EUROMOD release directory (e.g.
  ``EUROMOD_RELEASES_J2.0+``, openly downloadable from the JRC).
- ``EUROMOD_PYTHON`` — the EUROMOD execution environment: an x86_64
  interpreter with the ``euromod`` connector and a .NET runtime
  (``DOTNET_ROOT``). On Apple Silicon this is a Rosetta venv.

The UKMOD assertions are hand-computed 2025-26 UK law. For a single
employee with annual gross G above the personal allowance (12,570) and
below the higher-rate threshold (50,270):

- income tax = (G - 12,570) x 20%
- employee NICs (class 1 main rate, post-January-2024) = (G - 12,570) x 8%

UKMOD's demo dataset uprates employment income from the data year to the
system year, so the expectation is computed against the engine's own
post-uprating gross (``yem``), not the raw input — that is exactly the
bridging discipline population comparisons will need.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from axiom_oracles.adapters.euromod import (
    DEFAULT_OUTPUTS,
    EuromodPlatformRunner,
    _runner as euromod_worker,
    euromod_input_rows,
)
from axiom_oracles.core.case import Case, Concepts, Entity

UKMOD_MODEL_ROOT = os.environ.get("UKMOD_MODEL_ROOT")
EUROMOD_MODEL_ROOT_BE = os.environ.get("EUROMOD_MODEL_ROOT_BE")
EUROMOD_PYTHON = os.environ.get("EUROMOD_PYTHON")
EUROMOD_DATASET_BE = os.environ.get("EUROMOD_DATASET_BE", "BE_training_data")
EUROMOD_TEMPLATE_DATASET_BE = os.environ.get(
    "EUROMOD_TEMPLATE_DATASET_BE", "BE_training_data"
)


def _single_earner(case_id: str, annual_income: float) -> Case:
    return Case(
        case_id=case_id,
        period="2025",
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 35,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.YEARLY_EARNED_INCOME: annual_income,
                },
            ),
        ),
        outputs=(Concepts.UK_INCOME_TAX,),
    )


class TestProjection:
    def test_single_earner_projects_monthly_amounts(self) -> None:
        rows = euromod_input_rows(
            _single_earner("case-1", 30_000.0),
            household_number=7,
            country_code=15,
        )
        assert len(rows) == 1
        row = rows[0]
        assert row["idhh"] == 7
        assert row["idperson"] == 701
        assert row["yem"] == pytest.approx(2_500.0)  # 30,000 / 12
        assert row["dag"] == 35
        assert row["dct"] == 15
        assert row["les"] == 3  # employed
        assert row["dms"] == 1  # single

    def test_annual_dataset_keeps_annual_amounts(self) -> None:
        rows = euromod_input_rows(
            _single_earner("case-1", 30_000.0),
            household_number=1,
            country_code=15,
            monthly_inputs=False,
        )
        assert rows[0]["yem"] == pytest.approx(30_000.0)

    def test_couple_links_partners_and_children_to_head(self) -> None:
        case = Case(
            case_id="family",
            period="2025",
            entities=(
                Entity(
                    entity_id="head",
                    kind="person",
                    facts={
                        Concepts.PERSON_AGE: 40,
                        Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                        Concepts.YEARLY_EARNED_INCOME: 48_000.0,
                    },
                ),
                Entity(
                    entity_id="spouse",
                    kind="person",
                    facts={
                        Concepts.PERSON_AGE: 39,
                        Concepts.HOUSEHOLD_RELATION: "Spouse",
                    },
                ),
                Entity(
                    entity_id="child",
                    kind="person",
                    facts={Concepts.PERSON_AGE: 8},
                ),
            ),
        )
        rows = euromod_input_rows(case, household_number=3, country_code=15)
        head, spouse, child = rows
        assert head["idpartner"] == spouse["idperson"]
        assert spouse["idpartner"] == head["idperson"]
        assert head["dms"] == 2 and spouse["dms"] == 2
        assert child["idmother"] == head["idperson"]
        assert child["idpartner"] == 0

    def test_explicit_rows_override_but_keep_assigned_household(self) -> None:
        case = Case(
            case_id="explicit",
            period="2025",
            metadata={"euromod_inputs": [{"idhh": 999, "yem": 1_234.0}]},
        )
        rows = euromod_input_rows(case, household_number=4, country_code=15)
        assert rows == [{"idhh": 4, "yem": 1_234.0}]

    def test_case_without_persons_or_rows_is_refused(self) -> None:
        with pytest.raises(ValueError, match="no person entities"):
            euromod_input_rows(
                Case(case_id="empty", period="2025"),
                household_number=1,
                country_code=15,
            )


class TestSubprocessContract:
    def test_policy_switch_patch_targets_named_system_only(self) -> None:
        xml = """
<CountryConfig>
  <System>
    <Name>BE_2024</Name>
    <Policy>
      <Name>bsaoa_be</Name>
      <Switch>off</Switch>
      <Function><Switch>on</Switch></Function>
    </Policy>
  </System>
  <System>
    <Name>BE_2025</Name>
    <Policy>
      <Name>bsaoa_be</Name>
      <Switch>off</Switch>
      <Function><Switch>on</Switch></Function>
    </Policy>
  </System>
</CountryConfig>
"""

        patched = euromod_worker._patch_policy_switches(
            xml,
            system="BE_2025",
            overrides=[("bsaoa_be", True)],
        )

        assert "<Name>BE_2024</Name>\n    <Policy>\n      <Name>bsaoa_be</Name>\n      <Switch>off</Switch>" in patched
        assert "<Name>BE_2025</Name>\n    <Policy>\n      <Name>bsaoa_be</Name>\n      <Switch>on</Switch>" in patched

    def test_results_group_by_case_and_annualize(self) -> None:
        payload = {
            "columns": ["tin_s"],
            "missing": [],
            "idhh": [1, 2, 2],
            "values": {"tin_s": [290.5, 100.0, 50.0]},
        }

        def run(argv, **kwargs):
            Path(argv[3]).write_text(json.dumps(payload))
            return subprocess.CompletedProcess(argv, 0, "", "")

        runner = EuromodPlatformRunner(
            model_root="/nonexistent",
            country="UK",
            system="UK_2025",
            subprocess_run=run,
        )
        results = runner.run_cases(
            [_single_earner("a", 30_000.0), _single_earner("b", 60_000.0)],
            variables=["tin_s"],
        )
        assert results[0].values["tin_s"] == pytest.approx(290.5 * 12)
        # per-person amounts sum to the case before annualizing
        assert results[1].values["tin_s"] == pytest.approx(150.0 * 12)

    def test_belgium_property_tax_outputs_are_not_annualized(self) -> None:
        payload = {
            "columns": ["khooo_s", "tprhm_s", "tin_s"],
            "missing": [],
            "idhh": [1],
            "values": {
                "khooo_s": [2_244.6],
                "tprhm_s": [1_040.8120416],
                "tin_s": [100.0],
            },
        }

        def run(argv, **kwargs):
            Path(argv[3]).write_text(json.dumps(payload))
            return subprocess.CompletedProcess(argv, 0, "", "")

        runner = EuromodPlatformRunner(
            model_root="/nonexistent",
            country="BE",
            system="BE_2025",
            subprocess_run=run,
        )
        result = runner.run_cases(
            [_single_earner("a", 30_000.0)],
            variables=["khooo_s", "tprhm_s", "tin_s"],
        )[0]

        assert result.values["khooo_s"] == pytest.approx(2_244.6)
        assert result.values["tprhm_s"] == pytest.approx(1_040.8120416)
        assert result.values["tin_s"] == pytest.approx(1_200.0)

    def test_worker_error_reaches_every_case(self) -> None:
        def run(argv, **kwargs):
            Path(argv[3]).write_text(json.dumps({"error": "boom"}))
            return subprocess.CompletedProcess(argv, 0, "", "")

        runner = EuromodPlatformRunner(
            model_root="/nonexistent",
            country="UK",
            system="UK_2025",
            subprocess_run=run,
        )
        results = runner.run_cases([_single_earner("a", 30_000.0)])
        assert results[0].values == {}
        assert results[0].errors == ("boom",)

    def test_missing_result_file_reports_process_output(self) -> None:
        def run(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 1, "", "engine exploded")

        runner = EuromodPlatformRunner(
            model_root="/nonexistent",
            country="UK",
            system="UK_2025",
            subprocess_run=run,
        )
        results = runner.run_cases([_single_earner("a", 30_000.0)])
        assert "engine exploded" in results[0].errors[0]

    def test_concept_ids_project_to_euromod_output_columns(self) -> None:
        requested = []

        def run(argv, **kwargs):
            job = json.loads(Path(argv[2]).read_text())
            requested.extend(job["outputs"])
            Path(argv[3]).write_text(
                json.dumps(
                    {
                        "columns": [
                            "tin_s",
                            "tscee_s",
                            "tsceerd_s",
                            "tscse_s",
                            "tci_s",
                            "bsa_s",
                            "bsaoa_s",
                        ],
                        "missing": [],
                        "idhh": [1],
                        "values": {
                            "tin_s": [100.0],
                            "tscee_s": [50.0],
                            "tsceerd_s": [12.0],
                            "tscse_s": [40.0],
                            "tci_s": [5.3333333333],
                            "bsa_s": [20.0],
                            "bsaoa_s": [30.0],
                        },
                    }
                )
            )
            return subprocess.CompletedProcess(argv, 0, "", "")

        runner = EuromodPlatformRunner(
            model_root="/nonexistent",
            country="BE",
            system="BE_2025",
            subprocess_run=run,
        )
        [result] = runner.run_cases(
            [_single_earner("be-30k", 30_000.0)],
            variables=[
                Concepts.BE_WORKER_PIT_BEFORE_WITHHOLDING,
                Concepts.BE_EMPLOYEE_SOCIAL_CONTRIBUTIONS,
                Concepts.BE_SELF_EMPLOYED_SOCIAL_CONTRIBUTIONS,
                Concepts.BE_FLEMISH_SOCIAL_PROTECTION_PREMIUM,
                Concepts.BE_SOCIAL_INTEGRATION_INCOME_SUPPORT,
                Concepts.BE_INCOME_GUARANTEE_FOR_ELDERLY,
                "yem",
            ],
        )

        assert requested == [
            "tin_s",
            "tscee_s",
            "tsceerd_s",
            "tscse_s",
            "tci_s",
            "bsa_s",
            "bsaoa_s",
            "yem",
        ]
        assert result.values["tin_s"] == pytest.approx(1_200.0)
        assert result.values["tscee_s"] == pytest.approx(600.0)
        assert result.values["tsceerd_s"] == pytest.approx(144.0)
        assert result.values["tscee_net_s"] == pytest.approx(456.0)
        assert result.values["tscse_s"] == pytest.approx(480.0)
        assert result.values["tci_s"] == pytest.approx(64.0)
        assert result.values["bsa_s"] == pytest.approx(240.0)
        assert result.values["bsaoa_s"] == pytest.approx(360.0)

    def test_switches_reach_worker_payload(self) -> None:
        payload = {
            "columns": ["bsaoa_s"],
            "missing": [],
            "idhh": [1],
            "values": {"bsaoa_s": [1_580.37]},
        }
        observed = {}

        def run(argv, **kwargs):
            observed.update(json.loads(Path(argv[2]).read_text()))
            Path(argv[3]).write_text(json.dumps(payload))
            return subprocess.CompletedProcess(argv, 0, "", "")

        case = Case(
            case_id="be-grapa",
            period="2025",
            metadata={
                "euromod_inputs": [{"idhh": 999, "dag": 70}],
                "euromod_switches": [("Belmod_endo", True)],
            },
        )
        runner = EuromodPlatformRunner(
            model_root="/nonexistent",
            country="BE",
            system="BE_2025",
            switches=[("output_std_hh_be", False)],
            subprocess_run=run,
        )

        [result] = runner.run_cases([case], variables=["bsaoa_s"])

        assert observed["switches"] == [
            ["output_std_hh_be", False],
            ["Belmod_endo", True],
        ]
        assert observed["policy_switch_overrides"] == []
        assert result.values["bsaoa_s"] == pytest.approx(18_964.44)

    def test_policy_switch_overrides_reach_worker_payload(self) -> None:
        payload = {
            "columns": ["bsaoa_s"],
            "missing": [],
            "idhh": [1],
            "values": {"bsaoa_s": [1_580.37]},
        }
        observed = {}

        def run(argv, **kwargs):
            observed.update(json.loads(Path(argv[2]).read_text()))
            Path(argv[3]).write_text(json.dumps(payload))
            return subprocess.CompletedProcess(argv, 0, "", "")

        case = Case(
            case_id="be-grapa",
            period="2025",
            metadata={
                "euromod_inputs": [{"idhh": 999, "dag": 70}],
                "euromod_policy_switch_overrides": [("bsaoa_be", True)],
            },
        )
        runner = EuromodPlatformRunner(
            model_root="/nonexistent",
            country="BE",
            system="BE_2025",
            policy_switch_overrides=[("other_be", False)],
            subprocess_run=run,
        )

        [result] = runner.run_cases([case], variables=["bsaoa_s"])

        assert observed["switches"] == []
        assert observed["policy_switch_overrides"] == [
            ["other_be", False],
            ["bsaoa_be", True],
        ]
        assert result.values["bsaoa_s"] == pytest.approx(18_964.44)

    def test_mixed_case_switches_return_errors(self) -> None:
        runner = EuromodPlatformRunner(
            model_root="/nonexistent",
            country="BE",
            system="BE_2025",
            subprocess_run=lambda *_args, **_kwargs: pytest.fail(
                "mixed switches should not execute"
            ),
        )
        cases = [
            Case(
                case_id="default",
                period="2025",
                metadata={"euromod_inputs": [{"idhh": 1}]},
            ),
            Case(
                case_id="grapa",
                period="2025",
                metadata={
                    "euromod_inputs": [{"idhh": 2}],
                    "euromod_switches": [("Belmod_endo", True)],
                },
            ),
        ]

        results = runner.run_cases(cases, variables=["bsaoa_s"])

        assert all(result.values == {} for result in results)
        assert "incompatible" in results[0].errors[0]

    def test_mixed_case_policy_switch_overrides_return_errors(self) -> None:
        runner = EuromodPlatformRunner(
            model_root="/nonexistent",
            country="BE",
            system="BE_2025",
            subprocess_run=lambda *_args, **_kwargs: pytest.fail(
                "mixed policy overrides should not execute"
            ),
        )
        cases = [
            Case(
                case_id="default",
                period="2025",
                metadata={"euromod_inputs": [{"idhh": 1}]},
            ),
            Case(
                case_id="grapa",
                period="2025",
                metadata={
                    "euromod_inputs": [{"idhh": 2}],
                    "euromod_policy_switch_overrides": [("bsaoa_be", True)],
                },
            ),
        ]

        results = runner.run_cases(cases, variables=["bsaoa_s"])

        assert all(result.values == {} for result in results)
        assert "policy switch overrides" in results[0].errors[0]


@pytest.mark.skipif(
    not (UKMOD_MODEL_ROOT and EUROMOD_PYTHON),
    reason="set UKMOD_MODEL_ROOT and EUROMOD_PYTHON to run the live UKMOD oracle",
)
class TestUkmodLive:
    @pytest.fixture(scope="class")
    def runner(self) -> EuromodPlatformRunner:
        return EuromodPlatformRunner(
            model_root=UKMOD_MODEL_ROOT,
            country="UK",
            system="UK_2025",
        )

    def test_income_tax_and_nics_match_hand_computed_2025_law(self, runner) -> None:
        results = runner.run_cases(
            [_single_earner("uk-30k", 30_000.0), _single_earner("uk-45k", 45_000.0)],
            variables=["tin_s", "tscee_s", "yem"],
        )
        for result in results:
            gross = result.values["yem"]  # engine's own post-uprating gross
            expected_income_tax = (gross - 12_570.0) * 0.20
            expected_nics = (gross - 12_570.0) * 0.08
            assert result.values["tin_s"] == pytest.approx(
                expected_income_tax, abs=1.0
            )
            # NICs compute on weekly-rounded thresholds; allow the rounding.
            assert result.values["tscee_s"] == pytest.approx(
                expected_nics, abs=12.0
            )

    def test_default_outputs_cover_the_standard_bridge_set(self, runner) -> None:
        results = runner.run_cases([_single_earner("uk-30k", 30_000.0)])
        # ``tscee_net_s`` is a derived output (``tscee_s - tsceerd_s``); UKMOD's
        # UK systems do not emit ``tsceerd_s`` (the Belgian work-bonus-style
        # employee-contribution reduction), so the derived column is absent for
        # UKMOD. Assert every other default bridge output is present.
        expected = set(DEFAULT_OUTPUTS) - {"tscee_net_s"}
        assert expected <= set(results[0].values)
        assert "tsceerd_s" not in results[0].values


@pytest.mark.skipif(
    not (EUROMOD_MODEL_ROOT_BE and EUROMOD_PYTHON),
    reason=(
        "set EUROMOD_MODEL_ROOT_BE and EUROMOD_PYTHON to run the live "
        "EUROMOD Belgium oracle"
    ),
)
class TestEuromodBelgiumLive:
    """EUROMOD Belgium, live, under the configured synthetic dataset path.

    The current J2.0 local connector run succeeds under ``BE_training_data``
    but aborts under the real SILC configuration names with
    ``bsa_be/DefConst/IsLiteral`` parsing ``yes`` as an unknown variable. The
    issue ledger records both this local failure and the earlier inverse
    training-data prep failure. The dataset names are env-overridable for
    reproducing either behavior.

    The employee social-contribution check is statutory: Belgian employee
    SSC is a flat 13.07% of gross.
    """

    @pytest.fixture(scope="class")
    def runner(self) -> EuromodPlatformRunner:
        return EuromodPlatformRunner(
            model_root=EUROMOD_MODEL_ROOT_BE,
            country="BE",
            system="BE_2025",
            dataset=EUROMOD_DATASET_BE,
            template_dataset=EUROMOD_TEMPLATE_DATASET_BE,
        )

    def test_employee_contributions_are_the_statutory_13_07_percent(
        self, runner
    ) -> None:
        results = runner.run_cases(
            [_single_earner("be-30k", 30_000.0), _single_earner("be-60k", 60_000.0)],
            variables=["tin_s", "tscee_s", "yem"],
        )
        for result in results:
            gross = result.values["yem"]  # engine's post-uprating gross
            assert result.values["tscee_s"] == pytest.approx(
                gross * 0.1307, rel=1e-3
            )

    def test_pit_is_positive_and_progressive(self, runner) -> None:
        results = runner.run_cases(
            [_single_earner("be-30k", 30_000.0), _single_earner("be-60k", 60_000.0)],
            variables=["tin_s", "ils_dispy", "yem"],
        )
        low, high = results
        assert low.values["tin_s"] > 0
        # progressive: average rate rises with income
        assert (high.values["tin_s"] / high.values["yem"]) > (
            low.values["tin_s"] / low.values["yem"]
        )
        assert high.values["ils_dispy"] > low.values["ils_dispy"]
