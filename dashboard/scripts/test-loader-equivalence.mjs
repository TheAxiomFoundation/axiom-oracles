// Loader equivalence test: the overview.json fast path must produce the
// same oracle data as per-file loading. Run from dashboard/:
//   node scripts/test-loader-equivalence.mjs
import assert from 'node:assert/strict';
import { readFile } from 'fs/promises';
import { existsSync } from 'fs';

let hideOverview = false;
globalThis.fetch = async (url) => {
  const path = new URL('../public' + String(url), import.meta.url);
  if (hideOverview && path.pathname.endsWith('overview.json')) return { ok: false };
  if (!existsSync(path)) return { ok: false };
  const text = await readFile(path, 'utf8');
  return { ok: true, json: async () => JSON.parse(text) };
};

const { loadOracleData } = await import('../src/utils/data.js');
const { countUnexplained } = await import('../src/utils/programs.js');

const t0 = Date.now();
const fast = await loadOracleData('');
const t1 = Date.now();
hideOverview = true;
const slow = await loadOracleData('');
const t2 = Date.now();

const summarize = (d) => ({
  reports: d.reports.length,
  suites: d.suites.length,
  oracles: d.oracles.length,
  concepts: d.concepts.length,
  programs: d.programs.length,
  totalComparisons: d.reports.reduce((a, r) => a + (r.summary?.comparison_count || 0), 0),
  spsmCard: d.reports.some(r => r.engines?.right === 'spsm' && (r.aggregates||[]).length > 0),
  prdReports: d.reports.filter(r => r.engines?.right === 'prd').length,
  unexplained: countUnexplained(d.reports, d.knownCauses),
});
const f = summarize(fast), s = summarize(slow);
console.log('bundle path :', JSON.stringify(f), `${t1-t0}ms`);
console.log('perfile path:', JSON.stringify(s), `${t2-t1}ms`);
const equal = JSON.stringify(f) === JSON.stringify(s);
console.log('EQUIVALENT:', equal);
const fixup = fast.reports.filter(r => /^axiom-policyengine-[a-z]{2}-snap-ecps\.json$/.test(r.file||'') && r.suite === 'nyc-synthetic').length;
console.log('legacy-suite fixup leftovers (must be 0):', fixup);
if (!equal || fixup > 0) process.exit(1);

assert.deepEqual(
  fast.reports.map(r => [r.file, r.unexplained_assessment]),
  slow.reports.map(r => [r.file, r.unexplained_assessment]),
);
const spsm = fast.reports.find(r => r.suite === 'ca-federal-schedule-tax-spsm');
assert.equal(spsm.unexplained_assessment.count, 97);
assert.equal(countUnexplained([spsm], fast.knownCauses), 97);

// Filtering removes all three mismatch rows here, including the known-cause
// row. The assessment must still retain the unfiltered M=3, K=1 evidence.
const report = {
  suite: 'loader-unfiltered-test',
  engines: { left: 'axiom', right: 'spsm' },
  summary: { mismatch_count: 3 },
  mismatches: [{ concept: 'dropped', kind: 'numeric' }, {}, {}],
};
const causes = [{ suite: report.suite, concept: 'dropped', kind: 'numeric' }];
for (const useOverview of [true, false]) {
  const payloads = {
    '/data/manifest.json': { reports: ['fixture.json'] },
    '/data/programs.json': { programs: [{ id: 'kept' }] },
    '/data/known_causes.json': { entries: causes },
    '/data/fixture.json': report,
  };
  if (useOverview) payloads['/data/overview.json'] = { reports: [report] };
  globalThis.fetch = async url => ({
    ok: Object.hasOwn(payloads, String(url)),
    json: async () => structuredClone(payloads[String(url)]),
  });
  const loaded = await loadOracleData('');
  assert.equal(loaded.reports[0].mismatches.length, 0);
  assert.equal(loaded.reports[0].unexplained_assessment.known_cause_covered, 1);
  assert.equal(countUnexplained(loaded.reports, loaded.knownCauses), 2);
}
console.log('UNFILTERED UNEXPLAINED ASSESSMENT: true');
