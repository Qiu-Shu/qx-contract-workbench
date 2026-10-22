"""Replay only the original prefix, recording native SQLite liveness at publish."""
from datetime import datetime, timezone
import gc
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4
import xml.etree.ElementTree as ET

import pytest

root = Path.cwd()
sys.path.insert(0, str(root))
out = root / '.local/profile-persistence-20261023'
original = list(ET.parse(out / 'target.xml').getroot().iter('testcase'))
nodes = []
for case in original:
    nodes.append(case.get('classname').replace('.', '/') + '.py::' + case.get('name'))
    if case.get('name') == 'test_long_parent_paths_create_restore_and_rebackup[long]':
        break
assert len(nodes) == 79
temp = root / '.local' / ('po-' + uuid4().hex[:8])
assert not temp.exists()
connections, publish = [], []

def inputs():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ('src', 'tests') for p in Path(folder).rglob('*.py')}

before = inputs()
connect = sqlite3.connect
dbapi_connect = sqlite3.dbapi2.connect
rename = os.rename

def track(factory):
    def create(*args, **kwargs):
        connection = factory(*args, **kwargs)
        name = str(args[0] if args else kwargs.get('database', ''))
        if '.qx-restore-' in name:
            connections.append((name, connection))
        return connection
    return create

def observed_rename(source, target, *args, **kwargs):
    path = Path(source)
    if path.name != 'workspace' or not path.parent.name.startswith('.qx-restore-'):
        return rename(source, target, *args, **kwargs)
    entry = {'source':str(source), 'target':str(target), 'gc_enabled':gc.isenabled(),
             'gc_count':gc.get_count(), 'connections':[], 'source_mode':path.stat().st_mode,
             'target_exists':Path(target).exists()}
    for name, connection in connections:
        try:
            cursor = connection.execute('SELECT 1')
            cursor.close()
            state = 'OPEN'
        except sqlite3.ProgrammingError:
            state = 'CLOSED'
        entry['connections'].append({'path':name, 'state':state})
    publish.append(entry)
    try:
        result = rename(source, target, *args, **kwargs)
        entry['result'] = 'renamed'
        return result
    except OSError as error:
        entry.update(result='failed', winerror=getattr(error,'winerror',None), errno=error.errno)
        raise

sqlite3.connect = track(connect)
sqlite3.dbapi2.connect = track(dbapi_connect)
os.rename = observed_rename
started = datetime.now(timezone.utc).isoformat()
try:
    code = pytest.main(['-q','--tb=short','-o','junit_family=xunit1',
                       '--basetemp='+str(temp),'--junitxml='+str(out/'path-order-probe.xml'),*nodes])
finally:
    sqlite3.connect = connect
    sqlite3.dbapi2.connect = dbapi_connect
    os.rename = rename
after = inputs()
report = {'started_utc':started,'exit_code':int(code),'nodes':nodes,'publish':publish,
          'inputs_equal':before==after,'inputs_before':before,'inputs_after':after,
          'limitation':'Observational wrapper retains closed SQLite objects and can affect timing. A pass cannot establish the original root cause; no retry or product patch.'}
(out/'path-order-probe.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
raise SystemExit(code)
