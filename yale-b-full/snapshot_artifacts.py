#!/usr/bin/env python3
"""Copy small run evidence into the writable B branch for reviewable commits."""
from pathlib import Path
import shutil

run = Path(__file__).resolve().parent
out = run/'B/oracles/measurement/yale-campaign-b-full'
out.mkdir(parents=True,exist_ok=True)
files = [p for p in run.iterdir() if p.is_file() and p.suffix in {'.py','.sh','.md','.json','.stdout','.stderr'}]
files += [p for p in (run/'helpers').iterdir() if p.is_file() and p.suffix in {'.py','.md'}]
files += [p for p in (run/'logs').iterdir() if p.is_file() and not p.name.endswith('.running.json')]
files += [run/'prior-checkpoint/B-MANIFEST.json']
for folder in run.glob('B-completed-gap-inventory-chapters'):
    files += [p for p in folder.iterdir() if p.is_file()]
for source in files:
    target = out/source.relative_to(run)
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,target)
print(f'Copied {len(files)} evidence files to {out}')
