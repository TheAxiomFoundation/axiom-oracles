"use client";

import { useState } from "react";
import { IconChevronDown, IconChevronUp } from "@tabler/icons-react";
import { formatCurrency, formatDiff } from "../utils/format";

function CaseRow({ caseData }) {
  const [expanded, setExpanded] = useState(false);
  const hasMismatches = caseData.mismatches.length > 0;

  const taxsimInput = caseData.metadata?.taxsim_input;
  const wages = taxsimInput?.pwages ?? null;
  const deps = taxsimInput?.depx ?? null;
  const meta =
    wages != null
      ? `${formatCurrency(wages)} wages · ${deps ?? 0} dep${deps === 1 ? "" : "s"}`
      : null;

  return (
    <div
      style={{
        borderTop: "1px solid var(--hairline)",
        background: "var(--paper-elevated)",
      }}
    >
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        style={{
          width: "100%",
          padding: "14px 24px",
          cursor: "pointer",
          background: "transparent",
          border: 0,
          textAlign: "left",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          fontFamily: "inherit",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: 999,
              background: hasMismatches ? "var(--bad)" : "var(--good)",
              flexShrink: 0,
            }}
          />
          <div>
            <div
              className="mono"
              style={{ fontSize: 13, color: "var(--ink)" }}
            >
              {caseData.case_id}
            </div>
            {meta && (
              <div
                className="mono"
                style={{
                  fontSize: 11.5,
                  marginTop: 3,
                  color: "var(--ink-mute)",
                }}
              >
                {meta}
              </div>
            )}
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          {hasMismatches ? (
            <span
              className="mono"
              style={{
                fontSize: 12,
                color: "var(--bad)",
                fontWeight: 500,
              }}
            >
              {caseData.mismatches.length} mismatch
              {caseData.mismatches.length !== 1 ? "es" : ""}
            </span>
          ) : (
            <span
              className="mono"
              style={{ fontSize: 12, color: "var(--ink-mute)" }}
            >
              aligned
            </span>
          )}
          <span style={{ color: "var(--ink-mute)" }}>
            {expanded ? (
              <IconChevronUp size={16} />
            ) : (
              <IconChevronDown size={16} />
            )}
          </span>
        </div>
      </button>

      {expanded && hasMismatches && (
        <div
          style={{
            padding: "0 24px 18px",
            background: "var(--paper-warm)",
            borderTop: "1px solid var(--hairline)",
          }}
        >
          <table style={{ fontSize: 13, marginTop: 14 }}>
            <thead>
              <tr>
                <th
                  className="section-eyebrow"
                  style={{ padding: "8px 0" }}
                >
                  Concept
                </th>
                <th
                  className="section-eyebrow"
                  style={{ padding: "8px 0" }}
                >
                  Pair
                </th>
                <th
                  className="section-eyebrow"
                  style={{ padding: "8px 0", textAlign: "right" }}
                >
                  Left
                </th>
                <th
                  className="section-eyebrow"
                  style={{ padding: "8px 0", textAlign: "right" }}
                >
                  Right
                </th>
                <th
                  className="section-eyebrow"
                  style={{ padding: "8px 0", textAlign: "right" }}
                >
                  Δ
                </th>
              </tr>
            </thead>
            <tbody>
              {caseData.mismatches.map((m, i) => (
                <tr
                  key={i}
                  style={{
                    borderTop: "1px solid var(--hairline)",
                  }}
                >
                  <td style={{ padding: "8px 12px 8px 0", color: "var(--ink)" }}>
                    {m.description}
                  </td>
                  <td
                    className="mono"
                    style={{
                      padding: "8px 12px 8px 0",
                      fontSize: 11.5,
                      color: "var(--ink-mute)",
                    }}
                  >
                    {m.pair}
                  </td>
                  <td
                    className="mono"
                    style={{
                      padding: "8px 12px 8px 0",
                      textAlign: "right",
                      color: "var(--ink-soft)",
                    }}
                  >
                    {formatCurrency(m.left)}
                  </td>
                  <td
                    className="mono"
                    style={{
                      padding: "8px 12px 8px 0",
                      textAlign: "right",
                      color: "var(--ink-soft)",
                    }}
                  >
                    {formatCurrency(m.right)}
                  </td>
                  <td
                    className="mono"
                    style={{
                      padding: "8px 0",
                      textAlign: "right",
                      color: m.difference >= 0 ? "var(--good)" : "var(--bad)",
                      fontWeight: 600,
                    }}
                  >
                    {formatDiff(m.difference)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function CaseInspector({ allCases }) {
  const [filter, setFilter] = useState("mismatches");

  const filtered = allCases.filter((c) => {
    if (filter === "mismatches" && c.mismatches.length === 0) return false;
    if (filter === "matches" && c.mismatches.length > 0) return false;
    return true;
  });

  const mismatchCount = allCases.filter((c) => c.mismatches.length > 0).length;

  return (
    <div className="card-flat">
      <div className="section-head">
        <div>
          <div className="section-eyebrow">Cases</div>
          <div className="section-title">
            <span className="mono">{mismatchCount}</span> of{" "}
            <span className="mono">{allCases.length}</span> households diverge
          </div>
        </div>

        <select
          className="input-pill mono"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          style={{ fontSize: 12.5 }}
        >
          <option value="mismatches">Mismatches</option>
          <option value="matches">Aligned</option>
          <option value="all">All</option>
        </select>
      </div>

      <div style={{ maxHeight: 520, overflowY: "auto" }}>
        {filtered.slice(0, 50).map((c) => (
          <CaseRow key={c.case_id} caseData={c} />
        ))}
        {filtered.length === 0 && (
          <div
            style={{
              textAlign: "center",
              padding: "32px 0",
              fontSize: 13,
              color: "var(--ink-mute)",
            }}
          >
            No cases match the current filter.
          </div>
        )}
      </div>
    </div>
  );
}
