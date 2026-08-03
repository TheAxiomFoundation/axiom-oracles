"""Join universe × comparison reports × dispositions into a conformance scoreboard.

The scoreboard turns the universe (what the oracle simulates) and the committed
comparison reports (what Axiom actually matches) into one per-jurisdiction verdict
against an exact predicate:

    conformant  ⇔  covered == in_scope
                    AND unexplained_total == 0
                    AND axiom_attributed_open == 0

"Covered" is decided from *live evidence*, not intent: an in-scope policy counts
as covered only when its named suite has a committed comparison report present
AND — when that report carries a ``scope.column_exposure`` witness basis — the
reference actually exercises at least one of the policy's output columns with a
positive rate. A comparison of an all-zero column against an implicit 0 verifies
nothing: it would mark an absent implementation "covered" while never probing a
unit where the authority applies (sol stack review F3). Such a policy scores
``unwitnessed`` and is NOT covered. A suite named in the universe but with no
report is in scope and NOT covered — the honest gap the predicate is built to
expose. Reports without an exposure basis (other jurisdictions) keep the
presence-only coverage rule.

Attribution splits the residual mismatches by whose defect they are:

* ``unexplained_total`` — mismatches carrying no explanatory disposition, summed
  from each covered report's ``summary.dispositioned.unexplained_count`` (or the
  raw ``mismatch_count`` for a v2 report with no dispositions file).
* ``axiom_attributed_open`` — the residual that is *Axiom's* to fix: disposition
  rows classed ``axiom_encoding_gap``, plus mismatches whose disposition links an
  **open** ``rulespec-*`` issue. These block conformance; upstream engine gaps and
  bridge artifacts do not.
* ``oracle_attributed`` / ``bridge_artifacts`` — reported for transparency; they
  are explained and do not block conformance.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from axiom_oracles.conformance.loader import Universe

#: Disposition kinds that count as *explained* (do not block conformance).
_EXPLAINED_KINDS = ("explained_residual", "upstream_engine_gap", "bridge_artifact")


def _round(value: float, places: int = 4) -> float:
    return round(value, places)


@dataclass
class PolicyScore:
    """One universe policy's contribution to the scoreboard (the drill-down row)."""

    id: str
    oracle_policy_name: str
    in_scope: bool
    exclusion_reason: str | None
    suite: str | None
    #: True when the named suite has a committed comparison report present.
    covered: bool
    #: Raw comparison stats from the covering report (None when not covered).
    comparisons: int | None = None
    matches: int | None = None
    raw_match_rate: float | None = None
    explained_rate: float | None = None
    unexplained: int | None = None
    axiom_attributed_open: int | None = None
    oracle_attributed: int | None = None
    bridge_artifacts: int | None = None
    note: str | None = None
    #: One-word status for the drill-down table.
    status: str = "excluded"


@dataclass
class JurisdictionScoreboard:
    """The per-jurisdiction headline + predicate verdict + excluded breakdown."""

    jurisdiction: str
    oracle: str
    policies_in_scope: int
    covered: int
    covered_pct: float
    excluded: int
    excluded_by_reason: dict[str, int]
    unexplained_total: int
    axiom_attributed_open: int
    oracle_attributed: int
    bridge_artifacts: int
    #: The exact conformance predicate.
    conformant: bool
    #: Uncovered in-scope policies (the gap list) by name.
    uncovered_policies: list[str] = field(default_factory=list)
    #: In-scope policies whose covering report's exposure basis never
    #: exercises their output columns with a positive rate (subset of the
    #: uncovered gap; sol stack review F3).
    unwitnessed_policies: list[str] = field(default_factory=list)
    #: Aggregated temporal-debt account from covered reports that carry one
    #: (``scope.temporal_debt``): intervals the comparison domain does NOT
    #: reach, surfaced instead of silently clipped (sol stack review F4).
    #: None when no covered report carries a debt account.
    temporal_debt: dict | None = None
    #: Human-readable reasons the predicate is not yet satisfied (empty when
    #: conformant) — so a reader sees *why*, not just a red badge.
    blocking_reasons: list[str] = field(default_factory=list)
    #: Excluded policies invalidated by nonzero live exposure on their output
    #: columns (the enforced re-inclusion tripwire; sol closing review F1).
    #: Non-empty blocks conformance.
    invalid_exclusions: list[str] = field(default_factory=list)

    def to_summary(self) -> dict:
        return asdict(self)


