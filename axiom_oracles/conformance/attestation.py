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
   strictly positive cases AND comparisons,
   zero errors at every level the schema records them, an engine pair that
   contains Axiom *and* the oracle the universe declares, and — when the
   artifact records one — an oracle identity that does not contradict the
   universe's declared *model* (see :func:`_identity_problems`; the *release* is
   recorded rather than blocked). A report failing any of these is INELIGIBLE —
   the policy it would cover scores as **uncovered**, not as
   covered-with-zero-unexplained.

2. **Output binding** (blocking). The comparisons must be
   *about the policy*: at least one of the universe row's registered
   ``output_vars`` must carry a returned same-case pair in the covering
   report. A suite that ran perfectly against some other surface does not
   attest the policy it is registered under.

Every binding path calls :func:`observed_output_value`. Stamps, engine maps,
producer configuration and concept mappings supply candidate output names;
none is returned-value evidence. Coverage requires finite, non-null returned
comparison values from both engines in one real case, identified by output,
with no contradictory missing/error/skipped evidence. Stamps are optional and
must agree with recorded data when present. Returned sum members require their
own scored comparison identity and retained verdict and residual; a summed
scalar never proves its members.

Producer and concept bindings are deductions, so they are tracked as such:
:attr:`ExecutionAttestation.outputs_complete` is true only when EVERY
positive-comparison aggregate resolved to a named oracle variable. When the
recording is incomplete, "none of the registered outputs appear" means *the
artifact cannot show the binding*, never *the suite compared the wrong thing* —
a distinction the waiver reasons keep visible instead of collapsing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from .observations import (
    OutputEvidence, native_fiit_report, native_lbtt_pairs, observed_output_value, returned_output_rows,
)

#: Schema id stamped into a runner-produced ``report["attestation"]`` block.
EXECUTION_ATTESTATION_SCHEMA = "axiom_oracles.execution_attestation.v1"

