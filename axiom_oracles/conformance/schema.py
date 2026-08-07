"""Schema constants and value objects for the conformance universe.

The universe file (``conformance/<jurisdiction>.yaml``, schema
``axiom_oracles.conformance.v1``) has an oracle-identity header and one row per
policy the oracle simulates. This module defines the closed vocabularies and the
row value object so the generator, the scoreboard, and the gates all agree on
one definition of the shape — a drift between them is exactly the class of bug
this harness exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

#: Schema id stamped in every generated universe file.
CONFORMANCE_SCHEMA_VERSION = "axiom_oracles.conformance.v1"

#: Closed set of reasons a policy the oracle *simulates* is nonetheless excluded
#: from conformance scope. Every out-of-scope row MUST carry exactly one.
#:
#: - ``input_carrying``: the "policy" only initialises or carries input
#:   variables into the simulation (EUROMOD ``InitVars``/``SetDefault`` style);
#:   it computes no benefit/tax the way a real instrument does.
#: - ``technical``: engine scaffolding — uprating, output framing, RNG,
#:   constant/income-list definitions, aggregation/poverty-line helpers.
#: - ``takeup_adjustment``: the policy exists to model *take-up* (who claims a
#:   benefit they are entitled to), a stochastic behavioural adjustment Axiom
#:   deliberately does not encode. The canonical UK case is ``bsauc_s``'s
#:   take-up handling (see ``euromod_issues.json``); comparing entitlement law
#:   against a take-up-adjusted figure would score encoding against behaviour.
#: - ``not_a_policy``: a container/def block that is not a distinct policy at
#:   all (e.g. a shared definition module referenced by others).
#: - ``unobservable_boundary``: the oracle simulates the policy AND writes its
#:   outputs, but the comparison boundary depends on engine-internal variables
#:   absent from the model's variable registry (VARCONFIG), so only the final
#:   output is queryable — any non-degenerate comparison is impossible and the
#:   degenerate one vacuous. Canonical UK case: ``bmu_s`` (UKMOD's simplified
#:   national Council Tax Reduction) — its applicable amount and non-dependant
#:   deductions are ``i_``-prefixed locals absent from VARCONFIG. Also the UKMOD
#:   TCO indirect-tax extension (``tco_calcbase``/``tco_calcadjusted``): present
#:   and computing, but its consumption-tax bases are non-``_s`` non-registry
#:   variables.
#: - ``extension_not_available``: the oracle *would* simulate the policy as a
#:   real instrument, but the model content that computes it is not in the public
#:   release — the policy body is definitional only (no ``OutputVar``) because the
#:   required extension/add-on (and often its microdata prerequisite) is absent.
#:   Distinct from ``technical`` (which is genuine scaffolding) and from
#:   ``unobservable_boundary`` (where the policy DOES compute). Canonical case:
#:   EUROMOD BE ``tco_be`` indirect tax — 15 ``DefConst``/``DefIl`` functions, no
#:   compute function, no consumption-tax extension in ``EUROMOD_RELEASES_J2.0+``
#:   (axiom-oracles#144). Requires a ``note`` recording the verdict.
#: - ``oracle_dataset_lacks_input``: the oracle DOES simulate the policy and its
#:   outputs ARE observable (a queryable ``_s`` surface), but the input that
#:   *activates* it is absent from the public dataset's schema, so under the
#:   registration-free setup the policy can never trigger and the only achievable
#:   comparison is vacuous (0 == 0). Distinct from ``unobservable_boundary`` (the
#:   policy computes but the comparison *boundary* is engine-internal) and from
#:   ``extension_not_available`` (the compute content itself is not in the public
#:   release). Canonical case: EUROMOD BE ``bfapl_be`` parental-leave allowance —
#:   encoded verbatim in rulespec-be (RD 29.10.1997 / RD 02.01.1991) but the
#:   ``lpb`` parental-leave-months input column is absent from the BE HHoT demo
#:   dataset schema, so ``bfapl_s`` stays 0 for every synthetic case (probe
#:   lineage: rulespec-be#86, axiom-oracles#150/#158, axiom-oracles#160). Requires
#:   a ``note`` recording the absent input and the probe evidence pointer.
#: - ``oracle_models_repealed_law``: the oracle retains a policy for a benefit or
#:   tax REPEALED before the validation period, so there is no current-law
#:   instrument for Axiom (which encodes current law) to compare. The policy is
#:   switch=on and runs, but produces no payable/current output for synthetic
#:   cases in the validation period — typically because it is gated (through the
#:   UKMOD Universal-Credit transition or a legacy-claimant receipt input) to a
#:   pre-repeal population that no longer exists. Distinct from
#:   ``oracle_dataset_lacks_input`` (there a dataset column WOULD make it
#:   comparable; here no dataset fix can, because the instrument itself is
#:   repealed and Axiom has no current-law surface for it by design) and from
#:   ``technical`` (a real instrument, not scaffolding). Requires a ``note``
#:   recording the repeal with a citation AND probe evidence that the oracle
#:   produces no current output. Canonical case: UK ``bwkmt_bfamt`` Working Tax
#:   Credit / Child Tax Credit — tax credits ended 5 April 2025 (GOV.UK
#:   www.gov.uk/tax-credits-have-ended), and UKMOD UK_2026 returns
#:   ``bwkmt_s``/``bfamt_s`` = 0 across a synthetic earnings/hours/labour-status
#:   sweep with take-up pinned and the UC transition disabled (probe:
#:   scripts/probe_uk_repealed_and_missing_input.py).
#: - ``oracle_models_nonstatutory_amount``: the oracle computes a payable ``_s``
#:   output, but the MONETARY value it pays has no basis in statute or regulation
#:   for Axiom (which encodes statutory monetary rules) to compare — the amount is
#:   (a) DISCRETIONARY (legislation confers a power to pay with no formula, rate,
#:   or cap), (b) an ADMINISTRATIVE figure set outside legislation (e.g. an
#:   intergovernmental "national minimum" that each authority may vary), or (c) a
#:   modelled COST-EQUIVALENT the oracle imputes for an IN-KIND entitlement that
#:   pays no cash. The oracle models the value as if formulaic, but encoding that
#:   figure as a statutory rule would misrepresent a non-statutory instrument, and
#:   the corpus carries no source to ground it. Distinct from
#:   ``extension_not_available`` (there the compute content is simply absent from
#:   the public release) and ``oracle_models_repealed_law`` (a real current/past
#:   statutory instrument, just repealed). Requires a ``note`` recording the
#:   governing instrument and why its amount is non-statutory. Canonical UK cases:
#:   ``bhosc01`` Scottish Discretionary Housing Payments — SI 2001/1167 reg 2(2)
#:   gives the authority a pure discretion "as to whether or not to make
#:   discretionary housing payments ... and as to the amount", no statutory
#:   formula (the 14%/25% UKMOD applies are the HB/UC size-criteria percentages,
#:   already covered on the UC side); ``bched02`` Scottish School Clothing Grant —
#:   the "national minimum" (£120 primary / £150 secondary) is a Scottish
#:   Government-COSLA administrative agreement, not fixed in any SSI, and each of
#:   the 32 councils sets its own amount (Education (Scotland) Act 1980 s.54
#:   confers the clothing duty with no figure); ``bched01`` Scottish Free School
#:   Meals — s.53 of the 1980 Act imposes an IN-KIND duty to "provide ... a school
#:   lunch, free of charge" with no monetary amount, so UKMOD's ``bched01_s`` is a
#:   modelled per-meal cost-equivalent, not a legislated cash benefit (the
#:   eligibility thresholds are statutory but no award amount is).
EXCLUSION_REASONS: tuple[str, ...] = (
    "input_carrying",
    "technical",
    "takeup_adjustment",
    "not_a_policy",
    "unobservable_boundary",
    "extension_not_available",
    "oracle_dataset_lacks_input",
    "oracle_models_repealed_law",
    "oracle_models_nonstatutory_amount",
)

ExclusionReason = Literal[
    "input_carrying",
    "technical",
    "takeup_adjustment",
    "not_a_policy",
    "unobservable_boundary",
    "extension_not_available",
    "oracle_dataset_lacks_input",
    "oracle_models_repealed_law",
    "oracle_models_nonstatutory_amount",
]

#: Comparability of an *in-scope* policy's output surface — how faithfully a
#: comparison can bind Axiom's statutory computation to the oracle's output.
#: The UK PolicyEngine coverage matrix (docs/uk-coverage-matrix.md) shows the
#: oracle's variable tree has more than one kind of "simulated": a rate table
#: applied over a frozen input category is only comparable on *rates*, and a
#: reported-ceiling passthrough never computes the statutory maximum. Carrying
#: the kind on the row means the scoreboard can hold rate-only and ceiling-only
#: surfaces to the right standard instead of scoring them as if they were full
#: rule engines.
#:
#: - ``full``: the oracle computes entitlement/liability from parameters and
#:   circumstances (a ``def formula`` rules engine, or a EUROMOD ``BenCalc``
#:   pipeline). Full statutory comparison. The default.
#: - ``rate_only``: the oracle applies a parameterised rate table but the
#:   award category/eligibility is a frozen input (PE-UK PIP/DLA/AA
#:   ``*_category``). Comparable on rate reforms, not eligibility rules.
#: - ``ceiling_only``: the oracle reads a ``*_reported`` input amount and
#:   applies only a capital/tariff screen or flat multiply, never computing the
#:   maximum from statute (PE-UK ``jsa_income``/``esa_income``/``sda`` …).
COMPARABILITY_KINDS: tuple[str, ...] = ("full", "rate_only", "ceiling_only")

#: Backends a universe file may be generated from (stamped in the header).
UNIVERSE_BACKENDS: tuple[str, ...] = (
    "ukmod",
    "euromod",
    "policyengine",
    "yale-tariff",
)


@dataclass(frozen=True)
class UniversePolicy:
    """One universe row: a policy the oracle simulates, plus its scope decision.

    ``id``, ``oracle_policy_name`` and ``output_vars`` are *generated facts*
    read from the oracle model — the generator overwrites them and ``--check``
    fails if the committed value drifts. ``in_scope``, ``exclusion_reason``,
    ``suite`` and ``note`` are *committed decisions* the generator preserves
    across regenerations (a decision the model can't make for us), validated for
    internal consistency.
    """

    id: str
    oracle_policy_name: str
    output_vars: tuple[str, ...]
    in_scope: bool
    exclusion_reason: str | None = None
    suite: str | None = None
    note: str | None = None
    #: How faithfully the oracle's output surface can be compared for an in-scope
    #: policy (see :data:`COMPARABILITY_KINDS`). Defaults to ``full``; the
    #: policyengine backend sets ``rate_only``/``ceiling_only`` for the PE-UK
    #: rate-from-frozen-input and reported-ceiling kinds. A committed decision.
    comparability: str = "full"
    #: Non-scored provenance carried for review: the policy's model ``type``
    #: (ben/tax/sic/inc/def) and switch state. Facts, regenerated from the model.
    oracle_policy_type: str | None = None
    #: Output variables the policy writes that are NOT in the model's variable
    #: registry (queryable set) — the evidence behind an ``unobservable_boundary``
    #: or ``technical`` classification. A fact, regenerated from the model.
    internal_only_vars: tuple[str, ...] = field(default_factory=tuple)

    def validate(self) -> list[str]:
        """Return a list of consistency problems (empty means valid)."""
        problems: list[str] = []
        if not self.id:
            problems.append("row is missing an id")
        if not self.oracle_policy_name:
            problems.append(f"{self.id or '<no id>'}: missing oracle_policy_name")
        if self.in_scope:
            if self.exclusion_reason is not None:
                problems.append(
                    f"{self.id}: in_scope rows must not carry an exclusion_reason "
                    f"(got {self.exclusion_reason!r})"
                )
            # `suite: null` on an in-scope row is a valid, honest state: the
            # policy IS in the conformance denominator but has no Axiom suite
            # assigned yet, so the scoreboard scores it as uncovered. Naming a
            # suite asserts intent; the scoreboard still decides `covered` by
            # whether that suite has a live matching report.
            if not self.output_vars:
                problems.append(
                    f"{self.id}: in_scope rows must have at least one queryable "
                    "output_var to compare against"
                )
            if self.comparability not in COMPARABILITY_KINDS:
                problems.append(
                    f"{self.id}: comparability {self.comparability!r} is not one "
                    f"of {', '.join(COMPARABILITY_KINDS)}"
                )
        else:
            if not self.exclusion_reason:
                problems.append(
                    f"{self.id}: out-of-scope rows REQUIRE an exclusion_reason "
                    f"(one of {', '.join(EXCLUSION_REASONS)})"
                )
            elif self.exclusion_reason not in EXCLUSION_REASONS:
                problems.append(
                    f"{self.id}: exclusion_reason {self.exclusion_reason!r} is not "
                    f"one of {', '.join(EXCLUSION_REASONS)}"
                )
            if self.exclusion_reason == "unobservable_boundary" and not self.note:
                problems.append(
                    f"{self.id}: unobservable_boundary requires a `note` citing "
                    "the model documentation and the internal variables involved"
                )
            if self.exclusion_reason == "extension_not_available" and not self.note:
                problems.append(
                    f"{self.id}: extension_not_available requires a `note` "
                    "recording the verdict (which extension/microdata is absent)"
                )
            if self.exclusion_reason == "oracle_dataset_lacks_input" and not self.note:
                problems.append(
                    f"{self.id}: oracle_dataset_lacks_input requires a `note` naming "
                    "the absent activating input and the probe evidence pointer"
                )
            if self.exclusion_reason == "oracle_models_repealed_law" and not self.note:
                problems.append(
                    f"{self.id}: oracle_models_repealed_law requires a `note` "
                    "recording the repeal citation and probe evidence pointer"
                )
            if (
                self.exclusion_reason == "oracle_models_nonstatutory_amount"
                and not self.note
            ):
                problems.append(
                    f"{self.id}: oracle_models_nonstatutory_amount requires a "
                    "`note` recording the governing instrument and why its "
                    "amount is non-statutory"
                )
            # comparability is an in-scope concept; an excluded row must not carry
            # a non-default value (it would be meaningless).
            if self.comparability != "full":
                problems.append(
                    f"{self.id}: out-of-scope rows must not set comparability "
                    f"(got {self.comparability!r})"
                )
            if self.suite is not None:
                problems.append(
                    f"{self.id}: out-of-scope rows must not name a `suite` "
                    f"(got {self.suite!r}) — an excluded policy is not covered"
                )
        return problems

    def to_row(self) -> dict:
        """Serialise to the ordered mapping written into the universe YAML."""
        row: dict = {
            "id": self.id,
            "oracle_policy_name": self.oracle_policy_name,
            "oracle_policy_type": self.oracle_policy_type,
            "output_vars": list(self.output_vars),
            "in_scope": self.in_scope,
        }
        if self.internal_only_vars:
            row["internal_only_vars"] = list(self.internal_only_vars)
        if self.in_scope:
            row["suite"] = self.suite
            # Only emit comparability when it departs from the default so the
            # UKMOD/EUROMOD full-comparison rows stay uncluttered.
            if self.comparability != "full":
                row["comparability"] = self.comparability
        else:
            row["exclusion_reason"] = self.exclusion_reason
        if self.note:
            row["note"] = self.note
        return row
