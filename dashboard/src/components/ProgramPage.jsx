"use client";

import { useMemo } from "react";
import {
  engineLabel,
  formatPct,
  formatAgreementRate,
  mismatchKindLabel,
} from "../utils/format";
import {
  US_STATE_NAMES,
  suiteMeta,
  reportMetric,
  nearMetric,
  topLevelAggregates,
  isAxiomPair,
  otherOracle,
  programKey,
} from "../utils/suites";
import { causeFor } from "../utils/programs";
import DispositionNote from "./DispositionNote";

/**
 * Level 2 of the drill: one program (family × jurisdiction), all its
 * oracles. Every fact appears exactly once, in reading order:
 *
 *  1. The verdict ledger — one agreement bar per oracle run; the filled
 *     mass is the matched share, the gap is what the rest of the page
 *     explains.
 *  2. Compared concepts — every value the engines were asked to agree
 *     on, across all runs, one table.
 *  3. WhySection — every disagreement pattern with its known cause or
 *     disposition explanation inline.
 *  4. The handoff to level 3 — browse the households.
 *  5. Provenance footnote — sources and measurement caveats, muted,
 *     at the very end.
 */

/** Render `backticked` spans in cause prose as inline code. */
function richText(text) {
  return String(text || "")
    .split(/`([^`]+)`/g)
    .map((seg, i) =>
      i % 2 ? (
        <code key={i} className="pp-cause-code">
          {seg}
        </code>
      ) : (
        seg
      ),
    );
}

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
 * The verdict ledger — the page's signature. One box per oracle run,
 * side by side when several oracles check the program: who checked,
 * over what population, and the agreement rate as the focal figure.
 * The card's edge and wash carry the verdict color; the disagreement
 * figures under the rate are what the why-section explains. Household
 * runs lead; parameter probes follow.
 */
function VerdictCard({ report }) {
  const meta = suiteMeta(report.suite);
  const metric = reportMetric(report);
  const near = nearMetric(report);
  const oracle = otherOracle(report);
  return (
    <article
      className="pp-verdict-card"

    >
      <div className="pp-verdict-who">
        <span className="pp-verdict-oracle">vs {engineLabel(oracle)}</span>
        <span className="mono pp-verdict-meta">
          {report.case_count > 0 &&
            `${report.case_count.toLocaleString()} ${
              meta.kind === "parameter" ? "parameters" : "households"
            }`}
          {report.population && ` · ${report.population}`}
          {meta.kind === "parameter" && " · parameter check"}
        </span>
      </div>
      <div className="pp-verdict-rates">
        <div className="mono pp-verdict-rate">
          {formatAgreementRate(metric.rate, metric.mismatches)}
          <span className="pp-verdict-rate-label">agree</span>
        </div>
        {metric.explainedRate != null &&
          metric.explainedRate - metric.rate >= 0.05 && (
            <div
              className="mono pp-verdict-rate"
              title="Counting mismatches with schema-validated dispositions as explained"
            >
              {formatPct(metric.explainedRate, 1)}
              <span className="pp-verdict-rate-label">explained</span>
            </div>
          )}
      </div>
      <div className="pp-verdict-subs">
        <span className="mono pp-verdict-sub">
          {metric.mismatches > 0
            ? `${metric.mismatches.toLocaleString()} of ${metric.total.toLocaleString()} checks disagree`
            : `all ${metric.total.toLocaleString()} checks agree`}
        </span>
        {near && near.rate - metric.rate >= 1 && (
          <span className="mono pp-verdict-sub">
            {formatPct(near.rate, 1)} within ${near.threshold}
          </span>
        )}
      </div>
    </article>
  );
}

/**
 * Provenance footnote — where Axiom's rules come from, what the oracle
 * claims about its own coverage, and how the measurement was taken.
 * Deliberately quiet: it qualifies the verdict, it doesn't compete with
 * it, so it renders as muted lines at the end of the page.
 */
function CoverageBlock({ programReports, coverageOverview }) {
  const first = programReports[0];
  const meta = suiteMeta(first.suite);
  const axiomPrograms = coverageOverview?.axiom?.programs || [];
  const pePrograms = coverageOverview?.policyengine?.programs || [];
  const axiomProgram =
    axiomPrograms.find((p) =>
      programReports.some((r) => r.suite === p.suite),
    ) ||
    axiomPrograms.find(
      (p) => p.program === meta.family && p.jurisdiction === meta.jurisdiction,
    );
  const peProgram = pePrograms.find((p) => p.id === meta.family);
  const notes = [
    ...new Set(
      programReports
        .map((r) => measurementNote(r, axiomProgram))
        .filter(Boolean),
    ),
  ];
  if (!axiomProgram && !peProgram && !notes.length) return null;
  return (
    <div className="pp-provenance">
      {axiomProgram && (
        <p className="pp-provenance-line">
          <span className="mono pp-provenance-label">Axiom</span>
          {COVERAGE_STATUS_LABEL[axiomProgram.status] || axiomProgram.status}
          {axiomProgram.source && (
            <span className="mono pp-provenance-source">
              {" "}
              · {axiomProgram.source}
            </span>
          )}
        </p>
      )}
      {peProgram && (
        <p className="pp-provenance-line">
          <span className="mono pp-provenance-label">PolicyEngine</span>
          {COVERAGE_STATUS_LABEL[peProgram.status] || peProgram.status}
          {peProgram.notes && <> — {peProgram.notes}</>}
        </p>
      )}
      {notes.map((note, i) => (
        <p key={i} className="pp-provenance-line">
          <span className="mono pp-provenance-label">Measurement</span>
          {note}
        </p>
      ))}
    </div>
  );
}

/**
 * Every compared concept across every run, one table: name, the grain it
 * was checked at, the disagreement figures, the rate.
 */
function ConceptTable({ programReports }) {
  const rows = [];
  for (const report of programReports) {
    const meta = suiteMeta(report.suite);
    for (const agg of topLevelAggregates(report.aggregates)) {
      if (!((agg.comparison_count || 0) > 0)) continue;
      rows.push({ agg, kind: meta.kind, oracle: otherOracle(report) });
    }
  }
  if (!rows.length) return null;
  rows.sort((a, b) => (a.agg.match_rate ?? 101) - (b.agg.match_rate ?? 101));
  const multiOracle =
    new Set(programReports.map((r) => otherOracle(r))).size > 1;
  return (
    <section className="card-flat">
      <div className="section-head">
        <div>
          <div className="section-eyebrow">Compared concepts</div>
          <div className="section-title">
            Every value the engines were asked to agree on
          </div>
        </div>
      </div>
      <div className="pp-concepts">
        {rows.map(({ agg, kind, oracle }, i) => (
          <div className="pp-concept" key={`${agg.concept}-${i}`}>
            <span className="pp-concept-name">
              {agg.description || agg.concept}
              <span className="mono pp-concept-kind">
                {kind === "parameter" ? "parameter" : "households"}
                {multiOracle && ` · vs ${engineLabel(oracle)}`}
              </span>
            </span>
            <span className="mono pp-concept-figures">
              {agg.mismatch_count > 0
                ? `${agg.mismatch_count.toLocaleString()} of ${(agg.comparison_count || 0).toLocaleString()} disagree`
                : `all ${(agg.comparison_count || 0).toLocaleString()} agree`}
              {agg.weighted_match_rate != null &&
                agg.match_rate != null &&
                Math.abs(agg.weighted_match_rate - agg.match_rate) >= 0.3 &&
                ` · ${formatPct(agg.weighted_match_rate, 1)} weighted`}
            </span>
            <span
              className="mono pp-concept-rate"

            >
              {formatPct(agg.match_rate, 1)}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

/**
 * The single "why" section: every disagreement pattern (concept × kind),
 * largest first, with its known cause or disposition explanation inline —
 * patterns, causes, and explanations are one list, not three sections.
 */
function WhySection({ programReports, knownCauses }) {
  const rows = [];
  // The run cards state the TRUE disagreement totals (from aggregates);
  // this section must never contradict them. Large suites slim the
  // recorded mismatch list to its first rows, so pattern counts derived
  // from that list are lower bounds — except when a concept shows a
  // single pattern, where the aggregate's exact count applies.
  let anyLowerBound = false;
  let trueTotal = 0;
  for (const report of programReports) {
    trueTotal += reportMetric(report).mismatches;
    const descriptions = new Map(
      (report.aggregates || []).map((a) => [a.concept, a.description]),
    );
    const aggMismatches = new Map();
    for (const agg of topLevelAggregates(report.aggregates)) {
      aggMismatches.set(
        agg.concept,
        (aggMismatches.get(agg.concept) || 0) + (agg.mismatch_count || 0),
      );
    }
    const list = report.mismatches || [];
    const truncated = (report.summary?.mismatch_count ?? 0) > list.length;
    const buckets = new Map();
    for (const m of list) {
      const key = `${m.concept}::${m.kind}`;
      buckets.set(key, (buckets.get(key) || 0) + 1);
    }
    const kindsPerConcept = new Map();
    for (const key of buckets.keys()) {
      const concept = key.split("::")[0];
      kindsPerConcept.set(concept, (kindsPerConcept.get(concept) || 0) + 1);
    }
    const dispositioned = Boolean(
      report.summary?.dispositioned?.dispositions_file,
    );
    for (const [key, recorded] of buckets) {
      const [concept, kind] = key.split("::");
      const singleKind = kindsPerConcept.get(concept) === 1;
      const exact =
        singleKind && aggMismatches.has(concept)
          ? aggMismatches.get(concept)
          : recorded;
      const lowerBound = truncated && !singleKind;
      if (lowerBound) anyLowerBound = true;
      rows.push({
        count: exact,
        lowerBound,
        concept,
        kind,
        conceptLabel: descriptions.get(concept) || concept,
        cause: causeFor(knownCauses, report, concept, kind),
        dispositioned,
        suite: report.suite,
        oracle: otherOracle(report),
        region: suiteMeta(report.suite).region,
        engines: report.engines,
      });
    }
  }
  if (!rows.length) return null;
  rows.sort((a, b) => b.count - a.count);
  const multiOracle = programReports.length > 1;

  return (
    <section className="card-flat">
      <div className="section-head">
        <div>
          <div className="section-eyebrow">Why they disagree</div>
          <div className="section-title">
            {trueTotal.toLocaleString()} disagreement
            {trueTotal === 1 ? "" : "s"} in {rows.length} pattern
            {rows.length === 1 ? "" : "s"}
          </div>
        </div>
      </div>
      <div className="pp-why">
        {rows.map((row, i) => (
          <div key={i} className="pp-why-row">
            <div className="pp-why-head">
              <span
                className="mono pp-why-count"
                title={
                  row.lowerBound
                    ? "Counted from the recorded mismatch rows — the true count may be higher"
                    : undefined
                }
              >
                {row.lowerBound ? "≥" : ""}
                {row.count.toLocaleString()}
              </span>
              <span className="pp-why-what">
                {row.cause?.label ||
                  mismatchKindLabel(row.kind, row.engines)}
                <span className="mono pp-why-concept">
                  {row.conceptLabel}
                  {row.cause?.label &&
                    ` · ${mismatchKindLabel(row.kind, row.engines)}`}
                  {multiOracle && ` · vs ${engineLabel(row.oracle)}`}
                </span>
              </span>
              {row.cause?.issue_url ? (
                <a
                  className="v2-action v2-action-filed"
                  href={row.cause.issue_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  issue filed ↗
                </a>
              ) : row.cause?.fix_owner ? (
                <span
                  className="mono pp-cause-owner"
                  title="Where the fix lives"
                >
                  {row.cause.fix_owner}
                </span>
              ) : row.cause ? (
                <span className="v2-action v2-action-doc">
                  cause documented
                </span>
              ) : row.dispositioned ? (
                <span className="v2-action v2-action-doc">dispositioned</span>
              ) : (
                <span className="v2-action v2-action-open">
                  open — needs triage
                </span>
              )}
            </div>
            {row.cause ? (
              <p className="pp-cause-desc">{richText(row.cause.description)}</p>
            ) : row.dispositioned ? (
              <DispositionNote row={row} />
            ) : null}
          </div>
        ))}
        {anyLowerBound && (
          <p className="mono pp-why-note">
            ≥ counts come from the recorded mismatch rows — this suite
            slims its list, so those patterns may be larger.
          </p>
        )}
      </div>
    </section>
  );
}

export default function ProgramPage({
  programId,
  reports,
  knownCauses,
  coverageOverview,
  onBack,
  onBrowseHouseholds,
}) {
  const programReports = useMemo(
    () =>
      (reports || []).filter((r) => {
        if (!isAxiomPair(r) || !(r.aggregates || []).length) return false;
        return programKey(suiteMeta(r.suite)) === programId;
      }),
    [reports, programId],
  );

  if (!programReports.length) {
    return (
      <section className="card-flat">
        <div className="section-head">
          <div>
            <div className="section-title">Program not found</div>
          </div>
        </div>
        <button type="button" className="pp-back" onClick={onBack}>
          ← back to overview
        </button>
      </section>
    );
  }

  const meta = suiteMeta(programReports[0].suite);
  const where = US_STATE_NAMES[meta.jurisdiction] || meta.jurisdiction;
  // The same population compared against several oracles is still the
  // same households — take the widest run, not the sum.
  const households = Math.max(
    0,
    ...programReports.map((r) =>
      Number.isFinite(r.case_count) ? r.case_count : 0,
    ),
  );

  // Household-scale runs lead the ledger; parameter probes follow.
  const orderedReports = [...programReports].sort((a, b) => {
    const ka = suiteMeta(a.suite).kind === "parameter" ? 1 : 0;
    const kb = suiteMeta(b.suite).kind === "parameter" ? 1 : 0;
    return ka - kb || (b.case_count || 0) - (a.case_count || 0);
  });

  return (
    <>
      <div className="pp-head">
        <button type="button" className="pp-back" onClick={onBack}>
          ← all programs
        </button>
        <h1 className="pp-title">
          {meta.label}
          <span className="mono pp-where"> · {where}</span>
        </h1>
      </div>

      <div className="pp-verdicts">
        {orderedReports.map((report) => (
          <VerdictCard key={report.suite} report={report} />
        ))}
      </div>

      <ConceptTable programReports={orderedReports} />

      <WhySection
        programReports={programReports}
        knownCauses={knownCauses}
      />

      {onBrowseHouseholds && meta.kind !== "parameter" && (
        <button
          type="button"
          className="pp-browse"
          onClick={onBrowseHouseholds}
        >
          Browse the {households > 0 ? households.toLocaleString() : ""}{" "}
          households →
        </button>
      )}

      <CoverageBlock
        programReports={programReports}
        coverageOverview={coverageOverview}
      />
    </>
  );
}
