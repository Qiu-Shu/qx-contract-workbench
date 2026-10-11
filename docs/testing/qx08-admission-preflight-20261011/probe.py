"""Synthetic call-order repro only: no models, files, clocks or service changes."""
import sys
from pathlib import Path
from io import BytesIO
from uuid import UUID
from hashlib import sha256
from unittest.mock import patch
import json
import time

sys.path.insert(0, str(Path.cwd() / 'src'))
from PIL import Image
from cn_contract.documents import ocr_process
from cn_contract.domain import OCRPageSource
from cn_contract.security import ServiceError

buffer = BytesIO()
Image.new('RGB', (1, 1), 'white').save(buffer, format='PNG')
raw = buffer.getvalue()
source = OCRPageSource(document_version_id=UUID('753c3402-51f6-4f78-a88c-e471538b509b'),
    document_sha256='0' * 64, page=1, page_width_points=1, page_height_points=1,
    bitmap_width=1, bitmap_height=1, bitmap_sha256=sha256(raw).hexdigest(),
    coordinate_space='rendered_page_top_left')
rows = []
for _ in range(2):
    events = []
    assert ocr_process._SERIAL.acquire(blocking=False)
    start = time.monotonic()
    try:
        with patch.object(ocr_process, 'require_ocr_runtime', side_effect=lambda: events.append('runtime_verification')):
            try:
                ocr_process.run_ocr_page(raw, source.model_dump(mode='python'))
            except ServiceError as error:
                code = error.code
            else:
                code = 'unexpected_success'
    finally:
        ocr_process._SERIAL.release()
    rows.append(dict(expected_code='OCR_BUSY', actual_code=code,
                     expected_pre_busy_runtime_verifications=0, actual_pre_busy_runtime_verifications=len(events),
                     seconds=round(time.monotonic() - start, 6)))
result = dict(scope='synthetic mocked runtime call-order repro, not latency or model evidence',
              source_sha256=sha256(Path('src/cn_contract/documents/ocr_process.py').read_bytes()).hexdigest(),
              model_calls=0, observations=rows)
print(json.dumps(result, ensure_ascii=False), flush=True)
assert all(row['actual_code'] == 'OCR_BUSY' and row['actual_pre_busy_runtime_verifications'] == 0 for row in rows)
