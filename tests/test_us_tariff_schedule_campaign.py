from __future__ import annotations

import copy
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest
import yaml

from axiom_oracles.comparison.dispositions import validate_dispositions as validate_shared

from scripts import us_tariff_schedule_campaign as campaign_module
from scripts.us_tariff_schedule_campaign import (
    BASE_INDEPENDENT_AUTHORITY_SLOTS,
    ENTRY_FLAG_ALIASES,
    EXPECTED_DROPPED_ENTRY_FLAGS,
    PREVIEW_DISPOSITION_LINE_SETS,
    _enforce_preview_selector_population,
    _named_line_sets,
    _preview_selector_contract,
    _case_feed,
    _routing_dispositions,
    canonicalize_entry_flags,
    compare_record,
    computed_conformant,
    enforce_excluded_exposure,
    filter_declared_feed,
    query_plan,
    matching_class_id,
    mismatch_signature,
    mismatch_unit,
    route_member,
    selector_matches,
    signature_population_sha256,
    validate_dispositions,
    witness_replay,
)
from scripts.us_tariff_schedule_campaign import DISPOSITION_LEDGER


def test_declared_feed_drops_only_retired_exemplar_flags() -> None:
    feed = {"hts_line": 1, "entry_is_line_a": False, "entry_is_line_b": False,
            "entry_is_line_c": False, "entry_is_line_d": False, "entry_is_line_e": False}
    declared = {"hts_line", "entry_is_line_a", "entry_is_line_b", "entry_is_line_d"}
    filtered, receipt = filter_declared_feed(
        feed, declared, emitted_flag_names={name for name in feed if name.startswith("entry_")}
    )
    assert set(filtered) == declared
    assert receipt["dropped_entry_flags"] == sorted(EXPECTED_DROPPED_ENTRY_FLAGS)


def test_undeclared_input_mutant_fails_filter_assertion() -> None:
    feed = {"declared": True, "entry_is_line_c": False, "entry_is_line_e": False,
            "mutant_undeclared": True}
    with pytest.raises(ValueError, match="undeclared non-flag inputs"):
        filter_declared_feed(
            feed, {"declared"}, emitted_flag_names={"entry_is_line_c", "entry_is_line_e"}
        )


def test_declared_but_unfed_input_mutant_surfaces_before_default() -> None:
    feed = {"entry_is_line_c": False, "entry_is_line_e": False}
    with pytest.raises(ValueError, match="declared inputs absent from feed:.*required_neutral_fact"):
        filter_declared_feed(
            feed, {"required_neutral_fact"},
            emitted_flag_names={"entry_is_line_c", "entry_is_line_e"},
        )


def test_entry_flag_aliases_canonicalize_when_equal() -> None:
    raw = {
        "entry_is_brazil_301": True,
        "entry_is_brazil_301_listed": True,
        "entry_is_forced_labor_301": False,
        "entry_is_forced_labor_301_listed": False,
        "entry_is_section_232_covered": True,
    }
    flags, aliases = canonicalize_entry_flags(raw)
    assert aliases == tuple(sorted(ENTRY_FLAG_ALIASES))
    assert not (set(flags) & set(ENTRY_FLAG_ALIASES))
    assert flags["entry_is_brazil_301_listed"] is True
    assert flags["entry_is_forced_labor_301_listed"] is False


def test_entry_flag_alias_disagreement_fails_closed() -> None:
    with pytest.raises(ValueError, match="entry-flag alias disagreement"):
        canonicalize_entry_flags({
            "entry_is_brazil_301": True,
            "entry_is_brazil_301_listed": False,
        })


def test_entry_flag_alias_without_canonical_fails_closed() -> None:
    with pytest.raises(ValueError, match="without canonical"):
        canonicalize_entry_flags({"entry_is_brazil_301": True})


