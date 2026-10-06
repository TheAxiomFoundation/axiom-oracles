#!/usr/bin/env python3
"""Merge completed CH29 only after the recorded primary writer has stopped.

Recompute current campaign keys and verify shard hashes before writing the
manifest. This never rewrites a shard or substitutes a cache key.
"""
import importlib.util
import json
import os
from pathlib import Path

root = Path(__file__).resolve().parent
writer = root / 'logs/B-evaluate-priority.json'
if not writer.is_file() or (root / 'logs/B-evaluate-priority.running.json').exists():
    raise RuntimeError('primary writer has not recorded a final outcome')
if json.loads(writer.read_text())['status'] not in ('complete', 'timeout', 'interrupted'):
    raise RuntimeError('primary writer is still active')
os.environ['AXIOM_TARIFF_C1_CACHE'] = str(root / 'B/cache')
os.environ['RULESPEC_US_CHECKOUT'] = str(root / 'B/rulespec-us')
script = root / 'B/oracles/scripts/us_tariff_schedule_campaign.py'
spec = importlib.util.spec_from_file_location('merge_current_campaign', script)
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)
primary = campaign._load_manifest()
isolated_path = root / 'B/ch29-isolated-MANIFEST.json'
isolated = json.loads(isolated_path.read_text())
if isolated.get('schema') != primary['schema']:
    raise ValueError('manifest schema mismatch')
engine = Path('/Users/maxghenis/TheAxiomFoundation/_tariff-parity/axiom-rules-engine/target/release/axiom-rules-engine')
by_chapter = {}
for manifest in (primary, isolated):
    for key, shard in manifest['shards'].items():
        expected = campaign._shard_key(chapter=shard['chapter'],
            rulespec_root=root / 'B/rulespec-us', engine_binary=engine)
        if key != expected or shard['key'] != expected:
            raise ValueError(f"current key mismatch: {shard['chapter']}")
        if campaign._sha256(Path(shard['path'])) != shard['sha256']:
            raise ValueError(f"shard hash mismatch: {shard['chapter']}")
        old = by_chapter.get(shard['chapter'])
        if old is not None and old != shard:
            raise ValueError(f"conflicting chapter shard: {shard['chapter']}")
        by_chapter[shard['chapter']] = shard
before = campaign._sha256(campaign.EVAL_MANIFEST)
primary['shards'] = {shard['key']: shard for shard in by_chapter.values()}
campaign._atomic_json(campaign.EVAL_MANIFEST, primary)
print(json.dumps({'verification': 'PASS: current keys, hashes, unique chapters',
    'manifest': str(campaign.EVAL_MANIFEST), 'before_sha256': before,
    'after_sha256': campaign._sha256(campaign.EVAL_MANIFEST),
    'chapters': sorted(by_chapter),
    'cases': sum(s['cases'] for s in by_chapter.values())}, indent=2))
