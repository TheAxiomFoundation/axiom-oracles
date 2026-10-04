"""SOUTHMOD findings ledgers shipped with axiom-oracles.

Each SOUTHMOD country model (UNU-WIDER, run on the EUROMOD engine) whose
comparison suites surfaced model behaviour worth recording has a ledger at
``axiom_oracles/data/<model>_issues.json`` (schema
``axiom_oracles.<model>_issues.v1``). ``scripts/publish_issue_ledgers.py``
publishes them to the dashboard and gates the published copy in CI.

The SOUTHMOD_A4.0 Adhesion Agreement bars redistributing the model bundle or
its input data, so a ledger may hold only what Axiom observed: model outputs
on synthetic households, input and output variable names, and statutory
citations. ``ledger_problems`` enforces that shape before anything is
published: a closed field allowlist (so a new field cannot carry model
content in unreviewed) plus a lint for the structural tokens EUROMOD model
content is made of (policy and function names, parameter constants,
condition syntax, GUIDs, XML) and for survey-microdata counts. The lint is a
tripwire, not proof: it cannot tell a copied sentence from an original one,
so ledger edits still need a reader who knows the licence.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class SouthmodModel:
    """One SOUTHMOD country model the dashboard publishes."""

    #: Suite-slug prefix and dashboard region (dashboard/src/utils/suites.js
    #: SOUTHMOD_MODELS keys); also the lower-case ledger jurisdiction.
    region: str
    model: str
    #: Ledger file under axiom_oracles/data/, or None when no ledger exists.
    ledger: str | None
    #: Why there is no ledger (required when ``ledger`` is None).
    no_ledger_note: str | None = None


#: In dashboard SOUTHMOD_MODELS order. tests/test_southmod_issues.py checks
#: this table against the dashboard's registry.
SOUTHMOD_MODELS: tuple[SouthmodModel, ...] = (
    SouthmodModel("gh", "GHAMOD", "ghamod_issues.json"),
    SouthmodModel(
        "ug",
        "UGAMOD",
        None,
        no_ledger_note=(
            "No findings ledger: no UGAMOD comparison found a value mismatch "
            "(axiom_oracles/bridges/mappings/ug.yaml)."
        ),
    ),
    SouthmodModel("zm", "MicroZAMOD", "microzamod_issues.json"),
    SouthmodModel("et", "ETMOD", "etmod_issues.json"),
    SouthmodModel("rw", "RWAMOD", "rwamod_issues.json"),
)

LEDGER_KEYS = frozenset({"schema", "updated_at", "purpose", "entries"})

#: Every field an entry may carry. Closed on purpose: adding one is a licence
#: review, made here, not a silent addition to the published copy.
ENTRY_KEYS = frozenset(
    {
        "id",
        "classification",
        "counts_as_axiom_gap",
        "jurisdiction",
        "observed_with",
        "oracle_scope",
        "status",
        "summary",
        "observed",
        "statute",
        "axiom_position",
        "statutory_evidence_gap",
        "reported_upstream",
        "oracle_outputs",
        "affected_comparisons",
        "affected_concepts",
    }
)
REQUIRED_ENTRY_KEYS = frozenset(
    {
        "id",
        "classification",
        "counts_as_axiom_gap",
        "jurisdiction",
        "observed_with",
        "affected_comparisons",
        "affected_concepts",
    }
)
OBSERVED_WITH_KEYS = frozenset(
    {"country", "system", "dataset", "model_root", "reproduction_note"}
)
MODEL_ROOT = "SOUTHMOD_A4.0"
#: The dashboard styles each of these; a new status needs a label there too.
STATUSES = frozenset({"observed_local", "upstream_filed", "not_reproduced_live"})
ORACLE_SCOPES = frozenset({"household_level"})
PROSE_FIELDS = (
    "summary",
    "observed",
    "statute",
    "axiom_position",
    "statutory_evidence_gap",
    "reported_upstream",
)

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
#: Simulated outputs (``tin_s``) and income lists (``ils_dispy``).
_OUTPUT_VARIABLE = re.compile(r"^(?:[a-z][a-z0-9]*_s|ils?_[a-z0-9_]+)$")

_COMPARE = r"(?:>=|<=|!=|==|<>|=|<|>)"
_RELATIONAL = r"(?:>=|<=|!=|==|<>|<|>)"

#: Tripwires for the tokens EUROMOD model content is written in, and for
#: survey-microdata counts. A hit is not proof of copying: a few benign
#: phrasings also trip them (a parenthesised "(age >= 15)", "issue#4"), and
#: those need rephrasing ("aged 15 or over", "issue 4"), never an exemption
#: in the ledger. Equally, a miss is not proof of absence (see the module
#: docstring).
LICENCE_PATTERNS: dict[str, re.Pattern[str]] = {
    "guid": re.compile(r"\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b"),
    "xml_tag": re.compile(r"</?[A-Za-z][\w:.-]*(?:\s[^<>]*)?/?>"),
    "dollar_constant": re.compile(r"\$[A-Za-z_]\w*"),
    "euromod_function": re.compile(
        r"\b(?:DefConst|DefVar|DefIL|DefTU|ArithOp|BenCalc|SchedCalc|UnitLoop"
        r"|DefOutput|ChangeParam|ChangeSwitch|IlArithOp|AddHHMembers"
        r"|CallProgramme|DropUnit|KeepUnit|RandSeed|SetDefault|DefInput)\b"
        r"|\b(?:Elig|Min|Max|Allocate|Loop|Uprate|Store|Restore|Totals|Scale)"
        r"(?=[_\[])"
    ),
    # Policy names (tin_gh, output_std_hh_gh, tin_gh_2025) and tax-unit names
    # (tu_individual_gh).
    "policy_or_unit": re.compile(
        r"\b[A-Za-z][A-Za-z0-9_]*_(?:gh|ug|zm|et|rw|GH|UG|ZM|ET|RW)(?![A-Za-z0-9])"
        r"|\btu_[A-Za-z]\w*"
    ),
    # Braced conditions ({IsMarried & dag>=18}, ETMOD) and the brace-less form
    # the GH, UG, ZM and RW models use: comparisons joined by & or |, and a
    # parenthesised relational test.
    "condition_syntax": re.compile(
        r"\{[^{}]*(?:[<>]=?|[!=]=|=|&|\|)[^{}]*\}|!\{|!\s*\(|&&|\|\|"
        r"|\{[A-Z][A-Za-z]+\}|\b(?:Is|Has|Get)[A-Z][a-z]+[A-Za-z]*\b"
        r"|\bn[A-Z][A-Za-z]*(?:InTu|InHH|InUnit)\b|#_[A-Z][A-Za-z]+"
        rf"|\b[a-z]\w*\s*{_COMPARE}\s*[\w$#.]+\s*\)?\s*[&|]"
        rf"|[&|]\s*\(?\s*[a-z]\w*\s*{_COMPARE}\s*[\w$#.]"
        rf"|\(\s*[a-z]\w*\s*{_RELATIONAL}\s*[\w$#.]+\s*\)"
    ),
    # Formula text: an unspaced relational test (dag>15; prose spaces its
    # operators, and an input value on a synthetic household is written
    # lfo=1, which stays allowed), a sum of four or more variable names, and
    # a (a)*(b/c) proration.
    "formula_syntax": re.compile(
        r"\b[a-z][a-z0-9_]*(?:>=|<=|!=|<>|<|>)-?[\w$.]"
        r"|\b[a-z][a-z0-9_]*(?:\s*\+\s*[a-z][a-z0-9_]*){3,}"
        r"|\(\s*[a-z]\w*\s*\)\s*\*\s*\(\s*[a-z]\w*\s*/\s*[a-z]\w*\s*\)"
    ),
    # Footnote parameters (amount#2); issue references (rulespec-zm#1, PR#592)
    # and prose numbering ("finding #8") are not.
    "footnote_parameter": re.compile(r"(?<![\w/-])[a-z_][a-z0-9_]*#\d+"),
    "internal_variable": re.compile(r"\bi_[a-z]\w*"),
    "parameter_constant": re.compile(
        r"\b[a-z]{2,}\w*_[A-Z][A-Za-z0-9]*\b"
        r"|\b\w+_(?:uprate|Rate\d*|Thres\w*|UpLim|LowLim|Amount\d*)\b"
    ),
    "income_list_composition": re.compile(
        r"\bils?_\w+\s*(?:=|==|:=|:|equals|is the sum of|comprises|consists of)"
        r"\s*[a-z]\w*(?:\s*[+-]\s*[a-z]\w*)+"
    ),
    # Counts drawn from the survey microdata behind a model's input data.
    "microdata_count": re.compile(
        r"(?i)\b\d[\d,.]*\s*(?:%\s*of\s+(?:the\s+)?)?(?:households?|individuals?"
        r"|persons?|observations?|records?|respondents?|people|rows?)\s+"
        r"(?:in|of|from)\s+(?:the\s+)?(?:dataset|survey|sample|microdata"
        r"|input data|GLSS\w*|LCMS\w*|UNHS\w*|ESPS\w*|[a-z]{2}_\d{4}_a\d+)"
        r"|\b(?:input data|microdata|survey|sample|dataset|GLSS\w*|LCMS\w*"
        r"|UNHS\w*|ESPS\w*)\b[^.;]{0,40}?\b\d[\d,.]*\s*(?:households?"
        r"|individuals?|persons?|observations?|records?|respondents?)\b"
        r"|\b(?:population[- ]weighted|sample size|(?:mean|average|survey"
        r"|sampling) weights?)\b"
    ),
    # Machine-local paths (the licensed bundle lives on one machine); a URL
    # whose path contains /home/ is not one.
    "local_path": re.compile(r"(?:^|[\s(\[\'\"`])(?:/Users/|/home/|~/)|\b[A-Za-z]:\\"),
}


def load_southmod_issues(region: str) -> dict[str, Any] | None:
    """Return the packaged findings ledger for a SOUTHMOD region, or None."""
    model = model_for(region)
    if model.ledger is None:
        return None
    payload = (
        resources.files("axiom_oracles.data")
        .joinpath(model.ledger)
        .read_text(encoding="utf-8")
    )
    return json.loads(payload)


def model_for(region: str) -> SouthmodModel:
    for model in SOUTHMOD_MODELS:
        if model.region == region:
            return model
    raise KeyError(f"unknown SOUTHMOD region {region!r}")


def _strings(value: Any, path: str):
    """Yield (path, string) for every string under ``value``, keys included."""
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield f"{path}.<key>", str(key)
            yield from _strings(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _strings(item, f"{path}[{index}]")


def _non_finite(value: Any, path: str):
    """Yield the path of every NaN or infinite float under ``value``."""
    if isinstance(value, float) and not math.isfinite(value):
        yield path
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _non_finite(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _non_finite(item, f"{path}[{index}]")


def licence_hits(ledger: Any) -> list[str]:
    """Every licence-pattern hit in any string of the ledger, as messages."""
    hits = []
    for path, text in _strings(ledger, "$"):
        for name, pattern in LICENCE_PATTERNS.items():
            for match in pattern.finditer(text):
                hits.append(f"{path}: {name} {match.group(0)!r}")
    return hits


def _entry_problems(
    model: SouthmodModel,
    entry: Any,
    where: str,
    comparisons_dir: Path,
) -> list[str]:
    if not isinstance(entry, dict):
        return [f"{where}: entry is not an object"]
    problems = []
    unknown = sorted(set(entry) - ENTRY_KEYS)
    if unknown:
        problems.append(f"{where}: fields outside the allowlist: {unknown}")
    missing = sorted(REQUIRED_ENTRY_KEYS - set(entry))
    if missing:
        problems.append(f"{where}: missing required fields: {missing}")

    stem = Path(model.ledger or "").name.removesuffix("_issues.json")
    entry_id = entry.get("id")
    if not isinstance(entry_id, str) or not _SLUG.match(entry_id):
        problems.append(f"{where}: id must be a lower-case slug, got {entry_id!r}")
    elif not entry_id.startswith(f"{stem}-"):
        problems.append(f"{where}: id {entry_id!r} must start with '{stem}-'")

    classification = entry.get("classification")
    if not isinstance(classification, str) or not _SNAKE.match(classification):
        problems.append(
            f"{where}: classification must be snake_case, got {classification!r}"
        )
    if "counts_as_axiom_gap" in entry and not (
        entry["counts_as_axiom_gap"] is None
        or isinstance(entry["counts_as_axiom_gap"], bool)
    ):
        problems.append(f"{where}: counts_as_axiom_gap must be true, false or null")
    jurisdiction = model.region.upper()
    if entry.get("jurisdiction") != jurisdiction:
        problems.append(
            f"{where}: jurisdiction {entry.get('jurisdiction')!r} != {jurisdiction!r}"
        )
    status = entry.get("status")
    if "status" in entry and (not isinstance(status, str) or status not in STATUSES):
        problems.append(f"{where}: status {status!r} not in {sorted(STATUSES)}")
    scope = entry.get("oracle_scope")
    if "oracle_scope" in entry and (
        not isinstance(scope, str) or scope not in ORACLE_SCOPES
    ):
        problems.append(f"{where}: oracle_scope {scope!r} unknown")
    if not any(
        isinstance(entry.get(f), str) and entry[f] for f in ("summary", "observed")
    ):
        problems.append(f"{where}: needs a non-empty summary or observed")
    for field in PROSE_FIELDS:
        if field in entry and not isinstance(entry[field], str):
            problems.append(f"{where}: {field} must be a string")

    observed_with = entry.get("observed_with")
    if not isinstance(observed_with, dict):
        problems.append(f"{where}: observed_with must be an object")
    else:
        unknown = sorted(set(observed_with) - OBSERVED_WITH_KEYS)
        if unknown:
            problems.append(
                f"{where}: observed_with fields outside allowlist: {unknown}"
            )
        # Every value is a plain string: a nested object or a number here
        # would carry content past the allowlist and break the page.
        for key, value in observed_with.items():
            if not isinstance(value, str) or not value:
                problems.append(
                    f"{where}: observed_with.{key} must be a non-empty string"
                )
        if observed_with.get("model_root") != MODEL_ROOT:
            problems.append(f"{where}: observed_with.model_root must be {MODEL_ROOT!r}")
        if observed_with.get("country") != jurisdiction:
            problems.append(f"{where}: observed_with.country must be {jurisdiction!r}")
        system = observed_with.get("system")
        if not isinstance(system, str) or not re.fullmatch(
            rf"{jurisdiction}_\d{{4}}", system
        ):
            problems.append(f"{where}: observed_with.system {system!r} malformed")
        # A registered dataset name, optionally with a digit-free note (no
        # room for a survey count): "rw_2024_a1 (registered name; ...)".
        dataset = observed_with.get("dataset")
        if not isinstance(dataset, str) or not re.match(
            rf"{model.region}_\d{{4}}_a\d+(?: \([^0-9()]*\))?$", dataset
        ):
            problems.append(f"{where}: observed_with.dataset {dataset!r} malformed")

    outputs = entry.get("oracle_outputs", [])
    if not isinstance(outputs, list) or not all(
        isinstance(o, str) and _OUTPUT_VARIABLE.match(o) for o in outputs
    ):
        problems.append(
            f"{where}: oracle_outputs must list output variables "
            f"(<name>_s or il(s)_<name>), got {outputs!r}"
        )
    comparisons = entry.get("affected_comparisons", [])
    if not isinstance(comparisons, list) or not all(
        isinstance(c, str) for c in comparisons
    ):
        problems.append(f"{where}: affected_comparisons must be a list of names")
    else:
        for name in comparisons:
            if (
                not name.startswith(f"{model.region}-")
                or not (comparisons_dir / f"{name}.yaml").is_file()
            ):
                problems.append(
                    f"{where}: affected comparison {name!r} has no "
                    f"comparisons/{name}.yaml in this model's suites"
                )
    concepts = entry.get("affected_concepts", [])
    if not isinstance(concepts, list) or not all(
        isinstance(c, str) and c.startswith(f"{model.region}:") for c in concepts
    ):
        problems.append(
            f"{where}: affected_concepts must be '{model.region}:' legal ids"
        )
    return problems


def ledger_problems(
    region: str,
    ledger: Any,
    *,
    comparisons_dir: Path | None = None,
) -> list[str]:
    """Everything that bars publishing a SOUTHMOD ledger; empty when clean."""
    model = model_for(region)
    if model.ledger is None:
        return [f"{region}: {model.model} has no ledger registered"]
    comparisons_dir = comparisons_dir or REPO_ROOT / "comparisons"
    name = model.ledger
    if not isinstance(ledger, dict):
        return [f"{name}: ledger is not an object"]
    problems = []
    if set(ledger) != LEDGER_KEYS:
        problems.append(
            f"{name}: top-level keys {sorted(ledger)} != {sorted(LEDGER_KEYS)}"
        )
    schema = f"axiom_oracles.{name.removesuffix('.json')}.v1"
    if ledger.get("schema") != schema:
        problems.append(f"{name}: schema {ledger.get('schema')!r} != {schema!r}")
    updated_at = ledger.get("updated_at")
    if not isinstance(updated_at, str) or not _DATE.match(updated_at):
        problems.append(f"{name}: updated_at must be YYYY-MM-DD")
    if not isinstance(ledger.get("purpose"), str):
        problems.append(f"{name}: purpose must be a string")
    for path in _non_finite(ledger, "$"):
        problems.append(f"{name} {path}: non-finite number (not valid JSON)")
    entries = ledger.get("entries")
    if not isinstance(entries, list) or not entries:
        problems.append(f"{name}: entries must be a non-empty list")
        entries = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        where = f"{name} entries[{index}]"
        problems.extend(_entry_problems(model, entry, where, comparisons_dir))
        entry_id = entry.get("id") if isinstance(entry, dict) else None
        if isinstance(entry_id, str):
            if entry_id in seen:
                problems.append(f"{where}: duplicate id {entry_id!r}")
            seen.add(entry_id)
    problems.extend(f"{name} {hit}" for hit in licence_hits(ledger))
    return problems
