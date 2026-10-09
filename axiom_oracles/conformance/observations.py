"""One output-observation predicate shared by producers and coverage consumers.

Bindings identify candidate outputs. Only returned comparison values can prove
an observation; counts, declarations, metadata and stamp claims cannot.
"""

from collections import defaultdict
from math import isclose, isfinite
from numbers import Number


# Exact queries made by scripts/generate_uk_lbtt_ltt.py::TxnCase. The native
# report records each query and country, while its engine heading groups both.
_LBTT_NATIVE_OUTPUTS = {
    "SCOTLAND": (
        "uk:policies/govuk/lbtt#land_and_buildings_transaction_tax",
        "land_and_buildings_transaction_tax",
    ),
    "WALES": (
        "uk:policies/govuk/ltt#land_transaction_tax",
        "land_transaction_tax",
    ),
}


def _output_names(value):
    if isinstance(value, str):
        return frozenset(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, (list, tuple)) and all(isinstance(name, str) for name in value):
        return frozenset(value)
    return frozenset()


def native_lbtt_pairs(report):
    """Resolve recorded native country/query pairs; values still need validation.

    None denotes another dialect. An empty dictionary denotes a native report
    whose recorded bindings contradict its actual per-case query identity.
    """
    provenance = report.get("provenance")
    if (report.get("suite") != "uk-lbtt-ltt" or not isinstance(provenance, dict)
            or provenance.get("generator") != "scripts/generate_uk_lbtt_ltt.py"):
        return None
    engines = report.get("engines") or {}
    declared_oracle = _output_names(engines.get("policyengine"))
    axiom_heading = engines.get("axiom")
    declared_axiom = (
        frozenset(spec[0] for spec in _LBTT_NATIVE_OUTPUTS.values())
        if axiom_heading == "uk:policies/govuk/{lbtt,ltt} devolved transaction tax"
        else _output_names(axiom_heading)
    )
    explicit = report.get("output_bindings") or {}
    native = report.get("engine_bindings") or {}
    if not isinstance(explicit, dict) or not isinstance(native, dict):
        return {}
    pairs = {}
    for case in report.get("cases") or []:
        if not isinstance(case, dict):
            return {}
        spec = _LBTT_NATIVE_OUTPUTS.get(case.get("country"))
        if (spec is None or case.get("concept") != spec[0]
                or spec[0] not in declared_axiom or spec[1] not in declared_oracle):
            return {}
        binding = explicit.get(spec[0], {})
        if not isinstance(binding, dict):
            return {}
        for engine, target in zip(("axiom", "policyengine"), spec):
            if engine in binding and _output_names(binding[engine]) != {target}:
                return {}
            engine_binding = native.get(engine)
            if isinstance(engine_binding, dict) and ("outputs" in engine_binding or "output" in engine_binding):
                recorded = _output_names(engine_binding.get("outputs", engine_binding.get("output")))
                if target not in recorded:
                    return {}
        pairs[spec[0]] = spec
    return pairs


