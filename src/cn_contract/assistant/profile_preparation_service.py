"""Rebuild profile inputs from current storage; never a send or save permit.

The caller owns the session. Existing authorization may flush or audit denial;
this module adds no business records. Runtime permission/budget gates still apply.
"""
from uuid import UUID

from sqlalchemy import text

from .. import domain as d
from ..intake import service as intake
from ..security import ServiceError
from . import attachment_records as records, profile_store, service, conversation_history
from .providers import profile_preparation


def _validated(kind, value):
    if type(value) is not kind:
        raise ValueError('invalid profile input')
    return kind.model_validate(value.model_dump(mode='python', warnings=False))


def _identifier(value):
    if type(value) is not UUID:
        raise ValueError('invalid profile identity')
    return value


def _baseline(actor, conversation, db):
    scope = service._snapshot(conversation)
    previous = profile_store._profile(scope.conversation_id, db)
    if previous is not None:
        fixed = ('workspace_id', 'conversation_id', 'scope_kind', 'scope_ref', 'binding_revision')
        if (any(getattr(previous.scope, key) != getattr(scope, key) for key in fixed)
                or previous.scope.input_revision > scope.input_revision
                or previous.scope.materials_revision > scope.materials_revision):
            raise ServiceError('VERSION_CONFLICT', 409)
    target = conversation['scope_ref'] if conversation['scope_kind'] == 'intake' else conversation['projection_intake_id']
    current = intake.read(UUID(target), actor, db) if target is not None else None
    if current is not None and current.matter_id is not None:
        raise ServiceError('VERSION_CONFLICT', 409)
    return dict(base_profile_revision=previous.revision if previous else 0,
                expected_intake_id=current.id if current else None,
                expected_intake_revision=current.revision if current else None)


def _text_only(conversation, db):
    if records.items(conversation, db):
        raise ServiceError('NOT_SUPPORTED', 422)


def build_profile_basis(actor, cid, message, db, *, config, project_intake=False) -> d.MainProfileSendBasis:
    """Describe the exact current draft and server-owned save baseline."""
    try:
        actor = _validated(d.Actor, actor)
        cid = _identifier(cid)
        message = _validated(d.AssistantMessageInput, message)
        config = _validated(d.MainModelConfig, config)
        conversation = profile_store._writable(actor, cid, db)
        service._expected(conversation, message)
        if message.content != conversation['draft_input']:
            raise ServiceError('VERSION_CONFLICT', 409)
        if message.requested_skill is not None or message.attachment_ids:
            raise ServiceError('NOT_SUPPORTED', 422)
        _text_only(conversation, db)
        return profile_preparation.build_basis(message, config, project_intake=project_intake,
                                               conversation_history=conversation_history.for_message(db, message.expected_scope, message.content, config),
                                               **_baseline(actor, conversation, db))
    except (ValueError, TypeError, KeyError):
        raise ServiceError('VERSION_CONFLICT', 409) from None


def prepare_profile(actor, run_id, basis, db, *, config) -> d.MainProfilePreparedInput:
    """Revalidate a saved submission without adopting a newer draft or baseline."""
    try:
        actor = _validated(d.Actor, actor)
        run_id = _identifier(run_id)
        basis = _validated(d.MainProfileSendBasis, basis)
        config = _validated(d.MainModelConfig, config)
        row = service._owned_run(actor, run_id, db)
        conversation = profile_store._writable(actor, UUID(row['conversation_id']), db)
        if row['actor_id'] != str(actor.user_id) or row['session_id'] != str(actor.session_id):
            raise ServiceError('CROSS_MATTER_DENIED', 403)
        if row['state'] not in ('queued', 'generating') or row['cancel_requested'] != 0:
            raise ServiceError('STATE_CONFLICT', 409)
        if row['requested_skill'] is not None:
            raise ServiceError('NOT_SUPPORTED', 422)
        expected = basis.expected_scope.model_copy(update={
            'input_revision': basis.expected_scope.input_revision + 1})
        records.expected(conversation, expected)
        if conversation['composer_revision'] < basis.expected_composer_revision + 1:
            raise ServiceError('VERSION_CONFLICT', 409)
        _text_only(conversation, db)
        message_row = db.execute(text('''SELECT id,role,content,created_at,source_revision
            FROM assistant_messages WHERE id=:id AND conversation_id=:cid'''),
            {'id':row['message_id'], 'cid':conversation['id']}).mappings().first()
        if message_row is None or message_row['role'] != 'user' or message_row['source_revision'] != expected.input_revision:
            raise ServiceError('VERSION_CONFLICT', 409)
        message = d.AssistantMessageView(**message_row)
        submission = d.AssistantMessageInput(request_id=basis.request_id, expected_scope=basis.expected_scope,
            expected_composer_revision=basis.expected_composer_revision, content=message.content)
        digest = service._digest({'actor_id':str(actor.user_id), 'workspace_id':conversation['workspace_id'],
            'conversation_id':conversation['id'], 'request':submission.model_dump(mode='json')})
        if row['request_sha256'] != digest:
            raise ServiceError('VERSION_CONFLICT', 409)
        rebuilt = profile_preparation.build_basis(submission, config, project_intake=basis.project_intake,
            conversation_history=(conversation_history.for_message(db, basis.expected_scope, message.content,
                config, before_at=message.created_at) if basis.conversation_history else ()),
            **_baseline(actor, conversation, db))
        if rebuilt != basis:
            raise ServiceError('VERSION_CONFLICT', 409)
        return profile_preparation.prepare(service.get_run(actor, run_id, db), message, basis, config,
                                            composer_revision=basis.expected_composer_revision + 1)
    except (ValueError, TypeError, KeyError):
        raise ServiceError('VERSION_CONFLICT', 409) from None
