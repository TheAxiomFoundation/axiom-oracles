/**
 * Dependency-free mirror of axiom_oracles/conformance/unexplained.py.
 * Assess the unfiltered report. Browser consumers cannot validate repository
 * disposition files; parity therefore uses the Python API without repo_root.
 */

const CLASSIFIED_KINDS = [
  "explained_residual",
  "upstream_engine_gap",
  "bridge_artifact",
  "axiom_encoding_gap",
];
const KNOWN_KINDS = [...CLASSIFIED_KINDS, "unexplained"];
// Max's d1248 split preserves the published headline until a separate decision.
export const CONSERVATIVE_UNEXPLAINED_ENABLED = false;
const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
const has = (value, key) => Object.hasOwn(value, key);
const truthy = value => {
  if (Array.isArray(value)) return value.length > 0;
  if (object(value)) return Object.keys(value).length > 0;
  return Boolean(value);
};

// Count diagnostics preserve the Python API's established wording, including
// Python representations of JSON scalars and non-finite numeric mutants.
function repr(value) {
  if (value == null) return "None";
  if (typeof value === "boolean") return value ? "True" : "False";
  if (typeof value === "number") {
    if (Number.isNaN(value)) return "nan";
    if (value === Infinity) return "inf";
    if (value === -Infinity) return "-inf";
    if (value !== 0 && Math.abs(value) < 0.0001) {
      return value.toExponential().replace(/e([+-])(\d)$/, "e$10$2");
    }
    return String(value);
  }
  if (typeof value === "string") {
    const quote = value.includes("'") && !value.includes('"') ? '"' : "'";
    const escaped = value.replace(/\\/g, "\\\\")
      .replace(new RegExp(quote, "g"), `\\${quote}`)
      .replace(/\n/g, "\\n").replace(/\r/g, "\\r").replace(/\t/g, "\\t")
      .replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, char =>
        `\\x${char.charCodeAt(0).toString(16).padStart(2, "0")}`);
    return `${quote}${escaped}${quote}`;
  }
  if (Array.isArray(value)) return `[${value.map(repr).join(", ")}]`;
  return `{${Object.entries(value).map(([key, item]) => `${repr(key)}: ${repr(item)}`).join(", ")}}`;
}

export function admitCount(value) {
  return typeof value === "number" && Number.isFinite(value) &&
    Number.isSafeInteger(value) && value >= 0 ? value : null;
}

function countDefect(value, field, suite) {
  if (typeof value === "boolean") return `${suite}: ${field} is a boolean, not a count`;
  if (typeof value === "number" && Number.isInteger(value) && value < 0) {
    return `${suite}: ${field} is negative (${BigInt(value)})`;
  }
  return `${suite}: ${field} is not a non-negative integer (${repr(value)})`;
}

export function requireCount(value, field, suite = "<unknown>") {
  const admitted = admitCount(value);
  if (admitted === null) throw new Error(countDefect(value, field, suite));
  return admitted;
}