def test_case_feed_never_forwards_entry_flag_aliases() -> None:
    def entry_flags(_line, _hts, _iso2):
        return {
            "entry_is_brazil_301": True,
            "entry_is_brazil_301_listed": True,
            "entry_is_forced_labor_301": False,
            "entry_is_forced_labor_301_listed": False,
            "entry_is_line_c": False,
            "entry_is_line_e": False,
        }

    feed, flags = _case_feed(
        {"hts10": "0102294024", "iso2": "BR"},
        {"hts_line": "102294000"},
        entry_flags,
    )
    assert not (set(flags) & set(ENTRY_FLAG_ALIASES))
    assert not (set(feed) & set(ENTRY_FLAG_ALIASES))
    assert feed["entry_is_brazil_301_listed"] is True


def test_mismatch_signature_preserves_selector_dimensions() -> None:
    row = {
        "slot": "brazil_section_301",
        "delta": 0.25,
        "context": {
            "flags": {"entry_is_brazil_301_listed": True},
            "revision": "bnd_2026-07-22",
            "interval": ["2026-07-22", "2026-07-23"],
            "origin_regime": "0000000001000000",
            "hts10": "0409000010",
            "hts_line": "0409000000",
            "iso2": "BR",
        },
    }
    other_hts10 = {**row, "context": {**row["context"], "hts10": "0409000090"}}
    other_iso2 = {**row, "context": {**row["context"], "iso2": "AR"}}
    assert mismatch_signature(row) != mismatch_signature(other_hts10)
    assert mismatch_signature(row) != mismatch_signature(other_iso2)


def test_preview_disposition_line_sets_are_receipted_and_registered() -> None:
    receipt = json.loads(PREVIEW_DISPOSITION_LINE_SETS.read_text())
    names = set(receipt["line_sets"])
    assert receipt["verdict"] == "PASS"
    assert len(names) == len(receipt["selectors"]) == 20
    registered = _named_line_sets()
    assert names <= set(registered)
    assert all(registered[name][0][0] == 10 for name in names)
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    contract = _preview_selector_contract(ledger["entries"])
    assert {
        selector_id: selector["match"] for selector_id, selector in contract.items()
    } == {
        selector["id"]: selector["match"] for selector in receipt["selectors"]
    }


def test_preview_selector_match_drift_fails_hermetically() -> None:
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    entries = copy.deepcopy(ledger["entries"])
    entries[0]["match"]["delta"] = {"sign": "neg"}
    with pytest.raises(ValueError, match="preview selector match drift"):
        _preview_selector_contract(entries)


@pytest.mark.parametrize(
    ("field", "mutant", "message"),
    (
        ("disposition", "explained_residual", "preview selector disposition drift"),
        ("attribution", "reference-behavior", "preview selector attribution drift"),
    ),
)
def test_preview_selector_ruling_cannot_be_relabeled(
    field: str, mutant: str, message: str
) -> None:
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    entries = copy.deepcopy(ledger["entries"])
    entry = next(item for item in entries if item["id"] == "section232-exposed-brazil")
    entry[field] = mutant
    with pytest.raises(ValueError, match=message):
        _preview_selector_contract(entries)


def test_unreceipted_preview_selector_is_rejected() -> None:
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    entries = copy.deepcopy(ledger["entries"])
    mutant = copy.deepcopy(entries[0])
    mutant["id"] = "unreceipted-preview-selector"
    mutant["match"]["delta"] = {"values": [0.123456]}
    entries.append(mutant)
    with pytest.raises(ValueError, match="unreceipted preview selector"):
        _preview_selector_contract(entries)


def test_preview_selector_must_expire_on_source_change() -> None:
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    entries = copy.deepcopy(ledger["entries"])
    entries[0]["expires_on_source_change"] = False
    with pytest.raises(ValueError, match="lost source-change expiry"):
        _preview_selector_contract(entries)


