# Belgium Axiom↔EUROMOD per-record validation — July 6, 2026

> Historical report. Its non-documentary PIT pipelines are no longer active;
> the preserved scorecard is excluded from current dashboard loaders and lives
> under `dashboard/public/data/historical/retired-documentary-boundary/`.

Upgrades the Belgium cross-engine evidence from aggregate agreement (€643 on
€20.9B employee SSC over an identical population) to **per-record** agreement,
and extends it to a nonlinear program (personal income tax with the Article 87
marital quotient). Ladder rungs 1 + 2 of axiom-rules-engine#77.

The historical machine-readable scorecard with full per-record distributions
and config pins is
`dashboard/public/data/historical/retired-documentary-boundary/report-artifacts/be-euromod-per-record-scorecard.json`.

## Why per-record

Employee SSC is a flat 13.07% of gross professional income, so it is
approximately proportional to gross. Two engines that both price the same
population will therefore agree in aggregate almost regardless of encoding
detail — the €643-on-€20.9B headline (0.031 ppm) is a weak discriminator. The
honest test is whether they agree record by record, and whether that agreement
survives on a **nonlinear** surface where progressive brackets, a tax-free-amount
ladder, and a household-splitting quotient can each introduce disagreement.

## Config pins

| Pin | Value |
| --- | --- |
| EUROMOD release | J2.0+ (`EUROMOD_RELEASES_J2.0+`) |
| System / dataset | BE_2025 / BE_2024_c1_2015_03_e2 (dataset-name gating workaround, ec-jrc#4; no licensed microdata) |
| Template dataset | BE_training_data |
| Runtime | x86_64 (Rosetta) Python 3.12 + .NET x64 (coreclr) |
| Uprating factor | 1.05502 (config → system) |
| Batch isolation | per-household engine runs (axiom-oracles#168) |
| axiom-rules-engine | aa1ff02 (v0.1.0) |
| rulespec-be | a69bfa6 |
| Population sha256 | 82ba2938…72cdc (166,302 records; 78,479 workers; weighted 4.42M workers) |

Population: calibrated `populace-be v0` — populace-us records reweighted to
Belgian Ledger targets. This is the identical population the €643 aggregate
check used. EUROMOD's post-uprating gross matches Axiom's annual gross to a
maximum relative difference of 0.000000 across all 78,479 worker records,
confirming both engines price the same population.

## Rung 1 — Employee SSC: exact per-record

| Metric | Value |
| --- | ---: |
| Worker records compared | 78,479 |
| Max per-record \|difference\| | €0.028 / yr |
| Mean per-record \|difference\| | €0.0005 / yr |
| Within €0.10 / yr | 78,479 / 78,479 (100.000%) |
| Within €0.01 / yr | 78,378 / 78,479 (99.871%) |
| Aggregate (Axiom vs EUROMOD) | €20,874,275,929 vs €20,874,276,572 |
| Aggregate \|difference\| | €642.87 (0.031 ppm) |

The €643 aggregate concealed **exact** per-record identity. The €0.028 maximum is
float32 rounding in the population pipeline, not a modeling difference. A live
re-run of the first 2,000 rows through EUROMOD BE_2025 today reproduces the
stored `tscee_s` to `max|d| = 0.000000`.

## Rung 2 — Personal income tax (nonlinear)

Two views: the isolated marital-quotient mechanism (clean, controlled) and the
whole-population PIT (confounded by known scope differences).

### 2b. Marital quotient — isolated, controlled grid

Single-earner married couples at 30k / 45k / 60k gross. `tin_s` is deterministic
PIT — no take-up draw is involved, so no `euromod_constant_overrides` pin is
required (the pin mechanism applies to benefit suites where the solo draw marks
non-take).

| Case | EUROMOD tin_s | Axiom couple PIT | Difference |
| --- | ---: | ---: | ---: |
| 30k | −808.58 | 2,766.60 | +3,575.18 |
| 45k | 3,484.26 | 7,000.91 | +3,516.65 |
| 60k | 7,548.60 | 12,345.08 | +4,796.47 |

**Diagnosis — encoding scope limitation, not an engine defect.** The
`couple_pit_oracle_pipeline` is a deliberately thin Article 87 marital-quotient
slice: its per-spouse taxable-income entry is `max(0,
professional_income_after_imputation)` fed the raw post-uprating gross. It does
**not** subtract the 13.07% employee SSC (Law 29.06.1981 art. 38) or the Article
51 professional-expense forfait (30%, capped €5,930) before the rate scale —
whereas EUROMOD, and the complete single-worker `pilot_worker_oracle_pipeline`
(which matches EUROMOD 0/0), applies the scale to gross − SSC − forfait.

Independent hand-computation of CIR 1992 PIT (Art 130 brackets
16,320/28,800/49,840 at 25/40/45/50%; Art 131 tax-free amount €10,910; Art 134
ladder; Art 5/2 autonomy factor 0.24957) confirms it exactly:

- Scale on **gross** × 0.75043 = Axiom to the cent at all three cases.
- Scale on **net base** = EUROMOD to the cent at 60k, within €57.73 at 45k, and
  at 30k the remaining €1,596.30 is exactly the refundable Article 289ter/1
  work-bonus credit that drives EUROMOD's `tin_s` negative.

Per-case attribution:

- **60k**: €4,796.47 = 100% omitted SSC + Art. 51 forfait base reduction.
- **45k**: €3,516.65 = that base reduction + €57.73 further pre-scale reductions.
- **30k**: €3,575.18 = that base reduction + €1,596.30 refundable work-bonus credit.

The Article 87 imputation arithmetic itself is exact; the slice needs SSC +
forfait wired into its per-spouse base to reach 0/0. Filed on rulespec-be.

### 2a. Whole-population PIT — honest scope gap

On the full 166,302-record population (individual filers; the marital quotient
is not exercised here), aggregate Axiom PIT is €35.1B at a 7% flat communal
assumption (€32.8B at 0%) vs EUROMOD `tin_s` €19.5B. This is **not** a per-record
match, but every divergence resolves to a documented concept/scope difference,
not a rate/bracket/quotient defect:

- **Refundable work-bonus credit**: EUROMOD `tin_s` goes negative for 20,332
  records (weighted 1.99M; €2.65B of refunds); the pilot clamps liability at ≥0.
  Filed as rulespec-be#5.
- **Dependants / children** (Art. 132 supplements): declared out of scope in the
  pilot (~€1.4B per the prior decomposition on populace#259).
- **7% flat communal assumption**: the pilot has no commune assignment; the 0%
  run is reported alongside.

## Divergence classification

| Rung | Surface | Result | Cause |
| --- | --- | --- | --- |
| 1 | Employee SSC | Exact per-record (max €0.028/yr) | — |
| 2b | Marital-quotient PIT (isolated) | +€3,516–4,796 per case | Encoding scope: couple slice omits SSC + Art. 51 forfait base reduction (rulespec-be) |
| 2a | Population PIT | €35.1B vs €19.5B aggregate | Concept/scope: refundable credit (rulespec-be#5), dependants out of scope, communal assumption |

No EUROMOD engine defect was found on these surfaces. The one open engine-side
item touching Belgium remains ec-jrc#15 (household-keyed random draws), already
neutralized here by per-household runs (axiom-oracles#168).
