"""Compare every state's encoded Medicaid/CHIP eligibility levels against PolicyEngine.

The corpus encodes one CMS eligibility-levels file per state
(``us-XX/policies/cms/<state>-medicaid-chip-bhp-eligibility-levels.yaml``)
with per-category FPL limits plus ``*_effective_fpl_limit`` deriveds that
add the shared MAGI 5% disregard. PolicyEngine carries the same table as
``gov.hhs.medicaid.eligibility.categories.<category>.income_limit.<STATE>``.

This runner discovers the state files from upstream ``origin/main`` (so a
newly encoded state joins the comparison with no changes here), evaluates
each file together with the shared federal disregard module, and compares
every effective limit both sides model. Colorado and Georgia keep their
dedicated suites and are skipped to avoid double-counting.

Output: ``axiom.comparison_report.v1`` JSON at
``dashboard/public/data/axiom-policyengine-medicaid-thresholds-states.json``.

Usage:
    uv run python scripts/run_medicaid_thresholds_comparison.py
    RULESPEC_US_ROOT=~/rulespec-us uv run python scripts/run_medicaid_thresholds_comparison.py
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
from pathlib import Path

import yaml

PERIOD = "2026-01-01"
SUITE = "medicaid-thresholds-states"
REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = (
    REPO_ROOT
    / "dashboard"
    / "public"
    / "data"
    / "axiom-policyengine-medicaid-thresholds-states.json"
)
RULESPEC_ROOT = Path(
    os.environ.get("RULESPEC_US_ROOT", Path.home() / "rulespec-us")
).expanduser()

SHARED_MODULE = "us/policies/cms/medicaid-chip-bhp-eligibility-levels.yaml"
STATE_FILE_RE = re.compile(
    r"^us-(?P<code>[a-z]{2})/policies/cms/(?P<slug>[a-z-]+)-medicaid-chip-bhp-eligibility-levels\.yaml$"
)

# States with dedicated, deeper parameter suites already on the dashboard.
SKIP_STATES = {"co", "ga"}

# Encoded effective-limit rule suffix → PolicyEngine category node. The
# effective values include the MAGI 5% disregard on both sides.
SUFFIX_TO_CATEGORY = {
    "children_medicaid_ages_0_to_1_effective_fpl_limit": "infant",
    "children_medicaid_ages_1_to_5_effective_fpl_limit": "young_child",
    "children_medicaid_ages_6_to_18_effective_fpl_limit": "older_child",
    "pregnant_women_medicaid_effective_fpl_limit": "pregnant",
    "parent_caretaker_adults_medicaid_effective_fpl_limit": "parent",
    "expansion_adults_medicaid_effective_fpl_limit": "adult",
}

_NAME_RE = re.compile(r"[a-z_][a-z0-9_]*")
_ALLOWED_FORMULA = re.compile(r"^[a-z0-9_+\-*/(),.\s]+$")


def _git_show(path: str) -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(RULESPEC_ROOT), "show", f"origin/main:{path}"],
        capture_output=True,
        text=True,
    )
    return proc.stdout if proc.returncode == 0 else None


def _state_files() -> list[tuple[str, str, str]]:
    """(state_code, state_slug, repo_path) for every encoded CMS file."""
    proc = subprocess.run(
        ["git", "-C", str(RULESPEC_ROOT), "ls-tree", "-r", "--name-only", "origin/main"],
        capture_output=True,
        text=True,
        check=True,
    )
    out = []
    for line in proc.stdout.splitlines():
        m = STATE_FILE_RE.match(line)
        if m:
            out.append((m.group("code"), m.group("slug"), line))
    return sorted(out)


def evaluate_rules(texts: list[str]) -> dict[str, float]:
    """Evaluate parameter AND scalar derived rules across merged documents.

    Same restricted evaluator as the SSA runner, widened to scalar
    ``kind: derived`` rules (the effective limits) — they are plain
    arithmetic over parameters, with no entity or period machinery.
    """
    formulas: dict[str, str] = {}
    values: dict[str, float] = {}
    for text in texts:
        doc = yaml.safe_load(text)
        for rule in doc.get("rules", []) or []:
            versions = rule.get("versions") or []
            if rule.get("kind") not in {"parameter", "derived"} or not versions:
                continue
            if rule.get("entity"):
                continue  # entity-scoped deriveds need the engine, not this
            table = versions[0].get("values")
            if isinstance(table, dict):
                continue
            formula = str(versions[0].get("formula", "")).strip()
            if _ALLOWED_FORMULA.match(formula):
                formulas[rule["name"]] = formula

    namespace = {
        "floor": math.floor,
        "max": max,
        "min": min,
        "true": True,
        "false": False,
    }
    for _ in range(len(formulas) + 1):
        progressed = False
        for name, formula in formulas.items():
            if name in values:
                continue
            deps = [
                token
                for token in _NAME_RE.findall(formula)
                if token in formulas and token != name
            ]
            if any(dep not in values for dep in deps):
                continue
            try:
                values[name] = float(
                    eval(formula, {"__builtins__": {}}, {**namespace, **values})  # noqa: S307
                )
            except Exception:
                continue
            progressed = True
        if not progressed:
            break
    return values


def build_report() -> dict:
    from policyengine_us import CountryTaxBenefitSystem

    parameters = CountryTaxBenefitSystem().parameters
    categories = (
        parameters.children["gov"]
        .children["hhs"]
        .children["medicaid"]
        .children["eligibility"]
        .children["categories"]
    )

    shared_text = _git_show(SHARED_MODULE)
    if shared_text is None:
        raise SystemExit(f"cannot read {SHARED_MODULE} from {RULESPEC_ROOT} origin/main")

    concepts = []
    aggregates = []
    cases = []
    mismatches = []
    states_compared = set()
    skipped = []

    for code, slug, path in _state_files():
        if code in SKIP_STATES:
            continue
        state_text = _git_show(path)
        if state_text is None:
            skipped.append((code, "unreadable"))
            continue
        values = evaluate_rules([shared_text, state_text])
        prefix = slug.replace("-", "_")

        for suffix, category in SUFFIX_TO_CATEGORY.items():
            rule = f"{prefix}_{suffix}"
            if rule not in values:
                continue
            pe_node = (
                categories.children[category]
                .children["income_limit"]
                .children.get(code.upper())
            )
            if pe_node is None:
                skipped.append((f"{code}:{category}", "no PE node"))
                continue
            axiom_value = values[rule]
            pe_value = float(pe_node(PERIOD))
            tolerance = 1e-9
            matched = abs(axiom_value - pe_value) <= tolerance
            concept_id = f"us-{code}:policies/cms/{slug}-medicaid-chip-bhp-eligibility-levels#{rule}"
            states_compared.add(code.upper())

            concepts.append(
                {
                    "category": "health",
                    "comparison": "amount",
                    "components": [],
                    "description": f"{code.upper()} {category} effective FPL limit",
                    "id": concept_id,
                    "parent": None,
                    "tolerance": tolerance,
                }
            )
            aggregates.append(
                {
                    "category": "health",
                    "comparison": "amount",
                    "comparison_count": 1,
                    "comparison_weight": 1,
                    "components": [],
                    "concept": concept_id,
                    "description": f"{code.upper()} {category} effective FPL limit",
                    "left_weighted_sum": axiom_value,
                    "match_count": 1 if matched else 0,
                    "match_rate": 100.0 if matched else 0.0,
                    "match_weight": 1 if matched else 0,
                    "mismatch_count": 0 if matched else 1,
                    "mismatch_weight": 0 if matched else 1,
                    "missing_both_count": 0,
                    "missing_left_count": 0,
                    "missing_right_count": 0,
                    "parent": None,
                    "right_weighted_sum": pe_value,
                    "tolerance": tolerance,
                    "weighted_difference": axiom_value - pe_value,
                    "weighted_match_rate": 100.0 if matched else 0.0,
                }
            )
            case_id = f"{SUITE}-{code}-{category}"
            case_mismatches = []
            if not matched:
                entry = {
                    "case_id": case_id,
                    "concept": concept_id,
                    "kind": "amount_difference",
                    "left": axiom_value,
                    "right": pe_value,
                    "difference": axiom_value - pe_value,
                }
                case_mismatches.append(entry)
                mismatches.append(entry)
            cases.append(
                {
                    "case_id": case_id,
                    "left_engine": "axiom",
                    "left_errors": [],
                    "match_rate": 100.0 if matched else 0.0,
                    "metadata": {
                        "axiom_rule": rule,
                        "axiom_source": f"rulespec-us/{path}",
                        "dataset": "encoded_parameter_oracle",
                        "policyengine_parameter": (
                            "gov.hhs.medicaid.eligibility.categories."
                            f"{category}.income_limit.{code.upper()}"
                        ),
                        "population": "rulespec-parameters",
                        "period": PERIOD,
                        "state": code.upper(),
                    },
                    "mismatches": case_mismatches,
                    "right_engine": "policyengine",
                    "right_errors": [],
                }
            )

    comparison_count = len(cases)
    mismatch_count = len(mismatches)
    match_count = comparison_count - mismatch_count
    return {
        "aggregates": aggregates,
        "case_count": comparison_count,
        "cases": cases,
        "concepts": concepts,
        "engines": {"left": "axiom", "right": "policyengine"},
        "errors": [],
        "locales": sorted(states_compared),
        "mismatches": mismatches,
        "population": "rulespec-parameters",
        "schema_version": "axiom.comparison_report.v1",
        "scope": {
            "period": PERIOD,
            "source": "rulespec-us us-*/policies/cms (origin/main)",
            "skipped": [f"{a}:{b}" for a, b in skipped],
        },
        "suite": SUITE,
        "summary": {
            "comparison_count": comparison_count,
            "error_count": 0,
            "errors_by_engine": {},
            "match_count": match_count,
            "mismatch_count": mismatch_count,
            "mismatches_by_concept": [
                {"concept": m["concept"], "count": 1} for m in mismatches
            ],
            "mismatches_by_kind": (
                [{"count": mismatch_count, "kind": "amount_difference"}]
                if mismatch_count
                else []
            ),
            "mismatches_by_scenario": {},
            "weighted": {
                "comparison_weight": comparison_count,
                "match_rate": (
                    100.0 * match_count / comparison_count if comparison_count else 0.0
                ),
                "match_weight": match_count,
                "mismatch_weight": mismatch_count,
            },
            "alarms": [],
        },
    }


def main() -> None:
    report = build_report()
    OUTPUT_PATH.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    s = report["summary"]
    states = report["locales"]
    print(f"wrote {OUTPUT_PATH}")
    print(
        f"{s['match_count']}/{s['comparison_count']} effective FPL limits match "
        f"across {len(states)} states"
    )
    by_state: dict[str, list] = {}
    for m in report["mismatches"]:
        st = m["concept"].split(":", 1)[0].removeprefix("us-").upper()
        by_state.setdefault(st, []).append(m)
    for st in sorted(by_state):
        for m in by_state[st]:
            rule = m["concept"].rsplit("#", 1)[-1]
            print(f"  mismatch {st} {rule}: axiom={m['left']} pe={m['right']}")


if __name__ == "__main__":
    main()
