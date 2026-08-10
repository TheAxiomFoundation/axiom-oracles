"use client";

import { useEffect, useMemo, useState } from "react";
import { loadOracleData } from "../utils/data";
import { BASE_PATH } from "../utils/basePath";
import { causeFor, countUnexplained } from "../utils/programs";
import {
  engineLabel,
  formatAgreementRate,
  formatPct,
  mismatchKindLabel,
} from "../utils/format";
import ProgramPage from "./ProgramPage";
import DispositionNote from "./DispositionNote";
import HouseholdsView from "./Households";
import {
  suiteMeta,
  suiteLabel,
  reportMetric,
  topLevelAggregates,
  isAxiomPair,
  otherOracle,
  JURISDICTION_LABELS,
} from "../utils/suites";

/**
 * v2 concept — the oracle-first, validation-centered dashboard.
 *
 * The oracle is the first-class object: trust comes from WHO checked the
 * work. The page is one argument, top to bottom:
 *   1. Thesis — every encoding is checked against independent engines.
 *   2. The roster — one card per oracle: identity, scope, verdict, and
 *      validation state. A card opens into the oracle's full record, where
 *      every discrepancy class ends in an action — a filed issue, a
 *      schema-validated disposition, a documented cause, or it is OPEN and
 *      says so — plus the per-household evidence.
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
  "snap-qc": {
    org: "USDA Food and Nutrition Service",
    what: "SNAP Quality Control microdata — the USDA's annual audit sample of real SNAP cases, re-verified case by case by state reviewers. Administrative records of benefits actually issued, not a simulation.",
    url: "https://snapqcdata.us",
  },
  spsm: {
    org: "Statistics Canada",
    what: "SPSD/M — Statistics Canada's Social Policy Simulation Database and Model, the reference Canadian tax–transfer microsimulation, run under licence over its synthetic database. Results carry the SPSD/M licence attribution; per-household evidence stays local.",
    url: "https://www.statcan.gc.ca/en/microsimulation/spsdm/spsdm",
  },
};

const REGION_LABELS = { us: "US", ca: "CA", uk: "UK", be: "BE", de: "DE", dk: "DK" };

/**
 * Oracles hidden from every dashboard surface (roster, hero totals, program
 * census, household drill) without touching their data or dispositions.
 * TAXSIM is parked here until its comparison surface is rebuilt — the full
 * mismatch rows are not yet persisted (axiom-oracles#439), so most of its
 * open residuals cannot be triaged. The unexplained publication ratchet
 * still gates its reports at the data level regardless of UI visibility.
 * Delete an entry to restore the oracle.
 */
const HIDDEN_ORACLES = new Set(["taxsim"]);

/**
 * The unit of counting is the household case: one household compared once,
 * no matter how many concepts (liability, CTC, EITC, …) that comparison
 * covers — component concepts roll up into their parent, and a household's
 * concept-by-concept comparisons are the evidence, not extra households.
 */
function reportHouseholds(report) {
  return Number.isFinite(report.case_count)
    ? report.case_count
    : (report.cases || []).length;
}

