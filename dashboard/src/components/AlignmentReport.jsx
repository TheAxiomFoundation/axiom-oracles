"use client";

import { useState } from "react";
import { IconChevronRight, IconChevronDown } from "@tabler/icons-react";
import { formatPct, formatCurrency, engineLabel } from "../utils/format";
import { rateColor, heatmapBg } from "../utils/colors";

/**
 * Per-report alignment card.
 *
 * Each report becomes one card. Inside, every concept the report compared
 * (e.g. eligibility + benefit amount) gets its own metric block, and
 * mismatches roll up into named patterns so reviewers can attribute a
 * disagreement to a structural cause (e.g. "PE eligible, Axiom not — 17
 * cases") instead of skimming individual rows.
 *
 * The "show cases" drawer lists individual mismatches per pattern so you
 * can take a concrete case_id into a triage script.
 */

const KIND_LABEL = {
  eligibility_right_only: "PE eligible, Axiom not",
  eligibility_left_only: "Axiom eligible, PE not",
  amount_difference: "Amount differs",
  missing_left: "Axiom returned no value",
  missing_right: "PE returned no value",
  missing_both: "Both engines missing",
};

const KIND_DESCRIPTION = {
  eligibility_right_only:
    "Households PolicyEngine marks eligible that Axiom rejects. Usually points to an unencoded eligibility path (state BBCE, categorical exemption, …).",
  eligibility_left_only:
    "Households Axiom marks eligible that PolicyEngine rejects. Often Axiom missing a disqualifying condition the rulespec hasn't encoded yet.",
  amount_difference:
    "Both engines agree on eligibility, but the dollar amount diverges beyond tolerance.",
  missing_left:
    "Axiom didn't produce a value for this case — typically a missing input or formula that references an undeclared identifier.",
  missing_right: "PolicyEngine didn't produce a value.",
  missing_both: "Neither engine could evaluate the case.",
};

function kindLabel(kind) {
  return KIND_LABEL[kind] || kind;
}

function ConceptMetric({ aggregate, mismatchCount }) {
  const rate = aggregate.match_rate;
  const total = aggregate.comparison_count;
  const matched = total - aggregate.mismatch_count;
  const weighted = aggregate.weighted_match_rate;
  const tolerance = aggregate.tolerance;
  const isAmount = aggregate.comparison === "amount";
  return (
    <div
      style={{
        flex: 1,
        minWidth: 220,
        padding: "14px 16px",
        background: rate != null ? heatmapBg(rate) : "var(--paper-warm)",
        border: "1px solid var(--hairline)",
        borderRadius: 8,
      }}
    >
      <div
        className="section-eyebrow"
        style={{ fontSize: 10.5, letterSpacing: "0.1em" }}
      >
        {isAmount ? "Benefit amount" : "Eligibility"}
        {isAmount && tolerance != null ? (
          <span style={{ marginLeft: 6, color: "var(--ink-mute)" }}>
            (±{formatCurrency(tolerance)})
          </span>
        ) : null}
      </div>
      <div
        className="mono"
        style={{
          fontSize: 22,
          fontWeight: 500,
          marginTop: 6,
          color: rate != null ? rateColor(rate) : "var(--ink-mute)",
        }}
      >
        {rate != null ? formatPct(rate) : "—"}
      </div>
      <div
        className="mono"
        style={{ fontSize: 11.5, color: "var(--ink-mute)", marginTop: 4 }}
      >
        {matched.toLocaleString()}/{total.toLocaleString()} cases match
        {weighted != null && weighted !== rate && (
          <span style={{ marginLeft: 8 }}>
            · {formatPct(weighted)} weighted
          </span>
        )}
      </div>
    </div>
  );
}