class OutputEvidence:
    """Indexes for one report, built after its producer finishes writing it.

    The context belongs to a single computation, rather than a global cache:
    callers that mutate a report must build another context. Each observation
    checks only the relevant case and concept after the report is indexed.
    """

    def __init__(self, report):
        self.report = report
        self.observed_by_output = defaultdict(list)
        self.observed_by_case_output = defaultdict(list)
        self.cases_by_id = defaultdict(list)
        self.comparisons_by_case_concept = defaultdict(list)
        self.comparisons_by_engine_concept = defaultdict(list)
        self.top_mismatches_by_engine_concept = defaultdict(list)
        self.mismatches_by_case_concept = defaultdict(list)
        self.explicit_comparisons_by_case_output = defaultdict(list)
        self.scored_members = defaultdict(list)
        self.aggregates_by_concept = defaultdict(list)
        self.grid_cases_by_engine_concept = defaultdict(list)
        self.sides_by_engine = defaultdict(set)
        self._returned_rows = {}
        self._returned_by_case = {}
        self.native_fiit = native_fiit_report(report)
        self.native_lbtt = native_lbtt_pairs(report)

        engines = report.get("engines") or {}
        self.engines = engines if isinstance(engines, dict) else {}
        self.grid_targets = {
            engine: frozenset(part.strip() for part in targets.split(",") if part.strip())
            if isinstance(targets, str) else frozenset(targets)
            if isinstance(targets, (list, tuple)) else frozenset()
            for engine, targets in self.engines.items()
            if engine not in {"left", "right", "versions"}
        }
        for side in ("left", "right"):
            engine = self.engines.get(side)
            if isinstance(engine, str):
                self.sides_by_engine[engine].add(side)
        grid_engines = (set(self.engines) - {"left", "right", "versions"}) | {
            self.engines[side] for side in ("left", "right")
            if isinstance(self.engines.get(side), str)
        }
        compared_concepts = {
            row["concept"] for row in report.get("aggregates") or []
            if isinstance(row, dict) and isinstance(row.get("concept"), str)
            and isinstance(row.get("comparison_count"), int)
            and not isinstance(row["comparison_count"], bool)
            and row["comparison_count"] > 0
        }
        sole_concept = next(iter(compared_concepts)) if len(compared_concepts) == 1 else None

        observations = list(report.get("observed_outputs") or [])
        if self.native_fiit:
            from .fiit import FIIT_SURFACE_CONCEPT_IDS, native_fiit_pairs
            from axiom_oracles.bridges.tax_populace import SURFACE_OUTPUTS

            pairs = native_fiit_pairs(report)
            retained = []
            for row in observations:
                if not isinstance(row, dict):
                    continue
                native_concept = FIIT_SURFACE_CONCEPT_IDS.get(row.get("surface"))
                native_spec = SURFACE_OUTPUTS.get(row.get("surface"), {}).get(row.get("output"))
                if row.get("engine") == "policyengine" and native_spec and (
                    row.get("concept") != native_concept or row.get("variable") != native_spec["pe"]
                ):
                    # Both explicit names contradict this native binding;
                    # neither label can hide the conflicting case/output.
                    retained.extend([
                        dict(row, missing=True),
                        dict(row, concept=native_concept, variable=native_spec["pe"],
                             value=None, missing=True),
                    ])
                    continue
                target = pairs.get((row.get("concept"), row.get("variable")))
                if row.get("engine") != "policyengine" or target is None:
                    retained.append(row)
                    continue
                # This value was returned for the exact native Axiom output,
                # in this oracle output's comparison, before money projection.
                retained.extend([
                    dict(row, require_counterpart=True),
                    dict(row, engine="axiom", variable=target,
                         value=row.get("counterpart_value"),
                         counterpart_value=row.get("value"), require_counterpart=True),
                ])
            observations = retained
        for row in observations:
            if not isinstance(row, dict):
                continue
            if all(isinstance(row.get(key), str) for key in ("engine", "variable")):
                # Contradictions identify a case/output independently of its
                # concept label. A malformed label cannot erase a NULL or stop.
                if valid_case_id(row.get("case_id")):
                    self.observed_by_case_output[(row["engine"], row["variable"], row["case_id"])].append(row)
            if all(isinstance(row.get(key), str) for key in ("engine", "concept", "variable")):
                key = (row["engine"], row["concept"], row["variable"])
                self.observed_by_output[key].append(row)

        for ordinal, case in enumerate(report.get("cases") or []):
            if not isinstance(case, dict):
                continue
            # Yale records case families rather than individual comparison
            # units; their stable family ordinal is the producer's identity.
            if report.get("suite") == "us-tariff-panel" and "case_id" not in case:
                case = dict(case, case_id=ordinal)
            case_id = case.get("case_id")
            if not valid_case_id(case_id):
                continue
            self.cases_by_id[case_id].append(case)
            concept = case.get("concept", sole_concept)
            if isinstance(concept, str):
                for engine in grid_engines:
                    if engine in case or f"{engine}_components" in case:
                        self.grid_cases_by_engine_concept[(engine, concept)].append(case)
            for side in ("left", "right"):
                engine = case.get(f"{side}_engine", self.engines.get(side))
                if isinstance(engine, str):
                    self.sides_by_engine[engine].add(side)
            for matched, row in (
                [(True, row) for row in case.get("matches") or []]
                + [(False, row) for row in case.get("mismatches") or []]
            ):
                if not isinstance(row, dict):
                    continue
                concept = row.get("concept")
                if isinstance(concept, str):
                    self.comparisons_by_case_concept[(case_id, concept)].append((case, row))
                    if isinstance(row.get("variable"), str):
                        self.scored_members[(concept, row["variable"], case_id)].append((row, matched))
                for side in ("left", "right"):
                    engine = case.get(f"{side}_engine", self.engines.get(side))
                    if isinstance(engine, str) and isinstance(row.get("variable"), str):
                        self.explicit_comparisons_by_case_output[(
                            engine, row["variable"], case_id,
                        )].append((row, side))
                    if isinstance(engine, str) and isinstance(concept, str) and side in row:
                        self.comparisons_by_engine_concept[(engine, concept)].append(
                            (case_id, row, side)
                        )

        # Engine-key grid dialects conventionally compare Axiom on the left.
        # Explicit role names from their case rows take precedence.
        if len(grid_engines) == 2 and "axiom" in grid_engines:
            for engine in grid_engines:
                if not self.sides_by_engine.get(engine):
                    self.sides_by_engine[engine].add("left" if engine == "axiom" else "right")

        # Engine-key grids also retain named left/right member comparisons.
        # Index their sides after resolving the grid convention, so a scored
        # member cannot disagree with its own returned ledger values.
        for case_id, cases in self.cases_by_id.items():
            for case in cases:
                for row in (case.get("matches") or []) + (case.get("mismatches") or []):
                    if not isinstance(row, dict) or not isinstance(row.get("variable"), str):
                        continue
                    for engine in grid_engines:
                        side = self.side_for_engine(engine)
                        if side is None or case.get(f"{side}_engine", self.engines.get(side)) is not None:
                            continue
                        self.explicit_comparisons_by_case_output[(
                            engine, row["variable"], case_id,
                        )].append((row, side))
                        if isinstance(row.get("concept"), str) and side in row:
                            self.comparisons_by_engine_concept[(engine, row["concept"])].append(
                                (case_id, row, side)
                            )

        for row in report.get("mismatches") or []:
            if isinstance(row, dict) and valid_case_id(row.get("case_id")):
                concept = row.get("concept")
                if isinstance(concept, str):
                    self.mismatches_by_case_concept[(row["case_id"], concept)].append(row)
                    if isinstance(row.get("variable"), str):
                        self.scored_members[(concept, row["variable"], row["case_id"])].append((row, False))
                for engine in grid_engines:
                    side = self.side_for_engine(engine)
                    value_key = engine if engine in row else side
                    if isinstance(row.get("variable"), str):
                        self.explicit_comparisons_by_case_output[(
                            engine, row["variable"], row["case_id"],
                        )].append((row, value_key))
                    if isinstance(concept, str) and value_key and value_key in row:
                        self.top_mismatches_by_engine_concept[(engine, concept)].append(
                            (row["case_id"], row, value_key)
                        )
        for row in report.get("aggregates") or []:
            if isinstance(row, dict) and isinstance(row.get("concept"), str):
                self.aggregates_by_concept[row["concept"]].append(row)

        stamp = report.get("attestation")
        summary = report.get("summary") or {}
        summary = summary if isinstance(summary, dict) else {}
        by_engine = summary.get("errors_by_engine") or {}
        engine_errors = (
            any(by_engine.values()) if isinstance(by_engine, dict)
            else any(isinstance(row, dict) and row.get("count") for row in by_engine)
            if isinstance(by_engine, list) else bool(by_engine)
        )
        self.execution_valid = (
            (stamp is None or (isinstance(stamp, dict) and stamp.get("executed", True) is True
                              and not _contradiction(stamp)))
            and not _contradiction(report)
            and not _contradiction(summary) and not summary.get("error_count")
            and not summary.get("skipped_count") and not engine_errors
        )

    def side_for_engine(self, engine):
        sides = self.sides_by_engine.get(engine, ())
        return next(iter(sides)) if len(sides) == 1 else None

    def rows(self, *, engine, concept, output, targets=()):
        """Cached returned rows for one binding, including its case index."""
        key = (engine, concept, output, frozenset(targets))
        if key in self._returned_rows:
            return self._returned_rows[key]
        rows = list(self.observed_by_output.get((engine, concept, output), ()))
        scalar = set(targets) == {output} and not self.native_fiit
        for case in self.grid_cases_by_engine_concept.get((engine, concept), ()):
            components = case.get(f"{engine}_components")
            if isinstance(components, dict) and output in targets and output in components:
                rows.append(_value_row(
                    case, case_id=case["case_id"], engine=engine,
                    concept=concept, output=output, value=components[output],
                ))
            native_scalar = (
                self.native_lbtt is not None and concept in self.native_lbtt
                and engine in {"axiom", "policyengine"}
                and output == self.native_lbtt[concept][0 if engine == "axiom" else 1]
            )
            if (scalar and engine in case and self.report.get("suite") != "us-tariff-panel"
                    and (native_scalar or engine not in self.grid_targets or self.grid_targets[engine] == {output})):
                rows.append(_value_row(
                    case, case_id=case["case_id"], engine=engine,
                    concept=concept, output=output, value=case[engine],
                ))
        comparisons = self.comparisons_by_engine_concept.get((engine, concept), ())
        top_mismatches = self.top_mismatches_by_engine_concept.get((engine, concept), ())
        for case_id, row, side in (*comparisons, *top_mismatches):
            named = row.get("variable")
            if (named == output or scalar) and (named is None or named == output):
                rows.append(_value_row(
                    row, case_id=case_id, engine=engine,
                    concept=concept, output=output, value=row[side],
                ))

        # An expected slot is a returned column only for a single-column
        # authority. Its Axiom counterpart is part of the same comparison.
        if engine in {"axiom", "yale_statutory"} and self.report.get("suite") == "us-tariff-panel":
            from axiom_oracles.suites.us_tariff_panel import AUTHORITY_SLOTS

            slot_spec = AUTHORITY_SLOTS.get(concept)
            if slot_spec is not None and slot_spec[0] is not None and tuple(slot_spec[1]) == (output,):
                for cases in self.cases_by_id.values():
                    for case in cases:
                        values = case.get("expected" if engine == "yale_statutory" else "axiom")
                        if not isinstance(values, dict) or concept not in values:
                            continue
                        counterpart = case.get("axiom" if engine == "yale_statutory" else "expected")
                        rows.append(_value_row(
                            case, case_id=case["case_id"], engine=engine,
                            concept=concept, output=output, value=values[concept],
                            counterpart_value=counterpart.get(concept) if isinstance(counterpart, dict) else None,
                            require_counterpart=True, numeric_counterpart=True,
                        ))

        by_case = defaultdict(list)
        for row in rows:
            if valid_case_id(row.get("case_id")):
                by_case[row["case_id"]].append(row)
        self._returned_rows[key] = rows
        self._returned_by_case[key] = by_case
        return rows

    def rows_for_case(self, *, case_id, engine, concept, output, targets=()):
        self.rows(engine=engine, concept=concept, output=output, targets=targets)
        return self._returned_by_case[(engine, concept, output, frozenset(targets))].get(case_id, ())

    def scored_member_cases(self, concept, output):
        """Member comparison identities whose verdict and residual are retained."""
        mismatches = sum(
            any(not matched for _, matched in rows)
            for rows in self.scored_members.values()
        )
        retained = (self.report.get("summary") or {}).get("mismatch_count", 0)
        if not isinstance(retained, int) or isinstance(retained, bool) or retained < mismatches:
            return set()
        return {
            case_id for (row_concept, variable, case_id), rows in self.scored_members.items()
            if row_concept == concept and variable == output
            and all(_scored_member_valid(row, matched) for row, matched in rows)
        }


