# Lane S2 — Belgian merged-pipeline suites

Run date: 2026-08-22 (Europe/Brussels). Worktree:
`~/TheAxiomFoundation/_cape-prep/oracles-suites`; branch:
`be-suites-pensions-selfemp-unemployment`. This lane had no successful network
access and made no pushes, RuleSpec edits, or ledger edits.

## Outcome

Registered and ran three genuine per-case EUROMOD/Axiom suites:

- `be-pensioner-pit`: four cases, ten comparisons, nine raw matches, one
  dispositioned mismatch, no errors, no unexplained residuals.
- `be-self-employment-pit`: five cases, five comparisons, two raw matches,
  three dispositioned mismatches, no errors, no unexplained residuals.
- `be-replacement-income-pit`: five cases, nine comparisons, eight raw
  matches, one dispositioned mismatch, no errors, no unexplained residuals.

The command that produced those counts and the exact observed residuals was:

```sh
jq -s 'map({suite,case_count,comparison_count:.summary.comparison_count,match_count:.summary.match_count,mismatch_count:.summary.mismatch_count,error_count:.summary.error_count,mismatches:(.mismatches|map({case_id,left,right,difference}))})' \
  /private/tmp/lane-s2-pension-raw.json \
  /private/tmp/lane-s2-selfemp-raw.json \
  /private/tmp/lane-s2-replacement-raw.json
```

```json
[
  {"suite":"be-pensioner-pit","case_count":4,"comparison_count":10,"match_count":9,"mismatch_count":1,"error_count":0,"mismatches":[{"case_id":"be-pensioner-pit-pension-30k-wage-15k","left":6051.513079980725,"right":6403.811847106921,"difference":-352.29876712619625}]},
  {"suite":"be-self-employment-pit","case_count":5,"comparison_count":5,"match_count":2,"mismatch_count":3,"error_count":0,"mismatches":[{"case_id":"be-self-employment-pit-yse-25k","left":2030.3371518803276,"right":2093.4331518803265,"difference":-63.09599999999887},{"case_id":"be-self-employment-pit-yem-30k-yse-20k","left":10507.62779506539,"right":10466.620891910272,"difference":41.00690315511747},{"case_id":"be-self-employment-pit-negative-yse-1k-yem-10k","left":7000.0,"right":6000.0,"difference":1000.0}]},
  {"suite":"be-replacement-income-pit","case_count":5,"comparison_count":9,"match_count":8,"mismatch_count":1,"error_count":0,"mismatches":[{"case_id":"be-replacement-income-pit-bun-15k-yem-15k","left":1163.0377081352365,"right":1690.24372540135,"difference":-527.2060172661136}]}
]
```

Across the lane that is fourteen cases and twenty-four comparisons: nineteen
raw matches and five schema-validated dispositions. The addition is therefore
100% explained with zero unexplained comparisons; it does not manufacture
matches by widening the EUR 0.01 amount tolerance.

## Binding and release frontier

The lane began at axiom-oracles `93e8748a319fc209ecd39fef6637ffec65c16d67`.
The shared `origin/main` ref advanced independently while the detached lane was
running; this branch was intentionally not rebased because Fable integrates it.

```sh
git log -1 --format='%H %cI %s' 93e8748a319fc209ecd39fef6637ffec65c16d67
git merge-base HEAD 93e8748a319fc209ecd39fef6637ffec65c16d67
git reflog show --date=iso origin/main -5
```

The executable bindings used for every Axiom-side value were:

```sh
git -C /private/tmp/lane-s2-rulespec-parent/rulespec-be rev-parse HEAD
git -C /Users/maxghenis/TheAxiomFoundation/_cape-prep-engine rev-parse HEAD
shasum -a 256 /Users/maxghenis/TheAxiomFoundation/_cape-prep-engine/target/release/axiom-rules-engine
```

```text
b105e2b3a3086ddd2de447d58a9b951346870dd1
c6cc389a8f5e7238019e4fa06849325fad9acd46
9452599c5ef641a30ded4ab65ced19cdfc054a667582b62ad33577a8ad787a1f  .../axiom-rules-engine
```

