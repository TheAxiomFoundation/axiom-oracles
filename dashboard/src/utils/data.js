/**
 * Load and combine pairwise axiom.comparison_report.v1 JSON files
 * into an N-way oracle comparison structure.
 *
 * Data files are expected at /data/<left>-<right>.json
 * (e.g., policyengine-taxsim.json).
 */

/**
 * @typedef {Object} OracleData
 * @property {string[]} oracles - Unique oracle names
 * @property {Object[]} reports - Raw report objects
 * @property {Object} matrix - { [concept]: { [left]: { [right]: matchRate } } }
 * @property {Object[]} concepts - Unique concept definitions
 * @property {Object[]} allCases - Merged case list with per-oracle values
 */

export async function loadOracleData(basePath = "") {
  // Load manifest to discover report files
  let reportFiles = ["policyengine-taxsim.json"];
  try {
    const manifestResp = await fetch(`${basePath}/data/manifest.json`);
    if (manifestResp.ok) {
      const manifest = await manifestResp.json();
      reportFiles = manifest.reports || reportFiles;
    }
  } catch {
    // fall back to default
  }

  const reports = [];
  for (const file of reportFiles) {
    try {
      const url = `${basePath}/data/${file}`;
      const resp = await fetch(url);
      if (resp.ok) {
        reports.push(await resp.json());
      }
    } catch {
      // skip missing files
    }
  }

  // Load Axiom corpus program manifest
  let allPrograms = [];
  try {
    const programsResp = await fetch(`${basePath}/data/programs.json`);
    if (programsResp.ok) {
      const payload = await programsResp.json();
      allPrograms = payload.programs || [];
    }
  } catch {
    // continue without programs filter
  }

  // Drop aspirational / missing programs — the dashboard reflects only what
  // is actually encoded in the Axiom corpus today.
  const programs = allPrograms.filter(
    (p) => p.encoding_status !== "missing",
  );

  // Filter reports to concepts encoded in the Axiom corpus, plus any
  // components those concepts declare. Components carry parent={parent_id}
  // in the report so they hitch a ride on their parent's allow-listing.
  const allowedConcepts = new Set(programs.map((p) => p.id));
  for (const report of reports) {
    for (const concept of report.concepts || []) {
      if (concept.parent && allowedConcepts.has(concept.parent)) {
        allowedConcepts.add(concept.id);
      }
    }
  }
  const filteredReports = reports.map((report) =>
    filterReportToConcepts(report, allowedConcepts),
  );

  const data = buildNWayData(filteredReports);
  return { ...data, programs, reports: filteredReports };
}

function filterReportToConcepts(report, allowed) {
  if (allowed.size === 0) return report;
  return {
    ...report,
    concepts: (report.concepts || []).filter((c) => allowed.has(c.id)),
    aggregates: (report.aggregates || []).filter((a) =>
      allowed.has(a.concept)
    ),
    mismatches: (report.mismatches || []).filter((m) =>
      allowed.has(m.concept)
    ),
    cases: (report.cases || []).map((c) => ({
      ...c,
      mismatches: (c.mismatches || []).filter((m) => allowed.has(m.concept)),
    })),
  };
}

export function buildNWayData(reports) {
  const oracleSet = new Set();
  const conceptMap = new Map();

  for (const report of reports) {
    const left = report.engines?.left;
    const right = report.engines?.right;
    if (left) oracleSet.add(left);
    if (right) oracleSet.add(right);

    for (const concept of report.concepts || []) {
      if (!conceptMap.has(concept.id)) {
        conceptMap.set(concept.id, concept);
      }
    }
  }

  const oracles = [...oracleSet].sort();
  const concepts = [...conceptMap.values()];

  // Build per-concept pairwise agreement matrix
  const matrix = {};
  for (const concept of concepts) {
    matrix[concept.id] = {};
    for (const left of oracles) {
      matrix[concept.id][left] = {};
      for (const right of oracles) {
        if (left === right) {
          matrix[concept.id][left][right] = 100;
        } else {
          matrix[concept.id][left][right] = null;
        }
      }
    }
  }

  for (const report of reports) {
    const left = report.engines?.left;
    const right = report.engines?.right;
    if (!left || !right) continue;

    for (const agg of report.aggregates || []) {
      const rate = agg.match_rate;
      if (rate != null && matrix[agg.concept]) {
        matrix[agg.concept][left][right] = rate;
        matrix[agg.concept][right][left] = rate;
      }
    }
  }

  // Compute overall pairwise rates (average across concepts)
  const overallMatrix = {};
  for (const left of oracles) {
    overallMatrix[left] = {};
    for (const right of oracles) {
      if (left === right) {
        overallMatrix[left][right] = 100;
        continue;
      }
      const rates = concepts
        .map((c) => matrix[c.id]?.[left]?.[right])
        .filter((r) => r != null);
      overallMatrix[left][right] =
        rates.length > 0
          ? rates.reduce((a, b) => a + b, 0) / rates.length
          : null;
    }
  }

  // Merge cases across reports — index by case_id
  const caseIndex = new Map();
  for (const report of reports) {
    const left = report.engines?.left;
    const right = report.engines?.right;

    for (const c of report.cases || []) {
      if (!caseIndex.has(c.case_id)) {
        caseIndex.set(c.case_id, {
          case_id: c.case_id,
          metadata: c.metadata || {},
          values: {},
          mismatches: [],
          match_rate: c.match_rate,
        });
      }
      const entry = caseIndex.get(c.case_id);

      // Extract per-oracle values from mismatches and matches
      for (const m of c.mismatches || []) {
        if (!entry.values[m.concept]) entry.values[m.concept] = {};
        entry.values[m.concept][left] = m.left;
        entry.values[m.concept][right] = m.right;
        entry.mismatches.push({
          ...m,
          pair: `${left} vs ${right}`,
        });
      }
    }
  }

  const allCases = [...caseIndex.values()];

  // Summary stats — recomputed from filtered aggregates so dropped concepts
  // (e.g., state income tax that isn't in the Axiom corpus) don't inflate
  // numbers.
  const aggregateTotals = reports.reduce(
    (acc, r) => {
      for (const agg of r.aggregates || []) {
        acc.matches += (agg.comparison_count - agg.mismatch_count) || 0;
        acc.mismatches += agg.mismatch_count || 0;
        acc.comparisons += agg.comparison_count || 0;
      }
      return acc;
    },
    { matches: 0, mismatches: 0, comparisons: 0 },
  );

  const summary = {
    totalCases: allCases.length,
    totalOracles: oracles.length,
    totalConcepts: concepts.length,
    totalReports: reports.length,
    overallMatchRate:
      aggregateTotals.comparisons > 0
        ? (aggregateTotals.matches / aggregateTotals.comparisons) * 100
        : 0,
    mismatchCount: aggregateTotals.mismatches,
  };

  return { oracles, reports, matrix, overallMatrix, concepts, allCases, summary };
}

