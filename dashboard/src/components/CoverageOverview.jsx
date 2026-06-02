"use client";

import { formatPct } from "../utils/format";
import { rateColor, heatmapBg } from "../utils/colors";

const SUITE_META = {
  "al-snap-ecps": {
    program: "snap",
    jurisdiction: "AL",
    label: "Alabama SNAP",
    order: 20,
  },
  "ca-snap-ecps": {
    program: "snap",
    jurisdiction: "CA",
    label: "California SNAP",
    order: 30,
  },
  "ma-snap-ecps": {
    program: "snap",
    jurisdiction: "MA",
    label: "Massachusetts SNAP",
    order: 40,
  },
  "ny-snap-ecps": {
    program: "snap",
    jurisdiction: "NY",
    label: "New York SNAP",
    order: 50,
  },
  "tn-snap-ecps": {
    program: "snap",
    jurisdiction: "TN",
    label: "Tennessee SNAP",
    order: 60,
  },
  "co-snap-ecps": {
    program: "snap",
    jurisdiction: "CO",
    label: "Colorado SNAP",
    order: 70,
  },
  "sc-snap-ecps": {
    program: "snap",
    jurisdiction: "SC",
    label: "South Carolina SNAP",
    order: 80,
  },
  "nc-snap-ecps": {
    program: "snap",
    jurisdiction: "NC",
    label: "North Carolina SNAP",
    order: 90,
  },
  "co-state-income-tax-ecps": {
    program: "state_income_tax",
    jurisdiction: "CO",
    label: "Colorado income tax",
    order: 100,
  },
  "co-health-thresholds": {
    program: "medicaid_chip_bhp_thresholds",
    jurisdiction: "CO",
    label: "Colorado Medicaid / CHIP / BHP thresholds",
    order: 110,
  },
  "co-tanf-coverage": {
    program: "tanf",
    jurisdiction: "CO",
    label: "Colorado Works TANF",
    order: 120,
  },
  "fiit-ecps": {
    program: "federal_income_tax",
    jurisdiction: "US",
    label: "Federal income tax",
    order: 10,
  },
};