The RuleSpec checkout was detached at the merged main fixture commit, not at
the original P/S/U lane heads. A direct comparison of every supplied Person
record against the named fixture `input` map produced no mismatches:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 - <<'PY'
from pathlib import Path
import json, yaml
from axiom_oracles.suites import load_suite

root = Path('/private/tmp/lane-s2-rulespec-parent/rulespec-be')
result = {}
for suite in ('be-pensioner-pit', 'be-self-employment-pit',
              'be-replacement-income-pit'):
    counts, mismatches = [], []
    for case in load_suite(suite):
        rel, name = case.metadata['rulespec_fixture'].split('#', 1)
        fixture = next(row for row in yaml.safe_load((root / rel).read_text())
                       if row['name'] == name)
        records = {row['name']: row['value']
                   for row in case.metadata['axiom_input_records']}
        counts.append(len(records))
        if records != fixture['input']:
            mismatches.append(case.case_id)
    result[suite] = {'cases': len(counts),
                     'record_counts': sorted(set(counts)),
                     'mismatches': mismatches}
print(json.dumps(result, sort_keys=True))
PY
```

```json
{"be-pensioner-pit":{"cases":4,"mismatches":[],"record_counts":[19]},"be-replacement-income-pit":{"cases":5,"mismatches":[],"record_counts":[19]},"be-self-employment-pit":{"cases":5,"mismatches":[],"record_counts":[29]}}
```

All fourteen cases use Person input records. These single-person pipelines need
no relations:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 - <<'PY'
import json
from axiom_oracles.suites import load_suite
for suite in ('be-pensioner-pit','be-self-employment-pit',
              'be-replacement-income-pit'):
    cases=load_suite(suite)
    print(json.dumps({'suite':suite,'cases':len(cases),
      'record_entities':sorted({r['entity'] for c in cases
                                for r in c.metadata['axiom_input_records']}),
      'relation_counts':sorted({len(c.metadata.get('axiom_relations',[]))
                                for c in cases}),
      'comparison_surfaces':sum(len(c.outputs) for c in cases)},sort_keys=True))
PY
```

```text
{"cases": 4, "comparison_surfaces": 10, "record_entities": ["Person"], "relation_counts": [0], "suite": "be-pensioner-pit"}
{"cases": 5, "comparison_surfaces": 5, "record_entities": ["Person"], "relation_counts": [0], "suite": "be-self-employment-pit"}
{"cases": 5, "comparison_surfaces": 9, "record_entities": ["Person"], "relation_counts": [0], "suite": "be-replacement-income-pit"}
```

The campaign release frontier was enforced:

- Draft #122 dependants were not imported or used.
- The reverted Article 171/capital-income surface was not registered. `yiy`
  was re-probed, but no Axiom parity claim was made.
- Lane U's current sickness oracle uses `bhl`; `pdi` changes disability/TFA
  semantics and legacy `phl` is not the resolved current income-list input.
  Both were re-probed but were not substituted for `bhl`.
- Pension cases use `poa`, whose live factor is exactly 1.0.

## EUROMOD input uprating

The installed EUROMOD J2.0+ BE_2025 model was re-probed in this lane. The
command created one 1,000-unit monthly-input row per variable, ran
`BE_2024_c1_2015_03_e2`, and divided the returned variable by 1,000:

```sh
arch -x86_64 env PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
  DOTNET_ROOT=/Users/maxghenis/.dotnet-x64 \
  PYTHONNET_RUNTIME=coreclr POLARS_SKIP_CPU_CHECK=1 \
  /Users/maxghenis/.venvs/axiom-euromod-x64/bin/python - <<'PY'
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import numpy as np
import pandas as pd
from euromod import Model

root = Path('/Users/maxghenis/Downloads/EUROMOD_J2.0/EUROMOD_RELEASES_J2.0+')
with (root / 'Input/BE_training_data.txt').open(encoding='utf-8') as stream:
    columns = [x.strip() for x in stream.readline().rstrip('\n').split('\t')
               if x.strip()]
if 'bhl' not in columns:
    columns.append('bhl')
names = ('yem', 'yse', 'bun', 'pdi', 'phl', 'bhl', 'yiy', 'poa')
frame = pd.DataFrame(np.zeros((len(names), len(columns)), dtype=np.float64),
                     columns=columns)
for row, name in enumerate(names):
    values = {
      'idhh':row+1,'idperson':(row+1)*100+1,'idpartner':0,'idmother':0,
      'idfather':0,'dag':45,'dgn':1,'ddi':1 if name=='pdi' else 0,
      'dms':1,'drgn1':0,'dwt':1,
      'les':3 if name in ('yem','yse') else (5 if name=='bun' else 6),
      'lfs':15 if name=='yem' else 0,'lhw':38 if name=='yem' else 0,
      'liwmy':12 if name=='yem' else 0,'liwwh':120 if name=='yem' else 0,
      'loc':5,'lunmy':12 if name=='bun' else 0,
      'bunmy':12 if name=='bun' else 0,'pdimy':12 if name=='pdi' else 0,
      'yemmy':12 if name=='yem' else 0,name:1000}
    for key, value in values.items():
        frame.loc[row, key] = float(value)
model = Model(str(root))
country = next(x for x in model.countries if x.name == 'BE')
system = next(x for x in country.systems if x.name == 'BE_2025')
with redirect_stdout(StringIO()):
    simulation = system.run(frame, 'BE_2024_c1_2015_03_e2', verbose=False,
      nowarnings=True, requested_vargroups=[], requested_ilgroups=[],
      suppress_other_output=False)
out = simulation.outputs[0].sort_values('idperson').reset_index(drop=True)
print(json.dumps({'errors':[str(x) for x in simulation.errors],
  'factors':{name:float(out.loc[row,name])/1000.0
             for row,name in enumerate(names)}},
  sort_keys=True,separators=(',',':')))
PY
```

```json
{"errors":["Variable(s) yds, lindi, yptmp, tad, tis not found in user-provided lists (zero is used as default)","2.1 uprate_be/Uprate (43a9959d-ec21-446c-9223-8d69af445b1b): variable(s) bunpe01, bunpe02, xcc, yempv, yiyitdp is/are uprated with default factor (1.050524934383202)"],"factors":{"bhl":1.1096513390601312,"bun":1.0793082886106142,"pdi":1.1096513390601312,"phl":1.1096513390601312,"poa":1.0,"yem":1.055022392834293,"yiy":1.0710267229254573,"yse":1.055022392834293}}
```

The two connector warnings are nonfatal and are recorded rather than hidden.
Each synthetic raw monthly input is divided by its own observed factor before
the post-uprating output is bridged into the Axiom Person record. The code uses
`yem/yse=1.055022392834293`, `bun=1.0793082886106142`,
`bhl=1.1096513390601312`, and `poa=1.0` for the surfaces that crossed this
release frontier.

## Implementation

The lane adds:

- Seven legal concept mappings: pension final PIT, pension social withholding,
  pension reduction, unemployment reduction, sickness/invalidity reduction,
  self-employment final PIT, and combined worker/self-employment taxable income.
- Three suite builders in `axiom_oracles/suites/be_worker.py`, their registry
  entries, comparison configs, and per-case output declarations.
- `euromod_extra_columns` plumbing so `drgn1` and current-variable `bhl` can be
  present even when the legacy training template omits them.
- Per-case comparison projection in the shared CLI. Legacy all-output suites,
  explicit concept/category requests, and `--include-components` retain their
  former behavior; explicitly unsupported per-case surfaces project to zero.
- Three disposition files plus exact served dashboard mirrors.
- Generated grid, affected-map, dashboard manifest/freshness/overview,
  exercise census, BE coverage rollup, and zero-unexplained ratchet pins.

The registry/report inventory changed as follows. This command parses the base
and current registry rather than inferring counts from filenames alone:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 - <<'PY'
import ast, subprocess, yaml
from pathlib import Path
base='93e8748a319fc209ecd39fef6637ffec65c16d67'

def available_count(source):
    tree=ast.parse(source)
    fn=next(n for n in tree.body
            if isinstance(n,ast.FunctionDef) and n.name=='available_suites')
    ret=next(n for n in ast.walk(fn) if isinstance(n,ast.Return))
    return len(ast.literal_eval(ret.value))

