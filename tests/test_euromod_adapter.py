"""EUROMOD-platform adapter: projection, subprocess contract, live engines.

The projection and subprocess-contract tests run everywhere. The live
tests execute real models and are gated on environment variables:

- ``UKMOD_MODEL_ROOT`` — a UKMOD checkout (e.g. ``UKMOD_PUBLIC_B2026.03``,
  openly downloadable from github.com/centreformicrosimulation/UKMOD-PUBLIC).
- ``EUROMOD_MODEL_ROOT_BE`` — a EUROMOD release directory (e.g.
  ``EUROMOD_RELEASES_J2.0+``, openly downloadable from the JRC).
- ``EUROMOD_MODEL_ROOT_DE`` — the same release directory, used with the
  DE_2025 system and the DE_2024_b1_2015_03_e2 dataset configuration.
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
import sys
import textwrap
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
EUROMOD_MODEL_ROOT_DE = os.environ.get("EUROMOD_MODEL_ROOT_DE")
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


def _uc_adult_row(idperson, *, partner_id=0, couple=False, is_head=True,
                  tenure=1, monthly_rent=0.0, capital=0.0):
    return {
        "idhh": 1,
        "idperson": idperson,
        "idpartner": partner_id,
        "idmother": 0,
        "idfather": 0,
        "drgn1": 2,
        "dct": 15,
        "dwt": 1_000.0,
        "dag": 35 if is_head else 34,
        "dgn": 1 if is_head else 0,
        "dms": 2 if couple else 1,
        "dhr": 1 if is_head else 0,
        "dec": 0,
        "ddi": 0,
        "les": 0,
        "lhw": 0,
        "loc": 5,
        "amrtn": tenure,
        "yem": 0.0,
        "yse": 0.0,
        "yiy": 0.0,
        "poa": 0.0,
        "xhcrt": monthly_rent,
        "afc": capital,
    }


def _uc_child_row(idperson, age, mother_id):
    return {
        "idhh": 1,
        "idperson": idperson,
        "idpartner": 0,
        "idmother": mother_id,
        "idfather": 0,
        "drgn1": 2,
        "dct": 15,
        "dwt": 1_000.0,
        "dag": age,
        "dgn": 1,
        "dms": 1,
        "dhr": 0,
        "dec": 2,
        "ddi": 0,
        "les": 6,
        "lhw": 0,
        "loc": 5,
        "amrtn": 5,
        "yem": 0.0,
        "yse": 0.0,
        "yiy": 0.0,
        "poa": 0.0,
        "xhcrt": 0.0,
        "afc": 0.0,
    }


def _uc_single_adult(case_id: str) -> Case:
    return Case(
        case_id=case_id,
        period="2026-04",
        metadata={"euromod_inputs": [_uc_adult_row(101, tenure=1)]},
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={Concepts.PERSON_AGE: 35},
            ),
        ),
    )


def _uc_couple_two_children(case_id: str, *, monthly_rent: float) -> Case:
    return Case(
        case_id=case_id,
        period="2026-04",
        metadata={
            "euromod_inputs": [
                _uc_adult_row(
                    101, partner_id=102, couple=True, is_head=True,
                    tenure=5, monthly_rent=monthly_rent,
                ),
                _uc_adult_row(
                    102, partner_id=101, couple=True, is_head=False, tenure=5,
                ),
                _uc_child_row(103, 8, 101),
                _uc_child_row(104, 5, 101),
            ]
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={Concepts.PERSON_AGE: 35},
            ),
        ),
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

    def test_constant_patch_targets_named_system_and_group_only(self) -> None:
        xml = """
<CountryConfig>
  <System>
    <Name>BE_2024</Name>
    <Policy><Function><Name>DefConst</Name>
      <Parameter><Name>$bed_FlTakeUp</Name><Value><![CDATA[0.31]]></Value><Group /></Parameter>
    </Function></Policy>
  </System>
  <System>
    <Name>BE_2025</Name>
    <Policy><Function><Name>DefConst</Name>
      <Parameter><Name>$bed_FlTakeUp</Name><Value><![CDATA[0.31]]></Value><Group /></Parameter>
      <Parameter><Name>$f_cpi</Name><Value><![CDATA[1.0]]></Value><Group>2024</Group></Parameter>
      <Parameter><Name>$f_cpi</Name><Value><![CDATA[1.1]]></Value><Group>2025</Group></Parameter>
    </Function></Policy>
  </System>
