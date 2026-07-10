"use client";

import { useEffect, useMemo, useState } from "react";
import { engineLabel, formatPct, formatAgreementRate } from "../utils/format";
import { rateColor } from "../utils/colors";
import {
  US_STATE_NAMES,
  suiteMeta,
  reportMetric,
  nearMetric,
  isAxiomPair,
  otherOracle,
  programKey,
} from "../utils/suites";
import { loadSuiteCases } from "../utils/caseData";
import ProgramRuns from "./ProgramRuns";

/**
 * The program page — one program (family × jurisdiction), all its oracles.
 *
 * Three instruments live here and nowhere else:
 *  - per-oracle scorecards (exact and near-agreement),
 *  - the triangulation partition: for each case, WHICH oracles agree with
 *    axiom (disagreeing with two independent engines points at axiom;
 *    oracles disagreeing with each other lets the encoding arbitrate),
 *  - the case explorer over every match and mismatch, from the per-suite
 *    case artifacts.
 */

const PAGE_SIZE = 50;

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

function useSuiteCases(suites) {
  const [bySuite, setBySuite] = useState({});
  useEffect(() => {
    let alive = true;
    (async () => {
      const entries = await Promise.all(
        suites.map(async (s) => [s, await loadSuiteCases(s)]),
      );
      if (alive) setBySuite(Object.fromEntries(entries));
    })();
    return () => {
      alive = false;
    };
  }, [suites.join("|")]);
  return bySuite;
}

function Triangulation({ runs, bySuite, onPick }) {
  const loaded = runs.filter((r) => bySuite[r.suite]?.cases);
  if (loaded.length < 2) return null;

  const agreement = new Map(); // case id -> Set of agreeing oracles
  const seen = new Map(); // case id -> count of suites carrying it
  for (const run of loaded) {
    for (const row of bySuite[run.suite].cases) {
      if (!seen.has(row.id)) {
        seen.set(row.id, 0);
        agreement.set(row.id, new Set());
      }
      seen.set(row.id, seen.get(row.id) + 1);
      if (row.r === 100) agreement.get(row.id).add(run.oracle);
    }
  }
  const oracles = loaded.map((r) => r.oracle);
  const buckets = new Map();
  let joined = 0;
  for (const [id, count] of seen) {
    if (count !== loaded.length) continue; // only cases every suite carries
    joined += 1;
    const agreeing = agreement.get(id);
    const key = oracles
      .filter((o) => agreeing.has(o))
      .join("+") || "none";
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push(id);
  }
  if (!joined) return null;

  const order = [
    { key: oracles.join("+"), label: "agrees with all oracles", cls: "tri-all" },
    ...oracles.map((o) => ({
      key: o,
      label: `${engineLabel(o)} only agrees`,
      cls: "tri-partial",
    })),
    { key: "none", label: "disagrees with every oracle", cls: "tri-none" },
  ];

  return (
    <section className="card-flat">
      <div className="section-head">
        <div>
          <div className="section-eyebrow">Triangulation</div>
          <div className="section-title">
            Which oracles agree with the encoding, case by case
          </div>
        </div>
        <span className="mono tri-note">
          {joined.toLocaleString()} cases carried by all {loaded.length} oracles
        </span>
      </div>
      <div className="tri-body">
        <div className="tri-bar" aria-hidden="true">
          {order.map(({ key, cls }) => {
            const n = (buckets.get(key) || []).length;
            if (!n) return null;
            return (
              <span
                key={key}
                className={`tri-seg ${cls}`}
                style={{ flexGrow: n }}
                title={`${n.toLocaleString()} cases`}
              />
            );
          })}
        </div>
        <div className="tri-legend">
          {order.map(({ key, label, cls }) => {
            const ids = buckets.get(key) || [];
            if (!ids.length) return null;
            return (
              <button
                key={key}
                type="button"
                className="tri-item"
                onClick={() => onPick(new Set(ids))}
                title="Filter the case explorer to this bucket"
              >
                <span className={`tri-swatch ${cls}`} />
                {label}
                <span className="mono tri-count">
                  {ids.length.toLocaleString()} ·{" "}
                  {formatPct((ids.length / joined) * 100, 1)}
                </span>
              </button>
            );
          })}
          <span className="tri-hint mono">
            disagreeing with independent engines points at the encoding;
            oracles disagreeing with each other lets it arbitrate
          </span>
        </div>
      </div>
    </section>
  );
}

/** A case row is settled when every one of its mismatches is dispositioned. */
function unexplainedCount(c) {
  return (c.m || []).filter((m) => !m.e).length;
}

