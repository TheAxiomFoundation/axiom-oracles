"use client";

import { formatPct, formatAgreementRate, engineLabel } from "../utils/format";
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
 * The coverage register — one glance answers "where is Axiom verified, and
 * where are the gaps?"
 *
 * Rows are program families; cells are jurisdictions. A tile is:
 *  - tinted with its agreement rate when verification runs exist,
 *  - outlined when the program is encoded but not yet measured,
 *  - hatched when nothing is encoded there yet.
 *
 * A cell aggregates every oracle Axiom was checked against there (e.g. a
 * federal-income-tax cell can combine PolicyEngine and TAXSIM runs); the
 * tooltip breaks the rate out per oracle. The SNAP row deliberately shows
 * all 50 states + DC so remaining work is as visible as finished work.
 */

const STATE_ORDER = Object.keys(US_STATE_NAMES);

// When a surface has both real verification runs and diagnostic probes,
// the register reports the most authoritative kind only.
const KIND_RANK = { household: 0, parameter: 1, coverage: 2, diagnostic: 3 };

/**
 * Group axiom-pair reports into register cells keyed by
 * (family, jurisdiction), keeping only the most authoritative run kind per
 * cell and combining metrics across oracle pairs of that kind.
 */
function buildCells(reports) {
  const cells = new Map();
  for (const report of reports || []) {
    if (!isAxiomPair(report)) continue;
    if (!(report.aggregates || []).length && !(report.summary?.alarms || []).length)
      continue;
    const meta = suiteMeta(report.suite);
    const key = `${meta.family}::${meta.jurisdiction}`;
    if (!cells.has(key)) cells.set(key, []);
    cells.get(key).push({
      meta,
      metric: reportMetric(report),
      oracle: otherOracle(report),
      anchor: runAnchor(report),
    });
  }

  const out = new Map();
  for (const [key, runs] of cells) {
    const bestRank = Math.min(...runs.map((r) => KIND_RANK[r.meta.kind] ?? 9));
    const kept = runs.filter((r) => (KIND_RANK[r.meta.kind] ?? 9) === bestRank);
    let total = 0;
    let mismatches = 0;
    for (const r of kept) {
      total += r.metric.total;
      mismatches += r.metric.mismatches;
    }
    const combined = {
      total,
      mismatches,
      rate: total > 0 ? ((total - mismatches) / total) * 100 : null,
    };
    // Link to the run that most needs attention.
    const worst = [...kept].sort(
      (a, b) => (a.metric.rate ?? 101) - (b.metric.rate ?? 101),
    )[0];
    out.set(key, {
      meta: worst.meta,
      kind: worst.meta.kind,
      runs: kept,
      combined,
      anchor: worst.anchor,
    });
  }
  return out;
}

function cellTile(cell) {
  if (cell.kind === "parameter") {
    return {
      status: "parameter",
      note:
        cell.combined.total > 0
          ? formatAgreementRate(cell.combined.rate, cell.combined.mismatches)
          : "parameters",
    };
  }
  if (cell.kind === "coverage") return { status: "encoded", note: "encoded" };
  if (cell.kind === "diagnostic") return { status: "diagnostic", note: "diagnostic" };
  return {
    status: rateStatus(cell.combined.rate),
    note: formatAgreementRate(cell.combined.rate, cell.combined.mismatches),
  };
}

function cellTitle(cell) {
  if (!cell.runs.length) {
    return `${cell.meta.label} — encoded, not yet verified${cell.source ? `\n${cell.source}` : ""}`;
  }
  const lines = cell.runs.map((r) => {
    const oracle = engineLabel(r.oracle);
    if (r.metric.total > 0) {
      return `vs ${oracle}: ${formatPct(r.metric.rate, 1)} agreement over ${r.metric.total.toLocaleString()} checks`;
    }
    return `vs ${oracle}: no case-level comparison yet`;
  });
  return `${cell.meta.label}\n${lines.join("\n")}`;
}

// Row order for program families that only exist as coverage entries (no
// comparison run yet), aligned with the suite orders in utils/suites.js.
const FAMILY_FALLBACK_ORDER = {
  federal_income_tax: 10,
  social_security: 20,
  snap: 100,
  state_income_tax: 200,
  medicaid_chip_bhp_thresholds: 210,
  medicaid_eligibility_groups: 215,
  tanf: 220,
  nyc_income_tax: 400,
};

function coverageRegion(program) {
  return program.jurisdiction === "UK" ? "uk" : "us";
}

/**
 * Programs the corpus has encoded but no comparison suite exercises yet.
 * They render as outlined "encoded" cells so the register distinguishes
 * "not compared yet" from "not encoded".
 */
