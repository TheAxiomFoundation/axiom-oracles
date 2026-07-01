"use client";

import { useEffect, useState } from "react";
import { IconChevronRight, IconChevronDown } from "@tabler/icons-react";
import AlignmentReport from "./AlignmentReport";
import { engineLabel, formatAgreementRate } from "../utils/format";
import { rateColor } from "../utils/colors";
import {
  US_STATE_NAMES,
  suiteMeta,
  reportMetric,
  rateStatus,
  isAxiomPair,
  runAnchor,
} from "../utils/suites";

/**
 * Every verification run, expanded by default and ordered the same way as
 * the coverage register above (federal income tax, then SNAP states, then
 * the remaining programs), so scrolling the runs follows the register.
 * Each row shows the full per-concept breakdown, cause attribution, and
 * case drawer; the header line collapses it.
 *
 * Rows are keyed by (suite, engine pair), so the same program verified
 * against several oracles (PolicyEngine, TAXSIM, …) lists once per oracle.
 * Oracle-vs-oracle cross-checks and diagnostic runs live in their own groups
 * and never mix into the verified numbers.
 */

const COVERAGE_STATUS_LABEL = {
  complete: "Complete",
  executable: "Executable",
  executableCoverage: "Executable coverage",
  parameter: "Parameter check",
  coverageOnly: "Coverage only",
  inProgress: "In progress",
  partial: "Partial",
};

function measurementNote(report, axiomProgram) {
  if (report.suite === "co-snap-ecps") {
    return "Measured by the encoder-backed CO SNAP report; the axiom-programs wrapper now has generic output/input mapping smoke-tested, but is not yet the dashboard comparison path.";
  }
  if (axiomProgram?.status === "coverageOnly") {
    return "Coverage-only surface; not a measured alignment run.";
  }
  if (axiomProgram?.status === "executableCoverage") {
    return "Executable Axiom package; the comparison is still coverage-only, not a measured alignment run.";
  }
  if (axiomProgram?.status === "parameter") {
    return "Parameter check; not end-to-end household eligibility.";
  }
  if (report.population === "enhanced-cps") {
    return "Measured over the Enhanced CPS slice for this jurisdiction.";
  }
  if (report.population === "enhanced-frs") {
    return "Measured over the Enhanced FRS slice.";
  }
  return null;
}

/**
 * What each engine claims to cover for this run's program — the piece of the
 * old coverage table that the register and rate figures don't already say.
 */
function RunCoverageContext({ report, coverageOverview }) {
  const meta = suiteMeta(report.suite);
  const axiomPrograms = coverageOverview?.axiom?.programs || [];
  const pePrograms = coverageOverview?.policyengine?.programs || [];

  const axiomProgram =
    axiomPrograms.find((p) => p.suite === report.suite) ||
    axiomPrograms.find(
      (p) => p.program === meta.family && p.jurisdiction === meta.jurisdiction,
    );
  const peProgram = pePrograms.find((p) => p.id === meta.family);
  const note = measurementNote(report, axiomProgram);

  if (!axiomProgram && !peProgram && !note) return null;

  return (
    <div className="run-context">
      {axiomProgram && (
        <div className="run-context-item">
          <span className="mono run-context-label">Axiom coverage</span>
          <span>
            {COVERAGE_STATUS_LABEL[axiomProgram.status] || axiomProgram.status}
            {axiomProgram.source && (
              <span className="mono run-context-source">
                {" "}
                · {axiomProgram.source}
              </span>
            )}
          </span>
        </div>
      )}
      {peProgram && (
        <div className="run-context-item">
          <span className="mono run-context-label">
            PolicyEngine coverage
          </span>
          <span>
            {COVERAGE_STATUS_LABEL[peProgram.status] || peProgram.status}
            {peProgram.notes && <> — {peProgram.notes}</>}
          </span>
        </div>
      )}
      {note && (
        <div className="run-context-item">
          <span className="mono run-context-label">Measurement</span>
          <span>{note}</span>
        </div>
      )}
    </div>
  );
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

function RunRow({ report, knownCauses, coverageOverview, isOpen, onToggle, anchorId }) {
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
              ` · ${report.case_count.toLocaleString()} ${
                meta.kind === "parameter" ? "parameters" : "households"
              }`}
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
          <RunCoverageContext
            report={report}
            coverageOverview={coverageOverview}
          />
          <AlignmentReport report={report} knownCauses={knownCauses} embedded />
        </div>
      )}
    </div>
  );
}

// Mirror the coverage register's order: family order first, then
// jurisdictions by state name within a family (matching the state strip).
function sortRuns(reports) {
  return [...reports].sort((a, b) => {
    const ma = suiteMeta(a.suite);
    const mb = suiteMeta(b.suite);
    if (ma.order !== mb.order) return ma.order - mb.order;
    const ja = US_STATE_NAMES[ma.jurisdiction] || ma.jurisdiction || "";
    const jb = US_STATE_NAMES[mb.jurisdiction] || mb.jurisdiction || "";
    return ja.localeCompare(jb);
  });
}

function RunGroup({ reports, knownCauses, coverageOverview, open, toggle }) {
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
            coverageOverview={coverageOverview}
            anchorId={anchor}
            isOpen={open.has(anchor)}
            onToggle={() => toggle(anchor)}
          />
        );
      })}
    </div>
  );
}

export default function ProgramRuns({ reports, knownCauses, coverageOverview }) {
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

  // Verification runs start expanded; cross-checks and diagnostics start
  // collapsed inside their groups.
  const [open, setOpen] = useState(
    () => new Set(verification.map(runAnchor)),
  );

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
          <div className="section-eyebrow">Verification runs</div>
          <RunGroup
            reports={verification}
            knownCauses={knownCauses}
            coverageOverview={coverageOverview}
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
