"""Rebuild only referenced local sources; this snapshot is not a write permit."""
from sqlalchemy import text

from .. import domain as d
from ..ops.storage import require_active
from ..security import ServiceError
from . import attachment_files as files, attachment_records as records
from .service import _owned


def _current(actor, scope, db):
    row = _owned(actor, scope.conversation_id, db)
    require_active(db)
    records.expected(row, scope)
    return row


def read_profile_sources(actor, patch: d.ProfilePatch, *, database) -> d.ProfileSourceSnapshot:
    """Read current authorized bytes, then recheck after transaction-free file I/O.

    Quote/hash/anchor claims must still pass merge_profile. A later commit must
    recheck current authorization and versions inside its own write transaction.
    """
    patch = d.ProfilePatch.model_validate(patch.model_dump(mode='python'))
    refs = tuple(ref for change in patch.changes for ref in change.source_refs)
    messages = {ref.message_id for ref in refs if ref.kind == 'message'}
    documents = {ref.attachment_id for ref in refs if ref.kind == 'document'}
    if len(messages) > 200 or len(documents) > 20:
        raise ServiceError('FILE_LIMIT', 413)
    if any(ref.conversation_id != patch.scope.conversation_id for ref in refs):
        raise ServiceError('VERSION_CONFLICT', 409)
    originals, message_views, document_views = [], [], []
    with database.session() as db:
        conversation = _current(actor, patch.scope, db)
        try:
            for identifier in sorted(messages, key=str):
                row = db.execute(text('''SELECT id,role,content,created_at,source_revision
                    FROM assistant_messages WHERE id=:id AND conversation_id=:cid'''),
                    {'id':str(identifier), 'cid':str(patch.scope.conversation_id)}).mappings().first()
                if row is None or row['role'] != 'user' or row['source_revision'] > patch.scope.input_revision:
                    raise ServiceError('VERSION_CONFLICT', 409)
                message_views.append(d.AssistantMessageView(**row))
            items = records.items(conversation, db) if documents else ()
            selected = {item.attachment_id:item.parse_revision for item in items}
            if len(selected) != len(items):
                raise ServiceError('VERSION_CONFLICT', 409)
            for ref in refs:
                if ref.kind == 'document' and selected.get(ref.attachment_id) != ref.parse_revision:
                    raise ServiceError('VERSION_CONFLICT', 409)
            for identifier in sorted(documents, key=str):
                row = records.owned_attachment(actor, patch.scope.conversation_id, identifier, db)
                original = records.attachment_view(row)
                parsed = records.parse_view(records.parse_row(patch.scope.conversation_id, identifier, selected[identifier], db))
                if parsed.result is None:
                    raise ServiceError('VERSION_CONFLICT', 409)
                document_views.append(d.ProfileDocumentSource(conversation_id=patch.scope.conversation_id,
                    attachment_id=identifier, original_name=original.original_name, original_sha256=original.sha256,
                    parse_revision=parsed.revision, result_sha256=parsed.result_sha256, result=parsed.result))
                originals.append(dict(row))
            snapshot = d.ProfileSourceSnapshot(scope=patch.scope, messages=message_views, documents=document_views)
        except (ValueError, TypeError):
            # Stored malformed JSON/DTOs must never echo original text in errors.
            raise ServiceError('VERSION_CONFLICT', 409) from None
    for original in originals:
        files.read_checked(original, database)
    with database.session() as db:
        _current(actor, patch.scope, db)
    return snapshot
