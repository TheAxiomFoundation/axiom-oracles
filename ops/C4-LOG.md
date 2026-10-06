# C4 executable tariff receipt journal

## 2026-08-16 — producer adoption and contract read

- A0 — P(pass) = 1.00. PASS. Adopted the executable producer, DK worked
  example, and tests from axiom-oracles PR #475. Producer introduction:
  `5402e5bf6`; final supplied refresh: `d236e5320`. The DK artifact was
  regenerated against this branch's committed source reports.
- A1 — P(pass) = 1.00. PASS. Read the producer contract completely. A receipt
  binds the exact committed certified values and inputs, recorded RuleSpec Git
  commit, source/program bytes, compiled artifact bytes, and engine binary
  SHA-256. `--check` re-archives the recorded commit, recompiles, reruns, and
  requires byte-identical derived JSON. JSON numeric equality is type-aware and
  exact (`1` is not `1.0`).
- A2 — P(pass) = 1.00. PASS. Engine binding is pinned-by-hash, not engine
  `main`. Tariff engine binary SHA-256:
  `674ca6e70afdccb59c3d6847933bc24b4590105e49db54790f2dcd0bdbbe32d7`;
  source commit: `ffd8213271947b0189a9dd61a055c1e0e78908a0`. Therefore
  oracles#296 (engine-main × rulespec-us-main) does not block this receipt.

## 2026-08-16 — tariff binding and selection

- B0 — P(pass) = 1.00. PASS. Bound rulespec-us `origin/main` exactly at
  `96d5e7c1e6309dc205b7320bbddaae8dd5d410df`; the requested `96d5e7c1`
  resolves to that same commit.
- B1 — P(pass) = 1.00. PASS. Bound and recompiled 101 composed programs: the
  witness `programs/us/us-tariff-duty/fy-2026.yaml` →
  `us/policies/cbp/us-tariff-duty/composition.yaml`, plus all 100 generated
  `programs/us/us-tariff-schedule/ch*.yaml` specs → their generated chapter
  composition modules. Compilation uses the pinned engine's
  `compile --program <absolute module path> --output <artifact>` contract and
  an `AXIOM_RULESPEC_REPO_ROOTS` parent containing the archived exact commit.
- B2 — P(pass) = 1.00. PASS. Selected a DK-sized 10-value set: all five
  witness lines, Canada/Census `1220` (the sole raw-conformant origin cohort
  common to all five), each line's earliest conformant in-domain interval with
  two distinct endpoints, and the composed statutory total at both endpoints.
  The receipt binds the full report, reference extract, bridge, and covered-line
  list by SHA-256 and names the source report family for each value.
- B3 — P(pass) = 1.00. PASS. C1 had only design/preflight plus uncommitted
  extraction/config work at the checkpoint; no landed scale-suite cell set was
  available, so no optional scale subset was added and C4 did not block on it.

## 2026-08-16 — gates

- G0 — P(pass) = 1.00. PASS. Tariff producer `--check`: 10/10 exact JSON
  numeric equality, `executable=true`; all 101 artifacts recompiled.
- G1 — P(pass) = 1.00. PASS. Fail-closed mutants: changed certified value,
  changed engine hash, and changed RuleSpec SHA each rejected by the hermetic
  validator. Focused producer suite: 10 passed.
- G2 — P(pass) = 1.00. PASS. Byte determinism: two full generations both
  produced receipt SHA-256
  `f32aad33893b9ff27680cac7fc58112dec2bd41d931e49f786280ae27f53c71f`.
- G3 — P(pass) = 1.00. PASS. No program-artifacts release is required. Like
  the DK producer, this producer records compiled-artifact identities in the
  receipt and rebuilds ephemeral artifacts during generation/check; it does
  not consume a released compiled-program bundle.
