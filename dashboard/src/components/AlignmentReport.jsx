"use client";

import React, { useState } from "react";
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

function ConceptMetric({ aggregate }) {
  const rate = aggregate.match_rate;
  const total = aggregate.comparison_count;
  const matched = total - aggregate.mismatch_count;
  const weighted = aggregate.weighted_match_rate;
  const tolerance = aggregate.tolerance;
  const isAmount = aggregate.comparison === "amount";
  // The descriptive label comes from the concept (e.g. "SNAP benefit
  // amount", "Child Tax Credit value", "Federal income tax liability").
  // Falls back to the kind tag only when no description is set.
  const title = aggregate.description || (isAmount ? "Amount" : "Eligibility");
  return (
    <div
      style={{
        flex: "1 1 200px",
        minWidth: 200,
        padding: "12px 14px",
        background: rate != null ? heatmapBg(rate) : "var(--paper-warm)",
        border: "1px solid var(--hairline)",
        borderRadius: 8,
      }}
    >
      <div
        style={{
          fontSize: 12,
          color: "var(--ink)",
          fontWeight: 500,
          lineHeight: 1.35,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {title}
      </div>
      <div
        className="mono"
        style={{
          fontSize: 9.5,
          letterSpacing: "0.08em",
          color: "var(--ink-soft)",
          textTransform: "uppercase",
          marginTop: 2,
        }}
      >
        {isAmount ? "Amount comparison" : "Eligibility comparison"}
      </div>
      <div
        className="mono"
        style={{
          fontSize: 22,
          fontWeight: 500,
          marginTop: 8,
          color: rate != null ? rateColor(rate) : "var(--ink-mute)",
          letterSpacing: "-0.01em",
          lineHeight: 1,
        }}
      >
        {rate != null ? formatPct(rate) : "—"}
      </div>
      <div
        className="mono"
        style={{ fontSize: 11, color: "var(--ink-mute)", marginTop: 6 }}
      >
        {matched.toLocaleString()}/{total.toLocaleString()}
        {isAmount && tolerance != null && (
          <span style={{ marginLeft: 6 }}>
            · ±{formatCurrency(tolerance)}
          </span>
        )}
        {weighted != null && Math.abs(weighted - rate) > 0.5 && (
          <span style={{ marginLeft: 6 }}>
            · {formatPct(weighted)} wtd
          </span>
        )}
      </div>
    </div>
  );
}

const FEDERAL_TAX_BREAKOUT = [
  {
    label: "Taxable income",
    suffixes: ["#taxable_income"],
    fallback: "Not compared in the current FIIT ECPS suite",
  },
  {
    label: "Tax before credits",
    suffixes: ["#tax_before_credits"],
    fallback: "Not compared in the current FIIT ECPS suite",
  },
  {
    label: "Federal income tax liability",
    suffixes: ["#liability"],
    fallback: "Not compared in the current FIIT ECPS suite",
  },
  {
    label: "Nonrefundable credits",
    suffixes: ["#nonrefundable_credits", "#non_refundable_credits"],
    fallback: "Not compared in the current FIIT ECPS suite",
  },
  {
    label: "Earned Income Tax Credit",
    suffixes: ["#eitc"],
    fallback: "Not compared in the current FIIT ECPS suite",
  },
  {
    label: "Child Tax Credit",
    suffixes: ["#ctc"],
    fallback: "Not compared in the current FIIT ECPS suite",
  },
  {
    label: "Child and Dependent Care Credit",
    suffixes: ["#cdcc", "#child_and_dependent_care_credit"],
    fallback: "Not compared in the current FIIT ECPS suite",
  },
  {
    label: "Alternative Minimum Tax",
    suffixes: ["#amt", "#alternative_minimum_tax"],
    fallback: "Not compared in the current FIIT ECPS suite",
  },
  {
    label: "Standard deduction",
    suffixes: ["#standard_deduction"],
    fallback: "Compared as a federal tax component",
  },
  {
    label: "Capital gain definitions",
    suffixes: ["#capital_gain"],
    fallback: "Compared as a federal tax component",
  },
  {
    label: "Payroll taxes",
    suffixes: [
      "#employee_oasdi",
      "#employee_medicare",
      "#employer_oasdi",
      "#employer_medicare",
    ],
    fallback: "Not compared in the current FIIT ECPS suite",
  },
];

function findBreakoutAggregates(aggregates, suffixes) {
  return aggregates.filter((aggregate) =>
    suffixes.some((suffix) => aggregate.concept?.endsWith(suffix)),
  );
}

function combineBreakoutAggregates(items) {
  if (!items.length) return null;
  let total = 0;
  let mismatches = 0;
  let weightedTotal = 0;
  let weightedMatches = 0;
  for (const item of items) {
    total += item.comparison_count || 0;
    mismatches += item.mismatch_count || 0;
    if (item.comparison_weight != null && item.match_weight != null) {
      weightedTotal += item.comparison_weight;
      weightedMatches += item.match_weight;
    }
  }
  const matched = total - mismatches;
  return {
    matched,
    total,
    mismatches,
    rate: total > 0 ? (matched / total) * 100 : null,
    weightedRate: weightedTotal > 0 ? (weightedMatches / weightedTotal) * 100 : null,
  };
}

function FederalTaxBreakout({ aggregates }) {
  const rows = FEDERAL_TAX_BREAKOUT.map((row) => {
    const matches = findBreakoutAggregates(aggregates, row.suffixes);
    return {
      ...row,
      metrics: combineBreakoutAggregates(matches),
      comparedCount: matches.length,
    };
  });

  return (
    <section
      style={{
        padding: "13px 14px",
        border: "1px solid var(--hairline-strong)",
        borderRadius: 8,
        background: "var(--paper-warm)",
      }}
    >
      <div
        className="section-eyebrow"
        style={{ fontSize: 10.5, marginBottom: 8 }}
      >
        Federal income tax pieces
      </div>
      <div style={{ overflowX: "auto" }}>
        <table
          className="mono"
          style={{
            width: "100%",
            minWidth: 640,
            borderCollapse: "collapse",
            fontSize: 11.5,
          }}
        >
          <thead>
            <tr style={{ color: "var(--ink-mute)" }}>
              <th style={{ textAlign: "left", padding: "0 8px 6px 0" }}>
                Piece
              </th>
              <th style={{ textAlign: "right", padding: "0 8px 6px" }}>
                Alignment
              </th>
              <th style={{ textAlign: "right", padding: "0 8px 6px" }}>
                Matched
              </th>
              <th style={{ textAlign: "right", padding: "0 8px 6px" }}>
                Mismatches
              </th>
              <th style={{ textAlign: "left", padding: "0 0 6px 8px" }}>
                Status
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const metrics = row.metrics;
              const compared = metrics && metrics.total > 0;
              return (
                <tr
                  key={row.label}
                  style={{ borderTop: "1px solid var(--hairline)" }}
                >
                  <td
                    style={{
                      padding: "7px 8px 7px 0",
                      color: "var(--ink)",
                      fontWeight: 600,
                    }}
                  >
                    {row.label}
                  </td>
                  <td
                    style={{
                      padding: "7px 8px",
                      textAlign: "right",
                      color: compared ? rateColor(metrics.rate) : "var(--ink-mute)",
                      fontWeight: compared ? 600 : 400,
                    }}
                  >
                    {compared ? formatPct(metrics.rate) : "—"}
                  </td>
                  <td
                    style={{
                      padding: "7px 8px",
                      textAlign: "right",
                      color: compared ? "var(--ink)" : "var(--ink-mute)",
                    }}
                  >
                    {compared
                      ? `${metrics.matched.toLocaleString()}/${metrics.total.toLocaleString()}`
                      : "—"}
                  </td>
                  <td
                    style={{
                      padding: "7px 8px",
                      textAlign: "right",
                      color:
                        compared && metrics.mismatches > 0
                          ? "var(--bad)"
                          : "var(--ink-mute)",
                    }}
                  >
                    {compared ? metrics.mismatches.toLocaleString() : "—"}
                  </td>
                  <td
                    style={{
                      padding: "7px 0 7px 8px",
                      color: compared ? "var(--ink-mute)" : "var(--ink-soft)",
                      whiteSpace: "normal",
                      lineHeight: 1.35,
                    }}
                  >
                    {compared
                      ? row.comparedCount > 1
                        ? `${row.comparedCount} payroll components compared`
                        : "Compared in current FIIT suite"
                      : row.fallback}
                    {compared &&
                      metrics.weightedRate != null &&
                      Math.abs(metrics.weightedRate - metrics.rate) > 0.5 && (
                        <> · {formatPct(metrics.weightedRate)} weighted</>
                      )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function HouseholdDetail({ row, mismatch }) {
  // Pull household-shaped fields out of the case metadata + the mismatch
  // payload. Anything that's null is hidden so the panel stays tight.
  const md = row?.metadata || {};
  const scope = md.scope || {};
  const hh = md.household_summary || {};
  const items = [
    [
      "household size",
      hh.household_size ??
        (Array.isArray(mismatch.ages) ? mismatch.ages.length : null),
    ],
    [
      "member ages",
      (hh.ages && hh.ages.join(", ")) || mismatch.ages?.join?.(", "),
    ],
    [
      "yearly earned income (total)",
      hh.yearly_earned_income_total != null
        ? "$" + hh.yearly_earned_income_total.toLocaleString()
        : mismatch.yearly_earned_income != null
          ? "$" + mismatch.yearly_earned_income.toLocaleString()
          : null,
    ],
    [
      "income per person",
      hh.yearly_earned_income_per_person?.length
        ? hh.yearly_earned_income_per_person
            .map((v) => "$" + v.toLocaleString())
            .join(", ")
        : null,
    ],
    [
      "pregnant member",
      hh.pregnant_member_present === true || mismatch.pregnant_head === true
        ? "yes"
        : null,
    ],
    ["county/geoid", scope.geoid],
    [
      "household weight",
      md.household_weight != null
        ? Math.round(md.household_weight).toLocaleString()
        : null,
    ],
    ["dataset", md.dataset],
    [
      "axiom inputs sent",
      md.axiom_input_records_count != null
        ? md.axiom_input_records_count.toLocaleString()
        : null,
    ],
    ["scenario", mismatch.scenario],
  ].filter(([_, v]) => v !== undefined && v !== null && v !== "");

  if (!items.length) {
    return (
      <div
        style={{
          padding: "8px 12px",
          fontSize: 11.5,
          color: "var(--ink-mute)",
          background: "var(--paper-warm)",
          borderTop: "1px dashed var(--hairline)",
        }}
      >
        No additional household context recorded for this case.
      </div>
    );
  }
  return (
    <div
      style={{
        padding: "8px 12px",
        background: "var(--paper-warm)",
        borderTop: "1px dashed var(--hairline)",
        fontSize: 11.5,
        display: "grid",
        gridTemplateColumns: "max-content 1fr",
        columnGap: 12,
        rowGap: 4,
      }}
    >
      {items.map(([k, v]) => (
        <span key={k} style={{ display: "contents" }}>
          <span
            className="mono"
            style={{ color: "var(--ink-mute)", whiteSpace: "nowrap" }}
          >
            {k}
          </span>
          <span style={{ color: "var(--ink)" }}>{String(v)}</span>
        </span>
      ))}
    </div>
  );
}

function MismatchCaseTable({ cases, casesById }) {
  const [openCase, setOpenCase] = useState(null);
  return (
    <div
      style={{
        marginTop: 10,
        background: "var(--paper-elevated)",
        border: "1px solid var(--hairline)",
        borderRadius: 6,
        maxHeight: 360,
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
            <th style={{ textAlign: "left", padding: "6px 10px", width: 24 }} />
            <th style={{ textAlign: "left", padding: "6px 10px" }}>case_id</th>
            <th style={{ textAlign: "right", padding: "6px 10px" }}>Axiom</th>
            <th style={{ textAlign: "right", padding: "6px 10px" }}>PE</th>
            <th style={{ textAlign: "right", padding: "6px 10px" }}>diff</th>
          </tr>
        </thead>
        <tbody>
          {cases.map((m, index) => {
            const key = `${m.case_id}-${m.concept}-${m.kind || "mismatch"}-${index}`;
            const isOpen = openCase === key;
            const row = casesById?.get(m.case_id);
            return (
              <React.Fragment key={key}>
                <tr
                  onClick={() => setOpenCase(isOpen ? null : key)}
                  style={{
                    borderTop: "1px solid var(--hairline)",
                    cursor: "pointer",
                    background: isOpen ? "var(--paper-warm)" : "transparent",
                  }}
                >
                  <td
                    style={{
                      padding: "5px 10px",
                      color: "var(--ink-mute)",
                      width: 24,
                    }}
                  >
                    {isOpen ? (
                      <IconChevronDown size={11} />
                    ) : (
                      <IconChevronRight size={11} />
                    )}
                  </td>
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
                {isOpen && (
                  <tr>
                    <td colSpan={5} style={{ padding: 0 }}>
                      <HouseholdDetail row={row} mismatch={m} />
                    </td>
                  </tr>
                )}
              </React.Fragment>
            );
          })}
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

function CauseDriverBreakdown({ cause, compact = false }) {
  const drivers = cause?.drivers || [];
  if (!drivers.length) return null;

  return (
    <div
      style={{
        marginTop: compact ? 8 : 10,
        display: "grid",
        gridTemplateColumns: compact
          ? "1fr"
          : "repeat(auto-fit, minmax(220px, 1fr))",
        gap: 8,
      }}
    >
      {drivers.map((driver) => (
        <div
          key={driver.label}
          style={{
            padding: compact ? "7px 9px" : "8px 10px",
            border: "1px solid var(--hairline)",
            borderRadius: 6,
            background: compact ? "var(--paper-elevated)" : "var(--paper-warm)",
          }}
        >
          <div
            className="mono"
            style={{
              fontSize: 10.5,
              color: "var(--ink)",
              fontWeight: 600,
              letterSpacing: "0.03em",
              textTransform: "uppercase",
            }}
          >
            {driver.label}
          </div>
          <div
            style={{
              fontSize: 11.5,
              color: "var(--ink-mute)",
              lineHeight: 1.45,
              marginTop: 4,
            }}
          >
            {driver.description}
          </div>
          {driver.evidence?.length > 0 && (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 3,
                marginTop: 6,
              }}
            >
              {driver.evidence.map((item) => (
                <div
                  key={item}
                  style={{
                    display: "flex",
                    gap: 6,
                    fontSize: 11,
                    lineHeight: 1.35,
                    color: "var(--ink-soft)",
                  }}
                >
                  <span className="mono" style={{ color: "var(--ink-mute)" }}>
                    -
                  </span>
                  <span>{item}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function MismatchPattern({ kind, cases, casesById, knownCause }) {
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
          alignItems: "flex-start",
          gap: 10,
          background: "transparent",
          border: 0,
          cursor: "pointer",
          padding: 0,
          textAlign: "left",
          fontFamily: "inherit",
        }}
      >
        <span style={{ color: "var(--ink-mute)", marginTop: 2 }}>
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
            marginTop: 1,
          }}
        >
          {cases.length}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, color: "var(--ink)" }}>
            {kindLabel(kind)}
          </div>
          {knownCause && (
            <div
              style={{
                fontSize: 11.5,
                marginTop: 3,
                color: "var(--ink-mute)",
              }}
            >
              {knownCause.label}
              {knownCause.issue_url && (
                <>
                  {" "}
                  <a
                    href={knownCause.issue_url}
                    target="_blank"
                    rel="noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="cite"
                  >
                    (track)
                  </a>
                </>
              )}
            </div>
          )}
        </div>
      </button>
      {expanded && (
        <>
          <div
            style={{
              fontSize: 12,
              color: "var(--ink-mute)",
              padding: "6px 0 0 60px",
              lineHeight: 1.5,
              maxWidth: 760,
            }}
          >
            {knownCause?.description || KIND_DESCRIPTION[kind]}
            <CauseDriverBreakdown cause={knownCause} />
          </div>
          <div style={{ paddingLeft: 60 }}>
            <MismatchCaseTable cases={cases} casesById={casesById} />
          </div>
        </>
      )}
    </div>
  );
}

// Human-readable display names for the suites we currently know about.
// Falls back to the suite slug if not listed.
const SUITE_TITLE = {
  "ca-snap-ecps": "California SNAP (CalFresh)",
  "ny-snap-ecps": "New York SNAP",
  "co-snap-ecps": "Colorado SNAP",
  "sc-snap-ecps": "South Carolina SNAP",
  "nc-snap-ecps": "North Carolina SNAP",
  "co-state-income-tax-ecps": "Colorado State Income Tax",
  "co-health-thresholds": "Colorado Medicaid / CHIP / BHP Thresholds",
  "co-tanf-coverage": "Colorado Works TANF",
  "fiit-ecps": "Federal Income Tax",
  "uk-universal-credit-efrs": "UK Universal Credit",
  "uk-tax-benefits-efrs": "UK Tax and Benefits",
  "nyc-income-tax-gap": "NYC Income Tax Components",
  "nyc-income-tax-ecps-diagnostic": "NYC Income Tax ECPS Diagnostic",
  "nyc-synthetic": "NYC Synthetic Scenarios",
};

const SUITE_JURISDICTION = {
  "ca-snap-ecps": "US-CA",
  "ny-snap-ecps": "US-NY",
  "co-snap-ecps": "US-CO",
  "sc-snap-ecps": "US-SC",
  "nc-snap-ecps": "US-NC",
  "co-state-income-tax-ecps": "US-CO",
  "co-health-thresholds": "US-CO",
  "co-tanf-coverage": "US-CO",
  "fiit-ecps": "US (federal)",
  "uk-universal-credit-efrs": "UK",
  "uk-tax-benefits-efrs": "UK",
  "nyc-income-tax-gap": "US-NY-NYC",
  "nyc-income-tax-ecps-diagnostic": "US-NY-NYC",
  "nyc-synthetic": "US-NY-NYC",
};

function reportTitle(report) {
  if (report.suite && SUITE_TITLE[report.suite]) return SUITE_TITLE[report.suite];
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

function reportJurisdiction(report) {
  return SUITE_JURISDICTION[report.suite] || null;
}

function reportHeadlineRate(aggregates) {
  let matched = 0;
  let total = 0;
  for (const a of aggregates) {
    total += a.comparison_count || 0;
    matched += (a.comparison_count || 0) - (a.mismatch_count || 0);
  }
  return total > 0 ? (matched / total) * 100 : null;
}

export default function AlignmentReport({ report, knownCauses = [] }) {
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

  // Index the report's case rows by case_id so the per-case drawer can
  // pull household metadata (county, weight, dataset) without extra fetch.
  const casesById = new Map();
  for (const c of report.cases || []) {
    if (c?.case_id) casesById.set(c.case_id, c);
  }

  // Quick lookup for known causes scoped to this report. Entries may carry an
  // optional `engines` pair to disambiguate reports that share a suite slug
  // (e.g. the two nyc-synthetic reports); engine-specific entries win, and
  // entries without `engines` apply to any report in the suite.
  const causeFor = (concept, kind) => {
    const candidates = knownCauses.filter(
      (c) =>
        c.suite === report.suite &&
        c.concept === concept &&
        c.kind === kind,
    );
    return (
      candidates.find(
        (c) =>
          c.engines &&
          c.engines.left === report.engines?.left &&
          c.engines.right === report.engines?.right,
      ) || candidates.find((c) => !c.engines)
    );
  };

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
          alignItems: "flex-start",
          gap: 16,
          flexWrap: "wrap",
        }}
      >
        <div style={{ flex: 1, minWidth: 220 }}>
          <h3
            style={{
              fontSize: 18,
              fontWeight: 500,
              margin: 0,
              color: "var(--ink)",
              letterSpacing: "-0.005em",
            }}
          >
            {reportTitle(report)}
          </h3>
          <div
            className="mono"
            style={{
              fontSize: 11,
              color: "var(--ink-mute)",
              marginTop: 4,
            }}
          >
            {reportEngines(report)}
            {reportJurisdiction(report) && (
              <>
                {" · "}
                {reportJurisdiction(report)}
              </>
            )}
            {" · "}
            {(report.case_count ?? aggregateCount).toLocaleString()} households
            {report.population && <> · {report.population}</>}
          </div>
        </div>
        {(() => {
          const headline = reportHeadlineRate(aggregates);
          if (headline == null) return null;
          return (
            <div style={{ textAlign: "right" }}>
              <div
                className="section-eyebrow"
                style={{ fontSize: 10, color: "var(--ink-mute)" }}
              >
                Combined match
              </div>
              <div
                className="mono"
                style={{
                  fontSize: 28,
                  fontWeight: 500,
                  marginTop: 2,
                  color: rateColor(headline),
                  lineHeight: 1,
                  letterSpacing: "-0.01em",
                }}
              >
                {formatPct(headline)}
              </div>
            </div>
          );
        })()}
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

      {report.suite === "fiit-ecps" && (
        <FederalTaxBreakout aggregates={aggregates} />
      )}

      {mismatchCount > 0 && (() => {
        // Collect top causes across all (concept, kind) buckets so the
        // user sees the dominant explanations up front rather than
        // hunting through chevrons.
        const causes = [];
        for (const agg of aggregates) {
          const byKind = byConcept.get(agg.concept);
          if (!byKind) continue;
          for (const [kind, cases] of byKind.entries()) {
            const cause = causeFor(agg.concept, kind);
            if (cause) {
              causes.push({
                cause,
                count: cases.length,
                kind,
                concept: agg.description || agg.concept,
              });
            }
          }
        }
        causes.sort((a, b) => b.count - a.count);
        if (causes.length === 0) return null;
        return (
          <div
            style={{
              padding: "14px 16px",
              background: "var(--paper-warm)",
              border: "1px solid var(--hairline-strong)",
              borderRadius: 8,
            }}
          >
            <div
              className="section-eyebrow"
              style={{ fontSize: 10.5, marginBottom: 8 }}
            >
              Why the {mismatchCount} mismatch{mismatchCount === 1 ? "" : "es"}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {causes.map((c, i) => (
                <div
                  key={`${c.concept}-${c.kind}-${i}`}
                  style={{ display: "flex", gap: 12, alignItems: "flex-start" }}
                >
                  <div
                    className="mono"
                    style={{
                      minWidth: 44,
                      textAlign: "right",
                      fontSize: 13,
                      color: "var(--bad)",
                      fontWeight: 600,
                      paddingTop: 1,
                    }}
                  >
                    {c.count}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: 13,
                        color: "var(--ink)",
                        fontWeight: 500,
                      }}
                    >
                      {c.cause.label}
                      {c.cause.issue_url && (
                        <>
                          {" "}
                          <a
                            href={c.cause.issue_url}
                            target="_blank"
                            rel="noreferrer"
                            className="cite"
                            style={{ fontSize: 11 }}
                          >
                            (track)
                          </a>
                        </>
                      )}
                    </div>
                    <div
                      style={{
                        fontSize: 11.5,
                        color: "var(--ink-mute)",
                        marginTop: 2,
                        lineHeight: 1.5,
                      }}
                    >
                      {c.cause.description}
                    </div>
                    <CauseDriverBreakdown cause={c.cause} compact />
                    <div
                      className="mono"
                      style={{
                        fontSize: 10.5,
                        color: "var(--ink-soft)",
                        marginTop: 4,
                        letterSpacing: "0.04em",
                        textTransform: "uppercase",
                      }}
                    >
                      {c.concept} · {kindLabel(c.kind)}
                      {c.cause.fix_owner && (
                        <> · owner: {c.cause.fix_owner}</>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })()}

      {mismatchCount > 0 && (
        <div>
          <div
            className="section-eyebrow"
            style={{ marginBottom: 4, fontSize: 10.5 }}
          >
            All disagreement patterns
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
                    casesById={casesById}
                    knownCause={causeFor(agg.concept, kind)}
                  />
                ))}
              </div>
            );
          })}
        </div>
      )}

      {aggregateCount === 0 && alarms.length > 0 && (
        <div
          style={{
            fontSize: 12.5,
            color: "var(--ink-mute)",
            padding: "6px 10px",
            background: "var(--paper-warm)",
            borderRadius: 6,
          }}
        >
          No case-level comparison is available for this encoded surface yet.
        </div>
      )}

      {mismatchCount === 0 && aggregateCount > 0 && (
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
