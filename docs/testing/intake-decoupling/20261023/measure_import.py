"""Same fresh-interpreter intake import probe, optional Python allocation tracing."""
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys

probe = '''
import json, sys, time, tracemalloc
traced = sys.argv[1] == 'traced'
if traced: tracemalloc.start()
start = time.perf_counter()
from cn_contract.intake import service
elapsed = time.perf_counter() - start
peak = tracemalloc.get_traced_memory()[1] if traced else None
print(json.dumps(dict(seconds=elapsed, python_peak_bytes=peak, modules=len(sys.modules),
    web_services='cn_contract.web.services' in sys.modules,
    web_storage='cn_contract.web.storage' in sys.modules,
    docx='docx' in sys.modules, ingestion='cn_contract.documents.ingest' in sys.modules,
    review='cn_contract.review.workflow' in sys.modules)))
'''
rows = []
for mode, count in (('untraced', 7), ('traced', 3)):
    for _ in range(count):
        result = subprocess.run([sys.executable, '-X', 'utf8', '-c', probe, mode],
                                capture_output=True, text=True, timeout=45, check=True)
        rows.append({'mode': mode, **json.loads(result.stdout)})
value = dict(python=sys.version, probe_sha256=hashlib.sha256(probe.encode()).hexdigest(), samples=rows,
    untraced_seconds_median=statistics.median(r['seconds'] for r in rows if r['mode']=='untraced'),
    python_peak_bytes_median=statistics.median(r['python_peak_bytes'] for r in rows if r['mode']=='traced'))
Path(sys.argv[1]).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k:v for k,v in value.items() if k!='samples'}))
