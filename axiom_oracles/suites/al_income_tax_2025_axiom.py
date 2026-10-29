"""Conditional Axiom execution for the Alabama TY2025 saved-output lane.

The module and input/output names below are the proposed composed RuleSpec
contract from the lane's source review. They are not an Alabama tax formula.
The seven federal amounts are the Form 40 booklet p31 worksheet inputs. Net
``fiitax`` is never a substitute for Form 1040 line 22. In particular, PE's
``income_tax_before_refundable_credits`` includes NIIT and cannot be passed as
line 22 alongside a separate NIIT amount. Neither saved feed establishes line
22, refundable-only AOTC, refundable adoption credit, or Schedule 3 line 13a.
Those amounts remain unavailable; an observed zero in some broader tax total
does not certify a missing form line as zero.

Future direct form amounts can be supplied in ``<feed>_federal_<field>`` frame
columns with the corresponding ``<feed>_federal_<field>_status`` equal to
``verified_form_line``. The prototype's candidate crosswalk is not sufficient.
The original TAXSIM inputs are passed unchanged as ``input.taxsim_<column>``;
``filing_status`` retains TAXSIM's numeric ``mstat`` encoding. The RuleSpec
module must interpret those household facts and derive Alabama components.
Completed Alabama AGI, deductions, taxable income, and liability are never
inputs. Dependent counts/ages do not themselves certify exemption eligibility.
"""

from __future__ import annotations

import hashlib
import math
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner
from axiom_oracles.core.case import Case
from axiom_oracles.engine_compat import (
    JURISDICTION_DIR_NAME,
    compile_with_engine,
    stage_pure_root,
)

MODULE = "us-al:policies/income_tax/2025_resident_liability"
MODULE_PATH = Path("us-al/policies/income_tax/2025_resident_liability.yaml")
FEDERAL_FIELDS = (
    "form_1040_line_22",
    "form_8960_line_17",
    "form_1040_line_27a",
    "form_1040_line_28",
    "form_1040_line_29",
    "form_1040_line_30",
    "schedule_3_line_13a",
)
OUTPUTS = (
    "agi",
    "standard_deduction",
    "itemized_deductions",
    "exemptions",
    "taxable_income",
    "tax_before_credits",
    "credits",
    "liability",
    "deductions",
    "federal_tax_deduction",
)
RULESPEC_OUTPUTS = {name: f"{MODULE}#al_{name}" for name in OUTPUTS}
REQUIRED_INPUTS = (*FEDERAL_FIELDS, "federal_agi", "filing_status")

# Each alternative names an actual saved engine component, in preference order.
# All remaining worksheet lines have no supported saved-output crosswalk.
_FEDERAL_COLUMNS = {
    "pe": {
        "form_8960_line_17": ("pe_sidecar_net_investment_income_tax", "pe_raw_niit"),
        "form_1040_line_27a": ("pe_sidecar_eitc", "pe_raw_v25"),
        "form_1040_line_28": ("pe_sidecar_refundable_ctc", "pe_raw_actc"),
        "federal_agi": ("pe_sidecar_adjusted_gross_income", "pe_raw_v10"),
    },
    "taxsim": {
        "form_8960_line_17": ("taxsim_raw_niit",),
        "form_1040_line_27a": ("taxsim_raw_v25",),
        "form_1040_line_28": ("taxsim_raw_actc",),
        "federal_agi": ("taxsim_raw_v10",),
    },
}
_UNAVAILABLE_REASONS = {
    "form_1040_line_22": (
        "Not directly reported; net fiitax and income_tax_before_refundable_credits "
        "are not verified Form 1040 line 22 amounts."
    ),
    "form_1040_line_29": (
        "Refundable-only American Opportunity Credit is not separately reported; "
        "PE american_opportunity_credit does not certify the refundable share."
    ),
    "form_1040_line_30": "Refundable adoption credit is not separately reported.",
    "schedule_3_line_13a": "Credit from Forms 2439 is not separately reported.",
}


