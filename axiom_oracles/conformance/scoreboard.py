"""Join universe × comparison reports × dispositions into a conformance scoreboard.

The scoreboard turns the universe (what the oracle simulates) and the committed
comparison reports (what Axiom actually matches) into one per-jurisdiction verdict
against an exact predicate:

    conformant  ⇔  covered == in_scope
                   AND unexplained_total == 0
                   AND axiom_attributed_open == 0
                   AND no invalidated exclusions (nonzero live exposure on an
                       excluded policy's output column blocks the verdict)

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

* ``unexplained_total`` — shared conservative unexplained assessments, summed
  once for each distinct covered report. Invalid count signals block conformance.
* ``axiom_attributed_open`` — the residual that is *Axiom's* to fix: disposition
  rows classed ``axiom_encoding_gap``, plus mismatches whose disposition links an
  **open** ``rulespec-*`` issue. These block conformance; upstream engine gaps and
  bridge artifacts do not.
* ``oracle_attributed`` / ``bridge_artifacts`` — reported for transparency; they
  are explained and do not block conformance.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from pathlib import Path

from axiom_oracles.conformance.loader import Universe
from axiom_oracles.conformance.unexplained import (
    admit_count,
    assess_unexplained,
    load_known_causes,
    resolve_suite_reports,
)

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


def _report_suite_index(
    reports: list[dict], *, known_causes=(), repo_root: Path | None = None,
) -> dict[str, dict]:
    """Resolve duplicate reports by the shared maximum-unexplained rule."""
    return resolve_suite_reports(reports, known_causes=known_causes, repo_root=repo_root)


def _disposition_signals(
    report: dict, *, known_causes=None, repo_root: Path | None = None,
) -> tuple[int, int, int, int]:
    """Return shared unexplained/Axiom signals and admitted upstream/bridge counts."""
    if known_causes is None:
        known_causes = load_known_causes(repo_root)
    assessment = assess_unexplained(report, known_causes=known_causes, repo_root=repo_root)
    summary = report.get("summary") or {}
    if not isinstance(summary, dict):
        summary = {}
    block = summary.get("dispositioned") or {}
    counts = (block.get("counts") or {}) if isinstance(block, dict) else {}
    if not isinstance(counts, dict):
        counts = {}
    return (
        assessment.count,
        assessment.axiom_attributed,
        admit_count(counts.get("upstream_engine_gap", 0)) or 0,
        admit_count(counts.get("bridge_artifact", 0)) or 0,
    )


def _exposure_number(value: object) -> int | float | None:
    """Only finite native numbers can witness or support an exclusion."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def score_jurisdiction(
    universe: Universe,
    reports: list[dict],
    *,
    known_causes=None,
    repo_root: Path | None = None,
) -> tuple[JurisdictionScoreboard, list[PolicyScore]]:
    """Compute the scoreboard + per-policy drill-down for one jurisdiction."""
    if known_causes is None:
        known_causes = load_known_causes(repo_root)
    universe_suites = {policy.suite for policy in universe.in_scope() if policy.suite}
    relevant_reports = [r for r in reports if r.get("suite") in universe_suites]
    suite_index = _report_suite_index(
        relevant_reports, known_causes=known_causes, repo_root=repo_root,
    )
    suite_files: dict[str, list[str]] = {}
    report_defects: set[str] = set()
    for report in relevant_reports:
        suite = report["suite"]
        filename = report.get("_file") or "<unnamed report>"
        suite_files.setdefault(suite, []).append(filename)
        assessment = assess_unexplained(
            report, known_causes=known_causes, repo_root=repo_root,
        )
        report_defects.update(
            f"[{suite}] {filename}: {defect}" for defect in assessment.defects
        )
    contested_suites = {suite for suite, files in suite_files.items() if len(files) > 1}
    #: The raw, uncollapsed report list — exclusion-tripwire scans must see
    #: every report, order-independently (sol closing review r2 finding 1).
    all_reports = list(reports)

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
            # Scan EVERY raw report, not the collapsed suite index — a
            # zero-exposure duplicate must never shadow a nonzero one
            # (order-independence; sol closing review r2 finding 1).
            exclusion_violated = False
            if policy.output_vars:
                for report in all_reports:
                    exposure = (report.get("scope") or {}).get("column_exposure")
                    if isinstance(exposure, dict) and any(
                        (value := _exposure_number(exposure[var])) is None or value != 0
                        for var in policy.output_vars if var in exposure
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
        if report is None or policy.suite in contested_suites:
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
                    status="contested" if policy.suite in contested_suites else "uncovered",
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
                (value := _exposure_number(exposure.get(var))) is not None and value > 0
                for var in policy.output_vars
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
        if not isinstance(summary, dict):
            summary = {}
        comparisons = int(summary.get("comparison_count", 0) or 0)
        match_count = int(summary.get("match_count", 0) or 0)
        # Per-policy signals for the drill-down row (the report's own numbers).
        unexplained, axiom_open, oracle_gap, bridge = _disposition_signals(
            report, known_causes=known_causes, repo_root=repo_root,
        )

        dispositioned = summary.get("dispositioned") or {}
        if not isinstance(dispositioned, dict):
            dispositioned = {}
        raw_rate = (
            dispositioned.get("raw_match_rate")
            if dispositioned
            else (_round(100 * match_count / comparisons) if comparisons else None)
        )
        explained_rate = dispositioned.get("explained_rate") if dispositioned else None

        status = "conformant"
        if assess_unexplained(
            report, known_causes=known_causes, repo_root=repo_root,
        ).defects:
            status = "invalid-report"
        elif axiom_open > 0:
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
        unexplained, axiom_open, oracle_gap, bridge = _disposition_signals(
            report, known_causes=known_causes, repo_root=repo_root,
        )
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
        and not report_defects
    )

    blocking_reasons: list[str] = sorted(report_defects)
    for suite in sorted(contested_suites):
        blocking_reasons.append(
            f"[{suite}] contested coverage: multiple reports: "
            + ", ".join(sorted(suite_files[suite]))
        )
    if invalid_exclusions:
        blocking_reasons.append(
            f"{len(invalid_exclusions)} excluded polic"
            f"{'y is' if len(invalid_exclusions) == 1 else 'ies are'} "
            "invalidated by nonzero or invalid live exposure on their output columns "
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
