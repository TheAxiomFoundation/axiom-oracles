"use client";

const STATUS_LABELS = {
  live_oracle_verified_for_regular_worker_statutory_slice: "Live verified",
  live_oracle_verified_gross_regular_worker_slice: "Live verified",
  live_oracle_verified_worker_pilot_not_full_household_parity:
    "Worker pilot verified",
  live_oracle_compared_with_known_2025_timing_residual:
    "Live compared; known residual",
  prepared_worker_pilot_not_full_household_parity: "Pilot ready",
  not_mapped: "Not mapped",
  oracle_anchor_not_target_output: "Anchor",
};

const STATUS_CLASS = {
  live_oracle_verified_for_regular_worker_statutory_slice: "good",
  live_oracle_verified_gross_regular_worker_slice: "good",
  live_oracle_verified_worker_pilot_not_full_household_parity: "good",
  live_oracle_compared_with_known_2025_timing_residual: "warn",
  prepared_worker_pilot_not_full_household_parity: "warn",
  not_mapped: "gap",
  oracle_anchor_not_target_output: "neutral",
};

function statusLabel(status) {
  return (
    STATUS_LABELS[status] ||
    String(status || "Unknown").replaceAll("_", " ")
  );
}

function statusClass(status) {
  return STATUS_CLASS[status] || "neutral";
}

function compactNumber(value) {
  if (value == null) return "—";
  return Number(value).toLocaleString();
}

function plural(value, singular, pluralForm = `${singular}s`) {
  return Number(value) === 1 ? singular : pluralForm;
}

function Stat({ value, label }) {
  return (
    <div className="be-stat">
      <span className="mono be-stat-value">{value}</span>
      <span className="mono be-stat-label">{label}</span>
    </div>
  );
}

function CoverageBadge({ status }) {
  return (
    <span className={`be-status be-status-${statusClass(status)}`}>
      {statusLabel(status)}
    </span>
  );
}

function OutputTargets({ outputs }) {
  return (
    <div className="be-output-list">
      {outputs.map((output) => (
        <div className="be-output-row" key={output.euromod_variable}>
          <div className="be-output-main">
            <span className="mono be-output-code">{output.euromod_variable}</span>
            <span className="be-output-meaning">{output.meaning}</span>
          </div>
          <CoverageBadge status={output.status} />
          <div className="be-output-evidence">
            {output.evidence || output.remaining_gap}
          </div>
        </div>
      ))}
    </div>
  );
}

function DomainCoverage({ domains }) {
  return (
    <div className="be-domain-grid">
      {domains.map((domain) => (
        <div className="be-domain-row" key={domain.domain}>
          <div>
            <div className="be-domain-name">
              {domain.domain.replaceAll("_", " ")}
            </div>
            <div className="mono be-domain-meta">
              {domain.euromod_policies.length} EUROMOD policies ·{" "}
              {domain.rulespec_modules.length} RuleSpec modules
            </div>
          </div>
          <span className="be-domain-status">
            {domain.status.replaceAll("_", " ")}
          </span>
        </div>
      ))}
    </div>
  );
}

