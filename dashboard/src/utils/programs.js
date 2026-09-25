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
} from "./suites.js";
import { gatedUnexplainedBySuite } from "./unexplained.js";

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
 * The unexplained-gate count over these reports: the shared assessment (made
 * before the loader filters concepts), restricted to the publication gate's
 * domain and resolved per suite by maximum, exactly as
 * scripts/unexplained_ratchet.py counts. A report outside the gate counts 0.
 */
export function countUnexplained(reports, knownCauses) {
  const bySuite = gatedUnexplainedBySuite(reports, {
    known_causes: knownCauses,
    isDiagnostic: (suite) => suiteMeta(suite).kind === "diagnostic",
  });
  return Object.values(bySuite).reduce((total, count) => total + count, 0);
}

/** Region bucket for a coverage-overview program entry. */
export function coverageRegion(program) {
  if (program.jurisdiction === "UK") return "uk";
  if (program.jurisdiction === "BE") return "be";
  if (program.jurisdiction === "CAN") return "ca";
  return "us";
}
