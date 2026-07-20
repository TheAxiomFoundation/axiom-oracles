"use client";

import { useState } from "react";
import { engineLabel, formatAgreementRate } from "../utils/format";
import { rateColor } from "../utils/colors";
import { buildProgramRows, rowVerdict } from "../utils/programs";
import {
  US_STATE_NAMES,
  FAMILY_LABELS,
  rateStatus,
  programKey,
} from "../utils/suites";

/**
 * The overview's program table, grouped by program family so 40+ rows read
 * as ~a dozen programs. Each row leads with one scannable verdict — a status
 * dot and the program-level roll-up rate — with the per-oracle breakdown as
 * supporting detail. Multi-jurisdiction families collapse behind a header
 * carrying the family roll-up; a family opens by default whenever a member
 * is diverging, so the broken thing is never folded away. A toolbar (text
 * search + status tiers) keeps the table navigable as the program count
 * grows. Every program row is a door into the program page, where the run
 * detail, triangulation, and case explorer live.
 */

const TIERS = [
  { id: "all", label: "All" },
  { id: "verified", label: "Verified" },
  { id: "flagged", label: "Flagged" },
  { id: "params", label: "Parameter-only" },
];

function matchesTier(row, tier) {
  if (tier === "all") return true;
  if (tier === "params") return row.total === 0 && (row.paramTotal || 0) > 0;
  const status = rateStatus(rowVerdict(row).rate);
  if (tier === "flagged") return status !== "verified";
  return status === tier;
}

function matchesQuery(row, query) {
  if (!query) return true;
  const hay = [
    row.meta.label,
    US_STATE_NAMES[row.meta.jurisdiction] || row.meta.jurisdiction || "",
    FAMILY_LABELS[row.meta.family] || row.meta.family || "",
  ]
    .join(" ")
    .toLowerCase();
  return hay.includes(query.toLowerCase());
}

function OracleRate({ run, tagged }) {
  const near = run.near;
  const title = [
    `${run.metric.mismatches.toLocaleString()} of ${run.metric.total.toLocaleString()} checks disagree`,
    near ? `${near.rate.toFixed(1)}% within $${near.threshold}` : null,
    run.kind === "parameter"
      ? "parameter-value check, not household-level"
      : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <span className="pst-oracle" title={title}>
      {tagged && <span className="pst-oracle-kind">params</span>}
      <span
        className="mono pst-oracle-rate"
        style={{ color: rateColor(run.metric.rate) }}
      >
        {formatAgreementRate(run.metric.rate, run.metric.mismatches)}
      </span>
    </span>
  );
}

function OracleBreakdown({ runs }) {
  const byOracle = new Map();
  for (const run of runs) {
    if (run.metric.rate == null) continue;
    if (!byOracle.has(run.oracle)) byOracle.set(run.oracle, []);
    byOracle.get(run.oracle).push(run);
  }
  return [...byOracle.entries()]
    .sort(
      (a, b) =>
        Math.max(...b[1].map((r) => r.metric.total)) -
        Math.max(...a[1].map((r) => r.metric.total)),
    )
    .map(([oracle, oracleRuns]) => {
      // Household rate first; a parameter probe rides along as "params N%".
      // When the program is ONLY a parameter check the checks column already
      // says so — no tag.
      const ordered = oracleRuns.sort((a, b) =>
        a.kind === b.kind
          ? b.metric.total - a.metric.total
          : a.kind === "household"
            ? -1
            : 1,
      );
      const mixed = ordered.some((r) => r.kind === "household");
      return (
        <span key={oracle} className="pst-oracle-group">
          <span className="pst-oracle-name">{engineLabel(oracle)}</span>
          {ordered.map((run, i) => (
            <span key={run.suite} className="pst-oracle-run">
              {i > 0 && (
                <span className="pst-oracle-sep" aria-hidden="true">
                  ·
                </span>
              )}
              <OracleRate
                run={run}
                tagged={mixed && run.kind === "parameter"}
              />
            </span>
          ))}
        </span>
      );
    });
}

function checksLabel(total, paramTotal) {
  if (total > 0) return `${total.toLocaleString()} checks`;
  const n = paramTotal || 0;
  return `${n.toLocaleString()} parameter ${n === 1 ? "check" : "checks"}`;
}

function ProgramRow({ row, nested, onOpen }) {
  const verdict = rowVerdict(row);
  const where = US_STATE_NAMES[row.meta.jurisdiction] || row.meta.jurisdiction;
  return (
    <button
      type="button"
      className={`pst-row${nested ? " pst-row-nested" : ""}`}
      onClick={() => onOpen(programKey(row.meta))}
      title={`Open ${row.meta.label}`}
    >
      <span className="pst-label">
        <span
          className="pst-dot"
          style={{ background: rateColor(verdict.rate) }}
          aria-hidden="true"
        />
        {row.meta.label}
      </span>
      <span className="mono pst-where">{where}</span>
      <span className="pst-oracles">
        <OracleBreakdown runs={row.runs} />
      </span>
      <span className="mono pst-checks">
        {checksLabel(row.total, row.paramTotal)}
      </span>
      <span
        className="mono pst-rate"
        style={{ color: rateColor(verdict.rate) }}
      >
        {formatAgreementRate(verdict.rate, verdict.mismatches)}
      </span>
      <span className="pst-arrow" aria-hidden="true">
        →
      </span>
    </button>
  );
}

