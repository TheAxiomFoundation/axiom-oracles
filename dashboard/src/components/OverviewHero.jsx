"use client";

import { engineLabel, formatPct } from "../utils/format";
import { rateColor, heatmapBg } from "../utils/colors";

/**
 * Top-of-page summary: where Axiom stands today against every oracle it
 * has been compared with. One headline rate per (Axiom, other-oracle)
 * pair, summed across every program with comparison data.
 *
 * The aim is to answer the first question a reviewer should have on
 * load: "how well does Axiom track the oracles we trust?"
 */

function pairMetric(reports, otherOracle) {
  let matched = 0;
  let total = 0;
  let weightedMatch = 0;
  let weightedTotal = 0;
  let programs = 0;
  let mismatches = 0;
  for (const report of reports) {
    const left = report.engines?.left;
    const right = report.engines?.right;
    if (left !== "axiom" && right !== "axiom") continue;
    const other = left === "axiom" ? right : left;
    if (other !== otherOracle) continue;
    const reportTotal = (report.aggregates || []).reduce(
      (sum, agg) => sum + (agg.comparison_count || 0),
      0,
    );
    if (reportTotal > 0) programs += 1;
    for (const agg of report.aggregates || []) {
      total += agg.comparison_count || 0;
      const aggregateMismatches = agg.mismatch_count || 0;
      matched += (agg.comparison_count || 0) - aggregateMismatches;
      mismatches += aggregateMismatches;
      weightedTotal += agg.comparison_weight || 0;
      weightedMatch += agg.match_weight || 0;
    }
  }
  return {
    other: otherOracle,
    matched,
    total,
    rate: total > 0 ? (matched / total) * 100 : null,
    weightedRate:
      weightedTotal > 0 ? (weightedMatch / weightedTotal) * 100 : null,
    programs,
    mismatches,
  };
}

function SummaryStat({ label, value }) {
  return (
    <div
      style={{
        padding: "8px 10px",
        border: "1px solid var(--hairline)",
        borderRadius: 8,
        background: "var(--paper-elevated)",
        minWidth: 128,
      }}
    >
      <div
        className="mono"
        style={{
          fontSize: 15,
          lineHeight: 1,
          color: "var(--ink)",
          fontWeight: 500,
          letterSpacing: 0,
        }}
      >
        {value}
      </div>
      <div
        className="mono"
        style={{
          fontSize: 10.5,
          color: "var(--ink-mute)",
          marginTop: 5,
          textTransform: "uppercase",
          letterSpacing: "0.04em",
        }}
      >
        {label}
      </div>
    </div>
  );
}

function PairCard({ pair }) {
  return (
    <div
      style={{
        flex: 1,
        minWidth: 240,
        padding: "18px 20px",
        background:
          pair.rate != null ? heatmapBg(pair.rate) : "var(--paper-warm)",
        border: "1px solid var(--hairline)",
        borderRadius: 8,
      }}
    >
      <div
        className="section-eyebrow"
        style={{
          fontSize: 10.5,
          letterSpacing: "0.1em",
          color: "var(--ink-mute)",
        }}
      >
        Axiom vs {engineLabel(pair.other)}
      </div>
      <div
        className="mono hero-pair-figure"
        style={{
          fontSize: 34,
          fontWeight: 500,
          marginTop: 6,
          letterSpacing: 0,
          color: pair.rate != null ? rateColor(pair.rate) : "var(--ink-mute)",
          lineHeight: 1,
        }}
      >
        {pair.rate != null ? formatPct(pair.rate) : "—"}
      </div>
      <div
        className="mono"
        style={{
          fontSize: 11.5,
          color: "var(--ink-mute)",
          marginTop: 8,
        }}
      >
        {pair.matched.toLocaleString()}/{pair.total.toLocaleString()}{" "}
        comparisons match
        {pair.weightedRate != null && Math.abs(pair.weightedRate - pair.rate) > 0.5 && (
          <span style={{ marginLeft: 6 }}>
            · {formatPct(pair.weightedRate)} weighted
          </span>
        )}
      </div>
    </div>
  );
}

export default function OverviewHero({ reports }) {
  const others = new Set();
  for (const report of reports) {
    const left = report.engines?.left;
    const right = report.engines?.right;
    if (left === "axiom" && right) others.add(right);
    if (right === "axiom" && left) others.add(left);
  }
  const pairs = [...others]
    .map((other) => pairMetric(reports, other))
    .filter((p) => p.total > 0)
    .sort((a, b) => (b.total || 0) - (a.total || 0));

  // Roll-up headline: total comparisons + match rate across every pair.
  let allMatched = 0;
  let allTotal = 0;
  let allMismatches = 0;
  for (const p of pairs) {
    allMatched += p.matched;
    allTotal += p.total;
    allMismatches += p.mismatches;
  }
  const headlineRate = allTotal > 0 ? (allMatched / allTotal) * 100 : null;
  const comparisonSuiteCount = pairs.reduce(
    (sum, pair) => sum + pair.programs,
    0,
  );

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1fr)",
          gap: 14,
        }}
      >
        <div className="section-eyebrow">Where Axiom stands today</div>
        <div
          style={{
            display: "flex",
            alignItems: "flex-end",
            gap: 20,
            flexWrap: "wrap",
          }}
        >
          <div>
            <h1
              className="mono hero-figure"
              style={{
                fontSize: 52,
                fontWeight: 500,
                letterSpacing: 0,
                margin: 0,
                color:
                  headlineRate != null ? rateColor(headlineRate) : "var(--ink)",
                lineHeight: 1,
              }}
            >
              {headlineRate != null ? formatPct(headlineRate, 1) : "—"}
            </h1>
            <div
              style={{
                fontSize: 14,
                color: "var(--ink-mute)",
                maxWidth: 620,
                lineHeight: 1.5,
                marginTop: 8,
              }}
            >
              Agreement across live Axiom comparisons. Program cards below show
              the breakdown; mismatch groups explain the known residuals.
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <SummaryStat
              label="comparisons"
              value={allTotal.toLocaleString()}
            />
            <SummaryStat
              label="comparison suites"
              value={comparisonSuiteCount.toLocaleString()}
            />
            <SummaryStat
              label="mismatches"
              value={allMismatches.toLocaleString()}
            />
            <SummaryStat
              label="oracle pairs"
              value={pairs.length.toLocaleString()}
            />
          </div>
        </div>
      </div>

      {pairs.length > 0 && (
        <div
          style={{
            display: "flex",
            gap: 12,
            flexWrap: "wrap",
          }}
        >
          {pairs.map((pair) => (
            <PairCard key={pair.other} pair={pair} />
          ))}
        </div>
      )}
    </section>
  );
}
