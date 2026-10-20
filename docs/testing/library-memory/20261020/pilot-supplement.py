from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

out = Path('.local/library-memory-20261020')
runtime = Path('D:/Documents/裁判文书数据库试点2025/.venv/Scripts/python.exe')
previous = json.loads((out/'verification.json').read_text('utf-8'))['inputs_after']
hashes = lambda: {p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in previous}
before = hashes()
assert before == previous
probe = [str(runtime), '-I', '-c', 'import duckdb,json,sys; print(json.dumps({"python":sys.executable,"version":duckdb.__version__,"module":duckdb.__file__}))']
check = subprocess.run(probe, capture_output=True, text=True, encoding='utf-8')
assert check.returncode == 0, check.stderr
runtime_info = json.loads(check.stdout)
assert runtime_info['version'] == '1.5.6'
env = {**os.environ, 'QX_PILOT_PYTHON':str(runtime), 'PYTHONUTF8':'1'}
command = [sys.executable,'-X','utf8','-m','pytest','tests/integration/test_library_pilot.py','-q',
           '--junitxml='+str(out/'pilot-supplement.xml')]
started = datetime.now(timezone.utc).isoformat(); clock = time.monotonic()
run = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', env=env)
(out/'pilot-supplement.log').write_text(run.stdout+run.stderr,encoding='utf-8')
suites = ET.parse(out/'pilot-supplement.xml').getroot()
counts = {k:sum(int(s.get(k,0)) for s in suites.iter('testsuite')) for k in ('tests','failures','errors','skipped')}
after = hashes()
report = {'started_utc':started,'command':command,'environment':{'QX_PILOT_PYTHON':str(runtime)},
          'runtime_probe':{'command':probe,'exit_code':check.returncode, 'observed':runtime_info},
          'installed_packages':[], 'exit_code':run.returncode,'seconds':round(time.monotonic()-clock,3),
          'counts':counts,'inputs_before':before,'inputs_after':after,'inputs_equal':before==after,
          'matches_prior_verified_inputs':before==previous,
          'scope':'Reused isolated DuckDB interpreter only. Tests create fresh synthetic CSV and DuckDB in pytest tmp_path; no existing pilot database read or changed.'}
(out/'pilot-supplement.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ('inputs_before','inputs_after')},ensure_ascii=False),flush=True)
sys.exit(0 if run.returncode==0 and before==after and counts=={'tests':2,'failures':0,'errors':0,'skipped':0} else 1)