function titleFromId(id) {
  return String(id || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function statusLabel(status) {
  const labels = {
    complete: "Complete",
    executable: "Executable",
    parameter: "Parameter check",
    coverageOnly: "Coverage only",
    inProgress: "In progress",
    partial: "Partial",
    notStarted: "Not started",
  };
  return labels[status] || titleFromId(status);
}

function statusClass(status) {
  if (status === "complete" || status === "executable" || status === "parameter") {
    return "badge badge-good";
  }
  if (status === "inProgress" || status === "partial" || status === "coverageOnly") {
    return "badge badge-warn";
  }
  return "badge badge-bad";
}

function metricFor(report, comparison) {
  const items = (report.aggregates || []).filter((agg) => agg.comparison === comparison);
  if (!items.length) return null;
  const total = items.reduce((sum, agg) => sum + (agg.comparison_count || 0), 0);
  const mismatches = items.reduce((sum, agg) => sum + (agg.mismatch_count || 0), 0);
  const matched = total - mismatches;
  return {
    matched,
    total,
    mismatches,
    rate: total > 0 ? (matched / total) * 100 : null,
  };
}

function lookupProgram(programs, predicate) {
  return (programs || []).find(predicate) || null;
}

function buildRows(reports, coverageOverview) {
  const pePrograms = coverageOverview?.policyengine?.programs || [];
  const axiomPrograms = coverageOverview?.axiom?.programs || [];

  return (reports || [])
    .filter((report) => SUITE_META[report.suite])
    .filter((report) => report.engines?.left === "axiom" || report.engines?.right === "axiom")
    .map((report) => {
      const meta = SUITE_META[report.suite];
      const peProgram = lookupProgram(pePrograms, (p) => p.id === meta.program);
      const axiomProgram = lookupProgram(
        axiomPrograms,
        (p) => p.program === meta.program && p.jurisdiction === meta.jurisdiction,
      );
      return {
        ...meta,
        suite: report.suite,
        report,
        peProgram,
        axiomProgram,
        eligibility: metricFor(report, "eligibility"),
        amount: metricFor(report, "amount"),
        hasReportSurface:
          (report.summary?.alarms || []).length > 0 ||
          (report.aggregates || []).some((agg) => (agg.quality_flags || []).length > 0),
      };
    })
    .filter((row) => row.eligibility || row.amount || row.hasReportSurface)
    .sort((a, b) => a.order - b.order || a.label.localeCompare(b.label));
}

function AlignmentCell({ metric, label }) {
  if (!metric) {
    return (
      <span className="mono" style={{ color: "var(--ink-mute)", fontSize: 12 }}>
        Not compared
      </span>
    );
  }
  return (
    <div
      style={{
        display: "inline-flex",
        flexDirection: "column",
        minWidth: 116,
        padding: "8px 10px",
        border: "1px solid var(--hairline)",
        borderRadius: 8,
        background: heatmapBg(metric.rate),
      }}
    >
      <span
        className="mono"
        style={{
          fontSize: 18,
          lineHeight: 1,
          color: rateColor(metric.rate),
          fontWeight: 500,
        }}
      >
        {formatPct(metric.rate, 1)}
      </span>
      <span
        className="mono"
        style={{ color: "var(--ink-mute)", fontSize: 10.5, marginTop: 5 }}
      >
        {metric.matched.toLocaleString()}/{metric.total.toLocaleString()} {label}
      </span>
    </div>
  );
}

function SourceLine({ program }) {
  if (!program?.source) return null;
  return (
    <div
      className="mono"
      style={{
        marginTop: 5,
        color: "var(--ink-mute)",
        fontSize: 10.5,
        overflowWrap: "anywhere",
      }}
    >
      {program.source}
    </div>
  );
}

function GapText({ gaps }) {
  if (!gaps?.length) {
    return <span style={{ color: "var(--ink-mute)" }}>No current gap called out.</span>;
  }
  return (
    <span>
      {gaps.map((gap, index) => (
        <span key={gap}>
          {index > 0 ? "; " : ""}
          {gap}
        </span>
      ))}
    </span>
  );
}

export default function CoverageOverview({ reports, coverageOverview }) {
  const rows = buildRows(reports, coverageOverview);
  if (!rows.length) return null;

  const axiomExecutable = rows.filter((row) => row.axiomProgram?.status === "executable").length;
  const peComplete = rows.filter((row) => row.peProgram?.status === "complete").length;
  const compared = rows.length;

  return (
    <section className="card-flat">
      <div className="section-head">
        <div>
          <div className="section-eyebrow">Coverage and measured alignment</div>
          <div className="section-title">
            PolicyEngine coverage is shown separately from Axiom executable coverage.
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <span className="badge badge-good">{peComplete}/{compared} PE complete</span>
          <span className="badge badge-good">{axiomExecutable}/{compared} Axiom executable</span>
        </div>
      </div>

      <div style={{ overflowX: "auto" }}>
        <table className="coverage-table">
          <thead>
            <tr>
              <th>Area</th>
              <th>Axiom coverage</th>
              <th>PolicyEngine coverage</th>
              <th>Eligibility alignment</th>
              <th>Amount alignment</th>
              <th>Current gaps</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.suite}>
                <td>
                  <div style={{ fontWeight: 600, color: "var(--ink)" }}>{row.label}</div>
                  <div className="mono" style={{ color: "var(--ink-mute)", fontSize: 11 }}>
                    {row.suite}
                  </div>
                </td>
                <td>
                  <span className={statusClass(row.axiomProgram?.status)}>
                    {statusLabel(row.axiomProgram?.status || "notStarted")}
                  </span>
                  <SourceLine program={row.axiomProgram} />
                </td>
                <td>
                  <span className={statusClass(row.peProgram?.status)}>
                    {statusLabel(row.peProgram?.status || "notStarted")}
                  </span>
                  {row.peProgram?.notes && (
                    <div style={{ marginTop: 5, color: "var(--ink-mute)", fontSize: 11.5 }}>
                      {row.peProgram.notes}
                    </div>
                  )}
                </td>
                <td>
                  <AlignmentCell metric={row.eligibility} label="match" />
                </td>
                <td>
                  <AlignmentCell metric={row.amount} label="match" />
                </td>
                <td style={{ minWidth: 220 }}>
                  <GapText gaps={row.axiomProgram?.known_non_tanf_gaps} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
