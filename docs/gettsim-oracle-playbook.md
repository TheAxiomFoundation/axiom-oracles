# GETTSIM oracle playbook

GETTSIM — the German Taxes and Transfers SIMulator (IZA and an academic
consortium) — is the **second, independent** German comparison oracle in the
dual-oracle lane (`rulespec-de#1`), running alongside `EuromodPlatformRunner`.
Germany is the org's first lane where every instrument validates against *two*
oracles: where the two disagree, the statute print adjudicates and the
divergence is a finding against the losing model; where both agree against the
Axiom encoding, the encoding is presumed wrong until the print says otherwise.

Why GETTSIM is the complement to the EUROMOD engine path: it is pure Python with
an explicit policy DAG, date-parameterized, deterministic, and free of take-up
randomness — so it is fast (seconds per grid) and reproducible, with no
per-household random draws to neutralize. No licensed microdata is ever needed;
per-case validation uses hypothetical households.

## 1. The adapter

```python
from axiom_oracles.adapters.gettsim import GettsimCase, GettsimRunner

runner = GettsimRunner(policy_date_str="2025-06-30")  # lane default; rules in force 30 Jun 2025

result = runner.compute(
    GettsimCase.single_person({"einnahmen__bruttolohn_m": 4000.0}),
    {"sozialversicherung": {"kranken": {"beitrag": {"betrag_versicherter_m": "health_ee_m"}}}},
)
# {"health_ee_m": [342.0]}  -- one value per person, in p_id order
```

- `GettsimRunner(policy_date_str=..., rounding=True)` — construct once per policy
  date. `rounding=True` (the GETTSIM default) gives statute-exact amounts.
- `runner.compute(case, targets) -> {output_name: [value per person]}` — the flat
  result dict; each value is the per-person column in `p_id` order.
- `runner.run_case(case, targets) -> GettsimRunResult` — the same values plus the
  pinned `gettsim_version` and `policy_date_str` for a reproducible comparison
  row. `.scalar(name)` unwraps a one-person household.
- `runner.run_metadata()` / `runner.gettsim_version` — reproducibility metadata.

`targets` is a nested `tt_targets` tree whose **string leaves name the output
columns** (a `None` leaf is rejected — an oracle needs every output named).

## 2. The verified seed case

A single worker at €4,000/month gross, policy date 2025-06-01 (identical amounts
at the lane date 2025-06-30). The social-insurance legs carry their statutory
arithmetic; the income tax is an engine-pinned regression value (the §32a tariff
plus deduction chain is not hand-derived):

| output (`tt_target`) | leaf | amount |
|---|---|---|
| `sozialversicherung.kranken.beitrag.betrag_versicherter_m` | health | **342.00** = 4,000 × (14.6 % + 2.5 % average Zusatzbeitrag 2025) / 2 |
| `sozialversicherung.rente.beitrag.betrag_versicherter_m` | pension | **372.00** = 4,000 × 18.6 % / 2 (BSV 2018, continued for 2025 by RVBeitrSBek 2025) |
| `sozialversicherung.arbeitslosen.beitrag.betrag_versicherter_m` | unemployment | **52.00** = 4,000 × 2.6 % / 2 |
| `sozialversicherung.pflege.beitrag.betrag_versicherter_m` | long-term care | **96.00** = 4,000 × (3.6 % / 2 + 0.6 % childless surcharge); 3.6 % per PBAV 2025 |
| `einkommensteuer.betrag_y_sn` | income tax (annual) | **6,433** (engine-pinned) |
| `kindergeld.betrag_m`, `solidaritätszuschlag.betrag_y_sn` | Kindergeld / Soli | **0** |

A one-child household (parent + child born 2015, `parents={1: (0, None)}`,
`kindergeld_recipients={1: 0}`) pays the recipient **255.00/month** Kindergeld
at the 2025 dates and **259.00/month** at 2026-01-01 — the two staged amounts of
the Steuerfortentwicklungsgesetz (BGBl. 2024 I Nr. 449, Art. 1/Art. 2 amending
§ 66(1) EStG). The test suite executes *both* dates, which pins the 2025
validation year and proves the date parameterisation end to end.

GETTSIM's float arithmetic leaves ~1e-13 noise (342.00 stored as
341.99999999999994). The adapter tests pin with `abs=1e-6` — wide enough for the
noise, tight enough that a real cent-level regression fails. The comparison
layer's per-concept `tolerance` defaults to **zero** (`comparison/mappings.py`),
so when the DE mappings are wired they must set an explicit cent tolerance
(`tolerance=0.01`) per money concept; nothing applies one automatically.

