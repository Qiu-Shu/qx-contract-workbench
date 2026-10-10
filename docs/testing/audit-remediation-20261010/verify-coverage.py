"""Reconcile actual staged regression XML; never equate it to one clean run."""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
nodes = json.loads((HERE / 'collection.json').read_text(encoding='utf-8'))

def key(node):
    parts = node.split('::')
    return parts[0][:-3].replace('/', '.') + ''.join('.' + p for p in parts[1:-1]), parts[-1]

mapping = {key(n): n for n in nodes}
assert len(mapping) == len(nodes) == 1599
resolved = {}
counts = {}
for name in ['full.xml', 'remainder.xml', 'harness-and-source-final.xml', 'format-binding-final.xml']:
    records = ET.parse(HERE / name).getroot().findall('.//testcase')
    count = dict(passed=0, failed=0, errors=0, skipped=0, incomplete=0)
    for record in records:
        if 'classname' not in record.attrib:
            assert name == 'full.xml' and len(record) == 0
            count['incomplete'] += 1
            continue
        node = mapping[(record.attrib['classname'], record.attrib['name'])]
        state = next((s for s, tag in [('failed', 'failure'), ('errors', 'error'), ('skipped', 'skipped')]
                      if record.find(tag) is not None), 'passed')
        count[state] += 1
        resolved[node] = dict(state=state, evidence=name)
    counts[name] = count
assert counts['full.xml'] == dict(passed=1271, failed=0, errors=0, skipped=0, incomplete=1)
assert counts['remainder.xml'] == dict(passed=327, failed=1, errors=0, skipped=0, incomplete=0)
assert counts['harness-and-source-final.xml'] == dict(passed=80, failed=0, errors=0, skipped=0, incomplete=0)
assert set(resolved) == set(nodes)
assert all(r['state'] == 'passed' for r in resolved.values())
before = json.loads((HERE / 'full-receipt.json').read_text(encoding='utf-8'))['before']
current = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in before}
changed = sorted(p for p in before if current[p] != before[p])
assert changed == ['plugins/qx-contract-offline-codex/runtime-binding.json',
                   'plugins/qx-contract-offline-local/runtime-binding.json',
                   'src/cn_contract/acceptance/assisted_registry.py',
                   'tests/unit/test_mcp_offline.py', 'tests/unit/test_patch_preconditions.py'], changed
cleanup = json.loads((HERE / 'format-only-cleanup.json').read_text(encoding='utf-8'))
assert before[cleanup['source']] == cleanup['before_sha256']
assert current[cleanup['source']] == cleanup['after_sha256']
assert cleanup['ast_unchanged'] is True
result = dict(collected=1599, latest_unique_passed=1599, missing=[], final_failures=[],
              single_uninterrupted_full_run_passed=False, raw_counts=counts,
              changes_since_prefix=changed, final_input_hashes=current,
              xml_sha256={n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in counts},
              resolved=resolved)
(HERE / 'regression-coverage.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: v for k, v in result.items() if k not in ('final_input_hashes', 'resolved')}, ensure_ascii=False, indent=2))
