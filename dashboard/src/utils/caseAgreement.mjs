/**
 * Case-level agreement is tri-state: null is unmeasured, exact 100 is full
 * agreement, and every other finite percentage is measured non-full agreement.
 */
export function caseAgreement(rate) {
  if (rate == null || !Number.isFinite(rate)) return null;
  return rate === 100;
}