#: The engine name a report records for each universe oracle backend. UKMOD and
#: EUROMOD are one runtime (``axiom_oracles.adapters.euromod``) and both write
#: ``euromod`` into the report's engine pair.
BACKEND_ENGINE_NAMES: dict[str, str] = {
    "euromod": "euromod",
    "ukmod": "euromod",
    "policyengine": "policyengine",
    "yale-tariff": "yale_statutory",
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
        """The recording gap, or None when the registered output has a pair.

        Two distinct states, deliberately not merged:

        * ``compared_surface_differs`` — the report records every surface it
          compared and none of them is a registered output. The suite ran
          against a different surface than the universe registers for this
          policy (canonical case: a state income-tax grid comparing PolicyEngine's
          ``*_before_refundable_credits`` against a row registering the final
          ``*_income_tax``).
        * ``oracle_variable_not_recorded`` — the artifact does not record which
          oracle variable each compared concept was bound to, so the binding
          cannot be machine-verified either way. A rerun retaining both returned
          values and their native bindings resolves it.
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
        output_types: dict[tuple[str, str], type] | None = None,
    ) -> None:
        self._concept_targets = concept_targets or {}
        self._policyengine_registry = policyengine_registry
        self._output_types = output_types or {}

    def resolve(self, concept_id: str, engine: str) -> frozenset[str]:
        names = self._concept_targets.get(concept_id, {}).get(engine, frozenset())
        if engine == "policyengine" and self._policyengine_registry is not None:
            mapping = self._policyengine_registry.mapping_for_legal_id(concept_id)
            if mapping is not None and mapping.policyengine_variable:
                names = names | {mapping.policyengine_variable}
        return names


    def output_type(self, output: str, engine: str) -> type | None:
        """Authoritative declared type; report metadata cannot register a type."""
        return self._output_types.get((engine, output))


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
    value_evidence = OutputEvidence(report)

    case_count = _int(report.get("case_count"))
    comparison_count = _int(summary.get("comparison_count"))
    error_count = _error_count(report, summary)
    engines = _engine_names(report)

    problems: list[str] = []

    executed = True
    if stamped:
        problems.extend(_stamp_problems(stamp, report, case_count, comparison_count, error_count, resolver, value_evidence))
        if stamp.get("executed", True) is not True:
            executed = False
            claim = "false" if stamp.get("executed") is False else repr(stamp.get("executed"))
            problems.append(
                f"{suite}: the run stamped `executed: {claim}` rather than `executed: true`"
                + (f" ({stamp.get('skip_reason')})" if stamp.get("skip_reason") else "")
                + " — a skipped or unconfirmed run cannot cover an in-scope policy"
            )
    elif stamp is not None:
        executed = False
        problems.append(f"{suite}: attestation must be an object when present")

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
        report, oracle_engine, resolver, stamp if stamped else None, value_evidence
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
    stamp: dict, report: dict, case_count: int, comparison_count: int, error_count: int,
    resolver: OracleTargetResolver,
    value_evidence: OutputEvidence,
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
    engines = _engine_names(report)
    if "engines" in stamp and _engine_names(stamp) != engines:
        problems.append("attestation engines contradict the report body")

    # Each variable may be one component of a summed concept, so its observed
    # count may be smaller than the aggregate, but cannot exceed that evidence.
    aggregate_counts = {
        row.get("concept"): _int(row.get("comparison_count"))
        for row in report.get("aggregates") or []
        if isinstance(row, dict) and isinstance(row.get("concept"), str)
    }
    outputs = stamp.get("outputs")
    if outputs is None:
        return problems
    if not isinstance(outputs, list):
        return problems + ["attestation outputs must be a list"]
    seen: set[tuple[str, str, str]] = set()
    for entry in outputs:
        if not isinstance(entry, dict):
            problems.append("attestation output must name a concept, engine and variable")
            continue
        concept = entry.get("concept")
        engine = entry.get("engine")
        variable = entry.get("variable")
        if not all(isinstance(value, str) and value for value in (concept, engine, variable)):
            problems.append("attestation output must explicitly name its concept, engine and variable")
            continue
        if engine not in engines:
            problems.append(f"attestation output engine {engine!r} is absent from the report body")
        count = entry.get("comparisons")
        observed = _observed_cases(report, engine, concept, variable, resolver, value_evidence)
        bound = min(aggregate_counts.get(concept, 0), comparison_count, len(observed))
        if not isinstance(count, int) or isinstance(count, bool) or not 0 < count <= bound:
            problems.append(
                f"attestation output {concept!r}/{variable!r} comparisons={count!r} "
                f"contradicts positive report body evidence ({bound})"
            )
        key = (concept, engine, variable)
        if key in seen:
            problems.append(f"attestation repeats output evidence for {key!r}")
        seen.add(key)
    return problems


def _targets(report, engine, concept, resolver, value_evidence):
    if native_fiit_report(report):
        from .fiit import native_fiit_pairs

        pairs = native_fiit_pairs(report)
        targets = frozenset(
            output if engine == "policyengine" else axiom
            for (native_concept, output), axiom in pairs.items()
            if native_concept == concept and engine in {"axiom", "policyengine"}
        )
        # A native ledger identifies the exact comparison, but cannot override
        # a contradictory target explicitly recorded elsewhere in its report.
        bindings = (report.get("output_bindings") or {}).get(concept, {})
        if isinstance(bindings, dict) and engine in bindings:
            targets &= _as_names(bindings[engine])
        recorded = (report.get("engine_bindings") or {}).get(engine)
        if isinstance(recorded, dict) and ("outputs" in recorded or "output" in recorded):
            targets &= _as_names(recorded.get("outputs", recorded.get("output")))
        declared = _engines_map_variables(report, engine)
        engines = report.get("engines")
        if isinstance(engines, dict) and engine in engines:
            targets &= declared
        return targets
    lbtt_pairs = native_lbtt_pairs(report)
    if lbtt_pairs is not None:
        spec = lbtt_pairs.get(concept)
        return frozenset({spec[0 if engine == "axiom" else 1]}) if spec and engine in {"axiom", "policyengine"} else frozenset()
    if report.get("suite") == "us-tariff-panel" and engine in {"axiom", "yale_statutory"}:
        from axiom_oracles.suites.us_tariff_panel import AUTHORITY_SLOTS

        slot = AUTHORITY_SLOTS.get(concept)
        targets = frozenset(slot[1]) if slot and slot[0] is not None else frozenset()
        bindings = (report.get("output_bindings") or {}).get(concept, {})
        declarations = []
        if isinstance(bindings, dict) and engine in bindings:
            declarations.append(bindings[engine])
        recorded = (report.get("engine_bindings") or {}).get(engine)
        if isinstance(recorded, dict) and ("outputs" in recorded or "output" in recorded):
            declarations.append(recorded.get("outputs", recorded.get("output")))
        for declaration in declarations:
            names = _as_names(declaration)
            if engine == "axiom" and slot and slot[0] in names:
                # Native query URIs and their recorded slot column names
                # identify the same returned authority value.
                names |= frozenset(slot[1])
            targets &= names
        return targets
    declarations = []
    bindings = (report.get("output_bindings") or {}).get(concept, {})
    if isinstance(bindings, dict) and engine in bindings:
        declarations.append(_as_names(bindings[engine]))
    native_targets = _efrs_targets(report, engine, concept)
    if native_targets is not None:
        declarations.append(native_targets)
    bindings = (report.get("engine_bindings") or {}).get(engine)
    global_binding = (report.get("concept") in {None, concept}
                      or report.get("concept") not in value_evidence.compared_concepts)
    if global_binding and isinstance(bindings, dict) and ("outputs" in bindings or "output" in bindings):
        # These are the custom producer's recorded comparison targets;
        # diagnostic_outputs and current generic mappings cannot replace them.
        declarations.append(_as_names(bindings.get("outputs", bindings.get("output"))))
    declared = _engines_map_variables(report, engine) if global_binding else frozenset()
    engines = report.get("engines") or {}
    if global_binding and isinstance(engines, dict) and engine in engines:
        declarations.append(declared)
    if declarations:
        # Per-concept bindings cannot hide a contradictory native declaration
        # or engine heading. Broad headings may contain several scalar targets.
        # Keep the comparison's full identity: narrowing a sum to one returned
        # member must not turn it into an independently compared scalar.
        targets = declarations[0]
        if isinstance((report.get("output_bindings") or {}).get(concept), dict):
            # A primary declaration cannot discard the comparison's returned
            # members. Current resolver names supplement invalid/missing ledger
            # rows without replacing a native producer's different binding.
            key = (engine, concept)
            recorded = (value_evidence.clean_ledger_targets.get(key, set())
                        | (value_evidence.ledger_targets.get(key, set()) & resolver.resolve(concept, engine)))
            if not recorded <= targets:
                return frozenset()
        return targets if all(targets <= names for names in declarations[1:]) else frozenset()
    resolved = resolver.resolve(concept, engine)
    if resolved:
        return resolved
    recorded = {
        row["variable"] for row in report.get("observed_outputs") or []
        if isinstance(row, dict) and row.get("engine") == engine
        and row.get("concept") == concept and isinstance(row.get("variable"), str)
    }
    if recorded:
        return frozenset(recorded)
    # Stamps name candidates; they cannot identify a legacy value's comparison
    # target. Native per-output ledgers carry their own returned-value binding.
    return frozenset()


def _efrs_targets(report, engine, concept):
    """Resolve an explicitly recorded native output, including historical rows."""
    if report.get("suite") != "uk-tax-benefits-efrs" or engine not in {"axiom", "policyengine"}:
        return None
    from axiom_oracles.bridges.efrs_uk import SURFACE_SPECS

    rows = [
        row for case in report.get("cases") or [] if isinstance(case, dict)
        for row in (case.get("matches") or []) + (case.get("mismatches") or [])
        if isinstance(row, dict) and row.get("concept") == concept
    ] + [row for row in report.get("mismatches") or []
         if isinstance(row, dict) and row.get("concept") == concept]
    if not rows:
        return None
    names = set()
    for row in rows:
        surface = SURFACE_SPECS.get(row.get("surface"))
        description = row.get("description")
        output = description.rsplit(" — output=", 1)[-1] if isinstance(description, str) else None
        spec = surface.outputs.get(output) if surface else None
        if not spec or spec.get("axiom") != concept or not spec.get("pe"):
            return frozenset()
        names.add(spec["axiom" if engine == "axiom" else "pe"])
    return frozenset(names)


def _observed_cases(report, engine, concept, output, resolver, value_evidence):
    targets = _targets(report, engine, concept, resolver, value_evidence)
    if output not in targets:
        return set()
    return {
        row.get("case_id")
        for row in returned_output_rows(
            report, engine=engine, concept=concept, output=output, targets=targets,
            evidence=value_evidence,
        )
        if observed_output_value(
            report, case_id=row.get("case_id"), output=output, value=row.get("value"),
            engine=engine, concept=concept, targets=targets,
            declared_type=resolver.output_type(output, engine), evidence=value_evidence,
        )
    }


def _paired_cases(report, oracle_engine, concept, output, resolver, value_evidence):
    """Intersect returned case identities for one unambiguous output comparison."""
    oracle_targets = _targets(report, oracle_engine, concept, resolver, value_evidence)
    axiom_targets = _targets(report, AXIOM_ENGINE, concept, resolver, value_evidence)
    if value_evidence.native_fiit:
        from .fiit import native_fiit_pairs

        axiom = native_fiit_pairs(report).get((concept, output))
    elif output in axiom_targets:
        axiom = output
    elif len(oracle_targets) == len(axiom_targets) == 1:
        axiom = next(iter(axiom_targets))
    else:
        # A scalar total does not prove either side's individual components.
        return set()
    if axiom is None:
        return set()
    # Conflicting engine roles cannot pair values from one actual comparison.
    if value_evidence.side_for_engine(AXIOM_ENGINE) is None or value_evidence.side_for_engine(oracle_engine) is None:
        return set()
    paired = (
        _observed_cases(report, oracle_engine, concept, output, resolver, value_evidence)
        & _observed_cases(report, AXIOM_ENGINE, concept, axiom, resolver, value_evidence)
    )
    if not value_evidence.native_fiit and (len(oracle_targets) > 1 or len(axiom_targets) > 1):
        # Returned components do not inherit the total's verdict. A member
        # must retain its own scored comparison and counted residual instead.
        paired &= value_evidence.scored_member_cases(concept, output)
    return paired


def _attested_outputs(
    report: dict,
    oracle_engine: str,
    resolver: OracleTargetResolver,
    stamp: dict | None,
    value_evidence: OutputEvidence,
) -> tuple[frozenset[str], bool]:
    """Every dialect supplies candidate bindings to the same value predicate."""
    if not value_evidence.execution_valid:
        return frozenset(), False
    candidates: set[tuple[str, str]] = set()
    complete = True
    if stamp is not None and isinstance(stamp.get("outputs"), list):
        for row in stamp.get("outputs") or []:
            if not isinstance(row, dict) or row.get("engine") != oracle_engine:
                continue
            if isinstance(row.get("variable"), str) and isinstance(row.get("concept"), str):
                candidates.add((row["concept"], row["variable"]))
        complete = stamp.get("outputs_complete", True) is not False
    if value_evidence.native_fiit:
        from .fiit import native_fiit_pairs

        candidates.update(native_fiit_pairs(report))
    elif oracle_engine == "yale_statutory":
        yale_candidates, complete = _yale_panel_candidates(report)
        candidates.update(yale_candidates)
    elif value_evidence.native_lbtt is not None:
        candidates.update((concept, spec[1]) for concept, spec in value_evidence.native_lbtt.items())
        complete = complete and bool(value_evidence.native_lbtt)
    else:
        concepts = {
            row.get("concept") for row in report.get("aggregates") or []
            if isinstance(row, dict) and _int(row.get("comparison_count")) > 0
        }
        if _int((report.get("summary") or {}).get("comparison_count")) > 0 and isinstance(report.get("concept"), str):
            concepts.add(report["concept"])
        for concept in concepts:
            if not isinstance(concept, str):
                complete = False
                continue
            targets = _targets(report, oracle_engine, concept, resolver, value_evidence)
            if not targets:
                complete = False
            candidates.update((concept, target) for target in targets)

    names = {
        output for concept, output in candidates
        if _paired_cases(report, oracle_engine, concept, output, resolver, value_evidence)
    }
    return frozenset(names), bool(names) and complete and all(
        output in names for _, output in candidates
    )


def _yale_panel_candidates(report):
    """Producer slot metadata supplies bindings, never observation evidence."""
    provenance = report.get("provenance") or {}
    if report.get("suite") != "us-tariff-panel" or not (
        provenance.get("generated_by") == "scripts/run_comparison.py::us-tariff-panel"
        or provenance.get("generator") == "scripts/generate_us_tariff_panel.py"
    ):
        return set(), False
    from axiom_oracles.suites.us_tariff_panel import AUTHORITY_SLOTS

    summary = report.get("summary") or {}
    scope = report.get("scope") or {}
    slots = summary.get("slots") or {}
    declared = scope.get("authority_slots") or []
    columns = (scope.get("reference") or {}).get("columns") or []
    units = report.get("case_count")
    if (not isinstance(units, int) or isinstance(units, bool) or units <= 0
            or summary.get("comparison_count") != units or scope.get("comparison_units") != units):
        return set(), False
    candidates = set()
    complete = set(slots) == set(declared) == set(AUTHORITY_SLOTS) | {"total"}
    for slot, (_, targets) in AUTHORITY_SLOTS.items():
        row = slots.get(slot)
        if slot not in declared or not set(targets) <= set(columns) or not isinstance(row, dict):
            complete = False
            continue
        counts = (row.get("matches"), row.get("mismatches"))
        if not all(isinstance(count, int) and not isinstance(count, bool) and count >= 0
                   for count in counts):
            complete = False
            continue
        family_units = sum(
            family["unit_count"] for family in report.get("cases") or []
            if isinstance(family, dict) and isinstance(family.get("unit_count"), int)
            and not isinstance(family["unit_count"], bool) and family["unit_count"] > 0
            and slot in (family.get("expected") or {}) and slot in (family.get("axiom") or {})
        )
        if not 0 < sum(counts) == family_units <= units:
            complete = False
            continue
        candidates.update((slot, target) for target in targets)
    return candidates, complete


def _engines_map_variables(report: dict, engine: str) -> frozenset[str]:
    """Oracle variables named by the engine→variable ``engines`` shape.

    Reports come in two ``engines`` shapes: the role pair
    ``{"left": "axiom", "right": "policyengine"}`` (names only) and the grid
    shape ``{"axiom": "<concept>", "policyengine": "<variable>"}`` where the
    value declares a candidate variable. Neither shape proves an observation.
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
    # Runner stamping adds versions to both role-pair and engine-key shapes;
    # it is metadata and can neither supply nor conceal a comparison party.
    identities = {key: value for key, value in engines.items() if key != "versions"}
    if set(identities) <= {"left", "right"}:
        return {value for value in identities.values() if isinstance(value, str) and value}
    return {str(key) for key in identities}


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
    except (TypeError, ValueError, OverflowError):
        return 0
