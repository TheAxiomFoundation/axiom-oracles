"""Read and write ``conformance/<jurisdiction>.yaml`` universe files.

The universe file is human-reviewable YAML with a stable, deterministic
serialisation so the drift gate can compare a fresh regeneration against the
committed copy byte-for-byte (the ``affected_map --check`` pattern).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from axiom_oracles.conformance.schema import (
    CONFORMANCE_SCHEMA_VERSION,
    UniversePolicy,
)


@dataclass
class OracleIdentity:
    """The oracle a universe is defined against — stamped in the file header.

    ``model`` names the engine/model (``UKMOD_PUBLIC``); ``release`` the pinned
    release (``B2026.03``); ``system`` the policy system (``UK_2026``). Together
    they are the identity a conformance claim is scoped to — "Axiom conforms to
    *this* oracle at *this* release", never a floating latest.
    """

    model: str
    release: str
    system: str
    country: str
    backend: str

    @property
    def label(self) -> str:
        """Compact identity, e.g. ``UKMOD_PUBLIC_B2026.03/UK_2026``."""
        return f"{self.model}_{self.release}/{self.system}"

    def to_header(self) -> dict:
        return {
            "model": self.model,
            "release": self.release,
            "system": self.system,
            "country": self.country,
            "backend": self.backend,
            "label": self.label,
        }

    @classmethod
    def from_header(cls, header: dict) -> "OracleIdentity":
        return cls(
            model=header["model"],
            release=header["release"],
            system=header["system"],
            country=header["country"],
            backend=header.get("backend", "euromod"),
        )


@dataclass
class Universe:
    """A parsed universe file: header identity + ordered policy rows."""

    jurisdiction: str
    oracle: OracleIdentity
    policies: list[UniversePolicy]

    def in_scope(self) -> list[UniversePolicy]:
        return [p for p in self.policies if p.in_scope]

    def excluded(self) -> list[UniversePolicy]:
        return [p for p in self.policies if not p.in_scope]

    def by_name(self) -> dict[str, UniversePolicy]:
        return {p.oracle_policy_name: p for p in self.policies}

    def validate(self) -> list[str]:
        problems: list[str] = []
        seen_ids: set[str] = set()
        for policy in self.policies:
            problems.extend(policy.validate())
            if policy.id in seen_ids:
                problems.append(f"duplicate row id {policy.id!r}")
            seen_ids.add(policy.id)
        return problems


def _represent_ordered(dumper: yaml.Dumper, data: dict) -> yaml.nodes.MappingNode:
    return dumper.represent_mapping("tag:yaml.org,2002:map", data.items())


class _UniverseDumper(yaml.Dumper):
    """Dumper that preserves insertion order and indents block sequences."""

    def increase_indent(self, flow: bool = False, indentless: bool = False):
        return super().increase_indent(flow, False)


_UniverseDumper.add_representer(dict, _represent_ordered)


def serialize(universe: Universe) -> str:
    """Deterministic YAML serialisation of a universe (rows sorted by id).

    Sorting by id makes the file order independent of the model's internal
    policy ordering, so the drift check is stable even if a release reorders the
    spine. A leading provenance comment mirrors the other generated artifacts.
    """
    rows = sorted(universe.policies, key=lambda p: p.id)
    document = {
        "schema": CONFORMANCE_SCHEMA_VERSION,
        "jurisdiction": universe.jurisdiction,
        "oracle": universe.oracle.to_header(),
        "policies": [row.to_row() for row in rows],
    }
    body = yaml.dump(
        document,
        Dumper=_UniverseDumper,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=100,
    )
    header = (
        f"# {CONFORMANCE_SCHEMA_VERSION} — GENERATED universe facts + committed "
        "scope decisions.\n"
        "# Rows (policy id, oracle_policy_name, output_vars) are regenerated from "
        "the oracle\n"
        "# model spine by scripts/generate_conformance_universe.py — do NOT "
        "hand-edit those.\n"
        "# in_scope / exclusion_reason / suite / note ARE hand-authored "
        "decisions the generator\n"
        "# preserves; edit those here. CI fails if the generated facts drift "
        "from the model.\n"
    )
    return header + body


def parse(path: str | Path) -> Universe:
    """Load a committed universe file into a :class:`Universe`."""
    path = Path(path)
    document = yaml.safe_load(path.read_text()) or {}
    schema = document.get("schema")
    if schema != CONFORMANCE_SCHEMA_VERSION:
        raise ValueError(
            f"{path}: expected schema {CONFORMANCE_SCHEMA_VERSION!r}, got "
            f"{schema!r}"
        )
    oracle = OracleIdentity.from_header(document["oracle"])
    policies: list[UniversePolicy] = []
    for row in document.get("policies", []):
        policies.append(
            UniversePolicy(
                id=row["id"],
                oracle_policy_name=row["oracle_policy_name"],
                output_vars=tuple(row.get("output_vars") or ()),
                in_scope=bool(row["in_scope"]),
                exclusion_reason=row.get("exclusion_reason"),
                suite=row.get("suite"),
                note=row.get("note"),
                comparability=row.get("comparability", "full"),
                oracle_policy_type=row.get("oracle_policy_type"),
                oracle_switch=row.get("oracle_switch"),
                internal_only_vars=tuple(row.get("internal_only_vars") or ()),
            )
        )
    return Universe(
        jurisdiction=document["jurisdiction"],
        oracle=oracle,
        policies=policies,
    )


def parse_if_exists(path: str | Path) -> Universe | None:
    path = Path(path)
    return parse(path) if path.exists() else None
