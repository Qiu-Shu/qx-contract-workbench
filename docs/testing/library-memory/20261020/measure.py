import csv
import gc
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
import tracemalloc

from cn_contract import domain as d
from cn_contract.assistant.tools.library import LegalLibraryAdapter
from cn_contract.library import service
from cn_contract.library.csv_source import import_case_file
from cn_contract.library.index import activate_generation, build_generation, current_generation

out = Path('.local/library-memory-20261020')
out.mkdir(parents=True, exist_ok=True)
root = out/'synthetic-library'
source = out/'synthetic.csv'
body = '甲乙丙丁。'*50000 + '目标租赁。\r\n结束'
if not root.exists():
    with source.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['标题', '案号', '法院', '文书内容'])
        writer.writerow(['完全虚构性能样本', '(2025)虚构1号', '虚构法院', body])
    import_case_file(root, source, 'synthetic-memory')
    activate_generation(root, build_generation(root))

inputs = ('src/cn_contract/library/text.py', 'src/cn_contract/library/service.py',
          'src/cn_contract/assistant/tools/library.py')
hashes = {p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in inputs}
functions = {'library_search':lambda:service.search(root,d.LibraryQuery(text='目标租赁', limit=2)),
             'assistant_adapter':lambda:LegalLibraryAdapter(root).search(d.AssistantLibraryQuery(text='目标租赁',limit=2))}
result = {'body_characters':len(body), 'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
          'generation_id':current_generation(root)['generation_id'], 'inputs':hashes,
          'scope':'One synthetic record, warm rank cache; Python traced peak separate from untraced timings. Not RSS/GUI/cold-start/installer.'}
for name, function in functions.items():
    expected = function().model_dump_json()
    timings, peaks = [], []
    for _ in range(3):
        started = time.perf_counter()
        actual = function().model_dump_json()
        timings.append(time.perf_counter()-started)
        assert actual == expected
    for _ in range(3):
        gc.collect()
        tracemalloc.start()
        try:
            value = function()
            peaks.append(tracemalloc.get_traced_memory()[1])
        finally:
            tracemalloc.stop()
        assert value.model_dump_json() == expected
    result[name] = {'seconds':timings,'median_seconds':statistics.median(timings),
        'traced_peak_bytes':peaks,'median_peak_bytes':statistics.median(peaks),
        'result_sha256':hashlib.sha256(expected.encode()).hexdigest()}
assert hashes == {p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in inputs}
(out/(sys.argv[1]+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({name:result[name] for name in functions},ensure_ascii=False),flush=True)