def registry_count(ref):
    names=subprocess.check_output(
        ['git','ls-tree','-r','--name-only',ref,'comparisons'],text=True
    ).splitlines()
    count=0
    for name in names:
        if not name.startswith('comparisons/be-') or not name.endswith('.yaml'):
            continue
        doc=yaml.safe_load(subprocess.check_output(
            ['git','show',f'{ref}:{name}'],text=True)) or {}
        if (doc.get('runner') or {}).get('type')=='euromod-synthetic-compare':
            count += 1
    return count

before_source=subprocess.check_output(
    ['git','show',f'{base}:axiom_oracles/suites/__init__.py'],text=True)
after_source=Path('axiom_oracles/suites/__init__.py').read_text()
before_reports=[n for n in subprocess.check_output(
    ['git','ls-tree','-r','--name-only',base,'dashboard/public/data'],text=True
).splitlines() if n.startswith('dashboard/public/data/axiom-euromod-be-')
                and n.endswith('.json')]
after_reports=list(Path('dashboard/public/data').glob('axiom-euromod-be-*.json'))
print({'before':{'available_suites':available_count(before_source),
                 'be_euromod_registry':registry_count(base),
                 'be_dashboard_reports':len(before_reports)},
       'after':{'available_suites':available_count(after_source),
                'be_euromod_registry':sum(
                    1 for p in Path('comparisons').glob('be-*.yaml')
                    if ((yaml.safe_load(p.read_text()) or {}).get('runner') or {})
                       .get('type')=='euromod-synthetic-compare'),
                'be_dashboard_reports':len(after_reports)}})
PY
```

```text
{'before': {'available_suites': 65, 'be_euromod_registry': 9, 'be_dashboard_reports': 30}, 'after': {'available_suites': 68, 'be_euromod_registry': 12, 'be_dashboard_reports': 33}}
```

The generated Belgian grid count was produced by:

```sh
python3 - <<'PY'
import yaml
x=yaml.safe_load(open('grids/be.yaml'))
print(len(x['case_sets']))
print(sum(len(row['cases']) for row in x['case_sets'].values()))
PY
```

```text
33
142
```

## Live comparison and report provenance

Plain EUROMOD execution works in this sandbox. Each suite was run through the
real comparison CLI with `sample-size=0` and the pinned RuleSpec/engine. The
three actual invocations differed only in `SUITE` and `OUT`:

```sh
PYTHONPATH=. \
EUROMOD_PYTHON=/Users/maxghenis/.venvs/axiom-euromod-x64/bin/python \
DOTNET_ROOT=/Users/maxghenis/.dotnet-x64 \
PYTHONNET_RUNTIME=coreclr POLARS_SKIP_CPU_CHECK=1 \
EUROMOD_MODEL_ROOT=/Users/maxghenis/Downloads/EUROMOD_J2.0/EUROMOD_RELEASES_J2.0+ \
EUROMOD_COUNTRY=BE EUROMOD_SYSTEM=BE_2025 \
EUROMOD_DATASET=BE_2024_c1_2015_03_e2 \
EUROMOD_TEMPLATE_DATASET=BE_training_data \
EUROMOD_EXTRA_COLUMNS=drgn1,bhl \
AXIOM_RULESPEC_REPO_ROOTS=/private/tmp/lane-s2-rulespec-parent \
python3 -m axiom_oracles.cli compare euromod axiom \
  --population synthetic --suite "$SUITE" --report-suite "$SUITE" \
  --sample-size 0 --period 2025 \
  --axiom-engine-binary /Users/maxghenis/TheAxiomFoundation/_cape-prep-engine/target/release/axiom-rules-engine \
  --output "$OUT"

