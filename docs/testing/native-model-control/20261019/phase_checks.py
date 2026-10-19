"""Bounded reproducible verification; no production data or external provider."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
PYTHON = ROOT / '.venv/Scripts/python.exe'
TESTS = [
    'tests/integration/test_native_credential_backup.py',
    'tests/integration/test_native_model_control.py',
    'tests/integration/test_native_control_process.py',
    'tests/integration/test_desktop_runtime.py',
    'tests/unit/test_desktop_control_protocol.py',
    'tests/integration/test_model_registry.py',
    'tests/integration/test_session_model_runtime.py',
    'tests/integration/test_assistant_generation.py',
    'tests/integration/test_assistant_generation_routes.py',
    'tests/integration/test_assistant_task_manager.py',
    'tests/integration/test_assistant_generation_history.py',
    'tests/integration/test_assistant_model_startup.py',
    'tests/integration/test_assistant_model_denial_fence.py',
    'tests/integration/test_assistant_main_provider.py',
    'tests/integration/test_assistant_model_backup.py',
    'tests/integration/test_assistant_model_upgrade_backup.py',
    'tests/integration/test_assistant_routes.py',
    'tests/integration/test_local_workbench.py',
    'tests/integration/test_local_worker_contention.py',
    'tests/unit/test_assistant_model_contract.py',
]


def save(name, data):
    (BASE / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def snapshot(name, *, build=False):
    names = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT).decode('utf-8').split('\0')
    prefixes = ('src/', 'tests/', 'scripts/', 'desktop/', 'schemas/', 'config/', 'prompts/', 'rules/', 'plugins/')
    exact = {'pyproject.toml', 'requirements.lock', 'requirements-build.lock', 'sources/runtime-dependencies.lock.json', 'sources/upstream.lock.json'}
    if build:
        prefixes = ('src/', 'config/', 'prompts/', 'rules/', 'tests/fixtures/assisted-v1/', 'tests/fixtures/synthetic/')
        exact |= {'desktop/backend.spec', 'scripts/desktop_backend_entry.py'}
    values = {n: hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(names))
              if n and (n.startswith(prefixes) or n in exact) and (ROOT/n).is_file()}
    save(name, values)
    return values


def run(name, arguments, *, env=None):
    command = [str(PYTHON), '-X', 'utf8', *arguments]
    save(name+'-command.json', command)
    with (BASE/(name+'.log')).open('wb') as output:
        code = subprocess.run(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, env=env).returncode
    (BASE/(name+'.exit')).write_text(str(code)+'\n', encoding='utf-8')
    print(json.dumps({'stage':name, 'exit_code':code}), flush=True)
    if code:
        raise SystemExit(code)


if sys.argv[1] == 'regression':
    before = snapshot('regression-source-before.json')
    run('collected', ['-m', 'pytest', *TESTS, '--collect-only', '-q'])
    run('regression', ['-m', 'pytest', *TESTS, '-q', '--tb=short', '--junitxml='+str(BASE/'regression.xml')])
    after = snapshot('regression-source-after.json')
    tree = ET.parse(BASE/'regression.xml')
    cases = tree.findall('.//testcase')
    identities = [c.attrib['classname'].replace('.', '/')+'.py::'+c.attrib['name'] for c in cases]
    collected = [line.strip() for line in (BASE/'collected.log').read_text('utf-8').splitlines()
                 if line.startswith('tests/') and '::' in line]
    summary = {'tests':len(cases), 'failures':len(tree.findall('.//failure')), 'errors':len(tree.findall('.//error')),
               'skips':len(tree.findall('.//skipped')), 'unique':len(identities)==len(set(identities)),
               'collection_matches':set(identities)==set(collected), 'input_files':len(before),
               'changed_inputs':[n for n in before.keys() | after.keys() if before.get(n)!=after.get(n)],
               'junit_seconds':sum(float(s.attrib.get('time',0)) for s in tree.findall('testsuite')), 'exit_code':0}
    save('regression-summary.json', summary)
    print(json.dumps(summary), flush=True)
    assert summary['unique'] and summary['collection_matches'] and not summary['changed_inputs']
    assert not any(summary[k] for k in ('failures', 'errors', 'skips'))
elif sys.argv[1] == 'gates':
    for name, arguments in [
        ('defaults', ['scripts/verify_defaults.py']),
        ('sources', ['scripts/verify_sources.py', '--mode', 'development']),
        ('dependencies', ['scripts/verify_runtime_dependencies.py', '--mode', 'development']),
        ('schema', ['-m', 'cn_contract.cli', 'schema', '--check']),
    ]:
        run(name, arguments)
elif sys.argv[1] == 'build':
    before = snapshot('build-source-before.json', build=True)
    environment = os.environ.copy()
    environment['PYTHONPATH'] = str(ROOT/'.local/desktop-tools/python-build')
    run('frozen-build', ['-m', 'PyInstaller', '--noconfirm', '--distpath', str(BASE/'frozen-backend'),
                       '--workpath', str(BASE/'build-backend'), str(ROOT/'desktop/backend.spec')], env=environment)
    after = snapshot('build-source-after.json', build=True)
    assert before == after
    run('frozen-smoke', [str(BASE/'frozen_backend_smoke.py')])
