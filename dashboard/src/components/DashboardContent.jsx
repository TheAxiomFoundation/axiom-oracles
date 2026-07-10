"use client";

import { useState, useEffect, useMemo } from "react";
import { loadOracleData, buildNWayData } from "../utils/data";
import { suiteRegion } from "../utils/suites";
import { engineLabel } from "../utils/format";
import OverviewHero from "./OverviewHero";
import ConformanceCard from "./ConformanceCard";
import BelgiumEuromodCoverage from "./BelgiumEuromodCoverage";
import RuleVerification from "./RuleVerification";
import GapLedger from "./GapLedger";
import ProgramStatusTable from "./ProgramStatusTable";
import ProgramPage from "./ProgramPage";
import FreshnessRegister from "./FreshnessRegister";
import AgreementMatrix from "./AgreementMatrix";
import ProgramBreakdown from "./ProgramBreakdown";

function programRegion(program) {
  const id = String(program?.id || "");
  if (id.startsWith("ca:")) return "ca";
  if (id.startsWith("be:")) return "be";
  if (id.startsWith("uk:")) return "uk";
  if (id.startsWith("us:")) return "us";
  const coverage = program?.coverage || [];
  if (coverage.some((entry) => entry?.country === "CA")) return "ca";
  if (coverage.some((entry) => entry?.country === "BE")) return "be";
  if (coverage.some((entry) => entry?.country === "UK")) return "uk";
  if (coverage.some((entry) => entry?.country === "US")) return "us";
  return "us";
}

const COUNTRIES = [
  { id: "us", label: "US" },
  { id: "ca", label: "CA" },
  { id: "uk", label: "UK" },
  { id: "be", label: "BE" },
];

// The Axiom app owns the "what is encoded" story; Oracles only measures
// how accurate those encodings are, and links out for the rest.
const AXIOM_APP_URL = "https://axiom-foundation.org";

function TopBar({ jurisdiction = "us", onJurisdictionChange = () => {} }) {
  return (
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
        <div className="country-toggle" role="tablist" aria-label="Country">
          {COUNTRIES.map((country) => {
            const active = jurisdiction === country.id;
            return (
              <button
                type="button"
                role="tab"
                aria-selected={active}
                className={`country-toggle-btn ${
                  active ? "country-toggle-btn-active" : ""
                }`}
                onClick={() => onJurisdictionChange(country.id)}
                key={country.id}
              >
                {country.label}
              </button>
            );
          })}
        </div>
      </div>
    </header>
  );
}

/**
 * The oracles a report is checked against: the non-axiom engine of an
 * axiom pair, or both engines of an oracle-vs-oracle cross-check.
 */
function reportOracles(report) {
  const engines = [report?.engines?.left, report?.engines?.right].filter(
    (e) => e && e !== "axiom",
  );
  return engines;
}

function OracleFilter({ available, selected, onToggle }) {
  if (available.length <= 1) return null;
  return (
    <div className="oracle-filter" role="group" aria-label="Oracles compared">
      <span className="oracle-filter-label mono">oracles</span>
      {available.map(({ oracle, runs }) => {
        const on = selected.has(oracle);
        const lastOn = on && selected.size === 1;
        return (
          <button
            key={oracle}
            type="button"
            aria-pressed={on}
            disabled={lastOn}
            className={`oracle-chip${on ? " oracle-chip-on" : ""}`}
            title={
              lastOn
                ? "At least one oracle stays selected"
                : `${on ? "Hide" : "Show"} runs against ${engineLabel(oracle)}`
            }
            onClick={() => onToggle(oracle)}
          >
            <span className="oracle-chip-mark" aria-hidden="true" />
            {engineLabel(oracle)}
            <span className="mono oracle-chip-count">{runs}</span>
          </button>
        );
      })}
    </div>
  );
}