</CountryConfig>
"""

        patched = euromod_worker._patch_constants(
            xml,
            system="BE_2025",
            overrides=[("$bed_FlTakeUp", "", "1.0"), ("$f_cpi", "2025", "2.0")],
        )

        be_2024 = patched[: patched.find("<Name>BE_2025</Name>")]
        be_2025 = patched[patched.find("<Name>BE_2025</Name>") :]
        assert "<![CDATA[0.31]]>" in be_2024  # other system untouched
        assert "<![CDATA[0.31]]>" not in be_2025
        assert "<Name>$bed_FlTakeUp</Name><Value><![CDATA[1.0]]>" in be_2025
        assert "<Value><![CDATA[1.0]]></Value><Group>2024</Group>" in be_2025
        assert "<Value><![CDATA[2.0]]></Value><Group>2025</Group>" in be_2025

        with pytest.raises(ValueError, match="was not found"):
            euromod_worker._patch_constants(
                xml, system="BE_2025", overrides=[("$missing", "", "1.0")]
            )

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

    def test_germany_monthly_outputs_stay_monthly_but_tin_is_annualized(
        self,
    ) -> None:
        monthly_outputs = {
            "tsceehl_s": 372.5357142857143,
            "tsceepi_s": 405.2142857142856,
            "tsceeui_s": 56.64285714285714,
            "tsceeci_s": 104.57142857142856,
            "bch00_s": 255.0,
        }
        payload = {
            "columns": [*monthly_outputs, "tin_s"],
            "missing": [],
            "idhh": [1],
            "values": {
                **{key: [value] for key, value in monthly_outputs.items()},
                "tin_s": [100.0],
            },
        }

        def run(argv, **kwargs):
            Path(argv[3]).write_text(json.dumps(payload))
            return subprocess.CompletedProcess(argv, 0, "", "")

        runner = EuromodPlatformRunner(
            model_root="/nonexistent",
            country="DE",
            system="DE_2025",
            subprocess_run=run,
        )
        result = runner.run_cases(
            [_single_earner("de", 48_000.0)],
            variables=[*monthly_outputs, "tin_s"],
        )[0]

        for output, expected in monthly_outputs.items():
            assert result.values[output] == pytest.approx(expected)
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
                            "tintace_s",
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
                            "tintace_s": [33.0],
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
                Concepts.BE_ARTICLE_51_EMPLOYEE_FORFAIT,
                Concepts.BE_EMPLOYEE_SOCIAL_CONTRIBUTIONS,
                Concepts.BE_SELF_EMPLOYED_SOCIAL_CONTRIBUTIONS,
                Concepts.BE_FLEMISH_SOCIAL_PROTECTION_PREMIUM,
                Concepts.BE_SOCIAL_INTEGRATION_INCOME_SUPPORT,
                Concepts.BE_INCOME_GUARANTEE_FOR_ELDERLY,
                "yem",
            ],
        )

        assert requested == [
            "tintace_s",
            "tscee_s",
            "tsceerd_s",
            "tscse_s",
            "tci_s",
            "bsa_s",
            "bsaoa_s",
            "yem",
        ]
        assert result.values["tintace_s"] == pytest.approx(396.0)
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

    def test_worker_groups_rows_by_household_in_first_appearance_order(self) -> None:
        rows = [
            {"idhh": 2, "idperson": 201},
            {"idhh": 1, "idperson": 101},
            {"idhh": 2, "idperson": 202},
            {"idhh": 3, "idperson": 301},
        ]

        groups = euromod_worker._rows_by_household(rows)

        assert list(groups) == [2, 1, 3]
        assert [row["idperson"] for row in groups[2]] == [201, 202]
        assert [row["idperson"] for row in groups[1]] == [101]

    def test_household_error_reaches_only_that_case(self) -> None:
        payload = {
            "columns": ["tin_s"],
            "missing": [],
            "idhh": [1],
            "values": {"tin_s": [290.5]},
            "household_errors": {"2": "RuntimeError: engine rejected household"},
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
        good, bad = runner.run_cases(
            [_single_earner("a", 30_000.0), _single_earner("b", 60_000.0)],
            variables=["tin_s"],
        )

        assert good.values["tin_s"] == pytest.approx(290.5 * 12)
        assert good.errors == ()
        assert bad.values == {}
        assert bad.errors == ("RuntimeError: engine rejected household",)

    def test_case_without_output_rows_errors_instead_of_empty_values(self) -> None:
        payload = {
            "columns": ["tin_s"],
            "missing": [],
            "idhh": [1],
            "values": {"tin_s": [290.5]},
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
        assert results[1].values == {}
        assert "no output rows" in results[1].errors[0]

    def test_mixed_case_constant_overrides_return_errors(self) -> None:
        runner = EuromodPlatformRunner(
            model_root="/nonexistent",
            country="BE",
            system="BE_2025",
            subprocess_run=lambda *_args, **_kwargs: pytest.fail(
                "mixed constant overrides should not execute"
            ),
        )
        cases = [
            Case(
                case_id="default",
                period="2025",
                metadata={"euromod_inputs": [{"idhh": 1}]},
            ),
            Case(
                case_id="full-takeup",
                period="2025",
                metadata={
                    "euromod_inputs": [{"idhh": 2}],
                    "euromod_constant_overrides": {"$bed_FlTakeUp": "1.0"},
                },
            ),
        ]

        results = runner.run_cases(cases, variables=["bed_s"])

        assert all(result.values == {} for result in results)
        assert "constant overrides" in results[0].errors[0]

    def test_constant_overrides_normalize_groups_and_values(self) -> None:
        from axiom_oracles.adapters.euromod.runner import (
            _normalize_constant_overrides,
        )

        assert _normalize_constant_overrides(None) == ()
        assert _normalize_constant_overrides({"$bed_FlTakeUp": 1.0}) == (
            ("$bed_FlTakeUp", "", "1.0"),
        )
        assert _normalize_constant_overrides({"$f_cpi": ("2022", 1000)}) == (
            ("$f_cpi", "2022", "1000"),
        )
        assert _normalize_constant_overrides(
            [("$a", 1), ("$b", "2024", 2.5)]
        ) == (("$a", "", "1"), ("$b", "2024", "2.5"))
        with pytest.raises(ValueError, match="non-empty strings"):
            _normalize_constant_overrides({"": 1.0})
        with pytest.raises(ValueError, match="numeric or string value"):
            _normalize_constant_overrides({"$a": None})

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


class TestBatchPositionIsolation:
    """Multi-case batches must give every case its solo-run result.

    EUROMOD-platform models are not necessarily row-independent across
    households: fixed-seed random streams can be consumed one draw per
    household in dataset order, and take-up corrections can gate benefits on
    those draws.

    The stub engine below reproduces that lottery hermetically: the
    benefit is nonzero only for the *first* household of each submitted
    frame. The worker must therefore run one engine run per household —
    every case then gets its own distinct, position-independent amount.
    This drives the real ``_runner.py`` under the test interpreter.
    """

    STUB_ENGINE = textwrap.dedent(
        '''
        """Stub euromod connector: benefit only for the frame's first household.

        Reads the ``$stub_bonus`` DefConst value out of the (possibly
        overlay-patched) country XML and adds it to the benefit, so tests
        can assert constant overrides land in the model the engine loads —
        the same mechanism the real worker uses.
        """

        import re
        from pathlib import Path


        class _Simulation:
            def __init__(self, output):
                self.outputs = [output]

        class _System:
            name = "BE_2025"

            def __init__(self, bonus):
                self._bonus = bonus

            def run(self, frame, dataset, switches=()):
                output = frame[["idhh", "idperson", "yem"]].copy()
                first_household = int(frame.iloc[0]["idhh"])
                output["ben_s"] = [
                    100.0 + float(row.yem) + self._bonus
                    if int(row.idhh) == first_household
                    else 0.0
                    for row in frame.itertuples()
                ]
                return _Simulation(output)

        class _Country:
            name = "BE"

            def __init__(self, bonus):
                self.systems = [_System(bonus)]

        class Model:
            def __init__(self, model_root):
                xml_path = (
                    Path(model_root) / "XMLParam" / "Countries" / "BE" / "BE.xml"
                )
                bonus = 0.0
                if xml_path.exists():
                    match = re.search(
                        r"<Name>\\$stub_bonus</Name>.*?<Value><!\\[CDATA\\[(.*?)\\]\\]></Value>",
                        xml_path.read_text(encoding="utf-8"),
                        re.S,
                    )
                    if match:
                        bonus = float(match.group(1))
                self.countries = [_Country(bonus)]
        '''
    )

    STUB_COUNTRY_XML = textwrap.dedent(
        """\
        <CountryConfig>
          <System>
            <Name>BE_2025</Name>
            <Policy>
              <Name>stub_be</Name>
              <Switch>on</Switch>
              <Function>
                <Name>DefConst</Name>
                <Parameter>
                  <Name>$stub_bonus</Name>
                  <Value><![CDATA[0]]></Value>
                  <Group />
                </Parameter>
              </Function>
            </Policy>
          </System>
        </CountryConfig>
        """
    )

    @pytest.fixture()
    def lottery_model_root(self, tmp_path: Path, monkeypatch) -> Path:
        model_root = tmp_path / "model"
        (model_root / "Input").mkdir(parents=True)
        (model_root / "Input" / "training_data.txt").write_text(
            "idhh\tidperson\tyem\tdag\n", encoding="utf-8"
        )
        country_dir = model_root / "XMLParam" / "Countries" / "BE"
        country_dir.mkdir(parents=True)
        (country_dir / "BE.xml").write_text(
            self.STUB_COUNTRY_XML, encoding="utf-8"
        )
        stub_dir = tmp_path / "stub-site"
        stub_dir.mkdir()
        (stub_dir / "euromod.py").write_text(self.STUB_ENGINE, encoding="utf-8")
        monkeypatch.setenv("PYTHONPATH", str(stub_dir))
        return model_root

    def test_three_cases_in_one_call_each_get_their_own_nonzero_result(
        self, lottery_model_root: Path
    ) -> None:
        incomes = [12_000.0, 24_000.0, 36_000.0]
        cases = [
            _single_earner(f"case-{int(income)}", income) for income in incomes
        ]
        runner = EuromodPlatformRunner(
            model_root=lottery_model_root,
            country="BE",
            system="BE_2025",
            dataset="training_data",
            python_executable=sys.executable,
        )

        results = runner.run_cases(cases, variables=["ben_s"])

        # Stub benefit is 100 + monthly yem, annualized by the adapter:
        # 1,200 + annual income — distinct and nonzero for every case.
        for result, income in zip(results, incomes, strict=True):
            assert result.errors == ()
            assert result.values["ben_s"] == pytest.approx(1_200.0 + income)

    def test_reversed_batch_order_returns_the_same_per_case_results(
        self, lottery_model_root: Path
    ) -> None:
        incomes = [12_000.0, 24_000.0, 36_000.0]
        cases = [
            _single_earner(f"case-{int(income)}", income) for income in incomes
        ]
        runner = EuromodPlatformRunner(
            model_root=lottery_model_root,
            country="BE",
            system="BE_2025",
            dataset="training_data",
            python_executable=sys.executable,
        )

        forward = runner.run_cases(cases, variables=["ben_s"])
        reversed_back = runner.run_cases(list(reversed(cases)), variables=["ben_s"])

        by_case_forward = {r.household_id: r.values["ben_s"] for r in forward}
        by_case_reversed = {r.household_id: r.values["ben_s"] for r in reversed_back}
        assert by_case_forward == pytest.approx(by_case_reversed)

    def test_constant_overrides_reach_the_engine_run(
        self, lottery_model_root: Path
    ) -> None:
        runner = EuromodPlatformRunner(
            model_root=lottery_model_root,
            country="BE",
            system="BE_2025",
            dataset="training_data",
            constant_overrides={"$stub_bonus": 7},
            python_executable=sys.executable,
        )

        [result] = runner.run_cases(
            [_single_earner("case-12000", 12_000.0)], variables=["ben_s"]
        )

        # (100 + 1,000 monthly yem + 7 bonus) x 12
        assert result.values["ben_s"] == pytest.approx(1_284.0 + 12_000.0)

    def test_case_metadata_constant_overrides_merge_over_runner_defaults(
        self, lottery_model_root: Path
    ) -> None:
        runner = EuromodPlatformRunner(
            model_root=lottery_model_root,
            country="BE",
            system="BE_2025",
            dataset="training_data",
            constant_overrides={"$stub_bonus": 7},
            python_executable=sys.executable,
        )
        case = Case(
            case_id="override-case",
            period="2025",
            metadata={
                "euromod_inputs": [{"idhh": 1, "idperson": 101, "yem": 1_000.0}],
                "euromod_constant_overrides": {"$stub_bonus": 50},
            },
        )

        [result] = runner.run_cases([case], variables=["ben_s"])

        # (100 + 1,000 + the case's 50, not the runner's 7) x 12
        assert result.values["ben_s"] == pytest.approx(13_800.0)


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

    def test_universal_credit_household_award_aggregates_over_the_benefit_unit(
        self, runner
    ) -> None:
        # A couple with two children and a social-renter housing element is one
        # UKMOD benefit unit; the award ``bsauc_s`` is a monthly assessment-
        # period amount the adapter deliberately leaves un-annualized
        # (NON_ANNUALIZED_OUTPUTS: its Axiom counterpart is also monthly).
        # Each element is a UC 2025-26 statutory amount for the UK_2025
        # system this class runs: single 25+ standard allowance 400.14,
        # couple joint 25+ 628.10, first child element at the higher rate
        # 339.00 (the eight-year-old's birth year falls before 6 April 2017
        # in the training dataset's calendar — ages anchor to the data year,
        # not the case period), 292.81 for the younger child, and the full
        # rent as the social-renter housing element. The award composes
        # these over the whole household, so it far exceeds the single-adult
        # award and moves with the benefit-unit composition. Each case runs
        # as its own engine run so the award is the full entitlement rather
        # than a batch-position draw of UKMOD's benefit take-up correction
        # (see euromod_issues.json ukmod-uc-bsauc-takeup-correction).
        single_award = runner.run_cases(
            [_uc_single_adult("uc-single")], variables=["bsauc_s"]
        )[0].values["bsauc_s"]
        household_award = runner.run_cases(
            [_uc_couple_two_children("uc-couple-2c", monthly_rent=900.0)],
            variables=["bsauc_s"],
        )[0].values["bsauc_s"]
        # Single adult standard allowance, monthly.
        assert single_award == pytest.approx(400.14, abs=0.01)
        # Couple + two children + 900/month housing: strictly larger, and
        # exactly the couple standard allowance plus the two child elements
        # plus the housing element (monthly), the earnings taper being zero
        # here.
        assert household_award > single_award
        floor = 628.10 + 339.00 + 292.81 + 900.0
        assert household_award == pytest.approx(floor, abs=0.01)


@pytest.mark.skipif(
    not (EUROMOD_MODEL_ROOT_DE and EUROMOD_PYTHON),
    reason=(
        "set EUROMOD_MODEL_ROOT_DE and EUROMOD_PYTHON to run the live "
        "EUROMOD Germany oracle"
    ),
)
class TestEuromodGermanyLive:
    """Live anchors from the canonical DE dual-oracle worker grid."""

    OUTPUTS = (
        "tsceehl_s",
        "tsceepi_s",
        "tsceeui_s",
        "tsceeci_s",
        "tin_s",
        "bch00_s",
        "yem",
    )
    ANCHORS = {
        "single-w-1200": {
            "tsceehl_s": 88.95112781954889,
            "tsceepi_s": 96.75385833003561,
            "tsceeui_s": 13.524732884843688,
            "tsceeci_s": 24.968737633557577,
            "tin_s": 0.0,
            "bch00_s": 0.0,
            "yem": 15_685.714285714286,
        },
        "parent-2children-4000": {
            "tsceehl_s": 372.5357142857143,
            "tsceepi_s": 405.21428571428567,
            "tsceeui_s": 56.64285714285714,
            "tsceeci_s": 67.53571428571428,
            "tin_s": 3_416.008586249796,
            "bch00_s": 510.0,
            "yem": 52_285.71428571428,
        },
    }

    @pytest.fixture(scope="class")
    def runner(self) -> EuromodPlatformRunner:
        return EuromodPlatformRunner(
            model_root=EUROMOD_MODEL_ROOT_DE,
            country="DE",
            system="DE_2025",
            dataset="DE_2024_b1_2015_03_e2",
            template_dataset="DE_training_data",
            extra_columns=["drgn1"],
        )

    @pytest.mark.parametrize("case_id", ["single-w-1200", "parent-2children-4000"])
    def test_canonical_grid_anchor(self, runner, case_id) -> None:
        from axiom_oracles.suites.de_worker import de_worker_dual_oracle_cases

        cases = {case.case_id: case for case in de_worker_dual_oracle_cases()}
        [result] = runner.run_cases([cases[case_id]], variables=list(self.OUTPUTS))

        assert result.errors == ()
        assert result.household_id == case_id
        for variable, expected in self.ANCHORS[case_id].items():
            assert result.values[variable] == pytest.approx(expected, abs=1e-6)


@pytest.mark.skipif(
    not (EUROMOD_MODEL_ROOT_BE and EUROMOD_PYTHON),
    reason=(
        "set EUROMOD_MODEL_ROOT_BE and EUROMOD_PYTHON to run the live "
        "EUROMOD Belgium oracle"
    ),
)
class TestEuromodBelgiumLive:
    """EUROMOD Belgium, live, under the configured synthetic dataset path.

    Run with ``EUROMOD_DATASET_BE=BE_2024_c1_2015_03_e2``: BE_2025 aborts at
    parameter preparation under the bundled ``BE_training_data`` name (gated
    income lists; euromod_issues.json
    jrc-euromod-4-be-training-data-income-list-prep), while the real
    configuration name runs clean — verified 2026-07-05 for the SSC, PIT,
    and study-allowance tests below. The earlier local observation of an
    inverse ``bsa_be/DefConst/IsLiteral`` abort under real configuration
    names did not reproduce in that sweep (ledger
    euromod-be-real-config-bsa-is-literal-yes). The dataset names stay
    env-overridable for reproducing either behavior.

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


