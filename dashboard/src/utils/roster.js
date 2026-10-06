/**
 * The oracle roster: which reports verify Axiom, and how they group by
 * oracle. Pure, so scripts/test-oracle-attribution.mjs can check the
 * grouping the overview renders.
 */

import {
  displayEngines,
  isAxiomPair,
  otherOracle,
  reportMetric,
  suiteMeta,
} from "./suites";

/**
 * The unit of counting is the household case: one household compared once,
 * no matter how many concepts (liability, CTC, EITC, …) that comparison
 * covers — component concepts roll up into their parent, and a household's
 * concept-by-concept comparisons are the evidence, not extra households.
 */
export function reportHouseholds(report) {
  return Number.isFinite(report.case_count)
    ? report.case_count
    : (report.cases || []).length;
}

/** Axiom-pair reports with measured aggregates, minus hidden oracles. */
export function verificationReports(reports, hidden) {
  return reports.filter(
    (r) =>
      isAxiomPair(r) &&
      !hidden.has(otherOracle(r)) &&
      suiteMeta(r.suite).kind !== "diagnostic" &&
      (r.aggregates || []).length > 0,
  );
}

/** Oracle-vs-oracle arbitration runs, unless either side is hidden. */
export function crossCheckCount(reports, hidden) {
  return reports.filter((r) => {
    if (isAxiomPair(r)) return false;
    const { left, right } = displayEngines(r);
    return !hidden.has(left) && !hidden.has(right);
  }).length;
}

/**
 * One roster entry per oracle: its reports, checks, mismatches,
 * households, and the regions and programs it covers.
 */
export function groupByOracle(verification) {
  const byOracle = new Map();
  for (const report of verification) {
    const id = otherOracle(report);
    if (!byOracle.has(id)) {
      byOracle.set(id, {
        id,
        reports: [],
        checks: 0,
        mismatches: 0,
        households: 0,
        regions: new Set(),
        programs: new Set(),
      });
    }
    const entry = byOracle.get(id);
    entry.reports.push(report);
    const m = reportMetric(report);
    entry.checks += m.total;
    entry.mismatches += m.mismatches;
    entry.households += reportHouseholds(report);
    const meta = suiteMeta(report.suite);
    entry.regions.add(meta.region);
    entry.programs.add(`${meta.family}__${meta.jurisdiction}`);
  }
  return [...byOracle.values()];
}
