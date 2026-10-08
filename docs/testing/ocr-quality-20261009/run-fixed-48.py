"""Measured development regression, fixed committed fictional PDF only."""
from pathlib import Path
from uuid import UUID
from datetime import datetime,timezone
import hashlib,json,time
from cn_contract.documents.ocr_candidates import page_bitmap
from cn_contract.documents.ocr_process import run_ocr_page
from cn_contract.domain import OCRPageSource
from cn_contract.security import ServiceError
ROOT=Path.cwd();OUT=ROOT/'.audit-local/ocr-quality-20261009/fixed-48'
fixture=ROOT/'tests/fixtures/ocr-proofreading'
raw=(fixture/'independent-48-pages.pdf').read_bytes()
manifest_raw=(fixture/'manifest.json').read_bytes();manifest=json.loads(manifest_raw)
expected_hash='017866f3c56b2fad241fc048e6440e30314db41bef53391eabd7bc706117ae9b'
assert hashlib.sha256(raw).hexdigest()==manifest['pdf_sha256']==expected_hash
assert [row['page'] for row in manifest['pages']]==list(range(1,49))
OUT.mkdir(exist_ok=False)
observations=[]
for row in manifest['pages']:
    started=time.monotonic()
    obs={'page':row['page'],'group':row['group'],'input':'rendered_immutable_pdf_page','pdf_sha256':expected_hash}
    try:
        image,w,h,bw,bh=page_bitmap(raw,row['page'])
        source=OCRPageSource(document_version_id=UUID('4c68c5c5-1f35-447b-95fb-6646f66f1948'),document_sha256=expected_hash,page=row['page'],page_width_points=w,page_height_points=h,bitmap_width=bw,bitmap_height=bh,bitmap_sha256=hashlib.sha256(image).hexdigest(),coordinate_space='rendered_page_top_left')
        obs.update(bitmap_sha256=source.bitmap_sha256,bitmap=[bw,bh],rendered_points=[w,h])
        result=run_ocr_page(image,source.model_dump(mode='python'))
        (OUT/f"result-{row['page']:02}.json").write_text(result.model_dump_json(indent=2),encoding='utf8')
        recognized=''.join(''.join(block.raw_text.split()) for block in result.blocks)
        correct=all(''.join(expected.split()) in recognized for expected in row['expected'])
        obs.update(status='CORRECT' if correct else 'INCORRECT_CANDIDATE',recognized=recognized,blocks=len(result.blocks))
    except ServiceError as error:obs.update(status='BLOCKED',code=error.code)
    except Exception as error:obs.update(status='ERROR',error_type=type(error).__name__)
    obs['seconds']=round(time.monotonic()-started,3);observations.append(obs)
    (OUT/'observations.json').write_text(json.dumps(observations,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(obs,ensure_ascii=False),flush=True)
summary={'scope':'same_fixture_development_regression_not_blind_or_legal_validation','pdf_sha256':expected_hash,'manifest_sha256':hashlib.sha256(manifest_raw).hexdigest(),'pages':len(observations),'correct':sum(r['status']=='CORRECT' for r in observations),'incorrect':sum(r['status']=='INCORRECT_CANDIDATE' for r in observations),'blocked':sum(r['status']=='BLOCKED' for r in observations),'errors':sum(r['status']=='ERROR' for r in observations),'finished_utc':datetime.now(timezone.utc).isoformat()}
summary['by_group']={g:{s:sum(r['group']==g and r['status']==s for r in observations) for s in ('CORRECT','INCORRECT_CANDIDATE','BLOCKED','ERROR')} for g in dict.fromkeys(r['group'] for r in observations)}
summary['clear_positive']=summary['by_group']['clear']['CORRECT']
summary['minimal_engineering_gate']=bool(summary['clear_positive'] and not summary['errors'])
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(summary,ensure_ascii=False))
assert (fixture/'independent-48-pages.pdf').read_bytes()==raw and (fixture/'manifest.json').read_bytes()==manifest_raw
raise SystemExit(0 if summary['minimal_engineering_gate'] else 1)
