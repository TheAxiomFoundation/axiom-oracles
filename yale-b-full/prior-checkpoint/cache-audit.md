# Current campaign cache audit and exposure priority

This audit did not alter campaign source, receipts, manifests, rulespec source, or the default cache. It read `/Users/maxghenis/TheAxiomFoundation/CLAUDE.md` and the prior lane's `yale-1383-run/RESULT.md` first. All new files are under this workspace's `yale-full-run/`.

## Observed cache results

- Current `_shard_key` with baseline rulespec `96d5e7c1e6309dc205b7320bbddaae8dd5d410df`, the required engine, and main's committed input contract matches **0/100** committed manifest keys.
- Recomputing those exact same ingredients with the historical input-contract bytes immediately before #510 gives **100/100** matching keys. This is a diagnostic computation only: no historical receipt was installed and no shard was rekeyed.
- **100/100** default-cache shard files exist and pass the committed SHA-256, totaling **722,142,701 bytes**. This validation took 4.332 seconds.
- The historical input contract's entry-flag tool SHA-256 equals baseline source exactly: `d3f4b26e062e99349f656f7d9e39521db2897d565f5335e59e21b9aae7a5cc90`.
- Current committed input-contract SHA-256: `bdd258d7e86a81d4ffd472149d14033b75c11ceb490ae13685592c06475da717`.
- Historical input-contract SHA-256: `48f9caf2ad8461035007a1ee3b0d38968abc4c3da6239d5383631bae9de2ba29`.

`git show 6ce2e6743 -- reference/us-tariff-schedule/declared-input-contract-receipt.json` shows #510 added the alias map and observed aliases, changed the tool SHA from `d3f4b26e...` to `8032dde5...`, and changed `stage_wall_clock_seconds` from 7.673 to 8.677. Its changed-file list does not include `eval/MANIFEST.json`.

The cache mechanism is `scripts/us_tariff_schedule_campaign.py:728`: keys include the entire input-contract receipt hash, selected CSV hash, routing artifact hash, chapter wrapper hash, engine binary hash, requested output names, and chapter. `main():2143` appends measured `stage_wall_clock_seconds` to the input-contract receipt. Thus even a semantically identical input-contract CLI rerun with a different duration invalidates every shard key. Prepass timing is not a key ingredient; only its routing artifact is.

`evaluate_campaign():827` accepts a resume shard only when the newly computed key exists in the manifest and its path passes its recorded SHA-256. It never searches cache contents for semantic equivalents. Neither A nor B can claim a current full evaluate-stage resume using the committed receipt. The verified old shards remain usable as explicitly labeled historical-result diagnostics, as in the prior lane.

`git diff --stat A B -- us/policies/cbp/us-tariff-schedule/generated` produced no output: all generated chapter wrappers are byte-identical between A and B. `git diff --numstat A B -- tools/b16_entry_flags.py` produced `90 4 tools/b16_entry_flags.py`. Candidate's new input contract records the different entry-flag tool hash; all candidate keys must differ even though chapter wrapper modules do not.

The campaign also preserves existing manifest entries when adding new keys (`evaluate_campaign():841`), while comparison rejects duplicate chapter entries (`_iter_eval_records():857`). A fresh run must archive the old manifest before replacing it through evaluation. Setting a fresh cache path alone does not remove the old entries.

## Exposure ranking and observed historical runtimes

A single selected-CSV streaming pass read **9,913,304 rows** in **154.417 seconds**. Each nonzero Brazil / note52 field was counted once per campaign endpoint probe (one probe for a one-day interval, otherwise two), using committed routing to assign chapters. These are Yale statutory exposure counts, **not measured Axiom mismatches**. Note52 counts include slots excluded by the non-ad-valorem comparison plan. They are suitable for prioritizing chapters, not conformance claims.

| Chapter | Brazil nonzero probes | Note52 nonzero probes | Combined exposure | Historical engine cases | Historical shard seconds |
|---|---:|---:|---:|---:|---:|
| 62 | 7,482 | 139,040 | 146,522 | 1,403,865 | 2317.103 |
| 84 | 6,558 | 127,132 | 133,690 | 1,821,240 | 2875.274 |
| 29 | 6,746 | 106,602 | 113,348 | 991,575 | 1711.205 |
| 61 | 5,028 | 92,120 | 97,148 | 936,549 | 1641.589 |
| 85 | 4,026 | 76,028 | 80,054 | 928,638 | 1228.730 |
| 52 | 3,150 | 60,208 | 63,358 | 596,970 | 869.768 |
| 03 | 3,072 | 59,208 | 62,280 | 567,621 | 1381.232 |
| 44 | 2,082 | 46,228 | 48,310 | 534,303 | 889.350 |
| 90 | 2,490 | 45,648 | 48,138 | 446,985 | 573.939 |
| 64 | 2,346 | 43,968 | 46,314 | 433,269 | 565.043 |
| 55 | 2,394 | 42,684 | 45,078 | 442,233 | 979.710 |
| 39 | 1,914 | 37,200 | 39,114 | 346,617 | 584.333 |
| 07 | 2,088 | 35,596 | 37,684 | 372,492 | 912.373 |
| 48 | 1,872 | 32,556 | 34,428 | 312,471 | 464.597 |
| 70 | 1,662 | 31,888 | 33,550 | 308,421 | 456.322 |

