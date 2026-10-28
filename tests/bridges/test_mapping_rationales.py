"""Mapping rationales parse to their full text.

In a plain YAML scalar, " #" starts a comment, so a rationale written as
"(PolicyEngine-UK #1795)" is silently cut at "PolicyEngine-UK" by
yaml.safe_load. These tests fail on any plain-scalar rationale that YAML
truncates this way.
"""

from pathlib import Path

import pytest
import yaml

MAPPINGS = Path(__file__).resolve().parents[2] / "axiom_oracles/bridges/mappings"


def truncated_rationales(text: str) -> list[tuple[int, str]]:
    """(line, text YAML dropped) for each plain-scalar rationale followed by
    more text on its line."""
    lines = text.splitlines()
    found: list[tuple[int, str]] = []

    def walk(node: yaml.Node) -> None:
        if isinstance(node, yaml.MappingNode):
            for key, value in node.value:
                if (
                    isinstance(key, yaml.ScalarNode)
                    and key.value == "rationale"
                    and isinstance(value, yaml.ScalarNode)
                    and value.style is None
                ):
                    rest = lines[value.end_mark.line][value.end_mark.column :]
                    if rest.strip():
                        found.append((value.start_mark.line + 1, rest.strip()))
                else:
                    walk(value)
        elif isinstance(node, yaml.SequenceNode):
            for item in node.value:
                walk(item)

    walk(yaml.compose(text))
    return found


def test_detects_a_comment_cut_rationale():
    text = "mappings:\n  - legal_id: x\n    rationale: Filed upstream (PolicyEngine-UK #1795).\n"

    assert yaml.safe_load(text)["mappings"][0]["rationale"] == (
        "Filed upstream (PolicyEngine-UK"
    )
    assert truncated_rationales(text) == [(3, "#1795).")]


@pytest.mark.parametrize(
    "path", sorted(MAPPINGS.glob("*.yaml")), ids=lambda path: path.name
)
def test_no_mapping_rationale_is_cut_by_a_yaml_comment(path):
    assert truncated_rationales(path.read_text()) == []


@pytest.mark.parametrize(
    ("legal_id", "ending"),
    [
        (
            "uk:statutes/ukpga/2002/16/1#qualifying_age",
            "and they are over both from 2019-20.",
        ),
        (
            "uk:statutes/ukpga/2002/16/1#claimant_has_attained_qualifying_age",
            "and claimant_age is then the age.",
        ),
    ],
)
def test_state_pension_credit_rationales_parse_in_full(legal_id, ending):
    mappings = yaml.safe_load((MAPPINGS / "uk.yaml").read_text())["mappings"]
    rationale = next(m for m in mappings if m["legal_id"] == legal_id)["rationale"]

    assert rationale.endswith(ending)
