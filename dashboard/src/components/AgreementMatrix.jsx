"use client";

import { useState } from "react";
import { heatmapBg, rateColor } from "../utils/colors";
import { engineLabel, formatPct } from "../utils/format";

export default function AgreementMatrix({
  oracles,
  matrix,
  overallMatrix,
  concepts,
}) {
  const [selectedConcept, setSelectedConcept] = useState("__overall__");

  const activeMatrix =
    selectedConcept === "__overall__"
      ? overallMatrix
      : matrix[selectedConcept] || overallMatrix;

  // Compute per-oracle averages for the rail at the right
  const oracleAverages = oracles.map((oracle) => {
    const others = oracles.filter((o) => o !== oracle);
    const rates = others
      .map((o) => activeMatrix?.[oracle]?.[o])
      .filter((r) => r != null);
    const avg =
      rates.length > 0 ? rates.reduce((a, b) => a + b, 0) / rates.length : null;
    return { oracle, avg };
  });

  return (
    <div className="card-flat">
      <div className="section-head">
        <div>
          <div className="section-eyebrow">Agreement matrix</div>
        </div>
        <select
          className="input-pill mono"
          value={selectedConcept}
          onChange={(e) => setSelectedConcept(e.target.value)}
          style={{ fontSize: 12.5 }}
        >
          <option value="__overall__">All concepts</option>
          {concepts.map((c) => (
            <option key={c.id} value={c.id}>
              {c.description}
            </option>
          ))}
        </select>
      </div>

      <div
        style={{
          padding: "32px 40px 36px",
          display: "flex",
          gap: 32,
          alignItems: "center",
          justifyContent: "center",
          flexWrap: "wrap",
        }}
      >
        <table
          style={{
            borderSpacing: 4,
            borderCollapse: "separate",
            width: "auto",
          }}
        >
          <thead>
            <tr>
              <th />
              {oracles.map((oracle) => (
                <th
                  key={oracle}
                  className="section-eyebrow"
                  style={{
                    minWidth: 130,
                    textAlign: "center",
                    paddingBottom: 10,
                  }}
                >
                  {engineLabel(oracle)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {oracles.map((row) => (
              <tr key={row}>
                <td
                  className="section-eyebrow"
                  style={{
                    paddingRight: 16,
                    textAlign: "right",
                    whiteSpace: "nowrap",
                  }}
                >
                  {engineLabel(row)}
                </td>
                {oracles.map((col) => {
                  const value = activeMatrix?.[row]?.[col];
                  const isSelf = row === col;
                  return (
                    <td
                      key={col}
                      className="mono"
                      style={{
                        background: isSelf
                          ? "var(--paper-warm)"
                          : heatmapBg(value),
                        minWidth: 130,
                        height: 70,
                        textAlign: "center",
                        fontSize: 15,
                        borderRadius: 6,
                        border: "1px solid var(--hairline)",
                      }}
                    >
                      {isSelf ? (
                        <span
                          style={{ color: "var(--ink-mute)", fontSize: 18 }}
                        >
                          —
                        </span>
                      ) : value != null ? (
                        <span
                          style={{
                            color: rateColor(value),
                            fontWeight: 500,
                          }}
                        >
                          {formatPct(value)}
                        </span>
                      ) : (
                        <span
                          style={{
                            color: "var(--ink-mute)",
                            fontSize: 12,
                          }}
                        >
                          n/a
                        </span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>

        {/* Legend */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 10,
            minWidth: 110,
          }}
        >
          <div className="section-eyebrow">Scale</div>
          <LegendRow color="var(--good)" label="≥ 90%" />
          <LegendRow color="var(--ink-soft)" label="70–90%" />
          <LegendRow color="var(--bad)" label="< 70%" />
          <LegendRow color="var(--ink-mute)" label="n/a" muted />
        </div>
      </div>
    </div>
  );
}

function LegendRow({ color, label, muted }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span
        style={{
          width: 10,
          height: 10,
          borderRadius: 2,
          background: muted ? "var(--paper-warm)" : color,
          border: muted ? "1px dashed var(--hairline-strong)" : "none",
        }}
      />
      <span
        className="mono"
        style={{ fontSize: 11.5, color: "var(--ink-mute)" }}
      >
        {label}
      </span>
    </div>
  );
}
