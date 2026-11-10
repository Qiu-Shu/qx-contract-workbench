"""Private Jev control; only exact, independently approved drafts grant egress."""
from datetime import datetime, timedelta, timezone
from functools import wraps
from uuid import uuid4

from sqlalchemy import text

from .. import domain as d
from ..config import canonical_json
from ..ops.storage import require_active
from ..security import ServiceError, authenticate
from . import service
from .attachment_records import items
from .providers import jev_codec
from .providers.jev import JevProvider
from .providers.judge_policy import copy, encoded, sha, validated


def _fixed_errors(method):
    @wraps(method)
    def invoke(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except ServiceError:
            raise
        except Exception:
            raise ServiceError('BLOCKED_LIVE', 403) from None
    return invoke


def _payload(model, value):
    data = value.model_dump(mode='python', warnings=False) if type(value) is model else value
    return validated(model, data)


def _existing(actor, basis, conversation, db):
    run = db.execute(text('''SELECT r.*,m.content,m.conversation_id AS message_conversation,
        m.role AS message_role,m.source_revision FROM assistant_runs r
        JOIN assistant_messages m ON m.id=r.message_id WHERE r.request_id=:request'''),
        {'request': str(basis.request_id)}).mappings().first()
    if run is None:
        return False
    expected = basis.expected_scope.model_copy(update={'input_revision': basis.expected_scope.input_revision+1})
    if (run['conversation_id'] != conversation['id'] or run['message_conversation'] != conversation['id']
            or run['actor_id'] != str(actor.user_id) or run['session_id'] != str(actor.session_id)
            or d.ScopeSnapshot.model_validate_json(run['scope_snapshot']) != expected
            or run['message_role'] != 'user' or run['source_revision'] != expected.input_revision
            or sha(run['content']) != basis.content_sha256 or run['requested_skill'] is not None):
        raise ServiceError('VERSION_CONFLICT', 409)
    original = d.AssistantMessageInput(request_id=basis.request_id, expected_scope=basis.expected_scope,
        expected_composer_revision=basis.expected_composer_revision, content=run['content'])
    digest = service._digest({'actor_id': str(actor.user_id), 'workspace_id': conversation['workspace_id'],
        'conversation_id': conversation['id'], 'request': original.model_dump(mode='json')})
    if run['request_sha256'] != digest:
        raise ServiceError('VERSION_CONFLICT', 409)
    return True


def _available_slot(runtime, workspace_id, db):
    pending = db.scalar(text('''SELECT 1 FROM assistant_judge_attempts a
        JOIN assistant_conversations c ON c.id=a.conversation_id
        WHERE c.workspace_id=:workspace AND a.state IN ('reserved','sending') LIMIT 1'''),
        {'workspace': str(workspace_id)})
    if pending:
        raise ServiceError('STATE_CONFLICT', 409)
    current = runtime.policy
    if current is None or current.expires_at <= datetime.now(timezone.utc):
        return
    if current.max_calls == 1 and len(current.permissions) == 1 and current.workspace_id == workspace_id:
        permission = current.permissions[0]
        run = db.execute(text('''SELECT r.*,m.content,a.state AS judge_state,a.policy_sha256,a.input_hash,
            a.policy_id,a.purpose FROM assistant_runs r
            JOIN assistant_conversations c ON c.id=r.conversation_id
            JOIN assistant_messages m ON m.id=r.message_id
            LEFT JOIN assistant_judge_attempts a ON a.run_id=r.id
            WHERE r.request_id=:request AND c.workspace_id=:workspace
            AND r.actor_id=:actor AND r.session_id=:session'''),
            {'request': str(permission.local_request_id), 'workspace': str(workspace_id),
             'actor': str(current.actor_id), 'session': str(current.session_id)}).mappings().first()
        if run is not None:
            if (run['judge_state'] in ('received', 'not_sent', 'sent_unknown')
                    and run['policy_id'] == str(current.policy_id) and run['policy_sha256'] == sha(encoded(current))
                    and run['purpose'] == permission.purpose and run['input_hash'] == permission.input_hash):
                return
            if run['judge_state'] is None and run['state'] in ('completed', 'failed', 'cancelled', 'interrupted'):
                original = d.JudgeRequest(local_request_id=permission.local_request_id,
                    scope=d.ScopeSnapshot.model_validate_json(run['scope_snapshot']), purpose=permission.purpose,
                    text=run['content'], explicit_skill=run['requested_skill'])
                if jev_codec.input_hash(original, runtime.configuration()) == permission.input_hash:
                    return
    raise ServiceError('STATE_CONFLICT', 409)


class NativeJudgeControl:
    def __init__(self, runtime, provider_factory=None, *, database=None):
        self._runtime = runtime
        self._database = database
        self._provider_factory = provider_factory or JevProvider
        self._config_version = None
        self._intents = {}

    def configure(self, payload):
        self._runtime.bind_execution()
        try:
            value = _payload(d.NativeJudgeConfigure, payload)
            provider = self._provider_factory(value.config, lambda secret=value.secret: secret)
            if copy(d.JevConfig, provider.config) != value.config:
                raise ServiceError('BLOCKED_LIVE', 403)
            version = uuid4()
            result = {'status': 'configured', 'config_sha256': sha(encoded(value.config)),
                      'config_version': str(version)}
            self._runtime.configure(provider)
            self._config_version = version
            return result
        except ServiceError:
            raise
        except Exception:
            raise ServiceError('BLOCKED_LIVE', 403) from None

    def disable(self):
        self._runtime.bind_execution()
        self._runtime.configure(None)
        self._config_version = None
        return {'status': 'disabled'}

    @_fixed_errors
    def authorize(self, payload):
        self._runtime.bind_execution()
        if self._database is None:
            raise ServiceError('BLOCKED_LIVE', 403)
        value = _payload(d.NativeJudgeAuthorization, payload)
        with self._database.session() as db:
            actor = authenticate(value.session_token, db)
            basis = value.basis
            conversation = service._owned(actor, basis.expected_scope.conversation_id, db)
            require_active(db)
            if self._config_version is None or value.expected_config_version != self._config_version:
                raise ServiceError('BLOCKED_LIVE', 403)
            fingerprint = sha(canonical_json({'actor': str(actor.user_id), 'session': str(actor.session_id),
                'approval': value.model_dump(mode='json', exclude={'session_token'})}))
            previous = self._intents.get(basis.request_id)
            if previous is not None and previous[0] != fingerprint:
                raise ServiceError('VERSION_CONFLICT', 409)
            if _existing(actor, basis, conversation, db):
                return {'status': 'existing'}
            service._expected(conversation, basis)
            if (not conversation['draft_input'].strip() or sha(conversation['draft_input']) != basis.content_sha256
                    or items(conversation, db)):
                raise ServiceError('BLOCKED_LIVE', 403)
            config = self._runtime.configuration()
            request = d.JudgeRequest(local_request_id=basis.request_id,
                scope=basis.expected_scope.model_copy(update={'input_revision': basis.expected_scope.input_revision+1}),
                purpose=basis.purpose, text=conversation['draft_input'], explicit_skill=None)
            if not config.enabled:
                raise ServiceError('BLOCKED_LIVE', 403)
            jev_codec.build_request(request, config)
            if previous is not None:
                if self._runtime.snapshot_for(actor, request)[2] != previous[1]:
                    raise ServiceError('BLOCKED_LIVE', 403)
                return {'status': 'authorized'}
            _available_slot(self._runtime, basis.expected_scope.workspace_id, db)
            policy = validated(d.JudgePolicy, dict(policy_id=uuid4(), workspace_id=basis.expected_scope.workspace_id,
                actor_id=actor.user_id, session_id=actor.session_id, config_sha256=sha(encoded(config)),
                permissions=(d.JudgePermission(local_request_id=request.local_request_id, purpose=request.purpose,
                    input_hash=jev_codec.input_hash(request, config)),), reserved_usd=value.max_total_usd,
                max_total_usd=value.max_total_usd, max_calls=1,
                expires_at=datetime.now(timezone.utc)+timedelta(seconds=value.valid_for_seconds)))
        # Publish only after commit; this synchronous app-loop path cannot interleave.
        version = self._runtime.grant(policy)
        self._intents[basis.request_id] = fingerprint, version
        return {'status': 'authorized'}

    @_fixed_errors
    def revoke(self, payload):
        self._runtime.bind_execution()
        if self._database is None:
            raise ServiceError('BLOCKED_LIVE', 403)
        value = _payload(d.NativeJudgeRevoke, payload)
        with self._database.session() as db:
            actor = authenticate(value.session_token, db)
            policy = self._runtime.policy
            if policy is not None and (policy.actor_id != actor.user_id or policy.session_id != actor.session_id):
                raise ServiceError('CROSS_MATTER_DENIED', 403)
        self._runtime.revoke()
        return {'status': 'revoked'}
