"""Conformance ratchets — monotonic invariants that may not regress.

The ratchet file (``conformance/ratchet.yaml``, schema
``axiom_oracles.conformance_ratchet.v1``) pins, per jurisdiction, the best
conformance numbers achieved so far. CI recomputes the live scoreboard and fails
if any invariant regressed:

* ``covered`` may only **rise** (never lose coverage of an in-scope policy),
* ``unexplained_total`` may only **fall** (never add an unexplained mismatch),
* ``axiom_attributed_open`` may only **fall** (never add an open Axiom gap),
* ``bridge_artifacts`` may only **fall**. This one gates nothing in the
  predicate — a bridge artifact is *explained* by definition ("the comparison
  harness fed the engines different inputs; not an engine or encoding defect",
  dispositions/README.md) — which is exactly why it needs a ceiling: an
  explanatory bucket that blocks nothing can absorb an unbounded new residual
  without any gate noticing. Today it absorbs 3,371 mismatches, 3,067 of them
  in one ssi-ecps entry whose own evidence cites a v1-slice scope omission
  alongside genuine bridge-input divergence. Growth is legitimate sometimes, so
  this is a ratchet rather than a block: raising it means re-pinning through
  ``scripts/conformance_ratchet.py``, which shows up in review.

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
    #: bridge artifacts may only fall → committed value is a CEILING. None means
    #: the row predates the ceiling; ``--check`` refuses that rather than
    #: silently skipping the invariant.
    bridge_artifacts_max: int | None = None

    def to_row(self) -> dict:
        return {
            "jurisdiction": self.jurisdiction,
            "covered_min": self.covered_min,
            "unexplained_max": self.unexplained_max,
            "axiom_attributed_open_max": self.axiom_attributed_open_max,
            "bridge_artifacts_max": self.bridge_artifacts_max,
            "policies_in_scope": self.policies_in_scope,
        }

    @classmethod
    def from_row(cls, row: dict) -> "RatchetInvariant":
        bridge = row.get("bridge_artifacts_max")
        return cls(
            jurisdiction=row["jurisdiction"],
            covered_min=int(row["covered_min"]),
            unexplained_max=int(row["unexplained_max"]),
            axiom_attributed_open_max=int(row["axiom_attributed_open_max"]),
            policies_in_scope=int(row.get("policies_in_scope", 0)),
            bridge_artifacts_max=None if bridge is None else int(bridge),
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
            bridge_artifacts_max=int(summary.get("bridge_artifacts", 0)),
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

    bridge = int(summary.get("bridge_artifacts", 0))
    if ratchet.bridge_artifacts_max is None:
        violations.append(
            f"[{ratchet.jurisdiction}] RATCHET incomplete: no "
            "`bridge_artifacts_max` ceiling is pinned. A bridge artifact is "
            "explained by definition and blocks nothing, so without a ceiling it "
            "can absorb an unbounded residual silently. Re-pin with "
            "`uv run scripts/conformance_ratchet.py`."
        )
    elif bridge > ratchet.bridge_artifacts_max:
        violations.append(
            f"[{ratchet.jurisdiction}] RATCHET regressed: `bridge_artifacts` rose "
            f"from {ratchet.bridge_artifacts_max} to {bridge}. Bridge artifacts "
            "may only fall — new mismatches are being classed as harness "
            "input-boundary differences. Confirm each new row really is a "
            "different-inputs artifact (dispositions/README.md) and not an "
            "encoding or scope gap wearing that label; if the growth is genuine, "
            "re-pin with `uv run scripts/conformance_ratchet.py` and say why in "
            "the PR."
        )
    return violations
