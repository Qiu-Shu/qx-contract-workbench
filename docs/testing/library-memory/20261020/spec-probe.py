"""CH-00B2 independent synthetic equivalence and evidence checks."""
import csv
import hashlib
import json
from pathlib import Path
import random
from unittest.mock import patch

from cn_contract import domain as d
from cn_contract.assistant.tools import library as adapter_module
from cn_contract.library import service
from cn_contract.library.text import normalize, original_span


def legacy_span(source, start, end):
    _, mapping = normalize(source, with_map=True)
    return mapping[start], mapping[end - 1] + 1


root = Path('.local/library-memory-20261020')
rng = random.Random(20261020)
alphabet = '甲乙㍻年Ａßﬁﬃe\u0301\r\n\t \u00a0\u200b\u200c\u200d\u2060\ufeff𠀀😀\u2028\u3000'
span_checks = 0
for _ in range(500):
    source = ''.join(rng.choice(alphabet) for _ in range(rng.randrange(1, 50)))
    normalized, mapping = normalize(source, with_map=True)
    assert normalize(source) == normalized
    if not normalized:
        continue
    for _ in range(20):
        start = rng.randrange(len(normalized))
        end = rng.randrange(start + 1, len(normalized) + 1)
        assert original_span(source, start, end) == (mapping[start], mapping[end - 1] + 1)
        span_checks += 1

baseline = json.loads((root / 'baseline.json').read_text(encoding='utf-8'))
final = json.loads((root / 'final.json').read_text(encoding='utf-8'))
assert baseline['source_sha256'] == final['source_sha256'] == hashlib.sha256((root/'synthetic.csv').read_bytes()).hexdigest()
assert baseline['generation_id'] == final['generation_id']
with (root/'synthetic.csv').open(encoding='utf-8', newline='') as stream:
    records = list(csv.DictReader(stream))
assert len(records) == 1
assert len(records[0]['文书内容']) == baseline['body_characters'] == final['body_characters'] == 250009
for path, expected in final['inputs'].items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected

library_root = root / 'synthetic-library'
calls = {
    'library_search':lambda:service.search(library_root, d.LibraryQuery(text='目标租赁', limit=2)),
    'assistant_adapter':lambda:adapter_module.LegalLibraryAdapter(library_root).search(d.AssistantLibraryQuery(text='目标租赁', limit=2)),
}
numbers = {}
for name, function in calls.items():
    current = function().model_dump_json()
    with patch.object(service, 'original_span', legacy_span), patch.object(adapter_module, 'original_span', legacy_span):
        reference = function().model_dump_json()
    assert current == reference
    digest = hashlib.sha256(current.encode()).hexdigest()
    assert digest == baseline[name]['result_sha256'] == final[name]['result_sha256']
    numbers[name] = {
        'peak_reduction_pct':100*(1-final[name]['median_peak_bytes']/baseline[name]['median_peak_bytes']),
        'median_time_change_pct':100*(final[name]['median_seconds']/baseline[name]['median_seconds']-1),
        'output_equal':True,
    }
print(json.dumps({'span_checks':span_checks, 'synthetic_records':len(records),
                  'body_characters':len(records[0]['文书内容']), 'inputs_match_final':True,
                  'end_to_end':numbers}, ensure_ascii=False))