def _number(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _crosswalk(feed: str) -> dict[str, dict[str, Any]]:
    result = {}
    for field in REQUIRED_INPUTS:
        columns = _FEDERAL_COLUMNS[feed].get(field, ())
        result[field] = {
            "rule_input": f"{MODULE}#input.{field}",
            "saved_columns": list(columns),
            "status": "saved_component" if columns else "unavailable",
        }
        if field in FEDERAL_FIELDS:
            result[field]["worksheet_source"] = {
                "document": "Alabama Form 40 Instructions TY2025",
                "page": 31,
            }
            result[field]["verified_override_column"] = f"{feed}_federal_{field}"
            result[field]["verified_override_status_column"] = (
                f"{feed}_federal_{field}_status"
            )
            result[field]["required_override_status"] = "verified_form_line"
        if field in _UNAVAILABLE_REASONS:
            result[field]["reason"] = _UNAVAILABLE_REASONS[field]
    result["filing_status"].update(
        status="original_household_input",
        saved_columns=["households.mstat"],
        encoding="TAXSIM mstat code, unchanged; interpreted by the composed module",
    )
    return result


def _federal_values(
    household: pd.Series,
    row: pd.Series,
    feed: str,
) -> tuple[dict[str, float | None], dict[str, str | None]]:
    values: dict[str, float | None] = {}
    sources: dict[str, str | None] = {}
    for field in REQUIRED_INPUTS:
        value, source = None, None
        for column in _FEDERAL_COLUMNS[feed].get(field, ()):
            value = _number(row.get(column))
            if value is not None:
                source = column
                break
        direct = f"{feed}_federal_{field}"
        if row.get(f"{direct}_status") == "verified_form_line":
            value, source = _number(row.get(direct)), direct
        if field == "filing_status":
            value, source = _number(household.get("mstat")), "households.mstat"
        values[field], sources[field] = value, source
    return values, sources


def _case(taxsimid: int, household: pd.Series, federal: dict) -> Case:
    inputs = {
        f"{MODULE}#input.taxsim_{column}": float(value)
        for column, raw in household.items()
        if (value := _number(raw)) is not None
    }
    inputs.update(
        {f"{MODULE}#input.{field}": value for field, value in federal.items()}
    )
    # The original integer code avoids inventing a filing-status legal mapping.
    inputs[f"{MODULE}#input.filing_status"] = int(federal["filing_status"])
    return Case(
        case_id=taxsimid,
        period="2025",
        outputs=tuple(RULESPEC_OUTPUTS.values()),
        metadata={
            "axiom_inputs": inputs,
            "axiom_entity": "TaxUnit",
            "axiom_entity_id": f"tax_unit:{taxsimid}",
        },
    )


@contextmanager
def _scratch_tempfiles(scratch: Path):
    """Contain the adapter's internal TemporaryDirectory calls in this lane.

    The generator executes serially. Restore Python's process-local tempfile
    setting even on an engine failure; no environment variable is changed.
    """
    original = tempfile.tempdir
    tempfile.tempdir = str(scratch)
    try:
        yield
    finally:
        tempfile.tempdir = original


def _compile(root: Path, scratch: Path) -> AxiomRulesRunner:
    # Include transitive jurisdiction imports, while omitting repository tooling.
    jurisdictions = {
        path.name
        for path in root.iterdir()
        if path.is_dir() and JURISDICTION_DIR_NAME.fullmatch(path.name)
    }
    staged = stage_pure_root(root, jurisdictions, scratch / "roots")
    if staged.name != "rulespec-us":
        staged = staged.rename(staged.with_name("rulespec-us"))
    program = scratch / "al-ty2025.composed.yaml"
    program.write_text(
        yaml.safe_dump(
            {
                "format": "rulespec/v1",
                "module": {
                    "kind": "composition",
                    "summary": "Alabama TY2025 eCPS lane",
                },
                "imports": [MODULE],
                "rules": [],
            },
            sort_keys=False,
        )
    )
    artifact = scratch / "al-ty2025.compiled.json"
    runner = AxiomRulesRunner(
        program_path=root / MODULE_PATH,
        compiled_artifact_path=artifact,
        rulespec_repo_roots=(staged,),
    )
    env = dict(os.environ)
    env["AXIOM_RULESPEC_REPO_ROOTS"] = str(staged)
    compile_with_engine(
        runner.binary_path,
        program,
        artifact,
        roots=[staged],
        composed=True,
        env=env,
    )
    return runner


def _engine_identity(runner: AxiomRulesRunner) -> dict[str, str | None]:
    """Record the executable actually selected by the ordinary Axiom adapter."""
    selected = getattr(runner, "binary_path", None)
    if selected is None:
        return {"path": None, "sha256": None}
    binary = Path(selected)
    if not binary.is_file():
        located = shutil.which(str(binary))
        if located is None:
            return {"path": str(binary), "sha256": None}
        binary = Path(located)
    with binary.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(binary.resolve()), "sha256": digest}


