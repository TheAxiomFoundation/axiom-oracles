"""The generated ratchet is ASCII and retains every YAML payload value."""

from pathlib import Path

import yaml
from hypothesis import example, given, settings
from hypothesis import strategies as st

from axiom_oracles.comparison.pe_axiom_standard import (
    RATCHET_RELATIVE_PATH,
    Ratchet,
    Record,
    derive_ratchet,
    serialize_ratchet,
)


def test_committed_ratchet_is_ascii_and_round_trips() -> None:
    path = Path(__file__).resolve().parents[1] / RATCHET_RELATIVE_PATH
    text = path.read_text()
    assert text.isascii()
    document = yaml.safe_load(text)
    assert serialize_ratchet(document) == text
    assert Ratchet.from_document(yaml.safe_load(serialize_ratchet(document))) == (
        Ratchet.from_document(document)
    )


@settings(max_examples=300, deadline=None, derandomize=True)
@example(record_id="NEL\u0085id")
@given(record_id=st.text(min_size=1, max_size=40))
def test_ratchet_serialization_is_ascii_without_losing_text(record_id: str) -> None:
    record = Record(
        source="dispositions/example.yaml",
        id=record_id,
        suite="example",
        concept="us:policies/example#amount",
        basis="rows",
        pe_issue=None,
        entry={},
    )
    document = derive_ratchet([record], None)
    text = serialize_ratchet(document)
    assert text.isascii()
    assert yaml.safe_load(text) == document
    assert Ratchet.from_document(yaml.safe_load(text)) == Ratchet.from_document(document)