class TestExtraColumns:
    """Extra template columns for model-required variables missing from demo data."""

    def test_worker_template_extends_header_with_extra_columns(self) -> None:
        template = euromod_worker._dataset_template(
            ["idhh", "idperson", "yem"], ["drgn1", "yem"]
        )
        assert list(template) == ["idhh", "idperson", "yem", "drgn1"]
        assert template["drgn1"] == 0.0

    def test_runner_passes_extra_columns_and_rows_keep_them(self, tmp_path) -> None:
        captured: dict = {}

        def run(argv, **kwargs):
            captured["job"] = json.loads(Path(argv[2]).read_text())
            Path(argv[3]).write_text(
                json.dumps(
                    {
                        "columns": ["tin_s"],
                        "missing": [],
                        "idhh": [1],
                        "values": {"tin_s": [0.0]},
                    }
                )
            )
            return subprocess.CompletedProcess(argv, 0, "", "")

        runner = EuromodPlatformRunner(
            model_root="/nonexistent",
            country="DE",
            system="DE_2025",
            extra_columns=["drgn1"],
            subprocess_run=run,
        )
        case = Case(
            case_id="de-extra",
            period="2025",
            entities=(Entity(entity_id="head", kind="person", facts={}),),
            metadata={
                "euromod_inputs": [
                    {"idhh": 1, "idperson": 101, "yem": 4000.0, "drgn1": 9}
                ]
            },
        )
        runner.run_cases([case], variables=["tin_s"])

        assert captured["job"]["extra_columns"] == ["drgn1"]
        assert captured["job"]["rows"][0]["drgn1"] == 9
