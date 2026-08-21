"""Focused guards for the NZ pinned-corpus gap ledger."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "closure" / "nz" / "corpus-gap-scan.json"


def _load_producer():
    scripts = REPO / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location(
        "nz_corpus_gap_scan_test", scripts / "nz_corpus_gap_scan.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _document() -> dict:
    return json.loads(LEDGER.read_text(encoding="utf-8"))


def test_committed_gap_scan_has_three_column_ledger_and_priority_receipts():
    document = _document()

    assert document["counts"] == {
        "bearing_instruments": 18,
        "in_release": 233,
        "instruments": 26,
        "instruments_with_missing": 13,
        "law_derived_rows": 229,
        "missing": 54,
        "provisions": 287,
        "unique_derivation_expressions": 77,
    }
    assert all(
        set(row) == {"provision", "in_release", "source_url"}
        for row in document["provisions"]
    )

    receipts = document["priority_receipts"]
    assert [row["priority"] for row in receipts] == [1, 2, 3, 4, 5]
    assert [row["cone"] for row in receipts] == [
        "acc_earnings_definition_instruments",
        "individual_income_tax",
        "independent_earner_tax_credit",
        "winter_energy_payment",
        "demographics",
    ]
    assert [(row["in_release"], row["missing"]) for row in receipts] == [
        (19, 0),
        (4, 0),
        (37, 10),
        (6, 41),
        (12, 0),
    ]

    worklist_order = [
        (row["priority"], row["instrument"]) for row in document["ingest_worklist"]
    ]
    assert worklist_order == sorted(worklist_order)
    assert all(row["priority_reason"] for row in document["ingest_worklist"])

    wep_74 = [
        row
        for row in document["provision_metadata"]
        if row["citation_path"] == "nz/statute/act/public/2018/0032/section/74"
    ]
    assert len(wep_74) == 1
    assert wep_74[0]["coverage_basis"] == "exact_nonempty_body"


def test_dropped_small_cone_root_reds_priority_receipt():
    """MUTANT: dropping the named WEP s 74 root must fail closed."""

    producer = _load_producer()
    document = _document()
    pairs = list(
        zip(document["provisions"], document["provision_metadata"], strict=True)
    )
    mutant = [
        pair
        for pair in pairs
        if pair[1]["citation_path"] != "nz/statute/act/public/2018/0032/section/74"
    ]

    with pytest.raises(
        producer.CorpusGapError,
        match="winter_energy_payment: priority path has 0 ledger rows",
    ):
        producer._priority_receipts(mutant)
