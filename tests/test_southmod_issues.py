"""SOUTHMOD findings ledgers: schema, licence lint, registry and references.

Invariants under test:

- Every registered ledger passes ``ledger_problems`` (closed field allowlist,
  field rules, licence lint), and every ``*_issues.json`` in the package other
  than EUROMOD's is registered.
- The Python registry and the dashboard's SOUTHMOD_MODELS agree on regions,
  models and order.
- A model registered without a ledger has no value mismatch in any of its
  published reports (the dashboard states this).
- Every ``<model>_issues.json#<id>`` citation in the repository resolves.
- Lint monotonicity: inserting a licence-forbidden token into any prose field
  of any real entry makes the ledger fail; benign prose passes.
- Differential: the dashboard's grouping of the published bundle
  (dashboard/src/utils/southmodFindings.mjs) gives the per-model counts Python
  reads from the packaged ledgers, and its scoping and folding hold their
  invariants over every region x single-suite filter.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from axiom_oracles.southmod_issues import (
    ENTRY_KEYS,
    LICENCE_PATTERNS,
    PROSE_FIELDS,
    SOUTHMOD_MODELS,
    ledger_problems,
    licence_hits,
    load_southmod_issues,
    model_for,
)

ROOT = Path(__file__).resolve().parents[1]
LEDGER_MODELS = [m for m in SOUTHMOD_MODELS if m.ledger is not None]
SUITES_JS = ROOT / "dashboard/src/utils/suites.js"


def _ledger(region: str) -> dict:
    ledger = load_southmod_issues(region)
    assert ledger is not None
    return ledger


def dashboard_southmod_models() -> list[tuple[str, str, str]]:
    """(region, model, country) from suites.js SOUTHMOD_MODELS, in order."""
    text = SUITES_JS.read_text(encoding="utf-8")
    start = text.index("export const SOUTHMOD_MODELS = {")
    end = text.index("\n};", start)
    block = text[start:end]
    return re.findall(
        r'^  ([a-z]{2}): \{\n    model: "([^"]+)",\n    country: "([^"]+)",',
        block,
        flags=re.M,
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node runtime not available")
def test_dashboard_findings_helpers_agree_with_python() -> None:
    expected = {
        "models": {
            region: {"model": model, "country": country}
            for region, model, country in dashboard_southmod_models()
        },
        "counts": {m.region: len(_ledger(m.region)["entries"]) for m in LEDGER_MODELS},
    }
    proc = subprocess.run(
        ["node", "scripts/test-southmod-findings.mjs"],
        cwd=ROOT / "dashboard",
        env={**os.environ, "SOUTHMOD_FINDINGS_EXPECTED": json.dumps(expected)},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SOUTHMOD FINDINGS SEMANTICS: true" in proc.stdout


@pytest.mark.parametrize("model", LEDGER_MODELS, ids=lambda m: m.model)
def test_registered_ledger_passes_schema_and_licence_lint(model) -> None:
    assert ledger_problems(model.region, _ledger(model.region)) == []


def test_every_packaged_southmod_ledger_is_registered() -> None:
    packaged = {
        path.name
        for path in (ROOT / "axiom_oracles/data").glob("*_issues.json")
        if path.name != "euromod_issues.json"
    }
    assert packaged == {m.ledger for m in LEDGER_MODELS}


def test_python_registry_matches_dashboard_registry() -> None:
    dashboard = dashboard_southmod_models()
    assert len(dashboard) == len(SOUTHMOD_MODELS)
    assert [(region, model) for region, model, _ in dashboard] == [
        (m.region, m.model) for m in SOUTHMOD_MODELS
    ]


@pytest.mark.parametrize(
    "model",
    [m for m in SOUTHMOD_MODELS if m.ledger is None],
    ids=lambda m: m.model,
)
def test_ledgerless_model_has_no_published_mismatch(model) -> None:
    # The dashboard shows no_ledger_note ("no UGAMOD comparison found a value
    # mismatch"); a mismatch in any of the model's reports falsifies it.
    assert model.no_ledger_note
    reports = sorted(
        (ROOT / "dashboard/public/data").glob(f"axiom-euromod-{model.region}-*.json")
    )
    assert reports, f"no published {model.model} reports"
    for path in reports:
        summary = json.loads(path.read_text())["summary"]
        assert summary["mismatch_count"] == 0, path.name
        assert summary["match_count"] == summary["comparison_count"], path.name


def test_every_ledger_citation_resolves() -> None:
    ids = {
        m.ledger: {e["id"] for e in _ledger(m.region)["entries"]} for m in LEDGER_MODELS
    }
    files = subprocess.run(
        ["git", "ls-files", "dispositions", "comparisons", "axiom_oracles", "docs"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(name) for name in ids) + r")#([a-z0-9-]+)"
    )
    cited = 0
    for name in files:
        path = ROOT / name
        if path.suffix not in {".yaml", ".yml", ".py", ".md", ".json"}:
            continue
        for ledger, entry_id in pattern.findall(path.read_text(encoding="utf-8")):
            cited += 1
            assert entry_id in ids[ledger], f"{name}: {ledger}#{entry_id}"
    assert cited > 0


def _entry_with(region: str, **fields) -> dict:
    ledger = copy.deepcopy(_ledger(region))
    ledger["entries"][0].update(fields)
    return ledger


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda e: e.update(model_parameters="x"), "outside the allowlist"),
        (lambda e: e["observed_with"].update(xml="x"), "outside allowlist"),
        (lambda e: e["observed_with"].update(model_root="EM"), "model_root"),
        (lambda e: e.update(jurisdiction="UG"), "jurisdiction"),
        (lambda e: e.update(status="filed"), "status"),
        (lambda e: e.update(oracle_outputs=["tin_gh"]), "oracle_outputs"),
        (lambda e: e.update(affected_comparisons=["gh-nope"]), "gh-nope"),
        (lambda e: e.update(affected_comparisons=["zm-vat"]), "zm-vat"),
        (lambda e: e.update(affected_concepts=["zm:x#y"]), "affected_concepts"),
        (lambda e: e.update(counts_as_axiom_gap="no"), "counts_as_axiom_gap"),
        (lambda e: e.update(id="tin-s-top-band"), "must start with"),
        (lambda e: e.update(classification="Model Bug"), "classification"),
        (lambda e: e.pop("affected_concepts"), "missing required"),
        (
            lambda e: (e.pop("summary", None), e.pop("observed", None)),
            "summary or observed",
        ),
        (lambda e: e.update(statute=["Act 896"]), "statute must be a string"),
    ],
)
def test_closed_schema_rejects(mutate, expected) -> None:
    ledger = copy.deepcopy(_ledger("gh"))
    mutate(ledger["entries"][0])
    problems = ledger_problems("gh", ledger)
    assert any(expected in p for p in problems), problems


def test_top_level_and_identity_rules() -> None:
    ledger = copy.deepcopy(_ledger("rw"))
    ledger["model_dump"] = {}
    ledger["schema"] = "axiom_oracles.rwamod_issues.v2"
    ledger["entries"].append(copy.deepcopy(ledger["entries"][0]))
    problems = ledger_problems("rw", ledger)
    assert any("top-level keys" in p for p in problems)
    assert any("schema" in p for p in problems)
    assert any("duplicate id" in p for p in problems)
    assert ledger_problems("ug", {}) == ["ug: UGAMOD has no ledger registered"]
    with pytest.raises(KeyError):
        model_for("xx")


#: Strings a ledger must never carry: EUROMOD model content structure and
#: survey-microdata facts. Each must trip exactly the named pattern family.
FORBIDDEN = [
    ("policy_or_unit", "the tin_gh policy"),
    ("policy_or_unit", "unit tu_individual_gh"),
    ("dollar_constant", "rate $tin_rate1"),
    ("euromod_function", "a SchedCalc step"),
    ("euromod_function", "an Elig_cond row"),
    ("condition_syntax", "{IsMarried & dag>=18}"),
    ("condition_syntax", "!{IsDepChild}"),
    ("condition_syntax", "uses nDepChildrenInTu"),
    ("footnote_parameter", "amount#2 applies"),
    ("xml_tag", "<Parameter Name='x'/>"),
    ("guid", "id 3f2504e0-4f89-11d3-9a0c-0305e82c3301"),
    ("income_list_composition", "il_tintb3 = yem + yse"),
    ("microdata_count", "1,204 households in GLSS7"),
    ("microdata_count", "the sample size"),
    ("internal_variable", "the i_tmp_s helper"),
    ("parameter_constant", "tscse_StdRate1"),
    ("local_path", "see /Users/someone/.axiom/oracles"),
]

BENIGN = [
    "Candidate finding #8 (rulespec-zm#1 finding 1).",
    "Minimum Alternative Tax under Proclamation 1395/2025 Article 23.",
    "Store-bought bottled water, probed 2026-10-04.",
    "ils_dispy = 46,518 (60,000 less 13,482 tax).",
    "tin_s = 193,244 at chargeable income 700,000 GHS.",
    "Income Tax (Amendment) (No. 2) Act 2023 (Act 1111) First Schedule.",
    "GETFund levy and NHIL on household expenditure.",
    "dependant_child_count >= 2 on the encoded side.",
]


@pytest.mark.parametrize(("family", "text"), FORBIDDEN)
def test_licence_lint_catches(family: str, text: str) -> None:
    assert LICENCE_PATTERNS[family].search(text), text
    ledger = _entry_with("gh", observed=f"GHAMOD output. {text}")
    assert any(family in hit for hit in licence_hits(ledger))
    assert ledger_problems("gh", ledger)


@pytest.mark.parametrize("text", BENIGN)
def test_licence_lint_passes_benign_prose(text: str) -> None:
    assert licence_hits({"entries": [{"observed": text}]}) == []


def test_licence_lint_scans_keys_and_nested_values() -> None:
    assert licence_hits({"a": {"tin_gh": 1}})
    assert licence_hits({"a": [[{"b": "$x"}]]})


@settings(max_examples=200, deadline=None)
@given(
    model=st.sampled_from(LEDGER_MODELS),
    data=st.data(),
    forbidden=st.sampled_from([text for _, text in FORBIDDEN]),
    field=st.sampled_from(PROSE_FIELDS),
    prefix=st.text(alphabet=" abcdefgh.,;", max_size=20),
)
def test_injecting_forbidden_content_anywhere_fails(
    model, data, forbidden, field, prefix
) -> None:
    """Monotonicity: a clean ledger plus any forbidden token is never clean."""
    ledger = copy.deepcopy(_ledger(model.region))
    index = data.draw(st.integers(0, len(ledger["entries"]) - 1))
    entry = ledger["entries"][index]
    entry[field] = f"{entry.get(field, '')}{prefix} {forbidden}"
    assert ledger_problems(model.region, ledger)


@settings(max_examples=100, deadline=None)
@given(
    model=st.sampled_from(LEDGER_MODELS),
    data=st.data(),
    key=st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=20),
)
def test_any_unlisted_field_is_rejected(model, data, key) -> None:
    assume(key not in ENTRY_KEYS)
    ledger = copy.deepcopy(_ledger(model.region))
    entry = ledger["entries"][data.draw(st.integers(0, len(ledger["entries"]) - 1))]
    entry[key] = "value"
    problems = ledger_problems(model.region, ledger)
    assert any("outside the allowlist" in p for p in problems), problems