function PolicyDenominator({ policies }) {
  return (
    <details className="be-policy-details">
      <summary>BE_2025 policy denominator</summary>
      <div className="table-scroll">
        <table className="be-policy-table">
          <thead>
            <tr>
              <th>Policy</th>
              <th>Switch</th>
              <th>Functions</th>
              <th>Parameters</th>
              <th>Label</th>
            </tr>
          </thead>
          <tbody>
            {policies.map((policy) => (
              <tr key={policy.code}>
                <td className="mono">{policy.code}</td>
                <td className="mono">{policy.xml_default_switch}</td>
                <td>{compactNumber(policy.function_count)}</td>
                <td>{compactNumber(policy.parameter_count)}</td>
                <td>{policy.label}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function EuromodIssueLedger({ issues }) {
  const entries = (issues?.entries || []).filter(
    (issue) => issue.jurisdiction === "BE",
  );
  if (entries.length === 0) return null;

  return (
    <section className="card-flat">
      <div className="section-head">
        <div>
          <div className="section-eyebrow">EUROMOD issue ledger</div>
          <div className="section-title">
            External engine or model issues affecting household-level oracles
          </div>
        </div>
        <div className="mono be-config">{issues.updated_at}</div>
      </div>
      <div className="be-issue-list">
        {entries.map((issue) => (
          <div className="be-issue-row" key={issue.id}>
            <div>
              <div className="be-issue-title">
                <span className="mono">{issue.id}</span>
                <CoverageBadge status="oracle_anchor_not_target_output" />
              </div>
              <p>{issue.summary}</p>
              <p>{issue.workaround?.description}</p>
            </div>
            {issue.upstream_url ? (
              <a
                className="cite"
                href={issue.upstream_url}
                target="_blank"
                rel="noreferrer"
              >
                upstream issue
              </a>
            ) : (
              <span className="cite">local ledger</span>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

export default function BelgiumEuromodCoverage({ coverage, issues }) {
  if (!coverage) {
    return (
      <section className="hero">
        <div className="section-eyebrow">Belgium EUROMOD coverage</div>
        <h1 className="hero-thesis">No Belgium EUROMOD inventory found.</h1>
      </section>
    );
  }

  const denominator = coverage.denominator || {};
  const summary = coverage.coverage_summary || {};
  const outputTargets = coverage.oracle_output_coverage || [];
  const mappedTargets =
    summary.current_oracle_output_targets ||
    outputTargets.filter((target) => target.rulespec_output).length;
  const verifiedTargets = summary.live_verified_oracle_output_targets || 0;
  const residualTargets = outputTargets.filter((target) =>
    String(target.status || "").includes("known_2025_timing_residual"),
  ).length;
  const source = coverage.source_artifacts?.find(
    (artifact) => artifact.kind === "euromod_training_input_schema",
  );

  return (
    <div className="be-page">
      <section className="hero">
        <div className="section-eyebrow">Belgium EUROMOD coverage</div>
        <h1 className="hero-thesis">
          Axiom maps <em>{compactNumber(mappedTargets)}</em> EUROMOD BE{" "}
          {plural(mappedTargets, "output")} across the{" "}
          <em>{coverage.oracle_configuration?.system}</em> model:{" "}
          <em>{compactNumber(verifiedTargets)}</em>{" "}
          {plural(verifiedTargets, "target")} verified and{" "}
          <em>{compactNumber(residualTargets)}</em>{" "}
          {plural(residualTargets, "target")} live-compared with a known
          EUROMOD residual.
        </h1>
        <p className="hero-sub">{coverage.coverage_claim}</p>
        <div className="hero-stats">
          <Stat
            value={compactNumber(denominator.policy_count)}
            label="BE_2025 policies"
          />
          <Stat
            value={compactNumber(denominator.function_count)}
            label="functions"
          />
          <Stat
            value={compactNumber(denominator.parameter_count)}
            label="parameters"
          />
          <Stat
            value={compactNumber(source?.header_columns)}
            label="input columns"
          />
        </div>
      </section>

      <section className="card-flat">
        <div className="section-head">
          <div>
            <div className="section-eyebrow">Oracle targets</div>
            <div className="section-title">
              EUROMOD variables mapped to Axiom outputs
            </div>
          </div>
          <div className="mono be-config">
            {coverage.oracle_configuration?.dataset} ·{" "}
            {coverage.oracle_configuration?.template_dataset}
          </div>
        </div>
        <OutputTargets outputs={coverage.oracle_output_coverage || []} />
      </section>

      <section className="card-flat">
        <div className="section-head">
          <div>
            <div className="section-eyebrow">Domain map</div>
            <div className="section-title">
              RuleSpec overlap with the EUROMOD Belgium model
            </div>
          </div>
        </div>
        <DomainCoverage domains={coverage.domain_coverage || []} />
      </section>

      <EuromodIssueLedger issues={issues} />

      <section className="card-flat">
        <div className="section-head">
          <div>
            <div className="section-eyebrow">Denominator</div>
            <div className="section-title">
              Parsed EUROMOD BE_2025 policy surface
            </div>
          </div>
          <div className="mono be-config">
            {coverage.source_artifacts?.[0]?.sha256?.slice(0, 12)}
          </div>
        </div>
        <div className="be-denominator">
          <div className="be-switch-strip">
            {Object.entries(denominator.policy_switch_counts || {}).map(
              ([status, count]) => (
                <span className="be-switch-chip" key={status}>
                  <span className="mono">{compactNumber(count)}</span> {status}
                </span>
              ),
            )}
          </div>
          <PolicyDenominator policies={coverage.euromod_policies || []} />
        </div>
      </section>
    </div>
  );
}