export function publishedUnexplained(report, {
  known_causes = [], view = "dashboard", conservative = CONSERVATIVE_UNEXPLAINED_ENABLED,
} = {}) {
  if (!["dashboard", "scoreboard"].includes(view)) {
    throw new Error(`unknown unexplained publication view '${view}'`);
  }
  if (conservative) {
    const assessment = assessUnexplained(report, { known_causes });
    if (assessment.defects.length) throw new Error(assessment.defects.join("; "));
    return assessment.count;
  }
  const suite = report.suite ?? "<unknown>";
  const summary = has(report, "summary") ? report.summary : {};
  const rows = has(report, "mismatches") ? report.mismatches : [];
  if (!object(summary)) throw new Error(`${suite}: summary must be an object`);
  if (!Array.isArray(rows)) throw new Error(`${suite}: mismatches must be an array`);
  for (const field of ["comparison_count", "match_count", "mismatch_count"]) {
    if (has(summary, field)) requireCount(summary[field], field, suite);
  }
  const block = summary.dispositioned ?? {};
  if (!object(block)) throw new Error(`${suite}: dispositioned must be an object`);
  const counts = has(block, "counts") ? block.counts : {};
  if (!object(counts)) throw new Error(`${suite}: disposition counts must be an object`);
  for (const [kind, raw] of Object.entries(counts)) requireCount(raw, `counts.${kind}`, suite);
  if (has(block, "unexplained_count")) requireCount(block.unexplained_count, "unexplained_count", suite);
  if (has(summary, "mismatch_count")) {
    const mismatch = requireCount(summary.mismatch_count, "mismatch_count", suite);
    if (rows.length > mismatch) throw new Error(`${suite}: ${rows.length} mismatch rows are listed but mismatch_count is ${mismatch}`);
    const classified = CLASSIFIED_KINDS.reduce((sum, kind) => sum + (counts[kind] ?? 0), 0);
    if (classified > mismatch) throw new Error(`${suite}: classified rows (${classified}) exceed mismatches (${mismatch})`);
    for (const raw of [block.unexplained_count ?? 0, counts.unexplained ?? 0]) {
      if (raw > mismatch) throw new Error(`${suite}: unexplained count (${raw}) exceeds mismatches (${mismatch})`);
    }
  }
  if (view === "scoreboard") {
    if (truthy(block)) return requireCount(has(block, "unexplained_count") ? block.unexplained_count : 0, "unexplained_count", suite);
    return requireCount(has(summary, "mismatch_count") ? summary.mismatch_count : rows.length, "mismatch_count", suite);
  }
  if (truthy(block.dispositions_file) && has(block, "unexplained_count")) {
    return requireCount(block.unexplained_count, "unexplained_count", suite);
  }
  let count = 0;
  for (const row of rows) {
    if (!object(row)) throw new Error(`${suite}: mismatch row must be an object`);
    if (truthy(row.concept) && !causeFor(known_causes, report, row.concept, row.kind, suite)) count += 1;
  }
  return count;
}

function isOpenRulespecIssue(url) {
  const lowered = String(url).toLowerCase();
  return lowered.includes("/rulespec-") && lowered.includes("/issues/");
}

function causeFor(knownCauses, report, concept, kind, suite) {
  const engines = report.engines || {};
  const candidates = knownCauses.filter(cause => cause.suite === suite &&
    cause.concept === concept && (cause.kind ?? null) === (kind ?? null));
  return candidates.find(cause => truthy(cause.engines) &&
    (cause.engines.left ?? null) === (engines.left ?? null) &&
    (cause.engines.right ?? null) === (engines.right ?? null)) ||
    candidates.find(cause => !truthy(cause.engines));
}

