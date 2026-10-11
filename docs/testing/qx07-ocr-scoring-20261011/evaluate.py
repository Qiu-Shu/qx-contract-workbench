"""Run from repository root; synthetic-only QX07 evidence, never a model tune."""
from pathlib import Path
from datetime import datetime, timezone
from uuid import UUID
import hashlib
import json
import random
import sys
import time

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from cn_contract.acceptance.ocr_scoring import score_page, summarize_scores
from cn_contract.documents.ocr_candidates import page_bitmap
from cn_contract.documents.ocr_process import run_ocr_page
from cn_contract.domain import OCRPageSource
from cn_contract.security import ServiceError
from scripts.ocr_synthetic_acceptance import critical_fields_match, LEGACY_SCORER_VERSION

OUT = ROOT / 'docs/testing/qx07-ocr-scoring-20261011/evaluation'
OUT.mkdir(parents=True, exist_ok=False)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def score(blocks, row):
    return score_page(blocks, reference_blocks=row['reference'], amount=row['amount'],
                      unit=row['unit'], date=row['date'], prohibition=row['prohibition'])


started = datetime.now(timezone.utc).isoformat()
frozen = {path: sha(ROOT / path) for path in [
    'src/cn_contract/acceptance/ocr_scoring.py', 'scripts/ocr_synthetic_acceptance.py',
    'src/cn_contract/documents/ocr_worker.py', 'src/cn_contract/documents/ocr_candidates.py',
    'src/cn_contract/documents/ocr_process.py', 'src/cn_contract/documents/_windows_ocr.py',
    'src/cn_contract/documents/ocr_assets.py',
    'sources/ocr-assets.lock.json', 'sources/ocr-environment.lock.json',
    'tests/fixtures/ocr-proofreading/manifest.json', 'tests/fixtures/ocr-proofreading/independent-48-pages.pdf',
    '.audit-local/qx07_evaluate.py']}
save(OUT / 'frozen-before.json', {'started_utc': started, 'files': frozen})

examples = {
    'correct': ['价款28473元', '不得自动验收2026-10-15'],
    'wrong_ascii_number': ['价款128473元', '不得自动验收2026-10-15'],
    'conflicting_amount': ['价款28473元', '价款284730元', '不得自动验收2026-10-15'],
    'duplicate_amount': ['价款28473元', '价款28473元', '不得自动验收2026-10-15'],
    'cross_box_digit': ['价款28473元', '不得自动验收2', '2026-10-15'],
    'unicode_negative': ['价款−28473元', '不得自动验收2026-10-15'],
    'fullwidth_decimal': ['价款28473．9元', '不得自动验收2026-10-15'],
    'wrong_unit': ['价款28473万元', '不得自动验收2026-10-15'],
}
audit = []
for name, blocks in examples.items():
    result = score(blocks, dict(reference=examples['correct'], amount='28473', unit='元',
                               date='2026-10-15', prohibition='不得自动验收'))
    audit.append(dict(name=name, blocks=blocks, expected_v2=name == 'correct', score_v2=result,
                      legacy_v1=critical_fields_match(blocks, ['28473', '不得自动验收', '2026-10-15'])))
assert all(row['score_v2']['fields_match'] == row['expected_v2'] for row in audit)
save(OUT / 'audit-eight.json', audit)

