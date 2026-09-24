"""Canonical US state jurisdiction registry.

``axiom_oracles/data/jurisdictions.v1.json`` is the one table of the 50 states
and DC: USPS code, Census FIPS code, NBER TAXSIM (SOI) state code, name,
rulespec-us slug, and personal income tax base, plus TAXSIM's special state
codes (0 = no state tax, -1 = every state). Each field is tested against the
source recorded for it in the file (``tests/test_jurisdictions.py``).

Read state codes from here instead of typing a table. Every lookup fails
closed: an unknown code raises :class:`UnknownJurisdictionError` rather than
falling back to a default. (A FIPS->TAXSIM table that omitted Alabama and
defaulted to 0 put every Alabama household in a comparison at "no state tax"
for 17 months; PolicyEngine/policyengine-taxsim#1204.)

Other repositories that cannot depend on this package vendor the JSON file and
pin it by sha256 (:func:`registry_sha256`).
"""

from __future__ import annotations

import hashlib
import json
import operator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

REGISTRY_PATH = Path(__file__).resolve().parent / "data" / "jurisdictions.v1.json"
SCHEMA = "axiom.jurisdictions.v1"

PERSONAL_INCOME_TAX_BASES = frozenset(
    {"wages_and_salaries", "capital_gains_only", "none"}
)


class UnknownJurisdictionError(ValueError):
    """A code that is not in the jurisdiction registry."""


@dataclass(frozen=True)
class UsState:
    """One of the 50 states or DC."""

    usps: str
    fips: str
    taxsim_soi: int
    name: str
    taxsim_name: str
    rulespec_slug: str
    has_broad_personal_income_tax: bool
    personal_income_tax_base: str

    @property
    def fips_code(self) -> int:
        """Census FIPS code as an integer (``"01"`` -> ``1``)."""
        return int(self.fips)


@dataclass(frozen=True)
class TaxsimSpecialCode:
    """A TAXSIM state code that does not name a state (0 or -1)."""

    code: int
    key: str
    idtl5_label: str
    meaning: str


@dataclass(frozen=True)
class JurisdictionRegistry:
    states: tuple[UsState, ...]
    taxsim_special_codes: tuple[TaxsimSpecialCode, ...]
    taxsim_missing_state_column_code: int
    sources: dict[str, Any]


@lru_cache(maxsize=1)
def load_registry() -> JurisdictionRegistry:
    """Parse and validate the registry file (cached)."""
    return _parse(json.loads(REGISTRY_PATH.read_text(encoding="utf-8")))


def registry_sha256() -> str:
    """SHA-256 of the registry file's bytes, for consumers that vendor it."""
    return hashlib.sha256(REGISTRY_PATH.read_bytes()).hexdigest()


def us_states() -> tuple[UsState, ...]:
    """The 50 states and DC, ordered by FIPS code."""
    return load_registry().states


def state_by_usps(code: Any) -> UsState:
    """State for a USPS code (case and surrounding space ignored)."""
    if not isinstance(code, str):
        raise UnknownJurisdictionError(
            f"USPS state code must be a string, got {code!r}"
        )
    state = _indexes()["usps"].get(code.strip().upper())
    if state is None:
        raise UnknownJurisdictionError(f"Unknown USPS state code {code!r}")
    return state


def state_by_fips(code: Any) -> UsState:
    """State for a Census FIPS code given as an int (``1``) or digits (``"01"``)."""
    state = _indexes()["fips"].get(_fips_int(code))
    if state is None:
        raise UnknownJurisdictionError(f"Unknown state FIPS code {code!r}")
    return state


def state_by_taxsim(code: Any) -> UsState:
    """State for a TAXSIM (SOI) state code 1-51.

    The special codes 0 (no state) and -1 (every state) name no state and
    raise; use :func:`taxsim_entry` to accept them.
    """
    number = _taxsim_int(code)
    state = _indexes()["taxsim"].get(number)
    if state is not None:
        return state
    special = _indexes()["taxsim_special"].get(number)
    if special is not None:
        raise UnknownJurisdictionError(
            f"TAXSIM state code {number} is the special code {special.key!r} "
            f"({special.idtl5_label}), not a state"
        )
    raise UnknownJurisdictionError(f"{code!r} is not a valid TAXSIM SOI state code")


def taxsim_special_code(code: Any) -> TaxsimSpecialCode:
    """The special TAXSIM state code 0 or -1."""
    special = _indexes()["taxsim_special"].get(_taxsim_int(code))
    if special is None:
        raise UnknownJurisdictionError(f"{code!r} is not a special TAXSIM state code")
    return special