function compactCount(n) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} million`;
  return n.toLocaleString();
}

/**
 * One discrepancy class = a (suite, concept, kind) mismatch bucket.
 * Large suites slim the recorded mismatch list, so bucket counts from it
 * are lower bounds — except when a concept shows a single kind, where the
 * aggregate's exact mismatch_count applies (and must, so these figures
 * never contradict the run totals).
 */
function buildClasses(reports, knownCauses) {
  const rows = [];
  for (const report of reports) {
    const descriptions = new Map(
      (report.aggregates || []).map((a) => [a.concept, a.description]),
    );
    const aggMismatches = new Map();
    for (const agg of topLevelAggregates(report.aggregates)) {
      aggMismatches.set(
        agg.concept,
        (aggMismatches.get(agg.concept) || 0) + (agg.mismatch_count || 0),
      );
    }
    const list = report.mismatches || [];
    const truncated = (report.summary?.mismatch_count ?? 0) > list.length;
    const buckets = new Map();
    for (const m of list) {
      const key = `${m.concept}::${m.kind}`;
      buckets.set(key, (buckets.get(key) || 0) + 1);
    }
    const kindsPerConcept = new Map();
    for (const key of buckets.keys()) {
      const concept = key.split("::")[0];
      kindsPerConcept.set(concept, (kindsPerConcept.get(concept) || 0) + 1);
    }
    const dispositioned = Boolean(
      report.summary?.dispositioned?.dispositions_file,
    );
    for (const [key, recorded] of buckets) {
      const [concept, kind] = key.split("::");
      const singleKind = kindsPerConcept.get(concept) === 1;
      const count =
        singleKind && aggMismatches.has(concept)
          ? aggMismatches.get(concept)
          : recorded;
      const lowerBound = truncated && !singleKind;
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
        lowerBound,
        suite: report.suite,
        program: suiteLabel(report.suite),
        region: suiteMeta(report.suite).region,
        oracle: otherOracle(report),
        engines: report.engines,
        concept,
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

/**
 * Discrepancy classes grouped by program: a program header with its case
 * total, then one line per class — count, what differs, which concept,
 * and where the triage stands. Explained classes (documented, filed, or
 * dispositioned) expand on click to show WHY. Programs with open classes
 * surface first; the long tail collapses behind a summary that still
 * states its size.
 */
function ClassLedger({ classes }) {
  const [openKey, setOpenKey] = useState(null);
  const byProgram = new Map();
  for (const row of classes) {
    if (!byProgram.has(row.program)) {
      byProgram.set(row.program, {
        program: row.program,
        rows: [],
        total: 0,
        open: 0,
      });
    }
    const g = byProgram.get(row.program);
    g.rows.push(row);
    g.total += row.count;
    if (row.action === "open") g.open += 1;
  }
  const groups = [...byProgram.values()].sort(
    (a, b) => (b.open > 0) - (a.open > 0) || b.total - a.total,
  );

  // Show whole programs until ~10 class lines are on screen; the rest
  // fold away. Never split a program across the fold.
  const shown = [];
  let lines = 0;
  let i = 0;
  while (i < groups.length && (lines < 10 || shown.length === 0)) {
    shown.push(groups[i]);
    lines += groups[i].rows.length;
    i += 1;
  }
  const rest = groups.slice(i);
  const restClasses = rest.reduce((n, g) => n + g.rows.length, 0);

  const renderGroup = (g) => (
    <div key={g.program} className="v2-ledger-group">
      <div className="v2-ledger-prog">
        <span className="v2-ledger-progname">{g.program}</span>
      </div>
      {g.rows.map((row, ri) => {
        const key = `${row.suite}:${row.concept}:${row.kind}`;
        const explainable = row.action !== "open";
        const isOpen = openKey === key;
        return (
          <div key={ri}>
            <div
              className={`v2-ledger-row${explainable ? " v2-ledger-click" : ""}`}
              onClick={
                explainable
                  ? () => setOpenKey(isOpen ? null : key)
                  : undefined
              }
            >
              <span
                className="mono v2-ledger-count"
                title={
                  row.lowerBound
                    ? "Counted from the recorded mismatch rows — the true count may be higher"
                    : undefined
                }
              >
                {row.lowerBound ? "≥" : ""}
                {row.count.toLocaleString()}
              </span>
              <span className="v2-ledger-what">
                {row.cause?.label ||
                  mismatchKindLabel(row.kind, row.engines)}
                <span className="v2-ledger-concept">
                  {row.conceptLabel}
                  {explainable && (
                    <>
                      {" · "}
                      <span className="v2-ledger-why">
                        {isOpen ? "hide details" : "see details"}
                      </span>
                    </>
                  )}
                </span>
              </span>
              <ActionChip row={row} />
            </div>
            {isOpen &&
              (row.cause?.description ? (
                <div className="v2-expl">{row.cause.description}</div>
              ) : (
                <DispositionNote row={row} />
              ))}
          </div>
        );
      })}
    </div>
  );

  return (
    <div className="v2-ledger">
      {shown.map(renderGroup)}
      {rest.length > 0 && (
        <details className="v2-ledger-more">
          <summary>
            show {restClasses} more class{restClasses === 1 ? "" : "es"}{" "}
            across {rest.length} program{rest.length === 1 ? "" : "s"}
          </summary>
          {rest.map(renderGroup)}
        </details>
      )}
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

function OracleCard({ oracle, selected, onSelect }) {
  const id = ORACLE_IDENTITY[oracle.id] || {};
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
      <div
        className="v2-card-stats"
        title={`${oracle.checks.toLocaleString()} individual checks across these households`}
      >
        <Stat value={oracle.households.toLocaleString()} label="households" />
        <Stat value={oracle.programs.size} label="programs" />
      </div>
      <div className="mono v2-card-foot">
        <span className="v2-card-open">
          {selected ? "close" : "full record →"}
        </span>
      </div>
    </button>
  );
}

const REGION_ORDER = ["us", "ca", "uk", "be", "de", "dk"];

function ProgRow({ p, onOpenProgram }) {
  return (
    <button
      type="button"
      className="v2-prog-row"
      onClick={() => onOpenProgram(p.key)}
      title={`Open ${p.label} in the program explorer`}
    >
      <span className="v2-prog-label">
        {p.label}
        {p.oracles && p.oracles.size > 0 && (
          <span className="mono v2-prog-oracles">
            vs {[...p.oracles].map(engineLabel).join(", ")}
          </span>
        )}
      </span>
      <span className="mono v2-region">
        {REGION_LABELS[p.region] || p.region}
      </span>
      <span
        className="mono v2-prog-checks"
        title={`${p.households.toLocaleString()} households · ${p.total.toLocaleString()} checks`}
      >
        {p.households.toLocaleString()}
        <span className="v2-prog-unit"> households</span>
      </span>
      <span className="mono v2-prog-rate">
        <span className="v2-prog-rate-part">
          <span className="v2-prog-rate-value">
            {formatAgreementRate(p.rate, p.mismatches)}
          </span>
          <span className="v2-prog-unit">agree</span>
        </span>
        {p.explainedRate != null &&
          p.rate != null &&
          p.explainedRate - p.rate >= 0.05 && (
            <span
              className="v2-prog-rate-part"
              title="Counting disagreements with schema-validated dispositions as explained"
            >
              <span className="v2-prog-rate-value">
                {formatPct(p.explainedRate, 1)}
              </span>
              <span className="v2-prog-unit">explained</span>
            </span>
          )}
      </span>
    </button>
  );
}

const programKeyOf = (suite) => {
  const meta = suiteMeta(suite);
  return `${meta.family}__${meta.jurisdiction}`;
};

function OracleRecord({ oracle, knownCauses, onOpenProgram, onBrowseHouseholds }) {
  // One filter bar scopes the whole record: country chips + program select
  // apply to the alignment census, the discrepancy classes, and the
  // household browser alike.
  const regions = REGION_ORDER.filter((r) => oracle.regions.has(r));
  const [region, setRegion] = useState(null);
  const [program, setProgram] = useState(null);
  const [query, setQuery] = useState("");

  const regionScoped = useMemo(() => {
    if (!region) return oracle;
    return {
      ...oracle,
      reports: oracle.reports.filter(
        (r) => suiteMeta(r.suite).region === region,
      ),
      classes: oracle.classes.filter((c) => c.region === region),
    };
  }, [oracle, region]);

  const programRows = useMemo(() => {
    const byProgram = new Map();
    for (const report of regionScoped.reports) {
      const meta = suiteMeta(report.suite);
      const key = `${meta.family}__${meta.jurisdiction}`;
      if (!byProgram.has(key)) {
        byProgram.set(key, {
          key,
          label: meta.label,
          region: meta.region,
          total: 0,
          mismatches: 0,
          unexplained: 0,
          households: 0,
        });
      }
      const entry = byProgram.get(key);
      const m = reportMetric(report);
      entry.total += m.total;
      entry.mismatches += m.mismatches;
      entry.unexplained += countUnexplained([report], knownCauses || []);
      entry.households += reportHouseholds(report);
    }
    return [...byProgram.values()]
      .map((p) => ({
        ...p,
        rate: p.total > 0 ? ((p.total - p.mismatches) / p.total) * 100 : null,
        explainedRate:
          p.total > 0 ? ((p.total - p.unexplained) / p.total) * 100 : null,
      }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [regionScoped, knownCauses]);

  // A stale program selection (after a scope change) falls back to all.
  const activeProgram = programRows.some((p) => p.key === program)
    ? program
    : null;

  // The search box narrows to every program whose name matches; the
  // dropdown pins exactly one. Either way the whole record follows.
  const q = query.trim().toLowerCase();
  const matchedKeys = useMemo(() => {
    if (activeProgram || !q) return null;
    return new Set(
      programRows
        .filter((p) => p.label.toLowerCase().includes(q))
        .map((p) => p.key),
    );
  }, [programRows, activeProgram, q]);

  const scoped = useMemo(() => {
    if (!activeProgram && !matchedKeys) return regionScoped;
    const keep = (suite) => {
      const key = programKeyOf(suite);
      return activeProgram ? key === activeProgram : matchedKeys.has(key);
    };
    return {
      ...regionScoped,
      reports: regionScoped.reports.filter((r) => keep(r.suite)),
      classes: regionScoped.classes.filter((c) => keep(c.suite)),
    };
  }, [regionScoped, activeProgram, matchedKeys]);

  const visibleRows = activeProgram
    ? programRows.filter((p) => p.key === activeProgram)
    : matchedKeys
      ? programRows.filter((p) => matchedKeys.has(p.key))
      : programRows;
  // Highest alignment first: fully agreeing programs alphabetically,
  // then the rest by descending rate — all visible, nothing folded away.
  const alignmentRows = [
    ...[...visibleRows]
      .filter((p) => p.mismatches === 0)
      .sort((a, b) => a.label.localeCompare(b.label)),
    ...[...visibleRows]
      .filter((p) => p.mismatches > 0)
      .sort((a, b) => (b.rate ?? -1) - (a.rate ?? -1)),
  ];

  return (
    <section className="card-flat v2-dossier">
      <div className="v2-scope" role="group" aria-label="Scope">
        {regions.length > 1 ? (
          [null, ...regions].map((r) => (
            <button
              key={r ?? "all"}
              type="button"
              className={`v2-scope-chip${region === r ? " v2-scope-chip-on" : ""}`}
              aria-pressed={region === r}
              onClick={() => setRegion(r)}
            >
              {r ? REGION_LABELS[r] || r : "All countries"}
            </button>
          ))
        ) : (
          <span className="mono v2-dossier-colhead v2-scope-label">
            Program alignment against {engineLabel(oracle.id)}
          </span>
        )}
        <input
          className="input-pill v2-scope-search"
          type="search"
          placeholder="search programs…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setProgram(null);
          }}
          aria-label="Search programs"
        />
        <select
          className="input-pill v2-scope-select"
          value={activeProgram ?? ""}
          onChange={(e) => {
            setProgram(e.target.value || null);
            setQuery("");
          }}
          aria-label="Program"
        >
          <option value="">All programs · {programRows.length}</option>
          {programRows.map((p) => (
            <option key={p.key} value={p.key}>
              {p.label}
            </option>
          ))}
        </select>
      </div>

      <div className="v2-record-stack">
        <div className="v2-dossier-col">
          {regions.length > 1 && (
            <div className="mono v2-dossier-colhead">
              Program alignment against {engineLabel(oracle.id)}
            </div>
          )}
          {alignmentRows.length === 0 && (
            <p className="v2-empty">No programs in this scope.</p>
          )}
          <div className="v2-prog-grid">
            {alignmentRows.map((p) => (
              <ProgRow key={p.key} p={p} onOpenProgram={onOpenProgram} />
            ))}
          </div>
        </div>

        <div className="v2-dossier-col">
          <div className="mono v2-dossier-colhead">Discrepancy classes</div>
          {scoped.classes.length === 0 ? (
            <p className="v2-empty">
              No measured disagreements in this scope.
            </p>
          ) : (
            <ClassLedger classes={scoped.classes} />
          )}
        </div>
      </div>
      {onBrowseHouseholds && (
        <div className="v2-record-foot">
          <button
            type="button"
            className="pp-browse"
            onClick={onBrowseHouseholds}
          >
            Browse the households →
          </button>
        </div>
      )}
    </section>
  );
}

export default function OraclesV2() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  // Three-level drill: {} overview · {oracle}|{program} detail ·
  // {view:"households", oracle?|program?} evidence. Mirrored in the URL.
  const [route, setRoute] = useState({});
  const [overviewRegion, setOverviewRegion] = useState(null);
  const [overviewJurisdiction, setOverviewJurisdiction] = useState(null);
  const [overviewQuery, setOverviewQuery] = useState("");

  useEffect(() => {
    loadOracleData(BASE_PATH)
      .then(setData)
      .catch((e) => setError(e.message));
    // Deep-link, read once on mount.
    const params = new URLSearchParams(window.location.search);
    const next = {};
    if (params.get("oracle")) next.oracle = params.get("oracle");
    if (params.get("program")) next.program = params.get("program");
    if (params.get("view") === "households") next.view = "households";
    setRoute(next);
  }, []);

  const navigate = (next) => {
    setRoute(next);
    const url = new URL(window.location.href);
    for (const k of ["oracle", "program", "view"]) url.searchParams.delete(k);
    if (next.oracle) url.searchParams.set("oracle", next.oracle);
    if (next.program) url.searchParams.set("program", next.program);
    if (next.view) url.searchParams.set("view", next.view);
    window.history.replaceState(null, "", url);
    window.scrollTo(0, 0);
  };

  const model = useMemo(() => {
    if (!data) return null;
    const verification = data.reports.filter(
      (r) =>
        isAxiomPair(r) &&
        !HIDDEN_ORACLES.has(otherOracle(r)) &&
        suiteMeta(r.suite).kind !== "diagnostic" &&
        (r.aggregates || []).length > 0,
    );
    const crossChecks = data.reports.filter(
      (r) =>
        !isAxiomPair(r) &&
        !HIDDEN_ORACLES.has(r.engines?.left) &&
        !HIDDEN_ORACLES.has(r.engines?.right),
    ).length;

    const byOracle = new Map();
    for (const report of verification) {
      const id = otherOracle(report);
      if (!byOracle.has(id)) {
        byOracle.set(id, {
          id,
          reports: [],
          checks: 0,
          mismatches: 0,
          households: 0,
          regions: new Set(),
          programs: new Set(),
        });
      }
      const entry = byOracle.get(id);
      entry.reports.push(report);
      const m = reportMetric(report);
      entry.checks += m.total;
      entry.mismatches += m.mismatches;
      entry.households += reportHouseholds(report);
      const meta = suiteMeta(report.suite);
      entry.regions.add(meta.region);
      entry.programs.add(`${meta.family}__${meta.jurisdiction}`);
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
      households: oracles.reduce((n, o) => n + o.households, 0),
      programs: new Set(oracles.flatMap((o) => [...o.programs])).size,
    };
    totals.rate =
      totals.checks > 0
        ? ((totals.checks - totals.mismatches) / totals.checks) * 100
        : null;

    return { oracles, totals, crossChecks, verification };
  }, [data]);

  // Level 1's program census: every verified program across every oracle.
  const allPrograms = useMemo(() => {
    if (!model) return [];
    const byProgram = new Map();
    for (const report of model.verification) {
      const meta = suiteMeta(report.suite);
      const key = `${meta.family}__${meta.jurisdiction}`;
      if (!byProgram.has(key)) {
        byProgram.set(key, {
          key,
          label: meta.label,
          region: meta.region,
          jurisdiction: meta.jurisdiction,
          total: 0,
          mismatches: 0,
          unexplained: 0,
          households: 0,
          oracles: new Set(),
        });
      }
      const entry = byProgram.get(key);
      const m = reportMetric(report);
      entry.total += m.total;
      entry.mismatches += m.mismatches;
      entry.unexplained += countUnexplained([report], data.knownCauses || []);
      entry.households += reportHouseholds(report);
      entry.oracles.add(otherOracle(report));
    }
    return [...byProgram.values()].map((p) => ({
      ...p,
      rate: p.total > 0 ? ((p.total - p.mismatches) / p.total) * 100 : null,
      explainedRate:
        p.total > 0 ? ((p.total - p.unexplained) / p.total) * 100 : null,
    }));
  }, [model]);

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

  const { oracles, totals, crossChecks } = model;
  const routeOracle = oracles.find((o) => o.id === route.oracle);

  // Households scope: the axiom-pair reports level 3 browses.
  const householdReports =
    route.view === "households"
      ? route.program
        ? model.verification.filter(
            (r) => programKeyOf(r.suite) === route.program,
          )
        : routeOracle
          ? routeOracle.reports
          : model.verification
      : [];
  const householdTitle = route.program
    ? suiteMeta(
        (householdReports[0] || {}).suite || route.program,
      ).label
    : routeOracle
      ? `vs ${engineLabel(routeOracle.id)}`
      : "all programs";

  // The overview census: country-scoped, disagreeing programs worst-first,
  // then the fully-agreeing ones alphabetically — all visible.
  const censusRegions = REGION_ORDER.filter((r) =>
    allPrograms.some((p) => p.region === r),
  );
  // A country with several jurisdictions (the US, for now) gets a second
  // filter level. Jurisdictions offered are the ones the country's
  // programs actually carry; a stale pick falls back to all.
  const censusJurisdictions = overviewRegion
    ? [
        ...new Set(
          allPrograms
            .filter((p) => p.region === overviewRegion && p.jurisdiction)
            .map((p) => p.jurisdiction),
        ),
      ].sort((a, b) =>
        (JURISDICTION_LABELS[a] || a).localeCompare(
          JURISDICTION_LABELS[b] || b,
        ),
      )
    : [];
  const activeJurisdiction = censusJurisdictions.includes(
    overviewJurisdiction,
  )
    ? overviewJurisdiction
    : null;

  const censusQuery = overviewQuery.trim().toLowerCase();
  const censusPrograms = allPrograms.filter(
    (p) =>
      (!overviewRegion || p.region === overviewRegion) &&
      (!activeJurisdiction || p.jurisdiction === activeJurisdiction) &&
      (!censusQuery || p.label.toLowerCase().includes(censusQuery)),
  );
  const censusRows = [
    ...[...censusPrograms]
      .filter((p) => p.mismatches === 0)
      .sort((a, b) => a.label.localeCompare(b.label)),
    ...[...censusPrograms]
      .filter((p) => p.mismatches > 0)
      .sort((a, b) => (b.rate ?? -1) - (a.rate ?? -1)),
  ];

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <span className="brand-group">
            <a
              href={AXIOM_APP_URL}
              className="brand-link"
              aria-label="Axiom Foundation"
            >
              <img
                src={`${BASE_PATH}/axiom-foundation.svg`}
                alt="Axiom Foundation"
                className="brand-axiom"
              />
            </a>
            <a href={`${BASE_PATH}/`} className="brand-title">
              <span className="brand-name">Oracles</span>
            </a>
          </span>
          <a href="https://axiom.org/demos" className="all-demos-link">
            All demos
          </a>
        </div>
      </header>
      <main className="v2-main">
        {route.view === "households" ? (
          /* ── Level 3 · the households ── */
          <HouseholdsView
            title={householdTitle}
            reports={householdReports}
            backLabel={
              route.program
                ? "back to the program"
                : routeOracle
                  ? `back to ${engineLabel(routeOracle.id)}`
                  : "back to overview"
            }
            onBack={() =>
              navigate(
                route.program
                  ? { program: route.program }
                  : routeOracle
                    ? { oracle: routeOracle.id }
                    : {},
              )
            }
          />
        ) : route.program ? (
          /* ── Level 2 · one program ── */
          <ProgramPage
            programId={route.program}
            reports={model.verification}
            knownCauses={data.knownCauses || []}
            coverageOverview={data.coverageOverview}
            onBack={() => navigate({})}
            onBrowseHouseholds={() =>
              navigate({ view: "households", program: route.program })
            }
          />
        ) : routeOracle ? (
          /* ── Level 2 · one oracle ── */
          <>
            <div className="pp-head">
              <button
                type="button"
                className="pp-back"
                onClick={() => navigate({})}
              >
                ← all oracles
              </button>
              <h1 className="pp-title">
                {engineLabel(routeOracle.id)}
                <span className="mono pp-where">
                  {" "}
                  · {(ORACLE_IDENTITY[routeOracle.id] || {}).org ||
                    "independent engine"}
                </span>
              </h1>
              <p className="v2-oracle-what">
                {(ORACLE_IDENTITY[routeOracle.id] || {}).what}
                {(ORACLE_IDENTITY[routeOracle.id] || {}).url && (
                  <>
                    {" "}
                    <a
                      className="cite"
                      href={ORACLE_IDENTITY[routeOracle.id].url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {ORACLE_IDENTITY[routeOracle.id].url.replace(
                        /^https?:\/\//,
                        "",
                      )}
                    </a>
                  </>
                )}
              </p>
            </div>
            <OracleRecord
              key={routeOracle.id}
              oracle={routeOracle}
              knownCauses={data.knownCauses || []}
              onOpenProgram={(key) => navigate({ program: key })}
              onBrowseHouseholds={() =>
                navigate({ view: "households", oracle: routeOracle.id })
              }
            />
          </>
        ) : (
          /* ── Level 1 · the overview ── */
          <>
            <section className="v2-hero">
              <h1
                className="v2-thesis"
                title={`${compactCount(totals.checks)} concept-level checks behind these figures${crossChecks > 0 ? ` · ${crossChecks} oracle-vs-oracle arbitration runs` : ""}`}
              >
                Axiom never grades its own work —{" "}
                <em>{compactCount(totals.households)}</em> households checked
                against <em>{oracles.length}</em> independent engines, every
                disagreement tracked in the open.
              </h1>
            </section>

            <section className="v2-section">
              <div className="v2-roster">
                {oracles.map((oracle) => (
                  <OracleCard
                    key={oracle.id}
                    oracle={oracle}
                    selected={false}
                    onSelect={() => navigate({ oracle: oracle.id })}
                  />
                ))}
              </div>
            </section>

            <section className="card-flat v2-dossier">
              <div className="v2-scope" role="group" aria-label="Country">
                {censusRegions.length > 1 &&
                  [null, ...censusRegions].map((r) => (
                    <button
                      key={r ?? "all"}
                      type="button"
                      className={`v2-scope-chip${
                        overviewRegion === r ? " v2-scope-chip-on" : ""
                      }`}
                      aria-pressed={overviewRegion === r}
                      onClick={() => {
                        setOverviewRegion(r);
                        setOverviewJurisdiction(null);
                      }}
                    >
                      {r ? REGION_LABELS[r] || r : "All countries"}
                    </button>
                  ))}
                {censusJurisdictions.length > 1 && (
                  <select
                    className="input-pill v2-scope-select"
                    value={activeJurisdiction ?? ""}
                    onChange={(e) =>
                      setOverviewJurisdiction(e.target.value || null)
                    }
                    aria-label="Jurisdiction"
                  >
                    <option value="">All jurisdictions</option>
                    {censusJurisdictions.map((j) => (
                      <option key={j} value={j}>
                        {JURISDICTION_LABELS[j] || j}
                      </option>
                    ))}
                  </select>
                )}
                <input
                  className="input-pill v2-scope-search"
                  type="search"
                  placeholder="search programs…"
                  value={overviewQuery}
                  onChange={(e) => setOverviewQuery(e.target.value)}
                  aria-label="Search programs"
                />
              </div>
              <div className="v2-dossier-col">
                {censusRows.length === 0 && (
                  <p className="v2-empty">
                    No programs match that search in this scope.
                  </p>
                )}
                <div className="v2-prog-grid">
                        {censusRows.map((p) => (
                    <ProgRow
                      key={p.key}
                      p={p}
                      onOpenProgram={(key) => navigate({ program: key })}
                    />
                  ))}
                </div>
              </div>
            </section>
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
