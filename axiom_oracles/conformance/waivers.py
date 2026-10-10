"""Retired output-attestation migration metadata.

The bootstrap rows record historical reports whose comparisons could not be
bound to registered outputs. Their suite, reason and complete artifact hashes
remain available for historical lookup, but this metadata never supplies a
missing same-case output pair or authorizes scoreboard coverage.

Every bootstrap row has been retired from
``conformance/attestation_waivers.yaml``. Its immutable remaining approval floor
is empty: the parser accepts an absent or schema-valid empty file and refuses
every retired row, even when its original suite and reason still match. Deleted
bootstrap entries cannot return by rewriting the editable current file.

``scripts/conformance_attestation.py`` audits and serializes the file;
``--prune`` only removes rows.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import yaml

WAIVERS_SCHEMA = "axiom_oracles.attestation_waivers.v1"

# Approved migration debt at reviewed PR head
# e83d47f31be70e4028278507a17ee95e0f4ecfab. This baseline is independent of the
# editable current waiver file. Retired rows cannot regain approval from it.
# Values are (suite, reason, SHA-256 of the complete canonical parsed report).
# All approved artifacts predate runner stamps. Keep their hashes fixed when a
# report is regenerated; the replacement must attest its own registered output.
BOOTSTRAP_WAIVERS: dict[tuple[str, str], tuple[str, str, str]] = {
    ("be", "be:tintb_be"): (
        "be-marital-quotient", "compared_surface_differs",
        "48ce04e4f5c0bb5fd5809357008890e1c8ca82f04fbfe0e4bb60e72c9439b079",
    ),
    ("uk-pe", "uk-pe:dla"): (
        "uk-tax-benefits-efrs", "oracle_variable_not_recorded",
        "bb08796ec556d585bfa8e1fde4c7bf33effecfb138bcf2d54d699db115879345",
    ),
    ("uk-pe", "uk-pe:housing_benefit"): (
        "uk-tax-benefits-efrs", "oracle_variable_not_recorded",
        "bb08796ec556d585bfa8e1fde4c7bf33effecfb138bcf2d54d699db115879345",
    ),
    ("uk-pe", "uk-pe:marriage_allowance"): (
        "uk-tax-benefits-efrs", "oracle_variable_not_recorded",
        "bb08796ec556d585bfa8e1fde4c7bf33effecfb138bcf2d54d699db115879345",
    ),
    ("uk-pe", "uk-pe:pip"): (
        "uk-tax-benefits-efrs", "oracle_variable_not_recorded",
        "bb08796ec556d585bfa8e1fde4c7bf33effecfb138bcf2d54d699db115879345",
    ),
    ("uk-pe", "uk-pe:universal_credit"): (
        "uk-universal-credit-efrs", "oracle_variable_not_recorded",
        "aa55a6e2451baa1f41cc17d15beabab2669aa523b387ba1c9dc2c523fb67e890",
    ),
    ("us-pe", "us-pe:aca_ptc"): (
        "us-aca-ptc-grid", "oracle_variable_not_recorded",
        "91a0635b9ff859904ea952b5f06794329181c220cc472835ab635a121b08a14e",
    ),
    ("us-pe", "us-pe:additional_medicare_tax"): (
        "us-additional-medicare-grid", "oracle_variable_not_recorded",
        "123cf4c874cdc5f02dc305322022e2ae2ec0042a4e129b39618a6b167e88fd69",
    ),
    ("us-pe", "us-pe:al_income_tax"): (
        "al-income-tax-liability", "compared_surface_differs",
        "3b44ae60538daf57359c734c8b09af9e6b945fb53d11f7d7fba8cb3d93178cc5",
    ),
    ("us-pe", "us-pe:ctc"): (
        "fiit-ecps", "compared_surface_differs",
        "8e6118426473c4e18b45469e1b50eb3c606d9f97d13709090d8f018c40443bf1",
    ),
    ("us-pe", "us-pe:elderly_disabled_credit"): (
        "us-elderly-disabled-grid", "oracle_variable_not_recorded",
        "b4f3d0400ce6e04bb4c3c824df8d8f11c01162d2fc0ec8ffbf4d35ce9af58200",
    ),
    ("us-pe", "us-pe:income_tax_before_refundable_credits"): (
        "fiit-ecps", "compared_surface_differs",
        "8e6118426473c4e18b45469e1b50eb3c606d9f97d13709090d8f018c40443bf1",
    ),
    ("us-pe", "us-pe:ks_tanf"): (
        "ks-tanf-ecps", "compared_surface_differs",
        "aca3d732e733098a37eeb5861638871e37e6e8ddf294f71e65cab336995cff2e",
    ),
    ("us-pe", "us-pe:lifetime_learning_credit"): (
        "us-llc-grid", "oracle_variable_not_recorded",
        "ee33ed7d57484dbf0b4be7db2c2aff4e5fa71de97ebc98fd8307d6ed4acba6df",
    ),
    ("us-pe", "us-pe:medicaid"): (
        "medicaid-magi-co-ecps", "compared_surface_differs",
        "f9c3627fd873155361c0282e450039a426530a49b94c1b10a0e2a098454696dd",
    ),
    ("us-pe", "us-pe:nc_income_tax"): (
        "nc-income-tax-liability", "compared_surface_differs",
        "1daf17177f589ba521f2cb746c1d6c0e04b14f6e9fde3a009272258b0afcb7e8",
    ),
    ("us-pe", "us-pe:net_investment_income_tax"): (
        "us-niit-grid", "oracle_variable_not_recorded",
        "3e37695f6bd611a2f7eb546cb457a791f5fd0d09bbc27a4988dd99b53a625cde",
    ),
    ("us-pe", "us-pe:qualified_business_income_deduction"): (
        "us-qbid-grid", "oracle_variable_not_recorded",
        "813161bad04047ec05a173126aea94306b7e3bae3f60aa96467ff777b8f8dbf5",
    ),
    ("us-pe", "us-pe:self_employment_tax"): (
        "us-seca-grid", "oracle_variable_not_recorded",
        "a2767a6cb8a3d1b96fa02849f6f2517e750592c121fe3fa058ea5ef1bb608e3b",
    ),
    ("us-pe", "us-pe:snap"): (
        "ca-snap-ecps", "compared_surface_differs",
        "e33b0065d7b9e408505af10627417c12ba795b6eceae7d50310192d732b7391c",
    ),
}

# All bootstrap rows were retired by reviewed head 45ae02123. This fixed floor
# cannot be expanded by editing the current YAML or restoring a bootstrap row.
REMAINING_BOOTSTRAP_WAIVERS: frozenset[tuple[str, str]] = frozenset()


def artifact_sha256(report: dict) -> str:
    """Hash all artifact content, independent of JSON whitespace or key order."""
    body = json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(body.encode()).hexdigest()

#: Closed vocabulary — the two historical output-binding gaps. Both
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
    """Historical metadata for a policy whose output binding was unattested."""

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
    """Lookup of approved migration waivers, pinned to the legacy artifact."""

    def __init__(self, waivers: list[AttestationWaiver] | None = None) -> None:
        self._by_key = {waiver.key: waiver for waiver in (waivers or [])}

    def __len__(self) -> int:
        return len(self._by_key)

    def __iter__(self):
        return iter(sorted(self._by_key.values(), key=lambda w: (w.jurisdiction, w.policy_id)))

    def waiver_for(
        self, jurisdiction: str, policy_id: str, suite: str | None,
        *, report: dict, reason: str,
    ) -> AttestationWaiver | None:
        waiver = self._by_key.get((jurisdiction, policy_id))
        if waiver is None or waiver.suite != suite:
            return None
        approved = BOOTSTRAP_WAIVERS.get(waiver.key)
        if approved is None or (waiver.suite, waiver.reason) != approved[:2]:
            return None
        if reason != waiver.reason or "attestation" in report:
            return None
        if artifact_sha256(report) != approved[2]:
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
    seen: set[tuple[str, str]] = set()
    for waiver in waivers:
        if waiver.key in seen:
            problems.append(f"{waiver.policy_id}: duplicate waiver")
        seen.add(waiver.key)
        approved = BOOTSTRAP_WAIVERS.get(waiver.key)
        if approved is None:
            problems.append(f"{waiver.policy_id}: not in the approved bootstrap waiver set")
        elif (waiver.suite, waiver.reason) != approved[:2]:
            problems.append(
                f"{waiver.policy_id}: suite and reason must match the approved "
                "bootstrap waiver"
            )
        elif waiver.key not in REMAINING_BOOTSTRAP_WAIVERS:
            problems.append(
                f"{waiver.policy_id}: retired bootstrap waiver cannot return"
            )
    if problems:
        raise ValueError(f"{path}: " + "; ".join(problems))
    return WaiverIndex(waivers)


def serialize(waivers: list[AttestationWaiver]) -> str:
    """Deterministic YAML (rows sorted) so the gate can diff it byte-for-byte."""
    rows = sorted(waivers, key=lambda w: (w.jurisdiction, w.policy_id))
    document = {
        "schema": WAIVERS_SCHEMA,
        "_comment": (
            "Historical output-attestation migration metadata. HAND-AUTHORED "
            "and SHRINK-ONLY: all approved bootstrap entries have been retired "
            "and cannot return. The remaining approval floor is empty. This "
            "metadata never authorizes coverage; every covered policy requires "
            "a valid same-case registered-output pair."
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
