"""Authorized ingestion and parsing against trusted immutable server records."""
from datetime import datetime, timezone
from io import BytesIO
from pathlib import PurePath
from uuid import uuid4

from ..audit import append_event
from ..config import Settings
from ..domain import AnchoredSpan, AuditEvent, BaselineView, UploadMeta
from ..persistence import (MatterRow, configured_database, create_version, read_original,
                           read_version, save_parse_result)
from ..security import ServiceError, authorize
from .docx_adapter import has_revisions, parse_docx, read_package
from .pdf_adapter import parse_pdf

DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'


def _type(data, name, mime):
    extension = PurePath(name).suffix.lower()
    if extension == '.docx' and mime == DOCX_MIME and data.startswith(b'PK\x03\x04'):
        return 'docx'
    if extension == '.pdf' and mime == 'application/pdf' and data.startswith(b'%PDF-'):
        return 'pdf'
    raise ServiceError('FILE_UNSUPPORTED', 400)


def _settings(requested, db):
    configured = configured_database(db).settings
    if requested is None:
        return configured
    # A caller cannot raise server resource caps or bypass strict model validation.
    settings = Settings.model_validate(requested.model_dump(mode='python'))
    caps = ('upload_max_file_mib', 'upload_max_matter_files', 'upload_max_matter_mib',
            'parse_max_pages_per_file', 'archive_uncompressed_max_mib', 'archive_max_ratio')
    values = settings.model_dump(mode='python')
    values.update({field: min(getattr(settings, field), getattr(configured, field)) for field in caps})
    return Settings.model_validate(values)


def ingest(file, meta, actor, *, db):
    # Authorization precedes even reading the untrusted file or checking a cache.
    authorize(actor, meta.matter_id, 'upload', db)
    meta = UploadMeta.model_validate(meta.model_dump(mode='python'))
    settings = configured_database(db).settings
    matter = db.get(MatterRow, str(meta.matter_id), populate_existing=True)
    if matter.status == 'archived':
        raise ServiceError('STATE_CONFLICT', 409)
    if matter.file_count >= settings.upload_max_matter_files or matter.total_bytes >= settings.upload_max_matter_mib * 1024 * 1024:
        raise ServiceError('FILE_LIMIT', 413)
    available = min(settings.upload_max_file_mib * 1024 * 1024,
                    settings.upload_max_matter_mib * 1024 * 1024 - matter.total_bytes)
    content = bytearray()
    while True:
        chunk = file.read(min(64 * 1024, available - len(content) + 1))
        if not isinstance(chunk, bytes):
            raise ServiceError('FILE_UNSUPPORTED', 400)
        if not chunk:
            break
        if len(chunk) + len(content) > available:
            raise ServiceError('FILE_LIMIT', 413)
        content.extend(chunk)
    data = bytes(content)
    kind = _type(data, meta.original_name, meta.mime)
    if kind == 'docx':
        _, xml_parts = read_package(data, settings)
        revisions = has_revisions(xml_parts)
        if revisions and meta.baseline_view is None:
            raise ServiceError('BASELINE_REQUIRED', 400)
        if revisions or meta.baseline_view in {BaselineView.ACCEPTED_VIEW, BaselineView.REJECTED_VIEW, BaselineView.CONFIRMED_CUSTOM}:
            authorize(actor, meta.matter_id, 'confirm_baseline', db)
    else:
        # Validate every page before admitting a PDF original. No placeholder version
        # is persisted: adapter only needs a UUID for its discarded preview anchors.
        parse_pdf(data, uuid4(), settings)
        if meta.baseline_view not in {None, BaselineView.ORIGINAL}:
            raise ServiceError('BASELINE_REQUIRED', 400)
        revisions = False
    actual = UploadMeta(**{**meta.model_dump(mode='python'), 'baseline_view': meta.baseline_view or BaselineView.ORIGINAL})
    version = create_version(actual, actor, db, content=BytesIO(data))
    if revisions or actual.baseline_view != BaselineView.ORIGINAL:
        append_event(AuditEvent(id=uuid4(), matter_id=version.matter_id, actor_id=actor.user_id,
                               action='baseline_selected', entity_type='document', entity_id=version.id,
                               before_hash=None, after_hash=version.sha256, timestamp=datetime.now(timezone.utc),
                               reason=actual.baseline_view.value, correlation_id=uuid4()), db)
    return version


def _parse(data, version, settings):
    kind = _type(data, version.original_name, version.mime)
    if kind == 'docx':
        return parse_docx(data, version, settings)
    return parse_pdf(data, version, settings)


def parse_document(version, settings, *, actor, db):
    trusted = read_version(version.matter_id, version.id, actor, db)
    data = read_original(trusted.matter_id, trusted.id, actor, db)
    result = _parse(data, trusted, _settings(settings, db))
    return save_parse_result(trusted.matter_id, result, actor, db)


def resolve_anchor(anchor, version, *, actor, db, settings=None):
    trusted = read_version(version.matter_id, version.id, actor, db)
    data = read_original(trusted.matter_id, trusted.id, actor, db)
    if anchor.document_version_id != trusted.id:
        raise ServiceError('VERSION_CONFLICT', 409)
    result = _parse(data, trusted, _settings(settings, db))
    matches = [item for item in result.anchors if item.part_name == anchor.part_name and item.element_id == anchor.element_id]
    if len(matches) != 1 or matches[0] != anchor:
        raise ServiceError('VERSION_CONFLICT', 409)
    return AnchoredSpan.model_validate(matches[0].model_dump(mode='python'))
