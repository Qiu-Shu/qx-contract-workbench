"""Server-rendered pages and immutable unverified OCR candidates."""
from datetime import datetime
from hashlib import sha256
from io import BytesIO
import math
from uuid import UUID
from PIL import ImageOps
import pypdfium2 as pdfium
from sqlalchemy import ForeignKey,String,Text,select
from sqlalchemy.orm import Mapped,mapped_column
from ..domain import OCRCandidate,OCRPageSource,PageOCRInput
from ..persistence import Base,UTCDateTime,read_original
from ..security import ServiceError,authorize
from ..review.proposals import digest
from .proofreading import _document
from .ocr_process import run_prepared_ocr_page


class OCRCandidateRow(Base):
    __tablename__='ocr_candidates'
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    matter_id:Mapped[str]=mapped_column(ForeignKey('matters.id'))
    actor_id:Mapped[str]=mapped_column(ForeignKey('users.id'))
    document_version_id:Mapped[str]=mapped_column(ForeignKey('document_versions.id'))
    created_at:Mapped[datetime]=mapped_column(UTCDateTime())
    payload:Mapped[str]=mapped_column(Text)
    sha256:Mapped[str]=mapped_column(String(64))


def initialize_storage(database):
    with database.engine.begin() as connection:
        Base.metadata.create_all(connection,tables=[OCRCandidateRow.__table__])
        for operation in ('UPDATE','DELETE'):
            connection.exec_driver_sql(f'CREATE TRIGGER IF NOT EXISTS immutable_ocr_candidates_{operation.lower()} '
                f"BEFORE {operation} ON ocr_candidates BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END")


def page_bitmap(original,page):
    """Existing PDFium renderer; finite size checked before allocation."""
    document=pdfium.PdfDocument(original)
    try:
        if not 1<=page<=len(document):raise ServiceError('VERSION_CONFLICT',409)
        current=document[page-1]
        try:
            width,height=current.get_size()
            if not all(math.isfinite(x) and x>0 for x in (width,height)):raise ServiceError('FILE_LIMIT',413)
            # Reject before multiplication (even a finite dimension can overflow).
            if max(width,height)>4096:raise ServiceError('FILE_LIMIT',413)
            # Higher-resolution sampling reduces observed JPEG-page omissions.
            # Preserve the old supported page envelope without cropping any page.
            for scale in (4,2):
                bw,bh=math.ceil(width*scale),math.ceil(height*scale)
                if max(bw,bh)<=8192 and bw*bh<=16000000:break
            else:raise ServiceError('FILE_LIMIT',413)
            bitmap=current.render(scale=scale)
            try:
                # Enhance faint ink for OCR only; preserve every pixel's position.
                image=ImageOps.autocontrast(bitmap.to_pil());buffer=BytesIO();image.save(buffer,format='PNG')
                return buffer.getvalue(),width,height,image.width,image.height
            finally:bitmap.close()
        finally:current.close()
    finally:document.close()


def prepare_page_ocr(matter_id,value,actor,db):
    authorize(actor,matter_id,'candidate_facts',db)
    from ..ops.storage import require_active
    require_active(db)
    value=PageOCRInput.model_validate_json(value.model_dump_json())
    _document(matter_id,value,actor,db)
    original=read_original(matter_id,value.document_version_id,actor,db)
    return original


def predict_page(original,value):
    source=None
    def prepare():
        nonlocal source
        raw,width,height,bw,bh=page_bitmap(original,value.page)
        source=OCRPageSource(document_version_id=value.document_version_id,document_sha256=value.document_sha256,
            page=value.page,page_width_points=width,page_height_points=height,bitmap_width=bw,bitmap_height=bh,
            bitmap_sha256=sha256(raw).hexdigest(),coordinate_space='rendered_page_top_left')
        return raw,source.model_dump(mode='python')
    result=run_prepared_ocr_page(prepare)
    if result.source!=source:raise ServiceError('OCR_OUTPUT_INVALID',409)
    return result


def save_page_ocr(matter_id,value,result,actor,db):
    authorize(actor,matter_id,'candidate_facts',db)
    from ..ops.storage import require_active
    require_active(db)
    source=result.source
    if (source.document_version_id,source.document_sha256,source.page)!=(value.document_version_id,value.document_sha256,value.page):
        raise ServiceError('OCR_OUTPUT_INVALID',409)
    candidate=OCRCandidate(matter_id=matter_id,actor_id=actor.user_id,result=result,sha256='0'*64)
    candidate=OCRCandidate(**candidate.model_dump(mode='python',exclude={'sha256'}),
        sha256=digest(candidate.model_dump(mode='json',exclude={'sha256'})))
    _document(matter_id,value,actor,db)
    with db.begin_nested():
        db.add(OCRCandidateRow(id=str(result.id),matter_id=str(matter_id),actor_id=str(actor.user_id),
            document_version_id=str(value.document_version_id),created_at=result.created_at,
            payload=candidate.model_dump_json(),sha256=candidate.sha256))
        db.flush();authorize(actor,matter_id,'candidate_facts',db)
    return candidate


def read_candidate(matter_id,identifier,actor,db):
    authorize(actor,matter_id,'read',db)
    row=db.get(OCRCandidateRow,str(identifier))
    if row is None or row.matter_id!=str(matter_id):raise ServiceError('VERSION_CONFLICT',409)
    value=OCRCandidate.model_validate_json(row.payload)
    if (value.sha256!=row.sha256 or value.sha256!=digest(value.model_dump(mode='json',exclude={'sha256'}))
        or str(value.result.id)!=row.id or str(value.matter_id)!=row.matter_id or str(value.actor_id)!=row.actor_id
        or str(value.result.source.document_version_id)!=row.document_version_id or value.result.created_at!=row.created_at):
        raise ServiceError('VERSION_CONFLICT',409)
    _document(matter_id,value.result.source,actor,db)
    return value


def current_candidates(matter_id,actor,db):
    authorize(actor,matter_id,'read',db)
    from ..web.services import current_versions
    current=[str(v.id) for v in current_versions(matter_id,actor,db)]
    rows=db.scalars(select(OCRCandidateRow.id).where(OCRCandidateRow.matter_id==str(matter_id),
        OCRCandidateRow.document_version_id.in_(current)).order_by(OCRCandidateRow.created_at)).all()
    return tuple(read_candidate(matter_id,UUID(identifier),actor,db) for identifier in rows)