The historical manifest contains 19,118,619 cases across 100 chapters. Its recorded chapter elapsed times sum to 37,074.912 seconds (10.30 hours serial); dividing that sum by the maximum three workers gives 3.43 hours as arithmetic only, not a measurement or reliable current runtime prediction. CH84's recorded 2,875.274 seconds is the largest shard duration. Comparison/classification runtime is not included. The campaign sorts chosen chapter names before submitting futures (`evaluate_campaign():822`), so priority order requires separate `--chapters` batches.

## Commands and reproduction

Commands below were run from the assigned workspace unless a `cd` is shown. No network calls, secret reads, external writes, or OpenAI API calls were performed by this audit.

```sh
cat /Users/maxghenis/TheAxiomFoundation/CLAUDE.md
cat /Users/maxghenis/.subfleet/worktrees/20260923-093102-yale-parity-1383-measure/yale-1383-run/RESULT.md
cd yale-full-run/A/oracles
rg -n 'def _render|def _load_manifest|stage_wall|input_contract|rulespec' scripts/us_tariff_schedule_campaign.py
git log -8 --format='%h %s' -- reference/us-tariff-schedule/declared-input-contract-receipt.json reference/us-tariff-schedule/eval/MANIFEST.json
git show 6ce2e6743 -- reference/us-tariff-schedule/declared-input-contract-receipt.json
cd ../../B/rulespec-us
git diff --stat 96d5e7c1e6309dc205b7320bbddaae8dd5d410df c62645022a8b2fcb5f9e6afdc2def2c8d68c2baf -- us/policies/cbp/us-tariff-schedule/generated
git diff --numstat 96d5e7c1e6309dc205b7320bbddaae8dd5d410df c62645022a8b2fcb5f9e6afdc2def2c8d68c2baf -- tools/b16_entry_flags.py
```

The following exact streaming command produced the exposure artifact:

```sh
python3 - <<'PY_EXPOSURE'
import csv,gzip,json,time,collections,pathlib
start=time.monotonic()
p=pathlib.Path('yale-full-run/B/oracles/reference/us-tariff-schedule')
routes={}
with gzip.open(p/'disposition-routing.csv.gz','rt',newline='') as f:
 for row in csv.DictReader(f): routes[row['hts10']]=row['chapter_shard']
counts=collections.defaultdict(collections.Counter)
with gzip.open(p/'selected-intervals.csv.gz','rt',newline='') as f:
 r=csv.reader(f); h=next(r); inds={k:h.index(k) for k in ['hts10','clipped_from','clipped_until','statutory_rate_s301br','statutory_rate_s301fl']}
 for n,row in enumerate(r,1):
  chapter=routes[row[inds['hts10']]]; k=counts[chapter]; weight=1+(row[inds['clipped_from']]!=row[inds['clipped_until']]);k['rows']+=1;k['probes']+=weight
  if float(row[inds['statutory_rate_s301br']])!=0:k['brazil_nonzero_probes']+=weight
  if float(row[inds['statutory_rate_s301fl']])!=0:k['note52_nonzero_probes']+=weight
  if n%2000000==0: print(json.dumps({'rows':n,'elapsed':round(time.monotonic()-start,3)}),flush=True)
ranked=[{'chapter':ch,**dict(c),'combined_exposure':c['brazil_nonzero_probes']+c['note52_nonzero_probes']} for ch,c in counts.items()]
ranked.sort(key=lambda x:x['combined_exposure'],reverse=True)
result={'rows':n,'elapsed_seconds':round(time.monotonic()-start,3),'method':'nonzero Yale Brazil and note52 selected values, counted once per campaign endpoint probe; exposure ranking, not measured Axiom mismatches','ranking':ranked}
out=pathlib.Path('yale-full-run/chapter-exposure-ranking.json');out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({**{k:v for k,v in result.items() if k!='ranking'},'top15':ranked[:15]},indent=2))
PY_EXPOSURE
```

Cache computation loaded the current module with `runpy.run_path`, reused `_sha256`, `_render`, `_module_path`, and `_load_manifest`, computed each of `_shard_key`'s exact ingredients, and checked manifest membership. Hashing the shared selected CSV once avoids doing the same read 100 times; the SHA inputs are identical to the script's. The two JSON audit artifacts retain every chapter's result.

The exact current-key audit command was:

