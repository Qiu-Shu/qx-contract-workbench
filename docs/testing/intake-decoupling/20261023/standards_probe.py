"""Independent, synthetic-only Standards checks for CH-00A3."""
import ast
import copy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = '1a73e36f687b6dc0eab98892149737c02e8d9ce6'
PATHS = ('src/cn_contract/intake/service.py', 'src/cn_contract/web/services.py',
         'src/cn_contract/web/storage.py', 'src/cn_contract/matters.py',
         'src/cn_contract/record_codec.py')


def digest_inputs():
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in PATHS}


def old(path):
    return subprocess.check_output(['git', 'show', BASE + ':' + path], cwd=ROOT).decode('utf-8')


def functions(source):
    return {n.name: n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)}


before = digest_inputs()
old_service = functions(old('src/cn_contract/web/services.py'))['create_matter']
for node in ast.walk(old_service):
    if isinstance(node, ast.ImportFrom):
        assert node.level == 2
        node.level = 1
new_service = functions((ROOT / 'src/cn_contract/matters.py').read_text('utf-8'))['create_matter']
assert ast.dump(old_service) == ast.dump(new_service)
old_codec = functions(old('src/cn_contract/web/storage.py'))
new_codec = functions((ROOT / 'src/cn_contract/record_codec.py').read_text('utf-8'))
for name in ('now', 'encode', 'sha'):
    assert ast.dump(old_codec[name]) == ast.dump(new_codec[name])
old_intake = functions(old('src/cn_contract/intake/service.py'))
new_intake = functions((ROOT / 'src/cn_contract/intake/service.py').read_text('utf-8'))
for node in ast.walk(old_intake['convert']):
    if isinstance(node, ast.Name) and node.id == 'services':
        node.id = 'matters'
new_intake['export'].body = [n for n in new_intake['export'].body
                             if not isinstance(n, ast.ImportFrom) or n.module != 'docx']
assert old_intake.keys() == new_intake.keys()
assert all(ast.dump(old_intake[k]) == ast.dump(new_intake[k]) for k in old_intake)
print('PASS 1: all moved record/create_matter AST and intake behavior AST preserved')

# Compile only pre-existing pure functions; do not import the old HTTP stack.
namespace = {'datetime': datetime, 'timezone': timezone, 'json': json, 'hashlib': hashlib}
body = [copy.deepcopy(old_codec[name]) for name in ('now', 'encode', 'sha')]
exec(compile(ast.fix_missing_locations(ast.Module(body=body, type_ignores=[])), '<baseline-codec>', 'exec'), namespace)
from cn_contract import record_codec
values = ({'z': ['合成记录', True, None, -0.0], 'a': {'换行': '\n', 'emoji': '☁'}},
          [], {'integer': 10**35, 'float': 0.125}, {'empty': ''})
for value in values:
    assert record_codec.encode(value) == namespace['encode'](value)
    assert record_codec.sha(value) == namespace['sha'](value)
for value in ({'x': float('nan')}, {'x': float('inf')}, {'x': Decimal('1.25')}, {'x': object()}):
    errors = []
    for codec in (record_codec.encode, namespace['encode']):
        try:
            codec(value)
        except (TypeError, ValueError) as error:
            errors.append(type(error))
    assert len(errors) == 2 and errors[0] is errors[1]
assert record_codec.now().utcoffset().total_seconds() == 0
print('PASS 2: four synthetic records, four rejected inputs, hashes and UTC retain baseline behavior')

probe = '''
import importlib.abc
import sys
blocked = ('cn_contract.web', 'fastapi', 'docx', 'cn_contract.documents.ingest', 'cn_contract.review.workflow')
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + '.') for name in blocked):
            raise AssertionError('reverse/heavy dependency: ' + fullname)
sys.meta_path.insert(0, Guard())
from cn_contract.intake import service
assert not any(n == p or n.startswith(p + '.') for n in sys.modules for p in blocked)
assert service.convert.__globals__['matters'].__name__ == 'cn_contract.matters'
print('PASS 3: fresh-process intake import has no Web/FastAPI/Word/ingest/review dependency')
'''
result = subprocess.run([sys.executable, '-X', 'utf8', '-c', probe], cwd=ROOT, capture_output=True, text=True, timeout=30)
assert result.returncode == 0, result.stderr
print(result.stdout.strip())

from cn_contract import matters
from cn_contract.web import services, storage
assert services.create_matter is matters.create_matter
assert all(getattr(storage, name) is getattr(record_codec, name) for name in ('now', 'encode', 'sha'))
print('PASS 4: old Web exports remain exact aliases of new application functions')
after = digest_inputs()
assert before == after
report = {'baseline': BASE, 'checks': 4, 'passed': 4, 'failed': 0, 'synthetic_only': True,
          'network_calls': 0, 'database_opened': False, 'input_hashes': after, 'inputs_unchanged': before == after}
(Path(__file__).parent / 'standards-probe.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