# SUITE=be-pensioner-pit;          OUT=/private/tmp/lane-s2-pension-raw.json
# SUITE=be-self-employment-pit;    OUT=/private/tmp/lane-s2-selfemp-raw.json
# SUITE=be-replacement-income-pit; OUT=/private/tmp/lane-s2-replacement-raw.json
```

The registry wrapper could not complete its nested `uv` environment resolution
without network access. I did not hand-edit result values. The genuine raw CLI
reports were passed through the repository's standard `_build_run_provenance`,
`_stamp_report_provenance`, `_adapt_to_v2`, and `_write_dashboard_report`
helpers. Consequently `run_kind` is honestly `manual`, not a fabricated
registry run. There is no `reemitted_report` marker.

The canonical committed dashboard reports have this provenance:

```sh
jq -s 'map({suite,generated_by:.provenance.generated_by,run_kind:.provenance.run_kind,rulespec:.provenance.rulespecs[0].sha,engine:.provenance.engine.axiom_rules_engine_sha,binary_sha256:.provenance.engine.binary_sha256,oracle:.provenance.oracle,error_count:.summary.error_count,unexplained:.summary.dispositioned.unexplained_count})' \
  dashboard/public/data/axiom-euromod-be-pensioner-pit.json \
  dashboard/public/data/axiom-euromod-be-self-employment-pit.json \
  dashboard/public/data/axiom-euromod-be-replacement-income-pit.json
```

All three report rows returned RuleSpec `b105e2b3a3086ddd2de447d58a9b951346870dd1`,
engine `c6cc389a8f5e7238019e4fa06849325fad9acd46`, binary SHA-256
`9452599c5ef641a30ded4ab65ced19cdfc054a667582b62ad33577a8ad787a1f`,
EUROMOD `J2.0+/BE_2025/BE_2024_c1_2015_03_e2`, `error_count=0`, and
`unexplained=0`.

Canonical report hashes:

```sh
shasum -a 256 dashboard/public/data/axiom-euromod-be-{pensioner-pit,self-employment-pit,replacement-income-pit}.json
```

```text
85f225f912bd964684e1192c2c6452f934585364f0865499eb436b84dcaffadb  dashboard/public/data/axiom-euromod-be-pensioner-pit.json
3e1e6949a65708530ab29e062f3c32242c8f926540597de3e23e11f6067b9662  dashboard/public/data/axiom-euromod-be-self-employment-pit.json
b45f3fe27e7fcd47924a48b7b0ded305707bd190908d4534fd5a02cae801a73c  dashboard/public/data/axiom-euromod-be-replacement-income-pit.json
```

The conventional dated full reports also remain locally as reproducibility
evidence. They are excluded by the worktree's `.git/info/exclude` `reports`
rule, matching the #487/#500 precedent in which the canonical dashboard report
is committed:

```sh
shasum -a 256 reports/axiom-euromod-be-{pensioner-pit,self-employment-pit,replacement-income-pit}-0-2026-08-22.json
git check-ignore -v reports/axiom-euromod-be-pensioner-pit-0-2026-08-22.json
```

```text
624af8f1cc5e671cf43b8503e2ad0ba774ccbd9e58e7d94c13e1e6455a05bc05  reports/axiom-euromod-be-pensioner-pit-0-2026-08-22.json
82f36e9e5e5e3961c7d08cf9d6781903072be1436dcd9de83353ae0adc843821  reports/axiom-euromod-be-self-employment-pit-0-2026-08-22.json
f7b72c77e9d59000f15d715eaa19d855dcb2148c3587fbf4791deeefba225cdc  reports/axiom-euromod-be-replacement-income-pit-0-2026-08-22.json
.../.git/info/exclude:9:reports reports/axiom-euromod-be-pensioner-pit-0-2026-08-22.json
```

## Residual dispositions

Residual is EUROMOD minus Axiom throughout.

- Pension mixed case: `+124.261060873803` from JRC #26's
  `il_netYem`/pension-withholding forfait base, plus `-476.559828` from the
  existing JRC #12 uncapped work-bonus credit, equals
  `-352.298767126197` (observed `-352.29876712619625`).
- Self-employment 25k: JRC #24 subtracts the EUR 880 credit before the 7.17%
  communal addition: `-(880 * 0.0717) = -63.096` (observed
  `-63.09599999999887`).
- Mixed worker/self-employment: the named base mechanisms produce a
  `-1454.6358` taxable-base difference; its fixed-credit tax effect is
  `+701.5202884247187`, JRC #12 contributes `-552.615720`, and JRC #24
  contributes `-(1504.848888 * 0.0717)`. The sum is
  `+41.0069031551187` (observed `+41.00690315511747`).
- Negative self-employment: installed `neg_be/Max` clips requested
  `yse=-1000` to zero, so EUROMOD retains EUR 7,000 taxable worker income while
  merged RuleSpec Article 23 nets the EUR 1,000 current-period activity loss to
  EUR 6,000. Named mechanism: `7000 - 6000 = +1000`.
- Mixed unemployment/wage: JRC #25 contributes
  `-(163.9032131147541 - 96.41365477338476) * 0.75043 =
  -50.64618926611379`; JRC #12 contributes `1028.28906 - 1504.848888 =
  -476.559828`; the sum is `-527.20601726611379` (observed
  `-527.2060172661136`).

Those quantities are executable `arithmetic` rows in the three disposition
YAMLs, not prose-only rationalizations. The validator command and result were:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 scripts/apply_dispositions.py --check
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 scripts/emit_disposition_artifacts.py --check \
  be-pensioner-pit be-self-employment-pit be-replacement-income-pit
```

