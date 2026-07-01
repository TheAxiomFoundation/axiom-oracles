"use client";

import { formatPct, formatAgreementRate } from "../utils/format";
import {
  US_STATE_NAMES,
  FAMILY_LABELS,
  suiteMeta,
  reportMetric,
  rateStatus,
} from "../utils/suites";

/**
 * The coverage register — one glance answers "where is Axiom verified, and
 * where are the gaps?"
 *
 * Rows are program families; cells are jurisdictions. A tile is:
 *  - tinted with its agreement rate when a verification run exists,
 *  - outlined when the program is encoded but not yet measured,
 *  - hatched when nothing is encoded there yet.
 *
 * The SNAP row deliberately shows all 50 states + DC so the remaining work
 * is as visible as the finished work.
 */

const STATE_ORDER = Object.keys(US_STATE_NAMES);

function isAxiomPair(report) {
  return report.engines?.left === "axiom" || report.engines?.right === "axiom";
}

function tileForMeasured(metric, kind) {
  if (kind === "parameter") return { status: "parameter", note: "parameters" };
  if (kind === "coverage") return { status: "encoded", note: "encoded" };
  if (kind === "diagnostic") return { status: "diagnostic", note: "diagnostic" };
  return {
    status: rateStatus(metric.rate),
    note: formatAgreementRate(metric.rate, metric.mismatches),
  };
}

function Tile({ jurisdiction, title, tile, wide = false }) {
  const status = tile?.status || "gap";
  const label = tile?.note;
  const body = (
    <>
      <span className="tile-code">{jurisdiction}</span>
      {label && <span className="tile-rate">{label}</span>}
    </>
  );
  const cls = `register-tile tile-${status}${wide ? " register-tile-wide" : ""}`;
  if (tile?.suite) {
    return (
      <a className={cls} href={`#run-${tile.suite}`} title={title}>
        {body}
      </a>
    );
  }
  return (
    <span className={cls} title={title}>
      {body}
    </span>
  );
}

function buildSuiteIndex(reports) {
  const bySuite = new Map();
  for (const report of reports || []) {
    if (!isAxiomPair(report)) continue;
    if (!(report.aggregates || []).length && !(report.summary?.alarms || []).length)
      continue;
    const meta = suiteMeta(report.suite);
    const metric = reportMetric(report);
    const existing = bySuite.get(report.suite);
    // Keep the run with the most comparisons if a suite appears twice.
    if (!existing || metric.total > existing.metric.total) {
      bySuite.set(report.suite, { report, meta, metric });
    }
  }
  return bySuite;
}

function SnapRow({ bySuite, coveragePrograms }) {
  const measured = new Map();
  for (const entry of bySuite.values()) {
    if (entry.meta.family === "snap" && entry.meta.jurisdiction) {
      measured.set(entry.meta.jurisdiction, entry);
    }
  }
  const encoded = new Set(
    (coveragePrograms || [])
      .filter((p) => p.program === "snap" && p.jurisdiction)
      .map((p) => p.jurisdiction),
  );

  let verified = 0;
  const tiles = STATE_ORDER.map((abbr) => {
    const entry = measured.get(abbr);
    if (entry) {
      const tile = {
        ...tileForMeasured(entry.metric, entry.meta.kind),
        suite: entry.meta.suite,
      };
      if (tile.status === "verified") verified += 1;
      return {
        abbr,
        tile,
        title: `${US_STATE_NAMES[abbr]} SNAP — ${formatPct(entry.metric.rate, 1)} agreement over ${entry.metric.total.toLocaleString()} checks`,
      };
    }
    if (encoded.has(abbr)) {
      return {
        abbr,
        tile: { status: "encoded", note: "encoded" },
        title: `${US_STATE_NAMES[abbr]} SNAP — encoded, not yet verified`,
      };
    }
    return {
      abbr,
      tile: null,
      title: `${US_STATE_NAMES[abbr]} SNAP — not encoded yet`,
    };
  });

  return (
    <div className="register-row">
      <div className="register-rowhead">
        <span className="register-rowlabel">{FAMILY_LABELS.snap}</span>
        <span className="mono register-rowcount">
          {verified} of {STATE_ORDER.length} states verified
          {measured.size > verified &&
            ` · ${measured.size - verified} diverging`}
        </span>
      </div>
      <div className="register-grid">
        {tiles.map(({ abbr, tile, title }) => (
          <Tile key={abbr} jurisdiction={abbr} tile={tile} title={title} />
        ))}
      </div>
    </div>
  );
}

