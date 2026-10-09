from pathlib import Path
from uuid import UUID
import hashlib,json,time
from cn_contract.documents.ocr_candidates import page_bitmap
from cn_contract.documents.ocr_process import run_ocr_page
from cn_contract.domain import OCRPageSource
from scripts.ocr_synthetic_acceptance import critical_fields_match

ROOT=Path.cwd();OUT=Path(__file__).resolve().parent/'changed-pages';OUT.mkdir(exist_ok=False)
fixture=ROOT/'tests/fixtures/ocr-proofreading'
raw=(fixture/'independent-48-pages.pdf').read_bytes()
manifest=json.loads((fixture/'manifest.json').read_bytes())
assert hashlib.sha256(raw).hexdigest()==manifest['pdf_sha256']=='017866f3c56b2fad241fc048e6440e30314db41bef53391eabd7bc706117ae9b'
observations=[]
for row in manifest['pages']:
    page=row['page'];before=json.loads((ROOT/f'.audit-local/ocr-quality-20261009/fixed-48/result-{page:02}.json').read_bytes())
    image,w,h,bw,bh=page_bitmap(raw,page)
    digest=hashlib.sha256(image).hexdigest()
    assert (bw,bh)==(before['source']['bitmap_width'],before['source']['bitmap_height'])
    changed=digest!=before['source']['bitmap_sha256']
    record={'page':page,'group':row['group'],'bitmap_changed':changed,'before_sha256':before['source']['bitmap_sha256'],'after_sha256':digest,'before_fields':critical_fields_match([b['raw_text'] for b in before['blocks']],row['expected'])}
    if changed:
        source=OCRPageSource(document_version_id=UUID('4c68c5c5-1f35-447b-95fb-6646f66f1948'),document_sha256=manifest['pdf_sha256'],page=page,page_width_points=w,page_height_points=h,bitmap_width=bw,bitmap_height=bh,bitmap_sha256=digest,coordinate_space='rendered_page_top_left')
        start=time.monotonic();result=run_ocr_page(image,source.model_dump(mode='python'))
        (OUT/f'result-{page:02}.json').write_text(result.model_dump_json(indent=2),encoding='utf8')
        texts=[b.raw_text for b in result.blocks]
        record.update(prediction='executed_this_run',seconds=round(time.monotonic()-start,3),recognized=texts,after_fields=critical_fields_match(texts,row['expected']))
    else:
        record.update(prediction='not_rerun_identical_bitmap',after_fields=None)
    observations.append(record)
    (OUT/'observations.json').write_text(json.dumps(observations,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(record,ensure_ascii=False),flush=True)
summary={'pages_compared':len(observations),'new_predictions':sum(r['bitmap_changed'] for r in observations),'identical_bitmaps':sum(not r['bitmap_changed'] for r in observations),'newly_recovered':sum(r['after_fields'] is True and not r['before_fields'] for r in observations),'newly_regressed':sum(r['after_fields'] is False and r['before_fields'] for r in observations),'combined_field_hits':sum(r['after_fields'] if r['bitmap_changed'] else r['before_fields'] for r in observations),'scope':'incremental comparison; identical bitmap pages retain historical observations, not a new 48-page OCR run'}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(summary),flush=True)
assert summary['pages_compared']==48 and summary['newly_regressed']==0
