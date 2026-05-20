"use client";

export default function SuiteSelector({ suites, value, onChange }) {
  if (!suites || suites.length <= 1) return null;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "10px 14px",
        border: "1px solid var(--hairline)",
        borderRadius: 8,
        background: "var(--surface)",
      }}
    >
      <label
        htmlFor="suite-selector"
        className="mono"
        style={{ fontSize: 12, color: "var(--ink-mute)" }}
      >
        Dataset
      </label>
      <select
        id="suite-selector"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          fontSize: 13,
          padding: "4px 8px",
          borderRadius: 4,
          border: "1px solid var(--hairline)",
          background: "transparent",
          color: "inherit",
        }}
      >
        <option value="all">All ({suites.length})</option>
        {suites.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>
    </div>
  );
}
