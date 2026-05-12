"use client";

import { useState, useEffect } from "react";
import { loadOracleData } from "../utils/data";
import MetricsRow from "./MetricsRow";
import ProgramBreakdown from "./ProgramBreakdown";
import AgreementMatrix from "./AgreementMatrix";
import CaseInspector from "./CaseInspector";

function TopBar() {
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
      </div>
    </header>
  );
}

function countLivePrograms(data) {
  const conceptsWithData = new Set();
  for (const report of data.reports) {
    for (const agg of report.aggregates || []) {
      if (agg.comparison_count > 0) conceptsWithData.add(agg.concept);
    }
  }
  return data.programs.filter((p) => conceptsWithData.has(p.id)).length;
}

function PageIntro({ data }) {
  return (
    <div className="page-intro" style={{ marginBottom: 36 }}>
      <h1>
        Programs encoded in the <em>Axiom corpus</em>, validated against other engines.
      </h1>
      <p>
        Each program below is a statute or regulation encoded as an Axiom
        RuleSpec module. As coverage grows, every encoding gets cross-checked
        against the engines that already compute it.
      </p>
    </div>
  );
}

export default function DashboardContent() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadOracleData("")
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <>
        <TopBar />
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
        <TopBar />
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

  const hasComparisonData = data.summary.totalCases > 0;

  return (
    <>
      <TopBar />
      <main
        style={{
          maxWidth: 1180,
          margin: "0 auto",
          padding: "56px 20px 80px",
        }}
      >
        <PageIntro data={data} />

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <MetricsRow
            summary={data.summary}
            programCount={data.programs.length}
            liveProgramCount={countLivePrograms(data)}
          />

          {hasComparisonData && (
            <AgreementMatrix
              oracles={data.oracles}
              matrix={data.matrix}
              overallMatrix={data.overallMatrix}
              concepts={data.concepts}
            />
          )}

          <ProgramBreakdown
            programs={data.programs}
            reports={data.reports}
            oracles={data.oracles}
          />

          {hasComparisonData && (
            <CaseInspector
              allCases={data.allCases}
              oracles={data.oracles}
            />
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
