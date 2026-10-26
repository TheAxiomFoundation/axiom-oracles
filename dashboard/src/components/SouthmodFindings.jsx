"use client";

import { useEffect, useMemo, useState } from "react";
import { BASE_PATH } from "../utils/basePath";
import { SOUTHMOD_MODELS, suiteLabel } from "../utils/suites";
import {
  axiomGapLabel,
  classificationLabel,
  findingAnchor,
  findingText,
  foldGroups,
  groupFindings,
  scopeFindings,
  statusLabel,
  STATUS_TONES,
} from "../utils/southmodFindings.mjs";

// One fetch per page load, shared by every mount of the section; a failed
// fetch is forgotten so the next mount retries. Written by
// scripts/publish_issue_ledgers.py; CI's --check keeps it equal to the
// packaged ledgers.
let bundlePromise = null;
function loadSouthmodIssues() {
  if (!bundlePromise) {
    bundlePromise = fetch(`${BASE_PATH}/data/southmod-issues.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.status))))
      .catch(() => {
        bundlePromise = null;
        return null;
      });
  }
  return bundlePromise;
}

/** The entry id a `#finding-<id>` URL fragment names, or null. */
function hashFinding() {
  if (typeof window === "undefined") return null;
  let hash;
  try {
    hash = decodeURIComponent(window.location.hash.slice(1));
  } catch {
    return null;
  }
  return hash.startsWith("finding-") ? hash.slice("finding-".length) : null;
}

function Field({ label, children }) {
  return (
    <div className="v2-finding-field">
      <span className="mono v2-finding-label">{label}</span>
      <div className="v2-finding-value">{children}</div>
    </div>
  );
}

function FindingDetail({ entry, onOpenSuite }) {
  const run = entry.observed_with || {};
  const outputs = entry.oracle_outputs || [];
  const suites = entry.affected_comparisons || [];
  const concepts = entry.affected_concepts || [];
  return (
    <div className="v2-expl v2-finding-expl">
      {entry.statute && <Field label="source">{entry.statute}</Field>}
      {entry.axiom_position && (
        <Field label="Axiom's position">{entry.axiom_position}</Field>
      )}
      {entry.statutory_evidence_gap && (
        <Field label="evidence gap">{entry.statutory_evidence_gap}</Field>
      )}
      {entry.reported_upstream && (
        <Field label="upstream">{entry.reported_upstream}</Field>
      )}
      {outputs.length > 0 && (
        <Field label="model outputs">
          {outputs.map((o) => (
            <code key={o} className="pp-cause-code v2-finding-code">
              {o}
            </code>
          ))}
        </Field>
      )}
      {suites.length > 0 && (
        <Field label="comparisons">
          {suites.map((suite) => (
            <button
              key={suite}
              type="button"
              className="v2-finding-suite"
              onClick={() => onOpenSuite(suite)}
              title={`Open the program page for ${suite}`}
            >
              {suiteLabel(suite)} →
            </button>
          ))}
        </Field>
      )}
      {concepts.length > 0 && (
        <Field label="Axiom concepts">
          {concepts.map((c) => (
            <span key={c} className="mono v2-finding-concept">
              {c}
            </span>
          ))}
        </Field>
      )}
      <Field label="observed on">
        <span className="mono">
          {[run.system, run.dataset, run.model_root].filter(Boolean).join(" · ")}
        </span>
        {run.reproduction_note && (
          <span className="v2-finding-note">{run.reproduction_note}</span>
        )}
      </Field>
      <div className="mono v2-expl-foot">
        <a className="v2-expl-link" href={`#${findingAnchor(entry.id)}`}>
          #{entry.id}
        </a>
        <span>{axiomGapLabel(entry.counts_as_axiom_gap)}</span>
      </div>
    </div>
  );
}

function FindingRow({ entry, open, pinned, onToggle, onOpenSuite }) {
  const status = entry.status;
  return (
    <div
      className={`v2-finding${pinned ? " v2-finding-pinned" : ""}`}
      id={findingAnchor(entry.id)}
    >
      <div
        className="v2-ledger-row v2-finding-row v2-ledger-click"
        role="button"
        tabIndex={0}
        aria-expanded={open}
        onClick={onToggle}
        onKeyDown={(ev) => {
          if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            onToggle();
          }
        }}
      >
        <span className="v2-ledger-what">
          <span className={open ? undefined : "v2-finding-clamp"}>
            {findingText(entry)}
          </span>
          <span className="v2-ledger-concept">
            {classificationLabel(entry.classification)}
            {" · "}
            <span className="v2-ledger-why">
              {open ? "hide details" : "see details"}
            </span>
          </span>
        </span>
        {status ? (
          <span
            className={`v2-action v2-action-${STATUS_TONES[status] || "muted"}`}
          >
            {statusLabel(status)}
          </span>
        ) : (
          <span />
        )}
      </div>
      {open && <FindingDetail entry={entry} onOpenSuite={onOpenSuite} />}
    </div>
  );
}

/**
 * The SOUTHMOD models' findings ledgers, on the SOUTHMOD oracle page: what
 * each country model returned on synthetic households where it departs from
 * the statute Axiom encodes, or where a comparison adopts a convention. One
 * group per model, scoped by the record's country chips and program filter.
 *
 * `keepSuite(suite)` is the record's program filter (null for none);
 * `onOpenSuite(suite)` opens a comparison's program page.
 */
export default function SouthmodFindings({ region, keepSuite, onOpenSuite }) {
  const [bundle, setBundle] = useState(undefined);
  const [openId, setOpenId] = useState(null);
  const [pinned, setPinned] = useState(null);

  useEffect(() => {
    let live = true;
    const follow = () => {
      const target = hashFinding();
      if (target) {
        setPinned(target);
        setOpenId(target);
      }
    };
    loadSouthmodIssues().then((b) => {
      if (!live) return;
      setBundle(b);
      follow();
    });
    // A permalink clicked (or a fragment typed) after load pins its entry too.
    window.addEventListener("hashchange", follow);
    return () => {
      live = false;
      window.removeEventListener("hashchange", follow);
    };
  }, []);

  // Scroll a deep-linked finding into view once it has rendered.
  useEffect(() => {
    if (!pinned) return;
    const el = document.getElementById(findingAnchor(pinned));
    if (el) el.scrollIntoView({ block: "center" });
  }, [pinned, bundle]);

  const scope = useMemo(
    () =>
      scopeFindings(bundle ? groupFindings(bundle, SOUTHMOD_MODELS) : [], {
        region,
        keepSuite,
      }),
    [bundle, region, keepSuite],
  );

  const head = <div className="mono v2-dossier-colhead">Model findings</div>;
  if (bundle === undefined) {
    return (
      <>
        {head}
        <p className="v2-empty mono">loading model findings…</p>
      </>
    );
  }
  if (bundle === null) {
    return (
      <>
        {head}
        <p className="v2-empty">The model findings could not be loaded.</p>
      </>
    );
  }

  const { groups, total, inScope } = scope;
  const { shown, rest, pinnedInRest } = foldGroups(groups, 10, pinned);
  const restCount = rest.reduce((n, g) => n + g.entries.length, 0);

  const renderGroup = (g) => (
    <div key={g.region} className="v2-ledger-group">
      <div className="v2-ledger-prog">
        <span className="v2-ledger-progname">
          {g.country} · {g.model}
        </span>
        <span className="mono v2-finding-count">
          {g.ledger
            ? `${g.entries.length === g.total ? g.total : `${g.entries.length} of ${g.total}`} finding${g.total === 1 ? "" : "s"} · updated ${g.updatedAt}`
            : "no ledger"}
        </span>
      </div>
      {!g.ledger ? (
        <p className="v2-empty v2-finding-none">
          {g.note || `No findings ledger is recorded for ${g.model}.`}
        </p>
      ) : g.entries.length === 0 ? (
        <p className="v2-empty v2-finding-none">
          No {g.model} findings in this scope.
        </p>
      ) : (
        g.entries.map((entry) => (
          <FindingRow
            key={entry.id}
            entry={entry}
            open={openId === entry.id}
            pinned={pinned === entry.id}
            onToggle={() => setOpenId(openId === entry.id ? null : entry.id)}
            onOpenSuite={onOpenSuite}
          />
        ))
      )}
    </div>
  );

  return (
    <>
      {head}
      <p className="v2-finding-intro">
        What the country models were seen to do while being compared with
        Axiom on synthetic households: model simplifications and defect
        candidates, conventions a comparison adopts to stay like-for-like,
        and gaps in the published statutory record. Under the SOUTHMOD_A4.0
        licence an entry records observed outputs, variable names and
        statutory citations, never model content.{" "}
        <span className="mono">
          {inScope === total
            ? `${total} finding${total === 1 ? "" : "s"}`
            : `${inScope} of ${total} findings in scope`}
        </span>
      </p>
      {groups.length === 0 ? (
        <p className="v2-empty">
          No model findings touch the programs in this scope.
        </p>
      ) : (
        <div className="v2-ledger">
          {shown.map(renderGroup)}
          {rest.length > 0 && (
            <details
              // Remount per pinned entry, so a later deep link into the fold
              // opens it even after the reader closed it.
              key={pinnedInRest ? `pinned-${pinned}` : "fold"}
              className="v2-ledger-more"
              open={pinnedInRest || undefined}
            >
              <summary>
                show {restCount} more finding{restCount === 1 ? "" : "s"} ·{" "}
                {rest.map((g) => g.country).join(", ")}
              </summary>
              {rest.map(renderGroup)}
            </details>
          )}
        </div>
      )}
    </>
  );
}
