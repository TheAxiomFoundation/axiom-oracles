"use client";

/**
 * Encoding run-log visualization (axiom_encode.run_log.v1).
 *
 * Data-driven from the published run log only:
 *   /data/run_log_pipeline.json  - machine-readable stage DAG (drawn, not hardcoded)
 *   /data/run_log_runs.json      - folded per-run summaries + precomputed aggregates
 *
 * Renders the aggregate funnel (generated -> gates-passed -> judged -> applied ->
 * pr -> merged), the failure Pareto by gate/reason, and a per-run step DAG whose
 * nodes are colored by verdict with stage timings.
 */

import { useEffect, useMemo, useState } from "react";

const STATUS_COLOR = {
  passed: "var(--good)",
  failed: "var(--bad)",
  error: "var(--bad)",
  skipped: "var(--ink-mute)",
  started: "var(--accent)",
  superseded: "var(--ink-soft)",
};

function statusColor(status) {
  return STATUS_COLOR[status] || "transparent";
}

function fmtDuration(ms) {
  if (!ms) return null;
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}

function fmtDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

export default function EncodingRunLog({ basePath = "" }) {
  const [pipeline, setPipeline] = useState(null);
  const [index, setIndex] = useState(null);
  const [status, setStatus] = useState("loading");
  const [showRuns, setShowRuns] = useState(50);

  useEffect(() => {
    let alive = true;
    Promise.all([
      fetch(`${basePath}/data/run_log_pipeline.json`).then((r) =>
        r.ok ? r.json() : null,
      ),
      fetch(`${basePath}/data/run_log_runs.json`).then((r) =>
        r.ok ? r.json() : null,
      ),
    ])
      .then(([spec, runs]) => {
        if (!alive) return;
        if (!spec || !runs) {
          setStatus("absent");
          return;
        }
        setPipeline(spec);
        setIndex(runs);
        setStatus("ready");
      })
      .catch(() => alive && setStatus("absent"));
    return () => {
      alive = false;
    };
  }, [basePath]);

  const aggregates = index?.aggregates;
  const stages = pipeline?.stages || [];

  const paretoMax = useMemo(() => {
    const p = aggregates?.failure_pareto || [];
    return p.length ? Math.max(...p.map((x) => x.count)) : 0;
  }, [aggregates]);

  if (status === "loading" || status === "absent") {
    // Silent no-op until the run log has been published, so the dashboard is
    // clean before the first `axiom-encode run-log-publish`.
    return null;
  }

  const runs = index.runs || [];
  const funnel = aggregates?.funnel || [];
  const funnelMax = funnel.length ? funnel[0].count : 0;
  const pareto = (aggregates?.failure_pareto || []).slice(0, 10);

  return (
    <section className="card" style={{ marginTop: 24 }}>
      <div className="section-eyebrow">Encoding pipeline</div>
      <h2 style={{ margin: "4px 0 2px", fontSize: 20, color: "var(--ink)" }}>
        Encoding run log
      </h2>
      <p style={{ color: "var(--ink-mute)", fontSize: 13, margin: "0 0 16px" }}>
        {index.run_count.toLocaleString()} runs · {pipeline.run_log_schema} ·
        published {fmtDate(index.generated_at)}. Downstream stages (judge, PR, CI,
        merge, oracle-at-merge) populate as the pipeline emits them.
      </p>

      {/* Aggregate funnel */}
      <div style={{ marginBottom: 24 }}>
        <div className="section-eyebrow" style={{ marginBottom: 8 }}>
          Funnel
        </div>
        {funnel.map((step) => {
          const pct = funnelMax ? (step.count / funnelMax) * 100 : 0;
          const dim = step.count === 0;
          return (
            <div
              key={step.bucket}
              style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}
            >
              <div
                style={{
                  width: 120,
                  fontSize: 12,
                  color: dim ? "var(--ink-mute)" : "var(--ink-soft)",
                  textTransform: "capitalize",
                }}
              >
                {step.bucket.replace(/_/g, " ")}
              </div>
              <div
                style={{
                  flex: 1,
                  background: "var(--paper-warm)",
                  borderRadius: 6,
                  height: 22,
                  position: "relative",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: `${Math.max(pct, step.count > 0 ? 2 : 0)}%`,
                    height: "100%",
                    background: dim ? "var(--ink-mute)" : "var(--accent)",
                    opacity: dim ? 0.25 : 0.85,
                  }}
                />
              </div>
              <div
                style={{
                  width: 90,
                  textAlign: "right",
                  fontSize: 12,
                  color: dim ? "var(--ink-mute)" : "var(--ink)",
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {step.count.toLocaleString()}
                {dim ? " (none yet)" : ""}
              </div>
            </div>
          );
        })}
      </div>

      {/* Failure Pareto */}
      {pareto.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <div className="section-eyebrow" style={{ marginBottom: 8 }}>
            Failure Pareto (first failing stage · reason)
          </div>
          {pareto.map((row) => {
            const pct = paretoMax ? (row.count / paretoMax) * 100 : 0;
            return (
              <div
                key={row.key}
                style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 5 }}
              >
                <div
                  style={{
                    width: 220,
                    fontSize: 12,
                    color: "var(--ink-soft)",
                    fontFamily: "var(--font-mono, monospace)",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                  title={row.key}
                >
                  {row.stage} · {row.reason_code}
                </div>
                <div
                  style={{
                    flex: 1,
                    background: "var(--paper-warm)",
                    borderRadius: 6,
                    height: 18,
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      width: `${Math.max(pct, 2)}%`,
                      height: "100%",
                      background: "var(--bad)",
                      opacity: 0.7,
                    }}
                  />
                </div>
                <div
                  style={{
                    width: 50,
                    textAlign: "right",
                    fontSize: 12,
                    color: "var(--ink)",
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {row.count}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Per-run step DAG */}
      <div>
        <div className="section-eyebrow" style={{ marginBottom: 8 }}>
          Per-run step DAG (nodes colored by verdict)
        </div>
        <StageLegend />
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--ink-mute)" }}>
                <th style={{ padding: "4px 8px", fontWeight: 500 }}>Run</th>
                <th style={{ padding: "4px 8px", fontWeight: 500 }}>Citation</th>
                <th style={{ padding: "4px 8px", fontWeight: 500 }}>Stages</th>
              </tr>
            </thead>
            <tbody>
              {runs.slice(0, showRuns).map((run) => (
                <RunRow key={run.run_id} run={run} stages={stages} />
              ))}
            </tbody>
          </table>
        </div>
        {runs.length > showRuns && (
          <button
            onClick={() => setShowRuns((n) => n + 50)}
            style={{
              marginTop: 12,
              padding: "6px 14px",
              fontSize: 12,
              background: "var(--paper-warm)",
              border: "1px solid var(--hairline, #e5e7eb)",
              borderRadius: 8,
              color: "var(--ink-soft)",
              cursor: "pointer",
            }}
          >
            Show more ({runs.length - showRuns} more runs)
          </button>
        )}
      </div>
    </section>
  );
}

function RunRow({ run, stages }) {
  return (
    <tr style={{ borderTop: "1px solid var(--hairline, #eee)" }}>
      <td
        style={{
          padding: "6px 8px",
          fontFamily: "var(--font-mono, monospace)",
          color: "var(--ink-mute)",
          whiteSpace: "nowrap",
        }}
      >
        {run.run_id}
      </td>
      <td
        style={{
          padding: "6px 8px",
          color: "var(--ink-soft)",
          maxWidth: 260,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
        title={run.citation || ""}
      >
        {run.citation || "—"}
      </td>
      <td style={{ padding: "6px 8px" }}>
        <div style={{ display: "flex", gap: 3, alignItems: "center" }}>
          {stages.map((stage) => {
            const st = run.stage_status?.[stage.id];
            const ms = run.stage_duration_ms?.[stage.id];
            const label =
              `${stage.label}: ${st || "not recorded"}` +
              (ms ? ` (${fmtDuration(ms)})` : "");
            return (
              <span
                key={stage.id}
                title={label}
                style={{
                  width: 16,
                  height: 16,
                  borderRadius: 4,
                  background: st ? statusColor(st) : "transparent",
                  border: st ? "none" : "1px dashed var(--hairline, #d1d5db)",
                  opacity: st ? 0.9 : 0.5,
                  display: "inline-block",
                }}
              />
            );
          })}
        </div>
      </td>
    </tr>
  );
}

function StageLegend() {
  const items = [
    ["passed", "var(--good)"],
    ["failed", "var(--bad)"],
    ["skipped", "var(--ink-mute)"],
    ["not recorded", "transparent"],
  ];
  return (
    <div
      style={{
        display: "flex",
        gap: 16,
        marginBottom: 10,
        fontSize: 11,
        color: "var(--ink-mute)",
      }}
    >
      {items.map(([label, color]) => (
        <span key={label} style={{ display: "flex", alignItems: "center", gap: 5 }}>
          <span
            style={{
              width: 12,
              height: 12,
              borderRadius: 3,
              background: color,
              border:
                color === "transparent"
                  ? "1px dashed var(--hairline, #d1d5db)"
                  : "none",
              display: "inline-block",
            }}
          />
          {label}
        </span>
      ))}
    </div>
  );
}
