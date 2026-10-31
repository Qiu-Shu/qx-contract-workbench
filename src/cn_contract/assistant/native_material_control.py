"""One native disclosure consent binds the entire rebuilt material manifest."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import text
from .. import domain as d
from ..security import authenticate, ServiceError
from ..ops.storage import require_active
from . import service, material_preparation as inputs
from .providers.policy import sha, encoded, reservation, budget_exceeded


def authorize(control, value):
    basis = value.basis
    if control._config_version is None or value.expected_config_version != control._config_version:
        raise ServiceError('BLOCKED_LIVE', 403)
    with control._database.session() as db:
        actor = authenticate(value.session_token, db)
        service._owned(actor, basis.expected_scope.conversation_id, db)
        require_active(db)
        fingerprint = sha(encoded(value.model_copy(update={'session_token':'redacted'})))
        previous = control._intents.get(basis.request_id)
        if previous is not None and previous[0] != fingerprint:
            raise ServiceError('VERSION_CONFLICT', 409)
        row = db.execute(text('''SELECT a.* FROM assistant_model_attempts a JOIN assistant_runs r ON r.id=a.run_id
            WHERE r.request_id=:id AND r.conversation_id=:cid'''),
            {'id':str(basis.request_id), 'cid':str(basis.expected_scope.conversation_id)}).mappings().first()
        if row:
            from .providers.attempts import _input
            prepared = _input(row)
            run = service._owned_run(actor, prepared.request.run_id, db)
            if type(prepared) is not d.MainMaterialPreparedInput or prepared.request.basis != basis or run['session_id'] != str(actor.session_id):
                raise ServiceError('VERSION_CONFLICT', 409)
            return {'status':'existing'}
    computed = inputs.preview(actor, inputs.selection_for(basis), control._database, control._config)
    if computed != basis or not control._config.enabled or budget_exceeded(reservation(control._config), value.max_total_usd):
        raise ServiceError('BLOCKED_LIVE', 403)
    with control._database.session() as db:
        # Authenticate and rebuild again after all filesystem reads.
        actor = authenticate(value.session_token, db)
        current, _ = inputs.assemble(actor, inputs.selection_for(basis), db)
        if current != basis.manifest:
            raise ServiceError('VERSION_CONFLICT', 409)
        if previous is not None:
            control._registry.validate_authorization(actor, basis.expected_scope, previous[1])
            return {'status':'authorized'}
        policy = d.MainModelPolicy(policy_id=uuid4(), workspace_id=basis.expected_scope.workspace_id,
            actor_id=actor.user_id, config_sha256=basis.config_sha256,
            allowed_content_sha256s=(basis.manifest_sha256,), max_total_usd=value.max_total_usd, max_calls=1,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=value.valid_for_seconds))
        control._registry.grant(policy, actor.session_id, basis=basis)
        control._intents[basis.request_id] = fingerprint, control._registry.authorization_token(actor, basis.expected_scope)
    return {'status':'authorized'}
