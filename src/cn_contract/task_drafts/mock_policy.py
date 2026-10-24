"""Server-side permission for a frozen task's local, registered-fiction review."""
from uuid import UUID

from sqlalchemy import select

from .. import domain as d
from ..assistant import attachment_files, attachment_records
from ..documents.ingest import DOCX_MIME
from ..documents import local_materials
from ..ops import backup
from ..ops.storage import require_active
from ..persistence import DocumentRow, configured_database, read_matter
from ..security import ServiceError


def require_mock_case(matter_id, actor, db):
    require_active(db)
    matter = read_matter(matter_id, actor, db)
    rows = list(db.scalars(select(DocumentRow).where(DocumentRow.matter_id == str(matter_id))))
    superseded = {row.supersedes_id for row in rows if row.supersedes_id}
    current = [row for row in rows if row.id not in superseded]
    registered = backup._registered_hashes() | set(getattr(configured_database(db), '_assistant_synthetic_hashes', ()))
    if (local_materials.is_local(matter_id, db) or not matter.client_ref.startswith('SYNTHETIC-')
            or not current or any(row.sha256 not in registered for row in current)):
        raise ServiceError('DATA_POLICY_UNAPPROVED', 409)


def sources(execution, actor, db):
    """Read trusted bytes and the exact frozen parser revision, never a path input."""
    database = configured_database(db)
    registered = backup._registered_hashes() | set(getattr(database, '_assistant_synthetic_hashes', ()))
    result = {}
    for event in execution.manifest.events:
        for media in event.media:
            if media.excluded:
                continue
            if media.status != 'ready' or media.attachment_id is None or media.parse_revision is None:
                raise ServiceError('STATE_CONFLICT', 409)
            row = attachment_records.owned_attachment(actor, execution.manifest.conversation_id,
                media.attachment_id, db)
            policy = d.AssistantMaterialPolicy.model_validate_json(row['policy_json'])
            if policy.material_mode != 'synthetic' or row['sha256'] not in registered:
                raise ServiceError('DATA_POLICY_UNAPPROVED', 409)
            if row['mime'] != DOCX_MIME:
                raise ServiceError('FILE_UNSUPPORTED', 400)
            parsed = attachment_records.parse_view(attachment_records.parse_row(
                execution.manifest.conversation_id, media.attachment_id, media.parse_revision, db))
            if (row['sha256'] != media.sha256 or parsed.result_sha256 != media.result_sha256
                    or parsed.reading_status != 'readable' or parsed.baseline_view is None):
                raise ServiceError('VERSION_CONFLICT', 409)
            source = (row, parsed, attachment_files.read_checked(row, database))
            if media.attachment_id in result:
                if result[media.attachment_id][1] != parsed:
                    raise ServiceError('VERSION_CONFLICT', 409)
            else:
                result[media.attachment_id] = source
    if not result or execution.manifest.main_attachment_id not in result:
        raise ServiceError('STATE_CONFLICT', 409)
    return result


def require_mock_execution(identifier, context, actor, db):
    """Recheck on run creation and later reads; a config label grants nothing."""
    from .service import read_execution
    try:
        execution_id = UUID(str(identifier))
    except (ValueError, TypeError, AttributeError):
        raise ServiceError('DATA_POLICY_UNAPPROVED', 409) from None
    execution = read_execution(actor, execution_id, db)
    if (execution.state not in {'running', 'completed', 'failed'}
            or execution.matter_id != context.matter.id
            or dict(execution.document_versions) != {v.id: v.sha256 for v in context.document_versions}):
        raise ServiceError('VERSION_CONFLICT', 409)
    require_mock_case(context.matter.id, actor, db)
    source_items = sources(execution, actor, db)
    if set(source_items) != set(execution.source_versions):
        raise ServiceError('VERSION_CONFLICT', 409)
    for source_id, version_id in execution.source_versions.items():
        if execution.document_versions.get(version_id) != source_items[source_id][0]['sha256']:
            raise ServiceError('VERSION_CONFLICT', 409)
