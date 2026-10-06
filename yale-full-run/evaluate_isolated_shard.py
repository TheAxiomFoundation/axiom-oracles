#!/usr/bin/env python3
"""Call the unmodified campaign evaluator with an isolated manifest location.

This avoids concurrent read/modify/write on the primary manifest. No case,
cache-key, engine, selector, or stage implementation is changed. Merge verified
receipts only after all writers to the primary manifest have stopped.
"""
import argparse
import importlib.util
import json
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--oracles-root', type=Path, required=True)
p.add_argument('--rulespec-root', type=Path, required=True)
p.add_argument('--engine-binary', type=Path, required=True)
p.add_argument('--manifest', type=Path, required=True)
p.add_argument('--chapter', required=True)
a = p.parse_args()
script = a.oracles_root.resolve() / 'scripts/us_tariff_schedule_campaign.py'
spec = importlib.util.spec_from_file_location('isolated_current_campaign', script)
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)
if a.manifest.resolve() == campaign.EVAL_MANIFEST.resolve():
    raise ValueError('isolated manifest must differ from the primary manifest')
campaign.EVAL_MANIFEST = a.manifest.resolve()
receipt = campaign.evaluate_campaign(
    rulespec_root=a.rulespec_root.resolve(),
    engine_binary=a.engine_binary.resolve(), workers=1,
    chapters=[a.chapter], resume=True,
)
print(json.dumps(receipt, indent=2, sort_keys=True))
