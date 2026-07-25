# Federal grid suite final integration

## State

Active on `fed-parity/federal-grid-suites`. The required rulespec-us pull requests
#1002, #1003, #1004, and #1009 are merged. All eight federal suite configs now
resolve through the isolated canonical-basename snapshot at
`/private/tmp/oracle-rerun/rulespec-us`.

## Done

- Verified the four merge preconditions against GitHub.
- Recorded the merged rulespec-us merge commits:
  - #1002: `8166c5462caaa9392fa30ee92368afc2fcc38393`
  - #1003: `91829ea72e7d2e4fd3f26705c27cabbc4670db67`
  - #1004: `3373e8411f7e141fd50879e3de964386f606f7f6`
  - #1009: `96df09f79deaea3e287e9c35e2582dede1b4bad5`
- Confirmed GitHub `main` is exactly #1004 merge commit `3373e841...`.
- Built the isolated rulespec-us clone. Direct network cloning was unavailable
  in the sandbox, so the clone uses the locally present merged objects and
  checks out credit head `09b28cdd...`, whose tree `7e00f195...` is the exact
  #1004 merge tree. All 11 blobs changed between #1003 and #1004 were verified
  against their GitHub `main` blob IDs.
- Pointed all eight federal grid configs at that snapshot.

## Next

- Remove the stale Saver's Credit config/report/manifest/disposition and preserve
  the PolicyEngine #9151 evidence in the uncovered tracking note.
- Re-scope Additional Medicare to its five-case wage-only, zero-SE domain and
  add an upstream-main provenance/tree-integrity pin.
- Run the seven remaining registered suites plus record the removed eighth lane,
  regenerate conformance artifacts, and run the full validation battery.