## 3. API gotchas for suite authors

These are the sharp edges the adapter absorbs; know them before writing a suite.

- **Discover the full template — one uniform route.** The adapter discovers the
  full template once (`MainTarget.templates.input_data_dtypes.tree`, 81 columns
  at the 2025 dates), defaults every column, and overlays the case — "add until
  clean" by construction, and target choice can never change which inputs
  exist. (Per-target templates computed fine in spot probes on 1.2.1, but the
  full template is what the adapter uses and tests.)
- **The mapper is a nested tree.** `InputData.df_and_mapper` wants a nested
  mapper whose leaves are the flat DataFrame column names; a flat `{tuple: name}`
  dict is rejected loudly (`TypeError`: path elements must be strings). The
  adapter builds the nested tree from the template.
- **`tt_targets` leaves are strings that name output columns.** `None` → an
  unnamed column; the adapter rejects `None` leaves, and rejects duplicate
  aliases (GETTSIM returns one column per alias, so a repeated alias would
  silently drop a requested target).
- **Defaults are dtype-first, with value guards — never a `"jahr"` substring
  heuristic.** Several template columns carry `jahr` while being booleans
  (`bürgergeld__bezug_im_vorjahr`) or money amounts
  (`elterngeld__…_vorjahr_y_sn`); defaulting those to a year is wrong. The
  adapter defaults bools to `False`, floats to `0.0`, and special-cases only the
  columns that GETTSIM's table lookups constrain:
  - `alter_beginn_*` are **ages** → 65 (a year overruns the §22 Ertragsanteil
    table, size 121);
  - `jahr_renteneintritt` is a **year** → 2020 (0 underruns the
    Besteuerungsanteil table, indexed `year − 1940`);
  - `steuerklasse` → 1, `mietstufe_hh` → 3 (valid lookup keys).
- **The four demographics resolve jointly, never per column.** `alter`,
  `alter_monate`, `geburtsjahr`, and `geburtsmonat` describe one birth date, so
  the adapter derives the missing ones from whichever the case supplies plus
  the policy date (default: a coherent 40-year-old), and **raises on
  contradictions** — independent per-column defaults would invent a chimera
  person (an `alter=40` adult whose defaulted `alter_monate=0` is a
  benefit-establishing newborn for Elterngeld-class rules).
- **`p_id` links use −1 for "none".** `p_id` is the person's 0-based index; every
  other `p_id…` column (`familie__p_id_ehepartner`,
  `familie__p_id_elternteil_1/2`, `kindergeld__p_id_empfänger`,
  `bürgergeld__p_id_einstandspartner`, …) defaults to −1.
- **Unknown inputs are silently ignored; unknown targets raise.** A mistyped
  input column does nothing (no warning) and yields a defaulted result, so the
  adapter validates every case input path against the template and raises
  `GettsimInputError` first. An unknown target raises GETTSIM's `ValueError`,
  which the adapter wraps as `GettsimTargetError`. No silent zeros either way.
