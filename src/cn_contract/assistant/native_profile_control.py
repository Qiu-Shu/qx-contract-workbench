"""Private one-shot approval for server-rebuilt profile bytes and save intent."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import text

from .. import domain as d
from ..config import canonical_json
from ..security import ServiceError, authenticate
from . import profile_preparation_service, profile_store, service, conversation_history
from .providers import attempts, profile_preparation
from .providers.policy import encoded, reservation, sha, validated, budget_exceeded


def _existing(actor, conversation, run, basis, config, db):
    """Compare immutable registration, even after the draft or save baseline advances."""
    attempt = db.execute(text('''SELECT * FROM assistant_model_attempts
        WHERE run_id=:id AND round_no=1'''), {'id': run['id']}).mappings().first()
    expected = basis.expected_scope.model_copy(update={
        'input_revision': basis.expected_scope.input_revision + 1})
    if (attempt is None or attempt['input_format'] != 'profile-text-v1'
            or run['conversation_id'] != conversation['id']
            or run['actor_id'] != str(actor.user_id) or run['session_id'] != str(actor.session_id)
            or d.ScopeSnapshot.model_validate_json(run['scope_snapshot']) != expected
            or run['requested_skill'] is not None):
        raise ServiceError('VERSION_CONFLICT', 409)
    prepared = attempts._input(attempt)
    message = db.execute(text('''SELECT id,role,content,created_at,source_revision
        FROM assistant_messages WHERE id=:id AND conversation_id=:cid'''),
        {'id': run['message_id'], 'cid': conversation['id']}).mappings().first()
    if message is None or type(prepared) is not d.MainProfilePreparedInput or prepared.basis != basis:
        raise ServiceError('VERSION_CONFLICT', 409)
    if basis.conversation_history and conversation_history.for_message(db, basis.expected_scope,
            message['content'], config, before_at=d.AssistantMessageView(**message).created_at) != basis.conversation_history:
        raise ServiceError('VERSION_CONFLICT', 409)
    original = d.AssistantMessageInput(request_id=basis.request_id, expected_scope=basis.expected_scope,
        expected_composer_revision=basis.expected_composer_revision, content=message['content'])
    digest = service._digest({'actor_id': str(actor.user_id), 'workspace_id': conversation['workspace_id'],
        'conversation_id': conversation['id'], 'request': original.model_dump(mode='json')})
    rebuilt = profile_preparation.prepare(service.get_run(actor, UUID(run['id']), db),
        d.AssistantMessageView(**message), basis, config,
        composer_revision=basis.expected_composer_revision + 1)
    if (run['request_sha256'] != digest or rebuilt != prepared
            or attempt['conversation_id'] != conversation['id']
            or attempts._model(d.MainModelConfig, attempt['config_json']) != config
            or attempt['config_sha256'] != sha(encoded(config))
            or attempt['request_sha256'] != sha(prepared.wire_payload_json)):
        raise ServiceError('VERSION_CONFLICT', 409)


def authorize(control, value):
    with control._database.session() as db:
        actor = authenticate(value.session_token, db)
        basis = value.basis
        conversation = profile_store._writable(actor, basis.expected_scope.conversation_id, db)
        config = control._registry.configuration()
        if (control._config_version is None or value.expected_config_version != control._config_version
                or config is None or not config.enabled):
            raise ServiceError('BLOCKED_LIVE', 403)
        fingerprint = sha(canonical_json({'actor': str(actor.user_id), 'session': str(actor.session_id),
            'approval': value.model_dump(mode='json', exclude={'session_token'})}))
        previous = control._intents.get(basis.request_id)
        if previous is not None and previous[0] != fingerprint:
            raise ServiceError('VERSION_CONFLICT', 409)
        run = db.execute(text('SELECT * FROM assistant_runs WHERE request_id=:request'),
            {'request': str(basis.request_id)}).mappings().first()
        if run is not None:
            _existing(actor, conversation, run, basis, config, db)
            return {'status': 'existing'}
        original = d.AssistantMessageInput(request_id=basis.request_id, expected_scope=basis.expected_scope,
            expected_composer_revision=basis.expected_composer_revision, content=conversation['draft_input'])
        computed = profile_preparation_service.build_profile_basis(actor, basis.expected_scope.conversation_id,
            original, db, config=config, project_intake=basis.project_intake)
        if computed != basis or budget_exceeded(reservation(config), value.max_total_usd):
            raise ServiceError('BLOCKED_LIVE', 403)
        # A repeated confirmation cannot bypass a changed local save target.
        if previous is not None:
            control._registry.validate_authorization(actor, basis.expected_scope, previous[1])
            return {'status': 'authorized'}
        policy = validated(d.MainModelPolicy, dict(policy_id=uuid4(),
            workspace_id=basis.expected_scope.workspace_id, actor_id=actor.user_id,
            config_sha256=sha(encoded(config)), allowed_content_sha256s=(profile_preparation.basis_digest(basis),),
            max_total_usd=value.max_total_usd, max_calls=1,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=value.valid_for_seconds)))
        control._registry.grant(policy, actor.session_id, basis=basis)
        token = control._registry.authorization_token(actor, basis.expected_scope)
        control._intents[basis.request_id] = fingerprint, token
    return {'status': 'authorized'}