def _report_suite_index(reports: list[dict]) -> dict[str, dict]:
    """Index committed comparison reports by their ``suite`` field.

    When two reports share a suite (e.g. tin_s is compared by uk-worker-pit and
    the savings/dividend variants under distinct suites), each keeps its own key;
    a policy's ``suite`` names exactly one. The presence of ANY report for the
    named suite is what makes a policy covered.
    """
    index: dict[str, dict] = {}
    for report in reports:
        suite = report.get("suite")
        if suite:
            index.setdefault(suite, report)
    return index


def _is_open_rulespec_issue(url: str) -> bool:
    """A linked ``rulespec-*`` issue URL. Open-ness is treated conservatively.

    We cannot query GitHub in the scoreboard join (it must run offline in CI), so
    a linked ``rulespec-*`` *issue* URL is treated as an OPEN Axiom-attributed gap
    by default — the safe direction: an unresolved encoding gap should block
    conformance until the disposition is removed (which is what closing the issue
    prompts). A PR URL or a non-rulespec URL is not counted here.
    """
    lowered = url.lower()
    if "/rulespec-" not in lowered:
        return False
    return "/issues/" in lowered


def _disposition_signals(report: dict) -> tuple[int, int, int, int]:
    """Extract (unexplained, axiom_open, oracle_attributed, bridge) from a report.

    Reads ``summary.dispositioned`` (v2.1). For a v2 report with no dispositions,
    every mismatch is unexplained (nothing has been classified yet).
    """
    summary = report.get("summary") or {}
    dispositioned = summary.get("dispositioned")
    if not dispositioned:
        mismatch = summary.get("mismatch_count")
        if mismatch is None:
            # Fall back to counting mismatch rows.
            mismatch = len(report.get("mismatches") or [])
        return int(mismatch or 0), 0, 0, 0

    counts = dispositioned.get("counts") or {}
    unexplained = int(dispositioned.get("unexplained_count", 0) or 0)
    axiom_open = int(counts.get("axiom_encoding_gap", 0) or 0)
    oracle_attributed = int(counts.get("upstream_engine_gap", 0) or 0)
    bridge = int(counts.get("bridge_artifact", 0) or 0)

    # Add mismatches whose disposition links an OPEN rulespec issue but were not
    # already classed axiom_encoding_gap — those are Axiom-attributed too.
    for mismatch in report.get("mismatches") or []:
        disposition = mismatch.get("disposition")
        if not isinstance(disposition, dict):
            continue
        if disposition.get("disposition") == "axiom_encoding_gap":
            continue  # already counted in counts
        linked = disposition.get("linked_issue")
        if linked and _is_open_rulespec_issue(str(linked)):
            axiom_open += 1
    return unexplained, axiom_open, oracle_attributed, bridge


