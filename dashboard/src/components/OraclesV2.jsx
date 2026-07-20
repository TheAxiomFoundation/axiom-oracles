"use client";

import { useEffect, useMemo, useState } from "react";
import { loadOracleData } from "../utils/data";
import { causeFor, countUnexplained } from "../utils/programs";
import {
  ageDays,
  engineLabel,
  formatAgreementRate,
  mismatchKindLabel,
} from "../utils/format";
import { rateColor } from "../utils/colors";
import ProgramPage from "./ProgramPage";
import {
  suiteMeta,
  suiteLabel,
  reportMetric,
  isAxiomPair,
  otherOracle,
} from "../utils/suites";

/**
 * v2 concept — the oracle-first, validation-centered dashboard.
 *
 * The oracle is the first-class object: trust comes from WHO checked the
 * work. The page is one argument, top to bottom:
 *   1. Thesis — every encoding is checked against independent engines.
 *   2. The roster — one dossier card per oracle: identity, scope, verdict,
 *      and validation state. Click through for the full dossier.
 *   3. The validation ledger — every known discrepancy class ends in an
 *      action: a filed issue, a schema-validated disposition, a documented
 *      cause, or it is OPEN and says so. "Nothing ignored" is inspectable,
 *      not asserted.
 *   4. Coverage — the executable-surface burn-down; what is encoded at all
 *      is the Axiom app's story.
 * Jurisdiction is an attribute here, not the navigation.
 */

const AXIOM_APP_URL = "https://axiom-foundation.org";

/** Who each oracle IS — the identity that makes the check independent. */
const ORACLE_IDENTITY = {
  policyengine: {
    org: "PolicyEngine",
    what: "Open-source tax–benefit microsimulation of US and UK law, maintained independently of Axiom.",
    url: "https://policyengine.org",
  },
  taxsim: {
    org: "NBER",
    what: "TAXSIM-35 — the National Bureau of Economic Research's federal and state income-tax calculator, the reference model of empirical tax research.",
    url: "https://taxsim.nber.org/",
  },
  taxcalc: {
    org: "Policy Simulation Library",
    what: "Tax-Calculator — open-source US federal income-tax microsimulation used by think tanks across the spectrum.",
    url: "https://github.com/PSLmodels/Tax-Calculator",
  },
  euromod: {
    org: "European Commission JRC",
    what: "The EU's official tax–benefit microsimulation model, covering all member states including Belgium.",
    url: "https://euromod-web.jrc.ec.europa.eu/",
  },
  ukmod: {
    org: "University of Essex (CeMPA)",
    what: "UKMOD — the UK's tax–benefit microsimulation model, EUROMOD's UK descendant.",
    url: "https://www.microsimulation.ac.uk/ukmod/",
  },
  accessnyc: {
    org: "NYC Opportunity",
    what: "ACCESS NYC — New York City's official benefits screening service.",
    url: "https://access.nyc.gov/",
  },
  prd: {
    org: "Policy Rules Database",
    what: "The Atlanta Fed's Policy Rules Database of US safety-net program rules.",
    url: "https://www.atlantafed.org/economic-mobility-and-resilience/advancing-careers-for-low-income-families/policy-rules-database",
  },
};

const REGION_LABELS = { us: "US", ca: "CA", uk: "UK", be: "BE" };

/** One discrepancy class = a (suite, concept, kind) mismatch bucket. */
function buildClasses(reports, knownCauses) {
  const rows = [];
  for (const report of reports) {
    const descriptions = new Map(
      (report.aggregates || []).map((a) => [a.concept, a.description]),
    );
    const buckets = new Map();
    for (const m of report.mismatches || []) {
      const key = `${m.concept}::${m.kind}`;
      buckets.set(key, (buckets.get(key) || 0) + 1);
    }
    const dispositioned = Boolean(
      report.summary?.dispositioned?.dispositions_file,
    );
    for (const [key, count] of buckets) {
      const [concept, kind] = key.split("::");
      const cause = causeFor(knownCauses, report, concept, kind);
      const action = cause?.issue_url
        ? "filed"
        : cause
          ? "documented"
          : dispositioned
            ? "dispositioned"
            : "open";
      rows.push({
        count,
        suite: report.suite,
        program: suiteLabel(report.suite),
        region: suiteMeta(report.suite).region,
        oracle: otherOracle(report),
        engines: report.engines,
        conceptLabel: descriptions.get(concept) || concept,
        kind,
        cause,
        action,
      });
    }
  }
  const rank = { open: 0, filed: 1, documented: 2, dispositioned: 3 };
  return rows.sort(
    (a, b) => rank[a.action] - rank[b.action] || b.count - a.count,
  );
}