export function assessUnexplained(report, {
  known_causes = [], summary = null, rows = null, suite = null,
} = {}) {
  if (object(suite)) suite = suite.suite ?? null;
  suite = suite ?? (has(report, "suite") ? report.suite : "<unknown>");
  const suiteLabel = suite == null ? "None" : String(suite);
  const defects = [];
  const notes = [];
  if (summary == null) summary = has(report, "summary") ? report.summary : {};
  if (!object(summary)) {
    throw new Error(`${suiteLabel}: summary must be an object`);
  }
  if (rows == null) rows = has(report, "mismatches") ? report.mismatches : [];
  if (!Array.isArray(rows)) {
    throw new Error(`${suiteLabel}: mismatches must be an array`);
  }
  if (rows.some(row => !object(row))) throw new Error(`${suiteLabel}: mismatch row must be an object`);
  const read = (value, field) => {
    return requireCount(value, field, suiteLabel);
  };

  for (const field of ["comparison_count", "match_count"]) {
    if (has(summary, field)) read(summary[field], field);
  }

  let mismatch = rows.length;
  if (has(summary, "mismatch_count")) {
    const admitted = read(summary.mismatch_count, "mismatch_count");
    if (admitted !== null) mismatch = admitted;
  }
  if (rows.length > mismatch) {
    throw new Error(`${suiteLabel}: ${rows.length} mismatch rows are listed but mismatch_count is ${mismatch}`);
  }
  let block = summary.dispositioned;
  if (block == null) block = {};
  else if (!object(block)) {
    throw new Error(`${suiteLabel}: dispositioned must be an object`);
  }
  let counts = has(block, "counts") ? block.counts : {};
  if (!object(counts)) {
    throw new Error(`${suiteLabel}: disposition counts must be an object`);
  }
  const unknown = Object.keys(counts).filter(kind => !KNOWN_KINDS.includes(kind)).sort();
  if (unknown.length) {
    defects.push(`${suiteLabel}: unknown disposition kind(s) ${repr(unknown)} — only ` +
      `${repr([...KNOWN_KINDS].sort())} carry defined meaning`);
  }
  const admittedCounts = Object.fromEntries(Object.keys(counts).sort().map(kind =>
    [kind, read(counts[kind], `counts.${kind}`)]));
  const classified = CLASSIFIED_KINDS.reduce((sum, kind) => sum + (admittedCounts[kind] || 0), 0);
  const signals = [];
  if (has(block, "unexplained_count")) {
    const signal = read(block.unexplained_count, "unexplained_count");
    if (signal !== null) signals.push(signal);
  }
  if (admittedCounts.unexplained != null) signals.push(admittedCounts.unexplained);
  const declared = signals.length ? Math.max(...signals) : null;
  if (classified > mismatch) throw new Error(`${suiteLabel}: classified rows (${classified}) exceed mismatches (${mismatch})`);
  if (declared !== null && declared > mismatch) throw new Error(`${suiteLabel}: unexplained count (${declared}) exceeds mismatches (${mismatch})`);
  if (new Set(signals).size > 1) notes.push("declared unexplained counts disagree; using the maximum");
  const filename = block.dispositions_file;
  if (filename != null && filename !== "" && typeof filename !== "string") {
    defects.push(`${suiteLabel}: dispositions_file must be a repository-relative string`);
  }
  const mode = typeof filename === "string" && filename ? "file" : classified > 0 ? "inline" : "none";
  let covered = 0;
  let axiom = 0;
  let count;
  if (mode === "file" || mode === "inline") {
    count = Math.max(declared || 0, mismatch - classified);
    axiom = admittedCounts.axiom_encoding_gap || 0;
    for (const row of rows) {
      const disposition = object(row) ? row.disposition : null;
      if (object(disposition) && disposition.disposition !== "axiom_encoding_gap" &&
        isOpenRulespecIssue(disposition.linked_issue)) axiom += 1;
    }
    if (classified + (declared || 0) !== mismatch) {
      notes.push("disposition counts do not conserve against mismatches; using the conservative maximum");
    }
    if (mode === "inline") notes.push("inline classification is producer-declared, not file-validated");
  } else {
    for (const row of rows) {
      if (!object(row)) {
        defects.push(`${suiteLabel}: mismatch row must be an object`);
        continue;
      }
      if (has(row, "disposition") || !truthy(row.concept)) continue;
      const cause = causeFor(known_causes, report, row.concept, row.kind, suite);
      if (cause) {
        covered += 1;
        const owner = cause.fix_owner || "";
        if (String(owner).startsWith("rulespec") || owner === "axiom-encode" ||
          isOpenRulespecIssue(cause.issue_url)) axiom += 1;
      }
    }
    if (covered > mismatch) {
      defects.push(`${suiteLabel}: known-cause covered rows (${covered}) exceed mismatches (${mismatch})`);
      count = mismatch;
    } else count = mismatch - covered;
    count = Math.max(count, declared || 0);
  }
  return {
    count, mode, mismatch_count: mismatch, declared, classified,
    known_cause_covered: covered, axiom_attributed: axiom, defects, notes,
  };
}

/**
 * The unexplained publication gate's domain, mirroring
 * scripts/unexplained_ratchet.py: a report with a suite and engines, carrying
 * summary and mismatches, not a typed diagnostic suite, with an Axiom leg in
 * either the {left, right} or the named-engine (grid) shape.
 */
export function isUnexplainedGated(report, isDiagnostic = () => false) {
  if (!object(report) || !truthy(report.suite) || !truthy(report.engines)) return false;
  if (!has(report, "mismatches") || !has(report, "summary")) return false;
  if (isDiagnostic(report.suite)) return false;
  const engines = object(report.engines) ? report.engines : {};
  return engines.left === "axiom" || engines.right === "axiom" || has(engines, "axiom");
}

/**
 * Per-suite gated counts: the maximum over a suite's reports, independent of
 * order (the ratchet's duplicate-suite resolution). Summing the values gives
 * the gate's total.
 */
export function gatedUnexplainedBySuite(reports, {
  known_causes = [],
  isDiagnostic = () => false,
  conservative = CONSERVATIVE_UNEXPLAINED_ENABLED,
} = {}) {
  const bySuite = {};
  for (const report of reports || []) {
    if (!isUnexplainedGated(report, isDiagnostic)) continue;
    const count = publishedUnexplained(report, { known_causes, conservative });
    bySuite[report.suite] = Math.max(bySuite[report.suite] ?? 0, count);
  }
  return bySuite;
}
