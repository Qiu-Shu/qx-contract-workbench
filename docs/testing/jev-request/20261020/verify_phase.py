from pathlib import Path
import hashlib, json, os, subprocess, sys, time
from datetime import datetime, timezone

root = Path.cwd()
local = root / '.local/jev-request-20261020'
out = local / 'parent'
python = root / '.venv/Scripts/python.exe'
electron = root / 'desktop/node_modules/electron/dist/electron.exe'

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def snapshot():
    names = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard'], encoding='utf-8').splitlines()
    prefixes = ('src/', 'desktop/', 'prompts/', 'rules/', 'config/', 'tests/fixtures/assisted-v1/', 'tests/fixtures/synthetic/', 'tests/helpers/')
    explicit = {'scripts/desktop_backend_entry.py', 'pyproject.toml', 'requirements.lock', 'requirements-build.lock'}
    return {name: sha(root / name) for name in sorted(set(names))
            if (name.startswith(prefixes) or name in explicit) and (root/name).is_file()}

def save(name, value):
    (out/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

def run(name, args, env):
    before = snapshot()
    started = datetime.now(timezone.utc).isoformat()
    timer = time.monotonic()
    with (out/(name+'.log')).open('wb') as log:
        result = subprocess.run([str(a) for a in args], cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
    after = snapshot()
    record = {'command': [str(a) for a in args], 'started_utc': started, 'exit_code': result.returncode,
              'elapsed_seconds': round(time.monotonic()-timer,3), 'inputs_before': before, 'inputs_after': after,
              'inputs_equal': before == after}
    save(name+'.json',record)
    print(json.dumps({'step': name, 'exit_code': result.returncode, 'seconds':record['elapsed_seconds'],
                      'inputs_equal': before == after, 'inputs':len(before)}), flush=True)
    if result.returncode or before != after:
        raise SystemExit(result.returncode or 2)

env = os.environ.copy()
env['PYTHONPATH'] = str(root/'src')
mode = sys.argv[1]
if mode == 'source':
    run('native-source', [electron, root/'desktop/tests/model-control-acceptance.cjs', local/'native-source', '--judge'], env)
elif mode == 'gates-build':
    gates = [('-m','cn_contract.cli','schema','--check'), ('scripts/verify_defaults.py',),
             ('scripts/verify_sources.py','--mode','development'), ('scripts/verify_runtime_dependencies.py','--mode','development')]
    for i, args in enumerate(gates,1):
        run('gate-'+str(i), [python,'-X','utf8',*args],env)
    env['PYTHONPATH'] = str(root/'.local/desktop-tools/python-build')
    run('build', [python,'-m','PyInstaller','--noconfirm','--distpath',local/'frozen-backend',
                 '--workpath',local/'build','desktop/backend.spec'],env)
    folder = local/'frozen-backend/qx-backend'
    paths = [p for p in folder.rglob('*') if p.is_file()]
    save('build-size.json', {'files':len(paths),'bytes':sum(p.stat().st_size for p in paths),
                           'exe_sha256':sha(folder/'qx-backend.exe')})
elif mode == 'frozen':
    run('native-frozen', [electron, root/'desktop/tests/model-control-acceptance.cjs', local/'native-frozen',
                         '--judge','--frozen',local/'frozen-backend/qx-backend/qx-backend.exe'],env)
else:
    raise SystemExit('unknown phase')
