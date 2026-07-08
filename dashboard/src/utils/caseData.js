// Lazy loader for the per-suite case artifacts under /data/cases/<suite>/.
// Each suite's full case rows (matches AND mismatches) are chunked JSON;
// this caches per suite so the explorer and triangulation share one fetch.

const cache = new Map();

export async function loadSuiteCases(suite) {
  if (cache.has(suite)) return cache.get(suite);
  const promise = (async () => {
    const base = `/data/cases/${suite}`;
    const indexResp = await fetch(`${base}/index.json`);
    if (!indexResp.ok) return null;
    const index = await indexResp.json();
    const chunks = await Promise.all(
      Array.from({ length: index.chunks }, (_, i) =>
        fetch(`${base}/chunk-${i}.json`).then((r) => (r.ok ? r.json() : [])),
      ),
    );
    return { index, cases: chunks.flat() };
  })().catch(() => null);
  cache.set(suite, promise);
  return promise;
}
