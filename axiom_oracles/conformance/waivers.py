"""Output-attestation waivers — the enumerated, shrink-only migration debt.

Execution attestation (:mod:`axiom_oracles.conformance.attestation`) is
unconditional: a report that cannot show a real run against the declared oracle
never covers anything. Its second layer — binding the run's comparisons to the
*registered outputs* of the policy the suite is named under — is enforced the
same way, with one deliberate escape: the reports committed before attestation
existed do not all record which oracle variable each compared concept was bound
to, and those bindings cannot be reconstructed without re-running suites that
need a UKMOD/EUROMOD runtime or a multi-million-comparison PolicyEngine pass.

Rather than fail those rows (which would retract badges backed by real
evidence) or fail open (which is the bug axiom-oracles#355 reports), each is
**named** in ``conformance/attestation_waivers.yaml`` with the suite it depends
on and why the binding cannot be shown. That file is hand-authored and
shrink-only:

* a covered row that needs a waiver and has none is NOT covered — so a new lane
  cannot green a suite whose comparisons are not tied to the policy;
* a waiver that is no longer needed is stale and fails the gate — so the list
  can only shrink as reports are regenerated with stamped attestations;
* a waiver is pinned to a ``suite``, so re-pointing a policy at a different
  suite drops the waiver rather than carrying it along.

``scripts/conformance_attestation.py`` reports, checks and prunes the file; the
scoreboard consumes it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

WAIVERS_SCHEMA = "axiom_oracles.attestation_waivers.v1"

#: Closed vocabulary — the two states a covered-but-unbound row can be in. Both
#: are produced by :meth:`ExecutionAttestation.binding_gap`, never hand-chosen.
WAIVER_REASONS: tuple[str, ...] = (
    #: The report records every surface it compared and none is a registered
    #: output — the suite ran against a different surface than the universe
    #: registers for this policy.
    "compared_surface_differs",
    #: The report does not record which oracle variable each compared concept
    #: was bound to, so the binding cannot be machine-verified either way.
    "oracle_variable_not_recorded",
)


@dataclass(frozen=True)
class AttestationWaiver:
    """One covered policy whose output binding cannot be attested yet."""

    jurisdiction: str
    policy_id: str
    #: The suite the waiver is pinned to — a policy re-pointed elsewhere is not
    #: waived, because the evidence question is about *that* report.
    suite: str
    reason: str
    note: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.jurisdiction, self.policy_id)

    def to_row(self) -> dict:
        row = {
            "jurisdiction": self.jurisdiction,
            "policy_id": self.policy_id,
            "suite": self.suite,
            "reason": self.reason,
        }
        if self.note:
            row["note"] = self.note
        return row

    @classmethod
    def from_row(cls, row: dict) -> "AttestationWaiver":
        return cls(
            jurisdiction=row["jurisdiction"],
            policy_id=row["policy_id"],
            suite=row["suite"],
            reason=row["reason"],
            note=row.get("note"),
        )

    def validate(self) -> list[str]:
        problems: list[str] = []
        if self.reason not in WAIVER_REASONS:
            problems.append(
                f"{self.policy_id}: reason {self.reason!r} is not one of "
                f"{', '.join(WAIVER_REASONS)}"
            )
        if not self.suite:
            problems.append(
                f"{self.policy_id}: a waiver must pin the `suite` whose report "
                "cannot show the binding"
            )
        return problems


class WaiverIndex:
    """Lookup of waivers by (jurisdiction, policy id), honouring the suite pin."""

    def __init__(self, waivers: list[AttestationWaiver] | None = None) -> None:
        self._by_key = {waiver.key: waiver for waiver in (waivers or [])}

    def __len__(self) -> int:
        return len(self._by_key)

    def __iter__(self):
        return iter(sorted(self._by_key.values(), key=lambda w: (w.jurisdiction, w.policy_id)))

    def waiver_for(
        self, jurisdiction: str, policy_id: str, suite: str | None
    ) -> AttestationWaiver | None:
        waiver = self._by_key.get((jurisdiction, policy_id))
        if waiver is None or waiver.suite != suite:
            return None
        return waiver

    def keys(self) -> set[tuple[str, str]]:
        return set(self._by_key)


def parse(path: str | Path) -> WaiverIndex:
    """Load the committed waiver file (an absent file means no waivers)."""
    path = Path(path)
    if not path.exists():
        return WaiverIndex([])
    document = yaml.safe_load(path.read_text()) or {}
    schema = document.get("schema")
    if schema != WAIVERS_SCHEMA:
        raise ValueError(f"{path}: expected schema {WAIVERS_SCHEMA!r}, got {schema!r}")
    waivers = [AttestationWaiver.from_row(row) for row in document.get("waivers") or []]
    problems = [problem for waiver in waivers for problem in waiver.validate()]
    if problems:
        raise ValueError(f"{path}: " + "; ".join(problems))
    return WaiverIndex(waivers)


def serialize(waivers: list[AttestationWaiver]) -> str:
    """Deterministic YAML (rows sorted) so the gate can diff it byte-for-byte."""
    rows = sorted(waivers, key=lambda w: (w.jurisdiction, w.policy_id))
    document = {
        "schema": WAIVERS_SCHEMA,
        "_comment": (
            "Output-attestation waivers — covered policies whose committed report "
            "cannot bind its comparisons to the universe's registered outputs. "
            "HAND-AUTHORED and SHRINK-ONLY: a new unbound row fails the gate "
            "(scripts/conformance_attestation.py --check) instead of landing here, "
            "and a waiver that is no longer needed must be pruned. Execution "
            "attestation itself is never waivable."
        ),
        "waivers": [waiver.to_row() for waiver in rows],
    }
    body = yaml.dump(
        document,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=100,
    )
    return (
        f"# {WAIVERS_SCHEMA} — hand-authored, shrink-only. See "
        "axiom_oracles/conformance/waivers.py.\n" + body
    )
