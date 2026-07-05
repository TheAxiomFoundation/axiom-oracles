"""SnapScreener diagnostic oracle support.

This adapter executes the public browser JavaScript bundle served by
tools.snapscreener.com. It is intentionally a diagnostic cross-check, not a
vendored dependency or authoritative source of law.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SNAPSCREENER_API_JS_URL = "https://tools.snapscreener.com/api.js"


@dataclass(frozen=True)
class SnapScreenerBundle:
    path: Path
    url: str
    sha256: str


def ensure_api_js(
    *,
    api_js: Path | None = None,
    cache_dir: Path | None = None,
) -> SnapScreenerBundle:
    """Resolve or fetch the public SnapScreener calculator bundle."""

    if api_js is not None:
        path = api_js.resolve()
        if not path.exists():
            raise FileNotFoundError(f"SnapScreener API bundle not found: {path}")
        return SnapScreenerBundle(
            path=path,
            url=SNAPSCREENER_API_JS_URL,
            sha256=file_sha256(path),
        )

    if cache_dir is None:
        cache_dir = Path.home() / ".cache" / "axiom-encode" / "snapscreener"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "api.js"
    request = urllib.request.Request(
        SNAPSCREENER_API_JS_URL,
        headers={"User-Agent": "axiom-encode SnapScreener diagnostic oracle"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        path.write_bytes(response.read())
    return SnapScreenerBundle(
        path=path.resolve(),
        url=SNAPSCREENER_API_JS_URL,
        sha256=file_sha256(path),
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_payloads(cases: Iterable[Any], *, state: str) -> list[dict[str, Any]]:
    return [project_payload(case, state=state) for case in cases]


def project_payload(case: Any, *, state: str) -> dict[str, Any]:
    outputs = case.pe_outputs
    utility_type = str(outputs.get("snap_utility_allowance_type", ""))
    payload = {
        "api": True,
        "state_or_territory": snapscreener_state_key(state, outputs),
        "household_size": int(amount(outputs.get("snap_unit_size", 1))),
        "monthly_job_income": amount(outputs.get("snap_earned_income", 0)),
        "monthly_non_job_income": amount(outputs.get("snap_unearned_income", 0)),
        "monthly_job_income_frequency": "3",
        "monthly_non_job_income_frequency": "3",
        "household_includes_elderly_or_disabled": bool(
            outputs.get("has_usda_elderly_disabled", False)
        ),
        "household_all_elderly_or_disabled": bool(
            outputs.get("has_usda_elderly_disabled", False)
        ),
        "all_citizens": True,
        "resources": amount(outputs.get("snap_assets", 0)),
        "dependent_care_costs": amount(outputs.get("snap_dependent_care_deduction", 0)),
        "medical_expenses_for_elderly_or_disabled": medical_expenses_for_deduction(
            amount(outputs.get("snap_excess_medical_expense_deduction", 0))
        ),
        "court_ordered_child_support_payments": amount(
            outputs.get("snap_child_support_deduction", 0)
            + outputs.get("snap_child_support_gross_income_deduction", 0)
        ),
        "rent_or_mortgage": amount(outputs.get("housing_cost", 0)),
        "homeowners_insurance_and_taxes": 0,
        "household_homeless": False,
        "wic_child": False,
        "wic_pregnant": False,
        "wic_postpartum": False,
        "monthly_utility_bills": 0,
        "noncitizen_number": 0,
        "noncitizen_lpr_plus_criteria_number": 0,
        "noneligible_monthly_income": 0,
        **utility_flags(utility_type),
    }
    return payload


def snapscreener_state_key(state: str, outputs: dict[str, Any]) -> str:
    state = state.upper()
    if state != "NY":
        return state

    region = str(outputs.get("snap_utility_region_str", ""))
    if region == "NY_NYC":
        area = "NYC"
    elif region == "NY_NAS":
        area = "NAS"
    else:
        area = "ONY"

    if amount(outputs.get("snap_dependent_care_deduction", 0)) > 0 or bool(
        outputs.get("has_usda_elderly_disabled", False)
    ):
        suffix = "DC"
    elif amount(outputs.get("snap_earned_income", 0)) > 0:
        suffix = "EI"
    else:
        suffix = "XX"
    return f"NY_{area}_{suffix}"


def utility_flags(utility_type: str) -> dict[str, bool]:
    flags = {
        "utility_electricity": False,
        "utility_gas": False,
        "utility_heating": False,
        "utility_phone": False,
        "utility_sewage": False,
        "utility_trash": False,
        "utility_water": False,
    }
    if utility_type == "SUA":
        flags["utility_heating"] = True
    elif utility_type in {"BUA", "LUA"}:
        flags["utility_electricity"] = True
    elif utility_type in {"TUA", "IUA"}:
        flags["utility_phone"] = True
    return flags


def medical_expenses_for_deduction(deduction: float) -> float:
    if deduction <= 0:
        return 0
    return deduction + 35


def amount(value: Any) -> float:
    if value is None:
        return 0.0
    value = float(value)
    if not math.isfinite(value):
        return 0.0
    return round(value, 6)


def run_payloads(
    payloads: list[dict[str, Any]],
    *,
    api_js: Path,
) -> list[dict[str, Any]]:
    if not payloads:
        return []
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node.js is required to run the SnapScreener oracle")
    result = subprocess.run(
        [node, "-e", NODE_RUNNER, str(api_js)],
        input=json.dumps(payloads),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout)


NODE_RUNNER = r"""
const fs = require("fs");
const apiPath = process.argv[1];

globalThis.STATE_HAS_BBCE = false;
globalThis.ELIGIBILITY_TEST_METHOD_DISPLAYED = "";
globalThis.STATE_FULL_NAME = "";
globalThis.urlParams = new URLSearchParams("");
globalThis.CURRENT_PROFILE = {};
globalThis.$ = { extend: Object.assign };
globalThis.location = { pathname: "" };
globalThis.window = { goatcounter: { count() {} } };
globalThis.inFrame = false;
globalThis.snapscreenercom = false;
globalThis.smoothScroll = false;

var STATE_HAS_BBCE = globalThis.STATE_HAS_BBCE;
var ELIGIBILITY_TEST_METHOD_DISPLAYED = globalThis.ELIGIBILITY_TEST_METHOD_DISPLAYED;
var STATE_FULL_NAME = globalThis.STATE_FULL_NAME;
var urlParams = globalThis.urlParams;
var CURRENT_PROFILE = globalThis.CURRENT_PROFILE;
var $ = globalThis.$;
var location = globalThis.location;
var window = globalThis.window;
var inFrame = globalThis.inFrame;
var snapscreenercom = globalThis.snapscreenercom;
var smoothScroll = globalThis.smoothScroll;

eval(fs.readFileSync(apiPath, "utf8"));

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", chunk => input += chunk);
process.stdin.on("end", () => {
  const payloads = JSON.parse(input);
  const results = payloads.map((payload) => {
    try {
      const result = new SnapAPI.SnapEstimateEntrypoint(payload).calculate();
      return {
        status: result.status,
        estimated_eligibility: result.estimated_eligibility,
        estimated_monthly_benefit: result.estimated_monthly_benefit,
        gross_income_result: result.gross_income_result,
        net_income_result: result.net_income_result,
        errors: result.errors || []
      };
    } catch (error) {
      return {
        status: "ERROR",
        estimated_eligibility: null,
        estimated_monthly_benefit: null,
        gross_income_result: null,
        net_income_result: null,
        errors: [String(error && error.stack ? error.stack : error)]
      };
    }
  });
  process.stdout.write(JSON.stringify(results));
});
"""
