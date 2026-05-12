/** Paper-theme color helpers — soft semantic palette */
export function rateColor(pct) {
  if (pct == null) return "var(--ink-mute)";
  if (pct >= 90) return "var(--good)";
  if (pct >= 70) return "var(--ink-soft)";
  return "var(--bad)";
}

export function rateBg(pct) {
  if (pct == null) return "var(--paper-warm)";
  if (pct >= 90) return "var(--good-bg)";
  if (pct >= 70) return "var(--paper-warm)";
  return "var(--bad-bg)";
}

/** Heatmap cell background for the matrix */
export function heatmapBg(pct) {
  if (pct == null) return "transparent";
  if (pct >= 95) return "rgba(6, 95, 70, 0.10)";
  if (pct >= 80) return "rgba(6, 95, 70, 0.05)";
  if (pct >= 60) return "rgba(146, 64, 14, 0.08)";
  if (pct >= 40) return "rgba(146, 64, 14, 0.14)";
  return "rgba(153, 27, 27, 0.10)";
}

export function rateBadgeClass(pct) {
  if (pct == null) return "badge";
  if (pct >= 90) return "badge badge-good";
  if (pct >= 70) return "badge badge-warn";
  return "badge badge-bad";
}
