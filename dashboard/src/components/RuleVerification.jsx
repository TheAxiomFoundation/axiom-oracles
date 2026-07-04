"use client";

import { useEffect, useMemo, useState } from "react";
import { formatPct } from "../utils/format";
import { FAMILY_LABELS, US_STATE_NAMES } from "../utils/suites";

/**
 * Per-rule verification status (Phase-A item A7).
 *
 * Answers "which rules have no oracle?" and turns the coverage number into a
 * tracked KPI. Reads the compact summary that
 * scripts/rule_verification.py emits; the full per-rule join
 * (rule_verification.json) is fetched lazily only when a row is expanded, so
 * the initial page load stays light.
 *
 * The view keeps three axes deliberately distinct:
 *  - grounding + manifest provenance are true per-rule signals (near-total),
 *  - oracle coverage is reported at the SURFACE grain (the plan's headline:
 *    executable surfaces / total surfaces), and the per-rule "on an oracle
 *    surface" number is labelled as a lower bound, never as per-rule proof.
 */

function KpiTile({ value, label, sub, tone }) {
  return (
    <div className="rv-kpi" data-tone={tone || "neutral"}>
      <span className="mono rv-kpi-value">{value}</span>
      <span className="rv-kpi-label">{label}</span>
      {sub ? <span className="rv-kpi-sub">{sub}</span> : null}
    </div>
  );
}

function familyLabel(family) {
  if (family === "unclassified") return "Unclassified paths";
  return FAMILY_LABELS[family] || family;
}

function jurisdictionLabel(code) {
  if (!code || code === "unclassified") return "Unclassified";
  if (code === "US") return "Federal (US)";
  if (code === "UK") return "United Kingdom";
  if (code === "NYC") return "New York City";
  return US_STATE_NAMES[code] || code;
}

// Rate → semantic tone for the small inline bars. Grounding/manifest read as
// good near 100; the oracle column is intentionally neutral so a low number
// reads as "work remaining", not "failure".
function rateTone(pct) {
  if (pct == null) return "gap";
  if (pct >= 90) return "good";
  if (pct >= 60) return "warn";
  return "bad";
}

function Bar({ pct, tone }) {
  return (
    <span className="rv-bar" title={pct == null ? "—" : `${pct}%`}>
      <span
        className="rv-bar-fill"
        data-tone={tone}
        style={{ width: `${Math.max(0, Math.min(100, pct || 0))}%` }}
      />
    </span>
  );
}

const GROUPINGS = [
  { id: "family", label: "By program" },
  { id: "jurisdiction", label: "By jurisdiction" },
];

