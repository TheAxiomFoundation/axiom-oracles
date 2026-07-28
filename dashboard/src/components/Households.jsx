"use client";

import React, { useEffect, useMemo, useState } from "react";
import { loadSuiteCases } from "../utils/caseData";
import { caseAgreement } from "../utils/caseAgreement.mjs";
import { engineLabel, formatPct } from "../utils/format";
import { suiteMeta, suiteLabel, otherOracle } from "../utils/suites";

/**
 * Level 3 of the drill: the households themselves. One browser for every
 * scope — a program (all its oracles) or an oracle (all its programs) —
 * with the full filter set, expandable per-household evidence, and the
 * triangulation partition when more than one oracle covers the scope.
 */

const PAGE = 15;

function caseValue(v) {
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") return `$${Math.round(v).toLocaleString()}`;
  return v == null ? "—" : String(v);
}

function conceptShort(conceptId, labels) {
  const known = labels.get(conceptId);
  if (known) return known;
  const tail = String(conceptId).split("#").pop().replaceAll(/[_-]/g, " ");
  return tail.length <= 4
    ? tail.toUpperCase()
    : tail.charAt(0).toUpperCase() + tail.slice(1);
}

/** "us:tax/…#input.age_at_close_of_taxable_year" → "age at close of taxable year" */
function inputName(name) {
  const tail = String(name || "").split("#input.").pop().split("#").pop();
  return tail.replaceAll(/[_-]/g, " ");
}

function unexplainedCount(c) {
  return (c.m || []).filter((m) => !m.e).length;
}

export function useSuiteCases(suites) {
  const [bySuite, setBySuite] = useState({});
  const key = suites.join("|");
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return bySuite;
}

/**
 * Which oracles agree with the encoding, case by case — only cases every
 * oracle carried. Clicking a bucket filters the table below.
 */
