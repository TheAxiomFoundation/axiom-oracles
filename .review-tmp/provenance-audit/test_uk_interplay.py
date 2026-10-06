from __future__ import annotations
import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from axiom_oracles.provenance import is_real_run_report

CONFIGS = [
    yaml.safe_load(path.read_text())
    for path in sorted((REPO / 'comparisons').glob('uk-*.yaml'))
    if not path.name.endswith('.fixtures.yaml')
]
CONFIGS = [
    config for config in CONFIGS
    if isinstance(config, dict)
    and str((config.get('runner') or {}).get('type', '')).endswith('-grid')
]

def load_runner():
    spec = importlib.util.spec_from_file_location('uk_interplay_runner', REPO / 'scripts/run_comparison.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

@pytest.mark.parametrize('original', CONFIGS, ids=lambda cfg: cfg['name'])
@pytest.mark.parametrize('require_live', (False, True), ids=('preserve-real', 'require-live'))
def test_actual_uk_config_main_fallback(original, require_live, tmp_path, monkeypatch):
    rc = load_runner()
    config = copy.deepcopy(original)
    root = tmp_path / 'repo'
    data_dir = root / 'dashboard/public/data'
    data_dir.mkdir(parents=True)
    filename = config['dashboard']['filename']
    real_bytes = (REPO / 'dashboard/public/data' / filename).read_bytes()
    assert is_real_run_report(json.loads(real_bytes)), filename
    target = data_dir / filename
    target.write_bytes(real_bytes)
    # Keep all path and git resolution inside this task-owned scratch root.
    config['runner']['parameters']['rulespec_roots'] = [str(root / 'rulespec-uk')]
    monkeypatch.setattr(rc, 'REPO_ROOT', root)
    monkeypatch.setattr(rc, 'DASHBOARD_DATA_DIR', data_dir)
    monkeypatch.setattr(rc, '_load_comparison', lambda _: config)
    original_run = subprocess.run
    def fail_generator(cmd, *args, **kwargs):
        if cmd[0] == 'uv':
            raise subprocess.CalledProcessError(1, cmd)
        return original_run(cmd, *args, **kwargs)
    monkeypatch.setattr(subprocess, 'run', fail_generator)
    out = root / 'reports'
    argv = ['run_comparison.py', config['name'], '--output-dir', str(out)]
    if require_live:
        argv.append('--require-live')
    monkeypatch.setattr(sys, 'argv', argv)
    if require_live:
        with pytest.raises(SystemExit, match='--require-live.*re-emitted'):
            rc.main()
        assert not list(out.glob('*.json'))
    else:
        assert rc.main() == 0
        files = list(out.glob('*.json'))
        assert len(files) == 1
        report = json.loads(files[0].read_text())
        assert not is_real_run_report(report)
        assert report['provenance']['reemitted_report'] is True
        assert report['provenance']['rulespecs'] == [
            {'repo': 'TheAxiomFoundation/rulespec-uk', 'sha': None}
        ]
    assert target.read_bytes() == real_bytes
    assert not list(out.glob('*.tmp'))
