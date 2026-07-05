"""Conformance ratchets — monotonic invariants that may not regress.

The ratchet file (``conformance/ratchet.yaml``, schema
``axiom_oracles.conformance_ratchet.v1``) pins, per jurisdiction, the best
conformance numbers achieved so far. CI recomputes the live scoreboard and fails
if any invariant regressed:

* ``covered`` may only **rise** (never lose coverage of an in-scope policy),
* ``unexplained_total`` may only **fall** (never add an unexplained mismatch),
* ``axiom_attributed_open`` may only **fall** (never add an open Axiom gap).

``policies_in_scope`` is recorded too: when the oracle model adds an in-scope
policy, the denominator legitimately grows — that is not a regression, but the
ratchet records it so ``covered`` is read against the right base.

Advancing a ratchet is deliberate: run ``scripts/conformance_ratchet.py`` to
re-pin to the current (better) scoreboard, which is the only way the committed
floor moves.
"""

from __future__ import annotations

from dataclasses import dataclass

RATCHET_SCHEMA = "axiom_oracles.conformance_ratchet.v1"


@dataclass
class RatchetInvariant:
    """The pinned floor/ceiling for one jurisdiction."""

    jurisdiction: str
    #: covered may only rise → committed value is a FLOOR.
    covered_min: int
    #: unexplained may only fall → committed value is a CEILING.
    unexplained_max: int
    #: axiom-attributed-open may only fall → committed value is a CEILING.
    axiom_attributed_open_max: int
    #: recorded for context (denominator can grow when the model does).
    policies_in_scope: int

    def to_row(self) -> dict:
        return {
            "jurisdiction": self.jurisdiction,
            "covered_min": self.covered_min,
            "unexplained_max": self.unexplained_max,
            "axiom_attributed_open_max": self.axiom_attributed_open_max,
            "policies_in_scope": self.policies_in_scope,
        }

    @classmethod
    def from_row(cls, row: dict) -> "RatchetInvariant":
        return cls(
            jurisdiction=row["jurisdiction"],
            covered_min=int(row["covered_min"]),
            unexplained_max=int(row["unexplained_max"]),
            axiom_attributed_open_max=int(row["axiom_attributed_open_max"]),
            policies_in_scope=int(row.get("policies_in_scope", 0)),
        )

    @classmethod
    def from_summary(cls, summary: dict) -> "RatchetInvariant":
        """Pin a ratchet at a scoreboard jurisdiction's current numbers."""
        return cls(
            jurisdiction=summary["jurisdiction"],
            covered_min=int(summary["covered"]),
            unexplained_max=int(summary["unexplained_total"]),
            axiom_attributed_open_max=int(summary["axiom_attributed_open"]),
            policies_in_scope=int(summary["policies_in_scope"]),
        )


def check_regressions(
    ratchet: RatchetInvariant, summary: dict
) -> list[str]:
    """Return violation messages naming the exact invariant that regressed.

    Each message tells the agent which monotonic invariant they broke and how,
    following the repo's gate convention of actionable failure text.
    """
    violations: list[str] = []
    covered = int(summary["covered"])
    unexplained = int(summary["unexplained_total"])
    axiom_open = int(summary["axiom_attributed_open"])

    if covered < ratchet.covered_min:
        violations.append(
            f"[{ratchet.jurisdiction}] RATCHET regressed: `covered` fell from "
            f"{ratchet.covered_min} to {covered}. Coverage may only rise — a "
            "previously-covered in-scope policy lost its live suite. Restore the "
            "suite/report, or if a policy was intentionally reclassified, re-pin "
            "with `scripts/conformance_ratchet.py` and explain in the PR."
        )
    if unexplained > ratchet.unexplained_max:
        violations.append(
            f"[{ratchet.jurisdiction}] RATCHET regressed: `unexplained_total` "
            f"rose from {ratchet.unexplained_max} to {unexplained}. Unexplained "
            "mismatches may only fall — a new mismatch has no disposition. Either "
            "fix the encoding, or add a schema-validated disposition classifying "
            "the residual (dispositions/<suite>.yaml)."
        )
    if axiom_open > ratchet.axiom_attributed_open_max:
        violations.append(
            f"[{ratchet.jurisdiction}] RATCHET regressed: `axiom_attributed_open` "
            f"rose from {ratchet.axiom_attributed_open_max} to {axiom_open}. Open "
            "Axiom-attributed gaps may only fall — a mismatch is now classed as "
            "an Axiom encoding gap (or links an open rulespec issue). Fix the "
            "rulespec encoding to close it."
        )
    return violations