function Triangulation({ runs, bySuite, onPick }) {
  const loaded = runs.filter((r) => bySuite[r.suite]?.cases);
  if (loaded.length < 2) return null;

  const agreement = new Map();
  const seen = new Map();
  for (const run of loaded) {
    for (const row of bySuite[run.suite].cases) {
      const agrees = caseAgreement(row.r);
      if (agrees === null) continue;
      if (!seen.has(row.id)) {
        seen.set(row.id, 0);
        agreement.set(row.id, new Set());
      }
      seen.set(row.id, seen.get(row.id) + 1);
      if (agrees) agreement.get(row.id).add(run.oracle);
    }
  }
  const oracles = loaded.map((r) => r.oracle);
  const buckets = new Map();
  let joined = 0;
  for (const [id, count] of seen) {
    if (count !== loaded.length) continue;
    joined += 1;
    const agreeing = agreement.get(id);
    const key = oracles.filter((o) => agreeing.has(o)).join("+") || "none";
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
          {joined.toLocaleString()} cases carried by all {loaded.length}{" "}
          oracles
        </span>
      </div>
      <div className="tri-body">
        <div className="tri-grid">
          {order.map(({ key, label, cls }) => {
            const ids = buckets.get(key) || [];
            if (!ids.length) return null;
            return (
              <button
                key={key}
                type="button"
                className={`tri-box ${cls}`}
                onClick={() => onPick(new Set(ids))}
                title="Filter the households below to this bucket"
              >
                <span className="tri-box-label">{label}</span>
                <span className="mono tri-box-count">
                  {ids.length.toLocaleString()}
                  <span className="tri-box-share">
                    {formatPct((ids.length / joined) * 100, 1)}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
        <span className="tri-hint mono">
          disagreeing with independent engines points at the encoding; oracles
          disagreeing with each other lets it arbitrate
        </span>
      </div>
    </section>
  );
}

/**
 * The expanded view of one household: every input the artifact recorded
 * (compact {n, v, e} records; defaults are counted, not listed) and the
 * values both engines agreed on. Intermediate engine outputs land here as
 * harnesses start recording them.
 */
function HouseholdDetail({ c, conceptLabels, oracleLabel, inputSlots, outputSlots }) {
  const records = Array.isArray(c.i) ? c.i : null;
  const outputs = Array.isArray(c.o) ? c.o : null;
  const matched = c.v || [];
  const [showDefaults, setShowDefaults] = useState(false);
  const [showZeroOutputs, setShowZeroOutputs] = useState(false);
  const zeroOutputSlots = useMemo(() => {
    if (!showZeroOutputs || !Array.isArray(outputSlots)) return [];
    const present = new Set((outputs || []).map((r) => r.n));
    return outputSlots.filter((n) => !present.has(n));
  }, [showZeroOutputs, outputSlots, outputs]);
  const defaultedSlots = useMemo(() => {
    if (!showDefaults || !Array.isArray(inputSlots)) return [];
    const present = new Set((records || []).map((r) => r.n));
    return inputSlots.filter((n) => !present.has(n));
  }, [showDefaults, inputSlots, records]);
  return (
    <div className="v2-hhd">
      <div className="v2-hhd-block">
        <div className="mono v2-hhd-head">household inputs</div>
        <div className="v2-hhd-grid">
          {c.h?.n != null && (
            <>
              <span className="mono v2-hhd-k">people</span>
              <span>{c.h.n}</span>
            </>
          )}
          {(c.h?.a || []).length > 0 && (
            <>
              <span className="mono v2-hhd-k">ages</span>
              <span>{c.h.a.join(", ")}</span>
            </>
          )}
          {c.h?.e != null && (
            <>
              <span className="mono v2-hhd-k">earned income</span>
              <span>${Number(c.h.e).toLocaleString()} / year</span>
            </>
          )}
        </div>
        {records ? (
          <>
            <div className="v2-hhd-grid v2-hhd-record">
              {records.map((rec, ri) => (
                <span key={ri} style={{ display: "contents" }}>
                  <span className="mono v2-hhd-k" title={rec.n}>
                    {inputName(rec.n)}
                  </span>
                  <span className="mono">
                    {typeof rec.v === "number"
                      ? rec.v.toLocaleString()
                      : typeof rec.v === "boolean"
                        ? rec.v
                          ? "yes"
                          : "no"
                        : String(rec.v)}
                  </span>
                </span>
              ))}
            </div>
            {c.i0 > 0 && (
              <p className="v2-hhd-note">
                {c.i0.toLocaleString()} more inputs sit at their zero /
                false defaults
                {Array.isArray(inputSlots) && inputSlots.length > 0 ? (
                  <>
                    {" — "}
                    <button
                      type="button"
                      className="v2-linklike"
                      onClick={() => setShowDefaults((v) => !v)}
                    >
                      {showDefaults ? "hide them" : "show them"}
                    </button>
                  </>
                ) : (
                  " and aren't listed."
                )}
              </p>
            )}
            {defaultedSlots.length > 0 && (
              <div className="v2-hhd-grid v2-hhd-record">
                {defaultedSlots.map((n) => (
                  <span key={n} style={{ display: "contents" }}>
                    <span className="mono v2-hhd-k" title={n}>
                      {inputName(n)}
                    </span>
                    <span className="mono">0 / no (default)</span>
                  </span>
                ))}
              </div>
            )}
            {outputs && (
              <>
                <div className="mono v2-hhd-head">
                  engine outputs (axiom) — full computed surface
                </div>
                <div className="v2-hhd-grid v2-hhd-record">
                  {outputs.map((rec, ri) => (
                    <span key={ri} style={{ display: "contents" }}>
                      <span className="mono v2-hhd-k" title={rec.n}>
                        {inputName(rec.n)}
                      </span>
                      <span className="mono">
                        {typeof rec.v === "number"
                          ? rec.v.toLocaleString()
                          : typeof rec.v === "boolean"
                            ? rec.v
                              ? "yes"
                              : "no"
                            : String(rec.v)}
                      </span>
                    </span>
                  ))}
                </div>
                {c.o0 > 0 && (
                  <p className="v2-hhd-note">
                    {c.o0.toLocaleString()} more outputs evaluate to zero /
                    false
                    {Array.isArray(outputSlots) && outputSlots.length > 0 ? (
                      <>
                        {" — "}
                        <button
                          type="button"
                          className="v2-linklike"
                          onClick={() => setShowZeroOutputs((v) => !v)}
                        >
                          {showZeroOutputs ? "hide them" : "show them"}
                        </button>
                      </>
                    ) : (
                      "."
                    )}
                  </p>
                )}
                {zeroOutputSlots.length > 0 && (
                  <div className="v2-hhd-grid v2-hhd-record">
                    {zeroOutputSlots.map((n) => (
                      <span key={n} style={{ display: "contents" }}>
                        <span className="mono v2-hhd-k" title={n}>
                          {inputName(n)}
                        </span>
                        <span className="mono">0 / no</span>
                      </span>
                    ))}
                  </div>
                )}
              </>
            )}
          </>
        ) : (
          <p className="v2-hhd-note">
            Full input records and intermediate outputs aren&apos;t captured
            by this suite&apos;s harness yet — only the summary above.
          </p>
        )}
      </div>
      {matched.length > 0 && (
        <div className="v2-hhd-block">
          <div className="mono v2-hhd-head">values both engines agree on</div>
          <div className="v2-hhd-grid">
            {matched.map((m, i) => (
              <span key={i} style={{ display: "contents" }}>
                <span className="mono v2-hhd-k">
                  {conceptShort(m.c, conceptLabels)}
                </span>
                <span className="mono">
                  {caseValue(m.l)}
                  {caseValue(m.l) !== caseValue(m.x) &&
                    ` (${oracleLabel}: ${caseValue(m.x)})`}
                </span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * The households page. `reports` are the axiom-pair reports in scope; the
 * table merges every suite's case artifact, worst disagreement first.
 */
export default function HouseholdsView({ title, reports, onBack, backLabel }) {
  const runs = useMemo(
    () =>
      reports.map((r) => ({
        suite: r.suite,
        oracle: otherOracle(r),
        kind: suiteMeta(r.suite).kind,
      })),
    [reports],
  );
  const suites = useMemo(
    () => [...new Set(runs.map((r) => r.suite))],
    [runs],
  );
  const oracleBySuite = useMemo(
    () => new Map(runs.map((r) => [r.suite, r.oracle])),
    [runs],
  );
  const oracles = [...new Set(runs.map((r) => r.oracle))];
  const oracleLabel =
    oracles.length === 1 ? engineLabel(oracles[0]) : "oracle";
  const conceptLabels = useMemo(() => {
    const labels = new Map();
    for (const report of reports) {
      for (const agg of report.aggregates || []) {
        if (agg.description) labels.set(agg.concept, agg.description);
      }
    }
    return labels;
  }, [reports]);

  const bySuite = useSuiteCases(suites);
  const [picked, setPicked] = useState(null);
  const [status, setStatus] = useState("mismatch");
  const [minDiff, setMinDiff] = useState(0);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [openId, setOpenId] = useState(null);

  const loadedSuites = suites.filter((s) => bySuite[s]?.cases);
  const anyLoading = suites.some((s) => bySuite[s] === undefined);
  const partial = loadedSuites.some((s) => bySuite[s]?.index?.partial);
  const totalCompared = loadedSuites.reduce(
    (n, s) =>
      n + (bySuite[s].index?.total_cases ?? bySuite[s].cases.length),
    0,
  );

  const merged = useMemo(() => {
    const out = [];
    for (const s of loadedSuites) {
      for (const c of bySuite[s].cases) out.push({ ...c, s });
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bySuite, loadedSuites.join("|")]);

  const rows = useMemo(() => {
    let out = merged;
    if (picked) out = out.filter((c) => picked.has(c.id));
    if (status === "mismatch") out = out.filter((c) => (c.m || []).length > 0);
    if (status === "unexplained")
      out = out.filter((c) => unexplainedCount(c) > 0);
    if (status === "explained")
      out = out.filter(
        (c) => (c.m || []).length > 0 && unexplainedCount(c) === 0,
      );
    if (status === "match")
      out = out.filter((c) => caseAgreement(c.r) === true);
    if (minDiff > 0)
      out = out.filter((c) =>
        (c.m || []).some((m) => Math.abs(m.d || 0) >= minDiff),
      );
    if (query) out = out.filter((c) => String(c.id).includes(query.trim()));
    return [...out].sort((a, b) => {
      const worst = (c) =>
        Math.max(0, ...(c.m || []).map((m) => Math.abs(m.d || 0)));
      return worst(b) - worst(a);
    });
  }, [merged, picked, status, minDiff, query]);

  useEffect(() => {
    setPage(0);
    setOpenId(null);
  }, [status, minDiff, query, picked]);

  const pages = Math.max(1, Math.ceil(rows.length / PAGE));
  const pageRows = rows.slice(page * PAGE, (page + 1) * PAGE);
  const inputsMissing =
    merged.length > 0 &&
    merged
      .slice(0, 50)
      .every((c) => !(c.h?.n || (c.h?.a || []).length || (c.i || []).length));

  return (
    <>
      <div className="pp-head">
        <button type="button" className="pp-back" onClick={onBack}>
          ← {backLabel}
        </button>
        <h1 className="pp-title">
          Households
          <span className="mono pp-where"> · {title}</span>
        </h1>
      </div>

      <Triangulation runs={runs} bySuite={bySuite} onPick={setPicked} />

      <section className="card-flat">
        <div className="section-head">
          <div>
            <div className="section-eyebrow">Case evidence</div>
            <div className="section-title">
              Every compared household, worst disagreement first
            </div>
          </div>
          {!anyLoading && (
            <span className="mono tri-note">
              {rows.length.toLocaleString()} of{" "}
              {totalCompared.toLocaleString()} households
            </span>
          )}
        </div>

        {merged.length > 0 && (
        <div className="cx-filters">
          <select
            className="cx-select"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            aria-label="Status"
          >
            <option value="mismatch">disagreements</option>
            <option value="unexplained">unexplained only</option>
            <option value="explained">explained only</option>
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
          {picked && (
            <button
              type="button"
              className="cx-clear"
              onClick={() => setPicked(null)}
            >
              clear triangulation filter ×
            </button>
          )}
        </div>
        )}

        {(partial || inputsMissing) && (
          <p className="v2-hh-note">
            {partial &&
              `${
                loadedSuites.length > 1
                  ? "These artifacts store"
                  : "This artifact stores"
              } only the disagreeing households — the other ${(
                totalCompared - merged.length
              ).toLocaleString()} matched on every compared value. `}
            {inputsMissing &&
              "Household inputs are not yet captured by this scope's harnesses."}
          </p>
        )}

        {anyLoading && merged.length === 0 ? (
          <p className="v2-empty">Loading household cases…</p>
        ) : merged.length === 0 ? (
          <div className="hh-empty">
            <span className="mono hh-empty-glyph" aria-hidden="true">
              ∅
            </span>
            <div className="hh-empty-title">
              No per-household evidence yet
            </div>
            <p className="hh-empty-body">
              This scope&apos;s runs report aggregate agreement only — the
              harness hasn&apos;t recorded individual household cases. Once a
              full run persists them, every compared household will be
              browsable here.
            </p>
          </div>
        ) : rows.length === 0 ? (
          <p className="v2-empty">Nothing matches these filters.</p>
        ) : (
          <>
            <div className="v2-hh-tablewrap">
              <table className="v2-hh-table">
                <thead>
                  <tr>
                    <th>household</th>
                    <th>concept</th>
                    <th className="v2-hht-num">Axiom</th>
                    <th className="v2-hht-num">{oracleLabel}</th>
                    <th className="v2-hht-num">Δ</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((c) => {
                    const ms = c.m || [];
                    const rid = `${c.s || ""}:${c.id}`;
                    const isOpen = openId === rid;
                    const toggle = () => setOpenId(isOpen ? null : rid);
                    const who = (
                      <td
                        className="v2-hht-who"
                        rowSpan={Math.max(1, ms.length)}
                      >
                        <div className="v2-hh-who">
                          <span className="mono v2-hh-id" title={c.id}>
                            <span
                              className="v2-hht-caret"
                              aria-hidden="true"
                            >
                              {isOpen ? "▾" : "▸"}
                            </span>{" "}
                            {c.id}
                          </span>
                          {suites.length > 1 && c.s && (
                            <span
                              className="mono v2-hh-suitetag"
                              title={suiteLabel(c.s)}
                            >
                              {suiteLabel(c.s)}
                              {oracles.length > 1 &&
                                ` · vs ${engineLabel(oracleBySuite.get(c.s))}`}
                            </span>
                          )}
                        </div>
                      </td>
                    );
                    const detail = isOpen && (
                      <tr key={`${rid}-detail`} className="v2-hht-detailrow">
                        <td colSpan={6}>
                          <HouseholdDetail
                            c={c}
                            conceptLabels={conceptLabels}
                            oracleLabel={engineLabel(
                              oracleBySuite.get(c.s) || oracles[0],
                            )}
                            inputSlots={
                              bySuite[c.s]?.index?.input_slots || null
                            }
                            outputSlots={
                              bySuite[c.s]?.index?.output_slots || null
                            }
                          />
                        </td>
                      </tr>
                    );
                    if (ms.length === 0) {
                      const agrees = caseAgreement(c.r);
                      return (
                        <React.Fragment key={rid}>
                          <tr
                            className="v2-hht-case v2-hht-click"
                            onClick={toggle}
                          >
                            {who}
                            <td colSpan={5} className="v2-hh-agree">
                              {agrees === true
                                ? "engines agree on every compared value"
                                : agrees === null
                                  ? "case-level agreement not recorded"
                                  : "case-level disagreement recorded; values unavailable"}
                            </td>
                          </tr>
                          {detail}
                        </React.Fragment>
                      );
                    }
                    return (
                      <React.Fragment key={rid}>
                        {ms.map((m, i) => (
                          <tr
                            key={`${rid}-${i}`}
                            className={`${
                              i === 0 ? "v2-hht-case" : "v2-hht-cont"
                            } v2-hht-click`}
                            onClick={toggle}
                          >
                            {i === 0 && who}
                            <td
                              className="v2-hh-concept"
                              title={conceptShort(m.c, conceptLabels)}
                            >
                              <span>{conceptShort(m.c, conceptLabels)}</span>
                            </td>
                            <td className="mono v2-hht-num">
                              {caseValue(m.l)}
                            </td>
                            <td className="mono v2-hht-num">
                              {caseValue(m.x)}
                            </td>
                            <td className="mono v2-hht-num">
                              {typeof m.d === "number" && m.d !== 0 ? (
                                <span className="v2-hh-diff">
                                  $
                                  {Math.abs(
                                    Math.round(m.d),
                                  ).toLocaleString()}
                                </span>
                              ) : (
                                "—"
                              )}
                            </td>
                            <td className="v2-hht-status">
                              {m.e ? (
                                <span className="v2-action v2-action-doc">
                                  explained
                                </span>
                              ) : (
                                <span className="v2-action v2-action-open">
                                  unexplained
                                </span>
                              )}
                            </td>
                          </tr>
                        ))}
                        {detail}
                      </React.Fragment>
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
                  onClick={() => {
                    setPage((p) => p - 1);
                    setOpenId(null);
                  }}
                >
                  ‹ prev
                </button>
                <span>
                  page {page + 1} / {pages} ·{" "}
                  {rows.length.toLocaleString()} households
                </span>
                <button
                  type="button"
                  disabled={page >= pages - 1}
                  onClick={() => {
                    setPage((p) => p + 1);
                    setOpenId(null);
                  }}
                >
                  next ›
                </button>
              </div>
            )}
          </>
        )}
      </section>
    </>
  );
}
