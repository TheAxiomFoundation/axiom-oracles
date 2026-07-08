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

function OracleDot({ run }) {
  const status = rateStatus(run.metric.rate);
  const near = run.near;
  const title = [
    `vs ${engineLabel(run.oracle)}: ${formatAgreementRate(run.metric.rate, run.metric.mismatches)}`,
    near ? `${near.rate.toFixed(1)}% within $${near.threshold}` : null,
    run.kind === "parameter" ? "parameter check" : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <span
      className={`pst-dot pst-${status}${run.kind === "parameter" ? " pst-param" : ""}`}
      title={title}
    />
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
          const rate = row.total > 0 ? ((row.total - row.mismatches) / row.total) * 100 : null;
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
              <span className="pst-dots">
                {row.runs
                  .sort((a, b) => b.metric.total - a.metric.total)
                  .map((run) => (
                    <OracleDot key={run.suite} run={run} />
                  ))}
              </span>
              <span className="mono pst-checks">
                {row.total > 0 ? `${row.total.toLocaleString()} checks` : "parameters"}
              </span>
              <span
                className="mono pst-rate"
                style={rate != null ? { color: rateColor(rate) } : undefined}
              >
                {rate != null ? formatAgreementRate(rate, row.mismatches) : "—"}
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
