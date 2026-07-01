"use client";

import { useState, useEffect, useMemo } from "react";
import { loadOracleData, buildNWayData } from "../utils/data";
import { suiteRegion } from "../utils/suites";
import OverviewHero from "./OverviewHero";
import CoverageRegister from "./CoverageRegister";
import GapLedger from "./GapLedger";
import ProgramRuns from "./ProgramRuns";
import AgreementMatrix from "./AgreementMatrix";
import ProgramBreakdown from "./ProgramBreakdown";

function programRegion(program) {
  const id = String(program?.id || "");
  if (id.startsWith("uk:")) return "uk";
  if (id.startsWith("us:")) return "us";
  const coverage = program?.coverage || [];
  if (coverage.some((entry) => entry?.country === "UK")) return "uk";
  if (coverage.some((entry) => entry?.country === "US")) return "us";
  return "us";
}

function TopBar({ jurisdiction = "us", onJurisdictionChange = () => {} }) {
  const isUS = jurisdiction === "us";
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <span className="brand-group">
          <a
            href="https://axiom-foundation.org"
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
          <button
            type="button"
            role="tab"
            aria-selected={isUS}
            className={`country-toggle-btn ${
              isUS ? "country-toggle-btn-active" : ""
            }`}
            onClick={() => onJurisdictionChange("us")}
          >
            US
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={!isUS}
            className={`country-toggle-btn ${
              !isUS ? "country-toggle-btn-active" : ""
            }`}
            onClick={() => onJurisdictionChange("uk")}
          >
            UK
          </button>
        </div>
      </div>
    </header>
  );
}

export default function DashboardContent() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [jurisdiction, setJurisdiction] = useState("us");

  useEffect(() => {
    loadOracleData("")
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const viewData = useMemo(() => {
    if (!data) return null;
    const reports = data.reports.filter(
      (r) => suiteRegion(r.suite) === jurisdiction,
    );
    const programs = data.programs.filter(
      (p) => programRegion(p) === jurisdiction,
    );
    return { ...buildNWayData(reports), reports, programs };
  }, [data, jurisdiction]);

  if (loading) {
    return (
      <>
        <TopBar
          jurisdiction={jurisdiction}
          onJurisdictionChange={setJurisdiction}
        />
        <main style={{ maxWidth: 1180, margin: "0 auto", padding: "56px 20px" }}>
          <div className="page-intro">
            <p className="mono" style={{ fontSize: 13 }}>
              Loading oracle data…
            </p>
          </div>
        </main>
      </>
    );
  }

  if (error || !data) {
    return (
      <>
        <TopBar
          jurisdiction={jurisdiction}
          onJurisdictionChange={setJurisdiction}
        />
        <main style={{ maxWidth: 1180, margin: "0 auto", padding: "56px 20px" }}>
          <div className="page-intro">
            <h1>No reports found.</h1>
            <p>
              Generate one with the <code className="mono">axiom-oracles</code> CLI.
            </p>
          </div>
        </main>
      </>
    );
  }

  const withData = viewData.reports.filter(
    (r) =>
      (r.aggregates || []).length > 0 || (r.summary?.alarms || []).length > 0,
  );

  return (
    <>
      <TopBar
        jurisdiction={jurisdiction}
        onJurisdictionChange={setJurisdiction}
      />
      <main
        className="page-main"
        style={{
          maxWidth: 1180,
          margin: "0 auto",
          padding: "56px 20px 80px",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 36 }}>
          <OverviewHero reports={withData} />

          <CoverageRegister
            reports={withData}
            coverageOverview={data.coverageOverview}
            region={jurisdiction}
          />

          <ProgramRuns
            reports={withData}
            knownCauses={data.knownCauses || []}
            coverageOverview={data.coverageOverview}
          />

          <GapLedger
            reports={withData}
            knownCauses={data.knownCauses || []}
            coverageOverview={data.coverageOverview}
            region={jurisdiction}
          />

          <details
            style={{
              background: "var(--paper-elevated)",
              border: "1px solid var(--hairline)",
              borderRadius: 12,
              padding: "12px 16px",
            }}
          >
            <summary
              style={{
                cursor: "pointer",
                fontSize: 13,
                color: "var(--ink-mute)",
              }}
            >
              Advanced view · oracle agreement matrix and the encoded-rule
              inventory (statute references, corpus files)
            </summary>
            <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 16 }}>
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
