"""Capture read-only baseline checks and reviewed byte identities."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path.cwd()
BASE = 'aa77af6903fd324bc3fd7cc4f5fb5b78a99a3aa9'
OUT = ROOT / '.local/context-provider-20261021'
FILES = (
    'AGENTS.md', 'CONTRIBUTING.md', 'docs/plans/2026-10-21-context-provider.md',
    'src/cn_contract/domain.py', 'src/cn_contract/assistant/providers/main.py',
    'src/cn_contract/assistant/providers/context.py',
    'src/cn_contract/assistant/providers/context_codec.py',
    'src/cn_contract/assistant/providers/deepseek_protocol.py',
    'src/cn_contract/assistant/providers/deepseek_transport.py',
    'tests/unit/test_assistant_context_codec.py',
    'tests/integration/test_assistant_context_provider.py',
    'tests/integration/test_deepseek_transport_refactor.py',
)

def baseline(path):
    return subprocess.check_output(['git', 'show', BASE + ':' + path], cwd=ROOT)

def node(source, name):
    for entry in ast.parse(source).body:
        if getattr(entry, 'name', None) == name:
            return ast.dump(entry, include_attributes=False)
        if isinstance(entry, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in entry.targets):
            return ast.dump(entry, include_attributes=False)
    raise AssertionError(name)

main_path = 'src/cn_contract/assistant/providers/main.py'
old_main = baseline(main_path).decode('utf-8-sig')
new_main = (ROOT / main_path).read_text(encoding='utf-8-sig')
checks = {name + '_AST_unchanged': node(old_main, name) == node(new_main, name)
          for name in ('_SYSTEM', 'build_request')}
old_domain = baseline('src/cn_contract/domain.py').decode('utf-8-sig').replace('\r\n', '\n')
new_domain = (ROOT / 'src/cn_contract/domain.py').read_text(encoding='utf-8-sig')
checks['existing_domain_prefix_unchanged'] = new_domain.startswith(old_domain)
unchanged = ('src/cn_contract/assistant/providers/registry.py',
             'src/cn_contract/assistant/providers/policy.py',
             'src/cn_contract/assistant/runner.py',
             'src/cn_contract/assistant/model_integrity.py')
for path in unchanged:
    checks[path + '_unchanged'] = baseline(path).decode('utf-8-sig').replace('\r\n', '\n') == (ROOT / path).read_text(encoding='utf-8-sig')
assert all(checks.values()), checks
result = {
    'baseline': BASE, 'captured_utc': datetime.now(timezone.utc).isoformat(),
    'workspace': str(ROOT), 'python': sys.version, 'static_checks': checks,
    'files': [{'path': path, 'sha256': hashlib.sha256((ROOT / path).read_bytes()).hexdigest()}
              for path in FILES],
    'test_command': json.loads((OUT / 'standards-command.json').read_text(encoding='utf-8-sig')),
    'test_exit': int((OUT / 'standards-probes.exit').read_text()),
    'actual_independent_test_count': 6,
    'limits': ['synthetic loopback only', 'no broad suite', 'no application send wiring',
               'no real model or credentials', 'no product or existing test edits'],
}
(OUT / 'standards-evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'static_checks': checks, 'reviewed_files': len(FILES)}, ensure_ascii=False))