export default function RuleVerification({ region = "us" }) {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);
  const [grouping, setGrouping] = useState("family");
  const [onlyGaps, setOnlyGaps] = useState(false);

  useEffect(() => {
    fetch("/data/rule_verification_summary.json")
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`);
        return r.json();
      })
      .then(setSummary)
      .catch((e) => setError(e.message));
  }, []);

  const rows = useMemo(() => {
    if (!summary) return [];
    const source =
      grouping === "family" ? summary.by_family : summary.by_jurisdiction;
    let out = (source || []).map((r) => ({
      key: grouping === "family" ? r.family : r.jurisdiction,
      label:
        grouping === "family"
          ? familyLabel(r.family)
          : jurisdictionLabel(r.jurisdiction),
      rules: r.rules,
      grounded: r.grounded_pct,
      manifest: r.manifest_backed_pct,
      oracle: r.surface_oracle_pct,
    }));
    if (onlyGaps) out = out.filter((r) => (r.oracle || 0) < 100);
    return out;
  }, [summary, grouping, onlyGaps]);

  if (error) {
    return null; // page renders fine without this section
  }
  if (!summary) {
    return (
      <section className="card-flat">
        <div className="section-head">
          <div>
            <div className="section-eyebrow">Rule verification</div>
            <div className="section-title">Loading per-rule coverage…</div>
          </div>
        </div>
      </section>
    );
  }

  const s = summary.rules;
  const surf = summary.surfaces;

  return (
    <section className="card-flat">
      <div className="section-head">
        <div>
          <div className="section-eyebrow">Rule verification · KPI</div>
          <div className="section-title">
            Every encoded rule: grounded, provenance-backed, oracle-covered?
          </div>
        </div>
        <span className="mono rv-ref" title={summary.provenance.rulespec_commit}>
          rulespec-us @ {summary.provenance.rulespec_commit.slice(0, 12)}
        </span>
      </div>

      <div className="rv-kpis">
        <KpiTile
          value={s.total.toLocaleString()}
          label="Encoded rules"
          sub={`${surf.total} program surfaces`}
        />
        <KpiTile
          value={formatPct(s.grounded_pct)}
          label="Grounded"
          sub="corpus citation + proof atoms"
          tone={rateTone(s.grounded_pct)}
        />
        <KpiTile
          value={formatPct(s.manifest_backed_pct)}
          label="Manifest-backed"
          sub="signed manifest, sha verified"
          tone={rateTone(s.manifest_backed_pct)}
        />
        <KpiTile
          value={`${surf.executable} / ${surf.total}`}
          label="Executable oracle surfaces"
          sub={`${formatPct(surf.executable_pct)} — the burn-down`}
          tone="track"
        />
        <KpiTile
          value={formatPct(s.on_oracle_surface_pct)}
          label="Rules on an oracle surface"
          sub="surface-level lower bound"
          tone="track"
        />
      </div>

      <p className="rv-note">
        Grounding and manifest provenance are measured per rule. Oracle coverage
        is measured per program surface — a comparison on a program's benefit
        calculation does not verify every table and appendix rule in that
        program, so the per-rule figure is a lower bound, not a claim that each
        rule is individually checked. Growing the {surf.executable}-of-
        {surf.total} executable-surface number is the tracked burn-down.
      </p>

      <div className="rv-controls">
        <div className="rv-toggle" role="tablist" aria-label="Group rules by">
          {GROUPINGS.map((g) => (
            <button
              key={g.id}
              type="button"
              role="tab"
              aria-selected={grouping === g.id}
              className={`rv-toggle-btn ${
                grouping === g.id ? "rv-toggle-btn-active" : ""
              }`}
              onClick={() => setGrouping(g.id)}
            >
              {g.label}
            </button>
          ))}
        </div>
        <label className="rv-filter">
          <input
            type="checkbox"
            checked={onlyGaps}
            onChange={(e) => setOnlyGaps(e.target.checked)}
          />
          Only rows with an oracle gap
        </label>
      </div>

      <div className="table-scroll">
        <table className="coverage-table rv-table">
          <thead>
            <tr>
              <th>{grouping === "family" ? "Program" : "Jurisdiction"}</th>
              <th className="rv-num">Rules</th>
              <th>Grounded</th>
              <th>Manifest-backed</th>
              <th>
                On an oracle surface
                <span className="rv-th-note">surface-level</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key}>
                <td className="rv-rowlabel">{r.label}</td>
                <td className="rv-num mono">{r.rules.toLocaleString()}</td>
                <td>
                  <div className="rv-cell">
                    <Bar pct={r.grounded} tone={rateTone(r.grounded)} />
                    <span className="mono rv-cell-pct">
                      {formatPct(r.grounded)}
                    </span>
                  </div>
                </td>
                <td>
                  <div className="rv-cell">
                    <Bar pct={r.manifest} tone={rateTone(r.manifest)} />
                    <span className="mono rv-cell-pct">
                      {formatPct(r.manifest)}
                    </span>
                  </div>
                </td>
                <td>
                  <div className="rv-cell">
                    <Bar pct={r.oracle} tone="track" />
                    <span className="mono rv-cell-pct">
                      {formatPct(r.oracle)}
                    </span>
                  </div>
                </td>
              </tr>
            ))}
            {rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="rv-empty">
                  No rows match the current filter.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}
