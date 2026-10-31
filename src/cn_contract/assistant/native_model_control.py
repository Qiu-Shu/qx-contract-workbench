"""Private native control operations; no HTTP route or model call lives here."""
import asyncio
from datetime import datetime, timedelta, timezone
from functools import wraps
from uuid import UUID, uuid4

from sqlalchemy import text

from .. import domain as d
from ..config import canonical_json
from ..ops.storage import require_active
from ..security import ServiceError, authenticate
from . import service
from .attachment_records import items
from .context_preview import assemble_context
from .providers.attempts import _input as _stored_input
from .providers.context_codec import build_basis
from .providers.rounds_codec import build_basis_rounds
from .providers.main import DeepSeekProvider
from .providers.policy import encoded, prepare, reservation, sha, validated, budget_exceeded


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


def _payload(model, payload):
    data = payload.model_dump(mode='python', warnings=False) if isinstance(payload, model) else payload
    return validated(model, data)


class NativeModelControl:
    def __init__(self, database, registry, provider_factory=None):
        self._database, self._registry = database, registry
        self._provider_factory = provider_factory or DeepSeekProvider
        self._loop = None
        self._config = None
        self._config_version = None
        self._intents = {}
        self.on_policy_change = lambda session_id=None: None

    def _check_loop(self):
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise ServiceError('BLOCKED_LIVE', 403)

    @_fixed_errors
    def configure(self, payload):
        self._check_loop()
        value = _payload(d.NativeModelConfigure, payload)
        provider = self._provider_factory(value.config, lambda: value.secret)
        actual = _payload(d.MainModelConfig, provider.config)
        if actual != value.config:
            raise ServiceError('BLOCKED_LIVE', 403)
        self.on_policy_change()
        self._registry.configure(provider)
        self._config, self._config_version = value.config, uuid4()
        return {'status': 'configured', 'config_sha256': sha(encoded(value.config)),
            'config_version': str(self._config_version)}

    @_fixed_errors
    def disable(self):
        self._check_loop()
        self.on_policy_change()
        self._registry.configure(None)
        self._config, self._config_version = None, None
        return {'status': 'disabled'}

    @_fixed_errors
    def revoke(self, payload):
        self._check_loop()
        value = _payload(d.NativeModelRevoke, payload)
        with self._database.session() as db:
            actor = authenticate(value.session_token, db)
        self.on_policy_change(actor.session_id)
        self._registry.revoke(actor.session_id)
        return {'status': 'revoked'}

    @_fixed_errors
    def authorize(self, payload):
        self._check_loop()
        value = _payload(d.NativeModelAuthorization, payload)
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
            run = db.execute(text('''SELECT r.*,m.content FROM assistant_runs r
                JOIN assistant_messages m ON m.id=r.message_id WHERE r.request_id=:request'''),
                {'request': str(basis.request_id)}).mappings().first()
            if run is not None:
                expected = basis.expected_scope.model_copy(update={
                    'input_revision': basis.expected_scope.input_revision+1})
                if (run['conversation_id'] != str(basis.expected_scope.conversation_id)
                        or run['actor_id'] != str(actor.user_id) or run['session_id'] != str(actor.session_id)
                        or d.ScopeSnapshot.model_validate_json(run['scope_snapshot']) != expected
                        or sha(run['content']) != basis.content_sha256 or run['requested_skill'] is not None):
                    raise ServiceError('VERSION_CONFLICT', 409)
                original = d.AssistantMessageInput(request_id=basis.request_id, expected_scope=basis.expected_scope,
                    expected_composer_revision=basis.expected_composer_revision, content=run['content'])
                digest = service._digest({'actor_id': str(actor.user_id), 'workspace_id': conversation['workspace_id'],
                    'conversation_id': conversation['id'], 'request': original.model_dump(mode='json')})
                if run['request_sha256'] != digest:
                    raise ServiceError('VERSION_CONFLICT', 409)
                return {'status': 'existing'}
            service._expected(conversation, basis)
            if (not conversation['draft_input'].strip() or sha(conversation['draft_input']) != basis.content_sha256
                    or items(conversation, db)):
                raise ServiceError('BLOCKED_LIVE', 403)
            if previous is not None:
                self._registry.validate_authorization(actor, basis.expected_scope, previous[1])
                return {'status': 'authorized'}
            config = self._config
            if not config.enabled or budget_exceeded(reservation(config), value.max_total_usd):
                raise ServiceError('BLOCKED_LIVE', 403)
            prepare(d.MainRequest(run_id=UUID(int=0), message_id=UUID(int=0), scope=basis.expected_scope,
                content=conversation['draft_input'], source_sha256=basis.content_sha256), config)
            policy = validated(d.MainModelPolicy, dict(policy_id=uuid4(), workspace_id=basis.expected_scope.workspace_id,
                actor_id=actor.user_id, config_sha256=sha(encoded(config)), allowed_content_sha256s=(basis.content_sha256,),
                max_total_usd=value.max_total_usd, max_calls=1,
                expires_at=datetime.now(timezone.utc)+timedelta(seconds=value.valid_for_seconds)))
            self._registry.grant(policy, actor.session_id, basis=basis)
            token = self._registry.authorization_token(actor, basis.expected_scope)
            # Keep replay tombstones, not leases that retain retired providers and secrets.
            self._intents[basis.request_id] = fingerprint, token
        return {'status': 'authorized'}

    @_fixed_errors
    def authorize_material(self, payload):
        from .native_material_control import authorize
        self._check_loop()
        return authorize(self, _payload(d.NativeMaterialAuthorization, payload))

    @_fixed_errors
    def authorize_profile(self, payload):
        from .native_profile_control import authorize
        self._check_loop()
        return authorize(self, _payload(d.NativeProfileAuthorization, payload))

    @_fixed_errors
    def authorize_context(self, payload):
        """One native grant for a server-rebuilt library-context basis; no new scopes."""
        self._check_loop()
        value = _payload(d.NativeContextAuthorization, payload)
        with self._database.session() as db:
            actor = authenticate(value.session_token, db)
            basis = value.basis
            # The explicit bounded-rounds shape and the basis format must agree.
            fmt = 'library-context-v2' if value.max_rounds > 1 else 'library-context-v1'
            if basis.input_format != fmt:
                raise ServiceError('BLOCKED_LIVE', 403)
            conversation = service._owned(actor, basis.expected_scope.conversation_id, db)
            require_active(db)
            if self._config_version is None or value.expected_config_version != self._config_version:
                raise ServiceError('BLOCKED_LIVE', 403)
            fingerprint = sha(canonical_json({'actor': str(actor.user_id), 'session': str(actor.session_id),
                'approval': value.model_dump(mode='json', exclude={'session_token'})}))
            previous = self._intents.get(basis.request_id)
            if previous is not None and previous[0] != fingerprint:
                raise ServiceError('VERSION_CONFLICT', 409)
            run = db.execute(text('''SELECT r.*,m.content FROM assistant_runs r
                JOIN assistant_messages m ON m.id=r.message_id WHERE r.request_id=:request'''),
                {'request': str(basis.request_id)}).mappings().first()
            if run is not None:
                attempt = db.execute(text('''SELECT * FROM assistant_model_attempts
                    WHERE run_id=:id AND round_no=1'''),
                    {'id': run['id']}).mappings().first()
                expected = basis.expected_scope.model_copy(update={
                    'input_revision': basis.expected_scope.input_revision+1})
                if (attempt is None or attempt['input_format'] != fmt
                        or run['conversation_id'] != str(basis.expected_scope.conversation_id)
                        or run['actor_id'] != str(actor.user_id) or run['session_id'] != str(actor.session_id)
                        or d.ScopeSnapshot.model_validate_json(run['scope_snapshot']) != expected
                        or run['requested_skill'] is not None):
                    raise ServiceError('VERSION_CONFLICT', 409)
                prepared = _stored_input(attempt)
                expected_type = (d.MainContextRoundsPreparedInput if fmt == 'library-context-v2'
                                 else d.MainContextPreparedInput)
                if (type(prepared) is not expected_type
                        or getattr(prepared, 'round_no', 1) != 1):
                    raise ServiceError('VERSION_CONFLICT', 409)
                if prepared.request.basis != basis or prepared.request.manifest.question != run['content']:
                    raise ServiceError('VERSION_CONFLICT', 409)
                original = d.AssistantMessageInput(request_id=basis.request_id, expected_scope=basis.expected_scope,
                    expected_composer_revision=basis.expected_composer_revision, content=run['content'])
                digest = service._digest({'actor_id': str(actor.user_id), 'workspace_id': conversation['workspace_id'],
                    'conversation_id': conversation['id'], 'request': original.model_dump(mode='json')})
                if run['request_sha256'] != digest:
                    raise ServiceError('VERSION_CONFLICT', 409)
                return {'status': 'existing'}
            service._expected(conversation, basis)
            if (not conversation['draft_input'].strip() or items(conversation, db)):
                raise ServiceError('BLOCKED_LIVE', 403)
            if previous is not None:
                self._registry.validate_authorization(actor, basis.expected_scope, previous[1])
                return {'status': 'authorized'}
            config = self._config
            if not config.enabled or budget_exceeded(reservation(config), value.max_total_usd):
                raise ServiceError('BLOCKED_LIVE', 403)
            # The exact approved bytes are rebuilt from persisted citations and the
            # current draft; a client-presented basis only names what to rebuild.
            scope, manifest, records = assemble_context(actor, conversation,
                tuple(item.saved_citation_id for item in basis.source_bindings), db)
            builder = build_basis_rounds if fmt == 'library-context-v2' else build_basis
            computed = builder(basis.request_id, manifest, scope,
                conversation['composer_revision'], config, records)
            if computed != basis:
                raise ServiceError('BLOCKED_LIVE', 403)
            policy = validated(d.MainModelPolicy, dict(policy_id=uuid4(), workspace_id=basis.expected_scope.workspace_id,
                actor_id=actor.user_id, config_sha256=sha(encoded(config)), allowed_content_sha256s=(basis.manifest_sha256,),
                max_total_usd=value.max_total_usd, max_calls=value.max_rounds,
                expires_at=datetime.now(timezone.utc)+timedelta(seconds=value.valid_for_seconds)))
            self._registry.grant(policy, actor.session_id, basis=basis)
            token = self._registry.authorization_token(actor, basis.expected_scope)
            self._intents[basis.request_id] = fingerprint, token
        return {'status': 'authorized'}
