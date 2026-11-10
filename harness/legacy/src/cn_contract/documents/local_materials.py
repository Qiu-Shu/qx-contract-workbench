"""Case- and version-bound local consent stored in the existing immutable audit."""
from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

from sqlalchemy import select

from ..audit import append_event
from ..domain import AuditEvent, LocalMaterialPolicy
from ..persistence import AuditRow, MatterRow, configured_database, read_version
from ..security import ServiceError, authorize


def policy_hash():
    return hashlib.sha256(LocalMaterialPolicy().model_dump_json().encode()).hexdigest()


def is_local(matter_id, db):
    matter = db.get(MatterRow, str(matter_id), populate_existing=True)
    return bool(matter and json.loads(matter.payload)['client_ref'].startswith('LOCAL-'))


def require_policy(matter_id, db):
    if not is_local(matter_id, db) or getattr(configured_database(db), '_local_materials_enabled', False) is not True:
        raise ServiceError('DATA_POLICY_UNAPPROVED', 409)
    rows = list(db.scalars(select(AuditRow).where(AuditRow.matter_id == str(matter_id),
        AuditRow.action == 'local_material_case_created')))
    if len(rows) != 1:
        raise ServiceError('DATA_POLICY_UNAPPROVED', 409)
    event = json.loads(rows[0].payload)
    if event['entity_id'] != str(matter_id) or event['after_hash'] != policy_hash():
        raise ServiceError('DATA_POLICY_UNAPPROVED', 409)
    return LocalMaterialPolicy()


def record_case(matter_id, actor, db):
    authorize(actor, matter_id, 'upload', db)
    if getattr(configured_database(db), '_local_materials_enabled', False) is not True:
        raise ServiceError('DATA_POLICY_UNAPPROVED', 409)
    append_event(AuditEvent(id=uuid4(), matter_id=matter_id, actor_id=actor.user_id,
        action='local_material_case_created', entity_type='matter', entity_id=matter_id,
        before_hash=None, after_hash=policy_hash(), timestamp=datetime.now(timezone.utc),
        reason='LOCAL_WORKPAPER_CASE_EXPLICIT_SELECTION', correlation_id=uuid4()), db)


def confirm_upload(matter_id, mime, confirmed, policy_id, actor, db):
    authorize(actor, matter_id, 'upload', db)
    policy = require_policy(matter_id, db)
    if confirmed != 'yes' or policy_id != policy.policy_id:
        raise ServiceError('DATA_POLICY_UNAPPROVED', 409)
    if mime != policy.allowed_mime:
        raise ServiceError('NOT_SUPPORTED', 409)


def record_admission(version, actor, db):
    authorize(actor, version.matter_id, 'upload', db)
    require_policy(version.matter_id, db)
    append_event(AuditEvent(id=uuid4(), matter_id=version.matter_id, actor_id=actor.user_id,
        action='local_material_admitted', entity_type='document', entity_id=version.id,
        before_hash=policy_hash(), after_hash=version.sha256, timestamp=datetime.now(timezone.utc),
        reason='EXPLICIT_LOCAL_PROCESSING_NO_EXTERNAL_SHARING', correlation_id=uuid4()), db)


def require_versions(versions, actor, db):
    for version in versions:
        authorize(actor, version.matter_id, 'read', db)
        policy = require_policy(version.matter_id, db)
        actual = read_version(version.matter_id, version.id, actor, db)
        if version != actual or version.mime != policy.allowed_mime:
            raise ServiceError('DATA_POLICY_UNAPPROVED', 409)
        rows = db.scalars(select(AuditRow).where(AuditRow.matter_id == str(version.matter_id),
            AuditRow.action == 'local_material_admitted'))
        matches = [json.loads(row.payload) for row in rows if json.loads(row.payload)['entity_id'] == str(version.id)]
        if len(matches) != 1 or matches[0]['after_hash'] != version.sha256 or matches[0]['before_hash'] != policy_hash():
            raise ServiceError('DATA_POLICY_UNAPPROVED', 409)
