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

export function formatDiff(value) {
  if (value == null) return "—";
  const sign = value >= 0 ? "+" : "";
  return `${sign}${formatCurrency(value)}`;
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
