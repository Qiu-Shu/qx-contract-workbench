"""Offline, synthetic-only admission probes; reuse pinned local candidate environments."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import socket
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
HARNESS = HERE.parents[1]
FIXTURES = HERE / 'privacy-docling-fixtures.json'
ROOT = Path('D:/CodexChecks/AI-Shixiong-candidate-admission-20261112/privacy-docling')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def offline():
    os.environ.update(HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', DO_NOT_TRACK='1',
                      HF_HOME=str(ROOT / 'model-cache'), OMP_NUM_THREADS='2', MKL_NUM_THREADS='2',
                      CUDA_VISIBLE_DEVICES='-1')
    def blocked(*args, **kwargs):
        raise RuntimeError('This synthetic probe forbids network access')
    socket.socket.connect = blocked
    socket.socket.connect_ex = blocked
    socket.create_connection = blocked


def metric(sample, covered):
    expected, entities, offsets = set(), [], {}
    for entity in sample['entities']:
        offset = sample['text'].index(entity, offsets.get(entity, 0))
        offsets[entity] = offset + len(entity)
        positions = {offset + i for i, c in enumerate(entity) if not c.isspace()}
        expected.update(positions)
        entities.append(positions <= covered)
    safe = ''.join('[PII]' if i in covered else c for i, c in enumerate(sample['text']))
    return {'entity_covered': entities, 'facts_preserved': all(s in safe for s in sample['preserve']),
            'non_entity_characters_masked': sum(i not in expected and not sample['text'][i].isspace() for i in covered),
            'safe_text': safe}


def self_check():
    probe = {'text':'甲乙甲乙 100', 'entities':['甲乙','甲乙'], 'preserve':['100']}
    assert metric(probe, {0, 1})['entity_covered'] == [True, False]
    assert metric(probe, {0, 1, 2, 3})['non_entity_characters_masked'] == 0
    assert not metric(probe, {5})['facts_preserved']
    probe = {'text':'甲\n乙', 'entities':['甲\n乙'], 'preserve':[]}
    assert metric(probe, {0, 2})['entity_covered'] == [True]


def make_docx(spec, path):
    from docx import Document
    document = Document()
    document.add_paragraph('完全虚构，仅用于本地解析准入测试。')
    if spec['kind'] == 'vertical':
        table = document.add_table(rows=3, cols=3)
        for row, values in zip(table.rows, [('项目','阶段','金额（元）'), ('合成项目','首期','12000'), ('','次期','8000')]):
            for cell, value in zip(row.cells, values):
                cell.text = value
        table.cell(1, 0).merge(table.cell(2, 0))
    else:
        table = document.add_table(rows=1, cols=1)
        table.cell(0, 0).text = '外层说明'
        inner = table.cell(0, 0).add_table(rows=2, cols=2)
        for row, values in zip(inner.rows, [('内层项目','内层金额'), ('合成配件','3000')]):
            for cell, value in zip(row.cells, values):
                cell.text = value
    document.save(path)


def baseline(fixtures):
    os.environ['QX_LEGACY_ROOT'] = str(HARNESS.parent)
    sys.path.insert(0, str(HARNESS / 'bridge'))
    import privacy
    import reader
    from store import MaterialStore
    pii = []
    for sample in fixtures['privacy']:
        candidates = privacy._candidates(sample['text'], [], 'standard')
        covered = set()
        for value in candidates:
            offset = 0
            while (offset := sample['text'].find(value, offset)) != -1:
                covered.update(range(offset, offset + len(value)))
                offset += len(value)
        safe, count = privacy._redact(sample['text'], [], ROOT / (sample['id'] + '-mapping.sqlite'))
        pii.append({**sample, **metric(sample, covered), 'candidates':candidates,
                    'product_safe_text':safe, 'product_replacements':count,
                    'product_facts_preserved':all(s in safe for s in sample['preserve'])})
    store = MaterialStore(ROOT)
    outputs = []
    inputs = ROOT / 'inputs'
    inputs.mkdir()
    for spec in fixtures['documents']:
        path = inputs / spec['name']
        make_docx(spec, path)
        before = digest(path)
        store.register(path)
        result = reader.parse(store, path)
        with store.db() as db:
            chunks = [dict(row) for row in db.execute('SELECT location,text FROM chunks WHERE path=? ORDER BY ordinal', (path.relative_to(ROOT).as_posix(),))]
        text = '\n'.join(c['text'] for c in chunks)
        grids = [json.loads(c['location'].split(':grid:', 1)[1].split(':chars:', 1)[0]) for c in chunks if ':grid:' in c['location']]
        if spec['kind'] == 'vertical':
            structure = any(cell.get('start_col') == 1 and cell.get('vmerge') == 'continue' and cell.get('owner') is not None for g in grids for cell in g['cells'])
        else:
            structure = any(c['location'].count('/tbl[') >= 2 for c in chunks)
        outputs.append({**spec, 'sha256':before, 'unchanged':digest(path) == before, 'result':result, 'chunks':chunks,
                        'text_preserved':all(s in text for s in spec['required_text']), 'structure_preserved':structure})
    return {'privacy':pii, 'documents':outputs,
            'source_hashes':{name:digest(HARNESS / 'bridge' / name) for name in ('privacy.py','reader.py','material_tables.py')}}


def get_baseline(fixtures):
    data = json.loads((ROOT / 'baseline.json').read_text(encoding='utf-8'))
    assert data['synthetic_only'] and data['fixture_sha256'] == digest(FIXTURES)
    assert [s['id'] for s in data['privacy']] == [s['id'] for s in fixtures['privacy']]
    return data


def presidio(fixtures):
    old = get_baseline(fixtures)
    versions = {p:importlib.metadata.version(p) for p in ('presidio-analyzer','spacy','spacy-pkuseg','zh-core-web-sm')}
    assert versions == {'presidio-analyzer':'2.2.366','spacy':'3.8.18','spacy-pkuseg':'1.0.2','zh-core-web-sm':'3.8.0'}
    import spacy
    spacy.require_cpu()
    from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
    from presidio_analyzer.nlp_engine import SpacyNlpEngine
    from presidio_analyzer.predefined_recognizers import SpacyRecognizer
    started = time.monotonic()
    engine = SpacyNlpEngine(models=[{'lang_code':'zh','model_name':'zh_core_web_sm'}])
    registry = RecognizerRegistry(supported_languages=['zh'])
    registry.add_recognizer(SpacyRecognizer(supported_language='zh', supported_entities=['PERSON','ORGANIZATION']))
    analyzer = AnalyzerEngine(nlp_engine=engine, registry=registry, supported_languages=['zh'])
    loaded = time.monotonic() - started
    rows = []
    for sample, previous in zip(fixtures['privacy'], old['privacy']):
        begin = time.monotonic()
        predictions = analyzer.analyze(text=sample['text'], language='zh', entities=['PERSON','ORGANIZATION'], score_threshold=0.5)
        seconds = time.monotonic() - begin
        covered, spans = set(), []
        for p in predictions:
            assert 0 <= p.start < p.end <= len(sample['text'])
            covered.update(range(p.start, p.end))
            spans.append({'start':p.start,'end':p.end,'type':p.entity_type,'score':p.score,'text':sample['text'][p.start:p.end]})
        rows.append({**sample, **metric(sample, covered), 'spans':spans, 'seconds':seconds,
                     'baseline_entity_covered':previous['entity_covered']})
    return {'versions':versions, 'model_load_seconds':loaded, 'samples':rows,
            'expected_entities':sum(len(s['entities']) for s in rows),
            'covered_entities':sum(sum(s['entity_covered']) for s in rows),
            'baseline_covered_entities':sum(sum(s['baseline_entity_covered']) for s in rows),
            'newly_covered':sum(not b and a for s in rows for b,a in zip(s['baseline_entity_covered'],s['entity_covered'])),
            'regressed':sum(b and not a for s in rows for b,a in zip(s['baseline_entity_covered'],s['entity_covered'])),
            'facts_preserved_samples':sum(s['facts_preserved'] for s in rows),
            'non_entity_characters_masked':sum(s['non_entity_characters_masked'] for s in rows),
            'inference_seconds':sum(s['seconds'] for s in rows)}


def docling(fixtures):
    old = get_baseline(fixtures)
    assert importlib.metadata.version('docling-slim') == '2.150.0'
    from docling.document_converter import DocumentConverter
    from docling.datamodel.base_models import InputFormat
    converter = DocumentConverter(allowed_formats=[InputFormat.DOCX])
    outputs = []
    for spec in old['documents']:
        path = ROOT / 'inputs' / spec['name']
        assert digest(path) == spec['sha256']
        begin = time.monotonic()
        result = converter.convert(path)
        seconds = time.monotonic() - begin
        text = result.document.export_to_markdown()
        tables = [t.model_dump(mode='json') for t in result.document.tables]
        if spec['kind'] == 'vertical':
            structure = any(c.get('start_row_offset_idx') == 1 and c.get('end_row_offset_idx') == 3 and c.get('start_col_offset_idx') == 0 for t in tables for c in t['data']['table_cells'])
        else:
            structure = any(any(c.get('text') == '内层项目' for c in t['data']['table_cells']) for t in tables)
        outputs.append({'name':spec['name'],'sha256':digest(path),'unchanged':digest(path) == spec['sha256'],
                        'status':str(result.status),'seconds':seconds,'markdown':text,'tables':tables,
                        'text_preserved':all(s in text for s in spec['required_text']), 'structure_preserved':structure,
                        'baseline_text_preserved':spec['text_preserved'],'baseline_structure_preserved':spec['structure_preserved']})
    assert all(s['unchanged'] for s in outputs)
    return {'version':'2.150.0','models_used':[],'documents':outputs,
            'improvements':sum(not s['baseline_structure_preserved'] and s['structure_preserved'] for s in outputs),
            'regressions':sum(s['baseline_structure_preserved'] and not s['structure_preserved'] for s in outputs)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['baseline','presidio','docling'])
    args = parser.parse_args()
    ROOT.mkdir(parents=True, exist_ok=True)
    target = ROOT / (args.mode + '.json')
    if target.exists():
        raise ValueError('Preserve prior evidence; output already exists')
    for path in [ROOT, *ROOT.parents]:
        if path.exists() and (path.is_symlink() or getattr(path.stat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Reparse points are not permitted')
    self_check()
    fixtures = json.loads(FIXTURES.read_text(encoding='utf-8'))
    assert fixtures['synthetic_only'] is True
    started = time.monotonic()
    offline()
    result = globals()[args.mode](fixtures)
    sys.path.insert(0, str(HARNESS / 'experiments' / 'audit-followups'))
    from presidio_experiment import peak_memory
    result.update(synthetic_only=True, network_blocked=True, fixture_sha256=digest(FIXTURES),
                  script_sha256=digest(Path(__file__)), python=sys.version.split()[0],
                  total_seconds=time.monotonic()-started, peak_working_set_bytes=peak_memory())
    with target.open('x', encoding='utf-8') as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
    print(json.dumps({'mode':args.mode,'report':str(target),'seconds':result['total_seconds']}, ensure_ascii=True))