def _scored_member_valid(row, matched):
    """A member's retained numeric residual and verdict describe the same score."""
    tolerance = row.get("tolerance", 0)
    relative_tolerance = row.get("relative_tolerance", 0)
    if (_contradiction(row)
            or ("matches" in row and row["matches"] is not matched)
            or not _valid_value(row.get("difference"), None, allow_bool=False)
            or not _valid_value(row.get("left"), None)
            or not _valid_value(row.get("right"), None)
            or not _valid_value(tolerance, None, allow_bool=False) or tolerance < 0
            or not _valid_value(relative_tolerance, None, allow_bool=False) or relative_tolerance < 0):
        return False
    try:
        return (
            row["difference"] == row["left"] - row["right"]
            and isclose(row["left"], row["right"], abs_tol=tolerance,
                        rel_tol=relative_tolerance) == matched
        )
    except (TypeError, ValueError, OverflowError):
        return False


def returned_output_rows(report, *, engine, concept, output, targets=(), evidence=None):
    """Read returned values without expanding scalar sums into components."""
    evidence = evidence if evidence is not None else OutputEvidence(report)
    _check_context(report, evidence)
    return iter(evidence.rows(engine=engine, concept=concept, output=output, targets=targets))


def observed_output_value(
    report, *, case_id, output, value, engine, concept=None, declared_type=None,
    targets=(), evidence=None,
):
    """Whether an executed comparison actually returned this case/output value.

    Zero and False are observations. Nonnumeric outputs need a registered type,
    supplied by the resolver rather than report metadata. Missing, error or skip
    evidence for the same case/output overrides a positive claim.
    """
    evidence = evidence if evidence is not None else OutputEvidence(report)
    _check_context(report, evidence)
    if not evidence.execution_valid or not valid_case_id(case_id):
        return False
    cases = evidence.cases_by_id.get(case_id, ())
    if len(cases) > 1:
        concepts = [_case_concepts(case) for case in cases]
        # Custom grids may record separate outputs of one real case in
        # separate rows. Repeated comparisons of the same concept, or rows
        # whose comparison identity is absent, cannot be paired across rows.
        if any(not names for names in concepts) or sum(concept in names for names in concepts) > 1:
            return False
    if not _valid_value(value, declared_type):
        return False
    same_case = evidence.rows_for_case(
        case_id=case_id, engine=engine, concept=concept, output=output, targets=targets,
    )
    if not same_case or not any(_same_value(row.get("value"), value) for row in same_case):
        return False
    cross_concept = evidence.observed_by_case_output.get((engine, output, case_id), ())
    side = evidence.side_for_engine(engine)
    if any(not _valid_value(row.get("value"), declared_type)
           or _contradiction(row) or _missing_side(row, side)
           or not _values_agree(row.get("value"), value)
           or (row.get("require_counterpart") and (
               not _valid_value(row.get("value"), declared_type,
                                allow_bool=not row.get("numeric_counterpart"))
               or not _valid_value(row.get("counterpart_value"), declared_type,
                                    allow_bool=not row.get("numeric_counterpart"))
           ))
           for row in (*same_case, *cross_concept)):
        return False

    for case in evidence.cases_by_id.get(case_id, ()):
        if side is not None and case.get(f"{side}_engine", engine) != engine:
            return False
        if _contradiction(case) or case.get("left_errors") or case.get("right_errors"):
            return False
        missing = case.get("missing_outputs") or {}
        if isinstance(missing, dict) and _names_missing(missing.get(engine), output):
            return False
        components = case.get(f"{engine}_components")
        if isinstance(components, dict) and output in components and (
            not _valid_value(components[output], declared_type)
            or not _values_agree(components[output], value)
        ):
            return False

    for row, value_key in evidence.explicit_comparisons_by_case_output.get((engine, output, case_id), ()):
        row_side = value_key if value_key in ("left", "right") else side
        if _contradiction(row) or _missing_side(row, row_side):
            return False
        if value_key and value_key in row and (
            not _valid_value(row[value_key], declared_type)
            or not _values_agree(row[value_key], value)
        ):
            return False

    scalar = set(targets) == {output}
    for case, row in evidence.comparisons_by_case_concept.get((case_id, concept), ()):
        if _comparison_stopped(row):
            return False
        if row.get("variable") is not None and row.get("variable") != output:
            if scalar and engine != "axiom":
                return False
            continue
        if row.get("variable") == output and _contradiction(row):
            return False
        # A missing sum cannot identify the absent member. Individual ledger
        # rows decide the components independently.
        if not scalar:
            continue
        side = next((side for side in ("left", "right")
                     if case.get(f"{side}_engine", evidence.engines.get(side)) == engine), None)
        if _missing_side(row, side):
            return False
        if side and side in row and (
            not _valid_value(row[side], declared_type)
            or not _values_agree(row[side], value) or _contradiction(row)
        ):
            return False

    side = evidence.side_for_engine(engine)
    for row in evidence.mismatches_by_case_concept.get((case_id, concept), ()):
        if _comparison_stopped(row):
            return False
        if row.get("variable") is not None and row.get("variable") != output:
            if scalar and engine != "axiom":
                return False
            continue
        if row.get("variable") == output and _contradiction(row):
            return False
        if scalar and _missing_side(row, side):
            return False
        if scalar and side and side in row and (
            not _valid_value(row[side], declared_type)
            or not _values_agree(row[side], value) or _contradiction(row)
        ):
            return False

    # Scalar missing counters can disprove all claimed cases. Sum counters
    # cannot identify an absent component and do not apply to individual members.
    if scalar:
        for row in evidence.aggregates_by_concept.get(concept, ()):
            compared = row.get("comparison_count")
            if not isinstance(compared, int) or isinstance(compared, bool) or compared <= 0:
                continue
            for key in (f"missing_{side}_count", f"missing_{engine}_count", "missing_both_count"):
                missing = row.get(key)
                if isinstance(missing, int) and not isinstance(missing, bool) and missing >= compared:
                    return False
    return True


