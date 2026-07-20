/**
 * Program-level rollups shared by the status strip (census chips) and the
 * program table. One row per program (family × jurisdiction), aggregating
 * that program's verification runs.
 */

import {
  suiteMeta,
  reportMetric,
  nearMetric,
  isAxiomPair,
  otherOracle,
} from "./suites";

export function buildProgramRows(reports) {
  const programs = new Map();
  for (const report of reports || []) {
    if (!isAxiomPair(report)) continue;
    if (!(report.aggregates || []).length) continue;
    const meta = suiteMeta(report.suite);
    if (meta.kind === "diagnostic") continue;
    const key = `${meta.family}__${meta.jurisdiction}`;
    if (!programs.has(key)) {
      programs.set(key, {
        meta,
        runs: [],
        reports: [],
        total: 0,
        mismatches: 0,
      });
    }
    const entry = programs.get(key);
    entry.reports.push(report);
    // Prefer the household run's meta for the row label — a family that
    // has both (SSI) should read as the program, not its parameter probe.
    if (meta.kind === "household" && entry.meta.kind !== "household") {
      entry.meta = meta;
    }
    const metric = reportMetric(report);
    entry.runs.push({
      oracle: otherOracle(report),
      metric,
      near: nearMetric(report),
      kind: meta.kind,
      suite: report.suite,
    });
    // Program-level rate rolls up household runs only, so a parameter
    // probe never dilutes (or inflates) a measured population figure.
    if (meta.kind === "household") {
      entry.total += metric.total;
      entry.mismatches += metric.mismatches;
    } else {
      entry.paramTotal = (entry.paramTotal || 0) + metric.total;
      entry.paramMismatches =
        (entry.paramMismatches || 0) + metric.mismatches;
    }
  }
  return [...programs.values()];
}

/**
 * The row's verdict: the household roll-up when the program has one, the
 * parameter roll-up otherwise (the checks column already says which grain).
 */
export function rowVerdict(row) {
  if (row.total > 0) {
    return {
      rate: ((row.total - row.mismatches) / row.total) * 100,
      mismatches: row.mismatches,
    };
  }
  if ((row.paramTotal || 0) > 0) {
    return {
      rate:
        (((row.paramTotal || 0) - (row.paramMismatches || 0)) /
          row.paramTotal) *
        100,
      mismatches: row.paramMismatches || 0,
    };
  }
  return { rate: null, mismatches: 0 };
}

/** Match a (suite, concept, kind) mismatch bucket to its known-cause entry. */
export function causeFor(knownCauses, report, concept, kind) {
  const candidates = (knownCauses || []).filter(
    (c) => c.suite === report.suite && c.concept === concept && c.kind === kind,
  );
  return (
    candidates.find(
      (c) =>
        c.engines &&
        c.engines.left === report.engines?.left &&
        c.engines.right === report.engines?.right,
    ) || candidates.find((c) => !c.engines)
  );
}

/**
 * The health-signal count: disagreements with no explanation anywhere.
 * A report's own disposition layer (summary.dispositioned) is authoritative
 * only when a dispositions/<suite>.yaml actually backs it — without one the
 * block is a stub whose unexplained_count merely mirrors mismatch_count.
 * Those reports fall back to the gap ledger's mechanism: mismatch buckets
 * with no known-cause entry (counted from the possibly-slimmed mismatch
 * list, so a lower bound — the same one the ledger itself displays).
 */
export function countUnexplained(reports, knownCauses) {
  let total = 0;
  for (const report of reports || []) {
    if (!isAxiomPair(report)) continue;
    if (suiteMeta(report.suite).kind === "diagnostic") continue;
    const dispositioned = report.summary?.dispositioned;
    if (
      dispositioned?.dispositions_file &&
      dispositioned.unexplained_count != null
    ) {
      total += dispositioned.unexplained_count;
      continue;
    }
    const buckets = new Map();
    for (const m of report.mismatches || []) {
      const key = `${m.concept}::${m.kind}`;
      buckets.set(key, (buckets.get(key) || 0) + 1);
    }
    for (const [key, count] of buckets) {
      const [concept, kind] = key.split("::");
      if (!causeFor(knownCauses, report, concept, kind)) total += count;
    }
  }
  return total;
}

/** Region bucket for a coverage-overview program entry. */
export function coverageRegion(program) {
  if (program.jurisdiction === "UK") return "uk";
  if (program.jurisdiction === "BE") return "be";
  if (program.jurisdiction === "CAN") return "ca";
  return "us";
}
