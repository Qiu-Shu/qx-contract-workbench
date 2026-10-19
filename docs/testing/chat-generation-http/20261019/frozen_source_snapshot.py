"""Hash only explicit backend build inputs, never a workspace or real materials."""
import hashlib
import json
from pathlib import Path
import sys

base = Path(__file__).resolve().parent
root = base.parents[1]
selected = [root/'desktop/backend.spec', root/'scripts/desktop_backend_entry.py', root/'pyproject.toml']
for relative in ('src/cn_contract','config','prompts','rules','tests/fixtures/assisted-v1','tests/fixtures/synthetic'):
    selected.extend(path for path in (root/relative).rglob('*')
                    if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc')
values = {path.relative_to(root).as_posix():hashlib.sha256(path.read_bytes()).hexdigest()
          for path in sorted(set(selected))}
payload = json.dumps(values, sort_keys=True, ensure_ascii=False, separators=(',',':')).encode('utf-8')
snapshot = {'file_count':len(values), 'source_sha256':hashlib.sha256(payload).hexdigest(), 'files':values}
(base/sys.argv[1]).write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'file_count':snapshot['file_count'],'source_sha256':snapshot['source_sha256']}))
