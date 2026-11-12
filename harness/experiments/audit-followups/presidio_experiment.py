"""Run the fixed five Chinese synthetic probes through local Presidio + spaCy."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import urllib.request

sys.dont_write_bytecode = True
from backup_experiment import no_links
from candidate_experiment import LOCAL, SAMPLES, offline

MODEL_NAME = 'zh_core_web_sm-3.8.0-py3-none-any.whl'
MODEL_URL = 'https://github.com/explosion/spacy-models/releases/download/zh_core_web_sm-3.8.0/' + MODEL_NAME
MODEL_BYTES = 48515003
MODEL_SHA256 = '7de3bd267176b9b2a8defb6997c1cd296da16c57b5e712f72ea44a51755421c8'


def prepare_model():
    target = LOCAL / 'downloads' / MODEL_NAME
    no_links(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        with urllib.request.urlopen(MODEL_URL, timeout=60) as response, target.open('xb') as output:
            size = 0
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > MODEL_BYTES:
                    raise RuntimeError('Model exceeds the pinned official release size')
                output.write(chunk)
    if target.stat().st_size != MODEL_BYTES or hashlib.sha256(target.read_bytes()).hexdigest() != MODEL_SHA256:
        raise RuntimeError('Model size/checksum mismatch; do not install')
    print(json.dumps({'verified_model': str(target), 'bytes': MODEL_BYTES, 'sha256': MODEL_SHA256}))


def peak_memory():
    if os.name != 'nt':
        return None
    class Counters(ctypes.Structure):
        _fields_ = [('cb', ctypes.c_ulong), ('PageFaultCount', ctypes.c_ulong)] + [
            (name, ctypes.c_size_t) for name in ['PeakWorkingSetSize', 'WorkingSetSize',
            'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
            'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage']]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    if ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(-1), ctypes.byref(counters), counters.cb):
        return counters.PeakWorkingSetSize
    return None


def run(baseline_path):
    started = time.monotonic()
    path = Path(baseline_path)
    no_links(path)
    path = path.resolve()
    if not path.is_relative_to(LOCAL.resolve()) or path.name != 'baseline.json':
        raise ValueError('Only a generated experiment baseline is accepted')
    baseline_bytes = path.read_bytes()
    baseline = json.loads(baseline_bytes)
    if baseline.get('synthetic_only') is not True or [
        {key: item[key] for key in ('id', 'text', 'entities', 'preserve')} for item in baseline['privacy']
    ] != SAMPLES:
        raise ValueError('Baseline must contain exactly the five predeclared synthetic samples')
    versions = {package: importlib.metadata.version(package) for package in
                ('presidio-analyzer', 'spacy', 'spacy-pkuseg', 'zh-core-web-sm')}
    if versions['presidio-analyzer'] != '2.2.366' or versions['zh-core-web-sm'] != '3.8.0':
        raise ValueError('Candidate/model version differs from the experiment pin')
    if not importlib.util.find_spec('zh_core_web_sm'):
        raise RuntimeError('Install the verified model locally; runtime downloading is forbidden')
    offline()
    os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
    import spacy
    spacy.require_cpu()
    from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
    from presidio_analyzer.nlp_engine import SpacyNlpEngine
    from presidio_analyzer.predefined_recognizers import SpacyRecognizer
    load_started = time.monotonic()
    engine = SpacyNlpEngine(models=[{'lang_code': 'zh', 'model_name': 'zh_core_web_sm'}])
    registry = RecognizerRegistry(supported_languages=['zh'])
    registry.add_recognizer(SpacyRecognizer(supported_language='zh', supported_entities=['PERSON', 'ORGANIZATION']))
    analyzer = AnalyzerEngine(nlp_engine=engine, registry=registry, supported_languages=['zh'])
    load_seconds = time.monotonic() - load_started
    rows = []
    for sample, old in zip(SAMPLES, baseline['privacy']):
        begin = time.monotonic()
        predictions = analyzer.analyze(text=sample['text'], language='zh', entities=['PERSON', 'ORGANIZATION'],
                                       score_threshold=0.5)
        seconds = time.monotonic() - begin
        spans, covered = [], set()
        for prediction in predictions:
            assert 0 <= prediction.start < prediction.end <= len(sample['text'])
            covered.update(range(prediction.start, prediction.end))
            spans.append({'start': prediction.start, 'end': prediction.end, 'entity_type': prediction.entity_type,
                          'score': prediction.score, 'text': sample['text'][prediction.start:prediction.end]})
        expected, entity_covered = set(), []
        for entity in sample['entities']:
            offset = sample['text'].index(entity)
            positions = {offset + i for i, char in enumerate(entity) if not char.isspace()}
            expected.update(positions)
            entity_covered.append(positions.issubset(covered))
        # Mask actual analyzer spans only to measure factual retention; no custom recognition rules.
        safe, in_mask = [], False
        for index, char in enumerate(sample['text']):
            if index in covered:
                if not in_mask:
                    safe.append('[PII]')
                in_mask = True
            else:
                safe.append(char)
                in_mask = False
        safe = ''.join(safe)
        rows.append({**sample, 'spans': spans, 'entity_covered': entity_covered,
                     'baseline_entity_covered': old['entity_covered'], 'safe_text_from_spans': safe,
                     'facts_preserved': all(value in safe for value in sample['preserve']),
                     'non_entity_characters_masked': sum(i not in expected and not sample['text'][i].isspace() for i in covered),
                     'seconds': round(seconds, 6)})
    report = {'synthetic_only': True, 'candidate': 'presidio-analyzer + spaCy zh_core_web_sm',
              'versions': versions, 'python': sys.version.split()[0],
              'baseline_sha256': hashlib.sha256(baseline_bytes).hexdigest(),
              'configuration': {'language': 'zh', 'entities': ['PERSON', 'ORGANIZATION'], 'score_threshold': 0.5,
                                'recognizers': ['SpacyRecognizer'], 'custom_patterns': [], 'GPU': False},
              'network_guard': 'HF offline and Python socket connects rejected before model initialization',
              'samples': rows, 'model_load_seconds': round(load_seconds, 6),
              'inference_seconds': round(sum(row['seconds'] for row in rows), 6),
              'total_seconds': round(time.monotonic() - started, 6), 'peak_working_set_bytes': peak_memory(),
              'expected_entities': sum(len(row['entities']) for row in rows),
              'covered_entities': sum(sum(row['entity_covered']) for row in rows),
              'baseline_covered_entities': sum(sum(row['baseline_entity_covered']) for row in rows),
              'facts_preserved_samples': sum(row['facts_preserved'] for row in rows),
              'non_entity_characters_masked': sum(row['non_entity_characters_masked'] for row in rows),
              'newly_covered_entities': sum(not before and after for row in rows for before, after in zip(row['baseline_entity_covered'], row['entity_covered'])),
              'regressed_entities': sum(before and not after for row in rows for before, after in zip(row['baseline_entity_covered'], row['entity_covered']))}
    target = path.parent / 'presidio-comparison.json'
    no_links(target)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'result': str(target), 'covered': report['covered_entities'],
                      'expected': report['expected_entities'], 'newly_covered': report['newly_covered_entities'],
                      'regressed': report['regressed_entities'], 'facts_preserved': report['facts_preserved_samples']}, ensure_ascii=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--baseline')
    mode.add_argument('--download-model', action='store_true', help='Explicitly fetch/check the pinned official model; never runs during inference')
    arguments = parser.parse_args()
    prepare_model() if arguments.download_model else run(arguments.baseline)
