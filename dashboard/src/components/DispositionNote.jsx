"use client";

import { useEffect, useState } from "react";
import { loadSuiteDispositions } from "../utils/caseData";
import { engineLabel } from "../utils/format";

const DISPOSITION_LABELS = {
  explained_residual: "explained residual",
  bridge_artifact: "bridge artifact",
  axiom_encoding_gap: "axiom encoding gap",
};

/** Name the actual engine behind a gap — UK suites run EUROMOD's UK
 *  descendant UKMOD, so say that instead of the engine id's brand. */
export function dispositionTag(disposition, row) {
  if (disposition === "upstream_engine_gap") {
    const name =
      row.region === "uk" && row.oracle === "euromod"
        ? "UKMOD"
        : engineLabel(row.oracle);
    return `${name} gap`;
  }
  return DISPOSITION_LABELS[disposition] || disposition;
}

function humanizeSlug(id) {
  const s = String(id || "").replaceAll("-", " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/**
 * One recorded disposition: title (its yaml id), category tag, the
 * mechanism prose clamped to two lines until clicked, the arithmetic that
 * reproduces the delta, and the affected case / upstream issue.
 */
function DispositionEntry({ e, row }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="v2-expl-entry">
      <div className="v2-expl-head">
        <span className="v2-expl-title">{humanizeSlug(e.id)}</span>
        <span className="mono v2-expl-tag">
          {dispositionTag(e.disposition, row)}
        </span>
      </div>
      {e.mechanism && (
        <p
          className={`v2-expl-body${expanded ? "" : " v2-expl-clamp"}`}
          onClick={() => setExpanded(!expanded)}
        >
          {e.mechanism}
        </p>
      )}
      {(e.arithmetic || []).length > 0 && (
        <div className="mono v2-expl-math">
          {e.arithmetic.map((a, i) => (
            <span key={i}>
              {a.expression} = {a.equals}
            </span>
          ))}
        </div>
      )}
      {((e.cases || []).length > 0 || e.linked_issue) && (
        <div className="mono v2-expl-foot">
          {(e.cases || []).length > 0 && (
            <span>
              {e.cases.length === 1
                ? e.cases[0]
                : `${e.cases.length} cases`}
            </span>
          )}
          {e.linked_issue && (
            <a
              href={e.linked_issue}
              target="_blank"
              rel="noreferrer"
              className="v2-expl-link"
              onClick={(ev) => ev.stopPropagation()}
            >
              upstream issue ↗
            </a>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Why a dispositioned class is explained: the matching entries from the
 * suite's shipped dispositions artifact, first few up front and the rest
 * behind a count. `row` needs {suite, concept, kind, region, oracle}.
 */
export default function DispositionNote({ row }) {
  const [entries, setEntries] = useState(undefined);
  const [showAll, setShowAll] = useState(false);
  useEffect(() => {
    let live = true;
    loadSuiteDispositions(row.suite).then((d) => {
      if (!live) return;
      const match = (d?.entries || []).filter(
        (e) =>
          (!e.concept || e.concept === row.concept) &&
          (!e.kind || e.kind === row.kind),
      );
      setEntries(match);
    });
    return () => {
      live = false;
    };
  }, [row.suite, row.concept, row.kind]);

  if (entries === undefined) {
    return <p className="v2-expl mono">loading disposition…</p>;
  }
  if (!entries.length) {
    return (
      <p className="v2-expl">
        Recorded in this suite&apos;s dispositions file, but its entry
        hasn&apos;t shipped to the dashboard yet.
      </p>
    );
  }
  const shown = showAll ? entries : entries.slice(0, 3);
  return (
    <div className="v2-expl">
      {shown.map((e) => (
        <DispositionEntry key={e.id} e={e} row={row} />
      ))}
      {entries.length > shown.length && (
        <button
          type="button"
          className="mono v2-expl-more"
          onClick={() => setShowAll(true)}
        >
          show {entries.length - shown.length} more disposition
          {entries.length - shown.length === 1 ? "" : "s"}
        </button>
      )}
    </div>
  );
}
