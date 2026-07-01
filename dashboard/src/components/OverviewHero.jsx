"use client";

import { engineLabel, formatPct } from "../utils/format";
import { rateColor } from "../utils/colors";
import { suiteKind, reportMetric } from "../utils/suites";

/**
 * The page opens with a sentence, not a widget: what was checked, against
 * whom, and how often the answers agreed. Only household-level verification
 * runs count toward the headline; diagnostic instrumentation runs are
 * disclosed separately so they can't flatter or sink the number.
 */

function isAxiomPair(report) {
  return report.engines?.left === "axiom" || report.engines?.right === "axiom";
}

function otherEngine(report) {
  return report.engines?.left === "axiom"
    ? report.engines?.right
    : report.engines?.left;
}

function compactCount(n) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} million`;
  if (n >= 10_000) return `${Math.round(n / 1000).toLocaleString()},000`;
  return n.toLocaleString();
}

function Stat({ value, label }) {
  return (
    <div className="hero-stat">
      <span className="mono hero-stat-value">{value}</span>
      <span className="mono hero-stat-label">{label}</span>
    </div>
  );
}

export default function OverviewHero({ reports }) {
  const headlineReports = (reports || []).filter(
    (r) =>
      isAxiomPair(r) &&
      suiteKind(r.suite) === "household" &&
      (r.aggregates || []).length > 0,
  );

  let matched = 0;
  let total = 0;
  let households = 0;
  const oracles = new Set();
  for (const report of headlineReports) {
    const m = reportMetric(report);
    matched += m.matched;
    total += m.total;
    households += report.case_count || 0;
    const other = otherEngine(report);
    if (other) oracles.add(other);
  }
  const rate = total > 0 ? (matched / total) * 100 : null;
  const mismatches = total - matched;

  const diagnosticCount = (reports || []).filter(
    (r) => isAxiomPair(r) && suiteKind(r.suite) === "diagnostic",
  ).length;

  const oracleNames = [...oracles].map(engineLabel);
  const oracleText =
    oracleNames.length <= 1
      ? oracleNames[0] || "its oracles"
      : `${oracleNames.slice(0, -1).join(", ")} and ${oracleNames.at(-1)}`;

  return (
    <section className="hero">
      <div className="section-eyebrow">Verification status</div>
      {rate != null ? (
        <h1 className="hero-thesis">
          Axiom and {oracleText} agree on{" "}
          <em style={{ color: rateColor(rate) }}>{formatPct(rate, 2)}</em> of{" "}
          <em>{compactCount(total)}</em> checks across{" "}
          <em>{headlineReports.length}</em> verified program runs.
        </h1>
      ) : (
        <h1 className="hero-thesis">No verified program runs yet.</h1>
      )}
      <p className="hero-sub">
        Each check asks two independent rule engines the same question about a
        real survey household — is it eligible, and for how much — and records
        whether the answers match. Every disagreement below is traced to a
        cause.
      </p>
      <div className="hero-stats">
        <Stat value={households.toLocaleString()} label="households compared" />
        <Stat
          value={mismatches.toLocaleString()}
          label="open disagreements"
        />
        <Stat
          value={headlineReports.length.toLocaleString()}
          label="verified runs"
        />
        {diagnosticCount > 0 && (
          <Stat
            value={diagnosticCount.toLocaleString()}
            label="diagnostic runs (not in headline)"
          />
        )}
      </div>
    </section>
  );
}
