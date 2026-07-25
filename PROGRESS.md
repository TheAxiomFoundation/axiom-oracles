# Federal grid suite final integration

## State

Active on `fed-parity/federal-grid-suites`. The required rulespec-us pull requests
#1002, #1003, #1004, and #1009 are merged. No suite or report changes have been
made yet.

## Done

- Verified the four merge preconditions against GitHub.
- Recorded the merged rulespec-us merge commits:
  - #1002: `8166c5462caaa9392fa30ee92368afc2fcc38393`
  - #1003: `91829ea72e7d2e4fd3f26705c27cabbc4670db67`
  - #1004: `3373e8411f7e141fd50879e3de964386f606f7f6`
  - #1009: `96df09f79deaea3e287e9c35e2582dede1b4bad5`

## Next

- Inventory the federal suite configs, reports, dispositions, manifest, and gates.
- Build a fresh canonical-basename rulespec-us `origin/main` snapshot under
  `/private/tmp/oracle-rerun/rulespec-us`.
- Re-scope or remove stale surfaces as required, run all eight suites for real,
  regenerate conformance artifacts, and run the full validation battery.