function FamilyRow({ family, entries }) {
  return (
    <div className="register-row">
      <div className="register-rowhead">
        <span className="register-rowlabel">
          {FAMILY_LABELS[family] || family}
        </span>
      </div>
      <div className="register-grid">
        {entries.map(({ meta, metric }) => (
          <Tile
            key={meta.suite}
            jurisdiction={meta.jurisdiction || meta.label}
            wide
            tile={{ ...tileForMeasured(metric, meta.kind), suite: meta.suite }}
            title={
              metric.total > 0
                ? `${meta.label} — ${formatPct(metric.rate, 1)} agreement over ${metric.total.toLocaleString()} checks`
                : `${meta.label} — no case-level comparison yet`
            }
          />
        ))}
      </div>
    </div>
  );
}

const LEGEND = [
  { status: "verified", label: "Verified — engines agree on 99%+ of checks" },
  { status: "diverging", label: "Diverging — measured, mismatches under triage" },
  { status: "attention", label: "Needs attention — below 90% agreement" },
  { status: "encoded", label: "Encoded, not yet verified" },
  { status: "parameter", label: "Parameter check only" },
  { status: "diagnostic", label: "Diagnostic run" },
  { status: "gap", label: "Not encoded yet" },
];

export default function CoverageRegister({ reports, coverageOverview, region }) {
  const bySuite = buildSuiteIndex(reports);
  if (bySuite.size === 0) return null;

  // One tile per (family, jurisdiction): several diagnostic suites can probe
  // the same surface (e.g. NYC income tax), but the register answers "what is
  // covered where", not "how many runs exist".
  const byCell = new Map();
  for (const entry of bySuite.values()) {
    if (entry.meta.family === "snap") continue; // rendered as the state strip
    const cell = `${entry.meta.family}::${entry.meta.jurisdiction}`;
    const existing = byCell.get(cell);
    const better =
      !existing ||
      (existing.meta.kind === "diagnostic" && entry.meta.kind !== "diagnostic") ||
      (existing.meta.kind === entry.meta.kind &&
        entry.metric.total > existing.metric.total);
    if (better) byCell.set(cell, entry);
  }
  const families = new Map();
  for (const entry of byCell.values()) {
    if (!families.has(entry.meta.family)) families.set(entry.meta.family, []);
    families.get(entry.meta.family).push(entry);
  }
  const familyRows = [...families.entries()].sort(
    (a, b) =>
      Math.min(...a[1].map((e) => e.meta.order)) -
      Math.min(...b[1].map((e) => e.meta.order)),
  );

  const hasSnap = [...bySuite.values()].some((e) => e.meta.family === "snap");
  const usedStatuses = new Set();
  // Hatched "not encoded" tiles only appear on the 50-state SNAP strip.
  if (region === "us" && hasSnap) usedStatuses.add("gap");
  for (const entry of bySuite.values()) {
    usedStatuses.add(tileForMeasured(entry.metric, entry.meta.kind).status);
  }

  return (
    <section className="card-flat">
      <div className="section-head">
        <div>
          <div className="section-eyebrow">Coverage register</div>
          <div className="section-title">
            What is encoded, what is verified, and what remains
          </div>
        </div>
      </div>
      <div className="register-body">
        {region === "us" && hasSnap && (
          <SnapRow
            bySuite={bySuite}
            coveragePrograms={coverageOverview?.axiom?.programs}
          />
        )}
        {familyRows.map(([family, entries]) => (
          <FamilyRow key={family} family={family} entries={entries} />
        ))}
        <div className="register-legend">
          {LEGEND.filter((l) => usedStatuses.has(l.status)).map((l) => (
            <span key={l.status} className="register-legend-item">
              <span className={`register-swatch tile-${l.status}`} />
              {l.label}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
