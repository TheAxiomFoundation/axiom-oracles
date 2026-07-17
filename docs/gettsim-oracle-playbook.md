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
at the lane date 2025-06-30), all four social-insurance legs statute-exact by
hand:

| output (`tt_target`) | leaf | amount |
|---|---|---|
| `sozialversicherung.kranken.beitrag.betrag_versicherter_m` | health | **342.00** (8.55% incl. half the average Zusatzbeitrag) |
| `sozialversicherung.rente.beitrag.betrag_versicherter_m` | pension | **372.00** (9.3%) |
| `sozialversicherung.arbeitslosen.beitrag.betrag_versicherter_m` | unemployment | **52.00** (1.3%) |
| `sozialversicherung.pflege.beitrag.betrag_versicherter_m` | long-term care | **96.00** (2.4% childless) |
| `einkommensteuer.betrag_y_sn` | income tax (annual) | **6,433** |
| `kindergeld.betrag_m`, `solidaritätszuschlag.betrag_y_sn` | Kindergeld / Soli | **0** |

A one-child household (parent + child, `parents={1: (0, None)}`,
`kindergeld_recipients={1: 0}`) pays the recipient **255.00/month** Kindergeld at
the 2025 date (the 2026 amount is 259.00 — the value moves with the policy date,
so pinning 255.00 pins the 2025 validation year).

GETTSIM's float arithmetic leaves ~1e-13 noise (342.00 stored as
341.99999999999994), so pin expectations with a cent tolerance
(`pytest.approx(..., abs=0.01)`), which is the tolerance the comparison layer
applies anyway.

## 3. API gotchas for suite authors

These are the sharp edges the adapter absorbs; know them before writing a suite.

- **Discover the full template, not per-target templates.** GETTSIM's per-target
  input templates miss transitive dependencies. The adapter discovers the full
  template once (`MainTarget.templates.input_data_dtypes.tree`, 81 columns at the
  2025 dates), defaults every column, and overlays the case — "add until clean"
  by construction. Requesting a deep target (e.g. Bürgergeld) then needs no
  hand-added inputs.
- **The mapper is a nested tree.** `InputData.df_and_mapper` wants a nested
  mapper whose leaves are the flat DataFrame column names; a flat `{tuple: name}`
  dict silently maps almost nothing. The adapter builds it from the template.
- **`tt_targets` leaves are strings that name output columns.** `None` → an
  unnamed column; the adapter rejects `None` leaves.
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
  - `steuerklasse` → 1, `mietstufe_hh` → 3 (valid lookup keys);
  - `geburtsjahr` and `alter` are case demographics (defaults 1980 / 40).
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
`GettsimRunResult` and in `run_metadata()`; the `gettsim` extra pins the version
(`pyproject.toml`), and the seed amounts above are verified against it.

**Version quirk.** The installable PyPI distribution is `gettsim==1.2`, but
`gettsim.__version__` reports `"1.2.1"` (the `ttsim-backend` engine version it
re-exports). The extra therefore pins `gettsim==1.2` (the distribution), while
`run_metadata()["gettsim_version"]` shows `"1.2.1"` — pin the distribution, read
the reported version.

**Dependency conflict.** GETTSIM's `ttsim-backend` transitively conflicts with
the PolicyEngine dependency tree, so `pyproject.toml` declares the `gettsim`
extra as conflicting with the `policyengine` and `taxsim` extras
(`[tool.uv] conflicts`). `uv` locks each fork separately and CI only syncs
`[dev]`, so nothing ever installs both; run German comparisons in a dedicated
`uv sync --extra gettsim` environment (GETTSIM installs cleanly on the repo's
Python 3.13 and 3.14 — the conflict is with PolicyEngine, not a Python version).

## 6. Wiring a DE comparison suite (follow-up, once encodings exist)

No DE encodings exist yet, so this adapter ships **without** comparison suites or
registry entries — adapter + tests only. When `rulespec-de` lands its first
instrument, wire the dual-oracle comparison the way the EUROMOD playbook
describes (§6 there): add durable-id concepts in `core/case.py` pointing at the
rulespec modules, map them to GETTSIM `tt_target` leaves *and* EUROMOD output
columns in `comparison/mappings`, add a `de-worker-*` synthetic suite over the
income grid the encoding exercises, and record model findings (GETTSIM →
`iza-institute-of-labor-economics/gettsim`; EUROMOD →
`ec-jrc/JRC-EUROMOD-software-source-code`) versus encoding findings (on
`rulespec-de`). The single-worker seed and the Kindergeld case in
`tests/test_gettsim_adapter.py` are the ready anchors for the first
income-tax/SSC and family-benefit suites.

## Dependency

GETTSIM is an optional heavy dependency, imported lazily. Install the extra only
to run German comparisons:

```bash
uv pip install -e ".[gettsim,dev]"
```

Tests that need it use `pytest.importorskip("gettsim")` and skip cleanly when it
is absent; the projection, defaulting, and input-guard logic are pure and tested
without it.