function ActionChip({ row }) {
  if (row.action === "open") {
    return <span className="v2-action v2-action-open">open — needs triage</span>;
  }
  if (row.action === "filed") {
    return (
      <a
        className="v2-action v2-action-filed"
        href={row.cause.issue_url}
        target="_blank"
        rel="noreferrer"
      >
        issue filed ↗
      </a>
    );
  }
  if (row.action === "documented") {
    return <span className="v2-action v2-action-doc">cause documented</span>;
  }
  return <span className="v2-action v2-action-doc">dispositioned</span>;
}

function ClassRow({ row, showOracle = true }) {
  return (
    <div className="v2-class-row">
      <span className="mono v2-class-count">{row.count.toLocaleString()}</span>
      <div className="v2-class-body">
        <div className="v2-class-label">
          {row.cause?.label || mismatchKindLabel(row.kind, row.engines)}
        </div>
        <div className="mono v2-class-meta">
          {row.program}
          {showOracle && row.oracle && <> · vs {engineLabel(row.oracle)}</>}
          {" · "}
          {row.conceptLabel}
        </div>
      </div>
      <ActionChip row={row} />
    </div>
  );
}

function Stat({ value, label, tone }) {
  return (
    <div className="v2-stat" data-tone={tone}>
      <span className="mono v2-stat-value">{value}</span>
      <span className="mono v2-stat-label">{label}</span>
    </div>
  );
}

function lastRunLabel(days) {
  if (days == null) return "not stamped";
  if (days < 1) return "ran today";
  if (days < 2) return "ran 1 day ago";
  return `ran ${Math.round(days)} days ago`;
}

function OracleCard({ oracle, selected, onSelect }) {
  const id = ORACLE_IDENTITY[oracle.id] || {};
  const openCount = oracle.classes.filter((c) => c.action === "open").length;
  const actioned = oracle.classes.length - openCount;
  return (
    <button
      type="button"
      className={`v2-card${selected ? " v2-card-selected" : ""}`}
      onClick={onSelect}
      aria-expanded={selected}
    >
      <div className="mono v2-card-eyebrow">
        {id.org || "Independent engine"}
        <span className="v2-card-regions">
          {[...oracle.regions].map((r) => (
            <span key={r} className="mono v2-region">
              {REGION_LABELS[r] || r}
            </span>
          ))}
        </span>
      </div>
      <div className="v2-card-name">{engineLabel(oracle.id)}</div>
      <p className="v2-card-what">{id.what}</p>
      <div className="v2-card-stats">
        <Stat
          value={
            <span style={{ color: rateColor(oracle.rate) }}>
              {formatAgreementRate(oracle.rate, oracle.mismatches)}
            </span>
          }
          label="agreement"
        />
        <Stat value={oracle.checks.toLocaleString()} label="checks" />
        <Stat value={oracle.programs.size} label="programs" />
      </div>
      <div className="v2-card-validation">
        {oracle.unexplained > 0 ? (
          <span className="v2-vchip v2-vchip-warn">
            {oracle.unexplained.toLocaleString()} unexplained
          </span>
        ) : (
          <span className="v2-vchip v2-vchip-good">
            every disagreement explained
          </span>
        )}
        {openCount > 0 && (
          <span className="v2-vchip v2-vchip-warn">
            {openCount} open {openCount === 1 ? "class" : "classes"}
          </span>
        )}
        {actioned > 0 && (
          <span className="v2-vchip">
            {actioned} {actioned === 1 ? "class" : "classes"} actioned
          </span>
        )}
      </div>
      <div className="mono v2-card-foot">
        <span>{lastRunLabel(oracle.lastRunDays)}</span>
        <span className="v2-card-open">
          {selected ? "close dossier" : "open dossier →"}
        </span>
      </div>
    </button>
  );
}

