"use client";

import { formatPct, engineLabel } from "../utils/format";
import {
  US_STATE_NAMES,
  FAMILY_LABELS,
  suiteMeta,
  reportMetric,
  rateStatus,
  isAxiomPair,
  otherOracle,
  runAnchor,
} from "../utils/suites";

/**
 * The coverage register — a pure coverage tracker. Rows are program
 * families, cells are jurisdictions, and a cell has exactly three
 * states: measured against an oracle, encoded but not yet measured, or
 * not encoded yet. Agreement numbers live in the run breakdowns below;
 * this board only answers "how far has the corpus spread?"
 *
 * Everything is derived from data — the coverage inventory that
 * scripts/sync_encoded_coverage.py regenerates from upstream, plus the
 * comparison reports. A newly encoded program appears here on the next
 * sync without touching this component: unknown families get a
 * prettified label, and rows sort by how covered they are.
 */

const STATE_ORDER = Object.keys(US_STATE_NAMES);
const STATE_SET = new Set(STATE_ORDER);

// Fallback label for families the hand-curated map doesn't know yet, so
// new programs render decently the moment the coverage sync emits them.
const ACRONYMS = new Set([
  "snap",
  "ssi",
  "tanf",
  "chip",
  "bhp",
  "nyc",
  "us",
  "ira",
  "prwora",
  "cfr",
  "usc",
  "oasdi",
]);
function labelForFamily(family) {
  if (FAMILY_LABELS[family]) return FAMILY_LABELS[family];
  return String(family)
    .split(/[_-]+/)
    .map((w) => (ACRONYMS.has(w) ? w.toUpperCase() : w))
    .join(" ")
    .replace(/^./, (c) => c.toUpperCase());
}

function coverageRegion(program) {
  if (program.jurisdiction === "UK") return "uk";
  if (program.jurisdiction === "CAN") return "ca";
  return "us";
}

/**
 * Build the tracker's model: family → jurisdiction → cell.
 * Measured cells come from axiom-pair reports; encoded cells from the
 * synced coverage inventory. Measured wins when both exist.
 */
function buildBoard(reports, coveragePrograms, region) {
  const families = new Map();
  const cell = (family, jurisdiction) => {
    if (!families.has(family)) families.set(family, new Map());
    const row = families.get(family);
    if (!row.has(jurisdiction)) row.set(jurisdiction, {});
    return row.get(jurisdiction);
  };

  // A household run outranks a parameter probe outranks a diagnostic.
  const rank = { household: 0, parameter: 1, diagnostic: 2 };
  for (const report of reports || []) {
    if (!isAxiomPair(report)) continue;
    if (!(report.aggregates || []).length) continue;
    const meta = suiteMeta(report.suite);
    if (meta.region !== region || !meta.family || !meta.jurisdiction) continue;
    const metric = reportMetric(report);
    const c = cell(meta.family, meta.jurisdiction);
    if (c.measured && (rank[c.kind] ?? 9) <= (rank[meta.kind] ?? 9)) continue;
    c.measured = true;
    c.kind = meta.kind;
    c.rate = metric.rate;
    c.checks = metric.total;
    c.anchor = runAnchor(report);
    c.oracle = engineLabel(otherOracle(report));
  }

  for (const program of coveragePrograms || []) {
    if (!program.program || !program.jurisdiction) continue;
    if (coverageRegion(program) !== region) continue;
    const c = cell(program.program, program.jurisdiction);
    if (!c.measured) c.encoded = true;
  }

  return families;
}

function cellState(c) {
  if (!c) return "none";
  if (c.measured) {
    if (c.kind === "diagnostic") return "encoded";
    return rateStatus(c.rate) === "verified" ? "measured" : "issue";
  }
  return c.encoded ? "encoded" : "none";
}

function cellTitle(family, jurisdiction, c) {
  const where = US_STATE_NAMES[jurisdiction] || jurisdiction;
  const label = labelForFamily(family);
  if (!c) return `${where} — ${label}: not encoded yet`;
  if (c.measured && c.kind !== "diagnostic") {
    const kind = c.kind === "parameter" ? "parameter check" : "measured";
    return `${where} — ${label}: ${kind} vs ${c.oracle}, ${formatPct(c.rate, 1)} over ${Number(c.checks || 0).toLocaleString()} checks`;
  }
  if (c.measured) return `${where} — ${label}: diagnostic run only`;
  return `${where} — ${label}: encoded, not yet measured`;
}

function Cell({ family, jurisdiction, c, wide }) {
  const state = cellState(c);
  const cls = `cov-cell cov-${state}${wide ? " cov-cell-wide" : ""}`;
  const title = cellTitle(family, jurisdiction, c);
  const body = wide ? (
    <span className="cov-cell-code">{jurisdiction}</span>
  ) : null;
  return c?.anchor ? (
    <a className={cls} href={`#${c.anchor}`} title={title}>
      {body}
    </a>
  ) : (
    <span className={cls} title={title}>
      {body}
    </span>
  );
}

