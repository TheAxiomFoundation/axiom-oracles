/**
 * Uncompared pairs: one engine's return was missing or nonfinite. The
 * producer records an engine error and retains the pair as a diagnostic
 * mismatch, so an aggregate's `mismatch_count` includes it and its
 * `uncompared_mismatches` counts it. `comparison_count` and
 * `compared_values` exclude it. Every figure that pairs a mismatch count
 * with a compared count must use the compared mismatches only.
 */

/** Uncompared pairs an aggregate (or summary) records; 0 when absent. */
export function uncomparedCount(agg) {
  const n = agg?.uncompared_mismatches;
  return Number.isFinite(n) && n > 0 ? n : 0;
}

/** Mismatches among compared pairs: `mismatch_count` less uncompared pairs. */
export function comparedMismatchCount(agg) {
  const total = agg?.mismatch_count;
  if (!Number.isFinite(total)) return 0;
  return Math.max(0, total - uncomparedCount(agg));
}

/** A served compact case row's uncompared pair ("u": true). */
export function isUncompared(m) {
  return m?.u === true;
}

/** Whether a compared compact row has a nonzero numeric delta to display. */
export function hasMismatchDelta(m) {
  return !isUncompared(m) && typeof m?.d === "number" && m.d !== 0;
}

/** A served case's compared disagreements. */
export function caseDisagreements(c) {
  return (c?.m || []).filter((m) => !isUncompared(m));
}

/** A served case's uncompared pairs. */
export function caseUncompared(c) {
  return (c?.m || []).filter(isUncompared);
}

/** Compared disagreements without an explanation. */
export function caseUnexplainedCount(c) {
  return caseDisagreements(c).filter((m) => !m.e).length;
}
