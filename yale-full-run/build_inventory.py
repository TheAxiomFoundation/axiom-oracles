#!/usr/bin/env python3
"""Inventory retained evidence without scanning repository or cache trees."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
paths = set()
for pattern in ('*.md', '*.py', '*.sh', '*.json', '*.bundle', '*.txt'):
    paths.update(root.glob(pattern))
paths.discard(root / 'ARTIFACTS.json')
for directory in [root / 'logs', root / 'targeted-A', root / 'targeted-B',
                  *root.glob('*-chapters')]:
    if directory.is_dir():
        paths.update(p for p in directory.iterdir() if p.is_file())
for variant in ('A', 'B'):
    paths.update((root / variant).glob('*.json'))
    directory = root / variant / 'oracles/reference/us-tariff-schedule'
    for name in ('disposition-routing-receipt.json', 'disposition-routing.csv.gz',
                 'declared-input-contract-receipt.json', 'evaluation-projection-receipt.json',
                 'eval/MANIFEST.json'):
        paths.add(directory / name)
    paths.update((root / variant / 'committed').glob('*.json'))
    manifest = json.loads((directory / 'eval/MANIFEST.json').read_text())
    for shard in manifest['shards'].values():
        paths.add(Path(shard['path']))
isolated = root / 'B/ch29-isolated-MANIFEST.json'
if isolated.is_file():
    paths.add(isolated)
    for shard in json.loads(isolated.read_text())['shards'].values():
        paths.add(Path(shard['path']))

def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()

rows = []
for path in sorted(paths):
    if not path.is_file():
        continue
    path.resolve().relative_to(root)
    rows.append({'path': str(path.relative_to(root)), 'bytes': path.stat().st_size,
                 'sha256': digest(path)})
payload = {'schema': 'measurement.yale_checkpoint_artifacts.v1',
           'created_utc': datetime.now(timezone.utc).isoformat(),
           'root': str(root), 'files': rows,
           'scope': 'Retained measurement evidence and completed fresh shards; excludes Git object stores, full source checkouts, external historical cache bodies and uncommitted temporary shard output.'}
(root / 'ARTIFACTS.json').write_text(json.dumps(payload, indent=2) + '\n')
print(json.dumps({'files': len(rows), 'bytes': sum(r['bytes'] for r in rows),
                  'output': str(root / 'ARTIFACTS.json')}))
