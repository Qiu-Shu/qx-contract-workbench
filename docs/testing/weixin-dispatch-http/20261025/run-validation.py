from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess
import sys
import time

ROOT = Path.cwd()
OUT = Path(__file__).resolve().parent
PY = ROOT / '.venv/Scripts/python.exe'
os.environ['PYTHONPATH'] = 'src;tests/integration'
GROUPS = {
 'red-services': (['tests/integration/test_weixin_generation_dispatch_conversation.py'], ['-k', 'fixed_receipt_projection or dispatch_input']),
 'final-services': (['tests/integration/test_weixin_generation_dispatch_conversation.py', 'tests/integration/test_weixin_generation_dispatch_routes.py'], []),
 'final-services-fixed': (['tests/integration/test_weixin_generation_dispatch_conversation.py', 'tests/integration/test_weixin_generation_dispatch_routes.py'], []),
 'final-services-verified': (['tests/integration/test_weixin_generation_dispatch_conversation.py', 'tests/integration/test_weixin_generation_dispatch_routes.py'], []),
 'audit-oracle-check': (['tests/integration/test_weixin_generation_dispatch_routes.py'], ['-k','current_root_and_fixed_target_acl']),
 'final-services-complete': (['tests/integration/test_weixin_generation_dispatch_conversation.py', 'tests/integration/test_weixin_generation_dispatch_routes.py'], []),
 'final-dispatch': (['tests/integration/test_weixin_generation_dispatch.py', 'tests/integration/test_weixin_generation_dispatch_atomic.py', 'tests/integration/test_weixin_generation_dispatch_integrity.py', 'tests/integration/test_weixin_dispatch.py', 'tests/integration/test_weixin_dispatch_atomic.py'], []),
 'final-http': (['tests/integration/test_weixin_authorization_routes.py', 'tests/integration/test_weixin_generation_routes.py', 'tests/integration/test_weixin_generation_routes_recovery.py', 'tests/integration/test_weixin_generation_head_routes.py'], []),
 'final-history': (['tests/integration/test_weixin_generation_service.py', 'tests/integration/test_weixin_generation_service_atomic.py', 'tests/integration/test_weixin_generation_ingress.py', 'tests/integration/test_weixin_generation_ingress_atomic.py'], []),
 'final-backup': (['tests/integration/test_weixin_generation_backup.py', 'tests/integration/test_weixin_generation_service_backup.py', 'tests/integration/test_weixin_provenance_backup.py'], []),
 'final-integrity': (['tests/integration/test_weixin_dispatch_integrity.py', 'tests/integration/test_weixin_generation_integrity.py', 'tests/integration/test_workspace_upgrade_semantic_preflight.py'], []),
 'final-schema': (['tests/integration/test_weixin_generation_dispatch_schema.py', 'tests/unit/test_domain.py'], []),
}
all_inputs = sorted(set([p.relative_to(ROOT).as_posix() for folder in ('src', 'tests') for p in (ROOT/folder).rglob('*.py')]
    + [p.relative_to(ROOT).as_posix() for p in (ROOT/'tests/fixtures').rglob('*.json')]
    + ['pyproject.toml','sources/upstream.lock.json','sources/specification-v2.0.md','schemas/review-report.v2.schema.json',
       'docs/plans/2026-10-25-weixin-dispatch-http-d2g5e.md']
    + [p.relative_to(ROOT).as_posix() for p in (ROOT/'scripts').glob('verify_*.py')]))
red_inputs = ['src/cn_contract/domain.py','src/cn_contract/weixin_inbox/conversation.py',
              'src/cn_contract/weixin_inbox/generation_dispatch.py','tests/integration/test_weixin_generation_dispatch_conversation.py']
def snapshot(paths):
    return {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in paths}
for label in sys.argv[1:]:
    paths = red_inputs if label.startswith('red-') else all_inputs
    if label in GROUPS:
        modules, extra = GROUPS[label]
        base = ROOT/'.local'/('dh-'+label)
        base = Path(str(base) + 'x'*(89-len(str(base))))
        assert len(str(base)) == 89
        args = [PY,'-B','-X','utf8','-m','pytest',*modules,*extra,'-q','--tb=short',
                '--basetemp='+str(base),'--junitxml='+str(OUT/(label+'.xml'))]
    else:
        args = [PY,'-B','-X','utf8',*{
            'gate-schema':['-m','cn_contract.cli','schema','--check'],
            'gate-defaults':['scripts/verify_defaults.py'],
            'gate-sources':['scripts/verify_sources.py','--mode','development'],
            'gate-dependencies':['scripts/verify_runtime_dependencies.py','--mode','development']}[label]]
    assert not (OUT/(label+'.json')).exists(), 'Do not overwrite prior evidence; use a fresh label.'
    before = snapshot(paths)
    start = datetime.now(timezone.utc).isoformat()
    clock = time.monotonic()
    with (OUT/(label+'.log')).open('wb') as output:
        run = subprocess.run([str(arg) for arg in args], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
    after = snapshot(paths)
    result = dict(label=label, argv=[str(arg) for arg in args], started_at=start,
                  ended_at=datetime.now(timezone.utc).isoformat(), seconds=round(time.monotonic()-clock,3),
                  exit_code=run.returncode, source_before=before, source_after=after)
    (OUT/(label+'.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({name:result[name] for name in ('label','exit_code','seconds')}), flush=True)
    print((OUT/(label+'.log')).read_text(encoding='utf-8',errors='replace')[-6000:], flush=True)
    assert before == after, 'Source changed during this verification run.'
    if run.returncode:
        raise SystemExit(run.returncode)
