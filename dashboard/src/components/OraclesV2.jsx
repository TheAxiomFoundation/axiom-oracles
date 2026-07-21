"use client";

import { useEffect, useMemo, useState } from "react";
import { loadOracleData } from "../utils/data";
import { loadSuiteCases } from "../utils/caseData";
import { causeFor, countUnexplained } from "../utils/programs";
import {
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
};

const REGION_LABELS = { us: "US", ca: "CA", uk: "UK", be: "BE" };

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
        <Stat
          value={
            <span style={{ color: rateColor(oracle.rate) }}>
              {formatAgreementRate(oracle.rate, oracle.mismatches)}
            </span>
          }
          label="agreement"
        />
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

function caseValue(v) {
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") return `$${Math.round(v).toLocaleString()}`;
  return v == null ? "—" : String(v);
}

function conceptShort(conceptId, labels) {
  const known = labels.get(conceptId);
  if (known) return known;
  const tail = String(conceptId).split("#").pop().replaceAll(/[_-]/g, " ");
  // Short tails are acronyms (eitc, ctc); longer ones read as phrases.
  return tail.length <= 4
    ? tail.toUpperCase()
    : tail.charAt(0).toUpperCase() + tail.slice(1);
}

/**
 * The bottom of the drill: individual households, their inputs, and — when
 * the engines disagree — both engines' answers side by side. Reads the
 * per-suite case artifacts (matches carry inputs only; outputs are stored
 * for disagreements, where they are the evidence).
 */
