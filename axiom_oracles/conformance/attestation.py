"""Execution attestation — the evidence that a comparison suite actually RAN.

The conformance predicate reads a report's mismatch signals. Before this module
it never asked whether the report was the product of a *run*: a skipped or
errored suite emits an artifact with ``case_count: 0``, empty ``comparisons``
and an ``errors`` row (``scripts/run_comparison.py``'s graceful-skip path), and
``_disposition_signals`` scored that empty artifact as ``(0, 0, 0, 0)`` — zero
unexplained, zero Axiom-attributed, therefore conformant. Coverage was decided
by suite-name *registration*, not by evidence the named suite produced
comparisons for the outputs the universe registers (axiom-oracles#355).

An **execution attestation** is that missing evidence, in two layers:

1. **Execution** (blocking, no exceptions). The report must show a real run:
   ``executed`` not explicitly false, strictly positive cases AND comparisons,
   zero errors at every level the schema records them, an engine pair that
   contains Axiom *and* the oracle the universe declares, and — when the
   artifact records one — an oracle identity that does not contradict the
   universe's declared *model* (see :func:`_identity_problems`; the *release* is
   recorded rather than blocked). A report failing any of these is INELIGIBLE —
   the policy it would cover scores as **uncovered**, not as
   covered-with-zero-unexplained.

2. **Output binding** (blocking, waivable only through the committed
   :mod:`conformance/attestation_waivers.yaml`). The comparisons must be
   *about the policy*: at least one of the universe row's registered
   ``output_vars`` must carry positive comparison evidence in the covering
   report. A suite that ran perfectly against some other surface does not
   attest the policy it is registered under.

Both layers read only what the artifact itself carries. ``attested_outputs``
comes, in order of authority, from

* a runner-stamped ``report["attestation"]`` block (schema
  :data:`EXECUTION_ATTESTATION_SCHEMA`) — the producer recording which oracle
  variables it queried and how many comparisons each carried;
* the report's ``engines`` map when it is written in the engine→variable shape
  (``{"axiom": "...", "policyengine": "al_income_tax_before_refundable_credits"}``);
* the concept→engine-target bindings the comparison machinery itself uses —
  ``axiom_oracles/config/concept_mappings.yaml`` (``ProgramMapping``) and the
  PolicyEngine oracle registry (``bridges/mappings/*.yaml``) — applied to the
  report's aggregates that carry a positive ``comparison_count``.

The third source is a deduction, so it is tracked as such:
:attr:`ExecutionAttestation.outputs_complete` is true only when EVERY
positive-comparison aggregate resolved to a named oracle variable. When the
recording is incomplete, "none of the registered outputs appear" means *the
artifact cannot show the binding*, never *the suite compared the wrong thing* —
a distinction the waiver reasons keep visible instead of collapsing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

#: Schema id stamped into a runner-produced ``report["attestation"]`` block.
EXECUTION_ATTESTATION_SCHEMA = "axiom_oracles.execution_attestation.v1"

#: The engine name a report records for each universe oracle backend. UKMOD and
#: EUROMOD are one runtime (``axiom_oracles.adapters.euromod``) and both write
#: ``euromod`` into the report's engine pair.
BACKEND_ENGINE_NAMES: dict[str, str] = {
    "euromod": "euromod",
    "ukmod": "euromod",
    "policyengine": "policyengine",
}

#: Axiom must be a party to any comparison that can attest Axiom conformance —
#: a taxcalc-vs-PolicyEngine cross-check is a real run that verifies nothing
#: about the encoding.
AXIOM_ENGINE = "axiom"


@dataclass(frozen=True)
class ExecutionAttestation:
    """Machine-checked evidence that one report is the product of a real run."""

    suite: str
    #: The oracle engine the universe declares (report must have run against it).
    oracle_engine: str
    #: True when a runner stamped the attestation rather than it being derived.
    stamped: bool
    executed: bool
    case_count: int
    comparison_count: int
    error_count: int
    engines: tuple[str, ...] = ()
    #: The oracle release the report records, when it differs from the release
    #: the universe pins (None when they agree or the artifact is silent). NOT
    #: blocking — see :func:`_identity_problems`.
    oracle_release_drift: str | None = None
    #: Oracle output variables carrying positive comparison evidence.
    attested_outputs: frozenset[str] = frozenset()
    #: True when EVERY positive-comparison surface in the report resolved to a
    #: named oracle variable — only then is "output X was not compared" a
    #: statement about the run rather than about the artifact's recording.
    outputs_complete: bool = False
    #: Why this report cannot attest execution (empty ⇒ eligible).
    problems: tuple[str, ...] = field(default_factory=tuple)

    @property
    def eligible(self) -> bool:
        """True when the report attests a real run against the declared oracle."""
        return not self.problems

    @property
    def outputs_recorded(self) -> bool:
        """True when the artifact names ANY oracle variable it compared."""
        return bool(self.attested_outputs)

    def binds(self, output_vars: tuple[str, ...] | list[str]) -> bool:
        """True when at least one registered output carries comparison evidence."""
        return bool(self.attested_outputs & set(output_vars))

    def binding_gap(self, output_vars: tuple[str, ...] | list[str]) -> str | None:
        """The waiver reason a covered policy needs, or None when it binds.

        Two distinct states, deliberately not merged:

        * ``compared_surface_differs`` — the report records every surface it
          compared and none of them is a registered output. The suite ran
          against a different surface than the universe registers for this
          policy (canonical case: a state income-tax grid comparing PolicyEngine's
          ``*_before_refundable_credits`` against a row registering the final
          ``*_income_tax``).
        * ``oracle_variable_not_recorded`` — the artifact does not record which
          oracle variable each compared concept was bound to, so the binding
          cannot be machine-verified either way. Regenerating the report with a
          stamped attestation resolves it.
        """
        if self.binds(output_vars):
            return None
        if self.outputs_complete:
            return "compared_surface_differs"
        return "oracle_variable_not_recorded"


class OracleTargetResolver:
    """Resolve a report concept id to the oracle variable(s) it compares.

    Uses the same bindings the comparison machinery uses at run time, so this is
    a deduction from the run's own configuration rather than a re-guess:
    ``ProgramMapping.target_for_engine`` (concept_mappings.yaml) and the
    PolicyEngine oracle registry keyed by legal id (bridges/mappings/*.yaml).
    """

    def __init__(
        self,
        concept_targets: dict[str, dict[str, frozenset[str]]] | None = None,
        policyengine_registry=None,
    ) -> None:
        self._concept_targets = concept_targets or {}
        self._policyengine_registry = policyengine_registry

    def resolve(self, concept_id: str, engine: str) -> frozenset[str]:
        names = self._concept_targets.get(concept_id, {}).get(engine, frozenset())
        if engine == "policyengine" and self._policyengine_registry is not None:
            mapping = self._policyengine_registry.mapping_for_legal_id(concept_id)
            if mapping is not None and mapping.policyengine_variable:
                names = names | {mapping.policyengine_variable}
        return names


@lru_cache(maxsize=1)
def default_resolver() -> OracleTargetResolver:
    """The committed concept→oracle-variable bindings, parsed once per process."""
    from axiom_oracles.comparison.mappings import load_program_mappings

    concept_targets: dict[str, dict[str, frozenset[str]]] = {}
    for mapping in load_program_mappings():
        per_engine: dict[str, frozenset[str]] = {}
        for engine in set(mapping.targets) | {"policyengine", "axiom"}:
            names = _as_names(mapping.target_for_engine(engine))
            if names:
                per_engine[engine] = names
        if per_engine:
            concept_targets[mapping.concept_id] = per_engine

    try:
        from axiom_oracles.bridges.registry import load_policyengine_registry

        registry = load_policyengine_registry()
    except Exception:  # pragma: no cover - packaged data; never fatal for a join
        registry = None

    return OracleTargetResolver(concept_targets, registry)


def attest(
    report: dict,
    *,
    oracle,
    resolver: OracleTargetResolver | None = None,
) -> ExecutionAttestation:
    """Build the execution attestation for one committed comparison report.

    ``oracle`` is the universe's :class:`OracleIdentity` (or, for a caller that
    only knows the backend, its name as a string).
    """
    resolver = resolver if resolver is not None else default_resolver()
    suite = str(report.get("suite") or "<unnamed>")
    oracle_backend = oracle if isinstance(oracle, str) else oracle.backend
    oracle_engine = BACKEND_ENGINE_NAMES.get(oracle_backend, oracle_backend)
    summary = report.get("summary") or {}
    stamp = report.get("attestation")
    stamped = isinstance(stamp, dict)

    case_count = _int(report.get("case_count"))
    comparison_count = _int(summary.get("comparison_count"))
    error_count = _error_count(report, summary)
    engines = _engine_names(report)

    problems: list[str] = []

    executed = True
    if stamped:
        problems.extend(_stamp_problems(stamp, case_count, comparison_count, error_count))
        if stamp.get("executed") is False:
            executed = False
            problems.append(
                f"{suite}: the run stamped `executed: false`"
                + (f" ({stamp.get('skip_reason')})" if stamp.get("skip_reason") else "")
                + " — a skipped run cannot cover an in-scope policy"
            )

    if case_count <= 0:
        executed = False
        problems.append(
            f"{suite}: report carries {case_count} cases — a suite that produced "
            "no case executed nothing"
        )
    if comparison_count <= 0:
        executed = False
        problems.append(
            f"{suite}: report carries {comparison_count} comparisons — a suite "
            "that compared nothing verifies nothing"
        )
    if error_count > 0:
        problems.append(
            f"{suite}: report carries {error_count} engine error(s) — an errored "
            "run is not evidence of conformance"
        )

    if AXIOM_ENGINE not in engines:
        problems.append(
            f"{suite}: engines {sorted(engines)} do not include {AXIOM_ENGINE!r} — "
            "a comparison Axiom is not party to cannot attest Axiom conformance"
        )
    if oracle_engine not in engines:
        problems.append(
            f"{suite}: engines {sorted(engines)} do not include the universe's "
            f"declared oracle {oracle_engine!r}"
        )
    if len(engines) < 2:
        problems.append(
            f"{suite}: engines {sorted(engines)} name fewer than two distinct "
            "engines — an engine compared against itself verifies nothing"
        )

    release_drift = None
    if not isinstance(oracle, str):
        identity_problems, release_drift = _identity_problems(report, oracle, suite)
        problems.extend(identity_problems)

    attested_outputs, outputs_complete = _attested_outputs(
        report, oracle_engine, resolver, stamp if stamped else None
    )

    return ExecutionAttestation(
        suite=suite,
        oracle_engine=oracle_engine,
        stamped=stamped,
        executed=executed,
        case_count=case_count,
        comparison_count=comparison_count,
        error_count=error_count,
        engines=tuple(sorted(engines)),
        oracle_release_drift=release_drift,
        attested_outputs=attested_outputs,
        outputs_complete=outputs_complete,
        problems=tuple(problems),
    )


def _identity_problems(report: dict, oracle, suite: str) -> tuple[list[str], str | None]:
    """Check the recorded oracle identity against the universe's declared one.

    ``provenance.oracle`` is the run's own record of WHICH oracle it drove —
    ``{euromod_release, euromod_system, euromod_country}`` for the EUROMOD
    platform, ``{policyengine_<cc>: <version>}`` for PolicyEngine. Split in two
    on purpose:

    * **Blocking** — the *model* identity: a different policy system, a
      different country, or a different country's PolicyEngine package. A
      ``UK_2026`` report cannot attest a ``BE_2025`` universe however clean its
      numbers are, and that substitution is the one an identity check must make
      impossible.
    * **Recorded, not blocking** — the *release*. Reports legitimately lag a
      universe re-pin (a PE-US bump lands long before every population suite is
      rerun), so a release difference is published as
      :attr:`ExecutionAttestation.oracle_release_drift` and counted on the
      scoreboard rather than retracting coverage. Making it blocking is a
      scope decision about what a badge claims, not a bug fix.

    Silence is not evidence: a report with no ``provenance.oracle`` records no
    identity and neither passes nor fails this check — the engine-name check
    above still applies to it.
    """
    provenance = (report.get("provenance") or {}).get("oracle")
    if not isinstance(provenance, dict) or not provenance:
        return [], None

    problems: list[str] = []
    drift: str | None = None

    if oracle.backend in ("euromod", "ukmod"):
        system = provenance.get("euromod_system")
        country = provenance.get("euromod_country")
        if system and system != oracle.system:
            problems.append(
                f"{suite}: report ran EUROMOD system {system!r}, but the universe "
                f"declares {oracle.system!r}"
            )
        if country and country != oracle.country:
            problems.append(
                f"{suite}: report ran EUROMOD country {country!r}, but the "
                f"universe declares {oracle.country!r}"
            )
        release = provenance.get("euromod_release")
        # The BE model root is EUROMOD_J2.0/EUROMOD_RELEASES_J2.0+, so the runner
        # records "J2.0+" for the release the universe pins as "J2.0" — one
        # release, two path conventions, not drift.
        if release and release.rstrip("+") != str(oracle.release).rstrip("+"):
            drift = str(release)
    elif oracle.backend == "policyengine":
        # `policyengine-uk` → the `policyengine_uk` provenance key.
        expected_key = oracle.model.replace("-", "_")
        recorded = {
            key: value
            for key, value in provenance.items()
            if key.startswith("policyengine_")
            and key not in ("policyengine_package", "policyengine_core")
        }
        if recorded and expected_key not in recorded:
            problems.append(
                f"{suite}: report records {sorted(recorded)} but the universe "
                f"declares {oracle.model!r} — a different country's PolicyEngine "
                "package cannot attest this oracle"
            )
        version = recorded.get(expected_key)
        if version and str(version) != str(oracle.release):
            drift = str(version)

    return problems, drift


# ---------------------------------------------------------------------------
# Evidence extraction
# ---------------------------------------------------------------------------


def _stamp_problems(
    stamp: dict, case_count: int, comparison_count: int, error_count: int
) -> list[str]:
    """A stamp may not claim more than the report body shows.

    The stamp is producer-written, so on its own it is an assertion. Requiring
    it to agree with the body's independently-counted cases/comparisons/errors
    means a lane cannot stamp `executed: true, comparisons: 5000` over an empty
    artifact and have it believed.
    """
    problems: list[str] = []
    schema = stamp.get("schema_version") or stamp.get("schema")
    if schema and schema != EXECUTION_ATTESTATION_SCHEMA:
        problems.append(
            f"attestation schema {schema!r} is not {EXECUTION_ATTESTATION_SCHEMA!r}"
        )
    for key, body_value in (
        ("case_count", case_count),
        ("comparison_count", comparison_count),
        ("error_count", error_count),
    ):
        if key not in stamp:
            continue
        if _int(stamp.get(key)) != body_value:
            problems.append(
                f"attestation {key}={stamp.get(key)!r} contradicts the report "
                f"body ({body_value}) — the stamp must be produced by the run "
                "that wrote the report"
            )
    return problems


def _attested_outputs(
    report: dict,
    oracle_engine: str,
    resolver: OracleTargetResolver,
    stamp: dict | None,
) -> tuple[frozenset[str], bool]:
    """Oracle variables with positive comparison evidence + recording completeness."""
    if stamp is not None and stamp.get("outputs") is not None:
        names: set[str] = set()
        for entry in stamp.get("outputs") or []:
            if not isinstance(entry, dict):
                continue
            if entry.get("engine") not in (None, oracle_engine):
                continue
            if _int(entry.get("comparisons")) <= 0:
                continue
            variable = entry.get("variable")
            if isinstance(variable, str) and variable:
                names.add(variable)
            elif isinstance(variable, list):
                names.update(str(item) for item in variable if item)
        # A stamp enumerates every output the run compared, so the recording is
        # complete by construction — that is what stamping means.
        return frozenset(names), True

    names = set(_engines_map_variables(report, oracle_engine))
    resolved_every_surface = True
    saw_surface = False
    for aggregate in report.get("aggregates") or []:
        if not isinstance(aggregate, dict):
            continue
        if _int(aggregate.get("comparison_count")) <= 0:
            continue
        concept_id = aggregate.get("concept")
        if not isinstance(concept_id, str) or not concept_id:
            resolved_every_surface = False
            continue
        saw_surface = True
        resolved = resolver.resolve(concept_id, oracle_engine)
        if resolved:
            names.update(resolved)
        else:
            resolved_every_surface = False
    outputs_complete = bool(names) and resolved_every_surface
    if not saw_surface and not names:
        outputs_complete = False
    return frozenset(names), outputs_complete


def _engines_map_variables(report: dict, engine: str) -> frozenset[str]:
    """Oracle variables named by the engine→variable ``engines`` shape.

    Reports come in two ``engines`` shapes: the role pair
    ``{"left": "axiom", "right": "policyengine"}`` (names only) and the grid
    shape ``{"axiom": "<concept>", "policyengine": "<variable>"}`` where the
    value IS the compared variable. Only the latter carries output evidence.
    """
    engines = report.get("engines")
    if not isinstance(engines, dict) or set(engines) <= {"left", "right"}:
        return frozenset()
    value = engines.get(engine)
    return _as_names(value)


def _engine_names(report: dict) -> set[str]:
    engines = report.get("engines")
    if not isinstance(engines, dict):
        return set()
    if set(engines) <= {"left", "right"}:
        return {str(value) for value in engines.values() if value}
    return {str(key) for key in engines}


def _error_count(report: dict, summary: dict) -> int:
    """Errors from every place the v2/v2.1 schema records them.

    ``summary.error_count`` is absent from some generator-written reports, and a
    per-case ``left_errors``/``right_errors`` row never reaches the summary at
    all, so all three are counted.
    """
    total = max(_int(summary.get("error_count")), len(report.get("errors") or []))
    by_engine = summary.get("errors_by_engine")
    if isinstance(by_engine, list):
        total = max(total, sum(_int(row.get("count")) for row in by_engine if isinstance(row, dict)))
    elif isinstance(by_engine, dict):
        total = max(total, sum(_int(value) for value in by_engine.values()))
    case_errors = sum(
        len(case.get("left_errors") or []) + len(case.get("right_errors") or [])
        for case in (report.get("cases") or [])
        if isinstance(case, dict)
    )
    return max(total, case_errors)


def _as_names(value: object) -> frozenset[str]:
    if isinstance(value, str):
        # The devolved-tax grids record a comma-joined pair in one engines slot.
        return frozenset(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, (list, tuple, set)):
        return frozenset(str(item) for item in value if item)
    return frozenset()


def _int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