def _value_row(source, *, case_id, engine, concept, output, value, **extra):
    row = {key: source[key] for key in (
        "missing", "error", "errors", "skipped", "skip_reason", "executed",
    ) if key in source}
    row.update(case_id=case_id, engine=engine, concept=concept,
               variable=output, value=value, **extra)
    return row


def _contradiction(row):
    return bool(row.get("missing") or row.get("error") or row.get("errors")
                or row.get("skipped") or row.get("skip_reason")
                or ("executed" in row and row["executed"] is not True))


def _names_missing(missing, output):
    if isinstance(missing, dict):
        return bool(missing.get(output))
    if isinstance(missing, str):
        return missing == output
    return isinstance(missing, (list, tuple, set)) and output in missing


def _check_context(report, evidence):
    if evidence.report is not report:
        raise ValueError("OutputEvidence belongs to another report")


def _missing_side(row, side):
    if row.get("kind") == "missing_both" or (
        side is not None and row.get("kind") == f"missing_{side}"
    ):
        return True
    return any(
        isinstance(row.get(key), int) and not isinstance(row[key], bool) and row[key] > 0
        for key in (f"missing_{side}_count", "missing_both_count")
    )


def _comparison_stopped(row):
    return bool(row.get("error") or row.get("errors") or row.get("skipped")
                or row.get("skip_reason")
                or ("executed" in row and row["executed"] is not True))


