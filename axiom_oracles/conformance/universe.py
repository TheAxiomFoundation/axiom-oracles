"""Enumerate the policy universe an oracle simulates, from its model spine.

Universe facts are never hand-invented: they come from parsing the oracle's own
model definition. The backends here preserve that provenance in either live or
committed form.

* :class:`EuromodUniverseBackend` parses a EUROMOD-platform country XML
  (UKMOD or the JRC EUROMOD release) — the same ``XMLParam/Countries/<CC>/<CC>.xml``
  spine the ``EuromodPlatformRunner`` executes. It reads the policy list for one
  system and, per policy, the output variables its functions write, then splits
  those into *queryable* outputs (present in ``VARCONFIG``, the model's variable
  registry) and *internal-only* locals (absent from ``VARCONFIG``). A pure XML
  parse — no engine, no .NET, no licensed data — so it is CI-friendly.

* :class:`EuromodSpineArtifactBackend` consumes a reviewed single-system JSON
  extract produced by the live EUROMOD backend. It lets CI enforce the real
  model row/output facts when the external model checkout is unavailable,
  rather than turning the drift gate into a no-op.

* :class:`PolicyEngineUniverseBackend` enumerates PolicyEngine-UK's *simulated*
  surface from a pinned ``policyengine-uk`` checkout — the PolicyEngine analogue
  of the EUROMOD policy list. It instantiates the checkout's
  ``CountryTaxBenefitSystem`` (no microdata, no engine run — just the variable
  registry) and, for each PE-UK **program** in a declared spine (the fiscal
  instruments PE-UK models, one row per program like UKMOD's ``<Policy>`` list),
  reads from code which of the program's bound output variables carry a
  ``formula`` and which are pure inputs. The formula body of each is inspected to
  split the four PE-UK simulation kinds the UK coverage matrix documents
  (``docs/uk-coverage-matrix.md``): *rules-simulated* (a ``def formula`` computes
  entitlement from parameters + circumstances), *rate-from-frozen-input-category*
  (a rate table over a frozen ``*_category`` FRS input — comparable on rates
  only), *reported-ceiling* (reads a ``*_reported`` amount, never computes the
  statutory maximum), and *pure-input* (no formula at all). The program→variable
  binding is the spine (structural, like the EUROMOD policy names); every scored
  fact — variable existence, formula presence, kind — is read from the checkout's
  code and the drift ``--check`` fails if the committed universe diverges. The
  package version is pinned in the universe header from the checkout's
  ``pyproject.toml``. This is CI-friendly the same way the EUROMOD backend is: it
  needs the checkout present (and importable), and ``--check`` is a clean no-op
  when it is absent.

The classification *heuristic* below only proposes a default scope; the
authoritative ``in_scope``/``exclusion_reason`` decision lives in the committed
universe YAML and is preserved across regenerations. The generator overwrites
the *facts* (policy list, outputs) and keeps the *decisions*.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from axiom_oracles.conformance.schema import UniversePolicy

_CC_NS = "{http://euromod.com/CountryConfig.xsd}"
_VAR_NS = "{http://euromod.com/VarConfig.xsd}"

#: Schema stamped on committed, single-system EUROMOD spine extracts. These
#: artifacts let CI verify an externally sourced model spine without requiring
#: the licensed/local model checkout itself.
EUROMOD_SPINE_ARTIFACT_SCHEMA = "axiom_oracles.euromod_spine.v1"

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


class EuromodSpineArtifactBackend:
    """Read a committed, single-system EUROMOD policy-spine extract.

    The live :class:`EuromodUniverseBackend` remains the extraction authority.
    This backend consumes its committed JSON result so ``--check`` can compare
    real model facts in CI even when the external EUROMOD checkout is absent.
    Identity checks prevent a DK_2025 extract, for example, from being scored as
    another country, release, or system.
    """

    backend = "euromod"

    def __init__(
        self,
        artifact_path: str | Path,
        *,
        model: str,
        release: str,
        country: str,
        system: str,
    ) -> None:
        self.artifact_path = Path(artifact_path)
        self.model = model
        self.release = release
        self.country = country.upper()
        self.system = system

    def _document(self) -> dict:
        if not self.artifact_path.exists():
            raise FileNotFoundError(
                f"committed EUROMOD spine artifact not found at "
                f"{self.artifact_path}"
            )
        try:
            document = json.loads(self.artifact_path.read_text())
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{self.artifact_path}: invalid JSON ({exc})"
            ) from exc
        if document.get("schema") != EUROMOD_SPINE_ARTIFACT_SCHEMA:
            raise ValueError(
                f"{self.artifact_path}: expected schema "
                f"{EUROMOD_SPINE_ARTIFACT_SCHEMA!r}, got "
                f"{document.get('schema')!r}"
            )

        oracle = document.get("oracle") or {}
        expected_identity = {
            "model": self.model,
            "release": self.release,
            "country": self.country,
        }
        actual_identity = {
            key: oracle.get(key) for key in expected_identity
        }
        if actual_identity != expected_identity:
            raise ValueError(
                f"{self.artifact_path}: oracle identity {actual_identity!r} does "
                f"not match configured identity {expected_identity!r}"
            )

        systems = document.get("systems")
        if not isinstance(systems, list):
            raise ValueError(f"{self.artifact_path}: systems must be a list")
        system_names = {
            row.get("name") for row in systems if isinstance(row, dict)
        }
        if system_names != {self.system} or len(systems) != 1:
            raise ValueError(
                f"{self.artifact_path}: expected the single-system set "
                f"{{{self.system!r}}}, got {system_names!r}"
            )
        if not systems[0].get("id"):
            raise ValueError(
                f"{self.artifact_path}: {self.system} is missing its model id"
            )
        return document

    @staticmethod
    def _outputs(row: dict, key: str, artifact_path: Path) -> tuple[str, ...]:
        values = row.get(key)
        if not isinstance(values, list) or not all(
            isinstance(value, str) and value for value in values
        ):
            raise ValueError(
                f"{artifact_path}: policy {row.get('name')!r} field {key!r} "
                "must be a list of non-empty strings"
            )
        if len(values) != len(set(values)):
            raise ValueError(
                f"{artifact_path}: policy {row.get('name')!r} field {key!r} "
                "contains duplicates"
            )
        return tuple(values)

    def raw_policies(self) -> list[RawPolicy]:
        """Return the exact raw policy facts recorded in the artifact."""
        document = self._document()
        rows = document.get("policies")
        if not isinstance(rows, list):
            raise ValueError(f"{self.artifact_path}: policies must be a list")

        policies: list[RawPolicy] = []
        seen_names: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(
                    f"{self.artifact_path}: every policy must be an object"
                )
            name = row.get("name")
            if not isinstance(name, str) or not name:
                raise ValueError(
                    f"{self.artifact_path}: policy is missing a non-empty name"
                )
            if name in seen_names:
                raise ValueError(
                    f"{self.artifact_path}: duplicate policy name {name!r}"
                )
            seen_names.add(name)

            policy_type = row.get("policy_type")
            switch = row.get("switch")
            if policy_type is not None and not isinstance(policy_type, str):
                raise ValueError(
                    f"{self.artifact_path}: {name} policy_type must be a string"
                )
            if switch is not None and not isinstance(switch, str):
                raise ValueError(
                    f"{self.artifact_path}: {name} switch must be a string"
                )
            all_outputs = self._outputs(row, "all_outputs", self.artifact_path)
            queryable_outputs = self._outputs(
                row, "queryable_outputs", self.artifact_path
            )
            internal_outputs = self._outputs(
                row, "internal_outputs", self.artifact_path
            )
            if set(queryable_outputs) & set(internal_outputs) or set(
                queryable_outputs + internal_outputs
            ) != set(all_outputs):
                raise ValueError(
                    f"{self.artifact_path}: {name} queryable/internal outputs "
                    "must be a disjoint partition of all_outputs"
                )
            policies.append(
                RawPolicy(
                    name=name,
                    policy_type=policy_type,
                    switch=switch,
                    all_outputs=all_outputs,
                    queryable_outputs=queryable_outputs,
                    internal_outputs=internal_outputs,
                )
            )
        return policies


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

    def system_id(self) -> str:
        """Return the model GUID for the selected system."""
        return self._system_id()

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
    * A policy with queryable outputs is proposed in-scope with no suite yet.
      This is the valid, honest uncovered state: it enters the denominator and
      remains visible in the scoreboard burn-down until a live suite covers it.
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
        oracle_switch=policy.switch,
        internal_only_vars=policy.internal_outputs,
    )


#: PolicyEngine-UK simulation kinds, read from a variable's formula body. These
#: are the four kinds the UK coverage matrix (docs/uk-coverage-matrix.md)
#: distinguishes — PE-UK's variable tree is not simply "computed vs input".
PE_KIND_RULES = "rules"  # def formula computes entitlement/liability from statute
PE_KIND_RATE = "rate_from_category"  # rate table over a frozen *_category input
PE_KIND_REPORTED = "reported_ceiling"  # reads a *_reported amount, no statutory max
PE_KIND_INPUT = "pure_input"  # no formula: value straight from microdata


@dataclass(frozen=True)
class PolicyEngineProgram:
    """One PolicyEngine-UK program (a fiscal instrument) in the enumeration spine.

    The spine is the PE analogue of the EUROMOD ``<Policy>`` list: the set of
    instruments PE-UK models, one row per program. ``name`` is the program's
    canonical PE-UK output variable (the id the universe row keys on); ``outputs``
    are all the PE-UK output variables that carry the program's statutory surface,
    in priority order (the queryable set is whichever of these the code gives a
    formula). The binding is structural; the *facts* (which of ``outputs`` have a
    formula, and each one's kind) are read from the checkout's code, never here.
    """

    name: str
    outputs: tuple[str, ...]


#: The PolicyEngine-UK program spine — the fiscal instruments PE-UK simulates,
#: ordered by the coverage matrix's 2026 fiscal weight. One row per program; each
#: names the PE-UK output variable(s) carrying its statutory surface. The
#: generator confirms every listed variable exists in the pinned checkout's
#: tax-benefit system (a missing/renamed variable fails the drift check) and
#: reads each one's simulation kind from its formula — so this list is the
#: *grouping*, and the checkout's code is the *ground truth* for every scored
#: fact. Sourced by enumerating PE-UK's ``variables/**`` formula surface (matrix
#: provenance §"Denominators"); it is NOT the self-reported ``programs.yaml``
#: registry, which drifts from code.
PE_UK_PROGRAM_SPINE: tuple[PolicyEngineProgram, ...] = (
    PolicyEngineProgram("vat", ("vat",)),
    PolicyEngineProgram("income_tax", ("income_tax", "personal_allowance")),
    PolicyEngineProgram(
        "national_insurance",
        (
            "national_insurance",
            "ni_class_1_employee_primary",
            "ni_class_1_employee_additional",
            "ni_class_4_main",
            "ni_class_4_maximum",
            "ni_class_2",
        ),
    ),
    PolicyEngineProgram("state_pension", ("state_pension",)),
    PolicyEngineProgram("universal_credit", ("universal_credit",)),
    PolicyEngineProgram("council_tax", ("council_tax",)),
    PolicyEngineProgram("business_rates", ("business_rates",)),
    PolicyEngineProgram("pip", ("pip", "pip_dl", "pip_m")),
    PolicyEngineProgram("capital_gains_tax", ("capital_gains_tax",)),
    PolicyEngineProgram("fuel_duty", ("fuel_duty",)),
    PolicyEngineProgram(
        "child_benefit",
        ("child_benefit", "child_benefit_respective_amount", "child_benefit_entitlement"),
    ),
    PolicyEngineProgram(
        "housing_benefit", ("housing_benefit", "housing_benefit_applicable_amount")
    ),
    PolicyEngineProgram("stamp_duty_land_tax", ("stamp_duty_land_tax",)),
    PolicyEngineProgram("attendance_allowance", ("attendance_allowance",)),
    PolicyEngineProgram(
        "student_loan_repayments", ("student_loan_repayments", "student_loan_repayment")
    ),
    PolicyEngineProgram("dla", ("dla", "dla_sc", "dla_m")),
    PolicyEngineProgram("esa_contrib", ("esa_contrib",)),
    PolicyEngineProgram(
        "pension_credit", ("pension_credit", "guarantee_credit", "savings_credit")
    ),
    PolicyEngineProgram("carers_allowance", ("carers_allowance",)),
    PolicyEngineProgram("council_tax_benefit", ("council_tax_benefit",)),
    PolicyEngineProgram("marriage_allowance", ("marriage_allowance",)),
    PolicyEngineProgram("esa_income", ("esa_income",)),
    PolicyEngineProgram("winter_fuel_allowance", ("winter_fuel_allowance",)),
    PolicyEngineProgram("incapacity_benefit", ("incapacity_benefit", "afcs", "iidb")),
    PolicyEngineProgram("scottish_child_payment", ("scottish_child_payment",)),
    PolicyEngineProgram("tax_free_childcare", ("tax_free_childcare",)),
    PolicyEngineProgram("carer_support_payment", ("carer_support_payment",)),
    PolicyEngineProgram("council_tax_reduction", ("council_tax_reduction",)),
    PolicyEngineProgram(
        "legacy_means_tested",
        ("jsa_income", "income_support", "working_tax_credit", "child_tax_credit"),
    ),
    PolicyEngineProgram(
        "lbtt_ltt", ("land_and_buildings_transaction_tax", "land_transaction_tax")
    ),
    PolicyEngineProgram("sda", ("sda",)),
    PolicyEngineProgram("ssmg", ("ssmg",)),
    PolicyEngineProgram("tv_licence", ("tv_licence", "free_tv_licence_value")),
)


#: The PolicyEngine-US program spine — the committed *grouping* (the row set /
#: badge denominator). Like :data:`PE_UK_PROGRAM_SPINE` it is the stable list; the
#: checkout's code is ground truth for every scored fact (variable existence,
#: computed-or-input, kind) and the drift ``--check`` fails if the committed
#: universe diverges. PE-US is far larger than PE-UK, so the grouping follows a
#: DETERMINISTIC RULE, biased to PE-US's own module organization, so a new program
#: lands as a new row without a judgement call:
#:
#:   One row per PE-US program instrument PE simulates for the validation year, at
#:   the granularity of the household-facing output variable PE computes, taken
#:   from PE-US's own module tree (``policyengine_us/variables/gov``):
#:
#:   1. Federal income tax → one row per distinct component surface PE computes
#:      (final ``income_tax``, ``income_tax_before_refundable_credits``,
#:      ``taxable_income``, the deduction paths — ``standard_deduction``,
#:      ``itemized_taxable_income_deductions``, ``salt_deduction``,
#:      ``qualified_business_income_deduction`` — and the add-on schedules
#:      ``alternative_minimum_tax``, ``net_investment_income_tax``,
#:      ``capital_gains_tax``), plus one row per credit in PE-US's own
#:      ``gov.irs.credits.refundable`` + ``gov.irs.credits.non_refundable``
#:      parameter lists (deduped to the household credit surface: ``eitc``,
#:      ``ctc``, ``cdcc``, ``american_opportunity_credit`` …).
#:   2. Payroll & SECA → one row per contribution surface (employee/employer
#:      OASDI + Medicare, additional Medicare, self-employment tax).
#:   3. Federal benefit & health programs → one row per member of PE-US's
#:      ``gov.household.household_benefits`` parameter list and the
#:      ``household_health_benefits`` expansion (``ssi``, ``snap``, ``wic`` …,
#:      ``medicaid``, ``aca_ptc``, ``chip``).
#:   4. State-computed programs (per-state, mirroring PE-US's per-state variable
#:      tree) → one row per ``<state>_income_tax`` PE computes (44 states with an
#:      income tax) and one row per member of ``STATE_TANF_VARIABLES`` (51 state
#:      cash-assistance programs — CalWORKs, MFIP, TFA …). SNAP/SSI stay a single
#:      national row because PE computes each as one national variable; TANF and
#:      income tax are per-state because PE computes them as per-state variables.
#:      That asymmetry is the rule following PE's own tree, not a coverage choice.
#:
#: In-scope iff PE carries the primary output with a computed surface (a
#: ``def formula`` OR an ``adds``/``subtracts`` composition). Pure microdata
#: passthroughs PE only *carries* (reported ``social_security``,
#: ``unemployment_compensation``, ``child_support_received``, …, and the
#: reform-lever ``basic_income``) are rows too, excluded ``input_carrying`` /
#: ``technical`` — the PE-US analogue of PE-UK's 8 reported-passthrough
#: exclusions. Sourced by enumerating PE-US's ``variables/gov`` surface against
#: those PE-native parameter lists; NOT a hand-curated wish-list.
PE_US_PROGRAM_SPINE: tuple[PolicyEngineProgram, ...] = (
    # Federal income tax — structural surfaces (10)
    PolicyEngineProgram("income_tax", ("income_tax",)),
    PolicyEngineProgram(
        "income_tax_before_refundable_credits",
        ("income_tax_before_refundable_credits",),
    ),
    PolicyEngineProgram("taxable_income", ("taxable_income",)),
    PolicyEngineProgram("standard_deduction", ("standard_deduction",)),
    PolicyEngineProgram(
        "itemized_taxable_income_deductions",
        ("itemized_taxable_income_deductions",),
    ),
    PolicyEngineProgram("salt_deduction", ("salt_deduction",)),
    PolicyEngineProgram(
        "qualified_business_income_deduction",
        ("qualified_business_income_deduction",),
    ),
    PolicyEngineProgram("alternative_minimum_tax", ("alternative_minimum_tax",)),
    PolicyEngineProgram("net_investment_income_tax", ("net_investment_income_tax",)),
    PolicyEngineProgram("capital_gains_tax", ("capital_gains_tax",)),
    # Federal income tax — credits (gov.irs.credits.refundable/non_refundable) (13)
    PolicyEngineProgram("eitc", ("eitc",)),
    PolicyEngineProgram("ctc", ("ctc",)),
    PolicyEngineProgram("cdcc", ("cdcc",)),
    PolicyEngineProgram("american_opportunity_credit", ("american_opportunity_credit",)),
    PolicyEngineProgram("lifetime_learning_credit", ("lifetime_learning_credit",)),
    PolicyEngineProgram("savers_credit", ("savers_credit",)),
    PolicyEngineProgram("elderly_disabled_credit", ("elderly_disabled_credit",)),
    PolicyEngineProgram("recovery_rebate_credit", ("recovery_rebate_credit",)),
    PolicyEngineProgram(
        "residential_clean_energy_credit", ("residential_clean_energy_credit",)
    ),
    PolicyEngineProgram(
        "energy_efficient_home_improvement_credit",
        ("energy_efficient_home_improvement_credit",),
    ),
    PolicyEngineProgram("foreign_tax_credit", ("foreign_tax_credit",)),
    PolicyEngineProgram("new_clean_vehicle_credit", ("new_clean_vehicle_credit",)),
    PolicyEngineProgram("used_clean_vehicle_credit", ("used_clean_vehicle_credit",)),
    # Payroll & SECA (6)
    PolicyEngineProgram("employee_social_security_tax", ("employee_social_security_tax",)),
    PolicyEngineProgram("employer_social_security_tax", ("employer_social_security_tax",)),
    PolicyEngineProgram("employee_medicare_tax", ("employee_medicare_tax",)),
    PolicyEngineProgram("employer_medicare_tax", ("employer_medicare_tax",)),
    PolicyEngineProgram("additional_medicare_tax", ("additional_medicare_tax",)),
    PolicyEngineProgram("self_employment_tax", ("self_employment_tax",)),
    # Federal benefit & health programs (gov.household.household_benefits) (16)
    PolicyEngineProgram("ssi", ("ssi",)),
    PolicyEngineProgram("snap", ("snap",)),
    PolicyEngineProgram("wic", ("wic",)),
    PolicyEngineProgram("free_school_meals", ("free_school_meals",)),
    PolicyEngineProgram("reduced_price_school_meals", ("reduced_price_school_meals",)),
    PolicyEngineProgram("acp", ("acp",)),
    PolicyEngineProgram("ebb", ("ebb",)),
    PolicyEngineProgram("head_start", ("head_start",)),
    PolicyEngineProgram("early_head_start", ("early_head_start",)),
    PolicyEngineProgram(
        "spm_unit_capped_housing_subsidy", ("spm_unit_capped_housing_subsidy",)
    ),
    PolicyEngineProgram(
        "commodity_supplemental_food_program",
        ("commodity_supplemental_food_program",),
    ),
    PolicyEngineProgram(
        "high_efficiency_electric_home_rebate",
        ("high_efficiency_electric_home_rebate",),
    ),
    PolicyEngineProgram(
        "residential_efficiency_electrification_rebate",
        ("residential_efficiency_electrification_rebate",),
    ),
    PolicyEngineProgram("medicaid", ("medicaid",)),
    PolicyEngineProgram("aca_ptc", ("aca_ptc",)),
    PolicyEngineProgram("chip", ("chip",)),
    # Carried microdata passthroughs — reported income PE sums but does not
    # compute from statute (rows, excluded input_carrying / technical) (8)
    PolicyEngineProgram("social_security", ("social_security",)),
    PolicyEngineProgram("unemployment_compensation", ("unemployment_compensation",)),
    PolicyEngineProgram("child_support_received", ("child_support_received",)),
    PolicyEngineProgram("workers_compensation", ("workers_compensation",)),
    PolicyEngineProgram("educational_assistance", ("educational_assistance",)),
    PolicyEngineProgram("financial_assistance", ("financial_assistance",)),
    PolicyEngineProgram("survivor_benefits", ("survivor_benefits",)),
    PolicyEngineProgram("basic_income", ("basic_income",)),
    # State income tax — one row per state PE computes (<state>_income_tax) (44)
    PolicyEngineProgram("al_income_tax", ("al_income_tax",)),
    PolicyEngineProgram("ar_income_tax", ("ar_income_tax",)),
    PolicyEngineProgram("az_income_tax", ("az_income_tax",)),
    PolicyEngineProgram("ca_income_tax", ("ca_income_tax",)),
    PolicyEngineProgram("co_income_tax", ("co_income_tax",)),
    PolicyEngineProgram("ct_income_tax", ("ct_income_tax",)),
    PolicyEngineProgram("dc_income_tax", ("dc_income_tax",)),
    PolicyEngineProgram("de_income_tax", ("de_income_tax",)),
    PolicyEngineProgram("ga_income_tax", ("ga_income_tax",)),
    PolicyEngineProgram("hi_income_tax", ("hi_income_tax",)),
    PolicyEngineProgram("ia_income_tax", ("ia_income_tax",)),
    PolicyEngineProgram("id_income_tax", ("id_income_tax",)),
    PolicyEngineProgram("il_income_tax", ("il_income_tax",)),
    PolicyEngineProgram("in_income_tax", ("in_income_tax",)),
    PolicyEngineProgram("ks_income_tax", ("ks_income_tax",)),
    PolicyEngineProgram("ky_income_tax", ("ky_income_tax",)),
    PolicyEngineProgram("la_income_tax", ("la_income_tax",)),
    PolicyEngineProgram("ma_income_tax", ("ma_income_tax",)),
    PolicyEngineProgram("md_income_tax", ("md_income_tax",)),
    PolicyEngineProgram("me_income_tax", ("me_income_tax",)),
    PolicyEngineProgram("mi_income_tax", ("mi_income_tax",)),
    PolicyEngineProgram("mn_income_tax", ("mn_income_tax",)),
    PolicyEngineProgram("mo_income_tax", ("mo_income_tax",)),
    PolicyEngineProgram("ms_income_tax", ("ms_income_tax",)),
    PolicyEngineProgram("mt_income_tax", ("mt_income_tax",)),
    PolicyEngineProgram("nc_income_tax", ("nc_income_tax",)),
    PolicyEngineProgram("nd_income_tax", ("nd_income_tax",)),
    PolicyEngineProgram("ne_income_tax", ("ne_income_tax",)),
    PolicyEngineProgram("nh_income_tax", ("nh_income_tax",)),
    PolicyEngineProgram("nj_income_tax", ("nj_income_tax",)),
    PolicyEngineProgram("nm_income_tax", ("nm_income_tax",)),
    PolicyEngineProgram("ny_income_tax", ("ny_income_tax",)),
    PolicyEngineProgram("oh_income_tax", ("oh_income_tax",)),
    PolicyEngineProgram("ok_income_tax", ("ok_income_tax",)),
    PolicyEngineProgram("or_income_tax", ("or_income_tax",)),
    PolicyEngineProgram("pa_income_tax", ("pa_income_tax",)),
    PolicyEngineProgram("ri_income_tax", ("ri_income_tax",)),
    PolicyEngineProgram("sc_income_tax", ("sc_income_tax",)),
    PolicyEngineProgram("ut_income_tax", ("ut_income_tax",)),
    PolicyEngineProgram("va_income_tax", ("va_income_tax",)),
    PolicyEngineProgram("vt_income_tax", ("vt_income_tax",)),
    PolicyEngineProgram("wa_income_tax", ("wa_income_tax",)),
    PolicyEngineProgram("wi_income_tax", ("wi_income_tax",)),
    PolicyEngineProgram("wv_income_tax", ("wv_income_tax",)),
    # State TANF / cash assistance — one row per STATE_TANF_VARIABLES member (51)
    PolicyEngineProgram("al_tanf", ("al_tanf",)),
    PolicyEngineProgram("az_tanf", ("az_tanf",)),
    PolicyEngineProgram("ca_tanf", ("ca_tanf",)),
    PolicyEngineProgram("co_tanf", ("co_tanf",)),
    PolicyEngineProgram("dc_tanf", ("dc_tanf",)),
    PolicyEngineProgram("de_tanf", ("de_tanf",)),
    PolicyEngineProgram("ga_tanf", ("ga_tanf",)),
    PolicyEngineProgram("hi_tanf", ("hi_tanf",)),
    PolicyEngineProgram("il_tanf", ("il_tanf",)),
    PolicyEngineProgram("in_tanf", ("in_tanf",)),
    PolicyEngineProgram("ks_tanf", ("ks_tanf",)),
    PolicyEngineProgram("me_tanf", ("me_tanf",)),
    PolicyEngineProgram("mo_tanf", ("mo_tanf",)),
    PolicyEngineProgram("ms_tanf", ("ms_tanf",)),
    PolicyEngineProgram("mt_tanf", ("mt_tanf",)),
    PolicyEngineProgram("nc_tanf", ("nc_tanf",)),
    PolicyEngineProgram("nd_tanf", ("nd_tanf",)),
    PolicyEngineProgram("nv_tanf", ("nv_tanf",)),
    PolicyEngineProgram("ny_tanf", ("ny_tanf",)),
    PolicyEngineProgram("ok_tanf", ("ok_tanf",)),
    PolicyEngineProgram("or_tanf", ("or_tanf",)),
    PolicyEngineProgram("pa_tanf", ("pa_tanf",)),
    PolicyEngineProgram("sc_tanf", ("sc_tanf",)),
    PolicyEngineProgram("sd_tanf", ("sd_tanf",)),
    PolicyEngineProgram("tx_tanf", ("tx_tanf",)),
    PolicyEngineProgram("va_tanf", ("va_tanf",)),
    PolicyEngineProgram("wa_tanf", ("wa_tanf",)),
    PolicyEngineProgram("ak_atap", ("ak_atap",)),
    PolicyEngineProgram("ar_tea", ("ar_tea",)),
    PolicyEngineProgram("ct_tfa", ("ct_tfa",)),
    PolicyEngineProgram("fl_tca", ("fl_tca",)),
    PolicyEngineProgram("ia_fip", ("ia_fip",)),
    PolicyEngineProgram("id_tafi", ("id_tafi",)),
    PolicyEngineProgram("ky_ktap", ("ky_ktap",)),
    PolicyEngineProgram("la_fitap", ("la_fitap",)),
    PolicyEngineProgram("ma_tafdc", ("ma_tafdc",)),
    PolicyEngineProgram("md_tca", ("md_tca",)),
    PolicyEngineProgram("mi_fip", ("mi_fip",)),
    PolicyEngineProgram("mn_mfip", ("mn_mfip",)),
    PolicyEngineProgram("ne_adc", ("ne_adc",)),
    PolicyEngineProgram("nh_fanf", ("nh_fanf",)),
    PolicyEngineProgram("nj_wfnj", ("nj_wfnj",)),
    PolicyEngineProgram("nm_works", ("nm_works",)),
    PolicyEngineProgram("oh_owf", ("oh_owf",)),
    PolicyEngineProgram("ri_works", ("ri_works",)),
    PolicyEngineProgram("tn_ff", ("tn_ff",)),
    PolicyEngineProgram("ut_fep", ("ut_fep",)),
    PolicyEngineProgram("vt_reach_up", ("vt_reach_up",)),
    PolicyEngineProgram("wi_works", ("wi_works",)),
    PolicyEngineProgram("wv_works", ("wv_works",)),
    PolicyEngineProgram("wy_power", ("wy_power",)),
)


def _pe_variable_kind(
    name: str,
    index: "PolicyEngineVariableIndex",
    include_adds_subtracts: bool = False,
) -> str:
    """Read one PE variable's simulation kind from its formula, or pure input.

    The kind is derived from the formula source the way the coverage matrix
    classifies it: a formula that reads a ``*_reported`` amount is a
    reported-ceiling passthrough; one that reads a ``*_category`` frozen input is
    a rate-from-category surface; any other formula is a rules engine; no formula
    is a pure microdata input. A conservative textual test on the formula body,
    matching the matrix's own method (grep of the formula source).

    ``include_adds_subtracts`` extends the "PE simulates it" test to the
    PolicyEngine-US convention where an aggregate surface is composed from an
    ``adds``/``subtracts`` variable list rather than a ``def formula`` (e.g.
    ``income_tax_before_credits``, ``standard_deduction``, every
    ``<state>_income_tax``). A variable with no ``def formula`` but a non-empty
    ``adds``/``subtracts`` list IS computed — a rules surface — so it must not be
    misread as a pure input. PE-US carries no ``*_reported``/``*_category``
    frozen-input surfaces, so composed variables classify as ``rules``.
    """
    if not index.has_formula(name):
        if include_adds_subtracts and index.has_adds_or_subtracts(name):
            return PE_KIND_RULES
        return PE_KIND_INPUT
    source = index.formula_source(name)
    if "_reported" in source:
        return PE_KIND_REPORTED
    if "_category" in source:
        return PE_KIND_RATE
    return PE_KIND_RULES


class PolicyEngineVariableIndex:
    """The code-derived variable surface of a pinned ``policyengine-uk`` checkout.

    Instantiates the checkout's ``CountryTaxBenefitSystem`` (importing the package
    *from the checkout*, so facts come from that exact tree, not any other
    installed copy) and exposes, per variable name: whether it carries a formula
    (PE-UK computes it) and, if so, its formula source (to classify the kind). No
    microdata is loaded and no simulation is run — building the tax-benefit system
    only reads the variable registry, so this is cheap and deterministic.
    """

    def __init__(self, checkout: Path, package: str) -> None:
        self.checkout = checkout
        self.package = package
        self._formula_source: dict[str, str] = {}
        self._has_formula: dict[str, bool] = {}
        #: PE-US composes many surfaces from an ``adds``/``subtracts`` variable
        #: list instead of a ``def formula`` — those are computed, not inputs.
        self._adds_or_subtracts: dict[str, bool] = {}
        self._variables: set[str] = set()
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        import importlib
        import inspect
        import sys

        checkout = str(self.checkout)
        # Import the package FROM the pinned checkout: prepend its path and drop
        # any already-imported copy so a differently-versioned installed package
        # cannot shadow the tree we are pinning facts to.
        inserted = checkout not in sys.path
        if inserted:
            sys.path.insert(0, checkout)
        stale = [m for m in sys.modules if m == self.package or m.startswith(self.package + ".")]
        saved = {m: sys.modules.pop(m) for m in stale}
        try:
            pkg = importlib.import_module(self.package)
            pkg_file = getattr(pkg, "__file__", "") or ""
            if checkout not in str(Path(pkg_file).resolve()):
                raise RuntimeError(
                    f"imported {self.package} from {pkg_file!r}, not the pinned "
                    f"checkout {checkout!r}; refusing to enumerate facts from the "
                    "wrong tree. Ensure the checkout path is importable and its "
                    "dependencies are installed."
                )
            tbs = pkg.CountryTaxBenefitSystem()
            for var_name, variable in tbs.variables.items():
                self._variables.add(var_name)
                formulas = getattr(variable, "formulas", None)
                has_formula = bool(formulas) and len(formulas) > 0
                self._has_formula[var_name] = has_formula
                self._adds_or_subtracts[var_name] = bool(
                    getattr(variable, "adds", None)
                ) or bool(getattr(variable, "subtracts", None))
                if has_formula:
                    sources: list[str] = []
                    for formula in formulas.values():
                        try:
                            sources.append(inspect.getsource(formula))
                        except (OSError, TypeError):
                            continue
                    self._formula_source[var_name] = "\n".join(sources)
        finally:
            # Restore whatever module state we displaced (leave the pinned import
            # in place for the caller's process life; tests re-import cleanly).
            for name, module in saved.items():
                sys.modules.setdefault(name, module)
        self._loaded = True

    def exists(self, name: str) -> bool:
        self._load()
        return name in self._variables

    def has_formula(self, name: str) -> bool:
        self._load()
        return self._has_formula.get(name, False)

    def has_adds_or_subtracts(self, name: str) -> bool:
        self._load()
        return self._adds_or_subtracts.get(name, False)

    def formula_source(self, name: str) -> str:
        self._load()
        return self._formula_source.get(name, "")


class PolicyEngineUniverseBackend:
    """Enumerate PolicyEngine-UK's simulated surface from a pinned checkout.

    The PolicyEngine analogue of :class:`EuromodUniverseBackend`: instead of
    parsing a EUROMOD country XML it reads the checkout's ``CountryTaxBenefitSystem``
    variable registry and walks the declared program spine
    (:data:`PE_UK_PROGRAM_SPINE`), producing one :class:`RawPolicy` per program.

    For each program it derives, purely from the checkout's code:

    * ``queryable_outputs`` — the program's bound output variables that carry a
      formula (the surfaces PE-UK actually computes, so a comparison can bind to
      them). Ordered as the spine lists them.
    * ``internal_outputs`` — bound outputs that are pure microdata inputs (no
      formula): the evidence for classifying an input-carrying passthrough.
    * ``policy_type`` — the program's simulation kind (``rules`` /
      ``rate_from_category`` / ``reported_ceiling`` / ``pure_input``), read from
      the primary computed output's formula. This is the fact the committed
      universe's ``comparability``/``exclusion_reason`` decision is reviewed
      against, the PE parallel of the EUROMOD policy ``Type``.

    The scope decision (``in_scope``/``exclusion_reason``/``suite``/``comparability``)
    is a committed decision preserved across regenerations, exactly as for the
    EUROMOD backend; this backend only supplies the regenerated facts.
    """

    backend = "policyengine"

    def __init__(
        self,
        checkout: str | Path,
        package: str = "policyengine_uk",
        spine: tuple[PolicyEngineProgram, ...] = PE_UK_PROGRAM_SPINE,
        include_adds_subtracts: bool = False,
    ) -> None:
        self.checkout = Path(checkout).expanduser()
        self.package = package
        self.spine = spine
        #: Treat ``adds``/``subtracts``-composed variables as computed surfaces
        #: (the PE-US aggregate convention). Off for PE-UK, whose surfaces are
        #: ``def formula`` and whose input-carriers are genuine pure inputs.
        self.include_adds_subtracts = include_adds_subtracts
        self._index = PolicyEngineVariableIndex(self.checkout, package)

    def _is_computed(self, name: str) -> bool:
        """A variable PE simulates: a ``def formula`` or (PE-US) an ``adds``/
        ``subtracts`` composition. Bare inputs are not computed."""
        if self._index.has_formula(name):
            return True
        return self.include_adds_subtracts and self._index.has_adds_or_subtracts(
            name
        )

    def pinned_version(self) -> str:
        """Pin the exact package version enumerated — a fact from the checkout.

        Reads the checkout's ``pyproject.toml`` (the source-tree case, e.g.
        ``policyengine-uk`` at ``2.89.2``). When the checkout is a pip-installed
        package tree with no ``pyproject.toml`` at its root (the CI-friendly
        ``pip install policyengine-us==<v>`` case), fall back to the installed
        distribution metadata. Either way the header is scoped to
        ``policyengine-*@<version>``, never a floating latest.
        """
        pyproject = self.checkout / "pyproject.toml"
        if pyproject.exists():
            for line in pyproject.read_text().splitlines():
                stripped = line.strip()
                if stripped.startswith("version"):
                    # version = "2.89.2"
                    _, _, rhs = stripped.partition("=")
                    return rhs.strip().strip('"').strip("'")
            raise ValueError(
                f"no `version = \"…\"` line in {pyproject}; cannot pin the "
                f"{self.package} version."
            )
        # No pyproject at the checkout root: use the installed distribution's
        # metadata (dist name = package with underscores → hyphens).
        import importlib.metadata as _metadata

        dist = self.package.replace("_", "-")
        try:
            return _metadata.version(dist)
        except _metadata.PackageNotFoundError as exc:
            raise FileNotFoundError(
                f"pyproject.toml not found at {pyproject} and distribution "
                f"{dist!r} is not installed; cannot pin the {self.package} "
                "version for the universe header."
            ) from exc

    def raw_policies(self) -> list[RawPolicy]:
        """Enumerate every program in the spine with its code-derived output facts."""
        policies: list[RawPolicy] = []
        for program in self.spine:
            present = [v for v in program.outputs if self._index.exists(v)]
            missing = [v for v in program.outputs if not self._index.exists(v)]
            if missing:
                # A spine variable vanished/renamed in the checkout: fail loudly so
                # the drift check forces a spine review rather than silently
                # dropping the program's surface.
                raise ValueError(
                    f"{self.package} program {program.name!r}: spine output "
                    f"variable(s) {missing} not found in the pinned checkout's "
                    "tax-benefit system. The model renamed or removed them — "
                    "update the program spine (a scope review) and regenerate."
                )
            queryable = [v for v in present if self._is_computed(v)]
            internal = [v for v in present if not self._is_computed(v)]
            # Program kind = the kind of its primary COMPUTED output (first bound
            # output that carries a formula), else pure input. rules dominates
            # rate/reported when a program mixes surfaces (its statutory engine is
            # what a full comparison binds to).
            kinds = [
                _pe_variable_kind(v, self._index, self.include_adds_subtracts)
                for v in queryable
            ]
            if PE_KIND_RULES in kinds:
                policy_type = PE_KIND_RULES
            elif PE_KIND_RATE in kinds:
                policy_type = PE_KIND_RATE
            elif PE_KIND_REPORTED in kinds:
                policy_type = PE_KIND_REPORTED
            else:
                policy_type = PE_KIND_INPUT
            policies.append(
                RawPolicy(
                    name=program.name,
                    policy_type=policy_type,
                    switch=None,
                    all_outputs=tuple(program.outputs),
                    queryable_outputs=tuple(queryable),
                    internal_outputs=tuple(internal),
                )
            )
        return policies


# ---------------------------------------------------------------------------
# Yale Budget Lab tariff-rate-tracker backend
# ---------------------------------------------------------------------------

#: RATE_SCHEMA literals that are table keys / interval framing, not simulated
#: surfaces. Every OTHER literal column must map into a universe row (the
#: no-silent-drop accounting); a new framing column must be added here
#: deliberately, so it cannot vanish from the accounting unnoticed.
_YALE_KEY_COLUMNS = frozenset(
    {"hts10", "country", "revision", "effective_date", "valid_from", "valid_until"}
)


def parse_r_string_vector(source: str, name: str) -> list[str | None]:
    """Parse ``name = c('a', 'b', NA, ...)`` from an R source block.

    Returns the quoted strings in order, with ``NA`` entries as ``None``.
    Only literal entries are read — a spliced expression inside ``c(...)``
    (e.g. ``registry$rate_col[...]``) raises, because a universe fact must be
    a literal the parse can pin, never something we'd re-derive by memory.
    """
    import re

    match = re.search(
        rf"{re.escape(name)}\s*=\s*c\((.*?)\)", source, flags=re.DOTALL
    )
    if match is None:
        raise ValueError(f"vector {name!r} not found in registry source")
    entries: list[str | None] = []
    for raw in match.group(1).split(","):
        token = raw.strip()
        if not token:
            continue
        if token == "NA":
            entries.append(None)
        elif (token.startswith("'") and token.endswith("'")) or (
            token.startswith('"') and token.endswith('"')
        ):
            entries.append(token[1:-1])
        elif re.fullmatch(r"-?\d+L?", token):
            entries.append(token.rstrip("L"))
        else:
            raise ValueError(
                f"vector {name!r} contains a non-literal entry {token!r}; "
                "the registry parse only pins literals"
            )
    return entries


def parse_r_quoted_literals(source: str) -> list[str]:
    """All single/double-quoted string literals in an R block, in order."""
    import re

    return [
        m.group(1) or m.group(2)
        for m in re.finditer(r"'([^']*)'|\"([^\"]*)\"", source)
    ]


class YaleTariffUniverseBackend:
    """Enumerate the Yale Budget Lab tariff-rate-tracker's statutory panel spine.

    The oracle's own model spine is ``src/model/authority_registry.R``
    (``AUTHORITY_REGISTRY``: one row per tariff authority rate layer, with its
    normalized authority name and stacking class) plus the canonical output
    schema ``src/model/rate_schema.R`` (``RATE_SCHEMA``). Both are read by a
    pure text parse of literal vectors — no R runtime — so this is CI-friendly
    the same way the EUROMOD XML parse is.

    Per panel authority the *statutory* column ``statutory_<rate_col>`` is the
    queryable comparison surface (created pre-exemption/pre-stacking at
    ``src/pipeline/06_calculate_rates.R`` — the backend verifies each name
    appears there, so a renamed statutory column fails the drift check). The
    effective-layer columns (``rate_*``/``net_*``, post share/utilization
    transform) are recorded as internal-only evidence, outside the statutory
    comparison boundary. The MFN base is its own row (``statutory_base_rate``
    vs the exemption-share-adjusted effective ``base_rate``); the Swiss
    framework metadata columns and the stacking/framing outputs are emitted as
    non-queryable rows so the exclusion decision is visible, never a silent
    drop.
    """

    backend = "yale-tariff"

    def __init__(self, checkout: str | Path) -> None:
        self.checkout = Path(checkout).expanduser()
        self._registry_r = self.checkout / "src" / "model" / "authority_registry.R"
        self._schema_r = self.checkout / "src" / "model" / "rate_schema.R"
        self._pipeline_r = (
            self.checkout / "src" / "pipeline" / "06_calculate_rates.R"
        )

    def pinned_commit(self) -> str:
        """The checkout's HEAD commit — the oracle release the header pins."""
        import subprocess

        try:
            result = subprocess.run(
                ["git", "-C", str(self.checkout), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ValueError(
                f"cannot pin the tariff-rate-tracker commit at {self.checkout}: "
                f"{exc}"
            ) from exc
        return result.stdout.strip()

    def _registry_rows(self) -> list[dict]:
        source = self._registry_r.read_text()
        import re

        block = re.search(
            r"AUTHORITY_REGISTRY\s*<-\s*data\.frame\((.*?)\n\)\n",
            source,
            flags=re.DOTALL,
        )
        if block is None:
            raise ValueError(
                f"AUTHORITY_REGISTRY data.frame not found in {self._registry_r}"
            )
        body = block.group(1)
        columns = {
            name: parse_r_string_vector(body, name)
            for name in (
                "rate_col",
                "net_col",
                "spec_authority",
                "default_stacking_class",
                "panel_order",
                "schema_group",
            )
        }
        length = len(columns["rate_col"])
        if any(len(v) != length for v in columns.values()):
            raise ValueError(
                f"AUTHORITY_REGISTRY vectors have unequal lengths in "
                f"{self._registry_r}"
            )
        return [
            {name: values[i] for name, values in columns.items()}
            for i in range(length)
        ]

    def _rate_schema_literals(self) -> list[str]:
        source = self._schema_r.read_text()
        import re

        block = re.search(
            r"RATE_SCHEMA\s*<-\s*c\((.*?)\n\)\n", source, flags=re.DOTALL
        )
        if block is None:
            raise ValueError(f"RATE_SCHEMA not found in {self._schema_r}")
        return parse_r_quoted_literals(block.group(1))

    def _statutory_column(self, rate_col: str) -> str:
        """``rate_232`` -> ``statutory_rate_232``, verified against the pipeline.

        The statutory columns are created at src/pipeline/06_calculate_rates.R
        (the pre-exemption, pre-stacking save); a rename there must fail the
        drift check, not silently break the comparison surface.
        """
        column = f"statutory_{rate_col}"
        if column not in self._pipeline_text():
            raise ValueError(
                f"statutory column {column!r} not found in {self._pipeline_r}; "
                "the model renamed or removed it — review the panel suite's "
                "statutory column mapping and regenerate"
            )
        return column

    def _pipeline_text(self) -> str:
        if not hasattr(self, "_pipeline_cache"):
            self._pipeline_cache = self._pipeline_r.read_text()
        return self._pipeline_cache

    def raw_policies(self) -> list[RawPolicy]:
        registry = self._registry_rows()
        # The RATE_SCHEMA c(...) splices the registry's per-group rate columns
        # via `panel_registry$rate_col[schema_group == '<group>']`; the quoted
        # group names in those splices are selectors, not columns.
        group_names = {r["schema_group"] for r in registry if r["schema_group"]}
        schema_literals = [
            c for c in self._rate_schema_literals() if c not in group_names
        ]

        policies: list[RawPolicy] = []

        # MFN base: statutory_base_rate is the parsed HTS column-1 rate the
        # panel keeps; the effective base_rate applies MFN exemption shares
        # (06_calculate_rates.R step 6c) — outside the statutory boundary.
        for required in ("statutory_base_rate", "base_rate"):
            if required not in schema_literals:
                raise ValueError(
                    f"{required!r} missing from RATE_SCHEMA in {self._schema_r}"
                )
        policies.append(
            RawPolicy(
                name="mfn_base",
                policy_type="base",
                switch=None,
                all_outputs=("statutory_base_rate", "base_rate"),
                queryable_outputs=("statutory_base_rate",),
                internal_outputs=("base_rate",),
            )
        )

        # One row per panel authority in the model's own registry.
        for row in registry:
            if row["panel_order"] is None:
                continue  # scenario-only authority: not in the baseline panel
            rate_col = row["rate_col"]
            statutory = self._statutory_column(rate_col)
            policies.append(
                RawPolicy(
                    name=row["spec_authority"] or rate_col,
                    policy_type=row["default_stacking_class"],
                    switch=None,
                    all_outputs=(statutory, rate_col, row["net_col"]),
                    queryable_outputs=(statutory,),
                    internal_outputs=(rate_col, row["net_col"]),
                )
            )

        # Every remaining RATE_SCHEMA literal must land in a declared row (the
        # no-silent-drop accounting): swiss framework metadata + the stacking/
        # framing outputs. A new schema column fails here until classified.
        claimed = {
            "statutory_base_rate",
            "base_rate",
            *(f"statutory_{r['rate_col']}" for r in registry),
        } | _YALE_KEY_COLUMNS
        remaining = [c for c in schema_literals if c not in claimed]
        swiss = [c for c in remaining if c.startswith("swiss_")]
        framing = [c for c in remaining if not c.startswith("swiss_")]
        expected_framing = {
            "metal_share",
            "heading_program",
            "total_additional",
            "total_rate",
            "usmca_eligible",
        }
        unexpected = set(framing) - expected_framing
        if unexpected:
            raise ValueError(
                "RATE_SCHEMA carries unclassified column(s) "
                f"{sorted(unexpected)}; classify them in the Yale universe "
                "backend (a new simulated surface must not be silently dropped)"
            )
        policies.append(
            RawPolicy(
                name="swiss_framework",
                policy_type="framework_metadata",
                switch=None,
                all_outputs=tuple(swiss),
                queryable_outputs=(),
                internal_outputs=tuple(swiss),
            )
        )
        policies.append(
            RawPolicy(
                name="stacking_outputs",
                policy_type="output_framing",
                switch=None,
                all_outputs=tuple(framing),
                queryable_outputs=(),
                internal_outputs=tuple(framing),
            )
        )
        return policies
