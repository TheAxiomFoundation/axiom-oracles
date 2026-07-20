"use client";

import { formatAgreementRate } from "../utils/format";
import { rateColor } from "../utils/colors";
import { rowVerdict, countUnexplained } from "../utils/programs";
import { US_STATE_NAMES, rateStatus, programKey } from "../utils/suites";

/**
 * The queue above the matrix: every program below the verified band, worst
 * first, with its rate and its unexplained-disagreement count. This is the
 * actionable slice of the program census — the matrix below carries the
 * full shape, this list carries the work.
 */

export default function ProgramExceptions({ rows, knownCauses, onOpen }) {
  const flagged = (rows || [])
    .filter((row) => rateStatus(rowVerdict(row).rate) !== "verified")
    .sort(
      (a, b) => (rowVerdict(a).rate ?? 101) - (rowVerdict(b).rate ?? 101),
    );
  if (!flagged.length) return null;

  return (
    <section className="card-flat" id="needs-review">
      <div className="section-head">
        <div>
          <div className="section-eyebrow">Needs review</div>
          <div className="section-title">
            {flagged.length} {flagged.length === 1 ? "program" : "programs"}{" "}
            below the verified band
          </div>
        </div>
      </div>
      <div className="exc-list">
        {flagged.map((row) => {
          const verdict = rowVerdict(row);
          const unexplained = countUnexplained(row.reports, knownCauses);
          const where =
            US_STATE_NAMES[row.meta.jurisdiction] || row.meta.jurisdiction;
          return (
            <button
              key={programKey(row.meta)}
              type="button"
              className="exc-row"
              onClick={() => onOpen(programKey(row.meta))}
              title={`Open ${row.meta.label}`}
            >
              <span className="pst-label">
                <span
                  className="pst-dot"
                  style={{ background: rateColor(verdict.rate) }}
                  aria-hidden="true"
                />
                {row.meta.label}
              </span>
              <span className="mono pst-where">{where}</span>
              <span
                className="mono exc-rate"
                style={{ color: rateColor(verdict.rate) }}
              >
                {formatAgreementRate(verdict.rate, verdict.mismatches)}
              </span>
              <span className="mono exc-unexplained">
                {unexplained > 0
                  ? `${unexplained.toLocaleString()} unexplained`
                  : "all explained"}
              </span>
              <span className="pst-arrow" aria-hidden="true">
                →
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
