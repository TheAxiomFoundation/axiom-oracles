"use client";

import { useState } from "react";
import { engineLabel, mismatchKindLabel } from "../utils/format";
import {
  FAMILY_LABELS,
  US_STATE_NAMES,
  suiteMeta,
  suiteLabel,
  isAxiomPair,
  otherOracle,
  runAnchor,
} from "../utils/suites";

/**
 * The open-gaps ledger: every measured disagreement, rolled up across all
 * verification runs and ranked by how many checks it affects. Buckets with a
 * known-cause entry show the plain-language explanation and issue link;
 * unexplained buckets are labeled as such so the triage backlog is honest.
 *
 * Below the ledger, documented encoding gaps (work known before any run)
 * are listed per program.
 */

function causeFor(knownCauses, report, concept, kind) {
  const candidates = (knownCauses || []).filter(
    (c) => c.suite === report.suite && c.concept === concept && c.kind === kind,
  );
  return (
    candidates.find(
      (c) =>
        c.engines &&
        c.engines.left === report.engines?.left &&
        c.engines.right === report.engines?.right,
    ) || candidates.find((c) => !c.engines)
  );
}

function buildLedger(reports, knownCauses) {
  const rows = [];
  for (const report of reports || []) {
    if (!isAxiomPair(report)) continue;
    if (suiteMeta(report.suite).kind === "diagnostic") continue;

    const descriptions = new Map(
      (report.aggregates || []).map((a) => [a.concept, a.description]),
    );
    const buckets = new Map();
    for (const m of report.mismatches || []) {
      const key = `${m.concept}::${m.kind}`;
      buckets.set(key, (buckets.get(key) || 0) + 1);
    }
    for (const [key, count] of buckets) {
      const [concept, kind] = key.split("::");
      const cause = causeFor(knownCauses, report, concept, kind);
      rows.push({
        count,
        suite: report.suite,
        anchor: runAnchor(report),
        program: suiteLabel(report.suite),
        oracle: otherOracle(report),
        engines: report.engines,
        conceptLabel: descriptions.get(concept) || concept,
        kind,
        cause,
      });
    }
  }
  return rows.sort((a, b) => b.count - a.count);
}

function LedgerRow({ row }) {
  return (
    <div className="ledger-row">
      <span className="mono ledger-count">{row.count.toLocaleString()}</span>
      <div className="ledger-body">
        <div className="ledger-label">
          {row.cause?.label || (
            <>
              {mismatchKindLabel(row.kind, row.engines)}
              <span className="ledger-unexplained"> · not yet explained</span>
            </>
          )}
          {row.cause?.issue_url && (
            <>
              {" "}
              <a
                href={row.cause.issue_url}
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
        {row.cause?.description && (
          <div className="ledger-desc">{row.cause.description}</div>
        )}
        <div className="mono ledger-meta">
          <a href={`#${row.anchor}`} className="ledger-programlink">
            {row.program}
          </a>
          {row.oracle && <> · vs {engineLabel(row.oracle)}</>}
          {" · "}
          {row.conceptLabel} · {mismatchKindLabel(row.kind, row.engines)}
          {row.cause?.fix_owner && <> · owner: {row.cause.fix_owner}</>}
        </div>
      </div>
    </div>
  );
}

function programGapLabel(program) {
  const family = FAMILY_LABELS[program.program] || program.program;
  const j = program.jurisdiction;
  const place = US_STATE_NAMES[j] || j;
  return j && j !== "US" && j !== "UK" ? `${place} ${family}` : family;
}

function DocumentedGaps({ coveragePrograms, region }) {
  const withGaps = (coveragePrograms || [])
    .filter((p) => (p.known_non_tanf_gaps || []).length > 0)
    .filter((p) => {
      const isUK = p.jurisdiction === "UK";
      return region === "uk" ? isUK : !isUK;
    });
  if (!withGaps.length) return null;

  return (
    <details className="ledger-documented">
      <summary>
        Documented encoding gaps ·{" "}
        {withGaps.reduce((n, p) => n + p.known_non_tanf_gaps.length, 0)} known
        items across {withGaps.length} programs
      </summary>
      <div className="ledger-documented-list">
        {withGaps.map((p) => (
          <div key={`${p.program}-${p.jurisdiction}-${p.suite || ""}`}>
            <div className="ledger-documented-program">
              {programGapLabel(p)}
            </div>
            <ul>
              {p.known_non_tanf_gaps.map((gap) => (
                <li key={gap}>{gap}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </details>
  );
}

const INITIAL_ROWS = 6;

export default function GapLedger({ reports, knownCauses, coverageOverview, region }) {
  const [showAll, setShowAll] = useState(false);
  const rows = buildLedger(reports, knownCauses);
  const coveragePrograms = coverageOverview?.axiom?.programs;

  const hasDocumented = (coveragePrograms || []).some(
    (p) => (p.known_non_tanf_gaps || []).length > 0,
  );
  if (!rows.length && !hasDocumented) return null;

  const visible = showAll ? rows : rows.slice(0, INITIAL_ROWS);
  const totalAffected = rows.reduce((n, r) => n + r.count, 0);

  return (
    <section className="card-flat">
      <div className="section-head">
        <div>
          <div className="section-eyebrow">Open gaps</div>
          <div className="section-title">
            {rows.length > 0
              ? `${totalAffected.toLocaleString()} disagreeing checks, ranked by cause`
              : "No measured disagreements in verified runs"}
          </div>
        </div>
      </div>
      <div className="ledger-list">
        {visible.map((row, i) => (
          <LedgerRow key={`${row.suite}-${row.conceptLabel}-${row.kind}-${i}`} row={row} />
        ))}
        {rows.length > INITIAL_ROWS && (
          <button
            type="button"
            className="ledger-more"
            onClick={() => setShowAll(!showAll)}
          >
            {showAll
              ? "Show fewer"
              : `Show all ${rows.length} causes`}
          </button>
        )}
        <DocumentedGaps coveragePrograms={coveragePrograms} region={region} />
      </div>
    </section>
  );
}
