"""Repeatable Chinese PII and DOCX structural probes; synthetic fixtures only."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import time

from backup_experiment import no_links

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parents[1]
ROOT = HARNESS.parent
LOCAL = HARNESS / '.local' / 'audit-followups'

SAMPLES = [
    {'id': 'labelled-control', 'text': '姓名：赵明远。甲方：昆陵合成科技有限公司。金额 12000 元，2026年11月12日付款。',
     'entities': ['赵明远', '昆陵合成科技有限公司'], 'preserve': ['12000', '2026年11月12日']},
    {'id': 'unlabelled-chinese-person', 'text': '赵明远于2026年11月12日签收虚构测试材料。',
     'entities': ['赵明远'], 'preserve': ['2026年11月12日']},
    {'id': 'ocr-linebreak-person', 'text': '姓名：赵\n明远。金额 12000 元。',
     'entities': ['赵\n明远'], 'preserve': ['12000']},
    {'id': 'ocr-linebreak-organization', 'text': '昆陵合成科技有限\n公司于2026年11月12日签约。',
     'entities': ['昆陵合成科技有限\n公司'], 'preserve': ['2026年11月12日']},
    {'id': 'generic-negative-control', 'text': '学校应在2026年11月12日前支付12000元。',
     'entities': [], 'preserve': ['学校', '2026年11月12日', '12000']},
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def offline():
    os.environ.update(HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', DO_NOT_TRACK='1',
                      OMP_NUM_THREADS='2', MKL_NUM_THREADS='2', HF_HOME=str(LOCAL / 'model-cache'))
    def blocked(*args, **kwargs):
        raise RuntimeError('Experiment forbids network/model downloads during inference')
    socket.socket.connect = blocked
    socket.socket.connect_ex = blocked
    socket.create_connection = blocked


def fixtures(directory):
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    for legacy in (False, True):
        doc = Document()
        doc.add_paragraph('完全虚构样本。金额单位为元，禁止推断真实案件。')
        table = doc.add_table(rows=3, cols=3)
        for row, values in zip(table.rows, [('付款阶段', '', '金额（元）'), ('第一期', '交付后', '12000'), ('第二期', '验收后', '8000')]):
            for cell, value in zip(row.cells, values):
                cell.text = value
        if legacy:
            for column, mode in enumerate(('restart', 'continue')):
                merge = OxmlElement('w:hMerge')
                merge.set(qn('w:val'), mode)
                table.cell(0, column)._tc.get_or_add_tcPr().append(merge)
        else:
            table.cell(0, 0).merge(table.cell(0, 1))
        doc.save(directory / ('legacy-hmerge.docx' if legacy else 'gridspan-control.docx'))


def baseline():
    os.environ['QX_LEGACY_ROOT'] = str(ROOT)
    sys.path.insert(0, str(HARNESS / 'bridge'))
    import privacy
    import reader
    from store import MaterialStore
    no_links(LOCAL)
    LOCAL.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix='candidates-', dir=LOCAL))
    started = time.monotonic()
    pii = []
    for sample in SAMPLES:
        candidates = privacy._candidates(sample['text'], [], 'standard')
        covered = set()
        for value in candidates:
            offset = 0
            while (offset := sample['text'].find(value, offset)) != -1:
                covered.update(range(offset, offset + len(value)))
                offset += len(value)
        recalls = []
        for entity in sample['entities']:
            offset = sample['text'].index(entity)
            recalls.append(all(offset + i in covered for i, c in enumerate(entity) if not c.isspace()))
        safe, count = privacy._redact(sample['text'], [], run / (sample['id'] + '-mapping.sqlite'))
        pii.append({**sample, 'candidates': candidates, 'safe_text': safe, 'replacements': count,
                    'entity_covered': recalls, 'facts_preserved': all(value in safe for value in sample['preserve'])})
    inputs = run / 'synthetic-inputs'
    inputs.mkdir()
    fixtures(inputs)
    store = MaterialStore(run)
    parsed = []
    for source in sorted(inputs.glob('*.docx')):
        before = digest(source)
        store.register(source)
        result = reader.parse(store, source)
        with store.db() as db:
            chunks = [dict(row) for row in db.execute('SELECT location,text FROM chunks WHERE path=? ORDER BY ordinal', (source.relative_to(run).as_posix(),))]
        text = '\n'.join(c['text'] for c in chunks)
        grids = [json.loads(c['location'].split(':grid:', 1)[1].split(':chars:', 1)[0]) for c in chunks if ':grid:' in c['location']]
        merged = any(any(c.get('start_col') == 1 and c.get('end_col') == 2 for c in g.get('cells', [])) for g in grids)
        parsed.append({'sample': source.name, 'sha256': before, 'unchanged': before == digest(source),
                       'result': result, 'chunks': chunks,
                       'texts_preserved': all(s in text for s in ['付款阶段', '金额（元）', '第一期', '12000', '第二期', '8000']),
                       'first_row_merge_1_to_2_preserved': merged})
    report = {'synthetic_only': True, 'python': sys.version.split()[0], 'privacy': pii, 'documents': parsed,
              'seconds': round(time.monotonic() - started, 3), 'baseline_sources': {name: digest(HARNESS / 'bridge' / name) for name in ['privacy.py', 'reader.py', 'material_tables.py']},
              'candidate_modules_available': {name: bool(importlib.util.find_spec(name)) for name in ['presidio_analyzer', 'spacy', 'docling', 'torch']}}
    (run / 'baseline.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    assert pii[0]['entity_covered'] == [True, True] and all(p['facts_preserved'] for p in pii)
    assert all(d['unchanged'] and d['texts_preserved'] for d in parsed)
    assert next(d for d in parsed if d['sample'] == 'gridspan-control.docx')['first_row_merge_1_to_2_preserved']
    assert not next(d for d in parsed if d['sample'] == 'legacy-hmerge.docx')['first_row_merge_1_to_2_preserved']
    print(json.dumps({'baseline': str(run / 'baseline.json'), 'pii_entities_covered': sum(sum(p['entity_covered']) for p in pii),
                      'pii_entities_expected': sum(len(p['entities']) for p in pii), 'documents': len(parsed)}, ensure_ascii=True))


def docling_comparison(baseline_path):
    no_links(Path(baseline_path))
    path = Path(baseline_path).resolve()
    if not path.is_relative_to(LOCAL.resolve()) or path.name != 'baseline.json':
        raise ValueError('Only generated experiment baseline paths are allowed')
    data = json.loads(path.read_text(encoding='utf-8'))
    assert data.get('synthetic_only') is True
    offline()
    from docling.document_converter import DocumentConverter
    from docling.datamodel.base_models import InputFormat
    converter = DocumentConverter(allowed_formats=[InputFormat.DOCX])
    started = time.monotonic()
    outputs = []
    for expected in data['documents']:
        assert expected['sample'] in {'gridspan-control.docx', 'legacy-hmerge.docx'}
        source = path.parent / 'synthetic-inputs' / expected['sample']
        no_links(source)
        assert digest(source) == expected['sha256']
        begin = time.monotonic()
        result = converter.convert(source)
        text = result.document.export_to_markdown()
        tables = [table.model_dump(mode='json') for table in result.document.tables]
        merged = any(any(cell.get('start_row_offset_idx') == 0 and cell.get('start_col_offset_idx') == 0
                         and cell.get('end_col_offset_idx') == 2 for cell in table['data']['table_cells']) for table in tables)
        outputs.append({'sample': source.name, 'sha256': digest(source), 'unchanged': digest(source) == expected['sha256'],
                        'status': str(result.status), 'seconds': round(time.monotonic() - begin, 3),
                        'markdown': text, 'tables': tables,
                        'texts_preserved': all(s in text for s in ['付款阶段', '金额（元）', '第一期', '12000', '第二期', '8000']),
                        'first_row_merge_1_to_2_preserved': merged})
    report = {'synthetic_only': True, 'candidate': 'docling-slim', 'version': importlib.metadata.version('docling-slim'),
              'python': sys.version.split()[0], 'baseline_sha256': digest(path), 'documents': outputs,
              'network_blocked': True, 'models_used': [], 'seconds': round(time.monotonic() - started, 3)}
    report['structure_improvements'] = sum(not old['first_row_merge_1_to_2_preserved'] and new['first_row_merge_1_to_2_preserved']
                                           for old, new in zip(data['documents'], outputs))
    report['structure_regressions'] = sum(old['first_row_merge_1_to_2_preserved'] and not new['first_row_merge_1_to_2_preserved']
                                          for old, new in zip(data['documents'], outputs))
    assert all(item['unchanged'] for item in outputs), 'Candidate modified a source document'
    target = path.parent / 'docling-comparison.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'result': str(target), 'documents': len(outputs)}, ensure_ascii=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--docling-baseline', help='Compare Docling with the generated baseline; network is blocked')
    arguments = parser.parse_args()
    offline()
    if arguments.docling_baseline:
        docling_comparison(arguments.docling_baseline)
    else:
        baseline()
