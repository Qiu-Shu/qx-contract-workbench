"""Single-page OCR under an explicit fixed Windows process boundary."""
from datetime import datetime,timezone
from hashlib import sha256
from io import BytesIO
import json,os,threading
from pathlib import Path
from uuid import uuid4
from PIL import Image
from ..config import PROJECT_ROOT
from ..domain import OCRPageSource,OCRResult,OCRBlock
from ..security import ServiceError
from .ocr_assets import require_ocr_runtime
from . import ocr_assets
from .pdfjs_assets import _regular

_SERIAL=threading.Lock()


def run_ocr_page(image_bytes, source_metadata):
    require_ocr_runtime()
    source=OCRPageSource.model_validate(source_metadata)
    if os.name!='nt':raise ServiceError('OCR_ISOLATION_UNAVAILABLE',503)
    if not isinstance(image_bytes,bytes) or len(image_bytes)>50*1024**2 or sha256(image_bytes).hexdigest()!=source.bitmap_sha256:
        raise ServiceError('OCR_INPUT_INVALID',422)
    with Image.open(BytesIO(image_bytes)) as image:
        if image.format!='PNG' or image.size!=(source.bitmap_width,source.bitmap_height):
            raise ServiceError('OCR_INPUT_INVALID',422)
        image.verify()
    if not _SERIAL.acquire(blocking=False):raise ServiceError('OCR_BUSY',409)
    lock_file=None
    try:
        parent=PROJECT_ROOT/'.local/ocr-jobs';parent.mkdir(parents=True,exist_ok=True);_regular(parent,directory=True)
        import msvcrt
        lock_path=parent/'worker.lock'
        if lock_path.exists():_regular(lock_path)
        lock_file=lock_path.open('a+b')
        if lock_file.seek(0,2)==0:lock_file.write(b'0');lock_file.flush()
        lock_file.seek(0)
        try:msvcrt.locking(lock_file.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            lock_file.close();lock_file=None
            raise ServiceError('OCR_BUSY',409) from None
        work=parent/uuid4().hex;work.mkdir()
        (work/'input.png').write_bytes(image_bytes)
        (work/'worker.py').write_bytes(Path(__file__).with_name('ocr_worker.py').read_bytes())
        models=PROJECT_ROOT/'.local/ocr-assets/models'
        stage_models(work)
        (work/'request.json').write_text(json.dumps({'image':'input.png','model_root':str(models)}),encoding='utf-8')
        from ._windows_ocr import run_sandboxed
        try:status=run_sandboxed(work,PROJECT_ROOT/'.local/ocr-worker/python',models)
        except (OSError,ValueError):raise ServiceError('OCR_ISOLATION_UNAVAILABLE',503) from None
        if status['timed_out']:raise ServiceError('OCR_TIMEOUT',409)
        output=work/'output.json'
        if status['exit_code'] or not output.is_file():raise ServiceError('OCR_WORKER_FAILED',409)
        _regular(output)
        if output.stat().st_size>2_000_000:raise ServiceError('OCR_OUTPUT_INVALID',409)
        raw=output.read_bytes()
        return decode_output(raw,source)
    finally:
        if lock_file:
            lock_file.seek(0);msvcrt.locking(lock_file.fileno(),msvcrt.LK_UNLCK,1);lock_file.close()
        _SERIAL.release()


def stage_models(work):
    raw=ocr_assets.MANIFEST_PATH.read_bytes()
    if sha256(raw).hexdigest()!=ocr_assets.MANIFEST_SHA256:raise ServiceError('OCR_ASSETS_INVALID',503)
    for row in json.loads(raw)['files']:
        if row['path'].startswith('models/'):
            source=ocr_assets.ASSET_ROOT/row['path'];_regular(source)
            data=source.read_bytes()
            if len(data)!=row['bytes'] or sha256(data).hexdigest()!=row['sha256']:
                raise ServiceError('OCR_ASSETS_INVALID',503)
            dest=work/row['path'];dest.parent.mkdir(parents=True,exist_ok=True)
            with dest.open('xb') as stream:stream.write(data)


def decode_output(raw,source):
    try:
        result=json.loads(raw,parse_constant=lambda value:(_ for _ in ()).throw(ValueError('nonfinite output')))
        if not isinstance(result,dict) or result.get('status')!='ok':raise ValueError('worker failed')
        if not isinstance(result.get('blocks'),list) or len(result['blocks'])>2000:raise ValueError('blocks')
        blocks=tuple(OCRBlock.model_validate(block) for block in result['blocks'])
        return OCRResult(id=uuid4(),source=source,created_at=datetime.now(timezone.utc),
            engine='PaddleOCR-3.7.0/PaddleX-3.7.0/PaddlePaddle-3.3.0-CPU',asset_manifest_sha256=ocr_assets.MANIFEST_SHA256,
            raw_output_sha256=sha256(raw).hexdigest(),blocks=blocks,
            bitmap_to_page=(source.page_width_points/source.bitmap_width,0,0,source.page_height_points/source.bitmap_height,0,0),
            reasons=('OCR_IS_UNVERIFIED','AMOUNTS_DATES_NEGATIONS_REQUIRE_LAWYER_CHECK'))
    except (ValueError,TypeError,KeyError):raise ServiceError('OCR_OUTPUT_INVALID',409) from None
