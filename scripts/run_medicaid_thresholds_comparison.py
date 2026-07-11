"""Compare every state's encoded Medicaid/CHIP eligibility levels against PolicyEngine.

The corpus encodes one CMS eligibility-levels file per state
(``us-XX/policies/cms/<state>-medicaid-chip-bhp-eligibility-levels.yaml``)
with per-category FPL limits plus ``*_effective_fpl_limit`` deriveds that
add the shared MAGI 5% disregard. PolicyEngine carries the same table as
``gov.hhs.medicaid.eligibility.categories.<category>.income_limit.<STATE>``.

This runner discovers state files under one explicitly supplied canonical
rulespec-us checkout, executes each through Axiom (including its shared federal
disregard import), and compares every effective limit both sides model.

Output: ``axiom.comparison_report.v1`` JSON at
``dashboard/public/data/axiom-policyengine-medicaid-thresholds-states.json``.

Usage:
    uv run python scripts/run_medicaid_thresholds_comparison.py \
      --rulespec-root ~/TheAxiomFoundation/rulespec-us \
      --axiom-binary ~/TheAxiomFoundation/axiom-rules-engine/target/release/axiom-rules-engine
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from canonical_rulespec_runtime import parse_canonical_runtime_args

from axiom_oracles.bridges.parameter_runtime import evaluate_rulespec_outputs
from axiom_oracles.bridges.repo_routing import canonical_rulespec_module_path

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


def _state_files(rulespec_root: Path) -> list[tuple[str, str, Path]]:
    """Return canonical state CMS modules from the explicit checkout."""

    out = []
    pattern = "us-??/policies/cms/*-medicaid-chip-bhp-eligibility-levels.*"
    for path in rulespec_root.glob(pattern):
        if path.is_symlink():
            raise ValueError(f"symlinked RuleSpec module is unsupported: {path}")
        if path.is_file() and path.suffix == ".yml":
            raise ValueError(f"legacy .yml RuleSpec module is unsupported: {path}")
        if not path.is_file() or path.suffix != ".yaml":
            continue
        relative = path.relative_to(rulespec_root).as_posix()
        match = STATE_FILE_RE.fullmatch(relative)
        if match:
            content_root = rulespec_root / f"us-{match.group('code')}"
            if canonical_rulespec_module_path(path, content_root=content_root) is None:
                raise ValueError(f"noncanonical RuleSpec module path: {path}")
            out.append((match.group("code"), match.group("slug"), path))
    return sorted(out)


def build_report(*, rulespec_root: Path, axiom_binary: Path) -> dict:
    from policyengine_us import CountryTaxBenefitSystem

    parameters = CountryTaxBenefitSystem().parameters
    categories = (
        parameters.children["gov"]
        .children["hhs"]
        .children["medicaid"]
        .children["eligibility"]
        .children["categories"]
    )

    concepts = []
    aggregates = []
    cases = []
    mismatches = []
    states_compared = set()
    skipped = []

    for code, slug, path in _state_files(rulespec_root):
        if code in SKIP_STATES:
            continue
        prefix = slug.replace("-", "_")
        rule_names = {
            rule.get("name")
            for rule in (yaml.safe_load(path.read_text()).get("rules") or [])
        }
        rules = [
            f"{prefix}_{suffix}"
            for suffix in SUFFIX_TO_CATEGORY
            if f"{prefix}_{suffix}" in rule_names
        ]
        module_ref = (
            f"us-{code}:policies/cms/{slug}-medicaid-chip-bhp-eligibility-levels"
        )
        output_ids = [f"{module_ref}#{rule}" for rule in rules]
        executed = evaluate_rulespec_outputs(
            path,
            output_ids,
            rulespec_root=rulespec_root,
            axiom_binary=axiom_binary,
            period="2026",
        )
        values = {
            rule: float(executed[output_id])
            for rule, output_id in zip(rules, output_ids, strict=True)
        }

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
                        "axiom_source": path.relative_to(rulespec_root).as_posix(),
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
            "source": "canonical rulespec-us us-*/policies/cms",
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


def main(argv: list[str] | None = None) -> None:
    rulespec_root, axiom_binary = parse_canonical_runtime_args(argv, country="us")
    report = build_report(
        rulespec_root=rulespec_root,
        axiom_binary=axiom_binary,
    )
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
