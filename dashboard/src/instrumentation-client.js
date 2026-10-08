import posthog from "posthog-js";

// Runs once in the browser when the app boots (Next.js instrumentation-client).
if (typeof window !== "undefined" && !posthog.__loaded) {
  posthog.init("phc_mrEaBroaYTRUrdkfhJYBGMpafKXWEdUyw5VPQnheh37m", {
    api_host: "https://us.i.posthog.com",
    defaults: "2026-01-30",
    person_profiles: "identified_only",
    respect_dnt: true,
    capture_pageview: "history_change",
  });
}
