// Deployment base path — must match `basePath` in next.config.mjs.
// The dashboard is served under https://axiom.org/oracles via the main-site
// reverse proxy, so every absolute asset/data URL needs this prefix.
export const BASE_PATH = "/oracles";
