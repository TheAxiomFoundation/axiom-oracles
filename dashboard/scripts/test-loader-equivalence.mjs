// Loader equivalence test: the overview.json fast path must produce the
// same oracle data as per-file loading. Run from dashboard/:
//   npx esbuild src/utils/data.js --bundle --format=esm --outfile=/tmp/data-bundled.mjs
//   node scripts/test-loader-equivalence.mjs
import { readFile } from 'fs/promises';
import { existsSync } from 'fs';

let hideOverview = false;
globalThis.fetch = async (url) => {
  const path = 'public' + String(url);
  if (hideOverview && path.endsWith('overview.json')) return { ok: false };
  if (!existsSync(path)) return { ok: false };
  const text = await readFile(path, 'utf8');
  return { ok: true, json: async () => JSON.parse(text) };
};

const { loadOracleData } = await import('/tmp/data-bundled.mjs');

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
});
const f = summarize(fast), s = summarize(slow);
console.log('bundle path :', JSON.stringify(f), `${t1-t0}ms`);
console.log('perfile path:', JSON.stringify(s), `${t2-t1}ms`);
const equal = JSON.stringify(f) === JSON.stringify(s);
console.log('EQUIVALENT:', equal);
const fixup = fast.reports.filter(r => /^axiom-policyengine-[a-z]{2}-snap-ecps\.json$/.test(r.file||'') && r.suite === 'nyc-synthetic').length;
console.log('legacy-suite fixup leftovers (must be 0):', fixup);
if (!equal || fixup > 0) process.exit(1);
