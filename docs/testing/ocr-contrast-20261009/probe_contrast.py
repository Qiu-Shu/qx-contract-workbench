from pathlib import Path
from io import BytesIO
from uuid import UUID
import hashlib,json,time
from PIL import Image,ImageOps
from cn_contract.documents.ocr_candidates import page_bitmap
from cn_contract.documents.ocr_process import run_ocr_page
from cn_contract.domain import OCRPageSource
from scripts.ocr_synthetic_acceptance import critical_fields_match

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent/'contrast'
OUT.mkdir(exist_ok=False)
manifest=json.loads((ROOT/'tests/fixtures/ocr-proofreading/manifest.json').read_text(encoding='utf8'))
raw=(ROOT/'tests/fixtures/ocr-proofreading/independent-48-pages.pdf').read_bytes()
assert hashlib.sha256(raw).hexdigest()==manifest['pdf_sha256']
for page in (9,29,32):
    original,w,h,bw,bh=page_bitmap(raw,page)
    with Image.open(BytesIO(original)) as image:
        enhanced=ImageOps.autocontrast(image.convert('RGB'))
        assert enhanced.size==(bw,bh)
        buffer=BytesIO();enhanced.save(buffer,format='PNG');png=buffer.getvalue()
    (OUT/f'input-{page}.png').write_bytes(png)
    source=OCRPageSource(document_version_id=UUID('4c68c5c5-1f35-447b-95fb-6646f66f1948'),document_sha256=manifest['pdf_sha256'],page=page,page_width_points=w,page_height_points=h,bitmap_width=bw,bitmap_height=bh,bitmap_sha256=hashlib.sha256(png).hexdigest(),coordinate_space='rendered_page_top_left')
    start=time.monotonic()
    result=run_ocr_page(png,source.model_dump(mode='python'))
    (OUT/f'result-{page}.json').write_text(result.model_dump_json(indent=2),encoding='utf8')
    texts=[b.raw_text for b in result.blocks]
    record={'page':page,'transform':'PIL.ImageOps.autocontrast cutoff=0 RGB','seconds':round(time.monotonic()-start,3),'correct_critical_fields':critical_fields_match(texts,manifest['pages'][page-1]['expected']),'recognized':texts,'original_bitmap_sha256':hashlib.sha256(original).hexdigest(),'enhanced_bitmap_sha256':source.bitmap_sha256}
    (OUT/f'observation-{page}.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(record,ensure_ascii=False),flush=True)
