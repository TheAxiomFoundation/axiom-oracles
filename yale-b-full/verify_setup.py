#!/usr/bin/env python3
"""Verify exact checkpoint receipts; relocate only cache path metadata."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

RUN = Path(__file__).resolve().parent
OLD = Path('/Users/maxghenis/.subfleet/worktrees/20260923-140123-yale-campaign-full-v2/yale-full-run')
ENGINE = Path('/Users/maxghenis/TheAxiomFoundation/_tariff-parity/axiom-rules-engine/target/release/axiom-rules-engine')

def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def git(root,*args):
 return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()

out = {'checkpoint_source': str(OLD), 'checks': []}
assert git(RUN/'B/rulespec-us','rev-parse','HEAD') == 'c62645022a8b2fcb5f9e6afdc2def2c8d68c2baf'
assert not git(RUN/'B/rulespec-us','diff','--name-only')
assert sha(ENGINE)=='674ca6e70afdccb59c3d6847933bc24b4590105e49db54790f2dcd0bdbbe32d7'
out['engine_sha256']=sha(ENGINE)
ref=Path('B/oracles/reference/us-tariff-schedule')
for rel in ['scripts/us_tariff_schedule_campaign.py','reference/us-tariff-schedule/campaign-dispositions.yaml']:
 old=OLD/'B/oracles'/rel; new=RUN/'B/oracles'/rel
 assert sha(old)==sha(new)
 out['checks'].append({'path':str(new),'sha256':sha(new),'unchanged':True})
for name in ['disposition-routing.csv.gz','disposition-routing-receipt.json','declared-input-contract-receipt.json','evaluation-projection-receipt.json','selected-intervals.csv.gz']:
 old=OLD/ref/name; new=RUN/ref/name
 assert sha(old)==sha(new)
 out['checks'].append({'path':str(new),'sha256':sha(new),'unchanged':True})
manifest=RUN/ref/'eval/MANIFEST.json'
source=OLD/ref/'eval/MANIFEST.json'
assert sha(source)=='11a722f898e8fd3ce23a33f175acdf4ad2bf9e66e178f8d6e2c960f783cbad42'
assert sha(manifest)==sha(source)
shutil.copy2(source,RUN/'prior-checkpoint/B-MANIFEST.json')
os.environ['RULESPEC_US_CHECKOUT']=str(RUN/'B/rulespec-us')
os.environ['AXIOM_TARIFF_C1_CACHE']=str(RUN/'B/cache')
spec=importlib.util.spec_from_file_location('campaign',RUN/'B/oracles/scripts/us_tariff_schedule_campaign.py')
campaign=importlib.util.module_from_spec(spec);spec.loader.exec_module(campaign)
data=json.loads(manifest.read_text())
assert sorted(x['chapter'] for x in data['shards'].values())==['29','79']
for key, shard in data['shards'].items():
 assert key==campaign._shard_key(chapter=shard['chapter'],rulespec_root=RUN/'B/rulespec-us',engine_binary=ENGINE)
 old=Path(shard['path']);new=RUN/old.relative_to(OLD)
 assert sha(old)==sha(new)==shard['sha256']
 out['checks'].append({'chapter':shard['chapter'],'key':key,'sha256':sha(new),'old_path':str(old),'new_path':str(new)})
 shard['path']=str(new)
manifest.write_text(json.dumps(data,sort_keys=True,indent=2)+'\n')
out.update(original_manifest_sha256=sha(source),relocated_manifest_sha256=sha(manifest),result='PASS',relocation='Only shard path metadata changed; no receipts, keys or shard bytes changed.')
(RUN/'setup-verification.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