function addCoverageOnlyCells(cells, coveragePrograms, region) {
  for (const program of coveragePrograms || []) {
    if (!program.program || program.program === "snap") continue; // snap → state strip
    if (coverageRegion(program) !== region) continue;
    const key = `${program.program}::${program.jurisdiction}`;
    if (cells.has(key)) continue;
    const label = FAMILY_LABELS[program.program] || program.program;
    cells.set(key, {
      meta: {
        family: program.program,
        jurisdiction: program.jurisdiction,
        label:
          program.jurisdiction && !["US", "UK"].includes(program.jurisdiction)
            ? `${US_STATE_NAMES[program.jurisdiction] || program.jurisdiction} ${label}`
            : label,
        order: FAMILY_FALLBACK_ORDER[program.program] ?? 450,
        kind: program.status === "parameter" ? "parameter" : "coverage",
      },
      kind: program.status === "parameter" ? "parameter" : "coverage",
      runs: [],
      combined: { total: 0, mismatches: 0, rate: null },
      anchor: null,
      source: program.source,
    });
  }
}

function Tile({ jurisdiction, title, tile, anchor, wide = false }) {
  const status = tile?.status || "gap";
  const body = (
    <>
      <span className="tile-code">{jurisdiction}</span>
      {tile?.note && <span className="tile-rate">{tile.note}</span>}
    </>
  );
  const cls = `register-tile tile-${status}${wide ? " register-tile-wide" : ""}`;
  if (anchor) {
    return (
      <a className={cls} href={`#${anchor}`} title={title}>
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

function SnapRow({ cells, coveragePrograms }) {
  const measured = new Map();
  for (const cell of cells.values()) {
    if (cell.meta.family === "snap" && cell.meta.jurisdiction) {
      measured.set(cell.meta.jurisdiction, cell);
    }
  }
  const encoded = new Set(
    (coveragePrograms || [])
      .filter((p) => p.program === "snap" && p.jurisdiction)
      .map((p) => p.jurisdiction),
  );

  let verified = 0;
  const tiles = STATE_ORDER.map((abbr) => {
    const cell = measured.get(abbr);
    if (cell) {
      const tile = cellTile(cell);
      if (tile.status === "verified") verified += 1;
      return { abbr, tile, anchor: cell.anchor, title: cellTitle(cell) };
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
        {tiles.map(({ abbr, tile, title, anchor }) => (
          <Tile
            key={abbr}
            jurisdiction={abbr}
            tile={tile}
            title={title}
            anchor={anchor}
          />
        ))}
      </div>
    </div>
  );
}

function FamilyRow({ family, cells }) {
  return (
    <div className="register-row">
      <div className="register-rowhead">
        <span className="register-rowlabel">
          {FAMILY_LABELS[family] || family}
        </span>
      </div>
      <div className="register-grid">
        {cells.map((cell) => (
          <Tile
            key={`${cell.meta.family}-${cell.meta.jurisdiction}`}
            jurisdiction={cell.meta.jurisdiction || cell.meta.label}
            wide
            tile={cellTile(cell)}
            anchor={cell.anchor}
            title={cellTitle(cell)}
          />
        ))}
      </div>
    </div>
  );
}

const LEGEND = [
  { status: "verified", label: "Verified — engines agree on 90%+ of checks" },
  { status: "diverging", label: "Diverging — 70–90% agreement, under triage" },
  { status: "attention", label: "Needs attention — below 70% agreement" },
  { status: "encoded", label: "Encoded, not yet verified" },
  { status: "parameter", label: "Parameter check only" },
  { status: "diagnostic", label: "Diagnostic run" },
  { status: "gap", label: "Not encoded yet" },
];

export default function CoverageRegister({ reports, coverageOverview, region }) {
  const cells = buildCells(reports);
  addCoverageOnlyCells(cells, coverageOverview?.axiom?.programs, region);
  if (cells.size === 0) return null;

  const families = new Map();
  for (const cell of cells.values()) {
    if (cell.meta.family === "snap") continue; // rendered as the state strip
    if (!families.has(cell.meta.family)) families.set(cell.meta.family, []);
    families.get(cell.meta.family).push(cell);
  }
  const familyRows = [...families.entries()].sort(
    (a, b) =>
      Math.min(...a[1].map((c) => c.meta.order)) -
      Math.min(...b[1].map((c) => c.meta.order)),
  );

  const hasSnap = [...cells.values()].some((c) => c.meta.family === "snap");
  const usedStatuses = new Set();
  // Hatched "not encoded" tiles only appear on the 50-state SNAP strip.
  if (region === "us" && hasSnap) usedStatuses.add("gap");
  for (const cell of cells.values()) {
    usedStatuses.add(cellTile(cell).status);
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
        {/* Families ordered before SNAP (order < 100, i.e. federal income
            tax) render above the state strip; the rest follow it. */}
        {familyRows
          .filter(([, c]) => Math.min(...c.map((x) => x.meta.order)) < 100)
          .map(([family, familyCells]) => (
            <FamilyRow key={family} family={family} cells={familyCells} />
          ))}
        {region === "us" && hasSnap && (
          <SnapRow
            cells={cells}
            coveragePrograms={coverageOverview?.axiom?.programs}
          />
        )}
        {familyRows
          .filter(([, c]) => Math.min(...c.map((x) => x.meta.order)) >= 100)
          .map(([family, familyCells]) => (
            <FamilyRow key={family} family={family} cells={familyCells} />
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
