"""Enumerate the policy universe an oracle simulates, from its model spine.

Universe facts are never hand-invented: they come from parsing the oracle's own
model definition. Two backends live here.

* :class:`EuromodUniverseBackend` parses a EUROMOD-platform country XML
  (UKMOD or the JRC EUROMOD release) — the same ``XMLParam/Countries/<CC>/<CC>.xml``
  spine the ``EuromodPlatformRunner`` executes. It reads the policy list for one
  system and, per policy, the output variables its functions write, then splits
  those into *queryable* outputs (present in ``VARCONFIG``, the model's variable
  registry) and *internal-only* locals (absent from ``VARCONFIG``). A pure XML
  parse — no engine, no .NET, no licensed data — so it is CI-friendly.

* :class:`PolicyEngineUniverseBackend` is a documented stub that enumerates
  variables-with-formulas from a pinned ``policyengine-uk`` checkout. It exists
  so a ``pe-uk`` universe becomes reproducible the moment the scoper wiring
  lands; it is intentionally not exercised by the committed UK universe (which
  is UKMOD).

The classification *heuristic* below only proposes a default scope; the
authoritative ``in_scope``/``exclusion_reason`` decision lives in the committed
universe YAML and is preserved across regenerations. The generator overwrites
the *facts* (policy list, outputs) and keeps the *decisions*.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from axiom_oracles.conformance.schema import UniversePolicy

_CC_NS = "{http://euromod.com/CountryConfig.xsd}"
_VAR_NS = "{http://euromod.com/VarConfig.xsd}"

#: Function ``Parameter`` names that declare where a function writes its result.
#: EUROMOD is case-insensitive on parameter names, so we lower-case before test.
_OUTPUT_PARAM_NAMES = {"output_var", "output_add_var"}

#: EUROMOD elements that are large and irrelevant to universe enumeration; we
#: ``clear()`` them during iterparse so a 68 MB country XML streams cheaply.
_SKIP_ELEMENTS = {
    "Extension_Function",
    "Extension_Policy",
    "Extension_Parameter",
    "ConditionalFormat",
    "UpratingIndex",
    "LookGroup",
}


def _text(element: ET.Element, tag: str, ns: str = _CC_NS) -> str | None:
    child = element.find(ns + tag)
    return child.text if child is not None else None


def _is_queryable_output(name: str) -> bool:
    """A per-case *queryable* output is a bare ``_s`` result variable.

    ``i_``-prefixed names are function-local intermediates; ``tot_`` names are
    model-internal totals/counts. Neither is a variable a comparison can request
    from the engine — only bare ``*_s`` simulated outputs are. Membership in
    ``VARCONFIG`` is confirmed separately by the backend; this is the shape test.
    """
    lowered = name.lower()
    if lowered.startswith("i_"):
        return False
    if lowered.startswith("tot_"):
        return False
    return lowered.endswith("_s")


@dataclass
class RawPolicy:
    """The unclassified facts for one oracle policy, straight from the model."""

    name: str
    policy_type: str | None
    switch: str | None
    #: All output variables the policy's functions write, in first-seen order.
    all_outputs: tuple[str, ...]
    #: Outputs that are queryable (bare ``_s``) AND present in the variable
    #: registry — the surfaces a comparison could bind to.
    queryable_outputs: tuple[str, ...]
    #: Outputs the policy writes that are shaped like intermediates or are
    #: absent from the variable registry — evidence for exclusion classifying.
    internal_outputs: tuple[str, ...]


class EuromodUniverseBackend:
    """Enumerate a EUROMOD-platform country's policy universe for one system.

    Parameters
    ----------
    model_root:
        Path to the model checkout (``UKMOD_PUBLIC_B2026.03`` or a EUROMOD
        release root) — the directory containing ``XMLParam``.
    country:
        Two-letter country code (``UK``, ``BE``, …); selects
        ``XMLParam/Countries/<CC>/<CC>.xml``.
    system:
        System name whose policy list to read (e.g. ``UK_2026``). Each system
        carries its own copy of the policy spine; conformance is defined against
        one system, matching the oracle identity in the header.
    """

    backend = "euromod"

    def __init__(self, model_root: str | Path, country: str, system: str) -> None:
        self.model_root = Path(model_root).expanduser()
        self.country = country.upper()
        self.system = system
        self._country_xml = (
            self.model_root
            / "XMLParam"
            / "Countries"
            / self.country
            / f"{self.country}.xml"
        )
        self._varconfig_xml = (
            self.model_root / "XMLParam" / "Config" / "VARCONFIG.xml"
        )

    # -- registry (VARCONFIG) ------------------------------------------------

    def _registry_variables(self) -> set[str]:
        """Lower-cased set of every variable name declared in ``VARCONFIG``.

        This is the model's *queryable* surface: a variable a run can request.
        Membership decides whether a policy's ``_s`` output is comparable or an
        unobservable internal (the ``unobservable_boundary`` evidence).
        """
        if not self._varconfig_xml.exists():
            raise FileNotFoundError(
                f"VARCONFIG not found at {self._varconfig_xml}; cannot confirm "
                "which outputs are queryable"
            )
        names: set[str] = set()
        for _event, element in ET.iterparse(str(self._varconfig_xml), events=("end",)):
            if element.tag == _VAR_NS + "Variable":
                name = _text(element, "Name", _VAR_NS)
                if name and name.strip():
                    names.add(name.strip().lower())
                element.clear()
        return names

    # -- system resolution ---------------------------------------------------

    def _system_id(self) -> str:
        """Resolve the system name to its model ``System`` id (GUID)."""
        for _event, element in ET.iterparse(str(self._country_xml), events=("end",)):
            tag = element.tag.replace(_CC_NS, "")
            if tag == "System":
                if _text(element, "Name") == self.system:
                    sid = _text(element, "ID")
                    element.clear()
                    if sid:
                        return sid
                element.clear()
            elif tag in _SKIP_ELEMENTS or tag == "Policy":
                element.clear()
        raise ValueError(
            f"System {self.system!r} not found in {self._country_xml}. Available "
            "systems can be listed with the euromod connector or by inspecting "
            "the XML <System><Name> elements."
        )

    def available_systems(self) -> list[str]:
        """List system names in the country XML (for error messages / probing)."""
        systems: list[str] = []
        for _event, element in ET.iterparse(str(self._country_xml), events=("end",)):
            tag = element.tag.replace(_CC_NS, "")
            if tag == "System":
                name = _text(element, "Name")
                if name:
                    systems.append(name)
                element.clear()
            elif tag in _SKIP_ELEMENTS or tag == "Policy":
                element.clear()
        return systems

    # -- policy enumeration --------------------------------------------------

    def raw_policies(self) -> list[RawPolicy]:
        """Enumerate every policy in the target system with its output facts."""
        if not self._country_xml.exists():
            raise FileNotFoundError(
                f"Country XML not found at {self._country_xml}"
            )
        registry = self._registry_variables()
        system_id = self._system_id()
        policies: list[RawPolicy] = []
        for _event, element in ET.iterparse(str(self._country_xml), events=("end",)):
            tag = element.tag.replace(_CC_NS, "")
            if tag == "Policy":
                if _text(element, "SystemID") == system_id:
                    policies.append(self._parse_policy(element, registry))
                element.clear()
            elif tag in _SKIP_ELEMENTS or tag == "System":
                element.clear()
        return policies

    def _parse_policy(
        self, element: ET.Element, registry: set[str]
    ) -> RawPolicy:
        name = _text(element, "Name") or ""
        policy_type = _text(element, "Type")
        switch = _text(element, "Switch")
        seen: set[str] = set()
        all_outputs: list[str] = []
        for function in element.findall(_CC_NS + "Function"):
            for param in function.findall(_CC_NS + "Parameter"):
                pname = (_text(param, "Name") or "").strip().lower()
                if pname in _OUTPUT_PARAM_NAMES:
                    value = (_text(param, "Value") or "").strip()
                    if value and value not in seen:
                        seen.add(value)
                        all_outputs.append(value)
        queryable: list[str] = []
        internal: list[str] = []
        for out in all_outputs:
            if _is_queryable_output(out) and out.lower() in registry:
                queryable.append(out)
            else:
                internal.append(out)
        return RawPolicy(
            name=name,
            policy_type=policy_type,
            switch=switch,
            all_outputs=tuple(all_outputs),
            queryable_outputs=tuple(queryable),
            internal_outputs=tuple(internal),
        )


# ---------------------------------------------------------------------------
# Default scope proposal (advisory only)
# ---------------------------------------------------------------------------

#: EUROMOD policy types that are pure scaffolding, never a scored instrument.
_DEF_LIKE_TYPES = {"def"}


def propose_scope(policy: RawPolicy) -> tuple[bool, str | None]:
    """Propose a *default* (in_scope, exclusion_reason) for a fresh policy.

    This runs only when a policy appears in the model that the committed
    universe has no decision for. It never overrides a committed decision — it
    seeds a reviewable default so a newly-added oracle policy shows up with a
    sane starting classification (and, critically, is *not* silently counted as
    covered). The reviewer confirms or corrects it.

    The rules are deliberately conservative:

    * A policy with no queryable outputs cannot be compared per-case. If it is a
      ``def`` block it is ``technical``; otherwise it is proposed
      ``unobservable_boundary`` (it simulates something, but not at a queryable
      surface) so a human looks at it rather than it defaulting to covered.
    * A policy with queryable outputs is proposed in-scope with no suite yet —
      which is intentionally *invalid* until a reviewer names the covering
      suite, so it surfaces loudly in ``--check`` instead of passing vacuously.
    """
    if not policy.queryable_outputs:
        if (policy.policy_type or "").lower() in _DEF_LIKE_TYPES:
            return False, "technical"
        return False, "unobservable_boundary"
    return True, None


def raw_to_universe_policy(
    policy: RawPolicy,
    *,
    committed: UniversePolicy | None,
    jurisdiction: str,
) -> UniversePolicy:
    """Merge freshly-parsed facts with a committed scope decision.

    Facts (``output_vars``, ``oracle_policy_type``, ``internal_only_vars``) are
    always taken from ``policy``. Decisions (``in_scope``, ``exclusion_reason``,
    ``suite``, ``note``) come from ``committed`` when present, else from
    :func:`propose_scope`.
    """
    row_id = f"{jurisdiction}:{policy.name}"
    if committed is not None:
        in_scope = committed.in_scope
        exclusion_reason = committed.exclusion_reason
        suite = committed.suite
        note = committed.note
        comparability = committed.comparability
    else:
        in_scope, exclusion_reason = propose_scope(policy)
        suite = None
        note = None
        comparability = "full"
    return UniversePolicy(
        id=row_id,
        oracle_policy_name=policy.name,
        output_vars=policy.queryable_outputs,
        in_scope=in_scope,
        exclusion_reason=exclusion_reason if not in_scope else None,
        suite=suite if in_scope else None,
        note=note,
        comparability=comparability if in_scope else "full",
        oracle_policy_type=policy.policy_type,
        internal_only_vars=policy.internal_outputs,
    )


class PolicyEngineUniverseBackend:
    """Enumerate variables-with-formulas from a pinned ``policyengine-uk`` checkout.

    Documented TODO hook. A ``pe-uk`` universe is being scoped concurrently; this
    backend makes that matrix reproducible without duplicating the scoper's row
    decisions. It enumerates the *facts* (which variables have formulas, i.e.
    which the model computes rather than takes as input) from a pinned checkout,
    the PolicyEngine analogue of the EUROMOD policy list.

    Not wired into the committed UK universe (which is UKMOD-backed). Raising
    here keeps the stub honest: it advertises the exact contract a caller must
    satisfy rather than silently returning an empty universe that would look
    like "0 policies, all covered".
    """

    backend = "policyengine"

    def __init__(self, checkout: str | Path, package: str = "policyengine_uk") -> None:
        self.checkout = Path(checkout).expanduser()
        self.package = package

    def raw_policies(self) -> list[RawPolicy]:  # pragma: no cover - documented stub
        raise NotImplementedError(
            "PolicyEngineUniverseBackend is a documented TODO hook. To enumerate "
            "the pe-uk universe, walk the pinned policyengine-uk checkout at "
            f"{self.checkout} for Variable subclasses that define a `formula` "
            "(model-computed outputs) versus input variables, and map each to a "
            "RawPolicy. The pe-uk universe is being scoped concurrently; wire "
            "this in behind conformance/pe-uk.yaml when that lands."
        )