```sh
/Users/maxghenis/TheAxiomFoundation/axiom-oracles/.venv/bin/python - <<'PY_CURRENT'
import runpy,hashlib,json,pathlib,time
start=time.monotonic();root=pathlib.Path('yale-full-run/A/oracles').resolve();rules=pathlib.Path('yale-full-run/A/rulespec-us').resolve()
c=runpy.run_path(str(root/'scripts/us_tariff_schedule_campaign.py')); sha=c['_sha256']; render=c['_render']; engine=pathlib.Path('/Users/maxghenis/TheAxiomFoundation/_tariff-parity/axiom-rules-engine/target/release/axiom-rules-engine')
common={'selected_sha256':sha(c['SELECTED']),'routing_sha256':sha(c['ROUTING_ROWS']),'engine_sha256':sha(engine),'outputs':c['OUTPUT_NAMES'],'input_contract_sha256':sha(c['INPUT_CONTRACT_RECEIPT'])}
manifest=c['_load_manifest'](); contract=json.loads(c['INPUT_CONTRACT_RECEIPT'].read_text()); checks=[]
for item in contract['chapters']:
 ch=item['chapter']; ingredients={**common,'chapter':ch,'module_sha256':sha(c['_module_path'](rules,ch))};key=hashlib.sha256(render(ingredients).encode()).hexdigest();old=manifest['shards'].get(key);path=pathlib.Path(old['path']) if old else None
 checks.append({'chapter':ch,'key':key,'manifest_key_matches':old is not None,'cache_exists':path.is_file() if path else False,'cache_bytes':path.stat().st_size if path and path.is_file() else 0})
result={'input_hashes':common,'committed_input_contract_seconds':contract.get('stage_wall_clock_seconds'),'chapters':len(checks),'matching_manifest_keys':sum(c['manifest_key_matches'] for c in checks),'existing_shards':sum(c['cache_exists'] for c in checks),'cache_bytes':sum(c['cache_bytes'] for c in checks),'elapsed_seconds':round(time.monotonic()-start,3),'checks':checks}
pathlib.Path('yale-full-run/baseline-cache-key-audit.json').write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps({k:v for k,v in result.items() if k!='checks'},indent=2))
PY_CURRENT
```

The exact historical-key/cache-hash diagnostic command was:

```sh
/Users/maxghenis/TheAxiomFoundation/axiom-oracles/.venv/bin/python - <<'PY_HISTORICAL'
import runpy,hashlib,json,pathlib,subprocess,time
start=time.monotonic(); root=pathlib.Path('yale-full-run/A/oracles').resolve();rules=pathlib.Path('yale-full-run/A/rulespec-us').resolve();c=runpy.run_path(str(root/'scripts/us_tariff_schedule_campaign.py'));sha=c['_sha256'];render=c['_render'];m=c['_load_manifest']();a=json.loads(pathlib.Path('yale-full-run/baseline-cache-key-audit.json').read_text());common=a['input_hashes'];old_receipt=subprocess.check_output(['git','show','6ce2e6743^:reference/us-tariff-schedule/declared-input-contract-receipt.json'],cwd=root);old_sha=hashlib.sha256(old_receipt).hexdigest(); matches=0;verified=0;cache_bytes=0;checks=[]
for s in m['shards'].values():
 ch=s['chapter']; ingredients={**common,'input_contract_sha256':old_sha,'chapter':ch,'module_sha256':sha(c['_module_path'](rules,ch))};k=hashlib.sha256(render(ingredients).encode()).hexdigest();matches+=(k==s['key']);p=pathlib.Path(s['path']);exists=p.is_file();valid=exists and sha(p)==s['sha256'];verified+=valid;cache_bytes+=p.stat().st_size if exists else 0;checks.append({'chapter':ch,'historical_receipt_key_matches':k==s['key'],'sha256_verified':valid})
result={'historical_input_contract_sha256':old_sha,'historical_receipt_tool_sha256':json.loads(old_receipt)['entry_flag_tool_sha256'],'baseline_tool_sha256':sha(rules/'tools/b16_entry_flags.py'),'matches_using_historical_receipt':matches,'cache_files_sha256_verified':verified,'cache_bytes':cache_bytes,'elapsed_seconds':round(time.monotonic()-start,3),'checks':checks};pathlib.Path('yale-full-run/baseline-historical-cache-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='checks'},indent=2))
PY_HISTORICAL
```

These diagnostics ran before the pipeline refreshed A's receipt and manifest. Reproducing the same forensic observation after that refresh requires a separate pristine origin/main checkout or the archived committed files, rather than treating new run artifacts as the original inputs.

## New artifacts

- `cache-audit.md`: this command/output report.
- `chapter-exposure-ranking.json`: all 100 chapter exposure counts and ranking.
- `baseline-cache-key-audit.json`: current committed receipt/key ingredients and 100 nonmatching-key results; 0.733 seconds.
- `baseline-historical-cache-audit.json`: historical receipt/key diagnosis and 100 cache SHA verifications; 4.332 seconds.