def score_jurisdiction(
    universe: Universe,
    reports: list[dict],
) -> tuple[JurisdictionScoreboard, list[PolicyScore]]:
    """Compute the scoreboard + per-policy drill-down for one jurisdiction."""
    suite_index = _report_suite_index(reports)

    policy_scores: list[PolicyScore] = []
    excluded_by_reason: dict[str, int] = {}
    covered = 0
    uncovered_policies: list[str] = []
    unwitnessed_policies: list[str] = []
    #: Suites of the DISTINCT covered reports, so each report's mismatch signals
    #: are counted once toward the jurisdiction headline even when several
    #: in-scope policies share one report (the PE-UK case: 12 programs covered by
    #: uk-tax-benefits-efrs). Summing per-policy would multiply a report's 232
    #: upstream gaps by 12 — and, worse, inflate unexplained/axiom-attributed
    #: (which gate conformance) N-fold. The per-policy drill-down still shows each
    #: policy's covering-report stats; only the headline dedupes.
    covered_report_suites: set[str] = set()

    #: Excluded policies whose output columns the reference DOES exercise in a
    #: live report (sol closing review F1): an exclusion grounded in "the
    #: reference never exercises this column" is invalidated the moment any
    #: covering report records nonzero exposure for one of its output vars.
    #: This is the enforced re-inclusion tripwire — it blocks conformance
    #: until the universe row returns to scope with a witness requirement.
    invalid_exclusions: list[str] = []

    for policy in universe.policies:
        if not policy.in_scope:
            reason = policy.exclusion_reason or "unspecified"
            excluded_by_reason[reason] = excluded_by_reason.get(reason, 0) + 1
            exclusion_violated = False
            if policy.output_vars:
                for report in suite_index.values():
                    exposure = (report.get("scope") or {}).get("column_exposure")
                    if isinstance(exposure, dict) and any(
                        (exposure.get(var) or 0) > 0
                        for var in policy.output_vars
                    ):
                        exclusion_violated = True
                        break
            if exclusion_violated:
                invalid_exclusions.append(policy.oracle_policy_name)
            policy_scores.append(
                PolicyScore(
                    id=policy.id,
                    oracle_policy_name=policy.oracle_policy_name,
                    in_scope=False,
                    exclusion_reason=policy.exclusion_reason,
                    suite=None,
                    covered=False,
                    note=policy.note,
                    status=(
                        "excluded:INVALID-nonzero-exposure"
                        if exclusion_violated
                        else f"excluded:{reason}"
                    ),
                )
            )
            continue

        report = suite_index.get(policy.suite) if policy.suite else None
        if report is None:
            uncovered_policies.append(policy.oracle_policy_name)
            policy_scores.append(
                PolicyScore(
                    id=policy.id,
                    oracle_policy_name=policy.oracle_policy_name,
                    in_scope=True,
                    exclusion_reason=None,
                    suite=policy.suite,
                    covered=False,
                    note=policy.note,
                    status="uncovered",
                )
            )
            continue

        # Positive-exposure witness (sol stack review F3): when the covering
        # report carries an exposure basis, the reference must exercise at
        # least one of the policy's output columns with a positive rate.
        # An all-zero column compared against an implicit 0 witnesses
        # nothing — the policy is NOT covered by that comparison.
        exposure = (report.get("scope") or {}).get("column_exposure")
        if isinstance(exposure, dict) and policy.output_vars:
            witnessed = any(
                (exposure.get(var) or 0) > 0 for var in policy.output_vars
            )
            if not witnessed:
                uncovered_policies.append(policy.oracle_policy_name)
                unwitnessed_policies.append(policy.oracle_policy_name)
                policy_scores.append(
                    PolicyScore(
                        id=policy.id,
                        oracle_policy_name=policy.oracle_policy_name,
                        in_scope=True,
                        exclusion_reason=None,
                        suite=policy.suite,
                        covered=False,
                        note=policy.note,
                        status="unwitnessed",
                    )
                )
                continue

        # Covered: pull the report's comparison stats + disposition signals.
        covered += 1
        covered_report_suites.add(policy.suite)
        summary = report.get("summary") or {}
        comparisons = int(summary.get("comparison_count", 0) or 0)
        match_count = int(summary.get("match_count", 0) or 0)
        # Per-policy signals for the drill-down row (the report's own numbers).
        unexplained, axiom_open, oracle_gap, bridge = _disposition_signals(report)

        dispositioned = summary.get("dispositioned") or {}
        raw_rate = (
            dispositioned.get("raw_match_rate")
            if dispositioned
            else (_round(100 * match_count / comparisons) if comparisons else None)
        )
        explained_rate = dispositioned.get("explained_rate") if dispositioned else None

        status = "conformant"
        if axiom_open > 0:
            status = "axiom-gap"
        elif unexplained > 0:
            status = "unexplained"

        policy_scores.append(
            PolicyScore(
                id=policy.id,
                oracle_policy_name=policy.oracle_policy_name,
                in_scope=True,
                exclusion_reason=None,
                suite=policy.suite,
                covered=True,
                comparisons=comparisons,
                matches=match_count,
                raw_match_rate=raw_rate,
                explained_rate=explained_rate,
                unexplained=unexplained,
                axiom_attributed_open=axiom_open,
                oracle_attributed=oracle_gap,
                bridge_artifacts=bridge,
                note=policy.note,
                status=status,
            )
        )

    # Headline mismatch signals: sum each DISTINCT covered report once (a report
    # shared by N policies must not multiply its residual N-fold, or the
    # conformance predicate and the ratchet would be inflated).
    unexplained_total = 0
    axiom_attributed_open = 0
    oracle_attributed = 0
    bridge_artifacts = 0
    temporal_debt: dict | None = None
    for suite in sorted(covered_report_suites):
        report = suite_index[suite]
        unexplained, axiom_open, oracle_gap, bridge = _disposition_signals(report)
        unexplained_total += unexplained
        axiom_attributed_open += axiom_open
        oracle_attributed += oracle_gap
        bridge_artifacts += bridge
        # Temporal-debt surface (sol stack review F4): intervals the
        # comparison domain does not reach are carried onto the scoreboard
        # instead of silently clipped out of the coverage story.
        debt = (report.get("scope") or {}).get("temporal_debt")
        if isinstance(debt, dict):
            if temporal_debt is None:
                temporal_debt = {
                    "pre_domain_intervals": 0,
                    "straddle_clipped_intervals": 0,
                    "addressable_records": 0,
                }
            temporal_debt["pre_domain_intervals"] += int(
                debt.get("pre_domain_intervals") or 0
            )
            temporal_debt["straddle_clipped_intervals"] += int(
                debt.get("straddle_clipped_intervals") or 0
            )
            temporal_debt["addressable_records"] += len(debt.get("records") or [])

    in_scope = len(universe.in_scope())
    covered_pct = _round(100 * covered / in_scope) if in_scope else 0.0

    # The exact predicate. An invalidated exclusion (nonzero live exposure on
    # an excluded policy's output column) blocks conformance outright — the
    # excluded row must return to scope and earn a witness before any
    # conformant verdict.
    predicate_covered = covered == in_scope
    conformant = (
        predicate_covered
        and unexplained_total == 0
        and axiom_attributed_open == 0
        and not invalid_exclusions
    )

    blocking_reasons: list[str] = []
    if invalid_exclusions:
        blocking_reasons.append(
            f"{len(invalid_exclusions)} excluded polic"
            f"{'y is' if len(invalid_exclusions) == 1 else 'ies are'} "
            "invalidated by nonzero live exposure on their output columns "
            "(re-inclusion required): " + ", ".join(sorted(invalid_exclusions))
        )
    if not predicate_covered:
        blocking_reasons.append(
            f"{in_scope - covered} of {in_scope} in-scope policies are not "
            f"covered by a live suite: {', '.join(uncovered_policies)}"
        )
        if unwitnessed_policies:
            blocking_reasons.append(
                f"{len(unwitnessed_policies)} of those have a report but no "
                "positive-exposure witness — the reference never exercises "
                "their output columns with a nonzero rate: "
                f"{', '.join(unwitnessed_policies)}"
            )
    if unexplained_total > 0:
        blocking_reasons.append(
            f"{unexplained_total} unexplained mismatch(es) across covered suites"
        )
    if axiom_attributed_open > 0:
        blocking_reasons.append(
            f"{axiom_attributed_open} open Axiom-attributed encoding gap(s)"
        )

    scoreboard = JurisdictionScoreboard(
        jurisdiction=universe.jurisdiction,
        oracle=universe.oracle.label,
        policies_in_scope=in_scope,
        covered=covered,
        covered_pct=covered_pct,
        excluded=len(universe.excluded()),
        excluded_by_reason=dict(sorted(excluded_by_reason.items())),
        unexplained_total=unexplained_total,
        axiom_attributed_open=axiom_attributed_open,
        oracle_attributed=oracle_attributed,
        bridge_artifacts=bridge_artifacts,
        conformant=conformant,
        uncovered_policies=uncovered_policies,
        unwitnessed_policies=unwitnessed_policies,
        temporal_debt=temporal_debt,
        blocking_reasons=blocking_reasons,
        invalid_exclusions=sorted(invalid_exclusions),
    )
    return scoreboard, policy_scores