- **Grouping ids: only `hh_id` is an input.** At the 2025 dates GETTSIM derives
  the finer `wthh_id`/`bg_id`/`eg_id`/`fg_id`/`sn_id` from `hh_id` and the family
  links, and warns that the derivation is correct only for one
  Familien-/Bedarfsgemeinschaft per household. For complex households (multiple
  families, self-supporting children) compute those ids externally
  ([gettsim-crazy-grouping-rules](https://github.com/ttsim-dev/gettsim-crazy-grouping-rules))
  and pass them through `GettsimCase(grouping_ids={...})`; the adapter adds them
  as explicit input columns.
- **GETTSIM emits `RuntimeWarning: invalid value encountered in divide`** from
  its internal Midijob-band math even for the seed worker; it is harmless noise,
  not a failure.

## 4. Multi-person households

`GettsimCase.persons` is one input mapping per person (person `i` has `p_id` i);
keys may be qualified (`"einnahmen__bruttolohn_m"`) or nested
(`{"einnahmen": {"bruttolohn_m": 4000.0}}`). The relationship spec drives the
family-link columns:

```python
GettsimCase(
    persons=[
        {"einnahmen__bruttolohn_m": 4000.0, "einkommensteuer__gemeinsam_veranlagt": True},
        {"einkommensteuer__gemeinsam_veranlagt": True},
    ],
    spouse_pairs=[(0, 1)],                 # familie__p_id_ehepartner (set symmetrically)
    # parents={child_idx: (parent1_idx, parent2_idx)}     -> familie__p_id_elternteil_1/2
    # kindergeld_recipients={child_idx: recipient_idx}     -> kindergeld__p_id_empfänger
)
```

A spouse pair links the partners; joint assessment is the separate
`einkommensteuer__gemeinsam_veranlagt` input, so linking never presumes how a
couple files.

## 5. Determinism and version pinning

GETTSIM is deterministic (no random draws), so a case reproduces exactly at a
policy date. The exact `gettsim.__version__` is recorded in every
`GettsimRunResult` and in `run_metadata()`, and the runner **refuses to run** a
version outside `SUPPORTED_GETTSIM_VERSIONS` — the metadata pin alone
(`gettsim==1.2`) leaves the `ttsim-backend` requirement open (`>=1.2`), so only
the `uv.lock` fork pins the full resolution and an ad-hoc install can drift.
Install through the lock (`uv sync --extra gettsim`), and extend
`SUPPORTED_GETTSIM_VERSIONS` only after re-validating the pinned expectations.

**Version quirk.** The installable PyPI distribution is `gettsim==1.2`, but
`gettsim.__version__` reports `"1.2.1"` (the `ttsim-backend` engine version it
re-exports). The extra therefore pins `gettsim==1.2` (the distribution), while
`run_metadata()["gettsim_version"]` shows `"1.2.1"` — pin the distribution, read
the reported version.

**Dependency conflict.** GETTSIM's `ttsim-backend` transitively conflicts with
the PolicyEngine dependency tree, so `pyproject.toml` declares the `gettsim`
extra as conflicting with the `policyengine` and `taxsim` extras
(`[tool.uv] conflicts`). `uv` locks each fork separately, so nothing ever
installs both; run German comparisons in a dedicated
`uv sync --extra gettsim` environment (GETTSIM installs cleanly on the repo's
Python 3.13 and 3.14 — the conflict is with PolicyEngine, not a Python
version). The main CI job syncs `[dev]`; the dedicated `gettsim-live` CI job
syncs the gettsim fork and runs the live adapter tests, so a broken adapter
cannot ride in on skips.

## 6. Germany dual-oracle suite (realized)

The direct `de-worker-dual-oracle` lane is now registered and published. It
compares EUROMOD DE_2025 directly with GETTSIM 1.2.1 over the canonical
13-household worker grid; it is an oracle cross-check, not an Axiom conformance
claim, so its generated affected-map entry deliberately has no rulespec edge.

- `axiom_oracles/suites/de_worker.py` owns the shared case grid and the
  engine-specific projections.
- `axiom_oracles/config/concept_mappings.yaml` maps the four monthly employee
  contribution legs, annual income tax including Soli, and monthly Kindergeld
  at a one-cent absolute tolerance.
- `comparisons/de-worker-dual-oracle.yaml` selects the registered
  `gettsim-synthetic-compare` runner. The process hosting the runner has
  GETTSIM installed; the existing EUROMOD adapter delegates to
  `EUROMOD_PYTHON`.
- `dashboard/public/data/euromod-gettsim-de-worker-dual-oracle.json` is the
  committed live evidence. Hosts without both optional engines re-emit that
  report, while unsupported installed engine versions still fail loudly.
- `dispositions/de-worker-dual-oracle.yaml` records the three filed upstream
  model findings. The repository's schema calls these
  `upstream_engine_gap`; the evidence and issue link identify the model at
  fault.

The detailed engine contract, reductions, reproducible run command, and filed
findings are in `docs/de-dual-oracle-playbook.md`. A future Axiom DE encoding
can add a separate conformance comparison against these baselines without
changing this direct cross-oracle lane.

## Dependency

GETTSIM is an optional heavy dependency, imported lazily. Install it through
the locked fork (a bare `uv pip install` bypasses `uv.lock` and can drift the
`ttsim-backend` engine under the same distribution pin):

```bash
uv sync --extra gettsim --extra dev
```

Tests that need it are gated with a `skipif` marker on import availability and
skip cleanly when it is absent; the projection, defaulting, and input-guard
logic are pure and tested without it. The `gettsim-live` CI job runs the gated
tests with the fork installed.
