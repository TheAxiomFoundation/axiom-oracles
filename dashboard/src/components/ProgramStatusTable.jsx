"use client";

import { engineLabel, formatAgreementRate } from "../utils/format";
import { rateColor } from "../utils/colors";
import {
  US_STATE_NAMES,
  suiteMeta,
  reportMetric,
  nearMetric,
  rateStatus,
  isAxiomPair,
  otherOracle,
  programKey,
} from "../utils/suites";

/**
 * The overview's program table: one row per program (family ×
 * jurisdiction), one dot per oracle it is verified against. Every row is
 * a door into the program page, where the run detail, triangulation, and
 * case explorer live.
 */

function OracleRate({ run }) {
  const near = run.near;
  const title = [
    `${run.metric.mismatches.toLocaleString()} of ${run.metric.total.toLocaleString()} checks disagree`,
    near ? `${near.rate.toFixed(1)}% within $${near.threshold}` : null,
    run.kind === "parameter"
      ? "parameter-value check, not household-level"
      : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <span className="pst-oracle" title={title}>
      <span
        className="mono pst-oracle-rate"
        style={{ color: rateColor(run.metric.rate) }}
      >
        {formatAgreementRate(run.metric.rate, run.metric.mismatches)}
      </span>
      {run.kind === "parameter" && (
        <span className="pst-oracle-kind">params</span>
      )}
    </span>
  );
}

export default function ProgramStatusTable({ reports, onOpen }) {
  const programs = new Map();
  for (const report of reports || []) {
    if (!isAxiomPair(report)) continue;
    if (!(report.aggregates || []).length) continue;
    const meta = suiteMeta(report.suite);
    if (meta.kind === "diagnostic") continue;
    const key = programKey(meta);
    if (!programs.has(key)) {
      programs.set(key, { meta, runs: [], total: 0, mismatches: 0 });
    }
    const entry = programs.get(key);
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
    }
  }

  const rows = [...programs.values()].sort(
    (a, b) =>
      a.meta.order - b.meta.order ||
      String(a.meta.jurisdiction).localeCompare(String(b.meta.jurisdiction)),
  );
  if (!rows.length) return null;

  return (
    <section className="card-flat">
      <div className="section-head">
        <div>
          <div className="section-eyebrow">Verified programs</div>
          <div className="section-title">
            Every measured program — open one for runs, triangulation, and
            every case
          </div>
        </div>
      </div>
      <div className="pst-body">
        {rows.map((row) => {
          const key = programKey(row.meta);
          const where = US_STATE_NAMES[row.meta.jurisdiction] || row.meta.jurisdiction;
          return (
            <button
              key={key}
              type="button"
              className="pst-row"
              onClick={() => onOpen(key)}
              title={`Open ${row.meta.label}`}
            >
              <span className="pst-label">{row.meta.label}</span>
              <span className="mono pst-where">{where}</span>
              <span className="pst-oracles">
                {(() => {
                  const byOracle = new Map();
                  for (const run of row.runs) {
                    if (run.metric.rate == null) continue;
                    if (!byOracle.has(run.oracle)) byOracle.set(run.oracle, []);
                    byOracle.get(run.oracle).push(run);
                  }
                  return [...byOracle.entries()]
                    .sort(
                      (a, b) =>
                        Math.max(...b[1].map((r) => r.metric.total)) -
                        Math.max(...a[1].map((r) => r.metric.total)),
                    )
                    .map(([oracle, runs]) => (
                      <span key={oracle} className="pst-oracle-group">
                        <span className="pst-oracle-name">
                          {engineLabel(oracle)}
                        </span>
                        {runs
                          .sort((a, b) => b.metric.total - a.metric.total)
                          .map((run) => (
                            <OracleRate key={run.suite} run={run} />
                          ))}
                      </span>
                    ));
                })()}
              </span>
              <span className="mono pst-checks">
                {row.total > 0
                  ? `${row.total.toLocaleString()} checks`
                  : "parameter check"}
              </span>
              <span className="pst-arrow" aria-hidden="true">
                →
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