```text
Validated 97 dispositions files
Dispositions are consistent with the committed dashboard data
disposition-artifacts OK: 3 suites, 5 entries, exact YAML parity
```

The validator also printed two unrelated pre-existing expiry notes for
`be-worker-ssc` and `co-tax-intersection-taxsim`; neither is a Lane S2 entry.

## Scoreboards

The before/after Belgian dispositioned-parity rollup was produced from the base
blob and working tree with:

```sh
jq -s '{before: .[0].dispositioned_parity, after: .[1].dispositioned_parity}' \
  <(git show 93e8748a319fc209ecd39fef6637ffec65c16d67:axiom_oracles/data/euromod_be_coverage.json) \
  axiom_oracles/data/euromod_be_coverage.json
```

```text
before: 30 suites, 132 comparisons, 97 matches, raw 73.484848%, explained 100%, unexplained 0
after:  33 suites, 156 comparisons, 116 matches, raw 74.358974%, explained 100%, unexplained 0
```

The conformance universe itself did not change. This command produced the same
BE row before and after:

```sh
jq -s '{before:(.[0].jurisdictions[]|select(.jurisdiction=="be")),after:(.[1].jurisdictions[]|select(.jurisdiction=="be"))}' \
  <(git show 93e8748a319fc209ecd39fef6637ffec65c16d67:conformance/scoreboard.json) \
  conformance/scoreboard.json
```

```text
BE: 23 policies in scope, 23 covered, 100%; 20 excluded; unexplained 0; Axiom-attributed open 0; conformant true
```

## Gates

### Required pytest command

The exact requested command failed before collection because this sandbox may
not write the configured uv cache:

```sh
uv run --with pytest pytest -q
```

```text
error: Failed to initialize cache at `/Users/maxghenis/.cache/uv`
  Caused by: failed to open file `/Users/maxghenis/.cache/uv/sdists-v9/.git`: Operation not permitted (os error 1)
```

A retry with a writable cache also failed before collection because the no-
network sandbox could not resolve a missing wheel:

```sh
UV_CACHE_DIR=/private/tmp/lane-s2-uv-cache uv run --with pytest pytest -q
```

```text
Failed to download requests==2.33.1 ... files.pythonhosted.org ... dns error
```

The final focused fallback, using the already-installed system environment,
ran after all code fixes:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 -m pytest -q \
  tests/test_case_schema.py tests/test_run_comparison.py \
  tests/test_package_targets.py tests/test_case_grids.py \
  tests/test_unexplained_ratchet.py
```

```text
252 passed in 31.87s
```

A broad offline fallback excluded the two very slow certificate mutation/commit
refresh files and explicitly deselected three environment-bound failures
described below:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 -m pytest -q \
  --ignore=tests/test_certification_mutants.py \
  --ignore=tests/test_commit_refreshed_report.py \
  --deselect=tests/test_dashboard_loader.py::test_loader_equivalence \
  --deselect=tests/test_dk_comparison_config.py::test_dk_certificate_artifact_check_is_hermetic \
  --deselect=tests/test_entitledto_report.py::test_pe_reference_reproduces_from_policyengine
```

