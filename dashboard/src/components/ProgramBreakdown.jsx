"use client";

import { useState } from "react";
import { IconChevronRight, IconChevronDown } from "@tabler/icons-react";
import { rateColor, rateBg, heatmapBg } from "../utils/colors";
import { engineLabel, formatPct } from "../utils/format";

const CATEGORY_LABEL = {
  tax: "Tax",
  food: "Food",
  health: "Health",
  housing: "Housing",
  cash: "Cash",
};

/**
 * Computes per-program aggregates from the reports: oracles with data,
 * agreement rate, and a pairwise rate matrix.
 */
function programStats(program, reports, oracles) {
  const pairs = [];
  let matches = 0;
  let comparisons = 0;
  const matrix = {};
  for (const o of oracles) {
    matrix[o] = {};
    for (const p of oracles) matrix[o][p] = o === p ? 100 : null;
  }

  for (const report of reports) {
    const left = report.engines?.left;
    const right = report.engines?.right;
    for (const agg of report.aggregates || []) {
      if (agg.concept !== program.id) continue;
      const rate = agg.match_rate;
      pairs.push({
        left,
        right,
        rate,
        mismatch: agg.mismatch_count,
        count: agg.comparison_count,
      });
      matches += (agg.comparison_count - agg.mismatch_count) || 0;
      comparisons += agg.comparison_count || 0;
      if (rate != null) {
        matrix[left][right] = rate;
        matrix[right][left] = rate;
      }
    }
  }

  const overallRate = comparisons > 0 ? (matches / comparisons) * 100 : null;
  const oraclesWithData = new Set();
  for (const pair of pairs) {
    oraclesWithData.add(pair.left);
    oraclesWithData.add(pair.right);
  }

  return {
    pairs,
    overallRate,
    comparisons,
    mismatches: comparisons - matches,
    matrix,
    oraclesWithData,
  };
}

function StatusPill({ status }) {
  const cfg = {
    live: {
      label: "live",
      color: "var(--good)",
      bg: "rgba(6,95,70,0.10)",
    },
    partial: {
      label: "partial",
      color: "var(--warn)",
      bg: "var(--warn-bg)",
    },
    encoded: {
      label: "encoded",
      color: "var(--ink-soft)",
      bg: "var(--paper-warm)",
    },
  };
  const c = cfg[status] || cfg.encoded;
  return (
    <span
      className="mono"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        padding: "2px 8px",
        borderRadius: 999,
        background: c.bg,
        color: c.color,
        fontSize: 10.5,
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        fontWeight: 600,
      }}
    >
      <span
        style={{
          width: 5,
          height: 5,
          borderRadius: 999,
          background: c.color,
        }}
      />
      {c.label}
    </span>
  );
}

function MiniMatrix({ oracles, matrix }) {
  // Compact 1-row strip showing pairwise rates against axiom
  const others = oracles.filter((o) => o !== "axiom");
  return (
    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
      {others.map((other) => {
        const value = matrix?.axiom?.[other];
        return (
          <div
            key={other}
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 4,
              padding: "6px 10px",
              borderRadius: 6,
              background: value != null ? heatmapBg(value) : "var(--paper-warm)",
              border: "1px solid var(--hairline)",
              minWidth: 84,
            }}
          >
            <div
              className="mono"
              style={{
                fontSize: 10,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: "var(--ink-mute)",
              }}
            >
              vs {other}
            </div>
            <div
              className="mono"
              style={{
                fontSize: 13,
                fontWeight: 500,
                color: value != null ? rateColor(value) : "var(--ink-mute)",
              }}
            >
              {value != null ? formatPct(value) : "—"}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function CoverageChips({ coverage }) {
  if (!coverage.length) return null;
  // Group by jurisdiction so multiple files for the same state collapse
  const byJurisdiction = new Map();
  for (const entry of coverage) {
    const key = entry.label;
    if (!byJurisdiction.has(key)) byJurisdiction.set(key, []);
    byJurisdiction.get(key).push(entry);
  }
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 5,
        marginTop: 8,
      }}
    >
      {[...byJurisdiction.entries()].map(([label, entries]) => {
        const entry = entries[0];
        const isState = entry.scope === "state";
        return (
          <span
            key={label}
            className="mono"
            title={entries.map((e) => `${e.corpus}/${e.file}`).join("\n")}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 5,
              padding: "2px 8px",
              borderRadius: 3,
              fontSize: 10.5,
              letterSpacing: "0.04em",
              background: isState
                ? "rgba(180, 83, 9, 0.10)"
                : "rgba(8, 88, 133, 0.10)",
              color: isState ? "var(--accent-deep)" : "var(--info)",
              border: "1px solid",
              borderColor: isState
                ? "rgba(180, 83, 9, 0.30)"
                : "rgba(8, 88, 133, 0.25)",
            }}
          >
            {entry.state && (
              <span style={{ fontWeight: 600 }}>{entry.state}</span>
            )}
            {!entry.state && entry.scope === "federal" && (
              <span style={{ fontWeight: 600 }}>FED</span>
            )}
            <span>
              {label}
              {entries.length > 1 && (
                <span style={{ opacity: 0.6, marginLeft: 4 }}>
                  · {entries.length} files
                </span>
              )}
            </span>
          </span>
        );
      })}
    </div>
  );
}

