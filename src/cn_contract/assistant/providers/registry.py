"""Trusted, event-loop-owned configuration and login-session grants."""
import asyncio
from datetime import datetime, timezone
from uuid import UUID

from ... import domain as d
from ...security import ServiceError
from .policy import MainModelRuntime, encoded, require_policy, sha, validated


def _copy(model, value):
    try:
        if not isinstance(value, model):
            raise ValueError
        return validated(model, value.model_dump(mode='python', warnings=False))
    except Exception:
        raise ServiceError('BLOCKED_LIVE', 403) from None


def _config(provider):
    try:
        if not callable(provider.generate):
            raise ValueError
        return _copy(d.MainModelConfig, provider.config)
    except Exception:
        raise ServiceError('BLOCKED_LIVE', 403) from None


def _session_id(value):
    if type(value) is not UUID:
        raise ServiceError('BLOCKED_LIVE', 403)
    return value


def _identity(actor, scope):
    actor = _copy(d.Actor, actor)
    scope = _copy(d.ScopeSnapshot, scope)
    return scope.workspace_id, actor.user_id, actor.session_id


class MainModelRegistry:
    def __init__(self):
        self._loop = None
        self._provider = None
        self._config = None
        self._version = object()
        self._grants = {}
        self._seen_policies = {}

    def _check_loop(self, *, bind=False):
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None
        if self._loop is None:
            if bind:
                if current is None:
                    raise ServiceError('BLOCKED_LIVE', 403)
                self._loop = current
        elif current is not self._loop:
            raise ServiceError('BLOCKED_LIVE', 403)

    def _current_config(self):
        config = _config(self._provider)
        if config != self._config:
            raise ServiceError('BLOCKED_LIVE', 403)
        return config

    def configure(self, provider):
        self._check_loop()
        config = _config(provider) if provider is not None else None
        self._provider, self._config = provider, config
        self._version = object()
        self._grants.clear()

    def configuration(self):
        """Local preview only: inspecting configuration never resolves a grant."""
        self._check_loop()
        return self._current_config() if self._provider is not None else None

    def grant(self, policy, session_id, *, basis=None):
        self._check_loop()
        session_id = _session_id(session_id)
        policy = _copy(d.MainModelPolicy, policy)
        if basis is not None:
            basis = (_copy(d.MainMaterialSendBasis, basis) if isinstance(basis, d.MainMaterialSendBasis)
                     else _copy(d.MainProfileSendBasis, basis) if isinstance(basis, d.MainProfileSendBasis)
                     else _copy(d.MainContextSendBasis, basis) if isinstance(basis, d.MainContextSendBasis)
                     else _copy(d.MainSendApproval, basis))
        config = self._current_config()
        if (not config.enabled or policy.config_sha256 != sha(encoded(config))
                or policy.expires_at <= datetime.now(timezone.utc)):
            raise ServiceError('BLOCKED_LIVE', 403)
        if isinstance(basis, d.MainMaterialSendBasis):
            if (basis.expected_scope.workspace_id != policy.workspace_id or policy.max_calls != 1
                    or policy.allowed_content_sha256s != (basis.manifest_sha256,)
                    or basis.config_sha256 != sha(encoded(config))
                    or not callable(getattr(self._provider, 'generate_material', None))):
                raise ServiceError('BLOCKED_LIVE', 403)
        elif isinstance(basis, d.MainProfileSendBasis):
            from .profile_preparation import basis_digest
            if (basis.expected_scope.workspace_id != policy.workspace_id
                    or policy.allowed_content_sha256s != (basis_digest(basis),)
                    or basis.config_sha256 != sha(encoded(config)) or policy.max_calls != 1
                    or not callable(getattr(self._provider, 'generate_profile', None))):
                raise ServiceError('BLOCKED_LIVE', 403)
        elif isinstance(basis, d.MainContextSendBasis):
            if (basis.expected_scope.workspace_id != policy.workspace_id
                    or policy.allowed_content_sha256s != (basis.manifest_sha256,)
                    or basis.config_sha256 != sha(encoded(config))):
                raise ServiceError('BLOCKED_LIVE', 403)
        elif basis is not None and (basis.expected_scope.workspace_id != policy.workspace_id
                or policy.allowed_content_sha256s != (basis.content_sha256,)):
            raise ServiceError('BLOCKED_LIVE', 403)
        digest = sha(encoded(policy) + ('\n'+encoded(basis) if basis is not None else ''))
        previous = self._seen_policies.get(policy.policy_id)
        if previous is not None and previous != digest:
            raise ServiceError('VERSION_CONFLICT', 409)
        key = policy.workspace_id, policy.actor_id, session_id
        current = self._grants.get(key)
        if current is not None and current[0] == policy and current[2] == basis:
            return
        self._seen_policies[policy.policy_id] = digest
        self._grants[key] = policy, object(), basis

    def revoke(self, session_id):
        self._check_loop()
        session_id = _session_id(session_id)
        for key in tuple(self._grants):
            if key[2] == session_id:
                del self._grants[key]

    def authorization_token(self, actor, scope):
        """Current grant identity without retaining a provider or policy snapshot."""
        self._check_loop(bind=True)
        key = _identity(actor, scope)
        self._current_config()
        current = self._grants.get(key)
        if current is None or current[0].expires_at <= datetime.now(timezone.utc):
            raise ServiceError('BLOCKED_LIVE', 403)
        return self._version, current[1]

    def validate_authorization(self, actor, scope, token):
        current = self.authorization_token(actor, scope)
        if (type(token) is not tuple or len(token) != 2
                or token[0] is not current[0] or token[1] is not current[1]):
            raise ServiceError('BLOCKED_LIVE', 403)

    def resolve(self, actor, scope):
        self._check_loop(bind=True)
        key = _identity(actor, scope)
        if self._provider is None:
            return None
        config = self._current_config()
        return _RuntimeLease(self, key, actor, config, self._grants.get(key))