/* ── Nationwide checklist ──────────────────────────────────────────── */

function NationwideList({ rows }) {
  return (
    <div className="cov-nationwide">
      {rows.map(({ family, row }) => {
        const jurisdiction = row.keys().next().value;
        const c = row.get(jurisdiction);
        const state = cellState(c);
        const title = cellTitle(family, jurisdiction, c);
        const inner = (
          <>
            <span className={`cov-dot cov-${state}`} aria-hidden="true" />
            <span className="cov-name">{labelForFamily(family)}</span>
          </>
        );
        return c?.anchor ? (
          <a
            key={family}
            className="cov-item"
            href={`#${c.anchor}`}
            title={title}
          >
            {inner}
          </a>
        ) : (
          <span key={family} className="cov-item" title={title}>
            {inner}
          </span>
        );
      })}
    </div>
  );
}

/* ── State rows ────────────────────────────────────────────────────── */

function StateRow({ family, row }) {
  const extras = [...row.keys()].filter((j) => !STATE_SET.has(j)).sort();
  let measured = 0;
  let encoded = 0;
  for (const j of row.keys()) {
    const s = cellState(row.get(j));
    if (s === "measured" || s === "issue") measured += 1;
    else if (s === "encoded") encoded += 1;
  }
  const summary = [
    measured > 0 && `${measured} measured`,
    encoded > 0 && `${encoded} encoded`,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="cov-row">
      <span className="cov-name cov-row-label" title={labelForFamily(family)}>
        {labelForFamily(family)}
      </span>
      <span className="cov-strip">
        {STATE_ORDER.map((abbr) => (
          <Cell
            key={abbr}
            family={family}
            jurisdiction={abbr}
            c={row.get(abbr)}
          />
        ))}
        {/* Non-state jurisdictions (US-level framework, NYC) trail the
            strip so the 51 state columns align across every row. */}
        {extras.map((j) => (
          <Cell key={j} family={family} jurisdiction={j} c={row.get(j)} wide />
        ))}
      </span>
      <span className="mono cov-row-count">{summary}</span>
    </div>
  );
}

/* ── Register ──────────────────────────────────────────────────────── */

export default function CoverageTracker({
  reports,
  coverageOverview,
  region,
}) {
  const board = buildBoard(reports, coverageOverview?.axiom?.programs, region);
  if (board.size === 0) return null;

  const stateRows = [];
  const nationwideRows = [];
  for (const [family, row] of board) {
    const hasStates = [...row.keys()].some((j) => STATE_SET.has(j));
    (hasStates ? stateRows : nationwideRows).push({ family, row });
  }

  const measuredCount = (row) =>
    [...row.values()].filter((c) =>
      ["measured", "issue"].includes(cellState(c)),
    ).length;
  const encodedCount = (row) =>
    [...row.values()].filter((c) => cellState(c) === "encoded").length;

  // Most-covered rows first; label as the stable tiebreak, so a newly
  // encoded program simply joins the board where its coverage puts it.
  const byCoverage = (a, b) =>
    measuredCount(b.row) - measuredCount(a.row) ||
    encodedCount(b.row) - encodedCount(a.row) ||
    labelForFamily(a.family).localeCompare(labelForFamily(b.family));
  stateRows.sort(byCoverage);
  nationwideRows.sort(byCoverage);

  const totals = { measured: 0, encoded: 0 };
  for (const { row } of [...stateRows, ...nationwideRows]) {
    totals.measured += measuredCount(row);
    totals.encoded += encodedCount(row);
  }

  return (
    <section className="card-flat">
      <div className="section-head">
        <div>
          <div className="section-eyebrow">Coverage tracker</div>
          <div className="section-title">
            What is encoded, what is measured, and what remains
          </div>
        </div>
        <span className="mono cov-totals">
          {board.size} programs · {totals.measured} surfaces measured ·{" "}
          {totals.encoded} encoded
        </span>
      </div>
      <div className="register-body cov-body">
        {nationwideRows.length > 0 && <NationwideList rows={nationwideRows} />}
        {stateRows.length > 0 && (
          <div className="cov-rows">
            {stateRows.map(({ family, row }) => (
              <StateRow key={family} family={family} row={row} />
            ))}
          </div>
        )}
        <div className="cov-legend mono">
          <span className="cov-legend-item">
            <span className="cov-cell cov-measured" /> measured against an
            oracle
          </span>
          <span className="cov-legend-item">
            <span className="cov-cell cov-issue" /> measured, under 90%
          </span>
          <span className="cov-legend-item">
            <span className="cov-cell cov-encoded" /> encoded, not yet
            measured
          </span>
          <span className="cov-legend-item">
            <span className="cov-cell cov-none" /> not encoded yet
          </span>
        </div>
      </div>
    </section>
  );
}