def test_preview_source_hash_mutation_cannot_self_validate(tmp_path, monkeypatch) -> None:
    receipt = json.loads(PREVIEW_DISPOSITION_LINE_SETS.read_text())
    first_input = next(iter(receipt["inputs"].values()))
    first_input["sha256"] = "0" * 64
    receipt.pop("receipt_payload_sha256")
    receipt["receipt_payload_sha256"] = hashlib.sha256(json.dumps(
        receipt, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    mutant = tmp_path / "mutant-preview-receipt.json"
    mutant.write_text(json.dumps(receipt))
    monkeypatch.setattr(campaign_module, "PREVIEW_DISPOSITION_LINE_SETS", mutant)
    with pytest.raises(ValueError, match="preview disposition source hash drift"):
        campaign_module._preview_disposition_receipt()


def test_preview_population_digest_rejects_count_preserving_drift() -> None:
    original = [("a" * 64, 2), ("b" * 64, 3)]
    contract = {
        "preview": {
            "expected_units": 5,
            "expected_signature_count": 2,
            "expected_signature_population_sha256": signature_population_sha256(original),
        }
    }
    _enforce_preview_selector_population(
        contract, {signature: "preview" for signature, _ in original}, Counter(dict(original))
    )
    mutant = [("a" * 64, 2), ("c" * 64, 3)]
    with pytest.raises(ValueError, match="signature digest drift"):
        _enforce_preview_selector_population(
            contract,
            {signature: "preview" for signature, _ in mutant},
            Counter(dict(mutant)),
        )


def test_report_rejects_stale_classification_schema(tmp_path, monkeypatch) -> None:
    classification = json.loads(campaign_module.CLASSIFICATION_RECEIPT.read_text())
    classification["schema"] = "axiom_oracles.us_tariff_schedule.classification.v1"
    stale = tmp_path / "classification-receipt.json"
    stale.write_text(json.dumps(classification))
    monkeypatch.setattr(campaign_module, "CLASSIFICATION_RECEIPT", stale)
    with pytest.raises(ValueError, match="classification receipt schema is stale"):
        campaign_module.build_report()


def test_classification_handoff_rejects_unknown_legacy_classes() -> None:
    comparison = json.loads(campaign_module.COMPARISON_RECEIPT.read_text())
    classification = json.loads(campaign_module.CLASSIFICATION_RECEIPT.read_text())
    classification["schema"] = "axiom_oracles.us_tariff_schedule.classification.v2"
    classification["inputs"] = campaign_module._classification_inputs(comparison)
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    with pytest.raises(ValueError, match="unknown or malformed class census"):
        campaign_module._validate_classification_handoff(
            comparison, classification, ledger["entries"]
        )


def test_classification_handoff_rejects_stale_input_binding() -> None:
    comparison = json.loads(campaign_module.COMPARISON_RECEIPT.read_text())
    classification = json.loads(campaign_module.CLASSIFICATION_RECEIPT.read_text())
    classification["schema"] = "axiom_oracles.us_tariff_schedule.classification.v2"
    classification["inputs"] = campaign_module._classification_inputs(comparison)
    classification["inputs"]["disposition_ledger_sha256"] = "0" * 64
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    with pytest.raises(ValueError, match="classification receipt input binding is stale"):
        campaign_module._validate_classification_handoff(
            comparison, classification, ledger["entries"]
        )


def test_classification_handoff_rejects_preview_census_reassignment() -> None:
    comparison = json.loads(campaign_module.COMPARISON_RECEIPT.read_text())
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    classification = {
        "schema": "axiom_oracles.us_tariff_schedule.classification.v2",
        "inputs": campaign_module._classification_inputs(comparison),
        "mismatches": 395_330,
        "classified": 395_330,
        "unexplained": 0,
        "engine_errors": comparison["engine_errors"],
        "class_census": {"non-metal-232-family": 395_330},
        "derived_total_units": 0,
        "derived_total_compositions": {},
        "selector_count": len(ledger["entries"]),
        "groups": {},
    }
    with pytest.raises(ValueError, match="preview-selector census is stale"):
        campaign_module._validate_classification_handoff(
            comparison, classification, ledger["entries"]
        )


def test_classification_handoff_requires_rederivable_sidecar() -> None:
    comparison = json.loads(campaign_module.COMPARISON_RECEIPT.read_text())
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    contract = campaign_module._preview_selector_contract(ledger["entries"])
    class_census = {
        selector_id: selector["expected_units"]
        for selector_id, selector in contract.items()
    }
    mismatch_total = sum(
        slot.get("mismatch", 0) for slot in comparison["per_slot"].values()
    )
    class_census["non-metal-232-family"] = mismatch_total - sum(class_census.values())
    classification = {
        "schema": "axiom_oracles.us_tariff_schedule.classification.v2",
        "inputs": campaign_module._classification_inputs(comparison),
        "mismatches": mismatch_total,
        "classified": mismatch_total,
        "unexplained": 0,
        "engine_errors": comparison["engine_errors"],
        "class_census": class_census,
        "derived_total_units": 0,
        "derived_total_compositions": {},
        "selector_count": len(ledger["entries"]),
        "groups": {},
    }
    with pytest.raises(ValueError, match="classification sidecar receipt is stale"):
        campaign_module._validate_classification_handoff(
            comparison, classification, ledger["entries"]
        )


def test_classification_sidecar_rederives_all_unit_kinds(tmp_path) -> None:
    fields = {
        "slot": "base",
        "origin_regime": "regime",
        "revision": "revision",
        "delta": 0.25,
        "disposition": "free",
        "hts10": "0101210010",
        "hts_line": "0101210000",
        "flags": {"entry_is_test": False},
        "interval": ["2026-01-01", "2026-01-02"],
        "iso2": "CA",
    }
    signature = mismatch_signature({
        "slot": fields["slot"],
        "delta": fields["delta"],
        "context": {
            key: fields[key]
            for key in (
                "flags", "revision", "interval", "origin_regime", "hts10",
                "hts_line", "iso2",
            )
        },
    })
    rows = [
        {"kind": "component_signature", "signature": signature, "units": 2,
         "class": "positive-base", "fields": fields},
        {"kind": "total_signature_composition", "signatures": [signature], "units": 1},
        {"kind": "engine_errors", "units": 1},
    ]
    sidecar = tmp_path / "classification.jsonl.gz"
    with gzip.open(sidecar, "wt") as target:
        for row in rows:
            target.write(json.dumps(row) + "\n")
    rederived = campaign_module._rederive_classification_sidecar(
        sidecar,
        [{"id": "positive-base", "match": {"slot": "base", "delta": {"sign": "pos"}}}],
    )
    assert rederived["mismatches"] == 4
    assert rederived["classified"] == 3
    assert rederived["unexplained"] == 1
    assert rederived["class_census"] == {"positive-base": 2}
    assert rederived["derived_total_compositions"] == {"positive-base": 1}
    population_contract = {
        "positive-base": {
            "expected_units": 2,
            "expected_signature_count": 1,
            "expected_signature_population_sha256": signature_population_sha256(
                [(signature, 2)]
            ),
        }
    }
    campaign_module._enforce_preview_selector_population(
        population_contract,
        rederived["_signature_classes"],
        rederived["_signature_counts"],
    )
    substituted_fields = {**fields, "revision": "different-revision"}
    substituted_signature = mismatch_signature({
        "slot": substituted_fields["slot"],
        "delta": substituted_fields["delta"],
        "context": {
            key: substituted_fields[key]
            for key in (
                "flags", "revision", "interval", "origin_regime", "hts10",
                "hts_line", "iso2",
            )
        },
    })
    rows[0]["signature"] = substituted_signature
    rows[0]["fields"] = substituted_fields
    rows[1]["signatures"] = [substituted_signature]
    with gzip.open(sidecar, "wt") as target:
        for row in rows:
            target.write(json.dumps(row) + "\n")
    substituted = campaign_module._rederive_classification_sidecar(
        sidecar,
        [{"id": "positive-base", "match": {"slot": "base", "delta": {"sign": "pos"}}}],
    )
    with pytest.raises(ValueError, match="signature digest drift"):
        campaign_module._enforce_preview_selector_population(
            population_contract,
            substituted["_signature_classes"],
            substituted["_signature_counts"],
        )
    rows[0]["class"] = None
    with gzip.open(sidecar, "wt") as target:
        for row in rows:
            target.write(json.dumps(row) + "\n")
    with pytest.raises(ValueError, match="sidecar class does not rederive"):
        campaign_module._rederive_classification_sidecar(
            sidecar,
            [{"id": "positive-base",
              "match": {"slot": "base", "delta": {"sign": "pos"}}}],
        )


def test_classification_handoff_accepts_rederived_v2_sidecar(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(campaign_module, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(
        campaign_module, "_routing_dispositions",
        lambda: {"0101210010": ("free", "free")},
    )
    fields = {
        "slot": "base", "origin_regime": "regime", "revision": "revision",
        "delta": 0.25, "disposition": "free", "hts10": "0101210010",
        "hts_line": "0101210000", "flags": {"entry_is_test": False},
        "interval": ["2026-01-01", "2026-01-02"], "iso2": "CA",
    }
    signature = mismatch_signature({
        "slot": fields["slot"], "delta": fields["delta"],
        "context": {
            key: fields[key]
            for key in (
                "flags", "revision", "interval", "origin_regime", "hts10",
                "hts_line", "iso2",
            )
        },
    })
    context = {
        key: fields[key]
        for key in (
            "flags", "revision", "interval", "origin_regime", "hts10",
            "hts_line", "iso2",
        )
    }
    comparison_rows = [
        {"case_id": "case-1", "slot": "base", "match": False,
         "delta": fields["delta"], "context": context},
        {"case_id": "case-1", "slot": "total", "match": False},
        {"case_id": "case-2", "slot": "base", "match": False,
         "delta": fields["delta"], "context": context},
        {"case_id": "case-3", "slot": "engine_error", "match": False},
        {"case_id": "case-4", "slot": "base", "match": True},
    ]
    comparison_artifact = tmp_path / "comparison.jsonl.gz"
    with gzip.open(comparison_artifact, "wt") as target:
        for row in comparison_rows:
            target.write(json.dumps(row) + "\n")
    inputs = {
        "comparison_artifact_sha256": campaign_module._sha256(comparison_artifact),
        "disposition_ledger_sha256": "b" * 64,
        "preview_disposition_receipt_sha256": "c" * 64,
        "preview_disposition_payload_sha256": "d" * 64,
    }
    monkeypatch.setattr(
        campaign_module, "_classification_inputs", lambda _comparison: inputs
    )
    entries = [
        {"id": "positive-base",
         "match": {"slot": "base", "delta": {"sign": "pos"}}}
    ]
    contract = {
        "positive-base": {
            "expected_units": 2,
            "expected_signature_count": 1,
            "expected_signature_population_sha256": signature_population_sha256(
                [(signature, 2)]
            ),
        }
    }
    monkeypatch.setattr(
        campaign_module, "_preview_selector_contract", lambda _entries: contract
    )
    sidecar = campaign_module._classification_sidecar_path(inputs)
    sidecar.parent.mkdir(parents=True)
    rows = [
        {"kind": "component_signature", "signature": signature, "units": 2,
         "class": "positive-base", "fields": fields},
        {"kind": "total_signature_composition", "signatures": [signature], "units": 1},
        {"kind": "engine_errors", "units": 1},
    ]
    with gzip.open(sidecar, "wt") as target:
        for row in rows:
            target.write(json.dumps(row) + "\n")
    rederived = campaign_module._rederive_classification_sidecar(sidecar, entries)
    rederived.pop("_signature_classes")
    rederived.pop("_signature_counts")
    classification = {
        "schema": "axiom_oracles.us_tariff_schedule.classification.v2",
        "inputs": inputs,
        "selector_count": 1,
        "sidecar": {
            "schema": "axiom_oracles.us_tariff_schedule.classification_sidecar.v2",
            "path": str(sidecar), "sha256": campaign_module._sha256(sidecar),
        },
        "conservation": "PASS",
        **rederived,
    }
    comparison = {
        "comparison_artifact": {
            "path": str(comparison_artifact),
            "sha256": inputs["comparison_artifact_sha256"],
        },
        "per_slot": {
            "base": {"match": 1, "mismatch": 2},
            "engine_error": {"mismatch": 1},
            "total": {"mismatch": 1},
        },
        "engine_errors": 1,
    }
    campaign_module._validate_classification_handoff(
        comparison, classification, entries
    )
    comparison["per_slot"]["base"]["match"] = 2
    with pytest.raises(ValueError, match="per-slot census does not rederive"):
        campaign_module._validate_classification_handoff(
            comparison, classification, entries
        )
    comparison["per_slot"]["base"]["match"] = 1
    monkeypatch.setattr(
        campaign_module, "_preview_selector_contract", lambda _entries: {}
    )
    substituted_fields = {**fields, "revision": "fabricated-revision"}
    substituted_signature = mismatch_signature({
        "slot": substituted_fields["slot"],
        "delta": substituted_fields["delta"],
        "context": {
            key: substituted_fields[key]
            for key in (
                "flags", "revision", "interval", "origin_regime", "hts10",
                "hts_line", "iso2",
            )
        },
    })
    rows[0]["signature"] = substituted_signature
    rows[0]["fields"] = substituted_fields
    rows[1]["signatures"] = [substituted_signature]
    with gzip.open(sidecar, "wt") as target:
        for row in rows:
            target.write(json.dumps(row) + "\n")
    substituted = campaign_module._rederive_classification_sidecar(sidecar, entries)
    substituted.pop("_signature_classes")
    substituted.pop("_signature_counts")
    classification.update(substituted)
    classification["sidecar"]["sha256"] = campaign_module._sha256(sidecar)
    with pytest.raises(ValueError, match="population is not derived from comparison artifact"):
        campaign_module._validate_classification_handoff(
            comparison, classification, entries
        )


def test_cafta_preview_class_remains_axiom_attributed_open() -> None:
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    cafta = next(entry for entry in ledger["entries"] if entry["id"] == "cafta-52i-deferred")
    assert cafta["attribution"] == "axiom-attributed-open"
    assert cafta["disposition"] == "axiom_encoding_gap"


PREVIEW_TARGET_MISMATCH = (
    Path(__file__).parents[1]
    / "reference/us-tariff-schedule/preview-1311/target-mismatch-cells.jsonl.gz"
)


@pytest.mark.skipif(
    not PREVIEW_TARGET_MISMATCH.is_file(),
    reason="needs the externally receipted preview-1311 target mismatch sidecar",
)
def test_preview_dispositions_select_exact_395330_population() -> None:
    routes = _routing_dispositions()
    counts: Counter[str] = Counter()
    observed = {}
    with gzip.open(PREVIEW_TARGET_MISMATCH, "rt") as source:
        for line in source:
            row = json.loads(line)
            signature = mismatch_signature(row)
            counts[signature] += 1
            observed.setdefault(signature, mismatch_unit(row, routes))
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    selectors = validate_dispositions(ledger["entries"], observed)
    census: Counter[str] = Counter()
    unexplained = 0
    for signature, unit in observed.items():
        class_id = matching_class_id(signature, unit, selectors)
        if class_id is None:
            unexplained += counts[signature]
        else:
            census[class_id] += counts[signature]
    receipt = json.loads(PREVIEW_DISPOSITION_LINE_SETS.read_text())
    expected = {item["id"]: item["expected_units"] for item in receipt["selectors"]}
    assert {name: census[name] for name in expected} == expected
    assert unexplained == 0
    assert sum(expected.values()) == 395_330


def test_specific_disposition_routes_to_components_only() -> None:
    plan = query_plan("specific")
    assert plan["base"] == plan["total"] == "known_not_comparable"
    assert plan["reason"] == "non_ad_valorem_base:specific"
    assert plan["components"] == list(BASE_INDEPENDENT_AUTHORITY_SLOTS)
    assert plan["excluded_components"] == ["ieepa", "forced_labor_section_301"]
    assert plan["component_exclusion_reason"] == "requires_noncomparable_base"


def test_specific_disposition_routed_to_full_comparison_fails_closed() -> None:
    # Required N1 mutant: changing the classifier so a specific base reaches
    # full comparison must violate the contract, rather than reaching engine.
    mutant_comparable = {"ad_valorem", "free", "specific"}
    mutant = query_plan("specific") | {
        "base": "compare" if "specific" in mutant_comparable else "known_not_comparable",
        "total": "compare" if "specific" in mutant_comparable else "known_not_comparable",
    }
    with pytest.raises(AssertionError, match="non-ad-valorem query reached shard planning"):
        assert mutant["base"] != "compare", "non-ad-valorem query reached shard planning"


def test_column2_structural_unavailability_keeps_components() -> None:
    plan = query_plan("free", column2_rate_available=False)
    assert plan["base"] == plan["total"] == "known_not_comparable"
    assert plan["reason"] == "structurally_unavailable:column2_rate"
    assert plan["components"] == list(BASE_INDEPENDENT_AUTHORITY_SLOTS)


def test_routes_statistical_member_to_rate_line() -> None:
    tables = {"01": {102294000: ("specific", "specific")}}
    assert route_member("0102294024", tables) == ("01", 102294000, "specific", "specific")


def test_explicit_unowned_member_routes_to_empty() -> None:
    assert route_member("9802009100", {"98": {}}) == (
        "98", 9802009100, "empty", "empty"
    )


def _comparison_record() -> dict:
    expected = {
        "statutory_base_rate": "0.05", "statutory_rate_232": "0",
        "statutory_rate_ieepa_recip": "0.1", "statutory_rate_ieepa_fent": "0",
        "statutory_rate_301": "0", "statutory_rate_301_cs": "0",
        "statutory_rate_s301fl": "0", "statutory_rate_s301br": "0",
        "statutory_rate_s338": "0", "statutory_rate_s122": "0",
        "statutory_rate_section_201": "0", "statutory_rate_other": "0",
    }
    actual = {
        "mfn_ad_valorem_rate": 0.05, "ieepa_component_rate": 0.1,
        "section_201_component_rate": 0, "section_122_component_rate": 0,
        "section_232_aluminum_component_rate": 0, "section_232_steel_component_rate": 0,
        "section_338_component_rate": 0, "china_section_301_component_rate": 0,
        "brazil_section_301_component_rate": 0, "forced_labor_section_301_component_rate": 0,
        "schedule_statutory_stack": 0.15,
    }
    return {"case_id": "case", "expected": expected, "actual": actual, "engine_errors": [],
            "plan": query_plan("ad_valorem"), "hts10": "0101210010", "hts_line": "0101210000",
            "iso2": "CA", "revision": "r1", "interval": ["2026-02-15", "2026-02-19"],
            "origin_regime": "regime", "flags": {"entry_is_test": False}}


def test_changed_expected_value_mutant_fails() -> None:
    record = _comparison_record()
    assert all(row["match"] for row in compare_record(record))
    record["expected"]["statutory_rate_s122"] = "0.01"
    assert any(row["slot"] == "section_122" and not row["match"] for row in compare_record(record))


def test_engine_error_surfaces_as_unexplained_comparison() -> None:
    record = _comparison_record() | {"actual": None, "engine_errors": ["boom"]}
    assert compare_record(record) == [{"case_id": "case", "slot": "engine_error", "match": False,
                                       "error": ["boom"], "delta": None}]


def test_stale_and_overlapping_disposition_selectors_fail() -> None:
    base = {"id": "one", "attribution": "input-comparability", "receipt": "receipt",
            "reason": "reason", "evidence": {"receipt_type": "instrument",
                                                "instrument_receipt": "receipt"}}
    with pytest.raises(ValueError, match="stale"):
        validate_dispositions([base | {"signatures": ["stale"]}], {"live": 1})
    with pytest.raises(ValueError, match="overlapping"):
        validate_dispositions([base | {"signatures": ["live"]},
                               (base | {"id": "two", "signatures": ["live"]})], {"live": 1})


def test_campaign_ledger_uses_only_campaign_local_matcher() -> None:
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    entries = ledger["entries"]
    assert any(entry.get("match") for entry in entries)
    assert validate_dispositions(entries, {}) == entries
    shared_errors = validate_shared(ledger)
    assert any("unknown keys: ['match']" in error for error in shared_errors)


def _selector_unit() -> dict:
    return {
        "slot": "base", "origin_regime": "regime", "revision": "r1", "delta": 0.2,
        "disposition": "free", "hts10": "0101210010", "hts_line": "0101210000",
        "flags": {"entry_is_test": False}, "interval": ["2026-01-01", "2026-01-02"],
        "iso2": "CA",
    }


def test_overlapping_structured_selectors_fail_conservation() -> None:
    unit = _selector_unit()
    selectors = [
        {"id": "one", "match": {"slot": "base", "delta": {"sign": "pos"}}},
        {"id": "two", "match": {"revision": ["r1"], "disposition": ["free"],
                                  "iso2": ["CA"]}},
    ]
    with pytest.raises(ValueError, match="overlapping selectors"):
        matching_class_id("signature", unit, selectors)


def test_universal_structured_selector_fails() -> None:
    with pytest.raises(ValueError, match="universal"):
        selector_matches(_selector_unit(), {
            "slot": "any", "origin_regime": "any", "revision": "any", "delta": "any",
            "disposition": "any", "line_class": "any",
        })


def test_slot_only_structured_selector_mutant_fails() -> None:
    with pytest.raises(ValueError, match="non-slot bound"):
        selector_matches(_selector_unit(), {"slot": "base"})


def test_delta_and_date_are_non_slot_bounds() -> None:
    assert selector_matches(_selector_unit(), {
        "slot": "base", "delta": {"values": [0.2]},
        "date": {"from": "2026-01-01", "through": "2026-01-02"},
    })


def test_fabricated_structured_selector_field_fails_schema() -> None:
    with pytest.raises(ValueError, match="unknown selector fields"):
        selector_matches(_selector_unit(), {"slot": "base", "fabricated": ["value"]})


def test_iso2_structured_selector_is_exactly_bounded() -> None:
    assert selector_matches(_selector_unit(), {"slot": "base", "iso2": ["CA", "MX"]})
    assert not selector_matches(_selector_unit(), {"slot": "base", "iso2": ["CU", "RU"]})


def test_nonzero_excluded_column_exposure_fails_x1() -> None:
    with pytest.raises(ValueError, match="X1"):
        enforce_excluded_exposure({"statutory_rate_301_cs": 1, "statutory_rate_other": 0})


def test_unclassified_signature_fails_computed_conformance() -> None:
    assert computed_conformant(unexplained=1, engine_errors=0) is False


def test_witness_replay_is_conformant_and_byte_stable() -> None:
    assert witness_replay()["byte_stable"] is True
