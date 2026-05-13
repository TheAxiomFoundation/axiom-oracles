"use client";

import { rateColor, rateBg } from "../utils/colors";
import { formatPct } from "../utils/format";

function MetricCard({ label, value, type, description }) {
  const isRate = type === "rate";
  const numericValue = parseFloat(value);

  return (
    <div className="card" style={{ padding: 20 }}>
      <div className="section-eyebrow">{label}</div>
      <div
        className="mono"
        style={{
          fontSize: 32,
          fontWeight: 400,
          marginTop: 10,
          letterSpacing: "-0.02em",
          color: isRate ? rateColor(numericValue) : "var(--ink)",
          lineHeight: 1,
        }}
      >
        {isRate ? formatPct(numericValue) : Number(value).toLocaleString()}
      </div>
      {isRate && (
        <div
          style={{
            height: 3,
            borderRadius: 999,
            marginTop: 14,
            background: rateBg(numericValue),
            overflow: "hidden",
          }}
        >
          <div
            style={{
              height: "100%",
              borderRadius: 999,
              width: `${Math.min(numericValue, 100)}%`,
              background: rateColor(numericValue),
              transition: "width 600ms ease",
            }}
          />
        </div>
      )}
      {description && (
        <div
          style={{
            fontSize: 12.5,
            marginTop: 10,
            color: "var(--ink-mute)",
            lineHeight: 1.45,
          }}
        >
          {description}
        </div>
      )}
    </div>
  );
}

export default function MetricsRow({ summary, programCount }) {
  if (!summary) return null;

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
      <MetricCard
        label="Programs encoded"
        value={programCount ?? summary.totalConcepts}
        type="count"
      />
      <MetricCard
        label="Oracles"
        value={summary.totalOracles}
        type="count"
      />
      <MetricCard
        label="Households"
        value={summary.totalCases}
        type="count"
      />
      <MetricCard
        label="Overall agreement"
        value={summary.overallMatchRate.toFixed(1)}
        type="rate"
      />
    </div>
  );
}
