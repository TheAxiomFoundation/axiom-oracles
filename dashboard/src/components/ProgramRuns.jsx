"use client";

import { useEffect, useState } from "react";
import { IconChevronRight, IconChevronDown } from "@tabler/icons-react";
import AlignmentReport from "./AlignmentReport";
import { engineLabel, formatAgreementRate } from "../utils/format";
import { rateColor } from "../utils/colors";
import {
  suiteMeta,
  reportMetric,
  rateStatus,
  isAxiomPair,
  runAnchor,
} from "../utils/suites";

/**
 * Every verification run as one collapsed line: program, engines, how many
 * checks, how often they agreed. Runs with the most disagreement sort first
 * so the reading order is the triage order. Expanding a row reveals the full
 * per-concept breakdown, cause attribution, and case drawer.
 *
 * Rows are keyed by (suite, engine pair), so the same program verified
 * against several oracles (PolicyEngine, TAXSIM, …) lists once per oracle.
 * Oracle-vs-oracle cross-checks and diagnostic runs live in their own groups
 * and never mix into the verified numbers.
 */

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

function RunGroup({ reports, knownCauses, open, toggle }) {
  return (
    <div className="run-list">
      {reports.map((report, i) => {
        const anchor = runAnchor(report);
        // Anchor collisions are only possible if the exact (suite, pair)
        // ran twice; suffix the index so open-state stays per-row.
        const key = `${anchor}-${i}`;
        return (
          <RunRow
            key={key}
            report={report}
            knownCauses={knownCauses}
            anchorId={anchor}
            isOpen={open.has(anchor)}
            onToggle={() => toggle(anchor)}
          />
        );
      })}
    </div>
  );
}

export default function ProgramRuns({ reports, knownCauses }) {
  const [open, setOpen] = useState(() => new Set());

  // Register tiles and ledger rows link to #run-…; expand the target row.
  useEffect(() => {
    const openFromHash = () => {
      const match = window.location.hash.match(/^#(run-.+)$/);
      if (!match) return;
      const anchor = decodeURIComponent(match[1]);
      setOpen((prev) => new Set(prev).add(anchor));
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
    withData.filter(
      (r) => isAxiomPair(r) && suiteMeta(r.suite).kind !== "diagnostic",
    ),
  );
  const crossChecks = sortRuns(withData.filter((r) => !isAxiomPair(r)));
  const diagnostics = sortRuns(
    withData.filter(
      (r) => isAxiomPair(r) && suiteMeta(r.suite).kind === "diagnostic",
    ),
  );

  if (!verification.length && !crossChecks.length && !diagnostics.length) {
    return null;
  }

  const toggle = (anchor) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(anchor)) next.delete(anchor);
      else next.add(anchor);
      return next;
    });

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {verification.length > 0 && (
        <>
          <div className="section-eyebrow">
            Verification runs · lowest agreement first
          </div>
          <RunGroup
            reports={verification}
            knownCauses={knownCauses}
            open={open}
            toggle={toggle}
          />
        </>
      )}

      {crossChecks.length > 0 && (
        <details className="diagnostics-group">
          <summary>
            Oracle cross-checks · {crossChecks.length}{" "}
            {crossChecks.length === 1 ? "run" : "runs"} comparing the oracles
            to each other
          </summary>
          <div style={{ marginTop: 10 }}>
            <RunGroup
              reports={crossChecks}
              knownCauses={knownCauses}
              open={open}
              toggle={toggle}
            />
          </div>
        </details>
      )}

      {diagnostics.length > 0 && (
        <details className="diagnostics-group">
          <summary>
            Diagnostic runs · {diagnostics.length} instrumentation
            {diagnostics.length === 1 ? " run" : " runs"}, excluded from
            headline numbers
          </summary>
          <div style={{ marginTop: 10 }}>
            <RunGroup
              reports={diagnostics}
              knownCauses={knownCauses}
              open={open}
              toggle={toggle}
            />
          </div>
        </details>
      )}
    </section>
  );
}
