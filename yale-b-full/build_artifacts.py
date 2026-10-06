#!/usr/bin/env python3
"""Hash the bounded artifact set without scanning repositories or caches."""
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parent
paths=[]
for folder in [root,root/'helpers',root/'logs',root/'prior-checkpoint',root/'prior-checkpoint/logs',root/'B/committed',root/'B-completed-gap-inventory-chapters']:
 if folder.is_dir():
  paths.extend(p for p in folder.iterdir() if p.is_file() and p.name not in {'ARTIFACTS.json'} and not p.name.endswith('.running.json'))
ref=root/'B/oracles/reference/us-tariff-schedule'
paths.extend(ref/name for name in ['eval/MANIFEST.json','disposition-routing.csv.gz','disposition-routing-receipt.json','declared-input-contract-receipt.json','evaluation-projection-receipt.json','selected-intervals.csv.gz'])
manifest=json.loads((ref/'eval/MANIFEST.json').read_text())
paths.extend(Path(s['path']) for s in manifest['shards'].values())
items=[]
for p in sorted(set(paths)):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 items.append({'path':str(p.relative_to(root)),'bytes':p.stat().st_size,'sha256':h.hexdigest()})
(root/'ARTIFACTS.json').write_text(json.dumps({'schema':'measurement.b_checkpoint_artifacts.v1','root':str(root),'artifacts':items,'excluded':'Git metadata, source checkout bodies, mirrored review evidence, and this self-referential index. Source identities are in setup-verification.json.'},indent=2)+'\n')
print(json.dumps({'artifacts':len(items),'bytes':sum(i['bytes'] for i in items)}))
