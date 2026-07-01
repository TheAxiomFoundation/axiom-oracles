"use client";

import { formatPct } from "../utils/format";
import { rateColor, heatmapBg } from "../utils/colors";
import { suiteMeta } from "../utils/suites";

// Adapt the central suite metadata to the field names this table was built
// around (`program` here means program family).
function metaFor(suite) {
  const m = suiteMeta(suite);
  return {
    program: m.family,
    jurisdiction: m.jurisdiction,
    label: m.label,
    order: m.order,
  };
}

function titleFromId(id) {
  return String(id || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function statusLabel(status) {
  const labels = {
    complete: "Complete",
    executable: "Executable",
    executableCoverage: "Executable coverage",
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
  if (
    status === "inProgress" ||
    status === "partial" ||
    status === "coverageOnly" ||
    status === "executableCoverage"
  ) {
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

function measurementNote(row) {
  if (row.suite === "co-snap-ecps") {
    return "Measured by the encoder-backed CO SNAP report; the axiom-programs wrapper now has generic output/input mapping smoke-tested, but is not yet the dashboard comparison path.";
  }
  if (row.axiomProgram?.status === "coverageOnly") {
    return "Coverage-only surface; not a measured alignment run.";
  }
  if (row.axiomProgram?.status === "executableCoverage") {
    return "Executable Axiom package; PE comparison is still coverage-only, not a measured alignment run.";
  }
  if (row.axiomProgram?.status === "parameter") {
    return "Parameter check; not end-to-end household eligibility.";
  }
  if (row.report?.population === "enhanced-cps") {
    return "Measured over the Enhanced CPS slice for this jurisdiction.";
  }
  return null;
}

function lookupProgram(programs, predicate) {
  return (programs || []).find(predicate) || null;
}

function regionForSuite(suite) {
  return String(suite || "").startsWith("uk-") ? "uk" : "us";
}

function buildRows(reports, coverageOverview, jurisdictionFilter = "all") {
  const pePrograms = coverageOverview?.policyengine?.programs || [];
  const axiomPrograms = coverageOverview?.axiom?.programs || [];
  const includeSuite = (suite) =>
    jurisdictionFilter === "all" || regionForSuite(suite) === jurisdictionFilter;

  const reportRows = (reports || [])
    .filter((report) => report.suite)
    .filter((report) => includeSuite(report.suite))
    .filter((report) => report.engines?.left === "axiom" || report.engines?.right === "axiom")
    .map((report) => {
      const meta = metaFor(report.suite);
      const peProgram = lookupProgram(pePrograms, (p) => p.id === meta.program);
      const axiomProgram =
        lookupProgram(axiomPrograms, (p) => p.suite === report.suite) ||
        lookupProgram(
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
    .filter((row) => row.eligibility || row.amount || row.hasReportSurface);

  const reportedSuites = new Set(reportRows.map((row) => row.suite));
  const coverageRows = axiomPrograms
    .filter((program) => program.suite)
    .filter((program) => includeSuite(program.suite))
    .filter((program) => !reportedSuites.has(program.suite))
    .map((program) => {
      const meta = metaFor(program.suite);
      const peProgram = lookupProgram(pePrograms, (p) => p.id === meta.program);
      return {
        ...meta,
        suite: program.suite,
        report: null,
        peProgram,
        axiomProgram: program,
        eligibility: null,
        amount: null,
        hasReportSurface: false,
        coverageOnly: true,
      };
    });

  return [...reportRows, ...coverageRows]
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
  if (!metric.total) {
    return (
      <span className="mono" style={{ color: "var(--ink-mute)", fontSize: 12 }}>
        Not measured
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

function MeasurementLine({ row }) {
  const note = measurementNote(row);
  if (!note) return null;
  return (
    <div
      style={{
        marginTop: 6,
        color: "var(--ink-mute)",
        fontSize: 11.5,
        lineHeight: 1.35,
      }}
    >
      {note}
    </div>
  );
}

function GapText({ gaps }) {
  if (!gaps?.length) {
    return <span style={{ color: "var(--ink-mute)" }}>No current non-TANF gap called out.</span>;
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

export default function CoverageOverview({
  reports,
  coverageOverview,
  jurisdictionFilter = "all",
}) {
  const rows = buildRows(reports, coverageOverview, jurisdictionFilter);
  if (!rows.length) return null;

  const measured = rows.filter(
    (row) => row.eligibility?.total > 0 || row.amount?.total > 0,
  ).length;
  const axiomExecutable = rows.filter(
    (row) =>
      row.axiomProgram?.status === "executable" ||
      row.axiomProgram?.status === "executableCoverage" ||
      row.axiomProgram?.status === "parameter",
  ).length;
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
          <span className="badge badge-good">{measured}/{compared} measured</span>
          <span className="badge badge-good">{axiomExecutable}/{compared} Axiom executable or parameter</span>
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
              <th>Amount / parameter alignment</th>
              <th>Current non-TANF gaps</th>
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
                  {row.coverageOnly && (
                    <div
                      style={{
                        marginTop: 6,
                        color: "var(--ink-mute)",
                        fontSize: 11.5,
                        lineHeight: 1.35,
                      }}
                    >
                      Current gap only; no Axiom-vs-PolicyEngine alignment run yet.
                    </div>
                  )}
                  <MeasurementLine row={row} />
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