function MismatchCaseTable({ cases }) {
  return (
    <div
      style={{
        marginTop: 10,
        background: "var(--paper-elevated)",
        border: "1px solid var(--hairline)",
        borderRadius: 6,
        maxHeight: 280,
        overflow: "auto",
      }}
    >
      <table
        className="mono"
        style={{
          width: "100%",
          fontSize: 11.5,
          borderCollapse: "collapse",
        }}
      >
        <thead>
          <tr style={{ background: "var(--paper-warm)" }}>
            <th style={{ textAlign: "left", padding: "6px 10px" }}>case_id</th>
            <th style={{ textAlign: "right", padding: "6px 10px" }}>Axiom</th>
            <th style={{ textAlign: "right", padding: "6px 10px" }}>PE</th>
            <th style={{ textAlign: "right", padding: "6px 10px" }}>diff</th>
          </tr>
        </thead>
        <tbody>
          {cases.map((m) => (
            <tr
              key={`${m.case_id}-${m.concept}`}
              style={{ borderTop: "1px solid var(--hairline)" }}
            >
              <td style={{ padding: "5px 10px", color: "var(--ink-mute)" }}>
                {m.case_id}
              </td>
              <td style={{ padding: "5px 10px", textAlign: "right" }}>
                {formatValue(m.left)}
              </td>
              <td style={{ padding: "5px 10px", textAlign: "right" }}>
                {formatValue(m.right)}
              </td>
              <td style={{ padding: "5px 10px", textAlign: "right" }}>
                {m.difference != null
                  ? (m.difference >= 0 ? "+" : "") +
                    m.difference.toFixed(2)
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatValue(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "number") return v.toFixed(2);
  return String(v);
}

function MismatchPattern({ kind, cases, totalForConcept }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div
      style={{
        borderTop: "1px solid var(--hairline)",
        padding: "10px 0",
      }}
    >
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          gap: 10,
          background: "transparent",
          border: 0,
          cursor: "pointer",
          padding: 0,
          textAlign: "left",
          fontFamily: "inherit",
        }}
      >
        <span style={{ color: "var(--ink-mute)" }}>
          {expanded ? (
            <IconChevronDown size={14} />
          ) : (
            <IconChevronRight size={14} />
          )}
        </span>
        <span
          className="mono"
          style={{
            fontSize: 12,
            color: "var(--bad)",
            minWidth: 36,
            textAlign: "right",
            fontWeight: 600,
          }}
        >
          {cases.length}
        </span>
        <span style={{ fontSize: 13, color: "var(--ink)" }}>
          {kindLabel(kind)}
        </span>
      </button>
      {expanded && (
        <>
          <div
            style={{
              fontSize: 12,
              color: "var(--ink-mute)",
              padding: "4px 0 0 24px",
              lineHeight: 1.5,
              maxWidth: 640,
            }}
          >
            {KIND_DESCRIPTION[kind]}
          </div>
          <div style={{ paddingLeft: 24 }}>
            <MismatchCaseTable cases={cases} />
          </div>
        </>
      )}
    </div>
  );
}

function reportTitle(report) {
  if (report.suite) return report.suite;
  const left = engineLabel(report.engines?.left);
  const right = engineLabel(report.engines?.right);
  return `${left} vs ${right}`;
}

function reportEngines(report) {
  const left = engineLabel(report.engines?.left);
  const right = engineLabel(report.engines?.right);
  return `${left} vs ${right}`;
}

export default function AlignmentReport({ report }) {
  const aggregates = report.aggregates || [];
  const mismatches = report.mismatches || [];

  // Bucket mismatches per concept then per kind.
  const byConcept = new Map();
  for (const m of mismatches) {
    if (!byConcept.has(m.concept)) byConcept.set(m.concept, new Map());
    const byKind = byConcept.get(m.concept);
    if (!byKind.has(m.kind)) byKind.set(m.kind, []);
    byKind.get(m.kind).push(m);
  }

  const aggregateCount = aggregates.reduce(
    (sum, a) => sum + (a.comparison_count || 0),
    0,
  );
  const mismatchCount = aggregates.reduce(
    (sum, a) => sum + (a.mismatch_count || 0),
    0,
  );
  const alarms = report.summary?.alarms || [];

  return (
    <div
      style={{
        background: "var(--paper-elevated)",
        border: "1px solid var(--hairline)",
        borderRadius: 12,
        padding: "18px 20px",
        display: "flex",
        flexDirection: "column",
        gap: 14,
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <h3
          style={{
            fontSize: 16,
            fontWeight: 500,
            margin: 0,
            color: "var(--ink)",
          }}
        >
          {reportTitle(report)}
        </h3>
        <span
          className="mono"
          style={{ fontSize: 11, color: "var(--ink-mute)" }}
        >
          {reportEngines(report)}
        </span>
        <span style={{ flex: 1 }} />
        <span
          className="mono"
          style={{ fontSize: 11, color: "var(--ink-mute)" }}
        >
          {report.case_count?.toLocaleString() || aggregateCount.toLocaleString()}{" "}
          households
        </span>
      </header>

      {alarms.length > 0 && (
        <div
          style={{
            padding: "8px 12px",
            background: "rgba(180, 35, 24, 0.06)",
            border: "1px solid var(--bad)",
            borderRadius: 6,
            fontSize: 12,
            color: "var(--bad)",
            display: "flex",
            flexDirection: "column",
            gap: 4,
          }}
        >
          {alarms.map((a, i) => (
            <div key={i}>
              <span className="mono" style={{ fontWeight: 600 }}>
                {a.code || "alarm"}
              </span>
              <span style={{ marginLeft: 8, color: "var(--ink-mute)" }}>
                {a.message}
              </span>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        {aggregates.map((agg) => (
          <ConceptMetric
            key={agg.concept}
            aggregate={agg}
            mismatchCount={agg.mismatch_count}
          />
        ))}
      </div>

      {mismatchCount > 0 && (
        <div>
          <div
            className="section-eyebrow"
            style={{ marginBottom: 4, fontSize: 10.5 }}
          >
            Disagreement patterns
          </div>
          {aggregates.map((agg) => {
            const byKind = byConcept.get(agg.concept);
            if (!byKind || byKind.size === 0) return null;
            return (
              <div key={agg.concept} style={{ marginTop: 8 }}>
                <div
                  style={{
                    fontSize: 12,
                    color: "var(--ink-mute)",
                    marginBottom: 2,
                  }}
                >
                  {agg.description || agg.concept}
                </div>
                {[...byKind.entries()].map(([kind, cases]) => (
                  <MismatchPattern
                    key={kind}
                    kind={kind}
                    cases={cases}
                    totalForConcept={agg.comparison_count}
                  />
                ))}
              </div>
            );
          })}
        </div>
      )}

      {mismatchCount === 0 && (
        <div
          style={{
            fontSize: 12.5,
            color: "var(--good)",
            padding: "6px 10px",
            background: "rgba(6, 95, 70, 0.05)",
            borderRadius: 6,
          }}
        >
          All sampled cases agree on every compared concept.
        </div>
      )}
    </div>
  );
}