export default function DashboardContent() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [jurisdiction, setJurisdiction] = useState("us");
  const [programId, setProgramId] = useState(null);
  const [hiddenOracles, setHiddenOracles] = useState(() => new Set());

  // Deep-link jurisdiction (?jurisdiction=ca|uk|be|us, or #uk) and an open
  // program (?program=…). Read once on mount.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const fromUrl = (
      params.get("jurisdiction") || window.location.hash.replace("#", "")
    ).toLowerCase();
    if (COUNTRIES.some((c) => c.id === fromUrl)) {
      setJurisdiction(fromUrl);
    }
    const programFromUrl = params.get("program");
    if (programFromUrl) setProgramId(programFromUrl);
    // The retired two-tab system deep-linked ?view=…; strip the dead
    // param so bookmarked URLs don't carry it forever.
    if (params.has("view")) {
      const url = new URL(window.location.href);
      url.searchParams.delete("view");
      window.history.replaceState(null, "", url);
    }
  }, []);

  const syncUrl = (key, value) => {
    const url = new URL(window.location.href);
    url.searchParams.set(key, value);
    window.history.replaceState(null, "", url);
  };
  const changeJurisdiction = (next) => {
    setJurisdiction(next);
    syncUrl("jurisdiction", next);
  };
  const openProgram = (id) => {
    setProgramId(id);
    syncUrl("program", id);
  };
  const closeProgram = () => {
    setProgramId(null);
    const url = new URL(window.location.href);
    url.searchParams.delete("program");
    window.history.replaceState(null, "", url);
  };

  useEffect(() => {
    loadOracleData("")
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  // Region slice, then the oracle filter on top of it.
  const regionReports = useMemo(() => {
    if (!data) return [];
    return data.reports.filter((r) => suiteRegion(r.suite) === jurisdiction);
  }, [data, jurisdiction]);

  const availableOracles = useMemo(() => {
    const counts = new Map();
    for (const r of regionReports) {
      for (const o of reportOracles(r)) {
        counts.set(o, (counts.get(o) || 0) + 1);
      }
    }
    return [...counts.entries()]
      .map(([oracle, runs]) => ({ oracle, runs }))
      .sort((a, b) => b.runs - a.runs);
  }, [regionReports]);

  const selectedOracles = useMemo(() => {
    const all = new Set(availableOracles.map((o) => o.oracle));
    for (const hidden of hiddenOracles) all.delete(hidden);
    // Never allow an empty selection.
    if (all.size === 0 && availableOracles.length > 0) {
      all.add(availableOracles[0].oracle);
    }
    return all;
  }, [availableOracles, hiddenOracles]);

  const toggleOracle = (oracle) => {
    setHiddenOracles((prev) => {
      const next = new Set(prev);
      if (next.has(oracle)) next.delete(oracle);
      else next.add(oracle);
      return next;
    });
  };

  const filteredReports = useMemo(
    () =>
      regionReports.filter((r) =>
        reportOracles(r).every((o) => selectedOracles.has(o)),
      ),
    [regionReports, selectedOracles],
  );

  const viewData = useMemo(() => {
    if (!data) return null;
    const programs = data.programs.filter(
      (p) => programRegion(p) === jurisdiction,
    );
    return {
      ...buildNWayData(filteredReports),
      reports: filteredReports,
      programs,
    };
  }, [data, jurisdiction, filteredReports]);

  if (loading || error || !data) {
    return (
      <>
        <TopBar
          jurisdiction={jurisdiction}
          onJurisdictionChange={changeJurisdiction}
        />
        <main style={{ maxWidth: 1180, margin: "0 auto", padding: "56px 20px" }}>
          <div className="page-intro">
            {loading ? (
              <p className="mono" style={{ fontSize: 13 }}>
                Loading oracle data…
              </p>
            ) : (
              <>
                <h1>No reports found.</h1>
                <p>
                  Generate one with the{" "}
                  <code className="mono">axiom-oracles</code> CLI.
                </p>
              </>
            )}
          </div>
        </main>
      </>
    );
  }

  const withData = filteredReports.filter(
    (r) =>
      (r.aggregates || []).length > 0 || (r.summary?.alarms || []).length > 0,
  );
  const isBelgium = jurisdiction === "be";

  const mainView = (
    <>
      <OracleFilter
        available={availableOracles}
        selected={selectedOracles}
        onToggle={toggleOracle}
      />

      {isBelgium ? (
        <BelgiumEuromodCoverage
          coverage={data.euromodCoverage}
          issues={data.euromodIssues}
        />
      ) : (
        <OverviewHero reports={withData} />
      )}

      <ConformanceCard region={jurisdiction} />
      {jurisdiction === "uk" && <ConformanceCard region="uk-pe" />}

      <ProgramStatusTable reports={withData} onOpen={openProgram} />

      <GapLedger
        reports={withData}
        knownCauses={data.knownCauses || []}
        coverageOverview={data.coverageOverview}
        region={jurisdiction}
      />

      {jurisdiction === "us" && <RuleVerification region={jurisdiction} />}

      <FreshnessRegister freshness={data.freshness} region={jurisdiction} />

      <details className="advanced-panel">
        <summary>
          Advanced view · oracle agreement matrix and program breakdown
        </summary>
        <div className="advanced-panel-body">
          {viewData.summary.totalCases > 0 && (
            <AgreementMatrix
              oracles={viewData.oracles}
              matrix={viewData.matrix}
              overallMatrix={viewData.overallMatrix}
              concepts={viewData.concepts}
            />
          )}
          <ProgramBreakdown
            programs={viewData.programs}
            reports={viewData.reports}
            oracles={viewData.oracles}
          />
        </div>
      </details>
    </>
  );

  return (
    <>
      <TopBar
        jurisdiction={jurisdiction}
        onJurisdictionChange={changeJurisdiction}
      />
      <main
        className="page-main"
        style={{
          maxWidth: 1180,
          margin: "0 auto",
          padding: "40px 20px 80px",
        }}
      >
        {!programId && (
          <p className="page-caption">
            Oracles measures how accurate the encodings are. For what is
            encoded, see the{" "}
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
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
          {programId ? (
            <ProgramPage
              programId={programId}
              reports={withData}
              knownCauses={data.knownCauses || []}
              coverageOverview={data.coverageOverview}
              onBack={closeProgram}
            />
          ) : (
            mainView
          )}
        </div>

        <footer
          style={{
            marginTop: 48,
            paddingTop: 24,
            borderTop: "1px solid var(--hairline)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            fontSize: 12,
            color: "var(--ink-mute)",
          }}
        >
          <span className="mono">
            Axiom Foundation · Oracles · {new Date().getFullYear()}
          </span>
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