function Dossier({ oracle, onOpenProgram }) {
  const id = ORACLE_IDENTITY[oracle.id] || {};
  const programRows = useMemo(() => {
    const byProgram = new Map();
    for (const report of oracle.reports) {
      const meta = suiteMeta(report.suite);
      const key = `${meta.family}__${meta.jurisdiction}`;
      if (!byProgram.has(key)) {
        byProgram.set(key, {
          key,
          label: meta.label,
          region: meta.region,
          total: 0,
          mismatches: 0,
        });
      }
      const entry = byProgram.get(key);
      const m = reportMetric(report);
      entry.total += m.total;
      entry.mismatches += m.mismatches;
    }
    return [...byProgram.values()]
      .map((p) => ({
        ...p,
        rate: p.total > 0 ? ((p.total - p.mismatches) / p.total) * 100 : null,
      }))
      .sort((a, b) => (a.rate ?? 101) - (b.rate ?? 101));
  }, [oracle]);

  return (
    <section className="card-flat v2-dossier">
      <div className="section-head">
        <div>
          <div className="section-eyebrow">
            Dossier · {ORACLE_IDENTITY[oracle.id]?.org || "independent engine"}
          </div>
          <div className="section-title">{engineLabel(oracle.id)}</div>
        </div>
        {id.url && (
          <a href={id.url} target="_blank" rel="noreferrer" className="cite">
            {id.url.replace(/^https?:\/\//, "").replace(/\/$/, "")}
          </a>
        )}
      </div>
      <div className="v2-dossier-body">
        <div className="v2-dossier-col">
          <div className="mono v2-dossier-colhead">
            Programs verified against {engineLabel(oracle.id)}
          </div>
          {programRows.map((p) => (
            <button
              key={p.key}
              type="button"
              className="v2-prog-row"
              onClick={() => onOpenProgram(p.key)}
              title={`Open ${p.label} in the program explorer`}
            >
              <span className="v2-prog-label">{p.label}</span>
              <span className="mono v2-region">
                {REGION_LABELS[p.region] || p.region}
              </span>
              <span className="mono v2-prog-checks">
                {p.total.toLocaleString()}
              </span>
              <span
                className="mono v2-prog-rate"
                style={{ color: rateColor(p.rate) }}
              >
                {formatAgreementRate(p.rate, p.mismatches)}
              </span>
            </button>
          ))}
        </div>
        <div className="v2-dossier-col">
          <div className="mono v2-dossier-colhead">
            Discrepancy classes · every one ends in an action
          </div>
          {oracle.classes.length === 0 ? (
            <p className="v2-empty">
              No measured disagreements with this oracle.
            </p>
          ) : (
            oracle.classes.map((row, i) => (
              <ClassRow
                key={`${row.suite}-${row.conceptLabel}-${row.kind}-${i}`}
                row={row}
                showOracle={false}
              />
            ))
          )}
        </div>
      </div>
    </section>
  );
}

export default function OraclesV2() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [programId, setProgramId] = useState(null);
  const [ruleSummary, setRuleSummary] = useState(null);

  useEffect(() => {
    loadOracleData("")
      .then(setData)
      .catch((e) => setError(e.message));
    fetch("/data/rule_verification_summary.json")
      .then((r) => (r.ok ? r.json() : null))
      .then(setRuleSummary)
      .catch(() => {});
    // Deep-link an open program (?program=…), read once on mount.
    const fromUrl = new URLSearchParams(window.location.search).get("program");
    if (fromUrl) setProgramId(fromUrl);
  }, []);

  const model = useMemo(() => {
    if (!data) return null;
    const verification = data.reports.filter(
      (r) =>
        isAxiomPair(r) &&
        suiteMeta(r.suite).kind !== "diagnostic" &&
        (r.aggregates || []).length > 0,
    );
    const crossChecks = data.reports.filter((r) => !isAxiomPair(r)).length;

    const suiteAge = new Map(
      (data.freshness?.suites || []).map((s) => [
        s.suite,
        s.unstamped ? null : ageDays(s.generated_at),
      ]),
    );

    const byOracle = new Map();
    for (const report of verification) {
      const id = otherOracle(report);
      if (!byOracle.has(id)) {
        byOracle.set(id, {
          id,
          reports: [],
          checks: 0,
          mismatches: 0,
          regions: new Set(),
          programs: new Set(),
          lastRunDays: null,
        });
      }
      const entry = byOracle.get(id);
      entry.reports.push(report);
      const m = reportMetric(report);
      entry.checks += m.total;
      entry.mismatches += m.mismatches;
      const meta = suiteMeta(report.suite);
      entry.regions.add(meta.region);
      entry.programs.add(`${meta.family}__${meta.jurisdiction}`);
      const age = suiteAge.get(report.suite);
      if (age != null) {
        entry.lastRunDays =
          entry.lastRunDays == null ? age : Math.min(entry.lastRunDays, age);
      }
    }

    const oracles = [...byOracle.values()]
      .map((o) => ({
        ...o,
        rate: o.checks > 0 ? ((o.checks - o.mismatches) / o.checks) * 100 : null,
        unexplained: countUnexplained(o.reports, data.knownCauses || []),
        classes: buildClasses(o.reports, data.knownCauses || []),
      }))
      .sort((a, b) => b.checks - a.checks);

    const totals = {
      checks: oracles.reduce((n, o) => n + o.checks, 0),
      mismatches: oracles.reduce((n, o) => n + o.mismatches, 0),
      unexplained: oracles.reduce((n, o) => n + o.unexplained, 0),
      programs: new Set(oracles.flatMap((o) => [...o.programs])).size,
    };
    totals.rate =
      totals.checks > 0
        ? ((totals.checks - totals.mismatches) / totals.checks) * 100
        : null;

    const classes = buildClasses(verification, data.knownCauses || []);
    const actionCounts = { open: 0, filed: 0, documented: 0, dispositioned: 0 };
    for (const row of classes) actionCounts[row.action] += 1;

    return { oracles, totals, classes, actionCounts, crossChecks, verification };
  }, [data]);

  // The program explorer is the drill-down layer: runs, triangulation, and
  // the case-level unexplained queue live there.
  const openProgram = (key) => {
    setProgramId(key);
    const url = new URL(window.location.href);
    url.searchParams.set("program", key);
    window.history.replaceState(null, "", url);
  };
  const closeProgram = () => {
    setProgramId(null);
    const url = new URL(window.location.href);
    url.searchParams.delete("program");
    window.history.replaceState(null, "", url);
  };

  if (error) {
    return (
      <main className="v2-main">
        <p className="mono">Could not load oracle data: {error}</p>
      </main>
    );
  }
  if (!model) {
    return (
      <main className="v2-main">
        <p className="mono" style={{ fontSize: 13 }}>
          Loading oracle data…
        </p>
      </main>
    );
  }

  const { oracles, totals, classes, actionCounts, crossChecks } = model;
  const selectedOracle = oracles.find((o) => o.id === selected);
  const actionedTotal =
    actionCounts.filed + actionCounts.documented + actionCounts.dispositioned;
  const openRows = classes.filter((c) => c.action === "open");
  const actionedRows = classes.filter((c) => c.action !== "open");

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <span className="brand-group">
            <a
              href={AXIOM_APP_URL}
              target="_blank"
              rel="noreferrer"
              className="brand-link"
              aria-label="Axiom Foundation"
            >
              <img
                src="/axiom-foundation.svg"
                alt="Axiom Foundation"
                className="brand-axiom"
              />
            </a>
            <span className="brand-divider" aria-hidden="true" />
            <span className="brand-product">Oracles</span>
          </span>
        </div>
      </header>
      <main className="v2-main">
        {programId ? (
          <ProgramPage
            programId={programId}
            reports={model.verification}
            knownCauses={data.knownCauses || []}
            coverageOverview={data.coverageOverview}
            onBack={closeProgram}
          />
        ) : (
          <>
        {/* 1 · Thesis */}
        <section className="v2-hero">
          <div className="section-eyebrow">Independent verification</div>
          <h1 className="v2-thesis">
            Axiom never grades its own work. Every encoding is checked against{" "}
            <em>{oracles.length}</em> independent engines —{" "}
            <em>{(totals.checks / 1e6).toFixed(1)} million</em> checks,{" "}
            <em style={{ color: rateColor(totals.rate) }}>
              {formatAgreementRate(totals.rate, totals.mismatches)}
            </em>{" "}
            agreement, and every disagreement traced to an action.
          </h1>
          <p className="v2-hero-sub">
            An oracle is an independent implementation of the same law. When
            Axiom and an oracle disagree, the disagreement is triaged in the
            open: explained with a schema-validated disposition, filed as an
            issue upstream, or kept visibly open until someone does.
            {crossChecks > 0 &&
              ` Oracles are also cross-checked against each other (${crossChecks} arbitration runs), so a wrong oracle cannot silently win.`}
          </p>
          <div className="v2-trustline">
            <Stat
              value={classes.length}
              label="discrepancy classes"
            />
            <Stat
              value={actionedTotal}
              label="actioned"
              tone="good"
            />
            <Stat
              value={actionCounts.filed}
              label="issues filed"
            />
            <Stat
              value={actionCounts.open}
              label="open"
              tone={actionCounts.open > 0 ? "warn" : "good"}
            />
            <Stat
              value={totals.unexplained.toLocaleString()}
              label="unexplained checks"
              tone={totals.unexplained > 0 ? "warn" : "good"}
            />
          </div>
        </section>

        {/* 2 · The roster */}
        <section className="v2-section">
          <div className="v2-section-head">
            <span className="section-eyebrow">The oracles</span>
            <span className="v2-section-title">
              Who checks Axiom's work — open a dossier for the full record
            </span>
          </div>
          <div className="v2-roster">
            {oracles.map((oracle) => (
              <OracleCard
                key={oracle.id}
                oracle={oracle}
                selected={selected === oracle.id}
                onSelect={() =>
                  setSelected(selected === oracle.id ? null : oracle.id)
                }
              />
            ))}
          </div>
          {selectedOracle && (
            <Dossier oracle={selectedOracle} onOpenProgram={openProgram} />
          )}
        </section>

        {/* 3 · The validation ledger */}
        <section className="card-flat">
          <div className="section-head">
            <div>
              <div className="section-eyebrow">Validation ledger</div>
              <div className="section-title">
                {classes.length} discrepancy classes ·{" "}
                {actionCounts.open === 0
                  ? "all actioned"
                  : `${actionCounts.open} still open`}
              </div>
            </div>
            <span className="mono v2-ledger-key">
              filed {actionCounts.filed} · documented {actionCounts.documented}{" "}
              · dispositioned {actionCounts.dispositioned} · open{" "}
              {actionCounts.open}
            </span>
          </div>
          <div className="v2-ledger">
            {openRows.map((row, i) => (
              <ClassRow key={`open-${i}`} row={row} />
            ))}
            <details className="v2-ledger-more" open={openRows.length === 0}>
              <summary>
                {actionedRows.length} actioned classes — the explained record
              </summary>
              {actionedRows.map((row, i) => (
                <ClassRow key={`act-${i}`} row={row} />
              ))}
            </details>
          </div>
        </section>

        {/* 4 · Coverage */}
        {ruleSummary && (
          <section className="v2-coverage">
            <div className="v2-coverage-text">
              <span className="section-eyebrow">Coverage · US corpus</span>
              <p>
                <strong className="mono">
                  {ruleSummary.surfaces.executable} of{" "}
                  {ruleSummary.surfaces.total}
                </strong>{" "}
                program surfaces have an executable oracle today — the tracked
                burn-down across{" "}
                {ruleSummary.rules.total.toLocaleString()} encoded rules. What
                is encoded at all lives in the{" "}
                <a
                  href={`${AXIOM_APP_URL}/axiom/encoded`}
                  target="_blank"
                  rel="noreferrer"
                  className="cite"
                >
                  Axiom app
                </a>
                .
              </p>
            </div>
            <div
              className="v2-burndown"
              role="img"
              aria-label={`${ruleSummary.surfaces.executable} of ${ruleSummary.surfaces.total} surfaces executable`}
            >
              <div
                className="v2-burndown-fill"
                style={{
                  width: `${(ruleSummary.surfaces.executable / ruleSummary.surfaces.total) * 100}%`,
                }}
              />
            </div>
          </section>
        )}

          </>
        )}

        <footer className="v2-footer mono">
          <span>Axiom Foundation · Oracles · {new Date().getFullYear()}</span>
          <a
            href="https://github.com/TheAxiomFoundation/axiom-oracles"
            target="_blank"
            rel="noreferrer"
            className="cite"
          >
            github.com/TheAxiomFoundation/axiom-oracles
          </a>
        </footer>
      </main>
    </>
  );
}
