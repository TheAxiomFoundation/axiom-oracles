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
  let alarmCount = 0;
  for (const report of reports) {
    const left = report.engines?.left;
    const right = report.engines?.right;
    if (left !== "axiom" && right !== "axiom") continue;
    const other = left === "axiom" ? right : left;
    if (other !== otherOracle) continue;
    programs += 1;
    for (const agg of report.aggregates || []) {
      total += agg.comparison_count || 0;
      matched += (agg.comparison_count || 0) - (agg.mismatch_count || 0);
      weightedTotal += agg.comparison_weight || 0;
      weightedMatch += agg.match_weight || 0;
      alarmCount += (agg.quality_flags || []).length;
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
    alarmCount,
  };
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
        borderRadius: 10,
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
        className="mono"
        style={{
          fontSize: 34,
          fontWeight: 500,
          marginTop: 6,
          letterSpacing: "-0.01em",
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
      <div
        className="mono"
        style={{
          fontSize: 11.5,
          marginTop: 4,
          color: pair.alarmCount > 0 ? "var(--bad)" : "var(--ink-mute)",
        }}
      >
        {pair.programs} program{pair.programs === 1 ? "" : "s"}
        {pair.alarmCount > 0 && (
          <span style={{ marginLeft: 6 }}>
            · {pair.alarmCount} alarm{pair.alarmCount === 1 ? "" : "s"}
          </span>
        )}
      </div>
    </div>
  );
}

export default function OverviewHero({ reports, programCount }) {
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
  for (const p of pairs) {
    allMatched += p.matched;
    allTotal += p.total;
  }
  const headlineRate = allTotal > 0 ? (allMatched / allTotal) * 100 : null;

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div>
        <div className="section-eyebrow">Where Axiom stands today</div>
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: 14,
            flexWrap: "wrap",
            marginTop: 8,
          }}
        >
          <h1
            className="mono"
            style={{
              fontSize: 52,
              fontWeight: 500,
              letterSpacing: "-0.025em",
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
              maxWidth: 540,
              lineHeight: 1.55,
            }}
          >
            of {allTotal.toLocaleString()} comparisons agree across{" "}
            {programCount} program{programCount === 1 ? "" : "s"} and{" "}
            {pairs.length} oracle{pairs.length === 1 ? "" : "s"}. Each card
            below breaks the result down per program; expand a mismatch
            pattern to see why.
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