# The original fixed set is development data; do not call this a new OCR run.
development = OUT / 'development'
development.mkdir()
fixture = ROOT / 'tests/fixtures/ocr-proofreading'
manifest = json.loads((fixture / 'manifest.json').read_bytes())
assert sha(fixture / 'independent-48-pages.pdf') == manifest['pdf_sha256']
rows = []
for original in manifest['pages']:
    page = original['page']
    result_path = ROOT / f'docs/testing/ocr-contrast-20261009/result-{page:02}.json'
    if not result_path.exists():
        result_path = ROOT / f'.audit-local/ocr-quality-20261009/fixed-48/result-{page:02}.json'
    raw_result = result_path.read_bytes()
    result = json.loads(raw_result)
    assert result['source']['document_sha256'] == manifest['pdf_sha256'] and result['source']['page'] == page
    bitmap, _, _, _, _ = page_bitmap((fixture / 'independent-48-pages.pdf').read_bytes(), page)
    assert hashlib.sha256(bitmap).hexdigest() == result['source']['bitmap_sha256']
    (development / f'result-{page:02}.json').write_bytes(raw_result)
    amount, prohibition, date = original['expected']
    row = dict(page=page, group=original['group'], amount=amount, unit='元', date=date, prohibition=prohibition,
               reference=['独立虚构材料 ' + str(page), '价款 ' + amount + ' 元', prohibition + ' ' + date])
    blocks = [block['raw_text'] for block in result['blocks']]
    row.update(prediction='historical_output_rescored_no_model_run',
               source_result_path=result_path.relative_to(ROOT).as_posix(), result_sha256=sha(result_path),
               bitmap_sha256=result['source']['bitmap_sha256'],
               legacy_v1=critical_fields_match(blocks, original['expected']), score_v2=score(blocks, row))
    rows.append(row)
save(development / 'scores.json', rows)
dev_summary = summarize_scores([row['score_v2'] for row in rows])
dev_summary.update(legacy_version=LEGACY_SCORER_VERSION, legacy_field_hits=sum(row['legacy_v1'] for row in rows),
                   predictions_this_run=0, dataset='development_known_fixed_48',
                   groups={group: summarize_scores([r['score_v2'] for r in rows if r['group'] == group])
                           for group in sorted({r['group'] for r in rows})})
save(development / 'summary.json', dev_summary)
print(json.dumps({'stage': 'development', 'pages': len(rows), 'v2_field_matches': dev_summary['field_matches'],
                  'layout_exact': dev_summary['full_text']['layout_normalized']['exact_pages']}), flush=True)

# Fixed after the scorer freeze; no look at OCR output and no OCR/model tuning.
holdout = OUT / 'holdout'
holdout.mkdir()
rng = random.Random(20261011)
font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 40)
images = []
new_rows = []
for index, group in enumerate(['clear', 'clear_decimal_wanyuan', 'skew', 'blur', 'low_contrast', 'occluded']):
    amount = str(rng.randrange(51000, 89000))
    if index in (1, 3):
        amount += '.25'
    unit = '万元' if index == 1 else '元'
    date = f'2027-{rng.randrange(1, 10):02}-{rng.randrange(1, 28):02}'
    prohibition = '未经确认不得付款' if index % 2 == 0 else '不得默示同意续期'
    reference = ['留出虚构样本 ' + '甲乙丙丁戊己'[index], '约定服务费 ' + amount + ' ' + unit,
                 '完成期限 ' + date, prohibition]
    image = Image.new('RGB', (1200, 520), 'white')
    draw = ImageDraw.Draw(image)
    for line, text in enumerate(reference):
        draw.text((40, 30 + line * 115), text, font=font, fill='black')
    if group == 'skew':
        image = image.rotate(3.75, resample=Image.Resampling.BICUBIC, fillcolor='white')
    elif group == 'blur':
        image = image.filter(ImageFilter.GaussianBlur(1.8))
    elif group == 'low_contrast':
        image = ImageEnhance.Contrast(image).enhance(.16)
    elif group == 'occluded':
        ImageDraw.Draw(image).rectangle((262, 143, 322, 197), fill='white')
    image_path = holdout / f'page-{index + 1}.png'
    image.save(image_path)
    images.append(image)
    new_rows.append(dict(page=index + 1, group=group, amount=amount, unit=unit, date=date,
                         prohibition=prohibition, reference=reference, png_sha256=sha(image_path)))
pdf = holdout / 'synthetic-holdout-6.pdf'
images[0].save(pdf, save_all=True, append_images=images[1:], resolution=144,
               creationDate='D:20261011000000Z', modDate='D:20261011000000Z')
