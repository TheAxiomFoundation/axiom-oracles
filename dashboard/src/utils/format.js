export function formatCurrency(value) {
  if (value == null) return "—";
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function formatPct(value, decimals = 1) {
  if (value == null) return "—";
  return `${Number(value).toFixed(decimals)}%`;
}

/**
 * Format a measured agreement rate without rounding up to a false "100%".
 * A run with open mismatches never displays as 100, no matter how small the
 * residual is relative to the total.
 */
export function formatAgreementRate(rate, mismatches = 0) {
  if (rate == null) return "—";
  if (mismatches === 0 || rate === 100) return "100%";
  const oneDecimal = rate.toFixed(1);
  if (oneDecimal !== "100.0") return `${oneDecimal}%`;
  const twoDecimals = rate.toFixed(2);
  return twoDecimals !== "100.00" ? `${twoDecimals}%` : ">99.99%";
}

export function formatDiff(value) {
  if (value == null) return "—";
  const sign = value >= 0 ? "+" : "";
  return `${sign}${formatCurrency(value)}`;
}

/**
 * Mismatch kinds are left/right-relative, so labels must name the actual
 * engine pair of the report they came from — "TAXSIM eligible, Axiom not"
 * for a taxsim run, not a hard-coded PolicyEngine.
 */
export function mismatchKindLabel(kind, engines) {
  const left = engineLabel(engines?.left || "axiom");
  const right = engineLabel(engines?.right || "policyengine");
  const labels = {
    eligibility_right_only: `${right} eligible, ${left} not`,
    eligibility_left_only: `${left} eligible, ${right} not`,
    amount_difference: "Amount differs",
    missing_left: `${left} returned no value`,
    missing_right: `${right} returned no value`,
    missing_both: "Both engines missing",
  };
  return labels[kind] || kind;
}

export function engineLabel(name) {
  const labels = {
    policyengine: "PolicyEngine",
    taxsim: "TAXSIM",
    axiom: "Axiom",
    accessnyc: "ACCESS NYC",
    prd: "PRD",
  };
  return labels[name] || name;
}