function CaseExplorer({ runs, bySuite, pickedIds, onClearPick }) {
  const loaded = runs.filter((r) => bySuite[r.suite]?.cases);
  const householdRuns = runs.filter((r) => r.kind !== "parameter");
  const [suite, setSuite] = useState(null);
  // The queue view: unexplained disagreements are the work; everything
  // else (explained mismatches, matches) is reachable but not the default.
  const [status, setStatus] = useState("unexplained");
  const [minDiff, setMinDiff] = useState(0);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);

  const active = loaded.find((r) => r.suite === suite) || loaded[0];
  const data = active ? bySuite[active.suite] : null;
  const partial = Boolean(data?.index?.partial);

  const rows = useMemo(() => {
    if (!data) return [];
    let out = data.cases;
    if (pickedIds) out = out.filter((c) => pickedIds.has(c.id));
    if (status === "unexplained")
      out = out.filter((c) => unexplainedCount(c) > 0);
    if (status === "explained")
      out = out.filter(
        (c) => (c.m || []).length > 0 && unexplainedCount(c) === 0,
      );
    if (status === "match") out = out.filter((c) => c.r === 100);
    if (status === "mismatch") out = out.filter((c) => (c.m || []).length > 0);
    if (minDiff > 0)
      out = out.filter((c) =>
        (c.m || []).some((m) => Math.abs(m.d || 0) >= minDiff),
      );
    if (query)
      out = out.filter((c) => String(c.id).includes(query.trim()));
    return out;
  }, [data, status, minDiff, query, pickedIds]);

  useEffect(() => {
    setPage(0);
  }, [active?.suite, status, minDiff, query, pickedIds]);

  // A program measured only by parameter probes has no cases by nature —
  // no section at all, rather than an apologetic empty state.
  if (!householdRuns.length) return null;

  if (!loaded.length) {
    return (
      <section className="card-flat">
        <div className="section-head">
          <div>
            <div className="section-eyebrow">Case explorer</div>
            <div className="section-title">No per-case rows to browse</div>
          </div>
        </div>
        <p className="cx-empty">
          This program&apos;s reports don&apos;t record per-case rows or a
          complete mismatch list, so there is nothing to browse yet — the
          aggregate rates above are the whole story until the report writer
          includes them.
        </p>
      </section>
    );
  }

  const pageRows = rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));

  return (
    <section className="card-flat">
      <div className="section-head">
        <div>
          <div className="section-eyebrow">Case explorer</div>
          <div className="section-title">
            Unexplained disagreements — the queue for the next disposition
          </div>
        </div>
        <span className="mono tri-note">
          {rows.length.toLocaleString()} of{" "}
          {data.cases.length.toLocaleString()}
          {partial ? " disagreeing cases" : " cases"}
        </span>
      </div>

      {partial && (
        <p className="cx-partial mono">
          mismatch rows only — the other{" "}
          {Math.max(
            0,
            (data.index?.total_cases || 0) - data.cases.length,
          ).toLocaleString()}{" "}
          cases agree and aren&apos;t listed individually
        </p>
      )}

      <div className="cx-filters">
        {loaded.length > 1 && (
          <select
            className="cx-select"
            value={active.suite}
            onChange={(e) => setSuite(e.target.value)}
            aria-label="Oracle"
          >
            {loaded.map((r) => (
              <option key={r.suite} value={r.suite}>
                vs {engineLabel(r.oracle)}
              </option>
            ))}
          </select>
        )}
        <select
          className="cx-select"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          aria-label="Disposition status"
        >
          <option value="unexplained">unexplained mismatches</option>
          <option value="explained">explained mismatches</option>
          <option value="mismatch">all mismatches</option>
          {!partial && <option value="match">matches only</option>}
          {!partial && <option value="all">everything</option>}
        </select>
        <select
          className="cx-select"
          value={minDiff}
          onChange={(e) => setMinDiff(Number(e.target.value))}
          aria-label="Minimum difference"
        >
          <option value={0}>any difference</option>
          <option value={100}>|diff| ≥ $100</option>
          <option value={500}>|diff| ≥ $500</option>
          <option value={1000}>|diff| ≥ $1,000</option>
        </select>
        <input
          className="cx-input mono"
          placeholder="case id…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {pickedIds && (
          <button type="button" className="cx-clear" onClick={onClearPick}>
            clear triangulation filter ×
          </button>
        )}
      </div>

      <div className="cx-tablewrap">
        <table className="cx-table">
          <thead>
            <tr>
              <th>case</th>
              <th>household</th>
              <th>status</th>
              <th className="cx-num">axiom</th>
              <th className="cx-num">{engineLabel(active.oracle)}</th>
              <th className="cx-num">Δ</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && status === "unexplained" && (
              <tr>
                <td colSpan={6} className="cx-queue-empty">
                  Queue is empty — every disagreement here carries a
                  schema-validated disposition.
                </td>
              </tr>
            )}
            {pageRows.map((c) => {
              // Surface the worst UNEXPLAINED diff when one exists; a
              // dispositioned $10k residual is less urgent than a fresh $50.
              const pool = (c.m || []).some((m) => !m.e)
                ? (c.m || []).filter((m) => !m.e)
                : c.m || [];
              const worst = pool.reduce(
                (a, m) => (Math.abs(m.d || 0) > Math.abs(a?.d || 0) ? m : a),
                null,
              );
              const open = unexplainedCount(c);
              return (
                <tr key={c.id} className={c.r === 100 ? "" : "cx-miss"}>
                  <td className="mono">{c.id}</td>
                  <td className="mono cx-hh">
                    {c.h?.n || (c.h?.a || []).length
                      ? `${c.h?.n || (c.h?.a || []).length} ppl`
                      : "—"}
                    {c.h?.e ? ` · $${Number(c.h.e).toLocaleString()} earned` : ""}
                  </td>
                  <td>
                    {c.r === 100 ? (
                      <span className="cx-ok">match</span>
                    ) : open > 0 ? (
                      <span className="cx-bad">
                        {open} unexplained
                      </span>
                    ) : (
                      <span
                        className="cx-expl"
                        title={(c.m || [])
                          .map((m) => m.e)
                          .filter(Boolean)
                          .join(", ")}
                      >
                        explained
                      </span>
                    )}
                  </td>
                  <td className="mono cx-num">
                    {worst ? Number(worst.l).toLocaleString() : "—"}
                  </td>
                  <td className="mono cx-num">
                    {worst ? Number(worst.x).toLocaleString() : "—"}
                  </td>
                  <td
                    className="mono cx-num"
                    style={
                      worst ? { color: rateColor(worst.d === 0 ? 100 : 0) } : undefined
                    }
                  >
                    {worst && typeof worst.d === "number"
                      ? (worst.d > 0 ? "+" : "") + Math.round(worst.d).toLocaleString()
                      : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {pages > 1 && (
        <div className="cx-pager mono">
          <button
            type="button"
            disabled={page === 0}
            onClick={() => setPage((p) => p - 1)}
          >
            ‹ prev
          </button>
          <span>
            page {page + 1} / {pages}
          </span>
          <button
            type="button"
            disabled={page >= pages - 1}
            onClick={() => setPage((p) => p + 1)}
          >
            next ›
          </button>
        </div>
      )}
    </section>
  );
}

export default function ProgramPage({
  programId,
  reports,
  knownCauses,
  coverageOverview,
  onBack,
}) {
  const programReports = useMemo(
    () =>
      (reports || []).filter((r) => {
        if (!isAxiomPair(r) || !(r.aggregates || []).length) return false;
        return programKey(suiteMeta(r.suite)) === programId;
      }),
    [reports, programId],
  );
  const [pickedIds, setPickedIds] = useState(null);

  const runs = programReports.map((r) => ({
    suite: r.suite,
    oracle: otherOracle(r),
    metric: reportMetric(r),
    near: nearMetric(r),
    kind: suiteMeta(r.suite).kind,
  }));
  const bySuite = useSuiteCases(runs.map((r) => r.suite));

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
  const causes = (knownCauses || []).filter((c) =>
    programReports.some((r) => r.suite === c.suite),
  );

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
        <div className="pp-oracles">
          {runs.map((run) => (
            <div key={run.suite} className="pp-oracle-card">
              <span
                className="mono pp-oracle-rate"
                style={{ color: rateColor(run.metric.rate) }}
              >
                {formatAgreementRate(run.metric.rate, run.metric.mismatches)}
              </span>
              <span className="mono pp-oracle-label">
                vs {engineLabel(run.oracle)} ·{" "}
                {run.metric.total.toLocaleString()} checks
                {run.kind === "parameter" ? " · parameter" : ""}
              </span>
              {run.metric.explainedRate != null &&
                run.metric.explainedRate - run.metric.rate >= 0.05 && (
                  <span
                    className="mono pp-oracle-near"
                    title="Counting mismatches with schema-validated dispositions as explained"
                  >
                    {formatPct(run.metric.explainedRate, 1)} explained
                  </span>
                )}
              {run.near && run.near.rate - run.metric.rate >= 1 && (
                <span className="mono pp-oracle-near">
                  {formatPct(run.near.rate, 1)} within ${run.near.threshold}
                </span>
              )}
            </div>
          ))}
        </div>
      </div>

      <Triangulation runs={runs} bySuite={bySuite} onPick={setPickedIds} />

      <CaseExplorer
        runs={runs}
        bySuite={bySuite}
        pickedIds={pickedIds}
        onClearPick={() => setPickedIds(null)}
      />

      {causes.length > 0 && (
        <section className="card-flat">
          <div className="section-head">
            <div>
              <div className="section-eyebrow">Known causes</div>
              <div className="section-title">
                Why the remaining disagreements exist
              </div>
            </div>
          </div>
          <div className="pp-causes">
            {causes.map((c, i) => (
              <div key={i} className="pp-cause">
                <div className="pp-cause-head">
                  <span className="pp-cause-label">{c.label}</span>
                  {c.fix_owner && (
                    <span
                      className="mono pp-cause-owner"
                      title="Where the fix lives"
                    >
                      {c.fix_owner}
                    </span>
                  )}
                </div>
                <p className="pp-cause-desc">{richText(c.description)}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      <ProgramRuns
        reports={programReports}
        knownCauses={knownCauses}
        coverageOverview={coverageOverview}
      />
    </>
  );
}