function ProgramCard({ program, stats, oracles }) {
  const [expanded, setExpanded] = useState(false);
  const hasData = stats.comparisons > 0;
  const status =
    program.encoding_status ?? (hasData ? "live" : "encoded");

  return (
    <div
      style={{
        background: "var(--paper-elevated)",
        border: "1px solid var(--hairline)",
        borderRadius: 12,
        overflow: "hidden",
      }}
    >
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        style={{
          width: "100%",
          padding: "18px 20px",
          background: "transparent",
          border: 0,
          textAlign: "left",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: 16,
          fontFamily: "inherit",
        }}
      >
        <span style={{ color: "var(--ink-mute)", flexShrink: 0 }}>
          {expanded ? (
            <IconChevronDown size={16} />
          ) : (
            <IconChevronRight size={16} />
          )}
        </span>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              flexWrap: "wrap",
            }}
          >
            <div
              style={{
                fontSize: 15,
                fontWeight: 500,
                color: "var(--ink)",
              }}
            >
              {program.name}
            </div>
            <span
              className="mono"
              style={{
                fontSize: 10.5,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                color: "var(--ink-mute)",
                padding: "1px 7px",
                borderRadius: 3,
                background: "var(--paper-warm)",
                border: "1px solid var(--hairline)",
              }}
            >
              {CATEGORY_LABEL[program.category] || program.category}
            </span>
            <StatusPill status={status} />
          </div>
          <div
            className="mono"
            style={{
              fontSize: 11.5,
              marginTop: 4,
              color: "var(--ink-mute)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {program.axiom_ref} · {program.statute_label}
          </div>

          <CoverageChips coverage={program.coverage || []} />
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 24,
            flexShrink: 0,
          }}
        >
          <div style={{ textAlign: "right" }}>
            <div
              className="section-eyebrow"
              style={{ fontSize: 10, letterSpacing: "0.1em" }}
            >
              Oracles
            </div>
            <div
              className="mono"
              style={{ fontSize: 13, color: "var(--ink)", marginTop: 2 }}
            >
              {program.oracles.length}
            </div>
          </div>

          <div style={{ textAlign: "right", minWidth: 70 }}>
            <div
              className="section-eyebrow"
              style={{ fontSize: 10, letterSpacing: "0.1em" }}
            >
              Agreement
            </div>
            <div
              className="mono"
              style={{
                fontSize: 14,
                fontWeight: 500,
                marginTop: 2,
                color:
                  stats.overallRate != null
                    ? rateColor(stats.overallRate)
                    : "var(--ink-mute)",
              }}
            >
              {stats.overallRate != null
                ? formatPct(stats.overallRate)
                : "—"}
            </div>
          </div>
        </div>
      </button>

      {expanded && (
        <div
          style={{
            padding: "0 20px 18px 52px",
            borderTop: "1px solid var(--hairline)",
            background: "var(--paper-warm)",
          }}
        >
          <div
            style={{
              display: "flex",
              gap: 24,
              alignItems: "flex-start",
              flexWrap: "wrap",
              paddingTop: 18,
            }}
          >
            <div style={{ flex: 1, minWidth: 280 }}>
              {(program.coverage || []).length > 0 && (
                <>
                  <div
                    className="section-eyebrow"
                    style={{ marginBottom: 10 }}
                  >
                    Encoded in
                  </div>
                  <div style={{ marginBottom: 18 }}>
                    {program.coverage.map((c, i) => (
                      <div
                        key={i}
                        className="mono"
                        style={{
                          fontSize: 11.5,
                          color: "var(--ink-mute)",
                          marginBottom: 4,
                        }}
                      >
                        <span style={{ color: "var(--ink-soft)" }}>
                          {c.label}
                        </span>{" "}
                        ·{" "}
                        <span style={{ color: "var(--ink-mute)" }}>
                          {c.corpus}/{c.file}
                        </span>
                      </div>
                    ))}
                  </div>
                </>
              )}

              <div className="section-eyebrow" style={{ marginBottom: 10 }}>
                Oracle coverage
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {program.oracles.map((o) => {
                  const hasData = stats.oraclesWithData.has(o);
                  return (
                    <span
                      key={o}
                      className="mono"
                      style={{
                        padding: "4px 10px",
                        borderRadius: 999,
                        background: hasData
                          ? "var(--paper-elevated)"
                          : "transparent",
                        border: `1px solid ${hasData ? "var(--hairline-strong)" : "var(--hairline)"}`,
                        color: hasData ? "var(--ink)" : "var(--ink-mute)",
                        fontSize: 11.5,
                      }}
                    >
                      {engineLabel(o)}
                      {!hasData && (
                        <span
                          style={{
                            marginLeft: 6,
                            fontSize: 10,
                            color: "var(--ink-mute)",
                          }}
                        >
                          · no data
                        </span>
                      )}
                    </span>
                  );
                })}
              </div>

              <div
                className="section-eyebrow"
                style={{ marginBottom: 10, marginTop: 18 }}
              >
                Comparison
              </div>
              <div
                className="mono"
                style={{ fontSize: 12, color: "var(--ink-mute)" }}
              >
                {stats.comparisons > 0 ? (
                  <>
                    <span style={{ color: "var(--ink)", fontWeight: 500 }}>
                      {stats.comparisons}
                    </span>{" "}
                    comparisons ·{" "}
                    <span style={{ color: "var(--bad)" }}>
                      {stats.mismatches}
                    </span>{" "}
                    mismatches
                    <span
                      style={{ color: "var(--ink-mute)", marginLeft: 6 }}
                    >
                      · {program.comparison}
                      {program.tolerance != null
                        ? `, ±$${program.tolerance}`
                        : ""}
                    </span>
                  </>
                ) : (
                  "No comparisons run yet for this program."
                )}
              </div>

              {program.encoding_note && (
                <>
                  <div
                    className="section-eyebrow"
                    style={{ marginBottom: 8, marginTop: 18 }}
                  >
                    Encoding note
                  </div>
                  <div
                    style={{
                      fontSize: 12.5,
                      color: "var(--ink-mute)",
                      lineHeight: 1.55,
                    }}
                  >
                    {program.encoding_note}
                  </div>
                </>
              )}
            </div>

            {stats.pairs.length > 0 && (
              <div>
                <div className="section-eyebrow" style={{ marginBottom: 10 }}>
                  Agreement with Axiom
                </div>
                <MiniMatrix oracles={oracles} matrix={stats.matrix} />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function ProgramBreakdown({ programs, reports, oracles }) {
  const [filter, setFilter] = useState("all");

  const enrichedPrograms = programs.map((p) => ({
    program: p,
    stats: programStats(p, reports, oracles),
  }));

  const filtered = enrichedPrograms.filter(({ stats }) => {
    if (filter === "live") return stats.comparisons > 0;
    if (filter === "encoded") return stats.comparisons === 0;
    return true;
  });

  const liveCount = enrichedPrograms.filter(
    (e) => e.stats.comparisons > 0
  ).length;
  const totalCount = enrichedPrograms.length;

  return (
    <div className="card-flat">
      <div className="section-head">
        <div>
          <div className="section-eyebrow">Programs encoded in the Axiom corpus</div>
          <div className="section-title">
            <span className="mono">{liveCount}</span> live ·{" "}
            <span className="mono">{totalCount - liveCount}</span> encoded but
            not yet wired
          </div>
        </div>

        <select
          className="input-pill mono"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          style={{ fontSize: 12.5 }}
        >
          <option value="all">All programs</option>
          <option value="live">Live (has data)</option>
          <option value="encoded">Encoded only</option>
        </select>
      </div>

      <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 10 }}>
        {filtered.map(({ program, stats }) => (
          <ProgramCard
            key={program.id}
            program={program}
            stats={stats}
            oracles={oracles}
          />
        ))}
        {filtered.length === 0 && (
          <div
            style={{
              textAlign: "center",
              padding: "24px 0",
              fontSize: 13,
              color: "var(--ink-mute)",
            }}
          >
            No programs match this filter.
          </div>
        )}
      </div>
    </div>
  );
}
