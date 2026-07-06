"use client";

import { formatPct, formatAgreementRate, engineLabel } from "../utils/format";
import {
  US_STATE_NAMES,
  JURISDICTION_LABELS,
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
 * tooltip breaks the rate out per oracle.
 *
 * The register targets a single screen: nationwide single-cell families
 * flow together as one chip strip, encoded-only masses collapse to a
 * "+N states encoded" chip, and SNAP renders as a ranked comparison
 * panel whose 51-cell micro-strip keeps remaining work as visible as
 * finished work.
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
  canada_personal_income_tax: 12,
  canada_family_benefits: 14,
  social_security: 20,
  ssi: 25,
  state_ssi_supplement: 26,
  snap_federal: 90,
  snap: 100,
  state_income_tax: 200,
  medicaid_chip_bhp_thresholds: 210,
  medicaid_eligibility_groups: 215,
  chip: 216,
  medicare: 230,
  tanf: 220,
  childcare_assistance: 270,
  pell_grant: 240,
  immigrant_eligibility: 250,
  energy_rebates: 260,
  head_start: 280,
  lifeline: 290,
  nyc_income_tax: 400,
  other_federal: 460,
};

function coverageRegion(program) {
  if (program.jurisdiction === "CAN") return "ca";
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
    const jurisdictionLabel = JURISDICTION_LABELS[program.jurisdiction] || program.jurisdiction;
    cells.set(key, {
      meta: {
        family: program.program,
        jurisdiction: program.jurisdiction,
        label:
          program.jurisdiction && !["US", "UK"].includes(program.jurisdiction)
            ? `${jurisdictionLabel} ${label}`
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

/**
 * The SNAP comparison panel: every measured state as a ranked agreement
 * bar (rate, blocked-run marker, household count), an encoded-not-yet-
 * measured line, and a one-row micro-strip of all 51 jurisdictions so
 * remaining work stays as visible as finished work without four wrapped
 * rows of tiles.
 */
function SnapPanel({ reports, coveragePrograms, knownCauses }) {
  const staleBySuite = new Map(
    (knownCauses || [])
      .filter((c) => c && (c.kind === "stale_run" || c.staleness_note))
      .map((c) => [c.suite, c.staleness_note || c.description || ""]),
  );

  const measured = new Map();
  for (const report of reports || []) {
    if (!isAxiomPair(report)) continue;
    const meta = suiteMeta(report.suite);
    if (meta.family !== "snap" || !meta.jurisdiction) continue;
    if (!(report.aggregates || []).length) continue;
    const metric = reportMetric(report);
    measured.set(meta.jurisdiction, {
      abbr: meta.jurisdiction,
      rate: metric.rate,
      total: metric.total,
      cases: report.case_count || 0,
      anchor: runAnchor(report),
      oracle: engineLabel(otherOracle(report)),
      staleNote: staleBySuite.get(report.suite),
    });
  }

  const encoded = (coveragePrograms || [])
    .filter(
      (p) =>
        p.program === "snap" &&
        p.jurisdiction &&
        !measured.has(p.jurisdiction),
    )
    .map((p) => p.jurisdiction)
    .sort();
  const encodedSet = new Set(encoded);

  const ranked = [...measured.values()].sort(
    (a, b) => (b.rate ?? -1) - (a.rate ?? -1),
  );
  const verified = ranked.filter(
    (s) => rateStatus(s.rate) === "verified",
  ).length;
  const remaining = STATE_ORDER.filter(
    (abbr) => !measured.has(abbr) && !encodedSet.has(abbr),
  ).length;

  const compactCases = (n) =>
    n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);

  return (
    <div className="register-row">
      <div className="register-rowhead">
        <span className="register-rowlabel">{FAMILY_LABELS.snap}</span>
        <span className="mono register-rowcount">
          {ranked.length} of {STATE_ORDER.length} states measured · {verified}{" "}
          verified
          {ranked.length > verified &&
            ` · ${ranked.length - verified} diverging`}
          {encoded.length > 0 && ` · ${encoded.length} encoded`}
          {remaining > 0 && ` · ${remaining} remaining`}
        </span>
      </div>

      <div className="snapx-grid">
        {ranked.map((s) => {
          const status = rateStatus(s.rate);
          const title = [
            `${US_STATE_NAMES[s.abbr]} SNAP vs ${s.oracle}`,
            `${formatPct(s.rate, 1)} agreement over ${s.total.toLocaleString()} checks (${s.cases.toLocaleString()} households)`,
            s.staleNote
              ? `Last-good run — regeneration blocked. ${s.staleNote}`
              : null,
          ]
            .filter(Boolean)
            .join("\n");
          const body = (
            <>
              <span className="tile-code snapx-code">{s.abbr}</span>
              <span
                className={`snapx-bar${s.staleNote ? " snapx-bar-stale" : ""}`}
              >
                <span
                  className={`snapx-fill tile-${status}`}
                  style={{ width: `${Math.max(3, s.rate ?? 0)}%` }}
                />
              </span>
              <span className="mono snapx-rate">
                {formatPct(s.rate, 1)}
                {s.staleNote && <sup className="snapx-stale">†</sup>}
              </span>
              <span className="mono snapx-count">{compactCases(s.cases)}</span>
            </>
          );
          return s.anchor ? (
            <a
              key={s.abbr}
              className="snapx-row"
              href={`#${s.anchor}`}
              title={title}
            >
              {body}
            </a>
          ) : (
            <span key={s.abbr} className="snapx-row" title={title}>
              {body}
            </span>
          );
        })}
      </div>

      {encoded.length > 0 && (
        <div className="mono snapx-encoded">
          encoded, not yet measured · {encoded.join(" · ")}
        </div>
      )}

      <div className="snapx-strip" aria-label="All-states SNAP status">
        {STATE_ORDER.map((abbr) => {
          const s = measured.get(abbr);
          const status = s
            ? rateStatus(s.rate)
            : encodedSet.has(abbr)
              ? "encoded"
              : "gap";
          const title = s
            ? `${US_STATE_NAMES[abbr]} — ${formatPct(s.rate, 1)}${s.staleNote ? " (last-good, blocked)" : ""}`
            : encodedSet.has(abbr)
              ? `${US_STATE_NAMES[abbr]} — encoded, not yet measured`
              : `${US_STATE_NAMES[abbr]} — not encoded yet`;
          return (
            <span
              key={abbr}
              className={`snapx-cell tile-${status}`}
              title={title}
            />
          );
        })}
        <span className="snapx-strip-note">
          {ranked.length + encoded.length} of {STATE_ORDER.length}
        </span>
      </div>
    </div>
  );
}

// Above this many encoded-only cells, a family row collapses them into a
// single "+N states encoded" chip — 48 identical outline tiles say nothing
// four tiles and a count don't.
const ENCODED_COLLAPSE_THRESHOLD = 4;

function FamilyRow({ family, cells }) {
  const measured = cells.filter(
    (cell) => cell.runs.length > 0 || cell.kind !== "coverage",
  );
  const encodedOnly = cells.filter(
    (cell) => cell.runs.length === 0 && cell.kind === "coverage",
  );
  const collapse = encodedOnly.length > ENCODED_COLLAPSE_THRESHOLD;
  const shown = collapse ? measured : cells;
  const encodedCodes = encodedOnly
    .map((cell) => cell.meta.jurisdiction || cell.meta.label)
    .sort();

  return (
    <div className="register-row">
      <div className="register-rowhead">
        <span className="register-rowlabel">
          {FAMILY_LABELS[family] || cells[0]?.meta?.label || family}
        </span>
      </div>
      <div className="register-grid">
        {shown.map((cell) => (
          <Tile
            key={`${cell.meta.family}-${cell.meta.jurisdiction}`}
            jurisdiction={cell.meta.jurisdiction || cell.meta.label}
            wide
            tile={cellTile(cell)}
            anchor={cell.anchor}
            title={cellTitle(cell)}
          />
        ))}
        {collapse && (
          <span
            className="register-tile register-tile-wide tile-encoded register-chip"
            title={`Encoded, not yet measured:\n${encodedCodes.join(", ")}`}
          >
            <span className="tile-code">
              +{encodedOnly.length} states encoded
            </span>
          </span>
        )}
      </div>
    </div>
  );
}

/**
 * Families with a single nationwide cell (federal income tax, Medicare,
 * Pell…) don't need a labeled row each — thirteen rows of one "US" tile
 * was most of the register's height. They flow together as one strip of
 * program chips, ordered like the rows they replace.
 */
function NationwideStrip({ singles }) {
  return (
    <div className="register-row">
      <div className="register-rowhead">
        <span className="register-rowlabel">Nationwide programs</span>
        <span className="mono register-rowcount">
          {singles.length} programs · one jurisdiction each
        </span>
      </div>
      <div className="register-grid">
        {singles.map(([family, cells]) => {
          const cell = cells[0];
          const label = FAMILY_LABELS[family] || cell.meta.label || family;
          return (
            <Tile
              key={family}
              jurisdiction={label}
              wide
              tile={cellTile(cell)}
              anchor={cell.anchor}
              title={cellTitle(cell)}
            />
          );
        })}
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

export default function CoverageRegister({
  reports,
  coverageOverview,
  region,
  knownCauses,
}) {
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
        {/* Single-jurisdiction families flow together as one strip; families
            with several jurisdictions keep their own row. The strip leads
            (it opens with federal income tax), then SNAP, then the rest. */}
        {(() => {
          const singles = familyRows.filter(([, c]) => c.length === 1);
          const multis = familyRows.filter(([, c]) => c.length > 1);
          return (
            <>
              {singles.length > 0 && <NationwideStrip singles={singles} />}
              {region === "us" && hasSnap && (
                <SnapPanel
                  reports={reports}
                  coveragePrograms={coverageOverview?.axiom?.programs}
                  knownCauses={knownCauses}
                />
              )}
              {multis.map(([family, familyCells]) => (
                <FamilyRow key={family} family={family} cells={familyCells} />
              ))}
            </>
          );
        })()}
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