def taxsim_special_code_by_key(key: str) -> TaxsimSpecialCode:
    """The special TAXSIM state code named ``key`` (``no_state``, ``all_states``)."""
    for special in load_registry().taxsim_special_codes:
        if special.key == key:
            return special
    raise UnknownJurisdictionError(f"Unknown special TAXSIM state code key {key!r}")


def taxsim_entry(code: Any) -> UsState | TaxsimSpecialCode:
    """Any valid TAXSIM state code: a state (1-51) or a special code (0, -1)."""
    number = _taxsim_int(code)
    entry = _indexes()["taxsim"].get(number) or _indexes()["taxsim_special"].get(number)
    if entry is None:
        raise UnknownJurisdictionError(f"{code!r} is not a valid TAXSIM SOI state code")
    return entry


def _fips_int(code: Any) -> int:
    if isinstance(code, str):
        text = code.strip()
        if not (text.isascii() and text.isdigit() and 1 <= len(text) <= 2):
            raise UnknownJurisdictionError(f"Unknown state FIPS code {code!r}")
        return int(text)
    return _strict_int(code, "state FIPS code")


def _taxsim_int(code: Any) -> int:
    if isinstance(code, str):
        text = code.strip()
        digits = text[1:] if text.startswith("-") else text
        if not (digits.isascii() and digits.isdigit()):
            raise UnknownJurisdictionError(
                f"{code!r} is not a valid TAXSIM SOI state code"
            )
        return int(text)
    return _strict_int(code, "TAXSIM SOI state code")


def _strict_int(code: Any, what: str) -> int:
    # bool is an int subclass; True must not read as FIPS 1 / Alabama.
    if isinstance(code, bool):
        raise UnknownJurisdictionError(f"{what} must be an integer, got {code!r}")
    try:
        return operator.index(code)
    except TypeError:
        raise UnknownJurisdictionError(
            f"{what} must be an integer, got {code!r}"
        ) from None


@lru_cache(maxsize=1)
def _indexes() -> dict[str, dict[Any, Any]]:
    registry = load_registry()
    return {
        "usps": {state.usps: state for state in registry.states},
        "fips": {state.fips_code: state for state in registry.states},
        "taxsim": {state.taxsim_soi: state for state in registry.states},
        "taxsim_special": {
            special.code: special for special in registry.taxsim_special_codes
        },
    }


def _parse(document: dict[str, Any]) -> JurisdictionRegistry:
    if document.get("schema") != SCHEMA:
        raise ValueError(
            f"{REGISTRY_PATH} schema is {document.get('schema')!r}, expected {SCHEMA!r}"
        )
    states = tuple(UsState(**entry) for entry in document["states"])
    taxsim = document["taxsim"]
    specials = tuple(
        TaxsimSpecialCode(**entry) for entry in taxsim["special_state_codes"]
    )
    registry = JurisdictionRegistry(
        states=states,
        taxsim_special_codes=specials,
        taxsim_missing_state_column_code=taxsim["missing_state_column_code"],
        sources=document["sources"],
    )
    _validate(registry)
    return registry


def _validate(registry: JurisdictionRegistry) -> None:
    states = registry.states
    for field in ("usps", "fips", "taxsim_soi", "name", "taxsim_name", "rulespec_slug"):
        values = [getattr(state, field) for state in states]
        if len(set(values)) != len(values):
            raise ValueError(f"Duplicate {field} in {REGISTRY_PATH}")
    if [state.fips for state in states] != sorted(state.fips for state in states):
        raise ValueError(f"{REGISTRY_PATH} states must be ordered by FIPS code")
    for state in states:
        if not (len(state.usps) == 2 and state.usps.isascii() and state.usps.isupper()):
            raise ValueError(f"Malformed USPS code {state.usps!r}")
        if not (len(state.fips) == 2 and state.fips.isascii() and state.fips.isdigit()):
            raise ValueError(f"Malformed FIPS code {state.fips!r} for {state.usps}")
        if isinstance(state.taxsim_soi, bool) or not isinstance(state.taxsim_soi, int):
            raise ValueError(
                f"Malformed TAXSIM code {state.taxsim_soi!r} for {state.usps}"
            )
        if state.personal_income_tax_base not in PERSONAL_INCOME_TAX_BASES:
            raise ValueError(f"Unknown personal_income_tax_base for {state.usps}")
        if state.has_broad_personal_income_tax != (
            state.personal_income_tax_base == "wages_and_salaries"
        ):
            raise ValueError(
                f"has_broad_personal_income_tax disagrees with base for {state.usps}"
            )
    special_codes = {special.code for special in registry.taxsim_special_codes}
    if special_codes & {state.taxsim_soi for state in states}:
        raise ValueError("A special TAXSIM state code collides with a state's code")
    if registry.taxsim_missing_state_column_code not in special_codes:
        raise ValueError(
            "missing_state_column_code must be a special TAXSIM state code"
        )
