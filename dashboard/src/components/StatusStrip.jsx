"use client";

import { ageDays } from "./FreshnessRegister";
import {
  buildProgramRows,
  rowVerdict,
  countUnexplained,
} from "../utils/programs";
import { suiteMeta, rateStatus } from "../utils/suites";

/**
 * The health strip under the hero: the numbers that decide whether the
 * verdict above can be taken at face value — the program census, anything
 * still unexplained, and how current the evidence is. Each chip deep-links
 * to the section that carries the detail (#needs-review, #programs,
 * #open-gaps, #freshness).
 */

function Chip({ href, tone, onClick, children }) {
  const inner = (
    <>
      <span className="status-dot" aria-hidden="true" />
      {children}
    </>
  );
  if (!href) {
    return (
      <span className="status-chip" data-tone={tone}>
        {inner}
      </span>
    );
  }
  return (
    <a
      href={href}
      className="status-chip status-chip-link"
      data-tone={tone}
      onClick={onClick}
    >
      {inner}
    </a>
  );
}

export default function StatusStrip({ reports, knownCauses, freshness, region }) {
  const unexplained = countUnexplained(reports, knownCauses);

  // One census fact, not three: verified count, and everything else is
  // simply "flagged" — the table's tier chips carry the finer split.
  const programRows = buildProgramRows(reports);
  const total = programRows.length;
  const verified = programRows.filter(
    (row) => rateStatus(rowVerdict(row).rate) === "verified",
  ).length;
  const flagged = total - verified;

  // Same region slice and staleness rule as the freshness register below.
  const maxAge = freshness?.max_age_days || 14;
  const suites = (freshness?.suites || [])
    .filter((s) => (region ? suiteMeta(s.suite).region === region : true))
    .map((s) => ({ ...s, days: ageDays(s.generated_at) }));
  const stamped = suites.filter((s) => !s.unstamped && s.days != null);
  const staleCount = stamped.filter((s) => s.days > maxAge).length;
  const newest = stamped.length
    ? Math.min(...stamped.map((s) => s.days))
    : null;

  const newestLabel =
    newest == null
      ? null
      : newest < 1
        ? "today"
        : newest < 2
          ? "1 day ago"
          : `${Math.round(newest)} days ago`;

  return (
    <div className="status-strip">
      {total > 0 && (
        <Chip
          href={flagged > 0 ? "#needs-review" : "#programs"}
          tone={flagged > 0 ? "warn" : "good"}
        >
          {verified} of {total} programs verified
          {flagged > 0 && ` · ${flagged} flagged`}
        </Chip>
      )}
      <Chip
        href={unexplained > 0 ? "#open-gaps" : null}
        tone={unexplained > 0 ? "warn" : "good"}
      >
        {unexplained > 0
          ? `${unexplained.toLocaleString()} unexplained ${
              unexplained === 1 ? "disagreement" : "disagreements"
            }`
          : "No unexplained disagreements"}
      </Chip>
      {newestLabel && (
        <Chip href="#freshness" tone={staleCount > 0 ? "warn" : "neutral"}>
          latest run {newestLabel}
          {staleCount > 0 &&
            ` · ${staleCount} stale ${staleCount === 1 ? "report" : "reports"}`}
        </Chip>
      )}
    </div>
  );
}
