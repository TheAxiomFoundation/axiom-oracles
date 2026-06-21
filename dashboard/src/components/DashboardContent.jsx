"use client";

import { useState, useEffect, useMemo } from "react";
import { loadOracleData, buildNWayData } from "../utils/data";
import MetricsRow from "./MetricsRow";
import ProgramBreakdown from "./ProgramBreakdown";
import AgreementMatrix from "./AgreementMatrix";
import AlignmentReport from "./AlignmentReport";
import OverviewHero from "./OverviewHero";
import CoverageOverview from "./CoverageOverview";

const SUITE_DISPLAY_ORDER = {
  "fiit-ecps": 10,
  "ca-snap-ecps": 20,
  "ny-snap-ecps": 30,
  "ma-snap-ecps": 40,
  "al-snap-ecps": 50,
  "tn-snap-ecps": 60,
  "co-snap-ecps": 70,
  "sc-snap-ecps": 80,
  "nc-snap-ecps": 90,
  "co-state-income-tax-ecps": 100,
  "co-health-thresholds": 110,
  "co-tanf-coverage": 120,
  "uk-universal-credit-efrs": 130,
  "uk-tax-benefits-efrs": 140,
  "nyc-synthetic": 1000,
};

function orderedReports(reports) {
  return [...reports].sort((a, b) => {
    const aOrder = SUITE_DISPLAY_ORDER[a.suite] ?? 500;
    const bOrder = SUITE_DISPLAY_ORDER[b.suite] ?? 500;
    if (aOrder !== bOrder) return aOrder - bOrder;
    return (a.suite || "").localeCompare(b.suite || "");
  });
}

function reportRegion(report) {
  const suite = String(report?.suite || "");
  if (suite.startsWith("uk-")) return "uk";
  return "us";
}

function programRegion(program) {
  const id = String(program?.id || "");
  if (id.startsWith("uk:")) return "uk";
  if (id.startsWith("us:")) return "us";
  const coverage = program?.coverage || [];
  if (coverage.some((entry) => entry?.country === "UK")) return "uk";
  if (coverage.some((entry) => entry?.country === "US")) return "us";
  return "us";
}

function filterReportsByRegion(reports, region) {
  return reports.filter((report) => reportRegion(report) === region);
}

function filterProgramsByRegion(programs, region) {
  return programs.filter((program) => programRegion(program) === region);
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
    const reports = orderedReports(filterReportsByRegion(data.reports, jurisdiction));
    const programs = filterProgramsByRegion(data.programs, jurisdiction);
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

  const hasComparisonData = viewData.summary.totalCases > 0;

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
        <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
          <OverviewHero
            reports={viewData.reports.filter(
              (r) => (r.aggregates || []).length > 0,
            )}
            programCount={viewData.programs.length}
          />

          <CoverageOverview
            reports={viewData.reports.filter(
              (r) => (r.aggregates || []).length > 0,
            )}
            coverageOverview={data.coverageOverview}
            jurisdictionFilter={jurisdiction}
          />

          {hasComparisonData && (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 16,
              }}
            >
              <div className="section-eyebrow">By program</div>
              {viewData.reports
                .filter((r) => (r.aggregates || []).length > 0)
                .map((report, i) => (
                  <AlignmentReport
                    key={`${report.suite || "report"}-${i}`}
                    report={report}
                    knownCauses={data.knownCauses || []}
                  />
                ))}
            </div>
          )}

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
              All encoded programs (with and without live comparison data) ·
              advanced view
            </summary>
            <div style={{ marginTop: 12 }}>
              {hasComparisonData && (
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