function FamilyGroup({ group, open, onToggle, onOpen }) {
  const worst = group.members[0]; // members are sorted worst-first
  const worstVerdict = rowVerdict(worst);
  const allStates = group.members.every(
    (m) => US_STATE_NAMES[m.meta.jurisdiction],
  );
  return (
    <div className="pst-group">
      <button
        type="button"
        className="pst-row pst-group-head"
        onClick={onToggle}
        aria-expanded={open}
        title={`${open ? "Collapse" : "Expand"} ${group.label}`}
      >
        <span className="pst-label">
          <span
            className="pst-dot"
            style={{ background: rateColor(group.verdict.rate) }}
            aria-hidden="true"
          />
          {group.label}
        </span>
        <span className="mono pst-where">
          {group.members.length} {allStates ? "states" : "jurisdictions"}
        </span>
        <span className="pst-oracles">
          {!open && rateStatus(worstVerdict.rate) !== "verified" && (
            <span className="pst-group-worst">
              lowest: {worst.meta.label}{" "}
              <span
                className="mono pst-oracle-rate"
                style={{ color: rateColor(worstVerdict.rate) }}
              >
                {formatAgreementRate(worstVerdict.rate, worstVerdict.mismatches)}
              </span>
            </span>
          )}
        </span>
        <span className="mono pst-checks">
          {checksLabel(group.total, group.paramTotal)}
        </span>
        <span
          className="mono pst-rate"
          style={{ color: rateColor(group.verdict.rate) }}
        >
          {formatAgreementRate(group.verdict.rate, group.verdict.mismatches)}
        </span>
        <span className="pst-arrow pst-chevron" data-open={open || undefined}>
          ▸
        </span>
      </button>
      {open &&
        group.members.map((member) => (
          <ProgramRow
            key={programKey(member.meta)}
            row={member}
            nested
            onOpen={onOpen}
          />
        ))}
    </div>
  );
}

export default function ProgramStatusTable({ reports, onOpen }) {
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const allRows = buildProgramRows(reports);

  const tierCounts = { all: allRows.length };
  for (const tier of TIERS.slice(1)) {
    tierCounts[tier.id] = allRows.filter((r) => matchesTier(r, tier.id)).length;
  }

  const rows = allRows.filter(
    (r) => matchesTier(r, statusFilter) && matchesQuery(r, query),
  );

  // Group program rows by family; inside a family the worst rate leads.
  const families = new Map();
  for (const row of rows) {
    const family = row.meta.family;
    if (!families.has(family)) families.set(family, []);
    families.get(family).push(row);
  }
  const groups = [...families.entries()]
    .map(([family, members]) => {
      members.sort(
        (a, b) =>
          (rowVerdict(a).rate ?? 101) - (rowVerdict(b).rate ?? 101) ||
          String(a.meta.jurisdiction).localeCompare(
            String(b.meta.jurisdiction),
          ),
      );
      const total = members.reduce((n, m) => n + m.total, 0);
      const mismatches = members.reduce((n, m) => n + m.mismatches, 0);
      const paramTotal = members.reduce((n, m) => n + (m.paramTotal || 0), 0);
      const paramMismatches = members.reduce(
        (n, m) => n + (m.paramMismatches || 0),
        0,
      );
      return {
        family,
        label: FAMILY_LABELS[family] || family,
        members,
        total,
        paramTotal,
        verdict: rowVerdict({ total, mismatches, paramTotal, paramMismatches }),
        order: Math.min(...members.map((m) => m.meta.order)),
      };
    })
    .sort((a, b) => a.order - b.order);

  // Groups start collapsed: the needs-review queue below carries flagged
  // programs, and a collapsed header still previews its worst member.
  const [openFamilies, setOpenFamilies] = useState(() => new Set());
  const toggleFamily = (family) =>
    setOpenFamilies((prev) => {
      const next = new Set(prev);
      if (next.has(family)) next.delete(family);
      else next.add(family);
      return next;
    });

  // An active search or tier filter opens every surviving group — the
  // members are what the reader asked for.
  const filtering = Boolean(query) || statusFilter !== "all";

  if (!allRows.length) return null;

  return (
    <section className="card-flat">
      <div className="section-head">
        <div>
          <div className="section-eyebrow">Verified programs</div>
          <div className="section-title">
            Every measured program — open one for runs, triangulation, and
            every case
          </div>
        </div>
      </div>
      <div className="pst-toolbar">
        <input
          type="search"
          className="pst-search"
          placeholder="Filter programs…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Filter programs by name"
        />
        <div className="pst-tiers" role="group" aria-label="Status filter">
          {TIERS.map((tier) => {
            if (tier.id !== "all" && tierCounts[tier.id] === 0) return null;
            const active = statusFilter === tier.id;
            return (
              <button
                key={tier.id}
                type="button"
                aria-pressed={active}
                className={`pst-tier-chip${active ? " pst-tier-chip-on" : ""}`}
                onClick={() => setStatusFilter(active ? "all" : tier.id)}
              >
                {tier.label}
                <span className="mono pst-tier-count">
                  {tierCounts[tier.id]}
                </span>
              </button>
            );
          })}
        </div>
      </div>
      <div className="pst-body">
        {groups.map((group) =>
          group.members.length === 1 ? (
            <ProgramRow
              key={programKey(group.members[0].meta)}
              row={group.members[0]}
              onOpen={onOpen}
            />
          ) : (
            <FamilyGroup
              key={group.family}
              group={group}
              open={filtering || openFamilies.has(group.family)}
              onToggle={() => toggleFamily(group.family)}
              onOpen={onOpen}
            />
          ),
        )}
        {groups.length === 0 && (
          <div className="pst-empty">
            No programs match{query ? ` “${query}”` : " the current filter"}.
          </div>
        )}
      </div>
    </section>
  );
}
