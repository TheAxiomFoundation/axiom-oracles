// Lazy loader for the per-suite case artifacts under /data/cases/<suite>/.
// Each suite's full case rows (matches AND mismatches) are chunked JSON;
// this caches per suite so the explorer and triangulation share one fetch.

import { BASE_PATH } from "./basePath";

const cache = new Map();
const dispositionCache = new Map();

/**
 * The suite's disposition explanations (dispositions/<suite>.yaml shipped
 * as JSON): id, concept, kind, category, prose mechanism, linked issue.
 */
export async function loadSuiteDispositions(suite) {
  if (dispositionCache.has(suite)) return dispositionCache.get(suite);
  const promise = fetch(`${BASE_PATH}/data/dispositions/${suite}.json`)
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null);
  dispositionCache.set(suite, promise);
  return promise;
}

export async function loadSuiteCases(suite) {
  if (cache.has(suite)) return cache.get(suite);
  const promise = (async () => {
    const base = `${BASE_PATH}/data/cases/${suite}`;
    const indexResp = await fetch(`${base}/index.json`);
    if (!indexResp.ok) return null;
    const index = await indexResp.json();
    // v1 evidence indexes name and hash every chunk. Keep the numeric fallback
    // while the remaining legacy dashboard indexes are migrated.
    const chunkNames = Array.isArray(index.chunks)
      ? index.chunks.map((chunk) => chunk.name)
      : Array.from({ length: index.chunks }, (_, i) => `chunk-${i}.json`);
    const chunks = await Promise.all(
      chunkNames.map((name) =>
        fetch(`${base}/${name}`).then((r) => (r.ok ? r.json() : [])),
      ),
    );
    return { index, cases: chunks.flat() };
  })().catch(() => null);
  cache.set(suite, promise);
  return promise;
}