```text
2705 passed, 73 skipped, 3 deselected, 5 warnings in 147.19s
```

Before the ratchet pins were regenerated, the same narrowed run reported four
failures, 2,704 passes and 73 skips: one real Lane S2 failure was the absence of
the three new suite names from `conformance/unexplained-ratchet.yaml`. The
generator added all three at ceiling zero; `tests/test_unexplained_ratchet.py`
then passed 8/8. The other three failures were:

1. `npx esbuild` attempted a network download and received `ENOTFOUND`.
2. The DK certificate check could not rederive the DE certificate census on
   macOS.
3. The installed PolicyEngine-UK version lacks the pinned
   `council_tax_reduction` variable.

An unfiltered system-Python fallback was also attempted and manually stopped at
61% after 1,024.45 seconds because the certificate-mutant closure tests take
roughly two minutes each in this environment. At interruption it reported six
failures, 1,834 passes, and 38 skips. This was an interrupted diagnostic, not a
completed test-suite result. Its failures were the same certificate-chain
mechanism plus the then-stale exercise-census binding.

### Certificate architecture failure

The certificate failure is flat and reproducible:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 scripts/de_certificate_census.py --check
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 scripts/certify.py --check
```

```text
DE certificate census drifted
ValueError: DE certificate census does not rederive
```

The named mechanism is an architecture/OS mismatch, not an unexplained Lane S2
numeric residual. Even an x86_64 Python with Ed25519 support receives:

```text
release-binary-replay-receipt: cannot execute pinned release command:
[Errno 8] Exec format error: .../axiom-rules-engine-x86_64-unknown-linux-gnu/axiom-rules-engine
```

The embedded verifier is a Linux x86_64 binary; this macOS sandbox has no
available Linux runtime. Fable must refresh/check that certificate chain on a
Linux x86_64 integration runner after applying the exercise-census change.

### Static and generated gates

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m ruff check .
git diff --check
python3 scripts/extract_grids.py --check
python3 scripts/generate_affected_map.py --check
python3 scripts/check_vacuous_gate.py --check
python3 scripts/generate_dashboard_overview.py --check
python3 scripts/generate_conformance_universe.py --all --check
python3 scripts/generate_conformance_compositions.py --all --check
python3 scripts/conformance_scoreboard.py --check
python3 scripts/exercise_census.py --check
python3 scripts/conformance_burndown.py --check
python3 scripts/conformance_ratchet.py --check
python3 scripts/unexplained_ratchet.py --check
```

```text
All checks passed!
Grids up to date.
affected_map OK: 185 suites, 196 suite-repo edges
vacuous-gate OK: 149 configs oracle-backed; 226 suites, 34 executable surfaces, 69 suite(s) awaiting provenance
overview OK: 227 reports bundled
conformance[be] OK: 43 policies (23 in scope, 20 excluded) match EUROMOD_J2.0/BE_2025
conformance compositions[be] OK: 23 covered suite(s)
conformance scoreboard OK: 6 jurisdiction(s), 4 conformant
exercise census up to date
conformance burn-down OK: 6 series, 185 point(s)
conformance ratchet OK: 6 jurisdiction(s), no invariant regressed
unexplained ratchet OK: 138 suites gated, 644 unexplained within pinned ceilings
```

The all-jurisdiction universe command additionally verified UK, DK, and the
Yale tariff spine. It cleanly no-op'd the locally version-mismatched UK/US
PolicyEngine checkouts as designed; BE was freshly verified against the
installed EUROMOD model. Composition regeneration made no textual change to
`conformance/compositions/be.yaml`, because the existing 23-policy coverage
was already complete; the check nevertheless rederived it against the expanded
suite registry.

## Handoff

The branch is committed locally for Fable to integrate and push. No push was
attempted here. The only integration-runner follow-up is the Linux x86_64
certificate-chain refresh/check described above; all Lane S2 comparison,
disposition, registry, grid, universe, scoreboard, ratchet, ruff, and focused
test gates are complete.

LANE S2 DONE
