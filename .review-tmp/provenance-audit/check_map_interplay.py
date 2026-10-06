from __future__ import annotations
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from axiom_oracles.provenance import is_real_run_report

def load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

gen = load('generate_affected_map')
sel = load('select_affected_suites')
current = gen.build_map()
assert current == json.loads((REPO / 'comparisons/affected_map.json').read_text())
base = json.loads(subprocess.check_output(['git', 'show', 'fc3ce90de:comparisons/affected_map.json'], cwd=REPO))
base_entries = {row['suite']: row for row in base['suites']}
entries = {row['suite']: row for row in current['suites']}
assert base_entries.keys() == entries.keys()
changed = {suite for suite in entries if entries[suite] != base_entries[suite]}
snap = {suite for suite in entries if suite.endswith('-snap-qc')}
assert changed == snap and len(snap) == 7, changed
for suite in snap:
    assert entries[suite]['repos'] == ['TheAxiomFoundation/rulespec-us']
    assert entries[suite]['name'] is None
    assert 'pinned' not in entries[suite]
reports = {suite: json.loads((REPO / 'dashboard/public/data' / entries[suite]['report']).read_text()) for suite in snap}
for suite in snap:
    assert is_real_run_report(reports[suite])
    sha = sel._report_ran_against(reports[suite])['TheAxiomFoundation/rulespec-us']
    assert len(sha) == 40
    reportmap = {suite: reports[suite]}
    one = {'suites': [entries[suite]]}
    assert sel.select(one, {'TheAxiomFoundation/rulespec-us': sha}, reportmap) == []
    stale = sel.select(one, {'TheAxiomFoundation/rulespec-us': 'f' * 40}, reportmap)
    assert sel.runnable_names(stale) == []
    assert sel.manual_suites(stale) == [suite]
for suite in ['co-tax-intersection-taxsim', 'fiit-taxsim-ecps']:
    row = entries[suite]
    assert row == base_entries[suite]
    assert row['pinned'] == {'TheAxiomFoundation/rulespec-us': 'ca2d424f'}
    one = {'suites': [row]}
    real = {'provenance': {'rulespecs': [{'repo': 'TheAxiomFoundation/rulespec-us', 'sha': 'ca2d424f' + '0' * 32}]}}
    assert is_real_run_report(real)
    assert sel.select(one, {'TheAxiomFoundation/rulespec-us': 'f' * 40}, {suite: real}) == []
    reemit = {'provenance': {'reemitted_report': True, 'rulespecs': [{'repo': 'TheAxiomFoundation/rulespec-us', 'sha': None}]}}
    assert not is_real_run_report(reemit)
    assert sel.select(one, {}, {suite: reemit})[0]['name'] is None
uk_count = 0
for suite, row in entries.items():
    if suite.startswith('uk-') and row['repos'] == ['TheAxiomFoundation/rulespec-uk']:
        one = {'suites': [row]}
        report = {'provenance': {'rulespecs': [{'repo': 'TheAxiomFoundation/rulespec-uk', 'sha': 'a' * 40}]}}
        assert sel.select(one, {'TheAxiomFoundation/rulespec-uk': 'a' * 40}, {suite: report}) == []
        stale = sel.select(one, {'TheAxiomFoundation/rulespec-uk': 'b' * 40}, {suite: report})
        assert stale[0]['name'] == row['name']
        uk_count += 1
assert uk_count
print('UK single-root suite selector fresh/stale pairs:', uk_count)
print(json.dumps({'entries': len(entries), 'changed_vs_main': sorted(changed), 'snap_manual_and_sha_matching': 'passed', 'both_roots_pinned_suites': 'passed', 'non_snap_entries_byte_equivalent_as_parsed': 'passed'}, indent=2))
