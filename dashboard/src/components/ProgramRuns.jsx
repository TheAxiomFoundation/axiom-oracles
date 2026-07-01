"use client";

import { useEffect, useState } from "react";
import { IconChevronRight, IconChevronDown } from "@tabler/icons-react";
import AlignmentReport from "./AlignmentReport";
import { engineLabel, formatAgreementRate } from "../utils/format";
import { rateColor } from "../utils/colors";
import { suiteMeta, reportMetric, rateStatus } from "../utils/suites";

/**
 * Every verification run as one collapsed line: program, engines, how many
 * checks, how often they agreed. Runs with the most disagreement sort first
 * so the reading order is the triage order. Expanding a row reveals the full
 * per-concept breakdown, cause attribution, and case drawer.
 *
 * Diagnostic and instrumentation runs live in their own group at the end and
 * never mix into the verified numbers.
 */

function runKey(report, index) {
  return `${report.file || report.suite || "report"}-${index}`;
}

function RunStatus({ metric, kind, alarms }) {
  if (kind === "parameter") {
    return <span className="badge badge-warn">Parameter check</span>;
  }
  if (kind === "coverage") {
    return <span className="badge badge-warn">Coverage only</span>;
  }
  if (kind === "diagnostic") {
    return <span className="badge badge-warn">Diagnostic</span>;
  }
  if (metric.total === 0) {
    return alarms > 0 ? (
      <span className="badge badge-bad">
        {alarms} alarm{alarms === 1 ? "" : "s"}
      </span>
    ) : null;
  }
  const status = rateStatus(metric.rate);
  if (status === "verified" && metric.mismatches === 0) {
    return <span className="badge badge-good">All checks agree</span>;
  }
  return (
    <span className={status === "verified" ? "badge badge-good" : "badge badge-bad"}>
      {metric.mismatches.toLocaleString()} disagree
    </span>
  );
}

function RunRow({ report, knownCauses, isOpen, onToggle, anchorId }) {
  const meta = suiteMeta(report.suite);
  const metric = reportMetric(report);
  const alarms = (report.summary?.alarms || []).length;
  const engines = `${engineLabel(report.engines?.left)} vs ${engineLabel(report.engines?.right)}`;

  return (
    <div className="run-row" id={anchorId}>
      <button
        type="button"
        className="run-head"
        aria-expanded={isOpen}
        onClick={onToggle}
      >
        <span className="run-chevron">
          {isOpen ? <IconChevronDown size={15} /> : <IconChevronRight size={15} />}
        </span>
        <span className="run-title">
          <span className="run-label">{meta.label}</span>
          <span className="mono run-meta">
            {engines}
            {report.case_count > 0 &&
              ` · ${report.case_count.toLocaleString()} households`}
            {report.population && ` · ${report.population}`}
          </span>
        </span>
        <span className="run-figures">
          <RunStatus metric={metric} kind={meta.kind} alarms={alarms} />
          {metric.total > 0 && (
            <span
              className="mono run-rate"
              style={{ color: rateColor(metric.rate) }}
            >
              {formatAgreementRate(metric.rate, metric.mismatches)}
            </span>
          )}
        </span>
      </button>
      {isOpen && (
        <div className="run-detail">
          <AlignmentReport report={report} knownCauses={knownCauses} embedded />
        </div>
      )}
    </div>
  );
}

function sortRuns(reports) {
  return [...reports].sort((a, b) => {
    const ma = reportMetric(a);
    const mb = reportMetric(b);
    const ra = ma.rate ?? 101; // unmeasured after measured
    const rb = mb.rate ?? 101;
    if (ra !== rb) return ra - rb;
    return suiteMeta(a.suite).order - suiteMeta(b.suite).order;
  });
}

export default function ProgramRuns({ reports, knownCauses }) {
  const [open, setOpen] = useState(() => new Set());

  // Register tiles and ledger rows link to #run-<suite>; expand the target.
  useEffect(() => {
    const openFromHash = () => {
      const match = window.location.hash.match(/^#run-(.+)$/);
      if (!match) return;
      const suite = decodeURIComponent(match[1]);
      setOpen((prev) => new Set(prev).add(suite));
    };
    openFromHash();
    window.addEventListener("hashchange", openFromHash);
    return () => window.removeEventListener("hashchange", openFromHash);
  }, []);

  const withData = (reports || []).filter(
    (r) =>
      (r.aggregates || []).length > 0 ||
      (r.summary?.alarms || []).length > 0,
  );
  const verification = sortRuns(
    withData.filter((r) => suiteMeta(r.suite).kind !== "diagnostic"),
  );
  const diagnostics = sortRuns(
    withData.filter((r) => suiteMeta(r.suite).kind === "diagnostic"),
  );

  if (!verification.length && !diagnostics.length) return null;

  const toggle = (suite) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(suite)) next.delete(suite);
      else next.add(suite);
      return next;
    });

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {verification.length > 0 && (
        <>
          <div className="section-eyebrow">
            Verification runs · lowest agreement first
          </div>
          <div className="run-list">
            {verification.map((report, i) => (
              <RunRow
                key={runKey(report, i)}
                report={report}
                knownCauses={knownCauses}
                anchorId={`run-${report.suite}`}
                isOpen={open.has(report.suite)}
                onToggle={() => toggle(report.suite)}
              />
            ))}
          </div>
        </>
      )}

      {diagnostics.length > 0 && (
        <details className="diagnostics-group">
          <summary>
            Diagnostic runs · {diagnostics.length} instrumentation
            {diagnostics.length === 1 ? " run" : " runs"}, excluded from
            headline numbers
          </summary>
          <div className="run-list" style={{ marginTop: 10 }}>
            {diagnostics.map((report, i) => {
              // Two diagnostic reports can share a suite slug, so key
              // open-state by file name rather than suite.
              const key = `diag-${runKey(report, i)}`;
              return (
                <RunRow
                  key={key}
                  report={report}
                  knownCauses={knownCauses}
                  isOpen={open.has(key)}
                  onToggle={() => toggle(key)}
                />
              );
            })}
          </div>
        </details>
      )}
    </section>
  );
}
