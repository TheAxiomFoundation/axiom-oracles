/**
 * Pure helpers for the SOUTHMOD model-findings section of the oracle page.
 *
 * The data is dashboard/public/data/southmod-issues.json, written by
 * scripts/publish_issue_ledgers.py from axiom_oracles/data/<model>_issues.json.
 * No imports, so dashboard/scripts/test-southmod-findings.mjs runs it under
 * plain node; the caller passes the SOUTHMOD_MODELS registry in.
 *
 * Nothing here infers a ledger field: a missing status stays missing, and
 * `reported_upstream` is shown as written (several entries say nothing was
 * sent, so it is never read as "filed").
 */

export const STATUS_LABELS = {
  upstream_filed: "reported upstream",
  observed_local: "observed locally",
  not_reproduced_live: "not reproduced live",
};

/** Chip tone per status; the classes are .v2-action-* in globals.css. */
export const STATUS_TONES = {
  upstream_filed: "filed",
  observed_local: "muted",
  not_reproduced_live: "muted",
};

export const CLASSIFICATION_LABELS = {
  southmod_model_simplification: "model simplification",
  southmod_model_defect_candidate: "model defect candidate",
  southmod_model_schedule_issue: "model schedule issue",
  southmod_model_behaviour: "model behaviour",
  southmod_model_stale_parameter: "stale model parameter",
  southmod_source_gap: "source gap",
  convention_difference: "convention difference",
  no_engine_issue: "no model issue",
  validation_year_grounding_gap: "validation-year grounding gap",
  primary_instrument_not_publicly_digitized: "instrument not publicly digitized",
  carrier_not_in_captured_print: "carrier not in captured print",
};

/** A readable label for a snake_case code: the table, else the words. */
export function codeLabel(table, code) {
  if (code == null || code === "") return null;
  return table[code] || String(code).replaceAll("_", " ");
}

export function classificationLabel(code) {
  return codeLabel(CLASSIFICATION_LABELS, code);
}

export function statusLabel(code) {
  return codeLabel(STATUS_LABELS, code);
}

/** What the entry says Axiom's books should make of it. */
export function axiomGapLabel(value) {
  if (value === true) return "counts as an Axiom gap";
  if (value === false) return "not an Axiom gap";
  return "Axiom gap unadjudicated";
}

/** The entry's main prose: older entries say `summary`, newer `observed`. */
export function findingText(entry) {
  return entry?.summary || entry?.observed || "";
}

/** DOM id for an entry, so `<ledger>#<id>` citations can deep-link. */
export function findingAnchor(id) {
  return `finding-${id}`;
}

/**
 * One group per SOUTHMOD model, in registry order. A model the bundle does
 * not list, or lists with a null ledger, comes back with `entries: []` and
 * `ledger: null` so the page can say so instead of dropping the country.
 */
export function groupFindings(bundle, models) {
  const byRegion = new Map(
    (bundle?.models || []).map((m) => [m.region, m]),
  );
  return Object.entries(models || {}).map(([region, meta]) => {
    const published = byRegion.get(region) || null;
    const ledger = published?.ledger || null;
    return {
      region,
      model: meta.model,
      country: meta.country,
      source: published?.source || null,
      note: published?.note || null,
      updatedAt: ledger?.updated_at || null,
      ledger,
      entries: ledger?.entries || [],
    };
  });
}

/**
 * Narrow groups to the record's scope. `region` keeps one country (null for
 * all). `keepSuite`, when set, is the record's program filter: it keeps the
 * entries that touch at least one suite it accepts (an entry naming no suite
 * cannot match a program) and drops the groups left empty, a ledger-less
 * model included. Without it every group in the region stays, so a model
 * with no ledger still says so.
 *
 * Returns the scoped groups (each with `total`, its unfiltered count), the
 * region's `total` and the `inScope` count.
 */
export function scopeFindings(groups, { region = null, keepSuite = null } = {}) {
  const regional = groups.filter((g) => !region || g.region === region);
  const total = regional.reduce((n, g) => n + g.entries.length, 0);
  const scoped = regional
    .map((g) => ({
      ...g,
      total: g.entries.length,
      entries: keepSuite
        ? g.entries.filter((e) =>
            (e.affected_comparisons || []).some((suite) => keepSuite(suite)),
          )
        : g.entries,
    }))
    .filter((g) => !keepSuite || g.entries.length > 0);
  const inScope = scoped.reduce((n, g) => n + g.entries.length, 0);
  return { groups: scoped, total, inScope };
}

/**
 * Show whole groups until about `budget` entries are on screen; the rest
 * fold away. Never split a group (the discrepancy-class ledger's rule).
 * `pinned` (an entry id, e.g. from the URL hash) forces its group into view.
 */
export function foldGroups(groups, budget = 10, pinned = null) {
  const shown = [];
  let lines = 0;
  let i = 0;
  while (i < groups.length && (lines < budget || shown.length === 0)) {
    shown.push(groups[i]);
    lines += groups[i].entries.length;
    i += 1;
  }
  const rest = groups.slice(i);
  const pinnedInRest =
    pinned != null &&
    rest.some((g) => g.entries.some((e) => e.id === pinned));
  return { shown, rest, pinnedInRest };
}
