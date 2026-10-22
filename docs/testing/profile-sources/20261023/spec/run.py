import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[3]
output = Path(__file__).resolve().parent
product = root / 'src/cn_contract/assistant/profile_sources.py'
before = hashlib.sha256(product.read_bytes()).hexdigest()
command = [sys.executable, '-X', 'utf8', '-m', 'pytest', str(output/'test_spec.py'), '-q',
           '--basetemp', str(output / ('tmp-'+uuid.uuid4().hex[:8])),
           '--junitxml', str(output/'results.xml')]
result = subprocess.run(command, cwd=root, text=True, encoding='utf-8', capture_output=True)
(output/'output.log').write_text(result.stdout+result.stderr, encoding='utf-8')
after = hashlib.sha256(product.read_bytes()).hexdigest()
document = ET.parse(output/'results.xml')
cases = document.findall('.//testcase')
report = {'command':command, 'cwd':str(root), 'exit_code':result.returncode, 'tests':len(cases),
          'failures':len(document.findall('.//failure')), 'errors':len(document.findall('.//error')),
          'skipped':len(document.findall('.//skipped')), 'product_sha256_before':before,
          'product_sha256_after':after, 'product_stable':before==after}
(output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False))
print(result.stdout)
sys.exit(result.returncode)