function HouseholdBrowser({ oracle }) {
  const suites = useMemo(
    () => [...new Set(oracle.reports.map((r) => r.suite))],
    [oracle],
  );
  const conceptLabels = useMemo(() => {
    const labels = new Map();
    for (const report of oracle.reports) {
      for (const agg of report.aggregates || []) {
        if (agg.description) labels.set(agg.concept, agg.description);
      }
    }
    return labels;
  }, [oracle]);
  const [suite, setSuite] = useState(suites[0]);
  const [cases, setCases] = useState(undefined); // undefined = loading
  const [onlyDisagreements, setOnlyDisagreements] = useState(false);
  const [limit, setLimit] = useState(12);

  const activeSuite = suites.includes(suite) ? suite : suites[0];

  useEffect(() => {
    let live = true;
    setCases(undefined);
    setLimit(12);
    loadSuiteCases(activeSuite).then((d) => {
      if (live) setCases(d);
    });
    return () => {
      live = false;
    };
  }, [activeSuite]);
  const rows = useMemo(() => {
    if (!cases?.cases) return [];
    let out = cases.cases;
    if (onlyDisagreements) out = out.filter((c) => (c.m || []).length > 0);
    // Worst disagreement first; agreeing households after.
    return [...out].sort((a, b) => {
      const worst = (c) =>
        Math.max(0, ...(c.m || []).map((m) => Math.abs(m.d || 0)));
      return worst(b) - worst(a);
    });
  }, [cases, onlyDisagreements]);

  const totalCompared = cases?.index?.total_cases ?? cases?.cases?.length ?? 0;
  const inputsMissing = Boolean(
    cases?.cases?.length &&
      cases.cases
        .slice(0, 50)
        .every((c) => !(c.h?.n || (c.h?.a || []).length)),
  );

  return (
    <div className="v2-hh">
      <div className="v2-hh-head">
        <span className="mono v2-dossier-colhead">Households</span>
      </div>
      <div className="v2-hh-controls">
        <select
          className="input-pill v2-hh-select"
          value={activeSuite}
          onChange={(e) => setSuite(e.target.value)}
          aria-label="Verification suite"
        >
          {suites.map((s) => (
            <option key={s} value={s}>
              {suiteLabel(s)}
            </option>
          ))}
        </select>
        <button
          type="button"
          className={`v2-toggle${onlyDisagreements ? " v2-toggle-on" : ""}`}
          aria-pressed={onlyDisagreements}
          onClick={() => setOnlyDisagreements(!onlyDisagreements)}
        >
          <span className="v2-toggle-mark" aria-hidden="true" />
          only disagreements
        </button>
      </div>
      {cases?.cases &&
        (cases.index?.partial === "mismatch-only" || inputsMissing) && (
          <p className="v2-hh-note">
            {cases.index?.partial === "mismatch-only" &&
              `This artifact stores only the disagreeing households — the other ${(
                totalCompared - cases.cases.length
              ).toLocaleString()} matched on every compared value. `}
            {inputsMissing &&
              "Household inputs are not yet captured by this suite's harness."}
          </p>
        )}
      {cases === undefined ? (
        <p className="v2-empty">Loading household cases…</p>
      ) : cases === null ? (
        <p className="v2-empty">
          No per-household case artifacts for this suite yet.
        </p>
      ) : rows.length === 0 ? (
        <p className="v2-empty">
          {onlyDisagreements
            ? "No disagreeing households in this suite — every compared value matches."
            : "No households in this suite."}
        </p>
      ) : (
        <>
          {rows.slice(0, limit).map((c) => (
            <div key={c.id} className="v2-hh-row">
              <div className="v2-hh-who">
                <span className="mono v2-hh-id">{c.id}</span>
                {(c.h?.n || (c.h?.a || []).length > 0) && (
                  <span className="v2-hh-inputs">
                    {c.h?.n || (c.h?.a || []).length} ppl
                    {(c.h?.a || []).length > 0 &&
                      ` · ages ${(c.h.a || []).join(", ")}`}
                    {c.h?.e != null &&
                      ` · $${Number(c.h.e).toLocaleString()} earned`}
                  </span>
                )}
              </div>
              <div className="v2-hh-outcomes">
                {(c.m || []).length === 0 ? (
                  <span className="v2-hh-agree">
                    engines agree on every compared value
                  </span>
                ) : (
                  (c.m || []).map((m, i) => (
                    <div key={i} className="v2-hh-outcome">
                      <span className="v2-hh-concept">
                        {conceptShort(m.c, conceptLabels)}
                      </span>
                      <span className="mono v2-hh-values">
                        <span className="v2-hh-eng">Axiom</span>{" "}
                        {caseValue(m.l)}
                        <span className="v2-hh-eng">
                          {" "}
                          {engineLabel(oracle.id)}
                        </span>{" "}
                        {caseValue(m.x)}
                        {typeof m.d === "number" && m.d !== 0 && (
                          <span className="v2-hh-diff">
                            {" "}
                            Δ ${Math.abs(Math.round(m.d)).toLocaleString()}
                          </span>
                        )}
                      </span>
                      {m.e ? (
                        <span className="v2-action v2-action-doc">
                          explained
                        </span>
                      ) : (
                        <span className="v2-action v2-action-open">
                          unexplained
                        </span>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          ))}
          {rows.length > limit && (
            <button
              type="button"
              className="mono v2-hh-more"
              onClick={() => setLimit(limit + 24)}
            >
              show {Math.min(24, rows.length - limit)} more of{" "}
              {rows.length.toLocaleString()}
            </button>
          )}
        </>
      )}
    </div>
  );
}

const REGION_ORDER = ["us", "ca", "uk", "be"];

function OracleRecord({ oracle, onOpenProgram }) {
  // Multi-country oracles get a country scope; single-country ones don't
  // need the chrome. Scoping filters programs, classes, and households.
  const regions = REGION_ORDER.filter((r) => oracle.regions.has(r));
  const [region, setRegion] = useState(null);
  const scoped = useMemo(() => {
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
    for (const report of scoped.reports) {
      const meta = suiteMeta(report.suite);
      const key = `${meta.family}__${meta.jurisdiction}`;
      if (!byProgram.has(key)) {
        byProgram.set(key, {
          key,
          label: meta.label,
          region: meta.region,
          total: 0,
          mismatches: 0,
          households: 0,
        });
      }
      const entry = byProgram.get(key);
      const m = reportMetric(report);
      entry.total += m.total;
      entry.mismatches += m.mismatches;
      entry.households += reportHouseholds(report);
    }
    return [...byProgram.values()]
      .map((p) => ({
        ...p,
        rate: p.total > 0 ? ((p.total - p.mismatches) / p.total) * 100 : null,
      }))
      .sort((a, b) => (b.rate ?? -1) - (a.rate ?? -1));
  }, [scoped]);

  return (
    <section className="card-flat v2-dossier">
      {regions.length > 1 && (
        <div className="v2-scope" role="group" aria-label="Country">
          {[null, ...regions].map((r) => (
            <button
              key={r ?? "all"}
              type="button"
              className={`v2-scope-chip${region === r ? " v2-scope-chip-on" : ""}`}
              aria-pressed={region === r}
              onClick={() => setRegion(r)}
            >
              {r ? REGION_LABELS[r] || r : "All countries"}
            </button>
          ))}
        </div>
      )}
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
              <span
                className="mono v2-prog-checks"
                title={`${p.households.toLocaleString()} households · ${p.total.toLocaleString()} checks`}
              >
                {p.households.toLocaleString()}
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
          <div className="mono v2-dossier-colhead">Discrepancy classes</div>
          {scoped.classes.length === 0 ? (
            <p className="v2-empty">
              No measured disagreements with this oracle.
            </p>
          ) : (
            <>
              {scoped.classes.slice(0, 8).map((row, i) => (
                <ClassRow
                  key={`${row.suite}-${row.conceptLabel}-${row.kind}-${i}`}
                  row={row}
                  showOracle={false}
                />
              ))}
              {scoped.classes.length > 8 && (
                <details className="v2-ledger-more">
                  <summary>
                    show all {scoped.classes.length} classes
                  </summary>
                  {scoped.classes.slice(8).map((row, i) => (
                    <ClassRow
                      key={`rest-${row.suite}-${row.conceptLabel}-${row.kind}-${i}`}
                      row={row}
                      showOracle={false}
                    />
                  ))}
                </details>
              )}
            </>
          )}
        </div>
      </div>
      {/* Keyed so the suite selection resets with the record and scope. */}
      <HouseholdBrowser key={`${oracle.id}-${region ?? "all"}`} oracle={scoped} />
    </section>
  );
}

export default function OraclesV2() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [programId, setProgramId] = useState(null);

  useEffect(() => {
    loadOracleData("")
      .then(setData)
      .catch((e) => setError(e.message));
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

  const { oracles, totals, crossChecks } = model;
  const selectedOracle = oracles.find((o) => o.id === selected);

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
            <span className="brand-product" aria-label="Oracles">
              OR
              <span className="brand-flip" aria-hidden="true">
                A
              </span>
              CLES
            </span>
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
          <h1 className="v2-thesis">
            Axiom never grades its own work —{" "}
            <em>{compactCount(totals.households)}</em> households checked
            against <em>{oracles.length}</em> independent engines,{" "}
            <em style={{ color: rateColor(totals.rate) }}>
              {formatAgreementRate(totals.rate, totals.mismatches)}
            </em>{" "}
            agreement.
          </h1>
          <p
            className="v2-hero-sub"
            title={`${compactCount(totals.checks)} concept-level checks behind the agreement rate${crossChecks > 0 ? ` · ${crossChecks} oracle-vs-oracle arbitration runs` : ""}`}
          >
            Every disagreement is triaged in the open — dispositioned, filed
            upstream, or kept visibly open until someone acts.
          </p>
        </section>

        {/* 2 · The roster */}
        <section className="v2-section">
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
            <OracleRecord
              key={selectedOracle.id}
              oracle={selectedOracle}
              onOpenProgram={openProgram}
            />
          )}
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
