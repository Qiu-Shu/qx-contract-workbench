"""Run one unchanged synthetic long-path test against a frozen source snapshot."""
from datetime import datetime, timezone
import functools
import hashlib
import json
from pathlib import Path
import os
import sys
import time
import traceback

import pytest

evidence = Path(__file__).resolve().parent
preparation = json.loads((evidence/'baseline-preparation.json').read_text('utf-8'))
snapshot = Path(preparation['snapshot'])
baseline_source = snapshot/'src'

import cn_contract
from cn_contract import config
from cn_contract.ops import workspace_backup
from cn_contract.ops.file_paths import filesystem_path

module = Path(workspace_backup.__file__).resolve()
assert module == (baseline_source/'cn_contract/ops/workspace_backup.py').resolve(), module
assert Path(cn_contract.__file__).resolve().is_relative_to(baseline_source.resolve())
assert config.PROJECT_ROOT.resolve() == snapshot.resolve()
assert hashlib.sha256(module.read_bytes()).hexdigest() == preparation['workspace_backup_sha256']

events = []
original = workspace_backup._validate_database


@functools.wraps(original)
def validate_observer(root):
    # Observe only path metadata. The exact frozen function still performs validation.
    database = Path(root)/'workbench.db'
    event = dict(root=str(root), root_length=len(str(root)), database=str(database),
        database_length=len(str(database)), database_uri_length=len(database.as_uri()),
        database_uri_utf8_bytes=len(database.as_uri().encode('utf-8')),
        exists=filesystem_path(database).is_file(),
        stage='snapshot' if Path(root).name == 'snapshot' else 'workspace')
    events.append(event)
    try:
        result = original(root)
    except BaseException as error:
        event.update(status='FAIL', exception_type=type(error).__name__, message=str(error),
            traceback=traceback.format_exc())
        raise
    event['status'] = 'PASS'
    return result


workspace_backup._validate_database = validate_observer
argv = [
    'tests/integration/test_assistant_attachment_backup.py::test_long_parent_paths_create_restore_and_rebackup[long]',
    '-q', '--tb=short', '--basetemp='+preparation['baseline_basetemp'],
    '--junitxml='+str(evidence/'baseline-long-path.xml'),
]
metadata = dict(preparation, actual_module=str(module), actual_module_sha256=hashlib.sha256(module.read_bytes()).hexdigest(),
    cn_contract_origin=cn_contract.__file__, config_project_root=str(config.PROJECT_ROOT),
    command=[sys.executable, '-B', '-X', 'utf8', str(Path(__file__).resolve())],
    pytest_argv=argv, pythonpath=os.environ.get('PYTHONPATH'), sys_path=sys.path,
    started_at_utc=datetime.now(timezone.utc).isoformat(),
    instrumentation='Local runtime wrapper observes path metadata and delegates unmodified frozen _validate_database; no product/test source patched.')
print(json.dumps({'baseline_execution':metadata}, ensure_ascii=False), flush=True)
started = time.monotonic()
code = int(pytest.main(argv))
metadata.update(exit_code=code, seconds=round(time.monotonic()-started, 3), validation_events=events,
    completed_at_utc=datetime.now(timezone.utc).isoformat())
origins = {name:str(Path(value.__file__).resolve()) for name,value in sys.modules.items()
    if name == 'cn_contract' or name.startswith('cn_contract.')
    if getattr(value,'__file__',None)}
metadata['product_module_origins'] = origins
metadata['all_product_modules_from_baseline'] = all(Path(path).is_relative_to(baseline_source.resolve()) for path in origins.values())
hashes = {p.relative_to(baseline_source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
    for p in baseline_source.rglob('*.py')}
metadata['source_hashes'] = hashes
metadata['source_hash_manifest_sha256'] = hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()
(evidence/'baseline-long-path.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
assert metadata['all_product_modules_from_baseline'], 'A product import escaped the frozen baseline'
print(json.dumps({'baseline_result':{'exit_code':code,'validation_events':events,
    'all_product_modules_from_baseline':metadata['all_product_modules_from_baseline'],
    'source_hash_manifest_sha256':metadata['source_hash_manifest_sha256']}},ensure_ascii=False),flush=True)
raise SystemExit(code)