def valid_case_id(case_id):
    """A usable comparison case identity: an integer or nonempty string."""
    return ((isinstance(case_id, int) and not isinstance(case_id, bool))
            or (isinstance(case_id, str) and bool(case_id)))


def native_fiit_report(report):
    """Native FIIT diagnostics use output names, not generic concept targets."""
    if ((report.get("suite") == "fiit-ecps" and "output_bindings" not in report)
            or (report.get("provenance") or {}).get("generated_by")
            == "scripts/run_comparison.py::fiit-ecps"):
        return True
    rows = [row for key in ("output_summary", "observed_outputs")
            for row in report.get(key) or []
            if isinstance(row, dict) and "surface" in row and "output" in row]
    if not rows:
        return False
    from .fiit import FIIT_SURFACE_CONCEPT_IDS

    return any(row.get("surface") in FIIT_SURFACE_CONCEPT_IDS for row in rows)


def _case_concepts(case):
    if isinstance(case.get("concept"), str):
        return {case["concept"]}
    return {
        row["concept"] for row in (case.get("matches") or []) + (case.get("mismatches") or [])
        if isinstance(row, dict) and isinstance(row.get("concept"), str)
    }


def json_output_values(value):
    """Represent nonfinite numeric report values as JSON null.

    The in-memory producer retains the returned values for inspection. Its
    serialized evidence keeps invalid numeric values absent, using the same
    validity rule as output observations. Error and skip markers retain their
    contradiction when replacing their numeric payload with null would erase it.
    """
    if isinstance(value, dict):
        normalized = {key: json_output_values(item) for key, item in value.items()}
        for key, item in value.items():
            if _contradiction({key: item}) and not _contradiction({key: normalized[key]}):
                normalized[key] = True
        return normalized
    if isinstance(value, list):
        return [json_output_values(item) for item in value]
    if isinstance(value, tuple):
        return tuple(json_output_values(item) for item in value)
    if isinstance(value, Number) and not _valid_value(value, None):
        return None
    return value


def _valid_value(value, declared_type, *, allow_bool=True):
    if value is None:
        return False
    if isinstance(value, bool) and not allow_bool:
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, Number):
        try:
            return isfinite(value)
        except (TypeError, ValueError, OverflowError):
            return False
    return declared_type is not None and isinstance(value, declared_type)


def _same_value(left, right):
    return type(left) is type(right) and left == right


def _values_agree(left, right):
    # Equivalent finite numeric representations do not contradict each other;
    # a genuinely different returned value for this same output/case does.
    return left == right
