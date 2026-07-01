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

const MISMATCH_KIND_LABELS = {
  eligibility_right_only: "PolicyEngine eligible, Axiom not",
  eligibility_left_only: "Axiom eligible, PolicyEngine not",
  amount_difference: "Amount differs",
  missing_left: "Axiom returned no value",
  missing_right: "PolicyEngine returned no value",
  missing_both: "Both engines missing",
};

export function mismatchKindLabel(kind) {
  return MISMATCH_KIND_LABELS[kind] || kind;
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
