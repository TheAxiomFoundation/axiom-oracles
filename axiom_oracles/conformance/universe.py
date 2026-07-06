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


def _pe_variable_kind(name: str, index: "PolicyEngineVariableIndex") -> str:
    """Read one PE-UK variable's simulation kind from its formula, or pure input.

    The kind is derived from the formula source the way the coverage matrix
    classifies it: a formula that reads a ``*_reported`` amount is a
    reported-ceiling passthrough; one that reads a ``*_category`` frozen input is
    a rate-from-category surface; any other formula is a rules engine; no formula
    is a pure microdata input. A conservative textual test on the formula body,
    matching the matrix's own method (grep of the formula source).
    """
    if not index.has_formula(name):
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
    ) -> None:
        self.checkout = Path(checkout).expanduser()
        self.package = package
        self.spine = spine
        self._index = PolicyEngineVariableIndex(self.checkout, package)

    def pinned_version(self) -> str:
        """Read the pinned package version from the checkout's ``pyproject.toml``.

        A fact from the checkout, not memory — it stamps the universe header so a
        conformance claim is scoped to ``policyengine-uk@<version>``, never a
        floating latest.
        """
        pyproject = self.checkout / "pyproject.toml"
        if not pyproject.exists():
            raise FileNotFoundError(
                f"pyproject.toml not found at {pyproject}; cannot pin the "
                "policyengine-uk version for the universe header."
            )
        for line in pyproject.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("version"):
                # version = "2.89.2"
                _, _, rhs = stripped.partition("=")
                return rhs.strip().strip('"').strip("'")
        raise ValueError(
            f"no `version = \"…\"` line in {pyproject}; cannot pin the "
            "policyengine-uk version."
        )

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
                    f"PolicyEngine-UK program {program.name!r}: spine output "
                    f"variable(s) {missing} not found in the pinned checkout's "
                    "tax-benefit system. The model renamed or removed them — "
                    "update PE_UK_PROGRAM_SPINE (a scope review) and regenerate."
                )
            queryable = [v for v in present if self._index.has_formula(v)]
            internal = [v for v in present if not self._index.has_formula(v)]
            # Program kind = the kind of its primary COMPUTED output (first bound
            # output that carries a formula), else pure input. rules dominates
            # rate/reported when a program mixes surfaces (its statutory engine is
            # what a full comparison binds to).
            kinds = [_pe_variable_kind(v, self._index) for v in queryable]
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