class _RuntimeLease:
    def __init__(self, registry, key, actor, config, grant):
        self._registry, self._key = registry, key
        self._actor = _copy(d.Actor, actor)
        self._version = registry._version
        self._fixed_provider = registry._provider
        self._config = config
        self._policy, self._nonce, self._basis = grant if grant is not None else (None, None, None)
        self.provider = _LeaseProvider(self)

    def snapshot(self):
        registry = self._registry
        registry._check_loop()
        current = registry._grants.get(self._key)
        nonce = current[1] if current is not None else None
        if (registry._version is not self._version or registry._provider is not self._fixed_provider
                or nonce is not self._nonce):
            raise ServiceError('BLOCKED_LIVE', 403)
        registry._current_config()
        if self._policy is not None and self._policy.expires_at <= datetime.now(timezone.utc):
            raise ServiceError('BLOCKED_LIVE', 403)
        return self._config, self._policy

    def snapshot_for(self, actor, scope):
        self._registry._check_loop()
        if _identity(actor, scope) != self._key:
            raise ServiceError('BLOCKED_LIVE', 403)
        return self.snapshot()

    def check_draft(self, actor, scope, composer_revision, content_sha256):
        self.snapshot_for(actor, scope)
        if self._basis is None:
            return
        basis = self._basis
        if isinstance(basis, (d.MainContextSendBasis, d.MainProfileSendBasis, d.MainMaterialSendBasis)):
            # A specialized grant never authorizes plain-text drafts.
            raise ServiceError('BLOCKED_LIVE', 403)
        if (scope != basis.expected_scope or composer_revision != basis.expected_composer_revision
                or content_sha256 != basis.content_sha256):
            raise ServiceError('BLOCKED_LIVE', 403)

    def check_submission(self, actor, request):
        request = _copy(d.AssistantMessageInput, request)
        self.check_draft(actor, request.expected_scope, request.expected_composer_revision, sha(request.content))
        if self._basis is not None and (request.request_id != self._basis.request_id
                or request.requested_skill is not None or request.attachment_ids):
            raise ServiceError('BLOCKED_LIVE', 403)

    def check_material_submission(self, actor, basis):
        basis = _copy(d.MainMaterialSendBasis, basis)
        config, policy = self.snapshot_for(actor, basis.expected_scope)
        if type(self._basis) is not d.MainMaterialSendBasis or basis != self._basis:
            raise ServiceError('BLOCKED_LIVE', 403)
        require_policy(config, policy, actor, basis.expected_scope, basis.manifest_sha256)

    def check_context_submission(self, actor, request, basis):
        """A granted context basis must equal the server's trusted rebuild exactly."""
        request = _copy(d.MainContextSubmission, request)
        basis = _copy(d.MainContextSendBasis, basis)
        self.snapshot_for(actor, request.expected_scope)
        granted = self._basis
        if type(granted) is not d.MainContextSendBasis or granted != basis:
            raise ServiceError('BLOCKED_LIVE', 403)
        if (request.request_id != basis.request_id
                or tuple(request.citation_ids) != tuple(item.saved_citation_id
                                                        for item in basis.source_bindings)):
            raise ServiceError('BLOCKED_LIVE', 403)

    def check_profile_submission(self, actor, request, basis):
        """Bind the original text to the whole granted local save plan."""
        from . import profile_preparation
        request = _copy(d.AssistantMessageInput, request)
        basis = _copy(d.MainProfileSendBasis, basis)
        config, policy = self.snapshot_for(actor, request.expected_scope)
        if type(self._basis) is not d.MainProfileSendBasis or self._basis != basis:
            raise ServiceError('BLOCKED_LIVE', 403)
        require_policy(config, policy, actor, request.expected_scope, profile_preparation.basis_digest(basis))
        if policy.max_calls != 1 or not callable(getattr(self._fixed_provider, 'generate_profile', None)):
            raise ServiceError('BLOCKED_LIVE', 403)
        try:
            rebuilt = profile_preparation.build_basis(request, config,
                base_profile_revision=basis.base_profile_revision, expected_intake_id=basis.expected_intake_id,
                expected_intake_revision=basis.expected_intake_revision, project_intake=basis.project_intake,
                conversation_history=basis.conversation_history)
            if rebuilt != basis:
                raise ValueError
        except (ValueError, TypeError):
            raise ServiceError('BLOCKED_LIVE', 403) from None

    def check_profile_execution(self, actor, request_id, prepared):
        """A request without its save basis and exact current wire is insufficient."""
        prepared = _copy(d.MainProfilePreparedInput, prepared)
        self.snapshot_for(actor, prepared.request.scope)
        basis = prepared.basis
        if request_id != basis.request_id:
            raise ServiceError('BLOCKED_LIVE', 403)
        submission = d.AssistantMessageInput(request_id=request_id, expected_scope=basis.expected_scope,
            expected_composer_revision=basis.expected_composer_revision, content=prepared.request.content)
        self.check_profile_submission(actor, submission, basis)

    def check_execution(self, actor, request_id, request):
        if isinstance(request, d.MainContextRequest):
            request = _copy(d.MainContextRequest, request)
            self.snapshot_for(actor, request.scope)
            basis = self._basis
            if type(basis) is not d.MainContextSendBasis or request.basis != basis:
                raise ServiceError('BLOCKED_LIVE', 403)
            return
        request = _copy(d.MainRequest, request)
        self.snapshot_for(actor, request.scope)
        if self._basis is None:
            return
        basis = self._basis
        if isinstance(basis, (d.MainContextSendBasis, d.MainProfileSendBasis, d.MainMaterialSendBasis)):
            raise ServiceError('BLOCKED_LIVE', 403)
        expected = basis.expected_scope.model_copy(update={
            'input_revision': basis.expected_scope.input_revision+1})
        if (request_id != basis.request_id or request.scope != expected
                or request.source_sha256 != basis.content_sha256):
            raise ServiceError('BLOCKED_LIVE', 403)

    def granted_context_format(self):
        """The granted basis fixes the context format for the whole run."""
        self.snapshot()
        if isinstance(self._basis, d.MainProfileSendBasis):
            raise ServiceError('BLOCKED_LIVE', 403)
        if type(self._basis) is d.MainContextSendBasis:
            return self._basis.input_format
        return 'library-context-v1'

    def _profile_preflight(self, prepared):
        """Repeat current policy/configuration and full content checks at transport boundaries."""
        try:
            self.check_profile_execution(self._actor, prepared.basis.request_id, prepared)
            return True
        except Exception:
            return False

    def _material_preflight(self, prepared):
        """Repeat current policy/configuration and exact material checks at transport boundaries."""
        try:
            self.check_material_submission(self._actor, prepared.request.basis)
            return True
        except Exception:
            return False

    def _preflight(self):
        """Boolean revalidation for the transport; exceptions are denial, never leases."""
        try:
            registry = self._registry
            registry._check_loop()
            current = registry._grants.get(self._key)
            return (registry._version is self._version and registry._provider is self._fixed_provider
                    and current is not None and current[1] is self._nonce and current[2] == self._basis)
        except Exception:
            return False