save(holdout / 'manifest.json', dict(scope='new_synthetic_holdout_not_real_materials', seed=20261011,
     font_sha256=sha(Path('C:/Windows/Fonts/msyh.ttc')), pdf_sha256=sha(pdf),
     scorer_sha256=frozen['src/cn_contract/acceptance/ocr_scoring.py'],
     generated_before_any_holdout_prediction=True, pages=new_rows))
observations = []
for row in new_rows:
    tick = time.monotonic()
    bitmap, w, h, bw, bh = page_bitmap(pdf.read_bytes(), row['page'])
    source = OCRPageSource(document_version_id=UUID('85e0ea86-60d0-49db-933b-e605663f444f'),
        document_sha256=sha(pdf), page=row['page'], page_width_points=w, page_height_points=h,
        bitmap_width=bw, bitmap_height=bh, bitmap_sha256=hashlib.sha256(bitmap).hexdigest(),
        coordinate_space='rendered_page_top_left')
    observation = dict(page=row['page'], group=row['group'], source=source.model_dump(mode='json'),
                       ocr_call_attempted=True, ocr_result_returned=False)
    try:
        result = run_ocr_page(bitmap, source.model_dump(mode='python'))
        observation['ocr_result_returned'] = True
        result_path = holdout / f"result-{row['page']:02}.json"
        result_path.write_text(result.model_dump_json(indent=2), encoding='utf-8', newline='\n')
        blocks = [block.raw_text for block in result.blocks]
        observation.update(status='SCORED', prediction='executed_this_run', result_sha256=sha(result_path),
                           legacy_v1=critical_fields_match(blocks, [row['amount'], row['prohibition'], row['date']]),
                           score_v2=score(blocks, row))
    except ServiceError as error:
        observation.update(status='BLOCKED', code=error.code)
    except Exception as error:
        observation.update(status='ERROR', error_type=type(error).__name__)
    observation['seconds'] = round(time.monotonic() - tick, 3)
    observations.append(observation)
    save(holdout / 'observations.json', observations)
    print(json.dumps({'stage': 'holdout', 'page': row['page'], 'status': observation['status'],
                      'fields_match': observation.get('score_v2', {}).get('fields_match'),
                      'seconds': observation['seconds']}), flush=True)
holdout_summary = summarize_scores([row.get('score_v2') for row in observations])
holdout_summary.update(dataset='new_synthetic_holdout_6', prediction_attempts=len(observations),
                       ocr_results_returned=sum(row['ocr_result_returned'] for row in observations),
                       legacy_version=LEGACY_SCORER_VERSION,
                       legacy_field_hits=sum(row.get('legacy_v1', False) for row in observations),
                       blocked=sum(row['status'] == 'BLOCKED' for row in observations),
                       errors=sum(row['status'] == 'ERROR' for row in observations))
save(holdout / 'summary.json', holdout_summary)
changed = [path for path, digest in frozen.items() if sha(ROOT / path) != digest]
receipt = dict(started_utc=started, finished_utc=datetime.now(timezone.utc).isoformat(),
               command=[sys.executable, '-X', 'utf8', '-u', '.audit-local/qx07_evaluate.py'],
               working_directory=str(ROOT),
               frozen_changed=changed, audit_examples_expected=8, audit_examples_matched=8,
               development_predictions=0, holdout_attempted=len(observations),
               holdout_scored=holdout_summary['scored_pages'],
               scope='synthetic engineering observation, not legal quality, no tuning on holdout output',
               files={p.relative_to(OUT).as_posix(): sha(p) for p in OUT.rglob('*') if p.is_file()})
save(OUT / 'receipt.json', receipt)
assert not changed
print(json.dumps({'stage': 'complete', 'holdout': holdout_summary}, ensure_ascii=False), flush=True)
sys.exit(1 if holdout_summary['errors'] or holdout_summary['blocked'] else 0)
