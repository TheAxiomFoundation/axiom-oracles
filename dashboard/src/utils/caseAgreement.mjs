/**
 * Case-level agreement is tri-state: null is unmeasured, exact 100 is full
 * agreement, and every other finite percentage is measured non-full agreement.
 */
export function caseAgreement(rate) {
  if (rate == null || !Number.isFinite(rate)) return null;
  return rate === 100;
}

/**
 * Buckets the cases every loaded run measured by the oracles that agree with
 * the encoding: "a+b" lists them in run order, and "none" holds a case every
 * oracle disagrees with. A case a run didn't measure joins no bucket.
 */
export function triangulate(loaded, bySuite) {
  const agreement = new Map();
  const seen = new Map();
  for (const run of loaded) {
    for (const row of bySuite[run.suite].cases) {
      const agrees = caseAgreement(row.r);
      if (agrees === null) continue;
      if (!seen.has(row.id)) {
        seen.set(row.id, 0);
        agreement.set(row.id, new Set());
      }
      seen.set(row.id, seen.get(row.id) + 1);
      if (agrees) agreement.get(row.id).add(run.oracle);
    }
  }
  const oracles = loaded.map((r) => r.oracle);
  const buckets = new Map();
  let joined = 0;
  for (const [id, count] of seen) {
    if (count !== loaded.length) continue;
    joined += 1;
    const agreeing = agreement.get(id);
    const key = oracles.filter((o) => agreeing.has(o)).join("+") || "none";
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push(id);
  }
  return { buckets, joined };
}
