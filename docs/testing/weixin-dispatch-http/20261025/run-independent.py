"""Record independently executed probe argv, actual results and frozen inputs."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PRODUCT = ('src/cn_contract/domain.py', 'src/cn_contract/weixin_inbox/conversation.py',
    'src/cn_contract/weixin_inbox/generation_dispatch.py', 'src/cn_contract/web/weixin_authorization.py')

def snapshot():
    files = [path for directory in ('src', 'tests') for path in (ROOT/directory).rglob('*')
        if path.is_file() and path.suffix in ('.py', '.json', '.mjs', '.html', '.css')]
    files += [ROOT/'AGENTS.md', ROOT/'CONTRIBUTING.md',
        ROOT/'docs/plans/2026-10-25-weixin-dispatch-http-d2g5e.md',
        ROOT/'sources/specification-v2.0.md', ROOT/'sources/upstream.lock.json',
        HERE/'independent-probe.py', HERE/'run-independent.py']
    return {path.relative_to(ROOT).as_posix():sha256(path.read_bytes()).hexdigest()
        for path in sorted(set(files))}

before = snapshot()
argv = [sys.executable, '-B', '-X', 'utf8', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
    '-o', 'addopts=', '--basetemp', str(HERE/'independent-probe-tmp'),
    '--junitxml', str(HERE/'independent-probe.xml'), str(HERE/'independent-probe.py')]
started = datetime.now(timezone.utc).isoformat(); tick = time.perf_counter()
env = dict(os.environ, PYTHONPATH='src;tests/integration', PYTHONDONTWRITEBYTECODE='1')
result = subprocess.run(argv, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
(HERE/'independent-probe.log').write_bytes(result.stdout)
after = snapshot()
xml = ET.parse(HERE/'independent-probe.xml').getroot()
cases = [value for value in xml.iter('testcase')]
record = {'baseline_sha_from_parent':'02e7e32a7d16c583d20d02396c6dc08cc348b65d',
    'cwd':str(ROOT), 'argv':argv, 'started_at':started,
    'ended_at':datetime.now(timezone.utc).isoformat(), 'elapsed_seconds':time.perf_counter()-tick,
    'exit_code':result.returncode, 'product_sha256':{path:after[path] for path in PRODUCT},
    'input_count':len(before), 'source_sha256_before':before, 'source_sha256_after':after,
    'inputs_unchanged':before==after, 'different_inputs':[path for path in set(before)|set(after)
        if before.get(path)!=after.get(path)],
    'tests':len(cases), 'failed':sum(value.find('failure') is not None for value in cases),
    'errors':sum(value.find('error') is not None for value in cases),
    'skipped':sum(value.find('skipped') is not None for value in cases),
    'node_ids':[value.attrib for value in cases],
    'log_sha256':sha256(result.stdout).hexdigest(),
    'xml_sha256':sha256((HERE/'independent-probe.xml').read_bytes()).hexdigest()}
(HERE/'independent-probe.json').write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({key:record[key] for key in ('exit_code','tests','failed','errors','skipped',
    'inputs_unchanged','input_count','different_inputs','product_sha256')}, ensure_ascii=False))
print(result.stdout.decode('utf-8', errors='replace'))
raise SystemExit(result.returncode or (0 if before==after else 3))