class _LeaseProvider:
    def __init__(self, lease):
        self._lease = lease

    @property
    def config(self):
        return self._lease.snapshot()[0]

    async def generate_material(self, prepared, *, expected_config=None, source_preflight=None):
        lease = self._lease
        config, _ = lease.snapshot()
        prepared = _copy(d.MainMaterialPreparedInput, prepared)
        lease.check_material_submission(lease._actor, prepared.request.basis)
        if expected_config is not None and config != expected_config:
            raise ServiceError('BLOCKED_LIVE', 403)
        preflight = lambda: (lease._material_preflight(prepared)
            and (source_preflight is None or source_preflight()))
        reply = await lease._fixed_provider.generate_material(prepared.request, expected_config=config, preflight=preflight)
        if reply.output is not None and not preflight():
            return d.MainMaterialReply(state='received', usage=reply.usage, provider_request_id=reply.provider_request_id, error_code='BLOCKED_LIVE')
        return reply

    async def generate_profile(self, prepared, *, expected_config=None):
        lease = self._lease
        config, _ = lease.snapshot()
        if expected_config is not None and _copy(d.MainModelConfig, expected_config) != config:
            raise ServiceError('BLOCKED_LIVE', 403)
        prepared = _copy(d.MainProfilePreparedInput, prepared)
        lease.check_profile_execution(lease._actor, prepared.basis.request_id, prepared)
        reply = _copy(d.MainProfileReply, await lease._fixed_provider.generate_profile(
            prepared.request, expected_config=config, preflight=lambda: lease._profile_preflight(prepared)))
        if reply.output is not None and not lease._profile_preflight(prepared):
            return d.MainProfileReply(state='received', usage=reply.usage,
                provider_request_id=reply.provider_request_id, error_code='BLOCKED_LIVE')
        return reply

    async def generate_rounds(self, prepared, *, expected_config=None):
        """Bounded-rounds send: the granted basis must equal the embedded one."""
        lease = self._lease
        config, policy = lease.snapshot()
        if expected_config is not None and _copy(d.MainModelConfig, expected_config) != config:
            raise ServiceError('BLOCKED_LIVE', 403)
        prepared = _copy(d.MainContextRoundsPreparedInput, prepared)
        basis = lease._basis
        if (type(basis) is not d.MainContextSendBasis or prepared.request.basis != basis
                or basis.input_format != 'library-context-v2'):
            raise ServiceError('BLOCKED_LIVE', 403)
        require_policy(config, policy, lease._actor, prepared.request.scope, basis.manifest_sha256)
        generate_rounds = getattr(lease._fixed_provider, 'generate_rounds', None)
        if not callable(generate_rounds):
            raise ServiceError('BLOCKED_LIVE', 403)
        return await generate_rounds(prepared, expected_config=config, preflight=lease._preflight)

    async def generate(self, request, *, expected_config=None):
        lease = self._lease
        config, policy = lease.snapshot()
        if expected_config is not None and _copy(d.MainModelConfig, expected_config) != config:
            raise ServiceError('BLOCKED_LIVE', 403)
        if isinstance(request, d.MainContextRequest):
            request = _copy(d.MainContextRequest, request)
            basis = lease._basis
            if type(basis) is not d.MainContextSendBasis or request.basis != basis:
                raise ServiceError('BLOCKED_LIVE', 403)
            require_policy(config, policy, lease._actor, request.scope, basis.manifest_sha256)
            generate_context = getattr(lease._fixed_provider, 'generate_context', None)
            if not callable(generate_context):
                raise ServiceError('BLOCKED_LIVE', 403)
            return await generate_context(request, expected_config=config, preflight=lease._preflight)
        request = _copy(d.MainRequest, request)
        if isinstance(lease._basis, (d.MainContextSendBasis, d.MainProfileSendBasis, d.MainMaterialSendBasis)):
            raise ServiceError('BLOCKED_LIVE', 403)
        require_policy(config, policy, lease._actor, request.scope, request.source_sha256)
        if lease._basis is not None:
            lease.check_execution(lease._actor, lease._basis.request_id, request)
        return await lease._fixed_provider.generate(request, expected_config=config)


def resolve_runtime(runtime_or_registry, actor, scope):
    if isinstance(runtime_or_registry, MainModelRegistry):
        return runtime_or_registry.resolve(actor, scope)
    if isinstance(runtime_or_registry, _RuntimeLease):
        runtime_or_registry.snapshot_for(actor, scope)
        return runtime_or_registry
    if runtime_or_registry is None or isinstance(runtime_or_registry, MainModelRuntime):
        return runtime_or_registry
    raise ServiceError('BLOCKED_LIVE', 403)
