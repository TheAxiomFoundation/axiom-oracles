# Federal grid suites progress

## State

In progress on `fed-parity/federal-grid-suites`. Building a configurable
`federal-tax-liability-grid` runner and four PolicyEngine-US 1.767.3 comparison
suites for ACA PTC, NIIT, SECA, and Additional Medicare Tax.

## Done

- Read the mandatory machinery recon, grid contract, state-grid generator,
  runner dispatch/pinning code, reference comparison/disposition, target
  conformance rows, live-suite gate, and conformance documentation.
- Confirmed the branch starts at `origin/main` commit `d4666ae`.

## Next

- Verify PolicyEngine-US 1.767.3 variable boundaries and exact input surfaces.
- Inspect the companion RuleSpec fixture locations and schemas as they land.
- Implement and test the generator, runner dispatch, and four comparison
  configurations with configurable `rulespec_roots`.
- Run all four real comparisons, disposition genuine residuals if any, adopt the
  four conformance rows, regenerate artifacts in the mandated order, and run the
  full deterministic check/build battery.
- Write the required build summary with per-case results and command outcomes.
