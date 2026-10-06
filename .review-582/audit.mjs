import fs from 'node:fs';
import path from 'node:path';
import { loadOracleData } from './data-bundled.mjs';
const root = process.cwd();
const source = fs.readFileSync('dashboard/src/utils/suites.js', 'utf8');
const { suiteMeta, isAxiomPair, otherOracle } = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
globalThis.fetch = async (url) => {
  const file = path.join(root, 'dashboard/public', String(url));
  if (!fs.existsSync(file)) return new Response('', { status: 404 });
  return new Response(fs.readFileSync(file));
};
const data = await loadOracleData();
const verification = data.reports.filter(r => isAxiomPair(r) && suiteMeta(r.suite).kind !== 'diagnostic' && (r.aggregates || []).length > 0);
const households = r => Number.isFinite(r.case_count) ? r.case_count : (r.cases || []).length;
const kinds = {};
for (const r of verification) {
  const kind = suiteMeta(r.suite).kind;
  kinds[kind] ||= { reports: 0, cases: 0 };
  kinds[kind].reports++;
  kinds[kind].cases += households(r);
}
console.log(JSON.stringify({
  reports: verification.length,
  heroOracles: new Set(verification.map(otherOracle)).size,
  heroHouseholds: verification.reduce((n,r) => n + households(r),0),
  byKind: kinds,
},null,2));
for (const suite of ['medicaid-thresholds-states','pell-parameters','fiit-ecps','ca-federal-schedule-tax-spsm']) {
  const overview = verification.find(r => r.suite === suite);
  if (!overview) continue;
  const full = JSON.parse(fs.readFileSync(path.join('dashboard/public/data', overview.file)));
  console.log(JSON.stringify({suite, kind: suiteMeta(suite).kind, population: full.population,
    caseCount: full.case_count, firstCase: full.cases?.[0], mismatches: full.summary?.mismatch_count,
    publicMismatchRows: full.mismatches?.length,
    hasCaseIndex: fs.existsSync(path.join('dashboard/public/data/cases',suite,'index.json')),
  },null,2));
}
const parameter = verification.find(r => r.suite === 'medicaid-thresholds-states');
console.log('Concrete input: Medicaid threshold report alone renders ' + households(parameter) + ' households; actual unit = ' + parameter.population + '.');
const crossPair = { engines: { left: 'policyengine', right: 'taxsim' } };
console.log('Non-Axiom pair excluded:', !isAxiomPair(crossPair));
const kpi = JSON.parse(fs.readFileSync('dashboard/public/data/rule_verification_summary.json'));
console.log('Coverage context:',JSON.stringify({rules:kpi.rules,surfaces:kpi.surfaces}));
