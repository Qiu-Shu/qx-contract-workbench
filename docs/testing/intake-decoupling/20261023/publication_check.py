import hashlib
import json
from pathlib import Path
import re
import subprocess

root = Path.cwd()
out = root / '.local/intake-decoupling-20261023'
evidence = root / 'docs/testing/intake-decoupling/20261023'
verification = json.loads((out / 'target-verification.json').read_text(encoding='utf-8'))
changed = [p for p, sha in verification['inputs_after'].items()
           if hashlib.sha256((root / p).read_bytes()).hexdigest() != sha]
assert not changed, changed
manifest = json.loads((evidence / 'evidence-manifest.json').read_text(encoding='utf-8'))
assert all(hashlib.sha256((evidence / row['path']).read_bytes()).hexdigest() == row['sha256']
           and (evidence / row['path']).stat().st_size == row['bytes'] for row in manifest['files'])
docs = [Path(p) for p in ('README.md', 'TODO.md', 'CONTRIBUTING.md', 'docs/TASK_STATUS.md',
    'docs/plans/2026-10-23-intake-decoupling.md', 'docs/plans/2026-10-23-profile-draft-readiness.md',
    'docs/testing/intake-decoupling/20261023/README.md',
    'docs/testing/model-ux/20261022/README.md', 'docs/testing/selection-gui/20261021/README.md')]
missing, links = [], 0
for doc in docs:
    for target in re.findall(r'\]\(([^)]+)\)', doc.read_text(encoding='utf-8')):
        if '://' in target or target.startswith('#'): continue
        links += 1
        path = target.split('#', 1)[0].strip('<>')
        if not (doc.parent / path).exists(): missing.append([str(doc), path])
assert not missing, missing
subprocess.run(['git', 'diff', '--check'], check=True)
report = {'source_inputs_unchanged': len(verification['inputs_after']),
          'evidence_entries_verified': len(manifest['files']), 'local_links_checked': links,
          'missing_links': missing, 'diff_check_exit': 0}
(out / 'publication-check.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report))
