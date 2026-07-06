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
 * The coverage register — a verification ledger. One glance answers
 * "where is Axiom verified, and where does it disagree?"
 *
 * One vocabulary throughout: a measured surface is a ledger line — label,
 * dotted leader, agreement rate in tabular numerals — followed by a red
 * sliver whose LENGTH is the share of checks that disagree (square-root
 * scale, so a 0.3% residual is visible and a 12% divergence is loud).
 * Clean agreement is quiet ink; the only color on the page is
 * disagreement. Encoded-but-unmeasured surfaces are a muted ○ list;
 * blocked last-good runs carry †; parameter-only checks carry ᵖ.
 *
 * Three groups: nationwide programs, the SNAP state ledger (the deepest
 * comparison, with a 51-cell spine keeping remaining work visible), and
 * per-state programs.
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
    if (
      !(report.aggregates || []).length &&
      !(report.summary?.alarms || []).length
    )
      continue;
    const meta = suiteMeta(report.suite);
    const key = `${meta.family}::${meta.jurisdiction}`;
    if (!cells.has(key)) cells.set(key, []);
    cells.get(key).push({
      meta,
      suite: report.suite,
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

// Row order for program families that only exist as coverage entries (no
// comparison run yet), aligned with the suite orders in utils/suites.js.
const FAMILY_FALLBACK_ORDER = {
  federal_income_tax: 10,
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
  if (program.jurisdiction === "UK") return "uk";
  if (program.jurisdiction === "CAN") return "ca";
  return "us";
}

/**
 * Programs the corpus has encoded but no comparison suite exercises yet.
 * They render as muted ○ entries so the register distinguishes
 * "not compared yet" from "not encoded".
 */
function addCoverageOnlyCells(cells, coveragePrograms, region) {
  for (const program of coveragePrograms || []) {
    if (!program.program || program.program === "snap") continue; // snap → spine
    if (coverageRegion(program) !== region) continue;
    const key = `${program.program}::${program.jurisdiction}`;
    if (cells.has(key)) continue;
    const label = FAMILY_LABELS[program.program] || program.program;
    cells.set(key, {
      meta: {
        family: program.program,
        jurisdiction: program.jurisdiction,
        label,
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

function staleMapFrom(knownCauses) {
  return new Map(
    (knownCauses || [])
      .filter((c) => c && (c.kind === "stale_run" || c.staleness_note))
      .map((c) => [c.suite, c.staleness_note || c.description || ""]),
  );
}

/**
 * Disagreement sliver width as a share of its track. Square-root scale
 * over the mismatch share: a 0.3% residual is visible, a 12% divergence
 * is loud, 100% fills the track. Zero disagreement draws nothing —
 * clean is quiet.
 */
function sliverWidth(rate) {
  if (rate == null || rate >= 100) return 0;
  const mismatch = Math.min(100, Math.max(0, 100 - rate));
  return Math.max(4, Math.round(Math.sqrt(mismatch) * 10));
}

function cellTooltip(cell, staleNote) {
  const lines = [cell.meta.label];
  for (const r of cell.runs) {
    const oracle = engineLabel(r.oracle);
    if (r.metric.total > 0) {
      lines.push(
        `vs ${oracle}: ${formatPct(r.metric.rate, 1)} agreement over ${r.metric.total.toLocaleString()} checks` +
          (r.metric.mismatches
            ? ` (${r.metric.mismatches.toLocaleString()} disagree)`
            : ""),
      );
    } else {
      lines.push(`vs ${oracle}: no case-level comparison yet`);
    }
  }
  if (!cell.runs.length) lines.push("encoded, not yet measured");
  if (cell.kind === "parameter") lines.push("parameter check, not household-level");
  if (cell.kind === "diagnostic") lines.push("diagnostic run, outside headline numbers");
  if (staleNote) lines.push(`Last-good run — regeneration blocked. ${staleNote}`);
  return lines.join("\n");
}

/** The rate figure: quiet ink when healthy, colored only when it needs eyes. */
function Rate({ rate, kind }) {
  if (kind === "diagnostic")
    return <span className="lg-rate lg-rate-word">diag</span>;
  if (rate == null) return <span className="lg-rate lg-rate-word">—</span>;
  const status = rateStatus(rate);
  return (
    <span className={`lg-rate${status !== "verified" ? ` lg-rate-${status}` : ""}`}>
      {formatPct(rate, 1).replace("%", "")}
    </span>
  );
}

function Sliver({ rate }) {
  const w = sliverWidth(rate);
  return (
    <span className="lg-sliver-track" aria-hidden="true">
      {w > 0 && <span className="lg-sliver" style={{ width: `${w}%` }} />}
    </span>
  );
}

function Marks({ stale, kind }) {
  return (
    <span className="lg-marks">
      {kind === "parameter" && <sup title="parameter check">ᵖ</sup>}
      {stale && <sup title="last-good run — regeneration blocked">†</sup>}
    </span>
  );
}

/** One ledger line: label ···· rate [sliver]. */
function LedgerLine({ label, cell, staleNote }) {
  const inner = (
    <>
      <span className="lg-label">{label}</span>
      <span className="lg-leader" aria-hidden="true" />
      <Rate rate={cell.combined.rate} kind={cell.kind} />
      <Marks stale={Boolean(staleNote)} kind={cell.kind} />
      <Sliver rate={cell.kind === "diagnostic" ? null : cell.combined.rate} />
    </>
  );
  const title = cellTooltip(cell, staleNote);
  return cell.anchor ? (
    <a className="lg-line" href={`#${cell.anchor}`} title={title}>
      {inner}
    </a>
  ) : (
    <span className="lg-line" title={title}>
      {inner}
    </span>
  );
}

/** Muted ○ list of encoded-but-unmeasured surfaces. */
function EncodedList({ items, title }) {
  if (!items.length) return null;
  return (
    <div className="lg-encoded mono" title={title}>
      <span className="lg-ring" aria-hidden="true">
        ○
      </span>{" "}
      encoded, not yet measured · {items.join(" · ")}
    </div>
  );
}

function GroupHead({ title, note }) {
  return (
    <div className="lg-grouphead">
      <span className="lg-grouptitle">{title}</span>
      <span className="lg-rule" aria-hidden="true" />
      {note && <span className="mono lg-groupnote">{note}</span>}
    </div>
  );
}

/* ── Nationwide ────────────────────────────────────────────────────── */

function NationwideGroup({ singles, staleBySuite }) {
  const measured = [];
  const encoded = [];
  for (const [family, cells] of singles) {
    const cell = cells[0];
    const label = FAMILY_LABELS[family] || cell.meta.label || family;
    if (cell.runs.length > 0) {
      const staleNote = cell.runs
        .map((r) => staleBySuite.get(r.suite ?? r.meta?.suite))
        .find(Boolean);
      measured.push({ family, label, cell, staleNote });
    } else {
      encoded.push(label.replace(/ \(.*\)$/, ""));
    }
  }
  measured.sort((a, b) => a.cell.meta.order - b.cell.meta.order);

  return (
    <div className="lg-group">
      <GroupHead
        title="Nationwide"
        note={`${measured.length} measured · ${encoded.length} encoded`}
      />
      <div className="lg-lines lg-lines-wide">
        {measured.map(({ family, label, cell, staleNote }) => (
          <LedgerLine
            key={family}
            label={label}
            cell={cell}
            staleNote={staleNote}
          />
        ))}
      </div>
      <EncodedList items={encoded} />
    </div>
  );
}

/* ── SNAP ──────────────────────────────────────────────────────────── */

function SnapGroup({ reports, coveragePrograms, staleBySuite }) {
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
    (a, b) =>
      (b.rate ?? -1) - (a.rate ?? -1) ||
      Number(Boolean(a.staleNote)) - Number(Boolean(b.staleNote)) ||
      a.abbr.localeCompare(b.abbr),
  );
  const remaining = STATE_ORDER.length - measured.size - encoded.length;
  const totalChecks = ranked.reduce((n, s) => n + s.total, 0);

  return (
    <div className="lg-group">
      <GroupHead
        title="SNAP, state by state"
        note={`${ranked.length} of ${STATE_ORDER.length} measured · ${totalChecks.toLocaleString()} checks`}
      />
      <div className="lg-lines lg-lines-snap">
        {ranked.map((s) => {
          const title = [
            `${US_STATE_NAMES[s.abbr]} SNAP vs ${s.oracle}`,
            `${formatPct(s.rate, 1)} agreement over ${s.total.toLocaleString()} checks (${s.cases.toLocaleString()} households)`,
            s.staleNote
              ? `Last-good run — regeneration blocked. ${s.staleNote}`
              : null,
          ]
            .filter(Boolean)
            .join("\n");
          const inner = (
            <>
              <span className="lg-label lg-label-code">{s.abbr}</span>
              <span className="lg-leader" aria-hidden="true" />
              <Rate rate={s.rate} kind="household" />
              <Marks stale={Boolean(s.staleNote)} kind="household" />
              <Sliver rate={s.rate} />
            </>
          );
          return s.anchor ? (
            <a key={s.abbr} className="lg-line" href={`#${s.anchor}`} title={title}>
              {inner}
            </a>
          ) : (
            <span key={s.abbr} className="lg-line" title={title}>
              {inner}
            </span>
          );
        })}
      </div>
      <EncodedList items={encoded} />
      <div className="lg-spine" aria-label="All-states SNAP status">
        {STATE_ORDER.map((abbr) => {
          const s = measured.get(abbr);
          const cls = s
            ? s.staleNote
              ? "lg-spine-stale"
              : "lg-spine-measured"
            : encodedSet.has(abbr)
              ? "lg-spine-encoded"
              : "lg-spine-gap";
          const title = s
            ? `${US_STATE_NAMES[abbr]} — ${formatPct(s.rate, 1)}${s.staleNote ? " (last-good, blocked)" : ""}`
            : encodedSet.has(abbr)
              ? `${US_STATE_NAMES[abbr]} — encoded, not yet measured`
              : `${US_STATE_NAMES[abbr]} — not encoded yet`;
          return <span key={abbr} className={`lg-spine-cell ${cls}`} title={title} />;
        })}
        <span className="mono lg-spine-note">
          {remaining} states not yet encoded
        </span>
      </div>
    </div>
  );
}

/* ── State programs ────────────────────────────────────────────────── */

function StateProgramRow({ family, cells, staleBySuite }) {
  const measured = cells
    .filter((c) => c.runs.length > 0 || c.kind === "diagnostic")
    .sort(
      (a, b) =>
        (b.combined.rate ?? -1) - (a.combined.rate ?? -1) ||
        (KIND_RANK[a.kind] ?? 9) - (KIND_RANK[b.kind] ?? 9) ||
        String(a.meta.jurisdiction).localeCompare(String(b.meta.jurisdiction)),
    );
  const encoded = cells
    .filter((c) => c.runs.length === 0 && c.kind !== "diagnostic")
    .map((c) => c.meta.jurisdiction || c.meta.label)
    .sort();

  const label = FAMILY_LABELS[family] || cells[0]?.meta?.label || family;

  return (
    <div className="lg-staterow">
      <span className="lg-label lg-staterow-label" title={label}>
        {label}
      </span>
      <span className="lg-staterow-entries">
        {measured.map((cell) => {
          const staleNote = cell.runs
            .map((r) => staleBySuite.get(r.suite))
            .find(Boolean);
          const inner = (
            <>
              <span className="lg-label-code">
                {cell.meta.jurisdiction || cell.meta.label}
              </span>{" "}
              <Rate rate={cell.combined.rate} kind={cell.kind} />
              <Marks stale={Boolean(staleNote)} kind={cell.kind} />
              <Sliver
                rate={cell.kind === "diagnostic" ? null : cell.combined.rate}
              />
            </>
          );
          const title = cellTooltip(cell, staleNote);
          return cell.anchor ? (
            <a
              key={cell.meta.jurisdiction || cell.meta.label}
              className="lg-entry"
              href={`#${cell.anchor}`}
              title={title}
            >
              {inner}
            </a>
          ) : (
            <span
              key={cell.meta.jurisdiction || cell.meta.label}
              className="lg-entry"
              title={title}
            >
              {inner}
            </span>
          );
        })}
        {encoded.length > 0 && (
          <span
            className="mono lg-entry-encoded"
            title={`Encoded, not yet measured:\n${encoded.join(", ")}`}
          >
            ○ {encoded.length <= 3 ? encoded.join(" · ") : `+${encoded.length}`}
          </span>
        )}
      </span>
    </div>
  );
}

/* ── Legend ────────────────────────────────────────────────────────── */

function Legend() {
  return (
    <div className="lg-legend mono">
      <span className="lg-legend-item">
        <span className="lg-rate lg-legend-rate">97.4</span> agreement rate
      </span>
      <span className="lg-legend-item">
        <span className="lg-sliver lg-legend-sliver" /> share of checks that
        disagree
      </span>
      <span className="lg-legend-item">
        <sup>†</sup> last-good run, regeneration blocked
      </span>
      <span className="lg-legend-item">
        <sup>ᵖ</sup> parameter check only
      </span>
      <span className="lg-legend-item">○ encoded, not yet measured</span>
    </div>
  );
}

/* ── Register ──────────────────────────────────────────────────────── */

export default function CoverageRegister({
  reports,
  coverageOverview,
  region,
  knownCauses,
}) {
  const cells = buildCells(reports);
  addCoverageOnlyCells(cells, coverageOverview?.axiom?.programs, region);
  if (cells.size === 0) return null;

  const staleBySuite = staleMapFrom(knownCauses);

  const families = new Map();
  for (const cell of cells.values()) {
    if (cell.meta.family === "snap") continue; // rendered as its own group
    if (!families.has(cell.meta.family)) families.set(cell.meta.family, []);
    families.get(cell.meta.family).push(cell);
  }
  const familyRows = [...families.entries()].sort(
    (a, b) =>
      Math.min(...a[1].map((c) => c.meta.order)) -
      Math.min(...b[1].map((c) => c.meta.order)),
  );
  const singles = familyRows.filter(([, c]) => c.length === 1);
  const multis = familyRows.filter(([, c]) => c.length > 1);
  const hasSnap = [...cells.values()].some((c) => c.meta.family === "snap");

  return (
    <section className="card-flat">
      <div className="section-head">
        <div>
          <div className="section-eyebrow">Coverage register</div>
          <div className="section-title">
            What is encoded, what is verified, and what disagrees
          </div>
        </div>
      </div>
      <div className="register-body lg-body">
        {singles.length > 0 && (
          <NationwideGroup singles={singles} staleBySuite={staleBySuite} />
        )}
        {region === "us" && hasSnap && (
          <SnapGroup
            reports={reports}
            coveragePrograms={coverageOverview?.axiom?.programs}
            staleBySuite={staleBySuite}
          />
        )}
        {multis.length > 0 && (
          <div className="lg-group">
            <GroupHead title="State programs" />
            <div className="lg-staterows">
              {multis.map(([family, familyCells]) => (
                <StateProgramRow
                  key={family}
                  family={family}
                  cells={familyCells}
                  staleBySuite={staleBySuite}
                />
              ))}
            </div>
          </div>
        )}
        <Legend />
      </div>
    </section>
  );
}