def evaluate_axiom_legs(
    households: pd.DataFrame,
    frame: pd.DataFrame,
    *,
    rulespec_root: Path,
    scratch_dir: Path,
) -> dict[str, dict[str, Any]]:
    """Compile once and evaluate the independent PE/TAXSIM federal feeds.

    Missing modules yield ``pending_module`` without importing an engine SDK or
    writing scratch files. A present module is compiled even when the available
    form inputs are incomplete. Only complete rows are submitted for evaluation;
    missing form lines yield ``unavailable_input``, never fabricated zeros.
    Compilation/runtime failures have explicit statuses, distinct from pending.
    """
    if not households.index.is_unique or not households.index.equals(frame.index):
        raise ValueError("Axiom household and comparison frame IDs must agree uniquely")
    root = Path(rulespec_root).resolve()
    module = root / MODULE_PATH
    module_present = module.is_file()
    pending_reason = (
        "Alabama TY2025 composed module is absent; encoding awaits source signing "
        "(decision d270; pending narrow union axiom-corpus#746)."
    )
    legs, prepared = {}, {}
    for feed in ("pe", "taxsim"):
        cases, runnable = [], []
        for taxsimid, household in households.iterrows():
            federal, sources = _federal_values(household, frame.loc[taxsimid], feed)
            unavailable = [name for name, value in federal.items() if value is None]
            cases.append(
                {
                    "taxsimid": int(taxsimid),
                    "status": "pending_module"
                    if not module_present
                    else "unavailable_input",
                    "outputs": dict.fromkeys(OUTPUTS),
                    "federal_inputs": federal,
                    "federal_input_sources": sources,
                    "unavailable_inputs": unavailable,
                }
            )
            if module_present and not unavailable:
                runnable.append(_case(int(taxsimid), household, federal))
        legs[f"{feed}_federal"] = {
            "status": "pending_module" if not module_present else "unavailable_input",
            "reason": pending_reason
            if not module_present
            else "Required federal form amounts are unavailable.",
            "module_path": MODULE_PATH.as_posix(),
            "module": MODULE,
            "module_sha256": hashlib.sha256(module.read_bytes()).hexdigest()
            if module_present
            else None,
            "input_contract_status": "proposed_for_future_composed_module",
            "input_crosswalk": _crosswalk(feed),
            "household_input_contract": f"{MODULE}#input.taxsim_<original column>",
            "household_assumptions": (
                "Original TAXSIM fields and mstat codes are preserved. assume_w2_wages=true; "
                "native SALT. Missing dependent ages remain missing; dependency counts do "
                "not establish Alabama exemption eligibility. The module derives state amounts."
            ),
            "output_contract": RULESPEC_OUTPUTS.copy(),
            "compiled": False,
            "engine_binary": {"path": None, "sha256": None},
            "evaluated_households": 0,
            "cases": cases,
        }
        prepared[feed] = runnable
    if not module_present:
        return legs

    scratch_dir = Path(scratch_dir).resolve()
    scratch_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="al-ty2025-", dir=scratch_dir) as temp:
        scratch = Path(temp)
        try:
            runner = _compile(root, scratch)
            engine_identity = _engine_identity(runner)
        except (OSError, RuntimeError, ValueError) as exc:
            for leg in legs.values():
                leg.update(status="compile_error", reason=str(exc))
                for record in leg["cases"]:
                    record["status"] = "compile_error"
            return legs
        for feed in ("pe", "taxsim"):
            leg = legs[f"{feed}_federal"]
            leg["compiled"] = True
            leg["engine_binary"] = engine_identity.copy()
            if not prepared[feed]:
                continue
            try:
                with _scratch_tempfiles(scratch):
                    results = runner.run_cases(
                        prepared[feed], list(RULESPEC_OUTPUTS.values())
                    )
                by_id = {int(result.household_id): result for result in results}
                expected_ids = {case.case_id for case in prepared[feed]}
                if len(by_id) != len(results) or set(by_id) != expected_ids:
                    raise ValueError(
                        "Axiom returned duplicate, missing, or unexpected household IDs"
                    )
            except (OSError, RuntimeError, ValueError) as exc:
                leg.update(status="execution_error", reason=str(exc))
                for record in leg["cases"]:
                    if not record["unavailable_inputs"]:
                        record.update(status="execution_error", errors=[str(exc)])
                continue
            for record in leg["cases"]:
                result = by_id.get(record["taxsimid"])
                if result is None:
                    continue
                errors = list(result.errors)
                try:
                    outputs = {
                        name: _number(result.values.get(target))
                        for name, target in RULESPEC_OUTPUTS.items()
                    }
                except (TypeError, ValueError) as exc:
                    outputs = dict.fromkeys(OUTPUTS)
                    errors.append(f"Invalid numeric Axiom output: {exc}")
                missing = [name for name, value in outputs.items() if value is None]
                if missing:
                    errors.append(
                        "Missing/nonfinite Axiom outputs: " + ", ".join(missing)
                    )
                record.update(
                    status="execution_error" if errors else "evaluated",
                    outputs=outputs,
                    errors=errors,
                )
            evaluated = sum(record["status"] == "evaluated" for record in leg["cases"])
            leg["evaluated_households"] = evaluated
            leg["status"] = (
                "evaluated"
                if evaluated == len(leg["cases"])
                else ("partial" if evaluated else "execution_error")
            )
            leg["reason"] = (
                "Compiled RuleSpec evaluated with the declared federal feed."
                if leg["status"] == "evaluated"
                else "Some households have unavailable inputs or failed Axiom outputs; see cases."
            )
    return legs
